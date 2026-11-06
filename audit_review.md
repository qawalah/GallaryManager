# Audit review: speed, robustness, ease of use, and an action plan

Written on 2026-10-12 against `main` at `e55aea4` (the commit that merged
`AUDIT.md`). No code was changed. This document does three things:

1. **Section 1 and 2** say where the code, the background work and the page
   can be faster, more robust and easier to use, without losing any option or
   feature. Every claim names the file and line it rests on.
2. **Section 3** challenges each finding in `AUDIT.md`. One is revised (O3),
   one has its open question settled (N2), and the rest hold, some with
   sharper evidence.
3. **Section 4** is the action plan, written as prompts an agent can be given
   one at a time. Each has a goal, the files, the steps, the constraints and
   the acceptance criteria.

Notation: `script.js` is `app/web/page/script.js`; `NN-name.js` is
`app/web/library/js/NN-name.js`; `server.py` is `app/server.py`.

## 0. What was measured

| Fact | Value | Where |
|---|---|---|
| Page served to the browser, uncompressed | 698 KB (script 500 KB, style 141 KB) | `app/page.py` `PAGE`; `_send` sets no `Content-Encoding` (`server.py:820-838`) |
| Background polls from one open tab, idle | `/api/jobs` every 0.7 s, `/api/health` every 5 s, `/api/index` every 2.5 s until the index settles | `script.js:933-935`, `01-router.js:70` |
| Polls while a run is on | `/api/progress` every 0.35-0.4 s | `script.js:3455`, `:8272` |
| Explorer open | `/api/files` for each pane every 5 s | `script.js:4696-4700` |
| Server loops | automation every 30 s, index check every 60 s | `server.py:2068`, `:2091` |
| Index refresh when anything wrote | one `os.walk` plus one `os.stat` per file | `core/catalogue.py:358-385` |
| Tools and options | 50 tools, 388 options, 150 of them backed by a Setup value, 25 tools with more than 6 options | registry dump |
| Biggest forms | Setup 38 options in 8 groups, Search 25, Colour meanings 25, Sort into folders 18 | registry dump |

## 1. Faster and more robust

Ranked by what a person would notice. "Effect" is an estimate, not a
measurement.

### 1.1 Speed

**S1. The page polls the server every 0.7 s for ever.** `showRunning`
(`script.js:634-660`) fetches `/api/jobs` on a 700 ms interval from boot,
whether or not anything is running, and on every answer calls `drawAuto`,
`drawBadge` and rewrites `#running`. Each answer makes the server take
`JOBS_LOCK` and read `/proc/loadavg` and two cgroup files
(`core/load.py:106-118`). A phone left on the page keeps the NAS awake. The
poll does not slow when the tab is hidden (only the explorer's peek checks
`document.hidden`, `script.js:4690`). *Fix:* poll every 2-3 s when nothing is
running and 700 ms only while `running` is non-empty; stop while
`document.hidden`; redraw only when the answer's hash changed. Effect: about
75 % fewer idle requests. Risk: low.

**S2. Every page of the grid re-scans the whole index.** `timeline()`
(`core/browse.py:275-326`) calls `matching()` on every request, which loops
over every row (`browse.py:86-150`) and runs `is_hidden` per row, then sorts,
then slices one page of 240. Scrolling an 80,000-photo library costs a full
Python pass per page. `inside()` and `clusters()` (`browse.py:703`, `:934`)
do the same. The caching that exists, `kept()` (`browse.py:226`), is used only
for overview, dashboard, choices, folders, people and albums
(`server.py:1061-1156`). *Fix:* cache `matching(cat, ask)` under `kept()`
keyed by the index generation plus the filter and the hidden list; cache
clusters per zoom. Effect: paging becomes a slice. Risk: low; `generation()`
already changes on every index or settings change.

**S3. The facts cache is loaded and rewritten whole, by every task.**
`facts.reader()` (`core/facts.py:350-360`) parses all of `facts.json` each
time it is called: once per index refresh (`catalogue.py:367`), once per
Search (`core/find.py:413`) and once per task plan that reads photographs.
`save()` (`facts.py:310-336`) rewrites the whole file. With 80,000 entries
that is a multi-megabyte parse and write per run. *Fix:* one shared `Reader`
per process behind a lock, saved on a short timer or after a run, not per
caller. Effect: removes a JSON parse from every plan. Risk: medium; see R2,
which this also fixes.

