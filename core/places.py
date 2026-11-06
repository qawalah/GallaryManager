"""Turning a photograph's coordinates into a country and a town.

Two sources, in this order:

1. **What the photograph already says.** Lightroom, Bridge and most cataloguing
   software write a city and a country into the file (IPTC 2:90/2:101, or XMP's
   `photoshop:City`). Somebody typed that, or a program looked it up properly -
   either way it beats anything worked out here, and it costs one header read.

2. **The nearest town to its coordinates**, from a table imported once. No
   network, no lookups, nothing leaves the NAS.

**The whole design problem is the second one being a GUESS.** The nearest town in
a table of towns over fifteen thousand people is not where the photograph was
taken; it is the nearest name we happen to know. In a city that is the right
answer and the distance is a kilometre. On a mountain, at sea, or in the desert
it is forty kilometres away and possibly across a border - and a folder called
`Italy/Rome` for a photograph taken in San Marino is a lie that never announces
itself.

So distance is carried on every answer and two limits are enforced:

    CITY_WITHIN_KM      beyond this, the town is not claimed - only the country
    COUNTRY_WITHIN_KM   beyond this, nothing is claimed at all

Both are options on the task, both are reported in the plan, and the distance is
written into every row. A guess you can see is a guess you can overrule.
"""

from __future__ import annotations

import bisect
import math
import os
import re
import zipfile

from . import countries, iptc, jpegseg
from . import sidecar as sc
from .photo import read_gps, sane_coordinate

STORE_HEADER = "#photo-manager place index v2"
# v1 held no population, so it cannot answer "only towns over 50,000". A v1 store
# still LOADS - re-importing is a download, and refusing to work until somebody
# does it would be rude - but it says it cannot do that one thing, rather than
# filtering against a column of zeros and reporting that nowhere qualifies.
OLD_HEADERS = ("#photo-manager place index v1",)

CITY_WITHIN_KM = 30
COUNTRY_WITHIN_KM = 200

# GeoNames' dump has 19 tab-separated columns. Only these four are wanted.
_NAME, _LAT, _LON, _CC, _POP = 1, 4, 5, 8, 14
_ADMIN1 = 10            # the region's code within its country - "56" is Catalonia


class Place:
    """Where one photograph was, as far as anything here can honestly say."""

    __slots__ = ("country", "city", "code", "how", "km", "lat", "lon", "region")

    def __init__(self, country="", city="", code="", how="", km=None,
                 lat=None, lon=None, region=""):
        self.region = region
        self.country = country
        self.city = city
        self.code = code
        self.how = how              # what answered: "the file", "nearest town"
        self.km = km                # None when it did not come from coordinates
        self.lat, self.lon = lat, lon

    def __bool__(self) -> bool:
        return bool(self.country or self.city)

    def describe(self) -> str:
        where = " / ".join(x for x in (self.country, self.city) if x)
        if not where:
            # Nothing was claimed. The reason IS the answer here, so it is not
            # dressed up as one - "nowhere - nearest town is Doha, 12,000 km
            # away, 12000 km away" is what saying it twice looks like.
            return self.how or "no location"
        if self.km is None:
            return f"{where} - {self.how}" if self.how else where
        return f"{where} - {self.how}, {self.km:.0f} km away"

    def __repr__(self) -> str:                     # pragma: no cover
        return f"Place({self.describe()!r})"


# --------------------------------------------------------- what the file says

_XMP_CITY = re.compile(r"photoshop:City\s*=\s*\"([^\"]*)\"|<photoshop:City>([^<]*)<",
                       re.I)
_XMP_COUNTRY = re.compile(
    r"photoshop:Country\s*=\s*\"([^\"]*)\"|<photoshop:Country>([^<]*)<", re.I)
_XMP_STATE = re.compile(
    r"photoshop:State\s*=\s*\"([^\"]*)\"|<photoshop:State>([^<]*)<", re.I)
_XMP_CC = re.compile(
    r"Iptc4xmpCore:CountryCode\s*=\s*\"([^\"]*)\"|<Iptc4xmpCore:CountryCode>([^<]*)<",
    re.I)


def _first_group(pattern, text: str) -> str:
    m = pattern.search(text or "")
    if not m:
        return ""
    return (m.group(1) or m.group(2) or "").strip()


def from_xmp(text: str) -> Place:
    """City and country out of a piece of XMP."""
    city = _first_group(_XMP_CITY, text)
    country = _first_group(_XMP_COUNTRY, text)
    code = countries.code_of(_first_group(_XMP_CC, text)) or countries.code_of(country)
    if code and not country:
        country = countries.name_of(code)
    if not city and not country:
        return Place()
    return Place(country=country, city=city, code=code, how="written in the file",
                 region=_first_group(_XMP_STATE, text))


