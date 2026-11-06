"""Renaming many folders at once - the table you type into.

Renaming one folder is a right-click in any file manager. What nobody has is a
way to fix *thirty* folder names in one pass: `2022-04-12`, `12 April 2022`,
`April 12`, `Spain trip` and `spain trip 2` all sitting in the same tree because
they were made across three years by three different habits. One at a time, that
is thirty dialogs, and halfway through you lose track of which convention you
decided on.

So: every folder in a table, its name in a box, type over the ones that are
wrong. Nothing is written until you say so, and the table says what WOULD
happen first - which is the same promise every other tab in this app makes.

Three things this refuses to do, because each one is a way to lose a folder:

* **Two folders with one name.** Typed by hand it happens constantly - you fix
  two names to the same convention and they meet. Caught before anything runs,
  per parent folder, and named in the table rather than reported afterwards.
* **Writing over something already there.** A name that is taken by a folder
  not in the table is refused outright. The move variant of this app makes a
  `_1`; a rename must not, because `Spain_1` is not what you typed and you would
  not find it again.
* **Renaming a parent before its children.** The deepest rows go first, so a
  child's path is still the path it was read at. A tree renamed top-down loses
  every row below the first one.

And the rule this app exists for: a folder renamed in the library is renamed at
the matching place in the RAW and previews trees, so the trees that have to stay
mirrored stay mirrored. Only the same position in a tree named in Setup - never
a guess.
"""

from __future__ import annotations

import os
import re

from . import settings as S
from .paths import companions, mirror, relative_under, skip_folder, under

CAP = 3000
BAD = '\\/:*?"<>|'
HIDDEN_START = (".", "@", "#")
TREES = ("library", "raw", "previews", "video", "develop", "inbox")


class Refused(Exception):
    """Said to the person as it is."""


# --------------------------------------------------------------- what to list


def _readable(where: str) -> list:
    try:
        with os.scandir(where) as it:
            return sorted((e.name for e in it if e.is_dir()), key=str.lower)
    except OSError:
        return []


def _walk(root: str, depth: int, out: list, level: int = 1) -> None:
    """Folders below `root`, breadth kept in reading order, down to `depth`."""
    for name in _readable(root):
        if name.startswith(HIDDEN_START) or skip_folder(name):
            continue
        here = os.path.join(root, name)
        if len(out) >= CAP:
            return
        out.append({"path": here, "name": name, "depth": level,
                    "parent": root, "kind": "folder",
                    "holds": len(_readable(here))})
        if depth <= 0 or level < depth:
            _walk(here, depth, out, level + 1)


def listing(folder: str, depth: int = 1, picked=None, start: int = 0) -> dict:
    """The rows for the table.

    `picked` is what you had selected in the file manager - the whole point of
    reaching this tab from there. Each picked folder goes in with everything
    below it to `depth`; picked files go in on their own, because a file you
    deliberately selected is a file you meant to rename. With nothing picked it
    is the folder you are standing in.

    `depth` of 1 is what is directly inside, 0 means the whole way down.

    `start` is which level to begin at: 0 is the folder you picked, 1 skips
    straight past its children to the level below, and so on. Together with
    `depth` that is "the year folders" or "the shoots inside the year folders"
    rather than "everything, all of it" - which on a library of twelve years is
    a table nobody can use.
    """
    folder = os.path.abspath(str(folder or "").strip())
    depth = max(0, int(depth or 0))
    start = max(0, int(start or 0))
    rows: list = []
    chosen = [os.path.abspath(str(p or "").strip()) for p in (picked or []) if p]
    chosen = [p for p in chosen if os.path.exists(p)]
    if chosen:
        for one in chosen:
            if os.path.isdir(one):
                rows.append({"path": one, "name": os.path.basename(one),
                             "depth": 0, "parent": os.path.dirname(one),
                             "kind": "folder", "holds": len(_readable(one))})
                if depth != 1:
                    _walk(one, 0 if depth == 0 else depth - 1, rows, 1)
            else:
                rows.append({"path": one, "name": os.path.basename(one),
                             "depth": 0, "parent": os.path.dirname(one),
                             "kind": "file", "holds": 0})
    else:
        if not os.path.isdir(folder):
            raise Refused(f"There is no folder at {folder}")
        _walk(folder, depth, rows)
    if start:
        # Thrown away AFTER the walk rather than skipped during it, because the
        # walk is what knows how deep each row is - and the depths that are kept
        # are renumbered so the table still indents from zero.
        rows = [dict(r, depth=r["depth"] - start) for r in rows
                if r["depth"] >= start]
    from . import naming
    return {"folder": folder, "rows": rows[:CAP], "capped": len(rows) >= CAP,
            "start": start, "depth": depth,
            "from_picked": bool(chosen),
            # The patterns kept in Setup, so naming thirty folders "2022
            # Ramadhan" is a choice in a list rather than something retyped here.
            "kept": [{"name": n, "pattern": pat} for n, pat in naming.saved()]}