**S4. Thumbnails are made two at a time, whatever the machine has.** `thumb()`
takes a process-wide `_GATE = threading.Semaphore(2)` around Pillow
(`core/thumbs.py:59`, `:179-180`). On a one-core NAS that is right; on a
four-core NAS or a PC it leaves most of the CPU idle while the first visit to
a grid of 240 tiles decodes them two at a time, and nothing makes thumbnails
ahead of a visit. *Fix:* size the semaphore to `min(4, os.cpu_count())`, and
pre-make thumbnails for the newest few hundred photographs after an index pass
that added any. Effect: first paint of a new month up to 2x faster on a
multi-core machine, and instant for the newest photographs. Risk: low.

**S5. The page is 698 KB with no compression.** `_send` never gzips
(`server.py:820-838`) and marks the page `no-store`, so every open on a phone
over wifi or Tailscale downloads 700 KB. Python's `gzip` module is standard
library. *Fix:* gzip HTML, JS, CSS and JSON when `Accept-Encoding` allows it
and the body is over a few KB. Effect: the page drops from 698 KB to 202 KB
(measured with `gzip` level 6 on the built page), and JSON shrinks too.
Risk: low; the service worker (`app/web/page/sw.js`) caches responses as
given.

**S6. `/api/tasks` is fetched three times at start.** `script.js:936`,
`script.js:3366` and `12-tools-arranged.js:355` each fetch the full task
catalogue (every option and help text). *Fix:* fetch once at boot and share.
Effect: small. Risk: none.

**S7. The explorer re-lists folders every 5 s.** `fmPeek`
(`script.js:4665-4677`) fetches `/api/files` per pane, which stats every
file in the folder, and compares a signature. A 2,000-file folder costs
2,000 stats every 5 s while the explorer is open. *Fix:* 10-15 s, and stop
when the pane has not been touched for a minute. Effect: small. Risk: none.

### 1.2 Robustness

**R1. Request bodies are unbounded and unguarded.** `_body()`
(`server.py:1929-1931`) reads `Content-Length` bytes into memory with no cap
and lets a bad header or bad JSON raise. Most POST routes call it outside a
`try`, so a malformed request prints a traceback and drops the connection
(`do_POST`, `server.py:1338-1500`). *Fix:* cap at a few MB, return a 400 JSON
error on bad input, and wrap `do_GET`/`do_POST` so any unexpected exception
answers 500 JSON instead of closing the socket (which the page shows as
"could not reach the app").

**R2. Two runs can overwrite each other's facts.** Each caller has its own
`Reader` with no lock (`facts.py:160-230`); `save()` writes the whole dict.
An automation pass and a run you started both finish and the second write
wins, dropping the first run's notes. Only cache is lost, so the next pass
re-reads those files, but it is silent and it happens most on the busiest
libraries. *Fix:* as S3.

**R3. Index read errors vanish.** `refresh()` swallows every per-file
exception with `continue` (`catalogue.py:393-396`) and `state()` exposes no
error count. A library where 400 files cannot be read shows 400 fewer photos
with no line saying why. *Fix:* count failures and the first few names into
`state()`, and show them in the rail foot and the Checklist.

