"""One photo, changed by hand from the viewer: stars, colour, tags, location, delete.

**Every copy of the shot, not just the one on screen.** The same photograph is
in the library, as a RAW and as a preview. Change only the one you are looking
at and the next Sync carries the OLD stars back from the previews over the
new ones - the edit would last until four in the morning. So each change is
written to the same name in the same folder of every tree in Setup: quick,
exact, and it never guesses. A copy that was renamed is not found here; Sync
still finds those by capture time.

**Delete is the Recycle Bin**, like Delete folder: every copy and its sidecars
move into the share's #recycle, and the moves are handed back so the viewer can
offer Undo. Nothing is ever removed for good here.
"""

from __future__ import annotations

import json
import os
import shutil

from . import cleanup as C
from . import facts
from . import labels as L
from . import settings as S
from . import tags as tagread
from . import tagwrite
from .exifwrite import rating_of, set_rating, write_rating_sidecar
from .paths import companions, ensure_folder, under
from .photo import kind
from .sidecar import beside
from .store import store_path

TREES = ("library", "raw", "previews")
RECENT = "quicktags.json"
KEEP_RECENT = 40
# A CLIP CAN BE MARKED, AND IT ALWAYS COULD HAVE BEEN.
#
# The rule used to be "stars go inside the file, and there is nowhere inside an
# MP4 to put them". The first half is only true of JPEGs. A RAW is never opened
# for writing by this app either - its stars, its label and its keywords go in
# an .xmp beside it, and `exifwrite.set_rating`, `tagwrite.add` and the labels
# have taken that path since they were written.
#
# A video is a RAW as far as this is concerned: nothing is written into it, a
# sidecar is written beside it, and every reader in this app already looks there
# first. So a clip is rated, coloured and tagged exactly like a negative - and
# the only thing that had to change was the list that said it could not be.
EDITABLE = ("jpeg", "image", "raw", "video")

# Moving a file to the Recycle Bin or renaming it writes nothing into it at all.
MOVABLE = EDITABLE


class Refused(Exception):
    """Said to the person as it is - these are never programming errors."""


def _check(path: str, kinds=EDITABLE) -> str:
    path = str(path or "").strip()
    if not path or not os.path.isfile(path):
        raise Refused("that file is not there any more")
    if kind(path) not in kinds:
        raise Refused("only photos can be marked here"
                      if kinds is EDITABLE else
                      "that is not a file this app looks after")
    return path


def copies(path: str) -> list:
    """This file, then the same shot in the other trees - same folder, same name."""
    out = [path]
    saved = S.load()
    roots = {k: str(saved[k] or "").strip() for k in TREES}
    home = next((k for k in TREES if roots[k] and under(path, roots[k])), "")
    if not home:
        return out
    rel = os.path.relpath(os.path.dirname(path), roots[home])
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    for key in TREES:
        if key == home or not roots[key]:
            continue
        folder = os.path.normpath(os.path.join(roots[key], rel))
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for n in sorted(names):
            full = os.path.join(folder, n)
            if (os.path.splitext(n)[0].lower() == stem and kind(full) in EDITABLE
                    and os.path.isfile(full) and full not in out):
                out.append(full)
    return out


def _forget(paths) -> None:
    try:
        r = facts.reader()
        for p in paths:
            r.forget(p)
        r.save()
    except Exception:                                  # noqa: BLE001
        pass


def state(path: str) -> dict:
    path = _check(path)
    return {"path": path,
            "stars": int(rating_of(path) or 0),
            "colour": L.colour_of(path) or "",
            "tags": tagread.tags_of(path)}


def _shutter(seconds) -> str:
    """The shutter the way a camera says it, not as a decimal.

    1/250 is a shutter speed; 0.004 is a number you have to convert in your head
    every time you read it, and nobody reading a photograph wants to do that.
    """
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return ""
    if seconds >= 1:
        return f"{seconds:g}s"
    return f"1/{round(1 / seconds):g}"


def shot(path: str) -> dict:
    """How this frame was exposed - the four numbers on the back of the camera.

    Focal length, shutter, aperture, ISO. Read from the same cache as
    everything else, so paging through a shoot with the overlay on costs one
    read per photograph and nothing on the second pass.

    The full-frame equivalent is carried separately rather than instead: on this
    library both matter, because a GH4 doubles every focal length and "25mm"
    means two different pictures depending on which body it was on.
    """
    path = _check(path)
    out = {"taken": "", "camera": "", "lens": "", "iso": 0, "shutter": "",
           "seconds": None, "fnumber": None, "focal": None, "focal35": None,
           "ev": None}
    try:
        cap = facts.reader().capture(path)
    except Exception:                                  # noqa: BLE001
        return out
    if cap.taken is not None:
        out["taken"] = cap.taken.strftime("%Y-%m-%d %H:%M:%S")
    from . import devices
    out["camera"] = devices.name_of(cap.model or "")
    out["model"] = str(cap.model or "").strip()
    out["lens"] = str(cap.lens or "").strip()
    out["iso"] = int(cap.iso or 0)
    out["seconds"] = cap.exposure
    out["shutter"] = _shutter(cap.exposure)
    out["fnumber"] = round(float(cap.fnumber), 1) if cap.fnumber else None
    out["focal"] = round(float(cap.focal_length), 1) if cap.focal_length else None
    out["focal35"] = round(float(cap.focal35)) if cap.focal35 else None
    out["ev"] = round(float(cap.ev), 2) if cap.ev is not None else None
    return out


