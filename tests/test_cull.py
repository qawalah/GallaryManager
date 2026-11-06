"""Cull's confirmation counts photographs, as its unit says.

A culled photograph is several files - the JPEG, its sidecar, its preview and
its RAW - and the button counted those, so "Set aside 12 photographs" was the
sentence about three.
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
from core.exifwrite import set_rating      # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class TheButtonCountsPhotographs(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cull-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.prev = os.path.join(self.dir, "Photos Previews")
        where = os.path.join("2022", "Spain")
        for root in (self.lib, self.raw, self.prev):
            os.makedirs(os.path.join(root, where))
        for name in ("plain", "aeb1"):
            jpeg = os.path.join(self.lib, where, name + ".JPG")
            shutil.copy(os.path.join(FIX, name + ".jpg"), jpeg)
            set_rating(jpeg, 1)
            shutil.copy(os.path.join(FIX, name + ".jpg"),
                        os.path.join(self.raw, where, name + ".RW2"))
            shutil.copy(os.path.join(FIX, name + ".jpg"),
                        os.path.join(self.prev, where, name + ".jpg"))
        S.save({"library": self.lib, "raw": self.raw, "previews": self.prev})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_two_photographs_and_their_files_are_two(self):
        t = R.get("cull")
        p = t.make_plan({"folder": self.lib, "jpeg_at_or_below": 1,
                         "raw_at_or_below": 1})
        self.assertFalse(p.blocked, p.blocked)
        self.assertEqual(len(p.rows), 6, [r.name for r in p.rows])
        self.assertEqual(R.impact_of(t, p)["count"], 2)


if __name__ == "__main__":
    unittest.main()
