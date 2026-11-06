"""The develop loop: out to the tablet, back again, and never twice.

    Send to develop  ->  Lightroom on the tablet  ->  File developed

Three things make it work, and each of them is a way it could quietly go wrong:

- **Per-kind thresholds.** A negative is fifty megabytes; a four-star shot is
  worth a look but not that. Send everything and the tablet fills up.
- **A memory.** A developed photo and an undeveloped one look identical in the
  library, so this cannot be measured - it has to be written down. Without it
  every run copies the same photos out again forever and the folder never
  empties.
- **Identity, not paths.** Lightroom writes every export into one flat folder,
  so an export has no path to file it by; and the memory is keyed the same way,
  so renaming a shoot does not send it all round again.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from core import ledger, walk              # noqa: E402
from core import settings as S             # noqa: E402
from core.exifwrite import set_rating      # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Loop(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="develop-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.out = os.path.join(self.dir, "To Develop")
        self.inbox = os.path.join(self.dir, "Lightroom")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        os.makedirs(os.path.join(self.raw, "2022", "Spain"))
        os.makedirs(self.inbox)
        for name, stars in (("plain", 5), ("rated", 4), ("aeb1", 2), ("aeb2", 0)):
            jpeg = os.path.join(self.shoot, name + ".JPG")
            shutil.copy(os.path.join(FIX, name + ".jpg"), jpeg)
            shutil.copy(os.path.join(FIX, name + ".jpg"),
                        os.path.join(self.raw, "2022", "Spain", name + ".RW2"))
            if stars:
                set_rating(jpeg, stars)
        S.save({"library": self.lib, "raw": self.raw, "develop": self.out,
                "inbox": self.inbox})

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
        return t, p

    def file_back(self, **over):
        t = R.get("filed")
        p = t.make_plan({"inbox": self.inbox, "folder": self.lib, **over})
        self.assertFalse(p.blocked, p.blocked)
        return t, p

    def out_files(self):
        return sorted(os.path.basename(f) for f in walk.walk(self.out).files)

    def export(self, name="plain"):
        """What Lightroom writes: the same base name, in one flat folder."""
        shutil.copy(os.path.join(FIX, name + ".jpg"),
                    os.path.join(self.inbox, name + ".jpg"))


class WhatGoesOut(Loop):
    def test_the_negative_only_for_the_top_rating(self):
        _t, p = self.send()
        sent = {r.name for r in p.rows if r.what == "send"}
        self.assertEqual(sent, {"plain.JPG", "plain.RW2", "rated.JPG"})

    def test_the_thresholds_are_separate_and_can_each_say_never(self):
        _t, p = self.send(raw_at_or_above=-1)
        self.assertFalse(any(r.name.endswith(".RW2") for r in p.rows))
        _t, p = self.send(jpeg_at_or_above=-1, raw_at_or_above=5)
        self.assertEqual({r.name for r in p.rows if r.what == "send"}, {"plain.RW2"})

    def test_an_unrated_photo_is_never_sent(self):
        _t, p = self.send(jpeg_at_or_above=1)
        self.assertFalse(any(r.name.startswith("aeb2") for r in p.rows))

    def test_it_keeps_the_librarys_shape(self):
        t, p = self.send()
        t.apply(p)
        self.assertTrue(os.path.isfile(
            os.path.join(self.out, "2022", "Spain", "plain.RW2")))

    def test_nothing_is_moved_out_of_the_library(self):
        """A working set, not a migration. A tablet that is lost or wiped must
        cost nothing."""
        before = sorted(walk.walk(self.lib).files)
        t, p = self.send()
        t.apply(p)
        self.assertEqual(sorted(walk.walk(self.lib).files), before)
        self.assertTrue(os.path.isfile(
            os.path.join(self.raw, "2022", "Spain", "plain.RW2")))

    def test_running_it_twice_sends_nothing_the_second_time(self):
        t, p = self.send()
        t.apply(p)
        was = self.out_files()
        _t2, p2 = self.send()
        self.assertEqual([r for r in p2.rows], [])
        self.assertEqual(self.out_files(), was)


class NotReadingTheWholeLibrary(Loop):
    """Filing five exports used to read the EXIF of every photograph in the
    library first - minutes of opening files over a share to answer a question
    about a handful of them.

    The narrowing is only sound because of one fact: EVERY tier of find_partner
    keys on the base name - full identity, then name and camera, then name, then
    name alone. A file whose name is not among the exports' can never be the
    answer to any of them. So these tests are in two halves: it really does read
    less, and the answer really is the same.
    """

    def reads(self, **over):
        """(what it planned, which files it opened).

        Three modules took their own reference to `read_capture` at import time,
        so all three have to be stood in for or the count is of whichever one
        happens to be called today - which would quietly stop testing anything.
        `core.facts` is the newest of them and is now the one that does the
        actual reading.
        """
        from core import facts, pairs, photo
        real = photo.read_capture
        opened = []
        spy = lambda p: (opened.append(p), real(p))[1]      # noqa: E731
        was = (pairs.read_capture, facts.read_capture)
        photo.read_capture = pairs.read_capture = facts.read_capture = spy
        try:
            _t, plan = self.file_back(**over)
        finally:
            photo.read_capture = real
            pairs.read_capture, facts.read_capture = was
        return plan, opened

    def test_it_does_not_open_photographs_that_cannot_be_the_answer(self):
        for n in ("plain", "rated", "aeb1", "aeb2", "aeb3", "burst1"):
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(self.shoot, n + ".JPG"))
        self.export("plain")
        _plan, opened = self.reads()
        from core.pairs import base_name
        self.assertTrue(opened, "it read nothing at all, which cannot be right")
        self.assertEqual({base_name(o) for o in opened}, {"plain"},
                         "it opened files whose name could never match")

    def test_and_the_answer_is_the_same_as_reading_everything(self):
        """The whole justification, checked rather than argued."""
        for n in ("plain", "rated", "aeb1"):
            shutil.copy(os.path.join(FIX, n + ".jpg"),
                        os.path.join(self.shoot, n + ".JPG"))
        for n in ("plain", "rated"):
            self.export(n)
        _t, narrowed = self.file_back()

        from core import pairs
        real = pairs.build_index
        pairs.build_index = lambda paths, want=("jpeg", "image"), progress=None, \
            names=None, reader=None: real(paths, want, progress, None, reader)
        import app.tasks.filed as F
        F.build_index = pairs.build_index
        try:
            _t2, everything = self.file_back()
        finally:
            pairs.build_index = real
            F.build_index = real
        self.assertEqual([(r.source, r.target) for r in narrowed.rows],
                         [(r.source, r.target) for r in everything.rows])
        self.assertEqual(narrowed.skipped, everything.skipped)

    def test_an_export_nothing_matches_is_still_reported(self):
        """The case narrowing could plausibly break: no candidate means no file
        is opened at all, and "nothing was read" must not become "nothing to
        say"."""
        shutil.copy(os.path.join(FIX, "phone_doha.jpg"),
                    os.path.join(self.inbox, "stranger.jpg"))
        plan, _opened = self.reads()
        self.assertEqual(plan.rows, [])
        self.assertTrue(any("nothing in the library matches" in why
                            for _n, why in plan.skipped))


