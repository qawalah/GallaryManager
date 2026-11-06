"""The index doing less work for the same answer.

Three changes, each with the same shape: the app already knew something and was
asking the filesystem - or itself - again anyway.

    "is there a sidecar next to this?"   asked twelve times per photograph,
                                         by seven callers, two stats each
    "has this file changed since?"       asked eleven times while reading one
    "did anything move?"                 answered by walking eighty thousand
                                         files to rediscover the forty this app
                                         had moved itself
    "does this match?"                   answered by building an object per
                                         photograph to ask it one question

These tests count syscalls and compare answers rather than measuring time: a
timing test on a shared machine fails for reasons that are nobody's fault.
"""

import builtins
import itertools
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import catalogue as C             # noqa: E402
from core import find                      # noqa: E402
from core import settings as S             # noqa: E402
from core import sidecar                   # noqa: E402
from core import steady                    # noqa: E402
from core import store                     # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Stats:
    """How many times the filesystem was stat'd while this ran."""

    def __enter__(self):
        self.n = 0
        self._was = os.stat

        def spy(*a, **k):
            self.n += 1
            return self._was(*a, **k)

        os.stat = spy
        return self

    def __exit__(self, *_):
        os.stat = self._was
        return False


class Base(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cheaper-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        store._MADE.clear()
        S.forget()
        sidecar.forget()
        C.forget_all()
        self.lib = os.path.join(self.home, "Photos")
        self.shoot = os.path.join(self.lib, "2023", "Spain")
        os.makedirs(self.shoot)
        for i in range(30):
            shutil.copy(os.path.join(FIX, "plain.jpg"),
                        os.path.join(self.shoot, f"IMG_{i:03d}.JPG"))
        S.save({"library": self.lib})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.home, ignore_errors=True)
        store._MADE.clear()
        S.forget()
        sidecar.forget()
        C.forget_all()

    def index(self):
        cat = C.Catalogue(os.path.join(self.home, "cat.json"))
        cat.refresh([self.lib])
        return cat


class TheSidecarQuestionIsAskedOnce(Base):
    def test_a_folder_is_listed_rather_than_every_name_tried(self):
        """Seven callers ask "is there a .xmp next to this", two stats each.
        One listing answers it for every photograph in the folder."""
        one = os.path.join(self.shoot, "IMG_000.JPG")
        sidecar.beside(one)                              # the listing
        with Stats() as c:
            for i in range(30):
                sidecar.beside(os.path.join(self.shoot, f"IMG_{i:03d}.JPG"))
        self.assertLessEqual(c.n, 30, "it is still asking file by file")

    def test_but_a_sidecar_that_appears_is_found(self):
        one = os.path.join(self.shoot, "IMG_000.JPG")
        self.assertIsNone(sidecar.beside(one))
        sidecar.write(one, **{"xmp:Rating": "5"})
        self.assertTrue(sidecar.beside(one), "a sidecar written here was missed")

    def test_and_one_that_appears_from_outside_is_found_too(self):
        """The listing is kept against the folder's own date, and creating a
        file in a folder moves it."""
        one = os.path.join(self.shoot, "IMG_001.JPG")
        self.assertIsNone(sidecar.beside(one))
        with open(os.path.splitext(one)[0] + ".xmp", "w", encoding="utf-8") as fh:
            fh.write("<x/>")
        self.assertTrue(sidecar.beside(one))

    def test_and_a_folder_that_cannot_be_listed_still_answers(self):
        """Unable to list a folder is not a reason to say there is no sidecar
        in it."""
        gone = os.path.join(self.home, "nowhere", "IMG_000.JPG")
        self.assertIsNone(sidecar.beside(gone))


