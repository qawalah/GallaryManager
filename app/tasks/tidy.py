"""What is sitting in a library that does not need to be - reported, never touched.

Every feature in this app that decides against a photograph puts it aside rather
than deleting it: a cull into `_Culled`, a duplicate into `_Duplicates`, an
original kept before geotagging into `_NoLocation`. That is the right default and
it has one consequence nobody sees at the time - after a few months of sorting an
old library, a real part of the disk is piles you have already made your mind up
about, scattered beside the shoots they came from rather than in one place.

This is the LOOK at that. It reads like the rest of Library: point it at a tree
and it tells you what is there. It never removes anything - the Clean up tab
does that, deliberately, with a confirmation of its own - and the split is the
point. Deciding what to empty and emptying it are two different moments, and a
page that does both at once is a page you press the wrong button on.

Three kinds of thing, and empty folders are the one worth explaining. They are
what reorganising leaves behind: a year folder whose shoots have all moved out
holds nothing, shows up in every folder picker forever, and no amount of looking
at photographs will ever tell you it is there.
"""

from __future__ import annotations

import os
import time

from app.registry import Flag, Folder, Plan, Result, Row, Task, register
from core import cleanup as C

# The same names Clean up gives the same piles, so the status and the tool
# that empties them call each pile one thing.
KINDS = [("culled", "Culled photos (_Culled)"),
         ("duplicates", "Duplicate copies (_Duplicates)"),
         ("nolocation", "Originals (_NoLocation)")]


def _size(n: int) -> str:
    if n >= 1e9:
        return f"{n / 1e9:.2f} GB"
    if n >= 1e6:
        return f"{n / 1e6:.0f} MB"
    if n >= 1e3:
        return f"{n / 1e3:.0f} KB"
    return f"{n:,} bytes"


def _when(stamp: float) -> str:
    return time.strftime("%d %b %Y", time.localtime(stamp)) if stamp else "unknown"


def _roots(opts) -> list:
    from core.paths import without_nested
    picked = []
    for key in ("folder", "raw", "previews", "develop", "video"):
        for one in str(opts.get(key) or "").splitlines():
            one = one.strip()
            if one and os.path.isdir(one) and one not in picked:
                picked.append(one)
    return without_nested(picked)


