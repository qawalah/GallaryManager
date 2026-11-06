"""Every photograph in the library, in memory, ready before you ask.

This is what 3.0 needed that the app did not have.

Until now every screen in here was a QUESTION you pressed a button to ask. That
is the right shape for "move four hundred files" and the wrong shape for "show
me my photographs": opening a photo library and being handed an empty form with
`Have a look` under it is a filing cabinet, not a library. Worse, the answer took
thirty seconds and was thrown away the moment you went to another tab, so you
paid for it again.

So the library is read ONCE, kept, and kept up to date:

- **built in the background**, at startup, while the page is already usable -
  with a count of where it has got to, because a library that is still being
  read should say so rather than looking empty;
- **remembered on disk** (`catalogue.json`), so a restart costs a load and not a
  re-read. The facts themselves still come from `core/facts.py`, which is where
  the "read a photograph once, ever" bargain lives - this is the index on top of
  it, and the two caches are keyed the same way, by a signature of the file;
- **incremental**: a later pass walks the tree (names only, no reads), drops what
  has gone, reads what is new or has changed, and leaves everything else alone.
  A library that has not moved costs one `os.walk`;
- **marked stale by anything that writes.** Every task here moves or rewrites
  photographs; `touch()` is called when one finishes, and the next refresh picks
  the changes up. Nothing in here ever decides it knows better than the disk.

**What it stores is one `find.Hit` per photograph**, the same shape the search
and the charts already speak, which is the whole reason this can be bolted under
them without a second set of rules about what a photograph is. `stats.tally_of`
counts these instead of walking, so the dashboard that used to take thirty
seconds is now instant and says when it was measured.

**It holds no opinions.** No ratings are invented, no folder is judged, nothing
is written to a photograph. It is a list of what is there.
"""

from __future__ import annotations

import json
import os
import threading
import time

from .photo import is_picture, kind
from .store import store_path

VERSION = 2
FILE = "catalogue.json"

# Fields of one entry, in the order they are stored. A list per photograph
# rather than a dict: a hundred thousand dicts of the same seventeen keys is
# most of a gigabyte of Python, and the keys never vary.
FIELDS = ("taken", "kind", "camera", "lens", "focal", "focal35", "fnumber",
          "shutter", "iso", "stars", "colour", "tags", "lat", "lon", "size",
          "when", "sig")
_AT = {name: i for i, name in enumerate(FIELDS)}


def _blank() -> list:
    return ["", "", "", "", None, None, None, "", 0, 0, "", [], None, None,
            0, 0.0, ""]


# How many of the files a pass could not read are named, with why. The count is
# always whole; the names are for finding the first few, not for a report.
UNREADABLE_NAMES = 20


