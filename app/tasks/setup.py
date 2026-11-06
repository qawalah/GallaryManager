"""The things you set once, and what they do everywhere else.

Two jobs.

**The three trees.** Typing `N:\\Photos` into seven forms is how they end up
subtly different in each - one with a trailing slash, one pointing at a shoot
instead of the tree root - and mirroring against the wrong root is precisely the
mistake that scatters files. Set them here and every task starts with them filled
in; you can still override any of them for a single run.

**What counts as a bracket.** Finding brackets was a feature of its own for a
while, and it should not have been: nobody wants to *find brackets*, they want
previews and culls that treat a set as one thing. So the settings live here, once,
and previews, ratings and cull all read them. The one thing worth doing on this
tab is checking them - point it at a folder you know and see whether the sets it
draws are the sets you shot.

Applying this writes the settings file. It never touches a photo.
"""

from __future__ import annotations

import os

from app.registry import (Choice, Flag, Folder, Folders, Number, Option, Plan,
                          Result, Row, Task, register)
from core import brackets as B
from core import settings as S
from core import walk

PROFILE_CHOICES = [(k, S.PROFILES[k]["label"]) for k in S.PROFILE_ORDER]


def _colours():
    """The five, as they are defined right now. Late, because Setup is imported
    while the settings module is still being set up."""
    from core import labels as _l
    return _l.defined()

# The settings this tab owns, and the option each one is edited by.
FIELDS = ["library", "raw", "previews", "video",
         "bracket_group", "bracket_gap", "bracket_min_set", "bracket_max_set",
         "bracket_probable",
         "preview_profile", "preview_long_edge", "preview_quality",
         "thumb_keep",
         "ignore", "develop", "inbox", "filed_where", "filed_into",
         "develop_raw_at", "develop_jpeg_at", "develop_prune",
         "develop_tags", "develop_tags_rule", "develop_tags_all",
         "develop_colour", "develop_labels",
         "filed_keep", "filed_tidy_resync",
         "bracket_tag", "place_names", "exclude",
         "server_name", "discovery", "public_port",
         "key_info", "key_histogram", "quick_tags", "developer"]


