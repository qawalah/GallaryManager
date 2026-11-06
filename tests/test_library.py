"""The library view: what each folder's marks claim, and whether it is true.

A status display that is subtly wrong is worse than none, because you act on it.
So the tests here are mostly about the three ways it could lie:

- saying a job is done when it is half done ("some" must not read as "all"),
- going stale when you reorganise the library by hand,
- serving a cached answer for a folder whose contents have changed.

The cache is the risky part. It exists because reading every JPEG over SMB is
slow, and a cache that does not notice a change turns a correct display into a
confidently wrong one.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from core import survey as SV              # noqa: E402
from core.exifwrite import write_gps, write_rating   # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Library(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="library-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.prev = os.path.join(self.dir, "Photos Previews")
        self.shoot = os.path.join(self.lib, "A7c", "Morocco")
        os.makedirs(self.shoot)
        for n in ("burst1", "burst2", "burst3"):
            shutil.copy(os.path.join(FIX, f"{n}.jpg"),
                        os.path.join(self.shoot, f"{n}.JPG"))

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def put(self, tree, rel, names, ext):
        folder = os.path.join(tree, *rel.split("/"))
        os.makedirs(folder, exist_ok=True)
        for n in names:
            shutil.copy(os.path.join(FIX, f"{n}.jpg"),
                        os.path.join(folder, f"{n}{ext}"))

    def look(self, **over):
        t = R.get("library")
        p = t.make_plan({"folder": self.lib, "raw": self.raw,
                         "previews": self.prev, **over})
        self.assertFalse(p.blocked, p.blocked)
        return p

    def node(self, plan, name):
        for n in plan.tree:
            if n["name"] == name:
                return n
        self.fail(f"{name} is not in the tree: {[n['name'] for n in plan.tree]}")


class WhatTheMarksSay(Library):
    def test_a_shoot_straight_off_the_card_is_marked_undone(self):
        self.put(self.lib, "A7c/Morocco", ["burst1", "burst2", "burst3"], ".RW2")
        marks = self.node(self.look(), "Morocco")["marks"]
        self.assertEqual(marks["separated"], "none")
        self.assertEqual(marks["rated"], "none")
        self.assertEqual(marks["located"], "none")
        self.assertEqual(marks["previews"], "none")

    def test_separated_raws_show_as_done(self):
        self.put(self.raw, "A7c/Morocco", ["burst1", "burst2", "burst3"], ".RW2")
        node = self.node(self.look(), "Morocco")
        self.assertEqual(node["marks"]["separated"], "all")
        self.assertEqual(node["raws_apart"], 3)
        self.assertEqual(node["raws_here"], 0)

    def test_half_separated_is_some_and_not_all(self):
        """The whole reason for a middle state: an unfinished job must not look
        like a finished one."""
        self.put(self.lib, "A7c/Morocco", ["burst1"], ".RW2")
        self.put(self.raw, "A7c/Morocco", ["burst2", "burst3"], ".RW2")
        self.assertEqual(self.node(self.look(), "Morocco")["marks"]["separated"], "some")

    def test_half_geotagged_is_some(self):
        write_gps(os.path.join(self.shoot, "burst1.JPG"), 41.38, 2.17)
        node = self.node(self.look(), "Morocco")
        self.assertEqual(node["marks"]["located"], "some")
        self.assertEqual(node["located"], 1)

    def test_all_geotagged_is_all(self):
        for n in ("burst1", "burst2", "burst3"):
            write_gps(os.path.join(self.shoot, f"{n}.JPG"), 41.38, 2.17)
        self.assertEqual(self.node(self.look(), "Morocco")["marks"]["located"], "all")

    def test_ratings_are_counted(self):
        write_rating(os.path.join(self.shoot, "burst1.JPG"), 4)
        write_rating(os.path.join(self.shoot, "burst2.JPG"), 2)
        node = self.node(self.look(), "Morocco")
        self.assertEqual(node["rated"], 2)
        self.assertEqual(node["marks"]["rated"], "some")

    def test_a_zero_rating_is_not_a_rating(self):
        """Zero means unrated everywhere else in this app; it must here too."""
        write_rating(os.path.join(self.shoot, "burst1.JPG"), 0)
        self.assertEqual(self.node(self.look(), "Morocco")["rated"], 0)

    def test_previews_are_counted_from_the_previews_tree(self):
        self.put(self.prev, "A7c/Morocco", ["burst1", "burst2"], ".jpg")
        node = self.node(self.look(), "Morocco")
        self.assertEqual(node["previews"], 2)
        self.assertEqual(node["marks"]["previews"], "some")

    def test_culled_things_are_counted(self):
        self.put(self.lib, "_Culled/A7c/Morocco", ["burst1"], ".JPG")
        node = self.node(self.look(), "Morocco")
        self.assertEqual(node["culled"], 1)
        self.assertEqual(node["marks"]["culled"], "some")

    def test_the_culled_folder_is_not_shown_as_a_folder_of_the_library(self):
        self.put(self.lib, "_Culled/A7c/Morocco", ["burst1"], ".JPG")
        self.assertNotIn("_Culled", [n["name"] for n in self.look().tree])

    def test_a_sidecar_rating_counts_too(self):
        from core.exifwrite import set_rating
        self.put(self.lib, "A7c/Morocco", ["aeb1"], ".RW2")
        set_rating(os.path.join(self.shoot, "aeb1.RW2"), 5)
        # the RAW is not a photo, but its sidecar must not break the read
        self.assertEqual(self.node(self.look(), "Morocco")["raws_here"], 1)


class RollingUp(Library):
    def test_a_parent_totals_everything_beneath_it(self):
        self.put(self.lib, "A7c/Italy", ["aeb1", "aeb2"], ".JPG")
        node = self.node(self.look(), "A7c")
        self.assertEqual(node["photos"], 5)          # 3 in Morocco, 2 in Italy

    def test_and_the_root_totals_the_whole_library(self):
        self.put(self.lib, "GH4/Hasa", ["aeb1"], ".JPG")
        self.assertEqual(self.node(self.look(), "Photos")["photos"], 4)

    def test_a_parent_of_a_finished_and_an_unfinished_shoot_reads_as_some(self):
        for n in ("burst1", "burst2", "burst3"):
            write_gps(os.path.join(self.shoot, f"{n}.JPG"), 41.38, 2.17)
        self.put(self.lib, "A7c/Italy", ["aeb1", "aeb2"], ".JPG")
        self.assertEqual(self.node(self.look(), "A7c")["marks"]["located"], "some")


class ItReadsTheDiskNotAHistory(Library):
    def test_moving_a_shoot_moves_its_marks_with_it(self):
        """A log of what was done would still be talking about the old path."""
        self.put(self.raw, "A7c/Morocco", ["burst1", "burst2", "burst3"], ".RW2")
        self.assertEqual(self.node(self.look(), "Morocco")["marks"]["separated"], "all")

        os.makedirs(os.path.join(self.lib, "Trips"))
        shutil.move(self.shoot, os.path.join(self.lib, "Trips", "Morocco 2022"))
        p = self.look()
        node = self.node(p, "Morocco 2022")
        self.assertEqual(node["photos"], 3)
        # No RAWs either side of the new position, so the mark honestly has
        # nothing to say - but the RAWs left behind must not go unmentioned.
        self.assertEqual(node["marks"]["separated"], "empty")
        self.assertTrue(any("no longer exist in the library" in n for n in p.notes),
                        p.notes)
        self.assertIn(("RAWs with no folder in the library", "3"), p.stats)

    def test_deleting_photos_by_hand_shows_up(self):
        self.assertEqual(self.node(self.look(), "Morocco")["photos"], 3)
        os.remove(os.path.join(self.shoot, "burst1.JPG"))
        self.assertEqual(self.node(self.look(), "Morocco")["photos"], 2)


class RawsLeftBehind(Library):
    """A renamed shoot leaves its RAWs where they were. Both halves then look
    quiet, and this count is the only thing that says otherwise."""

    def test_a_matching_raw_folder_is_not_stranded(self):
        self.put(self.raw, "A7c/Morocco", ["burst1"], ".RW2")
        p = self.look()
        self.assertNotIn(("RAWs with no folder in the library", "1"), p.stats)

    def test_but_one_with_no_library_folder_is_counted(self):
        self.put(self.raw, "A7c/Gone", ["burst1", "burst2"], ".RW2")
        p = self.look()
        self.assertIn(("RAWs with no folder in the library", "2"), p.stats)
        self.assertTrue(any("Gone" in name for name, _why in p.skipped))

    def test_an_empty_raw_folder_is_not_reported(self):
        os.makedirs(os.path.join(self.raw, "A7c", "Empty"))
        p = self.look()
        self.assertFalse(any("Empty" in name for name, _why in p.skipped))


class TheCache(Library):
    def test_the_second_look_reads_nothing(self):
        self.look()
        p = self.look()
        self.assertIn("0 folder(s) read this time", " ".join(p.notes))

    def test_but_a_changed_folder_is_read_again(self):
        """The dangerous failure: a cache that does not notice, and answers
        confidently with yesterday's truth."""
        self.look()
        write_rating(os.path.join(self.shoot, "burst1.JPG"), 4)
        p = self.look()
        self.assertEqual(self.node(p, "Morocco")["rated"], 1)

    def test_a_new_photo_changes_the_signature(self):
        self.look()
        shutil.copy(os.path.join(FIX, "aeb1.jpg"),
                    os.path.join(self.shoot, "aeb1.JPG"))
        self.assertEqual(self.node(self.look(), "Morocco")["photos"], 4)

    def test_a_deleted_photo_does_too(self):
        self.look()
        os.remove(os.path.join(self.shoot, "burst2.JPG"))
        self.assertEqual(self.node(self.look(), "Morocco")["photos"], 2)

    def test_changing_one_shoot_does_not_re_read_the_others(self):
        self.put(self.lib, "A7c/Italy", ["aeb1"], ".JPG")
        self.look()
        write_rating(os.path.join(self.shoot, "burst1.JPG"), 4)
        p = self.look()
        self.assertIn("1 folder(s) read this time", " ".join(p.notes))

    def test_rescan_reads_everything_again(self):
        self.look()
        p = self.look(rescan="on")
        self.assertNotIn("0 folder(s) read this time", " ".join(p.notes))

    def test_a_damaged_cache_file_is_not_fatal(self):
        self.look()
        from core.store import store_path
        with open(store_path("survey.json"), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(self.node(self.look(), "Morocco")["photos"], 3)


class TheFilters(Library):
    def setUp(self):
        super().setUp()
        # Morocco: finished. Italy: nothing done.
        self.put(self.raw, "A7c/Morocco", ["burst1", "burst2", "burst3"], ".RW2")
        self.put(self.prev, "A7c/Morocco", ["burst1", "burst2", "burst3"], ".jpg")
        for n in ("burst1", "burst2", "burst3"):
            write_gps(os.path.join(self.shoot, f"{n}.JPG"), 41.38, 2.17)
            write_rating(os.path.join(self.shoot, f"{n}.JPG"), 3)
        self.put(self.lib, "A7c/Italy", ["aeb1", "aeb2"], ".JPG")
        self.put(self.lib, "A7c/Italy", ["aeb1"], ".RW2")

    def names(self, **over):
        return [n["name"] for n in self.look(**over).tree]

    def test_everything_shows_both(self):
        got = self.names()
        self.assertIn("Morocco", got)
        self.assertIn("Italy", got)

    def test_raws_still_in_the_library(self):
        got = self.names(only="raws")
        self.assertIn("Italy", got)
        self.assertNotIn("Morocco", got)

    def test_unrated(self):
        got = self.names(only="unrated")
        self.assertIn("Italy", got)
        self.assertNotIn("Morocco", got)

    def test_unlocated(self):
        got = self.names(only="unlocated")
        self.assertIn("Italy", got)
        self.assertNotIn("Morocco", got)

    def test_a_filter_keeps_the_parents_so_the_tree_stays_navigable(self):
        got = self.names(only="raws")
        self.assertIn("A7c", got)
        self.assertIn("Photos", got)


class ItNeverWrites(Library):
    def test_the_task_says_it_only_reports(self):
        self.assertFalse(R.get("library").writes)

    def test_and_looking_changes_nothing_on_disk(self):
        before = {}
        for here, _dirs, names in os.walk(self.lib):
            for n in names:
                path = os.path.join(here, n)
                before[path] = os.stat(path).st_mtime_ns
        self.look()
        after = {}
        for here, _dirs, names in os.walk(self.lib):
            for n in names:
                path = os.path.join(here, n)
                after[path] = os.stat(path).st_mtime_ns
        self.assertEqual(before, after)

    def test_a_library_that_is_not_there_is_refused(self):
        t = R.get("library")
        p = t.make_plan({"folder": os.path.join(self.dir, "nope")})
        self.assertTrue(p.blocked)
        self.assertEqual(p.tree, [])


if __name__ == "__main__":
    unittest.main()
