"""Reindex - telling Synology that the files moved.

DSM keeps its own databases of what is on the disk - Media Indexing for Media
Server and DLNA, and a separate one inside Synology Photos - and neither of them
is the filesystem. Move a shoot with this app and it is on the disk instantly
and missing from Synology Photos until something says so. Not a bug in either
program: they are indexes, and an index that is not told is out of date.

**Only the folders that actually changed.** Every run of every task adds what it
touched to a queue - both ends of every move, because an index told about the
new folder still shows photographs in the old one. Re-indexing those costs
seconds; re-indexing a library takes hours, which is why nobody does it and why
Synology Photos stays wrong for weeks.

**Where this app runs is the awkward part.** The indexers are on the DSM host
and this app is in a container that mounts one home folder. A container cannot
call a program that is not inside it. So the tools are looked for, and:

- **found** - they are run here, folder by folder, and each result is reported;
- **not found** - a script holding exactly those commands is written for DSM's
  own Task Scheduler to run, as root, on a schedule or on demand.

No SSH out of the container, no stored credentials, nothing that could leak. The
script is plain text you can read before you run it.

**Synology Photos is all or nothing.** Its re-index API takes no folder, so that
part of the script covers the whole space and is slow. It is written separately
so it can be dropped, or scheduled less often than the rest.
"""

from __future__ import annotations

import os

from app.registry import Flag, Folder, Option, Plan, Result, Row, Task, register
from core import reindex

SCRIPT = "reindex.sh"


