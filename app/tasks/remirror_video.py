"""Reshape the video tree to match whatever the library looks like now.

The same job Re-mirror RAWs does, and the tree that needs it most - because
nothing else ever rewrites it. Reorganise the library and the RAW tree can be
put right, the previews can simply be made again, and the video tree stays in
last year's shape for ever.

**A clip cannot be paired, so it has to be placed by TIME.** A RAW finds its
JPEG by capture time, camera and name; a clip has no partner in the library at
all - it was filed with the shoot it was taken AMONG, which is a statement about
a moment rather than about a file. So re-mirroring asks the same question
Separate video asks: which folder holds the photographs of that moment NOW? -
and moves the clip to the matching place in the video tree.

That is the same machinery (`core/shoots.py`) and the same evidence, which
matters: a clip filed by Separate video and the same clip re-mirrored a year
later must land in the same place, or the two features quietly disagree about
where a clip belongs.

**A clip whose moment no longer exists is left alone and named.** Its shoot may
have been deleted, or merged, or the photographs of that day may never have been
imported. Moving it somewhere plausible is how a gigabyte goes missing.
"""

from __future__ import annotations

import os

from app.registry import Choice, Flag, Folder, Number, Plan, Result, Row, Task, register
from app.tasks.videos import (_gb, apply, companions_of, date_folder,
                              shoot_windows)
from core import shoots, video, walk
from core.paths import relative_under, safe_target, under
from core.photo import is_video

CACHE = "library.json"

WHEN_LOST = [
    ("leave", "Leave it exactly where it is"),
    ("list", "Only list it - do not move it"),
]


def plan(opts, progress=None) -> Plan:
    p = Plan(task="remirror_video")
    library = (opts.get("library") or "").strip()
    video_root = (opts.get("video") or "").strip()
    near_hours = float(opts.get("near_hours") or shoots.NEAR_HOURS)
    shift = int(opts.get("shift_minutes") or 0)
    shape = str(opts.get("shape") or "year_month")

    for label, folder in (("library", library), ("video tree", video_root)):
        if not folder or not os.path.isdir(folder):
            p.blocked = f"There is no {label} at {folder!r}"
            return p
    if os.path.realpath(library) == os.path.realpath(video_root) \
            or under(video_root, library) or under(library, video_root):
        p.blocked = ("The video tree is inside the library, or the other way "
                     "round. They have to be separate trees for one to mirror "
                     "the other.")
        return p

    if progress:
        progress(0, 0, f"listing everything in {video_root}")
    found = walk.walk(video_root)
    for path, why in found.errors:
        p.errors.append(f"could not read {path}: {why}")

    windows, in_library, _from = shoot_windows(library, progress)

    files = sorted(found.files)
    clips = moved = already = lost = extras = 0
    bytes_moved = 0
    p.columns = ["Clip", "When", "Belongs with", "Size"]
    for i, path in enumerate(files, 1):
        if progress:
            progress(i, len(files), os.path.basename(path))
        if not is_video(path):
            continue
        clips += 1
        shot = video.capture_of(path)
        when = video.local_time(shot, shift)
        hit = shoots.match(when, windows, near_hours) if windows else None

        if hit and hit.window:
            where = relative_under(hit.window.key, library)
            why = (f"the photos of {os.path.basename(hit.window.key)} are "
                   f"there now - {hit.why}")
        else:
            where = date_folder(when, shape) if when else ""
            if not where:
                lost += 1
                p.skipped.append((
                    path,
                    "nothing in the library was taken anywhere near it and it has "
                    "no usable capture time of its own, so where it belongs now "
                    "is not known. Left exactly where it is - a gigabyte moved "
                    "somewhere plausible is a gigabyte you will not find."))
                continue
            why = f"nothing in the library matches its moment - filed by its own date"

        target = os.path.join(video_root, where, os.path.basename(path))
        if os.path.normcase(os.path.dirname(target)) == \
                os.path.normcase(os.path.dirname(path)):
            already += 1
            continue

        size = 0
        try:
            size = os.path.getsize(path)
        except OSError:
            pass
        bytes_moved += size
        moved += 1
        p.rows.append(Row(
            what="video", name=os.path.basename(path), source=path,
            target=target, size=size, detail=why,
            cells=[when.strftime("%Y-%m-%d %H:%M") if when else "no time",
                   why, _gb(size)],
            approximate=bool(when and not shot.zone_known),
            data={"from": path, "to": target}))
        for side in companions_of(path, files):
            extras += 1
            side_target = os.path.join(video_root, where, os.path.basename(side))
            p.rows.append(Row(
                what="sidecar", name=os.path.basename(side), source=side,
                target=side_target,
                detail=f"travels with {os.path.basename(path)}",
                cells=["", f"travels with {os.path.basename(path)}", ""],
                data={"from": side, "to": side_target}))

    p.stats = [
        ("Videos in the video tree", f"{clips:,}"),
        ("Already in the right place", f"{already:,}"),
        ("TO MOVE", f"{moved:,}"),
        ("They weigh", _gb(bytes_moved)),
        ("Files to move, companions included", f"{len(p.rows):,}"),
        ("Left alone - moment unknown", f"{lost:,}"),
        ("Shoots found in the library", f"{len(windows):,}"),
    ]
    if not clips and in_library:
        # Said first, because it is the answer to "I pressed it and nothing
        # happened": the clips are still in the library, and this only ever
        # rearranges the video tree.
        p.notes.append(
            f"The video tree has no videos in it yet, and the library still has "
            f"{in_library:,}. Separate video is what moves videos out of the "
            f"library into the video tree; this only rearranges the videos "
            f"already there.")
    p.notes.append(
        "The library is never changed. Only the video tree is reshaped to match "
        "it - the same direction as Re-mirror RAWs, and for the same reason: "
        "the library is the truth.")
    p.notes.append(
        "A video has no partner in the library to be paired with, so it is placed "
        "by the moment it was shot - which folder holds the photos of that "
        "time NOW. That is the same question Separate video asks, deliberately: "
        "a video filed then and re-mirrored now must land in the same place.")
    p.notes.append(
        "This is the tree that needs it most. A RAW tree can be re-mirrored, "
        "previews can simply be made again - nothing else ever rewrites the "
        "video tree, so a reorganised library leaves it wrong for good.")
    if lost:
        p.notes.append(
            f"{lost} video(s) could not be placed: nothing in the library was "
            f"taken near them and they carry no usable time of their own. They "
            f"are named above and left exactly where they are.")
    if not windows:
        p.notes.append(
            "No shoots were found in the library at all, so every video fell back "
            "to its own date. If that is not what you expected, open the Library "
            "tab first - this reads the same survey it does.")
    if p.errors:
        p.blocked = (f"{len(p.errors)} folder(s) could not be read, so where a "
                     f"video belongs might be in one of them. Nothing will move "
                     f"until that is fixed.")
    return p


