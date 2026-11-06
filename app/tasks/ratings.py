"""Carry what you said about a photo across to everything that is the same shot.

You rate previews on a tablet. The stars then have to reach the original in the
library and the RAW in its own tree, or culling later reads the wrong number and
puts away a photo you kept.

**The colour comes with them, and for a while it did not.** A star and a colour
are made in the same place, at the same moment, by the same person going through
a folder - and only one of them was being carried. So the previews said "edit
this one" and the negative you actually open in Lightroom said nothing at all,
which is the same silence as an unrated RAW and just as much work to repair by
hand. They travel together now, and either half can be turned off.

A colour is carried more carefully than a star, for one reason: an overwritten
rating can be given again by looking at the photograph, and an overwritten
colour is a decision that is simply gone. So a photograph that already carries a
DIFFERENT colour is listed and left until you tick the box, and a label this app
does not recognise - somebody else's program using `xmp:Label` for its own
purposes - is never touched at all.

Matching is by IDENTITY, not by position: capture time, camera and base name. A
preview named the same thing in a folder you have since renamed still finds its
original, which is the entire reason this is not a path comparison.

Direction is fixed and stated, never inferred. Whichever folder you rated in is
the source; the library and the RAW tree receive. The Windows version tried to
work out which side had changed using a ledger of what it last saw, and a
two-sided guess about which of two files is "newer" is exactly the kind of thing
that is right until the one time it silently overwrites the ratings you spent an
evening making. Here the plan shows every change as "3 stars, was 2" before
anything is written, and you decide.

Zero stars means UNRATED, not "rated zero". An unrated source never clears a
rating that already exists on the other side.
"""

from __future__ import annotations

import os

from app.grouping import sets_for
from app.registry import Flag, Folder, Plan, Result, Row, Task, register
from core import facts, walk
from core import labels as L
from core.exifwrite import rating_of, set_rating
from core.pairs import build_index, find_partner
from core.photo import kind


