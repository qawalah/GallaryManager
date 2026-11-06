"""Finding photographs by what they ARE, not by where they were filed.

Every other feature in this app starts from a folder. This one starts from a
question: *the wide shots from the GH4 with no location on them*, *everything
under f/2 last summer*, *the four-star frames from Spain*. The library is a
tree, and a tree can only be asked one question - "what is in this folder" -
so the answer to anything else has been "open thirty folders and look".

**Every criterion is optional and they all narrow together.** Nothing here is
an "or": you add conditions until the answer is small, which is how a person
actually searches. An empty search matches every photograph, which is the
honest answer to asking nothing.

**Read from the same cache as everything else** (`core/facts.py`). The first
search over a tree that has never been looked at reads every file; the second
is nearly free, and so is the Library tab afterwards, because they share the
answers. A file that changed since is re-read on its own.

**A criterion that a file cannot answer excludes it, and says so.** A photo
with no capture time is not "before 2020" and not "after 2020" either - it is
unanswerable, and quietly treating unanswerable as "no" is how a search that
looks complete hides the thirty frames you were actually looking for. The
count of those is reported beside the matches.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from dataclasses import dataclass, field

from . import facts, settings as S
from .photo import is_picture, kind

# How many matches are KEPT, with their facts, for the page to list. Every
# match is still counted past this, so "Found" is the true number whatever the
# cap: the chart on Home that sent you here said 6,000, and a search that
# answered "5,000" because it stopped counting looked wrong when it was only
# tired. Twenty thousand hits is a few megabytes; it is the listing on the
# page, not this, that has to be paced.
CAP = 20_000
SAVED = "saved_searches"


class Refused(Exception):
    """Said to the person as it is."""


# ------------------------------------------------------------------ the asking


@dataclass
class Ask:
    """What is being looked for. Every field empty means "everything"."""
    # when
    since: str = ""                 # YYYY-MM-DD, on or after
    until: str = ""                 # YYYY-MM-DD, on or before
    # what it was taken on
    camera: str = ""                # part of the model name, any case
    lens: str = ""
    # how it was exposed
    focal_from: float | None = None
    focal_to: float | None = None
    focal35: bool = False           # measure focal length as full-frame
    f_from: float | None = None
    f_to: float | None = None
    iso_from: int | None = None
    iso_to: int | None = None
    # shutter, in seconds - "longer than 1/60" is slower_than = 1/60
    faster_than: float | None = None
    slower_than: float | None = None
    # marks
    stars_from: int | None = None
    stars_to: int | None = None
    colour: str = ""
    tags: tuple = ()
    all_tags: bool = False          # every tag rather than any of them
    # where
    located: str = ""               # "yes", "no" or ""
    country: str = ""
    city: str = ""
    # Within a circle, for "show me the photographs from THIS pin". A place on a
    # map is a position and a distance, not a name - the name may not exist (no
    # place table imported) and two different towns can share one. Degrees, and
    # a radius in kilometres.
    near_lat: float | None = None
    near_lon: float | None = None
    within_km: float | None = None
    # the file itself
    name: str = ""                  # part of the file name
    kinds: tuple = ()               # "jpeg", "raw", "video" - empty is photos
    # What the file must NOT say: names from `UNSAID` below. This is the
    # "not said" row of a chart as a search - the frames with no capture time,
    # no aperture, no camera - which no range or name box can ask for, because
    # every one of them treats "not said" as "cannot answer" and leaves it out.
    missing: tuple = ()

    def asked(self) -> list:
        """What was actually filled in, for the plan to say back."""
        out = []
        if self.since or self.until:
            out.append(f"taken {self.since or 'any time'} to {self.until or 'now'}")
        if self.camera:
            out.append(f"camera like {self.camera!r}")
        if self.lens:
            out.append(f"lens like {self.lens!r}")
        if self.focal_from is not None or self.focal_to is not None:
            out.append(f"{self.focal_from or 0:g}-{self.focal_to or 9999:g}mm"
                       + (" (full-frame)" if self.focal35 else ""))
        if self.f_from is not None or self.f_to is not None:
            out.append(f"f/{self.f_from or 0:g}-f/{self.f_to or 99:g}")
        if self.iso_from is not None or self.iso_to is not None:
            out.append(f"ISO {self.iso_from or 0}-{self.iso_to or 999999}")
        if self.faster_than is not None:
            out.append(f"faster than {_shutter(self.faster_than)}")
        if self.slower_than is not None:
            out.append(f"longer than {_shutter(self.slower_than)}")
        if self.stars_from is not None or self.stars_to is not None:
            out.append(f"{self.stars_from or 0}-{self.stars_to or 5} stars")
        if self.colour:
            out.append(f"{self.colour} label")
        if self.tags:
            out.append(("all of " if self.all_tags else "any of ")
                       + ", ".join(self.tags))
        if self.located == "yes":
            out.append("has a location")
        if self.located == "no":
            out.append("no location")
        if self.country:
            out.append(f"in {self.country}")
        if self.city:
            out.append(f"near {self.city}")
        if self.near_lat is not None and self.near_lon is not None:
            out.append(f"within {self.within_km or 5:g}km of "
                       f"{self.near_lat:.4f}, {self.near_lon:.4f}")
        if self.name:
            out.append(f"named like {self.name!r}")
        if self.kinds:
            out.append("/".join(self.kinds))
        for name in self.missing:
            out.append(UNSAID.get(name, name))
        return out

    def needs_place(self) -> bool:
        return bool(self.country or self.city)


# What a file can leave unsaid, and how a search says it back. The names are
# the ones a person types into the box, so they are the plain words, not field
# names. "taken" covers the year, month, day and hour charts alike: all four are
# read from the one capture time.
UNSAID = {
    "taken": "no capture time",
    "camera": "no camera",
    "lens": "no lens",
    "focal": "no focal length",
    "aperture": "no aperture",
    "iso": "no ISO",
    "shutter": "no shutter speed",
    "colour": "no colour label",
    "tags": "no tags",
}


def _unsaid(hit, name: str, focal35: bool = False) -> bool:
    """Does this photograph leave `name` unsaid?

    The same rule `core/stats.py` uses to put a photograph in a chart's "not
    said" row, so the row and the search behind it count the same frames: a
    number that cannot be read is not said, and so is an ISO of 0, which no
    camera shoots at.
    """
    if name == "taken":
        return not hit.taken
    if name == "camera":
        return not hit.camera
    if name == "lens":
        return not hit.lens
    if name == "focal":
        # Full-frame falls back to the number on the lens, as the chart does.
        mm = (hit.focal35 or hit.focal) if focal35 else hit.focal
        return _number_or_none(mm) is None
    if name == "aperture":
        return _number_or_none(hit.fnumber) is None
    if name == "iso":
        return not hit.iso
    if name == "shutter":
        return _number_or_none(getattr(hit, "seconds", None)) is None
    if name == "colour":
        return not hit.colour
    if name == "tags":
        return not hit.tags
    return False


def _number_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _shutter(seconds) -> str:
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return ""
    return f"{seconds:g}s" if seconds >= 1 else f"1/{round(1 / seconds):g}"


def _day(text: str):
    text = str(text or "").strip()
    if not text:
        return None
    for shape in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%Y-%m", "%Y"):
        try:
            return _dt.datetime.strptime(text, shape).date()
        except ValueError:
            continue
    raise Refused(f"{text!r} is not a date - write it as 2022-07-14")


def _between(value, low, high) -> bool:
    if value is None:
        return False
    if low is not None and value < low:
        return False
    if high is not None and value > high:
        return False
    return True


# ------------------------------------------------------------------ one photo


@dataclass
class Hit:
    """One photograph that matched, and the facts worth showing beside it."""
    path: str
    name: str = ""
    folder: str = ""
    taken: str = ""
    camera: str = ""
    lens: str = ""
    focal: float | None = None
    focal35: float | None = None
    fnumber: float | None = None
    shutter: str = ""
    iso: int = 0
    stars: int = 0
    colour: str = ""
    tags: list = field(default_factory=list)
    located: bool = False
    place: str = ""
    size: int = 0
    when: float = 0.0


def video_taken(path: str, reader, stat=None) -> str:
    """A clip's capture time as the index writes it, "" when there is none."""
    def read(one):
        from . import video
        shot = video.taken_of(one)
        when = video.local_time(shot)
        return when.strftime("%Y-%m-%d %H:%M:%S") if when else ""
    return str(reader._field(path, "vtaken", read, stat=stat) or "")


