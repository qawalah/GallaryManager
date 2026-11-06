"""Where the app keeps its own files.

One folder, chosen once. On the NAS it is a mounted volume so it survives the
container being rebuilt; on a PC it sits beside the code. `PM_DATA` overrides
both, which is what the container sets.
"""

from __future__ import annotations

import os

_DEFAULT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "config")


class Unwritable(RuntimeError):
    """The data folder cannot be written to. Said plainly, not as a traceback."""


# The folder is made once, not on every path lookup.
#
# `store_path` calls this, and `store_path` is called from inside per-photograph
# loops - so a screen that asked for a setting three hundred thousand times also
# asked the filesystem to create a folder that had existed since the app
# started, three hundred thousand times. On a mounted volume that was most of
# the cost. The check still happens on the first call, which is the one that has
# to fail clearly.
_MADE: set = set()


def data_dir(must_write: bool = True) -> str:
    """Where the app keeps its settings and its imported timeline.

    On the NAS the code is mounted read-only on purpose - it is a copy of what is
    on the PC and nothing should be writing into it - so the one folder that DOES
    have to be writable is worth failing clearly about. A traceback about
    makedirs, from inside a container, at the bottom of a log, is not a message
    anyone can act on.
    """
    folder = os.environ.get("PM_DATA") or _DEFAULT
    if folder in _MADE:
        return folder
    try:
        os.makedirs(folder, exist_ok=True)
        _MADE.add(folder)
    except OSError as exc:
        if must_write:
            raise Unwritable(
                f"Cannot write to {folder}.\n"
                f"    Set PM_DATA to a folder the app can write to. In the "
                f"container that is the /config volume;\n"
                f"    on a PC it is the 'config' folder beside the code."
            ) from exc
    return folder


def writable() -> tuple[bool, str]:
    """Whether settings can actually be saved, and where. Never raises."""
    folder = os.environ.get("PM_DATA") or _DEFAULT
    try:
        os.makedirs(folder, exist_ok=True)
        probe = os.path.join(folder, ".writable")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        return True, folder
    except OSError as exc:
        return False, f"{folder} ({exc.strerror or exc})"


def store_path(name: str) -> str:
    return os.path.join(data_dir(), name)
