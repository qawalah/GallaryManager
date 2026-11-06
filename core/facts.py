"""Everything worth knowing about a photograph, read once and remembered by stat.

Sending a library out to develop used to open each photograph four separate
times: `rating_of` for the stars, `read_capture` for the clock and the camera,
`tags_of` for the keywords and `colour_of` for the label - and each of those
looks in the sidecar first, so a rated RAW cost four sidecar reads as well.
Eight opens per photograph, over SMB, a hundred thousand times. That is the
thirty minutes.

Two things are done about it here, and they are independent:

**Every fact out of one read.** They all come from the same two places - the
front of the file and the sidecar beside it - so asking for the rating, the
clock, the keywords and the colour costs one open between them rather than four.
(The last piece of that lives in `jpegseg.read_header`, which hands back the
bytes it just read when the same unchanged file is asked for again; the three
readers that look for keywords alone used to be three reads.)

A task that walks its tree twice - once to group brackets, once to decide - pays
one read per file per walk, not per question. Two rather than eight, and then
none at all the next time.

**One read per file, ever, until the file changes.** The answer is kept against
a SIGNATURE of the file itself: its size and its modification time, to the
nanosecond, and the same for its sidecar. Touch either and the signature moves
and it is read again; touch neither and the answer is free.

**Why this does not break "measured, never remembered".** That rule is about not
keeping a record of what was DONE, because a log of past actions quietly stops
describing a library the moment a shoot is renamed in File Station. This is a
different shape: it is keyed on the thing it describes, so it cannot disagree
with the disk without the disk telling it. The Library view has worked this way
since it was built - a folder's answer cached against a fingerprint of that
folder - and this is the same bargain one level down.

**The sidecar is in the signature, and that is the whole correctness argument.**
Lightroom rates a RAW by rewriting the `.xmp` beside it and never touching the
negative. A signature made from the photograph alone would serve last week's
rating for ever, and the failure would be invisible: the star would be on the
tablet, the app would say nothing changed, and the photograph would simply never
go out to develop. So a file that has a sidecar is signed by both.

**Nothing here decides anything.** It reads, it caches, and every caller keeps
its own judgement. A cache that also knew what a four-star photograph deserves
would be a second place for the thresholds to live.
"""

from __future__ import annotations

import atexit
import datetime as _dt
import json
import os
import threading
import time

from . import sidecar as _sc
from . import tags as _tags
from .exifwrite import rating_of
from .photo import Capture, read_capture

VERSION = 1          # bump to throw away every cached answer

# How long a note survives after nothing has asked about that file. Long enough
# that a tree only one task walks is not thrown away and paid for again, short
# enough that a library reorganised months ago stops being carried around.
#
# Age rather than "drop whatever this run did not see", because the store is
# SHARED: syncing ratings walks the previews tree, sending to develop walks the
# develop tree, and each pruning the other's notes would mean both paid full
# price every pass while appearing to have a cache.
KEEP_DAYS = 45
_DAY = 86400.0

# The fields of a Capture, in the order they are stored. A list rather than a
# dict per photograph: a hundred thousand small dicts is most of a gigabyte of
# Python objects, and the keys are the same every time.
CAP_FIELDS = ("ok", "taken", "ev", "exposure_mode", "exposure", "fnumber",
              "iso", "focal_length", "model", "offset_minutes", "lens", "focal35")
# Adding a field changes the shape, and a note of the old shape is read again
# rather than trusted - see _unpack_capture. So growing this list costs one
# re-read per file, once, and never a wrong answer.


def _pack_capture(cap: Capture) -> list:
    out = []
    for name in CAP_FIELDS:
        value = getattr(cap, name, None)
        if isinstance(value, _dt.datetime):
            value = value.isoformat()
        out.append(value)
    return out


def _unpack_capture(path: str, packed) -> Capture | None:
    if not isinstance(packed, list) or len(packed) != len(CAP_FIELDS):
        return None                       # the shape changed; read it again
    values = {}
    for name, value in zip(CAP_FIELDS, packed):
        if name == "taken" and isinstance(value, str) and value:
            try:
                value = _dt.datetime.fromisoformat(value)
            except ValueError:
                return None
        values[name] = value
    try:
        return Capture(path=path, **values)
    except TypeError:
        return None


