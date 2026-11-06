"""Labels that are labels, and help that is a bubble.

Two faults with one cause: the interface was written the way the docstrings are,
and a docstring has all the room in the world.

**A label is a name, not a sentence.** "Where the locations come from" is a
sentence; "Location source" is a label. Two hundred and thirty-six options each
carrying a clause made every form look like prose with boxes in it, and the
thing you are actually looking for - which setting is this - was the hardest
part to find.

**Help is a bubble, not a panel.** It used to expand in place, and the
arithmetic of that is what made it wrong: most options here have two sentences
explaining a trap, so a form with a dozen of them opened is four screens of
prose with the controls scattered through it. You cannot compare two settings
that are a page apart, so you stop opening any of them.

Nothing was deleted. What a long label was carrying moved into its bubble, and
there is a test below that every option which lost words still has one.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R                # noqa: E402
import app.tasks                             # noqa: E402,F401
from app import page as P                    # noqa: E402

# Four words is a label. Five is a sentence with the verb left out.
LIMIT = 4

# The exceptions, named rather than waved through: each is a question rather
# than a name, and shortening it would make it ambiguous instead of shorter.
# Empty since the 3.13 rewrites: "Clock fast by (minutes)" fits in four.
ALLOWED_LONG: set = set()


class Labels(unittest.TestCase):
    def test_no_label_is_a_sentence(self):
        long = []
        for t in R.all_tasks():
            for o in t.options:
                if (t.name, o.name) in ALLOWED_LONG:
                    continue
                if len(o.label.split()) > LIMIT:
                    long.append(f"{t.name}.{o.name}: {o.label!r}")
        self.assertEqual(long, [], "labels that are sentences:\n  "
                                   + "\n  ".join(long))

    def test_nor_is_a_group_heading(self):
        long = []
        for t in R.all_tasks():
            for o in t.options:
                if o.group and len(o.group.split()) > LIMIT:
                    long.append(f"{t.name}: {o.group!r}")
        self.assertEqual(sorted(set(long)), [])

    def test_a_label_short_enough_to_be_ambiguous_has_context(self):
        """A one or two word label cannot explain itself, so something else must
        - either a bubble, or a group heading that names the decision it
        belongs to. "Days" under "Or shift by" needs neither; "The library" on
        its own needs one. This is the half that keeps shortening honest: the
        words did not disappear, they moved."""
        bare = []
        for t in R.all_tasks():
            for o in t.options:
                if len(o.label.split()) <= 2 and not o.help and not o.group:
                    bare.append(f"{t.name}.{o.name}: {o.label!r}")
        self.assertEqual(bare, [], "nothing explains these:\n  "
                                   + "\n  ".join(bare))

    def test_every_label_says_something(self):
        for t in R.all_tasks():
            for o in t.options:
                self.assertTrue(o.label.strip(), f"{t.name}.{o.name}")

    def test_the_help_a_label_gave_up_is_still_somewhere(self):
        """Spot-checked on the ones where the old label carried the only
        warning. A short label that lost a trap is worse than a long one."""
        # The warning, not the words: "never opens a negative" became "a RAW
        # file ... is never changed itself" when the glossary retired
        # "negative", and the trap it names is the same one.
        must = {
            ("geotag", "sidecar_only"): "is never changed itself",
            ("pin", "sidecar_only"): "is never changed itself",
            ("unpair", "copy"): "MOVED",
            ("retime", "keep_originals"): "_BeforeRetime",
            ("geotag", "keep_originals"): "_NoLocation",
        }
        for (task, opt), wanted in must.items():
            o = [x for x in R.get(task).options if x.name == opt][0]
            self.assertIn(wanted.lower(), (o.help or "").lower(),
                          f"{task}.{opt} lost what its label used to say")


class TheBubble(unittest.TestCase):
    def test_help_is_carried_on_the_button_rather_than_in_a_panel(self):
        self.assertIn("data-tip", P.PAGE)
        self.assertIn("#tip{", P.PAGE)
        self.assertIn('el.id = "tip"', P.PAGE)

    def test_and_no_panel_is_left_behind(self):
        """A hidden panel per option is weight on every form, and two ways to
        show one thing is one of them going stale."""
        self.assertNotIn("toggleHelp", P.PAGE)
        self.assertNotIn('class="help', P.PAGE)

    def test_it_is_bound_by_delegation_not_per_button(self):
        """Forms here are redrawn on every tab switch and every plan. Anything
        bound to the buttons themselves has to remember to rebind, which is a
        thing that gets forgotten once and then silently half-works."""
        self.assertIn("document.addEventListener", P.PAGE)

    def test_it_is_bound_once_and_never_again_on_a_redraw(self):
        """The selection bar called bindTips() on every redraw, so each tap on
        a tile stacked seven more document listeners - and an even number of
        click handlers opened and shut a bubble in the same tap."""
        calls = re.findall(r"(?<!function )\bbindTips\(\)", P.SCRIPT)
        self.assertEqual(len(calls), 1, "bindTips() is called more than once")
        self.assertIn("bindTips.bound", P.SCRIPT)

    def test_a_selection_bar_button_explains_itself_once(self):
        """A `title` beside `data-tip` showed the browser's own tooltip on top
        of the bubble, the same words twice."""
        from app import web
        bar = web.read("library/js/04-selection.js")
        draw = bar[bar.index("function drawPickBar("):bar.index("function rateMenu(")]
        self.assertIn("data-tip=", draw)
        self.assertNotIn("title=", draw)

    def test_the_selection_bars_delete_keeps_what_it_promises(self):
        """It promised Undo and gave none, and named the NAS on a PC."""
        from app import web
        bar = web.read("library/js/04-selection.js")
        self.assertNotIn("NAS", bar)
        if "Undo is offered" in bar:
            each = bar[bar.index("async function eachPicked("):bar.index("function rateThem(")]
            self.assertIn('"Undo"', each)
            self.assertIn('do: "undo"', each)
        self.assertNotIn("they are gone", bar)

    def test_hovering_is_a_mouse_thing_and_only_a_mouse_thing(self):
        """A tap fires pointerover, pointerout AND click in one gesture, so a
        bubble that opened on hover would then be toggled shut by the click -
        the button appearing not to work at all."""
        self.assertIn('e.pointerType && e.pointerType !== "mouse"', P.PAGE)

    def test_and_it_remembers_how_it_was_opened(self):
        """Because the focus a tap also causes would otherwise do the same
        thing the hover did: open it, so that the click reads it as already
        open and shuts it. One tap, nothing visible, a dead button."""
        self.assertIn('TIPHOW === "click"', P.PAGE)

    def test_it_is_clamped_so_it_cannot_push_the_page_sideways(self):
        self.assertIn("innerWidth - w - pad", P.PAGE)


class CountsReadAsSentences(unittest.TestCase):
    def test_no_count_on_the_page_says_s_in_brackets(self):
        """"12 photograph(s)" in seventeen places; count() says it properly."""
        code = re.sub(r"/\*.*?\*/", "", P.SCRIPT, flags=re.S)
        calls = set(re.findall(r"function ([\w$]+)\(", code))   # markRows(s) is code
        said = [w for w in re.findall(r"([A-Za-z]+)\(s\)", code) if w not in calls]
        self.assertEqual(said, [])
        self.assertEqual(P.SCRIPT.count("function count("), 1)

    def test_every_screen_waits_the_same_way(self):
        """One placeholder, so every screen that waits is one that also says
        when it could not get an answer."""
        from app import libraryui
        self.assertEqual(libraryui.SCRIPT.count('<div class="note">Reading...</div>'), 1)
        self.assertIn("function reading()", libraryui.SCRIPT)


class OneNameForOneThing(unittest.TestCase):
    """The header button reloads the page; the other two ask the index to read
    the library again. All three said Refresh, so nobody could tell which was
    which without pressing them."""

    def test_the_header_button_is_reload_page(self):
        self.assertIn('"<span>Reload page</span>"', P.PAGE)
        self.assertIn('title="Reload page"', P.PAGE)

    def test_the_two_reindex_buttons_are_one_button(self):
        """Home and the rail both offer Re-read library. They used to be two
        copies of the markup, and Home's never said "Reading..." because the
        handler looked for the rail's. One function draws both now, and the
        press passes the button that was pressed."""
        from app import web
        home = web.read("library/js/02-home.js")
        router = web.read("library/js/01-router.js")
        self.assertIn("${rereadButton()}", home)
        self.assertIn('${rereadButton("margin-top:4px")}', router)
        self.assertIn('onclick="reindexNow(this)"', router)
        self.assertIn('const REREAD = "Re-read library";', router)
        self.assertNotIn("Re-read library</button>", home)
        self.assertNotIn("#homeidx", router)

    def test_one_label_for_tagging_a_folder(self):
        from app import web
        people = web.read("library/js/08-folder-albums.js")
        self.assertNotIn("Tag a whole folder", people)
        self.assertGreaterEqual(people.count("Tag a folder"), 2)

    def test_no_button_is_called_refresh_any_more(self):
        import re
        self.assertEqual(re.findall(r">\s*(?:\$\{[^}]*\}\s*)?Refresh(?: now)?\s*<",
                                    P.PAGE), [])
        self.assertNotIn("<span>Refresh</span>", P.PAGE)

    def test_the_login_page_says_how_to_get_back_in(self):
        from app import loginpage
        for word in ("access.json", "PM_DATA", "PM_PASSWORD"):
            self.assertIn(word, loginpage.LOGIN)

    def test_and_so_do_both_install_guides(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for guide in ("nas/README.md", "windows/README.md"):
            with open(os.path.join(here, guide), encoding="utf-8") as fh:
                said = fh.read()
            for word in ("access.json", "PM_PASSWORD"):
                self.assertIn(word, said, guide)


class NoPrivatePaths(unittest.TestCase):
    """The app must never print anybody's real NAS path - not in help, not in
    an example, not in a default. It is somebody's user name on a screen."""

    def test_nowhere_in_the_interface(self):
        self.assertNotIn("volume1", P.PAGE.lower())

    def test_nor_in_any_task_it_declares(self):
        for t in R.all_tasks():
            said = " ".join([t.title, t.summary]
                            + [o.label for o in t.options]
                            + [o.help or "" for o in t.options])
            self.assertNotIn("volume1", said.lower(), t.name)

    def test_nor_anywhere_in_the_code_it_can_print(self):
        import glob
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        bad = []
        for path in (glob.glob(os.path.join(here, "core", "*.py"))
                     + glob.glob(os.path.join(here, "app", "*.py"))
                     + glob.glob(os.path.join(here, "app", "tasks", "*.py"))):
            with open(path, encoding="utf-8") as fh:
                if "volume1" in fh.read().lower():
                    bad.append(os.path.basename(path))
        self.assertEqual(bad, [], f"a private path is still in: {bad}")



