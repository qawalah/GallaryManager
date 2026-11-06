"""HEIC: an iPhone's photographs, read like any other.

They were counted and then known nothing about - no date, no camera, no place,
no thumbnail - so a phone's year sorted into "undated" and geotagged itself
over the position the phone had already recorded. The EXIF is the same TIFF
block a JPEG carries, boxed differently; these tests are about the boxing,
and about the app staying whole on a machine with no HEIC decoder.

The two real HEIC fixtures are made by tools/make_fixtures.py with
pillow-heif. The odd shapes below are built by hand, box by box, because no
encoder can be asked to write a file that is split, offset or damaged.
"""

import os
import shutil
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R                  # noqa: E402
import app.tasks                               # noqa: E402,F401
from core import exif, facts, heif, jpegseg    # noqa: E402
from core import settings as S                 # noqa: E402
from core import sidecar as sc                 # noqa: E402
from core import survey, thumbs                # noqa: E402
from core.photo import read_capture, read_gps  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def fx(name):
    return os.path.join(FIX, name)


def _bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _tiff() -> bytes:
    """The TIFF block of the Doha phone photograph, taken from the JPEG."""
    t = exif.exif_block(fx("phone_doha.jpg"))
    return t.buf[t.base:]


def box(typ: bytes, body: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(body), typ) + body


def full(typ: bytes, version: int, body: bytes) -> bytes:
    return box(typ, bytes([version, 0, 0, 0]) + body)


