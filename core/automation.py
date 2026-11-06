"""Noticing that something changed, so a workflow can run itself.

The three jobs that make up the developing loop each want to happen when
something else has finished, not at a time of day:

    rate on the tablet  ->  sync the ratings into the library
    ratings arrive      ->  send what now qualifies out to develop
    exports come back   ->  file each one beside its original

Running those on a clock is the obvious thing and it is wrong twice: at three in
the morning nothing has changed, and at four in the afternoon when you have just
finished rating a shoot it waits six hours. So each step WATCHES a tree, and
runs when that tree is different from the last time it looked.

**This is polling, and saying so matters.** A real change notification - inotify
- does not work here, and not because of an oversight: this app runs in a
container watching a volume that DSM, Synology Drive and SMB all write to from
outside, and a kernel watch on a bind-mounted volume does not reliably see those
writes. A watch that silently misses changes would be worse than no watch,
because the workflow would appear to work and then quietly stop. So the trees
are looked at on an interval, and the interval is how quickly a change is
NOTICED - not how often work is done.

**This app's own writes may not show up here, and that is deliberate.** Every
writer in it puts a file's date back after changing metadata, so a library does
not look freshly touched merely because a rating was copied onto it. Whether the
tree then looks different at all depends on whether the file's SIZE moved, which
is not something to build on either way. So the chain never relies on a step
noticing its own work: it carries "something earlier in this pass wrote"
forwards instead.

**What "different" means is a choice with a cost.** A folder's own timestamp
changes when a file appears, disappears or is renamed inside it, and reading
those is a handful of stats. It does NOT change when a file is edited in place -
and rating a photograph in Lightroom rewrites the sidecar without touching its
folder, which is the single most important change this thing has to notice. So
the honest default reads every file's date, which costs one stat per file, and
the cheaper mode is offered with its blind spot spelled out.
"""

from __future__ import annotations

import json
import os
import time

from . import exclude
from .paths import skip_folder
from .store import store_path

FILE = "automation.json"


def _path() -> str:
    try:
        return store_path(FILE)
    except Exception:                                  # noqa: BLE001
        return ""


