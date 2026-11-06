"""Break a folder up - by date, or by where the photographs were taken.

A card dumped straight in, a shoot split by lens, a decade of holidays in one
heap: whatever shape a folder is in now, this reads every photograph under it and
files each one into `2022/07`, or into `Italy/2022/Rome`, beneath that same
folder.

**Dates and places are one list of shapes, not two features.** They answer the
same question - how should this heap be broken up - and the answer for a travel
folder is usually "by where I was", while for a year of home photographs it is
"by month". Splitting them across two tabs would mean choosing the tab before
knowing the answer.

Place shapes need a location on the photograph and a table of place names
imported once (`core/places.py`, and the Place names tab). What that costs in
honesty is set out there: the nearest town in a table is a GUESS, so a town is
only claimed when one is close, a country only when a town is not absurdly far,
and a photograph that cannot be placed is left exactly where it is.

**How finely is yours to choose, folder by folder.** A quiet year is fine by
month; a fortnight abroad is thousands of frames in one folder, and by day or by
week it becomes a set of shoots you can work through. Nothing stops you sorting
one travel folder by day and the rest of the library by month - the task only
ever reshapes what you point it at.
Existing sub-folders are walked THROUGH, not preserved - a folder called
`100MSDCF` or `edited` is a fact about the card reader, not about the pictures.

Three decisions worth stating.

**The date comes from the photograph, never from the file.** A file's timestamp
says when it was last copied, which for most libraries is the day the disk was
replaced - and a whole library filed under one month, silently, is a far worse
outcome than a photo left alone. Anything without a readable capture time keeps
its position and is named.

**A shot moves as one thing.** The RAW is found by identity wherever it now
lives, the preview by position, sidecars travel with their file, and all of them
land in the same new place. Moving the JPEG alone would break every pair in the
folder and the damage would surface days later, in a task with nothing to do
with dates.

**The trees stay mirrored, or you are told they are not.** Only the tree you
point at is reshaped. If that is the library and its RAWs are elsewhere, the RAW
tree no longer matches - so the plan says how many RAWs that is, and Re-mirror
exists for exactly it.
"""

from __future__ import annotations

import datetime as _dt
import os
import shutil

from app.registry import (Choice, Flag, Folder, Number, Option, Pattern, Plan,
                          Result, Row, Task, register)
from core import moves
from core import naming, places, shoots, video, walk
from core import settings as _S
from core.pairs import build_index, find_partner
from core.paths import (common_root, companions, developed_beside,
                        developed_name, developed_target, ensure_folder, mirror,
                        relative_under, safe_target, skip_folder,
                        tidy_empty_folders, roots_of, under, without_nested)
from core.photo import VIDEO_COMPANION_EXTS, is_picture, kind, read_capture
from core.store import store_path

# What a folder ends up called. Dates and places in ONE list on purpose: they
# answer the same question - "how should this heap be broken up" - and splitting
# them across two tabs would mean choosing the tab before knowing the answer.
# The place shapes are written as COUNTRY and CITY rather than as Italy and Rome:
# an example is read as an example, and more than one person has wondered whether
# the folder would literally say Rome. The date shapes stay as real dates, since
# "2022 / 07" IS the format and spelling it as YEAR / MONTH would say less.
def shapes() -> list:
    """What the dropdown offers: a few ready-made, the ones you kept, your own.

    Called each time the form is drawn, so a pattern kept a minute ago is in
    the list without a restart.
    """
    out = [(key, naming.label(pat), group) for key, pat, group in naming.PRESETS]
    out += [(f"saved:{name}", f"{name}  -  {naming.label(pat)}", "Kept")
            for name, pat in naming.saved()]
    out.append(("custom", "Write my own pattern...", "Your own"))
    return out


class ShapeChoice(Choice):
    """A Choice that still understands every shape the app ever offered, so a
    flow saved last year keeps doing exactly what it did."""

    def describe(self):
        """...and that hands the page the PATTERN behind each ready-made one.

        So the pattern box can be a real box, always on screen, showing what the
        shape you picked actually does - rather than a field that only exists
        once you have found "Write my own pattern..." at the bottom of a
        dropdown. Picking a shape fills the box; typing in the box makes it
        yours.
        """
        d = super().describe()
        d["patterns"] = {key: naming.pattern_for(key)
                         for key, _label, _group in shapes()}
        return d

    def coerce(self, raw):
        text = str(raw or "")
        if text in naming.LEGACY or text.startswith("saved:") or text == "custom":
            return text
        return super().coerce(raw)


SHAPES = shapes()          # the list as it is at import - for tests and docs

PLACE_STORE = "places.tsv"

# A country we are sure of, a town we are not. Its own folder rather than a guess
# at the nearest name - and deliberately NOT one of the folders this app hides
# from its own scans, because there are real photographs in here and they should
# turn up in the Library like everything else.
UNSURE = "_Unsure"


def wants_place(shape: str, custom: str = "") -> bool:
    return naming.needs_place(naming.pattern_for(shape, custom))


