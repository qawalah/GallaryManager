"""The design system, as a rule rather than an intention.

A UX review of 3.3 said the architecture is right and the remaining work is
consistency: "define a tiny design system - Primary, Secondary, Tertiary,
Destructive, Filter, Contextual - and do not create one-off button styling per
feature". A document saying that is worth very little; the fourth feature
written after it will have its own button again, and nobody will notice for
three releases.

So the rules are here, and they fail. Adding a seventh kind of button, or a
fifth card radius, breaks a test that names what to do instead.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import libraryui as L               # noqa: E402
from app import page as P                    # noqa: E402

CSS = P.STYLE + L.STYLE


def rules():
    """(selector, body) for every rule in the app's stylesheet."""
    body = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    return [(" ".join(sel.split()), decl)
            for sel, decl in re.findall(r"([^{}]+)\{([^{}]*)\}", body)]


class TheSixRoles(unittest.TestCase):
    """Primary, Secondary, Quiet, Destructive, Filter, Contextual."""

    ROLES = {"button": "primary", "button.ghost": "secondary",
             "button.quiet": "quiet", "button.danger": "destructive",
             ".fchip": "filter", ".pillbtn": "contextual"}

    def test_every_role_has_a_definition_of_its_own(self):
        """Its own base rule - the one that says what the role LOOKS like. A
        phone stylesheet may of course adjust it afterwards; what must not
        happen is a role with no definition, or two of them."""
        bases = [sel for sel, _b in rules() if sel in self.ROLES]
        for sel, role in self.ROLES.items():
            self.assertIn(sel, bases, f"the {role} role has no definition")
        self.assertEqual(sorted(set(bases)), sorted(self.ROLES),
                         "a role is missing")

    def test_they_are_told_apart_by_more_than_colour(self):
        """A role somebody cannot see is not a role. Each carries a different
        shape, weight or border - not only a different hue."""
        said = {}
        for sel, body in rules():                  # the FIRST, which is the base
            if sel in self.ROLES and sel not in said:
                said[sel] = body
        self.assertIn("border:0", said["button"].replace(" ", ""))
        self.assertIn("border:1px", said["button.ghost"])
        self.assertIn("text-decoration", said["button.quiet"])
        self.assertIn("--r-pill", said[".fchip"])

    def test_no_feature_invents_a_seventh_kind_of_button(self):
        """The whole point of the review's P0. A new rule that paints a button
        its own colour has to justify itself HERE - by being added to this list
        with a reason, or by using one of the six roles instead.

        What is on the list is either a role or a SURFACE: the viewer's glass,
        the rail, a menu, the marks in the tree. Those are not buttons wearing
        a different coat, they are different places.
        """
        allowed = {
            # the roles
            "button", "button.ghost", "button.quiet", "button.danger",
            ".fchip", ".fchip.on", ".pillbtn",
            # surfaces, each defined once in its own place
            ".vbtn", ".vbtn:hover", ".vbtn.on", ".vchip", ".vchip:hover",
            ".vpill", ".vpill:hover", ".vtoast button", ".viewtabs button",
            ".viewtabs button.on", ".dstars button", ".dtabs button",
            ".fmenu button", ".fmenu button:hover", ".pick li button",
            ".pick li button:hover", ".pick li button.afile.chosen",
            ".seg button", ".seg button.on",
            ".twists button", ".twists button:hover:not(:disabled)",
            "#bottom button", "#scrub button", "#scrub button:hover",
            ".monthrow button", ".boardbar button.on", ".cat .list button",
            ".feat", ".feat:hover", ".feat .fic", ".feat:hover .fic",
            ".chip", ".chip button", ".fmchip", ".patchip button",
            ".lookmode button", ".lookmode button.on", ".lookacc button",
            ".lookpal button", ".pmzoom button", ".rngroup button.on",
            ".wbtn", "button.fmweigh.ask", "header button.on",
            "button.quiet:hover", "header button",
            # The header's controls are bare until a pointer reaches one; the
            # hover is the same surface, lit.
            "header button:hover",
            # The marks in the folder tree: three states that have to be told
            # apart at a glance, which is a meaning rather than an action.
            "button.pip",
            # The NAS line in the Settings card is not a button: it is a row
            # holding one filter chip per tab, painted like the rows round it.
            ".cat .list .featgroup",
            # The tool rows on the Tools screen are the same `.feat` surface,
            # said once more at the specificity needed to undo the chip
            # painting `.cat .list button` gives everything in that list.
            ".cat .list .feat", ".feat:hover,.cat .list .feat:hover",
            "header button, .chip button, button",
        }
        painted = []
        for sel, body in rules():
            if not re.search(r"button|btn|\.fchip|\.pillbtn|\.feat|\.chip", sel):
                continue
            if "background" not in body:
                continue
            if sel in allowed:
                continue
            painted.append(sel)
        self.assertEqual(sorted(set(painted)), [],
                         "these paint a button themselves - use one of the six "
                         "roles, or add it above with a reason: "
                         + ", ".join(sorted(set(painted))))


