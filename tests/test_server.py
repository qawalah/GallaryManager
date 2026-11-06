"""The web page's side of things: preview, apply, watch, stop.

Tested over real HTTP against a real server on a spare port, because the parts
worth checking are the ones between the browser and the task - that a plan is
remembered rather than sent back and forth, that Apply runs the plan that was
SHOWN, and that a folder outside the allowed roots is refused.
"""

import base64
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import server as S               # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Served(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="server-")
        self._was_data = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        for n in ("aeb1", "aeb2", "aeb3"):
            shutil.copy(os.path.join(FIX, f"{n}.jpg"), os.path.join(self.shoot, f"{n}.JPG"))
            shutil.copy(os.path.join(FIX, f"{n}.jpg"), os.path.join(self.shoot, f"{n}.RW2"))
        # What every real install has, and what every mirroring task now insists
        # on: without a library there is nothing to measure a folder's position
        # from, and rather than landing everything flat in the top of the other
        # tree those tasks refuse.
        from core import settings as _settings
        _settings.save({"library": self.lib, "raw": self.raw})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}/"
        # a short poll interval only so tearDown's shutdown() is quick
        threading.Thread(target=self.httpd.serve_forever,
                         kwargs={"poll_interval": 0.02}, daemon=True).start()

    def tearDown(self):
        if self._was_data is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was_data
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)
        S.ALLOWED_ROOTS.clear()
        with S.JOBS_LOCK:
            S.JOBS.clear()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as f:
            return json.load(f)

    def post(self, path, obj):
        req = urllib.request.Request(self.base + path, json.dumps(obj).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as f:
            return json.load(f)

    def preview(self, task, timeout=20, **options):
        """Ask for a plan and wait for it.

        Planning is a background job now - a Library survey over SMB is work,
        not a question with an instant answer - so the plan arrives through the
        same progress route the applying half uses. The wait belongs here rather
        than in every test.
        """
        started = self.post("api/plan", {"task": task, "options": options})
        if not started.get("id"):
            # A refusal comes back as a whole plan carrying a BLANK id rather
            # than as a bare error, because the page draws a plan and choked on
            # half of one. Blank, not absent - so this asks the same question
            # the page asks, and not a different one that used to agree with it.
            return started
        until = time.time() + timeout
        while time.time() < until:
            state = self.get("api/progress?id=" + started["id"])
            if state.get("error"):
                return {"error": state["error"]}
            if state.get("phase") != "planning":
                return state.get("plan", {})
            time.sleep(0.02)
        self.fail(f"planning {task} never finished")

    def finish(self, plan_id, timeout=10):
        self.post("api/apply", {"id": plan_id})
        until = time.time() + timeout
        while time.time() < until:
            state = self.get("api/progress?id=" + plan_id)
            if state["finished"]:
                return state
            time.sleep(0.02)
        self.fail("the run never finished")

    def tree(self, root):
        out = []
        for here, _dirs, names in os.walk(root):
            for n in names:
                out.append(os.path.relpath(os.path.join(here, n), root).replace("\\", "/"))
        return sorted(out)


class ThePageLoads(Served):
    def test_the_html_is_served(self):
        with urllib.request.urlopen(self.base) as f:
            body = f.read().decode()
        self.assertIn("Photo Manager", body)

    def test_every_task_is_offered_with_a_form(self):
        info = self.get("api/tasks")
        names = [t["name"] for t in info["tasks"]]
        for expected in ("unpair", "cull", "ratings", "remirror", "geotag", "previews"):
            self.assertIn(expected, names)
        for t in info["tasks"]:
            self.assertTrue(t["title"])
            for o in t["options"]:
                self.assertTrue(o["label"], f"{t['name']}.{o['name']}")


class KnowingWhatIsRunning(Served):
    """Three faults that look identical from the outside, separated.

    Copy new files to the NAS, hit Restart, open the page: it looks exactly the
    same whether the new code loaded, the copy went to the wrong folder, or the
    browser handed you a page it remembered from an hour ago. You cannot debug
    two faults that produce one symptom, so the header states all three.
    """

    def test_the_page_is_never_cached(self):
        with urllib.request.urlopen(self.base) as f:
            self.assertIn("no-store", f.headers.get("Cache-Control", ""))

    def test_neither_is_anything_it_answers_with(self):
        for path in ("api/tasks", "api/health", "api/browse"):
            with urllib.request.urlopen(self.base + path) as f:
                self.assertIn("no-store", f.headers.get("Cache-Control", ""), path)

    def test_but_the_icons_are_cached_because_they_never_change(self):
        with urllib.request.urlopen(self.base + "icon-192.png") as f:
            self.assertIn("max-age", f.headers.get("Cache-Control", ""))

    def test_health_says_what_code_is_running_and_for_how_long(self):
        h = self.get("api/health")
        self.assertTrue(h["code"])
        self.assertTrue(h["started"])
        self.assertIsInstance(h["uptime"], int)

    def test_a_folder_that_is_not_there_is_stated_not_left_to_be_discovered(self):
        """The NAS failure exactly: ALLOWED_ROOTS naming a folder no volume
        mounts. From inside the container that is indistinguishable from a typo,
        so the app cannot say why - but it must say THAT, instead of letting it
        be found one Browse click at a time."""
        S.ALLOWED_ROOTS[:] = [os.path.join(self.dir, "not-mounted")]
        h = self.get("api/health")
        self.assertFalse(h["folders"][0]["there"])
        self.assertIn("not-mounted", h["trouble"])
        self.assertIn("Build", h["trouble"])        # how to make a mount change take

    def test_and_folders_that_are_there_say_nothing(self):
        S.ALLOWED_ROOTS[:] = [os.path.realpath(self.lib)]
        h = self.get("api/health")
        self.assertTrue(h["folders"][0]["there"])
        self.assertEqual(h["trouble"], "")

    def test_the_page_offers_a_refresh_that_cannot_be_served_from_cache(self):
        with urllib.request.urlopen(self.base) as f:
            body = f.read().decode()
        self.assertIn('id="reload"', body)
        self.assertIn("location.replace", body)


class ResultsThatSurviveASwitch(Served):
    """Switching tab and losing a result you waited two minutes for is not a
    small annoyance - it is the reason you stop switching tabs, and half of this
    app is about opening one feature because of what another one told you.

    The page is what keeps them, so what is testable here is that the page ships
    the machinery: per-task memory, a run watched independently of what is on
    screen, and the marks in the Library tree being links to the feature that
    changes them."""

    def page(self):
        with urllib.request.urlopen(self.base) as f:
            return f.read().decode()

    def test_each_tab_keeps_its_own_form_and_result(self):
        body = self.page()
        self.assertIn("const SEEN", body)
        # defined AND called on the way out of a tab - a helper nothing calls
        # is the shape this bug would take if it came back
        showing = body[body.index("function show(name)"):]
        self.assertIn("keepWhereYouWere()", showing[:600])

    def test_a_run_is_watched_by_id_not_by_what_is_on_screen(self):
        """A run belongs to a task, not to whatever tab is open. Look elsewhere
        while it works and it keeps working; come back and it is there."""
        body = self.page()
        self.assertIn("WATCH", body)
        self.assertIn("WATCH.task", body)

    def test_a_status_mark_carries_the_feature_that_changes_it(self):
        """You spot that Italy is half geotagged; the next thing you want is to
        geotag Italy. The icon that told you is the thing you press."""
        body = self.page()
        for mark, task in (("separated", "unpair"), ("located", "geotag"),
                           ("rated", "ratings"), ("previews", "previews"),
                           ("culled", "cull")):
            row = [l for l in body.splitlines() if f'"{mark}"' in l and "MARKS" not in l]
            self.assertTrue(any(f'"{task}"' in l for l in row),
                            f"{mark} does not name {task}")

    def test_the_page_asks_what_is_running_and_draws_a_bar(self):
        """Whichever tab started it. The page cannot know about a run begun on a
        feature it is not showing unless it asks."""
        body = self.page()
        self.assertIn('id="running"', body)
        self.assertIn("api/jobs", body)
        # asked for repeatedly, not once at start-up: a bar that is drawn on
        # load and never again shows what was running when you opened the page.
        # Repeated by a timer that sets the next one - quickly while something
        # runs, slowly when nothing does (test_page_behaviour counts them).
        self.assertIn("setTimeout(pollJobs", body)
        self.assertIn("await showRunning()", body)

    def test_the_bar_really_disappears_when_nothing_is_running(self):
        """`display:flex` beats the browser's own [hidden] rule, so hiding it
        left a strip of colour under the header with nothing in it."""
        self.assertIn("#running[hidden]", self.page())

    def test_a_line_in_that_bar_opens_the_feature_it_belongs_to(self):
        self.assertIn('onclick="show(', self.page())

    def test_the_rows_table_can_be_headed_by_the_task(self):
        """History's rows are runs, not files. A column called File over a list
        of times is the sort of small lie that makes a page feel untrustworthy."""
        self.assertIn("p.columns", self.page())


class SeeingThePhoto(Served):
    """Reading a list of file names and deciding whether to cull them is a
    guess. Seeing the photo is not - it is the one thing a preview could not do.

    But this serves files off the disk, so it gets the same guards every task
    gets, and one more: it must never become a way to read anything that is not
    a picture."""

    def fetch(self, path, query=""):
        url = self.base + "api/file?path=" + urllib.parse.quote(path) + query
        try:
            with urllib.request.urlopen(url) as f:
                return f.status, f.headers.get("Content-Type"), f.read()
        except urllib.error.HTTPError as e:
            return e.code, "", b""

    def test_a_photo_in_the_library_can_be_looked_at(self):
        photo = os.path.join(self.lib, "2022", "Spain", "aeb1.JPG")
        code, ctype, body = self.fetch(photo)
        self.assertEqual(code, 200)
        self.assertEqual(ctype, "image/jpeg")
        self.assertTrue(body.startswith(b"\xff\xd8"))

    def test_something_that_is_not_a_picture_is_refused(self):
        """Otherwise this is a way to read any file on the NAS."""
        other = os.path.join(self.dir, "notes.txt")
        with open(other, "w", encoding="utf-8") as fh:
            fh.write("private")
        self.assertEqual(self.fetch(other)[0], 415)

    def test_and_so_is_a_photo_outside_the_allowed_folders(self):
        S.ALLOWED_ROOTS[:] = [os.path.realpath(self.raw)]
        photo = os.path.join(self.lib, "2022", "Spain", "aeb1.JPG")
        self.assertEqual(self.fetch(photo)[0], 403)

    def test_a_file_that_is_not_there_is_a_404_not_a_traceback(self):
        self.assertEqual(self.fetch("/no/such/photo.jpg")[0], 404)


class AskingForAPassword(Served):
    """Off until you set one: on a home network with one person on it a login
    screen is friction for no gain. The honest position is that without it
    anyone who can reach the port can not only look at every photo but move and
    cull them - which was true long before there was a way to view one.

    The door itself is tested in `test_access.py`. What matters here is that
    this server is the thing holding it: a login on the page with an open API is
    not a login at all.
    """

    def setUp(self):
        super().setUp()
        from core import access
        access.forget()
        access.forget_misses()
        self.access = access

    def tearDown(self):
        self.access.set_password("")
        self.access.forget()
        super().tearDown()

    def test_with_no_password_set_everything_is_open(self):
        with urllib.request.urlopen(self.base) as f:
            self.assertEqual(f.status, 200)

    def test_with_one_set_the_page_becomes_the_door(self):
        """Not a 401. A browser handed one shows its own grey box, which cannot
        say what this is or offer to remember you."""
        self.access.set_password("a good long one")
        with urllib.request.urlopen(self.base) as f:
            body = f.read().decode("utf-8", "replace")
        self.assertEqual(f.status, 200)
        self.assertIn("This library is locked", body)

    def test_and_the_right_one_gets_in(self):
        self.access.set_password("a good long one")
        req = urllib.request.Request(self.base)
        token = base64.b64encode(b"photos:a good long one").decode()
        req.add_header("Authorization", "Basic " + token)
        with urllib.request.urlopen(req) as f:
            self.assertEqual(f.status, 200)

    def test_the_wrong_one_does_not(self):
        self.access.set_password("a good long one")
        req = urllib.request.Request(self.base + "api/health")
        req.add_header("Authorization",
                       "Basic " + base64.b64encode(b"photos:guess").decode())
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 401)

    def test_it_guards_the_data_too_not_only_the_page(self):
        """A login on the page and an open API is not a login."""
        self.access.set_password("a good long one")
        for path in ("api/tasks", "api/health", "api/jobs"):
            with self.assertRaises(urllib.error.HTTPError, msg=path) as e:
                urllib.request.urlopen(self.base + path)
            self.assertEqual(e.exception.code, 401)


