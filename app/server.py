"""The web page. Same code on the PC and on the NAS.

It knows nothing about photos. It lists whatever tasks are registered, draws each
one's form from the options that task declares, runs plan(), and shows what came
back. Add a feature and it appears here with a working form and no changes to
this file - which is the whole reason the registry exists.

Standard library only, so it starts on a bare Python install.

ALLOWED_ROOTS is a hard boundary when it is set: a path outside it is refused,
and symlinks cannot sneak past because everything is resolved first. Unset on
the NAS means no restriction - the container's mounts are the real fence there.
Unset on a PC means the folders chosen in Setup, because a PC has the whole disk
behind it and the page says so out loud (`fence()`).
"""

from __future__ import annotations

import base64
import hmac
import ipaddress
import json
import os
import socket
import shutil
import sys
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from app import registry as R
from app.icons import ICON_32, ICON_192, ICON_512
from app.page import PAGE
from app import pagetext
from app import version
import app.tasks  # noqa: F401  - importing registers every task
from core import flows as _FLOWS

PORT = int(os.environ.get("PORT", "8080"))


def public_port() -> int:
    """The port a client on the network should actually use.

    Not always the one being listened on. In a container the mapping is
    `8842:8080` and 8080 is the only number this process can see - so a
    discovery answer that said 8080 would send every phone to a port that is
    not open, and the failure would look like the phone's fault.
    """
    said = os.environ.get("PM_PUBLIC_PORT", "").strip()
    if not said:
        try:
            from core import settings as _s
            said = str(_s.load()["public_port"] or "").strip()
        except Exception:                                  # noqa: BLE001
            said = ""
    try:
        n = int(said)
        return n if 1 <= n <= 65535 else PORT
    except (TypeError, ValueError):
        return PORT

ALLOWED_ROOTS = [os.path.realpath(p) for p in
                 os.environ.get("ALLOWED_ROOTS", "").split(os.pathsep) if p.strip()]


def _networks(text: str) -> list:
    """Addresses or ranges, comma-separated: `172.17.0.1, 10.0.0.0/8`."""
    out = []
    for piece in str(text or "").replace(";", ",").split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            out.append(ipaddress.ip_network(piece, strict=False))
        except ValueError:
            sys.stderr.write(f"PM_TRUSTED_PROXY: {piece!r} is not an address; "
                             f"left out\n")
    return out


# The reverse proxies whose word is taken about who is really knocking.
#
# Behind DSM's reverse proxy every request arrives from the proxy's own address,
# so a lockout keyed on that address is one lockout for the whole household: one
# guessing machine and nobody gets in. X-Forwarded-For says who the browser
# was, but anybody can send that header, so it is believed only from an address
# named here. Nothing is trusted by default.
TRUSTED_PROXIES = _networks(os.environ.get("PM_TRUSTED_PROXY", ""))

# Names this app answers to besides addresses, `localhost` and the names a home
# network gives itself (one word, or ending .local, .lan and so on). A page on
# some website can point a name it owns at this machine's address and talk to
# an app with no password as if it were its own; refusing names nobody here
# chose is what stops that. A reverse proxy's public name goes here.
EXTRA_HOSTS = {h.strip().lower().rstrip(".") for h in
               os.environ.get("PM_HOSTS", "").replace(";", ",").split(",")
               if h.strip()}
HOME_SUFFIXES = (".local", ".lan", ".home", ".home.arpa", ".internal",
                 ".localdomain", ".intranet", ".private", ".localhost",
                 # Tailscale's names: only Tailscale can point one anywhere,
                 # and nas/README.md suggests `tailscale serve` for HTTPS.
                 ".ts.net")


def trusted_proxy(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(str(address).strip().strip("[]"))
    except ValueError:
        return False
    return any(ip in net for net in TRUSTED_PROXIES)


def known_name(name: str) -> bool:
    """Is this a name the app may be reached by? See EXTRA_HOSTS."""
    name = str(name or "").strip().lower().rstrip(".")
    if not name:
        return True                     # HTTP/1.0 sends none; not a browser
    try:
        ipaddress.ip_address(name.strip("[]"))
        return True
    except ValueError:
        pass
    if name == "localhost" or "." not in name or name in EXTRA_HOSTS:
        return True
    if name.endswith(HOME_SUFFIXES):
        return True
    try:
        return name == socket.gethostname().lower()
    except OSError:
        return False


def _host_port(text: str):
    """("nas", 8842) from "nas:8842"; the port is None when not given."""
    try:
        got = urlparse("//" + str(text or "").strip())
        return (got.hostname or "").lower(), got.port
    except ValueError:
        return "", None


def same_place(origin: str, hosts: list) -> bool:
    """Is a browser's Origin one of the addresses this request was sent to?"""
    try:
        o = urlparse(str(origin or "").strip())
        port = o.port or (443 if o.scheme == "https" else 80)
    except ValueError:
        return False
    if o.scheme not in ("http", "https") or not o.hostname:
        return False
    for one in hosts:
        name, given = _host_port(one)
        if name != o.hostname.lower():
            continue
        # A Host without a port means the scheme's own: 80, or 443 behind TLS.
        if given is None and port in (80, 443):
            return True
        if given == port:
            return True
    return False


# The Setup boxes that, on a PC, draw the fence.
FENCE_KEYS = ("library", "raw", "previews", "video", "develop", "inbox",
              "also_allowed")
# The fence of a PC where nothing is chosen yet. Not a path anything can be
# under, and never shown: an empty list would mean "anywhere", the opposite.
NOWHERE = "<nothing chosen in Setup yet>"
_FENCE_SEEN: tuple = ("", [])


def fence() -> list:
    """The folders paths are checked against right now. Empty means anywhere.

    ALLOWED_ROOTS wins wherever it is set. On the NAS it is set in the compose
    file, and what is not mounted does not exist in the container anyway. A PC
    has no mounts: left alone, everything on the disk - a browser profile, the
    documents folder, this app's own ticket secret - was a download away for
    anything on the Wi-Fi. So a PC program with no ALLOWED_ROOTS is fenced to
    the folders chosen in Setup and the ones added under Also allowed. Before
    any are chosen that is nothing at all, which is the honest answer: the
    folder picker still lists the disk so the first one can be chosen.
    """
    global _FENCE_SEEN
    if ALLOWED_ROOTS:
        return ALLOWED_ROOTS
    from core import desktop
    if not desktop.as_program():
        return []
    from core import settings as _s
    saved = _s.load()
    stamp = saved.path + "|" + _s.stamp(saved.path)
    if _FENCE_SEEN[0] == stamp:
        return _FENCE_SEEN[1]
    roots = []
    for key in FENCE_KEYS:
        value = saved[key]
        # Only Also allowed is a list; a library called "Photos, 2020" is one
        # folder, and splitting it at the comma would fence it out.
        chosen = (R.Folders.chosen(value) if key == "also_allowed"
                  else [str(value or "").strip()])
        for one in chosen:
            if not one:
                continue
            try:
                real = os.path.realpath(one)
            except (OSError, ValueError):
                continue
            if real not in roots:
                roots.append(real)
    roots = roots or [NOWHERE]
    _FENCE_SEEN = (stamp, roots)
    return roots


def shown_fence() -> list:
    """The fence as folders a person can read: NOWHERE left out."""
    return [r for r in fence() if r != NOWHERE]


def fence_said() -> str:
    """The fence in words, for a refusal and for Setup."""
    roots = fence()
    if not roots:
        return "anywhere on this machine"
    if ALLOWED_ROOTS:
        return ", ".join(roots)
    shown = shown_fence()
    if not shown:
        return "nothing yet: on a PC that is the folders chosen in Setup"
    return ", ".join(shown) + " - the folders chosen in Setup, and Also allowed"


# The container's own operating system, which appears at the top of the tree and
# is never anybody's photos. Named rather than guessed, and only ever applied at
# the ROOT of the machine: a folder called "media" or "opt" inside a photo tree is
# a photo folder, and hiding it because of its name would be a lie.
SYSTEM_FOLDERS = {
    "app", "bin", "boot", "dev", "etc", "lib", "lib32", "lib64", "libx32",
    "lost+found", "media", "mnt", "opt", "proc", "root", "run", "sbin", "srv",
    "sys", "tmp", "usr", "var",
}


def is_system(path: str, inside: str) -> bool:
    """Is this one of the container's own folders, sitting at the top of it?"""
    if inside.rstrip(os.sep) not in ("", os.sep):
        return False
    return os.path.basename(path.rstrip(os.sep)).lower() in SYSTEM_FOLDERS


# ---------------------------------------------------------------- a password
#
# Off until you set one, because on a home network with one person on it a login
# screen is friction for no gain. But the honest position is worth stating: with
# nothing set, anyone who can reach the port can look at every photo in the
# library AND move, cull and re-mirror them. The destructive half was always the
# bigger exposure.
#
# Two ways in, and they are for different people. A browser signs in on a page
# and is given a signed ticket in a cookie - see `core.access`. A script, or
# curl, or anything without a place to keep a cookie, sends HTTP Basic, which is
# checked against the same password. Neither is a user account: there is one
# password for the app and nothing to administer.
PASSWORD = os.environ.get("PM_PASSWORD", "")
USERNAME = os.environ.get("PM_USERNAME", "photos")
COOKIE = "pm_ticket"


def _basic(header: str):
    """(name, password) from an HTTP Basic header, or None if it is not one.

    UTF-8, as RFC 7617 says and as curl sends what you type; a header that is
    not UTF-8 is read as Latin-1 rather than refused, so it is simply wrong.
    """
    try:
        kind, _, blob = (header or "").strip().partition(" ")
        if kind.lower() != "basic":
            return None
        raw = base64.b64decode(blob.strip(), validate=False)
    except Exception:                                  # noqa: BLE001
        return None
    try:
        said = raw.decode("utf-8")
    except UnicodeDecodeError:
        said = raw.decode("latin-1")
    name, _, word = said.partition(":")
    return name, word


def _password_ok(header: str) -> bool:
    """HTTP Basic, for everything that is not a browser."""
    from core import access
    if not access.is_on():
        return True
    got = _basic(header)
    if got is None:
        return False
    name, word = got
    # The name is not a user list - there is one password - but a wrong name
    # with the right word should still be a no, and comparing both in constant
    # time costs nothing. As bytes, because compare_digest refuses a str with
    # anything but ASCII in it, and an Arabic name was a 500 on every request.
    right_name = hmac.compare_digest(name.encode("utf-8", "surrogateescape"),
                                     USERNAME.encode("utf-8", "surrogateescape"))
    return access.correct(word) and right_name


def _cookies(header: str) -> dict:
    out = {}
    for piece in str(header or "").split(";"):
        name, _, value = piece.strip().partition("=")
        if name:
            out[name] = value
    return out


def path_allowed(p: str, roots: list | None = None) -> bool:
    roots = fence() if roots is None else roots
    if not roots:
        return True
    try:
        rp = os.path.normcase(os.path.realpath(p))
    except (OSError, ValueError):
        return False
    # normcase: on a PC `N:\photos` and the `N:\Photos` chosen in Setup are
    # one folder. It changes nothing on Linux, where they are two.
    for r in roots:
        r = os.path.normcase(r).rstrip(os.sep)
        if rp == r or rp.startswith(r + os.sep):
            return True
    return False


def paths_in(option, value) -> list:
    """The paths in one box, split exactly the way the task will split them.

    `check_paths` used to split on newlines while `Folders.chosen` also split
    on commas, so "/allowed/x,/elsewhere" was checked as one folder under
    the allowed root and then walked as two. One splitter, so the check and the
    task can never read a box differently.
    """
    if option.kind == "folders":
        return R.Folders.chosen(value)
    if option.kind == "folder" and getattr(option, "many", False):
        return option.chosen(value)
    text = str(value or "").strip()
    return [text] if text else []


def chooses_fence(task: R.Task, option) -> bool:
    """Is this the box that decides where the PC fence is?

    Setup's trees and the sample library's folder. Checked against the fence
    they draw, they could never be moved anywhere new - the library could only
    ever be where it already was.
    """
    if task.settings and option.setting in FENCE_KEYS:
        return True
    return task.name == "demo" and option.name == "folder"


def check_paths(task: R.Task, opts: dict, choosing: bool = False) -> str | None:
    """Every folder and file a task was given, against the fence. Lists included.

    The lists used to be skipped, which is the wrong way round for a check like
    this: a box holding twenty paths is more of a way out of the allowed folders
    than a box holding one, not less. File boxes were skipped as well, so a
    Reference photo or a Backup to restore could name anything on the disk.

    `choosing`: the person asking may move the PC fence itself (they are at the
    PC, or signed in), so the boxes that draw it answer to ALLOWED_ROOTS alone.
    """
    for o in task.options:
        if o.kind not in ("folder", "folders", "file"):
            continue
        value = opts.get(o.name)
        if not value:
            continue
        roots = ALLOWED_ROOTS if (choosing and chooses_fence(task, o)) else None
        for one in paths_in(o, value):
            if not path_allowed(one, roots):
                said = ", ".join(roots) if roots is not None else fence_said()
                return (f"{one} is outside the folders this is allowed to touch "
                        f"({said}).")
    return None


def attachment(name: str) -> str:
    """A Content-Disposition for a download, whatever the file is called.

    Headers go out as Latin-1, so a photograph named in Arabic, Chinese or with
    an emoji raised half-way through the answer and the Download button did
    nothing. The plain `filename` is an ASCII stand-in for old clients; every
    current browser reads `filename*`, the real name in UTF-8. Control
    characters go too: a newline in a header is a second header.
    """
    import unicodedata
    from urllib.parse import quote
    name = "".join(c for c in str(name or "") if c >= " " and c != "\x7f") or "download"
    def ascii_of(text):
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore")
        return text.decode("ascii").replace('"', "").replace("\\", "").strip()
    stem, ext = os.path.splitext(name)
    plain = (ascii_of(stem) or "download") + ascii_of(ext)
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(name, safe='')}"


