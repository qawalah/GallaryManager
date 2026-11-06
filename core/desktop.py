"""Running as a program on a PC rather than as a container on the NAS.

The same server, started a different way. On the NAS it is a container: someone
else decides when it starts, the settings live on a mounted volume, and stopping
it is Container Manager's job. On a PC none of that is true, and the three
things that follow are the whole of this file.

**Where its settings go.** Beside the code is right for a folder you copied to
a spare drive and wrong for something installed: put it in Program Files and the
app cannot write next to itself, and put it in Downloads and an upgrade deletes
your settings with the old copy. On Windows they go under `%LOCALAPPDATA%`,
which is per-user, writable, and survives replacing the program.

**How you stop it.** A container has a stop button. A window-less program has
Task Manager, which is not an answer. Started this way the server offers a Quit
on its own page - and only started this way, because a Quit button on the NAS
would be a button that takes the app off the network with no way to bring it
back.

**How it starts with Windows.** A shortcut in the Startup folder. Made by the
installer, removed by the uninstaller, and nothing is written to the registry -
an app that puts itself in the registry is an app you are not sure you have
removed.

**What sits by the clock.** A program with no window still needs somewhere to
be seen and stopped from. The icon in the notification area is that place (the
Win32 half is `windows/tray.py`); what its menu says and what each entry does is
decided here, as plain data, so it can be tested without Windows.

Nothing here has been run on Windows from this sandbox. The parts that could be
tested are tested (which folder, which address, what the installer writes, what
the tray menu offers); the parts that could not are the `.bat` files and the
tray's calls into Windows itself, which are kept small on purpose.
"""

from __future__ import annotations

import json
import ntpath
import os
import socket
import subprocess
import sys

FLAG = "PM_DESKTOP"          # set by the launcher: "this was started as a program"


def as_program() -> bool:
    """Was this server started as a desktop program rather than as a service?"""
    return str(os.environ.get(FLAG, "")).strip().lower() in ("1", "yes", "true", "on")


def windows() -> bool:
    return sys.platform.startswith("win")


def data_home(env=None, code_root: str = "") -> str:
    """Where a desktop copy should keep its settings.

    `%LOCALAPPDATA%\\PhotoManager` on Windows - per-user, writable, and not
    inside the program, so replacing the program with a newer copy does not take
    your library path with it. Anywhere else, a dot-folder in the home
    directory, for the same reason. Falls back to beside the code only when
    there is no home to speak of, which is a container, which is the one place
    that is right.
    """
    env = os.environ if env is None else env
    if str(env.get("PM_DATA", "")).strip():
        return str(env["PM_DATA"]).strip()
    local = str(env.get("LOCALAPPDATA", "")).strip()
    if local:
        return os.path.join(local, "PhotoManager")
    home = str(env.get("HOME", "") or env.get("USERPROFILE", "")).strip()
    if home:
        return os.path.join(home, ".photo-manager")
    return os.path.join(code_root or os.getcwd(), "config")


def address(port: int, host: str = "127.0.0.1") -> str:
    """The page's address. 127.0.0.1 rather than "localhost" on purpose: the
    server listens on IPv4 only, and on Windows "localhost" tries IPv6 first
    and waits two seconds for it to fail - on every request (measured on a
    real PC)."""
    return f"http://{host}:{int(port)}"


def _ps(text: str) -> str:
    """A PowerShell single-quoted string. A folder called "Ali's Photos" is a
    folder someone has, and an unescaped quote in it is a broken installer."""
    return "'" + str(text).replace("'", "''") + "'"


def _shortcut(link: str, target: str, args: str, working: str, icon: str) -> str:
    """One shortcut, with `link` already a PowerShell expression."""
    lines = [
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({link})",
        f"$s.TargetPath = {_ps(target)}",
    ]
    if args:
        lines.append(f"$s.Arguments = {_ps(args)}")
    lines.append(f"$s.WorkingDirectory = {_ps(working)}")
    if icon:
        lines.append(f"$s.IconLocation = {_ps(icon)}")
    lines.append(f"$s.Description = {_ps(NAME)}")
    lines.append("$s.Save()")
    return "; ".join(lines)


def shortcut_script(where: str, name: str, target: str, args: str = "",
                    working: str = "", icon: str = "") -> str:
    """The PowerShell that makes one shortcut.

    Written out rather than shelled out to a helper so the installer is a thing
    you can read before you run it - and so this can be tested without Windows.
    """
    return _shortcut(_ps(ntpath.join(where, name + ".lnk")), target, args,
                     working or ntpath.dirname(target), icon)


