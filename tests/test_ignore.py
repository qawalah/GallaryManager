"""Folders that are not your photos, and must not be counted or touched.

PhotoPrism, Immich and Synology all keep working files *inside* photo folders -
@eaDir thumbnails, sidecar databases, an `originals` cache. Two things go wrong
if the app walks into them:

- Every number is wrong. A folder of 40 photos reports 400 because each one has
  five thumbnails, and "0 of 400 geotagged" is not a state you can act on.
- A task can damage the other app. Re-mirror moves things it decides are stray;
  cull puts things aside. Neither should ever have an opinion about PhotoPrism's
  cache.

So the skip list is a setting, not a constant - a new tool appears and you add
its folder name without waiting for a release - and the built-in names are added
to yours rather than replaced by them, because clearing the box should not
silently start scanning @eaDir again.

Names, not paths, on purpose: one entry covers every shoot in the library.
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
from core import survey, walk              # noqa: E402
from core.paths import skip_folder         # noqa: E402


class Fresh(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ignore-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        os.makedirs(os.path.join(self.lib, "2022"))

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def make(self, *parts, name="a.jpg"):
        folder = os.path.join(self.lib, *parts)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name), "wb") as fh:
            fh.write(b"\xff\xd8\xff\xd9")
        return folder


class TheBuiltInNames(Fresh):
    def test_synologys_index_folders_are_skipped_without_being_configured(self):
        self.make("2022", "@eaDir")
        self.assertTrue(skip_folder("@eaDir"))
        # the real ones on a Synology are @eaDir with a suffix
        self.assertTrue(skip_folder("@eaDir_something"))

    def test_our_own_folders_are_still_skipped(self):
        self.assertTrue(skip_folder("_Culled"))
        self.assertTrue(skip_folder("_NoLocation"))

    def test_an_ordinary_folder_is_not(self):
        self.assertFalse(skip_folder("2022"))
        self.assertFalse(skip_folder("Barcelona 2024"))


class TheOnesYouAdd(Fresh):
    def test_a_name_you_add_is_skipped(self):
        self.assertFalse(skip_folder("lightroom cache"))
        S.save({"ignore": "lightroom cache"})
        self.assertTrue(skip_folder("lightroom cache"))
        self.assertTrue(skip_folder("  Lightroom Cache  "))   # trimmed, case-blind

    def test_clearing_the_box_does_not_re_enable_the_built_in_ones(self):
        """The trap: yours REPLACING the defaults means one edit quietly starts
        counting thumbnails again, and nothing says so."""
        S.save({"ignore": ""})
        self.assertTrue(skip_folder("@eaDir"))
        self.assertTrue(skip_folder("#recycle"))

    def test_setup_owns_the_setting_so_the_form_can_edit_it(self):
        t = R.get("setup")
        names = [o.name for o in t.options]
        self.assertIn("ignore", names)
        opt = next(o for o in t.options if o.name == "ignore")
        self.assertEqual(opt.setting, "ignore")
        p = t.make_plan({"library": self.lib, "ignore": "phototool"})
        self.assertFalse(p.blocked, p.blocked)
        self.assertEqual(t.apply(p).failed, 0)
        self.assertTrue(skip_folder("phototool"))


class WhatActuallyWalks(Fresh):
    def test_the_walk_does_not_go_into_them(self):
        self.make("2022")
        self.make("2022", "@eaDir", name="thumb.jpg")
        S.save({"ignore": "photoprism"})
        self.make("2022", "photoprism", name="cache.jpg")
        got = walk.walk(self.lib)
        self.assertEqual([os.path.basename(f) for f in got.files], ["a.jpg"])

    def test_the_survey_does_not_count_them_as_folders_or_photos(self):
        self.make("2022")
        self.make("2022", "@eaDir", name="thumb.jpg")
        S.save({"ignore": "photoprism"})
        self.make("2022", "photoprism", name="cache.jpg")
        got = survey.survey(self.lib)
        seen = {os.path.basename(p) for p in got.folders}
        self.assertNotIn("@eaDir", seen)
        self.assertNotIn("photoprism", seen)
        self.assertEqual(got.folders[os.path.join(self.lib, "2022")].photos, 1)

    def test_our_own_folders_can_still_be_looked_into_on_purpose(self):
        """Re-mirror and un-cull need to see inside _Culled. Skipping is a
        default, not a wall - but only for the folders WE made."""
        self.make("_Culled", "2022", name="put-aside.jpg")
        self.assertEqual(walk.walk(self.lib).files, [])
        got = walk.walk(self.lib, include_ours=True)
        self.assertEqual([os.path.basename(f) for f in got.files], ["put-aside.jpg"])

    def test_include_ours_does_not_also_open_other_apps_folders(self):
        """The two are separate ideas. Asking to look inside _Culled must not
        quietly also mean walking into PhotoPrism's cache."""
        S.save({"ignore": "photoprism"})
        self.make("photoprism", name="cache.jpg")
        got = walk.walk(self.lib, include_ours=True)
        self.assertEqual(got.files, [])


if __name__ == "__main__":
    unittest.main()
