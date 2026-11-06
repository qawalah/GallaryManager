"""Reading a coordinate out of a link somebody pasted.

The last resort for placing photos, and the most direct: you know where you were,
you find it on a map, you copy the address bar. No embedded map, no tiles, no
map provider to keep working - just text you already have.

The formats below are not a wish list; they are what the share buttons and
address bars of the common map sites actually produce. The one thing worth
knowing is that a Google `place/` link carries TWO positions: the `@` part is
where the map was centred when you copied it, and the `!3d…!4d…` buried in the
data blob is the place itself. They can be a street apart, so the place wins.

Everything read here is checked for being somewhere on Earth before it is
believed, and a link that yields nothing says so rather than returning a
plausible pair of numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .photo import sane_coordinate

SHORT_HOSTS = ("maps.app.goo.gl", "goo.gl/maps", "maps.google.com/maps?cid")


@dataclass
class Pin:
    ok: bool = False
    lat: float | None = None
    lon: float | None = None
    how: str = ""
    why: str = ""

    @property
    def map_link(self) -> str:
        return (f"https://www.google.com/maps?q={self.lat:.6f},{self.lon:.6f}"
                if self.ok else "")


def _pair(lat, lon, how) -> Pin | None:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not sane_coordinate(lat, lon):
        return None
    return Pin(True, lat, lon, how)


# Each rule is (what it means, the pattern). Order matters: the more specific
# reading of a link is tried before the more general one.
RULES = [
    ("the place the link points at",
     re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")),
    ("the point after ?q= or &query=",
     re.compile(r"[?&](?:q|query|daddr|saddr|destination)=(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")),
    ("the point after ?ll= or &center=",
     re.compile(r"[?&](?:ll|center|sll|cp)=(-?\d+\.\d+)[,~]\s*(-?\d+\.\d+)")),
    ("where the map was centred",
     re.compile(r"/@(-?\d+\.\d+),(-?\d+\.\d+)")),
    ("the OpenStreetMap position",
     re.compile(r"#map=\d+(?:\.\d+)?/(-?\d+\.\d+)/(-?\d+\.\d+)")),
    ("a geo: link",
     re.compile(r"^geo:(-?\d+\.\d+),(-?\d+\.\d+)", re.I)),
    ("two numbers, read as latitude and longitude",
     re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*[,;]\s*(-?\d+(?:\.\d+)?)\s*$")),
]


def looks_shortened(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(h in t for h in SHORT_HOSTS)


def read(text: str) -> Pin:
    """The coordinate in a pasted link, or a Pin saying why there is none."""
    text = (text or "").strip().strip("<>").strip()
    if not text:
        return Pin(why="Nothing was pasted.")

    for how, pattern in RULES:
        m = pattern.search(text)
        if m:
            pin = _pair(m.group(1), m.group(2), how)
            if pin:
                return pin

    if looks_shortened(text):
        return Pin(why=("That is a shortened link, which carries no coordinate at "
                        "all - it is only a lookup key. Open it in a browser, then "
                        "copy the address bar once the map has loaded."))
    return Pin(why=("No coordinate could be read from that. Open the place in Google "
                    "Maps, right-click it, click the numbers at the top of the menu "
                    "to copy them, and paste those instead."))


def describe(pin: Pin) -> str:
    """A human-readable position, for a preview line."""
    if not pin.ok:
        return pin.why
    ns = "N" if pin.lat >= 0 else "S"
    ew = "E" if pin.lon >= 0 else "W"
    return f"{abs(pin.lat):.6f}{ns}, {abs(pin.lon):.6f}{ew}  ({pin.how})"
