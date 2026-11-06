"""Put a colour on a folder of photographs - and on their negatives and previews.

This sits beside Sync, under one feature, because the two halves of a colour's
life belong together: here is where a colour is PUT on a folder you have already
made your mind up about, and next door is where a colour someone gave one frame
is carried to every copy of that shot. Tag photos, the third tab, is where a
colour becomes something other programs can search - including the repair for
colours written by something that never knew what they meant here.

A rating is something you give one frame at a time. A colour is usually
something you already know about a whole folder: these six hundred stills are a
timelapse, this shoot is the one to sharpen, that morning is the one worth
printing. Deciding that once and marking the folder is the job here, and it is
why this exists as well as whatever you tick frame by frame in Lightroom.

Three things it is careful about:

**A colour already there is left alone unless you say otherwise.** Marking a
folder green when half of it is already red would quietly undo an afternoon's
work, and the photographs it happened to overwrite are not recoverable from
anything - the old label is simply gone. So a photograph carrying a DIFFERENT
colour is listed, counted and skipped until the box is ticked.

**A label nothing here recognises is never touched.** `xmp:Label` is a free
string and somebody else's program may be using it for something this app has no
idea about. Bridge's own names are understood; anything else is left exactly as
it is and said so.

**The negative and the preview get it too.** A colour on the JPEG and not on the
RAW means Lightroom shows the shoot as unlabelled the moment you open the
negatives, which is the version you were going to develop. Each is found by
capture time, camera and name, the same pairing the rest of the app uses.
"""

from __future__ import annotations

import os

from app.registry import (Choice, Flag, Folder, Plan, Result, Row, Task, register)
from core import labels as L
from core import walk
from core import facts
from core.pairs import build_index, find_partner
from core.photo import kind, read_capture

CLEAR = "clear"


def _colour_choices():
    out = []
    for d in L.defined():
        out.append((d.colour, d.title() + ("" if d.defined
                                           else " - not defined yet")))
    out.append((CLEAR, "Take the colour off"))
    return out


def _others(opts) -> list:
    """The other trees to carry the colour into."""
    out = []
    for key, label in (("raw", "the RAW"), ("previews", "the preview")):
        folder = str(opts.get(key) or "").strip()
        if folder and os.path.isdir(folder):
            out.append((label, folder, ("raw",) if key == "raw"
                        else ("jpeg", "image")))
    return out


