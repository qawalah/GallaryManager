"""Colour labels: what they mean, what is actually written, and what they move.

A rating says how good a photograph is; a colour says what you want DONE with
it. That second axis is only worth having if it survives the trip out of this
app, so most of what is tested here is interoperability - the thing that cannot
be checked by looking at the screen:

- the colour WORD goes into xmp:Label, because "Red" is what Lightroom, Bridge
  and darktable read, and "AI sharpening" is a custom label nothing recognises;
- your name for it goes on as a keyword, which is the half other programs search;
- a JPEG's existing XMP - a crop, develop settings, a history - survives having
  a label written into it;
- labels written by OTHER programs are understood coming in, and a label this
  app does not recognise is never overwritten.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from core import jpegseg                   # noqa: E402
from core import labels as L               # noqa: E402
from core import settings as S             # noqa: E402
from core import sidecar as sc             # noqa: E402
from core import tags                      # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


class Tree(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="labels-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.raw = os.path.join(self.dir, "Photos Raw")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        S.save({"library": self.lib, "raw": self.raw})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def put(self, name="plain.JPG", fixture="plain", where=""):
        folder = os.path.join(self.lib, where) if where else self.shoot
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, name)
        shutil.copy(os.path.join(FIX, fixture + ".jpg"), target)
        return target

    def negative(self, name="plain.RW2", fixture="plain"):
        folder = os.path.join(self.raw, "2022", "Spain")
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, name)
        shutil.copy(os.path.join(FIX, fixture + ".jpg"), target)
        return target


class WhatIsWritten(Tree):
    def test_the_colour_word_goes_in_not_your_name_for_it(self):
        """Lightroom, Bridge and darktable read xmp:Label and expect a colour
        there. Writing "Sharpen" gives a custom label nothing recognises and no
        coloured swatch anywhere."""
        p = self.put()
        L.set_label(p, "yellow", ["Sharpen", "ai-sharpen"])
        self.assertEqual(L.written_label(p), "Yellow")

    def test_and_your_name_goes_on_as_a_keyword(self):
        """Which is the half other programs can act on - a keyword is searchable
        in Synology Photos, in Explorer's Tags column, in anything reading
        IPTC."""
        p = self.put()
        L.set_label(p, "yellow", ["Sharpen", "ai-sharpen"])
        on_it = [t.lower() for t in tags.tags_of(p)]
        self.assertIn("sharpen", on_it)
        self.assertIn("ai-sharpen", on_it)

    def test_it_is_written_in_both_places(self):
        """The sidecar is what Lightroom reads and the only thing a RAW can
        carry; inside the JPEG is what Synology Photos and Explorer look at."""
        p = self.put()
        L.set_label(p, "red", [])
        self.assertEqual(sc.read(p).get("xmp:Label"), "Red")
        self.assertIn("Red", jpegseg.xmp_packet(p))

    def test_a_raw_gets_a_sidecar_and_is_never_opened(self):
        neg = self.negative()
        with open(neg, "rb") as fh:
            before = fh.read()
        L.set_label(neg, "green", ["Timelapse"])
        with open(neg, "rb") as fh:
            self.assertEqual(fh.read(), before)
        self.assertEqual(sc.read(neg).get("xmp:Label"), "Green")

    def test_the_xmp_already_in_a_jpeg_survives(self):
        """A JPEG's packet can hold a crop, develop settings, a whole edit
        history. Rebuilding it from the one attribute this app cares about
        would throw all of that away without a word."""
        p = self.put()
        L.set_label(p, "red", [])                      # gives it a packet
        was = jpegseg.xmp_packet(p)
        mine = was.replace("<rdf:Description", '<rdf:Description crs:Sharpness="55"', 1)
        from core import tagwrite
        with open(p, "rb") as fh:
            original = fh.read()
        payload = jpegseg.XMP_NS + b"\x00" + mine.encode("utf-8")
        tagwrite._save(p, original,
                       tagwrite._replace_segment(original, 0xE1, payload,
                                                 lambda d: d.startswith(jpegseg.XMP_NS)))
        L.set_label(p, "blue", [])
        now = jpegseg.xmp_packet(p)
        self.assertIn('crs:Sharpness="55"', now)
        self.assertIn("Blue", now)

    def test_the_picture_itself_is_never_touched(self):
        p = self.put()
        with open(p, "rb") as fh:
            was = fh.read()
        original = was[jpegseg.scan_start(was):]
        L.set_label(p, "purple", ["something"])
        with open(p, "rb") as fh:
            after = fh.read()
        self.assertEqual(after[jpegseg.scan_start(after):], original)

    def test_an_empty_colour_clears_it(self):
        p = self.put()
        L.set_label(p, "red", [])
        L.set_label(p, "", [])
        self.assertEqual(L.written_label(p), "")
        self.assertEqual(L.colour_of(p), "")

    def test_a_colour_that_is_not_one_of_the_five_is_refused(self):
        p = self.put()
        with self.assertRaises(ValueError):
            L.set_label(p, "orange", [])


class WhatIsRead(Tree):
    def test_the_sidecar_wins_over_what_is_inside_the_photo(self):
        """The same rule as a rating, for the same reason: it is the one a
        person edited most recently in every tool that writes both."""
        p = self.put()
        L.set_label(p, "red", [])
        sc.write(p, **{"xmp:Label": "Green"})
        self.assertEqual(L.colour_of(p), "green")

    def test_bridges_own_names_are_understood(self):
        """Bridge ships with Select / Second / Approved / Review / To Do rather
        than colour names. A library labelled there would otherwise read as
        completely unlabelled."""
        for said, expect in (("Select", "red"), ("Second", "yellow"),
                             ("Approved", "green"), ("Review", "blue"),
                             ("To Do", "purple")):
            self.assertEqual(L.colour_named(said), expect, said)

    def test_so_is_the_name_you_gave_it(self):
        self.assertEqual(L.colour_named("Timelapse"), "green")
        self.assertEqual(L.colour_named("timelapse"), "green")

    def test_somebody_elses_label_resolves_to_nothing(self):
        """xmp:Label is a free string and another program may be using it for
        something this app has never heard of."""
        self.assertEqual(L.colour_named("Client approved 2019"), "")

    def test_a_photo_with_no_label_at_all_is_not_a_colour(self):
        self.assertEqual(L.colour_of(self.put()), "")


class WhereAColourSends(Tree):
    def test_a_blank_folder_means_the_develop_tree_itself(self):
        d = L.by_colour("red")
        self.assertEqual(L.send_folder(d, "/x/Develop"), "/x/Develop")

    def test_a_named_one_is_a_folder_inside_it(self):
        d = L.by_colour("green")
        self.assertEqual(L.send_folder(d, "/x/Develop"),
                         os.path.join("/x/Develop", "Timelapse"))

    def test_all_five_exist_even_when_nothing_is_defined(self):
        """A page that draws what it is given should draw five colours and say
        which are not set up, not silently show three."""
        S.save({f"label_{c}_name": "" for c in L.COLOURS})
        got = L.defined()
        self.assertEqual(len(got), 5)
        self.assertTrue(all(not d.defined for d in got))


class Tagging(Tree):
    """Tags are the half of a rating or a colour that anything else can search.

    Synology Photos looks for a keyword; Explorer shows one in its Tags column;
    nothing anywhere can search "the ones I marked green in Photo Manager". So
    this tab is the bridge out of the app, and it has three ways in: a folder at
    a time, by a rule about what is already on the photograph, and the words a
    colour MEANS - which is the repair for a colour put on by Lightroom or the
    tablet, neither of which could have written them.

    What every test here is really checking is the one promise that makes it
    safe to point at a whole library: tags are only ever ADDED.
    """

    def run_task(self, **over):
        t = R.get("tags")
        raw = {"folder": self.shoot, "with_raw": "", "with_previews": "",
               "which": "all", "words": "", "from_colour": ""}
        raw.update(over)
        return t, t.make_plan(raw)

    def bare_label(self, path, word="Green"):
        """A colour with no tags at all - what another program leaves."""
        sc.write(path, **{"xmp:Label": word})
        return path

    # ------------------------------------------------- a folder at a time

    def test_a_whole_folder_gets_the_words_you_typed(self):
        p = self.put()
        t, plan = self.run_task(words="Barcelona 2024, travel")
        self.assertEqual(len(plan.rows), 1)
        self.assertEqual(t.apply(plan).failed, 0)
        self.assertEqual({x.lower() for x in tags.tags_of(p)},
                         {"barcelona 2024", "travel"})

    def test_and_a_word_already_there_in_another_case_is_not_added_twice(self):
        p = self.put()
        sc.set_keywords(p, ["TRAVEL"])
        _t, plan = self.run_task(words="travel")
        self.assertEqual(plan.rows, [])

    def test_nothing_to_write_is_refused_rather_than_run(self):
        """A plan that would touch four hundred photographs and add nothing to
        any of them is not a plan, it is a mistake with a progress bar."""
        self.put()
        _t, plan = self.run_task()
        self.assertTrue(plan.blocked)
        self.assertIn("Nothing would be written", plan.blocked)

    # ------------------------------------------------------------ by a rule

    def test_by_rating_takes_the_ones_at_or_above_it(self):
        from core.exifwrite import write_rating
        good = self.put("good.JPG", fixture="rated")
        poor = self.put("poor.JPG")
        write_rating(good, 5)
        write_rating(poor, 2)
        _t, plan = self.run_task(words="portfolio", which="stars", stars=4)
        self.assertEqual([r.name for r in plan.rows], ["good.JPG"])
        self.assertTrue(any("rated 2" in why for _n, why in plan.skipped))

    def test_and_the_unrated_rule_is_the_other_way_round(self):
        from core.exifwrite import write_rating
        self.put("good.JPG", fixture="rated")
        write_rating(os.path.join(self.shoot, "good.JPG"), 5)
        self.put("blank.JPG")
        _t, plan = self.run_task(words="to look at", which="unrated")
        self.assertEqual([r.name for r in plan.rows], ["blank.JPG"])

    def test_and_a_rule_about_one_colour(self):
        self.bare_label(self.put("a.JPG"), "Green")
        self.bare_label(self.put("b.JPG", fixture="rated"), "Red")
        _t, plan = self.run_task(words="timelapse", which="colour", colour="red")
        self.assertEqual([r.name for r in plan.rows], ["b.JPG"])

    def test_a_rule_reads_the_photograph_so_it_can_be_run_again(self):
        """The point of a rule rather than a selection: run it next month and
        the frames rated since are picked up, the rest left alone."""
        from core.exifwrite import write_rating
        p = self.put()
        _t, plan = self.run_task(words="portfolio", which="stars", stars=4)
        self.assertEqual(plan.rows, [])
        write_rating(p, 5)
        _t, plan = self.run_task(words="portfolio", which="stars", stars=4)
        self.assertEqual(len(plan.rows), 1)

    def test_by_focal_range_reads_how_the_lens_frames(self):
        """The fixtures are a GH4 at 25mm with no full-frame figure recorded,
        so the number on the lens is what is left: Wide."""
        self.put()
        _t, plan = self.run_task(words="wide", which="focal",
                                 focal="Wide (24-35mm)")
        self.assertEqual(len(plan.rows), 1)
        _t, plan = self.run_task(words="tele", which="focal",
                                 focal="Tele (over 135mm)")
        self.assertEqual(plan.rows, [])

    def test_by_lens_matches_part_of_the_name(self):
        from core import facts
        from core.photo import Capture
        self.put()
        real = facts.Reader.capture
        facts.Reader.capture = lambda self, path, stat=None: Capture(
            path=path, lens="LUMIX G 25/F1.7 ASPH.", focal_length=25.0)
        try:
            _t, yes = self.run_task(words="nifty", which="lens", lens="25/f1.7")
            _t, no = self.run_task(words="nifty", which="lens", lens="12-35")
        finally:
            facts.Reader.capture = real
        self.assertEqual(len(yes.rows), 1)
        self.assertEqual(no.rows, [])

    def test_a_lens_the_camera_never_recorded_is_said_not_guessed(self):
        self.put()
        _t, plan = self.run_task(words="x", which="lens", lens="25")
        self.assertIn("did not record a lens", plan.skipped[0][1])

    # ------------------------------------------- the words a colour means

    def test_the_words_a_colour_means_are_written_onto_it(self):
        p = self.bare_label(self.put())
        t, plan = self.run_task(from_colour=True, which="missing")
        self.assertEqual(len(plan.rows), 1)
        self.assertEqual(t.apply(plan).failed, 0)
        want = {w.lower() for w in L.by_colour("green").all_keywords()}
        self.assertTrue(want <= {x.lower() for x in tags.tags_of(p)})

    def test_a_photograph_that_already_has_them_is_not_written_again(self):
        p = self.put()
        L.set_label(p, "green", L.by_colour("green").all_keywords())
        _t, plan = self.run_task(from_colour=True, which="missing")
        self.assertEqual(plan.rows, [])
        self.assertEqual(dict(plan.stats)["Already carry them"], "1")

    def test_only_the_missing_words_are_written(self):
        p = self.put()
        S.save({"label_green_keywords": "sequence, holding"})
        L.set_label(p, "green", [L.by_colour("green").name])
        _t, plan = self.run_task(from_colour=True, which="missing")
        self.assertEqual([r.data["tags"] for r in plan.rows],
                         [["sequence", "holding"]],
                         "the name it already has must not be written again")

    def test_somebody_elses_label_is_left_alone(self):
        """There is no meaning here to look up for another program's word."""
        p = self.put()
        sc.write(p, **{"xmp:Label": "Client approved 2019"})
        _t, plan = self.run_task(from_colour=True, which="missing")
        self.assertEqual(plan.rows, [])
        self.assertIn("not one of the five", plan.skipped[0][1])

    def test_a_colour_with_no_meaning_yet_is_said_rather_than_refused(self):
        """Unlike Apply label, which blocks: here the photographs are already
        marked, and the useful answer is which ones are waiting on a meaning."""
        S.save({"label_purple_name": ""})
        self.bare_label(self.put(), "Purple")
        _t, plan = self.run_task(from_colour=True, which="missing")
        self.assertFalse(plan.blocked)
        self.assertEqual(plan.rows, [])
        self.assertIn("no meaning set yet", plan.skipped[0][1])

    def test_your_words_and_the_colour_s_can_go_on_together(self):
        p = self.bare_label(self.put())
        t, plan = self.run_task(words="Spain", from_colour=True)
        t.apply(plan)
        on_it = {x.lower() for x in tags.tags_of(p)}
        self.assertIn("spain", on_it)
        self.assertIn(L.by_colour("green").name.lower(), on_it)

    # ---------------------------------------------------- and what it is not

    def test_it_never_puts_a_colour_on_or_takes_one_off(self):
        """Deciding a colour is Apply label, next door. Keeping the two apart is
        what makes this one safe to run over a whole library."""
        plain = self.put("plain.JPG")
        marked = self.bare_label(self.put("marked.JPG", fixture="rated"))
        t, plan = self.run_task(words="anything")
        t.apply(plan)
        self.assertEqual(L.written_label(plain), "")
        self.assertEqual(L.written_label(marked), "Green")

    def test_a_negative_answers_for_itself_with_no_pairing_at_all(self):
        """What a rule needs is written on each file already, so nothing has to
        be matched up first - the same shoot's folder in the RAW tree is simply
        looked through as well."""
        neg = self.negative()
        self.bare_label(neg)
        _t, plan = self.run_task(with_raw=True, from_colour=True, which="missing")
        self.assertEqual([r.name for r in plan.rows], [os.path.basename(neg)])

    def test_but_only_that_shoot_never_the_whole_raw_tree(self):
        """The bug this replaced: the RAW box followed to the matching shoot in
        the form, and the tree-settling that is right for a MIRRORING
        destination trimmed it back to the top of the tree - one shoot's worth
        of intent applied to every negative on the disk."""
        elsewhere = os.path.join(self.raw, "2019", "Rome")
        os.makedirs(elsewhere)
        other = os.path.join(elsewhere, "rome.RW2")
        shutil.copy(os.path.join(FIX, "plain.jpg"), other)
        self.bare_label(other)
        neg = self.negative()
        self.bare_label(neg)
        _t, plan = self.run_task(with_raw=True, from_colour=True, which="missing")
        self.assertEqual([r.name for r in plan.rows], [os.path.basename(neg)])

    def test_planning_alone_writes_nothing(self):
        p = self.bare_label(self.put())
        self.run_task(from_colour=True, which="missing")
        self.assertEqual(tags.tags_of(p), [])


