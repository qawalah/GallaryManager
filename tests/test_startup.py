"""The container's startup: finding the code, and becoming the right user.

Every bug this guards against has already happened once, and each surfaced far
from its cause:

- "No module named app.server", which reads as the app being broken and is
  really a mount off by one folder.
- Everything owned by root, which you discover days later when Windows will not
  let you delete a `_Culled` folder.
- A path typo, which Docker turns into an empty root-owned folder rather than an
  error, so it fails much later as "not writable".

The privilege drop itself can only be exercised as root; those tests skip
otherwise rather than pretending to pass.
"""

import os
import shutil
import subprocess
import sys
import threading
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

RUN = os.path.join(ROOT, "nas", "run.py")
AS_ROOT = hasattr(os, "getuid") and os.getuid() == 0
NOBODY = (65534, 65534)


def start(env, timeout=30):
    """Run the launcher until the server says it is listening, then stop it.

    The watchdog is not belt and braces. Reading a pipe until an expected line
    appears blocks for ever when it never does - so a launcher that fails in a
    new way stops being a failing test and becomes a test run that hangs, which
    is far harder to work out from a wall of dots.
    """
    # PM_PILLOW=skip matters more than it looks: without it every one of these
    # would try to pip install Pillow into its own fresh temp folder, which on a
    # machine that has no Pillow means ten downloads and a test run that looks
    # like it has hung.
    p = subprocess.Popen([sys.executable, RUN], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True,
                         cwd=os.path.abspath(os.sep),
                         env={**os.environ, "PM_PILLOW": "skip", **env})
    out = []
    watchdog = threading.Timer(timeout, p.kill)
    watchdog.start()
    try:
        for line in p.stdout:
            out.append(line)
            if "stop with Ctrl+C" in line:
                break
    finally:
        watchdog.cancel()
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
        p.stdout.close()
    return "".join(out)


class Tree(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="startup-")
        # mkdtemp is 0700, so after dropping privileges the new user could not
        # even traverse into it. On the NAS the docker share is traversable by
        # everyone, so 0700 here would be testing a situation that cannot arise.
        os.chmod(self.dir, 0o755)
        self.photos = os.path.join(self.dir, "photos")
        self.raw = os.path.join(self.dir, "raw")
        self.config = os.path.join(self.dir, "config")
        for d in (self.photos, self.raw, self.config):
            os.makedirs(d)

    def tearDown(self):
        if AS_ROOT:
            subprocess.run(["chown", "-R", f"{os.getuid()}:{os.getgid()}", self.dir],
                           check=False)
        shutil.rmtree(self.dir, ignore_errors=True)

    def env(self, **over):
        return {"PM_DATA": self.config, "PORT": "0",
                "ALLOWED_ROOTS": os.pathsep.join([self.photos, self.raw]),
                **over}


