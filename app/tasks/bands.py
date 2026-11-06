"""Chart bands - where the brackets fall, and what each one is called.

"f/2.8" on a chart is not one aperture. It is a bracket, and somebody chose its
edges. Until now that somebody was whoever wrote this app, for every library
that will ever open it - which is fine until yours is not the library they had
in mind. A landscape library wants f/8 to f/16 split into three and everything
wider in one heap; an available-light library wants exactly the opposite.

Each set is written out one band per line, `name = up to`. A photograph belongs
to the first band whose "up to" it is under, so the edges have to climb - and
the last line catches everything above it whatever number is against it, which
is why the built-in ones end at `1e9`.

Shutter speeds may be written as fractions - `1/500 = 1/400` - because that is
how they are said, and converting eight of them by hand is how one wrong edge
gets typed in.

**A set is taken whole or refused whole.** A half-saved table would put
photographs in the wrong bracket and the chart would still look perfectly
reasonable, which is the worst kind of wrong. Anything that does not add up
comes back with the line number and the old set stays.

Changing a set changes the dashboard, Search and Compare together, straight
away - they all read these at the moment they draw.
"""

from __future__ import annotations

from app.registry import Plan, Result, Row, Task, register
from core import bands as B


def plan(opts, progress=None) -> Plan:
    p = Plan(task="bands")
    p.columns = ["Set", "Bands", "Where they came from"]
    mine = B.saved()
    for name in B.ORDER:
        title, unit, about = B.ABOUT[name]
        rows = B.table(name, mine)
        p.rows.append(Row(
            what="bands", name=name, source="", detail=title,
            cells=[f"{len(rows)} band(s)",
                   "you set them" if B.how(name, mine) == "yours"
                   else "as this app comes"],
            data={"set": name, "title": title, "unit": unit, "about": about,
                  "text": B.as_text(name, mine),
                  "builtin": "\n".join(f"{label} = {B._say(name, top)}"
                                       for label, top in B.BUILTIN[name]),
                  "how": B.how(name, mine)}))
    p.data = {"sets": [{"set": r.data["set"], "title": r.data["title"],
                        "unit": r.data["unit"], "about": r.data["about"],
                        "text": r.data["text"], "builtin": r.data["builtin"],
                        "how": r.data["how"]} for r in p.rows]}
    p.stats = [("Sets of bands", f"{len(B.ORDER)}"),
               ("Changed by you", f"{len(mine)}")]
    p.notes.append("One band per line, written 'name = up to'. A value belongs "
                   "to the first band it is under, so the edges have to climb, "
                   "and the last line catches everything above it.")
    p.notes.append("Nothing is written to a photo. These only decide how "
                   "the counting is grouped, so changing them can never lose "
                   "anything - the same photos are simply put in different "
                   "heaps.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    return Result(details=["This tab only lists. Each set is saved as you "
                           "change it."])


register(Task(
    name="bands",
    line="Where the brackets fall on a chart: which apertures are one bar.",
    reads=(),
    title="Chart bands",
    summary="Sets how apertures, ISOs and focal lengths are grouped into "
            "bars on every chart.",
    icon="hist",
    parent="setup",
    tab="Chart bands",
    editor="bands",
    order=95,
    writes=False,
    options=[],
    plan=plan,
    apply=apply,
))
