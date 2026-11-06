"""Emptying the piles this app makes - the one place where things really go.

Every other feature in this app moves. A cull moves low-rated photographs into
`_Culled`, a duplicate check moves copies into `_Duplicates`, a geotag keeps the
un-located original in `_NoLocation`; nothing is ever deleted, and putting one
back is a move. That is the right default and it has one consequence: after a
few months of tidying an old library, a good part of the disk is piles.

So this is the feature that ends them, and it is the only one that can lose a
photograph. Four things follow from that, and they are the whole design:

**It only ever removes what this app put there.** A folder is a candidate
because its NAME is one of ours - `_Culled`, `_Duplicates`, `_NoLocation` - not
because of what is in it, and never because it looks unimportant. A folder you
made and called `old stuff` is not this feature's business at any setting.

**It measures before it offers.** "Delete the culled folders" with no numbers
beside it is a button nobody can make an informed decision about. Each pile is
counted and sized and dated first, so the list says "142 files, 2.1 GB, put
aside in March" and you can tell the forgotten pile from this morning's mistake.

**Age is a setting, because the mistake has a shape.** The pile you regret
deleting is the one from twenty minutes ago, when the cull was wrong and you had
not noticed yet. A pile from last spring is one you have lived without.

**The recycle bin, where there is one.** DSM gives each share a `#recycle`
folder, and a file moved there is recoverable by hand from File Station for as
long as the share's policy keeps it. Where that exists, moving into it is
strictly better than unlinking and costs nothing, because it is a rename on the
same volume.

Nothing here deletes. This module finds, measures and explains; the task decides
and its apply does the work, which is also what makes all of this testable
without a single file being at risk.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from .paths import CULLED, DUPLICATES, LEFTOVERS, NO_LOCATION

# The piles, by the name this app gives them. Keyed by the option that offers
# each one, so the task and this module cannot drift apart over a spelling.
PILES = {
    "culled": CULLED,
    "duplicates": DUPLICATES,
    "nolocation": NO_LOCATION,
}

RECYCLE = "#recycle"

# Never walked into. The Recycle Bin already holds what was deleted, and
# listing its piles again would count them twice and, with the bin ticked off,
# delete them from the one place they could still be got back from. `@eaDir`
# is DSM's index of the folder above it, not a place anybody put a pile.
NOT_WALKED = {"#recycle", "@recycle", "@eadir"}


def _walk(root: str):
    """os.walk from the top, never into the Recycle Bin or DSM's index."""
    for here, dirs, files in os.walk(root, onerror=lambda e: None):
        seen = list(dirs)
        dirs[:] = [d for d in dirs if d.strip().lower() not in NOT_WALKED]
        yield here, seen, dirs, files


def is_litter(folder: str, entries=None) -> bool:
    """Nothing in this folder but other software's thumbnails and index files.

    `@eaDir` counts here, because Thumbnail-only folders is something you ask
    for by name. The Recycle Bin never does: a folder holding one is holding
    everything anybody deleted from that share.
    """
    if entries is None:
        try:
            entries = os.listdir(folder)
        except OSError:
            return False
    if not entries:
        return False
    names = [e.strip().lower() for e in entries]
    return all(n in LEFTOVERS and n not in ("#recycle", "@recycle")
               for n in names)


@dataclass
class Pile:
    """One folder this app put aside, measured."""
    path: str
    kind: str = ""            # the option it came from: culled / duplicates / ...
    files: int = 0
    bytes: int = 0
    oldest: float = 0.0
    newest: float = 0.0
    folders: int = 0
    unreadable: int = 0

    @property
    def age_days(self) -> float:
        """How long since anything was PUT here - not since it was made.

        The newest file is the right clock. A `_Culled` folder made a year ago
        and added to this morning is this morning's pile, and deleting it
        because the folder is old is exactly the mistake worth avoiding.
        """
        if not self.newest:
            return 0.0
        return max(0.0, (time.time() - self.newest) / 86400.0)


def measure(folder: str) -> Pile:
    """Everything under this folder, counted, sized and dated. Nothing opened."""
    pile = Pile(path=folder)
    # Everything, @eaDir included: the whole folder goes, so the whole of it
    # is what it costs.
    for here, dirs, names in os.walk(folder, onerror=lambda e: None):
        pile.folders += len(dirs)
        for name in names:
            try:
                st = os.stat(os.path.join(here, name))
            except OSError:
                pile.unreadable += 1
                continue
            pile.files += 1
            pile.bytes += st.st_size
            pile.oldest = (st.st_mtime if not pile.oldest
                           else min(pile.oldest, st.st_mtime))
            pile.newest = max(pile.newest, st.st_mtime)
    return pile


