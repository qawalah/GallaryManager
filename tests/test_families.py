"""The way in: five families, a find box, and nothing lost on the way.

The whole value of a navigation layer is that it covers everything. A family
table that has fallen one feature behind the registry is worse than no table at
all, because the feature it forgot is the one nobody can find.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R                # noqa: E402
import app.tasks                            # noqa: E402,F401
from app import page as P                   # noqa: E402
from core import families                   # noqa: E402


class EveryFeatureIsFiled(unittest.TestCase):
    def test_every_feature_is_in_a_family(self):
        """Every feature, not every top-level one: 3.0 draws the tabs on the
        Tools screen as well, because "Cull by rating" is what somebody looks
        for and it used to be one click inside something else."""
        loose = [t.name for t in R.all_tasks()
                 if not t.inline and not families.of(t.name)]
        self.assertEqual(loose, [], f"not in any family: {loose}")

    def test_and_nothing_is_in_two(self):
        seen = {}
        for fam in families.ALL:
            for name in fam["tasks"]:
                self.assertNotIn(name, seen,
                                 f"{name} is in {seen.get(name)} and {fam['key']}")
                seen[name] = fam["key"]

    def test_a_feature_opened_from_a_row_is_in_no_family(self):
        """"Put a run back" is a thing you do TO a run, and the run is in
        History. A card for it in the tools could only ever say "pick a run
        first" - a dead end with a name on it."""
        inline = sorted(t.name for t in R.all_tasks() if t.inline)
        self.assertEqual(inline, ["forget", "undo"])
        for name in inline:
            self.assertEqual(families.of(name), "")

    def test_a_tab_is_in_the_same_group_as_the_feature_it_is_a_tab_of(self):
        """Opening a tab draws its siblings as a tab row. Cull by rating (in
        Review) used to sit under Clean up (in Maintain), and Space (in
        Maintain) under the Library (in Review) - so the row on screen named
        tools from a group other than the one you had just opened it from."""
        wrong = [f"{t.name} ({families.of(t.name)}) under {t.parent} "
                 f"({families.of(t.parent)})"
                 for t in R.all_tasks()
                 # an inline one is opened from a row, not drawn in a tab row
                 if t.parent and not t.inline
                 and families.of(t.name) != families.of(t.parent)]
        self.assertEqual(wrong, [])

    def test_the_weeding_tools_are_tabs_of_cull_and_space_of_clean_up(self):
        for name in ("blur", "duplicates", "brackets", "thin", "exposure"):
            self.assertEqual(R.get(name).parent, "cull", name)
        self.assertEqual(R.get("cull").parent, "")
        for name in ("space", "tidy"):
            self.assertEqual(R.get(name).parent, "cleanup", name)

    def test_a_family_names_only_features_that_exist(self):
        names = {t.name for t in R.all_tasks()}
        for fam in families.ALL:
            for name in fam["tasks"]:
                self.assertIn(name, names, f"{fam['key']} names {name}")

    def test_settings_is_not_one_of_the_tool_cards(self):
        """"Keep Settings separate" - a list of tools with Password in it reads
        as a job you have not done yet."""
        names = [t.name for t in R.all_tasks()]
        cards = families.catalogue(names)
        self.assertNotIn("settings", [c["key"] for c in cards])
        self.assertIn("settings",
                      [c["key"] for c in families.catalogue(names, True)])
        self.assertTrue(families.is_setting("password"))
        self.assertFalse(families.is_setting("bydate"))

    def test_the_catalogue_carries_nothing_that_is_not_there(self):
        got = families.catalogue(["library", "bydate"])
        self.assertEqual([f["key"] for f in got], ["organize", "review"])
        self.assertEqual(got[1]["tasks"], ["library"])

    def test_a_feature_nobody_filed_is_still_reachable(self):
        """The one thing a navigation layer must never do is lose a feature.
        An unfiled one gets a heading of its own rather than disappearing."""
        got = families.catalogue(["library", "brand-new-thing"])
        self.assertIn("brand-new-thing", got[-1]["tasks"])
        self.assertEqual(got[-1]["key"], "other")

    def test_the_order_is_the_order_you_would_work_in(self):
        self.assertEqual([f["key"] for f in families.FAMILIES],
                         ["organize", "metadata", "review", "develop",
                          "maintain"])

    def test_every_family_says_what_it_is_for(self):
        for fam in families.ALL:
            self.assertTrue(fam["note"].strip(), fam["key"])
            self.assertLessEqual(len(fam["label"].split()), 4, fam["key"])


class TheFindBoxCanFindThings(unittest.TestCase):
    """The page matches on title, tab, summary and family. These check the
    WORDS are there to be matched - a feature whose summary is empty cannot be
    found by what it does, only by what it is called."""

    def test_every_feature_has_words_to_be_found_by(self):
        thin = [t.name for t in R.all_tasks()
                if not t.summary.strip() and not t.title.strip()]
        self.assertEqual(thin, [])

    def test_the_obvious_searches_land_somewhere(self):
        """The words somebody types before they know what the feature is
        called."""
        for word, wanted in [("password", "password"), ("duplicate", "duplicates"),
                             ("blurry", "blur"), ("recycle", "delfolder"),
                             ("timeline", "import-timeline"),
                             ("sample", "demo")]:
            hits = [t.name for t in R.all_tasks()
                    if word in " ".join([t.title, t.tab or "", t.summary]).lower()]
            self.assertIn(wanted, hits, f"{word!r} does not find {wanted}")


