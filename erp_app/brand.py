"""هوية البرنامج: أيقونة ashour (صورة flat خضرا بحرف A وسهم صاعد) من erp_app/app_icon.png.
الاسم يتغيّر بـ ERP_BRAND_NAME (افتراضي ashour)."""
import functools
import os

NAME = os.environ.get("ERP_BRAND_NAME", "ashour")
ICON_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon.png")
BG_TOP, BG_BOTTOM = (23, 107, 83), (16, 78, 63)       # ألوان خلفية الأيقونة الخضرا (للأيقونات الـmaskable وشاشات البداية)
BG_HEX = "#124F40"


@functools.lru_cache(maxsize=1)
def _src():
    from PIL import Image
    return Image.open(ICON_FILE).convert("RGBA")


@functools.lru_cache(maxsize=32)
def mark(size=256, maskable=False):
    """PIL Image للأيقونة (صورة flat اللي رفعها المستخدم: erp_app/app_icon.png).
    maskable = تعبئة كاملة بنفس لون الخلفية + الأيقونة في المنطقة الآمنة (لأيقونات الموبايل اللي بتتقص بأي شكل)."""
    from PIL import Image
    src = _src()
    if not maskable:
        return src.resize((size, size), Image.LANCZOS)
    bg = Image.new("RGBA", (size, size))
    px = bg.load()
    c0, c1 = (25, 115, 89), (16, 75, 61)      # لون الأيقونة عند طرفها الأعلى-يسار والأسفل-يمين؛ الخلفية بتمتد بنفس الميل عشان الحافة ماتبانش
    for y in range(size):
        for x in range(size):
            t = ((x + y) / (2.0 * max(size - 1, 1)) - 0.1) / 0.8
            px[x, y] = tuple(max(0, min(255, int(c0[i] + (c1[i] - c0[i]) * t))) for i in range(3)) + (255,)
    inner = int(size * 0.80)
    ic = src.resize((inner, inner), Image.LANCZOS)
    bg.alpha_composite(ic, ((size - inner) // 2, (size - inner) // 2))
    return bg


@functools.lru_cache(maxsize=4)
def mark_png(size=128):
    import io
    b = io.BytesIO()
    mark(size).save(b, "PNG")
    return b.getvalue()


def write_assets(assets_dir):
    """بيكتب favicon + logo.svg/png في مجلد الملفات الثابتة (بيغطي favicon الافتراضي بتاع Flet)."""
    os.makedirs(os.path.join(assets_dir, "icons"), exist_ok=True)
    mark(64).save(os.path.join(assets_dir, "favicon.png"))
    mark(512).save(os.path.join(assets_dir, "icons", "logo.png"))
    mark(512).save(os.path.join(assets_dir, "icons", "loading-animation.png"))      # شاشة التحميل عند فتح البرنامج
