# Photo Manager - NAS edition: design notes

This was the project README, written by the app's original author. It is kept
as the record of why things are the way they are. For how the code is laid out
and how to work on it, start with `CLAUDE.md`; for installing on the NAS,
`nas/README.md`; on Windows, `windows/README.md`.

**Version 1.1.0.**

The Windows app rewritten to run on the Synology, as a container with a web page,
and on the PC as plain Python. Same code both places.

Three trees, and the first one is the truth:

    N:\Photos             the library.  Everything else follows it.
    N:\Photos Raw         the RAWs, in a tree shaped like the library.
    N:\Photos Previews    small JPEGs to rate on a tablet.  Disposable.

## The shape of it

    core/       reads and writes photos. Knows nothing about the web or the NAS.
    app/        the task registry, one module per feature, the CLI and the page.
    app/web/    what the browser runs: the HTML, CSS, JavaScript and icons.
    nas/        how it runs on the Synology. Start with nas/README.md.
    windows/    how it runs on a PC as a program. See windows/README.md.
    scripts/    check, test, run and web - the double-click launchers.
    tests/      the specification.
    tools/      builds the test photos (needs Pillow; results are committed).

### 3.0: a photo library with the features behind it

Everything in here used to be a QUESTION you pressed a button to ask. That is
right for "move four hundred files" and wrong for the first ten seconds: the app
opened on a form with `Have a look` under it, and the photographs - the only
reason any of it exists - were not on the screen at all.

So there are two halves now, and they meet in one place.

    core/catalogue.py   the library, read once in the background and kept
    core/browse.py      the questions a photo library is opened with
    app/libraryui.py    the screens: Home, Photos, Timeline, Places, Albums, Tools
    app/page.py         the forty-six features, unchanged (its markup, style and
                        script are now files in app/web/page/)

**The index is what makes a front door possible.** It is built on a thread at
startup, stored in `catalogue.json`, and brought up to date incrementally: a
later pass walks the tree by name, drops what has gone, reads what is new or has
changed, and leaves everything else alone. A library that has not moved costs one
`os.walk`. Anything that writes calls `catalogue.touch()`, so the next refresh
picks the change up - nothing in here ever decides it knows better than the disk.

**When the library moves, the index moves with it, at once.** The library is
a setting, and everything that keeps a copy of it has to notice when it
changes. On the server the index loop glances at the settings file every
couple of seconds (a stat) and a Setup save wakes it outright: the old
library's photographs leave the index the moment the trees change
(`Catalogue.let_go`), and the index refuses to vouch for the new trees until a
pass has read them (`unread`). In the page, `/api/health` carries a stamp of
the settings file, and when it moves the page re-reads the task list and lets
every copy follow (`library/js/19-settings-followed.js`): a form box that still
holds what Setup used to say takes the new value, one somebody typed into
stays theirs. A library that is set but not mounted keeps its index; only no
library at all empties it.

The same goes for the folders each tab remembers (`core/recent.py`). A run
on Setup's own value is following Setup, not choosing a folder, so it is not
remembered - remembering it is how Search came to open on the old library,
reload or not, because a remembered folder wins over Setup. And when a tree
moves, `settings.save` forgets what was remembered inside the old one. That
only works for a move it sees, so each pick is also kept with what Setup said
when it was made (`key@setup`), and `recent.meant` measures it against what
Setup says now: a folder of a tree that has since moved falls back to Setup,
one picked outside the tree (an Inbox) stays.

What it stores is one `find.Hit` per photograph: the same object the Search tab
builds and the charts count. That is not tidiness, it is the whole reason this
could be bolted underneath them. `stats.tally_of` counts those instead of
walking, so **the dashboard that took thirty seconds now opens with the numbers
already on it**, and a test asserts the two paths give the same answer bucket for
bucket.

**Select, then act.** Stars and colour labels are written straight through, one
file at a time, by the same endpoint the viewer has always used. Everything else
hands the selection to the feature that does it, with the folders those
photographs are in already filled in - because the tasks here work on folders,
and that is what makes "move four hundred files" something you can check before
it runs. A second half of the app that wrote without a plan would have been a
worse app wearing a better coat.

**One viewer, not two.** The detail view is the viewer this app already had -
stars, colours, tags, histogram, shot details, swipe, delete - with a panel
beside it carrying what the index knows and what is on the disk next to it.

### Why a registry

Every feature declares its own options as data and provides two functions:

```python
def plan(opts)  -> Plan     # reads, decides, writes NOTHING
def apply(plan) -> Result   # does what the plan said
```

The web page draws its form from the declared options. The command line generates
its `--help` from them. So a new feature is one module plus one test file - no
interface work, no API route, no scheduler change.

That plan/apply split is exactly how the Windows app already works (Preview, then
Apply), which is why the logic and its tests port across rather than being redesigned.

## The features

In the order you would work through a messy library. Indented ones are tabs
under the feature above them, because they are not separate jobs: pinning a
place by hand is part of geotagging, and taking finished exports back off the
tablet is the other half of sending them to it.

    Library           library     read a tree as it actually is - counts, dates,
                                  what is paired, what has a preview
      Clean-up status tidy        what is sitting in piles you already decided
                                  against, and what is empty. Never touches it
    Geotag            geotag      a location onto photos that have none
      Fix the clock   retime      correct a camera clock, whole folders at a time
      Import timeline import-timeline  Google's location history, read once
      Pin by hand     pin         one place, for a folder the timeline cannot cover
    Sort into folders bydate      year/month/week/day, and country and city shapes
      Place names     import-places    the offline table of towns, and your names
    Separate RAWs     unpair      RAWs out of the library, into a tree that mirrors it
      Re-mirror RAWs  remirror    reshape the RAW tree to match a reorganised library
    Separate video    videos      clips out of the library, into a tree that mirrors
                                  it - filed with the shoot they were taken among
      Re-mirror video remirror_video  move each clip to where the photographs of
                                  its moment now live
    Make previews     previews    small JPEGs in a tree shaped like the library
      Re-mirror       remirror_previews  move them to follow a reorganised library
      previews                    rather than making the whole tree again
    Rating & tags     ratings     stars and colours onto the originals and
                                  their RAWs; apply a colour to a folder;
                                  tag a folder or everything matching a rule
                                  on the photographs, the RAWs and the previews
    Send to develop   develop     the shots worth developing, copied out for a tablet
      File developed  filed       Lightroom's exports - one flat folder, no tree -
                                  matched to their originals and filed there
    Clean up          cleanup     empty the piles - _Culled, _Duplicates - once you
                                  no longer want them. The only thing that deletes
      Thin brackets   thin        keep one frame of a set, the spares to _Culled
      Cull by rating  cull        low-rated aside - JPEG, RAW, sidecars, preview
      Find duplicates duplicates  the same photo twice, and which copy to keep
    Automation        automation  the developing loop running itself: each step when
                                  the tree it watches changes
      Runs            autoruns    what it has done on its own, and what each pass
                                  took off the NAS
    Setup             setup       your trees, and what counts as a bracket
      Find brackets   brackets    how those settings group a folder, and mark the
                                  sets with a keyword
      Reindex         reindex     tell DSM about the folders that changed, so its
                                  own databases stop showing yesterday's library
      Colour meanings labels      what each of the five colours means, the keywords
                                  it writes, and where it sends
      Sample library  demo        builds a library with real EXIF, RAWs, duplicates,
                                  a bracket and a wrong clock - somewhere to learn
                                  every feature without risking photographs

    History           history     what was actually done, and when. In the header
                                  rather than the sidebar: somewhere you go to look
                                  back, not a step in any loop

