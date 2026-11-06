"""Put low-rated photos aside - and everything that belongs to them.

Culling a photo means the JPEG, its RAW wherever that now lives, both their
sidecars, and optionally the preview. Leaving any of those behind is how you end
up with a RAW tree full of files whose JPEGs are gone and no way to tell which.

Three decisions shape this task:

THE RATING IS READ FROM THE LIBRARY, not from the previews. Previews are
temporary and get regenerated; the library is the truth, and a preview that was
never re-synced would otherwise cull a photo on a stale number. The 'ratings'
task is what carries a rating from where you made it into the library first.

NOTHING IS DELETED. Files move into a `_Culled` folder inside their own tree,
keeping their position within it, so putting one back is a matter of moving it
up. A five-star photo mis-rated at one star is recoverable; deleted is not.

AN UNRATED PHOTO IS NEVER CULLED. Zero means "not looked at yet", not "rejected".
The Windows version had this backwards once and every unrated photo in the
library looked deliberately thrown out.

The thresholds are separate for JPEG and RAW, because the usual want is "keep
the JPEG of everything, keep the RAW only of what I liked" - and -1 means never
cull that kind at all.
"""

from __future__ import annotations

import os
import shutil

from app.grouping import sets_for
from app.registry import Flag, Folder, Number, Plan, Result, Row, Task, register
from core import moves
from core import walk
from core.exifwrite import rating_of, sidecar_path
from core import facts
from core.pairs import build_index, find_partner
from core.paths import (mirror_anchor, CULLED, ensure_folder, mirror, preview_for,
                        relative_under, safe_target, tidy_empty_folders, roots_of, under)
from core.photo import kind, read_capture

NEVER = -1



def _anchor(opts) -> str:
    """The library, from Setup - never a box on this tab.

    It used to be an Advanced option here, which asked a question with one
    right answer: the anchor is what makes a mirrored tree line up, and a
    different one typed on one tab and not another is how two features end up
    disagreeing about where a photograph belongs. Setup says it once.
    """
    from core import settings as _settings
    return (str(opts.get("library") or "").strip()
            or str(_settings.load()["library"] or "").strip())

def _aside(path: str, tree_root: str) -> str:
    """Where a file goes when it is put aside: _Culled, at the same position."""
    rel = relative_under(path, tree_root)
    return safe_target(os.path.join(tree_root, CULLED, rel))


