"""Download the Pillow and pi-heif that ship with the Windows program.

    python tools/fetch_wheels.py                # the pinned versions below
    python tools/fetch_wheels.py 12.4.0         # move Pillow to a newer one
    python tools/fetch_wheels.py 12.4.0 1.5.0   # and pi-heif too

pi-heif is what lets Pillow open a HEIC, the format every iPhone saves in. It is
the decode-only build of pillow-heif: a couple of megabytes rather than seven,
and LGPL libraries only, where pillow-heif also carries a GPL encoder this app
has no use for. See core/heif.py.

Shipped rather than fetched by Install.bat because an installer that needs the
internet half way through is an installer that stalls on a slow line with
nothing on screen - which is what happened on the first real PC. The wheels are
Windows 64-bit builds for every Python the README accepts; a Python outside
that list still works, Install.bat falls back to downloading.

It also writes windows/wheels/requirements.txt with each file's SHA-256, and
Install.bat installs with --require-hashes: a wheel that has been swapped or
damaged since it was downloaded is refused rather than installed.

Run it only to change the version. It needs the internet and pip; the files it
writes are committed like the icons, and like them are not edited by hand.
"""

from __future__ import annotations

import glob
import hashlib
import os
import subprocess
import sys

VERSION = "12.3.0"
HEIF_VERSION = "1.4.0"
PYTHONS = ("3.11", "3.12", "3.13", "3.14")
PLATFORM = "win_amd64"

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "windows",
                   "wheels")


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv) -> int:
    wanted = (("pillow", "pillow", argv[0] if argv else VERSION),
              ("pi-heif", "pi_heif", argv[1] if len(argv) > 1 else HEIF_VERSION))
    out = os.path.abspath(OUT)
    os.makedirs(out, exist_ok=True)
    lines = [f"# {', '.join(f'{name} {v}' for name, _, v in wanted)} for Windows "
             f"64-bit, Python {', '.join(PYTHONS)}. Written by tools/fetch_wheels.py."]
    every = []
    for name, stem, version in wanted:
        for old in glob.glob(os.path.join(out, f"{stem}-*.whl")):
            os.remove(old)
        for python in PYTHONS:
            subprocess.run(
                [sys.executable, "-m", "pip", "download", f"{name}=={version}",
                 "--only-binary=:all:", "--no-deps", "--platform", PLATFORM,
                 "--python-version", python, "--dest", out, "--quiet"],
                check=True)
        wheels = sorted(glob.glob(os.path.join(out, f"{stem}-*.whl")))
        every += wheels
        lines.append(f"{name}=={version} \\")
        lines += [f"    --hash=sha256:{sha256(w)}" + (" \\" if i < len(wheels) - 1 else "")
                  for i, w in enumerate(wheels)]
    with open(os.path.join(out, "requirements.txt"), "w", encoding="utf-8",
              newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    for w in every:
        print(f"  {os.path.basename(w)}  {os.path.getsize(w):,} bytes")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
