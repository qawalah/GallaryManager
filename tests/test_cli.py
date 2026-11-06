"""The command line refuses what it does not understand.

It is what the NAS scheduler runs at three in the morning with --apply, so a
typo there is not a typo someone sees: a misspelt option used to be dropped and
the task ran on Setup's whole library, and an unknown flow ran the first one.
"""

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import cli                          # noqa: E402
from app.tasks import automation             # noqa: E402
from core import flows as F                  # noqa: E402


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


class RefusingWhatItDoesNotKnow(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cli-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = self.home
        self._pass = automation.one_pass
        self.ran = []
        automation.one_pass = lambda *a, **k: self.ran.append(a) or []

    def tearDown(self):
        automation.one_pass = self._pass
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.home, ignore_errors=True)

    def test_an_unknown_flow_runs_nothing_and_lists_the_flows(self):
        code, said = run("automation", "--which", "nope", "--apply")
        self.assertEqual(code, 2)
        self.assertEqual(self.ran, [])
        for flow in F.read():
            self.assertIn(flow.id, said)
        self.assertIn("'nope'", said)

    def test_a_flow_that_exists_is_accepted(self):
        first = F.read()[0].id
        task = cli.R.get("automation")
        self.assertEqual(cli.problems(task, {"which": first, "apply": True}), [])

    def test_a_misspelt_option_is_an_error_with_a_hint(self):
        code, said = run("cull", "--foldr", "/nowhere", "--apply")
        self.assertEqual(code, 2)
        self.assertIn("there is no option --foldr", said)
        self.assertIn("did you mean --folder", said)
        self.assertIn("nothing was written", said)

    def test_a_hyphen_for_an_underscore_is_caught_too(self):
        task = cli.R.get("cull")
        names = {o.name for o in task.options if "_" in o.name}
        self.assertTrue(names, "cull has no option with an underscore to test")
        one = sorted(names)[0]
        wrong = cli.problems(task, {one.replace("_", "-"): "2"})
        self.assertEqual(len(wrong), 1)
        self.assertIn(f"--{one}", wrong[0])


class ExitStatus(unittest.TestCase):
    """DSM's Task Scheduler and run.bat read any non-zero status as a failed
    job, so asking for the list or the help is a success."""

    def test_list_and_help_are_a_success(self):
        for argv in (["--list"], ["--help"], ["-h"], ["help"], ["cull", "--help"]):
            with self.subTest(argv=argv):
                self.assertEqual(run(*argv)[0], 0)

    def test_no_task_or_an_unknown_one_is_not(self):
        self.assertEqual(run()[0], 1)
        self.assertEqual(run("no-such-task")[0], 1)


if __name__ == "__main__":
    unittest.main()
