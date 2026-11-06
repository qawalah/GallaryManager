"""Search: every criterion, what it refuses to guess, and keeping one by name."""

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
from app.tasks import search as SE               # noqa: E402
from core import find as F                       # noqa: E402
from core import settings as S                   # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="find-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        os.makedirs(os.environ["PM_DATA"])
        self.lib = os.path.join(self.dir, "share", "Photos")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        S.save({"library": self.lib})
        # aeb1: GH4, 25mm, 1/500, f/5.6, ISO 200, 2022-07-14
        self.one = os.path.join(self.shoot, "one.JPG")
        shutil.copy(os.path.join(FIX, "aeb1.jpg"), self.one)

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def hits(self, **asked):
        got = F.search([self.lib], F.from_dict(asked))
        return [os.path.basename(h.path) for h in got.hits]

    def why(self, **asked):
        return F.search([self.lib], F.from_dict(asked)).unanswerable


class EveryCriterion(_Tmp):
    def test_nothing_asked_is_everything(self):
        self.assertEqual(self.hits(), ["one.JPG"])

    def test_the_camera_matches_on_part_of_the_name(self):
        self.assertEqual(self.hits(camera="gh4"), ["one.JPG"])
        self.assertEqual(self.hits(camera="A7C"), [])

    def test_a_focal_length_range(self):
        self.assertEqual(self.hits(focal_from="20", focal_to="30"), ["one.JPG"])
        self.assertEqual(self.hits(focal_from="35"), [])
        self.assertEqual(self.hits(focal_to="24"), [])

    def test_an_aperture_range(self):
        self.assertEqual(self.hits(f_from="4", f_to="8"), ["one.JPG"])
        self.assertEqual(self.hits(f_to="2.8"), [])

    def test_an_iso_range(self):
        self.assertEqual(self.hits(iso_from="100", iso_to="400"), ["one.JPG"])
        self.assertEqual(self.hits(iso_from="800"), [])

    def test_a_shutter_speed_written_the_way_a_camera_writes_it(self):
        # the frame is 1/500
        self.assertEqual(self.hits(faster_than="1/250"), ["one.JPG"])
        self.assertEqual(self.hits(slower_than="1/250"), [])
        self.assertEqual(self.hits(slower_than="1/1000"), ["one.JPG"])

    def test_a_date_range_in_any_of_the_usual_shapes(self):
        self.assertEqual(self.hits(since="2022-01-01", until="2022-12-31"),
                         ["one.JPG"])
        self.assertEqual(self.hits(since="2022-07", until="2022-08"), ["one.JPG"])
        self.assertEqual(self.hits(since="2023"), [])

    def test_a_date_that_is_not_a_date_is_said(self):
        with self.assertRaises(F.Refused):
            F.from_dict({"since": "last summer"})

    def test_a_number_that_is_not_a_number_is_said(self):
        with self.assertRaises(F.Refused):
            F.from_dict({"f_from": "wide"})

    def test_stars_and_a_colour(self):
        from core import quickedit as QE
        self.assertEqual(self.hits(stars_from="1"), [])
        QE.set_stars(self.one, 4)
        QE.set_colour(self.one, "red")
        self.assertEqual(self.hits(stars_from="3"), ["one.JPG"])
        self.assertEqual(self.hits(stars_from="5"), [])
        self.assertEqual(self.hits(colour="red"), ["one.JPG"])
        self.assertEqual(self.hits(colour="blue"), [])

    def test_tags_any_or_all(self):
        from core import quickedit as QE
        QE.add_tag(self.one, "spain")
        QE.add_tag(self.one, "street")
        self.assertEqual(self.hits(tags="spain"), ["one.JPG"])
        self.assertEqual(self.hits(tags="spain, harbour"), ["one.JPG"])
        self.assertEqual(self.hits(tags="spain, harbour", all_tags=True), [])
        self.assertEqual(self.hits(tags="spain, street", all_tags=True),
                         ["one.JPG"])

    def test_has_a_location_or_has_none(self):
        self.assertEqual(self.hits(located="no"), ["one.JPG"])
        self.assertEqual(self.hits(located="yes"), [])
        from core.exifwrite import write_gps
        write_gps(self.one, 41.38, 2.17)
        from core import facts
        facts.reader().forget(self.one)
        self.assertEqual(self.hits(located="yes"), ["one.JPG"])
        self.assertEqual(self.hits(located="no"), [])

    def test_the_file_name(self):
        self.assertEqual(self.hits(name="ONE"), ["one.JPG"])
        self.assertEqual(self.hits(name="two"), [])

    def test_which_kind_of_file(self):
        with open(os.path.join(self.shoot, "one.RW2"), "wb") as fh:
            fh.write(b"RAWHEADER" * 40)
        self.assertEqual(sorted(self.hits()), ["one.JPG", "one.RW2"])
        self.assertEqual(self.hits(kinds=["jpeg"]), ["one.JPG"])
        self.assertEqual(self.hits(kinds=["raw"]), ["one.RW2"])

    def test_two_criteria_narrow_rather_than_widen(self):
        """Every box is an and. A search that widened as you filled it in would
        be the opposite of what filling one in means."""
        self.assertEqual(self.hits(camera="gh4", f_from="4"), ["one.JPG"])
        self.assertEqual(self.hits(camera="gh4", f_from="8"), [])