def signature(path: str, side: str | None = None, stat=None) -> str:
    """What this file looks like right now, cheaply enough to ask every run.

    Three numbers out of one stat, and each is here because the other two miss
    something:

    **Size**, which catches the ordinary case of a file being replaced.

    **Modification time in nanoseconds** - `st_mtime_ns`, the integer the
    filesystem actually recorded. A rating rewritten into a sidecar of the same
    length one second later is the exact case this has to catch, and seconds
    cannot see it.

    **The inode**, which is the one that matters most here and is the least
    obvious. Every metadata write in this app is "write a temp file, then
    os.replace" - and it then puts the original's date back on purpose, so that
    rating a photograph does not make it look freshly touched to every backup
    tool in the house. Size unchanged, date restored to the nanosecond: a
    signature made of those two alone would serve last week's rating for ever,
    and the failure would be silent. `os.replace` cannot preserve the inode.
    Measured, not assumed - there is a test that rates a JPEG and asserts the
    size and date are identical and the signature is not.

    A file moved or copied by DSM also gets a new inode, so it is read again
    when it need not have been. That is the error in the safe direction: extra
    reads cost time, a stale answer costs a photograph.

    Returns "" when the file cannot be stat'd, and "" never matches anything, so
    an unreadable file is read rather than answered from a stale note.
    """
    try:
        if stat is None:
            # The caller holding this file still has already taken it. See
            # `core/steady.py` - outside such a scope this is an ordinary stat.
            from . import steady
            stat = steady.stat_of(path)
        st = os.stat(path) if stat is None else stat
        mark = f"{st.st_size}:{st.st_mtime_ns}:{st.st_ino}"
    except OSError:
        return ""
    mark += _READER.get(os.path.splitext(path)[1].lower(), "")
    side = _sc.beside(path) if side is None else side
    if side:
        try:
            sst = os.stat(side)
            mark += f"|{sst.st_size}:{sst.st_mtime_ns}:{sst.st_ino}"
        except OSError:
            mark += "|gone"
    return mark


# File types whose reader learned to read more than it used to, and a mark that
# tells a note taken since apart from one taken before. Until 3.11 a HEIC was
# read as having no EXIF at all; without this, every HEIC already in the store
# would go on answering "no date, no camera" until the file itself changed.
# Only these files are read again - bumping VERSION would throw away the notes
# on a whole library to correct a few thousand of them.
#
# And a JPEG, from 3.12.2: the stars Lightroom writes into the photo's own XMP
# packet are read now, and so is a packet behind a big ICC profile past the
# first quarter megabyte. A note from before says "unrated" and "no tags" for
# both, so each JPEG is read once more.
_READER = {".heic": "#heif1", ".heif": "#heif1",
           ".jpg": "#xmp1", ".jpeg": "#xmp1"}


# How long after the last save() the store is actually written. Every task
# that reads photographs used to write the whole store when it finished - and a
# flow is several tasks, and the index loop is another, so a pass over a large
# library rewrote the same multi-megabyte file a handful of times within a
# minute. Saves that land inside this window are one write.
SAVE_AFTER = 2.0


class _Store:
    """The notes for one store file, shared by every reader in the process.

    One per path rather than one per reader, for two reasons. The file is read
    once when the process starts instead of once per task - a store the size of
    a library is a measurable read over SMB. And two readers in two threads (the
    index loop and a run, say) no longer each hold a copy and save it back over
    the other's, losing whatever the first had learned.

    The lock covers the dictionary, not the reading: a photograph is read with
    the lock released, so a slow file on one thread does not stall every other
    thread's questions. Two threads asking about the same new file at the same
    moment may both read it, which costs a read and never a wrong answer.
    """

    def __init__(self, path: str = ""):
        self.path = path
        self.lock = threading.Lock()
        self.entries: dict = {}
        self.dirty = False
        self.writes = 0                    # how many times the file was written
        self._timer: threading.Timer | None = None
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    got = json.load(fh)
                if isinstance(got, dict) and got.get("v") == VERSION:
                    self.entries = got.get("files") or {}
            except (OSError, ValueError):
                self.entries = {}

    def prune(self) -> None:
        """Drop notes nothing has asked about for KEEP_DAYS. Caller holds lock."""
        cutoff = time.time() - KEEP_DAYS * _DAY
        old = [k for k, v in self.entries.items()
               if float(v.get("t") or 0) < cutoff]
        for k in old:
            del self.entries[k]
        if old:
            self.dirty = True

    def save_soon(self) -> None:
        with self.lock:
            self.prune()
            if not self.dirty or self._timer is not None:
                return
            self._timer = threading.Timer(SAVE_AFTER, self.flush)
            self._timer.daemon = True
            self._timer.start()

    def flush(self) -> bool:
        """Write the notes now, if anything changed. Best effort, always."""
        with self.lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if not self.path or not self.dirty:
                return False
            self.prune()
            # A copy taken under the lock and written outside it: a run that is
            # still asking questions should not wait on a disk write, and the
            # copy cannot change size half way through being written out.
            snap = {k: dict(v) for k, v in self.entries.items()}
            self.dirty = False
        try:
            tmp = self.path + ".part"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"v": VERSION, "files": snap}, fh)
            os.replace(tmp, self.path)
            with self.lock:
                self.writes += 1
            return True
        except OSError:
            with self.lock:
                self.dirty = True
            return False


