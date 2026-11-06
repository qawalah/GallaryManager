"""Reading a Google Timeline export, and keeping it somewhere useful.

Google Takeout no longer holds this data. Timeline lives on the phone now, and a
Takeout "Timeline" export returns two files - settings and a note about backups -
with no locations at all. The real export comes off the phone:
Maps -> profile -> Your Timeline -> ... -> Location & privacy settings ->
Export Timeline data.

The file that produces has four sources of position, and all four are worth
having:

    timelinePath   the dense track - a fix every twenty minutes or so
    visit          a place you stayed, spanning a period rather than an instant
    activity       a journey, its start and its end
    rawSignals     individual readings, which carry an accuracy in metres

Two things about the format will bite anyone who writes this a second time.
`rawSignals` capitalises it `LatLng` while everything else uses `latLng` - miss
that and twelve thousand fixes vanish. And every timestamp carries its UTC
offset, which is the single most useful fact in the file: it says which timezone
you were standing in at that moment, which is exactly what a camera never records.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from dataclasses import dataclass, field

from .photo import sane_coordinate

STORE_HEADER = "#photo-manager location index v1"
_TIME_KEYS = ("startTime", "endTime")


@dataclass
class Fix:
    """One "at this moment, here"."""
    local: dt.datetime          # wall-clock time where the person was standing
    offset_minutes: int
    lat: float
    lon: float
    kind: str = "path"
    accuracy_m: float | None = None
    source: str = ""            # a filename, when the fix came from a photo
    # Whether the offset above is KNOWN or merely assumed to be zero.
    #
    # A timeline export always says which timezone the person was standing in; a
    # photograph says so only when the camera recorded a satellite time as well
    # as its own clock. Where it did not, the local time is the only honest
    # thing in the record, and a UTC moment computed from an assumed offset can
    # be twelve hours out - which is a crossing that never happened, or one
    # missed. So it is said, and it travels with the fix into the export.
    offset_known: bool = True

    @property
    def utc(self) -> dt.datetime:
        return self.local - dt.timedelta(minutes=self.offset_minutes)


def parse_point(text) -> tuple[float, float] | None:
    """`"24.497858°, 39.642967°"` -> two numbers.

    Google writes every coordinate this way - degree signs and all, without a
    single variation in 333,953 of them. Parsed explicitly rather than with
    `float()` on a locale-dependent string, because where the decimal separator
    is a comma, "24.497858" quietly becomes twenty-four million.
    """
    if not isinstance(text, str):
        return None
    parts = text.replace("°", " ").split(",")
    if len(parts) < 2:
        return None
    try:
        lat, lon = float(parts[0].strip()), float(parts[1].strip())
    except ValueError:
        return None
    return (lat, lon) if sane_coordinate(lat, lon) else None


def parse_time(text) -> tuple[dt.datetime, int] | None:
    """`"2012-08-16T23:31:00.000+03:00"` -> the local moment and its offset."""
    if not isinstance(text, str) or not text.strip():
        return None
    s = text.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        when = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if when.tzinfo is None:
        return (when, 0)
    offset = int(when.utcoffset().total_seconds() // 60)
    return (when.replace(tzinfo=None), offset)


def _fix(point, when, kind, accuracy=None) -> Fix | None:
    if not point or not when:
        return None
    return Fix(local=when[0], offset_minutes=when[1], lat=point[0], lon=point[1],
               kind=kind, accuracy_m=accuracy)


def read_export(path: str, progress=None) -> list[Fix]:
    """Every position in a Google Timeline export, sorted by local time."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict):
        raise ValueError("that file is not a Timeline export")

    out: list[Fix] = []
    segments = doc.get("semanticSegments") or []
    for i, seg in enumerate(segments, 1):
        if progress and i % 5000 == 0:
            progress(i, len(segments), path)
        if not isinstance(seg, dict):
            continue
        start = parse_time(seg.get("startTime"))
        end = parse_time(seg.get("endTime"))

        for p in seg.get("timelinePath") or []:
            f = _fix(parse_point(p.get("point")), parse_time(p.get("time")), "path")
            if f:
                out.append(f)

        visit = seg.get("visit")
        if isinstance(visit, dict):
            place = ((visit.get("topCandidate") or {}).get("placeLocation") or {})
            point = parse_point(place.get("latLng"))
            # A stay spans a period, so BOTH ends are recorded: every photo taken
            # during it then resolves to the place, instead of drifting toward
            # whatever came next.
            for when in (start, end):
                f = _fix(point, when, "visit")
                if f:
                    out.append(f)

        activity = seg.get("activity")
        if isinstance(activity, dict):
            for side, when in (("start", start), ("end", end)):
                point = parse_point((activity.get(side) or {}).get("latLng"))
                f = _fix(point, when, "activity")
                if f:
                    out.append(f)

    for raw in doc.get("rawSignals") or []:
        if not isinstance(raw, dict):
            continue
        pos = raw.get("position")
        if not isinstance(pos, dict):
            continue
        # capital L - everything else in the file uses latLng
        f = _fix(parse_point(pos.get("LatLng")), parse_time(pos.get("timestamp")),
                 "signal:" + str(pos.get("source") or "?"), pos.get("accuracyMeters"))
        if f:
            out.append(f)

    out.sort(key=lambda f: f.local)
    return out


