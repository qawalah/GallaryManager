"""One way of doing each thing, held in place.

These are cheap assertions about the page's source rather than about a browser,
and they exist because every one of them was a thing that drifted: two tooltip
engines bound to the same attribute, two dropdown mechanisms styled from two
different palettes, a modal under the phone's nav bar, the same three
destinations offered twice on a 390px screen.

A rule nobody checks is a rule that lasts until the next feature.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import page as P                        # noqa: E402

SRC = P.STYLE + P.SCRIPT if hasattr(P, "STYLE") else ""


def _src():
    """The page's own source, however it is put together.

    page.py reads its markup, style and script from app/web/page/, so those
    files are part of its source as much as the module is."""
    import inspect
    from app import web, libraryui
    where = os.path.join(web.HERE, "page")
    # The library screens are joined into the same page, so a rule about the
    # page's script is a rule about them too; reading only app/web/page/ let
    # four native dialogs through.
    return inspect.getsource(P) + "".join(
        web.read("page/" + name) for name in sorted(os.listdir(where))) \
        + libraryui.STYLE + libraryui.SCRIPT


class OneWayOfDoingIt(unittest.TestCase):
    def setUp(self):
        self.src = _src()

    def test_there_is_exactly_one_tooltip_engine(self):
        """Two of them, both bound to [data-tip], meant every bar and slice
        opened two bubbles at once - one under the mark and one by the
        pointer."""
        self.assertNotIn("viztip", self.src)
        self.assertEqual(self.src.count("function showTip("), 1)

    def test_a_path_handed_to_an_onclick_goes_through_quoted(self):
        """Escaping only the apostrophe left every backslash for JavaScript to
        read: `listDir('C:\\')` is a syntax error, so on Windows a click on a
        drive in the folder picker did nothing at all, and `N:\\Photos` arrived
        as `N:Photos`. One helper does both, and nothing goes round it."""
        whole = P.SCRIPT
        self.assertEqual(whole.count("function quoted("), 1)
        self.assertEqual(re.findall(r"esc\([^\n]*\)\.replace\(/'/g", whole), [])

    def test_nothing_typed_reaches_an_onclick_through_esc_alone(self):
        """esc() is for HTML, and leaves ' and \\ alone. Inside onclick="f('...')"
        that is a string a name can close: an album called "Mum's" was a card
        that did nothing, and a name ending "');alert(1)//" ran. quoted() does
        both jobs, so every value spliced into a handler goes through it - in
        the whole page, the library screens included."""
        whole = P.PAGE
        found = [m.group(0)[:80] for m in re.finditer(r'on\w+="[^"]*"', whole)
                 if "'${esc(" in m.group(0)]
        self.assertEqual(found, [])

    def test_the_page_menus_do_not_borrow_the_viewer_popup(self):
        """`.vpop` is a dark box with a palette nailed to it, and it is declared
        after `.fmmenu` was, so on a light theme the menu kept the dark
        background and took back the dark text: 1.0:1, unreadable."""
        self.assertNotIn('"vpop fmmenu"', self.src)
        self.assertIn(".pmenu{", self.src)
        self.assertIn("background:var(--card)", self.src)

    def test_every_page_menu_goes_through_one_opener(self):
        self.assertEqual(self.src.count("function pageMenu("), 1)
        # and the two old near-copies are gone
        self.assertEqual(self.src.count('className = "vpop fmmenu"'), 0)

    def test_a_menu_lays_glass_behind_itself_so_a_tap_can_close_it(self):
        """A tap on plain background does not reliably reach a document click
        listener on iOS, so a menu that listened only for that could be opened
        and then not closed."""
        self.assertIn("#menuscrim", self.src)
        self.assertGreaterEqual(self.src.count('id = "menuscrim"'), 2)

    def test_every_menu_sits_above_the_glass_that_closes_it(self):
        """The scrim is in front of the page on purpose. A menu BEHIND it would
        have every item dead - which is what `.fmenu`'s old z-index of 20 would
        have made of the folder menu the moment the scrim was added."""
        glass = int(re.search(r"#menuscrim\{[^}]*z-index:(\d+)",
                             self.src).group(1))
        for sel in (r"\.fmenu\{", r"\.pmenu\{"):
            rule = re.search(sel + r"[^}]*\}", self.src)
            self.assertIsNotNone(rule, sel)
            z = int(re.search(r"z-index:(\d+)", rule.group(0)).group(1))
            self.assertGreater(z, glass, sel)

    def test_a_chart_hands_its_folders_to_the_search_it_leads_to(self):
        """A chart of one shoot led to a search of the whole library: the bar
        said 4 and the table that opened said 60, which makes the chart look
        wrong when it was the search that had quietly widened."""
        self.assertIn("function searchFor(ask, where)", self.src)
        self.assertIn("PLAN.charts.folders", self.src)

    def test_both_kinds_of_menu_become_a_sheet_on_a_phone(self):
        self.assertRegex(self.src, r"\.fmenu,\.pmenu\{position:fixed !important")

    def test_the_app_asks_its_questions_in_its_own_dialog(self):
        """The browser's prompt() freezes the page, cannot be styled, and on a
        phone reads as an error - and an installed iOS web app suppresses it,
        so "Keep as an album" did nothing there. Checked over the whole joined
        script, comments aside, and whatever follows the parenthesis."""
        code = re.sub(r"/\*.*?\*/", "", P.SCRIPT, flags=re.S)
        code = re.sub(r"(?m)^\s*//.*$", "", code)
        self.assertEqual(
            re.findall(r"(?<![\w.$])(?:prompt|confirm|alert)\(", code), [])


class SaidToAScreenReader(unittest.TestCase):
    def test_a_page_menu_does_not_claim_to_be_a_menu(self):
        """role="menu" promises arrow keys and menuitems; it holds plain
        buttons, and says nothing it cannot keep."""
        whole = P.SCRIPT
        menu = whole[whole.index("function pageMenu("):]
        menu = re.sub(r"/\*.*?\*/", "", menu[:menu.index("\nfunction ")], flags=re.S)
        self.assertNotRegex(menu, r'"role",\s*"menu"|role="menu"')

    def test_every_dialog_says_it_is_one(self):
        whole = P.SCRIPT
        self.assertIn('role="dialog" aria-modal="true" aria-label="Photo"', whole)
        self.assertIn('class="surebox keyscard" role="dialog"', whole)
        self.assertEqual(whole.count("function holdFocus("), 1)


class ThePhoneChrome(unittest.TestCase):
    def setUp(self):
        self.src = _src()

    def test_the_bar_along_the_bottom_is_where_you_go(self):
        """The same five places as the top of the rail, drawn by the library
        shell (`SHELLBOTTOM`), which is the only code that fills the bar."""
        from app import libraryui
        bar = re.search(r"const SHELLBOTTOM = \[(.*?)\];", libraryui.SCRIPT, re.S)
        self.assertTrue(bar, "SHELLBOTTOM is gone")
        self.assertEqual(re.findall(r'\["([a-z]+)", "[a-z-]+", "[A-Za-z]+"\]', bar.group(1)),
                         ["home", "photos", "places", "tools", "menu"])
        self.assertNotIn("function drawBottom(", self.src)

    def test_the_header_does_not_repeat_the_bottom_bar(self):
        """Home, the hamburger and Runs were all in both, so a 390px screen
        offered the same three destinations twice."""
        self.assertIn("#menu{display:none}", self.src)
        self.assertNotIn('id="viewswap"', self.src)

    def test_no_control_in_the_header_keeps_its_word_on_a_phone(self):
        """One button twice the width of the rest of the row is a row that
        looks broken."""
        rule = re.search(r"#apart button span,[^{]*\{display:none\}", self.src)
        self.assertIsNotNone(rule)
        for one in ("#reload span", "#theme span", "#signout span", "#quit span"):
            self.assertIn(one, rule.group(0), one)

    def test_a_modal_covers_the_phone_furniture_rather_than_hiding_under_it(self):
        """The folder picker goes full screen on a phone. At z-index 9 it sat
        under the fixed bottom bar (40) and the sticky header (30), so the last
        folder rows and "Use this folder" could not be tapped."""
        veil = re.search(r"\.veil\{[^}]*\}", self.src)
        self.assertIsNotNone(veil)
        z = int(re.search(r"z-index:(\d+)", veil.group(0)).group(1))
        self.assertGreater(z, 40, "the veil has to sit above #bottom")

    def test_the_sticky_bars_clear_the_nav_bar(self):
        """The explorer's act bar and the rename bar both stick to the bottom of
        their card, and the fixed nav bar is 58px of screen they know nothing
        about - so their buttons sat behind it."""
        self.assertIn(".fmact,.rnbar{bottom:calc(58px + env(safe-area-inset-bottom))}",
                      self.src)

    def test_the_automation_chip_goes_somewhere_when_it_is_tapped(self):
        """It used to open Automation only where there was a mouse; on a phone
        a tap showed a bubble and nothing else, which is a dead control."""
        hit = re.search(r'getElementById\("autobar"\)\.onclick = \(\) => \{(.*?)\};',
                        self.src, re.S)
        self.assertIsNotNone(hit)
        self.assertIn('show("automation")', hit.group(1))
        self.assertNotIn("hover: hover", hit.group(1))


class WhatTheDashboardSays(unittest.TestCase):
    def test_a_task_may_name_its_own_left_alone_list(self):
        """"Left alone" is what a task that ACTS calls what it did not touch.
        The Library never touches anything, and used it for stranded RAW
        folders."""
        self.assertIn("skipped_title", _src())

    def test_the_library_calls_them_what_they_are(self):
        import inspect
        from app.tasks import library
        self.assertIn("RAW folders with nothing to match",
                      inspect.getsource(library))


if __name__ == "__main__":
    unittest.main()
