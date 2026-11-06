"""Forty-six features under five headings, and Settings on its own.

Version 2.2 put five families over the thirteen top-level features, which was
the right idea at the wrong level: the features somebody is looking for are
mostly TABS - Cull by rating, Fix the clock, Find duplicates - and those were
still hidden one click inside something else.

So the table now covers every feature there is, at whatever level it sits, and
the Tools screen draws it as five cards:

    Organize    get the files where they belong
    Metadata    times, places, stars and tags
    Review      look at what is there, and weed it
    Develop     out to the tablet, and back again
    Maintain    space, runs and the state of the machine

**Settings is not one of them.** It is where you say where things are and what
they mean, and a list of tools with "Password" in it reads as a job you have not
done yet. It has its own place.

The rules this file keeps are the same two as before, and both have tests:
nothing is in two families, and a feature in none of them is still reachable -
`catalogue()` ends with a catch-all that is visible rather than silent, so
forgetting to file a new feature costs an odd heading and never a feature that
cannot be found.
"""

from __future__ import annotations

# key, heading, the line under it, the glyph, the tone it is drawn in, and the
# features in it - in the order somebody would work through them.
FAMILIES: list[dict] = [
    {"key": "organize", "label": "Organize", "icon": "folder", "tone": "blue",
     "note": "Get the files where they belong",
     "tasks": ["bydate", "import-places", "unpair", "remirror", "videos",
               "remirror_video", "files", "rename"]},
    {"key": "metadata", "label": "Metadata", "icon": "globe", "tone": "teal",
     "note": "Times, places, stars and tags",
     "tasks": ["geotag", "timeline", "retime", "import-timeline", "pin",
               "unlocate", "ratings", "label", "tags"]},
    {"key": "review", "label": "Review", "icon": "find", "tone": "orange",
     "note": "Look at what is there, and weed it",
     "tasks": ["library", "search", "compare", "brackets", "exposure",
               "thin", "cull", "blur", "duplicates"]},
    {"key": "develop", "label": "Develop", "icon": "send", "tone": "purple",
     "note": "Out to the tablet, and back again",
     "tasks": ["previews", "remirror_previews", "develop", "filed"]},
    {"key": "maintain", "label": "Maintain", "icon": "layers", "tone": "grey",
     "note": "Space, piles and what was done",
     "tasks": ["space", "tidy", "cleanup", "delfolder", "history"]},
]

# Automation is not one of the five, and that is the point: a flow is not a job
# you do, it is the other five doing themselves on a timer. Filed under Maintain
# it read as housekeeping, which is how somebody ends up never finding it.
ALONE = {"key": "flows", "label": "Automation", "icon": "auto", "tone": "blue",
         "note": "The other tools, running themselves",
         "tasks": ["automation", "flows", "autoruns"]}

# Where you say where things are and what they mean. Deliberately not a card on
# the Tools screen: these are not jobs.
#
# Reindex and the permissions check are in here rather than under Maintain for
# the same reason: neither is something you set out to do. One tells DSM the
# files moved and the other fixes what the NAS lets the app touch - both are
# consequences of how this machine is set up.
SETTINGS = {"key": "settings", "label": "Settings", "icon": "gear",
            "tone": "grey", "note": "Where things are, and what they mean",
            "tasks": ["setup", "checklist", "permissions", "reindex", "labels",
                      "cameras", "bands", "password", "backup", "demo",
                      "wording"]}

# Tools that only mean something on a Synology NAS: Reindex asks DSM to look
# at the library again, and Permissions checks the share's owners and ACLs. On
# a PC there is no DSM to ask and nothing of the kind to check, so a desktop
# copy leaves them off the page. They stay registered, and the command line
# still runs them - a script written for the NAS should not break on a PC.
NAS_ONLY = ("reindex", "permissions")

# Tools for whoever is working on the app itself, shown only with Setup's
# developer switch on (core/wording.developer_on). Registered either way, so
# the command line still runs them.
DEVELOPER_ONLY = ("wording",)


