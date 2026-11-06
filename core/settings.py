"""The things you set once, that every task then reads.

Two kinds of thing live here.

THE THREE TREES. `N:\\Photos`, `N:\\Photos Raw`, `N:\\Photos Previews`. Typing
them into every form is how they end up subtly different in each - one with a
trailing slash, one pointing at a shoot instead of the tree root - and mirroring
against the wrong root is exactly the mistake that scatters files. Set once,
read everywhere.

HOW BRACKETS ARE GROUPED. Four numbers and a switch. They must mean the same
thing to every feature that uses them: if `previews` makes one preview per set
and `cull` groups the sets differently, then one frame of a set gets a preview
and a *different* grouping decides what to put aside, which is worse than not
grouping at all. So there is one answer, kept here, and previews, ratings and
cull all read it.

Kept in one small JSON file beside the app's other data. Nothing here is secret,
nothing here is large, and a missing or damaged file is not an error - it just
means the defaults, so the app always starts.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .store import store_path

FILE = "settings.json"

# Preview sizes, as a choice rather than two numbers, because "2048 at 85" is
# not a decision anyone wants to make twice. Named the way the Windows app named
# them so the two versions can be talked about together.
PROFILES = {
    "small":  {"long_edge": 1280, "quality": 80,
               "label": "Small: 1280 px, quality 80"},
    "medium": {"long_edge": 2048, "quality": 85,
               "label": "Medium: 2048 px, quality 85"},
    "large":  {"long_edge": 3200, "quality": 92,
               "label": "Large: 3200 px, quality 92"},
    "custom": {"long_edge": 2048, "quality": 85,
               "label": "Custom: set the boxes below"},
}
PROFILE_ORDER = ["small", "medium", "large", "custom"]


# Folder names never scanned. Other apps keep their working files inside photo
# folders - PhotoPrism, Synology's own indexes, Drive's versions - and those are
# not your photos: counting them makes every number wrong, and letting a task
# touch them can damage the other app. Names, not paths, so one entry covers
# every shoot.
IGNORE = ["Developed",
          "@eaDir", "#recycle", "@Recycle", "#snapshot", "@Transcode",
          ".@__thumb", ".stfolder", ".stversions", ".streams",
          "photoprism", ".photoprism", "originals/.photoprism",
          "immich", ".immich", "@Synology", ".DS_Store"]


DEFAULTS = {
    # Folders nothing ever walks into - the phone dump, the scanned negatives,
    # a video folder kept beside the library. PATHS, not names: "my phone's
    # photos are in Photos/Mobile" is about one place, and a name would take
    # out every folder called Mobile anywhere. A flow adds its own to these
    # rather than replacing them - see core/exclude.py.
    "exclude": "",
    # Folder-name patterns kept by name, for Sort into folders: a JSON list of
    # [name, pattern]. Text rather than a structure so the file stays one flat
    # dictionary like everything else in it.
    "folder_patterns": "",
    # Searches kept by name, for Search: a JSON list of [name, {criteria}].
    # Same shape and the same reason as the patterns above.
    "saved_searches": "",
    # What you call each camera, against the code it writes into the file:
    # {"sm-g991b": "Hana's phone"}. A display name only - nothing is ever
    # written to a photograph (`core/devices.py`).
    "camera_names": "",
    # What this machine calls itself to a client, and the id a client stores a
    # connection against (`core/identity.py`). The id is made once, on first
    # run, and is never shown to anyone.
    "server_name": "",
    "server_id": "",
    # Answer "is there a Photo Manager here?" shouted on the local network, so a
    # phone finds the NAS and the PC without anyone typing an address
    # (`core/discovery.py`). "no" turns it off.
    "discovery": True,
    # The port a client on the network should use, when it is not the port the
    # server is listening on. On the NAS the container maps 8842 to 8080, and
    # 8080 is the only number the process can see - so an answer to a discovery
    # shout that said 8080 would send every phone to a port that is not open.
    "public_port": "",
    # Where the brackets fall on a chart: {"aperture": [["wide", 3.0], ...]}.
    # Only the sets you have replaced are in here; the rest come from the
    # built-in tables in `core/bands.py`.
    "bands": "",
    # The dashboard as you arranged it, and the arrangements you kept
    # (`core/boards.py`).
    "dashboards": "",
    # Where the sample library to practise on was built (`core/demo.py`), and -
    # while the app is pointed at it - the tree paths it was pointed away from,
    # as JSON. Two keys rather than one because they answer two questions: "is
    # there a sample library" and "what were your own folders before I borrowed
    # the boxes". Without the second, turning demo mode off would mean typing
    # five paths back in from memory, which is not something anybody would
    # forgive a tutorial for.
    "demo_folder": "",
    "demo_stash": "",
    # Which of the tags in your library are people, comma separated. There is no
    # face detection here and none is coming: this app does not open a
    # photograph to guess at it, and a wrong name on somebody's child is a worse
    # failure than no name. So People is the names already written INTO the
    # files - and this is the short list of which tags those are, because
    # "beach" and "Hana" are both just keywords to a JPEG.
    "people_tags": "",
    # Features pinned to the top level of the rail, beside Home and Photos:
    # JSON, a list of names. Five screens and forty-eight features is the right
    # shape for a library and the wrong one for the two things somebody happens
    # to do every single day - which are different for every person, and are the
    # whole reason a list of everything exists to be gone past.
    "pinned_tools": "",
    # The tools, grouped the way you want them: JSON,
    # {"groups": [{"key", "label", "icon", "tone", "tasks": [...]}],
    #  "hidden": [names]}. Empty means the built-in five (`core/families.py`).
    #
    # A person's library is not the one this app was designed around. Somebody
    # who never shoots RAW does not want four features about separating them in
    # front of them every day, and somebody whose whole week is geotagging
    # wants those four together under a heading they chose. The built-in
    # grouping is a good default and a bad rule.
    "tool_groups": "",
    # Albums put away: JSON, a list of album keys ("favourites", "tag:beach",
    # "kept:My week"). The built-in ones are questions this app thinks are worth
    # asking, which is not the same as thinking YOU should be asked them: a
    # library with no video in it has a Videos album saying nothing, and "To
    # develop" means nothing to somebody who does not develop. Nothing is
    # deleted - an album is a question, and putting it away is declining to ask
    # it.
    "hide_albums": "",
    # Folders left out of the PHOTOS SCREEN - not out of the app. JSON, a list
    # of paths.
    #
    # Deliberately not the exclusion list above, which is a decision about your
    # library: nothing walks into those, no feature touches them, and the index
    # does not know they exist. This one is about a view. The scans you keep
    # beside the shoots are real photographs you want geotagged, backed up and
    # counted - you simply do not want to scroll past four hundred of them
    # looking for the holiday, and reaching for Setup to say that would mean
    # paying for it everywhere else.
    "hide_in_grid": "",
    # The two keys the viewer answers to besides the obvious ones. Letters, one
    # each, and settable because a keyboard is a personal thing and "i" is not
    # the letter everybody reaches for. Blank turns that shortcut off.
    "key_info": "i",
    "key_histogram": "h",
    # UP TO FIVE WORDS, ON SHIFT AND A NUMBER.
    #
    # The tag menu is right for a word you use once. It is wrong for the five
    # words you put on four hundred photographs an evening: opening a menu,
    # reading it and picking is three actions for a thing you already knew the
    # answer to before the photograph came up. These are one key each, and the
    # same key takes the tag off again.
    "quick_tags": "",
    "library": "",
    "raw": "",
    "previews": "",
    # Video gets a tree of its own, in the same shape as the library: a clip is
    # not a photograph, it is a hundred times the size, and half the tools here
    # skip it silently.
    "video": "",
    # the develop loop: a working set for the tablet, and where Lightroom's
    # exports come back to
    "develop": "",
    "inbox": "",
    # On a PC with no ALLOWED_ROOTS the app reaches only the folders above and
    # these: a GeoNames download, an export folder, a phone's camera roll.
    # Newline-separated paths. Read by `app.server.fence`.
    "also_allowed": "",
    # brackets
    "bracket_group": True,
    "bracket_gap": 3,
    "bracket_min_set": 3,
    "bracket_max_set": 9,
    "bracket_probable": False,
    # The keyword a bracket set is marked with, on the frames and on the preview
    # that stands for them. One place, so "Find brackets" and "Make previews"
    # cannot write two different words and leave half a library findable.
    "bracket_tag": "bracket",
    # previews
    "preview_profile": "medium",
    "preview_long_edge": 2048,
    "preview_quality": 85,
    # HOW MANY SMALL PICTURES TO KEEP.
    #
    # Making one means decoding a photograph; keeping one costs about twenty
    # kilobytes. The ceiling was six thousand, which on a library of eighty
    # thousand means browsing past six thousand photographs throws away the
    # thumbnails of the first ones - so coming back decodes them all again.
    # Sixty thousand is about a gigabyte, which is nothing on a NAS and is the
    # difference between a grid that scrolls and one that thinks.
    "thumb_keep": 60000,
    # stored as text so it is one editable box rather than a list widget
    "ignore": ", ".join(IGNORE),
    # --------------------------------------- what is worth sending to develop
    #
    # Here rather than only on the tab, because the automation sends to develop
    # in the background and fills that form from THESE. Left as option defaults
    # they would be 5 and 4 forever, whatever you had typed - which is the same
    # bug the developed folder name had, and it is invisible: the tab shows what
    # you set, and four in the morning uses something else.
    "develop_raw_at": 5,
    "develop_jpeg_at": 4,
    "develop_prune": True,
    "develop_tags": "",
    "develop_tags_rule": "only",
    "develop_tags_all": False,
    "develop_colour": "",
    "develop_labels": True,
    # ------------------------------------------- where developed photos land
    #
    # The tablet syncs ONE flat folder back - Lightroom on Android has no idea
    # what shape the library is - so each export is matched to its original by
    # capture time, camera and name, and put where that original lives. These
    # two say where exactly: beside it, or in a subfolder of the shoot.
    #
    # Here rather than only on the tab because the automation runs it in the
    # background: a name typed into a form once would not be the name used at
    # four in the morning, and the exports would quietly start landing in a
    # second folder.
    "filed_where": "subfolder",
    "filed_into": "Developed",
    "filed_keep": False,
    "filed_tidy_resync": True,
    # --------------------------------------------------------- the automation
    #
    # The developing loop, running itself. Each step watches a tree and runs
    # when that tree is not what it was last time. Filing exports reports rather
    # than running by default - it is the one step that MOVES photographs into
    # the library, and a wrong answer there is a photograph somewhere you did
    # not put it.
    "auto_on": False,
    "auto_every": 15,
    "auto_deep": True,
    "auto_ratings_on": True,
    "auto_ratings_do": "run",
    "auto_develop_on": True,
    "auto_develop_do": "run",
    "auto_filed_on": True,
    "auto_filed_do": "report",
    # ------------------------------------------------------------ the labels
    #
    # Five colours, and what each one MEANS - written here rather than typed
    # into a form every run, because the whole point of a colour is that it
    # means the same thing in January as it did in March.
    #
    # The colour WORD is what goes into xmp:Label, where Lightroom, Bridge and
    # darktable look. The name is yours, and is written as a keyword beside it,
    # which is what makes other apps able to find it.
    "label_red_name": "Edit",
    "label_red_keywords": "edit",
    "label_red_action": "develop",
    "label_red_folder": "",
    "label_red_raw": True,
    "label_yellow_name": "Sharpen",
    "label_yellow_keywords": "sharpen, ai-sharpen",
    "label_yellow_action": "develop",
    "label_yellow_folder": "Sharpen",
    "label_yellow_raw": False,
    "label_green_name": "Timelapse",
    "label_green_keywords": "timelapse",
    "label_green_action": "develop",
    "label_green_folder": "Timelapse",
    "label_green_raw": False,
    "label_blue_name": "Print",
    "label_blue_keywords": "print",
    "label_blue_action": "develop",
    "label_blue_folder": "Print",
    "label_blue_raw": True,
    "label_purple_name": "",
    "label_purple_keywords": "",
    "label_purple_action": "none",
    "label_purple_folder": "",
    "label_purple_raw": False,
    # "Marrakesh = Marrakech", one per line: the names YOU would give the folders,
    # overriding whatever the place table calls them. Here rather than only on the
    # sort tab so it is written once and every future run keeps it.
    "place_names": "",
    # Shows Setup > Wording, where the text of every tool can be edited and
    # exported. PM_DEVELOPER=1 turns it on too (core/wording.developer_on).
    "developer": False,
}


@dataclass
class Settings:
    values: dict = field(default_factory=lambda: dict(DEFAULTS))
    path: str = ""
    existed: bool = False

    def __getitem__(self, key):
        return self.values.get(key, DEFAULTS.get(key))

    def get(self, key, fallback=None):
        v = self.values.get(key, DEFAULTS.get(key))
        return fallback if v in (None, "") and fallback is not None else v

    def brackets(self) -> dict:
        """The bracket settings, in the shape `core.brackets.find` wants them."""
        return {"max_gap_seconds": float(self["bracket_gap"]),
                "min_set": int(self["bracket_min_set"]),
                "max_set": int(self["bracket_max_set"]),
                "include_probable": bool(self["bracket_probable"])}

    def ignored(self) -> set:
        """Folder names to skip, lower-cased. Never empty of the built-in ones.

        Yours are ADDED to the defaults rather than replacing them: clearing the
        box should not silently start scanning Synology's index folders again.
        """
        text = str(self["ignore"] or "")
        names = {n.strip().lower() for n in text.replace("\n", ",").split(",")}
        # And WHATEVER the developed subfolder is currently called.
        #
        # Not optional, and not something to leave to the ignore box. An export
        # has its original's name, capture time and camera, so a folder of them
        # that is scanned as part of the library is a second copy of every
        # photograph in that shoot: counted twice, paired against the same RAW,
        # reported as a duplicate of its own original, and sent out to develop
        # again. "Developed" is in the built-in list below and renaming it to
        # "Curated" would have quietly done all of that.
        mine = str(self["filed_into"] or "").strip().lower()
        return ({n for n in names if n} | {n.lower() for n in IGNORE}
                | ({mine} if mine else set()))

    def preview_size(self) -> tuple[int, int]:
        """Long edge and quality, from the chosen profile.

        A named profile wins over the two numbers, so picking Medium and leaving a
        stale 3200 in the custom box cannot quietly give you Large.
        """
        name = str(self["preview_profile"] or "medium").lower()
        if name in PROFILES and name != "custom":
            p = PROFILES[name]
            return int(p["long_edge"]), int(p["quality"])
        return int(self["preview_long_edge"]), int(self["preview_quality"])

    def profile_label(self) -> str:
        edge, quality = self.preview_size()
        name = str(self["preview_profile"] or "medium").lower()
        if name == "custom" or name not in PROFILES:
            return f"Custom - {edge}px, quality {quality}"
        return PROFILES[name]["label"]


# ---------------------------------------------------------------- read once
#
# THIS FILE IS READ FROM INSIDE PER-PHOTOGRAPH LOOPS.
#
# Not on purpose. "Which band does this focal length fall in" asks the bands
# table, which asks the settings, and the home screen asks that question eight
# times for each of eighty thousand photographs - 320,010 opens of one small
# JSON file to draw eight kilobytes of numbers, each one carrying an
# `os.makedirs` from `store_path`. On a NAS, with the config folder on a mounted
# volume, that was fifteen seconds of syscalls and no photograph read at all.
#
# So the file is read when it CHANGES and not when it is asked for. The stamp is
# the three numbers a filesystem actually records - size, modification time in
# nanoseconds, and the inode - the same signature `core/facts.py` trusts for a
# photograph, and for the same reason: every write here is "temp file, then
# os.replace", so the inode changes even when nothing else does.
#
# What is cached is the VALUES, and every caller gets its own copy of them. A
# `Settings` handed out twice and mutated once would be a bug that appears
# somewhere else entirely, and copying forty keys costs a microsecond against
# the sixty this saves.
_SEEN: dict = {}


def _stamp(path: str):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns, st.st_ino)


def _read(path: str) -> tuple:
    values = dict(DEFAULTS)
    existed = False
    try:
        with open(path, "r", encoding="utf-8") as fh:
            stored = json.load(fh)
        if isinstance(stored, dict):
            for k, v in stored.items():
                if k in DEFAULTS:
                    values[k] = v
            existed = True
    except (OSError, ValueError):
        pass                        # no file, or a damaged one: the defaults stand
    return values, existed


# The settings that are trees of folders, rather than words or switches.
TREES = ("library", "raw", "previews", "video", "develop")


def stamp(path: str = "") -> str:
    """Which version of the settings file this is, as text that changes with it.

    For anything that keeps a copy of a setting - the page's forms, the index
    of the library - to notice it is holding an old one, whoever changed it:
    Setup, the sample library borrowing the trees, the command line, another
    browser. Only a stat, so it is cheap enough to ask every few seconds.
    """
    got = _stamp(path or store_path(FILE))
    return "-".join(str(x) for x in got) if got else ""


def forget() -> None:
    """Drop what has been read. For tests, and after a write."""
    _SEEN.clear()


def load(path: str = "") -> Settings:
    """Whatever is on file, with the defaults filling any gap. Never raises."""
    path = path or store_path(FILE)
    stamp = _stamp(path)
    hit = _SEEN.get(path)
    if hit is None or hit[0] != stamp:
        values, existed = _read(path)
        _SEEN[path] = (stamp, values, existed)
        hit = _SEEN[path]
    return Settings(values=dict(hit[1]), path=path, existed=hit[2])


def save(values: dict, path: str = "") -> Settings:
    """Write the settings, keeping anything not mentioned.

    Written to a temporary file and moved into place, so a crash halfway cannot
    leave a half-written settings file that then fails to parse.
    """
    path = path or store_path(FILE)
    current = load(path)
    before = dict(current.values)
    for k, v in (values or {}).items():
        if k in DEFAULTS:
            current.values[k] = v
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(current.values, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)
    current.existed = True
    # The stamp will have moved anyway - this is so a reader in the same
    # millisecond, on a filesystem with a coarse clock, cannot be handed what
    # was there before this write.
    _SEEN.pop(path, None)
    # A tree that moved takes the folders remembered inside it along: a form
    # opening on a folder of the library you just left is still pointed at
    # it. Here rather than in Setup, because the sample library and the
    # command line move the trees too.
    if path == store_path(FILE):
        from . import recent
        for key in TREES:
            if str(before.get(key) or "").strip() != str(current.values.get(key) or "").strip():
                recent.tree_moved(before.get(key), current.values.get(key))
    return current
