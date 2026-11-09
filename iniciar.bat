@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -m radio_metadata
if errorlevel 1 pause
