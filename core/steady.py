"""One file, held still while several questions are asked of it.

Indexing a photograph asks it a dozen questions - the capture time, the rating,
the label, the keywords, the coordinates - and every one of them starts by
asking the filesystem something it was asked a moment ago:

    is there a sidecar next to this?        twelve times, two stats each
    has this file changed since I read it?  eleven times, one stat each

Both checks are right on their own. `core/jpegseg.py` caches the front of the
last file it read and stats before serving it, because two unrelated questions
can have a write between them and serving the old bytes would be a rating that
did not take. `core/sidecar.py` lists a folder and keeps the listing against the
folder's own date, because a sidecar can appear at any moment.

Between the twelve questions about ONE photograph, during ONE pass of the
indexer, neither is true. The caller has just stat'd the file. It is about to
ask everything it will ever ask about it and move on. Nothing in this app, and
nothing a person can do by hand in that window, is worth eleven stats.

So the caller says so, for a scope it controls:

    with steady.holding(path, st):
        ...everything that reads this photograph...

Inside, a reader that would have stat'd `path` again uses the stat it was given,
and the folder it sits in is not listed again. Outside - every other caller in
the app, a viewer asking about one photograph, a task writing a rating - nothing
changes at all.

This is deliberately NOT a cache with a timeout. A timeout is a guess about how
long a file stays still; this is a caller stating a fact about a scope it owns,
and it ends when the `with` ends.

Per thread, because the indexer runs on its own and must not vouch for a file
some other request is reading at the same moment.
"""

from __future__ import annotations

import os
import threading

_HERE = threading.local()


class _Held:
    __slots__ = ("path", "folder", "st", "was")

    def __init__(self, path: str, st):
        self.path = os.path.normcase(os.path.abspath(path))
        self.folder = os.path.dirname(self.path)
        self.st = st

    def __enter__(self):
        self.was = getattr(_HERE, "now", None)
        _HERE.now = self
        return self

    def __exit__(self, *_):
        _HERE.now = self.was
        return False


def holding(path: str, st=None):
    """Hold one file still for the questions about to be asked of it."""
    if st is None:
        try:
            st = os.stat(path)
        except OSError:
            st = None
    return _Held(path, st)


def stat_of(path: str):
    """The stat the caller already took, or None - then take your own."""
    held = getattr(_HERE, "now", None)
    if held is None or held.st is None:
        return None
    return held.st if held.path == os.path.normcase(os.path.abspath(path)) else None


def folder_held(folder: str) -> bool:
    """Is this the folder of the file being held still?"""
    held = getattr(_HERE, "now", None)
    if held is None:
        return False
    return held.folder == os.path.normcase(os.path.abspath(folder))
