"""Delete a folder - into the share's Recycle Bin, never for good.

The one thing File Station does better than this app used to: you see a shoot
that should not exist, and you get rid of it. Here it goes with its RAWs, its
previews and its video in the other trees, which is the part File Station
cannot do - delete Spain in the library there and Spain is still in three other
places, and the tablet still shows it.

**Only into #recycle.** DSM keeps one per share when the Recycle Bin is on, and
moving into it is a rename you can undo from File Station. If the share has no
Recycle Bin this refuses, rather than quietly deleting outright.

**Never a whole tree.** A tree root, anything above one, and the Recycle Bin
itself are refused - in the plan, and again at the moment of moving, because a
plan is data and data can be wrong.
"""

from __future__ import annotations

import os
import shutil

from app.registry import Flag, Folder, Plan, Result, Row, Task, register
from core import moves
from core import cleanup as C
from core import settings as S
from core.paths import ensure_folder, safe_target, under

KEYS = (("raw", "with_raw"), ("previews", "with_previews"), ("video", "with_video"))
TREES = ("library", "raw", "previews", "video", "develop", "inbox")


def _size(n: int) -> str:
    for unit, step in (("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if n >= step:
            return f"{n / step:,.1f} {unit}"
    return f"{n:,} bytes"


def refusal(folder: str) -> str:
    """Why this folder must not be deleted, or "" when it may."""
    here = os.path.abspath(folder)
    if not os.path.isdir(here):
        return "it is not there"
    if os.path.dirname(here) == here:
        return "it is the top of the disk"
    if C.RECYCLE in here.split(os.sep):
        return "it is inside the Recycle Bin already"
    saved = S.load()
    for key in TREES:
        root = str(saved[key] or "").strip()
        if root and under(os.path.abspath(root), here):
            return f"it is, or holds, a whole tree ({root})"
    return ""


def _folders(opts) -> list:
    from core.paths import same_place
    chosen = [f for f in Folder("folder", "").chosen(opts.get("folder")) if f]
    keys = tuple(k for k, flag in KEYS if opts.get(flag))
    got = same_place(chosen, keys) if keys else chosen
    # One inside another goes with its parent - listing it twice would move it
    # and then fail to find it.
    got = sorted(set(os.path.abspath(g) for g in got), key=len)
    out = []
    for g in got:
        if not any(under(g, o) for o in out):
            out.append(g)
    return out


def _count(folder: str) -> tuple:
    files = size = 0
    for top, _dirs, names in os.walk(folder):
        for n in names:
            files += 1
            try:
                size += os.path.getsize(os.path.join(top, n))
            except OSError:
                pass
    return files, size


def plan(opts) -> Plan:
    p = Plan(task="delfolder")
    chosen = [f for f in Folder("folder", "").chosen(opts.get("folder")) if f]
    if not chosen:
        p.blocked = "Pick a folder to delete."
        return p
    p.columns = ["Folder", "Files", "Size"]
    total_files = total = 0
    for folder in _folders(opts):
        if not os.path.isdir(folder):
            if folder in [os.path.abspath(c) for c in chosen]:
                p.errors.append(f"{folder}: it is not there")
            continue                      # the RAW tree simply has no such shoot
        why = refusal(folder)
        if why:
            p.errors.append(f"Not deleted - {folder}: {why}")
            continue
        bin_folder = C.recycle_root(folder)
        if not bin_folder:
            p.errors.append(
                f"Not deleted - {folder}: its share has no Recycle Bin. Turn it "
                f"on in DSM > Control Panel > Shared Folder > Edit.")
            continue
        files, size = _count(folder)
        total_files += files
        total += size
        to = C.recycle_target(folder, bin_folder)
        p.rows.append(Row(
            what="folder", name=os.path.basename(folder), source=folder,
            target=to, size=size, detail=f"{files:,} files, {_size(size)}",
            cells=[f"{files:,}", _size(size)],
            data={"from": folder, "to": to, "files": files}))
    if not p.rows and not p.errors:
        p.blocked = "None of those folders is there."
    p.stats = [("Folders", f"{len(p.rows):,}"), ("Files in them", f"{total_files:,}"),
               ("Size", _size(total))]
    p.notes.append("Moved into the share's Recycle Bin - get it back from File "
                   "Station until DSM empties it.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    moved = 0
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        status = "OK"
        try:
            src = row.data["from"]
            why = refusal(src)
            if why:
                raise PermissionError(f"refused: {why}")
            if C.RECYCLE not in row.data["to"].split(os.sep):
                raise PermissionError("refused: not into a Recycle Bin")
            dst = moves.shift(result, src, row.data["to"])
            moved += row.size
            result.done += 1
        except Exception as exc:                        # noqa: BLE001
            status = result.blame(row.name, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)
    from core import acl
    acl.after_delete([r.data["from"] for r in plan.rows
                      if not os.path.exists(r.data["from"])])
    result.reclaimed, result.reclaim_kind = moved, "aside"
    result.stats = [("Folders deleted", f"{result.done:,}"),
                    ("Into the Recycle Bin", _size(moved)),
                    ("Failed", f"{result.failed:,}")]
    return result


register(Task(
    name="delfolder",
    line="Delete folders, with their RAWs and previews, to the Recycle Bin.",
    verb="Delete",
    unit="folders",
    risk="high",
    undo="On a share with a Recycle Bin they can be restored from File "
         "Station. Without one, they are gone.",
    reads=("library", "raw", "previews", "video"),
    title="Delete folder",
    parent="cleanup",
    tab="Delete folder",
    summary="Deletes whole folders, with their RAW files, previews and "
            "videos, into the share's recycle bin.",
    icon="folder-x",
    order=48,
    options=[
        Folder("folder", "Folders to delete", default="", many=True,
               help="The folders to delete. Everything inside each one goes "
                    "too."),
        Flag("with_raw", "Delete their RAW files", default=True, group="Other trees",
             help="Also deletes the matching folder in the RAW tree, and "
                  "only that folder. On by default."),
        Flag("with_previews", "Delete their previews", default=True,
             group="Other trees",
             help="Also deletes the matching folder in the previews tree, so "
                  "the tablet loses it on the next sync. On by default."),
        Flag("with_video", "Delete their videos", default=True, group="Other trees",
             help="Also deletes the matching folder in the video tree. On by "
                  "default."),
    ],
    plan=plan,
    apply=apply,
))
