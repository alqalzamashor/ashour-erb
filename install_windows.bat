@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.11+ غير مثبت. نزله من python.org وفعّل Add to PATH & pause & exit /b 1)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo تم التثبيت. شغّل السيرفر: run_server_windows.bat   (ثم افتح الرابط من المتصفح)
pause
