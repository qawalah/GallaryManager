"""Are new folders coming out right on YOUR NAS - measured, not argued.

The fault this exists for is silent at both ends. This app creates a folder,
every file lands in it correctly, nothing fails and nothing is logged - and
Synology Drive, which reads the library as YOU rather than as this app, stops
seeing a tree it cannot read and says nothing either. The only symptom is a
folder that never turns up on the laptop, and the only cure anybody finds is
File Station > Properties > Permission > Advanced options > Make inherited
permissions explicit.

**It was half fixed, and the missing half was the half that matters.** Owner,
group and mode were being carried onto every folder this app made. The extended
attributes were not - and on DSM the extended attribute is where the access list
lives, which is what File Station, Drive and Photos all actually go by. So a new
shoot folder had the right owner and no access list at all, which is precisely
the state that "make inherited explicit" cures.

**Why this tab exists rather than a claim in a docstring.** That fix cannot be
tested from here. The access list is DSM's, the filesystem is DSM's, and the
only machine where the answer means anything is the one with the photographs on
it. So this makes a real folder in your library exactly the way every task
makes one, compares it attribute by attribute with the folder it was made
inside, says what differs, and removes it. It does not need to know which
attribute holds the access list, because it compares all of them.

**And the part that could not be done from in here at all.** DSM keeps its
access list in a PRIVILEGED extended attribute. A normal user cannot write one -
the kernel says "Operation not permitted" and that is the end of it - and
running this app as your own user is the right arrangement for everything else.
So the app stopped pretending: every folder it creates that it could not finish
goes on a short list, and a job in DSM's Task Scheduler, running as root, works
from that list and puts exactly those folders right. Set up once; after that
this tab is where you see that it is still happening.
"""

from __future__ import annotations

import os

from app.registry import Flag, Folder, Plan, Result, Row, Task, register
from core import acl, perms
from core import settings as S
from core.store import store_path

SCRIPT = acl.SCRIPT

TREES = [("library", "The library"), ("raw", "The RAW tree"),
         ("previews", "The previews tree"), ("video", "The video tree"),
         ("develop", "The develop tree")]


def _when(seconds) -> str:
    """"four minutes ago", because an epoch on a screen is not an answer."""
    import time
    gap = max(0, int(time.time() - float(seconds)))
    if gap < 90:
        return "just now"
    if gap < 3600:
        n = gap // 60
        return f"{n} minute{'s' if n != 1 else ''} ago"
    if gap < 86400:
        n = gap // 3600
        return f"{n} hour{'s' if n != 1 else ''} ago"
    n = gap // 86400
    return f"{n} day{'s' if n != 1 else ''} ago"


