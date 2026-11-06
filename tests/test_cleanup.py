"""The one feature that really removes something.

Everything else in this app moves. That makes most of its tests about whether
the right thing was chosen; here the question is different, because a wrong
answer is not a photograph in the wrong folder, it is a photograph that is gone.

So these are mostly tests about refusing:

- refusing to touch a folder this app did not make, whatever it is called;
- refusing to do anything at all until it has been confirmed in a second place;
- refusing to delete outright when the recycle bin was asked for and is missing,
  rather than quietly doing the irreversible half of what was asked;
- refusing to empty a pile that was added to this morning, when an age was set.

And one test that it actually works, because a safety feature that never does
the job is just a slow way of doing nothing.
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
from core import cleanup as C              # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Tree(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cleanup-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.share = os.path.join(self.dir, "homes")
        self.lib = os.path.join(self.share, "Photos")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def put(self, where, name="plain.JPG", fixture="plain", age=None):
        folder = os.path.join(self.lib, where)
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, name)
        shutil.copy(os.path.join(FIX, fixture + ".jpg"), target)
        if age is not None:
            os.utime(target, (age, age))
        return target

    def bin(self):
        os.makedirs(os.path.join(self.share, C.RECYCLE), exist_ok=True)
        return os.path.join(self.share, C.RECYCLE)

    def plan(self, **over):
        t = R.get("cleanup")
        raw = {"folder": self.lib, "raw": "", "previews": "", "develop": "",
               "recycle": False}
        raw.update(over)
        return t, t.make_plan(raw)


class WhatItFinds(Tree):
    def test_a_culled_folder_is_found_wherever_it_sits(self):
        """They sit beside the shoot they came from, not in one place."""
        self.put("2022/Spain/_Culled")
        self.put("2023/_Culled", name="other.JPG")
        _t, p = self.plan()
        found = sorted(os.path.basename(os.path.dirname(r.source))
                       for r in p.rows)
        self.assertEqual(found, ["2023", "Spain"])

    def test_a_folder_you_made_is_never_listed_at_any_setting(self):
        """Not by what is in it, not by what it is called - only ever by being
        one of the names this app itself uses."""
        self.put("2022/old stuff")
        self.put("2022/delete me", name="rubbish.JPG")
        self.put("2022/Spain")
        _t, p = self.plan(culled=True, duplicates=True, nolocation=True,
                          leftovers=True, empty=True)
        self.assertEqual(p.rows, [], [r.source for r in p.rows])

    def test_a_pile_inside_another_pile_is_counted_once(self):
        """Offering both would let you tick one, remove the other, and wonder
        where it went."""
        self.put("_Duplicates/2022/_Culled")
        _t, p = self.plan(empty=False)          # empty folders are their own row
        self.assertEqual(len(p.rows), 1)
        self.assertTrue(p.rows[0].source.endswith("_Duplicates"))

    def test_each_pile_is_counted_sized_and_dated(self):
        """"Delete the culled folders" with no numbers beside it is not a
        decision anybody can make."""
        self.put("2022/Spain/_Culled", name="a.JPG")
        self.put("2022/Spain/_Culled", name="b.JPG", fixture="rated")
        _t, p = self.plan()
        cells = " ".join(p.rows[0].cells)
        self.assertIn("2 file(s)", cells)
        self.assertIn("KB", cells)
        self.assertIn(time.strftime("%Y"), cells)

    def test_empty_folders_go_from_the_bottom_up(self):
        """A year folder whose shoots have all moved out is empty too - which is
        exactly what reorganising a library leaves behind."""
        os.makedirs(os.path.join(self.lib, "2019", "Rome", "day one"))
        _t, p = self.plan(culled=False, duplicates=False, empty=True)
        order = [r.source for r in p.rows]
        self.assertIn(os.path.join(self.lib, "2019"), order)
        self.assertLess(order.index(os.path.join(self.lib, "2019", "Rome",
                                                 "day one")),
                        order.index(os.path.join(self.lib, "2019")))

    def test_a_folder_with_one_photo_and_a_thumbnail_folder_is_not_litter(self):
        os.makedirs(os.path.join(self.shoot, "@eaDir"))
        self.put("2022/Spain")
        _t, p = self.plan(culled=False, duplicates=False, leftovers=True)
        self.assertNotIn(self.shoot, [r.source for r in p.rows])


class HowCareful(Tree):
    def test_nothing_happens_until_it_is_confirmed_in_a_second_place(self):
        self.put("2022/Spain/_Culled")
        _t, p = self.plan()
        self.assertIs(p.writes, False)
        self.assertTrue(any("tick" in n.lower() for n in p.notes))

    def test_and_the_apply_itself_refuses_too_not_only_the_page(self):
        """The page withholds the button; the API could still be asked. Of
        everything in this app, this is the one to check twice."""
        self.put("2022/Spain/_Culled")
        t, p = self.plan()
        result = t.apply(p)
        self.assertEqual(result.done, 0)
        self.assertTrue(os.path.isdir(os.path.join(self.shoot, "_Culled")))
        self.assertIn("not ticked", " ".join(result.lines()))

    def test_a_pile_added_to_this_morning_is_left_when_an_age_is_set(self):
        """The pile anybody regrets emptying is the recent one, from the cull
        that was wrong before they had noticed."""
        self.put("2022/Spain/_Culled")
        _t, p = self.plan(confirm=True, older_than=30)
        self.assertEqual(p.rows, [])
        self.assertEqual(len(p.skipped), 1)
        self.assertIn("day(s) ago", p.skipped[0][1])

    def test_and_an_old_one_is_not(self):
        self.put("2022/Spain/_Culled", age=time.time() - 200 * 86400)
        _t, p = self.plan(confirm=True, older_than=30)
        self.assertEqual(len(p.rows), 1)

    def test_age_is_measured_from_the_last_thing_put_in_not_the_folder(self):
        """A _Culled folder from last year that was added to this morning is
        this morning's pile."""
        self.put("2022/Spain/_Culled", name="old.JPG",
                 age=time.time() - 300 * 86400)
        self.put("2022/Spain/_Culled", name="new.JPG", fixture="rated")
        _t, p = self.plan(confirm=True, older_than=30)
        self.assertEqual(p.rows, [])

    def test_asking_for_the_recycle_bin_when_there_is_none_refuses(self):
        """Rather than doing the irreversible half of what was asked."""
        self.put("2022/Spain/_Culled")
        _t, p = self.plan(recycle=True, confirm=True)
        self.assertTrue(p.blocked)
        self.assertIn("#recycle", " ".join(p.notes) + p.blocked)

    def test_the_plan_says_out_loud_which_of_the_two_it_is_doing(self):
        self.put("2022/Spain/_Culled")
        _t, outright = self.plan(confirm=True)
        self.assertTrue(any("deleted outright" in n for n in outright.notes))
        self.bin()
        _t, kept = self.plan(confirm=True, recycle=True)
        self.assertTrue(any("#recycle" in n for n in kept.notes))


