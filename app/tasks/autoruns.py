"""What the automation did while nobody was watching - and what it cost.

The point of a background loop is that you stop thinking about it, and the price
of that is you no longer know whether it is working. The Automation tab says
what it WILL do; this says what it has done.

Two things it shows that the History tab cannot. It is only the runs the app
started ITSELF - the ones you did not press and therefore the ones worth
checking - and it says what each one took off the NAS: how long, how much of
that was actually working rather than waiting on the disk, and how many bytes
were read.

That last number is the honest answer to "what is this app doing to my NAS". It
is measured per run rather than estimated, and it is this process's own
counters, not the machine's: a NAS runs DSM's indexer, Drive, Photos and
whatever else is in a container, and the load average is all of them together.
The load average is shown - in the header - as context, and never as ours.

Looking at this tab is what clears the unread mark on Automation. Not opening
the Automation tab: going there to change a setting is not the same thing as
having read what happened.
"""

from __future__ import annotations

import time

from app.registry import Choice, Number, Plan, Result, Row, Task, register
from core import load, runlog

WHICH = [("results", "Passes that did something"),
         ("all", "Every pass")]


def _ago(when: float) -> str:
    gap = max(0, time.time() - when)
    if gap < 90:
        return "just now"
    if gap < 5400:
        return f"{int(gap // 60)} min ago"
    if gap < 172800:
        return f"{int(gap // 3600)} hours ago"
    return f"{int(gap // 86400)} days ago"