register(Task(
    name="remirror_video",
    line="Move each video to where the photos of its moment now live.",
    verb="Move",
    unit="clips",
    undo="Only the position changes - nothing leaves the video tree.",
    reads=('library', 'video'),
    moves_to=('video',),
    title="Re-mirror video",
    summary="Moves each video to the place in the video tree that matches "
            "the photos taken at the same time.",
    icon="mirror",
    parent="videos",
    tab="Re-mirror video",
    order=27,
    options=[
        Folder("library", "Library", tree=True, setting="library",
               help="The library, read only. Where the photos are now "
                    "decides where each video goes."),
        Folder("video", "Video tree", tree=True, setting="video",
               help="The top of the video tree. Videos are only moved within "
                    "it."),
        Number("near_hours", "Shoot window (hours)",
               default=shoots.NEAR_HOURS, minimum=0, maximum=240,
               group="Matching", advanced=True,
               help="How many hours after a shoot ended a video still "
                    "belongs to it. 0 to 240, default 12. Use the same number "
                    "as Separate video, or the two tools will disagree about "
                    "where a video belongs."),
        Choice("shape", "Fallback folders", default="year_month",
               choices=[("year_month", "Year / month"), ("year", "Year"),
                        ("year_month_day", "Year / month / day")],
               group="Matching", advanced=True,
               help="Where a video goes when no photos were taken near the "
                    "same time. Check the list says which rule decided each "
                    "video."),
        Number("shift_minutes", "Shift video times (minutes)", default=0,
               minimum=-1440, maximum=1440, group="Matching", advanced=True,
               help="Minutes added to each video's recorded time before "
                    "matching, for a camera whose clock was set to the wrong "
                    "time zone. -1440 to 1440, default 0. Use the same "
                    "number as Separate video."),
        Flag("tidy", "Tidy empty folders", default=True,
             group="Matching", advanced=True,
             help="Removes a folder that this run has emptied. Only folders "
                  "this run emptied itself are removed, never a folder that "
                  "still holds anything. On by default."),
    ],
    plan=plan,
    apply=apply,
))
