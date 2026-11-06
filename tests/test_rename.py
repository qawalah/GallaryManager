"""Power rename: the table, what it refuses, and the trees following along."""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.tasks  # noqa: E402,F401
from app import server as SRV                    # noqa: E402
from app.tasks import rename as T                # noqa: E402
from core import renames as R                    # noqa: E402
from core import settings as S                   # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="rename-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        os.makedirs(os.environ["PM_DATA"])
        self.lib = os.path.join(self.dir, "share", "Photos")
        self.raw = os.path.join(self.dir, "share", "Photos Raw")
        self.previews = os.path.join(self.dir, "share", "Previews")
        for tree in (self.lib, self.raw, self.previews):
            os.makedirs(tree)
        S.save({"library": self.lib, "raw": self.raw, "previews": self.previews})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def folder(self, *parts, tree=None):
        where = os.path.join(tree or self.lib, *parts)
        os.makedirs(where, exist_ok=True)
        return where

    def photo(self, folder, name="a.JPG", source="aeb1.jpg"):
        shutil.copy(os.path.join(FIX, source), os.path.join(folder, name))
        return os.path.join(folder, name)

    def rows(self, *pairs):
        return [{"path": p, "name": n} for p, n in pairs]


class TheTable(_Tmp):
    def test_one_level_is_what_is_directly_inside(self):
        self.folder("2022", "Spain")
        self.folder("2023")
        got = R.listing(self.lib, 1)
        self.assertEqual([r["name"] for r in got["rows"]], ["2022", "2023"])
        self.assertEqual({r["depth"] for r in got["rows"]}, {1})

    def test_all_the_way_down_is_indented(self):
        self.folder("2022", "Spain", "Day 1")
        got = R.listing(self.lib, 0)
        self.assertEqual([(r["name"], r["depth"]) for r in got["rows"]],
                         [("2022", 1), ("Spain", 2), ("Day 1", 3)])

    def test_a_depth_of_two_stops_at_two(self):
        self.folder("2022", "Spain", "Day 1")
        self.assertEqual([r["name"] for r in R.listing(self.lib, 2)["rows"]],
                         ["2022", "Spain"])

    def test_what_you_picked_in_files_is_what_it_lists(self):
        a = self.folder("2022", "Spain")
        b = self.folder("2023", "Italy")
        got = R.listing(self.lib, 1, [a, b])
        self.assertEqual([r["name"] for r in got["rows"]], ["Spain", "Italy"])
        self.assertTrue(got["from_picked"])

    def test_a_picked_folder_brings_what_is_under_it_when_asked(self):
        a = self.folder("2022", "Spain", "Day 1")
        got = R.listing(self.lib, 2, [os.path.dirname(a)])
        self.assertEqual([r["name"] for r in got["rows"]], ["Spain", "Day 1"])

    def test_a_picked_file_is_listed_on_its_own(self):
        one = self.photo(self.folder("2022"))
        got = R.listing(self.lib, 1, [one])
        self.assertEqual([(r["name"], r["kind"]) for r in got["rows"]],
                         [("a.JPG", "file")])

    def test_the_apps_own_and_synology_folders_are_left_out(self):
        self.folder("_Culled")
        self.folder("@eaDir")
        self.folder("Spain")
        self.assertEqual([r["name"] for r in R.listing(self.lib, 1)["rows"]],
                         ["Spain"])

    def test_it_says_how_many_are_inside_each_one(self):
        self.folder("2022", "Spain")
        self.folder("2022", "Italy")
        row = R.listing(self.lib, 1)["rows"][0]
        self.assertEqual(row["holds"], 2)

    def test_a_folder_that_is_not_there_is_said_not_crashed(self):
        with self.assertRaises(R.Refused):
            R.listing(os.path.join(self.dir, "nowhere"), 1)


