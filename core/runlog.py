"""What was actually done, kept after the page is closed.

The Windows app had a log and this did not, and the difference shows the first
time something goes wrong overnight: a scheduled re-mirror runs at 3am, moves
four hundred files, and the only record of it was a progress bar nobody was
watching. "What happened to this folder" then has no answer at all.

So every run that WRITES is recorded: when, which task, what it was pointed at,
how much it did, how much failed, and the lines it said about itself. Previews
are not recorded - a plan that changed nothing is not history, and a log full of
"looked at 40,000 photos" is a log nobody reads.

One file, newest last, one JSON object per line. Deliberately not a database:
it survives being opened in Notepad, being copied off the NAS, and being read by
something that is not this app - which is most of what a log is for. It is
trimmed to the last few hundred runs so it cannot grow without limit on a NAS
nobody is watching.
"""

from __future__ import annotations

import json
import os
import threading
import time

from .store import store_path  # noqa: F401  - re-exported for the History tab

FILE = "runs.jsonl"
COUNT = "runs.count"        # the serial the next run will carry
KEEP = 400                  # runs kept; older ones fall off the top
DETAILS = 40                # lines of a run's own words kept with it
MOVES = 20_000              # moves kept with a run, so it can be put back


def _path() -> str:
    return store_path(FILE)


_NUMBERING = threading.Lock()
_LAST_WHEN = 0.0


def _moment() -> float:
    """The moment a run finished, and never the same one twice.

    The log names a run by when it finished, to the millisecond, and two runs
    CAN finish inside one millisecond - a flow of quick steps, or two devices
    pressing at once. When they do, "put that run back" picks whichever line
    comes first in the file, which is how you reverse a run you did not mean.
    A thousandth of a second is worth less than that.
    """
    global _LAST_WHEN
    with _NUMBERING:
        now = round(time.time(), 3)
        if now <= _LAST_WHEN:
            now = round(_LAST_WHEN + 0.001, 3)
        _LAST_WHEN = now
        return now


def next_no() -> int:
    """The next run's number, and never the same one twice.

    A run needs a name you can say out loud - "put run 1042 back" - and the
    moment it finished is not one: it is sixteen digits, it is not in order on
    the screen, and two people reading the same log over a weekend cannot use it
    to mean the same run. The count is kept in its own small file rather than
    counted from the log, because the log is trimmed from the top and a number
    worked out by counting would start again at one the first time it was.
    """
    with _NUMBERING:
        here = store_path(COUNT)
        got = 0
        try:
            with open(here, "r", encoding="utf-8") as fh:
                got = int((fh.read() or "0").strip() or 0)
        except (OSError, ValueError):
            got = 0
        if got <= 0:            # first run after an upgrade: carry on from the log
            got = max([int(r.get("no") or 0) for r in read_lines()] or [0])
        got += 1
        try:
            with open(here, "w", encoding="utf-8") as fh:
                fh.write(str(got))
        except OSError:
            pass
        return got