def read() -> dict:
    where = _path()
    if not where:
        return {}
    try:
        with open(where, "r", encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def write(state: dict) -> bool:
    """Best effort, always.

    What is kept here is "what the trees looked like last time" - a convenience
    that can be rebuilt by looking again. Letting a failure to write it take
    down a run that has already copied files would be a bad trade: the work is
    done, and the worst case of a lost note is that the next pass does the same
    look twice and finds nothing to do.
    """
    where = _path()
    if not where:
        return False
    try:
        with open(where, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1, sort_keys=True)
        return True
    except OSError:
        return False


# --------------------------------------------------------------- looking

class Look:
    """What a tree looked like, and what it cost to find out."""

    def __init__(self, mark: str = "", files: int = 0, folders: int = 0,
                 newest: float = 0.0, seconds: float = 0.0, there: bool = True):
        self.mark, self.files, self.folders = mark, files, folders
        self.newest, self.seconds, self.there = newest, seconds, there

    def __eq__(self, other):
        return isinstance(other, Look) and self.mark == other.mark


def fingerprint(root: str, deep: bool = True) -> Look:
    """What this tree looks like right now, as one short string.

    Four numbers, because no one of them is enough on its own: how many files
    there are catches things appearing and disappearing; how many folders catches
    a shoot being moved; the total size catches a file replaced by a different
    one; and the SUM of every date - to the millisecond - catches a file being
    edited in place.

    The sum rather than the newest, and nanoseconds rather than seconds, because
    of one case that is not a corner: a sidecar rewritten by Lightroom seconds
    after the last look, holding a different rating in the same number of bytes.
    Same count, same size, same second - and one photograph that should have
    gone to the tablet and never would. `st_mtime_ns` is the filesystem's own
    integer, so nothing is rounded off on the way here, and a SUM also notices a
    date that went backwards, which a maximum cannot.

    `deep=False` reads folder dates only. That is a few hundred stats instead of
    a hundred thousand, and it cannot see a sidecar being rewritten in place.
    """
    began = time.time()
    root = str(root or "").strip()
    if not root or not os.path.isdir(root):
        return Look(mark="", there=False, seconds=time.time() - began)

    away = exclude.now()
    if away and exclude.blocks(root, away):
        # The tree being watched is itself excluded. "Not there" rather than
        # "unchanged for ever", because a step whose tree you have excluded
        # should say so rather than quietly never running again.
        return Look(mark="", there=False, seconds=time.time() - began)

    files = folders = 0
    newest = 0.0
    total = 0
    # Nanoseconds, as integers, summed exactly. st_mtime is a float and a sum of
    # a hundred thousand of them runs out of significant digits somewhere around
    # the millisecond - quietly swallowing the very changes this exists to
    # catch. st_mtime_ns is what the filesystem actually recorded.
    clocks = 0
    for here, dirs, names in os.walk(root, onerror=lambda e: None):
        dirs[:] = [d for d in dirs if not skip_folder(d)]
        if away:
            # The same folders the steps will refuse to look at. A fingerprint
            # that counted them would wake the flow up for a change in a folder
            # its own steps then leave alone - every pass, for ever.
            dirs[:] = [d for d in dirs
                       if not exclude.blocks(os.path.join(here, d), away)]
        folders += 1
        try:
            st = os.stat(here)
            newest = max(newest, st.st_mtime)
            clocks += st.st_mtime_ns
        except OSError:
            pass
        if not deep:
            files += len(names)
            continue
        with os.scandir(here) as it:
            for entry in it:
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                files += 1
                total += st.st_size
                newest = max(newest, st.st_mtime)
                clocks += st.st_mtime_ns
    return Look(mark=f"{files}:{folders}:{total}:{clocks}",
                files=files, folders=folders, newest=newest,
                seconds=time.time() - began)


def changed(key: str, look: Look, state: dict | None = None) -> bool:
    """Is this different from the last time that step looked?

    A tree that is not there is never "changed": the previews tree being missing
    is a thing to say out loud, not a reason to run a sync against nothing.
    """
    if not look.there or not look.mark:
        return False
    state = read() if state is None else state
    return str((state.get(key) or {}).get("seen") or "") != look.mark


def remember(key: str, look: Look, said: str = "", ran: bool = False,
             state: dict | None = None) -> dict:
    """Write down what the tree looked like, and what was done about it.

    Recorded AFTER the step has run, and only then, which is the whole
    correctness argument: a step that failed, or was interrupted half way, has
    not caught up with the tree, and leaving the old mark means the next pass
    tries again rather than deciding it is up to date.
    """
    state = read() if state is None else state
    entry = dict(state.get(key) or {})
    if look.there and look.mark:
        entry["seen"] = look.mark
    entry["at"] = time.time()
    if ran:
        entry["ran"] = time.time()
    if said:
        entry["said"] = said[:300]
    state[key] = entry
    write(state)
    return state


def waiting(key: str, count: int, title: str = "", task: str = "",
            state: dict | None = None) -> dict:
    """Work a step found and did NOT do, written down so it can be offered again.

    Deliberately separate from `remember`: it must not touch the mark. A step
    that is set to "just tell me", or one whose pass was a look rather than a
    run, has not caught up with its tree, and recording the mark would mean the
    next pass says "nothing has changed" and the waiting work is never mentioned
    again. That is the bug this app had for a fortnight: 194 photographs ready
    to go out to develop, reported once at four in the morning into a log nobody
    reads, and silent for ever after.

    Zero clears it, which is how the queue empties: the step ran, or the reason
    it was waiting went away.
    """
    state = read() if state is None else state
    entry = dict(state.get(key) or {})
    count = max(0, int(count or 0))
    if count:
        entry["waiting"] = count
        entry["waiting_since"] = entry.get("waiting_since") or time.time()
        if title:
            entry["waiting_what"] = title
        if task:
            entry["waiting_task"] = task
    else:
        for gone in ("waiting", "waiting_since", "waiting_what", "waiting_task"):
            entry.pop(gone, None)
    state[key] = entry
    write(state)
    return state


def last(key: str, state: dict | None = None) -> dict:
    state = read() if state is None else state
    return dict(state.get(key) or {})


def ago(stamp: float) -> str:
    """"12 minutes ago" - the only form of a timestamp anybody reads on a list."""
    if not stamp:
        return "never"
    gap = max(0.0, time.time() - float(stamp))
    if gap < 90:
        n = int(gap)
        return f"{n} second{'' if n == 1 else 's'} ago"
    if gap < 5400:
        n = int(gap / 60)
        return f"{n} minute{'' if n == 1 else 's'} ago"
    if gap < 172800:
        return f"{gap / 3600:.1f} hours ago"
    return f"{int(gap / 86400)} days ago"
