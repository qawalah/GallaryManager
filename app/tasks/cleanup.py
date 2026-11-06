"""Clean up - the only feature in this app that really removes something.

Everything else moves. A cull moves low-rated photographs into `_Culled`, a
duplicate check moves copies into `_Duplicates`, a geotag keeps the un-located
original in `_NoLocation`, and putting any of them back is a move. That is the
right default, and after a few months of sorting an old library it means a good
part of the disk is piles you have already decided about.

This ends them, and being the one thing that can lose a photograph it is built
differently from every other tab:

- **it only removes what this app put there**, by folder NAME, never by looking
  at a folder and judging it unimportant;
- **it counts, sizes and dates every pile first**, because "delete the culled
  folders" with no numbers beside it is not a decision anybody can make;
- **it will not do anything until you say so in a second place.** Every other
  task shows a plan and offers Apply. This one shows the plan and withholds
  the button until "Yes - actually delete" is ticked, and says so;
- **it uses DSM's recycle bin where there is one**, which turns the whole thing
  into a rename you can undo from File Station.

Age is a setting because the mistake has a shape: the pile anybody regrets
emptying is this morning's, from the cull that was wrong before you noticed. A
pile from last spring is one you have already lived without.
"""

from __future__ import annotations

import os
import shutil
import time

from app.registry import Flag, Folder, Number, Plan, Result, Row, Task, register
from core import moves
from core import cleanup as C
from core.paths import ensure_folder, safe_target, under

WHAT = [
    ("culled", "Culled photos (_Culled)"),
    ("duplicates", "Duplicate copies (_Duplicates)"),
    ("nolocation", "Originals (_NoLocation)"),
]


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
    """The trees to clean, without repeats and without one inside another."""
    from core.paths import without_nested
    picked = []
    for key in ("folder", "raw", "previews", "develop"):
        for one in str(opts.get(key) or "").splitlines():
            one = one.strip()
            if one and os.path.isdir(one) and one not in picked:
                picked.append(one)
    return without_nested(picked)


