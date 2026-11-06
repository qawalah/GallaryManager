"""Reading a Timeline export, and working out where a photo was taken."""

import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import geo, timeline            # noqa: E402
from core.timeline import Fix             # noqa: E402


def export_doc():
    """Mirrors Google's on-device export exactly.

    Degree-sign coordinates, ISO times carrying a UTC offset, and rawSignals
    spelling it `LatLng` while everything else uses `latLng`.
    """
    return {
        "semanticSegments": [
            {"startTime": "2022-07-14T10:00:00.000+02:00",
             "endTime": "2022-07-14T10:30:00.000+02:00",
             "timelinePath": [
                 {"point": "41.385064°, 2.173403°", "time": "2022-07-14T10:05:00.000+02:00"},
                 {"point": "41.390000°, 2.174000°", "time": "2022-07-14T10:20:00.000+02:00"}]},
            {"startTime": "2022-07-14T11:00:00.000+02:00",
             "endTime": "2022-07-14T13:00:00.000+02:00",
             "startTimeTimezoneUtcOffsetMinutes": 120,
             "visit": {"hierarchyLevel": 0, "probability": 0.9,
                       "topCandidate": {"placeId": "X", "semanticType": "UNKNOWN",
                                        "probability": 0.9,
                                        "placeLocation": {"latLng": "41.403630°, 2.174356°"}}}},
            {"startTime": "2022-07-14T14:00:00.000+02:00",
             "endTime": "2022-07-14T15:00:00.000+02:00",
             "activity": {"start": {"latLng": "41.403630°, 2.174356°"},
                          "end": {"latLng": "41.390205°, 2.154007°"},
                          "distanceMeters": 2200.0,
                          "topCandidate": {"type": "WALKING", "probability": 0.9}}},
            {"startTime": "2022-07-15T09:00:00.000-03:00",
             "endTime": "2022-07-15T09:10:00.000-03:00",
             "timelinePath": [{"point": "-33.868800°, -70.669300°",
                               "time": "2022-07-15T09:05:00.000-03:00"}]},
            {"startTime": "2022-07-16T09:00:00.000+02:00",
             "endTime": "2022-07-16T10:00:00.000+02:00",
             "timelineMemory": {"trip": {"distanceFromOriginKms": 12}}},
        ],
        "rawSignals": [
            {"position": {"LatLng": "41.385064°, 2.173403°", "accuracyMeters": 100,
                          "altitudeMeters": 12.0, "source": "WIFI",
                          "timestamp": "2022-07-14T10:07:00.000+02:00",
                          "speedMetersPerSecond": 0.0}},
            {"wifiScan": {"deliveryTime": "2022-07-14T10:08:00.000+02:00"}},
            {"activityRecord": {"probableActivities": [{"type": "WALKING"}],
                                "timestamp": "2022-07-14T10:09:00.000+02:00"}},
        ],
        "userLocationProfile": {"frequentPlaces": []},
    }