class OneSetOfShapes(unittest.TestCase):
    """A card was 10px here, 12px there and 13px on the Tools screen."""

    CARDS = (".card{", ".bigtile{", ".albumcard{", ".cat{", ".arrgroup{")

    def test_every_card_uses_the_same_radius(self):
        """The base rule of each - a phone stylesheet may change the margins
        afterwards, which is why this looks for the one that sets a radius."""
        for name in self.CARDS:
            sets = [body for sel, body in rules()
                    if sel == name.rstrip("{") and "border-radius" in body]
            self.assertTrue(sets, f"{name.rstrip('{')} has no radius at all")
            for body in sets:
                self.assertIn("--r-card", body,
                              f"{name.rstrip('{')} sets its own radius")

    def test_and_the_shapes_are_named_in_one_place(self):
        for token in ("--r-card:", "--r-ctl:", "--r-pill:", "--pad-card:"):
            self.assertEqual(CSS.count(token), 1,
                             f"{token} is defined more than once")


class OneOfEachComponent(unittest.TestCase):
    """The third audit's page findings: one fold, one chip, one set of label
    colours, one breakpoint, and primary buttons that can be read."""

    def test_no_fold_row_or_group_heading_shouts(self):
        """Group headings were in capitals and the More settings row was not;
        all of them are sentence case now."""
        for sel, decl in rules():
            if re.search(r"summary|legend", sel):
                self.assertNotIn("text-transform:uppercase", decl, sel)

    def test_there_is_one_fold_for_more_settings(self):
        js = P.SCRIPT
        self.assertEqual(js.count("function moreFold("), 1)
        self.assertNotIn("<summary>More</summary>", js)
        self.assertNotIn("<summary>Advanced", js)
        self.assertEqual(len([s for s, _ in rules() if s == "details.fold>summary"]), 1)

    def test_a_primary_button_can_be_read_in_every_accent_and_mode(self):
        """White on the dark accents was 2:1 to 2.7:1."""
        for name, (_label, light, dark) in P.ACCENTS.items():
            for mode, colour in (("light", light), ("dark", dark)):
                self.assertGreaterEqual(
                    P.contrast(colour, P.on_accent(colour)), 4.5, f"{name} {mode}")
        # the base palette, before any accent is chosen: the catalogue's ink
        # (4.0), read straight from the stylesheet so the two cannot drift
        light = re.search(r":root\{color-scheme:light;[^}]*?--accent:(#\w+);[^}]*?--on-accent:(#\w+);",
                          P.STYLE, re.S)
        dark = re.search(r'html\[data-theme="dark"\]\{color-scheme:dark;[^}]*?'
                         r"--accent:(#\w+);[^}]*?--on-accent:(#\w+);", P.STYLE, re.S)
        for got in (light, dark):
            self.assertIsNotNone(got)
            self.assertGreaterEqual(P.contrast(*got.groups()), 4.5, got.groups())
        button = [d for s, d in rules() if s == "button"][0]   # the base rule
        self.assertIn("color:var(--on-accent)", button)

    def test_the_label_colours_are_named_once(self):
        """A JS map said #f5c518 and the stylesheet #f5c400."""
        for c in ("red", "yellow", "green", "blue", "purple"):
            self.assertEqual(len(re.findall(rf"--label-{c}:", CSS)), 1, c)
        photos = L.SCRIPT[L.SCRIPT.index("function colourOf("):]
        photos = photos[:photos.index("\n}") ]
        self.assertNotRegex(photos, r"#[0-9a-fA-F]{6}")
        self.assertNotRegex(CSS, r"\.c-(red|yellow|green|blue|purple)\{background:#")

    def test_there_is_one_chip_shape(self):
        """The header pill, a value chip and a filter pill were three heights,
        three radii and three sizes of type."""
        got = {}
        for sel, decl in rules():
            got.setdefault(sel, decl)            # the base rule, not a phone's
        for sel in ("#autobar", ".chip", ".fchip"):
            decl = got.get(sel, "")
            self.assertIn("var(--chip-fs)", decl, sel)
            self.assertIn("var(--r-pill)", decl, sel)
            self.assertIn("var(--chip-h)", decl, sel)
        # a status that opens something says so
        self.assertIn("#autobar::after", got)

    def test_there_is_one_breakpoint(self):
        """720 in the script, 860 in the rail's stylesheet, 700 and 620 for
        one rule each."""
        widths = set(re.findall(r"@media[^{]*?(?:max|min)-width:(\d+)px", CSS))
        self.assertLessEqual(widths, {"860", "861", "1060"}, widths)
        self.assertIn("const PHONE_MAX = 860;", P.SCRIPT)
        self.assertNotIn("max-width:720px", P.SCRIPT)

    def test_nothing_styles_markup_that_is_never_drawn(self):
        from app import libraryui
        self.assertFalse(hasattr(libraryui, "SHELL"))
        for gone in ("#detail", ".backbar", ".btnlink", ".fmgroup"):
            self.assertFalse([s for s, _ in rules() if gone in s.split(",")[0]
                              or any(x.strip().startswith(gone) for x in s.split(","))],
                             gone)
        self.assertNotIn('classList.add("installed")', P.SCRIPT)


