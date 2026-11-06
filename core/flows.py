"""A flow: some features, in an order, each with its own settings.

The developing loop was three steps written into the source - sync the ratings,
send out to develop, file what came back. That was the right shape and the wrong
place. Every feature in this app already declares its options as data and
provides plan-then-apply, so there was never a reason for the loop to know which
three they were; it knew because somebody typed them.

So a flow is DATA now:

    Developing loop        every 15 min, run by the app
      1. Rating & tags     watches: previews    run
      2. Send to develop   watches: library     run
      3. File developed    watches: exports     just tell me

    Sunday tidy-up         Sundays 02:00, run by DSM's Task Scheduler
      1. Find duplicates   watches: library     just tell me
      2. Clean up          watches: library     just tell me

Anything registered can be a step, so a feature added next year is available to
every flow without a line of code here.

**Order is not decoration.** The chain runs forwards inside one pass: if a step
writes something, the step after it runs straight away rather than waiting for
the next interval. Put a step before the one that feeds it and it does its work
an interval late, every time, silently. The editor draws them as a chain for
that reason.

**A step watches a tree, and by default it is the tree the step reads.** Working
that out from the task rather than asking is what makes the default flow behave
exactly as the hard-coded one did: a task's first folder option names the Setup
tree it works from, so syncing ratings watches the previews and filing watches
the export folder without anybody choosing.

**Each step's settings are Setup's until you say otherwise.** An override is
stored per step and shown beside the value it replaces, because the thing that
went wrong before was invisible: a threshold typed on a tab was not the
threshold that ran at four in the morning, and neither end said so.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict

from .store import store_path

FILE = "flows.json"
VERSION = 1

# Who actually fires it. Both run the same pass through the same machinery -
# this only decides what wakes it up.
BY_APP = "app"
BY_DSM = "dsm"
FIRED_BY = [
    (BY_APP, "This app, in the background"),
    (BY_DSM, "An entry in DSM's Task Scheduler"),
]

DO = [("run", "Run it"), ("report", "Just tell me what it would do")]


@dataclass
class Step:
    """One feature in a flow, and how this flow wants it run.

    `id` is what the "has this tree changed since last time" mark is filed
    under, and it is why a step has an identity of its own rather than being
    known by its position. A flow may legitimately hold the same feature twice -
    send to develop, cull, send to develop again - and two steps sharing one
    mark would each decide the other had already caught up. Moving a step up or
    down must also not lose what it knew.
    """
    id: str = ""
    task: str = ""
    on: bool = True
    do: str = "run"            # "run" or "report"
    watch: str = ""            # a Setup tree key; "" means work it out
    opts: dict = field(default_factory=dict)   # per-step overrides

    def key(self) -> str:
        return self.id or self.task


@dataclass
class Flow:
    id: str = ""
    name: str = ""
    on: bool = False           # running by itself
    every: int = 15            # minutes, when the app fires it
    deep: bool = True          # notice edits inside files
    fired_by: str = BY_APP
    # Folders this flow never walks into - the phone dump, a video folder kept
    # beside the library. ADDED to Setup's list rather than replacing it, so
    # building a flow cannot quietly undo a decision made once (core/exclude.py).
    exclude: list = field(default_factory=list)
    steps: list = field(default_factory=list)

    def live(self) -> list:
        return [s for s in self.steps if s.on and s.task]


# ------------------------------------------------------------------- storing

def _path() -> str:
    try:
        return store_path(FILE)
    except Exception:                                  # noqa: BLE001
        return ""


def _as_flow(raw: dict) -> Flow:
    steps = []
    for s in (raw.get("steps") or []):
        if not isinstance(s, dict):
            continue
        steps.append(Step(
            id=str(s.get("id") or "") or step_id(),
            task=str(s.get("task") or ""),
            on=bool(s.get("on", True)),
            do=str(s.get("do") or "run"),
            watch=str(s.get("watch") or ""),
            opts=dict(s.get("opts") or {})))
    return Flow(
        id=str(raw.get("id") or ""),
        name=str(raw.get("name") or "Flow"),
        on=bool(raw.get("on", False)),
        every=max(1, int(raw.get("every") or 15)),
        deep=bool(raw.get("deep", True)),
        fired_by=str(raw.get("fired_by") or BY_APP),
        exclude=[str(x).strip() for x in (raw.get("exclude") or [])
                 if str(x).strip()],
        steps=steps)


def read() -> list:
    """Every flow. Never raises, and never empty - see `_first_time`."""
    where = _path()
    stored = None
    if where and os.path.isfile(where):
        try:
            with open(where, "r", encoding="utf-8") as fh:
                got = json.load(fh)
            if isinstance(got, dict) and got.get("v") == VERSION:
                stored = got.get("flows")
        except (OSError, ValueError):
            stored = None
    if not isinstance(stored, list) or not stored:
        return _first_time()
    return [_as_flow(f) for f in stored if isinstance(f, dict)]


def write(flows: list) -> bool:
    """Best effort. A flow that cannot be written is not a reason to lose a run."""
    where = _path()
    if not where:
        return False
    try:
        tmp = where + ".part"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"v": VERSION, "at": time.time(),
                       "flows": [asdict(f) for f in flows]}, fh, indent=1)
        os.replace(tmp, where)
        return True
    except OSError:
        return False


def get(flow_id: str, flows: list | None = None) -> Flow | None:
    for f in (read() if flows is None else flows):
        if f.id == flow_id:
            return f
    return None


def put(flow: Flow) -> list:
    """Add or replace one flow, keeping the rest and their order."""
    flows = read()
    for i, f in enumerate(flows):
        if f.id == flow.id:
            flows[i] = flow
            break
    else:
        flows.append(flow)
    write(flows)
    return flows


def drop(flow_id: str) -> list:
    flows = [f for f in read() if f.id != flow_id]
    write(flows)
    return flows


def step_id() -> str:
    """A short name of its own for one step, never a task name.

    Never a task name on purpose: the three steps carried over from the old
    hard-coded loop keep the keys their marks are already filed under, and a
    generated id must not collide with those and inherit a mark that belongs to
    something else.
    """
    return "s" + uuid.uuid4().hex[:8]


def new_id(name: str, flows: list | None = None) -> str:
    base = "".join(c if c.isalnum() else "-" for c in str(name).lower()).strip("-")
    base = base or "flow"
    taken = {f.id for f in (read() if flows is None else flows)}
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


# --------------------------------------------------------------- the first one

DEVELOPING = "developing"

# The loop that used to be written into the source, now one flow among however
# many you make. Its steps are the same three, in the same order, watching the
# same trees - so an install that upgrades keeps doing exactly what it did.
FIRST = [
    {"task": "ratings", "do": "run"},
    {"task": "develop", "do": "run"},
    # Filing MOVES finished photographs into the library, so a wrong answer is a
    # photograph somewhere you did not put it. It reports until you have watched
    # it a few times and said otherwise.
    {"task": "filed", "do": "report"},
]


def _first_time() -> list:
    """The developing loop, carried over from whatever the old settings said.

    An upgrade must not quietly switch the automation off, nor quietly switch it
    on: both are changes nobody asked for, and one of them starts moving
    photographs. So the old `auto_*` keys are read once and become the first
    flow, exactly as they were.
    """
    from . import settings as S
    saved = S.load()
    steps = []
    for one in FIRST:
        key = one["task"]
        steps.append(Step(
            # The key its "last seen" mark is already filed under, so an upgrade
            # does not make every step look freshly changed and run once for no
            # reason on the first pass after it.
            id=key,
            task=key,
            on=bool(saved[f"auto_{key}_on"]),
            do=str(saved[f"auto_{key}_do"] or one["do"])))
    return [Flow(id=DEVELOPING, name="Developing loop",
                 on=bool(saved["auto_on"]),
                 every=int(saved["auto_every"] or 15),
                 deep=bool(saved["auto_deep"]),
                 fired_by=BY_APP, steps=steps)]


# ------------------------------------------------- what a step actually does

# The Setup trees, in the order they read as a list of places.
TREES = [
    ("library", "The library"),
    ("previews", "The previews tree"),
    ("raw", "The RAW tree"),
    ("video", "The video tree"),
    ("develop", "The develop tree"),
    ("inbox", "Lightroom's export folder"),
]
TREE_NAMES = dict(TREES)


def watched_key(task, step=None) -> str:
    """Which Setup tree this step watches for changes.

    Chosen on the step when you have said; otherwise worked out from the task,
    and the rule is the plain one: **a feature's first folder option is the tree
    it works from**. Syncing ratings opens with "Where you rated", which is the
    previews tree; sending to develop opens with the library; filing opens with
    the export folder.

    That is not a coincidence to lean on quietly - it is how the forms are
    written, top to bottom in the order the work happens - so it is stated here,
    shown in the editor as "watches: the previews tree", and overridable. A task
    whose first folder names no Setup tree simply has no default, and the editor
    asks rather than guessing.
    """
    if step is not None and step.watch:
        return step.watch
    if task is None:
        return ""
    if getattr(task, "watches", ""):
        return task.watches
    for o in task.options:
        if getattr(o, "kind", "") == "folder" and not getattr(o, "many", False):
            return o.setting or ""
    return ""


def options_for(task, step, saved=None) -> dict:
    """Every option this step will run with, and where each value came from.

    `{name: {"value": ..., "from": "setup"|"step"|"default", "label": ...}}`

    The whole point is that nothing is invisible. The bug this replaces was a
    threshold typed on a tab that was not the threshold used at four in the
    morning, with neither end saying so; a step now shows every value it will
    use and which of the three places it came from.
    """
    out = {}
    overrides = dict((step.opts if step else {}) or {})
    for o in task.options:
        setting = getattr(o, "setting", "")
        if o.name in overrides:
            value, where = overrides[o.name], "step"
        else:
            value = o.saved_default()
            where = "setup" if setting and value not in (None, "") else "default"
        out[o.name] = {"value": value, "from": where, "label": o.label}
    return out


def raw_for(task, step) -> dict:
    """What to hand `Task.make_plan` - the overrides only.

    Deliberately only the overrides. Everything else is left absent so that the
    task's own `coerce` fills it from Setup, which is the single place those
    values live. Copying them in here would make this a second copy that goes
    stale the moment Setup is edited - which is exactly the failure that made
    the background run use different thresholds from the tab.
    """
    raw = {}
    for o in task.options:
        if step is not None and o.name in (step.opts or {}):
            raw[o.name] = step.opts[o.name]
    return raw


# --------------------------------------------------- would this eat itself?

def _same_place(a: str, b: str) -> bool:
    """Do these two settings point at the same tree, or one inside the other?

    Compared as PATHS, not as keys. The disaster this exists to catch is not
    "two steps named the same tree" - nobody does that - it is Lightroom's
    export folder being set to the develop tree, or to a folder inside it. Two
    different keys, one place on the disk, and every step behaving correctly.
    """
    from .paths import under
    a = str(a or "").strip()
    b = str(b or "").strip()
    if not a or not b:
        return False
    try:
        if os.path.realpath(a) == os.path.realpath(b):
            return True
    except OSError:
        pass
    return under(a, b) or under(b, a)


def trouble(flow: Flow, saved=None, tasks=None) -> list:
    """Every reason this flow should not run, worst first. Empty is a good flow.

    One shape matters above the rest and it is a RING: a step copies into a
    tree, a later step moves things out of that tree into a tree the first one
    reads. Nothing is broken at any point - each step does exactly what it was
    told - and the result is photographs multiplying into the library on a
    timer.

    The hard-coded version of this checked one case: exports landing in the
    develop tree. Assembling a flow from a dropdown makes that one case out of
    many, so it is worked out from what each feature says it reads, copies and
    moves, against the actual paths in Setup.

    Cheap to check, unrecoverable to get wrong, so it refuses rather than
    running the safe two-thirds of the flow.
    """
    from . import settings as S
    from app import registry as R
    saved = S.load() if saved is None else saved
    get_task = (lambda n: R.get(n)) if tasks is None else (lambda n: tasks.get(n))

    said = []
    live = flow.live()
    if not live:
        said.append("Every step is switched off, so this flow would do nothing.")
        return said

    known = []
    for step in live:
        task = get_task(step.task)
        if task is None:
            said.append(f"There is no tool called {step.task!r} any more. "
                        f"Remove that step, or the flow does not know what it "
                        f"would be running.")
            continue
        known.append((step, task))

    where = {key: str(saved[key] or "").strip() for key, _label in TREES}

    for step, task in known:
        for lands in list(task.copies_to) + list(task.moves_to):
            for other, other_task in known:
                if other is step:
                    continue
                for taken in other_task.moves_to:
                    if not other_task.reads:
                        continue
                    # does the other step take things OUT of where this one puts
                    # them, and put them where this one reads?
                    from_trees = [t for t in other_task.reads if t not in
                                  other_task.moves_to]
                    if not any(_same_place(where.get(lands), where.get(src))
                               for src in from_trees):
                        continue
                    if taken not in task.reads:
                        continue
                    said.append(
                        f"'{task.title}' puts photos into "
                        f"{TREE_NAMES.get(lands, lands)}, and '{other_task.title}' "
                        f"takes them out of there and into "
                        f"{TREE_NAMES.get(taken, taken)} - which '{task.title}' "
                        f"reads. Every pass would send the same photos round "
                        f"again, each step doing exactly what it was told. Give "
                        f"them separate folders in Setup.")

    seen = {}
    for step, task in known:
        seen.setdefault(task.name, []).append(step)
    for name, steps in seen.items():
        if len(steps) > 1:
            said.append(
                f"'{get_task(name).title}' is in this flow {len(steps)} times. "
                f"That is allowed - a cull between two sends is a real thing to "
                f"want - but each one watches its own mark, so check the order "
                f"is what you meant.")

    undescribed = [t.title for _s, t in known
                   if not (t.reads or t.copies_to or t.moves_to)]
    if undescribed:
        said.append(
            "Nothing is known about what " + ", ".join(sorted(set(undescribed)))
            + " reads and writes, so the loop check above could not include "
              "it. That is not a warning about this flow - it is this app "
              "saying what it did not check.")
    return said


def refusals(flow: Flow, saved=None, tasks=None) -> list:
    """Only the ones that must stop a run. The rest are worth saying, not stopping.

    A ring is unrecoverable and refuses. "This tool is in the flow twice" and
    "I could not check this step" are things you should be told and then be
    allowed to decide about - an app that refuses to run over something it
    merely has no opinion on is an app people work around.
    """
    return [x for x in trouble(flow, saved, tasks)
            if "round again" in x or "no tool called" in x
            or "would do nothing" in x]
