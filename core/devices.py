"""What a camera is CALLED, as opposed to what it writes into the file.

A GH4 writes `DMC-GH4` and an A7C writes `ILCE-7C`: awkward, but you learn them
once. A phone writes `SM-G991B`, or `iPhone14,2`, and there is nothing to learn
- those are order codes. A library with three phones in it produces a chart
whose legend is three strings of hex nobody can tell apart, and the honest
answer to "which camera was this" becomes "one of those".

Two halves, and the order matters:

1. **What you called it** wins, always. Rename `SM-G991B` to "Hana's phone" and
   that is what every chart, menu and overlay says.
2. **A table of names this app happens to know** fills the rest in. It is a
   convenience, not a fact: it was written from memory, it is far from
   complete, and a phone released after it was written is not in it. So a
   guessed name is marked as a guess and always carries the code it came from,
   because "Galaxy S21" beside a file that actually says `SM-G991U` is a small
   lie that takes an hour to catch.

**Nothing is ever written to a photograph.** This is a display name and only a
display name; the file keeps saying what the camera made it say, and a search
for the code still finds them - so does a search for the name you gave it.
"""

from __future__ import annotations

import json
import re

from . import settings as S

SAVED = "camera_names"

# Model codes this app knows a friendlier name for. Written by hand, from
# memory, and deliberately short: a wrong name here is worse than no name, so
# only the ones that are unambiguous are listed, and every one of them is shown
# as a guess with its code beside it. Add your own on the Camera names tab -
# yours are not guesses and are shown without the hedge.
KNOWN = {
    # Apple's identifiers - iPhone<major>,<minor>
    "iphone10,3": "iPhone X", "iphone10,6": "iPhone X",
    "iphone11,2": "iPhone XS", "iphone11,8": "iPhone XR",
    "iphone12,1": "iPhone 11", "iphone12,3": "iPhone 11 Pro",
    "iphone12,5": "iPhone 11 Pro Max", "iphone12,8": "iPhone SE (2020)",
    "iphone13,1": "iPhone 12 mini", "iphone13,2": "iPhone 12",
    "iphone13,3": "iPhone 12 Pro", "iphone13,4": "iPhone 12 Pro Max",
    "iphone14,2": "iPhone 13 Pro", "iphone14,3": "iPhone 13 Pro Max",
    "iphone14,4": "iPhone 13 mini", "iphone14,5": "iPhone 13",
    "iphone14,7": "iPhone 14", "iphone14,8": "iPhone 14 Plus",
    "iphone15,2": "iPhone 14 Pro", "iphone15,3": "iPhone 14 Pro Max",
    "iphone15,4": "iPhone 15", "iphone15,5": "iPhone 15 Plus",
    "iphone16,1": "iPhone 15 Pro", "iphone16,2": "iPhone 15 Pro Max",
    # Samsung - the letter after the number is the market, not the model
    "sm-g991": "Galaxy S21", "sm-g996": "Galaxy S21+", "sm-g998": "Galaxy S21 Ultra",
    "sm-s901": "Galaxy S22", "sm-s906": "Galaxy S22+", "sm-s908": "Galaxy S22 Ultra",
    "sm-s911": "Galaxy S23", "sm-s916": "Galaxy S23+", "sm-s918": "Galaxy S23 Ultra",
    "sm-s921": "Galaxy S24", "sm-s926": "Galaxy S24+", "sm-s928": "Galaxy S24 Ultra",
    "sm-n986": "Galaxy Note20 Ultra", "sm-n981": "Galaxy Note20",
    "sm-a546": "Galaxy A54", "sm-a536": "Galaxy A53", "sm-a526": "Galaxy A52",
    "sm-f946": "Galaxy Z Fold5", "sm-f731": "Galaxy Z Flip5",
    # cameras whose code is not their name either
    "dmc-gh4": "Lumix GH4", "dc-gh5": "Lumix GH5", "dc-gh5m2": "Lumix GH5 II",
    "dc-gh6": "Lumix GH6", "dmc-gx80": "Lumix GX80", "dmc-lx100": "Lumix LX100",
    "ilce-7c": "Sony A7C", "ilce-7m3": "Sony A7 III", "ilce-7m4": "Sony A7 IV",
    "ilce-7rm4": "Sony A7R IV", "ilce-6400": "Sony A6400",
    "ilce-6600": "Sony A6600", "ilce-1": "Sony A1",
    "canon eos r6": "Canon R6", "canon eos r5": "Canon R5",
    "x-t4": "Fujifilm X-T4", "x-t5": "Fujifilm X-T5", "x100v": "Fujifilm X100V",
}

