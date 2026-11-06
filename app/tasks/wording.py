"""Setup > Wording: edit the text of every tool in place, and hand it back.

Shown only with Setup's developer switch on (or PM_DEVELOPER=1). The tab is an
editor drawn by the page (`library/js/21-wording.js`); this module is the
server's half of it: the shipped text of every tool, read from the registry,
what has been edited (`core/wording.py`), and the export that carries both
plus the source line each edit belongs on.

The plan is the same list for the command line: `python -m app.cli wording`
says what has been edited, against what shipped. It writes nothing; edits are
saved one at a time by the editor through `/api/wording`.
"""

from __future__ import annotations

from app import registry as R
from app.registry import Plan, Result, Row, Task, register
from core import wording as W


# ----------------------------------------------------------- shipped text

def fields(task: R.Task) -> list[dict]:
    """Every piece of text this tool shows, in the order its form shows it.

    Read from the declarations, never from `describe()`, which already has
    the edits in it. Choices built at run time (History's list of tools) are
    left out: their labels are other tools' titles, edited there.
    """
    out = [{"key": f"{task.name}.title", "shipped": task.title}]
    if task.parent:
        out.append({"key": f"{task.name}.tab", "shipped": task.tab or task.title})
    out.append({"key": f"{task.name}.summary", "shipped": task.summary})
    out.append({"key": f"{task.name}.line", "shipped": task.one_line()})
    groups = []
    for o in task.options:
        lead = f"{task.name}.option.{o.name}"
        out.append({"key": f"{lead}.label", "shipped": o.label, "option": o.name})
        out.append({"key": f"{lead}.help", "shipped": o.help or "",
                    "option": o.name})
        if isinstance(o, R.Choice) and not callable(o.choices):
            for c in o.offered():
                if isinstance(c, (tuple, list)):
                    out.append({"key": f"{lead}.choice.{c[0]}",
                                "shipped": str(c[1]), "option": o.name})
        if o.group and o.group not in groups:
            groups.append(o.group)
    for g in groups:
        out.append({"key": f"{task.name}.group.{g}", "shipped": g})
    for f in out:
        f["kind"] = W.kind_of(f["key"])
    return out


# The page's own strings and the Guide, edited on the same tab as two more
# entries in the tool list (app/pagetext.py).
EXTRA = (("page", "Page text"), ("guide", "Guide"))


def shipped() -> dict:
    """key -> shipped text, for every tool, the page and the Guide."""
    from app import pagetext
    out = {f["key"]: f["shipped"] for t in R.all_tasks() for f in fields(t)}
    out.update(pagetext.shipped())
    return out


def counts(overrides: dict | None = None) -> dict:
    """The three numbers at the top of the tab, over the text as it reads now
    (shipped, with the edits on top)."""
    overrides = W.load() if overrides is None else overrides
    table = shipped()
    no_help = long = 0
    for key, text in table.items():
        now = overrides.get(key, text)
        kind = W.kind_of(key)
        if kind == "help" and not now.strip():
            no_help += 1
        if kind == "label" and len(now.split()) > W.LABEL_WORDS:
            long += 1
    return {"edited": len([k for k in overrides if k in table]),
            "no_help": no_help, "long_labels": long,
            "unknown": len(W.unknown(overrides, table))}


def task_fields(name: str, overrides: dict | None = None,
                source: bool = True) -> list[dict]:
    """One tool's fields, each with what it says now and what is wrong with it.

    `source` adds the file and line each one is written on, which means
    reading that tool's module; a search across every tool leaves it out."""
    from app import pagetext, wordsource
    if name in dict(EXTRA):
        found = pagetext.fields(name)
    else:
        task = R.get(name)
        if task is None:
            return []
        found = fields(task)
    overrides = W.load() if overrides is None else overrides
    out = []
    for f in found:
        now = overrides.get(f["key"], f["shipped"])
        f.update(text=now, edited=f["key"] in overrides,
                 problems=W.problems(f["key"], now),
                 where=_where(f["key"], f["shipped"]) if source else "")
        out.append(f)
    return out


def _where(key: str, shipped_text: str) -> str:
    from app import pagetext, wordsource
    return pagetext.where(key) or wordsource.where(key, shipped_text)


def export() -> dict:
    """The file to hand back: the edits, and for each the shipped text and the
    source line it replaces, so merging it is mechanical and can be checked.
    `tools/merge_wording.py` reads exactly this."""
    body = W.read()
    table = shipped()
    entries = []
    for key, text in sorted(body["overrides"].items()):
        entries.append({"key": key, "text": text,
                        "shipped": table.get(key),
                        "where": _where(key, table.get(key) or "")})
    return {"version": W.VERSION, "edited": body["edited"],
            "overrides": body["overrides"], "entries": entries,
            "unknown": W.unknown(body["overrides"], table)}


