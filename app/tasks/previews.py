"""Make the small JPEGs you take away to rate, in a tree shaped like the library.

Previews are disposable by design. You sync them to a tablet, give them stars in
the evening, sync the ratings back with the 'ratings' task, and then the previews
can be thrown away and made again. Nothing in this app treats them as a record of
anything.

Two things they must carry, and both are easy to lose:

THE CAPTURE TIME AND CAMERA. That is what pairs a preview back to its original -
not its filename, and certainly not its position, since you will have reorganised
the library by then. A preview stripped of its EXIF is an orphan the moment you
rename a folder, and the ratings you made on it have nowhere to go.

THE ORIENTATION, APPLIED. A phone or a tilted camera writes the picture sideways
and an orientation tag saying "turn this". Resizing without honouring that gives
you a folder of sideways previews to rate.

ONE PREVIEW PER BRACKET. Three exposures of one scene are one decision, so only
the metered frame gets a preview. The rating you give it reaches all three later.

This is the one task that needs Pillow. Without it the task still tells you
exactly what it would do and then refuses, rather than half-running.
"""

from __future__ import annotations

import os

from app.grouping import sets_for
from app.registry import (Choice, Flag, Folder, Number, Option, Plan, Result,
                          Row, Task, register)
from core import facts, heif
from core import settings as _S
from core import perms
from core import tags, tagwrite, walk
from core.paths import mirror_anchor, ensure_folder, preview_for, under
from core.photo import is_picture
from core.replace import replace_file

# "Use what Setup says" is the first choice rather than an empty value, because a
# blank dropdown looks like something you forgot to fill in.
PROFILE_CHOICES = ([("saved", "Size from Setup")]
                   + [(k, _S.PROFILES[k]["label"]) for k in _S.PROFILE_ORDER])

INSTALL = ("This tool needs the Pillow imaging library, which is the only part of "
           "the app that is not plain Python.\n"
           "      Install it with:   pip install pillow\n"
           "      (on the NAS, inside the container, or run this tool on the PC "
           "and sync the previews across.)")



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

def _pillow():
    try:
        from PIL import Image, ImageOps          # noqa: F401
    except Exception:                            # noqa: BLE001
        return None, None
    heif.decoder()                               # so a HEIC opens like a JPEG
    return Image, ImageOps


# The one definition lives in core/paths, because culling and thinning need the
# same answer and got it slightly wrong on their own.
preview_target = preview_for


def _stale(source: str, target: str) -> bool:
    """A preview is out of date when it is older than the photo it came from."""
    try:
        return os.path.getmtime(target) < os.path.getmtime(source) - 1
    except OSError:
        return True


# How many bytes a pixel of output costs, if we have not measured yet. Only a
# starting point: how well a JPEG compresses depends entirely on the picture -
# noise costs four times what a clear sky does - so a table is a guess dressed
# up as arithmetic.
ROUGH_BYTES_PER_PIXEL = {60: 0.20, 70: 0.26, 80: 0.34, 85: 0.42, 90: 0.60, 95: 0.95}


def _pixels_out(source: str, edge: int) -> tuple[int, int]:
    """(pixels the preview will have, pixels the original has). 0 if unreadable."""
    Image, _ = _pillow()
    if Image is None:
        return 0, 0
    try:
        with Image.open(source) as im:
            wide, tall = im.size
    except Exception:                                  # noqa: BLE001
        return 0, 0
    if not wide or not tall:
        return 0, 0
    scale = min(1.0, edge / max(wide, tall))
    return int(wide * scale) * int(tall * scale), wide * tall


def measure_rate(sample: str, edge: int, quality: int) -> float:
    """Bytes per output pixel, MEASURED by making one preview and weighing it.

    A table of bytes-per-pixel by quality is a guess dressed up as arithmetic -
    checked against a real resize it came out four times under, because how well
    a JPEG compresses depends on the picture and nothing else. One of his own
    photos, put through the exact size and quality that is about to be used, is
    a far better predictor of the rest of his own photos than any constant could
    be. It costs one resize, in memory, during a preview that was going to read
    every file anyway.
    """
    Image, _ = _pillow()
    if Image is None:
        return 0.0
    try:
        import io
        with Image.open(sample) as im:
            im = im.convert("RGB")
            im.thumbnail((edge, edge))
            hold = io.BytesIO()
            im.save(hold, "JPEG", quality=int(quality))
            pixels = im.size[0] * im.size[1]
            return (hold.tell() / pixels) if pixels else 0.0
    except Exception:                                  # noqa: BLE001
        return 0.0