### Where they are now

3.0 draws those forty-six under five headings on the Tools screen - **Organize,
Metadata, Review, Develop, Maintain** - with Settings kept separate. The table is
`core/families.py`, one place, with a test that fails if a feature is in none of
them and another that fails if it is in two. Tabs are listed there too, because
"Cull by rating" is what somebody looks for and it used to be one click inside
something else.

**One page per tool, its group beside it (3.15.0).** A tool used to open with
a tab row naming its relatives, and which ones were relatives was `parent` in
the source. Once tools could be dragged between groups on All tools, that was
two arrangements of the same tools: move Find blurry to Metadata and Cull still
offered it as a tab, while Metadata's tools did not. So the tab row is gone.
Each tool is a page of its own, and down the right of it is its group, read
from the same `families` list the rail and All tools draw
(`library/js/22-tool-side.js`), with the open tool lit. Whatever was reachable
from a tab is still one press away: a tool in no group (Put a run back, Clear
the history) is listed under the tool it belongs to. Below 1060 pixels the list
goes under the form, after any results, so it never pushes them down.

### The same four steps on every feature

Forty-six features in one flat list is a correct list and a bad menu. "Separate
RAWs" is a perfectly clear sentence that does not say whether it is a thing you
do on day one. 2.2 put five headings over them in the sidebar; 3.0 moved those
headings onto the Tools screen and the sidebar became the library's - see
**Where they are now** above.

Each feature that WRITES then says the same four things in the same places:

    1 Set it up    2 Check the list    3 Apply    4 What happened

a strip across the top with the step you are on lit, one sentence saying what
the feature is for (which you can put away per feature, and it stays away), and
every advanced setting behind ONE disclosure instead of five collapsed boxes
named More.

### Saying what is about to happen, in four facts

The page asked you to approve four hundred rows and never printed the sentence
that would let you check them. Every fact was already there - the task knows its
verb, the plan knows its rows, the boxes hold the folders - they were simply
never put side by side, so the only way to know what the button did was to read
the table and infer it. And the button said `Go ahead with these 184` on every
tab in the app, which is exactly where the missing word belongs.

A task now declares `verb`, `unit`, and - where it matters - `risk` and `undo`.
From those, `registry.impact_of` reads **what, how many, out of where, into
where** off the plan for every task at once, generically:

    Operation           Move 184 files
    Out of              Photos/Inbox
    Destination folder  Photos
    RAW tree            Photos Raw
    Afterwards          Files are moved, not copied. Nothing is overwritten.

The button says `Move 184 files`. The three tabs that can lose something ask a
second time, in a box naming the operation, the number, the place and what the
task itself says about putting it back - never "Are you sure?", which asks you to
confirm a question you have not been told the answer to.

The count comes from the plan on the server, not from the rows on the page: the
table is trimmed at two thousand, and a confirmation reading "Move 2,000 files"
about a plan holding 2,400 would be the worst kind of wrong - too small, and
reassuring.

Afterwards the run reports four numbers rather than one - **done, left alone,
unchanged, failed** - because "184 done" out of 400 rows has not told you about
the other 216. And a plan that finds nothing says *Nothing to do* with the folder
it read, instead of changing almost nothing on the screen and leaving you to
decide whether it is broken.

### Somewhere to practise

Every other tab in here moves somebody's real photographs, which makes this a bad
app to learn by trying. **Setup, Sample library** builds one of its own
(`core/demo.py`): forty-odd files with real EXIF written by Pillow - capture
times across two years, two cameras and three lenses, ISO, aperture, shutter,
focal length, stars, positions - plus the faults a real library has, because a
feature with nothing to find teaches nothing:

    an unsorted heap, three shoots and two years deep
    negatives beside their JPEGs, and in a mirrored RAW tree - some, not all
    a bracketed set of three: one second, one stop apart
    two pairs of duplicates, identical bytes, different names
    two blurry frames, one photograph with no EXIF at all
    a phone two hours fast, carrying a position that proves it
    two clips with real MP4 headers, so Separate video has something to move

The negatives are JPEG bytes under a `.RW2` or `.ARW` name. That is not a
shortcut: this app cannot read EXIF out of a real RW2 either, so a sample
negative behaves exactly like a real one - matched to its JPEG by name and
position, never by what is inside it - while still drawing a thumbnail.

"Point Setup at it" borrows the tree boxes and writes down where yours were;
removing the sample puts them back. It never overwrites a file, so building twice
costs nothing, and it will only DELETE a folder carrying the marker it wrote
itself - pointed at your library, Remove does nothing and says why.

### Reading a photograph once, and not at all the next time

Sending the library out to develop took half an hour, and almost none of it was
work. Each photograph was opened four separate times - once for its rating, once
for its clock and camera, once for its keywords, once for its colour - and each
of those looks in the sidecar first. Grouping brackets read every picture again
on top of that.

Two things fixed it, and they are independent.

**Every fact out of one read.** They all come from the same two places - the
front of the file and the sidecar beside it - so they are fetched together
(`core/facts.py`). The last piece lives in `jpegseg.read_header`, which hands
back the bytes it just read when the same unchanged file is asked for again:
keywords alone are looked for in three places inside one JPEG.

**And none at all the second time.** The answer is kept against a signature of
the file itself, so a pass over an unchanged library costs one stat per file.
Measured on 200 photographs: 800 files opened, then 0.

The signature is size, modification time in nanoseconds, and **the inode** -
which is the one that matters and the least obvious. Every metadata write here
is "write a temp file, then `os.replace`", and it then restores the original
date on purpose so that rating a photograph does not read as an edit to every
backup tool in the house. Same size, same nanosecond: a cache keyed on those two
alone would serve last week's rating for ever, silently. `os.replace` cannot
preserve the inode. A sidecar rewritten in place by Lightroom is the same
problem from the other side, so the sidecar's stat is in there too.