# Options that mean something only where the PC fence is in force: on the NAS
# the compose file's ALLOWED_ROOTS is the fence, and a box that did nothing
# there would be a box somebody fills in and trusts. Still registered, so the
# command line is the same everywhere.
PC_ONLY_OPTIONS = {("setup", "also_allowed")}


def _pc_options(described: dict, on_pc: bool) -> dict:
    if on_pc and not ALLOWED_ROOTS:
        return described
    name = described.get("name")
    if not any(t == name for t, _o in PC_ONLY_OPTIONS):
        return described
    keep = lambda o: (name, o.get("name")) not in PC_ONLY_OPTIONS  # noqa: E731
    out = dict(described)
    out["options"] = [o for o in described.get("options") or [] if keep(o)]
    out["groups"] = [dict(g, options=[o for o in g.get("options") or [] if keep(o)])
                     for g in described.get("groups") or []]
    return out


# ------------------------------------------------------------------ is it alive

def health() -> dict:
    """Enough for the page to prove three things at once.

    That it is talking to a live process (uptime moves), that the process loaded
    the code you just copied (the CODE stamp moves), and that the folders it was
    told to work in are actually there.

    That last one is the whole reason this exists. A mount that did not happen is
    invisible from inside the container - a path that was never mounted and a
    path that was misspelt look identical - so the app cannot work out WHY, but
    it can say plainly THAT the folder it was pointed at is not there, instead of
    letting you discover it one Browse click at a time.
    """
    from . import version

    folders = []
    for root in ALLOWED_ROOTS:
        there = os.path.isdir(root)
        folders.append({
            "path": root,
            "there": there,
            "writable": bool(there and os.access(root, os.W_OK)),
        })
    missing = [f["path"] for f in folders if not f["there"]]
    unwritable = [f["path"] for f in folders if f["there"] and not f["writable"]]

    from core import desktop
    on_pc = desktop.as_program()
    trouble = ""
    if missing and on_pc:
        # The container advice below is about a compose file a PC does not
        # have; what is worth checking there is the drive itself.
        trouble = (
            f"{'This folder is' if len(missing) == 1 else 'These folders are'} "
            f"not there: {', '.join(missing)}. If it is on a network drive or "
            f"a disk that comes and goes, check it is connected, or pick the "
            f"folder again in Setup.")
    elif missing:
        trouble = (
            f"{'This folder is' if len(missing) == 1 else 'These folders are'} "
            f"not visible from inside this container: {', '.join(missing)}. "
            f"In a container that means the volume is missing from the compose "
            f"file, or is spelt differently there. If you just corrected the "
            f"compose file, the change has not been applied: Stop the project "
            f"and Build it, which recreates the container - a Restart does not "
            f"always pick up a changed volume.")
    elif unwritable:
        trouble = (f"Readable but not writable: {', '.join(unwritable)}. "
                   f"Anything that moves a file will refuse.")

    from core import access
    out = version.describe()
    out["folders"] = folders
    out["trouble"] = trouble
    out["locked"] = access.is_on()
    # Which kind of copy this is, so the page can offer a Quit on a PC and not
    # on the NAS, where there is nothing to bring it back.
    out["desktop"] = on_pc
    # The permissions job is DSM's and Synology Drive's business. On a PC
    # neither exists, so a banner counting folders "waiting" for it is a nag
    # about a job that will never come; Permissions stays a command to run by
    # hand there, not something the page keeps asking for.
    out["permissions"] = ({"waiting": 0, "stale": False} if on_pc
                          else _permissions_waiting())
    # Which settings the page's forms were drawn from. The page asks for this
    # every few seconds anyway, so a library changed anywhere - Setup, the
    # sample library, the command line, another browser - reaches every open
    # form without a reload.
    from core import settings as _s
    out["settings"] = _s.stamp()
    return out


def _permissions_waiting() -> dict:
    """Folders this app could not finish, and whether anything is fixing them.

    On the page rather than only in Setup because of what the wait actually
    means: until DSM's own tool has been over them, Synology Drive cannot see
    those folders, and neither Drive nor this app says a word about it. It only
    appears when something is genuinely stuck - folders waiting and nothing
    having come for them in hours - so it stays worth reading.
    """
    import time
    try:
        from core import acl
        waiting = acl.waiting()
        ran = acl.last_run()
        if not waiting:
            return {"waiting": 0, "stale": False}
        old_enough = not ran or (time.time() - ran["when"]) > 6 * 3600
        return {"waiting": len(waiting), "stale": bool(old_enough),
                "ever": bool(ran)}
    except Exception:                                  # noqa: BLE001
        return {"waiting": 0, "stale": False}


# ------------------------------------------------------------- browsing folders

def drive_root(path: str, flavour=os.path) -> str:
    """`C:` on its own is not the top of drive C - it is wherever C: was last
    left, which for a program started from a shortcut is some folder nobody
    chose. Anyone typing or clicking a bare drive letter means its root."""
    if flavour.sep == "\\" and len(path) == 2 and path[1] == ":" and path[0].isalpha():
        return path + "\\"
    return path


def parent_of(path: str, flavour=os.path) -> str:
    """One level up, or "" for the shortcut list when there is nowhere higher.

    Not `dirname(path.rstrip(sep))`: on Windows that turns `C:\\` into `C:`, and
    "up one level" from the top of a drive then lands in a random folder on it
    instead of back at the list of drives. The same goes for the top of a
    network share. normpath keeps the root's own separator, so a root is simply
    the path that is its own parent.
    """
    here = flavour.normpath(path)
    up = flavour.dirname(here)
    return "" if not up or up == here else up


def browse(path: str, want_files: str = "") -> dict:
    """The folders inside this one, so the page can offer a Browse button.

    Typing `N:\\Photos\\2024\\Barcelona 2024` correctly, into seven forms, is a
    thing people get wrong - and a mistyped root does not fail loudly, it mirrors
    against the wrong tree.

    Only DIRECTORIES are listed. This is for choosing a folder; a list of eighty
    thousand photos would be no help and a lot of bytes.

    **Looking is not touching.** This used to stop dead at ALLOWED_ROOTS, and the
    result was a browser that answered "no folders" for a machine plainly full of
    them - with no way to tell a wrong path from a wrong fence. So it now lists
    anything the process can read, and marks each entry with whether a task would
    accept it. The boundary has not moved: `check_paths` still refuses a folder
    outside the roots, and in a container the mounts are the real fence anyway -
    what is not mounted does not exist in here to be listed.
    """
    path = (path or "").strip()

    if not path:
        # Nothing chosen yet. The allowed roots go first because they are almost
        # always what is wanted, but the top of the machine is offered underneath
        # so nothing is unreachable.
        tops = []
        if os.name == "nt":
            tops = [f"{c}:\\" for c in "CDEFGHIJKLMNOPQRSTUVWXYZ"
                    if os.path.isdir(f"{c}:\\")]
        else:
            home = os.path.expanduser("~")
            tops = [p for p in (home, os.sep) if os.path.isdir(p)]
        folders, seen = [], set()
        for r in shown_fence() + tops:
            if r in seen or not os.path.isdir(r):
                continue
            seen.add(r)
            folders.append({"name": r, "path": r, "allowed": path_allowed(r)})
        return {"path": "", "parent": None, "allowed": True, "folders": folders}

    path = drive_root(path)
    if not os.path.isdir(path):
        return {"path": path, "parent": None, "folders": [], "allowed": False,
                "error": f"{path} is not a folder on this machine. In a container "
                         f"that usually means it is not mounted, however plainly it "
                         f"exists outside."}

    # "" means the shortcut list, not "no parent". At the top of the machine
    # there is nowhere further up, but there is still somewhere to go BACK to -
    # the allowed roots - and a browser you can walk out of but not back into is
    # a browser you get lost in.
    parent = parent_of(path)

    folders, files = [], []
    # Folder NAMES anywhere, so the first library can be found; file names only
    # inside the fence. A list of every file in /etc is not a folder picker.
    listing_files = path_allowed(path)
    try:
        for name in sorted(os.listdir(path), key=str.lower):
            full = os.path.join(path, name)
            if name.startswith(".") or name.startswith("@eaDir"):
                continue
            try:
                if os.path.isdir(full):
                    folders.append({"name": name, "path": full,
                                    "allowed": path_allowed(full),
                                    "system": is_system(full, path)})
                elif want_files and listing_files and os.path.isfile(full):
                    # Only the ones the task can actually read. A folder of
                    # eighty thousand photographs listed under a box that wants
                    # a .zip is a list nobody can use.
                    if want_files == "*" or name.lower().endswith(
                            tuple(x.strip().lower() for x in want_files.split(",")
                                  if x.strip())):
                        files.append({"name": name, "path": full,
                                      "allowed": path_allowed(full),
                                      "file": True})
            except OSError:
                continue
    except OSError as exc:
        return {"path": path, "parent": parent, "folders": [], "allowed": False,
                "error": f"could not read that folder: {exc.strerror or exc}"}
    out = {"path": path, "parent": parent, "allowed": path_allowed(path),
           "folders": folders[:600], "files": files[:600]}
    if fence() and not out["allowed"]:
        out["outside"] = ("Tools will refuse this folder: it is outside "
                          + fence_said() + ".")
    return out


# ----------------------------------------------------------------------- jobs

# How many rows of a plan travel to the page. It was two thousand, which was
# the right number when the page drew every row it was given: a Search that
# matched six thousand photographs listed a third of them and said so in a
# note nobody read. The page now draws a few hundred at a time and offers the
# rest, so the limit is what a browser can hold, not what it can draw at once.
ROWS_SENT = 20_000


def plan_payload(task: R.Task, plan: R.Plan, job_id: str) -> dict:
    """A plan as the page wants it. One place, so the poll and the post agree."""
    return {
        "id": job_id,
        "task": plan.task, "blocked": plan.blocked,
        "writes": task.writes if plan.writes is None else bool(plan.writes),
        "title": task.title,
        "stats": [list(s) for s in plan.stats],
        "notes": plan.notes,
        "columns": list(plan.columns),
        "tree": plan.tree[:5000],
        "picks": plan.picks,
        "groups": list(plan.groups),
        # The plan may name an editor for THIS answer (a flow being edited);
        # otherwise the tab's own editor stands, which is how a tab that is an
        # editor rather than a report gets one without saying so every time.
        "editor": plan.editor or task.editor,
        "data": plan.data,
        # What this would change, in four facts, so the page can say it in a
        # sentence above the button instead of leaving it to be inferred from
        # four hundred rows. Computed here rather than in the page because the
        # rows below are TRIMMED and the count must not be.
        "impact": R.impact_of(task, plan),
        "rows": [{"name": r.name, "detail": r.detail, "source": r.source,
                  "target": r.target, "approximate": r.approximate,
                  "cells": [str(c) for c in r.cells], "group": r.group,
                  "act": r.act}
                 for r in plan.rows[:ROWS_SENT]],
        "skipped": [list(s) for s in plan.skipped[:2000]],
        "errors": plan.errors[:200],
        # Where each row would put a photograph, for the map drawn above the
        # table. Any plan whose rows carry a position gets one - Geotag, Pin by
        # hand - without either of them having to know a map exists.
        "points": _points(plan.rows),
        "charts": plan.charts,
    }


def _points(rows) -> list:
    out = []
    for r in rows[:2000]:
        data = getattr(r, "data", None) or {}
        lat, lon = data.get("lat"), data.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            out.append([round(float(lat), 6), round(float(lon), 6), r.name])
    return out


# ------------------------------------------------------------ file manager jobs
#
# Copying four hundred RAWs is not a thing to do inside one request: the browser
# would sit on it for minutes and a phone would give up. So the same shape as
# every other run here - start it, watch it, and it says what it did - but
# without a plan in front of it, because the person already said which files,
# in a file manager, by picking them.
FILE_JOBS: dict = {}
FILE_LOCK = threading.Lock()


def record_moves(task: str, opts: dict, moves, action: str = "", size: int = 0,
                 details=None, stats=None, failed: int = 0) -> None:
    """One file-manager or viewer run into History, WITH its moves.

    Without them History showed the run and Put it back said it "did not move
    any files": the only undo was the toast, for as long as it stayed on the
    screen. Never raises - the files have already moved either way.
    """
    try:
        from core import runlog
        moves = [list(m) for m in (moves or [])]
        res = R.Result(done=len(moves), failed=failed,
                       details=list(details if details is not None else
                                    [f"{m[0]}  ->  {m[1]}" for m in moves[:20]]))
        res.moves = moves
        if stats:
            res.stats = stats
        if size:
            res.reclaimed, res.reclaim_kind = size, "aside"
        runlog.record(task, opts, res, action=action)
    except Exception:                                  # noqa: BLE001
        pass


class FileJob:
    def __init__(self, what: str, jobs: list, move: bool):
        self.id = uuid.uuid4().hex[:12]
        self.what = what
        self.jobs = jobs
        self.move = move
        self.done = 0
        self.total = len(jobs)
        self.now = ""
        self.finished = False
        self.cancel = False
        self.started = time.time()
        self.result: dict = {}
        self.error = ""

    def progress(self, i, n, name, status="OK"):
        self.done, self.total, self.now = i, n, name

    def run(self):
        from core import filesops
        try:
            self.result = filesops.run(self.jobs, self.move, progress=self.progress,
                                       cancelled=lambda: self.cancel)
        except Exception:                              # noqa: BLE001
            self.error = traceback.format_exc(limit=3)
        finally:
            self.finished = True
            try:
                from core import runlog
                res = R.Result(done=int(self.result.get("done", 0)),
                               failed=int(self.result.get("failed", 0)),
                               details=self.result.get("errors", [])[:20])
                res.moves = [list(m) for m in self.result.get("moves", [])]
                res.stats = [("Files", f"{self.result.get('done', 0):,}"),
                             ("Renamed to avoid a clash",
                              f"{self.result.get('renamed', 0):,}")]
                runlog.record("files", {"folder": self.what}, res,
                              time.time() - self.started,
                              action=("move" if self.move else "copy"))
            except Exception:                          # noqa: BLE001
                pass

    def state(self) -> dict:
        return {"id": self.id, "done": self.done, "total": self.total,
                "now": self.now, "finished": self.finished, "error": self.error,
                "result": self.result, "what": self.what, "move": self.move,
                "seconds": int(time.time() - self.started)}


