"""Make or remove Photo Manager's shortcuts. Run by Install.bat and Uninstall.bat.

    python shortcuts.py install     Start menu, desktop, and Startup
    python shortcuts.py remove      all three taken away again

In Python rather than in the .bat files because the PowerShell it runs is built
by `core/desktop.py`, where it is tested - a quote in a folder name is exactly
the kind of thing a batch file gets wrong and nobody notices until it is ALI's
folder. Nothing is written to the registry either way.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from core import desktop                                   # noqa: E402


def pythonw() -> str:
    """The window-less Python beside the one running this, which is the one
    the installer found on the PATH."""
    here = os.path.dirname(sys.executable)
    for name in ("pythonw.exe", "pythonw"):
        candidate = os.path.join(here, name)
        if os.path.exists(candidate):
            return candidate
    return sys.executable


def main(argv) -> int:
    what = (argv[:1] or [""])[0]
    if what == "install":
        script = desktop.shortcuts_script(
            pythonw(), os.path.join(HERE, "PhotoManager.pyw"),
            os.path.join(HERE, "PhotoManager.ico"))
    elif what == "remove":
        script = desktop.remove_shortcuts_script()
    else:
        print(__doc__)
        return 2
    print("Making shortcuts:" if what == "install" else "Removing shortcuts:")
    if not desktop.run_powershell(script, quiet=False):
        print("PowerShell could not do it - nothing else was changed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