# ------------------------------------------------------------------- the store

def write_store(path: str, fixes: list[Fix], source: str = "") -> str:
    """Save the imported positions where the app can read them quickly.

    Plain tab-separated text, sorted by time, so a date range can be found by
    comparing strings while streaming - no dates parsed and no objects built for
    rows that were never going to be used. Text rather than something binary so
    it can be opened and looked at when a result seems wrong.
    """
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(STORE_HEADER + "\n")
        fh.write(f"#source={source}\n")
        fh.write(f"#imported={dt.datetime.now():%Y-%m-%d %H:%M:%S}\n")
        fh.write(f"#count={len(fixes)}\n")
        # Two columns were added in 3.3 and the format did not change: an older
        # reader takes the first five and ignores the rest, which is the whole
        # reason this is tab-separated text rather than something clever.
        fh.write("local\toffset\tlat\tlon\tkind\taccuracy\tsource\tzone\n")
        for f in fixes:
            fh.write(f"{f.local:%Y-%m-%dT%H:%M:%S}\t{f.offset_minutes}\t"
                     f"{f.lat:.7f}\t{f.lon:.7f}\t{f.kind}\t"
                     f"{'' if f.accuracy_m is None else round(float(f.accuracy_m), 1)}\t"
                     f"{str(f.source or '').replace(chr(9), ' ')}\t"
                     f"{1 if f.offset_known else 0}\n")
    return path


@dataclass
class StoreInfo:
    ok: bool = False
    count: int = 0
    first: str = ""
    last: str = ""
    source: str = ""
    imported: str = ""


def store_info(path: str) -> StoreInfo:
    """What the store holds, without reading all of it."""
    if not path or not os.path.isfile(path):
        return StoreInfo()
    try:
        with open(path, encoding="utf-8") as fh:
            if fh.readline().strip() != STORE_HEADER:
                return StoreInfo()
            info = StoreInfo(ok=True)
            for line in fh:
                if line.startswith("#source="):
                    info.source = line[8:].strip()
                elif line.startswith("#imported="):
                    info.imported = line[10:].strip()
                elif line.startswith("#count="):
                    info.count = int(line[7:].strip() or 0)
                elif line.startswith("local\t") or not line.strip():
                    continue
                else:
                    stamp = line.split("\t", 1)[0]
                    if not info.first:
                        info.first = stamp
                    info.last = stamp
            return info
    except (OSError, ValueError):
        return StoreInfo()


