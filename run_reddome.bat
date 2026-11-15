@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m reddome %*
if errorlevel 1 pause