class WhatItRefuses(_Tmp):
    def test_an_empty_or_slashed_name(self):
        a = self.folder("Spain")
        for name in ("", "   ", "a/b", "a\\b", "..", "a:b", "a?b"):
            got = R.check(self.rows((a, name)))
            self.assertTrue(got["rows"][0]["problem"], name)

    def test_a_name_with_space_on_the_end(self):
        a = self.folder("Spain")
        self.assertIn("space", R.check(self.rows((a, "Spain ")))["rows"][0]["problem"])

    def test_a_hidden_name_because_the_app_would_skip_that_folder(self):
        a = self.folder("Spain")
        self.assertIn("hidden", R.check(self.rows((a, "@Spain")))["rows"][0]["problem"])

    def test_two_rows_that_would_meet_on_one_name(self):
        a, b = self.folder("Spain"), self.folder("spain trip")
        got = R.check(self.rows((a, "Spain 2022"), (b, "Spain 2022")))
        self.assertTrue(all(r["problem"] for r in got["rows"]))
        self.assertIn("2 rows", got["rows"][0]["problem"])
        self.assertEqual(got["ready"], 0)

    def test_a_name_something_else_already_has(self):
        a = self.folder("Spain")
        self.folder("Italy")
        self.assertIn("already", R.check(self.rows((a, "Italy")))["rows"][0]["problem"])

    def test_but_not_when_the_thing_holding_it_is_moving_away(self):
        """Swapping two names, and a chain of them, are both legal.

        A -> B while B -> C is fine and is exactly what fixing a convention
        across a tree looks like. Refusing it would make the table refuse the
        thing it exists for.
        """
        a, b = self.folder("A"), self.folder("B")
        got = R.check(self.rows((a, "B"), (b, "C")))
        self.assertEqual([r["problem"] for r in got["rows"]], ["", ""])
        self.assertEqual(got["ready"], 2)

    def test_a_row_left_alone_is_not_a_problem(self):
        a = self.folder("Spain")
        got = R.check(self.rows((a, "Spain")))
        self.assertEqual(got["rows"][0]["problem"], "")
        self.assertTrue(got["rows"][0]["same"])
        self.assertEqual(got["ready"], 0)

    def test_a_folder_renamed_by_somebody_else_since(self):
        a = self.folder("Spain")
        os.rename(a, os.path.join(self.lib, "Espana"))
        self.assertIn("not there", R.check(self.rows((a, "Spain 2022")))["rows"][0]["problem"])

    def test_one_bad_row_stops_the_whole_table(self):
        a, b = self.folder("A"), self.folder("B")
        with self.assertRaises(R.Refused):
            R.apply(self.rows((a, "A 2022"), (b, "b/2022")))
        # and nothing was written - not even the good row
        self.assertTrue(os.path.isdir(a))
        self.assertFalse(os.path.isdir(os.path.join(self.lib, "A 2022")))


