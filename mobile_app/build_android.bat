@echo off
rem الاستخدام: build_android.bat https://erp.example.com ashour com.ashour.erp
set URL=%1
set NAME=%2
set ID=%3
if "%URL%"=="" (echo اكتب رابط السيرفر https://... & exit /b 1)
if "%NAME%"=="" set NAME=ashour
if "%ID%"=="" set ID=com.ashour.erp
cd /d %~dp0
python ..\tools\make_mobile_icons.py resources || exit /b 1
call npm install || exit /b 1
node configure.js %URL% %NAME% %ID% || exit /b 1
if not exist android call npx cap add android
call npx capacitor-assets generate --android --iconBackgroundColor #124F40 --splashBackgroundColor #124F40
call npx cap sync android || exit /b 1
cd android && call gradlew.bat assembleDebug
echo APK: %~dp0android\app\build\outputs\apk\debug\app-debug.apk
