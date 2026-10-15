@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv ( echo شغّل install_windows.bat الأول & pause & exit /b 1 )
call .venv\Scripts\activate.bat
python desktop.py %*