**R4. Nothing stops two writing runs on the same tree at once.** `_apply`
(`server.py:1937-1958`) checks only that *this* job has not already started.
A person pressing Apply on Sort into folders while an automation pass is
moving the same folder gets two passes moving files past each other. The
automation loop already guards against DSM-scheduled duplicates
(`server.py:2050-2065`) but not against the page. *Fix:* a per-tree write
lock (the task's `reads`/`moves_to` already name the trees); the second run
waits or is refused with a sentence.

**R5. Windows file locks are not retried.** Metadata writes do
`os.replace(tmp, path)` (`core/exifwrite.py:234`, `:342`, `:405`). On Windows
that raises `PermissionError` (WinError 32) while Lightroom or Explorer's
preview has the file open, where Linux succeeds. `CLAUDE.md` lists the port
as a goal. *Fix:* on `os.name == "nt"`, retry `os.replace` a few times with a
short backoff before giving up, and report the file by name.

**R6. Large plans are held in memory for a while.** A plan of 80,000 rows is
kept on the server for `KEEP_JOBS_SECONDS` (`server.py:804-811`) and in the
page's `SEEN` map. Several in a row from a big library is hundreds of MB. Not
a bug today; worth a cap on rows kept after a run finishes.

**R7. Good as it is.** Metadata writes are temp file plus `os.replace` with
owner and timestamp restore (`exifwrite.py:196-246`); the catalogue and
settings save the same way (`catalogue.py:118-137`, `core/settings.py:415-425`);
moves are recorded for undo (`core/moves.py`); the path fence uses `realpath`
(`server.py:168-175`); plans are kept server-side so Apply can never run a
page's edited copy (`server.py:525-535`). None of these need changing.

## 2. Easier to use, with every feature kept

**E1. One tool, two names.** The rail and tab row show `tab`, the Tools cards
and the guide show `title`, and 12 tools differ: Rating & tags / Sync,
Storage / Space, What can be cleaned up / Clean-up status, File explorer /
Explorer, Geotag / From my timeline, Location timeline / Combine & export,
Fix the clock / Time change, Find brackets / Check brackets, Import place names
/ Place names, Import Google Timeline / Import timeline, Put a run back / Put
it back, Clear the history / Clear the list (registry; drawn at
`01-router.js:170-177` and `05-places-albums-tools.js:360-366`). A person who
opens "Storage" from Tools finds themself on a tab called "Space". *Change:*
one name per tool everywhere; keep `tab` only where the tab row needs a
shorter word, and make the rail use `title`.

**E2. Three menus of "tools for these photos" that disagree** (AUDIT O2). The
selection bar, its Tools menu and the folder menu are hand-written lists
(`04-selection.js:107-120`, `:157-158`; `08-folder-albums.js:9-15`). *Change:*
derive all three from the registry: every tool whose first option is a
`Folder`, in family order. Nothing is lost; today's omissions (Geotag missing
from the Tools menu, Apply label missing from the folder menu) are fixed by
construction.

**E3. The first run has no path.** A new install lands on an empty Home with
Refresh and "See all photographs" (`02-home.js:33`, `:43`); the Checklist the
code meant to open is drawn underneath, unseen (AUDIT U4, D1; verified in a
browser). *Change:* with no library set, open the Checklist, and give Home and
the rail foot a real "Open Setup" button rather than the sentence at
`01-router.js:223`.

**E4. Three buttons called Refresh.** Header "Refresh" reloads the page
(`script.js:926-930`); Home "Refresh" and the rail's "Refresh now" re-index
(`02-home.js:33`, `01-router.js:226-233`). *Change:* "Reload page" in the
header, "Re-read library" for the other two.

**E5. Tabs that live under a tool from another group** (AUDIT O1). Opening
Cull from Review shows a tab row headed by Clean up from Maintain
(`core/families.py:43-50`; `parent="cleanup"` in `cull.py:289` and five
others). *Change:* make each tab's parent belong to its own group.

**E6. Forms: fold what Setup already answered.** 150 of 388 options fall back
to a Setup value (`Option.setting`, `app/registry.py:61-82`). They are drawn
as filled boxes, so a form like Sort into folders shows 18 boxes of which most
are "whatever Setup says". `fold_groups` exists but only Search uses it.
*Change:* draw setting-backed options as a one-line "From Setup: /volume1/..
(change)" summary that expands on press; apply `fold_groups` to every form
with more than 8 options. Every option stays reachable; the default view gets
shorter.

**E7. Search and the Photos filter panel look like two copies of one thing.**
They are not (see O3 below): Photos filters the index, Search walks folders,
including trees the index does not cover. *Change:* say so on each screen and
link them: Photos' filter panel gets "Search a folder instead" and Search's
result gets "Show in Photos" when the folder is in the library.

**E8. Deleting a folder means two different things** (AUDIT O4). The
explorer's delete takes RAWs and previews but not video
(`core/filesops.py:150`, `:353-363`); Delete folder takes video too and shows
a plan first (`app/tasks/delfolder.py:1-15`). *Change:* the explorer's delete
of a *folder* hands off to Delete folder's plan the way the selection bar
hands off with `pickInto` (`04-selection.js:226`); file deletes stay where
they are.

**E9. NAS-only tools on every machine** (AUDIT U5). The server already says
whether this is a desktop install (`out["desktop"]`, `server.py:251-252`), so
hiding Reindex and Permissions off the NAS is a page-side condition, not a
new flag.