class ReadingTheExport(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="timeline-")
        self.path = os.path.join(self.dir, "Timeline.json")
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(export_doc(), fh, ensure_ascii=False)
        self.fixes = timeline.read_export(self.path)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def kinds(self):
        out = {}
        for f in self.fixes:
            out[f.kind] = out.get(f.kind, 0) + 1
        return out

    def test_every_position_is_found(self):
        self.assertEqual(len(self.fixes), 8)

    def test_the_track_points(self):
        self.assertEqual(self.kinds()["path"], 3)

    def test_a_stay_is_recorded_at_both_ends_of_its_span(self):
        # so a photo taken during it resolves to the place, not to whatever came next
        self.assertEqual(self.kinds()["visit"], 2)
        visits = sorted((f for f in self.fixes if f.kind == "visit"), key=lambda f: f.local)
        self.assertEqual(visits[0].local.strftime("%H:%M"), "11:00")
        self.assertEqual(visits[1].local.strftime("%H:%M"), "13:00")
        self.assertEqual(visits[0].lat, visits[1].lat)

    def test_a_journey_gives_its_two_ends(self):
        self.assertEqual(self.kinds()["activity"], 2)

    def test_raw_positions_are_found_despite_the_capital_L(self):
        # rawSignals uses LatLng; everything else uses latLng. Missing it loses
        # twelve thousand fixes in a real export.
        self.assertEqual(self.kinds()["signal:WIFI"], 1)

    def test_a_raw_position_is_counted_once_not_twice(self):
        seen = [(f.local, f.lat, f.lon, f.kind) for f in self.fixes]
        self.assertEqual(len(seen), len(set(seen)))

    def test_its_accuracy_comes_through(self):
        signal = next(f for f in self.fixes if f.kind.startswith("signal"))
        self.assertEqual(signal.accuracy_m, 100)

    def test_they_come_back_in_order(self):
        self.assertEqual(self.fixes, sorted(self.fixes, key=lambda f: f.local))

    def test_a_segment_with_no_location_is_simply_skipped(self):
        self.assertEqual([f for f in self.fixes if f.local.day == 16], [])

    def test_south_and_west_keep_their_signs(self):
        south = [f for f in self.fixes if f.lat < 0]
        self.assertEqual(len(south), 1)
        self.assertAlmostEqual(south[0].lat, -33.8688, places=4)
        self.assertAlmostEqual(south[0].lon, -70.6693, places=4)
        self.assertEqual(south[0].offset_minutes, -180)

    def test_the_offset_is_kept_because_it_is_the_useful_part(self):
        # it says which timezone he was standing in - what a camera never records
        first = self.fixes[0]
        self.assertEqual(first.offset_minutes, 120)
        self.assertEqual(first.utc.strftime("%H:%M"), "08:05")


class TheCoordinateFormat(unittest.TestCase):
    def test_degree_signs_and_a_comma(self):
        self.assertEqual(timeline.parse_point("41.385064°, 2.173403°"),
                         (41.385064, 2.173403))

    def test_negative_both_ways(self):
        self.assertEqual(timeline.parse_point("-33.8688°, -70.6693°"),
                         (-33.8688, -70.6693))

    def test_null_island_is_refused(self):
        self.assertIsNone(timeline.parse_point("0°, 0°"))

    def test_rubbish_is_refused(self):
        for bad in ("somewhere nice", "", None, 42, "41.0°"):
            self.assertIsNone(timeline.parse_point(bad), bad)


class TheTimeFormat(unittest.TestCase):
    def test_it_converts_and_keeps_the_offset(self):
        when, off = timeline.parse_time("2022-07-14T10:05:00.000+02:00")
        self.assertEqual(when, dt.datetime(2022, 7, 14, 10, 5))
        self.assertEqual(off, 120)

    def test_a_negative_offset(self):
        self.assertEqual(timeline.parse_time("2022-07-15T09:05:00.000-03:00")[1], -180)

    def test_rubbish_gives_nothing(self):
        for bad in ("yesterday", "", None, 7):
            self.assertIsNone(timeline.parse_time(bad), bad)


class TheStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="store-")
        self.export = os.path.join(self.dir, "Timeline.json")
        self.store = os.path.join(self.dir, "timeline.tsv")
        with open(self.export, "w", encoding="utf-8") as fh:
            json.dump(export_doc(), fh, ensure_ascii=False)
        self.info = timeline.import_export(self.export, self.store)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_importing_reports_what_it_took_in(self):
        self.assertEqual(self.info.count, 8)
        self.assertTrue(os.path.isfile(self.store))

    def test_the_store_knows_its_own_size_and_where_it_came_from(self):
        info = timeline.store_info(self.store)
        self.assertEqual(info.count, 8)
        self.assertTrue(info.source.endswith("Timeline.json"))
        self.assertTrue(info.imported)

    def test_everything_comes_back_out(self):
        self.assertEqual(len(timeline.read_store(self.store)), 8)

    def test_coordinates_and_offsets_survive_the_round_trip(self):
        first = timeline.read_store(self.store)[0]
        original = timeline.read_export(self.export)[0]
        self.assertAlmostEqual(first.lat, original.lat, places=6)
        self.assertEqual(first.offset_minutes, original.offset_minutes)
        self.assertEqual(first.kind, original.kind)

    def test_only_the_dates_you_ask_for_are_read(self):
        some = timeline.read_store(self.store,
                                   dt.datetime(2022, 7, 14, 10, 30),
                                   dt.datetime(2022, 7, 14, 13, 30))
        self.assertLess(len(some), 8)
        self.assertTrue(all(dt.datetime(2022, 7, 14, 10, 30) <= f.local
                            <= dt.datetime(2022, 7, 14, 13, 30) for f in some))

    def test_a_range_with_nothing_in_it_gives_nothing(self):
        self.assertEqual(timeline.read_store(self.store,
                                             dt.datetime(2019, 1, 1),
                                             dt.datetime(2019, 1, 2)), [])

    def test_a_settings_only_takeout_export_is_refused_with_an_explanation(self):
        empty = os.path.join(self.dir, "empty.json")
        with open(empty, "w", encoding="utf-8") as fh:
            json.dump({"semanticSegments": [], "rawSignals": []}, fh)
        with self.assertRaises(ValueError) as caught:
            timeline.import_export(empty, os.path.join(self.dir, "x.tsv"))
        self.assertIn("exported from the phone", str(caught.exception))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "x.tsv")))

    def test_a_file_that_is_not_ours_is_refused(self):
        other = os.path.join(self.dir, "notours.tsv")
        with open(other, "w", encoding="utf-8") as fh:
            fh.write("hello\n")
        with self.assertRaises(ValueError):
            timeline.read_store(other)
        self.assertFalse(timeline.store_info(other).ok)

    def test_a_missing_store_reads_as_empty_rather_than_raising(self):
        self.assertFalse(timeline.store_info(os.path.join(self.dir, "nope.tsv")).ok)


def index_of(*rows):
    return geo.Index([Fix(local=dt.datetime(2022, 7, 14, h, m), offset_minutes=120,
                          lat=lat, lon=lon, kind=kind)
                      for h, m, lat, lon, kind in rows])


class FindingTheFixesEitherSide(unittest.TestCase):
    def setUp(self):
        self.idx = index_of((10, 0, 41.385, 2.173, "path"),
                            (11, 0, 41.4036, 2.1744, "visit"),
                            (13, 0, 41.4036, 2.1744, "visit"),
                            (15, 0, 41.390, 2.154, "activity"))

    def test_one_before_and_one_after(self):
        before, after = self.idx.around(dt.datetime(2022, 7, 14, 12, 0))
        self.assertEqual(before.local.hour, 11)
        self.assertEqual(after.local.hour, 13)

    def test_before_everything_nothing_precedes(self):
        before, after = self.idx.around(dt.datetime(2022, 7, 14, 6, 0))
        self.assertIsNone(before)
        self.assertEqual(after.local.hour, 10)

    def test_after_everything_nothing_follows(self):
        before, after = self.idx.around(dt.datetime(2022, 7, 14, 23, 0))
        self.assertEqual(before.local.hour, 15)
        self.assertIsNone(after)

    def test_the_search_terminates_for_every_size_and_target(self):
        # a binary search that stops narrowing hangs the app rather than failing,
        # and only for particular combinations - so walk all of them
        base = dt.datetime(2022, 1, 1)
        checked = 0
        for n in range(1, 41):
            idx = geo.Index([Fix(local=base + dt.timedelta(minutes=i * 10),
                                 offset_minutes=0, lat=41 + i * 0.001, lon=2.0)
                             for i in range(n)])
            for m in range(-5, n * 10 + 6):
                when = base + dt.timedelta(minutes=m)
                before, after = idx.around(when)
                checked += 1
                self.assertFalse(before and before.local > when)
                self.assertFalse(after and after.local < when)
                self.assertTrue(before or after)
        self.assertGreater(checked, 8000)


