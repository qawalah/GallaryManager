"""A flow: some features, in an order, each with its own settings.

The developing loop was three steps written into the source. That was the right
shape and the wrong place - every feature here already declares its options as
data and provides plan-then-apply, so the loop never needed to know which three
they were.

What is tested here is not "can a list hold three names". It is the four things
that make a flow assembled from a dropdown safe to leave running:

- **an upgrade changes nothing.** The old settings become the first flow exactly
  as they were: not switched on, not switched off, and keeping the marks its
  steps already had so the first pass after an upgrade does not run everything
  once for no reason.
- **the order is the chain**, and a step keeps its own identity when moved, or
  the marks shuffle with the positions.
- **a ring is refused.** A step that copies into a tree, followed by one that
  takes things out of there into a tree the first reads, sends the same
  photographs round again on every pass with every step behaving correctly.
- **nothing a step will use is invisible**, which is the fault this replaces: a
  threshold typed on a tab was not the threshold that ran in the background.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R                # noqa: E402
import app.tasks                             # noqa: E402,F401
from app.tasks import flows as FT            # noqa: E402
from core import automation as A             # noqa: E402
from core import flows as F                  # noqa: E402
from core import settings as S               # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Flows(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="flows-")
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


class CarriedOver(Flows):
    def test_the_developing_loop_is_there_without_being_made(self):
        got = F.read()
        self.assertEqual(len(got), 1)
        self.assertEqual([s.task for s in got[0].steps],
                         ["ratings", "develop", "filed"])

    def test_it_keeps_whatever_the_old_settings_said(self):
        """An upgrade must not quietly switch the automation on, nor quietly
        switch it off. Both are changes nobody asked for and one of them starts
        moving photographs."""
        S.save({"auto_on": True, "auto_every": 40, "auto_filed_do": "run",
                "auto_ratings_on": False})
        flow = F.read()[0]
        self.assertTrue(flow.on)
        self.assertEqual(flow.every, 40)
        by = {s.task: s for s in flow.steps}
        self.assertEqual(by["filed"].do, "run")
        self.assertFalse(by["ratings"].on)

    def test_and_keeps_the_marks_its_steps_already_had(self):
        """Otherwise the first pass after an upgrade finds every step
        'changed', and runs all of them once for no reason at all."""
        self.assertEqual([s.id for s in F.read()[0].steps],
                         ["ratings", "develop", "filed"])

    def test_a_new_step_never_takes_a_name_that_could_collide_with_those(self):
        for _ in range(20):
            self.assertNotIn(F.step_id(), ("ratings", "develop", "filed"))

    def test_filing_starts_as_report_because_it_moves_photographs(self):
        by = {s.task: s for s in F.read()[0].steps}
        self.assertEqual(by["filed"].do, "report")

    def test_a_damaged_flows_file_costs_the_flows_and_not_the_app(self):
        with open(os.path.join(self.dir, "config", "flows.json"), "w") as fh:
            fh.write("{not json")
        self.assertTrue(F.read())


class WhatAStepWatches(Flows):
    def test_it_is_worked_out_from_the_feature_itself(self):
        """And the rule is the plain one - a feature's first folder option is
        the tree it works from - which is why the carried-over flow watches
        exactly the trees the hard-coded one did."""
        want = {"ratings": "previews", "develop": "library", "filed": "inbox"}
        for step in F.read()[0].steps:
            self.assertEqual(F.watched_key(R.get(step.task), step),
                             want[step.task])

    def test_but_a_step_may_say_otherwise(self):
        step = F.read()[0].steps[0]
        step.watch = "library"
        self.assertEqual(F.watched_key(R.get("ratings"), step), "library")

    def test_a_feature_with_no_tree_to_watch_is_not_guessed_at(self):
        class Bare:
            options = []
            watches = ""
        self.assertEqual(F.watched_key(Bare()), "")


class TheOrderIsTheChain(Flows):
    def test_each_step_keeps_its_own_mark_when_it_is_moved(self):
        """The marks are filed by the step's identity, not its position - or
        reordering a flow would hand each step the one before it's history."""
        flow = F.read()[0]
        was = [s.id for s in flow.steps]
        flow.steps = [flow.steps[2]] + flow.steps[:2]
        F.write([flow])
        self.assertEqual([s.id for s in F.read()[0].steps],
                         [was[2], was[0], was[1]])

    def test_the_same_feature_twice_gets_two_marks(self):
        """A cull between two sends is a real thing to want, and two steps
        sharing one mark would each decide the other had already caught up."""
        flow = F.read()[0]
        extra = F.Step(id=F.step_id(), task="develop")
        flow.steps.append(extra)
        F.write([flow])
        ids = [s.id for s in F.read()[0].steps if s.task == "develop"]
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)

    def test_and_the_flow_says_so_rather_than_leaving_you_to_notice(self):
        flow = F.read()[0]
        flow.steps.append(F.Step(id=F.step_id(), task="develop"))
        said = " ".join(F.trouble(flow, S.load()))
        self.assertIn("2 times", said)

    def test_but_it_is_not_refused_because_it_is_a_real_thing_to_want(self):
        flow = F.read()[0]
        flow.steps.append(F.Step(id=F.step_id(), task="develop"))
        self.assertEqual(F.refusals(flow, S.load()), [])


