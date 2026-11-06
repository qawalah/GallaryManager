# Roadmap

What is planned and not built yet. Each item says what it is for, what it
would look like to the person using the app, and where the code would go, so
whoever picks it up starts from a decision rather than a blank page.

## Next

### Update Pillow from inside Photo Manager

**Why.** Pillow draws every preview and thumbnail. The Windows program ships
one copy of it (`windows/wheels/`, installed by Install.bat without the
internet), and the NAS installs one on first start (`nas/run.py`,
`ensure_pillow`). Newer Pillow releases fix security problems in image
decoders and read new formats. Today the only way to take one is a command
line, which is exactly what this app exists to spare people.

**What it looks like.**

- A **Components** card in Setup, showing which Pillow is running, which
  copy shipped with the app, and, when asked ("Check for updates", never on
  its own), the newest release on PyPI.
- **Update Pillow** downloads and installs the newer one as an ordinary
  background job, with the bar of everything running showing its progress. It
  follows the app's four steps: it says what it will do (from version X to Y,
  where, how big), then does it, then says what happened.
- A running program cannot swap a library it has already loaded, so the card
  then offers **Restart Photo Manager**. On a PC that is the tray's program
  restarting itself. On the NAS it is the same exit the container already
  restarts from.
- **Go back to the bundled version** reinstalls the shipped copy from
  `windows/wheels/` with no internet, in case a new release misbehaves.
- With a password set, only a signed-in person can update. With no internet,
  it says so plainly and changes nothing.

**Where the code goes.**

| Part | Place |
|---|---|
| Versions and the pip command for each kind of copy | `core/components.py` (new), tested without a network |
| `/api/components` (read) and the update/restore job | `app/server.py`, reusing the background-job machinery |
| Restart | `core/desktop.py` for the PC (start a new copy, then `desktop.quit`), `nas/run.py` for the container |
| The card | a new `app/web/library/js/NN-components.js` piece, so it does not collide with other UI work |
| Tests | `tests/test_components.py` |

**Open questions.** Should updates go into the user's own Python
(`pip --user`, as Install.bat does) or into a folder of the app's own under
`%LOCALAPPDATA%\PhotoManager`? The second keeps Photo Manager from changing
what other Python programs on the PC see, and is what the NAS already does.

### Stronger password storage

**Today** (`core/access.py`). There is one password for the app. It is never
stored, only a PBKDF2-HMAC-SHA256 hash of it: 240,000 rounds and a random
16-byte salt, in `access.json`. Signing in gives the browser a ticket in a
cookie that lasts 30 days. The cookie is HMAC-signed, HttpOnly and
SameSite=Strict. After 8 wrong tries, that address waits 5 minutes. That is a
sound base. The gaps:

- The work factor is below today's guidance (OWASP asks for 600,000 PBKDF2
  rounds), and PBKDF2 is cheap to attack with graphics cards. Python's own
  `hashlib.scrypt` is memory-hard and needs no package. Every stored hash
  records its own settings, so old hashes can be upgraded quietly the next
  time someone signs in, with no reset.
- `access.json` also holds the secret that signs the tickets. On the NAS the
  file is readable only by its owner (mode 600). On Windows that `chmod` does
  nothing, so any account on the PC could read it and forge a ticket. On
  Windows the secret should be encrypted with DPAPI (`CryptProtectData`,
  through ctypes, so no package): only the same Windows user can decrypt it.
- `PM_PASSWORD` in the NAS compose file is plain text, compared as it is. Let
  it take a hash instead (made by a small command, such as
  `python -m app.cli password`), and keep plain text only as a fallback with a
  warning in Setup.

A note on words: a password should be *hashed*, which is one-way and cannot
be turned back. Encryption, which can be undone with a key, is for things the
app must read back, like the signing secret.

**Where the code goes.** `core/access.py` (scrypt, upgrade on sign-in, the
compose hash), a new `core/secretbox.py` (DPAPI on Windows, file permissions
elsewhere), `app/cli.py` for the hashing command, and `tests/test_access.py`.

### HTTPS for the browser

