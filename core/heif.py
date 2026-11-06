"""HEIC and HEIF: where the EXIF sits inside one, and teaching Pillow to open it.

Every iPhone since 2017 saves HEIC unless told otherwise, and so do many
Android phones and some cameras. The app counted those files as photographs
and then knew nothing about them: no date, no camera, no position, no
thumbnail. Two separate halves fix that, and only one of them needs anything
installed.

**Reading the EXIF is plain Python.** A HEIF file is a tree of ISO media boxes,
the same family as MP4 and CR3. The `meta` box near the front lists the file's
items (`iinf`), one of which is of type `Exif`, and says where each item's bytes
are (`iloc`). Those bytes are four bytes of offset and then an ordinary TIFF
block - exactly what `core/exif.Tiff` already reads out of a JPEG. So nothing
about dates, cameras or GPS needed to change: only the finding.

**Decoding the picture needs libheif**, which Python does not have. `pi-heif`
(decode only, LGPL, a couple of megabytes) or `pillow-heif` (the same with an
encoder) adds it to Pillow. The Windows program ships `pi-heif` beside Pillow and
the NAS container installs it once, but neither can be relied on: a NAS on an
ARM chip nobody built it for has no copy. Without one, thumbnails of HEIC files
fall back to Synology's own, as they always did, and nothing else changes.
"""

from __future__ import annotations

import struct
import threading

from . import meter

EXTS = (".heic", ".heif")

# What a feature says about a HEIC it could not open. The install line is the
# whole fix, so it is in the message rather than in a guide somewhere.
WITHOUT = ("HEIC needs a decoder that is not installed here "
           "(python -m pip install pi-heif)")


def named(path: str) -> bool:
    """Whether this file is called a HEIC or HEIF."""
    return path.lower().endswith(EXTS)


# The brands a still-image HEIF announces in its `ftyp` box. A CR3 or an MP4 is
# the same box format with other brands, and must not be read as one of these:
# a CR3's metadata is laid out differently and would be misread.
BRANDS = {b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"mif1",
          b"msf1", b"avif", b"avis"}

# How much of the file any one piece may claim. An EXIF block is tens of
# kilobytes; a meta box with a few hundred grid tiles is still well under a
# megabyte. A length past this is a damaged file, and reading what it claims
# would be a way to make the app read a gigabyte to find a date.
MAX_PIECE = 4_194_304


def is_heif(buf: bytes) -> bool:
    """Whether these first bytes are a HEIF still image (HEIC, HEIF, AVIF)."""
    if len(buf) < 16 or buf[4:8] != b"ftyp":
        return False
    size = struct.unpack_from(">I", buf, 0)[0]
    end = min(len(buf), max(16, size))
    if buf[8:12] in BRANDS:
        return True
    # The compatible brands follow the major brand and its version.
    return any(buf[i:i + 4] in BRANDS for i in range(16, end - 3, 4))


def _boxes(buf: bytes, start: int, end: int, partial: bool = False):
    """(type, payload start, box end) for each box between start and end.

    Stops at the first box that does not fit rather than guessing past it: a
    size field that lies is a damaged file, and everything after it is noise.
    With `partial`, a last box that runs past `end` is still named - that is
    the front of a file, and the box simply goes on beyond what was read.
    """
    at = start
    while at + 8 <= end:
        size, typ = struct.unpack_from(">I4s", buf, at)
        head = 8
        if size == 1:
            if at + 16 > end:
                return
            size = struct.unpack_from(">Q", buf, at + 8)[0]
            head = 16
        elif size == 0:
            size = end - at                # "to the end of the enclosing box"
        if size < head:
            return
        if at + size > end:
            if partial:
                yield typ, at + head, at + size
            return
        yield typ, at + head, at + size
        at += size


def _uint(buf: bytes, at: int, size: int) -> tuple[int, int]:
    """An unsigned integer of 0, 4 or 8 bytes, and where the next field starts."""
    if size == 0:
        return 0, at
    if size == 4:
        return struct.unpack_from(">I", buf, at)[0], at + 4
    if size == 8:
        return struct.unpack_from(">Q", buf, at)[0], at + 8
    raise ValueError(f"a field of {size} bytes")


def _exif_items(buf: bytes, start: int, end: int) -> set[int]:
    """The ids of the items of type `Exif`, from an `iinf` box's payload."""
    version = buf[start]
    at = start + 4
    if version == 0:
        at += 2
    else:
        at += 4
    found = set()
    for typ, body, box_end in _boxes(buf, at, end):
        if typ != b"infe" or body + 4 > box_end:
            continue
        v = buf[body]
        # Versions 0 and 1 of an item entry carry no type at all; HEIF needs 2
        # or later, so anything older is not something to look inside.
        if v < 2:
            continue
        p = body + 4
        if v == 2:
            item = struct.unpack_from(">H", buf, p)[0]
            p += 2
        else:
            item = struct.unpack_from(">I", buf, p)[0]
            p += 4
        p += 2                              # the protection index
        if buf[p:p + 4] == b"Exif":
            found.add(item)
    return found


