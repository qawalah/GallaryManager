"""The library as a tree, with what has been done to each folder.

The question this answers is the one you cannot answer by looking at a folder in
File Station: *have I finished with this shoot?* Are its RAWs out? Is it rated?
Did it ever get geotagged? Somewhere in a library of a few hundred shoots there
are three you started and did not finish, and nothing about the folders shows it.

Every mark is read from the files as they are now - see `core/survey.py` for why
a log of past actions would be worse than useless here. Nothing is written, and
nothing can be: this task has no apply.

The three states an icon can show are none, some and all, and **some** is the one
worth having. A half-geotagged shoot is unfinished work; it must not look like a
finished one.
"""

from __future__ import annotations

import os

from app.registry import (Choice, Flag, Folder, Folders, Plan, Result,
                          Task, register)
from core import settings as S
from core import survey as SV
from core.store import store_path

CACHE = "survey.json"

ONLY = [
    ("all", "Everything"),
    ("unfinished", "Unfinished"),
    ("raws", "RAWs still mixed in"),
    ("unlocated", "No location"),
    ("unrated", "Not rated"),
    ("nopreviews", "No previews"),
    ("undated", "No date"),
    ("located", "Location done"),
    ("rated", "Rating done"),
    ("separated", "RAWs separated"),
    ("previewed", "Previews done"),
    ("video", "Video still mixed in"),
    ("unreadable", "Could not be read"),
]


def _keeps(state: SV.FolderState, only: str) -> bool:
    """Whether a rolled-up folder survives the filter."""
    if only == "all":
        return True
    marks = state.marks()
    if only == "raws":
        return state.raws_here > 0
    if only == "video":
        return state.videos_here > 0
    if only == "unrated":
        return state.photos > state.rated
    if only == "unlocated":
        return state.photos > state.located
    if only == "undated":
        return state.photos > state.dated
    if only == "unreadable":
        return state.unreadable > 0
    if only == "nopreviews":
        return bool(state.photos) and marks["previews"] in ("none", "some")
    # The other half of each question. "Which shoots still need a location" and
    # "which are done" are both worth asking, and a filter that only answers the
    # first makes you check the second by elimination.
    if only == "located":
        return bool(state.photos) and marks["located"] == "all"
    if only == "rated":
        return bool(state.photos) and marks["rated"] == "all"
    if only == "separated":
        return marks["separated"] == "all"
    if only == "previewed":
        return bool(state.photos) and marks["previews"] == "all"
    if only == "unfinished":
        return (any(marks[k] == "some" for k in ("separated", "located", "rated",
                                                 "dated", "previews", "video"))
                or state.raws_here > 0 or state.videos_here > 0
                # a folder the app cannot read properly is not finished either,
                # whatever the other marks say about the part it could read
                or state.unreadable > 0)
    return True


