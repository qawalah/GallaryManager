"""How much space this app has given back - kept, because it cannot be measured.

Once a pile is emptied, nothing on the disk says those files were ever there.
So the record is written at the moment it happens, by the one place every run
passes through, and "freed" and "put aside" are never added together - one is
space you have, the other is space you will have.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.registry import Result                  # noqa: E402
from core import reclaimed as RC                 # noqa: E402
from core import runlog                          # noqa: E402


class Kept(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="reclaimed-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = self.dir

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_freed_and_put_aside_are_separate_claims(self):
        RC.add("cleanup", 1000, RC.FREED)
        RC.add("cull", 500, RC.ASIDE)
        got = RC.summary()
        self.assertEqual((got["freed"], got["aside"]), (1000, 500))

    def test_this_year_and_ever(self):
        RC.add("cleanup", 1000, RC.FREED)
        next_year = time.time() + 400 * 86400
        got = RC.summary(now=next_year)
        self.assertEqual(got["freed"], 1000)
        self.assertEqual(got["freed_year"], 0)

    def test_every_run_is_recorded_in_one_place(self):
        """Not by each task: the run log writes it, so no task can forget."""
        r = Result(done=3)
        r.reclaimed, r.reclaim_kind = 2048, "aside"
        runlog.record("cull", {}, r)
        self.assertEqual(RC.summary()["aside"], 2048)

    def test_and_a_run_that_gave_nothing_back_adds_nothing(self):
        runlog.record("cull", {}, Result(done=0))
        self.assertEqual(RC.lines(), [])

    def test_it_outlives_the_run_log(self):
        """The run log keeps a few hundred runs. This keeps the total."""
        RC.add("cleanup", 10, RC.FREED)
        for _ in range(3):
            runlog.record("library", {}, Result())
        self.assertEqual(RC.summary()["freed"], 10)


if __name__ == "__main__":
    unittest.main()
