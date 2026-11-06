"""Building a flow: add a step, pick a feature, set its own settings.

The developing loop was three steps written into the source. This is where any
number of flows are assembled instead, out of anything registered - so a feature
added next year can be part of one without a line of code being written here.

**A flow is a chain, not a set.** The steps run in order inside one pass, and a
step that writes something makes the step after it run straight away rather than
an interval later. Put "send to develop" before "sync ratings" and every star
you give is acted on fifteen minutes late, for ever, silently. The editor draws
them numbered and moves them one at a time for that reason.

**Each step's settings are Setup's until you say otherwise.** Every option of
every feature is there to be overridden per step, and the value it would
otherwise use is shown beside it. That is the whole answer to the thing that
went wrong before: a threshold typed on a tab was not the threshold that ran at
four in the morning, and neither end said so.

**What it will not let you build is a ring.** A step that copies photographs
into a tree, followed by one that takes them out of there and into a tree the
first one reads, sends the same photographs round again on every pass - each
step doing exactly what it was told. That used to be one refusal written by
hand, about one arrangement; assembling flows from a dropdown makes it one case
of many, so it is worked out from what each feature declares it reads, copies
and moves, against the real paths in Setup.

**Who fires it is separate from what it does.** The app's own thread, or one
command in DSM's Task Scheduler. Both run the same pass through the same
machinery; the difference is what wakes it up, and DSM's has the advantage of
surviving anything that happens to this container.
"""

from __future__ import annotations

import os

from app import registry as R
from app.registry import Plan, Result, Row, Task, register
from core import automation as A
from core import exclude as X
from core import flows as F
from core import settings as S

# What a DSM User-defined script has to say to reach the app inside a container.
# `docker` rather than `synopkg`, because Container Manager is docker underneath
# and this is the same command you would type by hand to check it.
#
# No new code path on the app's side: the command line already runs any
# registered task from its declared options, so the flow the scheduler fires is
# the flow the tab shows, through the same plan-then-apply. A second entry point
# would be a second thing to keep in step, and it would drift.
COMMAND = ("docker exec {container} python -m app.cli automation "
           "--which {flow} --apply")


def container_name() -> str:
    """What this container is actually called, if it can be worked out.

    A command with the wrong container name in it fails in DSM's scheduler with
    "No such container" - at two in the morning, into a log nobody is reading -
    so it is worth trying rather than printing a plausible guess. Docker sets
    the hostname to the container id, and Container Manager sets it to the
    container's name; either is better than a name this app invented.

    When there is nothing to go on it says so in the command itself rather than
    looking certain.
    """
    for key in ("PM_CONTAINER", "HOSTNAME"):
        got = str(os.environ.get(key) or "").strip()
        if got and got not in ("localhost",):
            return got
    try:
        return os.uname().nodename.strip() or ""
    except Exception:                                  # noqa: BLE001
        return ""


def command_for(flow, container: str = "") -> str:
    return COMMAND.format(
        container=container or container_name() or "PUT-YOUR-CONTAINER-NAME-HERE",
        flow=flow.id)


def plan(opts) -> Plan:
    p = Plan(task="flows")
    p.editor = "flows"                 # the page draws the builder above this
    saved = S.load()
    state = A.read()
    all_flows = F.read()

    p.columns = ["Step", "Watches", "And then", "Its own settings", "Last run"]
    steps = 0
    for flow in all_flows:
        fired = ("DSM's Task Scheduler" if flow.fired_by == F.BY_DSM
                 else "this app")
        p.groups.append({
            "key": f"flow:{flow.id}",
            "label": f"{flow.name}",
            "note": (f"{'running by itself' if flow.on else 'switched off'}, "
                     f"every {flow.every} min, fired by {fired}"),
            "cells": [f"{len(flow.steps)} step(s)",
                      "on" if flow.on else "off", "", ""],
        })
        for n, step in enumerate(flow.steps, 1):
            steps += 1
            task = R.get(step.task)
            title = task.title if task is not None else f"{step.task} (missing)"
            key = F.watched_key(task, step)
            note = A.last(step.key(), state)
            overrides = step.opts or {}
            p.rows.append(Row(
                what="step", name=f"{n}. {title}",
                source=str(saved[key] or "") if key else "", target="",
                detail=(task.summary if task is not None else
                        "there is no tool with this name any more"),
                cells=[F.TREE_NAMES.get(key, key or "-"),
                       ("run" if step.do == "run" else "just tell me")
                       if step.on else "SWITCHED OFF",
                       ", ".join(sorted(overrides)) or "all from Setup",
                       A.ago(note.get("ran")) if note.get("ran") else "never"],
                group=f"flow:{flow.id}",
                data={"flow": flow.id, "step": step.key()}))

    p.stats = [
        ("Flows", f"{len(all_flows):,}"),
        ("Steps in all", f"{steps:,}"),
        ("Running by themselves",
         f"{sum(1 for f in all_flows if f.on and f.fired_by == F.BY_APP):,}"),
        ("Left to DSM's scheduler",
         f"{sum(1 for f in all_flows if f.fired_by == F.BY_DSM):,}"),
        ("Tools you can use as a step", f"{len(usable()):,}"),
        ("Folders excluded everywhere",
         f"{len(X.from_settings()):,}"),
        ("  and on top of that, per flow",
         f"{sum(len(f.exclude) for f in all_flows):,}"),
    ]

    for flow in all_flows:
        for said in F.trouble(flow, saved):
            p.notes.append(f"{flow.name}: {said}")

    p.notes.append(
        "The order is not decoration. Steps run in order inside one pass, and a "
        "step that writes something makes the one after it run straight away "
        "rather than an interval later - so a step placed before the one that "
        "feeds it does its work late, every time.")
    p.notes.append(
        "Each step's settings come from Setup unless you set them on the step. "
        "The editor shows the value it would otherwise use beside every box, "
        "because the thing that went wrong before was invisible: a threshold "
        "typed on a tab was not the threshold that ran in the background.")
    p.notes.append(
        "A step watches a tree - by default the tree that tool works from - "
        "and runs when it is different from last time. Each step keeps its own "
        "mark, so the same tool can appear twice in one flow without the two "
        "deciding each other has already caught up.")
    dsm = [f for f in all_flows if f.fired_by == F.BY_DSM]
    if dsm:
        p.notes.append(
            "A flow left to DSM's Task Scheduler is never fired by this app, "
            "whatever its switch says - two things firing one flow is how two "
            "passes end up moving the same photos past each other. In DSM: "
            "Control Panel, Task Scheduler, Create, Scheduled Task, "
            "User-defined script, run as root, with the command shown on the "
            "flow.")
    p.notes.append(
        "A flow can leave folders out - the phone dump, a video folder kept "
        "beside the library. They are ADDED to the list in Setup rather than "
        "replacing it, so building a flow cannot quietly undo a decision made "
        "once, and every run that meets one says what it did not look at.")
    p.notes.append(
        "Nothing here touches a photo. Saving writes the flows file; the "
        "Automation tab is where a flow is run.")
    return p


