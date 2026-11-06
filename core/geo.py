"""Working out where a photo was taken, from a record of where you were.

The whole thing rests on one choice: matching happens on **local wall-clock
time**, on both sides.

A camera writes local time with no timezone. The timeline writes UTC together
with the offset that was in force. Add the offset back and both are the same kind
of number - what a clock on the wall would have shown - so they compare directly,
and nobody has to remember what their camera was set to on a trip four years ago.
Whatever error remains is the camera clock genuinely being wrong, which is a real
thing worth reporting rather than a timezone puzzle to solve.
"""

from __future__ import annotations

import bisect
import datetime as dt
import math
from dataclasses import dataclass

from .timeline import Fix

# Two fixes closer together than this are the same place as far as anyone cares,
# so a position between them is an answer, not a guess.
SAME_PLACE_METRES = 100
# Beyond this, a single nearest fix is worth having but should be called rough.
ROUGH_AFTER_MINUTES = 15


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance, for saying how far apart two fixes are."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class Index:
    """Fixes sorted by local time, searchable by bisection."""

    def __init__(self, fixes: list[Fix]):
        self.fixes = sorted(fixes, key=lambda f: f.local)
        self._keys = [f.local for f in self.fixes]

    def __len__(self) -> int:
        return len(self.fixes)

    @property
    def first(self) -> dt.datetime | None:
        return self._keys[0] if self._keys else None

    @property
    def last(self) -> dt.datetime | None:
        return self._keys[-1] if self._keys else None

    def around(self, when: dt.datetime) -> tuple[Fix | None, Fix | None]:
        """The last fix at or before a moment, and the first at or after it."""
        if not self.fixes:
            return None, None
        i = bisect.bisect_left(self._keys, when)
        before = self.fixes[i - 1] if i > 0 else None
        after = self.fixes[i] if i < len(self.fixes) else None
        # bisect_left puts an exact hit at i, which is legitimately "before" too
        if after is not None and after.local == when:
            before = after
        return before, after


@dataclass
class Placement:
    ok: bool = False
    why: str = ""
    lat: float | None = None
    lon: float | None = None
    gap_minutes: float = 0.0
    how: str = ""
    spread_m: int = 0
    reference: str = ""
    approximate: bool = False

    @property
    def map_link(self) -> str:
        if not self.ok:
            return ""
        return f"https://www.google.com/maps/?q={self.lat:.6f},{self.lon:.6f}"


def place(index: Index, when: dt.datetime, max_gap_minutes: int = 60,
          interpolate: bool = True) -> Placement:
    """Where someone was at a moment, according to the fixes either side.

    Between two fixes the position is interpolated by time - stand still and both
    are the same place, so the answer is that place; move, and the answer is
    somewhere along the way, which is the honest reading of "you were between
    these two points".

    Beyond the limit, nothing is returned. A photo four hours from the nearest
    known position could be anywhere, and a confident wrong pin is worse than an
    empty one, because you would never think to check it.
    """
    before, after = index.around(when)
    gap_before = (when - before.local).total_seconds() / 60 if before else math.inf
    gap_after = (after.local - when).total_seconds() / 60 if after else math.inf

    if (interpolate and before and after and before is not after
            and gap_before <= max_gap_minutes and gap_after <= max_gap_minutes):
        span = (after.local - before.local).total_seconds() / 60
        t = (gap_before / span) if span > 0 else 0.0
        spread = distance_m(before.lat, before.lon, after.lat, after.lon)
        return Placement(
            ok=True,
            lat=before.lat + (after.lat - before.lat) * t,
            lon=before.lon + (after.lon - before.lon) * t,
            gap_minutes=round(min(gap_before, gap_after), 1),
            how=("between two fixes at the same spot" if spread < SAME_PLACE_METRES
                 else "interpolated between two fixes"),
            spread_m=int(round(spread)),
            reference=before.source or before.kind,
            approximate=spread >= SAME_PLACE_METRES)

    best, gap = (None, math.inf)
    if before and gap_before <= gap_after:
        best, gap = before, gap_before
    elif after:
        best, gap = after, gap_after
    if best is None or gap > max_gap_minutes:
        return Placement(why=f"nothing within {max_gap_minutes} minute(s)")

    return Placement(ok=True, lat=best.lat, lon=best.lon, gap_minutes=round(gap, 1),
                     how="nearest single fix", spread_m=0,
                     reference=best.source or best.kind,
                     approximate=gap > ROUGH_AFTER_MINUTES)


def fixes_from_photos(paths, progress=None) -> list[Fix]:
    """Photos that already carry a location, turned into fixes.

    A phone photo is unusually good evidence: it records the satellite time (UTC)
    AND the camera clock's local time, so subtracting one from the other gives the
    timezone that phone was set to - the same thing the timeline's "+03:00" gives,
    from a completely independent source.
    """
    from .photo import is_picture, read_gps

    out: list[Fix] = []
    paths = list(paths)
    for i, p in enumerate(paths, 1):
        if progress:
            progress(i, len(paths), p)
        if not is_picture(p):
            continue
        g = read_gps(p)
        if not g.has_gps:
            continue
        offset = g.offset_minutes
        local = g.taken
        if g.utc is not None and local is not None and offset is None:
            # round to the nearest quarter hour - every real timezone is one
            offset = int(round((local - g.utc.replace(tzinfo=None)).total_seconds()
                               / 900.0)) * 15
        if local is None and g.utc is not None and offset is not None:
            local = g.utc.replace(tzinfo=None) + dt.timedelta(minutes=offset)
        if local is None:
            continue
        out.append(Fix(local=local, offset_minutes=offset or 0,
                       lat=g.lat, lon=g.lon, kind="photo",
                       source=__import__("os").path.basename(p),
                       # A camera that recorded no satellite time gives no
                       # timezone, and zero is an assumption rather than a fact.
                       # Said here so that anything exporting these can say it
                       # too - a UTC moment from an assumed offset can be twelve
                       # hours out, which is a crossing that never happened.
                       offset_known=offset is not None))
    return out


def suggest_clock_drift(index: Index, takens, search_minutes: int = 240):
    """How wrong the camera clock looks, judged by the photos it took.

    If the clock is right these differences scatter around zero; if it is twelve
    minutes fast they cluster near twelve. The median is used, not the average,
    so a few photos taken where there was no signal cannot drag the answer.

    Only ever a suggestion. A systematic error and a day spent somewhere with poor
    reception look alike from here, so a person should look before agreeing.
    """
    diffs = []
    for taken in takens:
        if not taken:
            continue
        for f in index.around(taken):
            if f is None:
                continue
            d = (taken - f.local).total_seconds() / 60
            if abs(d) <= search_minutes:
                diffs.append(d)
    if len(diffs) < 6:
        return {"ok": False, "why": "not enough photos near a known position to tell",
                "samples": len(diffs)}
    diffs.sort()
    median = diffs[len(diffs) // 2]
    spread = diffs[int(len(diffs) * 0.75)] - diffs[int(len(diffs) * 0.25)]
    return {"ok": True, "minutes": round(median, 1), "spread": round(spread, 1),
            "samples": len(diffs),
            "confident": abs(median) > 2 and spread < max(20, abs(median))}
