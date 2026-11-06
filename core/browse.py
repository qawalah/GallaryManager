"""The questions a photo library is actually opened with.

"Show me March", "where have I been", "what is in here", "which of these have no
location" - every one of them a view of the same index (`core/catalogue.py`) and
none of them a scan. The point is that they are instant: a library you have to
wait for is a library you stop opening.

Three rules this file keeps:

**One set of rules about what matches.** The filters above the grid are a
`find.Ask`, matched by `find.matches` - the same object the Search tab builds
and the same function it is judged by. Two sets of matching rules, one for
browsing and one for searching, would disagree within a month and the one that
was wrong would be the one nobody had written a test for.

**Nothing is invented.** An album here is a question with an obvious answer -
five stars, has no location, is a video - never a guess about what matters. The
places are the coordinates in the files, grouped; the names come from the place
table if one has been imported and are left as coordinates if not.

**Counting is not reading.** Everything here works off entries already in the
index. A view that quietly opened a hundred thousand files to draw a map would
be the old thirty-second Library tab wearing a different coat.
"""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict

# How close two photographs must be to be one pin on the map, in degrees, at
# each zoom. Rounded rather than clustered properly on purpose: a real
# clustering pass over a hundred thousand points is work, and the answer -
# "there are 1,284 photographs around here" - is the same.
GRIDS = {1: 4.0, 2: 2.0, 3: 1.0, 4: 0.5, 5: 0.2, 6: 0.08, 7: 0.03,
         8: 0.012, 9: 0.005, 10: 0.002}

MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


def _month_label(key: str) -> str:
    try:
        year, month = key.split("-")
        return f"{MONTHS[int(month) - 1]} {year}"
    except (ValueError, IndexError):
        return key or "No date"


def hidden_folders() -> list:
    """Folders left out of the grid, longest first. A view, not a decision.

    Setup's exclusion list means "nothing goes in here" - no walk, no feature,
    no index. This means "do not show me these while I am looking for a
    holiday": the scans beside the shoots are real photographs that should
    still be geotagged, backed up and counted. One list would have made the
    cheaper wish cost the expensive thing.
    """
    import json
    from . import settings as S
    try:
        got = json.loads(str(S.load()["hide_in_grid"] or "[]"))
    except (ValueError, TypeError):
        return []
    out = []
    for one in got if isinstance(got, list) else []:
        text = str(one or "").strip().rstrip("/\\")
        if text and text not in out:
            out.append(text)
    return sorted(out, key=len, reverse=True)


def is_hidden(path: str, folders=None) -> bool:
    """Whether this photograph is inside one of them."""
    folders = hidden_folders() if folders is None else folders
    if not folders:
        return False
    low = os.path.normcase(os.path.dirname(os.path.abspath(path)))
    for one in folders:
        base = os.path.normcase(os.path.abspath(one))
        if low == base or low.startswith(base + os.sep):
            return True
    return False


def matching(cat, ask=None, kinds_default: bool = True, show_all: bool = False) -> list:
    """(sort key, path) for everything that matches, newest first.

    Negatives are left out unless they are asked for by name. A RAW is not a
    photograph you browse - it is the other half of one that is already in the
    grid, and a timeline showing both shows everything twice.
    """
    from . import find
    rows = cat.rows()
    hide = [] if show_all else hidden_folders()
    if ask is None:
        out = []
        for key, path in rows:
            e = cat.entry(path)
            if e is None:
                continue
            if kinds_default and e[1] == "raw":
                continue
            if hide and is_hidden(path, hide):
                continue
            out.append((key, path))
        return out
    want_raw = "raw" in (ask.kinds or ())
    # A search by town or country needs each photograph's coordinates turned
    # into a name. `cat.hit` cannot do it - the index holds numbers - so it is
    # done here, once per coordinate, and ONLY when the question was asked.
    namer = place_namer() if (ask.country or ask.city) else None
    out = []
    for key, path in rows:
        e = cat.entry(path)
        if e is None:
            continue
        if e[1] == "raw" and not want_raw:
            continue
        if hide and is_hidden(path, hide):
            continue
        # The row answers first, and it is only ever allowed to say no - see
        # `find.cannot_match`. On a typical filter most photographs are ruled
        # out here, and those never become an object at all.
        if find.cannot_match(e, path, ask):
            continue
        hit = cat.hit(path)
        if hit is None:
            continue
        if namer is not None and hit.located:
            hit.place = namer(hit.lat, hit.lon)
        ok, _unknown = find.matches(hit, ask)
        if ok:
            out.append((key, path))
    return out


# ------------------------------------------------- coordinates, as a place name
#
# A photograph carries numbers; a person searches for "Spain" or "Granada". The
# bridge between them is the imported place table, and crossing it costs a
# lookup in a table of millions - so it is crossed once per COORDINATE rather
# than once per photograph. A shoot is a few hundred frames standing in the same
# square hundred metres, which is one lookup, not four hundred.
#
# Without an imported table there is no bridge at all. That is a thing to SAY -
# "no place table has been imported" - and the one thing it must never be is a
# search that quietly matches nothing, which is what it was.

_PLACES: dict = {}


def place_table():
    """The imported table, or None. Cached for the life of the process."""
    from .store import store_path
    where = store_path("places.tsv")
    try:
        stamp = os.path.getmtime(where)
    except OSError:
        _PLACES.clear()
        return None
    if _PLACES.get("stamp") != stamp:
        from . import places as P
        _PLACES.clear()
        try:
            got = P.load(where)
        except Exception:                                  # noqa: BLE001
            got = None
        _PLACES["stamp"] = stamp
        _PLACES["table"] = got if (got and len(got)) else None
        _PLACES["seen"] = {}
    return _PLACES.get("table")


def place_namer():
    """(lat, lon) -> "Town, Country", memoised. None when there is no table."""
    table = place_table()
    if table is None:
        return None
    from . import places as P
    seen = _PLACES.setdefault("seen", {})

    def name(lat, lon) -> str:
        if lat is None or lon is None:
            return ""
        key = (round(float(lat), 3), round(float(lon), 3))
        if key not in seen:
            try:
                found = P.from_coordinates(table, key[0], key[1])
                seen[key] = ", ".join(x for x in (found.city, found.country) if x)
            except Exception:                              # noqa: BLE001
                seen[key] = ""
        return seen[key]

    return name


