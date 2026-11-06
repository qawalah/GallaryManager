"""Path arithmetic, done carefully because getting it wrong scatters files.

Small module, but every function in it exists because the Windows version got
that exact thing wrong once and moved photos somewhere unexpected.
"""

from __future__ import annotations

import os
import shutil

CULLED = "_Culled"           # things put aside, recoverable
NO_LOCATION = "_NoLocation"  # originals kept before a location was written
DUPLICATES = "_Duplicates"

# Folders this app made, which should never be scanned as if they held originals
OURS = {CULLED.lower(), NO_LOCATION.lower(), DUPLICATES.lower()}


def is_ours(name: str) -> bool:
    return name.strip().lower() in OURS


def skip_folder(name: str) -> bool:
    """Folders nothing should walk into: ours, and the ones you told it to skip.

    Read from the settings each time rather than captured once, so changing the
    list on the Setup tab takes effect without a restart.
    """
    clean = name.strip().lower()
    if clean in OURS or clean.startswith("@eadir"):
        return True
    try:
        from . import settings as _s
        return clean in _s.load().ignored()
    except Exception:                                # noqa: BLE001
        return False


def anchor_for(given: str, scanned: str) -> tuple[str, str]:
    """The tree `scanned` sits in - the root every mirror is measured from.

    Returns (anchor, a warning when it had to be assumed). The anchor is always
    usable; the warning is empty when it was actually known.

    This exists because the obvious fallback is silently destructive. Mirroring
    measures a folder's position from an anchor; fall back to "the folder being
    scanned" when the anchor is unknown and the position becomes empty, so every
    preview of `Photos/2022/Spain` lands directly in the top of the previews
    tree - flat, mixed in with every other shoot, and nothing said a word. It
    looks like it worked.

    So the anchor is worked out and, when it cannot be, the task refuses. There
    is one clear fix for that - fill in the library on the Setup tab - and it is
    the thing everybody is meant to do first anyway.
    """
    given = (given or "").strip()
    if given:
        return given, ""
    scanned = (scanned or "").strip()
    try:
        from . import settings as _s
        saved = _s.load()
    except Exception:                              # noqa: BLE001
        saved = None
    best = ""
    if saved is not None and scanned:
        for key in ("library", "raw", "previews"):
            root = str(saved[key] or "").strip()
            if root and under(scanned, root) and len(root) > len(best):
                best = root
    if best:
        return best, ""
    return scanned, (
        "Nothing says which tree that folder belongs to, so its position is being "
        "measured from the folder itself - which means everything lands in the TOP "
        "of the other trees rather than in a matching sub-folder. That is almost "
        "never what is wanted, and it looks like it worked. Fill in the library on "
        "the Setup tab and it will mirror properly.")


def mirror_anchor(given: str, scanned: str, into: str) -> tuple[str, str]:
    """The anchor to mirror from, and a REFUSAL when it had to be guessed.

    `anchor_for` explains why a guessed anchor is dangerous and then hands back
    a warning, and every task that used it put that warning in its notes - one
    sentence among ten, under a table that looked perfectly fine. It was not
    enough: the photographs land in the TOP of the other tree, flat, mixed in
    with every other shoot, and the run reports complete success.

    So when something is actually going to be WRITTEN into another tree, a
    guessed anchor is a refusal rather than a note. `into` is that tree; with no
    destination there is nothing to flatten and the guess costs nothing, which
    is why this takes it rather than assuming.
    """
    anchor, guessed = anchor_for(given, scanned)
    if not guessed or not str(into or "").strip():
        return anchor, ""
    return anchor, (
        f"Nothing says which tree {scanned} belongs to, so its position would be "
        f"measured from the folder itself - and every photo would land "
        f"directly in the top of {into}, flat, mixed in with every other shoot. "
        f"It would look like it worked. Fill in the library on the Setup tab, or "
        f"type it into 'The library (the anchor)' below, and it will mirror "
        f"properly.")


