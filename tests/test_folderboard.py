"""The folder board on the home screen: which shoots are not finished.

The Library tab has answered this since 1.x, by surveying five trees - which
means reading the front of every JPEG over SMB, a minute of waiting behind a
button. This answers the part of it the index already holds, with nothing read,
so the home screen can simply have it.

Two things have to be true for that to be worth having. It must agree with the
files (a half-rated folder has to look different from a finished one, and from
an untouched one), and it must stay a TREE under a filter - a shoot shown three
levels deep with nothing above it reads as an orphan, not as an answer.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import browse as B                 # noqa: E402
from core import catalogue as C              # noqa: E402

try:
    from PIL import Image                    # noqa: E402
    HAVE_PIL = True
except Exception:                            # noqa: BLE001
    HAVE_PIL = False


@unittest.skipUnless(HAVE_PIL, "making a photograph to index needs Pillow")
class TheBoard(unittest.TestCase):
    """One library, three shoots, each unfinished in a different way."""

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="board-")
        os.environ["PM_DATA"] = os.path.join(cls.home, "config")
        cls.lib = os.path.join(cls.home, "Photos")
        cls.made = {}
        # 2024/Spain - rated and placed: finished, as far as this can see
        cls.shot("2024/Spain", "a.jpg", stars=4, place=True)
        cls.shot("2024/Spain", "b.jpg", stars=5, place=True)
        # 2024/Wedding - half rated: the row worth having
        cls.shot("2024/Wedding", "c.jpg", stars=3, place=False)
        cls.shot("2024/Wedding", "d.jpg", stars=0, place=False)
        # 2023/Garden - a negative still in with the JPEGs
        cls.shot("2023/Garden", "e.jpg", stars=0, place=False)
        cls.raw("2023/Garden", "e.ARW")
        cls.cat = C.Catalogue(os.path.join(cls.home, f"c-{time.time_ns()}.json"))
        cls.cat.refresh([cls.lib])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)
        C.forget_all()

    @classmethod
    def shot(cls, where, name, stars=0, place=False):
        """A real JPEG with real EXIF, written by Pillow rather than by the code
        that will read it back."""
        from PIL import Image
        from PIL.TiffImagePlugin import IFDRational as Rat
        folder = os.path.join(cls.lib, *where.split("/"))
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        ex = Image.Exif()
        ex[0x010F], ex[0x0110] = "Panasonic", "DC-GH5"
        ex[0x0132] = "2024:05:01 10:00:00"
        if stars:
            ex[0x4746] = int(stars)
        sub = ex.get_ifd(0x8769)
        sub[0x9003] = "2024:05:01 10:00:00"
        if place:
            g = ex.get_ifd(0x8825)
            g[0x0001], g[0x0003] = "N", "E"
            g[0x0002] = (Rat(41, 1), Rat(23, 1), Rat(146, 100))
            g[0x0004] = (Rat(2, 1), Rat(10, 1), Rat(66, 100))
        Image.new("RGB", (60, 40), (120, 120, 120)).save(path, exif=ex.tobytes())
        return path

    @classmethod
    def raw(cls, where, name):
        folder = os.path.join(cls.lib, *where.split("/"))
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name)
        with open(path, "wb") as fh:
            fh.write(b"\x00" * 64)
        return path

    def rows(self, only="all"):
        got = B.folders(self.cat, only)
        return {r["label"]: r for r in got["rows"]}, got

    def test_every_folder_with_photographs_in_it_is_on_the_board(self):
        by, got = self.rows()
        self.assertIn("2024", by)
        self.assertIn(os.path.join("2024", "Spain"), by)
        self.assertIn(os.path.join("2024", "Wedding"), by)
        self.assertIn(os.path.join("2023", "Garden"), by)
        self.assertEqual(got["only"], "all")

    def test_a_parent_counts_everything_underneath_it(self):
        """"Is this shoot finished" is a question about the shoot, not about
        which level of it the files happen to sit at."""
        by, _ = self.rows()
        self.assertEqual(by["2024"]["photos"], 4)
        self.assertEqual(by[os.path.join("2024", "Spain")]["photos"], 2)
        self.assertEqual(by["2024"]["own_photos"], 0)

    def test_the_marks_are_none_some_and_all_and_some_is_the_point(self):
        by, _ = self.rows()

        def mark(label, what):
            return by[label]["marks"].get(what, "?")

        self.assertEqual(mark(os.path.join("2024", "Spain"), "rated"), "all")
        self.assertEqual(mark(os.path.join("2024", "Wedding"), "rated"), "some")
        self.assertEqual(mark(os.path.join("2023", "Garden"), "rated"), "none")
        # and a parent of a finished and an unfinished shoot is unfinished
        self.assertEqual(mark("2024", "rated"), "some")
        # the marks the index cannot answer say nothing rather than claiming
        # the work is done - the previews tree is not indexed at all
        self.assertEqual(mark(os.path.join("2024", "Spain"), "previews"), "empty")
        self.assertEqual(mark(os.path.join("2024", "Spain"), "culled"), "empty")

    def test_a_negative_still_in_with_the_jpegs_is_counted_and_not_as_a_photo(self):
        by, _ = self.rows()
        garden = by[os.path.join("2023", "Garden")]
        self.assertEqual(garden["raws_here"], 1)
        self.assertEqual(garden["photos"], 1)
        # and the mark says "not out", not "nothing to say"
        self.assertEqual(garden["marks"]["separated"], "none")

    def test_the_unfinished_filter_leaves_out_the_finished_shoot(self):
        by, _ = self.rows("unfinished")
        self.assertIn(os.path.join("2024", "Wedding"), by)
        self.assertNotIn(os.path.join("2024", "Spain"), by)

    def test_but_a_filter_never_leaves_a_folder_without_its_parents(self):
        """A shoot three levels in with nothing above it reads as an orphan."""
        for only in ("unfinished", "unrated", "unlocated", "raws"):
            rows = B.folders(self.cat, only)["rows"]
            seen = set()
            for row in rows:
                up = os.path.dirname(row["path"])
                if row["depth"]:
                    self.assertIn(up, seen,
                                  f"{only}: {row['label']} has no parent above it")
                seen.add(row["path"])

    def test_a_folder_that_matches_is_told_apart_from_one_kept_for_its_children(self):
        rows = B.folders(self.cat, "raws")["rows"]
        matched = {r["label"]: r["matched"] for r in rows}
        self.assertTrue(matched[os.path.join("2023", "Garden")])
        self.assertFalse(matched["2023"] is None)

    def test_it_agrees_with_the_overview_about_the_whole_library(self):
        """Two readings of one index that disagreed would be a bug nobody could
        see: the home screen would contradict itself in two cards."""
        board = B.folders(self.cat)
        sums = B.overview(self.cat)
        tops = [r for r in board["rows"] if r["depth"] == 0]
        self.assertEqual(sum(r["photos"] for r in tops), sums["shown"])
        self.assertEqual(sum(r["raws_here"] for r in tops), sums["raws"])

    def test_nothing_is_written_by_looking(self):
        before = {}
        for here, _dirs, files in os.walk(self.lib):
            for name in files:
                path = os.path.join(here, name)
                before[path] = os.stat(path).st_mtime_ns
        B.folders(self.cat, "unfinished")
        after = {}
        for here, _dirs, files in os.walk(self.lib):
            for name in files:
                path = os.path.join(here, name)
                after[path] = os.stat(path).st_mtime_ns
        self.assertEqual(before, after)

    def test_it_says_the_same_as_the_library_tab_about_the_same_folders(self):
        """One question, two ways of answering it. The Library tab reads the
        files; this reads the index. Where they both have something to say they
        have to say the same thing, or the home screen and the Library tab show
        two different colours for one folder and neither can be believed."""
        from app import registry as R
        import app.tasks                                   # noqa: F401
        from core import settings as S
        S.save({"library": self.lib})
        survey = R.get("library").make_plan({"folder": self.lib, "charts": False})
        theirs = {row["path"]: row for row in survey.tree}
        mine = {row["path"]: row for row in B.folders(self.cat)["rows"]}
        self.assertTrue(theirs and mine)
        shared = set(theirs) & set(mine)
        self.assertTrue(shared, "the two do not even name the same folders")
        for path in shared:
            a, b = theirs[path], mine[path]
            self.assertEqual(a["photos"], b["photos"], path)
            self.assertEqual(a["rated"], b["rated"], path)
            self.assertEqual(a["located"], b["located"], path)
            self.assertEqual(a["raws_here"], b["raws_here"], path)
            for key in ("rated", "located", "dated"):
                self.assertEqual(a["marks"][key], b["marks"][key],
                                 f"{path}: {key}")

    def test_and_never_claims_the_work_it_cannot_see_is_done(self):
        """The previews tree is not indexed. A tick there would be the one lie
        this screen must not tell, so it says nothing instead."""
        for row in B.folders(self.cat)["rows"]:
            self.assertEqual(row["marks"]["previews"], "empty", row["path"])
            self.assertEqual(row["marks"]["culled"], "empty", row["path"])

    def test_an_unknown_filter_is_everything_rather_than_nothing(self):
        got = B.folders(self.cat, "nonsense")
        self.assertEqual(got["only"], "all")
        self.assertTrue(got["rows"])


if __name__ == "__main__":
    unittest.main()


class LeftOutOfTheGrid(unittest.TestCase):
    """Hiding a folder from the Photos screen is a VIEW, not an exclusion.

    Setup's exclusion list means nothing walks in there - no feature, no index.
    This means "not while I am looking", and the difference has to hold: the
    scans beside the shoots are real photographs that must still be geotagged,
    counted and backed up.
    """

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="hide-")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        self.lib = os.path.join(self.home, "Photos")
        for where in ("Keep", "Scans"):
            os.makedirs(os.path.join(self.lib, where))
            for n in range(2):
                path = os.path.join(self.lib, where, f"{where}{n}.jpg")
                if HAVE_PIL:
                    Image.new("RGB", (40, 30), (90, 90, 90)).save(path)
                else:
                    with open(path, "wb") as fh:
                        fh.write(b"\xff\xd8\xff")
        self.cat = C.Catalogue(os.path.join(self.home, "c.json"))
        self.cat.refresh([self.lib])

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)
        C.forget_all()

    def hide(self, *folders):
        import json
        from core import settings as S
        S.save({"hide_in_grid": json.dumps([os.path.join(self.lib, f)
                                            for f in folders])})

    @unittest.skipUnless(HAVE_PIL, "needs a readable photograph")
    def test_the_grid_leaves_them_out(self):
        whole = B.timeline(self.cat)["total"]
        self.hide("Scans")
        after = B.timeline(self.cat)
        self.assertEqual(after["total"], whole - 2)
        self.assertTrue(after["hidden"], "it did not say what it left out")

    @unittest.skipUnless(HAVE_PIL, "needs a readable photograph")
    def test_but_the_library_still_has_them(self):
        self.hide("Scans")
        self.assertEqual(B.overview(self.cat)["shown"], 4)
        board = B.folders(self.cat)
        tops = [r for r in board["rows"] if r["depth"] == 0]
        self.assertEqual(sum(r["photos"] for r in tops), 4)

    @unittest.skipUnless(HAVE_PIL, "needs a readable photograph")
    def test_an_albums_count_is_what_opening_it_shows(self):
        """Two numbers for one album - a card saying 40 that opens on 12 - is
        the kind of wrong that reads as the app lying."""
        self.hide("Scans")
        for album in B.albums(self.cat):
            ask = B.album_ask(album["key"])
            self.assertEqual(album["count"],
                             B.timeline(self.cat, ask, 0, 9999)["total"],
                             album["title"])

    @unittest.skipUnless(HAVE_PIL, "needs a readable photograph")
    def test_a_folder_that_is_not_hidden_is_untouched(self):
        self.hide("Scans")
        paths = [i["path"] for i in B.timeline(self.cat)["items"]]
        self.assertTrue(paths)
        self.assertTrue(all("Keep" in p for p in paths), paths)

    def test_nonsense_in_the_setting_hides_nothing(self):
        from core import settings as S
        S.save({"hide_in_grid": "not json at all"})
        self.assertEqual(B.hidden_folders(), [])
