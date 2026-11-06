"""The page's own words, and the Guide's, as text the Wording tab can edit.

A tool's text is in its declaration and reaches the page through
`Task.describe()`. The rest of what the page says - a toast, a dialog, the
count under a folder - used to be written straight into the script, where
nothing could find it, test it or change it without a release. Those strings
are in one table now, `app/web/page/strings.json`, which the page reads as
`S` (`app/web/page/strings.js`). The Guide is already Python data
(`app/page.py`); its pages are named here by the slug of their title.

Keys, beside the tools' own (`core/wording.py`):

    page.<name>                    one string of the page
    guide.<slug>.title             a Guide page's heading
    guide.<slug>.body.<n>          its n-th paragraph, counted from 1

Overrides of these reach the page when it is served: the script carries an
empty `WORDING` object, and `served()` puts the edits into it. With nothing
edited the page is sent exactly as it was built.
"""

from __future__ import annotations

import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.path.join(HERE, "app", "web", "page", "strings.json")

# What the script says before anything is edited. `served()` swaps it for the
# edits, once, so it must appear in the page exactly once.
MARK = "/*wording*/{}"

_SEEN: dict = {}


def strings() -> dict:
    """name -> text, in the file's order. Read again when the file changes, so
    the merge tool's check in a fresh process sees what it just wrote."""
    stamp = os.stat(FILE).st_mtime_ns
    hit = _SEEN.get(FILE)
    if hit and hit[0] == stamp:
        return dict(hit[1])
    with open(FILE, encoding="utf-8") as fh:
        table = json.load(fh)
    _SEEN[FILE] = (stamp, table)
    return dict(table)


def slug(title: str) -> str:
    """"RAW, preview, sidecar" -> "raw-preview-sidecar"."""
    return re.sub(r"[^a-z0-9]+", "-", str(title or "").lower()).strip("-")


def guide() -> list:
    from app.page import GUIDE
    return GUIDE


# ----------------------------------------------------------- shipped text

def fields(name: str) -> list[dict]:
    """The Wording tab's cards for "page" or "guide", in the order they show."""
    from core import wording as W
    out = []
    if name == "page":
        out = [{"key": f"page.{k}", "shipped": v} for k, v in strings().items()]
    elif name == "guide":
        for page in guide():
            lead = f"guide.{slug(page['title'])}"
            out.append({"key": f"{lead}.title", "shipped": page["title"]})
            for n, text in enumerate(page.get("body") or [], 1):
                out.append({"key": f"{lead}.body.{n}", "shipped": text})
    for f in out:
        f["kind"] = W.kind_of(f["key"])
    return out


def shipped() -> dict:
    return {f["key"]: f["shipped"] for name in ("page", "guide")
            for f in fields(name)}


# ------------------------------------------------------------- serving

def edits_for_page(overrides: dict) -> dict:
    """{"page": {name: text}, "guide": {index: {"title", "body": {i: text}}}}
    for the edits that touch the page, or {} when none do. The Guide is
    addressed by position here because the page has no slugs."""
    page = {k[len("page."):]: v for k, v in overrides.items()
            if k.startswith("page.")}
    by_slug = {slug(p["title"]): i for i, p in enumerate(guide())}
    said: dict = {}
    for key, text in overrides.items():
        if not key.startswith("guide."):
            continue
        bits = key.split(".")
        at = by_slug.get(bits[1]) if len(bits) > 2 else None
        if at is None:
            continue
        one = said.setdefault(str(at), {})
        if bits[2] == "title":
            one["title"] = text
        elif bits[2] == "body" and len(bits) == 4 and bits[3].isdigit():
            one.setdefault("body", {})[str(int(bits[3]) - 1)] = text
    out = {}
    if page:
        out["page"] = page
    if said:
        out["guide"] = said
    return out


def served(built: str, overrides: dict | None = None) -> str:
    """The page as built, with the page and Guide edits put in."""
    from core import wording as W
    edits = edits_for_page(W.load() if overrides is None else overrides)
    if not edits:
        return built
    body = json.dumps(edits, ensure_ascii=False).replace("</", "<\\/")
    return built.replace(MARK, body, 1)


def where(key: str) -> str:
    """"app/web/page/strings.json:12" for a page string; a Guide key is a
    literal in app/page.py, found the way a tool's are."""
    if key.startswith("page."):
        name = json.dumps(key[len("page."):])
        with open(FILE, encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                if line.lstrip().startswith(name + ":"):
                    return f"app/web/page/strings.json:{n}"
        return ""
    return ""
