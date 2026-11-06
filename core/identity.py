"""What this server IS, in the two sentences a client needs before anything else.

One app, several machines: the NAS runs a copy, the PC runs a copy, and one
phone talks to both. The moment there is more than one, three questions have to
have answers a client can rely on:

**Which one is this?** Not the address - a phone moves between wifi and
Tailscale and the address changes under it. A server gets an `id` on first run,
kept in its settings, and that is what a client stores a connection against. Two
addresses with the same id are the same server; the same address with a
different id is a rebuilt one, and the client can say so rather than silently
mixing two libraries' worth of state.

**What is it called?** "NAS" and "the PC", because that is what they are called
out loud. Set on Setup; the machine's own name until then. A list of connections
showing two IP addresses is a list nobody can read.

**What can it do?** A client written against this release will outlive it. So
the answer carries an API number that only moves when something already there
changes meaning, and a list of what this build can do - a client that wants
Search asks whether Search is here rather than parsing a release number.

None of this is a login. Who may connect is still the password in Setup; this
only says what is on the other end of the wire.
"""

from __future__ import annotations

import os
import platform
import socket
import uuid

from . import settings as S

# The contract number. It goes up ONLY when something a client already relies on
# changes meaning - a field that disappears, a path that means something else.
# Adding a field, an endpoint or a capability does not move it, because nothing
# written against the old number breaks.
API = 1

NAME = "server_name"
ID = "server_id"

# What a client may ask for. Named rather than inferred from the release, so a
# client keeps working when the numbering changes and can degrade honestly when
# it is talking to an older build.
CAN = [
    "browse",        # /api/files, /api/folder-status
    "thumbs",        # /api/thumb, /api/file
    "view",          # /api/photo, GET + POST
    "rate",          # stars, colour, tags
    "delete",        # with undo
    "files",         # copy, move, rename, mkdir, delete
    "run",           # /api/plan, /api/apply, /api/progress
    "flows",         # /api/flows
    "search",        # /api/plan on the search task
    "charts",        # the dashboard payload
    "values",        # /api/values - what the library actually holds
    "boards",        # arrangements of the dashboard
    "bands",         # the brackets a chart groups by
    "cameras",       # display names for camera codes
]


def host() -> str:
    """The machine's own name, as a fallback label. Never fatal."""
    try:
        return socket.gethostname() or "photo-manager"
    except OSError:
        return "photo-manager"


def kind() -> str:
    """windows / linux / darwin - so a client can phrase a path the local way."""
    got = (platform.system() or "").lower()
    return got if got in ("windows", "linux", "darwin") else "other"


def my_id() -> str:
    """This install's own id, made once and kept.

    Made from uuid4, not from the hostname or the MAC: two Synology boxes out of
    the same batch, or a container rebuilt from the same image, would collide -
    and two servers a client believes are one is the worst outcome here.
    """
    saved = str(S.load()[ID] or "").strip()
    if len(saved) == 32 and all(c in "0123456789abcdef" for c in saved):
        return saved
    made = uuid.uuid4().hex
    try:
        S.save({ID: made})
    except Exception:                                      # noqa: BLE001
        # Settings that cannot be written is a real state (the /config volume is
        # missing). The server still answers; the id is simply not the same one
        # next time, and a client will treat it as a different server - which is
        # honest, because a server that cannot remember anything IS a new one.
        pass
    return made


def name() -> str:
    """What to call this server. Yours, then the machine's own name."""
    return str(S.load()[NAME] or "").strip() or host()


def trees() -> list:
    """The folders this server was set up with, and whether they are really there.

    A client showing "the library" has to be able to say when the library is not
    mounted - on the NAS that is a container whose volume did not come up, and
    from the outside it looks exactly like an empty folder.
    """
    saved = S.load()
    out = []
    for key, label in (("library", "The library"), ("raw", "RAWs"),
                       ("previews", "Previews"), ("video", "Video")):
        path = str(saved[key] or "").strip()
        if not path:
            continue
        out.append({"key": key, "name": label, "path": path,
                    "there": os.path.isdir(path)})
    return out


def describe(port: int = 0, locked: bool = False) -> dict:
    """Everything a client needs before its first real call."""
    from app import version

    return {
        "app": "photo-manager",
        "api": API,
        "release": version.RELEASE,
        "id": my_id(),
        "name": name(),
        "host": host(),
        "platform": kind(),
        "port": int(port or 0),
        "locked": bool(locked),
        "trees": trees(),
        "can": list(CAN),
        "started": version.WHEN_STARTED,
    }


def brief(port: int = 0, locked: bool = False) -> dict:
    """The short form, for the answer to a discovery shout.

    Small on purpose: it goes in one UDP datagram, and a datagram that has to be
    fragmented is one that quietly does not arrive on some networks.
    """
    return {"app": "photo-manager", "api": API, "id": my_id(), "name": name(),
            "platform": kind(), "port": int(port or 0), "locked": bool(locked)}
