"""The folders this app cannot finish, and the job that finishes them.

**Why there is a queue at all, in one paragraph.** DSM keeps its access list -
the thing File Station, Drive and Photos actually go by - in a privileged
extended attribute. Writing one needs root. Running this app as your own user is
the right arrangement for everything else, so on the NAS the app is a normal
user and the kernel answers "Operation not permitted" every time it tries. That
is not a bug to try harder at; it is the arrangement. The first test below is
the measurement that says so, and if it ever stops being true the rest of this
is unnecessary rather than wrong.

So the app does the half it can (owner, group, mode, every attribute it is
allowed), writes down the folders where the other half did not happen, and a job
in DSM's Task Scheduler running as root puts exactly those right. The tests here
run that job - the real generated script, under a real shell, against a stand-in
for `synoacltool` - because a script nothing ever executes is a script that is
wrong in some small way nobody finds until the library needs it.

**The one property everything rests on: neither side ever rewrites the file.**
Two different users share it. Whoever rewrites a file becomes its owner, and the
moment root did that, this app - as you - could never append to it again, and
the queue would look empty forever while folders quietly went unfixed. It would
have been the same silent failure one layer up. So the app appends, the job
appends, and only the app ever rewrites.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import acl                          # noqa: E402
from core import perms                        # noqa: E402

ACL = "user.pm-pretend-acl"      # stands in for DSM's own, which is privileged

TOOL = """#!/bin/sh
if [ $# -eq 0 ]; then
  echo "Usage: synoacltool -get <path>"
  echo "       synoacltool -enforce-inherit <path>"
  exit 0
fi
echo "$@" >> "$(dirname "$0")/calls.txt"
"""


def xattrs_work(path: str) -> bool:
    try:
        os.setxattr(path, ACL, b"x")
        return True
    except OSError:
        return False


class Store(unittest.TestCase):
    """Every test gets its own data folder - the list is a file, not an idea."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="acl-")
        self.data = os.path.join(self.dir, "data")
        self.lib = os.path.join(self.dir, "lib")
        os.makedirs(self.data)
        os.makedirs(self.lib)
        self.was = os.environ.get("PM_DATA")
        os.environ["PM_DATA"] = self.data

    def tearDown(self):
        if self.was is None:
            os.environ.pop("PM_DATA", None)
        else:
            os.environ["PM_DATA"] = self.was
        shutil.rmtree(self.dir, ignore_errors=True)

    def queue(self) -> str:
        return os.path.join(self.data, acl.QUEUE)


class TheList(Store):
    def test_a_folder_goes_on_it_with_the_reason_it_had_to(self):
        self.assertEqual(acl.remember(["/a/b"], "could not write x: no"), 1)
        self.assertEqual(acl.waiting(), ["/a/b"])
        self.assertIn("could not write x", acl.why_waiting())

    def test_the_same_folder_twice_is_still_one_folder(self):
        acl.remember(["/a/b"])
        self.assertEqual(acl.remember(["/a/b", "/a/c"]), 1)
        self.assertEqual(acl.waiting(), ["/a/b", "/a/c"])

    def test_and_the_job_finishing_empties_it(self):
        acl.remember(["/a/b", "/a/c"])
        acl.finished(2, 0)
        self.assertEqual(acl.waiting(), [])
        self.assertEqual(acl.last_run()["fixed"], 2)

    def test_but_anything_added_after_that_is_waiting_again(self):
        acl.remember(["/a/b"])
        acl.finished(1)
        acl.remember(["/a/d"])
        self.assertEqual(acl.waiting(), ["/a/d"])

    def test_never_run_is_said_as_never_run_rather_than_as_zero(self):
        """"has never run" and "ran and found nothing" are different answers
        and only one of them means you still have something to set up."""
        self.assertEqual(acl.last_run(), {})

    def test_the_check_s_own_folder_never_lands_on_it(self):
        """It makes a folder and removes it a line later. A job handed a path
        that is not there would say so on every run, forever."""
        with acl.quiet():
            self.assertEqual(acl.remember(["/a/b"]), 0)
        self.assertEqual(acl.waiting(), [])
        self.assertEqual(acl.remember(["/a/b"]), 1)

    def test_compacting_keeps_what_waits_and_what_last_happened(self):
        for n in range(5):
            acl.remember([f"/a/{n}"])
        acl.finished(5)
        acl.remember(["/a/late"])
        self.assertTrue(acl.compact())
        self.assertEqual(acl.waiting(), ["/a/late"])
        self.assertEqual(acl.last_run()["fixed"], 5)
        with open(self.queue(), encoding="utf-8") as fh:
            self.assertEqual(len(fh.readlines()), 2)

    def test_a_folder_that_went_away_can_be_taken_off(self):
        acl.remember(["/a/b", "/a/c"])
        self.assertTrue(acl.forget("/a/b"))
        self.assertEqual(acl.waiting(), ["/a/c"])

    def test_and_none_of_it_raises_when_there_is_nowhere_to_write(self):
        """A folder that has to be blessed again later is not worth failing a
        photograph over."""
        blocked = os.path.join(self.dir, "a-file")
        with open(blocked, "w", encoding="utf-8") as fh:
            fh.write("not a folder, and root cannot make it one either")
        os.environ["PM_DATA"] = os.path.join(blocked, "data")
        self.assertEqual(acl.remember(["/a/b"]), 0)
        self.assertEqual(acl.waiting(), [])
        self.assertEqual(acl.last_run(), {})


class WhatCannotBeDoneFromInHere(Store):
    """The measurement the whole design rests on."""

    def test_a_privileged_attribute_is_refused_to_a_normal_user(self):
        """Root can write `security.*`; a normal user cannot. DSM's access list
        lives in exactly that kind of attribute, which is why the app running as
        you - which is right for every other reason - cannot write it."""
        if not xattrs_work(self.lib):
            self.skipTest("no extended attributes on this filesystem")
        code = ("import os,sys\n"
                "try:\n"
                "    os.setxattr(sys.argv[1], 'security.pmpretend', b'x')\n"
                "    print('wrote')\n"
                "except OSError as exc:\n"
                "    print(exc.strerror)\n")
        os.chmod(self.dir, 0o755)
        os.chmod(self.lib, 0o777)
        try:
            got = subprocess.run(
                ["setpriv", "--reuid", "65534", "--regid", "65534",
                 "--clear-groups", sys.executable, "-c", code, self.lib],
                capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            self.skipTest("cannot drop privileges here")
        if got.returncode != 0:
            self.skipTest("cannot drop privileges here")
        self.assertNotIn("wrote", got.stdout, got.stdout)
        self.assertIn("permi", got.stdout.lower(), got.stdout)

    def test_so_the_refusal_is_reported_instead_of_swallowed(self):
        """The line that cost months: every OSError went into a `pass`, so the
        app copied the owner, copied the mode, wrote no access list at all and
        reported the fix as done."""
        refused = []
        real = os.setxattr

        def no(*_a, **_k):
            raise PermissionError(1, "Operation not permitted")

        os.setxattr = no
        try:
            done = perms.put_xattrs(self.lib, {"system.syno_acl": b"x"},
                                    to_folder=True, refused=refused)
        finally:
            os.setxattr = real
        self.assertEqual(done, 0)
        self.assertEqual(refused, [("system.syno_acl", "Operation not permitted")])

    def test_every_folder_it_makes_is_handed_to_the_job_that_can(self):
        """Not only the ones something refused. This app no longer writes an
        access list at all - see `perms.like_parent` - so a folder it creates is
        blank on purpose, and blank on purpose is still waiting."""
        made = os.path.join(self.lib, "2024")
        perms.make_folder(made)
        self.assertEqual(acl.waiting(), [made])
        self.assertIn("only DSM", acl.why_waiting())

    def test_and_it_carries_the_system_s_own_words_when_there_were_any(self):
        """The reason is kept when something actually refused - "Operation not
        permitted" is worth putting on a screen and "left for the job" is
        not the same sentence."""
        perms.hand_over(os.path.join(self.lib, "x"),
                        [("system.syno_acl", "Operation not permitted")])
        self.assertIn("Operation not permitted", acl.why_waiting())

    def test_but_nothing_is_listed_when_dsm_s_own_tool_did_it_here_and_now(self):
        """An empty list has to mean there is genuinely nothing to do, or the
        job stops being something that costs nothing to run every few minutes.
        With the tool reachable the folder is finished at birth."""
        real = perms._dsm_copied
        perms._dsm_copied = lambda parent, folder: True
        try:
            perms.make_folder(os.path.join(self.lib, "2024"))
        finally:
            perms._dsm_copied = real
        self.assertEqual(acl.waiting(), [])

    def test_and_the_check_says_which_attribute_and_why(self):
        if not xattrs_work(self.lib):
            self.skipTest("no extended attributes on this filesystem")
        os.setxattr(self.lib, ACL, b"an access list")
        real = os.setxattr

        def only_ours(path, name, value, **kw):
            if name == ACL:
                raise PermissionError(1, "Operation not permitted")
            return real(path, name, value, **kw)

        os.setxattr = only_ours
        try:
            got = perms.try_a_folder(self.lib)
        finally:
            os.setxattr = real
        self.assertEqual(got["refused"], [(ACL, "Operation not permitted")])
        self.assertTrue(got["removed"])
        self.assertEqual(acl.waiting(), [], "the check must not queue its own")

    def test_and_the_check_still_asks_whether_it_COULD_have_written_one(self):
        """Creation no longer writes an access list, so the check has to ask the
        question separately: could this app write one if it tried? That is the
        difference between "left for the job, as designed" and "this app is not
        allowed to, and here is the system's own sentence"."""
        if not xattrs_work(self.lib):
            self.skipTest("no extended attributes on this filesystem")
        os.setxattr(self.lib, ACL, b"an access list")
        got = perms.try_a_folder(self.lib)
        self.assertEqual(got["refused"], [])


class TheJob(Store):
    """The generated script, run under a real shell against a stand-in tool.

    Not read, RUN. The thing being tested is a shell script assembled from
    strings, and every way it can be wrong - a quoting slip, an option this DSM
    does not have, a loop that counts in a subshell and throws the count away -
    is invisible until it runs.
    """

    def setUp(self):
        super().setUp()
        if not os.path.exists("/bin/sh"):
            self.skipTest("no shell here")
        self.tool = os.path.join(self.dir, "synoacltool")
        with open(self.tool, "w", encoding="utf-8") as fh:
            fh.write(TOOL)
        os.chmod(self.tool, 0o755)
        self.script = os.path.join(self.data, acl.SCRIPT)

    def write(self, trees=(), uid=None, gid=None):
        text = acl.script_text(trees, uid=uid, gid=gid).replace(
            "TOOL=/usr/syno/bin/synoacltool", f"TOOL={self.tool}")
        with open(self.script, "w", encoding="utf-8") as fh:
            fh.write(text)
        return text

    def run_it(self, *args):
        return subprocess.run(["/bin/sh", self.script, *args],
                              capture_output=True, text=True, timeout=120)

    def calls(self):
        where = os.path.join(self.dir, "calls.txt")
        if not os.path.exists(where):
            return []
        with open(where, encoding="utf-8") as fh:
            return [ln.strip() for ln in fh if ln.strip()]

    def test_it_fixes_exactly_the_folders_that_were_waiting(self):
        a = os.path.join(self.lib, "a")
        b = os.path.join(self.lib, "b")
        os.makedirs(a)
        os.makedirs(b)
        os.makedirs(os.path.join(self.lib, "untouched"))
        acl.remember([a, b])
        self.write()
        got = self.run_it()
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(self.calls(),
                         [f"-enforce-inherit {a}", f"-enforce-inherit {b}"])

    def test_and_says_so_in_the_list_so_the_app_knows_it_happened(self):
        a = os.path.join(self.lib, "a")
        os.makedirs(a)
        acl.remember([a])
        self.write()
        self.run_it()
        self.assertEqual(acl.waiting(), [])
        self.assertEqual(acl.last_run()["fixed"], 1)

    def test_a_run_with_nothing_waiting_costs_one_line_and_no_tool_call(self):
        """Which is what makes running it every few minutes reasonable."""
        self.write()
        got = self.run_it()
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(self.calls(), [])
        self.assertTrue(acl.last_run())

    def test_a_folder_that_has_since_gone_is_skipped_not_failed(self):
        a = os.path.join(self.lib, "a")
        os.makedirs(a)
        acl.remember([a, os.path.join(self.lib, "moved-away")])
        self.write()
        self.run_it()
        self.assertEqual(self.calls(), [f"-enforce-inherit {a}"])
        self.assertEqual(acl.last_run()["failed"], 0)

    def test_it_asks_the_tool_which_option_this_dsm_has(self):
        """`-copy` and `-enforce-inherit` both appear in the wild and neither is
        documented, so a script that remembers one would fail a folder at a time
        into nobody's log."""
        with open(self.tool, "w", encoding="utf-8") as fh:
            fh.write(TOOL.replace("-enforce-inherit <path>", "-copy <a> <b>"))
        os.chmod(self.tool, 0o755)
        a = os.path.join(self.lib, "a")
        os.makedirs(a)
        acl.remember([a])
        self.write()
        self.run_it()
        self.assertEqual(self.calls(), [f"-copy {self.lib} {a}"])

    def test_all_goes_over_the_trees_for_what_was_made_before_any_of_this(self):
        self.write([self.lib])
        got = self.run_it("all")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(self.calls(), [f"-enforce-inherit {self.lib}"])

    def test_it_finds_its_list_beside_itself_rather_than_being_told_where(self):
        """DSM and the container call the same folder by different names. A path
        written into the script would be right in one of them and wrong in the
        other, and the wrong one fails silently - there is simply nothing
        waiting, forever."""
        text = self.write()
        self.assertIn('HERE=$(dirname "$0")', text)
        self.assertNotIn(self.data, text)

    def test_and_never_writes_over_the_list_because_that_would_take_it(self):
        """The property the whole arrangement depends on. This job runs as root;
        the app runs as you. Rewriting a file makes you its owner, so the first
        rewrite by root would lock the app out of its own list - and the app
        would go on believing nothing was waiting."""
        text = self.write()
        self.assertIn('>> "$QUEUE"', text)
        self.assertNotIn('> "$QUEUE"', text.replace('>> "$QUEUE"', ""))
        for dangerous in ("rm ", "mv ", "chmod"):
            self.assertNotIn(dangerous, text, dangerous)

    def test_the_one_chown_it_has_can_only_reach_what_root_owns(self):
        """The narrowest repair that fixes the fault, and no wider.

        A tree this app cannot write into fails every task on every file in it,
        and the cause is always the same: folders made while the app ran as
        root. `chown -R` would fix that and also take everything else in the
        library in passing - a share deliberately owned by somebody else, a
        mount, a folder another program keeps. `find -uid 0` takes exactly what
        root has and nothing else, and there is only one way for root to own
        something inside a photo library."""
        text = self.write([self.lib], uid=4242, gid=100)
        for line in text.splitlines():
            if "chown" in line:
                self.assertIn("-uid 0", line, line)
                self.assertNotIn("-R", line, line)
        self.assertEqual(text.count("chown"), 1)

    def test_and_it_hands_back_only_those(self):
        mine = os.path.join(self.lib, "mine")
        theirs = os.path.join(self.lib, "theirs")
        os.makedirs(mine)
        os.makedirs(theirs)
        try:
            os.chown(mine, 0, 0)
            os.chown(theirs, 4243, 100)
        except OSError:
            self.skipTest("cannot change an owner here")
        self.write([self.lib], uid=4242, gid=100)
        got = self.run_it("own")
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(os.stat(mine).st_uid, 4242)
        self.assertEqual(os.stat(theirs).st_uid, 4243,
                         "somebody else's folder is not this script's business")

    def test_and_says_so_rather_than_guessing_when_it_has_no_one_to_give_to(self):
        text = acl.script_text([self.lib])            # no uid worked out
        self.assertNotIn("chown", text)
        with open(self.script, "w", encoding="utf-8") as fh:
            fh.write(text.replace("TOOL=/usr/syno/bin/synoacltool",
                                  f"TOOL={self.tool}"))
        got = self.run_it("own")
        self.assertEqual(got.returncode, 1)
        self.assertIn("give things back to", got.stdout)

    def test_and_it_is_the_app_that_keeps_the_list_short(self):
        """Only one of the two may rewrite it, so shortening is the app's job."""
        a = os.path.join(self.lib, "a")
        os.makedirs(a)
        for n in range(20):
            os.makedirs(f"{a}/{n}")
            acl.remember([f"{a}/{n}"])
        self.write()
        self.run_it()
        acl.remember([a])
        self.assertTrue(acl.compact())
        self.assertEqual(acl.waiting(), [a])
        self.assertEqual(acl.last_run()["fixed"], 20)

    def test_and_says_so_when_not_one_folder_on_the_list_is_here(self):
        """A path this app and DSM spell differently would look exactly like
        "nothing to do", on every run, forever. It is the same silent failure
        this whole tab exists because of, so it gets a sentence."""
        acl.remember(["/somewhere/else/entirely"])
        self.write()
        got = self.run_it()
        self.assertIn("spell those paths", got.stderr)

    def test_and_folders_that_all_went_away_still_leave_the_list(self):
        """Nothing was fixed and nothing failed - and if that counted as "no
        work done" the job would not write its mark, and it would go looking for
        the same missing folders on every run from now on."""
        acl.remember([os.path.join(self.lib, "gone-a"),
                      os.path.join(self.lib, "gone-b")])
        self.write()
        self.run_it()
        self.assertEqual(acl.waiting(), [])


class OnThePageItself(Store):
    """Not only in a Setup tab. The wait means Synology Drive cannot see those
    folders yet, and neither Drive nor this app would otherwise say so."""

    def health(self) -> dict:
        from app import server
        return server._permissions_waiting()

    def test_nothing_waiting_says_nothing(self):
        self.assertEqual(self.health()["waiting"], 0)
        self.assertFalse(self.health()["stale"])

    def test_waiting_with_no_job_ever_is_worth_interrupting_for(self):
        acl.remember(["/a/b"])
        got = self.health()
        self.assertEqual(got["waiting"], 1)
        self.assertTrue(got["stale"])
        self.assertFalse(got["ever"])

    def test_but_waiting_for_the_next_run_in_a_minute_is_not(self):
        """The job runs every few minutes. A banner for the ordinary gap
        between one run and the next would be on the screen permanently, and a
        warning that is always there is not read when it matters."""
        acl.finished(3)
        acl.remember(["/a/b"])
        self.assertFalse(self.health()["stale"])


class NotOnAPC(Store):
    """On a copy started as a Windows program there is no permissions job, no
    DSM and no Synology Drive, so the page must not count folders "waiting"
    for them. The tool itself stays: the command line still runs it."""

    def setUp(self):
        super().setUp()
        self.desk = os.environ.get("PM_DESKTOP")

    def tearDown(self):
        if self.desk is None:
            os.environ.pop("PM_DESKTOP", None)
        else:
            os.environ["PM_DESKTOP"] = self.desk
        super().tearDown()

    def page_says(self, desktop: bool) -> dict:
        from app import server
        os.environ["PM_DESKTOP"] = "1" if desktop else ""
        return server.health()["permissions"]

    def test_on_a_pc_nothing_is_waiting_however_long_the_list(self):
        acl.remember(["/a/b", "/a/c"])
        got = self.page_says(desktop=True)
        self.assertEqual(got["waiting"], 0)
        self.assertFalse(got["stale"])

    def test_on_the_nas_the_same_list_still_raises_it(self):
        acl.remember(["/a/b", "/a/c"])
        got = self.page_says(desktop=False)
        self.assertEqual(got["waiting"], 2)
        self.assertTrue(got["stale"])


if __name__ == "__main__":
    unittest.main()
