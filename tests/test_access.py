"""A lock on the door, and the parts of it that have to be true to be a lock.

The app has always taken `PM_PASSWORD`, and in practice nobody ever set one,
because setting it meant editing the compose file and rebuilding the container.
A lock that costs a rebuild is a lock that stays open - so it moved inside the
app, and that move is only worth anything if the things below hold.

What is actually being protected is worth saying, because it decides how much of
this matters: not privacy from whoever runs the NAS, who has the photographs
anyway, but the fact that this app MOVES things. Cull, re-mirror, send to
develop, clean up. Anything that can reach the port can start those.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import access                       # noqa: E402


class Store(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="access-")
        self._was = os.environ.get("PM_DATA")
        self._word = os.environ.pop("PM_PASSWORD", None)
        os.environ["PM_DATA"] = self.dir
        access.forget()
        access.forget_misses()

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        if self._word is not None:
            os.environ["PM_PASSWORD"] = self._word
        else:
            os.environ.pop("PM_PASSWORD", None)
        access.forget()
        access.forget_misses()
        shutil.rmtree(self.dir, ignore_errors=True)


class ThePassword(Store):
    def test_there_is_no_lock_until_one_is_set(self):
        self.assertFalse(access.is_on())
        self.assertFalse(access.correct("anything"))

    def test_and_then_only_the_right_one_opens_it(self):
        access.set_password("a good long one")
        self.assertTrue(access.is_on())
        self.assertTrue(access.correct("a good long one"))
        self.assertFalse(access.correct("a good long On"))
        self.assertFalse(access.correct(""))

    def test_what_is_stored_is_not_the_password(self):
        """The file can be copied off the NAS - by a backup, by anybody who can
        read the config folder. What it must not contain is the thing somebody
        would type."""
        access.set_password("hunter2 and then some")
        with open(os.path.join(self.dir, access.FILE), encoding="utf-8") as fh:
            raw = fh.read()
        self.assertNotIn("hunter2", raw)
        held = json.loads(raw)
        self.assertTrue(held["hash"])
        self.assertTrue(held["salt"])
        self.assertGreaterEqual(held["rounds"], 100000)

    def test_and_two_people_with_the_same_password_do_not_match_on_disk(self):
        """Which is what the salt is for: a hash without one tells an attacker
        that two libraries share a password, and lets one table answer both."""
        access.set_password("the same words")
        first = dict(access._read())
        access.set_password("the same words")
        self.assertNotEqual(first["hash"], access._read()["hash"])

    def test_the_file_is_not_readable_by_everybody(self):
        access.set_password("a good long one")
        mode = os.stat(os.path.join(self.dir, access.FILE)).st_mode & 0o777
        self.assertEqual(mode & 0o077, 0, oct(mode))

    def test_an_empty_password_takes_the_lock_off(self):
        access.set_password("a good long one")
        access.set_password("")
        self.assertFalse(access.is_on())

    def test_the_compose_file_wins_and_cannot_be_overruled_from_inside(self):
        """A decision made outside this app must not be changeable by anyone who
        got in once - otherwise the first thing an intruder does is take the
        lock off."""
        os.environ["PM_PASSWORD"] = "from the compose file"
        access.forget()
        self.assertTrue(access.is_on())
        self.assertTrue(access.from_environment())
        self.assertTrue(access.correct("from the compose file"))
        access.set_password("something else")
        self.assertFalse(access.correct("something else"))
        self.assertTrue(access.correct("from the compose file"))


class TheTicket(Store):
    def test_a_ticket_this_app_signed_is_accepted(self):
        access.set_password("a good long one")
        self.assertTrue(access.ticket_ok(access.ticket()))

    def test_one_nobody_signed_is_not(self):
        access.set_password("a good long one")
        for made_up in ("", "rubbish", "1.9999999999.deadbeef",
                        access.ticket()[:-4] + "0000"):
            self.assertFalse(access.ticket_ok(made_up), made_up)

    def test_an_expired_one_is_not_either(self):
        access.set_password("a good long one")
        self.assertFalse(access.ticket_ok(access.ticket(days=-5)))

    def test_signing_out_everywhere_makes_every_ticket_worthless(self):
        """The only revocation there is, and it has to be real: if you think
        somebody has the password, changing it must not leave their browser
        signed in."""
        access.set_password("a good long one")
        had = access.ticket()
        access.sign_out_everywhere()
        self.assertFalse(access.ticket_ok(had))

    def test_and_so_does_changing_the_password(self):
        access.set_password("a good long one")
        had = access.ticket()
        access.set_password("a different good long one")
        self.assertFalse(access.ticket_ok(had))

    def test_a_restart_does_not_sign_you_out(self):
        """Tickets are signed rather than remembered, so nothing is lost when
        the container restarts - which on a NAS is often, and a lock that logs
        you out every time it happens is one you will turn off."""
        access.set_password("a good long one")
        had = access.ticket()
        access.forget()                       # as if the process had restarted
        self.assertTrue(access.ticket_ok(had))


class SlowingAGuessingMachine(Store):
    def test_wrong_tries_add_up_and_then_the_door_waits(self):
        for _ in range(access.LOCK_AFTER):
            self.assertEqual(access.locked_for("10.0.0.5"), 0)
            access.missed("10.0.0.5")
        self.assertGreater(access.locked_for("10.0.0.5"), 0)

    def test_and_getting_in_clears_the_count(self):
        for _ in range(3):
            access.missed("10.0.0.5")
        access.got_in("10.0.0.5")
        self.assertEqual(access.locked_for("10.0.0.5"), 0)

    def test_one_machine_guessing_does_not_lock_out_another(self):
        for _ in range(access.LOCK_AFTER + 2):
            access.missed("10.0.0.5")
        self.assertEqual(access.locked_for("10.0.0.9"), 0)


class TheDoorItself(Store):
    """The server, answered over a real socket - because what matters is not
    that the functions above work but that nothing gets past them."""

    def setUp(self):
        super().setUp()
        import http.server
        import threading
        from app import server as S
        import app.tasks                                  # noqa: F401
        S.ALLOWED_ROOTS[:] = []
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        super().tearDown()

    def get(self, path, cookie="", auth=""):
        req = urllib.request.Request(self.base + path)
        if cookie:
            req.add_header("Cookie", cookie)
        if auth:
            import base64
            req.add_header("Authorization", "Basic " + base64.b64encode(
                auth.encode()).decode())
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read().decode("utf-8", "replace"), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace"), e.headers

    def post(self, path, body):
        req = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b"{}"), r.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}"), e.headers

    def test_with_no_password_everything_is_open(self):
        code, body, _h = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("Photo Manager", body)
        self.assertEqual(self.get("/api/health")[0], 200)

    def test_with_one_set_the_page_becomes_the_login_page(self):
        """A browser, not a 401. A browser handed a 401 shows its own grey box,
        which cannot say what this is, cannot offer to remember you, and cannot
        be made to look like the app it is guarding."""
        access.set_password("a good long one")
        code, body, _h = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("This library is locked", body)
        self.assertNotIn('id="autobar"', body, "not a scrap of the app")

    def test_and_the_api_becomes_a_401_that_says_what_to_do(self):
        """Which is what a script can act on - and what the page itself reads to
        know it has been signed out."""
        access.set_password("a good long one")
        code, body, _h = self.post("/api/plan", {"task": "library"})
        self.assertEqual(code, 401)
        self.assertTrue(body.get("login"))

    def test_the_right_password_gives_a_ticket_and_the_app_back(self):
        access.set_password("a good long one")
        code, body, headers = self.post("/api/login",
                                        {"password": "a good long one"})
        self.assertEqual(code, 200)
        self.assertTrue(body.get("ok"))
        cookie = headers.get("Set-Cookie") or ""
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        ticket = cookie.split(";")[0]
        code, page, _h = self.get("/", cookie=ticket)
        self.assertEqual(code, 200)
        self.assertIn('id="autobar"', page, "the app itself, not the door")

    def test_the_wrong_one_gives_nothing_and_says_nothing_useful(self):
        access.set_password("a good long one")
        code, body, headers = self.post("/api/login", {"password": "guess"})
        self.assertEqual(code, 401)
        self.assertFalse(body.get("ok"))
        self.assertNotIn("Set-Cookie", headers)

    def test_a_made_up_cookie_does_not_get_in(self):
        access.set_password("a good long one")
        code, body, _h = self.get("/", cookie="pm_ticket=1.99999999999.abc")
        self.assertIn("This library is locked", body)

    def test_a_script_can_still_use_http_basic(self):
        """The command line and anything else without somewhere to keep a
        cookie. Same password, no session."""
        access.set_password("a good long one")
        code, _body, _h = self.get("/api/health",
                                   auth="photos:a good long one")
        self.assertEqual(code, 200)
        self.assertEqual(self.get("/api/health", auth="photos:wrong")[0], 401)

    def test_the_login_page_can_still_fetch_its_own_icon(self):
        """A lock that hides the key to itself is not a lock, it is a broken
        page."""
        access.set_password("a good long one")
        self.assertEqual(self.get("/icon-32.png")[0], 200)

    def test_signing_out_clears_the_cookie(self):
        access.set_password("a good long one")
        _c, _b, headers = self.post("/api/login", {"password": "a good long one"})
        ticket = (headers.get("Set-Cookie") or "").split(";")[0]
        code, body, out = self.post("/api/logout", {})
        self.assertEqual(code, 200)
        self.assertIn("Max-Age=0", out.get("Set-Cookie") or "")
        # and the ticket it cleared is still valid until it expires: signing out
        # of ONE browser must not sign out the tablet in the kitchen
        self.assertEqual(self.get("/api/health", cookie=ticket)[0], 200)

    def test_unless_you_ask_for_everywhere(self):
        access.set_password("a good long one")
        _c, _b, headers = self.post("/api/login", {"password": "a good long one"})
        ticket = (headers.get("Set-Cookie") or "").split(";")[0]
        self.post("/api/logout", {"everywhere": True})
        self.assertEqual(self.get("/api/health", cookie=ticket)[0], 401)

    def test_the_gate_says_whether_there_is_one_without_letting_you_in(self):
        access.set_password("a good long one")
        code, body, _h = self.get("/api/gate")
        self.assertEqual(code, 200)
        said = json.loads(body)
        self.assertTrue(said["on"])
        self.assertFalse(said["in"])

    def test_and_guessing_at_it_gets_slower(self):
        access.set_password("a good long one")
        for _ in range(access.LOCK_AFTER):
            self.post("/api/login", {"password": "no"})
        code, body, _h = self.post("/api/login", {"password": "a good long one"})
        self.assertEqual(code, 429, "the right password during a lock-out")
        self.assertIn("Try again", body.get("why", ""))


class TheTabThatSetsIt(Store):
    def task(self):
        from app import registry as R
        import app.tasks                                  # noqa: F401
        return R.get("password")

    def make(self, **opts):
        t = self.task()
        raw = {"word": "", "again": "", "off": False, "everywhere": False}
        raw.update(opts)
        return t, t.make_plan(raw)

    def test_setting_one_locks_the_app(self):
        t, p = self.make(word="a good long one", again="a good long one")
        self.assertFalse(p.blocked, p.blocked)
        t.apply(p)
        self.assertTrue(access.is_on())
        self.assertTrue(access.correct("a good long one"))

    def test_two_boxes_that_disagree_are_refused(self):
        """A password you cannot see is one you can mistype and not know."""
        _t, p = self.make(word="a good long one", again="a good long obe")
        self.assertIn("not the same", p.blocked)

    def test_and_so_is_one_hardly_worth_typing(self):
        _t, p = self.make(word="abc", again="abc")
        self.assertTrue(p.blocked)

    def test_planning_alone_changes_nothing(self):
        self.make(word="a good long one", again="a good long one")
        self.assertFalse(access.is_on())

    def test_taking_it_off_says_out_loud_what_that_means(self):
        access.set_password("a good long one")
        t, p = self.make(off=True)
        self.assertIn("move, cull and re-mirror", " ".join(p.notes))
        t.apply(p)
        self.assertFalse(access.is_on())

    def test_and_the_compose_file_version_cannot_be_touched_from_here(self):
        os.environ["PM_PASSWORD"] = "from the compose file"
        access.forget()
        _t, p = self.make(word="a good long one", again="a good long one")
        self.assertIn("compose file", p.blocked)

    def test_the_new_password_is_never_drawn_back_into_the_form(self):
        """Every other option in this app fills itself in from what you last
        used. A password box that did that would put the password into the
        page's HTML."""
        for option in self.task().options:
            if option.kind == "secret":
                self.assertEqual(option.describe()["default"], "")


if __name__ == "__main__":
    unittest.main()
