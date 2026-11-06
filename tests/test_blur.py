"""Finding the blurry ones - measured, and measured where it matters.

The judgement worth testing is "anywhere, not on average": a portrait with one
eye in focus and a whole frame of deliberate softness is the best frame of the
shoot, and averaged over the picture it looks blurred.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:                                 # pragma: no cover
    Image = None

from app import registry as R                     # noqa: E402
import app.tasks                                  # noqa: E402,F401
from app.tasks import blur as B                   # noqa: E402
from core import settings as S                    # noqa: E402
from core import tags                             # noqa: E402


def sharp_picture(path, size=(800, 600)):
    im = Image.new("RGB", size, (128, 128, 128))
    d = ImageDraw.Draw(im)
    for x in range(0, size[0], 16):
        d.line([(x, 0), (x, size[1])], fill=(0, 0, 0) if x % 32 else (255, 255, 255), width=3)
    im.save(path, "JPEG", quality=92)


def blurred(path, size=(800, 600), radius=12):
    sharp_picture(path, size)
    Image.open(path).filter(ImageFilter.GaussianBlur(radius)).save(path, "JPEG")


def soft_but_one_sharp_corner(path, size=(800, 600)):
    """A portrait's shape: almost everything soft, one small region crisp."""
    blurred(path, size)
    im = Image.open(path)
    d = ImageDraw.Draw(im)
    for x in range(0, 180, 12):
        d.line([(x, 0), (x, 140)], fill=(0, 0, 0) if x % 24 else (255, 255, 255), width=2)
    im.save(path, "JPEG", quality=92)


@unittest.skipIf(Image is None, "Pillow is not installed")
class Measuring(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="blur-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_sharp_frame_scores_far_above_a_blurred_one(self):
        a, b = os.path.join(self.dir, "a.jpg"), os.path.join(self.dir, "b.jpg")
        sharp_picture(a)
        blurred(b)
        self.assertGreater(B.sharpness(a), 5 * B.sharpness(b))

    def test_one_sharp_region_is_enough_to_not_be_blurry(self):
        """The portrait case. Scored by its SHARPEST cell, it is sharp."""
        soft = os.path.join(self.dir, "soft.jpg")
        blurred(soft)
        portrait = os.path.join(self.dir, "portrait.jpg")
        soft_but_one_sharp_corner(portrait)
        self.assertGreater(B.sharpness(portrait), 5 * B.sharpness(soft))

    def test_a_file_that_is_not_a_picture_is_not_a_score(self):
        bad = os.path.join(self.dir, "x.jpg")
        with open(bad, "wb") as fh:
            fh.write(b"not a jpeg")
        self.assertIsNone(B.sharpness(bad))


@unittest.skipIf(Image is None, "Pillow is not installed")
class TheTab(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="blurtab-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        for n in range(5):
            sharp_picture(os.path.join(self.shoot, f"s{n}.jpg"))
        blurred(os.path.join(self.shoot, "shaky.jpg"))
        S.save({"library": self.lib})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_task(self, **over):
        t = R.get("blur")
        raw = {"folder": self.shoot, "do": "tag", "below": 0, "of_shoot": 35,
               "raw": "", "previews": ""}
        raw.update(over)
        return t, t.make_plan(raw)

    def test_the_soft_one_in_a_sharp_shoot_is_caught(self):
        _t, p = self.run_task()
        self.assertEqual([r.name for r in p.rows], ["shaky.jpg"])
        self.assertIn("of its shoot", p.rows[0].cells[2])

    def test_tagging_writes_a_tag_and_moves_nothing(self):
        t, p = self.run_task()
        t.apply(p)
        shaky = os.path.join(self.shoot, "shaky.jpg")
        self.assertTrue(os.path.isfile(shaky))
        self.assertIn("blurry", [x.lower() for x in tags.tags_of(shaky)])

    def test_and_a_frame_already_tagged_is_not_written_again(self):
        t, p = self.run_task()
        t.apply(p)
        _t, again = self.run_task()
        self.assertEqual(again.rows, [])

    def test_putting_aside_moves_it_into_culled_at_the_top_of_the_tree(self):
        t, p = self.run_task(do="aside")
        t.apply(p)
        self.assertFalse(os.path.exists(os.path.join(self.shoot, "shaky.jpg")))
        self.assertTrue(os.path.isfile(os.path.join(
            self.lib, "_Culled", "2022", "Spain", "shaky.jpg")))

    def test_the_second_look_measures_nothing_again(self):
        """Measuring is the slow part; a shoot that has not changed is free."""
        self.run_task()
        real = B.sharpness
        calls = []
        B.sharpness = lambda p: (calls.append(p), real(p))[1]
        try:
            self.run_task()
        finally:
            B.sharpness = real
        self.assertEqual(calls, [])

    def test_planning_alone_changes_nothing(self):
        self.run_task(do="aside")
        self.assertTrue(os.path.isfile(os.path.join(self.shoot, "shaky.jpg")))



class TheButtonSaysWhatHappens(TheTab):
    def test_putting_aside_counts_photographs_not_files(self):
        with open(os.path.join(self.shoot, "shaky.xmp"), "w") as fh:
            fh.write("<x:xmpmeta xmlns:x='adobe:ns:meta/'/>")
        t, p = self.run_task(do="aside")
        self.assertEqual(len(p.rows), 2, [r.name for r in p.rows])
        self.assertEqual(R.impact_of(t, p)["count"], 1)

    def test_tagging_says_tag_and_names_no_destination(self):
        raw = os.path.join(self.dir, "Photos Raw")
        os.makedirs(raw)
        t, p = self.run_task(raw=raw)
        got = R.impact_of(t, p)
        self.assertEqual(got["verb"], "Tag")
        self.assertEqual(got["count"], 1)
        self.assertEqual(got["into"], [])


if __name__ == "__main__":
    unittest.main()
