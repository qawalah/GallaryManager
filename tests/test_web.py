"""The page's files live in app/web, and the Python only reads and joins them.

What could go wrong with that split, and is checked here: a piece left out of
the join, pieces joined in the wrong order, a slot filled twice, and a change
to a stylesheet that the header's CODE stamp does not notice - which would make
a Restart after a UI-only change look exactly like one that did not take.
"""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import web                                # noqa: E402
from app import libraryui as L                     # noqa: E402
from app import page as P                          # noqa: E402
from app import version                            # noqa: E402


class TheJoin(unittest.TestCase):
    def test_every_library_piece_is_in_the_page_in_name_order(self):
        for folder, joined in (("library/js", L.SCRIPT), ("library/css", L.STYLE),
                               ("library/icons", L.ICONS)):
            where = os.path.join(web.HERE, *folder.split("/"))
            names = sorted(os.listdir(where))
            self.assertTrue(names, folder)
            at = 0
            for name in names:
                piece = web.read(f"{folder}/{name}")
                found = joined.find(piece, at)
                self.assertEqual(found, at, f"{folder}/{name} is missing or out of order")
                at += len(piece)
            self.assertEqual(at, len(joined))

    def test_the_page_has_no_slot_left_unfilled(self):
        self.assertNotRegex(P.PAGE.split("<style>")[0], r"\{\{[A-Z_]+\}\}")
        self.assertIn(P.STYLE, P.PAGE)
        self.assertIn(P.SCRIPT, P.PAGE)

    def test_a_slot_inside_what_is_put_in_is_left_alone(self):
        out = web.fill("<a>{{ONE}}</a><b>{{TWO}}</b>", ONE="{{TWO}}", TWO="2")
        self.assertEqual(out, "<a>{{TWO}}</a><b>2</b>")


class OnePagePerTool(unittest.TestCase):
    """Each tool is a page of its own: no tab row naming its relatives, and
    the rest of its group listed beside it from FAMILIES, the arrangement the
    rail and All tools draw. Checked in the source here, and in a browser by
    test_page_behaviour when there is one."""

    def test_no_tab_row_is_drawn_on_a_tool(self):
        for source in (P.SCRIPT, L.SCRIPT):
            self.assertNotIn('class="tabs', source)
            self.assertNotIn("subtabs", source)

    def test_the_list_beside_it_is_read_from_the_arrangement(self):
        piece = web.read("library/js/22-tool-side.js")
        self.assertIn("FAMILIES", piece)
        self.assertIn("SETFAM", piece)
        self.assertIn('id="toolside"', P.PAGE)


class TheCodeStamp(unittest.TestCase):
    def test_a_stylesheet_counts_as_code(self):
        with tempfile.TemporaryDirectory() as d:
            py = os.path.join(d, "a.py")
            css = os.path.join(d, "web", "b.css")
            os.makedirs(os.path.dirname(css))
            for path in (py, css):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("x")
            old = time.time() - 3600
            os.utime(py, (old, old))
            self.assertGreater(version._newest(d), old + 1)


if __name__ == "__main__":
    unittest.main()
