"""Files - a file manager that knows what a photograph is made of.

File Station can already move a folder. What it cannot do is know that a
photograph in the library has a negative in a second tree and a preview in a
third, so a shoot moved there leaves two trees wrong and nothing says so until
a feature quietly stops pairing anything.

So this is an ordinary file manager - two panes, copy, move, rename, new
folder, delete, download - with one rule of its own: **what belongs together
travels together.** Move a JPEG inside the library and the same name in the
RAW and previews trees goes to the matching place, with every sidecar. It can
be turned off, and it is never guessed - only the same name, in the same
position, in a tree named in Setup.

Nothing here is a plan-then-apply feature: you have already said which files,
by picking them. What it does instead is refuse to overwrite (a taken name
becomes `_1`), send deletes to the Recycle Bin with Undo, and keep every run in
History like everything else.

Pictures view is the viewer: the same folder as thumbnails, with each one's
stars, colour and tags beside it, and a tap opens it full screen where it can be
rated, coloured, tagged or put aside.

The Power rename tab beside it is the same folders as a table you type into - thirty
folder names fixed in one pass rather than thirty dialogs.
"""

from __future__ import annotations

import os

from app.registry import Flag, Folder, Plan, Result, Task, register
from core import filesops


def plan(opts) -> Plan:
    """What is in the folder the manager is looking at. It writes nothing."""
    p = Plan(task="files")
    folder = str(opts.get("folder") or "").strip()
    if not folder or not os.path.isdir(folder):
        p.blocked = "Pick a folder to open."
        return p
    try:
        got = filesops.entries(folder)
    except filesops.Refused as exc:
        p.blocked = str(exc)
        return p
    p.stats = [("Folder", got["path"]),
               ("Folders in it", f"{len(got['folders']):,}"),
               ("Files", f"{len(got['files']):,}"),
               ("Size of those files", f"{got['size'] / 1e9:,.2f} GB"
                if got["size"] >= 1e9 else f"{got['size'] / 1e6:,.1f} MB")]
    p.notes.append("Everything in the manager above happens as you press it - "
                   "there is no list to read first, because you picked the "
                   "files yourself. Nothing is ever written over, and delete "
                   "means the Recycle Bin.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    return Result(details=["This tab only reports. The manager does the work."])


register(Task(
    name="files",
    line="Browse the folders themselves, with RAWs and previews following along.",
    title="File explorer",
    summary="Copies, moves, renames and deletes files and folders, with RAW "
            "files and previews following.",
    icon="folder",
    tab="Explorer",
    order=8,
    writes=False,
    editor="files",
    reads=("library", "raw", "previews", "video", "develop"),
    options=[
        Folder("folder", "Folder to open", setting="library",
               help="The folder the explorer opens on. The places bar jumps "
                    "to the other trees."),
        Flag("with_raw", "RAW files follow", default=True, group="Companion files",
             help="Moving or deleting a photo in the library does the same "
                  "to its RAW file at the matching place in the RAW tree. On "
                  "by default."),
        Flag("with_previews", "Previews follow", default=True,
             group="Companion files",
             help="Moving or deleting a photo in the library does the same "
                  "to its preview at the matching place in the previews "
                  "tree. On by default."),
    ],
    plan=plan,
    apply=apply,
))