def follow(picked: str, from_root: str, to_root: str) -> str:
    """The same position in the other tree - what a form should fill in for you.

    Pick `Photos/2022/Spain` and the RAW box should say `Photos Raw/2022/Spain`,
    not `Photos Raw`. Typing the same sub-path into three boxes, correctly, is
    the chore that Browse only halved.

    Returns the other ROOT when the picked folder is the root itself or sits
    outside it - there is no position to follow to, and inventing one would be a
    guess dressed as an answer.
    """
    if not to_root:
        return ""
    if not picked or not from_root or not under(picked, from_root):
        return to_root
    rel = relative_under(picked, from_root)
    return os.path.join(to_root, rel) if rel else to_root


def as_tree_root(given: str, scanned: str, anchor: str) -> str:
    """The TOP of a tree, whether you were handed the top or the matching folder.

    The other half of `follow`. Once a form fills the RAW box with
    `Photos Raw/2022/Spain`, every task that mirrors into that box would write
    the position twice - `Photos Raw/2022/Spain/2022/Spain/x.RW2` - because a
    mirroring destination is supposed to be the top of the tree.

    `strip_mirrored_tail` was written for exactly this and then never called by
    anything, which is why the form could not safely be made helpful until now.
    A path whose tail does NOT match is left alone: pointing at an unrelated
    folder on purpose still works.
    """
    given = (given or "").strip()
    if not given or not scanned or not anchor:
        return given
    rel = relative_under(scanned, anchor)
    if not rel:
        return given
    return strip_mirrored_tail(given, rel) or given


def normalise(path: str) -> str:
    """Trim, unquote, and settle on one separator. Never raises."""
    if not path:
        return ""
    p = path.strip().strip('"').strip("'")
    p = p.replace("\\", os.sep).replace("/", os.sep)
    return p.rstrip(os.sep) or p


def under(path: str, root: str) -> bool:
    """Is `path` inside `root`?

    The separator check is the whole point. Comparing prefixes alone says
    `N:\\Photos Raw` is inside `N:\\Photos`, which it very much is not - and that
    mistake is invisible until files start landing in the wrong tree.
    """
    p, r = normalise(path), normalise(root)
    if not p or not r:
        return False
    try:
        p, r = os.path.realpath(p), os.path.realpath(r)
    except OSError:
        pass
    if p.lower() == r.lower():
        return True
    return p.lower().startswith(r.lower() + os.sep)


def relative_under(path: str, root: str) -> str:
    """Where `path` sits beneath `root`, or just its leaf if it sits outside.

    Returning the leaf rather than raising matters: a stray folder outside the
    library should land somewhere sane instead of stopping the whole run, and it
    must never produce a path built from the wrong root.
    """
    p, r = normalise(path), normalise(root)
    if not p:
        return ""
    if not r:
        return os.path.basename(p)
    if p.lower() == r.lower():
        return ""
    if under(p, r):
        try:
            return os.path.relpath(os.path.realpath(p), os.path.realpath(r))
        except (OSError, ValueError):
            return p[len(r):].lstrip(os.sep)
    return os.path.basename(p)


def mirror(path: str, from_root: str, to_root: str) -> str:
    """The same position, in the other tree."""
    rel = relative_under(path, from_root)
    return os.path.join(to_root, rel) if rel else to_root


def strip_mirrored_tail(destination: str, relative: str) -> str | None:
    """Take the scanned folder's own position off the end of a destination.

    A mirroring destination is the TOP of the other tree. Hand it the *matching*
    folder instead - the obvious thing to reach for - and the position is written
    twice:

        ...\\Photos Raw\\GH4\\Spain  +  GH4\\Spain
          ->  ...\\Photos Raw\\GH4\\Spain\\GH4\\Spain

    Compared segment by segment, so `Spain 22` is never mistaken for the tail of
    `Spain 22_2`. Returns None when there is nothing to strip.
    """
    dst = normalise(destination)
    if not dst or not relative:
        return None
    rel_parts = [x for x in relative.replace("\\", "/").split("/") if x]
    dst_parts = [x for x in dst.replace("\\", "/").split("/")]
    if not rel_parts or len(dst_parts) <= len(rel_parts):
        return None            # never strip the tree away entirely
    tail = dst_parts[-len(rel_parts):]
    if [t.lower() for t in tail] != [r.lower() for r in rel_parts]:
        return None
    # Answer in the separator the CALLER used, not whichever one this machine
    # prefers - normalise() has already rewritten them, so asking it gives "/"
    # on Linux for a path the caller wrote with backslashes.
    sep = "\\" if "\\" in destination else "/"
    return sep.join(dst_parts[:-len(rel_parts)]) or None


