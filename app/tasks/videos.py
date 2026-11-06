"""Pull the video out of a mixed library, into a tree that mirrors it.

Every camera in the house also shoots video, and it lands in the same folders as
the photographs. That is a problem in three ways at once, and none of them
announces itself:

- **A folder of clips is not a folder of photographs.** Previews cannot be made
  from it, ratings mean nothing on it, and a shoot that is half video reports
  numbers that are half about something else.
- **Clips are enormous.** A minute of 4K is a gigabyte; a folder of them is why
  a library that is "mostly photographs" will not fit on the tablet, the backup
  or the second NAS.
- **The tools do not agree what to do with them.** Synology Photos indexes
  video, Lightroom mostly does not, and a cull by rating skips every one of them
  silently because a clip has no rating to read.

So they get a tree of their own, in **the same shape as the library**, exactly
as the RAWs do. `Photos/2022/Spain` has its clips in `Videos/2022/Spain`, and
finding them later is the same gesture as finding a negative.

Three rules, and two of them are `unpair`'s because the problem is the same one:

**The mirror is anchored to the LIBRARY**, never to the folder you happened to
pick, or scanning one shoot and scanning the whole library would build two
different trees which then collide.

**A clip's companions travel with it.** GoPro writes a `.LRV` proxy and a `.THM`
thumbnail beside every clip; some cameras write an `.xml` of settings. Alone
they are silent rubbish, and left behind they are rubbish that makes a tidied
folder look untidy.

**Nothing is ever renamed and nothing is deleted.** A clip moves, keeping its
name and its position, so putting one back is a move.
"""

from __future__ import annotations

import os
import shutil

from app.registry import (Choice, Flag, Folder, Number, Plan, Result, Row, Task,
                          register)
from core import moves
from core import shoots, survey as SV, video, walk
from core.paths import (mirror_anchor, ensure_folder, mirror, relative_under,
                        safe_target, tidy_empty_folders, roots_of, under)
from core.photo import VIDEO_COMPANION_EXTS, is_video, kind
from core.store import store_path

# Shared with the Library tab on purpose: the expensive part of matching clips
# to shoots is reading when every photograph was taken, and the Library has read
# exactly that and written it down.
CACHE = "library.json"

# The fallback shapes, when no shoot matches. A short list rather than the sort
# task's nineteen: this is where a clip goes when nothing else could be worked
# out, and a wrong answer here is one you have to go looking for.
SHAPES = [
    ("year_month", "2022 / 07"),
    ("year", "2022"),
    ("flat_month", "2022-07"),
    ("flat_day", "2022-07-14"),
    ("same", "The folder it is in now"),
]



def _anchor(opts) -> str:
    """The library, from Setup - never a box on this tab.

    It used to be an Advanced option here, which asked a question with one
    right answer: the anchor is what makes a mirrored tree line up, and a
    different one typed on one tab and not another is how two features end up
    disagreeing about where a photograph belongs. Setup says it once.
    """
    from core import settings as _settings
    return (str(opts.get("library") or "").strip()
            or str(_settings.load()["library"] or "").strip())

