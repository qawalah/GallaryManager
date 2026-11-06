"""Search - find photographs by what they are, not by where they were filed.

Everything else in this app starts from a folder, because a tree can only
answer one question: what is in here. The questions a photographer actually
has are not about folders. *The wide shots on the GH4 with no location.*
*Everything under f/2 from last summer.* *The four-star frames from Spain.*
Without this, each of those means opening thirty folders and looking.

Every box is optional and they all narrow together - there is no "or" here,
because that is not how anybody searches: you add conditions until the answer
is small enough to look at. Leave everything empty and you get the whole
library, which is the honest answer to asking nothing.

Nothing is written. The matches are listed with their thumbnails, a tap opens
the viewer and pages through them, and the whole set can be handed to the file
manager, where copy, move, download and delete work on exactly those files.

What a file cannot answer is counted separately and said. A photograph with no
capture time is not before 2020 and not after it either; a search that quietly
counts "cannot tell" as "no" is a search that looks complete while hiding the
files most worth knowing about.
"""

from __future__ import annotations

import os

from app.registry import (Choice, Flag, Folders, Number, Option, Plan, Result,
                          Row, Task, register)
from core import find
from core import settings as S
from core.store import store_path

PLACE_STORE = "places.tsv"
# Every match the search kept goes to the page: a chart that said 6,000 and a
# list that stopped at 400 of them read as two different answers. The page
# draws the table a few hundred rows at a time, so the length is its problem,
# not the reader's.
SHOW = find.CAP

KINDS = [("", "Photos and RAW files"), ("jpeg", "JPEGs only"),
         ("raw", "RAW files only"), ("video", "Videos only")]
LOCATED = [("", "Either"), ("yes", "Has a location"), ("no", "No location")]
COLOURS = [("", "Any"), ("red", "Red"), ("yellow", "Yellow"), ("green", "Green"),
           ("blue", "Blue"), ("purple", "Purple")]


def _folders(opts) -> list:
    out = [line.strip() for line in str(opts.get("folders") or "").splitlines()
           if line.strip()]
    if not out:
        saved = S.load()
        out = [str(saved["library"] or "").strip()]
    return [f for f in out if f]


def _ask_from(opts) -> find.Ask:
    """The form, as a search.

    A saved search is not a branch here: picking one fills the boxes on the
    page, so what runs is always what the form says. A hidden second source of
    truth - the form showing one thing and the run using another - is the kind
    of bug nobody can see.
    """
    kinds = str(opts.get("kinds") or "")
    return find.from_dict({
        "since": opts.get("since"), "until": opts.get("until"),
        "camera": opts.get("camera"), "lens": opts.get("lens"),
        "focal_from": opts.get("focal_from"), "focal_to": opts.get("focal_to"),
        "focal35": opts.get("focal35"),
        "f_from": opts.get("f_from"), "f_to": opts.get("f_to"),
        "iso_from": opts.get("iso_from"), "iso_to": opts.get("iso_to"),
        "faster_than": opts.get("faster_than"),
        "slower_than": opts.get("slower_than"),
        "stars_from": opts.get("stars_from"), "stars_to": opts.get("stars_to"),
        "colour": opts.get("colour"), "tags": opts.get("tags"),
        "all_tags": opts.get("all_tags"),
        "located": opts.get("located"), "country": opts.get("country"),
        "city": opts.get("city"), "name": opts.get("name"),
        "kinds": [kinds] if kinds else [],
        "missing": opts.get("missing"),
    })


