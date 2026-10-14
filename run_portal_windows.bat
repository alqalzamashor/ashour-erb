@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (set PY=.venv\Scripts\python.exe) else if exist venv\Scripts\python.exe (set PY=venv\Scripts\python.exe) else (set PY=python)
if "%1"=="invite" (%PY% trial_portal.py %* & goto :eof)
%PY% trial_portal.py run %*
pause
