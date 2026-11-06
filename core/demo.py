"""A sample library, so the app can be learned without risking real photographs.

Everything in this app is destructive in the sense that matters: it moves
somebody's photographs. That makes it a bad thing to learn by trying, and the
guide can only describe - so the first run of Sort into folders is on four
hundred real files, with the person reading the plan hoping they have understood
what "the pattern" does. Of course they press Go ahead anyway.

So the app can build its own library to practise on. Not a few blank files: a
library with the faults a real one has, because a feature with nothing to find
teaches nothing.

    an unsorted heap            with years and shoots mixed together
    RAWs lying beside JPEGs     some of them, not all - that is the realistic case
    a bracketed set             three frames, one second, EV -1 0 +1
    two pairs of duplicates     identical pixels, different names
    two blurry frames           for the blur check to find
    a camera whose clock is wrong   two hours fast, with GPS to prove it
    one photograph with no EXIF at all
    two clips                   so Separate video has something to move
    an already-tidy tree        with stars and a matching RAW tree

The EXIF is REAL - written with Pillow, which is not the code under test here -
so every feature that reads a photograph reads the same thing it would read from
a camera: capture time, make, model, lens, ISO, aperture, shutter, focal length,
stars, and a position for the ones that have one.

**The negatives are JPEG bytes under a .RW2 or .ARW name.** No library here can
write a real RAW file, and the realistic half is what matters: this app cannot
read EXIF out of a RW2 either, so a demo negative behaves exactly like a real
one - it is matched to its JPEG by name and position, not by what is inside it -
while still drawing a thumbnail rather than a broken image.

**It will only remove a folder it made.** `MARK` is written at the top when the
library is built and checked before anything is deleted, so "Remove the sample
library" pointed at the wrong folder does nothing at all.
"""

from __future__ import annotations

import os
import struct
import time

# Written at the top of a sample library. Checked before removal - a folder
# without it is somebody's own, whatever the box says.
MARK = ".photo-manager-sample"

INBOX = "Inbox"
LIBRARY = "Photos"
RAWTREE = "Photos Raw"


# --------------------------------------------------------------------- the shots
#
# One row is one photograph. Written out rather than generated from a loop so
# that the awkward cases are visible as awkward cases - a reader can see that
# there are exactly three bracketed frames and exactly two wrong clocks.
#
# (path, when, camera, lens, iso, f, shutter-denominator, focal,
#  {extras})
GH4 = ("Panasonic", "DMC-GH4", "LUMIX G VARIO 12-35mm F2.8")
A7C = ("Sony", "ILCE-7C", "FE 24-105mm F4 G OSS")
A7P = ("Sony", "ILCE-7C", "FE 55mm F1.8 ZA")
PHONE = ("Samsung", "SM-G991B", "")

# A corniche, a desert, and a courtyard in Spain. Real coordinates, so the map
# and the place lookup have something true to say.
DOHA = (25.3089, 51.5310)
DESERT = (24.6300, 51.1500)
SPAIN = (37.1760, -3.5881)

