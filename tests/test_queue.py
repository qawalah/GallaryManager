"""Work a step found and did not do, offered again with somewhere to press.

Filing exports reports by default, on purpose: it is the one step that MOVES
finished photographs into the library, so a wrong answer is a photograph
somewhere you did not put it. Sending to develop can be set the same way.

The consequence was a sentence with no button under it. A pass at four in the
morning would find 194 photographs ready, write "194 waiting - open the Send to
develop tab" into a log, and then say exactly that again every fifteen minutes
for a week. The information was there; there was nothing to do about it from the
tab you were looking at.

So a pass writes down what it left, the Automation tab shows it as a queue, and
Apply runs that one step - for that press only. Not by changing the setting:
promoting filing to "run" for ever because you once said yes to 194 exports is
precisely the silent change this app does not make.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R                 # noqa: E402
import app.tasks                              # noqa: E402,F401
from app.tasks import automation as AUTO      # noqa: E402
from core import automation as A              # noqa: E402
from core import flows as FL                  # noqa: E402
from core import settings as S                # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Queue(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="queue-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.prev = os.path.join(self.dir, "Previews")
        self.dev = os.path.join(self.dir, "Develop")
        self.inbox = os.path.join(self.dir, "Exports")
        for d in (self.lib, self.prev, self.dev, self.inbox):
            os.makedirs(d)
        S.save({"library": self.lib, "previews": self.prev,
                "develop": self.dev, "inbox": self.inbox})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def tab(self, **over):
        return R.get("automation").make_plan(over)

    def only(self, task, do="run", **flowbits):
        """A one-step flow, so a test is about the step it names and nothing else."""
        f = FL.read()[0]
        f.steps = [s for s in f.steps if s.task == task]
        for s in f.steps:
            s.on, s.do = True, do
        for k, v in flowbits.items():
            setattr(f, k, v)
        FL.write([f])
        return f

    # ------------------------------------------------------- writing it down

    def test_a_pass_that_only_reported_leaves_the_count_behind(self):
        A.waiting("develop", 194, title="Send out to develop",
                  task="Send to develop")
        self.assertEqual(A.last("develop").get("waiting"), 194)

    def test_and_it_does_not_mark_the_tree_up_to_date(self):
        """The correctness argument. Recording the mark would mean the next pass
        says "nothing has changed" and the waiting work is never mentioned
        again - which is the bug, not the fix."""
        look = A.fingerprint(self.lib)
        A.waiting("develop", 194)
        self.assertTrue(A.changed("develop", look))

    def test_doing_the_work_clears_it(self):
        A.waiting("develop", 194)
        A.waiting("develop", 0)
        self.assertNotIn("waiting", A.last("develop"))

    def test_it_remembers_when_the_work_first_appeared(self):
        """"194 waiting" and "194 waiting since Tuesday" are different facts,
        and only the second one tells you the loop is stuck."""
        A.waiting("develop", 194)
        first = A.last("develop")["waiting_since"]
        A.waiting("develop", 210)
        self.assertEqual(A.last("develop")["waiting_since"], first)

    # -------------------------------------------------------- showing it

    def test_the_tab_shows_the_queue_with_a_button(self):
        A.waiting("develop", 194, title="Send out to develop",
                  task="Send to develop")
        p = self.tab()
        self.assertEqual(dict(p.stats)["WAITING ON YOU"], "194")
        actions = [a for g in p.groups for a in g.get("actions", [])]
        self.assertTrue(actions, "nothing to press")
        self.assertEqual(actions[0]["option"], "apply_now")
        self.assertEqual(actions[0]["value"], "develop")

    def test_and_says_nothing_is_waiting_when_nothing_is(self):
        p = self.tab()
        self.assertEqual(dict(p.stats)["WAITING ON YOU"], "nothing")
        self.assertFalse([a for g in p.groups for a in g.get("actions", [])])

    def test_the_queue_is_read_rather_than_worked_out_again(self):
        """Finding out that 194 photographs are ready costs the same as sending
        them, so the tab must not do it to draw a number."""
        A.waiting("filed", 7)
        opened_before = _reads()
        self.tab()
        self.assertLess(_reads() - opened_before, 50,
                        "drawing the queue read the library")

    def test_asking_to_apply_says_plainly_what_this_press_will_do(self):
        A.waiting("filed", 7)
        p = self.tab(apply_now="filed")
        self.assertTrue(any("whatever its" in n for n in p.notes), p.notes)

    # ------------------------------------------------------------- doing it

    def test_apply_runs_that_step_although_it_is_set_to_report(self):
        shutil.copy(os.path.join(FIX, "rated.jpg"),
                    os.path.join(self.lib, "rated.JPG"))
        S.save({"develop_jpeg_at": 1, "develop_raw_at": -1})
        flow = self.only("develop", do="report")
        told = AUTO.one_pass(flow)
        step = [r for r in told if r["key"] == "develop"][0]
        self.assertFalse(step["ran"], step["said"])
        self.assertEqual(A.last("develop").get("waiting"), 1)

        done = AUTO.one_pass(flow, force="develop")
        step = [r for r in done if r["key"] == "develop"][0]
        self.assertTrue(step["ran"], step["said"])
        self.assertNotIn("waiting", A.last("develop"))

    def test_and_does_not_change_the_setting(self):
        """Saying yes to 194 exports once is not saying yes to every export
        from now on - which is what changing the setting would mean."""
        shutil.copy(os.path.join(FIX, "rated.jpg"),
                    os.path.join(self.lib, "rated.JPG"))
        S.save({"develop_jpeg_at": 1, "develop_raw_at": -1})
        flow = self.only("develop", do="report")
        AUTO.one_pass(flow, force="develop")
        after = [s for s in FL.read()[0].steps if s.task == "develop"][0]
        self.assertEqual(after.do, "report")

    def test_applying_is_not_a_setting_the_next_pass_reads(self):
        """apply_now must never be stored on the step, or one press would
        silently promote it for ever."""
        from dataclasses import fields
        self.assertNotIn("apply_now", {f.name for f in fields(FL.Step)})
        self.assertNotIn("apply_now", AUTO.FIELDS)

    def test_a_forced_step_runs_even_when_its_tree_has_not_changed(self):
        """The tree has not moved since the pass that found the work, so the
        ordinary "has anything changed" gate would refuse the press."""
        shutil.copy(os.path.join(FIX, "rated.jpg"),
                    os.path.join(self.lib, "rated.JPG"))
        S.save({"develop_jpeg_at": 1, "develop_raw_at": -1})
        flow = self.only("develop", do="run")
        AUTO.one_pass(flow)                        # catches up, marks it seen
        again = AUTO.one_pass(flow, force="develop")
        step = [r for r in again if r["key"] == "develop"][0]
        self.assertNotIn("nothing has changed", step["said"])


class TheUnreadMark(Queue):
    """It counted timestamps and said nothing about them, which is most of the
    way to useless: "3" tells you to go and look, and the whole point of a mark
    is to save you going to look at a pass that moved four sidecars."""

    def setUp(self):
        super().setUp()
        from app import server as srv
        self.srv = srv
        srv.AUTO_RESULTS.clear()

    def tearDown(self):
        self.srv.AUTO_RESULTS.clear()
        super().tearDown()

    def test_a_run_that_did_something_is_recorded_with_what_it_did(self):
        self.srv.note_automation_result(1.0, "develop", "Send to develop", 194, 2)
        got = self.srv.AUTO_RESULTS[-1]
        self.assertEqual(got["title"], "Send to develop")
        self.assertEqual(got["done"], 194)
        self.assertEqual(got["failed"], 2)

    def test_a_real_background_run_records_it_too(self):
        """Reached through the job, not by calling the recorder, because the
        thing that was broken was the wiring rather than the shape."""
        import shutil
        shutil.copy(os.path.join(FIX, "rated.jpg"),
                    os.path.join(self.lib, "rated.JPG"))
        S.save({"develop_jpeg_at": 1, "develop_raw_at": -1})
        flow = self.only("develop", do="run")
        AUTO.one_pass(flow)
        said = [r for r in self.srv.AUTO_RESULTS if r["task"] == "develop"]
        self.assertTrue(said, "a background run that did something was not noted")
        self.assertGreater(said[-1]["done"], 0)
        self.assertTrue(said[-1]["title"])

    def test_a_quiet_pass_is_not_recorded_at_all(self):
        """A pass that looked and found nothing changed is the normal state and
        there are hundreds of them. A mark lit by those is one you stop seeing
        in a week."""
        flow = self.only("develop", do="run")
        AUTO.one_pass(flow)
        before = len(self.srv.AUTO_RESULTS)
        AUTO.one_pass(flow)
        self.assertEqual(len(self.srv.AUTO_RESULTS), before)

    def test_the_page_is_given_what_each_run_did(self):
        from app import page as P
        self.assertIn("saidRuns", P.PAGE)
        self.assertIn("did something", P.PAGE)

    def test_and_what_is_seeded_from_the_log_has_the_same_shape(self):
        """Otherwise a restart turns every remembered run into a bare number
        again, which is the bug coming back through the back door."""
        import shutil
        shutil.copy(os.path.join(FIX, "rated.jpg"),
                    os.path.join(self.lib, "rated.JPG"))
        S.save({"develop_jpeg_at": 1, "develop_raw_at": -1})
        AUTO.one_pass(self.only("develop", do="run"))
        self.srv.AUTO_RESULTS.clear()
        self.srv.seed_automation_results()
        self.assertTrue(self.srv.AUTO_RESULTS)
        for one in self.srv.AUTO_RESULTS:
            self.assertIn("title", one)
            self.assertIn("done", one)


def _reads() -> int:
    from core import meter
    return meter.snapshot()["own_files"]


if __name__ == "__main__":
    unittest.main()
