"""Mirroring as a mode, and the three complaints that led to it.

Abu, three times over: "if i dont put the anchor previews and raw still act
stupid... it will always be the anchor is the same photos folder, it should
mirror unless i specify a specific folder i choose manually."

He is right, and the reason it kept happening is that the form asked a question
it already knew the answer to. The three trees are written down once, in Setup.
Asking again in every form - and falling back to "the folder being scanned" when
the box was empty - is what put previews flat in the top of their tree.

So mirroring is a switch, on by default. With it on the roots come from Setup,
the position is worked out from the library, and the destination boxes are along
for the ride: they show where things go rather than deciding it. Turning it off
is what a one-off destination is for.
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

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
WITH_TREES = ["unpair", "previews", "cull", "remirror", "ratings", "retime",
              "library"]


class Trees(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="mirror-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.prev = os.path.join(self.dir, "Photos Previews")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        os.makedirs(self.raw)
        os.makedirs(self.prev)
        for n in ("plain", "rated"):
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(self.shoot, n + ".JPG"))
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(self.shoot, n + ".RW2"))
        S.save({"library": self.lib, "raw": self.raw, "previews": self.prev})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)


class ItIsOfferedEverywhereItApplies(Trees):
    def test_every_task_with_a_tree_has_the_switch(self):
        for name in WITH_TREES:
            names = [o.name for o in R.get(name).options]
            self.assertIn("mirror", names, name)

    def test_and_it_is_on_unless_you_turn_it_off(self):
        for name in WITH_TREES:
            opt = next(o for o in R.get(name).options if o.name == "mirror")
            self.assertTrue(opt.default, name)


class WithItOn(Trees):
    def test_nothing_needs_to_be_typed(self):
        p = R.get("unpair").make_plan({"folder": self.shoot})
        self.assertFalse(p.blocked, p.blocked)
        self.assertEqual([r.target for r in p.rows],
                         [os.path.join(self.raw, "2022", "Spain", n)
                          for n in ("plain.RW2", "rated.RW2")])

    def test_a_stale_path_left_in_the_box_cannot_send_files_anywhere(self):
        """The box shows where things go; it does not decide it. A path left
        over from a previous run is exactly how a shoot ends up in the wrong
        tree, and it is the failure that kept happening."""
        p = R.get("unpair").make_plan({"folder": self.shoot,
                                       "raw": os.path.join(self.dir, "Somewhere Else")})
        for row in p.rows:
            self.assertTrue(row.target.startswith(self.raw), row.target)

    def test_the_anchor_is_always_the_library_never_the_scanned_folder(self):
        """The whole bug in one line. With the anchor falling back to the folder
        being scanned, its position is empty and everything lands flat in the top
        of the other tree."""
        p = R.get("previews").make_plan({"folder": self.shoot})
        self.assertTrue(p.rows)
        for row in p.rows:
            self.assertTrue(row.target.startswith(
                os.path.join(self.prev, "2022", "Spain")), row.target)

    def test_and_it_says_nothing_about_guessing_because_it_did_not(self):
        p = R.get("previews").make_plan({"folder": self.shoot})
        self.assertFalse(any("TOP" in n for n in p.notes), p.notes)


class WithItOff(Trees):
    def test_the_folder_you_choose_is_the_one_used(self):
        elsewhere = os.path.join(self.dir, "Somewhere Else")
        p = R.get("unpair").make_plan({"folder": self.shoot, "raw": elsewhere,
                                       "mirror": False})
        for row in p.rows:
            self.assertTrue(row.target.startswith(elsewhere), row.target)

    def test_and_the_position_inside_it_is_still_mirrored(self):
        """Off means "somewhere else", not "flat". The shoot keeps its shape."""
        elsewhere = os.path.join(self.dir, "Somewhere Else")
        p = R.get("unpair").make_plan({"folder": self.shoot, "raw": elsewhere,
                                       "mirror": False})
        self.assertTrue(p.rows[0].target.startswith(
            os.path.join(elsewhere, "2022", "Spain")), p.rows[0].target)

    def test_a_matching_sub_folder_is_still_read_as_the_top_of_the_tree(self):
        """The follow feature fills these boxes with the matching sub-folder, so
        turning mirroring off must not suddenly write the position twice."""
        elsewhere = os.path.join(self.dir, "Somewhere Else")
        p = R.get("unpair").make_plan(
            {"folder": self.shoot, "mirror": False,
             "raw": os.path.join(elsewhere, "2022", "Spain")})
        self.assertEqual(p.rows[0].target,
                         os.path.join(elsewhere, "2022", "Spain", "plain.RW2"))


class ThePageKnowsAboutIt(Trees):
    def test_the_switch_is_sent_to_the_page_with_the_tree_boxes_marked(self):
        described = R.get("cull").describe()
        by_name = {o["name"]: o for o in described["options"]}
        self.assertEqual(by_name["mirror"]["kind"], "flag")
        self.assertTrue(by_name["raw"]["tree"])
        self.assertTrue(by_name["previews"]["tree"])
        self.assertFalse(by_name["folder"]["tree"])


if __name__ == "__main__":
    unittest.main()