def piles_under(root: str, wanted) -> list:
    """Every pile of the wanted kinds inside this tree, measured.

    The top-most one only: a `_Culled` folder inside a `_Duplicates` folder is
    already counted by the one above it, and offering both would let you tick
    one, delete the other, and wonder where it went.
    """
    names = {PILES[k].lower(): k for k in (wanted or []) if k in PILES}
    if not names:
        return []
    out = []
    for here, _seen, dirs, _files in _walk(root):
        keep = []
        for name in sorted(dirs):
            kind = names.get(name.strip().lower())
            if kind is None:
                keep.append(name)
                continue
            pile = measure(os.path.join(here, name))
            pile.kind = kind
            out.append(pile)
            # not into it: everything below is part of THIS pile
        dirs[:] = keep
    return out


def leftovers_under(root: str) -> list:
    """Folders that hold nothing but somebody else's litter.

    `@eaDir`, `Thumbs.db`, `.DS_Store` - thumbnails and indexes other software
    leaves behind. A folder with one photograph AND an @eaDir is not litter and
    is not listed: the test is that there is nothing of yours in it at all.
    """
    out = []
    for here, seen, _dirs, files in _walk(root):
        if here == root:
            continue
        if is_litter(here, files + seen):
            out.append(here)
    # Deepest first, as before: the order rows are listed and removed in.
    out.sort(key=lambda p: p.count(os.sep), reverse=True)
    return out


def empty_under(root: str) -> list:
    """Folders holding nothing at all, deepest first.

    Deepest first so that a year folder whose only shoot folder is empty is
    itself empty by the time it is looked at - which is the shape a reorganised
    library actually leaves behind.
    """
    found = [(here, seen, files) for here, seen, _dirs, files in _walk(root)]
    out, empty = [], set()
    for here, dirs, files in sorted(found, key=lambda f: f[0].count(os.sep),
                                    reverse=True):
        if here == root or files:
            continue
        # A folder whose only contents are folders that are themselves empty is
        # empty. Walking upward is what turns "the shoot folder is empty" into
        # "so is the year above it", which is what reorganising a library
        # actually leaves behind. A folder holding the Recycle Bin or an
        # @eaDir is not empty: neither is ever walked, so neither is in `empty`.
        if all(os.path.join(here, d) in empty for d in dirs):
            out.append(here)
            empty.add(here)
    return out


def recycle_root(path: str) -> str:
    """The share's `#recycle` folder, if this path is on a share that has one.

    DSM makes one per share when the recycle bin is turned on, at the top of the
    share. Walking up to find it is how a file five folders down still ends up
    somewhere you can get it back from - and a missing one is a plain "no",
    never a folder this app creates itself. Creating it would be making
    something that looks like DSM's recycle bin and is not: nothing would ever
    empty it, and it would grow forever.
    """
    here = os.path.abspath(path)
    seen = set()
    while here and here not in seen:
        seen.add(here)
        candidate = os.path.join(here, RECYCLE)
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return ""


def recycle_target(path: str, bin_folder: str) -> str:
    """Where inside the recycle bin this folder or file goes.

    Named for where it came from, because a recycle bin holding forty folders
    all called `_Culled` is a recycle bin you cannot recover anything from. The
    date makes two cleanups of the same folder distinguishable.
    """
    stamp = time.strftime("%Y-%m-%d %H%M")
    # Said from the share down, not from the root of the disk: "Photos - 2022 -
    # Spain - _Culled" is a name you can read in File Station, and
    # The whole shared prefix on every row is the same thing with the part
    # you already know taking up the width of the window.
    here = os.path.abspath(path)
    share = os.path.dirname(os.path.abspath(bin_folder))
    if here.startswith(share + os.sep):
        here = here[len(share) + 1:]
    flat = here.strip(os.sep).replace(os.sep, " - ")
    # A path can be longer than any filesystem allows a name to be; the tail is
    # the part that says which folder this was.
    if len(flat) > 150:
        flat = "..." + flat[-150:]
    return os.path.join(bin_folder, f"{stamp} {flat}")
