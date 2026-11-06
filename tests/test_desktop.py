"""The Windows program: its icon by the clock, its shortcuts, its own icon.

What the tray menu offers, what the installer writes and how the program steps
aside for a copy already running are all decided in plain Python, so they are
tested here on any system. The calls into Windows itself (`windows/tray.py`)
can only be loaded here, not run; that is what a real PC is for.
"""

import importlib.machinery
import importlib.util
import json
import os
import shutil
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import app.tasks                                  # noqa: E402,F401
from app import server as SRV                     # noqa: E402
from core import desktop as DK                    # noqa: E402

WINDOWS = os.path.join(HERE, "windows")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _load(name: str, path: str):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="desktop-")
        self.env = {"PM_DATA": os.path.join(self.dir, "data")}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class TheTrayMenu(unittest.TestCase):
    def _ids(self, menu):
        return [m["id"] if m else None for m in menu]

    def test_open_comes_first_and_is_what_a_click_on_the_icon_does(self):
        menu = DK.tray_menu({})
        self.assertEqual(menu[0]["id"], "open")
        self.assertTrue(menu[0]["default"])
        self.assertEqual(sum(1 for m in menu if m and m.get("default")), 1)

    def test_quit_is_always_there_and_always_last(self):
        """The reason the icon exists: stopping a program with no window
        without Task Manager."""
        for state in ({}, {"busy": 2, "lan": "192.168.1.5", "edge": True}):
            menu = DK.tray_menu(state)
            self.assertEqual(menu[-1]["id"], "quit")
            self.assertNotEqual(menu[-1].get("enabled"), False)

    def test_quit_says_when_something_is_still_running(self):
        self.assertEqual(DK.tray_menu({})[-1]["label"], "Quit Photo Manager")
        self.assertIn("2 running", DK.tray_menu({"busy": 2})[-1]["label"])

    def test_the_quick_settings_show_how_things_are_now(self):
        on = DK.tray_menu({"edge": True, "own_window": True, "startup": True})
        off = DK.tray_menu({"edge": True, "own_window": False, "startup": False})
        for menu, want in ((on, True), (off, False)):
            by = {m["id"]: m for m in menu if m}
            self.assertEqual(by["own_window"]["checked"], want)
            self.assertEqual(by["startup"]["checked"], want)

    def test_its_own_window_is_greyed_out_where_there_is_no_edge_to_make_one(self):
        by = {m["id"]: m for m in DK.tray_menu({"own_window": True}) if m}
        self.assertFalse(by["own_window"]["enabled"])
        self.assertFalse(by["own_window"]["checked"])

    def test_the_phone_address_is_offered_only_when_there_is_one(self):
        self.assertNotIn("copy_address", self._ids(DK.tray_menu({})))
        menu = DK.tray_menu({"lan": "192.168.1.5"})
        self.assertIn("copy_address", self._ids(menu))
        self.assertIn("192.168.1.5", [m for m in menu if m and
                                      m["id"] == "copy_address"][0]["label"])

    def test_dividers_never_start_end_or_double_up(self):
        for state in ({}, {"lan": "10.0.0.2", "edge": True, "busy": 1}):
            ids = self._ids(DK.tray_menu(state))
            self.assertIsNotNone(ids[0])
            self.assertIsNotNone(ids[-1])
            for a, b in zip(ids, ids[1:]):
                self.assertFalse(a is None and b is None)

    def test_every_entry_is_one_the_program_knows_what_to_do_with(self):
        """An entry with no handler is a menu item that does nothing."""
        launcher = _read(os.path.join(WINDOWS, "PhotoManager.pyw"))
        menu = DK.tray_menu({"lan": "10.0.0.2", "edge": True})
        for entry in filter(None, menu):
            self.assertIn(f'what == "{entry["id"]}"', launcher, entry["id"])

    def test_the_words_under_the_mouse_fit_what_windows_allows(self):
        self.assertIn("http://127.0.0.1:8080", DK.tray_tip(8080))
        self.assertIn("1 task running", DK.tray_tip(8080, 1))
        self.assertIn("3 tasks running", DK.tray_tip(8080, 3))
        self.assertLess(len(DK.tray_tip(65535, 999)), 128)

    def test_quitting_asks_first_only_when_it_would_stop_something(self):
        self.assertEqual(DK.quit_question(0), "")
        self.assertIn("A tool is still running", DK.quit_question(1))
        self.assertIn("3 tools are still running", DK.quit_question(3))
        self.assertTrue(DK.quit_question(1).endswith("Quit anyway?"))


