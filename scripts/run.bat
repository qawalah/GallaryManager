@echo off
rem The command line. With no arguments it lists every task.
rem   run                          every task
rem   run cull --help              what that task accepts
rem   run cull --folder "N:\Photos" --raw "N:\Photos Raw" --raw_at_or_below 2
rem   run cull ... --apply         and then do it
cd /d "%~dp0.."
python -m app.cli %*
if "%~1"=="" pause