def about(path: str, reader, table=None, wanted_place: bool = False) -> Hit:
    """Everything a search can be asked about one photograph."""
    hit = Hit(path=path, name=os.path.basename(path),
              folder=os.path.dirname(path))
    try:
        st = os.stat(path)
        hit.size, hit.when = st.st_size, st.st_mtime
    except OSError:
        pass
    cap = reader.capture(path)
    if cap.taken is not None:
        hit.taken = cap.taken.strftime("%Y-%m-%d %H:%M:%S")
    elif kind(path) == "video":
        # A clip has no EXIF, so the photograph reader finds no time in it and
        # every clip in the index used to count as undated. Its own reader, and
        # cached like everything else so the next pass does not open it again.
        hit.taken = video_taken(path, reader)
    hit.camera = str(cap.model or "").strip()
    hit.lens = str(cap.lens or "").strip()
    hit.focal = cap.focal_length
    hit.focal35 = cap.focal35
    hit.fnumber = cap.fnumber
    hit.shutter = _shutter(cap.exposure)
    hit.seconds = cap.exposure
    hit.iso = int(cap.iso or 0)
    hit.stars = reader.stars(path)
    hit.colour = reader.colour(path)
    hit.tags = list(reader.tags(path))
    where = reader.location(path)
    hit.located = bool(where and where[0] is not None)
    if wanted_place and hit.located and table is not None:
        from . import places
        found = places.from_coordinates(table, where[0], where[1])
        hit.place = ", ".join(x for x in (found.city, found.country) if x)
    return hit


