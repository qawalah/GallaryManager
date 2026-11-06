"""Writing metadata into a JPEG without touching the picture.

Two rules govern everything here.

**Append, never insert.** Every offset inside an EXIF block is absolute, counted
from the start of the TIFF header. Insert twelve bytes into the middle of a
directory the obvious way and every value offset after it - the maker note, the
thumbnail, the exposure fields - points twelve bytes wrong. The file still opens.
The corruption is invisible until something tries to read the part that moved.

So a new directory goes on the END, a fresh copy of IFD0 goes after it, and the
only thing altered in place is the four-byte "first directory" offset in the TIFF
header. The old IFD0 is left behind as unreferenced padding, about 200 bytes.
Nothing existing moves, so nothing existing needs renumbering.

**Verify before replacing.** The new file is built in memory, its picture data is
compared byte for byte against the original, and only then does anything reach the
disk - to a temporary file, which then replaces the original. A failure at any
point leaves the photo exactly as it was. That check is not a setting.
"""

from __future__ import annotations

import datetime as _dt
import os
import shutil
import struct

from . import exif as E
from . import jpegseg
from . import perms
from . import sidecar as sc
from .photo import kind, sane_coordinate
from .replace import replace_file

# GPS directory tags
G_VERSION = 0x0000


def _u16(end: str, v: int) -> bytes:
    return struct.pack(end + "H", v)


def _u32(end: str, v: int) -> bytes:
    return struct.pack(end + "I", v)


def _entry(end: str, tag: int, typ: int, count: int,
           inline: bytes | None = None, offset: int | None = None) -> bytes:
    head = _u16(end, tag) + _u16(end, typ) + _u32(end, count)
    if offset is not None:
        return head + _u32(end, offset)
    return head + (inline or b"")[:4].ljust(4, b"\0")


def to_rationals(value: float) -> list[tuple[int, int]]:
    """One coordinate as degrees, minutes and seconds.

    Seconds keep four decimal places - about a centimetre, far finer than needed,
    but it means the number that goes in is the number that comes back out.
    """
    v = abs(float(value))
    deg = int(v)
    minutes_full = (v - deg) * 60.0
    minutes = int(minutes_full)
    seconds = (minutes_full - minutes) * 60.0
    return [(deg, 1), (minutes, 1), (int(round(seconds * 10000)), 10000)]


def gps_directory(lat: float, lon: float, altitude: float | None,
                  end: str, at: int) -> bytes:
    """A complete GPS directory, ready to sit at a known offset in the block.

    Values of four bytes or fewer live inside their entry; latitude and longitude
    are three rationals each - twenty-four bytes - so they follow the entries and
    are referenced by offset counted from the start of the TIFF block, which is
    why the caller must say where this will land.
    """
    has_alt = altitude is not None
    n = 7 if has_alt else 5
    size = 2 + n * 12 + 4
    data_at = at + size

    lat_ref = b"S\0" if lat < 0 else b"N\0"
    lon_ref = b"W\0" if lon < 0 else b"E\0"

    out = _u16(end, n)
    # tags must ascend - readers are entitled to binary-search them
    out += _entry(end, 0x0000, 1, 4, inline=bytes([2, 3, 0, 0]))
    out += _entry(end, 0x0001, 2, 2, inline=lat_ref)
    out += _entry(end, 0x0002, 5, 3, offset=data_at)
    out += _entry(end, 0x0003, 2, 2, inline=lon_ref)
    out += _entry(end, 0x0004, 5, 3, offset=data_at + 24)
    if has_alt:
        below = 1 if float(altitude) < 0 else 0
        out += _entry(end, 0x0005, 1, 1, inline=bytes([below, 0, 0, 0]))
        out += _entry(end, 0x0006, 5, 1, offset=data_at + 48)
    out += _u32(end, 0)                      # no directory after this one

    for num, den in to_rationals(lat):
        out += _u32(end, num) + _u32(end, den)
    for num, den in to_rationals(lon):
        out += _u32(end, num) + _u32(end, den)
    if has_alt:
        out += _u32(end, int(round(abs(float(altitude)) * 100))) + _u32(end, 100)
    return out