def _guess_bytes(source: str, edge: int, rate: float, quality: int) -> int:
    """Roughly how big this preview will come out.

    "Previews to make: 4,182" says nothing about whether the result fits
    anywhere. The long edge and the quality are on screen already and mean
    nothing to anybody; a number in megabytes is what the setting is for.
    """
    pixels, _ = _pixels_out(source, edge)
    if not pixels:
        return 0
    if rate <= 0:
        near = min(ROUGH_BYTES_PER_PIXEL, key=lambda q: abs(q - int(quality)))
        rate = ROUGH_BYTES_PER_PIXEL[near]
    return int(pixels * rate)


def _mb(n: int) -> str:
    if not n:
        return "?"
    if n >= 1_000_000:
        return f"{n / 1e6:.1f} MB"
    return f"{n / 1e3:.0f} KB"


def _wrong_size(target: str, source: str, edge: int) -> bool:
    """Was this preview made at a different size from the one now chosen?

    Without this, changing Large to Medium did nothing at all and said nothing
    either - existing previews are deliberately never replaced, so a settings
    change cannot wipe previews already rated, and the run correctly reported
    zero work. Correct, and indistinguishable from broken.

    Only the long edge is compared, because quality leaves no trace in the file
    to compare against. A preview whose original was smaller than the limit was
    never resized at all, so it is not wrong - just small.
    """
    Image, _ = _pillow()
    if Image is None:
        return False
    try:
        with Image.open(target) as im:
            made = max(im.size)
        if made == edge:
            return False
        with Image.open(source) as src:
            original = max(src.size)
    except Exception:                            # noqa: BLE001
        return False
    return made != min(edge, original)


def chosen_size(opts) -> tuple[int, int]:
    """Long edge and quality: this run's override, else whatever Setup says."""
    profile = str(opts.get("profile") or "").strip().lower()
    if profile and profile != "saved":
        s = _S.Settings(values={"preview_profile": profile,
                                "preview_long_edge": opts.get("long_edge") or 2048,
                                "preview_quality": opts.get("quality") or 85})
        return s.preview_size()
    return _S.load().preview_size()


