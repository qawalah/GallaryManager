"""Where the disk went, folder by folder - and how much of it you could get back.

The week the NAS says it is 90% full, the question is not "how many photographs
have I got". It is *which folders are the big ones*, and *what in here is not
worth keeping*. File Station will not answer the first without opening thirty
folders and adding up, and nothing at all answers the second, because only this
app knows that a `_Culled` pile is recoverable litter and a previews tree can be
made again from scratch.

**One folder, four trees.** A shoot does not cost what the library says it
costs: there is a negative for every frame in the RAW tree, a small copy in the
previews tree, clips in the video tree and whatever was put aside from it. They
are four different places on the disk and one decision, so they are one row
here, side by side, and the total is the one to argue with.

**The sizes are the Library tab's own.** They come off the same read, cached
against the same folder signatures (`core/survey.py`) - so if you have looked at
the Library today this costs nothing, and if you have not, the Library will be
free afterwards. Nothing here is opened twice.

**Reclaimable means reclaimable by something in this app.** Piles put aside,
previews that can be made again, the Recycle Bin. Not "delete your RAWs" - a
number that includes things you would never delete is a number nobody trusts
twice.

Nothing is written.
"""

from __future__ import annotations

import os

from app.registry import Flag, Folder, Number, Plan, Result, Row, Task, register
from core import cleanup
from core import settings as S
from core import survey as SV
from core.store import store_path
from core.survey import Cache

CACHE = "survey.json"          # shared with the Library tab, on purpose


def human(n: int) -> str:
    """Bytes, the way a disk is talked about."""
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return (f"{n:,.0f} {unit}" if unit in ("B", "KB")
                    else f"{n:,.1f} {unit}")
        n /= 1024
    return f"{n:,.1f} TB"


def bar(part: float, whole: float, width: int = 14) -> str:
    """A bar made of text, so it lives in the same table as the numbers."""
    if not whole:
        return ""
    filled = max(0, min(width, round(width * part / whole)))
    if part and not filled:
        filled = 1
    return "█" * filled + "░" * (width - filled)


def _depth_of(state, library: str) -> int:
    rel = state.rel or ""
    return len([p for p in rel.split(os.sep) if p])