def written_place(path: str) -> Place:
    """What the photograph itself says about where it was taken.

    The sidecar is read first for the same reason a rating is: it is the file a
    person edited most recently, and for a RAW it is the only place this can be
    written at all.
    """
    side = sc.beside(path)
    if side:
        try:
            with open(side, "r", encoding="utf-8", errors="replace") as fh:
                found = from_xmp(fh.read())
            if found:
                found.how = "written in the sidecar"
                return found
        except OSError:
            pass
    try:
        found = from_xmp(jpegseg.xmp_packet(path))
        if found:
            return found
    except Exception:                              # noqa: BLE001
        pass
    try:
        fields = iptc.datasets(path)
    except Exception:                              # noqa: BLE001
        return Place()
    city = iptc.first(fields, iptc.CITY)
    country = iptc.first(fields, iptc.COUNTRY)
    code = countries.code_of(iptc.first(fields, iptc.COUNTRY_CODE)) \
        or countries.code_of(country)
    if code and not country:
        country = countries.name_of(code)
    if not city and not country:
        return Place()
    return Place(country=country, city=city, code=code, how="written in the file")


# ------------------------------------------------------------------ the table

def _rows_from_dump(source: str):
    """Yield (name, lat, lon, country code, population) from a GeoNames dump.

    Takes the .zip exactly as downloaded or the .txt inside it, because asking
    somebody to unzip a file first is a step to get wrong at 11pm.
    """
    if source.lower().endswith(".zip"):
        with zipfile.ZipFile(source) as zf:
            inner = [n for n in zf.namelist() if n.lower().endswith(".txt")
                     and "readme" not in n.lower()]
            if not inner:
                raise ValueError("that zip holds no cities .txt file")
            with zf.open(inner[0]) as fh:
                yield from _parse_lines(line.decode("utf-8", "replace")
                                        for line in fh)
        return
    with open(source, "r", encoding="utf-8", errors="replace") as fh:
        yield from _parse_lines(fh)


def _parse_lines(lines):
    for line in lines:
        bits = line.rstrip("\n").split("\t")
        if len(bits) <= _POP:
            continue
        try:
            lat, lon = float(bits[_LAT]), float(bits[_LON])
        except ValueError:
            continue
        if not sane_coordinate(lat, lon):
            continue
        name = bits[_NAME].strip()
        code = bits[_CC].strip().upper()
        if not name or len(code) != 2:
            continue
        try:
            pop = int(bits[_POP] or 0)
        except ValueError:
            pop = 0
        admin1 = bits[_ADMIN1].strip() if len(bits) > _ADMIN1 else ""
        yield name, lat, lon, code, pop, admin1


def read_country_names(path: str) -> dict:
    """GeoNames' countryInfo.txt, when somebody downloaded that too.

    Optional. The built-in table already names every country; this exists so a
    name that is wrong or out of date is a file you can drop in rather than a bug
    you have to wait for.
    """
    out: dict = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("#"):
                    continue
                bits = line.rstrip("\n").split("\t")
                if len(bits) > 4 and len(bits[0]) == 2 and bits[4].strip():
                    out[bits[0].strip().upper()] = bits[4].strip()
    except OSError:
        return {}
    return out


def read_region_names(path: str) -> dict:
    """GeoNames' admin1CodesASCII.txt: `ES.56<tab>Catalonia...`. Optional.

    Without it a region is simply unknown, and {region} drops out of a folder
    name rather than turning into a code nobody can read.
    """
    out: dict = {}
    if not path:
        return out
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                bits = line.rstrip("\n").split("\t")
                if len(bits) > 1 and "." in bits[0] and bits[1].strip():
                    out[bits[0].strip().upper()] = bits[1].strip()
    except OSError:
        return {}
    return out