# ----------------------------------------------- answers kept until they change
#
# Home, Albums and the criteria menus are the same answer every time until
# something moves. They were worked out again on every visit, and visited every
# time you came back to the screen - so a library that had not changed in a week
# was counted from scratch a hundred times a day.
#
# What makes an answer stale is small and knowable: the index changed, or a
# setting did. Both say so - the index counts its passes and the settings file
# has a date - so the key is those two numbers and nothing else. No timer, no
# guessing, and no "it will be right in a minute".
_KEPT: dict = {}


def _stamp_of(path: str):
    try:
        st = os.stat(path)
        return (st.st_size, st.st_mtime_ns, st.st_ino)
    except OSError:
        return None


def generation(cat) -> tuple:
    """What the answers depend on, as a key. Changes exactly when they do.

    The folders left out of the grid are named in it as well as the settings
    file they live in: leaving a folder out has to change every answer at once,
    and a key that only noticed it through the file's date would be one coarse
    clock away from serving the grid with the folder still in it. The place
    table is here because a search by town is answered through it.
    """
    from . import settings as S
    from .store import store_path
    said = _stamp_of(store_path(S.FILE))
    places = _stamp_of(store_path("places.tsv"))
    hidden = tuple(hidden_folders())
    with cat._lock:                                        # noqa: SLF001
        return (id(cat), cat.when, cat.changes, len(cat.files),
                tuple(cat.roots), said, hidden, places)


def kept(cat, name: str, make):
    """`make()`, worked out once per generation of the index and the settings."""
    key = generation(cat)
    box = _KEPT.get(name)
    if box is not None and box[0] == key:
        return box[1]
    out = make()
    _KEPT[name] = (key, out)
    return out


def forget_kept() -> None:
    """Drop every kept answer. For tests, and for Refresh."""
    _KEPT.clear()
    with _ROWS_LOCK:
        _ROWS.clear()


# The matched rows of the last few filters, the same way. Scrolling the grid
# asks for page after page of ONE answer, and each page used to run the whole
# filter over the whole library again to cut 240 rows out of it - so the
# fortieth page of a search cost forty searches. A handful of filters is kept,
# newest last, because the grid, the folder view and an album open side by
# side are three filters and the fourth is usually the one before.
_ROWS: OrderedDict = OrderedDict()
_ROWS_LOCK = threading.Lock()
ROWS_KEPT = 16


def _kept_rows(cat, key, make):
    full = (key, generation(cat))
    with _ROWS_LOCK:
        got = _ROWS.get(full)
        if got is not None:
            _ROWS.move_to_end(full)
            return got
    got = make()
    with _ROWS_LOCK:
        _ROWS[full] = got
        _ROWS.move_to_end(full)
        while len(_ROWS) > ROWS_KEPT:
            _ROWS.popitem(last=False)
    return got


def matched(cat, ask=None) -> list:
    """`matching(cat, ask)`, worked out once per filter and generation.

    Shared, so nothing may change it: every caller sorts into a list of its own
    or reads it as it stands.
    """
    return _kept_rows(cat, ("rows", repr(ask)), lambda: matching(cat, ask))


def _grouped(cat, ask, by: str) -> tuple:
    """(rows in drawing order, {group: count}, [groups in order]) - kept."""
    def make():
        rows = matched(cat, ask)
        if by == "folder":
            rows = sorted(rows, key=lambda kp: (
                os.path.normcase(os.path.dirname(kp[1])), _flip(kp[0])))
        groups: dict = {}
        order: list = []
        for key, path in rows:
            name = os.path.dirname(path) if by == "folder" else key[:7]
            if name not in groups:
                groups[name] = 0
                order.append(name)
            groups[name] += 1
        return rows, groups, order
    return _kept_rows(cat, ("grouped", repr(ask), by), make)


def card(cat, path: str) -> dict:
    """One photograph as the grid draws it: small, and nothing it will not use."""
    e = cat.entry(path)
    if e is None:
        return {"path": path, "name": os.path.basename(path)}
    return {"path": path, "name": os.path.basename(path),
            "taken": e[0], "kind": e[1], "stars": e[9], "colour": e[10],
            "located": e[12] is not None, "size": e[14],
            # The file's own date, so the address of its thumbnail is the same
            # one tomorrow. Without it the grid asked for a new URL on every
            # page load and the browser's cache - which the server allows for a
            # day - could never be used: two hundred and forty requests to the
            # NAS for pictures the browser already had.
            "when": e[15]}


def _folder_label(folder: str, roots) -> str:
    """A folder as a person would name it: its position under the library.

    The whole path is the one thing nobody needs - it is the same forty
    characters down the left of every row, and on a NAS it is somebody's user
    name on a screen.
    """
    low = os.path.normcase(os.path.abspath(folder))
    for root in roots or []:
        base = os.path.normcase(os.path.abspath(str(root)))
        if low == base:
            return os.path.basename(folder) or folder
        if low.startswith(base + os.sep):
            return folder[len(str(root)):].strip("\\/") or os.path.basename(folder)
    return folder


def timeline(cat, ask=None, offset: int = 0, limit: int = 240,
             by: str = "date") -> dict:
    """A page of the grid, and the groups it falls in.

    `by` is the only thing that differs between the two ways of looking at a
    library, and it is one sort and one label apart:

        date    newest first, under the month it was taken
        folder  A to Z by folder, newest first inside each

    Both are the same photographs and the same filter. A folder view that was a
    different list, or a different idea of what matches, would be a second
    library to keep in step.

    Paged, because a browser asked to lay out eighty thousand tiles at once
    stops being a browser. The group headings come from the WHOLE answer, not
    from the page, so the rail down the side is the shape of the library rather
    than the shape of what has been scrolled to.
    """
    # The whole answer once per filter (see `_grouped`), and this page cut out
    # of it - the headings still come from all of it.
    rows, groups, order = _grouped(cat, ask, by)
    page = rows[max(0, offset):max(0, offset) + max(1, limit)]
    items = []
    for key, path in page:
        one = card(cat, path)
        one["group"] = os.path.dirname(path) if by == "folder" else key[:7]
        items.append(one)
    return {
        "items": items,
        "total": len(rows),
        "offset": offset,
        "by": by,
        # A grid quietly smaller than the library is how "where did those go"
        # starts. It says so, every time, with the folders it left out.
        "hidden": hidden_folders(),
        "groups": [{"key": k,
                    "label": (_folder_label(k, cat.roots) if by == "folder"
                              else _month_label(k)),
                    "count": groups[k]} for k in order],
        "state": cat.state(),
    }


