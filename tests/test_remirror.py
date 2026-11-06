"""Re-mirroring, and the one mistake that would make it dangerous.

The scenario each test builds is the real one: photos separated into two trees,
then the library reorganised afterwards - renamed, moved, nested deeper - and the
RAW tree asked to catch up.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R          # noqa: E402
import app.tasks                       # noqa: E402,F401
from core import paths, pairs          # noqa: E402
from core.photo import read_capture    # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Tree(unittest.TestCase):
    """A library and a RAW tree, already separated, ready to be reorganised."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="remirror-")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.shoot("GH4/Spain 22", ["aeb1", "aeb2", "aeb3"])
        self.shoot("GH4/Morocco", ["burst1", "burst2"])

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def shoot(self, rel, names):
        """One shoot: JPEGs in the library, matching RAWs in the RAW tree."""
        ldir = os.path.join(self.lib, *rel.split("/"))
        rdir = os.path.join(self.raw, *rel.split("/"))
        os.makedirs(ldir, exist_ok=True)
        os.makedirs(rdir, exist_ok=True)
        for n in names:
            shutil.copy(os.path.join(FIX, f"{n}.jpg"), os.path.join(ldir, f"{n}.JPG"))
            # a RAW carrying the same EXIF as its JPEG, which is what pairs them
            shutil.copy(os.path.join(FIX, f"{n}.jpg"), os.path.join(rdir, f"{n}.RW2"))

    def run_plan(self, **over):
        t = R.get("remirror")
        raw = {"library": self.lib, "raw": self.raw, **over}
        # make_plan, not plan: it is what the command line and the web page call,
        # and it is what puts the chosen options where apply() can see them.
        return t, t.coerce(raw), t.make_plan(raw)

    def raw_files(self):
        out = []
        for here, _dirs, names in os.walk(self.raw):
            for n in names:
                out.append(os.path.relpath(os.path.join(here, n), self.raw)
                           .replace("\\", "/"))
        return sorted(out)


class NothingToDo(Tree):
    def test_a_tidy_pair_of_trees_needs_no_moves(self):
        _, _, p = self.run_plan()
        self.assertEqual(p.rows, [])
        self.assertIn(("Already in the right place", "5"), p.stats)

    def test_and_applying_it_changes_nothing(self):
        before = self.raw_files()
        t, _, p = self.run_plan()
        t.apply(p)
        self.assertEqual(self.raw_files(), before)


class TheLibraryWasReorganised(Tree):
    def test_a_renamed_folder_is_followed(self):
        os.rename(os.path.join(self.lib, "GH4", "Spain 22"),
                  os.path.join(self.lib, "GH4", "Spain July 2022"))
        t, _, p = self.run_plan()
        self.assertEqual(len(p.rows), 3)
        t.apply(p)
        self.assertIn("GH4/Spain July 2022/aeb1.RW2", self.raw_files())
        self.assertNotIn("GH4/Spain 22/aeb1.RW2", self.raw_files())

    def test_a_folder_moved_somewhere_deeper_is_followed(self):
        deeper = os.path.join(self.lib, "GH4", "Travels", "2022")
        os.makedirs(deeper)
        shutil.move(os.path.join(self.lib, "GH4", "Spain 22"),
                    os.path.join(deeper, "Spain 22"))
        t, _, p = self.run_plan()
        t.apply(p)
        self.assertIn("GH4/Travels/2022/Spain 22/aeb2.RW2", self.raw_files())

    def test_a_shoot_split_in_two_sends_each_raw_to_its_own_half(self):
        src = os.path.join(self.lib, "GH4", "Spain 22")
        half = os.path.join(self.lib, "GH4", "Spain 22 day two")
        os.makedirs(half)
        shutil.move(os.path.join(src, "aeb3.JPG"), os.path.join(half, "aeb3.JPG"))
        t, _, p = self.run_plan()
        t.apply(p)
        files = self.raw_files()
        self.assertIn("GH4/Spain 22/aeb1.RW2", files)
        self.assertIn("GH4/Spain 22 day two/aeb3.RW2", files)

    def test_the_library_itself_is_never_touched(self):
        os.rename(os.path.join(self.lib, "GH4", "Spain 22"),
                  os.path.join(self.lib, "GH4", "Spain July 2022"))
        before = sorted(os.path.relpath(os.path.join(h, n), self.lib)
                        for h, _d, ns in os.walk(self.lib) for n in ns)
        t, _, p = self.run_plan()
        t.apply(p)
        after = sorted(os.path.relpath(os.path.join(h, n), self.lib)
                       for h, _d, ns in os.walk(self.lib) for n in ns)
        self.assertEqual(before, after)

    def test_folders_left_empty_are_tidied_away(self):
        os.rename(os.path.join(self.lib, "GH4", "Spain 22"),
                  os.path.join(self.lib, "GH4", "Spain July 2022"))
        t, _, p = self.run_plan()
        t.apply(p)
        self.assertFalse(os.path.isdir(os.path.join(self.raw, "GH4", "Spain 22")))


