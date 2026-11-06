"""Small pictures of photographs, for looking rather than for keeping.

**Synology's own first.** Synology Photos has already made thumbnails of
everything it indexed, in `@eaDir/<file>/SYNOPHOTO_THUMB_*.jpg` beside it, for
RAWs and videos too. Using those costs one file read and no decoding at all.

**Then made here, and kept.** A JPEG is decoded at a fraction of its size (the
decoder's `draft`), turned upright, and shrunk. A RAW has no picture Pillow can
read, but every RAW carries a finished JPEG inside it for the camera's screen -
the largest of those is used. A HEIC is decoded by libheif when a HEIC decoder
is installed (`core/heif.py`), and otherwise has only Synology's thumbnail.
Each result is kept in the config folder, named by the file's path, size and
date, so a changed photo gets a new one and a second look costs nothing. The
folder is trimmed to the newest few thousand.

Never more made at once than the machine has cores, and never more than four:
a NAS asked for eighty thumbnails by one scroll of a table should not stop doing
everything else, and a two-core NAS and an eight-core PC are not the same
amount of room. Making one is decoding, which is one core's work.

**And the newest made before anybody asks.** After the index finds new
photographs, the newest few hundred are made in the background (`warm`), so
opening Photos after an import shows pictures rather than grey squares filling
in one by one.
"""

from __future__ import annotations

import hashlib
import io
import os
import threading

from . import heif
from .store import store_path

SIZES = {"s": 240, "m": 640, "l": 1280}
# Synology's names, smallest that is still big enough FIRST - and then the
# smaller ones anyway.
#
# A video is the case that matters. Nothing here can decode one, so Synology's
# own thumbnail is the only picture of a clip there will ever be - and Synology
# does not always make the XL. Asking only for XL meant the Photos grid (which
# asks for "s", and so tried M as well) showed a clip's frame while the Albums
# screen (which asks for "m") showed an empty card for the very same file.
#
# A slightly soft picture of the right clip beats no picture at all.
SYNO = {"s": ("SYNOPHOTO_THUMB_M.jpg", "SYNOPHOTO_THUMB_XL.jpg"),
        "m": ("SYNOPHOTO_THUMB_XL.jpg", "SYNOPHOTO_THUMB_M.jpg"),
        "l": ("SYNOPHOTO_THUMB_XL.jpg", "SYNOPHOTO_THUMB_M.jpg")}
FOLDER = "thumbs"
# The floor, when the settings cannot be read at all. The real ceiling is
# `thumb_keep` in Setup - see the note beside it.
KEEP = 6000


def keeping() -> int:
    from . import settings as S
    try:
        return max(500, int(S.load()["thumb_keep"] or KEEP))
    except Exception:                                      # noqa: BLE001
        return KEEP
PICTURES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic", ".heif",
            ".gif", ".bmp"}
RAWS = {".rw2", ".arw", ".dng", ".cr2", ".cr3", ".nef", ".orf", ".raf"}
VIDEOS = {".mp4", ".mov", ".mts", ".m4v", ".avi", ".webm", ".mkv", ".m2ts",
          ".3gp", ".wmv", ".mpg", ".mpeg"}

# How many are made at once - see the note at the top.
GATE_WIDTH = max(1, min(4, os.cpu_count() or 1))
_GATE = threading.Semaphore(GATE_WIDTH)
_made = 0


