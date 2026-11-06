"""Put tags on photographs - a folder at a time, or by a rule.

A star says how good a frame is. A colour says what you want DONE with it. A
TAG is the one of the three that other programs can search: Synology Photos
looks for it, Explorer shows it in its Tags column, Lightroom and darktable both
read it, and none of them can search "the ones I marked green in Photo Manager".

So tagging is the bridge out of this app, and there are three ways a photograph
ends up needing one, all of them here rather than scattered:

**A whole folder at once.** You already know what a shoot is - a wedding, a
timelapse, the Barcelona trip - usually before you have looked at a single
frame. Type the words, point it at the folder.

**By a rule.** "Everything four stars and up in this year gets `portfolio`."
The rule reads what is already on the photograph - its rating or its colour - so
it is repeatable: run it again next month and the frames you have rated since
are picked up and the rest are left alone.

**The words a colour means.** `xmp:Label` holds "Green"; what green MEANS in
this library lives in Setup and belongs on the file as tags. A photograph can be
perfectly labelled and still unfindable, and there are four ordinary ways to
arrive there: the colour was put on in Lightroom or on the tablet; it was put on
here before that colour had a meaning; the meaning changed afterwards; or it
came in through a sidecar somebody else wrote.

**Tags are only ever ADDED.** Never replaced, never removed. They go on top of
whatever the photograph already carries, and a word already there in any casing
is not written twice. That is what makes this safe to run over a whole library
without reading the list first: the worst it can do is add a word you meant to
be there anyway.

**It never puts a colour on and never takes one off.** Deciding a colour is
Apply label, next door. This only reads them.
"""

from __future__ import annotations

import os

from app.registry import (Choice, Flag, Folder, Number, Option, Plan, Result,
                          Row, Task, register)
from core import facts, tagwrite, walk
from core import labels as L
from core.photo import kind

WHICH = [
    ("all", "Every photo in the folder"),
    ("stars", "Rated this many or more"),
    ("exact", "Rated exactly this many"),
    ("unrated", "Unrated only"),
    ("colour", "Carrying one colour label"),
    ("missing", "Missing its colour's tags"),
    ("lens", "Shot on a lens"),
    ("focal", "In a focal range"),
]


def _focal_choices():
    from core import bands
    return [(label, label) for label, _top in bands.table("range")]


def _colour_choices():
    out = [("", "Any colour")]
    for d in L.defined():
        out.append((d.colour, d.title() + ("" if d.defined
                                           else " - not defined yet")))
    return out


def _words(text) -> list:
    """The tags typed into the box, in the order they were typed.

    Commas or new lines, because both are what people actually type, and a
    trailing comma is not an empty tag.
    """
    out = []
    for word in str(text or "").replace("\n", ",").split(","):
        word = word.strip()
        if word and word.lower() not in {o.lower() for o in out}:
            out.append(word)
    return out


def _folders(opts) -> list:
    """Everywhere to look. Nothing is paired up here.

    Unlike Sync, this never has to find a photograph's negative: a rule reads
    what is written on each file, and a RAW's sidecar answers for the RAW. So
    the other trees are the SAME FOLDER in each of them - Spain in the RAW tree
    when you picked Spain in the library - and never the whole of the tree.
    """
    from core.paths import same_place
    chosen = [str(f).strip() for f in Folder("folder", "").chosen(opts.get("folder"))
              if str(f).strip()]
    keys = tuple(k for k, flag in (("raw", "with_raw"), ("previews", "with_previews"))
                 if opts.get(flag))
    return same_place(chosen, keys) if keys else list(chosen)


def _wanted(path, opts, facts_for, meanings) -> tuple:
    """Does this photograph match the rule? (yes, why not).

    One function, so the rule is in one place rather than spread through the
    loop - and so the reason a frame was passed over is a sentence rather than
    an absence.
    """
    which = str(opts.get("which") or "all")
    if which == "all":
        return True, ""
    if which in ("stars", "exact", "unrated"):
        stars = facts_for.stars(path)
        want = int(opts.get("stars") or 0)
        if which == "unrated":
            return (not stars), (f"rated {stars}" if stars else "")
        if which == "exact":
            return stars == want, f"rated {stars or 'not at all'}"
        return stars >= want, f"rated {stars or 'not at all'}"
    if which in ("lens", "focal"):
        # Read once and remembered, like everything else here - the lens and
        # the focal length come out of the same EXIF block as the clock.
        cap = facts_for.capture(path)
        if which == "lens":
            want = str(opts.get("lens") or "").strip().lower()
            have = str(cap.lens or "").strip()
            if not want:
                return False, "no lens was named"
            if not have:
                return False, "the camera did not record a lens"
            # "contains", not "equals": what a camera writes is often longer
            # than what anyone would type - "LUMIX G 25/F1.7" for "25/F1.7".
            return (want in have.lower()), (f"shot on {have}")
        from core import bands
        label, _how = bands.lens_range(cap)
        want = str(opts.get("focal") or "")
        if not label:
            return False, "no focal length recorded"
        return label == want, label
    said = facts_for.label(path)
    colour = L.colour_named(said)
    if which == "colour":
        only = str(opts.get("colour") or "").strip().lower()
        if not colour:
            return False, (f"carries the label {said!r}, which is not one of the "
                           f"five" if said else "no colour on it")
        if only and colour != only:
            return False, f"it is {L.WORD[colour]}"
        return True, ""
    # missing: it carries a colour and not the words that colour means
    if not colour:
        return False, (f"carries the label {said!r}, which is not one of the "
                       f"five - another program's word" if said
                       else "no colour on it")
    d = meanings.get(colour)
    if d is None or not d.defined:
        return False, (f"{L.WORD[colour]} has no meaning set yet, so there are "
                       f"no words to write. Setup > Colour meanings.")
    return True, ""