**E10. Good as it is.** The four steps (Set it up, Check the list, Apply,
What happened: `script.js:1478`), one word per act (`WORDS`,
`script.js:1502-1510`), the confirmation only for high-risk plans
(`sureAbout`, `script.js:3875-3887`), the Back trail, pinned tools, the
21-page guide, the keys card and the Tools search are the strengths. Keep
them.

## 3. Challenging AUDIT.md

Each finding was re-read against the code, and three were re-tested in a
browser. "Holds" means the finding and its call stand as written.

| ID | Finding | Verdict | What the re-check found |
|---|---|---|---|
| U1 | 2.x Home unreachable, delete | Holds | The "fallback if the shell never runs" argument was tested in thought and code: `shellStart` is in the same script (`app/page.py:166`); an old server without `/api/index` makes `refreshIndex` catch and Home draw "could not reach" (`02-home.js:15-16`), so the 2.x home never appears either way. Delete, with `tests/test_consistency.py:110-117` and `tests/test_page_behaviour.py:185`, `:793` updated. |
| U2 | 2.x side menu | Holds | Hidden by `02-viewer-panel.css:35`; replaced by the rail and Tools search. "Lately" is the only loss; put it in the rail if wanted. |
| U3 | 2.x bottom bar | Holds | Overwritten on every rail draw (`07-joining.js:40-41`). |
| U4 | Checklist never shows on first run | Holds | Verified in headless Chromium: `SCREEN = "home"`, `CURRENT = checklist`. |
| U5 | NAS-only tools on Windows | Holds, smaller | The server already sends `desktop` (`server.py:251-252`); this is a page condition. |
| U6 | Undo and Forget only from History | Holds | Deliberate (`app/registry.py` comment above `acts`). |
| D1 | Home on an empty library | Holds | Only Refresh and See all photographs (`02-home.js:33`, `:43`). |
| D2 | Stopped page | Holds | Nothing to link to. |
| D3 | Lost password | Holds | Neither README mentions resetting (`nas/README.md`, `windows/README.md:78` only says to set one). The file is `access.json` (`core/access.py:49`). |
| O1 | Tabs under another group's parent | Holds | `families.py:43-50` against `parent="cleanup"` in six tasks and `parent="library"` in `space.py:230`, `tidy.py:161`. |
| O2 | Three hand-written tool lists | Holds | Also the selection bar itself (`04-selection.js:107-120`). |
| **O3** | Search and Photos filters: merge the screens | **Revised: keep both, link them** | Search does not read the index. `search.py:103` calls `find.search(folders, ...)`, which walks the folders and reads files (`core/find.py:408-420`), so it can search the previews, RAW, develop and video trees and any folder, indexed or not. Photos filters only the index (`browse.py:86-150`). Merging the screens would lose searching outside the index. See E7. |
| O4 | Explorer delete and Delete folder | Holds, sharpened | `partners(path, with_raw, with_previews)` (`filesops.py:150`) has no video branch; `delete()` (`:353-363`) calls only that. Delete folder handles video. |
| O5-O8 | Library vs board; status/clean/storage; three re-mirrors; History vs Runs | Hold | Different sources or different matching rules in each case. |
| O9 | `label` / `labels` | Holds, minor | Titles differ already; CLI names stay. |
| O10 | `/api/gate` vs `/api/client` | Holds | Page uses neither; check the client contract before removing `gate`. |
| O11 | Two `13-*.js` | Holds | Rename the viewer-panel one to 16. |
| N1 | `/api/overview` unused | Holds | No caller in page, tests or docs. |
| **N2** | Six page functions unused | **Holds; `fmView` caveat resolved** | The audit wondered if `fmView` was a lost button. It is not: the list/grid switch is the pane menu at `script.js:5384-5415`. `fmView` is the old toggle. Delete all six and the `editor === "boards"` branch. |
| N3 | `i-heart` icon | Holds | |
| N4 | Nine Python functions | Holds | None referenced in tests or docs. `_entry_for` (`catalogue.py:495`) is an older copy of `_read_entry`. |

**What the audit missed.** It mapped reachability and overlap and did not
look at cost or failure: the constant polling (S1), the per-page index scans
(S2), the facts cache being loaded whole per run and racing between runs
(S3, R2), the unbounded request body (R1), concurrent writing runs (R4),
Windows file locks (R5), the 698 KB uncompressed page (S5), and the two-names
problem (E1). Those are the larger wins.

## 4. Action plan

