"""When a clip was shot, and which shoot it belongs to.

Two things that are easy to get subtly wrong and impossible to notice:

**The timezone.** `mvhd` is UTC by the specification and local in a great many
cameras. A photograph's capture time is local wall-clock with no zone at all.
Three hours of difference files an evening clip under the previous day - and it
looks exactly like a clip that was shot the previous day.

**Where moov is.** It sits at the END of anything not written for streaming, so
the obvious implementation - read the first megabyte, look for atoms - finds
nothing in most of the clips a camera actually writes, and reports them all as
undated.

The MP4 and MOV files here are made by ffmpeg when it is installed, and checked
against ffprobe, which is this module's Pillow: an independent reader that
agrees or does not. Without ffmpeg the container tests skip themselves and the
parsing tests still run against files built here by hand.
"""

import datetime as dt
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import shoots, video                    # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def has(tool: str) -> bool:
    return bool(shutil.which(tool))


def make_clip(path: str, when: str, container: str = "mp4", extra=()) -> bool:
    """A real clip, made by ffmpeg. False when there is no ffmpeg here."""
    if not has("ffmpeg"):
        return False
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
           "-i", "color=c=blue:s=32x24:d=0.2", "-c:v", "libx264",
           "-pix_fmt", "yuv420p", "-metadata", f"creation_time={when}"]
    cmd.extend(extra)
    cmd.extend(["-f", "mov" if container == "mov" else "mp4", path])
    return subprocess.run(cmd, capture_output=True).returncode == 0


def ffprobe_time(path: str, tag: str = "creation_time") -> str:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json",
         path], capture_output=True, text=True)
    try:
        tags = json.loads(out.stdout)["format"]["tags"]
    except (ValueError, KeyError):
        return ""
    return tags.get(tag, "")


def atom(name: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body) + 8) + name + body


