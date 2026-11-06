"""The dashboard as YOU arrange it, and the arrangements you keep.

The Library opened on a fixed set of tiles, meters and charts, chosen once by
whoever wrote the page. Some of them answer a question you have every day and
some of them answer one you have never had - and which is which depends on the
library, not on the app. "With a date" is the clearest case: it read 100% for
everybody, every time, and took up a row saying so.

So: a board is an ORDERED LIST OF WIDGET NAMES, and that is the whole model.
What is in the list is drawn, in that order. What is not in the list is not
drawn. There is no separate "hidden" list to get out of step with it, and
reordering, removing and adding are all the same edit.

**Several boards, one of them current.** The same library answers different
questions on different days - "what is left to do" is not "what did I shoot" -
and the arrangement for each is worth keeping rather than rebuilding. Setup
names, copies and deletes them; the dashboard switches between them.

**An unknown name is dropped, not an error.** A board saved by a later version
of the app, or one that mentions a chart that has since gone, still opens - it
just draws the widgets that exist. Refusing to show a dashboard because one
line of it is stale would be the worst possible trade.
"""

from __future__ import annotations

import json
import re

from . import settings as S

SAVED = "dashboards"

# name -> (what it is called, what kind of thing it is, a line about it)
#
# `tile` is one big number, `meter` is a share of a whole, and the rest are
# charts drawn from one dimension of core/stats.py. The chart names are the
# dimension names, which is what keeps this table honest: a chart exists here
# only if something can actually count it.
WIDGETS = {
    "tile:photos": ("Photos", "tile", "How many the library holds."),
    "tile:weight": ("Everything, all trees", "tile",
                    "The library, the RAWs, the previews and the video added up."),
    "tile:rated": ("Rated", "tile", "The share carrying stars."),
    "tile:placed": ("Placed", "tile", "The share carrying a location."),
    "tile:cameras": ("Cameras", "tile", "How many wrote their name into a file."),
    "tile:years": ("Years", "tile", "How many the library spans."),
    "meter:rated": ("Rated", "meter", "How far along the rating is."),
    "meter:located": ("With a location", "meter", "How far along geotagging is."),
    "meter:previews": ("Previews made", "meter", "How far along previews are."),
    "meter:raws": ("RAWs separated", "meter",
                   "How many RAW files are out of the library."),
    "chart:space": ("Where the space is", "donut",
                    "Every tree this library reaches into."),
    "chart:camera": ("Which camera", "donut", "By how many photos came off each."),
    "chart:lens": ("Which lens", "donut", "By how many photos came off each."),
    "chart:year": ("Photos by year", "bars", ""),
    "chart:month": ("Photos by month", "bars", "Across every year at once."),
    "chart:weekday": ("Photos by day of the week", "bars", ""),
    "chart:hour": ("Time of day", "bars", ""),
    "chart:aperture": ("Aperture", "bars",
                       "A frame that does not record one is counted as not "
                       "said, never as f/0."),
    "chart:focal": ("Focal length", "bars",
                    "As written on the lens - a GH4 frames tighter than the number."),
    "chart:iso": ("ISO", "bars", ""),
    "chart:shutter": ("Shutter", "bars", ""),
    "chart:stars": ("Stars", "bars", ""),
    "chart:colour": ("Colour label", "donut", ""),
    "chart:tag": ("Tags", "bars",
                  "A photo with two tags is counted under both, so these "
                  "add up to more than the library."),
    "chart:kind": ("Kind of file", "donut", ""),
    "chart:located": ("Location", "donut", "Photos carrying a position."),
    "chart:folder": ("Top folder", "bars", ""),
}

# What the Library opens on before anyone has arranged anything. Deliberately
# not everything: a first screen that needs scrolling twice is a first screen
# nobody reads.
BUILTIN = [
    "tile:photos", "tile:weight", "tile:rated", "tile:placed",
    "tile:cameras", "tile:years",
    "meter:rated", "meter:located", "meter:previews", "meter:raws",
    "chart:space", "chart:camera", "chart:year", "chart:aperture",
    "chart:focal", "chart:iso", "chart:stars", "chart:located", "chart:kind",
]

FIRST = "Everything"        # the name the built-in arrangement is kept under


def _clean(names) -> list:
    """A list of widget names, in order, with the ones this app knows kept."""
    out, seen = [], set()
    for name in names or []:
        name = str(name).strip()
        if name in WIDGETS and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _all() -> dict:
    try:
        got = json.loads(S.load()[SAVED] or "{}")
    except (ValueError, TypeError, AttributeError):
        got = {}
    boards = {}
    for name, names in (got.get("boards") or {}).items():
        name = re.sub(r"\s+", " ", str(name)).strip()[:40]
        if name:
            boards[name] = _clean(names)
    if FIRST not in boards:
        boards[FIRST] = list(BUILTIN)
    now = str(got.get("now") or "").strip()
    if now not in boards:
        now = FIRST
    return {"now": now, "boards": boards}


