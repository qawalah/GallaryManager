"""How much this app read off the disk, counted by the app rather than the kernel.

`core/load.py` asks the kernel: `/proc/self/io` says exactly how many bytes came
off the device, which is the best possible answer when it is there. On Abu's NAS
it is not - the container cannot read it, and every run reported

    Read: not measured

which is precisely the number worth having. On a NAS nothing here is
computation; it is opening files over a disk, so "read 412 MB" is the honest
description of the load and CPU seconds are a footnote.

So this counts the same thing from the other side: every place this app opens a
photograph, a sidecar or a header adds what it took. That number is always
available, because it does not depend on the container being allowed to see the
kernel's accounting.

**The two measures are not the same thing and both are kept.** The kernel counts
bytes off the DEVICE; this counts bytes this app ASKED for. The second is larger
when the page cache answered, smaller when readahead pulled in more than was
wanted - and the gap between them is itself informative: a second pass that asks
for the same 400 MB and takes none of it off the disk is the cache doing its
job. Where the kernel's figure is missing, this is the only one, and the wording
says which it is rather than passing one off as the other.

**Files opened matters as much as bytes.** Ten thousand files of 60 KB each is
six hundred megabytes and also ten thousand seeks, and on a spinning disk the
seeks are what you wait for. A run that halves its bytes and keeps its file
count has not got much faster, and the two numbers side by side say so.

Counted process-wide, like the kernel's own counters, so two runs at once each
see the other's reads in their own difference. That is not corrected for by
guessing: it is said in the wording, exactly as `load.py` says it.
"""

from __future__ import annotations

import threading

_LOCK = threading.Lock()
_FILES = 0
_BYTES = 0
_WROTE = 0


def read(size: int) -> None:
    """One file opened and read, of this many bytes. Never raises.

    Called from the handful of places that actually touch a photograph. It has
    to be free enough to sit in that path without being thought about - two
    integer adds under a lock, and no I/O of its own.
    """
    global _FILES, _BYTES
    try:
        n = int(size)
    except (TypeError, ValueError):
        return
    with _LOCK:
        _FILES += 1
        _BYTES += max(0, n)


def wrote(size: int) -> None:
    """One file written, of this many bytes."""
    global _WROTE
    try:
        n = int(size)
    except (TypeError, ValueError):
        return
    with _LOCK:
        _WROTE += max(0, n)


def copied(size: int) -> None:
    """A file copied: those bytes came off the disk and went back onto it.

    Counted as both, because that is what it costs. A MOVE is not counted at
    all - within one volume it is a rename, and no byte of the photograph is
    touched, which is exactly why this app moves rather than copies wherever it
    can.
    """
    read(size)
    wrote(size)


def totals() -> tuple:
    with _LOCK:
        return _FILES, _BYTES, _WROTE


def snapshot() -> dict:
    files, byts, wrt = totals()
    return {"own_files": files, "own_bytes": byts, "own_written": wrt}


def since(before: dict, after: dict | None = None) -> dict:
    after = snapshot() if after is None else after
    out = {}
    for key in ("own_files", "own_bytes", "own_written"):
        if key in before and key in after:
            out[key] = max(0, after[key] - before[key])
    return out
