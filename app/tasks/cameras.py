"""Camera names - what each body is called, against the code it writes.

A GH4 writes `DMC-GH4` and an A7C writes `ILCE-7C`. You learn those. A phone
writes `SM-G991B`, or `iPhone14,2` - order codes, not names - and a library with
three phones in it draws a chart whose legend is three strings nobody can tell
apart.

This tab lists every camera the library actually contains, biggest first, and
lets you call each one whatever you call it out loud. What you type wins
everywhere: charts, menus, the viewer, the Compare grid.

Where you have not typed anything, the app fills in a name if it happens to
recognise the code - and says it is a **guess**, with the code beside it,
because a table written from memory is wrong sooner or later and a wrong name
that looks authoritative costs an hour.

**Nothing is written to a photograph.** The file keeps saying what the camera
made it say. Searching by the code still works, and so does searching by the
name you gave it.
"""

from __future__ import annotations

import os

from app.registry import Folders, Plan, Result, Row, Task, register
from core import devices
from core import settings as S
from core import stats as ST


def _folders(opts) -> list:
    out = [line.strip() for line in str(opts.get("folders") or "").splitlines()
           if line.strip()]
    if not out:
        out = [str(S.load()["library"] or "").strip()]
    return [f for f in out if f and os.path.isdir(f)]


def plan(opts, progress=None) -> Plan:
    p = Plan(task="cameras")
    folders = _folders(opts)
    if not folders:
        p.blocked = "Fill in the library on Setup, or name a folder to look in."
        return p

    mine = devices.saved()
    got = ST.values(folders, "camera", progress=progress)
    seen = set()
    p.columns = ["What the file says", "Called", "Where the name came from",
                 "Photos"]
    for row in got["values"]:
        model = row["name"]
        # the buckets arrive already named - the code is what is in brackets
        code = (model[model.rfind("(") + 1:-1]
                if model.endswith(")") and "(" in model else model)
        seen.add(devices._key(code))
        how = devices.how(code, mine)
        p.rows.append(Row(
            what="camera", name=code, source="",
            detail=devices.name_of(code, mine),
            cells=[devices.name_of(code, mine),
                   {"yours": "you named it",
                    "guessed": "a guess by this app"}.get(how,
                                                          "the code itself"),
                   f"{row['photos']:,}"],
            data={"model": code, "name": devices.name_of(code, mine),
                  "how": how}))

    # names kept for cameras that are not in the library any anymore: shown so
    # they can be cleared rather than sitting in the settings for ever
    for code, name in sorted(mine.items()):
        if code in seen:
            continue
        p.rows.append(Row(
            what="camera", name=code, source="", detail=name,
            cells=[name, "you named it - nothing in the library uses it now",
                   "0"],
            data={"model": code, "name": name, "how": "yours"}))

    p.stats = [("Cameras in the library", f"{len(got['values']):,}"),
               ("Named by you", f"{len(mine):,}"),
               ("Photos read", f"{got['photos']:,}"),
               ("Files opened", got["read"])]
    p.notes.append("Type a name beside any of them above. It is a display name "
                   "- nothing is written to a photo, and searching by the "
                   "code still works.")
    p.notes.append("A guess comes from a short table written into this app from "
                   "memory. It is far from complete and it can be wrong, which "
                   "is why the code is always shown beside it. Your own name "
                   "replaces it.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    return Result(details=["This tab only lists. The names are saved as you "
                           "type them."])


register(Task(
    name="cameras",
    reads=("library",),
    title="Camera names",
    summary="Gives each camera a name to show instead of the model code it "
            "writes into files.",
    icon="image",
    parent="setup",
    tab="Camera names",
    editor="cameras",
    order=94,
    writes=False,
    options=[
        Folders("folders", "Folders to read", default="", setting="library",
                help="The folders to read camera codes from. Blank means the "
                     "library from Setup."),
    ],
    plan=plan,
    apply=apply,
))
