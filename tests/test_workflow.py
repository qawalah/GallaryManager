"""The three tasks that move and rate files, and the chain they form.

Separate, unpair leaves a RAW tree. Sync, ratings puts the stars on it. Cull,
and the low-rated ones go aside together. Reorganise, and re-mirror catches up.
Each step is tested on its own, and then the whole chain is run in order,
because most of the ways this can go wrong are things that only show up at a
handover: a sidecar left behind, a rating read from the wrong side, a bracket
split in half.
"""

import glob
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R                       # noqa: E402
import app.tasks                                    # noqa: E402,F401
from core.exifwrite import (rating_of, read_sidecar, set_rating,   # noqa: E402
                            write_gps_sidecar, write_rating)
from core import labels as L                        # noqa: E402
from core import tags                               # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")

# aeb1..3 are one bracket (-1/0/+1, flagged); burst1..3 share one bias.
BRACKET = ["aeb1", "aeb2", "aeb3"]
LOOSE = ["burst1", "burst2", "burst3"]


class Library(unittest.TestCase):
    """A mixed library: JPEGs and RAWs side by side, as the card leaves them."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="workflow-")
        # Settings are read by every task now, so a test must not see - or write -
        # the settings of whoever is running it. PM_DATA moves the whole store into
        # this test's own directory.
        self._was_data = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        for n in BRACKET + LOOSE:
            shutil.copy(os.path.join(FIX, f"{n}.jpg"), os.path.join(self.shoot, f"{n}.JPG"))
            shutil.copy(os.path.join(FIX, f"{n}.jpg"), os.path.join(self.shoot, f"{n}.RW2"))
        # The library, and ONLY the library. Without one saved there is nothing
        # to measure a folder's position from, and every task that mirrors into
        # another tree now refuses rather than landing it all flat in the top of
        # that tree. Saving the RAW tree as well would be worse than useless
        # here: mirroring is on by default, so Setup's value would replace the
        # one each test passes in, and the tests about a badly-placed RAW tree
        # would silently stop testing anything.
        from core import settings as _settings
        _settings.save({"library": self.lib})

    def tearDown(self):
        if self._was_data is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was_data
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_task(self, name, **raw):
        t = R.get(name)
        p = t.make_plan(raw)
        return t, p

    def apply(self, name, **raw):
        t, p = self.run_task(name, **raw)
        self.assertFalse(p.blocked, p.blocked)
        return p, t.apply(p)

    def tree(self, root):
        out = []
        for here, _dirs, names in os.walk(root):
            for n in names:
                out.append(os.path.relpath(os.path.join(here, n), root).replace("\\", "/"))
        return sorted(out)

    def rate(self, name, stars):
        write_rating(os.path.join(self.shoot, f"{name}.JPG"), stars)


# ------------------------------------------------------------------ separating

class Unpairing(Library):
    def test_every_raw_with_a_jpeg_beside_it_moves_and_keeps_its_position(self):
        p, r = self.apply("unpair", folder=self.lib, raw=self.raw)
        self.assertEqual(r.failed, 0)
        self.assertEqual(self.tree(self.raw),
                         sorted(f"2022/Spain/{n}.RW2" for n in BRACKET + LOOSE))
        self.assertEqual(self.tree(self.lib),
                         sorted(f"2022/Spain/{n}.JPG" for n in BRACKET + LOOSE))

    def test_a_lone_raw_stays_where_it_is(self):
        os.remove(os.path.join(self.shoot, "burst1.JPG"))
        _, p = self.run_task("unpair", folder=self.lib, raw=self.raw)
        names = [r.name for r in p.rows]
        self.assertNotIn("burst1.RW2", names)
        self.assertTrue(any("burst1" in n for n, _why in p.skipped))

    def test_unless_you_ask_for_it(self):
        os.remove(os.path.join(self.shoot, "burst1.JPG"))
        _, p = self.run_task("unpair", folder=self.lib, raw=self.raw, unpaired="on")
        self.assertIn("burst1.RW2", [r.name for r in p.rows])

    def test_sidecars_travel_with_the_raw(self):
        write_gps_sidecar(os.path.join(self.shoot, "aeb1.RW2"), 41.38, 2.17)
        self.apply("unpair", folder=self.lib, raw=self.raw)
        self.assertIn("2022/Spain/aeb1.xmp", self.tree(self.raw))

    def test_it_refuses_a_raw_tree_inside_the_library(self):
        _, p = self.run_task("unpair", folder=self.lib,
                             raw=os.path.join(self.lib, "Raw"))
        self.assertTrue(p.blocked)

    def test_one_shoot_lands_where_a_whole_library_run_would_have_put_it(self):
        """Scanning at two levels must build ONE tree, not two that collide."""
        self.apply("unpair", folder=self.shoot, raw=self.raw, library=self.lib)
        self.assertEqual(self.tree(self.raw),
                         sorted(f"2022/Spain/{n}.RW2" for n in BRACKET + LOOSE))

    def test_copying_leaves_the_library_untouched(self):
        before = self.tree(self.lib)
        self.apply("unpair", folder=self.lib, raw=self.raw, copy="on")
        self.assertEqual(self.tree(self.lib), before)
        self.assertEqual(len(self.tree(self.raw)), 6)

    def test_planning_alone_moves_nothing(self):
        before = self.tree(self.lib)
        self.run_task("unpair", folder=self.lib, raw=self.raw)
        self.assertEqual(self.tree(self.lib), before)
        self.assertFalse(os.path.isdir(self.raw))


# --------------------------------------------------------------------- ratings

class SyncingRatings(Library):
    def setUp(self):
        super().setUp()
        self.apply("unpair", folder=self.lib, raw=self.raw)

    def test_a_rating_reaches_the_raw_as_a_sidecar(self):
        self.rate("burst1", 4)
        _, r = self.apply("ratings", folder=self.lib, raw=self.raw, mirror=False, library="")
        self.assertEqual(r.failed, 0)
        self.assertEqual(rating_of(os.path.join(self.raw, "2022", "Spain", "burst1.RW2")), 4)

    def test_it_finds_the_raw_after_the_library_was_reorganised(self):
        """The point of matching on identity rather than on position."""
        self.rate("burst1", 4)
        os.rename(os.path.join(self.lib, "2022", "Spain"),
                  os.path.join(self.lib, "2022", "Spain in July"))
        self.apply("ratings",
                   folder=os.path.join(self.lib, "2022", "Spain in July"), raw=self.raw)
        self.assertEqual(rating_of(os.path.join(self.raw, "2022", "Spain", "burst1.RW2")), 4)

    def test_an_unrated_photo_never_clears_a_rating_on_the_other_side(self):
        target = os.path.join(self.raw, "2022", "Spain", "burst2.RW2")
        set_rating(target, 5)
        self.apply("ratings", folder=self.lib, raw=self.raw, mirror=False, library="")
        self.assertEqual(rating_of(target), 5)

    def test_the_whole_bracket_takes_the_rating_of_its_metered_frame(self):
        self.rate("aeb2", 3)                       # only the middle frame is rated
        self.apply("ratings", folder=self.lib, raw=self.raw, mirror=False, library="")
        for n in BRACKET:
            self.assertEqual(rating_of(os.path.join(self.raw, "2022", "Spain", f"{n}.RW2")), 3,
                             f"{n} did not take its bracket's rating")

    def test_a_burst_does_not_share_a_rating(self):
        """The same code must NOT spread a rating across frames that only look alike.

        burst1 is deliberately the one rated. If the burst were ever grouped, it is
        the frame that would stand for the set - so its rating would reach the other
        two, and this would fail. Rating a middle frame instead would let the test
        pass for the wrong reason.
        """
        self.rate("burst1", 3)
        self.apply("ratings", folder=self.lib, raw=self.raw, mirror=False, library="")
        self.assertIsNone(rating_of(os.path.join(self.raw, "2022", "Spain", "burst2.RW2")))
        self.assertIsNone(rating_of(os.path.join(self.raw, "2022", "Spain", "burst3.RW2")))

    def test_with_brackets_off_only_the_frame_you_rated_travels(self):
        self.rate("aeb2", 3)
        self.apply("ratings", folder=self.lib, raw=self.raw, brackets="", mirror=False, library="")
        self.assertEqual(rating_of(os.path.join(self.raw, "2022", "Spain", "aeb2.RW2")), 3)
        self.assertIsNone(rating_of(os.path.join(self.raw, "2022", "Spain", "aeb1.RW2")))

    def test_writing_a_rating_does_not_disturb_a_location_already_in_the_sidecar(self):
        target = os.path.join(self.raw, "2022", "Spain", "burst1.RW2")
        write_gps_sidecar(target, 41.38, 2.17)
        self.rate("burst1", 2)
        self.apply("ratings", folder=self.lib, raw=self.raw, mirror=False, library="")
        side = read_sidecar(target)
        self.assertEqual(side.get("xmp:Rating"), "2")
        self.assertIn("exif:GPSLatitude", side)

    def test_it_refuses_when_no_destination_was_given(self):
        _, p = self.run_task("ratings", folder=self.lib, mirror=False, library="")
        self.assertTrue(p.blocked)

    def test_planning_alone_writes_nothing(self):
        self.rate("burst1", 4)
        self.run_task("ratings", folder=self.lib, raw=self.raw, mirror=False, library="")
        self.assertEqual(glob.glob(os.path.join(self.raw, "**", "*.xmp"), recursive=True), [])


# --------------------------------------------------------------------- colours

class SyncingColours(Library):
    """The colour travels with the stars, and for a while it did not.

    Both marks are made in the same place, in the same minute, by the same
    person going through a folder - and only the stars were being carried. So
    the preview said "edit this one" and the negative you actually open said
    nothing at all: the same silence as an unrated RAW, and the same evening
    lost putting it back by hand.

    The colour is carried more carefully than a star, and the tests below are
    mostly about that care. A rating overwritten by mistake can be given again
    by looking at the photograph. A colour overwritten by mistake is a decision
    that is simply gone.
    """

    def setUp(self):
        super().setUp()
        self.apply("unpair", folder=self.lib, raw=self.raw)

    def colour(self, name, colour="green", keywords=None):
        where = os.path.join(self.shoot, f"{name}.JPG")
        d = L.by_colour(colour)
        L.set_label(where, colour,
                    keywords if keywords is not None else (d.all_keywords() if d else []))
        return where

    def negative(self, name):
        return os.path.join(self.raw, "2022", "Spain", f"{name}.RW2")

    def test_a_colour_reaches_the_raw_the_way_a_rating_does(self):
        self.colour("burst1")
        _, r = self.apply("ratings", folder=self.lib, raw=self.raw,
                          mirror=False, library="")
        self.assertEqual(r.failed, 0)
        self.assertEqual(L.colour_of(self.negative("burst1")), "green")

    def test_and_the_words_that_colour_means_go_with_it(self):
        """The colour word is what Lightroom reads; the keywords are the half
        Synology Photos can search. Carrying one without the other would put the
        swatch on the negative and leave it unfindable."""
        self.colour("burst1")
        self.apply("ratings", folder=self.lib, raw=self.raw,
                   mirror=False, library="")
        want = {w.lower() for w in L.by_colour("green").all_keywords()}
        self.assertTrue(want <= {t.lower() for t in tags.tags_of(self.negative("burst1"))})

    def test_a_photo_with_a_colour_and_no_stars_is_still_carried(self):
        """The regression this whole batch is about. An unrated photo used to be
        dropped before its colour was ever looked at, so a folder marked but not
        rated - which is the ordinary way a shoot is marked - synced nothing."""
        self.colour("burst2")
        self.apply("ratings", folder=self.lib, raw=self.raw,
                   mirror=False, library="")
        self.assertEqual(L.colour_of(self.negative("burst2")), "green")

    def test_both_halves_travel_in_one_pass(self):
        self.rate("burst1", 4)
        self.colour("burst1")
        self.apply("ratings", folder=self.lib, raw=self.raw,
                   mirror=False, library="")
        self.assertEqual(rating_of(self.negative("burst1")), 4)
        self.assertEqual(L.colour_of(self.negative("burst1")), "green")

    def test_a_different_colour_on_the_other_side_is_left_alone(self):
        """Not overwritten, listed. The old colour is not recoverable from
        anything once it is gone."""
        L.set_label(self.negative("burst1"), "red", [])
        self.colour("burst1")
        _t, p = self.run_task("ratings", folder=self.lib, raw=self.raw,
                              mirror=False, library="")
        self.assertEqual([r for r in p.rows if r.data.get("colour")], [])
        self.assertTrue(any("already Red" in why for _n, why in p.skipped))
        self.assertEqual(L.colour_of(self.negative("burst1")), "red")

    def test_unless_you_ask_for_it(self):
        L.set_label(self.negative("burst1"), "red", [])
        self.colour("burst1")
        self.apply("ratings", folder=self.lib, raw=self.raw, mirror=False,
                   library="", replace=True)
        self.assertEqual(L.colour_of(self.negative("burst1")), "green")

    def test_somebody_elses_label_is_neither_carried_nor_overwritten(self):
        """`xmp:Label` is a free string and another program may be using it for
        something this app has never heard of."""
        from core import sidecar as sc
        sc.write(self.negative("burst1"), **{"xmp:Label": "Client approved 2019"})
        sc.write(os.path.join(self.shoot, "burst2.JPG"),
                 **{"xmp:Label": "Client approved 2019"})
        self.colour("burst1")
        self.apply("ratings", folder=self.lib, raw=self.raw, mirror=False,
                   library="", replace=True)
        self.assertEqual(L.written_label(self.negative("burst1")),
                         "Client approved 2019")
        self.assertEqual(L.written_label(self.negative("burst2")), "")

    def test_either_half_can_be_turned_off(self):
        self.rate("burst1", 4)
        self.colour("burst1")
        self.apply("ratings", folder=self.lib, raw=self.raw, mirror=False,
                   library="", colours="")
        self.assertEqual(rating_of(self.negative("burst1")), 4)
        self.assertEqual(L.colour_of(self.negative("burst1")), "")

        self.rate("burst3", 2)
        self.colour("burst3")
        self.apply("ratings", folder=self.lib, raw=self.raw, mirror=False,
                   library="", stars="")
        self.assertIsNone(rating_of(self.negative("burst3")))
        self.assertEqual(L.colour_of(self.negative("burst3")), "green")

    def test_the_whole_bracket_takes_the_colour_of_its_metered_frame(self):
        """The same rule as a rating: there is one preview per set, so a colour
        given to the frame that stands for the set has to reach the rest or the
        set is split the next time anything acts on the colour."""
        self.colour("aeb2")
        self.apply("ratings", folder=self.lib, raw=self.raw,
                   mirror=False, library="")
        for n in BRACKET:
            self.assertEqual(L.colour_of(self.negative(n)), "green", n)

    def test_a_colour_already_the_same_is_not_written_again(self):
        self.colour("burst1")
        self.apply("ratings", folder=self.lib, raw=self.raw,
                   mirror=False, library="")
        _t, p = self.run_task("ratings", folder=self.lib, raw=self.raw,
                              mirror=False, library="")
        self.assertEqual(p.rows, [])

    def test_planning_alone_writes_nothing(self):
        self.colour("burst1")
        self.run_task("ratings", folder=self.lib, raw=self.raw,
                      mirror=False, library="")
        self.assertEqual(L.colour_of(self.negative("burst1")), "")


# ----------------------------------------------------------------------- cull

class Culling(Library):
    def setUp(self):
        super().setUp()
        self.apply("unpair", folder=self.lib, raw=self.raw)

    def test_an_unrated_photo_is_never_culled(self):
        _, p = self.run_task("cull", folder=self.lib, raw=self.raw, raw_at_or_below=5)
        self.assertEqual(p.rows, [])
        self.assertIn(("Unrated - never culled", "6"), p.stats)

    def test_a_low_rated_shot_takes_its_raw_with_it(self):
        self.rate("burst1", 1)
        self.apply("cull", folder=self.lib, raw=self.raw,
                   raw_at_or_below=2, jpeg_at_or_below=2)
        self.assertIn("_Culled/2022/Spain/burst1.JPG", self.tree(self.lib))
        self.assertIn("_Culled/2022/Spain/burst1.RW2", self.tree(self.raw))

    def test_the_usual_setting_keeps_the_jpeg_and_puts_only_the_raw_aside(self):
        self.rate("burst1", 1)
        self.apply("cull", folder=self.lib, raw=self.raw, raw_at_or_below=2)
        self.assertIn("2022/Spain/burst1.JPG", self.tree(self.lib))
        self.assertIn("_Culled/2022/Spain/burst1.RW2", self.tree(self.raw))

    def test_a_high_rating_is_left_alone(self):
        self.rate("burst1", 5)
        _, p = self.run_task("cull", folder=self.lib, raw=self.raw, raw_at_or_below=2)
        self.assertEqual(p.rows, [])

    def test_a_bracket_is_kept_or_culled_as_one_set(self):
        self.rate("aeb2", 1)
        self.apply("cull", folder=self.lib, raw=self.raw, raw_at_or_below=2)
        for n in BRACKET:
            self.assertIn(f"_Culled/2022/Spain/{n}.RW2", self.tree(self.raw),
                          f"{n} was left behind by its own set")

    def test_a_burst_is_not_culled_as_a_set(self):
        """burst1 again, for the same reason: it is the frame a wrongly-grouped
        burst would elect to speak for the others."""
        self.rate("burst1", 1)
        self.apply("cull", folder=self.lib, raw=self.raw, raw_at_or_below=2)
        self.assertIn("_Culled/2022/Spain/burst1.RW2", self.tree(self.raw))
        self.assertIn("2022/Spain/burst2.RW2", self.tree(self.raw))
        self.assertIn("2022/Spain/burst3.RW2", self.tree(self.raw))

    def test_the_sidecar_goes_with_the_raw(self):
        self.rate("burst1", 1)
        set_rating(os.path.join(self.raw, "2022", "Spain", "burst1.RW2"), 1)
        self.apply("cull", folder=self.lib, raw=self.raw, raw_at_or_below=2)
        self.assertIn("_Culled/2022/Spain/burst1.xmp", self.tree(self.raw))

    def test_nothing_is_ever_deleted(self):
        self.rate("burst1", 1)
        before = len(self.tree(self.lib)) + len(self.tree(self.raw))
        self.apply("cull", folder=self.lib, raw=self.raw,
                   raw_at_or_below=2, jpeg_at_or_below=2)
        self.assertEqual(len(self.tree(self.lib)) + len(self.tree(self.raw)), before)

    def test_culled_files_are_not_examined_again_on_the_next_run(self):
        self.rate("burst1", 1)
        self.apply("cull", folder=self.lib, raw=self.raw, jpeg_at_or_below=2)
        _, p = self.run_task("cull", folder=self.lib, raw=self.raw, jpeg_at_or_below=2)
        self.assertEqual(p.rows, [])

    def test_both_thresholds_off_is_refused_rather_than_doing_nothing_quietly(self):
        _, p = self.run_task("cull", folder=self.lib, raw=self.raw,
                             raw_at_or_below=-1, jpeg_at_or_below=-1)
        self.assertTrue(p.blocked)

    def test_planning_alone_moves_nothing(self):
        self.rate("burst1", 1)
        before = self.tree(self.lib)
        self.run_task("cull", folder=self.lib, raw=self.raw, jpeg_at_or_below=2)
        self.assertEqual(self.tree(self.lib), before)



# -------------------------------------------------------------------- previews

class MakingPreviews(Library):
    def setUp(self):
        super().setUp()
        self.prev = os.path.join(self.dir, "Photos Previews")
        try:
            from PIL import Image, ImageOps       # noqa: F401
        except Exception:                          # noqa: BLE001
            self.skipTest("Pillow is not installed here")

    def test_one_preview_per_bracket_and_one_for_every_loose_frame(self):
        _, r = self.apply("previews", folder=self.lib, previews=self.prev)
        self.assertEqual(r.failed, 0)
        made = self.tree(self.prev)
        self.assertIn("2022/Spain/aeb2.jpg", made)          # the metered frame
        self.assertNotIn("2022/Spain/aeb1.jpg", made)
        self.assertNotIn("2022/Spain/aeb3.jpg", made)
        for n in LOOSE:
            self.assertIn(f"2022/Spain/{n}.jpg", made)

    def test_with_brackets_off_every_frame_gets_one(self):
        self.apply("previews", folder=self.lib, previews=self.prev, brackets="")
        self.assertEqual(len(self.tree(self.prev)), 6)

    def test_a_big_photo_comes_out_at_the_size_you_asked_for(self):
        from PIL import Image
        big = os.path.join(self.shoot, "big.JPG")
        Image.new("RGB", (1600, 1200), (30, 90, 160)).save(big, "JPEG")
        self.apply("previews", folder=self.lib, previews=self.prev,
                   profile="custom", long_edge=400)
        with Image.open(os.path.join(self.prev, "2022", "Spain", "big.jpg")) as im:
            self.assertEqual(max(im.size), 400)
            self.assertEqual(im.size, (400, 300))          # the shape is kept

    def test_a_photo_smaller_than_the_limit_is_never_blown_up(self):
        from PIL import Image
        self.apply("previews", folder=self.lib, previews=self.prev,
                   profile="custom", long_edge=400)
        with Image.open(os.path.join(self.shoot, "burst1.JPG")) as src:
            was = src.size
        with Image.open(os.path.join(self.prev, "2022", "Spain", "burst1.jpg")) as im:
            self.assertEqual(im.size, was)

    def test_a_bracket_preview_carries_the_word_that_says_so(self):
        """One preview stands for three frames, and on the tablet there is
        nothing to say which. The keyword travels with it - along with whatever
        the original was already tagged."""
        from core import tags, tagwrite
        tagwrite.add(os.path.join(self.shoot, "aeb2.JPG"), ["Italy"])
        _, r = self.apply("previews", folder=self.lib, previews=self.prev)
        self.assertEqual(r.failed, 0)
        made = os.path.join(self.prev, "2022", "Spain", "aeb2.jpg")
        self.assertEqual(tags.tags_of(made), ["Italy", "bracket"])
        # and a loose frame's preview is not called a bracket
        loose = os.path.join(self.prev, "2022", "Spain", f"{LOOSE[0]}.jpg")
        self.assertEqual(tags.tags_of(loose), [])

    def test_the_keyword_can_be_turned_off(self):
        from core import tags
        _, r = self.apply("previews", folder=self.lib, previews=self.prev,
                          carry_tags=False)
        self.assertEqual(r.failed, 0)
        made = os.path.join(self.prev, "2022", "Spain", "aeb2.jpg")
        self.assertEqual(tags.tags_of(made), [])

    def test_a_preview_keeps_the_capture_time_and_camera(self):
        """Without these it cannot find its way home, which is its only job."""
        from core.photo import read_capture
        self.apply("previews", folder=self.lib, previews=self.prev)
        original = read_capture(os.path.join(self.shoot, "burst1.JPG"))
        preview = read_capture(os.path.join(self.prev, "2022", "Spain", "burst1.jpg"))
        self.assertTrue(preview.ok)
        self.assertEqual(preview.taken, original.taken)
        self.assertEqual(preview.model, original.model)

    def test_running_it_twice_makes_nothing_the_second_time(self):
        self.apply("previews", folder=self.lib, previews=self.prev)
        _, p = self.run_task("previews", folder=self.lib, previews=self.prev)
        self.assertEqual(p.rows, [])

    def test_unless_you_ask_for_a_rebuild(self):
        self.apply("previews", folder=self.lib, previews=self.prev)
        _, p = self.run_task("previews", folder=self.lib, previews=self.prev, rebuild="on")
        self.assertEqual(len(p.rows), 4)

    def test_a_preview_older_than_its_photo_is_remade(self):
        self.apply("previews", folder=self.lib, previews=self.prev)
        made = os.path.join(self.prev, "2022", "Spain", "burst1.jpg")
        os.utime(made, (0, 0))
        _, p = self.run_task("previews", folder=self.lib, previews=self.prev)
        self.assertIn("burst1.JPG", [r.name for r in p.rows])

    def test_it_refuses_a_previews_tree_inside_the_library(self):
        _, p = self.run_task("previews", folder=self.lib,
                             previews=os.path.join(self.lib, "Previews"))
        self.assertTrue(p.blocked)

    def test_planning_alone_makes_nothing(self):
        self.run_task("previews", folder=self.lib, previews=self.prev)
        self.assertFalse(os.path.isdir(self.prev))


class RatingOnATablet(Library):
    """The real loop: previews out, stars made on them, stars carried home."""

    def setUp(self):
        super().setUp()
        self.prev = os.path.join(self.dir, "Photos Previews")
        try:
            from PIL import Image                 # noqa: F401
        except Exception:                          # noqa: BLE001
            self.skipTest("Pillow is not installed here")
        self.apply("unpair", folder=self.lib, raw=self.raw)
        self.apply("previews", folder=self.lib, previews=self.prev)

    def rate_preview(self, name, stars):
        write_rating(os.path.join(self.prev, "2022", "Spain", f"{name}.jpg"), stars)

    def test_a_star_given_to_a_preview_reaches_the_original_and_its_raw(self):
        self.rate_preview("burst1", 4)
        _, r = self.apply("ratings", folder=self.prev, library=self.lib, raw=self.raw)
        self.assertEqual(r.failed, 0)
        self.assertEqual(rating_of(os.path.join(self.shoot, "burst1.JPG")), 4)
        self.assertEqual(rating_of(os.path.join(self.raw, "2022", "Spain", "burst1.RW2")), 4)

    def test_one_preview_rates_the_whole_bracket_it_stands_for(self):
        """The set is in the LIBRARY, not in the previews - there is only ever one
        preview of it. Looking for the set in the rated folder finds nothing and
        leaves the other two exposures unrated for good."""
        self.rate_preview("aeb2", 5)
        self.apply("ratings", folder=self.prev, library=self.lib, raw=self.raw)
        for n in BRACKET:
            self.assertEqual(rating_of(os.path.join(self.shoot, f"{n}.JPG")), 5,
                             f"{n} was left unrated in the library")
            self.assertEqual(rating_of(os.path.join(self.raw, "2022", "Spain", f"{n}.RW2")), 5,
                             f"{n}'s RAW was left unrated")

    def test_and_then_the_whole_set_survives_a_cull(self):
        self.rate_preview("aeb2", 5)
        self.rate_preview("burst1", 1)
        self.apply("ratings", folder=self.prev, library=self.lib, raw=self.raw)
        self.apply("cull", folder=self.lib, raw=self.raw, raw_at_or_below=2)
        for n in BRACKET:
            self.assertIn(f"2022/Spain/{n}.RW2", self.tree(self.raw))
        self.assertIn("_Culled/2022/Spain/burst1.RW2", self.tree(self.raw))

    def test_it_still_works_after_the_library_was_reorganised(self):
        self.rate_preview("burst1", 4)
        os.makedirs(os.path.join(self.lib, "Trips"))
        shutil.move(os.path.join(self.lib, "2022", "Spain"),
                    os.path.join(self.lib, "Trips", "Barcelona"))
        self.apply("ratings", folder=self.prev, library=self.lib, raw=self.raw)
        self.assertEqual(
            rating_of(os.path.join(self.lib, "Trips", "Barcelona", "burst1.JPG")), 4)


# ------------------------------------------------------------------ altogether

class TheWholeChain(Library):
    def test_separate_rate_cull_reorganise_remirror(self):
        # 1. the RAWs move out into their own tree
        self.apply("unpair", folder=self.lib, raw=self.raw)

        # 2. one frame of the bracket and one loose frame are rated
        self.rate("aeb2", 4)
        self.rate("burst1", 1)
        self.apply("ratings", folder=self.lib, raw=self.raw, mirror=False, library="")
        for n in BRACKET:
            self.assertEqual(rating_of(os.path.join(self.raw, "2022", "Spain", f"{n}.RW2")), 4)

        # 3. the one-star shot goes aside, and the four-star bracket does not
        self.apply("cull", folder=self.lib, raw=self.raw, raw_at_or_below=2)
        self.assertIn("_Culled/2022/Spain/burst1.RW2", self.tree(self.raw))
        self.assertIn("2022/Spain/aeb2.RW2", self.tree(self.raw))

        # 4. the library is reorganised entirely
        os.makedirs(os.path.join(self.lib, "Trips"))
        shutil.move(os.path.join(self.lib, "2022", "Spain"),
                    os.path.join(self.lib, "Trips", "Barcelona 2022"))

        # 5. and the RAW tree catches up, ratings intact
        _, r = self.apply("remirror", library=self.lib, raw=self.raw)
        self.assertEqual(r.failed, 0)
        for n in BRACKET:
            moved = os.path.join(self.raw, "Trips", "Barcelona 2022", f"{n}.RW2")
            self.assertTrue(os.path.isfile(moved), f"{n} did not follow its JPEG")
            self.assertEqual(rating_of(moved), 4,
                             f"{n} lost its rating when its sidecar was left behind")
        # what was put aside stays put aside - it has no JPEG to follow
        self.assertIn("_Culled/2022/Spain/burst1.RW2", self.tree(self.raw))


if __name__ == "__main__":
    unittest.main()
