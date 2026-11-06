"""Put the shots worth developing on the tablet - and take them off again.

The loop this is half of:

    send to develop   ->  Lightroom on the tablet  ->  file developed

**By rating, per kind.** A five-star shot is worth the negative; a four-star one
is worth a look but not fifty megabytes of ARW. So the thresholds are separate,
exactly as culling's are, and -1 means never send that kind at all.

**Nothing is moved.** Everything here is a COPY into a tree of its own. The
library is the truth and this is a working set; if the tablet is lost, dropped
or wiped, nothing has happened to a photograph.

**It remembers what has been developed** (`core/ledger.py`), by identity rather
than by path. That memory is the whole feature: without it every run copies the
same five-star photos out again forever, the folder never empties, and "what
still needs developing" has no answer. It is the one thing in this app that is
remembered rather than measured, because it has to be - a developed photo and an
undeveloped one look identical in the library.

**Pruning is what makes it temporary.** Anything in the tree that has since been
developed, or has dropped below its threshold, is taken out again. Deleting only
ever happens inside this tree, and even then the file is a copy of something the
library still holds.
"""

from __future__ import annotations

import os
import shutil

from app.grouping import sets_for
from app.registry import (Choice, Flag, Folder, Number, Option, Plan, Result, Row,
                          Task, register)
from core import meter
from core import perms
from core import labels as L
from core import facts, ledger, tags, walk
from core.pairs import build_index, find_partner, identity
from core.paths import (mirror_anchor, ensure_folder, mirror,
                        safe_target, tidy_empty_folders, roots_of, under, developed_beside)
from core.photo import kind

NEVER = -1



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

def _no_negative(m) -> str:
    """Why no RAW was found, said from the JPEG's side of the pair.

    `find_partner` is written for a RAW looking for its JPEG and this task calls
    it the other way round, so its own wording comes out backwards: "its RAW was
    not found - no JPEG anywhere in the library matches it". Turned round here
    rather than in pairs.py, because the reversal belongs to whoever did it.
    """
    if m.candidates > 1:
        return (f"{m.candidates} RAWs share its name, so which one is its RAW file "
                f"is not known")
    return "no RAW in the RAW tree matches it"


def _shot_key(path: str) -> tuple:
    """A develop-tree file as (its folder, its name without extension): the
    JPEG and the negative sent beside it share one."""
    return (os.path.normcase(os.path.dirname(path)),
            os.path.splitext(os.path.basename(path))[0].lower())


