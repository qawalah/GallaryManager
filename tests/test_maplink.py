"""Reading a coordinate out of a pasted link.

Every string here is one a real address bar or share button produces. The two
that matter most are the Google `place/` link, where the obvious number is the
wrong one, and the shortened link, which contains no coordinate at all and must
be said so rather than guessed at.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from core import maplink as M              # noqa: E402
from core.photo import read_gps            # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class LinksThatWork(unittest.TestCase):
    def near(self, text, lat, lon):
        p = M.read(text)
        self.assertTrue(p.ok, f"{text!r} -> {p.why}")
        self.assertAlmostEqual(p.lat, lat, places=4)
        self.assertAlmostEqual(p.lon, lon, places=4)
        return p

    def test_a_map_centred_somewhere(self):
        self.near("https://www.google.com/maps/@24.4678,39.6111,15z", 24.4678, 39.6111)

    def test_a_place_link_prefers_the_place_over_the_map_centre(self):
        """The @ part is where the map happened to be; !3d/!4d is the place itself."""
        p = self.near(
            "https://www.google.com/maps/place/Somewhere/@24.4672,39.6112,17z/"
            "data=!3m1!4b1!4m6!3m5!8m2!3d24.4709!4d39.6200",
            24.4709, 39.6200)
        self.assertIn("place", p.how)

    def test_the_query_forms(self):
        self.near("https://maps.google.com/?q=24.4672,39.6112", 24.4672, 39.6112)
        self.near("https://www.google.com/maps/search/?api=1&query=24.4672,39.6112",
                  24.4672, 39.6112)

    def test_apple_maps(self):
        self.near("https://maps.apple.com/?ll=24.4672,39.6112&q=Madinah", 24.4672, 39.6112)

    def test_openstreetmap(self):
        self.near("https://www.openstreetmap.org/#map=17/24.46720/39.61120",
                  24.4672, 39.6112)

    def test_a_geo_link_from_a_phone(self):
        self.near("geo:24.4672,39.6112", 24.4672, 39.6112)

    def test_just_the_numbers_which_is_what_right_click_copy_gives_you(self):
        self.near("24.4672, 39.6112", 24.4672, 39.6112)

    def test_the_southern_and_western_hemispheres(self):
        self.near("-33.8688, 151.2093", -33.8688, 151.2093)
        self.near("https://www.google.com/maps/@-22.9519,-43.2105,15z", -22.9519, -43.2105)

    def test_stray_brackets_and_spaces_do_not_matter(self):
        self.near("  <https://maps.google.com/?q=24.4672,39.6112>  ", 24.4672, 39.6112)


class LinksThatDoNot(unittest.TestCase):
    def refused(self, text):
        p = M.read(text)
        self.assertFalse(p.ok)
        self.assertTrue(p.why, "a refusal must say why")
        return p

    def test_a_shortened_link_is_named_as_such_rather_than_guessed_at(self):
        p = self.refused("https://maps.app.goo.gl/aBcDeF123")
        self.assertIn("shortened", p.why)
        self.assertIn("address bar", p.why)

    def test_ordinary_text(self):
        self.refused("the mosque in Madinah")

    def test_nothing_at_all(self):
        self.refused("")
        self.refused("   ")

    def test_null_island_is_refused(self):
        """0,0 is what a broken reading collapses to, not a place anyone shot."""
        self.refused("0, 0")
        self.refused("https://maps.google.com/?q=0.0,0.0")

    def test_numbers_that_are_not_on_earth(self):
        self.refused("95.0, 200.0")
        self.refused("https://www.google.com/maps/@100.5,-400.5,15z")


class ThePinTask(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pin-")
        for n in ("burst1", "burst2"):
            shutil.copy(os.path.join(FIX, f"{n}.jpg"), os.path.join(self.dir, f"{n}.JPG"))
        shutil.copy(os.path.join(FIX, "phone_doha.jpg"),
                    os.path.join(self.dir, "phone.JPG"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def plan(self, **over):
        t = R.get("pin")
        return t, t.make_plan({"folder": self.dir, "link": "24.4672, 39.6112", **over})

    def test_it_places_the_photos_that_have_no_location(self):
        t, p = self.plan()
        self.assertEqual(len(p.rows), 2)
        r = t.apply(p)
        self.assertEqual(r.failed, 0)
        got = read_gps(os.path.join(self.dir, "burst1.JPG"))
        self.assertTrue(got.has_gps)
        self.assertAlmostEqual(got.lat, 24.4672, places=4)

    def test_a_photo_that_already_knows_where_it_was_is_left_alone(self):
        _, p = self.plan()
        self.assertTrue(any("phone" in n for n, _why in p.skipped))

    def test_unless_you_ask_to_replace(self):
        _, p = self.plan(replace="on")
        self.assertEqual(len(p.rows), 3)
        self.assertTrue(any("replacing a fix" in r.detail for r in p.rows))

    def test_every_row_is_marked_approximate_because_it_is(self):
        _, p = self.plan()
        self.assertTrue(all(r.approximate for r in p.rows))

    def test_a_link_it_cannot_read_stops_the_task_with_the_reason(self):
        _, p = self.plan(link="https://maps.app.goo.gl/xyz")
        self.assertTrue(p.blocked)
        self.assertIn("shortened", p.blocked)
        self.assertEqual(p.rows, [])

    def test_planning_writes_nothing(self):
        before = {n: os.path.getmtime(os.path.join(self.dir, n))
                  for n in os.listdir(self.dir)}
        self.plan()
        after = {n: os.path.getmtime(os.path.join(self.dir, n))
                 for n in os.listdir(self.dir)}
        self.assertEqual(before, after)

    def test_a_sidecar_run_never_opens_the_photo(self):
        t, p = self.plan(sidecar_only="on")
        was = os.path.getmtime(os.path.join(self.dir, "burst1.JPG"))
        t.apply(p)
        self.assertTrue(os.path.isfile(os.path.join(self.dir, "burst1.xmp")))
        self.assertEqual(os.path.getmtime(os.path.join(self.dir, "burst1.JPG")), was)


if __name__ == "__main__":
    unittest.main()
