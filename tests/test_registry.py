"""The registry is what makes the tenth feature cheap, so it gets its own tests."""

import os
import unittest

from app import registry as R
import app.tasks  # noqa: F401  - importing registers every task

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class OptionsDescribeThemselves(unittest.TestCase):
    def test_a_flag_understands_what_a_browser_sends(self):
        f = R.Flag("x", "X")
        for truthy in ("on", "true", "1", "yes", True):
            self.assertTrue(f.coerce(truthy), truthy)
        for falsy in ("off", "false", "0", "", None, False):
            self.assertFalse(f.coerce(falsy), falsy)

    def test_a_number_is_clamped_not_rejected(self):
        n = R.Number("n", "N", default=60, minimum=1, maximum=100)
        self.assertEqual(n.coerce("5"), 5)
        self.assertEqual(n.coerce(0), 1)
        self.assertEqual(n.coerce(9999), 100)

    def test_nonsense_falls_back_to_the_default_rather_than_crashing(self):
        n = R.Number("n", "N", default=60, minimum=1, maximum=100)
        self.assertEqual(n.coerce("banana"), 60)
        self.assertEqual(n.coerce(None), 60)

    def test_a_choice_refuses_a_value_it_was_never_offered(self):
        c = R.Choice("c", "C", default="a", choices=["a", "b"])
        self.assertEqual(c.coerce("b"), "b")
        self.assertEqual(c.coerce("z"), "a")

    def test_every_option_can_describe_itself_well_enough_to_draw(self):
        for opt in (R.Folder("f", "F"), R.Flag("g", "G"),
                    R.Number("n", "N", default=1), R.Choice("c", "C", choices=["a"])):
            d = opt.describe()
            self.assertIn(d["kind"], ("folder", "flag", "number", "choice"))
            self.assertTrue(d["label"])
            self.assertEqual(d["name"], opt.name)


def _demo_task(name="demo-task"):
    """A task that exists only for these tests.

    The registry should be testable without depending on how any real feature
    happens to behave today - leaning on geotag meant these tests broke the moment
    geotag learned to write.
    """
    return R.Task(
        name=name, title="Demo", summary="Only for testing the registry.",
        writes=False, options=[
            R.Folder("folder", "A folder"),
            R.Flag("replace", "A flag"),
            R.Number("max_gap", "A number", default=60, minimum=1, maximum=1440),
            R.Choice("mode", "A choice", default="a", choices=["a", "b"]),
        ],
        plan=lambda o: R.Plan(task=name, stats=[("Given", str(o))]),
        apply=lambda p, **kw: R.Result(done=0))


