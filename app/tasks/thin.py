"""Put aside the spare frames of a bracket, keeping one.

Three exposures of one scene are one photograph and three files. Once the set has
served its purpose - you blended it, or you decided you never will - two of those
files are weight: on the NAS, in every backup, in every scan this app does, and
in every folder you scroll past looking for the picture.

**Which frame survives, Abu's rule:** the one you rated, if you rated one -
starring a frame is the clearest possible statement of which exposure you meant
to keep. Otherwise the metered frame, bias zero, which is what every other
feature here already treats as standing for the set. Both are printed on the row
before anything moves.

**Nothing is deleted.** The spares go into `_Culled`, inside their own tree, at
the position they had - exactly as culling by rating does, and recoverable by
moving them back. A bracket you thinned by mistake is a mistake; a bracket you
deleted by mistake is a photograph you no longer have.

**The whole shot moves.** The spare frame's negative goes with it, found by
identity wherever the RAW tree has it; its sidecar travels with it, or the rating
and location written there are lost silently; and its preview goes too, or the
previews tree keeps showing frames the library no longer has.

**A set that is only PROBABLE is left alone unless you say otherwise.** No bias
was recorded, so "three frames seconds apart" is what hand-bracketing looks like
- and also what three deliberate exposures of a changing scene look like. Thinning
those on a guess would put away photographs that were never a bracket at all.
"""

from __future__ import annotations

import os
import shutil

from app.grouping import sets_for
from app.registry import Flag, Folder, Plan, Result, Row, Task, register
from core import moves
from core import facts
from core import walk
from core.exifwrite import rating_of, sidecar_path
from core.pairs import build_index, find_partner
from core.paths import (CULLED, mirror_anchor, ensure_folder, mirror, preview_for,
                        relative_under, safe_target, tidy_empty_folders, roots_of, under)
from core.photo import read_capture



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

def _aside(path: str, tree_root: str) -> str:
    """Where a file goes when it is put aside: _Culled, at the same position."""
    rel = relative_under(path, tree_root)
    return safe_target(os.path.join(tree_root, CULLED, rel))


def keeper(members, rated: dict):
    """Which frame of a set survives, and why - in words that go on the row.

    Returns (frame, reason). The rated frame wins; if two frames are rated the
    highest-rated wins, and if THAT ties the metered one among them does - a tie
    broken by "whichever came first in the list" would put a different frame away
    depending on the order the disk handed the files over, which is not a rule
    anybody could predict or repeat.
    """
    starred = [m for m in members if rated.get(m.path)]
    if starred:
        best = max(rated[m.path] for m in starred)
        top = [m for m in starred if rated[m.path] == best]
        if len(top) == 1:
            return top[0], f"you rated it {best} star"
        metered = [m for m in top if getattr(m, "ev", None) == 0]
        if metered:
            return metered[0], (f"{len(top)} frames are rated {best} star; the "
                                f"metered one of them")
        return sorted(top, key=lambda m: m.path)[0], (
            f"{len(top)} frames are rated {best} star and none is the metered "
            f"one, so the first by name")
    return None, ""


