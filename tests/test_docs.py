"""The documents a newcomer opens first say what this is.

The top-level README was, for its whole life, a one-line UTF-16 file from
another project ("# PoliceChaseClaude"). GitHub showed it as the front page,
and nothing on it pointed at the two install guides.
"""

import glob
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TheReadme(unittest.TestCase):
    def read(self, name):
        with open(os.path.join(ROOT, name), "rb") as fh:
            return fh.read()

    def test_it_is_utf8_and_names_photo_manager(self):
        raw = self.read("README.md")
        self.assertFalse(raw.startswith((b"\xff\xfe", b"\xfe\xff")),
                         "README.md is UTF-16")
        text = raw.decode("utf-8")
        self.assertTrue(text.startswith("# Photo Manager"), text[:60])

    def test_it_points_at_both_install_guides(self):
        text = self.read("README.md").decode("utf-8")
        for guide in ("nas/README.md", "windows/README.md"):
            self.assertIn(guide, text)
            self.assertTrue(os.path.isfile(os.path.join(ROOT, guide)), guide)

    def test_every_markdown_file_at_the_top_is_utf8(self):
        for path in glob.glob(os.path.join(ROOT, "*.md")):
            with self.subTest(path=os.path.basename(path)):
                with open(path, "rb") as fh:
                    fh.read().decode("utf-8")


if __name__ == "__main__":
    unittest.main()
