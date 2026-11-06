"""The workflow running itself - and the four ways that could be a disaster.

An automation is a feature you stop watching. That is the point of it and it is
also the whole risk: every other tab in this app is read before it is pressed,
and this one is not read at all after the first week. So what is tested here is
not "does the chain work" - it does, and one test covers it - but the ways it
could go wrong while looking fine:

- **running when nothing has changed**, forever, reading the whole library every
  quarter of an hour for nothing;
- **NOT running when something has**, which is the failure that looks identical
  to working until the day you notice the tablet has been empty for a month.
  The specific case is a rating written into a sidecar that already existed: the
  folder's own date does not move, and the obvious cheap watch cannot see it;
- **marking itself up to date after a step that failed**, or after a step that
  only reported - either of which loses the work silently;
- **eating itself**, if the exports folder is the develop tree: send a photo
  out, have it filed back in as a finished export, marked developed, taken off
  the tablet, and around again on a timer.
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
from app.tasks import automation as T      # noqa: E402
from core import automation as A           # noqa: E402
from core import flows as F                # noqa: E402
from core import settings as S             # noqa: E402
from core.exifwrite import set_rating      # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Loop(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="auto-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.previews = os.path.join(self.dir, "Previews")
        self.develop = os.path.join(self.dir, "Develop")
        self.inbox = os.path.join(self.dir, "Inbox")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        self.pshoot = os.path.join(self.previews, "2022", "Spain")
        for x in (self.shoot, self.pshoot, self.develop, self.inbox):
            os.makedirs(x)
        for n in ("plain", "rated"):
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(self.shoot, n + ".JPG"))
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(self.pshoot, n + ".JPG"))
        S.save({"library": self.lib, "previews": self.previews, "raw": "",
                "develop": self.develop, "inbox": self.inbox})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def pass_now(self, **over):
        if over:
            S.save(over)
        return {r["key"]: r for r in T.one_pass()}

    # The developing loop is a FLOW now rather than three steps in the source,
    # so these reach in and change the flow rather than the settings file.
    def flow(self):
        return F.read()[0]

    def set_step(self, task, **over):
        f = self.flow()
        for step in f.steps:
            if step.task == task:
                for key, value in over.items():
                    setattr(step, key, value)
        F.write([f])
        return f

    def set_flow(self, **over):
        f = self.flow()
        for key, value in over.items():
            setattr(f, key, value)
        F.write([f])
        return f


class NoticingAChange(Loop):
    def test_a_tree_that_has_not_moved_looks_the_same(self):
        one = A.fingerprint(self.lib)
        two = A.fingerprint(self.lib)
        self.assertEqual(one.mark, two.mark)
        self.assertTrue(one.mark)

    def test_a_new_file_is_noticed(self):
        one = A.fingerprint(self.lib)
        shutil.copy(os.path.join(FIX, "aeb1.jpg"),
                    os.path.join(self.shoot, "new.JPG"))
        self.assertNotEqual(one.mark, A.fingerprint(self.lib).mark)

    def test_a_file_that_has_gone_is_noticed(self):
        one = A.fingerprint(self.lib)
        os.remove(os.path.join(self.shoot, "plain.JPG"))
        self.assertNotEqual(one.mark, A.fingerprint(self.lib).mark)

    def rated_outside(self, stars=5):
        """What another program does when you rate a photograph.

        Deliberately not this app's own writer: that one puts the file's date
        back afterwards on purpose, so its writes are invisible here - which is
        a property worth having and is tested on its own below. Lightroom,
        Photos and darktable all just write the file.
        """
        side = os.path.join(self.pshoot, "plain.xmp")
        with open(side, "w", encoding="utf-8") as fh:
            fh.write('<?xpacket?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
                     '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                     '<rdf:Description rdf:about="" '
                     'xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
                     f'xmp:Rating="{stars}"/></rdf:RDF></x:xmpmeta>')
        return side

    def test_a_rating_written_into_an_existing_sidecar_is_noticed(self):
        """THE case. Rating a photograph in Lightroom rewrites a sidecar that is
        already there: the folder's own date does not move, so the cheap watch
        cannot see it - and this is the single change the whole workflow hangs
        on."""
        self.rated_outside(3)
        one = A.fingerprint(self.previews)
        was = os.stat(self.pshoot).st_mtime_ns
        self.rated_outside(5)
        os.utime(self.pshoot, ns=(was, was))  # the folder date, put back as it was
        self.assertNotEqual(one.mark, A.fingerprint(self.previews).mark,
                            "an edited sidecar went unnoticed")

    def test_and_the_cheap_watch_says_so_by_failing_at_exactly_that(self):
        """Kept as a test rather than a comment: the shallow mode is offered,
        and what it cannot do has to stay true or the help text is a lie."""
        self.rated_outside(3)
        one = A.fingerprint(self.previews, deep=False)
        was = os.stat(self.pshoot).st_mtime_ns
        self.rated_outside(5)
        os.utime(self.pshoot, ns=(was, was))
        self.assertEqual(one.mark, A.fingerprint(self.previews, deep=False).mark)

    def test_the_cheap_watch_still_notices_a_file_arriving(self):
        """Which is its whole claim. Blind to a file being EDITED is a trade it
        is offered on; blind to a shoot appearing would make it useless and the
        help text a lie."""
        one = A.fingerprint(self.previews, deep=False)
        shutil.copy(os.path.join(FIX, "aeb1.jpg"),
                    os.path.join(self.pshoot, "new.JPG"))
        self.assertNotEqual(one.mark,
                            A.fingerprint(self.previews, deep=False).mark)

    def test_and_a_folder_being_renamed_under_it(self):
        one = A.fingerprint(self.previews, deep=False)
        os.rename(self.pshoot, self.pshoot + " again")
        self.assertNotEqual(one.mark,
                            A.fingerprint(self.previews, deep=False).mark)

    def test_this_apps_own_writes_do_not_move_a_files_date(self):
        """Which is deliberate everywhere in this app - a library should not look
        freshly touched because a rating was copied onto it - and is why nothing
        in the chain relies on a step noticing its own work. Whether the tree
        looks different at all then comes down to whether the size moved, which
        is not a thing to build on either way, so the chain carries "something
        earlier wrote" forwards instead."""
        where = os.path.join(self.shoot, "plain.JPG")
        was = os.stat(where).st_mtime
        set_rating(where, 4)
        self.assertEqual(os.stat(where).st_mtime, was)

    def test_a_sidecar_rewritten_in_the_same_second_at_the_same_size_is_noticed(self):
        """Not a corner case: Lightroom rewriting a rating seconds after the
        last look, four bytes different in the same number of bytes. Count,
        folders and size all identical - and one photograph that should have
        gone to the tablet and never would."""
        self.rated_outside(3)
        one = A.fingerprint(self.previews)
        self.rated_outside(4)                 # same length, same second
        self.assertNotEqual(one.mark, A.fingerprint(self.previews).mark)

    def test_a_tree_that_is_not_there_is_never_called_changed(self):
        """Missing is a thing to say out loud, not a reason to run a sync
        against nothing."""
        look = A.fingerprint(os.path.join(self.dir, "nowhere"))
        self.assertFalse(look.there)
        self.assertFalse(A.changed("x", look))

    def test_what_it_saw_is_remembered_and_then_it_is_not_changed(self):
        look = A.fingerprint(self.lib)
        self.assertTrue(A.changed("mine", look))
        A.remember("mine", look, "did a thing", ran=True)
        self.assertFalse(A.changed("mine", A.fingerprint(self.lib)))


