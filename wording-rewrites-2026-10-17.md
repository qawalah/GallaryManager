# Proposed wording, tool by tool

Source: every tool and option declared in `app/tasks/*.py` at a14e03c (50 tools, 389 options), rewritten to the style guide in section 10 of `AUDIT-2026-10-17.md`. Nothing here is applied to the code yet.

How to read this file:
- Tools and options appear in the same order as the dump.
- "keep" means the current label already follows the guide.
- An option repeated across tools (`skip_here`, `mirror`, `tidy`, `in_file`, the tree boxes, `sidecar_only`, `keep_originals`) is written in full the first time and then referred to as "same as <task>.<option>". Where the referring task needs a different word (tag instead of colour label, for example), the difference is stated.
- "(check: ...)" marks a place where the old help and the code disagree, or where the code should be confirmed before the text is applied.
- Labels are at most four whitespace-separated words, bracketed units included, because `tests/test_wording.py` counts them that way. "Shoot window (hours)" replaces every "Join a shoot within" for that reason.
- One name for one thing throughout: photo, RAW file, JPEG, preview, sidecar, video, folder, library, rating or stars, colour label, tag, Setup, tool, moved to _Culled, the tablet, run, Check the list, Apply.

Two facts from the code that the old help got wrong and this file describes as the code behaves:
- `mirror` (every task that has it): `registry.settle_trees` replaces each tree box with the Setup value when the flag is on, and uses the boxes as typed when it is off. The flag never decides whether RAW files or previews move. Several old bubbles say or imply that it does.
- `thin.probable`: `app/grouping.sets_for` finds bracket sets with the Setup settings, including Setup's `bracket_probable`. Thin's own flag then only drops sets marked probable from a list that already contains them. With Setup > Include hand-bracketed off, no probable set is ever found and the Thin brackets box has no effect.

---

## automation  (title: Automation)
summary:
- now: Run a flow: some features, in an order, each when the thing it watches changes.
- new: Runs a flow: a list of tools, in order, each when the folder it watches changes.

### which
- label now: Which flow  -> new: keep
- help now: Flows are built on the Flows tab - add a step, pick a feature, set its own settings. This chooses which one this tab is looking at and which one the button runs.
- help new: The flow this tab shows and the Run button runs. Flows are built on the Flows tab: add a step, pick a tool and set its options.

### apply_now
- label now: Run a waiting step  -> new: keep
- help now: The Apply button on a waiting row sets this. It runs that one step with writing allowed for this press only and does not change its 'and then' setting - so filing exports, which moves photographs into the library, goes back to reporting on the next pass.
- help new: Runs one waiting step with writing allowed, for this press only. The Apply button on a waiting row fills this in. The step's own 'and then' setting is not changed, so on the next pass the step reports again without writing.

## autoruns  (title: Automation runs)
summary:
- now: What the background loop has actually done, and what each pass took off the NAS.
- new: Lists each pass of the automation loop, what it did and what it cost. Nothing is changed.

### which
- label now: Which passes  -> new: keep
- help now: A pass that found nothing changed is the normal, correct state and there are a great many of them. Showing those by default would bury the handful that did something.
- help new: Which passes to list. Most passes find nothing changed, so by default only the passes that did something are shown.
- choices: `results`: Only the ones that did something -> Passes that did something; `all`: Every pass, including the quiet ones -> Every pass

### limit
- label now: How many  -> new: Passes to show
- help now: The most recent passes, newest first. A background loop does a great many of them, so this is a window rather than a history - the History button at the top has the whole log.
- help new: The number of most recent passes to list, newest first. 5 to 400, default 60. The History button at the top has the whole log.

## backup  (title: Backup)
summary:
- now: Back up the app's own state - settings, flows, and which photos are developed - and put a backup back.
- new: Backs up the app's settings, flows and developed list to a zip file, and restores one.

### what
- label now: What to do  -> new: keep
- help now: A backup is a zip in the config folder. Restoring backs up the current state first, so it can be undone.
- help new: Back up writes a zip file into the config folder. Restore puts one back. The current state is backed up first, so a restore can be undone.
- choices: `backup`: Back up now -> keep; `restore`: Restore from a backup -> Restore a backup

### source
- label now: Backup to restore  -> new: keep
- help now: Blank restores the newest. Browse to pick an older one, or one copied back onto the NAS.
- help new: The zip file to restore. Blank restores the newest backup. Browse to pick an older one, or one you copied back onto the NAS.

## bands  (title: Chart bands)
summary:
- now: Where the brackets fall on a chart - which apertures count as one bar, which ISOs, which focal lengths. Used by the dashboard, Search and Compare alike.
- new: Sets how apertures, ISOs and focal lengths are grouped into bars on every chart.

(no options)

## blur  (title: Find blurry)
summary:
- now: Measure how sharp each photo is, and tag the blurry ones or put them aside with their RAWs.
- new: Measures how sharp each photo is, then tags the blurry ones or moves them to _Culled.

### folder
- label now: Folder to check  -> new: keep
- help now: A shoot, or the whole library. JPEGs are measured; a RAW goes with its JPEG.
- help new: The folder to measure, a shoot or the whole library. Every JPEG in it is measured. A RAW file follows its JPEG when photos are moved to _Culled.

### do
- label now: Then  -> new: What to do
- help now: A tag is searchable in Lightroom and Synology Photos and moves nothing - the safe first run.
- help new: What happens to a blurry photo. A tag moves nothing and can be searched in Lightroom and Synology Photos, so start with it.
- choices: `tag`: Tag them 'blurry' - nothing moves -> Tag them (nothing moves); `aside`: Put them aside in _Culled, with their RAWs -> Move them to _Culled with their RAWs

### below
- label now: Sharpness under  -> new: Sharpness below
- help now: The number every frame is compared with. 0 turns this test off. The plan shows each frame's score - look at a few and adjust.
- help new: A photo with a sharpness score below this number counts as blurry. 0 to 5000, default 60. 0 turns this test off. Check the list shows each photo's score, so look at a few and adjust.

### of_shoot
- label now: Or % of shoot  -> new: Softer than folder (%)
- help now: Also catch a frame far softer than the rest of its own folder - so a dark night shoot is not flagged wholesale. 0 turns this off. Needs five frames in a folder.
- help new: Also counts a photo as blurry when its score is below this percentage of the typical score in its own folder, so a dark shoot is not flagged as a whole. 0 to 100, default 35. 0 turns this off. The folder needs at least five measured photos.

### word
- label now: Tag to write  -> new: keep
- help now: Used when tagging.
- help new: The tag written on each blurry photo when 'Tag them' is chosen. Default blurry.

### mirror
- label now: Mirror Setup's trees  -> new: Trees from Setup
- help now: When putting aside, the RAW and preview move too, found in Setup's trees.
- help new: On, the tree boxes below are ignored and the trees come from Setup, so files land where every other tool puts them. Off, the folders you type below are used for this run only. Turning this off does not stop RAW files or previews moving. (check: the code in registry.settle_trees only decides where the tree paths come from. The old help here and in bydate, cull, develop, thin and videos describes other effects that the flag does not have.)

### raw
- label now: The RAW tree  -> new: RAW tree
- help now: (none)
- help new: The top of the RAW tree. A blurry photo's RAW file is moved to the matching _Culled folder here. Blank leaves RAW files alone. Ignored while Trees from Setup is on.

### previews
- label now: The previews tree  -> new: Previews tree
- help now: (none)
- help new: The top of the previews tree. A blurry photo's preview is moved to the matching _Culled folder here. Blank leaves previews alone. Ignored while Trees from Setup is on.

### in_file
- label now: Write into the photo  -> new: keep
- help now: For the tag: inside the JPEG as well as its sidecar.
- help new: Writes the tag into the JPEG itself as well as into its sidecar. Lightroom and darktable read the sidecar. Synology Photos and Windows Explorer read the JPEG, so leave this on unless you have a reason not to.

### skip_here
- label now: Skip these folders  -> new: keep
- help now: Left out of this run only, as well as everything Setup skips everywhere. The plan says what was left out.
- help new: Folders left out of this run only. The folders in Setup > Skip everywhere are always left out as well. Check the list says what was left out.

## brackets  (title: Find brackets)
summary:
- now: Show how the bracket settings group a folder, and mark the sets with a tag so they are one search away.
- new: Shows how the bracket settings group a folder into sets, and can tag every frame of each set.

### folder
- label now: Folder to look through  -> new: Folder to check
- help now: (none)
- help new: The folder to group into bracket sets, a shoot or the whole library. How a set is found is set in Setup > Brackets.

### tag
- label now: Tag to write  -> new: keep
- help now: Leave BLANK and this task only reports, as it always has. Type a word - 'bracket' - and every frame of every set found is given it, in a sidecar and inside the JPEG. Nothing already on the file is replaced. The same word on the Make previews tab puts it on the preview that stands for the set.
- help new: The tag written on every frame of every set found, in the sidecar and inside the JPEG. Blank means the tool only reports and writes nothing. Tags already on a file are kept. Use the same word as Setup > Bracket tag, which Make previews writes on the preview of a set.

### raw
- label now: The RAW tree  -> new: RAW tree
- help now: So the negatives are marked too. Each is found by capture time, camera and name, wherever in the tree it sits. Only used when there is a tag to write.
- help new: The top of the RAW tree, so each frame's RAW file gets the tag too. A RAW file is matched by capture time, camera and name, wherever it sits in the tree. Only used when a tag is given.

### skip_here
- same as blur.skip_here

## bydate  (title: Sort into folders)
summary:
- now: Break a folder up by date or by place - year, month, week, day, or country and city - whatever shape it is in now.
- new: Moves photos into folders by date or place: year, month, week, day, country or city.

### folder
- label now: The folders to sort  -> new: Folders to sort
- help now: Everything underneath each of them is read, however it is arranged now - the sub-folders you already have are walked through, not kept. Add several and they are sorted together, into the folder they all sit in: three shoots from one trip become one set of date or place folders rather than three.
- help new: The folders to sort. Everything inside each one is read, whatever sub-folders it has now. Those sub-folders are walked through, not kept. Several folders are sorted together into the folder that holds them all.

### into
- label now: Build them in  -> new: Destination folder
- help now: Blank builds the new folders inside the folder being sorted. Pick another folder in the library to file INTO it instead - a card dump sorted straight into Photos/2024. The plan shows the folders it will make before anything moves.
- help new: Where the new folders are built. Blank builds them inside the folder being sorted. Pick another folder in the library to file into it instead, for example Photos/2024. Check the list shows the folders before anything moves.

### shape
- label now: Folders to make  -> new: Folder pattern
- help now: A few ready-made, the patterns you kept, or your own. Place patterns need the photos to carry a location and the place table imported - see the Place names tab.
- help new: The shape of the folders to make: a ready-made pattern, one you kept, or your own. Place patterns need photos with a location and the place table from the Import place names tab.

### pattern
- label now: The pattern itself  -> new: Pattern
- help now: Variables in braces, / for a folder inside a folder. Any text of your own around them is kept: {year}/{month} {monthname} - {city}. A missing value is left out, never guessed.
- help new: The folder pattern as text. Variables go in braces and / starts a folder inside a folder, for example {year}/{month} {monthname} - {city}. Your own text around them is kept. A missing value is left out, never guessed.

### hijri_shift
- label now: Hijri day shift  -> new: Hijri shift (days)
- help now: Days to move the Hijri calendar by, for a country whose months begin a day either side of the table. Only used by the {hijri} variables.
- help new: Moves the Hijri calendar by this many days, for a country whose months start a day earlier or later than the table. -3 to 3, default 0. Only used by the {hijri} variables.

### range_gap_hours
- label now: New shoot after  -> new: New range after (hours)
- help now: Hours without a photo. Only used by {range}: a trip is one range however many days it ran, and a quiet day starts the next one.
- help new: Hours without a photo that end one range and start the next. 1 to 336, default 24. Only used by the {range} variable: a trip is one range however many days it lasts.

### week_starts
- label now: Weeks start on  -> new: keep
- help now: Only used by the week shape. The folder is named by the date the week began, so whichever you choose is written in the name rather than assumed.
- help new: The first day of the week, for the week pattern. The folder is named after the date the week began, so the day you choose shows in the name.

### city_within_km
- label now: Name the town within  -> new: Town within (km)
- help now: Kilometres. Beyond this the nearest town is not claimed as where the photograph was taken, and it goes into _Unsure under its country instead. The table names towns over 15,000 people, so in a city the nearest is a kilometre away and on a mountain it is forty.
- help new: The largest distance, in kilometres, between a photo and a town for that town to be used as the folder name. 1 to 500, default 30. Further away, the photo goes into _Unsure under its country. The table lists towns over 15,000 people.

### town_at_least
- label now: Smallest town to name  -> new: Smallest town (people)
- help now: People. 0 names the nearest town whatever its size - honest, and it turns a week in Tuscany into eleven hamlets. 50,000 or 100,000 sticks to the places you would name yourself. When nothing that big is near, the row says so and the country is used on its own rather than a village being picked anyway.
- help new: Towns with fewer people than this are not used as folder names. 0 to 5,000,000, default 0, which uses the nearest town whatever its size and can give one folder per village. 50,000 or more keeps to well-known places. When no town that large is near, only the country is used.

### place_names
- label now: Rename places  -> new: keep
- help now: One per line: 'Marrakesh = Marrakech'. Matches a town or a country. The result lists every name it found, so the usual way to fill this in is to look once and edit it there.
- help new: Names to change before they are used as folder names, one per line: Marrakesh = Marrakech. A line matches a town or a country. The result lists every name found, so run once and edit the list from there. From Setup by default.

### country_within_km
- label now: Name the country within  -> new: Country within (km)
- help now: Kilometres. Past this, nothing is claimed at all and the photograph is left exactly where it is - at sea or deep in a desert, the nearest name we happen to know is not evidence of anything.
- help new: The largest distance, in kilometres, between a photo and the nearest known place for the country to be used. 1 to 2000, default 200. Further away, for example at sea, the photo is left where it is.

### move_video
- label now: Move video too  -> new: Move videos too
- help now: A clip has no rating, no bracket and usually no location, so the only honest way to file it with its shoot is the moment it was shot. It goes where the photographs taken at that moment are going; failing that, on its own date; failing that it is left exactly where it is and named.
- help new: Moves videos with the photos. A video goes where the photos taken at the same time go. With no photos near its time it is sorted by its own date, and with no date it stays where it is and is listed. On by default.

### near_hours
- label now: Join a shoot within  -> new: Shoot window (hours)
- help now: Hours. A shoot that ended at ten and a clip at half past eleven are the same evening; one from the next afternoon is not. Inside a shoot's own hours always counts.
- help new: How many hours after a shoot ended a video still belongs to it. 0 to 240, default 12. A video taken during the shoot always belongs to it.

### shift_minutes
- label now: Shift clip times by  -> new: Shift video times (minutes)
- help now: Minutes. Only for cameras that write the movie header in UTC while the photographs are local. Left at 0 the file is taken at its word and the row says when it stated no timezone.
- help new: Minutes added to each video's recorded time before it is matched to photos. -1440 to 1440, default 0. Only needed when the camera writes video times in UTC and photo times in local time: +180 lines up a UTC+3 video. At 0 the time is used as written, and the row says when the file gave no time zone.