def plan(opts) -> Plan:
    p = Plan(task="previews")
    scan = opts["folder"]
    previews = (opts.get("previews") or "").strip()

    if not scan or not os.path.isdir(scan):
        p.blocked = f"There is no folder at {scan!r}"
        return p
    if not previews:
        p.blocked = "Say where the previews should go."
        return p
    # After the two checks above, so "there is no folder at ''" is still the
    # answer to an empty box rather than a lecture about anchors.
    library, refuse = mirror_anchor(_anchor(opts), scan, previews)
    if refuse:
        p.blocked = refuse
        return p
    if under(scan, previews) or under(previews, library):
        p.blocked = ("The previews tree is inside the library (or the other way "
                     "round). Previews would then be scanned as if they were photos.")
        return p
    if library != scan and not under(scan, library):
        p.blocked = f"{scan!r} is not inside the library {library!r}."
        return p

    total_was = total_will = 0
    rate = -1.0                          # measured from the first photo, not guessed
    found = walk.walk(scan)
    for path, why in found.errors:
        p.errors.append(f"could not read {path}: {why}")

    # One reader for the run - see core/facts.py. Grouping reads every
    # picture's clock, and on a second pass over an unchanged shoot none
    # of them is opened.
    facts_for = facts.reader()
    sets = sets_for(found.files, opts, p, reader=facts_for)
    bracket_tag = str(opts.get("bracket_tag") or "").strip()
    rebuild = bool(opts["rebuild"])
    edge, quality = chosen_size(opts)

    photos = current = skipped_frames = wrong_size = 0
    for path in sorted(found.files):
        if not is_picture(path):
            continue
        photos += 1
        if sets is not None:
            s = sets.set_of(path)
            if s and s.representative.path != path:
                skipped_frames += 1
                p.skipped.append((path,
                                  f"one preview per bracket - {s.representative.name} "
                                  f"stands for this set"))
                continue
        if heif.named(path) and not heif.can_decode():
            p.skipped.append((path, heif.WITHOUT))
            continue
        target = preview_target(path, library, previews)
        why = ""
        if os.path.exists(target):
            if rebuild:
                why = "you asked for a rebuild"
            elif _stale(path, target):
                why = "the photo is newer than the preview"
            elif _wrong_size(target, path, edge):
                why = f"it was made at a different size - now {edge}px"
                wrong_size += 1
            else:
                current += 1
                continue
        was = 0
        try:
            was = os.path.getsize(path)
        except OSError:
            was = 0
        if rate < 0:                     # the first one we will actually make
            rate = measure_rate(path, edge, quality)
        will_be = _guess_bytes(path, edge, rate, quality)
        total_was += was
        total_will += will_be
        share = (f"  ~{round(100 * will_be / was)}% of the original"
                 if was and will_be else "")
        # What this preview should be findable by. A preview is disposable, but
        # while it exists it must answer to the same words as the photograph it
        # came from - otherwise "show me the brackets" gives a different answer
        # depending on which folder you happen to be standing in.
        carry = []
        if opts.get("carry_tags", True):
            carry = tags.tags_of(path)
            if sets is not None and sets.set_of(path) and bracket_tag:
                carry = tagwrite.keywords_for_preview(carry, [bracket_tag])
        p.rows.append(Row(
            what="preview", name=os.path.basename(path), source=path, target=target,
            size=will_be,
            detail=f"{_mb(was)} \u2192 about {_mb(will_be)}{share}   "
                   f"({edge}px long edge, quality {quality})"
                   + (f"  (replacing: {why})" if why else "")
                   + (f"   tags: {', '.join(carry)}" if carry else ""),
            cells=[_mb(was), _mb(will_be), f"{edge}px q{quality}",
                   ", ".join(carry), why],
            data={"from": path, "to": target, "tags": carry}))

    p.columns = ["File", "Was", "Will be", "Size", "Tags", "Replacing", "Where"]
    facts_for.save()
    p.stats = [
        ("Files opened", facts_for.said()),
        ("Photos examined", f"{photos:,}"),
        ("Previews to make", f"{len(p.rows):,}"),
        ("They will take about", _mb(total_will)
         + (f"  ({round(100 * total_will / total_was)}% of {_mb(total_was)})"
            if total_was and total_will else "")),
        ("Size", f"{edge}px at quality {quality}"),
        ("Sizes estimated", "by making one of your own photos and weighing it"
         if rate > 0 else "roughly - none could be read to measure from"),
        ("Already up to date", f"{current:,}"),
        ("Made at a different size", f"{wrong_size:,}"),
        ("Frames covered by their bracket", f"{skipped_frames:,}"),
        ("Folders unreadable", f"{len(found.errors):,}"),
    ]

    p.notes.append("Each preview keeps the capture time and camera of its original. "
                   "That is what carries your rating back afterwards, even if you "
                   "reorganise the library in between.")
    p.notes.append("Orientation is applied to the photo itself, so nothing arrives "
                   "on your tablet sideways.")
    if opts.get("carry_tags", True):
        p.notes.append(
            f"Each preview is given its original's tags"
            + (f", plus '{bracket_tag}' when it stands for a bracket set"
               if bracket_tag and sets is not None else "")
            + " - so the tablet, and anything you sort previews with, can find "
              "them by the same words as the library.")
    if sets is not None:
        p.notes.append("One preview per bracket - the metered frame. Rate it once and "
                       "the whole set is rated.")
    if wrong_size:
        p.notes.append(
            f"{wrong_size} preview(s) were made at a different size and will be "
            f"remade. Changing the size used to do nothing at all and say nothing "
            f"either, which looked exactly like the tool being broken.")
    if _pillow()[0] is None:
        p.blocked = INSTALL
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    Image, ImageOps = _pillow()
    if Image is None:
        result.details.append(INSTALL)
        return result
    if plan.blocked:
        result.details.append(plan.blocked)
        return result

    # the same call the plan made, so what was previewed is what gets built
    edge, quality = chosen_size(plan.opts)

    for i, row in enumerate(plan.rows, 1):
        if cancelled and cancelled():
            result.cancelled = True
            break
        src, dst = row.data["from"], row.data["to"]
        status = "OK"
        tmp = dst + ".part"
        try:
            with Image.open(src) as im:
                # exif_transpose applies the orientation AND clears the tag, so the
                # preview is not turned a second time by whatever opens it next.
                upright = ImageOps.exif_transpose(im)
                exif = upright.info.get("exif") or im.info.get("exif")
                if upright.mode not in ("RGB", "L"):
                    upright = upright.convert("RGB")
                upright.thumbnail((edge, edge), Image.LANCZOS)
                ensure_folder(os.path.dirname(dst))
                upright.save(tmp, "JPEG", quality=quality, optimize=True,
                             **({"exif": exif} if exif else {}))
            # Who the preview belongs to, before it is replaced - `os.replace`
            # puts a file this app wrote there, owned by this app, and a
            # previews tree that has quietly become root's is one the tablet
            # stops being able to sync.
            was, acl = perms.stat_of(dst), perms.xattrs_of(dst)
            replace_file(tmp, dst)                # only now does the old one go
            if was is not None:
                perms.restore(dst, was, acl)
            else:
                # A preview is GENERATED, so there is nothing of its own to put
                # back - it takes after the photograph it was made from, which
                # is a real file of the same kind with a real access list on it.
                perms.like(dst, src)
            # Keywords go on AFTER the file is in place, and a failure to write
            # them is reported without throwing the preview away: a preview with
            # no tags is still a preview you can rate, and losing the picture
            # over a keyword would be a bad trade.
            wanted = row.data.get("tags") or []
            if wanted:
                got = tagwrite.add(dst, wanted, in_sidecar=False)
                for why in got["errors"]:
                    result.details.append(f"{row.name}\n    tags: {why}")
            result.done += 1
        except Exception as exc:                # noqa: BLE001
            status = result.blame(src, exc)
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        if progress:
            progress(i, len(plan.rows), row.name, status)

    result.stats = [("Previews made", f"{result.done:,}"),
                    ("Failed", f"{result.failed:,}")]
    if not result.details:
        result.details.append(
            "Every preview carries its original's capture time and camera, so the "
            "ratings you make on them will find their way home.")
    return result


