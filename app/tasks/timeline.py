"""Where you were, from both records at once - and a file you can take away.

Two things know where somebody has been, and neither knows all of it.

**The Timeline export** is dense and continuous while the phone was on and
recording, and it is blank where it was not: the days it was off, the trip
before Timeline existed, every photograph taken with a camera that is not a
phone.

**The photographs themselves** are the other half. A phone photo carries a
position, a satellite time and the clock's local time - which is a fix, with the
timezone attached, from a completely independent source. A library is years of
them.

This puts the two together, and that is all it does: nothing is written into a
photograph here, and nothing already imported is altered.

**The two stores stay side by side.** The imported Google timeline is left
exactly as the import left it; the photographs make a store of their own; and
Geotag reads them in the order you choose, never pooled. One merged file would
have meant re-importing to undo a mistake, and "where did this position come
from" would have had no answer.

**What is exported is both together**, because that is what another program
wants. GeoJSON carries everything a fix knows - the moment in UTC, the local
clock and its offset, how accurate it claimed to be, what kind of record it came
from, and which file it came out of - as points, plus a line per journey, since
two paths cross between their points rather than at them. CSV is the same facts
flat, for something that has to read a million of them without parsing a
document.
"""

from __future__ import annotations

import datetime as dt
import os

from app.registry import (Flag, Folder, Folders, Number, Option, Plan, Result,
                          Row, Task, register)
from core import geo, timeline, walk
from core.store import store_path

GOOGLE = "timeline.tsv"          # what `import-timeline` wrote
PHOTOS = "timeline-photos.tsv"   # what this builds, kept beside it


def _day(text: str):
    text = str(text or "").strip()
    if not text:
        return None
    for shape in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%Y-%m", "%Y"):
        try:
            return dt.datetime.strptime(text, shape)
        except ValueError:
            continue
    return None


def _located(folders, progress=None) -> list:
    """The photographs that carry a position, asked of the index first.

    The index already knows which files have a location, so the slow part - -
    opening a file to read its GPS, its satellite time and its clock - happens
    only for those. On a library of eighty thousand where four thousand are
    phone photos, that is the difference between a minute and an hour.
    """
    from core import catalogue as _cat
    cat = _cat.shared()
    want = [os.path.normcase(os.path.abspath(str(f))) for f in folders if f]
    out = []
    indexed = False
    for _key, path in cat.rows():
        e = cat.entry(path)
        if e is None or e[12] is None:
            continue
        indexed = True
        low = os.path.normcase(os.path.abspath(path))
        if want and not any(low == w or low.startswith(w + os.sep) for w in want):
            continue
        out.append(path)
    if indexed:
        return out
    # No index yet (a fresh install, or it is still building): walk instead, and
    # let `fixes_from_photos` decide which of them carry anything.
    files = []
    for one in folders:
        if one and os.path.isdir(one):
            files.extend(walk.walk(one).files)
    return files


def _gathered(opts, progress=None):
    """(photo fixes, imported fixes, notes) - each from its own source."""
    notes = []
    want_photos = bool(opts.get("use_photos", True))
    want_google = bool(opts.get("use_timeline", True))
    since = _day(opts.get("since"))
    until = _day(opts.get("until"))

    photos: list = []
    if want_photos:
        folders = Folders.chosen(opts.get("folders"))
        paths = _located(folders)
        photos = geo.fixes_from_photos(paths, progress=progress)
        if since or until:
            photos = [f for f in photos
                      if (not since or f.local >= since)
                      and (not until or f.local <= until)]
        notes.append(f"{len(photos):,} position(s) read out of your photos"
                     + (f" in {len(folders)} folder(s)." if folders else "."))
        if paths and not photos:
            notes.append("None of those photos carries a position that could "
                         "be read - which is what Geotag is for.")

    google: list = []
    if want_google:
        store = store_path(GOOGLE)
        info = timeline.store_info(store)
        if info.ok and info.count:
            google = timeline.read_store(store, since, until)
            notes.append(f"{len(google):,} position(s) from the imported Timeline "
                         f"({info.count:,} on file, imported {info.imported}).")
        else:
            notes.append("No Timeline has been imported - 'Import timeline' reads "
                         "the export off your phone. This still works without one; "
                         "it is then your photos alone.")
    return photos, google, notes


