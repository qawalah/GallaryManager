"""What each of the five colours means. One place, so a colour keeps its meaning.

A rating says how good a photograph is. A colour says what you want done with
it, and this is where you write down what each one is for: a name, whatever
extra tags should go on the file so other programs can find it, and whether
photographs carrying it get sent out - and into which folder.

This is a settings tab. Applying it writes the settings file and touches no
photograph. Everything that acts on a colour reads from here, so changing what
purple means changes it everywhere at once, rather than in the seven forms where
it had been typed.

**The colour word is what goes into the file.** `xmp:Label` holds "Red", not
"Edit" - that is what Lightroom, Bridge, darktable and digiKam expect, and it is
the only way the colour swatch you were aiming for actually appears in them.
Your name for it is written as a KEYWORD beside it, which is the part that is
searchable in Synology Photos, in Explorer's Tags column and in anything reading
IPTC. Add as many more tags per colour as you like: that is what makes a
colour readable by a program that has never heard of this app.
"""

from __future__ import annotations

from app.registry import Choice, Flag, Option, Plan, Result, Row, Task, register
from core import labels as L
from core import settings as S

FIELDS = [f"label_{c}_{part}" for c in L.COLOURS
          for part in ("name", "keywords", "action", "folder", "raw")]

ACTION_CHOICES = [(k, v) for k, v in L.ACTIONS.items()]


def plan(opts) -> Plan:
    p = Plan(task="labels")
    saved = S.load()
    changed = 0
    p.columns = ["Colour", "Means", "Writes the tags", "What happens"]
    for d in L.defined(S.Settings(values={**saved.values, **opts})):
        was = str(saved[f"label_{d.colour}_name"] or "").strip()
        if was != d.name:
            changed += 1
        if d.sends:
            where = d.folder or "the develop tree itself"
            what = f"sent out to {where}" + (" , with its RAW" if d.raw else "")
        elif d.defined:
            what = "marked only - nothing is moved"
        else:
            what = "not defined yet, so nothing reads it"
        p.rows.append(Row(
            what="label", name=d.word,
            source=d.name or "(not defined)", target="",
            detail=f"{d.name or 'not defined'} - {what}",
            cells=[d.name or "(not defined)",
                   ", ".join(d.all_keywords()) or "none", what],
            data={"colour": d.colour}))

    p.stats = [
        ("Colours defined", f"{sum(1 for d in L.defined() if d.defined):,} of 5"),
        ("Names changed", f"{changed:,}"),
        ("Settings file", saved.path),
    ]
    p.notes.append(
        "The colour WORD is what goes into the file - xmp:Label holds 'Red', "
        "never 'Edit'. That is what Lightroom, Bridge, darktable and digiKam "
        "read, and writing your own word there gives you a custom label nothing "
        "else recognises and no coloured swatch anywhere.")
    p.notes.append(
        "Your name for a colour is written as a tag instead, along with any "
        "others you list. That is the half other programs can act on: a tag "
        "is searchable in Synology Photos, in Explorer's Tags column and in "
        "anything that reads IPTC.")
    p.notes.append(
        "Labels written elsewhere are understood on the way in. Bridge ships "
        "with Select / Second / Approved / Review / To Do rather than colour "
        "names, and a library labelled there reads correctly here without being "
        "relabelled.")
    p.notes.append(
        "A folder name sends that colour into a folder of its own inside the "
        "develop tree, which is what keeps six hundred timelapse stills out of "
        "tonight's edits. Blank means the develop tree itself.")
    p.notes.append("Nothing here touches a photo. Applying writes the "
                   "settings file, and Apply label and Send to develop read it.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    try:
        saved = S.save({k: plan.opts[k] for k in FIELDS if k in plan.opts})
        result.done = len(plan.rows)
        result.stats = [("Colours saved", f"{result.done:,}"),
                        ("Written to", saved.path)]
        result.details.append(
            "Set a colour on a folder from the Apply label tab; Send to "
            "develop reads the actions above every time it runs.")
    except Exception as exc:                        # noqa: BLE001
        result.failed = 1
        result.details.append(f"could not write the settings: {exc}")
    return result


def _options() -> list:
    out = []
    for colour in L.COLOURS:
        word = L.WORD[colour]
        group = f"{word}"
        out.append(Option(f"label_{colour}_name", "Meaning", default="", kind="text",
                          group=group, setting=f"label_{colour}_name",
                          help=f"What {word.lower()} means to you, for example "
                               f"Edit, Sharpen or Timelapse. The word is "
                               f"written on the photo as a tag, so other "
                               f"programs can search for it. Blank means "
                               f"{word.lower()} does nothing."))
        out.append(Option(f"label_{colour}_keywords", "Extra tags",
                          default="", kind="text", group=group,
                          setting=f"label_{colour}_keywords",
                          help="More tags written together with the meaning, "
                               "separated by commas. Use the words another "
                               "program searches for, so it can find these "
                               "photos without knowing this app. Blank adds "
                               "none."))
        out.append(Choice(f"label_{colour}_action", "Action",
                          default="none", choices=ACTION_CHOICES, group=group,
                          setting=f"label_{colour}_action",
                          help=f"What Send to develop does with photos "
                               f"carrying {word.lower()}. Send copies them "
                               f"into the develop tree on its next run. "
                               f"Nothing else is ever moved because of a "
                               f"colour label."))
        out.append(Option(f"label_{colour}_folder", "Develop subfolder", default="",
                          kind="text", group=group,
                          setting=f"label_{colour}_folder",
                          help="A folder name inside the develop tree, for "
                               "example Timelapse or Print. Blank sends the "
                               "photos into the develop tree itself. A name "
                               "of its own keeps hundreds of timelapse "
                               "frames apart from the photos you are "
                               "editing."))
        out.append(Flag(f"label_{colour}_raw", "Send the RAW file", default=False,
                        group=group, setting=f"label_{colour}_raw",
                        help="Also copies the RAW file into the develop "
                             "tree. RAW files are large, so turn this on "
                             "only for photos you will develop fully, not "
                             "for a timelapse or a sharpening pass. Off by "
                             "default."))
    return out


register(Task(
    name="labels",
    line="What each colour means, what it writes, and where it sends.",
    title="Colour meanings",
    summary="Sets what each of the five colour labels means, which tags it "
            "writes and where its photos go.",
    icon="tag",
    parent="setup",
    tab="Colour meanings",
    settings=True,
    writes=False,
    order=93,
    options=_options(),
    plan=plan,
    apply=apply,
))
