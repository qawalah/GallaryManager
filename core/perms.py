"""Keeping the owner and mode of what this app writes - the thing that broke Drive.

Every metadata write in this app is done the safe way: build the new file
completely, then `os.replace` it over the old one, so a crash half way cannot
leave you with half a photograph. That safety has a cost nobody sees until much
later, and it is the whole reason this module exists.

**A replaced file is a NEW file.** It has the owner, the group and the mode of
whatever process wrote it - not the ones the photograph had. This app runs in a
container as root, so syncing ratings across a library quietly re-owned every
rated JPEG in it to root:root. Nothing failed. Nothing was logged. The
photographs were all still there and all still correct.

What broke was everything that reads the library as a USER. Synology Drive runs
as you, not as root, and a tree it can no longer read is a tree it stops
syncing - silently, because from Drive's point of view nothing is wrong. The
repair is by hand in File Station: Properties, Permission, "make inherited
permissions explicit", apply to sub-folders and files. Nobody should have to do
that twice.

So there are three rules here, and each one is a different way the same problem
arrives:

- **a file rewritten in place keeps what it had** - owner, group, mode, and the
  date, which is restored beside these;
- **a file this app CREATES takes after the thing it belongs to** - a sidecar
  after its photograph, a copy after the folder it lands in;
- **a folder this app creates takes after the folder above it**, which is how a
  new shoot folder ends up looking exactly like the one it was made beside.

All of it is best effort and none of it ever raises. Changing an owner needs
root; on a PC there is no such thing as `chown` at all; and a photograph
correctly filed with awkward permissions is a far better outcome than a move
that failed. Where it cannot be done, `scripts/doctor.py` says so out loud rather than
leaving it to be discovered by a sync that goes quiet.
"""

from __future__ import annotations

import os

CAN_CHOWN = hasattr(os, "chown")
CAN_XATTR = hasattr(os, "listxattr")


def xattrs_of(path: str) -> dict:
    """The extended attributes on this file - which on DSM is where the ACL is.

    This is the half that owner and mode do not cover, and on a Synology it is
    the half that matters most. DSM keeps its own access control list in an
    extended attribute, and File Station, Drive and Photos all go by THAT rather
    than by the Unix bits underneath. A file replaced by `os.replace` has none
    of it - which is precisely the state that "Advanced options > Make inherited
    permissions explicit" is the cure for.
    """
    if not CAN_XATTR:
        return {}
    out = {}
    try:
        for name in os.listxattr(path, follow_symlinks=False):
            try:
                out[name] = os.getxattr(path, name, follow_symlinks=False)
            except OSError:
                pass
    except OSError:
        pass
    return out


# Extended attributes that belong to ONE file and must never be carried to
# another. `posix_acl_default` is the list a DIRECTORY hands to things created
# inside it and is meaningless on a file; the capability and selinux ones
# describe that exact inode. Everything else - including DSM's own access list -
# is what "the same permissions as" means and is copied.
NOT_INHERITED = ("system.posix_acl_default", "security.capability",
                 "security.selinux", "security.ima", "security.evm")


def travels(name: str, to_folder: bool) -> bool:
    """Does this attribute belong to the thing it is being copied ONTO?

    A decision of its own rather than a condition buried in a loop, because the
    loop swallows every refusal - so a wrong answer here would look exactly like
    the filesystem declining, and never be noticed. There is a test for each
    side of it.
    """
    if name not in NOT_INHERITED:
        return True
    # A directory's default list is what it hands to things created inside it:
    # it travels folder to folder, and never onto a photograph.
    return to_folder and name == "system.posix_acl_default"


