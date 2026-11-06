"""A file manager's worth of operations, with this app's rules kept.

File Station can copy a folder. What it cannot do is know that
`Photos/2022/Spain/a.jpg` has a negative in another tree and a preview in a
third - so moving a shoot there leaves two trees wrong, and nothing says so
until a later feature quietly fails to pair anything.

So: listing, copying, moving, renaming, making folders and deleting, and the
one rule that makes it worth having here rather than in File Station -

**what belongs together travels together.** Moving a photograph inside the
library moves the same name in the RAW and previews trees to the matching
place, and its sidecars go with each of them. It can be turned off for a run,
and it is never guessed: only the same name, in the same position, in a tree
named in Setup.

**Nothing is deleted.** Delete means the share's `#recycle`, exactly as Delete
folder and the viewer mean it, and the moves are handed back so they can be
undone.

**A name is never taken.** Copying onto something that exists writes `a_1.jpg`
rather than over it, and the run says how many were renamed that way.
"""

from __future__ import annotations

import os
import shutil
import time

from . import cleanup as C
from . import moves as M
from . import quickedit as QE
from . import settings as S
from .paths import (companions, ensure_folder, mirror, safe_target,
                    skip_folder, under)
from .photo import kind

TREES = ("library", "raw", "previews", "video", "develop", "inbox")
HIDDEN_START = (".", "@", "#")


class Refused(Exception):
    """Said to the person as it is."""


class Partly(Refused):
    """Stopped part-way. `moves` is what had already happened, so it can be
    recorded and put back: a delete that fails on its fifth file has still
    moved four, and a 409 with no record of them is four files nobody can
    find from History."""

    def __init__(self, message: str, moves=None, size: int = 0):
        super().__init__(message)
        self.moves = list(moves or [])
        self.size = size


class _Book:
    """What `core.moves.shift` writes each move on, as it is made."""

    def __init__(self):
        self.moves: list = []


def _saved_trees() -> list:
    saved = S.load()
    out = []
    for key in TREES:
        root = str(saved[key] or "").strip()
        if root and root not in [r[1] for r in out]:
            out.append((key, root))
    return out


def roots() -> list:
    """The trees from Setup, for the Go to menu in the file manager."""
    names = {"library": "Library", "raw": "RAWs", "previews": "Previews",
             "video": "Video", "develop": "Develop", "inbox": "Inbox"}
    return [{"key": k, "name": names.get(k, k), "path": p, "there": os.path.isdir(p)}
            for k, p in _saved_trees()]


def crumbs(path: str) -> list:
    """Each step of the way here, so any of them is one tap away."""
    path = os.path.abspath(path)
    out = []
    while True:
        out.append({"name": os.path.basename(path) or path, "path": path})
        up = os.path.dirname(path)
        if up == path or len(out) > 30:
            break
        path = up
    return list(reversed(out))


DEEP_CAP = 4000


def _below(path: str, cap: int = DEEP_CAP) -> tuple:
    """Every photograph under here, and whether there were more than the cap.

    What the old Photos tab called "Include subfolders". It walks the way every
    other feature walks, so a folder excluded in Setup stays out of the listing
    too rather than appearing in one place and not another.
    """
    from . import walk as W
    found = [f for f in W.walk(path).files if kind(f) in ("jpeg", "image", "raw", "video")]
    found.sort(key=str.lower)
    return found[:cap], len(found) > cap


def entries(path: str, hidden: bool = False, deep: bool = False) -> dict:
    """What is in this folder: folders first, then files.

    With deep, the files are every photograph below here instead of only the
    ones in it - the folders are still listed, so walking in still works.
    """
    path = os.path.abspath(str(path or "").strip())
    if not os.path.isdir(path):
        raise Refused(f"There is no folder at {path}")
    folders, files = [], []
    total = 0
    with os.scandir(path) as it:
        for e in it:
            name = e.name
            if not hidden and (name.startswith(HIDDEN_START) or skip_folder(name)):
                continue
            try:
                st = e.stat()
            except OSError:
                continue
            item = {"name": name, "path": os.path.join(path, name),
                    "size": 0 if e.is_dir() else st.st_size,
                    "when": st.st_mtime, "kind": "folder" if e.is_dir() else kind(name)}
            if e.is_dir():
                folders.append(item)
            else:
                total += st.st_size
                files.append(item)
    folders.sort(key=lambda x: x["name"].lower())
    files.sort(key=lambda x: x["name"].lower())
    capped = False
    if deep:
        found, capped = _below(path)
        files, total = [], 0
        for one in found:
            try:
                st = os.stat(one)
            except OSError:
                continue
            total += st.st_size
            files.append({"name": os.path.relpath(one, path), "path": one,
                          "size": st.st_size, "when": st.st_mtime, "kind": kind(one)})
    up = os.path.dirname(path)
    return {"path": path, "parent": "" if up == path else up,
            "crumbs": crumbs(path), "folders": folders, "files": files,
            "size": total, "roots": roots(), "deep": bool(deep), "capped": capped}