WEEK_STARTS = [
    ("monday", "Monday"),
    ("sunday", "Sunday"),
    ("saturday", "Saturday"),
]
FIRST_DAY = {"monday": 0, "sunday": 6, "saturday": 5}

MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"]


def week_start(taken, starts_on: str = "monday"):
    """The date the week containing `taken` began."""
    first = FIRST_DAY.get(str(starts_on or "monday").lower(), 0)
    back = (taken.weekday() - first) % 7
    return (taken - _dt.timedelta(days=back)).date()


def folder_for(taken, shape: str, starts_on: str = "monday", place=None,
               pattern: str = "", camera: str = "", lens: str = "",
               shoot=None, hijri_shift: int = 0) -> str:
    """Where a photo taken then, and there, belongs - as a relative path.

    Returns "" when the pattern needs something this photo does not have - a
    place, a date. The caller must treat that as "leave this photograph exactly
    where it is": filing it under a guess is the one outcome worth avoiding, and
    an empty answer cannot be mistaken for a folder name.
    """
    pat = pattern or naming.pattern_for(shape)
    if place is not None:
        country = places.tidy_name(getattr(place, "country", "") or "")
        city = places.tidy_name(getattr(place, "city", "") or "")
        if city and not country:
            # A file naming a city and no country at all. Filing it under a
            # country worked out from somewhere else would be inventing the
            # bit that is missing, so the city stands in for it.
            country, city = city, ""
        place = places.Place(country=country, city=city,
                             code=getattr(place, "code", "") or "",
                             region=places.tidy_name(getattr(place, "region", "") or ""))
    values = naming.facts(taken, place, camera, lens, shoot,
                          FIRST_DAY.get(str(starts_on or "monday").lower(), 0),
                          hijri_shift)
    rel = naming.render(pat, values)
    return rel.replace("/", os.sep) if rel else ""


