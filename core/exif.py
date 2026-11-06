"""Reading EXIF, by hand, without decoding the picture.

A TIFF block is three directories deep for our purposes:

    IFD0            camera, date, star rating, and pointers to the other two
      -> 0x8769     ExifIFD: exposure, aperture, ISO, capture time, timezone
      -> 0x8825     GPS IFD: latitude, longitude, altitude, satellite time

Every offset inside the block is absolute, counted from the start of the TIFF
header - which is why writing has to be done so carefully, and why reading has to
follow pointers rather than assume anything sits where it usually does.
"""

from __future__ import annotations

import datetime as _dt
import re
import struct
from typing import Any

from . import heif, jpegseg

# --- IFD0
T_MAKE            = 0x010F
T_MODEL           = 0x0110
T_DATETIME        = 0x0132
T_RATING          = 0x4746      # the stars Windows Explorer writes
T_EXIF_IFD        = 0x8769
T_GPS_IFD         = 0x8825
# --- ExifIFD
T_EXPOSURE        = 0x829A
T_FNUMBER         = 0x829D
T_ISO             = 0x8827
T_DATE_ORIGINAL   = 0x9003
T_OFFSET_ORIGINAL = 0x9011      # "+03:00" - the timezone, when a camera records one
T_EXPOSURE_BIAS   = 0x9204
T_FOCAL_LENGTH    = 0x920A
T_SUBSEC_ORIGINAL = 0x9291
T_EXPOSURE_MODE   = 0xA402      # 2 means the camera was auto-bracketing
T_FOCAL_35        = 0xA405      # focal length as if on a full-frame body
T_LENS_MODEL      = 0xA434      # the lens, as the camera names it
# --- GPS IFD
G_LAT_REF, G_LAT, G_LON_REF, G_LON = 0x0001, 0x0002, 0x0003, 0x0004
G_ALT_REF, G_ALT, G_TIME, G_DATE = 0x0005, 0x0006, 0x0007, 0x001D

# TIFF value types -> (struct code, size). Rationals are handled separately.
_TYPES = {1: ("B", 1), 2: ("s", 1), 3: ("H", 2), 4: ("I", 4), 5: ("rat", 8),
          6: ("b", 1), 7: ("B", 1), 8: ("h", 2), 9: ("i", 4), 10: ("srat", 8),
          11: ("f", 4), 12: ("d", 8)}


class Tiff:
    """A TIFF block plus the byte order it is written in."""

    def __init__(self, buf: bytes, base: int):
        self.buf = buf
        self.base = base
        bo = buf[base:base + 2]
        if bo == b"II":
            self.end = "<"
        elif bo == b"MM":
            self.end = ">"
        else:
            raise ValueError("no byte order marker")

    def u16(self, off: int) -> int:
        return struct.unpack_from(self.end + "H", self.buf, off)[0]

    def u32(self, off: int) -> int:
        return struct.unpack_from(self.end + "I", self.buf, off)[0]

    def first_ifd(self) -> int:
        return self.base + self.u32(self.base + 4)

    def entry_value(self, entry: int) -> Any:
        """One directory entry, decoded.

        A value of four bytes or fewer lives inside the entry; anything larger is
        an offset from the start of the block. Getting that backwards is the
        classic EXIF bug - a latitude is three rationals, twenty-four bytes, so it
        never fits, and reading it from the entry's own bytes returns noise that
        looks like a plausible coordinate.
        """
        typ = self.u16(entry + 2)
        count = self.u32(entry + 4)
        spec = _TYPES.get(typ)
        if not spec or count <= 0 or count > 100_000:
            return None
        code, unit = spec
        size = unit * count
        at = entry + 8 if size <= 4 else self.base + self.u32(entry + 8)
        if at < 0 or at + size > len(self.buf):
            return None

        if typ == 2:
            return self.buf[at:at + size].split(b"\0", 1)[0].decode("ascii", "replace")
        if code in ("rat", "srat"):
            fmt = self.end + ("ii" if code == "srat" else "II")
            out = []
            for k in range(count):
                num, den = struct.unpack_from(fmt, self.buf, at + k * 8)
                out.append(num / den if den else None)
            return out[0] if count == 1 else out
        vals = list(struct.unpack_from(f"{self.end}{count}{code}", self.buf, at))
        return vals[0] if count == 1 else vals

    def directory(self, ifd: int, wanted: set[int] | None = None) -> dict[int, Any]:
        """Every entry of one directory, as {tag: value}."""
        out: dict[int, Any] = {}
        if ifd <= 0 or ifd + 2 > len(self.buf):
            return out
        try:
            count = self.u16(ifd)
        except struct.error:
            return out
        if count <= 0 or count > 4096:
            return out
        for e in range(count):
            entry = ifd + 2 + e * 12
            if entry + 12 > len(self.buf):
                break
            try:
                tag = self.u16(entry)
            except struct.error:
                break
            if wanted is not None and tag not in wanted:
                continue
            try:
                val = self.entry_value(entry)
            except (struct.error, ValueError, ZeroDivisionError):
                continue
            if val is not None:
                out[tag] = val
        return out


def exif_block(path: str, max_bytes: int = jpegseg.HEADER_BYTES) -> Tiff | None:
    """The TIFF block of a JPEG's EXIF segment, or a HEIC's EXIF item, or None.

    A HEIC keeps the very same TIFF block, only boxed differently - see
    `core/heif.py` - so everything that reads a JPEG's date, camera or GPS reads
    a phone's HEIC through this without knowing which it was given.

    Retries with a bigger read if nothing was found: a camera with an unusually
    large embedded thumbnail can push the block past the small default, and
    reporting a perfectly good file as having no EXIF would be worse than the
    extra read.
    """
    buf = jpegseg.read_header(path, max_bytes)
    if heif.is_heif(buf):
        got = heif.exif_tiff(path, buf)
        if got is None:
            return None
        try:
            return Tiff(got[0], got[1])
        except ValueError:
            return None
    for seg in jpegseg.segments(buf):
        if seg.marker != 0xE1 or len(seg.data) < 14 or seg.data[:4] != b"Exif":
            continue
        try:
            return Tiff(seg.data, 6)
        except ValueError:
            return None
    if max_bytes < jpegseg.MAX_HEADER_BYTES:
        return exif_block(path, jpegseg.MAX_HEADER_BYTES)
    return None


def parse_datetime(text: str | None, subsec: str | None = None) -> _dt.datetime | None:
    """"2022:07:14 18:03:22" - EXIF's own shape, which no date parser accepts."""
    if not text:
        return None
    m = re.match(r"^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", text.strip())
    if not m:
        return None
    try:
        when = _dt.datetime(*(int(g) for g in m.groups()))
    except ValueError:
        return None
    if subsec:
        digits = re.sub(r"\D", "", str(subsec))
        if digits:
            # "07" means 70 ms, not 7 - it is a fraction, so it pads on the right
            when += _dt.timedelta(milliseconds=round(float("0." + digits) * 1000))
    return when


def parse_offset(text: str | None) -> int | None:
    """"+03:00" -> 180. The timezone the camera was set to, when it records one."""
    if not text:
        return None
    m = re.match(r"^([+-])(\d{2}):?(\d{2})$", text.strip())
    if not m:
        return None
    mins = int(m.group(2)) * 60 + int(m.group(3))
    return -mins if m.group(1) == "-" else mins