def build(payload: bytes, *, version=1, method=0, pieces=1, gap=0,
          brand=b"heic", meta_padding=0, cut=0) -> bytes:
    """A HEIF file whose item 2 is EXIF, laid out as asked.

    `pieces` splits the EXIF into that many extents, stored in reverse order
    so that joining them in file order would give the wrong bytes. `gap` puts
    that many bytes of picture before them. `method=1` keeps them in the meta
    box's own `idat` instead. `cut` chops that many bytes off the end.
    """
    size = len(payload)
    bounds = [size * i // pieces for i in range(pieces + 1)]
    chunks = [payload[bounds[i]:bounds[i + 1]] for i in range(pieces)]

    def iloc(offsets):
        body = bytes([0x44, 0x00])          # 4-byte offsets and lengths, no base
        body += struct.pack(">I" if version == 2 else ">H", 1)
        body += struct.pack(">I" if version == 2 else ">H", 2)
        if version in (1, 2):
            body += struct.pack(">H", method)
        body += struct.pack(">H", 0)        # data reference index
        body += struct.pack(">H", pieces)
        for off, chunk in zip(offsets, chunks):
            body += struct.pack(">II", off, len(chunk))
        return full(b"iloc", version, body)

    def infe(item, typ):
        return full(b"infe", 2, struct.pack(">HH4s", item, 0, typ) + b"\0")

    def meta(offsets):
        kids = full(b"hdlr", 0, b"\0" * 4 + b"pict" + b"\0" * 13)
        if meta_padding:
            kids += box(b"free", b"\0" * meta_padding)
        kids += full(b"iinf", 0, struct.pack(">H", 2) + infe(1, b"hvc1")
                     + infe(2, b"Exif"))
        kids += iloc(offsets)
        if method == 1:
            kids += box(b"idat", b"".join(reversed(chunks)))
        return full(b"meta", 0, kids)

    ftyp = box(b"ftyp", brand + b"\0\0\0\0" + b"mif1" + brand)
    # Stored in reverse, so the extents' own order is the only right one.
    stored = b"".join(reversed(chunks))
    where, at = [], 0
    for chunk in reversed(chunks):
        where.append(at)
        at += len(chunk)
    where = list(reversed(where))
    if method == 1:
        offsets = where
        mdat = box(b"mdat", b"\x55" * 64)
    else:
        head = len(ftyp) + len(meta([0] * pieces)) + 8 + gap
        offsets = [head + w for w in where]
        mdat = box(b"mdat", b"\x55" * gap + stored)
    data = ftyp + meta(offsets) + mdat
    return data[:len(data) - cut] if cut else data


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="heif-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, data: bytes, name="IMG_0001.HEIC") -> str:
        path = os.path.join(self.dir, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def standard(self, **kw) -> bytes:
        return build(struct.pack(">I", 6) + b"Exif\0\0" + _tiff(), **kw)


class AnIphonePhotograph(unittest.TestCase):
    def test_it_has_a_date_a_camera_and_a_timezone(self):
        got = read_capture(fx("phone_doha.heic"))
        self.assertTrue(got.ok)
        self.assertEqual(str(got.taken), "2022-07-14 21:03:20")
        self.assertEqual(got.model, "iPhone 15 Pro")
        self.assertEqual(got.offset_minutes, 180)
        self.assertEqual(got.fnumber, 5.6)

    def test_it_has_the_position_the_phone_recorded(self):
        got = read_gps(fx("phone_doha.heic"))
        self.assertTrue(got.has_gps)
        self.assertAlmostEqual(got.lat, 25.2854, places=4)
        self.assertAlmostEqual(got.lon, 51.5310, places=4)
        self.assertAlmostEqual(got.altitude, 12.5)
        self.assertEqual(got.utc.isoformat(), "2022-07-14T18:03:20+00:00")

    def test_one_without_a_position_says_so_and_keeps_its_date(self):
        got = read_gps(fx("plain.heic"))
        self.assertFalse(got.has_gps)
        self.assertEqual(str(got.taken), "2022-07-14 18:03:22")

    def test_it_is_recognised_by_what_is_inside_not_by_its_name(self):
        self.assertTrue(heif.is_heif(jpegseg.read_header(fx("plain.heic"), 64)))
        self.assertFalse(heif.is_heif(jpegseg.read_header(fx("plain.jpg"), 64)))

    def test_a_retimed_one_is_dated_by_its_sidecar(self):
        """As for any file this app does not rewrite: the sidecar holds the
        corrected time, and the clock inside is the wrong one."""
        tmp = tempfile.mkdtemp(prefix="heif-")
        try:
            path = os.path.join(tmp, "IMG_0001.HEIC")
            shutil.copy(fx("plain.heic"), path)
            from core.exifwrite import set_datetime
            import datetime as dt
            self.assertEqual(set_datetime(path, dt.datetime(2023, 1, 2, 3, 4, 5)),
                             "sidecar")
            self.assertEqual(str(read_capture(path).taken), "2023-01-02 03:04:05")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class FindingTheExifWhereverItIs(_Tmp):
    def assertReads(self, path):
        got = read_capture(path)
        self.assertTrue(got.ok, "no EXIF found")
        self.assertEqual(str(got.taken), "2022-07-14 21:03:20")
        self.assertEqual(got.model, "SM-G991B")
        self.assertTrue(read_gps(path).has_gps)

    def test_every_version_of_the_location_box(self):
        for version in (0, 1, 2):
            with self.subTest(version=version):
                self.assertReads(self.write(self.standard(version=version),
                                            f"v{version}.heic"))

    def test_kept_inside_the_meta_box(self):
        self.assertReads(self.write(self.standard(method=1)))

    def test_in_pieces_joined_in_the_order_the_box_gives(self):
        self.assertReads(self.write(self.standard(pieces=3)))

    def test_far_past_the_first_read(self):
        """Some writers put the EXIF after the picture. The first read is a
        quarter megabyte; the rest is fetched only as far as it is needed."""
        path = self.write(self.standard(gap=jpegseg.HEADER_BYTES * 2))
        self.assertGreater(os.path.getsize(path), jpegseg.HEADER_BYTES * 2)
        self.assertReads(path)

    def test_behind_a_meta_box_longer_than_the_first_read(self):
        """A HEIC made of hundreds of tiles has a long item list."""
        self.assertReads(self.write(
            self.standard(meta_padding=jpegseg.HEADER_BYTES + 1000)))

    def test_when_the_offset_does_not_say_where_the_tiff_starts(self):
        """Some writers say 0 and put "Exif\\0\\0" there anyway."""
        data = build(struct.pack(">I", 0) + b"Exif\0\0" + _tiff())
        self.assertReads(self.write(data))

    def test_with_no_exif_prefix_at_all(self):
        data = build(struct.pack(">I", 0) + _tiff())
        self.assertReads(self.write(data))

    def test_announced_only_as_a_compatible_brand(self):
        self.assertReads(self.write(self.standard(brand=b"XYZ1")))

    def test_announced_only_as_the_major_brand(self):
        data = self.standard()
        ftyp = box(b"ftyp", b"heic\0\0\0\0isomXYZ1")
        self.assertEqual(data[:len(ftyp)][4:8], b"ftyp")
        self.assertReads(self.write(ftyp + data[len(ftyp):]))


class ADamagedOneIsNotARaisedError(_Tmp):
    def test_cut_short_it_has_no_exif_rather_than_half_of_one(self):
        path = self.write(self.standard(cut=200))
        self.assertIsNone(exif.exif_block(path))
        self.assertFalse(read_capture(path).ok)

    def test_a_box_that_lies_about_its_size(self):
        data = bytearray(self.standard())
        at = data.index(b"meta") - 4
        data[at:at + 4] = struct.pack(">I", 0xFFFFFF00)
        self.assertIsNone(exif.exif_block(self.write(bytes(data))))

    def test_noise_after_a_heif_header(self):
        data = self.standard()[:40] + bytes(range(256)) * 8
        self.assertIsNone(exif.exif_block(self.write(data)))

    def test_a_cr3_is_not_read_as_one(self):
        """Same box format, other brands, and a different layout inside."""
        data = self.standard().replace(b"heic", b"crx ").replace(b"mif1", b"isom")
        self.assertIsNone(exif.exif_block(self.write(data, "A.CR3")))


class TheLibraryKnowsThemNow(_Tmp):
    def test_the_survey_counts_them_dated_and_located(self):
        path = self.write(_bytes(fx("phone_doha.heic")))
        readable, _rated, located, when = survey._read_one(path)
        self.assertTrue(readable)
        self.assertTrue(located)
        self.assertTrue(when.startswith("2022-07-14"))

    def test_a_note_taken_before_they_could_be_read_is_not_trusted(self):
        """A HEIC noted as "no date" by an older release must be read again,
        or a library stays undated until every file in it changes."""
        path = self.write(_bytes(fx("plain.heic")))
        st = os.stat(path)
        before = f"{st.st_size}:{st.st_mtime_ns}:{st.st_ino}"
        self.assertNotEqual(facts.signature(path), before)
        other = self.write(_bytes(fx("plain.jpg")), "a.png")
        st = os.stat(other)
        self.assertEqual(facts.signature(other),
                         f"{st.st_size}:{st.st_mtime_ns}:{st.st_ino}",
                         "only the HEIC notes are thrown away")
        # A JPEG carries a mark of its own since 3.12.2 (its XMP packet is read
        # further and its packet rating counts), and it is not the HEIC one.
        jpeg = self.write(_bytes(fx("plain.jpg")), "a.jpg")
        self.assertNotIn("#heif", facts.signature(jpeg))

    def test_and_a_folder_holding_one_is_surveyed_again(self):
        jpegs = os.path.join(self.dir, "jpegs")
        mixed = os.path.join(self.dir, "mixed")
        for folder in (jpegs, mixed):
            os.makedirs(folder)
            shutil.copy(fx("plain.jpg"), os.path.join(folder, "a.jpg"))
        shutil.copy(fx("plain.heic"), os.path.join(mixed, "b.HEIC"))
        self.assertTrue(survey.signature(jpegs).startswith(f"{survey.VERSION}:"))
        self.assertTrue(survey.signature(mixed).startswith(f"{survey.VERSION}h:"))


class WithoutADecoder(_Tmp):
    def test_none_installed_is_an_empty_answer_not_an_error(self):
        was = heif._OPENER
        try:
            heif._OPENER = None
            with mock.patch.dict(sys.modules, {"pi_heif": None, "pillow_heif": None}):
                self.assertEqual(heif.decoder(), "")
                self.assertFalse(heif.can_decode())
        finally:
            heif._OPENER = was

    def test_one_that_is_there_but_will_not_load_is_the_same(self):
        """On a NAS, a missing system library shows up as an OSError."""
        broken = types.ModuleType("pi_heif")

        def fails():
            raise OSError("libheif.so.1: cannot open shared object file")
        broken.register_heif_opener = fails
        was = heif._OPENER
        try:
            heif._OPENER = None
            with mock.patch.dict(sys.modules, {"pi_heif": broken,
                                               "pillow_heif": None}):
                self.assertEqual(heif.decoder(), "")
        finally:
            heif._OPENER = was

    def test_the_dates_and_places_do_not_need_one(self):
        with mock.patch.object(heif, "can_decode", return_value=False):
            self.assertTrue(read_gps(fx("phone_doha.heic")).has_gps)

    def test_a_thumbnail_is_simply_not_made(self):
        path = self.write(_bytes(fx("plain.heic")))
        with mock.patch.object(heif, "can_decode", return_value=False):
            self.assertIsNone(thumbs.thumb(path, "s"))

    def test_making_previews_names_what_to_install(self):
        lib = os.path.join(self.dir, "Photos")
        shoot = os.path.join(lib, "2022", "Phone")
        prev = os.path.join(self.dir, "Previews")
        os.makedirs(shoot)
        os.makedirs(prev)
        shutil.copy(fx("plain.heic"), os.path.join(shoot, "IMG_0001.HEIC"))
        shutil.copy(fx("plain.jpg"), os.path.join(shoot, "DSC0001.JPG"))
        S.save({"library": lib, "previews": prev})
        with mock.patch.object(heif, "can_decode", return_value=False):
            p = R.get("previews").make_plan({"folder": shoot, "previews": prev})
        self.assertFalse(p.blocked, p.blocked)
        self.assertEqual([r.name for r in p.rows], ["DSC0001.JPG"])
        why = dict(p.skipped)[os.path.join(shoot, "IMG_0001.HEIC")]
        self.assertIn("pi-heif", why)


@unittest.skipUnless(heif.can_decode(), "no HEIC decoder (pip install pi-heif)")
class WithADecoder(_Tmp):
    def test_a_thumbnail_is_a_jpeg(self):
        path = self.write(_bytes(fx("phone_doha.heic")))
        got = thumbs.thumb(path, "s")
        self.assertTrue(got and jpegseg.is_jpeg(got))

    def test_a_preview_is_made_and_keeps_the_clock(self):
        """The capture time is what pairs a preview back to its original."""
        lib = os.path.join(self.dir, "Photos")
        shoot = os.path.join(lib, "2022", "Phone")
        prev = os.path.join(self.dir, "Previews")
        os.makedirs(shoot)
        os.makedirs(prev)
        shutil.copy(fx("phone_doha.heic"), os.path.join(shoot, "IMG_0001.HEIC"))
        S.save({"library": lib, "previews": prev})
        t = R.get("previews")
        p = t.make_plan({"folder": shoot, "previews": prev})
        self.assertEqual(len(p.rows), 1, p.skipped)
        r = t.apply(p)
        self.assertEqual(r.failed, 0, r.details)
        made = os.path.join(prev, "2022", "Phone", "IMG_0001.jpg")
        self.assertEqual(str(read_capture(made).taken), "2022-07-14 21:03:20")


class LocatingThem(_Tmp):
    """Only a JPEG is rewritten here. A HEIC gets the sidecar every other
    program reads for it, and the position a phone recorded is left alone."""

    def setUp(self):
        super().setUp()
        self.shoot = os.path.join(self.dir, "Phone")
        os.makedirs(self.shoot)
        self.bare = os.path.join(self.shoot, "IMG_0001.HEIC")
        self.placed = os.path.join(self.shoot, "IMG_0002.HEIC")
        shutil.copy(fx("plain.heic"), self.bare)
        shutil.copy(fx("phone_doha.heic"), self.placed)

    def test_a_pin_goes_into_a_sidecar_and_the_file_is_untouched(self):
        before = _bytes(self.bare)
        t = R.get("pin")
        p = t.make_plan({"folder": self.shoot, "link": "24.4672, 39.6112"})
        self.assertEqual([r.name for r in p.rows], ["IMG_0001.HEIC"])
        r = t.apply(p)
        self.assertEqual(r.failed, 0, r.details)
        self.assertEqual(_bytes(self.bare), before)
        self.assertTrue(sc.read(self.bare).get("exif:GPSLatitude"))

    def test_replacing_does_not_pretend_to_move_a_recorded_position(self):
        p = R.get("pin").make_plan({"folder": self.shoot,
                                    "link": "24.4672, 39.6112", "replace": "on"})
        self.assertNotIn("IMG_0002.HEIC", [r.name for r in p.rows])
        self.assertIn("inside the file", dict(p.skipped)[self.placed])

    def test_geotag_skips_the_one_the_phone_already_placed(self):
        ref = os.path.join(self.dir, "Reference")
        os.makedirs(ref)
        shutil.copy(fx("phone_doha.jpg"), os.path.join(ref, "r.JPG"))
        p = R.get("geotag").make_plan({"folder": self.shoot, "phone": ref,
                                       "order": "photos_only", "max_gap": 100000})
        self.assertEqual(dict(p.skipped)[self.placed], "already has a location")

    def test_removing_a_location_names_the_one_it_cannot_take_out(self):
        S.save({"library": self.dir})
        p = R.get("unlocate").make_plan({"folder": self.shoot})
        self.assertIn("inside the file", dict(p.skipped)[self.placed])
        self.assertEqual(p.rows, [])


if __name__ == "__main__":
    unittest.main()
