"""Telling a bracket from a burst, which is the whole difficulty.

Every test here is really the same question asked from a different angle: does
the code group frames on the exposure bias and nothing else? Group on "taken
seconds apart with the same settings" and a burst of a bird taking off becomes a
bracket, one frame of it gets a preview, and the other nine are culled together.
"""

import datetime as dt
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R
from core import tags, tagwrite                 # noqa: E402
import app.tasks                              # noqa: E402,F401
from core import brackets as B                # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
T0 = dt.datetime(2022, 7, 14, 18, 3, 22)


def frame(name, seconds, ev=None, mode=None, exposure=1 / 250, fnum=5.6, iso=200,
          focal=25.0, model="DMC-GH4", folder="/lib"):
    return B.Frame(path=f"{folder}/{name}", name=name, folder=folder,
                   taken=T0 + dt.timedelta(seconds=seconds), ev=ev, exposure_mode=mode,
                   exposure=exposure, fnumber=fnum, iso=iso, focal_length=focal,
                   model=model)


class TheLadderTest(unittest.TestCase):
    def test_the_ordinary_three_shot_bracket(self):
        self.assertTrue(B.is_ladder([-1, 0, 1]))

    def test_wider_and_longer_ladders(self):
        self.assertTrue(B.is_ladder([-2, 0, 2]))
        self.assertTrue(B.is_ladder([-3, -1.5, 0, 1.5, 3]))

    def test_thirds_of_a_stop_as_the_camera_rounds_them(self):
        self.assertTrue(B.is_ladder([-0.667, 0.0, 0.667]))
        self.assertTrue(B.is_ladder([-0.33, 0.0, 0.33]))

    def test_a_burst_is_not_a_ladder(self):
        self.assertFalse(B.is_ladder([0, 0, 0]))

    def test_a_ladder_not_centred_on_zero_is_refused(self):
        """0 +1 +2 is three photos getting brighter, not a bracket of one scene."""
        self.assertFalse(B.is_ladder([0, 1, 2]))

    def test_an_uneven_ladder_is_refused(self):
        self.assertFalse(B.is_ladder([-2, 0, 1]))

    def test_two_frames_are_never_enough(self):
        self.assertFalse(B.is_ladder([-1, 1]))


class SplittingARun(unittest.TestCase):
    def test_two_brackets_back_to_back_are_cut_where_a_bias_repeats(self):
        run = [frame(f"a{i}", i, ev=ev) for i, ev in enumerate([-1, 0, 1, -1, 0, 1])]
        sets = B.split_run(run)
        self.assertEqual([len(s) for s in sets], [3, 3])

    def test_a_burst_falls_apart_into_single_frames(self):
        run = [frame(f"b{i}", i, ev=0) for i in range(10)]
        self.assertEqual([len(s) for s in B.split_run(run)], [1] * 10)

    def test_one_bracket_alone_still_comes_back_as_one_set(self):
        """The single-set case is the one that broke in the Windows version."""
        run = [frame(f"c{i}", i, ev=ev) for i, ev in enumerate([-1, 0, 1])]
        sets = B.split_run(run)
        self.assertEqual(len(sets), 1)
        self.assertEqual(len(sets[0]), 3)


class WhichFrameStandsForTheSet(unittest.TestCase):
    def test_the_metered_frame_is_the_one_kept(self):
        members = [frame("a", 0, ev=-1), frame("b", 1, ev=0), frame("c", 2, ev=1)]
        self.assertEqual(B.representative(members).name, "b")

    def test_with_no_bias_recorded_the_middle_frame_stands_in(self):
        members = [frame("a", 0), frame("b", 1), frame("c", 2)]
        self.assertEqual(B.representative(members).name, "b")

    def test_an_uneven_ladder_still_picks_the_one_nearest_metered(self):
        members = [frame("a", 0, ev=-2), frame("b", 1, ev=-0.3), frame("c", 2, ev=2)]
        self.assertEqual(B.representative(members).name, "b")


