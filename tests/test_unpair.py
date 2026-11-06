"""Separate RAWs: a move done as copy, check, remove - and written down.

The copy-check-remove is deliberate (a move across two shares that fails half
way leaves nothing on either side), and it was also why the run reached History
with no moves: nothing went through `core.moves`, so Put it back had nothing to
put back. Each finished move is now recorded the moment the original goes.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from core import moves as M                # noqa: E402
from core import settings as S             # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Unpair(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="unpair-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(self.shoot, "a.JPG"))
        with open(os.path.join(self.shoot, "a.RW2"), "wb") as fh:
            fh.write(b"raw" * 100)
        S.save({"library": self.lib, "raw": self.raw})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_it(self, **over):
        t = R.get("unpair")
        p = t.make_plan({"folder": self.lib, "raw": self.raw, **over})
        self.assertFalse(p.blocked, p.blocked)
        return t.apply(p)

    def test_the_move_is_recorded_and_can_be_put_back(self):
        result = self.run_it()
        moved = os.path.join(self.raw, "2022", "Spain", "a.RW2")
        self.assertTrue(os.path.isfile(moved))
        self.assertEqual(result.moves,
                         [[os.path.join(self.shoot, "a.RW2"), moved]])
        M.put_back(result.moves)
        self.assertTrue(os.path.isfile(os.path.join(self.shoot, "a.RW2")))
        self.assertFalse(os.path.exists(moved))

    def test_a_copy_is_not_recorded_as_a_move(self):
        result = self.run_it(copy=True)
        self.assertEqual(result.moves, [])
        self.assertTrue(os.path.isfile(os.path.join(self.shoot, "a.RW2")))


if __name__ == "__main__":
    unittest.main()
