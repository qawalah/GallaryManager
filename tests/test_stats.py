"""Counting the library along one axis, and along two at once."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.tasks  # noqa: E402,F401
from app.tasks import compare as C                # noqa: E402
from app.tasks import library as L                # noqa: E402
from core import settings as S                    # noqa: E402
from core import stats as ST                      # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="stats-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        os.makedirs(os.environ["PM_DATA"])
        self.lib = os.path.join(self.dir, "share", "Photos")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        S.save({"library": self.lib})
        for n in range(3):
            shutil.copy(os.path.join(FIX, "aeb1.jpg"),
                        os.path.join(self.shoot, f"a{n}.JPG"))

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def rows(self, got, dim):
        return [(name, n) for name, n, _size in got.counts[dim].rows]


class OneAxis(_Tmp):
    def test_the_usual_axes_come_back_counted(self):
        got = ST.tally([self.lib], ["year", "camera", "aperture", "iso",
                                    "focal", "stars", "located", "kind"])
        self.assertEqual(got.photos, 3)
        self.assertEqual(self.rows(got, "year"), [("2022", 3)])
        # the camera is named, with the code it writes in brackets
        self.assertEqual(self.rows(got, "camera"), [("Lumix GH4 (DMC-GH4)", 3)])
        self.assertEqual(self.rows(got, "aperture"), [("f/5.6", 3)])
        self.assertEqual(self.rows(got, "iso"), [("200", 3)])
        self.assertEqual(self.rows(got, "focal"), [("24-35mm", 3)])
        self.assertEqual(self.rows(got, "stars"), [("no stars", 3)])
        self.assertEqual(self.rows(got, "located"), [("none on it", 3)])
        self.assertEqual(self.rows(got, "kind"), [("JPEG", 3)])

    def test_a_file_that_cannot_answer_is_its_own_bucket_never_zero(self):
        """f/0 is not an aperture, and ISO 0 is not a speed. Folding an unknown
        into the smallest real bucket is a chart that lies tidily."""
        bare = os.path.join(self.shoot, "bare.JPG")
        with open(bare, "wb") as fh:
            fh.write(b"\xff\xd8\xff\xdb" + b"\0" * 200 + b"\xff\xd9")
        got = ST.tally([self.lib], ["aperture", "iso", "year", "camera"])
        for dim in ("aperture", "iso", "year", "camera"):
            self.assertIn(ST.UNSAID, [r[0] for r in got.counts[dim].rows], dim)
            self.assertEqual(got.counts[dim].unsaid, 1, dim)

    def test_not_said_is_sorted_last_whatever_the_axis(self):
        bare = os.path.join(self.shoot, "bare.JPG")
        with open(bare, "wb") as fh:
            fh.write(b"\xff\xd8\xff\xdb" + b"\0" * 200 + b"\xff\xd9")
        for dim in ("aperture", "year", "camera"):
            got = ST.tally([self.lib], [dim])
            self.assertEqual(got.counts[dim].rows[-1][0], ST.UNSAID, dim)

    def test_stars_and_colour_come_from_the_marks(self):
        from core import quickedit as QE
        QE.set_stars(os.path.join(self.shoot, "a0.JPG"), 4)
        QE.set_colour(os.path.join(self.shoot, "a1.JPG"), "red")
        got = ST.tally([self.lib], ["stars", "colour"])
        self.assertIn(("4", 1), self.rows(got, "stars"))
        self.assertIn(("no stars", 2), self.rows(got, "stars"))
        self.assertIn(("red", 1), self.rows(got, "colour"))

    def test_a_tag_puts_a_photo_in_more_than_one_bucket(self):
        """Which is what a tag is - and the alternative is a number that adds
        up while saying something false."""
        from core import quickedit as QE
        one = os.path.join(self.shoot, "a0.JPG")
        QE.add_tag(one, "spain")
        QE.add_tag(one, "street")
        got = ST.tally([self.lib], ["tag"])
        said = dict(self.rows(got, "tag"))
        self.assertEqual(said["spain"], 1)
        self.assertEqual(said["street"], 1)
        self.assertEqual(said["no tags"], 2)
        self.assertGreater(sum(said.values()), got.photos)

    def test_the_tail_is_folded_rather_than_given_a_ninth_colour(self):
        counted = ST.Counted(rows=[(str(i), 10 - i, 0) for i in range(12)])
        top = counted.top(8)
        self.assertEqual(len(top), 8)
        self.assertEqual(top[-1][0], "everything else")
        self.assertEqual(sum(r[1] for r in top),
                         sum(r[1] for r in counted.rows))

    def test_named_leaves_not_said_out(self):
        counted = ST.Counted(rows=[("A7c", 3, 0), (ST.UNSAID, 2, 0), ("GH4", 1, 0)])
        self.assertEqual(counted.named(), 2)
        self.assertEqual(ST.Counted(rows=[]).named(), 0)

    def test_the_given_order_is_kept_not_sorted_by_size(self):
        got = ST.tally([self.lib], ["aperture"])
        names = [r[0] for r in got.counts["aperture"].rows]
        rank = [ST.given("aperture").index(n) for n in names if n in ST.given("aperture")]
        self.assertEqual(rank, sorted(rank))


class TwoAxes(_Tmp):
    def test_every_photograph_lands_in_one_cell(self):
        got = ST.tally([self.lib], ["year", "aperture"],
                       cross=("year", "aperture"))
        grid = got.cross
        self.assertEqual(grid["rows"], ["2022"])
        self.assertEqual(grid["cols"], ["f/5.6"])
        self.assertEqual(sum(sum(r) for r in grid["grid"]), got.photos)

    def test_a_grid_is_trimmed_to_what_can_be_read(self):
        cross = {"down": "a", "across": "b", "down_label": "A",
                 "across_label": "B",
                 "rows": [f"r{i}" for i in range(20)],
                 "cols": [f"c{j}" for j in range(20)],
                 "grid": [[i + j for j in range(20)] for i in range(20)]}
        kept = ST.trim(cross, 5)
        self.assertEqual(len(kept["rows"]), 5)
        self.assertEqual(len(kept["cols"]), 5)
        self.assertGreater(kept["left_out"], 0)
        # the biggest rows and columns are the ones kept
        self.assertEqual(kept["rows"], [f"r{i}" for i in range(15, 20)])

    def test_each_edge_of_the_grid_carries_its_own_search(self):
        got = ST.tally([self.lib], ["year", "aperture"],
                       cross=("year", "aperture"))
        kept = ST.trim(got.cross)
        self.assertEqual(kept["row_asks"][0],
                         {"since": "2022-01-01", "until": "2022-12-31"})
        self.assertIn("f_from", kept["col_asks"][0])

    def test_the_tab_refuses_a_grid_of_something_against_itself(self):
        p = C.plan({"folders": "", "down": "year", "across": "year"})
        self.assertIn("two different", p.blocked)

    def test_the_tab_gives_the_grid_and_the_two_axes_on_their_own(self):
        p = C.plan({"folders": "", "down": "year", "across": "aperture"})
        self.assertEqual(p.charts["cross"]["rows"], ["2022"])
        self.assertEqual([c["title"] for c in p.charts["charts"]],
                         ["Year", "Aperture"])
        # and the same numbers as a table, because a colour scale is not
        # readable to everybody
        self.assertEqual(p.columns[0], "Down / across")
        self.assertEqual(p.rows[0].cells[-1], "3")

    def test_the_tab_writes_nothing(self):
        self.assertEqual(C.apply(C.plan({"folders": ""})).done, 0)


class TheDashboard(_Tmp):
    def test_the_library_page_carries_tiles_charts_and_meters(self):
        p = L.plan({"folder": self.lib})
        got = p.charts
        self.assertTrue(got["tiles"])
        self.assertEqual(got["tiles"][0]["label"], "Photos")
        self.assertEqual(got["tiles"][0]["value"], "3")
        titles = [c["title"] for c in got["charts"]]
        for wanted in ("Where the space is", "Which camera", "Aperture",
                       "Stars", "Location"):
            self.assertIn(wanted, titles)
        self.assertTrue(any(row[0] == "Rated" for row in got["done"]))

    def test_the_cameras_tile_counts_cameras_not_the_photos_that_name_none(self):
        """A photo with no camera in it is "not said" on the chart, not one more
        camera on the tile beside it."""
        for name in ("phone_doha", "noexif"):
            shutil.copy(os.path.join(FIX, f"{name}.jpg"),
                        os.path.join(self.shoot, f"{name}.JPG"))
        tiles = {t["widget"]: t for t in L.plan({"folder": self.lib}).charts["tiles"]}
        self.assertEqual(tiles["tile:cameras"]["value"], "2")

    def test_every_chart_carries_its_own_rows_so_the_page_draws_nothing_itself(self):
        p = L.plan({"folder": self.lib})
        for chart in p.charts["charts"]:
            self.assertIn(chart["kind"], ("donut", "bars"))
            self.assertTrue(chart["rows"])
            for row in chart["rows"]:
                # name, photographs, bytes, and the search this bucket means
                self.assertEqual(len(row), 4)
                self.assertIsInstance(row[3], dict)

    def test_every_chart_hands_over_all_of_its_buckets_not_just_the_drawn_ones(self):
        """"Everything else" with no way to find out what is in it is the chart
        saying there is something there and refusing to name it."""
        p = L.plan({"folder": self.lib})
        for chart in p.charts["charts"]:
            self.assertIn("show", chart)
            self.assertNotIn("everything else", [r[0] for r in chart["rows"]])

    def test_a_named_camera_still_searches_by_the_code_in_the_file(self):
        """The chart says "Lumix GH4 (DMC-GH4)"; only the code in the brackets
        is something a file can answer."""
        self.assertEqual(ST.ask_for("camera", "Lumix GH4 (DMC-GH4)"),
                         {"camera": "DMC-GH4"})
        self.assertEqual(ST.ask_for("camera", "NIKON Z9"), {"camera": "NIKON Z9"})

    def test_a_bucket_carries_the_search_that_lists_it(self):
        p = L.plan({"folder": self.lib})
        by = {c["dim"]: c for c in p.charts["charts"]}
        year = by["year"]["rows"][0]
        self.assertEqual(year[3], {"since": "2022-01-01", "until": "2022-12-31"})
        stars = [r for r in by["stars"]["rows"] if r[0] == "no stars"][0]
        self.assertEqual(stars[3], {"stars_from": 0, "stars_to": 0})

    def test_a_bucket_no_search_can_say_carries_no_link(self):
        """A chart that sends you to the wrong photographs is worse than one
        that does not move."""
        self.assertEqual(ST.ask_for("camera", "everything else"), {})
        self.assertEqual(ST.ask_for("folder", ST.UNSAID), {})
        self.assertEqual(ST.ask_for("month", "April"), {})
        self.assertEqual(ST.ask_for("weekday", "Monday"), {})

    def test_not_said_lists_the_photographs_that_do_not_say(self):
        """The row a library most needs to find. Year, month, day and hour are
        all one capture time, so all four ask for the same thing."""
        for dim in ("year", "month", "weekday", "hour"):
            self.assertEqual(ST.ask_for(dim, ST.UNSAID), {"missing": "taken"})
        for dim in ("camera", "lens", "focal", "aperture", "iso", "shutter"):
            self.assertEqual(ST.ask_for(dim, ST.UNSAID), {"missing": dim})
        self.assertEqual(ST.ask_for("tag", "no tags"), {"missing": "tags"})
        self.assertEqual(ST.ask_for("colour", "no label"), {"missing": "colour"})

    def test_the_dashboard_hands_the_not_said_row_its_search(self):
        p = L.plan({"folder": self.lib})
        for chart in p.charts["charts"]:
            for row in chart["rows"]:
                if row[0] == ST.UNSAID and chart["dim"] != "folder":
                    self.assertIn("missing", row[3], chart["dim"])

    def test_the_search_a_band_means_is_the_band_itself(self):
        """Worked out where the bands are defined, so a chart and the search
        behind it can never disagree about what f/5.6 covers."""
        ask = ST.ask_for("aperture", "f/5.6")
        self.assertEqual(ask["f_from"], 4.5)
        self.assertLess(ask["f_to"], 6.4)
        self.assertGreater(ask["f_to"], 5.6)
        focal = ST.ask_for("focal", "24-35mm")
        self.assertEqual(focal["focal_from"], 24)
        self.assertLess(focal["focal_to"], 36)
        iso = ST.ask_for("iso", "800")
        # The edge sits BETWEEN two stops rather than on one. It used to be
        # written on the stop, and ISO 100 - the commonest value in a daylight
        # library - fell past its own band into the 200 one.
        self.assertEqual(iso["iso_to"], 1200)
        self.assertEqual(ST.buckets_of(
            type("H", (), {"iso": 100, "taken": "", "camera": "", "lens": "",
                           "fnumber": 0, "seconds": 0, "focal_length": 0,
                           "focal35": 0, "path": "x"})(), "iso"),
            ["100 and under"])
        fast = ST.ask_for("shutter", "1/250")
        self.assertLess(fast["faster_than"], 0.0051)
        self.assertGreater(fast["slower_than"], 0.002)

    def test_the_charts_can_be_turned_off(self):
        p = L.plan({"folder": self.lib, "charts": False})
        self.assertEqual(p.charts, {})
        self.assertTrue(p.tree, "the tree is still there without them")


if __name__ == "__main__":
    unittest.main()
