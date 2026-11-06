"""Tidying away the folders a run emptied, and nothing else.

Every feature that moves photographs ends by removing the folders it left
empty, and walks upward because emptying a shoot usually empties its year too.
That walk once had no top: a cull near a share root found the root holding only
`#recycle` and `@eaDir`, called them litter, and removed the share's Recycle
Bin with everything in it. These are the rules that stop it:

- the walk stops at the folder the task was run on, and at every Setup tree;
- the Recycle Bin and DSM's `@eaDir` are never litter, so a folder holding one
  is not empty;
- litter is files - Thumbs.db, .DS_Store - removed only from a folder that is
  otherwise empty, and never a tree.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import paths as P                 # noqa: E402
from core import settings as S              # noqa: E402


class Tidy(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="paths-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        S.forget()
        self.share = os.path.join(self.dir, "share")
        self.spain = os.path.join(self.share, "2022", "Spain")
        os.makedirs(self.spain)
        self.bin = os.path.join(self.share, "#recycle")
        os.makedirs(self.bin)
        with open(os.path.join(self.bin, "x.jpg"), "wb") as fh:
            fh.write(b"precious")
        os.makedirs(os.path.join(self.share, "@eaDir"))

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        S.forget()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_the_audit_tree_loses_the_shoot_and_the_year_and_nothing_else(self):
        removed = P.tidy_empty_folders({self.spain}, stop_at=self.share)
        self.assertEqual(removed, 2)
        self.assertFalse(os.path.exists(os.path.join(self.share, "2022")))
        self.assertTrue(os.path.isfile(os.path.join(self.bin, "x.jpg")))
        self.assertTrue(os.path.isdir(os.path.join(self.share, "@eaDir")))
        self.assertTrue(os.path.isdir(self.share))

    def test_a_recycle_bin_sibling_survives_even_without_a_boundary(self):
        """No stop given: the folder itself goes, nothing above it is looked at."""
        P.tidy_empty_folders({self.spain})
        self.assertFalse(os.path.exists(self.spain))
        self.assertTrue(os.path.isdir(os.path.join(self.share, "2022")))
        self.assertTrue(os.path.isfile(os.path.join(self.bin, "x.jpg")))

    def test_the_walk_stops_at_the_root_it_was_given(self):
        P.tidy_empty_folders({self.spain}, stop_at=os.path.join(self.share, "2022"))
        self.assertFalse(os.path.exists(self.spain))
        self.assertTrue(os.path.isdir(os.path.join(self.share, "2022")))

    def test_and_at_a_setup_tree_whatever_the_task_said(self):
        lib = os.path.join(self.share, "2022")
        S.save({"library": lib})
        S.forget()
        P.tidy_empty_folders({self.spain}, stop_at=self.share)
        self.assertTrue(os.path.isdir(lib))

    def test_a_root_holding_only_the_bin_and_eadir_is_never_removed(self):
        """The share root itself - the experiment that found the bug."""
        shutil.rmtree(os.path.join(self.share, "2022"))
        P.tidy_empty_folders({self.share}, stop_at=self.dir)
        self.assertTrue(os.path.isfile(os.path.join(self.bin, "x.jpg")))
        self.assertTrue(os.path.isdir(self.share))

    def test_an_emptied_recycle_bin_is_still_not_removed(self):
        """Undoing a Delete folder run empties the bin; DSM's bin stays."""
        os.remove(os.path.join(self.bin, "x.jpg"))
        P.tidy_empty_folders({self.bin}, stop_at=self.dir)
        self.assertTrue(os.path.isdir(self.bin))

    def test_a_folder_holding_an_eadir_is_not_empty(self):
        os.makedirs(os.path.join(self.spain, "@eaDir", "a.JPG"))
        P.tidy_empty_folders({self.spain}, stop_at=self.share)
        self.assertTrue(os.path.isdir(os.path.join(self.spain, "@eaDir")))

    def test_litter_files_go_only_from_a_folder_otherwise_empty(self):
        with open(os.path.join(self.spain, "Thumbs.db"), "wb") as fh:
            fh.write(b"x")
        with open(os.path.join(self.spain, ".DS_Store"), "wb") as fh:
            fh.write(b"x")
        P.tidy_empty_folders({self.spain}, stop_at=self.share)
        self.assertFalse(os.path.exists(self.spain))

    def test_a_litter_file_beside_a_photograph_stays(self):
        with open(os.path.join(self.spain, "Thumbs.db"), "wb") as fh:
            fh.write(b"x")
        with open(os.path.join(self.spain, "a.JPG"), "wb") as fh:
            fh.write(b"x")
        P.tidy_empty_folders({self.spain}, stop_at=self.share)
        self.assertTrue(os.path.isfile(os.path.join(self.spain, "Thumbs.db")))

    def test_a_folder_named_like_litter_is_never_removed_as_a_tree(self):
        """Litter is a file. A folder called .@__thumb holds something."""
        os.makedirs(os.path.join(self.spain, ".@__thumb"))
        with open(os.path.join(self.spain, ".@__thumb", "keep"), "wb") as fh:
            fh.write(b"x")
        P.tidy_empty_folders({self.spain}, stop_at=self.share)
        self.assertTrue(os.path.isfile(os.path.join(self.spain, ".@__thumb",
                                                    "keep")))

    def test_roots_of_reads_every_folder_option(self):
        got = P.roots_of({"folder": self.spain + "\n" + self.share,
                          "raw": "", "stars": 3, "into": "nowhere"})
        self.assertEqual(got, [self.spain, self.share])


if __name__ == "__main__":
    unittest.main()
