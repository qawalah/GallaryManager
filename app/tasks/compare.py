"""Compare - two things about the library at once.

"Which apertures do I use" is mildly interesting. *Which apertures on which
lens*, or *how the stars fall by year*, or *which camera in which month* is the
question that changes what you do next - and no single list can answer it,
because the answer is a grid.

So: pick two, get the grid. Every photograph drops into one cell, the cell is
shaded by how many landed there, and the two edges carry their own totals so
the grid is never read without the shape of each axis beside it.

One pass over the library for both axes, through the same per-file cache as
Search, Storage and the Library dashboard. Nothing is written.

The honest parts, which are the reason this is not a spreadsheet:

* A photograph that cannot answer an axis lands in **not said** on that axis
  rather than being dropped, so every column adds up to the same library.
* **Tags are not one answer.** A photo tagged `spain, street` is counted in both
  columns; the grid then sums to more than the library, and the note says so
  rather than letting the totals look wrong.
* A grid larger than twelve by twelve is not a picture of anything, so the
  biggest rows and columns are kept and what was left out is counted.
"""

from __future__ import annotations

import os

from app.registry import Choice, Flag, Folders, Plan, Result, Row, Task, register
from core import settings as S
from core import stats as ST

MOST = 12

PAIRS = [(name, ST.DIMS[name][0]) for name in
         ("year", "month", "weekday", "hour", "camera", "lens", "focal",
         "aperture", "iso", "shutter", "stars", "colour", "tag", "kind",
         "located", "folder")]


def _folders(opts) -> list:
    out = [line.strip() for line in str(opts.get("folders") or "").splitlines()
           if line.strip()]
    if not out:
        out = [str(S.load()["library"] or "").strip()]
    return [f for f in out if f]


def plan(opts, progress=None) -> Plan:
    p = Plan(task="compare")
    folders = _folders(opts)
    if not folders or not os.path.isdir(folders[0]):
        p.blocked = "Pick a folder to look at, or fill in the library on Setup."
        return p
    down = str(opts.get("down") or "camera")
    across = str(opts.get("across") or "aperture")
    if down == across:
        p.blocked = ("Pick two different things - a grid of something against "
                     "itself is a diagonal line and says nothing.")
        return p

    got = ST.tally(folders, [down, across], progress=progress,
                   full_frame=bool(opts.get("focal35")),
                   cross=(down, across))
    grid = ST.trim(got.cross, MOST)
    if not grid or not grid["rows"] or not grid["cols"]:
        p.blocked = "Nothing in there to count."
        return p

    p.charts = {
        # Which folders these numbers are of, so a cell that leads to Search
        # leads to a search of the same folders rather than of everything.
        "folders": list(folders),
        "cross": grid,
        "charts": [dict({"kind": "bars", "dim": down, "unit": "photos",
                         "title": ST.DIMS[down][0]},
                        **got.counts[down].drawn(10)),
                   dict({"kind": "bars", "dim": across, "unit": "photos",
                         "title": ST.DIMS[across][0]},
                        **got.counts[across].drawn(10))],
    }

    # The same grid as a table, because a picture of numbers is not a substitute
    # for the numbers - and because a colour scale is not readable to everyone.
    p.columns = ["Down / across"] + list(grid["cols"]) + ["All"]
    for n, name in enumerate(grid["rows"]):
        row = grid["grid"][n]
        p.rows.append(Row(what="row", name=name, source="",
                          detail=f"{sum(row):,} photograph(s)",
                          cells=[f"{v:,}" if v else "-" for v in row]
                                + [f"{sum(row):,}"],
                          data={"row": name}))

    p.stats = [
        ("Rows", ST.DIMS[down][0]),
        ("Columns", ST.DIMS[across][0]),
        ("Photos", f"{got.photos:,}"),
        ("Biggest cell", f"{grid['most']:,}"),
        ("Files opened", got.read),
    ]
    if grid.get("left_out"):
        p.notes.append(f"The biggest {MOST} of each are shown; "
                       f"{grid['left_out']:,} photo(s) fall outside that "
                       f"corner of the grid.")
    if "tag" in (down, across):
        p.notes.append("A photo with three tags is counted in three "
                       "columns, so the grid adds up to more than the library. "
                       "That is what a tag is.")
    if got.capped:
        p.notes.append(f"Stopped at {ST.CAP:,} files.")
    p.notes.append("Nothing is written. The shading is only how many landed in "
                   "each cell - the numbers are in the table below it.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    return Result(details=["This tab only counts. Nothing was written."])


register(Task(
    name="compare",
    line="Two things about the library at once, as a grid.",
    reads=("library", "raw", "previews", "video"),
    title="Compare",
    summary="Draws a grid of one fact against another, such as aperture by "
            "lens. Nothing is changed.",
    icon="grid",
    parent="library",
    tab="Compare",
    order=9,
    writes=False,
    options=[
        Folders("folders", "Folders to read", default="", setting="library",
                help="The folders to read, one per line. Everything inside "
                     "each one is counted. Blank means the library from "
                     "Setup."),
        Choice("down", "Rows", default="camera", choices=PAIRS,
               help="The fact that makes the rows of the grid."),
        Choice("across", "Columns", default="aperture", choices=PAIRS,
               help="The fact that makes the columns of the grid."),
        Flag("focal35", "Full-frame focal length", default=False,
             group="Advanced", advanced=True,
             help="Uses the full-frame equivalent focal length, so 25mm on a "
                  "GH4 counts as 50mm. Only matters when rows or columns are "
                  "focal length. A photo that does not record the equivalent "
                  "is left out."),
    ],
    plan=plan,
    apply=apply,
))
