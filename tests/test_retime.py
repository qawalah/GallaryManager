"""Correcting a camera clock, and the thing it would quietly break.

The interesting tests here are not about arithmetic. They are about the fact that
a RAW is tied to its JPEG BY CAPTURE TIME, so moving the JPEGs of a shoot is
exactly the operation that can orphan every RAW in it - in a completely different
task, days later, with nothing to connect the two events.
"""

import datetime as dt
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R                        # noqa: E402
import app.tasks                                     # noqa: E402,F401
from app.tasks.retime import parse_when, say_offset  # noqa: E402
from core.exifwrite import read_sidecar, set_rating, write_datetime  # noqa: E402
from core.photo import read_capture                  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
NAMES = ["aeb1", "aeb2", "aeb3", "burst1", "burst2", "burst3"]


class ReadingWhatYouTyped(unittest.TestCase):
    def test_the_forms_a_person_actually_writes(self):
        want = dt.datetime(2024, 5, 1, 9, 0, 0)
        for text in ("2024-05-01 09:00:00", "2024-05-01T09:00:00",
                     "2024:05:01 09:00:00", "01/05/2024 09:00:00"):
            self.assertEqual(parse_when(text), want, text)

    def test_a_time_without_seconds(self):
        self.assertEqual(parse_when("2024-05-01 09:00"), dt.datetime(2024, 5, 1, 9, 0))

    def test_a_date_on_its_own_means_midnight(self):
        self.assertEqual(parse_when("2024-05-01"), dt.datetime(2024, 5, 1, 0, 0))

    def test_nonsense_is_refused_rather_than_guessed_at(self):
        for text in ("", "   ", "last tuesday", "2024-13-45 99:99:99"):
            self.assertIsNone(parse_when(text), text)


class SayingItInWords(unittest.TestCase):
    def test_a_plain_shift(self):
        self.assertEqual(say_offset(dt.timedelta(hours=3)), "forward by 3 hours")

    def test_backwards(self):
        self.assertEqual(say_offset(dt.timedelta(hours=-1)), "back by 1 hour")

    def test_the_parts_are_all_named(self):
        said = say_offset(dt.timedelta(days=2, hours=1, minutes=5, seconds=30))
        for bit in ("2 days", "1 hour", "5 minutes", "30 seconds"):
            self.assertIn(bit, said)

    def test_no_change_is_said_plainly(self):
        self.assertEqual(say_offset(dt.timedelta()), "no change at all")


