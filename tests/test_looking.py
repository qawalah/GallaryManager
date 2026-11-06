"""Thumbnails, the pictures the file manager shows, and deleting a folder."""

import io
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
from app.tasks import delfolder as D             # noqa: E402
from core import filesops as F                   # noqa: E402
from core import settings as S                   # noqa: E402
from core import thumbs as T                     # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="looking-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        os.makedirs(os.environ["PM_DATA"])
        self.lib = os.path.join(self.dir, "share", "Photos")
        self.raw = os.path.join(self.dir, "share", "Photos Raw")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        self.rshoot = os.path.join(self.raw, "2022", "Spain")
        os.makedirs(self.shoot)
        os.makedirs(self.rshoot)
        for n in ("aeb1", "aeb2"):
            shutil.copy(os.path.join(FIX, n + ".jpg"), os.path.join(self.shoot, n + ".JPG"))
        with open(os.path.join(self.rshoot, "aeb1.RW2"), "wb") as fh:
            fh.write(b"RAWHEADER" * 50 + open(os.path.join(FIX, "aeb1.jpg"), "rb").read()
                     + b"tail" * 20)
        S.save({"library": self.lib, "raw": self.raw})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)


class Thumbnails(_Tmp):
    def test_a_jpeg_gets_a_small_jpeg(self):
        from PIL import Image
        got = T.thumb(os.path.join(self.shoot, "aeb1.JPG"), "s")
        im = Image.open(io.BytesIO(got))
        self.assertEqual(im.format, "JPEG")
        self.assertLessEqual(max(im.size), T.SIZES["s"])

    def test_a_raw_uses_the_jpeg_inside_it(self):
        self.assertTrue(T.thumb(os.path.join(self.rshoot, "aeb1.RW2"), "s"))

    def test_the_second_time_is_read_from_the_cache(self):
        path = os.path.join(self.shoot, "aeb1.JPG")
        T.thumb(path, "s")
        kept = os.listdir(os.path.join(os.environ["PM_DATA"], T.FOLDER))
        self.assertEqual(len(kept), 1)
        self.assertTrue(T.thumb(path, "s"))
        self.assertEqual(len(os.listdir(os.path.join(os.environ["PM_DATA"], T.FOLDER))), 1)

    def test_synology_own_thumbnail_wins(self):
        path = os.path.join(self.shoot, "aeb1.JPG")
        ea = os.path.join(self.shoot, "@eaDir", "aeb1.JPG")
        os.makedirs(ea)
        with open(os.path.join(ea, "SYNOPHOTO_THUMB_M.jpg"), "wb") as fh:
            fh.write(b"synology")
        self.assertEqual(T.thumb(path, "s"), b"synology")

    def test_not_a_picture_is_nothing(self):
        other = os.path.join(self.shoot, "notes.txt")
        open(other, "w").write("x")
        self.assertIsNone(T.thumb(other))


class WhatTheFileManagerShows(_Tmp):
    """The Photos tab is gone; everything it did is the file manager's now.

    There used to be two ways to look at a folder - a grid with the marks under
    it, and a listing with neither - and pressing the wrong one was the thing
    a new pair of eyes did. One listing, with the marks in it.
    """

    def test_photos_and_subfolders(self):
        got = F.entries(os.path.join(self.lib, "2022"))
        self.assertEqual([f["name"] for f in got["folders"]], ["Spain"])
        self.assertEqual(got["files"], [])
        got = F.entries(self.shoot)
        self.assertEqual([f["name"] for f in got["files"]], ["aeb1.JPG", "aeb2.JPG"])
        self.assertEqual(got["parent"], os.path.join(self.lib, "2022"))

    def test_photos_below_too_reaches_every_level(self):
        got = F.entries(self.lib, deep=True)
        self.assertEqual(len(got["files"]), 2)
        self.assertTrue(got["deep"])
        # named by the way down, so two files called the same are still told apart
        self.assertEqual(sorted(f["name"] for f in got["files"]),
                         [os.path.join("2022", "Spain", "aeb1.JPG"),
                          os.path.join("2022", "Spain", "aeb2.JPG")])

    def test_synology_folders_are_not_offered(self):
        os.makedirs(os.path.join(self.shoot, "@eaDir"))
        self.assertEqual(F.entries(self.shoot)["folders"], [])

    def test_the_marks_come_with_the_listing(self):
        got = F.marks(self.shoot)
        self.assertEqual(sorted(os.path.basename(k) for k in got["marks"]),
                         ["aeb1.JPG", "aeb2.JPG"])
        one = got["marks"][os.path.join(self.shoot, "aeb1.JPG")]
        self.assertEqual(set(one), {"stars", "colour", "tags"})

    def test_marks_can_reach_below_as_well(self):
        got = F.marks(self.lib, deep=True)
        self.assertEqual(len(got["marks"]), 2)

    def test_nothing_is_registered_under_the_old_name(self):
        from app import registry
        self.assertIsNone(registry.get("browse"))