def start_file_job(what: str, jobs: list, move: bool) -> FileJob:
    job = FileJob(what, jobs, move)
    with FILE_LOCK:
        for old in [k for k, j in FILE_JOBS.items()
                    if j.finished and time.time() - j.started > 3600]:
            FILE_JOBS.pop(old, None)
        FILE_JOBS[job.id] = job
    threading.Thread(target=job.run, daemon=True).start()
    return job


def _save_facts() -> None:
    """Write what the run learned about its photographs, once, now it is over.

    Each task asks for a save as it finishes, and those are gathered into one
    write a moment later (`core/facts.py`); a run ending is the moment not to
    wait for, so the next one starts from the notes this one made.
    """
    try:
        from core import facts
        facts.flush()
    except Exception:                                  # noqa: BLE001
        pass


# ------------------------------------------------------------- one writer a tree
#
# Two runs writing into the same tree at once is how a photograph gets moved by
# one while the other is halfway through rewriting it, or how a duplicate pass
# and a sort into folders each act on a list the other has already made untrue.
# Each plan was right when it was shown; together they are not. So a run that
# writes holds the trees it touches until it ends, and a second writing run on
# an overlapping tree is refused (a button) or waits its turn (automation).
# Runs that only read never take part: looking at a tree while it is written is
# what the index loop and every preview already do, and is safe.
#
# A run that runs other runs - the Automation tab's Apply runs each step of a
# flow as a job of its own, on the same thread - is not in its own way: a clash
# with a run held by the asking thread is not a clash.
TREES_LOCK = threading.Condition()
WRITING: dict = {}            # job id -> [job, [folders it touches], thread id]


def trees_of(task: R.Task, plan: R.Plan, saved=None) -> list:
    """Every folder a writing run will touch: where it works and where it writes.

    From the four facts the confirmation shows (`impact_of`: from, into) and the
    Setup trees the task declares it reads, copies into or moves into. Those
    overlap on purpose - the declaration covers a destination that is a Setup
    value rather than a box on the form.
    """
    out = []
    try:
        facts = R.impact_of(task, plan)
    except Exception:                                  # noqa: BLE001
        facts = {}
    if facts.get("from"):
        out.append(str(facts["from"]))
    for one in facts.get("into") or []:
        if isinstance(one, dict) and one.get("path"):
            out.append(str(one["path"]))
    keys = tuple(task.reads) + tuple(task.copies_to) + tuple(task.moves_to)
    if keys:
        try:
            from core import settings as _s
            saved = _s.load() if saved is None else saved
            for key in keys:
                value = str(saved[key] or "").strip()
                if value:
                    out.append(value)
        except Exception:                              # noqa: BLE001
            pass
    seen, clean = set(), []
    for one in out:
        key = os.path.normcase(os.path.abspath(one))
        if key not in seen:
            seen.add(key)
            clean.append(one)
    return clean


def _overlap(a: str, b: str) -> bool:
    from core.paths import under
    return under(a, b) or under(b, a)


def _clash(trees: list):
    """(the running job, the folder) that is in the way, or None. Holds lock."""
    here = threading.get_ident()
    for other, theirs, owner in WRITING.values():
        if owner == here:
            continue
        for mine in trees:
            for held in theirs:
                if _overlap(mine, held):
                    return other, held
    return None


def _clash_said(other, where: str) -> str:
    who = "The automation's " if other.by == "automation" else ""
    return (f"{who}{other.task.title} is still writing to {where}. Wait for it "
            f"to finish, then apply this again.")


def claim_trees(job, wait: bool = False, cancelled=None) -> str:
    """Hold the trees this job writes to. "" when held; otherwise why not.

    `wait` is for the automation, which queues behind a run rather than being
    refused - nobody is there to press Apply again. It gives up only if the run
    is cancelled while it waits.
    """
    if not (job.task.writes if job.plan.writes is None else bool(job.plan.writes)):
        return ""
    trees = trees_of(job.task, job.plan)
    if not trees:
        return ""
    # Only the thread that will do the work is recorded as holding them. The
    # request that claims for a button run is not that thread, and its id can
    # be handed to the very next request once it ends - which would then not
    # see the clash at all.
    owner = threading.get_ident() if wait else None
    with TREES_LOCK:
        while True:
            if job.id in WRITING:
                # Claimed by the request that started it; now held by the
                # thread actually doing the work.
                if wait:
                    WRITING[job.id][2] = owner
                return ""
            got = _clash(trees)
            if got is None:
                WRITING[job.id] = [job, trees, owner]
                return ""
            said = _clash_said(*got)
            if not wait:
                return said
            if cancelled is not None and cancelled():
                return said
            job.now = f"waiting for {got[0].task.title} to finish"
            TREES_LOCK.wait(timeout=1.0)


def release_trees(job) -> None:
    with TREES_LOCK:
        if WRITING.pop(job.id, None) is not None:
            TREES_LOCK.notify_all()


class _Failed:
    """Stands in for a Result when apply threw, so the run is still logged."""

    def __init__(self, error: str):
        self.done = 0
        self.failed = 1
        self.cancelled = False
        self.stats = []
        self.details = [line for line in (error or "").splitlines() if line][-6:]
        self.faults = {}

    def lines(self) -> list:
        return list(self.details)


class Job:
    """One plan, and the run of it if the person went ahead.

    A plan is kept on the server between the preview and the Apply on purpose.
    Sending the rows back for the browser to hand over again would mean applying
    something assembled from what a page said, and a page can be stale, edited, or
    from a different tab. Applying only ever re-uses the exact plan that was shown.
    """

    def __init__(self, task: R.Task, plan: R.Plan | None = None, raw: dict | None = None):
        self.id = uuid.uuid4().hex
        self.task, self.plan = task, plan
        self.raw = dict(raw or {})
        self.made = time.time()
        # PLANNING and APPLYING are two phases of one job, not two jobs. The
        # plan is kept here between them on purpose, so Apply re-uses the exact
        # plan that was shown - and a bar of everything running should show one
        # line that changes phase, or it looks like the work doubled.
        self.phase = "ready" if plan is not None else "planning"
        self.started = False
        self.finished = False
        self.ended = 0.0           # when looking or doing last finished
        self.cancel = False
        self.done = self.total = 0
        self.now = ""
        self.recent: list[str] = []
        self.stumbled: list[int] = []      # rows that failed, by position
        self.result: R.Result | None = None
        self.error = ""
        # Who started it, and what it cost. "" is you pressing a button;
        # "automation" is the background loop, which is the one you cannot see
        # happening and therefore the one worth labelling.
        self.by = ""
        self.before: dict = {}
        self.cost: dict = {}

    def look(self):
        """Work out the plan. Slow enough on a NAS to be worth watching."""
        try:
            self.plan = self.task.make_plan(self.raw, progress=self.progress)
        except R.Stopped:
            self.plan = R.Plan(task=self.task.name,
                               blocked="Stopped before it had finished looking, so "
                                       "there is no list. Nothing was written - "
                                       "looking never writes.")
        except Exception:                              # noqa: BLE001
            self.error = traceback.format_exc(limit=4)
        finally:
            self.phase = "ready"
            self.done = self.total = 0
            self.now = ""
            self.ended = time.time()
            _save_facts()

    def progress(self, i, n, name, status="OK"):
        if self.cancel and self.phase == "planning":
            raise R.Stopped()
        self.done, self.total, self.now = i, n, name
        if status != "OK":
            self.recent.append(f"{name}: {status}")
            del self.recent[:-40]
            # by position, so the table can mark the exact row rather than
            # guessing from a name that may appear more than once
            self.stumbled.append(i - 1)
            del self.stumbled[:-500]

    def run(self):
        self.started = True
        self.phase = "applying"
        self.total = len(self.plan.rows)
        began = time.time()
        # What this costs the NAS, measured around the work rather than
        # estimated from it. Taken here because it is the one place every run
        # goes through - a task cannot forget to be measured.
        from core import load as _load
        self.before = _load.snapshot()
        try:
            # A button run claimed its trees before it was started, and was
            # refused if it could not. Anything else that runs a job - the
            # automation - waits here for its turn instead.
            claim_trees(self, wait=True, cancelled=lambda: self.cancel)
            if self.cancel:
                self.result = R.Result(cancelled=True)
            else:
                self.now = ""
                self.result = self.task.apply(self.plan, progress=self.progress,
                                              cancelled=lambda: self.cancel)
        except Exception:                          # noqa: BLE001
            self.error = traceback.format_exc(limit=4)
        finally:
            release_trees(self)
            self.finished = True
            self.phase = "done"
            # Whatever just ran, it may have moved or rewritten photographs -
            # that is what this app is for. The index is marked stale rather
            # than rebuilt here: a rebuild inside the run would make every task
            # pay for it, and the next refresh reads only what actually moved.
            try:
                from core import catalogue as _cat
                _cat.touch()
            except Exception:                          # noqa: BLE001
                pass
            _save_facts()
            self.ended = time.time()
            # Recorded here rather than inside each task, so a task cannot forget
            # to - and recorded even when it threw, because a run that failed
            # halfway is exactly the one somebody will come looking for.
            try:
                from core import runlog
                self.cost = _load.since(self.before)
                got = self.result or _Failed(self.error)
                runlog.record(self.task.name,
                              self.task.loggable(self.plan.opts), got,
                              time.time() - began, by=self.by, cost=self.cost)
                if self.by == "automation" and (getattr(got, "done", 0)
                                                or getattr(got, "failed", 0)):
                    note_automation_result(time.time(), self.task.name,
                                           self.task.title,
                                           getattr(got, "done", 0),
                                           getattr(got, "failed", 0))
            except Exception:                      # noqa: BLE001
                pass
            # And what Synology has not been told about yet. Here for the same
            # reason as the log: one place, so no task can forget - and after a
            # run that FAILED as well, because half a move is exactly the state
            # an out-of-date index describes worst.
            try:
                from core import reindex
                if self.task.writes and self.plan.rows:
                    reindex.remember(reindex.folders_touched(self.plan.rows))
            except Exception:                      # noqa: BLE001
                pass

    def busy(self) -> bool:
        return self.phase in ("planning", "applying")

    def line(self) -> dict:
        """One line for the bar of everything running."""
        from core import load as _load
        cost = _load.since(self.before) if self.before else {}
        return {"id": self.id, "task": self.task.name, "title": self.task.title,
                "icon": self.task.icon, "phase": self.phase,
                "done": self.done, "total": self.total, "now": self.now,
                "cancelled": self.cancel, "by": self.by,
                "cost": _load.describe(cost) if cost else "",
                "seconds": int(time.time() - self.made)}

    def brief(self) -> dict:
        """A run that has finished, for the bar - until you go and look."""
        res = self.result
        return {"id": self.id, "task": self.task.name, "title": self.task.title,
                "icon": self.task.icon, "by": self.by, "ended": self.ended,
                "planned": self.phase == "ready",
                "blocked": bool(self.plan is not None and self.plan.blocked),
                "failed": int(getattr(res, "failed", 0) or 0) + (1 if self.error else 0),
                "done": int(getattr(res, "done", 0) or 0)}

    def worth_telling(self) -> bool:
        """Finished lately - and, for the automation, finished doing something.
        A pass that looked and found nothing is not news."""
        if self.busy() or not self.ended or time.time() - self.ended > 1800:
            return False
        if self.by == "automation":
            return self.phase == "done" and bool(
                getattr(self.result, "done", 0) or getattr(self.result, "failed", 0)
                or self.error)
        return True

    def state(self) -> dict:
        out = {"id": self.id, "phase": self.phase,
               "started": self.started, "finished": self.finished,
               "cancelled": self.cancel, "done": self.done, "total": self.total,
               "now": self.now, "recent": self.recent[-12:], "error": self.error,
               "stumbled": self.stumbled[-500:]}
        if self.phase != "planning" and self.plan is not None:
            out["plan"] = plan_payload(self.task, self.plan, self.id)
        if self.result is not None:
            out["result"] = {
                "done": self.result.done, "failed": self.result.failed,
                "cancelled": self.result.cancelled,
                "stats": [list(x) for x in self.result.stats],
                "details": self.result.lines()[:60]}
        return out


# When the automation last actually DID something.
#
# "Had results" has to mean did something - not "looked and nothing had
# changed", or the mark is permanently lit and you stop seeing it inside a
# week. Kept in memory and seeded from the run log at startup, so it survives a
# restart without the page having to read a file every time it polls.
AUTO_RESULTS: list = []
AUTO_KEEP = 60


def automation_state() -> dict:
    """Which flows run by themselves, and when the soonest next looks.

    Always, not only while something is running - "is this thing working" is a
    question you have when NOTHING is happening, and a bar that appears only
    during a run answers it exactly when you do not need it.

    A flow fired by DSM's Task Scheduler is NOT counted as on here, and that is
    the honest answer rather than a technicality: this app is not going to run
    it, cannot say when DSM will, and a bar claiming otherwise would be
    reassuring and wrong.
    """
    try:
        from core import flows as _f
        mine = [f for f in _f.read() if f.on and f.fired_by == _f.BY_APP]
        by_dsm = [f for f in _f.read() if f.fired_by == _f.BY_DSM]
        last = float(LAST_PASS[0] or 0)
        every = min([f.every for f in mine], default=0) * 60
        return {"on": bool(mine),
                "flows": [f.name for f in mine],
                "by_dsm": [f.name for f in by_dsm],
                "count": len(mine),
                "every_minutes": int(every / 60) if every else None,
                "next_in": max(0, int(every - (time.time() - last)))
                if (mine and last and every) else None,
                "last_pass": last or None,
                "last_result": AUTO_RESULTS[-1] if AUTO_RESULTS else None}
    except Exception:                              # noqa: BLE001
        return {"on": False}


