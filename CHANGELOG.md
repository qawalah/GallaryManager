# Changelog

What changed in each release, newest first. The release number is `RELEASE`
in `app/version.py`, and the page header shows it.

## 4.0.0 - 2026-10-21

A new look: the page is printed like an exhibition catalogue, with the
photographs leading. Nothing was removed; every tool, option and setting is
where it was, and the look before this one is still under Appearance.

### Changed

- **Black stock by default, white stock in the light.** Hairline rules
  instead of shadows and boxes, square corners on everything (chips and
  filters included: a filter that is on fills with ink), and the primary
  button printed in the page's own ink (bone on black, black on white). In
  the light the ground and the cards are the same white, told apart by their
  hairlines. The header and the phone's bottom bar are solid, so words
  scrolling under them no longer show through. A browser that has never
  chosen opens dark; Auto, Light and Dark are all still on the theme button.
- **One typeface, one scale.** Archivo, served by the app itself (no internet
  needed), on eight sizes: 12, 13, 14, 16, 20, 28, 40 and 64 pixels. Counts
  line up in columns.
- **Five section inks.** Each group of tools (Organize, Metadata, Review,
  Develop, Maintain and Settings) keeps its colour, now strong enough to read
  as text on both stocks. A tool's page opens under a band of its group's ink,
  the step you are on is ruled in it, and the rail marks each group with it.
- **Home opens on the photos.** The newest photos hang as plates, the newest
  one twice the size and six round it in two whole rows, each with a label
  naming its folder, file and day on lines of their own. The four figures
  follow as a ruled row of large numbers in ink, then the dashboard. On a
  phone the plates are one row you swipe along.
- **Check the list leads with the decision.** What a run found and what it
  would do are printed on the page under rules of ink rather than in boxes.
  The approval prints the operation as one line, "Move 412 files" with the
  count at 64 pixels, then the facts in ruled columns, then the button that
  names what it will do.
- **Tools is a contents page.** Each group opens under a band of its ink and
  a large title, and its tools are ruled entries under it, without boxes or
  tinted squares round the icons.
- **The four steps** are a ruled row whose rule fills in as a run moves on,
  with all four labels kept on a phone.
- **Tools and Settings have more room:** wider gaps between groups, roomier
  entries and taller controls.
- **Drawn marks.** Closing crosses, the viewer's arrows and the fold and sort
  arrows are drawn from the app's icon set instead of typed characters, which
  each font drew at its own size.
- **Motion.** A screen slides in from the side you are going to, and back the
  other way; the newest photos arrive a beat apart; the count on the list
  settles into place. All of it is off for anybody whose machine asks for less
  motion.
- **The viewer's side panel is always dark,** like the stage beside it.
- **The sign-in page** wears the same look and follows the theme you chose.
- The old look is the **Original** theme with the **Blue** accent, under
  Appearance. The new default accent is **Ink**.

### Accessibility

- A live region reads out a list as it arrives ("Nothing has been written
  yet. Move 412 files"), a run's result, and every toast. A toast with Undo
  stays six seconds rather than two and a half.
- A **Skip to the page** link is the first thing the keyboard reaches.
- On a phone, the header buttons, filter chips, rail rows, fold rows and the
  buttons that run something are at least 44 pixels tall; the help bubble is
  larger and answers a 44-pixel tap.
- Fixed contrast: the lit rail row (was 3.9:1), the switched-off chart legend
  (was 2.6:1, now struck through instead of faded), the sign-in button in the
  dark (was 2.4:1), and the browser's own placeholder text.
- The Guide's title is a level 2 heading, so the page's headings no longer
  skip a level.

### Tests

- `test_design.TheCatalogue`: every font size is on the scale, the typeface is
  the app's own, each section ink reads at 4.5:1 on both stocks, Ink is the
  default accent and the Original look is kept, nothing is striped down its
  side, the new motion stops under reduced motion, and the live region and
  skip link are in place.
- `test_server.TheTypeface`: the font is served before the login gate, an
  unknown font is not found, and the page, sign-in page and service worker all
  ask for it.
- `test_page_behaviour`: a tool carries its group's ink and its list is read
  into the live region; nothing slides under reduced motion.

## 3.15.0 - 2026-10-19

Each tool opens on a page of its own, with the rest of its group beside it.

### Changed

- **No tab row on a tool.** Sort into folders no longer carries Place names
  as a tab, Cull by rating no longer carries five more, and so on. Every tool
  is its own page.
- **The group, down the right.** Beside the form is the group the tool is
  in (Organize, Metadata, Review, Develop, Maintain, Automation or
  Settings) with every tool in it and the open one lit. It is read from the
  same arrangement as All tools and the rail, so a tool moved to another
  group on All tools is listed with its new group. The heading opens that
  group on All tools.
- Below 1060 pixels wide, and on a phone, the list goes under the form.
- The NAS pair stays one line beside Setup, with Reindex and Permissions
  under it while you are in one. Put a run back and Clear the history, which
  are in no group, are listed under History on History's page.

### Tests

- `test_page_behaviour` checks that no tool draws a tab row, that the list is
  the tool's group with it lit, and that it follows an arrangement saved on
  All tools. The tests that drove the old tab row drive the list instead.
  `test_web.OnePagePerTool` holds the same in the source.

## 3.14.2 - 2026-10-19

The audit's glossary table, applied everywhere a person reads. 3.14.0 applied
it to the tools' names and option text, which is what the test checked; the
rest kept the old words.

### Changed

- **Plan notes, rows and results** say photo, RAW file, video, tool and move
  aside instead of photograph, picture, negative, clip, feature, task and put
  aside: about 270 strings across 60 files, with the tests that quoted them.
- **The page's own text** that still said photograph, picture, clip,
  negative, shot details, marks, plan or go ahead now says it in the table's
  words, and 43 of those sentences moved into `page/strings.json`, so Setup >
  Wording can edit them. The video badge on a tile says "video", the menu
  button is "Tools", the viewer's exposure button is "Exposure details" (and
  its Setup key), and the grid view is "As thumbnails".
