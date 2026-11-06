"""What a client is told, how it finds a server, and running as a PC program.

One app, several machines, three clients. Everything here is about the moment
before a client can do anything useful: which server is this, what is it called,
what can it do, and how was it found without anyone typing an address.
"""

import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.tasks                                  # noqa: E402,F401
from app import server as SRV                     # noqa: E402
from app.registry import get                      # noqa: E402
from core import desktop as DK                    # noqa: E402
from core import discovery as D                   # noqa: E402
from core import identity as I                    # noqa: E402
from core import settings as S                    # noqa: E402


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="clients-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        os.makedirs(os.environ["PM_DATA"])
        self.lib = os.path.join(self.dir, "Photos")
        os.makedirs(self.lib)
        S.save({"library": self.lib})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        os.environ.pop(DK.FLAG, None)
        shutil.rmtree(self.dir, ignore_errors=True)


class WhichServerIsThis(_Tmp):
    def test_it_has_an_id_that_does_not_change(self):
        """A client stores a connection against the id, not the address - a
        phone moves between wifi and a VPN and the address moves under it."""
        first = I.my_id()
        self.assertEqual(len(first), 32)
        self.assertEqual(first, I.my_id())

    def test_two_servers_never_share_an_id(self):
        """Made from uuid4 rather than the hostname or the MAC: two boxes out of
        one batch, or a container rebuilt from one image, would collide - and
        two servers a client believes are one is the worst outcome here."""
        mine = I.my_id()
        S.save({"server_id": ""})
        self.assertNotEqual(mine, I.my_id())

    def test_it_is_called_what_you_called_it_and_the_machine_otherwise(self):
        self.assertEqual(I.name(), I.host())
        S.save({"server_name": "  NAS  "})
        self.assertEqual(I.name(), "NAS")

    def test_what_it_says_it_can_do_is_named_not_guessed_from_a_version(self):
        said = I.describe()
        self.assertIn("browse", said["can"])
        self.assertIn("search", said["can"])
        self.assertEqual(said["api"], I.API)
        self.assertEqual(said["app"], "photo-manager")

    def test_it_says_which_trees_are_there_and_which_are_only_configured(self):
        """On the NAS a volume that did not come up looks exactly like an empty
        folder from the outside, so a client has to be told."""
        S.save({"raw": os.path.join(self.dir, "not here")})
        trees = {t["key"]: t for t in I.describe()["trees"]}
        self.assertTrue(trees["library"]["there"])
        self.assertFalse(trees["raw"]["there"])

    def test_the_short_form_fits_in_one_datagram(self):
        """A reply that has to be fragmented is one that quietly does not arrive
        on some networks."""
        S.save({"server_name": "x" * 60})
        said = json.dumps(I.brief(8842, True)).encode("utf-8")
        self.assertLess(len(said), D.MAX)


