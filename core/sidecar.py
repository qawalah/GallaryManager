"""The .xmp beside a photo: how anything is recorded about a file we will not open.

A RAW is a negative. This app never opens one for writing, so everything it has
to say about a RAW - a rating, a location, a corrected capture time - goes in a
small XML file beside it. Every tool that matters (Lightroom, darktable, Synology
Photos) already reads these.

The one thing worth being careful about is that a sidecar holds SEVERAL things at
once. Writing a location must not wipe a rating written last week, so every write
here reads whatever is already on file and rewrites the union.

Kept in its own module because both the reader and the writer need it, and having
the reader import the writer would tie a knot in the imports for no reason.
"""

from __future__ import annotations

from . import meter

import datetime as dt
import os
import re

ATTRS = ("exif:GPSLatitude", "exif:GPSLongitude", "exif:GPSVersionID",
         "exif:DateTimeOriginal", "xmp:Rating", "xmp:Label")


def sidecar_path(image_path: str) -> str:
    return os.path.splitext(image_path)[0] + ".xmp"


# ------------------------------------------------- "is there one?" asked once
#
# THIS QUESTION WAS ASKED TWELVE TIMES PER PHOTOGRAPH.
#
# Not by one caller - by seven, none of which knew about the others: the
# signature asks, the capture time asks, the rating asks, the label asks, the
# tags ask, the coordinates ask. Each ask is two `isfile` calls (`.xmp` and
# `.XMP`), so reading one photograph cost twenty-four stats on a file that in
# most libraries does not exist. Across eighty thousand photographs on a NAS
# that is minutes of asking the filesystem the same thing.
#
# The folder already knows. One listing answers it for every photograph in that
# folder, for every one of the seven callers, with no further syscalls at all -
# and the listing is thrown away the moment the folder's own date moves, which
# is exactly when a sidecar could have been created or deleted. A sidecar that
# is merely EDITED does not move the folder's date, and does not need to: this
# answers what the file is called, and `facts.signature` stats the sidecar
# itself to see what it says.
#
# `forget()` is the belt to that braces, called by the writer below, for the
# filesystem whose directory clock is too coarse to notice two changes in the
# same tick.
_FOLDERS: dict = {}
_KEEP_FOLDERS = 64


def forget(folder: str = "") -> None:
    """Drop what a folder was listed as. All of them when nothing is named."""
    if folder:
        _FOLDERS.pop(os.path.normcase(os.path.abspath(folder)), None)
    else:
        _FOLDERS.clear()


def _names_in(folder: str) -> dict | None:
    """{lower-cased name: the name as the disk spells it}, or None if unreadable."""
    from . import steady
    key = os.path.normcase(os.path.abspath(folder))
    hit = _FOLDERS.get(key)
    # The caller holding this file still has just stat'd it and is asking its
    # dozen questions. The folder is not listed again inside that.
    if hit is not None and steady.folder_held(folder):
        return hit[1]
    try:
        stamp = os.stat(folder).st_mtime_ns
    except OSError:
        _FOLDERS.pop(key, None)
        return None
    if hit is not None and hit[0] == stamp:
        return hit[1]
    try:
        names = {n.lower(): n for n in os.listdir(folder)}
    except OSError:
        return None
    if len(_FOLDERS) >= _KEEP_FOLDERS:
        # A pass walks a tree folder by folder, so the one it has just left is
        # the one it is least likely to want again.
        _FOLDERS.pop(next(iter(_FOLDERS)), None)
    _FOLDERS[key] = (stamp, names)
    return names


def beside(image_path: str) -> str | None:
    """The sidecar for this photo, if one exists. Case as the disk has it."""
    folder, name = os.path.split(image_path)
    stem = os.path.splitext(name)[0]
    names = _names_in(folder or ".")
    if names is None:
        # The folder could not be listed. Ask the file directly, as before -
        # being unable to list a folder is not a reason to say there is no
        # sidecar in it.
        base = os.path.splitext(image_path)[0]
        for ext in (".xmp", ".XMP"):
            p = base + ext
            if p != image_path and os.path.isfile(p):
                return p
        return None
    want = (stem + ".xmp").lower()
    there = names.get(want)
    if there is None or there == name:
        return None
    return os.path.join(folder, there)


