"""A folder this app makes must come out like the one it was made inside.

The fault is silent at both ends, which is why it survived one fix already. This
app creates a folder, the files land in it correctly, nothing fails and nothing
is logged - and Synology Drive, which reads the library as YOU rather than as
this app, stops seeing a tree it cannot read and says nothing either.

The first fix carried the owner, the group and the mode. It did not carry the
EXTENDED ATTRIBUTES, and on DSM that is where the access list lives - which is
what File Station, Drive and Photos actually go by. So a new shoot folder had
the right owner and no access list at all: exactly the state that "Advanced
options > Make inherited permissions explicit" is the cure for. Every year
folder, every shoot folder, every Developed subfolder, for months.

The premise is asserted rather than assumed: a subdirectory created by os.mkdir
inherits NO extended attributes. If that ever stops being true, the first test
here fails and the rest of this module is unnecessary rather than wrong.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import registry as R                # noqa: E402
import app.tasks                             # noqa: E402,F401
from core import perms                       # noqa: E402
from core import settings as S               # noqa: E402
from core.paths import ensure_folder         # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
ACL = "user.pm-pretend-acl"          # stands in for DSM's own, which is system.*


def xattrs_work(path: str) -> bool:
    try:
        os.setxattr(path, ACL, b"x")
        os.removexattr(path, ACL)
        return True
    except OSError:
        return False


class Folders(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="perms-")
        self._was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = os.path.join(self.dir, "config")
        self.lib = os.path.join(self.dir, "Photos")
        os.makedirs(self.lib)
        if not xattrs_work(self.lib):
            self.skipTest("no extended attributes on this filesystem")
        os.setxattr(self.lib, ACL, b"an access list")
        os.chmod(self.lib, 0o2775)
        S.save({"library": self.lib})
        perms.forget_tool()

    def tearDown(self):
        if self._was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self._was
        perms.forget_tool()
        shutil.rmtree(self.dir, ignore_errors=True)

    # ------------------------------------------------------------ the premise

    def test_a_plain_new_subfolder_inherits_no_access_list_at_all(self):
        """The reason this module exists, asserted rather than assumed."""
        where = os.path.join(self.lib, "plain")
        os.mkdir(where)
        self.assertNotIn(ACL, os.listxattr(where))

    # ------------------------------ and the fix, which is NOT copying the list

    def test_this_app_does_not_copy_the_list_onto_a_new_folder(self):
        """It used to, and the copy was measurably worse than nothing.

        A blank new folder is repaired by `synoacltool -enforce-inherit`, which
        is what the scheduled job runs, and that worked. A folder carrying a
        verbatim copy of its parent's list already HAS one, so the same command
        treats it as settled and skips it - and the copy is not what DSM would
        have produced by inheritance, so Drive goes on ignoring the folder while
        every check on this side reports success. A whole-tree sweep that used
        to take minutes started finishing in under a second having done nothing.

        So the copy was not a fix that fell short. It was the thing preventing
        the fix, and this test is the record of that."""
        where = os.path.join(self.lib, "2022")
        perms.make_folder(where)
        self.assertNotIn(ACL, os.listxattr(where))

    def test_it_writes_the_folder_down_for_the_job_that_can(self):
        """Left blank ON PURPOSE is still waiting, so it still goes on the
        list."""
        from core import acl as _acl
        where = os.path.join(self.lib, "2022")
        perms.make_folder(where)
        self.assertIn(where, _acl.waiting())

    def test_and_so_does_every_level_of_a_deep_one(self):
        """`os.makedirs` in one call would leave the year folder AND the shoot
        inside it unknown to anything - which is how a whole restructure comes
        out invisible to Drive."""
        from core import acl as _acl
        where = os.path.join(self.lib, "2022", "07", "Spain")
        perms.make_folder(where)
        waiting = _acl.waiting()
        for part in (os.path.join(self.lib, "2022"),
                     os.path.join(self.lib, "2022", "07"), where):
            self.assertIn(part, waiting, part)

    def test_the_mode_and_the_setgid_bit_come_too(self):
        where = os.path.join(self.lib, "2022")
        perms.make_folder(where)
        self.assertEqual(os.stat(where).st_mode & 0o7777, 0o2775)

    def test_ensure_folder_is_the_way_every_task_makes_one(self):
        """One choke point, so no task can make a folder the plain way - which
        would be a folder nothing ever hears about."""
        from core import acl as _acl
        where = os.path.join(self.lib, "2022", "Spain")
        ensure_folder(where)
        self.assertIn(where, _acl.waiting())

    def test_a_folder_that_already_exists_is_left_exactly_as_it_is(self):
        where = os.path.join(self.lib, "2022")
        os.mkdir(where)
        os.setxattr(where, ACL, b"its own, different")
        ensure_folder(where)
        self.assertEqual(os.getxattr(where, ACL), b"its own, different")

    # --------------------------------------------- but a FILE is not a folder

    def test_a_file_does_not_take_a_folders_default_list(self):
        """A directory's `posix_acl_default` is what it hands to things created
        inside it and means nothing on a file. Copying a folder's list onto a
        photograph would be inventing something plausible, which is the thing
        this module refuses to do.

        Asked of the decision rather than of the filesystem: the copying loop
        swallows every refusal, so a wrong answer here would look exactly like
        the kernel declining and never be noticed."""
        self.assertFalse(perms.travels("system.posix_acl_default", False))

    def test_but_a_folder_does(self):
        self.assertTrue(perms.travels("system.posix_acl_default", True))

    def test_and_the_access_list_travels_to_both(self):
        """Whatever it is called. This app does not know which attribute DSM
        keeps its list in, and must not have to."""
        for name in ("system.ntfs_acl", "system.posix_acl_access",
                     "user.whatever", ACL):
            self.assertTrue(perms.travels(name, True), name)
            self.assertTrue(perms.travels(name, False), name)

    def test_but_one_inode_s_own_marks_never_do(self):
        """A capability or an selinux label describes that exact file and
        nothing else."""
        for name in ("security.capability", "security.selinux"):
            self.assertFalse(perms.travels(name, True), name)
            self.assertFalse(perms.travels(name, False), name)

    def test_a_file_still_loses_the_executable_bits(self):
        where = os.path.join(self.lib, "a.JPG")
        shutil.copy(os.path.join(FIX, "plain.jpg"), where)
        perms.like_parent(where)
        self.assertFalse(os.stat(where).st_mode & 0o111)

    # ------------------------------------------------------------ DSM's tool

    def test_it_asks_the_tool_what_it_can_do_rather_than_remembering(self):
        """`-copy` and `-enforce-inherit` both appear in the wild and neither is
        documented by Synology, so which exist depends on the DSM version -
        and running a command a build does not have would fail once a folder,
        quietly, into nobody's log."""
        self.assertFalse(perms.dsm_can("-copy"), "there is no synoacltool here")
        self.assertEqual(perms.dsm_tool(), "")

    def test_and_writes_the_folder_down_when_the_tool_is_not_there(self):
        """The only two ways a folder gets its list: DSM's tool here and now, or
        the job later. Never this app inventing one."""
        from core import acl as _acl
        where = os.path.join(self.lib, "2022")
        perms.make_folder(where)
        self.assertNotIn(ACL, os.listxattr(where))
        self.assertEqual(_acl.waiting(), [where])