class ItsSettings(_Tmp):
    def test_they_start_as_own_window_and_not_yet_introduced(self):
        self.assertEqual(DK.prefs(self.env),
                         {"own_window": True, "told_about_tray": False})

    def test_a_change_is_kept_and_the_rest_left_alone(self):
        DK.save_prefs({"own_window": False}, self.env)
        DK.save_prefs({"told_about_tray": True}, self.env)
        self.assertEqual(DK.prefs(self.env),
                         {"own_window": False, "told_about_tray": True})

    def test_they_live_beside_the_other_settings_not_in_them(self):
        """settings.json is shared with the NAS; a PC preference must not be a
        way to break it there."""
        DK.save_prefs({"own_window": False}, self.env)
        self.assertTrue(os.path.exists(os.path.join(self.env["PM_DATA"],
                                                    "desktop.json")))
        self.assertFalse(os.path.exists(os.path.join(self.env["PM_DATA"],
                                                     "settings.json")))

    def test_a_broken_file_or_strange_keys_fall_back_to_the_defaults(self):
        os.makedirs(self.env["PM_DATA"])
        path = os.path.join(self.env["PM_DATA"], "desktop.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(DK.prefs(self.env), dict(DK.DEFAULT_PREFS))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"own_window": False, "evil": "x"}, fh)
        self.assertEqual(DK.prefs(self.env),
                         {"own_window": False, "told_about_tray": False})
        DK.save_prefs({"evil": True}, self.env)
        self.assertNotIn("evil", json.loads(_read(path)))


class OpeningThePage(unittest.TestCase):
    def test_edge_is_found_where_windows_puts_it(self):
        env = {"ProgramFiles(x86)": r"C:\Program Files (x86)",
               "ProgramFiles": r"C:\Program Files"}
        found = DK.edge_path(env, exists=lambda p: "(x86)" in p)
        self.assertTrue(found.endswith("msedge.exe"))
        self.assertIn("(x86)", found)
        self.assertEqual(DK.edge_path(env, exists=lambda p: False), "")
        self.assertEqual(DK.edge_path({}, exists=lambda p: True), "")

    def test_its_own_window_is_edge_in_app_mode_and_otherwise_the_browser(self):
        url = "http://localhost:8080"
        self.assertEqual(DK.open_command(url, True, r"C:\e\msedge.exe"),
                         [r"C:\e\msedge.exe", f"--app={url}"])
        self.assertEqual(DK.open_command(url, False, r"C:\e\msedge.exe"), [])
        self.assertEqual(DK.open_command(url, True, ""), [])


class TheShortcuts(unittest.TestCase):
    PYW = r"C:\Python\pythonw.exe"
    LAUNCHER = r"C:\Users\Ali\Photo Manager\windows\PhotoManager.pyw"
    ICON = r"C:\Users\Ali\Photo Manager\windows\PhotoManager.ico"

    def test_start_menu_desktop_and_startup_each_get_one_with_the_icon(self):
        made = DK.shortcuts_script(self.PYW, self.LAUNCHER, self.ICON)
        for place in ("Programs", "Desktop", "Startup"):
            self.assertIn(f"GetFolderPath('{place}')", made)
        self.assertEqual(made.count("$s.Save()"), 3)
        self.assertEqual(made.count(f"$s.IconLocation = '{self.ICON}'"), 3)
        self.assertEqual(made.count(r"$s.WorkingDirectory = "
                                    r"'C:\Users\Ali\Photo Manager\windows'"), 3)

    def test_only_the_startup_one_starts_quietly(self):
        """A browser window on every login is how a program gets taken out of
        Startup, and then the automation is not running when it is due."""
        made = DK.shortcuts_script(self.PYW, self.LAUNCHER, self.ICON)
        self.assertEqual(made.count(DK.BACKGROUND), 1)
        startup = made[made.index("'Startup'"):]
        self.assertIn(DK.BACKGROUND, startup)

    def test_a_quote_in_a_folder_name_does_not_break_it(self):
        made = DK.shortcuts_script(self.PYW, r"C:\Ali's\windows\PhotoManager.pyw",
                                   r"C:\Ali's\windows\PhotoManager.ico")
        self.assertIn(r"'C:\Ali''s\windows\PhotoManager.ico'", made)
        self.assertNotIn(r"'C:\Ali's", made)

    def test_nothing_goes_in_the_registry_either_way(self):
        for made in (DK.shortcuts_script(self.PYW, self.LAUNCHER, self.ICON),
                     DK.remove_shortcuts_script()):
            self.assertNotIn("HKEY", made)
            self.assertNotIn("HKCU", made)
            self.assertNotIn("reg add", made.lower())

    def test_removing_takes_only_its_own_shortcuts(self):
        gone = DK.remove_shortcuts_script()
        self.assertEqual(gone.count("Remove-Item"), 3)
        self.assertEqual(gone.count("'Photo Manager.lnk'"), 3)
        self.assertNotIn("-Recurse", gone)
        only = DK.remove_shortcuts_script(places=("Startup",))
        self.assertEqual(only.count("Remove-Item"), 1)
        self.assertIn("'Startup'", only)

    def test_whether_it_starts_with_windows_is_whether_the_shortcut_is_there(self):
        env = {"APPDATA": r"C:\Users\Ali\AppData\Roaming"}
        link = DK.startup_link(env)
        self.assertTrue(link.endswith("Photo Manager.lnk"))
        self.assertIn("Startup", link)
        self.assertTrue(DK.starts_with_windows(env, exists=lambda p: p == link))
        self.assertFalse(DK.starts_with_windows(env, exists=lambda p: False))
        self.assertFalse(DK.starts_with_windows({}, exists=lambda p: True))

    def test_powershell_is_handed_the_script_encoded_not_quoted(self):
        """Quotes passed through Windows' command line arrive changed."""
        seen = {}

        def run(args, **kw):
            seen["args"] = args
            return mock.Mock(returncode=0)

        with mock.patch.object(DK.subprocess, "run", run):
            self.assertTrue(DK.run_powershell("Write-Host 'a \"b\"'"))
        self.assertIn("-EncodedCommand", seen["args"])
        import base64
        said = base64.b64decode(seen["args"][-1]).decode("utf-16-le")
        self.assertEqual(said, "Write-Host 'a \"b\"'")

    def test_no_powershell_is_a_plain_no_not_a_crash(self):
        with mock.patch.object(DK.subprocess, "run", side_effect=OSError("no")):
            self.assertFalse(DK.run_powershell("x"))


class OneCopyAtATime(_Tmp):
    def test_a_second_start_finds_the_port_the_first_wrote_down(self):
        os.makedirs(self.env["PM_DATA"])
        with open(os.path.join(self.env["PM_DATA"], "desktop.pid"), "w") as fh:
            fh.write("1234\n8081\n")
        self.assertEqual(DK.running_port(self.env), 8081)

    def test_no_note_means_no_port_rather_than_an_error(self):
        self.assertEqual(DK.running_port(self.env), 0)

    def test_a_busy_port_is_passed_over(self):
        launcher = _load("pm_launcher", os.path.join(WINDOWS, "PhotoManager.pyw"))
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
            taken.bind(("", 0))
            taken.listen(1)
            port = taken.getsockname()[1]
            self.assertNotEqual(launcher.free_port(port), port)

    def test_the_tray_loads_anywhere_and_says_no_copy_is_running_off_windows(self):
        tray = _load("pm_tray", os.path.join(WINDOWS, "tray.py"))
        if not sys.platform.startswith("win"):
            self.assertFalse(tray.already_running())
        self.assertTrue(tray.MUTEX_NAME.startswith("Local\\"))


class TheTrayItself(unittest.TestCase):
    """Only Windows can run the tray, but its set-up can be checked anywhere."""

    class _Unhashable:
        """What a ctypes function pointer is: settable, callable, unhashable."""
        __hash__ = None

    class _Library:
        def __init__(self):
            self.made = {}

        def __getattr__(self, name):
            return self.made.setdefault(name, TheTrayItself._Unhashable())

    def test_every_windows_call_gets_its_types_without_hashing_them(self):
        """It once kept them in a dict keyed by the functions, which cannot
        be hashed: the icon never appeared on a real PC, and nothing here
        noticed because nothing built a Tray."""
        import ctypes
        tray = _load("pm_tray_bind", os.path.join(WINDOWS, "tray.py"))
        libraries = {}
        with mock.patch.object(ctypes, "WinDLL",
                               lambda name, **kw: libraries.setdefault(
                                   name, self._Library()), create=True), \
                mock.patch.object(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE,
                                  create=True):
            made = tray.Tray("x.ico", lambda: [], lambda what: None)
        shell = libraries["shell32"].made["Shell_NotifyIconW"]
        self.assertEqual(len(shell.argtypes), 2)
        self.assertIs(made.user32, libraries["user32"])
        for library in libraries.values():
            for name, fn in library.made.items():
                self.assertTrue(hasattr(fn, "argtypes"), name)
                self.assertTrue(hasattr(fn, "restype"), name)

    @unittest.skipUnless(sys.platform.startswith("win"), "Windows only")
    def test_on_windows_the_icon_goes_up_and_comes_down(self):
        tray = _load("pm_tray_real", os.path.join(WINDOWS, "tray.py"))
        seen = {}

        def ready(icon):
            seen["added"] = icon._added
            threading.Timer(0.5, icon.close).start()

        icon = tray.Tray(os.path.join(WINDOWS, "PhotoManager.ico"),
                         lambda: [{"id": "quit", "label": "Quit"}],
                         lambda what: None, tip=lambda: "test")
        icon.run(ready)
        self.assertTrue(seen.get("added"))
        self.assertFalse(icon._added)


class Quitting(unittest.TestCase):
    def test_the_icon_is_taken_away_before_the_program_goes(self):
        """An icon left behind stays by the clock until the mouse crosses it,
        and looks like the program is still running."""
        order = []
        with mock.patch.object(DK, "_ON_QUIT", []), \
                mock.patch.object(DK.os, "_exit", lambda code: order.append(code)):
            DK.on_quit(lambda: order.append("icon"))
            DK.on_quit(lambda: 1 / 0)               # one failing hook is not all
            DK.on_quit(lambda: order.append("more"))
            DK.quit(0)
        self.assertEqual(order, ["icon", "more", 0])

    def test_the_server_counts_what_is_still_running(self):
        busy = mock.Mock(busy=lambda: True)
        idle = mock.Mock(busy=lambda: False)
        copying = mock.Mock(finished=False)
        with mock.patch.dict(SRV.JOBS, {"a": busy, "b": idle}, clear=True), \
                mock.patch.dict(SRV.FILE_JOBS, {"c": copying}, clear=True):
            self.assertEqual(SRV.work_in_flight(), 2)
        with mock.patch.dict(SRV.JOBS, {}, clear=True), \
                mock.patch.dict(SRV.FILE_JOBS, {}, clear=True):
            self.assertEqual(SRV.work_in_flight(), 0)


class QuitFromThePage(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="desktop-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = self.dir
        os.environ[DK.FLAG] = "1"
        SRV.ALLOWED_ROOTS[:] = []
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), SRV.Handler)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        os.environ.pop(DK.FLAG, None)
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_it_goes_the_same_way_as_the_tray_so_the_icon_goes_too(self):
        called = threading.Event()
        with mock.patch.object(DK, "quit", lambda *a: called.set()):
            req = urllib.request.Request(self.base + "/api/quit", data=b"{}",
                                         headers={"Content-Type":
                                                  "application/json"},
                                         method="POST")
            with urllib.request.urlopen(req, timeout=10) as r:
                self.assertTrue(json.loads(r.read())["stopping"])
            self.assertTrue(called.wait(5))


