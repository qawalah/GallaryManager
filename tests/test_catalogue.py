"""The index: built once, kept, and never ahead of the disk.

The whole of 3.0 rests on this file being right. If the index is wrong the grid
shows photographs that are not there, the dashboard counts things twice, and the
map pins a trip somebody deleted last week - and all three are the kind of wrong
that looks like the app is lying rather than like a cache is stale.

So the tests here are mostly about the bargain, not about the shape: a file that
changed is read again, a file that went is dropped, a file that did not move
costs nothing, and nothing in here ever writes to a photograph.
"""

import os
import shutil
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile                              # noqa: E402

from core import catalogue as C              # noqa: E402
from core import demo, settings as S         # noqa: E402

try:
    import PIL                               # noqa: F401
    HAVE_PIL = True
except Exception:                            # noqa: BLE001
    HAVE_PIL = False


@unittest.skipUnless(HAVE_PIL, "the sample library needs Pillow")
class ReadingALibrary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="cat-")
        os.environ["PM_DATA"] = os.path.join(cls.home, "config")
        cls.sample = os.path.join(cls.home, "Sample")
        demo.build(cls.sample)
        cls.photos = os.path.join(cls.sample, demo.LIBRARY)
        cls.inbox = os.path.join(cls.sample, demo.INBOX)
        S.save({"library": cls.photos, "raw": os.path.join(cls.sample, demo.RAWTREE)})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)
        C.forget_all()

    def fresh(self):
        store = os.path.join(self.home, f"cat-{time.time_ns()}.json")
        return C.Catalogue(store)

    def test_it_reads_the_photographs_and_the_negatives_beside_them(self):
        cat = self.fresh()
        out = cat.refresh([self.photos, self.inbox])
        self.assertEqual(out["photos"], len(cat.files))
        self.assertGreater(out["photos"], 20)
        kinds = {cat.entry(p)[1] for p in cat.files}
        self.assertIn("jpeg", kinds)
        self.assertIn("raw", kinds)
        self.assertIn("video", kinds)

    def test_what_it_stores_is_what_a_search_speaks(self):
        """One shape, not two. The grid, the charts and the Search tab all
        judge a photograph through `find.Hit`, so the index holds one."""
        cat = self.fresh()
        cat.refresh([self.photos])
        path = next(p for p in cat.files if p.endswith("Alhambra-01.JPG"))
        hit = cat.hit(path)
        self.assertEqual(hit.camera, "DMC-GH4")
        self.assertEqual(hit.stars, 5)
        self.assertTrue(hit.located)
        self.assertTrue(hit.taken.startswith("2023-05-18"))
        self.assertEqual(hit.name, "Alhambra-01.JPG")

    def test_a_second_pass_over_an_unchanged_library_reads_nothing(self):
        """The bargain. A pass that re-read everything would make the index a
        tax on every restart instead of the thing that pays for itself."""
        cat = self.fresh()
        cat.refresh([self.photos])
        again = cat.refresh([self.photos])
        self.assertEqual(again["added"], 0)
        self.assertEqual(again["photos"], len(cat.files))

    def test_a_photograph_that_changed_is_read_again(self):
        cat = self.fresh()
        cat.refresh([self.photos])
        path = next(p for p in cat.files if p.endswith(".JPG"))
        was = cat.entry(path)[C._AT["sig"]]
        os.utime(path, (time.time() + 5, time.time() + 5))
        out = cat.refresh([self.photos])
        self.assertEqual(out["added"], 1)
        self.assertNotEqual(cat.entry(path)[C._AT["sig"]], was)

    def test_a_photograph_that_went_is_dropped(self):
        cat = self.fresh()
        folder = os.path.join(self.home, "Going")
        os.makedirs(folder, exist_ok=True)
        one = os.path.join(folder, "a.JPG")
        shutil.copy(next(p for p in os.listdir(self.inbox)
                         if p.endswith(".JPG")) and
                    os.path.join(self.inbox, next(p for p in os.listdir(self.inbox)
                                                  if p.endswith(".JPG"))), one)
        cat.refresh([folder])
        self.assertIn(one, cat.files)
        os.remove(one)
        out = cat.refresh([folder])
        self.assertNotIn(one, cat.files)
        self.assertEqual(out["gone"], 1)

    def test_it_survives_a_restart_without_reading_anything(self):
        store = os.path.join(self.home, "keep.json")
        first = C.Catalogue(store)
        first.refresh([self.photos])
        second = C.Catalogue(store)
        self.assertEqual(len(second.files), len(first.files))
        self.assertTrue(second.rows())
        again = second.refresh([self.photos])
        self.assertEqual(again["added"], 0, "a restart re-read the library")

    def test_it_knows_which_trees_it_can_answer_for(self):
        """An index that answered for a folder it never read would be worse
        than no index: the Library tab would quietly report on nothing."""
        cat = self.fresh()
        cat.refresh([self.photos])
        self.assertTrue(cat.covers([self.photos]))
        self.assertTrue(cat.covers([os.path.join(self.photos, "2023")]))
        self.assertFalse(cat.covers([self.inbox]))
        self.assertFalse(C.Catalogue("").covers([self.photos]))

    def test_the_newest_photograph_is_first(self):
        cat = self.fresh()
        cat.refresh([self.photos, self.inbox])
        keys = [k for k, _p in cat.rows()]
        self.assertEqual(keys, sorted(keys, reverse=True))

    def test_nothing_in_it_writes_to_a_photograph(self):
        cat = self.fresh()
        before = {}
        for here, _dirs, names in os.walk(self.photos):
            for n in names:
                p = os.path.join(here, n)
                before[p] = os.stat(p).st_mtime_ns
        cat.refresh([self.photos])
        for p, when in before.items():
            self.assertEqual(os.stat(p).st_mtime_ns, when, p)

    def test_the_mirrored_trees_are_not_indexed(self):
        """Indexing a mirror counts every photograph twice - once as itself and
        once as its own negative - and every number on the home screen is then
        wrong in a way that looks like the library is bigger than it is."""
        S.save({"library": self.photos, "raw": os.path.join(self.sample, demo.RAWTREE),
                "previews": os.path.join(self.sample, "Previews")})
        self.assertEqual(C.wanted_roots(), [self.photos])

    def test_anything_that_writes_marks_it_stale_and_a_pass_clears_it(self):
        """The index is never allowed to think it knows better than the disk.
        Every run in this app moves photographs; `touch()` is how it finds out,
        and the loop in the server is what acts on it."""
        cat = self.fresh()
        cat.refresh([self.photos])
        self.assertFalse(cat.state()["stale"])
        cat.touch()
        self.assertTrue(cat.state()["stale"])
        cat.refresh([self.photos])
        self.assertFalse(cat.state()["stale"])

    def test_it_can_be_read_while_it_is_being_rebuilt(self):
        """A rebuild must not freeze the page it is feeding. The lock is held
        around the swap, never around reading a photograph."""
        cat = self.fresh()
        cat.refresh([self.photos])
        rows = cat.rows()
        cat.start([self.photos, self.inbox])
        answered = cat.rows()                      # no exception, no wait
        self.assertTrue(answered)
        for _ in range(100):
            if not cat.busy():
                break
            time.sleep(0.05)
        self.assertFalse(cat.busy(), "the background pass never finished")
        self.assertGreater(len(cat.rows()), len(rows))

    def test_a_folder_that_is_not_there_is_not_an_error(self):
        cat = self.fresh()
        out = cat.refresh([os.path.join(self.home, "nope")])
        self.assertEqual(out["photos"], 0)
        self.assertTrue(cat.state()["error"])


