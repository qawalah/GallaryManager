"""Keywords, read from all four places photographs actually carry them.

The point of this module is not that it can parse XMP. It is that a tag filter
which reads ONE of the four formats is worse than no filter: it reports "nothing
matched Italy" about a folder full of Italy, and that answer looks like a fact.
So every test here is really the same test - does this photo still count as
tagged when the tag was written by a different program.
"""

import os
import shutil
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from core import tags                      # noqa: E402
from core import settings as S             # noqa: E402
from core.exifwrite import set_rating      # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


# --------------------------------------------------------------- making files

def app1_xmp(text: str) -> bytes:
    body = tags.XMP_NS + b"\x00" + text.encode("utf-8")
    return b"\xff\xe1" + struct.pack(">H", len(body) + 2) + body


def app1_xpkeywords(text: str) -> bytes:
    """A minimal TIFF block holding nothing but Windows' own Tags field."""
    value = text.encode("utf-16-le") + b"\x00\x00"
    ifd_size = 2 + 12 + 4
    at = 8 + ifd_size
    tiff = b"II*\x00" + struct.pack("<I", 8)
    ifd = struct.pack("<H", 1)
    ifd += struct.pack("<HHII", tags.XP_KEYWORDS, 1, len(value), at)
    ifd += struct.pack("<I", 0)
    body = b"Exif\x00\x00" + tiff + ifd + value
    return b"\xff\xe1" + struct.pack(">H", len(body) + 2) + body


def app13_iptc(keywords) -> bytes:
    datasets = b""
    for word in keywords:
        raw = word.encode("utf-8")
        datasets += b"\x1c\x02\x19" + struct.pack(">H", len(raw)) + raw
    resource = (b"8BIM" + struct.pack(">H", tags.IPTC_BLOCK) + b"\x00\x00"
                + struct.pack(">I", len(datasets)) + datasets)
    if len(datasets) % 2:
        resource += b"\x00"
    body = tags.PHOTOSHOP + resource
    return b"\xff\xed" + struct.pack(">H", len(body) + 2) + body


def jpeg_with(path: str, *segments: bytes) -> str:
    with open(path, "wb") as fh:
        fh.write(b"\xff\xd8")
        for seg in segments:
            fh.write(seg)
        fh.write(b"\xff\xda\x00\x02\x00\xff\xd9")
    return path


SIDECAR = """<?xpacket begin=""?><x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmp:Rating="5">
   <dc:subject><rdf:Bag>{}</rdf:Bag></dc:subject>
  </rdf:Description>
 </rdf:RDF></x:xmpmeta>"""

NO_RATING = """<?xpacket begin=""?><x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="">
   <dc:subject><rdf:Bag>{}</rdf:Bag></dc:subject>
  </rdf:Description>
 </rdf:RDF></x:xmpmeta>"""

RATING_ONLY = """<?xpacket begin=""?><x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmp:Rating="5"/>
 </rdf:RDF></x:xmpmeta>"""


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="tags-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def at(self, name):
        return os.path.join(self.dir, name)

    def sidecar(self, photo, *words, body=None):
        text = body if body is not None else SIDECAR.format(
            "".join(f"<rdf:li>{w}</rdf:li>" for w in words))
        with open(os.path.splitext(photo)[0] + ".xmp", "w", encoding="utf-8") as fh:
            fh.write(text)


# ------------------------------------------------------------------- the text

class ReadingXmp(Base):
    def test_a_bag_of_keywords(self):
        got = tags.from_xmp(SIDECAR.format(
            "<rdf:li>Italy</rdf:li><rdf:li>portfolio</rdf:li>"))
        self.assertEqual(got, ["Italy", "portfolio"])

    def test_the_hierarchical_list_too(self):
        """Lightroom writes both, and they do not hold the same thing. A library
        edited across two programs can have only one of them filled in."""
        text = ("<lr:hierarchicalSubject><rdf:Bag><rdf:li>Travel|Italy|Rome"
                "</rdf:li></rdf:Bag></lr:hierarchicalSubject>")
        self.assertEqual(tags.from_xmp(text), ["Travel|Italy|Rome"])

    def test_escaped_characters_come_back_as_typed(self):
        text = SIDECAR.format("<rdf:li>Ali &amp; Layla</rdf:li>")
        self.assertEqual(tags.from_xmp(text), ["Ali & Layla"])

    def test_a_writer_that_used_one_plain_element(self):
        self.assertEqual(tags.from_xmp("<dc:subject>Italy</dc:subject>"), ["Italy"])

    def test_repeats_and_blanks_are_dropped(self):
        text = SIDECAR.format("<rdf:li>Italy</rdf:li><rdf:li> </rdf:li>"
                              "<rdf:li>italy</rdf:li>")
        self.assertEqual(tags.from_xmp(text), ["Italy"])