class TheStyleGuide(unittest.TestCase):
    """Audit section 10.7: the rules the rewrite was written to, held against
    the shipped text so it cannot drift back. The rules themselves live in
    `core/wording.py`, where Setup > Wording warns about the same things while
    somebody is typing."""

    def test_every_option_has_help(self):
        bare = [f"{t.name}.{o.name}" for t in R.all_tasks() for o in t.options
                if not (o.help or "").strip()]
        self.assertEqual(bare, [])

    def test_no_text_breaks_the_style_guide(self):
        """A dash used as a full stop, capitals for emphasis, a sentence of
        more than 25 words, a semicolon, a word the glossary replaced, a name
        ending in a full stop. Every title, tab, line, summary, label, help,
        choice and group heading, as `describe()` gives them to the page."""
        from app.tasks import wording as TW
        from core import wording as W
        found = []
        for key, text in TW.shipped().items():
            said = W.problems(key, text)
            if said and said != ["no text"]:
                found.append(f"{key}: {', '.join(said)}: {text[:70]!r}")
        self.assertEqual(found, [], "\n  ".join(found))

    def test_a_number_says_what_it_counts(self):
        """In the label, in brackets ("Clock fast by (minutes)"), or in the
        first sentence of its help ("The lowest ISO to include")."""
        from core import wording as W
        mute = [f"{t.name}.{o.name}: {o.label!r}" for t in R.all_tasks()
                for o in t.options
                if o.kind == "number" and not W.names_a_unit(o.label, o.help)]
        self.assertEqual(mute, [], "\n  ".join(mute))

    def test_the_rules_catch_what_they_are_for(self):
        """The checks above pass on clean text, so each is tried once on text
        that breaks it, or a passing test could be a rule that never fires."""
        from core import wording as W
        cases = {
            "a dash used as a full stop": "Moves them - all of them.",
            "capitals for emphasis": "This MOVES them.",
            "glossary": "Moves the photographs.",
            "long sentence": " ".join(["word"] * 26) + ".",
            "a semicolon": "Moves them; all of them.",
        }
        for rule, text in cases.items():
            self.assertTrue(any(rule in p for p in W.problems("cull.summary", text)),
                            f"{rule!r} did not fire on {text!r}")
        for fine in ("A RAW file is never changed.", "A negative number moves "
                     "time backwards.", "Runs from DSM's Task Scheduler."):
            self.assertEqual(W.problems("cull.summary", fine), [], fine)
        self.assertFalse(W.names_a_unit("Sharpness", "How sharp it must be."))
        self.assertTrue(W.names_a_unit("Gap (hours)", ""))


