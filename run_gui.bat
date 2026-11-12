@echo off
cd /d "%~dp0"
py -3 folder_mirror.py
if errorlevel 1 pause