Each task below is written so it can be handed to an agent as its whole
instruction. Give them one at a time, in order within a phase. Phases are
ordered by value against risk: safety first, then speed, then ease of use,
then clean-up. Every task carries the same standing rules, so they are stated
once here and each prompt says "standing rules apply":

> **Standing rules.** Read `CLAUDE.md` first and keep to its layers table:
> UI work stays in `app/web/**` (and `app/page.py` only for GUIDE, ART and
> themes); feature work stays in `app/tasks/<name>.py` and `core/`; the API
> boundary is `app/server.py`. Do not remove or hide any option or feature;
> every tool and option reachable before the change stays reachable after
> it. Add or adjust a test in `tests/` for every behaviour change; never skip
> or delete a test to get green. Run `python -m unittest discover -s tests -t .`
> and `sh scripts/check.sh` before you finish, and report the output. Work on
> a branch and open a pull request; never commit to `main`. If a change
> touches a function, route, setting, file name or shared constant, update
> every other file that uses it (backend, page, Windows, NAS, docs, CLAUDE.md)
> in the same change, and list those files in the PR. Never point the app at
> real photos; use `tests/fixtures/` or the sample library in a temp folder.
> Keep each PR to the one task.

### Phase 1: safety and robustness

**Task 1.1: Guard request bodies and unexpected errors.** (R1)

```text
Standing rules apply. In app/server.py, make _body() (around line 1929) refuse a
Content-Length over 8 MB and bad JSON with a 400 JSON answer {"error": ...}
instead of raising. Wrap the bodies of do_GET and do_POST so any unexpected
exception answers 500 with {"error": "<one line>"} and logs the traceback,
instead of closing the socket. Keep every existing route and behaviour.
Add tests in tests/test_server.py (or the nearest existing server test module)
for: oversized body -> 400; invalid JSON -> 400; a route that raises -> 500 JSON.
Acceptance: all tests green; the page's "Could not reach the app" message no
longer appears for a malformed POST.
```

**Task 1.2: One facts reader per process, locked, saved once.** (S3, R2)

```text
Standing rules apply. Read docs/DESIGN.md on the facts cache and core/facts.py
first. Change core/facts.py so reader() returns one shared Reader per store
path, guarded by a threading.Lock around _entry, _field, forget and save, and
so save() is called by a short-lived timer or at the end of a run rather than by
every caller. Keep the signature check on every ask (the docstring explains
why). Keep the per-run read/reused counters correct per caller (a small
per-run view over the shared store is fine). Update core/catalogue.py
(refresh, around line 367) and core/find.py (search, around line 413) and any
task that calls facts.reader() so they still work unchanged.
Add tests: two threads reading and saving concurrently lose no entries; a
file rewritten between two asks is re-read; the facts file is written once
per run rather than once per caller.
Acceptance: tests/test_facts.py and the full suite green; no task reads
facts.json more than once per process start.
```

**Task 1.3: Say which files the index could not read.** (R3)

```text
Standing rules apply. In core/catalogue.py refresh() (around lines 390-396),
count files that raised while being read and keep the first 20 names with the
error text. Expose "unreadable": count and "unreadable_names": [...] in
state(). In the page, show the count in the rail foot (01-router.js indexLine)
and as a line in the Checklist (app/tasks/checklist.py) with the first names.
Acceptance: a fixture with one unreadable file shows "1 file could not be
read" in both places; tests added in tests/test_catalogue.py and
tests/test_checklist.py.
```

**Task 1.4: Stop two writing runs on the same tree.** (R4)

```text
Standing rules apply. In app/server.py, add a per-tree write guard used by
_apply (around line 1937) and by the automation pass (app/tasks/automation.py
one_pass): a task whose plan writes to a Setup tree (use Task.reads,
copies_to, moves_to and Plan.impact) cannot start while another writing run
on an overlapping tree is still running. The second one is refused with a
plain sentence naming the running task, or queued if the run is automation.
Do not change read-only tasks. Add tests for: two writing runs on the same
tree, one refused; a reading run alongside a writing run, allowed; the guard
released when the run finishes or fails.
Acceptance: tests green; the page shows the sentence when Apply is refused.
```

**Task 1.5: Retry metadata replaces on Windows.** (R5)

