"""What a photo says about itself: when it was taken, how, and where."""

from __future__ import annotations

import datetime as _dt
import os
from dataclasses import dataclass, field

from . import exif as E
from . import sidecar as _sc

JPEG_EXTS = {".jpg", ".jpeg", ".jpe"}
OTHER_IMAGE_EXTS = {".heic", ".heif", ".png", ".tif", ".tiff", ".webp"}
RAW_EXTS = {".arw", ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".raf", ".orf",
            ".rw2", ".dng", ".pef", ".srw", ".sr2", ".srf", ".erf", ".mrw",
            ".kdc", ".dcr", ".x3f", ".3fr"}
SIDECAR_EXTS = {".xmp"}

# Video, which every camera in the house also shoots. Named here rather than
# left in "other" because a file this app cannot name is a file it cannot count,
# and a folder of forty clips reporting "0 photographs" is not a state anybody
# can act on.
#
# `.lrv` and `.thm` are the low-resolution proxy and thumbnail that GoPro and
# some Panasonic bodies write beside a clip. They are not video you would watch -
# they travel WITH their clip, the way a sidecar travels with a photograph.
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mts", ".m2ts", ".avi", ".mkv", ".mpg",
              ".mpeg", ".3gp", ".webm", ".insv", ".wmv"}
VIDEO_COMPANION_EXTS = {".lrv", ".thm", ".srt", ".xml"}


