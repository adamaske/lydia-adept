@echo off
rem Double-click to run the piano-noise experiment (PsychoPy). The dialog asks for subject, condition, room ...
rem The first run builds the Python environment with uv (needs internet, a few minutes).
title Piano-noise experiment
cd /d "%~dp0studies\piano-noise"
if not exist .venv-psychopy\Scripts\python.exe (
    echo Setting up the PsychoPy environment - first run only, this takes a few minutes ...
    uv venv --python 3.10 .venv-psychopy || goto fail
    uv pip install -p .venv-psychopy -r requirements-psychopy.txt || goto fail
)
.venv-psychopy\Scripts\python.exe scripts\piano-noise-experiment.py %*
if errorlevel 1 goto fail
echo.
echo Done. Stop the Aurora recording if it is still running.
pause
exit /b 0
:fail
echo.
echo SOMETHING WENT WRONG - read the messages above.
pause
exit /b 1
