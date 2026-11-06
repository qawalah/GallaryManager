"""Find the blurry ones - and tag them, or put them aside with their RAWs.

**How sharpness is measured.** The standard measure: how much the picture
changes from one pixel to the next (the variance of a Laplacian filter). A sharp
edge is a big change; a blurred one is a gentle slope; a frame with nothing
sharp in it scores low everywhere.

**"Anywhere", not "on average", and that is most of the judgement.** A portrait
at f/1.7 is an eye in focus and a whole frame of deliberate softness - averaged
over the picture it looks blurred, and it is the best frame of the shoot. So
the frame is cut into a grid and scored by its SHARPEST cell: a photograph is
blurry when nothing in it is sharp, not when most of it is soft.

**Against its own shoot, as well as against a number.** A night street at ISO
6400 is softer than a beach at noon in every frame, and a single threshold
would flag the whole night. So a frame is also compared with the other frames
of its own folder: flagged when it is far below what that shoot usually
manages. Either test is enough, and the plan says which one caught it and shows
the score, so the first run is also how you calibrate.

**What it does about them is yours to choose.** A tag - `blurry` - that
Lightroom and Synology Photos can search, and nothing moves. Or put aside: the
JPEG, its RAW, their sidecars and its preview move into `_Culled`, exactly as a
cull by rating does, and putting them back is a move. Nothing is ever deleted
here; Clean up is the only place that does that, and it asks twice.

Closed eyes are not detected. Finding a face and then an eye inside it, without
a trained model, is guesswork that fails on sunglasses, profiles and anyone
laughing - and a guess that puts the best frame of a wedding aside is worse than
no feature.
"""

from __future__ import annotations

import os
import statistics

from app.registry import Choice, Flag, Folder, Number, Option, Plan, Result, Row, Task, register
from core import moves
from core import facts, tagwrite, walk
from core.exifwrite import sidecar_path
from core.pairs import build_index, find_partner
from core.paths import CULLED, preview_for, under
from core.photo import kind

GRID = 4
SIDE = 768               # the longest side it is scored at - enough for edges

DO = [
    ("tag", "Tag them (nothing moves)"),
    ("aside", "Move them to _Culled with their RAWs"),
]


