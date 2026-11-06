"""Replacing a photograph with its rewritten copy, and trying again on Windows.

Windows refuses `os.replace` while another program - Explorer making a
thumbnail, an antivirus scan - has the file open, and the refusal clears itself
a moment later. Linux never refuses for that reason, so there it stays a plain
replace.
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import replace as RP                # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def flaky(times):
    """An os.replace that is refused `times` times, then works."""
    real = os.replace
    calls = []

    def replace(src, dst):
        calls.append((src, dst))
        if len(calls) <= times:
            raise PermissionError(13, "The process cannot access the file")
        return real(src, dst)
    return replace, calls


class Retrying(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="replace-")
        self.src = os.path.join(self.dir, "a.JPG.tmp")
        self.dst = os.path.join(self.dir, "a.JPG")
        for p, body in ((self.src, b"new"), (self.dst, b"old")):
            with open(p, "wb") as fh:
                fh.write(body)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_refused_twice_then_it_works(self):
        fake, calls = flaky(2)
        slept = []
        with mock.patch("os.replace", fake):
            RP.replace_file(self.src, self.dst, retry=True, sleep=slept.append)
        self.assertEqual(len(calls), 3)
        self.assertEqual(slept, [0.2, 0.4])
        with open(self.dst, "rb") as fh:
            self.assertEqual(fh.read(), b"new")

    def test_held_for_good_it_says_which_file(self):
        fake, calls = flaky(100)
        slept = []
        with mock.patch("os.replace", fake):
            with self.assertRaises(PermissionError) as e:
                RP.replace_file(self.src, self.dst, retry=True,
                                sleep=slept.append)
        self.assertEqual(len(calls), 6)                  # once, then five more
        self.assertEqual(slept, [0.2, 0.4, 0.8, 1.6, 3.2])
        self.assertIn("a.JPG", str(e.exception))

    def test_off_windows_it_is_a_plain_replace(self):
        fake, calls = flaky(1)
        with mock.patch.object(RP, "_on_windows", lambda: False), \
                mock.patch("os.replace", fake):
            with self.assertRaises(PermissionError):
                RP.replace_file(self.src, self.dst, sleep=self.fail)
        self.assertEqual(len(calls), 1)

    def test_other_errors_are_not_retried(self):
        with self.assertRaises(FileNotFoundError):
            RP.replace_file(os.path.join(self.dir, "nope"), self.dst,
                            retry=True, sleep=self.fail)


class ThePhotoWritersUseIt(unittest.TestCase):
    def test_a_rating_write_survives_a_file_held_for_a_moment(self):
        from core.exifwrite import rating_of, write_rating
        d = tempfile.mkdtemp(prefix="replace-rating-")
        try:
            photo = os.path.join(d, "rated.JPG")
            shutil.copy(os.path.join(FIX, "rated.jpg"), photo)
            fake, calls = flaky(2)
            with mock.patch.object(RP, "_on_windows", lambda: True), \
                    mock.patch.object(RP, "DELAYS", (0, 0, 0, 0, 0)), \
                    mock.patch("os.replace", fake):
                write_rating(photo, 2)
            self.assertEqual(len(calls), 3)
            self.assertEqual(rating_of(photo), 2)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_nothing_that_rewrites_a_photograph_calls_os_replace_itself(self):
        for rel in ("core/exifwrite.py", "core/tagwrite.py", "core/sidecar.py",
                    "app/tasks/previews.py"):
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                code = [ln for ln in fh if not ln.lstrip().startswith("#")]
            self.assertFalse([ln for ln in code if "os.replace(" in ln], rel)


if __name__ == "__main__":
    unittest.main()
