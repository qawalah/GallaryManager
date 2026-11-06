"""The sample library: real enough to teach, and safe enough to delete.

Two different promises, and the second one is the serious one. A feature that
deletes a folder you named has to be unable to delete the wrong folder, and
"unable" means a test, not a careful author.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R                # noqa: E402
import app.tasks                            # noqa: E402,F401
from core import demo, photo, video          # noqa: E402

try:
    import PIL                              # noqa: F401
    HAVE_PIL = True
except Exception:                           # noqa: BLE001
    HAVE_PIL = False


class WhatItSaysItWillMake(unittest.TestCase):
    """The recipe is readable without building anything, which is what lets the
    plan say exactly what it would write."""

    def test_the_recipe_counts_what_the_table_holds(self):
        r = demo.recipe()
        self.assertEqual(r["pictures"], len(demo.SHOTS))
        self.assertEqual(r["clips"], len(demo.CLIPS))
        self.assertEqual(r["negatives"],
                         len([s for s in demo.SHOTS if s[7].get("raw")]))

    def test_it_is_small_enough_to_build_while_you_wait(self):
        """A sample library that takes a minute is one nobody builds twice."""
        self.assertLess(demo.recipe()["files"], 120)

    def test_the_negatives_go_beside_the_jpeg_and_into_the_tree(self):
        homes = {demo._raw_home(s) for s in demo.SHOTS if s[7].get("raw")}
        self.assertIn(demo.INBOX, homes)
        self.assertTrue(any(h.startswith(demo.RAWTREE) for h in homes),
                        "nothing lands in a mirrored RAW tree, so Re-mirror has "
                        "nothing to do")

    def test_a_mirrored_negative_keeps_its_position(self):
        for shot in demo.SHOTS:
            folder = os.path.dirname(shot[0])
            if not shot[7].get("raw") or not folder.startswith(demo.LIBRARY):
                continue
            self.assertEqual(demo._raw_home(shot),
                             demo.RAWTREE + folder[len(demo.LIBRARY):])


class TheFaultsAreReallyThere(unittest.TestCase):
    """A feature with nothing to find teaches nothing, so each awkward case the
    docstring promises is checked for rather than hoped for."""

    def test_a_bracketed_set_of_three_one_second_apart(self):
        ev = [s for s in demo.SHOTS if "ev" in s[7]]
        self.assertEqual(len(ev), 3)
        self.assertEqual(sorted(s[7]["ev"] for s in ev), [-1, 0, 1])

    def test_two_pairs_of_duplicates_and_nothing_else_shares_pixels(self):
        seeds = [s[7]["pixels"] for s in demo.SHOTS if s[7].get("pixels")]
        self.assertEqual(len(seeds), 4)
        self.assertEqual(len(set(seeds)), 2)

    def test_something_blurry_something_undated_and_a_wrong_clock(self):
        self.assertTrue([s for s in demo.SHOTS if s[7].get("blur")])
        self.assertTrue([s for s in demo.SHOTS if s[7].get("no_exif")])
        # A phone shot carrying BOTH a wall-clock time and a GPS time is the
        # only way the clock check can prove the clock is wrong.
        self.assertTrue([s for s in demo.SHOTS
                         if s[7].get("gpstime") and s[7].get("gps")])

    def test_more_than_one_camera_and_more_than_one_year(self):
        self.assertGreater(len({s[2][1] for s in demo.SHOTS}), 1)
        self.assertGreater(len({s[1][:4] for s in demo.SHOTS if s[1]}), 1)

    def test_some_photographs_have_no_negative(self):
        """All of them having one is the unrealistic case, and the one where
        Separate RAWs looks like it works perfectly on every library."""
        self.assertTrue([s for s in demo.SHOTS if not s[7].get("raw")])


class TheClipHeader(unittest.TestCase):
    def test_a_clip_says_when_it_was_taken(self):
        when = "2024:11:16 18:30:00"
        folder = tempfile.mkdtemp()
        path = os.path.join(folder, "clip.MP4")
        try:
            with open(path, "wb") as fh:
                fh.write(demo.clip_bytes(when))
            got = video.capture_of(path)
            self.assertTrue(got, "the header is not readable")
            self.assertEqual(got.taken.strftime("%Y:%m:%d %H:%M:%S"), when)
        finally:
            shutil.rmtree(folder, ignore_errors=True)


@unittest.skipUnless(HAVE_PIL, "building pictures needs Pillow")
class OnceItIsBuilt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp()
        cls.root = os.path.join(cls.home, "Sample library")
        cls.out = demo.build(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)

    def test_everything_was_written_and_nothing_failed(self):
        self.assertEqual(self.out["failed"], [])
        self.assertEqual(len(self.out["made"]), demo.recipe()["files"],
                         "the recipe and what was written disagree")

    def test_the_exif_reads_back_as_a_camera_would_have_written_it(self):
        got = photo.read_capture(os.path.join(self.root, demo.INBOX, "DSC01184.JPG"))
        self.assertTrue(got.ok)
        self.assertEqual(got.model, "ILCE-7C")
        self.assertEqual(got.iso, 100)
        self.assertEqual(got.fnumber, 8.0)
        self.assertEqual(got.focal_length, 24.0)
        self.assertIn("24-105", got.lens or "")
        self.assertEqual(got.taken.strftime("%Y-%m-%d %H:%M"), "2025-03-02 07:12")

    def test_a_negative_is_as_opaque_as_a_real_one(self):
        """This is the realistic half, not a shortcut: the app cannot read EXIF
        out of a RW2 either, so a sample negative has to be matched by name and
        position exactly like the real thing."""
        got = photo.read_capture(os.path.join(self.root, demo.INBOX, "P1010431.RW2"))
        self.assertFalse(got.ok)
        self.assertIsNone(got.taken)
        self.assertEqual(photo.kind(os.path.join(self.root, demo.INBOX,
                                                 "P1010431.RW2")), "raw")

    def test_a_located_photograph_really_carries_a_position(self):
        where = photo.read_gps(os.path.join(self.root, demo.LIBRARY, "2023",
                                            "Spain", "Alhambra-01.JPG"))
        self.assertTrue(where)
        self.assertAlmostEqual(where.lat, 37.176, places=2)
        self.assertAlmostEqual(where.lon, -3.588, places=2)

    def _bytes(self, *parts):
        with open(os.path.join(self.root, *parts), "rb") as fh:
            return fh.read()

    def test_the_duplicates_really_are_identical(self):
        self.assertEqual(self._bytes(demo.INBOX, "DSC01193.JPG"),
                         self._bytes(demo.INBOX, "DSC01193 (1).JPG"))

    def test_and_two_photographs_that_are_not_duplicates_are_not(self):
        self.assertNotEqual(self._bytes(demo.INBOX, "P1010431.JPG"),
                            self._bytes(demo.INBOX, "P1010432.JPG"))

    def test_building_again_overwrites_nothing(self):
        again = demo.build(self.root)
        self.assertEqual(again["made"], [])
        self.assertEqual(len(again["kept"]), demo.recipe()["files"])

    def test_it_knows_it_built_this_one(self):
        self.assertTrue(demo.built(self.root))
        self.assertEqual(demo.removable(self.root), "")


class ItWillNotDeleteSomebodyElsesFolder(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_a_folder_it_did_not_build_is_refused(self):
        mine = os.path.join(self.home, "Photos")
        os.makedirs(os.path.join(mine, "2022"))
        open(os.path.join(mine, "2022", "precious.JPG"), "w").close()
        said = demo.removable(mine)
        self.assertTrue(said)
        out = demo.remove(mine)
        self.assertEqual(out["gone"], 0)
        self.assertTrue(out["why"])
        self.assertTrue(os.path.isfile(os.path.join(mine, "2022", "precious.JPG")),
                        "it deleted a folder it did not build")

    def test_and_the_tab_refuses_before_it_offers_a_button(self):
        """Refused in the PLAN, not caught in apply: the page must never draw
        "Remove 400 files" over somebody's library and leave the check to the
        moment after they press it."""
        mine = os.path.join(self.home, "Photos")
        os.makedirs(mine)
        task = R.get("demo")
        p = task.make_plan({"folder": mine, "doing": "remove"})
        self.assertTrue(p.blocked)
        self.assertEqual(p.rows, [])

    def test_a_marker_it_wrote_itself_is_what_makes_it_willing(self):
        root = os.path.join(self.home, "Sample")
        os.makedirs(root)
        open(os.path.join(root, "a.jpg"), "w").close()
        self.assertTrue(demo.removable(root))
        open(os.path.join(root, demo.MARK), "w").close()
        self.assertEqual(demo.removable(root), "")
        self.assertEqual(demo.remove(root)["gone"], 2)
        self.assertFalse(os.path.isdir(root))


class TheTab(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_it_says_what_it_would_build_without_building_it(self):
        root = os.path.join(self.home, "Sample")
        p = R.get("demo").make_plan({"folder": root, "doing": "build"})
        self.assertFalse(p.blocked)
        self.assertTrue(p.rows)
        self.assertFalse(os.path.exists(root), "the plan wrote something")

    def test_with_no_folder_it_asks_for_one_rather_than_choosing(self):
        p = R.get("demo").make_plan({"folder": "", "doing": "build"})
        self.assertIn("Choose a folder", p.blocked)

    def test_the_button_says_files_not_folders(self):
        """The rows are folders and the thing being written is files - a button
        reading "Build 4 files" would be the wrong number twice over."""
        root = os.path.join(self.home, "Sample")
        task = R.get("demo")
        p = task.make_plan({"folder": root, "doing": "build"})
        im = R.impact_of(task, p)
        self.assertEqual(im["count"], demo.recipe()["files"])
        self.assertEqual(im["unit"], "files")

    def test_removing_it_is_marked_as_the_thing_you_cannot_undo(self):
        root = os.path.join(self.home, "Sample")
        os.makedirs(root)
        open(os.path.join(root, demo.MARK), "w").close()
        task = R.get("demo")
        p = task.make_plan({"folder": root, "doing": "remove"})
        self.assertEqual(R.impact_of(task, p)["risk"], "high")


if __name__ == "__main__":
    unittest.main()
