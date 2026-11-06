"""Folder patterns: any combination of variables, at any depth, kept by name."""

import datetime as dt
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import naming as N                     # noqa: E402
from core import places                          # noqa: E402

WHEN = dt.datetime(2022, 7, 14, 10, 30)


def spain(city="Barcelona", region="Catalonia"):
    return places.Place(country="Spain", city=city, code="ES", region=region)


class Rendering(unittest.TestCase):
    def v(self, **kw):
        return N.facts(WHEN, kw.pop("place", spain()), kw.pop("camera", "DMC-GH4"),
                       kw.pop("lens", ""), kw.pop("shoot", None))

    def test_several_variables_in_one_folder_and_several_levels(self):
        got = N.render("{year}/{month} {monthname} - {city}/{camera}", self.v())
        self.assertEqual(got, "2022/07 July - Barcelona/DMC-GH4")

    def test_an_empty_value_takes_its_separator_with_it(self):
        v = self.v(place=spain(region=""))
        self.assertEqual(N.render("{country} - {region} - {city}", v), "Spain - Barcelona")
        self.assertEqual(N.render("{region} - {city}", v), "Barcelona")
        self.assertEqual(N.render("{city} ({region})", v), "Barcelona")
        self.assertEqual(N.render("{year}/{region}/{city}", v), "2022/Barcelona")

    def test_no_country_means_no_folder_for_a_place_pattern(self):
        v = N.facts(WHEN, places.Place())
        self.assertEqual(N.render("{year}/{country}", v), "")
        self.assertEqual(N.render("{year}/{month}", v), "2022/07")

    def test_no_date_means_no_folder_for_a_date_pattern(self):
        self.assertEqual(N.render("{year}", N.facts(None, spain())), "")
        self.assertEqual(N.render("{country}", N.facts(None, spain())), "Spain")

    def test_a_known_country_with_no_town_is_unsure(self):
        v = self.v(place=spain(city=""))
        self.assertEqual(N.render("{country}/{city}", v), "Spain/_Unsure")

    def test_a_slash_or_a_bad_character_in_a_value_cannot_make_a_folder(self):
        v = self.v(lens="LUMIX G 25/F1.7", camera='A:B*"C')
        self.assertEqual(N.render("{lens}", v), "LUMIX G 25 F1.7")
        self.assertEqual(N.render("{camera}", v), "ABC")

    def test_the_shoot_range(self):
        shoot = (dt.datetime(2022, 7, 12), dt.datetime(2022, 7, 15))
        v = self.v(shoot=shoot)
        self.assertEqual(N.render("{rangestart} {range}", v), "2022-07-12 12-15 Jul")
        self.assertEqual(N.spell_range(dt.datetime(2022, 7, 28), dt.datetime(2022, 8, 2)),
                         "28 Jul - 02 Aug")

    def test_shoots_split_on_a_quiet_day(self):
        t = [dt.datetime(2022, 7, 12, 9), dt.datetime(2022, 7, 13, 8),
             dt.datetime(2022, 7, 20, 9)]
        got = N.shoots_of(t, 24)
        self.assertEqual(got[t[0]], (t[0], t[1]))
        self.assertEqual(got[t[2]], (t[2], t[2]))

    def test_problems_are_said(self):
        self.assertIn("{yr}", N.problem("{yr}/x"))
        self.assertTrue(N.problem(""))
        self.assertTrue(N.problem("Holidays"))
        self.assertEqual(N.problem("{year}/{country} - {city}"), "")

    def test_every_old_shape_still_means_what_it_did(self):
        for key, pattern in N.LEGACY.items():
            self.assertEqual(N.problem(pattern), "", key)


class Keeping(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="naming-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = self.dir

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_keep_use_and_forget(self):
        N.keep("Trips", "{year}/{rangestart} {country}")
        self.assertEqual(N.pattern_for("saved:trips"), "{year}/{rangestart} {country}")
        from app.tasks.bydate import shapes
        self.assertIn("saved:Trips", [s[0] for s in shapes()])
        N.forget("Trips")
        self.assertEqual(N.pattern_for("saved:Trips"), "")

    def test_a_broken_pattern_is_not_kept(self):
        with self.assertRaises(ValueError):
            N.keep("Bad", "{nope}")
        self.assertEqual(N.saved(), [])

    def test_the_sort_uses_a_custom_pattern(self):
        from app.tasks import bydate
        lib = os.path.join(self.dir, "Photos")
        os.makedirs(lib)
        fix = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
        shutil.copy(os.path.join(fix, "rated.jpg"), os.path.join(lib, "a.jpg"))
        p = bydate.plan({"folder": lib, "shape": "custom",
                         "pattern": "{year}/{monthname} {day}", "mirror": False})
        self.assertFalse(p.blocked, p.blocked)
        target = [r.target for r in p.rows if r.name == "a.jpg"]
        if target:
            self.assertRegex(target[0].replace(os.sep, "/"), r"/\d{4}/[A-Z][a-z]+ \d\d/a\.jpg$")

    def test_a_custom_pattern_that_cannot_work_blocks_the_plan(self):
        from app.tasks import bydate
        p = bydate.plan({"folder": self.dir, "shape": "custom", "pattern": "{nope}"})
        self.assertIn("{nope}", p.blocked)


if __name__ == "__main__":
    unittest.main()