def plan(opts) -> Plan:
    p = Plan(task="setup")
    saved = S.load()

    # Not an error. The RAW and previews trees are CREATED by the tasks that fill
    # them, so a path that does not exist yet is the normal state on day one. Only
    # the library has to be somewhere real, because nothing creates it.
    for key, label in (("raw", "RAW tree"), ("previews", "previews tree")):
        folder = (opts.get(key) or "").strip()
        if folder and not os.path.isdir(folder):
            p.notes.append(f"The {label} is not there yet. That is fine - it is made "
                           f"the first time something writes to it.")
    library = (opts.get("library") or "").strip()
    if library and not os.path.isdir(library):
        p.blocked = (f"There is no library at {library!r}. Nothing creates the "
                     f"library, so a path that is not there is a typo.")
        return p

    if int(opts["bracket_min_set"]) > int(opts["bracket_max_set"]):
        p.blocked = ("The smallest bracket set is larger than the largest, so no set "
                     "could ever qualify.")
        return p

    changes = 0
    for name in FIELDS:
        was, now = saved[name], opts[name]
        if str(was) != str(now):
            changes += 1
            p.rows.append(Row(what="setting", name=name, source=str(was),
                              target=str(now),
                              detail=f"{was!r}  ->  {now!r}",
                              data={"name": name, "value": now}))

    # A check, not a task: point it at a folder you know and see what it makes of it.
    check = (opts.get("check") or "").strip()
    if check:
        if not os.path.isdir(check):
            p.errors.append(f"nothing to check at {check!r}")
        else:
            found = walk.walk(check)
            got = B.find(found.files,
                         max_gap_seconds=float(opts["bracket_gap"]),
                         min_set=int(opts["bracket_min_set"]),
                         max_set=int(opts["bracket_max_set"]),
                         include_probable=bool(opts["bracket_probable"]))
            in_sets = sum(s.size for s in got.sets)
            p.notes.append(
                f"Checked against {check}: {got.examined:,} photos, "
                f"{len(got.sets):,} bracket set(s) ({got.certain:,} certain, "
                f"{got.probable:,} probable), {in_sets:,} frames inside a set, "
                f"{got.examined - in_sets:,} loose.")
            for s in got.sets[:40]:
                evs = ", ".join(f"{e:+g}" for e in s.evs) if s.evs else "no bias recorded"
                p.skipped.append((s.label(),
                                  f"{s.confidence}: {s.size} frames [{evs}], "
                                  f"keeps {s.representative.name} - {s.why}"))
            if not got.sets:
                p.notes.append("Nothing in that folder looks like a bracket. If you "
                               "know there are some, widen the gap or turn on the "
                               "hand-bracketed sets and check again.")

    edge, quality = S.Settings(values=dict(opts)).preview_size()
    # Which folders this copy may touch at all.
    #
    # It used to be a sentence of grey text in the header, between the app's
    # name and its buttons, saying the same thing every day and squeezing
    # everything else on a narrow screen. It belongs here: a restriction set by
    # whoever started the app is a fact you go LOOKING for, not one you read
    # four hundred times.
    from app import server as _srv
    fenced = list(getattr(_srv, "ALLOWED_ROOTS", []) or [])
    # A PC program with no ALLOWED_ROOTS is fenced to the boxes on this tab,
    # as they are about to be saved (app.server.fence).
    from core import desktop as _desk
    by_setup = not fenced and _desk.as_program()

    p.stats = [
        ("Settings changed", f"{changes:,}"),
        ("Folders this copy may touch",
         "   ".join(fenced) if fenced else
         "the folders above, and Also allowed" if by_setup else
         "anywhere on this machine"),
        ("Bracket grouping", "on" if opts["bracket_group"] else "off"),
        ("Previews", f"{edge}px at quality {quality}"),
        ("Settings file", saved.path),
    ]
    if not fenced and not by_setup:
        p.notes.append("No folder restriction is set, so every path on this "
                       "machine is reachable. Set ALLOWED_ROOTS where the app "
                       "is started to fence it in.")
    # Who this app writes as, said where it will be seen.
    #
    # The one fault in this app that reports itself as nothing at all: every
    # write succeeds, every move lands, and Synology Drive - which reads the
    # library as YOU, not as this app - stops syncing a tree it can no longer
    # read, without saying anything either. The first sign is a folder that has
    # not appeared on the tablet for a fortnight.
    from core import perms
    uid, gid = perms.writes_as()
    if uid is not None:
        for key, what in (("library", "library"), ("raw", "RAW tree"),
                          ("previews", "previews tree"),
                          ("develop", "develop tree")):
            said = perms.mismatch(str(opts.get(key) or "").strip())
            if said:
                p.notes.append(f"The {what}: {said}")
        p.stats.append(("This app writes as",
                        f"user {uid}, group {gid}" + (" (root)" if uid == 0 else "")))
        p.notes.append(
            "A photo this app REWRITES - a rating, a tag, a colour - "
            "keeps the owner and the mode it had, and anything it creates takes "
            "after the folder it lands in. That is not cosmetic: a library "
            "quietly re-owned to root is one Synology Drive stops syncing, "
            "silently, because from its side nothing is wrong.")
    p.notes.append("Nothing here touches a photo. Applying writes the settings file, "
                   "and every other tool reads it.")
    p.notes.append("Bracket grouping is read by previews (one per set), ratings (a "
                   "star reaches the whole set) and cull (a set is kept or moved aside "
                   "whole). Turning it off here turns it off in all three.")
    if not changes and not check:
        p.notes.append("Nothing is different from what is already saved.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    try:
        saved = S.save({k: plan.opts[k] for k in FIELDS if k in plan.opts})
        result.done = len(plan.rows)
        result.stats = [("Settings saved", f"{result.done:,}"),
                        ("Written to", saved.path)]
        result.details.append("Every tool will start from these from now on. Any of "
                              "them can still be overridden for a single run.")
    except Exception as exc:                        # noqa: BLE001
        result.failed = 1
        result.details.append(f"could not write the settings: {exc}")
    return result


register(Task(
    name="setup",
    title="Setup",
    summary="Sets the trees, the bracket rules and the defaults that every "
            "tool reads.",
    icon="gear",
    settings=True,
    writes=False,
    order=90,
    options=[
        Folder("library", "Library", default="", must_exist=False,
               setting="library", group="Trees",
               help="The top folder of your photos. Every other tree mirrors "
                    "its shape. No tool changes it unless you point that "
                    "tool at it."),
        Folder("raw", "RAW tree", default="", must_exist=False,
               setting="raw", group="Trees",
               help="The top folder for RAW files, shaped like the library. "
                    "It must not be inside the library. It does not need to "
                    "exist yet: it is made the first time RAW files are "
                    "moved."),
        Folder("previews", "Previews tree", default="", must_exist=False,
               setting="previews", group="Trees",
               help="The top folder for previews, shaped like the library. "
                    "It is disposable: synced to the tablet for rating, and "
                    "remade whenever needed."),
        Folder("video", "Video tree", default="", must_exist=False,
               setting="video", group="Trees",
               help="The top folder for videos, shaped like the library. "
                    "Videos are large and many tools skip them, so keeping "
                    "them apart helps. Blank until you want it."),
        # Only drawn on a PC (app.server.PC_ONLY_OPTIONS): there the trees above
        # are the fence, and a file the app needs from elsewhere - a GeoNames
        # download, an export folder - has to be let in by name.
        Folders("also_allowed", "Also allowed", default="",
                setting="also_allowed", group="Trees",
                help="Extra folders this PC may reach. The app reaches only "
                     "the trees above and these, so nothing else on the disk "
                     "can be opened or downloaded from another device. Add a "
                     "folder here to use files from it: a GeoNames download, "
                     "an export folder."),

        # This machine, as a client sees it. One phone, several servers: a list
        # of connections showing two IP addresses is a list nobody can read.
        Option("server_name", "Server name", default="",
               kind="text", setting="server_name", group="Network",
               help="The name a phone or desktop client shows for this "
                    "server, for example NAS. Blank uses the machine's own "
                    "name."),
        Flag("discovery", "Discoverable on the network", default=True,
             setting="discovery", group="Network",
             help="Lets a client on the same network find this server "
                  "without typing an address. The answer gives only the "
                  "server's name and port and whether it needs a password, "
                  "nothing about the photos. It does not cross a VPN or "
                  "another subnet. On by default."),
        Number("public_port", "Public port", default=0,
               minimum=0, maximum=65535, setting="public_port",
               group="Network", advanced=True,
               help="The port clients should connect to, when it differs "
                    "from the port the app listens on. 0 to 65535, default "
                    "0, which means the same port. In a container mapped "
                    "8842:8080 the app only sees 8080, so set 8842 here."),

        # The two keys the viewer answers to besides the obvious ones. Settable
        # because a keyboard is a personal thing: on a layout where "i" is
        # somewhere else, a shortcut you cannot reach is a shortcut you do not
        # have. The stars (0-5), the colours (6-9) and the arrows are fixed -
        # they are the ones everybody already knows.
        Option("key_info", "Exposure details key", default="i", kind="text",
               setting="key_info", group="Viewer keys",
               help="The key that shows camera, lens, aperture, shutter and "
                    "ISO over the photo in the viewer. One letter, default "
                    "i. Blank turns it off."),
        Option("key_histogram", "Histogram key", default="h",
               kind="text", setting="key_histogram",
               group="Viewer keys",
               help="The key that shows the histogram over the photo in the "
                    "viewer. One letter, default h. Pressing it again "
                    "changes what the histogram draws. Blank turns it off."),
        Option("quick_tags", "Quick tags", default="", kind="text",
               setting="quick_tags", group="Viewer keys",
               help="Up to five tags, separated by commas, put on Shift+1 to "
                    "Shift+5 in the viewer. Pressing the same key again "
                    "removes the tag. Press ? in the viewer for every key."),

        # What is worth sending, set once.
        #
        # These live here and not only on the Send to develop tab because the
        # automation sends in the background and fills that form from Setup.
        # Left on the tab alone they would be the option defaults at four in the
        # morning, whatever you had typed - the tab showing one thing and the
        # background doing another, invisibly.
        Number("develop_raw_at", "Send RAW from (stars)", default=5,
               minimum=-1, maximum=5, setting="develop_raw_at",
               group="What to send",
               help="A RAW file is sent when its photo has this many stars "
                    "or more. -1 to 5, default 5. -1 never sends a RAW file. "
                    "RAW files are large, so this is usually the top rating "
                    "only."),
        Number("develop_jpeg_at", "Send JPEG from (stars)",
               default=4, minimum=-1, maximum=5, setting="develop_jpeg_at",
               group="What to send",
               help="A JPEG is sent when it has this many stars or more. -1 "
                    "to 5, default 4. -1 never sends a JPEG. Set it lower "
                    "than the RAW threshold to get the photos worth a look "
                    "without the large RAW files."),
        Choice("develop_colour", "Only this colour", default="",
               choices=lambda: [("", "Any - send by rating and tag as well")]
                               + [(d.colour, d.title()) for d in _colours()
                                  if d.defined],
               setting="develop_colour", group="What to send",
               help="Send to develop sends only photos carrying this colour "
                    "label. Blank means any colour. The meaning of each "
                    "colour is set on the Colour meanings tab."),
        Option("develop_tags", "Only photos tagged", default="", kind="text",
               setting="develop_tags", group="What to send",
               help="Sends only photos carrying one of these tags, separated "
                    "by commas. Tags are read from the sidecar, from the "
                    "JPEG, from Windows Explorer's Tags box and from IPTC. A "
                    "level of a hierarchy matches: Italy finds "
                    "Travel|Italy|Rome. Blank means no tag filter."),
        Choice("develop_tags_rule", "What the tags do", default="only",
               choices=[("only", "Narrow: only photos with the tags"),
                        ("also", "Widen: tagged photos too, any rating")],
               setting="develop_tags_rule", group="What to send",
               advanced=True,
               help="How the tags combine with the ratings. Narrow sends "
                    "only photos that qualify by rating and also carry a "
                    "tag. Widen sends everything that qualifies by rating, "
                    "plus every tagged photo whatever its rating, as a JPEG "
                    "only."),
        Flag("develop_tags_all", "Must have all tags",
             default=False, setting="develop_tags_all",
             group="What to send", advanced=True,
             help="A photo must carry every tag listed in Only photos "
                  "tagged. Off, carrying any one of them is enough."),
        Flag("develop_labels", "Follow colour labels",
             default=True, setting="develop_labels",
             group="What to send",
             help="Lets a colour label decide which photos are sent and to "
                  "which folder, as set in Setup > Colour meanings. A colour "
                  "label beats a rating over which folder a photo lands in. "
                  "Off, only ratings and tags decide. On by default."),
        Flag("develop_prune", "Remove finished copies", default=True, setting="develop_prune",
             group="What to send",
             help="Removes a copy from the develop tree once its photo is "
                  "developed or no longer qualifies, so the tree holds only "
                  "what is still waiting. Only files inside the develop tree "
                  "are removed, and every one is a copy the library still "
                  "has. On by default."),

        Choice("filed_where", "Export destination", default="subfolder",
               choices=[("subfolder", "A subfolder of the shoot"),
                        ("beside", "Beside the original")],
               setting="filed_where", group="Tablet workflow",
               help="Where File developed puts each export once its original "
                    "is found. The export folder from the tablet is one flat "
                    "folder, so each export is first matched to its original "
                    "by capture time, camera and name. A subfolder keeps the "
                    "shoot folder for camera files only."),
        Option("filed_into", "Subfolder name", default="Developed", kind="text",
               setting="filed_into", group="Tablet workflow",
               help="The name of the subfolder, default Developed. A name, "
                    "not a path: it is made inside whichever shoot each "
                    "export belongs to. The name is also added to the "
                    "folders the app never scans, so exports are not read as "
                    "originals."),
        Flag("filed_tidy_resync", "Clear re-synced copies", default=True,
             setting="filed_tidy_resync", group="Tablet workflow",
             advanced=True,
             help="Removes an export from the export folder when the same "
                  "file was already filed, because the tablet can sync its "
                  "copy back again. Only the export folder is touched, never "
                  "the library. Off, such copies are listed and left, and "
                  "the export folder slowly fills. On by default."),
        Flag("filed_keep", "Keep the export",
             default=False, setting="filed_keep",
             group="Tablet workflow", advanced=True,
             help="Copies each export into the library instead of moving it. "
                  "Off by default: the export is moved and the export folder "
                  "empties for the next round."),
        Folder("develop", "Develop tree", default="", must_exist=False,
               setting="develop", group="Tablet workflow",
               help="The top folder for photos being developed. Send to "
                    "develop copies qualifying photos here, keeping the "
                    "library's shape, and removes them when they are "
                    "finished. Sync this folder to the tablet."),
        Folder("inbox", "Lightroom's export folder", default="", must_exist=False,
               setting="inbox", group="Tablet workflow",
               help="The folder Lightroom on the tablet exports into, synced "
                    "back to the NAS. Keep it outside the library, or every "
                    "export is read as an original photo."),

        Choice("preview_profile", "Preview size", default="medium",
               choices=PROFILE_CHOICES, setting="preview_profile", group="Previews",
               help="The size and JPEG quality Make previews uses. A named "
                    "size wins over the two boxes below, so a stale custom "
                    "value cannot change it. Choose Custom to use the boxes."),
        Number("preview_long_edge", "Custom longest side (pixels)", default=2048,
               minimum=320, maximum=8000, setting="preview_long_edge",
               group="Previews", advanced=True,
               help="The longest side of a custom preview, in pixels. 320 to "
                    "8000, default 2048. Only used when Preview size is "
                    "Custom."),
        Number("preview_quality", "Custom JPEG quality", default=85,
               minimum=40, maximum=98, setting="preview_quality",
               group="Previews", advanced=True,
               help="The JPEG quality of a custom preview. 40 to 98, default "
                    "85. Only used when Preview size is Custom."),
        Number("thumb_keep", "Thumbnails kept", default=60000,
               minimum=500, maximum=400000, setting="thumb_keep",
               group="Previews", advanced=True,
               help="How many thumbnails the app keeps for browsing. 500 to "
                    "400,000, default 60,000. Each one costs about twenty "
                    "kilobytes. Fewer than you have photos means the oldest "
                    "are thrown away as you browse and decoded again later."),

        Flag("bracket_group", "Group brackets", default=True,
             setting="bracket_group", group="Brackets",
             help="Treats a bracket set as one photo in Make previews, "
                  "Rating & tags and Cull by rating. Each set gets one "
                  "preview and one rating for every frame, and is kept or "
                  "moved together. On by default."),
        Number("bracket_gap", "Largest gap (seconds)",
               default=3, minimum=1, maximum=60, setting="bracket_gap",
               group="Brackets",
               help="The longest pause, in seconds, between two frames of "
                    "one bracket set. 1 to 60, default 3. Increase it only "
                    "if your camera is slow between frames."),
        Number("bracket_min_set", "Smallest set (frames)", default=3, minimum=2, maximum=9,
               setting="bracket_min_set", group="Brackets", advanced=True,
               help="The fewest frames that count as a bracket set. 2 to 9, "
                    "default 3."),
        Number("bracket_max_set", "Largest set (frames)", default=9, minimum=3, maximum=15,
               setting="bracket_max_set", group="Brackets", advanced=True,
               help="The most frames that count as one bracket set. 3 to 15, "
                    "default 9. A longer run of frames is not a set."),
        Flag("bracket_probable", "Include hand-bracketed",
             setting="bracket_probable", group="Brackets", advanced=True,
             help="Also counts sets with no exposure bias recorded, which is "
                  "what hand-bracketing leaves. Nothing in the file "
                  "separates such a set from three ordinary photos taken "
                  "seconds apart. Leave it off until Test folder shows what "
                  "it finds. Off by default. Thin brackets also finds these "
                  "sets when its own Include probable sets box is on."),

        Folders("exclude", "Skip everywhere", default="",
                setting="exclude", group="Skipped folders",
                help="Folders every tool leaves alone, as paths, for example "
                     "your phone's photos, your scans or a video folder "
                     "beside the library. Everything inside each one is left "
                     "alone too, and every run that meets one says so. "
                     "Folder names such as @eaDir go in Folder names never "
                     "scanned instead. A flow can add more on the Flows tab."),

        Option("ignore", "Folder names never scanned", default=S.DEFAULTS["ignore"],
               kind="text", setting="ignore", group="Skipped folders",
               help="Folder names, separated by commas, that no tool ever "
                    "reads. Other apps keep working files inside photo "
                    "folders, such as PhotoPrism, Immich, Synology's @eaDir "
                    "and #recycle. One name covers every shoot. The built-in "
                    "names are always skipped whatever is in this box."),

        Option("bracket_tag", "Bracket tag",
               default=S.DEFAULTS["bracket_tag"], kind="text", setting="bracket_tag",
               group="Brackets",
               help="The tag Find brackets writes on every frame of a set, "
                    "and Make previews writes on the preview of a set. "
                    "Default bracket. One setting, so the two cannot write "
                    "different words. Blank writes nothing."),
        Option("place_names", "Rename places", default="",
               kind="text", setting="place_names", group="Skipped folders",
               help="Names to change before they are used as folder names, "
                    "one per line: Marrakesh = Marrakech. A line matches a "
                    "town or a country. Sort into folders lists every name "
                    "found, so run once and edit the list from there."),

        Folder("check", "Test folder", default="",
               must_exist=False, group="Brackets",
               help="A shoot to test the bracket rules on. Nothing is "
                    "written. Apply shows the sets the rules find, so you "
                    "can compare them with what you shot."),

        Flag("developer", "Developer mode", default=False, setting="developer",
             group="Developer", advanced=True,
             help="Shows the Wording tab under Setup, where the text of every "
                  "tool can be edited and exported. Nothing else changes."),
    ],
    plan=plan,
    apply=apply,
))
