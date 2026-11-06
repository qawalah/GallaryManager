"""Telling DSM that the files moved.

The feature exists because an index is not the filesystem: move a shoot and it
is on the disk instantly and missing from Synology Photos until something says
so. What is worth testing is not the commands - they are three lines - but the
four ways this could quietly do nothing:

- forgetting the folder a file came FROM, so the index still lists photographs
  that are not there any more;
- queueing a folder that has since been tidied away, and emitting a command for
  a path that no longer exists;
- emptying the queue when nothing was actually told, which loses the list;
- claiming to have run the DSM tools when they were never there.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from app.registry import Row               # noqa: E402
from core import reindex                   # noqa: E402
from core import settings as S             # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="reindex-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        S.save({"library": self.lib})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)


class TheQueue(Base):
    def test_both_ends_of_a_move_are_remembered(self):
        """An index told about the new folder and not the old one still lists
        photographs that are no longer there."""
        rows = [Row(name="a.JPG", source=os.path.join(self.shoot, "a.JPG"),
                    target=os.path.join(self.lib, "2022", "07", "a.JPG"))]
        got = reindex.folders_touched(rows)
        self.assertIn(self.shoot, got)
        self.assertIn(os.path.join(self.lib, "2022", "07"), got)

    def test_the_same_folder_is_not_queued_twice(self):
        reindex.remember([self.shoot, self.shoot])
        reindex.remember([self.shoot])
        self.assertEqual(reindex.queued(), [self.shoot])

    def test_a_folder_that_has_gone_is_told_about_through_its_parent(self):
        """It cannot be re-read - it is gone - and re-reading the parent is what
        makes the index drop what it no longer holds."""
        emptied = os.path.join(self.lib, "2022", "card dump")
        reindex.remember([emptied])
        self.assertEqual(reindex.settle(reindex.queued()),
                         [os.path.join(self.lib, "2022")])

    def test_a_folder_inside_another_queued_one_is_dropped(self):
        """-R reads a folder and everything under it, so telling DSM about the
        shoot and the year above it is the same work done twice."""
        reindex.remember([os.path.join(self.lib, "2022"), self.shoot])
        self.assertEqual(reindex.settle(reindex.queued()),
                         [os.path.join(self.lib, "2022")])

    def test_a_queue_that_cannot_be_written_is_not_an_error(self):
        """It can be done again at any time. Turning a working file move into a
        failed one over a re-index note would be a bad trade - and the store
        raises rather than returning a path when it cannot be written."""
        os.environ["PM_DATA"] = "/proc/nowhere/at/all"
        self.assertEqual(reindex.remember([self.shoot]), 0)
        self.assertEqual(reindex.queued(), [])


class TheCommands(Base):
    def test_media_indexing_takes_one_folder(self):
        self.assertEqual(reindex.index_command("/photos/library"),
                         ["synoindex", "-R", "/photos/library"])

    def test_photos_has_a_different_api_for_each_space(self):
        shared = " ".join(reindex.photos_command("someone"))
        mine = " ".join(reindex.photos_command("someone", personal=True))
        self.assertIn("api=SYNO.FotoTeam.Index", shared)
        self.assertIn("api=SYNO.Foto.Index", mine)
        self.assertIn("runner=someone", shared)
        self.assertIn("method=reindex", shared)

    def test_a_folder_name_with_a_quote_in_it_cannot_break_the_script(self):
        text = reindex.script(["/photos/it's a folder", "/photos/plain"],
                              where="/x/reindex.sh")
        self.assertIn("'/photos/it'\\''s a folder'", text)
        self.assertIn("/photos/plain", text)

    def test_the_script_says_where_and_how_to_run_it(self):
        text = reindex.script([self.shoot], "someone", where="/x/reindex.sh")
        self.assertIn("Task Scheduler", text)
        self.assertIn("root", text)
        self.assertIn("/x/reindex.sh", text)
        self.assertIn("synoindex", text)
        self.assertIn("SYNO.FotoTeam.Index", text)

    def test_without_a_username_photos_is_left_out_entirely(self):
        text = reindex.script([self.shoot], "", where="/x/reindex.sh")
        self.assertNotIn("SYNO.FotoTeam.Index", text)
        self.assertNotIn("--exec", text)

    def test_running_something_that_is_not_there_fails_quietly(self):
        ok, said = reindex.run(["/no/such/tool", "-R", "/x"])
        self.assertFalse(ok)
        self.assertTrue(said)


class TheTask(Base):
    def plan(self, **over):
        t = R.get("reindex")
        return t, t.make_plan({"script_into": self.lib, "user": "someone", **over})

    def test_with_no_tools_here_it_writes_a_script_instead(self):
        reindex.remember([self.shoot])
        t, p = self.plan()
        self.assertFalse(p.blocked, p.blocked)
        self.assertEqual(len(p.rows), 1)
        self.assertEqual(t.apply(p).failed, 0)
        with open(os.path.join(self.lib, "reindex.sh"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(self.shoot, text)

    def test_and_it_says_why_rather_than_looking_broken(self):
        reindex.remember([self.shoot])
        _t, p = self.plan()
        self.assertTrue(any("container" in n for n in p.notes))

    def test_with_nowhere_to_write_it_refuses_and_explains(self):
        reindex.remember([self.shoot])
        _t, p = self.plan(script_into="")
        self.assertTrue(p.blocked)
        self.assertIn("container", p.blocked)

    def test_writing_a_script_does_not_empty_the_queue(self):
        """Nothing has been TOLD yet. Emptying it here would leave those folders
        waiting nowhere, and the next script would be empty."""
        reindex.remember([self.shoot])
        t, p = self.plan()
        t.apply(p)
        self.assertEqual(reindex.queued(), [self.shoot])

    def test_unless_you_ask_for_it(self):
        reindex.remember([self.shoot])
        t, p = self.plan(forget=True)
        t.apply(p)
        self.assertEqual(reindex.queued(), [])

    def test_when_the_tools_are_here_it_runs_them_and_empties_the_queue(self):
        """Pretended, because there is no DSM on this machine - what is being
        tested is that the app runs the tool per folder and only forgets the
        queue once something was actually told."""
        ran = []
        real_available, real_run = reindex.available, reindex.run
        reindex.available = lambda: {"synoindex": "/fake/synoindex",
                                     "synowebapi": ""}
        reindex.run = lambda command, seconds=900: (ran.append(command), (True, ""))[1]
        try:
            reindex.remember([self.shoot])
            t, p = self.plan()
            self.assertEqual(len(p.rows), 1)
            result = t.apply(p)
            self.assertEqual(result.failed, 0)
            self.assertEqual(ran, [["/fake/synoindex", "-R", self.shoot]])
            self.assertEqual(reindex.queued(), [])
        finally:
            reindex.available, reindex.run = real_available, real_run

    def test_a_tool_that_refuses_keeps_the_queue(self):
        real_available, real_run = reindex.available, reindex.run
        reindex.available = lambda: {"synoindex": "/fake/synoindex",
                                     "synowebapi": ""}
        reindex.run = lambda command, seconds=900: (False, "permission denied")
        try:
            reindex.remember([self.shoot])
            t, p = self.plan()
            result = t.apply(p)
            self.assertEqual(result.failed, 1)
            self.assertIn("permission denied", " ".join(result.lines()))
            self.assertEqual(reindex.queued(), [self.shoot],
                             "the queue was emptied although nothing was told")
        finally:
            reindex.available, reindex.run = real_available, real_run


class TheWholeLoop(Base):
    """A real move, and then the script that tells DSM about exactly it."""

    def plan(self, **over):
        t = R.get("reindex")
        return t, t.make_plan({"script_into": self.lib, "user": "someone", **over})

    def test_a_sort_fills_the_queue_and_the_script_names_those_folders(self):
        dump = os.path.join(self.lib, "card dump")
        os.makedirs(dump)
        for n in ("plain", "rated"):
            shutil.copy(os.path.join(FIX, n + ".jpg"), os.path.join(dump, n + ".JPG"))
        sort = R.get("bydate")
        p = sort.make_plan({"folder": dump, "shape": "year_month", "mirror": False,
                            "raw": "", "previews": ""})
        self.assertEqual(sort.apply(p).failed, 0)
        # what the server does after every run that writes
        reindex.remember(reindex.folders_touched(p.rows))

        t, p2 = self.plan()
        t.apply(p2)
        with open(os.path.join(self.lib, "reindex.sh"), encoding="utf-8") as fh:
            text = fh.read()
        # The photographs moved into 2022/07 INSIDE the card dump, so the dump
        # itself is still there and is what gets told - one command, because -R
        # reads a folder and everything under it. Naming the new sub-folder as
        # well would be the same work done twice.
        plain = text.replace("'", "")
        self.assertIn(f"-R {dump}\n", plain)
        self.assertNotIn(os.path.join(dump, "2022"), plain)
        self.assertEqual(plain.count('"$INDEX" -R'), 1)


if __name__ == "__main__":
    unittest.main()
