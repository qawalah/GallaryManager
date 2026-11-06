"""Is everything set up? One list, each line fine or not, and what to do.

The app works on a NAS it cannot see the whole of: a mount that did not happen,
a tree never set, a repair job never scheduled - each of those is quiet until a
feature trips over it. So this is the first thing a new install opens, and the
page to come back to when something behaves oddly.

Every line is measured, not assumed: the folder is looked at, a real folder is
made and removed to prove writing works, the repair job's own mark is read.
Nothing here changes anything.
"""

from __future__ import annotations

import os
import time

from app.registry import Flag, Plan, Result, Row, Task, register
from core import access, acl, perms
from core import settings as S
from core.store import store_path

OK, WARN, BAD = "ok", "warn", "bad"
MARK = {OK: "✓ Fine", WARN: "! Worth a look", BAD: "✗ Needs doing"}

TREES = [("library", "The library", True), ("raw", "The RAW tree", False),
         ("previews", "The previews tree", False),
         ("video", "The video tree", False)]


def _ago(seconds) -> str:
    from app.tasks.permissions import _when
    return _when(seconds)


def checks(try_writing: bool = True) -> list:
    """(what, state, says, where to fix it) for every line."""
    from core import desktop
    on_pc = desktop.as_program()
    saved = S.load()
    out = []
    for key, label, needed in TREES:
        root = str(saved[key] or "").strip()
        if not root:
            out.append((label, BAD if needed else WARN,
                        "not set" + ("" if needed else " - tools that use it are off"),
                        "Setup"))
            continue
        if not os.path.isdir(root):
            out.append((label, BAD, "set, but not there - is it mounted?", "Setup"))
            continue
        if not try_writing:
            out.append((label, OK, "there", ""))
            continue
        yes, why = perms.can_write(root)
        out.append((label, OK if yes else BAD,
                    "there, and writable" if yes else f"cannot write: {why}",
                    "" if yes or on_pc else "Permissions"))

    if not on_pc:
        out.append(_repair_line())

    if access.from_environment():
        out.append(("Password", OK, "set by the container (PM_PASSWORD)", ""))
    elif access.is_on():
        out.append(("Password", OK, "set", ""))
    else:
        out.append(("Password", WARN, "none - anyone on the network can open it",
                    "Password"))

    from core import timeline
    tl = timeline.store_info(store_path("timeline.tsv"))
    out.append(("Google Timeline", OK if tl.ok else WARN,
                f"{tl.count:,} points, up to {tl.last[:10]}" if tl.ok
                else "not imported - Geotag has nothing to match against",
                "" if tl.ok else "Geotag"))
    places = os.path.isfile(store_path("places.tsv"))
    out.append(("Place names", OK if places else WARN,
                "imported" if places else "not imported - folders get no place name",
                "" if places else "Sort into folders"))

    named = [c for c in ("red", "yellow", "green", "blue", "purple")
             if str(saved.values.get(f"label_{c}_name") or "").strip()]
    out.append(("Colour meanings", OK if named else WARN,
                f"{len(named)} of 5 colours named", "" if named else "Colour meanings"))

    try:
        import PIL
        out.append(("Pillow", OK, f"version {PIL.__version__}", ""))
    except ImportError:
        out.append(("Pillow", BAD, "missing - previews and blur cannot work", ""))
    from core import heif
    reader = heif.decoder()
    out.append(("HEIC reader", OK if reader else WARN,
                reader or "missing - HEIC photos get no thumbnails", ""))

    line = _index_line()
    if line:
        out.append(line)

    from app.tasks.backup import _backups
    have = _backups()
    if not have:
        out.append(("Backup", WARN, "none yet", "Backup"))
    else:
        age = os.path.getmtime(have[0])
        old = time.time() - age > 30 * 86400
        out.append(("Backup", WARN if old else OK, f"newest {_ago(age)}",
                    "Backup" if old else ""))
    return out


def _repair_line() -> tuple:
    """The permissions job's line. NAS only: on a PC there is no job, no DSM
    and no Synology Drive waiting on it, so a line saying it "has never run"
    would warn about something that never will, every time you looked. A PC
    can still run Permissions by hand from the command line."""
    run = acl.last_run()
    waiting = len(acl.waiting())
    if not run:
        return ("Repair job", WARN if not waiting else BAD,
                "has never run" + (f" - {waiting} folder(s) waiting" if waiting else ""),
                "Permissions")
    late = time.time() - run["when"] > 3 * 3600 and waiting
    return ("Repair job", WARN if late else OK,
            f"last ran {_ago(run['when'])}"
            + (f", {waiting} folder(s) waiting" if waiting else ""),
            "Permissions" if late else "")


def unreadable_said(count: int, names: list, show: int = 3) -> str:
    """"2 files could not be read: a.JPG (why), b.JPG (why)" - or ""."""
    if not count:
        return ""
    said = f"{count:,} file{'' if count == 1 else 's'} could not be read"
    named = [f"{os.path.basename(str(n.get('path') or ''))} ({n.get('error') or '?'})"
             for n in (names or [])[:show]]
    if named:
        said += ": " + ", ".join(named)
        if count > len(named):
            said += ", ..."
    return said


def _index_line():
    """The index, once it has been built: whether every file in it was read.

    A file the index could not read is missing from Photos, the counts and the
    map - and nothing else on the page says so, because a photograph that is
    not there leaves no gap to notice.
    """
    from core import catalogue
    try:
        state = catalogue.shared().state()
    except Exception:                                  # noqa: BLE001
        return None
    if not state.get("ready"):
        return None
    count = int(state.get("unreadable") or 0)
    if not count:
        return ("Library index", OK,
                f"{int(state.get('photos') or 0):,} files, every one read", "")
    return ("Library index", WARN,
            unreadable_said(count, state.get("unreadable_names") or []), "")


def first_run() -> bool:
    """No library set: nothing can work yet, so this is where to start."""
    return not str(S.load()["library"] or "").strip()


def plan(opts) -> Plan:
    p = Plan(task="checklist")
    lines = checks(bool(opts.get("try_writing", True)))
    p.columns = ["Check", "State", "What it says", "Fix it in"]
    for what, state, says, where in lines:
        p.rows.append(Row(what=state, name=what, source="", target="",
                          detail=says, cells=[MARK[state], says, where],
                          data={"state": state}))
    bad = sum(1 for l in lines if l[1] == BAD)
    warn = sum(1 for l in lines if l[1] == WARN)
    p.stats = [("Fine", f"{len(lines) - bad - warn}"),
               ("Worth a look", f"{warn}"), ("Needs doing", f"{bad}")]
    if first_run():
        p.notes.append("Start here: set the library in Setup, then come back.")
        # And the other way in, for somebody who does not want to point this at
        # four hundred real photographs on its first run - which is a perfectly
        # sensible thing not to want.
        p.notes.append("Or build the sample library first (Setup, Sample "
                       "library) and try every tool on that instead.")
    p.notes.append("Measured now. Nothing is changed.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    return Result(details=["This tab only reports. Nothing was written."])


register(Task(
    name="checklist",
    title="Checklist",
    parent="setup",
    tab="Checklist",
    summary="Checks that every part of the setup works, and says where to "
            "fix each problem.",
    icon="check",
    order=98,
    writes=False,
    options=[
        Flag("try_writing", "Try writing", default=True,
             help="Makes a folder in each tree and removes it again, to "
                  "prove the app can write there. Off only checks that the "
                  "folders exist. On by default."),
    ],
    plan=plan,
    apply=apply,
))
