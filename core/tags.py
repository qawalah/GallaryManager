"""The keywords on a photo - "Italy", "portfolio", "Layla" - wherever they hide.

There is no single place a tag lives. Four programs write them in four formats
and each one reads only its own unless it is being generous:

    .xmp sidecar        dc:subject      Lightroom, darktable, Bridge, this app
    XMP inside a JPEG   dc:subject      Lightroom and anything else modern
    EXIF XPKeywords     0x9C9E          Windows Explorer's "Tags" box, UTF-16
    IPTC 2:25           APP13 8BIM      Photoshop, older tools, some scanners

A filter that reads one of them and calls the rest untagged is worse than no
filter at all: it says "nothing matched 'Italy'" about a folder full of photos
tagged Italy, and the answer looks like a fact. So all four are read, and the
one place a judgement is needed - a sidecar disagreeing with the file - is
written down rather than decided quietly.

Nothing here decodes a picture. It is a header read per file, the same one the
rest of the app already does.
"""

from __future__ import annotations

from . import meter

import re

from . import exif as E
from . import iptc
from . import jpegseg
from . import sidecar as sc

XP_KEYWORDS = 0x9C9E        # Windows' own tag list, UTF-16LE, semicolon separated

XMP_NS = jpegseg.XMP_NS

# Kept as names here because the test fixtures and anything else that builds a
# JPEG by hand reach for them; the parsing itself lives in core/iptc.py, so the
# "what is this tagged" and "where does this say it was taken" questions cannot
# drift apart by being answered by two different readers.
PHOTOSHOP = iptc.PHOTOSHOP
IPTC_BLOCK = iptc.IPTC_RESOURCE
IPTC_KEYWORDS = iptc.KEYWORDS


def _clean(items) -> list[str]:
    """Trim, drop blanks, drop repeats - keeping the order they were written in."""
    out: list[str] = []
    seen = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        low = text.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(text)
    return out


# --------------------------------------------------------------------------- XMP

_SUBJECT = re.compile(
    r"<(?:\w+:)?(?:subject|hierarchicalSubject)\b[^>]*>(.*?)</(?:\w+:)?"
    r"(?:subject|hierarchicalSubject)>", re.S | re.I)
_LI = re.compile(r"<(?:\w+:)?li\b[^>]*>(.*?)</(?:\w+:)?li>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")
_ENTITIES = (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
             ("&quot;", '"'), ("&apos;", "'"))


def _unescape(text: str) -> str:
    for code, char in _ENTITIES:
        text = text.replace(code, char)
    return text


def from_xmp(text: str) -> list[str]:
    """Every keyword in a piece of XMP, from dc:subject and its hierarchical twin.

    Both are read because Lightroom writes both and they are not the same list:
    hierarchicalSubject holds "Travel|Italy|Rome" while subject holds the three
    leaves separately, and a library edited across two tools can end up with only
    one of them filled in.
    """
    if not text:
        return []
    found: list[str] = []
    for block in _SUBJECT.findall(text):
        items = _LI.findall(block)
        if not items:                      # a writer that used one plain element
            items = [_TAGS.sub("", block)]
        for item in items:
            found.append(_unescape(_TAGS.sub("", item)).strip())
    return _clean(found)


