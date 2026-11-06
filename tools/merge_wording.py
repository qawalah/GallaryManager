"""Merge an exported wording.json back into the source.

    python tools/merge_wording.py wording.json              # say what it would do
    python tools/merge_wording.py wording.json --apply      # and do it
    python tools/merge_wording.py wording.json --tasks cull,blur --apply

The file is what Setup > Wording's Download button gives (or any file with an
"overrides" object in it). Each key names one piece of text; this finds the
string literal that ships it (`app/wordsource.py`) and writes the new text in
its place, wrapped the way the code around it is. A help bubble an option
never had is added to its declaration. The page's own strings are written
into `app/web/page/strings.json` by name, and the Guide's into `app/page.py`
like any other literal.

Mechanical, and checked rather than trusting:
- an entry whose "shipped" text no longer matches the source is skipped and
  named, because the code changed after the export and a guess would undo it;
- a label of five words is refused, as the editor and the tests refuse it;
- text built at run time (no literal to replace) is listed for a hand edit;
- after writing, the registry is loaded again in a fresh process and every
  merged key must now ship exactly the new text.

Dev-only, standard library only. Run it from any checkout; it edits that one.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

WIDTH = 79


def quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace(
        "\n", "\\n") + '"'


def literal(text: str, col: int, parens: bool = False) -> str:
    """`text` as Python source starting at column `col`: one literal when it
    fits, else adjacent literals one per line, each broken after a space and
    lined up under the first, as the declarations already are."""
    one = quote(text)
    if col + len(one) + 2 <= WIDTH:
        return one
    start = col + (1 if parens else 0)
    room = max(20, WIDTH - start - 3)
    pieces, line = [], ""
    for word in text.split(" "):
        candidate = (line + " " + word) if line else word
        if len(quote(candidate + " ")) - 2 > room and line:
            pieces.append(line + " ")
            line = word
        else:
            line = candidate
    pieces.append(line)
    body = ("\n" + " " * start).join(quote(p) for p in pieces)
    return "(" + body + ")" if parens else body


def _offsets(source: str) -> list[int]:
    """Byte offset of the start of each line (1-based index)."""
    out, at = [0, 0], 0
    for line in source.encode("utf-8").splitlines(keepends=True):
        at += len(line)
        out.append(at)
    return out


def _span(starts, node) -> tuple[int, int]:
    return (starts[node.lineno] + node.col_offset,
            starts[node.end_lineno] + node.end_col_offset)


def _column(source: str, node) -> int:
    """The character column a node starts at (ast counts UTF-8 bytes)."""
    line = source.splitlines()[node.lineno - 1]
    return len(line.encode("utf-8")[:node.col_offset].decode("utf-8"))


def plan(overrides: dict, entries: dict, tasks: set | None):
    """[(path, start, end, new source)], and what could not be done."""
    import ast
    import app.tasks  # noqa: F401
    from app import pagetext as PT
    from app import wordsource as WS
    from app.tasks import wording as TW
    from core import wording as W

    table = TW.shipped()
    edits, notes = [], []
    for key, text in sorted(overrides.items()):
        got = W.parse(key)
        if not got:
            notes.append((key, "not a wording key"))
            continue
        if tasks and got["task"] not in tasks:
            continue
        if key not in table:
            notes.append((key, "the app does not ship this text any more"))
            continue
        now = table[key]
        was = entries.get(key)
        if was is not None and was != now:
            notes.append((key, "the source changed since the export; merge by hand"))
            continue
        why = W.refusal(key, text)
        if why:
            notes.append((key, why))
            continue
        if text == now:
            continue
        if got["task"] == "page":
            # JSON, not Python: written by name, not by offset (see write)
            edits.append((PT.FILE, -1, -1, text, key))
            continue
        found = WS.locate(key, now)
        if not found and got["kind"] == "help" and not now:
            calls = WS.option_calls(got["task"], got["option"])
            if not calls:
                notes.append((key, "the option's declaration was not found"))
                continue
            path, call = calls[0]
            idx = WS.index(path)
            source, starts = idx["source"], _offsets(idx["source"])
            last = (call.keywords[-1].value if call.keywords else call.args[-1])
            first = call.args[0] if call.args else call.keywords[0]
            indent = _column(source, first)
            at = starts[last.end_lineno] + last.end_col_offset
            new = ",\n" + " " * indent + "help=" + literal(text, indent + 5)
            edits.append((path, at, at, new, key))
            continue
        if not found:
            notes.append((key, "built at run time, not a literal; edit by hand"))
            continue
        for path, node in found:
            idx = WS.index(path)
            source, starts = idx["source"], _offsets(idx["source"])
            parent = WS.parent(path, node)
            parens = isinstance(parent, (ast.Assign, ast.AnnAssign, ast.Return,
                                         ast.AugAssign))
            a, b = _span(starts, node)
            edits.append((path, a, b, literal(text, _column(source, node),
                                              parens), key))
    return edits, notes


def write(edits) -> list:
    """Apply edits file by file, last first so earlier offsets hold. Two keys
    that land on one literal with different text are a conflict, not a race:
    the literal is left as it was and every key on it is reported, because
    writing whichever came first would give five colours the word "blue"."""
    clashes = []
    by_file: dict = {}
    for path, a, b, new, key in edits:
        by_file.setdefault(path, []).append((a, b, new, key))
    for path, items in by_file.items():
        if items[0][0] == -1:
            _write_strings(path, {key[len("page."):]: new
                                  for _a, _b, new, key in items})
            continue
        spots: dict = {}
        for a, b, new, key in items:
            spots.setdefault((a, b), []).append((new, key))
        clean = []
        for (a, b), said in spots.items():
            if len({new for new, _key in said}) > 1:
                keys = [key for _new, key in said]
                for key in keys:
                    clashes.append((key, "one line of source serves "
                                         f"{len(keys)} keys that now say different "
                                         "things; edit it by hand"))
                continue
            clean.append((a, b, said[0][0]))
        with open(path, "rb") as fh:
            data = fh.read()
        for a, b, new in sorted(clean, reverse=True):
            data = data[:a] + new.encode("utf-8") + data[b:]
        with open(path, "wb") as fh:
            fh.write(data)
    return clashes


def _write_strings(path: str, changed: dict) -> None:
    """The page's strings table, with these names given new text, in the
    order and layout it already had."""
    with open(path, encoding="utf-8") as fh:
        table = json.load(fh)
    table.update(changed)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(table, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


CHECK = r"""
import json, sys
import app.tasks
from app.tasks import wording as TW
from app.pagetext import slug
want = json.load(sys.stdin)
table = TW.shipped()
# a Guide page renamed is found under its new title's slug, paragraphs too
moved = {k.split(".")[1]: slug(v) for k, v in want.items()
         if k.startswith("guide.") and k.endswith(".title")}
