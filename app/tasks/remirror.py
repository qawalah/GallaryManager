"""Reshape the RAW tree to match whatever the library looks like now.

The library is the truth; the RAW tree follows it. Rename a shoot, move it under
a new parent, split it in two - run this and every RAW lands beside where its own
JPEG now lives. It never edits the library to match the RAWs; that direction only
ever causes arguments.

The whole design turns on one distinction:

    a JPEG that MOVED  and  a JPEG that was DELETED
    look identical to a RAW sitting where its partner used to be.

Since moving is the exact case this task exists for, "not where I left it" can
never mean "delete the RAW". So the entire library is searched by identity
first, and only a RAW whose JPEG is nowhere at all counts as orphaned - and even
then it is put aside, recoverable, never deleted.
"""

from __future__ import annotations

import os
import shutil

from app.registry import Choice, Flag, Folder, Plan, Result, Row, Task, register
from core import moves
from core import walk
from core.pairs import build_index, pair_trees
from core.photo import kind
from core.paths import (CULLED, companions, ensure_folder, relative_under,
                        safe_target, tidy_empty_folders, roots_of, under)

# The two words this tab used without ever saying what they meant. They are
# different problems and the fix for each is different, so they are now spelt
# out wherever they appear.
#
#   STRAY   - a RAW still sitting in the LIBRARY. It HAS its photo; it is simply
#             in the wrong tree, because it was never separated.
#   NO PHOTO - a RAW, anywhere, whose photo is not in the library at all. That is
#             either a shot taken RAW-only, or a photo that has since been culled,
#             filed into a folder this app skips, or deleted.
ORPHAN_CHOICES = [
    ("leave", "Leave them where they are"),
    ("aside", "Move them to _Culled in the RAW tree"),
    ("list", "Only list them"),
]


def _names_everywhere(library: str) -> dict:
    """Every base name under the library, INCLUDING the folders a walk skips.

    Why this exists: a RAW whose photo sits in `_Culled`, in `Developed`, or in
    a folder named in Setup's skip list is not orphaned - the photo is right
    there, in a place this app deliberately does not walk into. Reported as "no
    photo anywhere" it reads as a lost file and invites putting the RAW aside,
    which is the wrong answer to a photo you culled on purpose.

    Names only. No file is opened: this is for EXPLAINING an unmatched RAW, not
    for matching one.
    """
    out: dict = {}
    for here, dirs, names in os.walk(library, onerror=lambda e: None):
        dirs[:] = [d for d in dirs if not d.lower().startswith("@eadir")]
        for name in names:
            if kind(name) not in ("jpeg", "image"):
                continue
            out.setdefault(os.path.splitext(name)[0].lower(), os.path.join(here, name))
    return out