class TheChain(Loop):
    def test_the_first_pass_does_the_work_and_the_second_does_nothing(self):
        first = self.pass_now()
        self.assertTrue(first["develop"]["ran"])
        second = self.pass_now()
        self.assertFalse(second["develop"]["ran"])
        self.assertIn("nothing has changed", second["develop"]["said"])

    def test_a_rating_on_the_tablet_reaches_the_develop_tree_in_one_pass(self):
        """Not in two. A rating and the copy it should have caused being one
        interval apart is how a workflow comes to feel like it lags behind
        you."""
        self.pass_now()                                  # settle
        set_rating(os.path.join(self.pshoot, "plain.JPG"), 5)
        got = self.pass_now()
        self.assertTrue(got["ratings"]["ran"], got["ratings"]["said"])
        self.assertTrue(got["develop"]["ran"], got["develop"]["said"])
        self.assertTrue(any("plain" in f for f in
                            os.listdir(os.path.join(self.develop, "2022", "Spain"))))

    def test_the_chain_carries_on_even_when_the_tree_says_nothing_changed(self):
        """The "something earlier wrote" flag, on its own.

        Usually the library HAS visibly changed by the time sending to develop
        is reached - rewriting a file moves its folder's date, if nothing else -
        so the flag is belt and braces most of the time. It stops being belt and
        braces the moment a write leaves a tree looking identical, and then it
        is the only thing standing between a five-star photograph and never
        being sent. So it is tested for what it is: with the watch saying
        nothing has changed, a step after one that wrote still runs.
        """
        real = A.changed
        A.changed = lambda key, look, state=None: key == "ratings"
        try:
            set_rating(os.path.join(self.pshoot, "plain.JPG"), 5)
            got = self.pass_now()
        finally:
            A.changed = real
        self.assertTrue(got["ratings"]["ran"], got["ratings"]["said"])
        self.assertTrue(got["develop"]["ran"],
                        f"the chain stopped: {got['develop']['said']}")

    def test_filing_uses_the_folder_name_from_setup_not_its_own_default(self):
        """The background run fills each task's form from Setup. Leave one field
        out and it silently falls back to the option's default - so a name typed
        on the tab is not the name used at four in the morning, and exports
        start landing in two different folders. Found months later, if at all.
        """
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(self.inbox, "plain.jpg"))
        self.set_step("filed", do="run")
        got = self.pass_now(filed_into="Curated")
        self.assertTrue(got["filed"]["ran"], got["filed"]["said"])
        self.assertTrue(os.path.isfile(
            os.path.join(self.shoot, "Curated", "plain.jpg")),
            os.listdir(self.shoot))

    def test_a_step_switched_off_is_not_run_at_all(self):
        self.set_step("develop", on=False)
        got = self.pass_now()
        self.assertNotIn("develop", got)
        self.assertFalse(os.path.isdir(os.path.join(self.develop, "2022")))

    def test_a_step_set_to_report_does_not_do_it(self):
        self.set_step("develop", do="report")
        got = self.pass_now()
        self.assertFalse(got["develop"]["ran"])
        self.assertIn("waiting", got["develop"]["said"])
        self.assertFalse(os.path.isdir(os.path.join(self.develop, "2022")))

    def test_and_says_it_again_next_time_rather_than_going_quiet(self):
        """A step that only reported has not caught up with its tree. Marking it
        up to date would mean the waiting work is mentioned once, ever."""
        self.set_step("develop", do="report")
        first = self.pass_now()
        second = self.pass_now()
        self.assertIn("waiting", first["develop"]["said"])
        self.assertIn("waiting", second["develop"]["said"])

    def test_filing_reports_by_default_because_it_moves_things(self):
        filed = [s for s in self.flow().steps if s.task == "filed"][0]
        self.assertEqual(filed.do, "report")

    def test_a_step_that_cannot_run_says_why_and_the_others_still_go(self):
        S.save({"previews": os.path.join(self.dir, "nowhere")})
        got = self.pass_now()
        self.assertIn("is not there", got["ratings"]["said"])
        self.assertTrue(got["develop"]["ran"])