def plan(opts, progress=None) -> Plan:
    p = Plan(task="bydate")
    picked = without_nested(
        [line.strip() for line in str(opts.get("folder") or "").splitlines()
         if line.strip()])
    shape = str(opts.get("shape") or "year_month")
    pattern = naming.pattern_for(shape, opts.get("pattern"))
    starts_on = str(opts.get("week_starts") or "monday")
    raw_root = (opts.get("raw") or "").strip()
    prev_root = (opts.get("previews") or "").strip()

    if not picked:
        p.blocked = "Add at least one folder to sort."
        return p
    why = naming.problem(pattern) if pattern else (
        "That kept pattern is not there any more." if shape.startswith("saved:")
        else "Write a pattern - {year}/{month}, say.")
    if why:
        p.blocked = why
        return p
    for one in picked:
        if not os.path.isdir(one):
            p.blocked = f"There is no folder at {one!r}"
            return p

    # Several folders are sorted INTO THE FOLDER THEY ALL SIT IN, not into each
    # of them: picking January and February and getting `January/2022/07` beside
    # `February/2022/07` is not a sorted library, it is the same mess with more
    # folders in it. One folder is its own root, so nothing changes for the
    # ordinary case.
    scan = common_root(picked)
    if not scan or not os.path.isdir(scan):
        p.blocked = ("Those folders have nothing above them but the top of the "
                     "machine, so there is nowhere sensible to build the new "
                     "folders. Sort them in separate runs.")
        return p
    if len(picked) > 1:
        # The folder they all sit in has to be part of the library. Two folders
        # on different drives share only /tmp or C:\, and "sorted into the folder
        # they all sit in" would then mean building 2022/07 there - a plausible
        # answer to the arithmetic and a stupid one about photographs.
        home = str(_S.load()["library"] or "").strip()
        if home and not under(scan, home):
            p.blocked = (f"Those folders sit together in {scan}, which is not "
                         f"inside the library ({home}) - so that is where the new "
                         f"folders would be built. Sort them in separate runs, or "
                         f"pick folders from one library.")
            return p
        p.notes.append(
            f"{len(picked)} folders, sorted into {scan} - the folder they all sit "
            f"in. Everything under each of them is read; nothing outside them is "
            f"touched.")
    # Where the new folders are BUILT. Blank is the folder being sorted, which
    # is what this always did; set, it is any folder in the library - "file this
    # card's worth into Photos/2024", rather than into the card dump itself.
    into = str(opts.get("into") or "").strip()
    dest = scan
    if into:
        home_lib = str(_S.load()["library"] or "").strip()
        parent_of = os.path.dirname(into.rstrip("/\\")) or into
        if not os.path.isdir(into) and not os.path.isdir(parent_of):
            p.blocked = (f"There is no folder at {into!r}, and nothing above it "
                         f"either - so there is nowhere to build in.")
            return p
        if home_lib and not under(into, home_lib):
            p.blocked = (f"{into} is not inside the library ({home_lib}). The "
                         f"other trees mirror the library, so a shoot filed "
                         f"outside it would have no place in them.")
            return p
        for root, label in ((raw_root, "RAW tree"), (prev_root, "previews tree")):
            if root and (under(into, root) or under(root, into)):
                p.blocked = (f"{into} is inside the {label}, which is a mirror "
                             f"of the library rather than a place to file into.")
                return p
        dest = into
        p.notes.append(f"The new folders are built in {into}, not in the folder "
                       f"being sorted.")
    # What the other trees are a mirror OF. With Setup's trees mirrored, that
    # is the library itself - not the folder being sorted. It used to be the
    # folder being sorted, which is only the same thing when the whole library
    # is sorted at once: sort one card dump and its RAWs went to the TOP of the
    # RAW tree, `Photos Raw/2022/07`, instead of `Photos Raw/100MSDCF/2022/07`,
    # and its previews were looked for in the wrong place and quietly left
    # behind. Found by the tree preview, which drew the RAW heading where no
    # photograph was going.
    anchor = scan
    if opts.get("mirror"):
        lib_root = str(_S.load()["library"] or "").strip()
        if lib_root and under(scan, lib_root):
            anchor = lib_root
    for root, label in ((raw_root, "RAW tree"), (prev_root, "previews tree")):
        if root and any(under(one, root) or under(root, one) for one in picked):
            p.blocked = (f"The {label} is inside the folder being sorted (or the "
                         f"other way round). It would be reshaped as if it were the "
                         f"library, and then nothing would mirror anything.")
            return p

    by_place = naming.needs_place(pattern)
    hijri_shift = int(opts.get("hijri_shift") or 0)
    if naming.needs_hijri(pattern):
        from core import hijri as _hijri
        until = _hijri.known_until()
        p.notes.append(
            "Hijri months come from the announced first days this app knows, "
            "counted forward with the arithmetic calendar after the last one"
            + (f" ({until})." if until else ".")
            + " A photo taken within a day of a month's end can land in the "
              "month next door; add the start you use to hijri-starts.tsv in "
              "the config folder, or nudge it with 'Hijri shift (days)'.")
    by_date = naming.needs_date(pattern)
    table = places.Table()
    city_km = float(opts.get("city_within_km") or places.CITY_WITHIN_KM)
    country_km = float(opts.get("country_within_km") or places.COUNTRY_WITHIN_KM)
    at_least = int(opts.get("town_at_least") or 0)
    renames = places.read_renames(opts.get("place_names"))
    if by_place:
        table = places.load(store_path(PLACE_STORE))
        if not len(table):
            # Not blocked outright: a library catalogued in Lightroom carries its
            # own city and country, and that needs no table at all. But it is the
            # first thing on the plan, because for most libraries it means almost
            # nothing can be filed.
            p.notes.insert(0, "No place table has been imported, so only "
                              "photos that already carry a city or country "
                              "written into them can be filed. Import place names "
                              "(the tab beside this one) to place the rest by "
                              "their coordinates.")

    found = walk.walk(picked[0])
    for one in picked[1:]:
        more = walk.walk(one)
        found.files.extend(more.files)
        found.errors.extend(more.errors)
    for path, why in found.errors:
        p.errors.append(f"could not read {path}: {why}")

    raw_index = None
    if raw_root and os.path.isdir(raw_root):
        got = walk.walk(raw_root)
        for path, why in got.errors:
            p.errors.append(f"could not read {path}: {why}")
        raw_index = build_index(got.files, want=("raw",))

    # Which JPEG, if any, each RAW in the LIBRARY is the negative of.
    #
    # The bug this closes: a RAW has no EXIF this app can read (a .RW2 is not a
    # JPEG), so `read_capture` gives it no date, so it was skipped as "no
    # capture time" - while the JPEG beside it, with the same name, moved. The
    # shoot came apart, quietly, in the one feature that is supposed to keep it
    # together. RAWs in the RAW TREE were always handled; these were not.
    #
    # So a RAW with a JPEG of its own name in the same folder does not get filed
    # on its own at all: it goes wherever that JPEG goes.
    beside: dict = {}
    for f in found.files:
        if kind(f) == "raw":
            continue
        if not is_picture(f):
            continue
        key = (os.path.normcase(os.path.dirname(f)),
               os.path.normcase(os.path.splitext(os.path.basename(f))[0]))
        beside.setdefault(key, f)
    tagalong: list = []                # (the RAW, the JPEG it belongs to)

    moved = settled = undated = other = 0
    raws = previews = 0
    unplaced = unsure = told = 0
    clips: list = []                   # video, placed after the photographs
    landing: list = []                 # (where a photo is going, when it was taken)
    seen_places: dict = {}             # what each place folder ended up called
    seen_raw: set = set()
    # Every finished export already spoken for. A JPEG and its RAW sit beside
    # the same one and both would take it; the first to move wins, and the
    # second would otherwise plan a move of a file that is no longer there.
    claimed: set = set()
    known: dict = {}                  # coordinates already looked up, rounded
    files = sorted(found.files)
    todo: list = []                    # (path, kind, capture, place), read
    for i, path in enumerate(files, 1):
        if progress:
            progress(i, len(files), os.path.basename(path))
        k = kind(path)
        if k == "sidecar":
            continue                      # it travels with its file, not alone
        if os.path.splitext(path)[1].lower() in VIDEO_COMPANION_EXTS:
            # A proxy or a thumbnail. Like a sidecar, it travels with the clip it
            # belongs to and is never filed on its own - listing it here as well
            # put one file in the moving list AND in the left-alone list at the
            # same time, which is the app appearing to contradict itself.
            continue
        if k == "video":
            # Held back and dealt with after the photographs, because where a
            # clip goes depends on where the photographs went: it is filed with
            # the ones it was taken AMONG, and that is not known until they have
            # all been placed.
            clips.append(path)
            continue
        if not is_picture(path) and k != "raw":
            other += 1
            p.skipped.append((path,
                              "not a photo - left where it is"))
            continue

        if k == "raw":
            mate = beside.get((os.path.normcase(os.path.dirname(path)),
                               os.path.normcase(
                                   os.path.splitext(os.path.basename(path))[0])))
            if mate:
                # It follows its JPEG. Held back until every photograph has been
                # placed, because where it goes is wherever that one went - and
                # that is not known until the pass below has run.
                tagalong.append((path, mate))
                continue

        cap = read_capture(path)
        if not cap.taken and by_date:
            undated += 1
            p.skipped.append((
                path,
                "no capture time in the file, so there is no date to file it "
                "under - left exactly where it is"))
            continue

        where = None
        if by_place:
            where = _look_up(path, table, known, city_km, country_km, at_least,
                             renames)
            if not where:
                unplaced += 1
                p.skipped.append((path,
                                  f"{where.how or 'no location'} - left exactly "
                                  f"where it is"))
                continue
            if where.km is None:
                told += 1
            if not where.city:
                unsure += 1
            for name in (where.country, where.city):
                if name:
                    seen_places[name] = seen_places.get(name, 0) + 1

        todo.append((path, k, cap, where))

    # Where each photo goes is only decided now that every one has been read:
    # {range} names a folder by the whole shoot, and a shoot is only known once
    # every photograph in it is.
    landed: dict = {}                  # what moved, and into which folder
    spans = (naming.shoots_of([t[2].taken for t in todo],
                              float(opts.get("range_gap_hours") or 24))
             if naming.needs_range(pattern) else {})
    for path, k, cap, where in todo:
        rel = folder_for(cap.taken, shape, starts_on, where, pattern,
                         getattr(cap, "model", "") or "",
                         getattr(cap, "lens", "") or "",
                         spans.get(cap.taken), hijri_shift)
        if not rel:
            unplaced += 1
            p.skipped.append((path,
                              "nothing to file it under - left exactly where it is"))
            continue
        home = os.path.join(dest, rel)
        if cap.taken:
            landing.append((home, cap.taken))
        target = os.path.join(home, os.path.basename(path))
        if os.path.normcase(os.path.dirname(path)) == os.path.normcase(home):
            settled += 1
            continue

        moved += 1
        landed[os.path.normcase(path)] = home
        when = cap.taken.strftime("%Y-%m-%d") if cap.taken else "no date"
        why = f"taken {when}"
        if where is not None:
            why = f"{why}, {where.describe()}"
        _move(p, path, target, why, claimed)

        # the rest of the shot follows it
        if k != "raw" and raw_index is not None:
            m = find_partner(path, cap, raw_index)
            if m.jpeg and os.path.normcase(m.jpeg) not in seen_raw:
                seen_raw.add(os.path.normcase(m.jpeg))
                raws += 1
                _move(p, m.jpeg,
                      os.path.join(mirror(home, anchor, raw_root),
                                   os.path.basename(m.jpeg)),
                      f"the RAW file of {os.path.basename(path)}", claimed)
        if k != "raw" and prev_root and os.path.isdir(prev_root):
            was = mirror(path, anchor, prev_root)
            if os.path.isfile(was):
                previews += 1
                _move(p, was,
                      os.path.join(mirror(home, anchor, prev_root),
                                   os.path.basename(was)),
                      f"the preview of {os.path.basename(path)}", claimed)

    # ---- the negatives that were sitting in the library
    #
    # After the photographs, because each one goes where its own JPEG went. A
    # RAW whose JPEG did not move does not move either - it is already beside
    # it, which is the whole point.
    for raw_path, mate in tagalong:
        home = landed.get(os.path.normcase(mate))
        if home is None:
            settled += 1                   # its JPEG stayed; so does it
            continue
        raws += 1
        _move(p, raw_path, os.path.join(home, os.path.basename(raw_path)),
              f"the RAW file of {os.path.basename(mate)}", claimed)

    # ---- finished exports with nothing left to follow
    #
    # A developed version whose original has been culled, renamed by hand or
    # deleted cannot travel with anything, and it is invisible to every scan
    # this app makes. Left unsaid it is simply forgotten - so it is named here,
    # and nothing is done with it, because the answer depends on whether you
    # still want a finished photograph of something you threw away.
    into = developed_name()
    orphans = 0
    if into:
        for here, dirs, names in os.walk(scan, onerror=lambda e: None):
            if os.path.basename(here).strip().lower() != into.strip().lower():
                dirs[:] = [x for x in dirs if not skip_folder(x) or
                           x.strip().lower() == into.strip().lower()]
                continue
            dirs[:] = []
            parent = os.path.dirname(here)
            for name in sorted(names):
                stem = os.path.splitext(name)[0]
                stem = stem.rsplit("_", 1)[0] if (
                    "_" in stem and stem.rsplit("_", 1)[1].isdigit()) else stem
                if any(os.path.splitext(x)[0].lower() == stem.lower()
                       for x in os.listdir(parent)
                       if os.path.isfile(os.path.join(parent, x))):
                    continue
                orphans += 1
                if orphans <= 200:
                    p.skipped.append((
                        os.path.join(here, name),
                        "a finished export whose original is not in that folder "
                        "any more - culled, renamed by hand, or deleted. It "
                        "cannot travel with anything, so it is left exactly "
                        "where it is."))

    # ------------------------------------------------------------------ video
    #
    # A clip has no rating, no bracket and usually no location, so the only
    # honest way to file it with its shoot is the moment it was shot. Filed with
    # the photographs it was taken AMONG - by their DESTINATION, so a clip lands
    # in the folder those photographs are moving to rather than the one they are
    # leaving.
    windows = shoots.build(landing)
    near_hours = float(opts.get("near_hours") or shoots.NEAR_HOURS)
    shift = int(opts.get("shift_minutes") or 0)
    with_shoot = by_own_date = no_clue = 0
    for path in sorted(clips):
        if not opts.get("move_video", True):
            no_clue += 1
            p.skipped.append((path,
                              "video - left where it is, as asked"))
            continue
        shot = video.capture_of(path)
        when = video.local_time(shot, shift)
        hit = shoots.match(when, windows, near_hours) if windows else None
        if hit and hit.window:
            home = hit.window.key
            why = (f"with the photos going to "
                   f"{relative_under(home, scan) or os.path.basename(home)} - "
                   f"{hit.why}")
            with_shoot += 1
        elif when and not by_place:
            home = os.path.join(dest, folder_for(when, shape, starts_on,
                                                 pattern=pattern,
                                                 hijri_shift=hijri_shift))
            why = f"its own date - {shot.how}"
            by_own_date += 1
        else:
            no_clue += 1
            p.skipped.append((
                path,
                "video - " + (hit.why if hit and hit.why else
                              (shot.how or "nothing says when it was shot"))
                + (", and a video carries no place of its own" if by_place and when
                   else "") + " - left exactly where it is"))
            continue
        if os.path.normcase(os.path.dirname(path)) == os.path.normcase(home):
            settled += 1
            continue
        moved += 1
        _move(p, path, os.path.join(home, os.path.basename(path)), why)
        for side in _clip_companions(path, files):
            _move(p, side, os.path.join(home, os.path.basename(side)),
                  f"travels with {os.path.basename(path)}")

    p.columns = ["File", "Taken", "Where it was"]
    p.stats = [
        ("Photos examined", f"{moved + settled + undated + unplaced:,}"),
        ("To move", f"{moved:,}"),
        ("  their RAW files", f"{raws:,}"),
        ("  their previews", f"{previews:,}"),
        ("Already in the right folder", f"{settled:,}"),
        ("No capture time - left alone", f"{undated:,}"),
        ("Not photos - left alone", f"{other:,}"),
        ("Videos filed with their shoot", f"{with_shoot:,}"),
        ("Videos filed by their own date", f"{by_own_date:,}"),
        ("Videos left where they are", f"{no_clue:,}"),
        ("Files to move, sidecars included", f"{len(p.rows):,}"),
        ("Developed versions carried", f"{sum(1 for r in p.rows if r.what == 'developed'):,}"),
        ("  orphaned, left alone", f"{orphans:,}"),
        ("Folders unreadable", f"{len(found.errors):,}"),
    ]
    if by_place and seen_places:
        # The names it chose, with counts, editable on the page. A folder called
        # Marrakesh when you would have written Marrakech is not worth a bug
        # report and is worth fixing in one place before anything moves.
        p.picks = {
            "option": "place_names",
            "title": "Places found",
            "note": "Change a name and look again - every photo filed under "
                    "it follows. Keep the list in Setup to reuse it next time.",
            "items": [{"name": name, "count": n}
                      for name, n in sorted(seen_places.items(),
                                            key=lambda kv: (-kv[1], kv[0]))],
        }
    if by_place:
        p.stats.insert(5, ("No location - left alone", f"{unplaced:,}"))
        p.stats.insert(6, (f"Country only - into {UNSURE}", f"{unsure:,}"))
        p.stats.insert(7, ("Placed by what the file says", f"{told:,}"))
        p.notes.append(
            f"A country worked out from coordinates is nearly always right; a town "
            f"is only right when there is one nearby. So a town is claimed within "
            f"{city_km:.0f} km, the country alone out to {country_km:.0f} km, and "
            f"past that nothing is claimed and the photo stays where it is. "
            f"Every row says which town it was measured from and how far.")
        if len(table):
            p.notes.append(f"{len(table):,} towns on file"
                           + (f", read from {table.source}." if table.source else "."))
        if at_least:
            if not table.has_population:
                p.notes.insert(0, "The place table on file was imported by an older "
                                  "version and carries no population, so 'stick to "
                                  "bigger towns' cannot be applied. Import the "
                                  "cities file again on the Place names tab.")
            else:
                p.notes.append(
                    f"Only towns of {at_least:,} people or more are named, so a week "
                    f"in the hills is one folder rather than eleven hamlets. Where "
                    f"there is no such town nearby, the row says so and the country "
                    f"is used on its own.")
        if renames:
            p.notes.append("Renamed: " + ", ".join(f"{k} to {v}"
                                                   for k, v in sorted(renames.items())))
        if unplaced and not moved:
            p.blocked = ("Not one photo could be placed. Either they carry no "
                         "location at all - geotag them first - or no place table "
                         "has been imported, which is the tab beside this one.")
    _preview_tree(p, dest, raw_root, prev_root, anchor)
    p.notes.append("The date comes from the photo, never from the file. A "
                   "file's timestamp says when it was last copied, which for most "
                   "libraries is the day a disk was replaced - and a whole library "
                   "filed under one month is far worse than a photo left alone.")
    p.notes.append("Folders you already had are walked through, not kept: "
                   "'100MSDCF' is a fact about the card reader, not about the "
                   "photos. Any that empty out are tidied away afterwards.")
    if raw_index is None and raw_root:
        p.notes.append(f"There is no RAW tree at {raw_root!r}, so no RAW files can "
                       f"be moved with their photos.")
    if not raw_root:
        p.notes.append("No RAW tree was given. If this folder's RAWs live in one, "
                       "they will not follow - run 'Re-mirror RAWs' afterwards, "
                       "which finds each one by identity and puts it back in step.")
    if p.errors:
        p.blocked = (f"{len(p.errors)} folder(s) could not be read, so this is not "
                     f"the whole folder - and reshaping half of one leaves it in a "
                     f"state neither you nor the app can describe.")
    return p