def dms_text(value: float, positive: str, negative: str) -> str:
    """XMP writes a coordinate as "25,17.12300N", not as a decimal."""
    degrees = int(abs(value))
    minutes = (abs(value) - degrees) * 60.0
    return f"{degrees},{minutes:.5f}{negative if value < 0 else positive}"


def values_in(text: str) -> dict:
    """What a piece of XMP says, whether it is a sidecar or a JPEG's own packet.

    Separate from `read` because the two callers hold the same XML for different
    reasons: a .xmp is a file, and the packet inside a JPEG is a string spliced
    out of the picture. One parser, so a label written into a photograph is read
    back by exactly the code that reads it out of a sidecar.
    """
    out = {}
    for name in ATTRS:
        m = re.search(rf'{re.escape(name)}\s*=\s*"([^"]*)"', text or "")
        if not m:                       # some writers use elements, not attributes
            m = re.search(rf"<{re.escape(name)}>([^<]*)</{re.escape(name)}>",
                          text or "")
        if m:
            out[name] = m.group(1).strip()
    return out


def read(image_path: str) -> dict:
    """Whatever a sidecar beside this photo already says. Empty when there is none."""
    path = beside(image_path)
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return {}
    meter.read(len(text))
    return values_in(text)


NAMESPACES = {
    "exif": "http://ns.adobe.com/exif/1.0/",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "lr": "http://ns.adobe.com/lightroom/1.0/",
}

TEMPLATE = """<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:exif="http://ns.adobe.com/exif/1.0/"
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:dc="http://purl.org/dc/elements/1.1/">
{body}  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
"""

_DESCRIPTION = re.compile(r"<rdf:Description\b[^>]*?(/?)>", re.S)


def write(image_path: str, **attrs) -> str:
    """Merge these attributes into the sidecar, keeping everything else it holds.

    That sentence used to be false, and the way it was false is the worst kind:
    the file was REBUILT from the six attributes this app happens to know about,
    so writing a rating onto a photo whose sidecar came from Lightroom threw away
    its keywords, its label, its crop and its develop settings. Nothing said a
    word, and the loss only shows up the next time that photo is opened in the
    program that wrote them.

    So an existing sidecar is now EDITED: each value is replaced where it already
    sits, anything new is inserted into the rdf:Description, and every other byte
    of the document is left exactly as it was. Only a sidecar that does not exist
    yet is written from the template.
    """
    wanted = {k: v for k, v in attrs.items() if v is not None}
    path = beside(image_path)
    if not path:
        body = "".join(f'    {k}="{v}"\n' for k, v in sorted(wanted.items()))
        text = TEMPLATE.format(body=body)
        path = sidecar_path(image_path)
    else:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            text = TEMPLATE.format(body="")
        text = merge(text, wanted)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    # The folder listing above is keyed on the folder's own date, and a sidecar
    # created here moves it - but a filesystem whose directory clock is coarse
    # can land two changes in one tick, so the writer says so directly rather
    # than trusting the clock.
    forget(os.path.dirname(path))
    # A sidecar takes after its photograph. A root-owned .xmp beside your RAW is
    # a rating that quietly does not exist to Lightroom, to Drive, to anything
    # that reads the library as you rather than as this app.
    from . import perms
    perms.like(path, image_path)
    return path


def drop(image_path: str, prefix: str) -> int:
    """Take every attribute starting with `prefix` out of the sidecar.

    The removal counterpart of `write`, and edited the same way: only the named
    attributes go, and every other byte - keywords, label, crop, develop
    settings - is left exactly where it was. A sidecar that does not exist is
    not created just to have nothing removed from it.

    Returns how many were removed, so "it had no location" and "the location is
    gone" are different answers.
    """
    path = beside(image_path)
    if not path or not prefix:
        return 0
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return 0
    name = re.escape(prefix) + r"[\w.:-]*"
    attr = re.compile(r"\s+" + name + r'\s*=\s*"[^"]*"')
    elem = re.compile(r"\s*<(" + name + r")\b[^>]*>.*?</\1>", re.S)
    lone = re.compile(r"\s*<" + name + r"\b[^>]*/>")
    new, n1 = attr.subn("", text)
    new, n2 = elem.subn("", new)
    new, n3 = lone.subn("", new)
    total = n1 + n2 + n3
    if not total:
        return 0
    stamp = os.stat(path)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new)
    from . import perms
    perms.restore(path, stamp)
    return total


