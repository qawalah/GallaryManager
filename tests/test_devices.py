"""What a camera is called, against the code it writes into the file."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.tasks  # noqa: E402,F401
from app.tasks import cameras as C                # noqa: E402
from core import devices as D                     # noqa: E402
from core import settings as S                    # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="devices-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        os.makedirs(os.environ["PM_DATA"])
        self.lib = os.path.join(self.dir, "Photos")
        self.shoot = os.path.join(self.lib, "2022")
        os.makedirs(self.shoot)
        S.save({"library": self.lib})
        shutil.copy(os.path.join(FIX, "aeb1.jpg"),
                    os.path.join(self.shoot, "a.JPG"))

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)


class WhatItIsCalled(_Tmp):
    def test_a_code_this_app_knows_gets_a_name_and_admits_it_guessed(self):
        self.assertEqual(D.name_of("iPhone14,2"), "iPhone 13 Pro")
        self.assertEqual(D.how("iPhone14,2"), "guessed")
        # and the code stays beside it, because a guessed name that looks
        # authoritative is a small lie that takes an hour to catch
        self.assertEqual(D.label("iPhone14,2"), "iPhone 13 Pro (iPhone14,2)")

    def test_a_code_it_does_not_know_is_left_exactly_as_it_is(self):
        self.assertEqual(D.name_of("NIKON Z9"), "NIKON Z9")
        self.assertEqual(D.how("NIKON Z9"), "")
        self.assertEqual(D.label("NIKON Z9"), "NIKON Z9")

    def test_the_market_letter_on_a_samsung_code_is_not_a_different_phone(self):
        """SM-G991B, SM-G991U and SM-G991N are one phone sold in three places,
        and three legend entries for one phone is the problem this fixes."""
        for code in ("SM-G991B", "SM-G991U", "SM-G991N", "sm-g991"):
            self.assertEqual(D.name_of(code), "Galaxy S21", code)

    def test_what_you_call_it_beats_any_guess(self):
        D.rename("iPhone14,2", "the old phone")
        self.assertEqual(D.name_of("iPhone14,2"), "the old phone")
        self.assertEqual(D.how("iPhone14,2"), "yours")
        self.assertEqual(D.label("iPhone14,2"), "the old phone (iPhone14,2)")

    def test_naming_one_samsung_names_that_phone_wherever_it_was_sold(self):
        D.rename("SM-G991B", "Hana's phone")
        self.assertEqual(D.name_of("SM-G991U"), "Hana's phone")

    def test_an_empty_name_puts_the_code_back(self):
        D.rename("NIKON Z9", "the big one")
        self.assertEqual(D.name_of("NIKON Z9"), "the big one")
        D.rename("NIKON Z9", "")
        self.assertEqual(D.name_of("NIKON Z9"), "NIKON Z9")
        self.assertEqual(D.saved(), {})

    def test_a_nameless_or_enormous_rename_is_refused(self):
        with self.assertRaises(ValueError):
            D.rename("", "something")
        with self.assertRaises(ValueError):
            D.rename("NIKON Z9", "x" * 61)

    def test_it_answers_to_the_code_and_to_the_name(self):
        """A rename that made the library harder to search would be a bad
        trade."""
        D.rename("SM-G991B", "Hana's phone")
        self.assertTrue(D.matches("SM-G991B", "sm-g991"))
        self.assertTrue(D.matches("SM-G991B", "hana"))
        self.assertTrue(D.matches("iPhone14,2", "iphone 13"))     # the guess
        self.assertFalse(D.matches("SM-G991B", "pixel"))

    def test_nothing_is_ever_written_to_a_photograph(self):
        before = open(os.path.join(self.shoot, "a.JPG"), "rb").read()
        D.rename("DMC-GH4", "the video one")
        after = open(os.path.join(self.shoot, "a.JPG"), "rb").read()
        self.assertEqual(before, after)


class SearchingWithNames(_Tmp):
    def test_a_search_finds_a_camera_by_the_name_you_gave_it(self):
        from core import find
        D.rename("DMC-GH4", "the video one")
        hits = find.search([self.lib], find.from_dict({"camera": "video one"}))
        self.assertEqual(len(hits.hits), 1)
        # and by the code the file actually carries
        hits = find.search([self.lib], find.from_dict({"camera": "dmc-gh4"}))
        self.assertEqual(len(hits.hits), 1)


class TheTab(_Tmp):
    def test_it_lists_the_cameras_in_the_library_with_where_the_name_came_from(self):
        p = C.plan({"folders": ""})
        self.assertEqual([r.name for r in p.rows], ["DMC-GH4"])
        self.assertEqual(p.rows[0].data["name"], "Lumix GH4")
        self.assertEqual(p.rows[0].data["how"], "guessed")

    def test_a_name_you_gave_shows_as_yours(self):
        D.rename("DMC-GH4", "the video one")
        p = C.plan({"folders": ""})
        self.assertEqual(p.rows[0].data["how"], "yours")
        self.assertIn("you named it", p.rows[0].cells[1])

    def test_a_name_for_a_camera_no_longer_in_the_library_is_still_listed(self):
        """Otherwise it sits in the settings for ever with no way to clear it."""
        D.rename("SM-G991B", "the old phone")
        p = C.plan({"folders": ""})
        names = [r.name for r in p.rows]
        self.assertIn("sm-g991", names)          # kept per family, not per market
        stale = [r for r in p.rows if r.name == "sm-g991"][0]
        self.assertIn("nothing in the library uses it", stale.cells[1])

    def test_the_tab_writes_nothing_itself(self):
        self.assertEqual(C.apply(C.plan({"folders": ""})).done, 0)


if __name__ == "__main__":
    unittest.main()
