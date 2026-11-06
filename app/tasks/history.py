"""What was actually done, and when.

The Windows app had a log and this did not, and the gap shows the first time
something runs unattended. A scheduled re-mirror at 3am moves four hundred files
and the only record was a progress bar nobody was watching; "what happened to
this folder" then has no answer at all - and the Library view, which is measured
rather than remembered, deliberately cannot answer it either. It says what IS,
not what was done. This is the other half of that pair.

Only runs that WROTE something are here. A preview that changed nothing is not
history, and a log full of "looked at 40,000 photos" is a log nobody reads.

It is a task like any other so that it needs no interface of its own: the same
form, the same table, the same command line. It only ever reports.
"""

from __future__ import annotations

import os
import time

from app.registry import Choice, Number, Plan, Result, Row, Task, register
from core import runlog


def _ago(when: float) -> str:
    gap = max(0, time.time() - when)
    if gap < 90:
        return "just now"
    if gap < 5400:
        return f"{int(gap // 60)} min ago"
    if gap < 172800:
        return f"{int(gap // 3600)} hours ago"
    return f"{int(gap // 86400)} days ago"


# WHAT HAPPENED, IN THE WORD SOMEBODY WOULD USE.
#
# "files: 3 done - a.jpg -> ...@recycle/a.jpg" is true and unreadable. Deleting
# a photograph, copying one into another folder and moving a hundred are all the
# "files" task, and the log had no way to tell them apart - so every row had to
# be opened and read. The task says what it does (`Task.verb`, `Task.unit`), the
# run now says which of them it did (`action`), and this turns the two into a
# sentence.
ACTIONS = {
    # Power rename writes through the table's own buttons rather than through a
    # plan, so the task has no verb for History to borrow.
    ("rename", ""): ("Renamed", "folders"),
    ("files", "delete"): ("Deleted", "files"),
    ("files", "move"): ("Moved", "files"),
    ("files", "copy"): ("Copied", "files"),
    ("files", "rename"): ("Renamed", "files"),
    ("files", "folder"): ("Made", "folders"),
    ("files", ""): ("Changed", "files"),
}

# And where the things went, for the ones that did not really destroy anything.
# A delete here moves to the recycle folder; saying "deleted" and leaving it at
# that would be the opposite lie from the one being fixed.
AFTER = {
    ("files", "delete"): "into the recycle folder, where they can be fetched back",
    ("cleanup", ""): "into the recycle folder",
    ("cull", ""): "into the set-aside folder",
    ("blur", ""): "into the set-aside folder",
    ("duplicates", ""): "into the set-aside folder",
    ("thin", ""): "into the set-aside folder",
}


# A task's verb is an instruction - "Move", "Tag", "Set aside" - because it is
# written on a button you are about to press. History is the other tense: it
# happened. Spelled out rather than guessed at, because "Tagged" and "Copied"
# are not what a rule about adding "ed" produces, and a log that says "Taged"
# is a log that looks machine-written.
PAST = {
    "move": "Moved", "copy": "Copied", "tag": "Tagged", "delete": "Deleted",
    "create": "Created", "rename": "Renamed", "import": "Imported",
    "geotag": "Geotagged", "pin": "Pinned", "label": "Labelled",
    "sync": "Synced", "run": "Ran", "build": "Built", "back": "Backed",
    "set": "Set", "put": "Put", "fix": "Fixed", "strip": "Stripped",
    "file": "Filed", "reindex": "Reindexed", "forget": "Forgot",
    "send": "Sent", "make": "Made", "changed": "Changed", "change": "Changed",
}


def in_the_past(verb: str) -> str:
    """"Move" on the button, "Moved" in the log. It already happened."""
    bits = str(verb or "").split()
    if not bits:
        return "Changed"
    head = PAST.get(bits[0].lower())
    if not head:
        one = bits[0]
        head = one + ("d" if one.lower().endswith("e") else "ed")
        head = head[0].upper() + head[1:]
    return " ".join([head] + bits[1:])


def said_plainly(run) -> str:
    """One line: what was done, to how many, and where they are now."""
    from app import registry as R
    name = str(run.get("task") or "")
    act = str(run.get("action") or "")
    done = int(run.get("done") or 0)
    verb, unit = ACTIONS.get((name, act), ACTIONS.get((name, ""), ("", "")))
    if not verb:
        task = R.get(name)
        verb = in_the_past(task.verb if task and task.verb else "Changed")
        unit = (task.unit if task and task.unit else "files")
    said = f"{verb} {done:,} {unit if done != 1 else unit.rstrip('s')}"
    where = AFTER.get((name, act)) or AFTER.get((name, ""), "")
    if where and done:
        said += f" {where}"
    if run.get("failed"):
        said += f" - {int(run['failed']):,} FAILED"
    if run.get("cancelled"):
        said += " - stopped part way"
    return said


