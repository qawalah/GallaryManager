"""Put a run back - the one thing History could never do.

The log has always said what happened. "I sorted the wrong folder" could be
answered precisely and uselessly: four hundred files moved, here is where each
of them went, now do it again backwards by hand.

Every move is written down now (`core/moves.py`), so History can offer to
reverse one. It is an ordinary feature, which is the whole point:

- **it is a plan first.** You see every file it would move back, and the ones it
  will not touch, before anything happens - the same Check the list, Apply,
  Result as everything else here;
- **it refuses anything that has moved since.** A file that is not where the run
  left it has been touched by something else - another run, Lightroom, you - and
  dragging it backwards is how an afternoon's work is lost to a button that said
  Undo. Those are listed, with the reason, and left exactly as they are;
- **it does not undo a copy.** Sending to develop leaves the original where it
  was; reversing it would mean deleting the copy, which is a different decision
  with a different risk and does not belong behind the same word;
- **and it is itself a run.** Putting something back is recorded like anything
  else, with its own moves - so an undo can be undone.
"""

from __future__ import annotations

import os
import time

from app.registry import Number, Plan, Result, Row, Task, register
from core import moves as M
from core import runlog


def _run_of(opts):
    """The run to reverse - by its number, or by the exact moment it finished.

    The number is what a person has: it is on the left of every row in History
    and it is what the page fills in. The moment is what History's own button
    sends, because it is exact even if the log has been renumbered by hand.
    """
    try:
        no = int(float(opts.get("no") or 0))
    except (TypeError, ValueError):
        no = 0
    if no > 0:
        got = runlog.by_no(no)
        if got is not None:
            return got
    try:
        when = float(opts.get("run") or 0)
    except (TypeError, ValueError):
        return None
    return runlog.one(when) if when else None


def _said(run) -> str:
    """The run, named the way the page names it: a number, then a title."""
    from app import registry as R
    when = float(run.get("when") or 0)
    name = str(run.get("task") or "?")
    known = R.get(name)
    no = int(run.get("no") or 0)
    return ((f"Run #{no} - " if no else "")
            + (known.title if known else name)
            + (", " + time.strftime("%d %b %H:%M", time.localtime(when)) if when
               else ""))


def plan(opts) -> Plan:
    p = Plan(task="undo", opts=dict(opts))
    p.columns = ["File", "Back to"]
    run = _run_of(opts)
    if run is None:
        recent = [r for r in runlog.recent(limit=40) if r.get("moves")]
        p.blocked = ("Say which run to put back - its number is on the left of "
                     "every row in History, and each row that moved files has a "
                     "Put it back button that fills this in for you.")
        p.columns = ["Run", "Feature", "When", "What it moved"]
        for run in recent[:40]:
            when = float(run.get("when") or 0)
            from app import registry as R
            known = R.get(str(run.get("task") or ""))
            p.rows.append(Row(
                what="run", name=f"#{int(run.get('no') or 0)}",
                source=str((run.get("folders") or {}).get("folder") or ""),
                cells=[known.title if known else str(run.get("task") or "?"),
                       time.strftime("%d %b %H:%M", time.localtime(when)) if when
                       else "?",
                       f"{len(run.get('moves') or []):,} files"],
                detail=_said(run),
                data={"no": int(run.get("no") or 0)}))
        if recent:
            p.notes.append("These are the runs that moved something. Type one of "
                           "the numbers above into \"Which run\".")
        return p

    made = run.get("moves") or []
    if not made:
        p.blocked = (f"{_said(run)} did not move any files, so there is nothing "
                     f"to put back. A run that only wrote tags, stars or "
                     f"locations into photos is not reversed by moving "
                     f"anything - there is nothing here that can take a tag off "
                     f"again except the tool that put it on.")
        return p

    good, refused = M.can_put_back(made)
    # Handed to apply exactly as the run recorded it: `put_back` is the one
    # place that knows a chain of moves has to be reversed backwards.
    p.data["moves"] = made
    p.stats = [
        ("Putting back", _said(run)),
        ("Files it moved", f"{len(made):,}"),
        ("Can go back", f"{len(good):,}"),
        ("Will be left alone", f"{len(refused):,}"),
    ]
    p.impact = {"verb": "Put back", "unit": "files", "count": len(good),
                "risk": "high" if len(good) > 200 else "",
                "undo": "This is itself a run, and it is recorded like any "
                        "other - so putting it back can be put back."}
    for source, target in good:
        p.rows.append(Row(what="back", name=os.path.basename(target),
                          source=target, target=source,
                          cells=[os.path.basename(target), os.path.dirname(source)],
                          data={"from": target, "to": source}))
    for path, why in refused:
        p.skipped.append((path, why))
    if refused:
        p.data["skipped_title"] = "Left exactly as they are"
        p.data["skipped_note"] = ("these have moved since that run, so putting "
                                  "them back would undo something else")
    p.notes.append("Moves only. Tags, stars, locations and times written into "
                   "photos are not touched by this - the tool that "
                   "wrote them is the one that can take them off.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    made = plan.data.get("moves") or []
    out = M.put_back(made, result=result, progress=progress, cancelled=cancelled)
    result.done = out["done"]
    result.stats = [("Put back", f"{out['done']:,}"),
                    ("Could not be", f"{out['failed']:,}")]
    if out["refused"]:
        result.stats.append(("Left alone", f"{len(out['refused']):,}"))
    result.details.append(
        "Everything that went back is where that run found it. Anything that "
        "had moved since was left exactly as it is.")
    from core import paths as P
    # No higher than the folders the run itself was pointed at, and never the
    # Recycle Bin a Delete put things in: undoing one empties the bin's folder,
    # and the bin is not a folder that emptied out.
    run = _run_of(plan.opts or {}) or {}
    P.tidy_empty_folders({os.path.dirname(str(b)) for _a, b in made
                          if isinstance(b, str)},
                         stop_at=P.roots_of(run.get("folders") or {}))
    return result


register(Task(
    name="undo",
    verb="Put back",
    unit="files",
    line="Reverse a run that moved files, after reading what it would move.",
    title="Put a run back",
    parent="history",
    icon="undo",
    order=86,
    hidden=True,
    inline=True,
    summary="Moves the files of one past run back to where they were. "
            "Anything moved since is refused.",
    options=[
        Number("no", "Which run", default=0, minimum=0, maximum=99999999,
               help="The run number shown at the left of a row in History: "
                    "#412 is 412. Pressing Put it back on a row fills this "
                    "in."),
        Number("run", "Run time", default=0, minimum=0, maximum=99999999999,
               advanced=True,
               help="The exact time the run finished. The Put it back button "
                    "in History fills this in for you. You do not need to "
                    "type it."),
    ],
    plan=plan,
    apply=apply,
    writes=True,
    undo="This is itself a run, recorded like any other, so it can be put back "
         "in turn.",
))