### mirror
- label now: Mirror Setup's trees  -> new: Trees from Setup
- help now: The negative and the preview of a photograph move to the matching new place, so the trees stay in step. Without them the pairs still hold - they are found by identity - but Re-mirror has to be run afterwards to tidy the positions.
- help new: same as blur.mirror (check: the old help says the trees stay in step only with this on. RAW files and previews move whenever their tree box is filled, whatever this flag says.)

### raw
- label now: The RAW tree  -> new: RAW tree
- help now: Each negative is found by capture time, camera and name - wherever in this tree it currently sits.
- help new: The top of the RAW tree. Each photo's RAW file is moved to the matching new folder here. A RAW file is matched by capture time, camera and name, wherever it sits in the tree. Blank leaves RAW files alone.

### previews
- label now: The previews tree  -> new: Previews tree
- help now: Previews are found by position, since that is how they were made. Leave blank to leave them alone and remake them later.
- help new: The top of the previews tree. Each photo's preview is moved to the matching new folder here. Previews are matched by position. Blank leaves previews alone, and you can remake them later.

### skip_here
- same as blur.skip_here

## cameras  (title: Camera names)
summary:
- now: What each camera is called, against the code it writes into the file. Phones write order codes; this is where they get names.
- new: Gives each camera a name to show instead of the model code it writes into files.

### folders
- label now: Where to look  -> new: Folders to read
- help now: Which folders to take the list of cameras from.
- help new: The folders to read camera codes from. Blank means the library from Setup.

### skip_here
- same as blur.skip_here

## checklist  (title: Checklist)
summary:
- now: Is everything set up? Each line measured, with where to fix it.
- new: Checks that every part of the setup works, and says where to fix each problem.

### try_writing
- label now: Try writing  -> new: keep
- help now: Makes a folder and removes it again - the only real proof.
- help new: Makes a folder in each tree and removes it again, to prove the app can write there. Off only checks that the folders exist. On by default.

## cleanup  (title: Clean up)
summary:
- now: Empty the piles - _Culled, _Duplicates, _NoLocation - once you no longer want them. The only thing here that really deletes.
- new: Deletes the _Culled, _Duplicates and _NoLocation piles. The only tool that really deletes.

### folder
- label now: Folder to clean  -> new: Folders to clean
- help now: The tree to look through. The piles can be anywhere inside it - a _Culled folder sits beside the shoot it came from, not in one place.
- help new: The folders to look through. Piles can be anywhere inside them: a _Culled folder sits beside the shoot it came from.

### culled
- label now: Culled photographs (_Culled)  -> new: Culled photos (_Culled)
- help now: What Cull by rating and Thin brackets put aside. Everything in one is something you decided against - the question is only whether you still want the choice back.
- help new: Deletes the _Culled folders made by Cull by rating, Thin brackets and Find blurry. Everything in them is a photo you decided against. On by default.

### duplicates
- label now: Duplicate copies (_Duplicates)  -> new: keep
- help now: Copies moved aside by Find duplicates. One of each set was left exactly where it was, which is what makes this safe to empty.
- help new: Deletes the _Duplicates folders made by Find duplicates. One copy of each set was left in place, so these are spare copies. On by default.

### nolocation
- label now: Pre-geotag originals  -> new: Originals (_NoLocation)
- help now: Originals kept before a location was written into them. Off by default: these are untouched originals, and the only reason they exist is in case the geotag was wrong.
- help new: Deletes the _NoLocation folders that Geotag and Pin a place by hand make when Keep originals is on. Off by default: these are untouched originals, kept in case a location was wrong.

### leftovers
- label now: Thumbnail-only folders  -> new: keep
- help now: @eaDir, Thumbs.db, .DS_Store and the like, and only where there is nothing else in the folder at all. A folder with one photograph and an @eaDir is not litter.
- help new: Deletes folders that hold only system files such as @eaDir, Thumbs.db or .DS_Store and nothing else. A folder with one photo and an @eaDir is left alone. Off by default.

### empty
- label now: Empty folders  -> new: keep
- help now: What reorganising a library leaves behind. Deepest first, so a year folder whose shoots have all moved out goes too. On by default because every other task here already tidies away the folders IT empties - this is the same thing for the ones left by everything you did before.
- help new: Deletes folders with nothing in them, deepest first, so a year folder whose shoots have all moved goes too. On by default.

### older_than
- label now: Untouched for (days)  -> new: keep
- help now: The pile anybody regrets emptying is this morning's, from the cull that was wrong before you had noticed. 30 is a sensible number; 0 means everything, however recent.
- help new: Only piles that have not changed for this many days are deleted. 0 to 3650, default 0, which deletes every pile however recent. 30 is a safe choice, so this morning's cull is still there if it was wrong.

### recycle
- label now: Use the recycle bin  -> new: keep
- help now: Each share has a #recycle folder when the recycle bin is turned on for it, and moving there is a rename you can undo from File Station. If there is no #recycle folder this refuses rather than quietly deleting instead.
- help new: Moves files into the share's #recycle folder instead of deleting them, so File Station can bring them back. If the share has no #recycle folder the tool refuses rather than deleting. On by default.

### confirm
- label now: Yes, remove them  -> new: Confirm deletion
- help now: Until this is ticked the tab is a report and there is no Go ahead button. Everything else in this app puts things aside and can be undone with a move; this cannot, so it asks in two places.
- help new: Until this is ticked the tool only reports and there is no Apply button. Every other tool moves files and can be undone. Deleting cannot, so it asks twice.

### raw
- label now: Also the RAW tree  -> new: RAW tree
- help now: Culled negatives and duplicate RAWs pile up here too, and they are the big ones.
- help new: The top of the RAW tree, so its piles are cleaned too. Culled and duplicate RAW files are the largest. Blank leaves it alone.

### previews
- label now: Also the previews tree  -> new: Previews tree
- help now: (none)
- help new: The top of the previews tree, so its piles are cleaned too. Blank leaves it alone.

### develop
- label now: Also the develop tree  -> new: Develop tree
- help now: (none)
- help new: The top of the develop tree, so its piles are cleaned too. Blank leaves it alone.

### skip_here
- same as blur.skip_here

## compare  (title: Compare)
summary:
- now: Two things about the library at once - aperture against lens, stars against year - as a grid. Nothing is written.
- new: Draws a grid of one fact against another, such as aperture by lens. Nothing is changed.

### folders
- label now: Where to look  -> new: Folders to read
- help now: One folder per line, everything below each.
- help new: The folders to read, one per line. Everything inside each one is counted. Blank means the library from Setup.

### down
- label now: Down the side  -> new: Rows
- help now: The rows of the grid.
- help new: The fact that makes the rows of the grid.

### across
- label now: Across the top  -> new: Columns
- help now: The columns.
- help new: The fact that makes the columns of the grid.

### focal35
- label now: Focal length full-frame  -> new: Full-frame focal length
- help now: 25mm on the GH4 frames like 50mm. Only matters when one of the two is focal length.
- help new: Uses the full-frame equivalent focal length, so 25mm on a GH4 counts as 50mm. Only matters when rows or columns are focal length. A photo that does not record the equivalent is left out.

### skip_here
- same as blur.skip_here

## cull  (title: Cull by rating)
summary:
- now: Put low-rated photos aside - the JPEG, its RAW, their sidecars, its preview.
- new: Moves low-rated photos, with their RAW files, sidecars and previews, into a _Culled folder.

### folder
- label now: Folder to cull  -> new: keep
- help now: A single shoot, or the whole library. Ratings are read from here.
- help new: The folder to read ratings from, a shoot or the whole library.

### jpeg_at_or_below
- label now: JPEG at or below  -> new: keep
- help now: -1 means never cull a JPEG.
- help new: A JPEG rated this many stars or fewer is moved to _Culled. -1 to 5, default -1, which never moves a JPEG. An unrated photo is never moved.

### raw_at_or_below
- label now: RAW at or below  -> new: keep
- help now: -1 means never cull a RAW. The usual want is to keep every JPEG and only the RAWs of shots you liked. An unrated photo is never culled at any threshold - zero means not looked at yet.
- help new: A RAW file whose photo is rated this many stars or fewer is moved to _Culled. -1 to 5, default 2. -1 never moves a RAW file. The usual choice keeps every JPEG and only the RAW files of photos you liked. An unrated photo is never moved.

### mirror
- label now: Mirror Setup's trees  -> new: Trees from Setup
- help now: On, the RAW and previews trees come from Setup and the position inside them is worked out from the library - so a shoot always lands where unpairing the whole library would have put it, and there is nothing to type or get wrong. Turn it off only to send this one run somewhere else.
- help new: same as blur.mirror

### raw
- label now: The RAW tree  -> new: RAW tree
- help now: RAWs are found by capture time, camera and name - wherever in this tree they now sit. Leave blank to leave RAWs alone.
- help new: The top of the RAW tree. RAW files are matched by capture time, camera and name, wherever they sit in the tree. Blank leaves RAW files alone.

### previews
- label now: The previews tree  -> new: Previews tree
- help now: Leave blank to leave previews alone.
- help new: The top of the previews tree. Each moved photo's preview is moved to the matching _Culled folder here. Blank leaves previews alone.

### brackets
- label now: Keep brackets together  -> new: keep
- help now: An unrated frame takes its set's rating. Without this you cull the frame you judged and keep the two you did not. How a set is worked out is set once, in Setup.
- help new: Treats a bracket set as one photo: an unrated frame takes the rating of its set, so the whole set is kept or moved together. How a set is found is set in Setup > Brackets. From Setup by default.

### tidy
- label now: Tidy empty folders  -> new: keep
- help now: A folder this run empties is removed. Only ones it emptied itself, and never one holding anything at all.
- help new: Removes a folder that this run has emptied. Only folders this run emptied itself are removed, never a folder that still holds anything. On by default.

### skip_here
- same as blur.skip_here

## delfolder  (title: Delete folder)
summary:
- now: Delete folders - with their RAWs, previews and video - into the share's Recycle Bin.
- new: Deletes whole folders, with their RAW files, previews and videos, into the share's recycle bin.

### folder
- label now: Folders  -> new: Folders to delete
- help now: Everything inside goes too.
- help new: The folders to delete. Everything inside each one goes too.

### with_raw
- label now: Their RAWs  -> new: Delete their RAW files
- help now: The same folder in the RAW tree - only that folder.
- help new: Also deletes the matching folder in the RAW tree, and only that folder. On by default.

### with_previews
- label now: Their previews  -> new: Delete their previews
- help now: The same folder in the previews tree, so the tablet loses it.
- help new: Also deletes the matching folder in the previews tree, so the tablet loses it on the next sync. On by default.

### with_video
- label now: Their video  -> new: Delete their videos
- help now: The same folder in the video tree.
- help new: Also deletes the matching folder in the video tree. On by default.

## demo  (title: Sample library)
summary:
- now: Builds a small library with real EXIF, RAWs, duplicates, a bracketed set and a wrong clock - somewhere to try every feature without touching your photographs.
- new: Builds a small sample library to try every tool on, without touching your own photos.

### folder
- label now: Build it in  -> new: Sample folder
- help now: A folder of your own, not inside your library - it does not have to exist yet. Everything the sample needs is made underneath it, and Remove deletes that folder and nothing else.
- help new: A folder of your own, outside the library. It does not need to exist yet. Everything the sample needs is made inside it, and Remove deletes only this folder.

### doing
- label now: Build or remove  -> new: keep
- help now: Remove only ever deletes a folder this app built - it leaves a marker file when it builds one and checks for it first. Pointed anywhere else it does nothing.
- help new: Build makes the sample. Remove deletes a sample this app built. It checks for the marker file the build left, and does nothing in any other folder.
- choices: `build`: Build the sample -> keep; `remove`: Remove it again -> Remove the sample

### point
- label now: Point Setup at it  -> new: keep
- help now: Writes the sample's folders into Setup so every feature opens on it. Where your own folders are now is written down first and put back when you remove the sample.
- help new: Writes the sample's folders into Setup, so every tool opens on the sample. Your own folders are saved first and put back when you remove the sample.

### skip_here
- same as blur.skip_here

## develop  (title: Send to develop)
summary:
- now: Copy the shots worth developing to a tree of their own, and take back the ones you have finished.
- new: Copies the photos worth developing into the develop tree, and removes the copies you have finished.

### folder
- label now: The library  -> new: Library
- help now: Read only. Nothing here is ever moved or changed.
- help new: The library to read ratings, colour labels and tags from. Nothing here is moved or changed.

### raw_at_or_above
- label now: Send RAW at  -> new: Send RAW from (stars)
- help now: -1 never sends a RAW. A negative is fifty megabytes, so this is usually the top rating only.
- help new: A RAW file is sent when its photo has this many stars or more. -1 to 5, default 5. -1 never sends a RAW file. RAW files are large, so this is usually the top rating only. From Setup by default.

### jpeg_at_or_above
- label now: Send JPEG at  -> new: Send JPEG from (stars)
- help now: -1 never sends a JPEG. Lower than the RAW threshold gives you the shots worth a look without the weight of the negatives.
- help new: A JPEG is sent when it has this many stars or more. -1 to 5, default 4. -1 never sends a JPEG. Set it lower than the RAW threshold to get the photos worth a look without the large RAW files. From Setup by default.

### prune
- label now: Take finished back  -> new: Remove finished copies
- help now: This is what makes the folder temporary: it holds what is still waiting, not everything that ever qualified. Removing only ever happens inside the develop tree, and every file there is a copy the library still has.
- help new: Removes a copy from the develop tree once its photo is developed or no longer qualifies, so the tree holds only what is still waiting. Only files inside the develop tree are removed, and every one is a copy the library still has. On by default. From Setup by default.

### colour
- label now: Only this colour  -> new: keep
- help now: Picked rather than typed, because a colour has a NAME you set once and a tag you would otherwise have to spell the same way every time. Choosing one narrows the whole run to it: 'send me the sharpening pile' is a different question from 'send me the good photographs'.
- help new: Sends only photos carrying this colour label. Blank means any colour. The meaning of each colour is set in Setup > Colour meanings. From Setup by default.

### spot_done
- label now: Spot finished edits  -> new: keep
- help now: A photo whose edit is already sitting in its shoot's Developed folder is counted as done - recorded, and taken off the tablet - even if File developed never filed it. The edit might have come from Lightroom on the PC, or been put there by hand.
- help new: Counts a photo as developed when its edit is already in the shoot's Developed folder, even if File developed did not put it there. The photo is recorded as done and its copy is removed from the develop tree. On by default.

### labels
- label now: Obey colours too  -> new: Follow colour labels
- help now: A colour says what you want DONE with a photograph, which a rating cannot: sharpen this, print that, these six hundred are a timelapse. Each colour's meaning and destination is set in Setup > Colour meanings, and a colour beats a rating over which folder something lands in.
- help new: Lets a colour label decide which photos are sent and to which folder, as set in Setup > Colour meanings. A colour label beats a rating over which folder a photo lands in. Off, only ratings and tags decide. On by default. From Setup by default.

