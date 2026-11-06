"""Walking a JPEG's header, and knowing when the walk was cut short.

The front of a file is read in a quarter megabyte, which covers EXIF with room
to spare. An XMP packet behind a big ICC profile is past that, and a walk that
ran out of buffer used to say "no packet" exactly as a walk that reached the
picture did. Every writer then built a fresh packet over the real one.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import jpegseg as J              # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
DEEP = os.path.join(FIX, "deep_xmp.jpg")


def whole(path):
    with open(path, "rb") as fh:
        return fh.read()


class CutShort(unittest.TestCase):
    def test_the_fixture_really_has_its_packet_past_the_first_read(self):
        text, complete = J.packet_in(whole(DEEP)[:J.HEADER_BYTES])
        self.assertEqual(text, "")
        self.assertFalse(complete)

    def test_a_whole_header_walk_says_it_was_complete(self):
        _segs, complete = J.walked(whole(os.path.join(FIX, "plain.jpg")))
        self.assertTrue(complete)

    def test_the_packet_is_found_by_reading_further(self):
        self.assertIn("crs:CropTop", J.xmp_packet(DEEP))

    def test_segments_still_yields_the_same_segments(self):
        buf = whole(os.path.join(FIX, "plain.jpg"))
        self.assertEqual([s.marker for s in J.segments(buf)],
                         [s.marker for s in J.walked(buf)[0]])

    def test_a_writer_refuses_rather_than_build_over_a_packet_it_cannot_see(self):
        """APP segments that run on past the end: a cut-off file, or one whose
        header is longer than anything that was read."""
        buf = whole(os.path.join(FIX, "plain.jpg"))
        cut = buf[:2] + b"\xff\xe2" + struct.pack(">H", 60000) + b"\0" * 100
        with self.assertRaises(ValueError):
            J.packet_to_edit(cut)

    def test_a_file_with_no_packet_is_simply_empty(self):
        self.assertEqual(J.packet_to_edit(whole(os.path.join(FIX, "plain.jpg"))), "")


if __name__ == "__main__":
    unittest.main()