def plan(opts, progress=None) -> Plan:
    p = Plan(task="library")
    library = (opts.get("folder") or "").strip()
    if not library or not os.path.isdir(library):
        p.blocked = f"There is no library at {library!r}"
        return p

    saved = S.load()
    raw_root = (opts.get("raw") or "").strip()
    previews_root = (opts.get("previews") or "").strip()
    video_root = (opts.get("video") or "").strip()

    cache = SV.Cache(store_path(CACHE))
    # Reading the front of every JPEG over SMB is the slow part of this whole
    # app. Saying which folder it is on turns a page that looks hung into one
    # that is plainly working.
    leave_out = Folders.chosen(opts.get("exclude"))
    found = SV.survey(library, raw_root, previews_root, video_root=video_root,
                      cache=cache,
                      rescan=bool(opts.get("rescan")),
                      leave_out=SV.leaving_out(leave_out),
                      progress=(lambda i, n, where: progress(i, n, where, "OK"))
                      if progress else None)
    for e in found.errors:
        p.errors.append(e)

    only = opts.get("only") or "all"
    rolled = {}
    for state in found.order():
        rolled[state.path] = state.totals(found.folders)

    # A TREE HAS TO STAY A TREE.
    #
    # Filtering row by row leaves children with no parents above them: ask for
    # "location done" and you get three shoots at the third level of indentation
    # with nothing over them, which reads as a set of orphaned folders rather
    # than a filtered library. Some filters happened not to do this because they
    # test rolled-up totals, which a parent inherits - but that was luck, not
    # design, and it broke the moment a filter asked about a folder's own state.
    #
    # So: whatever matches is kept, and then every folder ABOVE a match is kept
    # too, marked as scaffolding so the display can tell them apart.
    matched = {state.path for state in found.order()
               if _keeps(rolled[state.path], only)}
    keep = set(matched)
    for path in matched:
        here = path
        while here and len(here) > len(library):
            here = os.path.dirname(here)
            keep.add(here)

    shown = 0
    for state in found.order():
        whole = rolled[state.path]
        if state.path not in keep:
            continue
        if state.path in matched:
            shown += 1
        p.tree.append({
            "matched": state.path in matched,
            "path": state.path,
            "name": state.name or os.path.basename(library) or library,
            "depth": state.depth,
            "photos": whole.photos,
            "own_photos": state.photos,
            "rated": whole.rated,
            "located": whole.located,
            "raws_here": whole.raws_here,
            "raws_apart": whole.raws_apart,
            "videos_here": whole.videos_here,
            "videos_apart": whole.videos_apart,
            "previews": whole.previews,
            "culled": whole.culled,
            "dated": whole.dated,
            "unreadable": whole.unreadable,
            # What the shoot weighs across every tree it reaches into, and the
            # stretch of time its photographs cover: both come free with the
            # read the marks already needed, and both are things you want in
            # the same glance as "is this one finished".
            "bytes": whole.weight(),
            "own_bytes": whole.bytes,
            "first_taken": whole.first_taken,
            "last_taken": whole.last_taken,
            "marks": whole.marks(),
            "leaf": not state.children,
        })

    top = rolled.get(library, SV.FolderState())
    p.stats = [
        ("Folders", f"{len(found.folders):,}"),
        ("Photos", f"{top.photos:,}"),
        ("Rated", f"{top.rated:,}  ({_share(top.rated, top.photos)})"),
        ("With a location", f"{top.located:,}  ({_share(top.located, top.photos)})"),
        ("Previews made", f"{top.previews:,}  ({_share(top.previews, top.photos)})"),
        ("RAWs separated", f"{top.raws_apart:,}"),
        ("RAWs still in the library", f"{top.raws_here:,}"),
        ("Video separated", f"{top.videos_apart:,}"),
        ("Video still in the library", f"{top.videos_here:,}"),
        ("Moved aside", f"{top.culled:,}"),
    ]
    # Only when some are missing. It read "all" for every library that has ever
    # opened this tab, which is a line of the first screen spent saying nothing -
    # and when it ISN'T all, it is the most important line here, because a
    # photograph with no capture time is silently skipped by Sort into folders,
    # Geotag and pairing by time.
    if top.photos and top.dated < top.photos:
        p.stats.insert(3, ("With no date at all", f"{top.photos - top.dated:,}"))
    if found.stranded:
        p.stats.append(("RAWs with no folder in the library",
                        f"{found.stranded_raws:,}"))
    if only != "all":
        p.stats.insert(0, ("Folders matching", f"{shown:,}"))
        p.stats.insert(1, ("Shown, with the ones holding them up",
                           f"{len(p.tree):,}"))

    if opts.get("charts", True):
        p.charts = _dashboard(library, top, found, progress)
        if p.charts.get("cold"):
            p.notes.append(
                "The charts read every photo once - the first time on a "
                "big library that is minutes, and every visit after it is "
                "nearly free. Turn them off in Advanced if you would rather "
                "not wait.")

    p.notes.append(
        "Every column is read from the files right now, not from a record of what "
        "was done. Move a shoot in File Station and the answer moves with it.")
    p.notes.append(
        f"{found.read:,} folder(s) read this time, {found.reused:,} answered from "
        f"last time. Only folders whose contents changed are read again.")
    if not raw_root:
        p.notes.append("No RAW tree given, so nothing can be said about separating.")
    if not previews_root:
        p.notes.append("No previews tree given, so nothing can be said about previews.")
    if not video_root and top.videos_here:
        p.notes.append(f"{top.videos_here:,} video(s) are sitting in the library. "
                       f"Fill in the video tree on Setup and 'Separate video' "
                       f"moves them into a tree of their own, in the same shape.")
    if found.stranded:
        p.notes.append(
            f"{found.stranded_raws:,} RAW(s) sit in {len(found.stranded):,} folder(s) "
            f"that no longer exist in the library - which is what a renamed or moved "
            f"shoot leaves behind. Re-mirror finds them by capture time and puts them "
            f"back beside their JPEGs.")
        for path, n in found.stranded[:20]:
            p.skipped.append((path,
                              f"{n} RAW(s) here, but no matching folder in the library"))
        # "Left alone" is what a task that ACTS calls the things it did not
        # touch. This one never touches anything, so the word was nonsense
        # here - these are stranded RAW folders, and that is what to call them.
        p.data["skipped_title"] = "RAW folders with nothing to match"
        p.data["skipped_note"] = "the library has no folder by that name any more"

    if top.unreadable:
        p.notes.append(f"{top.unreadable:,} photo(s) had no readable EXIF, so they "
                       f"count as neither rated nor located.")
    return p


