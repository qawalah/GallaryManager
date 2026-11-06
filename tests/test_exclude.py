"""Folders nothing walks into - a place, not a name.

Setup already skips folder NAMES: `@eaDir`, `#recycle`, `Developed`. Those mean
"this is not a photograph of yours", anywhere, and they are names because one
entry has to cover every shoot.

This is a different question. "My phone's photos live in Photos/Mobile and I do
not want the developing loop touching them" is about ONE PLACE - a name would
take out every folder called Mobile anywhere - and it is per flow, because the
Sunday tidy-up may well want them.

Three things have to hold or this is worse than not having it:

- **a tree that is quietly smaller than you think.** "0 of 400 geotagged" is a
  number nobody can act on if the 400 was really 12,000. Every run that meets an
  excluded folder says which, and how many files it did not look at.
- **Setup's list and a flow's are ADDED**, never replaced, or building a flow
  quietly undoes a decision made once.
- **it is scoped to the run.** Opening a tab by hand must still see the whole
  library, and two flows running at once must not have to agree.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R                # noqa: E402
import app.tasks                             # noqa: E402,F401
from core import automation as A             # noqa: E402
from core import exclude as X                # noqa: E402
from core import flows as F                  # noqa: E402
from core import settings as S               # noqa: E402
from core import walk                        # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Excluding(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="exclude-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.mobile = os.path.join(self.lib, "Mobile")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        self.dev = os.path.join(self.dir, "Develop")
        for d in (self.mobile, self.shoot, self.dev):
            os.makedirs(d)
        for n in ("a", "b", "c"):
            shutil.copy(os.path.join(FIX, "rated.jpg"),
                        os.path.join(self.mobile, n + ".JPG"))
        shutil.copy(os.path.join(FIX, "rated.jpg"),
                    os.path.join(self.shoot, "x.JPG"))
        S.save({"library": self.lib, "develop": self.dev})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    # ------------------------------------------------------------- the walk

    def test_a_walk_leaves_out_what_it_was_told_to(self):
        self.assertEqual(len(walk.walk(self.lib).files), 4)
        with X.using([self.mobile]):
            self.assertEqual(len(walk.walk(self.lib).files), 1)

    def test_and_anything_inside_it(self):
        deeper = os.path.join(self.mobile, "2019", "March")
        os.makedirs(deeper)
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(deeper, "d.JPG"))
        with X.using([self.mobile]):
            self.assertEqual(len(walk.walk(self.lib).files), 1)

    def test_but_not_the_tree_beside_it(self):
        """Compared segment by segment, never as text: `Photos` and `Photos Raw`
        share eight characters and share no folder at all, and an exclusion that
        also took out the tree beside it would be a quiet way to lose half a
        library."""
        beside = self.lib + " Raw"
        os.makedirs(beside)
        shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(beside, "r.RW2"))
        with X.using([self.lib]):
            self.assertEqual(len(walk.walk(beside).files), 1)

    def test_it_says_what_it_left_out_and_how_much(self):
        with X.using([self.mobile]):
            got = walk.walk(self.lib)
        self.assertEqual(got.left_out, {self.mobile: 3})

    def test_a_tree_that_is_itself_excluded_is_not_reported_as_empty(self):
        """An empty walk looks exactly like an empty folder, and "there is
        nothing there" is a very different thing to be told."""
        with X.using([self.lib]):
            got = walk.walk(self.lib)
        self.assertEqual(got.files, [])
        self.assertIn(self.lib, got.left_out)

    def test_nothing_excluded_costs_nothing_and_changes_nothing(self):
        got = walk.walk(self.lib)
        self.assertEqual(got.left_out, {})
        self.assertEqual(len(got.files), 4)

    # --------------------------------------------------- said, never silent

    def test_every_plan_says_what_it_did_not_look_at(self):
        """One place, so no task can walk a tree and forget to mention it."""
        task = R.get("develop")
        opts = {"folder": self.lib, "develop": self.dev, "raw": "",
                "mirror": False, "library": self.lib,
                "jpeg_at_or_above": 1, "raw_at_or_above": -1}
        with X.using([self.mobile]):
            p = task.make_plan(dict(opts))
        self.assertTrue(any("LEFT OUT on purpose" in n for n in p.notes), p.notes)
        self.assertTrue(any("3 file(s)" in n for n in p.notes), p.notes)

    def test_and_says_nothing_when_nothing_was_left_out(self):
        """A note about exclusions on every plan whether or not any applied is a
        note people learn to skip."""
        task = R.get("develop")
        p = task.make_plan({"folder": self.lib, "develop": self.dev, "raw": "",
                            "mirror": False, "library": self.lib,
                            "jpeg_at_or_above": 1, "raw_at_or_above": -1})
        self.assertFalse(any("LEFT OUT" in n for n in p.notes), p.notes)

    def test_setup_s_list_is_announced_on_a_feature_run_by_hand_too(self):
        """Not only in a flow. Setup's list was always HONOURED everywhere - the
        walker reads it - but outside a flow nothing kept count, so a feature
        run by hand skipped the excluded folders and then reported a smaller
        library without a word about why. That is the silent version of the
        thing the note exists to prevent."""
        S.save({"library": self.lib, "develop": self.dev,
                "exclude": self.mobile})
        task = R.get("develop")
        p = task.make_plan({"folder": self.lib, "develop": self.dev, "raw": "",
                            "mirror": False, "library": self.lib,
                            "jpeg_at_or_above": 1, "raw_at_or_above": -1})
        self.assertTrue(any("LEFT OUT on purpose" in n for n in p.notes), p.notes)

    def test_and_a_flow_s_own_list_is_not_replaced_by_it(self):
        """A flow's list is Setup's PLUS its own. Opening a fresh one inside it
        would quietly walk into the folders the flow was told to leave."""
        S.save({"library": self.lib, "develop": self.dev, "exclude": ""})
        task = R.get("develop")
        with X.using([self.mobile]):
            p = task.make_plan({"folder": self.lib, "develop": self.dev,
                                "raw": "", "mirror": False, "library": self.lib,
                                "jpeg_at_or_above": 1, "raw_at_or_above": -1})
        self.assertTrue(any("3 file(s)" in n for n in p.notes), p.notes)

    def test_a_folder_listed_but_never_met_is_not_announced(self):
        with X.using([os.path.join(self.dir, "somewhere else")]):
            got = walk.walk(self.lib)
        self.assertEqual(got.left_out, {})

    # ----------------------------------------------------- setup and a flow

    def test_setup_holds_a_list_every_flow_obeys(self):
        S.save({"exclude": self.mobile})
        self.assertEqual(X.from_settings(), [self.mobile])
        self.assertEqual(len(walk.walk(self.lib).files), 1)

    def test_a_flows_list_is_added_to_setups_not_instead_of_it(self):
        """Building a flow must not quietly undo a decision made once."""
        S.save({"exclude": self.mobile})
        with X.using([self.shoot]):
            got = walk.walk(self.lib)
        self.assertEqual(got.files, [])
        self.assertEqual(set(got.left_out), {self.mobile, self.shoot})

    def test_a_flow_carries_its_own_list(self):
        flow = F.read()[0]
        flow.exclude = [self.mobile]
        F.write([flow])
        self.assertEqual(F.read()[0].exclude, [self.mobile])

    def test_the_pass_runs_under_the_flows_list(self):
        import inspect
        from app.tasks import automation as AUTO
        source = inspect.getsource(AUTO.one_pass)
        self.assertIn("X.using(flow.exclude)", source)

    # ------------------------------------------------------- scoped to a run

    def test_it_is_put_back_afterwards(self):
        """A run that left an exclusion behind would make the NEXT thing you
        open quietly blind to part of your library."""
        with X.using([self.mobile]):
            pass
        self.assertEqual(len(walk.walk(self.lib).files), 4)

    def test_even_when_the_run_raised(self):
        try:
            with X.using([self.mobile]):
                raise ValueError("half way")
        except ValueError:
            pass
        self.assertEqual(len(walk.walk(self.lib).files), 4)

    def test_a_nested_run_does_not_carry_its_tally_out_with_it(self):
        """Every plan reports what IT left out by comparing the tally before and
        after, so a nested run leaking its own would make the outer plan claim
        folders it never met."""
        with X.using([self.shoot]):
            walk.walk(self.lib)
            outer = X.what_was_met()
            with X.using([self.mobile], add_settings=False):
                walk.walk(self.lib)
            self.assertEqual(X.what_was_met(), outer,
                             "the inner run's tally leaked out")

    def test_two_runs_at_once_do_not_have_to_agree(self):
        import threading
        seen = {}

        def other():
            with X.using([self.shoot]):
                seen["other"] = len(walk.walk(self.lib).files)
        with X.using([self.mobile]):
            t = threading.Thread(target=other)
            t.start()
            t.join()
            seen["mine"] = len(walk.walk(self.lib).files)
        self.assertEqual(seen["mine"], 1)          # Mobile gone, the shoot left
        self.assertEqual(seen["other"], 3)         # the shoot gone, Mobile left

    # ------------------------------------------------ and the change watcher

    def test_the_change_check_leaves_out_the_same_folders(self):
        """A fingerprint that counted them would wake the flow up for a change
        in a folder its own steps then refuse to look at - every pass, for
        ever."""
        self.assertEqual(A.fingerprint(self.lib).files, 4)
        with X.using([self.mobile]):
            self.assertEqual(A.fingerprint(self.lib).files, 1)

    def test_and_a_watched_tree_that_is_excluded_says_so_rather_than_never_running(self):
        with X.using([self.lib]):
            self.assertFalse(A.fingerprint(self.lib).there)


if __name__ == "__main__":
    unittest.main()