def from_sidecar(path: str) -> list[str] | None:
    """The keywords in the .xmp beside a photo.

    None and [] are different answers and the difference matters. None means
    there is no sidecar, or it says nothing about keywords at all - which is what
    a sidecar written only to hold a rating looks like, and it must not be read
    as "this photo has no tags". [] means a sidecar that DOES carry a keyword
    list, and that list is empty: the tags were removed on purpose.
    """
    found = sc.beside(path)
    if not found:
        return None
    try:
        with open(found, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    meter.read(len(text))
    if not _SUBJECT.search(text):
        return None
    return from_xmp(text)


def embedded_xmp(path: str) -> list[str]:
    """Keywords from the XMP packet inside a JPEG."""
    return from_xmp(jpegseg.xmp_packet(path))


# -------------------------------------------------------------------- Windows

def _xp_text(value) -> str:
    """XPKeywords is UTF-16LE bytes pretending to be a list of numbers."""
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    elif isinstance(value, list):
        raw = bytes(b & 0xFF for b in value if isinstance(b, int))
    elif isinstance(value, int):
        raw = bytes([value & 0xFF])
    else:
        return str(value or "")
    return raw.decode("utf-16-le", "replace").rstrip("\x00")


def windows_tags(path: str) -> list[str]:
    """The tags Windows Explorer's own Tags box writes, which nothing else reads."""
    try:
        t = E.exif_block(path)
    except Exception:                                  # noqa: BLE001
        return []
    if t is None:
        return []
    value = t.directory(t.first_ifd(), {XP_KEYWORDS}).get(XP_KEYWORDS)
    if value is None:
        return []
    return _clean(_xp_text(value).split(";"))


# ----------------------------------------------------------------------- IPTC

def iptc_tags(path: str) -> list[str]:
    """Keywords from the IPTC block Photoshop and Bridge write into APP13."""
    return _clean(iptc.values(path, iptc.KEYWORDS))


# ---------------------------------------------------------------------- public

def tags_of(path: str) -> list[str]:
    """Every keyword on a photo, from whichever place holds them.

    A sidecar that carries a keyword list WINS outright, exactly as it does for a
    rating: it is the file a person edited most recently in every tool that
    writes one, and for a RAW it is the only place tags can be at all. A sidecar
    that says nothing about keywords is not a claim that there are none, so the
    file itself is read instead - which is the case that would otherwise make
    every Windows-tagged photo in a rated library look untagged.
    """
    side = from_sidecar(path)
    if side is not None:
        return side
    found: list[str] = []
    try:
        found.extend(embedded_xmp(path))
        found.extend(windows_tags(path))
        found.extend(iptc_tags(path))
    except Exception:                                  # noqa: BLE001
        pass
    return _clean(found)


def wanted_list(text: str) -> list[str]:
    """What was typed in the box, as a list. Commas, or one per line."""
    if not text:
        return []
    return _clean(re.split(r"[,\n;]+", str(text)))


def _canon(tag: str) -> str:
    """One spelling for a hierarchy, whichever separator was typed.

    Lightroom writes Travel|Italy|Rome, some tools write Travel/Italy/Rome and
    people type either. Comparing the text as written would make the same tag
    fail to match itself.
    """
    bits = [b.strip() for b in re.split(r"[|/>]", str(tag or "")) if b.strip()]
    return "|".join(bits).lower()


def _parts(tag: str) -> list[str]:
    """A hierarchical tag and everything asking for it could reasonably mean.

    Travel|Italy|Rome answers to its own full path, to each level on its own
    (Travel, Italy, Rome) and to any branch above it (Travel|Italy) - because
    asking for a branch means "and everything under it", which is exactly what a
    hierarchy is for. It does NOT answer to Italy|Rome: that branch is not where
    this photo hangs, and matching it would be a guess.
    """
    bits = [b.strip() for b in re.split(r"[|/>]", str(tag or "")) if b.strip()]
    if not bits:
        return []
    out = []
    for i in range(len(bits)):
        out.append("|".join(bits[:i + 1]).lower())   # the branches above it
        out.append(bits[i].lower())                  # and each level alone
    return out


def hits(on_photo, wanted) -> list[str]:
    """Which of the wanted tags this photo actually carries, as they were typed.

    Matched on any level of a hierarchy, so asking for "Italy" finds a photo
    tagged "Travel|Italy|Rome". Typing the full path still works and is still
    exact - asking for "Travel|Italy" does not match a bare "Italy".

    Returns the matches rather than a yes/no because a result row that says
    "tagged Italy" is worth far more than one that says it qualified.
    """
    have = set()
    for tag in on_photo or []:
        have.update(_parts(tag))
    return [w for w in wanted if w and _canon(w) in have]


def matches(on_photo, wanted, every: bool = False) -> bool:
    """Does this photo carry these tags? `every` demands all, not just one.

    An empty want list is not a filter and matches everything, so a blank box
    never silently sends nothing.
    """
    wanted = [w for w in wanted if w]
    if not wanted:
        return True
    found = hits(on_photo, wanted)
    return len(found) == len(wanted) if every else bool(found)


__all__ = ["tags_of", "wanted_list", "matches", "hits", "from_xmp",
           "from_sidecar", "embedded_xmp", "windows_tags", "iptc_tags"]
