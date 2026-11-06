"""Empty the list of runs - all of it, or the part that has gone stale.

The log is one file on the NAS and every device writes to the same one. You
read the morning's runs on a phone, come back to the desk, and the same forty
rows are waiting again with nothing to be done about them: the list could be
trimmed by age, by itself, and never emptied on purpose.

So this. It is an ordinary feature, which means:

- **it says how many lines it would remove before it removes them** - the same
  Check the list, Apply, Result as everything else here;
- **it is about the LOG, not about the photographs.** Nothing on disk changes,
  and nothing that was put in the recycle folder comes back or goes away;
- **and it costs you the undo.** A run that has been forgotten cannot be put
  back, because the list of what it moved went with it. That is said on the
  page, in those words, before anything happens.
"""

from __future__ import annotations

import time

from app.registry import Choice, Number, Plan, Result, Row, Task, register
from core import runlog

WHICH = [
    ("all", "Everything"),
    ("old", "Older than a number of days"),
    ("task", "One tool only"),
]


def _days(opts) -> float:
    try:
        return max(0.0, float(opts.get("days") or 0))
    except (TypeError, ValueError):
        return 0.0


def plan(opts) -> Plan:
    p = Plan(task="forget", opts=dict(opts))
    which = str(opts.get("which") or "all")
    task = str(opts.get("task") or "").strip()
    days = _days(opts)
    if which == "old" and not days:
        p.blocked = "Say how many days to keep."
        return p
    if which == "task" and not task:
        p.blocked = "Pick which tool's runs to forget."
        return p
    if which == "all":
        task, days = "", 0.0
    elif which == "old":
        task = ""
    else:
        days = 0.0

    lines = runlog.read_lines()
    going = runlog.would_forget(task=task, days=days)
    p.columns = ["Run", "Feature", "When", "What happened"]
    from .history import said_plainly
    from app import registry as R
    cut = (time.time() - days * 86400) if days else 0.0
    shown = 0
    undoable = 0
    for run in reversed(lines):
        name = str(run.get("task") or "")
        if task and name != task:
            continue
        if cut and float(run.get("when") or 0) >= cut:
            continue
        if run.get("moves"):
            undoable += 1
        shown += 1
        if shown > 200:
            continue
        known = R.get(name)
        when = float(run.get("when") or 0)
        p.rows.append(Row(
            what=name, name=f"#{int(run.get('no') or 0)}",
            source=str((run.get("folders") or {}).get("folder") or ""),
            cells=[known.title if known else name,
                   time.strftime("%d %b %H:%M", time.localtime(when)) if when else "?",
                   said_plainly(run)],
            detail=said_plainly(run)))

    p.stats = [
        ("Runs in the log", f"{len(lines):,}"),
        ("Would be forgotten", f"{going:,}"),
        ("Would be left", f"{len(lines) - going:,}"),
        ("Of those, could have been put back", f"{undoable:,}"),
    ]
    p.impact = {"verb": "Forget", "unit": "runs", "count": going,
                "risk": "high" if undoable else "",
                "undo": "None. The log is the only record there is, and a line "
                        "that goes takes its list of moved files with it."}
    p.notes.append("Nothing on disk changes. This empties the list of what was "
                   "done, not the things that were done.")
    if undoable:
        p.notes.append(f"{undoable:,} of these can currently be put back, and "
                       f"will not be able to be afterwards - the list of what "
                       f"each one moved is kept in the line being removed.")
    if shown > 200:
        p.notes.append(f"The newest 200 are listed; {shown - 200:,} more match.")
    if not going:
        p.notes.append("Nothing matches, so there is nothing to forget.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    opts = plan.opts or {}
    which = str(opts.get("which") or "all")
    task = str(opts.get("task") or "").strip() if which == "task" else ""
    days = _days(opts) if which == "old" else 0.0
    try:
        got = runlog.forget(task=task, days=days)
    except OSError as exc:
        result.blame(runlog.store_path(runlog.FILE), exc)
        return result
    result.done = int(got["gone"])
    result.stats = [("Runs forgotten", f"{got['gone']:,}"),
                    ("Runs left", f"{got['left']:,}")]
    result.details.append(
        "The list is shorter. Nothing on disk moved, and anything in a recycle "
        "or set-aside folder is exactly where it was.")
    return result


def _features() -> list:
    """Only the features that have actually run - the rest would be empty tabs."""
    from app import registry as R
    counts: dict = {}
    for run in runlog.read_lines():
        name = str(run.get("task") or "")
        if name:
            counts[name] = counts.get(name, 0) + 1
    out = [("", "Pick one")]
    for name in sorted(counts):
        known = R.get(name)
        out.append((name, f"{known.title if known else name} ({counts[name]:,})"))
    return out


register(Task(
    name="forget",
    verb="Forget",
    unit="runs",
    line="Empty the list of runs: all of it, or anything past a given age.",
    title="Clear the history",
    parent="history",
    icon="trash",
    order=87,
    hidden=True,
    inline=True,
    summary="Removes runs from the history log. Nothing on disk changes, but "
            "those runs can no longer be put back.",
    options=[
        Choice("which", "What to forget", default="all", choices=WHICH,
               help="Which runs to remove: every run, only runs older than a "
                    "number of days, or only one tool's runs."),
        Number("days", "Older than (days)", default=30, minimum=1, maximum=3650,
               only_when="which=old",
               help="Runs that finished more than this many days ago are "
                    "removed. 1 to 3650, default 30."),
        Choice("task", "Which tool", default="", choices=_features,
               only_when="which=task",
               help="Only this tool's runs are removed."),
    ],
    plan=plan,
    apply=apply,
    writes=True,
    undo="None - the log is the only record there is.",
))