def plan(opts, progress=None) -> Plan:
    p = Plan(task="thin")
    scan = opts["folder"]
    raw_root = (opts.get("raw") or "").strip()
    preview_root = (opts.get("previews") or "").strip()
    # Only a refusal when another tree is actually going to be
    # reached into: with neither given, nothing is measured from the
    # anchor and a guess costs nothing.
    library, refuse = mirror_anchor(_anchor(opts), scan,
                                    raw_root or preview_root)
    if refuse:
        p.blocked = refuse
        return p
    include_probable = bool(opts.get("probable"))

    if not scan or not os.path.isdir(scan):
        p.blocked = f"There is no folder at {scan!r}"
        return p
    if library != scan and not under(scan, library):
        p.blocked = f"{scan!r} is not inside the library {library!r}."
        return p

    found = walk.walk(scan)
    for path, why in found.errors:
        p.errors.append(f"could not read {path}: {why}")

    raw_index = None
    if raw_root and os.path.isdir(raw_root):
        got = walk.walk(raw_root)
        for path, why in got.errors:
            p.errors.append(f"could not read {path}: {why}")
        raw_index = build_index(got.files, want=("raw",))

    facts_for = facts.reader()
    sets = sets_for(found.files, {"brackets": True}, p, reader=facts_for,
                    probable=include_probable)
    p.columns = ["File", "Set", "Kept instead", "Why that one", "Rating",
                 "Moved aside as"]

    kept = spare = left = 0
    bytes_moved = 0
    for s in (sets.sets if sets else []):
        if progress:
            progress(kept + left + 1, len(sets.sets), s.label())
        if s.confidence == "probable" and not include_probable:
            left += 1
            p.skipped.append((s.label(),
                              "only PROBABLE - no exposure bias was recorded, so "
                              "this is either a hand-bracketed set or three "
                              "deliberate exposures. Left alone."))
            continue

        rated = {m.path: rating_of(m.path) or 0 for m in s.members}
        chosen, why = keeper(s.members, rated)
        if chosen is None:
            chosen, why = s.representative, "the metered frame - nothing is rated"
        kept += 1

        for m in s.members:
            if m.path == chosen.path:
                continue
            spare += 1
            stars = rated.get(m.path) or 0
            detail = (f"spare frame of {s.label()} - keeping {chosen.name} "
                      f"({why})")
            cells = [s.label(), chosen.name, why,
                     f"{stars} star" if stars else "unrated", CULLED]
            batch = [("JPEG", m.path, library),
                     ("sidecar", sidecar_path(m.path), library)]
            if preview_root:
                prev = preview_for(m.path, library, preview_root)
                batch.append(("preview", prev, preview_root))
                batch.append(("sidecar", sidecar_path(prev), preview_root))
            if raw_index is not None:
                found_raw = find_partner(m.path, read_capture(m.path), raw_index)
                if found_raw.jpeg:
                    batch.append(("RAW", found_raw.jpeg, raw_root))
                    batch.append(("sidecar", sidecar_path(found_raw.jpeg), raw_root))
                elif found_raw.candidates > 1:
                    p.skipped.append((m.path,
                                      f"its RAW is ambiguous - {found_raw.how}, so "
                                      f"the RAW file was left where it is"))

            for what, target, root in batch:
                if not target or not os.path.isfile(target):
                    continue
                size = os.path.getsize(target)
                bytes_moved += size
                away = _aside(target, root)
                p.rows.append(Row(
                    what=what, name=os.path.basename(target), source=target,
                    target=away, size=size, detail=detail, cells=cells,
                    data={"from": target, "to": away}))

    # Frames, as the button's unit says - not the files each one brings along.
    p.impact = {"count": spare}
    facts_for.save()
    p.stats = [
        ("Files opened", facts_for.said()),
        ("Photos examined", f"{sets.examined:,}" if sets else "0"),
        ("Bracket sets found", f"{len(sets.sets):,}" if sets else "0"),
        ("Sets to thin", f"{kept:,}"),
        ("Spare frames", f"{spare:,}"),
        ("Files to move aside, RAWs and sidecars included", f"{len(p.rows):,}"),
        ("Size", f"{bytes_moved / 1e9:.2f} GB" if bytes_moved > 1e9
         else f"{bytes_moved / 1e6:.0f} MB"),
        ("Sets left alone - only probable", f"{left:,}"),
        ("Folders unreadable", f"{len(found.errors):,}"),
    ]
    p.notes.append(f"Nothing is deleted. Every spare frame moves into a {CULLED} "
                   f"folder inside its own tree, keeping its position, so putting a "
                   f"set back together is a move.")
    p.notes.append("The frame kept is the one you rated, if you rated one - that is "
                   "the clearest statement of which exposure you meant. Otherwise "
                   "the metered frame, which is what every other tool here "
                   "already treats as standing for the set.")
    if not raw_root:
        p.notes.append("No RAW tree was given, so the RAW files of the spare frames "
                       "stay where they are - and the library will then have three "
                       "RAW files for one JPEG. Fill it in, or run Re-mirror after.")
    if not preview_root:
        p.notes.append("No previews tree was given. Any preview of a spare frame is "
                       "left behind, showing a photo the library no longer has "
                       "in that folder.")
    if left:
        p.notes.append(f"{left} set(s) are only PROBABLE and were left alone. Tick "
                       f"the box to include them - but look at them first: three "
                       f"frames seconds apart with no bias recorded is what "
                       f"hand-bracketing looks like, and also what three deliberate "
                       f"exposures of a changing scene look like.")
    if p.errors:
        p.blocked = (f"{len(p.errors)} folder(s) could not be read, so these are not "
                     f"all the sets there are - and thinning half a shoot leaves it "
                     f"in a state nobody can describe.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result

    touched: set = set()
    moved = 0
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        status = "OK"
        src, dst = row.data["from"], row.data["to"]
        try:
            if not os.path.isfile(src):
                raise FileNotFoundError("it is no longer there")
            moves.shift(result, src, dst)
            touched.add(os.path.dirname(src))
            moved += row.size or 0
            result.done += 1
        except Exception as exc:                    # noqa: BLE001
            status = result.blame(row.name, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)

    removed = tidy_empty_folders(touched, stop_at=roots_of(plan.opts))
    result.reclaimed, result.reclaim_kind = moved, "aside"
    result.stats = [("Files moved aside", f"{result.done:,}"),
                    ("Failed", f"{result.failed:,}"),
                    ("Empty folders tidied", f"{removed:,}")]
    if not result.details:
        result.details.append(
            f"Each set is one frame now. The spares are in a {CULLED} folder inside "
            f"their own tree, at the position they had - nothing was deleted.")
    return result


register(Task(
    name="thin",
    line="Keep one frame of each bracket set and move the spares aside.",
    verb="Move aside",
    unit="frames",
    undo="They are moved into a pile, not deleted. Clean up is the "
         "only tool that finally removes them, and it tells you how "
         "much came back.",
    reads=('library', 'raw', 'previews'),
    moves_to=('library',),
    title="Thin brackets",
    summary="Keeps one frame of each bracket set, the rated or the metered "
            "one, and moves the rest to _Culled.",
    icon="scissors",
    # one frame per bracket, now that they are rated
    parent="cull",
    tab="Thin brackets",
    order=40,
    options=[
        Folder("folder", "Folder to thin", setting="library",
               help="The folder to thin, a shoot or the whole library. Only "
                    "bracket sets are touched. A single frame is never "
                    "moved."),
        Flag("probable", "Include probable sets", default=False,
             help="Also thins probable sets: frames seconds apart with no "
                  "exposure bias recorded, which could be hand-bracketing or "
                  "three deliberate photos of a changing scene. Off by "
                  "default. Look at the list first."),

        Flag("mirror", "Trees from Setup", default=True,
             group="Companion files",
             help="On, the tree boxes below are ignored and the trees come "
                  "from Setup, so files land where every other tool puts "
                  "them. Off, the folders you type below are used for this "
                  "run only. Turning this off does not stop RAW files or "
                  "previews moving."),
        Folder("raw", "RAW tree", tree=True, default="", must_exist=False,
               setting="raw", group="Companion files",
               help="The top of the RAW tree. A spare frame's RAW file is "
                    "moved to the matching _Culled folder here. Blank leaves "
                    "RAW files alone, which gives several RAW files for one "
                    "kept JPEG. Ignored while Trees from Setup is on."),
        Folder("previews", "Previews tree", tree=True, default="",
               must_exist=False, setting="previews", group="Companion files",
               help="The top of the previews tree. A spare frame's preview "
                    "is moved to the matching _Culled folder here. Blank "
                    "leaves previews alone, so the tablet still shows the "
                    "spare frames. Ignored while Trees from Setup is on."),
    ],
    plan=plan,
    apply=apply,
))
