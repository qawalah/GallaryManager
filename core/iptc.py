"""The IPTC block Photoshop, Bridge and most cataloguing software write.

It hides two layers down: an APP13 segment, holding Photoshop's 8BIM resources,
one of which (0x0404) holds the IPTC datasets. Each dataset is numbered by
record and field - 2:25 is a keyword, 2:90 is a city - and a file carries as
many of each as it likes.

Its own module because two very different questions come here: "what is this
photo tagged" and "where does this photo say it was taken". Parsing it twice, in
two places, is how the two answers start disagreeing.
"""

from __future__ import annotations

from . import jpegseg

PHOTOSHOP = b"Photoshop 3.0\x00"
IPTC_RESOURCE = 0x0404

# The datasets this app reads. Record 2 is the "application" record.
KEYWORDS = (2, 25)
CITY = (2, 90)
STATE = (2, 95)              # province or state
COUNTRY_CODE = (2, 100)      # ISO 3166 alpha-3, per the standard
COUNTRY = (2, 101)           # the country's name, as somebody typed it
SUBLOCATION = (2, 92)


def datasets(path: str) -> dict:
    """Every IPTC dataset in a file, as {(record, field): [values]}.

    Never raises and never decodes a picture - one header read, the same one the
    rest of the app already does.
    """
    out: dict = {}
    buf = jpegseg.read_header(path, jpegseg.HEADER_BYTES)
    for seg in jpegseg.segments(buf):
        if seg.marker != 0xED or not seg.data.startswith(PHOTOSHOP):
            continue
        _resources(seg.data[len(PHOTOSHOP):], out)
    return out


def values(path_or_found, which: tuple) -> list[str]:
    """One dataset's values, from a path or from an already-read dict."""
    found = path_or_found if isinstance(path_or_found, dict) else datasets(path_or_found)
    return list(found.get(which, []))


def first(found: dict, which: tuple) -> str:
    got = found.get(which) or []
    return got[0] if got else ""


def _resources(block: bytes, out: dict) -> None:
    """Walk 8BIM resources, reading the datasets in the IPTC one."""
    i = 0
    n = len(block)
    while i + 12 <= n:
        if block[i:i + 4] != b"8BIM":
            break
        kind = int.from_bytes(block[i + 4:i + 6], "big")
        # A Pascal name: one length byte, the characters, then a pad byte if that
        # came to an odd number. Measured as the FIELD's own length rather than
        # as a parity of where it happens to sit - the two agree only for as long
        # as every resource before it was even, which is a property of the file
        # and not of this loop.
        name_len = block[i + 6]
        name_field = 1 + name_len
        after = i + 6 + name_field + (name_field % 2)
        if after + 4 > n:
            break
        size = int.from_bytes(block[after:after + 4], "big")
        start = after + 4
        end = start + size
        if end > n:
            break
        if kind == IPTC_RESOURCE:
            _datasets(block[start:end], out)
        i = end + (size % 2)                # resources are padded to even too


def _datasets(data: bytes, out: dict) -> None:
    i = 0
    n = len(data)
    while i + 5 <= n:
        if data[i] != 0x1C:
            break
        key = (data[i + 1], data[i + 2])
        size = int.from_bytes(data[i + 3:i + 5], "big")
        start = i + 5
        if size & 0x8000:                   # an extended length - rare, and not ours
            break
        end = start + size
        if end > n:
            break
        text = data[start:end].decode("utf-8", "replace").strip("\x00").strip()
        if text:
            out.setdefault(key, []).append(text)
        i = end
