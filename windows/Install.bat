@echo off
rem Put Photo Manager in the Start menu, on the desktop, and in Startup so it
rem comes back after a reboot, with its own icon. Nothing is written to the
rem registry - removing it is Uninstall.bat, and you can check what this does by
rem reading it and windows\shortcuts.py.
setlocal
cd /d "%~dp0"

where pythonw.exe >nul 2>nul
if errorlevel 1 goto :nopython
for /f "delims=" %%P in ('where pythonw.exe') do set "PYW=%%P" & goto :got
:got
set "PY=%PYW:pythonw.exe=python.exe%"
if not exist "%PY%" goto :nopython

echo Using %PY%
echo.
"%PY%" -c "import PIL" >nul 2>nul
if errorlevel 1 goto :install
"%PY%" -c "import pi_heif" >nul 2>nul
if errorlevel 1 goto :install
echo Pillow and its HEIC reader are already installed.
goto :shortcuts

:install
rem Pillow and pi-heif ship inside this folder (wheels\), so installing them
rem needs no internet and takes seconds. pi-heif is what lets Pillow open the
rem HEIC files an iPhone saves. --require-hashes refuses a file that is not
rem exactly the one tools\fetch_wheels.py downloaded.
echo Installing Pillow and its HEIC reader (previews and thumbnails) from this folder ...
"%PY%" -m pip install --user --disable-pip-version-check --no-input --no-index --find-links "%~dp0wheels" --require-hashes -r "%~dp0wheels\requirements.txt"
if not errorlevel 1 goto :shortcuts

rem Only when this Python is one the bundled copies were not built for.
rem Progress shown on purpose: a download with nothing moving on screen looks
rem like a hang. --no-input and the short timeout make a blocked network fail
rem in seconds, not minutes. Two separate installs, so a Python that pi-heif
rem has no build for yet still gets Pillow.
echo.
echo The bundled copies do not fit this Python, so they are downloaded instead.
echo It is a few MB from the internet; the progress shows below.
"%PY%" -m pip install --user --disable-pip-version-check --no-input --timeout 20 --retries 2 pillow
if errorlevel 1 (
  echo.
  echo Pillow could not be installed - Photo Manager still runs, but
  echo previews and thumbnails stay blank until it is:  pip install pillow
)
"%PY%" -m pip install --user --disable-pip-version-check --no-input --timeout 20 --retries 2 pi-heif
if errorlevel 1 (
  echo.
  echo The HEIC reader could not be installed - Photo Manager still runs, and
  echo reads the dates and places of HEIC files, but their thumbnails stay
  echo blank until it is:  pip install pi-heif
)

:shortcuts
echo.
"%PY%" "%~dp0shortcuts.py" install
if errorlevel 1 (
  echo Could not make the shortcuts.
  pause
  exit /b 1
)

echo.
echo Done. Photo Manager is in the Start menu, on the desktop, and starts with
echo Windows. It runs in the background: look for its icon by the clock
echo (under the ^^ arrow if Windows has tucked it away). Right-click the icon
echo for settings or to quit. Starting it now - the page opens in your browser.
start "" "%PYW%" "%~dp0PhotoManager.pyw"
timeout /t 3 >nul
exit /b 0

:nopython
echo Python was not found on the PATH.
echo Install Python 3.11 or newer from python.org and tick "Add python.exe to PATH".
pause
exit /b 1