register(Task(
    name="previews",
    fold_groups=True,
    line="Small previews of your photos, for rating on the tablet away from the "
         "NAS.",
    verb="Create",
    unit="previews",
    undo="A preview is a copy. Deleting one loses nothing that is not "
         "still in the library.",
    reads=('library',),
    copies_to=('previews',),
    title="Make previews",
    summary="Makes small JPEG copies of the library, in the same folder "
            "shape, for rating on the tablet.",
    icon="image",
    # then the small JPEGs to rate away from the NAS
    order=32,
    options=[
        Folder("folder", "Folder to preview", setting="library",
               help="The folder to make previews of, a shoot or the whole "
                    "library."),
        Flag("mirror", "Trees from Setup", default=True,
             help="On, the tree boxes below are ignored and the trees come "
                  "from Setup, so files land where every other tool puts "
                  "them. Off, the folders you type below are used for this "
                  "run only. Turning this off does not stop RAW files or "
                  "previews moving."),
        Folder("previews", "Previews tree", tree=True, must_exist=False, setting="previews",
               help="The top of the previews tree. It is made if it does not "
                    "exist. It must not be inside the library."),

        Choice("profile", "Preview size", default="saved", choices=PROFILE_CHOICES,
               group="Size and quality",
               help="The size and JPEG quality of the previews. 'Size from "
                    "Setup' is the default. Pick another size here for this "
                    "one run only. A preview already made at a different "
                    "size is remade."),
        Number("long_edge", "Custom longest side (pixels)", default=2048,
               minimum=320, maximum=8000, group="Size and quality", advanced=True,
               help="The longest side of a custom preview, in pixels. 320 to "
                    "8000, default 2048. Only used when Preview size is "
                    "Custom."),
        Number("quality", "Custom JPEG quality", default=85, minimum=40, maximum=98,
               group="Size and quality", advanced=True,
               help="The JPEG quality of a custom preview. 40 to 98, default "
                    "85. Only used when Preview size is Custom."),

        Flag("brackets", "One preview per bracket", setting="bracket_group",
             group="Brackets",
             help="Makes a preview of only the metered frame of each bracket "
                  "set. Rating that preview rates the whole set. How a set "
                  "is found is set in Setup > Brackets. From Setup by "
                  "default."),
        Flag("carry_tags", "Copy tags to previews", default=True,
             group="Brackets",
             help="Writes each photo's tags into its preview, so a search on "
                  "the tablet finds the same photos as a search in the "
                  "library. On by default."),
        Option("bracket_tag", "Bracket tag", default="bracket",
               setting="bracket_tag", kind="text", group="Brackets",
               help="The tag written on the preview that stands for a "
                    "bracket set, so sets can be searched on the tablet. "
                    "Default bracket. Find brackets writes the same word on "
                    "the frames themselves. Blank writes nothing. From Setup "
                    "by default."),

        Flag("rebuild", "Remake every preview",
             group="Advanced", advanced=True,
             help="Remakes every preview, even one that already exists at "
                  "the right size. Rarely needed, because a size change is "
                  "noticed on its own. Off by default."),
    ],
    plan=plan,
    apply=apply,
))