class WhatItRefuses(Loop):
    def test_the_exports_folder_being_the_develop_tree_stops_everything(self):
        """Send a photograph out to develop, have filing move it into the
        library as a finished export, mark it developed, take the original off
        the tablet - and round again every pass. Every step doing exactly what
        it was told."""
        S.save({"inbox": self.develop})
        got = T.one_pass()
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0]["failed"])
        self.assertIn("round again", got[0]["said"])

    def test_and_the_tab_refuses_before_showing_a_plan_at_all(self):
        S.save({"inbox": os.path.join(self.develop, "back")})
        os.makedirs(os.path.join(self.develop, "back"))
        t = R.get("automation")
        p = t.make_plan({})
        self.assertTrue(p.blocked)
        self.assertIn("round again", p.blocked)

    def test_nothing_is_marked_up_to_date_when_a_step_failed(self):
        """Otherwise a failure is also a decision never to try again."""
        task = R.get("develop")
        real = task.apply

        class Bad:
            done, failed, cancelled, stats, details = 0, 3, False, [], []

        task.apply = lambda *a, **k: Bad()
        try:
            self.pass_now()
        finally:
            task.apply = real
        self.assertTrue(A.changed("develop", A.fingerprint(self.lib)))


class NothingIsLeftToItsDefault(Loop):
    """The bug that has now happened twice, made impossible a third time.

    A background run fills each task's form itself. Leave one field out and it
    silently falls back to the OPTION's default - so what you set on the tab is
    not what runs at four in the morning, the tab shows one thing, the loop does
    another, and neither says a word. It happened to the developed folder name,
    and then to every one of Send to develop's criteria: the rating thresholds,
    the tag filter and the colour filter were all ignored by the automation.

    So this walks every step and insists that each option a task declares is
    either passed explicitly or backed by a Setup setting. Both are fine - what
    is not fine is an option whose value in a background run came from a default
    nobody can see.
    """

    def test_a_step_with_no_overrides_runs_exactly_as_its_own_tab_would(self):
        """The invariant that replaces the old sweep, and a stronger one.

        A step used to carry a hand-written copy of the options to pass, and the
        bug was always the same shape: one was forgotten, so the threshold on
        the tab was not the threshold that ran. A step now passes only its
        OVERRIDES and lets the task's own `coerce` do the rest - which is the
        same code path the tab uses - so the two cannot disagree unless this
        assertion fails.
        """
        S.save({"develop_raw_at": 2, "develop_jpeg_at": 1,
                "filed_into": "Curated"})
        for step in self.flow().steps:
            task = R.get(step.task)
            self.assertEqual(task.coerce(F.raw_for(task, step)),
                             task.coerce({}),
                             f"{step.task} in a flow would not run as its tab does")

    def test_every_option_of_every_step_is_reported_somewhere_you_can_see(self):
        """The old guard insisted every option was either passed explicitly or
        backed by a Setup setting, because anything else came from a default
        nobody could see. The editor answers that better: it reports the
        effective value of EVERY option and which of the three places it came
        from, so there is nowhere left for a value to hide. What has to stay
        true is that the report is COMPLETE."""
        saved = S.load()
        for step in self.flow().steps:
            task = R.get(step.task)
            effective = F.options_for(task, step, saved)
            for o in task.options:
                self.assertIn(o.name, effective,
                              f"{step.task}.{o.name} is not reported anywhere")
                self.assertEqual(effective[o.name]["value"],
                                 task.coerce(F.raw_for(task, step))[o.name]
                                 if o.name in task.coerce({}) else
                                 effective[o.name]["value"])

    def test_and_the_editor_shows_where_every_single_value_came_from(self):
        """The other half, and the better answer: a step now reports the
        effective value of EVERY option it has and which of the three places it
        came from. Nothing invisible is possible if nothing is unreported."""
        saved = S.load()
        for step in self.flow().steps:
            task = R.get(step.task)
            effective = F.options_for(task, step, saved)
            self.assertEqual(set(effective), {o.name for o in task.options},
                             f"{step.task} does not report all its options")
            for name, said in effective.items():
                self.assertIn(said["from"], ("step", "setup", "default"))

    def test_and_what_a_step_overrides_is_a_real_option_of_that_task(self):
        """The other half of the same mistake: a key the task has never heard
        of is accepted in silence by `coerce` and does nothing at all."""
        for step in self.flow().steps:
            task = R.get(step.task)
            known = {o.name for o in task.options}
            for name in F.raw_for(task, step):
                self.assertIn(name, known, f"{step.task} overrides {name!r}, "
                                           f"which {task.name} does not have")

    def test_the_develop_criteria_actually_reach_the_background_run(self):
        """Named rather than left to the sweep above, because this is the one
        that was wrong: five stars is the default, so a threshold of three
        looked identical to a forgotten one."""
        S.save({"develop_raw_at": 2, "develop_jpeg_at": 1})
        step = [x for x in self.flow().steps if x.task == "develop"][0]
        task = R.get("develop")
        opts = task.coerce(F.raw_for(task, step))
        self.assertEqual(int(opts["raw_at_or_above"]), 2)
        self.assertEqual(int(opts["jpeg_at_or_above"]), 1)

    def test_and_a_colour_chosen_in_setup_narrows_the_background_send(self):
        S.save({"label_green_name": "Timelapse", "develop_colour": "green"})
        step = [x for x in self.flow().steps if x.task == "develop"][0]
        task = R.get("develop")
        self.assertEqual(task.coerce(F.raw_for(task, step))["colour"], "green")

    def test_a_step_override_beats_setup_and_says_so(self):
        """The point of a per-step setting: the same feature twice in one flow,
        with different thresholds, and each one saying where its value is from."""
        S.save({"develop_jpeg_at": 4})
        step = [x for x in self.flow().steps if x.task == "develop"][0]
        step.opts = {"jpeg_at_or_above": 2}
        task = R.get("develop")
        self.assertEqual(int(task.coerce(F.raw_for(task, step))
                             ["jpeg_at_or_above"]), 2)
        said = F.options_for(task, step, S.load())
        self.assertEqual(said["jpeg_at_or_above"]["from"], "step")
        self.assertEqual(said["raw_at_or_above"]["from"], "setup")


