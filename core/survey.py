"""What state each folder of the library is actually in.

**Measured, never remembered.** The obvious way to build this is to log what each
task did and show the log. That is wrong here: you reorganise the library in File
Station, you rename a shoot, you delete something from Windows - and a log of
past actions quietly stops describing the folder it claims to describe. Nothing
tells you it has gone stale, which is the worst property a status display can
have.

So every number here is read from the files as they are now. Move a folder and
the answer moves with it. Undo something by hand and it shows as undone. The
display cannot disagree with the disk, because it has no opinion of its own.

The cost is that it means reading the front of every JPEG, which is slow enough
over SMB to matter. So a folder's answer is cached against a SIGNATURE of that
folder - how many files, the newest timestamp, the total size. Touch anything in
it and the signature changes and it is read again; touch nothing and it is free.
The signature covers only the folder's own files, not its children, so editing
one shoot does not invalidate the whole library.
"""

from __future__ import annotations

import json
import os
import zlib
from dataclasses import dataclass, field, asdict

from . import exif as E
from . import heif
from .paths import CULLED, mirror, relative_under, skip_folder
from .photo import is_picture, kind

# 5: a JPEG rated only in its own XMP packet, as Lightroom rates, counts as
# rated - a folder surveyed before said it was not.
VERSION = 5          # bump to throw away every cached answer


@dataclass
class FolderState:
    """One folder of the library, and what has been done to it."""
    path: str = ""
    name: str = ""
    rel: str = ""
    depth: int = 0

    photos: int = 0              # JPEGs and other pictures living here
    rated: int = 0
    located: int = 0             # carrying real GPS
    dated: int = 0               # carrying a capture time
    unreadable: int = 0

    raws_here: int = 0           # RAWs still mixed in with the library
    raws_apart: int = 0          # RAWs in the matching folder of the RAW tree
    videos_here: int = 0         # clips still mixed in with the photographs
    videos_apart: int = 0        # clips in the matching folder of the video tree

    # The stretch of time this folder's photographs cover, as ISO text - text so
    # that the cache stays plain JSON, and ISO so that comparing them is
    # comparing strings. This is what lets a clip be filed with the photographs
    # it was taken among rather than with whatever folder it was dumped in.
    first_taken: str = ""
    last_taken: str = ""
    previews: int = 0            # previews in the matching folder
    culled: int = 0              # things put aside from this folder

    # What the folder WEIGHS, tree by tree. Read from the same scandir that
    # counts the files, so it costs nothing on top - and it is what lets one
    # read answer both "have I finished with this shoot" and "where has the
    # disk gone", rather than walking the whole library twice for two tabs.
    bytes: int = 0               # the photographs and everything else here
    raw_bytes: int = 0           # the matching folder of the RAW tree
    preview_bytes: int = 0
    video_bytes: int = 0
    culled_bytes: int = 0

    children: list = field(default_factory=list)

    # ---------------------------------------------------------------- rolled up

    def totals(self, everything: dict) -> "FolderState":
        """This folder plus everything beneath it, as one."""
        out = FolderState(path=self.path, name=self.name, rel=self.rel,
                          depth=self.depth)
        stack = [self.path]
        while stack:
            here = everything.get(stack.pop())
            if here is None:
                continue
            for field_name in ("photos", "rated", "located", "dated",
                               "unreadable", "raws_here", "raws_apart",
                               "videos_here", "videos_apart", "previews",
                               "culled", "bytes", "raw_bytes", "preview_bytes",
                               "video_bytes", "culled_bytes"):
                setattr(out, field_name,
                        getattr(out, field_name) + getattr(here, field_name))
            # Times are a span, not a sum: the earliest of the earliests and the
            # latest of the latests. Added rather than replaced, or a folder
            # whose own photographs are undated would report its children's
            # dates as nothing.
            if here.first_taken:
                out.first_taken = (min(out.first_taken, here.first_taken)
                                   if out.first_taken else here.first_taken)
            if here.last_taken:
                out.last_taken = max(out.last_taken, here.last_taken)
            stack.extend(here.children)
        return out

    # ------------------------------------------------------------------- states
    #
    # Three answers only - none, some, all - because that is what an icon can
    # honestly say. "Some" is the interesting one: a half-geotagged shoot is a
    # job you left unfinished, and it should not look the same as a finished one.

    def _state(self, done: int) -> str:
        if not self.photos:
            return "empty"
        if done <= 0:
            return "none"
        return "all" if done >= self.photos else "some"

    def separated(self) -> str:
        if not self.raws_here and not self.raws_apart:
            return "empty"
        return "all" if not self.raws_here else ("some" if self.raws_apart else "none")

    def video_separated(self) -> str:
        """Same three answers as the RAWs, for the same reason.

        A folder with no video at all says nothing rather than "done": a mark
        that reads as finished on every folder in the library is a mark nobody
        looks at.
        """
        if not self.videos_here and not self.videos_apart:
            return "empty"
        return ("all" if not self.videos_here
                else ("some" if self.videos_apart else "none"))

    def readable(self) -> str:
        """Files that could not be read at all - a permission, a truncated copy.

        Its own mark because it is the one thing here that is not work you have
        left undone: every other column says "not finished yet", and this one
        says "this folder is not being read properly", which is a different
        sentence and needs a different answer.
        """
        if not self.photos:
            return "empty"
        if not self.unreadable:
            return "all"
        return "none" if self.unreadable >= self.photos else "some"

    def marks(self) -> dict:
        return {
            "separated": self.separated(),
            "video": self.video_separated(),
            "located": self._state(self.located),
            "rated": self._state(self.rated),
            "dated": self._state(self.dated),
            "previews": self._state(self.previews),
            "culled": "some" if self.culled else "empty",
            "readable": self.readable(),
        }

    def weight(self) -> int:
        """Everything this folder costs, across every tree it reaches into."""
        return (self.bytes + self.raw_bytes + self.preview_bytes
                + self.video_bytes + self.culled_bytes)