class DeletingAFolder(_Tmp):
    def bin(self):
        where = os.path.join(self.dir, "share", "#recycle")
        os.makedirs(where)
        return where

    def test_without_a_recycle_bin_nothing_happens(self):
        p = D.plan({"folder": self.shoot, "with_raw": True})
        self.assertEqual(p.rows, [])
        self.assertTrue(any("Recycle Bin" in e for e in p.errors))

    def test_moves_it_and_its_raws_into_the_bin(self):
        where = self.bin()
        p = D.plan({"folder": self.shoot, "with_raw": True})
        self.assertEqual(len(p.rows), 2)
        r = D.apply(p)
        self.assertEqual(r.done, 2)
        self.assertFalse(os.path.exists(self.shoot))
        self.assertFalse(os.path.exists(self.rshoot))
        self.assertEqual(len(os.listdir(where)), 2)

    def test_raws_stay_when_not_ticked(self):
        self.bin()
        p = D.plan({"folder": self.shoot, "with_raw": False})
        self.assertEqual(len(p.rows), 1)

    def test_a_tree_root_is_refused(self):
        self.bin()
        for folder in (self.lib, os.path.join(self.dir, "share")):
            p = D.plan({"folder": folder})
            self.assertEqual(p.rows, [], folder)
            self.assertTrue(p.errors)

    def test_refused_again_at_the_moment_of_moving(self):
        self.bin()
        p = D.plan({"folder": self.shoot, "with_raw": False})
        p.rows[0].data["from"] = self.lib
        r = D.apply(p)
        self.assertEqual(r.done, 0)
        self.assertTrue(os.path.isdir(self.lib))