class ChoosingLightOrDark(Served):
    """The machine's preference is a default, not a verdict.

    His NAS reports dark all day, so a page that only reads
    prefers-color-scheme is a page he cannot make light. The rule that makes an
    explicit choice possible is that the dark palette must exist somewhere the
    media query does not gate - otherwise the button sets an attribute nothing
    styles, and the page keeps its own opinion.
    """

    def page(self):
        with urllib.request.urlopen(self.base) as f:
            return f.read().decode()

    def test_there_is_a_switch(self):
        body = self.page()
        self.assertIn('id="theme"', body)

    def test_an_explicit_choice_has_a_palette_the_media_query_does_not_gate(self):
        body = self.page()
        self.assertIn('html[data-theme="dark"]', body)
        self.assertIn('html[data-theme="light"]', body)
        # the light palette is the base, so a light choice has something to be
        self.assertIn(":root{color-scheme:light", body)

    def test_the_media_query_stands_aside_for_an_explicit_light_choice(self):
        """The bug this prevents: dark rules under a bare `:root` inside the
        media query win over the button on a machine set to dark, so Light does
        nothing on exactly the machine someone would press it on."""
        body = self.page()
        for block in body.split("@media (prefers-color-scheme:dark)")[1:]:
            head = block[:60]
            self.assertIn('html:not([data-theme="light"])', head, head)

    def test_the_choice_is_applied_before_the_page_is_drawn(self):
        """Otherwise choosing Light means watching it load dark and correct
        itself on every visit."""
        body = self.page()
        head = body[:body.index("<body>")]
        self.assertIn("pm-theme", head)
        self.assertIn("data-theme", head)


class PreviewingChangesNothing(Served):
    def test_a_plan_comes_back_with_rows_and_an_id(self):
        p = self.preview("unpair", folder=self.lib, raw=self.raw)
        self.assertTrue(p["id"])
        self.assertEqual(len(p["rows"]), 3)
        self.assertTrue(p["writes"])

    def test_and_nothing_moved(self):
        before = self.tree(self.lib)
        self.preview("unpair", folder=self.lib, raw=self.raw)
        self.assertEqual(self.tree(self.lib), before)
        self.assertFalse(os.path.isdir(self.raw))

    def test_a_task_that_cannot_run_says_why_instead_of_failing(self):
        p = self.preview("unpair", folder="/no/such/folder", raw=self.raw)
        self.assertTrue(p["blocked"])
        self.assertEqual(p["rows"], [])

    def test_a_refusal_is_a_whole_plan_not_half_of_one(self):
        """The page draws a plan. Handed {"blocked": ...} and nothing else, it
        fell over on the first list it read - and what it then showed was
        "Cannot read properties of undefined (reading 'length')" instead of the
        folder it was refusing. Every list has to be there, empty."""
        S.ALLOWED_ROOTS[:] = [os.path.realpath(self.raw)]
        p = self.preview("unpair", folder=self.lib, raw=self.raw)
        self.assertTrue(p["blocked"])
        self.assertEqual(p["id"], "")                  # blank: no job was started
        for name in ("stats", "notes", "rows", "skipped", "errors", "columns",
                     "tree"):
            self.assertEqual(p[name], [], name)
        self.assertEqual(p["task"], "unpair")
        self.assertTrue(p["title"])

    def test_an_unknown_task_is_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post("api/plan", {"task": "not-a-task", "options": {}})
        self.assertEqual(e.exception.code, 400)