class DoingIt(_Tmp):
    def test_names_are_written_and_the_moves_come_back(self):
        a = self.folder("spain trip")
        got = R.apply(self.rows((a, "2022 Spain")))
        self.assertTrue(os.path.isdir(os.path.join(self.lib, "2022 Spain")))
        self.assertEqual(got["renamed"], 1)
        self.assertEqual(got["moves"][0][0], a)

    def test_the_deepest_row_goes_first_so_a_parent_never_breaks_a_child(self):
        """Renaming top-down loses every row below the first one: the child's
        path was read before its parent moved."""
        child = self.folder("2022", "spain")
        parent = os.path.dirname(child)
        got = R.apply(self.rows((parent, "2022 photos"), (child, "Spain")))
        self.assertEqual(got["failed"], [])
        self.assertTrue(os.path.isdir(os.path.join(self.lib, "2022 photos", "Spain")))

    def test_a_swap_goes_through_in_the_order_it_has_to(self):
        a, b = self.folder("A"), self.folder("B")
        R.apply(self.rows((a, "B 2022"), (b, "A 2022")))
        self.assertEqual(sorted(os.listdir(self.lib)), ["A 2022", "B 2022"])

    def test_the_raw_and_previews_trees_follow(self):
        lib = self.folder("2022", "spain trip")
        raw = self.folder("2022", "spain trip", tree=self.raw)
        prev = self.folder("2022", "spain trip", tree=self.previews)
        got = R.apply(self.rows((lib, "2022 Spain")))
        self.assertEqual(got["mirrored"], 2)
        self.assertTrue(os.path.isdir(os.path.join(os.path.dirname(raw), "2022 Spain")))
        self.assertTrue(os.path.isdir(os.path.join(os.path.dirname(prev), "2022 Spain")))

    def test_and_can_be_told_not_to(self):
        lib = self.folder("2022", "spain trip")
        raw = self.folder("2022", "spain trip", tree=self.raw)
        got = R.apply(self.rows((lib, "2022 Spain")), with_raw=False,
                      with_previews=False)
        self.assertEqual(got["mirrored"], 0)
        self.assertTrue(os.path.isdir(raw))

    def test_a_tree_that_does_not_have_that_folder_is_left_alone(self):
        lib = self.folder("2022", "spain trip")
        got = R.apply(self.rows((lib, "2022 Spain")))
        self.assertEqual(got["mirrored"], 0)
        self.assertEqual(got["failed"], [])
        # and nothing was created in the other trees to make it true
        self.assertEqual(os.listdir(self.raw), [])

    def test_a_taken_name_in_the_other_tree_is_said_not_written_over(self):
        lib = self.folder("2022", "spain trip")
        self.folder("2022", "spain trip", tree=self.raw)
        self.folder("2022", "2022 Spain", tree=self.raw)
        got = R.apply(self.rows((lib, "2022 Spain")))
        self.assertEqual(got["mirrored"], 0)
        self.assertTrue(any("taken" in line for line in got["failed"]))
        # the library still went through, and the message says which tree did not
        self.assertTrue(os.path.isdir(os.path.join(self.lib, "2022", "2022 Spain")))

    def test_undo_puts_every_name_back(self):
        from core import filesops
        a = self.folder("2022", "spain trip")
        self.folder("2022", "spain trip", tree=self.raw)
        got = R.apply(self.rows((a, "2022 Spain")))
        back = filesops.undo(sorted(got["moves"], key=lambda m: m[1].count(os.sep)))
        self.assertEqual(back["restored"], 2)
        self.assertTrue(os.path.isdir(a))


class TheBulkTools(_Tmp):
    def test_find_and_replace_ignores_capitals_unless_told(self):
        self.assertEqual(R.swap("Spain Trip", "spain", "Espana"), "Espana Trip")
        self.assertEqual(R.swap("Spain Trip", "spain", "Espana", True), "Spain Trip")

    def test_and_replaces_every_time_it_appears(self):
        self.assertEqual(R.swap("a-a-a", "a", "b"), "b-b-b")

    def test_replacing_with_nothing_takes_it_out(self):
        self.assertEqual(R.swap("IMG_2022 Spain", "IMG_", ""), "2022 Spain")

    def test_title_case_keeps_a_camera_name_and_an_apostrophe(self):
        self.assertEqual(R.recase("GH4 spain's trip", "title"), "GH4 Spain's Trip")

    def test_lower_and_upper(self):
        self.assertEqual(R.recase("Spain", "lower"), "spain")
        self.assertEqual(R.recase("Spain", "upper"), "SPAIN")

    def test_tidying_spaces_and_underscores(self):
        self.assertEqual(R.tidy("  2022   Spain__trip  - "), "2022 Spain_trip")

    def test_dropping_a_leading_number(self):
        self.assertEqual(R.strip_number("01 - Spain"), "Spain")
        self.assertEqual(R.strip_number("2022 Spain"), "Spain")
        # and a name that is only a number keeps it rather than becoming empty
        self.assertEqual(R.strip_number("2022"), "2022")

    def test_numbering_pads_and_can_go_on_the_end(self):
        self.assertEqual(R.numbered(["a", "b"], 1, 3), ["001 - a", "002 - b"])
        self.assertEqual(R.numbered(["a"], 7, 2, True, "_"), ["a_07"])

    def test_a_pattern_names_a_folder_from_the_photographs_in_it(self):
        where = self.folder("dump")
        self.photo(where, "one.JPG")
        said = R.pattern_name(where, "{year} {monthname}")
        self.assertRegex(said, r"^\d{4} [A-Z][a-z]+$")

    def test_a_pattern_over_many_folders_keeps_the_names_it_cannot_say(self):
        has = self.folder("has photos")
        self.photo(has, "one.JPG")
        empty = self.folder("no photos")
        got = R.by_pattern([has, empty], "{year}")
        self.assertRegex(got[0], r"^\d{4}$")
        self.assertEqual(got[1], "no photos")

    def test_a_pattern_naming_a_tree_gives_the_deepest_level_only(self):
        """A rename makes one name. {year}/{month} would otherwise ask for a
        folder with a slash in it, which is not a name at all."""
        where = self.folder("dump")
        self.photo(where, "one.JPG")
        said = R.pattern_name(where, "{year}/{monthname}")
        self.assertNotIn("/", said)
        self.assertRegex(said, r"^[A-Z][a-z]+$")

    def test_a_folder_of_folders_is_dated_by_the_photographs_below_it(self):
        deep = self.folder("2022", "Spain")
        self.photo(deep, "one.JPG")
        said = R.pattern_name(os.path.dirname(deep), "{year}")
        self.assertRegex(said, r"^\d{4}$")