def plan(opts, progress=None) -> Plan:
    p = Plan(task="cleanup")
    roots = _roots(opts)
    if not roots:
        p.blocked = "Nothing to clean - give it a folder that is actually there."
        return p

    wanted = [key for key, _label in WHAT if bool(opts.get(key))]
    days = float(opts.get("older_than") or 0)
    confirmed = bool(opts.get("confirm"))
    recycle = bool(opts.get("recycle"))

    # The plan is a report until you say otherwise, IN A SECOND PLACE. Every
    # other task in this app puts things aside, so Apply is recoverable; here
    # it is not, and a button that reads the same in both cases is the whole
    # problem with dangerous buttons.
    p.writes = confirmed

    bins: dict = {}
    if recycle:
        for root in roots:
            found = C.recycle_root(root)
            if found:
                bins[root] = found
        if not bins:
            p.notes.append(
                "No #recycle folder was found above any of these, so there is "
                "nothing to move into. DSM makes one per share when the recycle "
                "bin is turned on for it - Control Panel > Shared Folder > Edit "
                "> Enable Recycle Bin. Until then this would delete outright, so "
                "untick it if that is what you want.")
            p.blocked = ("The recycle bin was asked for and there is not one. "
                         "Turn it on for the share in DSM, or untick it here - "
                         "but not silently, because the difference is whether "
                         "any of this can be undone.")
            return p
        # Some trees on a share with a bin and some on one without: the ones
        # without are refused, not quietly deleted. Asking for the bin and
        # getting a permanent delete for half of it is the worst of both.
        for root in [r for r in roots if r not in bins]:
            p.errors.append(
                f"Not cleaned: {root} - its share has no Recycle Bin, and the "
                f"recycle bin was asked for. Turn it on for that share in DSM, "
                f"or untick it to delete outright.")
        roots = [r for r in roots if r in bins]

    total_files = total_bytes = 0
    young = 0
    for root in roots:
        if progress:
            progress(len(p.rows), len(p.rows) + 1, root, "OK")
        for pile in C.piles_under(root, wanted):
            if pile.files == 0 and pile.folders == 0:
                where = _target(pile.path, root, bins)
                p.rows.append(Row(
                    what="empty pile", name=os.path.basename(pile.path),
                    source=pile.path, target=where,
                    detail="an empty folder this app made and never filled, "
                           + _going(where),
                    cells=["nothing in it", "", ""],
                    data={"path": pile.path, "to": where, "tree": True}))
                continue
            if days and pile.age_days < days:
                young += 1
                p.skipped.append((
                    pile.path,
                    f"something was put here {pile.age_days:.1f} day(s) ago, and "
                    f"you asked for piles that have been sitting for {days:.0f}. "
                    f"{pile.files:,} file(s), {_size(pile.bytes)}."))
                continue
            where = _target(pile.path, root, bins)
            total_files += pile.files
            total_bytes += pile.bytes
            p.rows.append(Row(
                what=pile.kind, name=os.path.basename(pile.path),
                source=pile.path, target=where, size=pile.bytes,
                detail=f"{pile.files:,} file(s), {_size(pile.bytes)}, last added "
                       f"to {_when(pile.newest)}, {_going(where)}",
                cells=[f"{pile.files:,} file(s)", _size(pile.bytes),
                       f"{_when(pile.oldest)} to {_when(pile.newest)}"],
                data={"path": pile.path, "to": where, "tree": True,
                      "files": pile.files}))
            if pile.unreadable:
                p.errors.append(f"{pile.unreadable} file(s) in {pile.path} could "
                                f"not be read, so its size is a guess")

        if bool(opts.get("leftovers")):
            for folder in C.leftovers_under(root):
                where = _target(folder, root, bins)
                p.rows.append(Row(
                    what="litter", name=os.path.basename(folder), source=folder,
                    target=where,
                    detail="nothing in it but thumbnails and index files other "
                           "software left behind, " + _going(where),
                    cells=["litter only", "", ""],
                    data={"path": folder, "to": where, "tree": True}))

        if bool(opts.get("empty")):
            for folder in C.empty_under(root):
                p.rows.append(Row(
                    what="empty folder", name=os.path.basename(folder),
                    source=folder, target="",
                    detail="holds nothing at all, deleted",
                    cells=["empty", "", ""],
                    data={"path": folder, "to": "", "tree": True}))

    p.columns = ["Folder", "How much", "Size", "Dates"]
    p.stats = [
        ("Piles found", f"{sum(1 for r in p.rows if r.what in dict(WHAT)):,}"),
        ("Photos and files in them", f"{total_files:,}"),
        ("Space they take", _size(total_bytes)),
        ("Folders to remove in all", f"{len(p.rows):,}"),
        ("Too recent to touch", f"{young:,}"),
        ("Where they go", _where_they_go(p.rows)),
    ]

    # What all of it has come to. The piles above are what is waiting now; this
    # is what every cull, thinning, duplicate check and emptying has already
    # done - which, once a pile is gone, nothing on the disk remembers.
    from core import reclaimed as _R
    back = _R.summary()
    if back["runs"]:
        p.stats += [
            ("Space freed, ever", _size(back["freed"])),
            ("  this year", _size(back["freed_year"])),
            ("Moved aside, ever", _size(back["aside"])),
        ]
        if back["last_freed"]:
            p.stats.append(("  last emptied",
                            _when(back["last_freed"]["when"]) + " - "
                            + _size(back["last_freed"]["bytes"])))

    binned, deleted = _split(p.rows)
    if binned and not deleted:
        p.notes.insert(0,
                       "These are being MOVED into the share's #recycle folder, "
                       "not deleted. You can get any of it back from File Station "
                       "for as long as DSM's policy keeps it, and it costs nothing "
                       "because it is a rename on the same disk.")
    elif binned:
        p.notes.insert(0,
                       f"{binned:,} of these are MOVED into the share's #recycle "
                       f"folder and can be got back from File Station. The other "
                       f"{deleted:,} are deleted outright - each row says which.")
    elif p.rows:
        p.notes.insert(0,
                       "These are deleted outright, not moved aside. "
                       "This is the only tool in the app that does that, and "
                       "there is no undo for it.")
    if not confirmed:
        p.notes.insert(0,
                       "Nothing will happen: this is a list, and the button is "
                       "not there. Read it, then tick 'Yes - actually remove "
                       "these' and look again. Everything else in this app puts "
                       "things aside, which is why this one asks twice.")
    if not wanted and not opts.get("leftovers") and not opts.get("empty"):
        p.notes.append("Nothing is ticked, so nothing was looked for.")
    if not p.rows:
        p.notes.append("There is nothing to clean up in there - no piles, or "
                       "none old enough to count.")
    p.notes.append(
        "Only folders this app made are ever listed: _Culled, _Duplicates and "
        "_NoLocation, by name. A folder you made and called 'old' is not this "
        "tool's business at any setting.")
    p.notes.append(
        "Age is measured from the last thing PUT in a pile, not from when the "
        "folder was made. A _Culled folder from last year that was added to this "
        "morning is this morning's pile.")
    return p