class TheMistakeThatWouldBeDangerous(Tree):
    """A moved JPEG and a deleted JPEG look identical from the RAW's position.

    Since moving is the whole reason this task exists, "not where I left it" can
    never be allowed to mean "delete the RAW".
    """

    def test_a_moved_jpeg_is_found_elsewhere_not_called_orphaned(self):
        os.rename(os.path.join(self.lib, "GH4", "Spain 22"),
                  os.path.join(self.lib, "GH4", "Somewhere Else"))
        _, _, p = self.run_plan()
        self.assertIn(("No photo found for them", "0"), p.stats)
        self.assertEqual(len(p.rows), 3)

    def test_no_raw_is_ever_put_aside_during_an_ordinary_reorganise(self):
        os.rename(os.path.join(self.lib, "GH4", "Spain 22"),
                  os.path.join(self.lib, "GH4", "Somewhere Else"))
        t, _, p = self.run_plan()
        t.apply(p)
        self.assertFalse(any(paths.CULLED in f for f in self.raw_files()))

    def test_a_genuinely_deleted_jpeg_makes_its_raw_an_orphan(self):
        os.remove(os.path.join(self.lib, "GH4", "Morocco", "burst1.JPG"))
        _, _, p = self.run_plan()
        self.assertIn(("No photo found for them", "1"), p.stats)

    def test_an_orphan_is_put_aside_not_deleted(self):
        os.remove(os.path.join(self.lib, "GH4", "Morocco", "burst1.JPG"))
        t, _, p = self.run_plan(orphans="aside")
        t.apply(p)
        files = self.raw_files()
        self.assertTrue(any(f.startswith(paths.CULLED) and f.endswith("burst1.RW2")
                            for f in files), files)
        self.assertTrue(any("burst1.RW2" in f for f in files), "it must still exist")

    def test_or_left_alone_if_you_prefer(self):
        os.remove(os.path.join(self.lib, "GH4", "Morocco", "burst1.JPG"))
        t, _, p = self.run_plan(orphans="leave")
        t.apply(p)
        self.assertIn("GH4/Morocco/burst1.RW2", self.raw_files())

    def test_or_merely_listed(self):
        os.remove(os.path.join(self.lib, "GH4", "Morocco", "burst1.JPG"))
        t, _, p = self.run_plan(orphans="list")
        self.assertEqual(p.rows, [])
        self.assertTrue(any("burst1" in name for name, _why in p.skipped))
        t.apply(p)
        self.assertIn("GH4/Morocco/burst1.RW2", self.raw_files())


class RefusingRatherThanGuessing(Tree):
    def test_the_same_folder_for_both_trees_is_refused(self):
        t = R.get("remirror")
        p = t.plan(t.coerce({"library": self.lib, "raw": self.lib}))
        self.assertIn("same folder", p.blocked)

    def test_a_missing_tree_is_refused(self):
        t = R.get("remirror")
        p = t.plan(t.coerce({"library": self.lib, "raw": self.raw + "-nope"}))
        self.assertTrue(p.blocked)

    def test_planning_moves_nothing(self):
        os.rename(os.path.join(self.lib, "GH4", "Spain 22"),
                  os.path.join(self.lib, "GH4", "Renamed"))
        before = self.raw_files()
        self.run_plan()
        self.assertEqual(self.raw_files(), before)

    def test_a_blocked_plan_does_nothing_even_if_applied(self):
        t = R.get("remirror")
        p = t.plan(t.coerce({"library": self.lib, "raw": self.raw + "-nope"}))
        before = self.raw_files()
        t.apply(p)
        self.assertEqual(self.raw_files(), before)


class PairingOnWhatFilesAreNotWhereTheyAre(unittest.TestCase):
    def test_identity_ignores_the_folder_entirely(self):
        a = read_capture(os.path.join(FIX, "aeb1.jpg"))
        one = pairs.identity(a, "/somewhere/aeb1.jpg")
        two = pairs.identity(a, "/somewhere/else/entirely/aeb1.JPG")
        self.assertEqual(one, two)

    def test_the_extension_and_case_do_not_matter(self):
        self.assertEqual(pairs.base_name("/x/P1130088.RW2"), "p1130088")
        self.assertEqual(pairs.base_name("/y/p1130088.JPG"), "p1130088")

    def test_a_raw_finds_its_jpeg_by_name_camera_and_time(self):
        idx = pairs.build_index([os.path.join(FIX, "aeb1.jpg")])
        raw = os.path.join(FIX, "aeb1.jpg")     # stands in for the RAW
        m = pairs.find_partner(raw, read_capture(raw), idx)
        self.assertTrue(m.confident)
        self.assertIn("capture time", m.how)

    def test_a_raw_with_no_match_anywhere_says_so_plainly(self):
        idx = pairs.build_index([os.path.join(FIX, "burst1.jpg")])
        raw = os.path.join(FIX, "aeb1.jpg")
        m = pairs.find_partner(raw, read_capture(raw), idx)
        self.assertIsNone(m.jpeg)
        self.assertEqual(m.candidates, 0)
        self.assertIn("no JPEG anywhere", m.how)