class ReadingTheClock(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="vidtime-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def at(self, name):
        return os.path.join(self.dir, name)

    @unittest.skipUnless(has("ffmpeg") and has("ffprobe"), "no ffmpeg here")
    def test_the_movie_header_agrees_with_ffprobe(self):
        path = self.at("a.mp4")
        self.assertTrue(make_clip(path, "2022-07-14T18:03:22Z"))
        got = video.capture_of(path)
        self.assertEqual(got.taken, dt.datetime(2022, 7, 14, 18, 3, 22))
        self.assertIn("2022-07-14T18:03:22", ffprobe_time(path))

    @unittest.skipUnless(has("ffmpeg"), "no ffmpeg here")
    def test_moov_at_the_end_of_the_file_is_still_found(self):
        """Which is where it is in anything not written for streaming - so
        reading the front of the file and giving up finds nothing at all."""
        path = self.at("b.mp4")
        self.assertTrue(make_clip(path, "2022-07-14T18:03:22Z"))
        with open(path, "rb") as fh:
            head = fh.read(200)
        self.assertNotIn(b"moov", head, "this file is not the case being tested")
        self.assertTrue(video.capture_of(path).ok)

    @unittest.skipUnless(has("ffmpeg"), "no ffmpeg here")
    def test_a_dated_string_with_a_timezone_beats_the_movie_header(self):
        """The header says 16:03 UTC and the camera says 18:03+0200. They are
        the same instant, and only one of them is the time on the clock where
        you were standing - which is what a photograph's time is."""
        path = self.at("c.mov")
        self.assertTrue(make_clip(path, "2022-07-14T16:03:22Z", "mov",
                                  ["-metadata", "date=2022-07-14T18:03:22+0200"]))
        got = video.capture_of(path)
        self.assertEqual(got.taken, dt.datetime(2022, 7, 14, 18, 3, 22))
        self.assertTrue(got.zone_known)
        self.assertEqual(got.offset_minutes, 120)

    @unittest.skipUnless(has("ffmpeg") and has("ffprobe"), "no ffmpeg here")
    def test_apples_creation_date_is_read_and_preferred(self):
        """iPhones and GoPros write it, and it is the only field that states the
        time where you were. Built here the way they build it, and ffprobe is
        asked whether the file really says what this test thinks it says."""
        path = self.at("d.mov")
        self.assertTrue(make_clip(path, "2022-07-14T16:03:22Z", "mov"))
        key = b"com.apple.quicktime.creationdate"
        keys = atom(b"keys", struct.pack(">II", 0, 1) + atom(b"mdta", key))
        data = atom(b"data", struct.pack(">II", 1, 0)
                    + b"2022-07-14T18:03:22+0300")
        ilst = atom(b"ilst", atom(struct.pack(">I", 1), data))
        hdlr = atom(b"hdlr", struct.pack(">II", 0, 0) + b"mdta" + b"\x00" * 12)
        udta = atom(b"udta", atom(b"meta", hdlr + keys + ilst))

        with open(path, "rb") as fh:
            buf = bytearray(fh.read())
        at = buf.find(b"moov") - 4
        size = struct.unpack_from(">I", buf, at)[0]
        buf[at + size:at + size] = udta
        struct.pack_into(">I", buf, at, size + len(udta))
        with open(path, "wb") as fh:
            fh.write(bytes(buf))

        self.assertIn("2022-07-14T18:03:22+0300",
                      ffprobe_time(path, "com.apple.quicktime.creationdate"),
                      "the file this test built is not what it thinks it is")
        got = video.capture_of(path)
        self.assertEqual(got.taken, dt.datetime(2022, 7, 14, 18, 3, 22))
        self.assertEqual(got.offset_minutes, 180)

    def test_a_sony_xml_beside_the_clip_wins_outright(self):
        path = self.at("C0001.MP4")
        with open(path, "wb") as fh:
            fh.write(b"\x00\x00\x00\x08free")
        with open(self.at("C0001.XML"), "w", encoding="utf-8") as fh:
            fh.write('<NonRealTimeMeta><CreationDate '
                     'value="2022-07-14T18:03:22+03:00"/></NonRealTimeMeta>')
        got = video.capture_of(path)
        self.assertEqual(got.taken, dt.datetime(2022, 7, 14, 18, 3, 22))
        self.assertEqual(got.offset_minutes, 180)
        self.assertTrue(got.zone_known)

    def test_a_time_with_no_zone_says_so(self):
        """Because what to do about it is the caller's decision, and it can only
        be made out loud."""
        moov = atom(b"moov", atom(b"mvhd", b"\x00\x00\x00\x00"
                                  + struct.pack(">I", 3740659402) + b"\x00" * 90))
        path = self.at("e.mp4")
        with open(path, "wb") as fh:
            fh.write(atom(b"ftyp", b"isom" + b"\x00" * 8) + moov)
        got = video.capture_of(path)
        self.assertEqual(got.taken, dt.datetime(2022, 7, 14, 16, 3, 22))
        self.assertFalse(got.zone_known)
        self.assertIn("may be UTC", got.describe())

    def test_a_flat_battery_date_is_not_a_capture_time(self):
        """A camera that lost its clock writes 1904, and filing a shoot under
        1904 is worse than not filing it."""
        moov = atom(b"moov", atom(b"mvhd", b"\x00\x00\x00\x00"
                                  + struct.pack(">I", 3600) + b"\x00" * 90))
        path = self.at("f.mp4")
        with open(path, "wb") as fh:
            fh.write(atom(b"ftyp", b"isom" + b"\x00" * 8) + moov)
        self.assertFalse(video.capture_of(path).ok)

    def test_rubbish_is_refused_rather_than_guessed_at(self):
        for name, body in (("g.mp4", b"not a video at all"),
                           ("h.mp4", b""),
                           ("i.mts", b"\x47" * 400)):
            path = self.at(name)
            with open(path, "wb") as fh:
                fh.write(body)
            got = video.capture_of(path)
            self.assertFalse(got.ok, name)
            self.assertTrue(got.how, "it should say why, not just fail")

    def test_the_formats_it_cannot_read_yet_say_which_they_are(self):
        path = self.at("00000.MTS")
        with open(path, "wb") as fh:
            fh.write(b"\x47" * 400)
        self.assertIn(".mts", video.capture_of(path).how)

    def test_a_clip_is_never_read_whole(self):
        """A four-gigabyte clip must cost a few seeks, not four gigabytes."""
        path = self.at("big.mp4")
        with open(path, "wb") as fh:
            fh.write(atom(b"ftyp", b"isom" + b"\x00" * 8))
            fh.write(struct.pack(">I", 8 + 40_000_000) + b"mdat")
            fh.write(b"\x00" * 40_000_000)
            fh.write(atom(b"moov", atom(b"mvhd", b"\x00\x00\x00\x00"
                                        + struct.pack(">I", 3740659402)
                                        + b"\x00" * 90)))
        moov = video.read_moov(path)
        self.assertLess(len(moov), 4096, "it read the picture data")
        self.assertTrue(video.capture_of(path).ok)


class WhichShoot(unittest.TestCase):
    def setUp(self):
        self.windows = shoots.build([
            ("Spain", dt.datetime(2022, 7, 14, 10)),
            ("Spain", dt.datetime(2022, 7, 14, 18)),
            ("Rome", dt.datetime(2022, 7, 20, 9)),
            ("Rome", dt.datetime(2022, 7, 21, 20)),
        ])

    def test_a_clip_shot_during_a_shoot(self):
        got = shoots.match(dt.datetime(2022, 7, 14, 12), self.windows)
        self.assertEqual(got.window.key, "Spain")
        self.assertTrue(got.exact)

    def test_and_one_shot_a_few_hours_after_it(self):
        """A shoot that ended at ten and a clip at half past eleven are the same
        evening."""
        got = shoots.match(dt.datetime(2022, 7, 14, 22), self.windows)
        self.assertEqual(got.window.key, "Spain")
        self.assertFalse(got.exact)

    def test_but_not_one_from_days_away(self):
        got = shoots.match(dt.datetime(2022, 7, 17, 12), self.windows)
        self.assertFalse(got)
        self.assertIn("nothing was photographed within", got.why)

    def test_the_tightest_window_wins(self):
        """A trip folder and the afternoon inside it both contain the clip, and
        only one of them is an answer."""
        windows = self.windows + shoots.build([
            ("Trip", dt.datetime(2022, 7, 13)), ("Trip", dt.datetime(2022, 7, 22))])
        got = shoots.match(dt.datetime(2022, 7, 14, 12), windows)
        self.assertEqual(got.window.key, "Spain")

    def test_a_year_folder_is_a_bucket_not_a_shoot(self):
        """Loose photographs in a year folder span a year, so that window
        contains every clip you own - true, and useless."""
        windows = self.windows + shoots.build([
            ("2022", dt.datetime(2022, 1, 1)), ("2022", dt.datetime(2022, 12, 31))])
        got = shoots.match(dt.datetime(2022, 7, 14, 22), windows)
        self.assertEqual(got.window.key, "Spain")
        self.assertFalse(shoots.match(dt.datetime(2022, 3, 3), windows))

    def test_two_equally_good_answers_are_refused_and_both_named(self):
        """Two shoots covering one afternoon is what a wedding and the walk home
        look like. A coin toss puts the clip somewhere you will not find it."""
        windows = shoots.build([
            ("Wedding", dt.datetime(2022, 7, 14, 10)),
            ("Wedding", dt.datetime(2022, 7, 14, 18)),
            ("Walk", dt.datetime(2022, 7, 14, 10)),
            ("Walk", dt.datetime(2022, 7, 14, 18)),
        ])
        got = shoots.match(dt.datetime(2022, 7, 14, 12), windows)
        self.assertFalse(got)
        self.assertIn("Wedding", got.why)
        self.assertIn("Walk", got.why)

    def test_no_time_and_no_windows_both_say_why(self):
        self.assertIn("no capture time", shoots.match(None, self.windows).why)
        self.assertIn("no dated photos",
                      shoots.match(dt.datetime(2022, 7, 14), []).why)


if __name__ == "__main__":
    unittest.main()