- **A few tool texts**: Thin brackets moves the spares aside, Unpair takes
  RAWs out of the library folders, the Guide's cull page says blurry photos,
  and the Library's help says columns.

### Tests

- `core/wording.BANNED` is now the whole "do not use" column of the table,
  and `tests/test_wording.TheGlossaryEverywhere` holds it against every string
  the Python can print (app, core, Windows, NAS, doctor) and every piece of
  text the page's scripts and HTML show, not only the option text.

## 3.14.1 - 2026-10-18

- The Cameras tile on Home said 6 for any library with more than six cameras.
  It counted the overview's short list of the six biggest; it now counts the
  camera chart's own rows, so the tile and the chart beside it agree.
- The same tile on the Library tab counted "not said" as one more camera. It
  leaves it out now, as the Years tile already did. Both use one count,
  `Counted.named()` in `core/stats.py`.

## 3.14.0 - 2026-10-18

The third audit (`audit/AUDIT-2026-10-17.md`), fixed in five phases and
merged as one release: data safety, security and the fence, the index and
the tools, the page, and the wording, with a Setup > Wording editor to
change any of it in place. Each phase was a pull request of its own
(#30, #32, #29, #35, and #28 to #42 for the wording); their notes follow.

### Phase 1: data safety

Data safety: nothing near a share root is removed that should not be, and
every move can be put back from History.

#### Fixed

- **Tidying no longer removes the share's Recycle Bin.** After a run emptied
  a folder, the tidy-up walked upward with no stopping point and counted
  `#recycle` and `@eaDir` as litter, so a folder near the share root holding
  only those was removed with everything in the bin. It now stops at the
  folder the task was run on and at every Setup tree, a folder holding the
  Recycle Bin or `@eaDir` is never empty, and only litter files such as
  `Thumbs.db` are removed. Clean up no longer walks into either.
- **Clean up says when it deletes.** With *Use the recycle bin* ticked, a
  tree on a share without a bin is refused and named, instead of deleted
  outright while the plan said "the recycle bin". Each row says where it
  goes.
- **Put it back works for the file manager, the viewer and Power rename.**
  Their moves, deletes and renames now reach History with the files they
  moved. File developed and Separate RAWs record theirs too.
- **A delete that cannot finish moves nothing.** A photo whose RAW is on a
  share with no Recycle Bin is refused before anything moves; a delete that
  fails part-way still records what it had moved. The viewer says which
  copies it left because their share has no bin.
- **Renaming never writes over a sidecar.** Renaming a photo to a name whose
  `.xmp` already exists is refused. Power rename now renames a picked
  file's sidecar and updates the index.
- **Moving a folder in the file manager moves its RAW and previews folders**,
  as renaming and Delete folder already did.
- **Send to develop takes back only what it was asked about.** A run on one
  shoot, or one colour, used to take every other shoot and colour off the
  tablet.
- **Lightroom's ratings and packets are kept.** The rating in a JPEG's own
  XMP packet is read, and writing a rating updates it too. A packet behind a
  large ICC profile is found instead of being replaced by a new one, and
  adding or removing a tag keeps the keywords already inside the photo. Each
  JPEG is read once more so ratings and tags made in Lightroom show up.

### Phase 2: security and the fence

Security and the fence, from the third audit (phase 2).

#### Added

- **Also allowed** in Setup, on a PC only. A PC program now reaches the
  folders chosen in Setup and nothing else on the disk; a folder added here
  is let in too, for a GeoNames download or a folder to export into.
- `PM_HOSTS` and `PM_TRUSTED_PROXY`, for a NAS behind a reverse proxy
  (nas/README.md).

#### Fixed

- **A page on another website can no longer drive the app.** A change whose
  browser says it came from somewhere else is refused, and with no password
  so is one sent under a name nobody here chose.
- **Wrong passwords sent by a script count.** HTTP Basic goes through the
  same lockout as the sign-in page, and behind a trusted proxy each phone is
  counted on its own instead of the proxy locking everybody out.
- **The PC no longer serves the whole disk to the Wi-Fi.** Downloads, file
  lists, "is it there" and every folder or file box are fenced to Setup's
  folders. Setup's folder boxes can be changed from the PC itself, or from
  another device once a password is set.
- A folder box with a comma in it, a file box (Reference photo, Backup to
  restore, the GeoNames files) and New folder with no folder chosen can no
  longer reach past the fence. The folder picker lists file names only inside
  it.
- An album or dashboard arrangement with an apostrophe in its name opens
  again, and a name can no longer run as script on the page.
- A password with a slash in it is no longer written to the run log.
- A file named in Arabic, Chinese or with an emoji downloads instead of
  failing silently.
- A password, or a name, outside plain ASCII works over HTTP Basic and in
  `PM_PASSWORD`; it used to be an error on every try.

### Phase 3: the index and the tools

The index and the tools, from the third audit (phase 3).

#### Fixed

- **Clips have a capture time in the index.** Videos were all "undated" on
  Home and sorted by file time. The index now reads a clip's own header (as
  Separate video does), then ffprobe when it is installed, then the file's
  time.
