# Photo Manager on Windows

The same app the NAS runs, started as a program instead of as a container. Use
it to keep a library on the PC, or to run the server on the PC and reach it from
your phone.

## What you need

Python 3.11 or newer from python.org, with **"Add python.exe to PATH"** ticked
during the install. Nothing else: the app is Python's own library plus Pillow
and pi-heif (which lets Pillow open the HEIC files an iPhone saves), and both
come with it in `wheels\`. Install.bat installs them from there, with no
internet needed. (On a PC there are no NAS-made thumbnails to borrow, so
without Pillow previews and thumbnails stay blank, and without pi-heif so do
those of HEIC files; their dates and places are read either way.) Only a Python
other than 3.11 to 3.14, 64-bit, makes Install.bat download them instead.

## Installing

Double-click **Install.bat**. It installs Pillow and pi-heif from `wheels\`, puts "Photo Manager" in the
Start menu, on the desktop and in Startup (all three with the app's own icon),
then starts it and opens the page.

It writes no registry keys. **Uninstall.bat** takes the three shortcuts away
again and leaves your settings alone.

## The icon by the clock

Photo Manager has no window of its own to close, so it lives in the
notification area, by the clock. Windows 11 tucks new icons under the **^**
arrow; drag it out onto the taskbar to keep it in sight.

- **Click** it to open Photo Manager.
- **Right-click** it for the quick settings:

| | |
|---|---|
| Open Photo Manager | the page, in its own window or the browser |
| Copy the address for your phone | `http://<this PC>:8080`, ready to paste |
| Open in its own window | ticked: a plain window with no address bar (Microsoft Edge's app mode). Unticked: your usual browser |
| Start with Windows | adds or removes the Startup shortcut. Started with Windows it goes straight into the tray without opening the page |
| Show the log | `desktop.log`, for when something is wrong |
| Open the settings folder | `%LOCALAPPDATA%\PhotoManager` |
| Quit Photo Manager | stops it. If a task is still running it asks first |

Resting the mouse on the icon says the address, or how many tasks are running.

Starting it a second time does not start a second copy: it opens the page of
the one already running.

## Where things go

| | |
|---|---|
| Settings, cache, log | `%LOCALAPPDATA%\PhotoManager` |
| Tray settings | `desktop.json` in the same folder |
| The page | http://localhost:8080 |
| If 8080 is taken | the next free port, written in `desktop.log` |

Settings live outside the program on purpose: replace this folder with a newer
copy and your library path, your dashboards and your bands are all still there.

Reindex and Permissions only mean something on a Synology NAS, so the page
leaves them out on a PC (Setup says so in one line). The command line still
runs them.

## Stopping it

**Quit Photo Manager** on the icon by the clock, or the **Quit** button in the
app's own top bar - which only appears on a copy started like this, the NAS
never shows it. **Stop.bat** is for when it is not answering; it ends the one
process it wrote down, not every Python on the account.

## Reaching it from your phone

First run, Windows Defender will ask whether to allow it on the network. Say yes
for **private networks** - that is what lets the phone reach it. Say no and the
page still works on this PC and nowhere else.

Then, on the phone, either let it find the PC by itself (Setup ▸ *Network* ▸
"Discoverable on the network", which is on unless you turn it off) or type the
address the tray's **Copy the address for your phone** gives.

Set a password in **Setup ▸ Password** before you do. With no password, anyone
on your network who finds the port can read and delete your photographs.

**Only your photo folders.** On a PC the app reaches the folders chosen in
Setup (the library, the RAW, previews, video and develop trees, Lightroom's
export folder) and nothing else on the disk, so another device cannot browse
or download your documents through it. A file you want a tool to read from
somewhere else, such as a GeoNames download or a folder to export into, needs
its folder added under **Setup ▸ Also allowed**. The folder boxes in Setup can
be changed from this PC at any time, and from another device only once a
password is set. Setting `ALLOWED_ROOTS` before starting the app replaces all
of this with the folders it names.

Lost the password? Quit the app, remove `access.json` from
`%LOCALAPPDATA%\PhotoManager` (its `PM_DATA` folder), or set `PM_PASSWORD` to a
new one, then start it again.

## When it does not start

There is no console window to read, so it writes everything to
`%LOCALAPPDATA%\PhotoManager\desktop.log` (right-click the icon ▸ **Show the
log**). If the server itself stops, a message box says so and points there. The
usual answers:

- **No icon by the clock** - look under the **^** arrow first.
- **"Python was not found on the PATH"** from Install.bat - Python is not on the PATH.
  Reinstall Python with the tick, or run `where pythonw` to see.
- Nothing at all in the log - the shortcut is pointing at a folder you have
  since moved. Run Install.bat again from wherever the app is now.
- A port complaint - something else has 8080. It moves itself to the next free
  port and says which in the log; use that one.

## The files here

| | |
|---|---|
| `PhotoManager.pyw` | the program: starts the server and the tray icon |
| `tray.py` | the icon by the clock, drawn with Windows' own calls (no packages) |
| `PhotoManager.ico` | the app icon, every size from 16 to 256 px. Made by `tools/make_icon.py` |
| `shortcuts.py` | makes and removes the shortcuts, for the two .bat files |
| `wheels\` | Pillow and pi-heif for Windows 64-bit, Python 3.11 to 3.14, with a hash for each file. Made by `tools/fetch_wheels.py` |
| `Install.bat`, `Uninstall.bat`, `Stop.bat` | as above |