class ShowingItself(Loop):
    """The app could read the whole library every fifteen minutes while the page
    said nothing at all - the bar at the top is fed by the job list, and a
    background pass never became a job. That is not a missing feature so much as
    the one kind of run you cannot see happening."""

    def test_a_background_step_becomes_a_job_like_any_other(self):
        from app import server as srv
        before = set(srv.JOBS)
        self.pass_now()
        made = [srv.JOBS[k] for k in set(srv.JOBS) - before]
        self.assertTrue(made, "nothing was registered, so the bar cannot show it")
        self.assertTrue(all(j.by == "automation" for j in made),
                        "a background run is not marked as one")

    def test_and_is_marked_as_started_by_automation_not_by_you(self):
        """Which is the only interesting thing about it: the runs you pressed
        you already know about."""
        self.pass_now()
        from core import runlog
        rows = [r for r in runlog.recent(limit=20) if r.get("done")]
        self.assertTrue(rows)
        self.assertTrue(all(r.get("by") == "automation" for r in rows))

    def test_what_it_cost_is_recorded_with_it(self):
        self.pass_now()
        from core import runlog
        rows = [r for r in runlog.recent(limit=20)
                if r.get("by") == "automation" and r.get("done")]
        self.assertTrue(rows)
        self.assertIn("seconds", rows[0].get("cost") or {})

    def test_the_server_knows_when_it_last_did_something(self):
        """Which is what the unread mark counts. It must be DID something - a
        pass that looked and found nothing changed is the normal state, and a
        mark that lights up for those is one you stop seeing in a week."""
        from app import server as srv
        srv.AUTO_RESULTS.clear()
        self.pass_now()                       # the first pass sends something
        self.assertEqual(len(srv.AUTO_RESULTS), 1)
        self.pass_now()                       # nothing has changed since
        self.assertEqual(len(srv.AUTO_RESULTS), 1,
                         "a quiet pass lit the unread mark")

    def _a_job(self, task_name, raw):
        from app import server as srv
        t = R.get(task_name)
        job = srv.remember(srv.Job(t, plan=t.make_plan(raw)))
        job.by = "automation"
        return srv, job

    def test_a_run_that_did_nothing_does_not_light_the_mark(self):
        """Reached directly, because a pass that finds nothing changed never
        gets as far as running - so the one case that matters here is a run
        that DID happen and turned out to have nothing to do. Clean up with the
        confirmation unticked is exactly that, and is real rather than
        contrived."""
        os.makedirs(os.path.join(self.lib, "2022", "Spain", "_Culled"),
                    exist_ok=True)
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(self.lib, "2022", "Spain", "_Culled", "x.JPG"))
        srv, job = self._a_job("cleanup", {"folder": self.lib, "raw": "",
                                           "previews": "", "develop": "",
                                           "recycle": False})
        srv.AUTO_RESULTS.clear()
        job.run()
        self.assertEqual(job.result.done, 0, "the fixture no longer does nothing")
        self.assertEqual(srv.AUTO_RESULTS, [],
                         "a run that did nothing lit the unread mark")

    def test_and_one_that_did_something_does(self):
        os.makedirs(os.path.join(self.lib, "2022", "Spain", "_Culled"),
                    exist_ok=True)
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(self.lib, "2022", "Spain", "_Culled", "x.JPG"))
        srv, job = self._a_job("cleanup", {"folder": self.lib, "raw": "",
                                           "previews": "", "develop": "",
                                           "recycle": False, "confirm": True})
        srv.AUTO_RESULTS.clear()
        job.run()
        self.assertGreater(job.result.done, 0, "the fixture no longer does anything")
        self.assertEqual(len(srv.AUTO_RESULTS), 1)

    def test_and_remembers_them_across_a_restart(self):
        """Seeded from the log, so restarting the container does not silently
        mark everything as read."""
        from app import server as srv
        self.pass_now()
        srv.AUTO_RESULTS.clear()
        self.assertGreaterEqual(srv.seed_automation_results(), 1)


