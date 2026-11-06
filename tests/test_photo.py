"""The cases that came from the Windows app, which are the real specification.

Each one is here because it was once wrong. The names say what the behaviour is,
so a failure reads as a sentence rather than an assertion.
"""

import datetime as dt
import os
import unittest

from core import exif, jpegseg
from core.photo import Location, kind, read_capture, read_gps, sane_coordinate

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def fx(name):
    return os.path.join(FIX, name)


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


class TellingFilesApart(unittest.TestCase):
    def test_jpg_and_jpeg_are_the_same_thing(self):
        self.assertEqual(kind("a.JPG"), "jpeg")
        self.assertEqual(kind("a.jpeg"), "jpeg")
        self.assertEqual(kind("a.jpe"), "jpeg")

    def test_raw_files_are_recognised(self):
        for ext in (".arw", ".RW2", ".dng", ".cr3"):
            self.assertEqual(kind("shot" + ext), "raw", ext)

    def test_a_sidecar_is_not_a_picture(self):
        self.assertEqual(kind("a.xmp"), "sidecar")


class ReadingTheHeaders(unittest.TestCase):
    def test_a_jpeg_is_recognised(self):
        self.assertTrue(jpegseg.is_jpeg(jpegseg.read_header(fx("plain.jpg"))))

    def test_something_that_is_not_a_jpeg_is_not(self):
        self.assertFalse(jpegseg.is_jpeg(jpegseg.read_header(fx("notajpeg.jpg"))))

    def test_a_missing_file_does_not_raise(self):
        self.assertEqual(jpegseg.read_header(fx("nothing-here.jpg")), b"")

    def test_the_picture_starts_after_the_headers(self):
        buf = _read(fx("plain.jpg"))
        self.assertGreater(jpegseg.scan_start(buf), 0)

    def test_a_file_compared_with_itself_is_unchanged(self):
        buf = _read(fx("plain.jpg"))
        ok, why = jpegseg.picture_unchanged(buf, buf)
        self.assertTrue(ok, why)

    def test_a_changed_picture_is_caught(self):
        buf = bytearray(_read(fx("plain.jpg")))
        buf[-20] ^= 0xFF                       # a single byte, deep in the picture
        ok, why = jpegseg.picture_unchanged(_read(fx("plain.jpg")), bytes(buf))
        self.assertFalse(ok)
        self.assertIn("changed", why)


class ReadingHowAFrameWasExposed(unittest.TestCase):
    def test_the_exposure_fields_are_one_pointer_deeper_than_the_rest(self):
        c = read_capture(fx("aeb1.jpg"))
        self.assertTrue(c.ok)
        self.assertEqual(c.model, "DMC-GH4")
        self.assertEqual(c.fnumber, 5.6)         # these live in the ExifIFD
        self.assertEqual(c.iso, 200)
        self.assertEqual(c.focal_length, 25)

    def test_exposure_bias_can_be_negative(self):
        self.assertEqual(read_capture(fx("aeb1.jpg")).ev, -1.0)
        self.assertEqual(read_capture(fx("aeb3.jpg")).ev, 1.0)

    def test_the_camera_says_when_it_is_auto_bracketing(self):
        self.assertEqual(read_capture(fx("aeb1.jpg")).exposure_mode, 2)
        self.assertEqual(read_capture(fx("burst1.jpg")).exposure_mode, 0)

    def test_sub_seconds_are_a_fraction_not_an_integer(self):
        # "10" means 100 ms, not 10 ms - it pads on the right
        self.assertEqual(read_capture(fx("aeb1.jpg")).taken.microsecond, 100_000)
        self.assertEqual(read_capture(fx("aeb2.jpg")).taken.microsecond, 450_000)

    def test_a_photo_with_no_exif_says_so_rather_than_guessing(self):
        self.assertFalse(read_capture(fx("noexif.jpg")).ok)

    def test_a_missing_file_does_not_raise(self):
        self.assertFalse(read_capture(fx("nope.jpg")).ok)