- **Photographs added outside the app are found.** A card copied over SMB or
  a phone backup now shows up within five minutes without running a task.
- **A rating changed in place shows on the Library tab**, and a move made in
  the explorer while the index is reading keeps the index marked stale.
- **The command line refuses what it does not understand.** A misspelt
  option, or `automation --which` naming a flow that does not exist, now
  exits with status 2 and runs nothing, instead of running on Setup's
  defaults or the first flow. `--list` and `--help` exit with status 0.
- **Re-mirror video** files by year, month and day when asked, and leaves
  emptied folders when Tidy is off.
- **The confirmation button counts the right thing**: photographs, frames,
  copies or steps rather than every file row. Blur's tag mode says Tag.
  Send to develop says Copy, Take back or both.
- **Find duplicates** checks the RAW tree on its own and builds `_Duplicates`
  at the top of the tree, not inside the folder scanned.
- **Fix the clock** accepts a reference photo picked as a whole path.
- **Stop on Automation** stops the pass, not only the bar.
- **NAS**: a scheduled `docker exec ... app.cli previews --apply` finds
  Pillow, and phones that find the app are sent to the mapped port.
- **Windows**: Install.bat no longer runs its install block twice.
- The top-level README is this project's own.

### Phase 4: the page

The page keeps its promises: phase 4 of the third audit (`AUDIT-2026-10-17.md`,
PG1, PG2, PG4 to PG14, PG15, PG17 to PG19, PG21, PG22, UI1, UI4, UI6, UI8 to
UI12, UI14, UI16).

#### Fixed

- **Deleting a selection offers Undo.** The dialog said so and the toast had
  nothing to press; it now puts the files back. It no longer says "NAS" on a
  PC, and says that nothing is deleted where there is no Recycle Bin.
- **A help bubble opens with one tap.** The selection bar bound the bubble's
  listeners again on every redraw, so after an even number of redraws a tap
  opened and shut it at once.
- **The newest search wins.** Typing while the last answer was on its way
  dropped the new text; now every ask is numbered and only the newest draws.
- **Screens that cannot reach the app say so.** Photos, Places, Albums and
  People showed "Reading..." for ever; they show "Could not reach the app"
  with Try again, as Home does.
- **Home's Re-read library button shows its own "Reading...".** It changed
  the rail's button instead, or "Open Setup" on a new install.
- **Back works after opening a tool from the header, a job row, the guide or
  a notification**, and the page's Back arrow and the browser's Back are one
  history: pressing one no longer leaves entries for the other to do nothing
  with.
- **No browser pop-ups.** Keep as an album, Forget album and Remove flow ask
  in the app's own dialog (an installed iOS app suppressed the old prompt).
- **Keyboard and screen readers.** The viewer and dialogs keep Tab inside and
  give focus back when they close; the Keys card closes with Escape and its
  Close sits at the top; a pinned tool's cross is a real button that Tab
  reaches; grid tiles say their name, stars and colour; menus no longer claim
  to be a `menu` they are not.
- **The offline copy is always the app**, never the sign-in page; Reload no
  longer keeps a copy per press, thumbnails are capped and cleared when the
  pictures change.
- **One way of saying things.** Counts say "1 photograph" and "12
  photographs", not "photograph(s)" (Home said "1 minutes ago"); times are
  "17 Oct 20:24" everywhere; the Country and Near town notes sit under their
  labels.

#### Changed

- **More settings (N).** Setup's "More" and every other form's "Advanced · N
  settings" are one fold, and group headings are in sentence case.