SHOTS: list[tuple] = [
    # ---- the heap: a card copied off in one go, three shoots deep
    (f"{INBOX}/P1010431.JPG", "2024:11:16 17:42:08", GH4, 200, 5.6, 400, 25, {"raw": ".RW2"}),
    (f"{INBOX}/P1010432.JPG", "2024:11:16 17:43:55", GH4, 200, 5.6, 320, 25, {"raw": ".RW2"}),
    (f"{INBOX}/P1010433.JPG", "2024:11:16 17:51:02", GH4, 400, 4.0, 160, 35, {"raw": ".RW2"}),
    (f"{INBOX}/P1010434.JPG", "2024:11:16 18:02:17", GH4, 800, 2.8, 60, 35, {}),
    (f"{INBOX}/P1010435.JPG", "2024:11:16 18:04:40", GH4, 1600, 2.8, 30, 12, {"blur": 2.4}),
    (f"{INBOX}/P1010436.JPG", "2024:11:16 18:09:12", GH4, 1600, 2.8, 25, 12, {}),
    (f"{INBOX}/P1010437.JPG", "2024:11:16 18:15:33", GH4, 3200, 2.8, 15, 12, {"blur": 3.1}),
    (f"{INBOX}/P1010438.JPG", "2024:11:16 18:22:01", GH4, 3200, 2.8, 10, 12, {}),
    # ---- a second trip, nine months later, same card
    (f"{INBOX}/DSC01184.JPG", "2025:03:02 07:12:44", A7C, 100, 8.0, 500, 24,
     {"raw": ".ARW", "gps": DESERT}),
    (f"{INBOX}/DSC01185.JPG", "2025:03:02 07:14:09", A7C, 100, 8.0, 640, 35,
     {"raw": ".ARW", "gps": DESERT}),
    (f"{INBOX}/DSC01186.JPG", "2025:03:02 07:31:50", A7C, 125, 5.6, 800, 105, {}),
    (f"{INBOX}/DSC01187.JPG", "2025:03:02 09:48:30", A7P, 100, 1.8, 2000, 55,
     {"stars": 4}),
    (f"{INBOX}/DSC01188.JPG", "2025:03:02 09:49:02", A7P, 100, 1.8, 2000, 55,
     {"stars": 2}),
    (f"{INBOX}/DSC01189.JPG", "2025:03:02 09:52:18", A7P, 160, 2.8, 1600, 55, {}),
    # ---- three frames, one second, one stop apart: a bracket
    (f"{INBOX}/DSC01190.JPG", "2025:03:02 16:20:11", A7C, 100, 11.0, 500, 24,
     {"ev": -1, "subsec": "10", "mode": 2}),
    (f"{INBOX}/DSC01191.JPG", "2025:03:02 16:20:11", A7C, 100, 11.0, 250, 24,
     {"ev": 0, "subsec": "45", "mode": 2}),
    (f"{INBOX}/DSC01192.JPG", "2025:03:02 16:20:12", A7C, 100, 11.0, 125, 24,
     {"ev": 1, "subsec": "10", "mode": 2}),
    # ---- the same photograph twice, under two names, twice over
    (f"{INBOX}/DSC01193.JPG", "2025:03:02 17:02:00", A7C, 200, 4.0, 320, 70,
     {"pixels": "twin-a"}),
    (f"{INBOX}/DSC01193 (1).JPG", "2025:03:02 17:02:00", A7C, 200, 4.0, 320, 70,
     {"pixels": "twin-a"}),
    (f"{INBOX}/DSC01194.JPG", "2025:03:02 17:04:21", A7C, 200, 4.0, 400, 70,
     {"pixels": "twin-b"}),
    (f"{INBOX}/copy of DSC01194.JPG", "2025:03:02 17:04:21", A7C, 200, 4.0, 400, 70,
     {"pixels": "twin-b"}),
    # ---- the phone, two hours fast, and carrying a position that proves it
    (f"{INBOX}/20250302_194500.jpg", "2025:03:02 19:45:00", PHONE, 50, 1.8, 120, 26,
     {"gps": DESERT, "gpstime": (15, 45, 0.0), "gpsdate": "2025:03:02"}),
    (f"{INBOX}/20250302_195130.jpg", "2025:03:02 19:51:30", PHONE, 50, 1.8, 120, 26,
     {"gps": DESERT, "gpstime": (15, 51, 30.0), "gpsdate": "2025:03:02"}),
    # ---- and one that says nothing about itself at all
    (f"{INBOX}/scan-0014.jpg", "", GH4, 0, 0, 0, 0, {"no_exif": True}),
    # ---- an already-tidy corner, so the Library has something to chart
    (f"{LIBRARY}/2023/Spain/Alhambra-01.JPG", "2023:05:18 11:04:22", GH4, 200, 7.1, 500, 12,
     {"gps": SPAIN, "stars": 5, "raw": ".RW2"}),
    (f"{LIBRARY}/2023/Spain/Alhambra-02.JPG", "2023:05:18 11:19:40", GH4, 200, 7.1, 400, 25,
     {"gps": SPAIN, "stars": 3, "raw": ".RW2"}),
    (f"{LIBRARY}/2023/Spain/Alhambra-03.JPG", "2023:05:18 12:40:05", GH4, 400, 4.0, 250, 35,
     {"gps": SPAIN, "raw": ".RW2"}),
    (f"{LIBRARY}/2023/Spain/Granada-01.JPG", "2023:05:19 20:12:33", GH4, 1600, 2.8, 50, 12,
     {"gps": SPAIN, "stars": 4}),
    (f"{LIBRARY}/2023/Spain/Granada-02.JPG", "2023:05:19 20:30:18", GH4, 3200, 2.8, 30, 12, {}),
    (f"{LIBRARY}/2024/Doha Corniche/P1010388.JPG", "2024:11:09 16:50:11", GH4,
     200, 8.0, 500, 25, {"gps": DOHA, "stars": 4}),
    (f"{LIBRARY}/2024/Doha Corniche/P1010389.JPG", "2024:11:09 17:02:44", GH4,
     200, 8.0, 400, 25, {"gps": DOHA}),
    (f"{LIBRARY}/2024/Doha Corniche/P1010390.JPG", "2024:11:09 17:30:52", GH4,
     800, 4.0, 125, 35, {"gps": DOHA, "stars": 2}),
]

