"""Two kinds of remembering, and why they are not the same thing.

**Where you last worked** (`core/recent.py`). Setup answers "the library is
here"; this answers "last time you culled, you culled Italy 2024". Both are
useful and neither substitutes for the other, which is why the narrower one
fills the box and the broader one is the fallback.

**What was actually done** (`core/runlog.py`). The Library view is measured from
the files as they are now, and that is deliberate - but it means it cannot
answer "what happened to this folder last night". A scheduled run at 3am has
nobody watching it, so the log is the only place that answer can come from.

The failure mode both share: remembering something wrong is worse than
remembering nothing. A form that opens on a path that no longer exists, or a log
that loses everything because one line got mangled, is a feature that has turned
against you.
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from core import recent, runlog            # noqa: E402
from core import settings as S             # noqa: E402


class Fresh(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="memory-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.shoot = os.path.join(self.lib, "2024", "Italy")
        os.makedirs(self.shoot)

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)


class WhereYouLastWorked(Fresh):
    def test_planning_a_task_remembers_the_folder_it_was_pointed_at(self):
        t = R.get("library")
        t.make_plan({"folder": self.shoot})
        self.assertEqual(recent.get("library", "folder"), self.shoot)

    def test_and_the_form_opens_there_next_time(self):
        R.get("library").make_plan({"folder": self.shoot})
        opened = R.get("library").start_values()
        self.assertEqual(opened["folder"], self.shoot)

    def test_it_beats_the_setting_because_it_is_the_narrower_answer(self):
        """Setup says where the library is. This says what you were working on.
        The box you type in wants the second one."""
        S.save({"library": self.lib})
        self.assertEqual(R.get("library").start_values()["folder"], self.lib)
        R.get("library").make_plan({"folder": self.shoot})
        self.assertEqual(R.get("library").start_values()["folder"], self.shoot)

    def test_but_a_folder_that_has_gone_falls_back_rather_than_lying(self):
        """A form that opens on a path that no longer exists is worse than one
        that opens on the library root."""
        S.save({"library": self.lib})
        R.get("library").make_plan({"folder": self.shoot})
        shutil.rmtree(self.shoot)
        self.assertEqual(R.get("library").start_values()["folder"], self.lib)

    def test_a_folder_that_is_not_there_is_never_written_down(self):
        S.save({"library": self.lib})
        """A blocked plan never gets here at all, so the case that matters is a
        plan that SUCCEEDS with a folder that does not exist yet - the RAW tree,
        which is created the first time something writes to it. Accepting it for
        the run is right; remembering it as where you work is not."""
        gone = os.path.join(self.dir, "not-yet")
        # A folder of the library rather than the library itself, which is
        # Setup's value and is never remembered (WhenSetupMoves).
        p = R.get("unpair").make_plan({"folder": self.shoot, "raw": gone})
        self.assertFalse(p.blocked, p.blocked)
        self.assertEqual(recent.get("unpair", "raw"), "")
        self.assertNotIn("unpair.raw", recent.load())
        self.assertEqual(recent.load().get("unpair.folder"), self.shoot)

    def test_each_task_remembers_its_own(self):
        R.get("library").make_plan({"folder": self.shoot})
        R.get("duplicates").make_plan({"folder": self.lib})
        self.assertEqual(recent.get("library", "folder"), self.shoot)
        self.assertEqual(recent.get("duplicates", "folder"), self.lib)

    def test_a_damaged_file_means_nothing_remembered_not_a_crash(self):
        os.makedirs(os.environ["PM_DATA"], exist_ok=True)
        with open(os.path.join(os.environ["PM_DATA"], recent.FILE), "w") as fh:
            fh.write("{ this is not json")
        self.assertEqual(recent.get("library", "folder"), "")
        R.get("library").make_plan({"folder": self.shoot})      # still works
        self.assertEqual(recent.get("library", "folder"), self.shoot)


class MovingSetup(Fresh):
    def setUp(self):
        super().setUp()
        self.new = os.path.join(self.dir, "New library")
        os.makedirs(self.new)
        S.save({"library": self.lib})

    def opens_on(self, task, option):
        return R.get(task).start_values()[option]


class WhenSetupMoves(MovingSetup):
    """ALI changed the library in Setup and Search went on opening on the old
    one, reload or not: running Search with the box as it opened had been
    remembered as "where you last worked", and a remembered folder beats
    Setup. Setup's own value is not a choice, and a tree that moves takes
    what was remembered inside it along."""

    def test_a_run_on_setups_library_is_not_remembered(self):
        R.get("search").make_plan({"folders": self.lib})
        self.assertEqual(recent.get("search", "folders", must_exist=False), "")
        S.save({"library": self.new})
        self.assertEqual(self.opens_on("search", "folders"), self.new)

    def test_nor_for_a_single_folder_box(self):
        R.get("library").make_plan({"folder": self.lib})
        self.assertEqual(recent.get("library", "folder"), "")

    def test_and_going_back_to_setups_value_forgets_the_pick(self):
        R.get("search").make_plan({"folders": self.shoot})
        self.assertEqual(self.opens_on("search", "folders"), self.shoot)
        R.get("search").make_plan({"folders": self.lib})
        self.assertEqual(self.opens_on("search", "folders"), self.lib)

    def test_a_folder_of_the_old_library_is_forgotten_when_it_moves(self):
        R.get("search").make_plan({"folders": self.shoot})
        R.get("library").make_plan({"folder": self.shoot})
        S.save({"library": self.new})
        self.assertEqual(self.opens_on("search", "folders"), self.new)
        self.assertEqual(self.opens_on("library", "folder"), self.new)

    def test_a_folder_somewhere_else_is_still_yours(self):
        elsewhere = os.path.join(self.dir, "Scans")
        os.makedirs(elsewhere)
        R.get("library").make_plan({"folder": elsewhere})
        S.save({"library": self.new})
        self.assertEqual(self.opens_on("library", "folder"), elsewhere)

    def test_moving_into_a_folder_of_it_keeps_what_is_still_inside(self):
        R.get("library").make_plan({"folder": self.shoot})
        S.save({"library": os.path.join(self.lib, "2024")})
        self.assertEqual(self.opens_on("library", "folder"), self.shoot)

    def test_a_list_keeps_the_folders_that_are_not_in_the_old_tree(self):
        elsewhere = os.path.join(self.dir, "Scans")
        os.makedirs(elsewhere)
        R.get("search").make_plan({"folders": self.shoot + "\n" + elsewhere})
        S.save({"library": self.new})
        self.assertEqual(recent.get("search", "folders", must_exist=False),
                         elsewhere)


class WhatAPickStillMeans(MovingSetup):
    """ALI again: the Library tool's box said "last used" and showed the old
    library. A pick remembered by 3.12.0 or earlier - when Setup's own library
    was remembered as a pick - survived the library moving, because the move
    that would have forgotten it happened before the fix. Each pick now
    carries what Setup said when it was made, and is measured against what
    Setup says now, however the settings got changed."""

    def remembered_by_an_older_version(self, task, option, value):
        os.makedirs(os.environ["PM_DATA"], exist_ok=True)
        with open(os.path.join(os.environ["PM_DATA"], recent.FILE), "w") as fh:
            json.dump({f"{task}.{option}": value}, fh)

    def settings_edited_by_hand(self, **values):
        """Not through `settings.save`, so nothing is told the tree moved."""
        path = os.path.join(os.environ["PM_DATA"], S.FILE)
        with open(path) as fh:
            body = json.load(fh)
        body.update(values)
        with open(path, "w") as fh:
            json.dump(body, fh)
        S.forget()

    def test_an_old_library_remembered_before_the_fix_does_not_come_back(self):
        self.remembered_by_an_older_version("library", "folder", self.lib)
        self.settings_edited_by_hand(library=self.new)
        self.assertEqual(self.opens_on("library", "folder"), self.new)
        self.assertEqual(R.get("library").value_sources()["folder"], "setup")

    def test_an_old_pick_inside_todays_library_is_still_used(self):
        self.remembered_by_an_older_version("library", "folder", self.shoot)
        self.assertEqual(self.opens_on("library", "folder"), self.shoot)
        self.assertEqual(R.get("library").value_sources()["folder"], "recent")

    def test_a_pick_in_a_library_that_moved_is_dropped_however_it_moved(self):
        R.get("library").make_plan({"folder": self.shoot})
        self.settings_edited_by_hand(library=self.new)
        self.assertEqual(self.opens_on("library", "folder"), self.new)

    def test_a_pick_outside_the_library_survives_it_moving_by_hand_too(self):
        """An Inbox is outside the library on purpose, and Sort into folders
        is pointed at it every time."""
        inbox = os.path.join(self.dir, "Inbox")
        os.makedirs(inbox)
        R.get("library").make_plan({"folder": inbox})
        self.settings_edited_by_hand(library=self.new)
        self.assertEqual(self.opens_on("library", "folder"), inbox)

    def test_a_list_keeps_only_what_still_means_something(self):
        inbox = os.path.join(self.dir, "Inbox")
        os.makedirs(inbox)
        R.get("search").make_plan({"folders": self.shoot + "\n" + inbox})
        self.settings_edited_by_hand(library=self.new)
        self.assertEqual(self.opens_on("search", "folders"), inbox)


class WhatWasActuallyDone(Fresh):
    class Done:
        def __init__(self, done=0, failed=0):
            self.done, self.failed = done, failed
            self.cancelled = False
            self.stats = [("Files moved", str(done))]
            self.details = ["it went fine"]

    def test_a_run_is_recorded_with_what_it_touched(self):
        runlog.record("unpair", {"folder": self.lib}, self.Done(done=4), 2.5)
        got = runlog.recent()
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["task"], "unpair")
        self.assertEqual(got[0]["done"], 4)
        self.assertEqual(got[0]["folders"]["folder"], self.lib)

    def test_newest_first(self):
        runlog.record("unpair", {}, self.Done(1))
        time.sleep(0.01)
        runlog.record("cull", {}, self.Done(2))
        self.assertEqual([g["task"] for g in runlog.recent()], ["cull", "unpair"])

    def test_it_can_be_asked_about_one_feature(self):
        runlog.record("unpair", {}, self.Done(1))
        runlog.record("cull", {}, self.Done(2))
        self.assertEqual([g["task"] for g in runlog.recent(task="cull")], ["cull"])

    def test_one_damaged_line_does_not_cost_you_the_rest(self):
        """The whole reason it is one JSON object per line rather than one big
        document: a half-written line loses that run, not the year."""
        runlog.record("unpair", {}, self.Done(1))
        with open(os.path.join(os.environ["PM_DATA"], runlog.FILE), "a") as fh:
            fh.write("{ half a line\n")
        runlog.record("cull", {}, self.Done(2))
        self.assertEqual([g["task"] for g in runlog.recent()], ["cull", "unpair"])

    def test_nothing_recorded_yet_is_not_an_error(self):
        self.assertEqual(runlog.recent(), [])


class TheHistoryTab(Fresh):
    def test_it_shows_what_the_log_holds(self):
        runlog.record("unpair", {"folder": self.lib},
                      WhatWasActuallyDone.Done(done=4), 1.0)
        p = R.get("history").make_plan({})
        self.assertEqual(len(p.rows), 1)
        # In the words somebody would use: the feature's title, and what it did
        # to how many - not its internal name and "4 done".
        self.assertIn("Separate RAWs", p.rows[0].detail)
        self.assertIn("Moved 4", p.rows[0].detail)
        self.assertEqual(p.rows[0].source, self.lib)

    def test_it_never_writes(self):
        self.assertFalse(R.get("history").writes)

    def test_its_columns_are_named_because_its_rows_are_not_files(self):
        """"File" over a column of times is the sort of small lie that makes a
        page feel untrustworthy."""
        p = R.get("history").make_plan({})
        # The run NUMBER goes where a name goes: "put run 1042 back" is a thing
        # somebody can say, and the millisecond it finished is not.
        self.assertEqual(p.columns[0], "Run")
        self.assertIn("When", p.columns)
        self.assertNotIn("File", p.columns)

    def test_the_cells_line_up_under_the_headings(self):
        """The table puts the row's NAME in the first column and the folder in
        the last by itself, so a task names the middle ones only. Getting that
        wrong shifts every value one column left and the page reads as nonsense
        while looking perfectly tidy - "Geotag" under "When"."""
        runlog.record("files", {"folder": self.lib},
                      WhatWasActuallyDone.Done(done=2), 0.5, action="delete")
        p = R.get("history").make_plan({})
        row = p.rows[0]
        self.assertEqual(len(row.cells), len(p.columns) - 1)
        self.assertEqual(row.cells[0], "File explorer")   # under "Feature"
        self.assertIn("Deleted", row.cells[2])            # under "What happened"
        self.assertTrue(row.name.startswith("#"))         # under "Run"

    def test_it_can_be_narrowed_to_one_feature(self):
        runlog.record("unpair", {}, WhatWasActuallyDone.Done(1))
        runlog.record("cull", {}, WhatWasActuallyDone.Done(2))
        p = R.get("history").make_plan({"task": "cull"})
        self.assertEqual(len(p.rows), 1)
        self.assertEqual(p.rows[0].what, "cull")
        self.assertIn("Cull by rating", p.rows[0].detail)

    def test_the_tabs_are_built_from_the_log_when_asked(self):
        """One tab per operation that has actually happened, with how many.
        A tab for every feature would be a row of mostly empty tabs, and an
        empty tab teaches you not to trust the row. Built when asked, not at
        import: History is itself a task being imported, so at import time it
        would see almost nothing."""
        offered = [c["label"] for c in R.get("history").options[0].describe()["choices"]]
        self.assertEqual(offered, ["Everything"])        # nothing has run yet

        runlog.record("cull", {}, WhatWasActuallyDone.Done(1))
        runlog.record("cull", {}, WhatWasActuallyDone.Done(2))
        runlog.record("unpair", {}, WhatWasActuallyDone.Done(1))
        offered = [c["label"] for c in R.get("history").options[0].describe()["choices"]]
        self.assertIn("Everything (3)", offered)
        self.assertIn("Cull by rating (2)", offered)
        self.assertIn("Separate RAWs (1)", offered)
        self.assertFalse(any("Find duplicates" in o for o in offered))   # never run

    def test_and_they_are_drawn_as_tabs_not_a_dropdown(self):
        """It is a view of the same answer, not a setting - a dropdown hides the
        options you did not pick and makes looking at each in turn three
        clicks."""
        self.assertTrue(R.get("history").options[0].describe()["tabs"])


if __name__ == "__main__":
    unittest.main()
