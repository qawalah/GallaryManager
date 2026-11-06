"""Start Photo Manager on Windows as a program rather than as a command.

Double-clicked, or started by the shortcut the installer puts in Startup. The
`.pyw` extension is the whole trick: Windows runs it with `pythonw.exe`, which
has no console window, so there is no black box sitting in the taskbar for as
long as the app is running.

What it does, in order:

1. Steps aside if it is already running. A second double-click opens the page
   of the copy that is running instead of starting another one on the next
   port - two copies would both run the automation, on the same photographs.
2. Puts the settings somewhere sensible - `%LOCALAPPDATA%\\PhotoManager` - so
   replacing the program with a newer copy does not take your library path with
   it, and so it works when the program lives somewhere you cannot write to.
3. Marks itself as a desktop copy, which is what makes **Quit** appear on the
   app's own Setup page.
4. Picks a free port if the usual one is taken, so a second program on 8080
   gets a different port rather than a stack trace.
5. Starts the server on a thread of its own, and puts an icon by the clock on
   this one. Right-click it for the quick settings and **Quit**; click it to
   open the page. That icon is how a program with no window is found again,
   and stopped, without Task Manager.
6. Opens the page once the server is answering - unless it was started with
   Windows (`--background`), when it goes quietly into the tray. A browser
   window on every login is how a program gets taken out of Startup.

Everything it writes goes to `%LOCALAPPDATA%\\PhotoManager\\desktop.log`,
because a program with no console that fails has nowhere else to say so, and
"it does not start" with no log is the worst bug to be handed.

Run on anything but Windows it is the same server with no tray, which is how
the parts that are not Windows' own were tested.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import traceback

# core/heif.py loads the HEIC reader by name at run time, which a PyInstaller
# build (DevStore) cannot see; this import makes it bundle pi_heif. Harmless
# when it is not installed.
try:
    import pi_heif  # noqa: F401
except ImportError:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(HERE)
sys.path.insert(0, CODE)

ICON = os.path.join(HERE, "PhotoManager.ico")


def free_port(first: int) -> int:
    """`first` if it is free, else the next one that is, up to ten along.

    Tried the way the server will use it - every address, not only this PC's
    own - and on Windows without SO_REUSEADDR, which there means "let me share
    a port someone else has" rather than "let me reuse one that just closed".
    With it, every port looks free on Windows, and two programs answer on one.
    """
    for port in range(first, first + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if os.name != "nt":
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("", port))
                return port
            except OSError:
                continue
    return first


def answering(port: int, seconds: float = 30.0) -> bool:
    """Wait until the server takes connections, so the page never opens onto
    "can't reach this page" while it is still starting."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def main(argv=None) -> int:
    from core import desktop

    argv = sys.argv[1:] if argv is None else argv
    quietly = desktop.BACKGROUND in argv

    where = desktop.data_home()
    os.makedirs(where, exist_ok=True)
    os.environ["PM_DATA"] = where
    os.environ[desktop.FLAG] = "1"

    log = os.path.join(where, "desktop.log")
    try:
        out = open(log, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = out
    except OSError:
        pass

    on_windows = desktop.windows()
    if on_windows:
        import tray
        if tray.already_running():
            port = desktop.running_port() or int(os.environ.get("PORT", "8080"))
            print(f"\n--- already running on port {port}"
                  + ("" if quietly else "; opening that one"))
            if not quietly:
                desktop.open_page(desktop.address(port))
            return 0

    port = free_port(int(os.environ.get("PORT", "8080")))
    os.environ["PORT"] = str(port)

    # Its own process id, so Stop.bat can end THIS program rather than every
    # window-less Python on the account - which would take out whatever else
    # you happen to be running. The port, so a second start can find it.
    try:
        with open(os.path.join(where, "desktop.pid"), "w", encoding="utf-8") as fh:
            fh.write(f"{os.getpid()}\n{port}\n")
    except OSError:
        pass

    from app import server

    print(f"\n--- starting on port {port}, settings in {where}")
    if not on_windows:
        if not quietly:
            desktop.open_page(desktop.address(port))
        server.serve(port)
        return 0

    def serve() -> None:
        try:
            server.serve(port)
        except BaseException:                              # noqa: BLE001
            print("\n--- the server stopped with an error")
            traceback.print_exc()
            tray.message("Photo Manager stopped with an error. What went "
                         f"wrong is at the end of\n\n{log}", error=True)
            desktop.quit(1)

    threading.Thread(target=serve, name="server", daemon=True).start()
    shown: list = []
    try:
        run_tray(tray, desktop, server, port, log, where, quietly, shown)
    except Exception:                                      # noqa: BLE001
        # No icon is a nuisance; no app would be a failure. Carry on serving,
        # with the Quit in the page's top bar as the way out.
        print("\n--- the icon by the clock could not be shown; running without it")
        traceback.print_exc()
        if not shown and not quietly and answering(port):
            desktop.open_page(desktop.address(port))
        threading.Event().wait()
    desktop.quit(0)
    return 0


def run_tray(tray, desktop, server, port: int, log: str, where: str,
             quietly: bool, shown: list) -> None:
    """The icon by the clock, until Quit. Runs on the main thread. `shown` is
    given a True once the icon is up and the page is being opened."""
    url = desktop.address(port)
    edge = desktop.edge_path()

    def state() -> dict:
        prefs = desktop.prefs()
        return {"lan": desktop.lan_address(), "edge": bool(edge),
                "own_window": prefs["own_window"],
                "startup": desktop.starts_with_windows(),
                "busy": server.work_in_flight()}

    def picked(what: str) -> None:
        if what == "open":
            desktop.open_page(url)
        elif what == "copy_address":
            lan = desktop.lan_address()
            phone = desktop.address(port, lan) if lan else ""
            if phone and copy_text(phone):
                icon.notify("Address copied",
                            f"{phone} - paste it into the browser on your "
                            f"phone. Both need to be on the same network.")
        elif what == "own_window":
            desktop.save_prefs({"own_window": not desktop.prefs()["own_window"]})
        elif what == "startup":
            want = not desktop.starts_with_windows()
            if not desktop.set_start_with_windows(
                    want, sys.executable, os.path.abspath(__file__), ICON):
                tray.message("Windows would not let Photo Manager change its "
                             "Startup shortcut. Install.bat makes it, and "
                             "Uninstall.bat takes it away.", error=True)
        elif what == "log":
            os.startfile(log)                              # noqa: S606
        elif what == "folder":
            os.startfile(where)                            # noqa: S606
        elif what == "quit":
            ask = desktop.quit_question(server.work_in_flight())
            if ask and not tray.message(ask, ask=True):
                return
            icon.close()

    def ready(_icon) -> None:
        shown.append(True)
        desktop.on_quit(_icon.remove)
        prefs = desktop.prefs()
        if not prefs["told_about_tray"]:
            _icon.notify("Photo Manager is running",
                         "It keeps going in the background, here by the "
                         "clock. Right-click this icon for settings, or to "
                         "quit.")
            desktop.save_prefs({"told_about_tray": True})

        def open_when_up() -> None:
            if answering(port) and not quietly:
                desktop.open_page(url)
        threading.Thread(target=open_when_up, daemon=True).start()

    icon = tray.Tray(ICON, lambda: desktop.tray_menu(state()), picked,
                     tip=lambda: desktop.tray_tip(port, server.work_in_flight()))
    icon.run(ready)


def copy_text(text: str) -> bool:
    """Onto the clipboard, through Windows' own `clip`. An address is plain
    ASCII, which is the one thing clip.exe reads without a fuss."""
    import subprocess
    try:
        subprocess.run(["clip"], input=text.encode("ascii", "replace"),
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                       timeout=10, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:                                  # noqa: BLE001
        # A window-less program that dies silently is a program nobody can fix.
        try:
            from core import desktop
            where = desktop.data_home()
            os.makedirs(where, exist_ok=True)
            with open(os.path.join(where, "desktop.log"), "a",
                      encoding="utf-8") as fh:
                fh.write("\n--- it stopped with an error\n")
                traceback.print_exc(file=fh)
        except Exception:                                  # noqa: BLE001
            pass
        raise