def _rebuild_ifd0(tiff: bytes, t: E.Tiff, extra: dict[int, int]) -> bytes:
    """A fresh IFD0: every existing entry, plus pointers to new directories.

    Entries are copied verbatim, so their value offsets still point into the
    original data - which has not moved, because nothing was inserted.
    """
    end = t.end
    ifd0 = t.first_ifd()
    count = t.u16(ifd0)
    entries_at = ifd0 + 2
    next_ifd = t.u32(entries_at + count * 12)

    keep: list[tuple[int, bytes]] = []
    for e in range(count):
        at = entries_at + e * 12
        tag = t.u16(at)
        if tag in extra:                     # ours replaces any existing one
            continue
        keep.append((tag, tiff[at:at + 12]))

    for tag, offset in extra.items():
        keep.append((tag, _entry(end, tag, 4, 1, offset=offset)))
    keep.sort(key=lambda kv: kv[0])

    out = _u16(end, len(keep))
    for _tag, raw in keep:
        out += raw
    return out + _u32(end, next_ifd)


def block_with_gps(tiff: bytes, lat: float, lon: float,
                   altitude: float | None = None) -> bytes:
    """The existing EXIF block with a GPS directory added, by appending only."""
    t = E.Tiff(tiff, 0)
    gps_at = len(tiff)
    gps = gps_directory(lat, lon, altitude, t.end, gps_at)
    new_ifd0_at = gps_at + len(gps)
    out = bytearray(tiff + gps + _rebuild_ifd0(tiff, t, {E.T_GPS_IFD: gps_at}))
    # the single in-place change in the whole operation
    out[4:8] = _u32(t.end, new_ifd0_at)
    return bytes(out)


def block_gps_only(lat: float, lon: float, altitude: float | None = None) -> bytes:
    """A minimal EXIF block, for a JPEG that has none at all."""
    end = "<"
    ifd0_at = 8
    gps_at = ifd0_at + (2 + 12 + 4)
    out = b"II" + _u16(end, 42) + _u32(end, ifd0_at)
    out += _u16(end, 1) + _entry(end, E.T_GPS_IFD, 4, 1, offset=gps_at) + _u32(end, 0)
    return out + gps_directory(lat, lon, altitude, end, gps_at)


def _find_exif_segment(buf: bytes) -> tuple[int, int, int]:
    """(offset of the EXIF APP1, its total length, where to insert if absent)."""
    insert_at = 2
    first = False
    for seg in jpegseg.segments(buf):
        if seg.marker == 0xE1 and seg.data[:4] == b"Exif":
            return seg.offset, len(seg.data) + 4, insert_at
        # a JFIF APP0 has to stay first, so anything new goes after it
        if not first and seg.marker == 0xE0:
            insert_at = seg.offset + len(seg.data) + 4
        first = True
    return -1, 0, insert_at


def _splice(buf: bytes, payload: bytes) -> bytes:
    """Put an EXIF APP1 carrying `payload` into a JPEG, replacing any existing one."""
    at, length, insert_at = _find_exif_segment(buf)
    body = b"Exif\0\0" + payload
    if len(body) + 2 > 65535:
        raise ValueError(
            f"the EXIF block would not fit in one segment ({len(body) + 2} bytes). "
            f"This photo's metadata is unusually large - a sidecar is the way to "
            f"give it a location.")
    head = struct.pack(">BBH", 0xFF, 0xE1, len(body) + 2)
    if at >= 0:
        return buf[:at] + head + body + buf[at + length:]
    return buf[:insert_at] + head + body + buf[insert_at:]


