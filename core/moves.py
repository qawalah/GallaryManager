"""Moving a file, written down so the run can be taken back.

Eleven features in this app move photographs, and until now each of them did it
the same way in its own words:

    ensure_folder(dirname(dst)); shutil.move(src, safe_target(dst))

Three lines, repeated eleven times, and nowhere in the app that knew a file had
moved. So "I sorted the wrong folder" had one answer - sort it back by hand,
working out from the plan where four hundred files came from.

This is that line, once, with the one thing it was missing: it writes the move
down on the `Result`, which `core/runlog.py` keeps, which is what lets History
offer **Put it back**.

**It is not an undo stack and does not pretend to be.** It records what this run
moved, in order. Putting it back is itself a plan you read first, and it refuses
every move whose destination has since changed - because a photograph you rated,
renamed or moved again afterwards is not one this should quietly drag backwards.

**A copy is not recorded.** Sending to develop leaves the original where it is;
"undoing" that means deleting the copy, which is a different decision with a
different risk, and this does not make it look like the same one.
"""

from __future__ import annotations

import os
import shutil

from .paths import ensure_folder, safe_target

# How many moves one run keeps. A sort of a whole library is tens of thousands,
# and a log line that big is one nobody can open - but the run is still recorded
# and still says what it did, it simply cannot be put back in one press.
CAP = 20_000


class Interrupted(Exception):
    """Stop was pressed part-way through copying one file. The file is still
    where it was, and nothing half-copied was left behind."""


# A clip moved between two drives is copied in pieces this big, so the bar can
# say how far through it is and Stop does not have to wait for the whole file.
CHUNK = 8 * 1024 * 1024


def shift(result, source: str, target: str, on_bytes=None, cancelled=None) -> str:
    """Move one file, and write it down. Returns where it actually landed.

    The destination is made safe first - a name already taken gets a number -
    so what is recorded is where the file IS, not where it was aimed.

    `on_bytes(done, total)` and `cancelled()` are for files big enough to matter.
    A move inside one drive is a rename and over at once. A move to ANOTHER
    drive - on Windows, a library on one share and the video tree on another,
    which is how a Synology hands out `photo` and `video` - is a copy through
    this machine, and a 4 GB clip copied without a word looked exactly like a
    run that had hung.
    """
    target = safe_target(target)
    ensure_folder(os.path.dirname(target))
    if on_bytes is None and cancelled is None:
        shutil.move(source, target)
    else:
        _move_watched(source, target, on_bytes, cancelled)
    note(result, source, target)
    return target


def _move_watched(source: str, target: str, on_bytes, cancelled) -> None:
    """shutil.move, with the copy it falls back to done in pieces it reports."""
    try:
        os.rename(source, target)
        return
    except OSError:
        # Another drive (EXDEV, or WinError 17 on Windows). Anything else - the
        # file is open elsewhere, the folder is read-only - fails the copy too,
        # with a clearer error, and the source is never touched.
        pass
    total = os.path.getsize(source)
    done = 0
    made = False
    try:
        with open(source, "rb") as src, open(target, "xb") as dst:
            made = True
            while True:
                if cancelled is not None and cancelled():
                    raise Interrupted()
                piece = src.read(CHUNK)
                if not piece:
                    break
                dst.write(piece)
                done += len(piece)
                if on_bytes is not None:
                    on_bytes(done, total)
        shutil.copystat(source, target)
        # Only once the copy is whole. If the original cannot be removed - on
        # Windows, because another program has it open - the copy goes instead,
        # so the clip is in exactly one place either way.
        os.remove(source)
    except BaseException:
        try:
            if made and os.path.exists(source) and os.path.exists(target):
                os.remove(target)
        except OSError:
            pass
        raise


def note(result, source: str, target: str) -> None:
    """Record a move somebody else made. Never raises: a run must not fail
    because its own history could not be written."""
    try:
        moves = getattr(result, "moves", None)
        if moves is None or len(moves) >= CAP:
            return
        moves.append([source, target])
    except Exception:                                      # noqa: BLE001
        return


def can_put_back(moves) -> tuple:
    """(what can go back, in the order it would be done, and why the rest cannot).

    Walked NEWEST FIRST and simulated as it goes, because a run can move the
    same file twice - out of the library, and then into a pile - and judging
    each move against the disk on its own would refuse the first one for the
    crime of having been followed by the second.

    The refusals are the useful half: a file that is not where the run left it
    has been touched since, and dragging it backwards is how an afternoon's work
    is lost to a button that said Undo.
    """
    good, refused = [], []
    will_be, will_go = set(), set()

    def there(path: str) -> bool:
        if path in will_be:
            return True
        if path in will_go:
            return False
        return os.path.exists(path)

    for pair in reversed(list(moves or [])):
        if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
            continue
        source, target = str(pair[0]), str(pair[1])
        if not there(target):
            refused.append((target, "it is not where the run left it"))
            continue
        if there(source):
            refused.append((target, "something is back at the old name already"))
            continue
        good.append([source, target])
        will_go.add(target)
        will_be.add(source)
    return good, refused


def put_back(moves, result=None, progress=None, cancelled=None) -> dict:
    """Move each file back to where it came from.

    Takes the run's own list, in the order the run made it, and works out the
    order to reverse it in - so every caller hands over the same thing and only
    one place knows that it has to be done backwards.
    """
    good, refused = can_put_back(moves)
    done, failed = 0, 0
    for n, (source, target) in enumerate(good, 1):
        if cancelled and cancelled():
            break
        if progress and n % 20 == 0:
            progress(n, len(good), os.path.basename(target))
        try:
            ensure_folder(os.path.dirname(source))
            shutil.move(target, source)
            done += 1
            note(result, target, source)
        except OSError as exc:
            failed += 1
            if result is not None and hasattr(result, "blame"):
                result.blame(target, exc)
    return {"done": done, "failed": failed, "refused": refused}
