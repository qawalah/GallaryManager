"""Finding the same photo twice - carefully, because the obvious answers are wrong.

Two ways to define a duplicate, and the difference matters more than it looks.

**Byte-identical** is easy, exact, and nearly useless on its own: a photo copied,
then opened and re-saved by anything at all, is no longer byte-identical, and
that is the case people actually accumulate.

**The same photograph** is the useful question, and it is where every false
positive lives. Two frames of a bracket were shot within one second of each other
on one camera. So were two frames of a burst. Neither is a duplicate, and a rule
that groups by "same camera, same second" would put a bracket in the aside pile
and leave you with one exposure of three. That is unrecoverable in the way that
matters: you would not notice for months.

So the identity used here is the one the rest of the app already trusts - capture
time AND camera AND base name - and the base name is what does the real work.
A copy keeps its name. Bracket and burst frames get consecutive names from the
camera, so they can never collide, whatever they share.

Four rules keep the rest honest:

- **Only within one kind.** A RAW is never compared with a JPEG. Otherwise a RAW
  still sitting beside its JPEG - which shares its time, camera and name exactly,
  because that is what pairing is built on - reads as a duplicate of it.
- **Only within one tree.** A preview is a smaller copy of its original with the
  same name and the same capture time. It is the single most duplicate-looking
  thing in the whole library, and it is not a duplicate.
- **Certain and probable are never mixed.** Identical bytes is a fact. Same
  identity, different bytes, is a judgement, and it is reported separately and
  acted on only if asked.
- **The keeper is chosen by a stated rule**, not by whichever the walk saw first.
  Two runs must agree, and you must be able to predict which file survives
  without running it.

Reading whole files is the expensive part, so nothing is hashed until it has to
be: files are grouped by size first - two files of different sizes cannot be
identical - and only inside a group is anything read, first the two ends and only
then the whole file.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field

from .photo import is_picture, kind, read_capture

ENDS = 65536             # bytes read from each end for the cheap fingerprint
CHUNK = 1024 * 1024

# Names a copy gets given, by Windows, by macOS, by a file manager, by a person.
#
# NOT `_\d+$`. It is tempting - it is what this app's own safe_target appends -
# and it is catastrophic: IMG_1234, DSC_0001 and P1000123 are what every camera
# on earth names its files, so stripping a trailing _number turns an entire card
# into "IMG" and declares all of it one photo. The keeper rule already handles
# the app's own _1 files, because they only ever live in a folder it made.
#
# "copy" needs whitespace in front of it too, or Photocopy.jpg becomes Photo.jpg.
COPY_MARKS = [
    re.compile(r"\s*\(\d+\)$"),                  # photo (1)
    re.compile(r"\s*-\s*copy(\s*\d+)?$", re.I),   # photo - Copy
    re.compile(r"\s+copy(\s*\d+)?$", re.I),       # photo copy 2
]


@dataclass
class Copy:
    """One file that might be a duplicate of another."""
    path: str
    size: int = 0
    mtime: float = 0.0
    kind: str = ""
    name: str = ""
    stem: str = ""
    taken: str = ""          # capture time, as text, or "" if unreadable
    camera: str = ""
    marked: bool = False     # its name looks like a copy's

    @property
    def folder(self) -> str:
        return os.path.dirname(self.path)


@dataclass
class Group:
    """One photo, and every file that is it."""
    keep: Copy
    others: list = field(default_factory=list)
    certain: bool = True
    why: str = ""
    # Why the file in `keep` is the one being kept, in words. The match and the
    # choice are two different questions and answering only the first is how a
    # list of four hundred moves becomes a list you have to take on trust.
    because: str = ""

    @property
    def size(self) -> int:
        return 1 + len(self.others)

    @property
    def wasted(self) -> int:
        return sum(c.size for c in self.others)

    def label(self) -> str:
        return f"{self.keep.name} x{self.size}"


@dataclass
class Found:
    groups: list = field(default_factory=list)
    examined: int = 0
    read: int = 0            # files actually opened and hashed
    bytes_read: int = 0
    unreadable: list = field(default_factory=list)
    skipped: list = field(default_factory=list)

    @property
    def certain(self) -> int:
        return sum(1 for g in self.groups if g.certain)

    @property
    def probable(self) -> int:
        return sum(1 for g in self.groups if not g.certain)

    @property
    def wasted(self) -> int:
        return sum(g.wasted for g in self.groups)


# ------------------------------------------------------------------ the names

def looks_copied(stem: str) -> bool:
    """Does this name carry a copy marker - "(1)", " - Copy", "_2"?"""
    for mark in COPY_MARKS:
        if mark.search(stem):
            return True
    return False


def original_stem(stem: str) -> str:
    """The name with any copy marker taken off, once.

    Deliberately once, not repeatedly: "IMG_1234" is a perfectly ordinary camera
    name and stripping until nothing is left would turn every photo on the card
    into a copy of every other.
    """
    for mark in COPY_MARKS:
        stripped = mark.sub("", stem)
        if stripped and stripped != stem:
            return stripped
    return stem


# ------------------------------------------------------------------ the files

def describe(path: str, read_exif: bool = True) -> Copy | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    name = os.path.basename(path)
    stem = os.path.splitext(name)[0]
    c = Copy(path=path, size=st.st_size, mtime=st.st_mtime, kind=kind(path),
             name=name, stem=stem, marked=looks_copied(stem))
    if read_exif:
        cap = read_capture(path)
        if cap.taken:
            c.taken = cap.taken.strftime("%Y-%m-%d %H:%M:%S")
        c.camera = (cap.model or "").strip()
    return c


def _digest(path: str, whole: bool) -> str:
    """A fingerprint of a file: both ends, or all of it."""
    h = hashlib.sha256()
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        if whole:
            while True:
                block = fh.read(CHUNK)
                if not block:
                    break
                h.update(block)
        else:
            h.update(fh.read(ENDS))
            if size > ENDS * 2:
                fh.seek(-ENDS, os.SEEK_END)
                h.update(fh.read(ENDS))
    return h.hexdigest()


# ---------------------------------------------------------------- the keeper

# Which copy survives. The Windows app offered these and they are the reason
# this port was described as missing something: "it keeps one of them" is not an
# answer you can check, and a library is sorted in several different ways at
# once - a shoot filed properly near the top, a card dump six levels down, an
# export folder full of re-saves with today's date on them. Which of those is
# the original depends on what you were doing, and only you know that.
#
# The order here is the order they are offered in.
RULES = {
    "smart": "The one most like the original",
    "shallowest": "The one nearest the top",
    "deepest": "The one deepest in the tree",
    "oldest": "The oldest file",
    "newest": "The newest file",
    "alpha": "The first path alphabetically",
    "priority": "The one in a listed folder",
}

PUT_ASIDE = ("_culled", "_duplicates", "_nolocation")


def depth_of(path: str) -> int:
    return len([bit for bit in re.split(r"[\\/]", path) if bit])


def rank_in(path: str, prefer) -> int:
    """How high up your list of folders this file sits, or "not on it at all".

    The ORDER of the list is the ranking, so the first folder that contains this
    file wins - even if a later one is a closer match. That is what a list you
    can drag into order means, and the alternative - most specific folder wins -
    makes the answer depend on a rule nobody can see while typing.
    """
    lowered = os.path.normcase(os.path.abspath(path))
    for i, folder in enumerate(prefer or []):
        root = os.path.normcase(os.path.abspath(str(folder).rstrip("/\\")))
        if root and (lowered == root or lowered.startswith(root + os.sep)):
            return i
    return len(prefer or [])


def _score(c: Copy, rule: str = "smart", prefer=None) -> tuple:
    """Lower sorts first, and first is kept. Every part of this is on purpose.

    The rule has to be stated and stable: two runs must agree, and you should be
    able to say which file survives before pressing anything.

    Two things come before whichever rule was chosen, and they come before it in
    every rule:

    - a file already put aside never beats a live one. Otherwise a cull followed
      by a duplicate check quietly reverses the cull - the copy in _Culled wins
      on some rule or other and the one in the library is filed away as its
      duplicate.
    - a folder YOU listed beats one you did not. That is the whole point of the
      list: the app decides by rule, and this is how you overrule it for a
      folder without having to find a rule that happens to agree with you.
    """
    lowered = c.path.lower()
    put_aside = 1 if any(bit in lowered for bit in PUT_ASIDE) else 0
    first = (put_aside, rank_in(c.path, prefer))
    if rule == "shallowest":
        rest = (depth_of(c.path), c.mtime)
    elif rule == "deepest":
        rest = (-depth_of(c.path), c.mtime)
    elif rule == "oldest":
        rest = (c.mtime, depth_of(c.path))
    elif rule == "newest":
        rest = (-c.mtime, depth_of(c.path))
    elif rule == "alpha":
        rest = ()
    elif rule == "priority":
        # The list is already the first thing compared. Below it, the same
        # sensible order as `smart` - a rule that said nothing at all about
        # files in no listed folder would be decided by the walk order.
        rest = (1 if c.marked else 0, c.mtime, len(c.path))
    else:                                   # smart
        rest = (
            1 if c.marked else 0,   # "photo (1)" loses to "photo"
            c.mtime,                # the older file is the original import
            len(c.path),            # then the shorter path - nearer the top
        )
    return first + rest + (c.path.lower(),)   # last, so the answer never wobbles


def kept_because(keep: Copy, others, rule: str = "smart", prefer=None) -> str:
    """Why THIS one, in a sentence - the part a list of duplicates needs most.

    Said from the file that survived, not from the rule: "oldest file" is a
    setting, "kept because it is the oldest - 12 Mar 2019" is an answer.
    """
    if rank_in(keep.path, prefer) < len(prefer or []):
        return "it is in a folder you chose"
    aside = [c for c in others if any(b in c.path.lower() for b in PUT_ASIDE)]
    if aside and not any(b in keep.path.lower() for b in PUT_ASIDE):
        return "the other copy is already moved aside"
    if rule in ("smart", "priority") and keep.marked is False \
            and any(c.marked for c in others):
        return "the others are named like copies"
    if rule == "shallowest":
        return "it is closest to the top of the tree"
    if rule == "deepest":
        return "it is deepest in the tree"
    if rule == "newest":
        return "it is the newest file"
    if rule == "alpha":
        return "it is first alphabetically"
    if rule == "oldest" or rule in ("smart", "priority"):
        return "it is the oldest file"
    return "the stated rule chose it"


def _make_group(copies: list, certain: bool, why: str,
                rule: str = "smart", prefer=None) -> Group:
    ordered = sorted(copies, key=lambda c: _score(c, rule, prefer))
    keep, others = ordered[0], ordered[1:]
    return Group(keep=keep, others=others, certain=certain, why=why,
                 because=kept_because(keep, others, rule, prefer))


# ------------------------------------------------------------- about a folder

def folder_facts(folder: str, cache: dict | None = None) -> dict:
    """How many files this folder holds, and the span of their dates.

    Not how many DUPLICATES - that is the number already on screen, and on its
    own it is misleading in the direction that costs you something. "Nine copies
    here" reads very differently once you know the folder holds nine files and
    nothing else: this is not a folder with some duplicates in it, it is a whole
    folder about to be emptied, and that is worth seeing before pressing rather
    than afterwards.

    Only this folder, not what is under it, because that is the folder the rows
    are talking about. Cheap: one scandir, no file is opened.
    """
    if cache is not None and folder in cache:
        return cache[folder]
    got = {"files": 0, "oldest": 0.0, "newest": 0.0, "readable": True}
    try:
        with os.scandir(folder) as it:
            for entry in it:
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    when = entry.stat(follow_symlinks=False).st_mtime
                except OSError:
                    continue
                got["files"] += 1
                got["oldest"] = when if not got["oldest"] else min(got["oldest"], when)
                got["newest"] = max(got["newest"], when)
    except OSError:
        got["readable"] = False
    if cache is not None:
        cache[folder] = got
    return got


# ------------------------------------------------------------------- finding

def find(paths, *, include_resaved: bool = True, rule: str = "smart",
         prefer=None, progress=None) -> Found:
    """Every set of files that is one photo more than once.

    Built by joining rather than by two separate passes, and that is not a
    detail. Suppose a photo exists three times: the original, a byte-identical
    copy, and a re-saved version. Settle the identical pair first and then look
    at "everything left over" and the re-saved one has nobody to pair with - it
    is a duplicate, of a photo you are holding twice, reported as neither. So
    identical files are joined, then identity joins those groups to each other,
    and one photo comes out as one group however many ways it was copied.

    `include_resaved` turns on the second, judged join: same identity, different
    bytes. It is ON here and the ACTING on it is what the task keeps switched
    off, which is the right way round: something you cannot see is something you
    cannot decide about, and "there are 40 of these, here they are, nothing was
    done" is the whole point of a report. Pass False only to skip the EXIF pass
    when the answer genuinely is not wanted.
    """
    out = Found()

    files = []
    for path in paths:
        if kind(path) not in ("jpeg", "image", "raw"):
            continue
        c = describe(path, read_exif=False)
        if c is None:
            out.unreadable.append(path)
            continue
        files.append(c)
    out.examined = len(files)

    # Union-find over the files: `home[i]` is the group i belongs to.
    home = list(range(len(files)))
    judged = [False] * len(files)          # did a JUDGED link build this group?

    def root(i):
        while home[i] != i:
            home[i] = home[home[i]]
            i = home[i]
        return i

    def join(a, b, certain):
        ra, rb = root(a), root(b)
        if ra != rb:
            home[rb] = ra
        if not certain:
            judged[root(a)] = True
        if judged[ra] or judged[rb]:
            judged[root(a)] = True

    # ---- the fact: identical bytes.
    #
    # Two files of different sizes cannot be identical, so size buckets the work
    # and nothing outside a bucket of two or more is ever opened at all.
    by_size: dict = {}
    for i, c in enumerate(files):
        by_size.setdefault((c.kind, c.size), []).append(i)

    candidates = [g for g in by_size.values() if len(g) > 1]
    done, total = 0, sum(len(g) for g in candidates)
    for group in candidates:
        by_ends: dict = {}
        for i in group:
            done += 1
            if progress:
                progress(done, total, files[i].name)
            try:
                by_ends.setdefault(_digest(files[i].path, False), []).append(i)
                out.read += 1
                out.bytes_read += min(files[i].size, ENDS * 2)
            except OSError:
                out.unreadable.append(files[i].path)
        for maybe in by_ends.values():
            if len(maybe) < 2:
                continue                       # the ends already separate them
            whole: dict = {}
            for i in maybe:
                try:
                    whole.setdefault(_digest(files[i].path, True), []).append(i)
                    out.bytes_read += files[i].size
                except OSError:
                    out.unreadable.append(files[i].path)
            for same in whole.values():
                for other in same[1:]:
                    join(same[0], other, True)

    # ---- the judgement: the same photograph, saved again.
    #
    # Identity, not resemblance: capture time AND camera AND the name with any
    # copy marker taken off. The name is what keeps a bracket safe - its frames
    # share the second and the camera but never the name.
    if include_resaved:
        by_identity: dict = {}
        for i, c in enumerate(files):
            full = describe(c.path, read_exif=True)
            if full is None or not full.taken:
                continue           # no capture time is not evidence of anything
            files[i] = full
            key = (full.kind, full.taken, full.camera.lower(),
                   original_stem(full.stem).lower())
            by_identity.setdefault(key, []).append(i)
        for same in by_identity.values():
            for other in same[1:]:
                if root(same[0]) != root(other):
                    join(same[0], other, False)

    grouped: dict = {}
    for i in range(len(files)):
        grouped.setdefault(root(i), []).append(i)

    for where, members in grouped.items():
        if len(members) < 2:
            continue
        copies = [files[i] for i in members]
        certain = not judged[where]
        if certain:
            why = f"identical - {len(copies)} files, byte for byte the same photo"
        else:
            taken = next((c.taken for c in copies if c.taken), "")
            camera = next((c.camera for c in copies if c.camera), "")
            why = ("same photo, saved again - same name"
                   + (f", taken {taken}" if taken else "")
                   + (f" on {camera}" if camera else "")
                   + ", different file")
        out.groups.append(_make_group(copies, certain, why, rule, prefer))

    out.groups.sort(key=lambda g: (-g.wasted, g.keep.path.lower()))
    return out