- **Primary buttons in dark mode have dark text** on the light accent (white
  was 2.6:1); the light Teal, Green and Amber accents are a shade deeper so
  white text on them passes 4.5:1.
- **One set of label colours, one chip shape, one breakpoint (860px).** The
  Flows pill has a chevron because it opens Automation. Unused markup and
  styles (`library/shell.html`, `#detail`, `.backbar`, `.btnlink`,
  `.fmgroup`, `body.installed`) are gone.

### Phase 5: one name for each tool and each button

One name for each tool and each button, wherever it appears (audit UI2, UI3,
UI13, PG16).

#### Changed

- **A tool has one name.** The rail used to call nine tools something other
  than the Tools cards, History and search did. Each now has one name: Find
  brackets, Clear the history, Geotag, Rating & tags, Storage, Fix the clock,
  Clean-up status (was "What can be cleaned up"), Location timeline, Power
  rename and Put a run back. A tab only shortens its title (File explorer is
  Explorer in the rail).
- **"Tool", not "feature".** The Tools search box, History's and Clear the
  history's tool pickers, the flow messages and the Guide say "tool".
- **File explorer is File explorer.** The Guide said "Files", the buttons "Open
  the explorer" and "Show in the file explorer".
- **Re-read library is one button.** Home and the rail draw it from one
  function, and the copy you press is the one that says "Reading...". People's
  two buttons for the same thing both say "Tag a folder".

### Phase 5: the Setup > Wording editor (WD1)

The wording of every tool can be edited inside the app (audit WD1).

#### Added

- **Setup > Wording.** Turn on Setup > Developer mode (or set
  `PM_DEVELOPER=1`) and a Wording tab appears under Setup. Pick a tool and
  every piece of its text is a box: title, tab, summary, each option's label
  and help, each choice and each group heading. A box saves when you leave
  it, and the tool's own form says the new words at once. Each card counts
  words or sentences and warns about what the style guide warns about
  (dashes as full stops, capitals for emphasis, long sentences, words the
  glossary replaces). A label of five words is refused, as the tests refuse
  it. Reset to shipped puts one box back; Reset everything puts them all back.
- **Download and upload wording.json.** The download is every edit with the
  text it replaces and the file and line it belongs on. Upload merges a file
  back in, or replaces your edits with it.
- **tools/merge_wording.py** writes a downloaded file into the source,
  checks each line still says what the export says it replaced, and loads
  the app again to prove every merged line now ships.
- `python -m app.cli wording` lists what has been edited; `--help` for any
  tool reads the edited text.

### Phase 5: Organize tools (WD2)

The approved rewrites for the Organize tools are in the source (audit WD2,
first family).

#### Changed

- **Organize wording.** Sort by date, Places, Unpair, Mirror RAWs, Videos,
  Mirror videos, File explorer and Power rename say what each option does in
  the approved words: labels of four words at most, help that opens with what
  the box is for and states its range and default, choices named for what
  they do, and group headings such as "Companion folders". The shared
  "Folders to skip" help now says Setup's list is always left out as well.
- Power rename's plan and table call the depth "Levels to list" and the start
  "Start at level", as its form does. The explorer's View menu says "RAW files
  follow", as the option does.

### Phase 5: Metadata tools (WD2, TK13)

The approved rewrites for the Metadata tools are in the source (audit WD2),
and Geotag and Pin stop promising a copy they do not keep (TK13).

#### Changed

- **Metadata wording.** Geotag, Location timeline, Fix the clock, Import
  Google Timeline, Pin a place by hand, Strip location, Rating & tags, Apply
  label and Tag photos read in the approved words. "Clock fast by (minutes)" fits in four
  words, so the one long label the tests allowed is gone.
- Plan figures follow their options: Apply label says "Colour label" and
  "Photos to mark"; Location timeline counts "From your photos".

#### Fixed

- **Geotag and Pin said the un-located original was kept aside** even though
  Keep originals is off by default and nothing was kept. The confirmation now
  says Strip location takes the location out again, and only says the copy in
  _NoLocation is the undo when Keep originals is on for that run.

### Phase 5: Review tools (WD2, TK12, TK14)

The approved rewrites for the Review tools are in the source (audit WD2), with
the two findings they flagged fixed in the code (TK12, TK14).

#### Changed

- **Review wording.** Library, Search, Compare, Find brackets, Check exposure,
  Thin brackets, Cull by rating, Find blurry and Find duplicates read in the
  approved words. Library's "Trees from Setup" help says it only changes what
  is compared, since Library writes nothing.
- Compare's plan names its axes "Rows" and "Columns", and Find blurry's last
  column "What to do", as their options do.
- Enter in Tools > Find a tool opens the tool whose name holds the word before
  one that only mentions it ("cull" opens Cull by rating, not Thin brackets).

#### Fixed

- **Check exposure had its own "Folders to skip" box** under Tags, a second
  name for the box every other tool calls "Skip these folders". It now has the
  shared one, which also says Setup's list is always left out (TK12).
