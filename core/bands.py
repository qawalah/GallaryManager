"""The brackets: which values get grouped together, and under what name.

"f/2.8" on a chart is not one aperture, it is everything from f/2.1 to f/3.1.
Someone chose those edges - and until now that someone was whoever wrote this
file, for everybody, for ever. A landscape library wants the small apertures
split and the wide ones in one heap; a low-light library wants the opposite.
So the tables live here, they are read at the moment a chart is drawn rather
than at import, and Setup can replace any of them.

**The shape of a table is (label, up to).** A value belongs to the first band
whose "up to" it is under; the last band catches everything above it, whatever
number is written against it. That is why the built-in tables end in "and over"
- the edge is a formality, the label is the truth.

**Yours are checked before they are kept.** Edges have to climb, a band needs a
name, and a table needs at least two of them - a one-band chart is a chart with
nothing to say. A table that does not pass is refused with the reason, and the
old one stays; a half-saved bracketing would quietly mis-sort a library and the
charts would still look fine.

Written as text, one band per line, `name = up to`:

    f/1.4 and wider = 1.5
    f/1.8           = 2.0
    ...
    f/16 and smaller = 1e9

Shutter speeds may be written as fractions (`1/500 = 1/400`), because that is
how they are said out loud and converting them by hand is how a wrong edge gets
typed in.
"""

from __future__ import annotations

import json
import re

from . import settings as S

SAVED = "bands"

# (label, up to) - the last band catches everything above it
BUILTIN = {
    "aperture": [("f/1.4 and wider", 1.5), ("f/1.8", 2.0), ("f/2.8", 3.2),
                 ("f/4", 4.5), ("f/5.6", 6.4), ("f/8", 9.0), ("f/11", 13.0),
                 ("f/16 and smaller", 1e9)],
    # The edge is "under this", so it sits BETWEEN two stops rather than on
    # one. It used to be written on the stop - ("100 and under", 100) - and ISO
    # 100, the commonest value in a daylight library, fell past it into the 200
    # band. Every edge here is between the two it separates.
    "iso": [("100 and under", 150), ("200", 300), ("400", 600), ("800", 1200),
            ("1600", 2400), ("3200", 4800), ("6400 and over", 1e9)],
    "shutter": [("1/1000 and faster", 1 / 999), ("1/500", 1 / 400),
                ("1/250", 1 / 200), ("1/125", 1 / 100), ("1/60", 1 / 45),
                ("1/30", 1 / 20), ("1/15 to 1/2", 0.5), ("1s and longer", 1e9)],
    "focal": [("under 24mm", 24), ("24-35mm", 36), ("35-50mm", 51),
              ("50-85mm", 86), ("85-135mm", 136), ("135-300mm", 301),
              ("over 300mm", 1e9)],
    "hour": [("night (0-5)", 6), ("morning (6-11)", 12),
             ("afternoon (12-17)", 18), ("evening (18-23)", 24)],
    "range": [("Ultra wide (under 24mm)", 24), ("Wide (24-35mm)", 36),
              ("Normal (36-70mm)", 71), ("Short tele (71-135mm)", 136),
              ("Tele (over 135mm)", 1e9)],
}

# what each set is called on screen, and what the number against a band means
ABOUT = {
    "aperture": ("Aperture", "f-number", "Used by the dashboard, Search and "
                 "Compare wherever apertures are counted."),
    "iso": ("ISO", "ISO number", "Sensitivity as the camera wrote it."),
    "shutter": ("Shutter", "seconds - 1/500 may be written as a fraction",
                "Exposure time. Faster speeds are smaller numbers."),
    "focal": ("Focal length", "millimetres",
              "As written on the lens, unless full-frame equivalent is asked "
              "for."),
    "hour": ("Time of day", "hour of the day, 0 to 24",
             "Which part of the day a photo was taken in."),
    "range": ("Lens range", "millimetres, full-frame equivalent",
              "The coarse wide/normal/tele grouping used when tagging by "
              "lens range."),
}

ORDER = ["aperture", "iso", "shutter", "focal", "hour", "range"]

_FRACTION = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*$")


def _number(text: str) -> float:
    """A band edge, written as a number or as a fraction like 1/400."""
    text = str(text).strip()
    hit = _FRACTION.match(text)
    if hit:
        under = float(hit.group(2))
        if under == 0:
            raise ValueError("a fraction cannot be over zero")
        return float(hit.group(1)) / under
    return float(text)


