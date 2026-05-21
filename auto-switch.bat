@echo off
REM Auto Model Switcher — Universal CLI Wrapper (.bat for cmd.exe)
REM Usage: auto-switch.bat opencode [args...]
REM Usage: auto-switch.bat claude [args...]

set SWITCHER=%~dp0switcher.py
set STATE=%USERPROFILE%\.auto-model-switcher\state.json

REM Quick health check
python "%SWITCHER%" switch --silent >nul 2>&1

REM Run the target CLI
%*
