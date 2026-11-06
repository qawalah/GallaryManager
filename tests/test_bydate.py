"""Filing a folder into year and month folders, whatever shape it is in now.

The feature is easy; the ways it can quietly ruin a library are not.

- **Filing by the file's timestamp instead of the photograph's.** A file's mtime
  says when it was last copied, so a library restored from a backup would go
  under one month - all of it, silently, and it looks like it worked.
- **Moving a JPEG and leaving its RAW.** Pairing survives it, because pairing is
  by identity - but the positions no longer mirror, and that surfaces days later
  in a task with nothing to do with dates.
- **Filing a photo with no readable date somewhere plausible.** A photograph in
  a plausible folder is a photograph you will not find again.
"""

import datetime as dt
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from app.tasks import bydate as B          # noqa: E402
from app.tasks.bydate import folder_for, week_start   # noqa: E402
from core import settings as S             # noqa: E402
from core import walk                      # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Messy(unittest.TestCase):
    """A folder in the state a card reader leaves one: junk names, nesting."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="bydate-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.prev = os.path.join(self.dir, "Photos Previews")
        self.card = os.path.join(self.lib, "100MSDCF")
        self.deep = os.path.join(self.lib, "edited", "keep")
        os.makedirs(self.card)
        os.makedirs(self.deep)
        os.makedirs(os.path.join(self.raw, "100MSDCF"))
        os.makedirs(os.path.join(self.prev, "100MSDCF"))
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(self.card, "plain.JPG"))
        shutil.copy(os.path.join(FIX, "rated.jpg"),
                    os.path.join(self.deep, "rated.JPG"))
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(self.raw, "100MSDCF", "plain.RW2"))
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(self.prev, "100MSDCF", "plain.JPG"))
        S.save({"library": self.lib, "raw": self.raw, "previews": self.prev})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def sort(self, **over):
        t = R.get("bydate")
        p = t.make_plan({"folder": self.lib, **over})
        self.assertFalse(p.blocked, p.blocked)
        return t, p

    def under(self, root):
        return sorted(os.path.relpath(f, root) for f in walk.walk(root).files)


class FinishedExportsTravelWithTheirOriginal(Messy):
    """Restructure a library and the finished exports were left behind.

    They are the one thing here that cannot be found again by looking. An export
    shares its original's name, capture time and camera - which is exactly why
    it lives in a subfolder every scan skips - and the price of that is nothing
    can re-match it afterwards. Re-sort the library and they sit in the shape it
    used to have, beside a folder the photographs have left.
    """

    def everything(self, root):
        """Every file, INCLUDING the folders the app's own walk skips - which
        is the whole point here: `walk.walk` cannot see a Developed folder, so
        checking with it would pass whether or not anything moved."""
        return sorted(os.path.relpath(os.path.join(here, f), root)
                      for here, _d, fs in os.walk(root) for f in fs)

    def developed(self, folder, stem, name=None):
        where = os.path.join(folder, "Developed")
        os.makedirs(where, exist_ok=True)
        out = os.path.join(where, (name or stem) + ".jpg")
        shutil.copy(os.path.join(FIX, "plain.jpg"), out)
        return out

    def test_it_moves_with_the_photograph_it_came_from(self):
        self.developed(self.card, "plain")
        t, p = self.sort(shape="year_month", mirror=False, raw="", previews="")
        t.apply(p)
        landed = self.everything(self.lib)
        self.assertIn(os.path.join("2022", "07", "Developed", "plain.jpg"), landed)
        self.assertIn(os.path.join("2022", "07", "plain.JPG"), landed)

    def test_into_a_subfolder_of_the_new_place_not_beside_the_photographs(self):
        """An export in the shoot folder itself is a second copy of every
        photograph to everything else in this app - counted twice, paired
        against the same RAW, reported as its own duplicate."""
        self.developed(self.card, "plain")
        _t, p = self.sort(shape="year_month", mirror=False, raw="", previews="")
        row = [r for r in p.rows if r.what == "developed"][0]
        self.assertEqual(os.path.basename(os.path.dirname(row.target)), "Developed")

    def test_a_second_export_of_the_same_photograph_comes_too(self):
        """`plain_1.jpg` is this app's own way of not overwriting a finished
        version when you export one again."""
        self.developed(self.card, "plain")
        self.developed(self.card, "plain", name="plain_1")
        _t, p = self.sort(shape="year_month", mirror=False, raw="", previews="")
        names = sorted(r.name for r in p.rows if r.what == "developed")
        self.assertEqual(names, ["plain.jpg", "plain_1.jpg"])

    def test_a_folder_that_splits_takes_its_exports_apart_with_it(self):
        """The case worth having: one shoot sorted into two months, each export
        following ITS photograph rather than all landing together."""
        import datetime as dt
        from core.exifwrite import set_datetime
        later = os.path.join(self.card, "doha.JPG")
        shutil.copy(os.path.join(FIX, "phone_doha.jpg"), later)
        set_datetime(later, dt.datetime(2022, 9, 2, 10, 0, 0))
        self.developed(self.card, "plain")
        self.developed(self.card, "doha")
        t, p = self.sort(shape="year_month", mirror=False, raw="", previews="")
        t.apply(p)
        landed = self.everything(self.lib)
        homes = {os.path.dirname(f) for f in landed if "Developed" in f}
        self.assertEqual(len(homes), 2,
                         f"both exports landed in one place: {sorted(landed)}")
        for f in landed:
            if "Developed" not in f:
                continue
            stem = os.path.splitext(os.path.basename(f))[0]
            self.assertIn(os.path.join(os.path.dirname(os.path.dirname(f)),
                                       stem + ".JPG"), landed)

    def test_the_photograph_and_its_negative_do_not_both_claim_it(self):
        """In a library that has not been separated yet - which is the state
        this whole tab exists for - the RAW sits in the same folder as its JPEG,
        so both of them find the same export beside them. The first to move
        wins; the second would plan a move of a file that is no longer there."""
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(self.card, "plain.RW2"))
        self.developed(self.card, "plain")
        t, p = self.sort(shape="year_month", mirror=False, raw="", previews="")
        sources = [r.source for r in p.rows if r.what == "developed"]
        self.assertEqual(len(sources), len(set(sources)))
        self.assertEqual(t.apply(p).failed, 0)

    def test_one_whose_original_has_gone_is_named_rather_than_forgotten(self):
        """It cannot travel with anything and no scan in this app can see it,
        so unsaid it is simply lost."""
        self.developed(self.card, "was-culled")
        _t, p = self.sort(shape="year_month", mirror=False, raw="", previews="")
        self.assertEqual([r for r in p.rows if r.what == "developed"], [])
        self.assertTrue(any("original is not in that folder" in why
                            for _n, why in p.skipped))

    def test_whatever_the_folder_is_called(self):
        S.save({"filed_into": "Curated"})
        where = os.path.join(self.card, "Curated")
        os.makedirs(where)
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(where, "plain.jpg"))
        _t, p = self.sort(shape="year_month", mirror=False, raw="", previews="")
        row = [r for r in p.rows if r.what == "developed"][0]
        self.assertEqual(os.path.basename(os.path.dirname(row.target)), "Curated")

    def test_and_when_exports_are_filed_beside_the_originals_none_of_this_applies(self):
        """They are ordinary photographs then, sorted like any other."""
        S.save({"filed_into": ""})
        self.developed(self.card, "plain")
        _t, p = self.sort(shape="year_month", mirror=False, raw="", previews="")
        self.assertEqual([r for r in p.rows if r.what == "developed"], [])


class TheShapeOfTheFolders(unittest.TestCase):
    when = dt.datetime(2022, 7, 14, 18, 3, 22)

    def test_each_one(self):
        self.assertEqual(folder_for(self.when, "year_month"),
                         os.path.join("2022", "07"))
        self.assertEqual(folder_for(self.when, "year"), "2022")
        self.assertEqual(folder_for(self.when, "flat_month"), "2022-07")
        self.assertEqual(folder_for(self.when, "year_dash_month"),
                         os.path.join("2022", "2022-07"))
        self.assertEqual(folder_for(self.when, "year_month_name"),
                         os.path.join("2022", "07 July"))

    def test_the_month_is_padded_so_it_sorts(self):
        self.assertEqual(folder_for(dt.datetime(2022, 3, 1), "year_month"),
                         os.path.join("2022", "03"))

    def test_by_day_for_the_folders_that_need_it(self):
        """A fortnight abroad is thousands of frames in one month folder."""
        self.assertEqual(folder_for(self.when, "year_month_day"),
                         os.path.join("2022", "07", "14"))
        self.assertEqual(folder_for(self.when, "year_month_dashday"),
                         os.path.join("2022", "07", "2022-07-14"))
        self.assertEqual(folder_for(self.when, "flat_day"), "2022-07-14")

    def test_and_the_day_is_padded_too(self):
        self.assertEqual(folder_for(dt.datetime(2022, 3, 5), "flat_day"),
                         "2022-03-05")


class ByWeek(unittest.TestCase):
    thursday = dt.datetime(2022, 7, 14, 18, 3, 22)

    def test_the_folder_is_named_by_the_date_the_week_began(self):
        self.assertEqual(folder_for(self.thursday, "year_week"),
                         os.path.join("2022", "week of 2022-07-11"))

    def test_which_day_a_week_starts_on_is_yours_to_say(self):
        """Monday is not universal, and the answer is written into the folder
        name rather than assumed."""
        self.assertEqual(week_start(self.thursday, "monday").isoformat(),
                         "2022-07-11")
        self.assertEqual(week_start(self.thursday, "sunday").isoformat(),
                         "2022-07-10")
        self.assertEqual(week_start(self.thursday, "saturday").isoformat(),
                         "2022-07-09")

    def test_a_photo_on_the_first_day_of_a_week_stays_in_that_week(self):
        monday = dt.datetime(2022, 7, 11, 6, 0)
        self.assertEqual(week_start(monday, "monday").isoformat(), "2022-07-11")

    def test_a_week_that_straddles_two_months_is_still_one_folder(self):
        """A trip from the 29th to the 4th belongs in one folder, not two -
        which is why weeks sit under the year and not under a month."""
        june = folder_for(dt.datetime(2022, 6, 30, 9, 0), "year_week")
        july = folder_for(dt.datetime(2022, 7, 2, 9, 0), "year_week")
        self.assertEqual(june, july)
        self.assertEqual(june, os.path.join("2022", "week of 2022-06-27"))

    def test_it_is_not_an_iso_week_number_and_that_is_deliberate(self):
        """1 January 2022 falls in ISO week 52 OF 2021, so "2022/W52" for a
        January photo is correct, useless, and looks like a bug. A date needs no
        explaining."""
        new_year = dt.datetime(2022, 1, 1, 12, 0)
        self.assertEqual(new_year.isocalendar()[1], 52)          # ISO says 52
        self.assertEqual(folder_for(new_year, "year_week"),
                         os.path.join("2021", "week of 2021-12-27"))

    def test_an_unknown_week_start_falls_back_rather_than_failing(self):
        self.assertEqual(week_start(self.thursday, "nonsense").isoformat(),
                         "2022-07-11")


class WhateverShapeItWasIn(Messy):
    def test_folders_you_already_had_are_walked_through_not_kept(self):
        """'100MSDCF' is a fact about the card reader, not about the pictures."""
        t, p = self.sort()
        t.apply(p)
        self.assertEqual(self.under(self.lib),
                         [os.path.join("2022", "07", "plain.JPG"),
                          os.path.join("2022", "07", "rated.JPG")])

    def test_and_the_folders_that_emptied_are_tidied_away(self):
        t, p = self.sort()
        t.apply(p)
        self.assertFalse(os.path.isdir(self.card))
        self.assertFalse(os.path.isdir(os.path.join(self.lib, "edited")))

    def test_running_it_again_does_nothing(self):
        t, p = self.sort()
        t.apply(p)
        _t, again = self.sort()
        self.assertEqual(again.rows, [])
        self.assertEqual(dict(again.stats)["Already in the right folder"], "2")


class TheDateComesFromThePhotograph(Messy):
    def test_not_from_the_file(self):
        """A library restored from a backup would otherwise go under one month -
        all of it, silently, and it would look like it worked."""
        old = os.path.join(self.card, "plain.JPG")
        os.utime(old, (0, 0))                     # 1970, if anyone were asking
        _t, p = self.sort()
        target = next(r.target for r in p.rows if r.name == "plain.JPG")
        self.assertIn(os.path.join("2022", "07"), target)

    def test_a_photo_with_no_capture_time_is_left_exactly_where_it_is(self):
        shutil.copy(os.path.join(FIX, "noexif.jpg"),
                    os.path.join(self.card, "noexif.JPG"))
        t, p = self.sort()
        self.assertFalse(any(r.name == "noexif.JPG" for r in p.rows))
        self.assertTrue(any("no capture time" in why for _n, why in p.skipped))
        t.apply(p)
        self.assertTrue(os.path.isfile(os.path.join(self.card, "noexif.JPG")))

    def test_and_neither_is_anything_that_is_not_a_photograph(self):
        with open(os.path.join(self.card, "notes.txt"), "w") as fh:
            fh.write("x")
        t, p = self.sort()
        t.apply(p)
        self.assertTrue(os.path.isfile(os.path.join(self.card, "notes.txt")))


class TheWholeShotMovesTogether(Messy):
    def test_the_negative_follows_its_photo(self):
        """Found by identity wherever it sits, and put in the matching new
        place. Moving the JPEG alone breaks the mirror, and that surfaces days
        later in a task with nothing to do with dates."""
        t, p = self.sort()
        t.apply(p)
        self.assertEqual(self.under(self.raw),
                         [os.path.join("2022", "07", "plain.RW2")])

    def test_so_does_the_preview(self):
        t, p = self.sort()
        t.apply(p)
        self.assertEqual(self.under(self.prev),
                         [os.path.join("2022", "07", "plain.JPG")])

    def test_a_sidecar_travels_with_its_file(self):
        side = os.path.join(self.raw, "100MSDCF", "plain.xmp")
        with open(side, "w", encoding="utf-8") as fh:
            fh.write("<x/>")
        t, p = self.sort()
        t.apply(p)
        self.assertFalse(os.path.exists(side))
        self.assertTrue(os.path.isfile(
            os.path.join(self.raw, "2022", "07", "plain.xmp")))

    def test_without_a_raw_tree_it_says_what_will_be_left_behind(self):
        _t, p = self.sort(raw="", mirror=False)
        self.assertTrue(any("Re-mirror" in n for n in p.notes))


class SortingOneFolderMoreFinelyThanAnother(Messy):
    """The point of offering a range: a quiet year is fine by month, a fortnight
    abroad is thousands of frames in one folder. The task only ever reshapes
    what you point it at, so one travel folder can be sorted by day while the
    rest of the library stays by month."""

    def test_by_day_puts_each_shoot_in_its_own_folder(self):
        t, p = self.sort(shape="year_month_day")
        t.apply(p)
        self.assertEqual(self.under(self.lib),
                         [os.path.join("2022", "07", "14", "plain.JPG"),
                          os.path.join("2022", "07", "14", "rated.JPG")])

    def test_by_week_too(self):
        t, p = self.sort(shape="year_week")
        t.apply(p)
        self.assertTrue(all(f.startswith(os.path.join("2022", "week of 2022-07-11"))
                            for f in self.under(self.lib)), self.under(self.lib))

    def test_the_week_start_reaches_the_folder_name(self):
        _t, p = self.sort(shape="year_week", week_starts="saturday")
        target = next(r.target for r in p.rows if r.name == "plain.JPG")
        self.assertIn("week of 2022-07-09", target)

    def test_and_the_negatives_follow_into_the_finer_folders(self):
        t, p = self.sort(shape="year_month_day")
        t.apply(p)
        self.assertEqual(self.under(self.raw),
                         [os.path.join("2022", "07", "14", "plain.RW2")])

    def test_re_sorting_a_folder_more_finely_works_from_wherever_it_is(self):
        """Sorted by month last month, by day today - the second run reads the
        photographs again, not the shape it made the first time."""
        t, p = self.sort(shape="year_month")
        t.apply(p)
        t2, p2 = self.sort(shape="year_month_day")
        t2.apply(p2)
        self.assertEqual(self.under(self.lib),
                         [os.path.join("2022", "07", "14", "plain.JPG"),
                          os.path.join("2022", "07", "14", "rated.JPG")])


class ItOnlyReshapesWhatYouPointItAt(Messy):
    def test_a_tree_inside_the_folder_being_sorted_is_refused(self):
        inside = os.path.join(self.lib, "Raw")
        os.makedirs(inside)
        t = R.get("bydate")
        p = t.make_plan({"folder": self.lib, "raw": inside, "mirror": False})
        self.assertTrue(p.blocked)
        self.assertIn("nothing would mirror anything", p.blocked)

    def test_previewing_moves_nothing(self):
        before = sorted(walk.walk(self.lib).files)
        self.sort()
        self.assertEqual(sorted(walk.walk(self.lib).files), before)



class ANegativeSittingInTheLibrary(unittest.TestCase):
    """The bug: a RAW beside its JPEG stayed behind when the JPEG moved.

    A .RW2 is not a JPEG, so this app cannot read EXIF out of it, so it had no
    capture time, so it was skipped as "no date" - while the JPEG of the same
    name, in the same folder, was filed. The shoot came apart in the one feature
    whose job is to keep it together. RAWs in the RAW TREE were always carried;
    these were not, because nothing was looking for them.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="bydate-raw-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        os.makedirs(self.lib)
        shutil.copy(os.path.join(FIX, "aeb1.jpg"), os.path.join(self.lib, "P1.JPG"))
        # the negative, beside it, with nothing readable in it
        with open(os.path.join(self.lib, "P1.RW2"), "wb") as fh:
            fh.write(b"\x00" * 2048)

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def _plan(self):
        return B.plan({"folder": self.lib, "shape": "year_month", "by": "date"})

    def test_the_negative_goes_where_its_jpeg_goes(self):
        p = self._plan()
        where = {os.path.basename(r.source): os.path.dirname(r.target)
                 for r in p.rows if r.what == "move"}
        self.assertIn("P1.RW2", where, "the negative was left behind")
        self.assertEqual(where["P1.RW2"], where["P1.JPG"])

    def test_and_it_says_which_photograph_it_belongs_to(self):
        p = self._plan()
        raw = [r for r in p.rows if os.path.basename(r.source) == "P1.RW2"][0]
        self.assertIn("the RAW file of P1.JPG", raw.detail)

    def test_it_is_not_in_the_left_alone_list_as_well(self):
        """It used to be there, under "no capture time" - which was true and
        completely the wrong thing to do about it."""
        p = self._plan()
        left = [os.path.basename(s[0]) for s in p.skipped]
        self.assertNotIn("P1.RW2", left)

    def test_a_negative_with_no_jpeg_of_its_own_is_still_left_alone(self):
        """Nothing to follow, and no date to file it under by itself. Saying so
        is right; moving it somewhere invented is not."""
        os.rename(os.path.join(self.lib, "P1.RW2"),
                  os.path.join(self.lib, "LONE.RW2"))
        p = self._plan()
        left = [os.path.basename(s[0]) for s in p.skipped]
        self.assertIn("LONE.RW2", left)

    def test_a_negative_whose_jpeg_does_not_move_does_not_move_either(self):
        """It is already beside it, which is the whole point."""
        first = self._plan()
        done = [os.path.dirname(r.target) for r in first.rows
                if os.path.basename(r.source) == "P1.JPG"][0]
        os.makedirs(done, exist_ok=True)
        for name in ("P1.JPG", "P1.RW2"):
            shutil.move(os.path.join(self.lib, name), os.path.join(done, name))
        again = self._plan()
        moved = [os.path.basename(r.source) for r in again.rows if r.what == "move"]
        self.assertEqual(moved, [], "nothing had anywhere else to go")