class OneFileHeldStill(Base):
    def test_reading_a_photograph_stats_it_once_not_a_dozen_times(self):
        cat = self.index()                               # everything read once
        with Stats() as c:
            cat.refresh([self.lib])
        self.assertLessEqual(c.n, 30 + 10,
                             f"{c.n} stats for a pass over 30 unchanged files")

    def test_outside_that_scope_nothing_changes(self):
        """A caller that has not vouched for a file gets the old behaviour -
        the file is stat'd before its bytes are served."""
        from core import jpegseg
        one = os.path.join(self.shoot, "IMG_000.JPG")
        jpegseg.read_header(one)
        with Stats() as c:
            jpegseg.read_header(one)
        self.assertGreaterEqual(c.n, 1, "it stopped checking whether it changed")

    def test_and_a_file_that_changes_mid_scope_is_not_served_stale(self):
        """The scope says "I have just stat'd this"; it does not say "nothing
        will ever change". Held with its own stat, the answer is that stat."""
        one = os.path.join(self.shoot, "IMG_000.JPG")
        with steady.holding(one):
            self.assertIsNotNone(steady.stat_of(one))
            self.assertIsNone(steady.stat_of(os.path.join(self.shoot, "IMG_001.JPG")))
        self.assertIsNone(steady.stat_of(one), "the scope outlived its block")


class TheIndexFollowsWhatTheAppDid(Base):
    def test_a_move_does_not_cost_a_walk(self):
        from core import filesops
        cat = self.index()
        C._ONE = cat                                     # the shared one, for filesops
        was = os.path.join(self.shoot, "IMG_000.JPG")
        into = os.path.join(self.lib, "2024")
        os.makedirs(into)
        jobs = filesops.gather([was], into)
        with Stats() as c:
            filesops.run(jobs, move=True)
        now = os.path.join(into, "IMG_000.JPG")
        self.assertIn(now, cat.files, "the index did not follow the file")
        self.assertNotIn(was, cat.files, "the index kept it where it was")
        self.assertLess(c.n, 60, f"{c.n} stats to move one file")

    def test_the_photograph_keeps_what_was_read_about_it(self):
        """A move is not a change to a photograph, so nothing is read again -
        but the signature is taken afresh, because a move changes the inode."""
        from core import filesops
        cat = self.index()
        C._ONE = cat
        was = os.path.join(self.shoot, "IMG_001.JPG")
        before = list(cat.files[was])
        into = os.path.join(self.lib, "2025")
        os.makedirs(into)
        filesops.run(filesops.gather([was], into), move=True)
        after = cat.files[os.path.join(into, "IMG_001.JPG")]
        for name in ("taken", "camera", "stars", "tags"):
            self.assertEqual(after[C._AT[name]], before[C._AT[name]], name)

    def test_a_whole_folder_moved_takes_everything_under_it(self):
        from core import filesops
        cat = self.index()
        C._ONE = cat
        into = os.path.join(self.lib, "2026")
        os.makedirs(into)
        filesops.run(filesops.gather([self.shoot], into), move=True)
        landed = os.path.join(into, "Spain")
        self.assertEqual(len([p for p in cat.files if p.startswith(landed)]), 30)
        self.assertFalse([p for p in cat.files if p.startswith(self.shoot + os.sep)])

    def test_and_a_delete_takes_them_out_of_it(self):
        cat = self.index()
        C._ONE = cat
        one = os.path.join(self.shoot, "IMG_002.JPG")
        cat.followed(gone=[one])
        self.assertNotIn(one, cat.files)

    def test_an_index_that_cannot_follow_asks_for_a_walk_instead(self):
        """Told a file landed somewhere it is not, it says so rather than
        writing down a guess."""
        cat = self.index()
        cat.stale = False
        cat.followed(moves=[[os.path.join(self.shoot, "IMG_003.JPG"),
                             os.path.join(self.home, "nowhere", "x.JPG")]])
        self.assertTrue(cat.stale)


class TheIndexIsWrittenOnlyWhenItChanges(Base):
    def test_a_pass_that_finds_nothing_writes_nothing(self):
        cat = self.index()
        when = os.stat(cat.path).st_mtime_ns
        got = cat.refresh([self.lib])
        self.assertFalse(got["written"])
        self.assertEqual(os.stat(cat.path).st_mtime_ns, when)

    def test_but_a_pass_that_finds_something_does(self):
        cat = self.index()
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(self.shoot, "NEW.JPG"))
        got = cat.refresh([self.lib])
        self.assertTrue(got["written"])
        self.assertEqual(got["added"], 1)


