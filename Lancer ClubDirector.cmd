@echo off
title ClubDirector AI
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_clubdirector.ps1" %*
pause