class WouldThisEatItself(Flows):
    def test_the_exports_folder_being_the_develop_tree_is_refused(self):
        """The one that used to be a refusal written by hand about one
        arrangement. It is now worked out from what each feature declares, so
        the same reasoning covers a flow nobody has thought of yet."""
        S.save({"inbox": self.dev})
        said = F.refusals(F.read()[0], S.load())
        self.assertTrue(said)
        self.assertIn("round again", said[0])

    def test_and_so_is_a_folder_inside_it(self):
        inside = os.path.join(self.dev, "back")
        os.makedirs(inside)
        S.save({"inbox": inside})
        self.assertTrue(F.refusals(F.read()[0], S.load()))

    def test_separate_folders_are_fine(self):
        self.assertEqual(F.refusals(F.read()[0], S.load()), [])

    def test_the_ring_needs_both_halves_to_be_a_ring(self):
        """Sending to develop on its own is not a ring however the folders are
        set: nothing takes anything back out. A check that fired on one step
        would be a check people learn to ignore."""
        S.save({"inbox": self.dev})
        flow = F.read()[0]
        flow.steps = [s for s in flow.steps if s.task != "filed"]
        F.write([flow])
        self.assertEqual(F.refusals(F.read()[0], S.load()), [])

    def test_and_it_only_closes_when_what_is_taken_goes_back_where_it_is_read(self):
        """The half that makes this a RING check rather than "these two steps
        touch the same folder". Taking photographs out of the develop tree and
        putting them somewhere the sender never looks does not send anything
        round again - it is a one-way trip, and refusing it would be this app
        being frightened of an arrangement that is fine."""
        S.save({"inbox": self.dev})
        task = R.get("filed")
        was = task.moves_to
        task.moves_to = ("video",)          # not a tree Send to develop reads
        try:
            said = F.refusals(F.read()[0], S.load())
        finally:
            task.moves_to = was
        self.assertEqual(said, [], said)

    def test_a_step_naming_a_feature_that_is_gone_is_refused(self):
        flow = F.read()[0]
        flow.steps.append(F.Step(id=F.step_id(), task="no-such-feature"))
        self.assertTrue(any("no tool called" in x
                            for x in F.refusals(flow, S.load())))

    def test_a_feature_that_declared_nothing_is_said_rather_than_assumed_safe(self):
        """"I checked and it is fine" and "I could not check this" are different
        answers, and only one of them is honest about a flow this app has not
        been told the shape of."""
        flow = F.read()[0]
        task = R.get("history")
        was = (task.reads, task.copies_to, task.moves_to)
        task.reads = task.copies_to = task.moves_to = ()
        flow.steps.append(F.Step(id=F.step_id(), task="history"))
        try:
            said = " ".join(F.trouble(flow, S.load()))
        finally:
            task.reads, task.copies_to, task.moves_to = was
        self.assertIn("could not include", said)

    def test_every_step_switched_off_is_said_and_does_not_run(self):
        flow = F.read()[0]
        for s in flow.steps:
            s.on = False
        self.assertTrue(F.refusals(flow, S.load()))