def _glossary_hits(text):
    """The glossary words in one piece of text, after the names that only
    look like them (DSM's Task Scheduler, a negative number) are taken out."""
    from core import wording as W
    low = " ".join(text.split()).lower()
    for phrase in W.NOT_BANNED:
        low = low.replace(phrase, " ")
    return [w for w in W.BANNED
            if re.search(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", low)]


def _js_pieces(src):
    """(line, text) for every string and template literal in a script, outside
    comments and outside ${...}. Small on purpose: it has to tell a string from
    a regular expression and a comment, nothing more."""
    out, i, n, stack, last = [], 0, len(src), [], ""

    def keep(at, buf):
        out.append((src.count("\n", 0, at) + 1, "".join(buf)))

    def template(i):
        at, buf = i, []
        while i < n:
            c = src[i]
            if c == "\\":
                buf.append(src[i:i + 2]); i += 2; continue
            if c == "`":
                keep(at, buf); return i + 1, False
            if c == "$" and src[i + 1:i + 2] == "{":
                keep(at, buf); return i + 2, True
            buf.append(c); i += 1
        return i, False

    while i < n:
        c = src[i]
        if c in " \t\r\n":
            i += 1; continue
        if src.startswith("//", i):
            j = src.find("\n", i); i = n if j < 0 else j; continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2); i = n if j < 0 else j + 2; continue
        if c in "\"'":
            j, buf = i + 1, []
            while j < n and src[j] != c:
                step = 2 if src[j] == "\\" else 1
                buf.append(src[j:j + step]); j += step
            keep(i, buf); i = j + 1; last = "a"; continue
        if c == "`" or (c == "}" and stack and stack[-1] == 0):
            if c == "}":
                stack.pop()
            i, opened = template(i + 1)
            if opened:
                stack.append(0)
            last = "a"; continue
        if c == "{" and stack:
            stack[-1] += 1
        if c == "}" and stack:
            stack[-1] -= 1
        if c == "/" and (last in "(,=:[!&|?{};+-*%<>~^" or last in (
                "return", "typeof", "case", "in", "of")):
            j, cls = i + 1, False
            while j < n and src[j] != "\n":
                if src[j] == "\\":
                    j += 2; continue
                if src[j] == "[":
                    cls = True
                elif src[j] == "]":
                    cls = False
                elif src[j] == "/" and not cls:
                    break
                j += 1
            i = j + 1; last = "a"; continue
        m = re.match(r"[A-Za-z_$][\w$]*", src[i:i + 40])
        if m:
            last = m.group(); i += len(last); continue
        last = c; i += 1
    return out

def _js_visible(text):
    """What a person reads in one piece of a script's text: the words between
    tags, and the tooltips and labels inside them. A piece with no space that
    starts in lower case is a name the code uses (a route, a kind, a class),
    not something shown, so it is left out."""
    said = re.findall(r'(?:title|aria-label|placeholder|alt)="([^"$]*)"', text)
    shown = text
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"^[^<>]*>|<\w[^>]*$", " ", text)
    text = re.sub(r"&\w+;", " ", text)
    if re.search(r"\s", shown.strip()) or shown.strip()[:1].isupper():
        said.append(text)
    return [" ".join(t.split()) for t in said if t.strip()]


