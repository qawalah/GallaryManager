"""Reshape the previews tree to match whatever the library looks like now.

The same job Re-mirror RAWs does, for the tree you rate on. Reorganise the
library and the previews stay in the old shape, so the folders you browse on the
tablet no longer look like the folders on the NAS - and the ratings you give
still come back correctly, because syncing pairs by identity rather than by
path, but finding anything becomes guesswork.

**A preview is disposable, and that changes the honest advice rather than the
feature.** Making them again produces exactly the same result and costs minutes
of CPU per thousand; moving them costs seconds and no CPU at all. So this is the
cheap way round, and Make previews is the other one - neither is wrong, and the
tab says so rather than pretending re-mirroring is the only answer.

**An orphaned preview is left alone by default**, for the same reason: the
photograph it stands for is gone, so it is a picture of nothing. Deleting it
would be this app deleting a file, which it does in exactly one place and not
here; and putting it aside clutters a tree whose whole point is being
disposable. So it is named, and Make previews will simply not make it again.
"""

from __future__ import annotations

import os
import shutil

from app.registry import Choice, Flag, Folder, Plan, Result, Row, Task, register
from core import moves
from core import walk
from core.pairs import base_name, build_index, find_partner
from core.paths import (CULLED, ensure_folder, mirror, relative_under,
                        safe_target, tidy_empty_folders, roots_of, under)
from core.photo import kind, read_capture

ORPHANS = [
    ("leave", "Leave it where it is"),
    ("aside", "Move it to _Culled in the previews tree"),
]


def plan(opts, progress=None) -> Plan:
    p = Plan(task="remirror_previews")
    library = (opts.get("library") or "").strip()
    previews = (opts.get("previews") or "").strip()

    for label, folder in (("library", library), ("previews tree", previews)):
        if not folder or not os.path.isdir(folder):
            p.blocked = f"There is no {label} at {folder!r}"
            return p
    if os.path.realpath(library) == os.path.realpath(previews) \
            or under(previews, library) or under(library, previews):
        p.blocked = ("The previews tree is inside the library, or the other way "
                     "round. They have to be separate trees for one to mirror "
                     "the other.")
        return p

    prev_walk = walk.walk(previews)
    lib_walk = walk.walk(library)
    for path, why in prev_walk.errors + lib_walk.errors:
        p.errors.append(f"could not read {path}: {why}")

    # Only the names that could possibly be asked about - a preview carries its
    # original's name, and every way one is matched to the other starts there.
    mine = [f for f in prev_walk.files if kind(f) in ("jpeg", "image")]
    originals = build_index(lib_walk.files, want=("jpeg", "image", "raw"),
                            names={base_name(f) for f in mine},
                            progress=(lambda i, n, x: progress(i, n, x, "OK"))
                            if progress else None)

    moved = already = orphaned = 0
    p.columns = ["Preview", "Its photo", "Why there"]
    for i, path in enumerate(sorted(mine), 1):
        if progress:
            progress(i, len(mine), os.path.basename(path))
        m = find_partner(path, read_capture(path), originals)
        if not m.jpeg:
            orphaned += 1
            if str(opts.get("orphans") or "leave") == "aside":
                rel = relative_under(os.path.dirname(path), previews)
                target = safe_target(os.path.join(previews, CULLED, rel,
                                                  os.path.basename(path)))
                p.rows.append(Row(
                    what="moved aside", name=os.path.basename(path), source=path,
                    target=target, approximate=True,
                    detail="the photo it stands for is nowhere in the library",
                    cells=["none - it is a preview of nothing",
                           "moved aside inside the previews tree"],
                    data={"from": path, "to": target}))
            else:
                p.skipped.append((
                    path,
                    "the photo it stands for is nowhere in the library. Left "
                    "where it is - a preview is disposable, and Make previews "
                    "will simply not make it again."))
            continue

        target = mirror(m.jpeg, library, previews)
        target = os.path.join(os.path.dirname(target), os.path.basename(path))
        if os.path.normcase(os.path.dirname(target)) == \
                os.path.normcase(os.path.dirname(path)):
            already += 1
            continue
        moved += 1
        p.rows.append(Row(
            what="move", name=os.path.basename(path), source=path, target=target,
            detail=f"follows {os.path.basename(m.jpeg)}  ({m.how})",
            cells=[os.path.basename(m.jpeg), m.how],
            data={"from": path, "to": target}))

    p.stats = [
        ("Previews found", f"{len(mine):,}"),
        ("Already in the right place", f"{already:,}"),
        ("TO MOVE", f"{moved:,}"),
        ("Orphaned - no photo any more", f"{orphaned:,}"),
        ("Folders unreadable", f"{len(prev_walk.errors) + len(lib_walk.errors):,}"),
    ]
    p.notes.append(
        "The library is never changed. Only the previews tree is reshaped to "
        "match it.")
    p.notes.append(
        "Making them again would give exactly the same result. Moving them costs "
        "seconds and no CPU; remaking a thousand costs minutes of it. This is "
        "the cheap way round and Make previews is the other - neither is wrong.")
    p.notes.append(
        "Each preview is matched to its photo by capture time, camera and "
        "name, so this works however the library was renamed or split.")
    if orphaned:
        p.notes.append(
            f"{orphaned} preview(s) stand for photos that are no longer in "
            f"the library. A preview is disposable, so the default is to leave "
            f"them: nothing here deletes, and putting them aside only clutters a "
            f"tree whose point is being thrown away.")
    if p.errors:
        p.blocked = (f"{len(p.errors)} folder(s) could not be read. A preview "
                     f"might look orphaned only because its photo is in one "
                     f"of them, so nothing will be moved until that is fixed.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    touched: set = set()
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
            result.done += 1
        except Exception as exc:                    # noqa: BLE001
            status = result.blame(src, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)

    removed = (tidy_empty_folders(touched, stop_at=roots_of(plan.opts))
               if plan.opts.get("tidy", True) else 0)
    result.stats = [("Previews moved", f"{result.done:,}"),
                    ("Failed", f"{result.failed:,}"),
                    ("Empty folders tidied", f"{removed:,}")]
    if not result.details:
        result.details.append(
            "The previews tree is the shape of the library again. Nothing was "
            "remade, so every rating already on them is untouched.")
    return result


register(Task(
    name="remirror_previews",
    line="Move each preview to where its photo now lives.",
    verb="Move",
    unit="previews",
    undo="Only the position changes - nothing leaves the previews "
         "tree.",
    reads=('library', 'previews'),
    moves_to=('previews',),
    title="Re-mirror previews",
    summary="Moves each preview to where its photo now is, instead of "
            "remaking the whole tree.",
    icon="mirror",
    parent="previews",
    tab="Re-mirror previews",
    order=33,
    options=[
        Folder("library", "Library", tree=True, setting="library",
               help="The library, read only. Where each photo is now decides "
                    "where its preview goes."),
        Folder("previews", "Previews tree", tree=True,
               setting="previews",
               help="The top of the previews tree. Previews are only moved "
                    "within it and none is remade, so the ratings on them "
                    "survive."),
        Choice("orphans", "Orphaned previews",
               default="leave", choices=ORPHANS,
               help="What to do with a preview whose photo no longer exists. "
                    "Leaving it costs a few kilobytes, and Make previews "
                    "will not remake it."),
        Flag("tidy", "Tidy empty folders", default=True,
             advanced=True, group="Advanced",
             help="Removes a folder that this run has emptied. Only folders "
                  "this run emptied itself are removed, never a folder that "
                  "still holds anything. On by default."),
    ],
    plan=plan,
    apply=apply,
))
