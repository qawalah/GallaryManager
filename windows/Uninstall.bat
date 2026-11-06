@echo off
rem Take the shortcuts away again. Your settings and your photographs are not
rem touched - settings live in %LOCALAPPDATA%\PhotoManager and are left exactly
rem where they are, so reinstalling picks up where you left off.
rem
rem It does not stop a copy that is running: right-click the icon by the clock
rem and choose Quit for that.
setlocal
cd /d "%~dp0"

where python.exe >nul 2>nul
if errorlevel 1 (
  echo Python was not found on the PATH, so the shortcuts cannot be removed
  echo from here. Delete "Photo Manager" from the Start menu, the desktop and
  echo shell:startup by hand - nothing else was installed.
  pause
  exit /b 1
)
python "%~dp0shortcuts.py" remove
echo.
echo The shortcuts are gone. Settings kept in %LOCALAPPDATA%\PhotoManager.
echo Delete that folder yourself if you want them gone too.
pause
