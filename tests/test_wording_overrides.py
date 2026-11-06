"""Setup > Wording: local edits to the text of every tool, and the way back.

What has to hold: an edit reaches everything that reads `describe()` - the
page, the API, the command line - and nothing else; the shipped text the
other tests check is untouched; the file holds only real edits; the same
four-word rule the shipped labels keep is kept by an edit; and the export is
enough to merge an edit back into the source mechanically, which the merge
tool then does and checks.
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from app.tasks import wording as TW        # noqa: E402
from core import families                  # noqa: E402
from core import settings as S             # noqa: E402
from core import wording as W              # noqa: E402


class Isolated(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="wording-")
        self._was = {k: os.environ.get(k) for k in ("PM_DATA", "PM_DEVELOPER")}
        os.environ["PM_DATA"] = os.path.join(self.home, "config")
        os.environ.pop("PM_DEVELOPER", None)
        W.forget()

    def tearDown(self):
        for k, v in self._was.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        W.forget()
        shutil.rmtree(self.home, ignore_errors=True)

    def developer(self, on=True):
        S.save({"developer": on})


class TheKeys(unittest.TestCase):
    def test_each_kind_of_key_is_read(self):
        self.assertEqual(W.parse("cull.summary")["kind"], "summary")
        got = W.parse("cull.option.min_stars.help")
        self.assertEqual((got["kind"], got["option"]), ("help", "min_stars"))
        got = W.parse("blur.option.do.choice.tag")
        self.assertEqual((got["kind"], got["value"]), ("choice", "tag"))
        self.assertEqual(W.parse("search.option.kinds.choice.")["value"], "")
        self.assertEqual(W.parse("cull.group.What goes with it")["value"],
                         "What goes with it")

    def test_anything_else_is_not_a_key(self):
        for bad in ("cull", "cull.colour", "cull.option.x", "cull.option.x.size",
                    ".title", "cull.group."):
            self.assertIsNone(W.parse(bad), bad)

    def test_every_shipped_key_is_one_the_file_can_hold(self):
        for key in TW.shipped():
            self.assertIsNotNone(W.parse(key), key)


class TheRules(unittest.TestCase):
    def test_a_label_of_five_words_is_refused_with_the_tests_reason(self):
        why = W.refusal("cull.option.folder.label", "The folder to cull from")
        self.assertIn("at most 4 words", why)
        self.assertEqual(W.refusal("cull.option.folder.label", "Folder to cull"), "")

    def test_and_so_is_a_heading_or_an_empty_name(self):
        self.assertTrue(W.refusal("cull.group.Thresholds", "The limits of this tool"))
        self.assertTrue(W.refusal("cull.title", "   "))
        self.assertEqual(W.refusal("cull.option.folder.help", ""), "")

    def test_the_style_guide_is_a_warning_not_a_refusal(self):
        said = W.problems("x.option.y.help",
                          "Leave BLANK - the photographs stay; this is honest.")
        joined = " ".join(said)
        for wanted in ("dash", "BLANK", "photographs", "semicolon"):
            self.assertIn(wanted, joined)
        self.assertEqual(W.problems("x.option.y.help",
                                    "Photos below this rating move to _Culled. "
                                    "The RAW file and its XMP sidecar go too."), [])

    def test_a_long_sentence_is_counted(self):
        long = " ".join(["word"] * 30) + "."
        self.assertTrue(any("long sentence" in p
                            for p in W.problems("x.summary", long)))


class Applying(Isolated):
    def test_an_edit_changes_only_its_own_text(self):
        before = R.get("cull").describe()
        W.write({"cull.option.folder.label": "Folder to check",
                 "cull.summary": "Moves low-rated photos to _Culled."})
        after = R.get("cull").describe()
        self.assertEqual(after["summary"], "Moves low-rated photos to _Culled.")
        o = next(x for x in after["options"] if x["name"] == "folder")
        self.assertEqual(o["label"], "Folder to check")
        g = next(x for g in after["groups"] for x in g["options"]
                 if x["name"] == "folder")
        self.assertEqual(g["label"], "Folder to check")
        self.assertEqual(after["title"], before["title"])
        for a, b in zip(before["options"], after["options"]):
            if a["name"] != "folder":
                self.assertEqual(a["label"], b["label"])

    def test_the_registry_itself_still_ships_the_old_text(self):
        """So tests/test_wording.py keeps testing what ships."""
        shipped = R.get("cull").options[0].label
        W.write({"cull.option.folder.label": "Something else"})
        self.assertEqual(R.get("cull").options[0].label, shipped)

    def test_choices_and_group_headings(self):
        W.write({"blur.option.do.choice.tag": "Tag them (nothing moves)",
                 "cull.group.Thresholds": "Limits"})
        blur = R.get("blur").describe()
        do = next(o for o in blur["options"] if o["name"] == "do")
        self.assertIn("Tag them (nothing moves)", [c["label"] for c in do["choices"]])
        cull = R.get("cull").describe()
        names = [g["name"] for g in cull["groups"]]
        self.assertIn("Limits", names)
        self.assertNotIn("Thresholds", names)
        self.assertTrue(all(o["group"] != "Thresholds" for o in cull["options"]))

    def test_a_derived_line_and_tab_follow_their_edit(self):
        plain = next(t for t in R.all_tasks() if not t.line)
        tabbed = next(t for t in R.all_tasks() if t.parent and not t.tab)
        W.write({f"{plain.name}.summary": "First sentence. Second one.",
                 f"{tabbed.name}.title": "New name"})
        self.assertEqual(plain.describe()["line"], "First sentence.")
        self.assertEqual(tabbed.describe()["tab"], "New name")

    def test_an_edit_for_something_gone_is_listed_not_a_crash(self):
        W.write({"cull.option.nothing_here.label": "Ghost",
                 "nosuchtool.title": "Ghost"})
        R.get("cull").describe()
        self.assertEqual(W.unknown(W.load(), TW.shipped()),
                         ["cull.option.nothing_here.label", "nosuchtool.title"])

    def test_a_damaged_file_is_no_edits(self):
        os.makedirs(os.environ["PM_DATA"], exist_ok=True)
        with open(W.path(), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(W.load(), {})
        self.assertTrue(R.get("cull").describe()["title"])

    def test_the_command_line_help_reads_the_edit(self):
        from app import cli
        W.write({"cull.option.folder.help": "Edited help for the folder box."})
        out = io.StringIO()
        with redirect_stdout(out):
            cli._task_help(R.get("cull"))
        self.assertIn("Edited help for the folder box.", out.getvalue())


class TheSwitch(Isolated):
    def test_off_by_default_and_the_api_refuses(self):
        self.assertFalse(W.developer_on())
        got, code = TW.answer({})
        self.assertEqual(code, 403)
        got, code = TW.change({"key": "cull.title", "text": "X"})
        self.assertEqual(code, 403)
        self.assertEqual(W.load(), {})

    def test_setup_or_the_environment_turns_it_on(self):
        self.developer()
        self.assertTrue(W.developer_on())
        self.developer(False)
        os.environ["PM_DEVELOPER"] = "1"
        self.assertTrue(W.developer_on())

    def test_setup_has_the_switch_in_a_folded_group(self):
        o = next(o for o in R.get("setup").options if o.name == "developer")
        self.assertEqual((o.kind, o.setting, o.group, o.advanced),
                         ("flag", "developer", "Developer", True))
        self.assertIn("Wording tab", o.help)

    def test_the_tab_is_offered_only_with_the_switch_on(self):
        names = [t.name for t in R.all_tasks()]
        self.assertNotIn("wording", families.offered(names, False))
        self.assertIn("wording", families.offered(names, False, True))
        self.assertEqual(R.get("wording").parent, "setup")
        self.assertEqual(families.of("wording"), "settings")


class TheApi(Isolated):
    def setUp(self):
        super().setUp()
        self.developer()

    def test_one_tool_is_listed_field_by_field_with_its_source_line(self):
        got, code = TW.answer({"task": "cull"})
        self.assertEqual(code, 200)
        keys = [f["key"] for f in got["fields"]]
        self.assertEqual(keys[:3], ["cull.title", "cull.summary", "cull.line"])
        label = next(f for f in got["fields"]
                     if f["key"] == "cull.option.folder.label")
        path, line = label["where"].split(":")
        self.assertEqual(path, "app/tasks/cull.py")
        with open(os.path.join(HERE, path), encoding="utf-8") as fh:
            self.assertIn(label["shipped"], fh.read().splitlines()[int(line) - 1])

    def test_saving_reports_the_rules_and_the_counts(self):
        got, code = TW.change({"key": "cull.option.folder.help",
                               "text": "Leave BLANK - it is fine."})
        self.assertEqual(code, 200)
        self.assertTrue(got["edited"])
        self.assertTrue(got["problems"])
        self.assertEqual(got["counts"]["edited"], 1)

    def test_a_five_word_label_is_refused_and_not_saved(self):
        got, code = TW.change({"key": "cull.option.folder.label",
                               "text": "The folder to cull from"})
        self.assertEqual(code, 400)
        self.assertIn("at most 4 words", got["error"])
        self.assertEqual(W.load(), {})

    def test_text_equal_to_the_shipped_text_is_not_an_edit(self):
        shipped = R.get("cull").title
        TW.change({"key": "cull.title", "text": "Different"})
        TW.change({"key": "cull.title", "text": "  " + shipped + " "})
        self.assertEqual(W.load(), {})

    def test_reset_one_and_reset_everything(self):
        TW.change({"key": "cull.title", "text": "One"})
        TW.change({"key": "blur.title", "text": "Two"})
        TW.change({"key": "cull.title", "reset": True})
        self.assertEqual(W.load(), {"blur.title": "Two"})
        TW.change({"reset_all": True})
        self.assertEqual(W.load(), {})

    def test_an_unknown_key_is_refused(self):
        got, code = TW.change({"key": "cull.option.ghost.label", "text": "x"})
        self.assertEqual(code, 400)

    def test_an_upload_merges_and_names_what_it_left_out(self):
        TW.change({"key": "cull.title", "text": "Kept"})
        got, code = TW.change({"file": {"overrides": {
            "blur.title": "Blurry",
            "cull.option.folder.label": "Five words is too many",
            "ghost.title": "x"}}})
        self.assertEqual(code, 200)
        self.assertEqual(W.load(), {"cull.title": "Kept", "blur.title": "Blurry"})
        self.assertEqual(sorted(r["key"] for r in got["refused"]),
                         ["cull.option.folder.label", "ghost.title"])
        TW.change({"file": {"overrides": {"blur.title": "Only"}}, "replace": True})
        self.assertEqual(W.load(), {"blur.title": "Only"})

    def test_the_export_carries_the_shipped_text_and_where_it_is(self):
        TW.change({"key": "cull.option.folder.label", "text": "Folder to check"})
        got, code = TW.answer({"export": "1"})
        self.assertEqual(code, 200)
        entry = got["entries"][0]
        self.assertEqual(entry["key"], "cull.option.folder.label")
        self.assertEqual(entry["shipped"], R.get("cull").options[0].label)
        self.assertTrue(entry["where"].startswith("app/tasks/cull.py:"))

    def test_a_search_reads_every_tool(self):
        got, _ = TW.answer({"task": "*"})
        self.assertEqual(len(got["fields"]), len(TW.shipped()))

    def test_the_tool_lists_the_edits_for_the_command_line(self):
        TW.change({"key": "cull.title", "text": "Edited"})
        plan = R.get("wording").make_plan({})
        self.assertEqual([r.name for r in plan.rows], ["cull.title"])
        self.assertEqual(plan.rows[0].cells, ["Edited", R.get("cull").title])


class OverHttp(Isolated):
    def setUp(self):
        super().setUp()
        from http.server import ThreadingHTTPServer
        from app import server
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}/"
        threading.Thread(target=self.httpd.serve_forever,
                         kwargs={"poll_interval": 0.02}, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def call(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data,
                                     {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as f:
                return f.status, json.load(f)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_refused_while_the_switch_is_off(self):
        self.assertEqual(self.call("api/wording")[0], 403)
        self.assertEqual(self.call("api/wording", {"key": "cull.title",
                                                   "text": "x"})[0], 403)
        names = [t["name"] for t in self.call("api/tasks")[1]["tasks"]]
        self.assertNotIn("wording", names)

    def test_a_page_string_edited_over_http_is_in_the_next_page(self):
        self.developer()
        code, got = self.call("api/wording", {"key": "page.notSaved",
                                              "text": "Held back, see below."})
        self.assertEqual(code, 200, got)
        with urllib.request.urlopen(self.base) as f:
            page = f.read().decode("utf-8")
        self.assertIn('"notSaved": "Held back, see below."', page)

    def test_an_edit_saved_over_http_reaches_the_task_list(self):
        self.developer()
        code, got = self.call("api/wording", {"key": "cull.title",
                                              "text": "Weed by stars"})
        self.assertEqual(code, 200, got)
        tasks = self.call("api/tasks")[1]["tasks"]
        self.assertIn("wording", [t["name"] for t in tasks])
        self.assertEqual(next(t for t in tasks if t["name"] == "cull")["title"],
                         "Weed by stars")


class ThePageAndTheGuide(Isolated):
    """The page's own strings (app/web/page/strings.json) and the Guide
    (app/page.py) are edited on the same tab, and reach the page as it is
    sent (app/pagetext.py)."""

    def setUp(self):
        super().setUp()
        self.developer()
        from app import pagetext
        self.PT = pagetext

    def test_their_keys_are_read(self):
        self.assertEqual(W.kind_of("page.notSaved"), "string")
        self.assertEqual(W.kind_of("guide.welcome.title"), "title")
        self.assertEqual(W.kind_of("guide.welcome.body.2"), "body")
        self.assertIsNone(W.parse("guide.welcome.body.x"))

    def test_no_tool_takes_their_names(self):
        self.assertIsNone(R.get("page"))
        self.assertIsNone(R.get("guide"))

    def test_both_are_in_the_tool_list_and_in_what_ships(self):
        got, _ = TW.answer({})
        self.assertEqual([t["name"] for t in got["tasks"]][-2:], ["page", "guide"])
        table = TW.shipped()
        self.assertEqual(table["page.notSaved"], self.PT.strings()["notSaved"])
        self.assertEqual(table["guide.welcome.title"], "Welcome")

    def test_each_card_names_its_line(self):
        got, _ = TW.answer({"task": "page"})
        one = next(f for f in got["fields"] if f["key"] == "page.notSaved")
        path, line = one["where"].split(":")
        with open(os.path.join(HERE, path), encoding="utf-8") as fh:
            self.assertIn('"notSaved"', fh.read().splitlines()[int(line) - 1])
        got, _ = TW.answer({"task": "guide"})
        one = next(f for f in got["fields"] if f["key"] == "guide.welcome.body.1")
        self.assertTrue(one["where"].startswith("app/page.py:"), one["where"])

    def test_with_nothing_edited_the_page_is_sent_as_built(self):
        from app.page import PAGE
        self.assertEqual(PAGE.count(self.PT.MARK), 1)
        self.assertIs(self.PT.served(PAGE, {}), PAGE)
        self.assertIs(self.PT.served(PAGE, {"cull.title": "x"}), PAGE)

    def test_an_edit_is_put_into_the_page_as_it_is_sent(self):
        from app.page import PAGE
        TW.change({"key": "page.notSaved", "text": "Kept back."})
        TW.change({"key": "guide.welcome.body.2", "text": "Nothing moves yet."})
        sent = self.PT.served(PAGE)
        self.assertNotIn(self.PT.MARK, sent)
        said = json.loads(sent.split("const WORDING = ", 1)[1].split(";</script>", 1)[0])
        self.assertEqual(said["page"], {"notSaved": "Kept back."})
        self.assertEqual(said["guide"], {"0": {"body": {"1": "Nothing moves yet."}}})

    def test_text_that_would_close_the_script_cannot(self):
        from app.page import PAGE
        TW.change({"key": "page.notSaved", "text": "</script><b>x</b>"})
        sent = self.PT.served(PAGE)
        self.assertNotIn("</script><b>", sent)


class ThePage(unittest.TestCase):
    def test_the_editor_is_a_library_piece_hooked_in_by_name(self):
        from app import page as P
        from app import web
        piece = web.read("library/js/21-wording.js")
        self.assertIn("TAB_EDITORS.wording = startWording;", piece)
        self.assertIn("const TAB_EDITORS = {};", P.PAGE)
        self.assertIn("TAB_EDITORS[wanted.editor]", P.PAGE)
        for wanted in ("api/wording", "Download wording.json",
                       "Upload wording.json", "Reset everything",
                       "Reset to shipped"):
            self.assertIn(wanted, piece)
        self.assertIn(".wdcard", P.PAGE)


class TheMergeTool(unittest.TestCase):
    """Run against a copy of the code, so the test never edits this checkout."""

    def setUp(self):
        self.copy = tempfile.mkdtemp(prefix="merge-")
        for part in ("app", "core", "tools"):
            shutil.copytree(os.path.join(HERE, part), os.path.join(self.copy, part),
                            ignore=shutil.ignore_patterns("__pycache__"))
        self.env = dict(os.environ, PM_DATA=os.path.join(self.copy, "config"))
        self.env.pop("PM_DEVELOPER", None)

    def tearDown(self):
        shutil.rmtree(self.copy, ignore_errors=True)

    def merge(self, body, *extra):
        path = os.path.join(self.copy, "w.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(body, fh)
        return subprocess.run(
            [sys.executable, os.path.join(self.copy, "tools", "merge_wording.py"),
             path, *extra], cwd=self.copy, env=self.env, capture_output=True,
            text=True, check=False)

    def read(self, rel):
        with open(os.path.join(self.copy, rel), encoding="utf-8") as fh:
            return fh.read()

    def test_it_writes_labels_help_choices_and_headings_in_place(self):
        cull = R.get("cull")
        new_help = ("Photos rated at or below this are moved to _Culled. "
                    "-1 never moves a JPEG, whatever its rating, and this "
                    "sentence is long enough to need wrapping over lines.")
        got = self.merge({"overrides": {
            "cull.option.folder.label": "Folder to check",
            "cull.option.jpeg_at_or_below.help": new_help,
            "cull.group.Thresholds": "Limits",
            "forget.option.which.choice.old": "Older than a number of days",
            "cull.summary": "Moves low-rated photos to _Culled."},
            "entries": [{"key": "cull.option.folder.label",
                         "shipped": cull.options[0].label}]}, "--apply")
        self.assertEqual(got.returncode, 0, got.stdout + got.stderr)
        self.assertIn("Done.", got.stdout)
        source = self.read("app/tasks/cull.py")
        self.assertIn('"Folder to check"', source)
        self.assertIn('group="Limits"', source)
        self.assertNotIn('group="Thresholds"', source)
        for line in source.splitlines():
            self.assertLessEqual(len(line), 100, line)
        self.assertIn('("old", "Older than a number of days")',
                      self.read("app/tasks/forget.py"))

    def test_a_help_an_option_never_had_is_added(self):
        """Every shipped option has help since the 3.13 rewrites, so the copy
        is given a tool with one bare box to try it on."""
        with open(os.path.join(self.copy, "app", "tasks", "zz_bare.py"), "w",
                  encoding="utf-8") as fh:
            fh.write(
                "from app.registry import Flag, Plan, Result, Task, register\n"
                "register(Task(name='zz_bare', title='Bare', summary='A test.',\n"
                "              options=[Flag('box', 'Bare box', default=False)],\n"
                "              plan=lambda opts: Plan(task='zz_bare'),\n"
                "              apply=lambda plan: Result(task='zz_bare'),\n"
                "              hidden=True, writes=False))\n")
        with open(os.path.join(self.copy, "app", "tasks", "__init__.py"), "a",
                  encoding="utf-8") as fh:
            fh.write("from . import zz_bare  # noqa: E402,F401\n")
        got = self.merge({"overrides": {
            "zz_bare.option.box.help": "A brand new bubble."}}, "--apply")
        self.assertEqual(got.returncode, 0, got.stdout + got.stderr)
        self.assertIn('help="A brand new bubble."',
                      self.read("app/tasks/zz_bare.py"))

    def test_page_strings_and_guide_pages_are_merged_too(self):
        got = self.merge({"overrides": {
            "page.notSaved": "Held back. See below.",
            "guide.welcome.body.2": "Nothing happens until you say so. Every "
                                    "tool shows what it would do first."}},
            "--apply")
        self.assertEqual(got.returncode, 0, got.stdout + got.stderr)
        table = json.loads(self.read("app/web/page/strings.json"))
        self.assertEqual(table["notSaved"], "Held back. See below.")
        joined = re.sub(r'"\s*\n\s*"', "", self.read("app/page.py"))
        self.assertIn("Nothing happens until you say so. Every tool shows "
                      "what it would do first.", joined)

    def test_text_changed_since_the_export_is_left_alone(self):
        got = self.merge({"overrides": {"cull.title": "Weed"},
                          "entries": [{"key": "cull.title",
                                       "shipped": "What it said last year"}]},
                         "--apply")
        self.assertIn("source changed since the export", got.stdout)
        self.assertIn(f'title="{R.get("cull").title}"', self.read("app/tasks/cull.py"))

    def test_without_apply_nothing_is_written(self):
        before = self.read("app/tasks/cull.py")
        got = self.merge({"overrides": {"cull.title": "Weed"}})
        self.assertIn("Nothing written", got.stdout)
        self.assertEqual(self.read("app/tasks/cull.py"), before)

    def test_one_line_serving_two_keys_that_now_differ_is_left_alone(self):
        """Colour meanings declares each colour's boxes in one loop, so one
        literal is red's help and blue's help at once. Writing whichever key
        came first would give every colour the other one's words."""
        before = self.read("app/tasks/labels.py")
        got = self.merge({"overrides": {
            "labels.option.label_red_keywords.help": "Red's own words.",
            "labels.option.label_blue_keywords.help": "Blue's own words."}},
            "--apply")
        self.assertNotEqual(got.returncode, 0)
        self.assertIn("conflict    labels.option.label_red_keywords.help",
                      got.stdout)
        self.assertIn("conflict    labels.option.label_blue_keywords.help",
                      got.stdout)
        self.assertEqual(self.read("app/tasks/labels.py"), before)

    def test_a_five_word_label_is_refused_here_too(self):
        got = self.merge({"overrides": {
            "cull.option.folder.label": "The folder to cull from"}}, "--apply")
        self.assertIn("at most 4 words", got.stdout)


if __name__ == "__main__":
    unittest.main()