class ApplyingRunsThePlanThatWasShown(Served):
    def test_the_run_reports_progress_and_finishes(self):
        p = self.preview("unpair", folder=self.lib, raw=self.raw)
        state = self.finish(p["id"])
        self.assertEqual(state["result"]["done"], 3)
        self.assertEqual(state["result"]["failed"], 0)
        self.assertEqual(state["total"], 3)
        self.assertEqual(self.tree(self.raw),
                         ["2022/Spain/aeb1.RW2", "2022/Spain/aeb2.RW2",
                          "2022/Spain/aeb3.RW2"])

    def test_a_second_apply_does_not_run_it_again(self):
        p = self.preview("unpair", folder=self.lib, raw=self.raw)
        self.finish(p["id"])
        again = self.post("api/apply", {"id": p["id"]})
        self.assertTrue(again["finished"])
        self.assertEqual(again["result"]["done"], 3)
        self.assertEqual(len(self.tree(self.raw)), 3)

    def test_an_expired_or_invented_plan_is_refused_not_guessed_at(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post("api/apply", {"id": "0" * 32})
        self.assertEqual(e.exception.code, 400)

    def test_a_blocked_plan_cannot_be_applied(self):
        p = self.preview("unpair", folder="/no/such/folder", raw=self.raw)
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post("api/apply", {"id": p["id"]})
        self.assertEqual(e.exception.code, 400)

    def test_a_task_that_only_reports_cannot_be_applied(self):
        p = self.preview("brackets", folder=self.lib)
        self.assertFalse(p["writes"])
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post("api/apply", {"id": p["id"]})
        self.assertEqual(e.exception.code, 400)

    def test_progress_for_a_run_that_does_not_exist_is_a_404(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.get("api/progress?id=nope")
        self.assertEqual(e.exception.code, 404)


class EverythingThatIsRunning(Served):
    """One bar at the top, whichever tab started the work.

    Planning used to be a blocking request: a Library survey held one HTTP
    connection open for the length of the scan, reported nothing, could not be
    cancelled, and was indistinguishable from a page that had hung. Making it a
    job with an id fixes all four at once and is what lets a bar exist at all -
    a scan that is not a job cannot be listed.
    """

    def test_asking_for_a_plan_comes_back_at_once_with_a_job(self):
        """The claim is that the request returns a JOB rather than holding the
        connection open for the whole scan.

        NOT that the phase is still "planning" when it does. A library of four
        photographs is planned in about a millisecond, so the job can be ready
        before the response is written - and asserting "planning" made this fail
        about one run in thirty, on a fast day, for the right reason."""
        started = self.post("api/plan", {"task": "library",
                                         "options": {"folder": self.lib}})
        self.assertTrue(started["id"])
        self.assertIn(started["phase"], ("planning", "ready", "done"))

    def test_the_plan_arrives_through_the_same_route_as_the_run(self):
        started = self.post("api/plan", {"task": "unpair",
                                         "options": {"folder": self.lib,
                                                     "raw": self.raw}})
        until = time.time() + 20
        while time.time() < until:
            state = self.get("api/progress?id=" + started["id"])
            if state["phase"] != "planning":
                self.assertIn("plan", state)
                self.assertEqual(len(state["plan"]["rows"]), 3)
                return
            time.sleep(0.02)
        self.fail("planning never finished")

    def test_a_scan_appears_in_the_list_of_what_is_running(self):
        self.post("api/plan", {"task": "library", "options": {"folder": self.lib}})
        until = time.time() + 5
        seen = []
        while time.time() < until:
            seen = self.get("api/jobs")["running"]
            if seen:
                break
            time.sleep(0.005)
        # it may already be done on a library this small; either it was caught
        # in flight, or it finished - what must not happen is an error
        for job in seen:
            self.assertIn(job["phase"], ("planning", "applying"))
            self.assertTrue(job["title"])

    def test_and_a_finished_job_is_not_in_it(self):
        p = self.preview("unpair", folder=self.lib, raw=self.raw)
        self.finish(p["id"])
        self.assertEqual([j for j in self.get("api/jobs")["running"]
                          if j["id"] == p["id"]], [])

    def test_a_task_that_cannot_say_where_it_has_got_to_is_not_offered_a_stop(self):
        """A Stop button that does nothing is worse than no button. A task earns
        one by accepting a progress callback."""
        by_name = {t["name"]: t for t in self.get("api/tasks")["tasks"]}
        self.assertTrue(by_name["library"]["watchable"])
        self.assertTrue(by_name["duplicates"]["watchable"])
        self.assertFalse(by_name["unpair"]["watchable"])

    def test_a_scan_can_be_stopped_and_says_so_rather_than_pretending(self):
        started = self.post("api/plan", {"task": "library",
                                         "options": {"folder": self.lib}})
        self.post("api/cancel", {"id": started["id"]})
        until = time.time() + 20
        while time.time() < until:
            state = self.get("api/progress?id=" + started["id"])
            if state["phase"] != "planning":
                # either it stopped, or it was quick enough to finish first -
                # both are honest; what matters is that it never claims a plan
                # it did not finish
                if state["plan"].get("blocked"):
                    self.assertIn("Stopped", state["plan"]["blocked"])
                return
            time.sleep(0.02)
        self.fail("the scan neither finished nor stopped")


class StoppingPartWay(Served):
    def test_cancelling_marks_the_run_and_it_ends(self):
        p = self.preview("unpair", folder=self.lib, raw=self.raw)
        self.post("api/apply", {"id": p["id"]})
        self.post("api/cancel", {"id": p["id"]})
        until = time.time() + 10
        while time.time() < until:
            state = self.get("api/progress?id=" + p["id"])
            if state["finished"]:
                break
            time.sleep(0.02)
        self.assertTrue(state["finished"])
        self.assertTrue(state["cancelled"])
        # whatever it did get to is complete; a cancel never leaves half a file
        for name in self.tree(self.raw):
            self.assertTrue(name.endswith(".RW2"), name)


class BrowsingForAFolder(Served):
    """The Browse button. A mistyped root does not fail loudly - it mirrors against
    the wrong tree - so being able to pick one is a correctness feature."""

    def test_it_lists_the_folders_inside_one(self):
        d = self.get("api/browse?path=" + urllib.parse.quote(self.lib))
        self.assertEqual(d["path"], self.lib)
        self.assertIn("2022", [f["name"] for f in d["folders"]])

    def test_only_folders_are_listed_never_the_photos(self):
        d = self.get("api/browse?path=" + urllib.parse.quote(self.shoot))
        self.assertEqual(d["folders"], [])

    def test_you_can_go_back_up(self):
        d = self.get("api/browse?path=" + urllib.parse.quote(self.shoot))
        self.assertEqual(d["parent"], os.path.join(self.lib, "2022"))

    def test_a_folder_that_is_not_there_says_so_rather_than_failing(self):
        d = self.get("api/browse?path=" + urllib.parse.quote("/no/such/folder"))
        self.assertTrue(d["error"])
        self.assertEqual(d["folders"], [])

    def test_looking_outside_the_allowed_folders_is_allowed_but_marked(self):
        """Looking is not touching.

        Stopping the browser at the fence produced "no folders" for a machine
        plainly full of them, with nothing to separate a wrong path from a wrong
        fence. So it lists, and says what a task would make of what it listed.
        The refusal that matters is tested in TheAllowedFolders, at the point a
        task is actually asked to write.
        """
        S.ALLOWED_ROOTS[:] = [os.path.realpath(self.lib)]
        d = self.get("api/browse?path=" + urllib.parse.quote(self.dir))
        self.assertFalse(d.get("error"))
        self.assertTrue(d["folders"])                  # it can see them
        self.assertFalse(d["allowed"])                 # and says they are out
        self.assertIn("outside", d["outside"])

    def test_a_folder_inside_the_allowed_ones_is_not_marked(self):
        S.ALLOWED_ROOTS[:] = [os.path.realpath(self.lib)]
        d = self.get("api/browse?path=" + urllib.parse.quote(self.lib))
        self.assertTrue(d["allowed"])
        self.assertNotIn("outside", d)
        inside = {f["name"]: f["allowed"] for f in d["folders"]}
        self.assertTrue(inside["2022"])

    def test_with_allowed_folders_set_they_are_offered_first(self):
        S.ALLOWED_ROOTS[:] = [os.path.realpath(self.lib)]
        d = self.get("api/browse")
        paths = [f["path"] for f in d["folders"]]
        self.assertEqual(paths[0], os.path.realpath(self.lib))
        self.assertTrue(d["folders"][0]["allowed"])
        # the rest of the machine is still reachable underneath them
        self.assertGreater(len(paths), 1)
        self.assertFalse(any(f["allowed"] for f in d["folders"][1:]))

    def test_nothing_the_page_serves_contains_a_mangled_escape(self):
        """A CSS escape like \\25B8 written with one backslash is read by PYTHON
        first, where \\25 is an octal escape - so the stylesheet ships a control
        character and the arrow renders as a tofu box. Invisible in the source,
        obvious only on screen."""
        with urllib.request.urlopen(self.base) as f:
            body = f.read().decode()
        bad = [c for c in body if ord(c) < 32 and c not in "\t\r\n"]
        self.assertEqual(bad, [], f"control characters in the page: "
                                 f"{[hex(ord(c)) for c in bad]}")

    def test_the_containers_own_folders_are_marked_so_they_can_be_moved_aside(self):
        """A dozen operating-system folders sit at the top of a container, in
        front of the two that are photos. Marked, not hidden - a folder you
        cannot see is one you cannot rule out."""
        top = "C:\\" if os.name == "nt" else os.sep
        d = self.get("api/browse?path=" + urllib.parse.quote(top))
        by_name = {f["name"]: f for f in d["folders"]}
        if os.name != "nt":
            self.assertTrue(by_name["etc"]["system"])
            self.assertTrue(by_name["usr"]["system"])

    def test_but_only_at_the_top_a_photo_folder_may_share_the_name(self):
        """'media' or 'opt' inside a photo tree is a photo folder. Hiding it
        because of its name would be a lie about what is there."""
        os.makedirs(os.path.join(self.lib, "media"), exist_ok=True)
        d = self.get("api/browse?path=" + urllib.parse.quote(self.lib))
        by_name = {f["name"]: f for f in d["folders"]}
        self.assertFalse(by_name["media"]["system"])

    def test_the_top_of_the_machine_can_still_go_back_to_the_shortcuts(self):
        """A browser you can walk out of but not back into is one you get lost
        in. At the top there is nowhere further up, but "" means the starting
        list rather than no parent at all."""
        S.ALLOWED_ROOTS[:] = [os.path.realpath(self.lib)]
        top = "C:\\" if os.name == "nt" else os.sep
        d = self.get("api/browse?path=" + urllib.parse.quote(top))
        self.assertEqual(d["parent"], "")

    def test_climbing_above_an_allowed_folder_reaches_a_real_parent(self):
        S.ALLOWED_ROOTS[:] = [os.path.realpath(self.lib)]
        d = self.get("api/browse?path=" + urllib.parse.quote(self.lib))
        self.assertEqual(d["parent"], os.path.dirname(self.lib))


class ReReadingTheLibrary(Served):
    """The Re-read library button. "Re-read" means every file is opened again,
    and a person pressing it is not refused because the minute's own pass is
    running: that pass is stopped and the asked-for one starts."""

    def test_a_deep_pass_opens_every_file_again(self):
        from core import catalogue as _cat
        cat = _cat.shared()
        got = self.post("api/index", {"deep": True})
        self.assertTrue(got["started"])
        said = cat.wait(60)
        self.assertGreaterEqual(said.get("added", 0), 3, "the deep pass opened nothing")
        # the ordinary pass that follows opens nothing: everything is known
        got = self.post("api/index", {})
        self.assertTrue(got["started"])
        self.assertEqual(cat.wait(60).get("added"), 0)
        # and asked again, deep, it opens them all again
        got = self.post("api/index", {"deep": True})
        self.assertTrue(got["started"])
        self.assertGreaterEqual(cat.wait(60).get("added", 0), 3)

    def test_a_deep_pass_is_not_refused_while_another_is_running(self):
        from core import catalogue as _cat
        cat = _cat.shared()
        # a pass of its own, started first and still running when asked
        cat.start(_cat.wanted_roots(), deep=True)
        got = self.post("api/index", {"deep": True})
        self.assertTrue(got["started"], "refused because one was running")
        self.assertGreaterEqual(cat.wait(60).get("added", 0), 3)


class TheIcons(Served):
    """The page's own icon, on the tab and on a phone's home screen. The web
    manifest that made the page installable as an app went in 3.12.0, by
    request; the icons stay, because a tab with no icon is a tab you cannot
    find."""

    def fetch(self, path):
        with urllib.request.urlopen(self.base + path) as f:
            return f.headers.get("Content-Type"), f.read()

    def test_the_icons_are_real_pictures(self):
        for name in ("icon-32.png", "icon-192.png", "icon-512.png"):
            ctype, body = self.fetch(name)
            self.assertEqual(ctype, "image/png", name)
            self.assertTrue(body.startswith(b"\x89PNG"), name)
            self.assertGreater(len(body), 500, name)

    def test_there_is_no_manifest_any_more(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.fetch("manifest.webmanifest")
        self.assertEqual(e.exception.code, 404)

    def test_a_favicon_is_served_rather_than_404ing(self):
        ctype, body = self.fetch("favicon.ico")
        self.assertEqual(ctype, "image/png")
        self.assertTrue(body.startswith(b"\x89PNG"))

    def test_the_page_points_at_the_icon_and_not_at_a_manifest(self):
        with urllib.request.urlopen(self.base) as f:
            head = f.read().decode().split("</head>")[0]
        self.assertNotIn('rel="manifest"', head)
        self.assertNotIn("web-app-capable", head)
        self.assertIn('rel="icon"', head)
        self.assertIn("theme-color", head)


class TheTypeface(Served):
    """4.0 sets the page in Archivo, served by the app itself at /font/, so
    nothing on the page is asked of the internet. Before the door, like the
    icon: the sign-in page is set in it too."""

    def fetch(self, path):
        with urllib.request.urlopen(self.base + path) as f:
            return f.headers.get("Content-Type"), f.read()

    def test_both_halves_are_served_as_fonts(self):
        for name in ("archivo-latin.woff2", "archivo-latin-ext.woff2"):
            ctype, body = self.fetch("font/" + name)
            self.assertEqual(ctype, "font/woff2", name)
            self.assertTrue(body.startswith(b"wOF2"), name)

    def test_a_font_that_is_not_there_is_not_found(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.fetch("font/nothing.woff2")
        self.assertEqual(e.exception.code, 404)

    def test_it_is_served_before_the_door(self):
        from core import access
        access.forget()
        access.set_password("a good long one")
        try:
            ctype, body = self.fetch("font/archivo-latin.woff2")
        finally:
            access.set_password("")
            access.forget()
        self.assertEqual(ctype, "font/woff2")

    def test_the_page_the_sign_in_page_and_the_worker_all_ask_for_it(self):
        from app.page import PAGE, SERVICE_WORKER
        from app.loginpage import LOGIN
        self.assertIn('url("font/archivo-latin.woff2")', PAGE)
        self.assertIn('url("/font/archivo-latin.woff2")', LOGIN)
        self.assertIn('"./font/archivo-latin.woff2"', SERVICE_WORKER)
        self.assertIn('"./font/archivo-latin-ext.woff2"', SERVICE_WORKER)


class TabsAndIcons(Served):
    def test_the_page_offers_geotag_with_its_two_tabs_under_it(self):
        info = self.get("api/tasks")
        by = {t["name"]: t for t in info["tasks"]}
        self.assertEqual(by["pin"]["parent"], "geotag")
        self.assertEqual(by["import-timeline"]["parent"], "geotag")
        # Find brackets is a feature, not a setting: what COUNTS as a bracket
        # is the setting, and that stayed in Setup. A Review tool, so a tab of
        # Cull by rating, the head of Review's weeding tools.
        self.assertEqual(by["brackets"]["parent"], "cull")

    def test_the_sidebar_is_the_features_not_the_tabs(self):
        info = self.get("api/tasks")
        top = [t["name"] for t in info["tasks"] if not t["parent"]]
        self.assertIn("geotag", top)
        self.assertNotIn("pin", top)
        self.assertNotIn("brackets", top)

    def test_every_task_arrives_with_groups_the_page_can_draw(self):
        for t in self.get("api/tasks")["tasks"]:
            # Except a tab that IS an editor, which has no options to group.
            self.assertTrue(t["groups"] or t["editor"], t["name"])
            self.assertTrue(t["icon"], t["name"])
            for g in t["groups"]:
                self.assertTrue(g["options"], f"{t['name']} has an empty group")


class NasOnlyToolsOffTheNas(Served):
    """Reindex and Permissions ask things of DSM. On a PC there is no DSM, so a
    copy started as a desktop program leaves them off the page - and only off
    the page: they stay registered and the command line still runs them."""

    def _tasks(self, desktop):
        was = os.environ.get("PM_DESKTOP")
        os.environ["PM_DESKTOP"] = "1" if desktop else ""
        try:
            return self.get("api/tasks")
        finally:
            if was is None:
                os.environ.pop("PM_DESKTOP", None)
            else:
                os.environ["PM_DESKTOP"] = was

    @staticmethod
    def _everywhere(info):
        names = {t["name"] for t in info["tasks"]}
        for fam in info["families"]:
            names |= set(fam["tasks"])
        return names | set(info["settings_tasks"]) | set(info["pinned"])

    def test_on_the_nas_they_are_offered(self):
        info = self._tasks(desktop=False)
        self.assertFalse(info["desktop"])
        self.assertEqual(info["nas_only"], [])
        self.assertIn("reindex", {t["name"] for t in info["tasks"]})
        self.assertIn("permissions", info["settings_tasks"])
        self.assertIn("reindex", info["settings_tasks"])

    def test_on_a_pc_they_are_nowhere_the_page_draws_from(self):
        info = self._tasks(desktop=True)
        self.assertTrue(info["desktop"])
        self.assertEqual(sorted(info["nas_only"]), ["permissions", "reindex"])
        seen = self._everywhere(info)
        self.assertNotIn("reindex", seen)
        self.assertNotIn("permissions", seen)
        # and nothing else went with them
        self.assertEqual(self._everywhere(self._tasks(desktop=False)) - seen,
                         {"reindex", "permissions"})

    def test_even_when_one_of_them_was_pinned_on_the_nas(self):
        from core import families
        families.pin(["reindex", "library"])
        self.assertIn("reindex", self._tasks(desktop=False)["pinned"])
        self.assertEqual(self._tasks(desktop=True)["pinned"], ["library"])

    def test_they_are_still_registered_for_the_command_line(self):
        from app import registry as R
        self.assertTrue(R.get("reindex"))
        self.assertTrue(R.get("permissions"))
        import subprocess
        import sys
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ, PM_DESKTOP="1")
        for name in ("reindex", "permissions"):
            got = subprocess.run([sys.executable, "-m", "app.cli", name, "--help"],
                                 cwd=here, env=env, capture_output=True,
                                 text=True, timeout=60)
            self.assertEqual(got.returncode, 0, got.stderr)
            self.assertIn("Options:", got.stdout, name)

    def _health_with_a_missing_folder(self, desktop):
        gone = os.path.join(self.dir, "not mounted")
        roots = list(S.ALLOWED_ROOTS)
        was = os.environ.get("PM_DESKTOP")
        S.ALLOWED_ROOTS[:] = [gone]
        os.environ["PM_DESKTOP"] = "1" if desktop else ""
        try:
            return S.health()["trouble"]
        finally:
            S.ALLOWED_ROOTS[:] = roots
            if was is None:
                os.environ.pop("PM_DESKTOP", None)
            else:
                os.environ["PM_DESKTOP"] = was

    def test_a_missing_folder_on_a_pc_is_not_explained_as_a_container(self):
        """A PC has no compose file to fix; telling it to rebuild a container
        is a NAS instruction on the wrong machine."""
        said = self._health_with_a_missing_folder(desktop=True)
        self.assertIn("not there", said)
        self.assertNotIn("container", said)
        self.assertNotIn("compose", said)

    def test_on_the_nas_it_still_is(self):
        self.assertIn("compose file", self._health_with_a_missing_folder(desktop=False))


class TheAllowedFolders(Served):
    def test_a_path_outside_them_is_refused_before_anything_is_read(self):
        S.ALLOWED_ROOTS[:] = [os.path.realpath(self.raw)]
        p = self.preview("unpair", folder=self.lib, raw=self.raw)
        self.assertTrue(p["blocked"])
        self.assertIn("outside", p["blocked"])

    def test_and_a_path_inside_them_is_allowed(self):
        S.ALLOWED_ROOTS[:] = [os.path.realpath(self.dir)]
        p = self.preview("unpair", folder=self.lib, raw=self.raw)
        self.assertFalse(p["blocked"])
        self.assertEqual(len(p["rows"]), 3)

    def test_a_symlink_cannot_be_used_to_step_outside(self):
        outside = tempfile.mkdtemp(prefix="outside-")
        try:
            link = os.path.join(self.dir, "shortcut")
            try:
                os.symlink(outside, link)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are not available here")
            S.ALLOWED_ROOTS[:] = [os.path.realpath(self.dir)]
            self.assertFalse(S.path_allowed(link))
        finally:
            shutil.rmtree(outside, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


class TheMapBeforeWriting(unittest.TestCase):
    """Where each photograph would be pinned, before anything is written - which
    is when a wrong clock is cheap to notice."""

    def test_any_plan_whose_rows_carry_a_position_sends_points(self):
        from app import registry as R
        import app.tasks                           # noqa: F401
        task = R.get("pin")
        plan = R.Plan(task="pin")
        plan.rows.append(R.Row(what="location", name="a.JPG",
                               data={"lat": 41.3851, "lon": 2.1734}))
        plan.rows.append(R.Row(what="other", name="b.JPG", data={}))
        got = S.plan_payload(task, plan, "x")
        self.assertEqual(got["points"], [[41.3851, 2.1734, "a.JPG"]])

    def test_and_one_without_positions_sends_none(self):
        from app import registry as R
        import app.tasks                           # noqa: F401
        task = R.get("library")
        got = S.plan_payload(task, R.Plan(task="library"), "x")
        self.assertEqual(got["points"], [])


class OnAPhone(Served):
    """The page on a phone: a worker for the shell and thumbnails, a release."""

    def test_the_worker_is_served_and_never_cached(self):
        import urllib.request as _r
        with _r.urlopen(self.base + "sw.js") as f:
            body = f.read().decode()
            self.assertIn("no-store", f.headers.get("Cache-Control", ""))
        self.assertIn("addEventListener(\"fetch\"", body)
        # it must not keep the page or an API answer - only the shell and thumbs
        self.assertIn("pm-thumbs-", body)
        self.assertNotIn("__RELEASE__", body)

    def test_the_worker_keeps_only_the_app_as_the_shell(self):
        """The sign-in page answers / with a 200 when there is no ticket, and
        the worker kept it as the offline app; Reload's ?t=<now> kept a copy
        per press; thumbnails were kept for ever."""
        from app.page import SERVICE_WORKER, PAGE
        from app.loginpage import LOGIN
        mark = '<meta name="pm-shell" content="app">'
        self.assertIn(mark, PAGE)
        self.assertNotIn(mark, LOGIN)
        self.assertIn(mark, SERVICE_WORKER)
        self.assertIn('c.put("./", copy)', SERVICE_WORKER)
        self.assertIn("PICS_MAX", SERVICE_WORKER)
        self.assertIn('"forget-pics"', SERVICE_WORKER)
        from app import page as P
        self.assertIn('postMessage("forget-pics")', P.SCRIPT)

    def test_the_release_is_said_out_loud(self):
        from app import version
        got = self.get("api/health")
        self.assertEqual(got["release"], version.RELEASE)
        self.assertRegex(version.RELEASE, r"^\d+\.\d+\.\d+$")

    def test_the_page_offers_the_app_things_only_where_they_work(self):
        from app.page import PAGE
        self.assertIn("isSecureContext", PAGE)          # the worker is asked for
        self.assertIn('id="bottom"', PAGE)              # the bar on a phone
        # Install as an app went in 3.12.0, by request: no prompt, no button
        self.assertNotIn("beforeinstallprompt", PAGE)
        self.assertNotIn("installapp", PAGE)
        self.assertNotIn("Install as an app", PAGE)


class AnsweringABadRequest(Served):
    """A request the app cannot use gets a sentence back, never a closed socket.

    A closed socket is what the page reports as "Could not reach the app" - the
    same words as a NAS that is switched off - so every failure here has to come
    back as JSON the page can show.
    """

    def ask(self, method, path, body=b"", headers=None):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1],
                                          timeout=10)
        try:
            conn.putrequest(method, "/" + path)
            for k, v in (headers or {}).items():
                conn.putheader(k, v)
            if "Content-Length" not in (headers or {}):
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders()
            if body:
                conn.send(body)
            got = conn.getresponse()
            return got.status, got.getheader("Content-Type"), got.read()
        finally:
            conn.close()

    def test_an_oversized_body_is_refused_without_being_read(self):
        code, ctype, body = self.ask(
            "POST", "api/plan",
            headers={"Content-Type": "application/json",
                     "Content-Length": str(S.MAX_BODY + 1)})
        self.assertEqual(code, 400)
        self.assertEqual(ctype, "application/json")
        self.assertIn("too large", json.loads(body)["error"])

    def test_a_body_under_the_limit_is_still_read(self):
        # A normal body still reaches its route, which gives its own answer.
        filler = b'{"task": "nothing-called-this", "pad": "' + b"x" * 1000 + b'"}'
        code, _ctype, body = self.ask("POST", "api/plan", filler,
                                      {"Content-Type": "application/json"})
        self.assertEqual(code, 400)
        self.assertEqual(json.loads(body)["error"], "no such tool")

    def test_invalid_json_is_a_400_with_a_sentence(self):
        code, ctype, body = self.ask("POST", "api/plan", b"{not json",
                                     {"Content-Type": "application/json"})
        self.assertEqual(code, 400)
        self.assertEqual(ctype, "application/json")
        self.assertIn("not valid JSON", json.loads(body)["error"])

    def test_json_that_is_not_an_object_is_refused_too(self):
        code, _ctype, body = self.ask("POST", "api/apply", b"[1, 2]",
                                      {"Content-Type": "application/json"})
        self.assertEqual(code, 400)
        self.assertIn("error", json.loads(body))

    def test_a_route_that_raises_answers_500_in_json(self):
        was = S.health

        def broken():
            raise RuntimeError("the disk caught fire\nand a second line")
        S.health = broken
        import io
        import contextlib
        caught = io.StringIO()
        try:
            with contextlib.redirect_stderr(caught):
                code, ctype, body = self.ask("GET", "api/health")
        finally:
            S.health = was
        self.assertEqual(code, 500)
        self.assertEqual(ctype, "application/json")
        said = json.loads(body)["error"]
        self.assertIn("the disk caught fire", said)
        self.assertNotIn("\n", said)                 # one line, not a traceback
        self.assertIn("Traceback", caught.getvalue())  # which went to the log

    def test_a_post_route_that_raises_answers_500_in_json(self):
        from core import families as _fam
        was = _fam.pin

        def broken(_names):
            raise KeyError("pinned")
        _fam.pin = broken
        import io
        import contextlib
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                code, _ctype, body = self.ask("POST", "api/pinned",
                                              b'{"pinned": []}',
                                              {"Content-Type": "application/json"})
        finally:
            _fam.pin = was
        self.assertEqual(code, 500)
        self.assertIn("KeyError", json.loads(body)["error"])

    def test_the_server_keeps_answering_afterwards(self):
        self.ask("POST", "api/plan", b"{not json")
        self.assertIn("release", self.get("api/health"))


class OneWriterATree(Served):
    """Two runs writing into one tree at once are refused, or queued."""

    def tearDown(self):
        with S.TREES_LOCK:
            S.WRITING.clear()
        super().tearDown()

    def job(self, plan):
        with S.JOBS_LOCK:
            return S.JOBS[plan["id"]]

    def test_a_second_writing_run_on_the_same_tree_is_refused(self):
        first = self.preview("unpair", folder=self.lib, raw=self.raw)
        second = self.preview("unpair", folder=self.lib, raw=self.raw)
        # As if the first were still running: held from another thread.
        self.assertEqual(S.claim_trees(self.job(first)), "")
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post("api/apply", {"id": second["id"]})
        self.assertEqual(e.exception.code, 409)
        said = json.loads(e.exception.read())["error"]
        self.assertIn("is still writing to", said)
        self.assertIn(R_TITLE("unpair"), said)
        self.assertEqual(self.tree(self.raw), [], "the refused run wrote")
        # and once the first lets go, it goes ahead
        S.release_trees(self.job(first))
        self.assertEqual(self.finish(second["id"])["result"]["done"], 3)

    def test_a_run_on_a_different_tree_is_not_in_the_way(self):
        other = os.path.join(self.dir, "Elsewhere")
        os.makedirs(os.path.join(other, "2022"))
        first = self.preview("unpair", folder=self.lib, raw=self.raw)
        S.claim_trees(self.job(first))
        job = S.Job(self.job(first).task, plan=self.job(first).plan)
        job.plan = type(job.plan)(task="unpair", opts={"folder": other,
                                                       "raw": other + "-raw"})
        # Unpair also declares it reads the library, which is self.lib here;
        # without that declaration it touches only the other folders.
        job.task = _without_trees(job.task)
        self.assertEqual(S.claim_trees(job), "")

    def test_a_reading_run_alongside_a_writing_run_is_allowed(self):
        first = self.preview("unpair", folder=self.lib, raw=self.raw)
        S.claim_trees(self.job(first))
        looked = self.preview("brackets", folder=self.lib)
        self.assertFalse(looked["writes"])
        self.assertFalse(looked.get("blocked"))
        self.assertEqual(S.claim_trees(self.job(looked)), "")
        with S.TREES_LOCK:
            self.assertNotIn(looked["id"], S.WRITING)

    def test_the_trees_are_let_go_when_the_run_finishes(self):
        p = self.preview("unpair", folder=self.lib, raw=self.raw)
        self.finish(p["id"])
        with S.TREES_LOCK:
            self.assertEqual(S.WRITING, {})

    def test_and_when_it_fails(self):
        import dataclasses
        p = self.preview("unpair", folder=self.lib, raw=self.raw)
        job = self.job(p)

        def broken(plan, progress=None, cancelled=None):
            raise RuntimeError("half way")
        job.task = dataclasses.replace(job.task, apply=broken)
        self.assertEqual(S.claim_trees(job), "")
        job.run()
        self.assertIn("half way", job.error)
        with S.TREES_LOCK:
            self.assertEqual(S.WRITING, {})

    def test_the_automation_waits_its_turn_instead(self):
        first = self.preview("unpair", folder=self.lib, raw=self.raw)
        second = self.preview("unpair", folder=self.lib, raw=self.raw)
        S.claim_trees(self.job(first))
        queued = self.job(second)
        queued.by = "automation"
        t = threading.Thread(target=queued.run, daemon=True)
        t.start()
        time.sleep(0.3)
        self.assertFalse(queued.finished, "it ran over the other one")
        self.assertIn("waiting for", queued.now)
        S.release_trees(self.job(first))
        t.join(10)
        self.assertTrue(queued.finished)
        self.assertEqual(queued.result.done, 3)

    def test_a_run_started_by_a_run_on_its_own_thread_is_not_in_its_way(self):
        """The Automation tab's Apply runs each step of a flow as a job of its
        own, on the thread doing the Apply. Refusing those would deadlock it."""
        outer = self.preview("unpair", folder=self.lib, raw=self.raw)
        inner = self.preview("unpair", folder=self.lib, raw=self.raw)
        self.assertEqual(S.claim_trees(self.job(outer)), "")    # the request
        self.assertEqual(S.claim_trees(self.job(outer), wait=True), "")  # its run
        self.assertEqual(S.claim_trees(self.job(inner)), "")
        # but from any other thread it is still a clash
        S.release_trees(self.job(inner))
        said = []
        t = threading.Thread(target=lambda: said.append(
            S.claim_trees(self.job(inner))))
        t.start()
        t.join(5)
        self.assertIn("is still writing to", said[0])

    def test_a_queued_run_that_is_stopped_never_starts(self):
        first = self.preview("unpair", folder=self.lib, raw=self.raw)
        second = self.preview("unpair", folder=self.lib, raw=self.raw)
        S.claim_trees(self.job(first))
        queued = self.job(second)
        t = threading.Thread(target=queued.run, daemon=True)
        t.start()
        time.sleep(0.2)
        queued.cancel = True
        t.join(10)
        self.assertTrue(queued.finished)
        self.assertTrue(queued.result.cancelled)
        self.assertEqual(self.tree(self.raw), [])


def R_TITLE(name):
    from app import registry as R
    return R.get(name).title


def _without_trees(task):
    import dataclasses
    return dataclasses.replace(task, reads=(), copies_to=(), moves_to=())


class PackedForTheWire(Served):
    """The page and big answers go gzipped to whatever says it can take it."""

    def fetch(self, path, encoding=None):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1],
                                          timeout=10)
        try:
            headers = {"Accept-Encoding": encoding} if encoding else {}
            conn.request("GET", "/" + path, headers=headers)
            got = conn.getresponse()
            return got, got.read()
        finally:
            conn.close()

    def test_the_page_is_gzipped_when_asked_and_unpacks_to_the_same_bytes(self):
        import gzip
        from app.page import PAGE
        got, body = self.fetch("", "gzip, deflate, br")
        self.assertEqual(got.getheader("Content-Encoding"), "gzip")
        self.assertEqual(got.getheader("Vary"), "Accept-Encoding")
        self.assertEqual(int(got.getheader("Content-Length")), len(body))
        self.assertEqual(gzip.decompress(body), PAGE.encode("utf-8"))
        self.assertLess(len(body), len(PAGE.encode("utf-8")) // 2)
        # and the never-cache rule is the same either way
        self.assertIn("no-store", got.getheader("Cache-Control"))

    def test_without_asking_it_is_plain(self):
        from app.page import PAGE
        got, body = self.fetch("")
        self.assertIsNone(got.getheader("Content-Encoding"))
        self.assertEqual(got.getheader("Vary"), "Accept-Encoding")
        self.assertEqual(body, PAGE.encode("utf-8"))

    def test_saying_no_to_gzip_is_heard(self):
        got, _body = self.fetch("", "gzip;q=0, identity")
        self.assertIsNone(got.getheader("Content-Encoding"))

    def test_a_big_json_answer_is_packed_too(self):
        import gzip
        got, body = self.fetch("api/tasks", "gzip")
        self.assertEqual(got.getheader("Content-Encoding"), "gzip")
        self.assertIn("tasks", json.loads(gzip.decompress(body)))

    def test_a_small_answer_is_not_worth_packing(self):
        got, body = self.fetch("api/health", "gzip")
        self.assertLess(len(body), S.GZIP_OVER)
        self.assertIsNone(got.getheader("Content-Encoding"))

    def test_pictures_are_never_packed(self):
        got, body = self.fetch("icon-512.png", "gzip")
        self.assertIsNone(got.getheader("Content-Encoding"))
        self.assertIsNone(got.getheader("Vary"))
        self.assertTrue(body.startswith(b"\x89PNG"))
        self.assertIn("max-age", got.getheader("Cache-Control"))

    def test_which_answers_count_as_text(self):
        for ctype in ("text/html; charset=utf-8", "application/json",
                      "text/javascript; charset=utf-8", "text/css",
                      "image/svg+xml", "application/manifest+json"):
            self.assertTrue(S._squeezable(ctype), ctype)
        for ctype in ("image/jpeg", "image/png", "video/mp4",
                      "application/octet-stream", "application/zip"):
            self.assertFalse(S._squeezable(ctype), ctype)


# ------------------------------------------------------------ 3.13: the door

def _ask(served, method, path, body=b"", headers=None):
    """A request with exactly the headers given - urllib fills in its own Host."""
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", served.httpd.server_address[1],
                                      timeout=10)
    try:
        conn.putrequest(method, "/" + path, skip_host=True,
                        skip_accept_encoding=True)
        headers = dict(headers or {})
        headers.setdefault("Host", f"127.0.0.1:{served.httpd.server_address[1]}")
        headers.setdefault("Content-Type", "application/json")
        headers["Content-Length"] = str(len(body))
        for k, v in headers.items():
            conn.putheader(k, v)
        conn.endheaders()
        if body:
            conn.send(body)
        got = conn.getresponse()
        return got.status, got.read(), got
    finally:
        conn.close()