class TheThumbnailAddress(_Tmp):
    def setUp(self):
        super().setUp()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), SRV.Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}/"
        threading.Thread(target=self.httpd.serve_forever,
                         kwargs={"poll_interval": 0.02}, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        SRV.ALLOWED_ROOTS.clear()
        super().tearDown()

    def fetch(self, path):
        url = self.base + "api/thumb?s=s&path=" + urllib.parse.quote(path)
        with urllib.request.urlopen(url) as f:
            return f.status, f.headers.get("Content-Type")

    def test_served_as_a_jpeg(self):
        self.assertEqual(self.fetch(os.path.join(self.shoot, "aeb1.JPG")),
                         (200, "image/jpeg"))

    def test_outside_the_allowed_folders_is_refused(self):
        SRV.ALLOWED_ROOTS.append(os.path.realpath(self.raw))
        with self.assertRaises(urllib.error.HTTPError) as got:
            self.fetch(os.path.join(self.shoot, "aeb1.JPG"))
        self.assertEqual(got.exception.code, 403)


if __name__ == "__main__":
    unittest.main()


class EditingOnePhoto(_Tmp):
    """The viewer's edits reach every copy of the shot, and delete can be undone."""

    def setUp(self):
        super().setUp()
        from core import quickedit as QE
        self.QE = QE
        self.prev = os.path.join(self.dir, "share", "Previews")
        self.pshoot = os.path.join(self.prev, "2022", "Spain")
        os.makedirs(self.pshoot)
        shutil.copy(os.path.join(FIX, "aeb1.jpg"), os.path.join(self.pshoot, "aeb1.jpg"))
        S.save({"library": self.lib, "raw": self.raw, "previews": self.prev})
        self.photo = os.path.join(self.shoot, "aeb1.JPG")

    def test_copies_are_found_by_name_in_every_tree(self):
        got = self.QE.copies(self.photo)
        self.assertEqual(got[0], self.photo)
        self.assertIn(os.path.join(self.rshoot, "aeb1.RW2"), got)
        self.assertIn(os.path.join(self.pshoot, "aeb1.jpg"), got)

    def test_what_this_photograph_is_can_be_read_in_one_go(self):
        """The viewer's "what it is" - everything that answers "which one is
        this", from the cache every other feature reads."""
        got = self.QE.about(self.photo)
        self.assertEqual(got["name"], "aeb1.JPG")
        self.assertEqual(got["folder"], self.shoot)
        self.assertTrue(got["taken"], "no capture time read")
        self.assertTrue(got["camera"])
        self.assertGreater(got["bytes"], 0)
        # and it names the negative beside it rather than only counting copies
        self.assertIn("aeb1.RW2", [c["name"] for c in got["copies"]])
        self.assertIn("raw", [c["kind"] for c in got["copies"]])

    def test_removing_the_location_takes_it_off_every_copy(self):
        from core.exifwrite import write_gps
        from core.photo import read_gps
        for one in self.QE.copies(self.photo):
            if one.lower().endswith((".jpg", ".jpeg")):
                write_gps(one, 41.38, 2.17)
        self.assertTrue(read_gps(self.photo).has_gps)
        out = self.QE.unlocate(self.photo)
        self.assertFalse(read_gps(self.photo).has_gps)
        self.assertFalse(out["located"])
        self.assertGreaterEqual(out["taken"], 1)
        for one in self.QE.copies(self.photo):
            if one.lower().endswith((".jpg", ".jpeg")):
                self.assertFalse(read_gps(one).has_gps, one)

    def test_and_says_plainly_when_there_was_none_to_remove(self):
        out = self.QE.unlocate(self.photo)
        self.assertEqual(out["taken"], 0)
        self.assertFalse(out["located"])

    def test_how_the_frame_was_exposed_is_read_for_the_overlay(self):
        """The four numbers on the back of a camera, from the same cache
        everything else reads."""
        got = self.QE.shot(self.photo)
        # what the camera is CALLED, with the code it writes kept beside it
        self.assertEqual(got["camera"], "Lumix GH4")
        self.assertEqual(got["model"], "DMC-GH4")
        self.assertEqual(got["iso"], 200)
        self.assertEqual(got["shutter"], "1/500")
        self.assertEqual(got["fnumber"], 5.6)
        self.assertEqual(got["focal"], 25.0)
        self.assertTrue(got["taken"])

    def test_the_shutter_is_said_the_way_a_camera_says_it(self):
        """0.004 is a number you convert in your head every time you read it."""
        self.assertEqual(self.QE._shutter(0.004), "1/250")
        self.assertEqual(self.QE._shutter(1 / 60), "1/60")
        self.assertEqual(self.QE._shutter(2), "2s")
        self.assertEqual(self.QE._shutter(0.5), "1/2")
        # and nothing at all when the file does not say
        for bad in (None, 0, -1, "", "fast"):
            self.assertEqual(self.QE._shutter(bad), "")

    def test_a_file_with_no_exposure_facts_says_nothing_rather_than_dashes(self):
        """A line reading "- mm  -  f/-  ISO -" says nothing except that this
        app likes dashes, so an empty fact stays empty and the page leaves it
        out of the overlay entirely."""
        bare = os.path.join(self.shoot, "nothing.JPG")
        with open(bare, "wb") as fh:                    # not a photograph at all
            fh.write(b"\xff\xd8\xff\xdb" + b"\0" * 200 + b"\xff\xd9")
        got = self.QE.shot(bare)
        self.assertEqual(got["shutter"], "")
        self.assertIsNone(got["fnumber"])
        self.assertEqual(got["iso"], 0)
        self.assertEqual(got["camera"], "")

    def test_stars_go_to_every_copy(self):
        from core.exifwrite import rating_of
        out = self.QE.set_stars(self.photo, 4)
        self.assertEqual(out["stars"], 4)
        self.assertEqual(out["copies"], 3)
        for p in self.QE.copies(self.photo):
            self.assertEqual(rating_of(p), 4, p)
        self.assertEqual(self.QE.set_stars(self.photo, 0)["stars"], 0)

    def test_colour_on_and_off(self):
        self.assertEqual(self.QE.set_colour(self.photo, "red")["colour"], "red")
        self.assertEqual(self.QE.set_colour(self.photo, "")["colour"], "")

    def test_a_tag_added_and_removed(self):
        self.assertIn("beach", self.QE.add_tag(self.photo, "beach")["tags"])
        self.assertIn("beach", self.QE.recent())
        out = self.QE.remove_tag(self.photo, "beach")
        self.assertNotIn("beach", out["tags"])
        from core.tags import tags_of
        self.assertNotIn("beach", tags_of(os.path.join(self.pshoot, "aeb1.jpg")))

    def test_delete_moves_every_copy_and_undo_puts_them_back(self):
        os.makedirs(os.path.join(self.dir, "share", "#recycle"))
        out = self.QE.delete(self.photo)
        self.assertEqual(len(out["moves"]), 3)
        self.assertFalse(os.path.exists(self.photo))
        back = self.QE.undo(out["moves"])
        self.assertEqual(back["restored"], 3)
        self.assertTrue(os.path.exists(self.photo))

    def test_delete_without_a_bin_is_refused(self):
        with self.assertRaises(self.QE.Refused):
            self.QE.delete(self.photo)
        self.assertTrue(os.path.exists(self.photo))

    def test_undo_only_takes_out_of_a_recycle_bin(self):
        other = os.path.join(self.shoot, "aeb2.JPG")
        self.assertEqual(self.QE.undo([[os.path.join(self.shoot, "x.JPG"), other]])["restored"], 0)
        self.assertTrue(os.path.exists(other))


class NoExifStillRates(_Tmp):
    def test_a_jpeg_with_no_exif_gets_a_sidecar_rating(self):
        from PIL import Image
        from core import quickedit as QE
        p = os.path.join(self.shoot, "bare.JPG")
        Image.new("RGB", (60, 40), (9, 9, 9)).save(p)
        self.assertEqual(QE.set_stars(p, 3)["stars"], 3)
