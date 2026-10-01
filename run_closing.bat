@echo off
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
.\.venv\Scripts\python.exe send_alert.py --closing