def put_xattrs(path: str, attrs: dict, to_folder: bool = None,
               refused: list = None) -> int:
    """Put them back. Each one on its own, because one refusal is not the rest.

    Only ever attributes read off a real thing a moment ago - the file before it
    was replaced, the photograph a sidecar belongs to, the folder a new folder
    was made inside. Nothing is synthesised.

    `to_folder` says whether the destination is a directory, and it matters for
    exactly one attribute: `system.posix_acl_default` is a directory's list of
    what to give things created inside it, so it travels from folder to folder
    and never onto a file.

    **`refused` is the important argument, and it was added late.** This used to
    swallow every refusal in silence, and that one line is what made the whole
    permissions problem take so long to find: on the NAS the app ran as a
    NORMAL user, DSM's access list lives in a privileged extended attribute, the
    kernel answered "Operation not permitted" - and the app carried on, copied
    the owner and the mode, and reported the fix as done. Pass a list here and
    every refusal arrives in it as `(attribute, reason)`, so the caller can say
    what did not happen instead of pretending it did.
    """
    if not CAN_XATTR or not attrs:
        return 0
    if to_folder is None:
        to_folder = os.path.isdir(path)
    done = 0
    for name, value in attrs.items():
        if not travels(name, to_folder):
            continue
        try:
            os.setxattr(path, name, value, follow_symlinks=False)
            done += 1
        except OSError as exc:
            if refused is not None:
                refused.append((name, exc.strerror or str(exc)))
    return done


# ------------------------------------------------- DSM's own tool, where it is

# Where Container Manager would have it if the DSM binaries are bind-mounted in,
# and the plain name in case this app is running on the NAS itself rather than
# in a container.
SYNOACLTOOL = ("/usr/syno/bin/synoacltool", "/usr/bin/synoacltool", "synoacltool")

_TOOL: list = []          # [path or ""], worked out once
_CAN: dict = {}           # which options it advertises


def dsm_tool() -> str:
    """`synoacltool`, if it can actually be run from in here. "" otherwise.

    It lives on the DSM host and this app is usually in a container mounting one
    home folder, so the normal answer is "" - which is not a failure, it is the
    ordinary case, and the fallback below is what happens instead.
    """
    if _TOOL:
        return _TOOL[0]
    import shutil as _sh
    found = ""
    for name in SYNOACLTOOL:
        if os.sep in name:
            if os.access(name, os.X_OK):
                found = name
                break
        else:
            got = _sh.which(name)
            if got:
                found = got
                break
    _TOOL.append(found)
    return found


def dsm_can(option: str) -> bool:
    """Does this build of the tool advertise that option?

    ASKED, not remembered. `-copy` and `-enforce-inherit` both appear in the
    wild and neither is documented by Synology, so which exist depends on the
    DSM version - and running a command a build does not have would fail once a
    folder, quietly, into nobody's log. It prints its own usage when called with
    nothing, so that is what is read.
    """
    if not _CAN:
        tool = dsm_tool()
        text = ""
        if tool:
            import subprocess as _sp
            try:
                got = _sp.run([tool], capture_output=True, text=True, timeout=20)
                text = (got.stdout or "") + (got.stderr or "")
            except Exception:                          # noqa: BLE001
                text = ""
        _CAN["_text"] = text
    return bool(_CAN.get("_text")) and option in _CAN["_text"]


def _dsm_copied(parent: str, folder: str) -> bool:
    """Ask DSM to give this new folder the access list it should have inherited.

    The accurate answer where it is reachable: DSM knows its own ACL format,
    including which entries are inheritable and what an inherited copy of one
    should look like, and this app does not and should not learn. Where the tool
    is not in the container - the ordinary case - False, and the caller copies
    the parent's attributes verbatim instead, which is what File Station's "make
    inherited permissions explicit" does and is a great deal better than the
    nothing a new folder gets on its own.
    """
    if not dsm_can("-copy"):
        return False
    import subprocess as _sp
    try:
        got = _sp.run([dsm_tool(), "-copy", parent, folder],
                      capture_output=True, text=True, timeout=60)
        return got.returncode == 0
    except Exception:                                  # noqa: BLE001
        return False