def plan(opts, progress=None) -> Plan:
    p = Plan(task="search")
    folders = _folders(opts)
    if not folders:
        p.blocked = "Pick a folder to search, or fill in the library on Setup."
        return p
    try:
        ask = _ask_from(opts)
    except find.Refused as exc:
        p.blocked = str(exc)
        return p

    table = None
    if ask.needs_place():
        from core import places
        table = places.load(store_path(PLACE_STORE))
        if not table.rows:
            p.blocked = ("Searching by country or city needs the place table - "
                         "import it on the Place names tab first. Everything "
                         "else here works without it.")
            return p

    try:
        found = find.search(folders, ask, progress=progress, table=table)
    except find.Refused as exc:
        p.blocked = str(exc)
        return p

    p.columns = ["Photograph", "Taken", "Camera", "Exposure", "Marks"]
    for hit in found.hits[:SHOW]:
        marks = []
        if hit.stars:
            marks.append("★" * hit.stars)
        if hit.colour:
            marks.append(hit.colour)
        if hit.tags:
            marks.append(", ".join(hit.tags[:3]))
        if hit.place:
            marks.append(hit.place)
        elif hit.located:
            marks.append("placed")
        lens = " / ".join(x for x in (hit.camera, hit.lens) if x)
        p.rows.append(Row(
            what="found", name=hit.name, source=hit.path, size=hit.size,
            detail=lens or "nothing says how it was taken",
            cells=[hit.taken[:16] or "-", lens or "-", _exposure(hit),
                   " · ".join(marks) or "-"],
            data={"path": hit.path}))

    p.stats = [("Found", f"{found.matched:,}"),
               ("Looked at", f"{found.looked:,}"),
               ("Files opened", found.read)]
    asked = ask.asked()
    p.stats.insert(0, ("Asking for", "; ".join(asked) if asked else "everything"))
    if found.matched > len(found.hits[:SHOW]):
        p.notes.append(f"The first {len(found.hits[:SHOW]):,} are listed; "
                       f"{found.matched - len(found.hits[:SHOW]):,} more matched. "
                       f"Narrow it to see every one.")
    for why, n in sorted(found.unanswerable.items(), key=lambda kv: -kv[1]):
        p.skipped.append((f"{n:,} photograph(s)",
                          f"{why} - so they could not answer this search either "
                          f"way, and are neither in nor out"))
    if not found.hits:
        p.notes.append("Nothing matched. Every box narrows the answer, so the "
                       "usual cause is one box too many - empty one and look "
                       "again.")
    p.notes.append("Nothing is written. A tap on a thumbnail opens the viewer "
                   "and pages through the matches.")
    return p


def _exposure(hit) -> str:
    bits = []
    mm = hit.focal35 or hit.focal
    if mm:
        bits.append(f"{float(mm):.0f}mm" + ("eq" if hit.focal35 and not hit.focal
                                            else ""))
    if hit.shutter:
        bits.append(hit.shutter)
    if hit.fnumber:
        bits.append(f"f/{float(hit.fnumber):g}")
    if hit.iso:
        bits.append(f"ISO {hit.iso}")
    return " · ".join(bits) or "-"


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    return Result(details=["This tab only finds. Nothing was written."])


