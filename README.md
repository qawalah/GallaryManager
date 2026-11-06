# Photo Manager

A photo-library manager that sorts, geotags, rates, tags, culls and
de-duplicates photographs, keeps RAWs, previews and videos in trees that mirror
the library, and runs all of that on a schedule. One web page is the interface,
and every feature also runs from the command line.

It is plain Python 3.10 or newer using only the standard library. Pillow (for
previews and thumbnails), pi-heif (for HEIC thumbnails) and ffmpeg (for video
times) are optional; without them the related features say so instead of
failing.

Every feature shows what it will do before it does it, and nothing is deleted
by accident: culls, duplicates and the like move into piles such as `_Culled`
and `_Duplicates`, and History can put a run back.

## Installing it

- **On a Synology NAS**, as a container: [nas/README.md](nas/README.md).
- **On a Windows PC**, as a program with a tray icon: [windows/README.md](windows/README.md).

## Running it from a checkout

```
python -m app.server                 # the page, on http://localhost:8080
python -m app.cli                    # list every task
python -m app.cli cull --help        # what one task accepts
python -m app.cli cull --apply       # plan, then do it
```

Without `--apply` a task only reports what it would do.

## Tests

```
python -m unittest discover -s tests -t .
sh scripts/check.sh                  # builds the page and checks its script
```

Set `PM_DATA` to a temporary folder so the tests do not write settings beside
the code.

## Where to read more

- [CLAUDE.md](CLAUDE.md): the layout of the code and where each kind of change goes.
- [PRODUCT.md](PRODUCT.md): who it is for, what it promises, and the voice and accessibility it keeps.
- [docs/DESIGN.md](docs/DESIGN.md): why things are the way they are.
- [docs/ROADMAP.md](docs/ROADMAP.md): what is planned.
- [CHANGELOG.md](CHANGELOG.md): what each release changed.