class Catalogue:
    """The library as a list, with the locks that make it safe to read while
    it is being rebuilt.

    One lock, held only around the swap of the whole table and around the small
    bookkeeping - never around reading a photograph, which is the slow part. A
    scan that held the lock while it read would make the page it is feeding
    freeze for as long as it ran, which is the opposite of the point.
    """

    def __init__(self, path: str = ""):
        self.path = path
        self.files: dict = {}              # path -> entry list
        self.roots: list = []
        self.reading = 0
        # How many passes have actually CHANGED something. The page watches this
        # rather than the clock: a pass that read nothing and dropped nothing is
        # not news, and redrawing the screen for it is what made Home flicker.
        self.changes = 0
        self.when = 0.0                    # when the last pass finished
        self.building = False
        self.done = 0
        self.total = 0
        self.now = ""                      # what it is reading, for the bar
        self.stale = True
        # Counts the writes reported to it. A pass compares the count at its
        # start and its end, so a write made WHILE it walked keeps the index
        # stale instead of being cleared by a pass that never saw it.
        self.writes = 0
        self.error = ""
        # Files the last pass found and could not read. Each one is missing from
        # the grid, the counts and the map, and without this nothing says so:
        # a photograph simply is not there, which looks like the app lost it.
        self.unreadable = 0
        self.unreadable_names: list = []   # the first few, {"path", "error"}
        self._lock = threading.Lock()
        self._order: list = []             # (sort key, path), newest first
        self._thread = None
        self._for: list = []               # what the running pass is reading
        # The trees moved and the new ones have not been read through yet, so
        # `roots` names them but `files` holds only what they shared with the
        # old ones. Nothing may trust the index for them until a pass ends.
        self.unread = False
        self._stop = False
        self.last: dict = {}               # what the last background pass said
        if path:
            self.load()

    # --------------------------------------------------------------- on disk

    def load(self) -> bool:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                got = json.load(fh)
        except (OSError, ValueError):
            return False
        if not isinstance(got, dict) or got.get("v") != VERSION:
            return False
        files = got.get("files")
        if not isinstance(files, dict):
            return False
        with self._lock:
            self.files = files
            self.roots = list(got.get("roots") or [])
            self.when = float(got.get("when") or 0)
            self._reorder()
        return True

    def save(self) -> bool:
        if not self.path:
            return False
        with self._lock:
            body = {"v": VERSION, "when": self.when, "roots": list(self.roots),
                    "files": dict(self.files)}
        tmp = self.path + ".part"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(body, fh, separators=(",", ":"))
            os.replace(tmp, self.path)
            return True
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False

    # ------------------------------------------------------------- the order

    def _reorder(self) -> None:
        """Newest first, by when it was TAKEN - and by the file's own date for
        the ones that have no capture time, so a photograph with no EXIF still
        lands somewhere sensible instead of at the bottom for ever."""
        rows = []
        for path, e in self.files.items():
            rows.append((key_of(e), path))
        rows.sort(reverse=True)
        self._order = rows

    # --------------------------------------------------------------- reading

    def state(self) -> dict:
        with self._lock:
            return {"ready": bool(self.files) or (self.when > 0),
                    "building": self.building, "done": self.done,
                    # Files this pass has opened. Zero while it is only
                    # checking, which is most passes on most days.
                    "reading": getattr(self, "reading", 0),
                    "changes": getattr(self, "changes", 0),
                    "total": self.total, "now": self.now,
                    "photos": len(self.files), "when": self.when,
                    "stale": self.stale, "error": self.error,
                    "unreadable": self.unreadable,
                    "unreadable_names": [dict(u) for u in self.unreadable_names],
                    "roots": list(self.roots)}

    def entry(self, path: str):
        return self.files.get(path)

    def rows(self) -> list:
        """(key, path) newest first. A copy, so a rebuild cannot change the
        list somebody is halfway through drawing."""
        with self._lock:
            return list(self._order)

    def hit(self, path: str):
        """One entry as the `find.Hit` the rest of the app speaks."""
        from . import find
        e = self.files.get(path)
        if e is None:
            return None
        h = find.Hit(path=path, name=os.path.basename(path),
                     folder=os.path.dirname(path))
        h.taken = e[_AT["taken"]]
        h.camera = e[_AT["camera"]]
        h.lens = e[_AT["lens"]]
        h.focal = e[_AT["focal"]]
        h.focal35 = e[_AT["focal35"]]
        h.fnumber = e[_AT["fnumber"]]
        h.shutter = e[_AT["shutter"]]
        h.iso = e[_AT["iso"]]
        h.stars = e[_AT["stars"]]
        h.colour = e[_AT["colour"]]
        h.tags = list(e[_AT["tags"]] or [])
        h.located = e[_AT["lat"]] is not None
        h.size = e[_AT["size"]]
        h.when = e[_AT["when"]]
        # `find.matches` reads `seconds` for a shutter search, and a Hit built
        # by `about` always has it. One built here must too, or a search by
        # shutter speed quietly matches nothing.
        h.seconds = _seconds_of(e[_AT["shutter"]])
        # Where it is, for "within so far of this pin". `find.about` does not
        # carry the coordinates - it only ever answered "has one or not" - and
        # a search by distance needs the numbers themselves.
        h.lat, h.lon = e[_AT["lat"]], e[_AT["lon"]]
        return h

    def hits(self, under=()) -> list:
        """Every photograph as a Hit, optionally only under these folders."""
        want = [os.path.normcase(os.path.abspath(str(f)))
                for f in (under or []) if str(f or "").strip()]
        out = []
        for _key, path in self.rows():
            if want:
                low = os.path.normcase(path)
                if not any(low == w or low.startswith(w + os.sep) for w in want):
                    continue
            h = self.hit(path)
            if h is not None:
                out.append(h)
        return out

    def taken_under(self, folder: str) -> list:
        """(path, kind, capture time) for every file under `folder`.

        The two columns Separate video needs to know which shoot a clip was
        taken among, without building a whole `find.Hit` for each of a hundred
        thousand photographs to read two fields off it.
        """
        want = os.path.normcase(os.path.abspath(str(folder)))
        out = []
        for _key, path in self.rows():
            low = os.path.normcase(path)
            if not (low == want or low.startswith(want + os.sep)):
                continue
            e = self.files.get(path)
            if e is not None:
                out.append((path, e[_AT["kind"]], e[_AT["taken"]]))
        return out

    def covers(self, under=()) -> bool:
        """Is this folder inside what the catalogue actually read?

        The question every caller has to ask before trusting it. Pointed at a
        folder outside the library the answer is no, and the caller walks the
        disk as it always did - an index that answered for trees it never read
        would be worse than no index.
        """
        roots = [os.path.normcase(os.path.abspath(r)) for r in self.roots]
        if not roots or self.unread:
            return False
        for folder in (under or []):
            low = os.path.normcase(os.path.abspath(str(folder)))
            if not any(low == r or low.startswith(r + os.sep) for r in roots):
                return False
        return True

    # -------------------------------------------------------------- building

    def touch(self) -> None:
        """Something wrote to the library. The next refresh will find out what."""
        with self._lock:
            self.stale = True
            self.writes += 1

    def let_go(self, roots) -> int:
        """The library has moved: forget, now, what is not in the new one.

        The pass that reads the new library can take minutes, and until this
        existed the old one's photographs stayed in the grid, the counts and
        the map for all of them - Setup said one library and Photos showed
        another. What is still inside the new trees is kept, so pointing the
        library one folder up or down costs nothing to re-read.
        """
        want = _normed(roots)
        with self._lock:
            if _normed(self.roots) == want:
                return 0
            keep = {p: e for p, e in self.files.items()
                    if _inside(os.path.normcase(os.path.abspath(p)), want)}
            gone = len(self.files) - len(keep)
            self.files = keep
            self.roots = [os.path.abspath(str(r)) for r in roots]
            self.unread = True
            self.changes += 1
            self._reorder()
        return gone

    def clear(self) -> bool:
        """No library at all: an empty index, rather than the last one's."""
        with self._lock:
            if not self.files and not self.roots:
                return False
            self.files = {}
            self.roots = []
            self.unread = False
            self.changes += 1
            self.stale = True
            self._reorder()
        self.save()
        return True

    # ------------------------------------------- when the app did it itself

    def followed(self, moves=(), copies=(), gone=()) -> int:
        """What this app just did to the library, written straight in.

        A WALK IS FOR CHANGES NOBODY TOLD US ABOUT.

        Moving a shoot used to mark the index stale, and the next pass walked
        the whole library and stat'd every file in it to discover the forty
        files this app had moved itself - and it knew exactly which forty the
        whole time. Worse, the explorer's own moves told the index nothing at
        all, so after moving a folder the Photos screen went on showing those
        photographs where they used to be until something else happened to mark
        it stale.

        A move does not change a photograph. The capture time, the camera, the
        stars, the tags and the coordinates are all facts about the file, and
        the file is the same file - so its entry travels with it and only the
        signature is taken again, which is one stat and no read. A copy is the
        same photograph in a second place, so its entry is copied too. Nothing
        here opens a photograph.

        Paths are matched as paths: moving a FOLDER moves everything the index
        holds beneath it.

        Returns how many entries this changed.
        """
        import shutil as _sh                            # noqa: F401  (symmetry)
        hit = 0
        with self._lock:
            if self.building:
                # A pass is walking right now and will replace `files` with
                # what it found, which may be from before this move. Written in
                # below all the same, so the grid is right meanwhile, and marked
                # stale so the next pass reads it again rather than trusting it.
                self.stale = True
                self.writes += 1
            def under(prefix: str) -> list:
                low = os.path.normcase(os.path.abspath(prefix))
                out = []
                for path in self.files:
                    here = os.path.normcase(path)
                    if here == low or here.startswith(low + os.sep):
                        out.append(path)
                return out

            def carry(was: str, now: str, keep: bool) -> int:
                """The entry at `was` lands at `now`. `keep` leaves the original
                where it is, which is what a copy means."""
                n = 0
                was_abs = os.path.abspath(was)
                now_abs = os.path.abspath(now)
                for path in under(was_abs):
                    rest = os.path.abspath(path)[len(was_abs):].lstrip("\\/")
                    to = os.path.join(now_abs, rest) if rest else now_abs
                    e = list(self.files[path])
                    try:
                        st = os.stat(to)
                    except OSError:
                        # It is not where it was said to be. Leave it to the
                        # next pass rather than writing down a guess.
                        self.stale = True
                        continue
                    e[_AT["size"]] = st.st_size
                    e[_AT["when"]] = st.st_mtime
                    e[_AT["sig"]] = facts_signature(to, st)
                    self.files[to] = e
                    if not keep:
                        self.files.pop(path, None)
                    n += 1
                return n

            for was, now in (moves or ()):
                hit += carry(str(was), str(now), keep=False)
            for was, now in (copies or ()):
                hit += carry(str(was), str(now), keep=True)
            for path in (gone or ()):
                for one in under(str(path)):
                    self.files.pop(one, None)
                    hit += 1
            if hit:
                self.changes += 1
                self.when = time.time()
                self._reorder()
        if hit:
            self.save()
        return hit

    def stop(self) -> None:
        self._stop = True

    def refresh(self, roots, progress=None, deep: bool = False) -> dict:
        """Bring the index up to date. Reads only what it has to.

        `deep` throws the notes away and reads everything again, which is the
        button for "it is wrong and I do not know why".
        """
        from . import facts
        from . import find
        from . import steady
        from . import walk as W

        roots = [os.path.abspath(str(r).strip()) for r in roots
                 if str(r or "").strip() and os.path.isdir(str(r).strip())]
        if not roots:
            with self._lock:
                self.building = False
                self.error = "No library folder is set yet."
            return {"photos": 0, "added": 0, "gone": 0, "error": self.error}

        self._stop = False
        with self._lock:
            was_roots = [os.path.abspath(str(r)) for r in self.roots]
        self.let_go(roots)
        with self._lock:
            self.building = True
            began = self.writes
            self.done = 0
            self.total = 0
            self.now = ""
            self.error = ""
            # How many files this pass has actually had to OPEN - as opposed to
            # how many it walked past and recognised. The difference is the
            # difference between work and a check, and the page needs to know
            # which is happening: a library that has not changed in a week was
            # announcing "Reading your library" every minute, which teaches
            # somebody to ignore the one line that matters when it is true.
            self.reading = 0

        found: list = []
        seen: set = set()
        for root in roots:
            for path in W.walk(root).files:
                if path in seen:
                    continue
                seen.add(path)
                if is_picture(path) or kind(path) in ("raw", "video"):
                    found.append(path)

        with self._lock:
            self.total = len(found)
            was = dict(self.files) if not deep else {}

        reader = facts.reader()
        fresh: dict = {}
        added = 0
        unreadable = 0
        unreadable_names: list = []
        for n, path in enumerate(found, 1):
            if self._stop:
                break
            if n % 25 == 0:
                with self._lock:
                    self.done = n
                    self.now = os.path.basename(path)
                if progress:
                    progress(n, len(found), os.path.basename(path))
            try:
                st = os.stat(path)
            except OSError:
                continue
            # Held from the stat to the decision. Asking whether this file has
            # changed, and then reading it if it has, are questions about one
            # file in one moment - and the stat for that moment has just been
            # taken. See `core/steady.py`.
            with steady.holding(path, st):
                sig = facts.signature(path, stat=st)
                old = was.get(path)
                if old is not None and old[_AT["sig"]] == sig \
                        and len(old) == len(FIELDS):
                    fresh[path] = old
                    continue
                try:
                    fresh[path] = _read_entry(path, st, sig, find, reader)
                    added += 1
                    with self._lock:
                        self.reading = added
                except Exception as exc:                   # noqa: BLE001
                    unreadable += 1
                    if len(unreadable_names) < UNREADABLE_NAMES:
                        why = (str(exc).strip().splitlines() or [""])[0]
                        unreadable_names.append({
                            "path": path,
                            "error": (why or type(exc).__name__)[:200]})
                    continue
        reader.save()

        with self._lock:
            gone = len(was) - sum(1 for p in was if p in fresh)
            self.files = fresh
            self.roots = roots
            self.when = time.time()
            self.unreadable = unreadable
            self.unreadable_names = unreadable_names
            self.building = False
            self.stale = self.writes != began
            if not self._stop:
                self.unread = False
            self.done = len(fresh)
            self.total = len(fresh)
            self.now = ""
            self.reading = 0
            if added or gone:
                self.changes += 1
            moved = [os.path.abspath(str(r)) for r in roots] != was_roots
            self._reorder()
        # WRITTEN ONLY WHEN THERE IS SOMETHING TO WRITE.
        #
        # The index is one JSON document - sixteen megabytes for eighty
        # thousand photographs - and it was rewritten at the end of every pass,
        # including the passes that walked the whole library and found that
        # nothing at all had changed. Those are most passes on most days. On a
        # NAS that is sixteen megabytes through the mount, and a disk spun up,
        # to write down what was already written down.
        if added or gone or moved:
            self.save()
        return {"photos": len(fresh), "added": added, "gone": max(0, gone),
                "stopped": self._stop, "written": bool(added or gone or moved)}

    def start(self, roots, deep: bool = False) -> bool:
        """Refresh on a thread of its own, if one is not already running.

        Daemon, so a Stop or a restart never waits for it: nothing here is a
        write, so an interrupted pass costs a partial index and no damage.
        """
        if self._thread is not None and self._thread.is_alive():
            return False
        self._for = list(roots)
        self._thread = threading.Thread(
            target=self._run, args=(list(roots), deep), daemon=True)
        self._thread.start()
        return True

    def _run(self, roots, deep) -> None:
        try:
            self.last = self.refresh(roots, deep=deep)
        except Exception as exc:                           # noqa: BLE001
            with self._lock:
                self.building = False
                self.error = str(exc)[:300]

    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def reading_roots(self) -> list:
        """The trees the running pass was started on, or the ones last read."""
        return list(self._for) if self.busy() else list(self.roots)

    def wait(self, timeout: float | None = None) -> dict:
        """Wait for a refresh started by `start` to end; what it said, or {}."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return dict(self.last) if not self.busy() else {}


def key_of(entry) -> str:
    """Where a photograph sorts. One function, because everything that orders
    photographs has to agree: the grid put the EXIF-less scan at the top (by
    its file date) while an album used its blank capture time and put it last,
    so the album's cover was not the first thing in the album."""
    taken = entry[_AT["taken"]]
    return taken or time.strftime("%Y-%m-%d %H:%M:%S",
                                  time.localtime(entry[_AT["when"]] or 0))