class TheDiskBehindAPC(unittest.TestCase):
    """SV3: a PC program with no ALLOWED_ROOTS served the whole disk to the
    Wi-Fi. It is fenced to the folders chosen in Setup now."""

    def setUp(self):
        from core import settings as S
        self.S = S
        self.dir = tempfile.mkdtemp(prefix="desktop-fence-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        os.environ[DK.FLAG] = "1"
        SRV.ALLOWED_ROOTS[:] = []
        self.lib = os.path.join(self.dir, "Photos")
        self.other = os.path.join(self.dir, "Documents")
        for where in (self.lib, self.other):
            os.makedirs(where)
            with open(os.path.join(where, "a.jpg"), "wb") as fh:
                fh.write(b"\xff\xd8 not much of a photo")
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), SRV.Handler)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        os.environ.pop(DK.FLAG, None)
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def code(self, path):
        import urllib.error
        import urllib.parse
        url = self.base + "/api/download?" + urllib.parse.urlencode({"path": path})
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    def post(self, route, body):
        req = urllib.request.Request(self.base + route, json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())

    def test_with_nothing_chosen_nothing_is_downloadable(self):
        self.assertEqual(self.code(os.path.join(self.other, "a.jpg")), 403)
        self.assertEqual(SRV.shown_fence(), [])

    def test_a_file_outside_the_trees_is_refused_and_one_inside_is_not(self):
        self.S.save({"library": self.lib})
        self.assertEqual(self.code(os.path.join(self.lib, "a.jpg")), 200)
        self.assertEqual(self.code(os.path.join(self.other, "a.jpg")), 403)

    def test_also_allowed_lets_a_folder_in(self):
        self.S.save({"library": self.lib, "also_allowed": self.other})
        self.assertEqual(self.code(os.path.join(self.other, "a.jpg")), 200)

    def test_setup_can_still_move_the_library_from_this_pc(self):
        """Checked against the fence it draws, the library could never move."""
        self.S.save({"library": self.lib})
        got = self.post("/api/save", {"task": "setup",
                                      "options": {"library": self.other}})
        self.assertTrue(got.get("saved"), got)
        self.assertEqual(self.code(os.path.join(self.other, "a.jpg")), 200)
        self.assertEqual(self.code(os.path.join(self.lib, "a.jpg")), 403)

    def test_but_not_from_another_machine_without_a_password(self):
        from app import registry as R
        self.S.save({"library": self.lib})
        setup = R.get("setup")
        self.assertIsNotNone(SRV.check_paths(setup, {"library": self.other}))
        self.assertIsNone(SRV.check_paths(setup, {"library": self.other},
                                          choosing=True))
        phone = mock.Mock(_who=lambda: "192.168.1.30")
        self.assertFalse(SRV.Handler._at_this_machine(phone))
        here = mock.Mock(_who=lambda: "127.0.0.1")
        self.assertTrue(SRV.Handler._at_this_machine(here))

    def test_any_other_task_answers_to_the_fence(self):
        from app import registry as R
        self.S.save({"library": self.lib})
        said = SRV.check_paths(R.get("cull"), {"folder": self.other},
                               choosing=True)
        self.assertIn("Also allowed", said or "")

    def test_the_also_allowed_box_is_drawn_on_a_pc_and_not_on_the_nas(self):
        def boxes():
            with urllib.request.urlopen(self.base + "/api/tasks", timeout=20) as r:
                tasks = json.loads(r.read())["tasks"]
            setup = next(t for t in tasks if t["name"] == "setup")
            return ([o["name"] for o in setup["options"]],
                    [o["name"] for g in setup["groups"] for o in g["options"]])
        flat, grouped = boxes()
        self.assertIn("also_allowed", flat)
        self.assertIn("also_allowed", grouped)
        os.environ.pop(DK.FLAG, None)
        flat, grouped = boxes()
        self.assertNotIn("also_allowed", flat)
        self.assertNotIn("also_allowed", grouped)

    def test_the_nas_has_no_fence_but_its_own(self):
        os.environ.pop(DK.FLAG, None)
        self.assertEqual(SRV.fence(), [])
        SRV.ALLOWED_ROOTS[:] = [os.path.realpath(self.other)]
        try:
            os.environ[DK.FLAG] = "1"
            self.assertEqual(SRV.fence(), [os.path.realpath(self.other)])
        finally:
            SRV.ALLOWED_ROOTS[:] = []