def plan(opts, progress=None) -> Plan:
    p = Plan(task="timeline", opts=dict(opts))
    photos, google, notes = _gathered(opts, progress)
    p.notes.extend(notes)

    gap = int(opts.get("gap") or timeline.TRACK_GAP_MINUTES)
    apart = int(opts.get("apart") or 0) if opts.get("dedupe", True) else 0
    both = timeline.merge(photos, google, apart_seconds=apart)
    if not both:
        p.blocked = ("Nothing to combine: no photos with a position, and no "
                     "imported Timeline.")
        return p

    runs = timeline.tracks(both, gap)
    first, last = timeline.span(both)
    p.columns = ["What", "How many", "Covering"]
    p.data["counts"] = {"photos": len(photos), "google": len(google),
                        "both": len(both)}

    out = str(opts.get("out") or "").strip()
    stem = "".join(c for c in str(opts.get("name") or "location-timeline")
                   if c.isalnum() or c in "-_ ").strip() or "location-timeline"
    files = []
    if out:
        if bool(opts.get("as_geojson", True)):
            files.append((os.path.join(out, stem + ".geojson"), "GeoJSON",
                          f"{len(both):,} points and {len(runs):,} journey(s), "
                          f"each carrying its time, offset, accuracy and source"))
        if bool(opts.get("as_csv", True)):
            files.append((os.path.join(out, stem + ".csv"), "CSV",
                          f"{len(both):,} rows - the same facts, flat"))
    keeping = bool(opts.get("keep_store", True)) and photos

    for path, what, why in files:
        p.rows.append(Row(what="write", name=os.path.basename(path), source=path,
                          cells=[what, f"{len(both):,} position(s)",
                                 f"{first} to {last}"],
                          detail=why, data={"format": what.lower(), "path": path}))
    if keeping:
        p.rows.append(Row(
            what="store", name=PHOTOS, source=store_path(PHOTOS),
            cells=["The photo timeline", f"{len(photos):,} position(s)",
                   " to ".join(x for x in timeline.span(photos) if x)],
            detail="Kept beside the imported one, not merged into it - Geotag "
                   "can then use both, in the order you choose.",
            data={"format": "store"}))

    p.stats = [
        ("From your photos", f"{len(photos):,}"),
        ("From the imported Timeline", f"{len(google):,}"),
        ("Together, without repeats", f"{len(both):,}"),
        ("Journeys", f"{len(runs):,}"),
        ("Covering", f"{first} to {last}" if first else "-"),
    ]
    years = timeline.per_year(both)
    if years:
        p.stats.append(("Busiest year",
                        f"{years and max(years, key=lambda kv: kv[1])[0]} "
                        f"({max(y[1] for y in years):,})"))
    vague = [f for f in both if not getattr(f, "offset_known", True)]
    if vague:
        p.stats.append(("With no timezone in them", f"{len(vague):,}"))
        p.notes.append(
            f"{len(vague):,} position(s) came off a camera that recorded no "
            f"satellite time, so the timezone is not in the file and zero was "
            f"assumed. Their local time is exact and their UTC moment is a "
            f"guess - the export says which is which (`offset_known`), because "
            f"a moment that is twelve hours out is a meeting that never "
            f"happened.")
    overlap = len(photos) + len(google) - len(both)
    if overlap > 0:
        p.stats.append(("Repeats dropped", f"{overlap:,}"))
        p.notes.append(f"{overlap:,} position(s) were in both records - the same "
                       f"moment in the same place - and are in the export once. "
                       f"Anything counting crossings would otherwise count them "
                       f"twice.")
    if not out:
        p.notes.append("No folder to export into, so nothing will be written "
                       "except the photo timeline itself. Give a folder to get "
                       "the files.")
    p.notes.append("Nothing is written into a photo here, and the imported "
                   "Timeline is not altered. What this writes is a store of its "
                   "own and the export files.")
    p.notes.append("A journey is a run of positions with no gap longer than "
                   f"{gap} minutes. The export carries the points AND a line per "
                   f"journey, because two paths cross between their points "
                   f"rather than at them.")
    p.impact = {"verb": "Write", "unit": "files", "count": len(p.rows),
                "undo": "Nothing is overwritten except these files and the photo "
                        "timeline, which is rebuilt from your photos any "
                        "time this runs."}
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    opts = plan.opts or {}
    photos, google, _notes = _gathered(opts, progress)
    gap = int(opts.get("gap") or timeline.TRACK_GAP_MINUTES)
    apart = int(opts.get("apart") or 0) if opts.get("dedupe", True) else 0
    both = timeline.merge(photos, google, apart_seconds=apart)

    wrote = []
    if bool(opts.get("keep_store", True)) and photos:
        try:
            timeline.write_store(store_path(PHOTOS), photos,
                                 source="your photos")
            wrote.append((store_path(PHOTOS), len(photos)))
            result.done += 1
        except OSError as exc:
            result.blame(store_path(PHOTOS), exc)

    for row in plan.rows:
        if cancelled and cancelled():
            result.cancelled = True
            break
        kind = str(row.data.get("format") or "")
        path = str(row.data.get("path") or "")
        if not path or kind == "store":
            continue
        try:
            if kind == "geojson":
                n = timeline.write_geojson(path, both, gap, True,
                                           os.path.basename(path))
            else:
                n = timeline.write_csv(path, both, gap)
            wrote.append((path, n))
            result.done += 1
        except OSError as exc:
            result.blame(path, exc)

    result.stats = [("Positions combined", f"{len(both):,}"),
                    ("Files written", f"{len(wrote):,}")]
    for path, n in wrote:
        result.details.append(f"{path} - {n:,} record(s)")
    if wrote:
        result.details.append(
            "GeoJSON carries every fact a position has; the CSV carries the same "
            "facts flat. Both say which record each position came from, which is "
            "what lets something downstream tell a phone's own photo from a "
            "line in an export.")
    return result