class ComingBack(Loop):
    def test_an_export_is_filed_beside_the_photo_it_came_from(self):
        self.export("plain")
        t, p = self.file_back()
        self.assertEqual(len(p.rows), 1)
        self.assertEqual(p.rows[0].target,
                         os.path.join(self.shoot, "Developed", "plain.jpg"))
        self.assertEqual(t.apply(p).failed, 0)
        self.assertTrue(os.path.isfile(
            os.path.join(self.shoot, "Developed", "plain.jpg")))
        self.assertFalse(os.listdir(self.inbox))          # ready for the next round

    def test_the_export_folder_is_never_scanned_as_originals(self):
        """An export has its original's name, capture time and camera. Left
        anywhere the app walks, it is counted as a second photograph, judged as
        a duplicate, and paired against the RAW."""
        self.export("plain")
        t, p = self.file_back()
        t.apply(p)
        found = [os.path.basename(f) for f in walk.walk(self.lib).files]
        self.assertNotIn("plain.jpg", found)              # the export
        self.assertIn("plain.JPG", found)                 # the original

    def test_the_same_export_arriving_again_is_not_filed_twice(self):
        """The export folder is a ONE-WAY sync: the tablet keeps its copy, so
        moving the file out here can have it pushed back on the next sync. Filed
        again it lands beside the first as "plain (1).jpg", and a week of that
        is a folder of numbered copies of one photograph."""
        self.export("plain")
        t, p = self.file_back()
        t.apply(p)
        self.export("plain")                       # the sync puts it back
        t2, p2 = self.file_back()
        self.assertTrue(all(r.data.get("drop") for r in p2.rows), p2.rows)
        t2.apply(p2)
        self.assertEqual(os.listdir(os.path.join(self.shoot, "Developed")),
                         ["plain.jpg"])
        self.assertFalse(os.listdir(self.inbox))

    def test_and_can_be_left_alone_instead_of_taken_out(self):
        self.export("plain")
        t, p = self.file_back()
        t.apply(p)
        self.export("plain")
        _t2, p2 = self.file_back(tidy_resync=False)
        self.assertEqual(p2.rows, [])
        self.assertTrue(any("already filed" in why for _n, why in p2.skipped))

    def test_but_a_photo_exported_again_after_more_work_does_land(self):
        """Same name, different bytes - that is you, not the sync. Both are
        kept, and the plan says so rather than showing one name and writing
        another."""
        self.export("plain")
        t, p = self.file_back()
        t.apply(p)
        self.export("plain")
        with open(os.path.join(self.inbox, "plain.jpg"), "ab") as fh:
            fh.write(b"\x00" * 64)                 # a different export
        t2, p2 = self.file_back()
        self.assertEqual(len(p2.rows), 1)
        self.assertFalse(p2.rows[0].data.get("drop"))
        self.assertIn("numbered name", p2.rows[0].detail)
        t2.apply(p2)
        self.assertEqual(sorted(os.listdir(os.path.join(self.shoot, "Developed"))),
                         ["plain.jpg", "plain_1.jpg"])

    def test_the_folder_they_land_in_can_be_called_anything(self):
        self.export("plain")
        _t, p = self.file_back(subfolder="Curated")
        self.assertEqual(p.rows[0].target,
                         os.path.join(self.shoot, "Curated", "plain.jpg"))

    def test_and_whatever_it_is_called_is_left_out_of_the_scanning(self):
        """The one that matters when the name is changed. An export has its
        original's name, time and camera: a folder of them scanned as part of
        the library is a second copy of every photograph in that shoot - counted
        twice, paired against the same RAW, called a duplicate of its own
        original, and sent out to develop again."""
        from core import settings as CS
        CS.save({"filed_into": "Curated"})
        self.export("plain")
        t, p = self.file_back(subfolder="Curated")
        t.apply(p)
        found = [os.path.basename(f) for f in walk.walk(self.lib).files]
        self.assertNotIn("plain.jpg", found)              # the export
        self.assertIn("plain.JPG", found)                 # the original

    def test_an_export_matching_nothing_is_left_where_it_is_and_named(self):
        """A photograph filed in a plausible folder is a photograph you will not
        find again."""
        shutil.copy(os.path.join(FIX, "phone_doha.jpg"),
                    os.path.join(self.inbox, "stranger.jpg"))
        t, p = self.file_back()
        self.assertEqual(p.rows, [])
        self.assertTrue(any("nothing in the library matches" in why
                            for _n, why in p.skipped))
        t.apply(p)
        self.assertTrue(os.path.isfile(os.path.join(self.inbox, "stranger.jpg")))

    def test_it_can_file_beside_the_original_if_you_insist(self):
        self.export("plain")
        _t, p = self.file_back(where="beside")
        self.assertEqual(p.rows[0].target, os.path.join(self.shoot, "plain.jpg"))
        self.assertTrue(any("duplicates" in n for n in p.notes))

    def test_the_exports_folder_inside_the_library_is_refused(self):
        inside = os.path.join(self.lib, "Lightroom")
        os.makedirs(inside)
        t = R.get("filed")
        p = t.make_plan({"inbox": inside, "folder": self.lib})
        self.assertTrue(p.blocked)
        self.assertIn("read as an original", p.blocked)