def write_gps(path: str, lat: float, lon: float, altitude: float | None = None,
              backup_folder: str = "") -> bool:
    """Write a location into a JPEG, or refuse and leave it untouched."""
    if not sane_coordinate(lat, lon):
        raise ValueError(f"refusing to write an impossible position ({lat}, {lon})")

    acl = perms.xattrs_of(path)
    with open(path, "rb") as fh:
        original = fh.read()
    if not jpegseg.is_jpeg(original):
        raise ValueError(f"not a JPEG: {path}")

    at, length, _ = _find_exif_segment(original)
    if at >= 0:
        tiff = original[at + 4 + 6:at + length]
        payload = block_with_gps(tiff, lat, lon, altitude)
    else:
        payload = block_gps_only(lat, lon, altitude)

    rewritten = _splice(original, payload)

    ok, why = jpegseg.picture_unchanged(original, rewritten)
    if not ok:
        raise ValueError(f"refusing to write: {why}")

    if backup_folder:
        # Through perms, not os.makedirs: a folder made the plain way inherits
        # no access list at all, which is how a _BeforeRetime folder ends up
        # invisible to Synology Drive.
        perms.make_folder(backup_folder)
        os.makedirs(backup_folder, exist_ok=True)
        dest = os.path.join(backup_folder, os.path.basename(path))
        n = 1
        stem, ext = os.path.splitext(os.path.basename(path))
        while os.path.exists(dest):
            dest = os.path.join(backup_folder, f"{stem}_{n}{ext}")
            n += 1
        shutil.copy2(path, dest)
        perms.like(dest, path)

    stamp = os.stat(path)
    tmp = path + ".gpstmp"
    with open(tmp, "wb") as fh:
        fh.write(rewritten)
    replace_file(tmp, path)
    # the photo was taken when it was taken; adding a location is not a new version
    # In NANOSECONDS, not seconds. "Put the date back" has to actually put it
    # back: a float pair keeps the second and quietly loses everything below it,
    # and the automation watch compares dates at the resolution the filesystem
    # records them. A rating rewritten in place would otherwise look like a
    # change to every tree this app writes into.
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    # And the OWNER and the mode, for the same reason and in the same breath.
    # `os.replace` puts a NEW file there: written by this app, owned by this
    # app. A library quietly re-owned to root is one Synology Drive - which
    # reads it as you - stops syncing, without either of them saying a word.
    perms.restore(path, stamp, acl)
    return True


def block_without_gps(tiff: bytes) -> bytes | None:
    """The same EXIF block with its location gone. None when it had none.

    Two things happen, and both are needed.

    **IFD0 stops pointing at the GPS directory**, the same append-only way a GPS
    directory is added: a fresh copy of IFD0 without that one entry goes on the
    end, and the four-byte offset in the header is the only thing changed in
    place. Nothing that exists moves, so no other offset needs renumbering.

    **The GPS directory itself is zeroed**, entries and values both. Leaving it
    as unreferenced bytes would satisfy every photo program - none of them would
    find it - and it would still be sitting in the file for anything that goes
    looking. When the reason for stripping a location is that it is WRONG, a
    wrong location recoverable by a hex editor is still a wrong location on
    disk. The picture data is not touched and is checked afterwards, as always.
    """
    t = E.Tiff(tiff, 0)
    ifd0 = t.first_ifd()
    count = t.u16(ifd0)
    gps_at = None
    for e in range(count):
        at = ifd0 + 2 + e * 12
        if t.u16(at) == E.T_GPS_IFD:
            gps_at = t.u32(at + 8)
            break
    if gps_at is None:
        return None

    out = bytearray(tiff)
    # Zero every value the GPS directory points at, then the directory itself.
    try:
        n = t.u16(gps_at)
        if 0 < n < 200 and gps_at + 2 + n * 12 + 4 <= len(tiff):
            for e in range(n):
                at = gps_at + 2 + e * 12
                typ, cnt = t.u16(at + 2), t.u32(at + 4)
                spec = E._TYPES.get(typ)
                if spec and 0 < cnt < 100_000:
                    size = spec[1] * cnt
                    if size > 4:
                        where = t.u32(at + 8)
                        if 0 <= where and where + size <= len(out):
                            out[where:where + size] = bytes(size)
            end = gps_at + 2 + n * 12 + 4
            out[gps_at:end] = bytes(end - gps_at)
    except (struct.error, IndexError):
        pass

    # A fresh IFD0 without the pointer, on the end.
    end = t.end
    entries_at = ifd0 + 2
    next_ifd = t.u32(entries_at + count * 12)
    keep = []
    for e in range(count):
        at = entries_at + e * 12
        if t.u16(at) != E.T_GPS_IFD:
            keep.append(bytes(tiff[at:at + 12]))
    fresh = _u16(end, len(keep)) + b"".join(keep) + _u32(end, next_ifd)
    new_at = len(out)
    out += fresh
    out[4:8] = _u32(end, new_at)
    return bytes(out)