### tags
- label now: Tags  -> new: Only photos tagged
- help now: Comma separated. Read from a .xmp sidecar, from the XMP inside a JPEG, from Windows Explorer's own Tags box and from IPTC - all four, because a photo tagged in one of them is not untagged. A level of a hierarchy matches: Italy finds Travel|Italy|Rome. Leave blank for no tag filter at all.
- help new: Sends only photos carrying one of these tags, separated by commas. Tags are read from the sidecar, from the JPEG, from Windows Explorer's Tags box and from IPTC. A level of a hierarchy matches: Italy finds Travel|Italy|Rome. Blank means no tag filter. From Setup by default.

### tags_rule
- label now: What the tags do  -> new: keep
- help now: Narrowing sends your four-star Italy photos and nothing else. Widening sends everything that already qualified PLUS anything carrying the tag - the JPEG only, since a negative is fifty megabytes and a tag is not a rating.
- help new: How the tags combine with the ratings. Narrow sends only photos that qualify by rating and also carry a tag. Widen sends everything that qualifies by rating, plus every tagged photo whatever its rating, as a JPEG only. From Setup by default.
- choices: `only`: Narrow it: send only photos carrying them -> Narrow: only photos with the tags; `also`: Widen it: send them whatever the rating -> Widen: tagged photos too, any rating

### tags_all
- label now: Must have all tags  -> new: keep
- help now: Off, a photo tagged Italy OR portfolio counts. On, it has to carry both.
- help new: A photo must carry every tag listed. Off, carrying any one of them is enough. From Setup by default.