if __name__ == "__main__":
    unittest.main()


class FilingIntoAnotherFolder(Messy):
    """A card's worth sorted straight into the year it belongs in, rather than
    into the card dump it arrived as."""

    def test_the_new_folders_are_built_where_you_said(self):
        target = os.path.join(self.lib, "Archive")
        os.makedirs(target)
        t, p = self.sort(folder=self.card, into=target, shape="year_month")
        from core.paths import under as _under
        self.assertTrue(all(_under(r.target, os.path.join(target, "2022"))
                            for r in p.rows if _under(r.target, self.lib)),
                        [r.target for r in p.rows])
        t.apply(p)
        self.assertTrue(os.path.isfile(
            os.path.join(target, "2022", "07", "plain.JPG")))

    def test_and_the_raw_follows_to_the_same_place_in_its_tree(self):
        target = os.path.join(self.lib, "Archive")
        os.makedirs(target)
        t, p = self.sort(folder=self.card, into=target, shape="year_month",
                         raw=self.raw, previews=self.prev)
        t.apply(p)
        self.assertTrue(os.path.isfile(
            os.path.join(self.raw, "Archive", "2022", "07", "plain.RW2")))

    def test_a_folder_outside_the_library_is_refused(self):
        """The other trees mirror the library. A shoot filed outside it has no
        position in them, and its RAW would have nowhere to go."""
        outside = os.path.join(self.dir, "Elsewhere")
        os.makedirs(outside)
        p = R.get("bydate").make_plan({"folder": self.card, "into": outside})
        self.assertIn("not inside the library", p.blocked)

    def test_and_so_is_one_inside_the_raw_tree(self):
        S.save({"library": self.dir, "raw": self.raw, "previews": self.prev})
        p = R.get("bydate").make_plan({"folder": self.card,
                                       "into": os.path.join(self.raw, "x"),
                                       "raw": self.raw})
        self.assertTrue(p.blocked)

    def test_blank_still_sorts_in_place(self):
        _t, p = self.sort(folder=self.card, shape="year_month")
        self.assertTrue(any(r.target.startswith(os.path.join(self.card, "2022"))
                            for r in p.rows))


