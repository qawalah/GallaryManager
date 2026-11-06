"""Writing a keyword onto a photograph, in the places things actually read.

Reading keywords (`core/tags.py`) has to look in four places. Writing has to
choose, and the choice was Abu's: BOTH - a sidecar beside the file, and inside
the file itself where a JPEG allows it.

    .xmp sidecar        every kind of file, including RAWs, which this app
                        never opens for writing. Lightroom, darktable, Bridge.
    XMP inside a JPEG   what every modern program reads first
    EXIF XPKeywords     Windows Explorer's own Tags column, and nothing else

Three rules, each of which is a way this could destroy something:

**Nothing is ever replaced wholesale.** A keyword is ADDED to whatever the file
already carries. Setting the list would quietly drop the keywords somebody else
put there, and they would not find out until they looked for them.

**The picture is checked, byte for byte, before the file is replaced.** Every
rewrite here goes through `jpegseg.picture_unchanged`, the same guard the rating
and location writers use: metadata may move, pixels may not.

**A file that cannot take it is left alone and says so**, rather than being
half-written. A JPEG whose metadata is already near the 64 KB segment limit is
the realistic case, and the sidecar still gets the keyword.
"""

from __future__ import annotations

import os
import re
import struct

from . import exif as E
from . import jpegseg
from . import perms
from . import sidecar as sc
from . import tags as tagread
from .photo import kind
from .replace import replace_file

XP_KEYWORDS = 0x9C9E

_PACKET = ('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
           '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
           '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
           '<rdf:Description rdf:about="" '
           'xmlns:dc="http://purl.org/dc/elements/1.1/">{body}</rdf:Description>'
           '</rdf:RDF></x:xmpmeta><?xpacket end="w"?>')

_BAG = re.compile(r"(<dc:subject\b[^>]*>)(.*?)(</dc:subject>)", re.S | re.I)
_DESC = re.compile(r"<rdf:Description\b[^>]*?(/?)>", re.S)


def _bag(keywords) -> str:
    items = "".join(f"<rdf:li>{sc._escape(k)}</rdf:li>" for k in keywords)
    return f"<dc:subject><rdf:Bag>{items}</rdf:Bag></dc:subject>"


def packet_with(text: str, keywords) -> str:
    """An XMP packet carrying these keywords - editing one if there is one."""
    block = _bag(keywords)
    if not text.strip():
        return _PACKET.format(body=block)
    if _BAG.search(text):
        return _BAG.sub(lambda _m: block, text, count=1)
    m = _DESC.search(text)
    if not m:
        return _PACKET.format(body=block)
    head = m.group(0)
    if "xmlns:dc=" not in head:
        closing = "/>" if m.group(1) else ">"
        head = head[:-len(closing)] + ' xmlns:dc="http://purl.org/dc/elements/1.1/"' \
            + closing
    if m.group(1):
        head = head[:-2].rstrip() + ">"
        return (text[:m.start()] + head + block + "</rdf:Description>"
                + text[m.end():])
    return text[:m.start()] + head + block + text[m.end():]


def _replace_segment(buf: bytes, marker: int, payload: bytes,
                     matches) -> bytes:
    """Swap one marker segment for a new payload, or add it if there is none."""
    if len(payload) + 2 > 65535:
        raise ValueError(f"that metadata block would not fit in one JPEG segment "
                         f"({len(payload) + 2} bytes)")
    head = struct.pack(">BBH", 0xFF, marker, len(payload) + 2)
    insert_at = 2
    for seg in jpegseg.segments(buf):
        if seg.marker == marker and matches(seg.data):
            return buf[:seg.offset] + head + payload \
                + buf[seg.offset + 4 + len(seg.data):]
        # Anything new goes after the segments that have to come first: a JFIF
        # APP0, and the EXIF block, which several readers expect to find at the
        # front and stop looking for if it is not.
        if seg.marker in (0xE0, 0xE1):
            insert_at = seg.offset + 4 + len(seg.data)
    return buf[:insert_at] + head + payload + buf[insert_at:]


def write_xmp_keywords(path: str, keywords) -> bool:
    """Put a keyword list into a JPEG's XMP packet. True when the file changed."""
    with open(path, "rb") as fh:
        original = fh.read()
    if not jpegseg.is_jpeg(original):
        raise ValueError(f"not a JPEG: {path}")
    # From the bytes in hand, not a header read: a packet past the first
    # quarter megabyte was read as none, and a fresh one then replaced it.
    was = jpegseg.packet_to_edit(original)
    body = packet_with(was, keywords).encode("utf-8")
    payload = jpegseg.XMP_NS + b"\x00" + body
    rewritten = _replace_segment(original, 0xE1, payload,
                                 lambda d: d.startswith(jpegseg.XMP_NS))
    return _save(path, original, rewritten)


