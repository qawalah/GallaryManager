"""Two records of where somebody was, combined, and a file to take elsewhere.

The point of this feature is that neither source knows all of it: the Timeline
export is blank where the phone was off, and the photographs are blank where
nobody took one. What has to hold is that combining them loses nothing, counts
nothing twice, and says where every position came from - because anything
downstream deciding whether two people's paths crossed has to be able to tell a
photograph's own position from a line in an export.
"""

import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import timeline as T                # noqa: E402
from core.timeline import Fix                 # noqa: E402


def fix(when, lat, lon, kind="path", accuracy=None, source=""):
    return Fix(local=when, offset_minutes=180, lat=lat, lon=lon, kind=kind,
               accuracy_m=accuracy, source=source)


class PuttingTheTwoTogether(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="tl-")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        self.day = dt.datetime(2024, 5, 1, 9, 0)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_everything_from_both_is_in_it_once(self):
        google = [fix(self.day + dt.timedelta(minutes=n * 20), 25.0 + n / 1000, 51.5)
                  for n in range(5)]
        photos = [fix(self.day + dt.timedelta(hours=4), 25.3, 51.7, "photo",
                      8.0, "a.jpg")]
        both = T.merge(google, photos)
        self.assertEqual(len(both), 6)
        self.assertEqual([f.local for f in both], sorted(f.local for f in both))

    def test_the_same_moment_in_both_is_in_it_once(self):
        """Two records of one afternoon agree about most of it, and an export
        with every position twice counts every crossing twice."""
        same = fix(self.day, 25.0, 51.5)
        again = fix(self.day, 25.0, 51.5, "photo", 5.0, "a.jpg")
        self.assertEqual(len(T.merge([same], [again])), 1)

    def test_and_a_near_repeat_keeps_the_one_that_says_more(self):
        loose = fix(self.day, 25.0, 51.5, "path")
        measured = fix(self.day + dt.timedelta(seconds=10), 25.0001, 51.5001,
                       "photo", 6.0, "a.jpg")
        both = T.merge([loose], [measured], apart_seconds=30)
        self.assertEqual(len(both), 1)
        self.assertEqual(both[0].kind, "photo")
        self.assertEqual(both[0].accuracy_m, 6.0)

    def test_a_long_gap_is_a_different_journey(self):
        rows = [fix(self.day, 25.0, 51.5),
                fix(self.day + dt.timedelta(minutes=10), 25.01, 51.5),
                fix(self.day + dt.timedelta(hours=6), 25.4, 51.9)]
        self.assertEqual([len(t) for t in T.tracks(rows, 30)], [2, 1])
        self.assertEqual(len(T.tracks(rows, 600)), 1)

    def test_the_geojson_carries_what_a_position_knows(self):
        rows = [fix(self.day, 25.0, 51.5, "photo", 7.5, "IMG_1.jpg"),
                fix(self.day + dt.timedelta(minutes=5), 25.01, 51.51)]
        got = T.as_geojson(rows)
        self.assertEqual(got["type"], "FeatureCollection")
        points = [f for f in got["features"] if f["geometry"]["type"] == "Point"]
        self.assertEqual(len(points), 2)
        one = points[0]["properties"]
        for key in ("time", "local", "offset_minutes", "offset_known", "kind",
                    "accuracy_m", "source"):
            self.assertIn(key, one)
        # the moment in UTC, not the clock on the wall: +03:00 at 09:00 local
        self.assertEqual(one["time"], "2024-05-01T06:00:00Z")
        self.assertEqual(one["source"], "IMG_1.jpg")
        # and GeoJSON is lon,lat in that order - the single most common way to
        # put a whole dataset in the sea off west Africa
        self.assertEqual(points[0]["geometry"]["coordinates"], [51.5, 25.0])

    def test_and_a_line_per_journey_because_paths_cross_between_points(self):
        rows = [fix(self.day + dt.timedelta(minutes=n * 5), 25.0 + n / 100, 51.5)
                for n in range(4)]
        got = T.as_geojson(rows)
        lines = [f for f in got["features"] if f["geometry"]["type"] == "LineString"]
        self.assertEqual(len(lines), 1)
        self.assertEqual(len(lines[0]["geometry"]["coordinates"]), 4)
        self.assertEqual(lines[0]["properties"]["fixes"], 4)

    def test_the_csv_is_the_same_facts_flat(self):
        rows = [fix(self.day, 25.0, 51.5, "photo", 7.5, "IMG_1.jpg")]
        out = list(T.as_csv_rows(rows))
        self.assertEqual(out[0], list(T.CSV_COLUMNS))
        self.assertEqual(len(out), 2)
        said = dict(zip(out[0], out[1]))
        self.assertEqual(said["utc"], "2024-05-01T06:00:00Z")
        self.assertEqual(said["offset_known"], 1)
        self.assertEqual(said["source"], "IMG_1.jpg")
        self.assertEqual(said["track"], 1)

    def test_a_store_keeps_the_accuracy_and_the_source_it_was_given(self):
        """They were added in 3.3 and the format did not change - which is the
        whole reason it is tab-separated text."""
        path = os.path.join(self.home, "store.tsv")
        T.write_store(path, [fix(self.day, 25.0, 51.5, "photo", 7.5, "IMG_1.jpg")])
        back = T.read_store(path)
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0].accuracy_m, 7.5)
        self.assertEqual(back[0].source, "IMG_1.jpg")
        self.assertEqual(back[0].kind, "photo")

    def test_an_older_reader_still_understands_it(self):
        path = os.path.join(self.home, "store.tsv")
        T.write_store(path, [fix(self.day, 25.0, 51.5, "photo", 7.5, "IMG_1.jpg")])
        with open(path, encoding="utf-8") as fh:
            body = [l for l in fh if l[0] != "#" and not l.startswith("local\t")]
        self.assertTrue(body[0].split("\t")[:5])
        self.assertEqual(body[0].split("\t")[4], "photo")


    def test_a_position_with_no_timezone_in_it_says_so(self):
        """A camera that recorded no satellite time gives no offset, and zero is
        an assumption. A UTC moment built on it can be twelve hours out - which
        is a meeting that never happened - so the export says which is which."""
        sure = fix(self.day, 25.0, 51.5, "path")
        guessed = Fix(local=self.day, offset_minutes=0, lat=26.0, lon=52.0,
                      kind="photo", source="IMG_9.jpg", offset_known=False)
        got = T.as_geojson([sure, guessed])
        says = [f["properties"]["offset_known"] for f in got["features"]
                if f["geometry"]["type"] == "Point"]
        self.assertIn(True, says)
        self.assertIn(False, says)

    def test_and_a_store_remembers_that_too(self):
        path = os.path.join(self.home, "store.tsv")
        T.write_store(path, [Fix(local=self.day, offset_minutes=0, lat=25.0,
                                 lon=51.5, kind="photo", offset_known=False)])
        self.assertFalse(T.read_store(path)[0].offset_known)


