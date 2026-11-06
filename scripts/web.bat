@echo off
rem The web page. Open http://localhost:8080 once this is running.
rem Set ALLOWED_ROOTS to fence it in; leave it unset to reach anywhere.
rem   set ALLOWED_ROOTS=N:\Photos;N:\Photos Raw;N:\Photos Previews
cd /d "%~dp0.."
python -m app.server
pause