def _each(path: str, write) -> dict:
    """Write to every copy; the one on screen must work, the others try."""
    path = _check(path)
    done, failed = [], []
    for one in copies(path):
        try:
            write(one)
            done.append(one)
        except Exception as exc:                       # noqa: BLE001
            if one == path:
                raise Refused(f"could not write it: {exc}") from exc
            failed.append(f"{os.path.basename(one)}: {exc}")
    _forget(done)
    out = state(path)
    out["copies"] = len(done)
    out["failed"] = failed
    return out


def set_stars(path: str, stars) -> dict:
    stars = int(stars)
    if not 0 <= stars <= 5:
        raise Refused("stars are 0 to 5")

    def write(one):
        try:
            set_rating(one, stars)
        except ValueError:
            # A JPEG with no EXIF block at all (a messenger app stripped it)
            # has nowhere inside to hold stars - the sidecar still can.
            write_rating_sidecar(one, stars)
            return
        # A JPEG is rated inside the file - but a sidecar beside it that also
        # carries a rating would still win when it is read back.
        if kind(one) == "jpeg" and beside(one):
            write_rating_sidecar(one, stars)
    return _each(path, write)


def set_colour(path: str, colour: str) -> dict:
    colour = str(colour or "").strip().lower()
    if colour and colour not in L.COLOURS:
        raise Refused(f"{colour} is not one of the five colours")
    d = L.by_colour(colour) if colour else None
    words = d.all_keywords() if d else []
    def write(one):
        got = L.set_label(one, colour, keywords=words)
        if not got["sidecar"] and not got["photo"]:
            raise RuntimeError(got["why"] or "nothing could be written")
    return _each(path, write)


def add_tag(path: str, word: str) -> dict:
    word = str(word or "").strip()
    if not word:
        raise Refused("a tag needs a word")
    def write(one):
        got = tagwrite.add(one, [word])
        if not (got["sidecar"] or got["xmp"] or got["windows"]):
            raise RuntimeError("; ".join(got["errors"]) or "nothing written")
    out = _each(path, write)
    remember(word)
    return out


def remove_tag(path: str, word: str) -> dict:
    word = str(word or "").strip()
    left = []

    def write(one):
        got = tagwrite.remove(one, [word])
        if not (got["sidecar"] or got["xmp"] or got["windows"]) and got["errors"]:
            raise RuntimeError("; ".join(got["errors"]))
        left.extend(got.get("left_in_iptc") or [])
    out = _each(path, write)
    if left:
        out["failed"].append("still in the file's old IPTC tags, which "
                             "this app does not rewrite")
    return out


def unlocate(path: str) -> dict:
    """Take the location off this shot - out of every copy of it.

    The Strip location tab does this to a whole folder, which is the right
    shape when you have just geotagged one and want it undone. It is the wrong
    shape when you are LOOKING at the one photograph that is wrong: closing the
    viewer, finding the folder, typing it into another tab and running it over
    forty photographs to fix one is how a person decides not to bother.

    Same rule as every other edit here: every copy, and the one on screen has
    to work or the whole thing is refused. A copy in a sidecar counts - a
    position left in the sidecar is the position that gets read back.
    """
    from . import sidecar as sc
    from .exifwrite import strip_gps
    path = _check(path)
    done, failed, taken = [], [], 0
    for one in copies(path):
        try:
            hit = False
            if kind(one) == "jpeg":
                hit = strip_gps(one) or hit
            hit = sc.drop(one, "exif:GPS") or hit
            if hit:
                taken += 1
            done.append(one)
        except Exception as exc:                       # noqa: BLE001
            if one == path:
                raise Refused(f"could not take the location off: {exc}") from exc
            failed.append(f"{os.path.basename(one)}: {exc}")
    _forget(done)
    out = state(path)
    out["copies"] = len(done)
    out["failed"] = failed
    out["taken"] = taken
    out["located"] = False
    return out