def write_xp_keywords(path: str, keywords) -> bool:
    """Put a keyword list into EXIF's XPKeywords, where Explorer's Tags box looks.

    UTF-16LE, semicolon separated, NUL terminated, and typed as a list of BYTEs -
    which is Microsoft's own idea and not something any standard asked for.

    Longer than four bytes, so it never fits inside its directory entry: a fresh
    IFD0 is appended with the entry pointing past it at the text. The entries
    already there are copied verbatim, and every offset inside them still counts
    from the same place, so nothing else in the block has to be understood.
    """
    text = ";".join(str(k).strip() for k in keywords if str(k).strip())
    value = text.encode("utf-16-le") + b"\x00\x00"
    with open(path, "rb") as fh:
        original = fh.read()
    if not jpegseg.is_jpeg(original):
        raise ValueError(f"not a JPEG: {path}")

    at, length, _ = _find_exif(original)
    if at < 0:
        raise ValueError("this photo has no EXIF block to put a tag in")
    tiff = original[at + 4 + 6:at + length]
    t = E.Tiff(tiff, 0)
    end = t.end
    ifd0 = t.first_ifd()
    count = t.u16(ifd0)
    entries_at = ifd0 + 2
    next_ifd = t.u32(entries_at + count * 12)

    keep = [(t.u16(entries_at + e * 12),
             tiff[entries_at + e * 12:entries_at + e * 12 + 12])
            for e in range(count) if t.u16(entries_at + e * 12) != XP_KEYWORDS]
    ifd_size = 2 + (len(keep) + 1) * 12 + 4
    value_at = len(tiff) + ifd_size
    keep.append((XP_KEYWORDS,
                 struct.pack(end + "HHII", XP_KEYWORDS, 1, len(value), value_at)))
    keep.sort(key=lambda kv: kv[0])
    new_ifd0 = (struct.pack(end + "H", len(keep))
                + b"".join(entry for _tag, entry in keep)
                + struct.pack(end + "I", next_ifd))
    block = bytearray(tiff + new_ifd0 + value)
    block[4:8] = struct.pack(end + "I", len(tiff))
    rewritten = _splice_exif(original, bytes(block))
    return _save(path, original, rewritten)


def _find_exif(buf: bytes):
    insert_at = 2
    first = False
    for seg in jpegseg.segments(buf):
        if seg.marker == 0xE1 and seg.data[:4] == b"Exif":
            return seg.offset, len(seg.data) + 4, insert_at
        if not first and seg.marker == 0xE0:
            insert_at = seg.offset + len(seg.data) + 4
        first = True
    return -1, 0, insert_at


def _splice_exif(buf: bytes, payload: bytes) -> bytes:
    at, length, insert_at = _find_exif(buf)
    body = b"Exif\0\0" + payload
    if len(body) + 2 > 65535:
        raise ValueError(f"the EXIF block would not fit in one segment "
                         f"({len(body) + 2} bytes)")
    head = struct.pack(">BBH", 0xFF, 0xE1, len(body) + 2)
    if at >= 0:
        return buf[:at] + head + body + buf[at + length:]
    return buf[:insert_at] + head + body + buf[insert_at:]


def _save(path: str, original: bytes, rewritten: bytes) -> bool:
    """Write it back, but only once the picture has been proved untouched."""
    ok, why = jpegseg.picture_unchanged(original, rewritten)
    if not ok:
        raise ValueError(f"refusing to write: {why}")
    if rewritten == original:
        return False
    stamp, acl = os.stat(path), perms.xattrs_of(path)
    tmp = path + ".tagtmp"
    with open(tmp, "wb") as fh:
        fh.write(rewritten)
    replace_file(tmp, path)
    # The capture time is what pairs this file to its negative and its preview.
    # A keyword must not become "this file changed today" to every backup tool
    # and every sort-by-date in the house.
    # In NANOSECONDS, not seconds. "Put the date back" has to actually put it
    # back: a float pair keeps the second and quietly loses everything below it,
    # and the automation watch compares dates at the resolution the filesystem
    # records them. A rating rewritten in place would otherwise look like a
    # change to every tree this app writes into.
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    # And the owner, group and mode, which `os.replace` has just thrown away
    # along with the date: what is there now is a file this app wrote, not the
    # photograph's own.
    perms.restore(path, stamp, acl)
    return True


