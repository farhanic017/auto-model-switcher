@echo off
REM ============================================================================
REM  Auto Model Switcher  ---  Universal CLI Wrapper (cmd.exe)
REM  Copyright (c) 2026 Farhan Dhrubo  <farhaiee123@gmail.com>
REM  License: GPL-3.0  ---  https://github.com/farhanic017/auto-model-switcher
REM
REM  This program is free software. You may NOT remove this notice,
REM  re-distribute as your own work, or sell without attribution.
REM ============================================================================
REM Auto Model Switcher — Universal CLI Wrapper (.bat for cmd.exe)
REM Works with any CLI: opencode, claude, cursor, aider, windsurf, continue,
REM or any future agent. Just pass the CLI name as the first argument.
REM Usage: auto-switch.bat opencode [args...]
REM Usage: auto-switch.bat claude [args...]

set SWITCHER=%~dp0switcher.py
set STATE=%USERPROFILE%\.auto-model-switcher\state.json

if "%~1"=="" (
  echo Usage: auto-switch.bat ^<cli^> [args...]
  exit /b 2
)

REM Run through switcher brain: pre-check, detect usage-limit failures, switch, retry once.
python "%SWITCHER%" run "%~1" -- %*