class ReadingSidecars(Base):
    def test_keywords_beside_a_raw(self):
        raw = self.at("DSC1.RW2")
        open(raw, "wb").write(b"raw")
        self.sidecar(raw, "Italy")
        self.assertEqual(tags.tags_of(raw), ["Italy"])

    def test_a_sidecar_holding_only_a_rating_is_not_a_claim_of_no_tags(self):
        """The trap. This app writes rating-only sidecars itself, so reading one
        as "untagged" would make every photo it has ever rated invisible to the
        filter - including ones tagged inside the file."""
        photo = jpeg_with(self.at("a.jpg"), app1_xpkeywords("Italy"))
        self.sidecar(photo, body=RATING_ONLY)
        self.assertIsNone(tags.from_sidecar(photo))
        self.assertEqual(tags.tags_of(photo), ["Italy"])

    def test_but_an_empty_keyword_list_is_a_deliberate_answer(self):
        photo = jpeg_with(self.at("b.jpg"), app1_xpkeywords("Italy"))
        self.sidecar(photo, body=SIDECAR.format(""))
        self.assertEqual(tags.from_sidecar(photo), [])
        self.assertEqual(tags.tags_of(photo), [])

    def test_a_sidecar_with_keywords_wins_over_the_file(self):
        photo = jpeg_with(self.at("c.jpg"), app1_xpkeywords("old"))
        self.sidecar(photo, "new")
        self.assertEqual(tags.tags_of(photo), ["new"])


class ReadingFiles(Base):
    def test_xmp_inside_a_jpeg(self):
        photo = jpeg_with(self.at("x.jpg"),
                          app1_xmp(SIDECAR.format("<rdf:li>Roma</rdf:li>")))
        self.assertEqual(tags.embedded_xmp(photo), ["Roma"])
        self.assertEqual(tags.tags_of(photo), ["Roma"])

    def test_windows_own_tags_box(self):
        """UTF-16 bytes pretending to be a list of numbers, semicolon separated.
        Nothing but Explorer writes it and nothing but Explorer reads it."""
        photo = jpeg_with(self.at("w.jpg"), app1_xpkeywords("Italy;portfolio"))
        self.assertEqual(tags.windows_tags(photo), ["Italy", "portfolio"])

    def test_iptc_keywords(self):
        photo = jpeg_with(self.at("i.jpg"), app13_iptc(["Italy", "Rome"]))
        self.assertEqual(tags.iptc_tags(photo), ["Italy", "Rome"])

    def test_an_odd_length_keyword_does_not_derail_the_next_one(self):
        photo = jpeg_with(self.at("j.jpg"), app13_iptc(["odd", "Rome"]))
        self.assertEqual(tags.iptc_tags(photo), ["odd", "Rome"])

    def test_all_of_them_at_once(self):
        photo = jpeg_with(self.at("all.jpg"),
                          app1_xmp(SIDECAR.format("<rdf:li>Roma</rdf:li>")),
                          app1_xpkeywords("holiday"),
                          app13_iptc(["press"]))
        self.assertEqual(sorted(tags.tags_of(photo)), ["Roma", "holiday", "press"])

    def test_a_file_with_no_tags_anywhere(self):
        self.assertEqual(tags.tags_of(os.path.join(FIX, "plain.jpg")), [])

    def test_nothing_here_raises_on_rubbish(self):
        junk = self.at("junk.jpg")
        open(junk, "wb").write(b"not a jpeg at all")
        self.assertEqual(tags.tags_of(junk), [])
        self.assertEqual(tags.tags_of(self.at("missing.jpg")), [])


# ------------------------------------------------------------------ matching