# --------------------------------------------------------------------- reading

def _read_one(path: str) -> tuple[bool, bool, bool, str]:
    """(readable, rated, located, when) from ONE pass over the EXIF.

    Rating, GPS and the capture time separately would mean opening and parsing
    each photo three times, and over SMB the opening is most of the cost. The
    time is read from the same buffer as the rest, which is why the Library can
    say what a folder's photographs span without a second pass over the library.
    """
    try:
        t = E.exif_block(path)
    except Exception:                                  # noqa: BLE001
        return False, False, False, ""
    if t is None:
        return False, False, False, ""
    try:
        head = t.directory(t.first_ifd(),
                           {E.T_RATING, E.T_GPS_IFD, E.T_EXIF_IFD, E.T_DATETIME})
    except Exception:                                  # noqa: BLE001
        return False, False, False, ""

    rating = head.get(E.T_RATING)
    if isinstance(rating, list):
        rating = rating[0] if rating else None
    rated = bool(rating and int(rating) > 0)
    # Lightroom rates in the packet and leaves the Windows tag alone, and the
    # packet is what `rating_of` reads first; this count agrees with it.
    from .exifwrite import packet_rating
    packet = packet_rating(path)
    if packet is not None:
        rated = packet > 0

    located = False
    if E.T_GPS_IFD in head:
        try:
            g = t.directory(t.base + int(head[E.T_GPS_IFD]))
            from .photo import _coordinate, sane_coordinate
            located = sane_coordinate(
                _coordinate(g.get(E.G_LAT), g.get(E.G_LAT_REF)),
                _coordinate(g.get(E.G_LON), g.get(E.G_LON_REF)))
        except Exception:                              # noqa: BLE001
            located = False

    when = ""
    try:
        sub = {}
        if E.T_EXIF_IFD in head:
            sub = t.directory(t.base + int(head[E.T_EXIF_IFD]),
                              {E.T_DATE_ORIGINAL})
        taken = (E.parse_datetime(sub.get(E.T_DATE_ORIGINAL))
                 or E.parse_datetime(head.get(E.T_DATETIME)))
        if taken:
            when = taken.isoformat(timespec="seconds")
    except Exception:                                  # noqa: BLE001
        when = ""
    return True, rated, located, when


def _sidecar_says(path: str) -> tuple[bool, bool]:
    """(rated, located) from a sidecar - the only thing a RAW can have."""
    from .sidecar import read as read_sidecar
    side = read_sidecar(path)
    if not side:
        return False, False
    rating = side.get("xmp:Rating")
    rated = False
    if rating is not None:
        try:
            rated = int(float(str(rating).strip())) > 0
        except (TypeError, ValueError):
            rated = False
    return rated, bool(side.get("exif:GPSLatitude"))


