"""How much space this app has given back - kept, because it cannot be measured.

Once a pile is emptied the files are gone, and nothing on the disk says they
were ever there; the only record of "you got 180 GB back this year" is one
written at the moment it happened. So every run that frees space, or puts it
aside to be freed, adds one line here - and the Clean up tab adds them up.

Two kinds, never mixed, because they are different claims:

- **freed** - really gone, by Clean up (or into DSM's recycle bin, which DSM
  empties on its own schedule);
- **put aside** - moved into a _Culled or _Duplicates pile by a cull, a
  thinning, a duplicate check or the blur finder. Still on the disk, and the
  space you WILL get back when the pile is emptied.

Kept apart from the run log on purpose: that keeps the last few hundred runs
and throws the rest away, which is right for "what happened last night" and
wrong for "what has this saved me since I started using it".
"""

from __future__ import annotations

import json
import os
import time

from .store import store_path

FILE = "reclaimed.jsonl"
FREED, ASIDE = "freed", "aside"


def _path() -> str:
    try:
        return store_path(FILE)
    except Exception:                                  # noqa: BLE001
        return ""


def add(task: str, size: int, kind: str) -> bool:
    """One run's worth. Nothing is written for nothing. Never raises."""
    size = int(size or 0)
    if size <= 0 or kind not in (FREED, ASIDE) or not _path():
        return False
    try:
        with open(_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"when": time.time(), "task": task,
                                 "bytes": size, "kind": kind}) + "\n")
        return True
    except OSError:
        return False


def lines() -> list:
    out = []
    where = _path()
    if not where or not os.path.exists(where):
        return out
    try:
        with open(where, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    got = json.loads(line)
                except ValueError:
                    continue
                if isinstance(got, dict) and isinstance(got.get("bytes"), int):
                    out.append(got)
    except OSError:
        pass
    return out


def summary(now: float | None = None) -> dict:
    """Totals: all time, this year, and the last run that freed anything."""
    now = time.time() if now is None else now
    year = time.localtime(now).tm_year
    out = {"freed": 0, "freed_year": 0, "aside": 0, "aside_year": 0,
           "last_freed": None, "runs": 0}
    for row in lines():
        this_year = time.localtime(row.get("when", 0)).tm_year == year
        if row.get("kind") == FREED:
            out["freed"] += row["bytes"]
            out["freed_year"] += row["bytes"] if this_year else 0
            if not out["last_freed"] or row["when"] > out["last_freed"]["when"]:
                out["last_freed"] = row
        elif row.get("kind") == ASIDE:
            out["aside"] += row["bytes"]
            out["aside_year"] += row["bytes"] if this_year else 0
        out["runs"] += 1
    return out
