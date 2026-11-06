"""The wording of every tool, and local edits to it.

Every word a tool shows - its title, its summary, each option's label and
help, each choice, each group heading - is written in the `Task(...)` and
`Option(...)` declarations in `app/tasks/`. That stays the source. This module
keeps a small file of *overrides* beside the settings, so somebody can rewrite
the text from inside the app, read it in place, and hand the file back to be
merged into the source.

Overrides rather than edited source, for three reasons. A new release never
loses the edits, because they are not in the code it replaces. The tests keep
testing the shipped text, because they read the registry and not this file.
And the file holds only what changed, so it is small enough to review.

There is one choke point: `Task.describe()` ends by passing its answer through
`apply()`. The page, the API and the command line's `--help` all read
`describe()`, so none of them needs to know overrides exist.

Keys name one piece of text each:

    <task>.title    <task>.tab    <task>.summary    <task>.line
    <task>.option.<name>.label    <task>.option.<name>.help
    <task>.option.<name>.choice.<value>
    <task>.group.<heading as shipped>
    page.<name>    guide.<slug>.title    guide.<slug>.body.<n>

The style rules the editor warns about live here too, as data, so the editor,
the tests and the style guide in the audit share one list.

Nothing here imports from `app`: the shipped text is read from the registry by
`app/tasks/wording.py`, which hands it in.
"""

from __future__ import annotations

import json
import os
import re
import time

from .store import store_path

FILE = "wording.json"
VERSION = 1

# Four words is a label; five is a sentence with the verb left out. The same
# number `tests/test_wording.py` holds the shipped labels to.
LABEL_WORDS = 4

FIELDS = ("title", "tab", "summary", "line")
OPTION_FIELDS = ("label", "help")

# Words in capitals that are names, not shouting.
ACRONYMS = {"RAW", "RAWS", "JPEG", "JPEGS", "XMP", "EXIF", "GPS", "HEIC", "NAS",
            "DSM", "URL", "CSV", "KML", "GPX", "UTC", "PC", "ISO", "ID", "OK",
            "TIFF", "PNG", "DNG", "SMB", "ACL", "ACLS", "HTTP", "HTTPS", "API",
            "CLI", "UI", "MP4", "MOV", "IP", "LAN", "USB", "AM", "PM", "GB",
            "MB", "KB", "TB", "EV", "AF", "SD", "UID", "GID", "TSV", "ZIP",
            "IPTC", "DLNA", "VPN", "QGIS", "LUMIX", "README"}

# The glossary's "do not use" column (audit section 10.3), all of it. Matched
# as whole words, lower case. "marks" is the noun the page used for its
# columns; "mark" alone stays, because it is also the verb.
BANNED = ("photograph", "photographs", "picture", "pictures", "image",
          "images", "negative", "negatives", "small copy", "small copies",
          "tablet copy", "tablet copies", "side file", "side files", "clip",
          "clips", "movie", "movies", "directory", "directories",
          "the photo folders", "marks", "tag colour", "settings tab", "ipad",
          "feature", "features", "task", "tasks", "put aside", "set aside",
          "go ahead", "plan", "plans", "keyword", "keywords")

# Where a banned word is part of a name or of ordinary arithmetic, not the
# thing the glossary renamed: DSM's Task Scheduler and its Scheduled Task are
# what DSM calls them, and "a negative number" is not a RAW file.
NOT_BANNED = ("task scheduler", "scheduled task", "negative number")

SENTENCE_WORDS = 25

# What a Number's help can name as its unit when the label has none in
# brackets: "The lowest ISO to include", "How many levels to list". Matched as
# whole words in the first sentence, lower case.
UNIT_WORDS = ("stars", "rating", "iso", "f-number", "level", "levels", "rows",
              "folders", "runs", "passes", "number", "quality", "port",
              "thumbnails", "percentage", "score", "time", "minutes", "hours",
              "days", "seconds", "mm", "px", "pixels", "people", "km", "metres",
              "mb", "gb", "frames", "photos")

_SEEN: dict = {}


# ------------------------------------------------------------------ keys

