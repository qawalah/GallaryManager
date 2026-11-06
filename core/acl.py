"""The folders DSM still has to bless - a list, and a job that does it.

**Why this exists at all.** On a Synology, what File Station, Synology Drive and
Photos go by is not the Unix owner and mode; it is DSM's own access list, kept
in a privileged extended attribute. A folder this app creates gets none of it -
`os.mkdir` inherits no extended attributes - and a folder with no access list is
one Drive silently stops syncing.

`core.perms` copies the parent's attributes onto every new folder, and on a PC
or as root that is the whole story. On the NAS it is not, and the reason is not
a bug that can be fixed in here:

- **a privileged attribute needs root.** Running the container as your own user
  is the right thing for ownership, and it makes writing DSM's access list
  impossible: the kernel answers "Operation not permitted" and nothing else
  happens. Measured, not assumed - there is a test for it.
- **even as root, a verbatim copy is not DSM's inheritance.** DSM knows which
  entries in a list are inheritable and what an inherited copy of one should
  look like. This app does not, and learning it would mean keeping a guess about
  someone else's format up to date forever.

So the job goes to the only thing that has both the privilege and the knowledge:
`synoacltool`, on the DSM host, run by DSM's own Task Scheduler as root. What
this module does is make sure that job knows **exactly which folders** to look
at, so it is a fraction of a second rather than a sweep of the whole library.

**The file is append-only from both ends, and that is the whole trick.** Two
different users share it - this app, as you, and the repair job, as root - and
whoever REWRITES a file becomes its owner, which would lock the other one out on
the next run. So neither rewrites it:

- this app appends `+` lines, one per folder it created;
- the job appends one `-` line when it finishes, saying when and how many.

Everything after the last `-` line is what is still waiting. The app compacts
the file when it gets long, which is safe because a re-run of the job on a
folder already put right does nothing - `-enforce-inherit` is idempotent, so the
worst a lost line can cost is a second.
"""

from __future__ import annotations

import os
import threading
import time

from .store import store_path

QUEUE = "permissions-queue.txt"
SCRIPT = "fix-permissions.sh"
# Overwritten by the repair job every time it runs, whether or not there was
# anything to do. It is how the app can say "the job is alive and last looked
# four minutes ago" instead of telling you to go and set one up forever.
HEARTBEAT = "permissions-job.txt"

# Long before this is a problem, but a file nothing ever shortens is a file that
# eventually fills a disk. Compacted to what is still waiting, plus the last
# thing the job said.
TOO_LONG = 4000

_LOCAL = threading.local()


class quiet:
    """Nothing created in here is queued - for the check, which cleans up.

    The Permissions check makes a real folder and removes it again; queuing that
    folder would leave the repair job a path that is not there, over and over.
    A context manager rather than a flag because a flag is a thing somebody
    forgets to put back.
    """

    def __enter__(self):
        self.before = getattr(_LOCAL, "off", False)
        _LOCAL.off = True
        return self

    def __exit__(self, *_):
        _LOCAL.off = self.before
        return False


def muted() -> bool:
    return bool(getattr(_LOCAL, "off", False))


def _path() -> str:
    """Where the list lives, or "" when there is nowhere to put it.

    The store refuses rather than inventing a folder when `PM_DATA` is wrong,
    which is right for settings and wrong for this: a folder that has to be
    blessed again later is not worth failing a photograph over.
    """
    try:
        return store_path(QUEUE)
    except Exception:                                  # noqa: BLE001
        return ""


def _lines() -> list:
    where = _path()
    if not where:
        return []
    try:
        with open(where, "r", encoding="utf-8", errors="replace") as fh:
            return [ln.rstrip("\n") for ln in fh if ln.strip()]
    except OSError:
        return []


def remember(folders, why: str = "") -> int:
    """Add folders to the list the repair job works from. Never raises.

    Called the moment a folder is created, from `perms.like_parent`, and only
    when something the parent had could not be carried onto it. A folder that
    came out right is not on the list, so an empty list means there is genuinely
    nothing to do - which is what makes running the job every few minutes cost
    nothing.
    """
    if muted():
        return 0
    wanted = []
    for one in folders or []:
        one = str(one or "").strip()
        if one and one not in wanted:
            wanted.append(one)
    if not wanted or not _path():
        return 0
    try:
        have = set(waiting())
        fresh = [w for w in wanted if w not in have]
        if not fresh:
            return 0
        why = " ".join(str(why or "").split())[:200]
        with open(_path(), "a", encoding="utf-8") as fh:
            for one in fresh:
                fh.write(f"+\t{time.time():.0f}\t{one}\t{why}\n")
        return len(fresh)
    except OSError:
        return 0