class TheGlossaryEverywhere(unittest.TestCase):
    """The glossary covers every word a person reads, not only the option text
    the style guide test sees. The audit's table was applied to that text and
    the rest kept saying "photograph", "negative" and "put aside": in a plan's
    notes and rows, in the viewer, on Home. So the whole table is held against
    the strings the Python can print and the text the page's script shows."""

    HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_nothing_the_python_can_print_uses_a_replaced_word(self):
        """Every string constant with a space in it, in the app, the tools,
        the core, the Windows program, the NAS starter and the doctor. A
        docstring, or a string standing alone as a note, is for whoever reads
        the source and is left out."""
        import ast
        import glob
        files = []
        for pattern in ("app/*.py", "app/tasks/*.py", "core/*.py",
                        "windows/*.py", "windows/*.pyw", "nas/*.py",
                        "scripts/*.py"):
            files += glob.glob(os.path.join(self.HERE, pattern))
        found = []
        for path in sorted(files):
            if path.endswith(os.path.join("core", "wording.py")):
                continue                 # the list itself
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            notes = {id(node.value) for node in ast.walk(tree)
                     if isinstance(node, ast.Expr)
                     and isinstance(node.value, ast.Constant)}
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                        and id(node) not in notes and " " in node.value.strip()):
                    hits = _glossary_hits(node.value)
                    if hits:
                        found.append(f"{os.path.relpath(path, self.HERE)}:"
                                     f"{node.lineno} {hits}: {node.value[:60]!r}")
        self.assertEqual(found, [], "\n  ".join(found))

    def test_nothing_the_page_shows_uses_a_replaced_word(self):
        """The script's own text (strings.json is held to the style guide
        already), the page frame, and the login page."""
        import glob
        web = os.path.join(self.HERE, "app", "web")
        found = []
        for path in ([os.path.join(web, "page", "script.js")]
                     + sorted(glob.glob(os.path.join(web, "library", "js", "*.js")))):
            with open(path, encoding="utf-8") as fh:
                pieces = _js_pieces(fh.read())
            for line, text in pieces:
                if text.startswith("api/"):
                    continue
                for said in _js_visible(text):
                    hits = _glossary_hits(said)
                    if hits:
                        found.append(f"{os.path.basename(path)}:{line} {hits}: "
                                     f"{said[:60]!r}")
        for name in ("page/index.html", "login.html"):
            with open(os.path.join(web, name), encoding="utf-8") as fh:
                html = re.sub(r"<(script|style)\b.*?</\1>", " ", fh.read(),
                              flags=re.S)
            html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
            for said in _js_visible(html):
                hits = _glossary_hits(said)
                if hits:
                    found.append(f"{name} {hits}: {said[:60]!r}")
        self.assertEqual(found, [], "\n  ".join(found))

    def test_the_scan_sees_what_it_is_for(self):
        """Each half is tried on text that breaks the table, so a pass is not a
        scan that never looks."""
        src = ('// a photograph in a comment is fine\n'
               'const a = "Show the photographs";\n'
               'const b = `<b title="One clip">${n}</b> negatives ${"x"} left`;\n'
               'const c = /photograph/.test(x) ? "kind" : "image";\n')
        shown = [s for _l, t in _js_pieces(src) for s in _js_visible(t)]
        hits = sorted({w for s in shown for w in _glossary_hits(s)})
        self.assertEqual(hits, ["clip", "negatives", "photographs"])
        self.assertEqual(_glossary_hits("Open DSM's Task Scheduler and add a "
                                        "Scheduled Task. A negative number."), [])
        self.assertEqual(_glossary_hits("Full-frame plan-free"), [])
        self.assertEqual(_glossary_hits("Nothing is written until you go ahead."),
                         ["go ahead"])


