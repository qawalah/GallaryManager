"""What a run costs the NAS - and the two ways a number like that lies.

An app that reads a hundred thousand photographs every quarter of an hour on its
own is one you are entitled to know the cost of. The tempting version is a big
confident percentage, and the trouble with it is that it is not this app's
number: a NAS is running DSM's indexer, Drive, Photos and whatever else is in a
container, and the machine's load is all of them together.

So the two things worth testing are honesty, not arithmetic:

- what is reported is THIS process's own counters, and the machine's load is
  labelled as the machine's;
- a measure that could not be taken is absent rather than zero, because "it read
  nothing off the disk" is good news and "I could not tell" is not.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from core import load                      # noqa: E402
from core import runlog                    # noqa: E402
from core import settings as S             # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Measuring(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="load-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_reading_files_shows_up_as_reading_files(self):
        big = os.path.join(self.dir, "big")
        with open(big, "wb") as fh:
            fh.write(b"x" * 4_000_000)
        before = load.snapshot()
        with open(big, "rb") as fh:
            fh.read()
        cost = load.since(before)
        if "rchar" not in cost:
            self.skipTest("this machine does not expose /proc/self/io")
        self.assertGreaterEqual(cost["rchar"], 4_000_000)

    def test_time_is_measured_not_asked_for(self):
        before = load.snapshot()
        time.sleep(0.05)
        self.assertGreaterEqual(load.since(before)["seconds"], 0.04)

    def test_a_measure_that_cannot_be_taken_is_absent_not_zero(self):
        """"0 MB read" and "I could not tell" are different answers, and only
        one of them is good news."""
        cost = load.since({"at": 0.0}, {"at": 1.0})
        self.assertNotIn("read_bytes", cost)
        self.assertEqual(load.bytes_said(None), "not measured")

    def test_the_machine_figure_is_never_folded_into_this_apps(self):
        """The load average is the WHOLE NAS. Adding it to a run's own cost
        would be a number that looks precise and is wrong."""
        cost = load.since(load.snapshot())
        self.assertNotIn("load1", cost)
        self.assertNotIn("load5", cost)

    def test_it_says_where_the_time_went_not_only_how_long(self):
        """"4 min, 12s of that working" is the sentence that explains why a
        longer interval helps and a faster NAS does not."""
        said = load.describe({"seconds": 240.0, "cpu": 12.0,
                              "read_bytes": 4_000_000_000})
        self.assertIn("min", said)
        self.assertIn("working", said)
        self.assertIn("GB", said)

    def test_but_not_for_a_run_too_short_to_divide(self):
        """"0.3s, 0s of that working" tells you nothing and makes the line
        harder to read."""
        self.assertNotIn("working", load.describe({"seconds": 0.3, "cpu": 0.0}))

    def test_waiting_is_the_number_that_matters_on_a_nas(self):
        self.assertAlmostEqual(load.waiting_share({"seconds": 100, "cpu": 5}),
                               0.95, places=2)
        self.assertIsNone(load.waiting_share({"seconds": 0}))
        self.assertIsNone(load.waiting_share({"seconds": 10}))


class KeptWithTheRun(Measuring):
    def test_the_log_records_what_a_run_cost_and_who_started_it(self):
        class Got:
            done, failed, cancelled, stats, details = 3, 0, False, [], []
        entry = runlog.record("cull", {}, Got(), 1.5, by="automation",
                              cost={"seconds": 1.5, "cpu": 0.2,
                                    "read_bytes": 5_000})
        self.assertEqual(entry["by"], "automation")
        self.assertEqual(entry["cost"]["read_bytes"], 5_000)
        back = runlog.recent(limit=5)[0]
        self.assertEqual(back["by"], "automation")
        self.assertEqual(back["cost"]["cpu"], 0.2)

    def test_a_run_you_pressed_is_not_marked_as_automatic(self):
        """Which is the whole use of the field: the automatic ones are the half
        nobody was watching."""
        class Got:
            done, failed, cancelled, stats, details = 1, 0, False, [], []
        self.assertEqual(runlog.record("cull", {}, Got(), 1.0)["by"], "")

    def test_an_old_log_line_with_no_cost_is_still_readable(self):
        """The log outlives the code that writes it - a run recorded before any
        of this existed must not break the tab that lists it."""
        import json
        with open(runlog._path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"when": time.time(), "task": "cull", "done": 2,
                                 "failed": 0, "by": "automation"}) + "\n")
        p = R.get("autoruns").make_plan({})
        self.assertEqual(len(p.rows), 1)
        self.assertIn("not measured", " ".join(p.rows[0].cells))


class TheRunsTab(Measuring):
    def log(self, task="develop", by="automation", done=1, failed=0, cost=None):
        class Got:
            pass
        got = Got()
        got.done, got.failed, got.cancelled = done, failed, False
        got.stats, got.details = [], []
        return runlog.record(task, {}, got, 1.0, by=by,
                             cost=cost or {"seconds": 60.0, "cpu": 3.0,
                                           "read_bytes": 2_000_000,
                                           "rchar": 9_000_000})

    def test_it_shows_only_what_the_app_started_itself(self):
        self.log(by="automation")
        self.log(by="", task="cull")
        p = R.get("autoruns").make_plan({})
        self.assertEqual([r.cells[0] for r in p.rows], ["develop"])

    def test_the_quiet_passes_are_hidden_by_default(self):
        """A pass that found nothing changed is the normal, correct state and
        there are a great many of them - showing those by default buries the
        handful that did something."""
        self.log(done=0)
        self.log(done=4)
        self.assertEqual(len(R.get("autoruns").make_plan({}).rows), 1)
        self.assertEqual(len(R.get("autoruns").make_plan({"which": "all"}).rows), 2)

    def test_it_says_what_came_off_the_disk_and_what_came_from_memory(self):
        """The gap between them is why a second pass feels instant and the one
        after a reboot does not. Only shown where the kernel's own counters can
        be read at all - which in Abu's container they cannot."""
        self.log()
        stats = dict(R.get("autoruns").make_plan({}).stats)
        self.assertEqual(stats["Off the device itself"], "2.0 MB")
        self.assertEqual(stats["  the rest came from memory"], "7.0 MB")

    def test_and_the_figure_it_counts_itself_is_the_headline(self):
        """The one that is always there. A run that cannot say what it read is
        a run whose cost is unknown, which is what "not measured" meant on
        every line of Abu's table."""
        self.log(cost={"seconds": 60.0, "cpu": 3.0,
                       "own_files": 3000, "own_bytes": 400_000_000})
        stats = dict(R.get("autoruns").make_plan({}).stats)
        self.assertEqual(stats["FILES OPENED"], "3,000")
        self.assertEqual(stats["What that read"], "400 MB")

    def test_a_run_with_no_disk_figure_says_so_rather_than_showing_zero(self):
        self.log(cost={"seconds": 60.0})
        stats = dict(R.get("autoruns").make_plan({}).stats)
        self.assertEqual(stats["FILES OPENED"], "not measured")

    def test_and_names_the_machine_figure_as_the_machines(self):
        self.log()
        said = " ".join(f"{k} {v}" for k, v in
                        R.get("autoruns").make_plan({}).stats)
        if "The NAS right now" not in said:
            self.skipTest("no load average on this machine")
        self.assertIn("WHOLE machine", said)

    def test_it_only_ever_looks(self):
        self.assertFalse(R.get("autoruns").writes)


if __name__ == "__main__":
    unittest.main()
