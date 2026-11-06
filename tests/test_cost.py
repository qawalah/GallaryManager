"""What the run cost the disk, and the failures said once rather than 28 times.

Two complaints from the same screenshot. The runs table said

    develop   194 done   22.9s   Read: not measured

and the number he actually cares about - what this is doing to the hard disk -
was the missing one. `/proc/self/io` is the kernel's own accounting and his
container is not allowed to read it, so every run reported nothing at all.

The other was `ratings  103 done, 28 failed`, twenty-eight lines naming twenty-
eight photographs and nowhere saying WHY. Twenty-eight instances of one fixable
problem read as twenty-eight separate mysteries.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R                 # noqa: E402
import app.tasks                              # noqa: E402,F401
from app.registry import Result, _gist        # noqa: E402
from core import jpegseg, load, meter         # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Counting(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cost-")
        self.photo = os.path.join(self.dir, "a.JPG")
        shutil.copy(os.path.join(FIX, "rated.jpg"), self.photo)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_reading_a_photographs_header_is_counted(self):
        before = meter.snapshot()
        jpegseg.read_header(self.photo)
        got = meter.since(before)
        self.assertEqual(got["own_files"], 1)
        self.assertEqual(got["own_bytes"], os.path.getsize(self.photo))

    def test_a_file_that_cannot_be_opened_counts_as_nothing(self):
        before = meter.snapshot()
        jpegseg.read_header(os.path.join(self.dir, "not there.JPG"))
        self.assertEqual(meter.since(before)["own_files"], 0)

    def test_reading_a_sidecar_is_counted_too(self):
        """A rated RAW is read entirely through its sidecar, so a meter that
        only watched photographs would report a RAW tree as costing nothing."""
        from core import sidecar
        side = os.path.splitext(self.photo)[0] + ".xmp"
        with open(side, "w", encoding="utf-8") as fh:
            fh.write('<x:xmpmeta xmlns:x="adobe:ns:meta/"/>')
        before = meter.snapshot()
        sidecar.read(self.photo)
        self.assertEqual(meter.since(before)["own_files"], 1)

    def test_a_copy_counts_as_both_read_and_written(self):
        before = meter.snapshot()
        meter.copied(1000)
        got = meter.since(before)
        self.assertEqual(got["own_bytes"], 1000)
        self.assertEqual(got["own_written"], 1000)

    def test_the_measurement_is_there_even_with_no_kernel_counters(self):
        """The whole point. /proc/self/io may be unreadable; this may not be."""
        got = load.snapshot()
        self.assertIn("own_files", got)
        self.assertIn("own_bytes", got)

    def test_the_cost_line_leads_with_the_disk_not_the_cpu(self):
        said = load.describe({"seconds": 30.0, "cpu": 2.0,
                              "own_files": 3000, "own_bytes": 900_000_000})
        self.assertLess(said.index("opened"), said.index("working"))
        self.assertIn("3,000 files", said)

    def test_and_says_files_before_bytes(self):
        """On a spinning disk the seek is what you wait for."""
        said = load.disk({"own_files": 10, "own_bytes": 1000})
        self.assertLess(said.index("files"), said.index("KB"))

    def test_nothing_measured_says_so_rather_than_showing_zero(self):
        self.assertEqual(load.disk({"seconds": 1.0}), "not measured")


class TheSameFileTwiceInARow(unittest.TestCase):
    """Keywords alone are looked for in three places inside one JPEG, and each
    of them used to be its own quarter-megabyte read. The front of a file asked
    for twice running is read once - but only while it is demonstrably the same
    file, which is the half that has to be tested, because this app rewrites
    photographs in place and then puts their date back."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="memo-")
        self.photo = os.path.join(self.dir, "a.JPG")
        shutil.copy(os.path.join(FIX, "rated.jpg"), self.photo)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_the_second_ask_does_not_go_to_the_disk(self):
        jpegseg.read_header(self.photo)
        before = meter.snapshot()
        got = jpegseg.read_header(self.photo)
        self.assertEqual(meter.since(before)["own_files"], 0)
        self.assertTrue(got)

    def test_but_a_different_file_does(self):
        other = os.path.join(self.dir, "b.JPG")
        shutil.copy(os.path.join(FIX, "plain.jpg"), other)
        jpegseg.read_header(self.photo)
        before = meter.snapshot()
        jpegseg.read_header(other)
        self.assertEqual(meter.since(before)["own_files"], 1)

    def test_and_so_does_the_same_file_after_we_have_written_to_it(self):
        """The dangerous one. A rating is written by replacing the file and
        restoring its date to the nanosecond, so a memo keyed on the name - or
        even on the name, size and date - would hand back the bytes from before
        the write."""
        from core.exifwrite import write_rating
        was = jpegseg.read_header(self.photo)
        write_rating(self.photo, 1)
        before = meter.snapshot()
        now = jpegseg.read_header(self.photo)
        self.assertEqual(meter.since(before)["own_files"], 1,
                         "it answered from before the write")
        self.assertNotEqual(was, now)

    def test_a_file_that_is_not_there_is_not_remembered_as_empty(self):
        gone = os.path.join(self.dir, "never.JPG")
        self.assertEqual(jpegseg.read_header(gone), b"")
        shutil.copy(os.path.join(FIX, "plain.jpg"), gone)
        self.assertTrue(jpegseg.read_header(gone))