### mirror
- label now: Mirror Setup's trees  -> new: Trees from Setup
- help now: The develop tree keeps the library's shape, so a shoot arrives on the tablet in the folder it belongs to rather than in one flat heap of five-star photographs.
- help new: same as blur.mirror (check: the old help says this keeps the library's shape. The develop tree keeps that shape whatever this flag says.)

### develop
- label now: The develop tree  -> new: Develop tree
- help now: Sync THIS folder to the tablet - with Syncthing, or Synology Drive's offline folders. Made if it is not there yet.
- help new: The top of the develop tree. Sync this folder to the tablet, with Syncthing or Synology Drive. It is made if it does not exist yet.

### raw
- label now: The RAW tree  -> new: RAW tree
- help now: Where the negatives live. Leave blank to send JPEGs only.
- help new: The top of the RAW tree, where RAW files are copied from. Blank sends JPEGs only.

### brackets
- label now: Keep a bracket together  -> new: Keep brackets together
- help now: An unrated frame takes its set's rating, so you get the whole bracket to blend rather than the one frame you happened to star.
- help new: Treats a bracket set as one photo: an unrated frame takes the rating of its set, so the whole set is sent together for blending. How a set is found is set in Setup > Brackets. From Setup by default.

### skip_here
- same as blur.skip_here

## duplicates  (title: Find duplicates)
summary:
- now: The same photo twice - identical files for certain, re-saved ones if you ask.
- new: Finds the same photo stored twice and moves the spare copies into a _Duplicates folder.

### folder
- label now: Folder to check  -> new: keep
- help now: One tree at a time. Point it at the library, or at the RAW tree, but never at something containing both - a RAW shares its JPEG's capture time, camera and name, because that is how they are paired, so together they would all read as duplicates.
- help new: One tree at a time: the library or the RAW tree. Never a folder that holds both, because a RAW file shares its JPEG's capture time, camera and name, so the pair would count as duplicates.

### keep
- label now: Which copy to keep  -> new: keep
- help now: The Windows app asked this and the answer is not obvious: a library is filed several ways at once - a shoot near the top, a card dump six levels down, an export folder full of re-saves dated today. 'Whichever looks most like the original' prefers a name without a copy marker, then the oldest file, then the shortest path.
- help new: The rule that decides which copy stays in place. 'The one most like the original' prefers a name without a copy marker, then the oldest file, then the shortest path.
- choices: `smart`: Whichever looks most like the original -> The one most like the original; `shallowest`: Keep the one closest to the top of the tree -> The one nearest the top; `deepest`: Keep the one deepest in the tree -> The one deepest in the tree; `oldest`: Keep the oldest file -> The oldest file; `newest`: Keep the newest file -> The newest file; `alpha`: Keep the first path alphabetically -> The first path alphabetically; `priority`: Keep whichever sits in a folder you listed -> The one in a listed folder

### prefer
- label now: Folders that win  -> new: keep
- help now: In order. A file in the first of these beats a file in the second, and both beat a file in none of them, whatever the rule above says. This is the A-versus-B choice: every heading in the results offers both of its folders, and picking one puts it here.
- help new: Folders whose copy is kept, in order. A file in the first folder beats a file in the second, and both beat a file in neither, whatever the rule above says. In the results, each heading offers its two folders, and picking one adds it here.

### resaved
- label now: Include re-saved copies  -> new: keep
- help now: Identical bytes is a fact. This is a judgement: same capture time, same camera, same name, different file - a photo copied and then re-saved by something. It is listed either way; this decides whether anything is moved. Read the list first.
- help new: Also moves copies that are not identical files but have the same capture time, camera and name, such as a photo re-saved by another program. These are always listed. This decides whether they are moved, so read the list first. Off by default.

### raw
- label now: The RAW tree  -> new: RAW tree
- help now: Only used to leave it out, if it happens to sit inside the folder being scanned.
- help new: The top of the RAW tree. Only used to leave it out when it sits inside the folder being checked.

### previews
- label now: The previews tree  -> new: Previews tree
- help now: Only used to leave it out, if it happens to sit inside the folder being scanned.
- help new: The top of the previews tree. Only used to leave it out when it sits inside the folder being checked.

### develop
- label now: The develop tree  -> new: Develop tree
- help now: Also only used to leave it out. Everything in it is a copy of something in the library on purpose - that is what it is for - so every one of them would be reported as a duplicate.
- help new: The top of the develop tree. Only used to leave it out. Everything in it is a copy of a library photo on purpose, so every file there would count as a duplicate.

### tidy
- same as cull.tidy

### skip_here
- same as blur.skip_here

## exposure  (title: Check exposure)
summary:
- now: Measure how much of each frame is at the very top or the very bottom of the range, and tag the ones that cross a threshold you can see and change.
- new: Measures how much of each photo is pure white or pure black, and tags the ones over a limit you set.

### folder
- label now: The folder to check  -> new: Folder to check
- help now: Everything underneath it is read. Measured from the thumbnail, which is already made - so a second pass over the same folder costs almost nothing.
- help new: The folder to measure, a shoot or the whole library. Each photo is measured from its thumbnail, which already exists, so a second run over the same folder is fast.

### find_over
- label now: Find over exposed  -> new: Find over-exposed
- help now: (none)
- help new: Looks for photos with too much pure white. Off skips this end. On by default.

### find_under
- label now: Find under exposed  -> new: Find under-exposed
- help now: (none)
- help new: Looks for photos with too much pure black. Off skips this end. On by default.

### over_pct
- label now: Over at this %  -> new: Over-exposed from (%)
- help now: How much of the frame has to be at the very top of the range before it counts as blown. 5% is a lot of white sky; 1% is strict.
- help new: A photo is over-exposed when at least this share of it is pure white. 0.1 to 100, default 5. 5% is a lot of white sky, and 1% is strict.

### under_pct
- label now: Under at this %  -> new: Under-exposed from (%)
- help now: How much of the frame has to be at the very bottom before it counts as too dark. A night shot is legitimately half black, which is why this starts high.
- help new: A photo is under-exposed when at least this share of it is pure black. 0.1 to 100, default 40. The default is high because a night photo is often half black.

### write_tags
- label now: Write the tags  -> new: keep
- help now: Off, this only reports - which is the right way to run it the first time, while you are finding the thresholds that suit your own photographs.
- help new: Writes the tags below on the photos found. Off only reports, which is the right way to run it the first time while you find the limits that suit your photos. On by default.

### tag_over
- label now: Tag for over exposed  -> new: Over-exposed tag
- help now: Written into the photograph and its sidecar, so Search here and Lightroom can both find them. Leave blank to report without writing anything.
- help new: The tag written on an over-exposed photo and its sidecar, so Search and Lightroom can find it. Default overexposed. Blank reports without writing.

### tag_under
- label now: Tag for under exposed  -> new: Under-exposed tag
- help now: The same, for the dark end. Leave blank to only report.
- help new: The tag written on an under-exposed photo and its sidecar, so Search and Lightroom can find it. Default underexposed. Blank reports without writing.

### skip_here
- label now: Folders to skip  -> new: Skip these folders
- help now: Anything under these is not read.
- help new: same as blur.skip_here (check: the old help does not mention Setup > Skip everywhere. Confirm this tool also honours it before using the shared text.)

## filed  (title: File developed)
summary:
- now: Match Lightroom's exports to their originals and file them - and record them as developed.
- new: Matches Lightroom's exports to their originals, files them into the library and records them as developed.

### inbox
- label now: Lightroom's export folder  -> new: keep
- help now: The one folder Lightroom on the tablet writes to, synced back to the NAS. Keep it OUTSIDE the library, or every export is read as an original photograph.
- help new: The folder Lightroom on the tablet exports into, synced back to the NAS. Keep it outside the library, or every export is read as an original photo. From Setup by default.

### folder
- label now: The library  -> new: Library
- help now: Where the originals are looked for, by capture time, camera and name - anywhere in it, whatever you have renamed.
- help new: Where the originals are looked for, by capture time, camera and name, wherever they sit and whatever they were renamed.

### where
- label now: Where each export goes  -> new: Export destination
- help now: A subfolder keeps the shoot folder made of camera files only. An export has its original's name, time and camera, so beside it the rest of this app counts it as a second photograph.
- help new: Where an export is filed once its original is found. A subfolder keeps the shoot folder for camera files only. Beside the original, the rest of the app counts the export as a second photo with the same name, time and camera. From Setup by default.
- choices: `subfolder`: In a subfolder of the shoot, named below -> A subfolder of the shoot; `beside`: Straight in beside the original -> Beside the original

### subfolder
- label now: Called  -> new: Subfolder name
- help now: Only used for the subfolder choice, and it is a name rather than a path - it is joined onto whichever shoot each export belongs to. Whatever you call it - Developed, Curated - is added to the folders this app leaves out of its own scanning, so exports are never read as originals. Set it in Setup and the background automation uses the same one.
- help new: The name of the subfolder, default Developed. A name, not a path: it is made inside whichever shoot each export belongs to. The name is also added to the folders the app never scans, so exports are not read as originals. From Setup by default, and automation uses the same one.

### tidy_resync
- label now: Clear re-synced copies  -> new: keep
- help now: The export folder is a one-way sync: the tablet keeps its copy and can send it back after this has filed it. On, such a copy is removed from the EXPORT folder - never from the library, and never the one already filed. Off, it is listed and left, and the export folder slowly fills with photographs you have already dealt with.
- help new: Removes an export from the export folder when the same file was already filed, because the tablet can sync its copy back again. Only the export folder is touched, never the library. Off, such copies are listed and left, and the export folder slowly fills. On by default. From Setup by default.

### keep_exports
- label now: Keep the export  -> new: keep
- help now: Off means the export is moved, which empties the folder ready for the next round. On copies instead, and the folder keeps filling.
- help new: Copies each export into the library instead of moving it. Off by default: the export is moved and the export folder empties for the next round. From Setup by default.

### skip_here
- same as blur.skip_here

## files  (title: File explorer)
summary:
- now: A file manager for the trees: copy, move, rename and delete, with RAWs and previews following what you move.
- new: Copies, moves, renames and deletes files and folders, with RAW files and previews following.

### folder
- label now: Folder to open  -> new: keep
- help now: Where the manager starts. The places bar jumps to the other trees.
- help new: The folder the explorer opens on. The places bar jumps to the other trees.

### with_raw
- label now: RAWs follow  -> new: RAW files follow
- help now: Moving or deleting a photo in the library does the same to the same name in the RAW tree, at the matching place.
- help new: Moving or deleting a photo in the library does the same to its RAW file at the matching place in the RAW tree. On by default.

### with_previews
- label now: Previews follow  -> new: keep
- help now: The same for the previews tree, so the tablet copy does not get left behind.
- help new: Moving or deleting a photo in the library does the same to its preview at the matching place in the previews tree. On by default.

### skip_here
- same as blur.skip_here

## flows  (title: Flows)
summary:
- now: Build a flow: add a step, pick a feature, give it its own settings, and put them in the order the work happens.
- new: Builds a flow: add steps, pick a tool for each, set its options and put them in order.

(no options)

## forget  (title: Clear the history)
summary:
- now: Remove lines from the log of what has been done. Nothing on disk changes; what goes is the record, and the ability to put those runs back.
- new: Removes runs from the history log. Nothing on disk changes, but those runs can no longer be put back.

### which
- label now: What to forget  -> new: keep
- help now: Everything, or only what is older than a given age, or only one feature's runs.
- help new: Which runs to remove: every run, only runs older than a number of days, or only one tool's runs.
- choices: `all`: Everything -> keep; `old`: Older than -> Older than a number of days; `task`: One feature only -> One tool only

### days
- label now: Older than (days)  -> new: keep
- help now: Runs finished longer ago than this are forgotten.
- help new: Runs that finished more than this many days ago are removed. 1 to 3650, default 30.

### task
- label now: Which feature  -> new: Which tool
- help now: Only this feature's runs are forgotten.
- help new: Only this tool's runs are removed.

## geotag  (title: Geotag)
summary:
- now: Give photos a location, by matching when they were taken against where you were.
- new: Adds a location to photos by matching the time they were taken against where you were.

### folder
- label now: Photos missing a location  -> new: Folder to geotag
- help now: (none)
- help new: The folder of photos to give a location, a shoot or the whole library. Photos that already have a location are skipped unless Include already located is on.

### max_gap
- label now: Give up after (minutes)  -> new: keep
- help now: Beyond this, no guess is made. A confident wrong pin is worse than an empty one - you would never think to check it.
- help new: The largest time gap, in minutes, between a photo and the nearest known position for a location to be written. 1 to 1440, default 60. Beyond it no guess is made, because a wrong location is worse than none.

### order
- label now: Location source  -> new: keep
- help now: Never both at once. A Timeline is continuous but coarse; a phone that was in your pocket all day is sparse but exact - so which should win depends on the day, not on a rule. Whichever is asked first wins wherever it has anything near enough in time; the other is only consulted where it does not.
- help new: Which source of positions to ask first. The first source wins wherever it has a position near enough in time, and the other is used only where it has none. The Timeline is continuous but rough, and phone photos are exact but sparse.
- choices: `timeline`: The imported Timeline first, your photographs as a fallback -> Timeline first, then your photos; `photos`: Your photographs first, the Timeline as a fallback -> Your photos first, then the Timeline; `timeline_only`: Only the imported Timeline -> Timeline only; `photos_only`: Only your photographs -> Your photos only

### phone
- label now: Photos with locations  -> new: keep
- help now: Phone photos, or any folder of already-geotagged pictures - their GPS and capture times become the reference. Leave blank to use the Timeline alone.
- help new: A folder of photos that already have a location, usually phone photos. Their positions and capture times become the reference. Blank uses the Timeline alone.

### sidecar_only
- label now: Sidecars only  -> new: keep
- help now: A .xmp beside the photograph rather than inside it. This app never opens a negative for writing at all; for a JPEG it normally writes in place, where Explorer and Synology Photos look, and this keeps it out of the file entirely.
- help new: Writes the location into a .xmp sidecar beside each photo instead of into the photo. Off by default: a JPEG is normally written in place, which is where Windows Explorer and Synology Photos look. A RAW file always gets a sidecar and is never changed itself.

### keep_originals
- label now: Keep originals  -> new: keep
- help now: A copy of each photograph goes into a _NoLocation folder beside it before a location is written. The location goes into the existing file otherwise, which is what every program that reads one expects - this is the belt.
- help new: Copies each photo into a _NoLocation folder beside it before the location is written. Off by default: the location is written into the photo itself, which every other program expects. Turn it on if you want an untouched copy to go back to.

### replace
- label now: Include already located  -> new: keep
- help now: (none)
- help new: Also writes a location on photos that already have one, replacing it. Off by default: a position recorded by the camera is kept.

### no_interpolate
- label now: Nearest fix only  -> new: Nearest position only
- help now: By default a photo between two fixes is placed between them, and marked approximate when they are far apart.
- help new: Uses the position of the single nearest record in time. Off by default: a photo taken between two records is placed between them, and marked approximate when they are far apart.

### drift
- label now: Clock is fast by (min)  -> new: Clock fast by (minutes)
- help now: Leave at zero. If the camera clock is actually wrong, 'Fix the clock' corrects the photos themselves, which is better than working around them here every time.
- help new: Minutes the camera clock runs ahead of true time. This many minutes are taken off each photo's time before matching. -720 to 720, default 0. If the clock really is wrong, use Fix the clock to correct the photos instead.

### skip_here
- same as blur.skip_here

## history  (title: History)
summary:
- now: What was actually done, and when. Every run that wrote something.
- new: Lists every run that changed a file, and when. Nothing is changed.

### task
- label now: Which feature  -> new: Which tool
- help now: Every run that changed a file is recorded - from this page, from the command line, and from anything DSM's Task Scheduler runs overnight.
- help new: Shows only this tool's runs. Every run that changed a file is recorded, from this page, from the command line and from DSM's Task Scheduler.

### limit
- label now: How many  -> new: Runs to show
- help now: The most recent runs, newest first.
- help new: The number of most recent runs to list, newest first. 5 to 400, default 100.

## import-places  (title: Import place names)
summary:
- now: Read a table of towns once, so photos can be sorted by country and city without ever going online.
- new: Reads a table of towns once, so photos can be sorted by country and city offline.

### dump
- label now: The cities file  -> new: Cities file
- help now: Download it once from https://download.geonames.org/export/dump/ - cities15000.zip is the one to take (about 2 MB). Put it anywhere the NAS can see and give the path here; the .zip is read as it is, no unzipping needed. Leave blank to just see what is already imported.
- help new: The GeoNames file cities15000.zip (about 2 MB) from https://download.geonames.org/export/dump/. Put it anywhere the NAS can see and give its path here. The zip is read as it is. Blank only shows what is already imported.

### countries
- label now: countryInfo.txt (optional)  -> new: Country names file
- help now: Only replaces the built-in country names. Everything works without it - take it from the same page if a country is named differently from how you would name the folder.
- help new: The GeoNames file countryInfo.txt, from the same page. It replaces the built-in country names, for when a country should be named differently as a folder. Blank keeps the built-in names.

### regions
- label now: admin1CodesASCII.txt (optional)  -> new: Region names file
- help now: Region and state names - Catalonia, California - for the {region} variable in folder patterns. Same GeoNames page. Without it {region} is simply left out of a name.
- help new: The GeoNames file admin1CodesASCII.txt, from the same page. It gives region and state names, such as Catalonia or California, for the {region} variable in folder patterns. Blank leaves {region} out of names.

## import-timeline  (title: Import Google Timeline)
summary:
- now: Read a Timeline export once into the app's own store.
- new: Reads a Google Timeline export once into the app's own store.

### export
- label now: Your Timeline.json  -> new: Timeline.json path
- help now: Exported from the phone: Maps > profile > Your Timeline > ... > Location & privacy settings > Export Timeline data. Leave blank to just see what is already imported.
- help new: The path to the Timeline.json exported from your phone. In Google Maps: profile > Your Timeline > ... > Location & privacy settings > Export Timeline data. Blank only shows what is already imported.

## label  (title: Apply label)
summary:
- now: Mark a folder you have already made your mind up about - to edit, to sharpen, a timelapse - so everything downstream can act on it.
- new: Gives every photo in a folder one colour label, so other tools can act on it.

### folder
- label now: Folders to mark  -> new: Folders to label
- help now: Whole folders at a time, which is the point: you usually know what a shoot is FOR before you have looked at a single frame of it.
- help new: The folders to label. Every photo inside each one gets the colour label.

### colour
- label now: The colour  -> new: Colour label
- help now: What each one means is set in Setup > Colour meanings. A colour with no meaning set cannot be used here - a mark nothing can read is not worth writing.
- help new: The colour label to write. What each colour means is set in Setup > Colour meanings. A colour with no meaning set cannot be used. 'Take the colour off' removes the label.

### replace
- label now: Replace existing colour  -> new: keep
- help now: Off, a photograph already carrying a different colour is listed and left. On, it is overwritten - and the old colour is gone, not recoverable from anything.
- help new: Overwrites a different colour label already on a photo. Off by default: such a photo is listed and left. The old colour cannot be recovered.

### raw
- label now: The RAW tree  -> new: RAW tree
- help now: So the negative carries it too. Leave blank to mark only what is in the folders above.
- help new: The top of the RAW tree, so each photo's RAW file gets the colour label too, in its sidecar. Blank labels only the folders above.

### previews
- label now: The previews tree  -> new: Previews tree
- help now: So the colour is visible on the tablet, where you are actually looking at these.
- help new: The top of the previews tree, so the colour label shows on the tablet. Blank leaves previews alone.

### in_file
- label now: Write into the photo  -> new: keep
- help now: A sidecar is what Lightroom and darktable read and the only thing a RAW can carry. Inside the JPEG is what Synology Photos and Explorer look at. Both, unless you have a reason.
- help new: same as blur.in_file, with "the colour label" in place of "the tag"

### skip_here
- same as blur.skip_here

## labels  (title: Colour meanings)
summary:
- now: What each of the five colours means, what tags it writes, and where photographs carrying it are sent.
- new: Sets what each of the five colour labels means, which tags it writes and where its photos go.

### label_red_name
- label now: Means  -> new: Meaning
- help now: What red means to you - 'Edit', 'Sharpen', 'Timelapse'. Leave blank and this colour does nothing at all. Written onto the photograph as a tag, so other programs can search for it.
- help new: What red means to you, for example Edit, Sharpen or Timelapse. The word is written on the photo as a tag, so other programs can search for it. Blank means red does nothing.

### label_red_keywords
- label now: Extra keywords  -> new: Extra tags
- help now: Comma separated, and added to the name above. This is how a colour becomes readable by a program that has never heard of this app - put in whatever the other app searches for.
- help new: More tags written together with the meaning, separated by commas. Use the words another program searches for, so it can find these photos without knowing this app. Blank adds none.

### label_red_action
- label now: Action  -> new: keep
- help now: Sending copies the photograph out to the develop tree the next time Send to develop runs. Nothing else is ever moved by a colour.
- help new: What Send to develop does with photos carrying red. Send copies them into the develop tree on its next run. Nothing else is ever moved because of a colour label.
- choices: `none`: Nothing - just mark it, so you and other apps can find it -> Mark it only (nothing moves); `develop`: Send it out to the develop tree -> Send it to the develop tree

### label_red_folder
- label now: Into folder  -> new: Develop subfolder
- help now: A folder INSIDE the develop tree - 'Timelapse', 'Sharpen', 'Print'. Blank means the develop tree itself, which is what 'send it for editing' means. A name of its own is what keeps six hundred timelapse stills out of tonight's edits.
- help new: A folder name inside the develop tree, for example Timelapse or Print. Blank sends the photos into the develop tree itself. A name of its own keeps hundreds of timelapse frames apart from the photos you are editing.

### label_red_raw
- label now: Send the RAW  -> new: Send the RAW file
- help now: A negative is fifty megabytes. Worth it for something you are going to develop properly; not worth it for a timelapse frame or a sharpening pass.
- help new: Also copies the RAW file into the develop tree. RAW files are large, so turn this on only for photos you will develop fully, not for a timelapse or a sharpening pass. Off by default.

### label_yellow_name, label_yellow_keywords, label_yellow_action, label_yellow_folder, label_yellow_raw
- same as red, with yellow

### label_green_name, label_green_keywords, label_green_action, label_green_folder, label_green_raw
- same as red, with green

### label_blue_name, label_blue_keywords, label_blue_action, label_blue_folder, label_blue_raw
- same as red, with blue

### label_purple_name, label_purple_keywords, label_purple_action, label_purple_folder, label_purple_raw
- same as red, with purple

## library  (title: Library)
summary:
- now: Every folder, and what has been done to it. Nothing is written.
- new: Shows every folder in the library and what has been done to it. Nothing is changed.

### folder
- label now: The library  -> new: Library
- help now: Read, never written. Every mark on the tree is worked out from the files as they are now rather than from a log of what was done, so moving a shoot in File Station moves its answer with it.
- help new: The library to show. It is read, never written. Every mark is worked out from the files as they are now, so a folder moved in File Station keeps its marks.

### exclude
- label now: Folders to skip  -> new: Hide from this view
- help now: A folder NAME leaves out every folder called that, anywhere - 'Archive', 'Scans'. A PATH leaves out that one folder and everything under it. Comma separated, and it only affects this view: nothing is hidden from the tasks that actually do work. For folders that are not photographs at all - PhotoPrism's cache, @eaDir - use the Setup list instead, which every feature obeys.
- help new: Folders left out of this view only, separated by commas. A name such as Archive hides every folder with that name. A path hides that one folder and everything under it. Nothing is hidden from the tools that do work. For that, use Setup > Skip everywhere.

### only
- label now: Show  -> new: keep
- help now: 'Only what is unfinished' is the useful one: a shoot that is half geotagged or half separated is a job you left in the middle, and it looks identical to a finished one in File Station.
- help new: Which folders to list. 'Unfinished' shows shoots that are half geotagged or half separated, which look finished in File Station.

### mirror
- label now: Mirror Setup's trees  -> new: Trees from Setup
- help now: On, the RAW and previews trees come from Setup and the position inside them is worked out from the library - so a shoot always lands where unpairing the whole library would have put it, and there is nothing to type or get wrong. Turn it off only to send this one run somewhere else.
- help new: On, the tree boxes below are ignored and the trees come from Setup. Off, the folders you type below are compared against the library for this view only. (check: this tool writes nothing, so the shared blur.mirror text about files moving does not fit here.)

### raw
- label now: The RAW tree  -> new: RAW tree
- help now: (none)
- help new: The top of the RAW tree, compared against the library to see which shoots have their RAW files separated. Blank skips that check. Ignored while Trees from Setup is on.

### previews
- label now: The previews tree  -> new: Previews tree
- help now: (none)
- help new: The top of the previews tree, compared against the library to see which shoots have previews. Blank skips that check. Ignored while Trees from Setup is on.

### video
- label now: The video tree  -> new: Video tree
- help now: (none)
- help new: The top of the video tree, compared against the library to see which shoots have their videos separated. Blank skips that check. Ignored while Trees from Setup is on.

### charts
- label now: Draw the charts  -> new: keep
- help now: The dashboard at the top. It reads every photograph once - cached afterwards, and shared with Search and Storage.
- help new: Draws the dashboard at the top. Every photo is read once, and the result is cached and shared with Search and Storage. On by default.

### rescan
- label now: Read every folder again  -> new: keep
- help now: Normally a folder is only re-read when its contents change. Use this if you have edited photos with something else and want the marks brought up to date.
- help new: Reads every folder again instead of only the folders whose contents changed. Use it after editing photos with another program, so the marks are brought up to date.

### skip_here
- same as blur.skip_here

## password  (title: Password)
summary:
- now: Lock the app behind one password - there are no accounts, and the half worth locking is everything this app can move.
- new: Locks the app behind one password. There are no accounts.

### word
- label now: New password  -> new: keep
- help now: At least six characters. Stored as a hash with a random salt, never as the password itself.
- help new: The new password, at least six characters. It is stored as a salted hash, never as the password itself.

### again
- label now: Type it again  -> new: Repeat password
- help now: Because a password you cannot see is a password you can mistype twice the same way and not know.
- help new: The same password again, to catch a typing mistake you cannot see.

### everywhere
- label now: Sign out everywhere  -> new: keep
- help now: Every browser has to type it again. Tick this on its own to do only that; changing the password does it anyway.
- help new: Signs out every browser, so each one has to type the password again. Tick it alone to do only that. Changing the password signs out everywhere anyway.

### off
- label now: Take the password off  -> new: Remove the password
- help now: Unlocks the app entirely. Anything that can reach the port can then move, cull and re-mirror the library.
- help new: Removes the password. Anyone who can reach the port can then use the app, including every tool that moves files.

## permissions  (title: Permissions check)
summary:
- now: Make a real folder the way every task does and see whether it comes out like the one above it - and hand the ones this app cannot finish to a job on the NAS that can.
- new: Checks folder ownership in each tree, and writes a repair job for what the app cannot fix itself.

### folder
- label now: Also check  -> new: Extra folder to check
- help now: The trees from Setup are always checked. This is for one more - a share you are about to point the app at, say.
- help new: One more folder to check besides the trees from Setup, for example a share you are about to point the app at. Blank checks the Setup trees only.

### repair
- label now: Write repair job  -> new: keep
- help now: Writes the job DSM's Task Scheduler should run as root every few minutes. It fixes exactly the folders this app has just made, so it costs nothing when there is nothing waiting, and it can put the whole existing tree right once when you run it by hand with 'all'. Plain text - read it first.
- help new: Writes a script for DSM's Task Scheduler to run as root every few minutes. It fixes only the folders this app has just made, so it costs nothing when nothing is waiting. Run by hand with 'all' it fixes the whole tree once. It is plain text, so read it first.

## pin  (title: Pin a place by hand)
summary:
- now: Give a whole folder one location, from a map link you pasted.
- new: Gives every photo in a folder one location, from a map link you paste.

### folder
- label now: Photos to place  -> new: Folder to pin
- help now: (none)
- help new: The folder of photos to give the location. Every photo inside it gets the same position. Photos that already have a location are skipped unless Include already located is on.

### link
- label now: Map link or coordinates  -> new: keep
- help now: Google Maps, Apple Maps, OpenStreetMap, a geo: link, or a plain "24.467, 39.611". In Google Maps, right-click the spot and click the numbers at the top of the menu to copy them. A shortened maps.app.goo.gl link carries no coordinate - open it first.
- help new: A Google Maps, Apple Maps or OpenStreetMap link, a geo: link, or plain coordinates such as 24.467, 39.611. In Google Maps, right-click the spot and click the numbers at the top of the menu to copy them. A short maps.app.goo.gl link has no coordinates, so open it first.

### sidecar_only
- same as geotag.sidecar_only

### keep_originals
- same as geotag.keep_originals

### replace
- label now: Include already located  -> new: keep
- help now: Off by default: a real fix from a camera is better than a place you pointed at afterwards.
- help new: same as geotag.replace

### skip_here
- same as blur.skip_here

## previews  (title: Make previews)
summary:
- now: Small JPEGs in a tree shaped like the library, for rating away from the NAS.
- new: Makes small JPEG copies of the library, in the same folder shape, for rating on the tablet.

### folder
- label now: Photos to preview  -> new: Folder to preview
- help now: A single shoot, or the whole library.
- help new: The folder to make previews of, a shoot or the whole library.

### mirror
- label now: Mirror Setup's trees  -> new: Trees from Setup
- help now: On, the RAW and previews trees come from Setup and the position inside them is worked out from the library - so a shoot always lands where unpairing the whole library would have put it, and there is nothing to type or get wrong. Turn it off only to send this one run somewhere else.
- help new: same as blur.mirror

### previews
- label now: The previews tree  -> new: Previews tree
- help now: Created if it is not there. Must not be inside the library.
- help new: The top of the previews tree. It is made if it does not exist. It must not be inside the library.

### profile
- label now: Size  -> new: Preview size
- help now: Set your usual size once in Setup. Change it here only for this one run. A preview already made at a different size is noticed and remade - you do not have to remember to tick Rebuild.
- help new: The size and JPEG quality of the previews. 'Size from Setup' is the default. Pick another size here for this one run only. A preview already made at a different size is remade.
- choices: `saved`: Use the size set in Setup -> Size from Setup; `small`: Small - 1280px, quality 80 (quickest to sync) -> Small: 1280 px, quality 80; `medium`: Medium - 2048px, quality 85 (enough to judge sharpness) -> Medium: 2048 px, quality 85; `large`: Large - 3200px, quality 92 (close to the original) -> Large: 3200 px, quality 92; `custom`: Custom - set the size and quality yourself -> Custom: set the boxes below

### long_edge
- label now: Custom longest side (pixels)  -> new: keep
- help now: Only used when Size is set to Custom. Big enough to judge sharpness on a tablet, small enough to sync.
- help new: The longest side of a custom preview, in pixels. 320 to 8000, default 2048. Only used when Preview size is Custom.

### quality
- label now: Custom JPEG quality  -> new: keep
- help now: Only used when Size is set to Custom.
- help new: The JPEG quality of a custom preview. 40 to 98, default 85. Only used when Preview size is Custom.

### brackets
- label now: One per bracket  -> new: One preview per bracket
- help now: Only the metered frame gets a preview. Rating it rates the whole set. How a set is worked out is set once, in Setup, so previews, ratings and cull cannot come to different answers about one shoot.
- help new: Makes a preview of only the metered frame of each bracket set. Rating that preview rates the whole set. How a set is found is set in Setup > Brackets. From Setup by default.

### carry_tags
- label now: Carry tags over  -> new: Copy tags to previews
- help now: Written into the preview itself. Without this a preview answers to no search at all, and 'show me the brackets' gives a different answer depending on which folder you are standing in.
- help new: Writes each photo's tags into its preview, so a search on the tablet finds the same photos as a search in the library. On by default.

### bracket_tag
- label now: Bracket tag  -> new: keep
- help now: The tag put on the preview that stands for a bracket set, so a set is one search away on the tablet. Blank writes nothing. The same word is what 'Find brackets' writes onto the frames themselves.
- help new: The tag written on the preview that stands for a bracket set, so sets can be searched on the tablet. Default bracket. Find brackets writes the same word on the frames themselves. Blank writes nothing. From Setup by default.

### rebuild
- label now: Remake all  -> new: Remake every preview
- help now: Rarely needed now that a size change is noticed on its own.
- help new: Remakes every preview, even one that already exists at the right size. Rarely needed, because a size change is noticed on its own. Off by default.

### skip_here
- same as blur.skip_here

## ratings  (title: Rating & tags)
summary:
- now: Carry the stars AND the colour from where you marked them onto the originals and their RAWs.
- new: Copies ratings and colour labels from the previews you rated onto the originals and their RAW files.

### folder
- label now: Rated folder  -> new: keep
- help now: Usually the previews you synced to a tablet.
- help new: The folder where you rated, usually the previews tree synced to the tablet. Ratings and colour labels are read from here.

### library
- label now: The library  -> new: Library
- help now: Originals receive the rating. Leave blank to skip.
- help new: The top of the library. The originals here receive the ratings. Blank skips the library.

### mirror
- label now: Mirror Setup's trees  -> new: Trees from Setup
- help now: On, the RAW and previews trees come from Setup and the position inside them is worked out from the library - so a shoot always lands where unpairing the whole library would have put it, and there is nothing to type or get wrong. Turn it off only to send this one run somewhere else.
- help new: same as blur.mirror, with "RAW files or previews moving" replaced by "ratings being written"

### raw
- label now: The RAW tree  -> new: RAW tree
- help now: RAWs get a .xmp beside them - the negative is never opened for writing. Leave blank to skip.
- help new: The top of the RAW tree. Each RAW file receives the rating in a .xmp sidecar beside it. The RAW file itself is never changed. Blank skips RAW files.

### brackets
- label now: Spread across brackets  -> new: Spread over bracket sets
- help now: With one preview per set only the metered frame is rated. Without this the rest stay blank and a later cull splits the set. How a set is worked out is set once, in Setup.
- help new: Gives every frame of a bracket set the rating of its metered frame, which is the only frame with a preview. Off, the other frames stay unrated and a later cull splits the set. How a set is found is set in Setup > Brackets. From Setup by default.

### stars
- label now: Ratings  -> new: keep
- help now: The stars. Off, only colours are carried.
- help new: Copies the star ratings. Off, only colour labels are copied. On by default.

### colours
- label now: Colours  -> new: Colour labels
- help now: The colour label, and whatever that colour means in Setup, written on beside it as keywords. A star and a colour are made in the same moment and the colour used to be left behind.
- help new: Copies the colour label, and writes the colour's meaning from Setup > Colour meanings beside it as tags. On by default.

### replace
- label now: Replace existing colour  -> new: keep
- help now: Off, a photograph on the other side already carrying a different colour is listed and left. On, it is overwritten - and the old colour is gone, not recoverable from anything.
- help new: Overwrites a different colour label already on the original. Off by default: such a photo is listed and left. The old colour cannot be recovered.

### in_file
- label now: Write into the photo  -> new: keep
- help now: For the colour. A sidecar is what Lightroom and darktable read and the only thing a RAW can carry; inside the JPEG is what Synology Photos and Explorer look at. Both, unless you have a reason.
- help new: same as blur.in_file, with "the colour label" in place of "the tag"

### skip_here
- same as blur.skip_here

## reindex  (title: Reindex)
summary:
- now: Tell DSM about the folders this app changed, so Synology Photos and Media Server stop showing yesterday's library.
- new: Tells DSM which folders changed, so Synology Photos and Media Server show the current library.

### script_into
- label now: Write the script into  -> new: Script folder
- help now: Only used when the DSM tools cannot be reached from here, which is the normal case in a container. Somewhere you can see from File Station - the library root is fine.
- help new: Where the re-index script is written, when DSM's tools cannot be reached from here, which is normal in a container. Choose a folder you can see in File Station. The library root is fine.

### photos
- label now: Include Synology Photos  -> new: keep
- help now: Its re-index takes no folder, so it covers the whole space and is the slow half. Media Indexing - Media Server, DLNA, Photo Station - is per folder and quick.
- help new: Also re-indexes Synology Photos. That re-index covers the whole space and is the slow part. Media indexing for Media Server, DLNA and Photo Station is per folder and quick. On by default.

### user
- label now: Your DSM username  -> new: DSM username
- help now: Synology Photos' re-index is run as root but needs to know whose library to re-index. Nothing is stored anywhere but in the script this writes.
- help new: The DSM user whose Synology Photos library is re-indexed. The re-index runs as root, so it needs the name. It is stored only in the script this writes.

### personal
- label now: Personal space  -> new: keep
- help now: Photos keeps the shared space and each person's space in separate libraries, with separate APIs. Off is the shared one.
- help new: Re-indexes your personal space in Synology Photos. Off re-indexes the shared space. The two are separate libraries.

### forget
- label now: Empty the queue  -> new: keep
- help now: Off by default: the queue is what the NEXT script is built from, and emptying it before the schedule actually works would leave those folders waiting nowhere. Tick it once you have seen the task run on the NAS.
- help new: Clears the list of changed folders after the script is written. Off by default: the next script is built from that list, so clear it only once you have seen the scheduled task run on the NAS.

## remirror  (title: Re-mirror RAWs)
summary:
- now: Reshape the RAW tree to match the library, however you have reorganised it.
- new: Moves RAW files within the RAW tree so it matches the library's current shape.

### library
- label now: The library  -> new: Library
- help now: Always the whole tree, and never changed - it is what every RAW is matched against, so a photo that moved to another shoot is still found. To work on one shoot only, use 'Only these folders' below.
- help new: The whole library, read only. Every RAW file is matched against it, so a photo moved to another shoot is still found. To work on one shoot, use Only these folders.

### mirror
- label now: Mirror Setup's trees  -> new: Trees from Setup
- help now: On, the RAW and previews trees come from Setup and the position inside them is worked out from the library - so a shoot always lands where unpairing the whole library would have put it, and there is nothing to type or get wrong. Turn it off only to send this one run somewhere else.
- help new: same as blur.mirror

### raw
- label now: RAW tree  -> new: keep
- help now: RAWs are moved within this tree. Nothing leaves it.
- help new: The top of the RAW tree. RAW files are moved within it, and nothing leaves it.

### only
- label now: Only these folders  -> new: keep
- help now: Blank means the whole RAW tree. Pick a shoot - in either tree - and only its RAWs are judged and moved. The library is still searched whole, which is what tells 'the photo moved' apart from 'the photo is gone'.
- help new: Limits the run to these shoots, in either tree. Blank means the whole RAW tree. The library is still searched whole, which tells a moved photo from a missing one.

### gather_library
- label now: Stray RAWs too  -> new: Gather stray RAW files
- help now: A STRAY RAW is one still sitting in the library beside its photo: it has a partner, it is simply in the wrong tree because it was never separated. On, those are moved into the RAW tree at the position their photo has now.
- help new: Also moves RAW files still sitting in the library beside their photos into the RAW tree, at the position their photo has now. On by default.

### orphans
- label now: RAWs with no photo  -> new: Unmatched RAW files
- help now: A RAW whose photo is not in the library at all - a RAW-only shot, or one whose photo was culled, developed, or is in a folder you skip in Setup. The plan says which of those it is for each one. Left alone by default: a RAW-only shot is not a mistake to tidy away.
- help new: What to do with a RAW file whose photo is not in the library: a RAW-only photo, or one whose JPEG was culled, developed or sits in a skipped folder. Check the list says which. Left alone by default, because a RAW-only photo is not a mistake.
- choices: `leave`: Leave them exactly where they are -> Leave them where they are; `aside`: Put them aside, in a _Culled folder in the RAW tree -> Move them to _Culled in the RAW tree; `list`: Only list them -> keep

### tidy
- same as cull.tidy

### skip_here
- same as blur.skip_here

## remirror_previews  (title: Re-mirror previews)
summary:
- now: Move every preview to where its photograph now lives, instead of making the whole tree again.
- new: Moves each preview to where its photo now is, instead of remaking the whole tree.

### library
- label now: The library  -> new: Library
- help now: Read only. Where each photograph is now is the answer this works from.
- help new: The library, read only. Where each photo is now decides where its preview goes.

### previews
- label now: Previews tree  -> new: keep
- help now: Reshaped to match. Previews are only ever moved within it, and none is remade - so the ratings on them survive.
- help new: The top of the previews tree. Previews are only moved within it and none is remade, so the ratings on them survive.

### orphans
- label now: Orphaned previews  -> new: keep
- help now: A preview of a photograph that no longer exists is a picture of nothing. Leaving it costs a few kilobytes and Make previews will not remake it.
- help new: What to do with a preview whose photo no longer exists. Leaving it costs a few kilobytes, and Make previews will not remake it.
- choices: `leave`: Leave it where it is - Make previews will not remake it -> Leave it where it is; `aside`: Put it aside in a _Culled folder inside the previews tree -> Move it to _Culled in the previews tree

### tidy
- same as cull.tidy

### skip_here
- same as blur.skip_here

## remirror_video  (title: Re-mirror video)
summary:
- now: Move every clip to the place in the video tree that matches where the photographs of its moment now live.
- new: Moves each video to the place in the video tree that matches the photos taken at the same time.

### library
- label now: The library  -> new: Library
- help now: Read only. Where the photographs are now is the answer this works from.
- help new: The library, read only. Where the photos are now decides where each video goes.

### video
- label now: Video tree  -> new: keep
- help now: Reshaped to match. Clips are only ever moved within it.
- help new: The top of the video tree. Videos are only moved within it.

### near_hours
- label now: Shoot window (hours)  -> new: keep
- help now: The same number Separate video uses. Changing it here and not there is how the two come to disagree about where a clip belongs.
- help new: How many hours after a shoot ended a video still belongs to it. 0 to 72, default 12. Use the same number as Separate video, or the two tools will disagree about where a video belongs.

### shape
- label now: Otherwise file by  -> new: Fallback folders
- help now: Only used when nothing in the library was taken anywhere near it. A clip placed by its own date and one placed by the shoot it belongs to are worth very different amounts of trust, and the row says which decided it.
- help new: Where a video goes when no photos were taken near the same time. Check the list says which rule decided each video.

### shift_minutes
- label now: Shift clocks by (min)  -> new: Shift video times (minutes)
- help now: For a camera whose clock was set to the wrong zone. The same correction Separate video offers.
- help new: Minutes added to each video's recorded time before matching, for a camera whose clock was set to the wrong time zone. -1440 to 1440, default 0. Use the same number as Separate video.

### tidy
- same as cull.tidy

### skip_here
- same as blur.skip_here

## rename  (title: Power rename)
summary:
- now: Every folder in a table, names editable in place - with find and replace, patterns, numbering and case over the whole table.
- new: Lists folders in a table and renames them in place, with find and replace, patterns, numbering and case.

### folder
- label now: Folder to list  -> new: keep
- help now: Its folders fill the table. Picking folders in the Files tab first lists those instead.
- help new: The folder whose sub-folders fill the table. Folders selected in the Explorer tab first are listed instead.

### start
- label now: Start at level  -> new: keep
- help now: 0 is the folder above - its own contents. 1 skips straight past those to the level below, so a library of years can list the shoots inside them without listing the years.
- help new: How many levels below the folder the table starts. 0 to 9, default 0. 0 lists the folder's own sub-folders. 1 skips them and lists the level below, so a library of years can list the shoots without the years.

### depth
- label now: How far down  -> new: Levels to list
- help now: 1 is one level only. 0 is the whole way down from where it starts, indented, so a shoot four levels in can be fixed in the same pass.
- help new: How many levels of folders to list. 0 to 9, default 1. 1 lists one level. 0 lists every level down from the start, indented, so a deep folder can be fixed in the same run.

### with_raw
- label now: RAWs follow  -> new: RAW files follow
- help now: A folder renamed in the library is renamed at the matching place in the RAW tree, so the trees stay mirrored.
- help new: Renames the matching folder in the RAW tree too, so the trees stay mirrored. On by default.

### with_previews
- label now: Previews follow  -> new: keep
- help now: The same for the previews tree, so the tablet copy does not keep the old name.
- help new: Renames the matching folder in the previews tree too, so the tablet copy does not keep the old name. On by default.

### skip_here
- same as blur.skip_here

## retime  (title: Fix the clock)
summary:
- now: Correct the capture time of a whole shoot, from one photo you have dated.
- new: Corrects the capture time of a whole shoot, from one photo whose real time you know.

### folder
- label now: Photos to correct  -> new: Folder to correct
- help now: One shoot, usually - a clock is wrong for a stretch of time, not for a whole library.
- help new: The folder of photos to correct, usually one shoot. A clock is wrong for a stretch of time, not for a whole library.

### mirror
- label now: Mirror Setup's trees  -> new: Trees from Setup
- help now: On, the RAW and previews trees come from Setup and the position inside them is worked out from the library - so a shoot always lands where unpairing the whole library would have put it, and there is nothing to type or get wrong. Turn it off only to send this one run somewhere else.
- help new: same as blur.mirror, with "RAW files or previews moving" replaced by "RAW files being corrected"

### raw
- label now: The RAW tree  -> new: RAW tree
- help now: Strongly recommended. A RAW is paired to its JPEG by capture time, so correcting the JPEGs alone breaks every pair in the shoot. The RAW itself is never opened - the corrected time goes in the .xmp beside it.
- help new: The top of the RAW tree, so the RAW files are corrected too, in the .xmp sidecar beside each one. Strongly recommended: RAW files are paired to JPEGs by capture time, so correcting JPEGs alone breaks every pair. Blank leaves RAW files alone.

### mode
- label now: How to correct it  -> new: Correction method
- help now: From a photograph whose real time you know, or by a fixed amount you work out yourself. Everything in the folder moves by the same difference either way: a clock that is wrong is wrong by a constant.
- help new: How the correction is worked out: from one photo whose real time you know, or by an amount you type. Every photo in the folder moves by the same difference either way.
- choices: `photo`: From one photo I have dated correctly -> From one photo's real time; `amount`: By a fixed amount I know -> By a fixed amount

### reference
- label now: Reference photo  -> new: keep
- help now: Leave blank for the earliest photo in the folder, which is usually the one you can place. Only used by the first method.
- help new: The photo whose real time you know. Blank uses the earliest photo in the folder. Only used by the first method.

### correct_time
- label now: Its real time  -> new: Real capture time
- help now: For example 2024-05-01 09:00:00. Everything else in the folder moves by the same difference.
- help new: The real time the reference photo was taken, for example 2024-05-01 09:00:00. Every photo in the folder moves by the difference between this and the recorded time. Only used by the first method.

### days
- label now: Days  -> new: Shift by (days)
- help now: (none)
- help new: Days to add to every capture time, for the fixed-amount method. -3650 to 3650, default 0. A negative number moves time backwards. Added to the hours, minutes and seconds below.

### hours
- label now: Hours  -> new: Shift by (hours)
- help now: (none)
- help new: Hours to add to every capture time, for the fixed-amount method. -48 to 48, default 0. A negative number moves time backwards.

### minutes
- label now: Minutes  -> new: Shift by (minutes)
- help now: (none)
- help new: Minutes to add to every capture time, for the fixed-amount method. -1440 to 1440, default 0. A negative number moves time backwards.

### seconds
- label now: Seconds  -> new: Shift by (seconds)
- help now: Negative numbers move time backwards. Used by the second method.
- help new: Seconds to add to every capture time, for the fixed-amount method. -3600 to 3600, default 0. A negative number moves time backwards. The total of days, hours, minutes and seconds must not be zero.

### keep_originals
- label now: Keep originals  -> new: keep
- help now: A copy of each photograph goes into a _BeforeRetime folder beside it before its time is changed. Off by default: the correction is written into the existing file and verified by reading it back, so a copy is insurance rather than a necessity - but it is the cheap kind.
- help new: Copies each photo into a _BeforeRetime folder beside it before its time is changed. Off by default: the correction is written into the photo and read back to verify it, so a copy is extra safety.

### skip_here
- same as blur.skip_here

## search  (title: Search)
summary:
- now: Find photographs by camera, lens, focal length, exposure, stars, tags or location - as many at once as you like.
- new: Finds photos by camera, lens, exposure, date, stars, tags or location, in any combination.

### folders
- label now: Where to look  -> new: Folders to search
- help now: One folder per line, everything below each. Empty means the library from Setup.
- help new: The folders to search, one per line. Everything inside each one is searched. Blank means the library from Setup.

### kinds
- label now: Which files  -> new: keep
- help now: (none)
- help new: Which kinds of file to search. The default searches photos and RAW files together.
- choices: ``: Photographs and RAWs -> Photos and RAW files; `jpeg`: JPEGs only -> keep; `raw`: RAWs only -> RAW files only; `video`: Video only -> Videos only

### name
- label now: File name holds  -> new: File name contains
- help now: (none)
- help new: Text the file name must contain. Blank matches any name.

### missing
- label now: Not said  -> new: Missing fact
- help now: Only the photographs that do not record this - the "not said" row of a chart. One or more of: taken, camera, lens, focal, aperture, iso, shutter, colour, tags.
- help new: Finds photos that do not record a fact, the 'not said' row of a chart. Type one or more of taken, camera, lens, focal, aperture, iso, shutter, colour, tags, separated by commas. Blank ignores this.

### since
- label now: Taken on or after  -> new: keep
- help now: 2022, 2022-07 or 2022-07-14.
- help new: The earliest date to include. Type a year, a month or a day: 2022, 2022-07 or 2022-07-14. Blank means no start date.

### until
- label now: Taken on or before  -> new: keep
- help now: (none)
- help new: The latest date to include. Type a year, a month or a day: 2022, 2022-07 or 2022-07-14. Blank means no end date.

### camera
- label now: Camera  -> new: keep
- help now: Part of the name is enough - GH4, A7C.
- help new: Part of the camera name is enough, for example GH4 or A7C. Blank means any camera.

### lens
- label now: Lens  -> new: keep
- help now: (none)
- help new: Part of the lens name is enough, for example 25/F1.7. Blank means any lens.

### focal_from
- label now: Focal length from (mm)  -> new: keep
- help now: (none)
- help new: The shortest focal length to include, in millimetres. Blank means no lower limit.

### focal_to
- label now: to (mm)  -> new: Focal length to (mm)
- help now: (none)
- help new: The longest focal length to include, in millimetres. Blank means no upper limit.

### focal35
- label now: Measure it full-frame  -> new: Full-frame focal length
- help now: 25mm on the GH4 frames like 50mm. With this on, the numbers mean the same thing on both bodies - and a file that does not record the equivalent cannot answer, so it is left out and counted rather than guessed at.
- help new: Compares focal lengths as full-frame equivalents, so 25mm on a GH4 counts as 50mm and the numbers mean the same on every camera. A photo that does not record the equivalent cannot be compared, so it is left out and counted.

### f_from
- label now: Aperture from f/  -> new: keep
- help now: (none)
- help new: The widest aperture to include, as the f-number, for example 1.7. Blank means no limit.

### f_to
- label now: to f/  -> new: Aperture to f/
- help now: (none)
- help new: The narrowest aperture to include, as the f-number, for example 8. Blank means no limit.

### iso_from
- label now: ISO from  -> new: keep
- help now: (none)
- help new: The lowest ISO to include. Blank means no lower limit.

### iso_to
- label now: to  -> new: ISO to
- help now: (none)
- help new: The highest ISO to include. Blank means no upper limit.

### faster_than
- label now: Shutter faster than  -> new: keep
- help now: Written as a camera says it: 1/250, or 2 for two seconds.
- help new: Only shutter speeds faster than this, written as a camera shows it: 1/250, or 2 for two seconds. Blank means no limit.

### slower_than
- label now: or longer than  -> new: Shutter slower than
- help now: (none)
- help new: Only shutter speeds slower than this, written as a camera shows it: 1/30, or 2 for two seconds. Blank means no limit.

### stars_from
- label now: Stars from  -> new: keep
- help now: (none)
- help new: The lowest rating to include, 0 to 5. Blank means no lower limit.

### stars_to
- label now: to  -> new: Stars to
- help now: (none)
- help new: The highest rating to include, 0 to 5. Blank means no upper limit.

### colour
- label now: Colour label  -> new: keep
- help now: (none)
- help new: Only photos carrying this colour label. Any means no colour filter.

### tags
- label now: Tags  -> new: keep
- help now: Comma separated.
- help new: Only photos carrying these tags, separated by commas. Blank means no tag filter.

### all_tags
- label now: All the tags  -> new: Must have all tags
- help now: Off, a photo matches if it carries any one of them; on, it has to carry every one.
- help new: A photo must carry every tag listed. Off, carrying any one of them is enough.

### located
- label now: Location  -> new: keep
- help now: (none)
- help new: Whether a photo must have a location. Either means no filter.

### country
- label now: Country  -> new: keep
- help now: Needs the place table - the Place names tab imports it.
- help new: Only photos taken in this country. Needs the place table from the Import place names tab. Blank means any country.

### city
- label now: City or town  -> new: keep
- help now: (none)
- help new: Only photos taken in or near this city or town. Needs the place table from the Import place names tab. Blank means anywhere.

### skip_here
- same as blur.skip_here

## setup  (title: Setup)
summary:
- now: The three trees, and what counts as a bracket. Set once, read everywhere.
- new: Sets the trees, the bracket rules and the defaults that every tool reads.

### library
- label now: The library  -> new: Library
- help now: Everything else mirrors this one. Never changed by any task except the ones you point at it directly.
- help new: The top folder of your photos. Every other tree mirrors its shape. No tool changes it unless you point that tool at it.

### raw
- label now: The RAW tree  -> new: RAW tree
- help now: Shaped like the library. Must not be inside it. It does not have to exist yet - it is made the first time RAWs are moved.
- help new: The top folder for RAW files, shaped like the library. It must not be inside the library. It does not need to exist yet: it is made the first time RAW files are moved.

### previews
- label now: The previews tree  -> new: Previews tree
- help now: Disposable. Synced to a tablet for rating, then remade whenever.
- help new: The top folder for previews, shaped like the library. It is disposable: synced to the tablet for rating, and remade whenever needed.

### video
- label now: The video tree  -> new: Video tree
- help now: Shaped like the library, for the clips every camera also shoots. A minute of 4K is a gigabyte and half the tools here skip video silently, so it is worth having out of the way. Leave blank until you want it.
- help new: The top folder for videos, shaped like the library. Videos are large and many tools skip them, so keeping them apart helps. Blank until you want it.

### server_name
- label now: Call this machine  -> new: Server name
- help now: What a phone or a desktop client shows this server as - "NAS", "the PC". Blank uses the machine's own name.
- help new: The name a phone or desktop client shows for this server, for example NAS. Blank uses the machine's own name.

### discovery
- label now: Let clients find it  -> new: Discoverable on the network
- help now: A client on the same network shouts once and every server answers with its name and port, so nobody has to type an address. The answer says a server exists and whether it needs a password - never anything about the photos. It cannot cross a VPN or a different subnet, where the address still has to be typed.
- help new: Lets a client on the same network find this server without typing an address. The answer gives only the server's name and port and whether it needs a password, nothing about the photos. It does not cross a VPN or another subnet. On by default.

### public_port
- label now: Port clients should use  -> new: Public port
- help now: Only when it differs from the port this is listening on. In a container the mapping is 8842:8080 and 8080 is the only number this process can see, so leaving this at 0 would send every phone to a port that is not open. Set it to the number you reach it on.
- help new: The port clients should connect to, when it differs from the port the app listens on. 0 to 65535, default 0, which means the same port. In a container mapped 8842:8080 the app only sees 8080, so set 8842 here.

### key_info
- label now: Key for shot details  -> new: Shot details key
- help now: One letter. Shows the camera, lens, aperture, shutter and ISO over the photograph. Blank turns it off.
- help new: The key that shows camera, lens, aperture, shutter and ISO over the photo in the viewer. One letter, default i. Blank turns it off.

### key_histogram
- label now: Key for the histogram  -> new: Histogram key
- help now: One letter. Shows the histogram over the photograph, and pressing it again changes what it draws. Blank turns it off.
- help new: The key that shows the histogram over the photo in the viewer. One letter, default h. Pressing it again changes what the histogram draws. Blank turns it off.

### quick_tags
- label now: Quick tags  -> new: keep
- help now: Up to five words, separated by commas. They go on Shift and 1 to 5, and the same key takes the tag off again - for the handful of words you put on four hundred photographs an evening. Press ? in the viewer for the whole list of keys.
- help new: Up to five tags, separated by commas, put on Shift+1 to Shift+5 in the viewer. Pressing the same key again removes the tag. Press ? in the viewer for every key.

### develop_raw_at
- label now: Send RAW at  -> new: Send RAW from (stars)
- help now: -1 never sends a RAW. A negative is fifty megabytes, so this is usually the top rating only.
- help new: same as develop.raw_at_or_above, without the final "From Setup by default."

### develop_jpeg_at
- label now: Send JPEG at  -> new: Send JPEG from (stars)
- help now: -1 never sends a JPEG. Lower than the RAW threshold gives you the shots worth a look without the weight of the negatives.
- help new: same as develop.jpeg_at_or_above, without the final "From Setup by default."

### develop_colour
- label now: Only this colour  -> new: keep
- help now: Narrows the whole thing to one colour. What each one means is on the Colour meanings tab.
- help new: Send to develop sends only photos carrying this colour label. Blank means any colour. The meaning of each colour is set on the Colour meanings tab.

### develop_tags
- label now: Only photos tagged  -> new: keep
- help now: Comma separated. A level of a hierarchy matches: Italy finds Travel|Italy|Rome. Blank for no tag filter at all.
- help new: same as develop.tags, without the final "From Setup by default."

### develop_tags_rule
- label now: and those tags  -> new: What the tags do
- help now: (none)
- help new: same as develop.tags_rule, without the final "From Setup by default."
- choices: same as develop.tags_rule

### develop_tags_all
- label now: Must have all tags  -> new: keep
- help now: (none)
- help new: A photo must carry every tag listed in Only photos tagged. Off, carrying any one of them is enough.

### develop_labels
- label now: Obey colours too  -> new: Follow colour labels
- help now: A colour says what you want DONE with a photograph, which a rating cannot. Off, only ratings and tags decide.
- help new: same as develop.labels, without the final "From Setup by default."

### develop_prune
- label now: Take finished back  -> new: Remove finished copies
- help now: What makes the develop tree temporary: it holds what is still waiting, not everything that ever qualified.
- help new: same as develop.prune, without the final "From Setup by default."

### filed_where
- label now: Where exports land  -> new: Export destination
- help now: The export folder that syncs back from the tablet is ONE flat folder - Lightroom on Android has no idea what shape your library is. So each export is matched to its original by capture time, camera and name, and this says where it then goes.
- help new: Where File developed puts each export once its original is found. The export folder from the tablet is one flat folder, so each export is first matched to its original by capture time, camera and name. A subfolder keeps the shoot folder for camera files only.
- choices: same as filed.where

### filed_into
- label now: Called  -> new: Subfolder name
- help now: A NAME, not a path - it is joined onto whichever shoot each export belongs to. Call it Developed, Curated, anything: whatever it is, it is added to the folders this app leaves out of its own scanning, so a folder of exports is never read as a second copy of every photograph in the shoot.
- help new: The name of the subfolder, default Developed. A name, not a path: it is made inside whichever shoot each export belongs to. The name is also added to the folders the app never scans, so exports are not read as originals.

### filed_tidy_resync
- label now: Clear re-synced copies  -> new: keep
- help now: The export folder is a one-way sync: the tablet keeps its copy and can send it back after filing has dealt with it. On, such a copy is removed from the EXPORT folder - never from the library, and never the one already filed.
- help new: same as filed.tidy_resync, without the final "From Setup by default."

### filed_keep
- label now: Keep the export  -> new: keep
- help now: Off means the export is moved, which empties the folder ready for the next round. On copies instead, and the folder keeps filling.
- help new: same as filed.keep_exports, without the final "From Setup by default."

### develop
- label now: The develop tree  -> new: Develop tree
- help now: A working set: the shots worth developing, copied out of the library keeping its shape. Sync THIS folder to the tablet. It empties itself as you finish things.
- help new: The top folder for photos being developed. Send to develop copies qualifying photos here, keeping the library's shape, and removes them when they are finished. Sync this folder to the tablet.

### inbox
- label now: Lightroom's export folder  -> new: keep
- help now: The one folder Lightroom on the tablet exports into, synced back here. Keep it outside the library, or every export is read as an original photograph.
- help new: same as filed.inbox, without the final "From Setup by default."

### preview_profile
- label now: Preview size  -> new: keep
- help now: A named size wins over the two boxes below, so picking Medium and leaving a stale 3200 in the custom box cannot quietly give you Large. Choose Custom to use them.
- help new: The size and JPEG quality Make previews uses. A named size wins over the two boxes below, so a stale custom value cannot change it. Choose Custom to use the boxes.
- choices: same as previews.profile for `small`, `medium`, `large` and `custom`

### preview_long_edge
- label now: Custom longest side (pixels)  -> new: keep
- help now: (none)
- help new: same as previews.long_edge

### preview_quality
- label now: Custom JPEG quality  -> new: keep
- help now: (none)
- help new: same as previews.quality

### thumb_keep
- label now: Small pictures kept  -> new: Thumbnails kept
- help now: Making a small picture of a photograph means decoding it; keeping one costs about twenty kilobytes. Fewer than there are photographs means browsing past the ceiling throws the earliest ones away, and going back decodes them all again.
- help new: How many thumbnails the app keeps for browsing. 500 to 400,000, default 60,000. Each one costs about twenty kilobytes. Fewer than you have photos means the oldest are thrown away as you browse and decoded again later.

### bracket_group
- label now: Group brackets  -> new: keep
- help now: One preview per set, a star that reaches every frame, and a set kept or put aside whole. Read by previews, ratings and cull.
- help new: Treats a bracket set as one photo in Make previews, Rating & tags and Cull by rating: one preview per set, one rating for every frame, and the set kept or moved together. On by default.

### bracket_gap
- label now: Max gap (seconds)  -> new: Largest gap (seconds)
- help now: A bracket fires in one burst. Widen this only if your camera is slow between frames.
- help new: The longest pause, in seconds, between two frames of one bracket set. 1 to 60, default 3. Increase it only if your camera is slow between frames.

### bracket_min_set
- label now: Smallest set  -> new: Smallest set (frames)
- help now: (none)
- help new: The fewest frames that count as a bracket set. 2 to 9, default 3.

### bracket_max_set
- label now: Largest set  -> new: Largest set (frames)
- help now: (none)
- help new: The most frames that count as one bracket set. 3 to 15, default 9. A longer run of frames is not a set.

### bracket_probable
- label now: Include hand-bracketed  -> new: keep
- help now: Turning the dial yourself leaves every frame at bias 0 and no flag, so nothing in the file separates it from three deliberate exposures of a changing scene. Off unless you have looked at what the check below finds.
- help new: Also counts sets with no exposure bias recorded, which is what hand-bracketing leaves. Nothing in the file separates such a set from three ordinary photos taken seconds apart, so leave it off until Test folder shows what it finds. Off by default. Thin brackets only sees these sets when this is on.

### exclude
- label now: Skip everywhere  -> new: keep
- help now: PATHS, not names - your phone's photos, the scanned negatives, a video folder kept beside the library. The box above is for names like @eaDir that mean 'not a photograph of yours anywhere'; this is for one place you want the workflow to leave alone. Anything inside an excluded folder is excluded too, in EVERY feature, and every run that meets one says so rather than quietly reporting a smaller library. A flow can add more of its own on the Flows tab.
- help new: Folders every tool leaves alone, as paths, for example your phone's photos, your scans or a video folder beside the library. Everything inside each one is left alone too, and every run that meets one says so. Folder names such as @eaDir go in Folder names never scanned instead. A flow can add more on the Flows tab.

### ignore
- label now: Folder names never scanned  -> new: keep
- help now: Other apps keep their working files inside photo folders - PhotoPrism, Immich, Synology's own @eaDir indexes, #recycle. Those are not your photos: counting them makes every number wrong, and letting a task move one can damage the other app. Names separated by commas, not paths, so one entry covers every shoot. The built-in ones are always skipped whatever is in this box.
- help new: Folder names, separated by commas, that no tool ever reads. Other apps keep working files inside photo folders, such as PhotoPrism, Immich, Synology's @eaDir and #recycle. One name covers every shoot. The built-in names are always skipped whatever is in this box.

### bracket_tag
- label now: Bracket keyword  -> new: Bracket tag
- help now: Written by 'Find brackets' onto every frame of a set, and by 'Make previews' onto the preview that stands for one - so a bracket is one search away wherever you are looking. In one place so the two cannot write different words and leave half a library findable. Blank writes nothing.
- help new: The tag Find brackets writes on every frame of a set, and Make previews writes on the preview of a set. Default bracket. One setting, so the two cannot write different words. Blank writes nothing.

### place_names
- label now: Rename places  -> new: keep
- help now: One per line: 'Marrakesh = Marrakech'. Used when sorting into country and city folders, and matched against a town or a country. Sorting lists every name it found, so the usual way to fill this in is to look once and edit it there.
- help new: same as bydate.place_names, with "Sort into folders lists every name found" and without the final "From Setup by default."

### check
- label now: Check against  -> new: Test folder
- help now: Nothing is written. Point it at a shoot you remember and see whether the sets it draws are the sets you actually shot.
- help new: A shoot to test the bracket rules on. Nothing is written. Apply shows the sets the rules find, so you can compare them with what you shot.

## space  (title: Storage)
summary:
- now: Where the disk went, folder by folder and tree by tree - and what could be freed. Nothing is written.
- new: Shows how much disk each folder and tree uses, and what could be freed. Nothing is changed.

### folder
- label now: The library  -> new: Library
- help now: Read, never written.
- help new: The library to measure. It is read, never written.

### depth
- label now: How far down  -> new: Levels to list
- help now: 1 lists the years, 2 the shoots in them. Each row carries everything below it, so nothing is counted twice.
- help new: How many folder levels to list. 1 to 6, default 2. 1 lists the years, 2 the shoots in them. Each row includes everything below it, so nothing is counted twice.

### most
- label now: How many rows  -> new: Rows to show
- help now: The biggest this many. The rest are summed in a note.
- help new: How many of the largest folders to list. 5 to 500, default 40. The rest are added up in one note.

### with_raw
- label now: Count the RAWs  -> new: Count RAW files
- help now: The RAW tree from Setup. Usually most of the space.
- help new: Includes the RAW tree from Setup, usually most of the space. On by default.

### with_previews
- label now: Count the previews  -> new: Count previews
- help now: Small each, but one per photograph.
- help new: Includes the previews tree from Setup. Each preview is small, but there is one per photo. On by default.

### with_video
- label now: Count the video  -> new: Count videos
- help now: The video tree from Setup.
- help new: Includes the video tree from Setup. On by default.

### skip_here
- same as blur.skip_here

## tags  (title: Tag photos)
summary:
- now: Put tags on a whole folder, or on the photographs that match a rule - the half of a rating or a colour that other programs can actually search.
- new: Adds tags to every photo in a folder, or only to the photos that match a rule.

### folder
- label now: Folders to tag  -> new: keep
- help now: Whole trees at a time. Safe to run over everything: tags are only ever added, never replaced or removed.
- help new: The folders to tag. Every photo inside each one is considered. Safe to run over everything, because tags are only added, never replaced or removed.

### words
- label now: Tags to add  -> new: keep
- help now: Separated by commas. 'Barcelona 2024, travel, family' is three tags. Anything already on the photograph is not written again.
- help new: The tags to write, separated by commas. 'Barcelona 2024, travel, family' is three tags. A tag already on a photo is not written again.

### which
- label now: Which photos  -> new: keep
- help now: A rule reads what is already on the photograph, so it can be run again as you rate and colour more of them.
- help new: The rule that picks the photos to tag. A rule reads what is already on the photo, so it can be run again as you rate and label more of them.
- choices: `all`: Every photo in the folder -> keep; `stars`: Rated this many or more -> keep; `exact`: Rated exactly this many -> keep; `unrated`: Unrated only -> keep; `colour`: Carrying one colour -> Carrying one colour label; `missing`: Missing its colour's tags -> keep; `lens`: Shot on a lens -> keep; `focal`: In a focal range -> keep

### stars
- label now: Stars  -> new: keep
- help now: Used by the two rules about ratings, and ignored by the others.
- help new: The rating the two rating rules compare with. 1 to 5, default 4. Ignored by the other rules.

### colour
- label now: Colour  -> new: Colour label
- help now: Used by 'Carrying one colour', and ignored by the others.
- help new: The colour label for the 'Carrying one colour label' rule. Ignored by the other rules.

### lens
- label now: Lens name contains  -> new: keep
- help now: Used by 'Shot on a lens'. Part of the name is enough - '25/F1.7' finds 'LUMIX G 25/F1.7'. Storage on the Library tab lists the exact names your cameras write.
- help new: Text the lens name must contain, for the 'Shot on a lens' rule. Part of the name is enough: 25/F1.7 finds LUMIX G 25/F1.7. The Storage tab lists the exact lens names your cameras write.

### focal
- label now: Focal range  -> new: keep
- help now: Used by 'In a focal range'. Full-frame equivalent where the camera records it - so 25mm on the GH4 counts as 50mm - and the number on the lens where it does not.
- help new: The focal length range for the 'In a focal range' rule, default Normal (36-70mm). The full-frame equivalent is used where the camera records it, so 25mm on a GH4 counts as 50mm. Otherwise the number on the lens is used. The ranges are set in Setup > Chart bands.

### from_colour
- label now: Add the colour's tags  -> new: keep
- help now: As well as anything you typed, write what that photograph's colour MEANS - the name and tags you gave it in Setup. This is the repair for colours put on by Lightroom or the tablet, which could not have written them.
- help new: Also writes the meaning and extra tags of each photo's colour label, from Setup > Colour meanings. This repairs colour labels set by Lightroom or the tablet, which could not write those tags. Off by default.

### with_raw
- label now: The same shoot's RAWs  -> new: Tag their RAW files
- help now: The same folder in the RAW tree, judged by the same rule. Only that folder - never the whole tree.
- help new: Also tags the matching folder in the RAW tree, by the same rule. Only that folder, never the whole tree. On by default.

### with_previews
- label now: The same shoot's previews  -> new: Tag their previews
- help now: So the tablet copy is findable by the same words as the photograph it came from.
- help new: Also tags the matching folder in the previews tree, so the tablet copy is found by the same words. Off by default.

### in_file
- label now: Write into the photo  -> new: keep
- help now: A sidecar is what Lightroom and darktable read and the only thing a RAW can carry. Inside the JPEG is what Synology Photos and Explorer look at. Both, unless you have a reason.
- help new: same as blur.in_file, with "the tags" in place of "the tag"

### skip_here
- same as blur.skip_here

## thin  (title: Thin brackets)
summary:
- now: Keep one frame of each bracket set and put the spares aside - the frame you rated, or the metered one.
- new: Keeps one frame of each bracket set, the rated or the metered one, and moves the rest to _Culled.

### folder
- label now: The folder to thin  -> new: Folder to thin
- help now: A shoot, or the whole library. Only bracket sets are touched; a loose frame is never one of them.
- help new: The folder to thin, a shoot or the whole library. Only bracket sets are touched. A single frame is never moved.

### probable
- label now: Include probable sets  -> new: keep
- help now: Off by default and worth leaving off until you have looked. A probable set is frames seconds apart with no exposure bias recorded - hand-bracketing, or three deliberate exposures of a changing scene, and nothing in the file tells them apart.
- help new: Also thins probable sets: frames seconds apart with no exposure bias recorded, which could be hand-bracketing or three deliberate photos of a changing scene. Off by default. Look at the list first. Probable sets are only found when Setup > Include hand-bracketed is on. (check: with that Setup flag off, app/grouping.sets_for never returns a probable set, so this box has no effect. Either the text above stays, or the code should read this box instead.)

### mirror
- label now: Mirror Setup's trees  -> new: Trees from Setup
- help now: The spare frame's negative and preview are put aside with it. Leaving them behind gives you three negatives for one JPEG and a previews tree showing photographs that are no longer there.
- help new: same as blur.mirror (check: the old help says the RAW file and preview are left behind without it. They move whenever their tree box is filled.)

### raw
- label now: The RAW tree  -> new: RAW tree
- help now: (none)
- help new: The top of the RAW tree. A spare frame's RAW file is moved to the matching _Culled folder here. Blank leaves RAW files alone, which gives several RAW files for one kept JPEG. Ignored while Trees from Setup is on.

### previews
- label now: The previews tree  -> new: Previews tree
- help now: (none)
- help new: The top of the previews tree. A spare frame's preview is moved to the matching _Culled folder here. Blank leaves previews alone, so the tablet still shows the spare frames. Ignored while Trees from Setup is on.

### skip_here
- same as blur.skip_here

## tidy  (title: What can be cleaned up)
summary:
- now: Everything sitting in this library that you have already decided against - counted, sized and dated. Nothing is touched.
- new: Counts, sizes and dates everything in the library you have already decided against. Nothing is changed.

### folder
- label now: Tree to look through  -> new: Folders to check
- help now: The piles can be anywhere inside it - a _Culled folder sits beside the shoot it came from, not in one place.
- help new: The folders to look through. Piles can be anywhere inside them: a _Culled folder sits beside the shoot it came from.

### empty
- label now: Empty folders  -> new: keep
- help now: What reorganising leaves behind. They show up in every folder picker forever and nothing about looking at photographs will ever tell you they are there.
- help new: Also counts folders with nothing in them, which reorganising leaves behind and every folder picker keeps showing. On by default.

### leftovers
- label now: Thumbnail-only folders  -> new: keep
- help now: @eaDir, Thumbs.db and the like, where there is nothing else in the folder at all. A folder with one photograph and an @eaDir is not litter.
- help new: Also counts folders that hold only system files such as @eaDir or Thumbs.db and nothing else. A folder with one photo and an @eaDir is left out. Off by default.

### raw
- label now: Also the RAW tree  -> new: RAW tree
- help now: Culled negatives are the big ones.
- help new: The top of the RAW tree, so its piles are counted too. Culled RAW files are the largest. Blank leaves it out.

### previews
- label now: Also the previews tree  -> new: Previews tree
- help now: (none)
- help new: The top of the previews tree, so its piles are counted too. Blank leaves it out.

### develop
- label now: Also the develop tree  -> new: Develop tree
- help now: (none)
- help new: The top of the develop tree, so its piles are counted too. Blank leaves it out.

### video
- label now: Also the video tree  -> new: Video tree
- help now: (none)
- help new: The top of the video tree, so its piles are counted too. Blank leaves it out.

### skip_here
- same as blur.skip_here

## timeline  (title: Location timeline)
summary:
- now: Build one record of where you have been from your photographs and the imported Google Timeline, keep them side by side, and export the two together as GeoJSON and CSV.
- new: Builds one record of where you have been from your photos and the Google Timeline, and exports it.

### folders
- label now: Photographs to read  -> new: Folders to read
- help now: Anything underneath these is read - a phone dump, the library, or both. Only the photographs the index says carry a position are opened.
- help new: The folders of photos to read positions from: a phone dump, the library or both. Only photos the index says have a position are opened. Blank means the library from Setup.

### use_photos
- label now: From your photographs  -> new: Use your photos
- help now: Each one gives a position, the satellite time and the camera's own clock - which is a fix with its timezone attached, from a source Google never saw.
- help new: Takes positions from your photos. Each one gives a position, the GPS time and the camera's own clock with its time zone. On by default.

### use_timeline
- label now: From the imported Timeline  -> new: Use the imported Timeline
- help now: The export already brought in by 'Import timeline'. It is read, never changed.
- help new: Takes positions from the Timeline brought in by Import Google Timeline. It is read, never changed. On by default.

### out
- label now: Export into  -> new: Export folder
- help now: The folder the files are written into. Leave it blank to build the photo timeline and write no files.
- help new: The folder the export files are written into. Blank builds the photo timeline and writes no files.

### name
- label now: File name  -> new: keep
- help now: Without the extension - one file per format you ask for.
- help new: The name of the export files, without an extension. Default location-timeline. One file is written per format chosen below.

### as_geojson
- label now: GeoJSON  -> new: keep
- help now: Points with everything they know, plus a line per journey. What a map, QGIS and most code read.
- help new: Writes a GeoJSON file: every position with everything known about it, plus one line per journey. Maps, QGIS and most code read it. On by default.

### as_csv
- label now: CSV  -> new: keep
- help now: One row per position, same facts, for a spreadsheet or something reading a million of them.
- help new: Writes a CSV file with one row per position and the same facts, for a spreadsheet or a script. On by default.

### keep_store
- label now: Keep the photo timeline  -> new: keep
- help now: Kept beside the imported one rather than merged into it, so Geotag can use both and nothing has to be re-imported to undo a mistake.
- help new: Saves the timeline built from your photos in the app's store, beside the imported Google Timeline and not merged into it. Geotag can then use both, and a mistake needs no re-import. On by default.

### gap
- label now: New journey after (minutes)  -> new: keep
- help now: A longer gap than this starts a new journey. Shorter and a traffic light splits a drive; longer and a morning at home joins onto the afternoon.
- help new: A pause longer than this many minutes ends one journey and starts the next. 1 to 1440, default 30. Too short, and a traffic light splits a drive. Too long, and a morning at home joins the afternoon.

### dedupe
- label now: Drop repeats  -> new: keep
- help now: The same moment in the same place, recorded by both. Left in, anything counting crossings counts them twice.
- help new: Keeps only one record when both sources recorded the same moment in the same place. Off, such repeats are kept and counted twice. On by default.

### apart
- label now: Repeats are within (seconds)  -> new: keep
- help now: (none)
- help new: Two records closer in time than this many seconds count as the same moment. 0 to 600, default 30. Only used when Drop repeats is on.

### since
- label now: Only from  -> new: From date
- help now: A date - 2019-01-01.
- help new: The earliest date to include, for example 2019-01-01. Blank means from the first record.

### until
- label now: Only to  -> new: To date
- help now: (none)
- help new: The latest date to include, for example 2024-12-31. Blank means to the last record.

### skip_here
- same as blur.skip_here

## undo  (title: Put a run back)
summary:
- now: Move the files of one past run back to where it found them - as a plan you read first, refusing anything that has moved since.
- new: Moves the files of one past run back to where they were. Anything moved since is refused.

### no
- label now: Which run  -> new: keep
- help now: The number on the left of the row in History - #412 is 412. Pressing Put it back on a row fills this in.
- help new: The run number shown at the left of a row in History: #412 is 412. Pressing Put it back on a row fills this in.

### run
- label now: Exactly when  -> new: Run time
- help now: The moment the run finished, to the millisecond. History's own button sends this, because it names one run even if the numbers have been edited by hand. Nothing worth typing.
- help new: The exact time the run finished. The Put it back button in History fills this in for you. You do not need to type it.

## unlocate  (title: Strip location)
summary:
- now: Take the location off a folder of photographs - for when the clock was wrong and they were pinned to the wrong place.
- new: Removes the location from every photo in a folder, for when it was pinned to the wrong place.

### folder
- label now: Folders  -> new: Folders to strip
- help now: The photographs whose location should go. Everything inside each folder is included.
- help new: The folders whose photos lose their location. Everything inside each one is included.

### with_raw
- label now: The same shoot's RAWs  -> new: Strip their RAW files
- help now: The same folder in the RAW tree, so the negative's sidecar does not keep the wrong place. Only that folder - never the whole tree.
- help new: Also removes the location from the matching folder in the RAW tree, in each RAW file's sidecar. Only that folder, never the whole tree. On by default.

### with_previews
- label now: The same shoot's previews  -> new: Strip their previews
- help now: The same folder in the previews tree, so the tablet copy loses it too.
- help new: Also removes the location from the matching folder in the previews tree, so the tablet copy loses it too. On by default.

### skip_here
- same as blur.skip_here

## unpair  (title: Separate RAWs)
summary:
- now: Move RAWs out of the library into a tree that mirrors it.
- new: Moves RAW files out of the library into a RAW tree with the same folder shape.

### folder
- label now: Folder to separate  -> new: keep
- help now: A single shoot, or the whole library.
- help new: The folder to move RAW files out of, a shoot or the whole library.

### mirror
- label now: Mirror Setup's trees  -> new: Trees from Setup
- help now: On, the RAW and previews trees come from Setup and the position inside them is worked out from the library - so a shoot always lands where unpairing the whole library would have put it, and there is nothing to type or get wrong. Turn it off only to send this one run somewhere else.
- help new: same as blur.mirror

### raw
- label now: The RAW tree  -> new: RAW tree
- help now: Created if it is not there. Must not be inside the library.
- help new: The top of the RAW tree. It is made if it does not exist. It must not be inside the library.

### unpaired
- label now: Move lone RAWs  -> new: Move lone RAW files
- help now: Off by default: those are the only copy of that shot, and moving one leaves a hole in the folder you are making shareable.
- help new: Also moves RAW files that have no JPEG. Off by default: a lone RAW file is the only copy of that photo, and moving it leaves a gap in the folder.

### copy
- label now: Copy, don't move  -> new: Copy instead of move
- help now: Off, the RAWs are MOVED and the library is left holding only photographs - which is the point of separating them. On, they are copied and the library is untouched, which costs the disk space twice and is how you try this out without committing to it.
- help new: Copies RAW files into the RAW tree and leaves the library untouched. Off by default: RAW files are moved, which is the point of separating them. Copying uses the disk space twice and is a way to try the tool out.

### tidy
- same as cull.tidy

### skip_here
- same as blur.skip_here

## videos  (title: Separate video)
summary:
- now: Move clips out of the library into a video tree with the same shape.
- new: Moves videos out of the library into a video tree with the same folder shape.

### folder
- label now: Folder to scan  -> new: keep
- help now: A shoot, or the whole library. Only video is moved; every photograph is left exactly where it is.
- help new: The folder to move videos out of, a shoot or the whole library. Only videos move. Every photo stays where it is.

### mirror
- label now: Mirror Setup's trees  -> new: Trees from Setup
- help now: On, the video tree comes from Setup and each clip's position is measured from the library - so taking video out of one shoot puts it exactly where taking it out of the whole library would have, and the two cannot build different trees.
- help new: same as blur.mirror, with "videos moving" in place of "RAW files or previews moving"

### video
- label now: The video tree  -> new: Video tree
- help now: Made if it is not there. Must not be inside the library, or the clips would be found again on the next run in their new home and moved again.
- help new: The top of the video tree. It is made if it does not exist. It must not be inside the library, or the videos would be found and moved again on the next run.

### by_time
- label now: File by shoot  -> new: keep
- help now: A clip shot during the Spain trip goes to the Spain folder of the video tree, wherever the clip itself is sitting now - which is what sorts out a card dump. When every photograph was taken comes from the index, so it costs almost nothing once the library has been read; before that, the photographs are read once and remembered.
- help new: Puts each video in the video tree folder of the shoot taken at the same time, wherever the video sits now. This sorts out a card dump. The photo times come from the index, so it is fast once the library has been read. On by default.

### near_hours
- label now: Join a shoot within  -> new: Shoot window (hours)
- help now: Hours. A shoot that ended at ten and a clip at half past eleven are the same evening; a clip from the next afternoon is not. Inside a shoot's own hours always counts, whatever this says.
- help new: How many hours after a shoot ended a video still belongs to it. 0 to 240, default 12. A video taken during the shoot always belongs to it. Use the same number in Re-mirror video.

### shape
- label now: Otherwise file by  -> new: Fallback folders
- help now: The fallback, in the video tree. 'The folder it is in now' mirrors its current position, which is what this task did before it could read a clip's capture time.
- help new: Where a video goes when no photos were taken near the same time. 'The folder it is in now' keeps the video's current position, mirrored into the video tree.
- choices: `year_month`: 2022 / 07 -> keep; `year`: 2022 -> keep; `flat_month`: 2022-07 -> keep; `flat_day`: 2022-07-14 -> keep; `same`: the folder it is in now -> The folder it is in now

### shift_minutes
- label now: Shift clip times by  -> new: Shift video times (minutes)
- help now: Minutes. Only for cameras that write the movie header in UTC while the photographs are local: +180 makes a UTC+3 clip line up with the photographs beside it. Left at 0 the time is used exactly as the file states it, and the row says when the file did not state a timezone.
- help new: same as bydate.shift_minutes

### skip_here
- same as blur.skip_here

---

## Group names

Every distinct group name in the dump (57), with the tools that use it. "keep" means it already is a one-to-three-word noun. Where a form had both "Advanced" and another catch-all, the guide says to keep only one; "Advanced" stays because the registry folds it by default.

| Group now | Used by | New |
|---|---|---|
| Advanced | blur, compare, cull, duplicates, label, ratings, tags, remirror, remirror_previews, unpair, geotag, pin, previews, filed, library, password, space, retime (keep_originals is under Safety) | keep |
| Blue | labels | keep |
| Brackets | cull, develop, previews, ratings, setup | keep |
| Camera and lens | search | keep |
| Colours | develop | Colour labels |
| Compared against | library | Trees compared |
| Exposure | search | keep |
| Green | labels | keep |
| How careful | cleanup | Safety |
| How it decides | remirror_video | Matching |
| Journeys | timeline | keep |
| Keys in the viewer | setup | Viewer keys |
| Marks | search | Rating and tags |
| On the network | setup | Network |
| Or shift by | retime | Fixed amount |
| Other trees | cleanup, tidy | keep |
| Pattern | bydate | keep |
| Places | bydate | keep |
| Previews | setup | keep |
| Purple | labels | keep |
| Red | labels | keep |
| Safety | geotag, pin, retime | keep |
| Size and quality | previews | keep |
| Skip | every tool with skip_here | keep |
| Sources | geotag | keep |
| Tablet workflow | setup | keep |
| Tags | develop | keep |
| The correction | retime | Correction |
| The flow | automation | Flow |
| The other trees | delfolder, label, tags, unlocate | Other trees |
| The rule | tags | Rule |
| Thresholds | cull | keep |
| Video | bydate | Videos |
| What counts as blurry | blur | Thresholds |
| What counts | duplicates | Matching |
| What follows | rename | Companion folders |
| What goes with it | blur, cull | Companion files |
| What it is | search | File |
| What moves with them | bydate, thin | Companion files |
| What to carry | ratings | What to copy |
| What to correct | retime | Folders |
| What to leave alone | setup | Skipped folders |
| What to look for | exposure | Checks |
| What to remove | cleanup | Piles |
| What to send | develop, setup | keep |
| What to write | exposure, timeline | Tags (exposure), Export files (timeline) |
| What travels | files | Companion files |
| When | search | Date |
| Where it comes from | timeline | Sources |
| Where the line is | exposure | Thresholds |
| Where | develop, search | Trees (develop), Place (search) |
| Which folder | videos | Destination |
| Which to keep | duplicates | keep |
| Which trees | space | Trees |
| Yellow | labels | keep |
| Your trees | setup | Trees |

Notes on groups:
- `exposure.skip_here` sits in the group "What to write" today. It should move to "Skip" like every other skip_here.
- Three tools (bydate, thin, files, blur, cull) each name the same idea differently: "What moves with them", "What travels", "What goes with it". One name, "Companion files", for all of them.
- "Marks" (search) is the only place the word is used for ratings and colour labels; the glossary bans it.
- "Thresholds" is proposed for blur and exposure as well as cull, since each of those groups holds the numbers a photo is compared with.