class WhatTheFileDoesNotSay(_Tmp):
    """The "not said" row of a chart, as a search. Every other box leaves a
    file that cannot answer out; this one asks for exactly those files."""

    def bare(self):
        bare = os.path.join(self.shoot, "bare.JPG")
        with open(bare, "wb") as fh:
            fh.write(b"\xff\xd8\xff\xdb" + b"\0" * 200 + b"\xff\xd9")
        return bare

    def test_each_fact_lists_only_the_files_without_it(self):
        self.bare()
        for name in ("taken", "camera", "focal", "aperture", "iso", "shutter",
                     "lens", "colour", "tags"):
            got = self.hits(missing=name)
            self.assertIn("bare.JPG", got, name)
        # one.JPG says all of these, so it is never among them
        for name in ("taken", "camera", "focal", "aperture", "iso", "shutter"):
            self.assertEqual(self.hits(missing=name), ["bare.JPG"], name)

    def test_a_colour_or_a_tag_put_on_takes_it_out(self):
        from core import quickedit as QE
        self.assertEqual(self.hits(missing="tags"), ["one.JPG"])
        QE.add_tag(self.one, "spain")
        QE.set_colour(self.one, "red")
        self.assertEqual(self.hits(missing="tags"), [])
        self.assertEqual(self.hits(missing="colour"), [])

    def test_two_at_once_narrow_like_every_other_box(self):
        self.bare()
        self.assertEqual(self.hits(missing="taken, camera"), ["bare.JPG"])
        self.assertEqual(self.hits(missing=["taken", "colour"]), ["bare.JPG"])
        self.assertEqual(self.hits(missing="aperture", camera="gh4"), [])

    def test_a_word_it_does_not_know_is_refused_with_words(self):
        with self.assertRaises(F.Refused) as said:
            F.from_dict({"missing": "flash"})
        self.assertIn("taken", str(said.exception))

    def test_it_is_said_back_and_kept_with_a_search(self):
        ask = F.from_dict({"missing": "Aperture"})
        self.assertEqual(ask.missing, ("aperture",))
        self.assertIn("no aperture", ask.asked())
        F.keep("unsaid", ask)
        self.assertEqual(F.of_saved("unsaid").missing, ("aperture",))

    def test_the_search_tab_carries_it(self):
        self.bare()
        p = SE.plan({"folders": self.lib, "missing": "taken"})
        self.assertEqual([r.name for r in p.rows], ["bare.JPG"])
        from app import registry
        self.assertIn("missing", [o.name for o in registry.get("search").options])

    def test_it_agrees_with_the_chart_about_what_not_said_is(self):
        """The chart's "not said" row and the search behind it count the same
        frames, or pressing the row lists a different number from the bar."""
        from core import stats as ST
        self.bare()
        hits = F.search([self.lib], F.Ask()).hits
        for dim in ("year", "camera", "lens", "focal", "aperture", "iso",
                    "shutter", "colour", "tag"):
            unsaid = [os.path.basename(h.path) for h in hits
                      if ST.buckets_of(h, dim)[0] in (ST.UNSAID, "no label",
                                                      "no tags")]
            bucket = {"colour": "no label", "tag": "no tags"}.get(dim, ST.UNSAID)
            self.assertEqual(sorted(self.hits(**ST.ask_for(dim, bucket))),
                             sorted(unsaid), dim)