def _put(state: dict) -> dict:
    S.save({SAVED: json.dumps({"now": state["now"], "boards": state["boards"]})})
    return state


def names() -> list:
    """Every arrangement there is, the built-in one first."""
    state = _all()
    rest = sorted(n for n in state["boards"] if n != FIRST)
    return [FIRST] + rest


def now() -> str:
    return _all()["now"]


def board(name: str = "") -> list:
    """The widgets of one arrangement, in the order they are drawn."""
    state = _all()
    name = name or state["now"]
    # `or BUILTIN` would be wrong here: an arrangement with nothing on it is a
    # thing somebody may mean, and an empty list is falsy.
    return list(state["boards"][name]) if name in state["boards"] else list(BUILTIN)


def show(name: str) -> str:
    """Make one of them the current arrangement."""
    state = _all()
    if name not in state["boards"]:
        raise ValueError("there is no arrangement by that name")
    state["now"] = name
    _put(state)
    return name


def keep(names_in_order, name: str = "") -> list:
    """Save an arrangement. The list IS what is drawn, in that order."""
    state = _all()
    name = (name or state["now"]).strip()
    if name not in state["boards"]:
        raise ValueError("there is no arrangement by that name")
    state["boards"][name] = _clean(names_in_order)
    _put(state)
    return state["boards"][name]


def add(name: str, like: str = "") -> str:
    """A new arrangement, copied from another one or from the built-in list."""
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not name:
        raise ValueError("give it a name")
    if len(name) > 40:
        raise ValueError("that name is too long")
    state = _all()
    if name in state["boards"]:
        raise ValueError("there is already one called that")
    state["boards"][name] = (list(state["boards"][like])
                             if like in state["boards"] else list(BUILTIN))
    state["now"] = name
    _put(state)
    return name


def rename(was: str, to: str) -> str:
    to = re.sub(r"\s+", " ", str(to or "")).strip()
    if not to:
        raise ValueError("give it a name")
    if len(to) > 40:
        raise ValueError("that name is too long")
    state = _all()
    if was == FIRST:
        raise ValueError(f"'{FIRST}' is the one this app comes with, so it "
                         f"keeps its name - copy it to make one of your own")
    if was not in state["boards"]:
        raise ValueError("there is no arrangement by that name")
    if to in state["boards"]:
        raise ValueError("there is already one called that")
    state["boards"][to] = state["boards"].pop(was)
    if state["now"] == was:
        state["now"] = to
    _put(state)
    return to


def drop(name: str) -> str:
    state = _all()
    if name == FIRST:
        raise ValueError(f"'{FIRST}' is the one this app comes with and cannot "
                         f"be deleted - reset it instead")
    if name not in state["boards"]:
        raise ValueError("there is no arrangement by that name")
    state["boards"].pop(name)
    if state["now"] == name:
        state["now"] = FIRST
    _put(state)
    return state["now"]


def reset(name: str = "") -> list:
    """Put the built-in arrangement back into one of them."""
    state = _all()
    name = name or state["now"]
    if name not in state["boards"]:
        raise ValueError("there is no arrangement by that name")
    state["boards"][name] = list(BUILTIN)
    _put(state)
    return state["boards"][name]


def catalogue(picked=None) -> list:
    """Every widget there is, said plainly, and whether this board draws it.

    In the order the board draws them first, so the editor can list what is on
    without re-sorting, then everything else by kind.
    """
    picked = list(picked if picked is not None else board())
    rest = [n for n in WIDGETS if n not in picked]
    out = []
    for name in picked + rest:
        title, kind, about = WIDGETS[name]
        out.append({"name": name, "title": title, "kind": kind,
                    "about": about, "on": name in picked})
    return out


def dims(picked=None) -> list:
    """Which dimensions have to be counted for this board - and no others.

    A board with three charts on it should not pay for nine. `space` is not a
    dimension of the photographs, so it is not in here.
    """
    picked = list(picked if picked is not None else board())
    out = []
    for name in picked:
        if name.startswith("chart:") and name != "chart:space":
            dim = name.split(":", 1)[1]
            if dim not in out:
                out.append(dim)
    # the two tiles that count things need their dimension whatever else is on
    for need, dim in (("tile:cameras", "camera"), ("tile:years", "year")):
        if need in picked and dim not in out:
            out.append(dim)
    return out
