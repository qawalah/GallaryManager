"""Where a piece of a tool's wording is written in the source.

The Wording tab's export names, for every edited line, the file and line it
came from, so whoever merges the edits back knows exactly where each one goes.
`tools/merge_wording.py` uses the same answer to do the merge itself. Both
need the string *literal*, not a text search: "RAW tree" is written in a dozen
places, and the one that matters is the label of this option of this tool.

Read with `ast`, which gives each literal's exact span, implicit
concatenation across lines included. Nothing is imported or run. A literal is
only ever returned when it says exactly what the tool ships, so a wrong guess
comes back as "not found" rather than as a line that would be overwritten.
Text built at run time (the five colour labels' options are made in a loop)
has no literal, and is reported as such.
"""

from __future__ import annotations

import ast
import glob
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OPTION_CLASSES = {"Option", "Folder", "Folders", "FilePath", "Pattern", "Flag",
                  "Secret", "Number", "Choice"}

_INDEX: dict = {}


def files() -> list[str]:
    """Every source file a tool's wording can be written in."""
    return (sorted(glob.glob(os.path.join(HERE, "app", "tasks", "*.py")))
            + [os.path.join(HERE, "app", "registry.py")]
            + sorted(glob.glob(os.path.join(HERE, "core", "*.py"))))


def relative(path: str) -> str:
    return os.path.relpath(path, HERE).replace(os.sep, "/")


def _name_of(func) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def kw(call: ast.Call, name: str):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


def text_of(node):
    return node.value if isinstance(node, ast.Constant) and \
        isinstance(node.value, str) else None


def index(path: str) -> dict:
    """One file, read once per change: its tree, its Task(...) calls by tool
    name, its Option(...) calls by option name, and its two-element tuples."""
    stamp = os.stat(path).st_mtime_ns
    hit = _INDEX.get(path)
    if hit and hit["stamp"] == stamp:
        return hit
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source)
    got = {"stamp": stamp, "tree": tree, "source": source, "tasks": {},
           "options": {}, "pairs": [], "names": {}, "parents": {},
           "strings": {}}
    for node in ast.walk(tree):
        said = text_of(node)
        if said:
            got["strings"].setdefault(said, []).append(node)
        for child in ast.iter_child_nodes(node):
            got["parents"][id(child)] = node
        if isinstance(node, ast.Call):
            what = _name_of(node.func)
            if what == "Task":
                name = text_of(kw(node, "name"))
                if name:
                    got["tasks"][name] = node
            elif what in OPTION_CLASSES:
                first = text_of(node.args[0]) if node.args else \
                    text_of(kw(node, "name"))
                if first:
                    got["options"].setdefault(first, []).append(node)
        elif isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) >= 2:
            first = node.elts[0]
            if isinstance(first, ast.Constant) and text_of(node.elts[1]) is not None:
                got["pairs"].append((str(first.value), node.elts[1]))
    for top in tree.body:
        if isinstance(top, ast.Assign):
            for t in top.targets:
                if isinstance(t, ast.Name):
                    got["names"][t.id] = top.value
    _INDEX[path] = got
    return got


def parent(path: str, node):
    return index(path)["parents"].get(id(node))


def _resolve(path: str, node):
    """A literal, following one plain module-level name to it."""
    if isinstance(node, ast.Name):
        return index(path)["names"].get(node.id, node)
    return node


def task_call(name: str):
    """(path, the Task(...) call) for the tool called `name`, or (None, None)."""
    for path in sorted(glob.glob(os.path.join(HERE, "app", "tasks", "*.py"))):
        call = index(path)["tasks"].get(name)
        if call is not None:
            return path, call
    return None, None


def _inside(node, outer) -> bool:
    return (outer is not None
            and (node.lineno, node.col_offset) >= (outer.lineno, outer.col_offset)
            and (node.end_lineno, node.end_col_offset)
            <= (outer.end_lineno, outer.end_col_offset))


def _order(task: str) -> list[str]:
    """The tool's own file first, then the registry (which adds the shared
    Skip box), then everything else."""
    path, _ = task_call(task)
    reg = os.path.join(HERE, "app", "registry.py")
    first = [p for p in (path, reg) if p]
    return first + [p for p in files() if p not in first]


