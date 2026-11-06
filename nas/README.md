# Running it on the NAS

Nothing is built. The image is stock Python, the app is a folder you copy, so
**updating later is: copy the files, hit Restart.**

---

## Step 1 - make the folders

In File Station, inside your `docker` share:

    docker/Photo-Manager/code       <- the app goes here
    docker/Photo-Manager/config     <- leave it EMPTY

## Step 2 - copy the app into `code`

Copy the **contents** of `Desktop\Photo Manager NAS\` - not the folder itself.

Right when done:

    docker/Photo-Manager/code/app/
    docker/Photo-Manager/code/core/
    docker/Photo-Manager/code/nas/
    docker/Photo-Manager/code/scripts/
    docker/Photo-Manager/code/tests/
    docker/Photo-Manager/code/CLAUDE.md

Wrong (one level too deep):

    docker/Photo-Manager/code/Photo Manager NAS/app/

**The check:** `code/nas/start.sh` must exist. If it is
`code/Photo Manager NAS/nas/start.sh`, move everything up one level.

Do **not** copy the PC's `config` folder. The NAS has different paths, so it
needs its own settings.

### About the empty config folder

Empty is correct. On the PC it is empty because you have not pressed Apply on the
Setup tab yet - that is what writes `settings.json`. On the NAS the app fills it
on its own with:

    settings.json      your three trees and bracket settings
    timeline.tsv       once you import a Google Timeline
    python/            Pillow and pi-heif (HEIC pictures), installed on first start

It is the one folder that must be writable. `code` is mounted read-only on
purpose.

## Step 3 - check the one path

There is only one photo path in the compose file, and it is your **home folder**:

    /volume1/homes/YOU

Check it: File Station → right-click your Photos folder → **Properties** → the
**Location** line. If it reads `/volume1/homes/YOU/Photos`, your home folder is
`/volume1/homes/YOU` and there is nothing to change.

You do not need the RAW or previews paths here. They live inside your home
folder, so they are already inside the mount whatever they are called - which is
the point of mounting the home folder rather than three named trees.

### Why one mount, at its own path

A container path like `/photos` is a name that exists nowhere but inside the
container. Two things go wrong with it, and both are quiet:

- The moment it disagrees with `ALLOWED_ROOTS`, or with what you typed into
  Setup, the app says *"is not a folder"* about a folder plainly visible in File
  Station - because it exists on the NAS, not in there.
- It gives you a second set of names to keep straight forever.

Mounted at its own path, what File Station shows you is what you type.

## Step 4 - the user (nothing to do)

There is no `user:` line and no uid to find.

A container does not inherit the DSM account that created it, so by default it
runs as root and everything it writes belongs to root - which you discover later,
when Windows will not let you delete a `_Culled` folder. The account that created
the container is not the right answer either: what matters is who owns the
**photos**, and those are usually different people.

So it works it out. Started as root, it reads who owns your library, hands the
config folder to them, drops to that user, and only then writes anything. The log
says what it did:

    User:        dropping to your uid:gid - it owns /volume1/homes/YOU/Photos
    Running as:  uid=1027 gid=100
    Folders:
       owned by you, writable                    /volume1/homes/YOU/Photos
       MISSING                            /volume1/homes/YOU/Photos Raw

To override it, add to `environment:`

    PM_USER: "1027:100"    use exactly this
    PM_USER: "root"        stay as root, I know what I am doing

A folder Docker invented because a path was wrong - empty and owned by root - is
handed over too. One with anything in it is never touched: guessing at the
ownership of a real photo tree is not the app's business.

## Step 5 - create the project

**Container Manager** → **Project** (left side) → **Create**

1. **Project Name:** `photo-manager`
2. **Path:** click **Set Path**, browse to `docker/Photo-Manager`, **Select**
3. **Source:** choose **Create docker-compose.yml**
4. Paste in the contents of `nas/docker-compose.yml`, edited with:
   - your home folder from Step 3, if it is not `/volume1/homes/YOU`
     (it appears twice - in `ALLOWED_ROOTS` and in `volumes`; they must match)
   - a different port than 8842 if that one is taken. Change both numbers:
     the left-hand one under `ports:` and `PM_PUBLIC_PORT`, which is the
     port phones are told to use when they find the app on the network
   - nothing for the user. Step 4 is nothing to do; do not add a `user:` line
5. **Next** → it checks the file → **Next**
6. Leave the web-portal options alone → **Done**

It now downloads Python (a minute or two) and starts. The log ends with:

    Photo Manager
      open       http://localhost:8080
      folders    /volume1/homes/YOU
      settings   /config

If it says `settings CANNOT BE SAVED`, the `config` volume path is wrong.

## Step 6 - open it and fill in Setup

    http://<your-nas-ip>:8842

Go to **Setup** first, and use **Browse** rather than typing - it starts at your
home folder and every folder inside it is one click away:

    Library             /volume1/homes/YOU/Photos
    RAW tree            /volume1/homes/YOU/Photos Raw
    Previews tree       /volume1/homes/YOU/Photos Previews

The exact names are whatever they are in File Station; Browse will show you. Not
`N:\Photos` - that is your PC's drive letter, the container has never heard of
it. Press **Show me what would happen**, then **Go ahead**. Every other feature
now starts from those.

The RAW and previews trees do not have to exist yet. They are created the first
time something writes to them, and Setup says so rather than treating a missing
folder as a typo. Only the library has to be real, because nothing creates it.

---

## Updating it later

**Changed the app?** Restart is enough.

1. Copy the changed files into `docker/Photo-Manager/code`
2. Container Manager → Project → `photo-manager` → **Restart**

**Changed the compose file?** Check that it actually took.

Volumes, environment variables and ports are fixed when a container is
*created*, not when it starts. Some DSM versions re-create the project's
containers on **Restart** and pick the change up; others start the same container
again with the mounts it was born with, so a corrected volume line does nothing
and the app goes on saying "is not a folder" about the path you just fixed.

Try Restart, and look at the header (below). If the change did not take:

    Container Manager → Project → photo-manager → Stop
                                                → Build   (recreates it)

which always applies it.

Your `config` volume, and everything in it, is untouched either way.

### How to tell which one you are looking at

The header says. `code 04 Sep 17:25 · up 3m` is read from the running process
and never from cache:

- **the code stamp moved** - it loaded the files you copied
- **it did not move** - the copy did not reach the folder the container mounts
- **"not responding"** - the container is stopped or restarting
- **an amber bar across the top** - a folder in `ALLOWED_ROOTS` is not visible from
  inside the container, named for you rather than found one Browse click at a
  time

**Reload page** in the header reloads in a way a browser cannot answer from
cache. (**Re-read library**, on Home and at the foot of the rail, is the other
one: it asks the index to look at the library again.)
The page and every answer it gets are sent `no-store` for the same reason: a
cached page and a Restart that did not take look identical, and two faults with
one symptom cannot be told apart.

---

## Running a task on a schedule

Control Panel → **Task Scheduler** → Create → **Scheduled Task** → **User-defined
script**. Run as `root`. Under **Run command**:

```sh
docker exec photo-manager python -m app.cli remirror --apply
```

Useful ones:

```sh
# keep the RAW tree matching the library
docker exec photo-manager python -m app.cli remirror --apply