def record(task: str, opts: dict, result, seconds: float = 0.0,
           by: str = "", cost: dict | None = None, action: str = "") -> dict:
    """Write one finished run. Best effort - a log that raises is worse than none.

    `by` is who started it - "" for you pressing a button, "automation" for the
    background loop. Kept because those two are read for different reasons: one
    you already know about, and the other is the whole point of a log.

    `cost` is what it took off the NAS - CPU seconds, bytes read and written.
    Recorded here rather than by each task, for the same reason the log itself
    is: one place, so nothing can forget.
    """
    folders = {k: v for k, v in (opts or {}).items()
               if isinstance(v, str) and os.sep in v}
    entry = {
        "when": _moment(),
        "no": next_no(),
        "task": task,
        # What was actually done, when the task's own name does not say it.
        # Deleting a photograph from the file manager and copying one into
        # another folder are both the "files" task, and a log that calls them
        # the same thing is a log you have to open each row of to read.
        "action": str(action or ""),
        "by": str(by or ""),
        "cost": dict(cost or {}),
        "folders": folders,
        "done": int(getattr(result, "done", 0) or 0),
        "failed": int(getattr(result, "failed", 0) or 0),
        "cancelled": bool(getattr(result, "cancelled", False)),
        "seconds": round(float(seconds or 0), 1),
        "stats": [list(s) for s in (getattr(result, "stats", []) or [])],
        # `lines()` where the result has one: the grouped causes are the
        # part worth keeping, and a log of sixty file names with no reason
        # beside them is what made "28 failed" unanswerable a week later.
        "details": list((result.lines() if hasattr(result, "lines")
                         else getattr(result, "details", [])) or [])[:DETAILS],
        # Every file this run moved, so it can be put back. Kept here rather
        # than anywhere cleverer for the same reason the log is one flat file:
        # it survives being copied off the NAS and read by something that is
        # not this app, which is most of what a record is for.
        "moves": [list(m) for m in (getattr(result, "moves", []) or [])][:MOVES],
    }
    try:
        with open(_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        _trim()
    except (OSError, ValueError):
        pass
    # And the space it gave back, into a record that is never trimmed.
    if getattr(result, "reclaimed", 0):
        from . import reclaimed as _reclaimed
        _reclaimed.add(task, int(result.reclaimed),
                       str(getattr(result, "reclaim_kind", "") or ""))
    return entry


def _trim() -> None:
    try:
        if os.path.getsize(_path()) < 400_000:
            return
        lines = read_lines()
        if len(lines) <= KEEP:
            return
        tmp = _path() + ".part"
        with open(tmp, "w", encoding="utf-8") as fh:
            for line in lines[-KEEP:]:
                fh.write(json.dumps(line) + "\n")
        os.replace(tmp, _path())
    except (OSError, ValueError):
        pass


def read_lines() -> list:
    out = []
    try:
        with open(_path(), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    got = json.loads(line)
                except ValueError:
                    continue        # one damaged line never costs you the rest
                if isinstance(got, dict):
                    out.append(got)
    except OSError:
        pass
    return out


def one(when: float):
    """One run, by the moment it finished. "" when there is no such run.

    The time is the id: the log has no row numbers, it is appended to by every
    run and trimmed from the top, so anything counted from either end stops
    meaning the same run within a day.
    """
    want = round(float(when or 0), 3)
    for got in read_lines():
        if round(float(got.get("when") or 0), 3) == want:
            return got
    return None


def by_no(no: int):
    """One run, by the number on it. None when there is no such run."""
    try:
        want = int(no or 0)
    except (TypeError, ValueError):
        return None
    if want <= 0:
        return None
    for got in read_lines():
        if int(got.get("no") or 0) == want:
            return got
    return None


def forget(task: str = "", days: float = 0.0) -> dict:
    """Throw away log lines. Returns what went and what is left.

    The list could be trimmed by age and never emptied, which is wrong on a NAS
    read from three devices: you come back to the desk to a page of runs you
    already read on the phone, and there is nothing to be done about it. So this
    exists, it says how many lines it would remove before it removes them, and
    it is a run like any other - which means it is in the log it just emptied.
    """
    lines = read_lines()
    cut = float(time.time() - days * 86400) if days else 0.0
    keep = []
    for got in lines:
        if task and str(got.get("task") or "") != task:
            keep.append(got)
            continue
        if cut and float(got.get("when") or 0) >= cut:
            keep.append(got)
            continue
        if not task and not cut:
            continue            # everything goes
    gone = len(lines) - len(keep)
    if gone <= 0:
        return {"gone": 0, "left": len(keep)}
    try:
        tmp = _path() + ".part"
        with open(tmp, "w", encoding="utf-8") as fh:
            for line in keep:
                fh.write(json.dumps(line) + "\n")
        os.replace(tmp, _path())
    except (OSError, ValueError) as exc:
        raise OSError(f"the log could not be rewritten: {exc}") from exc
    return {"gone": gone, "left": len(keep)}


def would_forget(task: str = "", days: float = 0.0) -> int:
    """How many lines `forget` would remove, without removing them."""
    lines = read_lines()
    cut = float(time.time() - days * 86400) if days else 0.0
    n = 0
    for got in lines:
        if task and str(got.get("task") or "") != task:
            continue
        if cut and float(got.get("when") or 0) >= cut:
            continue
        n += 1
    return n


def recent(limit: int = 100, task: str = "") -> list:
    """The newest runs first, optionally only one task's."""
    got = read_lines()
    if task:
        got = [g for g in got if g.get("task") == task]
    got.reverse()
    return got[:max(1, int(limit or 100))]
