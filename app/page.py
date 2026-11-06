"""The page itself: markup, style and script, kept apart from the server.

The markup, style and script are files in `app/web/page/` - edit them there.
This module reads them, adds the library half (`app/libraryui.py`), the guide
and the appearance tables, and puts the one page together.

It knows nothing about photos. It asks what tasks exist, draws each one's form
from the options that task declares, and shows what came back. Add a feature and
it appears here with a working form, its group listed beside it, grouped
settings and a Browse button, without a line changing in this file.

Four things here are deliberate rather than decorative:

**The sidebar is icons and names, nothing else.** A one-line description under
every item is read once and then becomes noise you have to look past every time.
The description belongs at the top of the feature you opened.

**Related tools are listed beside each other.** Importing a timeline and
pinning a place by hand are both "give this a location", so each one's page
lists the other, and the rest of Metadata, down the right. The list is the
group as arranged on All tools, not a tab row fixed in the source, so it
follows wherever somebody moved a tool.

**Explanations are behind an (i).** Most of the help here is two sentences about
a trap. All of them on screen at once means none of them is read.

**Settings that belong to one decision are grouped, and the ones nobody changes
start folded.** A form of fifteen boxes is a form nobody reads.
"""

import json

from app import web

ICONS = web.read("page/icons.svg")

# The library screens bring their own glyphs, their own stylesheet and their own
# script. Kept in `app/libraryui.py` so the two halves of the app - the
# photographs and the forty-six features - can be read separately.
from app import libraryui as _LUI                 # noqa: E402

ICONS = ICONS.replace("</defs></svg>", _LUI.ICONS + "</defs></svg>")

STYLE = web.read("page/style.css")


# ------------------------------------------------------------------ appearance
#
# Three independent choices, all remembered per browser: the MODE (auto, light,
# dark - the button that was always there), a THEME that repaints the
# surfaces, and an ACCENT for everything you press. Written as data and turned
# into CSS here, because a hand-written grid of 5 themes x 2 modes x 7 accents
# is a grid with one cell wrong in it.
#
# The resolved mode is put on <html data-mode> by the page (and by a line that
# runs before the first paint), so a theme's dark palette can be picked by one
# attribute rather than by a media query repeated for every theme.
PALETTES = {
    # name: (label, light surfaces, dark surfaces) - bg, card, ink, dim, line
    # The default, drawn by the stylesheet's own tokens: the catalogue's black
    # stock in the dark and white stock in the light (4.0). The blue-grey that
    # was the default before it is still here, as Original.
    "classic": ("Catalogue", None, None),
    "original": ("Original", ("#eef1f5", "#ffffff", "#1b1e23", "#5d6470", "#dde2ea"),
                 ("#111316", "#1b1e24", "#e8eaee", "#98a0af", "#2b2f38")),
    "slate": ("Slate", ("#eceff3", "#fbfcfd", "#17202b", "#5a6573", "#d6dce4"),
              ("#0f141a", "#17202a", "#e6ebf1", "#93a0b0", "#253040")),
    "paper": ("Paper", ("#f3efe7", "#fffdf8", "#2a2520", "#6e655a", "#e3dccf"),
              ("#1a1714", "#23201c", "#efe8dd", "#a89d8f", "#36302a")),
    "nord": ("Nord", ("#e5e9f0", "#eceff4", "#2e3440", "#4c566a", "#d3d9e3"),
             ("#2e3440", "#3b4252", "#eceff4", "#aab3c5", "#4c566a")),
    "oled": ("Black", None,
             ("#000000", "#0c0c0d", "#ededee", "#9a9aa2", "#232327")),
    "sand": ("Sand", ("#f1ece2", "#fbf7ef", "#2f2a22", "#6b6256", "#e0d8c8"),
             ("#191714", "#242019", "#efe9dc", "#a79c8a", "#363026")),
    "moss": ("Moss", ("#e9efe9", "#f8fbf8", "#1d2620", "#55645b", "#d3dfd6"),
             ("#101614", "#182220", "#e3ece6", "#93a79c", "#26332e")),
    "ink": ("High contrast", ("#ffffff", "#ffffff", "#000000", "#3a3a3a", "#9a9a9a"),
            ("#000000", "#101010", "#ffffff", "#c8c8c8", "#6a6a6a")),
}
ACCENTS = {
    # name: (label, light, dark)
    # Ink is the default: a primary action printed in the page's own ink, black
    # on white stock and bone on black, so the only colours on the page are the
    # photographs and the five section inks.
    "ink": ("Ink", "#151514", "#f1efe9"),
    "blue": ("Blue", "#2c6bed", "#6ea0ff"),
    "teal": ("Teal", "#0e837a", "#3fc7b8"),
    "green": ("Green", "#1e864a", "#5cc98a"),
    "violet": ("Violet", "#6f4ad6", "#a78bfa"),
    "rose": ("Rose", "#cf2f68", "#f07aa3"),
    "amber": ("Amber", "#ab6300", "#f0b44c"),
    "graphite": ("Graphite", "#4a5260", "#b4bcc8"),
    "cyan": ("Cyan", "#0b7495", "#45b7da"),
    "lime": ("Lime", "#5a7a00", "#a8cc2c"),
    "coral": ("Coral", "#c04a2a", "#ff8f6b"),
    "indigo": ("Indigo", "#3a3fb8", "#8f94ff"),
}