# ------------------------------------------------------------ the mirrored ones


def _tree_of(path: str) -> tuple:
    saved = S.load()
    for key in TREES:
        root = str(saved[key] or "").strip()
        if root and under(path, root):
            return key, root
    return "", ""


def mirrored(path: str, with_raw: bool = True, with_previews: bool = True) -> list:
    """The same folder in the other trees - the ones that actually exist.

    A folder, not a photograph, so there is no capture time to match on: the
    only honest test is the same position under a tree named in Setup, and a
    folder that is not there gets nothing rather than being created.
    """
    key, root = _tree_of(path)
    if not key:
        return []
    want = {"raw": with_raw, "previews": with_previews}
    saved = S.load()
    out = []
    for other in TREES:
        if other == key or not want.get(other):
            continue
        to_root = str(saved[other] or "").strip()
        if not to_root or not os.path.isdir(to_root):
            continue
        where = mirror(path, root, to_root)
        if where != to_root and os.path.isdir(where):
            out.append(where)
    return out


# ------------------------------------------------------------------- checking


def trouble(name: str) -> str:
    """Why this name cannot be used, or "" if it can."""
    name = str(name or "")
    if not name.strip():
        return "a name cannot be empty"
    if name != name.strip():
        return "it starts or ends with a space"
    if name in (".", ".."):
        return "that is not a name"
    for c in BAD:
        if c in name:
            return f'a name cannot hold  {c}'
    if name.endswith("."):
        return "a name cannot end with a full stop"
    if name.startswith(HIDDEN_START):
        return "a name starting with . @ or # is hidden - the app skips those"
    if len(name) > 200:
        return "that is too long for a folder name"
    return ""


def check(wanted) -> dict:
    """[{path, was, name, problem}] for a table as it stands, before anything runs.

    Every check that matters happens here, once, over the whole table - because
    the two that bite (two rows meeting on one name, and a name already taken)
    are not visible from inside a single row.
    """
    rows, seen = [], {}
    for one in wanted or []:
        path = os.path.abspath(str((one or {}).get("path") or "").strip())
        name = str((one or {}).get("name") or "")
        was = os.path.basename(path)
        row = {"path": path, "was": was, "name": name, "problem": ""}
        if not path or not os.path.exists(path):
            row["problem"] = "it is not there any more"
        elif name == was:
            row["same"] = True
        else:
            row["problem"] = trouble(name)
        rows.append(row)
        if row["problem"] or row.get("same"):
            continue
        key = (os.path.normcase(os.path.dirname(path)), os.path.normcase(name))
        seen.setdefault(key, []).append(row)

    for (parent, _low), group in seen.items():
        if len(group) > 1:
            for row in group:
                row["problem"] = (f"{len(group)} rows would all be called "
                                  f"{row['name']} in the same folder")
            continue
        row = group[0]
        where = os.path.join(os.path.dirname(row["path"]), row["name"])
        if os.path.exists(where) and os.path.normcase(where) != os.path.normcase(row["path"]):
            # taken - unless the thing holding the name is itself moving away
            movers = {os.path.normcase(r["path"]) for r in rows
                      if not r["problem"] and not r.get("same")}
            if os.path.normcase(where) not in movers:
                row["problem"] = f"{row['name']} is already in that folder"
                continue
        # A picked file carries its sidecars, and one renamed onto a sidecar
        # that is already there replaces it - the stars of another photograph,
        # gone without a word.
        for was, now in _sidecars_of(row["path"], row["name"]):
            if os.path.exists(now) and os.path.normcase(now) != os.path.normcase(was):
                row["problem"] = (f"{os.path.basename(now)} is already in that "
                                  f"folder, and the sidecar would go over it")
                break
    changing = [r for r in rows if not r["problem"] and not r.get("same")]
    return {"rows": rows, "ready": len(changing),
            "problems": sum(1 for r in rows if r["problem"])}


