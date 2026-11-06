"""Settings that save when you press Save - and lock while the loop is running.

Two complaints, one cause. Setup did save what you typed, but only as a side
effect of pressing "Show me what would happen" - a button whose words promise
that NOTHING will be done. So a path typed and then walked away from was lost
without a word, and the honest reading of the tab was that it remembered
nothing. A settings tab now has a Save button that saves, and no preview button
at all, because there is nothing to preview about writing a path down.

The other half is the opposite risk. The Automation settings are read by a
thread that wakes on its own, so a form you can edit while it is running is a
form that will be half-changed when the next pass fires - three steps of a loop
running against a mixture of what you meant and what was there before. They are
locked while the switch is on, and the tab says why rather than simply refusing
to be typed into.
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R             # noqa: E402
import app.tasks                          # noqa: E402,F401
from app import page as P                 # noqa: E402
from app import server as SRV             # noqa: E402
from app.tasks import automation as AUTO  # noqa: E402
from core import settings as S            # noqa: E402


class Served(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="saving-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.prev = os.path.join(self.dir, "Previews")
        self.raw = os.path.join(self.dir, "Raw")
        for d in (self.lib, self.prev, self.raw):
            os.makedirs(d)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), SRV.Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}/"
        threading.Thread(target=self.httpd.serve_forever,
                         kwargs={"poll_interval": 0.02}, daemon=True).start()

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)
        SRV.ALLOWED_ROOTS.clear()

    def post(self, path, obj):
        req = urllib.request.Request(self.base + path, json.dumps(obj).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as f:
            return json.load(f)

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as f:
            return json.load(f)


class Saving(Served):
    # ------------------------------------------------------------------ saving

    def test_pressing_save_on_setup_writes_the_paths(self):
        got = self.post("api/save", {"task": "setup",
                                     "options": {"library": self.lib,
                                                 "previews": self.prev,
                                                 "raw": self.raw}})
        self.assertTrue(got.get("saved"), got)
        saved = S.load()
        self.assertEqual(saved["library"], self.lib)
        self.assertEqual(saved["previews"], self.prev)

    def test_and_the_next_tab_opens_with_them_already_in_its_boxes(self):
        """The whole point of Setup. A value that saves but does not reach the
        other forms is a value that saved nowhere anybody can see."""
        self.post("api/save", {"task": "setup",
                               "options": {"library": self.lib,
                                           "previews": self.prev}})
        tasks = self.get("api/tasks")
        step = [t for t in tasks["tasks"] if t["name"] == "ratings"][0]
        box = [o for o in step["options"] if o["name"] == "folder"][0]
        self.assertEqual(box["default"], self.prev)

    def test_a_refusal_saves_nothing_and_says_so(self):
        """A settings tab still has to be able to refuse - a library that is not
        there is worth catching once, here, rather than in six tabs later."""
        got = self.post("api/save", {"task": "setup",
                                     "options": {"library": os.path.join(
                                         self.dir, "nowhere at all")}})
        self.assertFalse(got.get("saved"))
        self.assertTrue(got.get("blocked"), got)
        self.assertNotEqual(S.load()["library"],
                            os.path.join(self.dir, "nowhere at all"))

    def test_a_save_that_fails_is_not_reported_as_saved(self):
        """The quiet version of the bug this whole batch is about: a Save button
        that says "Saved." whatever happened is exactly as useless as no button,
        and worse, because now you believe it."""
        import core.settings as _s
        was = _s.save

        def refuse(*a, **k):
            raise OSError("read-only file system")
        _s.save = refuse
        try:
            got = self.post("api/save", {"task": "labels",
                                         "options": {"label_red_name": "Print"}})
        finally:
            _s.save = was
        self.assertFalse(got.get("saved"), got)
        self.assertTrue(any("read-only" in d
                            for d in got.get("result", {}).get("details", [])),
                        got.get("result"))

    def test_a_tab_that_is_not_a_settings_tab_will_not_save(self):
        """Otherwise Save becomes a second, quieter way to run something."""
        try:
            self.post("api/save", {"task": "ratings", "options": {}})
            self.fail("a working tab accepted a save")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 400)

    def test_saving_the_colour_meanings_keeps_them(self):
        got = self.post("api/save", {"task": "labels",
                                     "options": {"label_red_name": "Print",
                                                 "label_blue_name": "Sharpen"}})
        self.assertTrue(got.get("saved"), got)
        self.assertEqual(S.load()["label_red_name"], "Print")

    # ------------------------------------------------------- no false promises

    def test_no_settings_tab_offers_to_show_what_would_happen(self):
        """"Show me what would happen" on a tab whose only effect is writing a
        settings file is a button that describes nothing and, worse, was the
        only thing that actually saved."""
        for t in R.all_tasks():
            if not t.settings:
                continue
            if t.writes:
                self.assertTrue(t.run_label,
                                f"{t.name} both saves and does something, so its "
                                f"button has to say which")
            else:
                self.assertFalse(t.writes, t.name)

    def test_automations_button_says_what_it_actually_does(self):
        self.assertEqual(R.get("automation").run_label, "Run one pass now")

    def test_the_page_draws_a_save_button_for_a_settings_tab(self):
        self.assertIn('id="save"', P.PAGE)
        self.assertIn("api/save", P.PAGE)

    # ----------------------------------------------------------------- locking

    def test_the_automation_tab_is_now_only_a_chooser_and_a_button(self):
        """The steps moved. They used to be nine options on this tab, locked
        while the loop ran; a flow is assembled on the Flows tab now, so what is
        left here is which flow and one press."""
        names = [o.name for o in R.get("automation").options]
        self.assertEqual(names, ["which", "apply_now"])

    def test_a_running_flow_has_its_steps_locked_and_says_why(self):
        """Same reasoning as before: a form you can edit while it is firing
        invites you to wonder which version just ran."""
        self.assertIn("flowLocked", P.PAGE)
        self.assertIn("Turn it off above to change them", P.PAGE)

    def test_and_a_flow_is_written_whole_so_a_half_change_cannot_run(self):
        """The belt under the braces. The lock is a signal; this is the reason a
        pass can never see a flow somebody was half way through editing."""
        import inspect
        from core import flows as FL
        source = inspect.getsource(FL.write)
        self.assertIn("os.replace", source)

    def test_the_switch_is_on_the_flow_itself(self):
        """A tab whose first question is the interval is a tab you cannot tell
        the state of at a glance. The flow carries its own switch now, beside
        its name, and the Automation tab reports it."""
        from core import flows as FL
        from dataclasses import fields
        self.assertIn("on", {f.name for f in fields(FL.Flow)})

    def test_the_plan_says_plainly_whether_it_is_on(self):
        from core import flows as FL
        S.save({"library": self.lib, "previews": self.prev})
        flow = FL.read()[0]
        flow.on = False
        FL.write([flow])
        p = R.get("automation").make_plan({})
        self.assertEqual(dict(p.stats)["Running by itself"], "off")
        self.assertTrue(any("IT IS OFF" in n for n in p.notes), p.notes)
        flow.on = True
        FL.write([flow])
        p = R.get("automation").make_plan({})
        self.assertEqual(dict(p.stats)["Running by itself"], "ON")
        self.assertTrue(any("IT IS ON" in n for n in p.notes), p.notes)

    # ------------------------------------------------------------ file picking

    def test_every_path_box_in_the_app_can_be_browsed_to(self):
        """A box you have to type a full path into from memory is a box that
        gets a wrong path typed into it."""
        # Every kind of path box the app declares, and the page's answer for it.
        drawn = {"folder": "browse(", "folders": "Add a folder",
                 "file": "kind === \"file\""}
        kinds = {o.kind for t in R.all_tasks() for o in t.options
                 if o.kind in drawn}
        self.assertIn("file", kinds, "no file box left to check")
        for k in kinds:
            self.assertIn(drawn[k], P.PAGE, f"a {k} box has no way to browse")
        self.assertIn("pickFiles", P.PAGE)

    def test_browsing_for_a_file_lists_files_as_well_as_folders(self):
        open(os.path.join(self.lib, "a.jpg"), "wb").write(b"x")
        open(os.path.join(self.lib, "notes.txt"), "wb").write(b"x")
        got = SRV.browse(self.lib, want_files=".jpg")
        names = [f["name"] for f in got.get("files", [])]
        self.assertIn("a.jpg", names)
        self.assertNotIn("notes.txt", names)

    def test_and_lists_everything_when_no_suffix_is_asked_for(self):
        open(os.path.join(self.lib, "a.jpg"), "wb").write(b"x")
        open(os.path.join(self.lib, "notes.txt"), "wb").write(b"x")
        got = SRV.browse(self.lib, want_files="*")
        names = [f["name"] for f in got.get("files", [])]
        self.assertIn("notes.txt", names)

    def test_folder_browsing_still_does_not_list_files(self):
        open(os.path.join(self.lib, "a.jpg"), "wb").write(b"x")
        got = SRV.browse(self.lib)
        self.assertFalse(got.get("files"))

    def test_up_from_the_top_of_a_windows_drive_is_the_list_of_drives(self):
        """`dirname("C:")` is `C:`, which Windows reads as "wherever C: was
        last" - so "up one level" from a drive opened a random folder on it
        instead of going back to the drives."""
        import ntpath
        self.assertEqual(SRV.parent_of("C:\\", ntpath), "")
        self.assertEqual(SRV.parent_of("C:\\Photos", ntpath), "C:\\")
        self.assertEqual(SRV.parent_of("N:\\Photos\\2024\\", ntpath), "N:\\Photos")
        # and the top of a network share is a top too
        self.assertEqual(SRV.parent_of("\\\\nas\\photos", ntpath), "")
        self.assertEqual(SRV.parent_of("\\\\nas\\photos\\2024", ntpath),
                         "\\\\nas\\photos\\")

    def test_a_bare_drive_letter_means_the_top_of_that_drive(self):
        import ntpath, posixpath
        self.assertEqual(SRV.drive_root("C:", ntpath), "C:\\")
        self.assertEqual(SRV.drive_root("C:\\Photos", ntpath), "C:\\Photos")
        # not a drive letter anywhere else
        self.assertEqual(SRV.drive_root("C:", posixpath), "C:")

    def test_up_on_this_machine_still_works_the_way_it_did(self):
        import posixpath
        self.assertEqual(SRV.parent_of("/", posixpath), "")
        self.assertEqual(SRV.parent_of("/volume1", posixpath), "/")
        self.assertEqual(SRV.parent_of("/volume1/photos/", posixpath), "/volume1")
        self.assertEqual(SRV.browse(self.lib)["parent"],
                         os.path.dirname(self.lib.rstrip(os.sep)))


class ChangingTheLibrary(Served):
    """ALI changed the library in Setup and Search went on searching the old
    one. The forms are the page's half (test_page_behaviour); this is the
    server's: it says when the settings changed, and the index follows the
    library at once instead of on its next minute."""

    FIX = os.path.join(os.path.dirname(__file__), "fixtures")

    def setUp(self):
        super().setUp()
        from core import catalogue as C
        self.C = C
        self.new = os.path.join(self.dir, "New library")
        os.makedirs(self.new)
        for where, name in ((self.lib, "plain"), (self.new, "rated")):
            shutil.copy(os.path.join(self.FIX, name + ".jpg"),
                        os.path.join(where, name + ".JPG"))
        S.save({"library": self.lib})
        C.forget_all()
        C.shared().refresh([self.lib])
        SRV.INDEX_NUDGE.clear()

    def tearDown(self):
        cat = self.C.shared()
        cat.stop()
        cat.wait(10)
        self.C.forget_all()
        super().tearDown()

    def indexed(self):
        return sorted(os.path.basename(p) for p in self.C.shared().files)

    def test_health_says_which_settings_the_page_is_looking_at(self):
        was = self.get("api/health")["settings"]
        self.assertTrue(was)
        self.assertEqual(self.get("api/tasks")["settings"], was)
        self.post("api/save", {"task": "setup", "options": {"library": self.new}})
        self.assertNotEqual(self.get("api/health")["settings"], was)

    def test_saving_a_new_library_drops_the_old_one_before_answering(self):
        self.assertEqual(self.indexed(), ["plain.JPG"])
        got = self.post("api/save", {"task": "setup",
                                     "options": {"library": self.new}})
        self.assertTrue(got.get("saved"), got)
        self.assertEqual(self.indexed(), [])
        self.assertTrue(SRV.INDEX_NUDGE.is_set())     # the loop looks now

    def test_and_the_next_look_reads_the_new_one_without_waiting(self):
        self.post("api/save", {"task": "setup", "options": {"library": self.new}})
        self.assertEqual(SRV.look_at_index(due=False), "started")
        self.C.shared().wait(20)
        self.assertEqual(self.indexed(), ["rated.JPG"])
        self.assertEqual(SRV.look_at_index(due=False), "")

    def test_a_change_made_elsewhere_is_followed_too(self):
        """The sample library borrowing the trees, or the command line."""
        S.save({"library": self.new})
        self.assertEqual(SRV.look_at_index(due=False), "started")
        self.C.shared().wait(20)
        self.assertEqual(self.indexed(), ["rated.JPG"])

    def test_a_pass_over_the_old_library_is_stopped(self):
        cat = self.C.shared()
        cat.busy = lambda: True                       # still reading the old one
        cat._for = [self.lib]
        S.save({"library": self.new})
        self.assertEqual(SRV.look_at_index(due=False), "stopped")
        self.assertTrue(cat._stop)
        del cat.busy

    def test_a_stale_index_still_waits_for_its_minute(self):
        """A run marks the index stale, and a flow of six steps should not
        rebuild it six times - only the library moving skips the wait."""
        self.C.shared().touch()
        self.assertEqual(SRV.look_at_index(due=False), "")
        self.assertEqual(SRV.look_at_index(due=True), "started")

    def test_a_photograph_copied_in_from_outside_is_found_on_the_timer(self):
        """A card copied over SMB or a phone backup tells this app nothing, so
        nothing marks the index stale. The timer walks it anyway."""
        cat = self.C.shared()
        shutil.copy(os.path.join(self.FIX, "aeb1.jpg"),
                    os.path.join(self.lib, "arrived.JPG"))
        self.assertFalse(cat.stale)
        self.assertEqual(SRV.look_at_index(due=True), "")   # walked just now
        cat.when = time.time() - SRV.INDEX_REWALK - 1
        self.assertEqual(SRV.look_at_index(due=False), "")  # only on the minute
        self.assertEqual(SRV.look_at_index(due=True), "started")
        cat.wait(20)
        self.assertEqual(self.indexed(), ["arrived.JPG", "plain.JPG"])

    def test_no_library_at_all_empties_the_index(self):
        S.save({"library": ""})
        self.assertEqual(SRV.look_at_index(due=False), "cleared")
        self.assertEqual(self.indexed(), [])


if __name__ == "__main__":
    unittest.main()
