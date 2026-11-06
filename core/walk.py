"""Walking a folder tree, and admitting what could not be read.

A folder that cannot be opened is reported, never skipped silently. "These are
the photos" is a claim about a whole tree; if part of it was invisible the claim
was never true, and anything acting on it should be able to refuse.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import exclude
from .paths import is_ours, skip_folder

JUNK = {"thumbs.db", ".ds_store", "desktop.ini"}


@dataclass
class Walk:
    files: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    folders: int = 0
    # Folders this walk turned back at because they are excluded, and how many
    # files were in each. A tree that is quietly smaller than you think is how
    # "0 of 400 geotagged" becomes a number nobody can act on.
    left_out: dict = field(default_factory=dict)


def walk(root: str, skip_names: set[str] | None = None,
         include_junk: bool = False, include_ours: bool = False) -> Walk:
    """Every file under `root`.

    The folders this app made - _Culled, _NoLocation, _Duplicates - are skipped
    unless asked for. They hold copies of things already in the tree, and walking
    them means a photo put aside last week gets examined again, re-mirrored, or
    backed up a second time. Pass include_ours=True to look inside them on purpose.

    So are the folders excluded in Setup or on the flow being run - by PATH, not
    by name (`core/exclude.py`). Every one actually met is recorded, with how
    many files were inside it, so the plan can say what it did not look at
    rather than simply reporting a smaller library.
    """
    out = Walk()
    skip = {s.lower() for s in (skip_names or set())}
    away = exclude.now()
    if away and exclude.blocks(root, away):
        # The whole tree is inside something excluded. Said rather than
        # returning an empty walk, which looks exactly like an empty folder.
        exclude.met(exclude.blocks(root, away), 0)
        out.left_out[exclude.blocks(root, away)] = 0
        return out
    for here, dirs, names in os.walk(root, onerror=lambda e: out.errors.append(
            (getattr(e, "filename", root), e.strerror or "unreadable"))):
        dirs[:] = [d for d in dirs
                   if d.lower() not in skip
                   and not (skip_folder(d) and not (include_ours and is_ours(d)))]
        if away:
            keep = []
            for d in dirs:
                where = os.path.join(here, d)
                hit = exclude.blocks(where, away)
                if hit:
                    n = _count_under(where)
                    out.left_out[hit] = out.left_out.get(hit, 0) + n
                    exclude.met(hit, n)
                else:
                    keep.append(d)
            dirs[:] = keep
        out.folders += 1
        for n in names:
            if not include_junk and n.lower() in JUNK:
                continue
            out.files.append(os.path.join(here, n))
    out.files.sort()
    return out


def _count_under(root: str) -> int:
    """How many files are in a folder that is about to be skipped.

    Counted rather than left blank because "left out Mobile" and "left out
    Mobile - 12,406 files" are different sentences, and only the second one
    explains why a number further up the page looks wrong. It is stats, not
    reads, and it happens once per excluded folder rather than per file.
    """
    n = 0
    for _here, _dirs, names in os.walk(root, onerror=lambda e: None):
        n += len(names)
    return n