def plan(opts, progress=None) -> Plan:
    p = Plan(task="tidy")
    roots = _roots(opts)
    if not roots:
        p.blocked = "Give it a tree to look through."
        return p

    wanted = [key for key, _label in KINDS]
    p.columns = ["Folder", "What it is", "How much", "Size", "Last added to"]

    total_files = total_bytes = 0
    empties = 0
    by_kind: dict = {}
    for n, root in enumerate(roots, 1):
        if progress:
            progress(n, len(roots) + 1, root)
        for pile in C.piles_under(root, wanted):
            label = dict(KINDS).get(pile.kind, pile.kind)
            by_kind[pile.kind] = by_kind.get(pile.kind, 0) + pile.files
            total_files += pile.files
            total_bytes += pile.bytes
            p.rows.append(Row(
                what=pile.kind, name=os.path.basename(pile.path) or pile.path,
                source=pile.path, target="", size=pile.bytes,
                detail=f"{label}: {pile.files:,} file(s), {_size(pile.bytes)}, "
                       f"last added to {_when(pile.newest)}",
                cells=[label, f"{pile.files:,} file(s)", _size(pile.bytes),
                       _when(pile.newest)],
                data={"path": pile.path}))

        if bool(opts.get("empty", True)):
            for folder in C.empty_under(root):
                empties += 1
                p.rows.append(Row(
                    what="empty", name=os.path.basename(folder) or folder,
                    source=folder, target="", size=0,
                    detail="holds nothing at all - what reorganising leaves behind",
                    cells=["Empty folder", "nothing in it", "", ""],
                    data={"path": folder}))

        if bool(opts.get("leftovers")):
            for folder in C.leftovers_under(root):
                p.rows.append(Row(
                    what="litter", name=os.path.basename(folder) or folder,
                    source=folder, target="", size=0,
                    detail="nothing in it but thumbnails and index files other "
                           "software left behind",
                    cells=["Litter only", "no photos", "", ""],
                    data={"path": folder}))

    p.stats = [
        ("Trees looked through", f"{len(roots):,}"),
        ("Piles found", f"{sum(1 for r in p.rows if r.what in dict(KINDS)):,}"),
        ("Photos in them", f"{total_files:,}"),
        ("Space they take", _size(total_bytes)),
        ("Empty folders", f"{empties:,}"),
    ]
    for key, label in KINDS:
        if by_kind.get(key):
            p.stats.append((f"  {label}", f"{by_kind[key]:,}"))

    p.notes.append(
        "Nothing here is touched. This is the look; the Clean up tab is where "
        "any of it is actually emptied, and it asks in a second place before it "
        "does. Deciding what to remove and removing it are two different "
        "moments, and one page that does both is a page you press the wrong "
        "button on.")
    p.notes.append(
        "Only folders this app made are counted - _Culled, _Duplicates, "
        "_NoLocation, by name. A folder you made and called 'old' is not a pile "
        "and is not here.")
    if empties:
        p.notes.append(
            f"{empties} folder(s) hold nothing at all. That is what reorganising "
            f"a library leaves behind - a year whose shoots have all moved out - "
            f"and nothing you can see by looking at photos will ever tell "
            f"you they are there. Clean up removes them.")
    if total_bytes:
        p.notes.append(
            f"{_size(total_bytes)} is sitting in piles you have already decided "
            f"about. Worth knowing before buying a disk.")
    if not p.rows:
        p.notes.append("Nothing moved aside, nothing empty. This tree is tidy.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    result.details.append(
        "This tab only ever looks. Clean up is where any of it is removed.")
    return result


register(Task(
    name="tidy",
    line="What is sitting in piles you have already decided against.",
    reads=('library', 'raw', 'previews', 'develop', 'video'),
    title="Clean-up status",
    summary="Counts, sizes and dates everything in the library you have "
            "already decided against. Nothing is changed.",
    # Not the bin: it sits beside Clean up now, which is the bin, and two tabs
    # with one glyph is a row you have to read.
    icon="inbox",
    parent="cleanup",
    writes=False,
    order=10,
    options=[
        Folder("folder", "Folders to check", setting="library", many=True,
               help="The folders to look through. Piles can be anywhere "
                    "inside them: a _Culled folder sits beside the shoot it "
                    "came from."),
        Flag("empty", "Empty folders", default=True,
             help="Also counts folders with nothing in them, which "
                  "reorganising leaves behind and every folder picker keeps "
                  "showing. On by default."),
        Flag("leftovers", "Thumbnail-only folders",
             default=False,
             help="Also counts folders that hold only system files such as "
                  "@eaDir or Thumbs.db and nothing else. A folder with one "
                  "photo and an @eaDir is left out. Off by default."),
        Folder("raw", "RAW tree", tree=True, default="", must_exist=False,
               setting="raw", group="Other trees", advanced=True,
               help="The top of the RAW tree, so its piles are counted too. "
                    "Culled RAW files are the largest. Blank leaves it out."),
        Folder("previews", "Previews tree", tree=True, default="",
               must_exist=False, setting="previews", group="Other trees",
               advanced=True,
               help="The top of the previews tree, so its piles are counted "
                    "too. Blank leaves it out."),
        Folder("develop", "Develop tree", tree=True, default="",
               must_exist=False, setting="develop", group="Other trees",
               advanced=True,
               help="The top of the develop tree, so its piles are counted "
                    "too. Blank leaves it out."),
        Folder("video", "Video tree", tree=True, default="",
               must_exist=False, setting="video", group="Other trees",
               advanced=True,
               help="The top of the video tree, so its piles are counted "
                    "too. Blank leaves it out."),
    ],
    plan=plan,
    apply=apply,
))