class TheMemory(Loop):
    def develop_one(self, name="plain"):
        self.export(name)
        t, p = self.file_back()
        t.apply(p)

    def test_filing_an_export_records_it_as_developed(self):
        self.develop_one()
        self.assertEqual(len(ledger.read()), 1)

    def test_and_it_is_then_taken_off_the_tablet(self):
        t, p = self.send()
        t.apply(p)
        self.assertIn("plain.RW2", self.out_files())

        self.develop_one()
        t2, p2 = self.send()
        taken = {r.name for r in p2.rows if r.what == "take back"}
        self.assertEqual(taken, {"plain.JPG", "plain.RW2"})
        t2.apply(p2)
        self.assertNotIn("plain.RW2", self.out_files())
        self.assertIn("rated.JPG", self.out_files())      # still waiting

    def test_and_never_sent_out_again(self):
        self.develop_one()
        _t, p = self.send()
        self.assertFalse(any(r.what == "send" and r.name.startswith("plain")
                             for r in p.rows))
        self.assertTrue(any("developed already" in why for _n, why in p.skipped))

    def test_it_is_remembered_by_identity_so_a_rename_does_not_undo_it(self):
        """Renaming a shoot is a thing this app actively encourages. By path,
        every finished photo would come round again - silently."""
        self.develop_one()
        moved = os.path.join(self.lib, "2022", "Spain 2022")
        os.rename(self.shoot, moved)
        _t, p = self.send()
        self.assertFalse(any(r.what == "send" and r.name.startswith("plain")
                             for r in p.rows))

    def test_filing_is_recorded_so_history_can_put_it_back(self):
        from core import moves
        self.export("plain")
        t, p = self.file_back()
        result = t.apply(p)
        self.assertEqual(len(result.moves), 1)
        good, refused = moves.can_put_back(result.moves)
        self.assertEqual((len(good), refused), (1, []))
        moves.put_back(result.moves)
        self.assertTrue(os.path.isfile(os.path.join(self.inbox, "plain.jpg")))

    def test_a_failed_move_is_not_recorded_as_developed(self):
        """Marking a photo done when its export never landed takes it off the
        tablet with the work not done."""
        self.export("plain")
        t, p = self.file_back()
        os.remove(p.rows[0].data["from"])              # it vanishes before applying
        r = t.apply(p)
        self.assertEqual(r.failed, 1)
        self.assertEqual(ledger.read(), {})

    def test_it_can_be_taken_back_so_a_photo_can_be_developed_again(self):
        self.develop_one()
        keys = list(ledger.read())
        self.assertEqual(ledger.forget(keys), 1)
        _t, p = self.send()
        self.assertTrue(any(r.what == "send" and r.name == "plain.RW2"
                            for r in p.rows))