class TheFeature(unittest.TestCase):
    """Driven the way the app drives it: a plan, then an apply."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="tlf-")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        self.out = os.path.join(self.home, "out")
        os.makedirs(self.out)
        from core import settings as S
        self.lib = os.path.join(self.home, "Photos")
        os.makedirs(self.lib)
        S.save({"library": self.lib})
        # an imported Google timeline, as `import-timeline` would have left it
        from core.store import store_path
        day = dt.datetime(2024, 5, 1, 9, 0)
        T.write_store(store_path("timeline.tsv"),
                      [fix(day + dt.timedelta(minutes=n * 20), 25.0 + n / 1000, 51.5)
                       for n in range(6)], source="a Timeline export")

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        from core import catalogue as C
        C.forget_all()

    def task(self):
        from app import registry as R
        import app.tasks                                   # noqa: F401
        return R.get("timeline")

    def test_it_exports_both_formats_and_says_what_is_in_them(self):
        task = self.task()
        plan = task.make_plan({"folders": self.lib, "out": self.out,
                               "use_photos": False})
        self.assertFalse(plan.blocked, plan.blocked)
        self.assertEqual(len(plan.rows), 2)                 # geojson and csv
        said = dict(plan.stats)
        self.assertEqual(said["From the imported Timeline"], "6")
        self.assertEqual(said["Together, without repeats"], "6")
        # nothing is written by planning
        self.assertEqual(os.listdir(self.out), [])
        out = task.apply(plan)
        self.assertEqual(out.done, 2)
        made = sorted(os.listdir(self.out))
        self.assertEqual(made, ["location-timeline.csv",
                                "location-timeline.geojson"])
        with open(os.path.join(self.out, "location-timeline.geojson"),
                  encoding="utf-8") as fh:
            body = json.load(fh)
        self.assertEqual(body["type"], "FeatureCollection")
        self.assertEqual(len([f for f in body["features"]
                              if f["geometry"]["type"] == "Point"]), 6)

    def test_the_imported_timeline_is_never_altered(self):
        from core.store import store_path
        with open(store_path("timeline.tsv"), encoding="utf-8") as fh:
            before = fh.read()
        task = self.task()
        task.apply(task.make_plan({"folders": self.lib, "out": self.out}))
        with open(store_path("timeline.tsv"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)

    def test_and_nothing_is_written_into_a_photograph(self):
        """It reads photographs and writes files of its own. That is all."""
        task = self.task()
        self.assertTrue(task.describe()["undo"])
        self.assertIn("Nothing is written into a photo", task.undo)

    def test_asking_for_neither_source_says_so_rather_than_writing_nothing(self):
        task = self.task()
        plan = task.make_plan({"folders": self.lib, "out": self.out,
                               "use_photos": False, "use_timeline": False})
        self.assertIn("Nothing to combine", plan.blocked)

    def test_with_no_folder_to_export_into_it_says_what_it_will_not_do(self):
        task = self.task()
        plan = task.make_plan({"folders": self.lib, "out": "",
                               "use_photos": False})
        self.assertFalse(plan.blocked)
        self.assertTrue(any("no folder to export into" in n.lower()
                            for n in plan.notes), plan.notes)


class AndGeotagCanUseIt(unittest.TestCase):
    """The two stores stay side by side, and Geotag asks for both in the order
    you chose - which is the whole reason they are not merged into one."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="tlg-")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        self.lib = os.path.join(self.home, "Photos")
        os.makedirs(self.lib)
        from core import settings as S
        S.save({"library": self.lib})

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_the_photo_timeline_is_a_source_geotag_will_read(self):
        from core.store import store_path
        from app import registry as R
        import app.tasks                                   # noqa: F401
        day = dt.datetime(2024, 5, 1, 9, 0)
        T.write_store(store_path("timeline-photos.tsv"),
                      [fix(day + dt.timedelta(minutes=n * 10), 25.0 + n / 1000,
                           51.5, "photo", 8.0, f"IMG_{n}.jpg") for n in range(4)],
                      source="your photographs")
        plan = R.get("geotag").make_plan({"folder": self.lib, "order": "photos"})
        said = " ".join(plan.notes)
        self.assertIn("Your photos", said)
        self.assertIn("Location timeline", said)

    def test_and_neither_store_is_written_by_the_other(self):
        from core.store import store_path
        day = dt.datetime(2024, 5, 1, 9, 0)
        T.write_store(store_path("timeline.tsv"), [fix(day, 25.0, 51.5)],
                      source="a Timeline export")
        T.write_store(store_path("timeline-photos.tsv"),
                      [fix(day, 26.0, 52.5, "photo")], source="your photographs")
        self.assertEqual(T.read_store(store_path("timeline.tsv"))[0].lat, 25.0)
        self.assertEqual(T.read_store(store_path("timeline-photos.tsv"))[0].lat,
                         26.0)


if __name__ == "__main__":
    unittest.main()
