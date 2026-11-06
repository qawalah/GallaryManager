"""The command line: one way in, for you and for the NAS scheduler.

Every task is reachable here without a line of per-task code, because each one
declares its own options. `--help` for a task is generated from those
declarations, so it cannot drift out of date with what the task actually accepts.

Planning is the default. Nothing is written unless --apply is given, and a task
that refuses to run says why rather than doing half a job.
"""

from __future__ import annotations

import difflib
import os
import sys
import time

from app import registry as R
import app.tasks  # noqa: F401  - importing registers every task


def _usage(code: int = 1) -> int:
    print("Photo Manager\n")
    print("  run <tool> [--option value ...]     say what would happen")
    print("  run <tool> ... --apply              and then do it")
    print("  run <tool> --help                   what this tool accepts")
    print("  run --list                          every tool\n")
    print("Tasks:")
    for t in R.all_tasks():
        mark = "" if t.writes else "   (only ever reports)"
        print(f"  {t.name:<12} {t.summary}{mark}")
    return code


def _task_help(t: R.Task) -> int:
    # Through describe(), like the page, so wording edited on Setup > Wording
    # reads the same here as it does in the browser.
    said = t.describe()
    print(f"{said['title']} - {said['summary']}\n")
    if not t.writes:
        print("  This tool only reports. It never writes.\n")
    print("Options:")
    for o, d in zip(t.options, said["options"]):
        line = f"  --{o.name:<12} {d['label']}"
        if d.get("choices"):
            line += "  [" + " | ".join(str(c["value"]) for c in d["choices"]) + "]"
        if o.default not in (None, ""):
            line += f"  (default {o.default})"
        print(line)
        if d.get("help"):
            print(f"                 {d['help']}")
    return 0


def parse_args(argv: list[str]) -> dict:
    """--name value, --name=value, or --flag on its own."""
    opts: dict = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if not a.startswith("--"):
            i += 1
            continue
        name = a[2:]
        if "=" in name:
            name, value = name.split("=", 1)
            opts[name] = value
        elif i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            opts[name] = argv[i + 1]
            i += 1
        else:
            opts[name] = True
        i += 1
    return opts


# Accepted by every task, on top of the options it declares.
COMMON = {"apply", "help"}


def problems(task: R.Task, raw: dict) -> list[str]:
    """What is wrong with the options as typed, before anything is planned.

    Both used to be dropped without a word. A misspelt `--foldr` left the task
    on Setup's whole library; an unknown `--which` ran the FIRST flow. With
    --apply on a schedule, nobody is watching to notice either.
    """
    out = []
    names = {o.name for o in task.options}
    for given in raw:
        if given in names or given in COMMON:
            continue
        near = difflib.get_close_matches(given.replace("-", "_"),
                                         sorted(names), n=1)
        hint = f" - did you mean --{near[0]}?" if near else ""
        out.append(f"there is no option --{given}{hint}")
    for o in task.options:
        if not isinstance(o, R.Choice) or o.name not in raw:
            continue
        value = raw[o.name]
        if value is True or value in (None, ""):
            continue
        offered = [c if isinstance(c, (tuple, list)) else (c, str(c))
                   for c in o.offered()]
        if any(str(c[0]) == str(value) for c in offered):
            continue
        listed = "\n".join(f"      {c[0]:<16} {c[1] if len(c) > 1 else ''}".rstrip()
                           for c in offered if str(c[0]) != "")
        out.append(f"--{o.name} {value!r} is not one of these:\n"
                   + (listed or "      (there are none yet)"))
    return out


MARKS = [("separated", "RAW"), ("located", "GEO"), ("rated", "*"),
         ("previews", "PRV"), ("culled", "X")]