def usable() -> list:
    """Every feature that can be a step.

    Everything registered that actually DOES something, minus the two that are
    about the flows themselves - a flow containing the flow editor is not a
    thought worth having - and minus settings pages, which have no work to do on
    a tree changing.
    """
    out = []
    for t in R.all_tasks():
        if t.name in ("automation", "flows", "autoruns"):
            continue
        if t.settings:
            continue
        out.append(t)
    return sorted(out, key=lambda t: (t.parent or t.name, t.order))


def catalogue() -> list:
    """What the editor's dropdown offers, with enough to fill a step in."""
    saved = S.load()
    out = []
    for t in usable():
        key = F.watched_key(t)
        out.append({
            "name": t.name, "title": t.title, "summary": t.summary,
            "icon": t.icon, "writes": t.writes,
            "parent": t.parent,
            "watches": key,
            "watches_label": F.TREE_NAMES.get(key, ""),
            "watches_path": str(saved[key] or "") if key else "",
            "reads": list(t.reads), "copies_to": list(t.copies_to),
            "moves_to": list(t.moves_to),
            "options": [o.describe() for o in t.options],
        })
    return out


def described() -> list:
    """Every flow, with each step's effective settings worked out."""
    saved = S.load()
    out = []
    for flow in F.read():
        steps = []
        for step in flow.steps:
            task = R.get(step.task)
            key = F.watched_key(task, step)
            steps.append({
                "id": step.key(), "task": step.task, "on": step.on,
                "do": step.do, "watch": step.watch,
                "watches": key,
                "watches_label": F.TREE_NAMES.get(key, ""),
                "watches_path": str(saved[key] or "") if key else "",
                "opts": dict(step.opts or {}),
                "title": task.title if task is not None else step.task,
                "missing": task is None,
                "effective": (F.options_for(task, step, saved)
                              if task is not None else {}),
            })
        out.append({
            "id": flow.id, "name": flow.name, "on": flow.on,
            "every": flow.every, "deep": flow.deep, "fired_by": flow.fired_by,
            "exclude": list(flow.exclude),
            "steps": steps,
            "command": command_for(flow),
            "trouble": F.trouble(flow, saved),
            "diagram": diagram(flow),
        })
    return out


def diagram(flow) -> list:
    """The flow as a chain of blocks, for the page to draw.

    A list of steps with a summary above it reads as a list. The same thing
    drawn as boxes with arrows between them reads as an ORDER, which is the one
    property of a flow that is easy to get wrong and invisible when you have -
    a step before the one that feeds it does its work an interval late, for
    ever. Worked out here rather than in the page so that the Automation tab and
    the Flows tab cannot draw two different pictures of one flow.
    """
    saved = S.load()
    state = A.read()
    out = []
    for n, step in enumerate(flow.steps, 1):
        task = R.get(step.task)
        key = F.watched_key(task, step)
        note = A.last(step.key(), state)
        waiting = int(note.get("waiting") or 0)
        out.append({
            "n": n,
            "id": step.key(),
            "task": step.task,
            "title": task.title if task is not None else step.task,
            "icon": task.icon if task is not None else "dot",
            "on": bool(step.on),
            "do": step.do,
            "missing": task is None,
            "watches": F.TREE_NAMES.get(key, key or ""),
            "ready": bool(str(saved[key] or "").strip()) if key else False,
            "overrides": len(step.opts or {}),
            "waiting": waiting,
            "last": A.ago(note.get("ran")) if note.get("ran") else "",
            "said": str(note.get("said") or ""),
        })
    return out


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    result.details.append(
        "This tab only ever looks. Flows are saved as you edit them above, and "
        "the Automation tab is where one is run.")
    return result


register(Task(
    name="flows",
    line="Build a flow: steps, each a tool with its own settings, in order.",
    title="Flows",
    summary="Builds a flow: add steps, pick a tool for each, set its options "
            "and put them in order.",
    icon="chain",
    parent="automation",
    tab="Flows",
    editor="flows",
    writes=False,
    order=72,
    options=[],
    plan=plan,
    apply=apply,
))