def plan(opts) -> Plan:
    p = Plan(task="autoruns")
    limit = int(opts.get("limit") or 60)
    only_results = str(opts.get("which") or "results") == "results"

    runs = [r for r in runlog.recent(limit=600)
            if str(r.get("by") or "") == "automation"]
    if only_results:
        runs = [r for r in runs
                if int(r.get("done") or 0) or int(r.get("failed") or 0)]

    p.columns = ["When", "Step", "What it did", "Files opened", "Read", "Took"]
    seconds = read = cpu = through = 0.0
    opened = 0
    kernel = 0.0
    # Whether the disk figure is a real zero or a missing one. "It read nothing
    # off the disk" and "I could not tell" are different answers and only one of
    # them is good news. `own_*` is this app counting its own reads and is always
    # there; `read_bytes` is the kernel's and needs a container allowed to see
    # /proc/self/io, which Abu's is not.
    measured = False
    kernel_measured = False
    for run in runs[:limit]:
        cost = dict(run.get("cost") or {})
        seconds += float(cost.get("seconds") or run.get("seconds") or 0)
        opened += int(cost.get("own_files") or 0)
        read += float(cost.get("own_bytes") or 0)
        kernel += float(cost.get("read_bytes") or 0)
        through += float(cost.get("rchar") or 0)
        cpu += float(cost.get("cpu") or 0)
        measured = measured or "own_files" in cost
        kernel_measured = kernel_measured or "read_bytes" in cost
        did = f"{int(run.get('done') or 0):,} done"
        if int(run.get("failed") or 0):
            did += f", {int(run.get('failed')):,} failed"
        if not int(run.get("done") or 0) and not int(run.get("failed") or 0):
            did = "nothing to do"
        p.rows.append(Row(
            what="run", name=_ago(float(run.get("when") or 0)),
            source=(list(run.get("folders", {}).values()) or [""])[0], target="",
            detail=f"{run.get('task')}: {did} - {load.describe(cost)}",
            cells=[str(run.get("task") or ""), did,
                   f"{int(cost['own_files']):,}" if "own_files" in cost
                   else "not measured",
                   load.bytes_said(cost.get("own_bytes"))
                   if "own_files" in cost else "not measured",
                   load.clock(cost.get("seconds") or run.get("seconds"))],
            data={"when": run.get("when")}))

    waiting = load.waiting_share({"seconds": seconds, "cpu": cpu})
    # Files first. On a spinning disk the seek is what you wait for, so the
    # count predicts how long a run takes far better than the byte total does:
    # ten thousand 60 KB files is six hundred megabytes and ten thousand seeks.
    p.stats = [
        ("Runs shown", f"{len(p.rows):,}"),
        ("FILES OPENED", f"{opened:,}" if measured else "not measured"),
        ("What that read", load.bytes_said(read) if measured else "not measured"),
        ("Time they took", load.clock(seconds)),
        ("  of that, actually working", load.clock(cpu)),
        ("  waiting on the disk", "-" if waiting is None else f"{waiting * 100:.0f}%"),
    ]
    if measured and seconds > 0:
        p.stats.append(("Files a second", f"{opened / seconds:,.0f}"))
    if kernel_measured:
        # The kernel's own figure, where the container is allowed to see it.
        # It counts bytes off the DEVICE, so it is smaller than ours whenever
        # the page cache answered - and that gap is why a second pass is quick.
        p.stats.append(("Off the device itself", load.bytes_said(kernel)))
        p.stats.append(("  the rest came from memory",
                        load.bytes_said(max(0.0, through - kernel))))
    here = load.machine()
    if "load1" in here:
        p.stats.append(("The NAS right now",
                        f"load {here['load1']:.2f} over "
                        f"{here.get('cores', '?')} core(s) - the WHOLE machine"))

    p.notes.append(
        "These are the runs the app started itself. The ones you pressed are on "
        "the History button at the top - both are in the same log, and this is "
        "the half nobody is watching when it happens.")
    p.notes.append(
        "The disk figures are counted by the app itself, at every place it "
        "opens a photo, a sidecar or a header - so they are there whatever "
        "the container is allowed to see. They are this app's reads only: a NAS "
        "is running DSM's indexer, Drive and Photos as well, and attributing "
        "those here would be a number that looks precise and is wrong.")
    p.notes.append(
        "FILES OPENED is the one to watch. Nothing here is computation - it is "
        "opening files over a disk - and on a spinning disk you wait for the "
        "seek rather than for the bytes. A run that opens ten thousand files "
        "takes about the same time whether they are 60 KB or 6 MB each.")
    if waiting is not None and waiting > 0.5:
        p.notes.append(
            f"{waiting * 100:.0f}% of that time was spent waiting on the disk "
            f"rather than computing, which is the normal shape of this work and "
            f"the useful thing to know: the lever that reduces the load is a "
            f"longer interval on the Automation tab, not a faster NAS.")
    if measured and p.rows:
        p.notes.append(
            f"That averages {opened / len(p.rows):,.0f} files opened per run. A "
            f"photo whose size and date have not moved since the last pass "
            f"is answered from the facts cache and never opened at all, so this "
            f"number should fall away to almost nothing once the library has "
            f"been read through once.")
    if kernel_measured and through > kernel * 2 and kernel >= 0:
        p.notes.append(
            "Rather more was read than came off the disk: the difference came "
            "out of the machine's page cache, which costs nothing. That is why "
            "a second pass shortly after the first is nearly free, and why the "
            "first one after a reboot is not.")
    if not runs:
        p.notes.append(
            "Nothing yet. Either the automation has not run, or it has run and "
            "found nothing changed - which is the quiet, correct state and is "
            "what the second view above shows.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    result.details.append("This tab only ever looks.")
    return result


register(Task(
    name="autoruns",
    title="Automation runs",
    summary="Lists each pass of the automation loop, what it did and what it "
            "cost. Nothing is changed.",
    icon="history",
    parent="automation",
    tab="Runs",
    writes=False,
    order=71,
    options=[
        Choice("which", "Which passes", default="results", choices=WHICH, tabs=True,
               help="Which passes to list. Most passes find nothing changed, "
                    "so by default only the passes that did something are "
                    "shown."),
        Number("limit", "Passes to show", default=60, minimum=5, maximum=400,
               help="The number of most recent passes to list, newest first. "
                    "5 to 400, default 60. The History button at the top has "
                    "the whole log."),
    ],
    plan=plan,
    apply=apply,
))
