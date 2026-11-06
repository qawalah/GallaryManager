"""Correct a camera clock across a whole shoot, from one photo you got right.

The situation this exists for: the battery came out, or you crossed two time
zones and never touched the camera, and now a day's shooting is filed under the
wrong date. It sorts wrongly beside the phone's photos, and it cannot be matched
against a timeline, because every comparison this app makes about *where* you
were starts from *when* the shutter fired.

You do not work out the offset. You take one photo you can date - usually the
first of the day - say what time it was really taken, and everything else in the
folder moves by the same amount. The gaps between frames are preserved exactly,
because a clock that is wrong is wrong by a constant: it did not also run fast.

Two things it insists on:

**THE RAWS MOVE TOO.** A RAW is tied to its JPEG by capture time. Retime the
JPEGs of a shoot and leave the RAWs on the old clock and every pair in it breaks
at once - and it surfaces much later, as RAWs that look orphaned, in a task that
has nothing to do with clocks. A RAW is never opened for writing, so its
corrected time goes in the .xmp beside it, which is where every other tool looks.

**THE WHOLE FOLDER, OR NONE OF IT.** A half-applied offset is worse than no
offset: the shoot is then in two different times and nothing about the mixture is
recoverable without knowing which half moved.
"""

from __future__ import annotations

import datetime as dt
import os
import shutil

from app.registry import FilePath, Choice, Flag, Folder, Number, Option, Plan, Result, Row, Task, register
from core import perms
from core import walk
from core.exifwrite import set_datetime
from core.pairs import build_index, find_partner
from core.paths import ensure_folder, is_ours
from core.photo import is_picture, kind, read_capture

BACKUP = "_BeforeRetime"

MODES = [
    ("photo", "From one photo's real time"),
    ("amount", "By a fixed amount"),
]

FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S",
           "%Y-%m-%dT%H:%M", "%Y:%m:%d %H:%M:%S", "%d/%m/%Y %H:%M:%S",
           "%d/%m/%Y %H:%M", "%Y-%m-%d")


def parse_when(text: str):
    """A date and time as a person would type one. None when it is not one."""
    text = (text or "").strip().replace("  ", " ")
    for form in FORMATS:
        try:
            return dt.datetime.strptime(text, form)
        except ValueError:
            continue
    return None


def say_offset(delta: dt.timedelta) -> str:
    """A shift in words, because "-25200 seconds" tells you nothing."""
    total = int(round(delta.total_seconds()))
    if total == 0:
        return "no change at all"
    sign = "forward" if total > 0 else "back"
    total = abs(total)
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, seconds = divmod(rest, 60)
    bits = [f"{n} {word}{'s' if n != 1 else ''}"
            for n, word in ((days, "day"), (hours, "hour"),
                            (minutes, "minute"), (seconds, "second")) if n]
    return f"{sign} by " + ", ".join(bits)


def _reference(opts, pictures, p: Plan):
    """The photo the correction is measured from, and what it currently says."""
    given = (opts.get("reference") or "").strip()
    wanted = given.lower()
    if wanted and ("/" in given or "\\" in given):
        # A whole path: what the page's file picker and the command line hand
        # over. Compared as a path, so two photographs of the same name in
        # different subfolders cannot be confused with each other.
        want = os.path.normcase(os.path.abspath(given))
        for path, cap in pictures:
            if os.path.normcase(os.path.abspath(path)) == want:
                return path, cap
        p.blocked = (f"{given!r} is not one of the photos in that folder. Pick "
                     f"the reference from inside the folder being corrected, or "
                     f"leave it blank to use the earliest photo.")
        return None, None
    if wanted:
        for path, cap in pictures:
            name = os.path.basename(path).lower()
            if name == wanted or os.path.splitext(name)[0] == os.path.splitext(wanted)[0]:
                return path, cap
        p.blocked = (f"There is no photo called {opts['reference']!r} in that folder. "
                     f"Leave it blank to use the earliest photo instead.")
        return None, None
    # earliest by the clock as it stands, which is the one you would have opened
    dated = [(path, cap) for path, cap in pictures if cap.taken]
    if not dated:
        p.blocked = "None of the photos in that folder carry a capture time."
        return None, None
    return min(dated, key=lambda pc: pc[1].taken)