**Today.** Plain HTTP only. On your own network, anyone who can watch the
traffic between a phone and the server can read the password as it is typed,
and can copy the sign-in cookie. `core/access.py` says so honestly. The cookie
is not marked Secure because, over HTTP, that would stop it working. On the
PC, the page opened on `127.0.0.1` never leaves the machine, so this matters
only for phones and other computers.

**What it would look like.** A **Secure connection (HTTPS)** card in Setup,
off by default, with three ways to turn it on:

1. **On the NAS, the recommended way:** DSM's own reverse proxy with a free
   Let's Encrypt certificate. This needs no code, only a page in
   `nas/README.md`. DSM renews the certificate, and the app keeps speaking HTTP
   inside the container.
2. **Bring your own certificate:** point Setup at a certificate file and a key
   file. The server wraps its socket with Python's own `ssl` module.
3. **A certificate made on the PC itself:** Windows can make one
   (PowerShell `New-SelfSignedCertificate`). Browsers will warn once, until it
   is trusted on each device. Setup says that plainly rather than hiding it.

Once HTTPS is on:

- the cookie gets the `Secure` flag;
- the server sends `Strict-Transport-Security`;
- plain HTTP on the network address redirects to HTTPS, while `127.0.0.1`
  keeps working for the tray's own window;
- discovery tells phones to use `https://`.

A bonus: phones only offer "Add to Home screen" as a real app (the service
worker) over HTTPS.

**Where the code goes.** `app/server.py` (`serve()` wraps the socket; the
cookie, header and redirect), `core/settings.py` (certificate paths),
`core/discovery.py` (the scheme), `core/desktop.py` (making the PC's
certificate, and the phone address the tray copies), `nas/README.md`, and
`tests/test_https.py`, which starts a server with a test certificate.

### The rest of the Windows port

The table under "Running fully on Windows" in `CLAUDE.md` lists the work.
Roughly in order: delete to the Windows Recycle Bin, hide the NAS-only
features (Permissions, Reindex), hide Windows' own system folders in the
folder picker, and case-insensitive sidecar names on NTFS. The first full test
run on a real PC (October 2026) found every remaining failure in one of these.

## Photo features

Four asked for in October 2026. Three of them run into the same wall, so the
order below starts with taking it down.

| Order | Item | Size | Why this order |
|---|---|---|---|
| 1 | Reading what is inside a RAW | small, core only | the next three need it |
| 2 | Geotagging RAWs | small | most of it is built already |
| 3 | Renaming photographs | medium | a new tab, no new UI |
| 4 | Previews of RAW-only shots | medium | needs 1, and changes to ratings |
| 5 | Folders made for each shoot | large | needs a table you can type into |

### Reading what is inside a RAW

