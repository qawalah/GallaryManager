"""The same photo twice - and the four ways this feature could do real harm.

Finding identical files is the easy half and barely needs a test. What needs one
is everything this must NOT call a duplicate, because each of those mistakes is
silent, plausible, and expensive:

- a bracket (three frames, one second, one camera)
- a burst (the same, without even the differing bias)
- a RAW sitting beside the JPEG it belongs to
- a preview of a photo

Every one of them shares the properties a naive rule would match on. The tests
below are mostly about those, not about the finding.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from core import duplicates as D           # noqa: E402
from core import walk                      # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
BRACKET = ["aeb1", "aeb2", "aeb3"]
BURST = ["burst1", "burst2", "burst3"]


class Tree(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="dupes-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def put(self, fixture, where, as_name=None, age=None):
        folder = os.path.join(self.lib, where) if where else self.lib
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, as_name or (fixture + ".JPG"))
        shutil.copy(os.path.join(FIX, fixture + ".jpg"), target)
        if age is not None:
            os.utime(target, (age, age))
        return target

    def find(self, **over):
        return D.find(walk.walk(self.lib).files, **over)

    def run_task(self, **raw):
        t = R.get("duplicates")
        p = t.make_plan({"folder": self.lib, **raw})
        return t, p


class IdenticalFiles(Tree):
    def test_the_same_file_in_two_folders_is_one_set(self):
        self.put("plain", "2022/Spain")
        self.put("plain", "2023/Copy")
        got = self.find()
        self.assertEqual(len(got.groups), 1)
        self.assertTrue(got.groups[0].certain)
        self.assertEqual(got.groups[0].size, 2)

    def test_three_copies_are_one_set_of_three_not_three_sets(self):
        self.put("plain", "a")
        self.put("plain", "b")
        self.put("plain", "c")
        got = self.find()
        self.assertEqual(len(got.groups), 1)
        self.assertEqual(got.groups[0].size, 3)
        self.assertEqual(len(got.groups[0].others), 2)

    def test_different_photos_are_not_a_set_however_alike(self):
        self.put("aeb1", "2022/Spain")
        self.put("aeb2", "2022/Spain")
        self.assertEqual(self.find().groups, [])

    def test_a_lone_file_is_never_opened(self):
        """Reading whole files over SMB is the whole cost. Nothing with a size
        of its own should ever be hashed."""
        self.put("plain", "a")
        self.put("aeb1", "b")
        got = self.find()
        self.assertEqual(got.read, 0)
        self.assertEqual(got.bytes_read, 0)


class ThingsThatAreNotDuplicates(Tree):
    def test_a_bracket_is_not_three_copies_of_one_photo(self):
        """One second, one camera, three frames. The frames differ, so tier one
        cannot match them - and the names differ, so tier two cannot either.
        This is the mistake that would leave one exposure of three."""
        for n in BRACKET:
            self.put(n, "2022/Spain")
        self.assertEqual(self.find(include_resaved=True).groups, [])

    def test_nor_is_a_burst(self):
        for n in BURST:
            self.put(n, "2022/Spain")
        self.assertEqual(self.find(include_resaved=True).groups, [])

    def test_a_raw_beside_its_jpeg_is_not_a_copy_of_it(self):
        """They share capture time, camera and base name - that IS the pairing
        identity - and here the bytes are identical too, which is the worst
        case. Different kinds are never compared."""
        self.put("plain", "2022/Spain", as_name="plain.JPG")
        self.put("plain", "2022/Spain", as_name="plain.RW2")
        self.assertEqual(self.find(include_resaved=True).groups, [])

    def test_two_photos_that_merely_share_a_second_are_not_a_set(self):
        self.put("plain", "2022/Spain")
        self.put("rated", "2022/Spain")
        self.assertEqual(self.find(include_resaved=True).groups, [])

    def test_camera_names_are_not_copy_markers(self):
        """IMG_1234 and DSC_0001 are what every camera calls its files. Treating
        a trailing _number as a copy marker turns a whole card into one photo."""
        self.assertFalse(D.looks_copied("IMG_1234"))
        self.assertEqual(D.original_stem("P1000123"), "P1000123")
        self.assertEqual(D.original_stem("Photocopy"), "Photocopy")


class TheSamePhotoSavedAgain(Tree):
    def setUp(self):
        super().setUp()
        self.put("plain", "2022/Spain", as_name="plain.JPG")
        # same photo, re-saved: same capture time, camera and name, other bytes
        again = self.put("plain", "2023/Import", as_name="plain.JPG")
        with open(again, "ab") as fh:
            fh.write(b"\x00" * 32)

    def test_it_is_found_but_marked_probable(self):
        got = self.find(include_resaved=True)
        self.assertEqual(len(got.groups), 1)
        self.assertFalse(got.groups[0].certain)

    def test_it_is_always_LOOKED_for_even_though_it_is_not_acted_on(self):
        """The option decides what moves, not what is examined. A set you cannot
        see is one you cannot make a decision about."""
        self.assertEqual(len(self.find().groups), 1)
        _t, p = self.run_task()                     # resaved off
        self.assertEqual(p.rows, [])                # nothing moves
        self.assertTrue(p.skipped)                  # but it is on the page

    def test_a_third_copy_joins_the_same_set_rather_than_going_unreported(self):
        """The gap two separate passes would leave. A photo held three ways -
        original, byte-identical copy, re-saved version - must come out as ONE
        set of three. Settle the identical pair first and the re-saved one has
        nobody left to pair with, and a real duplicate is reported as neither."""
        self.put("plain", "2024", as_name="plain.JPG")     # identical to the first
        got = self.find(include_resaved=True)
        self.assertEqual(len(got.groups), 1)
        self.assertEqual(got.groups[0].size, 3)
        self.assertFalse(got.groups[0].certain)   # a judged link built it

    def test_a_copy_marker_in_the_name_still_matches(self):
        self.put("plain", "2024", as_name="plain (1).JPG")
        got = self.find(include_resaved=True)
        self.assertEqual(len(got.groups), 1)
        self.assertEqual(got.groups[0].size, 3)


class WhichOneSurvives(Tree):
    """It must be predictable before you press anything, and identical between
    two runs. Whichever the walk happened to see first is neither."""

    def test_a_name_without_a_copy_marker_wins(self):
        self.put("plain", "2022", as_name="shot.JPG", age=2_000_000)
        self.put("plain", "2022", as_name="shot (1).JPG", age=1_000_000)
        got = self.find()
        self.assertEqual(os.path.basename(got.groups[0].keep.path), "shot.JPG")

    def test_then_the_older_file(self):
        self.put("plain", "2022", as_name="a.JPG", age=1_000_000)
        self.put("plain", "2022", as_name="b.JPG", age=2_000_000)
        got = self.find()
        self.assertEqual(os.path.basename(got.groups[0].keep.path), "a.JPG")

    def test_something_already_put_aside_never_beats_a_live_file(self):
        self.put("plain", "_Culled/2022", as_name="a.JPG", age=1_000_000)
        live = self.put("plain", "2022", as_name="z.JPG", age=2_000_000)
        got = D.find([live, os.path.join(self.lib, "_Culled", "2022", "a.JPG")])
        self.assertEqual(got.groups[0].keep.path, live)

    def test_the_answer_does_not_depend_on_the_order_files_arrive_in(self):
        a = self.put("plain", "2022", as_name="a.JPG", age=1_000_000)
        b = self.put("plain", "2022", as_name="b.JPG", age=2_000_000)
        one = D.find([a, b]).groups[0].keep.path
        two = D.find([b, a]).groups[0].keep.path
        self.assertEqual(one, two)


class TheRuleYouChoose(Tree):
    """The Windows app asked which copy to keep, and the port did not.

    That was the missing half: "it keeps one of them" is not something you can
    check. A library is filed several ways at once - a shoot near the top, a
    card dump six levels down, an export folder of re-saves dated today - and
    which of those holds the original depends on what you were doing.
    """

    def two(self):
        """The same photo high in the tree and deep in it, the deep one older."""
        high = self.put("plain", "2022", as_name="shot.JPG", age=2_000_000)
        deep = self.put("plain", "2022/Spain/day one", as_name="shot.JPG",
                        age=1_000_000)
        return high, deep

    def keep(self, **over):
        high, deep = self.two()
        got = D.find([high, deep], **over)
        return got.groups[0].keep.path, high, deep

    def test_closest_to_the_top(self):
        kept, high, _deep = self.keep(rule="shallowest")
        self.assertEqual(kept, high)

    def test_deepest_in_the_tree(self):
        kept, _high, deep = self.keep(rule="deepest")
        self.assertEqual(kept, deep)

    def test_the_oldest_file(self):
        kept, _high, deep = self.keep(rule="oldest")
        self.assertEqual(kept, deep)

    def test_the_newest_file(self):
        kept, high, _deep = self.keep(rule="newest")
        self.assertEqual(kept, high)

    def test_first_alphabetically(self):
        kept, high, deep = self.keep(rule="alpha")
        self.assertEqual(kept, sorted([high, deep], key=str.lower)[0])

    def test_a_rule_nobody_recognises_falls_back_rather_than_failing(self):
        """A scheduled run with a typo in it must still keep the right file -
        the alternative is a crash at three in the morning, or worse, a rule
        that silently means "whichever was found first"."""
        kept, _high, deep = self.keep(rule="nonsense")
        self.assertEqual(kept, deep)          # the same answer as 'smart'

    def test_every_rule_gives_the_same_answer_whatever_order_they_arrive_in(self):
        for rule in D.RULES:
            high, deep = self.two()
            one = D.find([high, deep], rule=rule).groups[0].keep.path
            two = D.find([deep, high], rule=rule).groups[0].keep.path
            self.assertEqual(one, two, rule)
            shutil.rmtree(os.path.join(self.lib, "2022"))


class TheFolderThatWins(Tree):
    """The A-versus-B choice. The app decides by rule; this is how you disagree
    with it for one pair of folders without hunting for a rule that happens to
    agree with you."""

    def setUp(self):
        super().setUp()
        # Two folders that do not contain each other, because a folder that
        # holds BOTH copies is not a preference between them - it matches each
        # of them equally and the rule decides, which is right and is not what
        # these tests are about.
        self.high = self.put("plain", "2022/Spain", as_name="shot.JPG",
                             age=2_000_000)
        self.deep = self.put("plain", "card dump/day one", as_name="shot.JPG",
                             age=1_000_000)
        self.A = os.path.dirname(self.high)
        self.B = os.path.dirname(self.deep)

    def test_a_listed_folder_beats_one_that_is_not(self):
        got = D.find([self.high, self.deep], prefer=[self.A])
        self.assertEqual(got.groups[0].keep.path, self.high)

    def test_a_folder_holding_both_copies_decides_nothing(self):
        """And must not pretend to. Naming the library as the folder that wins
        is not an answer to "which of these two files"."""
        got = D.find([self.high, self.deep], rule="deepest", prefer=[self.lib])
        self.assertEqual(got.groups[0].keep.path, self.deep)

    def test_and_it_beats_the_rule_rather_than_being_a_tiebreak(self):
        """The rule says keep the deepest; the list says keep the other one.
        A preference that only applies when nothing else decided is not a
        preference, it is a coincidence."""
        got = D.find([self.high, self.deep], rule="deepest", prefer=[self.A])
        self.assertEqual(got.groups[0].keep.path, self.high)

    def test_the_list_is_in_order_and_the_first_match_wins(self):
        both = [self.B, self.A]
        self.assertEqual(D.find([self.high, self.deep], prefer=both)
                         .groups[0].keep.path, self.deep)
        self.assertEqual(D.find([self.high, self.deep], prefer=both[::-1])
                         .groups[0].keep.path, self.high)

    def test_but_a_put_aside_file_still_never_wins(self):
        """Otherwise naming a folder that happens to contain _Culled quietly
        undoes a cull: the culled copy is kept and the live one is filed away
        as its duplicate."""
        culled = self.put("plain", "_Culled/2022", as_name="shot.JPG",
                          age=1_000_000)
        got = D.find([self.high, culled], prefer=[self.lib])
        self.assertEqual(got.groups[0].keep.path, self.high)

    def test_the_plan_says_why_that_one_and_not_just_which(self):
        t = R.get("duplicates")
        p = t.make_plan({"folder": self.lib, "raw": "", "previews": "",
                         "develop": "", "prefer": self.A})
        self.assertTrue(p.rows)
        self.assertIn("folder you chose", p.rows[0].cells[2])


class GatheredByFolder(Tree):
    """Four hundred duplicate files are not four hundred decisions. They are
    this folder against that one, a dozen times over - and the heading has to
    name BOTH folders, or you have to open a row to find out what the question
    was."""

    def setUp(self):
        super().setUp()
        # Three different photographs, each of them existing twice. All three
        # the SAME photograph would be one set of six, not three sets of two -
        # and then the copies come from both folders, which is a different
        # thing entirely and not what a pair of folders means.
        for fixture, name in (("plain", "a"), ("rated", "b"), ("burst1", "c")):
            self.put(fixture, "2022/Spain", as_name=name + ".JPG", age=1_000_000)
            self.put(fixture, "card dump", as_name=name + " (1).JPG",
                     age=2_000_000)

    def plan(self, **over):
        t = R.get("duplicates")
        return p_of(t, {"folder": self.lib, "raw": "", "previews": "",
                        "develop": "", **over})

    def test_one_heading_for_the_pair_not_one_per_file(self):
        p = self.plan()
        self.assertEqual(len(p.groups), 1)
        self.assertEqual(len(p.rows), 3)

    def test_the_heading_names_both_folders(self):
        p = self.plan()
        label = p.groups[0]["label"] + " " + p.groups[0]["note"]
        self.assertIn("card dump", label)
        self.assertIn("Spain", label)

    def test_it_says_how_big_each_folder_is_not_only_how_many_are_copies(self):
        """"Nine copies here" reads very differently once you know the folder
        holds nine files and nothing else."""
        p = self.plan()
        joined = " ".join(p.groups[0]["cells"])
        self.assertIn("3 copy(s)", joined)
        self.assertIn("3 file(s)", joined)

    def test_and_offers_either_folder_as_the_one_to_keep(self):
        p = self.plan()
        offered = [a["value"] for a in p.groups[0]["actions"]]
        self.assertIn(os.path.join(self.lib, "card dump"), offered)
        self.assertIn(os.path.join(self.lib, "2022", "Spain"), offered)
        for a in p.groups[0]["actions"]:
            self.assertEqual(a["option"], "prefer")

    def test_taking_one_of_those_offers_turns_the_pair_round(self):
        """Which is the whole point: pressing it is the same as typing that
        folder into the option, and the answer changes completely."""
        dump = os.path.join(self.lib, "card dump")
        p = self.plan(prefer=dump)
        for row in p.rows:
            self.assertTrue(row.source.startswith(os.path.join(self.lib, "2022")),
                            row.source)

    def test_every_row_belongs_to_a_heading_that_exists(self):
        """A row gathered under a heading that was never sent is a row nobody
        sees - and this is a list of things about to be moved."""
        p = self.plan()
        keys = {g["key"] for g in p.groups}
        for row in p.rows:
            self.assertIn(row.group, keys)


def p_of(task, raw):
    return task.make_plan(raw)


class WhatThePlanSays(Tree):
    """The list you read before pressing anything has to be worth reading."""

    def setUp(self):
        super().setUp()
        self.put("plain", "2022/Spain", as_name="plain.JPG", age=1_000_000)
        again = self.put("plain", "2023/Import", as_name="plain.JPG", age=2_000_000)
        with open(again, "ab") as fh:
            fh.write(b"\x00" * 32)

    def test_a_probable_set_is_listed_with_what_it_would_have_done(self):
        _t, p = self.run_task()
        self.assertEqual(p.rows, [])
        self.assertEqual(len(p.skipped), 1)
        self.assertIn("probable", p.skipped[0][1])
        self.assertIn("would move aside", p.skipped[0][1].lower())

    def test_and_the_notes_say_it_is_waiting_on_you(self):
        _t, p = self.run_task()
        self.assertTrue(any("Tick the box" in n for n in p.notes))

    def test_a_set_being_acted_on_is_not_also_in_the_left_alone_list(self):
        """A 'left alone' list that repeats what is being done teaches you to
        skim it, and this is the one list worth reading properly."""
        _t, p = self.run_task(resaved=True)
        self.assertTrue(p.rows)
        self.assertEqual(p.skipped, [])

    def test_every_row_names_the_copy_that_is_being_kept(self):
        _t, p = self.run_task(resaved=True)
        for row in p.rows:
            if row.what == "sidecar":
                continue
            self.assertIn("keeping", row.detail)


class TheTask(Tree):
    def test_it_plans_a_move_into_duplicates_keeping_the_position(self):
        self.put("plain", "2022/Spain", age=1_000_000)
        self.put("plain", "2023/Import", age=2_000_000)
        _t, p = self.run_task()
        self.assertFalse(p.blocked, p.blocked)
        self.assertEqual(len(p.rows), 1)
        row = p.rows[0]
        self.assertIn("_Duplicates", row.target)
        self.assertTrue(row.target.endswith(os.path.join("2023", "Import", "plain.JPG")))

    def test_previewing_moves_nothing(self):
        self.put("plain", "a")
        self.put("plain", "b")
        before = sorted(walk.walk(self.lib).files)
        self.run_task()
        self.assertEqual(sorted(walk.walk(self.lib).files), before)

    def test_applying_leaves_exactly_one_of_each_where_it_was(self):
        kept = self.put("plain", "2022/Spain", age=1_000_000)
        self.put("plain", "2023/Import", age=2_000_000)
        t, p = self.run_task()
        r = t.apply(p)
        self.assertEqual(r.failed, 0)
        self.assertTrue(os.path.isfile(kept))
        self.assertTrue(os.path.isfile(os.path.join(
            self.lib, "_Duplicates", "2023", "Import", "plain.JPG")))

    def test_nothing_is_ever_deleted(self):
        self.put("plain", "a", age=1_000_000)
        self.put("plain", "b", age=2_000_000)
        t, p = self.run_task()
        t.apply(p)
        self.assertEqual(len(walk.walk(self.lib, include_ours=True).files), 2)

    def test_a_sidecar_travels_with_the_copy_it_belongs_to(self):
        """An .xmp left behind does not lose a rating loudly - the file simply
        reads as unrated from then on."""
        self.put("plain", "2022/Spain", age=1_000_000)
        moved = self.put("plain", "2023/Import", age=2_000_000)
        side = os.path.splitext(moved)[0] + ".xmp"
        with open(side, "w", encoding="utf-8") as fh:
            fh.write("<x/>")
        t, p = self.run_task()
        t.apply(p)
        self.assertFalse(os.path.exists(side))
        self.assertTrue(os.path.isfile(os.path.join(
            self.lib, "_Duplicates", "2023", "Import", "plain.xmp")))

    def test_running_it_across_the_library_and_the_previews_tree_is_refused(self):
        """A folder INSIDE the previews tree. The previews tree itself is one
        tree, and checking it on its own is allowed (see below)."""
        previews = os.path.join(self.lib, "previews")
        os.makedirs(os.path.join(previews, "2022"))
        t = R.get("duplicates")
        p = t.make_plan({"folder": os.path.join(previews, "2022"),
                         "previews": previews})
        self.assertTrue(p.blocked)
        self.assertIn("one tree at a time", p.blocked.lower())

    def test_a_previews_tree_inside_the_library_is_left_out_not_matched(self):
        self.put("plain", "2022/Spain", as_name="plain.JPG")
        previews = os.path.join(self.lib, "Previews")
        os.makedirs(os.path.join(previews, "2022", "Spain"))
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(previews, "2022", "Spain", "plain.JPG"))
        _t, p = self.run_task(previews=previews)
        self.assertFalse(p.blocked, p.blocked)
        self.assertEqual(p.rows, [])



class TheButtonCountsCopies(Tree):
    def test_a_copy_and_its_sidecar_are_one_copy(self):
        self.put("plain", "2022/Spain")
        copy = self.put("plain", "Card dump")
        with open(os.path.splitext(copy)[0] + ".xmp", "w") as fh:
            fh.write("<x:xmpmeta xmlns:x='adobe:ns:meta/'/>")
        t, p = self.run_task(raw="", previews="")
        self.assertFalse(p.blocked, p.blocked)
        self.assertEqual(len(p.rows), 2, [r.name for r in p.rows])
        self.assertEqual(R.impact_of(t, p)["count"], 1)



class WhichTreeAndWhereThePileGoes(Tree):
    def test_the_raw_tree_can_be_checked_on_its_own(self):
        """Its help said so; `under` is true of a folder and itself, so the
        RAW tree was refused as being inside the RAW tree."""
        raw = os.path.join(self.dir, "Photos Raw")
        for where in ("2022", "Card"):
            os.makedirs(os.path.join(raw, where))
            shutil.copy(os.path.join(FIX, "plain.jpg"),
                        os.path.join(raw, where, "P1.RW2"))
        t = R.get("duplicates")
        p = t.make_plan({"folder": raw, "raw": raw, "previews": ""})
        self.assertFalse(p.blocked, p.blocked)
        self.assertEqual(len(p.rows), 1, [r.source for r in p.rows])
        self.assertTrue(p.rows[0].target.startswith(
            os.path.join(raw, "_Duplicates") + os.sep), p.rows[0].target)

    def test_a_folder_inside_the_raw_tree_is_still_refused(self):
        raw = os.path.join(self.dir, "Photos Raw")
        os.makedirs(os.path.join(raw, "2022"))
        t = R.get("duplicates")
        p = t.make_plan({"folder": os.path.join(raw, "2022"), "raw": raw})
        self.assertTrue(p.blocked)

    def test_checking_one_shoot_builds_the_pile_at_the_library_root(self):
        from core import settings as S
        S.save({"library": self.lib})
        self.put("plain", "2022/Spain")
        self.put("plain", "2022/Spain/Again")
        t = R.get("duplicates")
        p = t.make_plan({"folder": os.path.join(self.lib, "2022"), "raw": "",
                         "previews": ""})
        self.assertEqual(len(p.rows), 1)
        self.assertTrue(p.rows[0].target.startswith(
            os.path.join(self.lib, "_Duplicates") + os.sep), p.rows[0].target)

    def test_the_button_names_the_pile_not_the_trees_it_leaves_out(self):
        from core import settings as S
        S.save({"library": self.lib})
        raw = os.path.join(self.dir, "Photos Raw")
        os.makedirs(raw)
        self.put("plain", "2022/Spain")
        self.put("plain", "Card dump")
        t = R.get("duplicates")
        p = t.make_plan({"folder": self.lib, "raw": raw, "previews": ""})
        into = R.impact_of(t, p)["into"]
        self.assertEqual([w["path"] for w in into],
                         [os.path.join(self.lib, "_Duplicates")])


if __name__ == "__main__":
    unittest.main()