class DoingIt(Tree):
    def test_a_pile_is_removed_and_the_space_reported(self):
        self.put("2022/Spain/_Culled")
        t, p = self.plan(confirm=True)
        result = t.apply(p)
        self.assertEqual(result.failed, 0)
        self.assertFalse(os.path.isdir(os.path.join(self.shoot, "_Culled")))
        self.assertTrue(any("Space freed" == s[0] for s in result.stats))

    def test_nothing_outside_the_pile_is_touched(self):
        keep = self.put("2022/Spain", name="keep.JPG")
        self.put("2022/Spain/_Culled")
        t, p = self.plan(confirm=True)
        t.apply(p)
        self.assertTrue(os.path.exists(keep))

    def test_into_the_recycle_bin_it_is_a_move_and_the_name_says_where_from(self):
        self.bin()
        self.put("2022/Spain/_Culled")
        t, p = self.plan(confirm=True, recycle=True)
        self.assertEqual(t.apply(p).failed, 0)
        inside = os.listdir(os.path.join(self.share, C.RECYCLE))
        self.assertEqual(len(inside), 1)
        self.assertIn("Photos - 2022 - Spain - _Culled", inside[0])
        self.assertTrue(os.path.exists(os.path.join(
            self.share, C.RECYCLE, inside[0], "plain.JPG")))

    def test_a_row_pointing_somewhere_else_is_refused_at_the_moment_of_doing_it(self):
        """A plan is data, and data can be edited, replayed, or written by a
        test that got the folder wrong. This is the only code path in the app
        that destroys something, so it is the one place worth being impossible
        to talk into it."""
        self.put("2022/Spain/_Culled")
        t, p = self.plan(confirm=True)
        mine = self.put("2022/Spain", name="precious.JPG")
        p.rows[0].data["path"] = self.shoot
        result = t.apply(p)
        self.assertEqual(result.failed, 1)
        self.assertTrue(os.path.exists(mine))
        self.assertIn("not a folder this app made", " ".join(result.lines()))

    def test_a_pile_that_has_already_gone_is_a_failure_not_a_crash(self):
        self.put("2022/Spain/_Culled")
        t, p = self.plan(confirm=True)
        shutil.rmtree(os.path.join(self.shoot, "_Culled"))
        result = t.apply(p)
        self.assertEqual(result.failed, 1)
        self.assertIn("no longer there", " ".join(result.lines()))