# ------------------------------------------------------------- the shortcuts

NAME = "Photo Manager"
BACKGROUND = "--background"      # started with Windows: into the tray, no page

# Which shortcuts the installer makes, by the name Windows gives the folder.
# Asked of Windows rather than built from %APPDATA%, because a Desktop that
# OneDrive has moved is not where the environment says it is.
PLACES = ("Programs", "Desktop", "Startup")


def shortcuts_script(target: str, launcher: str, icon: str = "",
                     places=PLACES) -> str:
    """The PowerShell that puts Photo Manager in the Start menu, on the desktop
    and in Startup.

    The Startup one starts it with `--background`: a program that opens a
    browser window every time you log in is a program people take out of
    Startup, and then it is not running when the automation is due.
    """
    folder = ntpath.dirname(launcher)
    link = f"(Join-Path $d {_ps(NAME + '.lnk')})"
    parts = []
    for place in places:
        args = f'"{launcher}"' + (f" {BACKGROUND}" if place == "Startup" else "")
        parts.append(f"$d = [Environment]::GetFolderPath({_ps(place)}); "
                     + _shortcut(link, target, args, folder, icon)
                     + f"; Write-Host ('  ' + {link})")
    return "; ".join(parts)


def remove_shortcuts_script(places=PLACES) -> str:
    """The PowerShell that takes them away again, and touches nothing else."""
    return "; ".join(
        f"$p = Join-Path ([Environment]::GetFolderPath({_ps(place)})) "
        f"{_ps(NAME + '.lnk')}; if (Test-Path -LiteralPath $p) "
        "{ Remove-Item -LiteralPath $p -Force; Write-Host ('  removed ' + $p) }"
        for place in places)


def run_powershell(script: str, quiet: bool = True) -> bool:
    """Run it, without a console flashing up when `quiet`, and say whether it
    worked. Not quiet from the installer, whose window is where it reports.

    Handed over encoded rather than as text, because a script full of quotes
    passed through Windows' command-line rules is a script that means something
    slightly different by the time PowerShell reads it.
    """
    import base64
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        done = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-EncodedCommand", encoded],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if quiet else 0,
            timeout=60)
        return done.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def startup_link(env=None) -> str:
    """Where the Startup shortcut is. `%APPDATA%` is what Windows itself uses
    for the Startup folder; redirecting one redirects the other."""
    env = os.environ if env is None else env
    roaming = str(env.get("APPDATA", "")).strip()
    if not roaming:
        return ""
    return os.path.join(roaming, "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup", NAME + ".lnk")


def starts_with_windows(env=None, exists=os.path.exists) -> bool:
    link = startup_link(env)
    return bool(link) and exists(link)


def set_start_with_windows(on: bool, target: str, launcher: str,
                           icon: str = "") -> bool:
    """Put the Startup shortcut in place, or take it away. Nothing else."""
    if on:
        return run_powershell(shortcuts_script(target, launcher, icon,
                                               places=("Startup",)))
    return run_powershell(remove_shortcuts_script(places=("Startup",)))


# ------------------------------------------------------------ desktop settings
#
# The few things that only mean anything on a PC: whether the page opens in a
# window of its own, and whether the tray has introduced itself yet. Kept apart
# from settings.json because the NAS has no use for them, and because a file the
# NAS also reads is a file a PC preference could break there.

PREFS = "desktop.json"
DEFAULT_PREFS = {"own_window": True, "told_about_tray": False}


def prefs_path(env=None) -> str:
    return os.path.join(data_home(env), PREFS)


def prefs(env=None) -> dict:
    out = dict(DEFAULT_PREFS)
    try:
        with open(prefs_path(env), encoding="utf-8") as fh:
            saved = json.load(fh)
        if isinstance(saved, dict):
            out.update({k: bool(saved[k]) for k in DEFAULT_PREFS if k in saved})
    except (OSError, ValueError):
        pass
    return out


def save_prefs(changes: dict, env=None) -> dict:
    """Write through a temp file, so a crash halfway leaves the old file."""
    now = prefs(env)
    now.update({k: bool(v) for k, v in changes.items() if k in DEFAULT_PREFS})
    path = prefs_path(env)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(now, fh, indent=1)
        os.replace(path + ".tmp", path)
    except OSError:
        pass
    return now


# ------------------------------------------------------------- opening the page