def waiting() -> list:
    """The folders added since the repair job last finished, oldest first."""
    out: list = []
    for line in _lines():
        bit = line.split("\t")
        if bit[0] == "-":
            out = []                                   # the job took the lot
        elif bit[0] == "+" and len(bit) > 2 and bit[2] and bit[2] not in out:
            out.append(bit[2])
    return out


def why_waiting() -> str:
    """The reason recorded against the oldest thing still waiting, or ""."""
    for line in _lines():
        bit = line.split("\t")
        if bit[0] == "+" and len(bit) > 3 and bit[3].strip():
            if bit[2] in waiting():
                return bit[3].strip()
    return ""


def last_run() -> dict:
    """When the repair job last finished and what it did, or {} for never.

    This is how the app can say whether the job is actually running, rather than
    telling you to go and set one up and never mentioning it again. The job
    leaves a mark every run, idle or not; the line in the list itself is the
    fallback, and is what an in-app repair writes.
    """
    try:
        where = store_path(HEARTBEAT)
        with open(where, "r", encoding="utf-8", errors="replace") as fh:
            bit = fh.read().strip().split("\t")
        return {"when": float(bit[0]), "fixed": int(bit[1]),
                "failed": int(bit[2]),
                "gone": int(bit[3]) if len(bit) > 3 else 0}
    except Exception:                                  # noqa: BLE001
        pass
    for line in reversed(_lines()):
        bit = line.split("\t")
        if bit[0] == "-" and len(bit) > 3:
            try:
                return {"when": float(bit[1]), "fixed": int(bit[2]),
                        "failed": int(bit[3]),
                        "gone": int(bit[4]) if len(bit) > 4 else 0}
            except ValueError:
                return {}
    return {}


def finished(fixed: int, failed: int = 0, gone: int = 0) -> bool:
    """Write what the repair job writes - for when this app IS root.

    The same mark either way, so there is one answer to "when did this last
    happen" no matter which of the two did it.
    """
    if not _path():
        return False
    now = time.time()
    try:
        with open(_path(), "a", encoding="utf-8") as fh:
            fh.write(f"-\t{now:.0f}\t{int(fixed)}\t{int(failed)}"
                     f"\t{int(gone)}\n")
    except OSError:
        return False
    try:
        with open(store_path(HEARTBEAT), "w", encoding="utf-8") as fh:
            fh.write(f"{now:.0f}\t{int(fixed)}\t{int(failed)}"
                     f"\t{int(gone)}\n")
    except Exception:                                  # noqa: BLE001
        pass
    return True


def forget(folder: str) -> bool:
    """Take one folder off the list - it was removed, or put right by hand."""
    folder = str(folder or "").strip()
    return bool(folder) and _rewrite(drop=folder)


def compact() -> bool:
    """Shorten the file to what still matters: the last mark, and what waits."""
    return _rewrite()


def _rewrite(drop: str = "") -> bool:
    """The one place this file is rewritten, and only ever by this app.

    Rewriting makes the writer the owner, so the repair job - which runs as root
    - must never do it, or the next append from this app would be refused. That
    asymmetry is deliberate and is the reason the format is append-only.
    """
    where = _path()
    if not where:
        return False
    lines = _lines()
    keep = []
    mark = ""
    for line in lines:
        bit = line.split("\t")
        if bit[0] == "-":
            mark, keep = line, []
        elif bit[0] == "+" and len(bit) > 2:
            if drop and bit[2] == drop:
                continue
            keep.append(line)
    if mark:
        keep.insert(0, mark)
    if len(keep) == len(lines) and not drop:
        return False
    try:
        tmp = where + ".new"
        with open(tmp, "w", encoding="utf-8") as fh:
            for line in keep:
                fh.write(line + "\n")
        os.replace(tmp, where)
        return True
    except OSError:
        return False


# ---------------------------------------------- the job, as text you can read

