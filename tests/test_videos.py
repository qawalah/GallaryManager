"""Video: a tree of its own, in the same shape as the library.

Every camera in the house also shoots video, and it lands in the photo folders.
The three ways that hurts are all quiet: a folder that is half clips reports
numbers that are half about something else; a minute of 4K is a gigabyte, which
is why a library that is "mostly photographs" will not fit anywhere; and half
the tools here skip video without saying so.

What is tested is mostly what must NOT happen: a photograph must never move, a
clip must never be renamed, and a proxy file must never be left behind on its
own.
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
from core import survey as SV              # noqa: E402
from core.photo import is_video, kind      # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class KnowingWhatIsVideo(unittest.TestCase):
    def test_the_extensions_every_camera_here_writes(self):
        for name in ("a.MP4", "b.mov", "c.MTS", "d.m2ts", "e.avi", "f.mkv",
                     "g.insv"):
            self.assertEqual(kind(name), "video", name)
            self.assertTrue(is_video(name))

    def test_and_what_is_not(self):
        for name in ("a.jpg", "b.RW2", "c.xmp", "d.txt", "e.mp3"):
            self.assertNotEqual(kind(name), "video", name)

    def test_a_proxy_is_not_itself_a_clip(self):
        """GoPro's .LRV is a low-resolution copy and its .THM a thumbnail. They
        travel WITH a clip, the way a sidecar travels with a photograph - counted
        as video they would double every number."""
        self.assertNotEqual(kind("GX010042.LRV"), "video")
        self.assertNotEqual(kind("GX010042.THM"), "video")


class Separating(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="videos-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.video = os.path.join(self.dir, "Videos")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(self.shoot, "P1000001.JPG"))
        for name in ("GX010042.MP4", "GX010042.LRV", "GX010042.THM",
                     "P1000002.MOV"):
            with open(os.path.join(self.shoot, name), "wb") as fh:
                fh.write(b"x" * 2048)
        S.save({"library": self.lib, "video": self.video})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def plan(self, **over):
        t = R.get("videos")
        p = t.make_plan({"folder": self.lib, **over})
        self.assertFalse(p.blocked, p.blocked)
        return t, p

    def moving(self, p):
        return {os.path.basename(r.source) for r in p.rows}

    def test_the_clips_move_and_the_photograph_does_not(self):
        _t, p = self.plan()
        self.assertIn("GX010042.MP4", self.moving(p))
        self.assertIn("P1000002.MOV", self.moving(p))
        self.assertNotIn("P1000001.JPG", self.moving(p))

    def test_the_tree_keeps_the_librarys_shape(self):
        t, p = self.plan()
        self.assertEqual(t.apply(p).failed, 0)
        self.assertTrue(os.path.isfile(
            os.path.join(self.video, "2022", "Spain", "GX010042.MP4")))
        self.assertTrue(os.path.isfile(os.path.join(self.shoot, "P1000001.JPG")))

    def test_a_proxy_and_a_thumbnail_travel_with_their_clip(self):
        """Left behind they are silent rubbish that makes a tidied folder look
        untidy, and nothing else in the app knows what they are."""
        _t, p = self.plan()
        self.assertIn("GX010042.LRV", self.moving(p))
        self.assertIn("GX010042.THM", self.moving(p))

    def test_but_only_of_the_clip_they_actually_belong_to(self):
        """`GX010042.MP4` and `GX010042 edit.mp4` in one folder must not drag
        each other's companions along."""
        with open(os.path.join(self.shoot, "GX010042 edit.LRV"), "wb") as fh:
            fh.write(b"x")
        _t, p = self.plan()
        goes_with = {os.path.basename(r.source): r.detail for r in p.rows}
        self.assertNotIn("GX010042 edit.LRV", goes_with)

    def test_it_is_anchored_to_the_library_not_to_what_you_picked(self):
        """Scanning one shoot has to put clips exactly where scanning the whole
        library would - or two runs build two different trees that collide."""
        _t, p = self.plan(folder=self.shoot)
        target = [r.target for r in p.rows if r.name == "GX010042.MP4"][0]
        self.assertEqual(target,
                         os.path.join(self.video, "2022", "Spain", "GX010042.MP4"))

    def test_a_video_tree_inside_the_library_is_refused(self):
        inside = os.path.join(self.lib, "Clips")
        os.makedirs(inside)
        t = R.get("videos")
        p = t.make_plan({"folder": self.lib, "video": inside, "mirror": False})
        self.assertTrue(p.blocked)
        self.assertIn("found again on the next run", p.blocked)

    def test_with_no_video_tree_it_says_so_rather_than_guessing_one(self):
        t = R.get("videos")
        p = t.make_plan({"folder": self.lib, "video": "", "mirror": False})
        self.assertTrue(p.blocked)
        self.assertIn("where the video tree is", p.blocked)

    def test_each_clip_is_named_before_it_moves_not_only_after(self):
        """A clip going to another drive is a copy that can take minutes. With
        the name said only once it had arrived, the bar sat at "0 of N" with
        nothing under it - which is what "it does nothing" looked like."""
        t, p = self.plan()
        said = []
        t.apply(p, progress=lambda i, n, name, status="OK":
                said.append((i, name)))
        first = p.rows[0].name
        self.assertEqual(said[0], (0, first))
        self.assertIn((1, first), said)

    def test_it_says_it_is_listing_before_there_is_anything_to_count(self):
        said = []
        R.get("videos").make_plan(
            {"folder": self.lib},
            progress=lambda i, n, name, status="OK": said.append(name))
        self.assertTrue(said[0].startswith("listing everything in"), said[:2])

    def test_running_it_twice_moves_nothing_the_second_time(self):
        t, p = self.plan()
        t.apply(p)
        _t2, p2 = self.plan()
        self.assertEqual(p2.rows, [])


