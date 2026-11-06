"""Re-mirroring the other two trees - and the different shape of each problem.

Re-mirror RAWs exists because the library is the truth and the RAW tree follows
it. The previews tree and the video tree follow it too and had no way to catch
up, so reorganising a library left both in last year's shape.

They are not the same job twice, which is why they are not one module:

**A preview is paired, and disposable.** It carries its photograph's name and
capture time, so it can be matched exactly - and making it again gives the same
result, so the honest position is that re-mirroring is the CHEAP way round
rather than the only one.

**A clip cannot be paired at all.** It has no partner in the library; it was
filed with the shoot it was taken AMONG. So it is placed by its moment, using
the same machinery Separate video uses - and the two must agree, or a clip filed
one way and re-mirrored the other lands in two different places.

The video tree is also the one that matters most: nothing else ever rewrites it.
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


class Trees(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="remirror2-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.prev = os.path.join(self.dir, "Photos Previews")
        self.video = os.path.join(self.dir, "Video")
        # The library has been REORGANISED: what was one loose folder is now
        # filed under a year and a month.
        self.now = os.path.join(self.lib, "2022", "07")
        os.makedirs(self.now)
        os.makedirs(os.path.join(self.prev, "Spain trip"))
        os.makedirs(os.path.join(self.video, "Spain trip"))
        for n in ("plain", "rated"):
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(self.now, n + ".JPG"))
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(self.prev, "Spain trip", n + ".JPG"))
        S.save({"library": self.lib, "previews": self.prev, "video": self.video})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def everything(self, root):
        return sorted(os.path.relpath(os.path.join(here, f), root)
                      for here, _d, fs in os.walk(root) for f in fs)


class Previews(Trees):
    def run_task(self, **over):
        t = R.get("remirror_previews")
        p = t.make_plan(over)
        self.assertFalse(p.blocked, p.blocked)
        return t, p

    def test_each_preview_follows_its_photograph_into_the_new_shape(self):
        t, p = self.run_task()
        self.assertEqual(len(p.rows), 2)
        t.apply(p)
        self.assertEqual(self.everything(self.prev),
                         [os.path.join("2022", "07", "plain.JPG"),
                          os.path.join("2022", "07", "rated.JPG")])

    def test_nothing_is_remade_so_the_ratings_on_them_survive(self):
        """Which is the whole reason to move rather than remake: a preview you
        have already rated is not interchangeable with a fresh one."""
        from core.exifwrite import set_rating, rating_of
        set_rating(os.path.join(self.prev, "Spain trip", "plain.JPG"), 5)
        t, p = self.run_task()
        t.apply(p)
        self.assertEqual(rating_of(os.path.join(self.prev, "2022", "07",
                                                "plain.JPG")), 5)

    def test_one_already_in_the_right_place_is_not_moved_again(self):
        t, p = self.run_task()
        t.apply(p)
        _t2, p2 = self.run_task()
        self.assertEqual(p2.rows, [])

    def test_an_orphan_is_named_and_left_where_it_is(self):
        """A preview of a photograph that no longer exists is a picture of
        nothing - and a preview is disposable, so leaving it is cheaper than
        anything else this app could do with it."""
        shutil.copy(os.path.join(FIX, "phone_doha.jpg"),
                    os.path.join(self.prev, "Spain trip", "gone.JPG"))
        t, p = self.run_task()
        self.assertEqual(len(p.rows), 2)
        self.assertTrue(any("nowhere in the library" in why
                            for _n, why in p.skipped))
        t.apply(p)
        self.assertTrue(os.path.isfile(
            os.path.join(self.prev, "Spain trip", "gone.JPG")))

    def test_unless_you_ask_for_it_to_be_put_aside(self):
        shutil.copy(os.path.join(FIX, "phone_doha.jpg"),
                    os.path.join(self.prev, "Spain trip", "gone.JPG"))
        t, p = self.run_task(orphans="aside")
        t.apply(p)
        self.assertTrue(any("_Culled" in f for f in self.everything(self.prev)),
                        self.everything(self.prev))

    def test_the_library_is_never_touched(self):
        before = self.everything(self.lib)
        t, p = self.run_task()
        t.apply(p)
        self.assertEqual(self.everything(self.lib), before)

    def test_the_two_trees_being_the_same_folder_is_refused(self):
        t = R.get("remirror_previews")
        p = t.make_plan({"previews": self.lib})
        self.assertTrue(p.blocked)

    def test_it_says_that_remaking_them_is_the_other_answer(self):
        """A tab that pretends it is the only way is a tab that will be used
        when remaking would have been simpler."""
        _t, p = self.run_task()
        self.assertTrue(any("Make previews is the other" in n for n in p.notes))


class Video(Trees):
    def clip(self, where, name="MOV001.MP4"):
        os.makedirs(where, exist_ok=True)
        out = os.path.join(where, name)
        # A clip with no readable capture time of its own: the interesting case,
        # because it can only be placed by what is around it.
        with open(out, "wb") as fh:
            fh.write(b"\x00" * 64)
        return out

    def run_task(self, **over):
        t = R.get("remirror_video")
        p = t.make_plan(over)
        return t, p

    def test_a_clip_with_no_time_at_all_is_left_alone_and_named(self):
        """A gigabyte moved somewhere plausible is a gigabyte you will not find
        again."""
        self.clip(os.path.join(self.video, "Spain trip"))
        _t, p = self.run_task()
        self.assertFalse(p.blocked, p.blocked)
        self.assertEqual(p.rows, [])
        self.assertTrue(any("not known" in why for _n, why in p.skipped))

    def timed_clip(self, where, when="2022-07-14T18:05:00", name="MOV001.MP4"):
        """A clip with a real capture time, so it can actually be placed."""
        from tests.test_video_time import make_clip
        os.makedirs(where, exist_ok=True)
        out = os.path.join(where, name)
        if not make_clip(out, when):
            self.skipTest("no ffmpeg here to make a clip with a clock in it")
        return out

    def test_a_clip_lands_where_the_photographs_of_its_moment_now_live(self):
        """The whole feature. The library was reorganised from "Spain trip" to
        2022/07, and the clip was shot among those photographs - so that is
        where it belongs now, wherever they have been moved to."""
        self.timed_clip(os.path.join(self.video, "Spain trip"))
        t, p = self.run_task()
        self.assertFalse(p.blocked, p.blocked)
        self.assertEqual(len(p.rows), 1, [r.detail for r in p.rows])
        self.assertEqual(p.rows[0].target,
                         os.path.join(self.video, "2022", "07", "MOV001.MP4"))
        t.apply(p)
        self.assertIn(os.path.join("2022", "07", "MOV001.MP4"),
                      self.everything(self.video))

    def test_and_says_which_shoot_answered(self):
        """A clip placed by its shoot and one placed by its own date are worth
        very different amounts of trust."""
        self.timed_clip(os.path.join(self.video, "Spain trip"))
        _t, p = self.run_task()
        self.assertIn("photos of", p.rows[0].detail)

    def test_one_already_in_the_right_place_is_not_moved_again(self):
        self.timed_clip(os.path.join(self.video, "2022", "07"))
        _t, p = self.run_task()
        self.assertEqual(p.rows, [])
        self.assertEqual(dict(p.stats)["Already in the right place"], "1")

    def test_it_reads_the_librarys_shoots_rather_than_pairing(self):
        """A clip has no partner in the library, so the only honest question is
        which folder holds the photos of its moment."""
        _t, p = self.run_task()
        stats = dict(p.stats)
        self.assertIn("Shoots found in the library", stats)
        self.assertNotEqual(stats["Shoots found in the library"], "0")

    def test_the_video_tree_inside_the_library_is_refused(self):
        _t, p = self.run_task(video=os.path.join(self.lib, "Video"))
        self.assertTrue(p.blocked)

    def test_it_uses_the_same_nearness_as_separate_video(self):
        """Two features that answer "which shoot is this clip part of"
        differently are two features that disagree about where a clip lives."""
        from core import shoots
        opt = [o for o in R.get("remirror_video").options
               if o.name == "near_hours"][0]
        self.assertEqual(opt.default, shoots.NEAR_HOURS)

    def test_the_library_is_never_touched(self):
        before = self.everything(self.lib)
        t, p = self.run_task()
        if not p.blocked:
            t.apply(p)
        self.assertEqual(self.everything(self.lib), before)


    def test_clips_still_in_the_library_are_pointed_at_separate_video(self):
        """The video tree is empty and the clips are still among the
        photographs. "Nothing to do" alone read as a tool that did nothing when
        pressed; the plan says which feature moves them out."""
        self.clip(self.now, "IMG_0001.MP4")
        _t, p = self.run_task()
        self.assertFalse(p.blocked, p.blocked)
        self.assertEqual(p.rows, [])
        self.assertIn("Separate video", p.notes[0])
        self.assertIn("1", p.notes[0])

    def test_with_clips_in_the_video_tree_it_does_not_say_so(self):
        self.clip(self.now, "IMG_0001.MP4")
        self.clip(os.path.join(self.video, "Spain trip"))
        _t, p = self.run_task()
        self.assertFalse(any("Separate video is what" in n for n in p.notes))

    def test_it_says_it_is_listing_before_there_is_anything_to_count(self):
        said = []
        R.get("remirror_video").make_plan(
            {}, progress=lambda i, n, name, status="OK": said.append(name))
        self.assertTrue(said[0].startswith("listing everything in"), said[:2])

    def dated_clip(self, where, name="MOV009.MP4"):
        """A clip whose movie header says 2019-05-06 07:08:00, from a day the
        library has no photos of, so only its own date can place it."""
        import datetime as dt
        import struct

        def atom(kind, body):
            return struct.pack(">I", len(body) + 8) + kind + body
        secs = int((dt.datetime(2019, 5, 6, 7, 8) - dt.datetime(1904, 1, 1))
                   .total_seconds())
        os.makedirs(where, exist_ok=True)
        out = os.path.join(where, name)
        with open(out, "wb") as fh:
            fh.write(atom(b"ftyp", b"isom" + b"\x00" * 8) + atom(
                b"moov", atom(b"mvhd", b"\x00" * 4 + struct.pack(">I", secs)
                              + b"\x00" * 90)))
        return out

    def test_year_month_day_is_a_day_folder(self):
        """It was offered and silently filed by year and month."""
        from app.tasks.videos import date_folder
        import datetime as dt
        self.assertEqual(date_folder(dt.datetime(2024, 5, 6, 7, 8),
                                     "year_month_day"),
                         os.path.join("2024", "05", "06"))
        self.dated_clip(os.path.join(self.video, "Loose"))
        _t, p = self.run_task(shape="year_month_day")
        self.assertFalse(p.blocked, p.blocked)
        self.assertEqual([r.target for r in p.rows],
                         [os.path.join(self.video, "2019", "05", "06",
                                       "MOV009.MP4")])

    def test_tidy_off_leaves_the_emptied_folder(self):
        self.dated_clip(os.path.join(self.video, "Loose"))
        t, p = self.run_task(tidy=False)
        self.assertEqual(len(p.rows), 1, [r.detail for r in p.rows])
        t.apply(p)
        self.assertTrue(os.path.isdir(os.path.join(self.video, "Loose")))

    def test_and_on_it_is_tidied(self):
        self.dated_clip(os.path.join(self.video, "Loose"))
        t, p = self.run_task(tidy=True)
        t.apply(p)
        self.assertFalse(os.path.isdir(os.path.join(self.video, "Loose")))

    def test_the_shoot_window_goes_as_far_as_separate_videos(self):
        mine = [o for o in R.get("remirror_video").options
                if o.name == "near_hours"][0]
        theirs = [o for o in R.get("videos").options if o.name == "near_hours"][0]
        self.assertEqual(mine.maximum, theirs.maximum)


class WhereTheySit(Trees):
    def test_each_is_a_tab_under_the_feature_it_belongs_to(self):
        self.assertEqual(R.get("remirror_previews").parent, "previews")
        self.assertEqual(R.get("remirror_video").parent, "videos")
        self.assertEqual(R.get("remirror").parent, "unpair")

    def test_and_none_of_them_shares_an_icon_with_its_neighbours(self):
        for name in ("previews", "videos", "unpair"):
            family = [R.get(name)] + R.children(name)
            icons = [t.icon for t in family]
            self.assertEqual(len(set(icons)), len(icons), name)


if __name__ == "__main__":
    unittest.main()