def plan(opts) -> Plan:
    p = Plan(task="reindex")
    waiting = reindex.settle(reindex.queued())
    raw_queue = reindex.queued()
    tools = reindex.available()
    user = str(opts.get("user") or "").strip()
    personal = bool(opts.get("personal"))
    where = str(opts.get("script_into") or "").strip()
    also_photos = bool(opts.get("photos"))

    p.columns = ["Folder", "What would be told", "How"]
    p.stats = [
        ("Folders waiting", f"{len(waiting):,}"),
        ("  queued by tools", f"{len(raw_queue):,}"),
        ("Media Indexing tool", tools["synoindex"] or "not reachable from here"),
        ("Synology Photos tool", tools["synowebapi"] or "not reachable from here"),
    ]

    if tools["synoindex"]:
        for folder in waiting:
            p.rows.append(Row(
                what="index", name=os.path.basename(folder) or folder,
                source=folder, target="",
                detail="Media Indexing will be told to read this folder again",
                cells=["Media Indexing", "run from here"],
                data={"folder": folder}))
        if also_photos and tools["synowebapi"] and user:
            p.rows.append(Row(
                what="photos", name="Synology Photos", source="the whole space",
                target="",
                detail="Synology Photos re-index - its API takes no folder, so "
                       "this covers everything and is slow",
                cells=["Synology Photos", "run from here"],
                data={"photos": True}))
        p.notes.insert(0, "The DSM tools are reachable from here, so this can do "
                          "it itself - no script and no Task Scheduler needed.")
    else:
        # The normal case: a container cannot call a program on the host.
        if not where:
            p.blocked = (
                "The DSM indexers are not reachable from here - which is normal, "
                "because they live on the NAS itself and this app is in a "
                "container. Give a folder inside your library to write a small "
                "script into, and DSM's Task Scheduler can run it as root.")
            return p
        target = os.path.join(where, SCRIPT)
        p.rows.append(Row(
            what="script", name=SCRIPT, source=f"{len(waiting)} folder(s) queued",
            target=target,
            detail="a script holding exactly the folders that changed, for DSM's "
                   "Task Scheduler to run",
            cells=["a script for DSM", "written here, run there"],
            data={"script": target, "folders": waiting}))
        p.notes.insert(0,
                       "The DSM indexers are not reachable from inside this "
                       "container, so this writes the commands out instead of "
                       "running them. That is the whole difference: the script "
                       "below is exactly what would have been run.")

    if not waiting:
        p.notes.append("Nothing has changed since the last time, so there is "
                       "nothing DSM needs to be told. Running it anyway is safe "
                       "and does nothing.")
    else:
        p.notes.append(
            f"{len(waiting)} folder(s) are queued - both ends of every move this "
            f"app made. An index told about the new folder and not the old one "
            f"still lists photos that are no longer there.")
    if also_photos and not user:
        p.notes.append("Synology Photos needs your DSM username to re-index - it "
                       "runs the command as root but wants to know whose library "
                       "it is. Without it, only Media Indexing is covered.")
    if len(raw_queue) > len(waiting):
        p.notes.append(
            f"{len(raw_queue) - len(waiting)} of the queued folders are gone or "
            f"sit inside another one on the list. A folder that was emptied and "
            f"tidied away cannot be re-read - its PARENT is told instead, which "
            f"is what makes the index drop what is no longer there.")
    p.notes.append(
        "The paths in the script are the ones this app sees. That works because "
        "the library is mounted into the container at its own path rather than "
        "at an invented one - which was the point of setting it up that way.")
    p.notes.append(
        "Media Indexing covers Media Server, DLNA and Photo Station, and takes "
        "one folder at a time. Synology Photos keeps a separate database whose "
        "re-index takes no folder at all, so it is the whole space or nothing.")
    p.notes.append(
        "Synology Drive is not covered by either: it has no re-index command "
        "that could be found. It watches the filesystem itself, and the usual "
        "fix for a folder it has missed is Drive Admin Console > Sync Profile, "
        "or pausing and resuming that share.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result

    tools = reindex.available()
    told = 0
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        status = "OK"
        try:
            if "script" in row.data:
                where = row.data["script"]
                text = reindex.script(
                    row.data.get("folders") or [],
                    str((plan.opts or {}).get("user") or "").strip()
                    if (plan.opts or {}).get("photos") else "",
                    bool((plan.opts or {}).get("personal")),
                    where)
                os.makedirs(os.path.dirname(where) or ".", exist_ok=True)
                with open(where, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
                try:
                    os.chmod(where, 0o755)
                except OSError:
                    pass
                # DSM's Task Scheduler runs this as root, but you have to be
                # able to READ it in File Station first - that is the whole
                # point of writing it out rather than running it.
                from core import perms
                perms.like_parent(where)
                result.done += 1
            elif row.data.get("photos"):
                ok, said = reindex.run(reindex.photos_command(
                    str((plan.opts or {}).get("user") or "").strip(),
                    bool((plan.opts or {}).get("personal")),
                    tools["synowebapi"] or "synowebapi"))
                if not ok:
                    raise RuntimeError(said or "it refused")
                result.done += 1
            else:
                ok, said = reindex.run(reindex.index_command(
                    row.data["folder"], tools["synoindex"] or "synoindex"))
                if not ok:
                    raise RuntimeError(said or "it refused")
                told += 1
                result.done += 1
        except Exception as exc:                    # noqa: BLE001
            status = result.blame(row.name, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)

    wrote_script = any("script" in r.data for r in plan.rows)
    if not result.failed and not result.cancelled:
        # Only when it actually happened. Clearing the queue because a SCRIPT was
        # written would throw away the list before anything had been told - the
        # script has its own copy, but the next run would then write an empty one
        # and the folders would be waiting nowhere.
        if not wrote_script:
            reindex.clear()
            result.details.append(
                f"{told} folder(s) re-indexed and the queue is empty.")
        else:
            where = [r.data["script"] for r in plan.rows if "script" in r.data][0]
            result.details.append(
                f"Written to {where}. Run it on the NAS - DSM > Control Panel > "
                f"Task Scheduler > Create > Scheduled Task > User-defined script, "
                f"user root, command:  bash \"{where}\"")
            result.details.append(
                "The queue is kept until the tools are run from here, so the next "
                "script still holds these folders as well as any new ones. Tick "
                "'forget them' once the schedule is working.")
            if (plan.opts or {}).get("forget"):
                reindex.clear()
                result.details.append("The queue has been emptied, as asked.")
    result.stats = [("Folders told about", f"{told:,}"),
                    ("Script written", "yes" if wrote_script else "no"),
                    ("Failed", f"{result.failed:,}")]
    return result


register(Task(
    name="reindex",
    line="Tell the NAS's own apps, Photos and File Station, that these "
         "folders changed.",
    verb="Reindex",
    unit="folders",
    reads=('library',),
    title="Reindex",
    summary="Tells DSM which folders changed, so Synology Photos and Media "
            "Server show the current library.",
    icon="refresh",
    parent="setup",
    tab="Reindex",
    order=92,
    options=[
        Folder("script_into", "Script folder", default="",
               must_exist=False, setting="library",
               help="Where the re-index script is written, when DSM's tools "
                    "cannot be reached from here, which is normal in a "
                    "container. Choose a folder you can see in File Station. "
                    "The library root is fine."),
        Flag("photos", "Include Synology Photos", default=True,
             help="Also re-indexes Synology Photos. That re-index covers the "
                  "whole space and is the slow part. Media indexing for "
                  "Media Server, DLNA and Photo Station is per folder and "
                  "quick. On by default."),
        Option("user", "DSM username", default="", kind="text",
               help="The DSM user whose Synology Photos library is "
                    "re-indexed. The re-index runs as root, so it needs the "
                    "name. It is stored only in the script this writes."),
        Flag("personal", "Personal space",
             default=False, advanced=True,
             help="Re-indexes your personal space in Synology Photos. Off "
                  "re-indexes the shared space. The two are separate "
                  "libraries."),
        Flag("forget", "Empty the queue", default=False,
             advanced=True,
             help="Clears the list of changed folders after the script is "
                  "written. Off by default: the next script is built from "
                  "that list. Clear it only once you have seen DSM's Task "
                  "Scheduler run it on the NAS."),
    ],
    plan=plan,
    apply=apply,
))
