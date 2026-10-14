@echo off
chcp 65001 >nul
rem ترقية آمنة: اسحب ملف الإصدار الجديد (zip) على الملف ده، أو  update_windows.bat ملف.zip --check
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (set PY=.venv\Scripts\python.exe) else if exist venv\Scripts\python.exe (set PY=venv\Scripts\python.exe) else (set PY=python)
%PY% update.py %*
pause
