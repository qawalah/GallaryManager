"""Second opinion: what does an independent library make of a file we wrote?

Used by the tests. Kept as a separate script rather than an import so the test
suite still runs on a machine without Pillow - those checks skip instead of
failing, and everything else carries on.

It decodes the picture as well as reading the tags, because a file whose metadata
parses but whose pixels no longer decode is exactly the failure worth catching.
"""

import json
import os
import sys

from PIL import Image


def dms(parts, ref):
    d, m, s = (float(x) for x in parts)
    v = d + m / 60 + s / 3600
    return -v if str(ref).strip().upper().startswith(("S", "W")) else v


def look(path, compare_with=None):
    try:
        im = Image.open(path)
        ex = im.getexif()
        gps = ex.get_ifd(0x8825)
        sub = ex.get_ifd(0x8769)
        im.load()                                # decode - proves it is not corrupt
        out = {
            "ok": True,
            "lat": round(dms(gps[2], gps.get(1)), 6) if 2 in gps else None,
            "lon": round(dms(gps[4], gps.get(3)), 6) if 4 in gps else None,
            "altitude": (float(gps[6]) * (-1 if gps.get(5) == 1 else 1)) if 6 in gps else None,
            "model": ex.get(0x0110),
            "taken": sub.get(0x9003),
            "fnumber": float(sub[0x829D]) if 0x829D in sub else None,
            "iso": sub.get(0x8827),
            "rating": ex.get(0x4746),
            "bytes": os.path.getsize(path),
        }
        if compare_with:
            a = Image.open(compare_with).convert("RGB").tobytes()
            b = Image.open(path).convert("RGB").tobytes()
            out["pixels_match"] = a == b
        else:
            # No claim can be made without something to compare against, and a
            # cheerful True here would make the test that reads it unable to fail.
            out["pixels_match"] = None
        return out
    except Exception as exc:                     # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def main(argv):
    if not argv:
        print("usage: verify_with_pillow.py FILE [FILE ...] [--compare ORIGINAL]",
              file=sys.stderr)
        return 2
    compare = None
    if "--compare" in argv:
        i = argv.index("--compare")
        compare = argv[i + 1] if i + 1 < len(argv) else None
        argv = argv[:i] + argv[i + 2:]
    print(json.dumps({p: look(p, compare) for p in argv}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