register(Task(
    name="search",
    line="Find photos by camera, lens, exposure, stars, tags or location.",
    reads=("library", "raw", "previews", "video", "develop"),
    title="Search",
    summary="Finds photos by camera, lens, exposure, date, stars, tags or "
            "location, in any combination.",
    icon="find",
    parent="library",
    tab="Search",
    order=6,
    writes=False,
    editor="search",
    fold_groups=True,
    options=[
        Folders("folders", "Folders to search", default="", setting="library",
                help="The folders to search, one per line. Everything inside "
                     "each one is searched. Blank means the library from "
                     "Setup."),

        Choice("kinds", "Which files", default="", choices=KINDS, tabs=True,
               group="File",
               help="Which kinds of file to search. The default searches "
                    "photos and RAW files together."),
        Option("name", "File name contains", default="", group="File",
               help="Text the file name must contain. Blank matches any "
                    "name."),
        Option("missing", "Missing fact", default="", group="File",
               help="Finds photos that do not record a fact, the 'not said' "
                    "row of a chart. Type one or more of taken, camera, "
                    "lens, focal, aperture, iso, shutter, colour, tags, "
                    "separated by commas. Blank ignores this."),

        Option("since", "Taken on or after", default="", group="Date",
               help="The earliest date to include. Type a year, a month or a "
                    "day: 2022, 2022-07 or 2022-07-14. Blank means no start "
                    "date."),
        Option("until", "Taken on or before", default="", group="Date",
               help="The latest date to include. Type a year, a month or a "
                    "day: 2022, 2022-07 or 2022-07-14. Blank means no end "
                    "date."),

        Option("camera", "Camera", default="", group="Camera and lens",
               help="Part of the camera name is enough, for example GH4 or "
                    "A7C. Blank means any camera."),
        Option("lens", "Lens", default="", group="Camera and lens",
               help="Part of the lens name is enough, for example 25/F1.7. "
                    "Blank means any lens."),
        Number("focal_from", "Focal length from (mm)", default="",
               group="Camera and lens",
               help="The shortest focal length to include, in millimetres. "
                    "Blank means no lower limit."),
        Number("focal_to", "Focal length to (mm)", default="", group="Camera and lens",
               help="The longest focal length to include, in millimetres. "
                    "Blank means no upper limit."),
        Flag("focal35", "Full-frame focal length", default=False,
             group="Camera and lens",
             help="Compares focal lengths as full-frame equivalents, so 25mm "
                  "on a GH4 counts as 50mm and the numbers mean the same on "
                  "every camera. A photo that does not record the equivalent "
                  "cannot be compared, so it is left out and counted."),

        Number("f_from", "Aperture from f/", default="", group="Exposure",
               help="The widest aperture to include, as the f-number, for "
                    "example 1.7. Blank means no limit."),
        Number("f_to", "Aperture to f/", default="", group="Exposure",
               help="The narrowest aperture to include, as the f-number, for "
                    "example 8. Blank means no limit."),
        Number("iso_from", "ISO from", default="", group="Exposure",
               help="The lowest ISO to include. Blank means no lower limit."),
        Number("iso_to", "ISO to", default="", group="Exposure",
               help="The highest ISO to include. Blank means no upper limit."),
        Option("faster_than", "Shutter faster than", default="",
               group="Exposure",
               help="Only shutter speeds faster than this, written as a "
                    "camera shows it: 1/250, or 2 for two seconds. Blank "
                    "means no limit."),
        Option("slower_than", "Shutter slower than", default="", group="Exposure",
               help="Only shutter speeds slower than this, written as a "
                    "camera shows it: 1/30, or 2 for two seconds. Blank "
                    "means no limit."),

        Number("stars_from", "Stars from", default="", group="Rating and tags",
               help="The lowest rating to include, 0 to 5. Blank means no "
                    "lower limit."),
        Number("stars_to", "Stars to", default="", group="Rating and tags",
               help="The highest rating to include, 0 to 5. Blank means no "
                    "upper limit."),
        Choice("colour", "Colour label", default="", choices=COLOURS,
               group="Rating and tags",
               help="Only photos carrying this colour label. Any means no "
                    "colour filter."),
        Option("tags", "Tags", default="", group="Rating and tags",
               help="Only photos carrying these tags, separated by commas. "
                    "Blank means no tag filter."),
        Flag("all_tags", "Must have all tags", default=False, group="Rating and tags",
             help="A photo must carry every tag listed. Off, carrying any "
                  "one of them is enough."),

        Choice("located", "Location", default="", choices=LOCATED, tabs=True,
               group="Place",
               help="Whether a photo must have a location. Either means no "
                    "filter."),
        Option("country", "Country", default="", group="Place",
               help="Only photos taken in this country. Needs the place "
                    "table from the Import place names tab. Blank means any "
                    "country."),
        Option("city", "City or town", default="", group="Place",
               help="Only photos taken in or near this city or town. Needs "
                    "the place table from the Import place names tab. Blank "
                    "means anywhere."),
    ],
    plan=plan,
    apply=apply,
))