def _locations(buf: bytes, start: int, end: int) -> dict[int, tuple]:
    """{item id: (construction method, [(offset, length), ...])} from an `iloc`.

    The offsets are absolute file positions for method 0 and positions inside
    the `idat` box for method 1. Method 2 (bytes borrowed from another item) is
    never used for EXIF, and is left out rather than half-handled.
    """
    version = buf[start]
    at = start + 4
    sizes = buf[at]
    offset_size, length_size = sizes >> 4, sizes & 0x0F
    sizes = buf[at + 1]
    base_size = sizes >> 4
    index_size = (sizes & 0x0F) if version in (1, 2) else 0
    at += 2
    if version < 2:
        count = struct.unpack_from(">H", buf, at)[0]
        at += 2
    else:
        count = struct.unpack_from(">I", buf, at)[0]
        at += 4
    out: dict[int, tuple] = {}
    for _ in range(min(count, 65_535)):
        if at >= end:
            break
        if version < 2:
            item = struct.unpack_from(">H", buf, at)[0]
            at += 2
        else:
            item = struct.unpack_from(">I", buf, at)[0]
            at += 4
        method = 0
        if version in (1, 2):
            method = struct.unpack_from(">H", buf, at)[0] & 0x0F
            at += 2
        at += 2                             # the data reference index
        base, at = _uint(buf, at, base_size)
        extents = struct.unpack_from(">H", buf, at)[0]
        at += 2
        spans = []
        for _ in range(extents):
            if index_size:
                _, at = _uint(buf, at, index_size)
            offset, at = _uint(buf, at, offset_size)
            length, at = _uint(buf, at, length_size)
            spans.append((base + offset, length))
        out[item] = (method, spans)
    return out


def _read_at(path: str, offset: int, length: int) -> bytes:
    """Bytes from further into the file than the first read reached. Counted."""
    if offset < 0 or length <= 0 or length > MAX_PIECE:
        return b""
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            got = fh.read(length)
    except OSError:
        return b""
    meter.read(len(got))
    return got


def _piece(path: str, buf: bytes, offset: int, length: int) -> bytes:
    """From the bytes already read when they reach that far, from the disk if not."""
    if offset + length <= len(buf):
        return buf[offset:offset + length]
    return _read_at(path, offset, length)


def _tiff_start(payload: bytes) -> int:
    """Where the TIFF header starts inside an EXIF item, or -1.

    The item opens with a four-byte count of what to skip, and that is normally
    six, for the "Exif\\0\\0" a JPEG also puts first. Some writers say 0 and
    then put "Exif\\0\\0" there anyway, so the count is checked against what is
    really there, and the header looked for nearby when it does not match.
    """
    if len(payload) < 12:
        return -1
    skip = struct.unpack_from(">I", payload, 0)[0]
    at = 4 + skip
    if payload[at:at + 4] in (b"II*\0", b"MM\0*"):
        return at
    for marker in (b"II*\0", b"MM\0*"):
        found = payload.find(marker, 4, 64)
        if found >= 0:
            return found
    return -1


def exif_tiff(path: str, buf: bytes) -> tuple[bytes, int] | None:
    """(bytes, where the TIFF header starts in them), or None when there is none.

    `buf` is the front of the file as already read. Anything the boxes point to
    beyond it - the meta box of a file with many tiles, or EXIF stored at the
    end - is read from the disk, only as much as is needed.
    """
    if not is_heif(buf):
        return None
    try:
        meta = None
        for typ, body, end in _boxes(buf, 0, len(buf), partial=True):
            if typ == b"meta":
                meta = (body, end)
                break
        if meta is None:
            return None
        body, end = meta
        if end > len(buf):
            # The meta box runs past the first read: fetch it whole, and work
            # in its own bytes from there on.
            whole = _read_at(path, body, end - body)
            if len(whole) != end - body:
                return None
            data, start, stop, shift = whole, 0, len(whole), body
        else:
            data, start, stop, shift = buf, body, end, 0

        # `meta` is a full box: a version and flags come before its children.
        items: set[int] = set()
        where: dict[int, tuple] = {}
        idat = None
        for typ, b, e in _boxes(data, start + 4, stop):
            if typ == b"iinf":
                items = _exif_items(data, b, e)
            elif typ == b"iloc":
                where = _locations(data, b, e)
            elif typ == b"idat":
                idat = (b + shift, e - b)
        for item in sorted(items):
            if item not in where:
                continue
            method, spans = where[item]
            if method == 1 and idat is None:
                continue
            if method not in (0, 1):
                continue
            parts = []
            for offset, length in spans:
                if method == 1:
                    offset += idat[0]
                if length == 0:
                    continue
                part = _piece(path, buf, offset, length)
                if len(part) != length:
                    parts = []
                    break
                parts.append(part)
            payload = b"".join(parts)
            at = _tiff_start(payload)
            if at >= 0:
                return payload, at
    except (struct.error, IndexError, ValueError):
        return None
    return None


# ---------------------------------------------------------------- the decoder
#
# Registered once per process, on first need, and never at import: importing
# libheif costs a measurable moment, and most runs of most tasks never decode a
# picture at all.
_OPENER_LOCK = threading.Lock()
_OPENER: str | None = None                  # None: not tried yet; "": not there


def decoder() -> str:
    """The name of the HEIC decoder Pillow can now use, or "" when there is none.

    The first call teaches Pillow to open HEIC; later calls only answer.
    `pi-heif` is tried first because it is the one this app ships; a
    `pillow-heif` somebody installed themselves works just as well.
    """
    global _OPENER
    with _OPENER_LOCK:
        if _OPENER is not None:
            return _OPENER
        _OPENER = ""
        for module, name in (("pi_heif", "pi-heif"), ("pillow_heif", "pillow-heif")):
            try:
                got = __import__(module)
                got.register_heif_opener()
            except Exception:                              # noqa: BLE001
                # ImportError when it is not there; anything else when it is
                # there but cannot load its library, which on a NAS is a
                # missing system library - the same answer either way.
                continue
            _OPENER = f"{name} {getattr(got, '__version__', '')}".strip()
            break
        return _OPENER


def can_decode() -> bool:
    """Whether a HEIC can be opened as a picture here. Registers it if it can."""
    return bool(decoder())
