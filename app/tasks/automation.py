"""Running a flow: some features, in an order, when the thing they watch moves.

The developing loop used to be three steps written into this file. That was the
right shape and the wrong place - every feature here already declares its
options as data and provides plan-then-apply, so the loop never needed to know
which three they were. It knew because somebody typed them.

A flow is data now (`core/flows.py`), and this module runs one. What has not
changed is why it is built this way:

**It watches, it does not wait for a clock.** Each step watches a tree and runs
when that tree is different from last time. Nothing happens at three in the
morning because nothing has changed then, and finishing a shoot at four in the
afternoon does not wait for midnight.

**And it is polling, and says so.** A kernel change notification does not work
here: this app is in a container watching a volume that DSM, Synology Drive and
SMB all write to from outside, and a watch that quietly missed those would be
worse than no watch at all. The interval is how quickly a change is NOTICED,
not how often work is done - a pass where nothing changed reads folder dates
and stops.

**The chain runs forwards in one pass.** If syncing ratings wrote something into
the library, sending to develop runs straight after it rather than waiting for
the next pass to notice - otherwise a rating and the copy it should have caused
would always be one interval apart, which is how a workflow comes to feel like
it is lagging behind you. It is also why the ORDER of a flow is not decoration.

**Each step is separately switched and separately trusted.** A step that writes
metadata or copies files can be left to run on its own; one that MOVES
photographs into the library is where a wrong answer is a photograph somewhere
you did not put it, so it can be set to report and be promoted later.

**Who fires it is a separate question from what it does.** The app's own thread,
or a task in DSM's Task Scheduler running one command. Both run this same pass
through this same machinery.
"""

from __future__ import annotations

import os
import time

from app import registry as R
from app.registry import Choice, Flag, Number, Plan, Result, Row, Task, register
from core import automation as A
from core import exclude as X
from core import flows as F
from core import settings as S

DO = F.DO

# Kept so that anything still importing it gets the same three names. The flow
# they describe now lives in core/flows.FIRST.
STEPS = [{"key": one["task"], "task": one["task"]} for one in F.FIRST]

FIELDS = ["auto_on", "auto_every", "auto_deep"] + \
         [f"auto_{one['task']}_{part}" for one in F.FIRST for part in ("on", "do")]


def _title(name: str) -> str:
    t = R.get(name)
    return t.title if t is not None else name


def _watched_folder(step, task, saved) -> tuple:
    """(the folder this step watches, what to call it)."""
    key = F.watched_key(task, step)
    if not key:
        return "", "nothing it could work out"
    return str(saved[key] or "").strip(), F.TREE_NAMES.get(key, key)


def chosen(opts=None, flows=None) -> F.Flow:
    """The flow this tab is looking at: the one asked for, else the first.

    Never None. A tab whose dropdown is empty because a flow was deleted while
    you were looking at it should show you something rather than an error.
    """
    flows = F.read() if flows is None else flows
    want = str((opts or {}).get("which") or "").strip()
    for f in flows:
        if f.id == want:
            return f
    return flows[0] if flows else F.Flow(id="", name="No flows yet")


# ------------------------------------------------------------------ one pass

def one_pass(flow=None, allow_writes: bool = True, progress=None,
             force: str = "", saved=None, cancelled=None) -> list:
    """Run one flow's enabled steps once, in order. One report per step.

    Used by the tab's button AND by the background loop, on purpose: two code
    paths would mean the thing you tested by pressing the button is not the
    thing that runs at four in the morning.

    `force` names one step - by its id - to RUN this pass whatever its "and
    then" says. That is the Apply button on the waiting queue, and it is a
    deliberate override rather than a setting: filing exports reports by default
    because it moves photographs into the library, and "do the 194 you have been
    telling me about" should not quietly promote it to running on its own for
    ever afterwards.

    `cancelled` is the Stop button of whoever started the pass. It is asked
    before each step, and handed on to the step that is running, so Stop ends
    the pass rather than only the bar that shows it.
    """
    saved = S.load() if saved is None else saved
    flow = chosen() if flow is None else flow
    deep = bool(flow.deep)
    state = A.read()
    out = []
    # This flow's excluded folders, on top of Setup's, for the whole pass -
    # including the change check, or a flow would keep waking up for a folder
    # its own steps then refuse to look at.
    away = X.using(flow.exclude)

    for bad in F.refusals(flow, saved):
        return [{"key": "-", "title": "Refused", "said": bad, "ran": False,
                 "failed": True}]

    live = flow.live()
    with away:
        return _steps(flow, live, saved, deep, state, allow_writes, progress,
                      force, out, cancelled)