register(Task(
    name="timeline",
    fold_groups=True,
    verb="Write",
    unit="files",
    line="Combine your photos' positions with the imported Timeline, and "
         "export both.",
    title="Location timeline",
    parent="geotag",
    icon="timeline",
    # Beside Import timeline, not five tabs away from it. Importing an export
    # and combining it with your photographs are two halves of one thought, and
    # the second half sat after Strip location.
    order=16,
    summary="Builds one record of where you have been from your photos and "
            "the Google Timeline, and exports it.",
    options=[
        Folders("folders", "Folders to read", setting="library",
                group="Sources",
                help="The folders of photos to read positions from: a phone "
                     "dump, the library or both. Only photos the index says "
                     "have a position are opened. Blank means the library "
                     "from Setup."),
        Flag("use_photos", "Use your photos", default=True,
             group="Sources",
             help="Takes positions from your photos. Each one gives a "
                  "position, the GPS time and the camera's own clock with "
                  "its time zone. On by default."),
        Flag("use_timeline", "Use the imported Timeline", default=True,
             group="Sources",
             help="Takes positions from the Timeline brought in by Import "
                  "Google Timeline. It is read, never changed. On by "
                  "default."),
        Folder("out", "Export folder", default="", must_exist=False,
               group="Export files",
               help="The folder the export files are written into. Blank "
                    "builds the photo timeline and writes no files."),
        Option("name", "File name", default="location-timeline", kind="text",
               group="Export files",
               help="The name of the export files, without an extension. "
                    "Default location-timeline. One file is written per "
                    "format chosen below."),
        Flag("as_geojson", "GeoJSON", default=True, group="Export files",
             help="Writes a GeoJSON file: every position with everything "
                  "known about it, plus one line per journey. Maps, QGIS and "
                  "most code read it. On by default."),
        Flag("as_csv", "CSV", default=True, group="Export files",
             help="Writes a CSV file with one row per position and the same "
                  "facts, for a spreadsheet or a script. On by default."),
        Flag("keep_store", "Keep the photo timeline", default=True,
             group="Export files",
             help="Saves the timeline built from your photos in the app's "
                  "store, beside the imported Google Timeline and not merged "
                  "into it. Geotag can then use both, and a mistake needs no "
                  "re-import. On by default."),
        Number("gap", "New journey after (minutes)", default=30, minimum=1,
               maximum=1440, group="Journeys",
               help="A pause longer than this many minutes ends one journey "
                    "and starts the next. 1 to 1440, default 30. Too short, "
                    "and a traffic light splits a drive. Too long, and a "
                    "morning at home joins the afternoon."),
        Flag("dedupe", "Drop repeats", default=True, group="Journeys",
             help="Keeps only one record when both sources recorded the same "
                  "moment in the same place. Off, such repeats are kept and "
                  "counted twice. On by default."),
        Number("apart", "Repeats are within (seconds)", default=30, minimum=0,
               maximum=600, advanced=True, group="Journeys",
               help="Two records closer in time than this many seconds count "
                    "as the same moment. 0 to 600, default 30. Only used "
                    "when Drop repeats is on."),
        Option("since", "From date", default="", kind="text", advanced=True,
               group="Journeys", help="The earliest date to include, for "
                                      "example 2019-01-01. Blank means from "
                                      "the first record."),
        Option("until", "To date", default="", kind="text", advanced=True,
               group="Journeys",
               help="The latest date to include, for example 2024-12-31. "
                    "Blank means to the last record."),
    ],
    plan=plan,
    apply=apply,
    writes=True,
    reads=("library",),
    undo="Nothing is written into a photo. The files it writes can be "
         "deleted, and the photo timeline is rebuilt from your photos "
         "whenever this runs.",
))