class MarkingAFolder(Tree):
    def run_task(self, **over):
        t = R.get("label")
        raw = {"folder": self.shoot, "colour": "green", "raw": "", "previews": ""}
        raw.update(over)
        return t, t.make_plan(raw)

    def test_a_whole_folder_at_once(self):
        """The point of this tab: you usually know what a shoot is FOR before
        you have looked at a single frame of it."""
        self.put("a.JPG")
        self.put("b.JPG", fixture="rated")
        t, p = self.run_task()
        self.assertEqual(len(p.rows), 2)
        self.assertEqual(t.apply(p).failed, 0)
        self.assertEqual(L.colour_of(os.path.join(self.shoot, "a.JPG")), "green")

    def test_the_negative_gets_it_too(self):
        """A colour on the JPEG and not on the RAW means Lightroom shows the
        shoot as unlabelled the moment you open the negatives."""
        self.put()
        neg = self.negative()
        t, p = self.run_task(raw=self.raw)
        self.assertEqual(t.apply(p).failed, 0)
        self.assertEqual(L.colour_of(neg), "green")

    def test_a_photo_already_carrying_another_colour_is_left(self):
        """Overwriting would quietly undo an afternoon's work, and the old
        label is not recoverable from anything."""
        p = self.put()
        L.set_label(p, "red", [])
        _t, plan = self.run_task()
        self.assertEqual(plan.rows, [])
        self.assertIn("already Red", plan.skipped[0][1])

    def test_unless_you_ask_for_it(self):
        p = self.put()
        L.set_label(p, "red", [])
        t, plan = self.run_task(replace=True)
        self.assertEqual(len(plan.rows), 1)
        t.apply(plan)
        self.assertEqual(L.colour_of(p), "green")

    def test_somebody_elses_label_is_never_overwritten_even_then(self):
        """A label this app does not understand belongs to another program, and
        replacing it is not this app's to do at any setting."""
        p = self.put()
        sc.write(p, **{"xmp:Label": "Client approved 2019"})
        _t, plan = self.run_task(replace=True)
        self.assertEqual(plan.rows, [])
        self.assertIn("not one of the five", plan.skipped[0][1])

    def test_a_photo_already_that_colour_is_not_written_again(self):
        p = self.put()
        L.set_label(p, "green", ["Timelapse"])
        _t, plan = self.run_task()
        self.assertEqual(plan.rows, [])

    def test_a_colour_with_no_meaning_set_is_refused(self):
        """A mark nothing can read is not worth writing."""
        S.save({"label_purple_name": ""})
        _t, plan = self.run_task(colour="purple")
        self.assertTrue(plan.blocked)
        self.assertIn("Colour meanings", plan.blocked)

    def test_taking_it_off_again(self):
        p = self.put()
        L.set_label(p, "green", ["Timelapse"])
        t, plan = self.run_task(colour="clear")
        self.assertEqual(len(plan.rows), 1)
        t.apply(plan)
        self.assertEqual(L.colour_of(p), "")