def common_root(paths) -> str:
    """The deepest folder every one of these sits inside.

    Compared SEGMENT by segment, never as text. `Photos` and `Photos Raw` share
    eight characters and share no folder at all, and a common root worked out by
    characters would hand back `.../Photos` for a pair that has nothing in common
    but a prefix - and then a sort would build its new folders there.

    One path answers itself. No paths answer with "".
    """
    real = [normalise(p) for p in paths if p and str(p).strip()]
    if not real:
        return ""
    if len(real) == 1:
        return real[0]
    sep = "\\" if "\\" in real[0] else os.sep
    split = [[bit for bit in p.replace("\\", "/").split("/")] for p in real]
    shared: list = []
    for parts in zip(*split):
        first = parts[0]
        if any(x.lower() != first.lower() for x in parts):
            break
        shared.append(first)
    if not shared or (len(shared) == 1 and shared[0] == ""):
        return ""              # nothing above them but the root of the machine
    return sep.join(shared) or sep


def without_nested(paths) -> list:
    """These folders, with any that sit inside another dropped.

    Picking a folder and its parent is an easy thing to do with a chip list, and
    walking both counts every photograph under the child twice - which turns into
    two rows proposing to move the same file to the same place.
    """
    keep: list = []
    for path in sorted({normalise(p) for p in paths if p and str(p).strip()},
                       key=len):
        if not any(under(path, other) for other in keep):
            keep.append(path)
    return keep


def preview_for(path: str, library: str, previews: str) -> str:
    """Where the preview of this photograph lives. Always ends .jpg.

    Here rather than in the previews task because three tasks need the answer and
    two of them were working it out with plain `mirror`, which keeps the original
    extension. `DSC001.JPG` then looks for `DSC001.JPG` in the previews tree while
    the preview is called `DSC001.jpg` - and on Windows that works, because the
    filesystem does not care about case, and on the NAS it silently does not. The
    preview is simply never found: culling leaves it behind, thinning a bracket
    leaves it behind, and the previews tree quietly fills up with photographs the
    library no longer has.
    """
    return os.path.splitext(mirror(path, library, previews))[0] + ".jpg"


def companions(path: str) -> list[str]:
    """The sidecars sitting beside a file, which must travel with it.

    An .xmp is a note ABOUT one file - the rating, the location - and on its own
    it is silent rubbish. Move a RAW and leave its sidecar behind and the rating
    you made is not lost loudly, it is lost quietly: the RAW reads as unrated
    from then on, and a later cull judges it on that.
    """
    stem, _ = os.path.splitext(path)
    found = []
    for ext in (".xmp", ".XMP"):
        side = stem + ext
        if side != path and os.path.isfile(side) and side not in found:
            found.append(side)
    return found


def developed_name() -> str:
    """What the subfolder of finished exports is called - Developed, Curated.

    Read every time rather than captured, because it is a setting you may rename
    and the answer has to be the current one. Blank when exports are filed
    straight in beside their originals, where they are ordinary photographs and
    nothing here applies.
    """
    try:
        from . import settings as _s
        return str(_s.load()["filed_into"] or "").strip()
    except Exception:                                  # noqa: BLE001
        return ""