class TasksAreSelfDescribing(unittest.TestCase):
    def setUp(self):
        import shutil, tempfile
        self.dir = tempfile.mkdtemp(prefix="registry-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        os.makedirs(self.lib)
        os.makedirs(self.raw)
        self._rm = shutil.rmtree

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        self._rm(self.dir, ignore_errors=True)

    def test_at_least_one_task_is_registered(self):
        self.assertTrue(R.all_tasks())

    def test_a_task_can_be_fetched_by_name(self):
        self.assertIsNotNone(R.get("geotag"))
        self.assertIsNone(R.get("no-such-task"))

    def test_two_tasks_cannot_share_a_name(self):
        with self.assertRaises(ValueError):
            R.register(_demo_task("geotag"))

    def test_a_description_carries_everything_a_form_needs(self):
        d = R.get("geotag").describe()
        self.assertEqual(d["name"], "geotag")
        self.assertTrue(d["options"])
        self.assertTrue(d["title"])
        self.assertTrue(d["summary"])
        self.assertTrue(d["options"])
        for o in d["options"]:
            self.assertTrue(o["label"], o)

    def test_a_task_that_only_looks_says_so(self):
        self.assertFalse(_demo_task().writes)
        self.assertTrue(R.get("geotag").writes)

    def test_options_arriving_as_strings_come_back_as_the_right_types(self):
        t = _demo_task()
        opts = t.coerce({"folder": FIX, "replace": "on", "max_gap": "30"})
        self.assertEqual(opts["folder"], FIX)
        self.assertIs(opts["replace"], True)
        self.assertEqual(opts["max_gap"], 30)

    def test_a_box_you_emptied_is_not_a_box_you_never_filled(self):
        """Both arrive as "" once a form has been through a browser. Treating
        them the same means "leave blank to leave RAWs alone" is a sentence the
        app does not keep - the setting fills the box straight back in, and a
        cull you thought you had limited to JPEGs quietly moves negatives too."""
        from core import settings as _s
        _s.save({"raw": self.raw})
        t = R.get("cull")
        never_asked = t.coerce({"folder": self.lib})
        self.assertEqual(never_asked["raw"], self.raw)      # Setup fills it
        emptied = t.coerce({"folder": self.lib, "raw": ""})
        self.assertEqual(emptied["raw"], "")                # you meant it

    def test_but_only_folders_work_that_way(self):
        """A number or a choice submitted empty is a form quirk, not a decision -
        there is nothing a blank one could mean."""
        t = R.get("cull")
        self.assertEqual(t.coerce({"folder": self.lib, "raw_at_or_below": ""})
                         ["raw_at_or_below"], 2)

    def test_missing_options_fall_back_to_defaults(self):
        opts = _demo_task().coerce({})
        self.assertEqual(opts["max_gap"], 60)
        self.assertIs(opts["replace"], False)

    def test_every_registered_task_can_describe_itself(self):
        for t in R.all_tasks():
            d = t.describe()
            self.assertTrue(d["title"], t.name)
            self.assertTrue(d["summary"], t.name)
            for o in d["options"]:
                self.assertTrue(o["label"], f"{t.name}.{o['name']}")


class LongFormsStartFolded(unittest.TestCase):
    """More than eight boxes is a column you scroll past to reach the button.
    Setup and the colour labels are the two that are read through rather than
    filled in once, so they stay open."""

    OPEN_ON_PURPOSE = {"setup", "labels"}

    def test_every_long_form_folds(self):
        unfolded = [t.name for t in R.all_tasks()
                    if len(t.options) > 8 and t.name not in self.OPEN_ON_PURPOSE
                    and not t.fold_groups]
        self.assertEqual(unfolded, [])

    def test_these_fourteen_fold_now(self):
        for name in ("library", "retime", "geotag", "timeline", "bydate",
                     "previews", "ratings", "tags", "cull", "blur", "exposure",
                     "duplicates", "develop", "cleanup"):
            self.assertTrue(R.get(name).fold_groups, name)
            self.assertTrue(R.get(name).describe()["fold_groups"], name)

    def test_but_not_the_two_that_are_read_through(self):
        for name in self.OPEN_ON_PURPOSE:
            self.assertFalse(R.get(name).fold_groups, name)


class WhatWasChosenReachesTheWriter(unittest.TestCase):
    """The bug this guards against: options were coerced, handed to plan(), and
    then thrown away. apply() never saw them, so ticking a box on the form did
    nothing at all and said nothing about it. An option that reaches the form but
    not the writer is worse than one that was never offered."""

    def test_a_plan_carries_the_options_it_was_made_from(self):
        t = _demo_task()
        p = t.make_plan({"folder": FIX, "replace": "on", "max_gap": "30"})
        self.assertIs(p.opts["replace"], True)
        self.assertEqual(p.opts["max_gap"], 30)

    def test_make_plan_names_the_task_even_if_the_task_forgot_to(self):
        t = R.Task(name="unnamed-plan", title="T", summary="S", writes=False,
                   options=[R.Flag("f", "A flag")],
                   plan=lambda o: R.Plan(), apply=lambda p, **kw: R.Result())
        self.assertEqual(t.make_plan({"f": "on"}).task, "unnamed-plan")

    def test_every_writing_task_reads_its_own_flags_off_the_plan(self):
        """No writing task may take its behaviour from anywhere but plan.opts -
        there is no other route from the form to apply()."""
        import inspect
        for t in R.all_tasks():
            if not t.writes:
                continue
            src = inspect.getsource(t.apply)
            for line in src.splitlines():
                self.assertNotIn("opts[", line.replace("plan.opts[", ""),
                                 f"{t.name}: apply() reads options from somewhere "
                                 f"other than the plan")


class ThePlanIsAClaimNotAnAction(unittest.TestCase):
    def test_a_plan_reports_what_it_was_given(self):
        t = _demo_task()
        p = t.plan(t.coerce({"folder": FIX, "max_gap": "30"}))
        self.assertEqual(p.task, "demo-task")
        self.assertTrue(p.stats)

    def test_a_real_task_refuses_a_folder_that_is_not_there(self):
        for name in ("geotag", "remirror"):
            t = R.get(name)
            opts = t.coerce({"folder": "/no/such/folder",
                             "library": "/no/such/folder", "raw": "/no/such/folder"})
            p = t.plan(opts)
            self.assertTrue(p.blocked, name)
            self.assertEqual(p.rows, [], name)

    def test_planning_changes_nothing_on_disk(self):
        before = {n: os.stat(os.path.join(FIX, n)).st_mtime_ns
                  for n in os.listdir(FIX)}
        for name in ("geotag", "remirror"):
            t = R.get(name)
            t.plan(t.coerce({"folder": FIX, "replace": "on",
                             "library": FIX, "raw": FIX}))
        after = {n: os.stat(os.path.join(FIX, n)).st_mtime_ns
                 for n in os.listdir(FIX)}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
