"""Thumbnails: how many are made at once, and the newest made before asking.

The gate was two at once on every machine. A two-core NAS and an eight-core PC
are not the same amount of room, so it is the machine's cores now, up to four.
"""

import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import thumbs as T                  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="thumbs-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        os.makedirs(self.lib)

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def photos(self, n):
        out = []
        for i in range(n):
            p = os.path.join(self.lib, f"DSC{i:04}.JPG")
            shutil.copy(os.path.join(FIX, "plain.jpg"), p)
            out.append(p)
        return out

    def kept(self):
        folder = os.path.join(self.dir, "config", T.FOLDER)
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


class TheGate(_Tmp):
    def test_it_is_as_wide_as_the_machine_up_to_four(self):
        self.assertEqual(T.GATE_WIDTH, max(1, min(4, os.cpu_count() or 1)))

    def test_that_many_are_made_at_once_and_no_more(self):
        lock = threading.Lock()
        now, most = [0], [0]

        def slow(path, size):
            with lock:
                now[0] += 1
                most[0] = max(most[0], now[0])
            time.sleep(0.25)
            with lock:
                now[0] -= 1
            return b"\xff\xd8 a picture"
        paths = self.photos(T.GATE_WIDTH + 3)
        with mock.patch.object(T, "_make", slow):
            threads = [threading.Thread(target=T.thumb, args=(p,)) for p in paths]
            for t in threads:
                t.start()
            for t in threads:
                t.join(10)
        self.assertEqual(most[0], T.GATE_WIDTH)


@unittest.skipUnless(T.have_pillow(), "making thumbnails needs Pillow")
class WarmingTheNewest(_Tmp):
    def test_it_makes_them_in_the_thumbs_folder(self):
        paths = self.photos(5)
        thread = T.warm(paths)
        self.assertIsNotNone(thread)
        thread.join(30)
        self.assertEqual(len(self.kept()), 5)

    def test_and_they_are_the_same_bytes_as_one_made_when_asked(self):
        paths = self.photos(1)
        T.warm(paths).join(30)
        folder = os.path.join(self.dir, "config", T.FOLDER)
        with open(os.path.join(folder, self.kept()[0]), "rb") as fh:
            warmed = fh.read()
        self.assertEqual(warmed, T._make(paths[0], "s"))
        self.assertEqual(T.thumb(paths[0]), warmed)

    def test_one_already_made_is_not_made_again(self):
        paths = self.photos(2)
        T.thumb(paths[0])
        made = []
        real = T._make
        with mock.patch.object(T, "_make",
                               lambda p, s: made.append(p) or real(p, s)):
            T.warm(paths).join(30)
        self.assertEqual(made, [paths[1]])


class WithoutPillow(_Tmp):
    def test_warming_is_a_no_op(self):
        paths = self.photos(2)
        with mock.patch.object(T, "have_pillow", lambda: False):
            self.assertIsNone(T.warm(paths))
        self.assertEqual(self.kept(), [])


class AfterTheIndexAddsPhotographs(unittest.TestCase):
    class Cat:
        def __init__(self, n):
            self._rows = [(f"2024-01-{i:02}", f"/p/{i}.JPG") for i in range(n)]

        def rows(self):
            return list(self._rows)

    def test_the_newest_three_hundred_are_warmed(self):
        from app import server as S
        asked = []
        with mock.patch.object(T, "warm", lambda paths: asked.append(paths) or 1):
            self.assertTrue(S.warm_newest(self.Cat(400), {"added": 12}))
        self.assertEqual(len(asked[0]), S.WARM_NEWEST)
        self.assertEqual(asked[0][0], "/p/0.JPG")

    def test_a_pass_that_added_nothing_warms_nothing(self):
        from app import server as S
        with mock.patch.object(T, "warm", lambda paths: self.fail("warmed")):
            self.assertFalse(S.warm_newest(self.Cat(10), {"added": 0}))
            self.assertFalse(S.warm_newest(self.Cat(10), {}))


if __name__ == "__main__":
    unittest.main()