# --------------------------------------------- ruling a row out without a Hit
#
# `matches` below is the one definition of a match, and it stays that. But it
# takes a `Hit`, and a `Hit` has to be BUILT from the index row it is about to
# be compared against - eighty thousand objects, allocated and thrown away, to
# answer "which of these has five stars". Measured: 330 ms through `matches`
# against 47 ms doing the same test on the rows, and forty megabytes of objects
# that live only long enough to be asked one question.
#
# So the row is given a chance to say NO first. This function may only ever
# answer "this one cannot possibly match" - never "it does". Anything it does
# not rule out is built into a `Hit` and put through `matches` exactly as
# before, so the rule about what matches is still written down once.
#
# It lives here, next to `matches`, on purpose: these two must agree, and two
# functions in two files that must agree will stop agreeing. There is a test
# that runs both over a grid of asks and fails if they ever differ.
#
# Only the fields that are a plain lookup are tested. A camera name goes through
# `devices.matches` and a date that is missing is a shrug rather than a no, so
# both are left to `matches`.
def cannot_match(e, path: str, ask: Ask) -> bool:
    """True when this index row cannot match, whatever else is read about it.

    `e` is a catalogue row: taken, kind, camera, lens, focal, focal35, fnumber,
    shutter, iso, stars, colour, tags, lat, lon, size, when, sig.
    """
    if ask.kinds and kind(path) not in ask.kinds:
        return True
    if ask.name and ask.name.lower() not in os.path.basename(path).lower():
        return True
    taken = e[0]
    # A row with NO capture time is not ruled out here: `matches` calls that a
    # shrug rather than a no, and which of the two it is belongs to `matches`.
    if taken:
        day = taken[:10]
        if ask.since and day < ask.since:
            return True
        if ask.until and day > ask.until:
            return True
    if ask.stars_from is not None and (e[9] or 0) < ask.stars_from:
        return True
    if ask.stars_to is not None and (e[9] or 0) > ask.stars_to:
        return True
    if ask.colour and (e[10] or "") != ask.colour:
        return True
    if ask.located == "yes" and e[12] is None:
        return True
    if ask.located == "no" and e[12] is not None:
        return True
    if ask.tags:
        have = {str(t).lower() for t in (e[11] or ())}
        want = {str(t).lower() for t in ask.tags}
        if ask.all_tags:
            if not want <= have:
                return True
        elif not (want & have):
            return True
    return False