def edge_path(env=None, exists=os.path.isfile) -> str:
    """Microsoft Edge, which every Windows 10 and 11 has, or "".

    Wanted for one thing: `--app=`, which opens the page in a plain window of
    its own, with the app's icon and no address bar. That is what makes a page
    feel like a program, and it is the same page either way.
    """
    env = os.environ if env is None else env
    for base in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        root = str(env.get(base, "")).strip()
        if not root:
            continue
        candidate = os.path.join(root, "Microsoft", "Edge", "Application",
                                 "msedge.exe")
        if exists(candidate):
            return candidate
    return ""


def open_command(url: str, own_window: bool, edge: str) -> list:
    """What to run to open the page, or [] for "the default browser"."""
    if own_window and edge:
        return [edge, f"--app={url}"]
    return []


def open_page(url: str, env=None) -> None:
    """Open the page the way the tray's setting says. Never raises: a browser
    that will not start is not a reason for the server to stop."""
    command = open_command(url, prefs(env)["own_window"], edge_path(env))
    try:
        if command:
            subprocess.Popen(command, close_fds=True)
            return
    except OSError:
        pass
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:                                      # noqa: BLE001
        pass


def running_port(env=None) -> int:
    """The port the copy already running wrote down, or 0."""
    try:
        with open(os.path.join(data_home(env), "desktop.pid"),
                  encoding="utf-8") as fh:
            lines = fh.read().split()
        return int(lines[1]) if len(lines) > 1 else 0
    except (OSError, ValueError):
        return 0


def lan_address() -> str:
    """This PC's address on the local network, for typing into a phone.

    The UDP "connect" sends nothing; it only asks the system which interface it
    would use, which is the one a phone on the same network can reach.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))
            ip = probe.getsockname()[0]
    except OSError:
        return ""
    return "" if ip.startswith(("127.", "0.")) else ip


# ------------------------------------------------------------- quitting

_ON_QUIT: list = []


def on_quit(fn) -> None:
    """Something to do on the way out - taking the tray icon away, chiefly. An
    icon left behind by a program that has gone stays by the clock until the
    mouse passes over it, and looks like the program is still running."""
    _ON_QUIT.append(fn)


def quit(code: int = 0) -> None:                            # noqa: A001
    """Stop the whole program, now. Used by the page's Quit and the tray's."""
    for fn in list(_ON_QUIT):
        try:
            fn()
        except Exception:                                  # noqa: BLE001
            pass
    try:
        os.remove(os.path.join(data_home(), "desktop.pid"))
    except OSError:
        pass
    os._exit(code)


# ------------------------------------------------------------- the tray menu

def tray_menu(state: dict) -> list:
    """What right-clicking the icon by the clock offers. `None` is a divider.

    Each entry is {"id", "label"} plus, where they apply, "checked", "default"
    (drawn bold, and what a click on the icon itself does) and "enabled".
    Built fresh every time the menu opens, from `state`, so a tick is never
    left showing a setting that has since changed.
    """
    menu: list = [{"id": "open", "label": "Open Photo Manager", "default": True}]
    if state.get("lan"):
        menu.append({"id": "copy_address",
                     "label": f"Copy the address for your phone "
                              f"({state['lan']})"})
    menu.append(None)
    menu.append({"id": "own_window", "label": "Open in its own window",
                 "checked": bool(state.get("own_window")) and bool(state.get("edge")),
                 "enabled": bool(state.get("edge"))})
    menu.append({"id": "startup", "label": "Start with Windows",
                 "checked": bool(state.get("startup"))})
    menu.append(None)
    menu.append({"id": "log", "label": "Show the log"})
    menu.append({"id": "folder", "label": "Open the settings folder"})
    menu.append(None)
    busy = int(state.get("busy") or 0)
    menu.append({"id": "quit", "label": "Quit Photo Manager"
                 + (f" ({busy} running)" if busy else "")})
    return menu


def tray_tip(port: int, busy: int = 0) -> str:
    """The words under the mouse when it rests on the icon. Windows cuts this
    at 127 characters, so it is kept short."""
    if busy:
        return f"{NAME} - {busy} task{'s' if busy != 1 else ''} running"
    return f"{NAME} - {address(port)}"


def quit_question(busy: int) -> str:
    """Asked before quitting with work in flight, and only then."""
    if not busy:
        return ""
    things = "a tool is" if busy == 1 else f"{busy} tools are"
    return (f"{things.capitalize()} still running. Quitting stops "
            f"{'it' if busy == 1 else 'them'} part way - whatever has been "
            f"moved stays moved, and the rest is not done.\n\nQuit anyway?")

