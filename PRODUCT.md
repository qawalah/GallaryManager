# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

One page served by the app's own small server. It is opened in a desktop
browser, in a phone browser on the home network, and in an Edge app window
when it runs as the Windows program (`windows/`). The same page and code serve
the Synology container (`nas/`) and the PC.

## Users

Two audiences at launch, confirmed by ALI (2026-10-21):

- **Enthusiast photographers.** They shoot RAW+JPEG, often in brackets and on
  trips. They keep the library as plain folders on a Synology or a PC, and edit
  in Lightroom. Their job is to turn card dumps into a tidy, dated, geotagged
  and rated library: RAWs kept apart, previews ready to rate on a tablet, and
  nothing lost on the way.
- **People with a big, messy family library.** Years of phone and camera
  photos sit in folders with wrong clocks, duplicates and no places. They want
  them sorted, findable and de-duplicated without learning a photo editor, and
  without being afraid the app will lose something.

Both groups are trusting the app with an archive that cannot be replaced, so
the main emotion to design for is trust.

## Product Purpose

Photo Manager organises a photo library where it lives, as real folders on
disk. It sorts, geotags, fixes camera clocks, rates, tags, culls, finds
brackets and duplicates, and separates RAWs, videos and previews into trees
that mirror the library. It can also run those steps on its own when a folder
changes. Success is a library that a person can open in any program, years
from now, and find in order, with every change the app made explained and
reversible.

## Positioning

The safe file-level organiser for people who keep their photos as folders on
a NAS or a PC. It sits beside Lightroom, Synology Photos or Immich rather than
replacing them. What neighbours cannot truthfully claim (see
`research/competitors.md` in the project files):

- It changes the real folders, not a private catalogue, and every change is
  shown before it happens and recorded so a whole run can be undone.
- RAW, preview and video trees follow the library however it is reshaped,
  matched by capture time and camera rather than by path.
- Brackets, Google Timeline geotagging, the tablet round trip (previews out,
  stars and colours back, Lightroom exports filed beside their originals) and
  scheduled flows all live in one small app.

It is not "another Google Photos". Face recognition, search by what is in a
photo, AI culling, phone backup, sharing, accounts and editing are things the
alternatives have and this app does not.

## Operating Context

- **Where it runs:** a Docker container on a Synology NAS (`nas/`), or a
  Windows program with a tray icon (`windows/`). Mac is not covered.
- **Offline first.** The server and page need no internet. Anything that does
  (map tiles on Places) must degrade to something useful without it.
- **How it is used:** at a desk for big jobs (sorting a year, a whole
  library); on a phone on the home network for quick looks, ratings and
  checking a run; from a schedule with nobody watching (flows, DSM Task
  Scheduler or Windows Task Scheduler running `python -m app.cli`).
- **Neighbouring tools:** Lightroom Classic (editing, exports to file back),
  Synology Photos and DSM (its thumbnails are reused, `synoindex` after
  changes), a tablet for rating previews, Google Takeout location history.
- **Every feature also runs from the command line.**

## Capabilities and Constraints

- **The four steps.** Every feature that writes follows Set it up, Check the
  list, Apply, What happened. It says what it will do (verb, count, from,
  into, how to put it back) before it does it. This is the core of the
  product.
- **Nothing is deleted by accident.** Culls and duplicates move to piles
  (`_Culled`, `_Duplicates`). Delete goes to the share's `#recycle` and
  refuses when there is none (the Windows Recycle Bin is part of the
  unfinished Windows port). Only Clean up removes files, and only from piles
  the app made. History can put a run back.
- **Plain technology on purpose.** Python standard library only (Pillow,
  pi-heif and ffmpeg optional, each degrading with a clear message). One HTML
  page, no framework, no build step, no web fonts or scripts from the
  internet.
- **Tools are declared as data.** A feature declares its options in
  `app/tasks/`, and the page draws its form from them. About 50 tools sit
  under five headings: Organize, Metadata, Review, Develop, Maintain, with
  Settings apart (`core/families.py`). No tool or option may disappear when
  the page changes.
- **Terminology is fixed** by the glossary in `core/wording.py` and tested by
  `tests/test_wording.py`. The page says photo, not photograph or image;
  video, not clip; folder, not directory; tool, not feature or task; tag, not
  keyword; and "Check the list", not "plan".
- **One password, one user.** No accounts or sharing.
- **Undecided:** how it will be sold (one-time, subscription or free) is open.
  Do not write prices, licences, trials or "free" into any surface until it is
  decided.

## Brand Commitments

- **Name:** Photo Manager. The app icon is generated by `tools/make_icon.py`.
- **Voice:** plain, calm, specific and honest. It says what happened and why,
  in full sentences ("Nothing has been written yet.", "Counted just now, from
  the index, nothing was opened."). It never says "Are you sure?" without
  naming what is about to happen. Labels are names, and explanations go in
  the help bubble. No sentence over 25 words, no dash used as a full stop, no
  capitals for emphasis. The rules are data in `core/wording.py`.

## Evidence on Hand

- **Sample library:** Setup > Sample library (`core/demo.py`) builds a real
  library with EXIF, RAWs, brackets, duplicates, a wrong clock and videos. Use
  it for every screenshot and demo. Never use a real library.
- **Competitor research:** `research/competitors.md` in the project files
  (October 2026).
- **Design reasoning:** `docs/DESIGN.md` (why things are as they are),
  `docs/ROADMAP.md` (what is planned), `CHANGELOG.md`.
- **Audits and critiques:** `audit/` and `design-critique/` in the project
  files.
- **Not on hand:** customers, testimonials, reviews, usage numbers, benchmarks
  or press. Do not invent any of them.

## Product Principles

1. **Show before doing.** Nothing writes until the person has seen, in plain
   words, what will change, how many, where, and how to put it back.
2. **The folders are the truth.** The library stays readable by any other
   program. The app keeps no data that only it can read.
3. **Trust over speed, then speed.** Safety is never traded for convenience.
   Once the person trusts a run, repeat work should be fast (flows, bulk
   actions, shortcuts).
4. **The photos come first.** The interface is there to get a library in
   order, and should keep the person's own photos in view.
5. **Works with nobody watching and nothing online.** It runs on a schedule
   and offline, and says clearly what it did.

## Accessibility & Inclusion

- **Standard:** WCAG 2.2 AA at launch (confirmed by ALI, 2026-10-21). That
  covers contrast, keyboard use with visible focus, screen-reader
  announcements for results and undo, and 44 by 44 pixel touch targets on
  phones.
- **Language:** English only at launch. The page's strings are already kept
  as data (`app/web/page/strings.json`, Setup > Wording), which leaves room
  for other languages later.
- **Readers:** a family-library owner is not a photographer. Photography
  terms (RAW, bracket, EXIF) need a plain explanation in the help bubble.
