"""Tying a RAW to its JPEG by identity, so the link survives being reorganised.

The Windows app finds a RAW by WHERE IT SITS - same relative path under its
tree, same base name. That works right up until the library is rearranged, and
then it silently does not: rename a shoot folder and every RAW in it is orphaned
without a word.

So a pair is established on what the two files ARE, not where they are:

    capture time  +  camera model  +  base name

Capture time to the second is already close to unique for one camera; the model
separates two bodies shooting the same event; the base name catches the rest and
survives a card being re-numbered. None of the three depends on a path, so the
library can be reshaped freely and the pairing still holds.

Nothing here needs to have been prepared in advance. A tree separated months ago
can be re-paired from what the files themselves say.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass, field

from .photo import Capture, kind, read_capture

# How far apart two files' capture times may be and still be the same shot.
# Not zero: a camera writing a JPEG and a RAW can stamp them a second apart, and
# some bodies round the two differently.
SAME_SHOT_SECONDS = 2


def base_name(path: str) -> str:
    """`P1130088.RW2` -> `p1130088`. Case-folded, because Windows does not care."""
    return os.path.splitext(os.path.basename(path))[0].lower()


@dataclass(frozen=True)
class Identity:
    """What a file is, in terms that do not mention where it lives."""
    base: str
    model: str
    taken: str          # to the second, as text, so it is hashable and printable

    def __str__(self) -> str:
        bits = [self.base]
        if self.model:
            bits.append(self.model)
        if self.taken:
            bits.append(self.taken)
        return "  ".join(bits)


def identity(cap: Capture, path: str) -> Identity:
    return Identity(
        base=base_name(path),
        model=(cap.model or "").strip(),
        taken=cap.taken.strftime("%Y-%m-%d %H:%M:%S") if cap.taken else "",
    )


@dataclass
class Index:
    """Everything known about one tree, keyed several ways.

    Keyed by all three of base name, base+model and full identity, because the
    strongest key is not always available - a RAW whose EXIF cannot be read still
    has a name, and a name is usually enough within one library.
    """
    by_identity: dict[Identity, list[str]] = field(default_factory=lambda: defaultdict(list))
    by_base_model: dict[tuple[str, str], list[str]] = field(default_factory=lambda: defaultdict(list))
    by_base: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    captures: dict[str, Capture] = field(default_factory=dict)
    unreadable: list[str] = field(default_factory=list)
    # How many files of the right kind were SEEN, before any narrowing. The
    # difference between "that tree is empty" and "nothing in it could possibly
    # match" - which read the same from `len()` and mean opposite things.
    considered: int = 0

    def add(self, path: str, cap: Capture) -> None:
        ident = identity(cap, path)
        self.captures[path] = cap
        self.by_identity[ident].append(path)
        self.by_base_model[(ident.base, ident.model)].append(path)
        self.by_base[ident.base].append(path)
        if not cap.ok:
            self.unreadable.append(path)

    def __len__(self) -> int:
        return len(self.captures)


def build_index(paths, want=("jpeg", "image"), progress=None, names=None,
                reader=None) -> Index:
    """Read every candidate file once and key it every way we might need.

    `names` is the set of base names that could possibly be asked about, and
    passing it is the difference between a run that takes a minute and one that
    takes an hour. Filing five exports used to read the EXIF of every one of a
    hundred thousand photographs in the library first.

    It is not a shortcut with a cost, which is the part worth being sure of:
    **every tier of `find_partner` keys on the base name** - full identity, then
    name and camera, then name, then name alone. A file whose name is not in the
    set can never be the answer to any of those, so reading it is work whose
    result could not be used. The answers are identical, and there is a test
    that runs a whole tree both ways and compares.

    Reading is what costs, so the narrowing happens before it: the walk itself
    is a few thousand stats, and opening a hundred thousand files to read the
    front of each is minutes over a network share.

    `reader` is a `core.facts.Reader`. Given one, a file whose size and date
    have not moved since the last run is answered from its note and never opened
    at all - which is the same argument one step further: the cheapest read is
    the one that does not happen.
    """
    idx = Index()
    wanted = None if names is None else {str(n).strip().lower() for n in names}
    keep = []
    for p in paths:
        if kind(p) not in want:
            continue
        idx.considered += 1
        if wanted is None or base_name(p) in wanted:
            keep.append(p)
    for i, p in enumerate(keep, 1):
        if progress:
            progress(i, len(keep), p)
        idx.add(p, reader.capture(p) if reader is not None else read_capture(p))
    return idx


@dataclass
class Match:
    """One RAW and the JPEG it belongs to, with how sure we are and why."""
    raw: str
    jpeg: str | None
    how: str              # what actually matched
    confident: bool
    candidates: int = 1   # more than one means it was ambiguous


def _within(a: Capture, b: Capture) -> bool:
    if not a.taken or not b.taken:
        return True       # nothing to contradict; other keys have to carry it
    return abs((a.taken - b.taken).total_seconds()) <= SAME_SHOT_SECONDS


def find_partner(raw_path: str, raw_cap: Capture, jpegs: Index) -> Match:
    """The JPEG a RAW belongs to, tried strongest key first.

    Ambiguity is reported, never resolved by guessing. Two JPEGs that both look
    like this RAW's partner mean the answer is unknown, and moving the RAW on a
    coin toss is how files end up somewhere nobody can find them.
    """
    ident = identity(raw_cap, raw_path)

    exact = jpegs.by_identity.get(ident, [])
    if len(exact) == 1:
        return Match(raw_path, exact[0], "name, camera and capture time", True)
    if len(exact) > 1:
        return Match(raw_path, None, "several JPEGs share this name, camera and time",
                     False, len(exact))

    if ident.model:
        same = jpegs.by_base_model.get((ident.base, ident.model), [])
        near = [p for p in same if _within(raw_cap, jpegs.captures[p])]
        if len(near) == 1:
            return Match(raw_path, near[0], "name and camera", True)
        if len(near) > 1:
            return Match(raw_path, None, "several JPEGs share this name and camera",
                         False, len(near))

    same = jpegs.by_base.get(ident.base, [])
    near = [p for p in same if _within(raw_cap, jpegs.captures[p])]
    if len(near) == 1:
        return Match(raw_path, near[0], "name", True)
    if len(near) > 1:
        return Match(raw_path, None, f"{len(near)} JPEGs share this name",
                     False, len(near))

    # Last resort: the name matches but the clocks disagree.
    #
    # This is not a hypothetical. Correct a camera's clock across a shoot and
    # every JPEG in it moves in time while the RAWs do not, so a pair that is
    # obviously a pair fails every key above. Refusing here would report the whole
    # shoot as orphaned and offer to put it aside - a clock correction turning
    # into a mass file move is not an acceptable way to be strict.
    #
    # So it matches, and says plainly that it is going on the name alone. The
    # ambiguous case is still refused, and this is still the weakest tier: it is
    # only reached when nothing that checks the time worked.
    if len(same) == 1:
        return Match(raw_path, same[0],
                     "name only - the capture times disagree, so this is by name alone",
                     False)
    if len(same) > 1:
        return Match(raw_path, None,
                     f"{len(same)} JPEGs share this name and none of their times match",
                     False, len(same))

    return Match(raw_path, None, "no JPEG anywhere in the library matches it", False, 0)


def pair_trees(raw_paths, jpeg_index: Index, progress=None) -> list[Match]:
    """Every RAW, matched against the whole library rather than one folder.

    Searching the WHOLE library is the point. A RAW whose JPEG merely MOVED looks
    exactly like a RAW whose JPEG was deleted if you only look where it used to
    be - and treating the first as the second would put away files during an
    ordinary tidy-up.
    """
    out: list[Match] = []
    raw_paths = list(raw_paths)
    for i, rp in enumerate(raw_paths, 1):
        if kind(rp) != "raw":
            continue
        if progress:
            progress(i, len(raw_paths), rp)
        out.append(find_partner(rp, read_capture(rp), jpeg_index))
    return out
