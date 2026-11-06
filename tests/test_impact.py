"""What the button says, and what the box above it says.

The audit's sharpest finding was not about colours. It was that the page asks
you to approve four hundred rows and never says the one sentence that would let
you check them - what is being done, to how many, out of where, into where - and
that the button said "Go ahead with these 184" on every tab in the app, which is
exactly where the missing verb belongs.

These tests are about that sentence being true. A wrong impact box is worse than
none: it is a reassurance about something that is not what is going to happen.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R                # noqa: E402
import app.tasks                            # noqa: E402,F401
from app import page as P                   # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class EveryTaskCanNameWhatItDoes(unittest.TestCase):
    def test_everything_that_writes_has_a_verb(self):
        """Without one the button falls back to "Go ahead with these 184",
        which is the sentence this whole change exists to get rid of."""
        mute = [t.name for t in R.all_tasks()
                if t.writes and not t.settings and not t.verb]
        self.assertEqual(mute, [], f"no verb: {mute}")

    def test_and_nothing_that_only_reports_has_one(self):
        """A verb on a tab that writes nothing would put a button offering to
        do something on a page that cannot."""
        odd = [t.name for t in R.all_tasks() if not t.writes and t.verb]
        self.assertEqual(odd, [])

    def test_a_verb_is_a_verb_and_a_unit_is_a_noun(self):
        for t in R.all_tasks():
            if not t.verb:
                continue
            self.assertLessEqual(len(t.verb.split()), 4, t.name)
            self.assertLessEqual(len(t.unit.split()), 3, t.name)
            self.assertEqual(t.verb, t.verb.strip(), t.name)
            self.assertEqual(t.verb[:1], t.verb[:1].upper(),
                             f"{t.name}: a button starts with a capital")

    def test_the_sentence_it_makes_reads_properly(self):
        """What the button will actually say, assembled here so a unit that
        only works in the singular is caught before it is on screen."""
        for t in R.all_tasks():
            if not t.verb or not t.unit:
                continue
            said = f"{t.verb} 184 {t.unit}"
            self.assertNotIn("  ", said, t.name)
            self.assertLessEqual(len(said), 44, f"{t.name}: {said!r} is a label")

    def test_anything_irreversible_says_so_in_its_own_words(self):
        """Risk and silence together would mean a red card with nothing on it
        saying why it is red."""
        for t in R.all_tasks():
            if t.risk == "high":
                self.assertTrue(t.undo.strip(),
                                f"{t.name} is marked irreversible and says "
                                f"nothing about putting it back")

    def test_the_destructive_ones_are_the_ones_marked(self):
        """Named rather than derived: these are the three tabs that can lose
        something you cannot get back, and if a fourth appears it should be a
        decision somebody made rather than a default it inherited.

        The sample library is a fourth, and it marks itself in the PLAN rather
        than here - "remove it" is irreversible and "build it" is not, which is
        a property of the run and not of the tab."""
        self.assertEqual(sorted(t.name for t in R.all_tasks() if t.risk == "high"),
                         ["cleanup", "delfolder", "unlocate"])
        task = R.get("demo")
        self.assertEqual(task.risk, "")


class WhereItWouldHappen(unittest.TestCase):
    def test_the_first_folder_box_is_where_it_reads_from(self):
        task = R.get("bydate")
        plan = R.Plan(task="bydate", rows=[R.Row(name="a.jpg")],
                      opts={"folder": "/photos/heap", "into": "/photos/sorted"})
        got = R.impact_of(task, plan)
        self.assertEqual(got["from"], "/photos/heap")
        self.assertEqual([w["path"] for w in got["into"]], ["/photos/sorted"])

    def test_a_destination_is_named_by_its_own_label(self):
        """"Into: /x" is half an answer when a task writes into three trees.
        The label is the box it came from, which is the word the person chose
        it with."""
        task = R.get("bydate")
        plan = R.Plan(task="bydate", rows=[R.Row(name="a.jpg")],
                      opts={"folder": "/photos", "into": "/sorted", "raw": "/raws"})
        got = R.impact_of(task, plan)
        self.assertEqual([w["label"] for w in got["into"]],
                         [o.label for o in task.options
                          if o.name in ("into", "raw")])

    def test_a_list_of_folders_to_skip_is_never_read_as_a_destination(self):
        """The one reading that would be a flat lie: "into: the folders you
        told it to leave alone"."""
        task = R.get("bydate")
        plan = R.Plan(task="bydate", rows=[R.Row(name="a.jpg")],
                      opts={"folder": "/photos", "skip_here": "/photos/Mobile"})
        got = R.impact_of(task, plan)
        self.assertEqual(got["into"], [])

    def test_the_same_folder_twice_is_not_two_places(self):
        task = R.get("unpair")
        plan = R.Plan(task="unpair", rows=[R.Row(name="a.rw2")],
                      opts={"folder": "/photos", "raw": "/photos"})
        self.assertEqual(R.impact_of(task, plan)["into"], [])

    def test_a_plan_may_correct_any_of_it(self):
        task = R.get("bydate")
        plan = R.Plan(task="bydate", rows=[R.Row(name="a.jpg")],
                      opts={"folder": "/photos"},
                      impact={"verb": "Rebuild", "count": 9000})
        got = R.impact_of(task, plan)
        self.assertEqual(got["verb"], "Rebuild")
        self.assertEqual(got["count"], 9000)
        self.assertEqual(got["from"], "/photos", "it threw away what it knew")

    def test_the_count_is_every_row_even_when_the_table_is_trimmed(self):
        """The rows sent to the page stop at `ROWS_SENT`. A confirmation that
        read "Move 20,000 files" about a plan holding 20,400 would be the worst
        kind of wrong: too small, and reassuring."""
        from app import server
        task = R.get("bydate")
        many = server.ROWS_SENT + 400
        plan = R.Plan(task="bydate", opts={"folder": "/photos"},
                      rows=[R.Row(name=f"{i}.jpg") for i in range(many)])
        payload = server.plan_payload(task, plan, "job")
        self.assertEqual(len(payload["rows"]), server.ROWS_SENT)
        self.assertEqual(payload["impact"]["count"], many)

    def test_a_search_of_thousands_travels_whole(self):
        """Two thousand rows was the ceiling when the page drew every row it
        was handed. A search that matched six thousand listed a third of them;
        the page draws a few hundred at a time now, so the rest go too."""
        from app import server
        self.assertGreaterEqual(server.ROWS_SENT, 6000)