def plan(opts, progress=None) -> Plan:
    p = Plan(task="label")
    folders = [f for f in Folder("folder", "").chosen(opts.get("folder"))
               if f.strip()]
    missing = [f for f in folders if not os.path.isdir(f)]
    if not folders:
        p.blocked = "Give it a folder to mark."
        return p
    if missing:
        p.blocked = f"There is no folder at {missing[0]!r}"
        return p

    wanted = str(opts.get("colour") or "").strip().lower()
    clearing = wanted == CLEAR
    d = None if clearing else L.by_colour(wanted)
    if not clearing and d is None:
        p.blocked = f"{wanted!r} is not one of the five colours."
        return p
    if d is not None and not d.defined:
        p.blocked = (f"{L.WORD[d.colour]} has no meaning set yet. Setup > Colour "
                     f"meanings is where a colour is given a name, the tags "
                     f"it writes and whether it sends anything out - marking a "
                     f"folder with a colour that means nothing would be a mark "
                     f"nothing can read.")
        return p

    replace = bool(opts.get("replace"))
    keywords = d.all_keywords() if d else []

    p.columns = ["Photograph", "Carries", "Becomes", "Tags"]
    already = held = elsewhere = 0
    files = []
    for folder in folders:
        got = walk.walk(folder)
        for path, why in got.errors:
            p.errors.append(f"could not read {path}: {why}")
        files.extend(got.files)

    # The other trees are indexed for THESE names only. Marking one shoot should
    # not mean reading the EXIF of every negative on the disk first - and it
    # cannot change the answer, because every way a partner is looked up starts
    # from the base name.
    from core.pairs import base_name
    looking_for = {base_name(x) for x in files}
    # One reader for the run: the clock, the camera and the colour already on a
    # file all come out of the same two places, and one whose size, date and
    # inode have not moved since the last pass is not opened at all.
    facts_for = facts.reader()
    indexes = []
    for label, folder, want in _others(opts):
        got = walk.walk(folder)
        for path, why in got.errors:
            p.errors.append(f"could not read {path}: {why}")
        indexes.append((label, folder,
                        build_index(got.files, want=want, names=looking_for,
                                    reader=facts_for)))

    total = len(files)
    for i, path in enumerate(sorted(files), 1):
        if progress:
            progress(i, total, os.path.basename(path))
        if kind(path) not in ("jpeg", "image", "raw"):
            continue
        was = facts_for.label(path)
        was_colour = L.colour_named(was)
        becomes = L.WORD.get(wanted, "none") if not clearing else "none"

        if was and not was_colour:
            elsewhere += 1
            p.skipped.append((path,
                              f"it carries the label {was!r}, which is not one of "
                              f"the five and not a name anything here knows. Some "
                              f"other program is using it, so it is left alone."))
            continue
        if was_colour == wanted and not clearing:
            already += 1
            continue
        if was_colour and was_colour != wanted and not replace and not clearing:
            held += 1
            p.skipped.append((path,
                              f"already {L.WORD[was_colour]}. Tick 'replace a "
                              f"colour that is already there' to change it - the "
                              f"old one is not recoverable once it is gone."))
            continue

        rows = [(path, "the photo itself")]
        cap = facts_for.capture(path)
        for label, _folder, idx in indexes:
            if not idx.considered:
                continue
            m = find_partner(path, cap, idx)
            if m.jpeg:
                rows.append((m.jpeg, label))
        for where, why in rows:
            p.rows.append(Row(
                what="label", name=os.path.basename(where), source=where,
                target="", size=0,
                detail=f"{was or 'no colour'} -> {becomes} ({why})",
                cells=[was or "nothing", becomes,
                       ", ".join(keywords) or "none"],
                data={"path": where, "colour": "" if clearing else wanted,
                      "keywords": keywords}))

    facts_for.save()
    p.stats = [
        ("Files opened", facts_for.said()),
        ("Photos to mark", f"{sum(1 for r in p.rows):,}"),
        ("Already that colour", f"{already:,}"),
        ("Held back - another colour", f"{held:,}"),
        ("Left alone - somebody else's label", f"{elsewhere:,}"),
        ("Colour label", "taken off" if clearing else d.title()),
        ("Tags written", ", ".join(keywords) or "none"),
    ]
    if not clearing:
        p.notes.append(
            f"xmp:Label is written as {L.WORD[wanted]!r} - the colour word, which "
            f"is what Lightroom, Bridge and darktable read. Your name for it, "
            f"{d.name!r}, goes on as a TAG instead, which is the half other "
            f"programs can search.")
        if d.sends:
            where = d.folder or "the develop tree itself"
            p.notes.append(
                f"{L.WORD[wanted]} sends: the next run of Send to develop copies "
                f"anything carrying it into {where}"
                + (", with its RAW." if d.raw else ", the JPEG only."))
        else:
            p.notes.append(
                f"{L.WORD[wanted]} does not send anything anywhere - it is a mark "
                f"you and other programs can find. Setup > Colour meanings is "
                f"where that is changed.")
    else:
        p.notes.append("Taking a colour off does not take the tags off with "
                       "it. They were added to whatever the file already carried, "
                       "and removing them again would mean guessing which of them "
                       "were this app's.")
    if held:
        p.notes.append(f"{held} photo(s) already carry a different colour and "
                       f"are being left. That is the safe half of this: an "
                       f"overwritten label is gone, not recoverable.")
    if indexes:
        p.notes.append(
            "The RAW file and the preview are marked too, each found by capture "
            "time, camera and name. A colour on the JPEG alone means Lightroom "
            "shows the shoot as unlabelled the moment you open the RAWs.")
    else:
        p.notes.append("Only the photos in that folder - no RAW tree or "
                       "previews tree was given, so nothing else is marked.")
    if not p.rows:
        p.notes.append("Nothing to do: everything there already says what you are "
                       "asking it to say.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    in_file = bool((plan.opts or {}).get("in_file", True))
    photos = sidecars = 0
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        status = "OK"
        try:
            got = L.set_label(row.data["path"], row.data["colour"],
                              row.data.get("keywords") or [],
                              in_file=in_file, in_sidecar=True)
            photos += 1 if got["photo"] else 0
            sidecars += 1 if got["sidecar"] else 0
            if not got["sidecar"] and not got["photo"]:
                raise RuntimeError(got["why"] or "nothing could be written")
            if got["why"]:
                result.details.append(f"{row.name}\n    {got['why']}")
            result.done += 1
        except Exception as exc:                    # noqa: BLE001
            status = result.blame(row.name, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)

    result.stats = [("Marked", f"{result.done:,}"),
                    ("  inside the photo", f"{photos:,}"),
                    ("  in a sidecar", f"{sidecars:,}"),
                    ("Failed", f"{result.failed:,}")]
    if not result.failed and result.done:
        result.details.append(
            "Written in both places: the sidecar, which every tool reads and "
            "which is the only thing a RAW can carry, and inside the JPEG, which "
            "is what Synology Photos and Explorer look at.")
    return result


register(Task(
    name="label",
    line="Mark a whole folder you have already made your mind up about.",
    verb="Label",
    unit="photographs",
    reads=('library', 'raw', 'previews'),
    title="Apply label",
    parent="ratings",
    tab="Apply label",
    summary="Gives every photo in a folder one colour label, so other tools "
            "can act on it.",
    icon="tag",
    order=38,
    options=[
        Folder("folder", "Folders to label", setting="library", many=True,
               help="The folders to label. Every photo inside each one gets "
                    "the colour label."),
        Choice("colour", "Colour label", default="red", choices=_colour_choices,
               help="The colour label to write. What each colour means is "
                    "set in Setup > Colour meanings. A colour with no "
                    "meaning set cannot be used. 'Take the colour off' "
                    "removes the label."),
        Flag("replace", "Replace existing colour", default=False,
             help="Overwrites a different colour label already on a photo. "
                  "Off by default: such a photo is listed and left. The old "
                  "colour cannot be recovered."),
        Folder("raw", "RAW tree", tree=True, default="", must_exist=False,
               setting="raw", group="Other trees",
               help="The top of the RAW tree, so each photo's RAW file gets "
                    "the colour label too, in its sidecar. Blank labels only "
                    "the folders above."),
        Folder("previews", "Previews tree", tree=True, default="",
               must_exist=False, setting="previews", group="Other trees",
               help="The top of the previews tree, so the colour label shows "
                    "on the tablet. Blank leaves previews alone."),
        Flag("in_file", "Write into the photo",
             default=True, group="Advanced", advanced=True,
             help="Writes the colour label into the JPEG itself as well as "
                  "into its sidecar. Lightroom and darktable read the "
                  "sidecar. Synology Photos and Windows Explorer read the "
                  "JPEG, so leave this on unless you have a reason not to."),
    ],
    plan=plan,
    apply=apply,
))