def companions_of(path: str, everything) -> list[str]:
    """The proxy, thumbnail and settings files that belong to this clip.

    Matched on the base name inside the same folder, which is how every camera
    that writes them names them. Never by anything looser: a folder holding
    `GX010042.MP4` and `GX010042 edit.mp4` must not have one dragging the other
    along behind it.
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


def shoot_windows(library: str, progress=None):
    """(the shoots in the library, clips still in it, where the times came from).

    From the index when it has read the library. It already holds the capture
    time of every photograph, kept up to date in the background, and asking it
    costs nothing. The survey it used to come from opened every photograph in
    the library on the first run - over a network share that was long enough
    for "File by shoot" to look as if it never finished. The survey is still
    the answer for a library the index has not read yet.
    """
    import datetime as _dt
    from core import catalogue as CAT
    cat = CAT.shared()
    if cat.files and cat.covers([library]):
        if progress:
            progress(0, 0, "reading when the photos were taken, from the index")
        pairs, clips = [], 0
        for path, what, taken in cat.taken_under(library):
            if what == "video":
                clips += 1
                continue
            if what not in ("jpeg", "image") or not taken:
                continue
            try:
                pairs.append((os.path.dirname(path),
                              _dt.datetime.fromisoformat(taken)))
            except ValueError:
                continue
        return shoots.build(pairs), clips, "index"
    if progress:
        progress(0, 0, "reading when the photos were taken")
    seen = SV.survey(library, "", "", cache=SV.Cache(store_path(CACHE)),
                     progress=(lambda i, n, where: progress(i, n, where, "OK"))
                     if progress else None)
    clips = sum(getattr(st, "videos_here", 0) or 0
                for st in (seen.folders or {}).values())
    return shoots.from_survey(seen), clips, "survey"


def date_folder(when, shape: str) -> str:
    """Where a clip goes on its own date, when no shoot matched."""
    if not when or shape == "same":
        return ""
    if shape == "year":
        return f"{when.year}"
    if shape == "flat_month":
        return f"{when.year}-{when.month:02d}"
    if shape == "flat_day":
        return f"{when.year}-{when.month:02d}-{when.day:02d}"
    if shape == "year_month_day":
        # Offered by Re-mirror video, which shares this function. Without its
        # own branch it fell through to year/month without a word.
        return os.path.join(f"{when.year}", f"{when.month:02d}", f"{when.day:02d}")
    return os.path.join(f"{when.year}", f"{when.month:02d}")


def plan(opts, progress=None) -> Plan:
    p = Plan(task="videos")
    source = (opts.get("folder") or "").strip()
    video_root = (opts.get("video") or "").strip()
    library, refuse = mirror_anchor(_anchor(opts), source, opts.get('video') or '')
    if refuse:
        p.blocked = refuse
        return p
    by_time = bool(opts.get("by_time", True))
    near_hours = float(opts.get("near_hours") or shoots.NEAR_HOURS)
    shape = str(opts.get("shape") or "year_month")
    shift = int(opts.get("shift_minutes") or 0)

    if not source or not os.path.isdir(source):
        p.blocked = f"There is no folder at {source!r}"
        return p
    if not video_root:
        p.blocked = ("Say where the video tree is. It is the one place videos are "
                     "moved to, and without it there is nothing to mirror into.")
        return p
    if under(source, video_root) or under(video_root, library):
        p.blocked = ("The video tree is inside the library (or the other way "
                     "round). Videos would then be found again on the next run, in "
                     "their new home, and moved again.")
        return p
    if library != source and not under(source, library):
        p.blocked = f"{source!r} is not inside the library {library!r}."
        return p

    # Listing a whole library over a network share takes a while before there
    # is anything to count, and an empty bar that only said "reading" was
    # indistinguishable from one that had stopped.
    if progress:
        progress(0, 0, f"listing everything in {source}")
    found = walk.walk(source)
    for path, why in found.errors:
        p.errors.append(f"could not read {path}: {why}")

    # When the photographs were taken, folder by folder. Read from the Library's
    # own cache, so the second run costs almost nothing and the first costs what
    # opening the Library tab costs.
    windows = []
    if by_time:
        windows, _clips, _from = shoot_windows(library, progress)

    files = sorted(found.files)
    clips = extras = 0
    matched = dated = stayed = 0
    bytes_moved = 0
    p.columns = ["File", "What", "Size", "When", "Why there", "Goes with"]
    for i, path in enumerate(files, 1):
        if progress:
            progress(i, len(files), os.path.basename(path))
        if not is_video(path):
            continue
        clips += 1
        shot = video.capture_of(path) if by_time or shape != "same" else video.Clip()
        when = video.local_time(shot, shift)

        # In Abu's order: the shoot it was taken among, then its own date, then
        # the folder it is in now. Each row says WHICH of the three answered,
        # because a clip filed by the third rule and a clip filed by the first
        # are worth very different amounts of trust.
        hit = shoots.match(when, windows, near_hours) if windows else None
        if hit and hit.window:
            where = relative_under(hit.window.key, library)
            why = f"with the photos of {os.path.basename(hit.window.key)} - " \
                  f"{hit.why}"
            matched += 1
        else:
            where = date_folder(when, shape)
            if where:
                why = f"its own date - {shot.how}"
                dated += 1
            else:
                where = relative_under(os.path.dirname(path), library)
                why = ("the folder it is in now - "
                       + (hit.why if hit else shot.how or "no capture time"))
                stayed += 1
        target = os.path.join(video_root, where, os.path.basename(path))
        size = 0
        try:
            size = os.path.getsize(path)
        except OSError:
            pass
        bytes_moved += size
        p.rows.append(Row(
            what="video", name=os.path.basename(path), source=path, target=target,
            size=size, detail=f"{_gb(size)} - {why}",
            cells=["video", _gb(size),
                   when.strftime("%Y-%m-%d %H:%M") if when else "no time", why, ""],
            approximate=bool(when and not shot.zone_known),
            data={"from": path, "to": target}))
        for side in companions_of(path, files):
            extras += 1
            p.rows.append(Row(
                what="companion", name=os.path.basename(side), source=side,
                target=os.path.join(os.path.dirname(target),
                                    os.path.basename(side)),
                detail=f"travels with {os.path.basename(path)}",
                cells=[os.path.splitext(side)[1].lstrip(".").lower(), "", "", "",
                       os.path.basename(path)],
                data={"from": side,
                      "to": os.path.join(os.path.dirname(target),
                                         os.path.basename(side))}))

    already = 0
    if os.path.isdir(video_root):
        there = walk.walk(video_root)
        already = sum(1 for f in there.files if is_video(f))

    p.stats = [
        ("Files examined", f"{len(files):,}"),
        ("Videos to move", f"{clips:,}"),
        ("  filed with the shoot they were taken among", f"{matched:,}"),
        ("  filed by their own date", f"{dated:,}"),
        ("  kept where they are - nothing to go on", f"{stayed:,}"),
        ("  their proxies and thumbnails", f"{extras:,}"),
        ("They weigh", _gb(bytes_moved)),
        ("Videos already in the video tree", f"{already:,}"),
        ("Photos - left exactly where they are",
         f"{sum(1 for f in files if kind(f) in ('jpeg', 'image', 'raw')):,}"),
        ("Folders unreadable", f"{len(found.errors):,}"),
    ]
    p.notes.append("The video tree keeps the library's shape, so the videos of a "
                   "shoot sit in the folder that matches it - finding them later "
                   "is the same gesture as finding a RAW file.")
    if by_time:
        p.notes.append(
            f"A video is filed with the photos it was taken AMONG: whichever "
            f"folder of the library was being shot at that moment, or within "
            f"{near_hours:g} hours of it. That is what puts a video from the middle "
            f"of a card dump into the right shoot. Failing that it goes by its own "
            f"date, and failing that it keeps the position it has - and every row "
            f"says which of the three decided it.")
        p.notes.append(
            "When the photos of two shoots cover the same moment, neither is "
            "chosen: the row says so and the video keeps its position. A coin toss "
            "puts a video somewhere you will not find it.")
    if any(r.approximate for r in p.rows):
        p.notes.append(
            "Some videos carry a time with no timezone (the video header, which is "
            "UTC by the specification and local in a great many cameras). Those "
            "rows are marked. It matters most for the date fallback - a shoot "
            "match is a window hours wide and survives being a few hours out.")
    p.notes.append("Nothing is renamed and nothing is deleted. A video keeps its "
                   "name and its position, so putting one back is a move.")
    if not clips:
        p.notes.append("No video here. This tool only ever moves videos - "
                       "photos are not touched by it at all.")
    if p.errors:
        p.blocked = (f"{len(p.errors)} folder(s) could not be read, so this is not "
                     f"all the video there is. Moving half of it leaves the two "
                     f"trees describing different libraries.")
    return p


def _gb(n: int) -> str:
    if not n:
        return "0"
    if n >= 1e9:
        return f"{n / 1e9:.2f} GB"
    if n >= 1e6:
        return f"{n / 1e6:.0f} MB"
    return f"{n / 1e3:.0f} KB"


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result

    touched: set = set()
    total = len(plan.rows)
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        status = "OK"
        src, dst = row.data["from"], row.data["to"]
        # Said BEFORE the move, not only after it. A clip going to another drive
        # is a copy that can take minutes, and a bar reading "0 of 12" with no
        # name under it for all that time is what "it does nothing" looked like.
        if progress:
            progress(i - 1, total, row.name)

        def copying(done, size, name=row.name, at=i - 1):
            if progress:
                progress(at, total, f"{name} - {_gb(done)} of {_gb(size)}")

        try:
            if not os.path.isfile(src):
                raise FileNotFoundError("it is no longer there")
            moves.shift(result, src, dst, on_bytes=copying, cancelled=cancelled)
            touched.add(os.path.dirname(src))
            result.done += 1
        except moves.Interrupted:
            result.cancelled = True
            break
        except Exception as exc:                    # noqa: BLE001
            status = result.blame(row.name, exc)
        if progress:
            progress(i, total, row.name, status)

    # Re-mirror video shares this apply and has a "Tidy empty folders" box;
    # Separate video has none and has always tidied.
    removed = (tidy_empty_folders(touched, stop_at=roots_of(plan.opts))
               if plan.opts.get("tidy", True) else 0)
    result.stats = [("Files moved", f"{result.done:,}"),
                    ("Failed", f"{result.failed:,}"),
                    ("Empty folders tidied", f"{removed:,}")]
    if not result.details:
        result.details.append(
            "The library is photos now. The video tree beside it has the same "
            "shape, so a shoot's videos are in the folder that matches it.")
    return result


register(Task(
    name="videos",
    line="Move videos out of the library into a video tree with the "
         "same shape.",
    verb="Move",
    unit="clips",
    undo="The videos move into the video tree at the same position.",
    reads=('library',),
    moves_to=('video',),
    title="Separate video",
    summary="Moves videos out of the library into a video tree with the same "
            "folder shape.",
    icon="film",
    order=26,
    options=[
        Folder("folder", "Folder to scan", setting="library",
               help="The folder to move videos out of, a shoot or the whole "
                    "library. Only videos move. Every photo stays where it "
                    "is."),
        Flag("mirror", "Trees from Setup", default=True,
             help="On, the tree boxes below are ignored and the trees come "
                  "from Setup, so files land where every other tool puts "
                  "them. Off, the folders you type below are used for this "
                  "run only. Turning this off does not stop videos moving."),
        Folder("video", "Video tree", tree=True, must_exist=False,
               setting="video",
               help="The top of the video tree. It is made if it does not "
                    "exist. It must not be inside the library, or the videos "
                    "would be found and moved again on the next run."),
        Flag("by_time", "File by shoot",
             default=True, group="Destination",
             help="Puts each video in the video tree folder of the shoot "
                  "taken at the same time, wherever the video sits now. This "
                  "sorts out a card dump. The photo times come from the "
                  "index, so it is fast once the library has been read. On "
                  "by default."),
        Number("near_hours", "Shoot window (hours)", default=12, minimum=0,
               maximum=240, group="Destination",
               help="How many hours after a shoot ended a video still "
                    "belongs to it. 0 to 240, default 12. A video taken "
                    "during the shoot always belongs to it. Use the same "
                    "number in Re-mirror video."),
        Choice("shape", "Fallback folders", default="year_month",
               choices=SHAPES, group="Destination",
               help="Where a video goes when no photos were taken near the "
                    "same time. 'The folder it is in now' keeps the video's "
                    "current position, mirrored into the video tree."),
        Number("shift_minutes", "Shift video times (minutes)", default=0, minimum=-1440,
               maximum=1440, group="Destination", advanced=True,
               help="Minutes added to each video's recorded time before it "
                    "is matched to photos. -1440 to 1440, default 0. Only "
                    "needed when the camera writes video times in UTC and "
                    "photo times in local time: +180 lines up a UTC+3 video. "
                    "At 0 the time is used as written, and the row says when "
                    "the file gave no time zone."),
    ],
    plan=plan,
    apply=apply,
))
