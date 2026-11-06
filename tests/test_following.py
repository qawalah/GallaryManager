"""One box follows another - and the task undoes it before mirroring.

Pick `Photos/2022/Spain` and the RAW box should already say
`Photos Raw/2022/Spain`. That is what anyone means by the trees following, and
typing the same sub-path into three boxes correctly is exactly the chore Browse
only halved.

But a mirroring destination is supposed to be the TOP of a tree. Hand a task the
matching sub-folder instead - the obvious thing to reach for, and now the thing
the form fills in for you - and the position is written twice:

    Photos Raw/2022/Spain  +  2022/Spain  ->  Photos Raw/2022/Spain/2022/Spain

So the two halves are one feature. `core/paths.follow` fills the box,
`Task.settle_trees` takes the position back off before any task sees it, and
neither is safe without the other. `strip_mirrored_tail` had been sitting in
paths.py, correct and tested, called by nothing at all - which is precisely why
the form could not be made helpful until now.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from core import paths as P                # noqa: E402
from core import settings as S             # noqa: E402
from core import walk                      # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Trees(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="follow-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.prev = os.path.join(self.dir, "Photos Previews")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
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


class FindingTheSamePlaceInAnotherTree(Trees):
    def test_a_sub_folder_follows(self):
        self.assertEqual(P.follow(self.shoot, self.lib, self.raw),
                         os.path.join(self.raw, "2022", "Spain"))

    def test_the_root_itself_has_no_position_to_follow(self):
        self.assertEqual(P.follow(self.lib, self.lib, self.raw), self.raw)

    def test_a_folder_outside_the_tree_is_not_guessed_at(self):
        """Inventing a position for a folder that is not in the tree would be a
        guess dressed as an answer."""
        self.assertEqual(P.follow(os.path.join(self.dir, "Elsewhere"),
                                  self.lib, self.raw), self.raw)


class AndBackAgain(Trees):
    def test_a_followed_box_is_read_as_the_top_of_its_tree(self):
        self.assertEqual(
            P.as_tree_root(os.path.join(self.raw, "2022", "Spain"),
                           self.shoot, self.lib),
            self.raw)

    def test_the_top_itself_is_left_alone(self):
        self.assertEqual(P.as_tree_root(self.raw, self.shoot, self.lib), self.raw)

    def test_an_unrelated_folder_is_left_alone(self):
        """Pointing a tree somewhere else on purpose still has to work."""
        other = os.path.join(self.dir, "Elsewhere")
        self.assertEqual(P.as_tree_root(other, self.shoot, self.lib), other)

    def test_it_never_strips_the_tree_away_entirely(self):
        self.assertEqual(P.as_tree_root(self.raw, self.lib, self.lib), self.raw)


class ThroughARealTask(Trees):
    """The half that matters. If the strip is missing, these land two folders
    deeper than they should and nothing says a word about it."""

    def test_separating_raws_with_a_followed_box_lands_in_the_right_place(self):
        t = R.get("unpair")
        p = t.make_plan({"folder": self.shoot,
                         "raw": os.path.join(self.raw, "2022", "Spain")})
        self.assertFalse(p.blocked, p.blocked)
        self.assertTrue(p.rows)
        for row in p.rows:
            self.assertTrue(
                row.target.startswith(os.path.join(self.raw, "2022", "Spain")),
                row.target)
            self.assertNotIn(os.path.join("Spain", "2022"), row.target)
        self.assertEqual(t.apply(p).failed, 0)
        landed = walk.walk(self.raw).files
        self.assertTrue(landed)
        for f in landed:
            self.assertEqual(os.path.dirname(f),
                             os.path.join(self.raw, "2022", "Spain"), f)

    def test_and_gives_exactly_what_the_tree_root_would_have(self):
        """The two ways of saying it must produce identical plans, or the form
        being helpful has quietly changed what the task does."""
        t = R.get("unpair")
        followed = t.make_plan({"folder": self.shoot,
                                "raw": os.path.join(self.raw, "2022", "Spain")})
        plain = t.make_plan({"folder": self.shoot, "raw": self.raw})
        self.assertEqual([r.target for r in followed.rows],
                         [r.target for r in plain.rows])

    def test_previews_too(self):
        t = R.get("previews")
        p = t.make_plan({"folder": self.shoot,
                         "previews": os.path.join(self.prev, "2022", "Spain")})
        self.assertFalse(p.blocked, p.blocked)
        for row in p.rows:
            self.assertTrue(
                row.target.startswith(os.path.join(self.prev, "2022", "Spain")),
                row.target)
            self.assertNotIn(os.path.join("Spain", "2022"), row.target)

    def test_the_position_is_measured_from_whichever_tree_you_picked_in(self):
        """Sync ratings is pointed at the PREVIEWS tree, not the library, so its
        library and RAW boxes follow from there. Measuring from the library
        would find no position at all and strip nothing."""
        rated = os.path.join(self.prev, "2022", "Spain")
        os.makedirs(rated)
        shutil.copy(os.path.join(FIX, "rated.jpg"), os.path.join(rated, "rated.JPG"))
        t = R.get("ratings")
        opts = t.settle_trees(t.coerce({
            "folder": rated,
            "library": os.path.join(self.lib, "2022", "Spain"),
            "raw": os.path.join(self.raw, "2022", "Spain")}))
        self.assertEqual(opts["library"], self.lib)
        self.assertEqual(opts["raw"], self.raw)


class WhatTheFormIsToldToDoIt(Trees):
    def test_the_page_is_given_the_three_trees(self):
        """It follows a position in the browser, without a round trip per
        keystroke, so it has to know the roots."""
        import app.server as SV
        self.assertTrue(hasattr(SV, "browse"))
        marked = [o.name for o in R.get("cull").options if getattr(o, "tree", False)]
        self.assertIn("raw", marked)
        self.assertIn("previews", marked)

    def test_the_folder_being_scanned_is_not_itself_a_tree_box(self):
        """It is the thing that drives the others; if it followed too it would
        rewrite what you just picked."""
        self.assertFalse(
            getattr(next(o for o in R.get("cull").options if o.name == "folder"),
                    "tree", False))


if __name__ == "__main__":
    unittest.main()