- **Thin brackets' "Include probable sets" did nothing** unless Setup > Include
  hand-bracketed was on too, because only Setup reached the bracket finder.
  The box now asks for probable sets itself (TK14).

### Phase 5: Develop tools (WD2)

The approved rewrites for the Develop tools are in the source (audit WD2).

#### Changed

- **Develop wording.** Make previews, Re-mirror previews, Send to develop and
  File developed read in the approved words. The preview sizes are named
  "Small: 1280 px, quality 80" and so on, in Make previews and Setup alike;
  Send to develop's thresholds are "Send RAW from (stars)" and "Send JPEG from
  (stars)", grouped under "What to send", "Colour labels" and "Trees".
- The note under a folder box says "2022/Spain: the RAW tree and the previews
  tree followed to the same place", now that the tree labels are names
  without "The" in front.

### Phase 5: Maintain tools (WD2)

The approved rewrites for the Maintain tools are in the source (audit WD2).

#### Changed

- **Maintain wording.** Storage, Clean-up status, Clean up, Delete folder,
  History, Put a run back and Clear the history read in the approved words.
  Clean up names its piles "Culled photos (_Culled)", "Duplicate copies
  (_Duplicates)" and "Originals (_NoLocation)".
- Clean-up status calls the piles by the same names as Clean up, and counts
  "Photos in them".

### Phase 5: Automation tools (WD2)

The approved rewrites for the Automation tools are in the source (audit WD2).

#### Changed

- **Automation wording.** Automation, Flows and Automation runs read in the
  approved words. Automation runs offers "Passes that did something" or
  "Every pass", and "Passes to show".

### Phase 5: Setup and the settings screens (WD2)

The approved rewrites for Setup and the other settings screens are in the
source (audit WD2, last family of tool text).

#### Changed

- **Settings wording.** Setup, Checklist, Permissions check, Reindex, Colour
  meanings, Camera names, Chart bands, Password, Backup and Sample library
  read in the approved words. Setup's groups are "Trees", "Skipped folders",
  "Network" and "Viewer keys"; each colour on Colour meanings has "Meaning",
  "Extra tags", "Develop subfolder" and "Send the RAW file". Setup's copies of
  the develop and filing settings use the same names and choices as Send to
  develop and File developed.
- Setup > Include hand-bracketed says Thin brackets can also find
  hand-bracketed sets with its own box (TK14 in 3.13.3).
- Every option of every tool now has help.
- The NAS and Windows guides, DESIGN.md and ROADMAP.md use the new names
  (Setup > Network, Library, RAW tree, Previews tree, Destination folder).

#### Fixed

- **tools/merge_wording.py** no longer writes one key's text into a line of
  source that several keys share (Colour meanings declares all five colours in
  one loop). It leaves the line and names every key on it, so it is edited by
  hand.

### Phase 5: the style guide as a test

The style guide the rewrites were written to is now a test (audit 10.7).

#### Changed

- **tests/test_wording.py holds every piece of tool text to the style guide**:
  every option has help; no title, tab, line, summary, label, help, choice or
  group heading uses a dash as a full stop, capitals for emphasis, a sentence
  over 25 words, a semicolon or a word the glossary replaced; every number box
  names its unit in the label or the help. The rules are the ones Setup >
  Wording already warns about, in `core/wording.py`, which now knows a few
  more names (IPTC, DLNA, VPN, QGIS, LUMIX) and that "Task Scheduler" and "a
  negative number" are not banned words.
- The one-line descriptions on the Tools cards follow the glossary too
  ("photos", "videos", no dashes). Three helps that ran over 25 words in one
  sentence are split.

### Phase 5: page text and the Guide in the editor (WD2, part 2)

The page's own words and the Guide can be edited on Setup > Wording too
(audit WD2, the STRINGS table, phase 2 of the editor).

#### Added

- **app/web/page/strings.json**: the toasts, dialogs, counts and badges the
  page used to write inline, about a hundred of them, in one table. The script
  reads it as `S` and counts with `say()`, which picks "1 file" or "3 files"
  instead of "3 file(s)" and writes numbers the reader's way ("1,000").
- **Setup > Wording lists "Page text" and "Guide"** after the tools. Their
  edits reach the page as it is served (`app/pagetext.py`), the export names
  the line in strings.json or app/page.py, and `tools/merge_wording.py` writes
  them back like any other.

#### Changed

- The Guide is rewritten to the style guide: no capitals for emphasis, no
  dashes or semicolons, "photo", "RAW file" and "video" as the glossary says.
- The Photos and album filters use the names Search uses for the same facts
  ("Taken on or after", "City or town", "Which files", "Missing fact").

## 3.12.1 - 2026-10-14

The Library tool follows a new library too.

### Fixed