def _plus(have, keywords) -> list:
    merged = list(have)
    for k in keywords:
        if k.lower() not in {h.lower() for h in merged}:
            merged.append(k)
    return merged


def _held_in_file(path: str, have) -> list:
    """What the photo's own keyword lists should start from: everything in
    them, plus what the sidecar says.

    Not `have` alone. When a sidecar has a keyword list it wins the READ, and
    writing that list into the file replaced the file's own - a JPEG tagged
    Italy and Rome by Lightroom, with a sidecar saying Beach, came out of one
    added tag holding Beach and the new one.
    """
    found: list = []
    for read in (tagread.embedded_xmp, tagread.windows_tags, tagread.iptc_tags):
        try:
            found.extend(read(path))
        except Exception:                              # noqa: BLE001
            pass
    return _plus(tagread._clean(found), have)


def add(path: str, keywords, in_file: bool = True, in_sidecar: bool = True) -> dict:
    """Add these keywords wherever this file can hold them.

    Returns what was written and what refused, because "it worked" and "it worked
    for the sidecar and the JPEG said no" are different answers and only one of
    them means the tag is where Explorer will show it.
    """
    keywords = [str(k).strip() for k in keywords if str(k).strip()]
    done = {"sidecar": False, "xmp": False, "windows": False, "errors": []}
    if not keywords:
        return done
    have = tagread.tags_of(path)
    merged = _plus(have, keywords)
    in_photo = _plus(_held_in_file(path, have), keywords)

    if in_sidecar:
        try:
            sc.set_keywords(path, merged)
            done["sidecar"] = True
        except OSError as exc:
            done["errors"].append(f"sidecar: {exc}")

    # Both tests, and the kind comes first. A negative is never opened for
    # writing by this app - that is the rule the whole sidecar design rests on -
    # and asking only "do these four bytes look like a JPEG" quietly breaks it
    # for any file whose extension says RAW and whose first bytes do not: a
    # mis-named file, a format that leads with its embedded preview. The guard
    # that would have caught the damage compares the PICTURE, and in that case
    # the picture it compares is the preview, not the negative.
    if in_file and kind(path) == "jpeg" \
            and tagread.jpegseg.is_jpeg(jpegseg.read_header(path, 4)):
        for name, write in (("xmp", write_xmp_keywords),
                            ("windows", write_xp_keywords)):
            try:
                done[name] = write(path, in_photo)
            except Exception as exc:                   # noqa: BLE001
                done["errors"].append(f"{name}: {exc}")
    return done


def remove(path: str, keywords, in_file: bool = True, in_sidecar: bool = True) -> dict:
    """Take these keywords off, wherever this file holds them.

    The sidecar is always written - with an empty list if that is what is left,
    because an empty keyword list in a sidecar means "removed on purpose" and no
    list at all would let the old ones inside the file speak again. IPTC is the
    one place this cannot reach; a keyword still there is reported, not hidden.
    """
    gone = {str(k).strip().lower() for k in keywords if str(k).strip()}
    done = {"sidecar": False, "xmp": False, "windows": False, "errors": [],
            "left_in_iptc": []}
    if not gone:
        return done
    have = tagread.tags_of(path)
    kept = [h for h in have if h.lower() not in gone]
    in_photo = [h for h in _held_in_file(path, have) if h.lower() not in gone]
    if in_sidecar:
        try:
            sc.set_keywords(path, kept)
            done["sidecar"] = True
        except OSError as exc:
            done["errors"].append(f"sidecar: {exc}")
    if in_file and kind(path) == "jpeg" \
            and tagread.jpegseg.is_jpeg(jpegseg.read_header(path, 4)):
        for name, write in (("xmp", write_xmp_keywords),
                            ("windows", write_xp_keywords)):
            try:
                done[name] = write(path, in_photo)
            except Exception as exc:                   # noqa: BLE001
                done["errors"].append(f"{name}: {exc}")
        try:
            done["left_in_iptc"] = [t for t in tagread.iptc_tags(path)
                                    if t.lower() in gone]
        except Exception:                              # noqa: BLE001
            pass
    return done


def keywords_for_preview(source_tags, extra) -> list:
    """What a preview should carry: the original's keywords, plus the bracket tag.

    A preview is made to be rated on a tablet and thrown away, but while it
    exists it should be findable by the same words as the photograph it came
    from - otherwise "show me the brackets" answers differently depending on
    which folder you are standing in.
    """
    out = list(source_tags or [])
    for k in extra or []:
        if str(k).strip() and str(k).strip().lower() not in {
                str(o).strip().lower() for o in out}:
            out.append(str(k).strip())
    return out