def _flip(key: str) -> str:
    """Newest first inside a folder, while the folders themselves go A to Z.

    One sort, two directions: the characters are inverted so that a plain
    ascending sort puts the newest date first without a second pass.
    """
    return "".join(chr(0x10FFFD - ord(c)) if ord(c) < 0x10FFFD else c
                   for c in (key or ""))


def overview(cat) -> dict:
    """The numbers the home screen opens with. No scan, no button.

    Measured when the index was last refreshed, and it says so - a dashboard
    that cannot tell you how old it is is one you cannot trust after lunch.
    """
    photos = videos = raws = located = rated = undated = 0
    size = 0
    years: dict = {}
    cameras: dict = {}
    for _key, path in cat.rows():
        e = cat.entry(path)
        if e is None:
            continue
        what = e[1]
        size += e[14] or 0
        if what == "raw":
            raws += 1
            continue
        if what == "video":
            videos += 1
        else:
            photos += 1
        if e[12] is not None:
            located += 1
        if (e[9] or 0) > 0:
            rated += 1
        if e[0]:
            years[e[0][:4]] = years.get(e[0][:4], 0) + 1
        else:
            undated += 1
        if e[2]:
            cameras[e[2]] = cameras.get(e[2], 0) + 1
    shown = photos + videos
    return {
        "photos": photos, "videos": videos, "raws": raws, "size": size,
        "located": located, "rated": rated, "undated": undated,
        "shown": shown,
        "years": sorted(years.items(), reverse=True),
        "cameras": sorted(cameras.items(), key=lambda kv: -kv[1])[:6],
        "when": cat.when, "state": cat.state(),
    }



# --------------------------------------------------------------- the folders

# What a rolled-up folder can be filtered down to on the home screen. The same
# questions the Library tab asks, minus the ones that are about the OTHER trees
# (previews, negatives) - the index knows nothing about those, and a filter that
# silently answered the wrong question would be worse than one that is absent.
ONLY = (
    ("all", "Everything"),
    ("unfinished", "Unfinished"),
    ("unrated", "Not rated"),
    ("unlocated", "No location"),
    ("undated", "No date"),
    ("raws", "RAW files mixed in"),
    ("video", "Video mixed in"),
)


def _box() -> dict:
    return {"photos": 0, "videos": 0, "raws": 0, "rated": 0, "located": 0,
            "dated": 0, "size": 0, "first": "", "last": "", "files": 0}


def _into(whole: dict, part: dict) -> None:
    for key in ("photos", "videos", "raws", "rated", "located", "dated",
                "size", "files"):
        whole[key] += part[key]
    if part["last"] > whole["last"]:
        whole["last"] = part["last"]
    if part["first"] and (not whole["first"] or part["first"] < whole["first"]):
        whole["first"] = part["first"]


def _state(done: int, whole: int) -> str:
    """none, some or all - the Library tab's three answers, by its rules.

    `some` is the one worth having: a half-rated shoot is work you left
    unfinished and must not look like a finished one. Said in one place here
    and in `core/survey.py` the same way, because the home screen and the
    Library tab are answering the same question about the same folders - one
    from the index, one from the files - and two sets of rules would show two
    different colours for one folder.
    """
    if not whole:
        return "empty"
    if done <= 0:
        return "none"
    return "all" if done >= whole else "some"


def _above(folder: str, roots) -> str:
    """The folder over this one, or "" at the top of a library root."""
    low = os.path.normcase(folder)
    for root in roots:
        base = os.path.normcase(root)
        if low == base:
            return ""
        if low.startswith(base + os.sep):
            return os.path.dirname(folder)
    return ""


def _keeps(box: dict, only: str) -> bool:
    shown = box["photos"] + box["videos"]
    if only == "unrated":
        return shown > box["rated"]
    if only == "unlocated":
        return shown > box["located"]
    if only == "undated":
        return shown > box["dated"]
    if only == "raws":
        return box["raws"] > 0
    if only == "video":
        return box["videos"] > 0
    if only == "unfinished":
        return bool(shown) and (
            box["rated"] < shown or box["located"] < shown
            or box["dated"] < shown or box["raws"] > 0)
    return True