class WhatItWillNotGuess(_Tmp):
    def test_a_file_that_cannot_answer_is_counted_not_silently_dropped(self):
        """"Cannot tell" is not "no" - and a search that treats it as one hides
        exactly the files worth knowing about."""
        bare = os.path.join(self.shoot, "bare.JPG")
        with open(bare, "wb") as fh:
            fh.write(b"\xff\xd8\xff\xdb" + b"\0" * 200 + b"\xff\xd9")
        said = self.why(camera="gh4")
        self.assertEqual(said.get("does not say which camera"), 1)
        self.assertEqual(self.hits(camera="gh4"), ["one.JPG"])

    def test_a_full_frame_search_will_not_use_the_number_on_the_barrel(self):
        """25mm on a GH4 frames like 50mm. Answering a full-frame question with
        the barrel number would be wrong by a factor of two, silently."""
        self.assertEqual(self.hits(focal35=True, focal_from="20", focal_to="30"), [])
        self.assertEqual(self.why(focal35=True, focal_from="20")
                         .get("no full-frame equivalent in the file"), 1)

    def test_a_place_search_without_coordinates_says_so(self):
        said = self.why(country="Spain")
        self.assertEqual(said.get("no location to look up"), 1)


class EveryMatchIsCounted(_Tmp):
    """"Found 5,000" for a search that matched six thousand was the cap on
    what is kept, said as if it were the answer. The count is every match;
    only the list is capped, and it says when it is."""

    def test_the_count_runs_past_the_cap_on_what_is_kept(self):
        two = os.path.join(self.shoot, "two.JPG")
        shutil.copy(os.path.join(FIX, "aeb1.jpg"), two)
        got = F.search([self.lib], F.Ask(), cap=1)
        self.assertEqual(got.matched, 2)
        self.assertEqual(len(got.hits), 1)
        self.assertTrue(got.capped)
        whole = F.search([self.lib], F.Ask())
        self.assertEqual(whole.matched, 2)
        self.assertEqual(len(whole.hits), 2)
        self.assertFalse(whole.capped)

    def test_the_tab_says_the_whole_count_and_lists_what_it_kept(self):
        two = os.path.join(self.shoot, "two.JPG")
        shutil.copy(os.path.join(FIX, "aeb1.jpg"), two)
        was = SE.SHOW
        try:
            SE.SHOW = 1
            p = SE.plan({"folders": ""})
        finally:
            SE.SHOW = was
        self.assertEqual(dict(p.stats)["Found"], "2")
        self.assertEqual(len(p.rows), 1)
        self.assertTrue(any("1 more matched" in n for n in p.notes), p.notes)
        # and with room for both, no such note
        p = SE.plan({"folders": ""})
        self.assertEqual(len(p.rows), 2)
        self.assertFalse(any("more matched" in n for n in p.notes), p.notes)

    def test_the_tab_keeps_as_many_as_the_search_does(self):
        self.assertEqual(SE.SHOW, F.CAP)
        self.assertGreaterEqual(F.CAP, 20000)


class KeepingOne(_Tmp):
    def test_a_search_is_kept_by_name_and_comes_back(self):
        ask = F.from_dict({"camera": "GH4", "focal_to": "30", "located": "no"})
        F.keep("wide, no location", ask)
        self.assertEqual([n for n, _ in F.saved()], ["wide, no location"])
        back = F.of_saved("wide, no location")
        self.assertEqual(back.camera, "GH4")
        self.assertEqual(back.focal_to, 30.0)
        self.assertEqual(back.located, "no")

    def test_keeping_the_same_name_twice_replaces_it(self):
        F.keep("mine", F.from_dict({"camera": "GH4"}))
        F.keep("mine", F.from_dict({"camera": "A7C"}))
        self.assertEqual(len(F.saved()), 1)
        self.assertEqual(F.of_saved("mine").camera, "A7C")

    def test_only_what_was_filled_in_is_kept(self):
        F.keep("mine", F.from_dict({"camera": "GH4"}))
        self.assertEqual(F.saved()[0][1], {"camera": "GH4"})

    def test_a_nameless_search_is_refused(self):
        with self.assertRaises(F.Refused):
            F.keep("  ", F.from_dict({"camera": "GH4"}))

    def test_forgetting_one(self):
        F.keep("mine", F.from_dict({"camera": "GH4"}))
        F.forget("MINE")
        self.assertEqual(F.saved(), [])

    def test_asking_for_one_that_is_not_there(self):
        with self.assertRaises(F.Refused):
            F.of_saved("nothing")