**Why.** The app reads the capture time, camera and orientation of a JPEG
(`core/photo.read_capture`, from the JPEG's EXIF segment), but not of a RAW.
For a RAW, `core/exif.exif_block` finds nothing, so `read_capture` returns
only a time written in a sidecar. Pairing copes, because `core/pairs.find_partner`
falls back to the file name, and a RAW with a JPEG beside it borrows the
JPEG's facts. A RAW with no JPEG at all (a RAW-only shot) has no time, no
camera and no orientation as far as the app knows. Geotagging it, naming it
by date, and making a preview of it all need those three things.

**What it is.** Most RAW formats are TIFF files underneath: ARW, NEF, NRW,
CR2, DNG, PEF, SRW, ERF and 3FR start with `II*` or `MM*`, ORF and RW2 with a
variant of it. The TIFF reader in `core/exif.py` (`Tiff`) already decodes
directories, so reading IFD0 and the EXIF directory of a RAW is the same code
pointed at offset 0 of the file. CR3 (an ISO media container whose `CMT1`
and `CMT2` boxes hold the same TIFF directories) and RAF (a header pointing
at an embedded JPEG with ordinary EXIF) each need a short special case. Only
the directories are read, never the picture data.

While it is there, the same reader can note where the camera's own embedded
JPEG sits (`JpgFromRawStart`, `PreviewImageStart` and the like), which is what
RAW previews need.

**Where the code goes.** A new `core/rawfile.py`, used by `read_capture` and
`read_gps` for anything `kind()` calls `raw`. A sidecar time still wins over
the embedded one, as it does now. Tests in `tests/test_rawfile.py`, with one
small committed sample per format in `tests/fixtures/`, generated by
`tools/make_fixtures.py` as TIFF skeletons (a header and directories, no
picture), so no camera's files go into the repository.

### Geotagging RAWs (with an .xmp sidecar)

**Yes, this is possible, and it is the normal way to do it.** A RAW is never
opened for writing (`core/sidecar.py` explains why), so its location goes in a
small `.xmp` file beside it with the same name: `P1000123.RW2` gets
`P1000123.xmp` holding `exif:GPSLatitude` and `exif:GPSLongitude`. Lightroom
Classic, Bridge and Camera Raw read exactly that file, and this app already
writes ratings to RAWs the same way.

**Today.** Half of this is built. `core/exifwrite.write_gps_sidecar` writes the
location sidecar, and both **Geotag** and **Pin by hand** offer it as
"Sidecars only". `core/sidecar.write` merges into a sidecar that is already
there, so Lightroom's develop settings and keywords survive. What is missing
is that neither task ever looks at a RAW: `is_picture()` is true for JPEGs and
other images only, so RAWs are skipped without a word.

**What it would look like.** Two parts, the first one useful on its own.

1. **Carry the location to the RAW.** When Geotag or Pin places a JPEG, its
   RAW in the RAW tree (from Setup) is found by
   `find_partner`, exactly as the **Sync** tab of Rating & tags finds it, and gets a location
   sidecar. On by default whenever Setup names a RAW tree, with a plan line
   such as "412 RAWs get the same location in a sidecar". The JPEG's own
   location goes in the JPEG as it does now. This covers every shot taken as
   RAW+JPEG.
2. **Geotag RAW-only shots by their own time.** With the RAW reader above, a
   RAW has a capture time and can be matched against the Timeline or phone
   photos like any JPEG. Geotag gains "Include RAWs with no JPEG", and the
   rows say "sidecar" in the How column so it is clear nothing touched the RAW.

Smaller pieces that go with it:

- `read_gps` reads the sidecar for a RAW, so "already has a location" and the
  coverage figures (`core/survey.py` already looks) count RAWs correctly.
- **Strip location** (`unlocate`) takes the location out of the RAW's
  sidecar too, with `sidecar.drop`, which exists.
- `sidecar.write` writes to a temporary file and then `os.replace`, as every
  other metadata write in the app does. Today it writes in place.

**Worth knowing before relying on it.**

- **DNG** is the exception. Adobe keeps a DNG's metadata inside the file and
  ignores a sidecar. The plan should list DNGs separately and say so, rather
  than write a sidecar Lightroom will not read.
- **Lightroom Classic** reads a sidecar when a photo is imported. For photos
  already in its catalogue, it notices the change and needs *Metadata > Read
  Metadata from Files*. The result screen should say that in one line.
- **darktable** names its sidecars `P1000123.RW2.xmp`, so it will not pick
  these up by itself.
- **A JPEG and a RAW with the same name in the same folder** share one
  `P1000123.xmp`. That is Adobe's convention too (the sidecar belongs to the
  RAW). The JPEG keeps its location inside the file, so nothing is lost, but
  writing "Sidecars only" for that JPEG would land in the RAW's sidecar. The
  plan should notice that case and write into the JPEG instead.

**Where the code goes.** `app/tasks/geotag.py` and `app/tasks/pin.py` (find
the partner, write the sidecar, report it), `core/photo.read_gps`,
`app/tasks/unlocate.py`, `core/sidecar.write`. Tests in a new
`tests/test_geotag_raw.py`, plus `tests/test_unlocate.py`.

### Renaming photographs

**Why.** **Power rename** (`app/tasks/rename.py`, `core/renames.py`) renames
folders only. Cameras name files `P1000123`, `DSC04567` and `IMG_0042`, which
restart from 0001 and collide across cameras, and say nothing about the
picture. People want `2024-07-14_183022_GH5.jpg`, or `Spain 2024 - 001.jpg`.

