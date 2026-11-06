@echo off
rem Runs every test. Needs nothing installed - the fixtures are committed.
cd /d "%~dp0.."
python -m unittest discover -s tests -t . -v
if errorlevel 1 (
    echo.
    echo ==================================================
    echo  Tests failed, or Python could not be started.
    echo  If you see 'python is not recognized', install
    echo  Python 3.12 from python.org and tick "Add to PATH".
    echo ==================================================
)
pause
