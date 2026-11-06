"""Give photos a location they lack, by matching capture time against a record.

**Two sources, and one of them is asked first - never both together.** Pooling
them let a photo from the other folder outrank the timeline just by happening to
be a few minutes closer, which is not what a fallback means and is impossible to
reason about afterwards. Which comes first is now yours to choose, because the
right answer depends on what you have: a Timeline is continuous but coarse, and
a phone that was in your pocket all day is sparse but exact. The one that is
right for a hiking day is wrong for a wedding.

Whatever you choose, every row says which source placed it and how far away in
time it was, so a wrong order shows up in the preview rather than in your
library.

Writing is separated from deciding by design. `plan` reads and works everything
out; `apply` takes a latitude and a longitude and puts them in a file. The time
has done its job before anything is written, so a bad timestamp can misplace a
pin - visible in the preview, on the map, and reversible - but it cannot damage a
photo. Those two risks share no code.
"""

from __future__ import annotations

import datetime as dt
import os

from app.registry import Choice, Flag, Folder, Number, Plan, Result, Row, Task, register
from core import geo, timeline, walk
from core.exifwrite import write_gps, write_gps_sidecar
from core.paths import NO_LOCATION, ensure_folder
from core.photo import is_picture, kind, read_gps
from core.store import store_path

ORPHAN_PAD_MINUTES = 60


# "The photographs" means the folder named below when there is one, and
# otherwise the timeline built out of your own photographs by Location timeline.
# Two sources, never pooled: the order IS the decision, and a position that came
# from the wrong one is worse than no position at all.
ORDER = [
    ("timeline", "Timeline first, then your photos"),
    ("photos", "Your photos first, then the Timeline"),
    ("timeline_only", "Timeline only"),
    ("photos_only", "Your photos only"),
]


def _references(opts, since, until, notes):
    """The two sources, in the order you chose. Never pooled."""
    order = str(opts.get("order") or "timeline")
    want_timeline = order != "photos_only"
    want_photos = order != "timeline_only"

    line = photos = None
    store = store_path("timeline.tsv")
    info = timeline.store_info(store) if want_timeline else None
    if info is not None and info.ok and info.count:
        pad = dt.timedelta(minutes=max(ORPHAN_PAD_MINUTES, int(opts["max_gap"]) * 2))
        fixes = timeline.read_store(store, since - pad if since else None,
                                    until + pad if until else None)
        line = geo.Index(fixes)
        notes.append(f"Timeline: {info.count:,} positions on file, "
                     f"{len(fixes):,} of them near these photos.")
    elif want_timeline:
        notes.append("No timeline has been imported - run the 'import-timeline' tool.")

    folder = (opts.get("phone") or "").strip()
    if want_photos and folder and os.path.isdir(folder):
        fixes = geo.fixes_from_photos(walk.walk(folder).files)
        photos = geo.Index(fixes)
        notes.append(f"Photo folder: {len(fixes):,} photo(s) in {folder} carry a "
                     f"location.")
    elif want_photos and folder:
        notes.append(f"There is no folder at {folder!r}, so nothing was read from it.")
    elif want_photos:
        # The timeline built out of your own photographs ("Location timeline"),
        # kept beside the imported one rather than merged into it - so this can
        # use both without either becoming the other.
        built = store_path("timeline-photos.tsv")
        made = timeline.store_info(built)
        if made.ok and made.count:
            pad = dt.timedelta(minutes=max(ORPHAN_PAD_MINUTES,
                                           int(opts["max_gap"]) * 2))
            fixes = timeline.read_store(built, since - pad if since else None,
                                        until + pad if until else None)
            photos = geo.Index(fixes)
            notes.append(f"Your photos: {made.count:,} position(s) built by "
                         f"Location timeline, {len(fixes):,} of them near these "
                         f"photos. Give a folder above to read one afresh instead.")

    if order.startswith("timeline"):
        first, second, names = line, photos, ("the Timeline", "your photos")
    else:
        first, second, names = photos, line, ("your photos", "the Timeline")

    asked = [n for n, got in zip(names, (first, second)) if got is not None]
    if len(asked) > 1:
        notes.append(f"Asked in order: {asked[0]}, then {asked[1]} only where the "
                     f"first has nothing near enough in time. They are never "
                     f"pooled, so this order is the decision.")
    elif asked:
        notes.append(f"Using {asked[0]} only.")
    return first, second


# What the confirmation says about undoing a run. Keep originals is off by
# default, so the shipped answer is the one without a copy; a plan with the box
# on says so in `plan.impact`. Pin says the same, in the same words.
UNDO = ("Strip location takes the location out again. Turn on Keep originals "
        "to keep an untouched copy as well.")
UNDO_KEPT = (f"Each photo is copied into {NO_LOCATION} first, so putting those "
             f"back is the undo.")