def _preview_tree(p: Plan, dest: str, raw_root: str, prev_root: str,
                  anchor: str = "") -> None:
    """The folders this will make, with what lands in each - before anything moves.

    A list of four hundred "a.JPG -> 2022/07/a.JPG" lines is correct and says
    nothing about the SHAPE you are about to have. What you want to see is the
    tree: 2022/07 gets 143, 2022/08 gets 61, and there is one stray in 2019
    that is plainly a clock problem. So the rows are gathered under the folder
    they land in, one heading per new folder, closed until you open one.

    A shot's RAW and preview land in the same position in their own trees, so
    they are gathered under the same heading as the JPEG rather than scattered
    into three - "2022/07: 143 photos, 140 RAWs, 143 previews" is one decision.
    """
    # Each tree's rows are placed by where they sit relative to the matching
    # point in that tree: the photo's under `dest`, the RAW's and the preview's
    # under the mirror of `dest` - so all three land under ONE heading.
    base = anchor or dest
    roots = [(dest, "photo")]
    for root, label in ((raw_root, "RAW"), (prev_root, "preview")):
        if root:
            roots.append((mirror(dest, base, root), label))
    counts: dict = {}
    for row in p.rows:
        if not row.target:
            continue
        where = os.path.dirname(row.target)
        rel, what = "", "photo"
        for root, label in roots:
            if root and under(where, root):
                rel, what = relative_under(where, root), label
                break
        if not rel:
            continue
        rel = rel.replace("\\", "/")
        row.group = "to:" + rel
        slot = counts.setdefault(rel, {"photo": 0, "RAW": 0, "preview": 0,
                                       "size": 0, "new": not os.path.isdir(
                                           os.path.join(dest, rel))})
        slot[what] += 1
        slot["size"] += row.size or 0
    for rel in sorted(counts):
        c = counts[rel]
        bits = [f"{c['photo']:,} photo(s)"]
        if c["RAW"]:
            bits.append(f"{c['RAW']:,} RAW")
        if c["preview"]:
            bits.append(f"{c['preview']:,} preview(s)")
        p.groups.append({
            "key": "to:" + rel,
            "label": rel + ("  (new)" if c["new"] else ""),
            "cells": [", ".join(bits), ""],
            "note": ""})
    if counts:
        made = sum(1 for c in counts.values() if c["new"])
        p.stats.insert(0, ("Folders it will fill", f"{len(counts):,}"
                           + (f" ({made:,} new)" if made else "")))