def plan(opts, progress=None) -> Plan:
    p = Plan(task="develop")
    scan = (opts.get("folder") or "").strip()
    out_tree = (opts.get("develop") or "").strip()
    raw_root = (opts.get("raw") or "").strip()

    if not scan or not os.path.isdir(scan):
        p.blocked = f"There is no folder at {scan!r}"
        return p
    if not out_tree:
        p.blocked = "Say where the photos to develop should go."
        return p
    if under(scan, out_tree) or under(out_tree, scan):
        p.blocked = ("The develop tree is inside the library (or the other way "
                     "round). It would then be scanned as if it were the library, "
                     "and every copy would be sent out again as an original.")
        return p

    library, refuse = mirror_anchor(_anchor(opts), scan, out_tree)
    if refuse:
        p.blocked = refuse
        return p
    raw_at = int(opts["raw_at_or_above"])
    jpeg_at = int(opts["jpeg_at_or_above"])
    if raw_at < 0 and jpeg_at < 0:
        p.blocked = ("Both thresholds say never, so nothing would be sent. Set at "
                     "least one of them to 1-5.")
        return p

    found = walk.walk(scan)
    for path, why in found.errors:
        p.errors.append(f"could not read {path}: {why}")

    # One reader for the whole run. Every photograph's rating, clock, keywords
    # and colour come out of the same two places - the front of the file and the
    # sidecar beside it - so they are fetched together instead of four times
    # over, and a file whose size, date and inode have not moved since the last
    # pass is not opened at all. That is where this task's half hour went.
    facts_for = facts.reader()

    raw_index = None
    if raw_at >= 0 and raw_root and os.path.isdir(raw_root):
        raw_walk = walk.walk(raw_root)
        for path, why in raw_walk.errors:
            p.errors.append(f"could not read {path}: {why}")
        raw_index = build_index(raw_walk.files, want=("raw",), reader=facts_for)

    # One preview per bracket means only the metered frame carries a star; the
    # rest of the set borrows it, or you send one exposure of three.
    sets = sets_for(found.files, opts, p, reader=facts_for)

    only_colour = str(opts.get("colour") or "").strip().lower()
    if only_colour and only_colour not in L.COLOURS:
        only_colour = ""
    want_tags = tags.wanted_list(opts.get("tags"))
    rule = (opts.get("tags_rule") or "only").strip()
    every_tag = bool(opts.get("tags_all"))

    # The colours that SEND. A rating says how good a photograph is; a colour
    # says what you want done with it, and those are different questions - a
    # frame can be worth sharpening without being worth five stars, and six
    # hundred timelapse stills are worth nothing individually and everything
    # together. Read once here rather than per photo, so changing what a colour
    # means changes it in one place.
    senders = {d.colour: d for d in L.defined() if d.defined and d.sends} \
        if bool(opts.get("labels", True)) else {}

    done = ledger.read()
    spot_done = bool(opts.get("spot_done", True))
    spotted = 0
    redo = ledger.again() if spot_done else set()
    wanted: dict = {}                      # where it should be -> where it is now
    in_scope: set = set()                  # (develop folder, name) of every pick
    photos = unrated = below = already = 0
    set_aside = 0                          # did not carry the tags asked for
    by_tag = 0                             # sent because of a tag, not a rating
    by_colour: dict = {}                   # sent because of a colour, and which
    on_offer: dict = {}                    # every tag seen, and how often

    for path in sorted(found.files):
        if kind(path) not in ("jpeg", "image"):
            continue
        photos += 1

        # Tags first, so a photo the filter excludes is counted once as excluded
        # rather than turning up in the unrated or already-developed tallies as
        # well and making three numbers that do not add up.
        carried = facts_for.tags(path) if want_tags else []
        matched = tags.hits(carried, want_tags) if want_tags else []
        enough = (len(matched) == len(want_tags)) if every_tag else bool(matched)
        if want_tags:
            for t in carried:
                on_offer[t] = on_offer.get(t, 0) + 1
            if rule == "only" and not enough:
                set_aside += 1
                continue

        take_for_tag = bool(want_tags) and rule == "also" and enough

        # What colour is on it, and therefore where it belongs. The colour wins
        # over the rating for the DESTINATION, because it is the more specific
        # statement: five stars says this is a good photograph, green says it is
        # one of six hundred frames of a timelapse, and only one of those two is
        # an instruction about which folder.
        wearing = facts_for.colour(path) if (senders or only_colour) else ""
        if only_colour and wearing != only_colour:
            # Narrowed to one colour: everything else is out, whatever its
            # rating. "Send me the sharpening pile" is a different question from
            # "send me the good photographs", and mixing the two answers gives
            # you a folder you have to sort again by hand.
            set_aside += 1
            continue
        mine = senders.get(wearing) if senders else None
        into = L.send_folder(mine, out_tree) if mine else out_tree
        # In this run's scope: whatever happens to it below, a copy of it on
        # the tablet is this run's to take back, and nothing else is.
        in_scope.add(_shot_key(mirror(path, library, into)))

        stars = facts_for.stars(path)
        if not stars and sets is not None:
            s = sets.set_of(path)
            if s and s.representative.path != path:
                stars = facts_for.stars(s.representative.path)
        if not stars and not take_for_tag and mine is None:
            unrated += 1
            continue
        stars = stars or 0

        cap = facts_for.capture(path)
        mark = ledger.key(identity(cap, path))

        # DONE, noticed rather than told. The ledger only learns a photo is
        # developed when File developed files its export - so an edit that
        # reached the library some other way (exported from Lightroom on the PC
        # straight into the shoot's Developed folder, filed by hand, filed
        # before the ledger existed) left the photo on the tablet for ever,
        # asking to be developed again. The edit is right there beside it, in
        # the one place filing would have put it; so look.
        if mark not in done and spot_done and mark not in redo:
            edits = developed_beside(path)
            if edits:
                spotted += 1
                done[mark] = {"on": "just now - an edit was found beside it"}
                p.rows.append(Row(
                    what="done", name=os.path.basename(path), source=path,
                    target=edits[0], size=0,
                    detail=(f"DONE - {os.path.basename(edits[0])} is already in "
                            f"{os.path.basename(os.path.dirname(edits[0]))}"),
                    cells=["", "done - edit found",
                           os.path.basename(edits[0])],
                    data={"action": "record",
                          "entry": {"key": mark, "name": os.path.basename(path),
                                    "original": path, "edit": edits[0],
                                    "how": "found beside it"}}))
                continue
        if mark in done:
            already += 1
            p.skipped.append((path,
                              f"{stars} star - developed already, on "
                              f"{done[mark].get('on', 'a previous run')}"))
            continue

        # A tag brings the JPEG, never the negative on its own: "also send my
        # Italy shots" should not quietly copy fifty megabytes each for photos
        # that were never rated highly enough to want one.
        send_jpeg = ((0 <= jpeg_at <= stars) or (take_for_tag and jpeg_at >= 0)
                     or mine is not None)
        send_raw = (0 <= raw_at <= stars) or (mine is not None and mine.raw)
        if not send_jpeg and not send_raw:
            below += 1
            continue

        why = f"{stars} star" if stars else "unrated"
        if matched:
            why += " - tagged " + ", ".join(matched)
        if mine is not None:
            why += f" - {mine.word.lower()}, {mine.name}"
            by_colour[mine.colour] = by_colour.get(mine.colour, 0) + 1
        if take_for_tag and not (0 <= jpeg_at <= stars):
            by_tag += 1

        if send_jpeg:
            wanted[mirror(path, library, into)] = (path, why, "the JPEG", stars)
        if send_raw and raw_index is not None:
            m = find_partner(path, cap, raw_index)
            if m.jpeg:                     # `jpeg` is "the partner found"
                target = os.path.join(os.path.dirname(mirror(path, library, into)),
                                      os.path.basename(m.jpeg))
                wanted[target] = (m.jpeg, why, "the RAW file", stars)
            else:
                # Name the MISSING NEGATIVE, not the JPEG. The JPEG is very
                # likely being sent two lines above, and listing it here as well
                # put the same file under "what would happen" and under "left
                # alone" at the same time - the app appearing to contradict
                # itself over something it had got right.
                stem = os.path.splitext(os.path.basename(path))[0]
                also = " The JPEG itself is still being sent." if send_jpeg else ""
                p.skipped.append((f"{stem} - the RAW file",
                                  f"{why}, but {_no_negative(m)}.{also}"))

    # ---- what to copy in
    sending = 0
    bytes_out = 0
    for target, (source, why, which, stars) in sorted(wanted.items()):
        if os.path.exists(target):
            continue
        size = 0
        try:
            size = os.path.getsize(source)
        except OSError:
            pass
        bytes_out += size
        sending += 1
        # Split into columns rather than one sentence per row. A list of four
        # hundred rows whose only readable part is a comma-separated phrase is a
        # list nobody reads - and the two questions anybody actually has of it,
        # "why is this going" and "is that the negative or the JPEG", are two
        # columns you can sort by and see down the page at a glance.
        p.rows.append(Row(what="send", name=os.path.basename(source), source=source,
                          target=target, size=size,
                          detail=f"{why} - {which}",
                          cells=[f"{stars} star" if stars else "unrated",
                                 why.split(" - ", 1)[1] if " - " in why
                                 else "its rating", which, _mb(size)],
                          data={"action": "copy", "from": source, "to": target}))

    # ---- and what to take out again
    taken = 0
    freed = 0
    if os.path.isdir(out_tree) and opts.get("prune", True):
        # Built from the same scope as `wanted`, or a run on one shoot, or on
        # one colour, takes every other shoot and colour off the tablet: only
        # the places this scan sends to, and - when a colour or tag narrows
        # the pick - only the copies of photographs that pick looked at.
        if only_colour:
            chosen = senders.get(only_colour)
            places = [L.send_folder(chosen, out_tree) if chosen else out_tree]
        else:
            places = [out_tree] + [L.send_folder(d, out_tree)
                                   for d in senders.values()]
        places = sorted({mirror(scan, library, d) for d in places})
        narrowed = bool(only_colour) or (bool(want_tags) and rule == "only")
        there = walk.walk(out_tree)
        for path in sorted(there.files):
            if path in wanted:
                continue
            if not any(under(path, d) for d in places):
                continue
            if narrowed and _shot_key(path) not in in_scope:
                continue
            size = 0
            try:
                size = os.path.getsize(path)
            except OSError:
                pass
            freed += size
            taken += 1
            p.rows.append(Row(
                what="take back", name=os.path.basename(path), source=path,
                target="", size=size,
                detail="developed, or no longer above its rating",
                cells=["", "developed, or no longer above its rating",
                       "taken back off the tablet", _mb(size)],
                data={"action": "remove", "from": path}))

    facts_for.save()
    p.columns = ["Photograph", "Rating", "Why it is going", "Which file", "Size"]
    p.stats = [
        ("Files opened", facts_for.said()),
        ("They land in", out_tree),
        ("Shaped like", library),
        ("Photos examined", f"{photos:,}"),
        ("To send", f"{sending:,}"),
        ("They weigh", _mb(bytes_out)),
        ("To take back", f"{taken:,}"),
        ("  freeing", _mb(freed)),
        ("Developed already", f"{already:,}"),
        ("Found done - an edit is beside it", f"{spotted:,}"),
        ("Below the thresholds", f"{below:,}"),
        ("Unrated - never sent", f"{unrated:,}"),
        ("Sent by colour", f"{sum(by_colour.values()):,}"),
        ("Folders unreadable", f"{len(found.errors):,}"),
    ]
    if want_tags:
        listed = ", ".join(want_tags)
        # "any of Italy" is what a template writes and a person never says.
        if len(want_tags) == 1:
            listed = f"tagged {listed}"
        else:
            listed = f"carrying {'all of' if every_tag else 'any of'} {listed}"
        if rule == "only":
            p.stats.insert(2, ("Left out, not tagged", f"{set_aside:,}"))
            p.notes.append(f"Only photos {listed} were considered. Rating still "
                           f"decides what is sent, and what kind.")
        else:
            p.stats.insert(2, ("Sent for a tag alone", f"{by_tag:,}"))
            p.notes.append(f"Photos {listed} were sent whatever their rating - the "
                           f"JPEG only. A RAW file still has to earn its place on "
                           f"rating.")
        nothing_matched = (rule == "only" and photos and set_aside == photos)
        if not on_offer:
            p.notes.insert(0, "None of the photos examined carry any tags at all - "
                              "not in a sidecar, not inside the file, not in "
                              "Windows' own Tags box. The filter therefore has "
                              "nothing to match on.")
        elif nothing_matched:
            top = sorted(on_offer.items(), key=lambda kv: (-kv[1], kv[0]))[:12]
            p.notes.insert(0, "Nothing carried those tags. The tags that ARE on "
                              "these photos: " + ", ".join(f"{t} ({n})"
                                                           for t, n in top))
    if senders:
        for colour, n in sorted(by_colour.items()):
            d = senders[colour]
            where = d.folder or "the develop tree itself"
            p.notes.append(f"{n} carrying {d.word} ({d.name}) -> {where}"
                           + (", with the RAW file." if d.raw
                              else ", the JPEG only."))
        if not by_colour:
            named = ", ".join(f"{d.word} = {d.name}" for d in senders.values())
            p.notes.append(f"Nothing in there carries a colour that sends. The "
                           f"ones that do: {named}. Setup > Colour meanings is "
                           f"where that is decided; the Apply label tab is "
                           f"where a folder gets marked.")
        p.notes.append(
            "A colour beats a rating over WHERE something goes - it is the more "
            "specific statement. Five stars says this is a good photo; "
            "green says it is one of six hundred frames of a timelapse, and only "
            "one of those is an instruction about which folder.")
    p.notes.append("Nothing is moved. Everything sent is a COPY - the library is "
                   "untouched, so a tablet that is lost or wiped costs you nothing.")
    p.notes.append("What has been developed is remembered by capture time, camera "
                   "and name, so a shoot you rename does not come back round again. "
                   "'File developed' is what writes that down.")
    if taken:
        p.notes.append(f"{taken} file(s) will be removed from the develop tree. That "
                       f"is the only place this tool ever deletes, and every one of "
                       f"them is a copy the library still has.")
    if raw_at >= 0 and raw_index is None:
        p.notes.append("No RAW tree was given, so only JPEGs can be sent. Point the "
                       "RAW tree box at it to send RAW files.")
    if p.errors:
        p.blocked = (f"{len(p.errors)} folder(s) could not be read. Part of the "
                     f"library was invisible, so what is missing from the develop "
                     f"tree cannot be trusted - and this tool deletes from it.")
    p.impact = _impact(sending, taken, spotted)
    return p