class FiledWithItsShoot(unittest.TestCase):
    """The point of reading a clip's clock: a clip dumped in a card folder still
    belongs with the photographs it was taken among."""

    def setUp(self):
        from tests.test_video_time import has, make_clip
        if not has("ffmpeg"):
            self.skipTest("no ffmpeg here to make a real clip with")
        self.dir = tempfile.mkdtemp(prefix="shootmatch-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.video = os.path.join(self.dir, "Videos")
        # The fixtures were all taken at 2022-07-14 18:03, so that is the shoot.
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        for n in ("plain", "rated", "aeb1"):
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(self.shoot, n + ".JPG"))
        # ...and the clips are sitting in an unsorted card dump.
        self.dump = os.path.join(self.lib, "card dump")
        os.makedirs(self.dump)
        make_clip(os.path.join(self.dump, "DURING.MP4"), "2022-07-14T18:10:00Z")
        make_clip(os.path.join(self.dump, "MONTHS_LATER.MP4"), "2022-11-02T09:00:00Z")
        S.save({"library": self.lib, "video": self.video})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def plan(self, **over):
        t = R.get("videos")
        p = t.make_plan({"folder": self.lib, **over})
        self.assertFalse(p.blocked, p.blocked)
        return t, p

    def where(self, p):
        return {r.name: os.path.relpath(os.path.dirname(r.target), self.video)
                for r in p.rows}

    def test_a_clip_from_the_card_dump_lands_with_its_shoot(self):
        _t, p = self.plan()
        self.assertEqual(self.where(p)["DURING.MP4"],
                         os.path.join("2022", "Spain"))

    def test_and_one_from_another_month_falls_back_to_its_own_date(self):
        _t, p = self.plan()
        self.assertEqual(self.where(p)["MONTHS_LATER.MP4"],
                         os.path.join("2022", "11"))
        said = [r.detail for r in p.rows if r.name == "MONTHS_LATER.MP4"][0]
        self.assertIn("its own date", said)

    def test_the_row_says_which_of_the_rules_decided_it(self):
        """A clip filed with its shoot and a clip filed by the folder it happens
        to be in are worth very different amounts of trust."""
        _t, p = self.plan()
        said = [r.detail for r in p.rows if r.name == "DURING.MP4"][0]
        self.assertIn("with the photos of Spain", said)
        # seven minutes after the last frame of the shoot, which is "near" rather
        # than "during" - and the row says which, in minutes rather than "0h"
        self.assertIn("7 min from", said)

    def test_matching_can_be_turned_off_and_it_mirrors_as_before(self):
        _t, p = self.plan(by_time=False, shape="same")
        self.assertEqual(self.where(p)["DURING.MP4"], "card dump")

    def test_a_clip_with_no_readable_time_keeps_its_position(self):
        with open(os.path.join(self.dump, "BROKEN.MP4"), "wb") as fh:
            fh.write(b"not a video")
        _t, p = self.plan()
        self.assertEqual(self.where(p)["BROKEN.MP4"], "card dump")
        said = [r.detail for r in p.rows if r.name == "BROKEN.MP4"][0]
        self.assertIn("the folder it is in now", said)


