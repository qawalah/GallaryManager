"""Pull the RAWs out of a mixed library, into a tree that mirrors it.

The result is a library anyone can be handed - JPEGs only, in the folders you
already use - and a RAW tree standing beside it in the same shape.

Two rules, both learned the hard way:

A LONE RAW STAYS. A RAW with no JPEG beside it is the only copy of that shot;
moving it leaves a hole in the folder you were making shareable, and you would
not notice until you went looking for the picture. It is reported instead, and
moved only if you ask.

THE MIRROR IS ANCHORED TO THE LIBRARY, not to the folder you happened to select.
Unpairing one shoot has to put its RAWs exactly where unpairing the whole library
would have put them - otherwise scanning at two different levels quietly builds
two different trees which then collide.

Sidecars follow their RAW: an .xmp is a note about that file and is meaningless
without it.
"""

from __future__ import annotations

import os
import shutil

from app.registry import Flag, Folder, Plan, Result, Row, Task, register
from core import meter, moves
from core import walk
from core.paths import (mirror_anchor, ensure_folder, relative_under, safe_target, tidy_empty_folders, roots_of,
                        under)
from core.pairs import base_name
from core.photo import kind



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

def _groups(files):
    """Files of one folder sharing a base name: the JPEG, its RAW, their sidecars."""
    out: dict[tuple[str, str], dict] = {}
    for path in files:
        k = kind(path)
        if k == "other":
            continue
        key = (os.path.dirname(path), base_name(path))
        g = out.setdefault(key, {"folder": key[0], "jpeg": [], "raw": [], "sidecar": []})
        if k in ("jpeg", "image"):
            g["jpeg"].append(path)
        elif k == "raw":
            g["raw"].append(path)
        elif k == "sidecar":
            g["sidecar"].append(path)
    return out