class FromSomeOtherPage(Served):
    """SV1: with no password a page on any website could POST to the app and
    the server never asked where the request came from."""

    def setUp(self):
        super().setUp()
        self.port = self.httpd.server_address[1]
        self.made = os.path.join(self.shoot, "made-by-a-stranger")
        self.body = json.dumps({"do": "mkdir", "into": self.shoot,
                                "name": "made-by-a-stranger"}).encode()
        self._hosts = set(S.EXTRA_HOSTS)

    def tearDown(self):
        S.EXTRA_HOSTS.clear()
        S.EXTRA_HOSTS.update(self._hosts)
        super().tearDown()

    def test_a_post_from_another_site_is_refused_and_does_nothing(self):
        code, body, _r = _ask(self, "POST", "api/files", self.body,
                              {"Origin": "http://evil.example",
                               "Content-Type": "text/plain"})
        self.assertEqual(code, 403)
        self.assertIn("not from this app", json.loads(body)["error"])
        self.assertFalse(os.path.exists(self.made))

    def test_the_same_name_on_another_port_is_another_site(self):
        code, _b, _r = _ask(self, "POST", "api/files", self.body,
                            {"Origin": f"http://127.0.0.1:{self.port + 1}"})
        self.assertEqual(code, 403)
        self.assertFalse(os.path.exists(self.made))

    def test_a_page_with_no_address_is_refused_too(self):
        code, _b, _r = _ask(self, "POST", "api/files", self.body,
                            {"Origin": "null"})
        self.assertEqual(code, 403)

    def test_the_apps_own_page_gets_through(self):
        code, _b, _r = _ask(self, "POST", "api/files", self.body,
                            {"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(code, 200)
        self.assertTrue(os.path.isdir(self.made))

    def test_a_script_sends_no_origin_and_is_not_affected(self):
        code, _b, _r = _ask(self, "POST", "api/files", self.body)
        self.assertEqual(code, 200)
        self.assertTrue(os.path.isdir(self.made))

    def test_a_name_pointed_at_this_machine_is_refused(self):
        """DNS rebinding: the attacker's name resolves here, so its page and
        the app share an origin and the Origin check alone cannot tell."""
        here = f"photos.evil.example:{self.port}"
        code, body, _r = _ask(self, "POST", "api/files", self.body,
                              {"Host": here, "Origin": "http://" + here})
        self.assertEqual(code, 403)
        self.assertIn("PM_HOSTS", json.loads(body)["error"])
        self.assertFalse(os.path.exists(self.made))

    def test_the_names_a_home_network_uses_are_fine(self):
        for i, name in enumerate(("diskstation", "nas.local", "nas.lan",
                                  "localhost", "192.168.1.20", "[::1]")):
            here = f"{name}:{self.port}"
            body = json.dumps({"do": "mkdir", "into": self.shoot,
                               "name": f"home-{i}"}).encode()
            code, _b, _r = _ask(self, "POST", "api/files", body,
                                {"Host": here, "Origin": "http://" + here})
            self.assertEqual(code, 200, name)

    def test_and_a_name_given_in_PM_HOSTS(self):
        S.EXTRA_HOSTS.add("photos.example.com")
        here = "photos.example.com"
        code, _b, _r = _ask(self, "POST", "api/files", self.body,
                            {"Host": here, "Origin": "https://" + here})
        self.assertEqual(code, 200)

    def test_a_trusted_proxy_may_name_the_address_the_browser_used(self):
        was = list(S.TRUSTED_PROXIES)
        S.TRUSTED_PROXIES[:] = S._networks("127.0.0.1")
        try:
            code, _b, _r = _ask(self, "POST", "api/files", self.body,
                                {"Host": f"127.0.0.1:{self.port}",
                                 "X-Forwarded-Host": "photos.example.com",
                                 "Origin": "https://photos.example.com"})
            self.assertEqual(code, 200)
        finally:
            S.TRUSTED_PROXIES[:] = was

    def test_same_place_reads_ports_the_way_a_browser_does(self):
        self.assertTrue(S.same_place("http://nas:8842", ["nas:8842"]))
        self.assertTrue(S.same_place("https://photos.example.com",
                                     ["photos.example.com"]))
        self.assertTrue(S.same_place("http://NAS", ["nas"]))
        self.assertFalse(S.same_place("http://nas:5000", ["nas:8842"]))
        self.assertFalse(S.same_place("http://nas.evil", ["nas:8842"]))
        self.assertFalse(S.same_place("null", ["nas"]))
        self.assertFalse(S.same_place("file://", ["nas"]))


class TheFenceReadsABoxLikeTheTask(unittest.TestCase):
    """SV4, SV5: the check and the task must split a box the same way, and a
    file box is a path like any other."""

    def setUp(self):
        import app.tasks                                  # noqa: F401
        from app import registry as R
        self.R = R
        self.dir = tempfile.mkdtemp(prefix="fence-")
        self.inside = os.path.join(self.dir, "inside")
        self.outside = os.path.join(self.dir, "outside")
        os.makedirs(self.inside)
        os.makedirs(self.outside)
        S.ALLOWED_ROOTS[:] = [os.path.realpath(self.inside)]

    def tearDown(self):
        S.ALLOWED_ROOTS.clear()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_comma_does_not_smuggle_a_second_folder_past(self):
        task = self.R.get("search")
        sneaky = os.path.join(self.inside, "a") + "," + self.outside
        said = S.check_paths(task, {"folders": sneaky})
        self.assertIn(self.outside, said or "")
        self.assertIsNone(S.check_paths(task, {"folders": os.path.join(
            self.inside, "a") + "," + os.path.join(self.inside, "b")}))

    def test_a_file_box_outside_is_refused_in_the_same_words(self):
        task = self.R.get("retime")
        name = os.path.join(self.outside, "hostname")
        said = S.check_paths(task, {"reference": name})
        self.assertEqual(said, f"{name} is outside the folders this is allowed "
                               f"to touch ({S.ALLOWED_ROOTS[0]}).")
        self.assertIsNone(S.check_paths(
            task, {"reference": os.path.join(self.inside, "x.jpg")}))

    def test_every_kind_of_file_box_is_checked(self):
        for name, box in (("import-places", "dump"), ("backup", "source")):
            task = self.R.get(name)
            self.assertIsNotNone(S.check_paths(
                task, {box: os.path.join(self.outside, "x.zip")}), name)


class TheFenceOverTheWire(Served):
    """SV10, SV13: the routes that skipped it."""

    def setUp(self):
        super().setUp()
        self.outside = os.path.join(self.dir, "elsewhere")
        os.makedirs(self.outside)
        with open(os.path.join(self.outside, "secret.txt"), "w") as fh:
            fh.write("x")
        S.ALLOWED_ROOTS[:] = [os.path.realpath(self.lib)]

    def test_mkdir_with_no_folder_is_refused_not_made_where_the_app_started(self):
        here = os.getcwd()
        before = set(os.listdir(here))
        code, body, _r = _ask(self, "POST", "api/files", json.dumps(
            {"do": "mkdir", "into": "", "name": "stray"}).encode())
        self.assertEqual(code, 400)
        self.assertIn("Choose the folder", json.loads(body)["error"])
        self.assertEqual(set(os.listdir(here)), before)

    def test_exists_does_not_answer_outside_the_fence(self):
        q = urllib.parse.urlencode([("path", self.outside), ("path", self.shoot)])
        there = self.get("api/exists?" + q)["there"]
        self.assertIsNone(there[self.outside])
        self.assertTrue(there[self.shoot])

    def test_the_folder_picker_lists_no_file_names_outside_the_fence(self):
        q = urllib.parse.urlencode({"path": self.outside, "files": "*"})
        got = self.get("api/browse?" + q)
        self.assertEqual(got["files"], [])
        q = urllib.parse.urlencode({"path": self.shoot, "files": "*"})
        self.assertTrue(self.get("api/browse?" + q)["files"])


class ADownloadCalledAnything(Served):
    """SV7: a name outside Latin-1 raised half-way through the headers."""

    def test_a_non_latin_name_downloads(self):
        name = os.path.join(self.shoot, "صورة 写真 📷.jpg")
        shutil.copy(os.path.join(FIX, "aeb1.jpg"), name)
        code, body, r = _ask(self, "GET", "api/download?" + urllib.parse.urlencode(
            {"path": name}))
        self.assertEqual(code, 200)
        said = r.getheader("Content-Disposition")
        self.assertIn("filename*=UTF-8''", said)
        self.assertIn(urllib.parse.quote("صورة"), said)
        with open(name, "rb") as fh:
            self.assertEqual(body, fh.read())

    def test_a_line_break_in_a_name_cannot_start_a_header(self):
        said = S.attachment('a"b\r\nSet-Cookie: x.jpg')
        self.assertNotIn("\r", said)
        self.assertNotIn("\n", said)
        self.assertTrue(said.startswith('attachment; filename="ab'))


class ThePasswordStaysOutOfTheLog(Served):
    """SV6: the run log keeps every option with a slash in it, and a password
    can have one."""

    def setUp(self):
        super().setUp()
        from core import access
        self.access = access
        self._env = os.environ.pop("PM_PASSWORD", None)
        access.forget()

    def tearDown(self):
        self.access.set_password("")
        self.access.forget()
        if self._env is not None:
            os.environ["PM_PASSWORD"] = self._env
        super().tearDown()

    def test_a_password_with_a_slash_is_not_written_down(self):
        from app import registry as R
        from core import runlog
        task = R.get("password")
        word = "pw/with/slash1"
        plan = task.make_plan({"word": word, "again": word})
        self.assertFalse(plan.blocked, plan.blocked)
        job = S.Job(task, plan)
        job.run()
        self.assertTrue(self.access.correct(word))
        path = runlog._path()
        with open(path, encoding="utf-8") as fh:
            self.assertNotIn(word, fh.read())
        self.assertNotIn("word", task.loggable({"word": word, "x": "/a"}))
