"""Builds the test photos, using Pillow.

Run once; the results are committed so the tests need nothing installed. Built
with a DIFFERENT library from the one under test on purpose - fixtures made by
the code being tested would agree with it about anything, including a mistake.

The HEIC ones also need `pillow-heif` (not `pi-heif`, which cannot encode):

    python tools/make_fixtures.py           # everything it can make
    python tools/make_fixtures.py heic      # only the HEIC ones
    python tools/make_fixtures.py deep_xmp  # only deep_xmp.jpg
"""
import os
import sys

from PIL import Image
from PIL.TiffImagePlugin import IFDRational as R

OUT = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures")


def distinct_image(seed: str) -> Image.Image:
    """A small picture whose PIXELS differ from every other fixture's.

    They used to be one flat colour, which meant "the picture is unchanged"
    could be checked against the wrong file and still pass - a test that cannot
    fail. Deriving the pattern from the name makes that comparison mean something.
    """
    h = abs(hash(seed))
    im = Image.new("RGB", (16, 12))
    px = im.load()
    for y in range(12):
        for x in range(16):
            px[x, y] = ((h + x * 17 + y * 31) % 256,
                        (h // 7 + x * 5) % 256,
                        (h // 13 + y * 11) % 256)
    return im


def photo(name, *, taken="2022:07:14 18:03:22", model="DMC-GH4", rating=None,
          lat=None, lon=None, latref="N", lonref="E", alt=None, altref=0,
          gpsdate=None, gpstime=None, subsec=None, ev=None, expmode=None,
          fnum=5.6, iso=200, exp_den=250, focal=25, offset=None,
          no_exif=False, decimal_coords=False, heif=False):
    im = distinct_image(name)
    if heif:
        # The HEVC encoder works in blocks of eight; a 16x12 picture is padded
        # into something no phone would write, so these are drawn larger.
        im = im.resize((64, 48))
    path = os.path.join(OUT, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if no_exif:
        im.save(path)
        return path
    ex = Image.Exif()
    ex[0x010F], ex[0x0110], ex[0x0132] = "TEST", model, taken
    if rating is not None:
        ex[0x4746] = rating
    sub = ex.get_ifd(0x8769)
    sub[0x9003] = taken
    if subsec:  sub[0x9291] = subsec
    if offset:  sub[0x9011] = offset
    if ev is not None:      sub[0x9204] = R(int(round(ev * 100)), 100)
    if expmode is not None: sub[0xA402] = expmode
    sub[0x829D] = R(int(fnum * 10), 10)
    sub[0x8827] = iso
    sub[0x829A] = R(1, exp_den)
    sub[0x920A] = R(focal, 1)
    if lat is not None:
        g = ex.get_ifd(0x8825)
        g[0x0001], g[0x0003] = latref, lonref

        def parts(v):
            if decimal_coords:
                return (R(int(v * 1_000_000), 1_000_000), R(0, 1), R(0, 1))
            d = int(v); m = int((v - d) * 60); s = round(((v - d) * 60 - m) * 60, 4)
            return (R(d, 1), R(m, 1), R(int(s * 10000), 10000))

        g[0x0002], g[0x0004] = parts(abs(lat)), parts(abs(lon))
        if alt is not None:
            g[0x0005], g[0x0006] = altref, R(int(alt * 10), 10)
        if gpsdate: g[0x001D] = gpsdate
        if gpstime: g[0x0007] = tuple(R(int(x * 100), 100) for x in gpstime)
    if heif:
        im.save(path, format="HEIF", exif=ex.tobytes(), quality=60)
    else:
        im.save(path, exif=ex)
    return path


def build_heic():
    """The phone photographs again, as an iPhone saves them."""
    try:
        import pillow_heif
    except ImportError:
        print("HEIC fixtures skipped: pip install pillow-heif to make them")
        return
    pillow_heif.register_heif_opener()
    photo("phone_doha.heic", model="iPhone 15 Pro", taken="2022:07:14 21:03:20",
          lat=25.2854, lon=51.5310, alt=12.5, offset="+03:00",
          gpsdate="2022:07:14", gpstime=(18, 3, 20.0), heif=True)
    photo("plain.heic", model="iPhone 15 Pro", taken="2022:07:14 18:03:22",
          heif=True)


# What Lightroom leaves in a JPEG it exported: a crop, a keyword and a rating,
# in the photo's own packet, and nothing in the Windows rating tag.
DEEP_PACKET = (
    '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
    '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
    ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
    '  <rdf:Description rdf:about=""\n'
    '    xmlns:xmp="http://ns.adobe.com/xap/1.0/"\n'
    '    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"\n'
    '    xmlns:dc="http://purl.org/dc/elements/1.1/"\n'
    '    xmp:Rating="4"\n'
    '    crs:CropTop="0.125">\n'
    '   <dc:subject><rdf:Bag><rdf:li>Italy</rdf:li></rdf:Bag></dc:subject>\n'
    '  </rdf:Description>\n'
    ' </rdf:RDF>\n'
    '</x:xmpmeta>\n'
    '<?xpacket end="w"?>')


def build_deep_xmp():
    """A JPEG whose XMP packet sits past the first 256 KB of the file.

    A large ICC profile - five APP2 chunks, as a wide-gamut export carries -
    ahead of the packet. Readers that only look at the first quarter megabyte
    see no packet at all, and writers that trust them build a fresh one over it.
    Pillow writes the picture, EXIF and ICC; the packet is spliced in by hand
    after the last APP2, which is where an editor that rewrites it puts it.
    """
    import io
    import struct
    im = distinct_image("deep_xmp")
    ex = Image.Exif()
    ex[0x0110] = "DMC-GH4"
    ex[0x0132] = "2022:07:14 18:03:22"
    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=ex, icc_profile=bytes(300_000), quality=60)
    data = buf.getvalue()
    i, last = 2, 2
    while data[i] == 0xFF and data[i + 1] != 0xDA:
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if data[i + 1] in (0xE0, 0xE1, 0xE2):
            last = i + 2 + length
        i += 2 + length
    payload = b"http://ns.adobe.com/xap/1.0/\x00" + DEEP_PACKET.encode("utf-8")
    seg = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
    assert last > 262_144, "the packet must land past the first 256 KB"
    with open(os.path.join(OUT, "deep_xmp.jpg"), "wb") as fh:
        fh.write(data[:last] + seg + data[last:])


def build():
    os.makedirs(OUT, exist_ok=True)
    photo("plain.jpg")
    photo("noexif.jpg", no_exif=True)
    photo("rated.jpg", rating=4)
    photo("phone_doha.jpg", model="SM-G991B", taken="2022:07:14 21:03:20",
          lat=25.2854, lon=51.5310, alt=12.5,
          gpsdate="2022:07:14", gpstime=(18, 3, 20.0))
    photo("phone_south.jpg", model="SM-G991B", taken="2022:07:14 21:10:00",
          lat=-33.8688, lon=-70.6693, latref="S", lonref="W",
          gpsdate="2022:07:14", gpstime=(18, 10, 0.0))
    photo("phone_decimal.jpg", model="SM-G991B", taken="2022:07:14 21:20:00",
          lat=25.2854, lon=51.5310, decimal_coords=True,
          gpsdate="2022:07:14", gpstime=(18, 20, 0.0))
    photo("phone_belowsea.jpg", model="SM-G991B", taken="2022:07:14 21:30:00",
          lat=31.5590, lon=35.4732, alt=430.0, altref=1, offset="+03:00",
          gpsdate="2022:07:14", gpstime=(18, 30, 0.0))
    photo("phone_nullisland.jpg", model="SM-G991B", taken="2022:07:14 21:50:00",
          lat=0.0, lon=0.0, gpsdate="2022:07:14", gpstime=(18, 50, 0.0))
    photo("aeb1.jpg", taken="2022:07:14 18:03:22", subsec="10", ev=-1, expmode=2, exp_den=500)
    photo("aeb2.jpg", taken="2022:07:14 18:03:22", subsec="45", ev=0,  expmode=2, exp_den=250)
    photo("aeb3.jpg", taken="2022:07:14 18:03:23", subsec="10", ev=1,  expmode=2, exp_den=125)
    photo("burst1.jpg", taken="2022:07:14 18:10:00", ev=0, expmode=0)
    photo("burst2.jpg", taken="2022:07:14 18:10:01", ev=0, expmode=0)
    photo("burst3.jpg", taken="2022:07:14 18:10:02", ev=0, expmode=0)
    with open(os.path.join(OUT, "notajpeg.jpg"), "wb") as fh:
        fh.write(b"this is not a jpeg at all")
    build_deep_xmp()
    build_heic()
    print(f"fixtures written to {os.path.abspath(OUT)}")


if __name__ == "__main__":
    if sys.argv[1:] == ["heic"]:
        sys.exit(build_heic())
    if sys.argv[1:] == ["deep_xmp"]:
        sys.exit(build_deep_xmp())
    sys.exit(build())