class AShootOnTheWrongClock(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="retime-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        os.makedirs(os.path.join(self.raw, "2022", "Spain"))
        for n in NAMES:
            shutil.copy(os.path.join(FIX, f"{n}.jpg"), os.path.join(self.shoot, f"{n}.JPG"))
            shutil.copy(os.path.join(FIX, f"{n}.jpg"),
                        os.path.join(self.raw, "2022", "Spain", f"{n}.RW2"))

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_task(self, name, **raw):
        t = R.get(name)
        return t, t.make_plan(raw)

    def apply(self, name, **raw):
        t, p = self.run_task(name, **raw)
        self.assertFalse(p.blocked, p.blocked)
        return p, t.apply(p)

    def taken(self, name, tree=None):
        folder = tree or self.shoot
        ext = ".RW2" if tree else ".JPG"
        return read_capture(os.path.join(folder, name + ext)).taken

    def retime(self, **over):
        return self.apply("retime", folder=self.lib, raw=self.raw, **over)

    # ------------------------------------------------------------ the arithmetic

    def test_correcting_one_photo_moves_the_whole_folder_by_the_same_amount(self):
        was = {n: self.taken(n) for n in NAMES}
        # burst1 says 18:10:00; say it was really 21:10:00 - three hours forward
        self.retime(reference="burst1", correct_time="2022-07-14 21:10:00")
        for n in NAMES:
            self.assertEqual(self.taken(n), was[n] + dt.timedelta(hours=3), n)

    def test_the_gaps_between_frames_are_exactly_as_they_were(self):
        before = self.taken("aeb3") - self.taken("aeb1")
        self.retime(reference="aeb1", correct_time="2019-01-01 00:00:00")
        self.assertEqual(self.taken("aeb3") - self.taken("aeb1"), before)

    def test_a_fixed_amount_can_be_given_instead(self):
        was = self.taken("burst1")
        self.retime(mode="amount", hours=-2, minutes=-30)
        self.assertEqual(self.taken("burst1"), was - dt.timedelta(hours=2, minutes=30))

    def test_the_earliest_photo_is_the_reference_when_none_is_named(self):
        _, p = self.run_task("retime", folder=self.lib, raw=self.raw,
                             correct_time="2022-07-14 20:03:22")
        self.assertTrue(any("aeb1.JPG says" in n for n in p.notes), p.notes)

    # -------------------------------------------------------------- the pairing

    def test_the_raws_move_with_them_so_every_pair_still_holds(self):
        """The whole reason this task takes a RAW tree at all."""
        self.retime(reference="burst1", correct_time="2022-07-14 21:10:00")
        raws = os.path.join(self.raw, "2022", "Spain")
        for n in NAMES:
            # to the second, not to the millisecond: a JPEG can carry sub-second
            # precision and a sidecar records whole seconds. Pairing allows two
            # seconds of slack anyway, because a camera stamps the JPEG and the RAW
            # of one shot a moment apart.
            apart = abs((self.taken(n) - self.taken(n, raws)).total_seconds())
            self.assertLess(apart, 1,
                            f"{n}: the RAW is on a different clock from its JPEG")

    def test_the_raw_itself_is_never_opened_for_writing(self):
        raw = os.path.join(self.raw, "2022", "Spain", "burst1.RW2")
        with open(raw, "rb") as fh:
            before = fh.read()
        self.retime(reference="burst1", correct_time="2022-07-14 21:10:00")
        with open(raw, "rb") as fh:
            self.assertEqual(fh.read(), before)
        self.assertTrue(read_sidecar(raw).get("exif:DateTimeOriginal"))

    def test_a_rating_already_in_the_sidecar_is_not_disturbed(self):
        raw = os.path.join(self.raw, "2022", "Spain", "burst1.RW2")
        set_rating(raw, 4)
        self.retime(reference="burst1", correct_time="2022-07-14 21:10:00")
        side = read_sidecar(raw)
        self.assertEqual(side.get("xmp:Rating"), "4")
        self.assertTrue(side.get("exif:DateTimeOriginal"))

    def test_remirror_afterwards_finds_every_raw_and_orphans_none(self):
        """The failure this guards against: a clock fix silently turning into a
        mass file move the next time the RAW tree is tidied."""
        self.retime(reference="burst1", correct_time="2022-07-14 21:10:00")
        _, p = self.run_task("remirror", library=self.lib, raw=self.raw)
        self.assertIn(("No photo found for them", "0"), p.stats)
        self.assertEqual(p.rows, [])

    def test_even_when_only_the_jpegs_were_corrected(self):
        """Someone will run it without pointing at the RAW tree. The pairing has to
        survive that too - by name, reported as being by name alone."""
        self.apply("retime", folder=self.lib,
                   reference="burst1", correct_time="2022-07-14 21:10:00")
        _, p = self.run_task("remirror", library=self.lib, raw=self.raw)
        self.assertIn(("No photo found for them", "0"), p.stats)

    def test_and_it_says_so_loudly_when_no_raw_tree_was_given(self):
        _, p = self.run_task("retime", folder=self.lib,
                             reference="burst1", correct_time="2022-07-14 21:10:00")
        self.assertTrue(any("NO RAW TREE" in n for n in p.notes), p.notes)

    # ------------------------------------------------------------- refusing well

    def test_a_time_it_cannot_read_is_refused_with_what_the_photo_says(self):
        _, p = self.run_task("retime", folder=self.lib, raw=self.raw,
                             reference="burst1", correct_time="last tuesday")
        self.assertTrue(p.blocked)
        self.assertIn("2022-07-14 18:10:00", p.blocked)
        self.assertEqual(p.rows, [])

    def test_the_reference_can_be_a_whole_path(self):
        """What the file picker and the command line hand over. Only a bare
        name used to match, so a picked file was "not in that folder"."""
        was = self.taken("burst1")
        self.retime(reference=os.path.join(self.shoot, "burst1.JPG"),
                    correct_time="2022-07-14 21:10:00")
        self.assertEqual(self.taken("burst1"), was + dt.timedelta(hours=3))

    def test_a_whole_path_outside_the_folder_is_refused(self):
        elsewhere = os.path.join(self.dir, "elsewhere", "burst1.JPG")
        _, p = self.run_task("retime", folder=self.shoot, raw=self.raw,
                             reference=elsewhere,
                             correct_time="2022-07-14 21:10:00")
        self.assertTrue(p.blocked)
        self.assertIn("not one of the photos", p.blocked)

    def test_a_reference_that_is_not_there(self):
        _, p = self.run_task("retime", folder=self.lib, raw=self.raw,
                             reference="nosuch.jpg", correct_time="2022-07-14 21:10:00")
        self.assertTrue(p.blocked)
        self.assertIn("nosuch", p.blocked)

    def test_a_correction_that_changes_nothing_is_refused_rather_than_run(self):
        _, p = self.run_task("retime", folder=self.lib, raw=self.raw,
                             reference="burst1", correct_time="2022-07-14 18:10:00")
        self.assertTrue(p.blocked)

    def test_an_amount_of_zero_is_refused(self):
        _, p = self.run_task("retime", folder=self.lib, raw=self.raw, mode="amount")
        self.assertTrue(p.blocked)

    def test_planning_alone_changes_no_clock(self):
        was = self.taken("burst1")
        self.run_task("retime", folder=self.lib, raw=self.raw,
                      reference="burst1", correct_time="2022-07-14 21:10:00")
        self.assertEqual(self.taken("burst1"), was)

    def test_a_copy_can_be_kept_first(self):
        self.retime(reference="burst1", correct_time="2022-07-14 21:10:00",
                    keep_originals="on")
        spare = os.path.join(self.shoot, "_BeforeRetime", "burst1.JPG")
        self.assertTrue(os.path.isfile(spare))
        self.assertEqual(read_capture(spare).taken, dt.datetime(2022, 7, 14, 18, 10))


class WritingTheTimeIntoAJpeg(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="retime-write-")
        self.path = os.path.join(self.dir, "one.jpg")
        shutil.copy(os.path.join(FIX, "burst1.jpg"), self.path)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_every_datetime_field_moves_together(self):
        """A file that disagrees with itself is read differently by different
        programs, which is worse than one that is simply wrong."""
        written = write_datetime(self.path, dt.datetime(2023, 1, 2, 3, 4, 5))
        self.assertGreaterEqual(written, 2)

    def test_the_new_time_reads_back(self):
        write_datetime(self.path, dt.datetime(2023, 1, 2, 3, 4, 5))
        self.assertEqual(read_capture(self.path).taken, dt.datetime(2023, 1, 2, 3, 4, 5))

    def test_nothing_else_about_the_photo_changes(self):
        before = read_capture(self.path)
        write_datetime(self.path, dt.datetime(2023, 1, 2, 3, 4, 5))
        after = read_capture(self.path)
        for field in ("model", "fnumber", "iso", "focal_length", "ev", "exposure"):
            self.assertEqual(getattr(after, field), getattr(before, field), field)

    def test_the_picture_itself_is_untouched(self):
        from core import jpegseg
        with open(self.path, "rb") as fh:
            before = fh.read()
        write_datetime(self.path, dt.datetime(2023, 1, 2, 3, 4, 5))
        with open(self.path, "rb") as fh:
            ok, why = jpegseg.picture_unchanged(before, fh.read())
        self.assertTrue(ok, why)

    def test_a_photo_with_no_exif_is_left_alone_rather_than_invented(self):
        plain = os.path.join(self.dir, "plain.jpg")
        shutil.copy(os.path.join(FIX, "noexif.jpg"), plain)
        try:
            self.assertEqual(write_datetime(plain, dt.datetime(2023, 1, 2)), 0)
        except ValueError as exc:
            self.assertIn("EXIF", str(exc))


if __name__ == "__main__":
    unittest.main()