if __name__ == "__main__":
    unittest.main()


class ThePageStrings(unittest.TestCase):
    """The page's own words live in one table (app/web/page/strings.json) so
    the Wording tab can find and change them. A name the script asks for that
    the table lacks shows "undefined" on the screen; a name nobody asks for is
    text an editor changes and never sees."""

    def _script(self):
        import glob
        here = os.path.join(os.path.dirname(P.__file__), "web")
        out = ""
        for path in [os.path.join(here, "page", "script.js")] + \
                sorted(glob.glob(os.path.join(here, "library", "js", "*.js"))):
            with open(path, encoding="utf-8") as fh:
                out += fh.read()
        return out

    def test_every_name_the_script_asks_for_is_in_the_table(self):
        import re
        script = self._script()
        asked = set(re.findall(r"(?<![\w.$])S\.([A-Za-z_]\w*)", script))
        asked |= set(re.findall(r"\bsay\(\s*[\"']([A-Za-z_]\w*)[\"']", script))
        self.assertEqual(sorted(asked - set(P.STRINGS)), [])

    def test_and_every_name_in_the_table_is_asked_for(self):
        import re
        script = self._script()
        quiet = [k for k in P.STRINGS
                 if not re.search(r"(?<![\w.$])S\.%s\b|[\"']%s[\"']" % (k, k),
                                  script)]
        self.assertEqual(quiet, [])

    def test_counted_words_agree_with_their_number(self):
        """"3 file(s)" was the script's way round a plural; the table says
        {n:file|files} and say() picks one."""
        import re
        for name, text in P.STRINGS.items():
            self.assertNotRegex(text, r"\w\(s\)", name)
            for key in re.findall(r"\{(\w+):", text):
                self.assertIn("{%s}" % key, text, name)