def plan(opts) -> Plan:
    p = Plan(task="unpair")
    source, raw_root = opts["folder"], opts["raw"]
    library, refuse = mirror_anchor(_anchor(opts), source, opts.get('raw') or '')
    if refuse:
        p.blocked = refuse
        return p

    if not source or not os.path.isdir(source):
        p.blocked = f"There is no folder at {source!r}"
        return p
    if not raw_root:
        p.blocked = "Say where the RAW tree should be."
        return p
    if under(source, raw_root) or under(raw_root, source):
        p.blocked = ("The RAW tree is inside the library (or the other way round). "
                     "Moving RAWs into it would move them into the tree being scanned.")
        return p
    if library != source and not under(source, library):
        p.blocked = (f"{source!r} is not inside the library {library!r}, so mirroring "
                     f"it would put the RAWs in the wrong place.")
        return p

    found = walk.walk(source)
    for path, why in found.errors:
        p.errors.append(f"could not read {path}: {why}")

    move_lone = bool(opts["unpaired"])
    pairs = lone = 0
    total = 0
    for g in _groups(found.files).values():
        if not g["raw"]:
            continue
        has_jpeg = bool(g["jpeg"])
        if not has_jpeg and not move_lone:
            lone += len(g["raw"])
            for r in g["raw"]:
                p.skipped.append((r,
                                  "no JPEG beside it - moving it would leave a hole"))
            continue
        if has_jpeg:
            pairs += 1
        else:
            lone += len(g["raw"])

        rel = relative_under(g["folder"], library)
        for path in g["raw"] + g["sidecar"]:
            target = safe_target(os.path.join(raw_root, rel, os.path.basename(path)))
            size = os.path.getsize(path) if os.path.exists(path) else 0
            total += size
            p.rows.append(Row(
                what="RAW" if kind(path) == "raw" else "sidecar",
                name=os.path.basename(path), source=path, target=target, size=size,
                detail=("beside " + os.path.basename(g["jpeg"][0])) if has_jpeg
                       else "no JPEG - moved because you asked",
                approximate=not has_jpeg,
                data={"from": path, "to": target}))

    p.stats = [
        ("Shots with both a JPEG and a RAW", f"{pairs:,}"),
        ("Files to move", f"{len(p.rows):,}"),
        ("Size", f"{total / 1e9:.2f} GB" if total > 1e9 else f"{total / 1e6:.0f} MB"),
        ("Lone RAWs", f"{lone:,}"),
        ("Folders unreadable", f"{len(found.errors):,}"),
    ]

    p.notes.append(f"The RAW tree mirrors {library} - not the folder scanned - so "
                   f"unpairing one shoot lands where unpairing everything would.")
    if lone and not move_lone:
        p.notes.append(f"{lone} RAW(s) have no JPEG beside them and were left alone. "
                       f"They are the only copy of those shots.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    """Copy, verify the size, then remove - never a bare move across drives.

    The library and the RAW tree are usually different shares. A move that fails
    halfway across a network leaves nothing behind on either side; copy-verify-delete
    can only ever leave a duplicate, which is recoverable.
    """
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result

    copy_only = bool(plan.opts.get("copy"))
    touched: set[str] = set()
    moved = 0
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        src, dst = row.data["from"], row.data["to"]
        status = "OK"
        try:
            if not os.path.exists(src):
                raise FileNotFoundError("it is no longer there")
            dst = safe_target(dst)
            ensure_folder(os.path.dirname(dst))
            shutil.copy2(src, dst)
            meter.copied(row.size)
            if os.path.getsize(dst) != os.path.getsize(src):
                os.remove(dst)
                raise OSError("the copy came out a different size - nothing was removed")
            if not copy_only:
                os.remove(src)
                # The copy-check-remove above IS the move, done the careful
                # way; written down the moment it is whole, as core.moves.shift
                # does for every other mover, so History can put it back.
                moves.note(result, src, dst)
                touched.add(os.path.dirname(src))
            moved += 1
            result.done += 1
        except Exception as exc:                    # noqa: BLE001
            status = result.blame(src, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)

    removed = (tidy_empty_folders(touched, stop_at=roots_of(plan.opts))
               if plan.opts.get("tidy", True) else 0)
    result.stats = [("Files " + ("copied" if copy_only else "moved"), f"{moved:,}"),
                    ("Failed", f"{result.failed:,}"),
                    ("Empty folders tidied", f"{removed:,}")]
    if not result.details:
        result.details.append(
            "Each file was copied, its size checked against the original, and only "
            "then removed." if not copy_only else "Copied; the library is untouched.")
    return result


register(Task(
    name="unpair",
    line="Move the camera's RAW files out of the library folders into a tree of their own, each one still paired with its JPEG.",
    verb="Move",
    unit="RAW files",
    undo="The RAW files move into the RAW tree at the same position. "
         "Re-mirror puts them back in step after you reorganise the "
         "library.",
    reads=('library',),
    moves_to=('raw',),
    title="Separate RAWs",
    summary="Moves RAW files out of the library into a RAW tree with the "
            "same folder shape.",
    icon="scissors",
    # with the shape settled, the negatives come out of it
    order=25,
    options=[
        Folder("folder", "Folder to separate", setting="library",
               help="The folder to move RAW files out of, a shoot or the "
                    "whole library."),
        Flag("mirror", "Trees from Setup", default=True,
             help="On, the tree boxes below are ignored and the trees come "
                  "from Setup, so files land where every other tool puts "
                  "them. Off, the folders you type below are used for this "
                  "run only. Turning this off does not stop RAW files or "
                  "previews moving."),
        Folder("raw", "RAW tree", tree=True, must_exist=False, setting="raw",
               help="The top of the RAW tree. It is made if it does not "
                    "exist. It must not be inside the library."),
        Flag("unpaired", "Move lone RAW files",
             group="Advanced", advanced=True,
             help="Also moves RAW files that have no JPEG. Off by default: a "
                  "lone RAW file is the only copy of that photo, and moving "
                  "it leaves a gap in the folder."),
        Flag("copy", "Copy instead of move",
             group="Advanced", advanced=True,
             help="Copies RAW files into the RAW tree and leaves the library "
                  "untouched. Off by default: RAW files are moved, which is "
                  "the point of separating them. Copying uses the disk space "
                  "twice and is a way to try the tool out."),
        Flag("tidy", "Tidy empty folders", default=True,
             group="Advanced", advanced=True,
             help="Removes a folder that this run has emptied. Only folders "
                  "this run emptied itself are removed, never a folder that "
                  "still holds anything. On by default."),
    ],
    plan=plan,
    apply=apply,
))