def _impact(sending: int, taken: int, spotted: int) -> dict:
    """The button's words, from what the rows actually are.

    "Copy 7 photographs" about seven files being taken back off the tablet was
    the sentence this replaces: every row was counted under the one verb.
    """
    if sending and taken:
        return {"verb": "Copy and take back", "count": sending + taken,
                "unit": "files"}
    if sending:
        return {"verb": "Copy", "count": sending, "unit": "files"}
    if taken:
        return {"verb": "Take back", "count": taken, "unit": "files",
                "into": []}
    return {"verb": "Mark as developed", "count": spotted,
            "unit": "photographs", "into": []}


def _mb(n: int) -> str:
    """A size, said in the unit it is actually in.

    "0 MB" against a row is a row you stop reading, and a page of them is a
    table that has told you nothing - which matters most for the small files,
    because a sidecar or a preview at "0 MB" looks like a mistake.
    """
    if n >= 1e9:
        return f"{n / 1e9:.2f} GB"
    if n >= 1e6:
        return f"{n / 1e6:.0f} MB"
    if n >= 1e3:
        return f"{n / 1e3:.0f} KB"
    return f"{n:,} bytes"


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result

    sent = taken = recorded = 0
    touched: set = set()
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        status = "OK"
        try:
            if row.data["action"] == "record":
                # Written only when the plan is carried out, never while
                # looking - a plan must not change what the next plan sees.
                if not ledger.add([row.data["entry"]]):
                    raise OSError("the list of developed photos could not be "
                                  "written")
                recorded += 1
            elif row.data["action"] == "copy":
                src, dst = row.data["from"], row.data["to"]
                if not os.path.isfile(src):
                    raise FileNotFoundError("it is no longer there")
                ensure_folder(os.path.dirname(dst))
                # copy2 keeps the timestamps, so the tablet sorts by capture date
                landed = safe_target(dst)
                shutil.copy2(src, landed)
                meter.copied(row.size)
                # A copy of your photograph is your photograph: it takes after
                # the ORIGINAL, not after whoever is running this. The tablet
                # syncs that tree as you, and cannot sync what it cannot read.
                perms.like(landed, src)
                sent += 1
            else:
                gone = row.data["from"]
                if os.path.isfile(gone):
                    os.remove(gone)
                    touched.add(os.path.dirname(gone))
                taken += 1
            result.done += 1
        except Exception as exc:                    # noqa: BLE001
            status = result.blame(row.name, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)

    removed = tidy_empty_folders(touched, stop_at=roots_of(plan.opts))
    result.stats = [("Sent to develop", f"{sent:,}"),
                    ("Found done and recorded", f"{recorded:,}"),
                    ("Taken back", f"{taken:,}"),
                    ("Failed", f"{result.failed:,}"),
                    ("Empty folders tidied", f"{removed:,}")]
    if not result.details:
        result.details.append(
            "The develop tree now holds exactly what is still waiting to be "
            "developed. Sync that folder to the tablet.")
    return result


