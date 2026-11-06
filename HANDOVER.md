# Handover

Photo Manager was moved here from `alialyami90/JIC` (main at commit `9090b22`,
"Merge pull request #48") on 2026-11-06 and set up for DevStore.

No source code was changed apart from one import hint in
`windows/PhotoManager.pyw` (so the build bundles `pi_heif`).

Added for DevStore: `devstore.json`, `requirements.txt`, `icon.ico`,
`store/icon.png`, `Dockerfile`, `.dockerignore`, `docker-compose.yml`,
`windows/devstore-prepare.ps1`, `.github/workflows/release.yml`, and a
"DevStore" section in `CLAUDE.md`.

Not changed: `nas/` (the older code-folder setup), `windows/Install.bat` and the
other scripts. Under DevStore the PC app is installed by the DevStore Updater
instead of `Install.bat`.

Checked here: the PyInstaller build starts and serves the page on Linux, and
the `test_desktop`, `test_compose` and `test_startup` tests pass. Not checked
here (needs Windows or a Docker daemon): the Windows tray, and the Docker build.