def folders(cat, only: str = "all", most: int = 600) -> dict:
    """The library as a tree, with what has been done to each folder.

    This is the question you cannot answer by looking at a folder in File
    Station: *have I finished with this shoot?* Is it rated, is it placed, did
    anything ever get a date, are there negatives still mixed in with the
    JPEGs. Somewhere in a few hundred shoots there are three you started and
    did not finish, and nothing about the folders themselves shows it.

    The Library tab has answered this since 1.x by surveying all five trees,
    which means reading the front of every JPEG over SMB - a minute of waiting
    behind a button. This answers the part of it the index already holds, in
    the time it takes to send, so the home screen can simply have it.

    **The same rows, in the same shape, drawn by the same table.** What comes
    back here is exactly what `app/tasks/library.py` puts in `Plan.tree`, down
    to the names of the marks - so the page draws one tree, not two that have
    to be kept looking alike. The marks the index cannot answer (previews made,
    negatives in the OTHER tree, things put aside) come back as "empty", which
    is the value that already means "nothing to say about this" - never as a
    tick, because a mark that reads as finished when nothing was checked is the
    one lie this screen must not tell. The Library tab is still where the whole
    question is asked.

    A TREE HAS TO STAY A TREE. Filtering row by row leaves children indented
    under parents that are not there, which reads as a handful of orphans
    rather than a filtered library - so whatever matches is kept, and every
    folder above a match is kept with it and marked as scaffolding.
    """
    roots = [os.path.abspath(str(r)) for r in (cat.roots or []) if r]
    own: dict = {}
    for _key, path in cat.rows():
        e = cat.entry(path)
        if e is None:
            continue
        box = own.get(os.path.dirname(path))
        if box is None:
            box = own[os.path.dirname(path)] = _box()
        box["files"] += 1
        box["size"] += e[14] or 0
        if e[1] == "raw":
            box["raws"] += 1
            continue
        if e[1] == "video":
            box["videos"] += 1
        else:
            box["photos"] += 1
        if e[12] is not None:
            box["located"] += 1
        if (e[9] or 0) > 0:
            box["rated"] += 1
        if e[0]:
            box["dated"] += 1
            if e[0] > box["last"]:
                box["last"] = e[0]
            if not box["first"] or e[0] < box["first"]:
                box["first"] = e[0]

    # Rolled up: a folder's numbers are its own and everything beneath it,
    # because "is this shoot finished" is a question about the shoot, not about
    # which level of it the files happen to sit at.
    whole: dict = {}
    for folder, box in own.items():
        here = folder
        while True:
            into = whole.get(here)
            if into is None:
                into = whole[here] = _box()
            _into(into, box)
            up = _above(here, roots)
            if not up:
                break
            here = up

    kids: dict = {}
    for folder in whole:
        kids.setdefault(_above(folder, roots), []).append(folder)
    for where in kids.values():
        where.sort(key=os.path.normcase)

    only = only if only in dict(ONLY) else "all"
    matched = {f for f, box in whole.items() if _keeps(box, only)}
    keep = set(matched)
    for folder in matched:
        up = _above(folder, roots)
        while up:
            keep.add(up)
            up = _above(up, roots)

    rows: list = []
    tops = [f for f in kids.get("", []) if f in whole]

    def walk(folder: str, depth: int) -> None:
        if len(rows) >= most:
            return
        box = whole[folder]
        here = own.get(folder, _box())
        shown = box["photos"] + box["videos"]
        rows.append({
            "matched": folder in matched,
            "path": folder,
            "name": os.path.basename(folder) or folder,
            "label": _folder_label(folder, roots),
            "depth": depth,
            "photos": shown,
            "own_photos": here["photos"] + here["videos"],
            "rated": box["rated"],
            "located": box["located"],
            "dated": box["dated"],
            "raws_here": box["raws"],
            # The OTHER trees are not indexed - indexing a mirror would count
            # every photograph twice - so these are not numbers this screen has.
            # Zero and an "empty" mark, never a tick.
            "raws_apart": 0,
            "videos_here": box["videos"],
            "videos_apart": 0,
            "previews": 0,
            "culled": 0,
            "unreadable": 0,
            "bytes": box["size"],
            "own_bytes": here["size"],
            "first_taken": box["first"],
            "last_taken": box["last"],
            "marks": {
                "separated": ("empty" if not box["raws"] else "none"),
                "video": ("empty" if not box["videos"] else "none"),
                "located": _state(box["located"], shown),
                "rated": _state(box["rated"], shown),
                "dated": _state(box["dated"], shown),
                "previews": "empty",
                "culled": "empty",
                "readable": "empty",
            },
            "leaf": not [k for k in kids.get(folder, []) if k in keep],
        })
        for kid in kids.get(folder, []):
            if kid in keep:
                walk(kid, depth + 1)

    for top in tops:
        if top in keep:
            walk(top, 0)
    return {"tree": rows, "rows": rows, "only": only,
            "onlys": [list(o) for o in ONLY],
            "folders": len(whole), "shown": len(rows),
            "more": max(0, len(keep) - len(rows)),
            "measured": ago(cat.when), "state": cat.state()}


# The widgets this screen can answer from the index alone. The rest - how much
# the previews tree weighs, how many negatives have been separated - are facts
# about the OTHER trees, which are not indexed here (indexing a mirror would
# count every photograph twice). Those stay on the Library tab, where a survey
# of all five trees is the thing you came for.
FROM_INDEX = ("tile:photos", "tile:weight", "tile:rated", "tile:placed",
              "tile:cameras", "tile:years", "meter:rated", "meter:located")


def _human(n: int) -> str:
    n = float(n or 0)
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "bytes" else f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:,.1f} TB"


def _share(part: int, whole: int) -> str:
    # Halves round up, as the page's own percentages do. Python's round() sends
    # 62.5 to 62 while the browser says 63, and the Home screen shows both.
    return f"{int(100 * part / whole + 0.5)}%" if whole else "-"


def dashboard(cat) -> dict:
    """The home screen's numbers and charts, with nothing read.

    Same widgets, same arrangement, same bands as the Library tab - the board is
    `core/boards.py` either way - but counted from the index, so this screen is
    drawn in the time it takes to send it rather than in the time it takes to
    open eighty thousand files. That is the whole difference between a dashboard
    you look at and one you decide not to wait for.
    """
    from . import boards as BD
    from . import stats as ST
    picked = [w for w in BD.board() if w in FROM_INDEX or w.startswith("chart:")]
    wanted = BD.dims([w for w in picked if w.startswith("chart:")]
                     + [w for w in picked if w.startswith("tile:")])
    got = ST.tally_of(cat.hits(), wanted) if wanted else None
    sums = overview(cat)

    def counted(dim):
        return got.counts.get(dim) if got else None

    tiles, meters, charts = [], [], []
    for name in picked:
        title, kind, note = BD.WIDGETS.get(name, (name, "", ""))
        if name == "tile:photos":
            tiles.append({"label": title, "value": f"{sums['shown']:,}",
                          "note": f"{sums['videos']:,} of them videos",
                          "widget": name})
        elif name == "tile:weight":
            tiles.append({"label": title, "value": _human(sums["size"]),
                          "note": "in the library and the video tree",
                          "widget": name})
        elif name == "tile:rated":
            tiles.append({"label": title,
                          "value": _share(sums["rated"], sums["shown"]),
                          "note": f"{sums['rated']:,} of {sums['shown']:,}",
                          "widget": name})
        elif name == "tile:placed":
            tiles.append({"label": title,
                          "value": _share(sums["located"], sums["shown"]),
                          "note": f"{sums['located']:,} carry a location",
                          "widget": name})
        elif name == "tile:cameras":
            # From the camera chart's own rows. The overview's list is the six
            # biggest only, and counting it said "6" for any library with more.
            rows = counted("camera")
            many = rows.named() if rows else len(sums["cameras"])
            tiles.append({"label": title, "value": f"{many:,}",
                          "note": "that wrote their name into a file",
                          "widget": name})
        elif name == "tile:years":
            tiles.append({"label": title, "value": f"{len(sums['years'])}",
                          "note": "the library spans", "widget": name})
        elif name == "meter:rated":
            meters.append([title, sums["rated"], sums["shown"], name])
        elif name == "meter:located":
            meters.append([title, sums["located"], sums["shown"], name])
        elif name.startswith("chart:") and name != "chart:space":
            rows = counted(name.split(":", 1)[1])
            if rows and rows.rows:
                one = {"kind": "donut" if kind == "donut" else "bars",
                       "dim": name.split(":", 1)[1], "title": title,
                       "note": note, "unit": "photos", "widget": name}
                one.update(rows.drawn(8))
                charts.append(one)
    return {"tiles": tiles, "done": meters, "charts": charts,
            "folders": list(cat.roots), "board": BD.now(),
            "boards": BD.names(), "widgets": BD.catalogue(BD.board()),
            "overview": sums, "state": cat.state(),
            "measured": ago(cat.when)}


