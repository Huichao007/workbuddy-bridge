@echo off
REM Watchdog: relaunch the bridge if it died. Register with Windows Task Scheduler
REM to run every 10 minutes, or drop a shortcut in the Startup folder.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-bridge.ps1"
