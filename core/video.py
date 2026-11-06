"""When a clip was shot, read out of the file itself.

A photograph says `DateTimeOriginal` in a place this app has read since the first
week. A video says nothing so simple, and where it does say something there are
three fields that disagree with each other:

    moov/mvhd                seconds since 1904, defined as UTC
    moov/udta/©day           a dated string WITH the camera's timezone
    moov/meta/ilst           Apple's creationdate, also with a timezone
    a Sony/Panasonic .XML    written beside the clip, exact

**The timezone is the whole problem.** A photograph's capture time is local
wall-clock with no zone at all, and every other feature here compares
wall-clock to wall-clock deliberately. `mvhd` is UTC by the specification and
LOCAL in a great many cameras, and nothing in the file says which one you have.
Three hours of error files an evening clip under the previous day, silently.

So this reads every field, prefers the ones that carry a zone, and reports which
one answered and whether the zone was known - it never quietly shifts a time to
make it fit. What is done with an unzoned time is the caller's decision, made
out loud.

Nothing here decodes a frame. The header atoms are found by SEEKING over the
picture data: `moov` sits at the end of the file in anything not written for
streaming, so reading the first megabyte and giving up - the obvious
implementation - finds nothing in most of the clips a camera writes.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import shutil
import struct
import subprocess

# QuickTime and MP4 count from 1904, not 1970.
EPOCH_1904 = _dt.datetime(1904, 1, 1)

# A clip's headers are small; a clip is not. Never read more than this of moov,
# and never read mdat at all.
MAX_MOOV = 8 * 1024 * 1024
CONTAINERS = {".mp4", ".mov", ".m4v", ".3gp", ".m4a"}

_DATED = re.compile(
    r"(\d{4})[-:]?(\d{2})[-:]?(\d{2})[T ](\d{2}):?(\d{2}):?(\d{2})"
    r"\s*(Z|[+-]\d{2}:?\d{2})?")


class Clip:
    """What a video says about when it was shot, and how sure that is."""

    __slots__ = ("path", "taken", "how", "zone_known", "offset_minutes", "ok")

    def __init__(self, path="", taken=None, how="", zone_known=False,
                 offset_minutes=None):
        self.path = path
        self.taken = taken              # local wall-clock, as far as it is known
        self.how = how                  # which field answered
        self.zone_known = zone_known
        self.offset_minutes = offset_minutes
        self.ok = taken is not None

    def __bool__(self) -> bool:
        return self.taken is not None

    def describe(self) -> str:
        if not self.taken:
            return self.how or "no capture time in the file"
        when = self.taken.strftime("%Y-%m-%d %H:%M")
        if self.zone_known:
            return f"{when} ({self.how})"
        return (f"{when} ({self.how} - no timezone recorded, so this may be UTC "
                f"rather than the time on the clock where you were)")

    def __repr__(self) -> str:                     # pragma: no cover
        return f"Clip({self.describe()!r})"


# ------------------------------------------------------------------- the atoms

def _walk_top(fh, size: int):
    """Yield (name, start of body, length of body) for the top-level atoms.

    By SEEKING, never by reading. `mdat` holds the entire picture and is skipped
    over in one seek - which is the difference between reading eight bytes of a
    four-gigabyte clip and reading four gigabytes of it.
    """
    at = 0
    while at + 8 <= size:
        fh.seek(at)
        head = fh.read(8)
        if len(head) < 8:
            return
        length = struct.unpack(">I", head[:4])[0]
        name = head[4:8].decode("latin-1", "replace")
        body = at + 8
        if length == 1:                       # 64-bit size follows the name
            more = fh.read(8)
            if len(more) < 8:
                return
            length = struct.unpack(">Q", more)[0]
            body = at + 16
        elif length == 0:                     # runs to the end of the file
            length = size - at
        if length < 8 or at + length > size:
            return
        yield name, body, at + length - body
        at += length


def _children(buf: bytes, at: int, end: int):
    """Yield (name, start, end) for the atoms inside a piece of moov."""
    while at + 8 <= end:
        length = struct.unpack_from(">I", buf, at)[0]
        name = buf[at + 4:at + 8].decode("latin-1", "replace")
        body = at + 8
        if length == 1:
            length = struct.unpack_from(">Q", buf, at + 8)[0]
            body = at + 16
        elif length == 0:
            length = end - at
        if length < 8 or at + length > end:
            return
        yield name, body, at + length
        at += length


def _find(buf: bytes, path, at: int = 0, end: int | None = None):
    """The body of a nested atom - _find(moov, ("udta", "\\xa9day"))."""
    end = len(buf) if end is None else end
    want = path[0]
    for name, start, stop in _children(buf, at, end):
        if name != want:
            continue
        if len(path) == 1:
            return start, stop
        inner = start
        if name == "meta":
            # An MP4 `meta` carries a version and flags word before its
            # children; a QuickTime one does not, and the same four bytes are
            # then the length of the first child. Told apart by looking, because
            # both shapes turn up in files from the same camera.
            if buf[start + 4:start + 8] not in (b"hdlr", b"keys", b"ilst"):
                inner = start + 4
        found = _find(buf, path[1:], inner, stop)
        if found:
            return found
    return None


def read_moov(path: str) -> bytes:
    """The header atom of a clip, however big the clip is. b"" when there is none."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            for name, body, length in _walk_top(fh, size):
                if name != "moov":
                    continue
                fh.seek(body)
                return fh.read(min(length, MAX_MOOV))
    except (OSError, struct.error):
        return b""
    return b""


