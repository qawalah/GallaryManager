"""The same photo, more than once - found, explained, and put aside.

Ported from the Windows app, which had it, and rebuilt rather than translated
because the interesting part is not the finding. It is the two ways this feature
can be actively harmful, both of which look like it working:

**It can dismantle a bracket.** Three frames shot within one second on one camera
are not three copies of one photo. Group by "same camera, same second" and a
bracket goes into the aside pile as duplicates, leaving one exposure of three -
and you find out months later, if at all. The defence is that identity includes
the base NAME, and a camera never gives two frames the same name.

**It can decide a preview, or a RAW, is a copy of its original.** A preview is a
smaller version of a photo with the same name and the same capture time. A RAW is
tied to its JPEG by capture time, camera and name - that is precisely how pairing
works. Both are the most duplicate-looking things in the library and neither is a
duplicate. The defences are that this only ever compares files of the same kind,
and only ever walks one tree.

What it will not do: delete anything, or decide for you. Identical bytes is a
fact and is reported as certain. Same identity with different bytes is a
judgement, is reported separately, and is left alone unless you ask for it.
"""

from __future__ import annotations

import os
import shutil

import time

from app.registry import (Choice, Flag, Folder, Folders, Plan, Result, Row, Task,
                          register)
from core import moves
from core import duplicates as D
from core import walk
from core.paths import (DUPLICATES, companions, ensure_folder, relative_under,
                        safe_target, tidy_empty_folders, roots_of, under)


def _aside(path: str, tree_root: str) -> str:
    """Where a copy goes: _Duplicates, at the position it had."""
    rel = relative_under(path, tree_root)
    return safe_target(os.path.join(tree_root, DUPLICATES, rel))


def _short(folder: str, root: str) -> str:
    """A folder said the way a person would say it - from the scan down."""
    if not folder:
        return ""
    rel = relative_under(folder, root) if under(folder, root) else folder
    return rel or os.path.basename(root) or root


def _size(n: int) -> str:
    """Bytes as something readable, and never as "0 MB" - a heading that says a
    folder is about to lose nothing is a heading that gets ignored."""
    if n >= 1e9:
        return f"{n / 1e9:.2f} GB"
    if n >= 1e6:
        return f"{n / 1e6:.0f} MB"
    if n >= 1e3:
        return f"{n / 1e3:.0f} KB"
    return f"{n:,} bytes"


def _when(stamp: float) -> str:
    return time.strftime("%b %Y", time.localtime(stamp)) if stamp else ""


def _describe_folder(folder: str, root: str, cache: dict) -> str:
    """"12 files, Mar 2019 to Jul 2022" - the folder, not just its duplicates."""
    facts = D.folder_facts(folder, cache)
    if not facts["readable"]:
        return "could not be read"
    first, last = _when(facts["oldest"]), _when(facts["newest"])
    span = first if first == last else f"{first} to {last}"
    return f"{facts['files']:,} file(s)" + (f", {span}" if first else "")


def _pile_root(scan: str, opts) -> str:
    """The top of the tree `scan` is in: where `_Duplicates` is built.

    At the top, like Cull's `_Culled`, rather than inside whichever subfolder
    was scanned. Checking one shoot and then the whole library used to leave
    two piles, one of them buried in the shoot where Clean up and the next
    scan both had to find it.
    """
    from core import settings as _settings
    saved = _settings.load()
    best, deepest = "", -1
    for key in ("library", "raw", "previews", "develop"):
        root = str(opts.get(key) or saved[key] or "").strip()
        if not root or not os.path.isdir(root) or not under(scan, root):
            continue
        if len(os.path.abspath(root)) > deepest:
            best, deepest = root, len(os.path.abspath(root))
    return best or scan