def signature(folder: str) -> str:
    """A cheap fingerprint of a folder's own files. Changes when they do.

    A folder holding a HEIC is marked as well. Before 3.11 those were read as
    having no EXIF, so such a folder's answer is worked out again once - and only
    such a folder's, rather than every folder in the library.
    """
    count = newest = size = files = 0
    heic = ""
    try:
        with os.scandir(folder) as entries:
            for e in entries:
                if e.name.startswith("@eaDir"):
                    continue
                try:
                    if not e.is_file(follow_symlinks=False):
                        continue
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    continue
                count += 1
                size += st.st_size
                newest = max(newest, int(st.st_mtime))
                # Each file's exact time and inode too, summed so the order the
                # folder lists in does not matter. A rating changed in place
                # keeps the size, and its timestamps are restored on purpose,
                # but the rewrite is a new file: only the inode says so. The
                # same reason `facts.signature` has it.
                try:
                    ino = e.inode()
                except OSError:
                    ino = 0
                files = (files + zlib.crc32(
                    f"{e.name}:{st.st_mtime_ns}:{ino}".encode("utf-8",
                                                               "surrogateescape"))
                         ) & 0xFFFFFFFF
                if not heic and heif.named(e.name):
                    heic = "h"
    except OSError:
        return "unreadable"
    return f"{VERSION}{heic}:{count}:{newest}:{size}:{files:08x}"


def _count_in(folder: str, wanted) -> int:
    return _count_and_size(folder, wanted)[0]


def _count_and_size(folder: str, wanted) -> tuple:
    """(how many, how many bytes) of the wanted kinds in one folder.

    The size comes off the stat the count already needed, so asking for both
    costs the same as asking for one - which is the whole reason the Storage
    tab can share the Library's answers instead of walking everything again.
    """
    n = size = 0
    try:
        with os.scandir(folder) as entries:
            for e in entries:
                try:
                    if not e.is_file(follow_symlinks=False):
                        continue
                    if wanted is not None and kind(e.name) not in wanted:
                        continue
                    n += 1
                    size += e.stat(follow_symlinks=False).st_size
                except OSError:
                    continue
    except OSError:
        return 0, 0
    return n, size


def look_at(folder: str, library: str, raw_root: str, previews_root: str,
            video_root: str = "") -> FolderState:
    """One folder, read from disk. The expensive part, and the cached one."""
    rel = relative_under(folder, library)
    state = FolderState(path=folder, name=os.path.basename(folder) or folder,
                        rel=rel, depth=len([p for p in rel.split(os.sep) if p]))
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return state

    for e in entries:
        try:
            if not e.is_file(follow_symlinks=False):
                continue
            state.bytes += e.stat(follow_symlinks=False).st_size
        except OSError:
            continue
        k = kind(e.name)
        if k == "raw":
            state.raws_here += 1
            continue
        if k == "video":
            state.videos_here += 1
            continue
        if not is_picture(e.name):
            continue
        state.photos += 1
        ok, rated, located, when = _read_one(e.path)
        if not ok:
            state.unreadable += 1
        side_rated, side_located = _sidecar_says(e.path)
        state.rated += 1 if (rated or side_rated) else 0
        state.located += 1 if (located or side_located) else 0
        if when:
            state.dated += 1
            state.first_taken = (min(state.first_taken, when)
                                 if state.first_taken else when)
            state.last_taken = max(state.last_taken, when)

    if raw_root:
        state.raws_apart, state.raw_bytes = _count_and_size(
            mirror(folder, library, raw_root), ("raw",))
    if video_root:
        state.videos_apart, state.video_bytes = _count_and_size(
            mirror(folder, library, video_root), ("video",))
    if previews_root:
        state.previews, state.preview_bytes = _count_and_size(
            mirror(folder, library, previews_root), ("jpeg", "image"))
    if rel:
        state.culled, state.culled_bytes = _count_and_size(
            os.path.join(library, CULLED, rel), ("jpeg", "image", "raw"))
    return state


# ----------------------------------------------------------------- the cache

class Cache:
    """Folder answers, kept between runs so the second look is instant."""

    def __init__(self, path: str = ""):
        self.path = path
        self.entries: dict = {}
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    stored = json.load(fh)
                if isinstance(stored, dict):
                    self.entries = stored
            except (OSError, ValueError):
                self.entries = {}

    def get(self, folder: str, sig: str):
        got = self.entries.get(folder)
        if not got or got.get("sig") != sig:
            return None
        data = dict(got.get("state") or {})
        data.pop("children", None)
        try:
            return FolderState(**data)
        except TypeError:
            return None          # the shape changed; read it again

    def put(self, folder: str, sig: str, state: FolderState) -> None:
        data = asdict(state)
        data.pop("children", None)
        self.entries[folder] = {"sig": sig, "state": data}

    def save(self) -> None:
        if not self.path:
            return
        try:
            tmp = self.path + ".part"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.entries, fh)
            os.replace(tmp, self.path)
        except OSError:
            pass