- **A tool no longer opens on the old library after Setup changes it.** The
  Library tool (and any other) could still say "last used" beside the
  library you had moved away from. Older versions remembered running a tool
  on Setup's own library as your pick, and a pick like that could outlive
  the library moving. Each remembered folder now carries
  what Setup said when you picked it and is checked against what Setup says
  now, however the settings were changed. A folder of the old library falls
  back to Setup's; a folder you picked outside the library, such as an
  Inbox, stays. A folder remembered by 3.12.0 or earlier is only used if it
  is inside today's library; pick it once more and it is remembered
  properly.

## 3.12.0 - 2026-10-12

A search of thousands lists every one of them, and the explorer keeps up.
Two things went, by request: the Lately list in the rail, and Install as an
app.

### Fixed

- **"Send these to Files" keeps what you searched for.** Opening the Files
  tab starts a read of the library folder, and the matches used to land on
  top of it without claiming the pane - so on a big library the folder came
  back a second later and replaced them with every photograph. The set now
  claims the pane the way a folder read does, and a late folder answer is
  thrown away.
- **Re-read library reads it again.** The button asked for the ordinary pass,
  which on an unchanged library opens nothing and finishes in a second looking
  as if it never ran - and while the minute's own pass was running it was
  refused and did nothing. It now asks for the deep pass (every file opened
  again), and a pass already running is stopped to make room for it.

- **Search counts every match.** "Found 5,000" for a chart row that said
  6,000 was the cap on what Search kept, said as if it were the answer. The
  count is now every match; what is kept and listed goes up to 20,000, and a
  note says when a search went past that.
- **Search lists what it found.** Before, the first 400 matches were listed
  and the rest only counted. Now every kept match goes to the page.
- **A chart on Home searches what Home counted.** Home counts the library and
  the video tree together; pressing a row used to search the library alone, so
  the search came up short by the clips.

### Changed

- **Long tables are drawn 500 rows at a time.** Any plan's table draws the
  first 500 rows, with *Show the next 500* and *Show all* under it. The count
  in the heading, the confirmation and the sort are always the whole list.
- **The file explorer draws 400 rows at a time.** A listing of thousands -
  what *Send these to Files* hands over - draws the first 400, in list or grid
  view, and draws the next 400 as you reach the bottom or press for them. The
  counts, *Select everything* and the viewer still work on the whole listing.
  Before, every pick redrew every row, which is what made the page sluggish.
- **The found card holds its paths once** instead of writing all of them into
  its two buttons.
- **Files takes as many paths as a search keeps** (20,000, was 5,000).

### Removed

- **Install as an app.** The rail's button, the install prompt and the web
  manifest behind them. The page still works on a phone as a page; the
  service worker that keeps the shell and thumbnails stays.
- **Lately.** The list of the features you opened lately, under the pinned
  ones in the rail. Nothing notes what was opened any more.
## 3.11.2 - 2026-10-12

Separate video and Re-mirror video say what they are doing.

### Fixed

- **Separate video with "File by shoot" finishes.** To know which shoot a clip
  was taken among, it read the capture time of every photograph in the
  library, opening each one on the first run. Over a network share that took
  long enough that it looked as if it never finished, while the same run
  without "File by shoot" was quick. It now takes those times from the index,
  which already holds them, and reads the photographs only for a library the
  index has not read yet. Re-mirror video asks the same question and gets the
  same answer.
- **Separate video no longer looks stuck while it moves big clips.** When the
  video tree is on another drive from the library (on Windows, a library on
  one share and the video tree on another), each clip is copied through the
  PC, and a few gigabytes took minutes with the bar at "0 of N" and no name
  under it. Each clip is now named before it moves, the line under the bar
  counts the gigabytes as it copies, and Stop works part-way through a clip:
  the clip stays where it was and no half copy is left. A clip that cannot be
  removed after copying (open in another program) is not left in two places.
  Re-mirror video moves through the same code.
- **Looking says it is listing the library.** Before the first count there was
  an empty bar that only said "reading"; it now says which folder is being
  listed.
- **Re-mirror video says where the clips are when its tree is empty.** It only
  rearranges clips already in the video tree, so with every clip still in the
  library it found nothing to do and said only that. It now says how many
  clips are still in the library and that Separate video moves them out.
- **The page says when the app stops answering.** A run whose progress could
  not be read retried in silence for ever; after a few seconds the card now
  says the app is not answering.

## 3.11.1 - 2026-10-12

Changing the library reaches everything now.

### Fixed

- **Search no longer opens on the old library after Setup changes it.**
  Running Search (or any tab) on the library as the box opened was
  remembered as "the folder you last worked in", and a remembered folder
  wins over Setup, so the old library came back even after a reload. Setup's
  own value is not remembered any more, and when a tree in Setup moves, the
  folders remembered inside the old one are forgotten with it. A folder
  remembered from somewhere else stays. One left over from before this
  release goes the first time you run that tab on the new library.
