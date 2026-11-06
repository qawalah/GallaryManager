"""Walking a JPEG's marker segments, without decoding the picture.

Everything this project does to a photo's metadata starts here: the file is a
sequence of segments, the ones we care about sit at the front, and the picture
data begins at the start-of-scan marker and runs to the end of the file.

Nothing in this module decodes an image. That is the whole point - a twenty
megabyte photo costs one small read, and the pixels are never touched.
"""

from __future__ import annotations

import os as _os
import threading as _threading

from . import meter

# Markers that carry no payload and so have no length field after them.
_STANDALONE = {0xD8, 0x01} | set(range(0xD0, 0xD8))
SOS = 0xDA          # start of scan - the picture begins here
EOI = 0xD9          # end of image

# How much of a file to read when only the headers are wanted. EXIF lives at the
# very front; a quarter of a megabyte covers it with room to spare, and it means a
# folder of 20 MB photos costs a header read each rather than 700 full reads.
HEADER_BYTES = 262_144
MAX_HEADER_BYTES = 4_194_304


class Segment:
    __slots__ = ("marker", "data", "offset")

    def __init__(self, marker: int, data: bytes, offset: int):
        self.marker = marker
        self.data = data
        self.offset = offset        # of the 0xFF that starts the segment

    def __repr__(self) -> str:      # pragma: no cover - debugging convenience
        return f"Segment(0x{self.marker:02X}, {len(self.data)} bytes, at {self.offset})"


def is_jpeg(buf: bytes) -> bool:
    return len(buf) >= 4 and buf[0] == 0xFF and buf[1] == 0xD8


# The last file whose front was read, and what it looked like when it was.
#
# Asking a photograph three questions in a row is three reads of the same
# quarter megabyte: the keywords alone are read out of the XMP packet, the EXIF
# block and the IPTC block, and each of those starts here. One entry is enough
# to collapse that, because the three always happen back to back - and one entry
# is also a bounded amount of memory, which a dictionary of them would not be.
#
# **Keyed on the file, not on its name.** Size, modification time and inode, from
# one stat. A stat is a few microseconds and a read over a network share is
# milliseconds, so the check pays for itself immediately - and without it this
# would hand back the bytes from before a write that had happened in between,
# which is the kind of bug that shows up as a rating that did not take.
_LAST: tuple = ()
_LAST_BYTES = b""
_LAST_LOCK = _threading.Lock()

# The caller that is about to ask this file a dozen questions says so, and the
# stat it already took is used instead of eleven more. See `core/steady.py`.
def _mark(path: str, max_bytes: int) -> tuple:
    from . import steady
    st = steady.stat_of(path)
    if st is None:
        try:
            st = _os.stat(path)
        except OSError:
            return ()
    return (path, st.st_size, st.st_mtime_ns, st.st_ino, max_bytes)


def read_header(path: str, max_bytes: int = HEADER_BYTES) -> bytes:
    """The front of a file, or all of it if it is smaller. Never raises.

    Every photograph this app looks at comes through here, which is why the read
    is counted: on a NAS the cost of a run is the disk, and the container is
    often not allowed to read the kernel's own byte counters. See
    `core/meter.py`.

    The same file asked for twice in a row is read once - see `_LAST` above.
    """
    global _LAST, _LAST_BYTES
    mark = _mark(path, max_bytes)
    if mark:
        with _LAST_LOCK:
            if mark == _LAST:
                return _LAST_BYTES
    try:
        with open(path, "rb") as fh:
            got = fh.read(max_bytes)
    except OSError:
        return b""
    meter.read(len(got))
    if mark:
        with _LAST_LOCK:
            _LAST, _LAST_BYTES = mark, got
    return got


def segments(buf: bytes):
    """Yield each marker segment up to the start of the scan.

    Stops at SOS deliberately: everything past it is compressed picture data, and
    scanning it for 0xFF bytes would find markers that are not markers.
    """
    yield from walked(buf)[0]


