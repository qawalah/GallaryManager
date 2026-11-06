"""The page driven in a real browser, when there is one.

Some of this app's behaviour is not reachable from Python. "Switch tab, come
back, the result is still there" is a claim about a running page, and a test
that greps the source for a function name proves only that the function exists -
which is exactly the shape the bug would take if it came back.

So these tests drive an actual browser, and **skip themselves** when one is not
installed. That is deliberate: the whole point of this app is that it runs on a
fresh Windows box and a stock python image with nothing installed, and a suite
that needs a browser is a suite that stops being run. Here they add real
coverage; on Abu's PC they quietly step aside, and the source-level checks in
test_server.py still hold the line.
"""

import http.server
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def innerw(pg) -> int:
    return pg.evaluate("() => innerWidth")


def a_browser():
    """(playwright, path to chromium) or (None, "") if there is not one here."""
    try:
        from playwright.sync_api import sync_playwright        # noqa: F401
    except Exception:                                          # noqa: BLE001
        return None, ""
    for path in (os.environ.get("PM_CHROMIUM", ""), "/opt/pw-browsers/chromium"):
        if path and os.path.exists(path):
            return sync_playwright, path
    return sync_playwright, ""          # let playwright find its own


@unittest.skipUnless(a_browser()[0], "no browser here - source checks still apply")
class InABrowser(unittest.TestCase):
    server = None
    thread = None

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="page-")
        os.environ["PM_DATA"] = os.path.join(cls.dir, "config")
        os.environ["PM_PILLOW"] = "skip"
        cls.lib = os.path.join(cls.dir, "Photos")
        cls.shoot = os.path.join(cls.lib, "2022", "Spain")
        os.makedirs(cls.shoot)
        for n in ("plain", "rated"):
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(cls.shoot, n + ".JPG"))
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(cls.shoot, n + ".RW2"))
        # a second copy of one photo, so Find duplicates has something to show
        # and the "look at the photo" test is a real check rather than a skip
        other = os.path.join(cls.lib, "2023", "Import")
        os.makedirs(other)
        shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(other, "plain.JPG"))

        # A clip, so the viewer has something to play rather than a still of it
        from core import demo as _demo
        with open(os.path.join(cls.shoot, "holiday.mp4"), "wb") as fh:
            fh.write(_demo.clip_bytes("2022:07:14 10:00:00"))
        # And one in a format this BROWSER can decode. The Chromium these tests
        # drive is the open-source build, which has no H.264 in it at all - so a
        # test that played an MP4 here would be testing the browser, not the
        # app, and would fail on a machine where the app works perfectly.
        shutil.copy(os.path.join(FIX, "tiny.webm"),
                    os.path.join(cls.shoot, "holiday.webm"))

        # And one that carries a position, so the map has a pin on it. Without
        # one the Places tests skip themselves, which is the worst outcome: a
        # screen with no coverage that looks covered.
        placed = os.path.join(cls.shoot, "placed.JPG")
        shutil.copy(os.path.join(FIX, "plain.jpg"), placed)
        try:
            from core import exifwrite as _ew
            _ew.write_gps(placed, 41.3874, 2.1686)
        except Exception:                                      # noqa: BLE001
            pass

        # A previews tree as well, so the tabs that mirror into one have
        # something to plan against - Make previews is the widest results table
        # in the app and is what the phone-layout tests read.
        cls.previews = os.path.join(cls.dir, "Previews")
        os.makedirs(cls.previews)
        # And a folder with nothing in it, which is the only honest way to test
        # what a plan that finds nothing looks like. Its own folder, because
        # every other one in here is written into by some other test.
        cls.empty = os.path.join(cls.dir, "Nothing here")
        os.makedirs(cls.empty)
        from core import settings as _s
        _s.save({"library": cls.lib, "previews": cls.previews})

        # The library the 3.0 screens read. Built here rather than left to the
        # background thread so the grid has something in it the moment a test
        # looks - these are tests about the screens, not about the indexer.
        from core import catalogue as _cat
        _cat.forget_all()
        _cat.shared().refresh([cls.lib])

        from app import server as S
        import app.tasks                                       # noqa: F401
        S.ALLOWED_ROOTS[:] = []
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}/"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        if cls.server:
            cls.server.shutdown()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def shoot_of(self, name, photos):
        """A folder of my own inside the shared library, with RAWs beside them."""
        where = os.path.join(self.lib, "made", name)
        os.makedirs(where, exist_ok=True)
        for n in photos:
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(where, n + ".JPG"))
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(where, n + ".RW2"))
        return where

    def open_tab(self, pg, name):
        """Reach a feature the way a person does.

        Some of these are a line in the sidebar and some are a tab under one,
        and which is which is a layout decision that has changed twice. A test
        that hard-codes the sidebar breaks on a rearrangement it should not care
        about - and, worse, stops testing the thing it was written for.
        """
        # 3.0: the features are behind Tools, and every one of them - tab or
        # not - has a button of its own there. Which is the point: "Cull by
        # rating" is what somebody looks for, and it used to be one click
        # inside something else.
        pg.evaluate("() => goScreen('tools')")
        pg.wait_for_selector("#cats", timeout=15000)
        hit = pg.query_selector(f'#stage button[data-t="{name}"]')
        if hit:
            hit.click()
        else:
            pg.evaluate("(n) => show(n)", name)
        pg.wait_for_timeout(300)
        # A tab whose groups start folded (Search) is a tab whose boxes are not
        # on screen until a heading is opened. A test that drives the boxes is
        # not testing the folding, so it opens them all and gets on with it -
        # `test_the_search_criteria_start_folded` is where the folding itself
        # is held.
        pg.evaluate("() => document.querySelectorAll('#form details.gfold')"
                    ".forEach(d => { d.open = true; })")

    # A phone held upright. Not a guess: an iPhone 14's CSS viewport, which is
    # the narrowest screen this has to work on and narrower than most Androids.
    PHONE = {"width": 390, "height": 844}

    def page(self, work, viewport=None, touch=False):
        maker, exe = a_browser()
        errors = []
        with maker() as pw:
            b = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
            pg = b.new_page(viewport=viewport or {"width": 1280, "height": 900},
                            has_touch=touch, is_mobile=touch)
            pg.on("pageerror", lambda e: errors.append(
                str(e) + "\n" + (getattr(e, "stack", "") or "")))
            pg.goto(self.base)
            pg.wait_for_timeout(500)
            # The library shell starts once /api/index has answered. A test that
            # drove the page before that was racing it - `show()` would open a
            # feature and the shell would then land on Home over the top of it,
            # which is a flake that looks like a missing button.
            try:
                pg.wait_for_function(
                    "() => document.body.classList.contains('shell')",
                    timeout=20000)
            except Exception:                              # noqa: BLE001
                pass
            try:
                work(pg)
            finally:
                pg.close()
                b.close()
        self.assertEqual(errors, [], f"the page threw: {errors}")

    def phone(self, work):
        return self.page(work, viewport=self.PHONE)

    def assertNoSideScroll(self, pg, where=""):
        """Nothing may be wider than the screen.

        The single most useful thing to assert about a phone layout, because it
        is the failure you cannot see in a screenshot taken at desktop width and
        the one that makes an app feel broken: a table or a path that is forty
        pixels too wide, and every page scrolls sideways for ever after."""
        wide = pg.evaluate(
            "() => [document.documentElement.scrollWidth, innerWidth]")
        self.assertLessEqual(
            wide[0], wide[1] + 1,
            f"{where or 'the page'} is {wide[0] - wide[1]}px wider than the "
            f"screen, so the whole app scrolls sideways")

    # ----------------------------------------------------------------- the tests

    def test_a_look_that_stops_getting_answers_says_so(self):
        """The progress of a run that could not be read was retried in silence
        for ever, so an app that had stopped left a bar that sat there - which
        is what "it shows a loading bar and nothing happens" was."""
        def work(pg):
            self.open_tab(pg, "videos")
            pg.route("**/api/progress*", lambda route: route.abort())
            pg.click("#go")
            pg.wait_for_function(
                "() => /not answering/.test("
                "(document.getElementById('looknote') || {}).textContent || '')",
                timeout=20000)
        self.page(work)

    def test_a_result_is_still_there_after_looking_at_another_tab(self):
        def work(pg):
            self.open_tab(pg, "library")
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            pg.wait_for_selector("#treebody tr", timeout=15000)
            was = pg.eval_on_selector_all("#treebody tr", "e => e.length")
            self.assertGreater(was, 1)

            self.open_tab(pg, "cull")
            pg.wait_for_timeout(200)
            self.assertEqual(pg.eval_on_selector("#out", "e => e.innerHTML.trim()"), "")

            self.open_tab(pg, "library")
            pg.wait_for_timeout(300)
            self.assertEqual(
                pg.eval_on_selector_all("#treebody tr", "e => e.length"), was,
                "the tree did not come back")
        self.page(work)

    def test_what_was_typed_into_a_form_survives_the_switch_too(self):
        def work(pg):
            self.open_tab(pg, "cull")
            pg.fill("#o_folder", self.shoot)
            self.open_tab(pg, "library")
            pg.wait_for_timeout(200)
            self.open_tab(pg, "cull")
            pg.wait_for_timeout(200)
            self.assertEqual(pg.input_value("#o_folder"), self.shoot)
        self.page(work)

    def test_a_status_mark_opens_that_feature_with_the_folder_filled(self):
        """The point of the Library view: you spot that a shoot is half done,
        and the next thing you want is the feature that finishes it - not to
        remember the path, switch tab and type it in."""
        def work(pg):
            self.open_tab(pg, "library")
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            pg.wait_for_selector("#treebody tr", timeout=15000)
            row = pg.query_selector_all("#treebody tr")[-1]
            path = row.query_selector("a.fgo").inner_text()
            row.query_selector_all("button.pip")[0].click()     # RAWs out -> unpair
            pg.wait_for_timeout(400)
            self.assertIn("Separate RAWs", pg.inner_text("#form h2"))
            self.assertTrue(pg.input_value("#o_folder").endswith(path))
        self.page(work)

    def test_the_folder_you_last_used_is_waiting_next_time(self):
        def work(pg):
            self.open_tab(pg, "duplicates")
            pg.fill("#o_folder", self.shoot)
            pg.click("#go")
            pg.wait_for_timeout(1500)
            pg.reload()
            pg.wait_for_timeout(700)
            self.open_tab(pg, "duplicates")
            pg.wait_for_timeout(300)
            self.assertEqual(pg.input_value("#o_folder"), self.shoot)
        self.page(work)

    def test_the_other_tree_boxes_follow_the_folder_you_pick(self):
        """Pick 2022/Spain and the RAW and previews boxes should already say
        2022/Spain in their own trees."""
        from core import settings as S
        S.save({"library": self.lib,
                "raw": os.path.join(self.dir, "Photos Raw"),
                "previews": os.path.join(self.dir, "Photos Previews")})

        def work(pg):
            pg.reload(); pg.wait_for_timeout(600)
            self.open_tab(pg, "cull")
            pg.wait_for_timeout(200)
            pg.fill("#o_folder", self.shoot)
            pg.dispatch_event("#o_folder", "input")
            pg.wait_for_timeout(200)
            self.assertTrue(pg.input_value("#o_raw").endswith(
                os.path.join("Photos Raw", "2022", "Spain")),
                pg.input_value("#o_raw"))
            self.assertTrue(pg.input_value("#o_previews").endswith(
                os.path.join("Photos Previews", "2022", "Spain")))
            self.assertIn("followed", pg.inner_text("#followed"))
        self.page(work)

    def test_and_they_have_followed_before_you_touch_anything(self):
        """The two features meet here: the folder you last used fills the box on
        its own, so the tree boxes must already have followed it by the time the
        tab is drawn. Otherwise the form opens showing a sub-folder next to two
        tree roots - which is the state that made typing them necessary."""
        from core import recent, settings as S
        S.save({"library": self.lib,
                "raw": os.path.join(self.dir, "Photos Raw"),
                "previews": os.path.join(self.dir, "Photos Previews")})
        recent.remember("cull", {"folder": self.shoot})

        def work(pg):
            pg.reload(); pg.wait_for_timeout(600)
            self.open_tab(pg, "cull")
            pg.wait_for_timeout(300)
            self.assertEqual(pg.input_value("#o_folder"), self.shoot)
            self.assertTrue(pg.input_value("#o_raw").endswith(
                os.path.join("Photos Raw", "2022", "Spain")),
                f'opened showing {pg.input_value("#o_raw")!r}')
        self.page(work)

    def test_mirroring_locks_the_destination_boxes(self):
        """Mirroring is a mode, not a path you retype. With it on the boxes show
        where things go rather than deciding it - so they cannot be edited into
        disagreeing with what will actually happen."""
        from core import settings as S
        S.save({"library": self.lib,
                "raw": os.path.join(self.dir, "Photos Raw"),
                "previews": os.path.join(self.dir, "Photos Previews")})

        def work(pg):
            pg.reload(); pg.wait_for_timeout(600)
            self.open_tab(pg, "cull")
            pg.wait_for_timeout(250)
            self.assertTrue(pg.is_checked("#o_mirror"))
            self.assertTrue(pg.is_disabled("#o_raw"))
            pg.uncheck("#o_mirror")
            pg.wait_for_timeout(150)
            self.assertFalse(pg.is_disabled("#o_raw"))
            pg.check("#o_mirror")
            pg.wait_for_timeout(150)
            self.assertTrue(pg.is_disabled("#o_raw"))
        self.page(work)

    def test_but_a_box_you_typed_in_stops_following(self):
        """A box that overwrites what you just typed is worse than one that
        never helped - once mirroring is off and the box is yours again."""
        from core import settings as S
        S.save({"library": self.lib,
                "raw": os.path.join(self.dir, "Photos Raw"),
                "previews": os.path.join(self.dir, "Photos Previews")})

        def work(pg):
            pg.reload(); pg.wait_for_timeout(600)
            self.open_tab(pg, "cull")
            pg.wait_for_timeout(200)
            pg.uncheck("#o_mirror")
            pg.wait_for_timeout(150)
            pg.fill("#o_raw", "/somewhere/else")
            pg.dispatch_event("#o_raw", "input")
            pg.fill("#o_folder", self.shoot)
            pg.dispatch_event("#o_folder", "input")
            pg.wait_for_timeout(200)
            self.assertEqual(pg.input_value("#o_raw"), "/somewhere/else")
        self.page(work)

    def test_each_row_is_ticked_off_as_it_is_done(self):
        """A bar says how far along it is. This says WHICH ones - and when four
        files out of nine hundred fail, which four is the only thing you
        actually want."""
        from core import settings as S
        S.save({"library": self.lib, "raw": os.path.join(self.dir, "Photos Raw")})

        def work(pg):
            pg.reload(); pg.wait_for_timeout(600)
            self.open_tab(pg, "unpair")
            pg.wait_for_timeout(200)
            pg.fill("#o_folder", self.lib)
            pg.dispatch_event("#o_folder", "input")
            pg.click("#go")
            pg.wait_for_selector("#doit", timeout=15000)
            rows = pg.eval_on_selector_all("#out table tr[id^=r]", "e => e.length")
            self.assertGreater(rows, 0)
            pg.click("#doit")
            pg.wait_for_selector("#again", timeout=20000)
            self.assertEqual(
                pg.eval_on_selector_all("#out tr.did, #out tr.didnt", "e => e.length"),
                rows)
        self.page(work)

    def test_a_photo_in_a_result_can_be_looked_at(self):
        """Reading a list of file names and deciding whether to cull them is a
        guess. Seeing the photo is not."""
        def work(pg):
            self.open_tab(pg, "library")
            pg.wait_for_timeout(200)
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            pg.wait_for_selector("#treebody tr", timeout=15000)
            self.open_tab(pg, "duplicates")
            pg.wait_for_timeout(200)
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            pg.wait_for_timeout(2500)
            # The rows are gathered under their pair of folders and each heading
            # starts closed, so the file has to be reached the way a person
            # reaches it.
            head = pg.query_selector("#out tr.ghead")
            if head:
                head.click()
                pg.wait_for_timeout(200)
            link = pg.query_selector("#out table a.fgo")
            self.assertIsNotNone(link, "no viewable row - the fixture should have one")
            link.click()
            pg.wait_for_selector("#viewer #vimg", timeout=5000)
            pg.wait_for_timeout(600)
            self.assertTrue(pg.eval_on_selector("#viewer #vimg", "e => e.naturalWidth > 0"),
                            "the photo did not load")
        self.page(work)

    def test_duplicates_are_gathered_under_their_two_folders_and_start_closed(self):
        """Four hundred duplicate files are not four hundred decisions - they
        are this folder against that one, over and over. A flat list makes you
        read the same judgement forty times without noticing it is one."""
        def work(pg):
            self.open_tab(pg, "duplicates")
            pg.wait_for_timeout(200)
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            pg.wait_for_selector("#out tr.ghead", timeout=15000)
            head = pg.query_selector("#out tr.ghead")
            self.assertIn(" vs ", head.inner_text())
            hidden = pg.eval_on_selector_all(
                "#out tr.g0", "e => e.filter(t => !t.hasAttribute('hidden')).length")
            self.assertEqual(hidden, 0, "the files were showing before it was opened")
            head.click()
            pg.wait_for_timeout(200)
            shown = pg.eval_on_selector_all(
                "#out tr.g0", "e => e.filter(t => !t.hasAttribute('hidden')).length")
            self.assertGreater(shown, 0, "opening the heading showed nothing")
        self.page(work)

    def test_the_heading_offers_the_other_folder_and_taking_it_changes_the_answer(self):
        """The app chooses by a rule. This is how you say it chose wrong for
        one pair of folders, without hunting for a rule that agrees with you -
        and the choice lands in a setting you can see, not a hidden override."""
        def work(pg):
            self.open_tab(pg, "duplicates")
            pg.wait_for_timeout(200)
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            pg.wait_for_selector("#out tr.ghead", timeout=15000)
            head = pg.query_selector("#out tr.ghead")
            # The folder each copy is being taken FROM, not its name: both
            # copies of a photograph have the same name, so a list of names is
            # the same list whichever folder won.
            froms = lambda: pg.eval_on_selector_all(
                "#out tr:not(.ghead) td:nth-last-child(2)",
                "e => e.map(t => t.textContent.trim())")
            was = froms()
            buttons = head.query_selector_all("button.gact")
            self.assertEqual(len(buttons), 2, "both folders should be on offer")
            buttons[1].click()          # the folder currently LOSING
            pg.wait_for_selector("#out tr.ghead", timeout=15000)
            pg.wait_for_timeout(600)
            self.assertTrue(pg.query_selector("#c_prefer .chip"),
                            "the folder was not added to the list that wins")
            self.assertNotEqual(was, froms(), "the answer did not change")
        try:
            self.page(work)
        finally:
            # The list is remembered between runs, which is the point of it -
            # so this test has to put it back, or every later run of Find
            # duplicates in this shared library opens with a folder chosen.
            from core import recent
            recent.remember_text("duplicates", "prefer", "")

    def test_history_is_somewhere_you_go_rather_than_a_step(self):
        """Somewhere you GO to look back, not a step in the loop. It has a line
        of its own under Settings and a button under Maintain, and it is not
        among the five things the rail opens on."""
        def work(pg):
            rail = pg.eval_on_selector_all("#rail .railrow[data-s]",
                                           "e => e.map(x => x.dataset.s)")
            self.assertNotIn("history", rail, "history is one of the main screens")
            b = pg.query_selector('#apart button[data-t="history"]')
            self.assertIsNotNone(b, "history is not reachable from the header")
            b.click()
            pg.wait_for_timeout(400)
            self.assertIn("History", pg.inner_text("#form h2"))
            self.assertEqual(pg.evaluate("() => SCREEN"), "feature")
        self.page(work)

    def test_everything_is_reachable_from_the_sidebar_or_the_header(self):
        """A feature that is neither a line, nor a tab under one, nor a button
        of its own is code nobody can run."""
        def work(pg):
            pg.evaluate("() => goScreen('tools')")
            pg.wait_for_selector("#cats", timeout=15000)
            seen_tools = pg.eval_on_selector_all("#stage button[data-t]",
                                                 "es => es.map(e => e.dataset.t)")
            # Settings is a group of its own now - its own page, like the other
            # groups - so that is where the settings features are.
            pg.evaluate("() => goScreen('tools', {fam: 'settings'})")
            pg.wait_for_selector("#cats", timeout=15000)
            reachable = pg.evaluate("""
                (names => {
                  const seen = new Set(names);
                  document.querySelectorAll('#stage button[data-t]')
                          .forEach(b => seen.add(b.dataset.t));
                  document.querySelectorAll('#apart button')
                          .forEach(b => seen.add(b.dataset.t));
                  /* An `inline` feature is one a RESULT opens - "Put a run
                     back" is a button on the row of the run it reverses, and
                     has no sensible place in a list of tools (which run?). The
                     row is its way in, and test_setup holds that it has one. */
                  return TASKS.filter(t => !t.inline).map(t => t.name)
                              .filter(n => !seen.has(n));
                })""", seen_tools)
            self.assertEqual(reachable, [], f"unreachable: {reachable}")
        self.page(work)

    def test_the_unread_mark_appears_and_looking_at_the_runs_clears_it(self):
        """The whole point of a background loop is that you stop thinking about
        it, and the price is not knowing whether it is working."""
        # Through the SERVER, not by poking the page: the poll overwrites what
        # the page holds every 700ms, so a test that sets it in the browser is
        # testing something that cannot survive a second.
        from app import server as srv
        srv.AUTO_RESULTS.append({"when": time.time(), "task": "develop",
                                 "title": "Send to develop",
                                 "done": 194, "failed": 0})
        try:
            def work(pg):
                pg.evaluate("""() => {
                  try{ localStorage.removeItem('pm_auto_seen'); }catch(e){}
                }""")
                pg.wait_for_selector('#rail .railrow[data-fam="maintain"] .badge',
                                     timeout=8000)
                self.open_tab(pg, "autoruns")
                pg.wait_for_timeout(1400)      # long enough for two polls
                self.assertIsNone(
                    pg.query_selector('#rail .railrow[data-fam="maintain"] .badge'),
                    "reading the runs did not clear the mark")
            self.page(work)
        finally:
            srv.AUTO_RESULTS.clear()

    def test_and_the_automation_tab_itself_does_not_clear_it(self):
        """Going there to change a setting is not the same thing as having read
        what happened."""
        from app import server as srv
        srv.AUTO_RESULTS.append({"when": time.time(), "task": "develop",
                                 "title": "Send to develop",
                                 "done": 194, "failed": 0})
        try:
            def work(pg):
                pg.evaluate("""() => {
                  try{ localStorage.removeItem('pm_auto_seen'); }catch(e){}
                }""")
                pg.wait_for_selector('#rail .railrow[data-fam="maintain"] .badge',
                                     timeout=8000)
                self.open_tab(pg, "automation")
                pg.wait_for_timeout(1400)
                self.assertTrue(
                    pg.query_selector('#rail .railrow[data-fam="maintain"] .badge'),
                    "changing a setting counted as having read what happened")
            self.page(work)
        finally:
            srv.AUTO_RESULTS.clear()

    def test_every_tool_beside_a_page_carries_its_own_icon(self):
        def work(pg):
            self.open_tab(pg, "cleanup")
            pg.wait_for_timeout(250)
            n = pg.eval_on_selector_all("#toolside .siderow svg", "e => e.length")
            rows = pg.eval_on_selector_all("#toolside .siderow", "e => e.length")
            self.assertGreater(rows, 1)
            self.assertEqual(n, rows, "a tool was listed without its icon")
        self.page(work)

    def test_a_tool_opens_on_a_page_of_its_own_with_no_tab_row(self):
        """ALI: each tool on a page dedicated to it, with no tabs between them.
        Its relatives are in the list beside it instead."""
        def work(pg):
            names = pg.evaluate("() => TASKS.map(t => t.name)")
            for name in names:
                pg.evaluate(f"() => openFeature('{name}')")
                pg.wait_for_timeout(60)
                self.assertFalse(pg.query_selector("#form .tabs"),
                                 f"{name} still draws a tab row")
                self.assertEqual(pg.evaluate("() => CURRENT.name"), name)
        self.page(work)

    def test_the_list_beside_a_tool_is_its_group_with_it_lit(self):
        def work(pg):
            self.open_tab(pg, "bydate")
            pg.wait_for_selector("#toolside .siderow", timeout=10000)
            listed = pg.eval_on_selector_all(
                "#toolside .siderow", "e => e.map(b => b.dataset.t)")
            group = pg.evaluate(
                "() => FAMILIES.find(f => f.tasks.includes('bydate'))")
            self.assertEqual(listed, group["tasks"])
            self.assertIn(group["label"],
                          pg.eval_on_selector("#toolside .sidehead", "e => e.innerText"))
            lit = pg.eval_on_selector_all(
                "#toolside .siderow.on", "e => e.map(b => b.dataset.t)")
            self.assertEqual(lit, ["bydate"])
            # and the list sits to the right of the form, not under it
            form = pg.eval_on_selector("#form", "e => e.getBoundingClientRect().toJSON()")
            side = pg.eval_on_selector("#toolside", "e => e.getBoundingClientRect().toJSON()")
            self.assertGreaterEqual(side["left"], form["right"])
            # pressing another tool in it opens that one, and lights it
            pg.click('#toolside .siderow[data-t="import-places"]')
            pg.wait_for_timeout(300)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "import-places")
            self.assertEqual(pg.eval_on_selector_all(
                "#toolside .siderow.on", "e => e.map(b => b.dataset.t)"),
                ["import-places"])
            # its heading opens the group on All tools
            pg.click("#toolside .sidehead")
            pg.wait_for_selector("#cats.one", timeout=10000)
            self.assertEqual(pg.evaluate("() => TOOLFAM"), group["key"])
        self.page(work)

    def test_the_list_follows_the_arrangement_made_on_all_tools(self):
        """Move a tool from Review to Metadata on All tools, and a Metadata
        tool's list has it while a Review tool's list does not."""
        def work(pg):
            try:
                pg.evaluate("""async () => {
                  const got = await (await fetch('api/toolgroups')).json();
                  const groups = got.groups.map(g => ({...g,
                    tasks: g.tasks.filter(t => t !== 'blur')}));
                  groups.find(g => g.key === 'metadata').tasks.push('blur');
                  await fetch('api/toolgroups', {method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({groups: groups, hidden: got.hidden || []})});
                  await toolsReload();
                }""")
                self.open_tab(pg, "geotag")
                pg.wait_for_selector("#toolside .siderow", timeout=10000)
                listed = pg.eval_on_selector_all(
                    "#toolside .siderow", "e => e.map(b => b.dataset.t)")
                self.assertIn("blur", listed)
                self.open_tab(pg, "cull")
                pg.wait_for_timeout(300)
                listed = pg.eval_on_selector_all(
                    "#toolside .siderow", "e => e.map(b => b.dataset.t)")
                self.assertNotIn("blur", listed)
                self.assertIn("thin", listed)
                self.open_tab(pg, "blur")
                pg.wait_for_timeout(300)
                self.assertIn("Metadata", pg.eval_on_selector(
                    "#toolside .sidehead", "e => e.innerText"))
            finally:
                pg.evaluate("""async () => { await fetch('api/toolgroups', {
                  method: 'POST', headers: {'Content-Type': 'application/json'},
                  body: JSON.stringify({reset: true})}); await toolsReload(); }""")
        self.page(work)

    def test_what_was_only_a_tab_of_history_is_still_beside_it(self):
        """Put a run back and Clear the history are in no group. They were
        tabs of History, so they are listed under it on History's page."""
        def work(pg):
            pg.evaluate("() => openFeature('history')")
            pg.wait_for_selector("#toolside .siderow", timeout=10000)
            listed = pg.eval_on_selector_all(
                "#toolside .siderow", "e => e.map(b => b.dataset.t)")
            for name in ("history", "undo", "forget"):
                self.assertIn(name, listed)
            pg.click('#toolside .siderow[data-t="forget"]')
            pg.wait_for_timeout(300)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "forget")
        self.page(work)

    def test_the_new_tabs_draw_without_the_page_throwing(self):
        """Every tab is drawn from its options by one piece of code, so a task
        with a shape nothing else has - five folded groups of five, a list of
        choices worked out at run time - is exactly where that code breaks. The
        page() helper fails the test on any JS error."""
        def work(pg):
            for tab in ("label", "automation", "cleanup", "autoruns",
                        "tidy", "remirror_previews", "remirror_video"):
                self.open_tab(pg, tab)
                pg.wait_for_timeout(300)
                self.assertTrue(pg.query_selector("#form"),
                                f"{tab} drew no form")
            self.open_tab(pg, "setup")
            pg.wait_for_timeout(300)
            self.assertTrue(pg.query_selector('text=Colour meanings'),
                            "the colour meanings tab is not under Setup")
        self.page(work)

    def test_the_automation_tab_lists_its_steps_in_order(self):
        def work(pg):
            self.open_tab(pg, "automation")
            pg.wait_for_timeout(300)
            pg.click("#go")
            pg.wait_for_selector("#out table tr", timeout=15000)
            names = pg.eval_on_selector_all(
                "#out table tr td:first-child",
                "e => e.map(t => t.textContent.trim())")
            self.assertTrue(any(n.startswith("1.") for n in names), names)
            self.assertTrue(any(n.startswith("3.") for n in names), names)
        self.page(work)

    def test_the_flow_editor_builds_a_chain_from_a_dropdown(self):
        """The thing that was asked for: a feature, then a feature, then a
        feature, each with its own settings."""
        def work(pg):
            self.open_tab(pg, "flows")
            pg.wait_for_selector(".stepcard", timeout=15000)
            before = pg.eval_on_selector_all(".stepcard", "e => e.length")
            self.assertGreaterEqual(before, 3, "the developing loop is not there")
            # every feature that can be a step is on offer
            count = pg.eval_on_selector("#pick0", "e => e.options.length")
            self.assertGreater(count, 10, "the dropdown offers almost nothing")
            pg.select_option("#pick0", "previews")
            pg.click("text=Add this step")
            pg.wait_for_timeout(200)
            self.assertEqual(
                pg.eval_on_selector_all(".stepcard", "e => e.length"),
                before + 1)
            # and a step added from the dropdown starts as report-only
            said = pg.eval_on_selector_all(
                ".stepcard select", "e => e.map(x => x.value)")
            self.assertEqual(said[-1], "report",
                             "a step added from the dropdown starts as a doer")
        self.page(work)

    def test_a_step_can_be_moved_because_the_order_is_the_chain(self):
        def work(pg):
            self.open_tab(pg, "flows")
            pg.wait_for_selector(".stepcard", timeout=15000)
            first = pg.eval_on_selector(".steptitle", "e => e.textContent")
            pg.click('.stepcard >> nth=1 >> button[title="Earlier in the chain"]')
            pg.wait_for_timeout(200)
            self.assertNotEqual(
                pg.eval_on_selector(".steptitle", "e => e.textContent"), first,
                "moving a step up did nothing")
        self.page(work)

    def test_each_step_carries_the_settings_of_its_own_feature(self):
        """And says where each value came from, which is the whole point: the
        fault this replaces was a threshold that was not the threshold used."""
        def work(pg):
            self.open_tab(pg, "flows")
            pg.wait_for_selector(".stepcard", timeout=15000)
            pg.click('.stepcard >> nth=1 >> text=Settings')
            pg.wait_for_selector(".stepopt", timeout=5000)
            said = pg.eval_on_selector_all(
                ".stepopt .fromsetup", "e => e.map(x => x.textContent)")
            self.assertTrue(said, "no step settings were drawn")
            self.assertTrue(any("Setup" in x or "default" in x for x in said),
                            said[:4])
        self.page(work)

    def test_a_running_flow_locks_its_steps_and_says_why(self):
        """A form you can edit while the loop is firing invites you to wonder
        which version just ran."""
        def work(pg):
            self.open_tab(pg, "flows")
            pg.wait_for_selector(".stepcard", timeout=15000)
            self.assertFalse(
                pg.eval_on_selector(".stepcard select", "e => e.disabled"),
                "the steps are locked while the flow is off")
            pg.check(".card input[type=checkbox]")      # run this flow by itself
            # which asks first, now - and says yes here
            pg.wait_for_selector(".sure", timeout=5000)
            pg.click('.sure button[data-a="1"]')
            pg.wait_for_timeout(250)
            self.assertTrue(
                pg.eval_on_selector(".stepcard select", "e => e.disabled"),
                "a step can still be changed while the flow is running")
            self.assertTrue(pg.query_selector("#flowlocked0"),
                            "nothing on the page says why the form went dead")
        self.page(work)

    def test_the_automation_tab_draws_the_flow_as_a_chain(self):
        """A list of steps with a summary above it reads as a SET. The one
        property of a flow that is easy to get wrong is its ORDER, and arrows
        are what say it."""
        def work(pg):
            self.open_tab(pg, "automation")
            pg.wait_for_selector("#flowsum .blk", timeout=15000)
            blocks = pg.eval_on_selector_all("#flowsum .blk", "e => e.length")
            self.assertGreaterEqual(blocks, 3)
            self.assertEqual(
                pg.eval_on_selector_all("#flowsum .blkarrow", "e => e.length"),
                blocks - 1, "the blocks are not joined into a chain")
            # each block says what it watches and whether it runs
            said = pg.eval_on_selector_all("#flowsum .blkwatch",
                                           "e => e.map(x => x.textContent)")
            self.assertTrue(any("previews" in x for x in said), said)
        self.page(work)

    def test_and_shows_whether_that_flow_is_running_without_relying_on_colour(self):
        def work(pg):
            self.open_tab(pg, "automation")
            pg.wait_for_selector("#flowsum .flight", timeout=15000)
            word = pg.eval_on_selector("#flowsum .flight", "e => e.textContent")
            self.assertIn(word.strip(), ("On", "Off", "Running", "DSM runs it"))
        self.page(work)

    def test_the_flows_tab_has_a_run_button_per_flow(self):
        def work(pg):
            self.open_tab(pg, "flows")
            pg.wait_for_selector(".chain", timeout=15000)
            self.assertTrue(pg.query_selector('button[title="Run one pass of '
                                              'this flow now"]'))
        self.page(work)

    def test_every_step_opens_and_closes_at_once(self):
        """Opening six steps one at a time to compare a threshold across them is
        the chore that makes people stop checking."""
        def work(pg):
            self.open_tab(pg, "flows")
            pg.wait_for_selector(".stepcard", timeout=15000)
            self.assertEqual(
                pg.eval_on_selector_all(".stepopts", "e => e.length"), 0)
            pg.click("text=Expand all")
            pg.wait_for_selector(".stepopts", timeout=5000)
            opened = pg.eval_on_selector_all(".stepopts", "e => e.length")
            self.assertGreaterEqual(opened, 3)
            pg.click("text=Collapse all")
            pg.wait_for_timeout(200)
            self.assertEqual(
                pg.eval_on_selector_all(".stepopts", "e => e.length"), 0)
        self.page(work)

    def test_a_flow_can_be_told_to_leave_a_folder_alone(self):
        def work(pg):
            self.open_tab(pg, "flows")
            pg.wait_for_selector(".chain", timeout=15000)
            self.assertTrue(pg.query_selector("text=Leave a folder out"),
                            "no way to exclude a folder from this flow")
            pg.evaluate("""() => { FLOWS[0].exclude = ['/tmp/somewhere'];
                                   drawFlows(); }""")
            pg.wait_for_timeout(200)
            self.assertTrue(pg.query_selector("#fex0 .chip"))
            pg.click("#fex0 .chip button")
            pg.wait_for_timeout(200)
            self.assertIsNone(pg.query_selector("#fex0 .chip"))
        self.page(work)

    def test_the_top_bar_says_the_state_in_a_word_not_only_a_colour(self):
        """A hue difference is no answer to "is this thing working" on a dim
        screen, in the dark theme, or for anyone who reads red and green alike."""
        def work(pg):
            pg.wait_for_selector("#autobar b", timeout=15000)
            word = pg.eval_on_selector("#autobar b", "e => e.textContent")
            self.assertIn(word.strip(), ("On", "Off", "Running", "?"))
            # and the sentence is in the bubble, not in the bar
            self.assertTrue(pg.eval_on_selector("#autobar", "e => e.dataset.tip"))
        self.page(work)

    # ------------------------------------------------------- held upright

    def test_the_home_screen_answers_the_three_phone_questions(self):
        """What you open this app for on a phone is not what you open it for at
        a desk: is it running, did it do anything, can the thing it keeps
        mentioning go now."""
        def work(pg):
            pg.wait_for_selector("#stage .bigtile", timeout=20000)
            said = pg.text_content("#stage")
            self.assertIn("Photos", said)
            self.assertIn("With a location", said)
            # and it says how old the numbers are, which is the whole bargain:
            # they were counted in the background, not when you arrived
            self.assertRegex(said, r"Counted .*from the index")
            self.assertNoSideScroll(pg, "the home screen")
        self.phone(work)

    def test_and_the_full_app_is_one_tap_away_and_stays_where_you_put_it(self):
        """On a phone that switch is the bar along the bottom, not a second
        copy of it in the header - Home was offered twice on a 390px screen."""
        def work(pg):
            pg.wait_for_selector("#stage .bigtile", timeout=20000)
            self.assertFalse(pg.eval_on_selector_all("header button",
                "e => e.some(b => b.offsetParent && /Home/.test(b.textContent))"),
                "the header still repeats the bottom bar's Home")
            pg.click('#bottom button[data-b="photos"]')
            pg.wait_for_timeout(500)
            self.assertEqual(pg.evaluate("() => SCREEN"), "photos")
            self.assertEqual(
                pg.evaluate("() => localStorage.getItem('pm-screen')"), "photos")
            pg.click('#bottom button[data-b="home"]')
            pg.wait_for_timeout(500)
            self.assertEqual(pg.evaluate("() => SCREEN"), "home")
        self.phone(work)

    def test_but_going_to_look_at_something_is_not_that_decision(self):
        """Opening History from Home is not a decision to stop using Home."""
        def work(pg):
            pg.wait_for_selector("#stage .bigtile", timeout=20000)
            pg.evaluate("() => openFeature('history')")
            pg.wait_for_timeout(400)
            self.assertEqual(pg.evaluate("() => SCREEN"), "feature")
            self.assertEqual(
                pg.evaluate("() => localStorage.getItem('pm-screen')"), "home",
                "going to look at something changed where the app opens")
        self.phone(work)

    def test_the_sidebar_is_a_drawer_on_a_phone(self):
        """Thirteen features in a horizontal scroller is a list you have to
        swipe through to read and cannot see your place in."""
        def work(pg):
            pg.wait_for_selector("#rail .railrow", timeout=20000)
            off = pg.eval_on_selector("#rail", "e => e.getBoundingClientRect().right")
            self.assertLessEqual(off, 1, "the drawer is on screen already")
            pg.click('#bottom button[data-b="menu"]')
            pg.wait_for_timeout(350)
            self.assertGreater(pg.eval_on_selector(
                "#rail", "e => e.getBoundingClientRect().right"), 100)
            # and picking somewhere closes it, rather than covering what you opened
            pg.click('#rail .railrow[data-s="albums"]')
            pg.wait_for_timeout(400)
            self.assertEqual(pg.evaluate("() => SCREEN"), "albums")
            self.assertLessEqual(pg.eval_on_selector(
                "#rail", "e => e.getBoundingClientRect().right"), 1)
        self.phone(work)

    def test_the_drawer_carries_what_the_header_has_no_room_for(self):
        def work(pg):
            pg.wait_for_selector("#rail .railrow", timeout=20000)
            pg.click('#bottom button[data-b="menu"]')
            pg.wait_for_timeout(300)
            said = pg.eval_on_selector("#railfoot", "e => e.textContent")
            self.assertTrue(said.strip(), "the drawer's foot says nothing")
            # what it has no room for in the header: how the index is getting on
            self.assertRegex(said, r"indexed|Reading|library")
        self.phone(work)

    def test_the_rail_carries_the_notice_switch_and_nothing_that_went(self):
        """The 2.x sidebar went, and with it three things moved to the rail.
        Two of those went in turn, by request, in 3.12.0: the features you
        opened lately, and Install as an app. The notice switch stays."""
        def work(pg):
            pg.wait_for_selector("#rail .railrow", timeout=20000)
            self.assertIsNone(pg.query_selector("#nav"))
            self.assertIsNone(pg.query_selector("#home"))
            for name in ("cull", "geotag", "setup"):
                pg.evaluate(f"() => openFeature('{name}')")
                pg.wait_for_timeout(200)
            self.assertNotIn("Lately", pg.text_content("#rail"))
            self.assertEqual(pg.eval_on_selector_all(
                "#rail .railrow.lately", "e => e.length"), 0)
            self.assertIsNone(pg.evaluate("() => localStorage.getItem('pm-recent')"),
                              "something still notes what was opened")
            self.assertTrue(pg.query_selector("#railfoot #noticeon"))
            self.assertIsNone(pg.query_selector("#installapp"))
            self.assertNotIn("Install as an app", pg.text_content("#rail"))
        self.page(work)
        self.page(work)

    def test_every_feature_opens_on_a_phone_without_scrolling_sideways(self):
        """The failure you cannot see in a screenshot taken at desktop width,
        and the one that makes an app feel broken."""
        def work(pg):
            pg.wait_for_selector("#rail .railrow", timeout=20000)
            names = pg.evaluate(
                "() => TASKS.filter(t => !t.parent && !t.hidden).map(t => t.name)")
            self.assertGreater(len(names), 8)
            for name in names:
                pg.evaluate("(n) => show(n)", name)
                pg.wait_for_timeout(120)
                self.assertNoSideScroll(pg, name)
        self.phone(work)

    def test_a_wide_results_table_becomes_one_card_per_row(self):
        """Seven columns in 390 pixels is four characters each.

        Make previews rather than the Library, because its table is genuinely
        seven columns wide with rows for every photograph - the Library draws a
        folder tree, which is a different shape and would make this a skip."""
        def work(pg):
            pg.evaluate("() => show('previews')")
            pg.wait_for_timeout(250)
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            pg.wait_for_selector("#out table.stack tr", timeout=25000)
            heads = pg.eval_on_selector_all(
                "#out table.stack thead, #out table.stack tr:first-child",
                "e => e.map(x => getComputedStyle(x).display)")
            self.assertTrue(heads, "no table was drawn at all")
            said = pg.eval_on_selector(
                "#out table.stack td:nth-child(2)",
                "e => getComputedStyle(e, '::before').content")
            self.assertNotIn(said, ("none", '""'),
                             "the column name is not shown beside the value")
            # and a row really is a block rather than a table row
            self.assertEqual(pg.eval_on_selector(
                "#out table.stack tbody tr, #out table.stack tr:nth-child(2)",
                "e => getComputedStyle(e).display"), "block")
            self.assertNoSideScroll(pg, "a results table")
        self.phone(work)

    def test_and_stays_a_plain_table_on_a_wide_screen(self):
        """The stacking is for a phone. A desktop that lost its columns would
        have gained nothing and lost the thing tables are for."""
        def work(pg):
            self.open_tab(pg, "previews")
            pg.wait_for_timeout(250)
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            pg.wait_for_selector("#out table tr", timeout=25000)
            self.assertEqual(pg.eval_on_selector(
                "#out table tr:nth-child(2)",
                "e => getComputedStyle(e).display"), "table-row")
        self.page(work)

    def test_the_folder_picker_fills_a_phone_screen(self):
        """A dialog sized for a mouse is a dialog you cannot hit."""
        def work(pg):
            pg.evaluate("() => show('previews')")
            pg.wait_for_timeout(250)
            pg.click("#form .withbtn button:has-text('Browse') >> nth=0")
            pg.wait_for_selector(".pick", timeout=10000)
            box = pg.eval_on_selector(
                ".pick", "e => { const r = e.getBoundingClientRect();"
                         " return [r.width, r.height]; }")
            self.assertGreaterEqual(box[0], innerw(pg) - 2)
            self.assertGreater(box[1], 600)
        self.phone(work)

    def test_help_is_a_bubble_that_goes_away(self):
        """It used to expand in place. Most options here have two sentences
        explaining a trap, so a form with a dozen of them opened was four
        screens of prose with the controls scattered through it."""
        def work(pg):
            self.open_tab(pg, "geotag")
            pg.wait_for_selector(".info", timeout=15000)
            tall = pg.evaluate("() => document.body.scrollHeight")
            pg.hover(".info >> nth=0")
            pg.wait_for_selector("#tip.on", timeout=5000)
            said = pg.eval_on_selector("#tip", "e => e.textContent")
            self.assertTrue(said.strip())
            # the form did not grow: that is the whole point
            self.assertEqual(pg.evaluate("() => document.body.scrollHeight"), tall)
            pg.hover("#form h2")
            pg.wait_for_timeout(250)
            self.assertFalse(pg.query_selector("#tip.on"),
                             "the bubble stayed up after the mouse left")
        self.page(work)

    def test_and_a_tap_opens_it_on_a_phone(self):
        """A touch fires pointerout immediately, so a bubble that obeyed it
        would open and shut in one tap - which reads as a dead button."""
        def work(pg):
            pg.evaluate("() => show('geotag')")
            pg.wait_for_selector(".info", timeout=15000)
            pg.tap(".info >> nth=0")
            pg.wait_for_selector("#tip.on", timeout=5000)
            self.assertNoSideScroll(pg, "an open help bubble")
            pg.tap("#form h2")
            pg.wait_for_timeout(250)
            self.assertFalse(pg.query_selector("#tip.on"))
        self.page(work, viewport=self.PHONE, touch=True)

    def test_a_tools_group_is_on_the_page_under_it_on_a_phone(self):
        """Abu: jumping to a feature and then having to go back to the menu for
        each of its parts is annoying. So the rest of its group is on the
        page, under the form on a phone, and in the drawer."""
        def work(pg):
            pg.evaluate("() => show('automation')")
            pg.wait_for_timeout(300)
            self.assertEqual(pg.eval_on_selector(
                "#toolside", "e => getComputedStyle(e).display"), "block")
            form = pg.eval_on_selector("#form", "e => e.getBoundingClientRect().toJSON()")
            side = pg.eval_on_selector("#toolside", "e => e.getBoundingClientRect().toJSON()")
            self.assertGreaterEqual(side["top"], form["bottom"])
            self.assertNoSideScroll(pg, "the list of the group's tools")
            said = pg.eval_on_selector_all(
                "#toolside .siderow span", "e => e.map(x => x.textContent.trim())")
            self.assertTrue(any("Flows" in k for k in said), said)
            # and every one of those parts is a button of its own under Tools,
            # which is where somebody looks for "Flows" rather than for the
            # feature it happens to live inside
            pg.evaluate("() => goScreen('tools')")
            pg.wait_for_timeout(300)
            self.assertTrue(pg.query_selector('#stage button[data-t="flows"]'))
        self.phone(work)

    def test_but_sits_beside_the_form_on_a_wide_screen(self):
        def work(pg):
            self.open_tab(pg, "automation")
            pg.wait_for_timeout(300)
            form = pg.eval_on_selector("#form", "e => e.getBoundingClientRect().toJSON()")
            side = pg.eval_on_selector("#toolside", "e => e.getBoundingClientRect().toJSON()")
            self.assertGreaterEqual(side["left"], form["right"])
            self.assertLess(side["top"], form["bottom"])
        self.page(work)

    def test_the_header_is_one_row(self):
        """It wrapped whenever the allowed-folders line was long, which made the
        header a different height on different machines and pushed the whole
        app down."""
        def work(pg):
            pg.wait_for_selector("#reload", timeout=15000)
            # Compared on the vertical CENTRE, not the top: things of different
            # heights sitting on one centred row have different tops and are
            # perfectly aligned. Two centres means two rows.
            mids = pg.evaluate(
                "() => [...document.querySelectorAll('header > *')]"
                ".filter(x => x.offsetParent)"
                ".map(x => { const r = x.getBoundingClientRect();"
                " return Math.round((r.top + r.bottom) / 2); })")
            self.assertGreater(len(mids), 4)
            self.assertEqual(len(set(mids)), 1,
                             f"the header wrapped onto {len(set(mids))} rows")
        self.page(work)

    def test_and_its_buttons_line_up(self):
        """History sat a pixel or two off its neighbours, because every control
        in the header had grown its own padding, font size and radius."""
        def work(pg):
            pg.wait_for_selector("#reload", timeout=15000)
            boxes = pg.evaluate(
                "() => [...document.querySelectorAll('header button')]"
                ".filter(x => x.offsetParent)"
                ".map(x => { const r = x.getBoundingClientRect();"
                " return [Math.round(r.top), Math.round(r.height)]; })")
            self.assertGreater(len(boxes), 3)
            self.assertEqual(len({tuple(b) for b in boxes}), 1,
                             f"header controls differ in top/height: {boxes}")
        self.page(work)

    def test_a_settings_tab_has_a_save_button_and_it_saves(self):
        """The complaint that started this: Setup did save, but only as a side
        effect of a button promising to do nothing."""
        def work(pg):
            self.open_tab(pg, "setup")
            pg.wait_for_timeout(300)
            self.assertTrue(pg.query_selector("#save"), "Setup has no Save")
            self.assertFalse(pg.query_selector("#go"),
                             "a settings tab still offers to preview itself")
            pg.fill("#o_library", self.lib)
            pg.click("#save")
            pg.wait_for_function(
                "() => (document.getElementById('saidsaved')||{}).textContent"
                " === 'Saved.'", timeout=15000)
            # and the value reaches the other forms, which is the whole point
            got = pg.evaluate(
                "(TASKS.find(t => t.name === 'ratings').options"
                ".find(o => o.name === 'library') || {}).default")
            self.assertEqual(got, self.lib)
        self.page(work)

    def library_as_it_is(self):
        """The library now, and how to put it and the index back afterwards.

        Other tests in this class move the library about (Setup is a form like
        any other), so these start from whatever it is rather than assuming,
        and leave it exactly as they found it."""
        from core import settings as _s, catalogue as _cat
        was = str(_s.load()["library"] or "")
        roots = list(_cat.shared().roots) or [self.lib]

        def back():
            _s.save({"library": was})
            _cat.shared().refresh(roots)
        return was, back

    def test_a_form_already_opened_follows_a_new_library(self):
        """ALI's bug: change the library in Setup, go back to Search, and it is
        still searching the old one - because a tab you had already opened
        came back with the boxes it was left with."""
        moved = os.path.join(self.dir, "Elsewhere")
        os.makedirs(moved, exist_ok=True)

        def box(pg, task, name):
            self.open_tab(pg, task)
            return pg.input_value("#o_" + name)

        was, back = self.library_as_it_is()

        def work(pg):
            # Setup's library, or a folder of it a run here remembered.
            self.assertTrue(box(pg, "search", "folders").startswith(was))
            self.assertTrue(box(pg, "cull", "folder").startswith(was))
            self.open_tab(pg, "setup")
            pg.fill("#o_library", moved)
            pg.click("#save")
            pg.wait_for_function(
                "() => (document.getElementById('saidsaved')||{}).textContent"
                " === 'Saved.'", timeout=15000)
            pg.wait_for_timeout(300)
            self.assertEqual(box(pg, "search", "folders"), moved)
            self.assertEqual(box(pg, "cull", "folder"), moved)
        try:
            self.page(work)
        finally:
            back()

    def test_a_change_made_elsewhere_reaches_the_open_form(self):
        """The sample library borrowing the trees, the command line, another
        browser: none of them press this page's Save. And a folder typed into a
        form on purpose is the person's, and stays."""
        from core import settings as _s
        moved = os.path.join(self.dir, "Elsewhere")
        os.makedirs(moved, exist_ok=True)
        was, back = self.library_as_it_is()

        def work(pg):
            self.open_tab(pg, "search")
            # typed (the box behind the folder list): stays
            pg.evaluate("(p) => { const el = document.getElementById('o_folders');"
                        " el.value = p; el.dispatchEvent(new Event('input')); }",
                        self.empty)
            self.open_tab(pg, "cull")
            self.assertTrue(pg.input_value("#o_folder").startswith(was))
            _s.save({"library": moved})
            pg.wait_for_function(
                "(want) => (document.getElementById('o_folder')||{}).value"
                " === want", arg=moved, timeout=15000)
            self.open_tab(pg, "search")
            self.assertEqual(pg.input_value("#o_folders"), self.empty)
        try:
            self.page(work)
        finally:
            back()

    def test_the_top_of_every_page_says_whether_it_is_running(self):
        def work(pg):
            pg.wait_for_selector("#autobar", timeout=15000)
            words = pg.eval_on_selector("#autobar", "e => e.textContent")
            self.assertTrue(words.strip(), "the bar says nothing at all")
        self.page(work)

    def test_the_left_hand_tabs_stay_put_when_you_scroll(self):
        def work(pg):
            stuck = pg.eval_on_selector(
                "#rail", "e => getComputedStyle(e).position")
            self.assertEqual(stuck, "sticky")
        self.page(work)

    def test_the_tree_opens_and_closes_by_depth(self):
        """A library is years over shoots. "Show me the years" and "show me
        everything" are the two things anybody wants, and clicking twelve twists
        to get either is why nobody uses a tree view twice."""
        def work(pg):
            self.open_tab(pg, "library")
            pg.wait_for_timeout(200)
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            pg.wait_for_selector("#treebody tr", timeout=15000)
            everything = pg.eval_on_selector_all("#treebody tr", "e => e.length")
            self.assertGreater(everything, 2)

            pg.click('.twists button[title="Collapse everything"]')          # collapse everything
            pg.wait_for_timeout(200)
            self.assertEqual(pg.eval_on_selector_all("#treebody tr", "e => e.length"), 1)

            pg.click('.twists button[title="One level more"]')          # one level more
            pg.wait_for_timeout(200)
            one = pg.eval_on_selector_all("#treebody tr", "e => e.length")
            self.assertGreater(one, 1)
            self.assertLess(one, everything)

            pg.click('.twists button[title="Expand everything"]')          # everything again
            pg.wait_for_timeout(200)
            self.assertEqual(pg.eval_on_selector_all("#treebody tr", "e => e.length"),
                             everything)
        self.page(work)

    def test_folders_are_added_to_the_exclusion_list_by_picking_them(self):
        def work(pg):
            self.open_tab(pg, "library")
            pg.wait_for_timeout(250)
            pg.click("text=Add a folder")
            pg.wait_for_selector(".pick li button", timeout=5000)
            pg.wait_for_timeout(300)

            def go(name, seconds=6):
                """Click the folder called `name`, waiting for it to turn up.

                Waiting for the NAME rather than for a fixed number of
                milliseconds. Each click fetches a folder listing over HTTP, and
                a listing of a busy /tmp is not always back inside 350ms - which
                made this test fail about one run in fifteen, on a machine that
                happened to be doing something else. Polling for the thing we are
                waiting for cannot be too slow or too fast.
                """
                until = time.time() + seconds
                opened = False
                while time.time() < until:
                    for el in pg.query_selector_all(".pick li button"):
                        if el.inner_text().strip().split("\n")[-1].strip() == name:
                            el.click()
                            return True
                    # it may be behind the folded "system folders" group - which
                    # is exactly why they are folded rather than hidden
                    fold = pg.query_selector(".pick .sysfold summary")
                    if fold and not opened:
                        fold.click()
                        opened = True
                    pg.wait_for_timeout(100)
                return False

            # the picker opens on the shortcut list, so start at the top of the
            # machine and walk down to the library
            self.assertTrue(go(os.sep), "no way in to the top of the machine")
            for step in self.lib.strip(os.sep).split(os.sep):
                self.assertTrue(go(step, 1) or go(os.sep + step, 6) or go(step, 6),
                                f"could not reach {step} in the picker")
            self.assertTrue(go("2022"))
            pg.click("text=Use this folder")
            pg.wait_for_timeout(300)
            chips = pg.eval_on_selector_all("#c_exclude .chip span:nth-child(2)",
                                            "e => e.map(x => x.textContent)")
            self.assertEqual(len(chips), 1)
            self.assertTrue(chips[0].endswith(os.path.join("Photos", "2022")), chips)
        self.page(work)

    def test_a_previews_folder_is_read_as_the_folder_it_mirrors(self):
        """Paste a path from the previews tree into a task that wants originals
        and it used to refuse: "not inside the library". True, unhelpful, and
        the app knew perfectly well which folder was meant."""
        from core import settings as S
        prev = os.path.join(self.dir, "Photos Previews")
        S.save({"library": self.lib, "raw": os.path.join(self.dir, "Photos Raw"),
                "previews": prev})

        def work(pg):
            pg.reload(); pg.wait_for_timeout(600)
            self.open_tab(pg, "previews")
            pg.wait_for_timeout(250)
            pg.fill("#o_folder", os.path.join(prev, "2022", "Spain"))
            pg.dispatch_event("#o_folder", "input")
            pg.wait_for_timeout(250)
            self.assertEqual(pg.input_value("#o_folder"),
                             os.path.join(self.lib, "2022", "Spain"))
            self.assertIn("previews tree", pg.inner_text("#followed"))
            # and the previews box now points where those previews go
            self.assertTrue(pg.input_value("#o_previews").endswith(
                os.path.join("Photos Previews", "2022", "Spain")),
                pg.input_value("#o_previews"))
        self.page(work)

    def test_jumping_from_the_library_fills_the_other_trees_too(self):
        """Even after typing in one of them by hand on a previous folder: a new
        folder is a fresh start, and a box left pointing at last week's shoot is
        the shape of every mirroring bug this app has had."""
        from core import settings as S
        S.save({"library": self.lib, "raw": os.path.join(self.dir, "Photos Raw"),
                "previews": os.path.join(self.dir, "Photos Previews")})

        def work(pg):
            pg.reload(); pg.wait_for_timeout(600)
            self.open_tab(pg, "previews")
            pg.wait_for_timeout(250)
            # mirroring greys the destination boxes, so this is the case where
            # somebody turned it off and pointed one run somewhere else
            pg.uncheck("#o_mirror")
            pg.wait_for_timeout(150)
            pg.fill("#o_previews", os.path.join(self.dir, "somewhere else"))
            pg.dispatch_event("#o_previews", "input")
            self.open_tab(pg, "library")
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            pg.wait_for_selector("#treebody tr", timeout=15000)
            row = pg.query_selector_all("#treebody tr")[-1]
            path = row.query_selector("a.fgo").inner_text()
            pips = row.query_selector_all("button.pip")
            pips[len(pips) - 1].click()          # previews mark -> Make previews
            pg.wait_for_timeout(400)
            self.assertTrue(pg.input_value("#o_folder").endswith(path))
            self.assertTrue(pg.input_value("#o_previews").endswith(path),
                            pg.input_value("#o_previews"))
        self.page(work)

    def test_the_result_table_sorts_by_a_column_you_click(self):
        """Nine hundred rows in whatever order the disk gave them up, and the one
        you want is somewhere in the middle."""
        # Its own shoot, made here. The class shares one library between tests
        # and some of them MOVE files in it, so a test that needs rows has to
        # bring its own or it passes and fails depending on what ran before it.
        mine = self.shoot_of("sorting", ("plain", "rated", "aeb1"))
        from core import settings as S
        S.save({"library": self.lib, "raw": os.path.join(self.dir, "Photos Raw"),
                "previews": os.path.join(self.dir, "Photos Previews")})

        def work(pg):
            pg.reload(); pg.wait_for_timeout(500)
            self.open_tab(pg, "unpair")
            pg.wait_for_timeout(250)
            pg.fill("#o_folder", mine)
            pg.click("#go")
            pg.wait_for_selector("table th.sortable", timeout=15000)
            names = lambda: pg.eval_on_selector_all(
                "table tr td:first-child", "e => e.map(x => x.innerText.trim())")
            first = names()
            self.assertGreater(len(first), 1)
            pg.click("table th.sortable >> nth=0")
            pg.wait_for_timeout(200)
            up = names()
            self.assertEqual(sorted(first, key=str.lower), up)
            pg.click("table th.sortable >> nth=0")      # again: the other way
            pg.wait_for_timeout(200)
            self.assertEqual(list(reversed(up)), names())
        self.page(work)

    def test_the_folder_every_row_shares_is_said_once(self):
        """Every row repeated the same long shared prefix and pushed the part
        that differed - the only part worth reading - off to the right."""
        # Its own shoot, made here. The class shares one library between tests
        # and some of them MOVE files in it, so a test that needs rows has to
        # bring its own or it passes and fails depending on what ran before it.
        mine = self.shoot_of("paths", ("plain", "rated", "aeb1"))
        from core import settings as S
        S.save({"library": self.lib, "raw": os.path.join(self.dir, "Photos Raw"),
                "previews": os.path.join(self.dir, "Photos Previews")})

        def work(pg):
            pg.reload(); pg.wait_for_timeout(500)
            self.open_tab(pg, "unpair")
            pg.wait_for_timeout(250)
            pg.fill("#o_folder", mine)
            pg.click("#go")
            pg.wait_for_selector(".rootline", timeout=15000)
            said = pg.inner_text(".rootline")
            self.assertIn(self.dir, said)
            cells = pg.eval_on_selector_all(
                "table tr td:last-child", "e => e.map(x => x.innerText.trim())")
            self.assertTrue(cells, "no rows")
            for c in cells:
                self.assertNotIn(self.dir, c, "the shared folder is repeated")
        self.page(work)

    def test_one_level_less_closes_a_whole_level(self):
        """And a button that would do nothing is disabled rather than pressed
        twice and called broken."""
        deep = os.path.join(self.lib, "2023", "Trip", "Day 1", "Morning")
        os.makedirs(deep, exist_ok=True)
        shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(deep, "deep.JPG"))

        def work(pg):
            self.open_tab(pg, "library")
            pg.wait_for_timeout(200)
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            pg.wait_for_selector("#treebody tr", timeout=15000)
            indents = lambda: pg.eval_on_selector_all(
                "#treebody tr td:first-child",
                "e => e.map(x => parseInt(x.style.paddingLeft))")

            # one click should close a whole LEVEL, everywhere - not just the
            # single branch that happens to run deepest
            before = indents()
            deepest = max(before)
            self.assertGreater(before.count(deepest), 0)
            pg.click('.twists button[title="One level less"]')          # one level less
            pg.wait_for_timeout(250)
            after = indents()
            self.assertNotIn(deepest, after,
                             f"rows are still at the deepest level: {after}")
            self.assertLess(max(after), deepest)

            # everything open, or everything shut: half the buttons are spent
            pg.click('.twists button[title="Expand everything"]')          # expand everything
            pg.wait_for_timeout(250)
            self.assertTrue(pg.is_disabled('.twists button[title="One level more"]'))
            self.assertTrue(pg.is_disabled('.twists button[title="Expand everything"]'))
            pg.click('.twists button[title="Collapse everything"]')          # collapse everything
            pg.wait_for_timeout(250)
            self.assertTrue(pg.is_disabled('.twists button[title="Collapse everything"]'))
            self.assertTrue(pg.is_disabled('.twists button[title="One level less"]'))
        self.page(work)

    def test_a_filter_never_leaves_a_folder_without_its_parents(self):
        """Three shoots at the third level of indentation with nothing above
        them read as orphaned folders, not as a filtered library."""
        def work(pg):
            self.open_tab(pg, "library")
            pg.wait_for_timeout(200)
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            pg.wait_for_selector("#treebody tr", timeout=15000)
            pg.click(".viewtabs button:has-text('Not rated')")
            pg.wait_for_timeout(2500)
            depths = pg.eval_on_selector_all(
                "#treebody tr td:first-child",
                "e => e.map(x => parseInt(x.style.paddingLeft))")
            self.assertTrue(depths)
            for before, after in zip(depths, depths[1:]):
                self.assertLessEqual(after - before, 20,
                                     f"a level was skipped: {depths}")
        self.page(work)


    def test_the_bottom_bar_moves_between_the_four_you_use(self):
        def work(pg):
            pg.wait_for_selector("#bottom button", timeout=15000)
            self.assertTrue(pg.eval_on_selector(
                "#bottom", "e => getComputedStyle(e).display !== 'none'"))
            pg.dispatch_event('#bottom button[data-b="places"]', "click")
            pg.wait_for_timeout(600)
            self.assertEqual(pg.evaluate("() => SCREEN"), "places")
            self.assertEqual(pg.eval_on_selector_all(
                "#bottom button.on", "e => e.map(b => b.dataset.b)"), ["places"])
            self.assertNoSideScroll(pg, "the bottom bar")
        self.phone(work)

    def test_and_is_not_in_the_way_at_a_desk(self):
        def work(pg):
            pg.wait_for_selector("#bottom", state="attached", timeout=15000)
            self.assertEqual(pg.eval_on_selector(
                "#bottom", "e => getComputedStyle(e).display"), "none",
                "the phone bar is showing at desktop width")
        self.page(work)

    def test_the_worker_keeps_the_shell_and_the_thumbnails_only(self):
        def work(pg):
            pg.wait_for_timeout(1200)
            names = pg.evaluate("() => caches.keys()")
            self.assertTrue(any(n.startswith("pm-shell-") for n in names), names)
            # and it must never answer for the page's own API
            said = pg.evaluate("() => fetch('api/health').then(r => r.json())")
            self.assertIn("release", said)
        self.page(work)

    def test_light_and_dark_can_be_chosen_and_are_remembered(self):
        def work(pg):
            pg.click("#theme")                       # the appearance panel
            pg.click('#lookpop .lookmode button >> nth=1')      # Light
            self.assertEqual(
                pg.eval_on_selector(":root", "e => e.getAttribute('data-theme')"),
                "light")
            # an accent, picked by name: the list starts with Ink since 4.0
            pg.click('#lookpop .lookacc button[onclick*="\'teal\'"]')
            pg.reload()
            pg.wait_for_timeout(500)
            self.assertEqual(
                pg.eval_on_selector(":root", "e => e.getAttribute('data-theme')"),
                "light")
            self.assertEqual(
                pg.eval_on_selector(":root", "e => e.getAttribute('data-accent')"),
                "teal")
        self.page(work)

    # ---------------------------------------------------- the file manager

    def test_the_file_manager_notices_a_file_that_appeared(self):
        """Refresh looked broken because the names were right and the pictures
        were the browser's old ones. Now the listing re-reads by itself, and a
        thumbnail's address carries the time on the file."""
        where = self.shoot_of("appearing", ["plain"])

        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow, #fileman .fmempty", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {where!r})")
            pg.wait_for_timeout(900)
            before = pg.evaluate("() => FM.panes[0].data.files.map(f => f.name)")
            self.assertIn("plain.JPG", before)
            shutil.copy(os.path.join(FIX, "rated.jpg"),
                        os.path.join(where, "LATER.JPG"))
            # no button pressed: the pane is read again while you are looking
            pg.wait_for_timeout(7000)
            after = pg.evaluate("() => FM.panes[0].data.files.map(f => f.name)")
            self.assertIn("LATER.JPG", after, "the pane never noticed the new file")
            # and every thumbnail is asked for with a version, so a changed file
            # is a different picture as far as any cache is concerned
            srcs = pg.eval_on_selector_all("#fileman img.th", "e => e.map(i => i.src)")
            self.assertTrue(srcs, "no thumbnails in the listing")
            self.assertTrue(all("&v=" in u or "?v=" in u for u in srcs), srcs)
        self.page(work)

    def test_the_trees_are_a_named_menu_not_chips_to_press_by_accident(self):
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmtop", timeout=15000)
            self.assertEqual(pg.eval_on_selector_all(".fmplaces button", "e => e.length"), 0,
                             "the old chip row is still there")
            pg.click('#fileman .fmtop button:has-text("More")')
            pg.wait_for_selector(".pmenu .vopt", timeout=5000)
            pg.click('.pmenu .vopt:has-text("Go to a set-up folder")')
            pg.wait_for_selector(".pmenu .vopt", timeout=5000)
            said = pg.eval_on_selector_all(".pmenu .vopt", "e => e.map(b => b.textContent)")
            self.assertTrue(any("Library" in t for t in said), said)
            # each one says what that tree is for, which a chip never did
            self.assertTrue(all(len(t.split()) > 2 for t in said), said)
        self.page(work)

    def test_stars_and_tags_show_in_the_listing_itself(self):
        """What the Photos tab was for. There is one place to look now."""
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.shoot!r})")
            pg.wait_for_timeout(1500)
            self.assertIsNot(pg.evaluate("() => FM.panes[0].marks"), None,
                             "the listing never asked for the marks")
            self.assertTrue(pg.evaluate(
                "() => Object.keys(FM.panes[0].marks).length > 0"))
            # and there is no separate tab to press instead
            self.assertFalse(pg.evaluate("() => TASKS.some(t => t.name === 'browse')"))
        self.page(work)

    def test_deleting_a_folder_in_the_explorer_opens_delete_folder(self):
        """Delete folder takes the folder's RAW, previews and video twins with
        it; deleting it straight from the explorer left those behind."""
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.lib!r})")
            pg.wait_for_timeout(800)
            folder = os.path.join(self.lib, "2022")
            pg.evaluate(f"() => fmToggle(0, {folder!r}, true)")
            sent = []
            pg.on("request", lambda r: sent.append(r.post_data or "")
                  if "/api/files" in r.url and r.method == "POST" else None)
            pg.evaluate("() => fmDelete()")
            pg.wait_for_timeout(500)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "delfolder")
            self.assertEqual(pg.input_value("#o_folder").strip(), folder)
            self.assertFalse([b for b in sent if '"delete"' in b],
                             "the explorer deleted it itself")
            self.assertTrue(os.path.isdir(folder))
        self.page(work)


    def _on_a_pc(self, desktop):
        was = os.environ.get("PM_DESKTOP")
        os.environ["PM_DESKTOP"] = "1" if desktop else ""
        return was

    def _back(self, was):
        if was is None:
            os.environ.pop("PM_DESKTOP", None)
        else:
            os.environ["PM_DESKTOP"] = was

    def _nas_tools_seen(self, pg):
        """Every place the page offers a tool: the Settings rail group, the
        Tools screen, the Settings card on it, and the list beside Setup."""
        pg.evaluate("() => openFeature('setup')")
        pg.wait_for_selector("#toolside .siderow", timeout=10000)
        tabs = pg.eval_on_selector("#toolside", "e => e.innerText")
        pg.evaluate("() => { RAILFAM = 'settings'; drawRail(); }")
        rail = pg.evaluate("() => [...document.querySelectorAll("
                           "'.railrow[data-t], .railrow[data-g]')]"
                           ".map(b => b.dataset.t)")
        note = pg.evaluate("() => !!document.getElementById('nasonly')")
        # The Settings card of the Tools screen, where these two live.
        pg.evaluate("() => goScreen('tools', {fam: 'settings'})")
        pg.wait_for_selector("#stage [data-t='setup']", timeout=15000)
        tools = pg.evaluate("() => [...document.querySelectorAll("
                            "'#stage [data-t]')].map(b => b.dataset.t)")
        return {"tabs": tabs, "rail": rail, "tools": tools, "note": note}

    def test_on_the_nas_the_nas_tools_are_offered(self):
        was = self._on_a_pc(False)
        try:
            def work(pg):
                got = self._nas_tools_seen(pg)
                self.assertIn("NAS", got["tabs"])
                self.assertIn("reindex", got["rail"])
                self.assertIn("reindex", got["tools"])
                self.assertIn("permissions", got["tools"])
                self.assertFalse(got["note"])
            self.page(work)
        finally:
            self._back(was)

    def test_on_a_pc_they_are_left_out_and_setup_says_so(self):
        was = self._on_a_pc(True)
        try:
            def work(pg):
                got = self._nas_tools_seen(pg)
                self.assertNotIn("NAS", got["tabs"].split())
                self.assertNotIn("Reindex", got["tabs"])
                for name in ("reindex", "permissions"):
                    self.assertNotIn(name, got["rail"])
                    self.assertNotIn(name, got["tools"])
                self.assertTrue(got["note"])
                pg.evaluate("() => openFeature('setup')")
                pg.wait_for_selector("#nasonly", timeout=10000)
                said = pg.eval_on_selector("#nasonly", "e => e.innerText")
                self.assertIn("NAS-only", said)
            self.page(work)
        finally:
            self._back(was)
    def test_sorting_is_the_managers_own_and_folders_stay_on_top(self):
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmtop", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.lib!r})")
            pg.wait_for_timeout(900)
            pg.click('#fileman .fmtop button:has-text("View")')
            pg.wait_for_selector(".pmenu .vopt", timeout=5000)
            pg.click('.pmenu .vopt:has-text("Order:")')
            pg.wait_for_selector(".pmenu .vopt", timeout=5000)
            pg.click('.pmenu .vopt:has-text("Size")')
            pg.wait_for_timeout(400)
            self.assertEqual(pg.evaluate("() => FM.panes[0].sort"), "size")
            kinds = pg.evaluate(
                "() => fmOrder(0, FM.panes[0].data.folders"
                ".concat(FM.panes[0].data.files)).map(x => x.kind === 'folder')")
            self.assertEqual(kinds, sorted(kinds, reverse=True),
                             "a folder fell in among the files")
        self.page(work)

    def test_left_alone_shows_the_photograph_not_only_its_name(self):
        """A list of names does not answer "which one is that". Every left-alone
        entry that IS a photograph gets its thumbnail and opens in the viewer."""
        one = os.path.join(self.shoot, "plain.JPG")

        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_timeout(400)
            html = pg.evaluate(
                """(path) => { render({task: "t", rows: [], skipped: [
                     [path, "no capture time in the file"],
                     ["a shoot with four in it", "counted, not moved"]],
                   notes: [], errors: [], stats: [], writes: false});
                   return document.getElementById("out").innerHTML; }""", one)
            self.assertIn("Left alone", html)
            self.assertIn("api/thumb", html)
            self.assertIn("peekSkipped", html)
            # the name is what is printed, never the whole way there
            self.assertIn(">plain.JPG<", html)
            self.assertIn("a shoot with four in it", html)
        self.page(work)

    # --------------------------------------------------- the power rename table

    def rename_tree(self, name, folders):
        where = os.path.join(self.lib, "renaming", name)
        for one in folders:
            os.makedirs(os.path.join(where, one), exist_ok=True)
        return where

    def test_the_rename_table_lists_every_folder_and_writes_nothing_until_told(self):
        where = self.rename_tree("plain", ["spain trip", "italy trip"])

        def work(pg):
            self.open_tab(pg, "rename")
            pg.wait_for_timeout(300)
            pg.evaluate(f"() => {{ RN.folder = {where!r}; RN.picked = []; return rnLoad(); }}")
            pg.wait_for_selector(".rnbox", timeout=15000)
            self.assertEqual(sorted(pg.eval_on_selector_all(
                ".rnbox", "e => e.map(i => i.value)")), ["italy trip", "spain trip"])
            # typing does not write: the button is what writes
            pg.fill('.rnrow[data-p$="spain trip"] .rnbox', "2022 Spain")
            pg.wait_for_timeout(900)
            self.assertTrue(os.path.isdir(os.path.join(where, "spain trip")),
                            "typing in the box renamed the folder")
            self.assertIn("1 ready", pg.text_content("#rnfoot"))
            # not awaited on purpose: rnApply waits for the dialog below, and
            # an awaited evaluate would hold the page while doing it
            pg.evaluate("() => { rnApply(); }")
            pg.wait_for_selector(".sure", timeout=5000)
            pg.click('.sure button[data-a="1"]')
            pg.wait_for_timeout(2500)
            self.assertTrue(os.path.isdir(os.path.join(where, "2022 Spain")))
            self.assertFalse(os.path.isdir(os.path.join(where, "spain trip")))
        self.page(work)

    def test_the_table_says_when_two_rows_would_meet_on_one_name(self):
        where = self.rename_tree("clashing", ["a shoot", "another shoot"])

        def work(pg):
            self.open_tab(pg, "rename")
            pg.wait_for_timeout(300)
            pg.evaluate(f"() => {{ RN.folder = {where!r}; RN.picked = []; return rnLoad(); }}")
            pg.wait_for_selector(".rnbox", timeout=15000)
            pg.evaluate("""() => {
              Object.keys(RN.names).forEach(k => { RN.names[k] = 'Spain 2022'; });
              rnDraw(); return rnCheck(); }""")
            pg.wait_for_timeout(900)
            self.assertEqual(pg.eval_on_selector_all(".rnrow.bad", "e => e.length"), 2)
            self.assertIn("cannot be renamed", pg.text_content("#rnfoot"))
            self.assertTrue(pg.eval_on_selector(
                ".rnbar button", "e => e.disabled"), "it would have renamed both")
            # and nothing was touched
            self.assertTrue(os.path.isdir(os.path.join(where, "a shoot")))
        self.page(work)

    def test_find_and_replace_fills_the_boxes_rather_than_renaming(self):
        where = self.rename_tree("replacing", ["IMG_one", "IMG_two"])

        def work(pg):
            self.open_tab(pg, "rename")
            pg.wait_for_timeout(300)
            pg.evaluate(f"() => {{ RN.folder = {where!r}; RN.picked = []; return rnLoad(); }}")
            pg.wait_for_selector(".rnbox", timeout=15000)
            pg.fill("#rnfind", "IMG_")
            pg.fill("#rnput", "2022 ")
            pg.click('.rntool:has-text("Find and replace") button')
            pg.wait_for_timeout(700)
            self.assertEqual(sorted(pg.eval_on_selector_all(
                ".rnbox", "e => e.map(i => i.value)")), ["2022 one", "2022 two"])
            self.assertTrue(os.path.isdir(os.path.join(where, "IMG_one")),
                            "replace wrote to disk on its own")
            # and every name can be put back without touching anything
            pg.click('.rntop button:has-text("Put every name back")')
            pg.wait_for_timeout(400)
            self.assertEqual(sorted(pg.eval_on_selector_all(
                ".rnbox", "e => e.map(i => i.value)")), ["IMG_one", "IMG_two"])
        self.page(work)

    def test_case_and_numbering_work_on_the_ticked_rows_only(self):
        where = self.rename_tree("ticking", ["one shoot", "two shoot"])

        def work(pg):
            self.open_tab(pg, "rename")
            pg.wait_for_timeout(300)
            pg.evaluate(f"() => {{ RN.folder = {where!r}; RN.picked = []; return rnLoad(); }}")
            pg.wait_for_selector(".rnbox", timeout=15000)
            pg.evaluate("""() => { rnTick(RN.rows[0].path, true); }""")
            pg.wait_for_timeout(200)
            pg.click('.rntool:has-text("Case and spacing") button:has-text("UPPER")')
            pg.wait_for_timeout(300)
            said = pg.evaluate("() => RN.rows.map(r => RN.names[r.path])")
            self.assertEqual(said[0], said[0].upper())
            self.assertNotEqual(said[1], said[1].upper(),
                                "an unticked row was changed too")
        self.page(work)

    def test_what_you_picked_in_files_is_what_the_table_opens_on(self):
        where = self.rename_tree("picking", ["kept", "left"])
        one = os.path.join(where, "kept")

        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow, #fileman .fmempty", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {where!r})")
            pg.wait_for_timeout(900)
            pg.evaluate(f"() => fmToggle(0, {one!r}, true)")
            # the tool beside it, the way a person reaches it - not back out to
            # the feature and in again, which re-opens the manager at the library
            pg.click('#toolside .siderow span:text-is("Power rename")')
            pg.wait_for_selector(".rnbox", timeout=15000)
            self.assertEqual(pg.eval_on_selector_all(
                ".rnbox", "e => e.map(i => i.value)"), ["kept"])
            self.assertTrue(pg.evaluate("() => RN.from_picked"))
        self.page(work)

    # ------------------------------------------------- what this round changed

    def test_the_use_in_menu_is_two_tiers_and_scrolls(self):
        """Flat, it was thirty-odd rows on a menu that could not scroll - on a
        phone the bottom of it did not exist."""
        def work(pg):
            pg.evaluate(f"() => workOn({{preventDefault(){{}}, "
                        f"target: document.body}}, {self.shoot!r})")
            pg.wait_for_selector("#fmenu", timeout=5000)
            tier1 = pg.eval_on_selector_all("#fmenu button.tier1", "e => e.length")
            self.assertTrue(0 < tier1 < 20, f"{tier1} rows on the first tier")
            self.assertEqual(pg.eval_on_selector_all("#fmenu button.tier2",
                                                     "e => e.length"), 0)
            # the list can be scrolled even when it is taller than the menu
            self.assertIn(pg.eval_on_selector("#fmenu .fmenulist",
                "e => getComputedStyle(e).overflowY"), ("auto", "scroll"))
            # opening one feature shows its tabs, and only that one
            pg.eval_on_selector('#fmenu button.tier1:has-text("Geotag")',
                                "e => e.click()")
            pg.wait_for_timeout(400)
            self.assertGreater(pg.eval_on_selector_all("#fmenu button.tier2",
                                                       "e => e.length"), 1)
            self.assertEqual(pg.eval_on_selector_all(
                "#fmenu button.tier1", "e => e.length"), tier1,
                "opening one feature changed how many are listed")
            pg.eval_on_selector('#fmenu button.tier2:has-text("Strip location")',
                                "e => e.click()")
            pg.wait_for_timeout(600)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "unlocate")
            self.assertEqual(pg.eval_on_selector("#o_folder", "e => e.value"),
                             self.shoot)
        self.page(work)

    def test_and_fits_on_a_phone_without_running_off_the_screen(self):
        def work(pg):
            pg.evaluate(f"() => workOn({{preventDefault(){{}}, "
                        f"target: document.body}}, {self.shoot!r})")
            pg.wait_for_selector("#fmenu", timeout=5000)
            box = pg.eval_on_selector("#fmenu", "e => e.getBoundingClientRect().toJSON()")
            self.assertLessEqual(box["right"], 391, "the menu runs off the side")
            self.assertGreaterEqual(box["left"], -1)
            self.assertLessEqual(box["height"], 844, "taller than the screen")
            self.assertNoSideScroll(pg, "the use-in menu")
        self.phone(work)

    def test_the_results_header_stays_above_the_rows_it_heads(self):
        """Scrolled, every row was painted straight over the header's words."""
        def work(pg):
            self.open_tab(pg, "library")
            pg.click("#go")
            pg.wait_for_selector("#treebody tr", timeout=60000)
            pg.evaluate("() => depthTo(99)")
            pg.wait_for_timeout(400)
            pg.evaluate("""() => {
                document.querySelector('table.tree').scrollIntoView({block:'center'});
                const s = document.querySelector('.card .scroll');
                if (s) s.scrollTop = 200; }""")
            pg.wait_for_timeout(400)
            # the row group is what sticks - a table cell cannot be lifted out
            # of the table's painting order by z-index, which is why it failed
            self.assertEqual(pg.eval_on_selector("table.tree thead",
                "e => getComputedStyle(e).position"), "sticky")
            self.assertEqual(pg.eval_on_selector("table.tree",
                "e => getComputedStyle(e).borderCollapse"), "separate")
            # and nothing is drawn where the header is
            over = pg.evaluate("""() => {
              const th = document.querySelector('table.tree thead th');
              const box = th.getBoundingClientRect();
              const at = document.elementFromPoint(box.left + box.width / 2,
                                                   box.top + box.height / 2);
              return at ? (at.closest('thead') ? "header"
                           : (at.closest('tbody') ? "a row" : at.tagName)) : "nothing"; }""")
            self.assertEqual(over, "header", f"{over} is painted over the header")
        self.page(work)

    def test_the_library_columns_can_be_put_away_and_stay_away(self):
        def work(pg):
            self.open_tab(pg, "library")
            pg.click("#go")
            pg.wait_for_selector("#treebody tr", timeout=60000)
            before = pg.eval_on_selector_all("table.tree th", "e => e.length")
            pg.click('.twists button.colpick')
            pg.wait_for_selector(".pmenu .vopt", timeout=5000)
            pg.click('.pmenu .vopt:has-text("Previews")')
            pg.wait_for_timeout(400)
            after = pg.eval_on_selector_all("table.tree th", "e => e.length")
            self.assertEqual(after, before - 1)
            said = pg.eval_on_selector_all("table.tree th", "e => e.map(t => t.textContent)")
            self.assertNotIn("Previews", said)
            # and a column that is off stays off across a redraw
            pg.evaluate("() => depthTo(99)")
            pg.wait_for_timeout(300)
            self.assertEqual(pg.eval_on_selector_all("table.tree th", "e => e.length"),
                             before - 1)
        self.page(work)

    def test_a_folder_says_what_it_weighs_when_asked(self):
        where = self.shoot_of("weighing", ["plain"])

        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {os.path.dirname(where)!r})")
            pg.wait_for_timeout(900)
            # nothing is walked until you ask
            self.assertGreater(pg.eval_on_selector_all("button.fmweigh.ask",
                                                       "e => e.length"), 0)
            pg.click('.fmrow:has-text("weighing") button.fmweigh')
            pg.wait_for_timeout(1500)
            said = pg.eval_on_selector_all(".fmweigh.done", "e => e.map(x => x.textContent)")
            self.assertTrue(said, "the size never arrived")
            self.assertRegex(said[0], r"\d")
        self.page(work)

    def test_the_viewer_can_act_on_the_one_photograph_it_is_showing(self):
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.shoot!r})")
            pg.wait_for_timeout(900)
            pg.evaluate("() => { const f = FM.panes[0].data.files.find(fmShowable);"
                        " fmOpen(0, f); }")
            pg.wait_for_selector("#viewer", timeout=8000)
            pg.click("#vmore")
            pg.wait_for_selector("#vmorepop .vopt", timeout=5000)
            said = pg.eval_on_selector_all("#vmorepop .vopt",
                                           "e => e.map(b => b.textContent.trim())")
            joined = " | ".join(said)
            for wanted in ("Remove location", "Rename it",
                           "Show it in File explorer",
                           "What it is", "Use the folder in"):
                self.assertIn(wanted, joined, joined)
            # and "what it is" reads the photograph rather than guessing
            pg.click('#vmorepop .vopt:has-text("What it is")')
            pg.wait_for_selector("#vmorepop .vfacts", timeout=8000)
            facts = pg.text_content("#vmorepop .vfacts")
            self.assertIn("Taken", facts)
            self.assertIn("Camera", facts)
        self.page(work)

    # ------------------------------------------- the histogram and the numbers

    def clipped_shoot(self):
        """A folder holding one photograph that is half pure black, half pure
        white - so the histogram has a right answer rather than a plausible
        shape."""
        from PIL import Image
        where = os.path.join(self.lib, "made", "clipping")
        os.makedirs(where, exist_ok=True)
        im = Image.new("RGB", (240, 240), (0, 0, 0))
        im.paste(Image.new("RGB", (240, 120), (255, 255, 255)), (0, 120))
        im.save(os.path.join(where, "half.JPG"), quality=95)
        return where

    def open_one(self, pg, folder):
        pg.evaluate("() => show('files')")
        pg.wait_for_selector("#fileman", timeout=15000)
        pg.evaluate(f"() => fmGo(0, {folder!r})")
        pg.wait_for_timeout(900)
        pg.evaluate("() => { const f = FM.panes[0].data.files.find(fmShowable);"
                    " fmOpen(0, f); }")
        pg.wait_for_selector("#viewer", timeout=8000)
        pg.wait_for_timeout(700)

    def test_the_histogram_reads_the_picture_on_screen(self):
        where = self.clipped_shoot()

        def work(pg):
            self.open_one(pg, where)
            # nothing is counted while it is off
            self.assertTrue(pg.eval_on_selector("#vhist", "e => e.hidden"))
            pg.eval_on_selector("#vhistb", "e => e.click()")
            pg.wait_for_timeout(700)
            self.assertFalse(pg.eval_on_selector("#vhist", "e => e.hidden"))
            bins = pg.evaluate("() => { const b = HISTCACHE[viewerPath()];"
                               " return b ? {dark: b.dark, light: b.light,"
                               " low: b.l[0] + b.l[1], high: b.l[254] + b.l[255],"
                               " mid: b.l[128]} : null; }")
            self.assertIsNotNone(bins, "the histogram never counted anything")
            # half of it is black and half is white, so both ends carry the
            # mass and the middle is empty
            self.assertGreater(bins["dark"], 0.3)
            self.assertGreater(bins["light"], 0.3)
            self.assertGreater(bins["low"], bins["mid"] * 10)
            self.assertGreater(bins["high"], bins["mid"] * 10)
            # and it says so rather than only drawing it
            said = pg.text_content("#vhistclip")
            self.assertIn("black", said)
            self.assertIn("white", said)
        self.page(work)

    def test_and_draws_luminance_or_the_three_channels_as_asked(self):
        where = self.clipped_shoot()

        def work(pg):
            self.open_one(pg, where)
            pg.eval_on_selector("#vhistb", "e => e.click()")
            pg.wait_for_timeout(500)
            self.assertEqual(pg.text_content("#vhistmode"), "RGB + luminance")
            pg.eval_on_selector("#vhist", "e => e.click()")
            pg.wait_for_timeout(200)
            self.assertEqual(pg.text_content("#vhistmode"), "Luminance")
            pg.eval_on_selector("#vhist", "e => e.click()")
            pg.wait_for_timeout(200)
            self.assertEqual(pg.text_content("#vhistmode"), "RGB")
            # something is actually painted, not an empty canvas
            painted = pg.evaluate("""() => {
              const c = document.getElementById('vhistc');
              const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
              let on = 0;
              for (let i = 3; i < d.length; i += 4) if (d[i] > 8) on++;
              return on; }""")
            self.assertGreater(painted, 200, "the histogram canvas is blank")
        self.page(work)

    def test_the_shot_details_say_the_four_numbers_and_are_remembered(self):
        def work(pg):
            self.open_one(pg, self.shoot)
            pg.eval_on_selector("#vshotb", "e => e.click()")
            pg.wait_for_timeout(700)
            line = pg.text_content(".vshotline")
            for wanted in ("mm", "f/", "ISO", "1/"):
                self.assertIn(wanted, line, line)
            # what the camera is CALLED - the code it writes is in the ⋯ panel
            self.assertIn("Lumix GH4", pg.text_content(".vshotrest"))
            # it stays on for the next photograph
            pg.evaluate("() => viewerStep(1)")
            pg.wait_for_timeout(900)
            self.assertFalse(pg.eval_on_selector("#vshot", "e => e.hidden"))
            # and for the next visit to the app
            pg.reload()
            pg.wait_for_timeout(900)
            self.open_one(pg, self.shoot)
            self.assertFalse(pg.eval_on_selector("#vshot", "e => e.hidden"),
                             "the overlay was forgotten on reload")
            pg.eval_on_selector("#vshotb", "e => e.click()")
            pg.wait_for_timeout(300)
            self.assertTrue(pg.eval_on_selector("#vshot", "e => e.hidden"))
        self.page(work)

    def test_a_raw_gets_both_and_says_the_curve_came_from_its_jpeg(self):
        """The viewer is showing the JPEG the camera embedded, which is a real
        picture to measure - but it is the camera's rendering, not the sensor
        data, and that has to be said rather than assumed."""
        def work(pg):
            self.open_one(pg, self.shoot)
            pg.evaluate("""() => { const raw = VIEW.list.find(p => /\\.RW2$/i.test(p));
                if (raw) { VIEW.at = VIEW.list.indexOf(raw); viewerShow(0); } }""")
            pg.wait_for_timeout(900)
            self.assertRegex(pg.evaluate("() => viewerPath()"), r"\.RW2$")
            pg.eval_on_selector("#vhistb", "e => e.click()")
            pg.eval_on_selector("#vshotb", "e => e.click()")
            pg.wait_for_timeout(900)
            self.assertFalse(pg.eval_on_selector("#vhist", "e => e.hidden"))
            self.assertFalse(pg.eval_on_selector("#vshot", "e => e.hidden"))
            self.assertIn("embedded JPEG", pg.text_content("#vhistclip"))
        self.page(work)

    def test_both_overlays_fit_a_phone_and_go_with_the_chrome(self):
        def work(pg):
            self.open_one(pg, self.shoot)
            pg.eval_on_selector("#vhistb", "e => e.click()")
            pg.eval_on_selector("#vshotb", "e => e.click()")
            pg.wait_for_timeout(700)
            for sel in ("#vhist", "#vshot"):
                box = pg.eval_on_selector(sel, "e => e.getBoundingClientRect().toJSON()")
                self.assertLessEqual(box["right"], 391, f"{sel} runs off the side")
                self.assertGreaterEqual(box["left"], -1, sel)
            # they must not sit on top of each other
            a = pg.eval_on_selector("#vshot", "e => e.getBoundingClientRect().toJSON()")
            b = pg.eval_on_selector("#vhist", "e => e.getBoundingClientRect().toJSON()")
            self.assertGreaterEqual(b["top"], a["bottom"] - 2,
                                    "the histogram is on top of the shot details")
            # tapping the picture hides everything, numbers included
            pg.evaluate("() => { VIEW.chrome = false;"
                        " document.getElementById('viewer').classList.remove('chrome'); }")
            pg.wait_for_timeout(300)
            self.assertEqual(pg.eval_on_selector("#vhist",
                "e => getComputedStyle(e).opacity"), "0")
            self.assertEqual(pg.eval_on_selector("#vshot",
                "e => getComputedStyle(e).opacity"), "0")
        self.phone(work)

    # ------------------------------------------------------------ searching

    def test_a_search_lists_what_it_found_with_the_exposure_beside_it(self):
        def work(pg):
            self.open_tab(pg, "search")
            pg.wait_for_selector("#searchbar", timeout=15000)
            pg.fill("#o_camera", "gh4")
            pg.click("#go")
            pg.wait_for_selector("#out table", timeout=60000)
            said = pg.text_content("#out")
            self.assertIn("Asking for", said)
            self.assertIn("f/", said, "the exposure is not in the table")
            rows = pg.eval_on_selector_all("#out table tr td:first-child",
                                           "e => e.length")
            self.assertGreater(rows, 0)
            # and every row can be opened in the viewer, like any other table
            self.assertGreater(pg.eval_on_selector_all("#out img.th",
                                                       "e => e.length"), 0)
        self.page(work)

    def test_the_photos_filters_carry_over_to_search(self):
        """Photos reads the index; Search reads folders. The filter panel
        hands what is in it to Search, under Search's own option names."""
        def work(pg):
            pg.evaluate("() => { FILTER = {}; ALBUM = ''; goScreen('photos'); }")
            pg.wait_for_selector("#tiles", timeout=15000)
            pg.evaluate("() => filterPanel()")
            pg.wait_for_selector("#searchinstead", timeout=10000)
            self.assertIn("reads the library index",
                          pg.text_content("#photosreads"))
            pg.fill("[data-f=since]", "2020-01-01")
            pg.select_option("[data-f=stars_from]", "3")
            pg.fill("[data-f=iso_to]", "800")
            pg.click("#searchinstead")
            pg.wait_for_selector("#searchbar", timeout=10000)
            pg.wait_for_timeout(300)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "search")
            self.assertEqual(pg.input_value("#o_since"), "2020-01-01")
            self.assertEqual(pg.input_value("#o_stars_from"), "3")
            self.assertEqual(pg.input_value("#o_iso_to"), "800")
            self.assertIn("reads the folders", pg.text_content("#searchreads"))
            # filled, not run: a folder is usually what you came here to pick
            self.assertEqual(pg.evaluate("() => PLAN ? PLAN.task : ''"), "")
        self.page(work)

    def test_a_search_inside_the_library_can_be_shown_in_photos(self):
        def work(pg):
            self.open_tab(pg, "search")
            pg.wait_for_selector("#searchbar", timeout=15000)
            pg.evaluate("(f) => { const b = document.getElementById('o_folders');"
                        " b.value = f; b.dispatchEvent(new Event('input')); }",
                        os.path.join(self.lib, "2022"))
            pg.fill("#o_since", "2000-01-01")
            pg.click("#go")
            pg.wait_for_selector("#showinphotos", timeout=60000)
            pg.click("#showinphotos")
            pg.wait_for_timeout(500)
            self.assertEqual(pg.evaluate("() => SCREEN"), "photos")
            got = pg.evaluate("() => FILTER")
            self.assertEqual(got.get("since"), "2000-01-01")
            self.assertNotIn("folders", got)
            self.assertIn("since=2000-01-01", pg.evaluate("() => shotQuery(0)"))
        self.page(work)

    def test_a_search_outside_the_library_offers_no_photos_link(self):
        def work(pg):
            self.open_tab(pg, "search")
            pg.wait_for_selector("#searchbar", timeout=15000)
            self.assertTrue(pg.evaluate(
                "(l) => underLibrary([l + '/2022'])", self.lib))
            self.assertFalse(pg.evaluate(
                "(l) => underLibrary([l + ' Raw'])", self.lib))
            self.assertFalse(pg.evaluate("() => underLibrary(['/elsewhere'])"))
            pg.evaluate("(f) => { const b = document.getElementById('o_folders');"
                        " b.value = f; b.dispatchEvent(new Event('input')); }",
                        self.previews)
            self.assertEqual(pg.evaluate("() => showInPhotosButton()"), "")
        self.page(work)

    def test_a_box_too_many_finds_nothing_and_says_why(self):
        def work(pg):
            self.open_tab(pg, "search")
            pg.wait_for_selector("#searchbar", timeout=15000)
            pg.fill("#o_camera", "gh4")
            pg.fill("#o_iso_from", "64000")
            pg.click("#go")
            pg.wait_for_timeout(3000)
            said = pg.text_content("#out")
            self.assertIn("one box too many", said)
        self.page(work)

    def test_a_search_is_kept_by_name_and_fills_the_boxes_again(self):
        def work(pg):
            self.open_tab(pg, "search")
            pg.wait_for_selector("#searchbar", timeout=15000)
            pg.fill("#o_camera", "gh4")
            pg.fill("#o_focal_to", "30")
            pg.evaluate("() => searchSend({name: 'wide GH4', ask: searchNow()})")
            pg.wait_for_timeout(700)
            self.assertIn("wide GH4", pg.text_content(".kept"))
            # emptied, then filled again by pressing the kept one
            pg.fill("#o_camera", "")
            pg.fill("#o_focal_to", "")
            pg.eval_on_selector(".keptone button.ghost", "e => e.click()")
            pg.wait_for_timeout(400)
            self.assertEqual(pg.eval_on_selector("#o_camera", "e => e.value"), "gh4")
            self.assertEqual(pg.eval_on_selector("#o_focal_to", "e => e.value"), "30")
            # and it survives a reload, because it is kept on the NAS
            pg.reload()
            pg.wait_for_timeout(1200)
            self.open_tab(pg, "search")
            pg.wait_for_timeout(900)
            self.assertIn("wide GH4", pg.text_content(".kept"))
            pg.eval_on_selector(".keptx", "e => e.click()")
            pg.wait_for_timeout(600)
            self.assertNotIn("wide GH4", pg.text_content(".kept"))
        self.page(work)

    def test_the_matches_go_to_the_file_manager_as_one_listing(self):
        """They are in different folders, and the manager is built around one
        folder - so this is the one listing that is a set rather than a place."""
        def work(pg):
            self.open_tab(pg, "search")
            pg.wait_for_selector("#searchbar", timeout=15000)
            pg.fill("#o_camera", "gh4")
            pg.click("#go")
            pg.wait_for_selector("#out table", timeout=60000)
            pg.eval_on_selector('#out button:has-text("Send these to Files")',
                                "e => e.click()")
            pg.wait_for_timeout(2500)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "files")
            found = pg.evaluate("() => (FM.panes[FM.at].found || []).length")
            self.assertGreater(found, 1)
            rows = pg.eval_on_selector_all("#fileman .fmrow", "e => e.length")
            self.assertEqual(rows, found)
            # more than one folder in one listing, and it says so
            self.assertIn("found", pg.text_content("#fileman .fmtop"))
            self.assertRegex(pg.text_content("#fileman .fmstat"), r"from \d+ folders?")
            # and it can be left again
            pg.eval_on_selector('#fileman .fmtop button:has-text("leave")',
                                "e => e.click()")
            pg.wait_for_timeout(1200)
            self.assertIsNot(pg.evaluate("() => FM.panes[FM.at].found"), True)
            self.assertTrue(pg.evaluate("() => !!FM.panes[FM.at].path"))
        self.page(work)

    # ------------------------------------------------------ the dashboard

    def test_the_library_opens_on_a_dashboard_above_everything_else(self):
        def work(pg):
            self.open_tab(pg, "library")
            pg.click("#go")
            pg.wait_for_selector("#treebody tr", timeout=90000)
            pg.wait_for_timeout(600)
            # tiles, meters and charts are all there
            self.assertGreater(pg.eval_on_selector_all(".tile2", "e => e.length"), 3)
            self.assertGreater(pg.eval_on_selector_all(".meter", "e => e.length"), 2)
            titles = pg.eval_on_selector_all(".chart h4", "e => e.map(x => x.textContent)")
            for wanted in ("Where the space is", "Aperture", "Stars"):
                self.assertIn(wanted, titles)
            # and they are ABOVE the numbers and the tree, not under them
            order = pg.evaluate("""() => {
              const cards = [...document.querySelectorAll('#out .card')];
              return cards.map(c => c.querySelector('.tiles') ? 'charts'
                : c.querySelector('table.tree') ? 'tree'
                : c.querySelector('.charts') ? 'more-charts' : 'other'); }""")
            self.assertLess(order.index("charts"), order.index("tree"))
        self.page(work)

    def test_every_chart_says_its_numbers_as_words_as_well_as_colour(self):
        """Three of the light slots sit under 3:1 on white, so a reader who
        cannot separate two hues still has to be able to read the chart."""
        def work(pg):
            self.open_tab(pg, "library")
            pg.click("#go")
            pg.wait_for_selector(".chart", timeout=90000)
            pg.wait_for_timeout(500)
            # every donut slice is named and numbered in its legend
            donuts = pg.eval_on_selector_all(".chart svg[role=img]", "e => e.length")
            self.assertGreater(donuts, 0)
            legends = pg.eval_on_selector_all(".clegend", "e => e.length")
            self.assertEqual(legends, donuts)
            self.assertTrue(all(t.strip() for t in pg.eval_on_selector_all(
                ".clegend b", "e => e.map(x => x.textContent)")))
            # every bar carries its value beside it
            self.assertTrue(all(t.strip() for t in pg.eval_on_selector_all(
                ".bval", "e => e.map(x => x.textContent)")))
            # and a mark says what it is on hover
            self.assertTrue(all(pg.eval_on_selector_all(
                ".brow", "e => e.map(x => !!x.dataset.tip)")))
        self.page(work)

    def test_a_chart_with_one_slice_still_draws_a_ring(self):
        """An arc whose start and end are the same point draws nothing, which
        is how a library with one camera in it got an empty hole."""
        def work(pg):
            self.open_tab(pg, "library")
            pg.click("#go")
            pg.wait_for_selector(".chart", timeout=90000)
            pg.wait_for_timeout(500)
            drawn = pg.evaluate("""() => [...document.querySelectorAll('.chart svg')]
              .map(s => s.querySelectorAll('path[d], circle[stroke]').length)""")
            self.assertTrue(drawn, "no donuts at all")
            self.assertTrue(all(n > 0 for n in drawn),
                            f"a donut drew nothing: {drawn}")
        self.page(work)

    def test_search_and_compare_are_beside_the_library(self):
        def work(pg):
            self.open_tab(pg, "library")
            pg.wait_for_timeout(400)
            tabs = pg.eval_on_selector_all("#toolside .siderow span",
                                           "e => e.map(x => x.textContent.trim())")
            for wanted in ("Search", "Compare"):
                self.assertIn(wanted, tabs, tabs)
            # Storage is in Maintain, so it is beside Clean up - the list only
            # ever names tools from the group the open one is in
            self.assertNotIn("Storage", tabs, tabs)
            # "Cameras and lenses" is gone: the dashboard's own camera and lens
            # charts, Compare and Search each answered more of it than it did,
            # and a tab that is a worse version of three others is a tab you
            # open once.
            self.assertNotIn("Cameras and lenses", tabs, tabs)
            # and none of them is a feature of its own any more - they are
            # under the Library, in the drawer as well as on the tab strip
            for moved in ("search", "compare"):
                self.assertEqual(pg.evaluate(
                    f"() => (TASKS.find(t => t.name === '{moved}') || {{}}).parent"),
                    "library", moved)
        self.page(work)

    def test_the_list_names_only_tools_from_its_own_group(self):
        def work(pg):
            for name in ("blur", "space", "cull", "library", "cleanup"):
                self.open_tab(pg, name)
                pg.wait_for_timeout(250)
                tabs = pg.eval_on_selector_all(
                    "#toolside .siderow", "e => e.map(b => b.dataset.t)")
                fams = pg.evaluate("""(names) => names.map(n =>
                  (FAMILIES.find(f => f.tasks.includes(n)) || {}).key)""", tabs)
                self.assertEqual(len(set(fams)), 1, f"{name}: {tabs} {fams}")
            self.open_tab(pg, "cleanup")
            pg.wait_for_timeout(250)
            row = pg.eval_on_selector_all("#toolside .siderow span",
                                          "e => e.map(x => x.textContent.trim())")
            self.assertIn("Storage", row, row)
        self.page(work)

    # ------------------------------------------------- what it looks like

    def test_a_dropdown_on_the_page_is_readable(self):
        """It was not. The page menus borrowed the viewer's popup, which is a
        dark box with a palette nailed to it and is declared LATER in the
        stylesheet - so on a light theme the box stayed #1d1f24 while the text
        went back to var(--ink) #1b1e23. Contrast 1.0:1: a menu that opened
        and could not be read at all."""
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman", timeout=15000)
            pg.click('#fileman .fmtop button:has-text("View")')
            pg.wait_for_selector(".pmenu .vopt", timeout=5000)
            got = pg.eval_on_selector(".pmenu .vopt", """e => {
              const s = getComputedStyle(e);
              const box = getComputedStyle(e.closest('.pmenu'));
              return [s.color, box.backgroundColor];
            }""")

            def lum(css):
                nums = [int(n) / 255 for n in re.findall(r"\d+", css)[:3]]
                out = [c / 12.92 if c <= 0.03928
                       else ((c + 0.055) / 1.055) ** 2.4 for c in nums]
                return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]

            a, b = lum(got[0]), lum(got[1])
            ratio = (max(a, b) + 0.05) / (min(a, b) + 0.05)
            self.assertGreater(ratio, 4.5,
                               f"menu text on its own box is {ratio:.1f}:1 - {got}")
        self.page(work)

    def test_a_chart_mark_opens_exactly_one_bubble(self):
        """There were two tooltip engines, both bound to [data-tip], so every
        bar and slice opened two at once - one under the mark and one beside
        the pointer."""
        def work(pg):
            self.open_tab(pg, "library")
            pg.click("#go")
            pg.wait_for_selector(".chart", timeout=90000)
            # Into view FIRST. The bubble closes on scroll, on purpose - a bubble
            # anchored to something that has moved is worse than none - and
            # hovering something off-screen makes the driver scroll to it.
            pg.eval_on_selector(".chart .brow[data-tip]",
                                "e => e.scrollIntoView({block: 'center'})")
            pg.wait_for_timeout(300)
            pg.hover(".chart .brow[data-tip]")
            pg.wait_for_timeout(300)
            showing = pg.evaluate("""() => [...document.body.children]
                .filter(e => {
                  const s = getComputedStyle(e);
                  return (e.id === 'tip' || e.className === 'viztip')
                    && !e.hidden && s.display !== 'none';
                }).length""")
            self.assertEqual(showing, 1, "a mark opened more than one bubble")
        self.page(work)

    def test_the_search_criteria_start_folded_and_open_when_filled(self):
        """Twenty-two boxes over six groups is, on a phone, one column you
        scroll past to reach the button."""
        def work(pg):
            pg.evaluate("() => show('search')")
            pg.wait_for_selector("#form details.gfold", timeout=15000)
            shut = pg.eval_on_selector_all("#form details.gfold",
                                           "e => e.filter(d => !d.open).length")
            self.assertGreater(shut, 2, "nothing was folded away")
            # and folding never hides something that is in force
            pg.evaluate("""() => { const b = document.getElementById('o_camera');
              b.value = 'gh4';
              b.dispatchEvent(new Event('input', {bubbles: true})); }""")
            pg.wait_for_timeout(250)
            open_now = pg.eval_on_selector_all(
                "#form details.gfold",
                "e => e.filter(d => d.open).map(d => d.dataset.g)")
            self.assertTrue(open_now, "a group carrying a value stayed shut")
            said = pg.eval_on_selector_all("#form details.gfold .gcount",
                                           "e => e.map(x => x.textContent).join('')")
            self.assertIn("set", said,
                          "a folded group does not say how much it holds")
        self.page(work)

    @staticmethod
    def _box_in_view(pg, box):
        """A folder box is a hidden field with chips and a Browse button beside
        it, so "visible" is its row: drawn, and not inside a closed fold."""
        return pg.evaluate("""(id) => {
          const el = document.getElementById(id);
          if (!el) return false;
          const shut = el.closest('details:not([open])');
          const row = el.parentElement;
          return !shut && row.getBoundingClientRect().height > 0; }""", box)

    def test_by_date_opens_folded_with_its_folder_in_view(self):
        """Eighteen boxes over six groups. Folded, the folder and five named
        headings; and nothing in force is hidden, because a default is not a
        change."""
        def work(pg):
            pg.evaluate("() => show('bydate')")
            pg.wait_for_selector("#form details.gfold", timeout=15000)
            groups = pg.eval_on_selector_all(
                "#form details.gfold", "e => e.map(d => [d.dataset.g, d.open])")
            self.assertGreaterEqual(len(groups), 4)
            self.assertEqual([g for g, was in groups if was], [],
                             "a group opened with nothing changed in it")
            self.assertTrue(self._box_in_view(pg, "o_folder"),
                            "the folder is folded away")
            self.assertTrue(pg.is_visible("#go"))
            self.assertFalse(pg.is_visible("#o_shape"))
            # one Advanced still, as on every other form
            self.assertLessEqual(pg.eval_on_selector_all(
                "#form details.adv", "e => e.length"), 1)
            # opening a group shows what is in it
            pg.click("#form details.gfold[data-g='Pattern'] > summary")
            pg.wait_for_timeout(150)
            self.assertTrue(pg.is_visible("#o_shape"))
            self.assertTrue(pg.is_visible("#o_pattern"))
            # and a group that carries a change opens and says so
            pg.evaluate("""() => { const b = document.getElementById('o_near_hours');
              b.value = '3'; b.dispatchEvent(new Event('input')); }""")
            pg.wait_for_timeout(150)
            video = pg.eval_on_selector("#form details.gfold[data-g='Videos']",
                                        "d => [d.open, d.textContent]")
            self.assertTrue(video[0])
            self.assertIn("1 set", video[1])
        self.page(work)

    def test_a_form_whose_first_group_is_named_opens_that_one(self):
        """Retime keeps its folder in "Folders". Folded, that would be a form
        with no folder on it."""
        def work(pg):
            pg.evaluate("() => show('retime')")
            pg.wait_for_selector("#form details.gfold", timeout=15000)
            first = pg.eval_on_selector("#form details.gfold",
                                        "d => [d.dataset.g, d.open]")
            self.assertEqual(first, ["Folders", True])
            self.assertTrue(self._box_in_view(pg, "o_folder"))
            rest = pg.eval_on_selector_all(
                "#form details.gfold", "e => e.slice(1).filter(d => d.open).length")
            self.assertEqual(rest, 0)
        self.page(work)

    def test_folding_by_date_sends_the_same_plan_request(self):
        """Folding is how the boxes are shown, never what is sent."""
        def work(pg):
            sent = []

            def answer(route):
                sent.append(json.loads(route.request.post_data or "{}"))
                route.fulfill(status=200, content_type="application/json",
                              body='{"error": "held by the test"}')
            pg.route("**/api/plan", answer)
            # before: the same form drawn the way it was, unfolded
            unfolded = pg.evaluate("""() => {
              byName('bydate').fold_groups = false; show('bydate');
              const got = values(); byName('bydate').fold_groups = true;
              return got; }""")
            self.assertEqual(pg.eval_on_selector_all("#form details.gfold",
                                                     "e => e.length"), 0)
            pg.evaluate("() => show('bydate')")
            pg.wait_for_selector("#form details.gfold", timeout=15000)
            pg.click("#go")
            pg.wait_for_timeout(600)
            self.assertTrue(sent, "no plan was asked for")
            asked = sent[-1]
            self.assertEqual(asked["task"], "bydate")
            names = pg.evaluate("() => byName('bydate').options.map(o => o.name)")
            self.assertEqual(sorted(asked["options"]), sorted(names))
            self.assertEqual(asked["options"], unfolded)
        self.page(work)

    def test_the_folder_picker_is_not_under_the_phone_bars(self):
        """At z-index 9 it sat below the fixed bottom bar and the sticky
        header, so on a phone the last folder rows and "Use this folder" were
        painted over and could not be tapped."""
        def work(pg):
            pg.evaluate("() => show('library')")
            pg.wait_for_timeout(400)
            pg.click('#form button:has-text("Browse")')
            pg.wait_for_selector(".veil .pick", timeout=10000)
            over = pg.evaluate("""() => {
              const veil = document.querySelector('.veil');
              const bar = document.getElementById('bottom');
              const r = bar.getBoundingClientRect();
              const at = document.elementFromPoint(r.left + r.width / 2,
                                                   r.top + r.height / 2);
              return [+getComputedStyle(veil).zIndex,
                      +getComputedStyle(bar).zIndex,
                      !!(at && at.closest('.veil'))];
            }""")
            self.assertGreater(over[0], over[1],
                               "the picker sits under the bottom bar")
            self.assertTrue(over[2], "the bottom bar still catches the taps")
        self.phone(work)

    # -------------------------------------------- arranging the dashboard

    def test_the_dashboard_is_what_you_arranged_it_to_be(self):
        def work(pg):
            self.open_tab(pg, "library")
            pg.click("#go")
            pg.wait_for_selector(".chart", timeout=90000)
            pg.wait_for_timeout(500)
            was = pg.eval_on_selector_all("[data-widget]",
                                          "e => e.map(x => x.dataset.widget)")
            self.assertIn("chart:year", was)
            pg.click("#boardarrange")
            pg.wait_for_timeout(300)
            pg.eval_on_selector('[data-widget="chart:year"] .wdrop',
                                "e => e.click()")
            # waiting on the WIDGET, not on ".chart": the old charts are still in
            # the page while the new plan is being read, so any selector that
            # matches both is satisfied before anything has changed
            pg.wait_for_function(
                "() => !document.querySelector('[data-widget=\"chart:year\"]')"
                " && document.querySelectorAll('[data-widget]').length",
                timeout=90000)
            now = pg.eval_on_selector_all("[data-widget]",
                                          "e => e.map(x => x.dataset.widget)")
            self.assertNotIn("chart:year", now)
            # taken off, not lost: it is offered back
            off = pg.eval_on_selector_all(".offw", "e => e.length")
            self.assertGreater(off, 0, "nothing was offered to put back")
            # and it survives leaving the tab and coming back
            pg.evaluate("() => show('files')")
            pg.wait_for_timeout(300)
            self.open_tab(pg, "library")
            pg.click("#go")
            pg.wait_for_function(
                "() => document.querySelectorAll('[data-widget]').length",
                timeout=90000)
            again = pg.eval_on_selector_all("[data-widget]",
                                            "e => e.map(x => x.dataset.widget)")
            self.assertNotIn("chart:year", again)
            # and arranging is a mode you left when you left the tab
            self.assertEqual(pg.eval_on_selector_all(".wtools", "e => e.length"), 0)
            # put it back, for whatever runs after this
            pg.click("#boardarrange")
            pg.wait_for_timeout(250)
            pg.click('button:has-text("Put it back as it was")')
            pg.wait_for_function(
                "() => !!document.querySelector('[data-widget=\"chart:year\"]')",
                timeout=90000)
        self.page(work)

    def test_a_bucket_searches_the_folder_the_chart_counted(self):
        """The Library was pointed at one shoot, the chart counted that shoot,
        and the search the bar led to counted the whole library - so the bar
        said one number and the table that opened said another."""
        def work(pg):
            self.open_tab(pg, "library")
            pg.fill("#o_folder", self.shoot)
            pg.click("#go")
            pg.wait_for_selector(".chart", timeout=90000)
            said = pg.evaluate("() => (PLAN.charts || {}).folders || []")
            self.assertEqual(said, [self.shoot])
            # dispatched rather than .click(): the bar may be an SVG node, and
            # SVG elements have no click() method
            pg.eval_on_selector(".chart .brow.go, .chart .cbar.go",
                                "e => e.dispatchEvent(new MouseEvent('click',"
                                " {bubbles: true}))")
            pg.wait_for_timeout(1200)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "search")
            where = pg.eval_on_selector("#o_folders", "e => e.value").strip()
            self.assertEqual(where, self.shoot,
                             "the search widened to the whole library")
        self.page(work)

    def test_the_dashboard_never_says_how_many_photographs_have_a_date(self):
        """Every photograph in a library has one, so the meter read 100% for
        everybody, every time, and spent a row of the first screen saying so."""
        def work(pg):
            self.open_tab(pg, "library")
            pg.click("#go")
            pg.wait_for_selector(".meters", timeout=90000)
            self.assertNotIn("With a date", pg.text_content(".meters"))
        self.page(work)

    def test_the_bands_a_chart_groups_by_can_be_changed(self):
        def work(pg):
            self.open_tab(pg, "bands")
            pg.wait_for_selector(".bandset", timeout=20000)
            box = '.bandset[data-set="iso"] textarea'
            pg.fill(box, "dim = 400\nbright = 1e9")
            pg.click('.bandset[data-set="iso"] button:has-text("Keep these")')
            pg.wait_for_timeout(600)
            self.assertIn("Kept",
                          pg.text_content('.bandset[data-set="iso"] .bandwhy'))
            # a table that does not add up is refused, and says which line
            pg.fill(box, "high = 800\nlow = 400\ntop = 1e9")
            pg.click('.bandset[data-set="iso"] button:has-text("Keep these")')
            pg.wait_for_timeout(600)
            self.assertIn("line 2",
                          pg.text_content('.bandset[data-set="iso"] .bandwhy'))
            # and the refusal did not half-save it
            pg.click('.bandset[data-set="iso"] button:has-text("Put the built-in")')
            pg.wait_for_timeout(600)
            self.assertIn("100 and under",
                          pg.eval_on_selector(box, "e => e.value"))
        self.page(work)

    # ------------------------------------------------- the way in, and the shape

    def test_the_menu_is_grouped_and_can_be_searched(self):
        """Thirteen features with twenty tabs inside them, in one flat list,
        does not tell somebody which of them they are supposed to press first.
        Headings do - and the box finds the tab inside a feature, which is where
        half of them live."""
        def work(pg):
            pg.evaluate("() => goScreen('tools')")
            pg.wait_for_selector("#cats .cat", timeout=15000)
            heads = pg.eval_on_selector_all("#cats .cat h3",
                                            "e => e.map(x => x.textContent)")
            self.assertGreaterEqual(len(heads), 5, "the tools are still one list")
            # a word that is inside a TAB, not a feature: Cull is under Clean up
            pg.fill("#findtool", "cull")
            pg.wait_for_timeout(250)
            shown = pg.eval_on_selector_all(
                "#cats .cat:not([hidden]) .list button:not([hidden])",
                "e => e.map(x => x.dataset.t)")
            self.assertIn("cull", shown)
            self.assertNotIn("bydate", shown, "it matched something it should not")
            # and Enter opens it rather than making you aim at the button
            pg.press("#findtool", "Enter")
            pg.wait_for_timeout(400)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "cull")
        self.page(work)

    def test_searching_for_nothing_says_nothing_matches(self):
        """An empty menu with no explanation reads as a broken menu."""
        def work(pg):
            pg.evaluate("() => goScreen('tools')")
            pg.wait_for_selector("#cats .cat", timeout=15000)
            pg.fill("#findtool", "qqzz")
            pg.wait_for_timeout(250)
            left = pg.eval_on_selector_all("#cats .cat:not([hidden])", "e => e.length")
            self.assertEqual(left, 0, "it kept a card with nothing in it")
        self.page(work)

    def test_a_feature_that_writes_shows_the_same_four_steps(self):
        def work(pg):
            self.open_tab(pg, "previews")
            pg.wait_for_selector("#steps", timeout=10000)
            self.assertEqual(pg.eval_on_selector_all("#steps li", "e => e.length"), 4)
            self.assertEqual(pg.eval_on_selector("#steps li.now",
                                                 "e => e.dataset.s"), "1")
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            # for the PLAN, not for the first card: "Looking..." is a card too
            pg.wait_for_selector("#apply", timeout=90000)
            self.assertEqual(pg.eval_on_selector("#steps li.now",
                                                 "e => e.dataset.s"), "2",
                             "looking at the plan is still step one")
            self.assertEqual(pg.eval_on_selector_all("#steps li.done",
                                                     "e => e.length"), 1)
        self.page(work)

    def test_and_a_tab_that_only_reports_has_no_strip_at_all(self):
        """Four boxes with two of them permanently grey is furniture."""
        def work(pg):
            self.open_tab(pg, "library")
            pg.wait_for_timeout(250)
            self.assertEqual(pg.eval_on_selector_all("#steps", "e => e.length"), 0)
        self.page(work)

    def test_the_advanced_settings_are_one_disclosure_not_seven(self):
        """A form could show five collapsed boxes named More, Limits and What
        to do with RAWs, and you still had to open each one to find out whether
        any of it concerned you."""
        def work(pg):
            self.open_tab(pg, "previews")
            pg.wait_for_timeout(250)
            adv = pg.eval_on_selector_all("#form details.adv", "e => e.length")
            self.assertEqual(adv, 1, "there is not exactly one Advanced")
            said = pg.text_content("#form details.adv > summary")
            self.assertIn("More settings", said)
            self.assertRegex(said, r"More settings \(\d+\)",
                             "it does not say how much it holds")
            # nothing folded inside something folded
            deep = pg.eval_on_selector_all(
                "#form details.adv details", "e => e.length")
            self.assertEqual(deep, 0, "a setting is two clicks deep")
        self.page(work)

    def test_what_a_feature_is_for_is_said_before_you_open_it(self):
        """3.1 took the sentence off the form. Every list that reaches a feature
        carries its one line now - the rail, the cards, a category page - so by
        the time the form is on screen you have already read it, and a copy of
        it above the controls was prose pushing them down on every visit."""
        def work(pg):
            pg.evaluate("() => goScreen('tools')")
            pg.wait_for_selector("#cats .feat", timeout=15000)
            said = pg.eval_on_selector('#stage button[data-t="bydate"]',
                                       "e => e.textContent")
            self.assertIn("Sort into folders", said)
            self.assertIn("date", said.lower())
            self.open_tab(pg, "bydate")
            self.assertEqual(pg.eval_on_selector_all("#whatis", "e => e.length"), 0,
                             "the form is repeating what the list already said")
            # the long version is still a press away
            self.assertTrue(pg.query_selector("#form h2 .info"))
        self.page(work)

    def test_a_tool_wears_its_groups_ink_and_its_list_is_read_out(self):
        """4.0: the page a tool is on carries its group's ink, and the list
        that arrives is put into the live region a screen reader hears, in
        the words on the screen."""
        def work(pg):
            self.open_tab(pg, "previews")
            tone = pg.evaluate("() => document.body.dataset.tone")
            self.assertEqual(tone, pg.evaluate("() => sideGroup('previews').tone"))
            band = pg.eval_on_selector(
                "#form", "e => getComputedStyle(e).borderTopColor")
            self.assertNotEqual(band, pg.eval_on_selector(
                "#form", "e => getComputedStyle(e).borderBottomColor"))
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            pg.wait_for_selector("#apply .ckn", timeout=90000)
            pg.wait_for_function(
                "() => document.getElementById('said').textContent"
                ".includes('Nothing has been written yet')", timeout=5000)
            said = pg.text_content("#said")
            self.assertRegex(said, r"Create [\d,]+ previews")
            # the big count is the same number the button says
            count = pg.text_content("#apply .ckn")
            self.assertIn(count, pg.text_content("#doit"))
            # and a screen leaves its group's ink behind
            pg.evaluate("() => goScreen('home')")
            self.assertIsNone(pg.evaluate("() => document.body.dataset.tone || null"))
        self.page(work)

    def test_nothing_slides_for_anybody_who_asked_for_less_motion(self):
        def work(pg):
            pg.emulate_media(reduced_motion="reduce")
            pg.evaluate("() => goScreen('tools')")
            pg.wait_for_selector("#cats", timeout=15000)
            moving = pg.evaluate(
                "() => [...document.querySelectorAll('#stage > *')]"
                ".map(e => getComputedStyle(e).animationName)"
                ".filter(n => n !== 'none')")
            self.assertEqual(moving, [])
        self.page(work)

    def test_before_anything_is_written_the_page_says_what_will_change(self):
        """The audit's sharpest point: four hundred rows to approve and not one
        sentence saying what, how many, out of where, into where."""
        def work(pg):
            self.open_tab(pg, "previews")
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            pg.wait_for_selector("#apply", timeout=90000)
            said = pg.text_content("#apply")
            for want in ["Operation", "Create", "Out of"]:
                self.assertIn(want, said, want)
            # and the button names the operation rather than "Go ahead"
            button = pg.text_content("#doit")
            self.assertRegex(button, r"^Create [\d,]+ previews$",
                             f"the button says {button!r}")
            self.assertNotIn("Go ahead", button)
        self.page(work)

    def test_a_plan_that_finds_nothing_says_so_rather_than_drawing_nothing(self):
        """You pressed the button, the page flickered, and the only honest
        reading of that was that it had broken."""
        def work(pg):
            self.open_tab(pg, "blur")
            pg.fill("#o_folder", self.empty)
            pg.click("#go")
            pg.wait_for_function(
                "() => !document.querySelector('#lookfill')", timeout=60000)
            said = pg.text_content("#out")
            self.assertIn("Nothing to do", said)
            self.assertIn("Nothing was written", said)
        self.page(work)

    def test_the_irreversible_ones_ask_a_second_time_and_say_what_for(self):
        """Not "Are you sure?" - that asks you to confirm a question you have
        not been told the answer to. The dialog carries the verb, the number,
        where it happens and what the task says about putting it back."""
        def work(pg):
            self.open_tab(pg, "bydate")
            pg.evaluate("""() => { window.ASKED = sureAbout({
              rows: [1, 2, 3],
              impact: {verb: "Delete", unit: "folders", count: 3, risk: "high",
                       from: "/tmp/a shoot", undo: "There is no way back."}}); }""")
            pg.wait_for_selector(".sure", timeout=5000)
            said = pg.text_content(".sure .surebox")
            self.assertIn("Delete 3 folders", said)
            self.assertIn("a shoot", said)
            self.assertIn("no way back", said)
            # Cancel means nothing happens, and says so by resolving false
            # clicked through the DOM: the dialog is fixed to the window and
            # Playwright's own scroll-into-view fights with that
            pg.evaluate("""() => document.querySelector(
              '.sure button[data-a=\"0\"]').click()""")
            self.assertFalse(pg.evaluate("() => window.ASKED"))
            # and a plan that is not marked irreversible is not asked about
            self.assertTrue(pg.evaluate(
                "() => sureAbout({rows: [1], impact: {verb: 'Move'}})"))
        self.page(work)

    def test_a_run_reports_four_outcomes_and_not_just_done(self):
        """"184 done" out of 400 rows has not told you about the other 216."""
        def work(pg):
            self.open_tab(pg, "bydate")
            got = pg.evaluate("""() => {
              PLAN = {rows: [1,2,3,4,5], skipped: [["a.jpg", "no date"]],
                      impact: {count: 5}};
              return outcomeTiles({result: {done: 3, failed: 1, stats: [],
                                            details: []}});
            }""")
            self.assertIn("Done", got)
            self.assertIn("Left alone", got)
            self.assertIn("Unchanged", got)
            self.assertIn("Failed", got)
            # 3 done + 1 failed out of 5 leaves 1 untouched, and it is named
            pairs = re.findall(r"<span>.*?([A-Z][a-z ]+)</span><b>(\d+)</b>", got)
            self.assertEqual(dict((a.strip(), b) for a, b in pairs),
                             {"Done": "3", "Left alone": "1", "Unchanged": "1",
                              "Failed": "1"})
        self.page(work)

    def test_the_new_furniture_does_not_make_a_phone_scroll_sideways(self):
        def work(pg):
            # straight to the tab: on a phone the sidebar is a drawer, and
            # clicking a line inside a closed drawer is not something a person
            # does either
            pg.evaluate("() => show('previews')")
            pg.wait_for_selector("#steps", timeout=10000)
            self.assertNoSideScroll(pg, "a feature with the step strip")
            # the strip itself fits, with the step you are on keeping its words
            box = pg.eval_on_selector("#steps", "e => e.scrollWidth <= e.clientWidth")
            self.assertTrue(box, "the step strip is wider than the screen")
            words = pg.eval_on_selector("#steps li.now span",
                                        "e => getComputedStyle(e).display")
            self.assertNotEqual(words, "none",
                                "the step you are on lost its label too")
            openDrawer = pg.evaluate("() => { openDrawer(); return 1; }")
            pg.wait_for_timeout(250)
            self.assertNoSideScroll(pg, "the drawer")
        self.phone(work)

    def test_the_picker_says_which_box_it_is_filling_in(self):
        """It is a panel over the form it was opened from. Three folders deep,
        the only thing saying WHICH of a task's four folder boxes you are
        choosing for was your memory of pressing the button."""
        def work(pg):
            self.open_tab(pg, "previews")
            label = pg.evaluate(
                "() => CURRENT.options.find(o => o.name === 'folder').label")
            pg.click('#form .withbtn:has(#o_folder) button:has-text("Browse")')
            pg.wait_for_selector(".veil .pick h3", timeout=10000)
            self.assertIn(label, pg.text_content(".veil .pick h3"))
            pg.click('.veil button:has-text("Cancel")')
        self.page(work)

    def test_the_picker_walks_into_a_windows_drive(self):
        """Clicking a drive did nothing on Windows: the backslash in `C:\\`
        escaped the quote closing the onclick's string, so the click was a
        syntax error and the list never moved. The server here answers the way
        a Windows one does, so this runs on any machine."""
        drives = {
            "": {"path": "", "parent": None, "allowed": True, "folders": [
                {"name": "C:\\", "path": "C:\\", "allowed": True},
                {"name": "N:\\", "path": "N:\\", "allowed": True}]},
            "C:\\": {"path": "C:\\", "parent": "", "allowed": True, "folders": [
                {"name": "Photos", "path": "C:\\Photos", "allowed": True}]},
            "C:\\Photos": {"path": "C:\\Photos", "parent": "C:\\", "allowed": True,
                            "folders": [{"name": "Mum's", "allowed": True,
                                         "path": "C:\\Photos\\Mum's"}]},
            "C:\\Photos\\Mum's": {"path": "C:\\Photos\\Mum's", "allowed": True,
                                    "parent": "C:\\Photos", "folders": []},
        }
        asked = []

        def answer(route):
            from urllib.parse import parse_qs, urlparse
            wanted = (parse_qs(urlparse(route.request.url).query).get("path")
                      or [""])[0]
            asked.append(wanted)
            route.fulfill(content_type="application/json",
                          body=json.dumps(drives.get(wanted, {
                              "path": wanted, "parent": None, "folders": [],
                              "error": "not one of the test's folders"})))

        def work(pg):
            pg.route("**/api/browse*", answer)
            self.open_tab(pg, "previews")
            pg.fill("#o_folder", "")             # so it opens on the drives
            pg.click('#form .withbtn:has(#o_folder) button:has-text("Browse")')
            pg.wait_for_selector('#picklist button:has-text("C:")', timeout=10000)
            pg.click('#picklist button:has-text("C:")')
            pg.wait_for_function(
                "() => document.getElementById('pickat').textContent === 'C:\\\\'")
            pg.click('#picklist button:has-text("Photos")')
            pg.wait_for_function("() => pickAt === 'C:\\\\Photos'")
            pg.click('#picklist button:has-text("Mum")')
            pg.wait_for_function("() => pickAt === \"C:\\\\Photos\\\\Mum's\"")
            # and back up, all the way to the drives
            pg.click('#picklist button:has-text("up one level")')
            pg.wait_for_function("() => pickAt === 'C:\\\\Photos'")
            pg.click('#picklist button:has-text("up one level")')
            pg.click('#picklist button:has-text("up one level")')
            pg.wait_for_selector('#picklist button:has-text("N:")', timeout=5000)
            self.assertEqual(asked, ["", "C:\\", "C:\\Photos", "C:\\Photos\\Mum's",
                                     "C:\\Photos", "C:\\", ""])
            pg.click('.veil button:has-text("Cancel")')
        self.page(work)

    def test_the_rename_crumbs_open_the_folder_they_name(self):
        """Counted from the start of the path, every crumb on a Windows path
        opened the folder below the one it named, and "up" from a drive's
        first folder went to `C:` - wherever C: was last - not to `C:\\`."""
        def work(pg):
            got = pg.evaluate("""() => {
              const was = [RN.folder, window.rnGo], went = [];
              window.rnGo = p => went.push(p);
              const out = {};
              for (const f of ["C:\\\\Photos\\\\2024\\\\Trip", "C:\\\\Photos",
                               "/volume1/photos/2024/Trip"]){
                RN.folder = f;
                const box = document.createElement("div");
                box.innerHTML = rnCrumbs();
                went.length = 0;
                box.querySelectorAll("button").forEach(b => b.click());
                out[f] = [...box.querySelectorAll("button")].map(
                  (b, i) => [b.title || b.textContent.trim(), went[i]]);
              }
              [RN.folder, window.rnGo] = was;
              return out;
            }""")
            self.assertEqual(got["C:\\Photos\\2024\\Trip"], [
                ["Up one", "C:\\Photos\\2024"], ["Photos", "C:\\Photos"],
                ["2024", "C:\\Photos\\2024"], ["Trip", "C:\\Photos\\2024\\Trip"]])
            self.assertEqual(got["C:\\Photos"], [
                ["Up one", "C:\\"], ["C:", "C:\\"], ["Photos", "C:\\Photos"]])
            self.assertEqual(got["/volume1/photos/2024/Trip"][1:], [
                ["photos", "/volume1/photos"], ["2024", "/volume1/photos/2024"],
                ["Trip", "/volume1/photos/2024/Trip"]])
        self.page(work)

    # --------------------------------------------------- 3.0: the library itself

    def test_the_app_opens_on_the_photographs_not_on_a_form(self):
        """The whole shift. Until 3.0 this opened on a form with "Have a look"
        under it - a filing cabinet, not a library."""
        def work(pg):
            self.assertEqual(pg.evaluate("() => SCREEN"), "home")
            pg.wait_for_selector("#stage .bigtile", timeout=20000)
            said = pg.text_content("#stage")
            self.assertIn("Photos", said)
            # and the numbers were counted already - there is nothing to press
            self.assertRegex(said, r"Counted .*from the index")
            self.assertEqual(pg.eval_on_selector_all(
                "#stage button:has-text('Check the list')", "e => e.length"), 0)
        self.page(work)

    def test_the_grid_is_photographs_in_months_newest_first(self):
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            months = pg.eval_on_selector_all(".monthrow b", "e => e.map(x => x.textContent)")
            self.assertTrue(months, "no month headings")
            self.assertEqual(months, sorted(months, reverse=True)
                             if len(months) < 2 else months)
            shots = pg.eval_on_selector_all(".shot", "e => e.length")
            self.assertGreater(shots, 0)
            # every tile is a real thumbnail of a real file
            self.assertTrue(pg.eval_on_selector(".shot img", "e => !!e.src"))
            self.assertNoSideScroll(pg, "the photo grid")
        self.page(work)

    def test_a_filter_narrows_the_grid_and_says_so(self):
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            all_of_them = pg.eval_on_selector_all(".shot", "e => e.length")
            pg.click("#quickchips button:has-text('Videos')")
            pg.wait_for_timeout(600)
            self.assertLess(pg.eval_on_selector_all(".shot", "e => e.length"),
                            all_of_them)
            # and an empty answer says so rather than drawing nothing
            said = pg.text_content("#tiles")
            self.assertTrue(said.strip())
            pg.click("#quickchips button:has-text('All')")
            pg.wait_for_timeout(600)
            self.assertEqual(pg.eval_on_selector_all(".shot", "e => e.length"),
                             all_of_them)
        self.page(work)

    def test_tapping_a_photograph_opens_it_with_what_is_known_about_it(self):
        """The detail view is the viewer this app already had, with a panel
        beside it - one viewer, not two."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.click(".shot >> nth=0")
            pg.wait_for_selector("#viewer", timeout=10000)
            pg.wait_for_selector("#vinfo .facts", timeout=10000)
            said = pg.text_content("#vinfo")
            self.assertIn("Camera", said)
            self.assertIn("Folder", said)
            # the tabs are the four the design asked for
            tabs = pg.eval_on_selector_all(".dtabs button", "e => e.map(x => x.textContent)")
            self.assertEqual(tabs, ["Details", "Location", "Files", "History"])
            pg.click(".dtabs button:has-text('Files')")
            pg.wait_for_timeout(300)
            self.assertIn("This file", pg.text_content("#vinfo"))
            pg.click("#vclose")
        self.page(work)

    def test_selecting_photographs_offers_what_to_do_with_them(self):
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.click("#selmode")
            pg.wait_for_timeout(200)
            pg.click(".shot .tick >> nth=0")
            pg.wait_for_timeout(250)
            self.assertEqual(pg.evaluate("() => PICK.size"), 1)
            bar = pg.text_content("#picked")
            # the real name of what each one opens - "Organize" was a category
            # rather than an act, and "Develop" sounded like it changed the
            # photographs when it copies them
            for word in ["selected", "Rate", "Geotag", "Sort into folders",
                         "Send to develop", "Tools"]:
                self.assertIn(word, bar)
            # and the actions are dead until something is picked
            pg.click("#picked button:has-text('Done')")
            pg.wait_for_timeout(200)
            self.assertTrue(pg.eval_on_selector(
                "#picked .act-rate", "e => e.disabled"))
        self.page(work)

    def test_a_selection_carries_its_folders_into_the_feature(self):
        """Tasks here work on folders - that is what makes "move four hundred
        files" checkable - so the honest bridge is to carry the folders across
        and let the plan be read, not to invent a second way of writing."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("""() => {
              document.body.classList.add('picking');
              SHOTS.slice(0, 2).forEach(s => PICK.add(s.path));
              paintPicks();
            }""")
            folders = pg.evaluate("() => pickFolders()")
            self.assertTrue(folders)
            pg.click("#picked button:has-text('Sort into folders')")
            pg.wait_for_timeout(700)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "bydate")
            self.assertEqual(pg.evaluate("() => SCREEN"), "feature")
            got = pg.input_value("#o_folder")
            self.assertIn(folders[0], got)
            # and it says where the folders came from, rather than silently
            # widening what you picked
            self.assertIn("selection", pg.text_content("#followed"))
        self.page(work)

    def test_an_album_is_a_filter_and_holds_what_it_says(self):
        def work(pg):
            pg.evaluate("() => goScreen('albums')")
            pg.wait_for_selector(".albumcard", timeout=20000)
            counts = pg.eval_on_selector_all(
                ".albumcard", "e => e.map(x => x.textContent)")
            self.assertTrue(counts)
            said = pg.eval_on_selector(".albumcard .who", "e => e.textContent")
            n = int("".join(c for c in said.split("photograph")[0]
                            if c.isdigit()) or 0)
            pg.click(".albumcard >> nth=0")
            pg.wait_for_selector("#tiles", timeout=15000)
            pg.wait_for_timeout(700)
            self.assertEqual(pg.evaluate("() => TOTAL"), n,
                             "the album promised a different number")
        self.page(work)

    def test_the_tools_are_five_cards_and_automation_on_its_own(self):
        """Automation is not one of the five. It does not do anything to a
        photograph - it runs the things that do - and filing it under Maintain
        made it look like a housekeeping chore."""
        def work(pg):
            pg.evaluate("() => goScreen('tools')")
            pg.wait_for_selector("#cats .cat", timeout=15000)
            cards = pg.eval_on_selector_all("#cats .cat h3",
                                            "e => e.map(x => x.textContent)")
            self.assertEqual(cards, ["Organize", "Metadata", "Review",
                                     "Develop", "Maintain", "Automation"])
            pg.click('#stage button[data-t="cull"]')
            pg.wait_for_timeout(400)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "cull")
            self.assertIn("Cull", pg.inner_text("#form h2"))
        self.page(work)

    def test_where_you_were_is_where_you_come_back_to(self):
        def work(pg):
            pg.evaluate("() => goScreen('albums')")
            pg.wait_for_timeout(400)
            self.assertEqual(
                pg.evaluate("() => localStorage.getItem('pm-screen')"), "albums")
            pg.reload()
            pg.wait_for_function(
                "() => document.body.classList.contains('shell')", timeout=20000)
            pg.wait_for_timeout(500)
            self.assertEqual(pg.evaluate("() => SCREEN"), "albums")
        self.page(work)

    def test_a_link_to_a_feature_still_lands_on_the_feature(self):
        """An address that arrived with a tab in it was followed on purpose,
        and opening Home over the top of it would be the app deciding it knew
        better."""
        def work(pg):
            pg.goto(self.base + "#geotag")
            pg.wait_for_function(
                "() => document.body.classList.contains('shell')", timeout=20000)
            pg.wait_for_timeout(500)
            self.assertEqual(pg.evaluate("() => SCREEN"), "feature")
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "geotag")
        self.page(work)

    def test_the_library_screens_fit_a_phone(self):
        def work(pg):
            for screen in ("home", "photos", "albums", "tools"):
                pg.evaluate("(s) => goScreen(s)", screen)
                pg.wait_for_timeout(700)
                self.assertNoSideScroll(pg, screen)
            bar = pg.eval_on_selector_all("#bottom button",
                                          "e => e.map(b => b.dataset.b)")
            self.assertEqual(bar, ["home", "photos", "places", "tools", "menu"])
        self.phone(work)

    def test_compare_draws_a_grid_and_the_same_numbers_as_a_table(self):
        def work(pg):
            self.open_tab(pg, "compare")
            pg.wait_for_timeout(400)
            pg.select_option("#o_down", "year")
            pg.select_option("#o_across", "aperture")
            pg.click("#go")
            pg.wait_for_selector(".heat", timeout=90000)
            pg.wait_for_timeout(400)
            cells = pg.eval_on_selector_all(".heat .cell", "e => e.length")
            self.assertGreater(cells, 0)
            # the shading is not the only way to read it
            self.assertTrue(all(t.strip() for t in pg.eval_on_selector_all(
                ".heat .cell", "e => e.map(x => x.textContent)")))
            self.assertGreater(pg.eval_on_selector_all("#out table:not(.heat) tr",
                                                       "e => e.length"), 1)
            self.assertIn("busiest cell", pg.text_content(".heatkey"))
        self.page(work)

    # --------------------------------------------- charts that lead somewhere

    def test_a_folded_chart_names_what_is_in_the_fold_and_opens_out(self):
        """"Everything else" with no way to find out what is in it is the chart
        saying there is something there and refusing to name it."""
        def work(pg):
            self.open_tab(pg, "library")
            pg.click("#go")
            pg.wait_for_selector(".chart", timeout=90000)
            pg.wait_for_timeout(700)
            # a chart with more buckets than it draws says so and names them
            # a chart with more buckets than it draws, built here so the test
            # does not depend on how many years the fixture library happens to
            # span - the folding itself is what is being checked
            said = pg.evaluate("""() => {
              const c = {title: "Years", dim: "year", unit: "photos", show: 8,
                more: 0, rows: []};
              for (let y = 2010; y < 2025; y++)
                c.rows.push([String(y), 30 - (y - 2010), 0,
                             {since: y + "-01-01", until: y + "-12-31"}]);
              const folded = chartShown(c);
              CHARTOPEN[chartKey(c)] = true;
              const open = chartShown(c);
              CHARTOPEN[chartKey(c)] = false;
              const fold = folded.rows[folded.rows.length - 1];
              const html = barsHtml(c);
              return {before: folded.rows.length, after: open.rows.length,
                      name: fold[0], inside: (fold[4] || []).length,
                      tip: rowTip(fold, "120", 300),
                      button: html.indexOf("show all 15") >= 0}; }""")
            self.assertEqual(said["before"], 8)
            self.assertEqual(said["after"], 15)
            self.assertEqual(said["name"], "everything else")
            self.assertEqual(said["inside"], 8, "the fold names nobody")
            self.assertIn("2017", said["tip"], said["tip"])
            self.assertTrue(said["button"], "no way to open it out")
        self.page(work)

    def test_pressing_a_bucket_runs_the_search_that_lists_it(self):
        def work(pg):
            self.open_tab(pg, "library")
            pg.click("#go")
            pg.wait_for_selector(".chart", timeout=90000)
            pg.wait_for_timeout(700)
            # every clickable mark carries the search, worked out server-side
            asks = pg.eval_on_selector_all("[data-ask]", "e => e.length")
            self.assertGreater(asks, 0, "no chart leads anywhere")
            pg.eval_on_selector('.chart .brow.go', "e => e.click()")
            pg.wait_for_timeout(3500)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "search")
            # a box was filled and the search ran by itself
            filled = pg.evaluate("""() => ["since","until","camera","f_from",
              "iso_from","stars_from","located","kinds","focal_from"]
              .map(k => (document.getElementById("o_" + k) || {}).value)
              .filter(v => v)""")
            self.assertTrue(filled, "nothing was filled in")
        self.page(work)

    def test_a_bucket_no_search_can_say_is_not_clickable(self):
        """A chart that sends you to the wrong photographs is worse than one
        that does not move. "Not said" is a search now - the files that do not
        say - and only the rows no box can ask for stay still."""
        def work(pg):
            self.open_tab(pg, "library")
            pg.click("#go")
            pg.wait_for_selector(".chart", timeout=90000)
            pg.wait_for_timeout(700)
            bad = pg.evaluate("""() => {
              const rows = [];
              for (const c of PLAN.charts.charts)
                for (const r of c.rows){
                  const ask = r[3] && Object.keys(r[3]).length ? r[3] : null;
                  if (r[0] === "everything else" && ask) rows.push([c.dim, r[0]]);
                  if (r[0] === "not said" && c.dim !== "folder"
                      && !(ask && ask.missing)) rows.push([c.dim, r[0]]);
                }
              return rows; }""")
            self.assertEqual(bad, [])
        self.page(work)

    def test_pressing_not_said_lists_the_files_that_do_not_say(self):
        def work(pg):
            self.open_tab(pg, "library")
            pg.click("#go")
            pg.wait_for_selector(".chart", timeout=90000)
            pg.wait_for_timeout(700)
            # drawn here, so the test does not depend on the fixture library
            # having a frame with no aperture in it
            pg.evaluate("""() => {
              const c = {title: "Aperture", dim: "aperture", unit: "photos",
                show: 8, more: 0, rows: [["f/4", 3, 0, {f_from: 3.2}],
                ["not said", 2, 0, {missing: "aperture"}]]};
              const box = document.createElement("div");
              box.id = "unsaidtest";
              box.innerHTML = barsHtml(c);
              document.body.appendChild(box); }""")
            row = "#unsaidtest .brow.go[data-ask*='missing']"
            self.assertIn("click to list them",
                          pg.get_attribute(row, "data-tip"))
            pg.eval_on_selector(row, "e => e.click()")
            pg.wait_for_timeout(3500)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "search")
            self.assertEqual(pg.evaluate(
                "() => document.getElementById('o_missing').value"), "aperture")
        self.page(work)

    def test_pressing_everything_else_opens_the_chart_out(self):
        """No one search lists a folded tail, so pressing it shows the rows it
        held - each of which can then be pressed."""
        def work(pg):
            self.open_tab(pg, "library")
            pg.click("#go")
            pg.wait_for_selector(".chart", timeout=90000)
            pg.wait_for_timeout(700)
            said = pg.evaluate("""() => {
              const c = {title: "Folds", dim: "year", unit: "photos", show: 8,
                more: 0, rows: []};
              for (let y = 2010; y < 2025; y++)
                c.rows.push([String(y), 30 - (y - 2010), 0,
                             {since: y + "-01-01", until: y + "-12-31"}]);
              const box = document.createElement("div");
              box.id = "foldtest";
              box.innerHTML = barsHtml(c);
              document.body.appendChild(box);
              const fold = box.querySelector(".brow[data-fold]");
              const tip = fold ? fold.dataset.tip : "";
              const go = fold ? fold.classList.contains("go") : false;
              window.boardsRedraw = () => {};
              if (fold) fold.click();
              return {fold: !!fold, tip: tip, go: go,
                      open: !!CHARTOPEN[chartKey(c)]}; }""")
            self.assertTrue(said["fold"], "the folded row cannot be pressed")
            self.assertTrue(said["go"])
            self.assertIn("show them all", said["tip"])
            self.assertTrue(said["open"], "pressing it did not open the chart")
        self.page(work)

    def test_a_chart_on_home_searches_what_home_counted(self):
        """Home counts the index's roots - the library and the video tree.
        A search of the library alone said 5,000 where Home said 6,000."""
        def work(pg):
            self.open_tab(pg, "library")
            got = pg.evaluate("""() => {
              const wasS = SCREEN, wasP = PLAN, wasSums = SUMS;
              SCREEN = "home"; SUMS = {folders: ["/lib", "/clips"]};
              PLAN = {charts: {folders: ["/one/shoot"]}};
              const home = chartFolders();
              SCREEN = "feature";
              const tab = chartFolders();
              SCREEN = wasS; PLAN = wasP; SUMS = wasSums;
              return {home: home, tab: tab}; }""")
            self.assertEqual(got["home"], ["/lib", "/clips"])
            self.assertEqual(got["tab"], ["/one/shoot"])
        self.page(work)

    def test_the_found_card_holds_its_paths_once(self):
        """Six thousand paths serialised into two onclick attributes was half
        a megabyte of HTML before the card could be read."""
        def work(pg):
            self.open_tab(pg, "search")
            got = pg.evaluate("""() => {
              const rows = [];
              for (let i = 0; i < 3000; i++) rows.push({source: "/lib/a/" + i + ".jpg"});
              const html = foundCard({rows: rows});
              return {size: html.length, kept: FOUND.length,
                      uses: html.indexOf("foundToFiles(FOUND)") >= 0}; }""")
            self.assertEqual(got["kept"], 3000)
            self.assertTrue(got["uses"])
            self.assertLess(got["size"], 4000, "the paths are in the HTML")
        self.page(work)

    def test_a_long_table_is_drawn_a_few_hundred_rows_at_a_time(self):
        def work(pg):
            self.open_tab(pg, "search")
            pg.wait_for_selector("#form", timeout=15000)
            count = "() => document.querySelectorAll('#out table tr').length"
            got = pg.evaluate("""() => {
              const rows = [];
              for (let i = 0; i < 1200; i++)
                rows.push({name: i + ".jpg", source: "/lib/a/" + i + ".jpg",
                           cells: ["", "", "", ""]});
              PLAN = {task: "search", writes: false, rows: rows, stats: [],
                      notes: [], columns: ["Photograph", "Taken", "Camera",
                      "Exposure", "Marks"], impact: {count: 1200}};
              render(PLAN);
              return {rows: document.querySelectorAll('#out table tr').length,
                      more: (document.querySelector('#out .rowsmore') || {}).textContent || "",
                      head: document.querySelector('#out .card b').textContent,
                      found: (document.querySelector('#out .card .note') || {}).textContent}; }""")
            self.assertEqual(got["rows"], 501, "header and five hundred")
            self.assertIn("Show the next 500", got["more"])
            self.assertIn("500 of 1,200 drawn", got["more"])
            pg.evaluate("() => rowsMore(500)")
            self.assertEqual(pg.evaluate(count), 1001)
            pg.evaluate("() => rowsMore(0)")
            self.assertEqual(pg.evaluate(count), 1201)
            self.assertEqual(pg.evaluate(
                "() => document.querySelectorAll('#out .rowsmore').length"), 0)
            # a fresh plan starts the window again
            pg.evaluate("() => { PLAN = Object.assign({}, PLAN); render(PLAN); }")
            self.assertEqual(pg.evaluate(count), 501)
        self.page(work)

    def test_what_a_search_found_is_not_replaced_by_the_folder_read(self):
        """Opening the Files tab starts a read of the library folder; the
        matches handed over used to land on top of it with no number of their
        own, so on a big library the folder came back a second later and the
        six thousand you had searched for became every photograph you own."""
        def work(pg):
            self.open_tab(pg, "search")
            one = os.path.join(self.shoot, "plain.JPG")
            pg.evaluate("""(one) => {
              /* a slow folder read, so the race is certain rather than lucky:
                 the folder's answer arrives after the matches have landed */
              const real = window.fetch;
              window.fetch = (url, opts) => {
                if (String(url).indexOf("api/files?") === 0)
                  return new Promise(r => setTimeout(() => r(real(url, opts)), 900));
                return real(url, opts);
              };
              return foundToFiles([one]); }""", one)
            pg.wait_for_timeout(2500)
            got = pg.evaluate("""() => {
              const pane = FM.panes[FM.at];
              return {found: pane.found ? pane.found.length : null,
                      files: pane.data ? pane.data.files.length : null,
                      path: pane.path, busy: pane.busy,
                      rows: document.querySelectorAll('#fileman .fmrow').length}; }""")
            self.assertEqual(got["found"], 1, "the set was replaced by the folder")
            self.assertEqual(got["files"], 1)
            self.assertEqual(got["path"], "")
            self.assertFalse(got["busy"])
            self.assertEqual(got["rows"], 1)
        self.page(work)

    def test_the_file_manager_draws_a_few_hundred_rows_at_a_time(self):
        """A pane is redrawn on every pick, which is fine for a folder and a
        page that stops answering for a search of six thousand."""
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman", timeout=15000)
            rows = "() => document.querySelectorAll('#fileman .fmrow').length"
            got = pg.evaluate("""() => {
              const files = [];
              for (let i = 0; i < 1000; i++)
                files.push({name: "f" + String(i).padStart(4, "0") + ".txt",
                            path: "/lib/f" + i + ".txt", size: 10, when: 1.7e9,
                            kind: "other", folder: "/lib"});
              const pane = FM.panes[FM.at];
              pane.view = "list"; pane.busy = false; pane.error = "";
              pane.data = {path: "/lib", parent: "", crumbs: [], folders: [],
                           files: files, size: 10000, roots: []};
              pane.found = files.map(f => f.path); pane.shown = 0;
              drawFiles();
              return {rows: document.querySelectorAll('#fileman .fmrow').length,
                      more: (document.querySelector('#fileman .fmmore') || {}).textContent || "",
                      foot: document.querySelector('#fileman .fmfoot').textContent}; }""")
            self.assertEqual(got["rows"], 400)
            self.assertIn("Show the next 400", got["more"])
            self.assertIn("1,000 files", got["foot"], "the count is the whole")
            self.assertIn("400 drawn so far", got["foot"])
            pg.evaluate("() => fmMore(FM.at)")
            self.assertEqual(pg.evaluate(rows), 800)
            # reaching the bottom asks for the rest by itself
            pg.evaluate("""() => {
              const el = document.querySelector('#fileman .fmlist');
              el.scrollTop = el.scrollHeight;
              el.dispatchEvent(new Event('scroll')); }""")
            pg.wait_for_timeout(200)
            self.assertEqual(pg.evaluate(rows), 1000)
            self.assertEqual(pg.evaluate(
                "() => document.querySelectorAll('#fileman .fmmore').length"), 0)
            # a pick redraws only what is drawn, and keeps the window - back at
            # the top first, since standing at the bottom asks for more
            pg.evaluate("""() => {
              document.querySelector('#fileman .fmlist').scrollTop = 0;
              FM.panes[FM.at].shown = 400; drawFiles(); }""")
            pg.wait_for_timeout(200)
            pg.evaluate("() => fmToggle(FM.at, '/lib/f3.txt')")
            pg.wait_for_timeout(200)
            self.assertEqual(pg.evaluate(rows), 400)
            self.assertEqual(pg.evaluate(
                "() => document.querySelectorAll('#fileman .fmrow.on').length"), 1)
        self.page(work)

    # ------------------------------------------------ naming what a camera is

    def test_the_search_boxes_offer_what_the_library_really_holds(self):
        def work(pg):
            self.open_tab(pg, "search")
            pg.wait_for_selector("#searchbar", timeout=15000)
            pg.wait_for_timeout(300)
            self.assertGreater(pg.eval_on_selector_all(".pickrow button.pickbtn",
                                                       "e => e.length"), 1)
            pg.eval_on_selector('.pickrow button.pickbtn', "e => e.click()")
            pg.wait_for_selector(".pmenu .vopt", timeout=60000)
            said = pg.eval_on_selector_all(".pmenu .vopt",
                                           "e => e.map(x => x.textContent)")
            self.assertTrue(any("GH4" in t for t in said), said)
            pg.eval_on_selector(".pmenu .vopt", "e => e.click()")
            pg.wait_for_timeout(300)
            box = pg.eval_on_selector("#o_camera", "e => e.value")
            self.assertTrue(box)
            # the menu shows "Lumix GH4 (DMC-GH4)" so you can see which body it
            # is; the box gets something a file can actually answer
            self.assertNotIn("(", box, box)
            from core import devices
            self.assertTrue(devices.matches("DMC-GH4", box), box)
        self.page(work)

    def test_a_camera_can_be_given_a_name_and_it_sticks(self):
        def work(pg):
            self.open_tab(pg, "cameras")
            pg.wait_for_timeout(400)
            pg.click("#go")
            pg.wait_for_selector(".camname", timeout=90000)
            pg.wait_for_timeout(400)
            # the app already guesses this one, and says that it guessed
            self.assertIn("guess", pg.text_content("#out .camhow"))
            self.assertEqual(pg.eval_on_selector(".camname", "e => e.value"),
                             "Lumix GH4")
            pg.fill(".camname", "the video one")
            pg.eval_on_selector(".camname", "e => e.blur()")
            pg.wait_for_timeout(900)
            self.assertIn("you named it", pg.text_content("#out .camhow"))
            # and it is what the rest of the app calls that camera
            pg.reload()
            pg.wait_for_timeout(1200)
            self.open_tab(pg, "cameras")
            pg.click("#go")
            pg.wait_for_selector(".camname", timeout=90000)
            self.assertEqual(pg.eval_on_selector(".camname", "e => e.value"),
                             "the video one")
            # put it back: this class shares one settings file, and a name left
            # behind would follow every test that runs after this one
            pg.fill(".camname", "")
            pg.eval_on_selector(".camname", "e => e.blur()")
            pg.wait_for_timeout(700)
        self.page(work)

    # ------------------------------------------------------- 3.1: the feedback
    #
    # Everything below answers one line of the list that came back from 3.0.
    # They are browser tests because every one of them is a claim about a
    # running page - "pressing this gets you there" is not something a grep of
    # the source can hold.

    def test_the_home_screen_has_the_folders_on_it_without_being_asked(self):
        """The thing the old Library tab could say that nothing else can: which
        shoots are not finished. It used to be a minute behind a button - and it
        is the SAME TABLE, not a second one that looks like it."""
        def work(pg):
            pg.evaluate("() => goScreen('home')")
            pg.wait_for_selector("#homefolders table.tree", timeout=20000)
            rows = pg.eval_on_selector_all("#homefolders .fname a",
                                           "es => es.map(e => e.textContent.trim())")
            self.assertIn("2022", rows)
            # the Library tab's own marks, with its own three states
            pips = pg.eval_on_selector_all(
                "#homefolders .pip", "es => es.map(e => e.className)")
            self.assertTrue(pips)
            self.assertTrue(any("some" in c or "none" in c for c in pips), pips)
            # and it says where the numbers came from, and what it cannot say
            said = " ".join(pg.text_content("#homefolders").split())
            self.assertIn("Counted from the index", said)
            self.assertIn("The Library tab reads all five trees", said)
        self.page(work)

    def test_a_folder_on_the_board_opens_the_features_for_it(self):
        """Reading and acting in one gesture: the folder you spot is the folder
        the next feature opens on - exactly as on the Library tab."""
        def work(pg):
            pg.evaluate("() => goScreen('home')")
            pg.wait_for_selector("#homefolders table.tree", timeout=20000)
            pg.evaluate("""() => {
              const a = [...document.querySelectorAll('#homefolders .fname a')]
                .find(x => /Spain/.test(x.textContent));
              if (!a) throw new Error('no Spain row on the board');
              a.click();
            }""")
            pg.wait_for_timeout(700)
            self.assertTrue(pg.query_selector("#fmenu"),
                            "pressing a folder offered nothing")
            self.assertIn("Spain", pg.text_content("#fmenu"))
            # and the first thing offered is to LOOK at it, which is what you
            # wanted when you noticed the folder
            self.assertIn("Show the photos", pg.text_content("#fmenu"))
            pg.evaluate("""() => [...document.querySelectorAll('#fmenu button')]
              .find(b => /Show the photos/.test(b.textContent)).click()""")
            pg.wait_for_timeout(1200)
            self.assertEqual(pg.evaluate("() => SCREEN"), "photos")
            self.assertEqual(pg.evaluate("() => VIEWBY"), "folder")
        self.page(work)

    def test_the_board_can_be_narrowed_to_the_unfinished_ones(self):
        def work(pg):
            pg.evaluate("() => goScreen('home')")
            pg.wait_for_selector("#homefolders table.tree", timeout=20000)
            pg.evaluate("() => foldOnly('unfinished')")
            pg.wait_for_timeout(900)
            self.assertEqual(pg.evaluate("() => FONLY"), "unfinished")
            # whatever is left is still a tree: nothing indented under nothing
            bad = pg.evaluate("""() => {
              const seen = new Set();
              for (const r of (BOARD.rows || [])){
                const up = r.path.replace(/[\\/][^\\/]*$/, "");
                if (r.depth && !seen.has(up)) return r.path;
                seen.add(r.path);
              }
              return "";
            }""")
            self.assertEqual(bad, "", f"{bad} has no parent above it")
        self.page(work)

    def test_the_grid_can_be_grouped_by_folder_instead_of_by_month(self):
        """Folders is a PLACE now - the folders that are here, which you walk
        into - and the months are what you get back when you leave it."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("() => viewBy('folder')")
            pg.wait_for_selector("#folderwall .foldcard", timeout=20000)
            self.assertEqual(pg.eval_on_selector_all(".monthrow", "es => es.length"), 0,
                             "the old one-long-list folder view is still there")
            # and back again, to the months
            pg.evaluate("() => viewBy('date')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            heads = pg.eval_on_selector_all(
                ".monthrow b", "es => es.map(e => e.textContent.trim())")
            self.assertFalse(any("Spain" in h for h in heads), heads)
            self.assertTrue(pg.eval_on_selector("#wherebar", "e => e.hidden"))
        self.page(work)

    def test_the_grid_has_the_search_filters_above_it(self):
        """Six chips answered the six questions somebody asks most. The rest -
        a camera, a lens, an aperture - needed the Search tab and a round trip."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.click("#filtbtn")
            pg.wait_for_selector("#filters input, #filters select", timeout=8000)
            self.assertFalse(pg.eval_on_selector("#filters", "e => e.hidden"))
            before = pg.evaluate("() => TOTAL")
            pg.evaluate("() => { FILTER = {stars_from: 5}; loadShots(true); }")
            pg.wait_for_timeout(900)
            self.assertLess(pg.evaluate("() => TOTAL"), before)
            self.assertIn("Filters", pg.text_content("#filtbtn"))
        self.page(work)

    def test_a_place_on_the_map_shows_its_photographs_in_the_grid(self):
        """A pin that cannot be pressed is a picture of a map."""
        def work(pg):
            pg.evaluate("() => goScreen('places')")
            pg.wait_for_timeout(1200)
            pg.evaluate("() => openPlace(41.3874, 2.1686)")
            pg.wait_for_timeout(1000)
            self.assertEqual(pg.evaluate("() => SCREEN"), "photos")
            # and it is THAT place, not "everything with a location" - the
            # filter carries the pin and a radius
            got = pg.evaluate("() => FILTER")
            self.assertIn("near_lat", got)
            self.assertIn("within_km", got)
        self.page(work)

    def test_power_rename_says_which_folder_it_is_renaming_inside(self):
        """The thing that made it unusable: a table of every folder in the
        library, and no way to say "that one, and what is under it"."""
        def work(pg):
            self.open_tab(pg, "rename")
            pg.wait_for_selector(".rnwhere", timeout=20000)
            crumbs = pg.eval_on_selector_all(
                ".rncrumb", "es => es.map(e => e.textContent.trim())")
            self.assertTrue(crumbs, "no path to see or press")
            self.assertTrue(any("Photos" in c for c in crumbs), crumbs)
            # and pressing a folder in the table goes INTO it
            pg.wait_for_selector(".rnin", timeout=20000)
            pg.evaluate("() => document.querySelector('.rnin').click()")
            pg.wait_for_timeout(900)
            self.assertNotEqual(pg.eval_on_selector("#o_folder", "e => e.value"),
                                self.lib)
            self.assertTrue(pg.eval_on_selector("#o_folder", "e => e.value")
                            .startswith(self.lib))
        self.page(work)

    def test_the_viewer_opens_the_details_and_the_histogram_from_the_keyboard(self):
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            # a PHOTOGRAPH, not a clip: a clip has no exposure to show and no
            # histogram to draw, and both overlays say so by not being there
            pg.evaluate("""() => {
              const one = SHOTS.find(s => /\\.jpe?g$/i.test(s.path));
              openShot(one.path);
            }""")
            pg.wait_for_selector("#viewer", timeout=15000)
            was = pg.eval_on_selector("#vshot", "e => e.hidden")
            pg.keyboard.press("i")
            pg.wait_for_timeout(500)
            self.assertNotEqual(pg.eval_on_selector("#vshot", "e => e.hidden"), was,
                                "I did not open the details")
            pg.keyboard.press("h")
            pg.wait_for_timeout(500)
            self.assertFalse(pg.eval_on_selector("#vhist", "e => e.hidden"),
                             "H did not open the histogram")
            # and the keys are what Settings says they are, not hard-wired
            self.assertEqual(pg.evaluate("() => [KEYS.info, KEYS.histogram]"),
                             ["i", "h"])
        self.page(work)

    def test_the_people_screen_is_the_names_in_the_files(self):
        """Not faces. Nothing here looks at a face - it reads the names already
        written into the photographs as tags, which is what makes them the same
        names in Lightroom and in Synology Photos."""
        def work(pg):
            pg.evaluate("() => goScreen('people')")
            pg.wait_for_selector("#faces", timeout=20000)
            said = pg.text_content("#stage")
            self.assertIn("People", said)
            # this library has no name tags in it, and the screen says what to
            # do about that rather than drawing nothing
            self.assertTrue("No names yet" in said or pg.query_selector(".face"),
                            said[:200])
        self.page(work)

    def test_a_kept_search_is_an_album(self):
        """An album here IS a search, so a search you kept is one too - which is
        the only honest way to offer "albums on your own criteria"."""
        def work(pg):
            pg.evaluate("""async () => {
              await fetch("api/searches", {method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({name: "Five stars only",
                                      ask: {stars_to: "0"}})});
            }""")
            pg.evaluate("() => goScreen('albums')")
            pg.wait_for_selector("#albumgrid", timeout=20000)
            pg.wait_for_timeout(800)
            said = pg.text_content("#albumgrid")
            self.assertIn("Five stars only", said)
            # and put it back: this class shares one settings file, and a kept
            # search left behind follows every test that runs after this one
            pg.evaluate("""async () => {
              await fetch("api/searches", {method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({forget: "Five stars only"})});
            }""")
        self.page(work)

    def test_an_album_with_quotes_in_its_name_still_opens(self):
        """A name went into the card's onclick through esc(), which leaves an
        apostrophe alone: "Mum's" closed the string early, the click was a
        syntax error, and a name built for it ran as script. quoted() now."""
        name = 'Mum\'s "best"'
        def work(pg):
            pg.evaluate("""async (name) => {
              await fetch("api/searches", {method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({name, ask: {stars_to: "0"}})});
            }""", name)
            try:
                pg.evaluate("() => goScreen('albums')")
                pg.wait_for_selector("#albumgrid .albumcard", timeout=20000)
                pg.wait_for_timeout(800)
                pg.click(f'.albumcard:has-text("{name[:5]}")')
                pg.wait_for_timeout(500)
                self.assertEqual(pg.evaluate("() => SCREEN"), "photos")
                self.assertEqual(pg.evaluate("() => ALBUM"), "kept:" + name)
            finally:
                pg.evaluate("""async (name) => {
                  await fetch("api/searches", {method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({forget: name})});
                }""", name)
        self.page(work)

    # --------------------------------------------------------- 3.2: the second list

    def test_a_pin_is_pressed_with_a_mouse_and_not_only_with_a_finger(self):
        """It worked on a tablet and did nothing on a desktop, which is the
        signature of a handler hung on an element the map then rewrites: a mouse
        moves a pixel or two between pressing and letting go, the map repaints,
        and the button the click was going to land on no longer exists."""
        def work(pg):
            pg.evaluate("() => goScreen('places')")
            pg.wait_for_timeout(1500)
            pin = pg.query_selector(".pmpin")
            if not pin:
                self.skipTest("no located photographs in this library")
            box = pin.bounding_box()
            pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            pg.mouse.down()
            # the wobble a hand makes, which used to be enough to lose the click
            pg.mouse.move(box["x"] + box["width"] / 2 + 2,
                          box["y"] + box["height"] / 2 + 1)
            pg.mouse.up()
            pg.wait_for_timeout(900)
            self.assertEqual(pg.evaluate("() => SCREEN"), "photos")
            self.assertIn("near_lat", pg.evaluate("() => FILTER"))
        self.page(work)

    def test_but_dragging_the_map_does_not_count_as_pressing_one(self):
        def work(pg):
            pg.evaluate("() => goScreen('places')")
            pg.wait_for_timeout(1500)
            if not pg.query_selector(".pmpin"):
                self.skipTest("no located photographs in this library")
            box = pg.query_selector("#pmmap").bounding_box()
            pg.mouse.move(box["x"] + 40, box["y"] + 40)
            pg.mouse.down()
            pg.mouse.move(box["x"] + 160, box["y"] + 90, steps=8)
            pg.mouse.up()
            pg.wait_for_timeout(600)
            self.assertEqual(pg.evaluate("() => SCREEN"), "places")
        self.page(work)

    def test_one_flick_of_a_trackpad_is_not_four_zoom_levels(self):
        """A notch is 100, a trackpad sends a stream of 4s, and a level per
        event took the map from a street to a continent."""
        def work(pg):
            pg.evaluate("() => goScreen('places')")
            pg.wait_for_timeout(1500)
            if not pg.query_selector(".pmpin"):
                self.skipTest("no located photographs in this library")
            was = pg.evaluate("() => MAPAT.z")
            pg.evaluate("""() => {
              const box = document.getElementById("pmmap");
              for (let i = 0; i < 10; i++)
                box.dispatchEvent(new WheelEvent("wheel",
                  {deltaY: -4, clientX: 100, clientY: 100,
                   bubbles: true, cancelable: true}));
            }""")
            pg.wait_for_timeout(300)
            self.assertLessEqual(pg.evaluate("() => MAPAT.z") - was, 1,
                                 "a flick moved more than one level")
        self.page(work)

    def test_there_is_a_way_back_to_where_you_just_were(self):
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("() => goScreen('albums')")
            pg.wait_for_timeout(700)
            back = pg.query_selector("#back")
            self.assertFalse(pg.eval_on_selector("#back", "e => e.hidden"),
                             "no way back")
            back.click()
            pg.wait_for_timeout(900)
            self.assertEqual(pg.evaluate("() => SCREEN"), "photos")
        self.page(work)

    def test_back_comes_out_of_a_feature_onto_the_screen_that_opened_it(self):
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("() => openFeature('tags')")
            pg.wait_for_timeout(900)
            self.assertEqual(pg.evaluate("() => SCREEN"), "feature")
            pg.click("#back")
            pg.wait_for_timeout(900)
            self.assertEqual(pg.evaluate("() => SCREEN"), "photos")
        self.page(work)

    def test_and_it_carries_the_filters_you_had(self):
        """Going back to "Photos" is not going back if the four things you had
        narrowed it to have been forgotten on the way."""
        def work(pg):
            pg.evaluate("() => goScreen('photos', {filter: {stars_from: 5}})")
            pg.wait_for_timeout(900)
            pg.evaluate("() => goScreen('tools')")
            pg.wait_for_timeout(600)
            pg.click("#back")
            pg.wait_for_timeout(900)
            self.assertEqual(pg.evaluate("() => FILTER.stars_from"), 5)
        self.page(work)

    def test_the_browsers_own_back_does_the_same_one_step(self):
        """A page with a back arrow of its own that ignores the one in the
        chrome is worse than a page with neither."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("() => goScreen('places')")
            pg.wait_for_timeout(800)
            pg.go_back()
            pg.wait_for_timeout(1000)
            self.assertEqual(pg.evaluate("() => SCREEN"), "photos")
        self.page(work)

    def test_there_is_nothing_to_go_back_to_when_you_arrive(self):
        def work(pg):
            self.assertTrue(pg.eval_on_selector("#back", "e => e.hidden"))
        self.page(work)

    def test_an_album_can_be_made_from_criteria_on_the_albums_screen(self):
        """"Albums on your own criteria" means a button on Albums that asks for
        them - not a search kept from somewhere else that happens to appear."""
        def work(pg):
            pg.evaluate("() => goScreen('albums')")
            pg.wait_for_selector("#albumgrid", timeout=20000)
            pg.evaluate("() => albumMake()")
            pg.wait_for_selector("#albumasks", timeout=8000)
            pg.fill("#albumname", "Wide and rated")
            pg.eval_on_selector("#albumasks [data-a='stars_from']",
                                "e => { e.value = '1'; }")
            # it says how many before it is kept - a criterion you meant, rather
            # than a typo with a name on it
            pg.evaluate("() => albumTry()")
            pg.wait_for_timeout(700)
            self.assertRegex(pg.text_content("#albumsays"), r"\d+ photos? answers? to that")
            pg.evaluate("() => albumKeep('')")
            pg.wait_for_timeout(1200)
            self.assertIn("Wide and rated", pg.text_content("#albumgrid"))
            # and opening it shows what it promised
            pg.evaluate("() => openAlbum('kept:Wide and rated')")
            pg.wait_for_timeout(1200)
            self.assertEqual(pg.evaluate("() => SCREEN"), "photos")
            # then take it away again, so the next test starts where this did
            pg.evaluate("() => albumForget('Wide and rated', true)")
            pg.wait_for_timeout(500)
        self.page(work)

    def test_an_album_you_made_can_be_taken_away_again(self):
        def work(pg):
            pg.evaluate("""async () => {
              await fetch("api/searches", {method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({name: "Throwaway", ask: {stars_to: "0"}})});
            }""")
            pg.evaluate("() => goScreen('albums')")
            pg.wait_for_selector("#albumgrid .albumcard", timeout=20000)
            pg.wait_for_timeout(600)
            self.assertIn("Throwaway", pg.text_content("#albumgrid"))
            # every album has a cross now - a built-in one is put away rather
            # than forgotten, because the question is this app's, not yours
            crosses = pg.eval_on_selector_all(".albumx", "es => es.length")
            self.assertEqual(crosses,
                             pg.eval_on_selector_all(".albumcard", "es => es.length"))
            pg.evaluate("() => albumForget('Throwaway', true)")
            pg.wait_for_timeout(400)
            pg.evaluate("() => drawAlbums()")
            pg.wait_for_timeout(900)
            self.assertNotIn("Throwaway", pg.text_content("#albumgrid"))
        self.page(work)

    def test_a_folder_can_be_left_out_of_the_photos_screen(self):
        """And it is a VIEW, not an exclusion: the folder is still indexed, so
        the library's own count does not change when it goes."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            whole = pg.evaluate("() => TOTAL")
            pg.evaluate("() => viewBy('folder')")
            pg.wait_for_selector("#folderwall .foldcard", timeout=20000)
            folder = pg.evaluate("() => WALL.folders[0].path")
            gone = pg.evaluate("() => WALL.folders[0].photos + WALL.folders[0].videos")
            # it is offered on the card itself, which is where you are when you
            # decide a folder is cluttering the screen
            pg.evaluate("() => document.querySelector('.foldmore').click()")
            pg.wait_for_selector(".pmenu .vopt", timeout=10000)
            self.assertIn("Leave out of Photos", pg.text_content(".pmenu"))
            pg.evaluate("() => closePageMenu()")
            pg.evaluate("(f) => hideFolder(f)", folder)
            pg.wait_for_timeout(1200)
            pg.evaluate("() => viewBy('date')")
            pg.wait_for_timeout(1200)
            self.assertEqual(pg.evaluate("() => TOTAL"), whole - gone)
            self.assertFalse(pg.eval_on_selector("#hidebtn", "e => e.hidden"))
            # the index still has them: this is about the screen, nothing else
            state = pg.evaluate("""async () => (await (await fetch("api/index")).json())""")
            self.assertGreaterEqual(state["photos"], whole)
            # and it can be undone from the chip
            pg.evaluate("() => sendHidden([])")
            pg.wait_for_timeout(1200)
            self.assertEqual(pg.evaluate("() => TOTAL"), whole)
            self.assertTrue(pg.eval_on_selector("#hidebtn", "e => e.hidden"))
        self.page(work)

    def test_settings_is_a_group_of_its_own_and_not_in_the_tools(self):
        """"Where things are and what they mean" is not a tool. It used to be a
        block stuck on the end of All tools, which made that list something you
        had to read twice."""
        def work(pg):
            pg.evaluate("() => goScreen('tools')")
            pg.wait_for_selector("#cats .cat", timeout=15000)
            said = pg.text_content("#cats")
            self.assertNotIn("Camera names", said)
            self.assertNotIn("Chart bands", said)
            # and pressing Settings gives the same kind of page the others do:
            # every feature, with its icon and a line about what it does
            pg.evaluate("() => goScreen('tools', {fam: 'settings'})")
            pg.wait_for_selector("#cats .cat", timeout=15000)
            rows = pg.eval_on_selector_all("#cats .list button[data-t]",
                                           "es => es.map(e => e.dataset.t)")
            self.assertIn("setup", rows)
            self.assertIn("cameras", rows)
            lines = pg.eval_on_selector_all(
                "#cats .list button[data-t] .ftext span",
                "es => es.map(e => e.textContent.trim())")
            self.assertTrue(lines and all(lines), lines)
            icons = pg.eval_on_selector_all("#cats .list button[data-t] svg",
                                            "es => es.length")
            self.assertGreaterEqual(icons, len(rows))
        self.page(work)

    def test_the_nas_tools_are_one_line(self):
        """Reindex and Permissions only mean something on a NAS, so they sit
        behind one NAS line beside Setup, with their own two under it while
        you are in one - and the rail and the Settings card list that one line
        rather than the two."""
        def work(pg):
            pg.evaluate("() => openFeature('setup')")
            pg.wait_for_selector("#toolside .siderow", timeout=10000)
            row = pg.eval_on_selector_all("#toolside .siderow",
                                          "es => es.map(e => e.textContent.trim())")
            self.assertIn("NAS", row)
            self.assertNotIn("Reindex", row)
            self.assertNotIn("Permissions", row)
            self.assertFalse(pg.query_selector("#toolside .siderow.sub"))
            pg.click('#toolside .siderow[data-g="nas"]')
            pg.wait_for_selector("#toolside .siderow.sub", timeout=10000)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "reindex")
            under = pg.eval_on_selector_all("#toolside .siderow.sub",
                                            "es => es.map(e => e.textContent.trim())")
            self.assertEqual(under, ["Reindex", "Permissions"])
            pg.click('#toolside .siderow.sub[data-t="permissions"]')
            pg.wait_for_timeout(500)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "permissions")
            # the NAS line stays lit while you are inside it
            lit = pg.eval_on_selector_all("#toolside .siderow.on:not(.sub)",
                                          "es => es.map(e => e.textContent.trim())")
            self.assertEqual(lit, ["NAS"])
            pg.evaluate("() => { RAILFAM = 'settings'; drawRail(); }")
            rail = pg.eval_on_selector_all('#rail .railkids button',
                                           "es => es.map(e => e.textContent.trim())")
            self.assertIn("NAS", rail)
            self.assertNotIn("Permissions", rail)
        self.page(work)

    def test_the_guide_lights_the_feature_in_the_rail(self):
        """It was written for the old sidebar, so in the library every page
        about a feature lit nothing at all. It opens the group now and lights
        the line."""
        def work(pg):
            pg.evaluate("() => goScreen('home')")
            pg.wait_for_timeout(400)
            pg.evaluate("""() => { guideOpen();
              guideGo(GUIDE.findIndex(g => g.open === 'geotag')); }""")
            pg.wait_for_timeout(600)
            self.assertTrue(pg.evaluate("() => !document.getElementById('gspot').hidden"))
            ring = pg.evaluate("""() => {
              const r = document.getElementById('gspot').getBoundingClientRect();
              const e = document.querySelector('#rail .railkids [data-t="geotag"]')
                .getBoundingClientRect();
              return Math.abs(r.top + 5 - e.top) < 3 && Math.abs(r.left + 5 - e.left) < 3;
            }""")
            self.assertTrue(ring, "the ring is not round the feature in the rail")
            pg.evaluate("() => guideClose()")
        self.page(work)

    def test_and_it_is_reachable_from_the_rail(self):
        def work(pg):
            pg.evaluate("() => goScreen('home')")
            pg.wait_for_timeout(600)
            hit = pg.query_selector('#rail [data-fam="settings"]')
            self.assertTrue(hit, "no Settings group in the rail")
            hit.click()
            pg.wait_for_timeout(600)
            kids = pg.eval_on_selector_all('#rail .railkids button[data-t]',
                                           "es => es.map(e => e.dataset.t)")
            self.assertIn("password", kids)
        self.page(work)

    def test_the_tools_can_be_grouped_the_way_you_want_them(self):
        """The grouping this app ships with is a good default and a bad rule."""
        def work(pg):
            pg.evaluate("() => goScreen('tools')")
            pg.wait_for_selector("#cats .cat", timeout=15000)
            pg.click("#arrbtn")
            pg.wait_for_selector(".arrcard", timeout=10000)
            # a group of my own, with one feature moved into it
            pg.evaluate("() => arrNew()")
            pg.wait_for_timeout(300)
            n = pg.evaluate("() => ARR.groups.length")
            pg.evaluate("(n) => arrName(n - 1, 'My week')", n)
            pg.evaluate("(n) => arrPut('geotag', String(n - 1))", n)
            pg.wait_for_timeout(300)
            # and one I never use, put away
            pg.evaluate("() => arrHide('duplicates')")
            pg.wait_for_timeout(300)
            pg.evaluate("() => arrSave()")
            pg.wait_for_timeout(1500)
            cards = pg.eval_on_selector_all("#cats .cat h3",
                                            "es => es.map(e => e.textContent)")
            self.assertIn("My week", cards)
            # geotag is in it, under the name the rest of the app calls it by
            moved = pg.evaluate("""() => {
              const card = [...document.querySelectorAll('#cats .cat')]
                .find(c => /My week/.test(c.textContent));
              return [...card.querySelectorAll('button[data-t]')]
                .map(b => b.dataset.t);
            }""")
            self.assertEqual(moved, ["geotag"])
            self.assertNotIn("Find duplicates", pg.text_content("#cats"))
            # the rail follows the same arrangement, because it is one list
            rail = pg.eval_on_selector_all("#rail .fam span:first-of-type",
                                           "es => es.map(e => e.textContent.trim())")
            self.assertIn("My week", rail)
            # and it survives a reload - it is kept on the NAS, not in a browser
            pg.reload()
            pg.wait_for_function("() => document.body.classList.contains('shell')",
                                 timeout=20000)
            pg.evaluate("() => goScreen('tools')")
            pg.wait_for_selector("#cats .cat", timeout=15000)
            self.assertIn("My week", pg.text_content("#cats"))
            # put it back, so the next test gets the app this one found
            pg.evaluate("""async () => {
              await fetch("api/toolgroups", {method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({reset: true})});
            }""")
            pg.wait_for_timeout(500)
        self.page(work)

    def test_a_feature_put_away_is_away_not_gone(self):
        def work(pg):
            pg.evaluate("""async () => {
              await fetch("api/toolgroups", {method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({groups: [], hidden: ["duplicates"]})});
            }""")
            pg.wait_for_timeout(400)
            # hidden with no groups of your own means the built-in five, minus
            # the one put away
            got = pg.evaluate("""async () =>
              (await (await fetch("api/toolgroups")).json())""")
            self.assertIn("duplicates", got["hidden"])
            # it still exists and still runs: it is a list it is out of
            there = pg.evaluate("() => !!byName('duplicates')")
            self.assertTrue(there)
            pg.evaluate("""async () => {
              await fetch("api/toolgroups", {method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({reset: true})});
            }""")
        self.page(work)

    def test_a_tool_is_dragged_to_another_group_or_into_the_bin(self):
        """A drop-down per tool was forty drop-downs. Picking one up and putting
        it where it goes is the move people expected, so it is the move; the
        Bin is where the ones never used go, out of every list."""
        def drag(pg, what, to):
            a = pg.locator(what).first.bounding_box()
            b = pg.locator(to).first.bounding_box()
            pg.mouse.move(a["x"] + a["width"] / 2, a["y"] + a["height"] / 2)
            pg.mouse.down()
            pg.mouse.move(a["x"] + a["width"] / 2 + 10, a["y"] + a["height"] / 2 + 10,
                          steps=3)
            pg.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, steps=12)
            pg.mouse.up()
            pg.wait_for_timeout(300)

        def work(pg):
            pg.evaluate("() => goScreen('tools')")
            pg.wait_for_selector("#cats .cat", timeout=15000)
            pg.click("#arrbtn")
            pg.wait_for_selector(".arrcard", timeout=10000)
            home = pg.evaluate("() => arrWhere('geotag')")
            other = pg.evaluate("""(home) => String(ARR.groups.findIndex(
                (g, i) => String(i) !== home && g.tasks.length > 1))""", home)
            # into another group, landing before the second tool in it
            drag(pg, '.arrrow[data-name="geotag"] .arrwhat',
                 f'.arrgroup[data-drop="{other}"] .arrrow:nth-child(2)')
            self.assertEqual(pg.evaluate("() => arrWhere('geotag')"), other)
            self.assertEqual(pg.evaluate(
                "(g) => ARR.groups[+g].tasks.indexOf('geotag')", other), 1)
            # and one into the Bin, whose empty space is a place to drop
            drag(pg, '.arrrow[data-name="duplicates"] .arrwhat',
                 '.arrgroup.bin .arrempty')
            self.assertEqual(pg.evaluate("() => ARR.hidden"), ["duplicates"])
            # a press on a handle without moving is not a move
            pg.click('.arrrow[data-name="bydate"] .arrgrip')
            self.assertNotEqual(pg.evaluate("() => arrWhere('bydate')"), "bin")
            # Done keeps it, rather than throwing away what was dragged about
            pg.click("#arrbtn")
            pg.wait_for_timeout(1500)
            got = pg.evaluate("""async () =>
              (await (await fetch("api/toolgroups")).json())""")
            self.assertEqual(got["hidden"], ["duplicates"])
            self.assertIn("geotag", got["groups"][int(other)]["tasks"])
            self.assertNotIn("Find duplicates", pg.text_content("#cats"))
            # the Tools screen says something is in the Bin, and opens it
            pg.wait_for_selector("#toolbin:not([hidden])", timeout=5000)
            pg.click("#toolbin .fchip")
            pg.wait_for_selector('.arrgroup.bin .arrrow[data-name="duplicates"]',
                                 timeout=10000)
            # out of the Bin again from the keyboard, on the handle
            pg.focus('.arrgroup.bin .arrrow[data-name="duplicates"] .arrgrip')
            pg.keyboard.press("ArrowLeft")
            self.assertNotEqual(pg.evaluate("() => arrWhere('duplicates')"), "bin")
            pg.evaluate("""async () => {
              await fetch("api/toolgroups", {method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({reset: true})});
            }""")
            pg.wait_for_timeout(500)
        # tall enough that the Bin is on screen without scrolling to it
        self.page(work, viewport={"width": 1440, "height": 2400})

    # ---------------------------------------------------------- 3.3: the third list

    def test_the_side_panel_follows_the_photograph(self):
        """It was told what to show once, when the viewer opened, so swiping to
        the next frame left the previous one's details on screen under the right
        picture - which does not look broken, it looks like the answer."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("() => document.querySelector('#tiles .shot').click()")
            pg.wait_for_selector("#viewer", timeout=15000)
            pg.evaluate("() => infoOpen(true)")
            pg.wait_for_timeout(900)
            first = pg.evaluate("() => INFO.path")
            self.assertTrue(first)
            said = pg.text_content("#vinfo")
            self.assertIn(os.path.basename(first), said)
            pg.evaluate("() => viewerStep(1)")
            pg.wait_for_timeout(1200)
            now = pg.evaluate("() => viewerPath()")
            self.assertNotEqual(now, first)
            self.assertEqual(pg.evaluate("() => INFO.path"), now,
                             "the panel is still on the photograph before")
            self.assertIn(os.path.basename(now), pg.text_content("#vinfo"))
            self.assertNotIn(os.path.basename(first), pg.text_content("#vinfo"))
        self.page(work)

    def test_and_a_slow_answer_for_one_never_lands_on_another(self):
        """Two photographs in quick succession: whichever reply arrives last, the
        panel has to be showing the one on screen."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("() => document.querySelector('#tiles .shot').click()")
            pg.wait_for_selector("#viewer", timeout=15000)
            pg.evaluate("() => infoOpen(true)")
            pg.wait_for_timeout(600)
            pg.evaluate("() => { viewerStep(1); viewerStep(1); viewerStep(-1); }")
            pg.wait_for_timeout(1500)
            self.assertEqual(pg.evaluate("() => INFO.path"),
                             pg.evaluate("() => viewerPath()"))
        self.page(work)

    def test_the_colour_meanings_page_is_in_colour(self):
        """Five identical grey boxes, one per colour, is a page you have to read
        to use. With the colours on it you find the row you meant."""
        def work(pg):
            self.open_tab(pg, "labels")
            pg.wait_for_selector("#form fieldset", timeout=15000)
            tints = pg.eval_on_selector_all("#form fieldset.tinted",
                                            "es => es.map(e => e.className)")
            for colour in ("red", "yellow", "green", "blue", "purple"):
                self.assertTrue(any(f"t-{colour}" in c for c in tints),
                                f"{colour} has no colour on it: {tints}")
            swatches = pg.eval_on_selector_all("#form legend .cswatch",
                                               "es => es.length")
            self.assertGreaterEqual(swatches, 5)
            # and the swatch is a real colour, not a grey box
            shade = pg.eval_on_selector("#form legend .cswatch.c-red",
                                        "e => getComputedStyle(e).backgroundColor")
            self.assertNotIn(shade, ("rgba(0, 0, 0, 0)", "transparent"))
        self.page(work)

    def test_the_album_criteria_are_menus_of_what_the_library_holds(self):
        """Typing a camera's name from memory is how somebody searches a library
        of DMC-GH4 files for DMC-GH5 and concludes there is nothing there."""
        def work(pg):
            pg.evaluate("() => goScreen('albums')")
            pg.wait_for_selector("#albumgrid", timeout=20000)
            pg.evaluate("() => albumMake()")
            pg.wait_for_selector("#albumasks", timeout=8000)
            pg.wait_for_timeout(500)
            kinds = pg.eval_on_selector_all(
                "#albumasks [data-a='camera'], #albumasks [data-a='lens'],"
                " #albumasks [data-a='kinds'], #albumasks [data-a='colour']",
                "es => es.map(e => e.tagName)")
            self.assertEqual(kinds, ["SELECT"] * 4, kinds)
            # and the cameras offered are the ones in the files, as they spell
            # themselves - with the name you gave the camera where there is one
            offered = pg.eval_on_selector_all(
                "#albumasks [data-a='camera'] option", "es => es.map(e => e.value)")
            self.assertIn("", offered)               # "any"
            self.assertTrue(len(offered) > 1, offered)
            cams = pg.evaluate("""async () =>
              (await (await fetch("api/choices")).json()).camera.map(c => c.name)""")
            for one in cams:
                self.assertIn(one, offered)
            # picking one narrows the album to it
            pg.eval_on_selector("#albumasks [data-a='camera']",
                                "(e, v) => { e.value = v; }", cams[0])
            self.assertEqual(pg.evaluate("() => albumAsk().camera"), cams[0])
        self.page(work)

    def test_and_so_are_the_filters_over_the_grid(self):
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.click("#filtbtn")
            pg.wait_for_selector("#filters .filtgrid", timeout=8000)
            pg.wait_for_timeout(400)
            tag = pg.eval_on_selector("#filters [data-f='camera']", "e => e.tagName")
            self.assertEqual(tag, "SELECT")
            # a value that is set but no longer in the library stays on the menu
            # rather than quietly becoming "any"
            pg.evaluate("() => { FILTER = {camera: 'A CAMERA THAT WENT'};"
                        " document.getElementById('filters').hidden = true;"
                        " filterPanel(); }")
            pg.wait_for_timeout(600)
            self.assertEqual(
                pg.eval_on_selector("#filters [data-f='camera']", "e => e.value"),
                "A CAMERA THAT WENT")
            pg.evaluate("() => { FILTER = {}; loadShots(true); }")
        self.page(work)

    def test_a_built_in_album_can_be_put_away_and_asked_again(self):
        """They are questions this app thinks are worth asking, which is not the
        same as thinking you should be asked them - a library with no video in
        it has a Videos album saying nothing."""
        def work(pg):
            pg.evaluate("() => goScreen('albums')")
            pg.wait_for_selector("#albumgrid .albumcard", timeout=20000)
            pg.wait_for_timeout(400)
            was = pg.eval_on_selector_all(".albumcard", "es => es.length")
            self.assertGreater(was, 1)
            key = pg.evaluate("() => ALBUMS[0].key")
            title = pg.evaluate("() => ALBUMS[0].title")
            pg.evaluate("(k) => albumAway(k)", key)
            pg.wait_for_timeout(1200)
            self.assertEqual(pg.eval_on_selector_all(".albumcard", "es => es.length"),
                             was - 1)
            # it is named on the line underneath, not simply gone
            line = pg.text_content("#albumaway")
            self.assertIn(title, line)
            # and nothing was deleted - asking it again brings it straight back
            pg.evaluate("(k) => albumBack(k)", key)
            pg.wait_for_timeout(1200)
            self.assertEqual(pg.eval_on_selector_all(".albumcard", "es => es.length"),
                             was)
            self.assertTrue(pg.eval_on_selector("#albumaway", "e => e.hidden"))
        self.page(work)

    def test_and_it_stays_away_across_a_reload(self):
        def work(pg):
            pg.evaluate("() => goScreen('albums')")
            pg.wait_for_selector("#albumgrid .albumcard", timeout=20000)
            pg.wait_for_timeout(400)
            key = pg.evaluate("() => ALBUMS[0].key")
            pg.evaluate("(k) => albumAway(k)", key)
            pg.wait_for_timeout(1000)
            pg.reload()
            pg.wait_for_function("() => document.body.classList.contains('shell')",
                                 timeout=20000)
            pg.evaluate("() => goScreen('albums')")
            pg.wait_for_selector("#albumgrid", timeout=20000)
            pg.wait_for_timeout(900)
            self.assertNotIn(key, pg.evaluate("() => ALBUMS.map(a => a.key)"))
            pg.evaluate("() => sendAway([])")
            pg.wait_for_timeout(700)
        self.page(work)

    def test_the_location_timeline_offers_both_sources_and_both_formats(self):
        def work(pg):
            self.open_tab(pg, "timeline")
            pg.wait_for_selector("#form", timeout=15000)
            said = pg.text_content("#form")
            self.assertIn("Use your photos", said)
            self.assertIn("Use the imported Timeline", said)
            self.assertIn("GeoJSON", said)
            self.assertIn("CSV", said)
            pg.click("#go")
            pg.wait_for_selector("#out .card", timeout=90000)
            pg.wait_for_timeout(500)
            out = pg.text_content("#out")
            # it says what it found in each record, before writing anything
            self.assertIn("Together, without repeats", out)
            # and with nowhere to export to, it says so rather than failing
            self.assertIn("export", out.lower())
        self.page(work)

    # ---------------------------------------------------------- 3.4: the review

    def test_collapsing_a_level_on_the_home_board_folds_the_home_board(self):
        """The same table draws the Library tab and the folder board on Home.
        Folding used to redraw whichever feature's plan was last made - which on
        Home is either nothing at all or somebody else's rows."""
        def work(pg):
            pg.evaluate("() => goScreen('home')")
            pg.wait_for_selector("#homefolders table.tree", timeout=20000)
            before = pg.eval_on_selector_all("#homefolders tbody tr", "es => es.length")
            self.assertGreater(before, 1)
            pg.evaluate("() => depthTo(0)")
            pg.wait_for_timeout(400)
            after = pg.eval_on_selector_all("#homefolders tbody tr", "es => es.length")
            self.assertLess(after, before, "collapsing did nothing")
            self.assertGreater(after, 0, "collapsing emptied the board")
            # and the rows that are left are still the folder board's own
            said = pg.text_content("#homefolders")
            self.assertIn("Counted from the index", " ".join(said.split()))
            pg.evaluate("() => depthTo(99)")
            pg.wait_for_timeout(400)
            self.assertEqual(
                pg.eval_on_selector_all("#homefolders tbody tr", "es => es.length"),
                before)
        self.page(work)

    def test_and_a_twisty_on_the_home_board_folds_that_folder(self):
        def work(pg):
            pg.evaluate("() => goScreen('home')")
            pg.wait_for_selector("#homefolders table.tree", timeout=20000)
            before = pg.eval_on_selector_all("#homefolders tbody tr", "es => es.length")
            pg.evaluate("() => document.querySelector('#homefolders .twist').click()")
            pg.wait_for_timeout(400)
            self.assertLess(
                pg.eval_on_selector_all("#homefolders tbody tr", "es => es.length"),
                before)
        self.page(work)

    def test_the_reading_line_is_only_there_while_it_is_reading(self):
        """Every pass walks the library to see what changed; on an unchanged
        library that opens no files at all. Saying "Reading your library" for it
        every minute is how the line that matters stops being read."""
        def work(pg):
            pg.evaluate("() => goScreen('home')")
            pg.wait_for_selector("#homefolders", timeout=20000)
            pg.wait_for_timeout(600)
            self.assertTrue(pg.eval_on_selector("#idxbar", "e => e.hidden"),
                            "it says it is reading when it is not")
            # it appears when there is really something being read
            pg.evaluate("""() => { IDX = Object.assign({}, IDX,
              {building: true, reading: 12, done: 12, total: 400});
              drawIndexing(); }""")
            pg.wait_for_timeout(200)
            self.assertFalse(pg.eval_on_selector("#idxbar", "e => e.hidden"))
            # ...and a pass that is only checking says nothing
            pg.evaluate("""() => { IDX = Object.assign({}, IDX,
              {building: true, reading: 0, done: 0, total: 400});
              drawIndexing(); }""")
            pg.wait_for_timeout(200)
            self.assertTrue(pg.eval_on_selector("#idxbar", "e => e.hidden"))
        self.page(work)

    def test_a_clip_plays_in_the_viewer_rather_than_sitting_there(self):
        """It used to show the clip's thumbnail - a still frame with a play
        triangle drawn on it - and pressing it did nothing at all."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            opened = pg.evaluate("""() => {
              const one = SHOTS.find(s => /\\.webm$/i.test(s.path));
              if (!one) return "";
              openShot(one.path);
              return one.path;
            }""")
            if not opened:
                self.skipTest("no clip in this library")
            pg.wait_for_selector("#viewer", timeout=15000)
            pg.wait_for_timeout(900)
            # a real player, with the controls a player has
            self.assertFalse(pg.eval_on_selector("#vvid", "e => e.hidden"))
            self.assertTrue(pg.eval_on_selector("#vvid", "e => e.controls"))
            self.assertTrue(pg.eval_on_selector("#vimg", "e => e.hidden"))
            src = pg.eval_on_selector("#vvid", "e => e.getAttribute('src')")
            self.assertIn("api/video", src)
            # and the still frame is the poster, so there is a picture at once
            self.assertTrue(pg.eval_on_selector("#vvid", "e => !!e.poster"))
            # moving on stops it - a clip playing under the next photograph is
            # the kind of thing that makes an app feel haunted
            pg.evaluate("() => viewerStep(1)")
            pg.wait_for_timeout(800)
            self.assertTrue(pg.eval_on_selector("#vvid", "e => e.hidden"))
            self.assertTrue(pg.eval_on_selector("#vvid", "e => !e.getAttribute('src')"))
        self.page(work)

    def test_and_the_overlays_a_clip_cannot_have_are_disabled_not_hidden(self):
        """A button that vanishes teaches that the app is different on
        different photographs, and a person wonders where it went."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            got = pg.evaluate("""() => {
              const one = SHOTS.find(s => /\\.webm$/i.test(s.path));
              if (!one) return "";
              openShot(one.path); return one.path;
            }""")
            if not got:
                self.skipTest("no clip in this library")
            pg.wait_for_selector("#viewer", timeout=15000)
            pg.wait_for_timeout(800)
            for which in ("#vhistb", "#vshotb"):
                self.assertTrue(pg.eval_on_selector(which, "e => e.disabled"), which)
                self.assertFalse(pg.eval_on_selector(which, "e => e.hidden"), which)
                self.assertIn("video", pg.eval_on_selector(which, "e => e.title"))
            # and on a photograph they work again
            pg.evaluate("""() => {
              const one = SHOTS.find(s => /\\.jpe?g$/i.test(s.path));
              openShot(one.path);
            }""")
            pg.wait_for_timeout(900)
            self.assertFalse(pg.eval_on_selector("#vhistb", "e => e.disabled"))
        self.page(work)

    def test_and_the_server_will_stream_a_part_of_it(self):
        """Which is what lets a browser start playing at once and scrub."""
        def work(pg):
            got = pg.evaluate("""async () => {
              const one = (await (await fetch("api/timeline?limit=500")).json())
                .items.find(i => /\\.webm$/i.test(i.path));
              if (!one) return null;
              const r = await fetch("api/video?path=" + encodeURIComponent(one.path),
                                    {headers: {Range: "bytes=0-99"}});
              return {status: r.status, range: r.headers.get("Content-Range"),
                      accepts: r.headers.get("Accept-Ranges")};
            }""")
            if got is None:
                self.skipTest("no clip in this library")
            self.assertEqual(got["status"], 206)
            self.assertTrue(got["range"].startswith("bytes 0-99/"))
            self.assertEqual(got["accepts"], "bytes")
        self.page(work)

    def test_a_format_no_browser_plays_says_so_instead_of_a_black_rectangle(self):
        """MTS is what a camcorder writes and no browser has ever played it. A
        player that simply shows black for it reads as a broken app."""
        def work(pg):
            said = pg.evaluate("() => cannotPlay('/x/holiday.MTS')")
            self.assertIn("No browser plays MTS", said)
            self.assertIn("untouched", said)
            # and one this browser in particular cannot decode says that instead
            quiet = pg.evaluate("() => cannotPlay('/x/holiday.webm')")
            self.assertEqual(quiet, "")
        self.page(work)

    def test_space_plays_and_pauses_but_the_arrows_still_move(self):
        """A left arrow that sometimes changes photograph and sometimes rewinds
        four seconds is worse than either."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            got = pg.evaluate("""() => {
              const one = SHOTS.find(s => /\\.webm$/i.test(s.path));
              if (!one) return "";
              openShot(one.path);
              return one.path;
            }""")
            if not got:
                self.skipTest("no clip in this library")
            pg.wait_for_selector("#vvid", timeout=15000)
            pg.wait_for_timeout(1200)
            self.assertTrue(pg.eval_on_selector("#vvid", "e => e.paused"))
            pg.keyboard.press(" ")
            pg.wait_for_timeout(700)
            self.assertFalse(pg.eval_on_selector("#vvid", "e => e.paused"),
                             "space did not start it")
            pg.keyboard.press(" ")
            pg.wait_for_timeout(500)
            self.assertTrue(pg.eval_on_selector("#vvid", "e => e.paused"))
            # the arrow still moves to the next photograph
            pg.keyboard.press("ArrowRight")
            pg.wait_for_timeout(700)
            self.assertNotEqual(pg.evaluate("() => viewerPath()"), got)
        self.page(work)

    def test_a_feature_can_be_put_on_the_main_list(self):
        """Five screens and forty-eight features is the right shape for a
        library and the wrong one for the two things somebody does every day."""
        def work(pg):
            self.open_tab(pg, "geotag")
            pg.wait_for_selector("#form h2", timeout=15000)
            pg.click(".pinbtn")
            pg.wait_for_timeout(900)
            rail = pg.eval_on_selector_all("#rail .railrow.pinned",
                                           "es => es.map(e => e.dataset.p)")
            self.assertIn("geotag", rail)
            # it opens that feature from there
            pg.evaluate("() => goScreen('home')")
            pg.wait_for_timeout(500)
            pg.click('#rail .railrow.pinned[data-p="geotag"]')
            pg.wait_for_timeout(900)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "geotag")
            # and it is kept on the NAS, not in this browser
            pg.reload()
            pg.wait_for_function("() => document.body.classList.contains('shell')",
                                 timeout=20000)
            pg.wait_for_timeout(600)
            self.assertIn("geotag",
                          pg.eval_on_selector_all("#rail .railrow.pinned",
                                                  "es => es.map(e => e.dataset.p)"))
            # taken off again from the rail itself
            pg.evaluate("() => pinToggle('geotag')")
            pg.wait_for_timeout(900)
            self.assertEqual(
                pg.eval_on_selector_all("#rail .railrow.pinned", "es => es.length"), 0)
        self.page(work)

    def test_one_word_per_idea_across_every_feature(self):
        """The same act had four names depending on the screen: "Show me what
        would happen", "Have a look", "Go ahead", "Look again". Each reads well
        alone; together they teach that this app has several kinds of button
        doing several kinds of thing, which it has not."""
        def work(pg):
            seen = set()
            for name in ("bydate", "cull", "library", "history", "search"):
                self.open_tab(pg, name)
                pg.wait_for_selector("#go", timeout=15000)
                seen.add(pg.eval_on_selector("#go", "e => e.textContent.trim()"))
            self.assertEqual(seen, {"Check the list"},
                             f"the same button has several names: {seen}")
            # and the old words are nowhere in the page any more
            body = pg.evaluate("() => document.body.innerText")
            for gone in ("Go ahead", "Have a look", "Show me what would happen"):
                self.assertNotIn(gone, body)
        self.page(work)

    def test_and_apply_always_says_the_verb_and_the_count(self):
        """"Apply" on its own has not told you anything. The button carries the
        real operation - Move 412 files - which is the one place the missing
        word belongs."""
        def work(pg):
            self.open_tab(pg, "previews")
            pg.fill("#o_folder", self.lib)
            pg.click("#go")
            pg.wait_for_selector("#doit", timeout=90000)
            said = pg.text_content("#doit")
            self.assertRegex(said, r"^[A-Z][a-z]+ \d")
            self.assertNotIn("Go ahead", said)
        self.page(work)

    def test_every_screen_says_there_is_nothing_here_the_same_way(self):
        """Five screens had five ways of saying the same five things. An empty
        state that does not say what to do next is a dead end wearing an
        explanation."""
        def work(pg):
            # Photos, with a filter nothing answers to
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles", timeout=20000)
            pg.evaluate("() => { FILTER = {camera: 'NOTHING HAS THIS'};"
                        " loadShots(true); }")
            pg.wait_for_selector("#tiles .nothing", timeout=15000)
            one = pg.eval_on_selector("#tiles .nothing",
                                      "e => ({icon: !!e.querySelector('.nicon svg'),"
                                      " title: !!e.querySelector('b'),"
                                      " way: e.querySelectorAll('.act button').length})")
            self.assertTrue(one["icon"], "no glyph")
            self.assertTrue(one["title"], "no sentence")
            self.assertGreaterEqual(one["way"], 1, "no way out")
            pg.evaluate("() => { FILTER = {}; loadShots(true); }")
            pg.wait_for_timeout(600)

            # Albums, with every album put away - the same component
            pg.evaluate("""async () => {
              const all = (await (await fetch("api/albums")).json()).albums
                .map(a => a.key);
              await fetch("api/albums", {method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({hidden: all})});
            }""")
            pg.evaluate("() => goScreen('albums')")
            pg.wait_for_selector("#albumgrid .nothing", timeout=15000)
            self.assertTrue(pg.query_selector("#albumgrid .nothing .nicon svg"))
            self.assertGreaterEqual(
                pg.eval_on_selector_all("#albumgrid .nothing .act button",
                                        "es => es.length"), 1)
            pg.evaluate("() => sendAway([])")
            pg.wait_for_timeout(700)
        self.page(work)

    def test_the_selection_bar_says_what_each_button_would_do(self):
        """"Organize" is a category, not an act; "Develop" sounds like it
        changes the photographs and it copies them. A person who has just
        selected forty is deciding on the label alone."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("() => { pickMode(); pickAll(); }")
            pg.wait_for_selector("#picked .pillbtn", timeout=10000)
            said = pg.eval_on_selector_all("#picked .pillbtn",
                                           "es => es.map(e => e.textContent.trim())")
            self.assertIn("Sort into folders", said)
            self.assertIn("Send to develop", said)
            self.assertNotIn("Organize", said)
            # and each one says the consequence before it is pressed
            # in the bubble, once - not in a title beside it as well
            tips = pg.eval_on_selector_all("#picked .pillbtn",
                                           "es => es.map(e => e.dataset.tip || '')")
            self.assertTrue(all(len(t) > 20 for t in tips), tips)
            self.assertTrue(any(t.startswith("Moves") for t in tips), tips)
            self.assertTrue(any(t.startswith("Copies") for t in tips), tips)
            # the overflow names the destructive one, in red, with what it does
            pg.evaluate("""() => { const b = [...document.querySelectorAll('#picked .pillbtn')]
              .find(x => /More/.test(x.textContent)); b.click(); }""")
            pg.wait_for_selector(".pmenu", timeout=10000)
            menu = pg.text_content(".pmenu")
            self.assertIn("recycle", menu.lower())
            self.assertIn("Undo", menu)
        self.page(work)

    # ---------------------------------------------------------- folders as places

    def test_the_folder_view_is_folders_you_can_walk_into(self):
        """It used to be the timeline sorted differently: every photograph in
        the library in one list, with a heading each time the folder changed.
        Nothing to press, and no way to see that a folder HAS folders in it."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("() => viewBy('folder')")
            pg.wait_for_selector("#folderwall .foldcard", timeout=20000)
            names = pg.eval_on_selector_all(".foldcard .who b",
                                            "es => es.map(e => e.textContent)")
            self.assertIn("2022", names)
            self.assertIn("2023", names)
            # a cover, so a folder is recognised rather than read
            self.assertTrue(pg.eval_on_selector_all(".foldcard .cover img",
                                                    "es => es.length"))
            # and the photographs of the whole library are NOT all laid out here
            self.assertEqual(pg.eval_on_selector_all("#tiles .shot", "es => es.length"), 0)
            self.assertRegex(pg.text_content("#shotsaid"), r"\d+ folders? in ")
        self.page(work)

    def test_pressing_a_folder_goes_in_and_the_crumbs_come_back_out(self):
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("() => viewBy('folder')")
            pg.wait_for_selector("#folderwall .foldcard", timeout=20000)
            top = pg.evaluate("() => WHERE")
            pg.evaluate("""() => [...document.querySelectorAll('.foldcard')]
              .find(c => /2022/.test(c.textContent)).click()""")
            pg.wait_for_function("() => !LOADING && /2022$/.test(WHERE)", timeout=15000)
            pg.wait_for_selector("#folderwall .foldcard", timeout=15000)
            self.assertEqual(pg.eval_on_selector_all(".foldcard .who b",
                                                     "es => es.map(e => e.textContent)"),
                             ["Spain"])
            # down one more, and the photographs that are IN there are there
            pg.evaluate("() => document.querySelector('.foldcard').click()")
            pg.wait_for_selector("#tiles .shot", timeout=15000)
            self.assertTrue(pg.evaluate("() => WHERE").endswith("Spain"))
            crumbs = pg.eval_on_selector_all(".crumb",
                                             "es => es.map(e => e.textContent.trim())")
            self.assertEqual(crumbs[0], "All folders")
            self.assertEqual(crumbs[-1], "Spain")
            # and a crumb walks back up
            pg.evaluate("""() => [...document.querySelectorAll('.crumb')]
              .find(c => c.textContent.trim() === '2022').click()""")
            pg.wait_for_function("() => !LOADING && /2022$/.test(WHERE)", timeout=15000)
            # as does the button beside them
            pg.evaluate("() => document.querySelector('.wherebar .ghost').click()")
            pg.wait_for_function("(t) => WHERE === t", arg=top, timeout=15000)
        self.page(work)

    def test_everything_below_is_a_choice_and_not_the_only_way(self):
        """The old behaviour is still there - it is just no longer what you get
        without asking."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("() => viewBy('folder')")
            pg.wait_for_selector("#folderwall .foldcard", timeout=20000)
            pg.evaluate("""() => [...document.querySelectorAll('.foldcard')]
              .find(c => /2022/.test(c.textContent)).click()""")
            pg.wait_for_function("() => !LOADING && /2022$/.test(WHERE)", timeout=15000)
            self.assertEqual(pg.evaluate("() => SHOTS.length"), 0)
            pg.evaluate("() => goDeeper(true)")
            pg.wait_for_selector("#tiles .shot", timeout=15000)
            self.assertTrue(pg.evaluate("() => SHOTS.length") > 0)
            self.assertTrue(pg.eval_on_selector(".wherebar .fchip",
                                                "e => e.classList.contains('on')"))
            # and walking somewhere else does not keep the setting on
            pg.evaluate("() => goFolder('')")
            pg.wait_for_selector("#folderwall .foldcard", timeout=15000)
            self.assertFalse(pg.evaluate("() => DEEPER"))
        self.page(work)

    def test_the_month_rail_is_not_there_while_standing_in_a_folder(self):
        """It jumps to a month of the whole library, which from inside one
        folder is a way to nowhere you asked for."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("() => viewBy('folder')")
            pg.wait_for_selector("#folderwall .foldcard", timeout=20000)
            self.assertEqual(pg.eval_on_selector_all("#scrub button", "es => es.length"), 0)
        self.page(work)

    def test_there_is_a_way_from_the_folder_you_are_in_to_the_explorer(self):
        """Standing in a folder and wanting the files themselves was the one
        thing the folder view could not do at all."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("() => viewBy('folder')")
            pg.wait_for_selector("#folderwall .foldcard", timeout=20000)
            pg.evaluate("""() => [...document.querySelectorAll('.foldcard')]
              .find(c => /2022/.test(c.textContent)).click()""")
            pg.wait_for_function("() => !LOADING && /2022$/.test(WHERE)", timeout=15000)
            where = pg.evaluate("() => WHERE")
            pg.evaluate("""() => [...document.querySelectorAll('.wherebar .fchip')]
              .find(b => /explorer/i.test(b.textContent)).click()""")
            pg.wait_for_selector(".fmpane", timeout=20000)
            pg.wait_for_function("(w) => FM.panes[0].path === w", arg=where, timeout=20000)
            self.assertEqual(pg.eval_on_selector("#o_folder", "e => e.value"), where)
        self.page(work)

    # ------------------------------------------- the explorer: browse, select, act

    def test_one_press_opens_a_folder_rather_than_ticking_it(self):
        """It took two presses, which a phone does not have. Every file manager
        in the world opens on one."""
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.lib!r})")
            pg.wait_for_timeout(900)
            was = pg.evaluate("() => FM.panes[0].path")
            pg.evaluate("""() => [...document.querySelectorAll('.fmrow')]
              .find(r => /2022/.test(r.textContent)).click()""")
            pg.wait_for_timeout(1200)
            self.assertTrue(pg.evaluate("() => FM.panes[0].path").endswith("2022"))
            self.assertNotEqual(pg.evaluate("() => FM.panes[0].path"), was)
            self.assertEqual(pg.evaluate("() => FM.panes[0].sel.length"), 0,
                             "opening it picked it as well")
        self.page(work)

    def test_picking_is_a_mode_you_turn_on(self):
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.shoot!r})")
            pg.wait_for_timeout(900)
            # nothing picked, so there is no act bar at all
            self.assertEqual(pg.eval_on_selector_all(".fmact", "es => es.length"), 0)
            pg.evaluate("""() => [...document.querySelectorAll('.fmtop .fchip')][0].click()""")
            pg.wait_for_timeout(300)
            self.assertTrue(pg.evaluate("() => FM.picking"))
            pg.evaluate("() => document.querySelector('.fmrow').click()")
            pg.wait_for_selector(".fmact", timeout=10000)
            self.assertEqual(pg.evaluate("() => FM.panes[0].sel.length"), 1)
            said = pg.text_content(".fmact .fmcount")
            self.assertIn("1", said)
            self.assertIn("picked", said)
            # and Clear puts it back to browsing
            pg.evaluate("""() => [...document.querySelectorAll('.fmact button')]
              .find(b => /Clear/.test(b.textContent)).click()""")
            pg.wait_for_timeout(300)
            self.assertFalse(pg.evaluate("() => FM.picking"))
            self.assertEqual(pg.eval_on_selector_all(".fmact", "es => es.length"), 0)
        self.page(work)

    def test_or_a_ctrl_press_without_turning_anything_on(self):
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.shoot!r})")
            pg.wait_for_timeout(900)
            pg.evaluate("""() => document.querySelector('.fmrow')
              .dispatchEvent(new MouseEvent('click', {bubbles: true, ctrlKey: true}))""")
            pg.wait_for_selector(".fmact", timeout=10000)
            self.assertEqual(pg.evaluate("() => FM.panes[0].sel.length"), 1)
            # and shift reaches from there to another one in one press
            pg.evaluate("""() => document.querySelectorAll('.fmrow')[2]
              .dispatchEvent(new MouseEvent('click', {bubbles: true, shiftKey: true}))""")
            pg.wait_for_timeout(400)
            self.assertEqual(pg.evaluate("() => FM.panes[0].sel.length"), 3)
        self.page(work)

    def test_the_act_bar_says_how_many_and_what_each_button_would_do(self):
        """The old row was every action at once, greyed out, before a single
        file had been chosen - so the destructive one sat beside the harmless
        ones all day and stopped being read."""
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.shoot!r})")
            pg.wait_for_timeout(900)
            pg.evaluate("() => { FM.picking = true; fmPick(0, 'all'); }")
            pg.wait_for_selector(".fmact", timeout=10000)
            labels = pg.eval_on_selector_all(".fmact button",
                                             "es => es.map(e => e.textContent.trim())")
            self.assertTrue(any("Copy to" in t for t in labels), labels)
            self.assertTrue(any("Move to" in t for t in labels), labels)
            self.assertTrue(any("Delete" in t for t in labels), labels)
            # the dangerous one is the only one wearing the destructive role
            danger = pg.eval_on_selector_all(".fmact button.danger",
                                             "es => es.map(e => e.textContent.trim())")
            self.assertEqual(len(danger), 1, danger)
            self.assertIn("Delete", danger[0])
            # and each says the consequence before it is pressed
            tips = pg.eval_on_selector_all(".fmact button", "es => es.map(e => e.title)")
            self.assertTrue(any(t.startswith("Copies") for t in tips), tips)
            self.assertTrue(any(t.startswith("Moves") for t in tips), tips)
        self.page(work)

    def test_where_these_go_is_a_place_you_walk_into_not_a_second_pane(self):
        """A phone has no room for two panes, so "copied - now open a folder
        and press Paste" was the whole instruction it got."""
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.shoot!r})")
            pg.wait_for_timeout(900)
            name = pg.evaluate("() => FM.panes[0].data.files[0].name")
            pg.evaluate("() => { FM.picking = true; fmToggle(0, FM.panes[0].data.files[0].path); }")
            pg.wait_for_selector(".fmact", timeout=10000)
            pg.evaluate("""() => [...document.querySelectorAll('.fmact button')]
              .find(b => /Copy to/.test(b.textContent)).click()""")
            pg.wait_for_selector("#fmsheet", timeout=10000)
            pg.wait_for_timeout(900)
            self.assertIn("Copy", pg.text_content("#fmsheet h3"))
            # it walks: up to the library, then into the other year
            for _ in range(2):
                pg.evaluate("""() => document.querySelector('#fmsheet .sheettop .ghost').click()""")
                pg.wait_for_timeout(900)
            pg.evaluate("""() => [...document.querySelectorAll('#fmsheet .sheetrow')]
              .find(r => /2023/.test(r.textContent)).click()""")
            pg.wait_for_timeout(900)
            into = pg.evaluate("() => FM.sheet.at")
            self.assertNotEqual(into, self.shoot)
            pg.evaluate("""() => [...document.querySelectorAll('#fmsheet .act button')]
              .find(b => /^(Copy|Move) into/.test(b.textContent.trim())).click()""")
            pg.wait_for_timeout(2500)
            self.assertIsNone(pg.evaluate("() => FM.sheet"))
            there = pg.evaluate("""async (p) => {
              const got = await (await fetch("api/files?path=" + encodeURIComponent(p))).json();
              return (got.files || []).map(f => f.name);
            }""", into)
            self.assertIn(name, there)
        self.page(work)

    def test_the_folders_own_figures_are_one_line_with_a_light(self):
        """Eleven chips, all the same size and weight, so the one that said
        something was wrong looked like the seven that said nothing was."""
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmhealth", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.shoot!r})")
            pg.wait_for_selector("#fileman .fmhealth .light", timeout=15000)
            pg.wait_for_timeout(1500)
            self.assertEqual(pg.eval_on_selector_all(".fmhealth", "es => es.length"), 1)
            self.assertEqual(pg.eval_on_selector_all(".fmstat", "es => es.length"), 0,
                             "the chip row is on screen without being asked for")
            self.assertTrue(pg.eval_on_selector(".fmhealth .hsaid",
                                                "e => e.textContent.trim().length > 0"))
            # and the figures are a press away
            pg.evaluate("""() => document.querySelector('.fmhealth .quiet').click()""")
            pg.wait_for_selector(".fmstat .fmchip", timeout=10000)
            self.assertTrue(pg.eval_on_selector_all(".fmstat .fmchip", "es => es.length") > 2)
        self.page(work)

    def test_the_view_menu_holds_how_to_look_and_nothing_destructive(self):
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmtop", timeout=15000)
            pg.click('#fileman .fmtop button:has-text("View")')
            pg.wait_for_selector(".pmenu .vopt", timeout=10000)
            said = pg.text_content(".pmenu")
            for word in ("As a list", "As thumbnails", "Split view", "Details panel",
                         "Hidden folders"):
                self.assertIn(word, said)
            self.assertNotIn("Delete", said)
            # and it switches the listing for real
            pg.click('.pmenu .vopt:has-text("As thumbnails")')
            pg.wait_for_selector("#fileman .fmgrid", timeout=10000)
            self.assertEqual(pg.evaluate("() => FM.panes[0].view"), "grid")
        self.page(work)

    def test_a_search_box_narrows_the_folder_you_are_standing_in(self):
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.shoot!r})")
            pg.wait_for_timeout(900)
            whole = pg.eval_on_selector_all(".fmrow", "es => es.length")
            pg.evaluate("() => fmFind(0, 'rated')")
            pg.wait_for_timeout(500)
            now = pg.eval_on_selector_all(".fmrow .fmname",
                                          "es => es.map(e => e.textContent.trim())")
            self.assertTrue(now)
            self.assertLess(len(now), whole)
            self.assertTrue(all("rated" in t.lower() for t in now), now)
            pg.evaluate("() => fmFind(0, 'zzzz')")
            pg.wait_for_selector(".nothing", timeout=10000)
            self.assertIn("Nothing by that name", pg.text_content("#fileman .nothing"))
        self.page(work)

    def test_the_panel_on_the_right_says_what_is_picked(self):
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.shoot!r})")
            pg.wait_for_timeout(900)
            pg.evaluate("() => { FM.info = true; drawFiles(); }")
            pg.wait_for_selector(".fminfo", timeout=10000)
            self.assertIn("Pick something", pg.text_content(".fminfo"))
            pg.evaluate("() => { FM.picking = true; fmToggle(0, FM.panes[0].data.files[0].path); }")
            pg.wait_for_timeout(2000)
            said = pg.text_content(".fminfo")
            self.assertIn("Kind", said)
            self.assertIn("Size", said)
        self.page(work)

    # ------------------------------------------- what the 3.5.1 pass put right

    def test_a_clip_opens_from_the_explorer_as_well_as_from_the_grid(self):
        """The viewer has played clips since 3.4. It was the explorer's listing
        that still treated a video as a row with nothing behind it, so pressing
        one there did nothing at all."""
        clip = os.path.join(self.shoot, "clip.webm")
        shutil.copy(os.path.join(FIX, "tiny.webm"), clip)

        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.shoot!r})")
            pg.wait_for_timeout(1200)
            pg.evaluate("""() => { FM.picking = false;
              [...document.querySelectorAll('.fmrow')]
                .find(r => /webm/i.test(r.textContent)).click(); }""")
            pg.wait_for_selector("#viewer", timeout=15000)
            self.assertTrue(pg.evaluate("() => viewerPath()").endswith("clip.webm"))
            pg.evaluate("() => viewerClose()")
        self.page(work)
        os.remove(clip)

    def test_the_details_panel_is_reachable_wherever_the_viewer_opened(self):
        """It was built by the one caller that opened the viewer from the Photos
        grid - so from the explorer there was no panel AND no button to ask for
        one. The details were not hidden; they were unreachable."""
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.shoot!r})")
            pg.wait_for_timeout(1200)
            pg.evaluate("""() => { FM.picking = false;
              [...document.querySelectorAll('.fmrow')]
                .find(r => /plain/i.test(r.textContent)).click(); }""")
            pg.wait_for_selector("#viewer", timeout=15000)
            pg.wait_for_timeout(600)
            self.assertTrue(pg.evaluate("() => !!document.getElementById('vinfob')"),
                            "no way to ask for the details")
            pg.evaluate("() => infoOpen(true)")
            pg.wait_for_selector("#vinfo", timeout=10000)
            self.assertTrue(pg.evaluate(
                "() => document.getElementById('viewer').classList.contains('withinfo')"))
            pg.evaluate("() => viewerClose()")
        self.page(work)

    def test_and_the_histogram_moves_out_from_under_it(self):
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("() => document.querySelector('#tiles .shot').click()")
            pg.wait_for_selector("#viewer", timeout=15000)
            pg.evaluate("() => { infoOpen(false); overlayToggle('hist'); }")
            pg.wait_for_timeout(400)
            away = pg.eval_on_selector("#vhist", "e => getComputedStyle(e).right")
            pg.evaluate("() => infoOpen(true)")
            pg.wait_for_timeout(400)
            with_it = pg.eval_on_selector("#vhist", "e => getComputedStyle(e).right")
            self.assertNotEqual(away, with_it, "it stays behind the panel")
            self.assertGreater(float(with_it.replace("px", "")),
                               float(away.replace("px", "")))
            pg.evaluate("() => viewerClose()")
        self.page(work)

    def test_the_viewer_can_show_the_file_itself_and_keeps_doing_it(self):
        """A preview is right for browsing and wrong for "is this sharp" -
        zooming into a preview magnifies the preview. Deciding frame by frame
        which one you are looking at is the state nobody can hold, so the
        switch stays on for the next photograph too."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            # a JPEG on purpose: a clip and a RAW have no file a browser can
            # open, which is a different (and also correct) answer
            pg.evaluate("""() => [...document.querySelectorAll('#tiles .shot')]
              .find(a => /\.jpe?g$/i.test(a.dataset.p)).click()""")
            pg.wait_for_selector("#viewer", timeout=15000)
            pg.wait_for_timeout(500)
            self.assertTrue(pg.evaluate("() => !!document.getElementById('vfullb')"))
            self.assertFalse(pg.evaluate(
                "() => document.getElementById('vimg').src.includes('api/file?')"))
            pg.evaluate("() => fullToggle(true)")
            pg.wait_for_function(
                "() => document.getElementById('vimg').src.includes('api/file?')",
                timeout=10000)
            pg.evaluate("() => viewerStep(1)")
            pg.wait_for_function(
                "() => document.getElementById('vimg').src.includes('api/file?')",
                timeout=10000)
            pg.evaluate("() => { fullToggle(false); viewerClose(); }")
        self.page(work)

    def test_picking_a_file_does_not_throw_the_folder_back_to_the_top(self):
        """Every redraw rebuilt the listing, and a rebuilt listing starts at the
        top - so picking the fortieth file scrolled you back to the first."""
        many = os.path.join(self.lib, "Many")
        os.makedirs(many, exist_ok=True)
        for i in range(40):
            shutil.copy(os.path.join(FIX, "plain.jpg"),
                        os.path.join(many, f"Shot-{i:02d}.JPG"))

        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {many!r})")
            pg.wait_for_timeout(1800)
            pg.evaluate("() => { document.querySelector('.fmlist').scrollTop = 300; }")
            pg.wait_for_timeout(300)
            was = pg.eval_on_selector(".fmlist", "e => e.scrollTop")
            self.assertGreater(was, 0, "the list does not scroll in this window")
            pg.evaluate("""() => { FM.picking = true;
              fmToggle(0, FM.panes[0].data.files[10].path); }""")
            pg.wait_for_timeout(600)
            self.assertEqual(pg.eval_on_selector(".fmlist", "e => e.scrollTop"), was)
            pg.evaluate("() => fmClearSel()")
        self.page(work)
        shutil.rmtree(many, ignore_errors=True)

    def test_the_explorer_has_no_plan_form_under_it(self):
        """A box repeating the folder the crumbs already name, and a "Check the
        list" button whose whole answer was a count of what is in the folder -
        which is the line above the listing."""
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            said = pg.eval_on_selector("#form", "e => e.innerText")
            self.assertNotIn("Check the list", said)
            self.assertNotIn("Folder to open", said)
            # the boxes themselves stay, because the manager reads them
            self.assertTrue(pg.evaluate("() => !!document.getElementById('o_with_raw')"))
            # and they are reachable, in the menu where the rest of how this
            # tab behaves lives
            pg.click('#fileman .fmtop button:has-text("View")')
            pg.wait_for_selector(".pmenu .vopt", timeout=10000)
            self.assertIn("RAW files follow", pg.text_content(".pmenu"))
            pg.evaluate("() => closePageMenu()")
        self.page(work)

    def test_the_folder_you_are_standing_in_can_be_renamed(self):
        """Rename only ever looked at the selection, so the answer to "rename
        this folder" was to walk out of it and find it in the list."""
        where = os.path.join(self.lib, "Renameme")
        os.makedirs(where, exist_ok=True)

        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {where!r})")
            pg.wait_for_timeout(1200)
            pg.evaluate("() => { fmClearSel(); fmRename(); }")
            pg.wait_for_selector("#askbox", timeout=10000)
            pg.fill("#askbox", "Renamed")
            pg.evaluate("""() => { [...document.querySelectorAll('.sure .act button')]
              .find(b => /Rename/.test(b.textContent)).click(); }""")
            pg.wait_for_function("() => /Renamed$/.test(FM.panes[0].path)", timeout=15000)
            self.assertTrue(os.path.isdir(os.path.join(self.lib, "Renamed")))
        self.page(work)
        shutil.rmtree(os.path.join(self.lib, "Renamed"), ignore_errors=True)

    def test_a_country_and_a_town_are_menus_of_what_is_there(self):
        """They were free-text boxes over an index that holds coordinates, so
        every name anybody typed matched nothing - and an empty answer cannot
        tell a wrong spelling from a library with no place names in it."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("() => { CHOICES = null; filterPanel(); }")
            pg.wait_for_selector(".filtgrid", timeout=15000)
            pg.wait_for_timeout(600)
            said = pg.eval_on_selector(".filtgrid", "e => e.innerText")
            self.assertIn("place table", said.lower())
            # and it is not a box you can type a name into and learn nothing
            boxes = pg.eval_on_selector_all(
                '.filtgrid input[data-f="country"]', "es => es.length")
            self.assertEqual(boxes, 0)
        self.page(work)

    def test_a_picture_tile_is_a_number_of_pixels_tall_whatever_css_says(self):
        """It has been wrong twice. The box took its height from `aspect-ratio`,
        which came out as nothing and left rows of twenty-pixel bars holding a
        horizontal slice of a photograph; it was then given an aspect ratio AND
        a min-height in the stylesheet, and it was still nothing on the machine
        it mattered on.

        So the height is written onto the element. This test puts the old rule
        back on top of the page, with the highest weight a stylesheet has, and
        the box must still be the right size - because an inline style is not
        something a rule can argue with."""
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.shoot!r})")
            pg.wait_for_timeout(1200)
            pg.evaluate("() => { FM.panes[0].view = 'grid'; drawFiles(); }")
            pg.wait_for_selector("#fileman .fmgrid .tile", timeout=15000)
            pg.wait_for_timeout(600)
            want = pg.evaluate("() => fmTileHigh()")
            self.assertGreaterEqual(want, 90)
            high = pg.eval_on_selector_all(
                "#fileman .fmgrid .tile .pic",
                "es => es.map(e => Math.round(e.getBoundingClientRect().height))")
            self.assertTrue(high, "no picture tiles at all")
            self.assertTrue(all(h == want for h in high), high)
            # the name is on screen, not clipped away by the tile's own overflow
            caps = pg.eval_on_selector_all(
                "#fileman .fmgrid figcaption",
                "es => es.map(e => Math.round(e.getBoundingClientRect().height))")
            self.assertTrue(all(c > 10 for c in caps), caps)
            # and it survives the rule that used to decide this
            pg.add_style_tag(content=""".fmgrid .tile .pic{aspect-ratio:1/1;
              min-height:0;height:auto;flex:0 1 auto}
              .fmgrid .tile{min-height:0}""")
            pg.wait_for_timeout(500)
            still = pg.eval_on_selector_all(
                "#fileman .fmgrid .tile .pic",
                "es => es.map(e => Math.round(e.getBoundingClientRect().height))")
            self.assertTrue(all(h == want for h in still), still)
            pg.evaluate("() => { FM.panes[0].view = 'list'; drawFiles(); }")
        self.page(work)

    def test_a_folder_read_that_lands_late_does_not_win(self):
        """Two reads of two different folders can be in the air at once -
        opening the explorer AT a folder starts one while the tab's own first
        read is still running. On a sleeping NAS the first can land second, and
        the pane then shows a folder nobody asked for with the address bar
        saying something else."""
        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            # the slow one first, then the one you actually asked for
            pg.evaluate(f"""() => {{
              fmGo(0, {self.lib!r});
              fmGo(0, {self.shoot!r});
            }}""")
            pg.wait_for_timeout(2500)
            self.assertEqual(pg.evaluate("() => FM.panes[0].path"), self.shoot)
            self.assertEqual(
                pg.eval_on_selector("#o_folder", "e => e.value"), self.shoot)
        self.page(work)

    # --------------------------------------------------- 3.7: closer, and clips

    def test_a_picked_folder_in_the_explorer_can_be_renamed(self):
        """Not only the one you are standing in. Both paths exist and both are
        held here, because the one that was reported broken was this one."""
        where = os.path.join(self.lib, "Pickme")
        os.makedirs(where, exist_ok=True)

        def work(pg):
            self.open_tab(pg, "files")
            pg.wait_for_selector("#fileman .fmrow", timeout=15000)
            pg.evaluate(f"() => fmGo(0, {self.lib!r})")
            pg.wait_for_timeout(1500)
            pg.evaluate(f"""() => {{ FM.picking = true;
              fmToggle(0, {where!r}); }}""")
            pg.wait_for_selector(".fmact", timeout=10000)
            self.assertEqual(pg.evaluate("() => FM.panes[0].sel.length"), 1)
            pg.evaluate("""() => { [...document.querySelectorAll('.fmact button')]
              .find(b => b.textContent.trim() === 'Rename').click(); }""")
            pg.wait_for_selector("#askbox", timeout=10000)
            pg.fill("#askbox", "Picked")
            pg.evaluate("""() => { [...document.querySelectorAll('.sure .act button')]
              .find(b => /Rename/.test(b.textContent)).click(); }""")
            pg.wait_for_timeout(2500)
            self.assertTrue(os.path.isdir(os.path.join(self.lib, "Picked")))
            self.assertFalse(os.path.isdir(where))
        self.page(work)
        shutil.rmtree(os.path.join(self.lib, "Picked"), ignore_errors=True)

    def test_the_viewer_gets_closer_than_the_screen(self):
        """"Show me the file itself" changed not one visible pixel, because the
        picture is fitted to the screen either way. The switch was answering a
        question nobody could see."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("""() => [...document.querySelectorAll('#tiles .shot')]
              .find(a => /\\.jpe?g$/i.test(a.dataset.p)).click()""")
            pg.wait_for_selector("#viewer", timeout=15000)
            pg.wait_for_timeout(500)
            self.assertEqual(pg.evaluate("() => ZOOM.at"), 1)
            self.assertTrue(pg.eval_on_selector("#vzoom", "e => e.hidden"))
            pg.evaluate("() => zoomTo(3)")
            pg.wait_for_timeout(500)
            self.assertGreater(pg.evaluate("() => ZOOM.at"), 2)
            self.assertFalse(pg.eval_on_selector("#vzoom", "e => e.hidden"),
                             "it does not say how close in you are")
            self.assertTrue(pg.evaluate(
                "() => document.getElementById('viewer').classList.contains('zoomed')"))
            # and it fits back
            pg.evaluate("() => zoomReset()")
            pg.wait_for_timeout(300)
            self.assertEqual(pg.evaluate("() => ZOOM.at"), 1)
            pg.evaluate("() => viewerClose()")
        self.page(work)

    def test_and_going_closer_fetches_the_file_rather_than_blurring_a_preview(self):
        """A preview magnified is a blurred preview, which looks exactly like a
        photograph that is out of focus. That is the one wrong answer this
        screen must never give."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("""() => [...document.querySelectorAll('#tiles .shot')]
              .find(a => /\\.jpe?g$/i.test(a.dataset.p)).click()""")
            pg.wait_for_selector("#viewer", timeout=15000)
            pg.wait_for_timeout(500)
            self.assertFalse(pg.evaluate(
                "() => document.getElementById('vimg').src.includes('api/file?')"))
            pg.evaluate("() => zoomTo(3)")
            pg.wait_for_function(
                "() => document.getElementById('vimg').src.includes('api/file?')",
                timeout=15000)
            # and moving on starts fitted again, on the preview
            pg.evaluate("() => viewerStep(1)")
            pg.wait_for_timeout(600)
            self.assertEqual(pg.evaluate("() => ZOOM.at"), 1)
            pg.evaluate("() => viewerClose()")
        self.page(work)

    # ------------------------------------------------ phase 4 of the 3rd audit

    def test_redrawing_the_selection_bar_binds_nothing_more(self):
        """The selection bar bound the bubble's seven document listeners again
        on every redraw, so after an even number of them a tap opened and
        shut a bubble at once."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            cdp = pg.context.new_cdp_session(pg)

            def hovers():
                doc = cdp.send("Runtime.evaluate",
                               {"expression": "document"})["result"]["objectId"]
                got = cdp.send("DOMDebugger.getEventListeners", {"objectId": doc})
                return sum(1 for one in got["listeners"] if one["type"] == "pointerover")
            was = hovers()
            pg.evaluate("""() => { const ps = SHOTS.slice(0, 2).map(s => s.path);
                                   pickMode(); ps.forEach(p => pickToggle(p));
                                   drawPickBar(); drawPickBar(); }""")
            self.assertTrue(pg.query_selector("#picked [data-tip]"))
            self.assertEqual(hovers(), was, "a redraw bound the bubble again")
        self.page(work)

    def test_deleting_a_selection_offers_undo_and_it_puts_them_back(self):
        """The dialog promised Undo; the toast had nothing to press."""
        where = self.shoot_of("bin-test", ["plain"])
        os.makedirs(os.path.join(os.path.dirname(where), "#recycle"), exist_ok=True)
        photo = os.path.join(where, "plain.JPG")

        def work(pg):
            pg.evaluate("(p) => { PICK.clear(); PICK.add(p); deletePicked(); }", photo)
            pg.wait_for_selector(".sure .surebox", timeout=8000)
            said = pg.text_content(".sure .surebox")
            self.assertNotIn("NAS", said)
            pg.click('.sure button[data-a="1"]')
            pg.wait_for_selector("#vtoastgo", timeout=10000)
            self.assertEqual(pg.text_content("#vtoastgo").strip(), "Undo")
            self.assertFalse(os.path.exists(photo), "it was not deleted")
            pg.click("#vtoastgo")
            pg.wait_for_timeout(1200)
            self.assertTrue(os.path.exists(photo), "Undo did not put it back")
        try:
            self.page(work)
        finally:
            shutil.rmtree(os.path.dirname(where), ignore_errors=True)

    def test_the_newest_search_wins_when_an_older_one_is_still_out(self):
        """A keystroke while the last answer was on its way was dropped, and the
        grid showed the results for the text as it was before."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#findshots", timeout=20000)
            asked, held, holding = [], [], [True]

            def hold(route):
                asked.append(route.request.url)
                if holding[0]:
                    held.append(route)
                else:
                    route.continue_()
            pg.route("**/api/timeline*", hold)
            pg.type("#findshots", "p", delay=0)
            pg.wait_for_timeout(500)          # the first ask is out, unanswered
            pg.type("#findshots", "l", delay=0)
            pg.wait_for_timeout(600)
            holding[0] = False
            for one in held:
                one.continue_()
            pg.wait_for_timeout(1500)
            self.assertTrue(any("name=pl" in u for u in asked),
                            f"the full text was never asked for: {asked}")
            self.assertEqual(pg.evaluate("() => FILTER.name"), "pl")
            self.assertFalse(pg.evaluate("() => LOADING"))
        self.page(work)

    def test_an_idle_library_is_not_asked_about_every_few_seconds(self):
        def work(pg):
            pg.wait_for_timeout(1500)
            pg.evaluate("() => { IDX.building = false; IDXASKED = Date.now(); }")
            hits = []
            pg.on("request", lambda r: hits.append(r.url)
                  if r.url.split("?")[0].endswith("/api/index") and r.method == "GET"
                  else None)
            pg.wait_for_timeout(6000)
            self.assertLessEqual(len(hits), 1, hits)
        self.page(work)

    def test_a_screen_that_cannot_reach_the_app_says_so(self):
        """Places, Albums and People said "Reading..." for ever."""
        def work(pg):
            for screen, api in (("places", "places"), ("albums", "albums"),
                                ("people", "people")):
                pg.route(f"**/api/{api}*", lambda route: route.abort())
                pg.evaluate("(s) => goScreen(s)", screen)
                pg.wait_for_function(
                    "() => /Could not reach the app/.test("
                    "document.getElementById('stage').innerText)", timeout=8000)
                pg.unroute(f"**/api/{api}*")
        self.page(work)

    def test_home_says_reading_on_its_own_re_read_button(self):
        """It looked for an id nobody had, so the rail's button changed and
        Home's stayed as it was - or, on a new install, "Open Setup" did."""
        def work(pg):
            pg.evaluate("() => { SUMS = null; goScreen('home'); }")
            pg.wait_for_selector('#stage .vtools .fchip', timeout=15000)

            held = []

            def hold(route):
                # the POST is held until the button has been looked at
                if route.request.method == "POST":
                    held.append(route)
                else:
                    route.continue_()
            pg.route("**/api/index*", hold)
            pg.click('#stage .vtools .fchip')
            pg.wait_for_timeout(300)
            try:
                self.assertIn("Reading", pg.text_content('#stage .vtools .fchip'))
                rail = pg.eval_on_selector_all("#railfoot .fchip",
                                               "es => es.map(e => e.textContent)")
                self.assertFalse(any("Reading" in r for r in rail), rail)
            finally:
                for one in held:
                    one.continue_()
            pg.wait_for_timeout(500)
            self.assertIn("Re-read library", pg.text_content('#stage .vtools .fchip'))
        self.page(work)

    def test_a_feature_opened_from_the_header_can_be_gone_back_from(self):
        def work(pg):
            pg.evaluate("() => goScreen('home')")
            pg.wait_for_timeout(300)
            # nothing behind Home, so the arrow can only come from History
            pg.evaluate("() => { TRAIL.length = 0; drawBack(); }")
            self.assertTrue(pg.eval_on_selector("#back", "e => e.hidden"))
            pg.click("#apart [data-t=history]")
            pg.wait_for_timeout(400)
            self.assertFalse(pg.eval_on_selector("#back", "e => e.hidden"),
                             "no way back from History")
            pg.click("#back")
            pg.wait_for_timeout(600)
            self.assertEqual(pg.evaluate("() => SCREEN"), "home")
        self.page(work)

    def test_the_arrow_on_the_page_uses_up_the_browsers_history_too(self):
        """Ten presses of the page's Back left ten entries for the browser's
        own Back to do nothing with."""
        def work(pg):
            pg.evaluate("() => goScreen('home')")
            pg.wait_for_timeout(200)
            depth = pg.evaluate("() => history.length")
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_timeout(200)
            pg.evaluate("() => goScreen('places')")
            pg.wait_for_timeout(200)
            for _ in range(2):
                pg.evaluate("() => goBack()")
                pg.wait_for_timeout(500)
            self.assertEqual(pg.evaluate("() => SCREEN"), "home")
            self.assertFalse(pg.evaluate(
                "() => !!(history.state && history.state.pmback)"),
                "the browser is still standing on an entry the trail has left")
            self.assertGreaterEqual(depth, 1)
        self.page(work)

    def test_keeping_a_filter_as_an_album_asks_in_the_apps_own_dialog(self):
        def work(pg):
            pg.evaluate("() => { goScreen('photos'); FILTER = {stars_from: '1'}; "
                        "keepAsAlbum(); }")
            pg.wait_for_selector(".sure #askbox", timeout=8000)
            pg.click('.sure button[data-a="0"]')
        self.page(work)

    def test_a_pinned_tool_can_be_unpinned_from_the_keyboard(self):
        def work(pg):
            pg.evaluate("() => pinToggle('geotag')")
            pg.wait_for_selector('#rail .pinwrap button.unpin', timeout=8000)
            self.assertTrue(pg.eval_on_selector(
                "#rail .pinwrap button.unpin", "e => e.getAttribute('aria-label')"))
            self.assertEqual(pg.eval_on_selector_all(
                "#rail .railrow.pinned .unpin", "es => es.length"), 0,
                "a button inside a button")
            pg.focus("#rail .pinwrap button.unpin")
            self.assertEqual(pg.eval_on_selector(
                "#rail .pinwrap button.unpin", "e => getComputedStyle(e).opacity"), "1")
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(800)
            self.assertEqual(pg.eval_on_selector_all(
                "#rail .railrow.pinned", "es => es.length"), 0)
        self.page(work)

    def test_the_viewer_keeps_the_keyboard_and_gives_it_back(self):
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.focus("#findshots")
            pg.evaluate("() => peek(SHOTS[0].path, SHOTS.map(s => s.path))")
            pg.wait_for_selector("#viewer", timeout=8000)
            self.assertEqual(pg.evaluate("() => document.activeElement.id"), "vclose")
            for _ in range(40):
                pg.keyboard.press("Tab")
            self.assertTrue(pg.evaluate(
                "() => document.getElementById('viewer')"
                ".contains(document.activeElement)"), "Tab walked out of the viewer")
            pg.evaluate("() => viewerClose()")
            self.assertEqual(pg.evaluate("() => document.activeElement.id"),
                             "findshots")
            self.assertEqual(pg.eval_on_selector("#findshots", "e => e.id"), "findshots")
        self.page(work)

    def test_a_question_gives_the_keyboard_back_where_it_was(self):
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#findshots", timeout=20000)
            pg.focus("#findshots")
            pg.evaluate("() => { window.ANSWER = askSure({title: 'Sure?'}); }")
            pg.wait_for_selector(".sure .surebox", timeout=5000)
            for _ in range(5):
                pg.keyboard.press("Tab")
            self.assertTrue(pg.evaluate(
                "() => document.querySelector('.sure').contains(document.activeElement)"))
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(100)
            self.assertEqual(pg.evaluate("() => document.activeElement.id"), "findshots")
        self.page(work)

    def test_the_keys_card_is_a_dialog_that_escape_closes(self):
        def work(pg):
            pg.evaluate("() => shortcutCard()")
            pg.wait_for_selector("#keyscard", timeout=8000)
            self.assertEqual(pg.eval_on_selector(
                "#keyscard .surebox", "e => e.getAttribute('role')"), "dialog")
            # the way out is at the top of the card, not a scroll away
            top = pg.eval_on_selector("#keysclose",
                "e => e.getBoundingClientRect().top - "
                "e.closest('.surebox').getBoundingClientRect().top")
            self.assertLess(top, 60)
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(150)
            self.assertIsNone(pg.query_selector("#keyscard"))
        self.phone(work)

    def test_a_tile_says_what_it_is_to_a_screen_reader(self):
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            labels = pg.eval_on_selector_all(
                "#tiles .shot", "es => es.map(e => e.getAttribute('aria-label'))")
            self.assertTrue(labels and all(labels), labels)
            self.assertTrue(any(re.search(r"\.(JPG|RW2|mp4|webm)", l or "", re.I)
                                for l in labels), labels)
        self.page(work)

    def test_a_filter_note_sits_under_its_label_not_in_it(self):
        """"CountryNo place table has been imported..." read as one label."""
        def work(pg):
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot", timeout=20000)
            pg.evaluate("() => { CHOICES = null; filterPanel(); }")
            pg.wait_for_selector(".filtgrid", timeout=15000)
            pg.wait_for_timeout(500)
            if not pg.evaluate("() => noPlacesWhy()"):
                self.skipTest("this library has places, so there is no note")
            labels = pg.eval_on_selector_all(
                ".filtgrid label", "es => es.map(e => e.textContent.trim())")
            self.assertIn("Country", labels)
            self.assertIn("City or town", labels)
        self.page(work)

    def test_times_are_written_one_way_on_the_page(self):
        """The server wrote "17 Oct 20:24" and the page "Oct 17 08:29 PM"."""
        def work(pg):
            got = pg.evaluate("""() => {
              const t = new Date(new Date().getFullYear(), 9, 17, 20, 24) / 1000;
              return [dayTime(t), fmWhen(t), clock(t)]; }""")
            self.assertEqual(got, ["17 Oct 20:24", "17 Oct 20:24", "20:24"])
            old = pg.evaluate("() => dayTime(new Date(2019, 0, 5, 9, 7) / 1000)")
            self.assertEqual(old, "05 Jan 2019 09:07")
        self.page(work)

    def test_a_count_of_one_is_not_a_plural(self):
        def work(pg):
            self.assertEqual(pg.evaluate(
                "() => [count(1, 'photograph'), count(2, 'folder'), count(0, 'file')]"),
                ["1 photograph", "2 folders", "0 files"])
        self.page(work)

    def test_the_worker_never_keeps_the_sign_in_page_as_the_app(self):
        """The sign-in page answers the same address with a 200, and the worker
        kept it as the offline copy of the app."""
        def work(pg):
            ok = pg.evaluate("""async () => {
              if (!('serviceWorker' in navigator)) return "no worker";
              await navigator.serviceWorker.ready;
              for (let i = 0; i < 50; i++){
                if (await caches.match("./")) return true;
                await new Promise(r => setTimeout(r, 100));
              }
              return "never kept"; }""")
            if ok == "no worker":
                self.skipTest("no service worker in this browser")
            if not pg.evaluate("() => !!navigator.serviceWorker.controller"):
                pg.reload()
                pg.wait_for_function("() => !!navigator.serviceWorker.controller",
                                     timeout=10000)
            os.environ["PM_PASSWORD"] = "a-test-password"
            try:
                pg.goto(self.base)
                pg.wait_for_timeout(800)
                self.assertNotIn('id="autobar"', pg.content(), "not signed out")
            finally:
                os.environ.pop("PM_PASSWORD", None)
            kept = pg.evaluate("""async () => {
              await new Promise(r => setTimeout(r, 400));
              return (await (await caches.match("./")).text()); }""")
            self.assertIn('name="pm-shell" content="app"', kept,
                          "the offline copy is the sign-in page")
            # Reload adds ?t=<now>; that is the same page, kept once
            pg.goto(self.base + "?t=12345")
            pg.wait_for_timeout(1500)
            navs = pg.evaluate("""async () => {
              const names = (await caches.keys()).filter(n => n.startsWith("pm-shell-"));
              let out = [];
              for (const n of names){
                const c = await caches.open(n);
                out = out.concat((await c.keys()).map(r => r.url)
                                 .filter(u => !u.endsWith(".png")));
              }
              return out; }""")
            self.assertEqual([u for u in navs if "?t=" in u], [], navs)
        self.page(work)

    def test_new_pictures_clear_the_workers_thumbnails(self):
        def work(pg):
            ok = pg.evaluate("""async () => {
              if (!('serviceWorker' in navigator)) return "no worker";
              await navigator.serviceWorker.ready; return true; }""")
            if ok == "no worker":
                self.skipTest("no service worker in this browser")
            if not pg.evaluate("() => !!navigator.serviceWorker.controller"):
                pg.reload()
                pg.wait_for_function("() => !!navigator.serviceWorker.controller",
                                     timeout=10000)
            pg.evaluate("() => goScreen('photos')")
            pg.wait_for_selector("#tiles .shot img", timeout=20000)
            pg.wait_for_timeout(1500)
            pg.evaluate("() => freshPics()")
            left = pg.evaluate("""async () => {
              await new Promise(r => setTimeout(r, 600));
              const names = (await caches.keys()).filter(n => n.startsWith("pm-thumbs-"));
              let n = 0;
              for (const one of names) n += (await (await caches.open(one)).keys()).length;
              return n; }""")
            self.assertEqual(left, 0)
        self.page(work)

    def test_every_key_is_written_down_in_one_place(self):
        """A key that is not written down anywhere is a key that does not
        exist. The handler, the list in the rail and the card all read the same
        table."""
        def work(pg):
            pg.evaluate("() => goScreen('home')")
            pg.wait_for_timeout(400)
            pg.evaluate("() => shortcutCard()")
            pg.wait_for_selector("#keyscard", timeout=10000)
            said = pg.eval_on_selector("#keyscard", "e => e.innerText")
            # the headings are drawn in capitals, so the test asks the way a
            # reader would rather than the way the CSS happens to render
            flat = said.lower()
            for word in ("moving", "rating and tags", "looking", "stars", "actual size",
                         "the file itself", "histogram"):
                self.assertIn(word, flat, word)
            # the two that can be changed show the letter they are set to
            keys = pg.eval_on_selector_all("#keyscard kbd",
                                           "es => es.map(e => e.textContent.trim())")
            self.assertIn((pg.evaluate("() => KEYS.info") or "i").upper(), keys)
            pg.evaluate("() => document.getElementById('keyscard').remove()")
            # and it is reachable without knowing the key for it
            self.assertIn("Keys", pg.eval_on_selector("#rail", "e => e.innerText"))
        self.page(work)

    def test_a_clip_can_be_rated_and_tagged_like_a_negative(self):
        """Nothing is written into it. A sidecar is written beside it, which is
        exactly what a RAW has always done."""
        clip = os.path.join(self.shoot, "markme.mp4")
        shutil.copy(os.path.join(FIX, "tiny.mp4"), clip)

        def work(pg):
            got = pg.evaluate("""async (p) => {
              const r = await fetch("api/photo", {method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({do: "stars", path: p, value: 4})});
              return await r.json(); }""", clip)
            self.assertEqual(got.get("stars"), 4, got)
            got = pg.evaluate("""async (p) => {
              const r = await fetch("api/photo", {method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({do: "tag", path: p, value: "holiday"})});
              return await r.json(); }""", clip)
            self.assertIn("holiday", got.get("tags") or [], got)
            # beside it, not inside it
            self.assertTrue(os.path.exists(os.path.splitext(clip)[0] + ".xmp"))
            # and the viewer offers the marks for it
            self.assertTrue(pg.evaluate("(p) => editable(p)", clip))
        self.page(work)
        os.remove(clip)
        side = os.path.splitext(clip)[0] + ".xmp"
        if os.path.exists(side):
            os.remove(side)

    def test_with_nothing_running_it_asks_what_is_running_rarely(self):
        """It asked every 0.7 s whatever was happening - all night, in a tab
        nobody was looking at. Idle, it is every 2.5 s."""
        def work(pg):
            asked = []
            pg.on("request", lambda r: asked.append(r.url)
                  if "/api/jobs" in r.url else None)
            pg.wait_for_timeout(5000)
            self.assertLessEqual(len(asked), 3, asked)
        self.page(work)

    def test_a_hidden_tab_does_not_ask_at_all_and_asks_at_once_when_shown(self):
        def work(pg):
            asked = []
            pg.on("request", lambda r: asked.append(r.url)
                  if any(k in r.url for k in ("/api/jobs", "/api/health",
                                              "/api/index")) else None)
            pg.evaluate("""() => {
              Object.defineProperty(document, "hidden",
                {configurable: true, get: () => window.__hide === true});
              window.__hide = true;
              document.dispatchEvent(new Event("visibilitychange")); }""")
            pg.wait_for_timeout(300)
            asked.clear()
            pg.wait_for_timeout(5500)
            self.assertEqual(asked, [], "a hidden tab kept asking")
            pg.evaluate("""() => { window.__hide = false;
              document.dispatchEvent(new Event("visibilitychange")); }""")
            pg.wait_for_timeout(400)
            self.assertTrue(any("/api/jobs" in u for u in asked), asked)
            self.assertTrue(any("/api/health" in u for u in asked), asked)
        self.page(work)

    def test_the_rail_says_how_many_files_could_not_be_read(self):
        def work(pg):
            said = pg.evaluate("""() => {
              IDX = Object.assign({}, IDX, {building: false, photos: 5,
                unreadable: 1, unreadable_names: [{path: "/x/a.JPG",
                error: "Permission denied"}]});
              drawRail();
              return document.getElementById("railfoot").innerText; }""")
            self.assertIn("1 file could not be read", said)
        self.page(work)

    def test_the_worker_keeps_and_serves_the_page_it_was_sent_packed(self):
        """The page goes gzipped now. The worker keeps what the browser
        unpacked, so the copy it serves with the NAS out of reach is the page,
        not a packed blob."""
        def work(pg):
            ok = pg.evaluate("""async () => {
              if (!('serviceWorker' in navigator)) return "no worker";
              await navigator.serviceWorker.ready;
              for (let i = 0; i < 50; i++){
                const had = await caches.match("./");
                if (had) return (await had.text()).includes("<title>Photo Manager");
                await new Promise(r => setTimeout(r, 100));
              }
              return "never kept"; }""")
            if ok == "no worker":
                self.skipTest("no service worker in this browser")
            self.assertIs(ok, True, ok)
            packed = pg.evaluate("""async () => {
              const r = await fetch("./?t=" + Date.now());
              return r.headers.get("content-encoding"); }""")
            self.assertEqual(packed, "gzip")
            if not pg.evaluate("() => !!navigator.serviceWorker.controller"):
                pg.reload()
                pg.wait_for_function("() => !!navigator.serviceWorker.controller",
                                     timeout=10000)
            pg.context.set_offline(True)
            try:
                # Asked through the worker rather than by reloading, so the page
                # under test is not the one that then cannot reach the app.
                got = pg.evaluate("""async () => {
                  const r = await fetch("./?offline=" + Date.now());
                  return [r.status, await r.text()]; }""")
            finally:
                pg.context.set_offline(False)
            self.assertEqual(got[0], 200)
            self.assertIn("<title>Photo Manager</title>", got[1])
        self.page(work)

    # ------------------------------------------------------- Setup > Wording

    def test_the_wording_tab_edits_a_tool_in_place(self):
        """Behind the developer switch: pick a tool, type over its title, leave
        the box, and the title is saved and the tool's own entry says it."""
        from core import settings as _settings
        from core import wording as _wording
        _settings.save({"developer": True})
        _wording.forget()
        try:
            def work(pg):
                pg.evaluate("() => refreshTasks()")
                pg.wait_for_function(
                    "() => TASKS.some(t => t.name === 'wording')", timeout=8000)
                self.open_tab(pg, "wording")
                pg.wait_for_selector("#wdtask", timeout=15000)
                pg.select_option("#wdtask", "cull")
                pg.wait_for_selector('.wdcard[data-key="cull.title"] input',
                                     timeout=8000)
                box = '.wdcard[data-key="cull.title"] input'
                pg.fill(box, "Weed by stars")
                pg.click("#wdq")
                pg.wait_for_selector('.wdcard.edited[data-key="cull.title"]',
                                     timeout=8000)
                pg.wait_for_function(
                    "() => (TASKS.find(t => t.name === 'cull') || {}).title"
                    " === 'Weed by stars'", timeout=8000)
                self.assertEqual(_wording.load(), {"cull.title": "Weed by stars"})
                # five words is a sentence, and the card says why it was not kept
                label = '.wdcard[data-key="cull.option.folder.label"] input'
                pg.fill(label, "The folder to cull from")
                pg.click("#wdq")
                pg.wait_for_selector(".wdsaid .bad", timeout=8000)
                self.assertIn("at most 4 words", pg.text_content(".wdsaid .bad"))
                pg.click('.wdcard[data-key="cull.title"] button:has-text("Reset to shipped")')
                pg.wait_for_function(
                    "() => !document.querySelector('.wdcard.edited')", timeout=8000)
                self.assertEqual(_wording.load(), {})
            self.page(work)
        finally:
            _settings.save({"developer": False})
            _wording.write({})

    def test_a_page_string_and_a_guide_page_edited_there_show_on_the_page(self):
        """The page's own words are a table the server fills as it sends the
        page; an edit reads in the very next page load, and say() counts."""
        from core import wording as _wording
        _wording.write({"page.notSaved": "Kept back.",
                        "guide.welcome.title": "Hello there"})
        try:
            def work(pg):
                self.assertEqual(pg.evaluate("() => S.notSaved"), "Kept back.")
                self.assertEqual(pg.evaluate("() => GUIDE[0].title"), "Hello there")
                self.assertEqual(pg.evaluate("() => say('nFiles', {n: 1})"), "1 file")
                self.assertEqual(pg.evaluate("() => say('nFiles', {n: 1200})"),
                                 "1,200 files")
            self.page(work)
        finally:
            _wording.write({})


