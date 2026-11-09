@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -m radio_metadata --demo
if errorlevel 1 pause