def strip_gps(path: str) -> bool:
    """Take the location out of a JPEG. True when it had one and it is gone.

    The same safety as every other write here: built in memory, the picture
    compared byte for byte, written beside and swapped in, the date, owner and
    mode put back. A JPEG with no location is not rewritten at all.
    """
    acl = perms.xattrs_of(path)
    with open(path, "rb") as fh:
        original = fh.read()
    if not jpegseg.is_jpeg(original):
        raise ValueError(f"not a JPEG: {path}")
    at, length, _ = _find_exif_segment(original)
    if at < 0:
        return False
    tiff = original[at + 4 + 6:at + length]
    payload = block_without_gps(tiff)
    if payload is None:
        return False
    rewritten = _splice(original, payload)
    ok, why = jpegseg.picture_unchanged(original, rewritten)
    if not ok:
        raise ValueError(f"refusing to write: {why}")
    stamp = os.stat(path)
    tmp = path + ".gpstmp"
    with open(tmp, "wb") as fh:
        fh.write(rewritten)
    replace_file(tmp, path)
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    perms.restore(path, stamp, acl)
    return True


# --------------------------------------------------------------------- ratings

def write_rating(path: str, stars: int) -> bool:
    """The star rating, in IFD0 where Windows Explorer looks for it.

    Zero means UNRATED, not zero stars - a distinction the Windows version got
    wrong once and which made every unrated photo look deliberately rejected.
    """
    if not 0 <= int(stars) <= 5:
        raise ValueError("a rating is 0 to 5 stars")
    acl = perms.xattrs_of(path)
    with open(path, "rb") as fh:
        original = fh.read()
    if not jpegseg.is_jpeg(original):
        raise ValueError(f"not a JPEG: {path}")

    at, length, _ = _find_exif_segment(original)
    if at < 0:
        raise ValueError("this photo has no EXIF block to put a rating in")

    tiff = original[at + 4 + 6:at + length]
    t = E.Tiff(tiff, 0)
    ifd0 = t.first_ifd()
    count = t.u16(ifd0)
    end = t.end

    # A rating is a SHORT and fits inside its entry, so if one is already there it
    # can be overwritten where it sits - no appending, no offsets to disturb.
    for e in range(count):
        at_entry = ifd0 + 2 + e * 12
        if t.u16(at_entry) == E.T_RATING:
            block = bytearray(tiff)
            block[at_entry + 8:at_entry + 10] = _u16(end, int(stars))
            rewritten = _splice(original, bytes(block))
            break
    else:
        # none there: append a fresh IFD0 carrying one, same trick as GPS
        entries_at = ifd0 + 2
        next_ifd = t.u32(entries_at + count * 12)
        keep = [(t.u16(entries_at + e * 12), tiff[entries_at + e * 12:entries_at + e * 12 + 12])
                for e in range(count)]
        keep.append((E.T_RATING, _entry(end, E.T_RATING, 3, 1,
                                        inline=_u16(end, int(stars)) + b"\0\0")))
        keep.sort(key=lambda kv: kv[0])
        new_ifd0 = _u16(end, len(keep)) + b"".join(r for _t, r in keep) + _u32(end, next_ifd)
        block = bytearray(tiff + new_ifd0)
        block[4:8] = _u32(end, len(tiff))
        rewritten = _splice(original, bytes(block))

    # And the XMP packet, when the photo has one. Lightroom, Bridge, darktable
    # and digiKam read and write xmp:Rating there, not the Windows tag: change
    # one and not the other and Lightroom goes on showing the old stars.
    packet = jpegseg.packet_to_edit(rewritten)
    if packet.strip():
        from . import tagwrite
        body = sc.merge(packet, {"xmp:Rating": str(int(stars))}).encode("utf-8")
        rewritten = tagwrite._replace_segment(
            rewritten, 0xE1, jpegseg.XMP_NS + b"\x00" + body,
            lambda d: d.startswith(jpegseg.XMP_NS))

    ok, why = jpegseg.picture_unchanged(original, rewritten)
    if not ok:
        raise ValueError(f"refusing to write: {why}")

    stamp = os.stat(path)
    tmp = path + ".rattmp"
    with open(tmp, "wb") as fh:
        fh.write(rewritten)
    replace_file(tmp, path)
    # In NANOSECONDS, not seconds. "Put the date back" has to actually put it
    # back: a float pair keeps the second and quietly loses everything below it,
    # and the automation watch compares dates at the resolution the filesystem
    # records them. A rating rewritten in place would otherwise look like a
    # change to every tree this app writes into.
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    # And the OWNER and the mode, for the same reason and in the same breath.
    # `os.replace` puts a NEW file there: written by this app, owned by this
    # app. A library quietly re-owned to root is one Synology Drive - which
    # reads it as you - stops syncing, without either of them saying a word.
    perms.restore(path, stamp, acl)
    return True