class TheTabItself(_Tmp):
    def test_the_plan_says_what_the_table_is_standing_on(self):
        self.folder("2022")
        p = T.plan({"folder": self.lib, "depth": 1})
        said = dict(p.stats)
        self.assertEqual(said["Folders in the table"], "1")
        self.assertEqual(said["Levels to list"], "1 level(s) down")
        self.assertFalse(p.rows)

    def test_no_folder_is_asked_for_rather_than_guessed(self):
        self.assertTrue(T.plan({"folder": ""}).blocked)

    def test_it_writes_nothing_itself(self):
        got = T.apply(T.plan({"folder": self.lib}))
        self.assertEqual(got.done, 0)


class PickedFiles(_Tmp):
    """A picked file is renamed with its sidecars, and the index is told."""

    def setUp(self):
        super().setUp()
        self.shoot = self.folder("2022", "Spain")
        self.neg = os.path.join(self.shoot, "a.RW2")
        with open(self.neg, "wb") as fh:
            fh.write(b"raw")
        with open(os.path.join(self.shoot, "a.xmp"), "w") as fh:
            fh.write("<x/>")

    def test_the_sidecar_goes_with_it(self):
        got = R.apply(self.rows((self.neg, "b.RW2")))
        self.assertEqual(got["failed"], [])
        self.assertTrue(os.path.isfile(os.path.join(self.shoot, "b.RW2")))
        self.assertTrue(os.path.isfile(os.path.join(self.shoot, "b.xmp")))
        self.assertFalse(os.path.exists(os.path.join(self.shoot, "a.xmp")))
        self.assertEqual(got["renamed"], 1)
        self.assertEqual(len(got["moves"]), 2)

    def test_a_taken_sidecar_name_is_a_problem_before_anything_runs(self):
        with open(os.path.join(self.shoot, "b.xmp"), "w") as fh:
            fh.write("<keep/>")
        looked = R.check(self.rows((self.neg, "b.RW2")))
        self.assertIn("sidecar", looked["rows"][0]["problem"])
        with self.assertRaises(R.Refused):
            R.apply(self.rows((self.neg, "b.RW2")))
        self.assertTrue(os.path.isfile(self.neg))

    def test_the_index_is_told(self):
        from unittest import mock
        from core import filesops
        with mock.patch.object(filesops, "_tell") as told:
            R.apply(self.rows((self.neg, "b.RW2")))
        self.assertTrue(told.called)
        self.assertEqual(len(told.call_args.kwargs["moves"]), 2)