# When the background loop last completed a pass. A list so the loop can set it
# without importing anything back.
LAST_PASS = [0.0]


def note_automation_result(when: float, task: str = "", title: str = "",
                           done: int = 0, failed: int = 0) -> None:
    """One background run that actually did something, and WHAT it did.

    It used to be a bare timestamp, so the unread mark could count runs and say
    nothing about them - which is most of the way to useless: "3" tells you to
    go and look, and the whole point of a mark is to save you going to look at
    a pass that moved four sidecars.
    """
    AUTO_RESULTS.append({"when": float(when), "task": str(task or ""),
                         "title": str(title or task or "a run"),
                         "done": int(done or 0), "failed": int(failed or 0)})
    del AUTO_RESULTS[:-AUTO_KEEP]


def seed_automation_results() -> int:
    """What the log already knows, read once.

    Seeded rather than started empty, so restarting the container does not
    silently mark every background run as read.
    """
    try:
        from core import runlog
        for row in runlog.recent(limit=400):
            if str(row.get("by") or "") != "automation":
                continue
            done, failed = int(row.get("done") or 0), int(row.get("failed") or 0)
            if not (done or failed):
                continue
            name = str(row.get("task") or "")
            task = R.get(name)
            AUTO_RESULTS.append({
                "when": float(row.get("when") or 0), "task": name,
                "title": task.title if task is not None else name,
                "done": done, "failed": failed})
        AUTO_RESULTS.sort(key=lambda x: x["when"])
        del AUTO_RESULTS[:-AUTO_KEEP]
    except Exception:                                  # noqa: BLE001
        pass
    return len(AUTO_RESULTS)


JOBS: dict[str, Job] = {}
JOBS_LOCK = threading.Lock()
KEEP_JOBS_SECONDS = 3600


def work_in_flight() -> int:
    """How many runs are going right now, of any kind.

    For the tray, which asks before a Quit would stop one half way and says on
    its icon that something is running.
    """
    with JOBS_LOCK:
        busy = sum(1 for j in JOBS.values() if j.busy())
    with FILE_LOCK:
        busy += sum(1 for j in FILE_JOBS.values() if not j.finished)
    return busy


def remember(job: Job) -> Job:
    with JOBS_LOCK:
        cutoff = time.time() - KEEP_JOBS_SECONDS
        for old in [k for k, v in JOBS.items()
                    if v.made < cutoff and (v.finished or not v.started)]:
            del JOBS[old]
        JOBS[job.id] = job
    return job


# Answers worth packing. The page is about 700 KB of HTML, script and styles in
# one, and over a phone's Wi-Fi to a NAS that is most of the wait before
# anything is drawn; packed it is about 200 KB. Pictures, clips and downloads
# are already as small as packing will make them, so they go as they are.
GZIP_OVER = 4096
_GZIP_TYPES = ("text/", "application/json", "application/manifest+json",
               "javascript", "css", "image/svg+xml")
_GZIP_KEPT: dict = {}                  # the big answers packed lately
_GZIP_LOCK = threading.Lock()


def _squeezable(ctype: str) -> bool:
    low = str(ctype or "").lower()
    return any(t in low for t in _GZIP_TYPES)


def _takes_gzip(accepted: str) -> bool:
    """Does Accept-Encoding allow gzip? "gzip;q=0" is a no."""
    for part in str(accepted or "").lower().split(","):
        name, _, rest = part.strip().partition(";")
        if name.strip() not in ("gzip", "*"):
            continue
        q = rest.strip()
        if q.startswith("q="):
            try:
                return float(q[2:]) > 0
            except ValueError:
                return False
        return True
    return False


def _gzipped(body: bytes) -> bytes:
    """Packed at level 6. The page is the same bytes on every load, so a big
    answer is packed once and kept, rather than every time somebody opens it."""
    import gzip
    if len(body) < 65536:
        return gzip.compress(body, compresslevel=6, mtime=0)
    with _GZIP_LOCK:
        got = _GZIP_KEPT.get(body)
    if got is None:
        got = gzip.compress(body, compresslevel=6, mtime=0)
        with _GZIP_LOCK:
            if len(_GZIP_KEPT) >= 4:
                _GZIP_KEPT.clear()
            _GZIP_KEPT[body] = got
    return got