class FindingTheCode(unittest.TestCase):
    def test_it_works_out_where_it_is_without_the_working_directory(self):
        """Run from /, which is what broke it on the NAS."""
        from nas import run
        self.assertTrue(os.path.isfile(os.path.join(run.code_root(), "app", "server.py")))

    def test_a_mount_one_folder_too_deep_is_named_as_such(self):
        wrong = tempfile.mkdtemp(prefix="wrong-")
        try:
            os.makedirs(os.path.join(wrong, "nas"))
            os.makedirs(os.path.join(wrong, "Photo Manager NAS", "app"))
            shutil.copy(RUN, os.path.join(wrong, "nas", "run.py"))
            done = subprocess.run([sys.executable, os.path.join(wrong, "nas", "run.py")],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(done.returncode, 1)
            self.assertIn("not where the container is looking", done.stdout)
            self.assertIn("Photo Manager NAS", done.stdout)
        finally:
            shutil.rmtree(wrong, ignore_errors=True)


class ChoosingAUser(unittest.TestCase):
    """The decision, tested directly - it is the part with the judgement in it."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="whoami-")
        self._env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.dir, ignore_errors=True)

    def wanted(self, **env):
        from nas import run
        os.environ.pop("PM_USER", None)
        os.environ.update({k: str(v) for k, v in env.items()})
        return run.wanted_user()

    def test_pm_user_is_obeyed_exactly(self):
        uid, gid, why = self.wanted(PM_USER="1027:100", ALLOWED_ROOTS=self.dir)
        self.assertEqual((uid, gid), (1027, 100))
        self.assertIn("PM_USER", why)

    def test_pm_user_root_means_stay_put(self):
        uid, _gid, why = self.wanted(PM_USER="root", ALLOWED_ROOTS=self.dir)
        self.assertIsNone(uid)
        self.assertIn("root", why)

    def test_nonsense_in_pm_user_falls_back_rather_than_crashing(self):
        """It must not raise, and must not take "someone" for a number. What it
        falls back TO depends on who owns the temp folder, which differs from
        machine to machine - so that is not what is asserted here."""
        uid, _gid, why = self.wanted(PM_USER="someone", ALLOWED_ROOTS=self.dir,
                                     PM_DATA=self.dir)
        self.assertNotIn("someone", why)
        self.assertTrue(uid is None or isinstance(uid, int))

    @unittest.skipUnless(AS_ROOT, "needs root to make a folder owned by someone else")
    def test_it_picks_the_owner_of_the_library(self):
        os.chown(self.dir, *NOBODY)
        uid, gid, why = self.wanted(ALLOWED_ROOTS=self.dir, PM_DATA=self.dir)
        self.assertEqual((uid, gid), NOBODY)
        self.assertIn(self.dir, why)

    @unittest.skipUnless(AS_ROOT, "needs root")
    def test_a_root_owned_folder_is_not_mistaken_for_a_person(self):
        """Docker invents these when a path is wrong. Running as root because of
        one would be taking the typo as an instruction."""
        empty = os.path.join(self.dir, "invented")
        os.makedirs(empty)
        os.chown(empty, 0, 0)
        os.chown(self.dir, 0, 0)
        uid, _gid, _why = self.wanted(ALLOWED_ROOTS=empty, PM_DATA=self.dir)
        self.assertIsNone(uid)

    @unittest.skipUnless(AS_ROOT, "needs root")
    def test_the_library_wins_over_a_later_folder(self):
        lib = os.path.join(self.dir, "photos")
        other = os.path.join(self.dir, "raw")
        os.makedirs(lib)
        os.makedirs(other)
        os.chown(lib, *NOBODY)
        os.chown(other, 12345, 12345)
        uid, _gid, _why = self.wanted(ALLOWED_ROOTS=os.pathsep.join([lib, other]))
        self.assertEqual(uid, NOBODY[0])


@unittest.skipUnless(AS_ROOT, "the privilege drop can only be exercised as root")
class BecomingThatUser(Tree):
    def test_it_drops_to_whoever_owns_the_photos(self):
        os.chown(self.photos, *NOBODY)
        log = start(self.env())
        self.assertIn(f"dropping to {NOBODY[0]}:{NOBODY[1]}", log)
        self.assertIn(f"uid={NOBODY[0]}", log)

    def test_the_config_folder_is_handed_over_too(self):
        """Otherwise it drops to a user that cannot write its own settings."""
        os.chown(self.photos, *NOBODY)
        start(self.env())
        self.assertEqual(os.stat(self.config).st_uid, NOBODY[0])

    def test_an_empty_root_owned_folder_is_adopted(self):
        os.chown(self.photos, *NOBODY)
        os.chown(self.raw, 0, 0)
        log = start(self.env())
        self.assertIn("handed over", log)
        self.assertEqual(os.stat(self.raw).st_uid, NOBODY[0])

    def test_but_a_folder_with_anything_in_it_is_left_alone(self):
        """Guessing at the ownership of a real tree is not its business."""
        os.chown(self.photos, *NOBODY)
        with open(os.path.join(self.raw, "something.RW2"), "w") as fh:
            fh.write("x")
        os.chown(self.raw, 0, 0)
        start(self.env())
        self.assertEqual(os.stat(self.raw).st_uid, 0)

    def test_pm_user_overrides_the_detection(self):
        os.chown(self.photos, *NOBODY)
        log = start(self.env(PM_USER="12345:100"))
        self.assertIn("dropping to 12345:100", log)

    def test_pm_user_root_stays_root_and_says_why(self):
        os.chown(self.photos, *NOBODY)
        log = start(self.env(PM_USER="root"))
        self.assertIn("uid=0", log)
        self.assertIn("owned by root", log)

    def test_nothing_owned_by_a_person_means_it_says_so_and_carries_on(self):
        """It must not refuse to start. Saying plainly that it is root, and what
        that will mean, is more use than not running at all."""
        log = start(self.env())
        self.assertIn("Running as:  root", log)
        self.assertIn("owned by root", log)
        self.assertIn("stop with Ctrl+C", log)


class WhatItReports(Tree):
    def test_it_names_a_folder_that_is_not_there(self):
        missing = os.path.join(self.dir, "nope")
        log = start(self.env(ALLOWED_ROOTS=os.pathsep.join([self.photos, missing])))
        self.assertIn("MISSING", log)
        self.assertIn(missing, log)

    def test_it_lists_every_allowed_folder_including_the_last(self):
        """A `read` loop dropped the final entry once - the third tree is exactly
        the one most likely to be wrong."""
        third = os.path.join(self.dir, "previews")
        os.makedirs(third)
        log = start(self.env(ALLOWED_ROOTS=os.pathsep.join(
            [self.photos, self.raw, third])))
        for path in (self.photos, self.raw, third):
            self.assertIn(path, log)

    def test_it_says_which_port_is_the_container_one(self):
        log = start(self.env(PORT="8080"))
        self.assertIn("INSIDE the container", log)

    def test_it_starts_and_says_where_the_settings_live(self):
        log = start(self.env())
        self.assertIn(self.config, log)
        self.assertIn("stop with Ctrl+C", log)


class InstallingPillowAndItsHeicReader(unittest.TestCase):
    """Pillow and pi-heif go into the config volume on first start. Each is
    checked on its own: a NAS that already had Pillow when HEIC support
    arrived must get pi-heif on its next start without anything else."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pillow-")
        self._was = {k: os.environ.get(k) for k in ("PM_PILLOW", "PYTHONUSERBASE")}
        os.environ.pop("PM_PILLOW", None)
        self._path = list(sys.path)

    def tearDown(self):
        for k, v in self._was.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sys.path[:] = self._path
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_it(self, missing=(), broken=()):
        from unittest import mock
        from nas import run
        real = __import__

        def importing(name, *a, **kw):
            if name in missing:
                raise ImportError(name)
            if name in broken:
                raise OSError("libheif.so.1: cannot open shared object file")
            return real(name, *a, **kw)
        with mock.patch("builtins.__import__", importing), \
                mock.patch.object(run.subprocess, "run") as pip, \
                mock.patch("builtins.print") as said:
            run.ensure_pillow(self.dir)
        installed = [c.args[0][-1] for c in pip.call_args_list]
        log = "\n".join(" ".join(map(str, c.args)) for c in said.call_args_list)
        return installed, log

    def test_only_what_is_missing_is_installed(self):
        installed, log = self.run_it(missing=("pi_heif",))
        self.assertEqual(installed, ["pi-heif"])
        self.assertIn("Pillow:      already installed", log)

    def test_both_when_neither_is_there(self):
        installed, _ = self.run_it(missing=("PIL", "pi_heif"))
        self.assertEqual(installed, ["pillow", "pi-heif"])

    def test_one_that_will_not_load_is_reported_not_reinstalled(self):
        installed, log = self.run_it(broken=("pi_heif",))
        self.assertEqual(installed, [])
        self.assertIn("will not load", log)

    def test_skip_still_means_nothing_is_installed(self):
        os.environ["PM_PILLOW"] = "skip"
        installed, _ = self.run_it(missing=("PIL", "pi_heif"))
        self.assertEqual(installed, [])



class TheComposeTemplate(unittest.TestCase):
    """Read as text: the image has no YAML parser, and the template is meant
    to be pasted into Container Manager exactly as it stands."""

    def setUp(self):
        with open(os.path.join(ROOT, "nas", "docker-compose.yml"),
                  encoding="utf-8") as fh:
            self.text = fh.read()

    def env(self, name):
        import re
        m = re.search(rf'(?m)^\s+{name}:\s*"?([^"\n#]+?)"?\s*$', self.text)
        return m.group(1).strip() if m else None

    def test_docker_exec_finds_the_pillow_the_container_installed(self):
        """`ensure_pillow` installs into PM_DATA/python, but only told its own
        process so. A scheduled `docker exec ... app.cli previews --apply` is
        a fresh process, and said it needed Pillow."""
        self.assertEqual(self.env("PYTHONUSERBASE"),
                         os.path.join(self.env("PM_DATA"), "python"))

    def test_phones_are_told_the_port_that_is_mapped(self):
        import re
        host, inside = re.search(r'- "(\d+):(\d+)"', self.text).groups()
        self.assertEqual(inside, self.env("PORT"))
        self.assertEqual(host, self.env("PM_PUBLIC_PORT"))


if __name__ == "__main__":
    unittest.main()
