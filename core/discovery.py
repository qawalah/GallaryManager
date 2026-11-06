"""Finding a server without typing its address.

Typing `http://192.168.0.24:8842` into a phone is the first thing anyone does
with this app and the first thing that goes wrong: the NAS gets a new lease, the
PC is on a different subnet, someone reads a 4 as a 1. And the address is not
even stable for one machine - the same server is one thing on the LAN and
another over Tailscale.

So: a client shouts on the local network and every server that hears it answers
with its name, its id and its port. The client learns the address from where the
answer came back, which is the one thing nobody has to type.

**Why not mDNS/Bonjour.** It is the right answer and it is not stdlib. Bringing
in `zeroconf` would break the rule this whole app is built on - Python's own
library plus Pillow, nothing else, because anything else is a thing that has to
be installed on a NAS. A broadcast and a reply is forty lines and works the same
on Windows and on a Synology.

**What this is not.** It is not a way in. The answer says a server exists and
what it is called; every real call still goes through the password in Setup, and
the answer says whether one is set so a client can ask for it up front rather
than after a 401. Turn it off in Setup if you would rather nothing answered.

**What it cannot do.** Broadcasts do not cross subnets or VPNs - over Tailscale
or from outside the house, the address still has to be typed or kept. That is
the nature of a broadcast, not a limit of this file.
"""

from __future__ import annotations

import json
import socket
import threading

PORT = 8845                 # the shout, not the web page
ASK = b"photo-manager?"
MAX = 1400                  # one datagram, never fragmented


def wanted() -> bool:
    """Whether to answer at all.

    Reads either shape on purpose. The setting is a tick on Setup and arrives as
    a real boolean; it has also been written by hand as "yes"/"no" in the
    settings file, and a server that silently ignored that would be a setting
    that appears not to work.
    """
    from . import settings as S
    try:
        said = S.load()["discovery"]
    except Exception:                                      # noqa: BLE001
        return True
    if isinstance(said, str):
        return said.strip().lower() not in ("no", "off", "false", "0", "")
    return bool(said)


def _reply_for(ask: bytes, me: dict) -> bytes | None:
    """The answer to one datagram, or None when it is not for us.

    Anything that is not exactly our question is ignored in silence. A port that
    answers strangers is a port that turns up in someone's scan report.
    """
    if ask.strip()[:len(ASK)] != ASK:
        return None
    out = json.dumps(me, separators=(",", ":")).encode("utf-8")
    return out if len(out) <= MAX else None


def responder(me_now, stop=None) -> threading.Thread:
    """Answer the shout, for as long as the server runs.

    `me_now` is called for every datagram rather than once: the name can be
    changed on Setup while this is running, and a server that kept answering
    with its old name until the next restart is a small lie that is hard to
    spot.
    """
    def loop():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", PORT))
            # Short, so `stop` is noticed promptly. A responder that lingered
            # for a second after being told to go is a responder that answers
            # for the copy that replaced it.
            sock.settimeout(0.25)
        except OSError:
            # Another copy already listening, or a network stack that will not
            # have it. Discovery is a convenience; the server itself is fine.
            return
        while not (stop and stop.is_set()):
            try:
                ask, where = sock.recvfrom(256)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                out = _reply_for(ask, me_now())
                if out:
                    sock.sendto(out, where)
            except Exception:                              # noqa: BLE001
                continue                       # never take the server down
        try:
            sock.close()
        except OSError:
            pass

    thread = threading.Thread(target=loop, name="discovery", daemon=True)
    thread.start()
    return thread


def find(seconds: float = 1.5, port: int = PORT) -> list:
    """Shout, and collect what answers. This is what a client does.

    Kept here rather than only in the clients so there is one definition of the
    exchange, and so it can be tested against the real responder rather than
    against a description of it.
    """
    found, seen = [], set()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.3)
    try:
        for to in ("255.255.255.255", "127.0.0.1"):
            try:
                sock.sendto(ASK, (to, port))
            except OSError:
                continue
        end = __import__("time").monotonic() + seconds
        while __import__("time").monotonic() < end:
            try:
                data, where = sock.recvfrom(MAX + 64)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                said = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if said.get("app") != "photo-manager" or not said.get("id"):
                continue
            if said["id"] in seen:
                continue
            seen.add(said["id"])
            said["address"] = where[0]
            said["url"] = f"http://{where[0]}:{said.get('port') or 80}"
            found.append(said)
    finally:
        sock.close()
    return found