def kind(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in JPEG_EXTS:
        return "jpeg"
    if ext in OTHER_IMAGE_EXTS:
        return "image"
    if ext in RAW_EXTS:
        return "raw"
    if ext in SIDECAR_EXTS:
        return "sidecar"
    if ext in VIDEO_EXTS:
        return "video"
    return "other"


def is_picture(path: str) -> bool:
    return kind(path) in ("jpeg", "image")


def is_video(path: str) -> bool:
    return kind(path) == "video"


@dataclass
class Capture:
    """How a frame was exposed. Enough to tell a bracket from a burst."""
    path: str
    ok: bool = False
    taken: _dt.datetime | None = None
    ev: float | None = None
    exposure_mode: int | None = None
    exposure: float | None = None
    fnumber: float | None = None
    iso: int | None = None
    focal_length: float | None = None
    model: str | None = None
    offset_minutes: int | None = None
    # The lens and the full-frame focal length: what "shot on the 25mm" and
    # "anything wide" actually mean. The second matters on this library in
    # particular - a GH4 doubles every focal length, so 25mm on it frames like
    # 50mm on the A7C, and a rule about "normal" lenses written in the numbers
    # on the barrel would treat the two as different.
    lens: str | None = None
    focal35: float | None = None


@dataclass
class Location:
    """Where a photo says it was taken."""
    path: str
    has_gps: bool = False
    lat: float | None = None
    lon: float | None = None
    altitude: float | None = None
    utc: _dt.datetime | None = None          # from the satellites, so trustworthy
    taken: _dt.datetime | None = None        # the camera clock, so only as good as it
    offset_minutes: int | None = None
    model: str | None = None


def _first(v):
    return v[0] if isinstance(v, list) and v else v


def read_capture(path: str) -> Capture:
    t = E.exif_block(path)
    if t is None:
        # No readable EXIF - a RAW, in practice. It may still have a corrected
        # capture time in a sidecar, and that is the only thing keeping a retimed
        # RAW paired with its retimed JPEG.
        return Capture(path=path, taken=_sc.read_datetime(path))
    head = t.directory(t.first_ifd(), {E.T_MODEL, E.T_DATETIME, E.T_EXIF_IFD})
    sub = {}
    if E.T_EXIF_IFD in head:
        sub = t.directory(t.base + int(head[E.T_EXIF_IFD]))
    taken = (E.parse_datetime(sub.get(E.T_DATE_ORIGINAL), sub.get(E.T_SUBSEC_ORIGINAL))
             or E.parse_datetime(head.get(E.T_DATETIME)))
    # For anything that is not a JPEG, a sidecar time WINS over the embedded one.
    #
    # We write a sidecar precisely because we will not open that file - a RAW is
    # the negative. So when both exist, the sidecar is the corrected value and the
    # embedded one is the wrong clock we could not reach. Preferring the embedded
    # one would mean a clock correction appeared to work and then silently did
    # not, which is the same rule ratings already follow.
    if kind(path) != "jpeg":
        corrected = _sc.read_datetime(path)
        if corrected is not None:
            taken = corrected
    elif taken is None:
        taken = _sc.read_datetime(path)
    return Capture(
        path=path, ok=True, taken=taken,
        ev=_first(sub.get(E.T_EXPOSURE_BIAS)),
        exposure_mode=sub.get(E.T_EXPOSURE_MODE),
        exposure=_first(sub.get(E.T_EXPOSURE)),
        fnumber=_first(sub.get(E.T_FNUMBER)),
        iso=_first(sub.get(E.T_ISO)),
        focal_length=_first(sub.get(E.T_FOCAL_LENGTH)),
        model=head.get(E.T_MODEL),
        offset_minutes=E.parse_offset(sub.get(E.T_OFFSET_ORIGINAL)),
        lens=(str(sub.get(E.T_LENS_MODEL)).strip("\x00 ").strip() or None)
             if sub.get(E.T_LENS_MODEL) else None,
        focal35=_first(sub.get(E.T_FOCAL_35)),
    )


def sane_coordinate(lat: float | None, lon: float | None) -> bool:
    """Somewhere on Earth, and not the null island a broken reading collapses to."""
    if lat is None or lon is None:
        return False
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return False
    return not (abs(lat) < 1e-6 and abs(lon) < 1e-6)


def _coordinate(parts, ref) -> float | None:
    """Degrees, minutes and seconds into one number.

    A camera is free to put the whole value in the degrees slot: 25.4783/0/0 and
    25/28/41.88 are the same place written two ways, and both turn up. Adding all
    three handles either. Reading only the first would give whole degrees - about
    sixty miles of error, and a plausible-looking number.
    """
    if parts is None:
        return None
    if not isinstance(parts, list):
        parts = [parts]
    vals = [float(p) for p in parts[:3] if p is not None]
    if not vals:
        return None
    vals += [0.0] * (3 - len(vals))
    v = vals[0] + vals[1] / 60.0 + vals[2] / 3600.0
    if str(ref or "").strip().upper().startswith(("S", "W")):
        v = -v
    return v


def read_gps(path: str) -> Location:
    t = E.exif_block(path)
    if t is None:
        return Location(path=path)
    head = t.directory(t.first_ifd(), {E.T_MODEL, E.T_DATETIME, E.T_EXIF_IFD, E.T_GPS_IFD})
    sub = {}
    if E.T_EXIF_IFD in head:
        sub = t.directory(t.base + int(head[E.T_EXIF_IFD]),
                          {E.T_DATE_ORIGINAL, E.T_SUBSEC_ORIGINAL, E.T_OFFSET_ORIGINAL})
    taken = (E.parse_datetime(sub.get(E.T_DATE_ORIGINAL), sub.get(E.T_SUBSEC_ORIGINAL))
             or E.parse_datetime(head.get(E.T_DATETIME)))
    loc = Location(path=path, taken=taken, model=head.get(E.T_MODEL),
                   offset_minutes=E.parse_offset(sub.get(E.T_OFFSET_ORIGINAL)))
    if E.T_GPS_IFD not in head:
        return loc

    g = t.directory(t.base + int(head[E.T_GPS_IFD]))
    lat = _coordinate(g.get(E.G_LAT), g.get(E.G_LAT_REF))
    lon = _coordinate(g.get(E.G_LON), g.get(E.G_LON_REF))
    if not sane_coordinate(lat, lon):
        return loc
    loc.has_gps, loc.lat, loc.lon = True, lat, lon

    alt = g.get(E.G_ALT)
    if alt is not None:
        alt = float(_first(alt))
        if g.get(E.G_ALT_REF) == 1:
            alt = -alt
        loc.altitude = alt

    # GPSDateStamp and GPSTimeStamp come from the satellites, so they are UTC and
    # they are right - unlike DateTimeOriginal, which is whatever the clock said.
    d, tm = g.get(E.G_DATE), g.get(E.G_TIME)
    if d and tm and isinstance(tm, list) and len(tm) >= 3:
        m = E.re.match(r"^(\d{4}):(\d{2}):(\d{2})", str(d).strip())
        if m:
            try:
                loc.utc = (_dt.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                        tzinfo=_dt.timezone.utc)
                           + _dt.timedelta(hours=tm[0], minutes=tm[1], seconds=tm[2]))
            except (ValueError, TypeError):
                loc.utc = None
    return loc