class PlacingAPhoto(unittest.TestCase):
    def setUp(self):
        self.stay = index_of((11, 0, 41.403630, 2.174356, "visit"),
                             (13, 0, 41.403630, 2.174356, "visit"))
        self.walkabout = index_of((14, 0, 41.403630, 2.174356, "activity"),
                                  (15, 0, 41.390205, 2.154007, "activity"))

    def test_a_stay_resolves_to_the_place_for_its_whole_span(self):
        hit = geo.place(self.stay, dt.datetime(2022, 7, 14, 12, 0), 90)
        self.assertTrue(hit.ok)
        self.assertAlmostEqual(hit.lat, 41.403630, places=5)
        self.assertIn("same spot", hit.how)
        self.assertFalse(hit.approximate)

    def test_a_journey_interpolates_and_admits_it(self):
        hit = geo.place(self.walkabout, dt.datetime(2022, 7, 14, 14, 30), 90)
        self.assertTrue(hit.ok)
        self.assertAlmostEqual(hit.lat, 41.3969, places=3)
        self.assertIn("interpolated", hit.how)
        self.assertTrue(hit.approximate)
        self.assertGreater(hit.spread_m, 1000)

    def test_too_far_from_anything_known_is_refused_not_guessed(self):
        hit = geo.place(self.stay, dt.datetime(2022, 7, 14, 23, 59), 60)
        self.assertFalse(hit.ok)
        self.assertIn("nothing within", hit.why)

    def test_a_wider_limit_does_find_it_but_calls_it_rough(self):
        hit = geo.place(self.stay, dt.datetime(2022, 7, 14, 23, 59), 900)
        self.assertTrue(hit.ok)
        self.assertEqual(hit.how, "nearest single fix")
        self.assertTrue(hit.approximate)

    def test_interpolation_can_be_switched_off(self):
        hit = geo.place(self.walkabout, dt.datetime(2022, 7, 14, 14, 30), 90,
                        interpolate=False)
        self.assertEqual(hit.how, "nearest single fix")

    def test_an_empty_record_places_nothing(self):
        self.assertFalse(geo.place(geo.Index([]), dt.datetime(2022, 7, 14, 12, 0)).ok)

    def test_the_map_link_uses_dots_not_a_local_decimal_comma(self):
        hit = geo.place(self.stay, dt.datetime(2022, 7, 14, 12, 0), 90)
        self.assertRegex(hit.map_link, r"\?q=-?\d+\.\d+,-?\d+\.\d+$")


class Distance(unittest.TestCase):
    def test_the_same_spot_is_zero(self):
        self.assertEqual(round(geo.distance_m(41.3851, 2.1734, 41.3851, 2.1734)), 0)

    def test_about_two_kilometres(self):
        d = geo.distance_m(41.3851, 2.1734, 41.4036, 2.1744)
        self.assertAlmostEqual(d / 1000, 2.06, places=1)


class TheCameraClock(unittest.TestCase):
    def test_a_consistent_error_is_measured(self):
        idx = index_of(*[(10 + i, 0, 41.4, 2.17, "path") for i in range(6)])
        # every photo taken twelve minutes after the fix beside it
        takens = [dt.datetime(2022, 7, 14, 10 + i, 12) for i in range(6)]
        out = geo.suggest_clock_drift(idx, takens)
        self.assertTrue(out["ok"])
        self.assertLessEqual(abs(out["minutes"] - 12), 8)

    def test_too_little_evidence_and_it_declines(self):
        idx = index_of((10, 0, 41.4, 2.17, "path"))
        out = geo.suggest_clock_drift(idx, [dt.datetime(2022, 7, 14, 10, 12)])
        self.assertFalse(out["ok"])
        self.assertIn("not enough", out["why"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