# ------------------------------------------------------------------- doing it


def apply(wanted, with_raw: bool = True, with_previews: bool = True,
          progress=None) -> dict:
    """Rename every row that has a new name. Deepest first.

    Refuses the whole table if any row has a problem: a half-applied rename over
    thirty folders is far worse than none, because working out which fifteen
    went through is a job nobody can do from a results table.
    """
    looked = check(wanted)
    bad = [r for r in looked["rows"] if r["problem"]]
    if bad:
        raise Refused(f"{len(bad)} row(s) cannot be renamed - fix those first: "
                      + "; ".join(f"{r['was']}: {r['problem']}" for r in bad[:3])
                      + ("; ..." if len(bad) > 3 else ""))
    doing = [r for r in looked["rows"] if not r.get("same")]
    # Deepest first, so a parent renamed later never invalidates a child's path.
    doing.sort(key=lambda r: (-r["path"].count(os.sep), r["path"].lower()))
    moves, mirrors, sides, failed = [], 0, 0, []
    for n, row in enumerate(doing, 1):
        if progress:
            progress(n, len(doing), row["was"])
        where = os.path.join(os.path.dirname(row["path"]), row["name"])
        try:
            os.rename(row["path"], where)
        except OSError as exc:
            failed.append(f"{row['was']}  ->  {row['name']}: "
                          f"{exc.strerror or 'could not be renamed'}")
            continue
        moves.append([row["path"], where])
        for was, now in _sidecars_of(row["path"], row["name"], after=where):
            try:
                os.rename(was, now)
                moves.append([was, now])
                sides += 1
            except OSError:
                failed.append(f"{row['name']} was renamed, but its sidecar "
                              f"{os.path.basename(was)} could not be")
        if os.path.isdir(where) and (with_raw or with_previews):
            for other in mirrored(row["path"], with_raw, with_previews):
                to = os.path.join(os.path.dirname(other), row["name"])
                if os.path.exists(to):
                    failed.append(f"{row['name']} is taken in "
                                  f"{os.path.basename(os.path.dirname(other))} - "
                                  f"that tree still says {row['was']}")
                    continue
                try:
                    os.rename(other, to)
                except OSError:
                    failed.append(f"{row['was']} was renamed, but the same folder "
                                  f"in {os.path.basename(os.path.dirname(other))} "
                                  f"could not be")
                    continue
                moves.append([other, to])
                mirrors += 1
    # The index follows, as it does for the file manager's own rename: until
    # the next walk the Photos screen would show these under their old names.
    from .filesops import _tell
    _tell(moves=moves)
    return {"moves": moves, "done": len(moves), "renamed": len(moves) - mirrors - sides,
            "mirrored": mirrors, "sidecars": sides, "failed": failed}


def _sidecars_of(path: str, name: str, after: str = "") -> list:
    """[(sidecar, its new name)] for a picked file being renamed to `name`.

    `after` is where the file now is, once it has been renamed: the sidecars
    are found beside the old name, which is where they still are."""
    if os.path.isdir(after or path):
        return []
    stem = os.path.splitext(name)[0]
    out = []
    for side in companions(path):
        out.append((side, os.path.join(os.path.dirname(side),
                                        stem + os.path.splitext(side)[1])))
    return out


# --------------------------------------------------------- the bulk tools

NUM = re.compile(r"^[\s\-_.]*\d+[\s\-_.]+")


def swap(name: str, find: str, put: str, matching_case: bool = False) -> str:
    """Find and replace in one name. Plain text, never a pattern.

    A regular expression box here would be the most powerful and the most
    dangerous control in the app: the first mistake renames thirty folders to
    something nobody typed. The table shows every result before anything runs,
    and that is the safety this leans on instead.
    """
    name, find = str(name or ""), str(find or "")
    if not find:
        return name
    if matching_case:
        return name.replace(find, str(put or ""))
    out, low, lowfind = [], name.lower(), find.lower()
    at = 0
    while True:
        hit = low.find(lowfind, at)
        if hit < 0:
            out.append(name[at:])
            return "".join(out)
        out.append(name[at:hit])
        out.append(str(put or ""))
        at = hit + len(find)