def inside(cat, where: str = "", ask=None, offset: int = 0, limit: int = 240,
           deep: bool = False) -> dict:
    """One folder: the folders in it, and the photographs in it.

    The folder view used to be the whole library in one list with a heading
    every time the folder changed - which is not a folder view, it is the
    timeline sorted differently. Eighty thousand tiles to scroll past to reach
    the shoot you wanted, and no way to see that a folder HAS sub-folders until
    you had scrolled through everything in it.

    This is a place you walk into: where you are, what folders are here with a
    cover and a count, and the photographs that are in THIS folder. Nothing is
    read - it is the index, grouped by the one thing every file already carries,
    which is where it sits.

    `deep` is the old behaviour, kept and named: everything below here, not just
    what is in here.
    """
    roots = [os.path.abspath(str(r)) for r in (cat.roots or []) if r]
    here = os.path.abspath(str(where).strip()) if str(where or "").strip() else ""
    if here and not any(os.path.normcase(here) == os.path.normcase(r)
                        or os.path.normcase(here).startswith(os.path.normcase(r) + os.sep)
                        for r in roots):
        here = ""                      # outside the library: start at the top
    # ONE library means starting inside it. A top level holding a single card
    # called "Photos" is a click that tells you nothing, every time.
    if not here and len(roots) == 1:
        here = roots[0]

    rows = matched(cat, ask)
    low = os.path.normcase(here) if here else ""

    kids: dict = {}
    mine: list = []
    for key, path in rows:
        folder = os.path.dirname(path)
        fold_low = os.path.normcase(folder)
        if here:
            if fold_low == low:
                mine.append((key, path))
                continue
            if not fold_low.startswith(low + os.sep):
                continue
            rest = folder[len(here):].strip("\\/")
            kid = os.path.join(here, rest.split(os.sep)[0]
                               if os.sep in rest else rest.split("/")[0])
            if deep:
                mine.append((key, path))
        else:
            # At the top, the roots themselves are the folders.
            root = next((r for r in roots
                         if fold_low == os.path.normcase(r)
                         or fold_low.startswith(os.path.normcase(r) + os.sep)), "")
            if not root:
                continue
            if os.path.normcase(folder) == os.path.normcase(root):
                mine.append((key, path))
                continue
            rest = folder[len(root):].strip("\\/")
            kid = os.path.join(root, rest.replace("\\", "/").split("/")[0])
            if deep:
                mine.append((key, path))
        box = kids.get(kid)
        if box is None:
            box = kids[kid] = {"photos": 0, "videos": 0, "raws": 0,
                               "cover": "", "key": "", "size": 0}
        e = cat.entry(path)
        box["size"] += (e[14] or 0) if e else 0
        if e is not None and e[1] == "raw":
            box["raws"] += 1
        else:
            if e is not None and e[1] == "video":
                box["videos"] += 1
            else:
                box["photos"] += 1
            if key > box["key"]:
                box["key"], box["cover"] = key, path
                box["when"] = (e[15] if e is not None else 0) or 0

    if not here:
        # Several trees - the library and the video tree, say - so the top level
        # IS the trees, and nothing below them is listed beside them.
        whole: dict = {}
        for root in roots:
            box = whole[root] = {"photos": 0, "videos": 0, "raws": 0,
                                 "cover": "", "key": "", "size": 0}
            low_root = os.path.normcase(root)
            for key, path in rows:
                folder = os.path.normcase(os.path.dirname(path))
                if folder != low_root and not folder.startswith(low_root + os.sep):
                    continue
                e = cat.entry(path)
                box["size"] += (e[14] or 0) if e else 0
                if e is not None and e[1] == "raw":
                    box["raws"] += 1
                    continue
                if e is not None and e[1] == "video":
                    box["videos"] += 1
                else:
                    box["photos"] += 1
                if key > box["key"]:
                    box["key"], box["cover"] = key, path
                box["when"] = (e[15] if e is not None else 0) or 0
        kids = whole
        mine = []

    folders = []
    for path in sorted(kids, key=os.path.normcase):
        box = kids[path]
        folders.append({"path": path, "name": os.path.basename(path) or path,
                        "photos": box["photos"], "videos": box["videos"],
                        "raws": box["raws"], "size": box["size"],
                        "cover": box["cover"], "cover_when": box.get("when", 0),
                        "newest": box["key"][:10]})

    crumbs = []
    if here:
        root = next((r for r in roots
                     if os.path.normcase(here) == os.path.normcase(r)
                     or os.path.normcase(here).startswith(os.path.normcase(r) + os.sep)), "")
        if root:
            crumbs.append({"path": root, "name": os.path.basename(root) or root})
            rest = here[len(root):].strip("\\/")
            walked = root
            for bit in [b for b in rest.replace("\\", "/").split("/") if b]:
                walked = os.path.join(walked, bit)
                crumbs.append({"path": walked, "name": bit})

    page = mine[max(0, offset):max(0, offset) + max(1, limit)]
    items = []
    for key, path in page:
        one = card(cat, path)
        one["group"] = os.path.dirname(path)
        items.append(one)
    return {
        "where": here, "crumbs": crumbs, "folders": folders,
        "up": (os.path.dirname(here) if here and crumbs and len(crumbs) > 1
               else ("" if not here else "")),
        # "nowhere above here": the virtual top, or a library root, which is
        # the top when there is one library and the walk starts inside it.
        "at_top": (not here) or any(os.path.normcase(here) == os.path.normcase(r)
                                    for r in roots),
        "items": items, "total": len(mine), "offset": offset, "deep": bool(deep),
        "hidden": hidden_folders(), "state": cat.state(),
    }