class PathArithmetic(unittest.TestCase):
    def test_a_sibling_tree_is_not_inside_the_library(self):
        # comparing prefixes alone says it is, and that mistake scatters files
        self.assertFalse(paths.under("/n/Photos Raw/A7c", "/n/Photos"))
        self.assertTrue(paths.under("/n/Photos/A7c", "/n/Photos"))

    def test_a_folder_is_inside_itself(self):
        self.assertTrue(paths.under("/n/Photos", "/n/Photos"))

    def test_a_position_survives_being_moved_to_the_other_tree(self):
        self.assertEqual(
            paths.mirror("/n/Photos/GH4/Spain", "/n/Photos", "/n/Photos Raw"),
            os.path.join("/n/Photos Raw", "GH4", "Spain"))

    def test_a_doubled_destination_is_detected(self):
        self.assertEqual(
            paths.strip_mirrored_tail("N:\\Photos Raw\\GH4\\Spain", "GH4\\Spain"),
            "N:\\Photos Raw")

    def test_a_partial_name_is_not_a_tail(self):
        self.assertIsNone(
            paths.strip_mirrored_tail("N:\\Photos Raw\\GH4\\Spain 22", "GH4\\Spain 22_2"))

    def test_it_never_strips_the_tree_away_entirely(self):
        self.assertIsNone(paths.strip_mirrored_tail("N:\\A7c", "N:\\A7c"))

    def test_a_correct_destination_is_left_alone(self):
        self.assertIsNone(paths.strip_mirrored_tail("N:\\Photos Raw", "GH4\\Spain"))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class SayingWhichProblemItIs(unittest.TestCase):
    """Abu: "I don't get the difference between orphaned and stray, and it says
    many have no JPEG." A RAW whose photo sits in a folder this app does not
    walk into is not a lost file, and saying so is the whole fix."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="remirror-words-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.spain = os.path.join(self.lib, "2022", "Spain")
        self.italy = os.path.join(self.lib, "2022", "Italy")
        os.makedirs(self.spain)
        os.makedirs(self.italy)
        os.makedirs(os.path.join(self.raw, "2022", "Spain"))
        os.makedirs(os.path.join(self.raw, "2022", "Italy"))
        from core import settings as _s
        _s.save({"library": self.lib, "raw": self.raw})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def raw_at(self, folder, name):
        where = os.path.join(folder, name)
        with open(where, "wb") as fh:
            fh.write(b"raw")
        return where

    def jpeg_at(self, folder, name):
        os.makedirs(folder, exist_ok=True)
        where = os.path.join(folder, name)
        shutil.copy(os.path.join(FIX, "plain.jpg"), where)
        return where

    def run_plan(self, **opts):
        from app.tasks import remirror
        got = {"library": self.lib, "raw": self.raw, "orphans": "leave"}
        got.update(opts)
        return remirror.plan(got)

    def test_a_photo_in_culled_is_not_called_lost(self):
        self.raw_at(os.path.join(self.raw, "2022", "Spain"), "a.RW2")
        self.jpeg_at(os.path.join(self.spain, "_Culled"), "a.JPG")
        p = self.run_plan()
        said = " ".join(x[1] for x in p.skipped)
        self.assertIn("does not walk into", said)
        self.assertNotIn("no photo of that name", said)

    def test_a_raw_only_shot_says_so(self):
        self.raw_at(os.path.join(self.raw, "2022", "Spain"), "solo.RW2")
        p = self.run_plan()
        self.assertIn("RAW-only", " ".join(x[1] for x in p.skipped))

    def test_they_are_left_alone_by_default(self):
        self.raw_at(os.path.join(self.raw, "2022", "Spain"), "solo.RW2")
        self.assertEqual(self.run_plan().rows, [])

    def test_only_these_folders_narrows_what_is_judged(self):
        # one shoot needs re-mirroring, another has a RAW with no photo
        self.jpeg_at(self.italy, "moved.JPG")
        self.raw_at(os.path.join(self.raw, "2022", "Spain"), "moved.RW2")
        self.raw_at(os.path.join(self.raw, "2022", "Italy"), "solo.RW2")
        whole = self.run_plan()
        self.assertEqual(len(whole.skipped), 1)
        p = self.run_plan(only=os.path.join(self.raw, "2022", "Spain"))
        self.assertEqual(len(p.rows), 1)
        self.assertEqual(p.skipped, [])
        self.assertTrue(any("Only the folders you picked" in n for n in p.notes))

    def test_and_a_folder_of_the_library_picks_the_same_shoot(self):
        self.jpeg_at(self.italy, "moved.JPG")
        self.raw_at(os.path.join(self.raw, "2022", "Spain"), "moved.RW2")
        p = self.run_plan(only=self.italy)
        self.assertEqual(len(p.rows), 1)

    def test_the_words_are_explained_where_they_are_used(self):
        from app import registry as R
        task = R.get("remirror")
        words = " ".join([o.help for o in task.options] + task.summary.split())
        self.assertIn("STRAY", words + " " + " ".join(
            n for n in self.run_plan().notes))
