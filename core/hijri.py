"""The Hijri date of a photograph, for folders named the way the year is lived.

"2022 April" and "Ramadan 1443" are the same fortnight named two different
ways, and for some libraries the second is the one you would look under. So
the sort patterns can use Hijri variables beside the Gregorian ones.

**How it is worked out, and where it can be a day out.** There is no formula
for the Islamic calendar: a month begins when the new moon is sighted, and that
is announced, not computed. What can be computed is the ARITHMETIC calendar - a
30-year cycle of 354 and 355 day years - which stays within a day or two of the
announced dates forever but is not them.

Two things close that gap:

- **Known starts are used when there are any.** A small table of announced
  first-of-the-month dates ships with the app, and the conversion counts
  forward from the most recent one rather than from the year 622. A date after
  the last known start falls back to arithmetic, and is at most a day or so off.
- **You can add your own.** `hijri-starts.tsv` in the config folder, one line
  per month: `1447-09  2026-02-18`. Yours win over the built-in ones, so a
  country that started a day later than Saudi Arabia is one line to fix, not a
  bug to report.

A photograph taken within a day of a month's end is the only one this can
misfile, and it says so on the tab rather than pretending otherwise.
"""

from __future__ import annotations

import datetime as _dt
import os

# Latin spellings, without punctuation: these become folder names, and an
# apostrophe in a folder name is a thing to get wrong on one machine out of
# three.
MONTHS = ["", "Muharram", "Safar", "Rabi al-Awwal", "Rabi al-Thani",
          "Jumada al-Awwal", "Jumada al-Thani", "Rajab", "Shaban", "Ramadan",
          "Shawwal", "Dhul Qidah", "Dhul Hijjah"]
SHORT = ["", "Muh", "Saf", "Rab1", "Rab2", "Jum1", "Jum2", "Raj", "Sha",
         "Ram", "Shw", "DhQ", "DhH"]

# The arithmetic calendar: 11 leap years in every 30, and months alternating
# 30 and 29 days with a long twelfth month in a leap year.
LEAP = {2, 5, 7, 10, 13, 16, 18, 21, 24, 26, 29}
EPOCH = 1948440                     # julian day number of 1 Muharram 1 AH
CYCLE = 10631                       # days in 30 Hijri years

FILE = "hijri-starts.tsv"

# Announced first days of months, as published for Saudi Arabia (Umm al-Qura).
# Only a handful, and only where the date is not in dispute - the point of them
# is to pin the recent years, not to be a calendar of record. Add your own in
# the file above; yours win.
KNOWN = {
    (1443, 9): "2022-04-02",
    (1444, 1): "2022-07-30",
    (1444, 9): "2023-03-23",
    (1444, 10): "2023-04-21",
    (1445, 1): "2023-07-19",
    (1445, 9): "2024-03-11",
    (1446, 9): "2025-03-01",
    (1446, 10): "2025-03-30",
    (1447, 9): "2026-02-18",
}


def month_length(year: int, month: int) -> int:
    if month == 12 and ((year - 1) % 30 + 1) in LEAP:
        return 30
    return 30 if month % 2 == 1 else 29


def year_length(year: int) -> int:
    return 355 if ((year - 1) % 30 + 1) in LEAP else 354


def _tabular_start(year: int, month: int) -> _dt.date:
    """The arithmetic calendar's first day of that Hijri month, as a date."""
    days = 0
    cycles, rest = divmod(year - 1, 30)
    days += cycles * CYCLE
    for y in range(1, rest + 1):
        days += year_length(y)
    for m in range(1, month):
        days += month_length(year, m)
    return _dt.date.fromordinal(EPOCH + days - 1721425)


FIRST_YEAR, LAST_YEAR = 1300, 1600          # 1882 to 2176, and cheap to build


def _starts() -> list:
    """[(gregorian date, hijri year, hijri month)] - yours over the built-in."""
    table = dict(KNOWN)
    try:
        from .store import store_path
        with open(store_path(FILE), encoding="utf-8") as fh:
            for line in fh:
                if line.lstrip().startswith("#"):
                    continue
                bits = line.replace(",", "\t").split()
                if len(bits) < 2:
                    continue
                hy, _, hm = bits[0].partition("-")
                try:
                    key = (int(hy), int(hm))
                    _dt.date.fromisoformat(bits[1])       # readable, or ignored
                except ValueError:
                    continue                 # a bad line leaves the built-in one
                table[key] = bits[1]
    except OSError:
        pass
    out = []
    for (hy, hm), when in table.items():
        try:
            out.append((_dt.date.fromisoformat(str(when)), hy, hm))
        except ValueError:
            continue
    out.sort()
    return out


_TABLE: dict = {}


def _months() -> list:
    """Every month from 1300 to 1600 AH as (first day, year, month).

    Built ONCE, forwards, so it can never go backwards: each month starts where
    it was announced if it was announced, and otherwise one arithmetic month
    after the one before it. An announced date that would make a month shorter
    than 28 days is ignored rather than trusted - that is a typo in the file,
    and a calendar that jumps back a week would file one shoot in two folders.
    """
    said = _starts()
    key = tuple(said)
    if _TABLE.get("key") == key:
        return _TABLE["rows"]
    known = {(y, m): when for when, y, m in said}
    rows = []
    when = _tabular_start(FIRST_YEAR, 1)
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        for month in range(1, 13):
            told = known.get((year, month))
            if told is not None and (not rows or (told - rows[-1][0]).days >= 28):
                when = told
            rows.append((when, year, month))
            when = when + _dt.timedelta(days=month_length(year, month)) \
                if told is None else told + _dt.timedelta(
                    days=month_length(year, month))
    _TABLE["key"], _TABLE["rows"] = key, rows
    _TABLE["days"] = [r[0] for r in rows]
    return rows


def from_gregorian(day, shift: int = 0) -> tuple:
    """(year, month, day) in the Hijri calendar. Never raises.

    `shift` moves the whole calendar by days, for a country whose months start
    a day either side of the table.
    """
    import bisect
    if isinstance(day, _dt.datetime):
        day = day.date()
    if not isinstance(day, _dt.date):
        return (0, 0, 0)
    if shift:
        day = day + _dt.timedelta(days=int(shift))
    rows = _months()
    at = bisect.bisect_right(_TABLE["days"], day) - 1
    if at < 0 or at >= len(rows):
        return (0, 0, 0)                     # outside 1300-1600 AH
    began, year, month = rows[at]
    return year, month, (day - began).days + 1


def name(month: int) -> str:
    return MONTHS[month] if 1 <= month <= 12 else ""


def short(month: int) -> str:
    return SHORT[month] if 1 <= month <= 12 else ""


def written(day, shift: int = 0) -> str:
    """"1443-09-01" - sortable, for a folder name that has to line up."""
    y, m, d = from_gregorian(day, shift)
    return f"{y}-{m:02d}-{d:02d}" if y else ""


def known_until() -> str:
    """The last announced start this app has, so the tab can say it."""
    have = _starts()
    if not have:
        return ""
    began, year, month = have[-1]
    return f"{name(month)} {year} ({began.isoformat()})"
