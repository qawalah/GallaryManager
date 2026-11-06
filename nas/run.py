"""Start the server as the user who owns the photos, whoever that turns out to be.

The problem this removes:

A container does not inherit the DSM account that created it. Container Manager
runs the daemon as root, so unless you pin `user:` in the compose file everything
the app writes is owned by root - and then you cannot delete a `_Culled` folder
from Windows, in a way that has nothing obviously to do with the app.

Pinning `user:` works, but only if you know the number, and finding it normally
means SSH. Worse, the right number is not the account that created the container:
it is whoever owns the PHOTOS. Those are usually different people.

So this works it out instead. Started as root, it looks at who owns the library,
makes the config folder belong to them, drops to that user, and only then runs
anything. Started as a normal user already (you pinned `user:` yourself), it
leaves well alone.

    PM_USER=1027:100   use exactly this, skip the detection
    PM_USER=root       stay as root, I know what I am doing

Everything here is stdlib and works on any Linux. It deliberately does not use
setpriv or su, which are not guaranteed to be in a slim image.
"""

from __future__ import annotations

import os
import runpy
import subprocess
import sys


def unbuffer() -> None:
    """Make every print appear immediately.

    Python block-buffers stdout when it is a pipe, and a container log IS a pipe.
    Without this the startup lines - which user it became, which folders it can
    see - sit in a buffer instead of appearing in Container Manager, so the one
    place you look when something is wrong is empty until the buffer happens to
    fill. Found because a test on a different machine hung waiting for a line
    that had already been printed.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)
        except (AttributeError, ValueError):
            pass


def code_root() -> str:
    """The folder holding app/ and core/, worked out from this file's own path.

    Not from the working directory: the container runtime is supposed to set that
    and does not always, and when it is wrong the failure is "No module named
    app.server", which reads like the app is broken rather than like a mount is
    off by one folder.
    """
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def roots() -> list[str]:
    return [p for p in os.environ.get("ALLOWED_ROOTS", "").split(os.pathsep) if p]


def data_folder() -> str:
    return os.environ.get("PM_DATA") or os.path.join(code_root(), "config")


def owner_of(path: str):
    try:
        st = os.stat(path)
        return st.st_uid, st.st_gid
    except OSError:
        return None


def wanted_user():
    """Who to run as, and why. (uid, gid, reason) or (None, None, reason)."""
    asked = (os.environ.get("PM_USER") or "").strip()
    if asked.lower() == "root":
        return None, None, "PM_USER=root, so staying as root"
    if asked:
        try:
            uid, _, gid = asked.partition(":")
            return int(uid), int(gid or 0), f"PM_USER={asked}"
        except ValueError:
            print(f"  PM_USER={asked!r} is not uid:gid - ignoring it")

    # the library first: it is the folder that certainly exists and certainly
    # belongs to a person. A RAW or previews tree may have been conjured up empty
    # by Docker when the path was wrong, and those come out owned by root.
    for path in roots() + [data_folder()]:
        got = owner_of(path)
        if got and got[0] != 0:
            return got[0], got[1], f"it owns {path}"
    return None, None, "nothing it can reach is owned by a normal user"


def give_away(path: str, uid: int, gid: int) -> None:
    """Hand a folder and its contents to that user. Best effort, never fatal."""
    try:
        os.chown(path, uid, gid)
    except OSError:
        return
    for here, dirs, names in os.walk(path):
        for name in dirs + names:
            try:
                os.chown(os.path.join(here, name), uid, gid)
            except OSError:
                pass


def adopt_empty_roots(uid: int, gid: int) -> None:
    """Hand over any allowed root that is empty and owned by root.

    Docker creates a bind-mount source that does not exist, silently, as an empty
    root-owned folder. That is how a typo in a path becomes "the RAW tree is not
    writable" later. Empty and root-owned is unambiguous - nothing of yours is in
    it - so it is safe to hand over. A folder with anything in it is left exactly
    as it is; guessing at the ownership of a real photo tree is not this program's
    business.
    """
    for path in roots():
        try:
            if not os.path.isdir(path) or os.listdir(path):
                continue
            if os.stat(path).st_uid != 0:
                continue
            os.chown(path, uid, gid)
            print(f"             {path} was empty and owned by root - handed over")
        except OSError:
            pass


def am_root() -> bool:
    """True only where the question means anything. Windows has no getuid."""
    return hasattr(os, "getuid") and os.getuid() == 0


def whoami() -> str:
    if not hasattr(os, "getuid"):
        return "this account"          # Windows: there is nothing to drop to
    return f"uid={os.getuid()} gid={os.getgid()}"


def become(uid: int, gid: int) -> None:
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)


# What the config volume's own Python folder is given on first start: Pillow
# for every picture this app draws, and pi-heif so Pillow can open the HEIC an
# iPhone saves. (import name, pip name, what it is called here, and what
# still works without it)
COMPONENTS = (
    ("PIL", "pillow", "Pillow", "Everything except 'Make previews' still works."),
    ("pi_heif", "pi-heif", "HEIC reader", "HEIC dates and places are still read; "
                                          "only their thumbnails need it."),
)


def ensure_pillow(data: str) -> None:
    """Pillow and its HEIC reader into the config volume, once, as whoever we now are.

    Installed here rather than into the image so that deploying stays "copy the
    folder, restart" with nothing to build. Each is checked on its own, so a NAS
    that had Pillow before HEIC support arrived gets pi-heif on its next start
    without reinstalling Pillow. Neither is needed for the app to run, so a
    failure is reported and not fatal - a NAS on an ARM chip nobody built
    pi-heif for is the expected case of that.
    """
    if (os.environ.get("PM_PILLOW") or "").strip().lower() == "skip":
        return                          # the tests, which must not hit the network
    base = os.path.join(data, "python")
    os.environ["PYTHONUSERBASE"] = base
    sys.path[:0] = [p for p in _user_site(base) if os.path.isdir(p)]
    for module, name, called, without in COMPONENTS:
        label = f"{called + ':':<13}"
        try:
            __import__(module)
            print(f"{label}already installed")
            continue
        except ImportError:
            pass
        except Exception as exc:                    # noqa: BLE001
            # There, and broken - a system library it needs is missing.
            # Installing it again would not change that.
            print(f"{label}installed, but will not load ({exc}).")
            print(f"{'':13}{without}")
            continue
        print(f"{label}installing once into {base} ...")
        try:
            os.makedirs(base, exist_ok=True)
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--user", "--no-cache-dir",
                 "--disable-pip-version-check", "--quiet", name],
                check=True, env={**os.environ, "PYTHONUSERBASE": base,
                                 "PIP_ROOT_USER_ACTION": "ignore"})
            sys.path[:0] = [p for p in _user_site(base)
                            if os.path.isdir(p) and p not in sys.path]
            print(f"{label}done")
        except Exception as exc:                    # noqa: BLE001
            print(f"{label}COULD NOT INSTALL ({exc}).")
            print(f"{'':13}{without}")


def _user_site(base: str) -> list[str]:
    v = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return [os.path.join(base, "lib", v, "site-packages")]


def report() -> None:
    print(f"Running as:  {whoami()}")
    if not roots():
        print("Folders:     no restriction set (ALLOWED_ROOTS is empty)")
        return
    print("Folders:")
    for path in roots():
        if not os.path.isdir(path):
            print(f"   {'MISSING':<34} {path}")
            continue
        got = owner_of(path) or ("?", "?")
        state = "writable" if os.access(path, os.W_OK) else "NOT WRITABLE"
        print(f"   {f'owned by {got[0]}:{got[1]}, {state}':<34} {path}")
    if any(os.path.isdir(p) and not os.access(p, os.W_OK) for p in roots()):
        print("   A folder marked NOT WRITABLE is usually one Docker invented,")
        print("   empty and owned by root, because the path in the compose file")
        print("   did not exist. Check that path before running anything.")


def main() -> int:
    unbuffer()
    root = code_root()
    sys.path.insert(0, root)
    os.chdir(root)

    if not os.path.isfile(os.path.join(root, "app", "server.py")):
        print("\n" + "=" * 58)
        print(" The app is not where the container is looking for it.\n")
        print(f" Looking in:  {root}")
        print(f" Expected:    {os.path.join(root, 'app', 'server.py')}\n")
        print(" What is actually in there:")
        try:
            for name in sorted(os.listdir(root)):
                print(f"     {name}")
        except OSError as exc:
            print(f"     (cannot even list it: {exc})")
        print("\n The folder you mounted as /app must contain app/ core/ nas/")
        print(" directly - not a folder that contains them.")
        print("=" * 58)
        return 1

    data = data_folder()

    if am_root():
        uid, gid, why = wanted_user()
        if uid is None:
            print(f"Running as:  root - {why}")
            print("             Anything written will be owned by root, which you")
            print("             will notice when you try to delete it over SMB.")
        else:
            os.makedirs(data, exist_ok=True)
            give_away(data, uid, gid)
            adopt_empty_roots(uid, gid)
            print(f"User:        dropping to {uid}:{gid} - {why}")
            become(uid, gid)

    try:
        os.makedirs(data, exist_ok=True)
    except OSError as exc:
        print("\n" + "=" * 58)
        print(f" Cannot write to {data} ({exc.strerror or exc}).")
        print(f" Running as {whoami()}.\n")
        print(" That is the /config volume. Either the path does not exist on the")
        print(" NAS, or that user cannot reach it - check the folders ABOVE it")
        print(" too, not just the folder itself. PM_USER=root skips the drop if")
        print(" you would rather sort the permissions out afterwards.")
        print("=" * 58)
        return 1

    print(f"Code:        {root}")
    ensure_pillow(data)
    report()
    print("")

    runpy.run_module("app.server", run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
