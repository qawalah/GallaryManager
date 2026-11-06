"""The page's own files: markup, style, script and icons, kept as files.

Everything the browser runs lives in this folder, so the interface can be worked
on without opening a line of the Python that moves photographs. `app/page.py`,
`app/libraryui.py` and `app/loginpage.py` only read these files and glue them
together; the server sends the result exactly as before.

    page/       the features half: index.html (the frame), style.css,
                script.js, icons.svg, and sw.js (the service worker)
    library/    the library half (Home, Photos, Places, Albums, Tools):
                css/, js/ and icons/ in numbered pieces, joined in name order
    fonts/      the typeface (Archivo, SIL Open Font License, OFL.txt beside
                it), served at /font/<name> to the page and the sign-in page
    login.html  the sign-in page, which needs nothing else

Order matters inside library/js and library/css: the pieces are concatenated in
file-name order, so a new piece gets the next number, and a piece that must run
before another needs a lower one.

Everything is read once, at import, so a running server never touches the disk
to draw its page.
"""

from __future__ import annotations

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def read(rel: str) -> str:
    """One file from this folder, as text."""
    with open(os.path.join(HERE, *rel.split("/")), encoding="utf-8") as fh:
        return fh.read()


def fonts() -> dict:
    """The page's typeface files, by the name the page asks for them under.

    Served from the app itself (`/font/<name>`), never fetched from the internet:
    the app runs on a NAS or a PC that may have no way out, and a page that
    waits on a font host it cannot reach draws nothing for three seconds."""
    where = os.path.join(HERE, "fonts")
    out = {}
    for name in sorted(os.listdir(where)):
        if name.endswith(".woff2"):
            with open(os.path.join(where, name), "rb") as fh:
                out[name] = fh.read()
    return out


def concat(folder: str) -> str:
    """Every file in one of this folder's subfolders, joined in name order."""
    where = os.path.join(HERE, *folder.split("/"))
    return "".join(read(f"{folder}/{name}") for name in sorted(os.listdir(where))
                   if os.path.isfile(os.path.join(where, name)))


_SLOT = re.compile(r"\{\{([A-Z_]+)\}\}")


def fill(template: str, **slots: str) -> str:
    """Put each `{{NAME}}` in the template's place, in one pass.

    One pass, so a `{{` that happens to be inside the script being put in is
    never mistaken for another slot.
    """
    return _SLOT.sub(lambda m: slots[m.group(1)], template)