# ------------------------------------------------------------ the API

def answer(query: dict) -> tuple[dict, int]:
    """GET /api/wording. `task=` adds that tool's fields (`task=*` every
    tool's, for a search); `export=1` is the export instead."""
    if not W.developer_on():
        return {"error": "Turn on Setup > Developer mode first."}, 403
    if query.get("export"):
        return export(), 200
    overrides = W.load()
    out = {"on": True, "edited": W.read()["edited"], "overrides": overrides,
           "counts": counts(overrides),
           "unknown": W.unknown(overrides, shipped()),
           "tasks": [{"name": t.name, "title": t.title, "parent": t.parent,
                      "edits": len([k for k in overrides
                                    if k.startswith(t.name + ".")])}
                     for t in R.all_tasks()]
           + [{"name": name, "title": title, "parent": "", "page": True,
               "edits": len([k for k in overrides if k.startswith(name + ".")])}
              for name, title in EXTRA]}
    name = str(query.get("task") or "")
    if name == "*":
        out["fields"] = [f for t in [x.name for x in R.all_tasks()]
                         + [n for n, _t in EXTRA]
                         for f in task_fields(t, overrides, source=False)]
    elif name:
        out["fields"] = task_fields(name, overrides)
    return out, 200


def change(body: dict) -> tuple[dict, int]:
    """POST /api/wording.

        {"key", "text"}              save one edit (equal to shipped = reset)
        {"key", "reset": true}       back to the shipped text
        {"reset_all": true}          every edit gone
        {"file": {...}, "replace"}   an uploaded wording.json, merged or not

    A POST rather than a DELETE for the resets, so every change goes through
    the one guarded route the other writes use.
    """
    if not W.developer_on():
        return {"error": "Turn on Setup > Developer mode first."}, 403
    table = shipped()
    overrides = W.load()
    if body.get("reset_all"):
        W.write({})
        return {"overrides": {}, "counts": counts({})}, 200
    if isinstance(body.get("file"), dict):
        got = body["file"].get("overrides")
        if not isinstance(got, dict):
            return {"error": "That file has no overrides in it."}, 400
        merged = {} if body.get("replace") else dict(overrides)
        refused = []
        for key, text in got.items():
            why = W.refusal(key, text)
            if not why and key not in table:
                why = "the app does not ship this text any more"
            if why:
                refused.append({"key": key, "why": why})
                continue
            merged[key] = str(text)
        merged = W.without_shipped(merged, table)
        W.write(merged)
        return {"overrides": merged, "refused": refused,
                "counts": counts(merged)}, 200
    key = str(body.get("key") or "")
    if key not in table:
        return {"error": f"{key!r} is not a piece of text the app shows."}, 400
    if body.get("reset"):
        overrides.pop(key, None)
    else:
        text = " ".join(str(body.get("text") or "").split()) \
            if W.kind_of(key) not in ("help", "body", "string") \
            else str(body.get("text") or "").strip()
        why = W.refusal(key, text)
        if why:
            return {"error": why}, 400
        overrides[key] = text
    overrides = W.without_shipped(overrides, table)
    W.write(overrides)
    return {"key": key, "text": overrides.get(key, table[key]),
            "edited": key in overrides,
            "problems": W.problems(key, overrides.get(key, table[key])),
            "counts": counts(overrides)}, 200


# ----------------------------------------------------------- the tool

def plan(opts) -> Plan:
    p = Plan(task="wording", opts=dict(opts))
    overrides = W.load()
    table = shipped()
    c = counts(overrides)
    p.stats = [("Edited", str(c["edited"])), ("With no help", str(c["no_help"])),
               ("Labels over four words", str(c["long_labels"]))]
    p.columns = ["Text", "Now", "Shipped"]
    for key, text in sorted(overrides.items()):
        p.rows.append(Row(what="edit", name=key, detail=text,
                          cells=[text, table.get(key, "(not shipped any more)")]))
    if not overrides:
        p.notes.append("Nothing is edited. Turn on Setup > Developer mode and "
                       "use the Wording tab to change the text of any tool.")
    for key in W.unknown(overrides, table):
        p.skipped.append((key, "the app does not ship this text any more"))
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    return Result(details=["This tool only reports. Edits are saved one at a "
                           "time on the Wording tab."])


register(Task(
    name="wording",
    line="Edit the text of every tool, and export it.",
    title="Wording",
    summary="Edits the title, labels, help and choices of every tool, and "
            "exports the edits to merge into the source.",
    icon="type",
    parent="setup",
    editor="wording",
    order=99,
    writes=False,
    reads=(),
    options=[],
    plan=plan,
    apply=apply,
))