class ThePageSaysIt(unittest.TestCase):
    def test_the_button_is_built_from_the_verb(self):
        self.assertIn("function opWords", P.SCRIPT)
        self.assertIn("${im.verb} ${num(n)} ${im.unit}", P.SCRIPT)

    def test_there_is_a_card_naming_what_changes(self):
        for want in ["function changingCard", "Out of", "Operation", "Afterwards"]:
            self.assertIn(want, P.SCRIPT, want)

    def test_the_irreversible_ones_ask_twice(self):
        self.assertIn("function sureAbout", P.SCRIPT)
        self.assertIn("await sureAbout", P.SCRIPT)

    def test_and_red_is_never_the_only_thing_saying_so(self):
        """Colour alone fails for a colour-blind reader and in a screenshot.
        The card is outlined, the heading carries a warning mark, and the
        button is the red one."""
        self.assertIn('.card.risky', P.STYLE)
        self.assertIn('icon("warn")', P.SCRIPT)

    def test_a_run_reports_four_outcomes_not_one(self):
        for want in ["function outcomeTiles", "Left alone", "Not reached",
                     "Failed", "function nextStep"]:
            self.assertIn(want, P.SCRIPT, want)

    def test_a_plan_that_found_nothing_says_so(self):
        self.assertIn("function nothingCard", P.SCRIPT)
        self.assertIn("Nothing to do", P.SCRIPT)

    def test_the_four_steps_are_the_same_four_everywhere(self):
        self.assertIn('const STEPS = ["Set it up", "Check the list", "Apply",',
                      P.SCRIPT)
        self.assertIn("function setStep", P.SCRIPT)

    def test_the_advanced_settings_are_one_disclosure(self):
        self.assertIn("function formGroups", P.SCRIPT)
        self.assertIn('details class="fold adv"', P.SCRIPT)


class WhatUndoingALocationTakes(unittest.TestCase):
    """Geotag and Pin used to promise that the original was kept aside, while
    Keep originals was off by default and nothing was kept (audit TK13). The
    confirmation has to say what this run will actually leave behind."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.shoot = os.path.join(self.dir, "Shoot")
        self.ref = os.path.join(self.dir, "Reference")
        os.makedirs(self.shoot)
        os.makedirs(self.ref)
        shutil.copy(os.path.join(FIX, "plain.jpg"),
                    os.path.join(self.shoot, "a.JPG"))
        shutil.copy(os.path.join(FIX, "phone_doha.jpg"),
                    os.path.join(self.ref, "ref.JPG"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def said(self, name, **opts):
        task = R.get(name)
        if name == "geotag":
            base = {"folder": self.shoot, "phone": self.ref,
                    "order": "photos_only", "max_gap": 100000}
        else:
            base = {"folder": self.shoot, "link": "24.4672, 39.6112"}
        plan = task.make_plan({**base, **opts})
        self.assertFalse(plan.blocked, plan.blocked)
        return R.impact_of(task, plan)["undo"]

    def test_with_the_box_off_nothing_claims_a_copy(self):
        for name in ("geotag", "pin"):
            keep = next(o for o in R.get(name).options
                        if o.name == "keep_originals")
            self.assertFalse(keep.default,
                             "the shipped answer is written for the box off")
            undo = self.said(name)
            self.assertNotIn("_NoLocation", undo, name)
            self.assertNotIn("kept", undo, name)
            self.assertIn(R.get("unlocate").title, undo, name)

    def test_with_the_box_on_the_copy_is_the_undo(self):
        for name in ("geotag", "pin"):
            self.assertIn("_NoLocation", self.said(name, keep_originals=True), name)


if __name__ == "__main__":
    unittest.main()
