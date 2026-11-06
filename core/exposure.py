"""How a photograph is exposed, measured rather than guessed.

The viewer has had a histogram since 1.x, which answers the question one
photograph at a time while you are looking at it. This answers it for a folder
you are not looking at: which of these four hundred frames are blown out, and
which are so dark there is nothing in them.

**It is measured off the thumbnail, on purpose.** A thumbnail is a faithful
average of the picture - that is what shrinking does - and the question here is
about the whole frame, not about one pixel. Reading a 25MB RAW to answer it
would make this the slowest feature in the app and would not change a single
verdict. The thumbnails are already made and already cached (`core/thumbs.py`),
so a second pass over a folder costs nothing.

**Three numbers, not a score.** How much of the frame is at the very top of the
range, how much is at the very bottom, and the average. A photograph is called
over or under exposed when it crosses a threshold you can see and change - and
the numbers are reported beside the verdict, so a verdict you disagree with is
one you can argue with rather than one you have to accept.

**A silhouette is not a fault and nor is snow.** This cannot know what you meant,
so it does not pretend to: deliberate high key and a backlit portrait both
appear. That is why nothing here deletes, moves or rates anything - the most it
will do is write a tag, which is a thing you asked for and can search by.
"""

from __future__ import annotations

# A pixel this bright is at the top of what the file can hold; this dark is at
# the bottom. Not 255 and 0: a JPEG that has been through a camera's processing
# rarely has pure values, and a threshold of exactly 255 finds almost nothing
# on a frame that is visibly blown.
HIGH = 249
LOW = 6

# What counts as a fault, as a percentage of the frame. Defaults, and the task
# that uses them offers both as settings - the right number for a landscape is
# not the right number for a concert.
OVER_PCT = 5.0
UNDER_PCT = 40.0
# A frame that clips at BOTH ends - a subject against a window - is decided by
# its average rather than being called both.


class Unreadable(Exception):
    """No picture could be made of this file. Said, never guessed around."""


def luminance_histogram(data: bytes) -> list:
    """256 buckets of brightness, from JPEG bytes.

    Luminance rather than the three channels: "is this blown" is a question
    about the light in the frame, and a red flower with a saturated red channel
    is not an over-exposed photograph.
    """
    import io
    from PIL import Image
    try:
        with Image.open(io.BytesIO(data)) as im:
            grey = im.convert("L")
            return list(grey.histogram())
    except Exception as exc:                               # noqa: BLE001
        raise Unreadable(str(exc)) from exc


def verdict(hist, over_pct: float = OVER_PCT, under_pct: float = UNDER_PCT) -> dict:
    """What those buckets say, in numbers and then in one word."""
    total = sum(hist) or 1
    high = sum(hist[HIGH:]) * 100.0 / total
    low = sum(hist[:LOW + 1]) * 100.0 / total
    mean = sum(i * n for i, n in enumerate(hist)) / total
    # The threshold decides, and nothing else - otherwise moving it would not
    # move the answer, which is the one thing a setting has to do.
    blown = high >= over_pct
    dark = low >= under_pct
    said = "ok"
    if blown and dark:
        # A backlit subject clips at both ends every time. It has to come out as
        # one thing, and the average is what says which; "both" is a verdict
        # nobody can act on.
        said = "over" if mean >= 128 else "under"
    elif blown:
        said = "over"
    elif dark:
        said = "under"
    return {"high": round(high, 2), "low": round(low, 2),
            "mean": round(mean, 1), "verdict": said}


def look_at(path: str, over_pct: float = OVER_PCT,
            under_pct: float = UNDER_PCT) -> dict:
    """Measure one photograph. Raises `Unreadable` rather than guessing."""
    from . import thumbs
    data = thumbs.thumb(path, "s")
    if not data:
        raise Unreadable("this file cannot be shown")
    got = verdict(luminance_histogram(data), over_pct, under_pct)
    got["path"] = path
    return got


def describe(got: dict) -> str:
    """The numbers, in a line somebody can disagree with."""
    if got["verdict"] == "over":
        return (f"{got['high']:.1f}% of the frame is at the top of the range "
                f"(average {got['mean']:.0f})")
    if got["verdict"] == "under":
        return (f"{got['low']:.1f}% of the frame is at the bottom of the range "
                f"(average {got['mean']:.0f})")
    return (f"{got['high']:.1f}% high, {got['low']:.1f}% low, "
            f"average {got['mean']:.0f}")