class SendingByColour(Tree):
    """The other half: a colour that says "send this" actually sends it."""

    def setUp(self):
        super().setUp()
        self.develop = os.path.join(self.dir, "Develop")
        self.tl = os.path.join(self.lib, "2022", "Timelapse")
        os.makedirs(self.tl)
        S.save({"library": self.lib, "develop": self.develop, "raw": ""})

    def mark(self, folder, colour):
        t = R.get("label")
        p = t.make_plan({"folder": folder, "colour": colour, "raw": "",
                         "previews": ""})
        t.apply(p)

    def develop_plan(self, **over):
        t = R.get("develop")
        raw = {"folder": self.lib, "develop": self.develop, "raw": "",
               "mirror": False, "library": self.lib}
        raw.update(over)
        return t, t.make_plan(raw)

    def test_a_coloured_photo_is_sent_even_though_it_is_unrated(self):
        """Which is the whole point of the second axis: a timelapse frame is
        worth nothing on its own and everything as one of six hundred."""
        shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(self.tl, "a.JPG"))
        self.mark(self.tl, "green")
        _t, p = self.develop_plan()
        self.assertEqual(len(p.rows), 1)
        self.assertIn("green", p.rows[0].detail)

    def test_into_the_folder_its_colour_names(self):
        """Which is what keeps six hundred timelapse stills out of tonight's
        edits."""
        shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(self.tl, "a.JPG"))
        self.mark(self.tl, "green")
        _t, p = self.develop_plan()
        self.assertIn(os.path.join(self.develop, "Timelapse"), p.rows[0].target)

    def test_a_colour_beats_a_rating_over_which_folder(self):
        """Five stars says this is a good photograph; green says it is one of
        six hundred frames of a timelapse. Only one of those is an instruction
        about a folder."""
        shot = os.path.join(self.tl, "a.JPG")
        shutil.copy(os.path.join(FIX, "rated.jpg"), shot)
        self.mark(self.tl, "green")
        _t, p = self.develop_plan()
        self.assertEqual(len(p.rows), 1)
        self.assertIn("Timelapse", p.rows[0].target)

    def test_turning_the_colours_off_leaves_only_the_ratings(self):
        shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(self.tl, "a.JPG"))
        self.mark(self.tl, "green")
        _t, p = self.develop_plan(labels=False)
        self.assertEqual(p.rows, [])

    def test_a_colour_that_does_not_send_sends_nothing(self):
        S.save({"label_purple_name": "Someday", "label_purple_action": "none"})
        shutil.copy(os.path.join(FIX, "plain.jpg"), os.path.join(self.tl, "a.JPG"))
        self.mark(self.tl, "purple")
        _t, p = self.develop_plan()
        self.assertEqual(p.rows, [])


if __name__ == "__main__":
    unittest.main()