class NotADuplicate(Loop):
    def test_the_develop_tree_is_left_out_of_find_duplicates(self):
        """Everything in it is a copy of something in the library on purpose -
        that is what it is for - so every one of them would be reported."""
        t, p = self.send()
        t.apply(p)
        both = R.get("duplicates").make_plan(
            {"folder": self.dir, "develop": self.out, "raw": self.raw})
        self.assertFalse(p.blocked, p.blocked)
        for row in both.rows:
            self.assertFalse(row.source.startswith(self.out), row.source)


class WhereItLives(Loop):
    def test_the_develop_tree_inside_the_library_is_refused(self):
        t = R.get("develop")
        p = t.make_plan({"folder": self.lib,
                         "develop": os.path.join(self.lib, "Develop"),
                         "mirror": False})
        self.assertTrue(p.blocked)
        self.assertIn("sent out again as an original", p.blocked)

    def test_both_trees_are_remembered_in_setup(self):
        saved = S.load()
        self.assertEqual(saved["develop"], self.out)
        self.assertEqual(saved["inbox"], self.inbox)

    def test_pruning_can_be_turned_off(self):
        t, p = self.send()
        t.apply(p)
        self.export("plain")
        t2, p2 = self.file_back()
        t2.apply(p2)
        _t3, p3 = self.send(prune=False)
        self.assertFalse(any(r.what == "take back" for r in p3.rows))


class TakingBackOnlyWhatWasAsked(Loop):
    """Take finished back is built from the same scope as what is sent. A run
    on one shoot, or on one colour, used to take every other shoot and colour
    off the tablet - work in progress, removed without a record."""

    def setUp(self):
        super().setUp()
        self.doha = os.path.join(self.lib, "2023", "Doha")
        os.makedirs(self.doha)
        jpeg = os.path.join(self.doha, "doha.JPG")
        shutil.copy(os.path.join(FIX, "plain.jpg"), jpeg)
        set_rating(jpeg, 5)
        t, p = self.send(raw_at_or_above=-1)
        t.apply(p)
        self.assertIn("doha.JPG", self.out_files())

    def test_a_run_on_one_shoot_leaves_the_other_shoots_copies(self):
        _t, p = self.send(folder=self.shoot, raw_at_or_above=-1)
        self.assertEqual([r.source for r in p.rows if r.what == "take back"], [])

    def test_a_run_on_one_colour_leaves_the_other_colours_copies(self):
        _t, p = self.send(colour="red", raw_at_or_above=-1)
        self.assertEqual([r.source for r in p.rows if r.what == "take back"], [])

    def test_and_the_other_shoots_files_survive_the_apply(self):
        t, p = self.send(folder=self.shoot, raw_at_or_above=-1)
        t.apply(p)
        self.assertTrue(os.path.isfile(
            os.path.join(self.out, "2023", "Doha", "doha.JPG")))

    def test_a_finished_one_in_the_scanned_shoot_still_goes(self):
        set_rating(os.path.join(self.shoot, "rated.JPG"), 1)
        _t, p = self.send(folder=self.shoot, raw_at_or_above=-1)
        self.assertEqual({r.name for r in p.rows if r.what == "take back"},
                         {"rated.JPG"})