```text
Standing rules apply. In core/exifwrite.py (os.replace at about lines 234, 342,
405) and anywhere else metadata is written with os.replace (core/sidecar.py,
core/tagwrite.py), route the replace through one helper in core/perms.py or a
new core/replace.py that, on os.name == "nt", retries PermissionError up to 5
times with 0.2 s, 0.4 s, 0.8 s... backoff, then raises with the file name in
the message. On other platforms it is a plain os.replace. Add a test that
monkeypatches os.replace to fail twice then succeed and asserts the retry.
Acceptance: full suite green on Linux; the helper is the only os.replace call
on photo files.
```

### Phase 2: speed

**Task 2.1: Adaptive polling and no redraw when nothing changed.** (S1)

```text
Standing rules apply. In app/web/page/script.js, change showRunning (around
line 634) and its setInterval at line 935 so the page polls /api/jobs every
700 ms only while the last answer had a running job, every 2500 ms otherwise,
and not at all while document.hidden is true (resume at once on
visibilitychange). Compare a cheap hash of the answer and skip drawAuto,
drawBadge and the #running rewrite when it is unchanged. Keep the "a run
finished while you were away" behaviour (noteFinished) exactly as it is.
Apply the same hidden-tab pause to checkHealth (line 933) and tickIndex
(01-router.js:70). Add a Playwright test in tests/test_page_behaviour.py that
counts /api/jobs requests over 5 s with nothing running and asserts at most 3.
Acceptance: sh scripts/check.sh passes; existing page tests green.
```

**Task 2.2: Cache the matched rows per filter.** (S2)

```text
Standing rules apply. In core/browse.py, make timeline(), inside() and
clusters() reuse kept() (line 226) so that matching(cat, ask) for a given
filter, hidden-folder list and index generation is computed once and sliced per
page, and clusters are kept per zoom. Include the hidden folders file's stamp
in generation() so leaving a folder out invalidates the cache. Do not change
any answer's shape. Add tests in tests/test_browse.py: two pages of the same
filter call matching once; a change to hidden folders or the index invalidates.
Acceptance: tests green; the /api/timeline answer is byte-identical before and
after for the fixture library.
```

**Task 2.3: Gzip responses.** (S5)

```text
Standing rules apply. In app/server.py _send and _json (around lines 820-838),
gzip the body with the standard library when the request's Accept-Encoding
includes gzip and the body is over 4 KB and the content type is text, JSON,
JavaScript, CSS or SVG. Set Content-Encoding and Vary: Accept-Encoding; keep
the existing Cache-Control rules. Never gzip images, video or downloads.
Add tests: a request with Accept-Encoding: gzip gets a gzipped page that
decompresses to the same bytes; one without gets plain. Check the service
worker (app/web/page/sw.js) still serves the cached page.
Acceptance: tests green; the page transfers at about 200 KB (202 KB measured
at gzip level 6 on 2026-10-12).
```

**Task 2.4: Size the thumbnail gate to the machine, and warm the newest.** (S4)

```text
Standing rules apply. In core/thumbs.py, _GATE (line 59) is a
threading.Semaphore(2). Size it to min(4, os.cpu_count() or 1) instead, and
add a function warm(paths, size="s") that makes thumbnails for a list of paths
on a daemon thread, called from the index loop in app/server.py after a
refresh that added photographs, for the 300 newest. Pillow stays optional:
without it both are no-ops. Add tests: the gate allows as many makes at once
as the machine's count; warm() creates files in the thumbs folder for the
fixture library.
Acceptance: tests green; no change to the thumbnail bytes.
```

**Task 2.5: Fetch the task catalogue once.** (S6)

```text
Standing rules apply. The page fetches /api/tasks at app/web/page/script.js
lines 936 and 3366 and app/web/library/js/12-tools-arranged.js line 355. Keep
one copy (TASKS, loaded at boot) and have the other two callers reuse it,
re-fetching only after a change that alters the catalogue (saving Setup, the
tool arrangement, or pins). Acceptance: a Playwright test asserts one
/api/tasks request during boot; existing tests green.
```

### Phase 3: ease of use

**Task 3.1: One name per tool.** (E1)

```text
Standing rules apply. For every task in app/tasks/*.py whose tab differs from
its title, decide one name and use it everywhere: the rail
(app/web/library/js/01-router.js railFam), the Tools cards
(05-places-albums-tools.js featureRow), the tab row (script.js around line
1578), the guide (app/page.py GUIDE) and the menus. Keep CLI names unchanged.
Where a tab row needs a short word, keep tab for the tab row only and make the
rail and cards use title. Update tests/test_wording.py and
tests/test_consistency.py as needed; add a test that the rail label and the
Tools card label for each tool are the same string.
Acceptance: tests green; no tool is shown under two names on one screen.
```