# ------------------------------------------------------------------ the fields

def _text_of(buf: bytes, start: int, end: int) -> str:
    """A QuickTime text atom: two bytes of length, two of language, then text."""
    body = buf[start:end]
    if len(body) >= 4:
        said = struct.unpack_from(">H", body, 0)[0]
        if 0 < said <= len(body) - 4:
            return body[4:4 + said].decode("utf-8", "replace")
    return body.decode("utf-8", "replace").strip("\x00")


def parse_dated(text: str):
    """A dated string, and the offset it carried. (datetime, minutes or None)."""
    m = _DATED.search(text or "")
    if not m:
        return None, None
    y, mo, d, h, mi, s = (int(x) for x in m.groups()[:6])
    try:
        when = _dt.datetime(y, mo, d, h, mi, s)
    except ValueError:
        return None, None
    zone = m.group(7)
    if not zone:
        return when, None
    if zone.upper() == "Z":
        return when, 0
    sign = -1 if zone[0] == "-" else 1
    bits = zone[1:].replace(":", "")
    return when, sign * (int(bits[:2]) * 60 + int(bits[2:4]))


def from_mvhd(moov: bytes):
    """The creation time in the movie header. UTC by the book, local in the wild."""
    found = _find(moov, ("mvhd",))
    if not found:
        return None
    start, end = found
    if end - start < 20:
        return None
    version = moov[start]
    try:
        if version == 1:
            seconds = struct.unpack_from(">Q", moov, start + 4)[0]
        else:
            seconds = struct.unpack_from(">I", moov, start + 4)[0]
    except struct.error:
        return None
    if not seconds:
        return None
    try:
        when = EPOCH_1904 + _dt.timedelta(seconds=seconds)
    except OverflowError:
        return None
    # A camera with a flat battery writes 1904, and a few write 1970. Neither is
    # a capture time, and filing a shoot under 1904 is worse than not filing it.
    if when.year < 1990 or when.year > 2100:
        return None
    return when


def from_udta(moov: bytes):
    """`©day`, which carries the camera's own timezone when it is there."""
    for name in ("\xa9day", "\xa9dat", "date"):
        found = _find(moov, ("udta", name))
        if found:
            when, offset = parse_dated(_text_of(moov, *found))
            if when:
                return when, offset
    return None, None


def from_apple(moov: bytes):
    """`com.apple.quicktime.creationdate` - iPhones and GoPros, with an offset.

    Stored the awkward way: `keys` lists the names, `ilst` holds the values under
    numbers that index into that list. Worth following, because when it is there
    it is the one field that states the time on the clock where you were.
    """
    # `meta` sits directly under moov in some files and under `udta` in others -
    # both shapes come out of the same phone depending on how the clip was
    # written, and looking in only one place finds nothing in half of them.
    keys = ilst = None
    for where in (("meta",), ("udta", "meta")):
        keys = _find(moov, where + ("keys",))
        ilst = _find(moov, where + ("ilst",))
        if keys and ilst:
            break
    if not keys or not ilst:
        return None, None
    names = []
    start, end = keys
    at = start + 8                       # version/flags, then the count
    while at + 8 <= end:
        length = struct.unpack_from(">I", moov, at)[0]
        if length < 8 or at + length > end:
            break
        names.append(moov[at + 8:at + length].decode("utf-8", "replace"))
        at += length
    for name, body, stop in _children(moov, ilst[0], ilst[1]):
        try:
            index = struct.unpack(">I", name.encode("latin-1"))[0]
        except (struct.error, UnicodeEncodeError):
            continue
        if not 1 <= index <= len(names):
            continue
        if "creationdate" not in names[index - 1].lower():
            continue
        for inner, at, to in _children(moov, body, stop):
            if inner != "data":
                continue
            when, offset = parse_dated(
                moov[at + 8:to].decode("utf-8", "replace"))
            if when:
                return when, offset
    return None, None