def read_store(path: str, since: dt.datetime | None = None,
               until: dt.datetime | None = None) -> list[Fix]:
    """Positions from the store, optionally only those in a date range.

    The range is what makes this quick. A week away needs a few hundred of three
    hundred thousand positions, and because the file is sorted text the rest are
    skipped on a string comparison.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"no imported timeline at {path}")
    lo = f"{since:%Y-%m-%dT%H:%M:%S}" if since else ""
    hi = f"{until:%Y-%m-%dT%H:%M:%S}" if until else ""

    out: list[Fix] = []
    with open(path, encoding="utf-8") as fh:
        if fh.readline().strip() != STORE_HEADER:
            raise ValueError(f"that is not an imported timeline: {path}")
        for line in fh:
            if not line or line[0] == "#" or line.startswith("local\t"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5:
                continue
            if lo and parts[0] < lo:
                continue
            if hi and parts[0] > hi:
                break               # sorted, so there is nothing further to find
            try:
                local = dt.datetime.strptime(parts[0], "%Y-%m-%dT%H:%M:%S")
                got = Fix(local=local, offset_minutes=int(parts[1]),
                          lat=float(parts[2]), lon=float(parts[3]), kind=parts[4])
                if len(parts) > 5 and parts[5].strip():
                    got.accuracy_m = float(parts[5])
                if len(parts) > 6:
                    got.source = parts[6]
                if len(parts) > 7:
                    got.offset_known = parts[7].strip() != "0"
                out.append(got)
            except ValueError:
                continue
    return out


def import_export(export_path: str, store_path: str, progress=None) -> StoreInfo:
    """The one-time conversion: Google's export in, the app's own store out.

    A deliberate step rather than something done quietly on every run, so a broken
    or changed export fails HERE - where the message is about importing - instead
    of halfway through placing photos, where it would look like the photos were
    at fault.
    """
    fixes = read_export(export_path, progress)
    if not fixes:
        raise ValueError(
            f"No positions found in {export_path}.\n"
            f"If this came from Google Takeout it is probably the settings-only "
            f"export - Timeline data now has to be exported from the phone instead.")
    write_store(store_path, fixes, export_path)
    return store_info(store_path)


# ----------------------------------------------------------- one timeline, two sources
#
# A phone photograph is a position with a time on it, and a library of them is a
# record of where somebody was that Google never had: the days the phone was off,
# the camera that is not a phone at all, the years before Timeline existed. It is
# also BETTER evidence than a line in a JSON file - it comes with a picture, a
# camera model and a file somebody would have to forge - which matters to
# anything downstream that has to decide whether a timeline is real.
#
# So the two are kept side by side rather than poured into one another: the
# imported Google export stays exactly as it was imported, the photographs make
# a store of their own, and anything that wants both asks for both. What gets
# EXPORTED is the two together, because that is what another program wants.

# How long a gap makes it a different journey rather than the same one. Half an
# hour: shorter and a traffic light starts a new track, longer and a morning at
# home joins onto the afternoon's drive.
TRACK_GAP_MINUTES = 30


def merge(*lots, apart_seconds: int = 0) -> list:
    """Every fix from every source, in time order, without the same one twice.

    Two sources describing one afternoon agree about most of it, and an export
    with each position in it twice is one that counts every crossing twice.
    Identical (time, place) is always a duplicate; `apart_seconds` additionally
    drops a fix that is within that many seconds of one already kept AND from a
    different source, which is the shape of "the phone wrote it and so did
    Google".
    """
    out: list[Fix] = []
    for lot in lots:
        out.extend(lot or [])
    out.sort(key=lambda f: (f.local, f.lat, f.lon))
    kept: list[Fix] = []
    seen = set()
    for f in out:
        key = (f.local, round(f.lat, 6), round(f.lon, 6))
        if key in seen:
            continue
        seen.add(key)
        if apart_seconds and kept:
            last = kept[-1]
            gap = abs((f.local - last.local).total_seconds())
            if gap <= apart_seconds and f.kind != last.kind:
                # Keep whichever says more about itself: a fix with an accuracy
                # is a measurement, one without is a note.
                if f.accuracy_m is not None and last.accuracy_m is None:
                    kept[-1] = f
                continue
        kept.append(f)
    kept.sort(key=lambda f: f.local)
    return kept


def tracks(fixes, gap_minutes: int = TRACK_GAP_MINUTES) -> list:
    """The fixes split into journeys - a run of positions with no long gap.

    A list of points says where somebody was; a line says where they WENT, and
    two lines can cross between their points. Anything working out whether two
    people's paths met wants both, which is why the export carries both.
    """
    out: list = []
    run: list = []
    for f in sorted(fixes or [], key=lambda x: x.local):
        if run and (f.local - run[-1].local).total_seconds() > gap_minutes * 60:
            out.append(run)
            run = []
        run.append(f)
    if run:
        out.append(run)
    return out


def _utc_text(f) -> str:
    return f"{f.utc:%Y-%m-%dT%H:%M:%S}Z"


def as_geojson(fixes, gap_minutes: int = TRACK_GAP_MINUTES,
               with_tracks: bool = True, name: str = "") -> dict:
    """A FeatureCollection: every fix as a point, every journey as a line.

    GeoJSON because it is what a map, QGIS and most code read, and because it
    can carry what the position MEANS - when it was, in UTC and in the local
    time that was on the clock, how accurate it claimed to be, what kind of
    record it came from, and which file it came out of. A GPX track can carry
    none of that.
    """
    feats = []
    for f in sorted(fixes or [], key=lambda x: x.local):
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(f.lon, 7),
                                                          round(f.lat, 7)]},
            "properties": {
                "time": _utc_text(f),
                "local": f"{f.local:%Y-%m-%dT%H:%M:%S}",
                "offset_minutes": f.offset_minutes,
                # false means the offset was not recorded and 0 was assumed, so
                # `time` above is the clock on the wall wearing a Z. Anything
                # comparing two people's moments has to know that.
                "offset_known": bool(f.offset_known),
                "kind": f.kind,
                "accuracy_m": f.accuracy_m,
                "source": f.source or "",
            },
        })
    if with_tracks:
        for n, run in enumerate(tracks(fixes, gap_minutes), 1):
            if len(run) < 2:
                continue
            feats.append({
                "type": "Feature",
                "geometry": {"type": "LineString",
                             "coordinates": [[round(f.lon, 7), round(f.lat, 7)]
                                             for f in run]},
                "properties": {
                    "track": n,
                    "start": _utc_text(run[0]),
                    "end": _utc_text(run[-1]),
                    "fixes": len(run),
                    "minutes": round((run[-1].local - run[0].local).total_seconds()
                                     / 60.0, 1),
                    "kinds": sorted({f.kind for f in run}),
                },
            })
    out = {"type": "FeatureCollection", "features": feats}
    if name:
        out["name"] = name
    return out


CSV_COLUMNS = ("utc", "local", "offset_minutes", "offset_known", "lat", "lon",
               "kind", "accuracy_m", "source", "track")


def as_csv_rows(fixes, gap_minutes: int = TRACK_GAP_MINUTES):
    """One row per fix, with the journey it belongs to. Yields lists.

    The same facts as the GeoJSON, flat, because something that has to read a
    million positions should not have to parse a JSON document to do it.
    """
    yield list(CSV_COLUMNS)
    n = 0
    for run in tracks(fixes, gap_minutes):
        n += 1
        for f in run:
            yield [_utc_text(f), f"{f.local:%Y-%m-%dT%H:%M:%S}",
                   f.offset_minutes, 1 if f.offset_known else 0,
                   f"{f.lat:.7f}", f"{f.lon:.7f}", f.kind,
                   "" if f.accuracy_m is None else f"{float(f.accuracy_m):.1f}",
                   f.source or "", n]


def write_csv(path: str, fixes, gap_minutes: int = TRACK_GAP_MINUTES) -> int:
    import csv
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    rows = 0
    with open(path, "w", encoding="utf-8", newline="") as fh:
        out = csv.writer(fh)
        for row in as_csv_rows(fixes, gap_minutes):
            out.writerow(row)
            rows += 1
    return max(0, rows - 1)


def write_geojson(path: str, fixes, gap_minutes: int = TRACK_GAP_MINUTES,
                  with_tracks: bool = True, name: str = "") -> int:
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    body = as_geojson(fixes, gap_minutes, with_tracks, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(body, fh)
    return len(body["features"])


def span(fixes) -> tuple:
    """(first, last) as text, for saying what a timeline covers."""
    rows = sorted(fixes or [], key=lambda f: f.local)
    if not rows:
        return "", ""
    return (f"{rows[0].local:%Y-%m-%d}", f"{rows[-1].local:%Y-%m-%d}")


def per_year(fixes) -> list:
    """How many positions in each year, newest first."""
    years: dict = {}
    for f in (fixes or []):
        key = f"{f.local:%Y}"
        years[key] = years.get(key, 0) + 1
    return sorted(years.items(), reverse=True)
