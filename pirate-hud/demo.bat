@echo off
cd /d "%~dp0"
rem Find Python: py-launcheren, saa kendte installationsmapper, til sidst 'python'.
rem ('python' sidst, fordi Windows har en falsk python.exe der bare aabner Microsoft Store.)
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*") do if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python blev ikke fundet. Dobbeltklik installer.bat foerst.
  pause
  exit /b 1
)
"%PY%" hud.py --demo %*
if errorlevel 1 pause
