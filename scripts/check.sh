#!/bin/sh
# Build the page, check the JavaScript parses, and run the quick tests.
# Works from any checkout or worktree: everything is relative to this file.
cd "$(dirname "$0")/.." || exit 1
js="$(mktemp "${TMPDIR:-/tmp}/pm.XXXXXX.js")"
python3 -c "import sys; sys.path.insert(0,'.'); from app import page as P; open(sys.argv[1],'w').write(P.SCRIPT); print('page', len(P.PAGE))" "$js" || exit 1
node --check "$js" && echo JS_OK
status=$?
rm -f "$js"
exit $status