@dataclass
class Survey:
    folders: dict = field(default_factory=dict)
    root: str = ""
    read: int = 0                # folders actually opened this time
    reused: int = 0              # folders answered from the cache
    stranded: list = field(default_factory=list)   # RAW folders the library lost
    stranded_raws: int = 0
    left_out: int = 0                             # folders you asked to skip
    errors: list = field(default_factory=list)

    def order(self) -> list:
        """Every folder, parents before children, each sorted by name."""
        out = []

        def walk(path):
            state = self.folders.get(path)
            if state is None:
                return
            out.append(state)
            for child in sorted(state.children,
                                key=lambda p: os.path.basename(p).lower()):
                walk(child)

        walk(self.root)
        return out


def stranded_raw_folders(library: str, raw_root: str):
    """RAW folders with no matching folder left in the library.

    This is the gap a positional survey would otherwise hide. Rename or move a
    shoot and its RAWs stay where they were: the library folder then honestly has
    no RAWs to say anything about, and the RAW folder is orphaned somewhere the
    tree view never visits. Both halves look quiet, and the only sign that
    anything is wrong is this count.

    Cheap on purpose - folder positions only, no EXIF. Answering "which RAWs are
    these" needs identity pairing, which is what Re-mirror is for.
    """
    out = []
    if not raw_root or not os.path.isdir(raw_root):
        return out
    for here, dirs, _names in os.walk(raw_root):
        dirs[:] = [d for d in dirs if not skip_folder(d)]
        raws = _count_in(here, ("raw",))
        if not raws:
            continue
        rel = relative_under(here, raw_root)
        if not os.path.isdir(os.path.join(library, rel) if rel else library):
            out.append((here, raws))
    return out


def leaving_out(entries):
    """A test for folders to keep out of one survey.

    Two shapes in one box, because both are things people mean by "exclude":
    a NAME (`Archive`) leaves out every folder called that, anywhere; a PATH
    (anything with a separator in it) leaves out that one folder and what is
    under it. Guessing which was meant would be worse than accepting both.

    Separate from the Setup ignore list on purpose: that list is "these are not
    photographs, never scan them"; this is "not interested right now".
    """
    names, paths = set(), []
    for raw in entries or []:
        item = str(raw).strip().strip('"')
        if not item:
            continue
        if "/" in item or "\\" in item:
            paths.append(os.path.normcase(os.path.normpath(item)))
        else:
            names.add(item.lower())

    def left_out(path: str) -> bool:
        if os.path.basename(path).lower() in names:
            return True
        here = os.path.normcase(os.path.normpath(path))
        return any(here == p or here.startswith(p + os.sep) for p in paths)

    return left_out


def survey(library: str, raw_root: str = "", previews_root: str = "",
           cache: Cache | None = None, rescan: bool = False,
           progress=None, leave_out=None, video_root: str = "") -> Survey:
    """Walk the library and describe every folder in it."""
    out = Survey(root=library)
    left_out = leave_out or (lambda path: False)
    cache = cache if cache is not None else Cache()

    folders = []
    for here, dirs, _names in os.walk(
            library, onerror=lambda e: out.errors.append(
                f"{getattr(e, 'filename', library)}: {e.strerror or e}")):
        keep = []
        for d in sorted(dirs):
            if skip_folder(d):
                continue
            if left_out(os.path.join(here, d)):
                out.left_out += 1
                continue
            keep.append(d)
        dirs[:] = keep
        folders.append((here, [os.path.join(here, d) for d in dirs]))

    for i, (here, children) in enumerate(folders, 1):
        if progress:
            progress(i, len(folders), here)
        sig = signature(here)
        state = None if rescan else cache.get(here, sig)
        if state is None:
            state = look_at(here, library, raw_root, previews_root,
                            video_root)
            cache.put(here, sig, state)
            out.read += 1
        else:
            out.reused += 1
        state.children = children
        out.folders[here] = state

    out.stranded = stranded_raw_folders(library, raw_root)
    out.stranded_raws = sum(n for _path, n in out.stranded)

    cache.save()
    return out
