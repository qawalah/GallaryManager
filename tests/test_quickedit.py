"""Delete from the viewer: every copy into the Recycle Bin, and said when not.

A copy on a share with no Recycle Bin used to be skipped in silence, and a
failure part-way lost the record of what had already gone into the bin.
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import moves as M                # noqa: E402
from core import quickedit as QE           # noqa: E402
from core import settings as S             # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Deleting(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="quickedit-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.share = os.path.join(self.dir, "share")
        self.lib = os.path.join(self.share, "Photos")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        os.makedirs(os.path.join(self.share, "#recycle"))
        self.photo = os.path.join(self.shoot, "a.JPG")
        shutil.copy(os.path.join(FIX, "rated.jpg"), self.photo)
        with open(os.path.join(self.shoot, "a.xmp"), "w") as fh:
            fh.write("<x/>")
        S.save({"library": self.lib})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_it_goes_to_the_bin_with_its_sidecar(self):
        out = QE.delete(self.photo)
        self.assertEqual(len(out["moves"]), 2)
        self.assertEqual(out["kept"], [])
        self.assertFalse(os.path.exists(self.photo))

    def test_a_copy_on_a_share_without_a_bin_is_said_not_skipped(self):
        raw = os.path.join(self.dir, "other", "Raw")
        os.makedirs(os.path.join(raw, "2022", "Spain"))
        neg = os.path.join(raw, "2022", "Spain", "a.RW2")
        shutil.copy(os.path.join(FIX, "rated.jpg"), neg)
        S.save({"raw": raw})
        with mock.patch.object(QE, "copies", return_value=[self.photo, neg]):
            out = QE.delete(self.photo)
        self.assertEqual(out["kept"], [neg])
        self.assertTrue(os.path.isfile(neg))

    def test_a_failure_part_way_hands_back_what_had_moved(self):
        real, calls = M.shift, []

        def flaky(book, src, dst, **kw):
            calls.append(src)
            if len(calls) == 2:
                raise OSError(5, "Input/output error")
            return real(book, src, dst, **kw)

        with mock.patch.object(M, "shift", side_effect=flaky):
            with self.assertRaises(QE.Partly) as got:
                QE.delete(self.photo)
        self.assertEqual(len(got.exception.moves), 1)
        self.assertEqual(QE.undo(got.exception.moves)["restored"], 1)
        self.assertTrue(os.path.isfile(self.photo))


if __name__ == "__main__":
    unittest.main()