def about(path: str) -> dict:
    """What this photograph IS - the answer to "which one is this".

    Camera, lens, when it was taken, where it was taken, how big it is, and
    where its negative and its preview are. All of it read from the same cache
    every other feature reads, so opening this on a hundred photographs in a row
    costs one read each and nothing after that.
    """
    path = _check(path, MOVABLE)
    reader = facts.reader()
    out = {"path": path, "name": os.path.basename(path),
           "folder": os.path.dirname(path), "kind": kind(path)}
    try:
        st = os.stat(path)
        out["bytes"] = st.st_size
        out["changed"] = st.st_mtime
    except OSError:
        out["bytes"] = 0
        out["changed"] = 0
    try:
        out.update(shot(path))
    except Exception:                                  # noqa: BLE001
        out["taken"] = out["camera"] = out["lens"] = ""
    try:
        from .photo import read_gps
        where = read_gps(path)
        out["located"] = bool(where and where.has_gps)
        if out["located"]:
            out["lat"] = round(float(where.lat), 6)
            out["lon"] = round(float(where.lon), 6)
    except Exception:                                  # noqa: BLE001
        out["located"] = False
    beside_it = []
    for one in copies(path):
        if one == path:
            continue
        try:
            size = os.path.getsize(one)
        except OSError:
            size = 0
        beside_it.append({"path": one, "name": os.path.basename(one),
                          "bytes": size, "kind": kind(one)})
    out["copies"] = beside_it
    out["sidecar"] = bool(beside(path))
    reader.save()
    return out


def delete(path: str) -> dict:
    """Every copy and its sidecars into the Recycle Bin. Returns the moves.

    A clip counts. Nothing is written into it - it is moved - and the Photos
    screen lists clips beside photographs, so refusing to delete one from there
    was the screen disagreeing with itself.

    A copy on a share with no Recycle Bin is left where it is and said so in
    `kept`, rather than skipped in silence. Each move is written down as it is
    made, so a failure part-way raises `Partly` with the moves already done.
    """
    path = _check(path, MOVABLE)
    going, kept = [], []
    for one in copies(path):
        bin_folder = C.recycle_root(one)
        if not bin_folder:
            if one == path:
                raise Refused("this share has no Recycle Bin - turn it on in "
                              "DSM > Control Panel > Shared Folder")
            kept.append(one)
            continue
        for f in [one] + companions(one):
            if os.path.isfile(f):
                going.append((f, bin_folder))
    from . import moves as M
    book = _Book()
    try:
        for f, bin_folder in going:
            M.shift(book, f, C.recycle_target(f, bin_folder))
    except OSError as exc:
        _gone(book.moves)
        raise Partly(f"{os.path.basename(f)} could not be moved to the Recycle "
                     f"Bin ({exc.strerror or exc}); {len(book.moves)} file(s) "
                     f"before it were", moves=book.moves) from exc
    _gone(book.moves)
    return {"deleted": True, "moves": book.moves, "kept": kept}


class Partly(Refused):
    """Stopped part-way, with `moves` saying what had already gone."""

    def __init__(self, message: str, moves=None):
        super().__init__(message)
        self.moves = list(moves or [])


class _Book:
    def __init__(self):
        self.moves: list = []


def _gone(moves) -> None:
    _forget([m[0] for m in moves])
    from . import acl
    acl.after_delete([m[0] for m in moves])


def undo(moves) -> dict:
    """Put deleted files back - only out of a Recycle Bin, only where empty."""
    back = 0
    for pair in moves or []:
        try:
            src_was, now = str(pair[0]), str(pair[1])
        except (TypeError, IndexError):
            continue
        if C.RECYCLE not in now.split(os.sep) or not os.path.isfile(now):
            continue
        if os.path.exists(src_was):
            continue
        ensure_folder(os.path.dirname(src_was))
        shutil.move(now, src_was)
        back += 1
    return {"restored": back}


# ------------------------------------------------------------ recent tags

def recent() -> list:
    try:
        with open(store_path(RECENT), encoding="utf-8") as fh:
            got = json.load(fh)
        return [str(x) for x in got if str(x).strip()][:KEEP_RECENT]
    except (OSError, ValueError):
        return []


def remember(word: str) -> None:
    have = [w for w in recent() if w.lower() != word.lower()]
    have.insert(0, word)
    try:
        tmp = store_path(RECENT) + ".part"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(have[:KEEP_RECENT], fh)
        os.replace(tmp, store_path(RECENT))
    except OSError:
        pass


def vocabulary(extra=()) -> list:
    """Tags to offer: recent ones first, then the colours' words, then these."""
    out = []
    words = list(recent())
    for d in L.defined():
        words += [d.name] + list(d.keywords)
    words += list(extra)
    for w in words:
        w = str(w or "").strip()
        if w and w.lower() not in {o.lower() for o in out}:
            out.append(w)
    return out


def colours() -> list:
    return [{"colour": d.colour, "name": d.name} for d in L.defined()]
