"""Counting the library along any axis you like - and two at once.

The Library tab says what state each FOLDER is in. This says what the
photographs themselves are: which years, which cameras, which apertures, how
many carry a location, how the stars are spread. Same question a contact sheet
answers by being looked at for an hour, answered in a table.

**One pass, many axes.** Every dimension here is worked out from one read of
each photograph, through the same cache everything else uses
(`core/facts.py`) - so asking for six charts costs the same as asking for one,
and the second visit costs nothing at all.

**Two axes at once is the point of it.** "Which apertures" is mildly
interesting; "which apertures on which lens", or "how the stars fall by year",
is the question that changes what you shoot next. A cross-tab is one pass as
well: each photograph drops into one cell.

**A photograph that cannot answer is counted as "not said", never as zero.**
A frame with no aperture in it is not f/0, and a camera that wrote no ISO is not
ISO 0. Each axis keeps that bucket separate and visible, because a chart that
quietly folds unknowns into the smallest real bucket is a chart that lies in the
direction of tidiness.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import bands
from . import facts
from .photo import is_picture, kind

CAP = 200_000
UNSAID = "not said"

# The numeric bands live in core/bands.py and are READ EVERY TIME, not bound to
# a name here at import: Setup can replace any of them, and a chart drawn after
# that has to use the new edges rather than whatever was true when the process
# started. `APERTURES` and friends are the built-in tables, kept as names
# because they read well in the code that explains a bucket.
APERTURES = bands.BUILTIN["aperture"]
ISOS = bands.BUILTIN["iso"]
SHUTTERS = bands.BUILTIN["shutter"]
FOCALS = bands.BUILTIN["focal"]
HOURS = bands.BUILTIN["hour"]
STARS = ["no stars", "1", "2", "3", "4", "5"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
        "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# name -> (what it is called on screen, how its buckets are ordered)
DIMS = {
    "year": ("Year", "name"),
    "month": ("Month", "given"),
    "weekday": ("Day of the week", "given"),
    "hour": ("Time of day", "given"),
    "camera": ("Camera", "count"),
    "lens": ("Lens", "count"),
    "focal": ("Focal length", "given"),
    "aperture": ("Aperture", "given"),
    "iso": ("ISO", "given"),
    "shutter": ("Shutter", "given"),
    "stars": ("Stars", "given"),
    "colour": ("Colour label", "count"),
    "tag": ("Tag", "count"),
    "kind": ("Kind of file", "count"),
    "located": ("Location", "given"),
    "folder": ("Top folder", "count"),
}

# Which axes come out in an order somebody chose rather than by size, and what
# that order is. A function, not a table: four of these follow the bands, and
# the bands can be changed while the app is running.
_FIXED = {"month": MONTHS, "weekday": DAYS, "stars": STARS,
          "located": ["has one", "none on it"]}


def given(dim: str) -> list:
    if dim in _FIXED:
        return list(_FIXED[dim])
    if dim in ("hour", "focal", "aperture", "iso", "shutter"):
        return [label for label, _ in bands.table(dim)]
    return []


def _band(value, which: str, mine: dict | None = None) -> str:
    """Which band of `which` a value falls in, by the edges in force now."""
    return bands.band(value, which, UNSAID, mine)


# WHAT THE SETTINGS SAY, WORKED OUT ONCE FOR A WHOLE TALLY.
#
# The bands you have set and the names you have given your cameras come out of
# the settings file, and both were being fetched per photograph per dimension -
# so counting eighty thousand photographs across eight dimensions opened one
# small JSON file three hundred and twenty thousand times. `bands.table` and
# `devices.name_of` have taken a `mine=` argument for exactly this since they
# were written; nothing here was passing it.
class Edges:
    """The band tables and the camera names, read once and carried."""

    __slots__ = ("bands", "cameras", "named")

    def __init__(self):
        from . import devices
        self.bands = bands.saved()
        self.cameras = devices.saved()
        self.named: dict = {}

    def camera(self, model: str) -> str:
        """The same label `devices.label` gives - the name with the code beside
        it when the two differ - worked out once per camera rather than once
        per photograph."""
        if model not in self.named:
            from . import devices
            self.named[model] = devices.label(model, self.cameras)
        return self.named[model]


_NO_EDGES = None


def edges() -> "Edges":
    """A fresh set for one answer. Never shared between requests - the point is
    that it is consistent within one tally, not that it outlives it."""
    return Edges()


def buckets_of(hit, dim: str, root: str = "", full_frame: bool = False,
               said: "Edges | None" = None):
    """Which bucket (or buckets) of this dimension one photograph falls in.

    A list, because tags are not one answer: a photo tagged "spain, street" is
    in both columns, and pretending it is in one would make the numbers add up
    while saying something false.

    `said` carries the band tables and the camera names, read once for the whole
    tally. Without one every call reads them again, which is correct and three
    hundred times slower.
    """
    if said is None:
        said = Edges()
    if dim == "year":
        return [hit.taken[:4] if hit.taken else UNSAID]
    if dim == "month":
        return [MONTHS[int(hit.taken[5:7]) - 1] if hit.taken else UNSAID]
    if dim in ("weekday", "hour"):
        if not hit.taken:
            return [UNSAID]
        import datetime as _dt
        when = _dt.datetime.strptime(hit.taken[:19], "%Y-%m-%d %H:%M:%S")
        if dim == "weekday":
            return [DAYS[when.weekday()]]
        return [_band(when.hour, "hour", said.bands)]
    if dim == "camera":
        if not hit.camera:
            return [UNSAID]
        return [said.camera(hit.camera)]
    if dim == "lens":
        return [hit.lens or UNSAID]
    if dim == "focal":
        mm = hit.focal35 if (full_frame and hit.focal35) else hit.focal
        return [_band(mm, "focal", said.bands)]
    if dim == "aperture":
        return [_band(hit.fnumber, "aperture", said.bands)]
    if dim == "iso":
        return [_band(hit.iso or None, "iso", said.bands)]
    if dim == "shutter":
        return [_band(getattr(hit, "seconds", None), "shutter", said.bands)]
    if dim == "stars":
        return [STARS[min(5, max(0, int(hit.stars or 0)))]]
    if dim == "colour":
        return [hit.colour or "no label"]
    if dim == "tag":
        return list(hit.tags) or ["no tags"]
    if dim == "kind":
        return [{"jpeg": "JPEG", "image": "Other photo format", "raw": "RAW",
                 "video": "Video"}.get(kind(hit.path), "Other")]
    if dim == "located":
        return ["has one" if hit.located else "none on it"]
    if dim == "folder":
        rel = os.path.relpath(hit.path, root) if root else hit.path
        first = rel.split(os.sep)[0]
        return [first if first not in (".", "..") else "the folder itself"]
    return [UNSAID]


def _range_for(table, label) -> tuple:
    """(from, to) for a banded bucket, back out of the band table.

    The bands are defined here once, so the search a band MEANS is worked out
    here too rather than by the page guessing what "f/5.6" covers. A chart that
    sends you to a search showing different photographs from the ones it drew
    would be worse than a chart you cannot click.
    """
    low = None
    for name, top in table:
        if name == label:
            return low, (None if top >= 1e8 else top)
        low = top
    return None, None


# Which bucket of each dimension means "the file does not say", and the name
# `find.Ask.missing` knows it by. Tags and colour labels say it in their own
# words; every other dimension says "not said".
_UNSAID_AS = {
    "year": (UNSAID, "taken"), "month": (UNSAID, "taken"),
    "weekday": (UNSAID, "taken"), "hour": (UNSAID, "taken"),
    "camera": (UNSAID, "camera"), "lens": (UNSAID, "lens"),
    "focal": (UNSAID, "focal"), "aperture": (UNSAID, "aperture"),
    "iso": (UNSAID, "iso"), "shutter": (UNSAID, "shutter"),
    "colour": ("no label", "colour"), "tag": ("no tags", "tags"),
}


def ask_for(dim: str, bucket: str) -> dict:
    """The search that means "this bucket" - or {} when none can say it.

    Every dimension a chart draws can be clicked through to the files behind
    it, except the values Search has no box for (a month, a weekday, a time of
    day) and a folded tail, which is many values and opens out instead. Those
    get nothing rather than a link that lands somewhere else: a chart that
    sends you to the wrong photographs is worse than one that does not move.

    "Not said" is a search too - the frames that do not record this at all,
    which are the ones a library most needs to find - and `find.UNSAID` names
    each of them the way `buckets_of` decides them.
    """
    if not bucket or bucket == "everything else":
        return {}
    unsaid = _UNSAID_AS.get(dim)
    if unsaid and bucket == unsaid[0]:
        return {"missing": unsaid[1]}
    if bucket == UNSAID:
        return {}
    if dim == "year":
        return {"since": f"{bucket}-01-01", "until": f"{bucket}-12-31"}
    if dim == "camera":
        # The chart says "Galaxy S21 (SM-G991B)"; the search has to ask for
        # something the files can answer, which is the code in the brackets.
        return {"camera": bucket[bucket.rfind("(") + 1:-1]
                if bucket.endswith(")") and "(" in bucket else bucket}
    if dim == "lens":
        return {"lens": bucket}
    if dim == "tag":
        return {"tags": bucket}
    if dim == "colour":
        return {"colour": bucket}
    if dim == "stars":
        n = 0 if bucket == "no stars" else int(bucket)
        return {"stars_from": n, "stars_to": n}
    if dim == "located":
        return {"located": "yes" if bucket == "has one" else "no"}
    if dim == "kind":
        return {"kinds": [{"JPEG": "jpeg", "RAW": "raw", "Video": "video"}.get(bucket, "")]} \
            if bucket in ("JPEG", "RAW", "Video") else {}
    if dim == "aperture":
        low, high = _range_for(bands.table("aperture"), bucket)
        out = {}
        if low is not None:
            out["f_from"] = low
        if high is not None:
            out["f_to"] = round(high - 0.01, 2)
        return out
    if dim == "focal":
        low, high = _range_for(bands.table("focal"), bucket)
        out = {}
        if low is not None:
            out["focal_from"] = low
        if high is not None:
            out["focal_to"] = round(high - 0.1, 1)
        return out
    if dim == "iso":
        low, high = _range_for(bands.table("iso"), bucket)
        out = {}
        if low is not None:
            out["iso_from"] = low + 1
        if high is not None:
            out["iso_to"] = high
        return out
    if dim == "shutter":
        low, high = _range_for(bands.table("shutter"), bucket)
        out = {}
        # a band of seconds: "faster than" is an upper bound on the exposure
        if high is not None:
            out["faster_than"] = round(high, 6)
        if low is not None:
            out["slower_than"] = round(low, 6)
        return out
    return {}


@dataclass
class Counted:
    """One axis: its buckets, how many photographs in each, and how big."""
    dim: str = ""
    label: str = ""
    rows: list = field(default_factory=list)      # [(bucket, photos, bytes)]
    photos: int = 0
    unsaid: int = 0

    def named(self) -> int:
        """How many different buckets there are, "not said" left out.

        What a tile like Cameras counts. It is the chart's own rows, so the
        number and the bars beside it cannot disagree, and a photo with no
        camera in it is not one more camera.
        """
        return sum(1 for r in self.rows if r[0] != UNSAID)

    def top(self, many: int = 8) -> list:
        """The biggest few, with the tail folded into one row.

        Never more colours - a ninth hue is indistinguishable from an existing
        one to a colour-blind reader, and the tail is not the point of the
        chart anyway.
        """
        if len(self.rows) <= many:
            return list(self.rows)
        head = self.rows[:many - 1]
        tail = self.rows[many - 1:]
        return head + [("everything else", sum(r[1] for r in tail),
                        sum(r[2] for r in tail))]

    def drawn(self, many: int = 8, cap: int = 60) -> dict:
        """Everything the page needs to draw this axis - folded or opened out.

        The page is handed EVERY bucket, not the folded eight: folding is a
        view, and "everything else" with no way to find out what is in it is
        the chart telling you there is something there and refusing to say
        what. So the tail travels too, the page shows `many` of them and opens
        on request, and each row carries the search that would list its files.
        """
        rows = self.rows[:cap]
        return {"rows": [[name, n, size, ask_for(self.dim, name)]
                         for name, n, size in rows],
                "show": many, "more": max(0, len(self.rows) - len(rows)),
                "dim": self.dim}


@dataclass
class Tally:
    counts: dict = field(default_factory=dict)    # dim -> Counted
    photos: int = 0
    bytes: int = 0
    looked: int = 0
    read: str = ""
    cross: dict = field(default_factory=dict)     # the two-axis answer
    capped: bool = False


def _order(dim: str, seen: dict) -> list:
    how = DIMS.get(dim, ("", "count"))[1]
    items = [(name, n, size) for name, (n, size) in seen.items()]
    if how == "given":
        rank = {name: i for i, name in enumerate(given(dim))}
        items.sort(key=lambda r: (rank.get(r[0], 998) if r[0] != UNSAID else 999,
                                  r[0]))
    elif how == "name":
        items.sort(key=lambda r: (r[0] == UNSAID, r[0]))
    else:
        items.sort(key=lambda r: (r[0] in (UNSAID, "no tags", "no label"), -r[1],
                                  r[0].lower()))
    return items


class Counting:
    """The counting half of a tally, apart from the reading half.

    Pulled out when the catalogue arrived. Counting a photograph and GETTING a
    photograph are different problems: the second one used to be "walk the
    library and open every file", and is now usually "it is already in the
    index". The bucketing rules must not be written twice over that - a
    dashboard built from the index that disagreed with the same dashboard built
    from a scan would be a bug nobody could see.
    """

    def __init__(self, dims, cross=(), full_frame: bool = False, root: str = ""):
        self.dims = [d for d in dims if d in DIMS]
        self.pair = tuple(d for d in (cross or ()) if d in DIMS)[:2]
        self.full_frame = full_frame
        self.root = root
        self.seen = {d: {} for d in set(self.dims) | set(self.pair)}
        self.grid: dict = {}
        self.out = Tally()
        # Read once, here, and carried into every bucketing decision below.
        self.said = Edges()

    def add(self, hit) -> None:
        self.out.looked += 1
        self.out.photos += 1
        self.out.bytes += getattr(hit, "size", 0) or 0
        for dim in self.seen:
            for bucket in buckets_of(hit, dim, self.root, self.full_frame, self.said):
                was = self.seen[dim].get(bucket, (0, 0))
                self.seen[dim][bucket] = (was[0] + 1,
                                          was[1] + (getattr(hit, "size", 0) or 0))
        if len(self.pair) == 2:
            for a in buckets_of(hit, self.pair[0], self.root, self.full_frame, self.said):
                for b in buckets_of(hit, self.pair[1], self.root, self.full_frame,
                                    self.said):
                    self.grid[(a, b)] = self.grid.get((a, b), 0) + 1

    def finish(self) -> Tally:
        for dim in self.dims:
            rows = _order(dim, self.seen[dim])
            self.out.counts[dim] = Counted(
                dim=dim, label=DIMS[dim][0], rows=rows,
                photos=sum(r[1] for r in rows),
                unsaid=sum(r[1] for r in rows if r[0] == UNSAID))
        if len(self.pair) == 2:
            down = [r[0] for r in _order(self.pair[0], self.seen[self.pair[0]])]
            across = [r[0] for r in _order(self.pair[1], self.seen[self.pair[1]])]
            self.out.cross = {
                "down": self.pair[0], "across": self.pair[1],
                "down_label": DIMS[self.pair[0]][0],
                "across_label": DIMS[self.pair[1]][0],
                "rows": down, "cols": across,
                "grid": [[self.grid.get((a, b), 0) for b in across] for a in down],
            }
        return self.out


def tally_of(hits, dims, cross=(), full_frame: bool = False, root: str = "",
             cancelled=None) -> Tally:
    """The same answer, counted from photographs somebody else already has.

    This is what makes the dashboard open with numbers on it: the catalogue
    hands over what it read in the background, and nothing here touches a disk.
    """
    counting = Counting(dims, cross, full_frame, root)
    for hit in hits:
        if cancelled and cancelled():
            break
        counting.add(hit)
    out = counting.finish()
    out.read = "from the index - nothing was opened"
    return out


def tally(folders, dims, progress=None, cancelled=None, full_frame: bool = False,
          cross=(), cap: int = CAP) -> Tally:
    """Count every photograph under these folders, along each dimension asked for.

    `cross` is a pair of dimension names - the two-axis answer, counted in the
    same pass because walking the library twice to compare two things about it
    would be twice the work for no more truth.
    """
    from . import find
    from . import walk as W
    reader = facts.reader()
    root = os.path.abspath(str((list(folders) or [""])[0] or ""))
    counting = Counting(dims, cross, full_frame, root)
    out = counting.out

    files, known = [], set()
    for folder in folders:
        folder = os.path.abspath(str(folder or "").strip())
        if not os.path.isdir(folder):
            continue
        for one in W.walk(folder).files:
            if one in known:
                continue
            known.add(one)
            if is_picture(one) or kind(one) in ("raw", "video"):
                files.append(one)
    files.sort()
    if len(files) > cap:
        files, out.capped = files[:cap], True

    for n, path in enumerate(files, 1):
        if cancelled and cancelled():
            break
        if progress and n % 50 == 0:
            progress(n, len(files), os.path.basename(path))
        try:
            hit = find.about(path, reader)
        except Exception:                              # noqa: BLE001
            continue
        counting.add(hit)

    counting.finish()
    out.read = reader.said()
    reader.save()
    return out


def values(folders, dim: str, cap: int = 300, progress=None) -> dict:
    """What is actually IN the library on one axis, biggest first.

    For the boxes on the Search tab. Typing a camera's name from memory is how
    you search for `DMC-GH5` in a library that only ever says `DMC-GH4` and
    conclude there is nothing there - so the box offers what the files really
    say, spelled the way they spell it.
    """
    if dim not in DIMS:
        raise ValueError(f"nothing called {dim!r}")
    got = tally(folders, [dim], progress=progress)
    counted = got.counts.get(dim)
    rows = [{"name": name, "photos": n}
            for name, n, _size in (counted.rows if counted else [])
            if name not in (UNSAID, "no tags", "no label")][:cap]
    return {"dim": dim, "label": DIMS[dim][0], "values": rows,
            "photos": got.photos, "read": got.read}


def trim(cross: dict, most: int = 12) -> dict:
    """A cross-tab small enough to read: the biggest rows and columns kept.

    Forty cameras against forty lenses is sixteen hundred cells, which is not a
    picture of anything. The tail is dropped rather than folded into an
    "everything else" row, because a cell is a pair and "everything else by
    everything else" is a number nobody can act on - and the count of what was
    left out is said instead.
    """
    if not cross:
        return {}
    grid = cross["grid"]
    rows, cols = cross["rows"], cross["cols"]
    down = sorted(range(len(rows)), key=lambda i: -sum(grid[i]))[:most]
    down.sort()
    across = sorted(range(len(cols)),
                    key=lambda j: -sum(grid[i][j] for i in range(len(rows))))[:most]
    across.sort()
    kept = {
        "down": cross["down"], "across": cross["across"],
        "down_label": cross["down_label"], "across_label": cross["across_label"],
        "rows": [rows[i] for i in down], "cols": [cols[j] for j in across],
        "grid": [[grid[i][j] for j in across] for i in down],
    }
    whole = sum(sum(r) for r in grid)
    shown = sum(sum(r) for r in kept["grid"])
    kept["left_out"] = whole - shown
    kept["most"] = max([c for r in kept["grid"] for c in r] or [0])
    # what each edge means as a search, so a cell can be both at once
    kept["row_asks"] = [ask_for(kept["down"], name) for name in kept["rows"]]
    kept["col_asks"] = [ask_for(kept["across"], name) for name in kept["cols"]]
    return kept
