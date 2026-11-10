@echo off
rem Finder Python uden at koere scriptet to gange hvis det fejler.
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python er ikke installeret. Hent det fra python.org og saet flueben i "Add to PATH".
  pause
  exit /b 1
)
%PY% hud.py %*
if errorlevel 1 pause
