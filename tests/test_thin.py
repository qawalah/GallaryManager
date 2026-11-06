"""Keeping one frame of a bracket, and the two ways that could cost you a photo.

Which frame survives has to be a stated RULE, not a preference the code happens
to have: two runs must agree, and you should be able to predict the answer before
pressing anything. The rule is Abu's - the frame you rated, else the metered one.

And nothing is deleted, ever. A bracket thinned by mistake is a mistake; a
bracket deleted by mistake is a photograph you no longer have.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from core import settings as S             # noqa: E402
from core import walk                      # noqa: E402
from core.exifwrite import set_rating      # noqa: E402
from core.paths import CULLED              # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Thinning(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="thin-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.prev = os.path.join(self.dir, "Photos Previews")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        os.makedirs(os.path.join(self.raw, "2022", "Spain"))
        os.makedirs(os.path.join(self.prev, "2022", "Spain"))
        for n in ("aeb1", "aeb2", "aeb3"):
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(self.shoot, n + ".JPG"))
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(self.raw, "2022", "Spain", n + ".RW2"))
        # A loose photograph, which is not a bracket and must never be touched.
        # In its own folder: dropped in beside the set it lands INSIDE the set's
        # few seconds and breaks the ladder, which is the bracket finder working
        # correctly and not what this test is about.
        self.loose = os.path.join(self.lib, "2022", "Loose")
        os.makedirs(self.loose)
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(self.loose, "plain.JPG"))
        # the preview of the metered frame, which is what previews would have made
        shutil.copy(os.path.join(FIX, "aeb2.jpg"),
                    os.path.join(self.prev, "2022", "Spain", "aeb2.jpg"))
        S.save({"library": self.lib, "raw": self.raw, "previews": self.prev})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def at(self, *bits):
        return os.path.join(self.shoot, *bits)

    def plan(self, **over):
        t = R.get("thin")
        p = t.make_plan({"folder": self.lib, **over})
        self.assertFalse(p.blocked, p.blocked)
        return t, p

    def moving(self, p):
        return {os.path.basename(r.source) for r in p.rows}

    def test_the_metered_frame_is_kept_when_nothing_is_rated(self):
        _t, p = self.plan()
        self.assertEqual(self.moving(p), {"aeb1.JPG", "aeb1.RW2",
                                          "aeb3.JPG", "aeb3.RW2"})
        self.assertIn("aeb2.JPG", p.rows[0].detail)

    def test_the_frame_you_rated_is_kept_instead(self):
        """Starring a frame is the clearest possible statement of which exposure
        you meant to keep."""
        set_rating(self.at("aeb3.JPG"), 4)
        _t, p = self.plan()
        self.assertEqual(self.moving(p), {"aeb1.JPG", "aeb1.RW2",
                                          "aeb2.JPG", "aeb2.RW2",
                                          "aeb2.jpg"})     # and aeb2's preview
        self.assertIn("you rated it 4 star", p.rows[0].detail)

    def test_the_highest_rated_frame_when_two_are_rated(self):
        set_rating(self.at("aeb1.JPG"), 2)
        set_rating(self.at("aeb3.JPG"), 5)
        _t, p = self.plan()
        self.assertNotIn("aeb3.JPG", self.moving(p))

    def test_a_loose_photograph_is_never_touched(self):
        _t, p = self.plan()
        self.assertNotIn("plain.JPG", self.moving(p))

    def test_nothing_is_deleted_it_goes_to_culled(self):
        t, p = self.plan()
        self.assertEqual(t.apply(p).failed, 0)
        for name in ("aeb1", "aeb3"):
            self.assertTrue(os.path.isfile(
                os.path.join(self.lib, CULLED, "2022", "Spain", name + ".JPG")))
            self.assertTrue(os.path.isfile(
                os.path.join(self.raw, CULLED, "2022", "Spain", name + ".RW2")))
        self.assertTrue(os.path.isfile(self.at("aeb2.JPG")))       # the keeper
        # what a walk sees afterwards: the keeper and the loose photograph. The
        # spares are still on the disk, in _Culled, which nothing walks.
        self.assertEqual(sorted(os.path.basename(f)
                                for f in walk.walk(self.lib).files),
                         ["aeb2.JPG", "plain.JPG"])

    def test_the_preview_of_a_spare_frame_goes_with_it(self):
        """A preview left behind shows a photograph that folder no longer has -
        and its extension is .jpg where the original was .JPG, which is exactly
        how this was being missed on a case-sensitive disk."""
        spare = os.path.join(self.prev, "2022", "Spain", "aeb3.jpg")
        shutil.copy(os.path.join(FIX, "aeb3.jpg"), spare)
        _t, p = self.plan()
        self.assertIn(spare, {r.source for r in p.rows})

    def test_a_sidecar_travels_with_its_frame(self):
        side = self.at("aeb1.xmp")
        with open(side, "w", encoding="utf-8") as fh:
            fh.write("<x/>")
        _t, p = self.plan()
        self.assertIn(side, {r.source for r in p.rows})

    def test_a_probable_set_is_left_alone_unless_you_ask(self):
        """Frames seconds apart with no bias recorded are what hand-bracketing
        looks like, and also what three deliberate exposures look like.

        The set is marked probable by hand here. No fixture can produce one - a
        burst shares its shutter speed and the bracket fixtures record a bias -
        and the rule under test belongs to this task, not to the finder, which
        has its own tests for deciding which is which."""
        import app.tasks.thin as T
        real = T.sets_for

        def probable(files, opts, plan=None, **rest):
            found = real(files, opts, plan, **rest)
            for one in found.sets:
                one.confidence = "probable"
            return found

        T.sets_for = probable
        try:
            _t, p = self.plan()
            self.assertEqual(self.moving(p), set())
            self.assertTrue(any("PROBABLE" in why for _n, why in p.skipped))
            _t2, p2 = self.plan(probable=True)
            self.assertIn("aeb1.JPG", self.moving(p2))
        finally:
            T.sets_for = real

    def test_the_box_finds_probable_sets_even_with_setup_off(self):
        """"Include probable sets" used to do nothing unless Setup > Include
        hand-bracketed was on as well, because only Setup reached the finder
        (audit TK14). The box now asks the finder itself; with the box off,
        Setup still decides."""
        import app.grouping as G
        real = G.B.find
        asked = []

        def find(paths, **kw):
            asked.append(kw.get("include_probable"))
            return real(paths, **kw)

        S.save({"bracket_probable": False})
        G.B.find = find
        try:
            self.plan(probable=True)
            self.plan(probable=False)
            S.save({"bracket_probable": True})
            self.plan(probable=False)
        finally:
            G.B.find = real
        self.assertEqual(asked, [True, False, True])

    def test_the_row_says_which_frame_survives_and_why(self):
        set_rating(self.at("aeb3.JPG"), 4)
        _t, p = self.plan()
        cells = p.rows[0].cells
        self.assertIn("aeb3.JPG", cells)
        self.assertTrue(any("rated" in str(c) for c in cells), cells)

    def test_it_says_so_when_the_negatives_would_be_left_behind(self):
        _t, p = self.plan(raw="", mirror=False)
        self.assertTrue(any("RAW files of the spare frames" in n for n in p.notes))



class TheButtonCountsFrames(Thinning):
    def test_a_spare_frame_and_its_raw_are_one_frame(self):
        """Each spare frame brings its RAW, so rows are files and the button
        said twice the frames it was about to set aside."""
        t, p = self.plan()
        self.assertGreater(len(p.rows), 2)
        self.assertEqual(R.impact_of(t, p)["count"], 2)


if __name__ == "__main__":
    unittest.main()
