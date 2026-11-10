@echo off
rem Installerer alt der skal til. Se installer.ps1 for hvad den goer.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer.ps1"
echo.
pause