# The third choice: the app's FRAME, apart from its pages.
#
# Two pickers decided everything at once - change the surfaces and the header
# changed with them - so the one thing people actually want, a frame that stands
# apart from the white page under it, was the one thing that could not be asked
# for. "Same as the pages" stays the default, because that is what it has always
# looked like.
CHROMES = {
    # name: (label, light background, dark background) - None means "as the card"
    "plain": ("Same as pages", None, None),
    "tinted": ("Tinted", "color-mix(in srgb,var(--accent) 9%,var(--card))",
               "color-mix(in srgb,var(--accent) 16%,var(--card))"),
    "deep": ("Deep", "color-mix(in srgb,var(--accent) 86%,#0b1020)",
             "color-mix(in srgb,var(--accent) 34%,#0b1020)"),
    "contrast": ("Contrast", "var(--ink)", "#000000"),
    "paper": ("Paper", "var(--bg)", "var(--bg)"),
}


# The text on a button filled with the accent. White on every light accent; on
# a dark-mode accent, which is light so that it reads as text on a dark page,
# white was 2:1 and under, so the label there is near-black instead. Worked
# out from the colour rather than listed, so a new accent cannot get it wrong.
# The near-black is the catalogue's warm black (4.0) rather than a navy, so a
# label reads as printed in the page's own ink whichever accent it sits on.
ON_DARK_TEXT, ON_LIGHT_TEXT = "#ffffff", "#121211"


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio of two #rrggbb colours."""
    def lum(h):
        h = h.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        out = []
        for i in (0, 2, 4):
            c = int(h[i:i + 2], 16) / 255
            out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def on_accent(colour: str) -> str:
    """Whichever of white and near-black reads better on this accent."""
    return max((ON_DARK_TEXT, ON_LIGHT_TEXT), key=lambda t: contrast(colour, t))


def appearance_css() -> str:
    out = []
    for name, (_label, light, dark) in PALETTES.items():
        for mode, vals in (("light", light), ("dark", dark)):
            if not vals:
                continue
            bg, card, ink, dim, line = vals
            out.append(f'html[data-mode="{mode}"][data-palette="{name}"]{{'
                       f"--bg:{bg};--card:{card};--ink:{ink};--dim:{dim};"
                       f"--line:{line};}}")
    for name, (_label, light, dark) in ACCENTS.items():
        for mode, colour in (("light", light), ("dark", dark)):
            out.append(f'html[data-mode="{mode}"][data-accent="{name}"]{{'
                       f"--accent:{colour};--on-accent:{on_accent(colour)};"
                       f"--accent-soft:color-mix(in srgb,{colour} 14%,var(--card));}}")
    # The frame. `--chrome` is what the header and the sidebar are painted, and
    # `--chrome-ink` is what can be read on it - worked out from the colour
    # rather than chosen, so a dark frame gets light type without anyone having
    # to remember to set it.
    for name, (_label, light, dark) in CHROMES.items():
        for mode, colour in (("light", light), ("dark", dark)):
            if not colour:
                continue
            out.append(f'html[data-mode="{mode}"][data-chrome="{name}"]{{'
                       f"--chrome:{colour};"
                       f"--chrome-ink:{'#f2f4f8' if name in ('deep', 'contrast') else 'var(--ink)'};"
                       f"--chrome-dim:{'rgba(242,244,248,.66)' if name in ('deep', 'contrast') else 'var(--dim)'};"
                       f"--chrome-line:{'rgba(255,255,255,.16)' if name in ('deep', 'contrast') else 'var(--line)'};}}")
    # Solid, the header as much as the rail (4.0): a see-through header let
    # the words scrolling under it show through its own.
    out.append("html[data-chrome] header,html[data-chrome] nav{"
               "color:var(--chrome-ink,var(--ink));"
               "border-color:var(--chrome-line,var(--line))}")
    out.append("html[data-chrome] header,html[data-chrome] nav{"
               "background:var(--chrome,var(--card))}")
    out.append("html[data-chrome] header button,html[data-chrome] nav a{"
               "color:var(--chrome-ink,var(--ink))}")
    out.append("html[data-chrome] header .note,html[data-chrome] #autosays span{"
               "color:var(--chrome-dim,var(--dim))}")
    return "\n".join(out)