def _share(part: int, whole: int) -> str:
    if not whole:
        return "-"
    if part >= whole:
        return "all"
    # Halves round up, to agree with the page and the Home screen (see browse).
    return f"{int(100 * part / whole + 0.5)}%"


def _human(n) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return (f"{n:,.0f} {unit}" if unit in ("B", "KB") else f"{n:,.1f} {unit}")
        n /= 1024
    return f"{n:,.1f} TB"


def _dashboard(library: str, top, found, progress=None) -> dict:
    """The library at a glance - the widgets THIS board asks for, in its order.

    The folder tree below answers "have I finished with this shoot". These
    answer the questions that are about the photographs themselves - which
    years, which cameras, which apertures, how far along the whole thing is -
    and none of them can be read off a tree, however long you look at it.

    Which of them appear is not decided here any more. A board is a list of
    widget names (`core/boards.py`) and this walks that list. Only the
    dimensions that list needs are counted, so a dashboard with three charts on
    it costs three charts rather than nine.

    Read through the same per-file cache as Search and Space, so whichever of
    the three you open first pays and the other two are free.
    """
    from core import boards as BD
    from core import stats as ST

    picked = BD.board()
    wanted = BD.dims(picked)
    # From the index where the index has read this tree, which is the whole
    # point of there being one: the charts used to cost a pass over every
    # photograph every time you opened the tab, and were thrown away the moment
    # you left it. Falls back to reading where it has not - a folder outside the
    # library, or an index that has not finished - so the answer is the same
    # answer either way, just slower.
    from core import catalogue as CAT
    cat = CAT.shared()
    try:
        if not wanted:
            got = None
        elif cat.files and not cat.building and cat.covers([library]):
            got = ST.tally_of(cat.hits([library]), wanted)
        else:
            got = ST.tally([library], wanted, progress=progress)
    except Exception:                                  # noqa: BLE001
        return {}

    def counted(dim):
        return got.counts.get(dim) if got else None

    def chart(name, many=8):
        title, kind, note = BD.WIDGETS[name]
        dim = name.split(":", 1)[1]
        rows = counted(dim)
        if not rows or not rows.rows:
            return None
        one = {"kind": "donut" if kind == "donut" else "bars", "dim": dim,
               "title": title, "note": note, "unit": "photos", "widget": name}
        one.update(rows.drawn(many))
        return one

    space = [["The library itself", top.photos, top.bytes],
             ["RAWs", top.raws_apart, top.raw_bytes],
             ["Previews", top.previews, top.preview_bytes],
             ["Video", top.videos_apart, top.video_bytes],
             ["Moved aside", top.culled, top.culled_bytes]]
    space = [row + [{}] for row in space if row[2]]

    def tile(name):
        title = BD.WIDGETS[name][0]
        if name == "tile:photos":
            return {"label": title, "value": f"{(got.photos if got else top.photos):,}",
                    "note": f"in {len(found.folders):,} folder(s)", "widget": name}
        if name == "tile:weight":
            return {"label": title, "value": _human(top.weight()),
                    "note": f"{_human(top.bytes)} of it in the library",
                    "widget": name}
        if name == "tile:rated":
            return {"label": title, "value": _share(top.rated, top.photos),
                    "note": f"{top.rated:,} of {top.photos:,}", "widget": name}
        if name == "tile:placed":
            return {"label": title, "value": _share(top.located, top.photos),
                    "note": f"{top.located:,} carry a location", "widget": name}
        if name == "tile:cameras":
            rows = counted("camera")
            return {"label": title, "value": f"{rows.named() if rows else 0:,}",
                    "note": "that wrote their name into a file", "widget": name}
        if name == "tile:years":
            rows = counted("year")
            return {"label": title, "value": f"{rows.named() if rows else 0:,}",
                    "note": "the library spans", "widget": name}
        return None

    METERS = {
        "meter:rated": (top.rated, top.photos),
        "meter:located": (top.located, top.photos),
        "meter:previews": (top.previews, top.photos),
        "meter:raws": (top.raws_apart, top.raws_apart + top.raws_here),
    }

    tiles, done, charts = [], [], []
    for name in picked:
        if name.startswith("tile:"):
            made = tile(name)
            if made:
                tiles.append(made)
        elif name in METERS:
            part, whole = METERS[name]
            if whole:
                done.append([BD.WIDGETS[name][0], part, whole, name])
        elif name == "chart:space":
            if space:
                charts.append({"kind": "donut", "dim": "space",
                               "title": BD.WIDGETS[name][0],
                               "note": BD.WIDGETS[name][2], "unit": "bytes",
                               "rows": space, "show": 8, "more": 0,
                               "widget": name})
        elif name.startswith("chart:"):
            made = chart(name)
            if made:
                charts.append(made)

    return {
        "tiles": tiles,
        "done": done,
        "charts": charts,
        # Which folder these numbers are OF. A chart counted one folder and the
        # search it led to counted the whole library, so pointing the Library at
        # one shoot and clicking its 2013 bar answered a different question than
        # the bar had asked.
        "folders": [library],
        "board": BD.now(),
        "boards": BD.names(),
        "widgets": BD.catalogue(picked),
        "cold": bool(got) and "read" in (got.read or "")
                and not got.read.startswith("0 read"),
    }


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    return Result(details=["This tool only reports. Nothing was written."])


