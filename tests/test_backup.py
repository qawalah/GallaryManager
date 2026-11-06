"""Backup and the checklist: the password never travels, a restore can be undone."""

import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.tasks  # noqa: E402,F401
from app import registry as R                    # noqa: E402
from app.tasks import backup as B                # noqa: E402
from app.tasks import checklist as C             # noqa: E402


class _Data(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="backup-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = self.dir

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def put(self, name, text):
        with open(os.path.join(self.dir, name), "w") as fh:
            fh.write(text)

    def read(self, name):
        with open(os.path.join(self.dir, name)) as fh:
            return fh.read()


class BackingUp(_Data):
    def test_the_password_file_never_goes_in(self):
        self.put("settings.json", "{}")
        self.put("developed.jsonl", "a\n")
        self.put("access.json", "secret")
        where, n = B.make_backup()
        names = zipfile.ZipFile(where).namelist()
        self.assertIn("developed.jsonl", names)
        self.assertNotIn("access.json", names)
        self.assertEqual(n, 2)

    def test_only_the_last_twenty_are_kept(self):
        self.put("settings.json", "{}")
        for _ in range(B.KEEP + 3):
            B.make_backup()
        self.assertEqual(len(B._backups()), B.KEEP)

    def test_nothing_set_up_is_blocked(self):
        p = B.plan({"what": "backup"})
        self.assertTrue(p.blocked)

    def test_the_task_backs_up(self):
        self.put("flows.json", "[]")
        p = B.plan({"what": "backup"})
        r = B.apply(p)
        self.assertEqual(r.done, 1)
        self.assertEqual(len(B._backups()), 1)


class Restoring(_Data):
    def test_restore_puts_it_back_and_saves_now_first(self):
        self.put("settings.json", '{"library": "old"}')
        self.put("access.json", "mine")
        first, _ = B.make_backup()
        time.sleep(1.1)
        self.put("settings.json", '{"library": "new"}')
        p = B.plan({"what": "restore", "source": first})
        self.assertFalse(p.blocked)
        r = B.apply(p)
        self.assertEqual(r.done, 1)
        self.assertIn("old", self.read("settings.json"))
        self.assertEqual(self.read("access.json"), "mine")
        safety = [b for b in B._backups() if "before-restore" in b]
        self.assertEqual(len(safety), 1)
        with zipfile.ZipFile(safety[0]) as z:
            self.assertIn(b"new", z.read("settings.json"))

    def test_a_password_file_inside_a_zip_is_ignored(self):
        where = os.path.join(self.dir, "odd.zip")
        with zipfile.ZipFile(where, "w") as z:
            z.writestr("access.json", "evil")
            z.writestr("settings.json", "{}")
        p = B.plan({"what": "restore", "source": where})
        self.assertEqual([r.name for r in p.rows], ["settings.json"])

    def test_not_a_zip_is_blocked(self):
        where = os.path.join(self.dir, "bad.zip")
        self.put("bad.zip", "not a zip")
        self.assertTrue(B.plan({"what": "restore", "source": where}).blocked)

    def test_registered_in_setup(self):
        t = R.get("backup")
        self.assertEqual(t.parent, "setup")


class Checklist(_Data):
    def test_a_new_install_says_the_library_is_missing(self):
        self.assertTrue(C.first_run())
        p = C.plan({})
        lib = [r for r in p.rows if r.name == "The library"][0]
        self.assertEqual(lib.data["state"], C.BAD)
        self.assertTrue(any("Start here" in n for n in p.notes))

    def test_a_writable_library_is_fine(self):
        lib = tempfile.mkdtemp(dir=self.dir)
        self.put("settings.json", '{"library": "%s"}' % lib)
        self.assertFalse(C.first_run())
        p = C.plan({})
        row = [r for r in p.rows if r.name == "The library"][0]
        self.assertEqual(row.data["state"], C.OK)
        self.assertEqual(os.listdir(lib), [])

    def test_every_line_has_a_known_state(self):
        for what, state, says, _where in C.checks():
            self.assertIn(state, C.MARK)
            self.assertTrue(says)


if __name__ == "__main__":
    unittest.main()