STYLE = STYLE + "\n/* appearance: themes and accents */\n" + appearance_css()
STYLE = STYLE + "\n/* ---- 3.0: the library shell ---- */\n" + _LUI.STYLE


def looks_for_page() -> dict:
    """The same table, as the appearance panel draws its swatches from it."""
    base = {"light": ["#ffffff", "#ffffff", "#151514", "#5d5a54", "#dddad3"],
            "dark": ["#0f0f0e", "#181817", "#f1efe9", "#a8a49c", "#2e2d2a"]}
    return {"base": base,
            "palettes": {k: {"label": v[0], "light": list(v[1]) if v[1] else None,
                             "dark": list(v[2]) if v[2] else None}
                         for k, v in PALETTES.items()},
            "accents": {k: {"label": v[0], "light": v[1], "dark": v[2]}
                        for k, v in ACCENTS.items()},
            "chromes": {k: {"label": v[0], "has": bool(v[1] or v[2])}
                        for k, v in CHROMES.items()}}

# The page's own words (`page/strings.json`) come first, so every piece of the
# script can say `S.name` or `say("name", {...})`. app/pagetext.py explains
# why they are a table and how an edit on Setup > Wording reaches them.
SCRIPT = web.read("page/strings.js") + web.read("page/script.js")

SCRIPT = SCRIPT + _LUI.SCRIPT


# ------------------------------------------------------------ guide pictures
#
# One small drawing a page, in the page's own colours - they are drawn with the
# theme's variables, so they are right in dark mode and in every accent without
# a second set. Plain SVG in the page: nothing to fetch, nothing to go stale
# the way a screenshot does the day a button moves.
def _arrow(x1, y1, x2, y2):
    return (f'<path class="al" d="M{x1} {y1} L{x2} {y2}"/>'
            f'<path class="al" d="M{x2 - 6} {y2 - 5} L{x2} {y2} L{x2 - 6} {y2 + 5}"/>')


def _photo(x, y, w=34, h=26, cls="k"):
    return (f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="4"/>'
            f'<path class="ln" d="M{x + 5} {y + h - 5} l{w * .3:.0f} -{h * .4:.0f} '
            f'l{w * .2:.0f} {h * .2:.0f} l{w * .3:.0f} -{h * .25:.0f}"/>'
            f'<circle class="d" cx="{x + w - 9}" cy="{y + 8}" r="2.6"/>')


def _folder(x, y, label="", cls="k", w=58):
    return (f'<path class="{cls}" d="M{x} {y + 4} a4 4 0 0 1 4 -4 h14 l5 5 h{w - 27} '
            f'a4 4 0 0 1 4 4 v20 a4 4 0 0 1 -4 4 h-{w - 4} a4 4 0 0 1 -4 -4 z"/>'
            + (f'<text x="{x + w / 2}" y="{y + 19}" text-anchor="middle">{label}</text>'
               if label else ""))


def _stars(x, y, n=5, on=3, size=9):
    out = ""
    for i in range(n):
        cx = x + i * (size * 2 + 2)
        pts = []
        import math
        for k in range(10):
            r = size if k % 2 == 0 else size * .45
            a = -math.pi / 2 + k * math.pi / 5
            pts.append(f"{cx + r * math.cos(a):.1f},{y + r * math.sin(a):.1f}")
        out += f'<polygon class="{"y" if i < on else "gl"}" points="{" ".join(pts)}"/>'
    return out


