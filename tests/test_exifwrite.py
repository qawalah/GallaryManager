"""Writing metadata into a photo without damaging it.

The riskiest code in the project, so the tests are the strictest. Every write is
checked three ways: the picture must decode identically, our own reader must find
what was written, and - because a writer and a reader by the same hand can share
the same wrong assumption - Pillow must independently agree.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import exifwrite as W          # noqa: E402
from core import exif as E               # noqa: E402
from core import jpegseg                 # noqa: E402
from core.photo import read_capture, read_gps  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
VERIFY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "tools", "verify_with_pillow.py")

try:
    import PIL  # noqa: F401
    HAVE_PILLOW = True
except ImportError:
    HAVE_PILLOW = False


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


class Written(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="exifwrite-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def copy(self, name, as_name=None):
        dst = os.path.join(self.dir, as_name or name)
        shutil.copy(os.path.join(FIX, name), dst)
        return dst

    def assert_picture_untouched(self, path, original_bytes):
        ok, why = jpegseg.picture_unchanged(original_bytes, read(path))
        self.assertTrue(ok, why)

    def pillow_says(self, path, compare_with=None):
        """What an independent library makes of the file."""
        cmd = [sys.executable, VERIFY, path]
        if compare_with:
            cmd += ["--compare", compare_with]
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(out.stdout)[path]


class WritingALocation(Written):
    def test_into_a_photo_that_had_none(self):
        p = self.copy("plain.jpg")
        before = read(p)
        W.write_gps(p, 41.403630, 2.174356, 42.5)
        g = read_gps(p)
        self.assertTrue(g.has_gps)
        self.assertAlmostEqual(g.lat, 41.403630, places=6)
        self.assertAlmostEqual(g.lon, 2.174356, places=6)
        self.assertEqual(g.altitude, 42.5)
        self.assert_picture_untouched(p, before)

    def test_into_a_photo_with_no_exif_at_all(self):
        p = self.copy("noexif.jpg")
        before = read(p)
        W.write_gps(p, 25.2854, 51.5310)
        self.assertTrue(read_gps(p).has_gps)
        self.assert_picture_untouched(p, before)

    def test_replacing_a_location_that_was_already_there(self):
        p = self.copy("phone_doha.jpg")
        W.write_gps(p, -33.8688, -70.6693)
        g = read_gps(p)
        self.assertAlmostEqual(g.lat, -33.8688, places=4)
        self.assertAlmostEqual(g.lon, -70.6693, places=4)

    def test_south_and_west_keep_their_signs(self):
        p = self.copy("plain.jpg")
        W.write_gps(p, -33.868800, -70.669300)
        g = read_gps(p)
        self.assertAlmostEqual(g.lat, -33.8688, places=5)
        self.assertAlmostEqual(g.lon, -70.6693, places=5)

    def test_below_sea_level(self):
        p = self.copy("plain.jpg")
        W.write_gps(p, 31.5590, 35.4732, -430.0)
        self.assertEqual(read_gps(p).altitude, -430.0)

    def test_the_file_grows_only_a_little(self):
        p = self.copy("plain.jpg")
        before = len(read(p))
        W.write_gps(p, 41.4, 2.17)
        self.assertLess(len(read(p)) - before, 400)

    def test_the_modified_date_is_not_disturbed(self):
        p = self.copy("plain.jpg")
        os.utime(p, (1_600_000_000, 1_600_000_000))
        W.write_gps(p, 41.4, 2.17)
        self.assertEqual(int(os.stat(p).st_mtime), 1_600_000_000)


class EverythingElseSurvives(Written):
    def test_the_camera_and_the_exposure_fields(self):
        p = self.copy("aeb1.jpg")
        W.write_gps(p, 41.4, 2.17)
        c = read_capture(p)
        self.assertEqual(c.model, "DMC-GH4")
        self.assertEqual(c.fnumber, 5.6)
        self.assertEqual(c.iso, 200)
        self.assertEqual(c.ev, -1.0)
        self.assertEqual(c.exposure_mode, 2)

    def test_the_capture_time_including_its_fraction(self):
        p = self.copy("aeb2.jpg")
        W.write_gps(p, 41.4, 2.17)
        self.assertEqual(read_capture(p).taken.microsecond, 450_000)

    def test_a_star_rating_written_earlier(self):
        p = self.copy("rated.jpg")
        self.assertEqual(W.read_rating(p), 4)
        W.write_gps(p, 41.4, 2.17)
        self.assertEqual(W.read_rating(p), 4)
        self.assertTrue(read_gps(p).has_gps)

    def test_and_the_rating_can_still_be_changed_afterwards(self):
        p = self.copy("rated.jpg")
        W.write_gps(p, 41.4, 2.17)
        W.write_rating(p, 2)
        self.assertEqual(W.read_rating(p), 2)
        self.assertTrue(read_gps(p).has_gps)


class WhatItRefusesToDo(Written):
    def test_a_file_that_is_not_a_jpeg(self):
        p = self.copy("notajpeg.jpg")
        before = read(p)
        with self.assertRaises(ValueError):
            W.write_gps(p, 41.4, 2.17)
        self.assertEqual(read(p), before)

    def test_null_island(self):
        p = self.copy("plain.jpg")
        with self.assertRaises(ValueError):
            W.write_gps(p, 0, 0)
        self.assertFalse(read_gps(p).has_gps)

    def test_somewhere_off_the_planet(self):
        p = self.copy("plain.jpg")
        for lat, lon in ((91, 0), (0, 181), (-91, 0)):
            with self.assertRaises(ValueError):
                W.write_gps(p, lat, lon)

    def test_a_missing_file(self):
        with self.assertRaises(OSError):
            W.write_gps(os.path.join(self.dir, "nope.jpg"), 41.4, 2.17)

    def test_a_rating_outside_nought_to_five(self):
        p = self.copy("plain.jpg")
        for bad in (-1, 6, 99):
            with self.assertRaises(ValueError):
                W.write_rating(p, bad)

    def test_no_temporary_file_is_left_behind_after_a_refusal(self):
        p = self.copy("plain.jpg")
        with self.assertRaises(ValueError):
            W.write_gps(p, 0, 0)
        self.assertEqual([f for f in os.listdir(self.dir) if f.endswith("tmp")], [])


class WritingRepeatedly(Written):
    def test_five_writes_do_not_run_away_with_the_file(self):
        p = self.copy("plain.jpg")
        before = len(read(p))
        for i in range(5):
            W.write_gps(p, 41.4 + i * 0.001, 2.17)
        self.assertLess(len(read(p)) - before, 1400)

    def test_and_the_last_position_is_the_one_that_stuck(self):
        p = self.copy("plain.jpg")
        for i in range(5):
            W.write_gps(p, 41.4 + i * 0.001, 2.17)
        self.assertAlmostEqual(read_gps(p).lat, 41.404, places=3)

    def test_the_picture_is_still_untouched_after_all_of_them(self):
        p = self.copy("plain.jpg")
        before = read(p)
        for i in range(5):
            W.write_gps(p, 41.4 + i * 0.001, 2.17)
        self.assert_picture_untouched(p, before)


class KeepingACopy(Written):
    def test_the_original_is_kept_byte_for_byte(self):
        p = self.copy("plain.jpg")
        before = read(p)
        keep = os.path.join(self.dir, "_NoLocation")
        W.write_gps(p, 41.4, 2.17, backup_folder=keep)
        kept = os.path.join(keep, "plain.jpg")
        self.assertTrue(os.path.exists(kept))
        self.assertEqual(read(kept), before)

    def test_and_the_copy_has_no_location_while_the_photo_does(self):
        p = self.copy("plain.jpg")
        keep = os.path.join(self.dir, "_NoLocation")
        W.write_gps(p, 41.4, 2.17, backup_folder=keep)
        self.assertFalse(read_gps(os.path.join(keep, "plain.jpg")).has_gps)
        self.assertTrue(read_gps(p).has_gps)


class RatingsOnTheirOwn(Written):
    def test_writing_one_where_none_existed(self):
        p = self.copy("plain.jpg")
        before = read(p)
        W.write_rating(p, 3)
        self.assertEqual(W.read_rating(p), 3)
        self.assert_picture_untouched(p, before)

    def test_overwriting_one_that_was_there(self):
        p = self.copy("rated.jpg")
        W.write_rating(p, 1)
        self.assertEqual(W.read_rating(p), 1)

    def test_zero_means_unrated_not_zero_stars(self):
        p = self.copy("rated.jpg")
        W.write_rating(p, 0)
        self.assertIsNone(W.read_rating(p))

    def test_a_photo_with_no_rating_reads_as_none(self):
        self.assertIsNone(W.read_rating(os.path.join(FIX, "plain.jpg")))


class TheRatingInsideThePacket(Written):
    """Lightroom rates in the photo's own XMP packet and never writes the
    Windows tag. deep_xmp.jpg has four stars there and none anywhere else."""

    def test_it_is_read(self):
        p = self.copy("deep_xmp.jpg")
        self.assertEqual(W.read_rating(p), 4)
        self.assertEqual(W.rating_of(p), 4)

    def test_a_write_keeps_the_packet_and_the_windows_tag_in_step(self):
        p = self.copy("deep_xmp.jpg")
        before = read(p)
        W.write_rating(p, 5)
        self.assertIn('xmp:Rating="5"', jpegseg.xmp_packet(p))
        self.assertIn('crs:CropTop="0.125"', jpegseg.xmp_packet(p))
        t = E.exif_block(p)
        head = t.directory(t.first_ifd(), {E.T_RATING})
        self.assertEqual(int(head[E.T_RATING]), 5)
        self.assertEqual(W.rating_of(p), 5)
        self.assert_picture_untouched(p, before)

    def test_unrating_clears_it_in_both(self):
        p = self.copy("deep_xmp.jpg")
        W.write_rating(p, 0)
        self.assertIsNone(W.read_rating(p))

    def test_a_photo_with_no_packet_gets_none_made(self):
        p = self.copy("rated.jpg")
        W.write_rating(p, 2)
        self.assertEqual(jpegseg.xmp_packet(p), "")


class Sidecars(Written):
    def test_it_never_opens_the_photo_for_writing(self):
        p = self.copy("plain.jpg")
        before = read(p)
        W.write_gps_sidecar(p, 41.403630, 2.174356)
        self.assertEqual(read(p), before)

    def test_the_coordinate_is_written_the_way_xmp_expects(self):
        p = self.copy("plain.jpg")
        with open(W.write_gps_sidecar(p, 41.403630, 2.174356), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn('exif:GPSLatitude="41,24.21780N"', text)
        self.assertIn('exif:GPSLongitude="2,10.46136E"', text)

    def test_south_and_west_get_the_right_letters(self):
        p = self.copy("plain.jpg")
        with open(W.write_gps_sidecar(p, -33.8688, -70.6693), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("S\"", text)
        self.assertIn("W\"", text)


class TheCoordinateArithmetic(unittest.TestCase):
    def test_degrees_minutes_and_seconds_add_back_up(self):
        parts = W.to_rationals(25.2854)
        total = parts[0][0] + parts[1][0] / 60 + (parts[2][0] / parts[2][1]) / 3600
        self.assertAlmostEqual(total, 25.2854, places=6)

    def test_a_negative_value_is_stored_as_its_size(self):
        # the direction is carried by the N/S/E/W reference, not by a minus sign
        self.assertEqual(W.to_rationals(-33.8688)[0][0], 33)


@unittest.skipUnless(HAVE_PILLOW, "Pillow is not installed")
class ADifferentLibraryMustAgree(Written):
    """Never trust only your own reader.

    The writer and the reader here were written by the same hand and could share
    the same wrong assumption. Pillow has no such loyalty: it decodes the picture
    and reads the coordinates on its own terms.
    """

    def test_it_reads_back_what_we_wrote(self):
        for name in ("plain.jpg", "noexif.jpg", "rated.jpg", "phone_doha.jpg"):
            with self.subTest(name):
                p = self.copy(name)
                W.write_gps(p, 41.403630, 2.174356)
                seen = self.pillow_says(p)
                self.assertTrue(seen["ok"], seen.get("error"))
                self.assertAlmostEqual(seen["lat"], 41.403630, places=5)
                self.assertAlmostEqual(seen["lon"], 2.174356, places=5)

    def test_the_picture_still_decodes_and_is_identical(self):
        p = self.copy("plain.jpg")
        W.write_gps(p, 41.4, 2.17)
        # compared against the untouched fixture, or the answer means nothing
        self.assertIs(self.pillow_says(p, os.path.join(FIX, "plain.jpg"))["pixels_match"],
                      True)

    def test_and_that_comparison_can_actually_fail(self):
        # a check that cannot fail is worse than no check, so prove this one can
        p = self.copy("plain.jpg")
        W.write_gps(p, 41.4, 2.17)
        other = self.pillow_says(p, os.path.join(FIX, "burst1.jpg"))
        self.assertIs(other["pixels_match"], False)

    def test_it_agrees_the_other_metadata_survived(self):
        p = self.copy("rated.jpg")
        W.write_gps(p, 41.4, 2.17)
        seen = self.pillow_says(p)
        self.assertEqual(seen["model"], "DMC-GH4")
        self.assertEqual(seen["rating"], 4)
        self.assertEqual(seen["taken"], "2022:07:14 18:03:22")

    def test_a_negative_coordinate_survives_the_round_trip(self):
        p = self.copy("plain.jpg")
        W.write_gps(p, -33.868800, -70.669300)
        seen = self.pillow_says(p)
        self.assertAlmostEqual(seen["lat"], -33.8688, places=4)
        self.assertAlmostEqual(seen["lon"], -70.6693, places=4)

    def test_it_agrees_a_rating_we_wrote_is_there(self):
        p = self.copy("plain.jpg")
        W.write_rating(p, 5)
        self.assertEqual(self.pillow_says(p)["rating"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