# The largest request body the app will read. Every POST is a small JSON
# document - a plan's options, a list of photos, a board's widgets - and the
# biggest real one (a selection of a few thousand paths) is well under a
# megabyte. Anything over this is a mistake or a nuisance, and reading it would
# only tie up a thread and the memory to hold it.
MAX_BODY = 8 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    server_version = "PhotoManager"
    _answered = False
    _parsed: dict | None = None
    _gate: bool | None = None          # this request's answer from _signed_in
    _locked = 0                        # seconds a guesser still has to wait

    def log_message(self, fmt, *args):        # quieter than the default
        pass

    def send_response(self, code, message=None):
        # Remembered so a failure part way through an answer is not followed by
        # a second set of headers, which would garble the first.
        self._answered = True
        super().send_response(code, message)

    def _guarded(self, work) -> None:
        """Run one request, and answer even when it fails.

        Without this, any exception in a route closed the socket with nothing
        said, and the page could only report "Could not reach the app" - the
        same words it uses when the NAS is switched off, for what was really a
        bug with a one-line explanation. So the traceback goes to the log for
        whoever fixes it, and the page gets that one line as JSON.
        """
        self._answered = False
        self._parsed = None
        self._gate = None
        self._locked = 0
        try:
            work()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return                              # the browser went away; nobody to tell
        except Exception as exc:                       # noqa: BLE001
            sys.stderr.write(f"{self.command} {self.path} failed:\n"
                             f"{traceback.format_exc()}")
            sys.stderr.flush()
            if self._answered:
                # Headers are already out; the only honest thing left is to end
                # the connection so the browser sees a broken answer, not a
                # complete-looking short one.
                self.close_connection = True
                return
            line = next((ln.strip() for ln in str(exc).splitlines() if ln.strip()),
                        "")
            said = f"{type(exc).__name__}: {line}" if line else type(exc).__name__
            try:
                self._json({"error": said[:300]}, 500)
            except OSError:
                pass

    def _read_body(self) -> str:
        """Read and check a POST's JSON once. Returns why it was refused, or ''.

        Done before any route sees the request, so every route gets the same
        refusal - a 400 with a sentence - for a body that is too big or is not
        JSON, instead of each one raising its own way.
        """
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0:
            self.close_connection = True
            return "The request gave a length that is not a number."
        if length > MAX_BODY:
            # Not read, so the connection cannot be reused: what is left of the
            # body would be taken for the next request.
            self.close_connection = True
            return (f"That request is too large ({length // (1024 * 1024)} MB); "
                    f"the most the app reads is {MAX_BODY // (1024 * 1024)} MB.")
        raw = self.rfile.read(length) if length else b""
        try:
            said = json.loads(raw or b"{}")
        except ValueError:
            return "That request was not valid JSON."
        if not isinstance(said, dict):
            return "That request was JSON, but not an object."
        self._parsed = said
        return ""

    def _send(self, code: int, body: bytes, ctype: str, cache: bool = False) -> None:
        squeezable = _squeezable(ctype)
        packed = squeezable and len(body) > GZIP_OVER and _takes_gzip(
            self.headers.get("Accept-Encoding", ""))
        if packed:
            body = _gzipped(body)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if packed:
            self.send_header("Content-Encoding", "gzip")
        if squeezable:
            # Whether or not this one was packed: a cache in between must not
            # hand a packed answer to something that did not ask for one.
            self.send_header("Vary", "Accept-Encoding")
        # NOTHING but the icons may be cached, ever.
        #
        # The page and the code behind it change every time files are copied
        # onto the NAS, and a browser holding yesterday's copy produces a bug
        # report about a fault that was fixed - indistinguishable, from the
        # outside, from a Restart that did not pick up the new code. An app
        # served from a folder you edit cannot afford that ambiguity, and it is
        # a page on a home network: there is nothing to save by caching it.
        if cache:
            self.send_header("Cache-Control", "public, max-age=86400")
        else:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def _peer(self) -> str:
        try:
            return str(self.client_address[0])
        except Exception:                              # noqa: BLE001
            return "?"

    def _who(self) -> str:
        """Which machine is knocking - for slowing down a guessing machine.

        The TCP peer, unless that is a proxy named in PM_TRUSTED_PROXY: then the
        nearest address in X-Forwarded-For that is not one of those proxies.
        From the right, because a proxy appends what it saw and everything to
        the left of that is whatever the browser chose to send.
        """
        peer = self._peer()
        if not trusted_proxy(peer):
            return peer
        hops = [h.strip() for h in
                str(self.headers.get("X-Forwarded-For") or "").split(",")
                if h.strip()]
        for hop in reversed(hops):
            if not trusted_proxy(hop):
                return hop
        return hops[0] if hops else peer

    def _at_this_machine(self) -> bool:
        """Is the person asking sitting at the machine the app runs on?"""
        try:
            return ipaddress.ip_address(self._who().strip("[]")).is_loopback
        except ValueError:
            return False

    def _may_choose_fence(self) -> bool:
        """May this request move the PC fence (Setup's trees, the sample)?

        From the PC itself, or once a password is on and this request got past
        it. Otherwise anything on the Wi-Fi could point the library at C:\\
        and then download the disk through the fence it had just moved.
        """
        from core import access
        return self._at_this_machine() or access.is_on()

    def _signed_in(self) -> bool:
        """Once per request, so a wrong Basic password counts as one miss."""
        if self._gate is None:
            self._gate = self._check_gate()
        return self._gate

    def _check_gate(self) -> bool:
        from core import access
        if not access.is_on():
            return True
        if access.ticket_ok(_cookies(self.headers.get("Cookie", "")).get(COOKIE)):
            return True
        header = self.headers.get("Authorization", "")
        if _basic(header) is None:
            return False
        # The same counter as the login form. Basic used to be checked with no
        # bookkeeping at all, so a script could guess at full speed - and each
        # guess is 240,000 rounds of PBKDF2, so a flood of them was also a
        # cheap way to keep the NAS's CPU busy.
        who = self._who()
        left = access.locked_for(who)
        if left:
            self._locked = left
            return False
        if _password_ok(header):
            access.got_in(who)
            return True
        access.missed(who)
        return False

    def _let_in(self) -> bool:
        """Signed in, or shown the door - and which door depends on who asked.

        A BROWSER asking for the page gets the login page, because a browser
        given a 401 shows its own grey box, which cannot say "set a password in
        Setup" or remember you for thirty days. Anything asking for /api gets a
        401 and a sentence, because that is what a script can act on - and
        because the page itself uses that answer to know it has been signed out
        and put the login screen back without losing what you were doing.
        """
        if self._signed_in():
            return True
        route = urlparse(self.path).path.rstrip("/") or "/"
        if route.startswith("/api") and self._locked:
            left = self._locked
            self.close_connection = True
            body = json.dumps({"error": f"Too many wrong tries. Try again in "
                                        f"{left // 60 + 1} minute(s).",
                               "wait": left, "login": True}).encode("utf-8")
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Retry-After", str(left))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return False
        if route.startswith("/api"):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            body = json.dumps({"error": "a password is needed",
                               "login": True}).encode("utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return False
        from app.loginpage import LOGIN
        self._send(200, LOGIN.encode("utf-8"), "text/html; charset=utf-8")
        return False

    def _sign_in(self) -> None:
        """One password, checked slowly, with a delay that grows on failures."""
        from core import access
        who = self._who()
        left = access.locked_for(who)
        if left:
            return self._json({"ok": False, "wait": left,
                               "why": f"Too many wrong tries. Try again in "
                                      f"{left // 60 + 1} minute(s)."}, 429)
        said = self._body()
        if not access.correct(str(said.get("password") or "")):
            access.missed(who)
            return self._json({"ok": False, "why": "That is not the password."},
                              401)
        access.got_in(who)
        days = access.DAYS if said.get("remember", True) else 1
        value = access.ticket(days)
        body = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # HttpOnly so no script on the page can read it; SameSite=Strict so it
        # is never sent by anything else that links here. Not Secure: this is
        # http on a home network, and a flag claiming otherwise would only stop
        # the cookie working.
        self.send_header("Set-Cookie",
                         f"{COOKIE}={value}; Path=/; Max-Age={days * 86400}; "
                         f"HttpOnly; SameSite=Strict")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _sign_out(self) -> None:
        from core import access
        said = self._body()
        if said.get("everywhere"):
            access.sign_out_everywhere()
        body = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Set-Cookie",
                         f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; "
                         f"SameSite=Strict")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._guarded(self._get)

    def _get(self):
        # The login page's own assets, before the gate - a lock that hides the
        # key to itself is not a lock, it is a broken page.
        route = urlparse(self.path).path.rstrip("/") or "/"
        if route in ("/favicon.ico", "/icon-32.png"):
            return self._send(200, ICON_32, "image/png", cache=True)
        if route.startswith("/font/"):
            # The typeface, before the gate like the icon: the sign-in page is
            # set in it too, and it is the same file for everybody.
            from app.page import FONTS
            got = FONTS.get(route[len("/font/"):])
            if got is not None:
                return self._send(200, got, "font/woff2", cache=True)
        if route == "/api/gate":
            from core import access
            return self._json({"on": access.is_on(),
                               "in": self._signed_in(),
                               "fixed": access.from_environment()})
        if route == "/api/client":
            # What this server IS - the first call any client makes, before it
            # has a password and possibly before it knows there is one. Open on
            # purpose, and for that reason it carries nothing about the photos:
            # a name, an id, a version and whether a password is needed. The
            # FOLDERS are added only once you are signed in, because the names
            # of someone's folders are not something to hand to whoever asks.
            from core import access
            from core import identity
            out = identity.describe(public_port(), access.is_on())
            if not self._signed_in():
                out.pop("trees", None)
                out["signed_in"] = False
            else:
                out["signed_in"] = True
            return self._json(out)
        if not self._let_in():
            return
        route = urlparse(self.path).path.rstrip("/") or "/"
        if route in ("/", "/index.html"):
            # the page as built, with any page or Guide wording edits put in
            return self._send(200, pagetext.served(PAGE).encode("utf-8"),
                              "text/html; charset=utf-8")
        if route in ("/favicon.ico", "/icon-32.png"):
            return self._send(200, ICON_32, "image/png", cache=True)
        if route == "/icon-192.png":
            return self._send(200, ICON_192, "image/png", cache=True)
        if route == "/icon-512.png":
            return self._send(200, ICON_512, "image/png", cache=True)
        if route == "/sw.js":
            # Served from the top so it can look after the whole app, and never
            # cached itself - a stale worker is a bug you cannot clear from the
            # phone.
            from app.page import SERVICE_WORKER
            body = SERVICE_WORKER.replace("__RELEASE__", version.RELEASE).replace(
                "__CODE__", str(int(version.WHEN_BUILT))).encode("utf-8")
            return self._send(200, body, "text/javascript; charset=utf-8")
        if route == "/api/health":
            return self._json(health())
        if route == "/api/wording":
            # Setup > Wording: the shipped text of every tool and the local
            # edits to it. Refused unless the developer switch is on.
            from app.tasks import wording as _words
            q = parse_qs(urlparse(self.path).query)
            got, code = _words.answer({k: v[0] for k, v in q.items() if v})
            return self._json(got, code)
        if route == "/api/jobs":
            # Everything in flight, whichever tab started it - the page has no
            # other way to know about a run begun on a feature it is not showing.
            with JOBS_LOCK:
                live = [j.line() for j in JOBS.values() if j.busy()]
            live.sort(key=lambda j: -j["seconds"])
            ended = [j.brief() for j in JOBS.values() if j.worth_telling()]
            from core import load as _load
            return self._json({"running": live, "ended": ended,
                               "auto_results": list(AUTO_RESULTS),
                               "automation": automation_state(),
                               "machine": _load.machine()})
        if route == "/api/tasks":
            from core import settings as _s
            saved = _s.load()
            from core import families as _fam
            from core import desktop as _desk
            # On a PC the two NAS-only tools are left off everything the page
            # draws from this answer: the rail, Tools, Settings and the tab
            # row. They are still registered, so the command line is the same.
            on_pc = _desk.as_program()
            from core import wording as _wording
            shown = set(_fam.offered([t.name for t in R.all_tasks()], on_pc,
                                     _wording.developer_on()))
            out = {"tasks": [_pc_options(d, on_pc) for d in R.describe_all()
                             if d["name"] in shown],
                   "roots": shown_fence(),
                   # The families the sidebar groups the features under. Sent
                   # rather than hard-coded in the page so that one table
                   # decides it, and a feature nobody filed still appears.
                   # What the SIDEBAR draws, so the hidden ones stay in
                   # the header where they were put on purpose: History is
                   # somewhere you go to look back, and a line for it among the
                   # features reads as another thing to do.
                   # Every feature, at whatever level it sits - the Tools
                   # screen draws tabs as well as top-level features, because
                   # "Cull by rating" is what somebody is looking for and it was
                   # one click inside something else.
                   "families": _fam.catalogue(
                       [t.name for t in R.all_tasks()
                        if not t.inline and t.name in shown]),
                   "settings_tasks": [t.name for t in R.all_tasks()
                                      if _fam.is_setting(t.name)
                                      and t.name in shown],
                   # What was left out, so Setup can say so in one line
                   # rather than have two tools vanish without a word.
                   "nas_only": list(_fam.NAS_ONLY) if on_pc else [],
                   # The two or three features this person does every day, which
                   # are different for every person - so they are data, not a
                   # list somebody chose when the app was written.
                   "pinned": [n for n in _fam.pinned() if n in shown],
                   # the three trees, so the page can make one box follow another
                   # without a round trip for every keystroke
                   "trees": {k: str(saved[k] or "") for k in
                             ("library", "raw", "previews")},
                   # The two viewer keys, so the page does not have to guess
                   # what somebody set them to.
                   "keys": {"info": str(saved["key_info"] or "").strip()[:1],
                            "histogram": str(saved["key_histogram"] or "").strip()[:1],
                            # The words on Shift and a number, in order.
                            "quick_tags": [w.strip() for w in
                                           str(saved["quick_tags"] or "")
                                           .replace("\n", ",").split(",")
                                           if w.strip()][:5]},
                   # every tree root, for ONE thing only: working out the
                   # folders they all share, so the page can stop printing them.
                   # Kept apart from "trees" on purpose - a box follows the
                   # trees in that list, and the develop tree is not one to
                   # follow into.
                   "tree_roots": [str(saved[k] or "") for k in
                             ("library", "raw", "previews", "video", "develop")
                             if str(saved[k] or "").strip()]}
            out.update(health())
            return self._json(out)
        # ------------------------------------------------ the photo library
        #
        # Everything under here answers out of the index (`core/catalogue.py`)
        # and touches no photographs. That is what lets the app open ON the
        # library instead of on a form with a button under it.
        if route == "/api/index":
            from core import catalogue as _cat
            return self._json(_cat.shared().state())
        if route == "/api/timeline":
            from core import browse as _b, catalogue as _cat, find as _find
            q = parse_qs(urlparse(self.path).query)
            flat = {k: v[0] for k, v in q.items() if v}
            offset = int(str(flat.pop("offset", "0") or 0) or 0)
            limit = min(600, int(str(flat.pop("limit", "240") or 240) or 240))
            album = str(flat.pop("album", "") or "")
            by = str(flat.pop("by", "date") or "date")
            flat.pop("t", None)
            try:
                ask = _b.album_ask(album) if album else (
                    _find.from_dict(flat) if flat else None)
            except _find.Refused as bad:
                return self._json({"error": str(bad)}, 400)
            return self._json(
                _b.timeline(_cat.shared(), ask, offset, limit, by))
        if route == "/api/places":
            from core import browse as _b, catalogue as _cat
            q = parse_qs(urlparse(self.path).query)
            zoom = int(str((q.get("zoom") or ["4"])[0]) or 4)
            out = _b.clusters(_cat.shared(), zoom)
            if (q.get("named") or [""])[0]:
                out["named"] = _b.named_places(_cat.shared())
            return self._json(out)
        if route == "/api/dashboard":
            # The same numbers until the index or a setting moves, which is what
            # makes Home a screen you look at rather than one you wait for.
            from core import browse as _b, catalogue as _cat
            cat = _cat.shared()
            return self._json(_b.kept(cat, "dashboard", lambda: _b.dashboard(cat)))
        if route == "/api/hidden":
            from core import browse as _b
            return self._json({"hidden": _b.hidden_folders()})
        if route == "/api/pinned":
            from core import families as _fam
            return self._json({"pinned": _fam.pinned()})
        if route == "/api/toolgroups":
            # The tools, grouped the way this person wants them.
            from core import families as _fam
            got = _fam.arranged()
            got["all"] = [{"name": t.name, "title": t.tab or t.title,
                           "line": t.line or t.summary, "icon": t.icon,
                           "setting": _fam.is_setting(t.name)}
                          for t in R.all_tasks() if not t.inline]
            got["built_in"] = [{"key": f["key"], "label": f["label"]}
                               for f in _fam.FAMILIES + [_fam.ALONE]]
            return self._json(got)
        if route == "/api/inside":
            # One folder of the library, from the index: the folders in it and
            # the photographs in it. The folder VIEW rather than the timeline
            # sorted by folder.
            from core import browse as _b, catalogue as _cat, find as _find
            q = parse_qs(urlparse(self.path).query)
            flat = {k: v[0] for k, v in q.items() if v}
            where = str(flat.pop("path", "") or "")
            offset = int(str(flat.pop("offset", "0") or 0) or 0)
            limit = min(600, int(str(flat.pop("limit", "240") or 240) or 240))
            deep = str(flat.pop("deep", "") or "") in ("1", "yes", "true")
            flat.pop("t", None)
            try:
                ask = _find.from_dict(flat) if flat else None
            except _find.Refused as bad:
                return self._json({"error": str(bad)}, 400)
            return self._json(_b.inside(_cat.shared(), where, ask, offset, limit,
                                        deep))
        if route == "/api/choices":
            # What the library holds, per criterion, from the index - so a menu
            # of cameras is there the moment the panel opens.
            from core import browse as _b, catalogue as _cat
            cat = _cat.shared()
            return self._json(_b.kept(cat, "choices", lambda: _b.choices(cat)))
        if route == "/api/folders":
            # The folder board the home screen opens with. The Library tab
            # answers the whole question by surveying five trees; this answers
            # the part the index already holds, with nothing read.
            from core import browse as _b, catalogue as _cat
            q = parse_qs(urlparse(self.path).query)
            only = str((q.get("only") or ["all"])[0] or "all")
            cat = _cat.shared()
            return self._json(_b.kept(cat, "folders:" + only,
                                      lambda: _b.folders(cat, only)))
        if route == "/api/people":
            from core import browse as _b, catalogue as _cat
            cat = _cat.shared()
            return self._json(_b.kept(cat, "people", lambda: _b.people(cat)))
        if route == "/api/albums":
            from core import browse as _b, catalogue as _cat
            cat = _cat.shared()
            shown = _b.kept(cat, "albums", lambda: _b.albums(cat))
            away = _b.hidden_albums()
            out = {"albums": shown, "hidden": away}
            if away:
                # Named, so "3 put away" is a line you can act on rather than a
                # number you have to remember the meaning of.
                known = {a["key"]: a for a in _b.kept(
                    cat, "albums:all", lambda: _b.albums(cat, show_all=True))}
                out["put_away"] = [{"key": k,
                                    "title": known[k]["title"] if k in known
                                             else k.split(":", 1)[-1]}
                                   for k in away]
            return self._json(out)
        if route == "/api/item":
            from core import browse as _b, catalogue as _cat
            wanted = (parse_qs(urlparse(self.path).query).get("path") or [""])[0]
            if not wanted or not path_allowed(wanted):
                return self._json({"error": "outside the allowed folders"}, 403)
            return self._json(_b.detail(_cat.shared(), wanted))
        if route == "/api/exists":
            # Fenced like everything else: "is there a folder called this" is
            # a question that maps a disk one guess at a time. Outside the fence
            # the answer is None - not False, which the page reads as "gone".
            wanted = parse_qs(urlparse(self.path).query).get("path") or []
            return self._json({"there": {
                w: (bool(w and os.path.isdir(w)) if w and path_allowed(w) else None)
                for w in wanted[:20]}})
        if route == "/api/files":
            from core import filesops
            q = parse_qs(urlparse(self.path).query)
            wanted = (q.get("path") or [""])[0].strip()
            if not wanted:
                from core import settings as _s
                wanted = str(_s.load()["library"] or "").strip() or os.path.expanduser("~")
            if not path_allowed(wanted):
                return self._json({"error": "outside the allowed folders"}, 403)
            try:
                return self._json(filesops.entries(
                    wanted, hidden=(q.get("hidden") or [""])[0] == "1",
                    deep=(q.get("deep") or [""])[0] == "1"))
            except filesops.Refused as exc:
                return self._json({"error": str(exc)}, 404)
            except OSError as exc:
                return self._json({"error": str(exc)}, 500)
        if route == "/api/folder-status":
            from core import filesops
            wanted = (parse_qs(urlparse(self.path).query).get("path") or [""])[0]
            if not path_allowed(wanted):
                return self._json({"error": "outside the allowed folders"}, 403)
            try:
                return self._json(filesops.status(wanted))
            except filesops.Refused as exc:
                return self._json({"error": str(exc)}, 404)
        if route == "/api/photo-marks":
            from core import filesops
            q = parse_qs(urlparse(self.path).query)
            wanted = (q.get("path") or [""])[0]
            if not path_allowed(wanted):
                return self._json({"error": "outside the allowed folders"}, 403)
            try:
                return self._json(filesops.marks(
                    wanted, deep=(q.get("deep") or [""])[0] == "1"))
            except filesops.Refused as exc:
                return self._json({"error": str(exc)}, 404)
        if route == "/api/searches":
            from core import find
            return self._json({"kept": [{"name": n, "ask": a}
                                        for n, a in find.saved()]})
        if route == "/api/values":
            from core import settings as _s
            from core import stats as _stats
            q = parse_qs(urlparse(self.path).query)
            dim = (q.get("dim") or [""])[0]
            where = [p for p in (q.get("path") or []) if p.strip()]
            if not where:
                where = [str(_s.load()["library"] or "").strip()]
            for one in where:
                if not path_allowed(one):
                    return self._json({"error": "outside the allowed folders"}, 403)
            try:
                return self._json(_stats.values(where, dim))
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
        if route == "/api/rename-list":
            from core import renames
            q = parse_qs(urlparse(self.path).query)
            wanted = (q.get("path") or [""])[0]
            picked = [p for p in (q.get("picked") or []) if p.strip()]
            for one in [wanted] + picked:
                if one and not path_allowed(one):
                    return self._json({"error": "outside the allowed folders"}, 403)
            try:
                depth = int((q.get("depth") or ["1"])[0] or 1)
            except ValueError:
                depth = 1
            try:
                start = int((q.get("start") or ["0"])[0] or 0)
            except ValueError:
                start = 0
            try:
                return self._json(renames.listing(wanted, depth, picked, start))
            except renames.Refused as exc:
                return self._json({"error": str(exc)}, 404)
        if route == "/api/folder-size":
            from core import filesops
            wanted = (parse_qs(urlparse(self.path).query).get("path") or [""])[0]
            if not path_allowed(wanted):
                return self._json({"error": "outside the allowed folders"}, 403)
            try:
                return self._json(filesops.weigh(wanted))
            except filesops.Refused as exc:
                return self._json({"error": str(exc)}, 404)
        if route == "/api/files/progress":
            wanted = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
            with FILE_LOCK:
                job = FILE_JOBS.get(wanted)
            if job is None:
                return self._json({"error": "no such run"}, 404)
            return self._json(job.state())
        if route == "/api/download":
            return self._download(
                (parse_qs(urlparse(self.path).query).get("path") or [""])[0])
        if route == "/api/pattern":
            from core import naming
            pat = (parse_qs(urlparse(self.path).query).get("p") or [""])[0]
            why = naming.problem(pat)
            return self._json({"problem": why,
                               "example": "" if why else naming.example(pat),
                               "place": naming.needs_place(pat)})
        if route == "/api/photo":
            from core import quickedit as QE
            wanted = (parse_qs(urlparse(self.path).query).get("path") or [""])[0]
            if not path_allowed(wanted):
                return self._json({"error": "outside the allowed folders"}, 403)
            try:
                out = QE.state(wanted)
            except QE.Refused as exc:
                return self._json({"error": str(exc)}, 404)
            out["vocab"] = QE.vocabulary(out["tags"])
            out["colours"] = QE.colours()
            # How it was exposed, on the same request that fetches the marks:
            # the viewer asks for this on every photograph it opens, and two
            # round trips per swipe is one too many over a phone connection.
            try:
                out["shot"] = QE.shot(wanted)
            except Exception:                          # noqa: BLE001
                out["shot"] = {}
            return self._json(out)
        if route == "/api/photo-about":
            from core import quickedit as QE
            wanted = (parse_qs(urlparse(self.path).query).get("path") or [""])[0]
            if not path_allowed(wanted):
                return self._json({"error": "outside the allowed folders"}, 403)
            try:
                return self._json(QE.about(wanted))
            except QE.Refused as exc:
                return self._json({"error": str(exc)}, 404)
        if route == "/api/thumb":
            q = parse_qs(urlparse(self.path).query)
            return self._thumb((q.get("path") or [""])[0], (q.get("s") or ["s"])[0])
        if route == "/api/file":
            return self._one_file(
                (parse_qs(urlparse(self.path).query).get("path") or [""])[0])
        if route == "/api/video":
            return self._video(
                (parse_qs(urlparse(self.path).query).get("path") or [""])[0])
        if route == "/api/flows":
            from app.tasks import flows as _flows
            return self._json({"flows": _flows.described(),
                               "catalogue": _flows.catalogue(),
                               "trees": [list(t) for t in _FLOWS.TREES],
                               "fired_by": [list(x) for x in _FLOWS.FIRED_BY],
                               "do": [list(x) for x in _FLOWS.DO]})
        if route == "/api/browse":
            q = parse_qs(urlparse(self.path).query)
            wanted = (q.get("path") or [""])[0]
            files = (q.get("files") or [""])[0]
            try:
                return self._json(browse(wanted, files))
            except Exception:                      # noqa: BLE001
                return self._json({"path": wanted, "parent": None, "folders": [],
                                   "files": [], "error": "that folder could not "
                                                         "be read"})
        if route == "/api/progress":
            wanted = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
            with JOBS_LOCK:
                job = JOBS.get(wanted)
            if job is None:
                return self._json({"error": "no such run"}, 404)
            return self._json(job.state())
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        self._guarded(self._post)

    def _foreign(self) -> str:
        """Why this POST cannot have come from this app's own page, or ''.

        Every POST changes something, and with no password set the only thing
        between a web page on some other site and `/api/files` was the
        browser's good manners - which allow a form-shaped POST to anywhere.
        Two checks, both cheap:

        - **Origin.** A browser names the page a request came from. One that is
          not this app's own address (scheme, name and port) is refused.
          Scripts and curl send no Origin and are not affected.
        - **Host, with no password set.** A site can point a name it owns at
          this machine's address, and then its pages ARE the same origin. So
          a name nobody here chose (see `known_name`) is refused. With a
          password that name has no cookie and cannot sign in, so it is let be,
          and a reverse proxy's public name needs no setting.
        """
        from core import access
        host = str(self.headers.get("Host") or "").strip()
        hosts = [host]
        via_proxy = trusted_proxy(self._peer())
        if via_proxy:
            hosts += [h.strip() for h in
                      str(self.headers.get("X-Forwarded-Host") or "").split(",")
                      if h.strip()]
        origin = self.headers.get("Origin")
        if origin is not None and not same_place(origin, hosts):
            return (f"This request came from a page at {origin.strip()[:80]}, "
                    f"not from this app, so it was refused.")
        if not access.is_on() and not via_proxy and not known_name(_host_port(host)[0]):
            return (f"This app was reached as {_host_port(host)[0][:80]}, a name "
                    f"it does not know, so the request was refused. Use its "
                    f"address, or add the name to PM_HOSTS where the app is "
                    f"started.")
        return ""

    def _post(self):
        foreign = self._foreign()
        if foreign:
            # Not read, so the connection cannot be reused: what is left of the
            # body would be taken for the next request.
            self.close_connection = True
            return self._json({"error": foreign}, 403)
        refused = self._read_body()
        if refused:
            return self._json({"error": refused}, 400)
        route = urlparse(self.path).path.rstrip("/")
        if route == "/api/login":
            return self._sign_in()
        if route == "/api/logout":
            return self._sign_out()
        if not self._let_in():
            return
        if route == "/api/apply":
            return self._apply()
        if route == "/api/cancel":
            return self._cancel()
        if route == "/api/quit":
            # Only when this was started as a desktop program. On the NAS the
            # container has a stop button and this one would only be a way to
            # take the app off the network with nothing to bring it back.
            from core import desktop
            if not desktop.as_program():
                return self._json({"error": "this copy is not stopped from here - "
                                            "it is started and stopped by "
                                            "whatever runs it"}, 400)
            self._json({"stopping": True})
            # Through desktop.quit rather than straight out, so the icon by
            # the clock goes with it instead of lingering as a ghost.
            threading.Timer(0.4, desktop.quit).start()
            return None
        if route == "/api/wording":
            from app.tasks import wording as _words
            got, code = _words.change(self._body())
            return self._json(got, code)
        if route == "/api/people":
            from core import browse as _b, catalogue as _cat
            body = self._body()
            names = _b.people_named()
            add = str(body.get("add") or "").strip()
            drop = str(body.get("remove") or "").strip()
            if add and add.lower() not in [n.lower() for n in names]:
                names.append(add)
            if drop:
                names = [n for n in names if n.lower() != drop.lower()]
            _b.name_people(names)
            return self._json(_b.people(_cat.shared()))
        if route == "/api/index":
            from core import catalogue as _cat
            body = self._body()
            cat = _cat.shared()
            deep = bool(body.get("deep"))
            # Re-read library is a person asking, and a person is not refused
            # because the minute's own pass happens to be running: that pass is
            # stopped and the one asked for starts in its place. The ordinary
            # pass (deep off) still yields to one already running.
            if deep and cat.busy():
                cat.stop()
                cat.wait(30)
            started = cat.start(_cat.wanted_roots(), deep=deep)
            if started:
                threading.Thread(target=lambda: warm_newest(cat, cat.wait()),
                                 daemon=True).start()
            return self._json({"started": started, **cat.state()})
        if route == "/api/save":
            return self._save()
        if route == "/api/flows":
            return self._flows()
        if route == "/api/photo":
            return self._photo_edit()
        if route == "/api/files":
            return self._files()
        if route == "/api/rename":
            return self._rename_many()
        if route == "/api/boards":
            # The dashboard as it is arranged. Every edit is the same shape: a
            # list of widget names in the order they are drawn.
            from core import boards
            try:
                body = self._body()
                what = str(body.get("do") or "keep")
                if what == "keep":
                    boards.keep(body.get("widgets") or [],
                                str(body.get("board") or ""))
                elif what == "show":
                    boards.show(str(body.get("board") or ""))
                elif what == "add":
                    boards.add(str(body.get("name") or ""),
                               str(body.get("like") or ""))
                elif what == "rename":
                    boards.rename(str(body.get("board") or ""),
                                  str(body.get("name") or ""))
                elif what == "drop":
                    boards.drop(str(body.get("board") or ""))
                elif what == "reset":
                    boards.reset(str(body.get("board") or ""))
                else:
                    return self._json({"error": "no such change"}, 400)
                return self._json({"now": boards.now(),
                                   "boards": boards.names(),
                                   "widgets": boards.catalogue()})
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
        if route == "/api/bands":
            # Where the brackets fall on a chart. Refused whole or kept whole:
            # half a table would mis-sort a library and still look right.
            from core import bands
            try:
                body = self._body()
                name = str(body.get("set") or "")
                if body.get("reset"):
                    bands.reset(name)
                else:
                    bands.save(name, str(body.get("text") or ""))
                return self._json({"set": name, "how": bands.how(name),
                                   "text": bands.as_text(name)})
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
        if route == "/api/cameras":
            from core import devices
            try:
                body = self._body()
                have = devices.rename(str(body.get("model") or ""),
                                      str(body.get("name") or ""))
                return self._json({"named": have,
                                   "label": devices.label(
                                       str(body.get("model") or "")),
                                   "how": devices.how(
                                       str(body.get("model") or ""))})
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
        if route == "/api/albums":
            from core import browse as _b
            body = self._body()
            return self._json({"hidden": _b.hide_albums(body.get("hidden") or [])})
        if route == "/api/pinned":
            from core import families as _fam
            body = self._body()
            return self._json({"pinned": _fam.pin(body.get("pinned") or [])})
        if route == "/api/toolgroups":
            from core import families as _fam
            body = self._body()
            if body.get("reset"):
                _fam.forget_arrangement()
                return self._json(_fam.arranged())
            got = _fam.save_arranged(body.get("groups") or [],
                                     body.get("hidden") or [])
            return self._json(got)
        if route == "/api/hidden":
            # Folders left out of the Photos screen. A view, not an exclusion:
            # everything here is still indexed, still counted, still backed up.
            import json as _json
            from core import browse as _b, settings as _s
            body = self._body()
            folders = [str(f).strip().rstrip("/\\")
                       for f in (body.get("folders") or []) if str(f).strip()]
            folders = [f for f in folders if path_allowed(f)][:400]
            _s.save({"hide_in_grid": _json.dumps(folders)})
            return self._json({"hidden": _b.hidden_folders()})
        if route == "/api/searches":
            from core import find
            try:
                body = self._body()
                if body.get("forget"):
                    have = find.forget(str(body["forget"]))
                else:
                    have = find.keep(str(body.get("name") or ""),
                                     find.from_dict(body.get("ask") or {}))
                return self._json({"kept": [{"name": n, "ask": a}
                                            for n, a in have]})
            except find.Refused as exc:
                return self._json({"error": str(exc)}, 400)
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
        if route == "/api/files-of":
            return self._files_of()
        if route == "/api/patterns":
            from core import naming
            try:
                body = self._body()
                if body.get("forget"):
                    have = naming.forget(str(body["forget"]))
                else:
                    have = naming.keep(str(body.get("name") or ""),
                                       str(body.get("pattern") or ""))
                return self._json({"kept": [{"name": n, "pattern": p,
                                             "label": naming.label(p)}
                                            for n, p in have]})
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
        if route != "/api/plan":
            return self._send(404, b"not found", "text/plain")
        try:
            body = self._body()
            task = R.get(str(body.get("task", "")))
            if task is None:
                return self._json({"error": "no such tool"}, 400)
            opts = task.coerce(body.get("options") or {})
            bad = check_paths(task, opts, choosing=self._may_choose_fence())
            if bad:
                # A whole plan shape, refused - not a bare {"blocked": ...}. The
                # page draws a plan; handing it half of one made it fall over on
                # the first missing list, and the error it showed was about
                # reading 'length' rather than about the folder it refused.
                return self._json(plan_payload(task, R.Plan(task=task.name,
                                                            blocked=bad), ""))
            # Planning is work, not a question with an instant answer: a Library
            # survey reads the front of every JPEG over SMB. Holding the HTTP
            # request open for it means no progress, no cancelling, and a page
            # that looks hung - so it becomes a job with an id, exactly like the
            # applying half, and the bar can show it.
            job = remember(Job(task, raw=body.get("options") or {}))
            threading.Thread(target=job.look, daemon=True).start()
            return self._json({"id": job.id, "phase": job.phase,
                               "task": task.name, "title": task.title})
        except Exception:
            return self._json({"error": traceback.format_exc(limit=4)}, 500)

    TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".jpe": "image/jpeg",
             ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
             ".tif": "image/tiff", ".tiff": "image/tiff",
             ".heic": "image/heic", ".heif": "image/heif"}
    MAX_FILE = 80 * 1024 * 1024
    # A download is a file leaving the NAS through this app. Generous enough
    # for a RAW and small enough that nobody tries to take the library home
    # through a phone browser.
    MAX_DOWNLOAD = 2 * 1024 * 1024 * 1024

    def _one_file(self, wanted: str):
        """One picture, so a plan can be checked against the photo itself.

        Reading a list of file names and deciding whether to cull them is a
        guess; seeing the photo is not. Three guards, and they are the same ones
        every task gets: inside the allowed roots, resolved first so a symlink
        cannot step out, and a picture rather than whatever else is on the disk.
        This serves files - it must never become a way to read /etc/passwd.
        """
        wanted = (wanted or "").strip()
        if not wanted or not os.path.isfile(wanted):
            return self._send(404, b"not there", "text/plain")
        if not path_allowed(wanted):
            return self._send(403, b"outside the allowed folders", "text/plain")
        ext = os.path.splitext(wanted)[1].lower()
        if ext not in self.TYPES:
            return self._send(415, b"not a picture", "text/plain")
        try:
            if os.path.getsize(wanted) > self.MAX_FILE:
                return self._send(413, b"too big to show", "text/plain")
            with open(wanted, "rb") as fh:
                body = fh.read()
        except OSError as exc:
            return self._send(500, str(exc).encode("utf-8"), "text/plain")
        return self._send(200, body, self.TYPES[ext], cache=True)

    # What a browser will actually play, and what it will not.
    #
    # An honest list matters more than a long one: a clip the browser cannot
    # decode plays as a black rectangle with no error, which reads as a broken
    # app rather than as a format nothing in a browser has ever supported. MTS
    # and AVI are the two a camera most often writes and a browser never plays,
    # so they are named and offered as a download instead.
    PLAYS = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
             ".webm": "video/webm", ".ogv": "video/ogg"}
    WONT_PLAY = (".mts", ".m2ts", ".avi", ".wmv", ".mpg", ".mpeg", ".3gp",
                 ".mkv", ".flv")

    def _video(self, wanted: str):
        """One clip, streamed, so it can be played and scrubbed.

        The whole file in one response is not a video player: a browser cannot
        seek in it, a two-gigabyte clip is read into memory to answer, and
        pressing play waits for all of it. So this answers Range requests - the
        browser asks for the part it needs and the file is read a block at a
        time - which is the difference between a player and a download that
        happens to be a film.

        The same three guards as every other file this app serves: inside the
        allowed roots, a real file, and an extension this will admit to.
        """
        wanted = (wanted or "").strip()
        if not wanted or not os.path.isfile(wanted):
            return self._send(404, b"not there", "text/plain")
        if not path_allowed(wanted):
            return self._send(403, b"outside the allowed folders", "text/plain")
        ext = os.path.splitext(wanted)[1].lower()
        if ext not in self.PLAYS:
            return self._send(415, b"not a clip a browser can play", "text/plain")
        try:
            size = os.path.getsize(wanted)
        except OSError as exc:
            return self._send(500, str(exc).encode("utf-8"), "text/plain")

        start, end = 0, size - 1
        asked = str(self.headers.get("Range") or "").strip()
        partial = False
        if asked.startswith("bytes="):
            bit = asked[6:].split(",")[0].strip()
            lo, _sep, hi = bit.partition("-")
            try:
                if lo:
                    start = int(lo)
                    if hi:
                        end = min(int(hi), size - 1)
                elif hi:                       # "bytes=-500": the last 500
                    start = max(0, size - int(hi))
            except ValueError:
                start, end = 0, size - 1
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            partial = True

        length = end - start + 1
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", self.PLAYS[ext])
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "private, max-age=600")
        self.end_headers()
        if self.command == "HEAD":
            return None
        try:
            with open(wanted, "rb") as fh:
                fh.seek(start)
                left = length
                while left > 0:
                    block = fh.read(min(256 * 1024, left))
                    if not block:
                        break
                    self.wfile.write(block)
                    left -= len(block)
        except (OSError, BrokenPipeError, ConnectionResetError):
            # A browser that seeks closes the connection mid-block, every time.
            # That is not an error and must not be logged as one.
            return None
        return None

    def _thumb(self, wanted: str, size: str):
        """A small picture of one photo - the same fence as /api/file."""
        from core import thumbs
        wanted = (wanted or "").strip()
        if not wanted or not os.path.isfile(wanted):
            return self._send(404, b"not there", "text/plain")
        if not path_allowed(wanted):
            return self._send(403, b"outside the allowed folders", "text/plain")
        if not thumbs.can_show(wanted):
            return self._send(415, b"not a picture", "text/plain")
        body = thumbs.thumb(wanted, size)
        if not body:
            return self._send(404, b"nothing to show", "text/plain")
        return self._send(200, body, "image/jpeg", cache=True)

    def _download(self, wanted: str):
        """One file, to the machine you are browsing from.

        The same fence as everything else, and a size limit: this is for
        fetching a photograph or a sidecar, not for streaming the library
        through a phone browser.
        """
        wanted = (wanted or "").strip()
        if not wanted or not os.path.isfile(wanted):
            return self._send(404, b"not there", "text/plain")
        if not path_allowed(wanted):
            return self._send(403, b"outside the allowed folders", "text/plain")
        try:
            size = os.path.getsize(wanted)
        except OSError as exc:
            return self._send(500, str(exc).encode("utf-8"), "text/plain")
        if size > self.MAX_DOWNLOAD:
            return self._send(413, b"too big to download from here", "text/plain")
        ext = os.path.splitext(wanted)[1].lower()
        self.send_response(200)
        self.send_header("Content-Type",
                         self.TYPES.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", attachment(os.path.basename(wanted)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            with open(wanted, "rb") as fh:
                shutil.copyfileobj(fh, self.wfile, 1024 * 256)
        except (OSError, BrokenPipeError):
            pass

    def _files(self):
        """Everything the file manager does that writes."""
        from core import filesops
        try:
            body = self._body()
        except ValueError:
            return self._json({"error": "that was not JSON"}, 400)
        do = str(body.get("do") or "")
        picked = [str(p) for p in (body.get("paths") or []) if str(p).strip()]
        into = str(body.get("into") or "")
        if do in ("copy", "move", "mkdir") and not into.strip():
            # Blank used to skip the fence and then mean the server's working
            # directory - wherever the app happened to be started from.
            what = "make it in" if do == "mkdir" else do + " into"
            return self._json({"error": f"Choose the folder to {what} first."},
                              400)
        for one in picked + ([into] if into else []):
            if not path_allowed(one):
                return self._json({"error": f"{one} is outside the allowed "
                                            f"folders"}, 403)
        with_raw = bool(body.get("with_raw", True))
        with_previews = bool(body.get("with_previews", True))
        try:
            if do in ("copy", "move"):
                jobs = filesops.gather(picked, into, with_raw, with_previews)
                if not jobs:
                    return self._json({"error": "nothing there to " + do}, 400)
                job = start_file_job(into, jobs, do == "move")
                return self._json({"id": job.id, "total": len(jobs),
                                   "state": job.state()})
            if do == "cancel":
                with FILE_LOCK:
                    job = FILE_JOBS.get(str(body.get("id") or ""))
                if job:
                    job.cancel = True
                return self._json({"stopping": bool(job)})
            if do == "rename":
                # The fence, which this branch did not have: `paths` is checked
                # above and rename carries its subject in `path`.
                one = str(body.get("path") or "")
                if not path_allowed(one):
                    return self._json({"error": f"{one} is outside the allowed "
                                                f"folders"}, 403)
                got = filesops.rename(one, str(body.get("name") or ""))
                record_moves("rename", {"folder": os.path.dirname(one)},
                             got.get("moves"))
                return self._json(got)
            if do == "mkdir":
                return self._json(filesops.make_folder(into, str(body.get("name") or "")))
            if do == "delete":
                where = {"folder": into or (picked[0] if picked else "")}
                try:
                    got = filesops.delete(picked, with_raw, with_previews)
                except filesops.Partly as exc:
                    # Some had already gone into the Recycle Bin: recorded, so
                    # History can put them back, and handed to the page too.
                    record_moves("files", where, exc.moves, action="delete",
                                 size=exc.size, failed=1)
                    return self._json({"error": str(exc), "moves": exc.moves},
                                      409)
                record_moves("files", where, got["moves"], action="delete",
                             size=got["bytes"])
                return self._json(got)
            if do == "undo":
                moves = [m for m in (body.get("moves") or [])
                         if isinstance(m, list) and len(m) == 2
                         and path_allowed(str(m[0])) and path_allowed(str(m[1]))]
                return self._json(filesops.undo(moves))
            return self._json({"error": f"nothing called {do!r}"}, 400)
        except filesops.Refused as exc:
            return self._json({"error": str(exc)}, 409)
        except Exception as exc:                       # noqa: BLE001
            return self._json({"error": f"could not do that: {exc}"}, 500)

    def _rename_many(self):
        """The power rename table: check it, fill it from a pattern, or do it.

        Checking is the server's job as well as the page's. The page checks so
        the table can say what is wrong while you type; the server checks again
        because a browser tab left open for an hour is describing a folder that
        may have been renamed by somebody else since.
        """
        from core import renames
        try:
            body = self._body()
        except ValueError:
            return self._json({"error": "that was not JSON"}, 400)
        do = str(body.get("do") or "check")
        rows = [r for r in (body.get("rows") or []) if isinstance(r, dict)]
        for one in rows:
            if not path_allowed(str(one.get("path") or "")):
                return self._json({"error": f"{one.get('path')} is outside the "
                                            f"allowed folders"}, 403)
        try:
            if do == "check":
                return self._json(renames.check(rows))
            if do == "pattern":
                pattern = str(body.get("pattern") or "")
                from core import naming
                why = naming.problem(pattern)
                if why:
                    return self._json({"error": why}, 400)
                if naming.needs_place(pattern):
                    return self._json({"error": "a pattern that needs a place "
                                                "cannot name a folder here - the "
                                                "date, month, Hijri month and "
                                                "camera ones can"}, 400)
                paths = [str(r.get("path") or "") for r in rows]
                names = renames.by_pattern(
                    paths, pattern,
                    int(body.get("week_starts") or 0),
                    int(body.get("hijri_shift") or 0))
                return self._json({"names": names})
            if do == "apply":
                got = renames.apply(rows, bool(body.get("with_raw", True)),
                                    bool(body.get("with_previews", True)))
                from core import runlog
                res = R.Result(
                    done=got["renamed"], failed=len(got["failed"]),
                    details=[f"{os.path.basename(m[0])}  ->  {os.path.basename(m[1])}"
                             for m in got["moves"][:40]] + got["failed"][:20])
                res.moves = [list(m) for m in got["moves"]]
                res.stats = [("Folders renamed", f"{got['renamed']:,}"),
                             ("Mirrored in other trees", f"{got['mirrored']:,}")]
                runlog.record("rename", {"folder": os.path.dirname(
                    str(rows[0].get("path") or "")) if rows else ""}, res)
                return self._json(got)
            if do == "undo":
                from core import filesops
                moves = [m for m in (body.get("moves") or [])
                         if isinstance(m, list) and len(m) == 2
                         and path_allowed(str(m[0])) and path_allowed(str(m[1]))]
                # Deepest last going forward means deepest FIRST coming back:
                # a child is only put back once its parent has its old name.
                moves.sort(key=lambda m: str(m[1]).count(os.sep))
                return self._json(filesops.undo(moves))
            return self._json({"error": f"nothing called {do!r}"}, 400)
        except renames.Refused as exc:
            return self._json({"error": str(exc)}, 409)
        except Exception as exc:                       # noqa: BLE001
            return self._json({"error": f"could not do that: {exc}"}, 500)

    def _files_of(self):
        """A listing of files that do not share a folder.

        What a search hands the file manager. The manager is built around one
        folder at a time, which is the right shape for moving things about and
        the wrong shape for "these forty, wherever they are" - so this is the
        one listing that is a set of paths rather than a place, and it carries
        the same fields as any other so every button above it still works.
        """
        from core import filesops
        try:
            body = self._body()
        except ValueError:
            return self._json({"error": "that was not JSON"}, 400)
        paths = [str(p) for p in (body.get("paths") or []) if str(p).strip()]
        # The same ceiling as a search keeps, so what a search found can be
        # handed over whole rather than losing its tail at the door.
        from core import find as _find
        if len(paths) > _find.CAP:
            paths = paths[:_find.CAP]
        files, missing = [], 0
        for one in paths:
            if not path_allowed(one):
                return self._json({"error": f"{one} is outside the allowed "
                                            f"folders"}, 403)
            try:
                st = os.stat(one)
            except OSError:
                missing += 1
                continue
            files.append({"name": os.path.basename(one), "path": one,
                          "size": st.st_size, "when": st.st_mtime,
                          "kind": filesops.kind(one),
                          "folder": os.path.dirname(one)})
        return self._json({"path": "", "parent": "", "crumbs": [], "folders": [],
                           "files": files, "size": sum(f["size"] for f in files),
                           "roots": filesops.roots(), "found": True,
                           "missing": missing})

    def _photo_edit(self):
        """One change to one photo, from the viewer. Same fence as everything."""
        from core import quickedit as QE
        try:
            body = self._body()
        except ValueError:
            return self._json({"error": "that was not JSON"}, 400)
        do = str(body.get("do") or "")
        path = str(body.get("path") or "")
        if do == "undo":
            moves = [m for m in (body.get("moves") or [])
                     if isinstance(m, list) and len(m) == 2
                     and path_allowed(str(m[0])) and path_allowed(str(m[1]))]
            return self._json(QE.undo(moves))
        if not path_allowed(path):
            return self._json({"error": "outside the allowed folders"}, 403)
        value = body.get("value")
        acts = {"stars": QE.set_stars, "colour": QE.set_colour,
                "tag": QE.add_tag, "untag": QE.remove_tag}
        try:
            if do == "delete":
                def weigh(moves):
                    size = 0
                    for _was, now in moves:
                        try:
                            size += os.path.getsize(now)
                        except OSError:
                            pass
                    return size
                try:
                    out = QE.delete(path)
                except QE.Partly as exc:
                    record_moves("files", {"photo": path}, exc.moves,
                                 action="delete", size=weigh(exc.moves), failed=1)
                    return self._json({"error": str(exc), "moves": exc.moves},
                                      409)
                # In History like any run, with its moves, and counted as put
                # aside. A copy on a share with no bin is said, not skipped.
                record_moves("files", {"photo": path}, out["moves"],
                             action="delete", size=weigh(out["moves"]),
                             details=[f"{m[0]}  ->  {m[1]}" for m in out["moves"]]
                             + [f"{k}: left where it is - its share has no "
                                f"Recycle Bin" for k in out.get("kept", [])])
                return self._json(out)
            if do == "unlocate":
                out = QE.unlocate(path)
                from core import runlog
                res = R.Result(done=int(out.get("taken") or 0),
                               details=[f"location removed from {os.path.basename(path)}"
                                        f" and {out.get('copies', 1) - 1} copy(s)"])
                runlog.record("unlocate", {"photo": path}, res)
                return self._json(out)
            if do == "rename":
                from core import filesops
                try:
                    got = filesops.rename(path, str(body.get("name") or ""))
                    record_moves("rename", {"folder": os.path.dirname(path)},
                                 got.get("moves"))
                    return self._json(got)
                except filesops.Refused as exc:
                    return self._json({"error": str(exc)}, 409)
            if do not in acts:
                return self._json({"error": f"nothing called {do!r}"}, 400)
            return self._json(acts[do](path, value))
        except QE.Refused as exc:
            return self._json({"error": str(exc)}, 409)
        except Exception as exc:                       # noqa: BLE001
            return self._json({"error": f"could not do that: {exc}"}, 500)

    def _body(self) -> dict:
        """The request's JSON, already read and checked by _read_body."""
        return self._parsed if self._parsed is not None else {}

    def _job(self, body) -> Job | None:
        with JOBS_LOCK:
            return JOBS.get(str(body.get("id", "")))

    def _apply(self):
        """Start the run the person just previewed. Returns at once; ask /api/progress."""
        try:
            job = self._job(self._body())
            if job is None:
                return self._json({"error": "That preview has expired. Show me what "
                                            "would happen again, then apply."}, 400)
            if job.plan.blocked:
                return self._json({"error": job.plan.blocked}, 400)
            writes = (job.task.writes if job.plan.writes is None
                      else bool(job.plan.writes))
            if not writes:
                return self._json({"error": "This tool only reports."}, 400)
            with JOBS_LOCK:
                if job.started:
                    return self._json(job.state())
                refused = claim_trees(job)
                if refused:
                    return self._json({"error": refused, "busy": True}, 409)
                job.started = True
            threading.Thread(target=job.run, daemon=True).start()
            return self._json(job.state())
        except Exception:                          # noqa: BLE001
            return self._json({"error": traceback.format_exc(limit=4)}, 500)

    def _save(self):
        """Save a settings tab, in one press.

        Every other tab shows what would happen and waits, which is right for
        moving four hundred photographs and absurd for writing down where your
        library is. Worse, it meant a path typed and then walked away from was
        never saved - silently - which is how somebody comes to believe the app
        remembers nothing.

        Still plan-then-apply underneath, because a settings tab that refuses -
        a library that is not there, an exports folder inside the develop tree -
        has to be able to say so instead of saving something wrong.
        """
        try:
            body = self._body()
            task = R.get(str(body.get("task", "")))
            if task is None or not task.settings:
                return self._json({"error": "that tab does not save settings"}, 400)
            opts = task.coerce(body.get("options") or {})
            bad = check_paths(task, opts, choosing=self._may_choose_fence())
            if bad:
                return self._json(plan_payload(task, R.Plan(task=task.name,
                                                            blocked=bad), ""))
            plan = task.make_plan(body.get("options") or {})
            out = plan_payload(task, plan, "")
            if plan.blocked:
                return self._json(out)
            result = task.apply(plan)
            out["saved"] = result.failed == 0
            # The index follows the library now rather than on its next
            # minute: the old library's photographs leave before this answers,
            # so the page's redraw after Save already shows the new one, and
            # the loop starts reading it.
            if out["saved"]:
                follow_setup()
            out["result"] = {"done": result.done, "failed": result.failed,
                             "cancelled": False,
                             "stats": [list(x) for x in result.stats],
                             "details": result.lines()[:60]}
            return self._json(out)
        except Exception:                          # noqa: BLE001
            return self._json({"error": traceback.format_exc(limit=4)}, 500)

    def _flows(self):
        """Save the flows, whole.

        The whole list rather than one flow at a time, because order matters
        here in two ways - the order of the steps inside a flow is the order the
        work happens, and a half-saved list is a flow that runs steps nobody
        assembled. One write, or none.

        It refuses a flow that would send photographs round in a ring, at the
        moment of saving rather than at the moment of running: a flow you can
        save and cannot run is a flow you will find out about at four in the
        morning.
        """
        try:
            body = self._body()
            given = body.get("flows")
            if not isinstance(given, list):
                return self._json({"error": "no flows were sent"}, 400)
            flows = [_FLOWS._as_flow(f) for f in given if isinstance(f, dict)]
            seen = set()
            for f in flows:
                if not f.id or f.id in seen:
                    f.id = _FLOWS.new_id(f.name, flows=[x for x in flows
                                                        if x.id in seen])
                seen.add(f.id)
                for step in f.steps:
                    if not step.id:
                        step.id = _FLOWS.step_id()
            from core import settings as _s
            saved = _s.load()
            refused = []
            for f in flows:
                for why in _FLOWS.refusals(f, saved):
                    refused.append(f"{f.name}: {why}")
            # "every step is switched off" is a thing to say, not a reason to
            # refuse a save - you switch them off one at a time while building.
            refused = [r for r in refused if "would do nothing" not in r]
            if refused:
                return self._json({"error": " ".join(refused),
                                   "refused": refused}, 400)
            _FLOWS.write(flows)
            from app.tasks import flows as _ft
            return self._json({"saved": True, "flows": _ft.described()})
        except Exception:                          # noqa: BLE001
            return self._json({"error": traceback.format_exc(limit=4)}, 500)

    def _cancel(self):
        job = self._job(self._body())
        if job is None:
            return self._json({"error": "no such run"}, 400)
        job.cancel = True
        return self._json(job.state())


def automation_loop(stop=None) -> None:
    """The background half of the Automation tab: every flow that runs itself.

    One thread for all of them, asleep almost all the time. Each flow keeps its
    own last-fired time, so a quarter-hourly developing loop and a weekly
    tidy-up do not have to share an interval.

    A flow fired by DSM's Task Scheduler is skipped here whatever its switch
    says. Two things firing the same flow is how you get two passes moving the
    same photographs past each other.

    It never raises. A background thread that dies takes the automation with it
    and says nothing, which is the exact failure this whole feature exists to
    avoid, so every pass is wrapped and the loop goes round again.
    """
    from core import flows as _f
    seen: dict = {}
    while not (stop and stop()):
        time.sleep(30)
        try:
            # Read every time round, so adding a flow, reordering its steps or
            # changing an interval takes effect on the next minute rather than
            # on the next restart. An app you have to restart to change a
            # schedule is an app whose schedule is whatever it was the day you
            # set it up.
            for flow in _f.read():
                if not flow.on or flow.fired_by != _f.BY_APP:
                    continue
                every = max(1, int(flow.every or 15)) * 60
                if time.time() - float(seen.get(flow.id) or 0) < every:
                    continue
                seen[flow.id] = time.time()
                from app.tasks.automation import one_pass
                one_pass(flow)
                LAST_PASS[0] = time.time()
        except Exception:                              # noqa: BLE001
            # Said out loud, but never fatal: the next pass may well work, and
            # the History tab is where a run that half-happened is recorded.
            traceback.print_exc(limit=3)


# Set when Setup is saved, so the index loop looks at once rather than on its
# next minute.
INDEX_NUDGE = threading.Event()


def index_loop(every: int = 60, glance: float = 2.0) -> None:
    """Keep the index in step with the disk, without anybody asking.

    Every run that writes marks it stale (`catalogue.touch`). This notices,
    waits for the run to finish, and reads only what actually changed - which
    for a pass that moved forty files is forty files and one walk.

    A loop rather than a refresh at the end of each run on purpose: a flow of six
    steps would otherwise rebuild the index six times while the sixth step was
    still moving things about.

    The library moving is different, and does not wait for the minute: the
    loop glances at the settings file every couple of seconds (a stat), and a
    save from Setup wakes it outright. Until it did, Photos went on showing
    the old library for up to a minute after Setup said the new one, and for
    as long as the old library's pass took after that.
    """
    from core import settings as _s
    stamp = _s.stamp()
    waited = 0.0
    look = False
    while True:
        if INDEX_NUDGE.wait(glance):
            INDEX_NUDGE.clear()
            look = True
        waited += glance
        now = _s.stamp()
        if now != stamp:
            stamp, look = now, True
        due = waited >= every
        if not (look or due):
            continue
        if due:
            waited = 0.0
        try:
            # Busy, or just told to stop: the look is still owed, and the
            # next glance takes it.
            if look_at_index(due) not in ("busy", "stopped"):
                look = False
        except Exception:                              # noqa: BLE001
            look = False


def follow_setup() -> None:
    """Setup has just been saved: let the index catch up at once."""
    from core import catalogue as _cat
    cat = _cat.shared()
    roots = _cat.wanted_roots()
    if roots and not cat.busy():
        cat.let_go(roots)
    INDEX_NUDGE.set()


# How long the index trusts a library nothing in this app has touched. A walk
# is a listing and a stat per file, so this is about not spinning a NAS disk
# every minute, not about the cost of reading photographs.
INDEX_REWALK = 300


def look_at_index(due: bool) -> str:
    """One look at the index: what, if anything, it should do now.

    `due` is the minute being up, when a stale index is worth re-reading,
    and one nobody has read for INDEX_REWALK seconds is walked again.
    Between minutes only the library moving is - a pass the moment Setup
    changes, not one for every file a run touches.

    Says what it did: "busy" (a pass is running, look again shortly),
    "stopped" (that pass was reading a library that is no longer the
    library), "cleared" (there is no library any more), "started", or "".
    """
    from core import catalogue as _cat
    cat = _cat.shared()
    roots = _cat.wanted_roots()
    if cat.busy():
        # A pass over the library that was: stop it, and the next glance starts
        # the new one, rather than finishing minutes of work nobody wants.
        if roots and _cat.trees_moved(cat.reading_roots(), roots):
            cat.stop()
            return "stopped"
        return "busy"
    if not roots:
        # No library at all - not a library that is missing this minute,
        # which keeps its index for when the share comes back.
        return "cleared" if _cat.nothing_set() and cat.clear() else ""
    moved = _cat.trees_moved(cat.roots, roots)
    # Photographs also arrive and leave without this app: a card copied over
    # SMB, a phone backup, a delete in File Station. Nothing marks the index
    # stale for those, so every INDEX_REWALK it walks the library anyway. A
    # walk over an unchanged library opens no files and writes nothing.
    overdue = time.time() - float(cat.when or 0) >= INDEX_REWALK
    if moved or cat.unread or (due and (cat.stale or not cat.files or overdue)):
        if cat.start(roots):
            # Warmed on a thread of its own so the loop is free to notice the
            # library moving again while this pass is still reading.
            threading.Thread(target=lambda: warm_newest(cat, cat.wait()),
                             daemon=True).start()
            return "started"
    return ""


WARM_NEWEST = 300


def warm_newest(cat, said: dict) -> bool:
    """After a pass that added photographs, make the newest ones' thumbnails.

    The newest because they are what Photos opens on, and what somebody who
    has just imported a card is about to look at. In the background, and a
    no-op without Pillow (`core/thumbs.warm`).
    """
    if not (said or {}).get("added"):
        return False
    from core import thumbs
    paths = [path for _key, path in cat.rows()[:WARM_NEWEST]]
    return thumbs.warm(paths) is not None


def serve(port: int = PORT) -> None:
    from core import store

    where = fence_said()
    ok, data = store.writable()
    print("Photo Manager")
    from core import desktop as _desktop
    if _desktop.as_program():
        # A PC program has no port mapping; the container wording would send
        # someone looking for an 8842 that does not exist.
        print(f"  listening  port {port} on this PC ({_desktop.address(port)})")
    else:
        print(f"  listening  port {port} INSIDE the container")
        print(f"             in a browser use the port you mapped it to")
        print(f"             (the left-hand number in ports: \"8842:{port}\")")
    print(f"  folders    {where}")
    print(f"  settings   {data}" if ok else f"  settings   CANNOT BE SAVED: {data}")
    if not ok:
        print("             Set PM_DATA to a folder the app can write to - in the")
        print("             container that is the /config volume. The page will")
        print("             still run, but nothing you set will survive a restart.")
    print(f"  tasks      {', '.join(t.name for t in R.all_tasks())}")
    from core import flows as _flows
    seed_automation_results()
    running = [f for f in _flows.read() if f.on and f.fired_by == _flows.BY_APP]
    print("  flows      " + (", ".join(f"{f.name} (every {f.every} min)"
                                       for f in running)
                             if running else "none running (Automation tab)"))
    threading.Thread(target=automation_loop, daemon=True).start()

    # The library, read in the background, starting now. Nothing waits for it:
    # the page opens, says how far along it is, and fills in as it goes. A photo
    # app that shows an empty screen for forty seconds and then everything at
    # once is one people assume is broken for the first thirty-nine.
    from core import catalogue as _cat
    roots = _cat.wanted_roots()
    if roots:
        _cat.shared().start(roots)
        print(f"  library    indexing {', '.join(roots)} in the background")
    else:
        print("  library    no library folder set yet (Setup)")
    threading.Thread(target=index_loop, daemon=True).start()

    # Answer "is there a Photo Manager here?" shouted on the local network, so a
    # phone finds this without anyone reading an address off a router page.
    # Never fatal: a network stack that will not have it, or a second copy
    # already listening, leaves the server itself untouched.
    from core import discovery, identity
    if discovery.wanted():
        from core import access as _access
        discovery.responder(
            lambda: identity.brief(public_port(), _access.is_on()))
        print(f"  on the network  answers as \"{identity.name()}\" on "
              f"port {public_port()} (Setup to change or turn off)")
    else:
        print("  on the network  not answering (turned off in Setup)")

    print("  stop with Ctrl+C")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    try:
        serve()
    except KeyboardInterrupt:
        print("\nstopped")
