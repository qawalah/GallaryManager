"""Take Lightroom's exports and put each one beside the photo it came from.

Lightroom on Android writes everything into ONE folder. That folder syncs back
to the NAS and is then a flat heap of exports with no relation to the library's
shape - which is the opposite of everything else here.

So each export is matched to its original **by identity** - capture time, camera
and base name, the same three things a RAW is paired by - and filed where that
original lives. A path could not do it: the exports have no path to speak of.

**Two things this must not do.**

A Lightroom export of `P1000123.RW2` comes out as `P1000123.jpg`: same name,
same capture time, same camera as the original JPEG already in that folder. To
the rest of this app it is that photo. Dropped straight into the shoot folder it
would be counted as a second photograph, judged as a duplicate, and paired
against the RAW. So it goes in a subfolder of its own by default, and that
folder name is one the app already knows to leave alone.

And it must not guess. An export whose original cannot be found is left exactly
where it is and named - never filed somewhere plausible, because "plausible" for
a photograph means a folder you will never think to look in.

Filing an export is also what records the photo as DEVELOPED, which is what
takes it off the tablet on the next send.
"""

from __future__ import annotations

import os
import shutil

from app.registry import (Choice, Flag, Folder, Option, Plan, Result, Row,
                          Task, register)
from core import facts, meter
from core import cleanup, moves, perms
from core import ledger, walk
from core.pairs import build_index, find_partner, identity
from core.paths import anchor_for, ensure_folder, safe_target, under
from core.photo import kind, read_capture

WHERE = [
    ("subfolder", "A subfolder of the shoot"),
    ("beside", "Beside the original"),
]


def _same_file(a: str, b: str) -> bool:
    """Is what is already filed there this very export, arriving again?

    The export folder is a ONE-WAY sync from the tablet, and one-way means the
    tablet keeps its copy: moving the file out of the inbox here can have it
    pushed back on the next sync, whereupon it would be filed a second time and
    land beside the first as "photo (1).jpg". A week of that is a shoot folder
    full of numbered copies of one photograph.

    Name and size, not content: an export that came back byte-identical is the
    sync doing its job, and an export you deliberately made again after more
    editing is a different number of bytes and SHOULD land. Hashing every pair
    would be minutes of reading to separate those two, and the answer would be
    the same one.
    """
    try:
        return os.path.getsize(a) == os.path.getsize(b)
    except OSError:
        return False


