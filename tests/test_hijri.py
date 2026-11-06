"""Hijri months for folder names: the announced starts, then arithmetic."""

import datetime as dt
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import hijri as H                      # noqa: E402
from core import naming as N                     # noqa: E402


class Converting(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="hijri-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = self.dir

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_every_start_it_ships_with_is_answered_exactly(self):
        for (year, month), when in H.KNOWN.items():
            got = H.from_gregorian(dt.date.fromisoformat(when))
            self.assertEqual(got, (year, month, 1), when)

    def test_the_middle_of_a_month_counts_on_from_its_start(self):
        # Abu's example: April 2022 is Ramadan
        self.assertEqual(H.from_gregorian(dt.date(2022, 4, 15)), (1443, 9, 14))
        self.assertEqual(H.name(9), "Ramadan")

    def test_a_date_before_anything_announced_still_answers(self):
        year, month, day = H.from_gregorian(dt.date(1990, 1, 1))
        self.assertTrue(1400 < year < 1420, year)
        self.assertTrue(1 <= month <= 12 and 1 <= day <= 30)

    def test_the_day_never_walks_backwards(self):
        """A calendar that goes 29, 30, 1, 30 would file a shoot in two months."""
        day = dt.date(2021, 1, 1)
        last = H.from_gregorian(day)
        for _ in range(2000):
            day += dt.timedelta(days=1)
            now = H.from_gregorian(day)
            if now[:2] == last[:2]:
                self.assertEqual(now[2], last[2] + 1, day)
            else:
                self.assertEqual(now[2], 1, day)
                # 28 as well as 29 or 30: a month whose end is pulled by an
                # announced start is a day or two short, which is the arithmetic
                # calendar being corrected rather than a fault.
                self.assertIn(last[2], (28, 29, 30), day)
            last = now

    def test_your_own_starts_win(self):
        with open(os.path.join(self.dir, H.FILE), "w") as fh:
            fh.write("# mine\n1443-09\t2022-04-03\n")
        self.assertEqual(H.from_gregorian(dt.date(2022, 4, 3)), (1443, 9, 1))
        self.assertEqual(H.from_gregorian(dt.date(2022, 4, 2)), (1443, 8, 29))

    def test_a_shift_moves_the_whole_calendar(self):
        self.assertEqual(H.from_gregorian(dt.date(2022, 4, 2), 1), (1443, 9, 2))
        self.assertEqual(H.from_gregorian(dt.date(2022, 4, 2), -1), (1443, 8, 28))
        self.assertEqual(H.from_gregorian(dt.date(2022, 4, 3), -1), (1443, 9, 1))

    def test_nonsense_in_the_file_is_ignored_not_fatal(self):
        with open(os.path.join(self.dir, H.FILE), "w") as fh:
            fh.write("rubbish\n1443-09\tnot-a-date\n")
        self.assertEqual(H.from_gregorian(dt.date(2022, 4, 2)), (1443, 9, 1))


class InAPattern(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="hijri-pat-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = self.dir

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def values(self, when=dt.datetime(2022, 4, 15, 10, 0), shift=0):
        return N.facts(when, None, "", "", None, 0, shift)

    def test_the_hijri_variables_render(self):
        v = self.values()
        self.assertEqual(N.render("{hyear}/{hmonth} {hmonthname}", v), "1443/09 Ramadan")
        self.assertEqual(N.render("{year} {monthname} = {hmonthname}", v),
                         "2022 April = Ramadan")
        self.assertEqual(N.render("{hdate}", v), "1443-09-14")

    def test_they_count_as_date_variables(self):
        self.assertTrue(N.needs_date("{hmonthname}"))
        self.assertTrue(N.needs_hijri("{hmon}"))
        self.assertFalse(N.needs_hijri("{monthname}"))
        # a photo with no date is left where it is, not filed under a guess
        self.assertEqual(N.render("{hyear}/{hmonthname}", N.facts(None)), "")

    def test_there_is_a_ready_made_shape_for_it(self):
        keys = [k for k, _pattern, _group in N.PRESETS]
        self.assertIn("hijri_year_month", keys)
        self.assertEqual(N.problem(N.LEGACY["hijri_year_month"]), "")

    def test_the_sort_files_april_2022_under_ramadan(self):
        from app.tasks.bydate import folder_for
        got = folder_for(dt.datetime(2022, 4, 15, 9, 0), "custom",
                         pattern="{hyear}/{hmonthname}")
        self.assertEqual(got.replace(os.sep, "/"), "1443/Ramadan")

    def test_and_the_shift_reaches_it_from_the_task(self):
        from app.tasks.bydate import folder_for
        edge = dt.datetime(2022, 4, 2, 9, 0)
        self.assertEqual(folder_for(edge, "custom", pattern="{hmonthname}"), "Ramadan")
        self.assertEqual(folder_for(edge, "custom", pattern="{hmonthname}",
                                    hijri_shift=-1), "Shaban")


if __name__ == "__main__":
    unittest.main()
