"""Every feature is a task, and every task declares itself.

This is the part that decides how much work the tenth feature costs.

The Windows app grew a hand-written form, a hand-written results list and a
hand-written summary for each of its seven jobs, which is most of why its
interface is four and a half thousand lines. Here a task declares its options as
data and provides two functions:

    plan(opts)  -> Plan     reads, decides, and writes NOTHING
    apply(plan) -> Result   does what the plan said

Everything else is generic. The web page renders its form from OPTIONS. The
scheduler runs plan-then-apply for anything registered. So does the command line.
A new feature is one module and one test file - no interface work, no API route,
no scheduler change.

The plan/apply split is not a new idea here either: it is exactly the Preview
then Apply that the Windows app already works by, so the logic ports across
unchanged and its tests come with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


# A box that was never filled in is not the same as a box somebody emptied.
# Both arrive as "" once a form has been through a browser, and treating them the
# same means "leave blank to leave RAWs alone" is a sentence the app does not
# keep: the setting from Setup fills the box straight back in, and a cull you
# thought you had limited to JPEGs quietly moves negatives too.
MISSING = object()


# --------------------------------------------------------------------- options

@dataclass
class Option:
    """One thing a task needs to know, described well enough to draw a control.

    `group` and `advanced` are the difference between a form you can read and a
    wall of fifteen boxes. Options belonging to one decision carry the same group
    name and are drawn together; a group marked `advanced` starts folded away,
    because a setting nobody changes should not be the third thing you see.

    `help` is not a hint printed under the label - it is what appears when the
    (i) beside it is pressed. Most of these are two sentences explaining a trap,
    and having all of them on screen at once means none of them gets read.

    `setting` names a Setup key this option falls back to when it is left blank.
    """
    name: str
    label: str
    default: Any = None
    help: str = ""
    kind: str = "text"
    group: str = ""
    advanced: bool = False
    setting: str = ""
    # The name of a Flag that must be OFF for this to be editable. For settings
    # that are read by something running in the background: changing the steps
    # of a loop WHILE it is looping is a question nobody wants to think about,
    # and a form that lets you is a form that will be half-changed when the next
    # pass fires.
    needs_off: str = ""
    # "choice=value": shown only while that choice has that value. A box that
    # means nothing for the answer picked is a box somebody fills in anyway.
    only_when: str = ""

    def saved_default(self) -> Any:
        """What this option starts as: the saved setting, or the plain default.

        This is how Setup actually reaches the rest of the app. An option naming a
        setting is filled from it - in the form, on the command line and in a
        scheduled run alike - and typing something in overrides it for that run
        only. Without this, "set it once" would be a claim the app does not keep.
        """
        if not self.setting:
            return self.default
        from core import settings as _s          # here, to keep the import shallow
        value = _s.load()[self.setting]
        return self.default if value in (None, "") else value

    def coerce(self, raw: Any) -> Any:
        if raw is MISSING or raw is None or raw == "":
            return self.saved_default()
        return raw

    def describe(self) -> dict:
        return {"name": self.name, "label": self.label, "kind": self.kind,
                "default": self.saved_default(), "help": self.help,
                "group": self.group, "advanced": self.advanced,
                "setting": self.setting, "needs_off": self.needs_off,
                "only_when": self.only_when}


@dataclass
class Folder(Option):
    """A path. Blank is blank - never the string "None", which is what an unset
    default turns into by the time it has been through a form and back."""
    kind: str = "folder"
    default: str = ""
    must_exist: bool = True

    def coerce(self, raw: Any) -> Any:
        """Not asked about -> the setting. Asked and emptied -> empty.

        The difference matters only for folders, and only because several tasks
        say "leave blank to leave those alone". They meant it.
        """
        if raw is MISSING or raw is None:
            return self.saved_default()
        text = str(raw).strip()
        return text
    # True when this box names the TOP of a tree that mirrors another - the RAW
    # tree, the previews tree, the library as an anchor. Two things follow from
    # it, and they are two halves of one idea: the form may fill it in by
    # following the folder you picked, and the task will strip that position
    # back off before mirroring into it. Without the second half the first is a
    # bug that writes ...\Photos Raw\2022\Spain\2022\Spain.
    tree: bool = False
    # Several folders in one run, drawn as chips like an exclusion list and
    # carried as one newline-separated string. Still `kind="folder"`, because
    # everything that guards a folder - the allowed-roots check, the tree
    # following, the remembering - has to keep guarding it.
    many: bool = False

    def describe(self):
        d = super().describe()
        d["tree"] = self.tree
        d["many"] = self.many
        return d

    def chosen(self, value) -> list:
        """The folders in this box: one, or a list, always as a list."""
        return [line.strip() for line in str(value or "").splitlines()
                if line.strip()]


@dataclass
class FilePath(Option):
    """One FILE, chosen rather than typed.

    A folder box has had a Browse button since the beginning and a file box
    never did, so the three places that want a file - the photograph whose real
    time you know, the GeoNames dumps - were the only boxes in the app where you
    had to type a full path correctly from memory. Same picker, listing files as
    well, filtered to the extensions the task can actually use.
    """
    kind: str = "file"
    default: str = ""
    suffixes: tuple = ()          # ".zip", ".txt" - what the task can read

    def describe(self):
        d = super().describe()
        d["suffixes"] = list(self.suffixes)
        return d


@dataclass
class Folders(Option):
    """Several folders, chosen rather than typed.

    A list of paths in a text box is a list of paths you get wrong: one typo and
    the folder you meant to leave out is scanned anyway, silently, because a name
    that matches nothing looks exactly like a name that matches nothing on
    purpose. Picked from a browser they are always real.

    Carried as one newline-separated string so that everything downstream - the
    form, the command line, the settings file, a remembered value - stays plain
    text and needs no special case. `chosen()` is the only place that knows.
    """
    kind: str = "folders"
    default: str = ""

    @staticmethod
    def chosen(value) -> list:
        text = str(value or "")
        out = []
        for line in text.replace(",", "\n").splitlines():
            item = line.strip().strip('"')
            if item and item not in out:
                out.append(item)
        return out


@dataclass
class Pattern(Option):
    """A folder-name pattern, typed with its variables at hand.

    Drawn as a box with the variables as buttons under it, a line showing what
    it makes for a sample photo while you type, and a way to keep it under a
    name. The variables themselves are `core.naming`'s, so the page and the task
    can never disagree about which exist.
    """
    kind: str = "pattern"
    default: str = ""

    def describe(self) -> dict:
        from core import naming
        d = super().describe()
        d["variables"] = [{"name": n, "label": l, "example": e}
                          for n, l, e in naming.VARIABLES]
        d["kept"] = [{"name": n, "pattern": p} for n, p in naming.saved()]
        return d


@dataclass
class Flag(Option):
    kind: str = "flag"
    default: bool = False

    def coerce(self, raw):
        if raw is MISSING or raw is None:
            return bool(self.saved_default())
        if isinstance(raw, str):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        return bool(raw)


@dataclass
class Secret(Option):
    """A box whose contents are not shown, and never come back out.

    Only one thing uses this - the password - and it is a kind of its own for
    two reasons a plain text box cannot cover: the characters are hidden as you
    type, and the browser's password manager is told what this is, so it offers
    to remember it and does not autofill a library path into it.

    It is never given a saved default. Every other option in this app fills
    itself in from what you last used; a password box that did that would be a
    password sitting in the page's HTML, readable by anything that can see the
    page at all.
    """
    kind: str = "secret"
    default: str = ""

    def saved_default(self):
        return ""

    def describe(self):
        d = super().describe()
        d["default"] = ""
        return d


@dataclass
class Number(Option):
    kind: str = "number"
    minimum: float | None = None
    maximum: float | None = None
    step: float = 1

    def coerce(self, raw):
        if raw is MISSING or raw is None or raw == "":
            return self.saved_default()
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return self.saved_default()
        if self.minimum is not None:
            v = max(self.minimum, v)
        if self.maximum is not None:
            v = min(self.maximum, v)
        return int(v) if float(v).is_integer() and self.step >= 1 else v

    def describe(self):
        d = super().describe()
        d.update(min=self.minimum, max=self.maximum, step=self.step)
        return d


@dataclass
class Choice(Option):
    kind: str = "choice"
    choices: list = field(default_factory=list)
    # Drawn as a row of tabs rather than a dropdown, and changing one runs the
    # task again straight away. For the two or three choices that are really a
    # VIEW of the same answer - which folders to show, which runs to list - a
    # dropdown hides the options you did not pick and makes looking at each in
    # turn a three-click job. A tab row shows what is on offer and costs one.
    tabs: bool = False

    def offered(self) -> list:
        """The choices, resolved.

        A callable is allowed because some lists cannot exist at import time: the
        History tab offers one entry per task that writes, and it is itself a
        task being imported. Asked for at import it sees an almost empty
        registry and quietly offers nothing.
        """
        got = self.choices
        if callable(got):
            try:
                got = got()
            except Exception:                      # noqa: BLE001
                got = []
        return list(got or [])

    def coerce(self, raw):
        if raw is MISSING or raw is None or raw == "":
            return self.saved_default()
        for c in self.offered():
            value = c[0] if isinstance(c, (tuple, list)) else c
            if str(value) == str(raw):
                return value
        return self.saved_default()

    def describe(self):
        d = super().describe()
        d["tabs"] = self.tabs
        # A third element names the heading this choice sits under. Fifteen ways
        # to break a folder up in one flat list is a list nobody reads to the
        # bottom of; "By date" and "By place" over the same fifteen is a decision
        # you make in one glance and then a short list.
        d["choices"] = [
            {"value": c[0], "label": c[1],
             "group": c[2] if len(c) > 2 else ""} if isinstance(c, (tuple, list))
            else {"value": c, "label": str(c), "group": ""}
            for c in self.offered()]
        return d


# ------------------------------------------------------------ plans and results

@dataclass
class Row:
    """One thing a plan intends to do, in terms a person can check."""
    what: str = ""
    name: str = ""
    source: str = ""
    target: str = ""
    detail: str = ""
    # The same information as `detail`, split into the columns a task named in
    # `Plan.columns`. One string per extra column, in that order.
    #
    # `detail` stays the fallback and is never dropped: a task that has not been
    # given columns still reads properly, and a row whose cells run out simply
    # has empty ones rather than the table shifting sideways - a table that
    # silently slides values under the wrong heading is worse than a sentence.
    cells: list = field(default_factory=list)
    size: int = 0
    approximate: bool = False
    data: dict = field(default_factory=dict)
    # Which of `Plan.groups` this row belongs under, by key. Blank means it
    # stands on its own, which is what almost every task wants.
    group: str = ""
    # One button on this row, when the row is a thing you might want to DO
    # something about: {"label", "task", "option", "value"}. The page draws it
    # in a column of its own and opens that feature with that option filled in.
    #
    # Generic because the first use would otherwise have been a special case in
    # the page for History - and the second one, whenever it comes, would have
    # been a second special case.
    act: dict = field(default_factory=dict)


@dataclass
class Plan:
    """What would happen, and why. Never a side effect.

    `stats` is the summary; `notes` is the reasoning; `skipped` is everything the
    task decided NOT to touch and the reason - which is usually the part worth
    reading, and the part a tool is most tempted to leave out.

    `opts` carries the settings the plan was made from, so `apply` sees exactly
    what the person chose. Without it an option that only affects writing - "keep
    a copy of each original", say - is accepted, shown, and then quietly ignored.
    """
    task: str = ""
    opts: dict = field(default_factory=dict)
    rows: list[Row] = field(default_factory=list)
    # A shape the page can draw as a folder tree. Optional, and generic on
    # purpose: a task that has something hierarchical to say fills it in, and the
    # page grows a tree view for every such task at once rather than one of them
    # gaining a hand-written display nothing else can use.
    tree: list[dict] = field(default_factory=list)
    # Numbers drawn rather than listed: stat tiles, donuts, bars, a heatmap.
    # A dict rather than a class because it crosses to the page as JSON and
    # every shape in it is one the page knows how to draw - see `chartsCard`.
    charts: dict = field(default_factory=dict)
    stats: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    blocked: str = ""          # set to refuse Apply outright, with the reason
    # What to head the columns of the rows table with. Optional: most tasks are
    # moving files and "File / Detail / Where" is right for all of them, but
    # History's rows are runs, not files, and a column called File over a list
    # of times is the kind of small lie that makes a page feel untrustworthy.
    #
    # More than three names means the rows carry `cells`: "was 3 stars" and "now
    # 5" belong in two columns you can sort and compare down the page, not in one
    # sentence per row that has to be read one at a time.
    columns: list[str] = field(default_factory=list)
    # Whether THIS plan would write anything, when that is not a fixed property
    # of the task. None means "whatever the task says". Find brackets is a report
    # until a tag is typed into it, and offering Go ahead for a report - or
    # withholding it when there is something to write - are both lies about what
    # the button does.
    writes: bool | None = None
    # A list of values this plan CHOSE, which the person may want to correct
    # before anything happens - the town names a place sort worked out, say.
    # {"option": which option to write back into, "title", "note",
    #  "items": [{"name", "count"}]}. Generic on purpose: the page grows an
    # editable list for every task that has one rather than one of them getting
    # a hand-written display nothing else can use.
    picks: dict = field(default_factory=dict)
    # Headings the rows are gathered under, in the order they should be drawn.
    #
    # Four hundred duplicate files are not four hundred decisions. They are
    # usually a dozen: this folder against that one, over and over. A flat list
    # makes you read the same judgement forty times and still not notice that it
    # IS the same judgement - so a task that knows how its rows cluster says so
    # here, the page draws each cluster closed with a line summarising it, and
    # opening one is how you get to the files.
    #
    # {"key": matches Row.group, "label", "cells": [...] laid into the same
    #  columns as the rows, "note": a sentence under the label, "actions":
    #  [{"label", "option", "value", "help"}] - each drawn as a button that puts
    #  `value` into that option and looks again, which is how a choice the task
    #  made by rule becomes one you can overrule without typing a path.}
    groups: list[dict] = field(default_factory=list)
    # Names an editor the page should draw above the table for this plan.
    #
    # There is exactly one so far - "flows" - and it exists because a flow is a
    # variable number of steps, each with the settings of a different feature,
    # and no list of options declared once at import time can be that. The plan
    # still describes the flows as ordinary rows underneath, so the command line
    # and a browser with the editor turned off both still show what is there.
    editor: str = ""
    # What this particular plan would change, when the generic reading of it
    # would be wrong. Merged over `impact_of`'s own answer - see there.
    impact: dict = field(default_factory=dict)
    # Buttons for the whole plan, not for one row: each opens another feature
    # with one option already filled in, exactly like `Row.act`.
    #
    # History is why. "Put a run back" and "Clear the history" are both things you
    # do FROM the list, to the list - neither belongs to any one row, and the
    # alternative was a tab of its own in a sidebar nobody would look in for it.
    # {"label", "task", "option", "value", "help"}
    acts: list[dict] = field(default_factory=list)
    # Whatever that editor needs that a row cannot carry.
    #
    # A row is a name and some cells, on purpose: the command line prints them,
    # a table shows them, and a plan that smuggled a dict per row into the page
    # would break the day the rows were trimmed. But an editor for a whole TAB -
    # the sets of chart bands, the arrangements of the dashboard - is about the
    # tab, not about any row, and this is where that goes. Ordinary JSON, sent
    # as it is; nothing outside the page reads it.
    data: dict = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.rows)


def impact_of(task: "Task", plan: "Plan") -> dict:
    """What pressing Apply would change, in four facts, for every task at once.

    The audit's finding was that the page asks you to approve a list of four
    hundred rows and never says the one sentence that would let you check it:
    WHAT is being done, to HOW MANY, OUT OF where, INTO where. Each of those
    exists already - the task knows its verb, the plan knows its rows, and the
    options carry the folders - they were simply never put side by side.

    Generic on purpose. Reading it from the options means every task gains the
    box at once, including the next one, rather than thirteen authors each
    writing their own summary and four of them forgetting. The reading is
    deliberately literal:

        from    the first folder box that has something in it
        into    any other folder box that has something different in it

    which is right because that IS the shape of every task here - one tree you
    are working on, and nought or more it writes into. A task for which it is
    wrong says so in `plan.impact`, and what it says wins.
    """
    # A list of folders to LEAVE OUT is not somewhere anything is written. It is
    # always the `folders` kind, and reading it as a destination would print
    # "into: the folders you told it to skip", which is the opposite of true.
    folders = [o for o in task.options
               if o.kind == "folder" and not o.name.startswith(("skip", "exclude"))]
    source, into = "", []
    for o in folders:
        value = str(plan.opts.get(o.name) or "").strip().splitlines()
        first = value[0].strip() if value else ""
        if not first:
            continue
        if not source:
            source = first
            continue
        if first != source and all(first != w["path"] for w in into):
            into.append({"label": o.label, "path": first})
    out = {
        "verb": task.verb, "unit": task.unit,
        "count": len(plan.rows),
        "from": source, "into": into[:4],
        "risk": task.risk, "undo": task.undo,
        "writes": task.writes if plan.writes is None else bool(plan.writes),
    }
    out.update(plan.impact or {})
    return out


_NUMBERS = __import__("re").compile(r"\d+")


def _gist(text: str) -> str:
    """One failure, reduced to the part that is the same for all of them.

    Paths and numbers are what differ between twenty-eight instances of one
    problem, so they come out: "[Errno 13] Permission denied: '<a path>/a.jpg'"
    and the same for b.jpg have to land in one group or the grouping does
    nothing. Quoted paths go entirely; bare numbers become #, which also folds
    "read back 3 instead of 4" and "read back 1 instead of 5" together - the
    same fault, and it is the fault that is worth naming.
    """
    text = " ".join(str(text).split())
    out = []
    for piece in text.split():
        stripped = piece.strip("'\"")
        if ("/" in stripped or "\\" in stripped) and len(stripped) > 3:
            continue                       # a path: the one thing that varies
        out.append(_NUMBERS.sub("#", piece))
    said = " ".join(out).strip(" :,").strip()
    return said[:160] or "it failed"


def _denied_note(paths) -> str:
    """Never in the way: a run that failed must still report what it failed at.

    This asks the filesystem who owns a folder, and a folder that refused a
    write is exactly the kind that might refuse a stat as well. An explanation
    that raises while explaining would turn a task's own error into a traceback
    about the error.
    """
    try:
        from core import perms as _perms
        return _perms.denied_note(paths)
    except Exception:                                  # noqa: BLE001
        return ""


@dataclass
class Result:
    """What a run actually did, and what went wrong with it.

    Failures are recorded by CAUSE rather than one line per file, and that is
    not tidiness. A sync that reported "103 done, 28 failed" wrote 28 lines
    naming 28 photographs, the payload showed the first 60 of them, and the one
    thing the list did not say anywhere was WHY - so twenty-eight instances of
    one fixable problem read as twenty-eight separate mysteries. Grouped, the
    same run says "28 x Permission denied" and names three examples, which is a
    thing you can go and fix.
    """
    done: int = 0
    failed: int = 0
    cancelled: bool = False
    details: list[str] = field(default_factory=list)
    stats: list[tuple[str, str]] = field(default_factory=list)
    # cause -> the files it happened to, in the order they were met
    faults: dict = field(default_factory=dict)
    # Space this run gave back, and whether it is really gone ("freed") or
    # sitting in a pile waiting to be ("aside"). Recorded once, centrally,
    # beside the run log - see core/reclaimed.py for why it is kept at all.
    reclaimed: int = 0
    reclaim_kind: str = ""
    # Every file this run moved, as [from, to], in the order it happened.
    # Written by `core/moves.shift`, kept by `core/runlog`, and what lets
    # History offer to put a run back. A copy is never in here - undoing a copy
    # means deleting something, which is a different decision.
    moves: list = field(default_factory=list)

    def blame(self, path: str, why) -> str:
        """Record one failure and return the line to show beside its row.

        Counts `failed` as well, so a task cannot record the reason and forget
        the tally, or the other way round - which is two numbers that disagree
        about the same run.
        """
        text = str(why).strip() or "it failed"
        self.faults.setdefault(_gist(text), []).append(path)
        self.failed += 1
        return f"FAILED: {text}"

    def lines(self) -> list:
        """Everything worth showing: the causes first, then the task's own lines.

        Computed rather than folded into `details` as it goes, so no task can
        forget to call it and quietly go back to reporting twenty-eight
        mysteries. Causes come FIRST because they are the part you act on - a
        list that opens with sixty file names and explains itself at the bottom
        is a list nobody scrolls.
        """
        import os as _os
        out = []
        denied = []
        for cause, paths in sorted(self.faults.items(),
                                   key=lambda kv: (-len(kv[1]), kv[0])):
            shown = ", ".join(_os.path.basename(x) for x in paths[:3])
            if len(paths) > 3:
                shown += f", and {len(paths) - 3:,} more"
            out.append(f"{len(paths):,} x  {cause}\n    {shown}")
            if "permission denied" in cause.lower():
                denied.extend(paths)
        # And WHY, which the grouping cannot say on its own. "156 x Permission
        # denied" is one mystery instead of a hundred and fifty-six, which was
        # worth doing and is still not something anybody can act on.
        if denied:
            said = _denied_note(denied)
            if said:
                out.append(said)
        return out + list(self.details)


class Stopped(Exception):
    """Raised through a progress callback to stop a scan that is still looking.

    Planning writes nothing, so unwinding out of the middle of one costs nothing
    and needs no cleanup - which is why this can be an exception rather than a
    flag every loop has to remember to check. A task earns a working Stop button
    by accepting `progress`; one that does not is not offered a button it would
    ignore.
    """


def _wants_progress(fn) -> bool:
    try:
        import inspect
        return "progress" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


# ------------------------------------------------------------------- the registry

@dataclass
class Task:
    name: str
    title: str
    summary: str
    options: list[Option]
    plan: Callable[[dict], Plan]
    apply: Callable[..., Result]
    writes: bool = True        # False for look-only tasks, so the UI can say so
    order: int = 100
    icon: str = "dot"          # which glyph the sidebar draws beside it
    parent: str = ""           # drawn as a tab under that task, not on its own
    tab: str = ""              # what to call that tab; defaults to the title
    # Reachable, but not in the sidebar - it has a place of its own in the
    # header instead. For the one or two things that are not steps in any
    # workflow: History is somewhere you GO to look back, and a list of twenty
    # features with one of them meaning "what happened last week" reads as
    # twenty steps, nineteen of which you do and one of which you do not.
    hidden: bool = False
    # This tab SAVES rather than does. Everything else here shows you what would
    # happen and waits for Go ahead, which is right for moving four hundred
    # photographs and absurd for a settings page: "show me what would happen if I
    # wrote down where my library is". Worse, it meant typing a path and walking
    # away saved nothing at all, silently, which is exactly how somebody ends up
    # certain the app does not remember anything.
    #
    # A settings task gets one obvious Save button that saves immediately.
    settings: bool = False
    # What to call the plan button when "Show me what would happen" is the wrong
    # sentence - "Run one pass now" on the Automation tab.
    run_label: str = ""

    # ---- what this feature does to which trees, for the flow checks
    #
    # Named as Setup tree keys ("library", "develop", "inbox", ...). A flow is
    # now anything you assemble from a dropdown, so "these two steps together
    # would multiply photographs into the library on a timer" has to be
    # something the app can work out rather than one refusal somebody wrote by
    # hand. Three facts are enough for that:
    #
    #   reads       it opens files there and decides from them
    #   copies_to   a copy lands there; the source is untouched
    #   moves_to    files ARRIVE there and LEAVE wherever they came from
    #
    # The dangerous shape is a ring: A copies into a tree that B moves out of,
    # into a tree A reads. Every photograph goes round it again on every pass,
    # with each step doing exactly what it was told.
    #
    # A task that declares nothing makes no claim, and the check says so rather
    # than reporting a flow as safe that it could not actually examine.
    reads: tuple = ()
    copies_to: tuple = ()
    moves_to: tuple = ()
    # Which tree a flow should watch for changes, when the first folder option
    # is not it. Blank means "work it out" - see core/flows.watched_key.
    watches: str = ""
    # Names an editor the page draws for this tab, above everything else and
    # as soon as the tab is opened rather than after a plan.
    #
    # There is exactly one, "flows", and it exists because a flow is a variable
    # number of steps each carrying a different feature's settings - which no
    # list of options declared once at import time can be. A tab whose whole
    # purpose is the editor must not make you press "Have a look" to see it.
    editor: str = ""
    # Opened from another feature's row, never from a list.
    #
    # "Put a run back" is a thing you do TO a run, and the run is in History -
    # so a card for it in the tools, where it can only say "pick a run first",
    # would be a dead end with a name. It is still an ordinary task: same plan,
    # same Apply, same log.
    inline: bool = False
    # Should this tab's option groups start folded away?
    #
    # Search has twenty-two boxes across six groups, and on a phone that is one
    # column you scroll past to reach the button. Folded, it is six lines you
    # can read - and any group you have actually filled in opens itself, so
    # folding can never hide something that is in force. Every feature with
    # more than eight options folds (Setup and the colour labels excepted: they
    # are pages you read through, not a form you fill in once); the first group,
    # which holds the folder, starts open.
    fold_groups: bool = False
    # ---- what to call what this does, so a button can say it
    #
    # "Go ahead with these 184" is the same sentence on every tab in the app,
    # which means the one word that would tell you what is about to happen -
    # move, copy, create, delete - is the one word it leaves out. A task that
    # names its verb and its unit gets "Move 184 files" instead, and the
    # confirmation above it can say the same thing in full.
    #
    # Left blank it falls back to the old sentence rather than guessing: a
    # button that says "Change 184 files" about a task that only writes a tag
    # is worse than one that says nothing.
    verb: str = ""
    unit: str = ""
    # One line, for a list of features. `summary` is two sentences explaining a
    # trap, which is right in a bubble and far too long under a button in a list
    # of forty-six. Left blank it falls back to the first sentence of the
    # summary, which for most tasks is already the line - and `one_line()` is
    # the only thing that decides, so a list cannot disagree with a card.
    line: str = ""
    # How much damage a mistake here does, which decides how hard the page makes
    # you work for it: "high" asks a second time, in a box that names the
    # operation, the number, where it happens and whether it can be undone.
    risk: str = ""
    # Whether it can be undone, in one sentence, in the task's own words.
    # Silence is honest; a cheerful generic "you can always move them back"
    # printed over something irreversible is not.
    undo: str = ""

    def one_line(self) -> str:
        """What this feature is, in one line somebody can scan a list of."""
        if self.line.strip():
            return self.line.strip()
        import re as _re
        said = " ".join(str(self.summary or "").split())
        first = _re.split(r"(?<=[.!?]) ", said)[0] if said else ""
        return first

    def defaults(self) -> dict:
        return {o.name: o.saved_default() for o in self.options}

    def coerce(self, raw: dict) -> dict:
        raw = raw or {}
        return {o.name: o.coerce(raw.get(o.name, MISSING)) for o in self.options}

    def loggable(self, opts: dict) -> dict:
        """The options without anything typed into a Secret box.

        For the run log, which keeps every option holding a path separator: a
        password with a slash in it was written to runs.jsonl in plain text.
        """
        hidden = {o.name for o in self.options if o.kind == "secret"}
        return {k: v for k, v in (opts or {}).items() if k not in hidden}

    def groups(self) -> list[dict]:
        """The options gathered into the groups they should be drawn in.

        Order comes from the option list itself rather than being sorted, so a
        task reads top to bottom the way its author wrote it. Ungrouped options
        come first, under no heading at all - a task with three options should not
        be dressed up as a control panel.
        """
        out: list[dict] = []
        index: dict[str, dict] = {}
        for o in self.options:
            key = o.group or ""
            g = index.get(key)
            if g is None:
                g = {"name": key, "advanced": True, "options": []}
                index[key] = g
                out.append(g)
            # a group is only folded away if EVERY option in it is advanced
            g["advanced"] = g["advanced"] and o.advanced
            g["options"].append(o.describe())
        return out

    def value_sources(self) -> dict:
        """Where each box's opening value actually came from.

        The form used to say "(from Setup)" beside every option that NAMES a
        setting, whether or not the value in the box came from there. So a path
        remembered from the last run was labelled as saved in Setup - and when
        Setup then showed an empty box, the app looked like it had lost it. It
        had not: it was never told to save it.
        """
        out = {}
        for o in self.options:
            where = ""
            if self._remembered(o):
                where = "recent"
            elif o.setting:
                from core import settings as _s
                if str(_s.load()[o.setting] or "").strip():
                    where = "setup"
            out[o.name] = where
        return out

    def start_values(self) -> dict:
        """What each option's box opens with, before anyone types anything.

        Three sources, in this order, and the order is the whole design:

        1. what you last pointed THIS task at, if that folder is still there
        2. the setting from Setup, for options that name one
        3. the option's own default

        Setup answers "where is the library"; the remembered value answers "what
        were you working on". Both are useful and they are not the same question,
        which is why the narrower one wins - and why a remembered folder that has
        since been renamed falls back rather than opening a form on a path that
        no longer exists.
        """
        out = {}
        for o in self.options:
            out[o.name] = self._remembered(o) or o.saved_default()
        return out

    def _remembered(self, o) -> str:
        """What this box was last pointed at, if that still means anything.

        Measured against what Setup says for the box now (`recent.meant`):
        a folder of a library that has since moved is the old library, not
        where you were working.
        """
        if o.kind not in ("folder", "folders"):
            return ""
        from core import recent as _recent
        now = ""
        if o.setting:
            from core import settings as _s
            now = str(_s.load()[o.setting] or "")
        return _recent.meant(self.name, o.name, now,
                             must_exist=o.kind == "folder")

    def describe(self) -> dict:
        start = self.start_values()
        came = self.value_sources()
        groups = self.groups()
        for g in groups:
            for o in g["options"]:
                o["default"] = start.get(o["name"], o["default"])
                o["from"] = came.get(o["name"], "")
        options = [o.describe() for o in self.options]
        for o in options:
            o["default"] = start.get(o["name"], o["default"])
            o["from"] = came.get(o["name"], "")
        out = {"name": self.name, "title": self.title, "summary": self.summary,
               "writes": self.writes, "icon": self.icon, "parent": self.parent,
               "tab": self.tab or self.title, "hidden": self.hidden,
               "settings": self.settings, "run_label": self.run_label,
               # can it say where it has got to - and therefore be stopped
               # part way through looking?
               "watchable": _wants_progress(self.plan),
               "editor": self.editor,
               "fold_groups": self.fold_groups,
               "inline": self.inline,
               "verb": self.verb, "unit": self.unit,
               "line": self.one_line(),
               "risk": self.risk, "undo": self.undo,
               "options": options,
               "groups": groups}
        # The one place local wording edits (Setup > Wording) reach anything:
        # the page, the API and the command line's --help all read this.
        from core import wording as _wording
        return _wording.apply(out, line_from_summary=not self.line.strip(),
                              tab_from_title=not self.tab)

    def settle_trees(self, opts: dict) -> dict:
        """Turn a tree box back into the top of its tree.

        The form is allowed to be helpful: pick `Photos/2022/Spain` and the RAW
        box follows to `Photos Raw/2022/Spain`, because that is where that
        shoot's RAWs actually are and typing it again is the chore. But a
        mirroring destination is supposed to be the TOP of the tree, so handing
        that sub-folder straight to a task writes the position twice -
        `Photos Raw/2022/Spain/2022/Spain/x.RW2`.

        Both halves live here rather than in each task, for the same reason
        `make_plan` exists at all: a task cannot be helpful in one and forget the
        other. Nothing is stripped unless the tail matches exactly, so pointing a
        tree at somewhere unrelated on purpose still works.
        """
        scanned = str(opts.get("folder") or "").strip()
        if not scanned:
            return opts
        from core import paths as _paths
        from core import settings as _settings
        saved = _settings.load()

        # The relative position is measured from whichever tree the scanned
        # folder is in - which is not always the library. "Where you rated" is a
        # folder of the PREVIEWS tree, and its sub-path is what the library and
        # RAW boxes should have followed.
        anchor = ""
        for key in ("library", "raw", "previews"):
            root = str(saved[key] or "").strip()
            if root and _paths.under(scanned, root):
                if len(root) > len(anchor):
                    anchor = root
        anchor = anchor or str(opts.get("library") or "").strip()
        if not anchor:
            return opts

        out = dict(opts)

        # MIRRORING is a mode, not a path you retype.
        #
        # Left to fill the boxes in himself, the anchor kept coming out as the
        # folder being scanned - and then everything landed in the top of the
        # other trees rather than in a matching sub-folder. The trees are already
        # written down once, in Setup; asking again in every form was never a
        # question worth asking. So with this on, the roots come from Setup and
        # the position is worked out from the library, and the boxes are along
        # for the ride. Turning it off is what a one-off destination is for.
        if bool(out.get("mirror", False)) and any(o.name == "mirror"
                                                  for o in self.options):
            for o in self.options:
                if getattr(o, "tree", False) and o.setting:
                    root = str(saved[o.setting] or "").strip()
                    if root:
                        out[o.name] = root
            return out

        for o in self.options:
            if not getattr(o, "tree", False):
                continue
            value = str(out.get(o.name) or "").strip()
            if value:
                out[o.name] = _paths.as_tree_root(value, scanned, anchor)
        return out

    def _cannot_write_into(self, opts) -> str:
        """Refuse BEFORE the run, when the tree it would write into says no.

        A hundred and fifty-six photographs failed one at a time with
        "Permission denied", which is a hundred and fifty-six attempts at
        something that could not have worked once. The task already declares
        which trees it copies or moves into - that is how the ring check knows a
        flow feeds itself - so the same declaration answers this, and every
        feature gains the refusal at once rather than one of them growing a
        hand-written check.

        Measured by making a folder and removing it, because `os.access` knows
        nothing about DSM's access list, which is the half that decides here.
        One mkdir per destination per plan.

        A tree that does not exist yet is not a refusal: plenty of tasks create
        their own destination, and blocking those would be a fault invented out
        of nothing.
        """
        import os as _os
        from core import perms as _perms
        wanted = tuple(self.copies_to) + tuple(self.moves_to)
        if not wanted:
            return ""
        for option in self.options:
            if option.kind != "folder" or option.setting not in wanted:
                continue
            where = str(opts.get(option.name) or "").strip()
            if not where or not _os.path.isdir(where):
                continue
            yes, why = _perms.can_write(where)
            if yes:
                continue
            owner, group = _perms.owner_of(where)
            uid, _gid = _perms.writes_as()
            return (
                f"This app cannot write into {where} - the system said "
                f"\"{why}\". "
                + (f"That folder belongs to user id {owner} group {group}, and "
                   f"this app writes as user id {uid}. " if owner is not None
                   and uid is not None else "")
                + "Nothing is attempted, because every single file would fail "
                  "the same way. Setup > Permissions measures this and writes "
                  "the repair.")
        return ""

    def make_plan(self, raw: dict, progress=None) -> Plan:
        """Coerce the settings, plan from them, and keep them with the plan.

        Every caller should use this rather than calling `plan` directly, so that
        `apply` always knows what was chosen. The CLI, the web page and the
        scheduler then behave identically without any of them plumbing options
        through by hand.
        """
        from core import exclude as _exclude
        opts = self.coerce(raw)
        opts = self.settle_trees(opts)
        # Planning is the slow half on a NAS - a Library survey reads the front
        # of every JPEG over SMB - so it reports progress where it can. Passed
        # only to a plan that asks for it, so a task stays two plain functions
        # and nothing has to be rewritten to gain a progress bar it does not
        # need.
        #
        # The excluded folders are watched around the whole of it, in one place,
        # so that no task can walk a tree and forget to mention that part of it
        # was skipped. A tree quietly smaller than you think is how "0 of 400
        # geotagged" becomes a number nobody can act on.
        met_before = _exclude.what_was_met()
        # Setup's list was always HONOURED by every walk - but outside a flow
        # nothing was keeping count, so a feature run by hand skipped the
        # excluded folders and then reported a smaller library without a word
        # about why. So every plan now runs inside a list of its own, unless a
        # flow has already opened one - a flow's list is Setup's plus its own,
        # and replacing it with Setup's alone would quietly walk into the
        # folders the flow was told to leave.
        import contextlib as _ctx
        # And this run's own "Skip these folders", on top of whichever list is
        # in force - Setup's, or a flow's.
        here = Folders.chosen(opts.get("skip_here")) if "skip_here" in opts else []
        if here:
            fence = _exclude.using(list(_exclude.now()) + here, add_settings=True)
        else:
            fence = (_ctx.nullcontext() if _exclude.active()
                     else _exclude.using([], add_settings=True))
        with fence:
            plan = (self.plan(opts, progress=progress)
                    if progress is not None and _wants_progress(self.plan)
                    else self.plan(opts))
            met_now = _exclude.what_was_met()
        plan.opts = opts
        met = {k: v for k, v in met_now.items() if v != met_before.get(k)}
        said = _exclude.said(met)
        if said and said not in plan.notes:
            plan.notes.insert(0, said)
        if not plan.task:
            plan.task = self.name
        if plan.errors:
            said = _denied_note([_denied_path(x) for x in plan.errors
                                 if "permission denied" in x.lower()])
            if said and said not in plan.notes:
                plan.notes.append(said)
        if not plan.blocked:
            shut = self._cannot_write_into(opts)
            if shut:
                plan.blocked = shut
        if not plan.blocked:
            # Planning is already a deliberate act - you typed a path and pressed
            # the button - so this is where a folder is worth remembering. Waiting
            # for an apply would mean a report-only task never remembered anything.
            # Setup's own value is handed over so that it is NOT remembered: a
            # run on the library because Setup said so is following Setup, and
            # a box that remembered it went on opening on the old library after
            # Setup named a new one.
            from core import recent as _recent
            from core import settings as _settings
            saved = _settings.load()
            setup = {o.name: str(saved[o.setting] or "") for o in self.options
                     if o.setting and o.kind in ("folder", "folders")}
            _recent.remember(self.name, {o.name: opts.get(o.name)
                                         for o in self.options
                                         if o.kind == "folder"}, setup)
            # A list of folders is remembered too - retyping which ones to leave
            # out, every single run, is the chore the list was meant to end.
            for o in self.options:
                if o.kind == "folders":
                    _recent.remember_text(self.name, o.name, opts.get(o.name),
                                          setup.get(o.name, ""))
        return plan


def _denied_path(line: str) -> str:
    """The folder out of "could not read /x/y: Permission denied".

    The message is assembled by the walker and read back here, which is not
    ideal and is better than the alternative: the walker collects errors as
    sentences, and giving every one of them a structured form would be a change
    to every task that reads them. The failure mode is harmless - no folder
    found means no explanation offered, never a wrong one.
    """
    text = str(line or "")
    if ":" not in text:
        return ""
    body = text.split(":")[0] if text.count(":") == 1 else \
        ":".join(text.split(":")[:-1])
    for lead in ("could not read ", "could not walk ", "could not open "):
        if body.startswith(lead):
            body = body[len(lead):]
    return body.strip()


_TASKS: dict[str, Task] = {}


# Tasks that walk no library of their own - settings, logs, imports - get no
# per-feature skip box: there is nothing in them for it to skip.
NO_SKIP = {"history", "backup", "checklist", "password", "autoruns", "flows",
           "automation", "permissions", "reindex", "import-places",
           "import-timeline", "delfolder"}


def _with_skip(task: Task) -> Task:
    """Every feature that walks folders gets its own "Skip these folders".

    Setup's list is skipped everywhere already; this is for "not this time":
    one shoot you are still working on, a folder a flow should leave. Added in
    one place so no feature can be the one that forgot.
    """
    if task.settings or task.name in NO_SKIP:
        return task
    if any(o.name == "skip_here" for o in task.options):
        return task
    if not any(o.kind in ("folder", "folders") for o in task.options):
        return task
    task.options.append(Folders(
        "skip_here", "Skip these folders", default="", group="Skip",
        advanced=True,
        help="Folders left out of this run only. The folders in Setup > Skip "
             "everywhere are always left out as well. Check the list says "
             "what was left out."))
    return task


def register(task: Task) -> Task:
    if task.name in _TASKS:
        raise ValueError(f"two tools are both called {task.name!r}")
    _with_skip(task)
    _TASKS[task.name] = task
    return task


def get(name: str) -> Task | None:
    return _TASKS.get(name)


def all_tasks() -> list[Task]:
    return sorted(_TASKS.values(), key=lambda t: (t.order, t.title))


def children(name: str) -> list[Task]:
    """The tasks drawn as tabs under this one."""
    return [t for t in all_tasks() if t.parent == name]


def top_level() -> list[Task]:
    """The tasks that are not a tab under another one.

    Not quite the same as "what is in the sidebar": a hidden one is reachable
    and has its own place in the header instead. Kept as "not a child" because
    that is what every caller actually means by it - covering every task, or
    checking nothing is a tab under a tab.
    """
    return [t for t in all_tasks() if not t.parent]


def in_sidebar() -> list[Task]:
    """The tasks that get a line in the sidebar."""
    return [t for t in top_level() if not t.hidden]


def describe_all() -> list[dict]:
    return [t.describe() for t in all_tasks()]