def parse(key: str) -> dict | None:
    """What a key names, or None when it is not a key this file can hold.

    {"task", "kind", "option", "value"}: kind is one of title, tab, summary,
    line, label, help, choice, group; option is set for the option kinds;
    value is the choice value or the shipped group heading.
    """
    text = str(key or "")
    task, dot, rest = text.partition(".")
    if not task or not dot or not rest:
        return None
    # The page's own strings and the Guide (app/pagetext.py). No tool is
    # called "page" or "guide", and tests/test_wording_overrides keeps it so.
    if task == "page":
        return {"task": task, "kind": "string", "option": "", "value": rest}
    if task == "guide":
        name, dot, what = rest.partition(".")
        if name and what == "title":
            return {"task": task, "kind": "title", "option": "", "value": name}
        if name and what.startswith("body.") and what[5:].isdigit():
            return {"task": task, "kind": "body", "option": "",
                    "value": name}
        return None
    if rest in FIELDS:
        return {"task": task, "kind": rest, "option": "", "value": ""}
    if rest.startswith("group."):
        name = rest[len("group."):]
        return {"task": task, "kind": "group", "option": "", "value": name} \
            if name else None
    if rest.startswith("option."):
        body = rest[len("option."):]
        name, dot, what = body.partition(".")
        if not name or not dot:
            return None
        if what in OPTION_FIELDS:
            return {"task": task, "kind": what, "option": name, "value": ""}
        # a choice's value may be "" ("Any"), so "choice." alone is a key
        if what.startswith("choice."):
            return {"task": task, "kind": "choice", "option": name,
                    "value": what[len("choice."):]}
    return None


def kind_of(key: str) -> str:
    got = parse(key)
    return got["kind"] if got else ""


# ------------------------------------------------------------- the file

def path() -> str:
    return store_path(FILE)


def _stamp(where: str):
    try:
        st = os.stat(where)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def read(where: str = "") -> dict:
    """The whole file: {"version", "edited", "overrides"}. Never raises.

    A missing or damaged file is no edits at all, never an error: the shipped
    text is always there to fall back on.
    """
    where = where or path()
    stamp = _stamp(where)
    hit = _SEEN.get(where)
    if hit is not None and hit[0] == stamp:
        return {"version": VERSION, "edited": hit[1],
                "overrides": dict(hit[2])}
    edited, overrides = "", {}
    if stamp is not None:
        try:
            with open(where, encoding="utf-8") as fh:
                got = json.load(fh)
            if isinstance(got, dict):
                edited = str(got.get("edited") or "")
                raw = got.get("overrides")
                if isinstance(raw, dict):
                    overrides = {str(k): str(v) for k, v in raw.items()
                                 if isinstance(v, str)}
        except (OSError, ValueError):
            edited, overrides = "", {}
    _SEEN[where] = (stamp, edited, overrides)
    return {"version": VERSION, "edited": edited, "overrides": dict(overrides)}


def load(where: str = "") -> dict:
    """The overrides alone, key -> text."""
    return read(where)["overrides"]


def write(overrides: dict, where: str = "") -> dict:
    """Keep exactly these overrides. Written to a temporary file and moved into
    place, like the settings, so a crash cannot leave half a file."""
    where = where or path()
    clean = {str(k): str(v) for k, v in (overrides or {}).items()}
    body = {"version": VERSION,
            "edited": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "overrides": dict(sorted(clean.items()))}
    tmp = where + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(body, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, where)
    _SEEN.pop(where, None)
    return body


def forget() -> None:
    """Drop what has been read. For tests."""
    _SEEN.clear()


# ---------------------------------------------------------- the rules

def refusal(key: str, text: str) -> str:
    """Why this text cannot be saved under this key, or "".

    Only the rules the tests also hold the shipped text to are refusals: a
    label or a group heading of five words, and an empty name. Everything else
    in the style guide is a warning (`problems`), because a rule of thumb that
    blocks a save is a rule people stop using the editor over.
    """
    kind = kind_of(key)
    if not kind:
        return f"{key!r} is not a piece of text the app knows how to name."
    said = " ".join(str(text or "").split())
    if kind in ("title", "label", "choice", "group", "tab") and not said:
        return "A name cannot be empty. Reset it to go back to the shipped text."
    if kind in ("label", "group") and len(said.split()) > LABEL_WORDS:
        return (f"A label is at most {LABEL_WORDS} words, the unit in brackets "
                f"included. This one has {len(said.split())}: put the rest in "
                f"the help.")
    return ""


def sentences(text: str) -> list[str]:
    said = " ".join(str(text or "").split())
    return [s for s in re.split(r"(?<=[.!?])\s+", said) if s]