class TheAppIcon(unittest.TestCase):
    PATH = os.path.join(WINDOWS, "PhotoManager.ico")

    def _sizes(self):
        with open(self.PATH, "rb") as fh:
            data = fh.read()
        reserved, kind, count = struct.unpack_from("<HHH", data, 0)
        self.assertEqual((reserved, kind), (0, 1))          # an icon, not a cursor
        sizes = []
        for n in range(count):
            w, h = struct.unpack_from("<BB", data, 6 + 16 * n)
            size, offset = struct.unpack_from("<II", data, 6 + 16 * n + 8)
            self.assertLessEqual(offset + size, len(data))
            sizes.append((w or 256, h or 256))
        return sizes

    def test_there_is_one_for_shortcuts_and_the_tray(self):
        self.assertTrue(os.path.exists(self.PATH))

    def test_it_has_every_size_windows_asks_for(self):
        """16 to 32 in the tray (more at higher scaling), 48 on the desktop,
        256 in Explorer's large views. A missing size is a blurry stretch."""
        sizes = self._sizes()
        for n in (16, 20, 24, 32, 48, 256):
            self.assertIn((n, n), sizes)

    def test_it_is_made_by_the_tool_that_makes_the_other_icons(self):
        tool = _read(os.path.join(HERE, "tools", "make_icon.py"))
        self.assertIn("PhotoManager.ico", tool)

    def test_git_keeps_it_byte_for_byte(self):
        attrs = _read(os.path.join(HERE, ".gitattributes"))
        self.assertIn("*.ico binary", attrs)