class TheGuide(unittest.TestCase):
    """A tour, not a manual - and one that cannot quietly rot."""

    def test_every_page_points_at_a_feature_that_exists(self):
        """A guide that sends you to a tab renamed last month is worse than no
        guide: it teaches you the app is broken on page six."""
        names = {t.name for t in R.all_tasks()}
        for page in P.GUIDE:
            if page["open"]:
                self.assertIn(page["open"], names, page["title"])

    def test_and_every_main_feature_has_a_page(self):
        pointed = {page["open"] for page in P.GUIDE}
        for page in P.GUIDE:
            pointed |= set(page.get("covers") or [])
        for t in R.top_level():
            if t.name in ("history", "tidy"):
                continue                  # a log and a status tab, not features
            self.assertIn(t.name, pointed, f"no guide page for {t.title}")

    def test_a_page_is_short_enough_to_be_read(self):
        """The whole point of a bubble and a guide is that the long version is
        not on the screen. A guide page of four paragraphs is the docstring
        again."""
        for page in P.GUIDE:
            words = sum(len(b.split()) for b in page["body"])
            self.assertLessEqual(words, 60, page["title"])
            self.assertLessEqual(len(page["body"]), 2, page["title"])

    def test_it_does_not_assume_the_library_is_on_a_nas(self):
        """The machine running this might be a NAS, a PC or anything else, so
        the tour talks about your photo library. The one place a NAS is named
        is the tab that only means something on one."""
        import re
        for page in P.GUIDE:
            for line in page["body"]:
                for hit in re.finditer(r"\bNAS\b", line):
                    self.assertIn("NAS tab", line, page["title"])
        self.assertNotIn(">NAS<", P.ART["welcome"])

    def test_every_tool_it_names_is_one_that_exists(self):
        """A tool named in the tour must be named the way the rail and the
        Tools cards name it. "Send it to Files" pointed at a tool called File
        explorer, and "Sync carries stars" at one called Rating & tags.

        A capitalised word in the middle of a sentence is a name here, so each
        has to be part of a tool's title or tab, a screen of the library, or a
        name the app does not own."""
        import re
        vocabulary = set()
        for t in R.all_tasks():
            vocabulary.update((t.title + " " + (t.tab or "")).split())
        screens = {"Home", "Photos", "Places", "Albums", "People", "Tools",
                   "Settings", "All", "Arrange", "Bin"}
        others = {"Photo", "Manager", "Google", "Timeline", "Lightroom",
                  "Synology", "Recycle", "Spain", "Tuscany"}
        known = vocabulary | screens | others
        stale = []
        for page in P.GUIDE:
            for line in page["body"]:
                # the first word of each sentence is capitalised for being
                # first, not for being a name
                for sentence in re.split(r"(?<=[.!?:])\s+|'", line):
                    words = re.findall(r"[A-Za-z][\w&-]*", sentence)
                    for word in words[1:]:
                        if re.fullmatch(r"[A-Z][a-z][\w-]*", word) \
                                and word not in known:
                            stale.append(f"{page['title']}: {word}")
        self.assertEqual(stale, [], "the Guide names tools that do not exist")

    def test_it_says_tool_not_feature(self):
        for page in P.GUIDE:
            for line in page["body"]:
                for word in ("feature", "task"):
                    self.assertNotIn(word, line.lower(), page["title"])