def developed_beside(path: str, folder_name: str = "") -> list[str]:
    """The finished versions of this photograph, in the subfolder beside it.

    These are the one thing in a library that CANNOT be found again by looking.
    Everything else this app moves is paired by what it is - capture time,
    camera, name - and an export shares all three with its original, which is
    exactly why it has to live in a subfolder of its own and be left out of
    every scan. The cost of that is it cannot be re-matched later: re-sort a
    library and the exports stay in the old shape, beside a folder the
    photographs have left.

    So they travel with the original, and what ties them is where they are and
    what they are called: `<shoot>/Developed/P1000123.jpg` belongs to
    `<shoot>/P1000123.RW2`. That is not a guess - it is how filing put them
    there. A second export of the same photograph is `P1000123_1.jpg`, which is
    this app's own way of not overwriting, so those come too.
    """
    folder_name = folder_name or developed_name()
    if not folder_name:
        return []
    where = os.path.join(os.path.dirname(path), folder_name)
    if not os.path.isdir(where):
        return []
    stem = os.path.splitext(os.path.basename(path))[0].lower()
    found = []
    try:
        for name in sorted(os.listdir(where)):
            mine = os.path.splitext(name)[0].lower()
            tail = mine[len(stem):] if mine.startswith(stem) else None
            if mine == stem or (tail and tail.startswith("_") and tail[1:].isdigit()):
                one = os.path.join(where, name)
                if os.path.isfile(one):
                    found.append(one)
    except OSError:
        return []
    return found


def developed_target(developed: str, photo_target: str,
                     folder_name: str = "") -> str:
    """Where a finished version goes when its photograph moves.

    Into a subfolder of the same name at the NEW place - so a shoot that splits
    across three date folders takes its exports apart with it, each beside the
    photograph it came from.
    """
    folder_name = folder_name or developed_name()
    return os.path.join(os.path.dirname(photo_target), folder_name,
                        os.path.basename(developed))


def safe_target(path: str) -> str:
    """A path nothing already occupies, by adding _1, _2 ... if needed."""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{stem}_{n}{ext}"):
        n += 1
    return f"{stem}_{n}{ext}"


def ensure_folder(path: str) -> None:
    """Make a folder, and every level of it, looking like the one above it.

    `os.makedirs` alone leaves each new level owned by whoever is running -
    so a new year folder and the shoot inside it are the app's while the
    library around them is yours, and Synology Drive stops seeing a tree it
    can no longer read. `perms.make_folder` makes them one at a time, each
    taking after its parent, which is what DSM would have done itself.
    """
    if path and not os.path.isdir(path):
        from . import perms
        perms.make_folder(path)
        if not os.path.isdir(path):           # a race, or a refusal - say it the
            os.makedirs(path, exist_ok=True)  # old way rather than not at all


# Left behind by something else, in a folder that is otherwise empty. A Mac
# leaves .DS_Store in every folder it opens, Windows leaves Thumbs.db and
# desktop.ini, and an empty-folder sweep that asks os.listdir finds a list and
# stops - so these files, and only these, may be removed to let a folder that
# is otherwise empty go.
#
# Named exactly, and only ever removed from a folder that has nothing else in
# it. A folder with one photograph and a Thumbs.db is not empty and is not
# touched.
LEFTOVERS = {"@eadir", "#recycle", "@recycle", ".ds_store", "thumbs.db",
             "desktop.ini", ".@__thumb", "@transcode"}

# Folders that are never litter, whatever is in them. `#recycle` and `@recycle`
# are the share's Recycle Bin: everything anybody ever deleted from File
# Station, this app's own Delete included, and removing one empties the bin
# for good. `@eaDir` is DSM's own index of the folder it sits in. A folder that
# holds any of them is not empty, so it stays - the sweep that once removed
# them is how a cull near a share root could take the Recycle Bin with it.
NOT_LITTER = {"#recycle", "@recycle", "@eadir"}


def only_leftovers(folder: str) -> list:
    """What is in this folder, if all of it is somebody else's litter FILES.

    Returns the files to remove, or None when there is anything real here -
    which is the answer that must be trusted, because getting it wrong deletes a
    folder with photographs in it. Any folder inside counts as real: litter is
    a file, never a tree, so nothing here ever needs removing recursively.
    """
    try:
        entries = os.listdir(folder)
    except OSError:
        return None
    for name in entries:
        low = name.strip().lower()
        if low in NOT_LITTER or low not in LEFTOVERS:
            return None
        if os.path.isdir(os.path.join(folder, name)):
            return None
    return entries


