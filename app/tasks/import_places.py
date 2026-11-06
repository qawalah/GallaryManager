"""Bring a table of place names onto the NAS, once, so sorting by place is offline.

Coordinates are numbers; `Italy / Rome` is a name, and the two are connected by a
table somebody has to supply. This reads GeoNames' free city dump into the app's
own compact store, and after that nothing here ever touches the network again -
no lookups, no accounts, no photograph's position leaving the house.

    https://download.geonames.org/export/dump/cities15000.zip

`cities15000` is towns over 15,000 people - about 26,000 of them, and the right
default: it is small, and it names somewhere within a few kilometres of anywhere
a person actually stands. `cities5000` and `cities1000` are the same file with a
lower cut-off, if a village near you is being called by its bigger neighbour's
name.

Optional second file, `countryInfo.txt`, only replaces the built-in country
names. Everything works without it.

A separate step, like the Timeline import, and for the same reason: when a
future format change breaks the reading it fails HERE, with a message about
importing, rather than halfway through filing photographs where it would look
like the photographs were at fault.
"""

from __future__ import annotations

import os

from app.registry import FilePath, Option, Plan, Result, Row, Task, register
from core import places
from core.store import store_path

STORE = "places.tsv"

WHERE_FROM = ("Download the GeoNames file cities15000.zip (about 2 MB) from "
              "https://download.geonames.org/export/dump/. Put it anywhere the "
              "NAS can see and give its path here. The zip is read as it is.")


def plan(opts) -> Plan:
    p = Plan(task="import-places")
    source = (opts.get("dump") or "").strip().strip('"')
    names = (opts.get("countries") or "").strip().strip('"')
    regions = (opts.get("regions") or "").strip().strip('"')
    info = places.store_info(store_path(STORE))

    if info["ok"]:
        p.notes.append(f"Already imported: {info['towns']:,} towns across "
                       f"{info['countries']:,} countries, from "
                       f"{info['source'] or 'a file'}.")
    else:
        p.notes.append("No place table yet, so sorting by country or city has "
                       "nothing to work from. " + WHERE_FROM)

    if not source:
        p.stats = [("Towns on file", f"{info['towns']:,}" if info["ok"] else "none"),
                   ("Countries", f"{info['countries']:,}" if info["ok"] else "-"),
                   ("Read from", info["source"] or "-")]
        if info["ok"]:
            p.notes.append("Give a path to import a different or newer file. "
                           + WHERE_FROM)
        return p

    if not os.path.isfile(source):
        p.blocked = f"There is no file at {source!r}"
        return p
    for extra in (names, regions):
        if extra and not os.path.isfile(extra):
            p.blocked = f"There is no file at {extra!r}"
            return p

    size = os.path.getsize(source)
    p.rows.append(Row(what="import", name=os.path.basename(source), source=source,
                      target=store_path(STORE),
                      detail=f"{size / 1e6:.1f} MB - read once, then not needed again",
                      data={"dump": source, "countries": names,
                            "regions": regions}))
    p.stats = [("File to read", f"{size / 1e6:.1f} MB"),
               ("Towns currently on file",
                f"{info['towns']:,}" if info["ok"] else "none")]
    if names:
        p.notes.append("Country names will be taken from that second file, "
                       "replacing the built-in ones.")
    p.notes.append("Nothing about your photos is sent anywhere. This is a "
                   "list of towns and their coordinates; the matching happens here.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked or not plan.rows:
        result.details.append(plan.blocked or "Nothing to import.")
        return result
    row = plan.rows[0]
    try:
        got = places.import_dump(
            row.data["dump"], store_path(STORE),
            progress=(lambda i, n, what: progress(i, n, what, "reading"))
            if progress else None,
            names_file=row.data.get("countries") or "",
            regions_file=row.data.get("regions") or "")
        result.done = got["towns"]
        result.stats = [("Towns imported", f"{got['towns']:,}"),
                        ("Countries", f"{got['countries']:,}"),
                        ("Country names replaced", f"{got['named']:,}"),
                        ("Region names", f"{got.get('regions', 0):,}")]
        result.details.append(
            "Sorting into place folders can run now. The original download is not "
            "needed again - the app reads its own copy from here on.")
    except Exception as exc:                       # noqa: BLE001
        result.failed = 1
        result.details.append(str(exc))
        result.details.append(WHERE_FROM)
    return result


register(Task(
    name="import-places",
    line="A table of towns, read once, so places work with no internet.",
    verb="Import",
    unit="place names",
    title="Import place names",
    summary="Reads a table of towns once, so photos can be sorted by country "
            "and city offline.",
    icon="download",
    parent="bydate",
    tab="Place names",
    order=21,
    options=[
        FilePath("dump", "Cities file", default="",
               help="The GeoNames file cities15000.zip (about 2 MB) from "
                    "https://download.geonames.org/export/dump/. Put it "
                    "anywhere the NAS can see and give its path here. The zip "
                    "is read as it is. Blank only shows what is already "
                    "imported."),
        FilePath("countries", "Country names file", default="",
               advanced=True,
               help="The GeoNames file countryInfo.txt, from the same page. "
                    "It replaces the built-in country names, for when a "
                    "country should be named differently as a folder. Blank "
                    "keeps the built-in names."),
        FilePath("regions", "Region names file", default="",
               advanced=True,
               help="The GeoNames file admin1CodesASCII.txt, from the same "
                    "page. It gives region and state names, such as "
                    "Catalonia or California, for the {region} variable in "
                    "folder patterns. Blank leaves {region} out of names."),
    ],
    plan=plan,
    apply=apply,
))