def can_show(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in PICTURES or ext in RAWS or ext in VIDEOS


def _synology(path: str, size: str) -> bytes | None:
    folder, name = os.path.split(path)
    for thumb in SYNO.get(size, ()):
        where = os.path.join(folder, "@eaDir", name, thumb)
        try:
            with open(where, "rb") as fh:
                return fh.read()
        except OSError:
            continue
    return None


def _key(path: str, size: str) -> str:
    st = os.stat(path)
    raw = f"{os.path.abspath(path)}|{st.st_size}|{st.st_mtime_ns}|{size}"
    return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()


def _inside_raw(path: str):
    """The largest JPEG the camera put inside this RAW, opened. None if none."""
    from PIL import Image
    with open(path, "rb") as fh:
        data = fh.read()
    best, best_area = None, 0
    start, tries = 0, 0
    while tries < 60:
        at = data.find(b"\xff\xd8\xff", start)
        if at < 0:
            break
        start = at + 3
        tries += 1
        try:
            im = Image.open(io.BytesIO(data[at:]))
            area = im.size[0] * im.size[1]
        except Exception:                              # noqa: BLE001
            continue
        if area > best_area:
            best, best_area = at, area
    if best is None:
        return None
    return Image.open(io.BytesIO(data[best:]))


def _make(path: str, size: str) -> bytes | None:
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None
    side = SIZES[size]
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in RAWS:
            im = _inside_raw(path)
            if im is None:
                return None
        elif ext in PICTURES:
            if heif.named(path) and not heif.can_decode():
                return None
            im = Image.open(path)
        else:
            return None
        with im:
            try:
                im.draft("RGB", (side, side))
            except Exception:                          # noqa: BLE001
                pass
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGB")
            im.thumbnail((side, side))
            out = io.BytesIO()
            im.save(out, "JPEG", quality=80 if size == "s" else 85)
            return out.getvalue()
    except Exception:                                  # noqa: BLE001
        return None


def _trim(folder: str) -> None:
    """Thrown away oldest first, and only when there are too many.

    The count is checked before the dates are read: `listdir` is one call and
    `getmtime` is one per file, so a folder of sixty thousand that is not over
    its ceiling must not cost sixty thousand syscalls to find that out.
    """
    keep = keeping()
    try:
        names = os.listdir(folder)
        if len(names) <= keep:
            return
        full = [os.path.join(folder, n) for n in names]
        full.sort(key=lambda p: os.path.getmtime(p))
        for old in full[:len(full) - keep]:
            os.remove(old)
    except OSError:
        pass


def thumb(path: str, size: str = "s") -> bytes | None:
    """A JPEG of this photograph, or None when there is nothing to show."""
    global _made
    size = size if size in SIZES else "s"
    if not os.path.isfile(path) or not can_show(path):
        return None
    got = _synology(path, size)
    if got:
        return got
    try:
        key = _key(path, size)
        folder = store_path(FOLDER)
        kept = os.path.join(folder, key + ".jpg")
        with open(kept, "rb") as fh:
            return fh.read()
    except OSError:
        pass
    with _GATE:
        got = _make(path, size)
    if not got:
        return None
    try:
        os.makedirs(folder, exist_ok=True)
        with open(kept + ".part", "wb") as fh:
            fh.write(got)
        os.replace(kept + ".part", kept)
        _made += 1
        # Every two thousand, not every two hundred: trimming reads the folder,
        # and the folder is now large on purpose.
        if _made % 2000 == 0:
            _trim(folder)
    except (OSError, UnboundLocalError):
        pass
    return got


# ------------------------------------------------------- made before they are asked
#
# One warming thread at a time. A second call while one is running hands it
# the new list instead of starting another, so an import found in two passes
# does not have two threads competing for the same few makes - and the newest
# list wins, because it is the one the grid is about to show.
_WARM_LOCK = threading.Lock()
_WARM_WANT: list = []
_WARM_THREAD: threading.Thread | None = None


def have_pillow() -> bool:
    try:
        import PIL                                         # noqa: F401
        return True
    except ImportError:
        return False


def _warm_one(path: str, size: str) -> None:
    """Make this one's thumbnail unless there already is one."""
    if not os.path.isfile(path) or not can_show(path):
        return
    if _synology(path, size):
        return
    try:
        kept = os.path.join(store_path(FOLDER), _key(path, size) + ".jpg")
        if os.path.isfile(kept):
            return
    except OSError:
        return
    thumb(path, size)


def _warming() -> None:
    global _WARM_THREAD
    while True:
        with _WARM_LOCK:
            if not _WARM_WANT:
                _WARM_THREAD = None
                return
            paths, size = _WARM_WANT.pop()
            _WARM_WANT.clear()
        for path in paths:
            with _WARM_LOCK:
                if _WARM_WANT:
                    break                  # a newer list: that one, from its top
            try:
                _warm_one(path, size)
            except Exception:                              # noqa: BLE001
                continue


def warm(paths, size: str = "s"):
    """Make thumbnails for these, on a daemon thread. Returns the thread.

    Without Pillow there is nothing to make them with, so it is a no-op and
    returns None - the grid then shows what Synology made, as it always has.
    """
    global _WARM_THREAD
    if not have_pillow():
        return None
    size = size if size in SIZES else "s"
    with _WARM_LOCK:
        _WARM_WANT.append((list(paths), size))
        if _WARM_THREAD is not None and _WARM_THREAD.is_alive():
            return _WARM_THREAD
        _WARM_THREAD = threading.Thread(target=_warming, daemon=True,
                                        name="thumbs-warm")
        _WARM_THREAD.start()
        return _WARM_THREAD