def forget_tool() -> None:
    """Only for tests: the answer is worked out once and cached."""
    _TOOL.clear()
    _CAN.clear()


def stat_of(path: str):
    """What this file's permissions are right now, or None."""
    try:
        return os.stat(path)
    except OSError:
        return None


def restore(path: str, was, attrs=None) -> bool:
    """Put back the owner, group, mode and ACL this file had before the replace.

    `was` is an os.stat_result taken BEFORE the write, `attrs` the extended
    attributes from the same moment. Called right after an `os.replace`, beside
    the line that puts the date back - all of it belongs together, and leaving
    out any one of them is the same bug in a different disguise.
    """
    if attrs:
        put_xattrs(path, attrs)
    if was is None:
        return False
    done = False
    try:
        os.chmod(path, was.st_mode & 0o7777)
        done = True
    except OSError:
        pass
    if CAN_CHOWN:
        try:
            if os.stat(path).st_uid != was.st_uid or \
                    os.stat(path).st_gid != was.st_gid:
                os.chown(path, was.st_uid, was.st_gid)
            done = True
        except OSError:
            # Not root, or a filesystem that does not do owners. Not an error:
            # it means this app is running as the user already, which is the
            # arrangement where none of this matters.
            pass
    return done


def like(path: str, template: str) -> bool:
    """Give this new file the owner, group and mode of something else.

    A sidecar takes after its photograph. A copy takes after the original it
    was made from. Both because the thing that reads them next - Lightroom,
    Drive, Photos - reads them as you, and a root-owned .xmp beside your RAW is
    a rating that quietly does not exist.

    The ACL comes too, and only ever from a real file of the same kind sitting
    in the same place. That is the difference between copying something true and
    inventing something plausible.
    """
    return restore(path, stat_of(template), xattrs_of(template))


def like_parent(path: str) -> bool:
    """Give this new file or folder the permissions of the folder above it.

    For a FILE the executable bits are dropped: a folder is 0755 because you
    have to be able to enter it, and a photograph that is executable is a
    photograph some virus scanner will eventually have an opinion about.

    **This app does NOT write DSM's access list onto a new folder, and that is a
    deliberate reversal.** It used to copy the parent's extended attributes
    across, which sounds obviously right and was measurably worse than doing
    nothing:

    - a blank new folder was repaired by `synoacltool -enforce-inherit`, which
      is what the scheduled job runs, and that worked;
    - a folder carrying a VERBATIM COPY of its parent's list already has one, so
      the same command considers it settled and skips it. The copy is not what
      DSM would have produced by inheritance - the entries are right and their
      inheritance flags are not - and Synology Drive goes on ignoring the folder
      while everything on this side reports success.

    So the copy was not a fix that fell short; it was the thing PREVENTING the
    fix. A whole tree sweep that used to take minutes started finishing in under
    a second, having done nothing, and the app said the folder came out
    identical to its parent - which was true of the bytes and false of the
    meaning.

    There are therefore exactly two ways a folder gets its access list, and
    neither of them is this app guessing at DSM's format:

    - **DSM's own tool, here and now**, when `synoacltool` is reachable - the
      accurate answer, because it knows which entries are inheritable and what
      an inherited copy of one looks like;
    - **the scheduled job**, running as root, over the list of folders this app
      writes down as it creates them. Every folder goes on that list, not just
      the ones something refused, because a folder left blank ON PURPOSE is
      still a folder waiting for its list.

    Owner, group and mode are still carried, and they still matter: they are
    what keep the library belonging to you rather than to whatever this app runs
    as.
    """
    up = os.path.dirname(os.path.abspath(path)) or "."
    was = stat_of(up)
    if was is None:
        return False
    done = False
    folder = os.path.isdir(path)
    if folder:
        # DSM's own tool if it is reachable, and otherwise the list - never a
        # copy made up in here. See the docstring: the copy was what stopped the
        # repair working.
        if not _dsm_copied(up, path):
            hand_over(path, [])
        done = True
    try:
        mode = was.st_mode & 0o7777
        if not folder:
            mode &= ~0o111
        os.chmod(path, mode)
        done = True
    except OSError:
        pass
    if CAN_CHOWN:
        try:
            os.chown(path, was.st_uid, was.st_gid)
            done = True
        except OSError:
            pass
    return done


