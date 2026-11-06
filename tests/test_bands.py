"""The brackets a chart groups values into - and changing them.

The point of this file is that the edges are not a constant. Setup can replace
any set, everything that counts has to pick the change up without a restart,
and a table that does not make sense has to be refused with the reason rather
than half-saved.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import bands as B                   # noqa: E402
from core import settings as S                # noqa: E402
from core import stats as ST                  # noqa: E402
from core.photo import Capture                # noqa: E402


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="bands-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        os.makedirs(os.environ["PM_DATA"])
        S.save({"library": self.dir})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)


class OutOfTheBox(_Tmp):
    def test_every_set_has_a_name_a_unit_and_at_least_two_bands(self):
        for name in B.ORDER:
            self.assertIn(name, B.BUILTIN, name)
            self.assertIn(name, B.ABOUT, name)
            self.assertGreaterEqual(len(B.table(name)), 2, name)
            self.assertEqual(B.how(name), "built in", name)

    def test_the_edges_climb_in_every_built_in_set(self):
        """A table whose edges did not climb would put values in the first band
        that happened to catch them, which is a chart that is wrong quietly."""
        for name in B.ORDER:
            tops = [top for _label, top in B.table(name)]
            self.assertEqual(tops, sorted(tops), name)

    def test_a_value_lands_in_the_first_band_it_is_under(self):
        self.assertEqual(B.band(2.8, "aperture"), "f/2.8")
        self.assertEqual(B.band(1.4, "aperture"), "f/1.4 and wider")
        self.assertEqual(B.band(6400, "iso"), "6400 and over")

    def test_anything_unreadable_is_never_put_in_a_band(self):
        """f/0 is not an aperture, and a chart that folded it into the widest
        one would be lying tidily."""
        self.assertEqual(B.band(None, "aperture"), "not said")
        self.assertEqual(B.band("", "iso"), "not said")
        self.assertEqual(B.band("wide", "focal"), "not said")

    def test_shutter_speeds_read_back_as_the_fractions_they_are_said_as(self):
        self.assertIn("1/500 = 1/400", B.as_text("shutter"))


class ChangingThem(_Tmp):
    def test_what_you_type_replaces_the_built_in_set(self):
        B.save("aperture", "wide = 3.0\nmiddling = 8.0\nsmall = 1e9")
        self.assertEqual(B.how("aperture"), "yours")
        self.assertEqual(B.band(2.8, "aperture"), "wide")
        self.assertEqual(B.band(11, "aperture"), "small")

    def test_an_empty_text_puts_the_built_in_set_back(self):
        B.save("iso", "low = 400\nhigh = 1e9")
        B.save("iso", "")
        self.assertEqual(B.how("iso"), "built in")
        self.assertEqual(B.band(100, "iso"), "100 and under")

    def test_typing_the_built_in_set_back_in_is_not_called_yours(self):
        B.save("hour", B.as_text("hour"))
        self.assertEqual(B.how("hour"), "built in")

    def test_a_fraction_is_a_fair_way_to_write_a_shutter_edge(self):
        B.save("shutter", "fast = 1/250\nslow = 1e9")
        self.assertEqual(B.band(1 / 1000, "shutter"), "fast")
        self.assertEqual(B.band(1, "shutter"), "slow")

    def test_edges_that_do_not_climb_are_refused_and_say_which_line(self):
        with self.assertRaises(ValueError) as caught:
            B.save("iso", "low = 800\nhigh = 400\ntop = 1e9")
        self.assertIn("line 2", str(caught.exception))
        self.assertEqual(B.how("iso"), "built in")   # and nothing was kept

    def test_the_other_ways_of_getting_it_wrong(self):
        for text, why in [("one band = 5", "at least two"),
                          ("no edge here\nsecond = 9", "name = up to"),
                          (" = 5\nsecond = 9", "no name"),
                          ("a = five\nb = 9", "not a number"),
                          ("same = 5\nsame = 9", "same name")]:
            with self.assertRaises(ValueError, msg=text) as caught:
                B.save("focal", text)
            self.assertIn(why.split()[0], str(caught.exception), text)

    def test_a_set_nobody_has_heard_of_is_refused(self):
        with self.assertRaises(ValueError):
            B.save("hairstyle", "a = 1\nb = 2")

    def test_blank_lines_and_comments_are_allowed(self):
        B.save("focal", "# my lenses\n\nshort = 40\n\nlong = 1e9\n")
        self.assertEqual([label for label, _ in B.table("focal")],
                         ["short", "long"])


class WhatUsesThem(_Tmp):
    def test_counting_follows_the_edges_you_set_without_a_restart(self):
        """The whole point. stats used to bind the tables at import, so a
        change in Setup did nothing until the container was restarted."""
        hit = type("Hit", (), {"taken": "", "camera": "", "lens": "",
                               "fnumber": 2.8, "iso": 0, "seconds": 0,
                               "focal_length": 0, "focal35": 0, "path": "x"})()
        self.assertEqual(ST.buckets_of(hit, "aperture"), ["f/2.8"])
        B.save("aperture", "wide = 4.0\nsmall = 1e9")
        self.assertEqual(ST.buckets_of(hit, "aperture"), ["wide"])

    def test_the_order_a_chart_draws_them_in_follows_too(self):
        B.save("iso", "dim = 400\nbright = 1e9")
        self.assertEqual(ST.given("iso"), ["dim", "bright"])

    def test_the_search_a_bucket_means_follows_the_edges(self):
        B.save("aperture", "wide = 4.0\nsmall = 1e9")
        ask = ST.ask_for("aperture", "wide")
        self.assertEqual(ask.get("f_to"), 3.99)

    def test_a_lens_range_prefers_the_full_frame_equivalent_and_says_so(self):
        """The GH4 doubles every focal length, so 25mm on it and 50mm on the
        A7C frame the same and belong in the same band."""
        self.assertEqual(B.lens_range(Capture(path="x", focal_length=25.0,
                                              focal35=50.0)),
                         ("Normal (36-70mm)", "full-frame equivalent"))
        self.assertEqual(B.lens_range(Capture(path="x", focal_length=25.0)),
                         ("Wide (24-35mm)", "the number on the lens"))
        self.assertEqual(B.lens_range(Capture(path="x")), ("", ""))


if __name__ == "__main__":
    unittest.main()