class BeingFound(_Tmp):
    def _serving(self, locked=False, port=8842):
        stop = threading.Event()
        thread = D.responder(lambda: I.brief(port, locked), stop)

        def done():
            stop.set()
            thread.join(timeout=3)
        # Joined, not just signalled: a responder still alive when the next test
        # starts answers that test's shout with this test's port, and the
        # failure reads as a discovery bug rather than as a test that leaked.
        self.addCleanup(done)
        time.sleep(0.25)
        return stop

    def test_a_shout_is_answered_with_a_name_a_port_and_an_address(self):
        S.save({"server_name": "The NAS"})
        self._serving(port=8842)
        found = D.find(1.0)
        self.assertTrue(found, "nothing answered")
        one = [f for f in found if f["id"] == I.my_id()]
        self.assertTrue(one, found)
        one = one[0]
        self.assertEqual(one["name"], "The NAS")
        self.assertEqual(one["port"], 8842)
        self.assertTrue(one["address"], "the client learns the address from the reply")
        self.assertTrue(one["url"].endswith(":8842"))

    def test_it_says_whether_a_password_is_needed_but_nothing_about_the_photos(self):
        """So a client can ask for the password up front rather than after a
        401 - and so a port that answers strangers says as little as possible."""
        self._serving(locked=True)
        one = [f for f in D.find(1.0) if f["id"] == I.my_id()][0]
        self.assertTrue(one["locked"])
        for leak in ("trees", "library", "path", "folders"):
            self.assertNotIn(leak, one, leak)

    def test_the_name_it_answers_with_follows_setup_without_a_restart(self):
        """The responder asks again for every datagram on purpose: a server
        still answering with last week's name is a small lie that is hard to
        spot."""
        self._serving()
        S.save({"server_name": "Renamed"})
        one = [f for f in D.find(1.0) if f["id"] == I.my_id()][0]
        self.assertEqual(one["name"], "Renamed")

    def test_anything_that_is_not_the_question_is_ignored_in_silence(self):
        """A port that answers strangers is a port that turns up in somebody's
        scan report."""
        self.assertIsNone(D._reply_for(b"hello?", I.brief()))
        self.assertIsNone(D._reply_for(b"", I.brief()))
        self.assertIsNotNone(D._reply_for(D.ASK, I.brief()))

    def test_it_can_be_turned_off_and_reads_either_way_of_saying_so(self):
        self.assertTrue(D.wanted())
        for off in (False, "no", "off", "0"):
            S.save({"discovery": off})
            self.assertFalse(D.wanted(), repr(off))
        S.save({"discovery": True})
        self.assertTrue(D.wanted())

    def test_a_port_it_cannot_have_does_not_bring_the_server_down(self):
        """Discovery is a convenience. A network stack that will not give out
        the port must leave the app serving pages exactly as before."""
        stop = threading.Event()
        thread = D.responder(lambda: I.brief(), stop)
        self.addCleanup(lambda: (stop.set(), thread.join(timeout=3)))
        time.sleep(0.2)
        # It hands back a thread either way - bound and answering, or given up
        # quietly. What it must never do is raise into the caller, because the
        # caller is the line that starts the web server.
        self.assertIsInstance(thread, threading.Thread)


