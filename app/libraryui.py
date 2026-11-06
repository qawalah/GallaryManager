"""The photo library: the screens 3.0 put in front of the features.

Everything in `app/page.py` is a FEATURE - a form, a plan, a table of what would
happen. That is the right shape for forty-six jobs and the wrong shape for the
first ten seconds: the app opened on a form with "Have a look" under it, and the
photographs - the only reason any of it exists - were not on the screen at all.

So this module is the other half: the library you open ON.

    Home        what is in there, measured already, and what is running
    Photos      the grid, newest first, grouped by month
    Timeline    every month there is, as a way to jump
    Places      the map, by what the files actually say
    Albums      collections that are questions, not folders
    Tools       the forty-six, in five cards
    Settings    where things are and what they mean

**None of it scans.** Every screen here reads `core/catalogue.py`, which is
built in the background and kept up to date, and that is the whole reason this
can be the front door. A front door that takes thirty seconds is a back door.

**Nothing here does the work.** Select photographs and press Geotag and you land
on the Geotag feature with the folders your selection is in already filled in -
the same form, the same plan, the same Go ahead. The two things that are
genuinely per-photograph and already have an endpoint of their own - stars and
colour labels - are written straight through, exactly as the viewer does it,
because making you open a feature to put a star on one photograph would be a
worse app wearing a better coat.

It is kept apart from `page.py` so that the library and the features can be read
separately. The page glues the three strings together: ICONS, STYLE and SCRIPT,
all files in `app/web/library/` - edit them there. The markup the router draws
into (#rail, #stage) is in `app/web/page/index.html`.
"""

from __future__ import annotations

from app import web

# --------------------------------------------------------------------- icons
#
# Only the ones the new screens need; the rest are page.py's.
ICONS = web.concat("library/icons")

# --------------------------------------------------------------------- the look
#
# Photo-first, which in practice means three things: the photographs are the
# only saturated thing on the screen, everything else is one of two greys, and
# nothing has a border it does not need. The semantic colours are the ones the
# review asked for - blue acts, green succeeded, amber wants attention, red
# destroys, purple develops, teal is metadata and place.
STYLE = web.concat("library/css")

# ------------------------------------------------------------------ the screens
SCRIPT = web.concat("library/js")