def merge(text: str, values: dict) -> str:
    """Put these attributes into a piece of XMP, leaving everything else alone."""
    missing = {}
    for name, value in values.items():
        value = _escape(value)
        attr = re.compile(rf'({re.escape(name)}\s*=\s*")([^"]*)(")')
        if attr.search(text):
            text = attr.sub(lambda m: m.group(1) + value + m.group(3), text, count=1)
            continue
        element = re.compile(rf"(<{re.escape(name)}>)([^<]*)(</{re.escape(name)}>)")
        if element.search(text):
            text = element.sub(lambda m: m.group(1) + value + m.group(3), text, count=1)
            continue
        missing[name] = value
    if not missing:
        return text

    m = _DESCRIPTION.search(text)
    if not m:
        # Not a shape this understands. Appending would produce something no
        # reader can parse, so the safe answer is to leave the file alone and
        # let the caller's value be the one that is lost, not the file.
        return text
    added = "".join(f'\n    {k}="{v}"' for k, v in sorted(missing.items()))
    head = m.group(0)
    for prefix in sorted({k.split(":")[0] for k in missing}):
        if prefix in NAMESPACES and f"xmlns:{prefix}=" not in head:
            added = f'\n    xmlns:{prefix}="{NAMESPACES[prefix]}"' + added
    closing = "/>" if m.group(1) else ">"
    return text[:m.start()] + head[:-len(closing)] + added + closing + text[m.end():]


def _escape(value) -> str:
    text = str(value).replace("&", "&amp;").replace("<", "&lt;")
    return text.replace(">", "&gt;").replace('"', "&quot;")


_BAG = re.compile(r"(<dc:subject\b[^>]*>)(.*?)(</dc:subject>)", re.S | re.I)


def subject_block(keywords) -> str:
    """A dc:subject bag, as every program that reads keywords expects it."""
    items = "".join(f"\n     <rdf:li>{_escape(k)}</rdf:li>" for k in keywords)
    return f"<dc:subject>\n    <rdf:Bag>{items}\n    </rdf:Bag>\n   </dc:subject>"


def set_keywords(image_path: str, keywords) -> str:
    """Write this keyword list into the sidecar, touching nothing else.

    Same rule as `write`: an existing document is edited, never rebuilt. A
    keyword list is the one thing here most likely to be sitting in a file
    somebody's cataloguing program also cares about.
    """
    keywords = [str(k).strip() for k in keywords if str(k).strip()]
    block = subject_block(keywords)
    path = beside(image_path)
    if not path:
        text = TEMPLATE.format(body="")
        path = sidecar_path(image_path)
    else:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            text = TEMPLATE.format(body="")

    if _BAG.search(text):
        text = _BAG.sub(lambda _m: block, text, count=1)
    else:
        m = _DESCRIPTION.search(text)
        if not m:
            return path
        head = m.group(0)
        if "xmlns:dc=" not in head:
            head = head[:-len("/>" if m.group(1) else ">")] \
                + f'\n    xmlns:dc="{NAMESPACES["dc"]}"' \
                + ("/>" if m.group(1) else ">")
        if m.group(1):
            # A self-closing description holds attributes only, so it has to be
            # opened up before an element can go inside it.
            head = head[:-2].rstrip() + ">"
            text = (text[:m.start()] + head + f"\n   {block}\n  </rdf:Description>"
                    + text[m.end():])
        else:
            text = text[:m.start()] + head + f"\n   {block}" + text[m.end():]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def read_datetime(image_path: str):
    """A corrected capture time from a sidecar, or None.

    This is how a RAW gets its clock fixed. Correcting the JPEGs of a shoot and
    leaving the RAWs on the old clock would break every pair in it at once - a RAW
    is tied to its JPEG by capture time - and the breakage would surface much
    later, as RAWs that look orphaned, in a task with nothing to do with clocks.
    """
    raw = read(image_path).get("exif:DateTimeOriginal")
    if not raw:
        return None
    text = str(raw).strip().replace("T", " ")[:19]
    for form in ("%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(text, form)
        except ValueError:
            continue
    return None
