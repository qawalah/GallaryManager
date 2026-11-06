"""The five colour labels, what each one MEANS, and what it makes happen.

A star rating says how good a photograph is. It cannot say what you want done
with it, and those are different questions: a four-star frame might need nothing,
or sharpening, or to be one of six hundred stills in a timelapse. Every serious
photo tool has the same second axis for exactly this and it is always the same
five colours, so this app uses that rather than inventing anything.

**The colour goes in `xmp:Label`, as the colour WORD.** That is the one thing
here worth getting right and it is not obvious. Lightroom, Bridge, darktable and
digiKam all read `xmp:Label`, and what they expect to find is "Red", "Yellow",
"Green", "Blue", "Purple" - the colour, not your name for it. Write "AI
sharpening" in there and Lightroom shows a custom label nothing else recognises,
and the colour swatch you were aiming for never appears.

So the colour word is what is written, and **your name for it is written as a
keyword** beside it. That is the half that makes other apps able to act on it:
a keyword is searchable everywhere, in Synology Photos, in Explorer's Tags
column, in anything that reads IPTC - and you can add as many more as you like
per colour, which is what "so more apps can read the tag" needs.

**Reading is deliberately generous.** Bridge's out-of-the-box label set is
"Select / Second / Approved / Review / To Do", not colour names, and a library
labelled in Bridge or in an older Lightroom would otherwise read as unlabelled.
Those, the colour words, the numbers 1-5, and whatever you have named your own
colours all resolve to the same five.

Nothing here decides what happens next. A colour's ACTION - send it out to the
develop tree, into a folder of its own - is read by the tasks that do the
sending, so that "what does purple mean" has one answer in one place.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import jpegseg
from . import sidecar as sc
from . import tagwrite
from .photo import kind

# In the order every photo tool shows them.
COLOURS = ["red", "yellow", "green", "blue", "purple"]

# What actually goes into xmp:Label. Capitalised, because that is what the tools
# that read it write themselves.
WORD = {c: c.capitalize() for c in COLOURS}

# What a colour can make happen. Kept short on purpose: a list of actions is a
# list of things that can go wrong, and "send it somewhere" covers editing,
# sharpening, printing and stitching a timelapse - they differ only in which
# folder, which is a setting rather than a feature.
ACTIONS = {
    "none": "Mark it only (nothing moves)",
    "develop": "Send it to the develop tree",
}

# Names other programs give the same five labels. Bridge ships with the second
# lot and calls them a label SET, so a library labelled there is full of
# "Approved" where this app would write "Green".
ALIASES = {
    "red": ("red", "select", "1"),
    "yellow": ("yellow", "second", "2"),
    "green": ("green", "approved", "3"),
    "blue": ("blue", "review", "4"),
    "purple": ("purple", "to do", "todo", "5"),
}


@dataclass
class Definition:
    """One colour, as you have defined it."""
    colour: str
    name: str = ""
    keywords: list = field(default_factory=list)
    action: str = "none"
    folder: str = ""
    raw: bool = False

    @property
    def word(self) -> str:
        return WORD.get(self.colour, self.colour.capitalize())

    @property
    def defined(self) -> bool:
        return bool(self.name.strip())

    @property
    def sends(self) -> bool:
        return self.action == "develop"

    def title(self) -> str:
        """How to say this colour in a sentence."""
        return f"{self.word} ({self.name})" if self.defined else self.word

    def all_keywords(self) -> list:
        """The words to write on a photograph carrying this colour.

        The NAME first, because that is the one you will search for, and then
        whatever else you listed. The colour word itself is deliberately not one
        of them: it is already in xmp:Label, where the tools look, and a keyword
        called "Red" in a library where red means editing is a keyword that will
        mean nothing to you in a year.
        """
        out = []
        for word in [self.name] + list(self.keywords):
            word = str(word or "").strip()
            if word and word.lower() not in {o.lower() for o in out}:
                out.append(word)
        return out


def _split(text) -> list:
    return [w.strip() for w in str(text or "").replace("\n", ",").split(",")
            if w.strip()]


def defined(saved=None) -> list:
    """All five, as they are set up. Always five, in colour order.

    Never a short list, even when nothing has been filled in: a page that draws
    what it is given should draw five colours and say which are not defined yet,
    rather than silently showing three.
    """
    if saved is None:
        from . import settings as _s
        saved = _s.load()
    out = []
    for colour in COLOURS:
        out.append(Definition(
            colour=colour,
            name=str(saved[f"label_{colour}_name"] or "").strip(),
            keywords=_split(saved[f"label_{colour}_keywords"]),
            action=str(saved[f"label_{colour}_action"] or "none").strip(),
            folder=str(saved[f"label_{colour}_folder"] or "").strip(),
            raw=bool(saved[f"label_{colour}_raw"]),
        ))
    return out


def by_colour(colour: str, saved=None) -> Definition | None:
    colour = str(colour or "").strip().lower()
    for d in defined(saved):
        if d.colour == colour:
            return d
    return None


def colour_named(text: str, saved=None) -> str:
    """Which of the five this piece of text means, or "".

    Four ways of saying the same thing all land here: the colour word, the name
    you gave it, one of Bridge's own label names, and the number. Anything else
    is somebody else's label and is left strictly alone - a label this app does
    not understand is not a label this app should overwrite.
    """
    clean = str(text or "").strip().lower()
    if not clean:
        return ""
    for colour, words in ALIASES.items():
        if clean in words:
            return colour
    for d in defined(saved):
        if d.defined and clean == d.name.strip().lower():
            return d.colour
    return ""


# ------------------------------------------------------------------- reading

def written_label(path: str) -> str:
    """The label string actually on this file, exactly as it is written.

    The sidecar wins, for the same reason it wins for a rating: it is the one a
    person edited most recently in every tool that writes both, and it is the
    only one a RAW can have at all.
    """
    side = sc.read(path).get("xmp:Label")
    if side:
        return str(side).strip()
    if kind(path) == "jpeg":
        try:
            packet = jpegseg.xmp_packet(path)
        except Exception:                              # noqa: BLE001
            return ""
        if packet:
            got = sc.values_in(packet).get("xmp:Label")
            if got:
                return str(got).strip()
    return ""


def colour_of(path: str, saved=None) -> str:
    """Which of the five this photograph carries, or "" for none."""
    return colour_named(written_label(path), saved)


# ------------------------------------------------------------------- writing

def set_label(path: str, colour: str, keywords=(), in_file: bool = True,
              in_sidecar: bool = True) -> dict:
    """Put a colour on a photograph, and the words that go with it.

    Returns what was actually written: {"sidecar": bool, "photo": bool,
    "keywords": [...], "why": "..."} - because "it worked" and "it worked in the
    sidecar but the JPEG's metadata was full" are different answers and only one
    of them means other apps will see it inside the file.

    An empty colour CLEARS the label, which is what every tool means by no
    label. The keywords are not removed with it: they were added to whatever the
    file already carried and taking them away again would have to guess which of
    them were this app's.
    """
    colour = str(colour or "").strip().lower()
    if colour and colour not in COLOURS:
        raise ValueError(f"{colour!r} is not one of the five colours")
    word = WORD.get(colour, "")
    out = {"sidecar": False, "photo": False, "keywords": [], "why": ""}

    if in_sidecar:
        try:
            sc.write(path, **{"xmp:Label": word})
            out["sidecar"] = True
        except OSError as exc:
            out["why"] = f"the sidecar could not be written: {exc}"

    if in_file and kind(path) == "jpeg":
        try:
            out["photo"] = write_label_in_jpeg(path, word)
        except Exception as exc:                       # noqa: BLE001
            out["why"] = (out["why"] + "; " if out["why"] else "") + \
                f"inside the photo: {exc}"

    words = [w for w in keywords if str(w).strip()]
    if words and colour:
        got = tagwrite.add(path, words, in_file=in_file, in_sidecar=in_sidecar)
        out["keywords"] = list(words)
        if got.get("why") and not out["why"]:
            out["why"] = got["why"]
    return out


def write_label_in_jpeg(path: str, word: str) -> bool:
    """Put xmp:Label into a JPEG's own XMP packet. True when the file changed.

    The packet is EDITED, never rebuilt - `sidecar.merge` is the same function
    the .xmp writer uses, and for the same reason: a JPEG's XMP packet can hold
    a crop, develop settings, a whole history, and rebuilding it from the one
    attribute this app cares about would throw all of that away without a word.
    """
    with open(path, "rb") as fh:
        original = fh.read()
    if not jpegseg.is_jpeg(original):
        raise ValueError(f"not a JPEG: {path}")
    was = jpegseg.packet_to_edit(original)
    if not was.strip():
        was = sc.TEMPLATE.format(body="")
    body = sc.merge(was, {"xmp:Label": word}).encode("utf-8")
    payload = jpegseg.XMP_NS + b"\x00" + body
    rewritten = tagwrite._replace_segment(original, 0xE1, payload,
                                          lambda d: d.startswith(jpegseg.XMP_NS))
    return tagwrite._save(path, original, rewritten)


# ------------------------------------------------------- where a colour sends

def send_folder(d: Definition, develop_root: str) -> str:
    """Where this colour's photographs go.

    A blank folder means the develop tree itself, which is what "send it for
    editing" means - the tablet syncs that folder and the photo is simply in it.
    A name means a folder of its own inside the tree, which is what makes
    "sharpen these" and "these are a timelapse" separable piles rather than six
    hundred stills mixed in with tonight's edits.
    """
    develop_root = str(develop_root or "").strip()
    name = str(d.folder or "").strip().strip("/\\")
    if not name:
        return develop_root
    return os.path.join(develop_root, name)
