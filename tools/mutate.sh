#!/bin/sh
# Break the code on purpose and check the tests notice.
#
#   tools/mutate.sh <file> <old text> <new text> [test module]
#
# The __pycache__ sweep is not tidiness. A one-character mutation reverted
# inside the same second leaves a .pyc whose recorded mtime and size still
# match the restored source, so Python keeps the MUTATED bytecode - and the
# next run reports a mutation as "survived" while testing code that is no
# longer there. That happened, and it cost an hour of looking in the wrong
# place.
set -e
file="$1"; old="$2"; new="$3"; tests="${4:-discover -s tests}"
cp "$file" "$file.mutbak"
python - "$file" "$old" "$new" <<'PY'
import sys
path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(path).read()
if old not in s:
    raise SystemExit(f"the mutation does not match anything in {path} - it would "
                     f"have looked like a test that survived it")
open(path, "w").write(s.replace(old, new, 1))
PY
sweep(){ find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true; }
sweep
python -m unittest $tests 2>&1 | tail -2 | tr '\n' ' '
echo "  <= mutation"
mv "$file.mutbak" "$file"
sweep
python -m unittest $tests 2>&1 | tail -2 | tr '\n' ' '
echo "  <= restored"