def _look_up(path, table, known: dict, city_km: float, country_km: float,
             at_least: int = 0, renames: dict | None = None):
    """Where this photograph was, remembering answers by rounded coordinates.

    A shoot is hundreds of frames in one place, so the same nearest-town search
    would otherwise be run hundreds of times for one answer. Rounded to three
    decimals - about a hundred metres, far finer than any town boundary, so the
    cache can never merge two places that would have been named differently.
    """
    found = places.written_place(path)
    if found.city and found.country:
        return places.rename(found, renames)
    coords = places.coordinates_of(path)
    if coords is None:
        return places.rename(found, renames)
    key = (round(coords[0], 3), round(coords[1], 3))
    if key not in known:
        known[key] = places.from_coordinates(table, coords[0], coords[1],
                                             city_km, country_km, at_least)
    from_gps = known[key]
    if not found:
        return places.rename(from_gps, renames)
    if found.country and from_gps.country and found.country != from_gps.country:
        found.how = (f"{found.how}, though its coordinates are nearest "
                     f"{from_gps.city or from_gps.country}")
        return places.rename(found, renames)
    merged = places.Place(
        region=found.region or from_gps.region,
        country=found.country or from_gps.country,
        city=found.city or from_gps.city,
        code=found.code or from_gps.code,
        how=found.how if found.city else (from_gps.how or found.how),
        km=None if found.city else from_gps.km)
    return places.rename(merged, renames)