def _linked(job, cancelled) -> None:
    """Make a step's job stop when the pass it belongs to is stopped.

    A job reads its own `cancel` flag between rows, and reports progress after
    each one; checking the pass's Stop there reaches the step at the next row,
    while planning as well as applying.
    """
    if cancelled is None:
        return
    own = job.progress

    def progress(*a, **k):
        if cancelled():
            job.cancel = True
        return own(*a, **k)
    job.progress = progress


def _steps(flow, live, saved, deep, state, allow_writes, progress, force, out,
           cancelled=None):
    """The pass itself, inside the flow's exclusions.

    Split out only so that `with` wraps the whole of it - the change check
    included. A flow whose fingerprint counted a folder its own steps then
    refuse to look at would wake up for it every pass and find nothing to do.
    """
    upstream_wrote = False
    for n, step in enumerate(live, 1):
        key = step.key()
        task = R.get(step.task)
        title = task.title if task is not None else step.task
        report = {"key": key, "title": title, "task": step.task, "ran": False,
                  "failed": False, "rows": 0, "said": ""}
        if cancelled is not None and cancelled():
            # Stopped: this step and every one after it is not started. Not
            # remembered either, so the next pass still sees the change.
            report["stopped"] = True
            report["said"] = "not started - the pass was stopped"
            out.append(report)
            continue
        if progress:
            progress(n, len(live), title)
        if task is None:
            report["failed"] = True
            report["said"] = f"there is no tool called {step.task!r} any more"
            out.append(report)
            continue

        tree, tree_name = _watched_folder(step, task, saved)
        look = A.fingerprint(tree, deep=deep)
        report["seconds"] = look.seconds
        report["files"] = look.files
        if not look.there:
            where = tree or "not set"
            report["said"] = (f"{tree_name} is not there ({where}) - Setup is "
                              f"where that is set")
            out.append(report)
            continue

        due = A.changed(key, look, state) or upstream_wrote or key == force
        if not due:
            report["said"] = "nothing has changed since the last look"
            A.remember(key, look, report["said"], ran=False, state=state)
            out.append(report)
            continue
        report["why"] = ("something earlier in the chain wrote"
                         if not A.changed(key, look, state) else
                         f"{tree_name} has changed")

        # Run it as a JOB, exactly as pressing the button does.
        #
        # It used to call make_plan and apply directly, and the consequence was
        # that the app could be reading the whole library every fifteen minutes
        # while the page said nothing at all: the bar at the top is fed by the
        # job list, and a background pass was not in it. Going through the same
        # machinery also gets the run log, the re-index queue and the cost
        # measurement for free, rather than three more places to forget them.
        from app import server as srv                  # here: server imports us
        job = srv.remember(srv.Job(task, raw=F.raw_for(task, step)))
        job.by = "automation"
        report["job"] = job.id
        _linked(job, cancelled)
        job.look()
        plan = job.plan
        if job.error:
            report["failed"] = True
            report["said"] = "it could not work out what to do: "
            report["said"] += job.error.strip().splitlines()[-1]
            out.append(report)
            continue
        if plan is None or plan.blocked:
            report["failed"] = True
            report["said"] = (plan.blocked if plan is not None
                              else "it produced no list at all")
            out.append(report)
            continue

        report["rows"] = len(plan.rows)
        doing = str(step.do or "report") == "run" or key == force
        if not plan.rows:
            report["said"] = "nothing to do"
            A.waiting(key, 0, state=state)
            A.remember(key, look, report["said"], ran=False, state=state)
            out.append(report)
            continue
        if not doing or not allow_writes:
            # Deliberately NOT remembered: this step has not caught up with its
            # tree, and writing the mark down would mean next time it says
            # "nothing has changed" and the waiting work is never mentioned
            # again.
            report["said"] = (f"{len(plan.rows)} waiting - press Apply on the "
                              f"queue at the top of this tab, or open the "
                              f"{task.title} tab")
            report["waiting"] = len(plan.rows)
            A.waiting(key, len(plan.rows), title=title, task=task.title,
                      state=state)
            out.append(report)
            continue

        # Waits its turn first if a run on an overlapping tree is still writing
        # (server.claim_trees): queued, not refused, because nobody is here to
        # press Apply again.
        job.run()                     # logs, queues the re-index, measures itself
        result = job.result
        if result is None:
            report["failed"] = True
            report["said"] = ("it failed part way: "
                              + (job.error.strip().splitlines()[-1]
                                 if job.error else "no result"))
            out.append(report)
            continue

        report["ran"] = True
        report["done"] = result.done
        report["failed"] = bool(result.failed)
        report["cost"] = dict(job.cost or {})
        report["said"] = (f"{result.done:,} done"
                          + (f", {result.failed:,} failed" if result.failed else ""))
        A.waiting(key, 0, state=state)
        if result.done:
            upstream_wrote = True
        # Only now, and only when it actually ran: a step that failed half way
        # has not caught up, and the next pass should try again.
        if not result.failed:
            A.remember(key, look, report["said"], ran=True, state=state)
        out.append(report)
    return out


