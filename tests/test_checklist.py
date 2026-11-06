"""The Checklist: each line measured, and the ones about the index.

Only the index's line is tested here; the other lines are covered where the
thing they measure is (permissions, backup, the password).
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.tasks                              # noqa: E402,F401
from app import registry as R                 # noqa: E402
from app.tasks import checklist               # noqa: E402
from core import catalogue as C               # noqa: E402
from core import settings as S                # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class TheIndexLine(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="checklist-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        self.lib = os.path.join(self.home, "Photos")
        os.makedirs(self.lib)
        for n in ("aeb1", "aeb2", "aeb3"):
            shutil.copy(os.path.join(FIX, f"{n}.jpg"),
                        os.path.join(self.lib, f"{n}.JPG"))
        S.save({"library": self.lib})
        C.forget_all()
        self._real = C._read_entry

    def tearDown(self):
        C._read_entry = self._real
        C.forget_all()
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.home, ignore_errors=True)

    def line(self):
        plan = R.get("checklist").make_plan({"try_writing": False})
        rows = [r for r in plan.rows if r.name == "Library index"]
        return rows[0] if rows else None

    def test_one_unreadable_file_is_a_line_naming_it(self):
        real = self._real

        def read(path, *a, **k):
            if os.path.basename(path) == "aeb2.JPG":
                raise OSError(5, "Input/output error")
            return real(path, *a, **k)
        C._read_entry = read
        C.shared().refresh([self.lib])
        row = self.line()
        self.assertIsNotNone(row)
        self.assertEqual(row.data["state"], checklist.WARN)
        self.assertIn("1 file could not be read", row.detail)
        self.assertIn("aeb2.JPG", row.detail)
        self.assertIn("Input/output error", row.detail)

    def test_a_library_read_whole_is_fine(self):
        C.shared().refresh([self.lib])
        row = self.line()
        self.assertEqual(row.data["state"], checklist.OK)
        self.assertIn("every one read", row.detail)

    def test_before_the_index_is_built_there_is_no_line(self):
        self.assertIsNone(self.line())

    def test_the_wording_counts_and_names_the_first_few(self):
        names = [{"path": f"/p/x{n}.JPG", "error": "bad"} for n in range(5)]
        said = checklist.unreadable_said(5, names)
        self.assertTrue(said.startswith("5 files could not be read: x0.JPG (bad)"))
        self.assertTrue(said.endswith(", ..."))
        self.assertEqual(checklist.unreadable_said(0, []), "")


class TheRepairJobLine(unittest.TestCase):
    """The permissions job is a NAS thing. On a PC its line would warn, on
    every visit, that a job which will never exist "has never run"."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="checklist-")
        self._was = {k: os.environ.get(k) for k in ("PM_DATA", "PM_DESKTOP")}
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        self.lib = os.path.join(self.home, "Photos")
        os.makedirs(self.lib)
        S.save({"library": self.lib})

    def tearDown(self):
        for k, v in self._was.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.home, ignore_errors=True)

    def names(self, desktop: bool) -> list:
        os.environ["PM_DESKTOP"] = "1" if desktop else ""
        return [c[0] for c in checklist.checks(try_writing=False)]

    def test_on_the_nas_it_is_there(self):
        self.assertIn("Repair job", self.names(desktop=False))

    def test_on_a_pc_it_is_not(self):
        names = self.names(desktop=True)
        self.assertNotIn("Repair job", names)
        self.assertIn("The library", names)

    def test_it_says_whether_heic_pictures_can_be_drawn(self):
        """Without the HEIC reader an iPhone library is grey squares, and
        nothing else on the page would say why."""
        self.assertIn("HEIC reader", self.names(desktop=True))
        self.assertIn("HEIC reader", self.names(desktop=False))

    def test_on_a_pc_nothing_points_at_permissions(self):
        os.environ["PM_DESKTOP"] = "1"
        where = [c[3] for c in checklist.checks(try_writing=True)]
        self.assertNotIn("Permissions", where)


if __name__ == "__main__":
    unittest.main()