def choices(cat, most: int = 200) -> dict:
    """What the library actually holds, per criterion, biggest first.

    For the menus over the grid and in the album maker. Typing a camera's name
    from memory is how somebody searches a library of `DMC-GH4` files for
    `DMC-GH5` and concludes there is nothing there - so the criteria offer what
    the files really say, spelled the way they spell it.

    `core/stats.py` has answered this since 2.x by READING the library, which is
    right for the Search tab's own numbers and far too slow for a menu that has
    to be there when the panel opens. This is the same question asked of the
    index, so it costs a walk over a table in memory.
    """
    cameras: dict = {}
    lenses: dict = {}
    tags: dict = {}
    colours: dict = {}
    kinds: dict = {}
    years: dict = {}
    towns: dict = {}
    lands: dict = {}
    # The places the library actually holds, so "in Spain" is something you pick
    # rather than something you spell. Typing a country name into a free box and
    # getting nothing back tells you nothing about whether the name was wrong,
    # the photographs have no location, or no place table was ever imported.
    namer = place_namer()
    for _key, path in cat.rows():
        e = cat.entry(path)
        if e is None:
            continue
        kinds[e[1]] = kinds.get(e[1], 0) + 1
        if e[1] == "raw":
            continue
        if namer is not None and e[12] is not None:
            said = namer(e[12], e[13])
            if said:
                town, _sep, land = said.partition(", ")
                if land:
                    lands[land] = lands.get(land, 0) + 1
                    towns[town] = towns.get(town, 0) + 1
                else:
                    lands[town] = lands.get(town, 0) + 1
        if e[2]:
            cameras[e[2]] = cameras.get(e[2], 0) + 1
        if e[3]:
            lenses[e[3]] = lenses.get(e[3], 0) + 1
        if e[10]:
            colours[e[10]] = colours.get(e[10], 0) + 1
        for word in (e[11] or []):
            word = str(word).strip()
            if word:
                tags[word] = tags.get(word, 0) + 1
        if e[0]:
            years[e[0][:4]] = years.get(e[0][:4], 0) + 1

    def listed(counts, by_name=False):
        rows = sorted(counts.items(),
                      key=(lambda kv: kv[0]) if by_name else (lambda kv: -kv[1]))
        return [{"name": k, "count": v} for k, v in rows[:most]]

    from . import devices
    return {
        # The camera's own name beside the code it writes, because "Lumix GH4"
        # is what somebody is looking for and `DMC-GH4` is what the file says.
        "camera": [{"name": k, "count": v, "label": devices.label(k) or k}
                   for k, v in sorted(cameras.items(), key=lambda kv: -kv[1])[:most]],
        "lens": listed(lenses),
        "tags": listed(tags),
        "colour": listed(colours),
        "kinds": listed(kinds),
        "years": listed(years, by_name=True),
        "city": listed(towns),
        "country": listed(lands),
        # Said out loud, because "no towns offered" has two very different
        # causes and the screen has to be able to tell them apart.
        "places": {"table": place_table() is not None,
                   "located": sum(1 for _k, p in cat.rows()
                                  if (cat.entry(p) or [None] * 13)[12] is not None)},
        "state": cat.state(),
    }


# ------------------------------------------------------------------- the places

def clusters(cat, zoom: int = 4, limit: int = 400) -> dict:
    """Pins on a map, and the biggest ones named.

    Named one per cluster, never one per photograph: resolving a coordinate to a
    town is a lookup in a table of millions, and doing it a hundred thousand
    times to draw forty pins would be the slow screen this file exists to avoid.

    Kept per zoom until the index or a setting moves: panning the map asks for
    the same zoom again and again, and the pins of a library that has not
    changed do not move. The index's state is read fresh every time.
    """
    got = kept(cat, f"clusters:{int(zoom)}:{int(limit)}",
               lambda: _clusters(cat, zoom, limit))
    return {"zoom": zoom, "pins": [dict(p) for p in got["pins"]],
            "located": got["located"], "state": cat.state()}


def _clusters(cat, zoom: int, limit: int) -> dict:
    step = GRIDS.get(int(zoom), 1.0)
    cells: dict = {}
    for _key, path in cat.rows():
        e = cat.entry(path)
        if e is None or e[12] is None:
            continue
        cell = (round(e[12] / step), round(e[13] / step))
        got = cells.get(cell)
        if got is None:
            cells[cell] = {"lat": e[12], "lon": e[13], "count": 1,
                           "cover": path, "taken": e[0]}
        else:
            got["count"] += 1
            # the newest one in the cell is its cover, which is what makes a
            # map of a trip look like the trip rather than like its first day
            if (e[0] or "") > (got["taken"] or ""):
                got["cover"], got["taken"] = path, e[0]
            got["lat"] = (got["lat"] * (got["count"] - 1) + e[12]) / got["count"]
            got["lon"] = (got["lon"] * (got["count"] - 1) + e[13]) / got["count"]
    out = sorted(cells.values(), key=lambda c: -c["count"])[:limit]
    for one in out:
        one["lat"] = round(one["lat"], 6)
        one["lon"] = round(one["lon"], 6)
    return {"pins": out, "located": sum(c["count"] for c in cells.values())}