# ------------------------------------------------------------ what travels

def _tree_of(path: str) -> tuple:
    for key, root in _saved_trees():
        if under(path, root):
            return key, root
    return "", ""


def partners(path: str, with_raw: bool = True, with_previews: bool = True) -> list:
    """The same shot in the other trees - the rule that earns this feature.

    Only the same name in the same position in a tree named in Setup. A file
    outside the trees, or renamed since, has no partner and gets none: a guess
    here moves somebody's photograph somewhere they did not put it.
    """
    want = {"raw": with_raw, "previews": with_previews}
    out = []
    for one in QE.copies(path):
        if one == path:
            continue
        key, _root = _tree_of(one)
        if want.get(key):
            out.append(one)
    return out


def _with_sidecars(paths) -> list:
    out = []
    for p in paths:
        if p not in out:
            out.append(p)
        for side in companions(p):
            if side not in out:
                out.append(side)
    return out


def _destination_for(source: str, into: str, home: str) -> str:
    """Where one partner lands: the same position in ITS own tree."""
    key, root = _tree_of(source)
    into_key, into_root = _tree_of(into)
    if not key or key == into_key or not home:
        return os.path.join(into, os.path.basename(source))
    # into is somewhere in the library; the RAW of what goes there belongs at
    # the matching place in the RAW tree, not beside the JPEG.
    if into_key and into_root:
        return os.path.join(mirror(into, into_root, root), os.path.basename(source))
    return os.path.join(into, os.path.basename(source))


def _mirrored_folders(folder: str, into: str, with_raw: bool,
                      with_previews: bool) -> list:
    """[(the same folder in another tree, where it goes)] for a folder move.

    Rename and Delete folder already carry the RAW and previews folders of a
    shoot; a move that did not left `Raw/2022/Spain` behind when `2022/Spain`
    went, which is exactly the File Station failure this module is for. Only
    when the folder moves within its own tree, so there is a matching place
    to send its mirrors to.
    """
    from . import renames
    key, root = _tree_of(folder)
    into_key, into_root = _tree_of(into)
    if not key or key != into_key:
        return []
    out = []
    for mate in renames.mirrored(folder, with_raw, with_previews):
        _mate_key, mate_root = _tree_of(mate)
        if not mate_root:
            continue
        out.append((mate, os.path.join(mirror(into, into_root, mate_root),
                                       os.path.basename(mate))))
    return out


def gather(sources, into: str, with_raw: bool = True,
           with_previews: bool = True) -> list:
    """[(from, to, why)] for everything one copy or move would touch."""
    into = os.path.abspath(str(into or "").strip())
    if not os.path.isdir(into):
        raise Refused(f"There is no folder at {into}")
    home = str(S.load()["library"] or "").strip()
    jobs, seen = [], set()

    def add(src, dst, why):
        if src in seen or not src:
            return
        seen.add(src)
        jobs.append((src, dst, why))

    for one in sources or []:
        one = os.path.abspath(str(one or "").strip())
        if not os.path.exists(one):
            continue
        if os.path.isdir(one):
            if under(into, one):
                raise Refused(f"{os.path.basename(one)} cannot go inside itself.")
            add(one, os.path.join(into, os.path.basename(one)), "folder")
            for mate, where in _mirrored_folders(one, into, with_raw,
                                                 with_previews):
                add(mate, where, f"the same folder as {os.path.basename(one)}, "
                                 f"in the {_tree_of(mate)[0]} tree")
            continue
        add(one, os.path.join(into, os.path.basename(one)), "picked")
        for side in companions(one):
            add(side, os.path.join(into, os.path.basename(side)),
                f"travels with {os.path.basename(one)}")
        if kind(one) in ("jpeg", "image", "raw"):
            for mate in partners(one, with_raw, with_previews):
                where = _destination_for(mate, into, home)
                add(mate, where, f"the {_tree_of(mate)[0]} of {os.path.basename(one)}")
                for side in companions(mate):
                    add(side, os.path.join(os.path.dirname(where),
                                           os.path.basename(side)),
                        f"travels with {os.path.basename(mate)}")
    return jobs


