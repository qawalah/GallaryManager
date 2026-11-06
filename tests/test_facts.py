"""Reading a photograph once, and not at all the second time.

Sending a library out to develop took half an hour, and almost none of it was
work. Each photograph was opened four separate times - once for its rating, once
for its clock and camera, once for its keywords, once for its colour - and each
of those looks in the sidecar first, so a rated RAW cost eight opens. Multiply
by a hundred thousand files over a network share.

Two things are tested here, and they are separate claims:

**Every fact out of one read.** They come from the same two places, so asking
for all four costs one open between them.

**One read per file, ever, until that file changes.** The answer is kept against
a signature of the file itself, so the second pass costs one stat.

The second claim is only safe if the signature cannot miss a change, and there
are two ways it could. A sidecar rewritten in place by Lightroom does not touch
the photograph at all - so the sidecar is in the signature. And this app's OWN
writes restore the file's date to the nanosecond, deliberately, so that rating a
photograph does not look like an edit to every backup tool in the house - so the
inode is in the signature too, because `os.replace` is the one thing that cannot
preserve it. Both have a test that would pass if the field were quietly dropped
and does not.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import facts                        # noqa: E402
from core import meter                        # noqa: E402
from core.exifwrite import write_rating       # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Facts(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="facts-")
        self.store = os.path.join(self.dir, "facts.json")
        self.photo = os.path.join(self.dir, "rated.JPG")
        shutil.copy(os.path.join(FIX, "rated.jpg"), self.photo)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def side(self, stars=2):
        path = os.path.splitext(self.photo)[0] + ".xmp"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
                     'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                     '<rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
                     f'xmp:Rating="{stars}"/></rdf:RDF></x:xmpmeta>')
        return path

    # ------------------------------------------------------- one read per run

    def test_asking_twice_in_one_run_opens_the_file_once(self):
        r = facts.Reader()
        self.assertEqual(r.stars(self.photo), 4)
        self.assertEqual(r.stars(self.photo), 4)
        self.assertEqual(r.read, 1)
        self.assertEqual(r.reused, 1)

    def test_all_four_facts_cost_one_open_between_them(self):
        """They come out of the same two places, so asking four questions of a
        photograph should not be four trips to the disk. Counted in files
        actually opened, not in calls."""
        r = facts.Reader()
        before = meter.snapshot()
        r.stars(self.photo); r.capture(self.photo)
        r.tags(self.photo); r.colour(self.photo)
        self.assertEqual(meter.since(before)["own_files"], 1)

    def test_and_asking_the_same_one_twice_does_not_read_at_all(self):
        r = facts.Reader()
        r.stars(self.photo); r.capture(self.photo)
        before = meter.snapshot()
        r.stars(self.photo); r.capture(self.photo)
        self.assertEqual(meter.since(before)["own_files"], 0)
        self.assertEqual(r.reused, 2)

    def test_it_counts_what_it_actually_read_off_the_disk(self):
        """The number Abu's container could not get from the kernel."""
        before = meter.snapshot()
        facts.Reader().capture(self.photo)
        after = meter.since(before)
        self.assertGreaterEqual(after["own_files"], 1)
        self.assertGreater(after["own_bytes"], 0)

    # ------------------------------------------------- and none the next time

    def test_the_second_run_does_not_open_it_at_all(self):
        first = facts.Reader(self.store)
        first.stars(self.photo); first.capture(self.photo)
        first.save()
        second = facts.Reader(self.store)
        self.assertEqual(second.stars(self.photo), 4)
        self.assertEqual(second.capture(self.photo).taken,
                         first.capture(self.photo).taken)
        self.assertEqual(second.read, 0, "it opened the file again")

    def test_a_file_that_changed_is_read_again(self):
        first = facts.Reader(self.store)
        first.stars(self.photo)
        first.save()
        with open(self.photo, "ab") as fh:
            fh.write(b"\x00")
        again = facts.Reader(self.store)
        again.stars(self.photo)
        self.assertEqual(again.read, 1)

    def test_a_file_that_cannot_be_stat_is_read_rather_than_guessed_at(self):
        r = facts.Reader(self.store)
        r.stars(self.photo)
        r.save()
        gone = os.path.join(self.dir, "never.JPG")
        self.assertEqual(facts.signature(gone), "")

    # ------------------------------------------- the two ways it could go bad

    def test_a_sidecar_written_beside_it_is_noticed(self):
        """Lightroom rates a RAW by rewriting the .xmp and never touching the
        negative. A signature made of the photograph alone would serve last
        week's rating for ever, and nothing would say so."""
        first = facts.Reader(self.store)
        self.assertEqual(first.stars(self.photo), 4)
        first.save()
        self.side(2)
        again = facts.Reader(self.store)
        self.assertEqual(again.stars(self.photo), 2)

    def test_and_so_is_a_sidecar_rewritten_in_place(self):
        side = self.side(2)
        first = facts.Reader(self.store)
        self.assertEqual(first.stars(self.photo), 2)
        first.save()
        # same length, a different rating, as a hurried second would produce
        with open(side, "r", encoding="utf-8") as fh:
            text = fh.read()
        with open(side, "w", encoding="utf-8") as fh:
            fh.write(text.replace('xmp:Rating="2"', 'xmp:Rating="5"'))
        again = facts.Reader(self.store)
        self.assertEqual(again.stars(self.photo), 5)

    def test_our_own_rating_write_is_noticed_although_it_puts_the_date_back(self):
        """The trap this app sets for itself. Every metadata write here is
        "write a temp file, then os.replace", and it then restores the original
        date on purpose so that rating a photograph does not read as an edit to
        every backup tool in the house. Same size, same nanosecond - and a cache
        keyed on those two would be wrong for ever, silently."""
        first = facts.Reader(self.store)
        self.assertEqual(first.stars(self.photo), 4)
        first.save()
        was = os.stat(self.photo)
        write_rating(self.photo, 1)
        now = os.stat(self.photo)
        # the premise, asserted rather than assumed
        self.assertEqual(was.st_size, now.st_size)
        self.assertEqual(was.st_mtime_ns, now.st_mtime_ns)
        again = facts.Reader(self.store)
        self.assertEqual(again.stars(self.photo), 1,
                         "it served the rating from before the write")

    def test_the_signature_moves_when_the_file_is_replaced(self):
        was = facts.signature(self.photo)
        write_rating(self.photo, 1)
        self.assertNotEqual(was, facts.signature(self.photo))

    def test_a_jpeg_noted_before_its_packet_rating_was_read_is_read_again(self):
        """Lightroom rates in the photo's own packet, and until 3.12.2 that
        was read as unrated. A note from then must not go on saying so."""
        st = os.stat(self.photo)
        self.assertNotEqual(facts.signature(self.photo),
                            f"{st.st_size}:{st.st_mtime_ns}:{st.st_ino}")

    # -------------------------------------------------------------- the store

    def test_a_note_nothing_has_asked_about_for_months_is_dropped(self):
        r = facts.Reader(self.store)
        r.stars(self.photo)
        r.entries["/somewhere/old.jpg"] = {
            "sig": "1:2:3", "stars": 5,
            "t": time.time() - (facts.KEEP_DAYS + 2) * 86400}
        r._dirty = True
        r.save()
        back = facts.Reader(self.store)
        self.assertIn(self.photo, back.entries)
        self.assertNotIn("/somewhere/old.jpg", back.entries)

    def test_but_one_this_run_never_looked_at_survives(self):
        """The store is shared: syncing ratings walks the previews tree and
        sending to develop walks the develop tree. If each dropped what the
        other had cached, both would pay full price every pass while appearing
        to have a cache."""
        other = os.path.join(self.dir, "elsewhere.JPG")
        shutil.copy(os.path.join(FIX, "plain.jpg"), other)
        one = facts.Reader(self.store)
        one.stars(other)
        one.save()
        two = facts.Reader(self.store)
        two.stars(self.photo)
        two.save()
        back = facts.Reader(self.store)
        self.assertIn(other, back.entries)
        self.assertIn(self.photo, back.entries)

    def test_a_store_written_by_an_older_version_is_thrown_away_not_trusted(self):
        with open(self.store, "w", encoding="utf-8") as fh:
            fh.write('{"v": 0, "files": {"' + self.photo + '": '
                     '{"sig": "x", "stars": 5}}}')
        r = facts.Reader(self.store)
        self.assertEqual(r.stars(self.photo), 4)

    def test_a_damaged_store_costs_the_cache_and_not_the_run(self):
        with open(self.store, "w", encoding="utf-8") as fh:
            fh.write("{not json at all")
        r = facts.Reader(self.store)
        self.assertEqual(r.stars(self.photo), 4)

    def test_nowhere_to_keep_it_is_still_a_working_reader(self):
        r = facts.Reader("")
        self.assertEqual(r.stars(self.photo), 4)
        self.assertFalse(r.save())

    def test_forget_drops_what_is_known_about_a_file_just_written(self):
        r = facts.Reader(self.store)
        r.stars(self.photo)
        r.forget(self.photo)
        self.assertNotIn(self.photo, r.entries)

    def test_it_says_how_much_it_saved(self):
        r = facts.Reader(self.store)
        r.stars(self.photo)
        r.save()
        again = facts.Reader(self.store)
        again.stars(self.photo)
        self.assertIn("already known", again.said())