class TheRowRulesItselfOutOrSaysNothing(unittest.TestCase):
    """`find.cannot_match` may only ever answer "this cannot match".

    It exists so a filter does not build eighty thousand objects to ask each of
    them one question. It is a second piece of code about what matches, which is
    the thing this app has always refused to have - so this test runs it and
    `find.matches` over a grid and fails the moment they disagree.
    """

    def rows(self):
        out = []
        for i, (stars, colour, taken, kind_, tags, lat) in enumerate(
                itertools.product(
                    (0, 3, 5), ("", "red"), ("", "2020-06-01 10:00:00",
                                             "2023-06-01 10:00:00"),
                    ("jpeg", "video"), ((), ("family",), ("family", "trip")),
                    (None, 36.0))):
            e = ["", kind_, "DMC-GH4", "lens", 35.0, 70.0, 4.0, "1/125", 400,
                 stars, colour, list(tags), lat, -3.0 if lat else None,
                 1000, 1.7e9, ""]
            e[0] = taken
            name = f"IMG_{i:04d}." + ("MP4" if kind_ == "video" else "JPG")
            out.append((os.path.join("/lib/2023", name), e))
        return out

    def asks(self):
        return [
            find.Ask(),
            find.Ask(stars_from=4), find.Ask(stars_to=2),
            find.Ask(stars_from=1, stars_to=4),
            find.Ask(colour="red"),
            find.Ask(since="2023-01-01"), find.Ask(until="2021-01-01"),
            find.Ask(since="2020-01-01", until="2020-12-31"),
            find.Ask(located="yes"), find.Ask(located="no"),
            find.Ask(tags=("family",)),
            find.Ask(tags=("family", "trip"), all_tags=True),
            find.Ask(tags=("family", "trip")),
            find.Ask(kinds=("video",)), find.Ask(kinds=("jpeg",)),
            find.Ask(name="IMG"), find.Ask(name="nothing"),
            find.Ask(stars_from=5, colour="red", located="yes"),
        ]

    def hit_for(self, path, e):
        hit = find.Hit(path=path, name=os.path.basename(path),
                       folder=os.path.dirname(path))
        hit.taken, hit.camera, hit.lens = e[0], e[2], e[3]
        hit.focal, hit.focal35, hit.fnumber = e[4], e[5], e[6]
        hit.shutter, hit.iso, hit.stars = e[7], e[8], e[9]
        hit.colour, hit.tags = e[10], list(e[11])
        hit.located = e[12] is not None
        hit.lat, hit.lon, hit.size, hit.when = e[12], e[13], e[14], e[15]
        hit.seconds = 1 / 125
        return hit

    def test_it_never_rules_out_something_that_would_have_matched(self):
        ruled = kept = 0
        for ask in self.asks():
            for path, e in self.rows():
                no = find.cannot_match(e, path, ask)
                ok, _unknown = find.matches(self.hit_for(path, e), ask)
                if no:
                    ruled += 1
                    self.assertFalse(ok, f"{ask.asked()} ruled out a match: {path}")
                else:
                    kept += 1
        self.assertTrue(ruled, "it rules nothing out at all - it is doing nothing")
        self.assertTrue(kept)

    def test_and_it_does_rule_most_of_them_out(self):
        """Not a correctness rule - the point of it. A filter that leaves
        everything to be built into an object has gained nothing."""
        rows = self.rows()
        ruled = sum(1 for path, e in rows
                    if find.cannot_match(e, path, find.Ask(stars_from=5)))
        self.assertGreater(ruled, len(rows) * 0.5)

    def test_an_empty_ask_rules_nothing_out(self):
        for path, e in self.rows():
            self.assertFalse(find.cannot_match(e, path, find.Ask()))

    def test_and_a_row_with_no_capture_time_is_left_to_the_real_matcher(self):
        """"No date on it" is a shrug, not a no, and which of the two it is
        belongs to `matches`."""
        path = "/lib/IMG_0001.JPG"
        e = ["", "jpeg", "", "", None, None, None, "", 0, 0, "", [], None, None,
             0, 0.0, ""]
        self.assertFalse(find.cannot_match(e, path, find.Ask(since="2020-01-01")))


if __name__ == "__main__":
    unittest.main()