def run(jobs, move: bool, progress=None, cancelled=None) -> dict:
    """Do them. Never writes over anything: a taken name gets _1."""
    done = failed = renamed = 0
    moved_bytes = 0
    errors, copied = [], []
    book = _Book()
    moves = book.moves
    for i, (src, dst, _why) in enumerate(jobs, 1):
        if cancelled and cancelled():
            break
        name = os.path.basename(src)
        try:
            if not os.path.exists(src):
                raise FileNotFoundError("it is not there any more")
            ensure_folder(os.path.dirname(dst))
            target = safe_target(dst)
            if target != dst:
                renamed += 1
            size = 0
            try:
                size = os.path.getsize(src) if os.path.isfile(src) else 0
            except OSError:
                pass
            if move:
                M.shift(book, src, target)
            elif os.path.isdir(src):
                shutil.copytree(src, target)
                copied.append([src, target])
            else:
                shutil.copy2(src, target)
                copied.append([src, target])
            moved_bytes += size
            done += 1
        except Exception as exc:                       # noqa: BLE001
            failed += 1
            errors.append(f"{name}: {exc}")
        if progress:
            progress(i, len(jobs), name, "OK" if not errors or errors[-1].split(":")[0] != name else "failed")
    # THE INDEX FOLLOWS, RATHER THAN BEING TOLD TO GO AND LOOK.
    #
    # This is the one place in the app where files are moved and copied, and it
    # knows every pair. Marking the index stale instead would send the next pass
    # on a walk of the whole library to rediscover what was already written down
    # here - and until that pass ran, the Photos screen would go on showing
    # these photographs where they used to be.
    _tell(moves=moves, copies=copied)
    return {"done": done, "failed": failed, "renamed": renamed, "bytes": moved_bytes,
            "errors": errors[:60], "moves": moves}


def _tell(moves=(), copies=(), gone=()) -> None:
    """Hand the index what just happened here. Never raises, never blocks.

    A late import and a bare except on purpose: an index that cannot be updated
    is a slower app, and a file operation that failed because of it would be a
    much worse thing than that. The periodic pass is still the backstop for
    everything this app did not do itself.
    """
    if not (moves or copies or gone):
        return
    try:
        from . import catalogue
        catalogue.shared().followed(moves=moves, copies=copies, gone=gone)
    except Exception:                                      # noqa: BLE001
        try:
            from . import catalogue
            catalogue.shared().touch()
        except Exception:                                  # noqa: BLE001
            pass


# ------------------------------------------------------- the smaller things

def rename(path: str, name: str) -> dict:
    """Rename one thing - and its sidecars, which are named after it."""
    path = os.path.abspath(str(path or "").strip())
    name = str(name or "").strip()
    if not os.path.exists(path):
        raise Refused("that is not there any more")
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise Refused("a name cannot be empty or hold a slash")
    if any(c in name for c in '\\:*?"<>|'):
        raise Refused('a name cannot hold any of  \\ : * ? " < > |')
    where = os.path.join(os.path.dirname(path), name)
    if os.path.exists(where) and os.path.normcase(where) != os.path.normcase(path):
        raise Refused(f"{name} is taken in that folder")
    sides = [] if os.path.isdir(path) else companions(path)
    stem = os.path.splitext(name)[0]
    pairs = [[path, where]] + [
        [side, os.path.join(os.path.dirname(side), stem + os.path.splitext(side)[1])]
        for side in sides]
    # Every name checked before anything moves. A sidecar is renamed onto
    # whatever has its new name, and on a NAS that silently replaces it: an
    # orphan b.xmp, or the b.xmp holding b.RW2's stars, gone without a word.
    for was, now in pairs[1:]:
        if os.path.exists(now) and os.path.normcase(now) != os.path.normcase(was):
            raise Refused(f"{os.path.basename(now)} is already in that folder, "
                          f"and the sidecar would be renamed over it")
    try:
        os.rename(path, where)
    except OSError as exc:
        # The NAS said no. WHICH no matters: a folder somebody else owns, a
        # share mounted read-only and a name the filesystem will not take are
        # three different problems with three different fixes, and "it did not
        # work" is none of them.
        raise Refused(f"the NAS would not rename that: {exc.strerror or exc}"
                      + (" - the Permissions check under Settings fixes the "
                         "usual cause" if getattr(exc, "errno", 0) in (1, 13)
                         else "")) from exc
    moves = [pairs[0]]
    for was, now in pairs[1:]:
        try:
            os.rename(was, now)
            moves.append([was, now])
        except OSError:
            pass
    _tell(moves=moves)
    return {"path": where, "sidecars": len(moves) - 1, "moves": moves}


