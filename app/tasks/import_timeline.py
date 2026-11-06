"""Bring a Google Timeline export into the app's own store, once.

Deliberately a separate step rather than something done quietly on every run. A
76 MB export takes real time to read, and doing it repeatedly to answer "where
was I on this afternoon in 2022" is waste. More importantly, when a future export
format breaks the conversion it fails HERE, with a message about importing,
instead of halfway through placing photos where it would look like the photos
were at fault.

After this the original export is not needed again.
"""

from __future__ import annotations

import os

from app.registry import Option, Plan, Result, Row, Task, register
from core import timeline
from core.store import store_path

STORE = "timeline.tsv"


def plan(opts) -> Plan:
    p = Plan(task="import-timeline")
    export = (opts["export"] or "").strip()
    info = timeline.store_info(store_path(STORE))

    if info.ok and info.count:
        p.notes.append(f"Already imported: {info.count:,} positions, "
                       f"{info.first[:10]} to {info.last[:10]} "
                       f"(imported {info.imported}).")
    else:
        p.notes.append("Nothing imported yet.")

    if not export:
        p.stats = [("Positions on file", f"{info.count:,}" if info.ok else "none"),
                   ("Earliest", info.first[:10] if info.first else "-"),
                   ("Latest", info.last[:10] if info.last else "-")]
        p.notes.append("Give the path to your Timeline.json to import or re-import it.")
        return p

    if not os.path.isfile(export):
        p.blocked = f"There is no file at {export!r}"
        return p

    size = os.path.getsize(export)
    p.rows.append(Row(what="import", name=os.path.basename(export), source=export,
                      target=store_path(STORE),
                      detail=f"{size / 1e6:.0f} MB - read once, then not needed again",
                      data={"export": export}))
    p.stats = [("Export to read", f"{size / 1e6:.0f} MB"),
               ("Positions currently on file", f"{info.count:,}" if info.ok else "none")]
    if size < 1_000_000:
        p.notes.append(
            "That file is unusually small. A Google TAKEOUT export of Timeline "
            "contains no locations at all any more - the real export comes off the "
            "phone: Maps > your profile > Your Timeline > ... > Location & privacy "
            "settings > Export Timeline data.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked or not plan.rows:
        result.details.append(plan.blocked or "Nothing to import.")
        return result
    export = plan.rows[0].data["export"]
    try:
        info = timeline.import_export(
            export, store_path(STORE),
            progress=(lambda i, n, p: progress(i, n, os.path.basename(p), "reading"))
            if progress else None)
        result.done = info.count
        result.stats = [("Positions imported", f"{info.count:,}"),
                        ("Earliest", info.first[:10]),
                        ("Latest", info.last[:10])]
        result.details.append(
            "Your original export is not needed again - the app reads its own copy "
            "from now on, and only the dates it needs for the photos in front of it.")
        result.details.append("Re-import whenever you take a fresh export from your phone.")
    except Exception as exc:                       # noqa: BLE001
        result.failed = 1
        result.details.append(str(exc))
    return result


register(Task(
    name="import-timeline",
    line="Read your phone's Timeline export into the app, once.",
    verb="Import",
    unit="days",
    title="Import Google Timeline",
    summary="Reads a Google Timeline export once into the app's own store.",
    icon="download",
    parent="geotag",
    tab="Import timeline",
    order=15,
    options=[
        Option("export", "Timeline.json path", default="",
               help="The path to the Timeline.json exported from your phone. "
                    "In Google Maps: profile > Your Timeline > ... > "
                    "Location & privacy settings > Export Timeline data. "
                    "Blank only shows what is already imported."),
    ],
    plan=plan,
    apply=apply,
))