def plan(opts) -> Plan:
    p = Plan(task="permissions")
    saved = S.load()
    check = [str(saved[key] or "").strip() for key, _label in TREES]
    check = [x for x in check if x and os.path.isdir(x)]
    one = (opts.get("folder") or "").strip()
    if one and os.path.isdir(one) and one not in check:
        check.insert(0, one)
    if not check:
        p.blocked = ("No trees are set up yet, so there is nothing to check. "
                     "Setup is where the library goes.")
        return p

    # Whether the access list is this app's business at all on this machine.
    # With DSM's tool reachable a new folder is finished at birth and anything
    # missing IS a fault. Without it, a new folder is left blank ON PURPOSE -
    # see perms.like_parent - and a missing list is the design, not the bug.
    by_dsm = bool(perms.dsm_tool())
    p.columns = ["Tree", "What came out", "Owner", "Mode", "Access list"]
    wrong = 0
    refusals = {}
    shut_out = []
    for folder in check:
        got = perms.try_a_folder(folder)
        if not got["made"]:
            wrong += 1
            owner, group = perms.owner_of(folder)
            shut_out.append((folder, got["why"], owner, group))
            p.rows.append(Row(
                what="tree", name=folder, source=folder, target="",
                detail=got["why"] or "a folder could not be created here",
                cells=["CANNOT WRITE HERE",
                       f"uid {owner} gid {group}" if owner is not None else "-",
                       "-", got["why"]],
                data={"folder": folder, "shut_out": True}))
            continue
        for name, why in got["refused"]:
            refusals.setdefault(why, set()).add(name)
        diff = got["compare"]
        named = [d[0] if isinstance(d, tuple) else d for d in diff["different"]]
        missing = list(diff["only_parent"])
        owner_ok = "owner" not in named and "group" not in named
        mode_ok = "mode" not in named
        # Whatever holds the access list is an extended attribute, and this does
        # not need to know which one: anything the parent has and the new folder
        # does not is a thing that would not have been inherited.
        adrift = missing or [x for x in named if "." in x]
        if not adrift:
            access = "the same as its parent"
        elif by_dsm:
            access = "NOT CARRIED: " + ", ".join(adrift)
        else:
            access = "left for the repair job"
        bad = bool((adrift and by_dsm) or not owner_ok or not mode_ok)
        if bad:
            wrong += 1
        p.rows.append(Row(
            what="tree", name=folder, source=folder, target="",
            approximate=bool(adrift and not by_dsm),
            detail=("a folder made here comes out "
                    + ("exactly like the one above it" if not bad
                       else "DIFFERENT from the one above it")),
            cells=["made and removed",
                   "same" if owner_ok else "DIFFERENT",
                   "same" if mode_ok else "DIFFERENT", access],
            data={"folder": folder, "missing": missing}))
        if not got["removed"]:
            p.errors.append(f"could not remove the test folder {got['folder']}")

    tool = perms.dsm_tool()
    uid, _gid = perms.writes_as()
    waiting = acl.waiting()
    ran = acl.last_run()
    p.stats = [
        ("Trees checked", f"{len(p.rows):,}"),
        ("Cannot write into", f"{len(shut_out):,}"),
        ("Coming out wrong", f"{wrong:,}"),
        ("Folders waiting", f"{len(waiting):,}"),
        ("Repair job", (f"last ran {_when(ran['when'])}, put {ran['fixed']:,} "
                        f"right" + (f", {ran['failed']:,} it could not"
                                    if ran.get("failed") else ""))
         if ran else "has never run"),
        ("This app writes as", "uid {} gid {}".format(uid, _gid)),
        ("DSM's synoacltool", tool or "not reachable from in here"),
    ]

    # ------------------------------------------------ what it all means, once
    #
    # Ownership comes FIRST when it is wrong, because it is the bigger fault by
    # a long way: a missing access list makes Synology Drive quietly stop
    # syncing, and a tree this app cannot write into makes every task fail on
    # every file in it. That is what "156 x Permission denied" is.
    if wrong:
        p.notes.insert(0, (
            "A folder made here does NOT come out like the one above it - which "
            "is exactly what makes Synology Drive stop seeing new folders "
            "without either of them saying anything."))
        for why, names in sorted(refusals.items()):
            p.notes.insert(1, (
                f"This app could not write {', '.join(sorted(names))}: "
                f"\"{why}\". That is where DSM keeps the access list, and "
                f"writing one needs root. Nothing in here can try harder at it."))
    elif by_dsm:
        p.notes.insert(0, (
            "A folder made here comes out exactly like the one it was made "
            "inside, DSM's own tool having given it its access list at the "
            "moment it was created. MEASURED just now, by making a real folder "
            "and comparing it."))
    else:
        p.notes.insert(0, (
            "Owner and mode come out right, and the access list is left EMPTY "
            "on purpose - that is not a fault. This app used to copy the "
            "parent's list across, and the copy was worse than nothing: "
            "synoacltool repairs a blank folder and SKIPS one that already has "
            "a list, so the copy quietly blocked the repair. Blank, plus the "
            "job below, is the arrangement that works."))

    if not perms.CAN_XATTR:
        p.notes.append(
            "This machine has no extended attributes at all, so there is no "
            "access list to carry and nothing here applies. That is a PC, not a "
            "Synology.")

    # ------------------------------------------------- and what to do about it
    if waiting:
        p.notes.append(
            f"{len(waiting):,} folder{'s' if len(waiting) != 1 else ''} made by "
            f"this app {'are' if len(waiting) != 1 else 'is'} on the list, "
            + ("waiting for the next run of the job." if ran else
               "and nothing has come to fix them yet."))
    elif ran:
        p.notes.append(
            "Nothing is waiting. Every folder made since the job last ran either "
            "came out right or has already been put right.")

    if wrong or waiting or not ran:
        p.notes.append(
            "TWO WAYS, and you only need one. Either let DSM do it on a "
            "schedule - tick the box, read the job, add it once in Task "
            "Scheduler as root, every 5 minutes - or give this app the tool "
            "itself, and it stops needing a schedule at all.")
    if not tool:
        p.notes.append(
            "To do it without a schedule: mount DSM's tool into the container "
            "read-only (/usr/syno/bin:/usr/syno/bin:ro) and run it as root. "
            "Then every folder is put right the moment it is made, and this tab "
            "will say the tool is reachable.")
    elif uid != 0:
        p.notes.append(
            f"DSM's tool is reachable ({tool}), but this app is not root, so it "
            f"cannot use it. Run the container as root and the whole schedule "
            f"becomes unnecessary - owners are still taken from the folder "
            f"above, so nothing ends up belonging to root.")
    else:
        p.notes.append(
            f"DSM's tool is reachable ({tool}) and this app is root, so it can "
            f"do the job itself - no schedule needed.")

    if opts.get("repair"):
        where = store_path(SCRIPT)
        p.rows.append(Row(
            what="script", name=os.path.basename(where), source="", target=where,
            detail="the repair job, for DSM's Task Scheduler to run as root",
            cells=["to write", "-", "-", "set it up once, then forget it"],
            data={"script": where, "folders": list(check),
                  "as": list(perms.writes_as())}))
        p.notes.append(
            "The script is plain text - read it before you run it. It finds its "
            "list beside itself, so it does not matter that DSM and this app "
            "call the same folder by different names. Nothing in it moves, "
            "deletes or rewrites a photo.")

    if waiting and tool and uid == 0:
        p.rows.append(Row(
            what="queue", name=f"{len(waiting):,} waiting folders",
            source="", target="",
            detail="put them right from in here - this app is root and the tool "
                   "is reachable",
            cells=["to fix now", "-", "-", "and clear the list"],
            data={"queue": list(waiting), "tool": tool}))
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    for i, row in enumerate(plan.rows, 1):
        status = "OK"
        if "script" in row.data:
            try:
                where = row.data["script"]
                os.makedirs(os.path.dirname(where) or ".", exist_ok=True)
                uid, gid = row.data.get("as") or (None, None)
                with open(where, "w", encoding="utf-8") as fh:
                    fh.write(acl.script_text(row.data["folders"],
                                             uid=uid, gid=gid))
                try:
                    os.chmod(where, 0o755)
                except OSError:
                    pass
                result.done += 1
                result.details.append(
                    f"Written to {where}\n"
                    f"    DSM > Control Panel > Task Scheduler > Create > "
                    f"Scheduled Task > User-defined script\n"
                    f"    User: root.  Schedule: every 5 minutes.  Command:  "
                    f"sh '{where}'\n"
                    f"    Once, by hand, for the folders made before any of "
                    f"this existed:  sh '{where}' all\n"
                    f"    Once, by hand, if a tree says CANNOT WRITE HERE - it "
                    f"hands back what belongs to root:  sh '{where}' own")
            except Exception as exc:                    # noqa: BLE001
                status = result.blame(row.name, exc)
        elif "queue" in row.data:
            ok, bad = _fix_now(row.data["queue"], row.data["tool"], result)
            acl.finished(ok, bad)
            result.done += ok
            result.details.append(
                f"Put right from in here: {ok:,}"
                + (f", could not: {bad:,}" if bad else ""))
            if bad:
                status = "could not do them all"
        else:
            continue
        if progress:
            progress(i, len(plan.rows), row.name, status)
    if not result.done and not result.failed:
        result.details.append(
            "Nothing to do - this tab only checks unless you ask for the repair "
            "job. The check itself makes a folder and removes it again, and "
            "that happens when you press Check the list.")
    result.stats = [("Things done", f"{result.done:,}")]
    return result