def import_dump(source: str, store: str, progress=None, names_file: str = "",
                regions_file: str = "") -> dict:
    """Read a GeoNames dump once into the app's own compact store.

    Sorted by latitude on the way out, because that is what makes the lookup a
    bisect over a narrow band rather than a walk through every town on earth.
    """
    rows = []
    for i, row in enumerate(_rows_from_dump(source), 1):
        rows.append(row)
        if progress and i % 5000 == 0:
            progress(i, 0, f"{i:,} towns")
    if not rows:
        raise ValueError("no towns could be read out of that file - is it the "
                         "cities file from geonames.org?")
    rows.sort(key=lambda r: r[1])
    extra = read_country_names(names_file) if names_file else {}
    regions = read_region_names(regions_file)

    os.makedirs(os.path.dirname(store) or ".", exist_ok=True)
    tmp = store + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{STORE_HEADER}\n")
        fh.write(f"#source\t{os.path.basename(source)}\n")
        for code, name in sorted(extra.items()):
            fh.write(f"#country\t{code}\t{name}\n")
        for code, name in sorted(regions.items()):
            fh.write(f"#region\t{code}\t{name}\n")
        for row in rows:
            name, lat, lon, code, pop = row[:5]
            admin1 = row[5] if len(row) > 5 else ""
            fh.write(f"{name}\t{lat:.4f}\t{lon:.4f}\t{code}\t{pop}\t{admin1}\n")
    os.replace(tmp, store)
    return {"towns": len(rows),
            "countries": len({r[3] for r in rows}),
            "named": len(extra), "regions": len(regions)}


class Table:
    """Every town, indexed by latitude so a lookup reads a band and not a world."""

    def __init__(self):
        self.lats: list = []
        self.rows: list = []
        self.names: dict = {}          # country code -> name, when overridden
        self.regions: dict = {}        # "ES.56" -> "Catalonia", when imported
        self.source = ""
        self.has_population = False

    def __len__(self) -> int:
        return len(self.rows)

    def country_name(self, code: str) -> str:
        return countries.name_of(code, self.names)

    def region_name(self, row) -> str:
        if not row or len(row) < 6 or not row[5]:
            return ""
        return self.regions.get(f"{row[3]}.{row[5]}".upper(), "")

    def nearest(self, lat: float, lon: float, at_least: int = 0):
        """(row, kilometres) for the closest town, or (None, None) if empty.

        `at_least` is a population floor: "stick to the towns anybody has heard
        of". A village three kilometres away is the honest nearest name and often
        not the name you would give the folder - a week in Tuscany becomes eleven
        hamlets rather than one Florence.

        Searched as a widening band of latitude. One degree of latitude is 111 km
        everywhere, so a band of N degrees cannot hide anything closer than
        111*N km - which is what makes stopping early safe rather than lucky.
        """
        if not self.rows:
            return None, None
        best = None
        best_km = None
        span = 0.5
        while span <= 90:
            lo = bisect.bisect_left(self.lats, lat - span)
            hi = bisect.bisect_right(self.lats, lat + span)
            for i in range(lo, hi):
                row = self.rows[i]
                if at_least and (len(row) < 5 or row[4] < at_least):
                    continue
                km = distance_km(lat, lon, row[1], row[2])
                if best_km is None or km < best_km:
                    best, best_km = row, km
            # Anything outside the band is at least this far away in latitude
            # alone, so a hit inside it that is closer than the band cannot be
            # beaten. Without this the answer near a pole or a date line would
            # depend on where the band happened to fall.
            if best_km is not None and best_km <= span * 110.0:
                return best, best_km
            span *= 2
        return best, best_km


def load(store: str) -> Table:
    """The store, or an empty table when there is not one yet. Never raises."""
    t = Table()
    try:
        with open(store, "r", encoding="utf-8", errors="replace") as fh:
            first = fh.readline().strip()
            if first not in (STORE_HEADER,) + OLD_HEADERS:
                return t
            t.has_population = (first == STORE_HEADER)
            for line in fh:
                if line.startswith("#"):
                    bits = line.rstrip("\n").split("\t")
                    if bits[0] == "#country" and len(bits) > 2:
                        t.names[bits[1].strip().upper()] = bits[2].strip()
                    elif bits[0] == "#region" and len(bits) > 2:
                        t.regions[bits[1].strip().upper()] = bits[2].strip()
                    elif bits[0] == "#source" and len(bits) > 1:
                        t.source = bits[1].strip()
                    continue
                bits = line.rstrip("\n").split("\t")
                if len(bits) < 4:
                    continue
                try:
                    t.rows.append((bits[0], float(bits[1]), float(bits[2]),
                                   bits[3].strip().upper(),
                                   int(bits[4]) if len(bits) > 4 and bits[4].strip()
                                   else 0,
                                   bits[5].strip() if len(bits) > 5 else ""))
                except ValueError:
                    continue
    except OSError:
        return t
    t.rows.sort(key=lambda r: r[1])
    t.lats = [r[1] for r in t.rows]
    return t