**One set of notes per process, written once.** Every task used to read
`facts.json` when it began and write all of it back when it finished. Two runs
in two threads then saved their own copies over each other, and a flow of five
tasks rewrote a multi-megabyte file five times in a minute. Now the notes are
read once when the process first asks, shared by every reader behind a lock,
and a task's `save()` only asks for a write: the saves of one pass are gathered
into one, made a couple of seconds later or when the run ends. Each task still
gets its own reader for its own counts, and the signature is still checked on
every ask, because a twenty-minute pass is long enough for Lightroom to rewrite
a sidecar half way through it.

This is not a hole in "measured, never remembered". That rule is about not
keeping a record of what was DONE, because a log of past actions quietly stops
describing a library the moment a shoot is renamed in File Station. This is
keyed on the thing it describes, so it cannot disagree with the disk without the
disk saying so - the same bargain the Library view has made since it was built.

### HEIC: the same EXIF, boxed differently

An iPhone saves HEIC, and for a long time this app counted those files and then
knew nothing about them. The fix is smaller than it sounds because a HEIC's
EXIF is the very TIFF block a JPEG carries: only the way to find it differs. A
HEIF file is ISO media boxes (the MP4 family); the `meta` box near the front
names an item of type `Exif` and says where its bytes are. `core/heif.py` follows
those two pointers and hands the TIFF block to the reader every JPEG already
goes through, so dates, cameras and GPS needed no change of their own, and none
of it needs a library.

Drawing the picture is different: HEVC needs libheif. That comes from pi-heif,
the decode-only build of pillow-heif (LGPL libraries only, a third of the size,
and none of the GPL encoder this app would never use). It is optional on
purpose. A NAS on an ARM chip nobody built it for still reads every HEIC's date
and place, and only loses the thumbnail it never had.

Nothing here writes inside a HEIC. Locations and corrected times go to a
sidecar, as for a RAW, and a position the phone recorded is left in place and
named, not replaced by a sidecar that would be read second and never win.

