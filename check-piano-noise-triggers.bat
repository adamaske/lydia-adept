@echo off
rem Trigger check, no participant: a listener stands in for Aurora on the LSL "Trigger" stream,
rem then a fast pilot session runs. Tick "send LSL" in the dialog. Result is in the listener window.
title Piano-noise trigger check
cd /d "%~dp0studies\piano-noise"
if not exist .venv-psychopy\Scripts\python.exe (
    echo Run run-piano-noise.bat once first - it sets up the Python environment.
    pause
    exit /b 1
)
start "Trigger listener" cmd /k .venv-psychopy\Scripts\python.exe scripts\check_triggers.py --log data\pilot\logs --wait 300
call "%~dp0run-piano-noise.bat" --pilot