def _holds_something(row) -> bool:
    """A row whose removal loses something: a pile or a litter folder. An empty
    folder is removed either way, and holds nothing to get back."""
    return row.what != "empty folder"


def _split(rows) -> tuple:
    """(rows going to the recycle bin, rows deleted outright), of the rows that
    hold something."""
    real = [r for r in rows if _holds_something(r)]
    binned = sum(1 for r in real if r.data.get("to"))
    return binned, len(real) - binned


def _where_they_go(rows) -> str:
    binned, deleted = _split(rows)
    if binned and deleted:
        return (f"mixed: {binned:,} to the recycle bin, {deleted:,} deleted "
                f"outright")
    if binned:
        return "the recycle bin"
    return "deleted outright"


def _going(where: str) -> str:
    """Said on each row, so a mixed plan cannot read as all one thing."""
    return "to the recycle bin" if where else "deleted outright"


def _target(folder: str, root: str, bins: dict) -> str:
    """Where this folder goes: into the recycle bin, or nowhere at all."""
    bin_folder = bins.get(root, "")
    if not bin_folder:
        return ""
    return C.recycle_target(folder, bin_folder)


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    if not bool((plan.opts or {}).get("confirm")):
        # Belt and braces. The page withholds the button, the API could still be
        # asked; and of everything in this app, this is the one to check twice.
        result.details.append(
            "Nothing was removed: 'Yes - actually remove these' was not ticked.")
        result.failed = 0
        return result

    freed = files = 0
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        where = row.data.get("path", "")
        status = "OK"
        try:
            _refuse_unless_ours(where)
            if not os.path.isdir(where):
                raise FileNotFoundError("it is no longer there")
            into = row.data.get("to") or ""
            if into:
                into = moves.shift(result, where, into)
            elif row.what == "empty folder":
                os.rmdir(where)           # refuses if anything arrived since
            else:
                shutil.rmtree(where)
            files += int(row.data.get("files") or 0)
            freed += row.size
            result.done += 1
        except Exception as exc:                    # noqa: BLE001
            status = result.blame(where, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)

    result.reclaimed, result.reclaim_kind = freed, "freed"
    result.stats = [("Folders removed", f"{result.done:,}"),
                    ("Files in them", f"{files:,}"),
                    ("Space freed", _size(freed)),
                    ("Failed", f"{result.failed:,}")]
    if not result.failed and not result.cancelled:
        result.details.append(
            f"{_size(freed)} back. Nothing outside the piles this app made was "
            f"touched." if result.done else "There was nothing to remove.")
    return result


def _refuse_unless_ours(folder: str) -> None:
    """Check again, at the moment of doing it, that this is ours to remove.

    The plan already decided, and checking a second time here is not paranoia
    about the plan - it is that this is the only code path in the app that
    destroys something, so it is the one place worth being unable to be talked
    into it. A plan is data; data can be edited, replayed, or written by a test
    that got the folder wrong.
    """
    name = os.path.basename(os.path.abspath(folder)).strip().lower()
    if name in {v.lower() for v in C.PILES.values()}:
        return
    if name in C.NOT_WALKED:
        raise PermissionError(
            f"{folder} is the share's Recycle Bin or DSM's index, and this "
            f"tool never removes either")
    try:
        if not os.listdir(folder):                 # genuinely empty
            return
        if C.is_litter(folder):                    # nothing but litter
            return
    except OSError:
        pass
    raise PermissionError(
        f"{folder} is not a folder this app made, and this tool only ever "
        f"removes its own piles")