class Matching(unittest.TestCase):
    HAVE = ["Travel|Italy|Rome", "portfolio"]

    def test_any_level_of_a_hierarchy(self):
        for word in ("Italy", "Rome", "Travel", "italy"):
            self.assertTrue(tags.matches(self.HAVE, [word]), word)

    def test_and_any_branch_above_it(self):
        self.assertTrue(tags.matches(self.HAVE, ["Travel|Italy"]))
        self.assertTrue(tags.matches(self.HAVE, ["Travel/Italy"]))

    def test_but_not_a_branch_it_does_not_hang_from(self):
        self.assertFalse(tags.matches(self.HAVE, ["Italy|Rome"]))

    def test_and_never_half_a_word(self):
        self.assertFalse(tags.matches(self.HAVE, ["Ital"]))
        self.assertFalse(tags.matches(self.HAVE, ["port"]))

    def test_every_means_all_of_them(self):
        self.assertTrue(tags.matches(self.HAVE, ["Italy", "portfolio"], every=True))
        self.assertFalse(tags.matches(self.HAVE, ["Italy", "Spain"], every=True))
        self.assertTrue(tags.matches(self.HAVE, ["Italy", "Spain"]))

    def test_an_empty_filter_is_not_a_filter(self):
        """A blank box must match everything. The other way round, an empty box
        silently sends nothing and looks like a broken app."""
        self.assertTrue(tags.matches([], []))
        self.assertTrue(tags.matches(self.HAVE, tags.wanted_list("")))

    def test_the_box_is_read_as_a_list(self):
        self.assertEqual(tags.wanted_list("Italy, portfolio"), ["Italy", "portfolio"])
        self.assertEqual(tags.wanted_list("Italy\nRome; Rome"), ["Italy", "Rome"])

    def test_hits_names_what_actually_matched(self):
        self.assertEqual(tags.hits(self.HAVE, ["Rome", "Spain"]), ["Rome"])


# ------------------------------------------------------------ send to develop