class OneNamePerTool(unittest.TestCase):
    """The rail shows a tool's `tab`, the Tools cards, search and History its
    `title`. A shorter tab word is fine; a different name is two tools as far
    as anybody reading can tell: Time change and Fix the clock, Sync and
    Rating & tags were the same tool."""

    def test_a_tab_is_its_title_or_a_shortened_form_of_it(self):
        def words(text):
            return [w for w in text.lower().replace("&", " ").split() if w]
        odd = []
        for t in R.all_tasks():
            tab, title = words(t.tab or t.title), words(t.title)
            shortened = (tab == title[:len(tab)] or tab == title[-len(tab):]
                         or set(tab) <= set(title))
            if not shortened:
                odd.append(f"{t.name}: tab {t.tab!r}, title {t.title!r}")
        self.assertEqual(odd, [], "\n  ".join(odd))

    def test_every_skip_box_is_the_same_box(self):
        """The registry adds "Skip these folders" to every tool that walks
        folders. Exposure declared its own, "Folders to skip" under Tags, so
        one box had two names (audit TK12)."""
        seen = {}
        for t in R.all_tasks():
            for o in t.options:
                if o.name == "skip_here":
                    seen[t.name] = (o.label, o.group)
        self.assertIn("exposure", seen)
        odd = {k: v for k, v in seen.items() if v != ("Skip these folders", "Skip")}
        self.assertEqual(odd, {})

    def test_the_page_says_tool_not_feature(self):
        """The code keeps `Task`; a person reads "tool" everywhere."""
        for t in R.all_tasks():
            for o in t.options:
                said = [o.label] + [str(c[1]) for c in (
                    o.offered() if hasattr(o, "offered") else [])
                    if isinstance(c, (tuple, list))]
                for text in said:
                    self.assertNotIn("feature", text.lower(), f"{t.name}.{o.name}")
        from app import web
        tools = web.read("library/js/05-places-albums-tools.js")
        self.assertIn('placeholder="Find a tool or action..."', tools)

    def test_the_file_explorer_is_called_file_explorer(self):
        from app import web
        for piece, wanted in (("library/js/04-selection.js",
                               "Show in File explorer"),
                              ("library/js/08-folder-albums.js",
                               '["files", "File explorer"]'),
                              ("library/js/15-walk-folders.js",
                               "File explorer</button>")):
            self.assertIn(wanted, web.read(piece), piece)
        self.assertNotIn("Open the explorer", P.PAGE)