def option_calls(task: str, option: str) -> list:
    """[(path, Option call)] that could declare this option of this tool, the
    most likely first: inside the tool's own Task(...) call, then elsewhere in
    its file, then in other files."""
    path, call = task_call(task)
    out = []
    for where in _order(task):
        found = index(where)["options"].get(option, [])
        if where == path:
            found = sorted(found, key=lambda c: not _inside(c, call))
        out.extend((where, c) for c in found)
    return out


def _matches(path, node, shipped):
    node = _resolve(path, node) if node is not None else None
    said = text_of(node)
    if said is None:
        return None
    if shipped is not None and said != shipped:
        return None
    return node


def locate(key: str, shipped: str | None = None) -> list:
    """[(path, literal node)] for one wording key, or [] when no literal says
    exactly `shipped` (when given).

    A group heading is written once per option that carries it, so a group
    key returns every one of them within that tool.
    """
    from core import wording
    got = wording.parse(key)
    if not got:
        return []
    task, kind = got["task"], got["kind"]
    if task == "guide":
        return _guide(key, got["value"], shipped)
    if task == "page":
        return []                       # JSON, not Python: app/pagetext.where
    if kind in wording.FIELDS:
        path, call = task_call(task)
        if call is None:
            return []
        node = _matches(path, kw(call, kind), shipped)
        return [(path, node)] if node is not None else _fallback(task, shipped)
    if kind == "group":
        out = []
        path, call = task_call(task)
        for where, c in [(p, c) for p, c in _all_option_calls(task)]:
            g = kw(c, "group")
            if text_of(g) == got["value"]:
                out.append((where, g))
        return out
    if kind == "choice":
        for where, c in option_calls(task, got["option"]):
            choices = kw(c, "choices")
            pool = []
            if choices is not None:
                resolved = _resolve(where, choices)
                pool = [(str(e.elts[0].value), e.elts[1]) for e in ast.walk(resolved)
                        if isinstance(e, (ast.Tuple, ast.List)) and len(e.elts) >= 2
                        and isinstance(e.elts[0], ast.Constant)
                        and text_of(e.elts[1]) is not None]
            for value, node in pool + index(where)["pairs"]:
                if value == got["value"] and (shipped is None
                                              or text_of(node) == shipped):
                    return [(where, node)]
        return _fallback(task, shipped)
    for where, c in option_calls(task, got["option"]):
        if kind == "label":
            node = c.args[1] if len(c.args) > 1 else kw(c, "label")
        else:
            node = kw(c, "help")
        node = _matches(where, node, shipped)
        if node is not None:
            return [(where, node)]
    return _fallback(task, shipped)


def _guide(key: str, name: str, shipped) -> list:
    """A Guide page's title or one paragraph, in app/page.py's GUIDE list,
    the page found by the slug of its title."""
    from app.pagetext import slug
    path = os.path.join(HERE, "app", "page.py")
    found = index(path)["names"].get("GUIDE")
    if not isinstance(found, ast.List):
        return []
    for page in found.elts:
        if not isinstance(page, ast.Dict):
            continue
        said = {text_of(k): v for k, v in zip(page.keys, page.values)}
        if slug(text_of(said.get("title")) or "") != name:
            continue
        if key.endswith(".title"):
            node = said.get("title")
        else:
            n = int(key.rsplit(".", 1)[1])
            body = said.get("body")
            node = (body.elts[n - 1] if isinstance(body, ast.List)
                    and 0 < n <= len(body.elts) else None)
        node = _matches(path, node, shipped) if node is not None else None
        return [(path, node)] if node is not None else []
    return []


def _all_option_calls(task: str) -> list:
    """Every Option call of this tool: inside its Task(...) call, or the first
    declaration of each of its options elsewhere."""
    from app import registry as R
    t = R.get(task)
    out = []
    for o in (t.options if t else []):
        found = option_calls(task, o.name)
        if found:
            out.append(found[0])
    return out


def _fallback(task: str, shipped) -> list:
    """The one literal that is exactly this text, when there is exactly one."""
    if not shipped:
        return []
    for where in _order(task):
        hits = [(where, n) for n in index(where)["strings"].get(shipped, [])]
        if len(hits) == 1:
            return hits
        if hits:
            return []
    return []


def where(key: str, shipped: str | None = None) -> str:
    """"app/tasks/cull.py:212", or "" when the text is not a literal."""
    found = locate(key, shipped)
    if not found:
        return ""
    path, node = found[0]
    return f"{relative(path)}:{node.lineno}"