**Task 3.2: One source for "tools for these photos".** (E2, AUDIT O2)

```text
Standing rules apply. Replace the three hand-written lists in
app/web/library/js/04-selection.js (PICKBAR lines 107-120, toolsMenu 157-158)
and 08-folder-albums.js (useFolder lines 9-15) with one list built from TASKS:
every task whose first option is a Folder, in core/families.py order, grouped
by family. Keep the four promoted buttons on the selection bar (Rate, Geotag,
Sort into folders, Send to develop) and move everything else into the menu.
Nothing that was offered before may disappear. Add a Playwright test that the
folder menu and the selection Tools menu list the same tools.
Acceptance: sh scripts/check.sh and page tests green.
```

**Task 3.3: A real first run.** (E3, AUDIT U4, D1)

```text
Standing rules apply. In app/web/library/js/01-router.js shellStart (lines
51-70), when TREES.library is empty and the checklist task exists, open the
Checklist feature instead of Home (the same test boot() makes at script.js
lines 1049-1051). On Home (02-home.js) and in the rail foot (01-router.js
indexLine, line 223), when nothing is indexed, show two buttons: "Open Setup"
and "Build a sample library", the same pair Photos already shows
(03-photos.js:391-392). Update app/tasks/checklist.py's docstring only if the
behaviour it describes changes. Add Playwright tests: empty PM_DATA lands on
the Checklist; Home with no library shows the two buttons.
Acceptance: tests green; a fresh start opens on the Checklist.
```

**Task 3.4: Explorer folder delete goes through Delete folder.** (E8, AUDIT O4)

```text
Standing rules apply. In app/web/page/script.js, where the file explorer
deletes a selection, if the selection contains a folder, open the Delete
folder feature with that folder filled in (use openFeature(name, {folders})
from 01-router.js as pickInto in 04-selection.js does) instead of calling
/api/files delete. Deleting files stays as it is. Do not change
core/filesops.py delete() semantics for files. Add a Playwright test: picking
a folder and pressing Delete lands on Delete folder with the folder in the
box.
Acceptance: tests green; a folder deleted from the explorer takes its video
with it, because Delete folder does.
```

**Task 3.5: Tabs belong to their own group.** (E5, AUDIT O1)

```text
Standing rules apply. Read docs/DESIGN.md on families and tabs first. Make each
task's parent belong to the same family as the task in core/families.py:
cull, blur, duplicates, brackets, thin and exposure (parent="cleanup", in
Maintain) get a Review parent (cull is the natural one, with the others as its
tabs); space and tidy (parent="library", in Review) move under cleanup in
Maintain. Keep every task's name, options and behaviour. Update
tests/test_families.py (or wherever the family rules are tested) and any
guide "covers" lists in app/page.py GUIDE.
Acceptance: tests green; opening any tab shows a tab row whose tools are all
in the same group as it.
```

**Task 3.6: Hide NAS-only tools off the NAS.** (E9, AUDIT U5)

```text
Standing rules apply. /api/tasks already returns "desktop": true on a PC
(app/server.py around line 251). In app/web/library/js (rail, Tools screen,
Settings group) and script.js (tab row, TABGROUPS at line 188), do not list
reindex and permissions when desktop is true, and show one line in Setup
saying they are NAS-only. The tasks stay registered and the CLI unchanged.
Add a test that with desktop true the rail and Tools screen omit them and
with desktop false they are shown.
Acceptance: tests green; python -m app.cli reindex --help still works.
```

**Task 3.7: Link Search and Photos both ways.** (E7, AUDIT O3 revised)

```text
Standing rules apply. In app/web/library/js/03-photos.js, add to the filter
panel a button "Search a folder instead" that opens the search feature with
the current filters carried over as options (map FILTER keys to the search
task's option names in app/tasks/search.py). In the search result
(script.js around line 6612, searchFor and its renderer), add "Show in
Photos" when the searched folder is inside the library root, opening Photos
with the same filter. Add one line of help on each screen saying which one
reads the index and which reads folders. Add Playwright tests for both links.
Acceptance: tests green; neither screen loses any option.
```

**Task 3.8: Distinct names for the three Refresh buttons, and a lost-password line.** (E4, AUDIT D3)