# The clips. Separate video has nothing to do without them, and a clip is not a
# picture: it gets a real MP4 header with a real creation time in it.
CLIPS: list[tuple] = [
    (f"{INBOX}/P1010439.MP4", "2024:11:16 18:30:00"),
    (f"{INBOX}/DSC01195.MP4", "2025:03:02 17:20:00"),
]


# --------------------------------------------------------------------- counting

def recipe() -> dict:
    """What a sample library consists of, without building one.

    Separate from `build` so that a plan can say exactly what it would write -
    this app's whole promise - without writing anything.
    """
    raws = [s for s in SHOTS if s[7].get("raw")]
    return {
        "pictures": len(SHOTS),
        "negatives": len(raws),
        "clips": len(CLIPS),
        "files": len(SHOTS) + len(raws) + len(CLIPS) + 1,     # + the marker
        "folders": sorted({os.path.dirname(s[0]) for s in SHOTS}
                          | {os.path.dirname(c[0]) for c in CLIPS}
                          | {_raw_home(s) for s in raws}),
        "notes": [
            f"{len([s for s in SHOTS if s[0].startswith(INBOX)])} photos in "
            f"an unsorted heap, from three shoots and two years",
            f"{len(raws)} RAW files, some beside their JPEG and some in a "
            f"mirrored RAW tree",
            "a bracketed set of three, two pairs of duplicates, two blurry "
            "frames, one photo with no EXIF",
            "a phone whose clock is two hours fast, with a position that "
            "proves it",
        ],
    }


def _raw_home(shot) -> str:
    """Where a negative goes: beside its JPEG in the heap, mirrored in the tree.

    Both cases are worth having. The heap is what a card looks like when it is
    copied off; the tree is what the library looks like afterwards, and
    Re-mirror is only interesting when there is one.
    """
    folder = os.path.dirname(shot[0])
    if folder.startswith(LIBRARY):
        return RAWTREE + folder[len(LIBRARY):]
    return folder


# ------------------------------------------------------------------- the picture