def shipped(k, v):
    task, _, rest = k.partition(".")
    if rest.startswith("group."):
        # a heading renamed is a heading under its new name
        return f"{task}.group.{v}" in table
    if task == "guide":
        name, _, tail = rest.partition(".")
        k = f"guide.{moved.get(name, name)}.{tail}"
    return table.get(k) == v
bad = [k for k, v in want.items() if not shipped(k, v)]
print(json.dumps(bad))
"""


def verify(merged: dict) -> list:
    env = dict(os.environ, PM_DATA=os.environ.get("PM_DATA") or
               os.path.join(HERE, "config"))
    got = subprocess.run([sys.executable, "-c", CHECK], cwd=HERE, env=env,
                         input=json.dumps(merged), capture_output=True,
                         text=True, check=False)
    if got.returncode:
        return [f"the registry no longer loads:\n{got.stderr}"]
    return json.loads(got.stdout or "[]")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file")
    ap.add_argument("--tasks", default="", help="only these tools, comma separated")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    with open(args.file, encoding="utf-8") as fh:
        body = json.load(fh)
    overrides = body.get("overrides") if isinstance(body, dict) else None
    if not isinstance(overrides, dict):
        print("That file has no overrides in it.")
        return 2
    entries = {e["key"]: e.get("shipped") for e in body.get("entries") or []
               if isinstance(e, dict) and "key" in e}
    tasks = {t.strip() for t in args.tasks.split(",") if t.strip()} or None
    edits, notes = plan(overrides, entries, tasks)
    keys = sorted({e[4] for e in edits})
    print(f"{len(keys)} piece(s) of text to write, in "
          f"{len({e[0] for e in edits})} file(s).")
    for key, why in notes:
        print(f"  left alone  {key}: {why}")
    if not args.apply:
        print("Nothing written. Add --apply to write it.")
        return 0
    clashes = write(edits)
    for key, why in clashes:
        print(f"  conflict    {key}: {why}")
    wrong = verify({k: overrides[k] for k in keys
                    if k not in {c[0] for c in clashes}})
    for key in wrong:
        print(f"  not merged  {key}")
    print("Done." if not wrong else "Done, with the lines above to check.")
    return 1 if wrong or clashes else 0


if __name__ == "__main__":
    sys.exit(main())