def hand_over(folder: str, refused: list = ()) -> bool:
    """This folder still needs its access list. Say so, in writing.

    Not a log line - a list, in a file, that a job running as root works from.
    DSM's access list lives in a privileged extended attribute, a normal user
    cannot write one, and running as a normal user is the RIGHT arrangement for
    everything else - so this is not something that can be fixed by trying
    harder in here. See `core.acl` for the whole of the reasoning.

    Every folder this app creates goes on the list when DSM's tool is not
    reachable, including the ones where nothing refused anything, because a
    folder deliberately left blank is still a folder waiting.
    """
    try:
        from . import acl
        if refused:
            names = ", ".join(sorted({n for n, _why in refused}))
            why = f"could not write {names}: {refused[0][1]}"
        else:
            why = "left for the repair job - only DSM can write its access list"
        return bool(acl.remember([folder], why))
    except Exception:                                  # noqa: BLE001
        return False


def make_folder(path: str) -> list:
    """Make a folder, and give every level made the permissions of its parent.

    `os.makedirs` in one call would leave each new level owned by whoever is
    running - so a new year folder, and the shoot folder inside it, would both
    be root's while the library around them is yours. Made one at a time
    instead, each taking after the one above it, which is exactly what DSM would
    have done itself.

    Returns the folders actually created, newest last.
    """
    path = os.path.abspath(path)
    if os.path.isdir(path):
        return []
    missing = []
    here = path
    while here and not os.path.isdir(here):
        missing.append(here)
        up = os.path.dirname(here)
        if up == here:
            break
        here = up
    made = []
    for one in reversed(missing):
        try:
            os.mkdir(one)
        except FileExistsError:
            continue
        except OSError:
            break
        like_parent(one)
        made.append(one)
    return made


def writes_as() -> tuple:
    """Who this app writes as: (uid, gid), or (None, None) where that is moot."""
    try:
        return os.geteuid(), os.getegid()
    except AttributeError:              # Windows
        return None, None


def owner_of(path: str) -> tuple:
    was = stat_of(path)
    return (was.st_uid, was.st_gid) if was else (None, None)


def mismatch(folder: str) -> str:
    """"Everything written here will be owned by root, and this folder is not."

    The check `scripts/doctor.py` and Setup make, because this is a fault that reports
    itself as nothing at all: the files are written, the moves succeed, the app
    is happy - and Synology Drive, which reads the library as YOU, stops syncing
    a tree it can no longer read, without saying anything either.
    """
    uid, _gid = writes_as()
    if uid is None or not folder or not os.path.isdir(folder):
        return ""
    owner, _g = owner_of(folder)
    if owner is None or owner == uid:
        return ""
    if uid == 0:
        return (f"This app writes as root, and {folder} belongs to user id "
                f"{owner}. Anything it creates keeps the permissions of what it "
                f"was made from, so this is usually fine - and as root it can "
                f"write the access list itself rather than leaving it to the "
                f"repair job.")
    return (f"This app writes as user id {uid}, and {folder} belongs to user id "
            f"{owner}. Files it creates may not be readable by whoever owns the "
            f"library - which is how Synology Drive quietly stops syncing a "
            f"folder.")


# ------------------------------------------------- proving it, on your machine