class WithoutALibrary(unittest.TestCase):
    def test_an_empty_catalogue_answers_rather_than_raising(self):
        cat = C.Catalogue("")
        self.assertEqual(cat.rows(), [])
        self.assertEqual(cat.hits(), [])
        self.assertFalse(cat.state()["building"])
        self.assertIsNone(cat.hit("/nowhere/x.jpg"))

    def test_a_shutter_speed_comes_back_as_a_number(self):
        """`find.matches` searches shutter in seconds, and an index that handed
        it a string would silently match nothing at all."""
        self.assertAlmostEqual(C._seconds_of("1/250"), 0.004)
        self.assertAlmostEqual(C._seconds_of("2.5s"), 2.5)
        self.assertIsNone(C._seconds_of(""))
        self.assertIsNone(C._seconds_of("nonsense"))


class SayingWhatCouldNotBeRead(unittest.TestCase):
    """A file the index could not read is missing from everything built on it,
    so the index says how many there were, and names the first few."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cat-unread-")
        self.lib = os.path.join(self.home, "Photos")
        os.makedirs(self.lib)
        fix = os.path.join(os.path.dirname(__file__), "fixtures")
        for n in ("aeb1", "aeb2", "aeb3"):
            shutil.copy(os.path.join(fix, f"{n}.jpg"),
                        os.path.join(self.lib, f"{n}.JPG"))
        self._real = C._read_entry

    def tearDown(self):
        C._read_entry = self._real
        shutil.rmtree(self.home, ignore_errors=True)

    def failing(self, *names):
        real = self._real

        def read(path, *a, **k):
            if os.path.basename(path) in names:
                raise PermissionError(13, "Permission denied", path)
            return real(path, *a, **k)
        C._read_entry = read

    def test_one_unreadable_file_is_counted_and_named(self):
        self.failing("aeb2.JPG")
        cat = C.Catalogue("")
        out = cat.refresh([self.lib])
        self.assertEqual(out["photos"], 2)
        state = cat.state()
        self.assertEqual(state["unreadable"], 1)
        self.assertEqual(len(state["unreadable_names"]), 1)
        one = state["unreadable_names"][0]
        self.assertEqual(os.path.basename(one["path"]), "aeb2.JPG")
        self.assertIn("Permission denied", one["error"])

    def test_a_library_read_whole_says_none(self):
        cat = C.Catalogue("")
        cat.refresh([self.lib])
        self.assertEqual(cat.state()["unreadable"], 0)
        self.assertEqual(cat.state()["unreadable_names"], [])

    def test_only_the_first_twenty_are_named_but_all_are_counted(self):
        fix = os.path.join(os.path.dirname(__file__), "fixtures", "plain.jpg")
        names = [f"x{n:02}.JPG" for n in range(25)]
        for n in names:
            shutil.copy(fix, os.path.join(self.lib, n))
        self.failing(*names)
        cat = C.Catalogue("")
        cat.refresh([self.lib])
        self.assertEqual(cat.state()["unreadable"], 25)
        self.assertEqual(len(cat.state()["unreadable_names"]),
                         C.UNREADABLE_NAMES)

    def test_and_once_it_can_be_read_the_count_goes(self):
        self.failing("aeb2.JPG")
        cat = C.Catalogue("")
        cat.refresh([self.lib])
        C._read_entry = self._real
        cat.refresh([self.lib])
        self.assertEqual(cat.state()["unreadable"], 0)
        self.assertEqual(cat.state()["photos"], 3)

    def test_the_rail_says_so(self):
        from app.libraryui import SCRIPT
        self.assertIn("could not be read", SCRIPT)
        self.assertIn("IDX.unreadable", SCRIPT)


def _clip(path: str, seconds_since_1904: int) -> None:
    """The smallest mp4 whose movie header says when it was shot."""
    import struct

    def atom(name: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body) + 8) + name + body
    moov = atom(b"moov", atom(b"mvhd", b"\x00\x00\x00\x00"
                              + struct.pack(">I", seconds_since_1904)
                              + b"\x00" * 90))
    with open(path, "wb") as fh:
        fh.write(atom(b"ftyp", b"isom" + b"\x00" * 8) + moov)


class ClipsInTheIndex(unittest.TestCase):
    """A clip has no EXIF. Read the photograph way it had no time at all, so
    every clip sorted by file time and counted as undated on Home."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cat-clip-")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        self.lib = os.path.join(self.home, "Photos")
        os.makedirs(self.lib)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_a_clip_gets_the_time_in_its_movie_header(self):
        path = os.path.join(self.lib, "clip.mp4")
        _clip(path, 3772202602)                      # 2023-07-14 18:03:22
        cat = C.Catalogue("")
        cat.refresh([self.lib])
        entry = cat.entry(path)
        self.assertEqual(entry[C._AT["kind"]], "video")
        self.assertEqual(entry[C._AT["taken"]], "2023-07-14 18:03:22")

    def test_one_that_says_nothing_falls_back_to_its_file_time(self):
        path = os.path.join(self.lib, "clip.webm")
        shutil.copy(os.path.join(os.path.dirname(__file__), "fixtures",
                                 "tiny.webm"), path)
        stamp = time.mktime((2021, 3, 4, 5, 6, 7, 0, 0, -1))
        os.utime(path, (stamp, stamp))
        cat = C.Catalogue("")
        cat.refresh([self.lib])
        self.assertEqual(cat.entry(path)[C._AT["taken"]], "2021-03-04 05:06:07")