def from_sidecar(path: str):
    """A Sony or Panasonic .XML written beside the clip. Exact, when it is there."""
    stem = os.path.splitext(path)[0]
    for ext in (".XML", ".xml"):
        beside = stem + ext
        if not os.path.isfile(beside):
            continue
        try:
            with open(beside, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read(20000)
        except OSError:
            continue
        m = re.search(r'CreationDate[^>]*value\s*=\s*"([^"]+)"', text, re.I)
        if m:
            when, offset = parse_dated(m.group(1))
            if when:
                return when, offset
    return None, None


def capture_of(path: str) -> Clip:
    """When this clip was shot, from whichever field actually says so.

    In order of how much they can be trusted, which is exactly the order of how
    much they say about the timezone. A field that states the offset is worth
    more than one that leaves you guessing by three hours.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in CONTAINERS:
        # AVCHD (.MTS) keeps its date inside the transport stream rather than in
        # a header atom, and is not read yet. Saying so is better than reporting
        # "no capture time", which would read as a fact about the clip.
        return Clip(path, how=f"{ext or 'that kind of file'} is not a container "
                              f"this can read a time out of yet")

    when, offset = from_sidecar(path)
    if when:
        return Clip(path, when, "from the .XML beside it", True, offset)

    moov = read_moov(path)
    if not moov:
        return Clip(path, how="no header atom in the file - it may be truncated")

    when, offset = from_apple(moov)
    if when:
        return Clip(path, when, "the camera's own creation date", offset is not None,
                    offset)
    when, offset = from_udta(moov)
    if when:
        return Clip(path, when, "the date written in the file", offset is not None,
                    offset)
    when = from_mvhd(moov)
    if when:
        return Clip(path, when, "the video header", False, None)
    return Clip(path, how="nothing in the header says when it was shot")


def from_ffprobe(path: str):
    """(when, offset) from ffprobe's reading of the container, or (None, None).

    Only a fallback, for the containers `capture_of` cannot read itself (AVCHD's
    .MTS, a .MKV) and only when ffprobe is installed: it is optional, and a
    missing one must cost nothing but this answer. Quietly, with a short
    timeout, because a stuck probe would otherwise stall an index pass.
    """
    probe = shutil.which("ffprobe")
    if not probe:
        return None, None
    try:
        out = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format_tags=creation_time",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None, None
    for line in (out.stdout or "").splitlines():
        when, offset = parse_dated(line.strip())
        if when:
            return when, offset
    return None, None


def taken_of(path: str) -> Clip:
    """When a clip was shot, as the index asks it: always with an answer.

    The header atoms first, the way Separate video reads them; then ffprobe when
    it is installed; then the file's own modification time. The last is a guess,
    and `how` says so, but a clip with no time at all sorts to the end of every
    list and counts as "undated" on Home, which is a worse wrong answer than the
    day the card was copied.
    """
    shot = capture_of(path)
    if shot.taken:
        return shot
    when, offset = from_ffprobe(path)
    if when:
        return Clip(path, when, "ffprobe's reading of the file",
                    offset is not None, offset)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return shot
    return Clip(path, _dt.datetime.fromtimestamp(mtime).replace(microsecond=0),
                "the file's own time - nothing inside it says")


def local_time(clip: Clip, shift_minutes: int = 0):
    """The wall-clock time to compare against a photograph's, or None.

    A photograph's capture time is local wall-clock with no zone; every other
    feature here compares wall-clock to wall-clock on purpose. A clip that
    states its offset is already telling you the local time. One that does not
    is reported as it stands, and the shift is there for the case where you know
    what the camera was doing and the file does not.
    """
    if not clip or not clip.taken:
        return None
    return clip.taken + _dt.timedelta(minutes=shift_minutes)
