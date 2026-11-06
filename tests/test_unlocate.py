"""Taking a wrong location off - the undo for Geotag.

When the camera's clock was wrong every photograph in the folder was matched to
the wrong moment of the timeline, and so to the wrong place. A confidently wrong
pin is worse than none, because nothing on the map says it is a guess. What
matters here is that the location really goes - not just out of sight of the
programs that look for it - and that nothing else does.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R                  # noqa: E402
import app.tasks                               # noqa: E402,F401
from core import exifwrite as W                # noqa: E402
from core import jpegseg                       # noqa: E402
from core import settings as S                 # noqa: E402
from core import sidecar as sc                 # noqa: E402
from core.photo import read_gps                # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Tree(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="unlocate-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        self.rawshoot = os.path.join(self.raw, "2022", "Spain")
        os.makedirs(self.shoot)
        os.makedirs(self.rawshoot)
        S.save({"library": self.lib, "raw": self.raw})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def jpeg(self, name="a.JPG", where=None, pinned=True):
        path = os.path.join(where or self.shoot, name)
        shutil.copy(os.path.join(FIX, "plain.jpg"), path)
        if pinned:
            W.write_gps(path, 41.38, 2.17)
        return path

    def run_task(self, **over):
        t = R.get("unlocate")
        raw = {"folder": self.shoot, "with_raw": True, "with_previews": ""}
        raw.update(over)
        return t, t.make_plan(raw)


class InsideTheJpeg(Tree):
    def test_the_location_is_gone(self):
        p = self.jpeg()
        t, plan = self.run_task()
        self.assertEqual(len(plan.rows), 1)
        self.assertEqual(t.apply(plan).failed, 0)
        self.assertFalse(read_gps(p).has_gps)

    def test_and_not_merely_unhooked(self):
        """Unhooking would satisfy every photo program, and the wrong position
        would still be in the file for anything that goes looking. When the
        reason for removing it is that it is WRONG, that is not removed."""
        p = self.jpeg()
        with open(p, "rb") as fh:
            before = fh.read()
        at, length, _ = W._find_exif_segment(before)
        tiff = before[at + 10:at + length]
        from core import exif as E
        t = E.Tiff(tiff, 0)
        gps_dir = [t.u32(t.first_ifd() + 2 + e * 12 + 8)
                   for e in range(t.u16(t.first_ifd()))
                   if t.u16(t.first_ifd() + 2 + e * 12) == E.T_GPS_IFD][0]
        after = W.block_without_gps(tiff)
        n = t.u16(gps_dir)
        self.assertEqual(after[gps_dir:gps_dir + 2 + n * 12], bytes(2 + n * 12))

    def test_the_picture_itself_is_not_touched(self):
        p = self.jpeg()
        with open(p, "rb") as fh:
            was = fh.read()
        W.strip_gps(p)
        with open(p, "rb") as fh:
            now = fh.read()
        self.assertEqual(now[jpegseg.scan_start(now):], was[jpegseg.scan_start(was):])

    def test_nor_the_date_it_was_last_changed(self):
        p = self.jpeg()
        was = os.stat(p).st_mtime_ns
        W.strip_gps(p)
        self.assertEqual(os.stat(p).st_mtime_ns, was)

    def test_a_photo_with_no_location_is_not_rewritten_at_all(self):
        p = self.jpeg(pinned=False)
        with open(p, "rb") as fh:
            was = fh.read()
        self.assertFalse(W.strip_gps(p))
        with open(p, "rb") as fh:
            self.assertEqual(fh.read(), was)
        _t, plan = self.run_task()
        self.assertEqual(plan.rows, [])


class InTheSidecar(Tree):
    def test_the_location_goes_and_nothing_else_does(self):
        """The rating, the colour, the tags and whatever Lightroom keeps there
        stay exactly as they were."""
        neg = os.path.join(self.rawshoot, "a.RW2")
        shutil.copy(os.path.join(FIX, "plain.jpg"), neg)
        W.write_gps_sidecar(neg, 41.38, 2.17)
        sc.write(neg, **{"xmp:Rating": "4", "xmp:Label": "Green"})
        t, plan = self.run_task()
        t.apply(plan)
        left = sc.read(neg)
        self.assertFalse([k for k in left if k.startswith("exif:GPS")])
        self.assertEqual(left.get("xmp:Rating"), "4")
        self.assertEqual(left.get("xmp:Label"), "Green")

    def test_a_raw_is_never_opened_for_writing(self):
        neg = os.path.join(self.rawshoot, "a.RW2")
        shutil.copy(os.path.join(FIX, "plain.jpg"), neg)
        W.write_gps_sidecar(neg, 41.38, 2.17)
        with open(neg, "rb") as fh:
            was = fh.read()
        t, plan = self.run_task()
        t.apply(plan)
        with open(neg, "rb") as fh:
            self.assertEqual(fh.read(), was)


class WhichFolders(Tree):
    def test_the_same_shoot_in_the_raw_tree_and_no_other(self):
        """Never the whole RAW tree - which is what a tree box trimmed back to
        its top would have done."""
        here = os.path.join(self.rawshoot, "a.RW2")
        shutil.copy(os.path.join(FIX, "plain.jpg"), here)
        W.write_gps_sidecar(here, 41.38, 2.17)
        rome = os.path.join(self.raw, "2019", "Rome")
        os.makedirs(rome)
        there = os.path.join(rome, "b.RW2")
        shutil.copy(os.path.join(FIX, "plain.jpg"), there)
        W.write_gps_sidecar(there, 41.9, 12.5)
        _t, plan = self.run_task()
        self.assertEqual([r.name for r in plan.rows], ["a.RW2"])

    def test_and_none_of_it_when_asked(self):
        here = os.path.join(self.rawshoot, "a.RW2")
        shutil.copy(os.path.join(FIX, "plain.jpg"), here)
        W.write_gps_sidecar(here, 41.38, 2.17)
        _t, plan = self.run_task(with_raw="")
        self.assertEqual(plan.rows, [])

    def test_planning_alone_changes_nothing(self):
        p = self.jpeg()
        self.run_task()
        self.assertTrue(read_gps(p).has_gps)


if __name__ == "__main__":
    unittest.main()
