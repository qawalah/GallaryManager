"""What code is actually running, so a Restart can be checked rather than hoped.

The failure this exists for: copy new files onto the NAS, hit Restart, open the
page - and it looks exactly the same whether the new code loaded, the copy went
into the wrong folder, or the browser handed you a cached page from an hour ago.
Three very different problems, one identical symptom, and no way to tell them
apart from the outside. That is the worst kind of bug to sit in front of.

So the page says two things in its header, and between them they separate all
three:

    CODE    the newest timestamp of any source file the running process can see
    UP      when this process started

Copy new files and Restart: both change. Copy new files and the mount is wrong:
neither changes. Look at a cached page: the header is stale, and pressing
Refresh - which cannot be served from cache - shows the truth.

The stamp is read once at import, on purpose. It describes the code THIS process
loaded, which is the question being asked; re-reading it later would report the
files on disk instead, and quietly answer a different question.
"""

from __future__ import annotations

import os
import time

# The release. Bumped by hand when a build is handed over, so "which build is
# this" has an answer that does not depend on file dates: the CODE stamp says
# what the process loaded, and this says which release it belongs to.
RELEASE = "4.0.0"

WHEN_STARTED = time.time()


def _newest(folder: str) -> float:
    newest = 0.0
    for here, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in names:
            # The page's own files count too: they live in app/web as .html,
            # .css, .js, .svg and the typeface's .woff2, and a change to one is
            # a change to the app.
            if not name.endswith((".py", ".sh", ".yml",
                                  ".html", ".css", ".js", ".svg", ".woff2")):
                continue
            try:
                newest = max(newest, os.stat(os.path.join(here, name)).st_mtime)
            except OSError:
                continue
    return newest


def _stamp() -> float:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    newest = 0.0
    for part in ("app", "core", "nas"):
        folder = os.path.join(root, part)
        if os.path.isdir(folder):
            newest = max(newest, _newest(folder))
    return newest


WHEN_BUILT = _stamp()


def _short(when: float) -> str:
    if not when:
        return "unknown"
    return time.strftime("%d %b %H:%M", time.localtime(when))


def describe() -> dict:
    """Everything the header needs to prove it is looking at a live process."""
    up = max(0, int(time.time() - WHEN_STARTED))
    return {
        "release": RELEASE,
        "code": _short(WHEN_BUILT),
        "started": _short(WHEN_STARTED),
        "uptime": up,
        "now": time.strftime("%H:%M:%S"),
    }