def _stops(stop_at) -> list:
    """The folders a tidy never removes and never climbs above.

    Whatever the caller named - the folder the task was run on - plus every
    tree in Setup, because the top of the library or the RAW tree is never
    "a folder that emptied out", however empty it is.
    """
    if isinstance(stop_at, str):
        stop_at = [stop_at]
    out = [str(s).strip() for s in (stop_at or []) if str(s or "").strip()]
    try:
        from . import settings
        saved = settings.load()
        for key in settings.TREES + ("inbox",):
            try:
                one = str(saved[key] or "").strip()
            except (KeyError, TypeError):
                continue
            if one:
                out.append(one)
    except Exception:                                      # noqa: BLE001
        pass
    return [_real(s) for s in out]


def _real(path: str) -> str:
    try:
        return os.path.realpath(normalise(path)).lower()
    except (OSError, ValueError):
        return normalise(os.path.abspath(path)).lower()


def roots_of(opts) -> list:
    """Every folder a task was pointed at, from its options: the boundary a
    tidy after it stops at. Any option whose value is an existing folder counts,
    a multi-line one line by line."""
    out = []
    for value in (opts or {}).values():
        if not isinstance(value, str):
            continue
        for line in value.splitlines():
            line = line.strip()
            if line and os.path.isabs(line) and os.path.isdir(line) \
                    and line not in out:
                out.append(line)
    return out


def tidy_empty_folders(folders, stop_at=None) -> int:
    """Remove folders that emptied out, and their parents if those emptied too.

    Only ever removes a directory holding nothing of yours - empty, or empty
    apart from the litter files other software leaves in it. Walks upward
    because moving one shoot usually empties the shoot folder and then its
    year folder above it - but only as far as `stop_at`, the folder the task
    was run on, and never removing it or any tree in Setup. Without a boundary
    above it a folder is removed on its own and nothing above it is touched:
    the climb is what once reached a share root and took its Recycle Bin.
    """
    stops = _stops(stop_at)

    def is_stop(path: str) -> bool:
        return _real(path) in stops

    def climbs(path: str) -> bool:
        return any(under(path, s) and not is_stop(path) for s in stops)

    removed = 0
    for start in sorted(set(folders), key=len, reverse=True):
        here = start
        while here and os.path.isdir(here) and not is_stop(here):
            if os.path.basename(normalise(here)).strip().lower() in NOT_LITTER:
                break                   # the Recycle Bin itself, even emptied
            litter = only_leftovers(here)
            if litter is None:
                break
            try:
                for name in litter:
                    os.remove(os.path.join(here, name))
                parent = os.path.dirname(here)
                os.rmdir(here)
                removed += 1
            except OSError:
                break
            if parent == here or not climbs(parent):
                break
            here = parent
    return removed


def same_place(folders, keys=("raw", "previews")) -> list:
    """Each folder, plus the SAME position in the other trees, where it exists.

    "Take the location off Photos/2022/Spain" means Spain in the RAW tree and
    Spain in the previews tree as well - not the whole of either. Two tabs got
    that wrong in the same way before this existed: they offered the other
    trees as boxes, the form helpfully followed them to the matching shoot, and
    the tree-settling that is right for a MIRRORING destination then trimmed
    them back to the top of the tree. One shoot's worth of intent, applied to
    every negative on the disk.

    So this answers the question the person actually asked, from Setup's trees,
    and never widens it. A folder outside the library has no position in the
    other trees and gets none - it is not guessed at.
    """
    from . import settings as _s
    saved = _s.load()
    lib = str(saved["library"] or "").strip()
    out = []
    for one in folders or []:
        one = str(one or "").strip()
        if not one:
            continue
        if one not in out:
            out.append(one)
        if not lib or not under(one, lib):
            continue
        for key in keys:
            root = str(saved[key] or "").strip()
            if not root:
                continue
            there = mirror(one, lib, root)
            if there and os.path.isdir(there) and there not in out:
                out.append(there)
    return out
