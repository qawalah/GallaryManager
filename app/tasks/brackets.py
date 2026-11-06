"""Show what the bracket settings do to a folder - and mark the sets it finds.

This used to be a feature of its own, which was a mistake. Nobody wants to *find
brackets*; they want previews and culls that treat a set as one shot. So it sits
under Setup, beside the settings it demonstrates, and everything else reads those
settings rather than carrying its own.

**With the tag box empty it still writes nothing** - it exists so that "will this
group my shoot the way I shot it" is a question you can look at the answer to
before it decides what gets a preview and what gets put aside.

**With a word in the box it marks every frame of every set with it**, in a
sidecar and inside the JPEG, so a bracket is one search away in Lightroom, in
Explorer, and on the tablet - where the preview that stands for the set carries
the same word (Make previews puts it there).

The negatives are marked too when a RAW tree is given. A tag on the JPEG and
nothing on the ARW means the set is findable in one program and invisible in the
one you actually develop in.
"""

from __future__ import annotations

import os

from app.grouping import sets_for
from app.registry import Flag, Folder, Option, Plan, Result, Row, Task, register
from core import facts
from core import settings as S
from core import tagwrite, walk
from core.pairs import build_index, find_partner
from core.photo import read_capture


def plan(opts) -> Plan:
    p = Plan(task="brackets")
    folder = opts["folder"]
    tag = str(opts.get("tag") or "").strip()
    raw_root = str(opts.get("raw") or "").strip()
    if not folder or not os.path.isdir(folder):
        p.blocked = f"There is no folder at {folder!r}"
        return p

    found = walk.walk(folder)
    for path, why in found.errors:
        p.errors.append(f"could not read {path}: {why}")

    raw_index = None
    if tag and raw_root and os.path.isdir(raw_root):
        got_raw = walk.walk(raw_root)
        for path, why in got_raw.errors:
            p.errors.append(f"could not read {path}: {why}")
        raw_index = build_index(got_raw.files, want=("raw",))

    # A report until a word is typed in. Offering "Apply" for a report, or
    # withholding it when there IS something to write, are both lies about what
    # the button does - so the plan says which of the two this run is.
    p.writes = bool(tag)
    p.columns = ["Set", "Frames", "Exposure bias", "Keeps", "How sure", "Tag"]

    facts_for = facts.reader()
    got = sets_for(found.files, {"brackets": True}, p, reader=facts_for)
    in_sets = 0
    negatives = 0
    for s in got.sets:
        in_sets += s.size
        evs = ", ".join(f"{e:+g}" for e in s.evs) if s.evs else "no bias recorded"
        marks = [m.path for m in s.members]
        if raw_index is not None:
            for m in s.members:
                partner = find_partner(m.path, read_capture(m.path), raw_index)
                if partner.jpeg:
                    marks.append(partner.jpeg)
                    negatives += 1
        p.rows.append(Row(
            what=s.confidence, name=s.label(), source=s.members[0].path,
            target=s.representative.path,
            detail=f"{s.size} frames [{evs}]   keeps {s.representative.name}   {s.why}",
            cells=[f"{s.size}", evs, s.representative.name, s.why,
                   (f"{tag} on {len(marks)} file(s)" if tag else "nothing written")],
            approximate=(s.confidence == "probable"),
            data={"paths": [m.path for m in s.members], "mark": marks, "tag": tag,
                  "representative": s.representative.path}))

    saved = S.load()
    facts_for.save()
    p.stats = [
        ("Files opened", facts_for.said()),
        ("Photos examined", f"{got.examined:,}"),
        ("Bracket sets found", f"{len(got.sets):,}"),
        ("  certain", f"{got.certain:,}"),
        ("  probable (bracketed by hand)", f"{got.probable:,}"),
        ("Frames inside a set", f"{in_sets:,}"),
        ("Loose frames", f"{got.examined - in_sets:,}"),
        ("No capture time", f"{len(got.no_capture_time):,}"),
        ("Unreadable", f"{len(got.unreadable):,}"),
    ]
    p.notes.append(
        "A bracket is told from a burst by the exposure bias and nothing else: "
        "burst frames all share one bias, bracket frames cannot.")
    p.notes.append(
        "The frame kept is the metered one - bias zero. It is the one that gets a "
        "preview, carries the rating, and decides the whole set.")
    p.notes.append("Change these numbers on the Setup tab; previews, ratings and cull "
                   "all read them from there.")
    if tag:
        p.stats.insert(2, ("Frames to tag", f"{in_sets:,}"))
        if raw_index is not None:
            p.stats.insert(3, ("  their RAW files", f"{negatives:,}"))
        p.notes.append(
            f"Every frame of every set above will be marked '{tag}' - in a .xmp "
            f"beside it and, for a JPEG, inside the file as well, where Lightroom "
            f"and Windows Explorer both look. Nothing already on the file is "
            f"replaced; the word is added to whatever tags are there.")
        if raw_index is None and not raw_root:
            p.notes.append("No RAW tree was given, so only the frames in this folder "
                           "are marked. A tag on the JPEG and nothing on the RAW file "
                           "means the set is findable in one program and invisible in "
                           "the one you develop in.")
        p.notes.append("Make previews writes the same word onto the preview that "
                       "stands for a set, so it is one search away on the tablet too.")
    else:
        p.notes.append("Nothing will be written: this is a report. Type a word into "
                       "the tag box to mark the frames of every set found.")
    if got.probable:
        p.notes.append(
            f"{got.probable} set(s) are only PROBABLE: no bias was recorded, but the "
            f"shutter walked across frames taken seconds apart. That is what "
            f"bracketing by hand looks like - and also what three deliberate "
            f"exposures of a changing scene look like. Check these yourself.")
    if not got.sets:
        p.notes.append("Nothing here looks like a bracket. If you know there are "
                       "some, widen the gap in Setup, or turn on the hand-bracketed "
                       "sets, and look again.")
    if not saved.existed:
        p.notes.append("No settings have been saved yet, so these are the defaults.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    tag = str((plan.opts or {}).get("tag") or "").strip()
    if not tag:
        result.details.append("No tag was given, so this was a report. Nothing was "
                              "written.")
        return result

    marked = files = 0
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        status = "OK"
        for path in row.data.get("mark", []):
            got = tagwrite.add(path, [tag])
            files += 1
            if got["errors"]:
                result.failed += 1
                status = "FAILED: " + "; ".join(got["errors"])
                result.details.append(f"{os.path.basename(path)}\n    {status}")
            elif any(got[k] for k in ("sidecar", "xmp", "windows")):
                marked += 1
        result.done += 1
        if progress:
            progress(i, len(plan.rows), row.name, status)

    result.stats = [("Sets marked", f"{result.done:,}"),
                    ("Files given the tag", f"{marked:,} of {files:,}"),
                    ("Failed", f"{result.failed:,}")]
    if not result.details:
        result.details.append(
            f"Every frame of every set now carries '{tag}'. Make previews will put "
            f"the same word on the preview that stands for each set.")
    return result


register(Task(
    name="brackets",
    line="How the bracket settings group a folder, and a tag for each set.",
    verb="Tag",
    unit="bracketed frames",
    reads=('library',),
    title="Find brackets",
    summary="Shows how the bracket settings group a folder into sets, and "
            "can tag every frame of each set.",
    icon="layers",
    # Not a setting. What COUNTS as a bracket is one (the gap, the smallest set,
    # the keyword - all in Setup, where a decision you make once belongs); this
    # reads a folder and writes a tag onto what it found, which is a job. It sat
    # under Setup because the two were written together, and the only thing that
    # kept it there was nobody moving it.
    parent="cull",
    order=42,
    writes=True,
    options=[
        Folder("folder", "Folder to check", setting="library",
               help="The folder to group into bracket sets, a shoot or the "
                    "whole library. How a set is found is set in Setup > "
                    "Brackets."),
        Option("tag", "Tag to write", default="",
               kind="text",
               help="The tag written on every frame of every set found, in "
                    "the sidecar and inside the JPEG. Blank means the tool "
                    "only reports and writes nothing. Tags already on a file "
                    "are kept. Use the same word as Setup > Bracket tag, "
                    "which Make previews writes on the preview of a set."),
        Folder("raw", "RAW tree", tree=True, default="", must_exist=False,
               setting="raw",
               help="The top of the RAW tree, so each frame's RAW file gets "
                    "the tag too. A RAW file is matched by capture time, "
                    "camera and name, wherever it sits in the tree. Only "
                    "used when a tag is given."),
    ],
    plan=plan,
    apply=apply,
))
