"""Set once, read everywhere - and the ways that could quietly not be true.

The claim Setup makes is that filling in three boxes changes what every other
feature does. That claim is only worth making if it holds on the command line and
in the web form alike, if typing something in still overrides it for one run, and
if the bracket settings really are the same settings all three features read.
Each of those is a test here, because each of them is a thing that would look
fine and be false.
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


class Fresh(unittest.TestCase):
    """Every test gets its own settings file. None of them sees the real one."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="setup-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.prev = os.path.join(self.dir, "Photos Previews")
        os.makedirs(self.lib)

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def save(self, **over):
        t = R.get("setup")
        p = t.make_plan({"library": self.lib, "raw": self.raw,
                         "previews": self.prev, **over})
        self.assertFalse(p.blocked, p.blocked)
        r = t.apply(p)
        self.assertEqual(r.failed, 0)
        return p, r


class TheSettingsFile(Fresh):
    def test_nothing_saved_yet_means_the_defaults_not_an_error(self):
        s = S.load()
        self.assertFalse(s.existed)
        self.assertEqual(s["preview_profile"], "medium")
        self.assertTrue(s["bracket_group"])

    def test_what_is_saved_comes_back(self):
        self.save()
        s = S.load()
        self.assertTrue(s.existed)
        self.assertEqual(s["library"], self.lib)
        self.assertEqual(s["raw"], self.raw)

    def test_saving_one_thing_keeps_the_others(self):
        self.save()
        S.save({"bracket_gap": 8})
        s = S.load()
        self.assertEqual(s["bracket_gap"], 8)
        self.assertEqual(s["library"], self.lib)

    def test_a_damaged_file_gives_the_defaults_rather_than_failing(self):
        """The app has to start. A settings file is not worth refusing to run over."""
        self.save()
        with open(S.store_path(S.FILE), "w", encoding="utf-8") as fh:
            fh.write("{ this is not json at all")
        s = S.load()
        self.assertEqual(s["preview_profile"], "medium")

    def test_a_stray_key_in_the_file_is_ignored(self):
        S.save({"library": self.lib})
        import json
        path = S.store_path(S.FILE)
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        raw["something_invented"] = "x"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(raw, fh)
        self.assertEqual(S.load()["library"], self.lib)


class PreviewSizes(Fresh):
    def test_a_named_profile_decides_both_numbers(self):
        self.save(preview_profile="large")
        self.assertEqual(S.load().preview_size(), (3200, 92))

    def test_a_named_profile_beats_a_stale_custom_number(self):
        """Picking Medium while 3200 sits in the custom box must not give Large."""
        self.save(preview_profile="medium", preview_long_edge=3200,
                  preview_quality=92)
        self.assertEqual(S.load().preview_size(), (2048, 85))

    def test_custom_uses_the_numbers(self):
        self.save(preview_profile="custom", preview_long_edge=1000,
                  preview_quality=70)
        self.assertEqual(S.load().preview_size(), (1000, 70))


class ItReachesTheOtherTasks(Fresh):
    def test_a_task_form_starts_from_the_saved_trees(self):
        self.save()
        for name, option, expected in (("unpair", "raw", self.raw),
                                       ("remirror", "library", self.lib),
                                       ("cull", "raw", self.raw),
                                       ("ratings", "folder", self.prev),
                                       ("previews", "previews", self.prev)):
            drawn = {o["name"]: o["default"] for o in R.get(name).describe()["options"]}
            self.assertEqual(drawn[option], expected, f"{name}.{option}")

    def test_and_a_run_with_nothing_typed_uses_them(self):
        self.save()
        opts = R.get("remirror").coerce({})
        self.assertEqual(opts["library"], self.lib)
        self.assertEqual(opts["raw"], self.raw)

    def test_but_typing_something_in_still_wins_for_that_run(self):
        self.save()
        opts = R.get("remirror").coerce({"library": "/somewhere/else"})
        self.assertEqual(opts["library"], "/somewhere/else")
        self.assertEqual(opts["raw"], self.raw)

    def test_the_preview_size_comes_from_setup(self):
        from app.tasks.previews import chosen_size
        self.save(preview_profile="small")
        self.assertEqual(chosen_size(R.get("previews").coerce({})), (1280, 80))

    def test_unless_this_one_run_says_otherwise(self):
        from app.tasks.previews import chosen_size
        self.save(preview_profile="small")
        opts = R.get("previews").coerce({"profile": "large"})
        self.assertEqual(chosen_size(opts), (3200, 92))

    def test_turning_bracket_grouping_off_turns_it_off_everywhere(self):
        """One switch, three features. Two of them agreeing and one not would be
        worse than no grouping at all."""
        self.save(bracket_group="")
        for name in ("previews", "ratings", "cull"):
            self.assertIs(R.get(name).coerce({})["brackets"], False, name)
        self.save(bracket_group="on")
        for name in ("previews", "ratings", "cull"):
            self.assertIs(R.get(name).coerce({})["brackets"], True, name)

    def test_all_three_group_a_folder_the_same_way(self):
        from app.grouping import sets_for
        from core import walk
        for n in ("aeb1", "aeb2", "aeb3"):
            shutil.copy(os.path.join(FIX, f"{n}.jpg"), os.path.join(self.lib, f"{n}.JPG"))
        self.save(bracket_gap=9)
        files = walk.walk(self.lib).files
        answers = {sets_for(files, R.get(n).coerce({})).certain
                   for n in ("previews", "ratings", "cull")}
        self.assertEqual(len(answers), 1, "the three features disagree about brackets")
        self.assertEqual(answers.pop(), 1)