def plan(opts) -> Plan:
    p = Plan(task="retime")
    folder = opts["folder"]
    if not folder:
        p.blocked = "Say which folder to correct."
        return p
    if not os.path.isdir(folder):
        p.blocked = f"There is no folder at {folder!r}"
        return p

    found = walk.walk(folder)
    for path, why in found.errors:
        p.errors.append(f"could not read {path}: {why}")

    pictures, no_time = [], 0
    for path in sorted(found.files):
        if not is_picture(path):
            continue
        cap = read_capture(path)
        if not cap.taken:
            no_time += 1
            p.skipped.append((path,
                              "no capture time in the file - nothing to correct"))
            continue
        pictures.append((path, cap))

    if not pictures:
        p.blocked = "No photos with a capture time were found in that folder."
        return p

    # ------------------------------------------------------ what the shift is
    if opts["mode"] == "amount":
        delta = dt.timedelta(days=int(opts["days"]), hours=int(opts["hours"]),
                             minutes=int(opts["minutes"]), seconds=int(opts["seconds"]))
        ref_path, ref_cap = _reference({}, pictures, p)
        if not delta:
            p.blocked = ("The amount is zero, so nothing would change. Set the days, "
                         "hours, minutes or seconds to shift by.")
            return p
        how = f"the amount you gave: {say_offset(delta)}"
    else:
        ref_path, ref_cap = _reference(opts, pictures, p)
        if ref_path is None:
            return p
        correct = parse_when(opts["correct_time"])
        if correct is None:
            p.blocked = (
                f"'{opts['correct_time']}' is not a date and time I can read. "
                f"{os.path.basename(ref_path)} currently says "
                f"{ref_cap.taken:%Y-%m-%d %H:%M:%S} - write the true one the same way.")
            return p
        delta = correct - ref_cap.taken
        if not delta:
            p.blocked = (f"{os.path.basename(ref_path)} already says "
                         f"{correct:%Y-%m-%d %H:%M:%S}, so nothing would change.")
            return p
        how = (f"{os.path.basename(ref_path)} says {ref_cap.taken:%Y-%m-%d %H:%M:%S} "
               f"and you say {correct:%Y-%m-%d %H:%M:%S}")

    # ------------------------------------------------------------- the RAWs
    raw_root = (opts.get("raw") or "").strip()
    raw_index = None
    if raw_root:
        if not os.path.isdir(raw_root):
            p.blocked = f"There is no RAW tree at {raw_root!r}"
            return p
        raw_walk = walk.walk(raw_root)
        for path, why in raw_walk.errors:
            p.errors.append(f"could not read {path}: {why}")
        raw_index = build_index(raw_walk.files, want=("raw",))

    raws = 0
    for path, cap in pictures:
        after = cap.taken + delta
        p.rows.append(Row(
            what="photo", name=os.path.basename(path), source=path,
            target=f"{after:%Y-%m-%d %H:%M:%S}",
            detail=f"{cap.taken:%Y-%m-%d %H:%M:%S}  ->  {after:%Y-%m-%d %H:%M:%S}",
            data={"path": path, "when": after.isoformat()}))
        if raw_index is not None:
            m = find_partner(path, cap, raw_index)
            if m.jpeg:
                raws += 1
                p.rows.append(Row(
                    what="RAW", name=os.path.basename(m.jpeg), source=m.jpeg,
                    target=f"{after:%Y-%m-%d %H:%M:%S}",
                    detail=f"follows {os.path.basename(path)}  (into the .xmp beside it)",
                    data={"path": m.jpeg, "when": after.isoformat()}))
            elif m.candidates > 1:
                p.skipped.append((path,
                                  f"its RAW is ambiguous - {m.how}, so it was left"))

    p.stats = [
        ("Photos to correct", f"{len(pictures):,}"),
        ("RAWs following them", f"{raws:,}"),
        ("The shift", say_offset(delta)),
        ("No capture time", f"{no_time:,}"),
        ("Folders unreadable", f"{len(found.errors):,}"),
    ]
    p.notes.append(f"Worked out from {how}.")
    p.notes.append("Every photo in the folder moves by the same amount, so the gaps "
                   "between frames are exactly as they were. A clock that is wrong is "
                   "wrong by a constant.")
    if raw_index is None:
        p.notes.append("NO RAW TREE WAS GIVEN. A RAW is tied to its JPEG by capture "
                       "time, so moving the JPEGs alone would break every pair in this "
                       "shoot. Point at the RAW tree unless you know there are none.")
    else:
        p.notes.append("Each RAW's corrected time goes in the .xmp beside it - the "
                       "RAW file is never opened for writing - which keeps it paired.")
    if p.errors:
        p.blocked = (f"{len(p.errors)} folder(s) could not be read. Half a shoot "
                     f"corrected is worse than none of it, so nothing will be written "
                     f"until that is fixed.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result

    keep = bool(plan.opts.get("keep_originals"))
    photos = sidecars = 0

    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        path = row.data["path"]
        when = dt.datetime.fromisoformat(row.data["when"])
        status = "OK"
        try:
            if keep and kind(path) == "jpeg":
                spare = os.path.join(os.path.dirname(path), BACKUP)
                ensure_folder(spare)
                kept = os.path.join(spare, os.path.basename(path))
                shutil.copy2(path, kept)
                perms.like(kept, path)
            where = set_datetime(path, when)
            back = read_capture(path).taken
            if back is None or abs((back - when).total_seconds()) > 1:
                raise ValueError(f"read back {back} instead of {when}")
            photos += 1 if where == "photo" else 0
            sidecars += 1 if where == "sidecar" else 0
            result.done += 1
        except Exception as exc:                    # noqa: BLE001
            status = result.blame(path, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)

    result.stats = [("Times written into photos", f"{photos:,}"),
                    ("Times written into a .xmp", f"{sidecars:,}"),
                    ("Failed", f"{result.failed:,}")]
    if result.cancelled and result.done:
        result.details.insert(0, (
            "STOPPED PART WAY. This folder is now in two different times: the first "
            f"{result.done} file(s) were corrected and the rest were not. Run the same "
            "correction again to finish it - the ones already done will show the new "
            "time and can be left out."))
    elif not result.details:
        result.details.append(
            "Every capture time was read back from the file after it was written. The "
            "pixel data in each JPEG was verified unchanged before it was replaced.")
    return result


register(Task(
    name="retime",
    fold_groups=True,
    line="Correct the time a camera recorded, for a whole shoot at once.",
    verb="Fix the time on",
    unit="photographs",
    risk="medium",
    undo="The new time is written into the file. History records what "
         "it was, but nothing here puts it back for you.",
    reads=('library', 'raw'),
    title="Fix the clock",
    summary="Corrects the capture time of a whole shoot, from one photo "
            "whose real time you know.",
    icon="clock",
    # a wrong clock poisons dates, pairing and geotagging,
    # so it is fixed before anything is decided from a timestamp
    parent="geotag",
    order=10,
    options=[
        Folder("folder", "Folder to correct", setting="library",
               group="Folders",
               help="The folder of photos to correct, usually one shoot. A "
                    "clock is wrong for a stretch of time, not for a whole "
                    "library."),
        Flag("mirror", "Trees from Setup", default=True,
             group="Folders",
             help="On, the tree boxes below are ignored and the trees come "
                  "from Setup, so files land where every other tool puts "
                  "them. Off, the folders you type below are used for this "
                  "run only. Turning this off does not stop RAW files being "
                  "corrected."),
        Folder("raw", "RAW tree", tree=True, default="", must_exist=False, setting="raw",
               group="Folders",
               help="The top of the RAW tree, so the RAW files are corrected "
                    "too, in the .xmp sidecar beside each one. Strongly "
                    "recommended: RAW files are paired to JPEGs by capture "
                    "time, so correcting JPEGs alone breaks every pair. "
                    "Blank leaves RAW files alone."),
        Choice("mode", "Correction method", default="photo",
               choices=MODES, group="Correction",
             help="How the correction is worked out: from one photo whose "
                  "real time you know, or by an amount you type. Every photo "
                  "in the folder moves by the same difference either way."),
        FilePath("reference", "Reference photo", default="",
               group="Correction",
               help="The photo whose real time you know. Blank uses the "
                    "earliest photo in the folder. Only used by the first "
                    "method."),
        Option("correct_time", "Real capture time", default="",
               group="Correction",
               help="The real time the reference photo was taken, for "
                    "example 2024-05-01 09:00:00. Every photo in the folder "
                    "moves by the difference between this and the recorded "
                    "time. Only used by the first method."),
        Number("days", "Shift by (days)", default=0, minimum=-3650, maximum=3650,
               group="Fixed amount", advanced=True,
               help="Days to add to every capture time, for the fixed-amount "
                    "method. -3650 to 3650, default 0. A negative number "
                    "moves time backwards. Added to the hours, minutes and "
                    "seconds below."),
        Number("hours", "Shift by (hours)", default=0, minimum=-48, maximum=48,
               group="Fixed amount", advanced=True,
               help="Hours to add to every capture time, for the "
                    "fixed-amount method. -48 to 48, default 0. A negative "
                    "number moves time backwards."),
        Number("minutes", "Shift by (minutes)", default=0, minimum=-1440, maximum=1440,
               group="Fixed amount", advanced=True,
               help="Minutes to add to every capture time, for the "
                    "fixed-amount method. -1440 to 1440, default 0. A "
                    "negative number moves time backwards."),
        Number("seconds", "Shift by (seconds)", default=0, minimum=-3600, maximum=3600,
               group="Fixed amount", advanced=True,
               help="Seconds to add to every capture time, for the "
                    "fixed-amount method. -3600 to 3600, default 0. A "
                    "negative number moves time backwards. The total of "
                    "days, hours, minutes and seconds must not be zero."),
        Flag("keep_originals", "Keep originals", group="Safety", advanced=True,
             help=f"Copies each photo into a {BACKUP} folder beside it before "
                  f"its time is changed. Off by default: the correction is "
                  f"written into the photo and read back to verify it, so a "
                  f"copy is extra safety."),
    ],
    plan=plan,
    apply=apply,
))
