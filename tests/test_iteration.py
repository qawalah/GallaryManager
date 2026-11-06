"""The batch of 2026-09-05, and what each one was actually fixing.

Most of these are small. Two are not, and both are the same shape of bug: the
app quietly did something reasonable-looking instead of the right thing, and
said nothing.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from core import settings as S             # noqa: E402
from core import survey as SV              # noqa: E402
from core import walk                      # noqa: E402
from core.paths import anchor_for          # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Trees(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="iter-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.prev = os.path.join(self.dir, "Photos Previews")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        os.makedirs(self.prev)
        for n in ("plain", "rated"):
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(self.shoot, n + ".JPG"))

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def settings(self, **over):
        S.save({"library": self.lib, "raw": self.raw, "previews": self.prev, **over})


class PreviewsMustNotLandFlat(Trees):
    """The one Abu hit: pick the previews ROOT and a library sub-folder, and
    every preview went straight into the top of the previews tree - mixed in
    with every other shoot, and nothing said a word. It looks like it worked."""

    def test_with_the_library_known_they_mirror(self):
        self.settings()
        p = R.get("previews").make_plan({"folder": self.shoot, "previews": self.prev})
        self.assertTrue(p.rows)
        for row in p.rows:
            self.assertTrue(row.target.startswith(
                os.path.join(self.prev, "2022", "Spain")), row.target)

    def test_the_anchor_is_worked_out_rather_than_asked_for(self):
        """It is the library that gives a folder its position, and Setup already
        knows where the library is. Nobody should have to fill in a second box
        that says the same thing."""
        self.settings()
        anchor, why = anchor_for("", self.shoot)
        self.assertEqual(anchor, self.lib)
        self.assertEqual(why, "")

    def test_and_when_it_cannot_be_worked_out_it_refuses(self):
        """A warning was not enough, and that is not a guess - it happened
        twice. Landing flat is not a defensible last resort after all: it is
        indistinguishable from working, the run reports complete success, and
        the sentence explaining it is one of ten under a table that looks
        perfectly fine. So now nothing happens until the anchor is known."""
        anchor, why = anchor_for("", self.shoot)          # no settings saved
        self.assertEqual(anchor, self.shoot)
        self.assertIn("TOP", why)
        p = R.get("previews").make_plan({"folder": self.shoot, "previews": self.prev})
        self.assertTrue(p.blocked)
        self.assertEqual(p.rows, [], "it planned work it should have refused")

    def test_and_the_refusal_names_the_one_thing_that_fixes_it(self):
        """A refusal you cannot act on is just a different way of being stuck."""
        p = R.get("previews").make_plan({"folder": self.shoot, "previews": self.prev})
        self.assertIn("Setup", p.blocked)
        self.assertIn("anchor", p.blocked)

    def test_but_with_nowhere_to_write_to_a_guess_costs_nothing(self):
        """The refusal is about FLATTENING something, not about the anchor being
        unknown - with no destination tree there is nothing to flatten, and
        refusing then would be an obstacle for its own sake."""
        from core.paths import mirror_anchor
        _anchor, refuse = mirror_anchor("", self.shoot, "")
        self.assertEqual(refuse, "")


class RawsStillInTheLibrary(Trees):
    """"Re-mirror is not detecting RAWs that don't follow the originals."

    It only ever looked inside the RAW tree, so a RAW that was never separated
    was invisible to it - and it would report a perfectly tidy tree while RAWs
    sat in the library the whole time. The last place you would look for a
    mirroring problem."""

    def setUp(self):
        super().setUp()
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(self.shoot, "plain.RW2"))
        os.makedirs(self.raw)

    def test_a_raw_still_in_the_library_is_gathered(self):
        p = R.get("remirror").make_plan({"library": self.lib, "raw": self.raw})
        moves = [r for r in p.rows if r.name == "plain.RW2"]
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0].target,
                         os.path.join(self.raw, "2022", "Spain", "plain.RW2"))
        self.assertIn("still in the library", moves[0].detail)

    def test_and_it_can_be_turned_off(self):
        p = R.get("remirror").make_plan({"library": self.lib, "raw": self.raw,
                                         "gather_library": False})
        self.assertEqual([r for r in p.rows if r.name == "plain.RW2"], [])

    def test_a_raw_in_the_wrong_place_inside_the_tree_still_moves(self):
        stray = os.path.join(self.raw, "Wherever")
        os.makedirs(stray)
        shutil.copy(os.path.join(FIX, "rated.jpg"), os.path.join(stray, "rated.RW2"))
        p = R.get("remirror").make_plan({"library": self.lib, "raw": self.raw})
        moves = [r for r in p.rows if r.name == "rated.RW2"]
        self.assertEqual(moves[0].target,
                         os.path.join(self.raw, "2022", "Spain", "rated.RW2"))


class LeavingFoldersOutOfTheLibraryView(Trees):
    def setUp(self):
        super().setUp()
        self.archive = os.path.join(self.lib, "2019", "Archive")
        os.makedirs(self.archive)
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(self.archive, "old.JPG"))
        self.settings()

    def seen(self, **over):
        """The folder names the tree view would draw."""
        p = R.get("library").make_plan({"folder": self.lib, "rescan": True, **over})
        return {node["name"] for node in p.tree}

    def test_by_name_it_leaves_out_every_folder_called_that(self):
        self.assertIn("Archive", self.seen())
        self.assertNotIn("Archive", self.seen(exclude="Archive"))

    def test_by_path_it_leaves_out_that_one_and_what_is_under_it(self):
        self.assertNotIn("Archive", self.seen(exclude=os.path.join(self.lib, "2019")))
        self.assertIn("Spain", self.seen(exclude=os.path.join(self.lib, "2019")))

    def test_a_name_that_merely_starts_the_same_is_not_caught(self):
        self.assertIn("Archive", self.seen(exclude="Arch"))

    def test_it_only_affects_the_view_never_the_work(self):
        """This is a display filter. The tasks that move files obey the Setup
        ignore list, which is a different question - "not photographs" rather
        than "not interested right now"."""
        left_out = SV.leaving_out(["Archive"])
        self.assertTrue(left_out(self.archive))
        self.assertIn(os.path.join(self.archive, "old.JPG"), walk.walk(self.lib).files)


class WhereLocationsComeFrom(Trees):
    def setUp(self):
        super().setUp()
        self.ref = os.path.join(self.dir, "Reference")
        os.makedirs(self.ref)
        shutil.copy(os.path.join(FIX, "phone_doha.jpg"),
                    os.path.join(self.ref, "ref.JPG"))

    def plan(self, order):
        return R.get("geotag").make_plan(
            {"folder": self.shoot, "phone": self.ref, "order": order,
             "max_gap": 100000})

    def test_a_folder_of_located_photos_can_be_the_only_source(self):
        p = self.plan("photos_only")
        self.assertFalse(p.blocked, p.blocked)
        self.assertTrue(p.rows)

    def test_asking_only_the_timeline_when_there_is_none_says_so(self):
        p = self.plan("timeline_only")
        self.assertTrue(p.blocked)
        self.assertIn("Timeline", p.blocked)

    def test_the_order_is_offered_as_a_choice_not_fixed(self):
        offered = {c["value"] for c in
                   next(o for o in R.get("geotag").options if o.name == "order")
                   .describe()["choices"]}
        self.assertEqual(offered,
                         {"timeline", "photos", "timeline_only", "photos_only"})

    def test_and_the_plan_says_which_order_it_used(self):
        p = self.plan("photos")
        self.assertTrue(any("Using your photos only" in n or "Asked in order" in n
                            for n in p.notes), p.notes)


class WhereThingsEndUp(Trees):
    def test_every_row_that_moves_a_file_says_where_to(self):
        """Half the question is which files; the other half is where they end
        up, and that is the half that goes wrong quietly."""
        self.settings()
        p = R.get("previews").make_plan({"folder": self.shoot, "previews": self.prev})
        self.assertTrue(p.rows)
        for row in p.rows:
            self.assertTrue(row.source)
            self.assertTrue(row.target)
            self.assertNotEqual(row.source, row.target)


class ChoosingFoldersRatherThanTypingThem(Trees):
    """A list of paths in a text box is a list of paths you get wrong. One typo
    and the folder you meant to leave out is scanned anyway, silently - a name
    that matches nothing looks exactly like a name that matches nothing on
    purpose."""

    def test_the_exclusion_box_is_a_list_of_folders_not_free_text(self):
        from app.registry import Folders
        opt = next(o for o in R.get("library").options if o.name == "exclude")
        self.assertIsInstance(opt, Folders)
        self.assertEqual(opt.describe()["kind"], "folders")

    def test_several_folders_travel_as_one_plain_string(self):
        """So the form, the command line, the settings file and a remembered
        value all stay plain text and need no special case."""
        from app.registry import Folders
        self.assertEqual(Folders.chosen("/a/b\n/c/d"), ["/a/b", "/c/d"])
        self.assertEqual(Folders.chosen("/a/b, /c/d"), ["/a/b", "/c/d"])
        self.assertEqual(Folders.chosen("  "), [])
        self.assertEqual(Folders.chosen("/a\n/a"), ["/a"])      # never twice

    def test_and_they_reach_the_survey(self):
        self.settings()
        archive = os.path.join(self.lib, "2019", "Archive")
        os.makedirs(archive, exist_ok=True)
        shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(archive, "old.JPG"))
        p = R.get("library").make_plan({"folder": self.lib, "rescan": True,
                                        "exclude": archive})
        self.assertNotIn("Archive", {n["name"] for n in p.tree})


class SayingWhereALocationCameFrom(Trees):
    def test_every_row_names_its_source(self):
        """With two sources and an order you chose, "where did this pin come
        from" is the first question of any result that looks wrong."""
        ref = os.path.join(self.dir, "Reference")
        os.makedirs(ref)
        shutil.copy(os.path.join(FIX, "phone_doha.jpg"), os.path.join(ref, "r.JPG"))
        p = R.get("geotag").make_plan({"folder": self.shoot, "phone": ref,
                                       "order": "photos", "max_gap": 100000})
        self.assertTrue(p.rows)
        for row in p.rows:
            self.assertIn("from the photo folder", row.detail)