def script_text(trees=(), every: str = "5 minutes", uid=None, gid=None) -> str:
    """The repair job, written out as plain text for DSM's Task Scheduler.

    Written rather than run, because the tool is on the host and this app is
    not, and because a thing that changes permissions across a library is a
    thing you should be able to read before you let it loose.

    It finds the list beside itself rather than being told where it is, so it
    does not matter that the app and DSM call the same folder by different
    names. It asks the tool which option this DSM build has instead of
    remembering, because `-copy` and `-enforce-inherit` both exist in the wild
    and neither is documented. And it never rewrites the list - it appends one
    line - so the file stays owned by the app and the app can go on adding to
    it.
    """
    out = [
        "#!/bin/sh",
        "# Photo Manager - give new folders the access list DSM would have",
        "# given them. Set it up once, as root, and forget it:",
        "#",
        "#   DSM > Control Panel > Task Scheduler > Create > Scheduled Task",
        "#   > User-defined script.  User: root.  Schedule: every "
        + str(every) + ".",
        "#",
        "# Each run it reads the short list of folders the app has made since",
        "# last time and fixes exactly those. With nothing waiting it stops",
        "# immediately, which is why it can run this often.",
        "#",
        "#   ...fix-permissions.sh all    goes over every tree once, for the",
        "#                                folders made before any of this.",
        "#   ...fix-permissions.sh own    gives back the folders and files that",
        "#                                belong to ROOT inside your trees - what",
        "#                                this app made while it ran as root and",
        "#                                can no longer write to as you.",
        "#",
        "# Nothing here moves, deletes or rewrites a photo.",
        "",
        'HERE=$(dirname "$0")',
        f'QUEUE="$HERE/{QUEUE}"',
        f'MARK="$HERE/{HEARTBEAT}"',
        "",
        "TOOL=/usr/syno/bin/synoacltool",
        '[ -x "$TOOL" ] || TOOL=$(command -v synoacltool 2>/dev/null)',
        'if [ ! -x "$TOOL" ]; then',
        '  echo "synoacltool is not on this machine - is this script running on'
        ' the NAS itself, as root?"',
        "  exit 1",
        "fi",
        "",
        "# Which option does THIS build have? Asked, not remembered.",
        'USAGE=$("$TOOL" 2>&1)',
        'case "$USAGE" in',
        "  *enforce-inherit*) HOW=inherit ;;",
        "  *-copy*)           HOW=copy ;;",
        "  *)                 HOW=inherit ;;",
        "esac",
        "",
        "bless() {",
        '  if [ "$HOW" = inherit ]; then',
        '    "$TOOL" -enforce-inherit "$1"',
        "  else",
        '    "$TOOL" -copy "$(dirname "$1")" "$1"',
        "  fi",
        "}",
        "",
    ]
    trees = [t for t in (trees or []) if str(t or "").strip()]
    out += ['if [ "$1" = all ]; then']
    if trees:
        out.append('  if [ "$HOW" != inherit ]; then')
        out.append('    echo "this DSM has no -enforce-inherit, so a whole tree'
                   ' cannot be done in one go"')
        out.append("    exit 1")
        out.append("  fi")
        for tree in trees:
            out.append(f'  if [ -d "{tree}" ]; then')
            out.append(f'    echo "--- {tree}"')
            out.append(f'    bless "{tree}"')
            out.append("  fi")
        # Every tree done covers every folder on the list, so the list is
        # marked done as well - without this, a job set up with "all" fixed
        # everything and the app went on saying folders were waiting.
        out.append('  [ -f "$QUEUE" ] && printf \'%s\\t%s\\t%s\\t%s\\t%s\\n\' \'-\' "$(date +%s)" 0 0 0 >> "$QUEUE"')
        out.append('  printf \'%s\\t%s\\t%s\\t%s\\n\' "$(date +%s)" 0 0 0 > "$MARK"')
        out.append('  echo "done"')
    else:
        out.append('  echo "no trees are set up in the app yet"')
    out += ["  exit 0", "fi", ""]

    # ---- giving back what root owns. Narrow on purpose: -uid 0 and nothing
    # else. Everything inside a photo library that belongs to root got there
    # one way - this app, running as root, before it ran as you - so that is
    # exactly the set to hand back, and anything else is somebody's deliberate
    # decision and none of this script's business.
    if uid is not None and trees:
        out += ['if [ "$1" = own ]; then']
        for tree in trees:
            out.append(f'  if [ -d "{tree}" ]; then')
            out.append(f'    echo "--- {tree}"')
            out.append(f'    find "{tree}" -uid 0 -print -exec chown '
                       f'{int(uid)}:{int(gid or 0)} {{}} +')
            out.append(f'    bless "{tree}"')
            out.append("  fi")
        out += ['  echo "done - nothing but root-owned things was touched"',
                "  exit 0", "fi", ""]
    else:
        out += ['if [ "$1" = own ]; then',
                '  echo "this app could not work out which user to give things'
                ' back to"',
                "  exit 1", "fi", ""]

    out += [
        '[ -f "$QUEUE" ] || { printf \'%s\\t0\\t0\\t0\\n\' "$(date +%s)"'
        ' > "$MARK"; exit 0; }',
        "",
        "# Everything after the last '-' line is what is still waiting. Read",
        "# straight out of the list into the loop: this script makes no file of",
        "# its own, deletes nothing, and never writes over the list itself.",
        "COUNT=$(awk -F'\\t' '$1==\"-\"{n=0} $1==\"+\"{a[++n]=$3} "
        "END{for(i=1;i<=n;i++) print a[i]}' \"$QUEUE\" | {",
        "  ok=0",
        "  bad=0",
        "  gone=0",
        "  while IFS= read -r folder; do",
        '    [ -n "$folder" ] || continue',
        "    # A folder that was moved or tidied away since is not a failure -",
        "    # but it still has to come OFF the list, or it is looked for on",
        "    # every run from now until somebody notices.",
        '    if [ ! -d "$folder" ]; then',
        "      gone=$((gone+1))",
        "      continue",
        "    fi",
        '    if bless "$folder" >/dev/null 2>&1; then',
        "      ok=$((ok+1))",
        "    else",
        "      bad=$((bad+1))",
        '      echo "could not fix: $folder" >&2',
        "    fi",
        "  done",
        '  echo "$ok $bad $gone"',
        "})",
        'ok=$(echo "$COUNT" | cut -d\' \' -f1)',
        'bad=$(echo "$COUNT" | cut -d\' \' -f2)',
        'gone=$(echo "$COUNT" | cut -d\' \' -f3)',
        "",
        "# One line appended, never a rewrite: the list belongs to the app and",
        "# has to stay that way, or it could not add to it after this ran.",
        'if [ $((ok + bad + gone)) -gt 0 ]; then',
        "  printf '%s\\t%s\\t%s\\t%s\\t%s\\n' '-' \"$(date +%s)\" \"$ok\""
        ' "$bad" "$gone" >> "$QUEUE"',
        "fi",
        "printf '%s\\t%s\\t%s\\t%s\\n' \"$(date +%s)\" \"$ok\" \"$bad\""
        ' "$gone" > "$MARK"',
        "",
        "# Not one folder on the list was here. Said out loud rather than",
        "# counted as nothing to do: it is what a path this app and DSM spell",
        "# differently looks like, and it would otherwise be silent forever.",
        'if [ "$gone" -gt 0 ] && [ $((ok + bad)) -eq 0 ]; then',
        '  echo "none of the $gone folders on the list are here - does this'
        ' machine spell those paths the same way the app does?" >&2',
        "fi",
        'echo "put right: $ok   could not: $bad   no longer there: $gone"',
    ]
    return "\n".join(out) + "\n"


def after_delete(paths) -> int:
    """Hand the folders that just LOST something to DSM's job.

    Synology Drive did not notice a folder this app sent to the Recycle Bin,
    while the same delete from File Station reached the tablet. What differs is
    who did it: File Station is DSM itself, and this app is a container. The
    repair job runs as DSM, so each parent is put on its list - DSM going over
    the folder is the nudge. Untested on the NAS: if Drive still misses it, the
    next step is to have DSM do the delete itself.
    """
    parents = []
    for one in paths or []:
        up = os.path.dirname(str(one or "").rstrip("/\\"))
        if up and up not in parents:
            parents.append(up)
    return remember(parents, "something inside was deleted - so Synology "
                             "Drive re-reads it")

