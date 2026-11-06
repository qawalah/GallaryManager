"""Putting a rewritten photograph in place of the old one, on every platform.

Every metadata write here is "write a temp file beside it, then `os.replace`" -
so a crash half way leaves the photograph as it was, never half written. On
Linux that replace succeeds whoever has the file open. On Windows it does not:
Explorer building a thumbnail, an antivirus scan or a backup tool reading the
file holds it open for a moment, and the replace fails with PermissionError -
the same error as a real lack of rights, though it clears itself a fraction of
a second later.

So on Windows the replace is tried again a few times, waiting a little longer
each time, before it is reported; anywhere else it is a plain `os.replace`,
because there the error is never the passing kind and waiting would only make a
real failure slower to say so.
"""

from __future__ import annotations

import os
import time

# Waits before each retry: five tries after the first, a little over six
# seconds in all - longer than a thumbnail or a scan holds a file, short enough
# that a file held for good is reported while somebody is still watching.
DELAYS = (0.2, 0.4, 0.8, 1.6, 3.2)


def _on_windows() -> bool:
    return os.name == "nt"


def replace_file(src: str, dst: str, retry: bool | None = None,
                 sleep=time.sleep) -> None:
    """`os.replace(src, dst)`, retried on Windows while another program has it.

    `retry` is worked out from the platform when not given; the tests pass it.
    The final failure names the file, because "Permission denied" alone does
    not say which of four hundred photographs was open somewhere.
    """
    if retry is None:
        retry = _on_windows()
    if not retry:
        os.replace(src, dst)
        return
    for wait in DELAYS:
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            sleep(wait)
    try:
        os.replace(src, dst)
    except PermissionError as exc:
        raise PermissionError(
            exc.errno,
            f"{os.path.basename(dst)} is in use by another program and could "
            f"not be replaced after {len(DELAYS) + 1} tries",
            dst) from exc