class TheSetupTabItself(Fresh):
    def test_it_lists_what_would_change_before_changing_it(self):
        t = R.get("setup")
        p = t.make_plan({"library": self.lib, "raw": self.raw, "previews": self.prev})
        names = [r.name for r in p.rows]
        self.assertIn("library", names)
        self.assertFalse(S.load().existed, "planning wrote the settings file")

    def test_a_second_look_finds_nothing_to_change(self):
        self.save()
        t = R.get("setup")
        p = t.make_plan({"library": self.lib, "raw": self.raw, "previews": self.prev})
        self.assertEqual(p.rows, [])

    def test_a_library_that_is_not_there_is_a_typo_and_is_refused(self):
        t = R.get("setup")
        p = t.make_plan({"library": os.path.join(self.dir, "nope")})
        self.assertTrue(p.blocked)

    def test_a_raw_tree_that_does_not_exist_yet_is_fine(self):
        """It is created by the task that fills it. Day one has no RAW tree."""
        t = R.get("setup")
        p = t.make_plan({"library": self.lib, "raw": self.raw})
        self.assertFalse(p.blocked)
        self.assertTrue(any("not there yet" in n for n in p.notes), p.notes)

    def test_impossible_bracket_sizes_are_refused(self):
        t = R.get("setup")
        p = t.make_plan({"library": self.lib, "bracket_min_set": 9,
                         "bracket_max_set": 3})
        self.assertTrue(p.blocked)

    def test_the_check_reports_what_the_settings_would_group(self):
        for n in ("aeb1", "aeb2", "aeb3", "burst1"):
            shutil.copy(os.path.join(FIX, f"{n}.jpg"), os.path.join(self.lib, f"{n}.JPG"))
        t = R.get("setup")
        p = t.make_plan({"library": self.lib, "check": self.lib})
        self.assertTrue(any("bracket set" in n for n in p.notes), p.notes)
        self.assertTrue(p.skipped, "the sets it found were not listed")

    def test_and_the_check_writes_nothing(self):
        for n in ("aeb1", "aeb2", "aeb3"):
            shutil.copy(os.path.join(FIX, f"{n}.jpg"), os.path.join(self.lib, f"{n}.JPG"))
        before = sorted(os.listdir(self.lib))
        R.get("setup").make_plan({"library": self.lib, "check": self.lib})
        self.assertEqual(sorted(os.listdir(self.lib)), before)


class TheDataFolder(unittest.TestCase):
    """On the NAS the code is mounted read-only on purpose, so the one folder that
    must be writable is worth failing clearly about rather than by traceback."""

    def setUp(self):
        self._was = os.environ.get("PM_DATA")

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was

    def test_a_writable_folder_reports_itself_as_one(self):
        from core import store
        d = tempfile.mkdtemp(prefix="data-")
        try:
            os.environ["PM_DATA"] = os.path.join(d, "config")
            ok, where = store.writable()
            self.assertTrue(ok)
            self.assertTrue(os.path.isdir(where))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_one_that_is_not_says_so_instead_of_raising(self):
        from core import store
        os.environ["PM_DATA"] = "/proc/definitely/not/here"
        ok, why = store.writable()
        self.assertFalse(ok)
        self.assertIn("/proc/definitely/not/here", why)

    def test_and_asking_for_it_outright_explains_what_to_do(self):
        from core import store
        os.environ["PM_DATA"] = "/proc/definitely/not/here"
        with self.assertRaises(store.Unwritable) as e:
            store.data_dir()
        self.assertIn("PM_DATA", str(e.exception))