def offered(names, desktop: bool, developer: bool = False) -> list:
    """The names the page should show: all of them, less the NAS-only tools
    on a copy started as a desktop program, and less the developer tools
    unless the developer switch is on."""
    return [n for n in names if not (desktop and n in NAS_ONLY)
            and (developer or n not in DEVELOPER_ONLY)]


# Anything this file has not been told about. Visible, last, and the test says
# it should be empty - but a feature in it is still a feature you can reach.
OTHER = {"key": "other", "label": "Anything else", "icon": "dot", "tone": "grey",
         "note": "Not filed under one of the above", "tasks": []}

ALL = FAMILIES + [ALONE, SETTINGS]


# ------------------------------------------------------- grouped your own way

def _defaults() -> list:
    """The built-in grouping, as plain data an arrangement starts from."""
    return [{"key": f["key"], "label": f["label"], "icon": f["icon"],
             "tone": f["tone"], "note": f["note"], "tasks": list(f["tasks"])}
            for f in FAMILIES + [ALONE]]


def arranged() -> dict:
    """{"groups": [...], "hidden": [...]} - yours if you made one, else the
    built-in five.

    The grouping this app ships with is a good default and a bad rule. Somebody
    who never shoots RAW does not want four features about separating negatives
    in front of them every day; somebody whose week is geotagging wants those
    four together under a heading they chose. So the arrangement is data, kept
    on the NAS with everything else, and the built-in one is what you get until
    you say otherwise.

    Nothing here can lose a feature. Whatever is not in a group ends up in the
    catch-all, visible, and `hidden` only ever affects the LISTS - a hidden
    feature still exists, still runs, and the Tools screen says how many there
    are and will show them.
    """
    import json
    from . import settings as S
    try:
        got = json.loads(str(S.load()["tool_groups"] or "") or "{}")
    except (ValueError, TypeError):
        got = {}
    if not isinstance(got, dict):
        got = {}
    groups = []
    for one in (got.get("groups") or []):
        if not isinstance(one, dict):
            continue
        key = str(one.get("key") or "").strip()[:40]
        label = str(one.get("label") or "").strip()[:40]
        if not key or not label:
            continue
        groups.append({
            "key": key, "label": label,
            "icon": str(one.get("icon") or "tools").strip()[:24],
            "tone": str(one.get("tone") or "grey").strip()[:12],
            "note": str(one.get("note") or "").strip()[:120],
            "tasks": [str(t) for t in (one.get("tasks") or []) if str(t)],
        })
    hidden = [str(h) for h in (got.get("hidden") or []) if str(h)]
    if not groups:
        return {"groups": _defaults(), "hidden": hidden, "mine": False}
    # A feature may be in one group only, whatever the file says: two cards
    # offering the same thing is a list you cannot trust the shape of.
    seen = set()
    for g in groups:
        keep = []
        for name in g["tasks"]:
            if name in seen:
                continue
            seen.add(name)
            keep.append(name)
        g["tasks"] = keep
    return {"groups": groups, "hidden": hidden, "mine": True}


def save_arranged(groups, hidden=()) -> dict:
    """Keep an arrangement. Returns what was actually kept."""
    import json
    from . import settings as S
    clean = []
    for one in (groups or []):
        if not isinstance(one, dict):
            continue
        label = str(one.get("label") or "").strip()[:40]
        if not label:
            continue
        key = str(one.get("key") or "").strip()[:40] or _slug(label)
        clean.append({"key": key, "label": label,
                      "icon": str(one.get("icon") or "tools").strip()[:24],
                      "tone": str(one.get("tone") or "grey").strip()[:12],
                      "note": str(one.get("note") or "").strip()[:120],
                      "tasks": [str(t) for t in (one.get("tasks") or []) if str(t)]})
    away = [str(h) for h in (hidden or []) if str(h)]
    body = {"groups": clean, "hidden": away}
    # Putting a feature away without regrouping anything is a real arrangement:
    # saving nothing in that case was how "I never use the sample library" came
    # back the next time the page was opened.
    S.save({"tool_groups": json.dumps(body) if (clean or away) else ""})
    return arranged()