def _clean(table) -> list:
    """Whatever came back from the settings, as (label, up to) or nothing."""
    out = []
    for row in table or []:
        try:
            label, top = row[0], float(row[1])
        except (TypeError, ValueError, IndexError, KeyError):
            return []
        label = re.sub(r"\s+", " ", str(label)).strip()
        if not label:
            return []
        out.append((label, top))
    return out if len(out) >= 2 else []


def saved() -> dict:
    """{set: table} - only the sets you have replaced."""
    try:
        got = json.loads(S.load()[SAVED] or "{}")
    except (ValueError, TypeError, AttributeError):
        return {}
    out = {}
    for name, table in (got or {}).items():
        if name in BUILTIN:
            clean = _clean(table)
            if clean:
                out[name] = clean
    return out


def table(name: str, mine: dict | None = None) -> list:
    """The bands in force for this set - yours if you set any, else built in."""
    mine = saved() if mine is None else mine
    return list(mine.get(name) or BUILTIN.get(name) or [])


def how(name: str, mine: dict | None = None) -> str:
    mine = saved() if mine is None else mine
    return "yours" if name in mine else "built in"


def as_text(name: str, mine: dict | None = None) -> str:
    """The set written out for editing, one band per line."""
    lines = []
    for label, top in table(name, mine):
        lines.append(f"{label} = {_say(name, top)}")
    return "\n".join(lines)


def _say(name: str, top: float) -> str:
    if top >= 1e9:
        return "1e9"
    if name == "shutter" and 0 < top < 1:
        return f"1/{round(1 / top):g}"
    return f"{top:g}"


def parse(name: str, text: str) -> list:
    """Text back into a table, or ValueError saying what is wrong with it.

    The message is meant to be shown to whoever typed it, so it names the line.
    """
    if name not in BUILTIN:
        raise ValueError("no such set of bands")
    out = []
    for n, line in enumerate(str(text or "").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"line {n}: write it as 'name = up to'")
        label, _, top = line.partition("=")
        label = re.sub(r"\s+", " ", label).strip()
        if not label:
            raise ValueError(f"line {n}: that band has no name")
        if len(label) > 40:
            raise ValueError(f"line {n}: that name is too long")
        try:
            edge = _number(top)
        except ValueError:
            raise ValueError(f"line {n}: '{top.strip()}' is not a number") from None
        if out and edge <= out[-1][1]:
            raise ValueError(f"line {n}: '{label}' has to come after "
                             f"'{out[-1][0]}', so its edge has to be bigger")
        out.append((label, edge))
    if len(out) < 2:
        raise ValueError("a set of bands needs at least two of them")
    if len({label for label, _ in out}) != len(out):
        raise ValueError("two bands with the same name would count as one")
    return out


def save(name: str, text: str) -> list:
    """Replace one set. An empty text puts the built-in one back."""
    if name not in BUILTIN:
        raise ValueError("no such set of bands")
    mine = saved()
    if not str(text or "").strip():
        mine.pop(name, None)
        S.save({SAVED: json.dumps(mine)})
        return table(name)
    made = parse(name, text)
    if made == [tuple(r) for r in BUILTIN[name]]:
        mine.pop(name, None)          # the same as built in is not "yours"
    else:
        mine[name] = [[label, top] for label, top in made]
    S.save({SAVED: json.dumps(mine)})
    return made


def reset(name: str) -> list:
    return save(name, "")


def band(value, name: str, unsaid: str = "not said", mine: dict | None = None) -> str:
    """Which band a value falls in. Anything unreadable is never bucketed."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return unsaid
    rows = table(name, mine)
    for label, top in rows:
        if value < top:
            return label
    return rows[-1][0] if rows else unsaid


def lens_range(cap, mine: dict | None = None) -> tuple:
    """(which lens range this shot is in, how the length was measured).

    Full-frame equivalent when the file carries one, otherwise the number on
    the lens - and it says which, because on a GH4 those are two different
    numbers and a chart that mixed them silently would be wrong by a factor.
    """
    ff = getattr(cap, "focal35", None)
    measured = "full-frame equivalent"
    if not ff:
        ff = getattr(cap, "focal_length", None)
        measured = "the number on the lens"
    try:
        ff = float(ff)
    except (TypeError, ValueError):
        return "", ""
    if ff <= 0:
        return "", ""
    return band(ff, "range", "", mine), measured