```text
Standing rules apply. Rename the header button at script.js line 926 to
"Reload page" and the two re-index buttons (02-home.js:33, 01-router.js:226)
to "Re-read library". Update tests/test_wording.py. In app/web/login.html add
one sentence under the form saying that a lost password is reset by removing
access.json from the settings folder (PM_DATA) or by setting PM_PASSWORD, and
add the same to nas/README.md and windows/README.md. Acceptance: tests green;
wording tests updated.
```

**Task 3.9: Fold what Setup already answers.** (E6)

```text
Standing rules apply. In app/web/page/script.js form drawing (around lines
1600-1700), draw any option with a setting (Option.setting, app/registry.py
line 61) whose value is still the saved default as one line "From Setup:
<value> (change)" that expands to the full control on press; a changed value
draws the control as now. Apply Task.fold_groups behaviour to any form with
more than 8 options. Every option must remain editable and its value must
still be sent by values(). Add Playwright tests: Sort into folders opens with
the setting-backed options folded; pressing (change) reveals the control; the
plan request carries the same options as before.
Acceptance: tests green; no option removed.
```

### Phase 4: clean-up (no behaviour change)

**Task 4.1: Remove the unused route, functions and icon.** (AUDIT N1-N4)

```text
Standing rules apply. Delete: GET /api/overview (app/server.py lines 1058-1061;
keep core/browse.overview, which dashboard uses; fix the comment at
01-router.js:7); goHome, fmView, mapLatLon (script.js 4043, 5660, 8455);
jumpTo (01-router.js:241); settingsTasks (05-places-albums-tools.js:399);
arrShow (12-tools-arranged.js:187; keep arrPut and arrHide, tests use them);
the editor === "boards" branch (script.js:1682); the i-heart icon
(app/web/library/icons/01-library.svg:21); and the Python functions
defaults_for and _saved (app/tasks/setup.py:56, :198), _targets
(app/tasks/ratings.py:50), tidy_if_long (core/acl.py:265), tails
(core/renames.py:442), _atom (core/demo.py:260), place_of
(core/places.py:477), start_page (core/desktop.py:394), _entry_for
(core/catalogue.py:495). Before each deletion, grep the whole repo including
tests and docs for the name and stop if anything references it.
Acceptance: full suite and sh scripts/check.sh green; the served page is
identical except for the removed code.
```

**Task 4.2: Remove the hidden 2.x screens.** (AUDIT U1-U3)

```text
Standing rules apply. Read docs/DESIGN.md on the 3.0 library shell first.
Remove the 2.x home (drawHome, wantsHome, loadSummaryData if unused, the home
half of setHome, #home and #viewswap in app/web/page/index.html lines 42 and
57, the pm_home setting), the 2.x side menu (navRow, findWords, navFilter,
recentList, pushRecent, drawRecent at script.js 783-870 and the fill at 958,
and main > nav#nav) and the 2.x bottom bar (BOTTOM, drawBottom at script.js
4491-4521). Keep every feature reachable through the rail, drawer, phone bar
and Tools screen; if removing the side menu loses the "Lately" list, add it to
the rail instead. Update tests/test_consistency.py (lines 110-117) and
tests/test_page_behaviour.py (lines 185, 793) and any CSS for the removed
elements in app/web/page/style.css. Rename
app/web/library/js/13-viewer-panel-sync.js to 16-viewer-panel-sync.js.
Acceptance: full suite, Playwright tests and sh scripts/check.sh green; a
screenshot of Home, Photos, Tools and one feature on desktop and at 390 px
matches before and after.
```

**Task 4.3: Fold `/api/gate` into `/api/client`.** (AUDIT O10)

```text
Standing rules apply. Check the client contract document (outside this repo,
"photo-manager-client-contract.md" in the project) for any use of /api/gate.
If none, add the "fixed" field to /api/client (app/server.py around line
952), remove /api/gate (line 947) and move its test in tests/test_access.py
line 295 to /api/client. If the contract uses gate, leave it and record that
in docs/DESIGN.md.
Acceptance: tests green.
```

### Order of work

Phase 1 first, in order (1.1 and 1.5 are small; 1.2 and 1.4 are the ones to
review carefully). Phase 2 next; 2.1 and 2.3 are the ones a person feels. In
Phase 3, do 3.1 before 3.2, since 3.2 draws the names 3.1 settles; 3.3 and
3.4 are the two that remove real traps. Phase 4 last, 4.1 before 4.2, so the
2.x removal is a smaller diff.
