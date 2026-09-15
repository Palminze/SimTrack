@echo off
title SimTrack
cd /d "%~dp0"

:: Source-run launcher (testers with Python). The packaged SimTrack.exe
:: needs none of this. Arguments are forwarded, so `start.bat --classic`
:: reaches the app.
python -m pip install --quiet -r requirements.txt
python server_windows.py %*

:: Always pause: a silent exit with code 0 is exactly the failure we need
:: the user to be able to see and report.
echo.
echo SimTrack has stopped. Press any key to close.
pause >nul
