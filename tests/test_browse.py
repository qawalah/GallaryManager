"""The screens a photo library is opened with, answered out of the index.

Two things are being held here. The first is arithmetic: a month count that is
one off, or an album that quietly leaves out the photographs with no stars, is a
library you cannot trust and there is no way to notice by looking.

The second is the rule that makes the whole thing maintainable - **the grid and
the Search tab judge a photograph the same way**. The filters above the grid are
a `find.Ask` and they are matched by `find.matches`, the same function the
Search feature is built on. Two sets of matching rules would disagree inside a
month, and the one that was wrong would be the one with no test.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import browse as B                 # noqa: E402
from core import catalogue as C              # noqa: E402
from core import demo, find, settings as S   # noqa: E402

try:
    import PIL                               # noqa: F401
    HAVE_PIL = True
except Exception:                            # noqa: BLE001
    HAVE_PIL = False


@unittest.skipUnless(HAVE_PIL, "the sample library needs Pillow")
class OverTheSampleLibrary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="browse-")
        os.environ["PM_DATA"] = os.path.join(cls.home, "config")
        cls.sample = os.path.join(cls.home, "Sample")
        demo.build(cls.sample)
        S.save({"library": os.path.join(cls.sample, demo.LIBRARY),
                "raw": os.path.join(cls.sample, demo.RAWTREE)})
        cls.cat = C.Catalogue(os.path.join(cls.home, "cat.json"))
        cls.cat.refresh([os.path.join(cls.sample, demo.LIBRARY),
                         os.path.join(cls.sample, demo.INBOX)])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)
        C.forget_all()

    # ------------------------------------------------------------ the grid

    def test_the_grid_leaves_the_negatives_out(self):
        """A RAW is not a photograph you browse - it is the other half of one
        that is already in the grid, and a timeline showing both shows
        everything twice."""
        page = B.timeline(self.cat)
        kinds = {self.cat.entry(i["path"])[1] for i in page["items"]}
        self.assertNotIn("raw", kinds)
        self.assertIn("jpeg", kinds)
        raws = [p for p in self.cat.files if self.cat.entry(p)[1] == "raw"]
        self.assertTrue(raws, "the sample has no negatives to leave out")
        self.assertEqual(page["total"], len(self.cat.files) - len(raws))

    def test_but_asking_for_them_shows_them(self):
        page = B.timeline(self.cat, find.Ask(kinds=("raw",)))
        self.assertTrue(page["items"])
        self.assertTrue(all(self.cat.entry(i["path"])[1] == "raw"
                            for i in page["items"]))

    def test_a_folder_view_is_the_same_photographs_in_another_order(self):
        """Two ways of looking, one library. A folder view that was a different
        list - or a different idea of what matches - would be a second library
        to keep in step with the first."""
        by_date = B.timeline(self.cat, None, 0, 999)
        by_folder = B.timeline(self.cat, None, 0, 999, by="folder")
        self.assertEqual(by_folder["total"], by_date["total"])
        self.assertEqual({i["path"] for i in by_folder["items"]},
                         {i["path"] for i in by_date["items"]})
        # folders A to Z, newest first inside each
        labels = [g["label"] for g in by_folder["groups"]]
        self.assertEqual(len(labels), len(set(labels)))
        for g in by_folder["groups"]:
            mine = [i for i in by_folder["items"]
                    if os.path.basename(os.path.dirname(i["path"]))
                    == os.path.basename(g["key"])]
            taken = [i["taken"] for i in mine if i["taken"]]
            self.assertEqual(taken, sorted(taken, reverse=True), g["label"])

    def test_a_folder_is_named_by_its_position_not_its_whole_path(self):
        got = B.timeline(self.cat, None, 0, 1, by="folder")["groups"]
        self.assertTrue(got)
        for g in got:
            self.assertNotIn(self.home, g["label"],
                             "the whole path is on screen")

    def test_the_months_add_up_to_the_whole_answer(self):
        """The rail down the side is the shape of the LIBRARY, not the shape of
        what has been scrolled to - so its counts have to come from every row,
        not from the page."""
        page = B.timeline(self.cat, None, 0, 4)
        self.assertEqual(len(page["items"]), 4)
        self.assertEqual(sum(m["count"] for m in page["groups"]), page["total"])
        self.assertGreater(len(page["groups"]), 1)

    def test_a_page_follows_on_from_the_one_before_it(self):
        first = B.timeline(self.cat, None, 0, 5)["items"]
        second = B.timeline(self.cat, None, 5, 5)["items"]
        self.assertEqual(len(set(i["path"] for i in first)
                             & set(i["path"] for i in second)), 0)

    def test_the_months_are_newest_first_and_so_are_the_photographs(self):
        page = B.timeline(self.cat)
        keys = [m["key"] for m in page["groups"]]
        self.assertEqual(keys, sorted(keys, reverse=True))
        taken = [i["taken"] for i in page["items"] if i["taken"]]
        self.assertEqual(taken, sorted(taken, reverse=True))

    def test_a_filter_is_the_same_filter_the_search_tab_uses(self):
        """The rule this file exists for. Not "it returns something" - the SAME
        photographs, judged by the same function."""
        ask = find.Ask(stars_from=4)
        mine = {i["path"] for i in B.timeline(self.cat, ask)["items"]}
        theirs = set()
        for path in self.cat.files:
            hit = self.cat.hit(path)
            if self.cat.entry(path)[1] == "raw":
                continue
            ok, _ = find.matches(hit, ask)
            if ok:
                theirs.add(path)
        self.assertEqual(mine, theirs)
        self.assertTrue(mine)

    # ------------------------------------------------------- what is in it

    def test_the_overview_counts_each_file_once(self):
        got = B.overview(self.cat)
        self.assertEqual(got["photos"] + got["videos"] + got["raws"],
                         len(self.cat.files))
        self.assertEqual(got["shown"], got["photos"] + got["videos"])
        self.assertLessEqual(got["located"], got["shown"])
        self.assertLessEqual(got["rated"], got["shown"])

    def test_and_knows_which_years_and_cameras_are_in_there(self):
        got = B.overview(self.cat)
        self.assertIn("2023", dict(got["years"]))
        self.assertIn("DMC-GH4", dict(got["cameras"]))

    def test_the_dashboard_needs_nothing_opened(self):
        """The point of the whole index: the home screen is drawn in the time it
        takes to send it, not in the time it takes to open eighty thousand
        files."""
        got = B.dashboard(self.cat)
        self.assertTrue(got["tiles"])
        self.assertTrue(got["charts"])
        self.assertTrue(got["measured"])
        self.assertEqual(got["overview"]["photos"], B.overview(self.cat)["photos"])

    def test_the_cameras_tile_counts_every_camera_not_the_top_six(self):
        """Home said "6 cameras" beside a chart of thirty-four: the tile counted
        the overview's short list of the biggest six. It counts what the camera
        chart counts, and a photo that names no camera is not one more."""
        at = C._AT["camera"]
        photos = [p for _k, p in self.cat.rows()
                  if self.cat.entry(p)[1] not in ("raw", "video")]
        self.assertGreaterEqual(len(photos), 10)
        was = {p: list(self.cat.entry(p)) for p in photos}
        self.addCleanup(self.cat.files.update, was)
        for n, path in enumerate(photos):
            e = list(was[path])
            e[at] = f"CAM-{n % 9}" if n % 10 != 9 else ""
            self.cat.files[path] = e
        tiles = {t["widget"]: t for t in B.dashboard(self.cat)["tiles"]}
        self.assertEqual(tiles["tile:cameras"]["value"], "9")

    def test_the_dashboard_leaves_out_what_the_index_cannot_answer(self):
        """How much the previews tree weighs is a fact about a tree this does
        not index. Saying nothing is right; guessing would not be."""
        got = B.dashboard(self.cat)
        names = [t["widget"] for t in got["tiles"]] + [m[3] for m in got["done"]]
        self.assertNotIn("meter:previews", names)
        self.assertNotIn("meter:raws", names)

    def test_a_half_rounds_up_as_the_page_rounds_it(self):
        """Five of eight is 62.5%. The page's own tiles say 63%, so the
        dashboard's must too - Home shows both, and Python's round() alone
        would have made it 62% beside 63%."""
        self.assertEqual(B._share(5, 8), "63%")
        self.assertEqual(B._share(1, 8), "13%")
        self.assertEqual(B._share(0, 8), "0%")
        self.assertEqual(B._share(1, 0), "-")

    # ---------------------------------------------------------- the places

    def test_places_are_grouped_rather_than_one_pin_per_photograph(self):
        got = B.clusters(self.cat, zoom=4)
        self.assertTrue(got["pins"])
        self.assertLess(len(got["pins"]), got["located"])
        self.assertEqual(sum(p["count"] for p in got["pins"]), got["located"])
        for pin in got["pins"]:
            self.assertTrue(os.path.exists(pin["cover"]))

    def test_a_tighter_zoom_separates_them_again(self):
        wide = B.clusters(self.cat, zoom=1)["pins"]
        tight = B.clusters(self.cat, zoom=10)["pins"]
        self.assertGreaterEqual(len(tight), len(wide))

    def test_a_place_with_no_table_imported_still_says_where_it_is(self):
        """An empty map is not an honest answer to "where have I been" just
        because nobody has imported a list of towns."""
        named = B.named_places(self.cat)
        self.assertTrue(named)
        for one in named:
            self.assertTrue(one["name"].strip())
            self.assertFalse(one["named"], "a place table was imported here?")

    # ---------------------------------------------------------- the albums

    def test_the_albums_are_questions_with_obvious_answers(self):
        got = {a["key"]: a for a in B.albums(self.cat)}
        self.assertIn("favourites", got)
        self.assertIn("videos", got)
        self.assertIn("nolocation", got)
        self.assertEqual(got["videos"]["count"],
                         B.overview(self.cat)["videos"])

    def test_and_opening_one_is_an_ordinary_filter(self):
        """Not a second way of listing photographs: an album IS a search, so it
        cannot drift away from what it claims to hold."""
        for album in B.albums(self.cat):
            page = B.timeline(self.cat, B.album_ask(album["key"]))
            self.assertEqual(page["total"], album["count"], album["key"])

    def test_an_album_cover_is_the_newest_thing_in_it(self):
        for album in B.albums(self.cat):
            page = B.timeline(self.cat, B.album_ask(album["key"]), 0, 1)
            self.assertEqual(page["items"][0]["path"], album["cover"],
                             album["key"])

    # ------------------------------------------------------ one photograph

    def test_a_photograph_knows_what_else_it_is(self):
        """The negative and the preview, found by POSITION in the mirrored
        trees - the same way every feature in this app finds them."""
        path = os.path.join(self.sample, demo.LIBRARY, "2023", "Spain",
                            "Alhambra-01.JPG")
        got = B.detail(self.cat, path)
        self.assertEqual(got["camera"], "DMC-GH4")
        kinds = [f["kind"] for f in got["files"]]
        self.assertIn("self", kinds)
        self.assertIn("raw", kinds)
        for f in got["files"]:
            self.assertTrue(os.path.exists(f["path"]), f["path"])

    def test_and_does_not_claim_files_that_are_not_there(self):
        """A detail view that confidently names a preview which does not exist
        is worse than one that says there is none."""
        path = os.path.join(self.sample, demo.INBOX, "P1010434.JPG")
        got = B.detail(self.cat, path)
        self.assertEqual([f["kind"] for f in got["files"]], ["self"])

    def test_a_file_the_index_has_never_seen_still_answers(self):
        got = B.detail(self.cat, os.path.join(self.home, "nope.jpg"))
        self.assertFalse(got["there"])
        self.assertEqual(got["files"][0]["kind"], "self")


@unittest.skipUnless(HAVE_PIL, "the sample library needs Pillow")
class TheIndexAndTheScanAgree(unittest.TestCase):
    """The one test that keeps the shortcut honest.

    The dashboard is counted from the index now instead of from a pass over
    every photograph. That is only allowed to be faster - it is not allowed to
    be a different answer, and a difference would be invisible: both look like
    a chart.
    """

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="agree-")
        os.environ["PM_DATA"] = os.path.join(cls.home, "config")
        cls.sample = os.path.join(cls.home, "Sample")
        demo.build(cls.sample)
        cls.lib = os.path.join(cls.sample, demo.LIBRARY)
        S.save({"library": cls.lib,
                "raw": os.path.join(cls.sample, demo.RAWTREE)})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)
        C.forget_all()

    def test_counting_the_index_gives_what_reading_the_disk_gives(self):
        from core import stats as ST
        dims = ["year", "camera", "stars", "aperture", "iso", "kind"]
        scanned = ST.tally([self.lib], dims)
        cat = C.Catalogue(os.path.join(self.home, "c.json"))
        cat.refresh([self.lib])
        indexed = ST.tally_of(cat.hits([self.lib]), dims)
        self.assertEqual(indexed.photos, scanned.photos)
        self.assertEqual(indexed.bytes, scanned.bytes)
        for dim in dims:
            self.assertEqual(indexed.counts[dim].rows,
                             scanned.counts[dim].rows, dim)

    def test_and_the_library_tab_uses_it_when_it_can(self):
        from app import registry as R
        import app.tasks                                # noqa: F401
        C.shared().refresh(C.wanted_roots())
        plan = R.get("library").make_plan({"folder": self.lib})
        self.assertTrue(plan.charts.get("charts"))
        # "cold" means it had to open files. Out of the index, it did not.
        self.assertFalse(plan.charts.get("cold"))

    def test_but_reads_the_disk_for_a_folder_the_index_never_saw(self):
        """An index that answered for trees it never read would be worse than
        no index: the tab would quietly report on nothing."""
        from app import registry as R
        import app.tasks                                # noqa: F401
        C.shared().refresh([self.lib])
        other = os.path.join(self.sample, demo.INBOX)
        plan = R.get("library").make_plan({"folder": other})
        self.assertTrue(plan.charts.get("charts"))
        self.assertGreater(
            sum(r[1] for r in plan.charts["charts"][0]["rows"]), 0)


class TheWordsUnderneath(unittest.TestCase):
    def test_a_month_is_named_rather_than_numbered(self):
        self.assertEqual(B._month_label("2024-11"), "November 2024")
        self.assertEqual(B._month_label(""), "No date")
        self.assertEqual(B._month_label("rubbish"), "rubbish")

    def test_how_old_the_numbers_are_is_said_in_words(self):
        import time
        self.assertEqual(B.ago(0), "never")
        self.assertEqual(B.ago(time.time()), "just now")
        self.assertIn("minutes", B.ago(time.time() - 600))
        self.assertIn("hours", B.ago(time.time() - 7200))
        self.assertIn("days", B.ago(time.time() - 400000))
        # one of a thing is not "1 minutes"
        self.assertEqual(B.ago(time.time() - 100), "1 minute ago")
        self.assertEqual(B.ago(time.time() - 3700 * 1.5), "1 hour ago")


if __name__ == "__main__":
    unittest.main()


class AlbumsPutAway(unittest.TestCase):
    """An album is a question, so putting one away is declining to ask it.

    The built-in ones are questions this app thinks are worth asking, which is
    not the same as thinking somebody should be asked them - and because none of
    them is a stored list, nothing is lost by putting one away.
    """

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="away-")
        os.environ["PM_DATA"] = os.path.join(cls.home, "config")
        cls.sample = os.path.join(cls.home, "Sample")
        demo.build(cls.sample)
        S.save({"library": os.path.join(cls.sample, demo.LIBRARY)})
        cls.cat = C.Catalogue(os.path.join(cls.home, "cat.json"))
        cls.cat.refresh([os.path.join(cls.sample, demo.LIBRARY)])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)
        C.forget_all()

    def setUp(self):
        B.hide_albums([])

    def test_an_album_put_away_is_not_on_the_screen(self):
        whole = B.albums(self.cat)
        self.assertTrue(whole)
        key = whole[0]["key"]
        B.hide_albums([key])
        self.assertNotIn(key, [a["key"] for a in B.albums(self.cat)])

    def test_but_it_still_exists_and_still_answers(self):
        """Nothing was deleted: the album is a search, and the search still
        finds what it always found."""
        whole = B.albums(self.cat)
        one = whole[0]
        B.hide_albums([one["key"]])
        again = [a for a in B.albums(self.cat, show_all=True)
                 if a["key"] == one["key"]]
        self.assertEqual(len(again), 1)
        self.assertEqual(again[0]["count"], one["count"])
        page = B.timeline(self.cat, B.album_ask(one["key"]), 0, 999)
        self.assertEqual(page["total"], one["count"])

    def test_and_it_comes_back(self):
        whole = [a["key"] for a in B.albums(self.cat)]
        B.hide_albums([whole[0]])
        B.hide_albums([])
        self.assertEqual([a["key"] for a in B.albums(self.cat)], whole)

    def test_nonsense_in_the_setting_puts_nothing_away(self):
        S.save({"hide_albums": "{not json"})
        self.assertEqual(B.hidden_albums(), [])
        self.assertTrue(B.albums(self.cat))


@unittest.skipUnless(HAVE_PIL, "the sample library needs Pillow")
class AFolderIsAPlace(unittest.TestCase):
    """`inside` answers one folder at a time.

    The folder view used to be `timeline(by="folder")` - every photograph in the
    library, in one list, with a heading each time the folder changed. That is
    the timeline sorted differently, not a folder view: there is no way to see
    that a folder HAS folders in it, and no way to go into one.
    """

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="inside-")
        os.environ["PM_DATA"] = os.path.join(cls.home, "config")
        cls.sample = os.path.join(cls.home, "Sample")
        demo.build(cls.sample)
        cls.lib = os.path.join(cls.sample, demo.LIBRARY)
        S.save({"library": cls.lib})
        cls.cat = C.Catalogue(os.path.join(cls.home, "cat.json"))
        cls.cat.refresh([cls.lib])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)
        C.forget_all()

    def test_one_library_means_starting_inside_it(self):
        """A top level holding a single card called "Photos" is a press that
        tells you nothing, every time."""
        got = B.inside(self.cat)
        self.assertEqual(got["where"], os.path.abspath(self.lib))
        self.assertTrue(got["at_top"])
        self.assertTrue(got["folders"])

    def test_the_folders_here_are_the_ones_here_and_not_the_ones_below(self):
        got = B.inside(self.cat)
        names = [f["name"] for f in got["folders"]]
        self.assertEqual(sorted(names), sorted(set(names)))
        for f in got["folders"]:
            self.assertEqual(os.path.dirname(f["path"]), got["where"])

    def test_a_folder_card_carries_a_cover_and_a_count(self):
        """So a folder is recognised rather than read."""
        for f in B.inside(self.cat)["folders"]:
            self.assertTrue(f["photos"] + f["videos"] + f["raws"],
                            f["name"] + " says it holds nothing")
            self.assertTrue(f["cover"], f["name"] + " has no cover")
            self.assertTrue(os.path.exists(f["cover"]))

    def test_the_counts_on_the_cards_add_up_to_the_library(self):
        """A count that is of what is directly in a folder, when the folders
        below it hold everything, is a card that says a shoot is empty."""
        got = B.inside(self.cat)
        here = got["total"]
        below = sum(f["photos"] + f["videos"] for f in got["folders"])
        whole = B.timeline(self.cat, None, 0, 1)["total"]
        self.assertEqual(here + below, whole)

    def test_walking_in_gets_what_is_in_that_one(self):
        top = B.inside(self.cat)
        first = top["folders"][0]["path"]
        got = B.inside(self.cat, first)
        self.assertEqual(got["where"], first)
        self.assertFalse(got["at_top"])
        for item in got["items"]:
            self.assertEqual(os.path.dirname(item["path"]), first)

    def test_and_the_crumbs_are_the_way_back_out(self):
        top = B.inside(self.cat)
        deep = top["folders"][0]["path"]
        got = B.inside(self.cat, deep)
        self.assertEqual([c["path"] for c in got["crumbs"]][-1], deep)
        for c in got["crumbs"]:
            self.assertNotIn(os.sep, c["name"].strip(os.sep))
        self.assertEqual(got["up"], os.path.dirname(deep))

    def test_everything_below_is_the_old_behaviour_kept_and_named(self):
        top = B.inside(self.cat)
        first = top["folders"][0]["path"]
        shallow = B.inside(self.cat, first)
        deep = B.inside(self.cat, first, deep=True)
        self.assertGreater(deep["total"], shallow["total"])
        self.assertTrue(deep["deep"])

    def test_a_path_outside_the_library_starts_at_the_top_instead(self):
        """Not an error page: a folder that is not in the library is a stale
        link or a typo, and the answer to both is "here is where you are"."""
        got = B.inside(self.cat, os.path.join(self.home, "nowhere"))
        self.assertEqual(got["where"], os.path.abspath(self.lib))

    def test_the_filters_over_the_grid_still_apply_in_here(self):
        """The folder view is a place, not an escape from what you asked for."""
        top = B.inside(self.cat)
        first = top["folders"][0]["path"]
        all_of = B.inside(self.cat, first, deep=True)
        starred = B.inside(self.cat, first, find.Ask(stars_from=5), deep=True)
        self.assertLessEqual(starred["total"], all_of["total"])
        for item in starred["items"]:
            self.assertEqual(self.cat.entry(item["path"])[9], 5)


class ASearchByPlaceName(unittest.TestCase):
    """"In Spain", when the file only knows 37.176, -3.5881.

    The index holds numbers. A person searches for a name. Crossing between them
    needs the imported place table, and `cat.hit` never did it - so every
    country and every town anybody typed matched nothing at all, whatever they
    typed, with no way to tell a wrong spelling from a missing table.
    """

    @classmethod
    def setUpClass(cls):
        from core import places, photo
        from core.store import store_path
        cls.home = tempfile.mkdtemp(prefix="placefind-")
        os.environ["PM_DATA"] = os.path.join(cls.home, "config")
        cls.lib = os.path.join(cls.home, "Photos")
        os.makedirs(cls.lib)
        S.save({"library": cls.lib})
        # two towns, two countries, far enough apart that nothing is ambiguous
        dump = os.path.join(cls.home, "cities.txt")
        rows = [("Rome", 41.8933, 12.4829, "IT"), ("Doha", 25.2854, 51.5310, "QA")]
        with open(dump, "w", encoding="utf-8") as fh:
            for name, lat, lon, cc in rows:
                bits = [""] * 19
                bits[0], bits[1], bits[2] = "1", name, name
                bits[4], bits[5] = f"{lat}", f"{lon}"
                bits[6], bits[7], bits[8] = "P", "PPL", cc
                bits[14] = "900000"
                fh.write("\t".join(bits) + "\n")
        places.import_dump(dump, store_path("places.tsv"))
        cls.cat = C.Catalogue(os.path.join(cls.home, "cat.json"))
        # the index straight out, rather than through a reader: this is about
        # what `matching` does with coordinates, not about reading EXIF
        for name, lat, lon in (("rome-1.JPG", 41.89, 12.48),
                               ("rome-2.JPG", 41.90, 12.49),
                               ("doha-1.JPG", 25.28, 51.53)):
            path = os.path.join(cls.lib, name)
            with open(path, "wb") as fh:
                fh.write(b"not a real jpeg")
            e = ["2023-05-01 10:00:00", "jpeg", "", "", None, None, None, "",
                 0, 0, "", [], lat, lon, 10, 0.0, ""]
            cls.cat.files[path] = e
        cls.cat.roots = [cls.lib]
        cls.cat._reorder()
        B._PLACES.clear()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)
        C.forget_all()
        B._PLACES.clear()

    def test_a_country_finds_the_photographs_taken_in_it(self):
        got = B.matching(self.cat, find.Ask(country="Italy"))
        self.assertEqual(len(got), 2, [p for _k, p in got])
        self.assertTrue(all("rome" in p for _k, p in got))

    def test_and_a_town_finds_the_ones_near_it(self):
        got = B.matching(self.cat, find.Ask(city="Doha"))
        self.assertEqual([os.path.basename(p) for _k, p in got], ["doha-1.JPG"])

    def test_a_name_the_library_does_not_hold_finds_nothing(self):
        """Which is a different answer from "it cannot look": this one is
        right, and before the fix both of them were empty."""
        self.assertEqual(B.matching(self.cat, find.Ask(country="Norway")), [])

    def test_the_lookup_is_done_once_per_coordinate_not_once_per_photograph(self):
        """A shoot is four hundred frames standing in one square hundred
        metres. Resolving that four hundred times is the slow screen this
        file exists to avoid."""
        B._PLACES.clear()
        B.matching(self.cat, find.Ask(country="Italy"))
        seen = B._PLACES.get("seen") or {}
        self.assertEqual(len(seen), 3)              # three distinct positions
        self.assertLessEqual(len(seen), len(self.cat.files))

    def test_and_nothing_is_looked_up_when_nothing_was_asked(self):
        B._PLACES.clear()
        B.matching(self.cat, find.Ask(stars_from=1))
        self.assertFalse(B._PLACES.get("seen"))

    def test_the_towns_and_countries_are_offered_as_menus(self):
        got = B.choices(self.cat)
        self.assertEqual(sorted(c["name"] for c in got["country"]), ["Italy", "Qatar"])
        self.assertIn("Rome", [c["name"] for c in got["city"]])
        self.assertTrue(got["places"]["table"])
        self.assertEqual(got["places"]["located"], 3)

    def test_and_with_no_table_it_says_so_rather_than_offering_nothing(self):
        from core.store import store_path
        where = store_path("places.tsv")
        with open(where, "r", encoding="utf-8") as fh:
            kept = fh.read()
        try:
            os.remove(where)
            B._PLACES.clear()
            got = B.choices(self.cat)
            self.assertEqual(got["country"], [])
            self.assertFalse(got["places"]["table"])
            # It still knows how many photographs HAVE a position - which is
            # what tells "no table" apart from "nothing is geotagged".
            self.assertEqual(got["places"]["located"], 3)
        finally:
            with open(where, "w", encoding="utf-8") as fh:
                fh.write(kept)
            B._PLACES.clear()


class OneFilterWorkedOutOnce(unittest.TestCase):
    """Scrolling the grid asks for page after page of one answer. Each page used
    to run the whole filter over the whole library again."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="browse-kept-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        self.lib = os.path.join(self.home, "Photos")
        fix = os.path.join(os.path.dirname(__file__), "fixtures")
        self.trip = os.path.join(self.lib, "2022", "Trip")
        self.scans = os.path.join(self.lib, "Scans")
        for where in (self.trip, self.scans):
            os.makedirs(where)
            for n in ("aeb1", "aeb2", "aeb3", "plain", "rated"):
                shutil.copy(os.path.join(fix, f"{n}.jpg"),
                            os.path.join(where, f"{n}.JPG"))
        S.save({"library": self.lib})
        self.cat = C.Catalogue("")
        self.cat.refresh([self.lib])
        B.forget_kept()
        self.real = B.matching
        self.calls = []

        def counting(*a, **k):
            self.calls.append(a[1:])
            return self.real(*a, **k)
        B.matching = counting

    def tearDown(self):
        B.matching = self.real
        B.forget_kept()
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.home, ignore_errors=True)

    def test_two_pages_of_one_filter_match_once(self):
        first = B.timeline(self.cat, None, 0, 4)
        second = B.timeline(self.cat, None, 4, 4)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(first["total"], 10)
        self.assertEqual(len(first["items"]) + len(second["items"]), 8)
        self.assertFalse({i["path"] for i in first["items"]}
                         & {i["path"] for i in second["items"]})

    def test_and_the_same_filter_is_shared_by_the_folder_view(self):
        B.timeline(self.cat, None, 0, 4)
        B.timeline(self.cat, None, 0, 4, by="folder")
        B.inside(self.cat, self.lib)
        self.assertEqual(len(self.calls), 1)

    def test_a_different_filter_is_worked_out_on_its_own(self):
        B.timeline(self.cat, None)
        B.timeline(self.cat, find.Ask(stars_from=4))
        B.timeline(self.cat, find.Ask(stars_from=4), 2, 2)
        self.assertEqual(len(self.calls), 2)

    def test_leaving_a_folder_out_starts_again(self):
        before = B.timeline(self.cat, None)
        S.save({"hide_in_grid": '["%s"]' % self.scans.replace("\\", "\\\\")})
        after = B.timeline(self.cat, None)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(after["total"], before["total"] - 5)

    def test_a_change_to_the_index_starts_again(self):
        before = B.timeline(self.cat, None)
        shutil.copy(os.path.join(self.trip, "plain.JPG"),
                    os.path.join(self.trip, "plain2.JPG"))
        self.cat.refresh([self.lib])
        after = B.timeline(self.cat, None)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(after["total"], before["total"] + 1)

    def test_the_answer_is_the_one_worked_out_from_scratch(self):
        import json
        kept = [json.dumps(B.timeline(self.cat, None, off, 3, by))
                for by in ("date", "folder") for off in (0, 3, 6)]
        B.forget_kept()
        fresh = []
        for by in ("date", "folder"):
            for off in (0, 3, 6):
                B.forget_kept()
                fresh.append(json.dumps(B.timeline(self.cat, None, off, 3, by)))
        self.assertEqual(kept, fresh)

    def test_map_pins_are_kept_per_zoom(self):
        real = B._clusters
        made = []

        def counting(cat, zoom, limit):
            made.append(zoom)
            return real(cat, zoom, limit)
        B._clusters = counting
        try:
            one = B.clusters(self.cat, 4)
            again = B.clusters(self.cat, 4)
            B.clusters(self.cat, 6)
        finally:
            B._clusters = real
        self.assertEqual(made, [4, 6])
        self.assertEqual(one, again)
        self.assertEqual(list(one), ["zoom", "pins", "located", "state"])