def _pixels(seed: str, blur: float = 0.0):
    """A small, distinct picture with its own name written on it.

    Distinct matters more than pretty: a duplicate check on forty identical
    grey squares finds forty duplicates and teaches the opposite of the truth.
    Two of these DO share pixels, on purpose, and they are the only two.
    """
    from PIL import Image, ImageDraw, ImageFilter
    h = sum((i + 1) * ord(c) for i, c in enumerate(seed)) % 3600
    im = Image.new("RGB", (320, 240))
    px = im.load()
    for y in range(240):
        for x in range(320):
            px[x, y] = ((h + x * 3 // 2) % 256,
                        (h * 3 + y * 2) % 256,
                        (h * 7 + (x + y)) % 256)
    draw = ImageDraw.Draw(im)
    draw.rectangle((0, 196, 320, 240), fill=(16, 16, 20))
    draw.text((10, 206), f"SAMPLE  {seed[:30]}", fill=(235, 235, 240))
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    return im


def _exif(shot):
    """Real EXIF, written by Pillow - not by the code that will read it back."""
    from PIL import Image
    from PIL.TiffImagePlugin import IFDRational as Rat
    _path, when, cam, iso, fnum, shutter, focal, extra = shot
    make, model, lens = cam
    ex = Image.Exif()
    ex[0x010F], ex[0x0110] = make, model
    ex[0x0132] = when
    if extra.get("stars"):
        ex[0x4746] = int(extra["stars"])
    sub = ex.get_ifd(0x8769)
    sub[0x9003] = when
    if lens:
        sub[0xA434] = lens
    if extra.get("subsec"):
        sub[0x9291] = extra["subsec"]
    if "ev" in extra:
        sub[0x9204] = Rat(int(round(extra["ev"] * 100)), 100)
    if "mode" in extra:
        sub[0xA402] = extra["mode"]
    sub[0x829D] = Rat(int(fnum * 10), 10)
    sub[0x8827] = int(iso)
    sub[0x829A] = Rat(1, int(shutter))
    sub[0x920A] = Rat(int(focal), 1)
    if extra.get("gps"):
        lat, lon = extra["gps"]
        g = ex.get_ifd(0x8825)
        g[0x0001] = "N" if lat >= 0 else "S"
        g[0x0003] = "E" if lon >= 0 else "W"

        def parts(v):
            v = abs(v)
            d = int(v)
            m = int((v - d) * 60)
            sec = round(((v - d) * 60 - m) * 60, 4)
            return (Rat(d, 1), Rat(m, 1), Rat(int(sec * 10000), 10000))

        g[0x0002], g[0x0004] = parts(lat), parts(lon)
        if extra.get("gpsdate"):
            g[0x001D] = extra["gpsdate"]
        if extra.get("gpstime"):
            g[0x0007] = tuple(Rat(int(x * 100), 100) for x in extra["gpstime"])
    return ex


# ---------------------------------------------------------------------- the clip

# A REAL two-second clip, 7 KB, as bytes.
#
# It used to be the smallest thing that could still be called an MP4: a `ftyp`
# and a `moov/mvhd` carrying a creation time, with no picture in it at all.
# That was right while the only features that touched clips were moving them
# about - and wrong the moment the viewer could PLAY one, because the sample
# library's whole job is to be a place to try things, and a clip that no player
# can decode teaches that the player is broken.
#
# So: a genuine H.264 clip, small enough to paste into a source file, with its
# recorded time rewritten per clip. Everything that read the time out of these
# still reads it out of these - the header is laid out exactly as it was.
_CLIP = (
    "AAAAIGZ0eXBpc29tAAACAGlzb21pc28yYXZjMW1wNDEAAAPxbW9vdgAAAGxtdmhkAAAAAAAA"
    "AAAAAAAAAAAD6AAAB9AAAQAAAQAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAA"
    "AAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgAAAxt0cmFrAAAAXHRr"
    "aGQAAAADAAAAAAAAAAAAAAABAAAAAAAAB9AAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAA"
    "AAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAKAAAAB4AAAAAAAkZWR0cwAAABxlbHN0AAAAAAAA"
    "AAEAAAfQAAAIAAABAAAAAAKTbWRpYQAAACBtZGhkAAAAAAAAAAAAAAAAAAAoAAAAUABVxAAA"
    "AAAALWhkbHIAAAAAAAAAAHZpZGUAAAAAAAAAAAAAAABWaWRlb0hhbmRsZXIAAAACPm1pbmYA"
    "AAAUdm1oZAAAAAEAAAAAAAAAAAAAACRkaW5mAAAAHGRyZWYAAAAAAAAAAQAAAAx1cmwgAAAA"
    "AQAAAf5zdGJsAAAAvnN0c2QAAAAAAAAAAQAAAK5hdmMxAAAAAAAAAAEAAAAAAAAAAAAAAAAA"
    "AAAAAKAAeABIAAAASAAAAAAAAAABFUxhdmM2MC4zMS4xMDIgbGlieDI2NAAAAAAAAAAAAAAA"
    "GP//AAAANGF2Y0MBZAAK/+EAGWdkAAqs2UKEflwEQAAAAwBAAAAFA8SJZYABAARo74/L/fj4"
    "AAAAABBwYXNwAAAAAQAAAAEAAAAUYnRydAAAAAAAAGM4AABjOAAAABhzdHRzAAAAAAAAAAEA"
    "AAAUAAAEAAAAABRzdHNzAAAAAAAAAAEAAAABAAAAeGN0dHMAAAAAAAAADQAAAAMAAAgAAAAA"
    "AQAADAAAAAABAAAEAAAAAAYAAAgAAAAAAQAAFAAAAAABAAAIAAAAAAEAAAAAAAAAAQAABAAA"
    "AAABAAAUAAAAAAEAAAgAAAAAAQAAAAAAAAABAAAEAAAAAAEAAAgAAAAAHHN0c2MAAAAAAAAA"
    "AQAAAAEAAAAUAAAAAQAAAGRzdHN6AAAAAAAAAAAAAAAUAAAKhAAAANsAAADsAAABTAAAABoA"
    "AADoAAAAzgAAANsAAADzAAAA5QAAAWUAAAHiAAAAUAAAABsAAAAcAAABpAAAAF4AAAAlAAAA"
    "KAAAAJcAAAAUc3RjbwAAAAAAAAABAAAEIQAAAGJ1ZHRhAAAAWm1ldGEAAAAAAAAAIWhkbHIA"
    "AAAAAAAAAG1kaXJhcHBsAAAAAAAAAAAAAAAALWlsc3QAAAAlqXRvbwAAAB1kYXRhAAAAAQAA"
    "AABMYXZmNjAuMTYuMTAwAAAACGZyZWUAABjWbWRhdAAAAq0GBf//qdxF6b3m2Ui3lizYINkj"
    "7u94MjY0IC0gY29yZSAxNjQgcjMxMDggMzFlMTlmOSAtIEguMjY0L01QRUctNCBBVkMgY29k"
    "ZWMgLSBDb3B5bGVmdCAyMDAzLTIwMjMgLSBodHRwOi8vd3d3LnZpZGVvbGFuLm9yZy94MjY0"
    "Lmh0bWwgLSBvcHRpb25zOiBjYWJhYz0xIHJlZj0xIGRlYmxvY2s9MTowOjAgYW5hbHlzZT0w"
    "eDM6MHgxMTMgbWU9aGV4IHN1Ym1lPTIgcHN5PTEgcHN5X3JkPTEuMDA6MC4wMCBtaXhlZF9y"
    "ZWY9MCBtZV9yYW5nZT0xNiBjaHJvbWFfbWU9MSB0cmVsbGlzPTAgOHg4ZGN0PTEgY3FtPTAg"
    "ZGVhZHpvbmU9MjEsMTEgZmFzdF9wc2tpcD0xIGNocm9tYV9xcF9vZmZzZXQ9MCB0aHJlYWRz"
    "PTMgbG9va2FoZWFkX3RocmVhZHM9MSBzbGljZWRfdGhyZWFkcz0wIG5yPTAgZGVjaW1hdGU9"
    "MSBpbnRlcmxhY2VkPTAgYmx1cmF5X2NvbXBhdD0wIGNvbnN0cmFpbmVkX2ludHJhPTAgYmZy"
    "YW1lcz0zIGJfcHlyYW1pZD0yIGJfYWRhcHQ9MSBiX2JpYXM9MCBkaXJlY3Q9MSB3ZWlnaHRi"
    "PTEgb3Blbl9nb3A9MCB3ZWlnaHRwPTEga2V5aW50PTI1MCBrZXlpbnRfbWluPTEwIHNjZW5l"
    "Y3V0PTQwIGludHJhX3JlZnJlc2g9MCByY19sb29rYWhlYWQ9MTAgcmM9Y3JmIG1idHJlZT0x"
    "IGNyZj0yMy4wIHFjb21wPTAuNjAgcXBtaW49MCBxcG1heD02OSBxcHN0ZXA9NCBpcF9yYXRp"
    "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"
    "ChNEF73aUa19"
)


def clip_bytes(when: str) -> bytes:
    """A playable clip that honestly says when it was taken.

    The time goes into `moov/mvhd` and into the track's `mdhd` - seconds since
    1904, UTC, which is what the specification says and what this app reads.
    """
    import base64
    stamp = time.strptime(when, "%Y:%m:%d %H:%M:%S")
    # 1904 to 1970, in seconds - the offset the format is defined against
    secs = int(time.mktime(stamp)) - time.timezone + 2082844800
    body = bytearray(base64.b64decode("".join(_CLIP)))
    for tag in (b"mvhd", b"mdhd"):
        at = body.find(tag)
        if at < 0 or body[at + 4] != 0:        # version 0 is what this file has
            continue
        body[at + 8:at + 16] = struct.pack(">II", secs, secs)
    return bytes(body)


# ---------------------------------------------------------------------- building

def have_pillow() -> bool:
    try:
        import PIL                                     # noqa: F401
        return True
    except Exception:                                  # noqa: BLE001
        return False


def built(root: str) -> bool:
    """Was this folder made by us? The only thing removal is allowed to trust."""
    return os.path.isfile(os.path.join(root, MARK))


def present(root: str) -> dict:
    """What is in there now - so a plan can say "already built" rather than
    offering to build a second copy over the top of the first."""
    if not os.path.isdir(root):
        return {"there": False, "ours": False, "files": 0}
    n = sum(len(names) for _here, _dirs, names in os.walk(root))
    return {"there": True, "ours": built(root), "files": n}


def build(root: str, progress=None) -> dict:
    """Write the sample library. Returns what it wrote, and what it could not.

    Never overwrites: a file already there is counted as left alone. Building
    twice therefore costs nothing and cannot damage a half-built library, which
    is the behaviour somebody who pressed the button twice deserves.
    """
    made, kept, failed = [], [], []
    os.makedirs(root, exist_ok=True)
    # Counted like everything else. It is one of the files the recipe promises,
    # and leaving it out made a clean build report "42 written, 1 unchanged" -
    # one unexplained file, which is exactly the kind of small wrongness that
    # makes somebody stop trusting the numbers.
    (kept if os.path.exists(os.path.join(root, MARK)) else made).append(MARK)
    with open(os.path.join(root, MARK), "w", encoding="utf-8") as fh:
        fh.write("Built by Photo Manager as a sample library to practise on.\n"
                 "Removing this file stops the app from being willing to "
                 "delete the folder for you.\n")
    total = len(SHOTS) + len(CLIPS)
    for i, shot in enumerate(SHOTS):
        if progress:
            progress(i, total, shot[0])
        path = os.path.join(root, *shot[0].split("/"))
        try:
            _write_shot(root, shot, path, made, kept)
        except Exception as exc:                       # noqa: BLE001
            failed.append(f"{shot[0]}: {exc}")
    for j, (rel, when) in enumerate(CLIPS):
        if progress:
            progress(len(SHOTS) + j, total, rel)
        path = os.path.join(root, *rel.split("/"))
        try:
            if os.path.exists(path):
                kept.append(rel)
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(clip_bytes(when))
            made.append(rel)
        except Exception as exc:                       # noqa: BLE001
            failed.append(f"{rel}: {exc}")
    return {"made": made, "kept": kept, "failed": failed, "root": root}


def _write_shot(root: str, shot, path: str, made: list, kept: list) -> None:
    extra = shot[7]
    rel = shot[0]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        im = _pixels(extra.get("pixels") or os.path.basename(rel),
                     extra.get("blur", 0.0))
        if extra.get("no_exif"):
            im.save(path, quality=88)
        else:
            im.save(path, quality=88, exif=_exif(shot))
        made.append(rel)
    else:
        kept.append(rel)
    suffix = extra.get("raw")
    if not suffix:
        return
    stem = os.path.splitext(os.path.basename(rel))[0]
    raw_rel = f"{_raw_home(shot)}/{stem}{suffix}"
    raw_path = os.path.join(root, *raw_rel.split("/"))
    if os.path.exists(raw_path):
        kept.append(raw_rel)
        return
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    # JPEG bytes under a RAW name, and deliberately NO EXIF - which is exactly
    # how this app sees a real RW2: matched by name and position, never by what
    # is inside it.
    # `format` named outright: Pillow picks it from the extension, and .RW2 is
    # not an extension it knows how to write.
    _pixels("neg " + stem).save(raw_path, format="JPEG", quality=80)
    made.append(raw_rel)


def removable(root: str) -> str:
    """"" when it is safe to delete, otherwise the reason it is not."""
    if not os.path.isdir(root):
        return "There is nothing there."
    if not built(root):
        return ("That folder was not built by this app - the marker it writes is "
                "not in it. Nothing has been removed.")
    return ""


def remove(root: str) -> dict:
    """Delete a sample library, and only a sample library."""
    why = removable(root)
    if why:
        return {"gone": 0, "why": why}
    import shutil
    n = sum(len(names) for _here, _dirs, names in os.walk(root))
    shutil.rmtree(root)
    return {"gone": n, "why": ""}