class OverHttp(_Tmp):
    """The one call a client makes before it has a password."""

    def setUp(self):
        super().setUp()
        SRV.ALLOWED_ROOTS[:] = []
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), SRV.Handler)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.shutdown)

    def _get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    def test_a_client_can_ask_what_this_is_before_it_has_a_password(self):
        said = self._get("/api/client")
        self.assertEqual(said["app"], "photo-manager")
        self.assertEqual(said["id"], I.my_id())
        self.assertIn("release", said)
        self.assertIn("can", said)

    def test_and_is_told_the_folders_only_once_it_is_signed_in(self):
        """The names of somebody's folders are not something to hand to whoever
        asks on the network."""
        from core import access
        said = self._get("/api/client")
        self.assertTrue(said["signed_in"])          # no password set yet
        self.assertIn("trees", said)
        access.set_password("hunter2")
        self.addCleanup(access.forget)
        said = self._get("/api/client")
        self.assertFalse(said["signed_in"])
        self.assertNotIn("trees", said)
        self.assertTrue(said["locked"])

    def test_health_says_which_kind_of_copy_this_is(self):
        self.assertFalse(self._get("/api/health")["desktop"])
        os.environ[DK.FLAG] = "1"
        self.assertTrue(self._get("/api/health")["desktop"])

    def test_the_nas_copy_refuses_to_be_quit_from_the_page(self):
        """A Quit on the NAS would take the app off the network with nothing to
        bring it back."""
        req = urllib.request.Request(self.base + "/api/quit", data=b"{}",
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(caught.exception.code, 400)


class TheWayAClientIsToldThePort(_Tmp):
    def test_it_is_the_listening_port_unless_something_says_otherwise(self):
        self.assertEqual(SRV.public_port(), SRV.PORT)

    def test_a_container_can_say_the_port_it_is_mapped_to(self):
        """The mapping is 8842:8080 and 8080 is the only number the process can
        see, so an answer saying 8080 would send every phone to a closed port."""
        S.save({"public_port": "8842"})
        self.assertEqual(SRV.public_port(), 8842)

    def test_the_environment_beats_the_setting(self):
        S.save({"public_port": "8842"})
        os.environ["PM_PUBLIC_PORT"] = "9000"
        self.addCleanup(os.environ.pop, "PM_PUBLIC_PORT", None)
        self.assertEqual(SRV.public_port(), 9000)

    def test_nonsense_falls_back_rather_than_breaking_the_answer(self):
        for bad in ("banana", "-1", "70000", ""):
            S.save({"public_port": bad})
            self.assertEqual(SRV.public_port(), SRV.PORT, bad)


class AsAProgramOnAPc(_Tmp):
    def test_settings_go_outside_the_program_so_an_upgrade_keeps_them(self):
        """Beside the code is right for a folder you copied to a spare drive and
        wrong for something installed: replace the program and the library path
        goes with it."""
        self.assertEqual(
            DK.data_home({"LOCALAPPDATA": r"C:\Users\A\AppData\Local"}),
            os.path.join(r"C:\Users\A\AppData\Local", "PhotoManager"))
        self.assertEqual(DK.data_home({"HOME": "/home/a"}),
                         os.path.join("/home/a", ".photo-manager"))

    def test_an_explicit_pm_data_still_wins_which_is_what_the_container_sets(self):
        self.assertEqual(DK.data_home({"PM_DATA": "/config",
                                       "LOCALAPPDATA": "C:\\x"}), "/config")

    def test_a_container_with_no_home_falls_back_beside_the_code(self):
        self.assertEqual(DK.data_home({}, code_root="/app"),
                         os.path.join("/app", "config"))

    def test_the_program_flag_is_what_makes_quit_appear(self):
        self.assertFalse(DK.as_program())
        for on in ("1", "yes", "true", "ON"):
            os.environ[DK.FLAG] = on
            self.assertTrue(DK.as_program(), on)
        os.environ[DK.FLAG] = "0"
        self.assertFalse(DK.as_program())

    def test_the_installer_writes_a_shortcut_and_nothing_else(self):
        """No registry keys: an app that writes to the registry is an app you
        are never sure you have removed."""
        made = DK.shortcut_script(r"C:\Menu", "Photo Manager",
                                  r"C:\Py\pythonw.exe", r'"C:\PM\x.pyw"')
        self.assertIn("CreateShortcut", made)
        self.assertIn("Photo Manager.lnk", made)
        self.assertIn("$s.Save()", made)
        self.assertNotIn("HKEY", made)
        self.assertNotIn("reg add", made.lower())

    def test_the_windows_launcher_is_valid_python_and_has_no_console(self):
        """`.pyw` is the whole trick - Windows runs it with pythonw.exe, so
        there is no black box in the taskbar for as long as the app runs."""
        import ast
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        launcher = os.path.join(here, "windows", "PhotoManager.pyw")
        self.assertTrue(os.path.exists(launcher))
        ast.parse(open(launcher, encoding="utf-8").read())

    def test_every_windows_file_the_readme_names_is_there(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for n in ("PhotoManager.pyw", "Install.bat", "Uninstall.bat",
                  "Stop.bat", "README.md"):
            self.assertTrue(os.path.exists(os.path.join(here, "windows", n)), n)


class OnTheSetupTab(_Tmp):
    def test_the_three_network_settings_are_there_and_saved(self):
        t = get("setup")
        names = [o.name for o in t.options if o.group == "Network"]
        self.assertEqual(names, ["server_name", "discovery", "public_port"])
        from app.tasks import setup as SU
        for n in names:
            self.assertIn(n, SU.FIELDS, n)


if __name__ == "__main__":
    unittest.main()