# make previews for anything new
docker exec photo-manager python -m app.cli previews --apply

# report what a cull WOULD do, without doing it
docker exec photo-manager python -m app.cli cull --raw_at_or_below 2
```

A misspelt option (`--foldr`) or a flow name that does not exist (`--which`)
is refused: the command writes nothing, says what it did not understand, lists
what it accepts, and exits with status 2 so DSM marks the task failed.

Leave `--apply` off and it only reports. Tick **Send run details by email** on the
task and the preview comes to you to decide on.

No paths needed - every task reads them from Setup.

---

## Without Docker at all

Everything except **Make previews** is plain Python with nothing installed.

Package Center → install **Python 3**. Then in Task Scheduler:

```sh
cd /volume1/docker/Photo-Manager/code
export PM_DATA=/volume1/docker/Photo-Manager/config
/var/packages/Python3/target/bin/python3 -m app.cli remirror --apply
```

You get the tasks and the command line, but no web page unless you also run
`python3 -m app.server`, and no previews without Pillow. Make those on the PC -
previews are disposable anyway.

---

## When something is wrong

**Container restarts in a loop.** Container Manager → Container →
`photo-manager` → Log. Almost always a volume path that does not exist.

**"... is not a folder"** for a path you can see in File Station. It exists on
the NAS, not inside the container - the mount is missing or the home folder in
`volumes` is spelt differently from the real one. The folder browser lists what
the container can actually see, so if your home folder is not in it, that is the
answer.

**"That is outside the folders this is allowed to touch."** `ALLOWED_ROOTS` and
the volume must be the same path. The browser will still *show* you folders
outside it - looking is not touching - and marks them, but a task refuses them.

**`sh: /app/nas/start.sh: No such file`.** Step 2 went one level too deep.

**Everything is owned by root.** Something stopped the app dropping user -
either a `user:` line in the compose file (remove it; it prevents the drop) or
`PM_USER: "root"`. The log's `User:` line says what happened. To repair what was
already written, over SSH:
`sudo chown -R YOU:users "/volume1/homes/YOU/Photos Raw"`

**"Make previews" says it needs Pillow.** No internet on first start. Restart -
it retries - or make previews on the PC.

**HEIC photos have dates and places but grey thumbnails.** The log's
`HEIC reader:` line says why. "COULD NOT INSTALL" with no internet: restart and
it retries. On an older ARM NAS there may be no pi-heif built for that chip at
all; the thumbnails Synology Photos made are still shown, and everything else
about a HEIC works without it.

**Lost the password.** Remove `access.json` from the config folder (the one
mounted as `PM_DATA`), or set `PM_PASSWORD` in the compose file to a new one,
then restart the container. `PM_PASSWORD` wins over the one set in the page.

**Synology Photos still shows a culled photo.** It re-indexes on its own
schedule. Photos → Settings → re-index, or wait.

---

## Which compose file?

Two exist. Only one is read.

    docker/Photo-Manager/docker-compose.yml            LIVE - Docker reads this
    docker/Photo-Manager/code/nas/docker-compose.yml   the template you paste from

Container Manager wrote the live one when you set the project path. The one under
`code/nas/` ships with the app so these instructions have something to point at,
and so it can be kept correct and tested - but nothing reads it. Editing it looks
right and changes nothing.

To change the configuration: Container Manager -> Project -> `photo-manager` ->
edit the compose there (or edit the file in File Station), then **Restart**.

The good side of that nesting: copying new code into `code/` never touches your
live compose, so your paths and port survive every update.

---

## On a phone

The page works on a phone as it is: a bar along the bottom for Home / Photos /
Places / Tools / More, and the same features as on a desk. (It is no longer
offered for installing as an app - that went in 3.12.0.)

Two of its parts need a **secure address** - `https://...` - because the
browser refuses them on a plain `http://192.168.x.x:8842`:

