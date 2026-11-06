"""Folders nothing walks into - a place, not a name.

Setup already has a list of folder NAMES never scanned: `@eaDir`, `#recycle`,
`Developed`. Those mean "this is not a photograph of yours", they are names
because one entry has to cover every shoot, and clearing the box must not
silently start scanning Synology's index folders again.

This is a different question and needs a different answer. "My phone's photos
live in `Photos/Mobile` and I do not want the developing loop touching them" is
about ONE PLACE, not about every folder that happens to be called Mobile - and
it is per flow, because the tidy-up flow may well want them.

So: full paths, and a folder inside an excluded one is excluded too.

**Two lists, added together, never replacing each other.** Setup holds the ones
that are always true - the phone dump, the scanned negatives, the videos you
keep beside the library - and a flow adds whatever else that flow should leave
alone. Replacing would mean building a flow quietly undoes a decision made once
in Setup, which is the shape of every "I thought I had set that" bug.

**It is scoped to a run, not global.** A flow's list applies while its steps are
planning and applying and to nothing else, so opening the Cull tab by hand still
sees your whole library. `using()` is a context manager over a thread-local for
exactly that: two flows running at once do not have to agree.

**And whatever was left out is said.** A tree that is quietly smaller than you
think is how "0 of 400 geotagged" becomes a number you cannot act on. Every walk
records which excluded folders it actually met and how many files it did not
look at, and `Task.make_plan` puts that on the plan as a note. An exclusion you
have forgotten about is worse than no exclusion at all.
"""

from __future__ import annotations

import os
import threading

_LOCAL = threading.local()


def tidy(paths) -> list:
    """A list of real, distinct paths, longest first.

    Longest first so that `under()` finds the most specific match, which is what
    makes a note say "left out Photos/Mobile/2019" rather than "left out
    Photos/Mobile" when both were listed.
    """
    out = []
    for one in (paths or []):
        text = str(one or "").strip().rstrip("/\\")
        if text and text not in out:
            out.append(text)
    return sorted(out, key=len, reverse=True)


def from_settings() -> list:
    from . import settings as _s
    from app.registry import Folders           # here: registry imports settings
    return tidy(Folders.chosen(_s.load()["exclude"]))


def now() -> list:
    """The list in force on this thread. Setup's, unless a run has set its own."""
    got = getattr(_LOCAL, "paths", None)
    if got is None:
        return from_settings()
    return got


class using:
    """The list for one run, and a record of what it actually left out.

    A context manager rather than a setter because the alternative is a flag
    somebody forgets to put back - and a run that leaves an exclusion behind
    makes the NEXT thing you open quietly blind to part of your library.
    """

    def __init__(self, paths=None, add_settings: bool = True):
        wanted = tidy(paths)
        if add_settings:
            wanted = tidy(list(wanted) + from_settings())
        self.paths = wanted
        self.before = None
        self.was_met = None

    def __enter__(self):
        self.before = getattr(_LOCAL, "paths", None)
        self.was_met = getattr(_LOCAL, "met", None)
        _LOCAL.paths = self.paths
        _LOCAL.met = {}
        return self

    def __exit__(self, *_):
        self.met = dict(getattr(_LOCAL, "met", None) or {})
        if self.before is None:
            _LOCAL.paths = None
        else:
            _LOCAL.paths = self.before
        _LOCAL.met = self.was_met
        return False


def active() -> bool:
    """Is a run's own list already in force on this thread?"""
    return getattr(_LOCAL, "paths", None) is not None


def met(folder: str, files: int = 0) -> None:
    """Record that a walk turned back at this folder. Best effort, never raises."""
    seen = getattr(_LOCAL, "met", None)
    if seen is None:
        return
    seen[folder] = seen.get(folder, 0) + max(0, int(files or 0))


def what_was_met() -> dict:
    return dict(getattr(_LOCAL, "met", None) or {})


def blocks(path: str, paths=None) -> str:
    """Which excluded folder this path is in, or "".

    Compared segment by segment, never as text: `Photos` and `Photos Raw` share
    eight characters and share no folder at all, and an exclusion that also took
    out the tree beside it would be a very quiet way to lose half a library.
    """
    from .paths import under
    path = str(path or "").strip()
    if not path:
        return ""
    for one in (now() if paths is None else paths):
        try:
            if os.path.realpath(path) == os.path.realpath(one):
                return one
        except OSError:
            if os.path.normcase(path) == os.path.normcase(one):
                return one
        if under(path, one):
            return one
    return ""


def said(seen: dict) -> str:
    """One line for a plan's notes. Empty when nothing was actually left out."""
    seen = {k: v for k, v in (seen or {}).items()}
    if not seen:
        return ""
    bits = ", ".join(f"{os.path.basename(k) or k} ({v:,} file(s))"
                     for k, v in sorted(seen.items(), key=lambda kv: -kv[1])[:6])
    more = "" if len(seen) <= 6 else f", and {len(seen) - 6} more"
    total = sum(seen.values())
    return (f"LEFT OUT on purpose: {bits}{more} - {total:,} file(s) were not "
            f"looked at - they are excluded in Setup (Skip everywhere) or on "
            f"this "
            f"flow. Every number above is about the rest of the tree.")