- **A tab you had already opened follows a new library.** Change the library
  in Setup and Search, Cull and every other tab with a library box opened on
  the new one only if you had not visited them yet; one you had came back
  with the old folder still in its box, so Search went on searching the old
  library. A box follows Setup whenever it still holds what Setup used to
  say. A folder you typed into a form yourself stays as you typed it, and
  the old result on that tab is cleared, because it was about the old folder.
- **A change made anywhere reaches the open page.** The sample library
  pointing Setup at itself (and handing your folders back), the command line
  or another browser changed the settings without this page knowing until a
  reload. The page now notices within a few seconds and follows, including
  the viewer keys and quick tags.
- **Photos shows the new library straight away.** The index waited up to a
  minute to notice the library had moved, and the old library's photographs
  stayed in Photos, Home, Places and the counts until the new one had been
  read all the way through. They leave the moment Setup is saved, and the new
  library is read at once. A pass still reading the old library is stopped.
- **No library means an empty index.** Clearing the library in Setup (or
  removing the sample library when you had none of your own) left the last
  library on show for good. A library that is set but not mounted this
  minute keeps its index, so a share that drops out is not read again from
  scratch.
- **Home's folder board and the camera and place menus keep up.** They were
  read once per visit and kept, so they went on listing what was there when
  the page opened. They are read again whenever the index changes.

## 3.11.0 - 2026-10-12

HEIC photographs, the format every iPhone saves in, are read like JPEGs.

### New

- **HEIC and HEIF files have a date, a camera and a place.** The capture
  time, timezone, camera, lens, exposure and GPS position are read from
  inside the file, so a phone's photographs sort by date, show on the map,
  pair with their brackets and count as dated and located on the dashboard.
  This needs nothing installed.
- **Thumbnails and previews of HEIC files.** Pillow opens them through
  pi-heif. The Windows program ships it beside Pillow in `windows/wheels/`
  and Install.bat installs it without the internet, also on a PC that
  already had Pillow. The NAS installs it into the config folder on its next
  start. Without it, HEIC files still have their dates and places; only the
  pictures are missing, as before.
- **The Checklist and `scripts/doctor.py` say whether the HEIC reader is
  there.**

### Changed

- **Geotag and Pin a location write a HEIC's position into a sidecar**,
  as they do for any file that is not a JPEG, instead of failing on it. A
  HEIC whose phone already recorded a position is left alone even with
  *Include already located* on, and says why.
- **Remove location names a HEIC that carries its own position** rather
  than skipping it silently, the way it already does for a RAW.
- Photographs already in the index or the read cache as HEIC are read again
  once, so the dates they were missing appear. Nothing else is re-read.

## 3.10.1 - 2026-10-12

A Windows install no longer nags about Synology jobs it does not have.

### Changed

- **No permissions banner on a PC.** The red "new folders waiting for the
  permissions job" line in Setup is gone on a Windows install: there is no
  permissions job, DSM or Synology Drive there to wait for. It still shows
  on the NAS.
- **No "Repair job" line in the Checklist on a PC**, and a folder it cannot
  write to no longer points at Permissions there. Both are unchanged on the
  NAS.
- **A missing folder on a PC is explained for a PC.** It says the folder is
  not there and to check the drive is connected, instead of talking about a
  container and its compose file.
- Permissions and Reindex still run by hand from the command line on a PC.

## 3.10.0 - 2026-10-12

The "not said" rows on the dashboard lead somewhere now.

### New

- **Press "not said" to list the photographs that do not say.** On Home and
  the Library tab, the "not said" row of Year, Camera, Lens, Focal length,
  Aperture, ISO and Shutter (and "no tags" and "no label") opens Search
  with those photographs, the same as pressing any other row. Before, those
  rows did nothing.
- **Search has a "Not said" box** (under *What it is*) that does the same
  by hand: type taken, camera, lens, focal, aperture, iso, shutter, colour
  or tags, or several separated by commas. Photos and albums have it as a
  filter too, and kept searches keep it. From the command line it is
  `--missing`.
- **Press "everything else" to open the chart out.** A folded tail is many
  values, so it now shows all the rows it held, each of which can be
  pressed. Before, it did nothing.

## 3.9.1 - 2026-10-12

Clean-up. Code nothing could reach is gone; every feature, option, setting
and command line works as before.

### Removed

- **The hidden 2.x screens.** The old phone home screen, its switch in the
  header, the side menu with its search box, and the code that drew the old
  bottom bar. The library shell has hidden all of them since 3.0, and the
  bar along the bottom of a phone was already drawn by the shell (Home,
  Photos, Places, Tools, More).
- **Unused code (audit N1-N4).** The `GET /api/overview` route, six page
  functions, the `i-heart` icon and nine Python functions that nothing
  called.

### Moved

- **What only the old side menu drew is in the rail now.** The features you
  opened lately (shown once there are three), *Tell me when a run finishes*
  at the foot of the rail, and *Install as an app* there too when the
  browser offers it. These were out of sight since 3.0.

### Kept