def compare(a: str, b: str) -> dict:
    """What is different between two things, attribute by attribute.

    Used to check the claim this module makes rather than assert it: a folder
    this app created is compared with the folder it was created inside, and
    anything that does not match is named. On a Synology the interesting entry
    is whichever extended attribute holds the access list - and this does not
    need to know which one that is, because it compares them all.
    """
    out = {"same": [], "different": [], "only_parent": [], "only_child": []}
    sa, sb = stat_of(a), stat_of(b)
    if sa is None or sb is None:
        out["different"].append(("exists", bool(sa), bool(sb)))
        return out
    for name, one, two in (("owner", sa.st_uid, sb.st_uid),
                           ("group", sa.st_gid, sb.st_gid),
                           ("mode", oct(sa.st_mode & 0o7777),
                            oct(sb.st_mode & 0o7777))):
        (out["same"] if one == two else out["different"]).append(
            (name, one, two) if one != two else name)
    xa, xb = xattrs_of(a), xattrs_of(b)
    for name in sorted(set(xa) | set(xb)):
        if name in xa and name not in xb:
            out["only_parent"].append(name)
        elif name in xb and name not in xa:
            out["only_child"].append(name)
        elif xa[name] == xb[name]:
            out["same"].append(name)
        else:
            out["different"].append((name, f"{len(xa[name])} bytes",
                                     f"{len(xb[name])} bytes"))
    return out


def try_a_folder(inside: str, name: str = ".pm-permission-check") -> dict:
    """Create a folder the way every task does, compare it, and remove it.

    The honest way to answer "are new folders coming out right on YOUR NAS",
    which is not a question that can be settled from here: the access list is
    DSM's, the filesystem is DSM's, and the only machine where the answer is
    worth anything is the one with the photographs on it.

    Removes what it made, always - including when the comparison raised.
    """
    from . import acl
    out = {"folder": "", "made": False, "removed": False, "why": "",
           "compare": {}, "tool": dsm_tool(), "copied_by_tool": False,
           "refused": []}
    inside = str(inside or "").strip()
    if not inside or not os.path.isdir(inside):
        out["why"] = f"there is no folder at {inside!r}"
        return out
    where = os.path.join(inside, name)
    n = 1
    while os.path.exists(where):
        where = os.path.join(inside, f"{name}-{n}")
        n += 1
    out["folder"] = where
    was = stat_of(inside)
    # Nothing made in here goes on the repair list: it is removed a line later,
    # and a job handed a folder that is not there would say so every run.
    with acl.quiet():
        try:
            made = make_folder(where)
            out["made"] = bool(made)
            if not out["made"]:
                # `make_folder` is deliberately silent - a photograph correctly
                # filed with awkward permissions beats a move that failed - so
                # the reason has to be asked for separately. "It could not be
                # created" is not an answer anybody can act on; "Permission
                # denied" is.
                _yes, why = can_write(inside)
                out["why"] = why or "the folder could not be created at all"
                return out
            out["copied_by_tool"] = bool(dsm_can("-copy"))
            # COMPARE FIRST, before anything else touches it. This has to be the
            # folder exactly as creation left it - which, since this app stopped
            # writing access lists, means blank. Probing first and comparing
            # afterwards would have the check reporting a folder that matches
            # its parent while every real folder comes out empty.
            out["compare"] = compare(inside, where)
            # Then, separately: COULD this app write one if it tried? That is a
            # different question from what creation does, and the answer is the
            # kernel's own words - which is the thing worth putting on a screen.
            refused = []
            put_xattrs(where, xattrs_of(inside), to_folder=True, refused=refused)
            out["refused"] = refused
        except Exception as exc:                       # noqa: BLE001
            out["why"] = str(exc)
        finally:
            try:
                os.rmdir(where)
                out["removed"] = True
            except OSError as exc:
                out["why"] = out["why"] or f"could not remove it again: {exc}"
    # And the tree's own date, which making a folder inside it has just moved.
    # Automation watches that date; a check that leaves it moved would set every
    # watched tree running on the next pass, over a library where nothing
    # happened.
    _put_the_date_back(inside, was)
    return out


# ------------------------------------------- "Permission denied", explained once

