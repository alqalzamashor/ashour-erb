// node configure.js https://erp.example.com "ashour" com.ashour.erp
// بيكتب capacitor.config.json برابط سيرفرك واسم التطبيق ومعرّفه، ويجهّز الأيقونة والصفحة الاحتياطية (من غير نت).
const fs = require('fs'), path = require('path');
const [url, name = 'ashour', id = 'com.ashour.erp'] = process.argv.slice(2);
if (!url || !/^https:\/\//.test(url)) { console.error('اكتب رابط السيرفر بـ https:// (مطلوب لـ iOS وأندرويد).\nمثال: node configure.js https://erp.example.com "ashour" com.ashour.erp'); process.exit(1); }
const clean = url.replace(/\/+$/, '');
fs.mkdirSync('www', { recursive: true });
fs.writeFileSync('capacitor.config.json', JSON.stringify({
  appId: id, appName: name, webDir: 'www',
  server: { url: clean, cleartext: false, allowNavigation: [new URL(clean).host] },
  android: { allowMixedContent: false },
  ios: { contentInset: 'always' },
  plugins: { SplashScreen: { launchShowDuration: 800, backgroundColor: '#124F40' }, StatusBar: { style: 'DEFAULT', backgroundColor: '#FFFFFF' } }
}, null, 2));
fs.writeFileSync(path.join('www', 'index.html'), `<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><body style="font-family:sans-serif;text-align:center;padding:40px"><h2>${name}</h2><p>لا يوجد اتصال بالسيرفر. تأكد من الإنترنت ثم أعد فتح التطبيق.</p><button onclick="location.href='${clean}'" style="padding:12px 24px;font-size:16px">إعادة المحاولة</button></body></html>`);
console.log('تم. الخطوة التالية: شغّل build_android.sh (أو build_android.bat) / للـ iOS راجع README_MOBILE_AR.md');