class OverTheWire(_Tmp):
    """The routes the table actually uses, through a real server."""

    def setUp(self):
        super().setUp()
        SRV.ALLOWED_ROOTS[:] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), SRV.Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        super().tearDown()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as r:
            return json.loads(r.read())

    def post(self, body, expect=200):
        req = urllib.request.Request(
            self.base + "/api/rename", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, expect)
            return json.loads(exc.read())

    def test_the_table_comes_back_with_the_kept_patterns(self):
        self.folder("2022")
        got = self.get("/api/rename-list?depth=1&path="
                       + urllib.parse.quote(self.lib))
        self.assertEqual([r["name"] for r in got["rows"]], ["2022"])
        self.assertIsInstance(got["kept"], list)

    def test_checking_comes_back_row_by_row(self):
        a = self.folder("A")
        self.folder("B")
        got = self.post({"do": "check", "rows": [{"path": a, "name": "B"}]})
        self.assertIn("already", got["rows"][0]["problem"])
        self.assertEqual(got["ready"], 0)

    def test_renaming_over_the_wire_and_undoing_it(self):
        a = self.folder("spain trip")
        got = self.post({"do": "apply", "rows": [{"path": a, "name": "2022 Spain"}]})
        self.assertEqual(got["renamed"], 1)
        self.assertTrue(os.path.isdir(os.path.join(self.lib, "2022 Spain")))
        back = self.post({"do": "undo", "moves": got["moves"]})
        self.assertEqual(back["restored"], 1)
        self.assertTrue(os.path.isdir(a))

    def test_a_refused_table_says_why_and_changes_nothing(self):
        a = self.folder("A")
        got = self.post({"do": "apply", "rows": [{"path": a, "name": ""}]}, 409)
        self.assertIn("error", got)
        self.assertTrue(os.path.isdir(a))

    def test_it_is_logged_like_any_other_run(self):
        from core import runlog
        a = self.folder("spain trip")
        self.post({"do": "apply", "rows": [{"path": a, "name": "2022 Spain"}]})
        self.assertTrue(any(e["task"] == "rename" for e in runlog.recent(5)))

    def test_and_history_can_put_it_back(self):
        from core import runlog
        from app import registry as REG
        a = self.folder("spain trip")
        self.post({"do": "apply", "rows": [{"path": a, "name": "2022 Spain"}]})
        last = runlog.recent(1)[0]
        self.assertEqual(last["moves"], [[a, os.path.join(self.lib, "2022 Spain")]])
        t = REG.get("undo")
        p = t.make_plan({"no": last["no"]})
        self.assertFalse(p.blocked, p.blocked)
        t.apply(p)
        self.assertTrue(os.path.isdir(a))

    def test_a_pattern_needing_a_place_is_refused_with_words(self):
        where = self.folder("dump")
        self.photo(where, "one.JPG")
        got = self.post({"do": "pattern", "pattern": "{country}/{city}",
                         "rows": [{"path": where, "name": "dump"}]}, 400)
        self.assertIn("place", got["error"])

    def test_a_pattern_fills_the_names_without_writing_anything(self):
        where = self.folder("dump")
        self.photo(where, "one.JPG")
        got = self.post({"do": "pattern", "pattern": "{year}",
                         "rows": [{"path": where, "name": "dump"}]})
        self.assertRegex(got["names"][0], r"^\d{4}$")
        self.assertTrue(os.path.isdir(where))          # still called dump

    def test_outside_the_allowed_folders_is_refused(self):
        SRV.ALLOWED_ROOTS[:] = [self.lib]
        try:
            outside = self.folder("elsewhere", tree=self.dir)
            got = self.post({"do": "check", "rows": [{"path": outside, "name": "x"}]}, 403)
            self.assertIn("outside", got["error"])
        finally:
            SRV.ALLOWED_ROOTS[:] = []


if __name__ == "__main__":
    unittest.main()