def matches(hit: Hit, ask: Ask) -> tuple:
    """(does it match, what it could not answer).

    The second half is the point: "no capture time" is not a no, it is a
    shrug, and a search that silently counts shrugs as noes hides exactly the
    files you would want to know about.
    """
    if ask.kinds:
        if kind(hit.path) not in ask.kinds:
            return False, ""
    if ask.name and ask.name.lower() not in hit.name.lower():
        return False, ""

    if ask.since or ask.until:
        if not hit.taken:
            return False, "no capture time"
        day = hit.taken[:10]
        if ask.since and day < ask.since:
            return False, ""
        if ask.until and day > ask.until:
            return False, ""

    if ask.camera:
        if not hit.camera:
            return False, "does not say which camera"
        # by the code the file carries, or by what you call that camera - a
        # rename that made the library harder to search would be a bad trade
        from . import devices
        if not devices.matches(hit.camera, ask.camera):
            return False, ""
    if ask.lens:
        if not hit.lens:
            return False, "does not say which lens"
        if ask.lens.lower() not in hit.lens.lower():
            return False, ""

    if ask.focal_from is not None or ask.focal_to is not None:
        mm = hit.focal35 if ask.focal35 else hit.focal
        if mm is None and ask.focal35:
            # No equivalent recorded: the number on the barrel is not the same
            # question, so this file cannot answer it rather than answering
            # wrongly by a factor of two.
            return False, "no full-frame equivalent in the file"
        if mm is None:
            return False, "no focal length"
        if not _between(float(mm), ask.focal_from, ask.focal_to):
            return False, ""

    if ask.f_from is not None or ask.f_to is not None:
        if hit.fnumber is None:
            return False, "no aperture"
        if not _between(float(hit.fnumber), ask.f_from, ask.f_to):
            return False, ""

    if ask.iso_from is not None or ask.iso_to is not None:
        if not hit.iso:
            return False, "no ISO"
        if not _between(int(hit.iso), ask.iso_from, ask.iso_to):
            return False, ""

    if ask.faster_than is not None or ask.slower_than is not None:
        seconds = getattr(hit, "seconds", None)
        if seconds is None:
            return False, "no shutter speed"
        if ask.faster_than is not None and float(seconds) > float(ask.faster_than):
            return False, ""
        if ask.slower_than is not None and float(seconds) < float(ask.slower_than):
            return False, ""

    if ask.stars_from is not None or ask.stars_to is not None:
        if not _between(int(hit.stars), ask.stars_from, ask.stars_to):
            return False, ""
    if ask.colour and hit.colour != ask.colour:
        return False, ""
    if ask.tags:
        have = {t.lower() for t in hit.tags}
        want = {t.lower() for t in ask.tags}
        if ask.all_tags and not want <= have:
            return False, ""
        if not ask.all_tags and not (want & have):
            return False, ""

    if ask.located == "yes" and not hit.located:
        return False, ""
    if ask.located == "no" and hit.located:
        return False, ""
    if ask.country or ask.city:
        if not hit.located:
            return False, "no location to look up"
        if not hit.place:
            return False, "its coordinates are not in the place table"
        low = hit.place.lower()
        if ask.country and ask.country.lower() not in low:
            return False, ""
        if ask.city and ask.city.lower() not in low:
            return False, ""
    for name in ask.missing:
        if not _unsaid(hit, name, ask.focal35):
            return False, ""
    if ask.near_lat is not None and ask.near_lon is not None:
        where = getattr(hit, "lat", None), getattr(hit, "lon", None)
        if where[0] is None:
            return False, "no location"
        from .places import distance_km
        if distance_km(float(where[0]), float(where[1]),
                       float(ask.near_lat), float(ask.near_lon)) > float(
                           ask.within_km or 5.0):
            return False, ""
    return True, ""


# ------------------------------------------------------------------ the search


@dataclass
class Found:
    hits: list = field(default_factory=list)
    looked: int = 0
    matched: int = 0                # every match, including the ones past cap
    unanswerable: dict = field(default_factory=dict)
    capped: bool = False
    read: str = ""


def search(folders, ask: Ask, progress=None, cancelled=None, cap: int = CAP,
           table=None) -> Found:
    """Every photograph under these folders that matches. Nothing is written."""
    from . import walk as W
    out = Found()
    reader = facts.reader()
    seen = set()
    files = []
    for folder in folders:
        folder = os.path.abspath(str(folder or "").strip())
        if not os.path.isdir(folder):
            raise Refused(f"There is no folder at {folder}")
        for one in W.walk(folder).files:
            if one in seen:
                continue
            seen.add(one)
            if is_picture(one) or kind(one) in ("raw", "video"):
                files.append(one)
    files.sort()
    wanted_place = ask.needs_place()
    for n, path in enumerate(files, 1):
        if cancelled and cancelled():
            break
        if progress and n % 25 == 0:
            progress(n, len(files), os.path.basename(path))
        out.looked += 1
        try:
            hit = about(path, reader, table, wanted_place)
        except Exception:                              # noqa: BLE001
            out.unanswerable["could not be read"] = \
                out.unanswerable.get("could not be read", 0) + 1
            continue
        ok, why = matches(hit, ask)
        if ok:
            out.matched += 1
            if len(out.hits) >= cap:
                out.capped = True
                continue
            out.hits.append(hit)
        elif why:
            out.unanswerable[why] = out.unanswerable.get(why, 0) + 1
    out.read = reader.said()
    reader.save()
    return out