class SortingOneFolderKeepsTheMirror(Messy):
    def test_a_card_s_raws_land_beside_the_card_not_at_the_top_of_the_tree(self):
        """Sort one card dump, not the whole library, and the RAWs used to go
        to the TOP of the RAW tree - because they were mirrored from the folder
        being sorted rather than from the library the trees mirror."""
        t, p = self.sort(folder=self.card, shape="year_month",
                         raw=self.raw, previews=self.prev)
        t.apply(p)
        self.assertTrue(os.path.isfile(os.path.join(
            self.raw, "100MSDCF", "2022", "07", "plain.RW2")))
        self.assertFalse(os.path.isdir(os.path.join(self.raw, "2022")))

    def test_and_its_previews_are_found_and_follow(self):
        t, p = self.sort(folder=self.card, shape="year_month",
                         raw=self.raw, previews=self.prev)
        t.apply(p)
        self.assertTrue(os.path.isfile(os.path.join(
            self.prev, "100MSDCF", "2022", "07", "plain.JPG")))


class TheTreeBeforeAnythingMoves(Messy):
    """Four hundred "a.JPG -> 2022/07/a.JPG" lines are correct and say nothing
    about the SHAPE you are about to have."""

    def test_rows_are_gathered_under_the_folder_they_land_in(self):
        _t, p = self.sort(folder=self.card, shape="year_month")
        keys = {g["key"] for g in p.groups}
        self.assertIn("to:2022/07", keys)
        self.assertTrue(all(r.group == "to:2022/07"
                            for r in p.rows if "2022" in r.target))

    def test_and_a_shot_s_raw_is_counted_under_the_same_heading(self):
        """One decision, not three scattered ones."""
        _t, p = self.sort(folder=self.card, shape="year_month",
                          raw=self.raw, previews=self.prev)
        g = [g for g in p.groups if g["key"] == "to:2022/07"][0]
        self.assertIn("RAW", g["cells"][0])

    def test_it_says_which_folders_are_new(self):
        _t, p = self.sort(folder=self.card, shape="year_month")
        g = [g for g in p.groups if g["key"] == "to:2022/07"][0]
        self.assertIn("(new)", g["label"])
        self.assertIn("Folders it will fill", dict(p.stats))

    def test_planning_alone_makes_no_folder(self):
        self.sort(folder=self.card, shape="year_month")
        self.assertFalse(os.path.isdir(os.path.join(self.card, "2022")))