register(Task(
    name="develop",
    fold_groups=True,
    line="Copy the photos worth developing out, and take the finished ones back.",
    verb="Copy",
    unit="photographs",
    undo="Copies. The originals stay where they are.",
    reads=('library', 'raw'),
    copies_to=('develop',),
    title="Send to develop",
    summary="Copies the photos worth developing into the develop tree, and "
            "removes the copies you have finished.",
    icon="send",
    # what survived, out to the tablet
    order=52,
    options=[
        Folder("folder", "Library", setting="library",
               help="The library to read ratings, colour labels and tags "
                    "from. Nothing here is moved or changed."),
        Number("raw_at_or_above", setting="develop_raw_at",
               label="Send RAW from (stars)", default=5,
               minimum=-1, maximum=5, group="What to send",
               help="A RAW file is sent when its photo has this many stars "
                    "or more. -1 to 5, default 5. -1 never sends a RAW file. "
                    "RAW files are large, so this is usually the top rating "
                    "only. From Setup by default."),
        Number("jpeg_at_or_above", setting="develop_jpeg_at",
               label="Send JPEG from (stars)", default=4,
               minimum=-1, maximum=5, group="What to send",
               help="A JPEG is sent when it has this many stars or more. -1 "
                    "to 5, default 4. -1 never sends a JPEG. Set it lower "
                    "than the RAW threshold to get the photos worth a look "
                    "without the large RAW files. From Setup by default."),
        Flag("prune", "Remove finished copies",
             default=True, setting="develop_prune", group="What to send",
             help="Removes a copy from the develop tree once its photo is "
                  "developed or no longer qualifies, so the tree holds only "
                  "what is still waiting. Only files inside the develop tree "
                  "are removed, and every one is a copy the library still "
                  "has. Only copies from the folder and colour this run "
                  "looks at are removed. On by default. From Setup by "
                  "default."),

        Choice("colour", "Only this colour", default="", setting="develop_colour",
               choices=lambda: [("", "Any - send by rating and tag as well")]
                               + [(d.colour, d.title()) for d in L.defined()
                                  if d.defined],
               group="Colour labels",
               help="Sends only photos carrying this colour label. Blank "
                    "means any colour. The meaning of each colour is set in "
                    "Setup > Colour meanings. From Setup by default."),
        Flag("spot_done", "Spot finished edits", default=True,
             help="Counts a photo as developed when its edit is already in "
                  "the shoot's Developed folder, even if File developed did "
                  "not put it there. The photo is recorded as done and its "
                  "copy is removed from the develop tree. On by default."),
        Flag("labels", "Follow colour labels", default=True,
             group="Colour labels", setting="develop_labels",
             help="Lets a colour label decide which photos are sent and to "
                  "which folder, as set in Setup > Colour meanings. A colour "
                  "label beats a rating over which folder a photo lands in. "
                  "Off, only ratings and tags decide. On by default. From "
                  "Setup by default."),

        Option("tags", "Only photos tagged", default="", kind="text", group="Tags",
               setting="develop_tags",
               help="Sends only photos carrying one of these tags, separated "
                    "by commas. Tags are read from the sidecar, from the "
                    "JPEG, from Windows Explorer's Tags box and from IPTC. A "
                    "level of a hierarchy matches: Italy finds "
                    "Travel|Italy|Rome. Blank means no tag filter. From "
                    "Setup by default."),
        Choice("tags_rule", "What the tags do", default="only", group="Tags",
               setting="develop_tags_rule",
               choices=[("only", "Narrow: only photos with the tags"),
                        ("also", "Widen: tagged photos too, any rating")],
               help="How the tags combine with the ratings. Narrow sends "
                    "only photos that qualify by rating and also carry a "
                    "tag. Widen sends everything that qualifies by rating, "
                    "plus every tagged photo whatever its rating, as a JPEG "
                    "only. From Setup by default."),
        Flag("tags_all", "Must have all tags", default=False,
             group="Tags", advanced=True, setting="develop_tags_all",
             help="A photo must carry every tag listed. Off, carrying any "
                  "one of them is enough. From Setup by default."),

        Flag("mirror", "Trees from Setup", default=True,
             group="Trees",
             help="On, the tree boxes below are ignored and the trees come "
                  "from Setup, so files land where every other tool puts "
                  "them. Off, the folders you type below are used for this "
                  "run only. Turning this off does not stop RAW files or "
                  "previews moving."),
        Folder("develop", "Develop tree", tree=True, default="",
               must_exist=False, setting="develop", group="Trees",
               help="The top of the develop tree. Sync this folder to the "
                    "tablet, with Syncthing or Synology Drive. It is made if "
                    "it does not exist yet."),
        Folder("raw", "RAW tree", tree=True, default="", must_exist=False,
               setting="raw", group="Trees",
               help="The top of the RAW tree, where RAW files are copied "
                    "from. Blank sends JPEGs only."),

        Flag("brackets", "Keep brackets together", setting="bracket_group",
             group="Brackets", advanced=True,
             help="Treats a bracket set as one photo: an unrated frame takes "
                  "the rating of its set, so the whole set is sent together "
                  "for blending. How a set is found is set in Setup > "
                  "Brackets. From Setup by default."),
    ],
    plan=plan,
    apply=apply,
))