# --------------------------------------------------------------- capture time

"""Correcting a camera clock.

A camera writes the time it believed it was. Get that wrong once - a flat
battery, a flight, a body you never set - and every photo of the trip is filed
under the wrong day, sorts wrongly next to the phone's, and cannot be matched
against a timeline.

An EXIF datetime is always the same nineteen characters plus a terminator:
"2024:05:01 09:00:03". Exactly twenty bytes, always. So a correction is written
straight over the value where it already sits - no appending, no new directory,
no offsets to disturb. The one case that needs more is a photo with no datetime
at all, and there is nothing to correct in that: it is left alone and said so.
"""

DATETIME_TAGS = (
    (E.T_DATE_ORIGINAL, "when the shutter fired"),
    (0x9004, "when it was written to the card"),      # DateTimeDigitized
)


def _stamp(when) -> bytes:
    return when.strftime("%Y:%m:%d %H:%M:%S").encode("ascii") + b"\0"


def _datetime_slots(tiff: bytes, t: E.Tiff) -> list[int]:
    """Where every datetime value sits inside the block, ready to be overwritten.

    IFD0's DateTime and the ExifIFD's DateTimeOriginal and DateTimeDigitized are
    all moved together. Shifting one and not the others leaves a file that
    disagrees with itself, and different programs read different ones.
    """
    slots: list[int] = []

    def scan(ifd: int, tags: set[int]) -> None:
        try:
            count = t.u16(ifd)
        except Exception:                              # noqa: BLE001
            return
        for e in range(count):
            at = ifd + 2 + e * 12
            tag, typ, n = t.u16(at), t.u16(at + 2), t.u32(at + 4)
            if tag not in tags or typ != 2 or n != 20:
                continue
            where = t.u32(at + 8)                      # 20 bytes never fits inline
            if 0 <= where <= len(tiff) - 20:
                slots.append(where)

    head = t.directory(t.first_ifd(), {E.T_EXIF_IFD})
    scan(t.first_ifd(), {E.T_DATETIME})
    if E.T_EXIF_IFD in head:
        # `base`, not a fixed six. A sub-directory pointer counts from the start of
        # the TIFF header, and where that sits inside the buffer depends on how the
        # block was obtained: exif_block keeps the "Exif\0\0" in front of it and so
        # has base 6, while the slice used here starts at the header itself. Adding
        # six to both reads a directory six bytes into the wrong place - which finds
        # nothing, silently, and looks like a photo with no capture time.
        scan(t.base + int(head[E.T_EXIF_IFD]), {E.T_DATE_ORIGINAL, 0x9004})
    return slots


def write_datetime(path: str, when) -> int:
    """Write this capture time into every datetime field the photo has.

    Returns how many fields were written. Zero means the photo carries no
    datetime at all - nothing was changed, and nothing was invented either.
    """
    acl = perms.xattrs_of(path)
    with open(path, "rb") as fh:
        original = fh.read()
    if not jpegseg.is_jpeg(original):
        raise ValueError(f"not a JPEG: {path}")

    at, length, _ = _find_exif_segment(original)
    if at < 0:
        raise ValueError("this photo has no EXIF block")

    tiff = original[at + 4 + 6:at + length]
    t = E.Tiff(tiff, 0)
    slots = _datetime_slots(tiff, t)
    if not slots:
        return 0

    stamp = _stamp(when)
    block = bytearray(tiff)
    for where in slots:
        block[where:where + 20] = stamp
    rewritten = _splice(original, bytes(block))

    ok, why = jpegseg.picture_unchanged(original, rewritten)
    if not ok:
        raise ValueError(f"refusing to write: {why}")

    # Who owns it, before it is replaced by a file this app wrote. Correcting a
    # camera clock is the one write here that SHOULD move the file's own date -
    # the metadata really did change today - but it must not move the owner.
    was = perms.stat_of(path)
    tmp = path + ".dttmp"
    with open(tmp, "wb") as fh:
        fh.write(rewritten)
    replace_file(tmp, path)
    perms.restore(path, was, acl)
    return len(slots)