**The trap this has to avoid.** The app pairs a JPEG with its RAW, its preview
and its finished exports **by name** (`core/pairs.base_name` is part of every
identity). Rename `P1000123.JPG` alone and its `P1000123.RW2` is orphaned: the
next **Re-mirror RAWs** reports it as "no photo of that name", the Rating & tags tab stops
reaching it, and **the developed record** (`core/ledger.py`, keyed on
name + camera + time) forgets the photo was developed. The file manager's
one-file rename (`core/filesops.rename`) has this problem today: it carries the
sidecars and nothing else.

So a photograph is renamed as **one shot**: the JPEG, its sidecars, its RAW in
the RAW tree (found by `find_partner`) and that RAW's sidecar, its preview
(`core/paths.preview_for`), its exports beside it (`developed_beside`), a
video's `.lrv` and `.thm`, and the ledger line. All of them or none.

**What it looks like.** A **Rename photos** tab beside Power rename, under
File explorer. It needs no new UI, because the plan table already shows "old name,
new name" per row:

- A **pattern**, with the variables Sort into folders already has
  (`core/naming.py`: `{date}`, `{year}`, `{camera}`, `{city}` and the rest),
  plus four that only make sense for a file: `{time}` (`183022`),
  `{seq}` (001, 002 in capture-time order, width and start chosen),
  `{original}` (the camera's name) and `{folder}` (the folder's own name).
  Ready-made: `{date}_{time}`, `{date}_{time}_{camera}`,
  `{folder} - {seq}`, `{date} - {original}`.
- **Find and replace** and **case** as a second way, like Power rename's.
- The same refusals as folder renaming: two photos meeting on one name, a
  name already taken by a file not being renamed, a character Windows will
  not take. Any one of those stops the whole run. Two shots taken in the same
  second get `-2`, `-3` in capture order, and the plan says so.
- A bracket keeps its frames together: three exposures named by time differ
  only by the second, so `{seq}` numbers the frames of a set as `014a`, `014b`.
- Every rename is recorded in `core/moves.py`, so **Undo** puts the names back.
- The one-file rename in the file manager is moved onto the same code, so it
  carries the RAW, preview and exports too.

**Where the code goes.** A new `core/photonames.py` (the pattern, the checks,
"one shot" collected and renamed), the new variables in `core/naming.py`,
a new `app/tasks/renamephotos.py` with `parent="files"`, its line in
`app/tasks/__init__.py` and `core/families.py`, `core/filesops.rename` calling
it, and `core/ledger.py` gaining a re-key. Tests in
`tests/test_renamephotos.py`.

**Open questions.** Should the camera's original name be kept somewhere, so it
can always be found again? Lightroom writes it to `xmpMM:PreservedFileName`.
That would be one more attribute in the sidecar (RAW) and a metadata write
(JPEG), and it makes "put the original names back" possible long after Undo
has forgotten the run.

### Previews of RAW-only shots

**Today.** **Make previews** (`app/tasks/previews.py`) makes the small JPEGs
you rate on the tablet from the library's JPEGs. A shot taken RAW-only has no
JPEG in the library, so it gets no preview and can never be rated there.
The viewer already shows RAWs: `core/thumbs.py` pulls out the JPEG the camera
puts inside every RAW for its own screen and shrinks it with Pillow.

**What it would look like.** Make previews gains "RAW-only shots too", on by
default when Setup names a RAW tree. A RAW whose JPEG cannot be found
anywhere in the library (the same test Re-mirror RAWs uses) gets a preview made
from that embedded JPEG, at the place the library's JPEG would have had it
(`preview_for` with the RAW tree as the anchor). The plan counts them on a
line of their own.

It has to carry the three things every preview carries, all read from the
RAW by `core/rawfile.py`, because an embedded JPEG often has none of them:
the **capture time and camera** (so the preview pairs back), and the
**orientation**, applied (so it is not sideways).

**What else has to learn about them.** A preview that stands for a RAW looks
like an orphan to every feature that expects a library JPEG behind it:

- **Sync** (Rating & tags) pairs a preview with a library JPEG, then the JPEG with its
  RAW. For these it pairs the preview with the RAW directly and writes the
  rating to the RAW's sidecar.
- **Re-mirror previews** would call them orphans. It checks the RAW tree
  before deciding.
- **Cull by rating** and **Thin brackets** remove the preview with the RAW, as they already do
  with a JPEG.

**Worth knowing.** The camera's embedded JPEG is the camera's own rendering,
much like the JPEG it would have saved. That is fine for rating. Some bodies
embed a small one (older Sony ARWs carry 1616 by 1080), so a 2560 preview of
those comes out at its own size, never enlarged, and the plan says how many.
A true development of the RAW data (white balance, highlights) needs LibRaw,
through the `rawpy` package. That could be an optional extra later, used when
installed, in the same way Pillow is.

`core/thumbs._inside_raw` reads the whole RAW (25 to 80 MB) to find the
largest embedded JPEG. With the RAW reader it can go straight to the offset,
which matters for a thousand RAWs on the NAS, and Make previews and the viewer
share the one function.

**Where the code goes.** `core/rawfile.py` (the embedded JPEG),
`app/tasks/previews.py`, `app/tasks/ratings.py`,
`app/tasks/remirror_previews.py`, `core/thumbs.py`. Tests in a new
`tests/test_raw_previews.py`, covering the preview and the rating coming back.

### Folders made for each shoot

**How this reads the request.** "Folders made automatically in a directory,
either named by you or named for you": a card dumped into one folder, broken
into one folder per shoot, where the app proposes the shoots and their names
and you can type over any name before anything moves.

**Today.** **Sort into folders** (`app/tasks/bydate.py`) already makes folders
from a pattern (`{year}/{month}`, `{country}/{city}`) and moves photos into
them, RAWs and previews included. Its `{range}` variable already splits by
gaps in time ("New range after (hours)"). What it cannot do is let you
**name** a shoot: "Spain trip" or "Sara's wedding" is something only you know,
and today the only way is Sort into folders by date and then Power rename
afterwards, two passes over the same folders.

**What it would look like.** An **Into shoots** tab under Sort into folders.

1. Point it at a folder (a card dump, the inbox). It reads the capture times
   and finds the shoots: a new one after a gap in time (default 6 hours), and,
   when photos carry a location, after a move of more than some distance
   (default 50 km).
2. A table, one row per shoot: its dates, how many photos, a few thumbnails,
   where (when known), and **a name in a box**. The box is filled from a
   pattern, `{rangestart} {city}` by default ("2024-07-12 Barcelona"). Type
   over any of them, or leave them. Rows can be joined or split by moving
   the boundary, for the evening that the gap rule cut in two.
3. **Make folders** creates them (inside the folder, or inside another one,
   as Sort into folders' "Destination folder" does), and moves each shoot in as one
   thing: JPEG, RAW by identity, preview by position, sidecars, exports.
   Recorded for Undo.

So "autogenerated" is accepting the table as it comes, "guided" is typing the
names, and both are the same screen. It can also run inside a flow with the
pattern alone (no typing), for an inbox that sorts itself.

**Where the code goes.** The grouping in `core/shoots.py` (it already turns
folders into time windows), the "move one shot" part of `bydate.apply` lifted
into `core/` so both tabs share it, a new `app/tasks/shoots.py` with
`parent="bydate"`. The editable table is the one piece of new UI: an
`/api/shoot-list` route in `app/server.py`, like `/api/rename-list`, and a new
`app/web/library/js/16-shoots.js`. Tests in `tests/test_shoots.py`.

**Open questions.** Did "auto generate folder" also mean making an empty set
of folders ahead of time, such as `2025/01` to `2025/12`, before any photos
exist? That is a small addition to the file manager's "New folder" (one
pattern, many folders) and can be done separately.

## Maintenance

- **Moving the bundled Pillow to a new release:** `python tools/fetch_wheels.py
  <version>`, run the tests, commit `windows/wheels/`.