def store_info(store: str) -> dict:
    """What is on file, for a form that has to say whether it is ready."""
    t = load(store)
    return {"towns": len(t), "countries": len({r[3] for r in t.rows}),
            "source": t.source, "ok": bool(len(t)),
            "population": t.has_population}


# ------------------------------------------------------------------ the answer

def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def from_coordinates(table: Table, lat: float, lon: float,
                     city_within_km: float = CITY_WITHIN_KM,
                     country_within_km: float = COUNTRY_WITHIN_KM,
                     at_least: int = 0) -> Place:
    """The nearest town, and how much of that answer is worth keeping.

    Two searches when a population floor is asked for, because the two halves of
    the answer have different evidence behind them. WHICH COUNTRY this is comes
    from the closest town of any size - a village three kilometres away is far
    better evidence of the country than a city three hundred kilometres away.
    WHAT TO CALL THE FOLDER comes from the closest town big enough to be worth
    naming, and only if that one is close too.
    """
    if not sane_coordinate(lat, lon) or not len(table):
        return Place()
    near, near_km = table.nearest(lat, lon)
    if near is None:
        return Place()
    if near_km > country_within_km:
        # Far out at sea, or deep in a desert. The nearest name we know is not
        # evidence of anything, and a country folder built on it would be wrong
        # without ever looking wrong.
        return Place(how=f"nearest town is {near[0]}, {near_km:.0f} km away - too "
                         f"far to say anything", km=near_km, lat=lat, lon=lon)

    code = near[3]
    country = table.country_name(code)
    row, km = (table.nearest(lat, lon, at_least) if at_least else (near, near_km))
    if row is None or km > city_within_km:
        if at_least and (row is None or km > city_within_km):
            # The floor was asked for and nothing that big is near. Falling back
            # to the village would ignore the setting silently; the country is
            # still known, and the row says which village it was measured from.
            return Place(country=country, code=code, km=near_km, lat=lat, lon=lon,
                         region=table.region_name(near),
                         how=(f"no town over {at_least:,} people is within "
                              f"{city_within_km:.0f} km - the nearest is {near[0]}"))
        return Place(country=country, code=code, how=f"nearest town is {near[0]}",
                     km=near_km, lat=lat, lon=lon, region=table.region_name(near))
    return Place(country=country, city=row[0], code=code,
                 region=table.region_name(row) or table.region_name(near),
                 how="nearest town" if not at_least else
                     (f"nearest town over {at_least:,} people"
                      if row[0] != near[0] else "nearest town"),
                 km=km, lat=lat, lon=lon)


def rename(place: Place, changes: dict) -> Place:
    """Apply the names you would rather use: Marrakesh -> Marrakech, once.

    Matched case-insensitively on the town OR the country, because "which of the
    two did I mean" is not a question worth making somebody answer - no country
    in the table shares a name with a town in it except where they genuinely are
    the same place (San Marino, Singapore), and there both answers agree.
    """
    if not changes or not place:
        return place
    for field in ("city", "country"):
        was = getattr(place, field, "")
        if was and was.strip().lower() in changes:
            setattr(place, field, changes[was.strip().lower()])
    return place


def read_renames(text: str) -> dict:
    """"Marrakesh = Marrakech" per line, or comma separated. Never raises."""
    out: dict = {}
    for line in re.split(r"[\n;]+", str(text or "")):
        if "=" not in line:
            continue
        was, _, now = line.partition("=")
        was, now = was.strip(), now.strip()
        if was and now:
            out[was.lower()] = now
    return out


def coordinates_of(path: str, loc=None):
    """(lat, lon) for a photograph, from the file or from its sidecar."""
    loc = loc if loc is not None else read_gps(path)
    if loc.has_gps and sane_coordinate(loc.lat, loc.lon):
        return loc.lat, loc.lon
    got = sc.read(path)
    lat = _dms(got.get("exif:GPSLatitude"))
    lon = _dms(got.get("exif:GPSLongitude"))
    if lat is None or lon is None or not sane_coordinate(lat, lon):
        return None
    return lat, lon


def _dms(text) -> float | None:
    """XMP writes a coordinate as "25,17.12300N" - degrees, minutes, hemisphere."""
    if not text:
        return None
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*([NSEW])?\s*$",
                 str(text))
    if not m:
        try:
            return float(str(text).strip())
        except ValueError:
            return None
    value = abs(float(m.group(1))) + float(m.group(2)) / 60.0
    if (m.group(3) or "").upper() in ("S", "W") or float(m.group(1)) < 0:
        value = -value
    return value


def tidy_name(text: str) -> str:
    """A folder name that will survive Windows, SMB and a person reading it."""
    text = (text or "").strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text