class Failures(unittest.TestCase):
    def test_one_cause_over_many_files_is_one_line(self):
        r = Result()
        for name in ("a", "b", "c", "d", "e"):
            r.blame(f"/photos/{name}.jpg",
                    OSError(f"[Errno 13] Permission denied: '/photos/{name}.jpg'"))
        lines = r.lines()
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("5 x", lines[0])
        self.assertIn("Permission denied", lines[0])

    def test_and_names_a_few_of_them_so_you_can_go_and_look(self):
        r = Result()
        for name in ("a", "b", "c", "d", "e"):
            r.blame(f"/photos/{name}.jpg", OSError("no"))
        self.assertIn("a.jpg", r.lines()[0])
        self.assertIn("and 2 more", r.lines()[0])

    def test_the_count_and_the_tally_cannot_disagree(self):
        """Recording the reason and counting the failure are one call, so a
        task cannot do one and forget the other."""
        r = Result()
        r.blame("/x/a.jpg", OSError("no"))
        r.blame("/x/b.jpg", OSError("no"))
        self.assertEqual(r.failed, 2)

    def test_different_causes_stay_apart_commonest_first(self):
        r = Result()
        r.blame("/x/a.jpg", OSError("it is no longer there"))
        for name in "bcd":
            r.blame(f"/x/{name}.jpg", OSError("[Errno 13] Permission denied"))
        lines = r.lines()
        self.assertEqual(len(lines), 2)
        self.assertIn("Permission denied", lines[0])

    def test_the_paths_are_what_is_stripped_to_make_a_cause(self):
        self.assertEqual(
            _gist("[Errno 13] Permission denied: '/photos/library/a.jpg'"),
            _gist("[Errno 13] Permission denied: '/photos/library/b.jpg'"))

    def test_and_so_are_the_numbers_inside_one(self):
        """"read back 3 instead of 4" and "read back 1 instead of 5" are the
        same fault, and it is the fault that is worth naming."""
        self.assertEqual(_gist("read back 3 instead of 4"),
                         _gist("read back 1 instead of 5"))

    def test_two_genuinely_different_messages_do_not_collapse(self):
        self.assertNotEqual(_gist("permission denied"),
                            _gist("it is no longer there"))

    def test_the_causes_come_before_the_tasks_own_lines(self):
        """A list that opens with sixty file names and explains itself at the
        bottom is a list nobody scrolls."""
        r = Result()
        r.details.append("everything else went fine")
        r.blame("/x/a.jpg", OSError("no"))
        self.assertIn("1 x", r.lines()[0])

    def test_a_run_with_nothing_wrong_says_exactly_what_it_used_to(self):
        r = Result()
        r.details.append("all good")
        self.assertEqual(r.lines(), ["all good"])

    def test_every_task_that_writes_reports_its_failures_this_way(self):
        """A task still appending raw lines is a task whose 28 failures are 28
        mysteries again, and it would never be noticed from the outside."""
        import glob
        import re
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bad = []
        for path in sorted(glob.glob(os.path.join(here, "app", "tasks", "*.py"))):
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            if re.search(r'status = f"FAILED', text):
                bad.append(os.path.basename(path))
        self.assertTrue(glob.glob(os.path.join(here, "app", "tasks", "*.py")),
                        "found no tasks to check, so this proves nothing")
        self.assertEqual(bad, [], f"still ungrouped: {bad}")


if __name__ == "__main__":
    unittest.main()