# Samsung codes carry a market letter on the end - SM-G991B, SM-G991U, SM-G991N
# are one phone sold in three places, and three legend entries for one phone is
# the problem this file exists to fix.
_SAMSUNG = re.compile(r"^(sm-[a-z]\d{3,4})[a-z0-9]{0,3}$")


def _key(model: str) -> str:
    return re.sub(r"\s+", " ", str(model or "").strip()).lower()


def saved() -> dict:
    """{code: what you called it} - yours, kept in Setup's settings."""
    try:
        got = json.loads(S.load()[SAVED] or "{}")
        return {_key(k): str(v).strip() for k, v in got.items()
                if _key(k) and str(v).strip()}
    except (ValueError, TypeError, AttributeError):
        return {}


def guess(model: str) -> str:
    """The name this app thinks that code is, or "" when it does not know."""
    key = _key(model)
    if not key:
        return ""
    if key in KNOWN:
        return KNOWN[key]
    hit = _SAMSUNG.match(key)
    if hit and hit.group(1) in KNOWN:
        return KNOWN[hit.group(1)]
    return ""


def name_of(model: str, mine: dict | None = None) -> str:
    """What to call this camera on screen: yours, then a guess, then the code."""
    key = _key(model)
    if not key:
        return ""
    mine = saved() if mine is None else mine
    if key in mine:
        return mine[key]
    hit = _SAMSUNG.match(key)
    if hit and hit.group(1) in mine:
        return mine[hit.group(1)]
    return guess(model) or str(model).strip()


def how(model: str, mine: dict | None = None) -> str:
    """Where the name came from: "yours", "guessed", or "" for the code itself."""
    key = _key(model)
    mine = saved() if mine is None else mine
    hit = _SAMSUNG.match(key)
    if key in mine or (hit and hit.group(1) in mine):
        return "yours"
    return "guessed" if guess(model) else ""


def label(model: str, mine: dict | None = None) -> str:
    """The name with its code beside it when the two differ.

    A guessed name on its own is a small lie waiting to be caught an hour
    later; with the code beside it, it is a helpful label you can check.
    """
    model = str(model or "").strip()
    said = name_of(model, mine)
    return said if said.lower() == model.lower() else f"{said} ({model})"


def _family(model: str) -> str:
    """One phone, not three: the market letter on a Samsung code is dropped.

    Naming `SM-G991B` and then finding `SM-G991U` still called Galaxy S21 would
    be the same split this file exists to close, so a name is kept against the
    family the code belongs to.
    """
    key = _key(model)
    hit = _SAMSUNG.match(key)
    return hit.group(1) if hit else key


def rename(model: str, name: str) -> dict:
    """Call this camera something. An empty name forgets it again."""
    model = _family(model)
    if not model:
        raise ValueError("which camera?")
    name = re.sub(r"\s+", " ", str(name or "").strip())
    if len(name) > 60:
        raise ValueError("that name is too long")
    have = saved()
    if name:
        have[model] = name
    else:
        have.pop(model, None)
    S.save({SAVED: json.dumps(have)})
    return have


def matches(model: str, wanted: str, mine: dict | None = None) -> bool:
    """Does this camera answer to `wanted` - by code OR by what it is called?

    Renaming is a display name, so a search for the code has to keep working;
    but a search for the name on the screen has to work too, or the rename has
    made the library harder to search rather than easier.
    """
    wanted = str(wanted or "").strip().lower()
    if not wanted:
        return True
    model = str(model or "")
    return (wanted in model.lower()
            or wanted in name_of(model, mine).lower())