def make_folder(inside: str, name: str) -> dict:
    inside = os.path.abspath(str(inside or "").strip())
    name = str(name or "").strip()
    if not os.path.isdir(inside):
        raise Refused("there is no folder to make it in")
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        raise Refused("a name cannot be empty or hold a slash")
    where = os.path.join(inside, name)
    if os.path.exists(where):
        raise Refused(f"{name} is already there")
    ensure_folder(where)
    return {"path": where}


def delete(paths, with_raw: bool = False, with_previews: bool = False) -> dict:
    """Into the share's Recycle Bin, with the moves for Undo.

    Every file's bin is found before anything moves: a share without one is
    refused while everything is still where it was, not after the JPEG has
    gone and its RAW could not follow. A failure part-way still hands back
    what had moved, as `Partly`, so it reaches History.
    """
    wanted = []
    for one in paths or []:
        one = os.path.abspath(str(one or "").strip())
        if not os.path.exists(one):
            continue
        wanted.append(one)
        if os.path.isfile(one) and kind(one) in ("jpeg", "image", "raw"):
            wanted += partners(one, with_raw, with_previews)
    going = []
    for one in _with_sidecars(wanted):
        if C.RECYCLE in one.split(os.sep):
            continue
        bin_folder = C.recycle_root(one)
        if not bin_folder:
            raise Refused(f"{os.path.basename(one)} is on a share with no "
                          f"Recycle Bin, so nothing was deleted - turn it on in "
                          f"DSM > Control Panel > Shared Folder, or use Clean up")
        going.append((one, bin_folder))
    book, size = _Book(), 0
    try:
        for one, bin_folder in going:
            try:
                bytes_ = os.path.getsize(one) if os.path.isfile(one) else 0
            except OSError:
                bytes_ = 0
            M.shift(book, one, C.recycle_target(one, bin_folder))
            size += bytes_
    except OSError as exc:
        _deleted(book.moves)
        raise Partly(f"{os.path.basename(one)} could not be moved to the Recycle "
                     f"Bin ({exc.strerror or exc}); {len(book.moves)} file(s) "
                     f"before it were, and History can put them back",
                     moves=book.moves, size=size) from exc
    _deleted(book.moves)
    return {"moves": book.moves, "bytes": size, "done": len(book.moves)}


def _deleted(moves) -> None:
    from . import acl
    acl.after_delete([m[0] for m in moves])
    # Gone from the library, rather than moved within it: the Recycle Bin is not
    # a place this app indexes, so these simply leave the index.
    _tell(gone=[m[0] for m in moves])


def undo(moves) -> dict:
    """Put back what a move or a delete just did.

    Two cases, one rule: the thing is only put back if where it came from is
    still free. Anything else would be this app writing over whatever has taken
    the name since, which is the one thing a file manager must never do.
    """
    back = 0
    put: list = []
    for pair in moves or []:
        try:
            was, now = str(pair[0]), str(pair[1])
        except (TypeError, IndexError):
            continue
        if not now or not os.path.exists(now) or os.path.exists(was):
            continue
        try:
            ensure_folder(os.path.dirname(was))
            shutil.move(now, was)
            put.append([now, was])
            back += 1
        except OSError:
            continue
    _tell(moves=put)
    return {"restored": back}


# ----------------------------------------------------------- what is in here

STATUS_CAP = 3000


