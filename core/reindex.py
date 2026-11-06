"""Telling Synology that the files moved.

DSM keeps its own databases of what is on the disk - Media Indexing for Media
Server and DLNA, and a separate one inside Synology Photos - and neither of them
is the filesystem. Move a shoot with this app and the folder is on the disk
immediately and missing from Synology Photos until something tells it. That is
not a bug in either program; they are indexes, and an index that is not told is
out of date.

**The awkward part is where this app runs.** The indexers live on the DSM host
(`/usr/syno/bin`), and this app runs in a container that mounts one home folder
and nothing else. A container cannot call a program that is not inside it. So:

- if the tools ARE reachable - the app running on the NAS itself, or the paths
  bind-mounted in - they are run, per folder, and the result is reported;
- if they are not, which is the normal case, the app writes a small script
  holding exactly the commands for the folders that actually changed, for DSM's
  own Task Scheduler to run. No credentials, no SSH from the container, nothing
  stored that could leak.

**Only the folders that changed.** Every run of every task appends what it
touched to a queue, so re-indexing costs seconds rather than the hours a whole
library takes. Synology Photos is the exception: its re-index API takes no
folder, so that one is all or nothing and the script says so.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time

from .store import store_path

QUEUE = "reindex.txt"

# Where DSM keeps them. Checked for rather than assumed, because "it is not
# there" and "it is there and failed" are different answers and only one of them
# is worth acting on.
SYNOINDEX = ["/usr/syno/bin/synoindex", "/usr/bin/synoindex", "synoindex"]
SYNOWEBAPI = ["/usr/syno/bin/synowebapi", "/usr/bin/synowebapi", "synowebapi"]


def _queue_path() -> str:
    """Where the queue lives, or "" when there is nowhere to put it.

    The store REFUSES rather than inventing a folder when PM_DATA is wrong,
    which is right for settings and wrong for this: a re-index note is a
    convenience that can be recreated at any time, and taking a file move down
    with it would be a bad trade.
    """
    try:
        return store_path(QUEUE)
    except Exception:                                  # noqa: BLE001
        return ""


def remember(folders) -> int:
    """Add folders to the queue of what Synology has not been told about.

    Best effort, always: a re-index queue that raises during a file move would
    turn a working run into a failed one over something that can be done again
    at any time.
    """
    wanted = []
    for one in folders or []:
        one = str(one or "").strip()
        if one and one not in wanted:
            wanted.append(one)
    if not wanted:
        return 0
    if not _queue_path():
        return 0
    try:
        have = set(queued())
        fresh = [w for w in wanted if w not in have]
        if not fresh:
            return 0
        with open(_queue_path(), "a", encoding="utf-8") as fh:
            for one in fresh:
                fh.write(f"{time.time():.0f}\t{one}\n")
        return len(fresh)
    except OSError:
        return 0


def queued() -> list:
    """The folders waiting to be re-indexed, oldest first, without repeats."""
    out: list = []
    where = _queue_path()
    if not where:
        return []
    try:
        with open(where, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                _when, _, path = line.rstrip("\n").partition("\t")
                path = path.strip()
                if path and path not in out:
                    out.append(path)
    except OSError:
        return []
    return out


def clear() -> None:
    try:
        os.remove(_queue_path() or "")
    except OSError:
        pass


def nearest_existing(folder: str) -> str:
    """This folder, or the nearest one above it that is still there.

    A folder that was emptied and tidied away is exactly the case an index gets
    wrong - it goes on listing photographs that are not there - and it cannot be
    re-read, because it is gone. Its PARENT can, and re-reading the parent is
    what makes the index drop what it no longer holds. Walking up rather than
    giving up is the difference between telling DSM and not.
    """
    folder = str(folder or "").strip()
    seen = set()
    while folder and folder not in seen and folder not in ("/", os.sep):
        if os.path.isdir(folder):
            return folder
        seen.add(folder)
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    return folder if os.path.isdir(folder) else ""


def settle(folders) -> list:
    """The folders to actually re-index: existing, no repeats, no nesting.

    Folders inside another one in the list are dropped, because `-R` reads a
    folder and everything under it - telling DSM about a shoot AND about the
    year above it is the same work done twice.
    """
    out: list = []
    for one in folders or []:
        got = nearest_existing(one)
        if got and got not in out:
            out.append(got)
    keep: list = []
    for one in sorted(out, key=len):
        if not any(one == other or one.startswith(other.rstrip(os.sep) + os.sep)
                   for other in keep):
            keep.append(one)
    return keep


def folders_touched(rows) -> list:
    """Every folder a plan's rows read from or wrote to.

    BOTH ends, and this is the whole point: moving a shoot leaves one folder
    emptier and another one new, and an index told about only the new one still
    shows photographs that are not there any more.
    """
    out: list = []
    for row in rows or []:
        for path in (getattr(row, "source", ""), getattr(row, "target", "")):
            path = str(path or "").strip()
            if not path:
                continue
            folder = os.path.dirname(path) or path
            if folder not in out:
                out.append(folder)
    return out


# ------------------------------------------------------------------ the tools

def find(names) -> str:
    """The first of these that is actually here, or ""."""
    for name in names:
        if os.sep in name:
            if os.access(name, os.X_OK):
                return name
        else:
            got = shutil.which(name)
            if got:
                return got
    return ""


def available() -> dict:
    """What can be run from where this app is, right now."""
    return {"synoindex": find(SYNOINDEX), "synowebapi": find(SYNOWEBAPI)}


def index_command(folder: str, tool: str = "synoindex") -> list:
    """`synoindex -R <folder>` - Media Indexing, one folder at a time."""
    return [tool, "-R", folder]


def photos_command(user: str, personal: bool = False,
                   tool: str = "synowebapi") -> list:
    """Synology Photos' own re-index. Whole space; there is no folder argument.

    Two APIs, because Photos keeps the shared space and each person's space in
    separate libraries: SYNO.FotoTeam for the shared one, SYNO.Foto for yours.
    Must run as root - it is the only account DSM lets call synowebapi.
    """
    api = "SYNO.Foto.Index" if personal else "SYNO.FotoTeam.Index"
    return [tool, "--exec", f"api={api}", "method=reindex", "version=1",
            f"runner={user}", "type=basic"]


def run(command, seconds: int = 900) -> tuple[bool, str]:
    """Run one command. (worked, what it said). Never raises."""
    try:
        got = subprocess.run(command, capture_output=True, text=True,
                             timeout=seconds)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    said = (got.stdout or "").strip() or (got.stderr or "").strip()
    return got.returncode == 0, said[:400]


# ----------------------------------------------------------------- the script

HOW = """\
# Run this ON THE NAS, not in the container - the indexers live on DSM and a
# container cannot call them.
#
#   DSM > Control Panel > Task Scheduler > Create > Scheduled Task > User-defined script
#   User: root        (synowebapi will not run as anybody else)
#   Run command: bash "{where}"
#
# Set it to run every few hours, or press Run to do it now. It is safe to run
# when nothing has changed: re-indexing a folder that is already correct costs
# a moment and changes nothing.
"""


def script(folders, user: str = "", personal: bool = False,
           where: str = "") -> str:
    """A shell script that tells DSM about exactly these folders."""
    lines = ["#!/bin/sh", "", HOW.format(where=where or "the path this was saved to"),
             'INDEX="/usr/syno/bin/synoindex"', ""]
    if folders:
        lines.append("# Media Indexing: Media Server, DLNA, and Photo Station.")
        lines.append("# One folder at a time, so this costs seconds rather than")
        lines.append("# the hours a whole library takes.")
        for one in folders:
            lines.append(f'"$INDEX" -R {_quote(one)}')
        lines.append("")
    else:
        lines.append("# Nothing is queued - no folder has changed since the last run.")
        lines.append("")
    if user:
        lines.append("# Synology Photos keeps its own database, and its re-index")
        lines.append("# API takes no folder - it is the whole space or nothing.")
        lines.append("# This is the slow one; drop it if you do not use Photos.")
        lines.append(" ".join(_quote(bit) for bit in
                              photos_command(user, personal,
                                             "/usr/syno/bin/synowebapi")))
        lines.append("")
    lines.append("echo \"told DSM about %d folder(s)\"" % len(folders or []))
    return "\n".join(lines) + "\n"


def _quote(text: str) -> str:
    """Single-quoted for sh, safely - a folder name may hold anything at all."""
    text = str(text)
    if all(c.isalnum() or c in "-_./=:," for c in text):
        return text
    return "'" + text.replace("'", "'\\''") + "'"