def read_rating(path: str) -> int | None:
    """The star rating, or None when there is none. Zero means unrated.

    The photo's own XMP packet first, then the Windows tag. Lightroom writes
    only the packet, so a library rated there read as unrated everywhere
    here; and `write_rating` keeps the two in step, so they only disagree when
    another program changed one of them since - which is the packet.
    """
    packet = packet_rating(path)
    if packet is not None:
        return packet if packet > 0 else None
    t = E.exif_block(path)
    if t is None:
        return None
    head = t.directory(t.first_ifd(), {E.T_RATING})
    value = head.get(E.T_RATING)
    if value is None:
        return None
    value = int(value[0] if isinstance(value, list) else value)
    return value if value > 0 else None


def packet_rating(path: str) -> int | None:
    """xmp:Rating from inside a JPEG's own packet, or None when it has none."""
    if kind(path) != "jpeg":
        return None
    raw = sc.values_in(jpegseg.xmp_packet(path)).get("xmp:Rating")
    if raw is None:
        return None
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------- sidecars
#
# The mechanics live in core/sidecar.py, which the READER also uses; these are the
# app-level operations expressed in terms of them.

sidecar_path = sc.sidecar_path
read_sidecar = sc.read
write_sidecar = sc.write
read_datetime_sidecar = sc.read_datetime


def write_gps_sidecar(image_path: str, lat: float, lon: float) -> str:
    """A location in an .xmp beside the photo, touching nothing else."""
    return sc.write(image_path,
                    **{"exif:GPSLatitude": sc.dms_text(lat, "N", "S"),
                       "exif:GPSLongitude": sc.dms_text(lon, "E", "W"),
                       "exif:GPSVersionID": "2.3.0.0"})


def write_rating_sidecar(image_path: str, stars: int) -> str:
    """A rating in an .xmp - the only way to rate a RAW without opening it."""
    if not 0 <= int(stars) <= 5:
        raise ValueError("a rating is 0 to 5 stars")
    return sc.write(image_path, **{"xmp:Rating": str(int(stars))})


def write_datetime_sidecar(image_path: str, when) -> str:
    """A corrected capture time in an .xmp - the only way to retime a RAW."""
    return sc.write(image_path,
                    **{"exif:DateTimeOriginal": when.strftime("%Y-%m-%dT%H:%M:%S")})


def read_rating_sidecar(image_path: str) -> int | None:
    """The rating from a sidecar, or None. Zero means unrated, as everywhere else."""
    raw = sc.read(image_path).get("xmp:Rating")
    if raw is None:
        return None
    try:
        v = int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def rating_of(path: str) -> int | None:
    """The rating of any file: from inside a JPEG, from a sidecar for anything else.

    A sidecar wins over an embedded rating when both are there. It is the one a
    person edited most recently in every tool that writes them, and it is the only
    one a RAW can have at all.
    """
    side = read_rating_sidecar(path)
    if side is not None:
        return side
    try:
        return read_rating(path)
    except Exception:                              # noqa: BLE001
        return None


def set_rating(path: str, stars: int) -> str:
    """Rate anything. Returns "photo" or "sidecar" - which one was written.

    A JPEG is rated in place, where Windows Explorer and Synology Photos look. A
    RAW gets a sidecar: this app never opens a negative for writing, and every
    tool that matters reads the .xmp anyway.
    """
    if kind(path) in ("jpeg",):
        write_rating(path, stars)
        return "photo"
    write_rating_sidecar(path, stars)
    return "sidecar"


def set_datetime(path: str, when) -> str:
    """Correct the capture time of anything. Returns "photo" or "sidecar"."""
    if kind(path) == "jpeg" and write_datetime(path, when):
        return "photo"
    write_datetime_sidecar(path, when)
    return "sidecar"
