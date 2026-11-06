"""Back up the app's own state, and put a backup back.

Everything this app knows that cannot be worked out again from the photographs
lives in a handful of files in its config folder, and one of them matters more
than the rest put together:

- **developed.jsonl** - which photographs have been developed. It cannot be
  measured: a developed photo and an undeveloped one look identical in the
  library. Lose it and the next Send to develop copies everything you ever
  finished back onto the tablet.
- settings.json, flows.json, automation.json - every decision you made in Setup,
  the flows, whether automation is on.
- reclaimed.jsonl and runs.jsonl - what has been done, and what it gave back.
- the imported timeline and place names - re-importable, but only if you still
  have the export you imported them from.

What is NOT in a backup, on purpose:

- the caches (facts, the library survey) - rebuilt on the next look, and large;
- **the password file**. It holds the hash and the signing secret, and a backup
  is exactly the kind of file that gets copied somewhere less careful than the
  NAS. After a restore the password is whatever it is now - set it again in
  Setup > Password if you need to.

A backup is a zip in the config folder's `backups` folder, named by date, and
the last twenty are kept. It is plain files: open one on a PC and every line
can be read. Restoring takes a backup of the current state FIRST, so a restore
can itself be undone.
"""

from __future__ import annotations

import os
import time
import zipfile

from app.registry import Choice, FilePath, Plan, Result, Row, Task, register
from core.store import data_dir

FOLDER = "backups"
KEEP = 20

# (file, what it is) - the order they are listed in the plan
KEPT = [
    ("developed.jsonl", "which photos are developed - cannot be worked out again"),
    ("settings.json", "everything set in Setup"),
    ("flows.json", "the flows"),
    ("automation.json", "whether automation is on, and its last passes"),
    ("reclaimed.jsonl", "the space given back, ever"),
    ("runs.jsonl", "the run history"),
    ("timeline.tsv", "the imported Google Timeline"),
    ("places.tsv", "the imported place names"),
    ("recent.json", "folders you used recently"),
    ("quicktags.json", "tags used recently in the viewer"),
]
NEVER = ("access.json",)

WHAT = [
    ("backup", "Back up now"),
    ("restore", "Restore a backup"),
]


def _folder() -> str:
    return os.path.join(data_dir(), FOLDER)


def _backups() -> list:
    where = _folder()
    if not os.path.isdir(where):
        return []
    out = [os.path.join(where, n) for n in os.listdir(where)
           if n.startswith("photo-manager-") and n.endswith(".zip")]
    return sorted(out, reverse=True)


def _size(n: int) -> str:
    return f"{n / 1e6:,.1f} MB" if n >= 1e6 else f"{n / 1e3:,.0f} KB"