def _clip_companions(path: str, everything) -> list:
    """The proxy and thumbnail a camera writes beside a clip, by exact base name.

    The same rule as Separate video, and for the same reason: alone they are
    silent rubbish, and `GX010042.MP4` must not drag `GX010042 edit.LRV` along.
    """
    stem = os.path.splitext(path)[0]
    out = []
    for other in everything:
        if other == path:
            continue
        base, ext = os.path.splitext(other)
        if base == stem and ext.lower() in VIDEO_COMPANION_EXTS:
            out.append(other)
    return out


def _move(p: Plan, source: str, target: str, why: str, claimed=None) -> None:
    size = 0
    try:
        size = os.path.getsize(source)
    except OSError:
        pass
    p.rows.append(Row(what="move", name=os.path.basename(source), source=source,
                      target=target, size=size, detail=why,
                      cells=[c for c in (why.split(", ", 1) + [""])[:2]],
                      data={"from": source, "to": target}))

    # The finished versions come too.
    #
    # They are the one thing in a library that cannot be found again by looking:
    # an export shares its original's name, capture time and camera, which is
    # why it lives in a subfolder that every scan skips - and the price of that
    # is that nothing can re-match it later. Left behind, they sit in the shape
    # the library used to have, beside a folder the photographs have left.
    #
    # `claimed` is because a JPEG and its RAW both sit beside the same export
    # and both would otherwise take it: the first one to move wins, and the
    # second would plan a move of a file that is no longer there.
    into = developed_name()
    if into:
        for done in developed_beside(source, into):
            key = os.path.normcase(os.path.abspath(done))
            if claimed is not None:
                if key in claimed:
                    continue
                claimed.add(key)
            lands = developed_target(done, target, into)
            p.rows.append(Row(
                what="developed", name=os.path.basename(done), source=done,
                target=lands,
                detail=f"the developed version of {os.path.basename(source)}",
                cells=["", f"developed from {os.path.basename(source)}"],
                data={"from": done, "to": lands}))

    for side in companions(source):
        p.rows.append(Row(
            what="sidecar", name=os.path.basename(side), source=side,
            target=os.path.join(os.path.dirname(target), os.path.basename(side)),
            detail=f"travels with {os.path.basename(source)}",
            cells=["", f"travels with {os.path.basename(source)}"],
            data={"from": side,
                  "to": os.path.join(os.path.dirname(target),
                                     os.path.basename(side))}))


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result

    touched: set = set()
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        status = "OK"
        src, dst = row.data["from"], row.data["to"]
        try:
            if not os.path.isfile(src):
                raise FileNotFoundError("it is no longer there")
            moves.shift(result, src, dst)
            touched.add(os.path.dirname(src))
            result.done += 1
        except Exception as exc:                    # noqa: BLE001
            status = result.blame(row.name, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)

    removed = tidy_empty_folders(touched, stop_at=roots_of(plan.opts))
    result.stats = [("Files moved", f"{result.done:,}"),
                    ("Failed", f"{result.failed:,}"),
                    ("Empty folders tidied", f"{removed:,}")]
    if not result.details:
        result.details.append(
            "Every photo is under the year and month it was taken. Anything "
            "without a capture time is exactly where it was.")
    return result