class TheMenuIsBuiltFromIt(unittest.TestCase):
    def test_the_page_draws_families_rather_than_a_flat_list(self):
        self.assertIn("cats", P.PAGE)
        self.assertIn("Find a tool", P.PAGE)

    def test_and_asks_the_server_for_them(self):
        """Hard-coded in the page, the table would be in two places and one of
        them would rot. Checked by looking for a family's own NOTE, which is a
        whole sentence and could not be in the page by coincidence."""
        self.assertIn("info.families", P.PAGE)
        for fam in families.FAMILIES:
            self.assertNotIn(fam["note"], P.PAGE,
                             f"{fam['key']} is written into the page as well")


if __name__ == "__main__":
    unittest.main()


class ArrangedYourOwnWay(unittest.TestCase):
    """The built-in grouping is a good default and a bad rule.

    What has to hold however somebody rearranges it: no feature is in two
    groups, no feature is lost, and putting one away takes it out of the lists
    and nothing else.
    """

    def setUp(self):
        import tempfile
        self.home = tempfile.mkdtemp(prefix="arr-")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        families.forget_arrangement()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.home, ignore_errors=True)

    def names(self):
        return [t.name for t in R.all_tasks() if not t.inline]

    def test_with_nothing_said_it_is_the_five_this_app_ships_with(self):
        got = families.arranged()
        self.assertFalse(got["mine"])
        self.assertEqual([g["key"] for g in got["groups"]],
                         [f["key"] for f in families.FAMILIES] + ["flows"])

    def test_a_feature_can_be_put_in_a_group_of_your_own(self):
        families.save_arranged([{"label": "My week",
                                 "tasks": ["geotag", "retime"]}])
        cat = families.catalogue(self.names())
        mine = [f for f in cat if f["label"] == "My week"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["tasks"], ["geotag", "retime"])

    def test_and_nothing_is_lost_by_rearranging(self):
        """A feature in no group is still a feature you can find - it falls into
        the catch-all, visibly, rather than disappearing."""
        families.save_arranged([{"label": "Just these", "tasks": ["bydate"]}])
        cat = families.catalogue(self.names())
        shown = {n for f in cat for n in f["tasks"]}
        for name in self.names():
            if families.is_setting(name):
                continue
            self.assertIn(name, shown, name)

    def test_a_feature_cannot_end_up_in_two_groups(self):
        families.save_arranged([{"label": "One", "tasks": ["bydate", "cull"]},
                                {"label": "Two", "tasks": ["cull"]}])
        cat = families.catalogue(self.names())
        seen = {}
        for fam in cat:
            for name in fam["tasks"]:
                self.assertNotIn(name, seen, f"{name} is in two groups")
                seen[name] = fam["key"]

    def test_putting_one_away_takes_it_out_of_the_lists_and_nothing_else(self):
        families.save_arranged([], ["duplicates"])
        cat = families.catalogue(self.names())
        shown = {n for f in cat for n in f["tasks"]}
        self.assertNotIn("duplicates", shown)
        # still a real feature: this is a list it is out of, not a deletion
        self.assertTrue(R.get("duplicates"))
        self.assertIn("duplicates", families.arranged()["hidden"])

    def test_and_it_comes_back(self):
        families.save_arranged([], ["duplicates"])
        families.save_arranged([], [])
        shown = {n for f in families.catalogue(self.names()) for n in f["tasks"]}
        self.assertIn("duplicates", shown)

    def test_settings_are_not_part_of_an_arrangement(self):
        """They are not tools, they have their own page, and a rearrangement
        that could swallow Password would be one nobody could undo."""
        families.save_arranged([{"label": "Everything", "tasks": self.names()}])
        cat = families.catalogue(self.names(), with_settings=True)
        settings = [f for f in cat if f["key"] == "settings"]
        self.assertEqual(len(settings), 1)
        self.assertIn("password", settings[0]["tasks"])

    def test_nonsense_in_the_setting_is_the_built_in_grouping(self):
        from core import settings as S
        S.save({"tool_groups": "{not json"})
        self.assertFalse(families.arranged()["mine"])

    def test_and_it_can_be_put_back_to_what_it_was(self):
        families.save_arranged([{"label": "Mine", "tasks": ["bydate"]}])
        self.assertTrue(families.arranged()["mine"])
        families.forget_arrangement()
        self.assertFalse(families.arranged()["mine"])


class PinnedToTheMainList(unittest.TestCase):
    """The two or three features somebody does every day, at the top level.

    Which two is different for every person, so it cannot be a decision this app
    makes once - and it must not become a second list of everything, which is
    why there is a cap.
    """

    def setUp(self):
        import tempfile
        self.home = tempfile.mkdtemp(prefix="pin-")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.home, ignore_errors=True)

    def test_nothing_is_pinned_to_begin_with(self):
        self.assertEqual(families.pinned(), [])

    def test_a_feature_can_be_pinned_and_unpinned(self):
        families.pin(["geotag"])
        self.assertEqual(families.pinned(), ["geotag"])
        families.pin([])
        self.assertEqual(families.pinned(), [])

    def test_the_order_is_the_order_you_pinned_them(self):
        families.pin(["geotag", "cull", "bydate"])
        self.assertEqual(families.pinned(), ["geotag", "cull", "bydate"])

    def test_the_same_one_twice_is_once(self):
        families.pin(["geotag", "geotag"])
        self.assertEqual(families.pinned(), ["geotag"])

    def test_and_it_cannot_become_the_list_of_everything_again(self):
        families.pin([t.name for t in R.all_tasks()])
        self.assertLessEqual(len(families.pinned()), 12)

    def test_nonsense_in_the_setting_pins_nothing(self):
        from core import settings as S
        S.save({"pinned_tools": "{not json"})
        self.assertEqual(families.pinned(), [])
