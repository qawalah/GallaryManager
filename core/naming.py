"""Folder names from a pattern you write: `{year}/{country} - {city}`.

A pattern is text with variables in braces. Every `/` starts a folder inside
the one before it, and a level can hold as many variables and as much of your
own text as you like: `{year}/{month} {monthname} - {city}` is two levels, the
second reading `07 July - Rome`.

**A missing value is dropped, never guessed.** A photo with no region in
`{country} - {region}` becomes `Spain`, not `Spain - ` and not a region made
up from somewhere else. The separators around an empty variable go with it,
and a level that ends up empty is not made at all. Two things are stricter,
because they decide whether the photo can be filed:

- a pattern that uses a PLACE variable leaves a photo with no known country
  exactly where it is;
- `{city}` for a photo whose country is known and town is not is `_Unsure`,
  the rule the place shapes always had - the half that is known is used, the
  half that is not is named.

Nothing here reads a file. The caller hands over the facts; this only spells
them - which is what makes it testable, and what lets the page show an example
while you type.
"""

from __future__ import annotations

import datetime as _dt
import re

UNSURE = "_Unsure"

MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

# name: (what it is, example) - the order they are offered in
VARIABLES = [
    ("year", "Year", "2022"),
    ("yy", "Year, two digits", "22"),
    ("month", "Month number", "07"),
    ("monthname", "Month name", "July"),
    ("mon", "Month, short", "Jul"),
    ("day", "Day", "14"),
    ("date", "Full date", "2022-07-14"),
    ("weekday", "Day of the week", "Thursday"),
    ("week", "Week it began", "2022-07-11"),
    ("weekyear", "Year that week began", "2022"),
    ("range", "The shoot's dates", "12-15 Jul"),
    ("rangestart", "The shoot's first day", "2022-07-12"),
    # The examples are all the SAME day - 14 July 2022 - so a pattern mixing
    # both calendars shows one date rather than two unrelated ones.
    ("hyear", "Hijri year", "1443"),
    ("hmonth", "Hijri month number", "12"),
    ("hmonthname", "Hijri month", "Dhul Hijjah"),
    ("hmon", "Hijri month, short", "DhH"),
    ("hday", "Hijri day", "15"),
    ("hdate", "Full Hijri date", "1443-12-15"),
    ("country", "Country", "Spain"),
    ("cc", "Country code", "ES"),
    ("region", "Region or state", "Catalonia"),
    ("city", "City or town", "Barcelona"),
    ("camera", "Camera", "DMC-GH4"),
    ("lens", "Lens", "LUMIX G 25mm F1.7"),
]
NAMES = {v[0] for v in VARIABLES}
PLACE = {"country", "cc", "region", "city"}
DATE = {"year", "yy", "month", "monthname", "mon", "day", "date", "weekday",
        "week", "weekyear", "range", "rangestart",
        "hyear", "hmonth", "hmonthname", "hmon", "hday", "hdate"}
HIJRI = {"hyear", "hmonth", "hmonthname", "hmon", "hday", "hdate"}
RANGE = {"range", "rangestart"}

_VAR = re.compile(r"\{([a-zA-Z]+)\}")
_BAD = re.compile(r'[\\:*?"<>|\x00-\x1f]')
_EDGE = " -,.·–—+&"

# The shapes offered ready-made. Few on purpose: anything else is one pattern
# away, and a list of nineteen was a list nobody read to the bottom of.
PRESETS = [
    ("year_month", "{year}/{month}", "By date"),
    ("year_month_name", "{year}/{month} {monthname}", "By date"),
    ("year_date", "{year}/{date}", "By date"),
    ("year_range", "{year}/{range}", "By date"),
    ("hijri_year_month", "{hyear}/{hmonth} {hmonthname}", "By date, Hijri"),
    ("place_country_city", "{country}/{city}", "By place"),
    ("place_year_country_city", "{year}/{country} - {city}", "By place"),
    ("place_country_year_city", "{country}/{year}/{city}", "By place"),
]