def named_places(cat, most: int = 40) -> list:
    """The biggest clusters, with a town and a country where one can be found.

    Falls back to the coordinates themselves, which is honest: a place table
    that has not been imported is a thing to say, not a reason to show nothing.
    """
    from . import places as P
    from .store import store_path
    table = None
    try:
        got = P.load(store_path("places.tsv"))
        table = got if got and got.rows else None
    except Exception:                                      # noqa: BLE001
        table = None
    out = []
    for one in clusters(cat, zoom=6, limit=most)["pins"]:
        name = ""
        if table is not None:
            try:
                found = P.from_coordinates(table, one["lat"], one["lon"])
                name = ", ".join(x for x in (found.city, found.country) if x)
            except Exception:                              # noqa: BLE001
                name = ""
        out.append({"name": name or f"{one['lat']:.3f}, {one['lon']:.3f}",
                    "lat": one["lat"], "lon": one["lon"],
                    "count": one["count"], "cover": one["cover"],
                    "named": bool(name)})
    return out


# ------------------------------------------------------------------- the albums

def albums(cat, show_all: bool = False) -> list:
    """Collections that are questions, not folders.

    Nothing here is stored or editable, and that is the point: an album that is
    a saved list goes wrong the moment a photograph moves, and this app moves
    photographs for a living. Each of these is recomputed from the index, so it
    is right by construction.
    """
    from . import settings as S
    saved = S.load()
    try:
        at_least = int(saved["develop_jpeg_at"] or 4)
    except (TypeError, ValueError):
        at_least = 4
    bracket_tag = str(saved["bracket_tag"] or "bracket").strip().lower()

    buckets: dict = {}

    def put(key, title, why, path, taken, colour="", when=0):
        """`taken` here is the catalogue's own sort key, not the capture time -
        so an album's cover is the first thing the grid would show in it.

        `when` is the cover file's own date, which is what makes its thumbnail
        address stable from one page load to the next."""
        got = buckets.get(key)
        if got is None:
            buckets[key] = {"key": key, "title": title, "why": why, "count": 1,
                            "cover": path, "taken": taken, "tone": colour,
                            "cover_when": when}
        else:
            got["count"] += 1
            if (taken or "") > (got["taken"] or ""):
                got["cover"], got["taken"] = path, taken
                got["cover_when"] = when

    tags: dict = {}
    hide = hidden_folders()
    for sortkey, path in cat.rows():
        e = cat.entry(path)
        if e is None or e[1] == "raw":
            continue
        # An album's count has to be the number of photographs opening it
        # shows. The grid leaves the hidden folders out, so these do too.
        if hide and is_hidden(path, hide):
            continue
        taken = sortkey
        when = e[15] or 0
        if (e[9] or 0) >= 5:
            put("favourites", "Favourites", "five stars", path, taken, "amber", when)
        if (e[9] or 0) >= at_least:
            put("develop", "To develop", f"{at_least} stars and up", path, taken,
                "purple", when)
        if e[1] == "video":
            put("videos", "Videos", "videos in the library", path, taken, "teal", when)
        if e[12] is None:
            put("nolocation", "No location", "nothing to put on the map", path,
                taken, "", when)
        if not (e[9] or 0):
            put("unrated", "Not rated", "no stars yet", path, taken, "", when)
        for word in (e[11] or []):
            low = str(word).strip().lower()
            if not low:
                continue
            if low == bracket_tag:
                put("brackets", "Brackets", "tagged as a bracketed set", path,
                    taken, "orange", when)
            else:
                tags.setdefault(low, []).append((path, taken, word, when))

    out = [buckets[k] for k in ("favourites", "develop", "brackets", "videos",
                                "unrated", "nolocation") if k in buckets]
    # And the ones you made yourself. A kept search IS an album - it is a
    # question with an answer that moves as the library does - so there is one
    # mechanism rather than two, and keeping one from the filters above the grid
    # is the same act as keeping one from the Search tab.
    from . import find as _find
    for name, ask in _find.saved():
        try:
            rows = matching(cat, _find.from_dict(ask))
        except Exception:                                  # noqa: BLE001
            continue
        if not rows:
            continue
        first = cat.entry(rows[0][1])
        out.append({"key": "kept:" + name, "title": name, "why": "kept search",
                    "count": len(rows), "cover": rows[0][1],
                    "cover_when": (first[15] if first else 0) or 0,
                    "taken": rows[0][0], "tone": "blue", "mine": True})
    # And the tags people actually use, biggest first - a tag used twice is not
    # a collection, it is a typo.
    for low, rows in sorted(tags.items(), key=lambda kv: -len(kv[1]))[:8]:
        if len(rows) < 3:
            continue
        rows.sort(key=lambda r: r[1] or "", reverse=True)
        out.append({"key": "tag:" + low, "title": rows[0][2], "why": "tagged",
                    "count": len(rows), "cover": rows[0][0],
                    "cover_when": rows[0][3], "taken": rows[0][1], "tone": "teal"})
    # Put away at the end, where every album is in one list - so the built-in
    # ones, the ones you made and the ones made out of your tags all answer to
    # the same button. An album is a question; putting it away is declining to
    # ask it, and the question is still there to be asked again.
    away = hidden_albums()
    if away and not show_all:
        out = [a for a in out if a["key"] not in away]
    return out


def hidden_albums() -> list:
    """The albums put away, by key. Never a deletion: see the setting."""
    import json
    from . import settings as S
    try:
        got = json.loads(str(S.load()["hide_albums"] or "[]"))
    except (ValueError, TypeError):
        return []
    return [str(k) for k in got if str(k)] if isinstance(got, list) else []


def hide_albums(keys) -> list:
    """Keep that list. Returns what was kept."""
    import json
    from . import settings as S
    clean = []
    for one in (keys or []):
        text = str(one or "").strip()[:200]
        if text and text not in clean:
            clean.append(text)
    S.save({"hide_albums": json.dumps(clean) if clean else ""})
    return clean


def album_ask(key: str):
    """The search one of those albums IS, so opening it is an ordinary filter
    rather than a second way of listing photographs."""
    from . import find
    from . import settings as S
    saved = S.load()
    try:
        at_least = int(saved["develop_jpeg_at"] or 4)
    except (TypeError, ValueError):
        at_least = 4
    if key == "favourites":
        return find.Ask(stars_from=5)
    if key == "develop":
        return find.Ask(stars_from=at_least)
    if key == "videos":
        return find.Ask(kinds=("video",))
    if key == "unrated":
        return find.Ask(stars_to=0)
    if key == "nolocation":
        return find.Ask(located="no")
    if key == "brackets":
        return find.Ask(tags=(str(saved["bracket_tag"] or "bracket"),))
    if key.startswith("tag:"):
        return find.Ask(tags=(key[4:],))
    if key.startswith("kept:"):
        for name, ask in find.saved():
            if name == key[5:]:
                return find.from_dict(ask)
    return find.Ask()