def _seconds_of(shutter: str):
    """"1/250" and "2.5s" back into seconds, for a search by shutter speed."""
    text = str(shutter or "").strip().rstrip("s")
    if not text:
        return None
    try:
        if "/" in text:
            top, bottom = text.split("/", 1)
            return float(top) / float(bottom)
        return float(text)
    except (ValueError, ZeroDivisionError):
        return None


def facts_signature(path: str, st=None) -> str:
    """The file's signature, without importing `facts` at the top of this file."""
    from . import facts
    return facts.signature(path, stat=st)


def _read_entry(path: str, st, sig: str, find, reader) -> list:
    hit = find.about(path, reader)
    where = reader.location(path, stat=st)
    e = _blank()
    e[_AT["taken"]] = hit.taken
    e[_AT["kind"]] = kind(path)
    e[_AT["camera"]] = hit.camera
    e[_AT["lens"]] = hit.lens
    e[_AT["focal"]] = hit.focal
    e[_AT["focal35"]] = hit.focal35
    e[_AT["fnumber"]] = hit.fnumber
    e[_AT["shutter"]] = hit.shutter
    e[_AT["iso"]] = hit.iso
    e[_AT["stars"]] = hit.stars
    e[_AT["colour"]] = hit.colour
    e[_AT["tags"]] = list(hit.tags)
    if where and where[0] is not None:
        e[_AT["lat"]], e[_AT["lon"]] = round(float(where[0]), 6), round(float(where[1]), 6)
    e[_AT["size"]] = hit.size
    e[_AT["when"]] = hit.when
    e[_AT["sig"]] = sig
    return e