When the reader learned HEIC, the read cache and the index already held a
"no date" note for every HEIC they had seen, keyed on files that had not
changed. Those notes alone are signed differently now (`facts._READER`, and a
mark in the survey's folder fingerprint), so they are read again once and the
rest of a large library is not.

### A flow is data, not three steps in the source

The developing loop used to be three steps written into `automation.py` - sync
the ratings, send out to develop, file what came back. Right shape, wrong place:
every feature here already declares its options as data and provides
plan-then-apply, so the loop never needed to know which three they were. It knew
because somebody typed them.

A flow is now a named, ordered list you assemble on the **Flows** tab: add a
step, pick any registered feature from a dropdown, set its own settings, put it
where it belongs in the chain. A feature added next year is available to every
flow without a line of code.

    Developing loop        every 15 min, run by the app
      1. Rating & tags     watches: previews    run
      2. Send to develop   watches: library     run
      3. File developed    watches: exports     just tell me

    Sunday tidy-up         Sundays 02:00, run by DSM's Task Scheduler
      1. Find duplicates   watches: library     just tell me
      2. Clean up          watches: library     just tell me

Four things make that safe to leave running.

**Upgrading changes nothing.** The old `auto_*` settings become the first flow
exactly as they were - not switched on, not switched off - and its steps keep
the marks they were already filed under, so the first pass after an upgrade does
not find everything "changed" and run all of it once for no reason.

**The order is the chain.** Steps run in order inside one pass, and a step that
writes something makes the next one run straight away rather than an interval
later. Put a step before the one that feeds it and it does its work late, every
time, silently - so the editor draws them numbered and moves them one at a time.
Each step keeps an identity of its own, so moving one does not hand it the
history of the step that was there before.

**A step watches a tree, worked out rather than asked.** A feature's first
folder option is the tree it works from - syncing ratings opens with "Where you
rated", filing opens with the export folder - which is why the carried-over flow
watches exactly what the hard-coded one did. Stated, shown, and overridable.

**Nothing a step will use is invisible.** A step stores only its OVERRIDES and
lets the feature's own `coerce` fill the rest from Setup - the same code path
the tab uses, so the two cannot disagree. The editor shows the effective value
of every option and which of the three places it came from. That is the fault
this replaces: a threshold typed on a tab was not the threshold that ran in the
background, and neither end said so.

### Folders a flow leaves alone

Setup has always skipped folder NAMES - `@eaDir`, `#recycle`, `Developed` -
which mean "this is not a photograph of yours", anywhere. That is the wrong tool
for "my phone's photos are in `Photos/Mobile` and the developing loop should not
touch them": that is one PLACE, a name would take out every folder called Mobile
anywhere, and the Sunday tidy-up may well want them.

So there is a second list, of paths: one in Setup that every flow obeys, and one
per flow **added** to it - never replacing it, or building a flow would quietly
undo a decision made once. Anything inside an excluded folder is excluded too,
and the comparison is segment by segment, so excluding `Photos` never takes
`Photos Raw` with it.

**Whatever was actually left out is said.** A tree quietly smaller than you
think is how "0 of 400 geotagged" becomes a number nobody can act on, so every
walk records which excluded folders it met and how many files were inside them,
and that goes on the plan as its first note. The change check obeys the same
list - a fingerprint that counted an excluded folder would wake the flow up for
it every pass and then find nothing to do.

It is scoped to the run, not global: opening a tab by hand still sees your whole
library, and two flows running at once do not have to agree.

### The flow as a picture

A list of steps with a summary above it reads as a SET. The one property of a
flow that is easy to get wrong is its ORDER - steps run in order inside one pass
and a step that writes makes the next one run straight away - and nothing on a
list says that. Arrows do.

So both the Automation tab and the Flows tab draw the flow as a chain of blocks,
from the same data on the server, because two pictures of one flow are two
pictures that will come to disagree. Each block says what the step is, which
tree it watches, whether that tree is actually set up, whether it runs or only
reports, and how much is waiting on it.

Beside it: a light that says **ON / OFF / RUNNING / DSM FIRES IT** in words as
well as colour, and a **Run** button that opens Automation with that flow chosen
and presses its button - the same one, not a second way of running a flow.

### Saying it in words, not only in colour

The status pill at the top had three states told apart by hue alone, which is no
answer to "is this thing working" on a dim monitor, in the dark theme, or for
anyone who reads red and green alike. Each state now differs in shape and in
word: off is a hollow ring on a plain pill, on is a filled dot on a tinted one,
running is a filled pulsing dot on a solid one, and the word - OFF, ON, RUNNING
- is the loudest thing in it.

The unread mark had the same fault in a different form: it counted background
runs and said nothing about them, which is most of the way to useless. It now
records what each run was and what it did, so the line under the header reads
"2 runs did something - 208 thing(s) (Rating & tags 14, Send to develop 194)"
rather than a number you have to go and investigate.

### A flow that would eat itself is refused

Send a photograph out to develop, have filing move it into the library as a
finished export, mark it developed, take the original off the tablet - and round
again every pass, every step doing exactly what it was told.

That used to be one refusal written by hand about one arrangement. Assembling
flows from a dropdown makes it one case of many, so each feature declares what
it **reads**, **copies into** and **moves into**, as Setup tree names, and the
check looks for the ring on the resolved paths. It closes only when what is
taken out goes back somewhere the first step reads - taking photographs
somewhere the sender never looks is a one-way trip and is fine.

A feature that declares nothing makes no claim, and the check says which steps
it could not examine rather than reporting a flow as safe.

### Who fires it, and letting DSM do it

Separate question from what it does. A flow is fired by the app's own thread or
by a task in DSM's Task Scheduler, and both run the same pass through the same
machinery.

    docker exec photo-manager python -m app.cli automation --which developing --apply

No second entry point: the command line already runs any registered task from
its declared options, so what the scheduler fires is what the tab shows. A flow
id it does not know, or an option the task does not declare, is refused with
status 2 before anything is planned: it used to fall back to the first flow and
to Setup's whole library, which with `--apply` at 3am is a run nobody asked for. The
Flows tab prints the exact line with this container's own name in it.

DSM's scheduler is time-based and the loop is change-based, which is the real
trade-off. It is smaller than it looks: a scheduled task every 30 minutes costs
a few thousand stats when nothing has moved, because the step still checks
first. What you get for it is a schedule that survives anything happening to
this container, and a run that appears in DSM's own history.

A flow left to DSM is never fired by the app as well, whatever its switch says,
and the bar at the top does not claim to be running it.

### Work that was found and not done

Filing exports reports by default, because it is the one step that MOVES
finished photographs into the library. The consequence was a sentence with no
button under it: a pass at four in the morning would find 194 photographs ready,
write "194 waiting" into a log nobody reads, and say it again every fifteen
minutes for a week.

So a pass writes down what it left, the Automation tab shows it as a queue at
the top with what and since when, and **Apply** runs that one step - for that
press only. Not by changing the setting: saying yes to 194 exports once is not
saying yes to every export from now on.

Nothing marks itself up to date while it is waiting, which is why the work is
still being offered rather than quietly forgotten after the first pass.

### What it costs the NAS

An app that reads a hundred thousand photographs every quarter of an hour on its
own is one you are entitled to know the cost of. Every run is measured around
itself - CPU seconds, bytes actually read off the disk, wall clock - and the
Automation Runs tab shows it per pass.

**The number that matters is files opened.** Nothing here is computation, it is
opening files over a disk - and on a spinning disk you wait for the seek rather
than for the bytes: ten thousand files of 60 KB is six hundred megabytes and
also ten thousand seeks. The CPU-to-clock ratio says the same thing from the
other side - "4 min, 12s of that working" means three and three quarter minutes
spent waiting.

**Counted by the app, not by the kernel.** `/proc/self/io` is the better answer
where it can be read, and in a Synology container it usually cannot - so every
run on Abu's NAS reported `Read: not measured`, which is precisely the figure he
wanted. Every place this app opens a photograph, a sidecar or a header now adds
what it took (`core/meter.py`), so the number is there whatever the container is
allowed to see. The kernel's figure is still shown beside it where available:
it counts bytes off the DEVICE, and the gap between the two is what came out of
the page cache.

What it will not do is claim the machine's load as its own. A NAS is running
DSM's indexer, Drive, Photos and whatever else is in a container; the load
average is all of them together, so it is shown as context and labelled as the
whole machine.

Automation also runs as ordinary jobs now, so the bar at the top shows a
background pass exactly as it shows one you pressed - marked `auto`. Before that
the app could read your whole library every fifteen minutes with the page saying
nothing at all.

### Finished exports travel with their originals

A developed export is the one thing in a library that cannot be found again by
looking. It shares its original's name, capture time and camera - which is
exactly why it lives in a subfolder every scan skips - and the price of that is
that nothing can re-match it later.

So when Sort into folders moves a photograph, the finished versions beside it
come too, into a subfolder of the same name at the new place. A shoot that
splits across three date folders takes its exports apart with it, each one
beside the photograph it came from. What ties them is where they are and what
they are called, which is not a guess: it is how filing put them there.

No tagging, deliberately. A tag is something remembered, and a remembered thing
can disagree with the disk - the position and the name are measured every time.

An export whose original has been culled, renamed by hand or deleted cannot
travel with anything. It is named in the "left alone" list with the reason,
because no scan in this app can see it and unsaid it would simply be forgotten.

### Why it does not read your whole library

Placing one export, or syncing one star, is a question about a handful of files.
The obvious way to answer it is to read every photograph in the library first
and build an index - and that is minutes of opening files over a share to answer
a question about five of them.

It does not, and the reason it can skip them is exact rather than clever: every
way one file is matched to another here keys on the BASE NAME first - full
identity, then name and camera, then name, then name alone. A photograph whose
name is not among the ones being asked about can never be the answer to any of
those, so reading it is work whose result could not be used.

So the walk happens (a few thousand stats, cheap), the names are collected, and
only the files that could possibly match are opened. Filing three exports into a
library of three thousand photographs opens three files rather than three
thousand. There is a test that runs a tree both ways and compares the answers,
because "faster" is only worth having if it is also "the same".

The one place this needs care is brackets: a star given to one preview reaches
the whole set it stands for, and those frames have different names. Their names
are added from the sets already worked out, without reading anything.

### Permissions, and why Synology Drive goes quiet

Every metadata write here builds the whole new file and then replaces the old
one, so a crash half way cannot leave half a photograph. The cost is invisible
and arrives months later: a replaced file is a NEW file, with the owner, the
mode and - on a Synology, the part that actually decides - the ACL of whatever
process wrote it.

Nothing fails when that goes wrong. The photographs are all there and all
correct. What stops is Synology Drive, which reads the library as YOU rather
than as this app: a tree it can no longer read is a tree it stops syncing, and
it does not say so either.

So: a file this app rewrites keeps its owner, group, mode and access list. A
file it creates takes after the thing it belongs to - a sidecar after its
photograph, a preview after the original it was made from, an export after the
photograph it is filed beside. A folder it makes takes after the folder above
it, one level at a time, which is what keeps DSM's setgid bit.

It never invents an access list. Copying a folder's onto a file would be
guessing at the difference between an inherited entry and an explicit one, and
guessing wrong silently is worse than leaving it to DSM.

If a folder does go quiet: File Station, its Properties, Permission, Advanced
options, "Make inherited permissions explicit", with "Apply to this folder,
sub-folders and files" ticked.

### A settings tab saves when you press Save

Setup did keep what you typed - but only as a side effect of pressing "Show me
what would happen", a button whose words promise that nothing will be done. So a
path typed and then walked away from was lost without a word, and the fair
reading of the tab was that the app remembered nothing at all.

A tab that only writes settings now has a **Save** button and no preview button,
because there is nothing to preview about writing a path down. Saving is still
plan-then-apply underneath, so a library that is not there, or an export folder
sitting inside the develop tree, is refused and says why instead of being saved
wrong. Automation keeps both: **Save** writes the settings, and **Run one pass
now** saves them and then runs the pass.

### The switch, and what it locks

The Automation settings are read by a thread that wakes on its own, so a form
you can edit while it is running is a form that will be half-changed when the
next pass fires - a loop running against a mixture of what you meant and what
was there before.

So the switch is the first thing on the tab and, while it is on, every setting
below it is greyed out with a line saying which switch is holding them. The
switch itself never locks: otherwise turning it off would need the form it
locked. The bar at the top of every page says whether it is on, whichever tab
you are looking at.

### The permissions fix, and the half of it that was missing

The first repair carried the owner, the group and the mode onto every folder
this app creates. It did not carry the **extended attributes** - and on DSM the
extended attribute is where the access list lives, which is what File Station,
Drive and Photos actually go by.

So a new shoot folder came out with the right owner and **no access list at
all**: exactly the state that "Advanced options > Make inherited permissions
explicit" is the cure for. Every year folder, every shoot folder, every
`Developed` subfolder. Silent at both ends again - the app is happy, the files
are all there, and Synology Drive stops seeing a tree it cannot read without
saying anything either.

A new FOLDER now takes its parent's attributes verbatim, which is what File
Station's repair does. A new FILE still does not take a folder's - a directory's
list carries inheritance flags that mean nothing on a file, so a file takes
after a real file of the same kind in the same place. That distinction is the
whole reason copying is safe rather than a guess, and `travels()` is a decision
of its own with a test on each side, because the copying loop swallows every
refusal and a wrong answer there would look exactly like the filesystem
declining.

Where DSM's own `synoacltool` is reachable from inside the container it is used
instead, since it knows which entries are inheritable and this app does not.
Which options that build has is **asked** - the tool prints its own usage -
rather than remembered, because `-copy` and `-enforce-inherit` both exist in the
wild, neither is documented by Synology, and running a command a build does not
have would fail once a folder, quietly, into nobody's log.

### Permissions check

The claim above cannot be tested from a development machine: the access list is
DSM's, the filesystem is DSM's, and the only machine where the answer means
anything is the one with the photographs on it. So there is a tab under Setup
that **measures it** - it makes a real folder in each of your trees exactly the
way every task makes one, compares it with the folder it was made inside
attribute by attribute, says what differs, and removes it.

It does not need to know which attribute holds the access list, because it
compares all of them. There is a test that the comparison mentions no Synology
name at all.

It also writes a repair script, on request: folders made before this was fixed
still have no list of their own, and nothing the app does later will give them
one. The script asks DSM's tool to fix inheritance across each tree - plain
text, readable before you run it, and it moves, deletes and rewrites nothing.

### Labels, and where the words went

The interface had been written the way the docstrings are, and a docstring has
all the room in the world. Two hundred and thirty-six options each carrying a
clause - "Where the locations come from", "Write .xmp sidecars only - never open
a photo for writing" - made every form read as prose with boxes in it, and the
thing you were actually looking for (which setting is this) was the hardest part
to find.

Every label is a NAME now, two or three words: *Location source*, *Sidecars
only*, *Send RAW at*, *Take finished back*. Nothing was deleted - what a long
label was carrying moved into its (i), and there is a test that the options
which lost words still say the same things.

**And help is a bubble, not a panel.** It used to expand in place. The
arithmetic of that is what made it wrong: most options here have two sentences
explaining a trap, so a form with a dozen of them opened is four screens of
prose with the controls scattered through it - you cannot compare two settings
that are a page apart, so you stop opening any of them. Now it hovers on a
mouse, taps on a phone, and is gone when you look away.

Two details that took a second attempt each. A tap fires pointerover, pointerout
AND click in one gesture, so hovering is treated as a mouse thing and only a
mouse thing - otherwise the tap opened the bubble and the click that followed
shut it, and the button appeared dead. And the bubble remembers HOW it was
opened, because the focus a tap also causes would do the same thing from the
other side.

### Wording lives in the declarations, and can be overridden

Every word a tool shows is in its `Task(...)` and `Option(...)` declarations,
and that stays the source. Setup > Wording (behind a developer switch in
Setup, or `PM_DEVELOPER=1`) lets somebody rewrite any of it in place and read
the result on the real forms. The edits are *overrides*, kept in
`PM_DATA/wording.json`, not edits to the code: a new release cannot lose them,
the tests keep testing what ships, and the file holds only what changed.

They reach the page through one choke point. `Task.describe()` ends by passing
its answer through `core/wording.apply()`, and the page, `/api/tasks` and the
command line's `--help` all read `describe()`, so none of them knows overrides
exist and no option can be missed.

The way back is mechanical on purpose. Download gives every edit with the text
it replaces and the file and line that text is written on
(`app/wordsource.py`, which reads the source with `ast`, so "RAW tree" means
this option's label and not the other eleven). `tools/merge_wording.py` writes
the edits into those literals, refuses an entry whose shipped text has changed
since the export rather than guessing, and loads the registry again to prove
every merged line now ships. Only the two rules the tests also enforce (a
label or heading of at most four words, a name that is not empty) refuse a
save; the rest of the style guide are warnings on the card, from one list in
`core/wording.py` that the tests share.

The page's own words and the Guide are the same kind of text with no
declaration to live in. The toasts, dialogs and counts the script used to
write inline are one table now, `app/web/page/strings.json`, which the script
reads as `S` and fills with `say(name, {n})`; `{n:file|files}` picks the
word that agrees with the number, so "3 file(s)" is gone. The Guide was
already Python data in `app/page.py`. Both are two more entries in the
Wording tab's list, "Page text" and "Guide", with keys `page.<name>` and
`guide.<slug>.title|body.<n>`. The script carries an empty `WORDING` object
and `app/pagetext.served()` puts the edits into it as the page is sent, so
with nothing edited the page is sent byte for byte as it was built, and the
merge tool writes a page key into the JSON table and a Guide key into its
literal, like any other.

### One row, one size

Every control in the header had grown its own padding, font size and corner
radius, added one at a time, so History sat a pixel or two off its neighbours
and the row read as things that had accumulated. Which is what had happened. One
rule now, one height, one radius; the only thing a button chooses is its icon.
The header no longer wraps either - the allowed-folders line is the one elastic
thing in it and truncates, rather than pushing Reload page onto a second row and
making the header a different height on different machines.

The automation chip is calm. Two earlier attempts painted the whole pill - first
accent blue by accident, then green or blue on purpose - and a filled block of
colour in a header is loud, fights the theme, and makes the WORD harder to read
rather than easier. A status is not a button and should not look like one, so
the chip is neutral and the colour is carried by the dot and the word alone.

**No private paths anywhere.** Not in help, not in an example, not in a default.
It is somebody's user name on a screen, and there is a test that the string
never appears in the page, in any task's declarations, or in any file the app
can print from.

### On a phone

Not a shrunken desktop. What you open this app for on a phone is not what you
open it for at a desk: at a desk you are working through a library, and on a
phone you are standing in a kitchen wondering whether the thing is still
running, whether last night's pass did anything, and whether the 194
photographs it keeps mentioning can go now.

2.x answered those three on a phone-only home screen of its own, with a switch
in the header between it and "the full app". 3.0 put the library in front of
everything at every width, and its Home is the same screen on a phone and a
desk; the three questions are answered by the Flows pill in the header, the
runs-since-you-looked line and History. The 2.x home screen, its header switch
and its side menu stayed in the page, hidden, as a fallback in case the library
shell never started, and went in 3.9.1: a fallback nobody can see is code
nobody tests. What only the side menu drew moved to the rail - the features you
opened lately, *Tell me when a run finishes*, and *Install as an app*. Two of
those went in turn in 3.12.0, by request: the Lately list, and Install as an
app together with the web manifest behind it. The notice switch stays.

**Three things change shape rather than size**, because scaling them down leaves
each one technically present and practically unusable:

- **the rail** becomes a drawer, and a feature's own tabs go inside it, under
  the feature. Thirteen features in a horizontal scroller is a list you have to
  swipe through to read and cannot see your place in - and a second strip inside
  each feature is a second navigation gesture in a different direction, which is
  a phone you have to learn. One pull reaches everything. It closes the moment
  you pick something, and its foot carries what the header has no room for;
- **wide tables** become one card per row, with the column name beside every
  value. Seven columns in 390 pixels is four characters each. The class that
  does it is put on by the code that knows how many columns there are, so a
  two-column table stays a table;
- **the folder picker** fills the screen. A dialog sized for a mouse is a dialog
  you cannot hit.

And one thing that is not layout at all: every input is 16px, because iOS Safari
zooms the whole page in when you focus anything smaller and leaves you scrolled
sideways in a form you were halfway through.

It installs. `viewport-fit=cover` plus safe-area insets so it can sit under a
notch without hiding behind one, and the manifest that was already there gives
it its own launcher icon and no address bar.

There is a browser test at 390x844 that opens **every** feature and asserts
nothing is wider than the screen - the failure you cannot see in a screenshot
taken at desktop width, and the one that makes an app feel broken.

### Setup is not decoration

The trees and the bracket settings live in one place and every feature
reads them, so a form opens with its paths already filled in and you can still
override any of them for one run. That matters twice over:

- A mistyped root does not fail loudly. It mirrors against the wrong tree.
- If previews grouped brackets one way and cull grouped them another, one frame
  of a set would get the preview and a *different* grouping would decide what to
  put aside. That is worse than not grouping at all.

### The loop they make

    setup       once, so nothing has to be typed twice
    unpair      once, to separate the trees
    previews    -> sync to the tablet -> give stars there
    ratings     from the previews, into the library and the RAWs
    cull        by those ratings
    remirror    whenever you have reorganised the library

Every step previews first and names what it left alone and why. Nothing is ever
deleted: culled files move into a `_Culled` folder inside their own tree, keeping
their position, so putting one back is a move.

## Running it

    scripts\check.bat     is this machine ready?
    scripts\test.bat      run every test  (a handful drive a real browser and
                          skip themselves when one is not installed)
    scripts\run.bat       the command line
    scripts\web.bat       the web page on http://localhost:8080

Nothing needs installing except for `previews`, which is the one task that uses
Pillow (`pip install pillow`). Without it that task says exactly what it would
have made and then refuses, rather than half-running.

From a shell:

    python -m app.cli --list
    python -m app.cli cull --help
    python -m app.cli cull --folder "N:\Photos" --raw "N:\Photos Raw" --raw_at_or_below 2
    python -m app.cli cull ... --apply

## Running it on Windows as a program

**See `windows/README.md`.** `scripts\web.bat` is a command you leave a console window
open for. `windows/Install.bat` makes it a program instead: Start menu, desktop,
starts with Windows, no console window, settings under `%LOCALAPPDATA%` so
replacing the folder with a newer copy keeps them, and a **Quit** button in the
app's own top bar - which only ever appears on a copy started that way, because
the one in a container has a stop button already.

That is also how the PC becomes a *server*: set a password, let Windows allow it
on private networks, and a phone on the same wifi finds it by name.

## Finding it from a phone

Every server answers a shout on UDP 8845 with its name, its port and whether it
needs a password - and nothing else, no paths and no counts. So a client lists
"NAS" and "the PC" instead of asking anyone to read an address off a router
page. Setup ▸ *Network* names this machine and can turn the answering
off; `core/discovery.py` is the whole of it, in forty lines of the standard
library.

A client stores a connection against the server's `id`, not its address, because
a phone moves between wifi and Tailscale and the address moves under it.
`GET /api/client` is the one open call that says what a server is and what it
can do - see `claude/photo-manager-client-contract.md` in the project.

`GET /api/gate` is the older open call: whether a password is on, whether
this browser is signed in, and whether the password is `fixed` by the
environment. The page uses neither call, and `/api/client` already says the
first two. The audit (O10) asked for `fixed` to be folded into `/api/client` and
`gate` removed, but only once the client contract was checked for `gate`. In
3.9.1 that contract was not in the repository, the project's shared files or
the project folder on the PC, so nobody could say no client calls it: `gate`
stays until the contract is found and checked.

## Running it on the NAS

**See `nas/README.md`.** In short: nothing is built and nothing is published.
The image is stock `python:3.12-slim`, the app is a mounted folder, and Pillow
installs itself once into the config volume. So updating is *copy the files, hit
Restart* - no rebuild, no image, no wizard.

    nas/docker-compose.yml    paste into Container Manager > Project
    nas/start.sh              what the container runs
    nas/README.md             the whole thing, step by step

The app lives in `docker/photo-manager/code` and its settings in
`docker/photo-manager/config`. `PM_DATA` points at the second - it is the one
folder that must be writable, because the code is mounted read-only on purpose. The app says so plainly at startup
if it cannot write there, rather than failing on the first save.

`ALLOWED_ROOTS` (paths separated by `:`) is a hard boundary when set - a task
refuses a folder outside it, and symlinks cannot sneak by because every path is
resolved first. Unset on the NAS means no restriction: the container's mounts
are the real boundary there. Unset on a PC it used to mean the same, and a PC
has no mounts - the whole disk, a browser profile, this app's own ticket
secret, was a download away for anything on the Wi-Fi. So a PC program with no
`ALLOWED_ROOTS` is fenced to the folders chosen in Setup and those listed under
Also allowed (`app.server.fence`), and before any are chosen to nothing at all.
Two consequences, both deliberate. Setup's folder boxes and the sample library
answer to `ALLOWED_ROOTS` alone, or the library could never move anywhere new;
but only from the PC itself or once a password is on, or anything on the
Wi-Fi could point the library at `C:\` and then download through the fence it
had just moved. And the Also allowed box is drawn only on a PC, where it means
something.

Every box is checked the way its task reads it: a `Folders` box split on
commas as well as lines, a `FilePath` box like a folder. A check that split a
box differently from the task it guarded was a way past it.

**Where a request came from.** Every POST changes something, and with no
password the only thing between a page on another website and `/api/files` was
the browser. A POST whose `Origin` is not the app's own address is refused; so
is one, with no password set, that reached the app under a name nobody here
chose (`PM_HOSTS` adds one), because a site can point a name it owns at a home
address and then its pages share the app's origin. With a password, that name
has no cookie and cannot sign in, so the check steps aside. HTTP Basic counts
toward the same lockout as the login form, and behind a reverse proxy named in
`PM_TRUSTED_PROXY` the lockout is per phone (`X-Forwarded-For`, read from the
proxy's end) rather than one for the whole house.

**Looking is not touching.** The folder browser lists anything the process can
read and marks what a task would refuse, rather than stopping at the fence.
Stopping at it produced "no folders" for a machine plainly full of them, with
nothing to separate a wrong path from a wrong fence - and in a container the
mounts are the real boundary anyway: a folder that is not mounted does not exist
in there to be listed. Which is also why *"is not a folder"* for a path you can
see in File Station means the volume is missing from the compose file, not that
the path is wrong.

DSM's Task Scheduler can run any task, because everything is on the command line:

    docker exec photo-manager python -m app.cli remirror --apply

That is a fresh process, not the one `run.py` started, so the compose file sets
`PYTHONUSERBASE: /config/python` for the whole container: it is where
`ensure_pillow` installs Pillow, and without it a scheduled `previews --apply`
could not see the copy the running app was using.

## The ideas the whole thing rests on

**A pair is an identity, not a position.** A RAW is tied to its JPEG by capture
time + camera + base name. Nothing in that depends on a path, so you can rename
and reshuffle the library freely and every link still holds.

**A moved JPEG and a deleted JPEG look identical from the RAW's position.** Since
moving is the case `remirror` exists for, "not where I left it" can never mean
"delete the RAW". The whole library is searched by identity first, and only a RAW
whose JPEG is nowhere at all counts as orphaned - and even then it is put aside,
never deleted.

**A bracket is told from a burst by the exposure bias, and by nothing else.**
Burst frames share one bias; bracket frames cannot. Everything else about them -
seconds apart, same aperture, same ISO - is identical.

**Zero stars means unrated, not rejected.** An unrated photo is never culled.

**How finely a folder is split is a per-folder decision.** A quiet year is fine
by month; a fortnight abroad is thousands of frames in one folder and wants days
or weeks. Sorting only ever reshapes the folder you point it at, so one travel
folder can go by day while the rest of the library stays by month. A week folder
is named by the date the week began and sits under the year, not the month -
a trip from the 29th to the 4th is one week, and ISO week numbers put 1 January
2022 in week 52 *of 2021*, which is correct, useless, and looks like a bug.

**A folder's date comes from the photograph, never from the file.** A file's
timestamp says when it was last copied, so sorting a restored backup by mtime
files the whole library under one month - silently, and it looks like it worked.
Anything without a readable capture time keeps its position and is named.

**A box you emptied is not a box you never filled.** Both arrive as `""` once a
form has been through a browser, and treating them the same made "leave blank to
leave RAWs alone" a sentence the app did not keep: Setup filled the box straight
back in. Only folders work this way, because only folders have something a blank
could mean.

**Developing on a tablet needs a memory, and it is the only thing here that
does.** A developed photo and an undeveloped one look identical in the library,
so "has this been developed" cannot be measured - it has to be written down.
`core/ledger.py` records it by identity (capture time + camera + name), so the
develop tree empties as you finish things and a renamed shoot never comes round
again. Everything that CAN be measured still is.

**A bracket is not a set of duplicates, and a preview is not a copy.** Both share
everything a naive duplicate rule matches on - one camera, one second, one name.
So duplicates are found by identity INCLUDING the base name (a camera never gives
two frames the same one), only ever within one kind, and only ever within one
tree. Identical bytes is reported as a fact; the same photo saved again is
reported as a judgement and moved only if you ask.

**The Library says what IS; History says what was DONE.** Neither can answer the
other's question. The Library reads the files as they are now, so it cannot tell
you what happened to a folder last night; the log records every run that wrote
something - from the page, the command line, or DSM's scheduler at 3am - so it
cannot tell you the state of anything. Both exist for that reason.

**Anyone on the network can reach it, until you lock it.** Setup > Password
sets one password for the whole app - no accounts, no user list - and the next
browser to open it gets a login page. What is kept is a PBKDF2 hash with a
random salt, never the password; a browser that gets it right is given a signed
ticket in a cookie that survives a restart and expires on its own. Scripts and
the command line use the same password over HTTP Basic. `PM_PASSWORD` in the
compose file still works and wins where it is set, because a decision made
outside the app must not be changeable by anyone who got in once.

Off by default, because on a home network with one person on it a login screen
is friction for no gain - but the honest position is that without it anyone who
can reach the port can look at every photo *and* move, cull and re-mirror them,
and the second half was always the larger exposure. It is http on a LAN either
way: a lock on the door, not a sealed envelope.

**Looking is work, so it is a job.** Planning used to be a blocking request: a
Library survey held one HTTP connection open for the length of the scan, showed
no progress, could not be cancelled, and was indistinguishable from a page that
had hung. Both halves - looking and doing - are now phases of one job with an
id, so one bar at the top shows everything in flight whichever tab started it,
several at once, and a scan can be stopped part way. A task earns a Stop button
by accepting a `progress` callback; one that cannot say where it has got to is
not offered a button it would ignore.

**Mirroring is a mode, not a path you retype.** The trees are written
down once, in Setup; asking again in every form was never a question worth
asking, and the fallback when a box was left empty - "measure the position from
the folder being scanned" - is what put previews flat in the top of their tree.
So there is a switch, on by default: the roots come from Setup, the position is
worked out from the library, and the destination boxes are greyed out because
they show where things go rather than deciding it. Turn it off to send one run
somewhere else.

**One box follows another.** Pick `Photos/2022/Spain` and the RAW and previews
boxes already say `2022/Spain` in their own trees. The task then strips that
position back off before mirroring into it - both halves or neither, because
filling the box without the strip writes `Photos Raw/2022/Spain/2022/Spain`.
A box you have typed in stops following: one that overwrites what you just typed
is worse than one that never helped.

**A result belongs to its tab, not to the page.** Switching away and losing a
result you waited two minutes for is why people stop switching - and half of
this app is about opening one feature because of what another one told you. Each
tab keeps its own form, its own last result and its own running job; a run
started on one tab keeps running while you look at another and is waiting for
you when you come back.

**Nothing has to be typed twice.** Setup says where the library is; the app also
remembers what you last pointed each task at, and that fills the box - unless
that folder has since gone, in which case Setup fills it instead. A form that
opens on a path that no longer exists is a form that lies to you.

**Status is measured, never remembered.** The Library view reads the files as
they are now rather than a log of what was done. A log would quietly stop
describing the folder it names the moment you rename a shoot in File Station, and
nothing would tell you it had gone stale - the worst property a status display
can have. The cost is reading every JPEG, so each folder's answer is cached
against a fingerprint of its own files and re-read only when those change.

**A sidecar travels with its file.** An .xmp left behind does not lose a rating
loudly; the file simply reads as unrated from then on.

**A clock correction moves the RAWs too.** Pairing is built on capture time, so
retiming the JPEGs of a shoot and leaving the RAWs behind breaks every pair in
it - and it surfaces days later, as RAWs that look orphaned, in a task with
nothing to do with clocks. The RAW is never opened; its corrected time goes in
the .xmp beside it, and a sidecar time beats the embedded one for any file the
app will not write into.

**Tidying stops at the folder you ran it on, and never takes the Recycle
Bin.** Every feature that moves photographs removes the folders it emptied,
and walks upward because a shoot's year empties with it. That walk once had no
top, and counted `#recycle` and `@eaDir` as litter: a cull near a share root
found the root holding only those two and removed the share's Recycle Bin
with it. Now the walk stops at the task's own folder and at every Setup tree,
a folder holding `#recycle`, `@recycle` or `@eaDir` is not empty, and the only
litter removed is files (`Thumbs.db`, `.DS_Store`) in a folder otherwise
empty. Clean up never walks into the bin or `@eaDir` either; its *Thumbnail-only
folders* still offers an `@eaDir`-only folder, because that is asked for by
name.

**Every move is written down as it is made.** History's Put it back reads the
moves a run recorded, so a move that is not recorded cannot be undone after the
toast has gone. The file manager, the viewer and Power rename record theirs;
File developed and Separate RAWs do too; a delete that fails part-way still
records what had already gone into the bin, and refuses before anything moves
when one of the files has no bin to go to. Clean up's plan says on each row
whether it goes to the bin or is deleted outright, and a tree with no bin is
refused when the bin was asked for.

**A rating lives in three places, read in one order.** A sidecar first (the
only place a RAW can be rated), then the photo's own XMP packet, where
Lightroom, Bridge and darktable write it, then the Windows tag. Writing a
rating into a JPEG keeps the packet and the Windows tag in step, and a packet
past the first quarter megabyte is read by reading further rather than taken
as missing - a writer that cannot find it refuses instead of building a new
one over it.

## Traps the Windows version fell into

Kept here because they were real, and each one looked like working code:

- A latitude is **three** rationals - degrees, minutes, seconds. Reading only the
  first gives whole degrees: sixty miles out, and a plausible-looking number.
- An EXIF thumbnail is itself a JPEG, so searching for the first start-of-scan
  marker finds the thumbnail's. Walk the segments instead.
- "Must end with FF D9" is wrong. Panasonic pads with nulls after it.
- Zero means *unrated*, not zero stars.
- Locale: parsing "24.497858" where the decimal separator is a comma gives
  24497858. Everything numeric here is parsed and written in the invariant form.
- Prefix comparison says `N:\Photos Raw` is inside `N:\Photos`. Check for the
  separator too, or files land in the wrong tree.
- An option accepted by the form but never read by the writer is worse than one
  that was never offered. `Task.make_plan` exists so that cannot happen again.
- A sub-directory pointer counts from the start of the TIFF header, and where
  that sits in the buffer depends on how the block was obtained. Adding a fixed
  six to both reads the wrong place, finds nothing, and looks like a photo with
  no capture time.
- Another app's working folders sitting inside the library - PhotoPrism's
  cache, Synology's `@eaDir` thumbnails - counted as photos, so a folder of 40
  reported 400 and "0 of 400 geotagged" was a state you could not act on. Worse,
  a task could move them. Setup keeps a list of folder names never to walk into,
  and yours are ADDED to the built-in ones rather than replacing them.
- Following the machine's colour scheme and nothing else is a page you cannot
  make light on a machine that says dark. The dark palette therefore exists
  twice - once behind the media query for Auto, once on an attribute the button
  sets - and the choice is applied before the first paint.
- A compose change applied with Restart. Volumes and environment are fixed when
  a container is CREATED, so a corrected path did nothing and the app went on
  saying "is not a folder" about the path just fixed. The header now states what
  code is running, for how long, and which allowed folders it cannot actually
  see - because a cached page, a Restart that did not take, and a missing mount
  are three different faults with one symptom.
- Changing the preview size did nothing and said nothing either - existing
  previews are deliberately never replaced. Correct, and indistinguishable from
  broken. A preview made at a different size is now noticed and remade.

The https address a phone needs for the shell and the notice is in
`nas/README.md` under **On a phone**.
