@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem مشغّل بضغطة واحدة: يثبّت أول مرة تلقائيًا ثم يفتح البرنامج
where python >nul 2>nul || (echo Python 3.11+ غير مثبت. نزله من python.org وفعّل Add to PATH & pause & exit /b 1)
if not exist .venv (
  echo أول تشغيل: جاري التثبيت، استنى دقيقة...
  python -m venv .venv || (echo فشل إنشاء البيئة & pause & exit /b 1)
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt || (echo فشل تثبيت المكتبات & pause & exit /b 1)
) else (
  call .venv\Scripts\activate.bat
)
python desktop.py %*
if errorlevel 1 pause