register(Task(
    name="library",
    fold_groups=True,
    line="Every folder, and how much of the work on it is finished.",
    reads=('library', 'raw', 'previews'),
    title="Library",
    summary="Shows every folder in the library and what has been done to it. "
            "Nothing is changed.",
    icon="tree",
    # the first thing you do is look
    order=5,
    writes=False,
    options=[
        Folder("folder", "Library",
               help="The library to show. It is read, never written. Every "
                    "column is worked out from the files as they are now, so a "
                    "folder moved in File Station keeps its counts.", setting="library"),
        Folders("exclude", "Hide from this view", default="",
               help="Folders left out of this view only, separated by "
                    "commas. A name such as Archive hides every folder with "
                    "that name. A path hides that one folder and everything "
                    "under it. Nothing is hidden from the tools that do "
                    "work. For that, use Setup > Skip everywhere."),
        Choice("only", "Show", default="all", choices=ONLY, tabs=True,
               help="Which folders to list. 'Unfinished' shows shoots that "
                    "are half geotagged or half separated, which look "
                    "finished in File Station."),
        Flag("mirror", "Trees from Setup", default=True,
             group="Trees compared",
             help="On, the tree boxes below are ignored and the trees come "
                  "from Setup. Off, the folders you type below are compared "
                  "against the library for this view only."),
        Folder("raw", "RAW tree", tree=True, default="", must_exist=False, setting="raw",
               group="Trees compared", advanced=True,
               help="The top of the RAW tree, compared against the library "
                    "to see which shoots have their RAW files separated. "
                    "Blank skips that check. Ignored while Trees from Setup "
                    "is on."),
        Folder("previews", "Previews tree", tree=True, default="", must_exist=False,
               setting="previews", group="Trees compared", advanced=True,
               help="The top of the previews tree, compared against the "
                    "library to see which shoots have previews. Blank skips "
                    "that check. Ignored while Trees from Setup is on."),
        Folder("video", "Video tree", tree=True, default="", must_exist=False,
               setting="video", group="Trees compared", advanced=True,
               help="The top of the video tree, compared against the library "
                    "to see which shoots have their videos separated. Blank "
                    "skips that check. Ignored while Trees from Setup is on."),
        Flag("charts", "Draw the charts", default=True, group="Advanced",
             advanced=True,
             help="Draws the dashboard at the top. Every photo is read once, "
                  "and the result is cached and shared with Search and "
                  "Storage. On by default."),
        Flag("rescan", "Read every folder again", group="Trees compared",
             advanced=True,
             help="Reads every folder again instead of only the folders "
                  "whose contents changed. Use it after editing photos with "
                  "another program, so the columns are brought up to date."),
    ],
    plan=plan,
    apply=apply,
))
