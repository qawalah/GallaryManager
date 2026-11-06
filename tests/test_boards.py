"""The dashboard as an arrangement you can change, and keep several of.

The thing worth testing hardest is that an arrangement is ONE list. Everything
the editor does - add, remove, reorder - is the same edit to the same list, so
there is no second copy of the order to fall out of step with what is drawn.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.tasks                                # noqa: E402,F401
from core import boards as B                    # noqa: E402
from core import settings as S                  # noqa: E402


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="boards-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        os.makedirs(os.environ["PM_DATA"])
        S.save({"library": self.dir})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)


class OutOfTheBox(_Tmp):
    def test_there_is_always_one_arrangement_and_it_is_the_built_in_one(self):
        self.assertEqual(B.names(), [B.FIRST])
        self.assertEqual(B.now(), B.FIRST)
        self.assertEqual(B.board(), B.BUILTIN)

    def test_every_widget_the_built_in_one_names_actually_exists(self):
        for name in B.BUILTIN:
            self.assertIn(name, B.WIDGETS, name)

    def test_every_widget_has_a_name_a_kind_and_a_line_about_it(self):
        for name, (title, kind, about) in B.WIDGETS.items():
            self.assertTrue(title, name)
            self.assertIn(kind, ("tile", "meter", "donut", "bars"), name)
            self.assertIsInstance(about, str, name)

    def test_nothing_counts_photographs_by_whether_they_have_a_date(self):
        """Every photograph in a library has one, so the meter read 100% for
        everybody, every time, and spent a row saying so."""
        self.assertNotIn("meter:dated", B.WIDGETS)
        self.assertFalse([n for n in B.WIDGETS if "dated" in n])


class ArrangingIt(_Tmp):
    def test_the_list_is_what_is_drawn_and_in_that_order(self):
        B.keep(["chart:year", "tile:photos"])
        self.assertEqual(B.board(), ["chart:year", "tile:photos"])

    def test_a_widget_this_app_has_never_heard_of_is_dropped_not_refused(self):
        """A board saved by a later version has to still open. Refusing to draw
        a dashboard because one line of it is stale is the worst trade there."""
        B.keep(["tile:photos", "chart:hologram", "chart:year"])
        self.assertEqual(B.board(), ["tile:photos", "chart:year"])

    def test_the_same_widget_twice_is_once(self):
        B.keep(["tile:photos", "tile:photos"])
        self.assertEqual(B.board(), ["tile:photos"])

    def test_an_empty_arrangement_is_allowed(self):
        """Taking everything off is a thing somebody may mean, and putting it
        back is one press."""
        B.keep([])
        self.assertEqual(B.board(), [])
        B.reset()
        self.assertEqual(B.board(), B.BUILTIN)

    def test_only_the_dimensions_this_board_needs_are_counted(self):
        """A dashboard with three charts on it should not pay for nine."""
        B.keep(["chart:year", "chart:aperture", "chart:space", "tile:photos"])
        self.assertEqual(B.dims(), ["year", "aperture"])

    def test_a_tile_that_counts_something_still_asks_for_its_dimension(self):
        B.keep(["tile:cameras", "tile:years"])
        self.assertEqual(sorted(B.dims()), ["camera", "year"])

    def test_the_catalogue_says_what_is_on_and_puts_those_first(self):
        B.keep(["chart:year", "tile:photos"])
        got = B.catalogue()
        self.assertEqual([w["name"] for w in got[:2]], ["chart:year", "tile:photos"])
        self.assertTrue(all(w["on"] for w in got[:2]))
        self.assertFalse(any(w["on"] for w in got[2:]))
        self.assertEqual(len(got), len(B.WIDGETS))


class SeveralOfThem(_Tmp):
    def test_a_new_one_is_a_copy_and_becomes_the_one_showing(self):
        B.keep(["tile:photos"])
        B.add("Shooting", like=B.FIRST)
        self.assertEqual(B.now(), "Shooting")
        self.assertEqual(B.board(), ["tile:photos"])
        # and the one it was copied from is untouched
        B.show(B.FIRST)
        self.assertEqual(B.board(), ["tile:photos"])

    def test_editing_one_does_not_touch_the_other(self):
        B.add("Shooting")
        B.keep(["chart:year"])
        B.show(B.FIRST)
        self.assertEqual(B.board(), B.BUILTIN)

    def test_two_with_the_same_name_is_refused(self):
        B.add("Shooting")
        with self.assertRaises(ValueError):
            B.add("Shooting")

    def test_a_nameless_or_enormous_name_is_refused(self):
        for bad in ("", "   ", "x" * 41):
            with self.assertRaises(ValueError, msg=bad):
                B.add(bad)

    def test_renaming_carries_the_arrangement_and_the_showing_mark(self):
        B.add("Shooting")
        B.keep(["chart:year"])
        B.rename("Shooting", "What I shot")
        self.assertEqual(B.now(), "What I shot")
        self.assertEqual(B.board(), ["chart:year"])
        self.assertNotIn("Shooting", B.names())

    def test_the_built_in_one_cannot_be_renamed_or_deleted(self):
        """So there is always one arrangement that is known to work."""
        with self.assertRaises(ValueError):
            B.rename(B.FIRST, "Mine")
        with self.assertRaises(ValueError):
            B.drop(B.FIRST)
        self.assertIn(B.FIRST, B.names())

    def test_deleting_the_one_showing_falls_back_to_the_built_in_one(self):
        B.add("Shooting")
        B.drop("Shooting")
        self.assertEqual(B.now(), B.FIRST)

    def test_resetting_puts_the_built_in_list_back_into_that_one_only(self):
        B.add("Shooting")
        B.keep(["chart:year"])
        B.reset()
        self.assertEqual(B.board(), B.BUILTIN)

    def test_an_arrangement_that_is_not_there_is_refused_not_invented(self):
        for call in (lambda: B.show("Nope"), lambda: B.keep([], "Nope"),
                     lambda: B.drop("Nope"), lambda: B.reset("Nope"),
                     lambda: B.rename("Nope", "Other")):
            with self.assertRaises(ValueError):
                call()

    def test_a_forgotten_current_arrangement_falls_back_rather_than_breaking(self):
        S.save({"dashboards": '{"now": "Gone", "boards": {}}'})
        self.assertEqual(B.now(), B.FIRST)
        self.assertEqual(B.board(), B.BUILTIN)

    def test_rubbish_in_the_settings_is_not_a_broken_dashboard(self):
        S.save({"dashboards": "not json at all"})
        self.assertEqual(B.names(), [B.FIRST])


class ThereIsNoTabForThem(_Tmp):
    """3.1 took the Dashboards settings tab away.

    Everything it did - name one, copy one, put one back - is on the Arrange bar
    beside the dashboard itself, where you are standing when you want it. A
    settings page listing arrangements by name, away from the thing it is
    arranging, is a second place to go to do what is already in front of you.
    """

    def test_the_arrangements_are_still_there_without_it(self):
        B.add("Shooting")
        self.assertIn("Shooting", B.names())
        B.show("Shooting")
        self.assertEqual(B.now(), "Shooting")
        B.drop("Shooting")
        self.assertNotIn("Shooting", B.names())

    def test_and_nothing_registers_a_tab_for_them(self):
        from app import registry as R
        import app.tasks                           # noqa: F401
        self.assertIsNone(R.get("dashboards"))


if __name__ == "__main__":
    unittest.main()
