"""One answer to "which frames are one shot", shared by everything that asks.

Previews makes one per bracket. Ratings sends a star to every frame of a set.
Cull keeps or puts aside a set whole. If those three grouped frames differently -
even slightly, even only when a camera is slow between frames - then one frame of
a set would get the preview and a *different* grouping would decide what to put
aside. That is worse than not grouping at all, because it is worse than either
answer taken consistently.

So the settings live in Setup, once, and every feature comes through here.
"""

from __future__ import annotations

from core import brackets as B
from core import settings as S


def sets_for(files, opts, plan=None, reader=None, probable=None):
    """The bracket sets among these files, or None when grouping is switched off.

    The per-task tick decides WHETHER to group; Setup decides HOW. A task never
    carries its own gap or set-size numbers, because that is exactly how two
    features come to disagree about the same shoot.

    `reader` is the run's `core.facts.Reader`, and passing it is worth as much as
    anywhere in the app: grouping reads the capture time of every picture in the
    tree, and five tasks do it. The same reader also serves the rest of that
    task, so a photograph is opened once for its clock, its rating, its keywords
    and its colour together.

    `probable=True` is a task's own "Include probable sets" box. It can only
    widen what Setup finds: a box that says "also thin the probable ones" and
    then finds none, because a Setup switch three screens away was off, is a
    box that does nothing (audit TK14).
    """
    if not opts.get("brackets", True):
        return None
    saved = S.load()
    p = saved.brackets()
    if probable:
        p["include_probable"] = True
    found = B.find(files, reader=reader, **p)
    if plan is not None:
        plan.notes.append(
            f"{len(found.sets):,} bracket set(s), grouped the way Setup says: "
            f"frames within {p['max_gap_seconds']:g}s, sets of "
            f"{p['min_set']}-{p['max_set']}"
            + (", hand-bracketed sets included." if p["include_probable"]
               else ", hand-bracketed sets left out."))
    return found
