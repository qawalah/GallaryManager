"""The compose file, checked against itself.

This is not testing Docker. It is testing the one mistake that has now cost real
time twice, and that nothing else can catch: a container path that exists in one
line of the file and nowhere else.

`ALLOWED_ROOTS` names folders. `volumes` mounts folders. If those two disagree,
the app starts perfectly, the page loads perfectly, and then says *"is not a
folder"* about a folder plainly visible in File Station - because it exists on
the NAS and not inside the container. Nothing in the code can notice: from in
there, a path that was never mounted and a path that was misspelt look the same.

So the file has to agree with itself, and that is checkable here, in a second,
without a NAS.

Parsed by hand rather than with PyYAML: the whole point of this app is that it
runs on a fresh Windows box and a stock python image with nothing installed, and
a test suite that needs a package is a test suite that gets skipped.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COMPOSE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "nas", "docker-compose.yml")


def lines():
    with open(COMPOSE, "r", encoding="utf-8") as fh:
        return [l.rstrip("\n") for l in fh]


def settings():
    """Every `key: value` in the file, ignoring comments and list items."""
    out = {}
    for line in lines():
        bare = line.strip()
        if not bare or bare.startswith("#") or bare.startswith("-"):
            continue
        key, sep, value = bare.partition(":")
        if not sep:
            continue
        out.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return out


def mounts():
    """(host path, container path) for every volume line."""
    out = []
    for line in lines():
        bare = line.strip()
        if not bare.startswith("- \"") or ":" not in bare:
            continue
        spec = bare[3:].rstrip('"')
        parts = spec.split(":")
        if len(parts) < 2 or not parts[0].startswith("/"):
            continue                        # a port mapping, not a volume
        if parts[-1] in ("ro", "rw"):
            parts = parts[:-1]
        out.append((parts[0], parts[1]))
    return out


class TheFileIsThere(unittest.TestCase):
    def test_it_ships_with_the_app(self):
        self.assertTrue(os.path.isfile(COMPOSE))


class ItAgreesWithItself(unittest.TestCase):
    def test_every_allowed_root_is_actually_mounted(self):
        """The bug this exists for. A root that is not mounted is a folder the
        container cannot see, and the error it produces points at the path
        rather than at the missing mount."""
        inside = [c for _host, c in mounts()]
        for root in settings()["ALLOWED_ROOTS"].split(":"):
            root = root.strip()
            if not root:
                continue
            self.assertTrue(
                any(root == m or root.startswith(m.rstrip("/") + "/") for m in inside),
                f"ALLOWED_ROOTS names {root!r}, which no volume mounts. "
                f"Mounted: {inside}")

    def test_the_photo_mount_is_at_its_own_path(self):
        """A container-only name like /photos is a second set of names to keep
        straight, and the day it drifts from ALLOWED_ROOTS or from what was
        typed into Setup, the app is wrong about a folder that exists."""
        for host, inside in mounts():
            if host.startswith("/volume1/docker/"):
                continue            # the app's own code and config, deliberately not
            self.assertEqual(host, inside,
                             f"{host} is mounted as {inside}; mount it at its own path")

    def test_the_data_folder_is_mounted_and_writable(self):
        s = settings()
        writable = [c for host, c in mounts()
                    if not any(l.strip().endswith(':ro"') for l in lines()
                               if host in l)]
        self.assertIn(s["PM_DATA"], writable)

    def test_the_code_is_mounted_read_only(self):
        """It is the one thing that must not be writable: the app writing to its
        own source is how a container quietly stops matching the folder you copy
        into it."""
        code = [l for l in lines() if "/app" in l and l.strip().startswith("-")]
        self.assertTrue(code)
        self.assertTrue(all(l.rstrip().endswith(':ro"') for l in code), code)


class NoUserLine(unittest.TestCase):
    """A fixed uid is a guess, and a wrong guess is silent - everything the app
    writes belongs to somebody else and you find out weeks later. Started as
    root it reads who owns the library and drops to them; a `user:` line takes
    that ability away, because it can no longer drop."""

    def test_there_is_no_user_line(self):
        for line in lines():
            self.assertFalse(line.strip().startswith("user:"),
                             f"{line.strip()} prevents the app dropping privileges")

    def test_and_the_file_says_why_so_nobody_adds_one_back(self):
        text = "\n".join(lines()).lower()
        self.assertIn("no `user:` line", text)


class ThePortIsPublished(unittest.TestCase):
    def test_the_container_port_matches_the_one_the_app_listens_on(self):
        s = settings()
        published = [l.strip()[3:].rstrip('"') for l in lines()
                     if l.strip().startswith("- \"") and l.strip().count(":") == 1
                     and "/" not in l]
        self.assertTrue(published, "no port mapping in the compose file")
        self.assertTrue(any(p.split(":")[1] == s["PORT"] for p in published),
                        f"published {published}, app listens on {s['PORT']}")


if __name__ == "__main__":
    unittest.main()
