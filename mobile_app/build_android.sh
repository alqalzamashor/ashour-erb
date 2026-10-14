#!/usr/bin/env bash
# الاستخدام:  ./build_android.sh https://erp.example.com "ashour" com.ashour.erp
# المتطلبات: Node 18+، JDK 17، Android SDK (Android Studio). الناتج: android/app/build/outputs/apk/debug/app-debug.apk
set -e
cd "$(dirname "$0")"
URL="${1:?اكتب رابط السيرفر https://...}"; NAME="${2:-ashour}"; ID="${3:-com.ashour.erp}"
python3 ../tools/make_mobile_icons.py resources
npm install
node configure.js "$URL" "$NAME" "$ID"
[ -d android ] || npx cap add android
npx capacitor-assets generate --android --iconBackgroundColor '#124F40' --splashBackgroundColor '#124F40' || true
npx cap sync android
(cd android && ./gradlew assembleDebug)
echo "APK: $(pwd)/android/app/build/outputs/apk/debug/app-debug.apk"
echo "للنشر على Google Play: ./gradlew bundleRelease بعد ضبط مفتاح التوقيع (راجع README_MOBILE_AR.md)"
