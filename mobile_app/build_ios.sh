#!/usr/bin/env bash
# يتشغّل على Mac فقط (Xcode + حساب Apple Developer). الاستخدام: ./build_ios.sh https://erp.example.com "ashour" com.ashour.erp
set -e
cd "$(dirname "$0")"
URL="${1:?اكتب رابط السيرفر https://...}"; NAME="${2:-ashour}"; ID="${3:-com.ashour.erp}"
python3 ../tools/make_mobile_icons.py resources
npm install
node configure.js "$URL" "$NAME" "$ID"
[ -d ios ] || npx cap add ios
npx capacitor-assets generate --ios --iconBackgroundColor '#124F40' --splashBackgroundColor '#124F40' || true
npx cap sync ios
npx cap open ios
echo "في Xcode: اختار Team (حسابك) ← Product > Archive ← Distribute (TestFlight / App Store)."
