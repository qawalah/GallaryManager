"""Sample library - somewhere to learn this app that is not your photographs.

Every other tab in here moves somebody's real files. That makes this app a bad
one to learn by trying things, and a guide can only describe: the first run of
Sort into folders is on four hundred photographs that matter, with the plan on
screen and the person reading it hoping they have worked out what the pattern
does. They press Apply anyway, and if they have misunderstood it they find
out afterwards.

This builds a library to practise on - with the faults a real one has, because a
feature with nothing to find teaches nothing. What is in it is `core/demo.py`'s
business; this tab is the two decisions:

    WHERE       a folder of your choosing, inside whatever this copy is allowed
                to touch. Never a path this app picked for you.
    POINT AT IT whether Setup should borrow the boxes while you are practising.

The second one is the part worth being careful about, and it is why there is a
stash: pointing Setup at the sample writes down where your own trees were, and
removing the sample puts them back. Without that, "have a go with the sample"
would end with five paths to retype from memory.

It never overwrites. A file already there is left alone and counted as left
alone, so pressing Build twice costs nothing. And it will only DELETE a folder
carrying the marker it wrote itself - pointing Remove at the real library does
nothing at all, and says why.
"""

from __future__ import annotations

import json
import os

from app.registry import Choice, Flag, Folder, Plan, Result, Row, Task, register
from core import demo, settings as S

# Which Setup boxes the sample borrows, and what it puts in each.
TREES = [("library", demo.LIBRARY), ("raw", demo.RAWTREE),
         ("previews", "Previews"), ("video", "Video"),
         ("develop", "Develop"), ("inbox", demo.INBOX)]


def _root(opts) -> str:
    return str(opts.get("folder") or "").strip()


def _stashed() -> dict:
    try:
        got = json.loads(str(S.load()["demo_stash"] or "") or "{}")
        return got if isinstance(got, dict) else {}
    except ValueError:
        return {}


def plan(opts) -> Plan:
    p = Plan(task="demo", opts=dict(opts))
    root = _root(opts)
    doing = str(opts.get("doing") or "build")
    recipe = demo.recipe()
    # Two of them; the page adds "Where" itself, and a row with a `target` would
    # make it add "From" and "To" as well and slide every value one column over.
    p.columns = ["Folder", "What goes in it"]

    if not root:
        p.blocked = ("Choose a folder to build it in first - somewhere of your "
                     "own, not inside your library. A folder that does not "
                     "exist yet is fine; it is made.")
        return p

    here = demo.present(root)
    if doing == "remove":
        why = demo.removable(root)
        p.stats = [("Folder", root), ("Files in it", f"{here['files']:,}")]
        if why:
            p.blocked = why
            return p
        p.impact = {"verb": "Remove", "unit": "files", "risk": "high",
                    # The rows are folders; the number worth confirming is files.
                    "count": here["files"],
                    "undo": "The sample library is deleted outright - it is not "
                            "put in a pile and it does not go to a recycle bin. "
                            "Nothing of yours is in it, and Build makes another."}
        p.rows = [Row(what="remove", name="The whole sample library",
                      cells=[f"{here['files']:,} files", root])]
        if _stashed():
            p.notes.append("Your own folders go back into Setup when this is "
                           "removed - they were written down when the sample "
                           "was pointed at.")
        return p

    if not demo.have_pillow():
        p.blocked = ("Building photos needs Pillow, which is not installed in "
                     "this copy. Everything else works without it; this is the "
                     "one tool that cannot.")
        return p

    p.stats = [("Folder", root),
               ("Photos", f"{recipe['pictures']:,}"),
               ("Negatives", f"{recipe['negatives']:,}"),
               ("Clips", f"{recipe['clips']:,}")]
    p.notes = list(recipe["notes"])
    p.impact = {"verb": "Build", "unit": "files",
                # One row is a folder. What is being written is files, and that
                # is the number the button should say.
                "count": recipe["files"],
                "undo": "Nothing of yours is touched. Remove it deletes the "
                        "whole sample folder again whenever you like."}
    if here["there"] and here["files"]:
        p.notes.append(f"There is already something in that folder "
                       f"({here['files']:,} files). Nothing in it is "
                       f"overwritten - anything missing is added.")
    for folder in recipe["folders"]:
        n = len([s for s in demo.SHOTS if os.path.dirname(s[0]) == folder])
        raws = len([s for s in demo.SHOTS
                    if s[7].get("raw") and demo._raw_home(s) == folder])
        clips = len([c for c in demo.CLIPS if os.path.dirname(c[0]) == folder])
        what = ", ".join(x for x in [f"{n} photographs" if n else "",
                                     f"{raws} negatives" if raws else "",
                                     f"{clips} clips" if clips else ""] if x)
        p.rows.append(Row(what="build", name=folder, cells=[what, root]))
    if opts.get("point"):
        p.notes.append("Setup will be pointed at the sample while you practise. "
                       "Where your own folders are now is written down first, "
                       "and put back when the sample is removed.")
    return p