# Every shape the app ever offered, so a flow or a saved form that names one
# keeps doing exactly what it did.
LEGACY = {
    "year": "{year}",
    "year_month": "{year}/{month}",
    "year_month_name": "{year}/{month} {monthname}",
    "year_dash_month": "{year}/{year}-{month}",
    "flat_month": "{year}-{month}",
    "year_week": "{weekyear}/week of {week}",
    "year_month_day": "{year}/{month}/{day}",
    "year_month_dashday": "{year}/{month}/{date}",
    "flat_day": "{date}",
    "year_date": "{year}/{date}",
    "year_range": "{year}/{range}",
    "hijri_year_month": "{hyear}/{hmonth} {hmonthname}",
    "place_country": "{country}",
    "place_city": "{city}",
    "place_country_city": "{country}/{city}",
    "place_country_dash_city": "{country} - {city}",
    "place_country_year_city": "{country}/{year}/{city}",
    "place_country_city_month": "{country}/{city}/{year}-{month}",
    "place_city_year": "{city}/{year}",
    "place_year_city": "{year}/{city}",
    "place_year_country_city": "{year}/{country} - {city}",
    "place_year_month_place": "{year}/{month}/{country} - {city}",
}


def used(pattern: str) -> set:
    return {m.lower() for m in _VAR.findall(pattern or "")}


def needs_place(pattern: str) -> bool:
    return bool(used(pattern) & PLACE)


def needs_date(pattern: str) -> bool:
    return bool(used(pattern) & DATE)


def needs_range(pattern: str) -> bool:
    return bool(used(pattern) & RANGE)


def problem(pattern: str) -> str:
    """Why this pattern cannot be used, or "" when it can."""
    text = str(pattern or "").strip()
    if not text:
        return "The pattern is empty."
    unknown = sorted(used(text) - NAMES)
    if unknown:
        return ("Not a variable: " + ", ".join("{" + u + "}" for u in unknown)
                + ". Pick from the list under the box.")
    if text.count("{") != text.count("}"):
        return "A { or } is not closed."
    if ".." in text.replace("\\", "/").split("/"):
        return "A folder cannot be called '..'."
    if not used(text):
        return ("There is no variable in it, so every photo would go into the "
                "same folder. Add at least one - {year}, say.")
    return ""


def spell_range(start, end) -> str:
    """12-15 Jul, 28 Jul - 2 Aug, 28 Dec 2021 - 3 Jan 2022. One day: 14 Jul."""
    if not start:
        return ""
    end = end or start
    a, b = start.date() if hasattr(start, "date") else start, \
        end.date() if hasattr(end, "date") else end
    mon = lambda d: MONTHS[d.month][:3]            # noqa: E731
    if a == b:
        return f"{a.day:02d} {mon(a)}"
    if (a.year, a.month) == (b.year, b.month):
        return f"{a.day:02d}-{b.day:02d} {mon(a)}"
    if a.year == b.year:
        return f"{a.day:02d} {mon(a)} - {b.day:02d} {mon(b)}"
    return f"{a.day:02d} {mon(a)} {a.year} - {b.day:02d} {mon(b)} {b.year}"


def needs_hijri(pattern: str) -> bool:
    return bool(used(pattern) & HIJRI)


def facts(taken=None, place=None, camera: str = "", lens: str = "",
          shoot=None, week_starts: int = 0, hijri_shift: int = 0) -> dict:
    """The values, from what the caller knows. Anything unknown is ""."""
    out = {n: "" for n in NAMES}
    if taken is not None:
        y, m, d = taken.year, taken.month, taken.day
        began = (taken - _dt.timedelta(days=(taken.weekday() - week_starts) % 7))
        out.update(year=f"{y}", yy=f"{y % 100:02d}", month=f"{m:02d}",
                   monthname=MONTHS[m], mon=MONTHS[m][:3], day=f"{d:02d}",
                   date=f"{y}-{m:02d}-{d:02d}", weekday=taken.strftime("%A"),
                   week=began.strftime("%Y-%m-%d"), weekyear=f"{began.year}")
        from . import hijri as _hijri
        hy, hm, hd = _hijri.from_gregorian(taken, hijri_shift)
        if hy:
            out.update(hyear=f"{hy}", hmonth=f"{hm:02d}",
                       hmonthname=_hijri.name(hm), hmon=_hijri.short(hm),
                       hday=f"{hd:02d}", hdate=f"{hy}-{hm:02d}-{hd:02d}")
        first, last = shoot if shoot else (taken, taken)
        out["range"] = spell_range(first, last)
        out["rangestart"] = first.strftime("%Y-%m-%d")
    if place is not None:
        country = str(getattr(place, "country", "") or "").strip()
        city = str(getattr(place, "city", "") or "").strip()
        out.update(country=country, cc=str(getattr(place, "code", "") or "").upper(),
                   region=str(getattr(place, "region", "") or "").strip(),
                   city=city or (UNSURE if country else ""))
    out["camera"] = str(camera or "").strip()
    out["lens"] = str(lens or "").strip()
    return out


