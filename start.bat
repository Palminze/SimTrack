@echo off
title SimTrack
cd /d "%~dp0"

:: Download cloudflared if missing (for HTTPS tunnel when not on same WiFi)
if not exist "cloudflared.exe" (
    echo Downloading cloudflared...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe'"
)

:: Launch the GUI app (handles everything — server + FreeTrack + UDP)
python server_windows.py