class ATreeStaysATree(Trees):
    """Filter row by row and children are left with no parents above them: ask
    for "location done" and you get three shoots at the third level of
    indentation with nothing over them, which reads as a set of orphaned folders
    rather than a filtered library.

    Some filters happened not to do this, because they test rolled-up totals
    that a parent inherits - but that was luck, not design, and it broke the
    moment a filter asked about a folder's own state."""

    def setUp(self):
        super().setUp()
        deep = os.path.join(self.lib, "2023", "Trip", "Day 1")
        os.makedirs(deep)
        shutil.copy(os.path.join(FIX, "phone_doha.jpg"),
                    os.path.join(deep, "located.JPG"))
        self.settings()

    def tree(self, only):
        return R.get("library").make_plan({"folder": self.lib, "only": only,
                                           "rescan": True}).tree

    def test_every_row_has_its_parent_above_it_whatever_the_filter(self):
        for only in ("all", "unfinished", "raws", "unrated", "unlocated",
                     "nopreviews", "located", "rated", "separated", "previewed"):
            nodes = self.tree(only)
            seen = {n["path"] for n in nodes}
            for n in nodes:
                if n["depth"] == 0:
                    continue
                self.assertIn(os.path.dirname(n["path"]), seen,
                              f"{only}: {n['name']} has nothing above it")

    def test_and_the_depth_never_jumps_a_level(self):
        """The other half of the same symptom: a gap in the levels makes 'one
        level more' appear to do nothing, because the level it opened is not
        there."""
        for only in ("located", "rated", "unfinished"):
            last = -1
            for n in self.tree(only):
                self.assertLessEqual(n["depth"], last + 1,
                                     f"{only}: {n['name']} jumps from {last}")
                last = n["depth"]

    def test_the_folders_only_holding_the_tree_up_are_marked_as_such(self):
        """Shown, because a child with nothing above it reads as an orphan - but
        not pretending to be an answer to what was asked."""
        nodes = self.tree("located")
        by_name = {n["name"]: n["matched"] for n in nodes}
        # 2023 and everything under it IS fully located, so those match in their
        # own right; the library root is not, and is only there to hold them up
        self.assertTrue(by_name["Day 1"])
        self.assertTrue(by_name["2023"])
        self.assertFalse(by_name["Photos"])
        self.assertNotIn("Spain", by_name)          # nothing located, not shown

    def test_asking_for_everything_marks_everything(self):
        self.assertTrue(all(n["matched"] for n in self.tree("all")))

    def test_both_halves_of_each_question_can_be_asked(self):
        """"Which shoots still need a location" and "which are done" are both
        worth asking, and a filter that only answers the first makes you work
        the second out by elimination."""
        offered = {c["value"] for c in
                   next(o for o in R.get("library").options if o.name == "only")
                   .describe()["choices"]}
        for both in ("unlocated", "located", "unrated", "rated",
                     "nopreviews", "previewed"):
            self.assertIn(both, offered)

    def test_the_filter_is_a_row_of_tabs(self):
        self.assertTrue(next(o for o in R.get("library").options
                             if o.name == "only").describe()["tabs"])