def plan(opts, progress=None) -> Plan:
    p = Plan(task="filed")
    inbox = (opts.get("inbox") or "").strip()
    library = (opts.get("folder") or "").strip()
    where = str(opts.get("where") or "subfolder")
    into = (opts.get("subfolder") or "Developed").strip() or "Developed"
    tidy = bool(opts.get("tidy_resync", True))

    if not inbox or not os.path.isdir(inbox):
        p.blocked = (f"There is no folder at {inbox!r}. This is the folder "
                     f"Lightroom exports into on the tablet, synced back to the NAS.")
        return p
    if not library or not os.path.isdir(library):
        p.blocked = f"There is no library at {library!r}"
        return p
    if under(inbox, library):
        p.blocked = ("The exports folder is inside the library, so every export "
                     "would be read as an original photo and matched against "
                     "itself. Keep it outside.")
        return p

    exports = walk.walk(inbox)
    lib = walk.walk(library)
    for path, why in exports.errors + lib.errors:
        p.errors.append(f"could not read {path}: {why}")

    # Only the names that could possibly be asked about.
    #
    # This used to read the EXIF of every photograph in the library before it
    # could place five exports - minutes of opening files over a share to answer
    # a question about a handful of them. Every tier of find_partner keys on the
    # base name, so a photograph whose name is not among the exports' can never
    # be the answer, and reading it is work whose result cannot be used.
    from core.pairs import base_name
    looking_for = {base_name(x) for x in exports.files
                   if kind(x) in ("jpeg", "image")}
    facts_for = facts.reader()
    originals = build_index(lib.files, want=("jpeg", "image", "raw"),
                            reader=facts_for,
                            names=looking_for,
                            progress=(lambda i, n, x: progress(i, n, x, "OK"))
                            if progress else None)

    filed = lost = ambiguous = again = 0
    marks = []
    for path in sorted(exports.files):
        if kind(path) not in ("jpeg", "image"):
            continue
        cap = facts_for.capture(path)
        m = find_partner(path, cap, originals)
        if not m.jpeg:
            if m.candidates > 1:
                ambiguous += 1
                p.skipped.append((path,
                                  f"more than one photo in the library looks like "
                                  f"this - {m.how} - so filing it would be a guess"))
            else:
                lost += 1
                p.skipped.append((path,
                                  "nothing in the library matches it, so it was "
                                  "left where it is"))
            continue

        home = os.path.dirname(m.jpeg)
        if where == "subfolder":
            home = os.path.join(home, into)
        target = os.path.join(home, os.path.basename(path))

        # Already filed, and here again because the sync put it back.
        if os.path.isfile(target) and _same_file(path, target):
            again += 1
            if tidy:
                p.rows.append(Row(
                    what="already filed", name=os.path.basename(path),
                    source=path, target="", size=0,
                    detail=f"already filed, in {os.path.dirname(target)} - this "
                           f"copy came back with the sync and is being taken out "
                           f"of the export folder",
                    data={"from": path, "to": "", "drop": True}))
            else:
                p.skipped.append((path,
                                  f"already filed in {os.path.dirname(target)}, "
                                  f"same size - the tablet's sync put this copy "
                                  f"back. Left where it is."))
            continue
        # A DIFFERENT file of the same name already filed there: you exported
        # this photograph again after more editing. Both are kept - the newer
        # one lands numbered - but the plan has to say so, or it shows a name
        # and writes another one.
        second = os.path.isfile(target)
        filed += 1
        marks.append({"key": ledger.key(identity(cap, path)),
                      "name": os.path.basename(path),
                      "original": m.jpeg})
        size = 0
        try:
            size = os.path.getsize(path)
        except OSError:
            pass
        p.rows.append(Row(
            what="file", name=os.path.basename(path), source=path, target=target,
            size=size,
            detail=f"developed from {os.path.basename(m.jpeg)}  ({m.how})"
                   + (" - a different version is already filed there, so this "
                      "one lands beside it under a numbered name; neither is "
                      "replaced" if second else ""),
            data={"from": path, "to": target,
                  "mark": marks[-1] if marks else None}))

    # Only the rows that file something count as "File". The others take a copy
    # the sync brought back out of the export folder, and calling those filed
    # was a number larger than what would land in the library.
    dropped = sum(1 for r in p.rows if (r.data or {}).get("drop"))
    if filed:
        p.impact = {"count": filed}
    elif dropped:
        p.impact = {"verb": "Take out", "count": dropped,
                    "unit": "returned copies", "into": []}
    facts_for.save()
    p.stats = [
        ("Files opened", facts_for.said()),
        ("Exports found", f"{filed + lost + ambiguous + again:,}"),
        ("To file", f"{filed:,}"),
        ("Back again from the sync", f"{again:,}"),
        ("No original found", f"{lost:,}"),
        ("Ambiguous - left alone", f"{ambiguous:,}"),
        ("Already recorded as developed", f"{len(ledger.read()):,}"),
    ]
    p.notes.append("Each export is matched to its original by capture time, camera "
                   "and name - it has no path of its own to go by, and Lightroom "
                   "writes them all into one folder.")
    if where == "subfolder":
        p.notes.append(f"They go into a '{into}' subfolder of the shoot. An export "
                       f"has the same name, time and camera as the original JPEG, so "
                       f"dropped in beside it the rest of this app would count it as "
                       f"a second photo and call it a duplicate.")
    else:
        p.notes.append("Filing them beside the originals means an export shares its "
                       "original's name, time and camera in the same folder - expect "
                       "'Find duplicates' to have opinions about that.")
    p.notes.append("Filing one records it as developed, which is what takes it off "
                   "the tablet the next time you send.")
    if again:
        p.notes.append(
            f"{again} export(s) are already filed and arrived again - the export "
            f"folder is a one-way sync, so the tablet keeps its copy and can push "
            f"it back. They are "
            + ("being taken out of the export folder rather than filed a second "
               "time." if tidy else "left where they are.")
            + " Without this they would land beside the first as 'photo (1).jpg', "
              "over and over.")
    if any(" already filed there" in r.detail for r in p.rows):
        p.notes.append(
            "Some of these have a version filed already and a different number "
            "of bytes - which is you exporting a photo again after more "
            "work, not the sync. Both are kept: nothing filed is ever replaced.")
    if lost:
        p.notes.append(f"{lost} export(s) matched nothing and were left where they "
                       f"are. Nothing is ever filed on a guess - a photo in a "
                       f"plausible folder is a photo you will not find again.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result

    keep = bool(plan.opts.get("keep_exports", False))
    marks = []
    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        status = "OK"
        try:
            src, dst = row.data["from"], row.data["to"]
            if not os.path.isfile(src):
                raise FileNotFoundError("it is no longer there")
            if row.data.get("drop"):
                # Already filed. Removing the copy in the EXPORT folder, which
                # is a working folder the tablet refills - never anything in the
                # library, and the filed one is untouched. Into the share's
                # Recycle Bin where there is one, as a recorded move, so Put it
                # back can return it too.
                bin_folder = cleanup.recycle_root(src)
                if bin_folder:
                    moves.shift(result, src,
                                cleanup.recycle_target(src, bin_folder))
                else:
                    os.remove(src)
                result.done += 1
                if progress:
                    progress(i, len(plan.rows), row.name, status)
                continue
            if keep:
                ensure_folder(os.path.dirname(dst))
                dst = safe_target(dst)
                shutil.copy2(src, dst)
                meter.copied(row.size)
            else:
                # Written down as it is made, so History can put it back.
                dst = moves.shift(result, src, dst)
            # An export arrives from the tablet's sync folder, owned by whatever
            # put it there. Landing in the library it should look like the
            # photograph it came from - which is a real file, in the right
            # place, with the right access list on it.
            born = (row.data.get("mark") or {}).get("original") or ""
            if born and os.path.exists(born):
                perms.like(dst, born)
            else:
                perms.like_parent(dst)
            if row.data.get("mark"):
                marks.append(row.data["mark"])
            result.done += 1
        except Exception as exc:                    # noqa: BLE001
            status = result.blame(row.name, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)

    # Only what actually landed is recorded. Marking a photo developed when its
    # export failed to move would take it off the tablet with the work not done.
    written = ledger.add(marks)
    result.stats = [("Filed", f"{result.done:,}"),
                    ("Recorded as developed", f"{written:,}"),
                    ("Failed", f"{result.failed:,}")]
    if not result.details:
        result.details.append(
            "Each one is beside the photo it came from, and recorded as developed - "
            "so the next 'Send to develop' takes it off the tablet.")
    return result


register(Task(
    name="filed",
    line="Match Lightroom's exports to their originals, and file them.",
    verb="File",
    unit="edited versions",
    reads=('inbox', 'library'),
    moves_to=('library',),
    title="File developed",
    summary="Matches Lightroom's exports to their originals, files them into "
            "the library and records them as developed.",
    icon="inbox",
    # and back again
    parent="develop",
    tab="File developed",
    order=56,
    options=[
        Folder("inbox", "Lightroom's export folder", default="", setting="inbox",
               help="The folder Lightroom on the tablet exports into, synced "
                    "back to the NAS. Keep it outside the library, or every "
                    "export is read as an original photo. From Setup by "
                    "default."),
        Folder("folder", "Library", setting="library",
               help="Where the originals are looked for, by capture time, "
                    "camera and name, wherever they sit and whatever they "
                    "were renamed."),
        Choice("where", "Export destination", default="subfolder", choices=WHERE,
               setting="filed_where",
               help="Where an export is filed once its original is found. A "
                    "subfolder keeps the shoot folder for camera files only. "
                    "Beside the original, the rest of the app counts the "
                    "export as a second photo with the same name, time and "
                    "camera. From Setup by default."),
        # A NAME, not a path - it is joined onto whichever shoot folder each
        # export belongs to. As a folder box it also got a Browse button and,
        # worse, the path guard resolved "Developed" against the container's
        # working directory, decided it was outside the allowed folders, and
        # refused the whole task.
        Option("subfolder", "Subfolder name", default="Developed", kind="text",
               setting="filed_into",
               help="The name of the subfolder, default Developed. A name, "
                    "not a path: it is made inside whichever shoot each "
                    "export belongs to. The name is also added to the "
                    "folders the app never scans, so exports are not read as "
                    "originals. From Setup by default, and automation uses "
                    "the same one."),
        Flag("tidy_resync", "Clear re-synced copies",
             default=True, advanced=True, group="Advanced",
             setting="filed_tidy_resync",
             help="Removes an export from the export folder when the same "
                  "file was already filed, because the tablet can sync its "
                  "copy back again. Only the export folder is touched, never "
                  "the library. Off, such copies are listed and left, and "
                  "the export folder slowly fills. On by default. From Setup "
                  "by default."),
        Flag("keep_exports", "Keep the export", default=False,
             advanced=True, group="Advanced", setting="filed_keep",
             help="Copies each export into the library instead of moving it. "
                  "Off by default: the export is moved and the export folder "
                  "empties for the next round. From Setup by default."),
    ],
    plan=plan,
    apply=apply,
))