# --------------------------------------------------------------- the one in use

_ONE: Catalogue | None = None
_MAKING = threading.Lock()


def shared() -> Catalogue:
    """The catalogue this process uses. Made once, loaded from disk."""
    global _ONE
    with _MAKING:
        if _ONE is None:
            try:
                _ONE = Catalogue(store_path(FILE))
            except Exception:                              # noqa: BLE001
                _ONE = Catalogue("")
        return _ONE


def forget_all() -> None:
    """Drop the shared one - for tests, which must not share an index."""
    global _ONE
    with _MAKING:
        _ONE = None


def wanted_roots() -> list:
    """Which trees the index covers: the library, and the video tree if it is
    somewhere else. Not the RAW or previews trees - those mirror the library and
    indexing them would count every photograph two or three times."""
    from . import settings as S
    saved = S.load()
    out = []
    for key in ("library", "video"):
        folder = str(saved[key] or "").strip()
        if folder and os.path.isdir(folder):
            if not any(os.path.normcase(os.path.abspath(folder)).startswith(
                    os.path.normcase(os.path.abspath(o)) + os.sep) for o in out):
                out.append(folder)
    return out


def _normed(roots) -> list:
    """Trees compared the way a filesystem compares them. A trailing slash or a
    different capitalisation in Setup is not a move, and treating it as one
    meant re-reading the whole library every minute for ever."""
    return [os.path.normcase(os.path.abspath(str(r))).rstrip("/\\")
            for r in roots]


def _inside(low: str, roots) -> bool:
    return any(low == r or low.startswith(r + os.sep) for r in roots)


def trees_moved(was, now) -> bool:
    """Do these two lists of trees name different places?"""
    return _normed(was) != _normed(now)


def nothing_set() -> bool:
    """Is there no library (and no video tree) in Setup at all?

    Not the same as `wanted_roots()` coming back empty: a library on a share
    that is not mounted this minute is still the library, and throwing its
    index away over a hiccup would mean reading eighty thousand photographs
    again when the share comes back.
    """
    from . import settings as S
    saved = S.load()
    return not any(str(saved[k] or "").strip() for k in ("library", "video"))


def touch() -> None:
    """Called when a run finishes. Cheap, and never blocks the run."""
    try:
        shared().touch()
    except Exception:                                      # noqa: BLE001
        pass
