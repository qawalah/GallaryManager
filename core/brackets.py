"""Finding exposure brackets: the three (or five, or seven) frames of one scene.

The whole thing rests on one fact:

    a burst and a bracket look identical except for the exposure bias.

Ten frames of a bird taking off and three frames of a landscape at -1/0/+1 are
both "several photos seconds apart with the same settings". The only thing in
the file that tells them apart is the bias: burst frames all share one value,
bracket frames cannot. So bias decides, and nothing else does.

Frames are grouped by folder, ordered by capture time, and cut into runs wherever
more than a few seconds pass or the camera, aperture, ISO or focal length
changes. Inside a run, a set ends as soon as a bias value repeats - fire three
brackets back to back and the biases read -1 0 +1 -1 0 +1, so the fourth frame is
where the cut goes. A set counts as a bracket when its biases form an even ladder
centred on zero, or the camera flagged auto-bracket itself.

Bracketing BY HAND - turning the shutter dial yourself - leaves every frame at
bias 0 with no flag, and there is genuinely nothing in the file separating that
from three deliberate exposures of a changing scene. Those are reported
separately as "probable" and never acted on unless asked, because grouping three
unrelated photos and culling two of them is not a mistake you can undo.

Nothing here reads pixels, and nothing here writes.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

from .photo import Capture, is_picture, read_capture

MAX_GAP_SECONDS = 3.0
MIN_SET = 3
MAX_SET = 9

# A camera records bias in thirds of a stop, so 1/3 = 0.333 and 2/3 = 0.667 both
# come back rounded. A sixth of a stop of slack accepts that without letting an
# uneven ladder through.
LADDER_SLACK = 0.17

# Hand bracketing has to move the shutter by nearly a stop before it is worth
# calling deliberate; less than that is just the camera metering differently.
HAND_SPREAD_STOPS = 0.9


@dataclass
class Frame:
    """One photo, reduced to what deciding a bracket needs."""
    path: str
    name: str
    folder: str
    taken: object
    ev: float | None = None
    exposure_mode: int | None = None
    exposure: float | None = None
    fnumber: float | None = None
    iso: int | None = None
    focal_length: float | None = None
    model: str | None = None


@dataclass
class BracketSet:
    members: list[Frame]
    representative: Frame
    confidence: str            # "certain" or "probable"
    why: str
    evs: list[float] = field(default_factory=list)

    @property
    def folder(self) -> str:
        return self.members[0].folder

    @property
    def taken(self):
        return self.members[0].taken

    @property
    def size(self) -> int:
        return len(self.members)

    def label(self) -> str:
        names = [m.name for m in self.members]
        return f"{names[0]} .. {names[-1]}" if len(names) > 2 else " + ".join(names)


@dataclass
class Found:
    sets: list[BracketSet] = field(default_factory=list)
    by_path: dict[str, BracketSet] = field(default_factory=dict)
    examined: int = 0
    no_capture_time: list[str] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)

    @property
    def certain(self) -> int:
        return sum(1 for s in self.sets if s.confidence == "certain")

    @property
    def probable(self) -> int:
        return sum(1 for s in self.sets if s.confidence == "probable")

    def set_of(self, path: str) -> BracketSet | None:
        """The set a file belongs to, matched case-insensitively like the disk."""
        return self.by_path.get(os.path.normcase(os.path.abspath(path)))


def same_setup(a: Frame, b: Frame) -> bool:
    """Two frames shot with the same settings, give or take the camera's rounding.

    Aperture and focal length arrive as rationals the camera rounded itself
    (56/10, 25/1), so they are compared with a tolerance: f/5.6 and f/5.66 are one
    setting written twice, and demanding equality would cut a bracket in half.
    """
    if a.model and b.model and a.model != b.model:
        return False
    if a.iso and b.iso and a.iso != b.iso:
        return False
    for x, y in ((a.fnumber, b.fnumber), (a.focal_length, b.focal_length)):
        if x is not None and y is not None:
            if abs(float(x) - float(y)) > max(0.05, 0.02 * abs(float(x))):
                return False
    return True


def is_ladder(evs) -> bool:
    """Distinct biases, evenly spaced, centred on zero: -1 0 +1, -2 0 +2, -3 -1.5 0 1.5 3."""
    s = sorted(float(e) for e in evs)
    if len(s) < 3:
        return False
    step = s[1] - s[0]
    if step <= 0.001:
        return False
    for i in range(1, len(s)):
        if abs((s[i] - s[i - 1]) - step) > LADDER_SLACK:
            return False
    return abs(s[0] + s[-1]) <= LADDER_SLACK


def exposure_spread_stops(members) -> float:
    """How many stops separate the fastest and slowest shutter speed in a set."""
    times = [float(m.exposure) for m in members if m.exposure and float(m.exposure) > 0]
    if len(times) < 2:
        return 0.0
    lo, hi = min(times), max(times)
    return math.log(hi / lo, 2) if lo > 0 else 0.0


def representative(members) -> Frame:
    """Which frame stands for the whole set.

    The metered exposure - bias zero - is the one you would look at to judge the
    shot, so it carries the preview and the rating. With no bias recorded, the
    middle frame in time is the nearest equivalent.
    """
    if members and all(m.ev is not None for m in members):
        return min(members, key=lambda m: abs(float(m.ev)))
    return members[(len(members) - 1) // 2]


def split_run(run):
    """Cut one continuous run into candidate sets, breaking where a bias repeats.

    The repeat rule handles a burst for free: ten frames all at bias 0 repeat
    immediately, so every "set" is a single frame and none of them qualifies.
    """
    sets, current, seen = [], [], set()
    for f in run:
        key = "none" if f.ev is None else f"{float(f.ev):.3f}"
        if key in seen:
            sets.append(current)
            current, seen = [], set()
        current.append(f)
        seen.add(key)
    if current:
        sets.append(current)
    return sets


def read_frames(paths, progress=None, reader=None):
    """Read every picture once. Returns frames, no-time paths, unreadable paths.

    `reader` is a `core.facts.Reader`. Given one, a picture whose size, date and
    inode have not moved since the last run is not opened at all - which matters
    here more than almost anywhere, because five separate tasks group brackets
    and each of them was reading the whole tree to do it.
    """
    frames, no_time, unreadable = [], [], []
    paths = list(paths)
    for i, path in enumerate(paths, 1):
        if not is_picture(path):
            continue
        if progress:
            progress(i, len(paths), path)
        c: Capture = (reader.capture(path) if reader is not None
                      else read_capture(path))
        if not c.ok:
            unreadable.append(path)
            continue
        if not c.taken:
            no_time.append(path)
            continue
        frames.append(Frame(
            path=path, name=os.path.basename(path), folder=os.path.dirname(path),
            taken=c.taken, ev=c.ev, exposure_mode=c.exposure_mode,
            exposure=c.exposure, fnumber=c.fnumber, iso=c.iso,
            focal_length=c.focal_length, model=c.model))
    return frames, no_time, unreadable


def runs_in(frames, max_gap_seconds: float = MAX_GAP_SECONDS):
    """Frames of one folder, in time order, cut wherever the shooting stopped."""
    ordered = sorted(frames, key=lambda f: (f.taken, f.name))
    out, run = [], []
    for f in ordered:
        if run:
            gap = (f.taken - run[-1].taken).total_seconds()
            if gap > max_gap_seconds or not same_setup(run[-1], f):
                out.append(run)
                run = []
        run.append(f)
    if run:
        out.append(run)
    return out


def find(paths, *, max_gap_seconds: float = MAX_GAP_SECONDS,
         min_set: int = MIN_SET, max_set: int = MAX_SET,
         include_probable: bool = False, progress=None, reader=None) -> Found:
    """Every bracket set among these files."""
    frames, no_time, unreadable = read_frames(paths, progress, reader=reader)
    found = Found(examined=len(frames), no_capture_time=no_time, unreadable=unreadable)

    by_folder: dict[str, list[Frame]] = {}
    for f in frames:
        by_folder.setdefault(f.folder, []).append(f)

    for folder_frames in by_folder.values():
        for run in runs_in(folder_frames, max_gap_seconds):
            for candidate in split_run(run):
                s = _judge(candidate, min_set, max_set)
                if s:
                    found.sets.append(s)
            if include_probable:
                s = _judge_by_hand(run, min_set, max_set)
                if s:
                    found.sets.append(s)

    found.sets.sort(key=lambda s: (s.folder, s.taken))
    for s in found.sets:
        for m in s.members:
            found.by_path.setdefault(os.path.normcase(os.path.abspath(m.path)), s)
    return found


def _judge(members, min_set, max_set) -> BracketSet | None:
    """A set the camera itself gives us grounds to call a bracket."""
    if not (min_set <= len(members) <= max_set):
        return None
    evs = [float(m.ev) for m in members if m.ev is not None]
    if len(evs) != len(members):
        return None                       # a missing bias means we cannot be sure
    flagged = any(m.exposure_mode == 2 for m in members)
    ladder = is_ladder(evs)
    if not flagged and not ladder:
        return None
    if flagged and ladder:
        why = "the camera flagged auto-bracket, and the bias values form a ladder"
    elif flagged:
        why = "the camera flagged auto-bracket"
    else:
        why = "the bias values form an even ladder centred on zero"
    return BracketSet(members=list(members), representative=representative(members),
                      confidence="certain", why=why, evs=sorted(evs))


def _judge_by_hand(run, min_set, max_set) -> BracketSet | None:
    """Bracketed by hand: one bias for the whole run, but the shutter walking."""
    if not (min_set <= len(run) <= max_set):
        return None
    evs = [float(m.ev) for m in run if m.ev is not None]
    one_bias = not evs or len(set(evs)) == 1
    times = [m.exposure for m in run if m.exposure]
    if not one_bias or len(times) != len(run) or len(set(times)) != len(run):
        return None
    spread = exposure_spread_stops(run)
    if spread < HAND_SPREAD_STOPS:
        return None
    return BracketSet(
        members=list(run), representative=representative(run), confidence="probable",
        why=(f"no bias recorded, but the shutter moved {spread:.1f} stop(s) across "
             f"{len(run)} frames taken seconds apart"),
        evs=sorted(set(evs)))
