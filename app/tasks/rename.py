"""Rename - every folder in a table, with its name in a box you type in.

The mess this is for: a library grown over years has `2022-04-12`, `12 April
2022`, `April 12`, `Spain trip` and `spain trip 2` sitting side by side, because
each was made by whatever habit you had that month. Any file manager renames one
of those. None of them lets you see all thirty at once and fix them in a pass -
and one at a time you lose track of what you decided halfway down.

So: the table. Every folder, its name editable in place, and nothing written
until Rename is pressed. Above it, four ways to change every row at once - find
and replace, a saved folder pattern, numbering, and case and spacing - each of
which fills the boxes rather than doing anything, so what you are about to write
is on the screen before it happens.

It refuses a half-done job. Any row with a problem stops the whole table, so
"which fifteen of the thirty went through" is a question nobody has to answer.
Two rows meeting on one name, and a name already taken by something not in the
table, are the two that actually happen; both are named in the row itself.

And the rule this app exists for: a folder renamed in the library is renamed at
the matching place in the RAW and previews trees. Only the same position in a
tree named in Setup - never a guess, and a tree that does not have that folder
is left alone and said so.
"""

from __future__ import annotations

import os

from app.registry import Flag, Folder, Number, Plan, Result, Task, register
from core import renames


def plan(opts) -> Plan:
    """What the table is standing on. It writes nothing - the table does."""
    p = Plan(task="rename")
    folder = str(opts.get("folder") or "").strip()
    if not folder or not os.path.isdir(folder):
        p.blocked = "Pick a folder whose folders you want to rename."
        return p
    depth = int(opts.get("depth") or 1)
    try:
        got = renames.listing(folder, depth)
    except renames.Refused as exc:
        p.blocked = str(exc)
        return p
    deep = "the whole way down" if depth == 0 else f"{depth} level(s) down"
    p.stats = [("Folder", got["folder"]),
               ("Folders in the table", f"{len(got['rows']):,}"),
               ("Levels to list", deep)]
    if got["capped"]:
        p.notes.append(f"The first {renames.CAP:,} only - go a level shallower, "
                       f"or start further in.")
    p.notes.append("Type over the names in the table above. Nothing is written "
                   "until you press Rename, and a row with a problem stops the "
                   "whole table rather than leaving half of it done.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    return Result(details=["This tab only reports. The table does the renaming."])


register(Task(
    name="rename",
    # No verb: this tab writes nothing itself - the table's own buttons do, one
    # folder at a time, and an Apply button here would be offering something
    # the page cannot do. History names its runs from this instead.
    unit="folders",
    line="Every folder in a table, with its name editable in place.",
    title="Power rename",
    summary="Lists folders in a table and renames them in place, with find "
            "and replace, patterns, numbering and case.",
    icon="rename",
    parent="files",
    order=9,
    writes=False,
    editor="rename",
    reads=("library", "raw", "previews", "video", "develop"),
    options=[
        Folder("folder", "Folder to list", setting="library",
               help="The folder whose sub-folders fill the table. Folders "
                    "selected in the Explorer tab first are listed instead."),
        Number("start", "Start at level", default=0, minimum=0, maximum=9,
               help="How many levels below the folder the table starts. 0 to "
                    "9, default 0. 0 lists the folder's own sub-folders. 1 "
                    "skips them and lists the level below, so a library of "
                    "years can list the shoots without the years."),
        Number("depth", "Levels to list", default=1, minimum=0, maximum=9,
               help="How many levels of folders to list. 0 to 9, default 1. "
                    "1 lists one level. 0 lists every level down from the "
                    "start, indented, so a deep folder can be fixed in the "
                    "same run."),
        Flag("with_raw", "RAW files follow", default=True, group="Companion folders",
             help="Renames the matching folder in the RAW tree too, so the "
                  "trees stay mirrored. On by default."),
        Flag("with_previews", "Previews follow", default=True,
             group="Companion folders",
             help="Renames the matching folder in the previews tree too, so "
                  "the preview does not keep the old name. On by "
                  "default."),
    ],
    plan=plan,
    apply=apply,
))
