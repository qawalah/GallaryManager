"""Putting a run back.

The dangerous half is not the moving, it is the refusing. A button that says
Undo and drags a photograph backwards over something you did afterwards has lost
you an afternoon, and it did it while looking like it was helping. So most of
what is held here is about what it declines to touch.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R                # noqa: E402
import app.tasks                             # noqa: E402,F401
from core import moves as M                  # noqa: E402
from core import runlog                      # noqa: E402


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="undo-")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        self.a = os.path.join(self.home, "A")
        self.b = os.path.join(self.home, "B")
        os.makedirs(self.a)
        os.makedirs(self.b)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def file(self, folder, name, text="x"):
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path


class RecordingAMove(_Tmp):
    def test_a_move_says_where_the_file_actually_landed(self):
        """Not where it was aimed. A name already taken gets a number, and a
        record of the intended path would put the wrong file back."""
        one = self.file(self.a, "x.jpg")
        self.file(self.b, "x.jpg")
        result = R.Result()
        where = M.shift(result, one, os.path.join(self.b, "x.jpg"))
        self.assertTrue(os.path.basename(where).startswith("x_"))
        self.assertEqual(result.moves, [[one, where]])
        self.assertFalse(os.path.exists(one))

    def test_it_never_fails_a_run_because_the_record_could_not_be_kept(self):
        one = self.file(self.a, "x.jpg")
        M.note(None, one, "/wherever")            # no result at all
        M.shift(R.Result(), one, os.path.join(self.b, "x.jpg"))
        self.assertTrue(os.path.exists(os.path.join(self.b, "x.jpg")))

    def test_the_log_keeps_them(self):
        result = R.Result(done=1)
        result.moves = [["/a/x.jpg", "/b/x.jpg"]]
        runlog.record("bydate", {}, result)
        got = runlog.recent(limit=1)[0]
        self.assertEqual(got["moves"], [["/a/x.jpg", "/b/x.jpg"]])
        self.assertIsNotNone(runlog.one(got["when"]))


class PuttingItBack(_Tmp):
    def moved_run(self, many=3):
        result = R.Result()
        for i in range(many):
            one = self.file(self.a, f"p{i}.jpg", f"body {i}")
            M.shift(result, one, os.path.join(self.b, f"p{i}.jpg"))
        result.done = many
        return runlog.record("bydate", {}, result)

    def test_every_file_goes_back_where_it_came_from(self):
        run = self.moved_run()
        task = R.get("undo")
        plan = task.make_plan({"run": f"{run['when']:.3f}"})
        self.assertFalse(plan.blocked)
        self.assertEqual(len(plan.rows), 3)
        out = task.apply(plan)
        self.assertEqual(out.done, 3)
        for i in range(3):
            self.assertTrue(os.path.isfile(os.path.join(self.a, f"p{i}.jpg")))
            self.assertFalse(os.path.exists(os.path.join(self.b, f"p{i}.jpg")))

    def test_it_is_a_plan_before_it_is_an_action(self):
        """Nothing moves until Apply - the same bargain as everything else."""
        run = self.moved_run()
        R.get("undo").make_plan({"run": f"{run['when']:.3f}"})
        self.assertTrue(os.path.isfile(os.path.join(self.b, "p0.jpg")))

    def test_a_file_that_moved_since_is_left_exactly_as_it_is(self):
        """The whole point. It has been touched by something else, and dragging
        it backwards would undo that instead."""
        run = self.moved_run()
        later = os.path.join(self.home, "C")
        os.makedirs(later)
        shutil.move(os.path.join(self.b, "p1.jpg"), os.path.join(later, "p1.jpg"))
        task = R.get("undo")
        plan = task.make_plan({"run": f"{run['when']:.3f}"})
        self.assertEqual(len(plan.rows), 2)
        self.assertEqual(len(plan.skipped), 1)
        self.assertIn("not where the run left it", plan.skipped[0][1])
        task.apply(plan)
        self.assertTrue(os.path.isfile(os.path.join(later, "p1.jpg")),
                        "it dragged back a file that had moved on")

    def test_nor_one_whose_old_name_is_taken_again(self):
        run = self.moved_run(1)
        self.file(self.a, "p0.jpg", "something else entirely")
        plan = R.get("undo").make_plan({"run": f"{run['when']:.3f}"})
        self.assertEqual(plan.rows, [])
        self.assertIn("already", plan.skipped[0][1])
        with open(os.path.join(self.a, "p0.jpg"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "something else entirely")

    def test_a_run_that_moved_nothing_says_so_rather_than_offering(self):
        result = R.Result(done=40)
        run = runlog.record("tags", {}, result)
        plan = R.get("undo").make_plan({"run": f"{run['when']:.3f}"})
        self.assertIn("did not move any files", plan.blocked)
        self.assertIn("tag", plan.blocked)

    def test_and_asking_for_no_run_at_all_lists_the_ones_it_could_put_back(self):
        """"Pick a run" is only useful next to the runs. Each one is named by
        the number History puts on it, which is the thing somebody can type."""
        self.moved_run(2)
        plan = R.get("undo").make_plan({"run": 0, "no": 0})
        self.assertIn("number", plan.blocked)
        self.assertTrue(plan.rows, "it refused without saying what it could do")
        self.assertTrue(all(r.name.startswith("#") for r in plan.rows),
                        [r.name for r in plan.rows])

    def test_a_run_can_be_put_back_by_the_number_on_it(self):
        """The number is what is on the screen and what a person can say out
        loud; the moment it finished, to the millisecond, is neither."""
        run = self.moved_run(2)
        self.assertTrue(run.get("no"), "the run was not numbered")
        plan = R.get("undo").make_plan({"no": run["no"]})
        self.assertFalse(plan.blocked, plan.blocked)
        self.assertEqual(len(plan.rows), 2)
        self.assertIn(f"#{run['no']}", dict(plan.stats)["Putting back"])

    def test_two_runs_never_share_a_number(self):
        seen = {self.moved_run(1)["no"] for _ in range(3)}
        self.assertEqual(len(seen), 3, seen)

    def test_putting_back_is_itself_a_run_that_can_be_put_back(self):
        run = self.moved_run(2)
        task = R.get("undo")
        out = task.apply(task.make_plan({"run": f"{run['when']:.3f}"}))
        self.assertEqual(len(out.moves), 2)
        again = runlog.record("undo", {}, out)
        back = task.make_plan({"run": f"{again['when']:.3f}"})
        self.assertEqual(len(back.rows), 2)
        task.apply(back)
        self.assertTrue(os.path.isfile(os.path.join(self.b, "p0.jpg")))

    def test_the_newest_move_is_reversed_first(self):
        """A run can move the same file twice - out of the library, then into a
        pile. Reversing in the order it happened would put the first move back
        underneath the second."""
        one = self.file(self.a, "x.jpg")
        result = R.Result()
        first = M.shift(result, one, os.path.join(self.b, "x.jpg"))
        pile = os.path.join(self.home, "pile")
        os.makedirs(pile)
        M.shift(result, first, os.path.join(pile, "x.jpg"))
        out = M.put_back(result.moves, result=R.Result())
        self.assertEqual(out["done"], 2)
        self.assertTrue(os.path.isfile(one))

    def test_history_offers_it_only_where_it_means_something(self):
        self.moved_run(1)
        result = R.Result(done=9)
        runlog.record("tags", {}, result)
        plan = R.get("history").make_plan({})
        acts = [(r.what, bool(r.act)) for r in plan.rows]
        self.assertIn(("bydate", True), acts)
        self.assertIn(("tags", False), acts)
        moved = [r for r in plan.rows if r.act]
        self.assertEqual(moved[0].act["task"], "undo")
        # by the number on the row, which is the thing a person can read out,
        # type themselves and say to somebody else
        self.assertEqual(moved[0].act["option"], "no")
        self.assertEqual(moved[0].name, f"#{moved[0].data['no']}")
        self.assertEqual(moved[0].act["value"], str(moved[0].data["no"]))

    def test_the_history_row_says_what_happened_in_a_word(self):
        """"files: 3 done - a.jpg -> ...@recycle/a.jpg" is true and unreadable."""
        result = R.Result(done=3)
        runlog.record("files", {}, result, action="delete")
        plan = R.get("history").make_plan({})
        said = plan.rows[0].detail
        self.assertIn("Deleted 3 files", said)
        self.assertIn("recycle", said)

    def test_and_every_run_carries_a_number(self):
        for _ in range(3):
            runlog.record("tags", {}, R.Result(done=1))
        plan = R.get("history").make_plan({})
        numbers = [r.name for r in plan.rows]
        self.assertTrue(all(n.startswith("#") for n in numbers), numbers)
        self.assertEqual(len(set(numbers)), len(numbers), numbers)

    def test_the_list_can_be_emptied(self):
        """It is one file on the NAS and every device adds to it; a list that
        can only be trimmed by age is one you cannot clear."""
        for _ in range(4):
            runlog.record("tags", {}, R.Result(done=1))
        task = R.get("forget")
        plan = task.make_plan({"which": "all"})
        self.assertEqual(dict(plan.stats)["Would be forgotten"], "4")
        # nothing has gone yet - it is a plan
        self.assertEqual(len(runlog.read_lines()), 4)
        out = task.apply(plan)
        self.assertEqual(out.done, 4)
        self.assertEqual(runlog.read_lines(), [])

    def test_or_only_the_part_that_has_gone_stale(self):
        import time as _t
        old = runlog.record("tags", {}, R.Result(done=1))
        lines = runlog.read_lines()
        lines[0]["when"] = _t.time() - 40 * 86400
        with open(runlog.store_path(runlog.FILE), "w", encoding="utf-8") as fh:
            import json
            fh.write(json.dumps(lines[0]) + "\n")
        runlog.record("tags", {}, R.Result(done=1))
        task = R.get("forget")
        out = task.apply(task.make_plan({"which": "old", "days": 30}))
        self.assertEqual(out.done, 1)
        left = runlog.read_lines()
        self.assertEqual(len(left), 1)
        self.assertNotEqual(int(left[0]["no"]), int(old["no"]))


if __name__ == "__main__":
    unittest.main()