class TheButtonSaysWhatHappens(Loop):
    """It said "Copy 7 photographs" when all seven rows were files being taken
    back off the tablet."""

    def test_sending_is_a_copy_of_files(self):
        t, p = self.send()
        got = R.impact_of(t, p)
        self.assertEqual((got["verb"], got["count"], got["unit"]),
                         ("Copy", 3, "files"))

    def test_taking_back_alone_says_take_back(self):
        t, p = self.send()
        t.apply(p)
        set_rating(os.path.join(self.shoot, "rated.JPG"), 0)
        t, p = self.send()
        self.assertEqual({r.what for r in p.rows}, {"take back"})
        got = R.impact_of(t, p)
        self.assertEqual((got["verb"], got["count"]), ("Take back", 1))
        self.assertEqual(got["into"], [])

    def filed_and_pushed_back(self):
        """plain is filed, then the tablet's one-way sync puts it back."""
        self.export("plain")
        t, p = self.file_back()
        t.apply(p)
        self.export("plain")

    def test_filing_counts_only_what_is_filed(self):
        """A copy the sync brought back is taken out of the export folder,
        not filed, and the button said File for those too."""
        self.filed_and_pushed_back()
        self.export("rated")
        t, p = self.file_back()
        self.assertEqual(sorted(r.what for r in p.rows), ["already filed", "file"])
        got = R.impact_of(t, p)
        self.assertEqual((got["verb"], got["count"]), ("File", 1))

    def test_only_copies_coming_back_say_take_out(self):
        self.filed_and_pushed_back()
        t, p = self.file_back()
        self.assertEqual([r.what for r in p.rows], ["already filed"])
        got = R.impact_of(t, p)
        self.assertEqual((got["verb"], got["count"]), ("Take out", 1))

if __name__ == "__main__":
    unittest.main()


class SpottingItIsDone(Loop):
    """Done, noticed rather than told.

    The ledger used to learn a photo was developed only when File developed
    filed its export. An edit that reached the library any other way - exported
    from Lightroom on the PC straight into the shoot's Developed folder, filed
    by hand, filed before the ledger existed - left the photo on the tablet for
    ever, asking to be developed again, with the finished edit sitting right
    beside it.
    """

    def edit_by_hand(self, name="plain"):
        where = os.path.join(self.shoot, "Developed")
        os.makedirs(where, exist_ok=True)
        out = os.path.join(where, name + ".jpg")
        shutil.copy(os.path.join(FIX, name + ".jpg"), out)
        return out

    def test_an_edit_beside_it_is_counted_as_done(self):
        self.edit_by_hand()
        _t, p = self.send()
        self.assertTrue(any(r.what == "done" and r.name == "plain.JPG"
                            for r in p.rows))
        self.assertFalse(any(r.what == "send" and r.name == "plain.JPG"
                             for r in p.rows))

    def test_and_recorded_when_you_go_ahead_not_when_you_look(self):
        """A plan must not change what the next plan sees."""
        self.edit_by_hand()
        t, p = self.send()
        self.assertEqual(ledger.read(), {})
        t.apply(p)
        self.assertEqual(len(ledger.read()), 1)

    def test_and_taken_off_the_tablet_if_it_was_already_sent(self):
        t, p = self.send()
        t.apply(p)
        self.assertIn("plain.RW2", self.out_files())
        self.edit_by_hand()
        t2, p2 = self.send()
        t2.apply(p2)
        self.assertNotIn("plain.RW2", self.out_files())

    def test_but_not_a_photo_you_asked_to_develop_again(self):
        """That edit is the one you were unhappy with. Counting it as done
        would quietly undo your decision."""
        self.edit_by_hand()
        t, p = self.send()
        t.apply(p)
        ledger.forget(list(ledger.read()))
        _t, again = self.send()
        self.assertFalse(any(r.what == "done" for r in again.rows))
        self.assertTrue(any(r.what == "send" and r.name == "plain.JPG"
                            for r in again.rows))

    def test_it_can_be_switched_off(self):
        self.edit_by_hand()
        _t, p = self.send(spot_done=False)
        self.assertFalse(any(r.what == "done" for r in p.rows))
