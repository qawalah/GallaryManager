# Photo Manager

A photo-library manager: sorts, geotags, rates, tags, culls and de-duplicates
photos, splits RAWs, videos and previews into mirror trees, and runs all of
that on a schedule. Pure Python 3.10+, standard library only (Pillow and
ffmpeg are optional). One web page is the interface; every feature also runs
from the command line. Today it runs as a container on a Synology NAS
(`nas/`); the goal is to run fully on Windows too (see the last section). The
same code serves both.

## Ground rules (read every time)

- **Only the project folder.** On ALI's PC, work only inside
  `C:\Users\PCD\Documents\AI Apps\Claud\Photo Manager` and in worktrees under
  its `.claude\worktrees\`. Never read, write, list or run anything else on
  the machine: not real photo libraries (`N:\Photos`), not
  `%LOCALAPPDATA%\PhotoManager`, not other projects. If a task seems to need
  another folder, stop and ask.
- **Never point the app at real photos.** Use `tests/fixtures/` or build the
  sample library (`demo` task, *Setup > Sample library*) in a temp folder.
  Every task with `--apply` moves, renames or rewrites real files.
- **Tests are the spec.** Add or adjust a test with every behaviour change.
  Never skip, weaken or delete a test to get green.
- **No feature or option may disappear.** Everything reachable before a change
  is reachable after it. Renaming, grouping and folding are fine; removing or
  hiding is not, unless the task says so.
- **Follow a change across files.** If you touch a function, route, setting,
  option name, file name or shared constant, update everything that uses it
  (server, page, CLI, NAS, Windows, docs, this file) in the same change, and
  list those files in the PR.
- **Branch and pull request, never `main`.** Repo: `qawalah/GallaryManager`
  (moved from `alialyami90/JIC`; see HANDOVER.md). A merge to `main` is a
  release when `devstore.json` has a new `version` (see DevStore below).
- **Plan first, then apply.** A feature that writes says exactly what it will
  do before it does it. Keep the four steps: set up, check the list, apply,
  what happened.
- **Keep the served page identical unless the change is meant to alter it.**

## Where to edit, by kind of change

| Change | Edit | Leave alone | Then run |
|---|---|---|---|
| Look, screens, browser behaviour | `app/web/**`; `app/page.py` only for `GUIDE`, `ART`, `PALETTES`, `ACCENTS`, `CHROMES` | `core/`, `app/tasks/` | `sh scripts/check.sh`, `tests.test_page_behaviour`, `test_consistency`, `test_design`, `test_wording` |
| A feature or tool | `app/tasks/<name>.py` and the `core/` modules it uses | `app/web/` (forms are drawn from declared options) | `tests.test_<name>` |
| Photo logic (files, EXIF, XMP, GPS, index) | `core/*.py` | `app/web/` | the module's tests, `test_catalogue`, `test_facts` |
| Page-to-server API | `app/server.py` (`do_GET` / `do_POST`, routes under `/api/`) and the page code that calls it, in one PR | | `test_server`, `test_web` |
| NAS deployment | `nas/` | | `test_startup` |
| Windows program | `windows/`, `core/desktop.py` | | `test_desktop` |

Import direction: `core` imports nothing from `app` (three deliberate lazy
exceptions inside functions in `core/flows.py`, `core/identity.py`,
`core/exclude.py`). `app/tasks` imports `core`, `app.registry`,
`app.grouping`. Keep it that way.

## Layout

```
core/            photo logic: files, EXIF (JPEG and HEIC), XMP sidecars, GPS, the index
                 (catalogue.py), browsing (browse.py), the read cache
                 (facts.py), moves + undo (moves.py), settings, thumbnails,
                 local wording edits (wording.py, applied in Task.describe)
app/registry.py  Task / Option / Plan / Result: how a feature declares itself
app/tasks/       one module per feature (51); __init__.py imports them all
app/server.py    HTTP server and JSON API, background jobs, automation and
                 index loops, login
app/cli.py       python -m app.cli <task> [--opt ...] [--apply]
app/page.py      assembles the page from app/web/page/*; holds GUIDE, ART
                 and the theme tables as Python data (tests read them)
app/libraryui.py joins app/web/library/* (the 3.0 library shell)
app/grouping.py  "which frames are one shot", shared by several tasks
app/version.py   which code is running (page header)
app/wordsource.py where each tool's text is written in the source (Wording
                 export, tools/merge_wording.py)
app/pagetext.py  the page's own strings and the Guide as Wording keys
                 (page.*, guide.*), put into the page as it is served
app/icons.py     generated app icons (tools/make_icon.py)
app/web/         everything the browser runs (next section)
core/families.py every feature under one of five headings; a test fails if
                 one is missing
nas/             Synology container: docker-compose.yml, start.sh, run.py,
                 README.md (install guide)
windows/         PC program: PhotoManager.pyw, tray.py, Install/Stop/
                 Uninstall.bat, wheels/ (bundled Pillow, pi-heif), README.md
scripts/         check.sh (build page + JS parse), doctor.py (environment),
                 *.bat double-click wrappers
tools/           dev-only: make_fixtures.py, make_icon.py (need Pillow),
                 fetch_wheels.py, mutate.sh, verify_with_pillow.py,
                 merge_wording.py (an exported wording.json into app/tasks)
tests/           about 2,680 unittest tests in 91 modules; fixtures/ committed
docs/            DESIGN.md (why things are as they are), ROADMAP.md (planned)
PRODUCT.md       who the app is for, what it promises, voice and accessibility
                 target (read before design work; /impeccable reads it)
DESIGN.md        the visual system as tokens and rules (4.0, the catalogue);
                 .impeccable/design.json is its machine copy. Not the same
                 file as docs/DESIGN.md, which explains behaviour
CHANGELOG.md     what each release (RELEASE in app/version.py) changed
```

## How a feature works

```python
register(Task(name="cull", title=..., summary=..., options=[Folder(...), Number(...)],
              plan=plan, apply=apply, verb=..., unit=..., reads=(...), moves_to=(...)))

def plan(opts) -> Plan      # reads, decides, writes NOTHING
def apply(plan) -> Result   # does what the plan said
```

- The page draws the form and the CLI builds `--help` from `options`. A new
  feature needs no UI or API work.
- `Task` fields worth knowing (`app/registry.py` explains each): `parent` +
  `tab` (a tool that belongs with another; its default group comes from
  `core/families.py`, not from `parent`. Every tool is a page of its own with
  no tab row; the list beside it is its group as arranged on All tools,
  `library/js/22-tool-side.js`. The rail and that list show `tab`, so keep it
  the title unless a shorter word reads better; `test_wording` fails a tab
  that is not its title or a shortened form of it),
  `hidden`, `settings` (saves instead of planning), `inline` (opened from a
  row, like Undo from History), `fold_groups` (option groups start folded),
  `verb` / `unit` / `risk` / `undo` (confirmation wording, `impact_of`),
  `reads` / `copies_to` / `moves_to` (Setup trees, so flows can detect loops).
- Options with `setting=` fall back to the Setup value.
- Adding a feature: the module, one import line in `app/tasks/__init__.py`,
  an entry in `core/families.py`, and `tests/test_<name>.py`. A tab's
  `parent` should be in the same family as the tab.
- Features move rather than delete: culls to `_Culled`, duplicates to
  `_Duplicates`, and so on, recorded in `core/moves.py` so a run can be
  undone. Delete in the viewer and explorer means the share's `#recycle`.
  Only Clean up (`core/cleanup.py`) really removes files, and only from piles
  this app made. Metadata writes go to a temp file then `os.replace`, then
  restore timestamps and permissions (`core/perms.py`).

## The page (`app/web/`)

```
page/index.html     the frame; {{STYLE}} {{ICONS}} {{SCRIPT}} {{GUIDE_JSON}}
                    {{LOOKS_JSON}} {{STRINGS_JSON}} are the only
                    {{UPPER_CASE}} slots
page/style.css      the features' stylesheet; the 4.0 tokens at its top
                    (palette, --t-* type scale, --r-* shapes, --ease and
                    --t-fast/mid/slow motion) are the only place those live
page/script.js      the features' script: one global scope, no modules
page/strings.json   every string the script shows that is not a tool's
                    (S.name, say("name", {n})); edited on Setup > Wording
page/strings.js     reads it into S, with the Wording edits on top
page/icons.svg      the <svg><defs> sprite; library icons are added before
                    its closing </defs></svg>
page/sw.js          service worker; __RELEASE__/__CODE__ filled by server.py
library/{css,js,icons}/NN-name.*   the library screens, joined in file-name
                    order after the page's own; give a new piece the next
                    number. css/14-catalogue.css and js/23-catalogue.js are
                    the 4.0 look: section inks (body[data-tone] -> --sec),
                    the turn between screens, the #said live region
fonts/*.woff2       Archivo (OFL.txt beside it), served at /font/<name>
                    before the login gate, cached by sw.js
login.html (standalone)
```

- Plain files, no build step, no framework. Everything ends up inline in one
  HTML page, so all JS shares one global scope and the order of `library/js`
  matters. Files are read once at import: restart the server to see an edit.
- The look (4.0, "the catalogue", visual rules in `DESIGN.md` at the root):
  every font size is on the scale 12/13/14/16/20/28/40/64, the accent is the
  page's own ink, the only other colours are the five section inks
  (`--tone-*`, one per group's `tone` in `core/families.py`), and a state is
  banded across the top, never striped down a side. Everything is cut square
  (`--r-pill` is 2px too). In the light the ground and cards are both white,
  so a fill on a card uses `--wash`, never `var(--bg)`. `test_design.TheCatalogue`
  holds these. The look before 4.0 is the Original palette with the Blue
  accent under Appearance.
- Lists of tools shown to the user (menus, selection bar, Tools cards) are
  built from the registry (`/api/tasks`), not written by hand.
- The server already says whether this is a desktop install (`desktop` in
  `/api/tasks`); use it rather than adding a flag.
- Two worktrees that both edit `page/script.js` or `app/server.py` will
  conflict, so prefer a new `library/js/NN-*.js` piece over growing the big
  file.

## Commands

From the project root (any checkout or worktree; `scripts\*.bat` wrap the
same on Windows):

```
python -m unittest discover -s tests -t .      # all tests: about a minute;
                                               # with Playwright + Chromium the
                                               # browser tests add several minutes
python -m unittest tests.test_cull             # one module
sh scripts/check.sh                            # build page + JS syntax check
python -m app.server                           # page on http://localhost:8080
python -m app.cli                              # list tasks
python -m app.cli cull --help
python scripts/doctor.py                       # environment check
tools/mutate.sh <file> <old> <new> [tests]     # check a test would catch a bug
```

Before a PR: full tests green, `check.sh` prints `JS_OK`, and the files you
changed are the ones the table above allows. Set `PM_DATA` to a temp folder
so tests do not write `config/facts.json` into the tree (harmless and
git-ignored if you forget).

Environment: `PM_DATA` (settings and caches; default `config/` beside the
code, git-ignored), `PORT` (8080), `PM_PUBLIC_PORT` (the port shown to
phones when a container maps it), `ALLOWED_ROOTS` (fence the page to some
folders, separated by `os.pathsep`: `;` on Windows, `:` elsewhere; unset on
a PC program the fence is Setup's folders plus Also allowed, `server.fence()`),
`PM_PASSWORD` / `PM_USERNAME` (login; `PM_USERNAME` defaults to `photos`),
`PM_HOSTS` (extra names a no-password app answers POSTs under, commas),
`PM_TRUSTED_PROXY` (proxy addresses whose `X-Forwarded-For` is believed),
`PM_DESKTOP=1` (set by the Windows launcher), `PM_DEVELOPER=1` (shows
Setup > Wording, like Setup's developer switch), `DETAIL_LINES` (CLI detail
rows, 20). NAS container only: `PM_USER` (`uid:gid` or `root`), `PM_PILLOW=skip`.

Optional: Pillow (previews, thumbnails, sample library, many tests),
pi-heif or pillow-heif (HEIC thumbnails and previews; HEIC dates and GPS are
read without it, `core/heif.py`; the HEIC fixtures need pillow-heif),
ffmpeg/ffprobe (video times), Playwright + Chromium (`tests/test_page_behaviour.py`
skips itself without them). Without them the related tests skip.

Known flaky: a few same-second sidecar tests (`test_automation.NoticingAChange`,
`test_facts`, `test_tagwrite`) fail intermittently in the Claude desktop
app's Linux sandbox on ALI's PC and pass in a normal Linux checkout. Rerun
before treating them as a regression.

## Conventions

- Standard library only in the base app. Anything optional degrades with a
  clear message, never a traceback.
- Comments and docstrings explain *why*, in plain sentences. Match that.
- Page wording is tested (`tests/test_wording.py`): a label is a name, not a
  sentence; the explanation goes in the help bubble. Call a thing by one name
  everywhere it appears. Every option has help; no dash as a full stop, no
  capitals for emphasis, no sentence over 25 words, no word the glossary
  replaced (photograph, clip, task, keyword...); a number's label or help
  names its unit. The rules are data in `core/wording.py`.
  To rewrite a lot of text, edit it on Setup > Wording (developer switch),
  download wording.json and merge it with `tools/merge_wording.py`.
  A string the script shows goes in `app/web/page/strings.json` and is read
  as `S.name` or `say("name", {n})`, never written inline; a test fails a
  name the table lacks or one nothing uses.
- Generated, never hand-edited: `app/icons.py`, `windows/PhotoManager.ico`,
  `windows/wheels/*`, `tests/fixtures/*`. Regenerate with `tools/`.
- `.bat` files are CRLF; `.gitattributes` handles it. Nothing uses an
  absolute path: everything resolves from `__file__`.
- Worktrees go under `.claude/worktrees/<name>` (what `claude --worktree`
  does), one branch each, split along the table above.

## Where docs/DESIGN.md explains a behaviour

Read the section before changing the behaviour it explains.

| Changing | docs/DESIGN.md section |
|---|---|
| The index, Home or the library screens | "3.0: a photo library with the features behind it" |
| Any task's shape, plan/apply, the four steps | "Why a registry", "The same four steps on every feature", "Saying what is about to happen, in four facts" |
| The read cache (`core/facts.py`) | "Reading a photograph once, and not at all the next time" |
| Flows and automation | "A flow is data, not three steps in the source" through "Work that was found and not done" |
| Ownership, ACLs, Synology Drive | "Permissions, and why Synology Drive goes quiet", "The permissions fix, and the half of it that was missing", "Permissions check" |
| Labels, colours, phone layout, Setup | "Labels, and where the words went" through "Setup is not decoration" |
| HEIC reading, the HEIC decoder | "HEIC: the same EXIF, boxed differently" |
| Anything Windows | "Running it on Windows as a program", "Traps the Windows version fell into" |

## Running fully on Windows (future goal)

What exists: `windows/PhotoManager.pyw` (server without a console, tray
icon from `windows/tray.py`, page in an Edge app window, one running copy
via a named mutex), `core/desktop.py` (settings in `%LOCALAPPDATA%\PhotoManager`,
tray menu as data, shortcuts, in-app Quit), `Install.bat` (bundled Pillow
and pi-heif, offline and hash-checked, plus shortcuts). Details in `windows/README.md`.
The original author wrote this on Linux and never ran it on Windows.

What a full port touches:

| Area | Today (Synology) | On Windows |
|---|---|---|
| Delete | share's `#recycle` (`core/cleanup.recycle_root`, used by `core/filesops.py`, `core/quickedit.py`, `app/tasks/delfolder.py`); refuses without one | Windows Recycle Bin (shell API or `send2trash`) |
| Ownership / ACLs | `core/perms.py`, `core/acl.py`, `app/tasks/permissions.py`, `nas/run.py`: uid/gid, `synoacltool`, xattrs | mostly no-ops already (`writes_as()` returns None). Permissions is off the page on a PC (`core/families.NAS_ONLY`); leave NTFS ACLs alone |
| Reindex | `core/reindex.py`, `app/tasks/reindex.py` call `synoindex` | not applicable: off the page on a PC (`core/families.NAS_ONLY`), CLI unchanged |
| Thumbnails | reuses DSM's `@eaDir/.../SYNOPHOTO_THUMB_*` (`core/thumbs.py`) | Pillow fallback; make Pillow required |
| Change-detection cache | `core/facts.py`, `core/jpegseg.py` key on size + mtime_ns + inode | `st_ino` can be 0 or unstable on SMB drives; needs testing |
| Scheduling | app's own thread, or DSM Task Scheduler running `python -m app.cli automation --which <flow> --apply` (an unknown flow or option exits 2 and runs nothing) | Windows Task Scheduler (`schtasks`) running the same command |
| Hidden/system folders | skips `@eaDir`, `#recycle`, Linux root folders (`SYSTEM_FOLDERS`, `app/server.py`) | add `$RECYCLE.BIN`, `System Volume Information`, `Windows`, `Program Files` |
| File locks | `os.replace` succeeds on an open file | raises `PermissionError` while another program has the file open; photo rewrites retry through `core/replace.py` (sidecars are still written in place) |
| Install | `python:3.12-slim` image, code mounted read-only | needs Python on PATH; later a bundled Python or installer |
| Network | container port 8842 -> 8080 | Defender firewall prompt on first run; `core/discovery.py` answers LAN discovery |
| Paths | one mount at the NAS path (`/volume1/homes/...`) | drive letters and UNC paths; `core/paths.py` does all path arithmetic, test it with `C:\` and `\\server\share` |

Run the full test suite on real Windows before changing any of these. The
first step of the port is getting it green there.

## DevStore (releases)

This repo is released through DevStore (`qawalah/devstore`). A push to `main`
builds both parts; a **new `version` in `devstore.json`** publishes them:

- **Windows** (`windows/PhotoManager.pyw`, PyInstaller, `windows-v<version>`):
  the DevStore window/Updater on the PC installs it. `name` is permanent
  (`photo-manager`). Settings already live in `%LOCALAPPDATA%\PhotoManager`,
  outside the install folder. `windows/devstore-prepare.ps1` copies the tray
  icon and the sources the wording tool reads into the frozen app; if you add
  a file the app reads from beside its code at run time, add it there or to
  `data` in `devstore.json`. Third-party packages go in `requirements.txt`.
- **NAS** (`Dockerfile`, `docker-v<version>`): published privately to
  `ghcr.io/qawalah/photo-manager`; Watchtower on the NAS installs it from
  `docker-compose.yml` (DevStore `docs/nas-setup.md`). The `HEALTHCHECK` must
  stay: the image is only published once it reports healthy. `nas/docker-compose.yml`
  is the older "copy the code folder" setup and is still tested.

Bump `version` in `devstore.json` together with `RELEASE` in `app/version.py`.
No bump means no release (the build still runs as a check).
