"""Which shoot a moment belongs to.

A folder of photographs covers a stretch of time - the afternoon in Rome, the
fortnight in Spain. A clip shot during that stretch belongs with them, whatever
folder the card reader happened to drop it in, and that is the whole of this
module: turn folders into time windows, and answer "which of these was this
taken among".

Three rules, and each is a way the obvious version goes wrong:

**A window that CONTAINS the moment beats one that is merely near it.** Nearness
alone puts a clip shot at noon into yesterday's folder when yesterday ran late.

**The tightest window wins.** `Photos/2022` spans a year and `Photos/2022/Spain`
spans a fortnight; both contain the clip and only one of them is an answer.

**Two equally good windows are an answer nobody can check, so they are refused
and both are named.** Two shoots on the same afternoon is not a rare case - it
is what a wedding and a walk home look like - and a coin toss puts a clip
somewhere you will not find it.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

# How far outside a shoot's own hours a clip may still belong to it. A shoot
# that ended at ten and a clip at half past eleven are the same evening; a clip
# from the following afternoon is not.
NEAR_HOURS = 12

# A folder whose photographs span longer than this is not a shoot, it is a
# bucket - a year folder with loose photographs in it covers every clip you own.
# Left in, it CONTAINS everything and therefore wins everything, and clips get
# filed into the year rather than into the fortnight abroad. Which is true, and
# useless.
LONGEST_SHOOT_DAYS = 45


@dataclass
class Window:
    """One folder, and the stretch of time its photographs cover."""
    key: str                       # the folder, or wherever it is going
    first: _dt.datetime
    last: _dt.datetime
    photos: int = 0

    @property
    def span(self) -> _dt.timedelta:
        return self.last - self.first

    def holds(self, when: _dt.datetime) -> bool:
        return self.first <= when <= self.last

    def distance(self, when: _dt.datetime) -> _dt.timedelta:
        if self.holds(when):
            return _dt.timedelta(0)
        return (self.first - when) if when < self.first else (when - self.last)

    def describe(self) -> str:
        if self.first.date() == self.last.date():
            return f"{self.first:%Y-%m-%d %H:%M}-{self.last:%H:%M}"
        return f"{self.first:%Y-%m-%d} to {self.last:%Y-%m-%d}"


def _gap(span) -> str:
    """How far outside the shoot, in units a person would use.

    "0h from" for seven minutes is arithmetic, not an answer - and this line is
    the whole justification for the file the clip is about to move into.
    """
    minutes = span.total_seconds() / 60.0
    if minutes < 90:
        return f"{minutes:.0f} min"
    if minutes < 60 * 36:
        return f"{minutes / 60:.0f}h"
    return f"{minutes / 1440:.0f} days"


@dataclass
class Found:
    window: Window | None = None
    why: str = ""
    exact: bool = False            # inside the shoot's own hours, not just near

    def __bool__(self) -> bool:
        return self.window is not None


def build(entries) -> list[Window]:
    """Windows from (key, capture time) pairs. Anything undated is ignored."""
    spans: dict = {}
    for key, when in entries:
        if not key or when is None:
            continue
        got = spans.get(key)
        if got is None:
            spans[key] = Window(key=key, first=when, last=when, photos=1)
            continue
        got.first = min(got.first, when)
        got.last = max(got.last, when)
        got.photos += 1
    return sorted(spans.values(), key=lambda w: (w.first, w.key))


def from_survey(found) -> list[Window]:
    """Windows from a Library survey - one per folder that HAS photographs.

    Only folders with photographs of their own, never the rolled-up totals: a
    year folder rolled up spans a year and contains every clip you own, which is
    true and useless. The shoot is the folder the pictures are actually in.
    """
    import datetime as dt

    out = []
    for path, state in (found.folders or {}).items():
        if not state.photos or not state.first_taken:
            continue
        try:
            first = dt.datetime.fromisoformat(state.first_taken)
            last = dt.datetime.fromisoformat(state.last_taken or state.first_taken)
        except ValueError:
            continue
        out.append(Window(key=path, first=first, last=last, photos=state.photos))
    return sorted(out, key=lambda w: (w.first, w.key))


def match(when, windows, near_hours: float = NEAR_HOURS,
          longest_shoot_days: float = LONGEST_SHOOT_DAYS) -> Found:
    """The shoot this moment was taken among, or nothing and the reason why."""
    if when is None:
        return Found(why="it has no capture time")
    if not windows:
        return Found(why="there are no dated photos to compare it against")

    wide = _dt.timedelta(days=float(longest_shoot_days))
    buckets = [w for w in windows if w.span > wide]
    windows = [w for w in windows if w.span <= wide]
    if not windows:
        return Found(why=(f"the only dated folders span more than "
                          f"{longest_shoot_days:g} days, which is a bucket rather "
                          f"than a shoot - " + ", ".join(
                              sorted(w.key for w in buckets[:2]))))

    inside = [w for w in windows if w.holds(when)]
    if inside:
        tightest = min(w.span for w in inside)
        best = [w for w in inside if w.span == tightest]
        if len(best) > 1:
            return Found(why=("it falls inside " + " and ".join(
                sorted(w.key for w in best[:3])) +
                " at the same time, so which one is a guess"))
        return Found(best[0], f"taken during {best[0].describe()}", True)

    near = _dt.timedelta(hours=float(near_hours))
    close = [w for w in windows if w.distance(when) <= near]
    if not close:
        nearest = min(windows, key=lambda w: w.distance(when))
        hours = nearest.distance(when).total_seconds() / 3600.0
        return Found(why=(f"nothing was photographed within {near_hours:g} hours of "
                          f"it - the nearest shoot is {hours:.0f} hours away"))
    closest = min(w.distance(when) for w in close)
    best = [w for w in close if w.distance(when) == closest]
    if len(best) > 1:
        return Found(why=("it is the same distance from " + " and ".join(
            sorted(w.key for w in best[:3])) + ", so which one is a guess"))
    return Found(best[0], f"{_gap(closest)} from {best[0].describe()}", False)