class TheTab(Loop):
    def test_it_shows_a_row_per_step_with_what_it_watches(self):
        t = R.get("automation")
        p = t.make_plan({})
        self.assertEqual(len(p.rows), len(self.flow().steps))
        self.assertIn("The previews tree", p.rows[0].cells)

    def test_the_button_runs_the_flow_it_is_showing(self):
        """One pass, through the same machinery that runs on its own, so what
        you watch here is exactly what happens at four in the morning."""
        t = R.get("automation")
        p = t.make_plan({})
        result = t.apply(p)
        self.assertTrue(os.path.isdir(os.path.join(self.develop, "2022")))
        self.assertTrue(result.details)
        self.assertEqual(dict(result.stats)["Flow"], "Developing loop")

    def test_and_it_changes_no_settings_of_its_own(self):
        """Running a flow is not editing it. The Flows tab is where a flow is
        changed, and a button that quietly saved as well would mean the thing
        you ran and the thing you saved could differ."""
        before = self.flow()
        t = R.get("automation")
        t.apply(t.make_plan({}))
        after = self.flow()
        self.assertEqual([(s.task, s.on, s.do) for s in before.steps],
                         [(s.task, s.on, s.do) for s in after.steps])
        self.assertEqual(before.on, after.on)

    def test_the_background_loop_reads_the_flows_every_time_it_wakes(self):
        """An app you have to restart to change a schedule is an app whose
        schedule is whatever it was the day you set it up."""
        import inspect
        from app import server
        source = inspect.getsource(server.automation_loop)
        self.assertIn("_f.read()", source)
        self.assertIn("while", source)

    def test_and_leaves_a_flow_that_dsm_fires_alone(self):
        """Two things firing one flow is two passes moving the same photographs
        past each other."""
        import inspect
        from app import server
        source = inspect.getsource(server.automation_loop)
        self.assertIn("BY_APP", source)

    def test_and_never_dies_on_an_error(self):
        """A background thread that dies takes the automation with it and says
        nothing - the exact failure this feature exists to avoid."""
        import inspect
        from app import server
        source = inspect.getsource(server.automation_loop)
        self.assertIn("except Exception", source)

    def test_ago_reads_like_a_person_would_say_it(self):
        self.assertEqual(A.ago(0), "never")
        self.assertIn("minutes ago", A.ago(time.time() - 600))
        self.assertIn("hours ago", A.ago(time.time() - 7200))
        self.assertEqual(A.ago(time.time() - 100), "1 minute ago")