class TheCheck(Folders):
    """Proving it on the machine that matters, because it cannot be proved from
    anywhere else: the access list is DSM's and the filesystem is DSM's."""

    def test_it_makes_a_real_folder_compares_it_and_removes_it(self):
        got = perms.try_a_folder(self.lib)
        self.assertTrue(got["made"])
        self.assertTrue(got["removed"])
        self.assertFalse(os.path.exists(got["folder"]))
        self.assertEqual(got["compare"]["different"], [])
        # The access list the parent has and the new folder does not - which is
        # now the expected answer rather than a fault, because this app leaves
        # it for the job. Owner and mode are still expected to match.
        self.assertEqual(got["compare"]["only_parent"], [ACL])

    def test_and_it_compares_before_it_probes_not_after(self):
        """The check does two different things - what did creation produce, and
        could this app write a list if it tried - and the order decides whether
        the first answer is true. Probing first would leave the test folder
        carrying a list nothing else ever gets, and the tab would report every
        tree as perfect while every real folder came out blank."""
        got = perms.try_a_folder(self.lib)
        self.assertIn(ACL, got["compare"]["only_parent"])

    def test_and_it_does_not_leave_the_tree_looking_as_if_it_changed(self):
        """A check must not schedule work.

        Making a folder inside another one moves the OUTER folder's modified
        date, and that date is exactly what Automation watches to decide whether
        a tree has anything new in it. Left moved, pressing Have a look here
        would set every watched tree running on the next pass - over a library
        where nothing happened - and the pass after that, and so on. Found by a
        test in another file failing for a reason that had nothing to do with
        what it was testing."""
        was = os.stat(self.lib).st_mtime_ns
        perms.try_a_folder(self.lib)
        self.assertEqual(os.stat(self.lib).st_mtime_ns, was)

    def test_the_same_goes_for_the_can_it_write_here_probe(self):
        was = os.stat(self.lib).st_mtime_ns
        yes, why = perms.can_write(self.lib)
        self.assertTrue(yes, why)
        self.assertEqual(os.stat(self.lib).st_mtime_ns, was)

    def test_and_the_probe_answers_no_where_it_cannot(self):
        yes, why = perms.can_write(os.path.join(self.lib, "not there"))
        self.assertFalse(yes)
        self.assertIn("no folder", why)

    def test_it_removes_it_even_when_the_comparison_goes_wrong(self):
        """A check that litters the library with test folders is a check nobody
        runs twice."""
        was = perms.compare
        perms.compare = lambda *a: (_ for _ in ()).throw(ValueError("no"))
        try:
            got = perms.try_a_folder(self.lib)
        finally:
            perms.compare = was
        self.assertTrue(got["removed"])
        self.assertFalse(os.path.exists(got["folder"]))

    def test_without_dsm_s_tool_an_empty_list_is_the_design_not_a_fault(self):
        """The tab has to say the same thing the code does, or it reports a
        working arrangement as broken every time it is opened. Blank is what a
        new folder is SUPPOSED to be here - the job fills it."""
        p = R.get("permissions").make_plan({})
        self.assertEqual(dict(p.stats)["Coming out wrong"], "0")
        self.assertIn("left for the repair job", " ".join(p.rows[0].cells))
        self.assertIn("on purpose", " ".join(p.notes))

    def test_but_with_the_tool_reachable_a_missing_list_IS_a_fault(self):
        """Then the folder was supposed to be finished at birth, and a missing
        list means DSM's own tool did not do what it was asked."""
        real_tool, real_copy = perms.dsm_tool, perms._dsm_copied
        perms.dsm_tool = lambda: "/usr/syno/bin/synoacltool"
        perms._dsm_copied = lambda parent, folder: False
        try:
            p = R.get("permissions").make_plan({})
        finally:
            perms.dsm_tool, perms._dsm_copied = real_tool, real_copy
        self.assertEqual(dict(p.stats)["Coming out wrong"], "1")
        self.assertIn("NOT CARRIED", " ".join(p.rows[0].cells))
        self.assertIn("does NOT come out", " ".join(p.notes))

    def test_and_owner_or_mode_coming_out_wrong_is_always_a_fault(self):
        """Whatever is happening with the access list. That half is this app's
        own doing and nothing else repairs it."""
        real = perms.like_parent
        perms.like_parent = lambda path: False
        try:
            p = R.get("permissions").make_plan({})
        finally:
            perms.like_parent = real
        self.assertEqual(dict(p.stats)["Coming out wrong"], "1")

    def test_it_does_not_need_to_know_which_attribute_holds_the_list(self):
        """Which is why it compares all of them: the name is DSM's business and
        differs by version and filesystem."""
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(perms.compare).strip())
        body = tree.body[0].body
        if (isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)):
            body = body[1:]                       # the docstring may say it
        code = "\n".join(ast.unparse(x) for x in body).lower()
        for guessed in ("ntfs", "syno", "posix_acl", "security."):
            self.assertNotIn(guessed, code, guessed)

    def test_the_repair_script_is_only_written_when_asked(self):
        p = R.get("permissions").make_plan({})
        self.assertFalse(any("script" in r.data for r in p.rows))
        p = R.get("permissions").make_plan({"repair": True})
        self.assertTrue(any("script" in r.data for r in p.rows))

    def test_and_it_is_plain_text_that_moves_no_photograph(self):
        t = R.get("permissions")
        p = t.make_plan({"repair": True})
        t.apply(p)
        where = [r.data["script"] for r in p.rows if "script" in r.data][0]
        with open(where, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("synoacltool", text)
        self.assertIn(self.lib, text)
        for dangerous in ("rm ", "mv ", "chmod -R", "chown -R"):
            self.assertNotIn(dangerous, text, dangerous)

    def test_the_check_tab_never_writes_without_the_box(self):
        t = R.get("permissions")
        result = t.apply(t.make_plan({}))
        self.assertEqual(result.done, 0)


if __name__ == "__main__":
    unittest.main()