def plan(opts) -> Plan:
    p = Plan(task="remirror")
    library, raw_root = opts["library"], opts["raw"]
    for label, folder in (("library", library), ("RAW tree", raw_root)):
        if not folder or not os.path.isdir(folder):
            p.blocked = f"There is no {label} at {folder!r}"
            return p
    if os.path.realpath(library) == os.path.realpath(raw_root):
        p.blocked = "The library and the RAW tree are the same folder."
        return p

    lib_walk = walk.walk(library)
    raw_walk = walk.walk(raw_root)
    for path, why in lib_walk.errors + raw_walk.errors:
        p.errors.append(f"could not read {path}: {why}")

    # Reading the whole library is the expensive part and also the point: a RAW's
    # JPEG could now be anywhere in it.
    jpegs = build_index(lib_walk.files)

    # A RAW still sitting in the library is a RAW that does not follow its
    # original either - and it was invisible here, because this only ever looked
    # inside the RAW tree. "Re-mirror" then reported a tidy tree while RAWs sat
    # in the library the whole time, which is the one place you would not think
    # to look for a mirroring problem.
    strays = []
    if opts.get("gather_library", True):
        strays = [f for f in lib_walk.files if kind(f) == "raw"]

    # Only these folders, when you say so. The library is still SEARCHED whole -
    # that is what makes "it moved" different from "it is gone" - but only the
    # RAWs you pointed at are judged and moved. Without this the tab was all or
    # nothing: one shoot to re-mirror meant a report about the whole library.
    only = [os.path.abspath(f) for f in
            Folder("only", "").chosen(opts.get("only")) if str(f).strip()]
    matches = pair_trees(list(raw_walk.files) + strays, jpegs)
    from_library = {os.path.normcase(f) for f in strays}
    if only:
        def inside(path):
            return any(under(path, one) for one in only)
        matches = [m for m in matches
                   if inside(m.raw) or (m.jpeg and inside(m.jpeg))]
        p.notes.append("Only the folders you picked were judged: "
                       + ", ".join(os.path.basename(o) or o for o in only)
                       + ". The whole library was still searched, so a RAW whose "
                         "photo moved elsewhere is still found.")

    moved = already = orphaned = ambiguous = hidden = 0
    elsewhere = None                 # names in the folders a walk skips, read once
    for m in matches:
        if m.jpeg:
            rel = relative_under(os.path.dirname(m.jpeg), library)
            target = safe_target(os.path.join(raw_root, rel, os.path.basename(m.raw)))
            if os.path.realpath(os.path.dirname(target)) == os.path.realpath(os.path.dirname(m.raw)):
                already += 1
                continue
            moved += 1
            stray = os.path.normcase(m.raw) in from_library
            p.rows.append(Row(
                what="move", name=os.path.basename(m.raw), source=m.raw, target=target,
                detail=("still in the library - moving it out to follow "
                        if stray else "follows ")
                       + f"{os.path.basename(m.jpeg)}  ({m.how})",
                data={"action": "move", "from": m.raw, "to": target}))
            for side in companions(m.raw):
                side_target = safe_target(os.path.join(raw_root, rel, os.path.basename(side)))
                p.rows.append(Row(
                    what="move", name=os.path.basename(side), source=side,
                    target=side_target,
                    detail=f"travels with {os.path.basename(m.raw)}",
                    data={"action": "move", "from": side, "to": side_target}))
            continue

        if m.candidates > 1:
            ambiguous += 1
            p.skipped.append((m.raw,
                              f"left alone - {m.how}, so which one is a guess"))
            continue

        orphaned += 1
        choice = opts["orphans"]
        # Say WHY, rather than "no JPEG anywhere" for four different causes.
        if elsewhere is None:
            elsewhere = _names_everywhere(library)
        found = elsewhere.get(os.path.splitext(os.path.basename(m.raw))[0].lower(), "")
        if found:
            where = relative_under(os.path.dirname(found), library) or "the library"
            why = (f"its photo is in {where}, which this app does not walk into "
                   f"- culled, developed, or skipped in Setup. Not a lost file.")
            hidden += 1
        else:
            why = "no photo of that name anywhere in the library - a RAW-only shot, "\
                  "or its photo was deleted"
        if choice == "aside":
            rel = relative_under(os.path.dirname(m.raw), raw_root)
            target = safe_target(os.path.join(raw_root, CULLED, rel, os.path.basename(m.raw)))
            p.rows.append(Row(
                what="moved aside", name=os.path.basename(m.raw), source=m.raw, target=target,
                detail=why, approximate=True,
                data={"action": "aside", "from": m.raw, "to": target}))
            for side in companions(m.raw):
                side_target = safe_target(
                    os.path.join(raw_root, CULLED, rel, os.path.basename(side)))
                p.rows.append(Row(
                    what="moved aside", name=os.path.basename(side), source=side,
                    target=side_target, approximate=True,
                    detail=f"travels with {os.path.basename(m.raw)}",
                    data={"action": "aside", "from": side, "to": side_target}))
        else:
            p.skipped.append((m.raw, why))

    p.stats = [
        ("Photos in the library", f"{len(jpegs):,}"),
        ("RAW files found", f"{len(matches):,}"),
        ("Already in the right place", f"{already:,}"),
        ("TO MOVE", f"{moved:,}"),
        ("Files to move, sidecars included", f"{len(p.rows):,}"),
        ("No photo found for them", f"{orphaned:,}"),
        ("...of those, photo is in a skipped folder", f"{hidden:,}"),
        ("Two photos match - left alone", f"{ambiguous:,}"),
        ("Folders unreadable", f"{len(lib_walk.errors) + len(raw_walk.errors):,}"),
    ]
    p.notes.append("The library is never changed. Only the RAW tree is reshaped to match it.")
    p.notes.append("Sidecars travel with their RAW - a .xmp left behind takes the "
                   "rating with it and the RAW reads as unrated from then on.")
    p.notes.append("A RAW is matched to its JPEG by capture time, camera and name - "
                   "not by where it sits - so renaming or moving folders does not break it.")
    p.notes.append(
        "Two different things, said plainly. A STRAY RAW is one still sitting in "
        "the library: it has its photo, it is just in the wrong tree. A RAW with "
        "NO PHOTO is one whose photo is not in the library at all.")
    if orphaned:
        p.notes.append(
            f"{orphaned} RAW(s) matched no photo. The whole library was searched, "
            f"not only where they used to be."
            + (f" {hidden} of them have a photo of the same name in a folder this "
               f"app does not walk into - _Culled, Developed, or one you skip in "
               f"Setup - so those are not lost." if hidden else "")
            + (" A RAW-only shot lands here too, which is why these are left where "
               "they are unless you choose otherwise." if orphaned > hidden else ""))
    if p.errors:
        p.blocked = (f"{len(p.errors)} folder(s) could not be read. A RAW might look "
                     f"orphaned only because its JPEG is in one of them, so nothing "
                     f"will be moved until that is fixed.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    """Move each RAW, then tidy up the folders that emptied out."""
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result

    touched: set[str] = set()
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        src, dst = row.data["from"], row.data["to"]
        status = "OK"
        try:
            if not os.path.exists(src):
                raise FileNotFoundError("it is no longer there")
            # re-checked inside: an earlier move may have taken the name
            dst = moves.shift(result, src, dst)
            touched.add(os.path.dirname(src))
            result.done += 1
        except Exception as exc:            # noqa: BLE001 - one bad file must not stop the rest
            status = result.blame(src, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)

    removed = (tidy_empty_folders(touched, stop_at=roots_of(plan.opts))
               if plan.opts.get("tidy", True) else 0)
    result.stats = [("RAWs moved", f"{result.done:,}"),
                    ("Failed", f"{result.failed:,}"),
                    ("Empty folders tidied", f"{removed:,}")]
    if not result.details:
        result.details.append("Every RAW is now beside where its JPEG lives.")
    return result


register(Task(
    name="remirror",
    line="Make the RAW tree's folders match your photo folders again, after you have reorganised them.",
    verb="Move",
    unit="RAW files",
    undo="Only the position changes - nothing leaves the RAW tree.",
    reads=('library', 'raw'),
    moves_to=('raw',),
    title="Re-mirror RAWs",
    summary="Moves RAW files within the RAW tree so it matches the library's "
            "current shape.",
    icon="mirror",
    # and anything that drifted goes back in step
    parent="unpair",
    tab="Re-mirror RAWs",
    order=28,
    options=[
        Folder("library", "Library", tree=True, setting="library",
               help="The whole library, read only. Every RAW file is matched "
                    "against it, so a photo moved to another shoot is still "
                    "found. To work on one shoot, use Only these folders."),
        Flag("mirror", "Trees from Setup", default=True,
             help="On, the tree boxes below are ignored and the trees come "
                  "from Setup, so files land where every other tool puts "
                  "them. Off, the folders you type below are used for this "
                  "run only. Turning this off does not stop RAW files or "
                  "previews moving."),
        Folder("raw", "RAW tree", tree=True, setting="raw",
               help="The top of the RAW tree. RAW files are moved within it, "
                    "and nothing leaves it."),
        Folder("only", "Only these folders", default="", many=True,
               must_exist=False,
               help="Limits the run to these shoots, in either tree. Blank "
                    "means the whole RAW tree. The library is still searched "
                    "whole, which tells a moved photo from a missing one."),
        Flag("gather_library", "Gather stray RAW files",
             default=True,
             help="Also moves RAW files still sitting in the library beside "
                  "their photos into the RAW tree, at the position their "
                  "photo has now. On by default."),
        Choice("orphans", "Unmatched RAW files", default="leave",
               choices=ORPHAN_CHOICES,
               help="What to do with a RAW file whose photo is not in the "
                    "library. It may be a RAW-only photo, or one whose JPEG "
                    "was culled, developed or sits in a skipped folder. Check "
                    "the list says which. Left alone by default, because a "
                    "RAW-only photo is not a mistake."),
        Flag("tidy", "Tidy empty folders", default=True,
             group="Advanced", advanced=True,
             help="Removes a folder that this run has emptied. Only folders "
                  "this run emptied itself are removed, never a folder that "
                  "still holds anything. On by default."),
    ],
    plan=plan,
    apply=apply,
))