def walked(buf: bytes) -> tuple:
    """(the segments before the scan, whether the walk got to the end of them).

    The second half is the one that matters to a writer. A walk that reached
    the start of the picture has seen every header segment; one that ran out of
    buffer first - a header read cut short by a big ICC profile or a stack of
    MPF previews - has not, and "no XMP packet in what was read" is then not
    "no XMP packet in the file".
    """
    out = []
    if not is_jpeg(buf):
        return out, True
    i = 2
    n = len(buf)
    while True:
        if i + 3 >= n:
            return out, False                # ran out of buffer, markers go on
        if buf[i] != 0xFF:
            return out, True
        marker = buf[i + 1]
        if marker in _STANDALONE:
            i += 2
            continue
        if marker in (SOS, EOI):
            return out, True
        length = (buf[i + 2] << 8) | buf[i + 3]
        if length < 2:
            return out, True
        if i + 2 + length > n:
            return out, False                # this segment runs past the buffer
        start = i + 4
        out.append(Segment(marker, buf[start:i + 2 + length], i))
        i = start + (length - 2)


# The XMP packet inside a JPEG announces itself with this namespace and a NUL.
XMP_NS = b"http://ns.adobe.com/xap/1.0/"


def packet_in(buf: bytes) -> tuple:
    """(the XMP text in these bytes, whether the header walk was complete)."""
    found, complete = walked(buf)
    for seg in found:
        if seg.marker != 0xE1 or not seg.data.startswith(XMP_NS):
            continue
        return seg.data[len(XMP_NS):].lstrip(b"\x00").decode("utf-8", "replace"), True
    return "", complete


def xmp_packet(path: str) -> str:
    """The XMP text inside a JPEG, or "" - what Lightroom writes into the file.

    Here rather than in whichever module asked first: keywords and locations both
    live in this packet, and two readers walking the same segments is how two
    answers about one file start disagreeing.

    Retries with the bigger read when the first one ran out before the header
    did, as `exif.exif_block` does: a packet past the first quarter megabyte -
    behind a large ICC profile or MPF previews - is still the file's packet,
    and reading it as "none" made every writer build a fresh one over it.
    """
    buf = read_header(path, HEADER_BYTES)
    text, complete = packet_in(buf)
    if not text and not complete and len(buf) >= HEADER_BYTES:
        text, _complete = packet_in(read_header(path, MAX_HEADER_BYTES))
    return text


def packet_to_edit(original: bytes) -> str:
    """The packet a writer edits, from the whole file it already holds.

    Refuses rather than returning "" when the header walk could not finish:
    a writer handed "" builds a new packet, and the splice that follows would
    put it in place of one it never read. Better a tag not written than a crop,
    a develop history and someone else's keywords quietly gone.
    """
    text, complete = packet_in(original)
    if not text and not complete:
        raise ValueError("refusing to write: the file's header segments run on "
                         "past where they could be read, so its XMP packet "
                         "could not be found to edit")
    return text


def scan_start(buf: bytes) -> int:
    """Where the picture data begins, or -1.

    Walks the segments rather than searching for the first 0xFFDA. That search
    looks equivalent and is not: an EXIF thumbnail is itself a JPEG, so its own
    start-of-scan marker sits inside a segment and gets found first. That bug
    made every rewrite look like it had changed the picture.
    """
    if not is_jpeg(buf):
        return -1
    i = 2
    n = len(buf)
    while i + 3 < n:
        if buf[i] != 0xFF:
            return -1
        marker = buf[i + 1]
        if marker in _STANDALONE:
            i += 2
            continue
        if marker == SOS:
            return i
        if marker == EOI:
            return -1
        length = (buf[i + 2] << 8) | buf[i + 3]
        if length < 2 or i + 2 + length > n:
            return -1
        i += 2 + length
    return -1


def picture_unchanged(original: bytes, rewritten: bytes) -> tuple[bool, str]:
    """True when two JPEGs differ only in their headers.

    Not "does it end with FF D9". Plenty of cameras write padding, a second image
    or maker data after the end-of-image marker - Panasonic pads with nulls - and
    demanding a tidy ending refuses perfectly good files. The real question is
    whether anything from the start of the picture data onwards changed.
    """
    if len(rewritten) < 4:
        return False, "result is too short"
    if not is_jpeg(rewritten):
        return False, "result is not a JPEG"
    a = scan_start(original)
    b = scan_start(rewritten)
    if a < 0:
        return False, "the original has no pixel data to compare against"
    if b < 0:
        return False, "no pixel data found in the result"
    if len(original) - a != len(rewritten) - b:
        return False, (f"pixel data changed size "
                       f"({len(original) - a} -> {len(rewritten) - b} bytes)")
    if original[a:] != rewritten[b:]:
        for i, (x, y) in enumerate(zip(original[a:], rewritten[b:])):
            if x != y:
                return False, f"pixel data changed at byte {i}"
        return False, "pixel data changed"
    return True, ""
