@echo off
setlocal
cd /d "%~dp0"
set PANEL_OPEN_BROWSER=1
if exist ".env" (
  echo Using .env in %CD%
) else (
  echo No .env — copy .env.example or re-run installer
)
start "" /B "PZControlPanel.exe"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8000/"