def _which() -> list:
    """One tab per operation that has actually happened, with how many.

    Offering a tab for every feature would be a row of mostly empty tabs, and an
    empty tab teaches you not to trust the row. The log says what has really
    been done; that is the list worth showing, and the counts turn the tabs into
    a summary in their own right.
    """
    from app import registry as R
    counts: dict = {}
    for run in runlog.read_lines():
        name = str(run.get("task") or "")
        if name:
            counts[name] = counts.get(name, 0) + 1
    out = [("", f"Everything ({sum(counts.values()):,})" if counts else "Everything")]
    for t in R.all_tasks():
        if t.name in counts:
            out.append((t.name, f"{t.title} ({counts[t.name]:,})"))
    # a run from a task that has since been renamed or removed still happened
    known = {t.name for t in R.all_tasks()}
    for name in sorted(counts):
        if name not in known:
            out.append((name, f"{name} ({counts[name]:,})"))
    return out


def plan(opts) -> Plan:
    from app import registry as R
    p = Plan(task="history")
    wanted = (opts.get("task") or "").strip()
    limit = int(opts.get("limit") or 100)

    runs = runlog.recent(limit=limit, task=wanted)
    total = done = failed = 0
    movers = 0
    for run in runs:
        total += 1
        done += int(run.get("done") or 0)
        failed += int(run.get("failed") or 0)
        when = float(run.get("when") or 0)
        folders = run.get("folders") or {}
        where = folders.get("folder") or next(iter(folders.values()), "")
        name = str(run.get("task") or "?")
        known = R.get(name)
        title = known.title if known else name
        no = int(run.get("no") or 0)
        if run.get("moves"):
            movers += 1
        said = "; ".join(str(d).replace("\n", " ") for d in (run.get("details") or []))
        p.rows.append(Row(
            what=name,
            # The number is the name of the run, on the left, where a name goes.
            # "Put run 1042 back" is a thing somebody can say; the moment it
            # finished, to the millisecond, is not.
            name=(f"#{no}" if no else "-"),
            source=where,
            target="",
            # `cells` is what goes under the columns the task named, in order,
            # and the table puts the row's NAME in the first one and the folder
            # in the last by itself - so neither belongs in here.
            cells=[title,
                   time.strftime("%d %b %H:%M", time.localtime(when)) if when else "?",
                   said_plainly(run),
                   (f"{run.get('seconds')}s" if run.get("seconds") else "")],
            detail=f"{title}: {said_plainly(run)}"
                   + (f" - {said[:300]}" if said else ""),
            data={"when": when, "no": no},
            # By NUMBER, which is what the row says and what somebody could
            # type themselves. The exact moment still identifies a run and the
            # feature still takes it, but it is not a thing to hand a person.
            act=({"label": "Put it back", "task": "undo", "option": "no",
                  "value": str(no)} if run.get("moves") and no else {})))

    # The table adds "Where" and the column of buttons itself - a task names
    # the middle ones only.
    p.columns = ["Run", "Feature", "When", "What happened", "Took"]

    p.stats = [
        ("Runs shown", f"{total:,}"),
        ("Files they changed", f"{done:,}"),
        ("Failures", f"{failed:,}"),
        ("Can be put back", f"{movers:,}"),
        ("Newest", _ago(float(runs[0].get("when") or 0)) if runs else "-"),
        ("Log file", runlog.store_path(runlog.FILE)),
    ]
    # Two things to do with a log, both of them one press away rather than a
    # path to type: reverse one of these runs, or empty the list.
    p.acts = [
        {"label": "Put a run back", "task": "undo", "option": "no", "value": "0",
         "help": "Type the number of the run on the left, or press the button on "
                 "its row."},
        {"label": "Clear the history", "task": "forget", "option": "which",
         "value": "all",
         "help": "The log is on the NAS and every device adds to the same one."},
    ]
    p.notes.append("Only runs that wrote something are recorded. A preview changes "
                   "nothing, so it is not history.")
    p.notes.append("Every run carries a number. A run that MOVED files can be put "
                   "back by it - the button is on those rows - and it shows a list "
                   "first like everything else, refusing anything that has moved since.")
    p.notes.append("The Library view says what IS - measured from the files right "
                   "now. This says what was DONE. Neither can answer the other's "
                   "question, which is why both exist.")
    if not runs:
        p.notes.append("Nothing has been applied yet, or the log was cleared. It is "
                       "written to the config folder, so it survives a Restart but "
                       "not a config volume that was thrown away.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    result.details.append("Nothing to apply - this only ever reports.")
    return result


register(Task(
    name="history",
    line="Every run that wrote something, numbered, with what it did.",
    title="History",
    summary="Lists every run that changed a file, and when. Nothing is "
            "changed.",
    icon="history",
    hidden=True,    order=85,   # last thing before Setup: it is a place you go to look back,
                # not a step in the loop
    writes=False,
    options=[
        Choice("task", "Which tool", default="", choices=_which, tabs=True,
               help="Shows only this tool's runs. Every run that changed a "
                    "file is recorded, from this page, from the command line "
                    "and from DSM's Task Scheduler."),
        Number("limit", "Runs to show", default=100, minimum=5, maximum=400,
               help="The number of most recent runs to list, newest first. 5 "
                    "to 400, default 100."),
    ],
    plan=plan,
    apply=apply,
))