def _clean(value: str) -> str:
    """A value that is safe as part of ONE folder name."""
    value = _BAD.sub("", str(value or "").replace("/", " "))
    return re.sub(r"\s+", " ", value).strip()


def render(pattern: str, values: dict) -> str:
    """The relative folder for these values, "/"-separated, or "" for none.

    "" means leave the photo where it is: a place pattern with no country, or
    a date pattern with no date.
    """
    wanted = used(pattern)
    if wanted & PLACE and not values.get("country"):
        return ""
    if wanted & DATE and not values.get("year"):
        return ""
    levels = []
    for level in str(pattern or "").replace("\\", "/").split("/"):
        # Each variable replaced by a marker when empty, so the text around an
        # empty one can be tidied away without touching the text you typed
        # around a full one.
        EMPTY = "\x00"
        text = _VAR.sub(lambda m: _clean(values.get(m.group(1).lower(), ""))
                        or EMPTY, level)
        # An empty value takes the separator BEFORE it with it - "Spain - \0 -
        # Girona" is "Spain - Girona" - or, at the start, the one after it.
        text = re.sub(r"[ \-,.·–—+&]*\x00", "", text) if not text.startswith(EMPTY) \
            else text
        text = re.sub(r"\x00[ \-,.·–—+&]*", "", text)
        text = re.sub(r"[ \-,.·–—+&]*\x00", "", text)
        text = re.sub(r"\(\s*\)|\[\s*\]", "", text)
        text = _clean(text).strip(_EDGE)
        if text and text not in (".", ".."):
            levels.append(text)
    return "/".join(levels)


def example(pattern: str) -> str:
    """What the pattern makes for one sample photo - for the page, while typing."""
    sample = {v[0]: v[2] for v in VARIABLES}
    return render(pattern, sample)


def shoots_of(times, gap_hours: float = 24.0) -> dict:
    """{time: (first, last)} - photos grouped into shoots by gaps between them.

    A new shoot starts when nothing was taken for `gap_hours`. A trip is then one
    range however many days it ran; the weekend after it is another.
    """
    out = {}
    ordered = sorted(set(t for t in times if t is not None))
    if not ordered:
        return out
    gap = _dt.timedelta(hours=gap_hours)
    group = [ordered[0]]
    for t in ordered[1:]:
        if t - group[-1] > gap:
            for g in group:
                out[g] = (group[0], group[-1])
            group = [t]
        else:
            group.append(t)
    for g in group:
        out[g] = (group[0], group[-1])
    return out


# ------------------------------------------------------------ kept patterns

def saved() -> list:
    """[(name, pattern)] kept in Setup's settings, in the order they were kept."""
    import json
    from . import settings as S
    try:
        got = json.loads(S.load()["folder_patterns"] or "[]")
        return [(str(n), str(p)) for n, p in got if str(n).strip() and str(p).strip()]
    except (ValueError, TypeError):
        return []


def keep(name: str, pattern: str) -> list:
    """Save (or replace) one by name. Refuses a pattern that cannot work."""
    import json
    from . import settings as S
    name, pattern = str(name or "").strip(), str(pattern or "").strip()
    if not name:
        raise ValueError("Give it a name.")
    why = problem(pattern)
    if why:
        raise ValueError(why)
    have = [(n, p) for n, p in saved() if n.lower() != name.lower()]
    have.append((name, pattern))
    S.save({"folder_patterns": json.dumps(have)})
    return have


def forget(name: str) -> list:
    import json
    from . import settings as S
    have = [(n, p) for n, p in saved() if n.lower() != str(name).strip().lower()]
    S.save({"folder_patterns": json.dumps(have)})
    return have


def label(pattern: str) -> str:
    """How a pattern reads in a list: dates as a real date, the rest by name.

    "2022 / 07" says what it IS; "Country / City" rather than "Italy / Rome",
    because an example place is read as a promise about that place.
    """
    sample = {v[0]: v[2] for v in VARIABLES}
    for n in PLACE | {"camera", "lens"}:
        sample[n] = {"cc": "CC"}.get(n, n.capitalize())
    return render(pattern, sample).replace("/", " / ")


def pattern_for(shape: str, custom: str = "") -> str:
    """The pattern a shape stands for: a preset, a kept one, or yours."""
    shape = str(shape or "")
    if shape == "custom":
        return str(custom or "").strip()
    if shape.startswith("saved:"):
        want = shape[6:].strip().lower()
        for n, p in saved():
            if n.lower() == want:
                return p
        return ""
    return LEGACY.get(shape, "")