def status(path: str) -> dict:
    """What this folder actually holds - the dashboard above the listing.

    The questions you have standing in a folder are not "how many files": they
    are whether it is rated, whether it has been geotagged, whether the RAWs and
    previews are beside it, and whether anything in it has no date. All of them
    come out of the same cache every other feature reads, so the second visit
    costs nothing, and a folder bigger than `STATUS_CAP` says so rather than
    reading for a minute.
    """
    from . import facts
    from .photo import read_gps
    path = os.path.abspath(str(path or "").strip())
    if not os.path.isdir(path):
        raise Refused(f"There is no folder at {path}")
    out = {"path": path, "photos": 0, "raws": 0, "videos": 0, "others": 0,
           "size": 0, "rated": 0, "tagged": 0, "located": 0, "undated": 0,
           "with_raw": 0, "with_preview": 0, "capped": False, "read": ""}
    names = []
    with os.scandir(path) as it:
        for e in it:
            if e.is_dir() or e.name.startswith(HIDDEN_START):
                continue
            names.append(e.path)
    if len(names) > STATUS_CAP:
        out["capped"] = True
        names = names[:STATUS_CAP]
    reader = facts.reader()
    for one in sorted(names):
        what = kind(one)
        try:
            out["size"] += os.path.getsize(one)
        except OSError:
            pass
        if what == "raw":
            out["raws"] += 1
            continue
        if what == "video":
            out["videos"] += 1
            continue
        if what not in ("jpeg", "image"):
            out["others"] += 1
            continue
        out["photos"] += 1
        try:
            if reader.stars(one):
                out["rated"] += 1
            if reader.tags(one):
                out["tagged"] += 1
            cap = reader.capture(one)
            if cap.taken is None:
                out["undated"] += 1
            # Read once and remembered beside everything else known about the
            # file, because a location is a header read like any other.
            if reader._field(one, "loc", lambda p: 1 if read_gps(p) else 0):
                out["located"] += 1
        except Exception:                              # noqa: BLE001
            pass
        mates = {_tree_of(m)[0] for m in partners(one, True, True)}
        if "raw" in mates:
            out["with_raw"] += 1
        if "previews" in mates:
            out["with_preview"] += 1
    out["read"] = reader.said()
    reader.save()
    return out


def marks(path: str, cap: int = 1500, deep: bool = False) -> dict:
    """{file: {stars, colour, tags}} for the photographs in one folder.

    What the Photos tab used to show, in the manager itself - so the grid says
    which of these you have already rated without opening any of them. Read
    from the same cache as everything else: the second visit costs nothing.
    """
    from . import facts
    path = os.path.abspath(str(path or "").strip())
    if not os.path.isdir(path):
        raise Refused(f"There is no folder at {path}")
    reader = facts.reader()
    out: dict = {}
    n = 0
    if deep:
        names, _ = _below(path, cap)
    else:
        with os.scandir(path) as it:
            names = sorted(e.path for e in it
                           if e.is_file() and not e.name.startswith(HIDDEN_START))
    for one in names:
        if kind(one) not in ("jpeg", "image", "raw"):
            continue
        n += 1
        if n > cap:
            break
        try:
            out[one] = {"stars": int(reader.stars(one) or 0),
                        "colour": reader.colour(one) or "",
                        "tags": list(reader.tags(one))[:6]}
        except Exception:                              # noqa: BLE001
            continue
    reader.save()
    return {"path": path, "marks": out, "capped": n > cap}


def weigh(path: str) -> dict:
    """How much a folder holds, all the way down - and what is in the way.

    Asked for one folder at a time, on purpose: a listing that weighed every
    folder in it would walk the whole tree before showing a single name, and
    the names are the part you were waiting for. Pressing the dash is cheap to
    do and obvious to undo.

    `deep` counts everything below; `here` is only what is directly in it, so
    "this folder is 40GB but nothing is in it" reads as "it is the subfolders",
    which is the next question every time.
    """
    path = os.path.abspath(str(path or "").strip())
    if not os.path.isdir(path):
        raise Refused(f"There is no folder at {path}")
    deep = here = files = folders = 0
    for where, dirs, names in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(HIDDEN_START)]
        folders += len(dirs)
        for name in names:
            try:
                size = os.stat(os.path.join(where, name)).st_size
            except OSError:
                continue
            deep += size
            files += 1
            if where == path:
                here += size
    return {"path": path, "bytes": deep, "here": here,
            "files": files, "folders": folders}


def stamp() -> str:
    return time.strftime("%d %b %H:%M")