class HowTheFormIsDrawn(unittest.TestCase):
    """The page draws itself from these, so they have to be sound for every task."""

    def test_every_option_belongs_to_exactly_one_group(self):
        for t in R.all_tasks():
            seen = [o["name"] for g in t.groups() for o in g["options"]]
            self.assertEqual(sorted(seen), sorted(o.name for o in t.options), t.name)

    def test_a_group_is_only_folded_away_if_all_of_it_is_advanced(self):
        for t in R.all_tasks():
            for g in t.groups():
                if g["advanced"]:
                    self.assertTrue(all(o["advanced"] for o in g["options"]),
                                    f"{t.name}/{g['name']} folds away a plain option")

    def test_the_first_group_is_never_folded_away(self):
        """Whatever the task needs first must be visible when it opens.

        A tab whose whole form is an editor has no options at all - the Flows
        tab is one - and that is a different thing from a form whose first
        question is hidden."""
        for t in R.all_tasks():
            if not t.options:
                self.assertTrue(t.editor,
                                f"{t.name} has no options and no editor either")
                continue
            self.assertFalse(t.groups()[0]["advanced"], t.name)

    def test_every_task_has_an_icon_and_a_tab_name(self):
        for t in R.all_tasks():
            self.assertTrue(t.icon, t.name)
            self.assertTrue(t.describe()["tab"], t.name)

    def test_a_tab_under_another_feature_names_a_real_parent(self):
        names = {t.name for t in R.all_tasks()}
        for t in R.all_tasks():
            if t.parent:
                self.assertIn(t.parent, names, t.name)
                self.assertFalse(R.get(t.parent).parent,
                                 f"{t.name} is a tab under a tab")

    def test_the_sidebar_and_the_tabs_together_cover_every_task(self):
        """Nothing may be unreachable. A task that is neither in the sidebar,
        nor a tab under something there, nor deliberately given a place of its
        own in the header, nor opened from a row of the feature it belongs to,
        is code nobody can run."""
        shown = {t.name for t in R.in_sidebar()}
        for t in R.in_sidebar():
            shown |= {k.name for k in R.children(t.name)}
        shown |= {t.name for t in R.top_level() if t.hidden}
        # And the ones a RESULT opens. "Put a run back" has no sensible place
        # in a sidebar - which run? - so it is a button on the row of the run it
        # would reverse, and `inline` is how it says so. The row is the only
        # honest way in, and `test_an_inline_task_is_opened_from_its_parent`
        # below is what holds that there is one.
        shown |= {t.name for t in R.all_tasks() if t.inline}
        self.assertEqual(shown, {t.name for t in R.all_tasks()})

    def test_an_inline_task_is_opened_from_its_parent(self):
        """Being `inline` is what exempts a feature from the sidebar, so it has
        to mean something: a parent that exists, and a row in that parent's
        result that opens it."""
        import re
        from app import page
        source = page.SCRIPT if hasattr(page, "SCRIPT") else page.build()
        for t in R.all_tasks():
            if not t.inline:
                continue
            self.assertTrue(t.parent, f"{t.name} is inline under nothing")
            self.assertIn(t.parent, {x.name for x in R.all_tasks()}, t.name)
            self.assertTrue(re.search(r"rowAct|row\.act", source),
                            "nothing in the page opens a feature from a row")

    def test_a_hidden_task_has_no_children_to_lose(self):
        """It has no tab row - it is one button in the header - so a child of
        one would have nowhere at all to be drawn. Unless the child is opened
        from a row rather than from a tab, which is what `inline` means."""
        for t in R.top_level():
            if t.hidden:
                self.assertEqual([k.name for k in R.children(t.name)
                                  if not k.inline], [], t.name)

    def test_no_two_tabs_in_one_family_share_an_icon(self):
        """The tabs carry icons now, and a row of five where two are identical
        is worse than no icons at all: you go to pick the one you want by its
        glyph and have to read the labels anyway."""
        for t in R.top_level():
            family = [t] + R.children(t.name)
            icons = [x.icon for x in family]
            self.assertEqual(len(set(icons)), len(icons),
                             f"{t.name}: " + ", ".join(
                                 f"{x.tab or x.title}={x.icon}" for x in family))

    def test_every_icon_is_one_the_page_can_actually_draw(self):
        from app.page import ICONS
        for t in R.all_tasks():
            self.assertIn(f'id="i-{t.icon}"', ICONS,
                          f"{t.name} asks for an icon the page does not have")


if __name__ == "__main__":
    unittest.main()
