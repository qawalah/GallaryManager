"""What a run actually costs the NAS - measured, not guessed.

An app that reads a hundred thousand photographs every fifteen minutes on its
own is an app you are entitled to know the cost of. The temptation is to report
something impressive and vague - "system load 32%" - and the trouble with that
is it is not this app's number. A NAS is running DSM's indexer, Synology Drive,
Photos, whatever else is in a container, and the machine's load average is all
of them together.

So the rule here: **report exactly what this process did, and show the machine's
load beside it as context that is explicitly not ours.**

What can be measured from inside a container, checked rather than assumed:

    resource.getrusage(RUSAGE_SELF)   CPU seconds used, peak memory
    /proc/self/io                     bytes actually read and written, syscalls
    /proc/loadavg                     the WHOLE machine - context, never ours
    /sys/fs/cgroup/...                sometimes; read if there, ignored if not

**The number that matters on a NAS is bytes read, not CPU.** Nothing here is
computation - it is opening files over a disk. And the ratio of the two says so
out loud: twelve seconds of CPU across four minutes of wall clock means the run
spent three and three quarter minutes waiting for the disk, which is the honest
description of what this app does to a NAS.

Everything is best effort. A missing file means that measure is simply absent
rather than zero - "0 MB read" and "I could not tell" are different answers, and
a run must never fail because it could not measure itself.
"""

from __future__ import annotations

import os
import time

from . import meter

try:
    import resource
except ImportError:                                    # Windows
    resource = None                                    # type: ignore


def _io() -> dict:
    """Bytes and syscalls this process has done, from /proc/self/io.

    `read_bytes` is what actually came off the disk; `rchar` includes what came
    from the page cache. Both are worth having: the difference between them is
    how much of a second run was free because the first one warmed the cache,
    which is most of why a re-run feels so much faster.
    """
    out = {}
    try:
        with open("/proc/self/io", "r", encoding="ascii") as fh:
            for line in fh:
                name, _, value = line.partition(":")
                try:
                    out[name.strip()] = int(value.strip())
                except ValueError:
                    pass
    except OSError:
        return {}
    return out


def snapshot() -> dict:
    """Where the counters stand right now. Cheap - two small reads."""
    now = {"at": time.time()}
    if resource is not None:
        try:
            r = resource.getrusage(resource.RUSAGE_SELF)
            now["cpu"] = r.ru_utime + r.ru_stime
            now["peak_kb"] = r.ru_maxrss
        except (OSError, ValueError):
            pass
    got = _io()
    for key in ("read_bytes", "write_bytes", "rchar", "wchar", "syscr", "syscw"):
        if key in got:
            now[key] = got[key]
    # Always present, because this one does not need the container's permission.
    # On a NAS the disk is the whole cost, and a run that cannot say what it read
    # is a run whose cost is unknown - which is what "Read: not measured" meant.
    now.update(meter.snapshot())
    return now


def since(before: dict, after: dict | None = None) -> dict:
    """What happened between two snapshots.

    The counters are per PROCESS and monotonic, so two tasks running at once
    both see the other's work in their own difference. That is not something to
    correct for by guessing - it is said in the wording instead, and the bar at
    the top shows what else was running.
    """
    after = snapshot() if after is None else after
    out = {"seconds": max(0.0, float(after.get("at", 0)) - float(before.get("at", 0)))}
    for key in ("cpu", "read_bytes", "write_bytes", "rchar", "wchar",
                "syscr", "syscw", "own_files", "own_bytes", "own_written"):
        if key in before and key in after:
            out[key] = max(0, after[key] - before[key])
    if "peak_kb" in after:
        out["peak_kb"] = after["peak_kb"]
    return out


def machine() -> dict:
    """The whole NAS: load average, and the container's own limits where DSM
    exposes them. Never this app's doing - context, and labelled as context."""
    out = {}
    try:
        with open("/proc/loadavg", "r", encoding="ascii") as fh:
            bits = fh.read().split()
        out["load1"], out["load5"], out["load15"] = (float(b) for b in bits[:3])
    except (OSError, ValueError, IndexError):
        pass
    for name, key in (("/sys/fs/cgroup/memory.current", "memory_bytes"),
                      ("/sys/fs/cgroup/memory.max", "memory_limit")):
        try:
            with open(name, "r", encoding="ascii") as fh:
                text = fh.read().strip()
            out[key] = None if text == "max" else int(text)
        except (OSError, ValueError):
            pass
    try:
        out["cores"] = os.cpu_count()
    except Exception:                                  # noqa: BLE001
        pass
    return out


# ------------------------------------------------------------------- saying it

def bytes_said(n) -> str:
    if n is None:
        return "not measured"
    n = float(n)
    for unit, size in (("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if n >= size:
            return f"{n / size:.1f} {unit}" if n < size * 100 else \
                   f"{n / size:.0f} {unit}"
    return f"{int(n):,} bytes"


def clock(seconds) -> str:
    seconds = float(seconds or 0)
    if seconds < 90:
        return f"{seconds:.1f}s"
    if seconds < 5400:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.1f} hours"


def disk(cost: dict) -> str:
    """What this run asked of the disk, in the words that matter on a NAS.

    Files first, then bytes, because on a spinning disk the seeks are what you
    wait for: ten thousand files of 60 KB is six hundred megabytes and also ten
    thousand seeks, and a change that halves the bytes while keeping the file
    count has not made the run much shorter.
    """
    if not cost or "own_files" not in cost:
        return "not measured"
    bits = [f"{cost['own_files']:,} files", bytes_said(cost.get("own_bytes"))]
    if cost.get("own_written"):
        bits.append(f"{bytes_said(cost['own_written'])} written")
    return ", ".join(bits)


def describe(cost: dict) -> str:
    """One line a person can act on.

    Disk first, deliberately. Nothing here is computation - it is opening files
    over a disk - so the number that predicts how long a run takes, and the only
    one a bigger interval changes, is how many files it had to open. CPU comes
    after it, and only when there is enough of it to be worth dividing: "0.3s,
    0s of that working" tells you nothing and makes the line harder to read.
    """
    if not cost:
        return "not measured"
    bits = [clock(cost.get("seconds"))]
    if "own_files" in cost:
        bits.append(f"opened {cost['own_files']:,} files")
        bits.append(f"read {bytes_said(cost.get('own_bytes'))}")
    elif "read_bytes" in cost:
        bits.append(f"read {bytes_said(cost['read_bytes'])}")
    if cost.get("own_written"):
        bits.append(f"wrote {bytes_said(cost['own_written'])}")
    elif cost.get("write_bytes"):
        bits.append(f"wrote {bytes_said(cost['write_bytes'])}")
    if "cpu" in cost and float(cost.get("seconds") or 0) >= 2:
        bits.append(f"{cost['cpu']:.0f}s of that working")
    return ", ".join(bits)


def waiting_share(cost: dict) -> float | None:
    """How much of the time was spent NOT computing, 0 to 1.

    On a NAS this is nearly all of it, and that is the point: the cost of this
    app is the disk, so the lever that helps is doing it less often, not doing
    it faster.
    """
    seconds = float(cost.get("seconds") or 0)
    if seconds <= 0 or "cpu" not in cost:
        return None
    return max(0.0, min(1.0, 1.0 - float(cost["cpu"]) / seconds))
