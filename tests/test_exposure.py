"""Over and under exposed, measured rather than guessed.

The risk in a feature like this is not that it misses one. It is that it is
confidently wrong about a photograph somebody made on purpose - a silhouette, a
high-key portrait, a night street - and then something acts on that. So it
writes nothing but a tag, it reports the numbers it judged by, and the tests
below are mostly about the awkward frames.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import exposure as E                # noqa: E402

try:
    from PIL import Image                     # noqa: E402
    HAVE_PIL = True
except Exception:                             # noqa: BLE001
    HAVE_PIL = False


def hist_of(values):
    """A histogram with the given share of pixels at each brightness."""
    hist = [0] * 256
    for level, n in values.items():
        hist[level] = n
    return hist


class TheJudgement(unittest.TestCase):
    def test_a_white_frame_is_over_exposed(self):
        got = E.verdict(hist_of({255: 1000}))
        self.assertEqual(got["verdict"], "over")
        self.assertEqual(got["high"], 100.0)

    def test_a_black_frame_is_under_exposed(self):
        got = E.verdict(hist_of({0: 1000}))
        self.assertEqual(got["verdict"], "under")
        self.assertEqual(got["low"], 100.0)

    def test_an_ordinary_frame_is_neither(self):
        got = E.verdict(hist_of({x: 10 for x in range(40, 200)}))
        self.assertEqual(got["verdict"], "ok")

    def test_a_backlit_frame_clips_at_both_ends_and_is_called_once(self):
        """A subject against a window: a lot of black and a lot of white. It has
        to come out as one thing, and the average is what decides which - a
        verdict of "both" is one nobody can act on."""
        got = E.verdict(hist_of({0: 300, 255: 150, 90: 550}))
        self.assertIn(got["verdict"], ("under", "over"))
        self.assertGreater(got["high"], 0)
        self.assertGreater(got["low"], 0)

    def test_a_night_frame_is_not_called_under_just_for_being_dark(self):
        """Half of a night street is legitimately black. The default threshold
        is high for exactly this reason, and a feature that flagged every night
        photograph would be one nobody runs twice."""
        got = E.verdict(hist_of({0: 300, 60: 300, 120: 400}))
        self.assertEqual(got["verdict"], "ok")

    def test_the_thresholds_are_what_decide_and_they_can_move(self):
        hist = hist_of({255: 30, 128: 970})
        self.assertEqual(E.verdict(hist, over_pct=5)["verdict"], "ok")
        self.assertEqual(E.verdict(hist, over_pct=2)["verdict"], "over")

    def test_it_always_says_what_it_judged_by(self):
        """A verdict you disagree with should be one you can argue with."""
        for hist in (hist_of({255: 1000}), hist_of({0: 1000}),
                     hist_of({128: 1000})):
            got = E.verdict(hist)
            said = E.describe(got)
            self.assertRegex(said, r"[0-9]")
            self.assertIn("%", said)


@unittest.skipUnless(HAVE_PIL, "reading a picture needs Pillow")
class OverRealFiles(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="exp-")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        self.shots = os.path.join(self.home, "shots")
        os.makedirs(self.shots)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def make(self, name, colour):
        path = os.path.join(self.shots, name)
        Image.new("RGB", (320, 240), colour).save(path)
        return path

    def test_it_reads_a_photograph_and_says_which_it_is(self):
        self.assertEqual(E.look_at(self.make("w.jpg", (252, 252, 252)))["verdict"],
                         "over")
        self.assertEqual(E.look_at(self.make("b.jpg", (2, 2, 2)))["verdict"],
                         "under")
        self.assertEqual(E.look_at(self.make("m.jpg", (128, 130, 125)))["verdict"],
                         "ok")

    def test_a_file_with_no_picture_in_it_says_so(self):
        path = os.path.join(self.shots, "broken.jpg")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("not a picture")
        with self.assertRaises(E.Unreadable):
            E.look_at(path)

    def test_the_tab_lists_them_and_writes_only_a_tag(self):
        from app import registry as R
        import app.tasks                                   # noqa: F401
        from core import facts, settings as S
        self.make("w.jpg", (252, 252, 252))
        self.make("b.jpg", (2, 2, 2))
        self.make("m.jpg", (128, 130, 125))
        S.save({"library": self.shots})
        task = R.get("exposure")
        plan = task.make_plan({"folder": self.shots})
        self.assertEqual(len(plan.rows), 2)
        # nothing moved, nothing deleted - every photograph is still there, and
        # the only new files are the sidecars the tags are written into
        task.apply(plan)
        left = sorted(os.listdir(self.shots))
        self.assertEqual([f for f in left if f.endswith(".jpg")],
                         ["b.jpg", "m.jpg", "w.jpg"])
        self.assertTrue(all(f.endswith((".jpg", ".xmp")) for f in left), left)
        reader = facts.reader()
        self.assertIn("overexposed", reader.tags(os.path.join(self.shots, "w.jpg")))
        self.assertIn("underexposed", reader.tags(os.path.join(self.shots, "b.jpg")))
        self.assertEqual(reader.tags(os.path.join(self.shots, "m.jpg")), [])

    def test_with_no_tag_set_it_only_reports(self):
        from app import registry as R
        import app.tasks                                   # noqa: F401
        from core import settings as S
        self.make("w.jpg", (252, 252, 252))
        S.save({"library": self.shots})
        plan = R.get("exposure").make_plan(
            {"folder": self.shots, "write_tags": False})
        self.assertFalse(plan.writes)
        self.assertTrue(any("a report" in n for n in plan.notes), plan.notes)

    def test_and_what_it_tags_can_then_be_searched_for(self):
        """The whole reason it writes a tag: "show me the blown ones" has to be
        answerable afterwards, by the same Search as everything else."""
        from app import registry as R
        import app.tasks                                   # noqa: F401
        from core import facts, find, settings as S
        self.make("w.jpg", (252, 252, 252))
        self.make("m.jpg", (128, 130, 125))
        S.save({"library": self.shots})
        task = R.get("exposure")
        task.apply(task.make_plan({"folder": self.shots}))
        reader = facts.reader()
        hits = [p for p in sorted(os.listdir(self.shots))
                if find.matches(find.about(os.path.join(self.shots, p), reader),
                                find.Ask(tags=("overexposed",)))[0]]
        self.assertEqual(hits, ["w.jpg"])


if __name__ == "__main__":
    unittest.main()
