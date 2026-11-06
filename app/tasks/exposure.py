"""Which of these are blown out, and which are too dark to hold anything.

The viewer has had a histogram for a long time, and it answers this one
photograph at a time, while you are already looking at it. This answers it for
four hundred you are not looking at.

**Measured, not guessed, and the numbers are shown.** How much of the frame is
at the very top of the range, how much is at the very bottom, and the average
brightness - then one word. You can move both thresholds, and the first run is
how you find the right ones for your own photographs: a concert and a beach
disagree about what "too dark" means and no default can be right for both.

**Read off the thumbnail.** A thumbnail is a faithful average of the frame -
that is what shrinking does - and they are already made and cached, so a second
pass over a folder costs nothing. Opening a 25MB RAW would make this the slowest
feature in the app and would not change one verdict.

**It will not throw anything away.** The most it does is write a tag, which is
the thing that makes these searchable afterwards - in here, in Lightroom and in
Synology Photos. A silhouette and a high-key portrait both land in this list,
because nothing here can know what you meant; that is exactly why it is a list
and not a cull.
"""

from __future__ import annotations

import os

from app.registry import Flag, Folder, Number, Option, Plan, Result, Row, Task, register
from core import exposure as E
from core import tagwrite, walk
from core.photo import kind


def plan(opts, progress=None) -> Plan:
    p = Plan(task="exposure")
    scan = str(opts.get("folder") or "").strip()
    if not scan:
        p.blocked = "Pick a folder to check."
        return p
    if not os.path.isdir(scan):
        p.blocked = f"There is no folder at {scan}"
        return p
    try:
        import PIL                                         # noqa: F401
    except ImportError:
        p.blocked = ("Pillow is not installed, and exposure cannot be measured "
                     "without reading the pixels.")
        return p

    over_pct = float(opts.get("over_pct") or E.OVER_PCT)
    under_pct = float(opts.get("under_pct") or E.UNDER_PCT)
    want_over = bool(opts.get("find_over", True))
    want_under = bool(opts.get("find_under", True))
    writing = bool(opts.get("write_tags", True))
    tag_over = str(opts.get("tag_over") or "").strip() if writing else ""
    tag_under = str(opts.get("tag_under") or "").strip() if writing else ""

    found = walk.walk(scan)
    for path, why in found.errors:
        p.errors.append(f"could not read {path}: {why}")
    photos = [f for f in sorted(found.files) if kind(f) in ("jpeg", "image")]

    p.columns = ["File", "What it is", "The numbers"]
    counts = {"over": 0, "under": 0, "ok": 0}
    for i, path in enumerate(photos, 1):
        if progress:
            progress(i, len(photos), os.path.basename(path))
        try:
            got = E.look_at(path, over_pct, under_pct)
        except E.Unreadable as why:
            p.skipped.append((path, str(why)))
            continue
        counts[got["verdict"]] = counts.get(got["verdict"], 0) + 1
        if got["verdict"] == "over" and not want_over:
            continue
        if got["verdict"] == "under" and not want_under:
            continue
        if got["verdict"] == "ok":
            continue
        word = tag_over if got["verdict"] == "over" else tag_under
        p.rows.append(Row(
            what=got["verdict"], name=os.path.basename(path), source=path,
            cells=["over exposed" if got["verdict"] == "over" else "under exposed",
                   E.describe(got)],
            data={"verdict": got["verdict"], "tag": word}))

    p.stats = [
        ("Photos read", f"{len(photos):,}"),
        ("Over exposed", f"{counts['over']:,}"),
        ("Under exposed", f"{counts['under']:,}"),
        ("Neither", f"{counts['ok']:,}"),
        ("Counted as over", f"{over_pct:g}% of the frame at the top"),
        ("Counted as under", f"{under_pct:g}% of the frame at the bottom"),
    ]
    words = [w for w in (tag_over if want_over else "",
                         tag_under if want_under else "") if w]
    if words:
        p.notes.append(f"Applying writes the tag{'s' if len(words) > 1 else ''} "
                       + " and ".join(repr(w) for w in words)
                       + " into the photos and their sidecars, so they can "
                         "be searched for here and in Lightroom.")
        p.impact = {"verb": "Tag", "unit": "photographs"}
    else:
        p.writes = False
        p.notes.append("Nothing is written: this is a report. Turn on \"Write "
                       "the tags\" to be able to find these again afterwards.")
    p.notes.append("A silhouette and a high-key portrait both appear here. "
                   "Nothing can know what you meant by a frame, which is why "
                   "this is a list and never a cull.")
    if not p.rows and photos:
        p.notes.append("Nothing crossed either threshold. Lower them if you "
                       "expected something - the numbers each frame scored are "
                       "the ones to aim at.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    tagged = {"over": 0, "under": 0}
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        if progress:
            progress(i, len(plan.rows), row.name)
        word = str(row.data.get("tag") or "")
        if not word:
            continue
        try:
            tagwrite.add(row.source, [word])
            tagged[row.data["verdict"]] = tagged.get(row.data["verdict"], 0) + 1
            result.done += 1
        except Exception as exc:                           # noqa: BLE001
            result.blame(row.source, exc)
    result.stats = [("Tagged as over exposed", f"{tagged.get('over', 0):,}"),
                    ("Tagged as under exposed", f"{tagged.get('under', 0):,}")]
    result.details.append(
        "The tags are in the photos themselves and in their sidecars, so "
        "Search here - and Lightroom, and Synology Photos - can find them.")
    return result


register(Task(
    name="exposure",
    fold_groups=True,
    verb="Tag",
    unit="photographs",
    line="Find the blown-out and the too-dark, with the numbers that say so.",
    title="Check exposure",
    tab="Check exposure",
    parent="cull",
    icon="hist",
    order=46,
    summary="Measures how much of each photo is pure white or pure black, "
            "and tags the ones over a limit you set.",
    options=[
        Folder("folder", "Folder to check", setting="library",
               help="The folder to measure, a shoot or the whole library. "
                    "Each photo is measured from its thumbnail, which "
                    "already exists, so a second run over the same folder is "
                    "fast."),
        Flag("find_over", "Find over-exposed", default=True,
             group="Checks",
             help="Looks for photos with too much pure white. Off skips this "
                  "end. On by default."),
        Flag("find_under", "Find under-exposed", default=True,
             group="Checks",
             help="Looks for photos with too much pure black. Off skips this "
                  "end. On by default."),
        Number("over_pct", "Over-exposed from (%)", default=E.OVER_PCT,
               minimum=0.1, maximum=100, group="Thresholds",
               help="A photo is over-exposed when at least this share of it "
                    "is pure white. 0.1 to 100, default 5. 5% is a lot of "
                    "white sky, and 1% is strict."),
        Number("under_pct", "Under-exposed from (%)", default=E.UNDER_PCT,
               minimum=0.1, maximum=100, group="Thresholds",
               help="A photo is under-exposed when at least this share of it "
                    "is pure black. 0.1 to 100, default 40. The default is "
                    "high because a night photo is often half black."),
        Flag("write_tags", "Write the tags", default=True,
             group="Tags",
             help="Writes the tags below on the photos found. Off only "
                  "reports, which is the right way to run it the first time "
                  "while you find the limits that suit your photos. On by "
                  "default."),
        Option("tag_over", "Over-exposed tag", default="overexposed",
               kind="text", group="Tags",
               help="The tag written on an over-exposed photo and its "
                    "sidecar, so Search and Lightroom can find it. Default "
                    "overexposed. Blank reports without writing."),
        Option("tag_under", "Under-exposed tag", default="underexposed",
               kind="text", group="Tags",
               help="The tag written on an under-exposed photo and its "
                    "sidecar, so Search and Lightroom can find it. Default "
                    "underexposed. Blank reports without writing."),
    ],
    plan=plan,
    apply=apply,
    writes=True,
    reads=("library",),
    undo="Tags are written into the files. Tag photos can take a tag off again "
         "the same way it puts one on.",
))