_STORES: dict[str, _Store] = {}
_STORES_LOCK = threading.Lock()


def _shared(path: str) -> _Store:
    if not path:
        return _Store("")                  # nowhere to keep it: this run only
    key = os.path.abspath(path)
    with _STORES_LOCK:
        got = _STORES.get(key)
        if got is None:
            got = _STORES[key] = _Store(key)
        return got


def flush() -> int:
    """Write every store that has unsaved notes. For the end of a run, and exit.

    The timer would get there on its own; this is for the moments when waiting
    is wrong - a command-line run about to exit, or a run that has just finished
    and whose notes the next run should not have to wait two seconds for.
    """
    with _STORES_LOCK:
        stores = list(_STORES.values())
    return sum(1 for s in stores if s.flush())


atexit.register(flush)


class Reader:
    """Reads photographs, and remembers what they said.

    Pass `store` a file path to keep the answers between runs; leave it blank
    and it is a per-run cache, which still saves the three duplicate opens.

    A Reader is one caller's view of a store the whole process shares (see
    `_Store`): the notes are common, the counts are its own. `read` and `reused`
    are the two numbers worth reporting: they are the difference between a pass
    that costs an hour and one that costs a minute, and a task that shows them
    makes the cache's behaviour visible instead of something to take on trust.
    """

    def __init__(self, store: str = ""):
        self.store = store
        self._shared = _shared(store)
        self.read = 0                      # files actually opened this run
        self.reused = 0                    # answered from the note
        self.seen: set = set()             # the files this run asked about

    @property
    def entries(self) -> dict:
        return self._shared.entries

    @property
    def _dirty(self) -> bool:
        return self._shared.dirty

    @_dirty.setter
    def _dirty(self, value: bool) -> None:
        with self._shared.lock:
            self._shared.dirty = bool(value)

    # ------------------------------------------------------------- the facts

    def _entry(self, path: str, stat=None) -> dict:
        """The note for this file, fresh if the file has moved since.

        The signature is checked on EVERY ask, not once per run. A pass that
        takes twenty minutes is a pass during which Lightroom can finish writing
        a sidecar, and answering the second half of it from a note taken before
        that write is how a rating goes missing for a day.
        """
        self.seen.add(path)
        sig = signature(path, stat=stat)
        shared = self._shared
        with shared.lock:
            got = shared.entries.get(path)
            if got is not None and sig and got.get("sig") == sig:
                # Touched, so it is not aged out - but only written down once a
                # day, or every pass would dirty every entry and rewrite the
                # whole store to record that nothing had changed.
                now = time.time()
                if now - float(got.get("t") or 0) > _DAY:
                    got["t"] = now
                    shared.dirty = True
                return got
            fresh = {"sig": sig, "t": time.time()}
            shared.entries[path] = fresh
            shared.dirty = True
            return fresh

    def _field(self, path: str, name: str, compute, stat=None):
        entry = self._entry(path, stat=stat)
        shared = self._shared
        with shared.lock:
            if name in entry:
                self.reused += 1
                return entry[name]
        # Read with the lock released - see _Store.
        value = compute(path)
        with shared.lock:
            entry[name] = value
            shared.dirty = True
        self.read += 1
        return value

    def stars(self, path: str, stat=None) -> int:
        """The rating, as a number. Unrated is 0 - never None.

        `rating_of` returns None for "could not tell" and 0 for "unrated", and
        every caller in this app treats the two the same, so the distinction is
        flattened here rather than in four `or 0`s.
        """
        return self._field(path, "stars",
                           lambda p: int(rating_of(p) or 0), stat=stat) or 0

    def capture(self, path: str, stat=None) -> Capture:
        packed = self._field(path, "cap", lambda p: _pack_capture(read_capture(p)),
                             stat=stat)
        cap = _unpack_capture(path, packed)
        if cap is not None:
            return cap
        # An unreadable note is not a reason to give a wrong answer.
        with self._shared.lock:
            self.entries.get(path, {}).pop("cap", None)
        self.read += 1
        return read_capture(path)

    def location(self, path: str, stat=None) -> tuple:
        """(lat, lon), or (None, None) when the file carries no position.

        Cached like everything else here: "which of these have a location" is a
        question the Library tab, Search and the viewer all ask, and reading the
        GPS block of forty thousand files three times over is three times the
        right amount of work.

        The sidecar counts. A position written beside the file is the position
        every other feature reads, so a search that only looked inside the JPEG
        would call a geotagged photograph unlocated.
        """
        def read(one):
            from . import places as _places
            got = _places.coordinates_of(one)
            return [got[0], got[1]] if got else [None, None]
        got = self._field(path, "gps", read, stat=stat) or [None, None]
        try:
            return (got[0], got[1])
        except (TypeError, IndexError):
            return (None, None)

    def tags(self, path: str, stat=None) -> list:
        return list(self._field(path, "tags",
                                lambda p: list(_tags.tags_of(p)), stat=stat) or [])

    def label(self, path: str, stat=None) -> str:
        """The label string actually written on this file, exactly as it is.

        The RAW string rather than the colour, because the two are not the same
        question and only one of them is worth caching. "" means no label;
        anything this app does not recognise - some other program's word - comes
        back as it stands, so a caller can leave it alone rather than read it as
        "no colour" and write over it.

        And the string does not depend on what a colour currently MEANS: rename
        purple in Setup and every cached colour would be stale, while every
        cached label is still exactly what is on the disk.
        """
        from . import labels as _labels     # here: labels reads settings
        return str(self._field(path, "label",
                               lambda p: _labels.written_label(p), stat=stat) or "")

    def colour(self, path: str, stat=None) -> str:
        """Which of the five that label means - "" for none, and for anybody
        else's."""
        from . import labels as _labels
        return _labels.colour_named(self.label(path, stat=stat))

    # ------------------------------------------------------------- keeping it

    def forget(self, path: str) -> None:
        """Drop what is known about a file this run has just written to.

        Any task that changes a photograph calls this. The signature would
        catch it on the next pass anyway - that is the point of the signature -
        but within one run a stale answer would be handed to the very next step
        of the chain, which is the case the signature cannot help with because
        nobody has looked again yet.
        """
        with self._shared.lock:
            if self._shared.entries.pop(path, None) is not None:
                self._shared.dirty = True

    def save(self) -> bool:
        """Ask for the notes to be written back. Best effort, always.

        Notes nothing has asked about for `KEEP_DAYS` are dropped now, which is
        what keeps the store the size of the library rather than the size of
        every library it has ever been pointed at. By AGE rather than by "what
        this run saw", because the store is shared between tasks that walk
        different trees - see the note on KEEP_DAYS.

        The write itself happens SAVE_AFTER seconds later, or at the end of the
        run (`flush`), so that the several tasks of one pass write the file once
        between them rather than once each. Returns whether a write is pending.

        A failure to write is not a failure of the run. The work is done; the
        worst case of a lost note is that the next pass reads those files again.
        """
        if not self.store:
            return False
        self._shared.save_soon()
        return self._shared.dirty or self._shared._timer is not None

    def said(self) -> str:
        """One line for a plan's stats: what the cache actually saved."""
        total = self.read + self.reused
        if not total:
            return "nothing read"
        return (f"{self.read:,} read, {self.reused:,} already known "
                f"({self.reused * 100 // total}%)")


STORE = "facts.json"


def reader() -> Reader:
    """The shared store, or a per-run one if there is nowhere to keep it.

    One file for the whole app on purpose. Syncing ratings reads the library's
    photographs to find each preview's original; sending to develop reads the
    same photographs to see what qualifies. A store each and the second task
    pays full price for files the first one had just read - within the same
    pass, seconds apart.

    Each call is a fresh Reader - its own counts for its own run - over the one
    set of notes the process keeps for that file, read from disk the first time
    it is asked for and not again.
    """
    try:
        from .store import store_path
        return Reader(store_path(STORE))
    except Exception:                                  # noqa: BLE001
        return Reader()