def plan(opts, progress=None) -> Plan:
    p = Plan(task="tags")
    folders = _folders(opts)
    if not folders:
        p.blocked = "Give it a folder to look through."
        return p
    missing = [f for f in folders if not os.path.isdir(f)]
    if missing:
        p.blocked = f"There is no folder at {missing[0]!r}"
        return p

    typed = _words(opts.get("words"))
    from_colour = bool(opts.get("from_colour"))
    if not typed and not from_colour:
        p.blocked = ("Nothing would be written. Type some tags, or tick 'Add "
                     "the colour's tags' to use what each colour means.")
        return p

    files = []
    for folder in folders:
        got = walk.walk(folder)
        for path, why in got.errors:
            p.errors.append(f"could not read {path}: {why}")
        files.extend(got.files)

    # One reader for the run: the rating, the colour and the tags already on a
    # file come out of the same two places, and a file whose size, date and
    # inode have not moved since the last pass is not opened at all.
    facts_for = facts.reader()
    meanings = {d.colour: d for d in L.defined()}

    p.columns = ["Photograph", "Already has", "To add", "Why it matched"]
    passed = complete = 0
    total = len(files)
    for i, path in enumerate(sorted(files), 1):
        if progress:
            progress(i, total, os.path.basename(path))
        if kind(path) not in ("jpeg", "image", "raw"):
            continue
        yes, why_not = _wanted(path, opts, facts_for, meanings)
        if not yes:
            passed += 1
            if why_not:
                p.skipped.append((path, why_not))
            continue

        want = list(typed)
        because = "you typed them" if typed else ""
        if from_colour:
            colour = L.colour_named(facts_for.label(path))
            d = meanings.get(colour) if colour else None
            if d is not None and d.defined:
                for word in d.all_keywords():
                    if word.lower() not in {w.lower() for w in want}:
                        want.append(word)
                because = (f"{L.WORD[colour]} means {d.name!r}"
                           + (" (and your words)" if typed else ""))
        if not want:
            passed += 1
            continue

        have = facts_for.tags(path)
        lower = {h.lower() for h in have}
        add = [w for w in want if w.lower() not in lower]
        if not add:
            complete += 1
            continue
        p.rows.append(Row(
            what="tags", name=os.path.basename(path), source=path, target=path,
            size=0,
            detail=f"adding {', '.join(add)}"
                   + (f" - {because}" if because else "")
                   + f" (it already has "
                     f"{', '.join(have) if have else 'no tags'})",
            cells=[", ".join(have) or "no tags", ", ".join(add), because],
            data={"path": path, "tags": add}))

    facts_for.save()
    p.stats = [
        ("Files opened", facts_for.said()),
        ("Photos to tag", f"{len(p.rows):,}"),
        ("Tags to write", f"{sum(len(r.data['tags']) for r in p.rows):,}"),
        ("Already carry them", f"{complete:,}"),
        ("Did not match the rule", f"{passed:,}"),
        ("Folders unreadable", f"{len(p.errors):,}"),
    ]
    p.notes.append(
        "Tags are ADDED to whatever the photo already carries. Nothing is "
        "replaced, nothing is removed, and a word already there in any casing "
        "is not written twice.")
    p.notes.append(
        "No colour is put on or taken off here - this only reads them. Apply "
        "label is where a colour is decided.")
    if str(opts.get("which") or "all") != "all":
        p.notes.append(
            "The rule reads what is already on the photo, so this is worth "
            "running again later: frames you have rated or coloured since will "
            "be picked up and the rest left alone.")
    if not p.rows:
        p.notes.append("Nothing to do: everything that matched already carries "
                       "those tags.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    in_file = bool((plan.opts or {}).get("in_file", True))
    words = sidecars = photos = 0
    reader = facts.reader()
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        status = "OK"
        path, add = row.data["path"], row.data["tags"]
        try:
            got = tagwrite.add(path, add, in_file=in_file, in_sidecar=True)
            if not got["sidecar"] and not got["xmp"] and not got["windows"]:
                raise RuntimeError("; ".join(got["errors"])
                                   or "nothing could be written")
            sidecars += 1 if got["sidecar"] else 0
            photos += 1 if (got["xmp"] or got["windows"]) else 0
            words += len(add)
            # What is known about this file was true a moment ago and is not
            # now. The signature would catch it on the next pass; the next STEP
            # of a flow is the case it cannot help with.
            reader.forget(path)
            if got["errors"]:
                result.details.append(f"{row.name}\n    " + "; ".join(got["errors"]))
            result.done += 1
        except Exception as exc:                        # noqa: BLE001
            status = result.blame(row.name, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)
    reader.save()

    result.stats = [("Photos tagged", f"{result.done:,}"),
                    ("Tags written", f"{words:,}"),
                    ("  in a sidecar", f"{sidecars:,}"),
                    ("  inside the photo", f"{photos:,}"),
                    ("Failed", f"{result.failed:,}")]
    if result.done and not result.failed:
        result.details.append(
            "Written in both places: the sidecar, which every editor reads and "
            "which is all a RAW can carry, and inside the JPEG, where Synology "
            "Photos and Explorer look for tags.")
    return result


register(Task(
    name="tags",
    fold_groups=True,
    line="Put tags on a whole folder, or on whatever matches a rule.",
    verb="Tag",
    unit="photographs",
    reads=("library", "raw", "previews"),
    title="Tag photos",
    parent="ratings",
    tab="Tag photos",
    summary="Adds tags to every photo in a folder, or only to the photos "
            "that match a rule.",
    icon="tag-plus",
    order=39,
    options=[
        Folder("folder", "Folders to tag", setting="library", many=True,
               help="The folders to tag. Every photo inside each one is "
                    "considered. Safe to run over everything, because tags "
                    "are only added, never replaced or removed."),
        Option("words", "Tags to add", default="",
               help="The tags to write, separated by commas. 'Barcelona "
                    "2024, travel, family' is three tags. A tag already on a "
                    "photo is not written again."),
        Choice("which", "Which photos", default="all", choices=WHICH,
               group="Rule",
               help="The rule that picks the photos to tag. A rule reads "
                    "what is already on the photo, so it can be run again as "
                    "you rate and label more of them."),
        Number("stars", "Stars", default=4, minimum=1, maximum=5,
               group="Rule",
               help="The rating the two rating rules compare with. 1 to 5, "
                    "default 4. Ignored by the other rules."),
        Choice("colour", "Colour label", default="", choices=_colour_choices,
               group="Rule",
               help="The colour label for the 'Carrying one colour label' "
                    "rule. Ignored by the other rules."),
        Option("lens", "Lens name contains", default="", group="Rule",
               help="Text the lens name must contain, for the 'Shot on a "
                    "lens' rule. Part of the name is enough: 25/F1.7 finds "
                    "LUMIX G 25/F1.7. The Storage tab lists the exact lens "
                    "names your cameras write."),
        Choice("focal", "Focal range", default="Normal (36-70mm)",
               choices=_focal_choices, group="Rule",
               help="The focal length range for the 'In a focal range' rule, "
                    "default Normal (36-70mm). The full-frame equivalent is "
                    "used where the camera records it, so 25mm on a GH4 "
                    "counts as 50mm. Otherwise the number on the lens is "
                    "used. The ranges are set in Setup > Chart bands."),
        Flag("from_colour", "Add the colour's tags", default=False,
             group="Rule",
             help="Also writes the meaning and extra tags of each photo's "
                  "colour label, from Setup > Colour meanings. This repairs "
                  "colour labels set by Lightroom or the tablet, which could "
                  "not write those tags. Off by default."),
        Flag("with_raw", "Tag their RAW files", default=True,
             group="Other trees",
             help="Also tags the matching folder in the RAW tree, by the "
                  "same rule. Only that folder, never the whole tree. On by "
                  "default."),
        Flag("with_previews", "Tag their previews", default=False,
             group="Other trees",
             help="Also tags the matching folder in the previews tree, so "
                  "the preview is found by the same words. Off by "
                  "default."),
        Flag("in_file", "Write into the photo",
             default=True, group="Advanced", advanced=True,
             help="Writes the tags into the JPEG itself as well as into its "
                  "sidecar. Lightroom and darktable read the sidecar. "
                  "Synology Photos and Windows Explorer read the JPEG, so "
                  "leave this on unless you have a reason not to."),
    ],
    plan=plan,
    apply=apply,
))
