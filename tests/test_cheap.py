"""What a screen costs when nothing has changed.

The home screen opened three hundred and twenty thousand files to draw eight
kilobytes of numbers, and not one of them was a photograph: they were all
`settings.json`, read once per photograph per dimension by the band tables, each
read carrying an `os.makedirs` from `store_path`. Fifteen seconds on an index of
eighty thousand, on a fast machine, for an answer that had not changed since the
last time it was asked.

These tests hold the three rules that came out of that:

    a setting is read when it CHANGES, not when it is asked for;
    what the settings say is worked out once per answer, not once per file;
    an answer is kept until the index or a setting moves.

They count syscalls rather than measuring time, because a timing test on a
shared machine is a test that fails for reasons that are nobody's fault.
"""

import builtins
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import browse as B                 # noqa: E402
from core import catalogue as C              # noqa: E402
from core import settings as S               # noqa: E402
from core import stats as ST                 # noqa: E402
from core import store                       # noqa: E402


class Counting:
    """How many files were opened, and how many folders made, while this ran."""

    def __enter__(self):
        self.opens = 0
        self.makedirs = 0
        self._open = builtins.open
        self._mk = os.makedirs

        def open_(*a, **k):
            self.opens += 1
            return self._open(*a, **k)

        def mk(*a, **k):
            self.makedirs += 1
            return self._mk(*a, **k)

        builtins.open = open_
        os.makedirs = mk
        return self

    def __exit__(self, *_):
        builtins.open = self._open
        os.makedirs = self._mk
        return False


def an_index(home, how_many=400):
    cat = C.Catalogue(os.path.join(home, "cat.json"))
    lib = os.path.join(home, "Photos")
    cat.roots = [lib]
    for i in range(how_many):
        path = os.path.join(lib, str(2020 + i % 5), f"IMG_{i:05d}.JPG")
        cat.files[path] = [f"{2020 + i % 5}-0{1 + i % 9}-01 10:00:00", "jpeg",
                           "DMC-GH4", "LUMIX 12-35", 35.0, 70.0, 4.0, "1/125",
                           400, i % 6, "", [], 36.0, -3.0, 1000, 1.7e9, ""]
    cat._reorder()
    return cat


class ASettingIsReadWhenItChanges(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cheap-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        store._MADE.clear()
        S.forget()
        B.forget_kept()

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.home, ignore_errors=True)
        store._MADE.clear()
        S.forget()
        B.forget_kept()

    def test_reading_it_a_thousand_times_opens_it_once(self):
        S.save({"library": os.path.join(self.home, "Photos")})
        S.load()                                   # the first, which does read it
        with Counting() as c:
            for _ in range(1000):
                S.load()
        self.assertEqual(c.opens, 0, "it is still being read every time")

    def test_and_the_data_folder_is_not_made_again_on_every_lookup(self):
        store.store_path("x")
        with Counting() as c:
            for _ in range(1000):
                store.store_path("x")
        self.assertEqual(c.makedirs, 0)

    def test_but_a_change_on_disk_is_picked_up(self):
        S.save({"bracket_tag": "one"})
        self.assertEqual(S.load()["bracket_tag"], "one")
        S.save({"bracket_tag": "two"})
        self.assertEqual(S.load()["bracket_tag"], "two")

    def test_and_what_a_caller_does_with_it_cannot_reach_the_next_caller(self):
        """Everybody gets their own copy. A Settings handed out twice and
        changed once would be a bug that appears somewhere else entirely."""
        S.save({"bracket_tag": "one"})
        first = S.load()
        first.values["bracket_tag"] = "scribbled on"
        self.assertEqual(S.load()["bracket_tag"], "one")


class TheHomeScreenDoesNotReadTheSettingsPerPhotograph(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cheap2-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        store._MADE.clear()
        S.forget()
        B.forget_kept()
        S.save({"library": os.path.join(self.home, "Photos")})
        self.cat = an_index(self.home)

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.home, ignore_errors=True)
        store._MADE.clear()
        S.forget()
        B.forget_kept()

    def test_four_hundred_photographs_do_not_cost_four_hundred_file_opens(self):
        B.dashboard(self.cat)                      # the first, which warms nothing
        with Counting() as c:
            B.dashboard(self.cat)
        self.assertLess(c.opens, 20,
                        f"{c.opens} file opens to count 400 photographs")
        self.assertLess(c.makedirs, 20)

    def test_the_band_tables_are_worked_out_once_for_a_whole_tally(self):
        said = ST.Edges()
        self.assertIsInstance(said.bands, dict)
        self.assertIsInstance(said.cameras, dict)
        # the camera's label is the one devices.label gives, worked out once
        from core import devices
        self.assertEqual(said.camera("DMC-GH4"), devices.label("DMC-GH4"))
        with Counting() as c:
            for _ in range(500):
                said.camera("DMC-GH4")
        self.assertEqual(c.opens, 0)


class AnAnswerIsKeptUntilItChanges(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cheap3-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        store._MADE.clear()
        S.forget()
        B.forget_kept()
        S.save({"library": os.path.join(self.home, "Photos")})
        self.cat = an_index(self.home)

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.home, ignore_errors=True)
        store._MADE.clear()
        S.forget()
        B.forget_kept()

    def test_asking_twice_works_it_out_once(self):
        made = []
        first = B.kept(self.cat, "t", lambda: made.append(1) or {"n": 1})
        again = B.kept(self.cat, "t", lambda: made.append(1) or {"n": 2})
        self.assertEqual(len(made), 1)
        self.assertIs(first, again)

    def test_but_a_changed_index_is_a_different_answer(self):
        B.kept(self.cat, "t", lambda: {"n": 1})
        self.cat.changes += 1
        made = []
        B.kept(self.cat, "t", lambda: made.append(1) or {"n": 2})
        self.assertEqual(len(made), 1, "a changed index served a stale answer")

    def test_and_so_is_a_changed_setting(self):
        """An album is a question whose wording lives in the settings - change
        "four stars and up" to five and the answer is a different answer."""
        B.kept(self.cat, "t", lambda: {"n": 1})
        S.save({"develop_jpeg_at": 5})
        made = []
        B.kept(self.cat, "t", lambda: made.append(1) or {"n": 2})
        self.assertEqual(len(made), 1, "a changed setting served a stale answer")

    def test_a_photograph_carries_its_own_date_so_its_picture_has_one_address(self):
        """Without it the grid asked for a new thumbnail address on every page
        load, and the browser cache - which the server allows for a day - could
        never be used."""
        path = next(iter(self.cat.files))
        card = B.card(self.cat, path)
        self.assertIn("when", card)
        self.assertEqual(card["when"], self.cat.files[path][15])

    def test_and_so_does_an_album_cover(self):
        for album in B.albums(self.cat):
            self.assertIn("cover_when", album, album["key"])


if __name__ == "__main__":
    unittest.main()