register(Task(
    # The registry name stays `bydate` although the feature now sorts by place
    # too: it is what History has written against every run since this was built,
    # and renaming it would quietly orphan them.
    name="bydate",
    fold_groups=True,
    line="Break a folder up by date, or by the place it was taken.",
    verb="Move",
    unit="files",
    undo="Files are moved, not copied. Nothing is overwritten: a name "
         "already taken gets a number.",
    title="Sort into folders",
    summary="Moves photos into folders by date or place: year, month, week, "
            "day, country or city.",
    icon="calendar",
    # now the heap can be broken into folders
    order=20,
    options=[
        Folder("folder", "Folders to sort", setting="library", many=True,
               help="The folders to sort. Everything inside each one is "
                    "read, whatever sub-folders it has now. Those "
                    "sub-folders are walked through, not kept. Several "
                    "folders are sorted together into the folder that holds "
                    "them all."),
        Folder("into", "Destination folder", default="", must_exist=False,
               help="Where the new folders are built. Blank builds them "
                    "inside the folder being sorted. Pick another folder in "
                    "the library to file into it instead, for example "
                    "Photos/2024. Check the list shows the folders before "
                    "anything moves."),
        ShapeChoice("shape", "Folder pattern", default="year_month", choices=shapes,
               group="Pattern",
               help="The shape of the folders to make: a ready-made pattern, "
                    "one you kept, or your own. Place patterns need photos "
                    "with a location and the place table from the Import "
                    "place names tab."),
        Pattern("pattern", "Pattern", default="{year}/{month}",
                group="Pattern",
                help="The folder pattern as text. Variables go in braces and "
                     "/ starts a folder inside a folder, for example "
                     "{year}/{month} {monthname} - {city}. Your own text "
                     "around them is kept. A missing value is left out, "
                     "never guessed."),
        Number("hijri_shift", "Hijri shift (days)", default=0, minimum=-3,
               maximum=3, group="Pattern", advanced=True,
               help="Moves the Hijri calendar by this many days, for a "
                    "country whose months start a day earlier or later than "
                    "the table. -3 to 3, default 0. Only used by the {hijri} "
                    "variables."),
        Number("range_gap_hours", "New range after (hours)", default=24, minimum=1,
               maximum=24 * 14, group="Pattern", advanced=True,
               help="Hours without a photo that end one range and start the "
                    "next. 1 to 336, default 24. Only used by the {range} "
                    "variable: a trip is one range however many days it "
                    "lasts."),
        Choice("week_starts", "Weeks start on", default="monday",
               choices=WEEK_STARTS, group="Pattern", advanced=True,
               help="The first day of the week, for the week pattern. The "
                    "folder is named after the date the week began, so the "
                    "day you choose shows in the name."),
        Number("city_within_km", "Town within (km)", default=30,
               minimum=1, maximum=500, group="Places",
               help="The largest distance, in kilometres, between a photo "
                    "and a town for that town to be used as the folder name. "
                    "1 to 500, default 30. Further away, the photo goes into "
                    "_Unsure under its country. The table lists towns over "
                    "15,000 people."),
        Number("town_at_least", "Smallest town (people)", default=0,
               minimum=0, maximum=5_000_000, group="Places",
               help="Towns with fewer people than this are not used as "
                    "folder names. 0 to 5,000,000, default 0, which uses the "
                    "nearest town whatever its size and can give one folder "
                    "per village. 50,000 or more keeps to well-known places. "
                    "When no town that large is near, only the country is "
                    "used."),
        Option("place_names", "Rename places", default="", kind="text",
               setting="place_names", group="Places",
               help="Names to change before they are used as folder names, "
                    "one per line: Marrakesh = Marrakech. A line matches a "
                    "town or a country. The result lists every name found, "
                    "so run once and edit the list from there. From Setup by "
                    "default."),
        Number("country_within_km", "Country within (km)", default=200,
               minimum=1, maximum=2000, group="Places", advanced=True,
               help="The largest distance, in kilometres, between a photo "
                    "and the nearest known place for the country to be used. "
                    "1 to 2000, default 200. Further away, for example at "
                    "sea, the photo is left where it is."),

        Flag("move_video", "Move videos too",
             default=True, group="Videos",
             help="Moves videos with the photos. A video goes where the "
                  "photos taken at the same time go. With no photos near its "
                  "time it is sorted by its own date, and with no date it "
                  "stays where it is and is listed. On by default."),
        Number("near_hours", "Shoot window (hours)", default=12, minimum=0,
               maximum=240, group="Videos", advanced=True,
               help="How many hours after a shoot ended a video still "
                    "belongs to it. 0 to 240, default 12. A video taken "
                    "during the shoot always belongs to it."),
        Number("shift_minutes", "Shift video times (minutes)", default=0, minimum=-1440,
               maximum=1440, group="Videos", advanced=True,
               help="Minutes added to each video's recorded time before it "
                    "is matched to photos. -1440 to 1440, default 0. Only "
                    "needed when the camera writes video times in UTC and "
                    "photo times in local time: +180 lines up a UTC+3 video. "
                    "At 0 the time is used as written, and the row says when "
                    "the file gave no time zone."),

        Flag("mirror", "Trees from Setup", default=True,
             group="Companion files",
             help="On, the tree boxes below are ignored and the trees come "
                  "from Setup, so files land where every other tool puts "
                  "them. Off, the folders you type below are used for this "
                  "run only. Turning this off does not stop RAW files or "
                  "previews moving."),
        Folder("raw", "RAW tree", tree=True, default="", must_exist=False,
               setting="raw", group="Companion files",
               help="The top of the RAW tree. Each photo's RAW file is moved "
                    "to the matching new folder here. A RAW file is matched "
                    "by capture time, camera and name, wherever it sits in "
                    "the tree. Blank leaves RAW files alone."),
        Folder("previews", "Previews tree", tree=True, default="",
               must_exist=False, setting="previews", group="Companion files",
               help="The top of the previews tree. Each photo's preview is "
                    "moved to the matching new folder here. Previews are "
                    "matched by position. Blank leaves previews alone, and "
                    "you can remake them later."),
    ],
    plan=plan,
    apply=apply,
))
