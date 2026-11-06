"""The folders you last used, so nothing has to be typed twice.

Setup already fills the three trees into every form. This is the other half: the
folder you actually pointed a task at last time. They are different questions.
Setup says "the library is here"; this says "last time you culled, you culled
Italy 2024" - and typing that path again, correctly, is exactly the chore the
Browse button only half solved.

Written when a plan is made rather than when one is applied, because a plan is
already a deliberate act: you typed a path and pressed the button. A report-only
task like Library never applies anything and would otherwise never remember
where you were looking.

Two rules keep it from being worse than nothing:

- **Only a folder that existed.** Remembering a typo means every future form
  opens with the typo in it.
- **It is a starting point, never a lock.** A remembered value fills the box and
  can be typed straight over, and if the folder has since gone the setting from
  Setup fills it instead. A form that opens with a path that no longer exists is
  a form that lies to you.
- **Setup's own value is not a choice.** A run on the box as it opened - the
  library, because Setup said so - is not "where you were working", and
  remembering it meant Search went on opening on the old library after Setup
  named a new one, reload or not. And when a tree moves, what was remembered
  inside the old one is forgotten with it (`tree_moved`).
- **A pick is kept with the Setup it was made under.** Beside each remembered
  folder is what Setup said for that box at the time (`key@setup`), so a
  pick inside a library that has since moved is known for what it is
  however the settings changed - and a folder picked outside the library,
  an Inbox say, is still yours after it moves (`meant`).
"""

from __future__ import annotations

import json
import os

from .store import store_path

FILE = "recent.json"
LIMIT = 400                  # plenty for a lifetime of tasks; keeps the file small
UNDER = "@setup"             # beside a key: what Setup said when it was picked


def _path() -> str:
    return store_path(FILE)


def load() -> dict:
    """Everything remembered. Never raises - a damaged file just means nothing."""
    try:
        with open(_path(), "r", encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def get(task: str, option: str, must_exist: bool = True) -> str:
    """What was last used here, if it is still a folder."""
    value = load().get(f"{task}.{option}")
    if not isinstance(value, str) or not value:
        return ""
    if must_exist and not os.path.isdir(value):
        return ""
    return value


def _write(current: dict) -> None:
    tmp = _path() + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(current, fh, indent=2, sort_keys=True)
    os.replace(tmp, _path())


def _same(a: str, b: str) -> bool:
    from . import paths
    a, b = str(a or "").strip(), str(b or "").strip()
    return bool(a and b) and (os.path.normcase(paths.normalise(a))
                              == os.path.normcase(paths.normalise(b)))


def meant(task: str, option: str, now: str, must_exist: bool = True) -> str:
    """What was last used here, as far as it still means what it meant.

    `now` is what Setup says for this box today ("" for a box that names no
    setting, which is simply `get`). A folder picked inside the tree Setup
    named at the time is dropped once that tree has moved and the folder is
    not inside the new one: it was a folder of the old library. One picked
    anywhere else is kept.

    A pick from before the Setup value was written beside it (3.12.0 and
    earlier) is only trusted inside today's tree. Those versions also
    remembered Setup's own library as a pick, so an old one outside today's
    library cannot be told apart from the library you moved away from - which
    is exactly what the Library tool went on opening on. Picking it again
    records it properly.
    """
    from . import paths
    value = get(task, option, must_exist=must_exist)
    now = str(now or "").strip()
    if not value or not now:
        return value
    then = load().get(f"{task}.{option}{UNDER}")
    lines = [x.strip() for x in value.split("\n") if x.strip()]
    if not isinstance(then, str):
        kept = [x for x in lines if paths.under(x, now)]
    elif not then.strip() or _same(then, now):
        kept = lines
    else:
        kept = [x for x in lines
                if not paths.under(x, then) or paths.under(x, now)]
    return "\n".join(kept)


def remember_text(task: str, option: str, value: str, setup: str = "") -> None:
    """Keep a value that is not a single folder - a list of them, say.

    Entries that no longer exist are dropped as they are written, so a list of
    folders to leave out shrinks by itself when one is deleted rather than
    quietly matching nothing forever.
    """
    lines = [x.strip() for x in str(value or "").replace(",", "\n").splitlines()]
    keep = [x for x in lines if x and (os.path.isdir(x) or (os.sep not in x
                                                            and "/" not in x))]
    if len(keep) == 1 and _same(keep[0], setup):
        keep = []                    # Setup's value, as the box opened: not a pick
    key = f"{task}.{option}"
    try:
        current = load()
        if keep:
            current[key] = "\n".join(dict.fromkeys(keep))
            current[key + UNDER] = str(setup or "")
        else:
            current.pop(key, None)
            current.pop(key + UNDER, None)
        _write(current)
    except (OSError, ValueError):
        pass


def remember(task: str, values: dict, setup: dict | None = None) -> None:
    """Keep the folder values of one run. Best effort - never raises.

    Failing to remember a path is not worth interrupting a task for. The worst
    case is that a box opens empty, which is where it started.

    `setup` is what Setup says for each option that names a setting. A value
    that is exactly that is not remembered, and anything remembered for that
    box before is dropped: the box goes back to following Setup. Anything
    else is kept with that Setup value beside it, for `meant`.
    """
    setup = setup or {}
    keep, drop = {}, []
    for name, value in (values or {}).items():
        if not isinstance(value, str) or not value.strip():
            continue
        if _same(value, setup.get(name, "")):
            drop += [f"{task}.{name}", f"{task}.{name}{UNDER}"]
            continue
        if not os.path.isdir(value):
            continue
        keep[f"{task}.{name}"] = value
        if name in setup:
            keep[f"{task}.{name}{UNDER}"] = str(setup[name] or "")
    if not keep and not drop:
        return
    try:
        current = load()
        if not keep and not any(k in current for k in drop):
            return
        for key in drop:
            current.pop(key, None)
        current.update(keep)
        if len(current) > LIMIT:                 # oldest keys first, roughly
            for key in list(current)[:len(current) - LIMIT]:
                current.pop(key, None)
        _write(current)
    except (OSError, ValueError):
        pass


def tree_moved(old: str, new: str) -> int:
    """A tree in Setup moved: forget what was remembered inside the old one.

    A folder of the old library is not "where you were working" once the
    library is somewhere else - it is the old library, and a form opening on
    it is a form still pointed at the library you just left. What is also
    inside the new tree (the library moved one folder up, say) is kept.
    Says how many it forgot.
    """
    from . import paths
    old = str(old or "").strip()
    if not old:
        return 0
    new = str(new or "").strip()

    def stays(folder: str) -> bool:
        folder = folder.strip()
        if not folder or not paths.under(folder, old):
            return True
        return bool(new) and paths.under(folder, new)

    current = load()
    changed = 0
    for key, value in list(current.items()):
        if not isinstance(value, str) or key.endswith(UNDER):
            continue                 # what Setup said then stays what it said
        lines = [x for x in value.split("\n") if x.strip()]
        kept = [x for x in lines if stays(x)]
        if len(kept) == len(lines):
            continue
        changed += 1
        if kept:
            current[key] = "\n".join(kept)
        else:
            current.pop(key, None)
    if changed:
        try:
            _write(current)
        except (OSError, ValueError):
            pass
    return changed