class OneWordPerIdea(unittest.TestCase):
    """The terminology lock, checked against the page that is actually built."""

    PAGE = P.PAGE + P.SCRIPT

    def test_the_old_synonyms_are_gone(self):
        for gone in ("Show me what would happen", "Have a look", "Go ahead with",
                     "Look again"):
            # the comments explaining the history are allowed to name them
            body = re.sub(r"/\*.*?\*/", "", self.PAGE, flags=re.S)
            self.assertNotIn(gone, body, f"{gone!r} is still on the page")

    def test_and_the_vocabulary_is_written_down_once(self):
        self.assertIn("const WORDS", self.PAGE)
        for word in ("check:", "apply:", "again:", "run:", "more:", "done:",
                     "back:"):
            self.assertIn(word, self.PAGE)


if __name__ == "__main__":
    unittest.main()


class PlainEnglishBesideTheJargon(unittest.TestCase):
    """"Never make the user learn your internal data model to do a normal photo
    task. Advanced terminology can remain visible, but it needs a plain-language
    explanation beside it."

    The technical names stay - they are what these things are called everywhere
    else, and renaming them would only move the problem. What each one MEANS is
    what had to be added.
    """

    def tasks(self):
        from app import registry as R
        import app.tasks                                   # noqa: F401
        return R.all_tasks()

    def test_every_feature_says_what_it_does_in_one_line(self):
        for t in self.tasks():
            said = t.one_line()
            self.assertTrue(said, f"{t.name} has no one-line explanation")
            self.assertLess(len(said), 160, f"{t.name}: that is a paragraph")

    def test_the_ones_with_jargon_in_their_name_explain_it(self):
        """A person who does not know what a RAW is should be able to read the
        line under "Separate RAWs" and know whether they want it."""
        wants = {
            "unpair": ("camera", "folder"),
            "remirror": ("match", "folder"),
            "previews": ("small", "photos"),   # "small copies" is the glossary's old word
            "reindex": ("NAS", "changed"),
            "cull": ("aside",),
            "thin": ("keep", "spares"),
        }
        from app import registry as R
        for name, words in wants.items():
            said = R.get(name).one_line().lower()
            for word in words:
                self.assertIn(word.lower(), said,
                              f"{name} does not say {word!r}: {said!r}")

    def test_and_the_words_themselves_are_explained_somewhere(self):
        """One page, in the guide, for the five words this app cannot avoid."""
        from app import page as _P
        guide = " ".join(" ".join(p.get("body", [])) for p in _P.GUIDE)
        for word in ("RAW", "PREVIEW", "SIDECAR", "MIRROR", "INDEX"):
            self.assertIn(word, guide.upper(),
                          f"nothing in the guide says what a {word} is")