def recase(name: str, how: str) -> str:
    name = str(name or "")
    if how == "lower":
        return name.lower()
    if how == "upper":
        return name.upper()
    if how == "title":
        # Words, not Python's title(): that turns "GH4" into "Gh4" and
        # "spain's" into "Spain'S", and camera names matter here.
        return re.sub(r"[A-Za-z][A-Za-z']*",
                      lambda m: m.group(0)[0].upper() + m.group(0)[1:], name)
    return name


def tidy(name: str) -> str:
    """Runs of spaces and underscores down to one, and nothing on the ends."""
    name = re.sub(r"[ \t]+", " ", str(name or "")).strip()
    return re.sub(r"_{2,}", "_", name).strip(" -_")


def strip_number(name: str) -> str:
    """Take a leading counter off - `01 - Spain` becomes `Spain`."""
    out = NUM.sub("", str(name or ""), count=1)
    return out or str(name or "")


def numbered(names, start: int = 1, width: int = 2, at_end: bool = False,
             sep: str = " - ") -> list:
    """A running number put on each name, in the order given."""
    start, width = int(start or 1), max(1, min(6, int(width or 2)))
    out = []
    for n, name in enumerate(names or [], start):
        num = str(n).zfill(width)
        out.append(f"{name}{sep}{num}" if at_end else f"{num}{sep}{name}")
    return out


PHOTO_CAP = 400


def _inside(folder: str) -> list:
    """The photographs this folder is about.

    The ones directly in it, and if there are none, the ones below it - because
    a folder called `2022` holds shoots rather than photographs and still has a
    date. Capped: the earliest and the camera do not get truer after the four
    hundredth file.
    """
    from .photo import is_picture, kind
    here = []
    try:
        with os.scandir(folder) as it:
            for e in it:
                if e.is_file() and (is_picture(e.path) or kind(e.path) == "raw"):
                    here.append(e.path)
                    if len(here) >= PHOTO_CAP:
                        return sorted(here)
    except OSError:
        return []
    if here:
        return sorted(here)
    from . import walk as W
    below = [f for f in W.walk(folder).files
             if is_picture(f) or kind(f) == "raw"]
    return sorted(below)[:PHOTO_CAP]


def pattern_name(folder: str, pattern: str, week_starts: int = 0,
                 hijri_shift: int = 0) -> str:
    """What a saved folder pattern would call this folder. "" if it cannot say.

    The same engine the filing tabs use (`core/naming.py`), fed the photographs
    inside - so "2022 Ramadhan" across thirty folders is one choice here rather
    than thirty names typed by hand. The folder is named by its EARLIEST
    photograph, with the whole span available to {range}.

    A pattern that needs a place gets nothing: working out where a folder is
    means looking every photograph up in the city table, and a folder renamed
    from a half-answered lookup is a folder nobody can find again. "" means keep
    the name you have, which is never wrong.
    """
    from . import naming
    from .photo import read_capture
    times, models, lenses = [], {}, {}
    for path in _inside(folder):
        try:
            cap = read_capture(path)
        except Exception:                              # noqa: BLE001
            continue
        if getattr(cap, "taken", None):
            times.append(cap.taken)
        model = str(getattr(cap, "model", "") or "").strip()
        lens = str(getattr(cap, "lens", "") or "").strip()
        if model:
            models[model] = models.get(model, 0) + 1
        if lens:
            lenses[lens] = lenses.get(lens, 0) + 1
    if not times:
        return ""
    first, last = min(times), max(times)
    camera = max(models, key=models.get) if models else ""
    lens = max(lenses, key=lenses.get) if lenses else ""
    values = naming.facts(first, None, camera, lens, (first, last),
                          int(week_starts or 0), int(hijri_shift or 0))
    said = naming.render(str(pattern or ""), values)
    if not said:
        return ""
    # A pattern can describe a tree - {year}/{month}. A rename makes ONE name,
    # so the deepest level is the one used, and the page says so.
    return said.split("/")[-1]


def by_pattern(paths, pattern: str, week_starts: int = 0,
               hijri_shift: int = 0) -> list:
    """`pattern_name` over many folders, each keeping its name where it cannot say."""
    out = []
    for path in paths or []:
        path = str(path or "")
        said = pattern_name(path, pattern, week_starts, hijri_shift) if path else ""
        out.append(said or os.path.basename(path))
    return out


def relative(path: str, folder: str) -> str:
    rel = relative_under(path, folder)
    return rel or os.path.basename(path)
