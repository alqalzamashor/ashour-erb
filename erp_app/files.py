"""ملفات المتصفح ↔ السيرفر: روابط تنزيل مؤقتة لملفات اتعملت على السيرفر (تقارير/نسخ/PDF)، ومجلد الرفع المؤقت للملفات اللي المستخدم يرفعها.
كل رابط تنزيل = مجلد باسم عشوائي (128 بت) جوه مجلد assets بيتخدم كملفات ثابتة، وبيتمسح تلقائي بعد مدة قصيرة.
الرفع بيروح لـ upload_dir بتاع Flet (عبر رابط موقّع ينتهي بسرعة)."""
import os
import re
import shutil
import time
import uuid

from .db import APP_DIR

ASSETS_DIR = os.environ.get("ERP_ASSETS_DIR") or os.path.join(APP_DIR, "web_assets")
UPLOAD_DIR = os.environ.get("ERP_UPLOAD_DIR") or os.path.join(APP_DIR, "uploads")
DL_SUBDIR = "dl"
DL_TTL = int(os.environ.get("ERP_DOWNLOAD_TTL", "900"))          # 15 دقيقة
UPLOAD_TTL = int(os.environ.get("ERP_UPLOAD_TTL", "86400"))      # يوم
for _d in (os.path.join(ASSETS_DIR, DL_SUBDIR), UPLOAD_DIR):
    os.makedirs(_d, exist_ok=True)


FONT_FILE = "NotoSansArabic-Regular.ttf"
FONT_URL = "/fonts/" + FONT_FILE


def ensure_fonts():
    """ينسخ الخط العربي المرفق (Noto Sans Arabic - SIL OFL) لمجلد الملفات الثابتة عشان الواجهة تشتغل من غير إنترنت عند المتصفحات."""
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_fonts")
    dst = os.path.join(ASSETS_DIR, "fonts")
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(src):
        if not os.path.exists(os.path.join(dst, f)):
            shutil.copyfile(os.path.join(src, f), os.path.join(dst, f))
    from . import sounds
    sounds.publish_sounds(ASSETS_DIR)
    try:
        ensure_pwa()
    except Exception as ex:
        print('تعذّر تجهيز ملفات تثبيت التطبيق (PWA):', ex)


def ensure_secret_key():
    """مفتاح توقيع روابط الرفع (FLET_SECRET_KEY): بيتولّد مرة ويتحفظ في مجلد البيانات (صلاحيات 600) عشان يثبت بعد إعادة التشغيل."""
    if os.environ.get("FLET_SECRET_KEY"):
        return
    import secrets
    p = os.path.join(APP_DIR, "secret_key.txt")
    try:
        with open(p, encoding="utf-8") as f:
            k = f.read().strip()
    except OSError:
        k = ""
    if not k:
        k = secrets.token_urlsafe(32)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(k)
    os.environ["FLET_SECRET_KEY"] = k


def safe_name(name):
    name = os.path.basename(str(name or "file")).replace("\\", "_")
    name = re.sub(r"[^\w.\- ()؀-ۿ]", "_", name).strip(" .") or "file"
    return name[:120]


def publish_download(path):
    """ينسخ ملف لمجلد التنزيل المؤقت وبيرجّع الرابط النسبي (من جذر الموقع) اللي المتصفح يفتحه."""
    token = uuid.uuid4().hex
    d = os.path.join(ASSETS_DIR, DL_SUBDIR, token)
    os.makedirs(d)
    name = safe_name(os.path.basename(path))
    shutil.copyfile(path, os.path.join(d, name))
    return f"/{DL_SUBDIR}/{token}/{name}"


def upload_path(rel):
    """المسار الحقيقي لملف مرفوع (rel = اللي رجّعه make_upload_target)، بدون السماح بالخروج من مجلد الرفع."""
    p = os.path.realpath(os.path.join(UPLOAD_DIR, rel))
    if not p.startswith(os.path.realpath(UPLOAD_DIR) + os.sep):
        raise ValueError("مسار رفع غير صالح")
    return p


def make_upload_target(file_name):
    """اسم نسبي فريد لملف سيتم رفعه: <uuid>/<اسم آمن>."""
    return f"{uuid.uuid4().hex}/{safe_name(file_name)}"


def keep_upload(path, dest_dir):
    """ينقل ملف مرفوع لمكان دائم (مثلاً مرفقات الأصناف) ويرجّع المسار الجديد."""
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"{uuid.uuid4().hex[:8]}_{safe_name(os.path.basename(path))}")
    shutil.copyfile(path, dest)
    return dest