ART = {
    "welcome": (
        '<rect class="k" x="28" y="30" width="70" height="78" rx="8"/>'
        '<rect class="as" x="38" y="42" width="50" height="9" rx="3"/>'
        '<rect class="as" x="38" y="57" width="50" height="9" rx="3"/>'
        '<circle class="g" cx="44" cy="96" r="3.5"/><circle class="d" cx="56" cy="96" r="3.5"/>'
        '<text x="63" y="124" text-anchor="middle">your library</text>'
        + _arrow(106, 68, 136, 68)
        + _photo(146, 40) + _photo(160, 54, cls="as") + _photo(174, 68)
        + _arrow(218, 68, 244, 68)
        + '<rect class="k" x="252" y="36" width="44" height="64" rx="7"/>'
        + _photo(258, 48, 32, 26, "as")
        + _stars(262, 88, 3, 2, 5)
        + '<text x="274" y="124" text-anchor="middle">tablet</text>'),
    "sample": (
        _folder(24, 52, "Inbox", w=70)
        + _photo(26, 90, 26, 20, "as") + _photo(56, 90, 26, 20)
        + _photo(86, 90, 26, 20, "as")
        + '<text x="59" y="40" text-anchor="middle">built for you</text>'
        + _arrow(120, 72, 150, 72)
        + _folder(158, 36, "2023", w=58) + _folder(158, 78, "2024", w=58)
        + _arrow(224, 72, 250, 72)
        + _photo(256, 44, 44, 34)
        + _stars(258, 88, 3, 3, 6)
        + '<text x="278" y="124" text-anchor="middle">practise</text>'),
    "plan": (
        '<rect class="k" x="20" y="18" width="120" height="96" rx="8"/>'
        '<rect class="as" x="30" y="30" width="60" height="7" rx="3"/>'
        + "".join(f'<rect class="gl" x="30" y="{46 + i * 14}" width="{95 - i * 12}" height="6" rx="3"/>'
                  for i in range(4))
        + '<circle class="k" cx="116" cy="34" r="9"/><circle class="a" cx="116" cy="34" r="3.5"/>'
        + '<text x="80" y="128" text-anchor="middle">what would happen</text>'
        + _arrow(150, 66, 186, 66)
        + '<rect class="a" x="196" y="50" width="104" height="32" rx="8"/>'
        + '<text x="248" y="70" text-anchor="middle" class="on">Apply</text>'
        + '<text x="248" y="104" text-anchor="middle">that list - nothing else</text>'),
    "trees": "".join(
        f'<text x="{x + 38}" y="16" text-anchor="middle">{name}</text>'
        + _folder(x + 8, 24, "2022", "k", 60)
        + _folder(x + 18, 60, "Spain", "as", 60)
        + f'<path class="ln" d="M{x + 14} 52 v22 h4"/>'
        + _folder(x + 18, 96, "Italy", "k", 60)
        + f'<path class="ln" d="M{x + 14} 74 v36 h4"/>'
        for x, name in ((12, "Photos"), (116, "RAW"), (220, "Previews")))
        + _arrow(92, 76, 112, 76).replace('class="al"', 'class="al dash"')
        + _arrow(196, 76, 216, 76).replace('class="al"', 'class="al dash"'),
    "identity": (
        _photo(30, 34, 70, 52) + '<text x="65" y="104" text-anchor="middle">P1010042.JPG</text>'
        + '<rect class="k" x="220" y="34" width="70" height="52" rx="4"/>'
        + '<text x="255" y="64" text-anchor="middle" class="i">RAW</text>'
        + '<text x="255" y="104" text-anchor="middle">P1010042.RW2</text>'
        + '<path class="al" d="M104 60 H216"/>'
        + '<rect class="as" x="122" y="44" width="76" height="32" rx="16"/>'
        + '<text x="160" y="58" text-anchor="middle" class="i">10:42:07</text>'
        + '<text x="160" y="70" text-anchor="middle">GH4 · same name</text>'),
    "library": (
        "".join(f'<rect class="{"a" if i == 3 else "as"}" x="{24 + i * 26}" y="{110 - h}" '
                f'width="18" height="{h}" rx="3"/>'
                f'<text x="{33 + i * 26}" y="124" text-anchor="middle">{y}</text>'
                for i, (y, h) in enumerate((("19", 30), ("20", 46), ("21", 62), ("22", 88), ("23", 54))))
        + "".join(_photo(172 + (i % 3) * 44, 20 + (i // 3) * 36, 38, 30,
                         "as" if i == 4 else "k") for i in range(6))
        + _stars(206, 104, 5, 4, 6)),
    # A grid of frames with three picked out of it, and the glass that picked
    # them: what the tab does, in one look.
    "search": (
        "".join(_photo(24 + (i % 4) * 46, 24 + (i // 4) * 44, 40, 34,
                       "a" if i in (1, 6) else "k") for i in range(8))
        + '<circle class="as" cx="196" cy="74" r="30" fill="none"/>'
        + '<circle class="a" cx="196" cy="74" r="30" fill="none"/>'
        + '<path class="a" d="M218 96 L244 122" stroke-width="6"/>'),
    # One shoot, four trees, and the pile at the end that can go: the picture
    # of the whole tab in one row of stacked bars.
    "storage": (
        "".join(
            f'<rect class="as" x="{28 + i * 34}" y="{112 - lib}" width="22" '
            f'height="{lib}" rx="3"/>'
            f'<rect class="a" x="{28 + i * 34}" y="{112 - lib - raw}" width="22" '
            f'height="{raw}" rx="3"/>'
            f'<rect class="gl" x="{28 + i * 34}" y="{112 - lib - raw - prev}" '
            f'width="22" height="{prev}" rx="3"/>'
            f'<text x="{39 + i * 34}" y="126" text-anchor="middle">{name}</text>'
            for i, (name, lib, raw, prev) in enumerate((
                ("19", 18, 22, 5), ("20", 26, 34, 6), ("21", 20, 30, 5),
                ("22", 34, 46, 8), ("23", 22, 28, 6))))
        + '<rect class="d" x="206" y="46" width="52" height="46" rx="6"/>'
        + '<text x="232" y="74" text-anchor="middle">free</text>'),
    "files": (
        '<rect class="k" x="14" y="16" width="130" height="98" rx="8"/>'
        '<rect class="as" x="24" y="26" width="56" height="10" rx="4"/>'
        + "".join(f'<rect class="{"as" if i == 1 else "gl"}" x="24" y="{46 + i * 18}" '
                  f'width="110" height="12" rx="3"/>' for i in range(3))
        + _arrow(150, 64, 176, 64)
        + '<rect class="k" x="186" y="16" width="118" height="98" rx="8"/>'
        + '<rect class="as" x="196" y="26" width="46" height="10" rx="4"/>'
        + '<rect class="as" x="196" y="46" width="98" height="12" rx="3"/>'
        + '<text x="160" y="104" text-anchor="middle">move</text>'),
    "geotag": (
        '<path class="ln" d="M16 96 H150"/>'
        + "".join(f'<circle class="{"a" if i == 3 else "d"}" cx="{24 + i * 20}" cy="96" r="4"/>'
                  for i in range(7))
        + '<text x="84" y="118" text-anchor="middle">your timeline</text>'
        + _photo(66, 30) + '<path class="al" d="M84 60 V88"/>'
        + '<rect class="k" x="180" y="16" width="124" height="96" rx="8"/>'
        + '<path class="ln" d="M190 90 q30 -40 60 -20 t44 -30"/>'
        + '<path class="a" d="M242 34 a13 13 0 0 1 13 13 c0 10 -13 24 -13 24 s-13 -14 -13 -24 a13 13 0 0 1 13 -13 z"/>'
        + '<circle class="k" cx="242" cy="47" r="5"/>'),
    "sort": (
        "".join(_photo(20 + (i * 17) % 60, 26 + (i * 23) % 60, 30, 24, "as" if i % 3 == 0 else "k")
                for i in range(7))
        + _arrow(116, 70, 152, 70)
        + _folder(166, 14, "2022", "k", 70)
        + '<path class="ln" d="M172 42 v18 h8 M172 60 v36 h8"/>'
        + _folder(182, 48, "07 July", "as", 84)
        + _folder(182, 84, "08 August", "k", 84)
        + '<text x="224" y="126" text-anchor="middle">you see this tree first</text>'),
    "separate": (
        _folder(18, 44, "", "k", 96)
        + _photo(26, 54, 22, 16, "as") + '<rect class="i" x="54" y="54" width="22" height="16" rx="3"/>'
        + '<rect class="a" x="82" y="54" width="22" height="16" rx="3"/>'
        + '<text x="66" y="96" text-anchor="middle">mixed</text>'
        + _arrow(124, 50, 176, 30) + _arrow(124, 70, 176, 70) + _arrow(124, 90, 176, 110)
        + _folder(186, 14, "Photos", "k", 90) + _folder(186, 54, "RAW", "as", 90)
        + _folder(186, 94, "Video", "k", 90)),
    "previews": (
        _photo(20, 24, 96, 72)
        + '<text x="68" y="114" text-anchor="middle">24 MB original</text>'
        + _arrow(126, 60, 162, 60)
        + _photo(172, 42, 44, 34, "as")
        + '<text x="194" y="94" text-anchor="middle">1 MB</text>'
        + '<rect class="k" x="236" y="26" width="62" height="86" rx="8"/>'
        + _photo(243, 38, 48, 36, "as") + _stars(248, 92, 3, 3, 5)),
    "ratings": (
        '<rect class="k" x="18" y="24" width="68" height="88" rx="8"/>'
        + _photo(26, 34, 52, 38, "as") + _stars(30, 88, 3, 3, 6)
        + '<text x="52" y="126" text-anchor="middle">tablet</text>'
        + _arrow(96, 68, 136, 68)
        + _photo(148, 22, 60, 44) + _stars(152, 80, 5, 3, 5)
        + '<circle class="r" cx="160" cy="98" r="6"/><circle class="y" cx="176" cy="98" r="6"/>'
        + '<rect class="as" x="220" y="30" width="80" height="22" rx="11"/>'
        + '<text x="260" y="45" text-anchor="middle" class="i">beach</text>'
        + '<rect class="as" x="220" y="60" width="80" height="22" rx="11"/>'
        + '<text x="260" y="75" text-anchor="middle" class="i">family</text>'
        + '<text x="260" y="104" text-anchor="middle">searchable tags</text>'),
    "develop": (
        _photo(18, 36, 64, 48) + '<circle class="r" cx="30" cy="30" r="7"/>'
        + _arrow(92, 60, 124, 60)
        + _folder(132, 44, "Develop", "as", 70)
        + '<path class="al" d="M168 88 q0 26 -40 26 h-44"/>'
        + '<path class="al" d="M92 108 L84 114 L92 120"/>'
        + '<text x="210" y="124" text-anchor="middle">edited version comes home</text>'
        + '<rect class="k" x="222" y="30" width="80" height="56" rx="6"/>'
        + '<path class="al" d="M232 76 q14 -30 30 -10 t30 -24"/>'),
    "cleanup": (
        "".join(_photo(20 + i * 14, 30 + i * 10, 40, 30, "as" if i == 2 else "k") for i in range(3))
        + _arrow(96, 64, 130, 64)
        + _folder(140, 50, "_Culled", "k", 70)
        + '<circle class="gl2" cx="262" cy="64" r="36"/>'
        + '<path class="gg" d="M262 28 a36 36 0 0 1 34 46"/>'
        + '<text x="262" y="62" text-anchor="middle" class="i">2.4 GB</text>'
        + '<text x="262" y="76" text-anchor="middle">freed</text>'),
    "automation": (
        '<circle class="as" cx="70" cy="40" r="20"/><circle class="as" cx="160" cy="96" r="20"/>'
        '<circle class="as" cx="250" cy="40" r="20"/>'
        '<text x="70" y="44" text-anchor="middle" class="i">watch</text>'
        '<text x="160" y="100" text-anchor="middle" class="i">run</text>'
        '<text x="250" y="44" text-anchor="middle" class="i">report</text>'
        + _arrow(92, 48, 138, 86) + _arrow(182, 86, 228, 50)
        + '<path class="al dash" d="M230 30 Q160 -6 92 30"/>'),
    "setup": (
        "".join(f'<path class="ln" d="M24 {34 + i * 30} H130"/>'
                f'<circle class="a" cx="{50 + i * 30}" cy="{34 + i * 30}" r="7"/>'
                for i in range(3))
        + '<rect class="k" x="170" y="16" width="130" height="100" rx="8"/>'
        + "".join(f'<circle class="{c}" cx="188" cy="{36 + i * 20}" r="6"/>'
                  f'<rect class="gl" x="202" y="{33 + i * 20}" width="{80 - i * 10}" height="6" rx="3"/>'
                  for i, c in enumerate(("g", "g", "y", "g")))),
}


# ------------------------------------------------------------------ the guide
#
# A tour, not a manual. One idea a page, three sentences at most, and a button
# that takes you to the feature it is about - because the fastest way to learn
# what "Separate RAWs" does is to open it and press Check the list,
# which writes nothing.
#
# Kept here as DATA rather than written into the page, so a test can check every
# page still points at a feature that exists. A guide that sends you to a tab
# renamed last month is worse than no guide.
GUIDE = [
    {"title": "Welcome", "art": "welcome",
     "body": ["Photo Manager looks after your photo library, wherever it is "
              "kept. It sorts, geotags, makes previews for a tablet, carries "
              "ratings and sends the best ones to be edited.",
              "Nothing happens until you say so. Every tool shows you exactly "
              "what it would do first."],
     "open": ""},
    {"title": "Finding your way", "art": "library", "spot": "#rail",
     "body": ["Home, Photos, Places, Albums and People show your photo "
              "library, read from the index. Tools lists every tool in "
              "groups, and Settings is the last group.",
              "Arrange on All tools lets you drag a tool to another group, or "
              "into the Bin to take it out of every list."],
     "open": ""},
    {"title": "Practise on a sample", "art": "sample",
     "body": ["Sample library, under Settings, builds one of its own: real "
              "dates and cameras, RAWs, duplicates, a bracketed set, a clock "
              "two hours fast.",
              "Point Setup at it and every tool works on that instead of "
              "your photos. Remove it and your own folders come back."],
     "open": "demo"},
    {"title": "RAW, preview, sidecar", "art": "plan",
     "body": ["A RAW file is the camera's own file beside the JPEG: bigger, "
              "better to edit, useless to browse. A preview is a small JPEG "
              "made for rating on a tablet. A sidecar is a text file beside "
              "a photo holding its stars and tags."],
     "open": ""},
    {"title": "Mirroring, and the index", "art": "plan",
     "body": ["Mirroring means a second tree of folders shaped exactly like "
              "your photo folders. A RAW file is found by where it sits, not "
              "by a database.",
              "The index is this app's own list of what is in your library, "
              "so a screen opens without reading every file first."],
     "open": ""},
    {"title": "Look first, then apply", "art": "plan", "spot": "#go",
     "body": ["Check the list reads and decides, and writes nothing. Apply "
              "does exactly that list, not a fresh one, and says what it is: "
              "'Move 412 files'.",
              "Anything that cannot be taken back is red and asks a second "
              "time. If something fails you are told why."],
     "open": ""},
    {"title": "The trees", "art": "trees",
     "body": ["Your photos live in up to five folders, set once in Setup. "
              "They are the library (JPEGs), RAW files, previews for a "
              "tablet, video, and the develop tree for editing.",
              "The other trees mirror the library: 2022/Spain in the library "
              "is 2022/Spain everywhere."],
     "open": "setup"},
    {"title": "Matched by identity", "art": "identity",
     "body": ["A photo is matched to its RAW file and its preview by capture "
              "time, camera and name, not by where it sits.",
              "So renaming or reorganising folders never breaks the link, and a "
              "rating made on the tablet still finds its way home."],
     "open": ""},
    {"title": "Library", "art": "library",
     "body": ["Opens on a dashboard: how many photos, how much space, how "
              "far along, and the years, cameras, apertures and stars drawn "
              "rather than listed.",
              "Under it, every folder and what has been done to it. Search "
              "and Compare are in the list beside it."],
     "open": "library", "covers": ["search", "compare"]},
    {"title": "Storage and charts", "art": "storage",
     "body": ["Space by folder: the library, its RAW files, previews and "
              "video side by side, biggest first, and what could be freed.",
              "Compare puts two things against each other as a grid: aperture "
              "against lens, stars against year."],
     "open": "space", "covers": []},
    {"title": "Search", "art": "search",
     "body": ["Find photos by what they are: camera, lens, focal length, "
              "aperture, shutter, ISO, stars, tags, location.",
              "Every box narrows it further. Keep a search by name, and send "
              "what it finds to File explorer as one set."],
     "open": "search"},
    {"title": "File explorer", "art": "files",
     "body": ["A file manager for your trees: two panes, copy, move, rename, "
              "new folder, delete to the Recycle Bin, download.",
              "Move a photo and its RAW and preview go with it. Power rename puts "
              "every folder in a table you type straight into."],
     "open": "files", "covers": ["rename"]},
    {"title": "Geotag", "art": "geotag",
     "body": ["Puts a location on photos from your Google Timeline, by the "
              "moment each was taken.",
              "Clock wrong? Fix the clock first. Pinned to the wrong place? "
              "Strip location takes it off a folder."],
     "open": "geotag"},
    {"title": "Sort into folders", "art": "sort",
     "body": ["Files a card's worth of photos into year/shoot folders, under "
              "whichever parent you choose.",
              "You see the new tree before a single file moves."],
     "open": "bydate"},
    {"title": "Separate RAWs and video", "art": "separate",
     "body": ["Moves RAW files and videos out of the library into their own "
              "trees, keeping each at the same position.",
              "Re-mirror catches them up after you reorganise the library."],
     "open": "unpair", "covers": ["videos"]},
    {"title": "Make previews", "art": "previews",
     "body": ["Small JPEGs for a tablet or phone, carrying the original's "
              "date, camera and tags. What you rate there comes back to the "
              "right file."],
     "open": "previews"},
    {"title": "Rating & tags", "art": "ratings",
     "body": ["Carries stars and colours from the tablet to the originals "
              "and RAWs. Apply label colours a whole folder.",
              "Tag photos writes real tags, by folder or by a rule, that "
              "other photo apps such as Lightroom can search."],
     "open": "ratings"},
    {"title": "Send to develop", "art": "develop",
     "body": ["Copies the photos you marked for editing into the develop tree, "
              "with their RAWs if you want them.",
              "When an edited version appears, it is spotted and filed back."],
     "open": "develop"},
    {"title": "Cull and clean up", "art": "cleanup",
     "body": ["Cull by rating, thin brackets, find duplicates and blurry "
              "photos. Nothing is deleted outright. It is moved aside, and "
              "you see how much space came back.",
              "Clean up empties those piles when you are sure. Delete folder "
              "sends a shoot, with its RAWs and previews, to the Recycle Bin."],
     "open": "cull", "covers": ["cleanup", "delfolder"]},
    {"title": "Automation", "art": "automation",
     "body": ["A flow is a chain of tools that runs by itself when the "
              "folder it watches changes.",
              "Build one in Flows. Runs shows what each pass did."],
     "open": "automation"},
    {"title": "Setup", "art": "setup",
     "body": ["The trees, the folders to skip everywhere, what each colour "
              "means, and the password. On a Synology, Reindex refreshes its own "
              "photo index and Permissions checks the share.",
              "Checklist says what is missing. Backup keeps the app's own "
              "state, but never the password."],
     "open": "setup", "covers": ["checklist", "backup"]},
]

for _page in GUIDE:
    _page["svg"] = ART.get(_page.get("art", ""), "")

# ------------------------------------------------------------ service worker
#
# What it is for, and what it deliberately does NOT do.
#
# Installed on a phone, this has to open when the NAS is asleep or the phone is
# on mobile data - otherwise it is a browser tab with an icon. So the shell is
# kept: the page, the icons, and the thumbnails already looked at.
#
# It never caches the PAGE ahead of the network, though, and never caches an
# API answer at all. The whole header of this app exists to prove you are
# looking at the running process; a worker that served yesterday's page from
# its own store would break that in the one place it matters, and the fault
# would look exactly like a Restart that did not take.
SERVICE_WORKER = web.read("page/sw.js")

# The typeface, as bytes, for the server's /font/ route (app/web/fonts).
FONTS = web.fonts()

STRINGS = json.loads(web.read("page/strings.json"))

PAGE = web.fill(web.read("page/index.html"),
                STYLE=STYLE, ICONS=ICONS, SCRIPT=SCRIPT,
                GUIDE_JSON=json.dumps(GUIDE),
                LOOKS_JSON=json.dumps(looks_for_page()),
                STRINGS_JSON=json.dumps(STRINGS, ensure_ascii=False))