class TheFilter(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="devtags-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.out = os.path.join(self.dir, "To Develop")
        self.shoot = os.path.join(self.lib, "2022", "Italy")
        os.makedirs(self.shoot)
        os.makedirs(os.path.join(self.raw, "2022", "Italy"))
        # five star and tagged; four star and untagged; unrated but tagged
        for name, stars, words in (("plain", 5, ["Travel|Italy|Rome"]),
                                   ("rated", 4, []),
                                   ("aeb1", 0, ["portfolio"])):
            jpeg = os.path.join(self.shoot, name + ".JPG")
            shutil.copy(os.path.join(FIX, name + ".jpg"), jpeg)
            shutil.copy(os.path.join(FIX, name + ".jpg"),
                        os.path.join(self.raw, "2022", "Italy", name + ".RW2"))
            if stars:
                set_rating(jpeg, stars)
            if words:
                with open(os.path.splitext(jpeg)[0] + ".xmp", "w",
                          encoding="utf-8") as fh:
                    fh.write(NO_RATING.format(
                        "".join(f"<rdf:li>{w}</rdf:li>" for w in words)))
        S.save({"library": self.lib, "raw": self.raw, "develop": self.out})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def send(self, **over):
        t = R.get("develop")
        p = t.make_plan({"folder": self.lib, **over})
        self.assertFalse(p.blocked, p.blocked)
        return p

    def sent(self, p):
        return {r.name for r in p.rows if r.what == "send"}

    def test_no_tags_typed_changes_nothing(self):
        self.assertEqual(self.sent(self.send()),
                         {"plain.JPG", "plain.RW2", "rated.JPG"})

    def test_narrowing_sends_only_what_carries_the_tag(self):
        p = self.send(tags="Italy")
        self.assertEqual(self.sent(p), {"plain.JPG", "plain.RW2"})

    def test_narrowing_counts_the_rest_once_and_says_so(self):
        p = self.send(tags="Italy")
        stats = dict(p.stats)
        self.assertEqual(stats["Left out, not tagged"], "2")
        self.assertEqual(stats["Photos examined"], "3")

    def test_widening_adds_an_unrated_photo_but_not_its_negative(self):
        """A tag is not a rating. "Also send my portfolio shots" must not quietly
        copy fifty megabytes of ARW for photos that never earned one."""
        p = self.send(tags="portfolio", tags_rule="also")
        self.assertEqual(self.sent(p), {"plain.JPG", "plain.RW2", "rated.JPG",
                                        "aeb1.JPG"})

    def test_the_row_says_which_tag_brought_it(self):
        p = self.send(tags="portfolio", tags_rule="also")
        row = [r for r in p.rows if r.name == "aeb1.JPG"][0]
        self.assertIn("portfolio", row.detail)

    def test_every_tag_can_be_demanded(self):
        p = self.send(tags="Italy, portfolio", tags_all=True)
        self.assertEqual(self.sent(p), set())
        p = self.send(tags="Italy, portfolio")
        self.assertEqual(self.sent(p), {"plain.JPG", "plain.RW2"})

    def test_when_nothing_matches_it_says_what_the_tags_actually_are(self):
        """A typo must not read as "you have no Italy photos". The dead end is
        the bug; the list of tags on file is the fix."""
        p = self.send(tags="Itlay")
        self.assertEqual(self.sent(p), set())
        said = " ".join(p.notes)
        self.assertIn("Nothing carried those tags", said)
        self.assertIn("Travel|Italy|Rome", said)

    def test_and_when_the_photos_carry_no_tags_at_all_it_says_that_instead(self):
        for side in ("plain", "aeb1"):
            os.remove(os.path.join(self.shoot, side + ".xmp"))
        p = self.send(tags="Italy")
        self.assertIn("do not carry any tags",
                      " ".join(p.notes).replace("carry any tags at all",
                                                "do not carry any tags"))

    def test_the_rule_in_force_is_written_down(self):
        self.assertIn("Only photos tagged x", " ".join(self.send(tags="x").notes))
        self.assertIn("carrying any of a, b",
                      " ".join(self.send(tags="a, b").notes))
        self.assertIn("whatever", " ".join(
            self.send(tags="x", tags_rule="also").notes))


class TheContradiction(unittest.TestCase):
    """A JPEG whose RAW is missing was listed as being sent AND as left alone, in
    the same result, with a reason that talked about JPEGs when it meant RAWs -
    because the matcher is written for a RAW looking for its JPEG and this task
    calls it the other way round."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="devrow-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.out = os.path.join(self.dir, "To Develop")
        self.shoot = os.path.join(self.lib, "2022", "Italy")
        os.makedirs(self.shoot)
        os.makedirs(self.raw)
        self.jpeg = os.path.join(self.shoot, "DSC00241.JPG")
        shutil.copy(os.path.join(FIX, "plain.jpg"), self.jpeg)
        set_rating(self.jpeg, 5)
        S.save({"library": self.lib, "raw": self.raw, "develop": self.out})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def plan(self):
        t = R.get("develop")
        p = t.make_plan({"folder": self.lib})
        self.assertFalse(p.blocked, p.blocked)
        return p

    def test_the_jpeg_is_not_in_both_lists(self):
        p = self.plan()
        sending = {r.name for r in p.rows if r.what == "send"}
        self.assertIn("DSC00241.JPG", sending)
        self.assertNotIn("DSC00241.JPG", {n for n, _why in p.skipped})

    def test_what_is_named_is_the_missing_negative(self):
        p = self.plan()
        names = [n for n, _why in p.skipped]
        self.assertTrue(any("RAW file" in n and "DSC00241" in n for n in names),
                        names)

    def test_and_the_reason_talks_about_raws_not_jpegs(self):
        p = self.plan()
        why = " ".join(w for _n, w in p.skipped)
        self.assertIn("no RAW in the RAW tree matches it", why)
        self.assertNotIn("no JPEG anywhere", why)

    def test_and_it_says_the_jpeg_is_still_going(self):
        p = self.plan()
        why = " ".join(w for _n, w in p.skipped)
        self.assertIn("JPEG itself is still being sent", why)

    def test_ambiguity_is_reported_as_ambiguity(self):
        for name in ("a", "b"):
            copy = os.path.join(self.raw, f"{name}.RW2")
            shutil.copy(os.path.join(FIX, "plain.jpg"), copy)
            os.rename(copy, os.path.join(self.raw, "DSC00241.RW2"
                                         if name == "a" else "DSC00241.RW2"))
        # two RAWs of the same base name, in two folders
        second = os.path.join(self.raw, "again")
        os.makedirs(second)
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(second, "DSC00241.RW2"))
        p = self.plan()
        why = " ".join(w for _n, w in p.skipped)
        self.assertIn("RAWs share its name", why)


if __name__ == "__main__":
    unittest.main()