def plan(opts) -> Plan:
    p = Plan(task="cull")
    scan = opts["folder"]
    raw_root = (opts.get("raw") or "").strip()
    preview_root = (opts.get("previews") or "").strip()
    # Only a refusal when another tree is actually going to be
    # reached into: with neither given, nothing is measured from the
    # anchor and a guess costs nothing.
    library, refuse = mirror_anchor(_anchor(opts), scan,
                                    raw_root or preview_root)
    if refuse:
        p.blocked = refuse
        return p

    if not scan or not os.path.isdir(scan):
        p.blocked = f"There is no folder at {scan!r}"
        return p
    if not os.path.isdir(library):
        p.blocked = f"There is no library at {library!r}"
        return p
    if library != scan and not under(scan, library):
        p.blocked = f"{scan!r} is not inside the library {library!r}."
        return p

    jpeg_at = int(opts["jpeg_at_or_below"])
    raw_at = int(opts["raw_at_or_below"])
    if jpeg_at < 0 and raw_at < 0:
        p.blocked = ("Both thresholds are set to never cull, so there is nothing to do. "
                     "Set at least one of them to 0-5.")
        return p

    found = walk.walk(scan)
    for path, why in found.errors:
        p.errors.append(f"could not read {path}: {why}")

    # One reader for the run - see core/facts.py. A cull reads the rating of
    # every photograph under the folder, which is the same set of files the
    # other tasks have just read, and on the second pass none of them is opened.
    facts_for = facts.reader()

    raw_index = None
    if raw_at >= 0 and raw_root and os.path.isdir(raw_root):
        raw_walk = walk.walk(raw_root)
        for path, why in raw_walk.errors:
            p.errors.append(f"could not read {path}: {why}")
        raw_index = build_index(raw_walk.files, want=("raw",),
                                reader=facts_for)

    # With one preview per bracket only the metered frame carries a rating. An
    # unrated frame borrows its set's, so the whole set is kept or culled together
    # - otherwise you drop the frame you judged and keep the two you did not.
    sets = sets_for(found.files, opts, p, reader=facts_for)

    photos = unrated = kept = via_bracket = shots = 0
    bytes_moved = 0
    seen_raws: set[str] = set()

    for path in sorted(found.files):
        if kind(path) not in ("jpeg", "image"):
            continue
        photos += 1
        stars = facts_for.stars(path)
        from_bracket = ""
        if not stars and sets is not None:
            s = sets.set_of(path)
            if s and s.representative.path != path:
                stars = facts_for.stars(s.representative.path)
                if stars:
                    from_bracket = s.representative.name
                    via_bracket += 1
        if not stars:
            unrated += 1
            p.skipped.append((path, "no rating - left alone"))
            continue

        cull_jpeg = 0 <= jpeg_at and stars <= jpeg_at
        cull_raw = 0 <= raw_at and stars <= raw_at
        if not cull_jpeg and not cull_raw:
            kept += 1
            p.skipped.append((path,
                              f"{stars} star - above both thresholds"
                              + (f" (rating from its bracket, {from_bracket})"
                                 if from_bracket else "")))
            continue

        why = []
        if cull_jpeg:
            why.append(f"JPEG at or below {jpeg_at}")
        if cull_raw:
            why.append(f"RAW at or below {raw_at}")
        if from_bracket:
            why.append(f"rating from its bracket ({from_bracket})")
        reason = f"{stars} star - " + " + ".join(why)

        batch: list[tuple[str, str, str]] = []      # what, path, tree root
        if cull_jpeg:
            batch.append(("JPEG", path, library))
            batch.append(("sidecar", sidecar_path(path), library))
            if preview_root:
                prev = preview_for(path, library, preview_root)
                batch.append(("preview", prev, preview_root))
                batch.append(("sidecar", sidecar_path(prev), preview_root))
        if cull_raw and raw_index is not None:
            m = find_partner(path, facts_for.capture(path), raw_index)
            if m.jpeg:                              # `jpeg` is "the partner found"
                seen_raws.add(os.path.normcase(m.jpeg))
                batch.append(("RAW", m.jpeg, raw_root))
                batch.append(("sidecar", sidecar_path(m.jpeg), raw_root))
            elif m.candidates > 1:
                p.skipped.append((path,
                                  f"its RAW is ambiguous - {m.how}, so it was left"))

        before = len(p.rows)
        for what, target, root in batch:
            if not target or not os.path.isfile(target):
                continue
            size = os.path.getsize(target)
            bytes_moved += size
            aside = _aside(target, root)
            p.rows.append(Row(
                what=what, name=os.path.basename(target), source=target,
                target=aside, size=size, detail=reason,
                cells=[what, f"{stars} star" if stars else "unrated",
                       " + ".join(why), CULLED],
                data={"from": target, "to": aside}))
        shots += len(p.rows) > before

    # A RAW whose JPEG is gone is never examined, because nothing walks it. Name
    # that gap rather than leaving it silent - it is exactly the blind spot that
    # makes a cull look complete when it was not.
    lonely = 0
    if raw_index is not None:
        scanned = build_index(found.files, reader=facts_for)   # once, not per RAW
        for raw_path, cap in raw_index.captures.items():
            if os.path.normcase(raw_path) in seen_raws:
                continue
            m = find_partner(raw_path, cap, scanned)
            if not m.jpeg and m.candidates == 0:
                lonely += 1

    p.columns = ["File", "Kind", "Rating", "Why", "Into"]
    # The button counts photographs, as its unit says. A row is a FILE - the
    # JPEG, its sidecar, its preview and its RAW - so counting rows said "Set
    # aside 12 photographs" about three.
    p.impact = {"count": shots}
    facts_for.save()
    p.stats = [
        ("Files opened", facts_for.said()),
        ("Photos examined", f"{photos:,}"),
        ("Files to move aside", f"{len(p.rows):,}"),
        ("Size", f"{bytes_moved / 1e9:.2f} GB" if bytes_moved > 1e9
         else f"{bytes_moved / 1e6:.0f} MB"),
        ("Kept - above the thresholds", f"{kept:,}"),
        ("Unrated - never culled", f"{unrated:,}"),
        ("  judged by their bracket", f"{via_bracket:,}"),
        ("RAWs with no JPEG in this scan", f"{lonely:,}"),
        ("Folders unreadable", f"{len(p.errors):,}"),
    ]

    p.notes.append("Nothing is deleted. Everything moves into a _Culled folder inside "
                   "its own tree, keeping its position, so putting one back is a move.")
    p.notes.append("The rating is read from the library, not from the previews - run "
                   "'ratings' first if you rated somewhere else.")
    p.notes.append("An unrated photo is never culled. Zero stars means not looked at "
                   "yet, not rejected.")
    if lonely:
        p.notes.append(f"{lonely} RAW(s) have no JPEG anywhere in what was scanned, so "
                       f"no rating could judge them and they were not touched. "
                       f"'remirror' is the tool that deals with those.")
    if p.errors:
        p.blocked = (f"{len(p.errors)} folder(s) could not be read. \"These are the "
                     f"low-rated photos\" is a claim about the whole tree; part of it "
                     f"was invisible, so nothing will be moved until that is fixed.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result

    touched: set[str] = set()
    freed = 0
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        src, dst = row.data["from"], row.data["to"]
        status = "OK"
        try:
            if not os.path.exists(src):
                raise FileNotFoundError("it is no longer there")
            dst = moves.shift(result, src, dst)
            touched.add(os.path.dirname(src))
            freed += row.size
            result.done += 1
        except Exception as exc:                    # noqa: BLE001
            status = result.blame(src, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)

    removed = (tidy_empty_folders(touched, stop_at=roots_of(plan.opts))
               if plan.opts.get("tidy", True) else 0)
    result.reclaimed, result.reclaim_kind = freed, "aside"
    result.stats = [("Files moved aside", f"{result.done:,}"),
                    ("Space freed in the library", f"{freed / 1e9:.2f} GB"
                     if freed > 1e9 else f"{freed / 1e6:.0f} MB"),
                    ("Failed", f"{result.failed:,}"),
                    ("Empty folders tidied", f"{removed:,}")]
    if not result.details:
        result.details.append(
            f"Everything is in a {CULLED} folder inside its own tree, at the same "
            f"position it had. Nothing was deleted.")
    return result


register(Task(
    name="cull",
    fold_groups=True,
    line="Move the low-rated photos aside, into a folder you can empty "
         "later. Nothing is deleted.",
    verb="Move aside",
    unit="photographs",
    undo="They are moved into a pile, not deleted. Clean up is the "
         "only tool that finally removes them, and it tells you how "
         "much came back.",
    reads=('library', 'raw', 'previews'),
    moves_to=('library',),
    title="Cull by rating",
    summary="Moves low-rated photos, with their RAW files, sidecars and "
            "previews, into a _Culled folder.",
    icon="cross",
    # and the low-rated go aside. The head of the Review tools that weed a
    # library - blurry, duplicates, brackets, exposure are its tabs - so the
    # tab row it draws is all Review, the group it is filed under.
    tab="Cull by rating",
    order=44,
    options=[
        Folder("folder", "Folder to cull", setting="library",
               help="The folder to read ratings from, a shoot or the whole "
                    "library."),
        Number("jpeg_at_or_below", "JPEG at or below", default=NEVER,
               minimum=-1, maximum=5, group="Thresholds",
               help="A JPEG rated this many stars or fewer is moved to "
                    "_Culled. -1 to 5, default -1, which never moves a JPEG. "
                    "An unrated photo is never moved."),
        Number("raw_at_or_below", "RAW at or below", default=2,
               minimum=-1, maximum=5, group="Thresholds",
               help="A RAW file whose photo is rated this many stars or "
                    "fewer is moved to _Culled. -1 to 5, default 2. -1 never "
                    "moves a RAW file. The usual choice keeps every JPEG and "
                    "only the RAW files of photos you liked. An unrated "
                    "photo is never moved."),

        Flag("mirror", "Trees from Setup", default=True,
             group="Companion files",
             help="On, the tree boxes below are ignored and the trees come "
                  "from Setup, so files land where every other tool puts "
                  "them. Off, the folders you type below are used for this "
                  "run only. Turning this off does not stop RAW files or "
                  "previews moving."),
        Folder("raw", "RAW tree", tree=True, default="", must_exist=False, setting="raw",
               group="Companion files",
               help="The top of the RAW tree. RAW files are matched by "
                    "capture time, camera and name, wherever they sit in the "
                    "tree. Blank leaves RAW files alone."),
        Folder("previews", "Previews tree", tree=True, default="", must_exist=False,
               setting="previews", group="Companion files",
               help="The top of the previews tree. Each moved photo's "
                    "preview is moved to the matching _Culled folder here. "
                    "Blank leaves previews alone."),

        Flag("brackets", "Keep brackets together",
             setting="bracket_group", group="Brackets",
             help="Treats a bracket set as one photo: an unrated frame takes "
                  "the rating of its set, so the whole set is kept or moved "
                  "together. How a set is found is set in Setup > Brackets. "
                  "From Setup by default."),

        Flag("tidy", "Tidy empty folders", default=True,
             group="Advanced", advanced=True,
             help="Removes a folder that this run has emptied. Only folders "
                  "this run emptied itself are removed, never a folder that "
                  "still holds anything. On by default."),
    ],
    plan=plan,
    apply=apply,
))
