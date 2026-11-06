"""Getting past the password, and being slowed down for trying.

test_access.py checks the lock itself. These check the two ways round it that
the third audit found: HTTP Basic, which never touched the lockout counter, and
a lockout keyed on whichever machine was nearest - a reverse proxy, for every
request in the house.
"""

import base64
import http.client
import http.server
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import access                                   # noqa: E402
from tests.test_access import Store                       # noqa: E402

WORD = "a good long one"


class Door(Store):
    def setUp(self):
        super().setUp()
        from app import server as S
        import app.tasks                                  # noqa: F401
        self.S = S
        S.ALLOWED_ROOTS[:] = []
        self._proxies = list(S.TRUSTED_PROXIES)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.S.TRUSTED_PROXIES[:] = self._proxies
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def ask(self, path="/api/health", user="photos", word=None, headers=None,
            method="GET", body=b""):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            heads = dict(headers or {})
            if word is not None:
                pair = f"{user}:{word}".encode("utf-8")
                heads["Authorization"] = "Basic " + base64.b64encode(pair).decode()
            if body:
                heads.setdefault("Content-Type", "application/json")
            conn.request(method, path, body=body or None, headers=heads)
            got = conn.getresponse()
            return got.status, got.read(), got
        finally:
            conn.close()


class BasicIsCountedLikeTheLoginForm(Door):
    """SV2: a script could guess through Basic at full speed."""

    def test_enough_wrong_guesses_and_even_the_right_one_waits(self):
        access.set_password(WORD)
        for _ in range(access.LOCK_AFTER):
            self.assertEqual(self.ask(word="nope")[0], 401)
        code, body, got = self.ask(word=WORD)
        self.assertEqual(code, 429)
        self.assertIn(b"Too many wrong tries", body)
        self.assertTrue(got.getheader("Retry-After"))

    def test_and_the_login_form_is_locked_by_the_same_count(self):
        access.set_password(WORD)
        for _ in range(access.LOCK_AFTER):
            self.ask(word="nope")
        code, _b, _g = self.ask("/api/login", method="POST",
                                body=b'{"password": "a good long one"}')
        self.assertEqual(code, 429)

    def test_the_right_one_clears_the_count(self):
        access.set_password(WORD)
        for _ in range(access.LOCK_AFTER - 1):
            self.ask(word="nope")
        self.assertEqual(self.ask(word=WORD)[0], 200)
        self.assertEqual(access.locked_for("127.0.0.1"), 0)

    def test_one_request_is_one_miss_however_often_the_gate_is_asked(self):
        """/api/client asks "signed in?" itself and then the gate asks again."""
        access.set_password(WORD)
        self.ask("/api/client", word="nope")
        misses, _when = access._MISSES.get("127.0.0.1", (0, 0))
        self.assertEqual(misses, 1)

    def test_no_password_header_is_not_a_miss(self):
        access.set_password(WORD)
        for _ in range(access.LOCK_AFTER + 2):
            self.assertEqual(self.ask()[0], 401)
        self.assertEqual(access.locked_for("127.0.0.1"), 0)


class BasicInAnyLanguage(Door):
    """SV8: compare_digest refuses a str with anything but ASCII in it."""

    def test_a_password_set_in_the_app_with_accents_works_over_basic(self):
        access.set_password("sécret ٣")
        self.assertEqual(self.ask(word="sécret ٣")[0], 200)
        self.assertEqual(self.ask(word="sécret 3")[0], 401)

    def test_a_name_outside_ascii_is_a_no_not_a_500(self):
        access.set_password(WORD)
        self.assertEqual(self.ask(user="مستخدم", word=WORD)[0], 401)

    def test_a_password_in_the_environment_with_accents(self):
        os.environ["PM_PASSWORD"] = "كلمة السر"
        self.assertTrue(access.correct("كلمة السر"))
        self.assertFalse(access.correct("x"))
        self.assertEqual(self.ask(word="كلمة السر")[0], 200)
        self.assertEqual(self.ask(word="كلمة")[0], 401)


class BehindAProxy(Door):
    """SV9: behind DSM's reverse proxy every request comes from the proxy."""

    def test_a_trusted_proxy_locks_out_only_the_guesser(self):
        access.set_password(WORD)
        self.S.TRUSTED_PROXIES[:] = self.S._networks("127.0.0.1")
        guesser = {"X-Forwarded-For": "10.0.0.5"}
        for _ in range(access.LOCK_AFTER):
            self.ask(word="nope", headers=guesser)
        self.assertEqual(self.ask(word=WORD, headers=guesser)[0], 429)
        self.assertEqual(self.ask(word=WORD,
                                  headers={"X-Forwarded-For": "10.0.0.9"})[0], 200)

    def test_the_header_is_read_from_the_proxy_end(self):
        """A browser can send its own X-Forwarded-For; the proxy appends the
        address it really saw, so that is the one that counts."""
        access.set_password(WORD)
        self.S.TRUSTED_PROXIES[:] = self.S._networks("127.0.0.0/8")
        for i in range(access.LOCK_AFTER):
            self.ask(word="nope",
                     headers={"X-Forwarded-For": f"1.2.3.{i}, 10.0.0.5"})
        self.assertGreater(access.locked_for("10.0.0.5"), 0)

    def test_without_one_the_header_is_ignored(self):
        """Or a guesser would send a fresh address with every try."""
        access.set_password(WORD)
        for i in range(access.LOCK_AFTER):
            self.ask(word="nope", headers={"X-Forwarded-For": f"10.0.0.{i}"})
        self.assertGreater(access.locked_for("127.0.0.1"), 0)


class TheNameCheckWithAPassword(Door):
    """With a password on, a name nobody chose has no cookie and cannot sign
    in, so a reverse proxy's public name needs no PM_HOSTS."""

    def test_an_unknown_name_is_let_be_once_a_password_is_set(self):
        access.set_password(WORD)
        heads = {"Host": "photos.example.com"}
        code, _b, _g = self.ask("/api/login", method="POST", headers=heads,
                                body=b'{"password": "a good long one"}')
        self.assertEqual(code, 200)

    def test_but_not_without_one(self):
        heads = {"Host": "photos.example.com"}
        code, _b, _g = self.ask("/api/index", method="POST", headers=heads,
                                body=b"{}")
        self.assertEqual(code, 403)


if __name__ == "__main__":
    unittest.main()