class TheButtonCountsSteps(Loop):
    def test_one_flow_of_several_steps_is_not_several_flows(self):
        """It read "Run 3 flows" for one flow of three steps."""
        t = R.get("automation")
        p = t.make_plan({})
        got = R.impact_of(t, p)
        self.assertEqual(got["count"], len(self.flow().live()))
        self.assertIn(got["unit"], ("step", "steps"))



class StoppingAPass(Loop):
    """Stop on "Run one pass now" stopped the bar and not the pass: the flow
    went on starting its remaining steps, which move files."""

    def setUp(self):
        super().setUp()
        from app import server as srv
        ran = self.ran = []

        class Step:
            """A step with one thing to do, standing in for the real job."""
            def __init__(self, task, raw=None, plan=None):
                self.task, self.id, self.by = task, task.name, ""
                self.cancel, self.error, self.cost = False, "", {}
                self.plan = self.result = None
                self.cancel_seen = None

            def progress(self, i, n, name, status="OK"):
                pass

            def look(self):
                self.plan = R.Plan(task=self.task.name, rows=[R.Row(name="x")])

            def run(self):
                self.progress(0, 1, "x")
                self.cancel_seen = self.cancel
                ran.append(self)
                self.result = R.Result(done=1)

        real, remember = srv.Job, srv.remember
        srv.Job, srv.remember = Step, (lambda job: job)
        self.addCleanup(setattr, srv, "Job", real)
        self.addCleanup(setattr, srv, "remember", remember)
        f = self.flow()
        for step in f.steps:
            step.on, step.do = True, "run"
        F.write([f])

    def test_without_stop_every_step_runs(self):
        """The cases below are only a test if this one holds."""
        T.one_pass()
        self.assertEqual(len(self.ran), len(self.flow().live()))
        self.assertGreater(len(self.ran), 1)

    def test_stop_after_the_first_step_runs_nothing_more(self):
        t = R.get("automation")
        result = t.apply(t.make_plan({}), cancelled=lambda: bool(self.ran))
        self.assertEqual(len(self.ran), 1)
        self.assertTrue(result.cancelled)
        self.assertTrue(any("not started" in d for d in result.details),
                        result.details)

    def test_stop_reaches_the_step_that_is_running(self):
        """Handed on to the step's own job, which reads it between rows."""
        state = {"calls": 0}

        def soon():
            # Not yet at the check before the step; yes once it is running.
            state["calls"] += 1
            return state["calls"] > 1
        T.one_pass(cancelled=soon)
        self.assertEqual(len(self.ran), 1)
        self.assertTrue(self.ran[0].cancel_seen)

if __name__ == "__main__":
    unittest.main()