class TheCatalogue(unittest.TestCase):
    """4.0: the page as a printed catalogue. Black stock and white stock, one
    typeface on one scale, five section inks and a primary action printed in
    the page's own ink. What is held here is what would quietly drift: a size
    off the scale, a section ink that stops reading, a stripe down a card's
    side, and the old look going missing from Appearance."""

    SCALE = {"12", "13", "14", "16", "20", "28", "40", "64"}

    def test_every_size_of_type_is_on_the_scale(self):
        """Twelve sizes on one screen, many half a pixel apart, was the
        critique's flat hierarchy. The viewer's arrow and star glyphs are
        drawn at their own size because they are pictures, not words."""
        glyphs = {"34", "38"}
        sizes = set(re.findall(r"font-size:(\d+(?:\.\d+)?)px", CSS))
        self.assertEqual(sizes - self.SCALE - glyphs, set())
        for token, px in (("--t-xs", 12), ("--t-s", 13), ("--t-m", 14), ("--t-l", 16),
                          ("--t-xl", 20), ("--t-2xl", 28), ("--t-3xl", 40),
                          ("--t-4xl", 64)):
            self.assertIn(f"{token}:{px}px", CSS.replace(" ", ""))

    def test_the_typeface_is_the_apps_own(self):
        """Served from the app, never asked of the internet: the page runs on
        a NAS with nothing online."""
        self.assertIn('url("font/archivo-latin.woff2")', CSS)
        self.assertNotRegex(CSS, r"url\(\"?https?:")
        self.assertIn("var(--font)", CSS)

    def test_the_section_inks_read_on_both_stocks(self):
        """Each group's ink is used for words (the verb over a count, a
        group's name), so each must read as text on the page and on a card,
        in the light and in the dark."""
        shell = L.STYLE
        light = dict(re.findall(r"--tone-(\w+):(#[0-9a-f]{6})",
                                shell[shell.index(":root{"):shell.index("@media")]))
        dark_block = shell[shell.index('html[data-theme="dark"]{'):]
        dark = dict(re.findall(r"--tone-(\w+):(#[0-9a-f]{6})",
                               dark_block[:dark_block.index("}")]))
        tones = {"blue", "teal", "orange", "purple", "grey"}
        self.assertEqual(set(light), tones)
        self.assertEqual(set(dark), tones)
        # The stocks as the stylesheet sets them: the ground and the card.
        def stock(block):
            return re.search(r"--bg:(#[0-9a-f]{6});\s*--card:(#[0-9a-f]{6})", block).groups()
        style = P.STYLE
        stocks = {"light": stock(style[style.index(":root{"):]),
                  "dark": stock(style[style.index('html[data-theme="dark"]{'):])}
        self.assertEqual(stocks["light"], ("#ffffff", "#ffffff"),
                         "the light page is white stock, ground and card alike")
        for mode, inks in (("light", light), ("dark", dark)):
            for tone, ink in inks.items():
                for stock in stocks[mode]:
                    self.assertGreaterEqual(P.contrast(ink, stock), 4.5,
                                            f"{tone} on {stock} ({mode})")

    def test_the_ink_accent_is_the_default_and_the_old_look_is_kept(self):
        """The new look is what a new browser gets; the blue-grey before it
        is a theme and an accent you can still pick."""
        self.assertEqual(next(iter(P.ACCENTS)), "ink")
        self.assertIn('localStorage.getItem("pm-accent") || "ink"', P.PAGE)
        self.assertIn('readLook("pm-accent", "ink")', P.SCRIPT)
        self.assertEqual(P.PALETTES["original"][1][:2], ("#eef1f5", "#ffffff"))
        self.assertEqual(P.ACCENTS["blue"][1:], ("#2c6bed", "#6ea0ff"))

    def test_nothing_is_striped_down_its_side(self):
        """A coloured stripe down one side of a card says "status" in every
        admin panel ever made. A state here is banded across the top."""
        self.assertNotRegex(CSS, r"border-left:\s*[2-9]px")
        self.assertNotRegex(CSS, r"border-left-width:\s*[2-9]px")
        self.assertNotRegex(CSS, r"inset\s+[2-9]px\s+0\s+0")

    def test_the_new_motion_stops_for_anybody_who_asked_for_less(self):
        self.assertIn("@keyframes pm-turn", CSS)
        tail = CSS[CSS.rindex("@media (prefers-reduced-motion: reduce)"):]
        self.assertIn("animation:none !important", tail)
        self.assertIn("transition:none !important", tail)

    def test_the_page_says_out_loud_what_it_shows(self):
        """A live region the toasts, the list and the result are read into,
        and a way past the header and the rail for a keyboard."""
        body = P.PAGE[P.PAGE.index("<body>"):]
        self.assertRegex(body, r'<div id="said" class="sronly" role="status" aria-live="polite">')
        first = re.search(r"<(a|button|input|select)\b[^>]*>", body.split("{{ICONS}}")[-1])
        self.assertIn('id="skiplink"', first.group(0))
        for wrapped in ("toast = function", "render = function", "finish = function"):
            self.assertIn(wrapped, L.SCRIPT)