| What                              | Needs https |
|-----------------------------------|-------------|
| Reading, rating, the file manager | no          |
| Keeping the shell and thumbnails  | yes         |
| "Tell me when a run finishes"     | yes         |

Two ways to get one, both free and neither of them opening anything to the
internet:

**Tailscale (easiest, works away from home).** On the NAS, in the Tailscale
package's own shell:

    tailscale serve --bg --https=443 http://127.0.0.1:8842

Then open `https://<machine>.<your-tailnet>.ts.net` on the phone. The
certificate is real, so the browser is happy, and only devices on your tailnet
can reach it.

**DSM reverse proxy (at home).** Control Panel > Login Portal > Advanced >
Reverse Proxy > Create:

    Source:       HTTPS, hostname photos.yournas.local (or your DDNS name), port 443
    Destination:  HTTP, localhost, port 8842

Give that hostname a certificate under Control Panel > Security > Certificate -
Let's Encrypt if the name is public, or DSM's own if you accept the warning
once on the phone.

Nothing about the app changes: the same page, on a name the phone trusts.
Two settings in the compose file are worth knowing about behind a proxy:

- **`PM_HOSTS`**: with no password set, the app refuses a change asked for
  under a name it does not know, so a web page elsewhere cannot point its
  own name at your NAS and drive the app. Addresses, one-word names and names
  ending `.local`, `.lan` or `.ts.net` are known already. A DDNS name such as
  `photos.example.synology.me` is not: put it in `PM_HOSTS`, or set a
  password, which makes the check unnecessary.
- **`PM_TRUSTED_PROXY`**: the proxy's address as the container sees it,
  usually `172.17.0.1`. Without it every request seems to come from the proxy,
  so eight wrong passwords from one phone lock out every phone for five
  minutes. With it the app reads `X-Forwarded-For` (and `X-Forwarded-Host`,
  for a proxy that rewrites the name) from that address only.

If every change through the proxy fails with *"This request came from a page
at ..., not from this app"*, the proxy is rewriting the `Host` header: set
`PM_TRUSTED_PROXY`.

The rest stays as it was. The
service worker keeps only the shell and thumbnails you have already looked at -
never a page or an API answer, because the header of this app exists to prove
you are looking at the running process.