register(Task(
    name="cleanup",
    fold_groups=True,
    line="Empty the piles once you no longer want what is in them.",
    verb="Delete",
    unit="piles",
    risk="high",
    undo="On a share with a Recycle Bin they can be restored from File "
         "Station. Without one, this is the one thing in the app that "
         "really loses photos.",
    reads=('library', 'raw', 'previews', 'develop'),
    title="Clean up",
    summary="Deletes the _Culled, _Duplicates and _NoLocation piles. The "
            "only tool that really deletes.",
    icon="trash",
    order=60,
    options=[
        Folder("folder", "Folders to clean", setting="library", many=True,
               help="The folders to look through. Piles can be anywhere "
                    "inside them: a _Culled folder sits beside the shoot it "
                    "came from."),
        Flag("culled", WHAT[0][1], default=True, group="Piles",
             help="Deletes the _Culled folders made by Cull by rating, Thin "
                  "brackets and Find blurry. Everything in them is a photo "
                  "you decided against. On by default."),
        Flag("duplicates", WHAT[1][1], default=True, group="Piles",
             help="Deletes the _Duplicates folders made by Find duplicates. "
                  "One copy of each set was left in place, so these are "
                  "spare copies. On by default."),
        Flag("nolocation", WHAT[2][1], default=False, group="Piles",
             help="Deletes the _NoLocation folders that Geotag and Pin a "
                  "place by hand make when Keep originals is on. Off by "
                  "default: these are untouched originals, kept in case a "
                  "location was wrong."),
        Flag("leftovers", "Thumbnail-only folders",
             default=False, group="Piles",
             help="Deletes folders that hold only system files such as "
                  "@eaDir, Thumbs.db or .DS_Store and nothing else. A folder "
                  "with one photo and an @eaDir is left alone. Off by "
                  "default."),
        Flag("empty", "Empty folders", default=True,
             group="Piles",
             help="Deletes folders with nothing in them, deepest first, so a "
                  "year folder whose shoots have all moved goes too. On by "
                  "default."),
        Number("older_than", "Untouched for (days)",
               default=0, minimum=0, maximum=3650, group="Safety",
               help="Only piles that have not changed for this many days are "
                    "deleted. 0 to 3650, default 0, which deletes every pile "
                    "however recent. 30 is a safe choice, so this morning's "
                    "cull is still there if it was wrong."),
        Flag("recycle", "Use the recycle bin",
             default=True, group="Safety",
             help="Moves files into the share's #recycle folder instead of "
                  "deleting them, so File Station can bring them back. If "
                  "the share has no #recycle folder the tool refuses rather "
                  "than deleting. On by default."),
        Flag("confirm", "Confirm deletion", default=False,
             group="Safety",
             help="Until this is ticked the tool only reports and there is "
                  "no Apply button. Every other tool moves files and can be "
                  "undone. Deleting cannot, so it asks twice."),
        Folder("raw", "RAW tree", tree=True, default="", must_exist=False,
               setting="raw", group="Other trees", advanced=True,
               help="The top of the RAW tree, so its piles are cleaned too. "
                    "Culled and duplicate RAW files are the largest. Blank "
                    "leaves it alone."),
        Folder("previews", "Previews tree", tree=True, default="",
               must_exist=False, setting="previews", group="Other trees",
               advanced=True,
               help="The top of the previews tree, so its piles are cleaned "
                    "too. Blank leaves it alone."),
        Folder("develop", "Develop tree", tree=True, default="",
               must_exist=False, setting="develop", group="Other trees",
               advanced=True,
               help="The top of the develop tree, so its piles are cleaned "
                    "too. Blank leaves it alone."),
    ],
    plan=plan,
    apply=apply,
))