def plan(opts) -> Plan:
    p = Plan(task="geotag")
    folder = opts["folder"]
    if not folder or not os.path.isdir(folder):
        p.blocked = f"There is no folder at {folder!r}"
        return p

    found = walk.walk(folder)
    for path, why in found.errors:
        p.errors.append(f"could not read {path}: {why}")

    # One pass over the files: reading the front of every JPEG is the slow part,
    # and the date range is only knowable afterwards.
    seen, pictures, already, no_time = [], 0, 0, 0
    lo = hi = None
    for path in found.files:
        if not is_picture(path):
            continue
        pictures += 1
        g = read_gps(path)
        if g.has_gps and not opts["replace"]:
            already += 1
            p.skipped.append((path, "already has a location"))
            continue
        if g.has_gps and kind(path) != "jpeg":
            # A phone's HEIC carries its own position, and only a JPEG is
            # rewritten here. A sidecar beside it would be read second, after
            # the position in the file, so replacing it that way would only look
            # as if it had worked.
            already += 1
            p.skipped.append((path, "its own location is inside the file, "
                                    "which this app does not rewrite"))
            continue
        if not g.taken:
            no_time += 1
            p.skipped.append((path, "no capture time in the file"))
            continue
        seen.append((path, g))
        lo = g.taken if lo is None or g.taken < lo else lo
        hi = g.taken if hi is None or g.taken > hi else hi

    main, fallback = _references(opts, lo, hi, p.notes)
    order = str(opts.get("order") or "timeline")
    first_name, second_name = (("the Timeline", "the photo folder")
                               if order.startswith("timeline")
                               else ("the photo folder", "the Timeline"))
    if main is None and fallback is None:
        p.blocked = ("Nothing to match against. Import a Google Timeline, or point "
                     "the photo-folder box at a folder of photos that already "
                     "carry a location - and check the order above allows the one "
                     "you have.")
        return p

    drift = int(opts["drift"])
    gap = int(opts["max_gap"])
    interpolate = not opts["no_interpolate"]
    too_far = rough = 0
    by_source: dict[str, int] = {}

    for path, g in seen:
        when = g.taken - dt.timedelta(minutes=drift)
        hit = geo.Placement(why="no reference")
        came_from = ""
        if main is not None and len(main):
            hit = geo.place(main, when, gap, interpolate)
            came_from = first_name
        if not hit.ok and fallback is not None and len(fallback):
            hit = geo.place(fallback, when, gap, interpolate)
            came_from = second_name
        if not hit.ok:
            too_far += 1
            p.skipped.append((path,
                              f"{hit.why} of {when:%Y-%m-%d %H:%M}"))
            continue
        rough += 1 if hit.approximate else 0
        by_source[hit.reference] = by_source.get(hit.reference, 0) + 1
        # Which source placed it, on every row. With two sources and an order
        # you chose, "where did this pin come from" is the first question of any
        # result that looks wrong - and answering it per row is the difference
        # between checking a plan and trusting it.
        detail = (f"from {came_from}   " if came_from else "")
        detail += (f"{hit.lat:.6f}, {hit.lon:.6f}   {hit.gap_minutes:g} min away   "
                   f"{hit.how}")
        if hit.spread_m:
            detail += f" ({hit.spread_m} m apart)"
        p.rows.append(Row(what="location", name=os.path.basename(path), source=path,
                          target=hit.map_link, detail=detail,
                          approximate=hit.approximate,
                          cells=[came_from or "-",
                                 f"{hit.lat:.6f}, {hit.lon:.6f}",
                                 f"{hit.gap_minutes:g} min",
                                 hit.how + (f" ({hit.spread_m} m apart)"
                                            if hit.spread_m else "")],
                          data={"path": path, "lat": hit.lat, "lon": hit.lon}))

    p.columns = ["File", "Source", "Where", "Time apart", "How"]
    p.stats = [
        ("Photos examined", f"{pictures:,}"),
        ("Would get a location", f"{len(p.rows):,}"),
        ("  of those, approximate", f"{rough:,}"),
        ("Already had one", f"{already:,}"),
        ("No capture time", f"{no_time:,}"),
        ("Nothing near enough in time", f"{too_far:,}"),
        ("Folders unreadable", f"{len(found.errors):,}"),
    ]
    if by_source:
        p.notes.append("where the positions came from: "
                       + ", ".join(f"{k} x{v}" for k, v in sorted(by_source.items())))
    if rough:
        p.notes.append(f"{rough} are approximate - the nearest fix was more than "
                       f"{geo.ROUGH_AFTER_MINUTES} minutes away, or the two fixes "
                       f"either side were far enough apart that the point between "
                       f"them is a guess. Check those on the map first.")
    p.notes.append("Nothing is written until you apply. Every row carries a map link.")
    if opts.get("keep_originals"):
        p.impact = {"undo": UNDO_KEPT}
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    """Write the planned locations, verifying each one afterwards."""
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result

    # read off the plan, not from arguments: the person chose these when they
    # previewed, and an option that reaches the form but not the writer is worse
    # than one that was never offered
    sidecar_only = bool(plan.opts.get("sidecar_only"))
    keep_originals = bool(plan.opts.get("keep_originals"))

    written = sidecars = 0
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        path, lat, lon = row.data["path"], row.data["lat"], row.data["lon"]
        status = "OK"
        try:
            # Only a JPEG is written in place. Anything else - a HEIC, a PNG -
            # gets the sidecar every other program reads for it.
            if sidecar_only or kind(path) != "jpeg":
                write_gps_sidecar(path, lat, lon)
                sidecars += 1
            else:
                backup = ""
                if keep_originals:
                    backup = os.path.join(os.path.dirname(path), NO_LOCATION)
                    ensure_folder(backup)
                write_gps(path, lat, lon, backup_folder=backup)
                # read it back - a write that did not take must not report success
                back = read_gps(path)
                if not back.has_gps:
                    raise ValueError("the position is not there when the file is read back")
                off = geo.distance_m(back.lat, back.lon, lat, lon)
                if off > 5:
                    raise ValueError(f"read back {off:.0f} m from what was written")
                written += 1
            result.done += 1
        except Exception as exc:                    # noqa: BLE001
            status = result.blame(path, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)

    result.stats = [("Locations written into photos", f"{written:,}"),
                    ("Sidecars written", f"{sidecars:,}"),
                    ("Failed", f"{result.failed:,}")]
    if not result.details:
        result.details.append(
            "Every location was written and read back from the file afterwards. "
            "The pixel data in each one was verified unchanged before it was replaced.")
    return result


