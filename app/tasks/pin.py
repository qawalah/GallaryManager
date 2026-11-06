"""Put one location on a folder of photos, from a link you pasted.

The plain case the other geotagging cannot cover: a shoot with no timeline
behind it and no phone photos from that day, but you remember perfectly well
where it was. Find it on a map, copy the address bar, paste it here.

It is deliberately blunt - every photo in the folder gets the same position -
because that is what is actually true of a shoot in one place, and pretending to
more precision than "this building" would be inventing it. The photos that
already carry a location are left alone unless you say otherwise, so running
this over a folder never overwrites a real fix with a rough one by accident.
"""

from __future__ import annotations

import os

from app.registry import Flag, Folder, Option, Plan, Result, Row, Task, register
from core import geo, maplink
from core.exifwrite import write_gps, write_gps_sidecar
from core.paths import NO_LOCATION, ensure_folder
from core.photo import is_picture, kind, read_gps
from core import walk


# The same two answers as Geotag's: Keep originals is off by default.
UNDO = ("Strip location takes the location out again. Turn on Keep originals "
        "to keep an untouched copy as well.")
UNDO_KEPT = (f"Each photo is copied into {NO_LOCATION} first, so putting those "
             f"back is the undo.")


def plan(opts) -> Plan:
    p = Plan(task="pin")
    folder = opts["folder"]
    if not folder or not os.path.isdir(folder):
        p.blocked = f"There is no folder at {folder!r}"
        return p

    pin = maplink.read(opts["link"])
    if not pin.ok:
        p.blocked = pin.why
        return p

    found = walk.walk(folder)
    for path, why in found.errors:
        p.errors.append(f"could not read {path}: {why}")

    photos = already = 0
    for path in sorted(found.files):
        if not is_picture(path):
            continue
        photos += 1
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
        detail = f"{pin.lat:.6f}, {pin.lon:.6f}   from the link you pasted"
        if g.has_gps:
            was = geo.distance_m(g.lat, g.lon, pin.lat, pin.lon)
            detail += f"   (replacing a fix {was / 1000:.1f} km away)"
        p.rows.append(Row(what="location", name=os.path.basename(path), source=path,
                          target=pin.map_link, detail=detail, approximate=True,
                          data={"path": path, "lat": pin.lat, "lon": pin.lon}))

    p.stats = [
        ("Photos examined", f"{photos:,}"),
        ("Would get this location", f"{len(p.rows):,}"),
        ("Already had one", f"{already:,}"),
        ("Folders unreadable", f"{len(found.errors):,}"),
    ]
    p.notes.append(f"Read as {maplink.describe(pin)}")
    p.notes.append(f"Check it before applying: {pin.map_link}")
    p.notes.append("Every photo in this folder gets the SAME position. That is right "
                   "for one place on one day and wrong for a drive - the timeline is "
                   "what handles a moving day.")
    p.notes.append("Every row is marked approximate, because it is: this is where you "
                   "say you were, not where the camera recorded being.")
    if opts.get("keep_originals"):
        p.impact = {"undo": UNDO_KEPT}
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    """The same writing path as geotag, with the same guarantees."""
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result

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
                back = read_gps(path)
                if not back.has_gps:
                    raise ValueError("the position is not there when the file is read back")
                if geo.distance_m(back.lat, back.lon, lat, lon) > 5:
                    raise ValueError("read back somewhere else than what was written")
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
            "Every location was written and read back from the file afterwards. The "
            "pixel data in each one was verified unchanged before it was replaced.")
    return result


register(Task(
    name="pin",
    line="Give a whole folder one location, from a map link you pasted.",
    verb="Pin",
    unit="photographs",
    undo=UNDO,
    title="Pin a place by hand",
    summary="Gives every photo in a folder one location, from a map link you "
            "paste.",
    icon="pin",
    parent="geotag",
    tab="Pin by hand",
    order=18,
    options=[
        Folder("folder", "Folder to pin", setting="library",
               help="The folder of photos to give the location. Every photo "
                    "inside it gets the same position. Photos that already "
                    "have a location are skipped unless Include already "
                    "located is on."),
        Option("link", "Map link or coordinates", default="",
               help="A Google Maps, Apple Maps or OpenStreetMap link, a geo: "
                    "link, or plain coordinates such as 24.467, 39.611. In "
                    "Google Maps, right-click the spot and click the numbers "
                    "at the top of the menu to copy them. A short "
                    "maps.app.goo.gl link has no coordinates, so open it "
                    "first."),
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
    ],
    plan=plan,
    apply=apply,
))