def _slug(text: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in str(text))
    return "-".join(bit for bit in out.split("-") if bit)[:40] or "group"


def forget_arrangement() -> None:
    """Back to the five this app ships with."""
    from . import settings as S
    S.save({"tool_groups": ""})


def pinned() -> list:
    """Features pinned to the top level, in the order they were pinned."""
    import json
    from . import settings as S
    try:
        got = json.loads(str(S.load()["pinned_tools"] or "[]"))
    except (ValueError, TypeError):
        return []
    return [str(n) for n in got if str(n)][:12] if isinstance(got, list) else []


def pin(names) -> list:
    """Keep that list. At most a dozen: a rail of forty pinned features is the
    list of everything again, with a different heading."""
    import json
    from . import settings as S
    clean = []
    for one in (names or []):
        text = str(one or "").strip()
        if text and text not in clean:
            clean.append(text)
    clean = clean[:12]
    S.save({"pinned_tools": json.dumps(clean) if clean else ""})
    return clean


def of(name: str) -> str:
    """Which family a feature belongs to. "" when none claims it."""
    for fam in ALL:
        if name in fam["tasks"]:
            return fam["key"]
    return ""


def label(key: str) -> str:
    for fam in ALL + [OTHER]:
        if fam["key"] == key:
            return fam["label"]
    return ""


def is_setting(name: str) -> bool:
    return name in SETTINGS["tasks"]


def catalogue(names, with_settings: bool = False) -> list:
    """The families, carrying only the features that actually exist.

    Takes the names rather than reading the registry, so the page, a test and
    the command line all ask the same question of the same list - and a family
    whose features are all missing simply does not appear, rather than drawing
    an empty heading.
    """
    want = list(names)
    mine_now = arranged()
    hide = set(mine_now["hidden"])
    out = []
    groups = (mine_now["groups"] + [SETTINGS]) if with_settings else mine_now["groups"]
    for fam in groups:
        mine = [n for n in fam["tasks"] if n in want and n not in hide]
        if mine:
            out.append({**fam, "tasks": mine,
                        "alone": fam["key"] == ALONE["key"]})
    # Always every family, Settings included: a settings tab left out of the
    # Tools screen on purpose is not an unfiled feature, and listing it under
    # "Anything else" would say it had been forgotten.
    known = set(SETTINGS["tasks"])
    for fam in mine_now["groups"]:
        known |= set(fam["tasks"])
    left = [n for n in want if n not in known and n not in hide]
    # A FEATURE ADDED AFTER YOU ARRANGED YOUR TOOLS IS NOT AN UNFILED FEATURE.
    #
    # An arrangement is a snapshot of the features that existed the day it was
    # saved. Every release since then adds one, and none of them are in it - so
    # a person who had once dragged their tools about got a heading called
    # "Anything else" holding the newest and most interesting thing in the
    # release, which reads as the app having lost track of it.
    #
    # The built-in grouping knows where each one goes. If the group it belongs
    # to is on screen, it goes in it; only a feature this file has never heard
    # of is genuinely unfiled.
    if left:
        home = {}
        for fam in FAMILIES + [ALONE]:
            for name in fam["tasks"]:
                home[name] = fam["key"]
        by_key = {row["key"]: row for row in out}
        rest = []
        for name in left:
            group = by_key.get(home.get(name, ""))
            if group is None:
                rest.append(name)
                continue
            # In the built-in order within that group, so it does not simply
            # land on the end of a list somebody arranged on purpose.
            order = [n for n in next(f["tasks"] for f in FAMILIES + [ALONE]
                                     if f["key"] == group["key"])]
            group["tasks"] = sorted(set(group["tasks"] + [name]),
                                    key=lambda n: (order.index(n) if n in order
                                                   else len(order)))
        left = rest
    if left:
        out.append({**OTHER, "tasks": left})
    return out