class HowBigThePreviewsWillBe(Trees):
    def test_a_row_says_what_it_will_come_out_at(self):
        self.settings()
        p = R.get("previews").make_plan({"folder": self.shoot})
        rows = [r for r in p.rows]
        if not rows:
            self.skipTest("no previews to make in this fixture")
        self.assertIn("about", rows[0].detail)
        self.assertIn("\u2192", rows[0].detail)

    def test_the_plan_says_the_sizes_were_measured_not_guessed(self):
        """And it must actually do it, not merely be able to: a constant table
        checked against a real resize came out four times under."""
        from app.tasks.previews import _pillow
        if _pillow()[0] is None:
            self.skipTest("Pillow is not installed here")
        self.settings()
        p = R.get("previews").make_plan({"folder": self.shoot})
        how = dict(p.stats).get("Sizes estimated", "")
        self.assertIn("weighing", how)

    def test_the_rate_is_measured_from_a_real_photo_not_a_table(self):
        """A bytes-per-pixel table is a guess dressed up as arithmetic: checked
        against a real resize it came out four times under, because how well a
        JPEG compresses depends on the picture and nothing else."""
        from app.tasks.previews import measure_rate, _pillow
        if _pillow()[0] is None:
            self.skipTest("Pillow is not installed here")
        rate = measure_rate(os.path.join(self.shoot, "plain.JPG"), 2048, 85)
        self.assertGreater(rate, 0)


class WhereHistorySits(unittest.TestCase):
    """Somewhere you GO to look back, not a step in any loop - so it is not in
    the sidebar at all. Twenty features with "what happened last week" among
    them reads as twenty steps, nineteen of which you do and one of which you
    do not."""

    def test_it_is_not_in_the_sidebar(self):
        self.assertNotIn("history", [t.name for t in R.in_sidebar()])

    def test_but_it_is_still_a_task_of_its_own(self):
        """Hidden from the sidebar, not hidden from the app: it has a place in
        the header, an address, and the same plan-and-apply shape as the rest."""
        self.assertTrue(R.get("history").hidden)
        self.assertFalse(R.get("history").parent, "it is not a tab under anything")
        self.assertIn("history", [t.name for t in R.top_level()])

    def test_setup_is_the_last_thing_in_the_sidebar(self):
        self.assertEqual([t.name for t in R.in_sidebar()][-1], "setup")


if __name__ == "__main__":
    unittest.main()
