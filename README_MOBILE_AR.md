# تثبيت البرنامج على أندرويد و iPhone

البرنامج بيشتغل على سيرفر (سحابة)، فالتطبيق على الموبايل بيفتح السيرفر بتاعك بملء الشاشة وبأيقونة ashour. فيه طريقتين:

## 1) تثبيت مباشر من المتصفح (PWA) — جاهز الآن، من غير متجر ومن غير أي بناء
- افتح رابط البرنامج على الموبايل واضغط **«تثبيت التطبيق على الموبايل»** في شاشة الدخول (أو افتح `/install.html`).
- **أندرويد (Chrome):** زر «تثبيت التطبيق الآن» أو القائمة ⋮ ← «تثبيت التطبيق».
- **iPhone/iPad (Safari فقط):** زر المشاركة ⬆︎ ← «إضافة إلى الشاشة الرئيسية».
- لازم الرابط يكون **HTTPS** (راجع `setup_https_linux.sh` / وضع الدومين). من غير HTTPS المتصفح مش هيعرض التثبيت.
- مفيش إشعارات push ولا نشر على المتاجر بهذه الطريقة. (إشعارات الويب على iPhone محتاجة iOS 16.4+ والتطبيق مثبّت.)

## 2) تطبيق حقيقي (APK / IPA) للمتاجر — غلاف Capacitor في مجلد `mobile_app/`
بيفتح رابط سيرفرك داخل تطبيق، وبشاشة «لا يوجد اتصال» لو النت قطع. **بيتبني على جهازك** (مش من السيرفر):
- **أندرويد** (ويندوز/لينكس/ماك): تثبّت Node 18+ و JDK 17 و Android Studio، وبعدين
  `cd mobile_app` ثم `./build_android.sh https://erp.example.com "ashour" com.ashour.erp` (أو `build_android.bat ...`).
  الناتج: `android/app/build/outputs/apk/debug/app-debug.apk` (تثبّته مباشرة). للنشر على Google Play: افتح مجلد `android` في Android Studio ← Build ← Generate Signed Bundle (AAB) بمفتاح توقيع تحتفظ بيه.
- **iOS**: محتاج **Mac + Xcode + حساب Apple Developer (99$/سنة)**: `./build_ios.sh https://erp.example.com "ashour" com.ashour.erp` ثم Archive/Distribute من Xcode (TestFlight أو App Store).
- كل عميل/دومين = بناء بتاعه (الرابط بيتحط وقت البناء). غيّر `com.ashour.erp` لمعرّف خاص بيك.
- تنبيه App Store: آبل أحيانًا بترفض تطبيقات «مجرد موقع داخل غلاف» (بند 4.2). لو هتنشر هناك لازم التطبيق يقدّم قيمة واضحة؛ التثبيت كـ PWA بديل مضمون.

الأيقونات وشاشة البداية بتتولّد تلقائي من اللوجو (`tools/make_mobile_icons.py`).

## بناء APK على GitHub (من غير ما تثبّت أي أدوات)
1. ارفع المشروع لمستودع GitHub (`.gitignore` جاهز ومانع رفع البيانات والمفاتيح).
2. Settings ← Secrets and variables ← Actions ← Variables: أضف `ERP_SERVER_URL` = رابط سيرفرك (https). (أو اكتبه وقت التشغيل.)
3. تبويب **Actions** ← **android-apk** ← Run workflow. بعد دقائق تنزّل `ashour-apk` من الـ Artifacts.
4. للنسخة الموقّعة (للنشر): أضف Secrets: `ANDROID_KEYSTORE_BASE64` (`base64 -w0 my.jks`) و `ANDROID_KEYSTORE_PASSWORD` و `ANDROID_KEY_ALIAS` — احتفظ بنسخة من المفتاح، لو ضاع مش هتقدر تحدّث التطبيق على Google Play. من غير الأسرار الـ APK بيتوقّع بمفتاح مؤقت للتجربة بس.
- **ios-check**: بيتأكد إن الغلاف بيتبني على Mac (محاكي). ملف IPA للمتجر لازم يتعمل من Xcode بحسابك.
- **tests**: بيشغّل الاختبارات (SQLite + PostgreSQL) عند كل push. **docker-image**: عند عمل tag `v1.0.0` بينشر الصورة على ghcr.io.
- الـ workflows دي اتكتبت واتراجعت صياغتها بس، ما اتشغّلتش على GitHub فعليًا — لو فشلت خطوة ابعتلي اللوج وأصلحها.