def _fix_now(folders, tool: str, result: Result) -> tuple:
    """The fast path: this app IS root and the tool IS reachable, so do it.

    The same arrangement Reindex is in - run it here if it can be run here, and
    otherwise write out a job for DSM. Which of the two happened is on the
    screen either way, so there is never a fix that only maybe took place.
    """
    import subprocess
    ok = bad = 0
    how = "-enforce-inherit" if perms.dsm_can("-enforce-inherit") else "-copy"
    for folder in folders:
        if not os.path.isdir(folder):
            acl.forget(folder)
            continue
        args = ([tool, how, folder] if how == "-enforce-inherit"
                else [tool, how, os.path.dirname(folder), folder])
        try:
            got = subprocess.run(args, capture_output=True, text=True, timeout=120)
            if got.returncode == 0:
                ok += 1
            else:
                bad += 1
                result.details.append(
                    f"could not fix {folder}: {(got.stderr or '').strip()}")
        except Exception as exc:                        # noqa: BLE001
            bad += 1
            result.details.append(f"could not fix {folder}: {exc}")
    return ok, bad


register(Task(
    name="permissions",
    line="Check what the NAS lets this app touch, and fix what it does not.",
    verb="Fix",
    unit="folders",
    title="Permissions check",
    summary="Checks folder ownership in each tree, and writes a repair job "
            "for what the app cannot fix itself.",
    icon="lock",
    parent="setup",
    tab="Permissions",
    order=96,
    reads=("library", "raw", "previews", "video", "develop"),
    options=[
        Folder("folder", "Extra folder to check", default="", must_exist=False,
               help="One more folder to check besides the trees from Setup, "
                    "for example a share you are about to point the app at. "
                    "Blank checks the Setup trees only."),
        Flag("repair", "Write repair job",
             default=False,
             help="Writes a script for DSM's Task Scheduler to run as root "
                  "every few minutes. It fixes only the folders this app has "
                  "just made, so it costs nothing when nothing is waiting. "
                  "Run by hand with 'all' it fixes the whole tree once. It "
                  "is plain text, so read it first."),
    ],
    plan=plan,
    apply=apply,
))