def _sweep(root, ttl):
    n, now = 0, time.time()
    if not os.path.isdir(root):
        return 0
    for e in os.listdir(root):
        p = os.path.join(root, e)
        try:
            if now - os.path.getmtime(p) > ttl:
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
                n += 1
        except OSError:
            pass
    return n


def cleanup():
    """تنظيف روابط التنزيل المنتهية والملفات المرفوعة القديمة. بيرجّع عدد اللي اتمسح."""
    return _sweep(os.path.join(ASSETS_DIR, DL_SUBDIR), DL_TTL) + _sweep(UPLOAD_DIR, UPLOAD_TTL)


def _pwa_icon(size, maskable=False):
    """أيقونة التطبيق = لوجو ashour (erp_app/brand.py). maskable = هامش أمان أكبر."""
    from . import brand
    return brand.mark(size, maskable).copy()


def ensure_pwa():
    """manifest.json عربي + أيقونات في مجلد الملفات الثابتة: المتصفح بيعرض "تثبيت التطبيق" / "إضافة للشاشة الرئيسية" على الموبايل."""
    import json
    from . import theme
    icons_dir = os.path.join(ASSETS_DIR, "icons")
    os.makedirs(icons_dir, exist_ok=True)
    entries = []
    for size in (192, 512):
        for mask in (False, True):
            name = f"icon-{'maskable-' if mask else ''}{size}.png"
            path = os.path.join(icons_dir, name)
            _pwa_icon(size, mask).save(path)       # بنكتبها كل مرة: عشان أي أيقونة قديمة تتبدّل باللوجو الحالي
            e = {"src": f"icons/{name}", "sizes": f"{size}x{size}", "type": "image/png"}
            if mask:
                e["purpose"] = "maskable"
            entries.append(e)
    from . import brand
    brand.write_assets(ASSETS_DIR)
    name = os.environ.get("ERP_APP_NAME", brand.NAME + " ERP")
    manifest = {
        "name": name, "short_name": os.environ.get("ERP_APP_SHORT_NAME", brand.NAME),
        "description": "نظام محاسبة ومخازن ومبيعات ونقاط بيع",
        "id": "/", "start_url": ".", "scope": ".", "display": "standalone", "orientation": "any",
        "lang": "ar", "dir": "rtl", "background_color": brand.BG_HEX, "theme_color": theme.PRIMARY,
        "prefer_related_applications": False, "icons": entries,
    }
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "install_page.html"), encoding="utf-8") as f:
            page_html = f.read().replace("__NAME__", brand.NAME).replace("__COLOR__", theme.PRIMARY)
        with open(os.path.join(ASSETS_DIR, "install.html"), "w", encoding="utf-8") as f:
            f.write(page_html)
    except OSError:
        pass
    with open(os.path.join(ASSETS_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # index.html: الصفحة الأصلية من Flet من غير viewport، فالموبايل كان بيعرضها بعرض 980px. بنضيف viewport + لون المتصفح + اسم التطبيق.
    try:
        import flet_web
        src = os.path.join(os.path.dirname(flet_web.__file__), "web", "index.html")
        html = open(src, encoding="utf-8").read()
        meta = ('<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n  '
                f'<meta name="theme-color" content="{theme.PRIMARY}">\n  ')
        if "name=\"viewport\"" not in html:
            html = html.replace("<meta name=\"description\"", meta + "<meta name=\"description\"", 1)
        html = html.replace('content="Flet">', 'content="%s">' % brand.NAME)
        html = html.replace('<meta name="apple-mobile-web-app-status-bar-style" content="black">',
                            '<meta name="apple-mobile-web-app-capable" content="yes">\n  <meta name="apple-mobile-web-app-status-bar-style" content="default">', 1)
        html = html.replace('<link rel="apple-touch-icon" href="icons/apple-touch-icon-192.png">',
                            '<link rel="apple-touch-icon" href="icons/apple-touch-icon-180.png">\n  <link rel="apple-touch-icon" sizes="180x180" href="icons/apple-touch-icon-180.png">', 1).replace('<html>', '<html lang="ar" dir="rtl">', 1)
        with open(os.path.join(ASSETS_DIR, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)
        brand.mark(180, True).save(os.path.join(icons_dir, "apple-touch-icon-180.png"))   # iOS بيحط خلفية سودا لو الأيقونة شفافة => ماسكابل (تعبئة كاملة)
        for n in ("apple-touch-icon-192.png",):
            dst = os.path.join(icons_dir, n)
            _pwa_icon(192, False).save(dst)
    except ImportError:
        pass