def plan(opts, progress=None) -> Plan:
    p = Plan(task="duplicates")
    scan = (opts.get("folder") or "").strip()
    if not scan or not os.path.isdir(scan):
        p.blocked = f"There is no folder at {scan!r}"
        return p

    # One tree at a time, always. A preview has its original's name and its
    # original's capture time; a RAW is tied to its JPEG by exactly the identity
    # this task matches on. Walking two trees together would find hundreds of
    # "duplicates", every one of them a pair that is supposed to exist.
    others = []
    for key, label in (("raw", "the RAW tree"), ("previews", "the previews tree"),
                       ("develop", "the develop tree")):
        root = (opts.get(key) or "").strip()
        if not root or not os.path.isdir(root):
            continue
        # The tree being scanned is not "another" tree. Its help has always
        # said the RAW tree can be checked on its own, and `under` is true of a
        # folder and itself, so pointing it at the RAW tree was refused.
        if os.path.realpath(root) == os.path.realpath(scan):
            continue
        if under(root, scan) or under(scan, root):
            others.append((os.path.realpath(root), label))
    if any(under(scan, root) for root, _ in others):
        p.blocked = ("That folder is inside the RAW or previews tree. Run this on one "
                     "tree at a time: a preview has its original's name and capture "
                     "time, so comparing the two trees together finds hundreds of "
                     "'duplicates' that are all pairs which are supposed to exist.")
        return p

    found_files = walk.walk(scan)
    for path, why in found_files.errors:
        p.errors.append(f"could not read {path}: {why}")

    keep = []
    inside = 0
    for path in found_files.files:
        real = os.path.realpath(path)
        if any(real.startswith(root + os.sep) for root, _ in others):
            inside += 1
            continue
        keep.append(path)
    if inside:
        p.notes.append(f"{inside:,} file(s) were left out because they are in "
                       f"{' or '.join(label for _r, label in others)}, which sits "
                       f"inside the folder being scanned. A preview is not a copy "
                       f"of its original, and a RAW is not a copy of its JPEG.")

    # Always LOOK for both kinds. The option decides what is acted on, not what
    # is examined: a set you cannot see is a set you cannot make a decision
    # about, and this is the tier that needs a human to read it.
    rule = str(opts.get("keep") or "smart")
    prefer = Folders.chosen(opts.get("prefer"))
    got = D.find(keep, rule=rule, prefer=prefer,
                 progress=(lambda i, n, name: progress(i, n, name, "OK"))
                 if progress else None)
    for path in got.unreadable:
        p.errors.append(f"could not read {path}")

    # Gathered by the pair of folders, because that is what the decision
    # actually is. Four hundred rows of "this copy loses to that one" are, in a
    # real library, a dozen judgements repeated: this card dump against that
    # shoot, over and over. Seeing them as a dozen is what makes it possible to
    # disagree with one of them - and the folders are named on the heading, both
    # of them, so you never have to open a row to find out which two.
    pile = _pile_root(scan, opts)
    facts: dict = {}
    pairs: dict = {}
    moved = 0
    for group in got.groups:
        why = group.why
        for copy in group.others:
            if not bool(opts.get("resaved")) and not group.certain:
                continue
            aside = _aside(copy.path, pile)
            key = f"{group.keep.folder}\x00{copy.folder}"
            pair = pairs.get(key)
            if pair is None:
                pair = pairs[key] = {"keep": group.keep.folder,
                                     "copy": copy.folder, "rows": 0,
                                     "bytes": 0, "why": group.because}
            pair["rows"] += 1
            pair["bytes"] += copy.size
            p.rows.append(Row(
                what="duplicate" if group.certain else "probable duplicate",
                name=copy.name, source=copy.path, target=aside, size=copy.size,
                detail=f"{why}; keeping {group.keep.path} - {group.because}",
                cells=[why, os.path.basename(group.keep.path), group.because],
                group=key,
                data={"from": copy.path, "to": aside}))
            moved += 1
            for side in companions(copy.path):
                p.rows.append(Row(
                    what="sidecar", name=os.path.basename(side), source=side,
                    target=_aside(side, pile), size=0,
                    detail="travels with its file", group=key,
                    data={"from": side, "to": _aside(side, pile)}))

    # Copies, as the button's unit says. Their sidecars are rows too, and
    # counting those made one copy with an .xmp read as two.
    # The RAW, previews and develop boxes are only there to be LEFT OUT, so
    # the generic reading of them as destinations ("into: The RAW tree") was
    # the opposite of true. The one place anything goes is the pile.
    p.impact = {"count": moved,
                "into": [{"label": "Moved aside in",
                          "path": os.path.join(pile, DUPLICATES)}]}

    for key, pair in sorted(pairs.items(),
                            key=lambda kv: (-kv[1]["rows"], kv[0])):
        keeps, loses = pair["keep"], pair["copy"]
        p.groups.append({
            "key": key,
            # BOTH folders on the heading, always. "12 duplicates" tells you
            # nothing you can act on; "card dump versus 2022/Spain" is the
            # actual question, and it is the same question for every row
            # underneath - which is why they are one heading and not twelve.
            "label": f"{_short(loses, scan)}  vs  {_short(keeps, scan)}",
            "note": f"{pair['rows']} copy(s) in {_short(loses, scan)}, "
                    f"kept instead in {_short(keeps, scan)}",
            "cells": [
                f"{pair['rows']} copy(s), {_size(pair['bytes'])}",
                _short(keeps, scan) + " - " + _describe_folder(keeps, scan, facts),
                pair["why"],
                _short(loses, scan) + " - " + _describe_folder(loses, scan, facts),
                DUPLICATES,
            ],
            # The app has already chosen, by a rule you can read. This is where
            # you say it chose wrong, for THIS pair of folders, without finding
            # a rule that happens to agree with you: the folder goes on the
            # list that wins, and everything is worked out again from scratch.
            "actions": [
                {"label": f"Keep {os.path.basename(keeps) or keeps} instead",
                 "option": "prefer", "value": keeps,
                 "help": "Already the one being kept here - adding it makes that "
                         "the answer everywhere, whatever the rule says."},
                {"label": f"Keep {os.path.basename(loses) or loses} instead",
                 "option": "prefer", "value": loses,
                 "help": "Puts this folder at the top instead: its files are kept "
                         "and the ones in the other folder become the copies."},
            ],
        })

    # Only the sets nothing will be done with are listed here - the rows above
    # already say, file by file, what is moving and which copy is being kept.
    # A "left alone" list that also repeats the things being acted on trains you
    # to skim it, and this is the one list worth reading properly.
    for group in got.groups[:200]:
        if group.certain or bool(opts.get("resaved")):
            continue
        p.skipped.append((group.label(),
                          f"probable: {group.why}. Would keep {group.keep.name} in "
                          f"{group.keep.folder} - would move aside: "
                          + ", ".join(c.name + " in " + c.folder
                                      for c in group.others)))

    read_mb = got.bytes_read / 1e6
    p.columns = ["File", "Why it is a copy", "Kept instead", "Why that one"]
    p.stats = [
        ("Files examined", f"{got.examined:,}"),
        ("Sets of duplicates", f"{len(got.groups):,}"),
        ("  identical, byte for byte", f"{got.certain:,}"),
        ("  same photo saved again", f"{got.probable:,}"
         + ("" if opts.get("resaved") else " (reported only)")),
        ("Copies to move aside", f"{moved:,}"),
        ("Space they take", f"{got.wasted / 1e9:.2f} GB" if got.wasted > 1e9
         else f"{got.wasted / 1e6:.0f} MB"),
        ("Read to be sure", f"{read_mb / 1000:.1f} GB" if read_mb > 1000
         else f"{read_mb:.0f} MB"),
        ("Folders unreadable", f"{len(found_files.errors):,}"),
    ]
    p.notes.append("Nothing is deleted. A copy moves into a _Duplicates folder "
                   "inside this tree, keeping its position, so putting one back is "
                   "a move.")
    p.notes.append(
        f"Which file is KEPT: {D.RULES.get(rule, rule).lower()}. Two things come "
        f"first whatever the rule - a file already moved aside never beats a live "
        f"one, and a folder on your list beats one that is not - and the path "
        f"decides any remaining tie, so two runs can never disagree.")
    if prefer:
        p.notes.append(
            f"{len(prefer)} folder(s) are on the list that wins, in that order. "
            f"Every heading below offers both of its folders, so disagreeing with "
            f"a choice is one click and then the whole thing is worked out again.")
    else:
        p.notes.append(
            "Nothing has been named as the folder that wins. Each heading below "
            "names both folders and offers to keep either one - pick a folder "
            "there and it is added to that list, which is a setting you can see "
            "rather than a decision that happened once.")
    p.notes.append("A bracket is not a set of duplicates. Its frames share a second "
                   "and a camera but never a name, and the name is part of what is "
                   "matched here - which is why 'same camera, same second' is not.")
    if got.probable and not opts.get("resaved"):
        p.notes.append(f"{got.probable} set(s) look like the same photo saved again - "
                       f"same capture time, same camera, same name, different bytes. "
                       f"They are listed below and nothing was done with them. Tick "
                       f"the box to include them once you have read the list.")
    if not got.groups:
        p.notes.append("Nothing in that folder appears twice.")
    if p.errors:
        p.blocked = (f"{len(p.errors)} file(s) or folder(s) could not be read. "
                     f"\"These are the duplicates\" is a claim about the whole tree; "
                     f"part of it was invisible, so nothing will be moved.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result

    touched: set = set()
    freed = 0
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        src, dst = row.data["from"], row.data["to"]
        status = "OK"
        try:
            if not os.path.exists(src):
                raise FileNotFoundError("it is no longer there")
            dst = moves.shift(result, src, dst)
            touched.add(os.path.dirname(src))
            freed += row.size
            result.done += 1
        except Exception as exc:                    # noqa: BLE001
            status = result.blame(src, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)

    removed = (tidy_empty_folders(touched, stop_at=roots_of(plan.opts))
               if plan.opts.get("tidy", True) else 0)
    result.reclaimed, result.reclaim_kind = freed, "aside"
    result.stats = [("Copies moved aside", f"{result.done:,}"),
                    ("Space freed", f"{freed / 1e9:.2f} GB" if freed > 1e9
                     else f"{freed / 1e6:.0f} MB"),
                    ("Failed", f"{result.failed:,}"),
                    ("Empty folders tidied", f"{removed:,}")]
    if not result.details:
        result.details.append(
            f"Every copy is in a {DUPLICATES} folder inside this tree, at the "
            f"position it had. Nothing was deleted, and one of each set was left "
            f"exactly where it was.")
    return result


register(Task(
    name="duplicates",
    fold_groups=True,
    line="The same photo twice: identical copies for certain, re-saved ones "
         "if you ask.",
    verb="Move aside",
    unit="copies",
    undo="They are moved into a pile, not deleted. Clean up is the "
         "only tool that finally removes them, and it tells you how "
         "much came back.",
    reads=('library', 'raw', 'previews'),
    moves_to=('library', 'raw'),
    title="Find duplicates",
    summary="Finds the same photo stored twice and moves the spare copies "
            "into a _Duplicates folder.",
    icon="copy",
    parent="cull",
    tab="Find duplicates",
    order=48,
    options=[
        Folder("folder", "Folder to check", setting="library",
               help="One tree at a time: the library or the RAW tree. Never "
                    "a folder that holds both, because a RAW file shares its "
                    "JPEG's capture time, camera and name, so the pair would "
                    "count as duplicates."),
        Choice("keep", "Which copy to keep", default="smart",
               choices=[(k, v) for k, v in D.RULES.items()],
               group="Which to keep",
               help="The rule that decides which copy stays in place. 'The "
                    "one most like the original' prefers a name without a "
                    "copy marker, then the oldest file, then the shortest "
                    "path."),
        Folders("prefer", "Folders that win", default="",
                group="Which to keep",
                help="Folders whose copy is kept, in order. A file in the "
                     "first folder beats a file in the second, and both beat "
                     "a file in neither, whatever the rule above says. In "
                     "the results, each heading offers its two folders, and "
                     "picking one adds it here."),
        Flag("resaved", "Include re-saved copies", default=False,
             group="Matching",
             help="Also moves copies that are not identical files but have "
                  "the same capture time, camera and name, such as a photo "
                  "re-saved by another program. These are always listed. "
                  "This decides whether they are moved, so read the list "
                  "first. Off by default."),

        Folder("raw", "RAW tree", tree=True, default="", must_exist=False, setting="raw",
               group="Advanced", advanced=True,
               help="The top of the RAW tree. Only used to leave it out when "
                    "it sits inside the folder being checked."),
        Folder("previews", "Previews tree", tree=True, default="", must_exist=False,
               setting="previews", group="Advanced", advanced=True,
               help="The top of the previews tree. Only used to leave it out "
                    "when it sits inside the folder being checked."),
        Folder("develop", "Develop tree", tree=True, default="", must_exist=False,
               setting="develop", group="Advanced", advanced=True,
               help="The top of the develop tree. Only used to leave it out. "
                    "Everything in it is a copy of a library photo on "
                    "purpose, so every file there would count as a "
                    "duplicate."),
        Flag("tidy", "Tidy empty folders", default=True,
             group="Advanced", advanced=True,
             help="Removes a folder that this run has emptied. Only folders "
                  "this run emptied itself are removed, never a folder that "
                  "still holds anything. On by default."),
    ],
    plan=plan,
    apply=apply,
))