def make_backup(label: str = "") -> tuple:
    """Write one backup. (path, files in it). Never includes the password file."""
    os.makedirs(_folder(), exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = f"photo-manager-{stamp}{('-' + label) if label else ''}.zip"
    where = os.path.join(_folder(), name)
    n = 1
    while os.path.exists(where):
        where = os.path.join(_folder(), name.replace(".zip", f"-{n}.zip"))
        n += 1
    count = 0
    home = data_dir()
    with zipfile.ZipFile(where + ".part", "w", zipfile.ZIP_DEFLATED) as z:
        for file, _what in KEPT:
            src = os.path.join(home, file)
            if os.path.isfile(src):
                z.write(src, file)
                count += 1
        z.writestr("README.txt",
                   "A backup of Photo Manager's own state, made "
                   + time.strftime("%d %b %Y %H:%M") + ".\n"
                   "Restore it from Setup > Backup. The password is not in "
                   "here, on purpose.\n")
    os.replace(where + ".part", where)
    for old in _backups()[KEEP:]:
        try:
            os.remove(old)
        except OSError:
            pass
    return where, count


def plan(opts) -> Plan:
    p = Plan(task="backup")
    what = str(opts.get("what") or "backup")
    home = data_dir()
    have = _backups()
    p.stats = [("Backups kept", f"{len(have):,} (the last {KEEP})"),
               ("Newest", time.strftime("%d %b %Y %H:%M",
                                         time.localtime(os.path.getmtime(have[0])))
                if have else "none yet")]
    p.columns = ["File", "What it is", "Size"]

    if what == "backup":
        for file, meaning in KEPT:
            src = os.path.join(home, file)
            if not os.path.isfile(src):
                continue
            size = os.path.getsize(src)
            p.rows.append(Row(what="file", name=file, source=src, target="",
                              size=size, detail=meaning,
                              cells=[meaning, _size(size)],
                              data={"backup": True}))
        if not p.rows:
            p.blocked = "There is nothing to back up yet - nothing has been set up."
            return p
        p.notes.append(
            "The password file is left out on purpose: a backup is the kind of "
            "file that gets copied somewhere less careful than the NAS.")
        p.notes.append(f"Written to the 'backups' folder inside {home}. It is a "
                       f"plain zip - copy it off the NAS with File Station.")
        return p

    source = str(opts.get("source") or "").strip() or (have[0] if have else "")
    if not source or not os.path.isfile(source):
        p.blocked = "There is no backup to restore from yet."
        return p
    try:
        with zipfile.ZipFile(source) as z:
            names = set(z.namelist())
            sizes = {i.filename: i.file_size for i in z.infolist()}
    except (OSError, zipfile.BadZipFile) as exc:
        p.blocked = f"That is not a backup this app can read: {exc}"
        return p
    known = dict(KEPT)
    for name in sorted(names):
        if name in NEVER or name not in known:
            continue
        here = os.path.join(home, name)
        p.rows.append(Row(
            what="file", name=name, source=source, target=here,
            size=sizes.get(name, 0),
            detail=("replaces the current one" if os.path.exists(here)
                    else "comes back"),
            cells=[known[name], _size(sizes.get(name, 0))],
            data={"restore": True, "zip": source, "name": name}))
    if not p.rows:
        p.blocked = "That backup has nothing in it this app keeps."
        return p
    p.notes.insert(0, (
        "A backup of how things are NOW is taken first, so this restore can "
        "itself be undone. The password is not touched."))
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    if any(r.data.get("backup") for r in plan.rows):
        try:
            where, count = make_backup()
            result.done = count
            result.details.append(f"Backed up {count} file(s) to {where}")
        except Exception as exc:                        # noqa: BLE001
            result.blame("backup", exc)
        result.stats = [("Files backed up", f"{result.done:,}")]
        return result

    # A restore: the current state first, so this can be undone.
    try:
        safety, _n = make_backup("before-restore")
        result.details.append(f"The state before this restore is in {safety}")
    except Exception as exc:                            # noqa: BLE001
        result.blame("the safety backup", exc)
        result.details.append("Nothing was restored, because the current state "
                              "could not be backed up first.")
        return result
    home = data_dir()
    for i, row in enumerate(plan.rows, 1):
        status = "OK"
        try:
            with zipfile.ZipFile(row.data["zip"]) as z:
                data = z.read(row.data["name"])
            tmp = os.path.join(home, row.data["name"] + ".restoring")
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, os.path.join(home, row.data["name"]))
            result.done += 1
        except Exception as exc:                        # noqa: BLE001
            status = result.blame(row.name, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)
    result.stats = [("Files restored", f"{result.done:,}"),
                    ("Failed", f"{result.failed:,}")]
    return result


register(Task(
    name="backup",
    line="Keep the app's own state, and put a backup back.",
    verb="Back up",
    unit="files",
    title="Backup",
    parent="setup",
    tab="Backup",
    summary="Backs up the app's settings, flows and developed list to a zip "
            "file, and restores one.",
    icon="download",
    order=97,
    options=[
        Choice("what", "What to do", default="backup", choices=WHAT, tabs=True,
               help="Back up writes a zip file into the config folder. "
                    "Restore puts one back. The current state is backed up "
                    "first, so a restore can be undone."),
        FilePath("source", "Backup to restore", default="",
                 suffixes=(".zip",), only_when="what=restore",
                 help="The zip file to restore. Blank restores the newest "
                      "backup. Browse to pick an older one, or one you "
                      "copied back onto the NAS."),
    ],
    plan=plan,
    apply=apply,
))