class OneStorePerProcess(unittest.TestCase):
    """Every task's reader shares one set of notes, read once and written once.

    Before, each task read facts.json when it began and wrote the whole of it
    back when it ended - so two runs in two threads each saved their own copy
    over the other's, and a flow of five tasks wrote the file five times.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="facts-shared-")
        self.store = os.path.join(self.dir, "facts.json")
        self.photos = []
        for n in range(40):
            p = os.path.join(self.dir, f"DSC{n:04}.JPG")
            shutil.copy(os.path.join(FIX, "rated.jpg"), p)
            self.photos.append(p)

    def tearDown(self):
        facts.flush()
        shutil.rmtree(self.dir, ignore_errors=True)

    def on_disk(self) -> dict:
        import json
        with open(self.store, encoding="utf-8") as fh:
            return json.load(fh)["files"]

    def test_readers_of_one_store_share_its_notes(self):
        one = facts.Reader(self.store)
        two = facts.Reader(self.store)
        self.assertIs(one.entries, two.entries)
        one.stars(self.photos[0])
        self.assertEqual(two.stars(self.photos[0]), 4)
        # the counts stay each caller's own
        self.assertEqual((one.read, one.reused), (1, 0))
        self.assertEqual((two.read, two.reused), (0, 1))

    def test_two_threads_reading_and_saving_at_once_lose_nothing(self):
        import threading
        halves = (self.photos[:20], self.photos[20:])
        failed = []

        def work(paths):
            try:
                r = facts.Reader(self.store)
                for p in paths:
                    r.stars(p)
                    r.capture(p)
                    r.save()
            except Exception as exc:                  # noqa: BLE001
                failed.append(exc)
        threads = [threading.Thread(target=work, args=(h,)) for h in halves]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(failed, [])
        facts.flush()
        written = self.on_disk()
        for p in self.photos:
            self.assertIn(p, written)
            self.assertEqual(written[p]["stars"], 4)
            self.assertIn("cap", written[p])

    def test_a_file_rewritten_between_two_asks_is_read_again(self):
        r = facts.Reader(self.store)
        self.assertEqual(r.stars(self.photos[0]), 4)
        write_rating(self.photos[0], 2)
        self.assertEqual(r.stars(self.photos[0]), 2)
        self.assertEqual(r.read, 2)

    def test_the_file_is_written_once_per_run_not_once_per_caller(self):
        shared = facts.Reader(self.store)._shared
        for p in self.photos[:5]:
            caller = facts.Reader(self.store)
            caller.stars(p)
            self.assertTrue(caller.save())
        self.assertEqual(shared.writes, 0, "a caller's save wrote at once")
        self.assertFalse(os.path.exists(self.store))
        facts.flush()                                # the end of the run
        self.assertEqual(shared.writes, 1)
        self.assertEqual(len(self.on_disk()), 5)
        self.assertFalse(facts.flush(), "nothing new, nothing to write")
        self.assertEqual(shared.writes, 1)

    def test_and_without_a_flush_the_timer_writes_it(self):
        was = facts.SAVE_AFTER
        facts.SAVE_AFTER = 0.05
        try:
            r = facts.Reader(self.store)
            r.stars(self.photos[0])
            r.save()
            until = time.time() + 5
            while not os.path.exists(self.store) and time.time() < until:
                time.sleep(0.02)
        finally:
            facts.SAVE_AFTER = was
        self.assertIn(self.photos[0], self.on_disk())
        self.assertEqual(r._shared.writes, 1)

    def test_the_store_file_is_read_once_per_process(self):
        r = facts.Reader(self.store)
        r.stars(self.photos[0])
        facts.flush()
        opened = []
        import builtins
        real = builtins.open

        def counting(path, *a, **k):
            if os.fspath(path) == self.store:
                opened.append(path)
            return real(path, *a, **k)
        builtins.open = counting
        try:
            for _ in range(3):
                again = facts.Reader(self.store)
                again.stars(self.photos[0])
        finally:
            builtins.open = real
        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()


class SecondPassIsFree(unittest.TestCase):
    """The claim Abu is owed a number for: thirty minutes, then seconds.

    Not a micro-benchmark - a count. Two passes of Send to develop over the same
    unchanged library, counting the files this app opened each time. The second
    one must open almost none of them, because nothing moved.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="twice-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos", "2022", "Spain")
        self.dev = os.path.join(self.dir, "Develop")
        os.makedirs(self.lib)
        os.makedirs(self.dev)
        for n in range(12):
            shutil.copy(os.path.join(FIX, "rated.jpg"),
                        os.path.join(self.lib, f"DSC{n:04}.JPG"))
        from core import settings as S
        S.save({"library": os.path.join(self.dir, "Photos"),
                "develop": self.dev})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def opened(self, fn):
        before = meter.snapshot()["own_files"]
        out = fn()
        return out, meter.snapshot()["own_files"] - before

    def test_the_second_look_at_an_unchanged_library_opens_almost_nothing(self):
        from app import registry as R
        import app.tasks                              # noqa: F401
        task = R.get("develop")
        opts = {"folder": os.path.join(self.dir, "Photos"),
                "develop": self.dev, "raw": "", "mirror": False,
                "library": os.path.join(self.dir, "Photos"),
                "jpeg_at_or_above": 1, "raw_at_or_above": -1}
        first, one = self.opened(lambda: task.make_plan(dict(opts)))
        second, two = self.opened(lambda: task.make_plan(dict(opts)))
        self.assertEqual(len(first.rows), len(second.rows),
                         "the two passes disagreed about what to do")
        self.assertGreaterEqual(one, 12, "the first pass did not read them")
        self.assertLess(two, one / 3,
                        f"the second pass still opened {two} of {one} files")

    def test_and_a_photograph_that_was_re_rated_is_read_again(self):
        """The cache must not be the reason a change is missed - which is the
        only way it could cost anything rather than save it."""
        from app import registry as R
        import app.tasks                              # noqa: F401
        from core.exifwrite import write_rating
        task = R.get("develop")
        opts = {"folder": os.path.join(self.dir, "Photos"),
                "develop": self.dev, "raw": "", "mirror": False,
                "library": os.path.join(self.dir, "Photos"),
                "jpeg_at_or_above": 5, "raw_at_or_above": -1}
        first = task.make_plan(dict(opts))
        self.assertEqual(len(first.rows), 0)         # all four-star, none sent
        write_rating(os.path.join(self.lib, "DSC0003.JPG"), 5)
        again = task.make_plan(dict(opts))
        self.assertEqual(len(again.rows), 1,
                         "a re-rated photograph was answered from the cache")