class TheRecycleBin(Tree):
    def test_it_is_found_by_walking_up_to_the_share(self):
        self.bin()
        self.assertEqual(C.recycle_root(self.shoot),
                         os.path.join(self.share, C.RECYCLE))

    def test_and_is_never_created(self):
        """Making something that looks like DSM's recycle bin and is not would
        be worse than not having one: nothing would ever empty it."""
        self.assertEqual(C.recycle_root(self.shoot), "")
        self.assertFalse(os.path.isdir(os.path.join(self.share, C.RECYCLE)))

    def test_two_cleanups_of_the_same_folder_do_not_collide(self):
        first = C.recycle_target(self.shoot, self.bin())
        os.makedirs(first)
        from core.paths import safe_target
        self.assertNotEqual(safe_target(first), first)


class NeverTheBin(Tree):
    """The Recycle Bin and DSM's index are not places this app made piles in,
    and walking into them counts the deleted twice - and, with the bin ticked
    off, deletes them from the one place they could still be got back from."""

    def test_a_pile_already_in_the_bin_is_not_listed(self):
        rb = self.bin()
        os.makedirs(os.path.join(rb, "old", "_Culled"))
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(rb, "old", "_Culled", "a.JPG"))
        self.put("2022/Spain/_Culled")
        _t, p = self.plan(folder=self.share, leftovers=True, empty=True)
        self.assertFalse([r.source for r in p.rows if C.RECYCLE in r.source])
        self.assertTrue([r for r in p.rows if r.what == "culled"])

    def test_nor_is_anything_inside_an_eadir(self):
        ea = os.path.join(self.shoot, "@eaDir", "_Culled")
        os.makedirs(ea)
        shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(ea, "t.jpg"))
        _t, p = self.plan(leftovers=True, empty=True)
        self.assertFalse([r.source for r in p.rows if "@eaDir" in r.source])

    def test_a_folder_holding_only_the_bin_is_not_litter_or_empty(self):
        inner = os.path.join(self.lib, "2021")
        os.makedirs(os.path.join(inner, C.RECYCLE))
        _t, p = self.plan(culled=False, duplicates=False, leftovers=True,
                          empty=True)
        self.assertNotIn(inner, [r.source for r in p.rows])

    def test_a_thumbnail_only_folder_is_still_offered_when_asked_for(self):
        """Thumbnail-only folders is asked for by name, so @eaDir counts
        there - and the apply's own second check agrees with the plan."""
        lone = os.path.join(self.lib, "2020")
        os.makedirs(os.path.join(lone, "@eaDir"))
        t, p = self.plan(culled=False, duplicates=False, leftovers=True,
                         empty=False, confirm=True)
        self.assertIn(lone, [r.source for r in p.rows])
        t.apply(p)
        self.assertFalse(os.path.exists(lone))


class SomeTreesWithoutABin(Tree):
    """Asking for the recycle bin and getting a permanent delete for half of
    it is the worst of both. The tree without one is refused, and said so."""

    def setUp(self):
        super().setUp()
        self.bin()
        self.other = os.path.join(self.dir, "elsewhere", "Raw")
        os.makedirs(os.path.join(self.other, "2022", "_Culled"))
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(self.other, "2022", "_Culled", "a.RW2"))
        self.put("2022/Spain/_Culled")

    def test_the_tree_without_a_bin_is_refused_and_left_alone(self):
        t, p = self.plan(raw=self.other, recycle=True, confirm=True)
        self.assertFalse(p.blocked)
        self.assertFalse([r for r in p.rows if r.source.startswith(self.other)])
        self.assertTrue(any("no Recycle Bin" in e for e in p.errors), p.errors)
        t.apply(p)
        self.assertTrue(os.path.isfile(
            os.path.join(self.other, "2022", "_Culled", "a.RW2")))
        self.assertFalse(os.path.isdir(os.path.join(self.shoot, "_Culled")))

    def test_a_plan_that_deletes_says_deleted(self):
        _t, p = self.plan(raw=self.other, recycle=False)
        where = dict(p.stats)["Where they go"]
        self.assertEqual(where, "deleted outright")
        self.assertTrue(all("deleted" in r.detail for r in p.rows),
                        [r.detail for r in p.rows])
        self.assertIn("deleted outright", p.notes[1].lower()
                      if p.notes[0].startswith("Nothing will happen")
                      else p.notes[0].lower())

    def test_a_plan_into_the_bin_says_so_on_every_row(self):
        _t, p = self.plan(recycle=True)
        self.assertEqual(dict(p.stats)["Where they go"], "the recycle bin")
        piles = [r for r in p.rows if r.what == "culled"]
        self.assertTrue(piles)
        self.assertTrue(all("recycle bin" in r.detail for r in piles))


if __name__ == "__main__":
    unittest.main()