class NothingIsInvisible(Flows):
    def test_a_step_reports_every_option_and_where_its_value_came_from(self):
        step = [s for s in F.read()[0].steps if s.task == "develop"][0]
        task = R.get("develop")
        said = F.options_for(task, step, S.load())
        self.assertEqual(set(said), {o.name for o in task.options})
        self.assertEqual(said["jpeg_at_or_above"]["from"], "setup")

    def test_an_override_is_reported_as_this_steps_own(self):
        step = [s for s in F.read()[0].steps if s.task == "develop"][0]
        step.opts = {"jpeg_at_or_above": 2}
        said = F.options_for(R.get("develop"), step, S.load())
        self.assertEqual(said["jpeg_at_or_above"]["from"], "step")
        self.assertEqual(said["jpeg_at_or_above"]["value"], 2)

    def test_only_the_overrides_are_handed_to_the_task(self):
        """Everything else is left absent so the task's own coerce fills it from
        Setup. A copy here would be a second copy, and it would go stale the
        moment Setup was edited - which is exactly the fault this replaces."""
        step = [s for s in F.read()[0].steps if s.task == "develop"][0]
        self.assertEqual(F.raw_for(R.get("develop"), step), {})
        step.opts = {"prune": False}
        self.assertEqual(F.raw_for(R.get("develop"), step), {"prune": False})


class TheEditorsData(Flows):
    def test_everything_that_can_be_a_step_is_offered(self):
        names = {c["name"] for c in FT.catalogue()}
        for wanted in ("ratings", "develop", "filed", "previews", "cull",
                       "duplicates", "cleanup", "bydate"):
            self.assertIn(wanted, names)

    def test_but_not_the_flow_machinery_itself(self):
        """A flow containing the flow editor is not a thought worth having."""
        names = {c["name"] for c in FT.catalogue()}
        for gone in ("automation", "flows", "autoruns", "setup", "labels"):
            self.assertNotIn(gone, names)

    def test_each_offer_says_what_it_would_watch(self):
        by = {c["name"]: c for c in FT.catalogue()}
        self.assertEqual(by["ratings"]["watches"], "previews")
        self.assertEqual(by["ratings"]["watches_path"], self.prev)

    def test_and_carries_the_options_the_editor_draws(self):
        by = {c["name"]: c for c in FT.catalogue()}
        names = {o["name"] for o in by["develop"]["options"]}
        self.assertIn("jpeg_at_or_above", names)

    def test_a_described_flow_carries_each_steps_effective_settings(self):
        got = FT.described()[0]
        step = [s for s in got["steps"] if s["task"] == "develop"][0]
        self.assertIn("jpeg_at_or_above", step["effective"])
        self.assertEqual(step["watches_label"], "The library")

    def test_the_tab_draws_the_editor_as_soon_as_it_is_opened(self):
        """A tab whose whole purpose is the editor must not make you press
        "Have a look" to see it."""
        self.assertEqual(R.get("flows").editor, "flows")
        self.assertEqual(R.get("flows").describe()["editor"], "flows")

    def test_and_lists_what_is_there_as_ordinary_rows_underneath(self):
        """So the command line and a browser with the editor broken both still
        show what the flows actually are."""
        p = R.get("flows").make_plan({})
        self.assertEqual(len(p.rows), 3)
        self.assertTrue(p.groups)

    def test_the_flows_tab_never_writes(self):
        self.assertFalse(R.get("flows").writes)


class DsmFiresIt(Flows):
    def test_a_flow_can_be_left_to_dsms_scheduler(self):
        flow = F.read()[0]
        flow.fired_by = F.BY_DSM
        F.write([flow])
        self.assertEqual(F.read()[0].fired_by, F.BY_DSM)

    def test_and_the_command_runs_that_flow_through_the_ordinary_command_line(self):
        """No second entry point: the command line already runs any registered
        task from its declared options, so what the scheduler fires is what the
        tab shows. A second way in would be a second thing to keep in step."""
        said = FT.command_for(F.read()[0])
        self.assertIn("app.cli automation", said)
        self.assertIn("--which developing", said)
        self.assertIn("--apply", said)

    def test_the_command_is_one_the_command_line_actually_accepts(self):
        from app import cli
        said = FT.command_for(F.read()[0])
        args = said.split("app.cli ", 1)[1].split()
        self.assertEqual(args[0], "automation")
        raw = cli.parse_args(args[1:])
        self.assertEqual(raw.get("which"), "developing")
        self.assertTrue(raw.get("apply"))

    def test_the_app_leaves_a_dsm_flow_alone_whatever_its_switch_says(self):
        """Two things firing one flow is two passes moving the same photographs
        past each other."""
        import inspect
        from app import server
        source = inspect.getsource(server.automation_loop)
        self.assertIn("BY_APP", source)

    def test_and_the_bar_does_not_claim_to_be_running_it(self):
        from app import server
        flow = F.read()[0]
        flow.on, flow.fired_by = True, F.BY_DSM
        F.write([flow])
        state = server.automation_state()
        self.assertFalse(state["on"])
        self.assertIn("Developing loop", state["by_dsm"])

    def test_it_names_this_container_rather_than_inventing_one(self):
        was = os.environ.get("PM_CONTAINER")
        os.environ["PM_CONTAINER"] = "photo-manager-1"
        try:
            self.assertIn("photo-manager-1", FT.command_for(F.read()[0]))
        finally:
            if was is None:
                os.environ.pop("PM_CONTAINER", None)
            else:
                os.environ["PM_CONTAINER"] = was