class WritesDuringAPass(unittest.TestCase):
    """A pass snapshots the index, walks, then swaps in what it found. A move
    the explorer reported in between used to vanish with the swap, and the
    index called itself up to date."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cat-race-")
        self.lib = os.path.join(self.home, "Photos")
        os.makedirs(self.lib)
        shutil.copy(os.path.join(os.path.dirname(__file__), "fixtures",
                                 "plain.jpg"), os.path.join(self.lib, "a.JPG"))

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_a_move_reported_mid_pass_leaves_the_index_stale(self):
        cat = C.Catalogue("")
        cat.refresh([self.lib])
        was = os.path.join(self.lib, "a.JPG")
        now = os.path.join(self.lib, "b.JPG")
        real = C._read_entry

        def moved_meanwhile(path, *a, **k):
            # The explorer moves a file while this pass is still reading.
            if os.path.exists(was):
                os.rename(was, now)
                cat.followed(moves=[(was, now)])
            return real(path, *a, **k)
        os.utime(was, None)
        os.utime(was, (time.time() + 5, time.time() + 5))  # read again
        C._read_entry = moved_meanwhile
        try:
            cat.refresh([self.lib])
        finally:
            C._read_entry = real
        self.assertTrue(cat.state()["stale"])
        cat.refresh([self.lib])
        self.assertFalse(cat.state()["stale"])
        self.assertEqual(list(cat.files), [now])

    def test_a_touch_mid_pass_is_not_cleared_by_that_pass(self):
        cat = C.Catalogue("")
        real = C._read_entry

        def touched(path, *a, **k):
            cat.touch()
            return real(path, *a, **k)
        C._read_entry = touched
        try:
            cat.refresh([self.lib])
        finally:
            C._read_entry = real
        self.assertTrue(cat.state()["stale"])


class TheLibraryTabsFolderCache(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cat-sig-")
        self.path = os.path.join(self.home, "a.JPG")
        shutil.copy(os.path.join(os.path.dirname(__file__), "fixtures",
                                 "plain.jpg"), self.path)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def test_a_rating_changed_in_place_changes_the_signature(self):
        """Same size, timestamps restored on purpose: only the rewrite itself
        (a new inode) says the folder changed."""
        from core import exifwrite, survey
        exifwrite.write_rating(self.path, 3)
        before = survey.signature(self.home)
        size = os.path.getsize(self.path)
        exifwrite.write_rating(self.path, 0)
        self.assertEqual(os.path.getsize(self.path), size,
                         "this is not the case being tested")
        self.assertNotEqual(survey.signature(self.home), before)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAVE_PIL, "the sample library needs Pillow")
class SayingWhatItIsDoing(unittest.TestCase):
    """A pass that opens nothing is a check, not work.

    The index walks the library every minute to see what changed. On a library
    nobody has touched that reads no files at all - and announcing "Reading your
    library" every minute is how the one line that matters, when photographs
    really are still missing, becomes a line nobody reads.
    """

    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="idx-")
        os.environ["PM_DATA"] = os.path.join(cls.home, "config")
        cls.sample = os.path.join(cls.home, "Sample")
        demo.build(cls.sample)
        cls.photos = os.path.join(cls.sample, demo.LIBRARY)
        S.save({"library": cls.photos})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.home, ignore_errors=True)
        C.forget_all()

    def fresh(self):
        return C.Catalogue(os.path.join(self.home, f"c-{time.time_ns()}.json"))

    def test_a_pass_that_changes_nothing_is_not_counted_as_a_change(self):
        cat = self.fresh()
        cat.refresh([self.photos])
        was = cat.state()["changes"]
        self.assertGreaterEqual(was, 1)              # the first build IS a change
        cat.refresh([self.photos])
        self.assertEqual(cat.state()["changes"], was)

    def test_but_a_photograph_that_appeared_is(self):
        cat = self.fresh()
        cat.refresh([self.photos])
        was = cat.state()["changes"]
        shutil.copy(os.path.join(self.photos, os.listdir(self.photos)[0])
                    if os.path.isfile(os.path.join(self.photos,
                                                   os.listdir(self.photos)[0]))
                    else next(os.path.join(r, f)
                              for r, _d, fs in os.walk(self.photos) for f in fs),
                    os.path.join(self.photos, "another.JPG"))
        try:
            cat.refresh([self.photos])
            self.assertEqual(cat.state()["changes"], was + 1)
        finally:
            os.remove(os.path.join(self.photos, "another.JPG"))

    def test_and_it_says_how_many_files_it_is_actually_opening(self):
        cat = self.fresh()
        cat.refresh([self.photos])
        # finished: nothing in hand
        self.assertEqual(cat.state()["reading"], 0)
        self.assertFalse(cat.state()["building"])


class WhenTheLibraryMoves(unittest.TestCase):
    """Setup names a different library. The index has to stop answering for
    the old one at once - not after the minute it used to wait, and not after
    however long the new library takes to read."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cat-moves-")
        self._data = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        S.forget()
        fix = os.path.join(os.path.dirname(__file__), "fixtures")
        self.a = os.path.join(self.home, "Old")
        self.b = os.path.join(self.home, "New")
        self.inner = os.path.join(self.a, "2022")
        for where, names in ((self.a, ("plain",)), (self.inner, ("rated",)),
                             (self.b, ("aeb1", "aeb2"))):
            os.makedirs(where, exist_ok=True)
            for n in names:
                shutil.copy(os.path.join(fix, f"{n}.jpg"),
                            os.path.join(where, f"{n}.JPG"))
        self.cat = C.Catalogue(os.path.join(self.home, "cat.json"))
        self.cat.refresh([self.a])

    def tearDown(self):
        if self._data is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._data
        S.forget()
        shutil.rmtree(self.home, ignore_errors=True)

    def names(self):
        return sorted(os.path.basename(p) for p in self.cat.files)

    def test_the_old_library_leaves_before_the_new_one_is_read(self):
        changes = self.cat.changes
        gone = self.cat.let_go([self.b])
        self.assertEqual(gone, 2)
        self.assertEqual(self.names(), [])
        self.assertGreater(self.cat.changes, changes)    # the page redraws
        # Named, but not read yet: nothing may trust it for the new library.
        self.assertFalse(self.cat.covers([self.b]))
        self.assertTrue(self.cat.unread)

    def test_once_the_new_one_is_read_it_is_trusted(self):
        self.cat.let_go([self.b])
        self.cat.refresh([self.b])
        self.assertEqual(self.names(), ["aeb1.JPG", "aeb2.JPG"])
        self.assertFalse(self.cat.unread)
        self.assertTrue(self.cat.covers([self.b]))
        self.assertFalse(self.cat.covers([self.a]))

    def test_a_refresh_on_its_own_drops_the_old_library_too(self):
        self.cat.refresh([self.b])
        self.assertEqual(self.names(), ["aeb1.JPG", "aeb2.JPG"])
        # and says so on disk, so a restart does not bring the old one back
        again = C.Catalogue(os.path.join(self.home, "cat.json"))
        self.assertEqual(sorted(os.path.basename(p) for p in again.files),
                         ["aeb1.JPG", "aeb2.JPG"])

    def test_moving_into_a_folder_of_it_keeps_what_is_still_inside(self):
        self.assertEqual(self.cat.let_go([self.inner]), 1)
        self.assertEqual(self.names(), ["rated.JPG"])

    def test_the_same_library_written_differently_is_not_a_move(self):
        self.assertFalse(C.trees_moved([self.a], [self.a + os.sep]))
        self.assertEqual(self.cat.let_go([self.a + os.sep]), 0)
        self.assertFalse(self.cat.unread)
        self.assertTrue(C.trees_moved([self.a], [self.b]))

    def test_no_library_at_all_empties_the_index(self):
        S.save({"library": "", "video": ""})
        self.assertTrue(C.nothing_set())
        self.assertTrue(self.cat.clear())
        self.assertEqual(self.cat.files, {})
        self.assertEqual(self.cat.roots, [])
        self.assertFalse(self.cat.clear())                 # nothing left to clear

    def test_a_library_that_is_only_missing_is_still_set(self):
        S.save({"library": os.path.join(self.home, "not mounted")})
        self.assertFalse(C.nothing_set())