# ------------------------------------------------------------------- the tab

def _flow_choices():
    return [(f.id, f.name) for f in F.read()] or [("", "No flows yet")]


def _step_choices(flow=None):
    flow = chosen() if flow is None else flow
    out = [("", "No - just run the enabled steps")]
    for step in flow.steps:
        out.append((step.key(), _title(step.task)))
    return out


def plan(opts, progress=None) -> Plan:
    p = Plan(task="automation")
    p.editor = "flowsummary"        # the page draws the chain above the table
    saved = S.load()
    state = A.read()
    all_flows = F.read()
    flow = chosen(opts, all_flows)
    deep = bool(flow.deep)
    # The same exclusions the pass will run under, so that "up to date" on this
    # tab means up to date for the tree this flow actually looks at.
    p.notes.append("")                       # placeholder, filled in below
    p.notes.pop()

    p.notes.append(
        f"Flow: {flow.name} - {len(flow.steps)} step(s), "
        f"{'running by itself' if flow.on else 'switched off'}. "
        f"Build and reorder steps on the Flows tab.")

    for bad in F.refusals(flow, saved):
        p.blocked = bad
        return p

    # ---- what is waiting, before anything else on the tab
    #
    # A step set to "just tell me" finds work, says so once into a log nobody
    # reads, and then says it again every fifteen minutes for a week. The
    # sentence was there; the thing missing was somewhere to press. This is the
    # queue, and it is read from what the passes wrote down rather than by
    # re-planning the steps - working out that 194 photographs are ready costs
    # the same as sending them.
    queued = []
    for step in flow.steps:
        note = A.last(step.key(), state)
        n = int(note.get("waiting") or 0)
        if n:
            queued.append((step, n, note))
    for step, n, note in queued:
        since = A.ago(note.get("waiting_since"))
        p.rows.append(Row(
            what="waiting", name=f"WAITING: {n:,} from {_title(step.task)}",
            source=note.get("waiting_task") or step.task, target="",
            detail=(f"{n:,} found and not done - {since}. Apply runs this one "
                    f"step now, whatever its 'and then' says."),
            cells=["", f"{n:,} waiting since {since}",
                   "press Apply to do it now"],
            group=f"waiting:{step.key()}",
            data={"key": step.key(), "waiting": n}))
    if queued:
        p.groups = [{
            "key": f"waiting:{step.key()}",
            "label": f"{n:,} waiting - {_title(step.task)}",
            "note": f"found {A.ago(note.get('waiting_since'))}, not done",
            "cells": [note.get("waiting_task") or "",
                      "this step is set to just tell you", ""],
            "actions": [{"option": "apply_now", "value": step.key(),
                         "label": f"Apply these {n:,}",
                         "help": "Runs this one step now with writing allowed, "
                                 "whatever its 'and then' setting says. It does "
                                 "not change the setting."}],
        } for step, n, note in queued]

    p.columns = ["Step", "Watches", "State", "Last run"]
    on = 0
    for n, step in enumerate(flow.steps, 1):
        task = R.get(step.task)
        title = task.title if task is not None else step.task
        tree, tree_name = _watched_folder(step, task, saved) if task else ("", "?")
        if progress:
            progress(n, len(flow.steps), title)
        note = A.last(step.key(), state)

        if task is None:
            state_says = "there is no such tool any more"
        elif not step.on:
            state_says = "switched off"
        elif not tree:
            state_says = f"{tree_name} is not set up - see Setup"
        else:
            with X.using(flow.exclude):
                look = A.fingerprint(tree, deep=deep)
            if not look.there:
                state_says = f"{tree} is not there"
            elif A.changed(step.key(), look, state):
                state_says = (f"changed - would "
                              f"{'run' if step.do == 'run' else 'report'} "
                              f"({look.files:,} files read in {look.seconds:.1f}s)")
            else:
                state_says = f"up to date ({look.files:,} files, {look.seconds:.1f}s)"
        on += 1 if step.on else 0
        overridden = len(step.opts or {})
        p.rows.append(Row(
            what="step", name=f"{n}. {title}",
            source=tree or "(not set up)", target="",
            # Short. What the feature DOES is one hover away on the Flows tab;
            # repeating its whole summary in every row of every flow made the
            # step list a wall of prose with the state buried at the end of it.
            detail=(f"{state_says}"
                    + (f" - {overridden} setting(s) set here"
                       if overridden else "")),
            cells=[tree_name, state_says,
                   (A.ago(note.get("ran")) + " - " + str(note.get("said") or ""))
                   if note.get("ran") else "never"],
            data={"key": step.key()}))

    fired = "DSM's Task Scheduler" if flow.fired_by == F.BY_DSM else "this app"
    p.stats = [
        ("Flow", flow.name),
        ("Running by itself", "ON" if flow.on else "off"),
        ("Fired by", fired),
        ("WAITING ON YOU", f"{sum(n for _s, n, _o in queued):,}"
         if queued else "nothing"),
        ("Steps switched on", f"{on} of {len(flow.steps)}"),
        ("Looks for changes every", f"{flow.every} minutes"),
        ("Notices edits inside files", "yes" if deep else "no - only files "
                                                          "appearing or going"),
        ("Flows in all", f"{len(all_flows):,}"),
    ]

    if flow.fired_by == F.BY_DSM:
        p.notes.append(
            "DSM's Task Scheduler fires this one, so the app's own loop leaves "
            "it alone whatever the switch says. The Flows tab has the exact "
            "command to paste into a User-defined script.")
    elif flow.on:
        p.notes.append(
            f"IT IS ON. These steps run by themselves every {flow.every} "
            f"minutes, whether or not this page is open, and the bar at the top "
            f"of every page says so.")
    else:
        p.notes.append(
            "IT IS OFF. Nothing happens on its own: this tab is a button, and "
            "Run one pass now does exactly one pass. Turn it on from the Flows "
            "tab and it starts within a minute - no restart.")

    asked = str(opts.get("apply_now") or "").strip()
    if asked:
        names = {s.key(): _title(s.task) for s in flow.steps}
        p.notes.insert(0, (
            f"This pass will RUN '{names.get(asked, asked)}' whatever its "
            f"'and then' says. That is this press only - the setting is not "
            f"changed, so the step goes back to reporting on the next pass."))
    elif queued:
        p.notes.insert(0, (
            f"{sum(n for _s, n, _o in queued):,} thing(s) are waiting: a step "
            f"found work and is set to tell you rather than do it. Press Apply "
            f"on the row above to do it now. Nothing counts itself up to date "
            f"while it is waiting, which is why it is still being offered."))

    for said in F.trouble(flow, saved):
        if said not in p.notes:
            p.notes.append(said)

    p.notes.append(
        f"Each step watches a tree and runs when it is different from last "
        f"time. The chain also runs forwards inside one pass: if a step wrote "
        f"something, the next one runs straight after it rather than waiting "
        f"{flow.every} minutes to notice. That is why the order matters.")
    if deep:
        p.notes.append(
            "Every file's date is read, which is what catches a rating being "
            "written into a sidecar that already existed - the most important "
            "change here, and the one a folder date cannot see. It costs one "
            "stat per file; the time each look took is in the table.")
    else:
        p.notes.append(
            "Only folder dates are read - quick, and BLIND to a file being "
            "edited in place. A rating written into a sidecar that already "
            "existed will not be noticed.")
    p.notes.append(
        "A step set to 'just tell me' never counts itself up to date, so work "
        "waiting on it is mentioned every pass rather than going quiet after "
        "the first one.")
    p.notes.append(
        "There is no kernel change notification here: this app is in a "
        "container watching a volume that DSM, Drive and SMB write to from "
        "outside, and a watch that missed those would be worse than none. So "
        "the trees are looked at on an interval - which is how quickly a change "
        "is noticed, not how often work is done.")
    # One pass of ONE flow runs its switched-on steps. Counting the rows (the
    # steps plus anything waiting) made the button read "Run 3 flows" for a
    # single flow of three steps.
    steps = len(flow.live())
    p.impact = {"count": steps, "unit": "step" if steps == 1 else "steps"}
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    flow = chosen(plan.opts)
    reports = one_pass(flow, progress=progress,
                       force=str(plan.opts.get("apply_now") or "").strip(),
                       cancelled=cancelled)
    result.cancelled = any(r.get("stopped") for r in reports) or bool(
        cancelled and cancelled())
    for r in reports:
        mark = "FAILED: " if r.get("failed") else ""
        result.details.append(f"{r['title']}\n    {mark}{r['said']}")
        result.done += 1 if r.get("ran") else 0
        result.failed += 1 if r.get("failed") else 0
    result.stats = [
        ("Flow", flow.name),
        ("Steps that ran", f"{sum(1 for r in reports if r.get('ran')):,}"),
        ("Things done", f"{sum(int(r.get('done') or 0) for r in reports):,}"),
        ("Waiting on you",
         f"{sum(int(r.get('rows') or 0) for r in reports if not r.get('ran')):,}"),
        ("Running by itself", "on" if flow.on else "off"),
    ]
    return result


register(Task(
    name="automation",
    verb="Run",
    unit="steps",
    title="Automation",
    summary="Runs a flow: a list of tools, in order, each when the folder it "
            "watches changes.",
    icon="auto",
    # The chain is drawn as soon as the tab opens, not after a plan: "which flow
    # is this and what is in it" is the question you have on arriving.
    editor="flowsummary",
    run_label="Run one pass now",
    writes=True,
    order=70,
    reads=("library", "previews", "raw", "develop", "inbox"),
    options=[
        Choice("which", "Which flow", default="", choices=_flow_choices,
               group="Flow", advanced=True,
               help="The flow this tab shows and the Run button runs. Flows "
                    "are built on the Flows tab: add a step, pick a tool and "
                    "set its options."),
        Choice("apply_now", "Run a waiting step", default="",
               choices=_step_choices, group="Flow",
               help="Runs one waiting step with writing allowed, for this "
                    "press only. The Apply button on a waiting row fills "
                    "this in. The step's own 'and then' setting is not "
                    "changed, so on the next pass the step reports again "
                    "without writing."),
    ],
    plan=plan,
    apply=apply,
))