class FromTheIndex(FiledWithItsShoot):
    """The same answers, read from the index instead of opening every
    photograph. With a library of any size over a network share the survey was
    long enough that "File by shoot" looked as if it never finished, while the
    index already held every capture time it was reading."""

    def setUp(self):
        super().setUp()
        from unittest import mock
        from core import catalogue as C
        C.forget_all()
        C.shared().refresh([self.lib])

        def no_survey(*_a, **_k):
            raise AssertionError("opened every photograph again")
        self.patch = mock.patch.object(SV, "survey", no_survey)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        from core import catalogue as C
        C.forget_all()
        super().tearDown()

    def test_the_index_and_the_survey_see_the_same_shoots(self):
        from app.tasks.videos import shoot_windows
        from_index, clips, said = shoot_windows(self.lib)
        self.assertEqual(said, "index")
        self.assertEqual(clips, 2)
        self.assertTrue(from_index)
        self.assertEqual([(w.key, w.first, w.last) for w in from_index],
                         [(w.key, w.first, w.last) for w in self.surveyed()])

    def surveyed(self):
        from core import shoots
        self.patch.stop()
        try:
            return shoots.from_survey(SV.survey(self.lib))
        finally:
            self.patch.start()

    def test_an_index_of_another_library_is_not_trusted(self):
        from app.tasks.videos import shoot_windows
        from core import catalogue as C
        other = os.path.join(self.dir, "Elsewhere")
        os.makedirs(other)
        C.forget_all()
        C.shared().refresh([other])
        self.patch.stop()
        try:
            _w, _c, said = shoot_windows(self.lib)
        finally:
            self.patch.start()
        self.assertEqual(said, "survey")


class TheLibraryView(Separating):
    def survey(self):
        return SV.survey(self.lib, "", "", video_root=self.video)

    def test_a_folder_holding_clips_says_none_separated(self):
        got = self.survey().folders[self.shoot]
        self.assertEqual(got.videos_here, 2)
        self.assertEqual(got.marks()["video"], "none")

    def test_and_all_of_them_once_they_have_moved(self):
        t, p = self.plan()
        t.apply(p)
        got = self.survey().folders[self.shoot]
        self.assertEqual(got.videos_here, 0)
        self.assertEqual(got.videos_apart, 2)
        self.assertEqual(got.marks()["video"], "all")

    def test_a_folder_with_no_video_at_all_says_nothing(self):
        """A mark that reads as finished on every folder in the library is a
        mark nobody looks at."""
        quiet = os.path.join(self.lib, "2023", "Quiet")
        os.makedirs(quiet)
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(quiet, "a.JPG"))
        got = self.survey().folders[quiet]
        self.assertEqual(got.marks()["video"], "empty")

    def test_the_clips_are_not_counted_as_photographs(self):
        got = self.survey().folders[self.shoot]
        self.assertEqual(got.photos, 1)


if __name__ == "__main__":
    unittest.main()


class ToAnotherDrive(Separating):
    """The video tree on a different drive from the library - on Windows, the
    library on one share and the video tree on another. A rename cannot do that,
    so the clip is copied through this machine, and a big one takes a while."""

    def setUp(self):
        super().setUp()
        import errno
        from unittest import mock
        from core import moves
        real = os.rename

        def other_drive(src, dst, *a, **k):
            if os.path.abspath(src).startswith(self.lib):
                raise OSError(errno.EXDEV, "Invalid cross-device link")
            return real(src, dst, *a, **k)
        self.patches = [mock.patch("os.rename", other_drive),
                        mock.patch.object(moves, "CHUNK", 512)]
        for one in self.patches:
            one.start()

    def tearDown(self):
        for one in self.patches:
            one.stop()
        super().tearDown()

    def test_it_still_arrives_and_leaves_nothing_behind(self):
        t, p = self.plan()
        got = t.apply(p)
        self.assertEqual(got.failed, 0, got.lines())
        there = os.path.join(self.video, "2022", "Spain", "GX010042.MP4")
        self.assertTrue(os.path.isfile(there))
        self.assertEqual(os.path.getsize(there), 2048)
        self.assertFalse(os.path.exists(os.path.join(self.shoot, "GX010042.MP4")))

    def test_the_bar_says_how_far_through_a_big_clip_it_is(self):
        t, p = self.plan()
        said = []
        t.apply(p, progress=lambda i, n, name, status="OK": said.append(name))
        self.assertTrue(any(" of 2 KB" in s for s in said), said)

    def test_stop_part_way_through_a_clip_leaves_it_where_it_was(self):
        t, p = self.plan()
        asked = []

        def stop_after_two():
            asked.append(1)
            return len(asked) > 2

        got = t.apply(p, cancelled=stop_after_two)
        self.assertTrue(got.cancelled)
        first = p.rows[0]
        self.assertTrue(os.path.isfile(first.source))
        self.assertFalse(os.path.exists(first.target), "half a clip was left")
        self.assertEqual(got.moves, [])

    def test_a_clip_that_cannot_be_removed_is_not_left_in_two_places(self):
        """On Windows a file another program has open cannot be deleted. The
        copy goes instead, so the clip is in exactly one place."""
        from unittest import mock
        t, p = self.plan()
        real = os.remove

        def held(path, *a, **k):
            if os.path.abspath(path).startswith(self.lib):
                raise PermissionError(13, "being used by another process")
            return real(path, *a, **k)
        with mock.patch("os.remove", held):
            got = t.apply(p)
        self.assertEqual(got.failed, len(p.rows))
        for r in p.rows:
            self.assertTrue(os.path.isfile(r.source))
            self.assertFalse(os.path.exists(r.target))