# ------------------------------------------------------------- keeping a search


def _clean(ask: Ask) -> dict:
    out = {}
    for key, value in ask.__dict__.items():
        if value in ("", None, (), [], False):
            continue
        out[key] = list(value) if isinstance(value, tuple) else value
    return out


def saved() -> list:
    """[(name, the search)] kept in Setup's settings, in the order kept."""
    try:
        got = json.loads(S.load()[SAVED] or "[]")
        return [(str(n), dict(a)) for n, a in got
                if str(n).strip() and isinstance(a, dict)]
    except (ValueError, TypeError):
        return []


def keep(name: str, ask: Ask) -> list:
    """Save (or replace) one by name."""
    name = str(name or "").strip()
    if not name:
        raise Refused("give the search a name")
    if len(name) > 60:
        raise Refused("that name is too long")
    have = [(n, a) for n, a in saved() if n.lower() != name.lower()]
    have.append((name, _clean(ask)))
    S.save({SAVED: json.dumps([[n, a] for n, a in have])})
    return have


def forget(name: str) -> list:
    have = [(n, a) for n, a in saved() if n.lower() != str(name or "").lower()]
    S.save({SAVED: json.dumps([[n, a] for n, a in have])})
    return have


def of_saved(name: str) -> Ask:
    """The search kept under this name, as an Ask."""
    for kept, data in saved():
        if kept.lower() == str(name or "").strip().lower():
            return from_dict(data)
    raise Refused(f"there is no saved search called {name!r}")


NUMS = {"focal_from", "focal_to", "f_from", "f_to", "faster_than", "slower_than",
        "near_lat", "near_lon", "within_km"}


def _number(value, key: str) -> float:
    """A number, or a shutter speed written the way a camera writes one.

    Typing 0.004 for a quarter of a 250th is arithmetic nobody should have to do
    to ask a question, so 1/250 is accepted where a number is wanted.
    """
    text = str(value).strip().replace(",", ".")
    try:
        if "/" in text:
            top, _, bottom = text.partition("/")
            return float(top or 1) / float(bottom)
        return float(text)
    except (TypeError, ValueError, ZeroDivisionError):
        raise Refused(f"{key.replace('_', ' ')}: {value!r} is not a number - "
                      f"write 250, 2.8, or 1/250 for a shutter speed")
INTS = {"iso_from", "iso_to", "stars_from", "stars_to"}


def from_dict(data: dict) -> Ask:
    """An Ask from whatever a form or a saved search hands over.

    Every value arrives as text from a browser, so the shapes are settled in one
    place rather than in each caller - and a box left empty means "do not ask
    about this", never zero.
    """
    ask = Ask()
    for key, value in (data or {}).items():
        if not hasattr(ask, key):
            continue
        if isinstance(value, str):
            value = value.strip()
        if value in ("", None):
            continue
        if key in NUMS:
            setattr(ask, key, _number(value, key))
        elif key in INTS:
            try:
                setattr(ask, key, int(float(value)))
            except (TypeError, ValueError):
                raise Refused(f"{key.replace('_', ' ')}: {value!r} is not a number")
        elif key in ("focal35", "all_tags"):
            setattr(ask, key, bool(value) and value not in ("0", "no", "off"))
        elif key == "missing":
            if isinstance(value, str):
                value = [t.strip().lower() for t in re.split(r"[,\n]", value)
                         if t.strip()]
            value = tuple(dict.fromkeys(str(t).strip().lower() for t in value
                                        if str(t).strip()))
            wrong = [t for t in value if t not in UNSAID]
            if wrong:
                raise Refused(f"not said: {wrong[0]!r} is not something a "
                              f"photo says - use "
                              f"{', '.join(UNSAID)}")
            ask.missing = value
        elif key in ("tags", "kinds"):
            if isinstance(value, str):
                value = [t.strip() for t in re.split(r"[,\n]", value) if t.strip()]
            setattr(ask, key, tuple(value))
        else:
            setattr(ask, key, str(value))
    for name in ("since", "until"):
        day = _day(getattr(ask, name))
        setattr(ask, name, day.isoformat() if day else "")
    return ask