def plan(opts) -> Plan:
    p = Plan(task="ratings")
    source = opts["folder"]
    if not source or not os.path.isdir(source):
        p.blocked = f"There is no folder at {source!r}"
        return p

    receivers = []
    for key, label in (("library", "library"), ("raw", "RAW")):
        folder = (opts.get(key) or "").strip()
        if not folder:
            continue
        if not os.path.isdir(folder):
            p.blocked = f"There is no {label} tree at {folder!r}"
            return p
        if os.path.realpath(folder) == os.path.realpath(source):
            p.blocked = f"The {label} tree is the same folder as the one you rated in."
            return p
        receivers.append((label, folder))
    if not receivers:
        p.blocked = "Say where the ratings should go - the library, the RAW tree, or both."
        return p

    src_walk = walk.walk(source)
    for path, why in src_walk.errors:
        p.errors.append(f"could not read {path}: {why}")

    # The trees are WALKED first and indexed after, because what has to be
    # indexed is not known until the bracket sets are worked out.
    walks = {}
    for label, folder in receivers:
        w = walk.walk(folder)
        for path, why in w.errors:
            p.errors.append(f"could not read {path}: {why}")
        walks[label] = (folder, w)

    # Where a bracket set actually LIVES decides where it has to be worked out.
    #
    # There is one preview per set, so the previews folder contains no sets at all
    # - the other two exposures were never given one. Group the previews and you
    # find nothing, and the two frames you did not preview stay unrated forever.
    # The set exists in the library, so that is where it is looked for: the rating
    # lands on the original, spreads to the rest of its set there, and each of
    # those then finds its own RAW.
    #
    # When you rated in the library itself, that folder is both source and
    # spreading ground, which is the same rule with the two ends coincident.
    spread_root, spread_walk = source, src_walk
    if "library" in walks:
        spread_root, spread_walk = walks["library"]

    # One reader for the whole run: a photograph's rating, clock and camera all
    # come out of the same two places, so they are fetched together, and a file
    # whose size and date have not moved since the last pass is not opened at
    # all. This is where the thirty minutes went.
    facts_for = facts.reader()

    sets = sets_for(spread_walk.files, opts, p, reader=facts_for)

    # Which names could possibly be asked about - and nothing else gets opened.
    #
    # A star can only reach a file that shares its name: that is how every tier
    # of the pairing works. So reading the rest of a tree is time spent on
    # answers nothing will ask for, and on a library of any size it is the
    # difference between a sync that finishes and one you stop watching.
    #
    # The brackets are why this cannot simply be "the names being rated from". A
    # star given to ONE preview reaches the whole set it stands for, and those
    # frames have different names - aeb1 was rated, aeb2 and aeb3 must still
    # find their own negatives. So the set members' names are added, worked out
    # from the sets already in hand rather than by reading anything.
    from core.pairs import base_name
    looking_for = {base_name(x) for x in src_walk.files}
    if sets is not None:
        for path in spread_walk.files:
            if base_name(path) not in looking_for:
                continue
            found = sets.set_of(path)
            if found:
                looking_for |= {base_name(f.path) for f in found.members}

    trees = {}
    for label, (folder, w) in walks.items():
        want = ("raw",) if label == "RAW" else ("jpeg", "image")
        trees[label] = (folder, w, build_index(w.files, want=want,
                                               names=looking_for,
                                               reader=facts_for))
    if sets is not None:
        p.notes.append(f"Those sets were looked for in {spread_root}. A rating "
                       f"reaching one frame of a set reaches the whole set.")

    carry_stars = bool(opts.get("stars", True))
    carry_colour = bool(opts.get("colours", True))
    replace = bool(opts.get("replace"))

    rated = unrated = same = missing = ambiguous = borrowed = 0
    colour_same = held = foreign = coloured = 0
    written: set[str] = set()
    for path in sorted(src_walk.files):
        if kind(path) not in ("jpeg", "image"):
            continue
        stars = facts_for.stars(path) if carry_stars else 0
        said = facts_for.label(path) if carry_colour else ""
        colour = L.colour_named(said)
        if said and not colour:
            # Somebody else's word in xmp:Label. Not carried, not overwritten,
            # not counted as "no colour" - just said out loud and left.
            foreign += 1
            p.skipped.append((path,
                              f"carries the label {said!r}, which is not one of "
                              f"the five - another program's, so it is left where "
                              f"it is and taken nowhere"))
        if not stars and not colour:
            unrated += 1
            p.skipped.append((path, "nothing on it to carry"))
            continue
        if colour:
            coloured += 1
        # The words that go with the colour, when the colour has been given a
        # meaning. An undefined colour is still carried - it is already on the
        # photograph, and copying what is there is not the same as inventing a
        # mark, which is what Apply label refuses to do without a meaning.
        d = L.by_colour(colour) if colour else None
        keywords = d.all_keywords() if d else []
        if stars:
            rated += 1
        cap = facts_for.capture(path)

        # the frame in the spreading tree that this rated file IS
        if spread_root == source:
            anchor, anchor_how = path, "the file itself"
        else:
            m = find_partner(path, cap, trees["library"][2])
            if m.jpeg is None:
                if m.candidates > 1:
                    ambiguous += 1
                    p.skipped.append((path,
                                      f"library: {m.how}, so which one is a guess"))
                else:
                    missing += 1
                    p.skipped.append((path,
                                      "nothing in the library is this shot"))
                continue
            anchor, anchor_how = m.jpeg, m.how

        s = sets.set_of(anchor) if sets is not None else None
        members = [m.path for m in s.members] if s else [anchor]

        for member in members:
            from_bracket = "" if member == anchor else os.path.basename(anchor)
            if from_bracket:
                borrowed += 1
            for label, (_folder, _w, idx) in trees.items():
                if label == "library":
                    target, how = member, anchor_how
                else:
                    mm = find_partner(member, facts_for.capture(member), idx)
                    if mm.jpeg is None:
                        if mm.candidates > 1:
                            ambiguous += 1
                            p.skipped.append((member,
                                              f"{label}: {mm.how}, so which one is a guess"))
                        else:
                            missing += 1
                            p.skipped.append((member,
                                              f"{label}: nothing there is this shot"))
                        continue
                    target, how = mm.jpeg, mm.how
                if os.path.realpath(target) == os.path.realpath(path):
                    continue                     # never write back over the source
                key = os.path.normcase(os.path.abspath(target))
                if key in written:
                    continue                     # two sources agreeing is not two writes
                was = facts_for.stars(target)
                star_change = bool(stars) and was != stars

                # The colour, decided separately and more cautiously, because an
                # overwritten rating can be given again by looking at the
                # photograph and an overwritten colour cannot.
                was_said = facts_for.label(target) if colour else ""
                was_colour = L.colour_named(was_said)
                take_colour = ""
                if colour:
                    if was_said and not was_colour:
                        foreign += 1
                        p.skipped.append((
                            target,
                            f"{label}: carries the label {was_said!r}, which is "
                            f"not one of the five - another program's, so it is "
                            f"left exactly as it is"))
                    elif was_colour == colour:
                        colour_same += 1
                    elif was_colour and not replace:
                        held += 1
                        p.skipped.append((
                            target,
                            f"{label}: already {L.WORD[was_colour]}. Tick "
                            f"'Replace existing colour' to change it - the old "
                            f"one is not recoverable once it is gone."))
                    else:
                        take_colour = colour

                if not star_change and not take_colour:
                    same += 1
                    written.add(key)
                    continue

                into = ("into the photo" if kind(target) == "jpeg"
                        else "into a .xmp beside it")
                said_was = [f"{was} star" if was else "unrated"]
                said_now = [f"{stars} star" if star_change else
                            (f"{was} star" if was else "unrated")]
                if colour:
                    said_was.append(L.WORD[was_colour] if was_colour
                                    else "no colour")
                    said_now.append(L.WORD[take_colour] if take_colour
                                    else (L.WORD[was_colour] if was_colour
                                          else "no colour"))
                was_text, now_text = ", ".join(said_was), ", ".join(said_now)
                detail = (f"{now_text} -> {label} ({into})"
                          f"  (was {was_text})  matched on {how}")
                if from_bracket:
                    detail += f"  [same bracket as {from_bracket}]"
                written.add(key)
                p.rows.append(Row(
                    what=label, name=os.path.basename(target), source=path,
                    target=target, detail=detail, approximate=bool(from_bracket),
                    cells=[was_text, now_text,
                           label, into, how,
                           f"same bracket as {from_bracket}" if from_bracket else ""],
                    data={"path": target,
                          "stars": stars if star_change else 0,
                          "colour": take_colour, "keywords": keywords}))

    facts_for.save()
    p.columns = ["File", "Was", "Now", "Kind", "Written", "Matched on", "Bracket"]
    stars_out = sum(1 for r in p.rows if r.data.get("stars"))
    colours_out = sum(1 for r in p.rows if r.data.get("colour"))
    p.stats = [
        ("Files opened", facts_for.said()),
        ("Rated photos in that folder", f"{rated:,}"),
        ("Coloured photos in that folder", f"{coloured:,}"),
        ("Reached through their bracket", f"{borrowed:,}"),
        ("Ratings to write", f"{stars_out:,}"),
        ("Colours to write", f"{colours_out:,}"),
        ("Already the same", f"{same + colour_same:,}"),
        ("Held back - another colour", f"{held:,}"),
        ("Somebody else's label - untouched", f"{foreign:,}"),
        ("Nothing on them to carry", f"{unrated:,}"),
        ("No match in the other trees", f"{missing:,}"),
        ("Ambiguous - left alone", f"{ambiguous:,}"),
        ("Folders unreadable", f"{len(p.errors):,}"),
    ]
    p.notes.append("Matched on capture time, camera and name - not on where the file "
                   "sits - so a folder you have renamed still matches.")
    p.notes.append("An unrated photo never clears a rating on the other side. Zero "
                   "stars means unrated, not rated zero.")
    if carry_colour:
        p.notes.append(
            "The colour travels with the stars: they are made in the same place "
            "at the same moment, and a preview marked 'edit this' whose RAW file "
            "says nothing is the same silence as an unrated RAW. The colour "
            "word goes into xmp:Label, and whatever that colour means in Setup "
            "goes on beside it as tags.")
        if held and not replace:
            p.notes.append(
                f"{held} photo(s) on the other side already carry a "
                f"different colour and are being left. That is the safe half: an "
                f"overwritten colour is gone, not recoverable.")
    else:
        p.notes.append("Colours are turned off for this run, so only the stars "
                       "are being carried.")
    if p.errors:
        p.blocked = (f"{len(p.errors)} folder(s) could not be read. A photo might look "
                     f"unmatched only because its partner is in one of them, so nothing "
                     f"will be written until that is fixed.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result

    in_file = bool((plan.opts or {}).get("in_file", True))
    sidecars = stars_done = colours_done = 0
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        path = row.data["path"]
        stars = int(row.data.get("stars") or 0)
        colour = str(row.data.get("colour") or "")
        status = "OK"
        try:
            if stars:
                where = set_rating(path, stars)
                sidecars += 1 if where == "sidecar" else 0
                back = rating_of(path)
                if back != stars:
                    raise ValueError(f"read back {back!r} instead of {stars}")
                stars_done += 1
            if colour:
                got = L.set_label(path, colour, row.data.get("keywords") or [],
                                  in_file=in_file, in_sidecar=True)
                if not got["sidecar"] and not got["photo"]:
                    raise RuntimeError(got["why"] or "the colour could not be written")
                if got["why"]:
                    result.details.append(f"{row.name}\n    {got['why']}")
                colours_done += 1
            result.done += 1
        except Exception as exc:                    # noqa: BLE001
            status = result.blame(path, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)

    result.stats = [("Ratings written", f"{stars_done:,}"),
                    ("  of those, into a .xmp beside a RAW", f"{sidecars:,}"),
                    ("Colours written", f"{colours_done:,}"),
                    ("Failed", f"{result.failed:,}")]
    if not result.details:
        result.details.append(
            "Every rating was read back afterwards. A JPEG was rated in place, with "
            "its pixel data verified unchanged before it was replaced; a RAW got a "
            ".xmp beside it, because this app never opens a RAW file for writing. A "
            "colour was written in both places at once - the sidecar, which every "
            "tool reads and which is all a RAW can carry, and inside the JPEG, which "
            "is what Synology Photos and Explorer look at.")
    return result


register(Task(
    name="ratings",
    fold_groups=True,
    line="Carry stars and colours back onto the originals and their RAWs.",
    verb="Sync",
    unit="ratings",
    reads=('previews', 'library', 'raw'),
    title="Rating & tags",
    summary="Copies ratings and colour labels from the previews you rated "
            "onto the originals and their RAW files.",
    icon="star",
    # the stars come back
    order=36,
    options=[
        Folder("folder", "Rated folder", setting="previews",
               help="The folder where you rated, usually the previews tree "
                    "synced to the tablet. Ratings and colour labels are "
                    "read from here."),
        Folder("library", "Library", tree=True, default="", must_exist=False,
               setting="library",
               help="The top of the library. The originals here receive the "
                    "ratings. Blank skips the library."),
        Flag("mirror", "Trees from Setup", default=True,
             help="On, the tree boxes below are ignored and the trees come "
                  "from Setup, so files land where every other tool puts "
                  "them. Off, the folders you type below are used for this "
                  "run only. Turning this off does not stop ratings being "
                  "written."),
        Folder("raw", "RAW tree", tree=True, default="", must_exist=False, setting="raw",
               help="The top of the RAW tree. Each RAW file receives the "
                    "rating in a .xmp sidecar beside it. The RAW file itself "
                    "is never changed. Blank skips RAW files."),
        Flag("brackets", "Spread over bracket sets",
             setting="bracket_group", group="Brackets",
             help="Gives every frame of a bracket set the rating of its "
                  "metered frame, which is the only frame with a preview. "
                  "Off, the other frames stay unrated and a later cull "
                  "splits the set. How a set is found is set in Setup > "
                  "Brackets. From Setup by default."),
        Flag("stars", "Ratings", default=True, group="What to copy",
             help="Copies the star ratings. Off, only colour labels are "
                  "copied. On by default."),
        Flag("colours", "Colour labels", default=True, group="What to copy",
             help="Copies the colour label, and writes the colour's meaning "
                  "from Setup > Colour meanings beside it as tags. On by "
                  "default."),
        Flag("replace", "Replace existing colour", default=False,
             group="What to copy",
             help="Overwrites a different colour label already on the "
                  "original. Off by default: such a photo is listed and "
                  "left. The old colour cannot be recovered."),
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