# ---------------------------------------------------------------- the people

def people_named() -> list:
    """The tags you have said are people, in the order you said them."""
    from . import settings as S
    said = str(S.load()["people_tags"] or "")
    out = []
    for word in said.replace("\n", ",").split(","):
        word = word.strip()
        if word and word.lower() not in [o.lower() for o in out]:
            out.append(word)
    return out


def name_people(names) -> list:
    """Write that list back. Returns what was kept."""
    from . import settings as S
    keep = []
    for word in names or []:
        word = str(word).strip()
        if word and word.lower() not in [k.lower() for k in keep]:
            keep.append(word)
    S.save({"people_tags": ", ".join(keep)})
    return keep


def tag_counts(cat) -> list:
    """Every tag in the library and how many photographs carry it.

    Out of the index, so it costs nothing - and it is what makes naming people
    a matter of ticking the ones that are, rather than typing them from memory.
    """
    counts: dict = {}
    covers: dict = {}
    for key, path in cat.rows():
        e = cat.entry(path)
        if e is None:
            continue
        for word in (e[11] or []):
            word = str(word).strip()
            if not word:
                continue
            low = word.lower()
            counts[low] = counts.get(low, 0) + 1
            if low not in covers or key > covers[low][0]:
                covers[low] = (key, path, word)
    return [{"name": covers[low][2], "count": n, "cover": covers[low][1]}
            for low, n in sorted(counts.items(), key=lambda kv: -kv[1])]


def people(cat) -> dict:
    """Who is in the library, and which other tags you might mean by that.

    `candidates` is every other tag with its count: naming somebody is ticking
    a name that is already in your photographs, which is both quicker than
    typing and incapable of inventing one.
    """
    want = people_named()
    low = {w.lower() for w in want}
    seen = {t["name"].lower(): t for t in tag_counts(cat)}
    out = []
    for name in want:
        got = seen.get(name.lower())
        out.append({"name": name, "count": got["count"] if got else 0,
                    "cover": got["cover"] if got else ""})
    out.sort(key=lambda p: -p["count"])
    rest = [t for t in seen.values() if t["name"].lower() not in low]
    return {"people": out, "candidates": rest[:60], "named": want}


# -------------------------------------------------------------- one photograph

def detail(cat, path: str) -> dict:
    """Everything the detail view shows, out of the index and the files beside it.

    The related files are the honest answer to "what else IS this photograph" -
    the negative, the preview, the sidecar - and they are found the way the rest
    of the app finds them (`core/pairs.py`), by position in the mirrored trees,
    so this view cannot disagree with the feature that moves them.
    """
    e = cat.entry(path)
    out = {"path": path, "name": os.path.basename(path),
            "folder": os.path.dirname(path), "there": os.path.exists(path)}
    if e is not None:
        for i, name in enumerate(("taken", "kind", "camera", "lens", "focal",
                                  "focal35", "fnumber", "shutter", "iso",
                                  "stars", "colour", "tags", "lat", "lon",
                                  "size", "when")):
            out[name] = e[i]
    out["files"] = related(path)
    return out


# What a negative of this photograph could be called. The app cannot know which
# camera wrote it without opening the folder, so it looks for all of them - the
# same list `core/photo.py` calls a RAW.
RAW_SUFFIXES = (".RW2", ".ARW", ".DNG", ".CR2", ".CR3", ".NEF", ".ORF", ".RAF")


def related(path: str) -> list:
    """The negative, the preview, the developed copy and the sidecar.

    Found by POSITION in the mirrored trees, which is how every feature in this
    app finds them (`core/paths.py`) - so this view cannot disagree with the
    thing that moves them. Only files that are really there are listed: a
    detail view that confidently names a preview which does not exist is worse
    than one that says there is none.
    """
    from . import paths as P
    from . import settings as S
    saved = S.load()
    out = [{"what": "This file", "path": path, "kind": "self",
            "size": _size_of(path), "there": os.path.exists(path)}]
    library = str(saved["library"] or "")
    if not library:
        return out
    raw_root = str(saved["raw"] or "")
    if raw_root:
        stem = os.path.splitext(P.mirror(path, library, raw_root))[0]
        for suffix in RAW_SUFFIXES:
            for one in (stem + suffix, stem + suffix.lower()):
                if os.path.isfile(one):
                    out.append({"what": "RAW", "path": one, "kind": "raw",
                                "size": _size_of(one), "there": True})
                    break
    previews = str(saved["previews"] or "")
    if previews:
        one = P.preview_for(path, library, previews)
        if os.path.isfile(one):
            out.append({"what": "Preview", "path": one, "kind": "previews",
                        "size": _size_of(one), "there": True})
    develop = str(saved["develop"] or "")
    if develop:
        one = P.mirror(path, library, develop)
        if os.path.isfile(one):
            out.append({"what": "Sent to develop", "path": one,
                        "kind": "develop", "size": _size_of(one), "there": True})
    for side in P.companions(path):
        out.append({"what": "Sidecar", "path": side, "kind": "sidecar",
                    "size": _size_of(side), "there": True})
    return out


def _size_of(path: str) -> int:
    try:
        return os.stat(path).st_size
    except OSError:
        return 0


def ago(when: float) -> str:
    """"4 minutes ago", for the line that says how old the numbers are."""
    if not when:
        return "never"
    gap = max(0, int(time.time() - when))
    if gap < 90:
        return "just now"
    # Home printed "Counted 1 minutes ago": the count decides the word.
    if gap < 5400:
        n, word = gap // 60, "minute"
    elif gap < 172800:
        n, word = gap // 3600, "hour"
    else:
        n, word = gap // 86400, "day"
    return f"{n} {word}{'' if n == 1 else 's'} ago"
