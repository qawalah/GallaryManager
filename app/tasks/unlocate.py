"""Take the location off a folder of photographs.

Geotagging trusts the camera's clock. When the clock was wrong - a trip where
the camera stayed on home time, a battery change that reset it to 2015 - every
photograph in the folder was matched to the wrong moment of your timeline, and
so to the wrong place. The pictures are fine. The pins are confidently wrong,
and a confidently wrong location is worse than none: Synology Photos puts the
beach on the map in the airport car park and nothing on screen says otherwise.

So this is the undo for Geotag, a folder at a time: find every photograph in it
that carries a location and take the location out - from inside the JPEG and
from its sidecar - so the folder can be put right (Fix the clock) and geotagged
again, or simply left without one.

**What it takes out, and what it leaves.**

- Inside a JPEG: the GPS directory is unhooked AND zeroed. Unhooked alone would
  satisfy every photo program, and the wrong coordinates would still be in the
  file for anything that goes looking. The picture is checked byte for byte
  afterwards, as with every write in this app.
- In a sidecar: every `exif:GPS...` attribute, and nothing else. The rating, the
  colour, the tags and anything Lightroom keeps there stay exactly as they were.
- Inside a RAW: nothing. This app never opens a negative for writing. A camera
  with its own GPS writes the position into the RAW itself, and that one is
  named in the plan rather than silently claimed as removed.
- Inside a HEIC: nothing either, and named the same way. Its position is read
  (`core/heif.py`), but only a JPEG is rewritten here.

Nothing here moves, renames or deletes a photograph.
"""

from __future__ import annotations

import os

from app.registry import Flag, Folder, Plan, Result, Row, Task, register
from core import sidecar as sc
from core import walk
from core.exifwrite import strip_gps
from core.photo import kind, read_gps


def _folders(opts) -> list:
    """The folders chosen, and the same shoot in the other trees if asked."""
    from core.paths import same_place
    chosen = [str(f).strip() for f in Folder("folder", "").chosen(opts.get("folder"))
              if str(f).strip()]
    keys = tuple(k for k, flag in (("raw", "with_raw"), ("previews", "with_previews"))
                 if opts.get(flag))
    return same_place(chosen, keys) if keys else chosen


def _in_sidecar(path: str) -> bool:
    return any(k.startswith("exif:GPS") for k in sc.read(path))


def plan(opts, progress=None) -> Plan:
    p = Plan(task="unlocate")
    folders = _folders(opts)
    if not folders:
        p.blocked = "Give it a folder."
        return p
    missing = [f for f in folders if not os.path.isdir(f)]
    if missing:
        p.blocked = f"There is no folder at {missing[0]!r}"
        return p

    files = []
    for folder in folders:
        got = walk.walk(folder)
        for path, why in got.errors:
            p.errors.append(f"could not read {path}: {why}")
        files.extend(got.files)

    p.columns = ["Photograph", "In the photo", "In the sidecar", "After"]
    none = raw_own = image_own = 0
    total = len(files)
    for i, path in enumerate(sorted(files), 1):
        if progress:
            progress(i, total, os.path.basename(path))
        what = kind(path)
        if what not in ("jpeg", "image", "raw"):
            continue
        inside = False
        if what == "jpeg":
            try:
                inside = read_gps(path).has_gps
            except Exception:                          # noqa: BLE001
                inside = False
        elif what == "raw":
            try:
                if read_gps(path).has_gps:
                    raw_own += 1
                    p.skipped.append((
                        path,
                        "the RAW carries its own position, written by the "
                        "camera. This app never opens a RAW file for writing, "
                        "so that one stays - only a sidecar's is taken out."))
            except Exception:                          # noqa: BLE001
                pass
        else:
            # A phone's HEIC: its position is readable now, and still only a
            # JPEG is rewritten here - so it is said, not silently left.
            try:
                if read_gps(path).has_gps:
                    image_own += 1
                    p.skipped.append((
                        path,
                        "the position is inside the file, which this app only "
                        "rewrites for a JPEG, so that one stays - only a "
                        "sidecar's is taken out."))
            except Exception:                          # noqa: BLE001
                pass
        beside = _in_sidecar(path)
        if not inside and not beside:
            none += 1
            continue
        p.rows.append(Row(
            what="unlocate", name=os.path.basename(path), source=path,
            target=path, size=0,
            detail=("location taken out of "
                    + " and ".join(x for x, y in (("the photo", inside),
                                                  ("its sidecar", beside)) if y)),
            cells=["yes - removed" if inside else "-",
                   "yes - removed" if beside else "-",
                   "no location"],
            data={"path": path, "inside": inside, "beside": beside}))

    p.stats = [
        ("Photos with a location", f"{len(p.rows):,}"),
        ("Already without one", f"{none:,}"),
        ("RAWs with their own (left)", f"{raw_own:,}"),
        ("HEICs with their own (left)", f"{image_own:,}"),
        ("Folders unreadable", f"{len(p.errors):,}"),
    ]
    p.notes.append(
        "The location only - the photo itself, the rating, the colour and the tags are "
        "not touched. Inside a JPEG the GPS block is zeroed as well as unhooked, "
        "so the wrong position is not left in the file for anything to find.")
    p.notes.append(
        "If the clock was the problem, Fix the clock next, then Geotag again - the "
        "photos will be matched to the right part of your timeline.")
    if not p.rows:
        p.notes.append("Nothing to do: none of these photos has a location.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    inside = beside = 0
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        status = "OK"
        path = row.data["path"]
        try:
            if row.data.get("inside") and kind(path) == "jpeg":
                if strip_gps(path):
                    inside += 1
                if read_gps(path).has_gps:
                    raise ValueError("the location is still there after removing it")
            if row.data.get("beside"):
                if sc.drop(path, "exif:GPS"):
                    beside += 1
                if _in_sidecar(path):
                    raise ValueError("the sidecar still has a location")
            result.done += 1
        except Exception as exc:                        # noqa: BLE001
            status = result.blame(row.name, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)
    result.stats = [("Locations removed", f"{result.done:,}"),
                    ("  from inside a JPEG", f"{inside:,}"),
                    ("  from a sidecar", f"{beside:,}"),
                    ("Failed", f"{result.failed:,}")]
    if result.done and not result.failed:
        result.details.append(
            "Every one was read back afterwards and has no location left.")
    return result


register(Task(
    name="unlocate",
    line="Take the location off a folder of photos.",
    verb="Strip the location from",
    unit="photographs",
    risk="high",
    undo="The location is removed from the file itself. Nothing here "
         "can put it back.",
    reads=("library", "raw", "previews"),
    title="Strip location",
    parent="geotag",
    tab="Strip location",
    summary="Removes the location from every photo in a folder, for when it "
            "was pinned to the wrong place.",
    icon="pin-off",
    order=24,
    options=[
        Folder("folder", "Folders to strip", setting="library", many=True,
               help="The folders whose photos lose their location. "
                    "Everything inside each one is included."),
        Flag("with_raw", "Strip their RAW files", default=True,
             group="Other trees",
             help="Also removes the location from the matching folder in the "
                  "RAW tree, in each RAW file's sidecar. Only that folder, "
                  "never the whole tree. On by default."),
        Flag("with_previews", "Strip their previews", default=True,
             group="Other trees",
             help="Also removes the location from the matching folder in the "
                  "previews tree, so the preview loses it too. On by "
                  "default."),
    ],
    plan=plan,
    apply=apply,
))
