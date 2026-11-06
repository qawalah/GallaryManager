"""Storage: where the disk went, folder by folder, and what could be freed."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.tasks  # noqa: E402,F401
from app.tasks import space as SP                 # noqa: E402
from core import settings as S                    # noqa: E402
from core import survey as SV                     # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="space-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        os.makedirs(os.environ["PM_DATA"])
        self.share = os.path.join(self.dir, "share")
        self.lib = os.path.join(self.share, "Photos")
        self.raw = os.path.join(self.share, "Photos Raw")
        self.previews = os.path.join(self.share, "Previews")
        for one in (self.lib, self.raw, self.previews):
            os.makedirs(one)
        S.save({"library": self.lib, "raw": self.raw, "previews": self.previews})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def photo(self, folder, name="a.JPG", pad=0):
        os.makedirs(folder, exist_ok=True)
        where = os.path.join(folder, name)
        shutil.copy(os.path.join(FIX, "aeb1.jpg"), where)
        if pad:
            with open(where, "ab") as fh:
                fh.write(b"\0" * pad)
        return where

    def rows(self, p, group):
        return [r for r in p.rows if r.group == group]


class WhereTheSpaceIs(_Tmp):
    def test_the_biggest_folder_is_first(self):
        self.photo(os.path.join(self.lib, "2022", "Small"))
        self.photo(os.path.join(self.lib, "2022", "Big"), pad=200_000)
        p = SP.plan({"folder": self.lib, "depth": 2})
        names = [r.name for r in self.rows(p, "folders")]
        self.assertEqual(names[0], os.path.join("2022", "Big"))

    def test_a_shoot_carries_its_raws_and_previews(self):
        self.photo(os.path.join(self.lib, "2022", "Spain"))
        self.photo(os.path.join(self.raw, "2022", "Spain"), "a.RW2", pad=300_000)
        self.photo(os.path.join(self.previews, "2022", "Spain"), "a.JPG")
        p = SP.plan({"folder": self.lib, "depth": 2})
        row = self.rows(p, "folders")[0]
        # photos, library, RAWs, previews, video, aside, total, share -
        # the negatives are the big number, and each tree has its own column
        photos, lib, raws, previews = row.cells[0], row.cells[1], row.cells[2], row.cells[3]
        self.assertEqual(photos, "1")
        self.assertTrue(lib.endswith(("B", "KB")), lib)
        self.assertTrue(raws.endswith(("KB", "MB")), raws)
        self.assertTrue(previews.endswith(("B", "KB")), previews)
        self.assertEqual(row.cells[4], "0 B")             # no video tree here
        self.assertGreater(row.size, 300_000)

    def test_nothing_is_counted_twice(self):
        """A parent listed as well as its children would double every byte."""
        self.photo(os.path.join(self.lib, "2022", "Spain"), pad=50_000)
        self.photo(os.path.join(self.lib, "2022", "Italy"), pad=50_000)
        p = SP.plan({"folder": self.lib, "depth": 2})
        rows = self.rows(p, "folders")
        self.assertEqual(sorted(r.name for r in rows),
                         [os.path.join("2022", "Italy"),
                          os.path.join("2022", "Spain")])
        everything = dict(p.stats)["Everything, all trees"]
        self.assertNotIn("TB", everything)
        listed = sum(r.size for r in rows)
        self.assertLessEqual(listed, SV.survey(self.lib).folders[self.lib]
                             .totals(SV.survey(self.lib).folders).weight() + 1)

    def test_one_level_down_lists_the_years(self):
        self.photo(os.path.join(self.lib, "2022", "Spain"))
        self.photo(os.path.join(self.lib, "2023", "Italy"))
        p = SP.plan({"folder": self.lib, "depth": 1})
        self.assertEqual(sorted(r.name for r in self.rows(p, "folders")),
                         ["2022", "2023"])

    def test_a_shallow_leaf_is_still_listed(self):
        """A folder with photographs and no children at depth 1 would otherwise
        vanish when you asked for depth 2."""
        self.photo(os.path.join(self.lib, "Loose"))
        self.photo(os.path.join(self.lib, "2022", "Spain"))
        p = SP.plan({"folder": self.lib, "depth": 2})
        self.assertIn("Loose", [r.name for r in self.rows(p, "folders")])

    def test_the_trees_can_be_left_out(self):
        self.photo(os.path.join(self.lib, "2022", "Spain"))
        self.photo(os.path.join(self.raw, "2022", "Spain"), "a.RW2", pad=300_000)
        p = SP.plan({"folder": self.lib, "depth": 2, "with_raw": False})
        self.assertEqual(dict(p.stats)["RAWs"], "0 B")

    def test_a_missing_library_is_said_not_crashed(self):
        self.assertTrue(SP.plan({"folder": os.path.join(self.dir, "no")}).blocked)

    def test_it_writes_nothing(self):
        self.photo(os.path.join(self.lib, "2022", "Spain"))
        self.assertEqual(SP.apply(SP.plan({"folder": self.lib})).done, 0)


class WhatCouldBeFreed(_Tmp):
    def test_a_culled_pile_is_offered_back(self):
        self.photo(os.path.join(self.lib, "2022", "Spain"))
        self.photo(os.path.join(self.lib, "_Culled", "2022", "Spain"),
                   "old.JPG", pad=100_000)
        p = SP.plan({"folder": self.lib, "depth": 2})
        back = self.rows(p, "back")
        self.assertTrue(any("_Culled" in r.name for r in back), back)
        self.assertNotEqual(dict(p.stats)["Could be freed"], "0 B")

    def test_previews_count_as_reclaimable_because_they_can_be_remade(self):
        self.photo(os.path.join(self.lib, "2022", "Spain"))
        self.photo(os.path.join(self.previews, "2022", "Spain"), "a.JPG")
        p = SP.plan({"folder": self.lib, "depth": 2})
        self.assertTrue(any(r.name == "Previews" for r in self.rows(p, "back")))

    def test_the_photographs_themselves_are_never_in_that_list(self):
        self.photo(os.path.join(self.lib, "2022", "Spain"), pad=400_000)
        self.photo(os.path.join(self.raw, "2022", "Spain"), "a.RW2", pad=400_000)
        p = SP.plan({"folder": self.lib, "depth": 2})
        for r in self.rows(p, "back"):
            self.assertNotIn("Photos Raw", r.source)
            self.assertNotEqual(r.source, self.lib)

    def test_the_recycle_bin_of_the_share_is_counted(self):
        self.photo(os.path.join(self.lib, "2022", "Spain"))
        self.photo(os.path.join(self.share, "#recycle"), "gone.JPG", pad=90_000)
        p = SP.plan({"folder": self.lib, "depth": 2})
        self.assertTrue(any("Recycle" in r.name for r in self.rows(p, "back")))


class TheSurveyUnderneath(_Tmp):
    def test_a_folder_knows_what_it_weighs_in_every_tree(self):
        self.photo(os.path.join(self.lib, "2022", "Spain"))
        self.photo(os.path.join(self.raw, "2022", "Spain"), "a.RW2", pad=1000)
        got = SV.survey(self.lib, self.raw, self.previews)
        state = got.folders[os.path.join(self.lib, "2022", "Spain")]
        self.assertGreater(state.bytes, 0)
        self.assertGreater(state.raw_bytes, 1000)
        self.assertEqual(state.weight(), state.bytes + state.raw_bytes)

    def test_and_how_many_of_its_photographs_carry_a_date(self):
        self.photo(os.path.join(self.lib, "2022", "Spain"))
        got = SV.survey(self.lib)
        state = got.folders[os.path.join(self.lib, "2022", "Spain")]
        self.assertEqual(state.photos, 1)
        self.assertEqual(state.dated, 1)
        self.assertEqual(state.marks()["dated"], "all")

    def test_a_file_that_cannot_be_read_gets_its_own_mark(self):
        where = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(where)
        with open(os.path.join(where, "broken.JPG"), "wb") as fh:
            fh.write(b"not a jpeg at all")
        got = SV.survey(self.lib)
        state = got.folders[where]
        self.assertEqual(state.unreadable, 1)
        self.assertEqual(state.marks()["readable"], "none")

    def test_weights_roll_up_the_tree(self):
        self.photo(os.path.join(self.lib, "2022", "Spain"), pad=10_000)
        self.photo(os.path.join(self.lib, "2022", "Italy"), pad=10_000)
        got = SV.survey(self.lib)
        year = got.folders[os.path.join(self.lib, "2022")].totals(got.folders)
        one = got.folders[os.path.join(self.lib, "2022", "Spain")]
        self.assertGreater(year.bytes, one.bytes)


if __name__ == "__main__":
    unittest.main()
