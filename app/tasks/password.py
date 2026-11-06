"""The lock on the front door: set it, change it, take it off.

This app has always been able to take a password - `PM_PASSWORD` in the compose
file - and in practice nobody sets one, because setting it means editing the
compose file and rebuilding the container, and changing it means doing that
again. A lock that costs a rebuild is a lock that stays open.

So it moves in here. Type a password, press Apply, and the next browser to
open the app is asked for it. What is stored is a PBKDF2 hash with a random
salt - not the password - so this file cannot be turned back into what you
typed, and neither can anybody who takes a copy of it.

**What it protects, and why it is worth having.** Not privacy from whoever runs
the NAS - they have the photographs anyway. The thing worth locking is that this
app MOVES things: cull, re-mirror, send to develop, clean up. Anything that can
reach the port can start those, and a mistaken tap from a device you lent
somebody is a real way to lose an evening.

**What it is not.** There are no accounts, no user list and no roles. One
password for the app. If you want your partner to have their own library, that
is a second container with its own folders, which is a far smaller thing to
arrange than a permissions model.

`PM_PASSWORD` still wins where it is set: something written into the compose
file is a decision made outside this app and must not be changeable from inside
it - otherwise anyone who got in once could take the lock off.
"""

from __future__ import annotations

from app.registry import Flag, Plan, Result, Row, Secret, Task, register
from core import access


def plan(opts) -> Plan:
    p = Plan(task="password")
    word = str(opts.get("word") or "")
    again = str(opts.get("again") or "")
    off = bool(opts.get("off"))
    out = bool(opts.get("everywhere"))

    if access.from_environment():
        p.blocked = (
            "The password is set in the compose file (PM_PASSWORD), which is a "
            "decision made outside this app - so it cannot be changed from "
            "inside it. Remove that line and rebuild if you want to manage it "
            "here instead.")
        return p

    on = access.is_on()
    p.stats = [
        ("The app is", "locked" if on else "OPEN to anyone who can reach it"),
        ("Signed-in browsers stay in for", f"{access.DAYS} days"),
    ]

    if off:
        if not on:
            p.blocked = "There is no password set, so there is nothing to remove."
            return p
        p.rows.append(Row(
            what="password", name="the password", source="", target="",
            detail="TAKE THE LOCK OFF - anyone who can reach this port gets in",
            cells=["removed", "everybody is signed out"],
            data={"off": True}))
        p.notes.append(
            "With no password, anything that can reach this port can not only "
            "look at the library but move, cull and re-mirror it. That is the "
            "half worth locking.")
        p.columns = ["What", "Happens", "And"]
        return p

    if out and not word:
        if not on:
            p.blocked = "There is no password set, so nobody is signed in."
            return p
        p.rows.append(Row(
            what="password", name="every browser", source="", target="",
            detail="sign out everywhere - every device has to type it again",
            cells=["signed out", "the password itself does not change"],
            data={"everywhere": True}))
        p.columns = ["What", "Happens", "And"]
        return p

    if not word:
        p.blocked = ("Type a password. Or tick 'Take the password off' to "
                     "unlock the app entirely.")
        return p
    if word != again:
        p.blocked = "The two boxes are not the same."
        return p
    if len(word) < 6:
        p.blocked = ("Six characters at the very least. This is the only thing "
                     "between the port and everything the app can move.")
        return p

    p.columns = ["What", "Happens", "And"]
    p.rows.append(Row(
        what="password", name="the password", source="", target="",
        detail=("changed" if on else "set for the first time"),
        cells=["changed" if on else "set",
               "every signed-in browser has to type it again"],
        data={"word": word}))
    p.notes.append(
        "Stored as a hash with a random salt, never as the password. Changing "
        "it signs every browser out, including this one - which is the point of "
        "changing it.")
    p.notes.append(
        "It travels over your home network in plain http, because that is what "
        "this is. Treat it as a lock on the door rather than a sealed envelope.")
    if not on:
        p.notes.append(
            "Scripts and the command line can still get in with HTTP Basic - "
            "user 'photos' (or PM_USERNAME) and this password.")
    return p


def apply(plan: Plan, progress=None, cancelled=None) -> Result:
    result = Result()
    if plan.blocked:
        result.details.append(plan.blocked)
        return result
    for i, row in enumerate(plan.rows, 1):
        status = "OK"
        try:
            if row.data.get("off"):
                if not access.set_password(""):
                    raise RuntimeError("the password file could not be written")
                result.details.append(
                    "The lock is off. Anyone who can reach this port can use "
                    "the app.")
            elif row.data.get("everywhere"):
                if not access.sign_out_everywhere():
                    raise RuntimeError("nothing could be written")
                result.details.append(
                    "Every browser is signed out, including this one.")
            else:
                if not access.set_password(row.data["word"]):
                    raise RuntimeError("the password file could not be written")
                result.details.append(
                    "Set. Reload the page and it will ask for it.")
            result.done += 1
        except Exception as exc:                        # noqa: BLE001
            status = result.blame(row.name, exc)
        if progress:
            progress(i, len(plan.rows), row.name, status)
    result.stats = [("Done", f"{result.done:,}"), ("Failed", f"{result.failed:,}")]
    return result


register(Task(
    name="password",
    line="Lock the app behind one password.",
    verb="Set the password",
    title="Password",
    parent="setup",
    tab="Password",
    summary="Locks the app behind one password. There are no accounts.",
    icon="key",
    order=95,
    options=[
        Secret("word", "New password",
               help="The new password, at least six characters. It is stored "
                    "as a salted hash, never as the password itself."),
        Secret("again", "Repeat password",
               help="The same password again, to catch a typing mistake you "
                    "cannot see."),
        Flag("everywhere", "Sign out everywhere", default=False,
             help="Signs out every browser, so each one has to type the "
                  "password again. Tick it alone to do only that. Changing "
                  "the password signs out everywhere anyway."),
        Flag("off", "Remove the password", default=False,
             group="Advanced", advanced=True,
             help="Removes the password. Anyone who can reach the port can "
                  "then use the app, including every tool that moves files."),
    ],
    plan=plan,
    apply=apply,
))