class TheWindowsFolder(unittest.TestCase):
    def test_the_readme_names_every_file_and_every_file_is_there(self):
        readme = _read(os.path.join(WINDOWS, "README.md"))
        for name in ("PhotoManager.pyw", "tray.py", "PhotoManager.ico",
                     "shortcuts.py", "wheels", "Install.bat", "Uninstall.bat",
                     "Stop.bat"):
            self.assertTrue(os.path.exists(os.path.join(WINDOWS, name)), name)
            self.assertIn(name, readme)

    def test_the_installer_hands_the_shortcuts_to_the_tested_code(self):
        bat = _read(os.path.join(WINDOWS, "Install.bat"))
        self.assertIn("shortcuts.py\" install", bat)
        self.assertIn("pillow", bat.lower())
        bat = _read(os.path.join(WINDOWS, "Uninstall.bat"))
        self.assertIn("shortcuts.py\" remove", bat)

    def test_the_installer_skips_pillow_when_it_is_there_and_shows_progress(self):
        """Found on a real PC: with --quiet, a slow download sat on one line
        with nothing moving and looked exactly like a hang."""
        bat = _read(os.path.join(WINDOWS, "Install.bat"))
        self.assertIn('-c "import PIL"', bat)
        self.assertLess(bat.index("import PIL"), bat.index("pip install"))
        self.assertNotIn("--quiet", bat)
        self.assertIn("--timeout", bat)

    def test_pillow_comes_with_it_and_is_installed_without_the_internet(self):
        """Shipped rather than downloaded half way through installing: an
        installer that needs the internet is one that stalls on a slow line."""
        bat = _read(os.path.join(WINDOWS, "Install.bat"))
        offline = bat.index("--no-index")
        self.assertIn('--find-links "%~dp0wheels"', bat)
        self.assertIn("--require-hashes", bat[offline:bat.index("\n", offline)])
        online = bat.index("--timeout")
        self.assertLess(offline, online, "the bundled copy is tried first")

    def test_there_is_a_bundled_pillow_for_every_python_the_readme_accepts(self):
        import glob
        wheels = [os.path.basename(w) for w in
                  glob.glob(os.path.join(WINDOWS, "wheels", "pillow-*.whl"))]
        for tag in ("cp311", "cp312", "cp313", "cp314"):
            self.assertTrue([w for w in wheels
                             if f"-{tag}-{tag}-win_amd64.whl" in w], tag)

    def test_the_heic_reader_comes_with_it_for_every_python_too(self):
        """pi-heif is what lets Pillow open an iPhone's HEIC. On a PC there are
        no NAS-made thumbnails to borrow, so without it they stay blank."""
        import glob
        wheels = [os.path.basename(w) for w in
                  glob.glob(os.path.join(WINDOWS, "wheels", "pi_heif-*.whl"))]
        for tag in ("cp311", "cp312", "cp313", "cp314"):
            self.assertTrue([w for w in wheels
                             if f"-{tag}-{tag}-win_amd64.whl" in w], tag)
        self.assertIn("pi-heif==", _read(os.path.join(WINDOWS, "wheels",
                                                      "requirements.txt")))

    def test_an_install_with_pillow_but_no_heic_reader_still_gets_one(self):
        """Checking for Pillow alone would skip every PC that installed
        before HEIC support arrived."""
        bat = _read(os.path.join(WINDOWS, "Install.bat"))
        self.assertIn('-c "import pi_heif"', bat)
        self.assertLess(bat.index("import pi_heif"), bat.index("pip install"))

    def test_a_python_without_a_heic_build_still_gets_pillow(self):
        """The download is two installs, so one that fails cannot take the
        other with it."""
        bat = _read(os.path.join(WINDOWS, "Install.bat"))
        online = bat[bat.index("--timeout"):]
        self.assertLess(online.index("2 pillow"), online.index("2 pi-heif"))

    def test_every_label_in_a_bat_file_is_there_once_and_no_bracket_is_stray(self):
        """Install.bat once carried a second, half-merged copy of its install
        block: `goto :shortcuts` landed on the first label and ran pip again,
        and a lone `)` sat under it."""
        import glob
        import re
        for bat in glob.glob(os.path.join(WINDOWS, "*.bat")):
            text = _read(bat)
            labels = re.findall(r"(?m)^:(\w+)\s*$", text)
            self.assertEqual(len(labels), len(set(labels)),
                             f"{os.path.basename(bat)}: {labels}")
            depth = 0
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("rem ") or stripped.startswith("echo"):
                    continue
                depth -= stripped.startswith(")")          # `) else (` too
                self.assertGreaterEqual(depth, 0,
                                        f"{os.path.basename(bat)}: a stray )")
                depth += stripped.endswith("(")
            self.assertEqual(depth, 0, os.path.basename(bat))

    def test_every_bundled_file_matches_the_hash_it_is_installed_against(self):
        """--require-hashes refuses anything else, so a wrong hash here is an
        installer that silently falls back to the internet."""
        import glob
        import hashlib
        import re
        wanted = set(re.findall(r"sha256:([0-9a-f]{64})", _read(
            os.path.join(WINDOWS, "wheels", "requirements.txt"))))
        found = set()
        for wheel in glob.glob(os.path.join(WINDOWS, "wheels", "*.whl")):
            with open(wheel, "rb") as fh:
                found.add(hashlib.sha256(fh.read()).hexdigest())
        self.assertTrue(found)
        self.assertEqual(found, wanted)

    def test_they_are_made_by_a_tool_and_kept_byte_for_byte(self):
        self.assertTrue(os.path.exists(os.path.join(HERE, "tools",
                                                    "fetch_wheels.py")))
        self.assertIn("*.whl binary", _read(os.path.join(HERE, ".gitattributes")))

    def test_updating_pillow_from_the_app_is_on_the_roadmap(self):
        roadmap = _read(os.path.join(HERE, "docs", "ROADMAP.md"))
        self.assertIn("Update Pillow from inside Photo Manager", roadmap)

    def test_password_storage_and_https_are_on_the_roadmap(self):
        roadmap = _read(os.path.join(HERE, "docs", "ROADMAP.md"))
        self.assertIn("### Stronger password storage", roadmap)
        self.assertIn("### HTTPS for the browser", roadmap)

    def test_the_python_files_are_valid_python(self):
        import ast
        for name in ("PhotoManager.pyw", "tray.py", "shortcuts.py"):
            ast.parse(_read(os.path.join(WINDOWS, name)))


if __name__ == "__main__":
    unittest.main()