def _point_at(root: str) -> None:
    """Borrow the Setup boxes, remembering what was in them."""
    saved = S.load()
    was = {key: str(saved[key] or "") for key, _rel in TREES}
    S.save({"demo_folder": root, "demo_stash": json.dumps(was),
            **{key: os.path.join(root, *rel.split("/")) for key, rel in TREES}})


def _hand_back() -> list:
    """Put the person's own folders back. Says what it restored."""
    was = _stashed()
    if not was:
        S.save({"demo_folder": "", "demo_stash": ""})
        return []
    S.save({"demo_folder": "", "demo_stash": "",
            **{key: was.get(key, "") for key, _rel in TREES}})
    return [key for key, _rel in TREES if was.get(key)]


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    root = _root(plan.opts or {})
    doing = str((plan.opts or {}).get("doing") or "build")

    if doing == "remove":
        out = demo.remove(root)
        if out["why"]:
            result.blame(root, out["why"])
            return result
        result.done = 1
        result.stats = [("Files deleted", f"{out['gone']:,}")]
        back = _hand_back()
        if back:
            result.stats.append(("Your folders put back", ", ".join(back)))
        result.details.append("The sample library is gone. Nothing of yours was "
                              "in it.")
        return result

    out = demo.build(root, progress=progress)
    result.done = len(out["made"])
    for line in out["failed"]:
        result.blame(line.split(":")[0], line)
    result.stats = [("Files written", f"{len(out['made']):,}"),
                    ("Already there", f"{len(out['kept']):,}"),
                    ("Built in", root)]
    if (plan.opts or {}).get("point"):
        _point_at(root)
        result.stats.append(("Setup now points at", root))
        result.details.append(
            "Every tool opens on the sample now. Remove it when you are "
            "finished and your own folders come back.")
    else:
        S.save({"demo_folder": root})
    result.details.append(
        "Start with Library to see what is in it, then Sort into folders on the "
        "Inbox - that is the heap, and it is the thing this app is for.")
    return result


register(Task(
    name="demo",
    line="A small library with real EXIF, to practise every tool on.",
    verb="Build",
    unit="files",
    title="Sample library",
    tab="Sample library",
    parent="setup",
    icon="play",
    order=99,
    summary="Builds a small sample library to try every tool on, without "
            "touching your own photos.",
    options=[
        Folder("folder", "Sample folder", default="", must_exist=False,
               setting="demo_folder",
               help="A folder of your own, outside the library. It does not "
                    "need to exist yet. Everything the sample needs is made "
                    "inside it, and Remove deletes only this folder."),
        Choice("doing", "Build or remove", default="build",
               choices=[("build", "Build the sample"),
                        ("remove", "Remove the sample")],
               help="Build makes the sample. Remove deletes a sample this "
                    "app built. It checks for the marker file the build "
                    "left, and does nothing in any other folder."),
        Flag("point", "Point Setup at it", default=False,
             help="Writes the sample's folders into Setup, so every tool "
                  "opens on the sample. Your own folders are saved first and "
                  "put back when you remove the sample."),
    ],
    plan=plan,
    apply=apply,
    writes=True,
    reads=(),
    copies_to=(),
    moves_to=(),
))