class TheTab(_Tmp):
    def test_it_says_what_it_was_asked_and_lists_the_matches(self):
        p = SE.plan({"folders": "", "camera": "gh4"})
        said = dict(p.stats)
        self.assertEqual(said["Found"], "1")
        self.assertIn("camera", said["Asking for"])
        self.assertEqual(p.rows[0].source, self.one)
        # the row carries the exposure, so the table answers without opening it
        self.assertIn("f/5.6", p.rows[0].cells[2])
        self.assertIn("25mm", p.rows[0].cells[2])

    def test_nothing_matching_is_explained_rather_than_left_blank(self):
        p = SE.plan({"folders": "", "iso_from": "6400"})
        self.assertEqual(dict(p.stats)["Found"], "0")
        self.assertTrue(any("one box too many" in n for n in p.notes))

    def test_a_place_search_without_the_table_is_refused_with_words(self):
        p = SE.plan({"folders": "", "country": "Spain"})
        self.assertIn("place table", p.blocked)

    def test_it_writes_nothing(self):
        self.assertEqual(SE.apply(SE.plan({"folders": ""})).done, 0)


class OverTheWire(_Tmp):
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

    def post(self, route, body, expect=200):
        req = urllib.request.Request(
            self.base + route, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, expect)
            return json.loads(exc.read())

    def test_searches_are_kept_and_listed_over_the_wire(self):
        self.assertEqual(self.get("/api/searches")["kept"], [])
        got = self.post("/api/searches", {"name": "wide", "ask": {"focal_to": "30"}})
        self.assertEqual(got["kept"][0]["name"], "wide")
        self.assertEqual(self.get("/api/searches")["kept"][0]["ask"],
                         {"focal_to": 30.0})
        self.assertEqual(self.post("/api/searches", {"forget": "wide"})["kept"], [])

    def test_a_search_that_will_not_parse_is_refused_with_words(self):
        got = self.post("/api/searches",
                        {"name": "bad", "ask": {"f_from": "wide"}}, 400)
        self.assertIn("not a number", got["error"])

    def test_the_matches_can_be_handed_to_the_file_manager(self):
        other = os.path.join(self.lib, "2023", "Italy")
        os.makedirs(other)
        two = os.path.join(other, "two.JPG")
        shutil.copy(os.path.join(FIX, "aeb1.jpg"), two)
        got = self.post("/api/files-of", {"paths": [self.one, two]})
        # one listing, two folders - which is the whole point of it
        self.assertTrue(got["found"])
        self.assertEqual(sorted(f["name"] for f in got["files"]),
                         ["one.JPG", "two.JPG"])
        self.assertEqual(got["folders"], [])
        self.assertEqual(len({f["folder"] for f in got["files"]}), 2)

    def test_the_file_manager_takes_as_many_as_a_search_keeps(self):
        """Five thousand was the door's limit while the search kept five
        thousand. The two move together, or a search's tail is lost on the way
        to Files without a word."""
        paths = [os.path.join(self.shoot, f"gone{i}.JPG") for i in range(5001)]
        got = self.post("/api/files-of", {"paths": paths})
        self.assertEqual(got["missing"], 5001)

    def test_files_that_have_gone_are_counted_rather_than_faked(self):
        got = self.post("/api/files-of",
                        {"paths": [self.one, os.path.join(self.shoot, "gone.JPG")]})
        self.assertEqual(len(got["files"]), 1)
        self.assertEqual(got["missing"], 1)

    def test_outside_the_allowed_folders_is_refused(self):
        SRV.ALLOWED_ROOTS[:] = [self.lib]
        try:
            outside = os.path.join(self.dir, "elsewhere.JPG")
            shutil.copy(os.path.join(FIX, "aeb1.jpg"), outside)
            got = self.post("/api/files-of", {"paths": [outside]}, 403)
            self.assertIn("outside", got["error"])
        finally:
            SRV.ALLOWED_ROOTS[:] = []


if __name__ == "__main__":
    unittest.main()