class CuttingIntoRuns(unittest.TestCase):
    def test_a_long_pause_starts_a_new_run(self):
        frames = [frame("a", 0, ev=-1), frame("b", 1, ev=0), frame("c", 60, ev=1)]
        self.assertEqual([len(r) for r in B.runs_in(frames)], [2, 1])

    def test_changing_the_aperture_starts_a_new_run(self):
        frames = [frame("a", 0, ev=-1), frame("b", 1, ev=0, fnum=2.8)]
        self.assertEqual([len(r) for r in B.runs_in(frames)], [1, 1])

    def test_rounding_in_the_aperture_does_not(self):
        """f/5.6 written as 5.66 is one setting, and must not split a bracket."""
        frames = [frame("a", 0, ev=-1), frame("b", 1, ev=0, fnum=5.66)]
        self.assertEqual([len(r) for r in B.runs_in(frames)], [2])

    def test_a_second_camera_starts_a_new_run(self):
        frames = [frame("a", 0, ev=-1), frame("b", 1, ev=0, model="ILCE-7C")]
        self.assertEqual([len(r) for r in B.runs_in(frames)], [1, 1])


class RealFilesOnDisk(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="brackets-")
        for n in ("aeb1", "aeb2", "aeb3", "burst1", "burst2", "burst3"):
            shutil.copy(os.path.join(FIX, f"{n}.jpg"), os.path.join(self.dir, f"{n}.JPG"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def found(self, **over):
        import glob
        return B.find(sorted(glob.glob(os.path.join(self.dir, "*.JPG"))), **over)

    def test_the_bracket_is_found_and_the_burst_is_not(self):
        f = self.found()
        self.assertEqual(len(f.sets), 1)
        self.assertEqual(f.certain, 1)
        self.assertEqual(f.sets[0].size, 3)
        self.assertTrue(all("aeb" in m.name for m in f.sets[0].members))

    def test_the_metered_frame_carries_the_set(self):
        self.assertEqual(self.found().sets[0].representative.name, "aeb2.JPG")

    def test_every_member_can_be_looked_up_by_path(self):
        f = self.found()
        for m in f.sets[0].members:
            self.assertIs(f.set_of(m.path), f.sets[0])

    def test_a_burst_frame_belongs_to_no_set(self):
        f = self.found()
        self.assertIsNone(f.set_of(os.path.join(self.dir, "burst1.JPG")))

    def test_the_reason_is_always_stated(self):
        for s in self.found().sets:
            self.assertTrue(s.why)


class TheTaskItself(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="brackets-task-")
        for n in ("aeb1", "aeb2", "aeb3", "burst1", "burst2"):
            shutil.copy(os.path.join(FIX, f"{n}.jpg"), os.path.join(self.dir, f"{n}.JPG"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_with_no_tag_it_reports_one_set_and_writes_nothing(self):
        """The plan itself says so - `writes` is per-run here, not per-task, since
        typing a word into the tag box is what turns a report into a change."""
        t = R.get("brackets")
        before = sorted(os.listdir(self.dir))
        p = t.make_plan({"folder": self.dir, "tag": ""})
        self.assertFalse(p.writes)
        self.assertEqual(len(p.rows), 1)
        self.assertIn("aeb", p.rows[0].name)
        t.apply(p)
        self.assertEqual(sorted(os.listdir(self.dir)), before)

    def test_with_a_tag_every_frame_of_the_set_is_marked(self):
        t = R.get("brackets")
        p = t.make_plan({"folder": self.dir, "tag": "bracket", "raw": ""})
        self.assertTrue(p.writes)
        self.assertEqual(t.apply(p).failed, 0)
        for n in ("aeb1", "aeb2", "aeb3"):
            self.assertEqual(tags.tags_of(os.path.join(self.dir, f"{n}.JPG")),
                             ["bracket"], n)
        # a burst is not a bracket, and must not be marked as one
        for n in ("burst1", "burst2"):
            self.assertEqual(tags.tags_of(os.path.join(self.dir, f"{n}.JPG")), [], n)

    def test_the_word_is_added_to_what_is_already_there(self):
        """Replacing the keyword list would drop whatever somebody else put on
        the photograph, and they would not find out until they went looking."""
        first = os.path.join(self.dir, "aeb1.JPG")
        tagwrite.add(first, ["Italy"])
        t = R.get("brackets")
        t.apply(t.make_plan({"folder": self.dir, "tag": "bracket"}))
        self.assertEqual(tags.tags_of(first), ["Italy", "bracket"])

    def test_it_refuses_a_folder_that_is_not_there(self):
        p = R.get("brackets").make_plan({"folder": "/no/such/place"})
        self.assertTrue(p.blocked)
        self.assertEqual(p.rows, [])


if __name__ == "__main__":
    unittest.main()