if __name__ == "__main__":
    unittest.main()


class SavingThemOverHttp(Flows):
    """The editor writes the whole list in one go, which is two things: the
    order of the steps is the order the work happens, so a half-saved list is a
    flow nobody assembled; and a pass can therefore never see a flow somebody
    was in the middle of editing."""

    def setUp(self):
        super().setUp()
        import threading
        from http.server import ThreadingHTTPServer
        from app import server as SRV
        self.SRV = SRV
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), SRV.Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}/"
        threading.Thread(target=self.httpd.serve_forever,
                         kwargs={"poll_interval": 0.02}, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.SRV.ALLOWED_ROOTS.clear()
        super().tearDown()

    def post(self, path, obj):
        import urllib.request
        req = urllib.request.Request(self.base + path, json.dumps(obj).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as fh:
            return json.load(fh)

    def get(self, path):
        import urllib.request
        with urllib.request.urlopen(self.base + path) as fh:
            return json.load(fh)

    def test_the_editor_is_given_the_flows_and_everything_it_could_add(self):
        got = self.get("api/flows")
        self.assertEqual([f["id"] for f in got["flows"]], ["developing"])
        self.assertGreater(len(got["catalogue"]), 10)

    def test_a_flow_assembled_from_the_catalogue_is_saved(self):
        got = self.get("api/flows")
        made = {"id": "", "name": "Sunday tidy-up", "on": False, "every": 1440,
                "deep": True, "fired_by": "dsm",
                "steps": [{"id": "", "task": "duplicates", "on": True,
                           "do": "report", "watch": "", "opts": {}}]}
        back = self.post("api/flows", {"flows": got["flows"] + [made]})
        self.assertTrue(back.get("saved"), back)
        names = [f.name for f in F.read()]
        self.assertIn("Sunday tidy-up", names)

    def test_and_is_given_an_id_and_step_ids_of_its_own(self):
        got = self.get("api/flows")
        made = {"id": "", "name": "Sunday tidy-up", "steps": [
            {"id": "", "task": "duplicates"}]}
        self.post("api/flows", {"flows": got["flows"] + [made]})
        new = [f for f in F.read() if f.name == "Sunday tidy-up"][0]
        self.assertTrue(new.id)
        self.assertTrue(new.steps[0].id)
        self.assertNotEqual(new.id, "developing")

    def test_a_step_keeps_its_own_settings_across_a_save(self):
        got = self.get("api/flows")
        got["flows"][0]["steps"][1]["opts"] = {"jpeg_at_or_above": 2}
        self.post("api/flows", {"flows": got["flows"]})
        step = F.read()[0].steps[1]
        self.assertEqual(step.opts, {"jpeg_at_or_above": 2})

    def test_a_ring_is_refused_at_the_moment_of_saving(self):
        """A flow you can save and cannot run is a flow you find out about at
        four in the morning."""
        S.save({"inbox": self.dev})
        got = self.get("api/flows")
        try:
            self.post("api/flows", {"flows": got["flows"]})
            self.fail("a flow that eats itself was accepted")
        except Exception as exc:                    # noqa: BLE001
            self.assertIn("400", str(exc))

    def test_but_a_flow_you_are_still_building_is_not(self):
        """Every step switched off is what a half-built flow looks like, and
        refusing to save one is refusing to let you build it."""
        got = self.get("api/flows")
        for s in got["flows"][0]["steps"]:
            s["on"] = False
        self.assertTrue(self.post("api/flows", {"flows": got["flows"]})
                        .get("saved"))

    def test_saving_returns_them_read_back_rather_than_what_was_sent(self):
        """So the editor shows what is on disk, ids and all, rather than its own
        idea of it."""
        got = self.get("api/flows")
        back = self.post("api/flows", {"flows": got["flows"]})
        self.assertEqual([f["id"] for f in back["flows"]], ["developing"])


class DrawnAsAChain(Flows):
    """A list of steps with a summary above it reads as a SET, and the one
    property of a flow that is easy to get wrong is its ORDER: steps run in
    order inside one pass and a step that writes makes the next one run straight
    away, so a step before the one that feeds it does its work an interval late,
    for ever, and nothing on a list says so.

    Worked out on the server so that the Automation tab and the Flows tab cannot
    draw two different pictures of one flow.
    """

    def test_a_block_per_step_in_order(self):
        got = FT.diagram(F.read()[0])
        self.assertEqual([b["task"] for b in got],
                         ["ratings", "develop", "filed"])
        self.assertEqual([b["n"] for b in got], [1, 2, 3])

    def test_each_block_says_what_it_watches(self):
        got = {b["task"]: b for b in FT.diagram(F.read()[0])}
        self.assertEqual(got["ratings"]["watches"], "The previews tree")
        self.assertEqual(got["filed"]["watches"], "Lightroom's export folder")

    def test_and_whether_that_tree_is_actually_set_up(self):
        """A step that cannot run because Setup is half filled in should say so
        on the diagram rather than looking like every other step."""
        got = {b["task"]: b for b in FT.diagram(F.read()[0])}
        self.assertTrue(got["develop"]["ready"])
        S.save({"previews": ""})
        got = {b["task"]: b for b in FT.diagram(F.read()[0])}
        self.assertFalse(got["ratings"]["ready"])

    def test_and_whether_it_runs_or_only_reports(self):
        got = {b["task"]: b for b in FT.diagram(F.read()[0])}
        self.assertEqual(got["develop"]["do"], "run")
        self.assertEqual(got["filed"]["do"], "report")

    def test_and_how_much_is_waiting_on_it(self):
        A.waiting("filed", 194)
        got = {b["task"]: b for b in FT.diagram(F.read()[0])}
        self.assertEqual(got["filed"]["waiting"], 194)

    def test_a_step_switched_off_is_drawn_rather_than_dropped(self):
        """It is still part of the flow, and a chain that silently omits it is
        a chain that does not explain why nothing happens."""
        flow = F.read()[0]
        flow.steps[0].on = False
        F.write([flow])
        got = FT.diagram(F.read()[0])
        self.assertEqual(len(got), 3)
        self.assertFalse(got[0]["on"])

    def test_a_step_whose_feature_is_gone_is_marked_not_hidden(self):
        flow = F.read()[0]
        flow.steps.append(F.Step(id=F.step_id(), task="no-such-feature"))
        F.write([flow])
        self.assertTrue(FT.diagram(F.read()[0])[-1]["missing"])

    def test_both_tabs_are_given_the_same_drawing(self):
        """Two pictures of one flow is two pictures that will disagree."""
        self.assertEqual(R.get("automation").make_plan({}).editor, "flowsummary")
        self.assertEqual(R.get("flows").editor, "flows")
        self.assertEqual(FT.described()[0]["diagram"], FT.diagram(F.read()[0]))


class LeavingFoldersOut(Flows):
    def test_a_flow_carries_folders_to_leave_alone(self):
        flow = F.read()[0]
        flow.exclude = [os.path.join(self.lib, "Mobile")]
        F.write([flow])
        self.assertEqual(F.read()[0].exclude,
                         [os.path.join(self.lib, "Mobile")])

    def test_the_editor_is_told_about_them(self):
        flow = F.read()[0]
        flow.exclude = [os.path.join(self.lib, "Mobile")]
        F.write([flow])
        self.assertEqual(FT.described()[0]["exclude"],
                         [os.path.join(self.lib, "Mobile")])

    def test_and_they_survive_being_saved_through_the_editor(self):
        flow = F.read()[0]
        raw = {"id": flow.id, "name": flow.name,
               "exclude": [os.path.join(self.lib, "Mobile")],
               "steps": [{"id": s.id, "task": s.task} for s in flow.steps]}
        F.write([F._as_flow(raw)])
        self.assertEqual(F.read()[0].exclude,
                         [os.path.join(self.lib, "Mobile")])

    def test_setup_has_the_list_every_flow_obeys(self):
        opt = [o for o in R.get("setup").options if o.name == "exclude"][0]
        self.assertEqual(opt.kind, "folders")
        self.assertEqual(opt.setting, "exclude")