class ReadingWhereAPhotoWasTaken(unittest.TestCase):
    def test_a_phone_photo_carries_a_location(self):
        g = read_gps(fx("phone_doha.jpg"))
        self.assertTrue(g.has_gps)
        self.assertAlmostEqual(g.lat, 25.2854, places=4)
        self.assertAlmostEqual(g.lon, 51.5310, places=4)

    def test_minutes_and_seconds_are_added_in_not_dropped(self):
        # 25.2854 as d/m/s is 25 / 17 / 7.44. Taking only the degrees gives 25 -
        # about sixty miles out, and a number that looks entirely plausible.
        self.assertNotEqual(round(read_gps(fx("phone_doha.jpg")).lat, 4), 25.0)

    def test_a_whole_value_in_the_degrees_slot_works_too(self):
        self.assertAlmostEqual(read_gps(fx("phone_decimal.jpg")).lat, 25.2854, places=4)

    def test_south_and_west_are_negative(self):
        g = read_gps(fx("phone_south.jpg"))
        self.assertAlmostEqual(g.lat, -33.8688, places=4)
        self.assertAlmostEqual(g.lon, -70.6693, places=4)

    def test_altitude_below_sea_level(self):
        self.assertEqual(read_gps(fx("phone_belowsea.jpg")).altitude, -430.0)

    def test_the_satellite_time_is_utc_and_is_kept(self):
        g = read_gps(fx("phone_doha.jpg"))
        self.assertEqual(g.utc, dt.datetime(2022, 7, 14, 18, 3, 20, tzinfo=dt.timezone.utc))

    def test_the_camera_clock_is_read_separately_from_the_satellite_time(self):
        g = read_gps(fx("phone_doha.jpg"))
        self.assertEqual(g.taken, dt.datetime(2022, 7, 14, 21, 3, 20))
        # local minus utc is the timezone the phone was set to - three hours
        self.assertEqual(int((g.taken - g.utc.replace(tzinfo=None)).total_seconds() / 60), 180)

    def test_a_camera_that_records_its_timezone_is_believed(self):
        self.assertEqual(read_gps(fx("phone_belowsea.jpg")).offset_minutes, 180)

    def test_null_island_is_refused_not_believed(self):
        self.assertFalse(read_gps(fx("phone_nullisland.jpg")).has_gps)

    def test_a_photo_with_exif_but_no_location_still_gives_its_time(self):
        g = read_gps(fx("plain.jpg"))
        self.assertFalse(g.has_gps)
        self.assertEqual(g.taken, dt.datetime(2022, 7, 14, 18, 3, 22))

    def test_a_photo_with_no_exif_at_all(self):
        self.assertFalse(read_gps(fx("noexif.jpg")).has_gps)

    def test_a_missing_file_does_not_raise(self):
        self.assertFalse(read_gps(fx("nope.jpg")).has_gps)


class WhatCountsAsAPlaceOnEarth(unittest.TestCase):
    def test_a_real_place(self):
        self.assertTrue(sane_coordinate(25.2854, 51.531))

    def test_null_island_is_not(self):
        self.assertFalse(sane_coordinate(0, 0))

    def test_past_the_pole_is_not(self):
        self.assertFalse(sane_coordinate(91, 0))

    def test_past_the_date_line_is_not(self):
        self.assertFalse(sane_coordinate(0, 181))

    def test_nothing_at_all_is_not(self):
        self.assertFalse(sane_coordinate(None, None))


class TheTimezoneTag(unittest.TestCase):
    def test_plus_three(self):
        self.assertEqual(exif.parse_offset("+03:00"), 180)

    def test_minus_eight(self):
        self.assertEqual(exif.parse_offset("-08:00"), -480)

    def test_half_hours(self):
        self.assertEqual(exif.parse_offset("+05:30"), 330)

    def test_without_a_colon(self):
        self.assertEqual(exif.parse_offset("+0330"), 210)

    def test_nonsense_gives_nothing(self):
        self.assertIsNone(exif.parse_offset("nope"))
        self.assertIsNone(exif.parse_offset(""))
        self.assertIsNone(exif.parse_offset(None))


class ExifsOwnDateFormat(unittest.TestCase):
    def test_it_is_not_a_format_any_date_parser_accepts(self):
        self.assertEqual(exif.parse_datetime("2022:07:14 18:03:22"),
                         dt.datetime(2022, 7, 14, 18, 3, 22))

    def test_rubbish_gives_nothing(self):
        self.assertIsNone(exif.parse_datetime("yesterday"))
        self.assertIsNone(exif.parse_datetime(""))
        self.assertIsNone(exif.parse_datetime(None))

    def test_an_impossible_date_gives_nothing_rather_than_raising(self):
        self.assertIsNone(exif.parse_datetime("2022:13:45 99:99:99"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
