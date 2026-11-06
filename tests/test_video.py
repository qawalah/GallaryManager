"""Playing a clip, rather than showing a picture of one.

The viewer has always shown a video's thumbnail - a still frame with a play
triangle drawn on it - and pressing it did nothing. Serving the whole file in
one response would not have been a player either: a browser cannot seek in that,
a two-gigabyte clip would be read into memory to answer, and pressing play would
wait for all of it.

So the test that matters here is not "does it return bytes" but **does it answer
a Range request properly**, because that is the whole difference between a
player and a download that happens to be a film.
"""

import http.client
import http.server
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import demo                           # noqa: E402


class Served(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = tempfile.mkdtemp(prefix="vid-")
        os.environ["PM_DATA"] = os.path.join(cls.home, "config")
        cls.lib = os.path.join(cls.home, "Photos")
        os.makedirs(cls.lib)
        cls.clip = os.path.join(cls.lib, "holiday.mp4")
        # a real little MP4, made by the sample library's own maker, padded so a
        # range of it is a range of something
        body = demo.clip_bytes("2024:05:01 10:00:00") + b"\0" * 40_000
        with open(cls.clip, "wb") as fh:
            fh.write(body)
        cls.size = len(body)
        cls.other = os.path.join(cls.lib, "handycam.MTS")
        with open(cls.other, "wb") as fh:
            fh.write(b"\0" * 2048)
        from core import settings as S
        S.save({"library": cls.lib})
        from app import server as Srv
        import app.tasks                                   # noqa: F401
        Srv.ALLOWED_ROOTS[:] = []
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Srv.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        shutil.rmtree(cls.home, ignore_errors=True)

    def ask(self, path, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        from urllib.parse import quote
        c.request("GET", "/api/video?path=" + quote(path), headers=headers or {})
        r = c.getresponse()
        body = r.read()
        head = dict(r.getheaders())
        code = r.status
        c.close()
        return code, head, body

    def test_the_whole_clip_comes_back_when_nothing_is_asked_for(self):
        code, head, body = self.ask(self.clip)
        self.assertEqual(code, 200)
        self.assertEqual(len(body), self.size)
        self.assertEqual(head.get("Content-Type"), "video/mp4")
        # the one header that tells a browser it may seek at all
        self.assertEqual(head.get("Accept-Ranges"), "bytes")

    def test_a_range_comes_back_as_a_range(self):
        code, head, body = self.ask(self.clip, {"Range": "bytes=100-199"})
        self.assertEqual(code, 206)
        self.assertEqual(len(body), 100)
        self.assertEqual(head.get("Content-Range"),
                         f"bytes 100-199/{self.size}")
        self.assertEqual(head.get("Content-Length"), "100")

    def test_and_it_is_the_right_hundred_bytes(self):
        """A player that is handed the wrong part of the file does not show an
        error - it shows a frozen frame, which reads as a broken app."""
        with open(self.clip, "rb") as fh:
            fh.seek(100)
            want = fh.read(100)
        _code, _head, body = self.ask(self.clip, {"Range": "bytes=100-199"})
        self.assertEqual(body, want)

    def test_an_open_ended_range_runs_to_the_end(self):
        code, head, body = self.ask(self.clip, {"Range": "bytes=40000-"})
        self.assertEqual(code, 206)
        self.assertEqual(len(body), self.size - 40000)
        self.assertIn(f"/{self.size}", head.get("Content-Range", ""))

    def test_the_last_bytes_can_be_asked_for_by_themselves(self):
        """Which is the first thing a browser does: an MP4's index is often at
        the end, and it reads that before it plays a second of anything."""
        code, _head, body = self.ask(self.clip, {"Range": "bytes=-500"})
        self.assertEqual(code, 206)
        self.assertEqual(len(body), 500)

    def test_a_range_past_the_end_is_refused_properly(self):
        code, head, _body = self.ask(self.clip,
                                     {"Range": f"bytes={self.size + 10}-"})
        self.assertEqual(code, 416)
        self.assertEqual(head.get("Content-Range"), f"bytes */{self.size}")

    def test_a_format_no_browser_plays_is_refused_rather_than_half_served(self):
        code, _head, body = self.ask(self.other)
        self.assertEqual(code, 415)
        self.assertIn(b"play", body)

    def test_nothing_outside_the_library_is_served(self):
        from app import server as Srv
        Srv.ALLOWED_ROOTS[:] = [self.lib]
        try:
            outside = os.path.join(self.home, "elsewhere.mp4")
            with open(outside, "wb") as fh:
                fh.write(b"\0" * 10)
            code, _head, _body = self.ask(outside)
            self.assertEqual(code, 403)
        finally:
            Srv.ALLOWED_ROOTS[:] = []

    def test_and_a_file_that_is_not_there_says_so(self):
        code, _head, _body = self.ask(os.path.join(self.lib, "nothing.mp4"))
        self.assertEqual(code, 404)


if __name__ == "__main__":
    unittest.main()