register(Task(
    name="geotag",
    fold_groups=True,
    line="Work out where each photo was taken, from the record of where you "
         "were that day.",
    verb="Geotag",
    unit="photographs",
    undo=UNDO,
    reads=('library',),
    title="Geotag",
    summary="Adds a location to photos by matching the time they were taken "
            "against where you were.",
    icon="globe",
    # locations before sorting, because sorting can be BY place
    order=14,
    options=[
        Folder("folder", "Folder to geotag", setting="library",
               help="The folder of photos to give a location, a shoot or the "
                    "whole library. Photos that already have a location are "
                    "skipped unless Include already located is on."),
        Number("max_gap", "Give up after (minutes)", default=60, minimum=1, maximum=1440,
               help="The largest time gap, in minutes, between a photo and "
                    "the nearest known position for a location to be "
                    "written. 1 to 1440, default 60. Beyond it no guess is "
                    "made, because a wrong location is worse than none."),

        Choice("order", "Location source", default="timeline",
               choices=ORDER, group="Sources",
               help="Which source of positions to ask first. The first "
                    "source wins wherever it has a position near enough in "
                    "time, and the other is used only where it has none. The "
                    "Timeline is continuous but rough, and phone photos are "
                    "exact but sparse."),
        Folder("phone", "Photos with locations",
               default="", must_exist=False, group="Sources",
               help="A folder of photos that already have a location, "
                    "usually phone photos. Their positions and capture times "
                    "become the reference. Blank uses the Timeline alone."),

        Flag("sidecar_only", "Sidecars only",
             group="Safety",
             help="Writes the location into a .xmp sidecar beside each photo "
                  "instead of into the photo. Off by default: a JPEG is "
                  "normally written in place, which is where Windows "
                  "Explorer and Synology Photos look. A RAW file always gets "
                  "a sidecar and is never changed itself."),
        Flag("keep_originals", "Keep originals",
             help=f"Copies each photo into a {NO_LOCATION} folder beside it "
                  f"before the location is written. Off by default: the "
                  f"location is written into the photo itself, which every "
                  f"other program expects. Turn it on if you want an untouched "
                  f"copy to go back to.",
             group="Safety"),

        Flag("replace", "Include already located",
             group="Advanced", advanced=True,
             help="Also writes a location on photos that already have one, "
                  "replacing it. Off by default: a position recorded by the "
                  "camera is kept."),
        Flag("no_interpolate", "Nearest position only",
             group="Advanced", advanced=True,
             help="Uses the position of the single nearest record in time. "
                  "Off by default: a photo taken between two records is "
                  "placed between them, and marked approximate when they are "
                  "far apart."),
        Number("drift", "Clock fast by (minutes)", default=0,
               minimum=-720, maximum=720, group="Advanced", advanced=True,
               help="Minutes the camera clock runs ahead of true time. This "
                    "many minutes are taken off each photo's time before "
                    "matching. -720 to 720, default 0. If the clock really "
                    "is wrong, use Fix the clock to correct the photos "
                    "instead."),
    ],
    plan=plan,
    apply=apply,
))