@unittest.skipUnless(a_browser()[0], "no browser here - source checks still apply")
class AFreshInstall(unittest.TestCase):
    """Nothing set up at all: an empty settings folder and no library."""

    page = InABrowser.page

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="page-fresh-")
        cls._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(cls.dir, "config")
        from core import catalogue as _cat
        _cat.forget_all()
        from app import server as S
        import app.tasks                                       # noqa: F401
        S.ALLOWED_ROOTS[:] = []
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}/"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        from core import catalogue as _cat
        _cat.forget_all()
        if cls._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = cls._was
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_it_opens_on_the_checklist(self):
        def work(pg):
            pg.wait_for_timeout(500)
            self.assertEqual(pg.evaluate("() => SCREEN"), "feature")
            self.assertEqual(pg.evaluate("() => CURRENT && CURRENT.name"),
                             "checklist")
        self.page(work)

    def test_home_with_no_library_offers_setup_and_a_sample(self):
        def work(pg):
            pg.evaluate("() => goScreen('home')")
            pg.wait_for_selector("#homefirst", timeout=10000)
            said = pg.eval_on_selector("#homefirst", "e => e.innerText")
            self.assertIn("Open Setup", said)
            self.assertIn("Build a sample library", said)
            foot = pg.eval_on_selector("#railfoot", "e => e.innerText")
            self.assertIn("Open Setup", foot)
            self.assertIn("Build a sample library", foot)
            pg.click("#homefirst button:has-text('Open Setup')")
            pg.wait_for_timeout(300)
            self.assertEqual(pg.evaluate("() => CURRENT.name"), "setup")
        self.page(work)


if __name__ == "__main__":
    unittest.main()