def _tree(plan: R.Plan, limit: int = 300) -> None:
    """The folder tree, in a terminal. Same marks as the page, spelled out.

    Worth having here and not only in the browser: a scheduled task emails this
    output, and "which shoots are half finished" is exactly the thing worth
    getting in an email once a week.
    """
    if not plan.tree:
        return
    print(f"\n  {'folder':<40}{'photos':>7}{'raws':>7}   " +
          "  ".join(f"{short:>3}" for _key, short in MARKS))
    for node in plan.tree[:limit]:
        name = ("  " * node["depth"]) + node["name"]
        raws = (f"{node['raws_here']}!" if node["raws_here"]
                else (str(node["raws_apart"]) if node["raws_apart"] else "-"))
        cells = []
        for key, short in MARKS:
            state = node["marks"].get(key, "empty")
            cells.append({"all": "yes", "some": "part", "none": "no",
                          "empty": "-"}.get(state, "-"))
        print(f"  {name[:40]:<40}{node['photos'] or '-':>7}{raws:>7}   " +
              "  ".join(f"{c:>3}" for c in cells))
    if len(plan.tree) > limit:
        print(f"      ... and {len(plan.tree) - limit} more folders")
    print("\n  yes = all of them, part = some (unfinished), no = none, ! = still "
          "in the library")


def _show(plan: R.Plan, limit: int = 40) -> None:
    for label, value in plan.stats:
        print(f"  {label:<28} {value}")
    _tree(plan)
    if plan.notes:
        print()
        for n in plan.notes:
            print(f"  {n}")
    if plan.rows:
        print(f"\n  what would happen ({len(plan.rows)}):")
        for r in plan.rows[:limit]:
            flag = "~" if r.approximate else " "
            print(f"    {flag} {r.name:<28} {r.detail}")
        if len(plan.rows) > limit:
            print(f"      ... and {len(plan.rows) - limit} more")
    if plan.skipped:
        print(f"\n  left alone ({len(plan.skipped)}):")
        for name, why in plan.skipped[:limit]:
            print(f"      {name:<28} {why}")
        if len(plan.skipped) > limit:
            print(f"      ... and {len(plan.skipped) - limit} more")
    if plan.errors:
        print(f"\n  could not be read ({len(plan.errors)}):")
        for e in plan.errors[:limit]:
            print(f"      {e}")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return _usage()
    if argv[0] in ("--list", "-h", "--help", "help"):
        # Asked for, so a success: the DSM scheduler and run.bat both read a
        # non-zero status as a failed job.
        return _usage(0)

    name = argv[0]
    task = R.get(name)
    if task is None:
        print(f"There is no tool called {name!r}.\n")
        return _usage()

    raw = parse_args(argv[1:])
    if "help" in raw:
        return _task_help(task)

    wrong = problems(task, raw)
    if wrong:
        for line in wrong:
            print(f"Cannot run: {line}")
        print(f"\nNothing was planned and nothing was written. "
              f"`{task.name} --help` lists what it accepts.")
        return 2

    do_it = bool(raw.pop("apply", False))

    print(f"\n{task.title}")
    print("-" * 60)
    plan = task.make_plan(raw)
    if plan.blocked:
        # still show what was found. "It cannot run" and "here is what it saw"
        # are different answers, and hiding the second makes the first unhelpful.
        print(f"  Cannot run: {plan.blocked}\n")
        _show(plan)
        return 2
    _show(plan)

    if not do_it:
        print("\n  Nothing was written. Add --apply to apply it.\n")
        return 0
    if not task.writes:
        print("\n  This tool only reports, so there is nothing to apply.\n")
        return 0
    if not plan.rows:
        print("\n  Nothing to do.\n")
        return 0

    print(f"\n  Applying to {len(plan.rows)} item(s)...")
    began = time.time()
    result = task.apply(plan)
    # A scheduled run at 3am has nobody watching it. The log is the only place
    # "what happened to this folder" can be answered afterwards, so the command
    # line records exactly what the web page does.
    try:
        from core import runlog
        runlog.record(task.name, task.loggable(plan.opts), result,
                      time.time() - began)
        try:
            from core import reindex
            if task.writes and plan.rows:
                reindex.remember(reindex.folders_touched(plan.rows))
        except Exception:                          # noqa: BLE001
            pass
    except Exception:                              # noqa: BLE001
        pass
    print(f"  done: {result.done}   failed: {result.failed}")
    for d in result.lines()[:int(os.environ.get("DETAIL_LINES", "20"))]:
        print(f"      {d}")
    return 1 if result.failed else 0


if __name__ == "__main__":
    sys.exit(main())
