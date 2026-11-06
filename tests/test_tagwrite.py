"""Writing a keyword - and the sidecar bug found while doing it.

Reading keywords was the easy half. Writing them means editing files somebody
else's program also writes, and the three ways that goes wrong are all silent:

- **the sidecar rebuilt instead of edited**, which threw away every develop
  setting, label and keyword Lightroom had put there. This was live: `write`
  said "keeping everything else it holds" and kept six attributes.
- **a keyword list replaced instead of added to**, which drops whatever was
  already on the photograph.
- **the picture changed**, which is the one thing that can never be undone. Every
  rewrite here is checked byte for byte before the file is replaced.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import jpegseg, sidecar, tags, tagwrite       # noqa: E402
from core.exifwrite import rating_of, set_rating        # noqa: E402
from core.photo import read_capture, read_gps           # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")

LIGHTROOM = """<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
   xmlns:dc="http://purl.org/dc/elements/1.1/"
   xmlns:xmp="http://ns.adobe.com/xap/1.0/"
   crs:Exposure2012="+0.85" crs:Highlights2012="-40" xmp:Label="Blue">
   <dc:subject><rdf:Bag><rdf:li>Italy</rdf:li></rdf:Bag></dc:subject>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="tagwrite-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def photo(self, name="plain", as_name="a.jpg"):
        path = os.path.join(self.dir, as_name)
        shutil.copy(os.path.join(FIX, name + ".jpg"), path)
        return path

    def negative(self, name="a.RW2", text=LIGHTROOM):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as fh:
            fh.write(b"not really a raw")
        with open(os.path.splitext(path)[0] + ".xmp", "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def side_text(self, path):
        with open(os.path.splitext(path)[0] + ".xmp", encoding="utf-8") as fh:
            return fh.read()


class TheSidecarBug(Base):
    """`write` rebuilt the file from the six attributes this app knows about."""

    def test_writing_a_rating_kept_nothing_and_now_keeps_everything(self):
        raw = self.negative()
        sidecar.write(raw, **{"xmp:Rating": "5"})
        text = self.side_text(raw)
        self.assertIn("Exposure2012", text)          # develop settings
        self.assertIn("Highlights2012", text)
        self.assertIn('xmp:Label="Blue"', text)      # somebody's colour label
        self.assertEqual(tags.tags_of(raw), ["Italy"])
        self.assertEqual(sidecar.read(raw)["xmp:Rating"], "5")

    def test_writing_keywords_keeps_the_rating_and_the_rest(self):
        raw = self.negative()
        sidecar.write(raw, **{"xmp:Rating": "4"})
        sidecar.set_keywords(raw, ["Italy", "bracket"])
        text = self.side_text(raw)
        self.assertIn("Exposure2012", text)
        self.assertEqual(sidecar.read(raw)["xmp:Rating"], "4")
        self.assertEqual(tags.tags_of(raw), ["Italy", "bracket"])

    def test_a_sidecar_written_from_nothing_still_reads_back(self):
        raw = os.path.join(self.dir, "fresh.RW2")
        with open(raw, "wb") as fh:
            fh.write(b"raw")
        sidecar.set_keywords(raw, ["bracket"])
        sidecar.write(raw, **{"xmp:Rating": "3"})
        self.assertEqual(tags.tags_of(raw), ["bracket"])
        self.assertEqual(sidecar.read(raw)["xmp:Rating"], "3")

    def test_a_document_this_does_not_understand_is_left_alone(self):
        """Better to lose the value than the file. Appending to something no
        reader can parse turns a sidecar into rubbish for every program."""
        raw = self.negative(text="this is not xmp at all")
        sidecar.write(raw, **{"xmp:Rating": "5"})
        self.assertEqual(self.side_text(raw), "this is not xmp at all")


class InsideTheJpeg(Base):
    def test_the_keyword_is_readable_three_ways(self):
        photo = self.photo()
        got = tagwrite.add(photo, ["bracket"])
        self.assertTrue(got["sidecar"] and got["xmp"] and got["windows"])
        self.assertEqual(got["errors"], [])
        self.assertEqual(tags.embedded_xmp(photo), ["bracket"])
        self.assertEqual(tags.windows_tags(photo), ["bracket"])
        self.assertEqual(tags.from_sidecar(photo), ["bracket"])

    def test_the_picture_is_not_touched(self):
        photo = self.photo()
        with open(photo, "rb") as fh:
            before = fh.read()
        tagwrite.add(photo, ["bracket", "Italy"])
        with open(photo, "rb") as fh:
            after = fh.read()
        ok, why = jpegseg.picture_unchanged(before, after)
        self.assertTrue(ok, why)

    def test_and_neither_is_anything_else_the_file_carried(self):
        """The rating, the capture time, the camera and the location all live in
        the same block being rewritten. Losing one silently is how a keyword
        costs you a location."""
        photo = self.photo("phone_doha", "gps.jpg")
        set_rating(photo, 4)
        was_gps, was_cap = read_gps(photo), read_capture(photo)
        tagwrite.add(photo, ["Doha"])
        now_gps, now_cap = read_gps(photo), read_capture(photo)
        self.assertEqual(rating_of(photo), 4)
        self.assertEqual((now_gps.lat, now_gps.lon), (was_gps.lat, was_gps.lon))
        self.assertEqual(now_cap.taken, was_cap.taken)
        self.assertEqual(now_cap.model, was_cap.model)

    def test_a_second_keyword_does_not_replace_the_first(self):
        photo = self.photo()
        tagwrite.add(photo, ["Italy"])
        tagwrite.add(photo, ["bracket"])
        self.assertEqual(tags.tags_of(photo), ["Italy", "bracket"])
        self.assertEqual(tags.windows_tags(photo), ["Italy", "bracket"])

    def test_the_same_keyword_twice_is_written_once(self):
        photo = self.photo()
        tagwrite.add(photo, ["bracket"])
        tagwrite.add(photo, ["BRACKET"])
        self.assertEqual(len(tags.tags_of(photo)), 1)

    def test_the_file_date_does_not_move(self):
        """A keyword must not read as "this file changed today" to every backup
        tool and every sort-by-date in the house."""
        photo = self.photo()
        os.utime(photo, (1_600_000_000, 1_600_000_000))
        tagwrite.add(photo, ["bracket"])
        self.assertEqual(int(os.path.getmtime(photo)), 1_600_000_000)

    def test_a_file_that_is_not_a_jpeg_still_gets_its_sidecar(self):
        raw = os.path.join(self.dir, "x.RW2")
        with open(raw, "wb") as fh:
            fh.write(b"raw")
        got = tagwrite.add(raw, ["bracket"])
        self.assertTrue(got["sidecar"])
        self.assertFalse(got["xmp"] or got["windows"])
        self.assertEqual(tags.tags_of(raw), ["bracket"])

    def test_nothing_is_written_for_an_empty_list(self):
        photo = self.photo()
        with open(photo, "rb") as fh:
            before = fh.read()
        self.assertEqual(tagwrite.add(photo, [])["errors"], [])
        with open(photo, "rb") as fh:
            self.assertEqual(fh.read(), before)
        self.assertFalse(os.path.exists(os.path.splitext(photo)[0] + ".xmp"))

    def test_a_photo_with_no_exif_says_so_rather_than_half_writing(self):
        photo = self.photo("noexif", "bare.jpg")
        got = tagwrite.add(photo, ["bracket"])
        self.assertTrue(got["sidecar"])              # the sidecar always works
        self.assertTrue(got["xmp"])                  # XMP can be added from nothing
        self.assertFalse(got["windows"])             # Explorer's field cannot
        self.assertTrue(any("EXIF" in e for e in got["errors"]), got["errors"])


class APacketPastTheFirstQuarterMegabyte(Base):
    """deep_xmp.jpg carries a 300 KB ICC profile ahead of a Lightroom packet:
    a crop, the keyword Italy and four stars. Read as "no packet", a tag write
    built a fresh packet and the splice put it in place of the real one."""

    def test_a_tag_write_keeps_the_crop_the_rating_and_the_old_keyword(self):
        p = self.photo("deep_xmp")
        with open(p, "rb") as fh:
            before = fh.read()
        tagwrite.add(p, ["Rome"], in_sidecar=False)
        packet = jpegseg.xmp_packet(p)
        self.assertIn('crs:CropTop="0.125"', packet)
        self.assertIn('xmp:Rating="4"', packet)
        self.assertEqual(sorted(tags.from_xmp(packet)), ["Italy", "Rome"])
        self.assertEqual(sorted(tags.tags_of(p)), ["Italy", "Rome"])
        with open(p, "rb") as fh:
            ok, why = jpegseg.picture_unchanged(before, fh.read())
        self.assertTrue(ok, why)

    def test_and_so_does_a_colour_label(self):
        from core import labels
        p = self.photo("deep_xmp")
        labels.write_label_in_jpeg(p, "Red")
        packet = jpegseg.xmp_packet(p)
        self.assertIn('crs:CropTop="0.125"', packet)
        self.assertIn("Italy", packet)
        self.assertIn("Red", packet)


class TheFilesOwnKeywordsAreKept(Base):
    """A sidecar with a keyword list wins the read; writing that list into the
    file replaced the file's own Italy and Rome with the sidecar's Beach."""

    def test_adding_merges_the_embedded_list_with_the_sidecar(self):
        p = self.photo()
        tagwrite.write_xmp_keywords(p, ["Italy", "Rome"])
        tagwrite.write_xp_keywords(p, ["Italy", "Rome"])
        sidecar.set_keywords(p, ["Beach"])
        tagwrite.add(p, ["Sunset"])
        self.assertEqual(sorted(tags.embedded_xmp(p)),
                         ["Beach", "Italy", "Rome", "Sunset"])
        self.assertEqual(sorted(tags.windows_tags(p)),
                         ["Beach", "Italy", "Rome", "Sunset"])

    def test_removing_takes_off_only_the_one_asked_for(self):
        p = self.photo()
        tagwrite.write_xmp_keywords(p, ["Italy", "Rome"])
        sidecar.set_keywords(p, ["Beach"])
        tagwrite.remove(p, ["Italy"])
        self.assertEqual(sorted(tags.embedded_xmp(p)), ["Beach", "Rome"])


class ForThePreview(unittest.TestCase):
    def test_the_originals_words_plus_the_bracket_one(self):
        got = tagwrite.keywords_for_preview(["Italy", "portfolio"], ["bracket"])
        self.assertEqual(got, ["Italy", "portfolio", "bracket"])

    def test_and_never_the_same_word_twice(self):
        got = tagwrite.keywords_for_preview(["Bracket"], ["bracket"])
        self.assertEqual(got, ["Bracket"])

    def test_nothing_extra_is_nothing_added(self):
        self.assertEqual(tagwrite.keywords_for_preview(["Italy"], []), ["Italy"])
        self.assertEqual(tagwrite.keywords_for_preview([], []), [])


if __name__ == "__main__":
    unittest.main()