- **`GET /api/gate`.** The audit asked to fold it into `/api/client` once
  the client contract was checked for it. The contract could not be found,
  so it stays; `docs/DESIGN.md` says why.

## 3.9.0 - 2026-10-12

Easier to find your way. Nothing was removed: every feature, option, setting
and command line works as before. Some tools moved to a different tab row, and
two are left off the page on a PC (they still run from the command line).

### Easier to start

- **A fresh install opens on the Checklist.** With no library set yet, the app
  opens on the list of what is missing instead of an empty Home. Home and the
  foot of the rail offer **Open Setup** and **Build a sample library**.

### Easier to find

- **Tabs sit with the tools they belong to.** Cull by rating now heads the
  Review tools: Find blurry, Find duplicates, Check brackets, Thin brackets
  and Check exposure are its tabs. Space and Clean-up status moved under Clean
  up. Before, Cull by rating and those Review tools were tabs of Clean up, and
  Space and Clean-up status were tabs of the Library.
- **Search and Photos lead to each other.** The Photos filter panel has
  **Search a folder instead**, which opens Search with the same filters filled
  in. A search of folders inside the library has **Show in Photos**, which
  opens the grid with the same filters. Each screen says which one reads the
  library index (Photos) and which reads the folders themselves (Search).
- **Long forms start folded.** The 14 features with more than eight options
  (Sort into folders, Fix the clock, Geotag, Make previews, Cull by rating and
  others) open with their option groups folded and the folder in view. A
  group you have changed opens itself and says how many boxes in it are set.
  Setup and the colour labels stay open. What a run is asked to do is exactly the same as before.

### Clearer

- **Deleting a folder in the explorer goes through Delete folder.** It opens
  with the folder filled in, so you see the plan first, and the folder's RAW
  and preview copies go with it. Before, the explorer deleted only the folder
  itself and left its mirror folders behind. Deleting files is unchanged.
- **Buttons say what they do.** The header's Refresh is now **Reload page**.
  The two buttons that read the library again (on Home and at the foot of the
  rail) are now **Re-read library**. Three buttons with one name did two
  different things.
- **Reindex and Permissions are left out on a PC.** Both only mean something
  on a Synology NAS. On a PC, Setup says so in one line. The command line still
  runs them.
- **A lost password can be reset.** The sign-in page, the NAS guide and the
  Windows guide say how: remove `access.json` from the app's settings folder
  (`PM_DATA`), or set `PM_PASSWORD`, then restart the app.

## 3.8.0 - 2026-10-12

Safety and speed. Nothing was removed or renamed: every screen, option,
setting and command line works as before.

### Safer

- **Errors come back as a message, not "Could not reach the app".** A request
  the app cannot read (bigger than 8 MB, or not valid JSON) is refused with a
  sentence saying why. A fault inside the app answers with a one-line error,
  and the full details go to the log.
- **Refresh now works again.** The button at the foot of the rail started a
  library refresh that crashed before it began.
- **Two runs can no longer write to the same folders at once.** While one run
  is moving or rewriting photographs in a tree, pressing Apply on another
  run that writes to that tree is refused, with a sentence naming the
  run still going. A run started by Automation waits its turn instead. Runs
  that only look, and every preview, are not affected.
- **Files the index could not read are named.** The foot of the rail says how
  many there were ("1 file could not be read"), and the Checklist gains a
  Library index line naming the first few and why. Before, they were simply
  missing from Photos, Places and the counts.
- **Windows: rating, tagging and geotagging survive a file held open for a
  moment.** When Explorer, an antivirus scan or a backup tool has a photo
  open, the write is tried again for a few seconds before it gives up. When
  it does give up, the error names the file. Sidecar (.xmp) files are written
  differently and are not covered yet.
- **The photo-facts cache is shared, and written once per run.** Every
  feature now shares one copy of what is known about each photo. Two runs
  at once no longer write over each other's notes, and a flow of several
  steps writes the file once instead of once per step. A changed photo is
  still always read again.

### Faster

- **The page is about 70% smaller to download.** The page and the larger
  answers are sent compressed (701 KB becomes about 203 KB), which matters
  most on a phone over Wi-Fi. Photos, clips and downloads are sent as they
  are. Offline, the installed app still opens from its saved copy.
- **The page asks the NAS less often.** It checks for running jobs every 0.7 s
  only while something is running, every 2.5 s otherwise, and not at all in a
  tab you are not looking at (it catches up when you come back). The bar
  and badges are no longer redrawn when nothing has changed.
- **Scrolling a filtered grid is quicker.** A filter is worked out once and
  each page is cut from that result, instead of the whole library being
  filtered again for every page. Map pins are kept for each zoom level. The
  answers are exactly the same as before.
- **Thumbnails are made faster, and the newest ahead of time.** Up to four
  are made at once on a machine with the cores for it (it was always two).
  After the library finds new photos, the 300 newest get their thumbnails
  made in the background, so Photos opens on pictures instead of grey
  squares. Without Pillow, nothing changes.