def sharpness(path: str) -> float | None:
    """How sharp the sharpest part of this photograph is. None if unreadable.

    `draft` asks the JPEG decoder for a reduced image directly - an eighth of
    the size costs an eighth of the work - which is the difference between a
    library that takes an evening and one that takes a coffee.
    """
    try:
        from PIL import Image, ImageFilter, ImageStat
    except ImportError:
        return None
    try:
        with Image.open(path) as im:
            im.draft("L", (SIDE, SIDE))
            g = im.convert("L")
            g.thumbnail((SIDE, SIDE))
    except Exception:                                  # noqa: BLE001
        return None
    edges = g.filter(ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0],
                                        scale=1, offset=128))
    w, h = edges.size
    if w < GRID * 8 or h < GRID * 8:
        return float(ImageStat.Stat(edges).var[0])
    best = 0.0
    for gx in range(GRID):
        for gy in range(GRID):
            box = (gx * w // GRID, gy * h // GRID,
                   (gx + 1) * w // GRID, (gy + 1) * h // GRID)
            v = ImageStat.Stat(edges.crop(box)).var[0]
            best = max(best, v)
    return round(best, 1)


def _aside(path: str, root: str) -> str:
    from app.tasks.cull import _aside as cull_aside
    return cull_aside(path, root)


def plan(opts, progress=None) -> Plan:
    p = Plan(task="blur")
    scan = str(opts.get("folder") or "").strip()
    if not scan:
        p.blocked = "Pick a folder to check."
        return p
    if not os.path.isdir(scan):
        p.blocked = f"There is no folder at {scan}"
        return p
    try:
        import PIL  # noqa: F401
    except ImportError:
        p.blocked = "Pillow is not installed, and sharpness cannot be measured without it."
        return p

    below = float(opts.get("below") or 0)
    ratio = float(opts.get("of_shoot") or 0) / 100.0
    action = str(opts.get("do") or "tag")
    word = str(opts.get("word") or "blurry").strip() or "blurry"

    found = walk.walk(scan)
    for path, why in found.errors:
        p.errors.append(f"could not read {path}: {why}")
    photos = [f for f in sorted(found.files) if kind(f) == "jpeg"]

    reader = facts.reader()
    scores: dict = {}
    for i, path in enumerate(photos, 1):
        if progress:
            progress(i, len(photos), os.path.basename(path))
        # Kept with the rest of what is known about the file, so a second look
        # at the same shoot costs nothing - measuring is the slow part here.
        s = reader._field(path, "sharp", sharpness)
        if s is not None:
            scores[path] = float(s)
    reader.save()

    by_folder: dict = {}
    for path, s in scores.items():
        by_folder.setdefault(os.path.dirname(path), []).append(s)
    typical = {k: statistics.median(v) for k, v in by_folder.items() if len(v) >= 5}

    # Put aside at the same position in each tree - measured from the LIBRARY,
    # not from the folder checked, or a shoot's _Culled would be built inside
    # the shoot rather than at the top of the tree where the cull puts it.
    from core import settings as _S
    home = str(_S.load()["library"] or "").strip()
    library = home if home and under(scan, home) else scan
    raw_root = str(opts.get("raw") or "").strip()
    prev_root = str(opts.get("previews") or "").strip()
    raw_index = None
    if action == "aside" and raw_root and os.path.isdir(raw_root):
        got = walk.walk(raw_root)
        raw_index = build_index(got.files, want=("raw",), reader=reader)

    p.columns = ["File", "Score", "Its shoot", "Caught by", "What to do"]
    flagged = 0
    tagged_already = 0
    shots = 0
    for path, s in sorted(scores.items(), key=lambda kv: kv[1]):
        shoot = typical.get(os.path.dirname(path))
        by_number = below > 0 and s < below
        by_shoot = bool(shoot) and ratio > 0 and s < shoot * ratio
        if not by_number and not by_shoot:
            continue
        flagged += 1
        caught = " and ".join(x for x, y in (
            (f"under {below:g}", by_number),
            (f"under {int(ratio * 100)}% of its shoot", by_shoot)) if y)
        typical_txt = f"{shoot:,.0f}" if shoot else "too few to say"
        if action == "tag":
            have = {t.lower() for t in reader.tags(path)}
            if word.lower() in have:
                tagged_already += 1
                continue
            p.rows.append(Row(
                what="tag", name=os.path.basename(path), source=path,
                target=path, detail=f"sharpness {s:,.0f} - {caught}",
                cells=[f"{s:,.0f}", typical_txt, caught, f"tag '{word}'"],
                data={"action": "tag", "path": path, "word": word}))
            continue
        batch = [("JPEG", path, library), ("sidecar", sidecar_path(path), library)]
        if prev_root:
            prev = preview_for(path, library, prev_root)
            batch += [("preview", prev, prev_root),
                      ("sidecar", sidecar_path(prev), prev_root)]
        if raw_index is not None:
            m = find_partner(path, reader.capture(path), raw_index)
            if m.jpeg:
                batch += [("RAW", m.jpeg, raw_root),
                          ("sidecar", sidecar_path(m.jpeg), raw_root)]
        before = len(p.rows)
        for what, target, root in batch:
            if not target or not os.path.isfile(target) or not under(target, root):
                continue
            size = os.path.getsize(target)
            p.rows.append(Row(
                what=what, name=os.path.basename(target), source=target,
                target=_aside(target, root), size=size,
                detail=f"sharpness {s:,.0f} - {caught}",
                cells=[f"{s:,.0f}", typical_txt, caught, f"{what} to {CULLED}"],
                data={"action": "aside", "from": target,
                      "to": _aside(target, root)}))
        shots += len(p.rows) > before

    # The button counts photographs. Putting one aside is several rows (its
    # sidecar, preview and RAW travel with it); tagging moves nothing at all,
    # so it must not claim a destination either.
    if action == "tag":
        p.impact = {"verb": "Tag", "count": len(p.rows), "into": []}
    else:
        p.impact = {"count": shots}

    p.stats = [
        ("Photos measured", f"{len(scores):,}"),
        ("Look blurry", f"{flagged:,}"),
        ("Already tagged", f"{tagged_already:,}") if action == "tag"
        else ("Files to move aside", f"{len(p.rows):,}"),
        ("Files opened", reader.said()),
    ]
    if scores:
        p.stats.insert(1, ("Sharpness, middle of the range",
                           f"{statistics.median(scores.values()):,.0f}"))
    p.notes.append(
        "Scored by the SHARPEST part of each frame, so a portrait with one eye in "
        "focus is not called blurry for its soft background. The scores are shown "
        "- the first run is also how you find the right number for your cameras.")
    p.notes.append(
        "Nothing is deleted. A tag moves nothing; putting aside moves the whole "
        "shot into _Culled at the same position, so putting it back is a move.")
    if not scores and photos:
        p.notes.append("None of these could be measured.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    import shutil
    from core.paths import ensure_folder, roots_of, safe_target, tidy_empty_folders
    in_file = bool((plan.opts or {}).get("in_file", True))
    touched = set()
    freed = 0
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        status = "OK"
        try:
            if row.data["action"] == "tag":
                got = tagwrite.add(row.data["path"], [row.data["word"]],
                                   in_file=in_file, in_sidecar=True)
                if not (got["sidecar"] or got["xmp"] or got["windows"]):
                    raise RuntimeError("; ".join(got["errors"]) or "nothing written")
            else:
                src = row.data["from"]
                if not os.path.exists(src):
                    raise FileNotFoundError("it is no longer there")
                dst = moves.shift(result, src, row.data["to"])
                touched.add(os.path.dirname(src))
                freed += row.size
            result.done += 1
        except Exception as exc:                        # noqa: BLE001
            status = result.blame(row.name, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)
    tidy_empty_folders(touched, stop_at=roots_of(plan.opts))
    result.reclaimed, result.reclaim_kind = freed, "aside"
    result.stats = [("Done", f"{result.done:,}"),
                    ("Moved out of the library", f"{freed / 1e6:,.0f} MB"),
                    ("Failed", f"{result.failed:,}")]
    return result


register(Task(
    name="blur",
    fold_groups=True,
    line="Measure how sharp each photo is, and act on the blurry ones.",
    verb="Move aside",
    unit="photographs",
    undo="They are moved into a pile, not deleted. Clean up is the "
         "only tool that finally removes them, and it tells you how "
         "much came back.",
    reads=("library", "raw", "previews"),
    moves_to=("library",),
    title="Find blurry",
    parent="cull",
    tab="Find blurry",
    summary="Measures how sharp each photo is, then tags the blurry ones or "
            "moves them to _Culled.",
    icon="image",
    order=45,
    options=[
        Folder("folder", "Folder to check", setting="library",
               help="The folder to measure, a shoot or the whole library. "
                    "Every JPEG in it is measured. A RAW file follows its "
                    "JPEG when photos are moved to _Culled."),
        Choice("do", "What to do", default="tag", choices=DO,
               help="What happens to a blurry photo. A tag moves nothing and "
                    "can be searched in Lightroom and Synology Photos, so "
                    "start with it."),
        Number("below", "Sharpness below", default=60, minimum=0, maximum=5000,
               group="Thresholds",
               help="A photo with a sharpness score below this number counts "
                    "as blurry. 0 to 5000, default 60. 0 turns this test "
                    "off. Check the list shows each photo's score, so look "
                    "at a few and adjust."),
        Number("of_shoot", "Softer than folder (%)", default=35, minimum=0,
               maximum=100, group="Thresholds",
               help="Also counts a photo as blurry when its score is below "
                    "this percentage of the typical score in its folder. "
                    "This keeps a dark shoot from being flagged as a whole. "
                    "0 to 100, default 35. 0 turns this off. The folder "
                    "needs at least five measured photos."),
        Option("word", "Tag to write", default="blurry",
               group="Thresholds",
               help="The tag written on each blurry photo when 'Tag them' is "
                    "chosen. Default blurry."),
        Flag("mirror", "Trees from Setup", default=True,
             group="Companion files", advanced=True,
             help="On, the tree boxes below are ignored and the trees come "
                  "from Setup, so files land where every other tool puts "
                  "them. Off, the folders you type below are used for this "
                  "run only. Turning this off does not stop RAW files or "
                  "previews moving."),
        Folder("raw", "RAW tree", tree=True, default="", must_exist=False,
               setting="raw", group="Companion files", advanced=True,
               help="The top of the RAW tree. A blurry photo's RAW file is "
                    "moved to the matching _Culled folder here. Blank leaves "
                    "RAW files alone. Ignored while Trees from Setup is on."),
        Folder("previews", "Previews tree", tree=True, default="",
               must_exist=False, setting="previews", group="Companion files",
               advanced=True,
               help="The top of the previews tree. A blurry photo's preview "
                    "is moved to the matching _Culled folder here. Blank "
                    "leaves previews alone. Ignored while Trees from Setup "
                    "is on."),
        Flag("in_file", "Write into the photo", default=True, group="Advanced",
             advanced=True,
             help="Writes the tag into the JPEG itself as well as into its "
                  "sidecar. Lightroom and darktable read the sidecar. "
                  "Synology Photos and Windows Explorer read the JPEG, so "
                  "leave this on unless you have a reason not to."),
    ],
    plan=plan,
    apply=apply,
))
