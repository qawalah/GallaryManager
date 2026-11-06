"""Who owns what this app writes - the fault that reports itself as nothing.

Every metadata write here is done the safe way: build the whole new file, then
`os.replace` it over the old one, so a crash half way cannot leave half a
photograph. The cost is invisible and arrives months later: a replaced file is a
NEW file, with the owner, group and mode of whatever process wrote it.

This app runs in a container as root. So syncing ratings across a library
quietly re-owned every rated JPEG in it to root - and nothing failed, nothing
was logged, every photograph was still there and still correct. What broke was
Synology Drive, which reads the library as YOU: a tree it can no longer read is
a tree it stops syncing, and it does not say so either. The repair was by hand
in File Station - Properties, Permission, make inherited permissions explicit,
apply to sub-folders and files.

Nothing here can be checked by looking at the app. Hence these.

Most of it needs root to test properly - changing an owner does - so the
owner half skips where it cannot run, and the MODE half is checked everywhere,
because it is the same code path and the same mistake.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R              # noqa: E402
import app.tasks                           # noqa: E402,F401
from core import perms                     # noqa: E402
from core import settings as S             # noqa: E402
from core import sidecar as sc             # noqa: E402
from core.exifwrite import set_rating      # noqa: E402
from core.paths import ensure_folder       # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")

# 0o2750 rather than 0o755: the setgid bit is what DSM sets on a share so that
# everything made inside it keeps the share's group, and it is exactly the bit a
# plain os.makedirs throws away.
LIKE_DSM = 0o2750


def mode(path) -> int:
    return os.stat(path).st_mode & 0o7777


class Tree(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="perms-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        self.shoot = os.path.join(self.lib, "2022", "Spain")
        os.makedirs(self.shoot)
        for where in (self.lib, os.path.join(self.lib, "2022"), self.shoot):
            os.chmod(where, LIKE_DSM)
        S.save({"library": self.lib})

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        shutil.rmtree(self.dir, ignore_errors=True)

    def put(self, name="plain.JPG", fixture="plain", perm=0o640):
        target = os.path.join(self.shoot, name)
        shutil.copy(os.path.join(FIX, fixture + ".jpg"), target)
        os.chmod(target, perm)
        return target


class RewritingInPlace(Tree):
    """The one that actually happened."""

    def test_a_rating_does_not_change_who_owns_the_photograph(self):
        p = self.put()
        was = os.stat(p)
        set_rating(p, 4)
        now = os.stat(p)
        self.assertEqual((now.st_uid, now.st_gid), (was.st_uid, was.st_gid))

    def test_nor_its_mode(self):
        """Which is the same code path, and checkable without being root."""
        p = self.put(perm=0o640)
        set_rating(p, 4)
        self.assertEqual(mode(p), 0o640)

    def test_nor_does_writing_a_keyword(self):
        from core import tagwrite
        p = self.put(perm=0o640)
        tagwrite.add(p, ["timelapse"], in_file=True, in_sidecar=False)
        self.assertEqual(mode(p), 0o640)

    def test_nor_does_writing_a_colour_label(self):
        from core import labels as L
        p = self.put(perm=0o640)
        L.set_label(p, "red", ["Edit"])
        self.assertEqual(mode(p), 0o640)

    def test_nor_does_writing_a_location(self):
        """Geotagging is the one that touches the MOST files in a sitting - a
        whole library in one run - so it is the one that would re-own the most
        of it."""
        from core.exifwrite import write_gps
        p = self.put(perm=0o640)
        write_gps(p, 41.9028, 12.4964)
        self.assertEqual(mode(p), 0o640)

    def test_nor_correcting_the_capture_time(self):
        import datetime as dt
        from core.exifwrite import set_datetime
        p = self.put(perm=0o640)
        set_datetime(p, dt.datetime(2022, 7, 1, 9, 0, 0))
        self.assertEqual(mode(p), 0o640)


class MakingFolders(Tree):
    def test_a_new_shoot_folder_looks_like_the_one_above_it(self):
        """Not like whatever umask the app happens to be running under. A year
        folder that is root's while the library around it is yours is how Drive
        stops seeing a tree."""
        deep = os.path.join(self.lib, "2019", "Rome", "day one")
        ensure_folder(deep)
        self.assertTrue(os.path.isdir(deep))
        for level in (os.path.join(self.lib, "2019"),
                      os.path.join(self.lib, "2019", "Rome"), deep):
            self.assertEqual(mode(level), LIKE_DSM, level)

    def test_every_level_of_it_not_only_the_last(self):
        """os.makedirs makes them all at once and gives them all the process's
        umask - so the deepest one being right proves nothing about the ones
        above it, which is where a sync actually stops."""
        made = perms.make_folder(os.path.join(self.lib, "a", "b", "c"))
        self.assertEqual(len(made), 3)
        self.assertTrue(all(mode(m) == LIKE_DSM for m in made))

    def test_one_that_is_already_there_is_left_exactly_as_it_is(self):
        os.chmod(self.shoot, 0o2700)
        ensure_folder(self.shoot)
        self.assertEqual(mode(self.shoot), 0o2700)


class MakingFiles(Tree):
    def test_a_sidecar_takes_after_its_photograph(self):
        """A root-owned .xmp beside your RAW is a rating that quietly does not
        exist to anything reading the library as you."""
        p = self.put("plain.RW2", perm=0o640)
        side = sc.write(p, **{"xmp:Rating": "5"})
        self.assertEqual(mode(side), 0o640)

    def test_a_copy_out_to_develop_takes_after_the_photograph_it_came_from(self):
        """A copy of your photograph is your photograph - not something owned by
        whoever happened to run the copy. The tablet syncs that tree as you."""
        rated = self.put("rated.JPG", fixture="rated", perm=0o640)
        develop = os.path.join(self.dir, "Develop")
        os.makedirs(develop)
        os.chmod(develop, LIKE_DSM)
        t = R.get("develop")
        p = t.make_plan({"folder": self.lib, "develop": develop, "raw": "",
                         "mirror": False, "library": self.lib})
        self.assertEqual(t.apply(p).failed, 0)
        out = os.path.join(develop, "2022", "Spain", os.path.basename(rated))
        self.assertTrue(os.path.isfile(out), os.listdir(develop))
        self.assertEqual(mode(out), mode(rated))

    def test_a_preview_takes_after_the_photograph_it_was_made_from(self):
        """It is GENERATED, so it has nothing of its own to keep - and the photo
        it stands for is a real file, of the same kind, with a real access list
        on it. Better than guessing from the folder."""
        try:
            from PIL import Image                              # noqa: F401
        except Exception:                                      # noqa: BLE001
            self.skipTest("Pillow is not installed here")
        source = self.put(perm=0o640)
        previews = os.path.join(self.dir, "Previews")
        os.makedirs(previews)
        os.chmod(previews, LIKE_DSM)
        t = R.get("previews")
        p = t.make_plan({"folder": self.shoot, "previews": previews,
                         "mirror": False, "library": self.lib})
        self.assertEqual(t.apply(p).failed, 0)
        made = [os.path.join(r, f) for r, _d, fs in os.walk(previews) for f in fs]
        self.assertTrue(made)
        for one in made:
            self.assertEqual(mode(one), mode(source), one)


class TheAccessList(Tree):
    """The half that owner and mode do not cover - and on a Synology, the half
    that actually decides.

    DSM keeps its own access control list in an extended attribute, and File
    Station, Drive and Photos go by THAT rather than by the Unix bits
    underneath. `os.replace` leaves a file with none of it, which is exactly the
    state that Properties > Permission > "make inherited permissions explicit"
    is the cure for.

    There is no DSM here to make a real one, so these use an extended attribute
    of the same shape. What is being tested is that the bytes on the file before
    a write are the bytes on it afterwards - which is the whole claim.
    """

    def acl(self, path, value=b"a-synology-acl"):
        try:
            os.setxattr(path, "user.pm_test_acl", value)
        except OSError:
            self.skipTest("this filesystem does not keep extended attributes")
        return value

    def test_a_rating_does_not_strip_it(self):
        p = self.put()
        mine = self.acl(p)
        set_rating(p, 5)
        self.assertEqual(perms.xattrs_of(p).get("user.pm_test_acl"), mine)

    def test_nor_does_a_keyword_or_a_colour(self):
        from core import labels as L
        p = self.put()
        mine = self.acl(p)
        L.set_label(p, "green", ["Timelapse"])
        self.assertEqual(perms.xattrs_of(p).get("user.pm_test_acl"), mine)

    def test_nor_does_a_location(self):
        from core.exifwrite import write_gps
        p = self.put()
        mine = self.acl(p)
        write_gps(p, 41.9028, 12.4964)
        self.assertEqual(perms.xattrs_of(p).get("user.pm_test_acl"), mine)

    def test_a_sidecar_is_given_its_photographs_one(self):
        p = self.put("plain.RW2")
        mine = self.acl(p)
        side = sc.write(p, **{"xmp:Rating": "5"})
        self.assertEqual(perms.xattrs_of(side).get("user.pm_test_acl"), mine)

    def test_a_new_folder_is_left_blank_for_the_job_that_can_fill_it(self):
        """This test has now been written three ways, and the history is the
        point.

        First it asserted that a new folder gets NOTHING - which was the bug:
        Synology Drive could not see any folder this app made.

        Then it asserted the opposite, that a new folder takes a verbatim copy
        of its parent's list. That looked obviously right and was worse than the
        bug: `synoacltool -enforce-inherit`, which is what the repair job runs,
        repairs a BLANK folder and skips one that already has a list. The copy
        is not what DSM produces by inheritance, so Drive went on ignoring the
        folder while every check on this side reported success - and the
        whole-tree sweep that used to take minutes began finishing in under a
        second having done nothing.

        So: blank again, deliberately, and written down on a list for the root
        job. The lesson underneath all three is the same one - this app must not
        guess at somebody else's format, and "it looks the same" is not the test
        that matters. What matters is whether the thing that READS it agrees."""
        self.acl(self.lib, b"the-librarys-own")
        made = perms.make_folder(os.path.join(self.lib, "2019"))
        self.assertEqual(len(made), 1)
        self.assertIsNone(perms.xattrs_of(made[0]).get("user.pm_test_acl"))
        from core import acl as _acl
        self.assertIn(made[0], _acl.waiting())

    def test_but_a_FILE_is_still_never_given_a_folders(self):
        """The half that was right. A file takes after a real file of the same
        kind in the same place - see `like()` - and never after a directory."""
        self.acl(self.lib, b"the-librarys-own")
        p = self.put("plain.jpg")
        perms.like_parent(p)
        self.assertIsNone(perms.xattrs_of(p).get("user.pm_test_acl"))

    def test_one_that_cannot_be_written_is_not_an_error(self):
        p = self.put()
        self.assertEqual(perms.put_xattrs(p, {"nonsense-name": b"x"}), 0)
        self.assertTrue(os.path.isfile(p))


class SayingSoBeforeItBites(Tree):
    """The fault is silent at both ends - the app is happy and Drive says
    nothing - so the only place it can be caught early is out loud."""

    def test_it_says_nothing_when_the_owner_matches(self):
        self.assertEqual(perms.mismatch(self.lib), "")

    def test_and_does_not_hand_out_the_advice_that_turned_out_to_be_wrong(self):
        """It used to say that running the container as your own user "removes
        the question entirely". It does the opposite for the half that matters.

        Ownership, yes. The ACCESS LIST, no: DSM keeps it in a privileged
        extended attribute, and a normal user cannot write one - the kernel
        answers "Operation not permitted". So that advice traded a problem the
        app already solves by copying the parent for one it cannot solve at all,
        and it was on the screen for months. What replaced it is the repair job,
        and this test is here so the old sentence cannot come back."""
        if perms.writes_as()[0] != 0:
            self.skipTest("not running as root here, which is the happy case")
        borrowed = os.path.join(self.dir, "borrowed")
        os.makedirs(borrowed)
        try:
            os.chown(borrowed, 1026, 100)
        except OSError:
            self.skipTest("cannot change an owner here")
        said = perms.mismatch(borrowed)
        self.assertIn("1026", said)
        self.assertNotIn("removes the question", said)
        self.assertIn("access list", said)

    def test_a_folder_that_is_not_there_is_not_a_complaint(self):
        self.assertEqual(perms.mismatch(os.path.join(self.dir, "nowhere")), "")


class NeverFatal(Tree):
    """A photograph correctly filed with awkward permissions is a far better
    outcome than a move that failed."""

    def test_restoring_onto_something_that_has_gone_is_not_an_error(self):
        p = self.put()
        was = perms.stat_of(p)
        os.remove(p)
        self.assertFalse(perms.restore(p, was))

    def test_nor_is_taking_after_something_that_is_not_there(self):
        self.assertFalse(perms.like(os.path.join(self.dir, "a"),
                                    os.path.join(self.dir, "b")))

    def test_and_a_rating_still_lands_when_the_owner_cannot_be_changed(self):
        p = self.put()
        real = perms.restore
        perms.restore = lambda *a, **k: False
        try:
            set_rating(p, 5)
        finally:
            perms.restore = real
        from core.exifwrite import rating_of
        self.assertEqual(rating_of(p), 5)


class SayingWhyItWasDenied(Tree):
    """"156 x Permission denied" is one mystery instead of a hundred and
    fifty-six, and still not a thing anybody can act on.

    The grouping was the right first move and it only ever says WHAT. The cause
    on this NAS is nearly always the same, and it is knowable from the disk
    rather than guessable: the folder belongs to root and this app is you. That
    happens for exactly one reason - the folder was made while the app itself
    ran as root - and it makes every task pointed at that tree fail on every
    file in it.
    """

    def as_user(self, uid):
        """Pretend to be somebody else, without needing to actually be."""
        real = perms.writes_as
        perms.writes_as = lambda: (uid, 100)
        self.addCleanup(lambda: setattr(perms, "writes_as", real))

    def test_it_names_the_owner_and_the_user_this_app_is(self):
        self.as_user(1026)
        said = perms.denied_note([os.path.join(self.lib, "a.JPG")])
        self.assertIn(str(os.stat(self.lib).st_uid), said)
        self.assertIn("1026", said)
        self.assertIn("ran as root", said)

    def test_but_says_nothing_when_the_owner_is_already_this_app(self):
        """A confident wrong explanation is worse than none. If those two agree
        this is an ordinary permission problem and the usual story does not
        apply."""
        self.as_user(os.stat(self.lib).st_uid)
        self.assertEqual(perms.denied_note([os.path.join(self.lib, "a.JPG")]), "")

    def test_a_run_of_failures_carries_the_reason_with_it(self):
        from app.registry import Result
        self.as_user(1026)
        r = Result()
        for n in ("a.JPG", "b.JPG", "c.JPG"):
            r.blame(os.path.join(self.lib, n), "[Errno 13] Permission denied")
        lines = r.lines()
        self.assertIn("3 x", lines[0])
        self.assertTrue(any("ran as root" in x for x in lines), lines)

    def test_and_so_does_a_plan_that_could_not_read_a_tree(self):
        """The other half of the same fault: a tree that cannot be READ turns up
        as a plan error, in a different place on the screen, with the same one
        word of explanation."""
        from app import registry as R
        import app.tasks                            # noqa: F401
        self.as_user(1026)
        task = R.get("previews")
        real = task.plan

        def refuses(opts, **kw):
            p = real(opts, **kw) if _takes_progress(real) else real(opts)
            p.errors.append(f"could not read {self.lib}: Permission denied")
            return p

        def _takes_progress(fn):
            import inspect
            return "progress" in inspect.signature(fn).parameters

        task.plan = refuses
        try:
            plan = task.make_plan({"folder": self.lib, "previews": self.lib})
        finally:
            task.plan = real
        self.assertTrue(any("ran as root" in n for n in plan.notes), plan.notes)

    def test_a_task_refuses_before_it_fails_a_hundred_times(self):
        """One hundred and fifty-six photographs failed one at a time with
        "Permission denied" - a hundred and fifty-six attempts at something that
        could not have worked once. Every task declares which trees it writes
        into, so the refusal is worked out from that declaration and every
        feature gains it at the same moment."""
        from app import registry as R
        import app.tasks                            # noqa: F401
        out = os.path.join(self.dir, "Previews")
        os.makedirs(out)
        real = perms.can_write
        perms.can_write = lambda where: (
            (False, "Permission denied") if where == out else real(where))
        try:
            plan = R.get("previews").make_plan(
                {"folder": self.lib, "previews": out, "mirror": ""})
        finally:
            perms.can_write = real
        self.assertIn("cannot write into", plan.blocked)
        self.assertIn(out, plan.blocked)
        self.assertIn("every single file would fail", plan.blocked)

    def test_but_a_destination_that_is_not_there_yet_is_not_a_refusal(self):
        """Plenty of tasks make their own destination. Blocking those would be
        a fault invented out of nothing."""
        from app import registry as R
        import app.tasks                            # noqa: F401
        out = os.path.join(self.dir, "not made yet")
        plan = R.get("previews").make_plan(
            {"folder": self.lib, "previews": out, "mirror": ""})
        self.assertFalse(plan.blocked, plan.blocked)

    def test_the_folder_is_read_out_of_the_walkers_own_sentence(self):
        from app.registry import _denied_path
        self.assertEqual(
            _denied_path("could not read /a/b/Photos Previews: Permission denied"),
            "/a/b/Photos Previews")
        self.assertEqual(_denied_path("nothing useful here"), "")


if __name__ == "__main__":
    unittest.main()