def _owner_words(uid) -> str:
    """"user id 0 (root)" - the (root) matters, because root is the whole story."""
    if uid is None:
        return "nobody in particular"
    return f"user id {uid}" + (" (root)" if uid == 0 else "")


def can_write(folder: str) -> tuple:
    """Can this app actually write into that folder? Measured, not guessed.

    `os.access` answers for the Unix bits and knows nothing about DSM's access
    list, which is the half that decides on this NAS - so it is not enough. This
    makes a real folder and removes it again, which is the only answer worth
    having, and it is the same thing every task does the moment it needs one.

    Returns (yes, why). `why` is the system's own words when the answer is no.
    """
    folder = str(folder or "").strip()
    if not folder or not os.path.isdir(folder):
        return False, "there is no folder there"
    where = os.path.join(folder, ".pm-write-check")
    n = 1
    while os.path.exists(where):
        where = os.path.join(folder, f".pm-write-check-{n}")
        n += 1
    before = stat_of(folder)
    try:
        os.mkdir(where)
    except OSError as exc:
        return False, (exc.strerror or str(exc))
    try:
        os.rmdir(where)
    except OSError:
        pass
    _put_the_date_back(folder, before)
    return True, ""


def _put_the_date_back(folder: str, was) -> None:
    """A check must not look like a change. This is not tidiness.

    Making a folder inside another one moves the OUTER folder's modified date,
    and that date is what Automation watches to decide whether a tree has
    anything new in it. So a check that leaves the date moved makes every
    watched tree look like it has just been touched - which means the next pass
    does a full run over a library where nothing happened, and the pass after
    that, forever. A probe that quietly schedules work is worse than no probe.

    The same restoration the metadata writers do after `os.replace`, for the
    same reason and in nanoseconds, because the automation compares dates at the
    resolution the filesystem records them.
    """
    if was is None:
        return
    try:
        os.utime(folder, ns=(was.st_atime_ns, was.st_mtime_ns))
    except OSError:
        pass


def denied_note(paths) -> str:
    """Why a run of "Permission denied" is happening, in one sentence. "" if not.

    The grouping already turns a hundred and fifty-six identical failures into
    one line, which was a large improvement over a hundred and fifty-six
    mysteries - but the line still only says WHAT, and "Permission denied" is
    not something anybody can act on. This is the WHY, and on this NAS it is
    nearly always the same why:

    **the folder was made while this app ran as root, and the app now runs as
    you.** Running as your own user is the right arrangement - it is what makes
    everything the app writes belong to you - and it cannot reach back into what
    the previous arrangement left behind. Every folder created during the root
    era belongs to root, and root's folders are not yours to write into.

    Worked out from what is actually on the disk rather than assumed: the owner
    of the folder that refused, against the user this process is. If those two
    agree the note says nothing at all, because then this is an ordinary
    permission problem and a confident wrong explanation is worse than none.
    """
    uid, _gid = writes_as()
    if uid is None:
        return ""
    seen = []
    for one in list(paths or [])[:20]:
        folder = str(one or "")
        if not folder:
            continue
        if not os.path.isdir(folder):
            folder = os.path.dirname(folder)
        owner, _g = owner_of(folder)
        if owner is not None and owner != uid and (folder, owner) not in seen:
            seen.append((folder, owner))
    if not seen:
        # Nothing could be established about who owns what, so nothing is said.
        # A confident wrong explanation is worse than none, and this one would
        # be offered at exactly the moment somebody is trying to work out what
        # went wrong.
        return ""
    where, owner = seen[0]
    more = (f" - and {len(seen) - 1:,} other folder(s) like it"
            if len(seen) > 1 else "")
    return (f"This app writes as {_owner_words(uid)}, and {where} belongs to "
            f"{_owner_words(owner)}{more}. That is what Permission denied means "
            f"here: the folder was almost certainly made while this app ran as "
            f"root, and running as your own user - which is the right "
            f"arrangement - cannot reach into what root left behind. Setup > "
            f"Permissions has the repair.")