def plan(opts, progress=None) -> Plan:
    p = Plan(task="space")
    library = str(opts.get("folder") or "").strip()
    if not library or not os.path.isdir(library):
        p.blocked = f"There is no library at {library!r}"
        return p

    saved = S.load()
    raw_root = (str(opts.get("raw") or saved["raw"] or "").strip()
                if opts.get("with_raw", True) else "")
    previews_root = (str(opts.get("previews") or saved["previews"] or "").strip()
                     if opts.get("with_previews", True) else "")
    video_root = (str(opts.get("video") or saved["video"] or "").strip()
                  if opts.get("with_video", True) else "")
    depth = max(1, int(opts.get("depth") or 2))
    most = max(5, int(opts.get("most") or 40))

    cache = Cache(store_path(CACHE))
    found = SV.survey(library, raw_root, previews_root, cache=cache,
                      progress=progress, video_root=video_root)
    cache.save()

    rolled = {s.path: s.totals(found.folders) for s in found.folders.values()}
    whole = rolled.get(library)
    if whole is None:
        p.blocked = "Nothing could be read in there."
        return p

    # -------------------------------------------------- where the space is
    rows = []
    for state in found.order():
        if state.path == library:
            continue
        here = _depth_of(state, library)
        if here > depth:
            continue
        total = rolled[state.path].weight()
        if not total:
            continue
        # A folder at the cut-off line carries everything below it; one above
        # the line would then count its children twice, so only the deepest
        # level asked for is listed, plus any shallower folder that is a leaf.
        if here < depth and state.children:
            continue
        rows.append((state, rolled[state.path], total))

    rows.sort(key=lambda r: -r[2])
    biggest = rows[0][2] if rows else 0
    listed = sum(r[2] for r in rows)

    p.columns = ["Folder", "Photos", "Library", "RAWs", "Previews", "Video",
                 "Aside", "Total", "Share"]
    if rows:
        p.groups.append({
            "key": "folders", "label": f"Where the space is - {depth} level(s) down",
            "cells": [f"{len(rows):,} folder(s)", "", human(listed), "", "", "",
                      "", "", ""],
            "note": "Each row is one shoot across every tree it reaches into: "
                    "the photos, their RAW files, the previews, the videos "
                    "and whatever was moved aside from it. Biggest first."})
    for state, totals, total in rows[:most]:
        p.rows.append(Row(
            what="folder", name=state.rel or state.name, source=state.path,
            size=total,
            detail=f"{human(total)} in {state.rel or state.name}",
            cells=[f"{totals.photos:,}" if totals.photos else "-",
                   human(totals.bytes), human(totals.raw_bytes),
                   human(totals.preview_bytes), human(totals.video_bytes),
                   human(totals.culled_bytes), human(total),
                   bar(total, biggest)],
            group="folders", data={"path": state.path}))
    if len(rows) > most:
        left = sum(r[2] for r in rows[most:])
        p.notes.append(f"{len(rows) - most:,} smaller folder(s) are not listed - "
                       f"{human(left)} between them.")

    # -------------------------------------------------- what could be freed
    back = []
    WHY = {
        "culled": "Moved aside by Cull or by hand. Clean up empties these once "
                  "you are sure.",
        "duplicates": "Copies this app moved out of the way. The one it kept "
                      "is still in the library.",
        "nolocation": "Originals kept before a location was written over them.",
    }
    for pile in cleanup.piles_under(library, list(WHY)):
        if pile.bytes:
            back.append((f"{os.path.basename(pile.path)} in "
                         f"{os.path.basename(os.path.dirname(pile.path)) or library}",
                         pile.path, pile.files, pile.bytes, WHY[pile.kind]))
    if previews_root and os.path.isdir(previews_root):
        pile = cleanup.measure(previews_root)
        if pile.bytes:
            back.append(("Previews", previews_root, pile.files, pile.bytes,
                         "Previews. Make previews builds them again from "
                         "the library whenever you want them back."))
    bin_folder = cleanup.recycle_root(library)
    if bin_folder and os.path.isdir(bin_folder):
        pile = cleanup.measure(bin_folder)
        if pile.bytes:
            back.append(("Recycle Bin", bin_folder, pile.files, pile.bytes,
                         "DSM's own bin for this share. Emptying it is the one "
                         "thing here that cannot be undone."))

    freeable = sum(b[3] for b in back)
    if back:
        p.groups.append({
            "key": "back", "label": "What you could get back",
            "cells": [f"{len(back)} pile(s)", "", "", "", "", "", "",
                      human(freeable), ""],
            "note": "Only things this app can put back or make again. Your "
                    "photos and their RAW files are not in this list, and "
                    "never will be."})
    for name, where, files, size, why in sorted(back, key=lambda b: -b[3]):
        p.rows.append(Row(
            what="reclaim", name=name, source=where, size=size,
            detail=why,
            cells=[f"{files:,}", "", "", "", "", "", "", human(size),
                   bar(size, freeable)],
            group="back", data={"path": where}))

    total = whole.weight()
    p.stats = [
        ("Everything, all trees", human(total)),
        ("The library itself", human(whole.bytes)),
        ("RAWs", human(whole.raw_bytes)),
        ("Previews", human(whole.preview_bytes)),
        ("Video", human(whole.video_bytes)),
        ("Moved aside", human(whole.culled_bytes)),
        ("Could be freed", human(freeable)),
        ("Photos", f"{whole.photos:,}"),
    ]
    if whole.photos:
        p.stats.append(("Each photo, on average",
                        human(total / whole.photos)))
    p.notes.append(
        f"{found.read:,} folder(s) read this time, {found.reused:,} answered "
        f"from last time. The Library tab reads the same answers, so whichever "
        f"you open first pays for both.")
    if not raw_root:
        p.notes.append("No RAW tree in Setup, so the RAW files are not counted "
                       "and the totals here are smaller than the disk.")
    if not previews_root:
        p.notes.append("No previews tree in Setup, so previews are not counted.")
    p.notes.append("Nothing is written. Click a folder to open it in another "
                   "tool - Clean up is usually the one you want.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    return Result(details=["This tab only reports. Nothing was written."])


register(Task(
    name="space",
    line="Where the disk has gone, folder by folder, and what could be "
         "freed.",
    reads=("library", "raw", "previews", "video"),
    title="Storage",
    summary="Shows how much disk each folder and tree uses, and what could "
            "be freed. Nothing is changed.",
    icon="layers",
    parent="cleanup",
    order=7,
    writes=False,
    options=[
        Folder("folder", "Library", setting="library",
               help="The library to measure. It is read, never written."),
        Number("depth", "Levels to list", default=2, minimum=1, maximum=6,
               help="How many folder levels to list. 1 to 6, default 2. 1 "
                    "lists the years, 2 the shoots in them. Each row "
                    "includes everything below it, so nothing is counted "
                    "twice."),
        Number("most", "Rows to show", default=40, minimum=5, maximum=500,
               group="Advanced", advanced=True,
               help="How many of the largest folders to list. 5 to 500, "
                    "default 40. The rest are added up in one note."),
        Flag("with_raw", "Count RAW files", default=True, group="Trees",
             help="Includes the RAW tree from Setup, usually most of the "
                  "space. On by default."),
        Flag("with_previews", "Count previews", default=True,
             group="Trees",
             help="Includes the previews tree from Setup. Each preview is "
                  "small, but there is one per photo. On by default."),
        Flag("with_video", "Count videos", default=True, group="Trees",
             help="Includes the video tree from Setup. On by default."),
    ],
    plan=plan,
    apply=apply,
))
