"""A password on the front door, and the smallest one that is honestly a lock.

Until now the only way to put a password on this app was `PM_PASSWORD` in the
compose file, which meant editing the compose file and rebuilding the container
to change it - so in practice it was never set, and anything that could reach
the port could not only LOOK at the library but move, cull and re-mirror it. The
destructive half was always the bigger exposure.

**What this is.** One password for the app, set from inside the app, stored as a
PBKDF2 hash with a random salt - never the password itself, so the file this
writes cannot be turned back into what you typed. A browser that gets it right
is given a signed ticket in a cookie; that ticket carries its own expiry and is
verified with a secret that never leaves the NAS. Nothing is remembered per
session, so there is no session list to grow, leak or clean up, and a restart
does not throw you out.

**What this is not.** It is not accounts. There is no user list, no roles, no
password reset by email, and no pretence that any of that exists. One household,
one library, one password. Someone who wants per-person libraries wants a
different program.

**Two things worth knowing before trusting it.**

Sign out everywhere is a real button and it works by rotating the signing
secret, which invalidates every ticket ever issued - including the one in the
browser you are holding. That is the only revocation there is, and it is enough
because there is only one password: if you think someone has it, you change it,
and changing it rotates the secret too.

And it travels over plain HTTP on your own network, because that is what a NAS
app on a LAN is. Anyone able to watch traffic between your tablet and the NAS
can read the password as you type it. That is a statement about the network, not
about this file, and a login page that implied otherwise would be worse than
none.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from .store import store_path

FILE = "access.json"
ROUNDS = 240_000                # ~0.2s on a NAS: slow for guessing, invisible once
DAYS = 30                       # how long a ticket lasts before you sign in again

# Read once and kept, because every request checks a ticket and every request
# re-reading a file from a spinning disk is a page that feels slow for no
# reason. Every write goes through here, so the copy cannot go stale.
_HELD: dict = {}


def _path() -> str:
    try:
        return store_path(FILE)
    except Exception:                                  # noqa: BLE001
        return ""


def _read() -> dict:
    if _HELD:
        return _HELD
    where = _path()
    got = {}
    if where and os.path.exists(where):
        try:
            with open(where, "r", encoding="utf-8") as fh:
                got = json.load(fh) or {}
        except Exception:                              # noqa: BLE001
            got = {}
    _HELD.clear()
    _HELD.update(got)
    return _HELD


def _write(what: dict) -> bool:
    where = _path()
    if not where:
        return False
    try:
        tmp = where + ".new"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(what, fh, indent=1)
        os.replace(tmp, where)
        # Nobody but the owner. A world-readable file holding the signing secret
        # would make the hash beside it beside the point.
        try:
            os.chmod(where, 0o600)
        except OSError:
            pass
        _HELD.clear()
        _HELD.update(what)
        return True
    except OSError:
        return False


def forget() -> None:
    """Only for tests: drop the copy held in memory."""
    _HELD.clear()


# ------------------------------------------------------------ is there a lock

def is_on() -> bool:
    """Is a password set? The environment counts, and wins."""
    if os.environ.get("PM_PASSWORD"):
        return True
    return bool(_read().get("hash"))


def from_environment() -> bool:
    """Set in the compose file, where this app cannot change it."""
    return bool(os.environ.get("PM_PASSWORD"))


# ------------------------------------------------------------- the password

def _hash(word: str, salt: bytes, rounds: int) -> str:
    return base64.b64encode(hashlib.pbkdf2_hmac(
        "sha256", word.encode("utf-8"), salt, rounds)).decode("ascii")


def set_password(word: str) -> bool:
    """Set or change it. An empty word takes the lock off entirely.

    Changing the password rotates the signing secret as well, so every browser
    anywhere has to sign in again. That is the whole point of changing it.
    """
    word = str(word or "")
    if not word:
        return _write({})
    salt = secrets.token_bytes(16)
    return _write({
        "hash": _hash(word, salt, ROUNDS),
        "salt": base64.b64encode(salt).decode("ascii"),
        "rounds": ROUNDS,
        "secret": secrets.token_hex(32),
        "set": time.time(),
    })


def correct(word: str) -> bool:
    """Is this the password? Constant time, and the environment is checked too.

    `PM_PASSWORD` wins where it is set, so a compose file that puts a password
    on the app cannot be talked out of it by anything written through the page.
    """
    said = str(word or "")
    env = os.environ.get("PM_PASSWORD", "")
    if env:
        # As bytes: compare_digest refuses a str holding anything but ASCII, so
        # an Arabic PM_PASSWORD was a 500 on every try and could never let
        # anybody in.
        return hmac.compare_digest(said.encode("utf-8", "surrogateescape"),
                                   env.encode("utf-8", "surrogateescape"))
    held = _read()
    if not held.get("hash"):
        return False
    try:
        salt = base64.b64decode(held.get("salt") or "")
        rounds = int(held.get("rounds") or ROUNDS)
    except Exception:                                  # noqa: BLE001
        return False
    return hmac.compare_digest(_hash(said, salt, rounds), held["hash"])


# ------------------------------------------------------------- the ticket

def _secret() -> bytes:
    """What tickets are signed with. Made on demand, kept until it is rotated.

    With the password in the environment there is nothing on disk to sign with,
    so one is made and stored beside nothing else - the environment still
    decides whether the password is right, and this only decides whether a
    ticket this app issued is genuine.
    """
    held = _read()
    if not held.get("secret"):
        fresh = dict(held)
        fresh["secret"] = secrets.token_hex(32)
        _write(fresh)
    return _read().get("secret", "").encode("ascii")


def sign_out_everywhere() -> bool:
    """Rotate the secret: every ticket ever issued stops being genuine."""
    held = dict(_read())
    if not held:
        return False
    held["secret"] = secrets.token_hex(32)
    return _write(held)


def ticket(days: int = DAYS) -> str:
    """A signed note saying "this browser got the password right, until then".

    Stateless on purpose. The alternative - a set of live sessions in memory -
    means a restart signs everybody out, and a list that has to be pruned,
    bounded and thought about. This is two numbers and a signature.
    """
    # Not clamped. A caller asking for a ticket that has already expired is
    # asking for one nothing will accept, which is a reasonable thing to want -
    # a test that cannot make an expired ticket cannot check that expiry is
    # enforced, and that check is the whole reason the expiry is in there.
    until = int(time.time() + int(days) * 86400)
    body = f"1.{until}"
    sig = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def ticket_ok(given: str) -> bool:
    """Is this ticket genuine and still in date?"""
    try:
        version, until, sig = str(given or "").split(".", 2)
        if version != "1":
            return False
        if int(until) < time.time():
            return False
        body = f"{version}.{until}"
        want = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, want)
    except Exception:                                  # noqa: BLE001
        return False


# ------------------------------------------------- slowing a guessing machine

# Failures per address, and when they happened. Not a ban list: a delay that
# grows, because a home NAS has one person on it and the thing worth stopping is
# a script trying ten thousand words a minute, not a person mistyping twice.
_MISSES: dict = {}
LOCK_AFTER = 8
LOCK_FOR = 300                 # five minutes, then it lets you try again


def locked_for(who: str) -> int:
    """Seconds this address still has to wait, or 0."""
    misses, when = _MISSES.get(who, (0, 0.0))
    if misses < LOCK_AFTER:
        return 0
    left = int(when + LOCK_FOR - time.time())
    if left <= 0:
        _MISSES.pop(who, None)
        return 0
    return left


def missed(who: str) -> None:
    misses, _when = _MISSES.get(who, (0, 0.0))
    _MISSES[who] = (misses + 1, time.time())


def got_in(who: str) -> None:
    _MISSES.pop(who, None)


def forget_misses() -> None:
    _MISSES.clear()
