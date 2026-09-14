@echo off
title SimTrack
cd /d "%~dp0"

:: Source-run launcher (testers with Python). The packaged SimTrack.exe
:: needs none of this.
python -m pip install --quiet -r requirements.txt
python server_windows.py
if errorlevel 1 pause
