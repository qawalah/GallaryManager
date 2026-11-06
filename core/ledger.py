"""What has already been developed, so it is never sent out to be done twice.

The develop loop only works if it has a memory. Without one, every run looks at
the library, sees a five-star photo, and copies it to the tablet again - forever,
including everything finished months ago. The folder never empties and the
question "what still needs developing" has no answer.

**Kept by identity, not by path.** capture time + camera + base name, the same
three things a RAW is paired to its JPEG by. A path would break the first time a
shoot is renamed, and renaming shoots is a thing this app actively encourages;
worse, it would break silently, and the symptom would be a tablet slowly filling
up with work already done.

This is the one place in the app that remembers rather than measures, and it is
deliberate: "was this developed" cannot be read off the files, because a photo
you developed and one you have not look identical in the library. Everything
that CAN be measured still is.

One JSON object per line, in the config volume. It survives a Restart, opens in
Notepad, and one damaged line costs that entry rather than the file.
"""

from __future__ import annotations

import json
import os
import time

from .store import store_path

FILE = "developed.jsonl"


def _path() -> str:
    return store_path(FILE)


def key(ident) -> str:
    """One identity, as a line of text. Stable, printable, and comparable."""
    return f"{ident.base}|{ident.model}|{ident.taken}"


def read() -> dict:
    """Everything recorded as developed, keyed by identity. Never raises.

    A photo you asked to develop AGAIN is not in here - see `forget` - so the
    rest of the app sees it as not developed, which is what you asked for.
    """
    return {k: v for k, v in _all().items() if not v.get("again")}


def again() -> set:
    """The photos you asked to develop again, and have not been filed since.

    Kept apart because one feature has to know the difference between "never
    developed" and "developed, and you want another go": Send to develop now
    SPOTS a finished edit sitting beside a photo and counts it as done. For a
    photo you deliberately put back in the queue, that edit is exactly the one
    you were unhappy with - and counting it would quietly undo your decision.
    """
    return {k for k, v in _all().items() if v.get("again")}


def _all() -> dict:
    """Every line, the latest per identity winning."""
    out: dict = {}
    try:
        with open(_path(), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    got = json.loads(line)
                except ValueError:
                    continue            # one damaged line, not the whole file
                if isinstance(got, dict) and got.get("key"):
                    out[got["key"]] = got
    except OSError:
        pass
    return out


def add(entries) -> int:
    """Record what has been developed. Best effort; returns how many were written."""
    rows = list(entries or [])
    if not rows:
        return 0
    try:
        with open(_path(), "a", encoding="utf-8") as fh:
            for row in rows:
                row = dict(row)
                row.setdefault("when", time.time())
                fh.write(json.dumps(row) + "\n")
        return len(rows)
    except OSError:
        return 0


def forget(keys) -> int:
    """Take entries back out - for a photo you want to develop again.

    Rewritten rather than appended to, because "developed" has to be able to
    become "not developed": re-rating a photo you were unhappy with and finding
    the app refuses to send it back out would be the feature working against you.
    """
    drop = {k for k in (keys or []) if k}
    if not drop:
        return 0
    kept = [row for row in _all().values() if row.get("key") not in drop]
    # Not simply removed: marked AGAIN, so the edit you were unhappy with -
    # still sitting in the Developed folder - is not spotted and counted as
    # done on the very next run. Filing a new export replaces the mark.
    kept += [{"key": k, "again": True, "when": time.time()} for k in sorted(drop)]
    try:
        tmp = _path() + ".part"
        with open(tmp, "w", encoding="utf-8") as fh:
            for row in kept:
                fh.write(json.dumps(row) + "\n")
        os.replace(tmp, _path())
    except OSError:
        return 0
    return len(drop)