def problems(key: str, text: str) -> list[str]:
    """What the style guide would say about this text. Warnings, not refusals."""
    kind = kind_of(key) or "help"
    said = " ".join(str(text or "").split())
    out = []
    if not said:
        return ["no text" if kind == "help" else "empty"]
    if re.search(r"[A-Za-z,)] [-–] [A-Za-z(]", said):
        out.append("a dash used as a full stop")
    shouting = sorted({w for w in re.findall(r"\b[A-Z][A-Z]{2,}\b", said)
                       if w not in ACRONYMS})
    if shouting:
        out.append("capitals for emphasis: " + ", ".join(shouting))
    lower = said.lower()
    for phrase in NOT_BANNED:
        lower = lower.replace(phrase, " ")
    banned = [w for w in BANNED if re.search(r"\b" + re.escape(w) + r"\b", lower)]
    if banned:
        out.append("glossary: " + ", ".join(banned))
    if kind in ("help", "summary", "body", "string"):
        long = [s for s in sentences(said) if len(s.split()) > SENTENCE_WORDS]
        if long:
            out.append(f"{len(long)} long sentence{'' if len(long) == 1 else 's'}"
                       f" (over {SENTENCE_WORDS} words)")
        if ";" in said:
            out.append("a semicolon")
    if kind in ("label", "group") and len(said.split()) > LABEL_WORDS:
        out.append(f"over {LABEL_WORDS} words")
    if kind in ("label", "group", "title", "tab", "choice") and said.endswith("."):
        out.append("a name ends without a full stop")
    return out


# ---------------------------------------------------------- applying

def names_a_unit(label: str, text: str) -> bool:
    """A number box says what it counts: a unit in brackets on the label
    ("Clock fast by (minutes)"), or a unit word in the help's first sentence."""
    if re.search(r"\([^)]+\)\s*$", str(label or "")):
        return True
    first = (sentences(text) or [""])[0].lower()
    return any(re.search(r"\b" + re.escape(w) + r"\b", first) for w in UNIT_WORDS)


def _first_sentence(text: str) -> str:
    got = sentences(text)
    return got[0] if got else ""


def apply(task: dict, overrides: dict | None = None,
          line_from_summary: bool = False, tab_from_title: bool = False) -> dict:
    """One task's `describe()` answer, with the overrides swapped in.

    Changes only the keys present; anything else is returned as it came. A key
    naming an option or a choice that no longer exists is ignored here and
    listed by `unknown()`, so an edit made against an older release never
    breaks a form.

    `line_from_summary` and `tab_from_title` say the task never set its own
    one-line description or tab name, so they follow an edited summary or
    title the way they follow the shipped one.
    """
    if overrides is None:
        overrides = load()
    if not overrides or not isinstance(task, dict):
        return task
    name = str(task.get("name") or "")
    mine = {k[len(name) + 1:]: v for k, v in overrides.items()
            if k.startswith(name + ".")}
    if not mine:
        return task
    for field in FIELDS:
        if field in mine and field in task:
            task[field] = mine[field]
    if line_from_summary and "summary" in mine and "line" not in mine:
        task["line"] = _first_sentence(mine["summary"])
    if tab_from_title and "title" in mine and "tab" not in mine:
        task["tab"] = mine["title"]

    renamed = {k[len("group."):]: v for k, v in mine.items()
               if k.startswith("group.")}

    def one(o: dict) -> dict:
        lead = f"option.{o.get('name')}."
        if lead + "label" in mine:
            o["label"] = mine[lead + "label"]
        if lead + "help" in mine:
            o["help"] = mine[lead + "help"]
        if o.get("group") in renamed:
            o["group"] = renamed[o["group"]]
        for c in o.get("choices") or []:
            k = lead + "choice." + str(c.get("value"))
            if k in mine:
                c["label"] = mine[k]
        return o

    for o in task.get("options") or []:
        one(o)
    for g in task.get("groups") or []:
        if g.get("name") in renamed:
            g["name"] = renamed[g["name"]]
        for o in g.get("options") or []:
            one(o)
    return task


def unknown(overrides: dict, shipped: dict) -> list[str]:
    """Keys in the file that name nothing the app ships today."""
    return sorted(k for k in overrides if k not in shipped or not parse(k))


def without_shipped(overrides: dict, shipped: dict) -> dict:
    """An override equal to the shipped text is not an edit, and is dropped,
    so the file only ever lists what is actually different."""
    out = {}
    for k, v in (overrides or {}).items():
        if k in shipped and " ".join(str(v).split()) == " ".join(
                str(shipped[k]).split()):
            continue
        out[k] = str(v)
    return out


# ------------------------------------------------------ developer switch

def developer_on() -> bool:
    """Is the Wording tab shown? Setup's switch, or PM_DEVELOPER=1 for a
    container where nobody wants to open Setup to turn it on."""
    if str(os.environ.get("PM_DEVELOPER", "")).strip().lower() in (
            "1", "true", "yes", "on"):
        return True
    try:
        from . import settings as _s
        return bool(_s.load()["developer"])
    except Exception:                                  # noqa: BLE001
        return False
