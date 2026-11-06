@echo off
rem Stop it when nothing else will. The tidy ways are Quit on the icon by the
rem clock (right-click it) or Quit in the app's top bar; this is for when it is
rem not answering.
rem
rem It ends THIS program by the process id it wrote down, not every window-less
rem Python on the account - that would take out whatever else you are running.
setlocal
set "PIDFILE=%LOCALAPPDATA%\PhotoManager\desktop.pid"
if not exist "%PIDFILE%" (
  echo No running copy was recorded ^(%PIDFILE% is not there^).
  pause
  exit /b 1
)
set /p PMPID=<"%PIDFILE%"
taskkill /f /pid %PMPID% >nul 2>nul
if errorlevel 1 (
  echo Nothing was running under process %PMPID%.
) else (
  echo Photo Manager stopped ^(process %PMPID%^).
)
del "%PIDFILE%" >nul 2>nul
pause
