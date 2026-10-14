"""طبقة ترجمة وقت التشغيل: النصوص مكتوبة عربي في الكود، وعند اختيار الإنجليزية بتتبدّل نصوص العناصر (عناوين، أزرار، حقول، رؤوس جداول، تلميحات)
من قاموس erp_app/data/i18n_en.json. أي نص مالوش ترجمة بيفضل عربي (مفيش كسر). اللغة لكل جلسة (page._erp_lang) ومحفوظة لكل مستخدم."""
import json
import os
import re
import threading

LANGS = {"ar": "العربية", "en": "English"}
_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "i18n_en.json")
_lock = threading.Lock()
_cache = {"mtime": None, "d": {}, "pat": []}
_AR = re.compile("[؀-ۿ]")
_PUNCT = {"؟": "?", "،": ",", "؛": ";"}


def _load():
    try:
        m = os.path.getmtime(_DATA)
    except OSError:
        return _cache
    if _cache["mtime"] != m:
        with _lock:
            try:
                raw = json.load(open(_DATA, encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
            pats = raw.pop("__patterns__", [])
            _cache["d"] = {k.strip(): v for k, v in raw.items() if isinstance(v, str)}
            _cache["pat"] = [(re.compile(a), b) for a, b in pats]
            _cache["mtime"] = m
    return _cache


def default_lang():
    v = (os.environ.get("ERP_DEFAULT_LANG") or "ar").strip().lower()
    return v if v in LANGS else "ar"


def _prefs_path():
    from . import db
    return os.path.join(db.APP_DIR, "lang_prefs.json")


def load_user_lang(username, fallback=None):
    """لغة المستخدم المحفوظة؛ لو ما اختارش قبل كده بنستخدم fallback (اللي اختارها في صفحة الدخول) ثم الافتراضي."""
    fb = fallback if fallback in LANGS else default_lang()
    try:
        v = json.load(open(_prefs_path(), encoding="utf-8")).get(username or "")
        return v if v in LANGS else fb
    except (OSError, ValueError):
        return fb


def save_user_lang(username, lang):
    if not username or lang not in LANGS:
        return
    p = _prefs_path()
    with _lock:
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        d[username] = lang
        try:
            with open(p + ".tmp", "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            os.replace(p + ".tmp", p)
        except OSError:
            pass


def _lookup(d, s):
    if s in d:
        return d[s]
    return None


def tr(text, lang="en"):
    """يترجم نص عربي للإنجليزية. لو مالوش ترجمة بيرجع زي ما هو."""
    if lang != "en" or not isinstance(text, str) or not text or not _AR.search(text):
        return text
    c = _load()
    d = c["d"]
    core = re.sub(r"[ \t]{2,}", " ", text.strip())          # مسافات مضاعفة (أسماء حسابات قديمة)
    lead, trail = text[:len(text) - len(text.lstrip())], text[len(text.rstrip()):]
    r = d.get(core)
    if r is not None:
        return lead + r + trail
    # علامات الترقيم في الآخر: "الاسم:" "هل أنت متأكد؟" "جاري التحميل..."
    m = re.match(r"^(.*?)(\s*(?::|؟|\.\.\.|…|!|\.)+)$", core, re.S)
    if m and m.group(1) in d:
        return lead + d[m.group(1)] + _PUNCT.get(m.group(2).strip(), m.group(2)) + trail
    for rx, rep in c["pat"]:
        mm = rx.fullmatch(core)
        if mm:
            try:
                return lead + mm.expand(rep) + trail
            except (re.error, IndexError):
                break
    # "تسمية: قيمة" / "تسمية - قيمة" / "تسمية | قيمة" / "تسمية (قيمة)" : نترجم كل جزء له ترجمة
    for sep in ("  •  ", " • ", ": ", " - ", " | ", " — ", " / ", "، "):
        if sep in core:
            parts = core.split(sep)
            out = [tr(p, "en") for p in parts]
            if out != parts:
                return lead + sep.replace("، ", ", ").join(out) + trail
    m = re.match(r"^(.*?)\s*\((.*)\)$", core, re.S)
    if m:
        inner = tr(m.group(2))
        if inner == m.group(2) and ("(" + m.group(2) + ")") in d:
            inner = d["(" + m.group(2) + ")"].strip("()")
        head = tr(m.group(1))
        if head != m.group(1) or inner != m.group(2):
            return lead + f"{head} ({inner})" + trail
    # تغطية بالعبارات: أطول عبارة متتالية موجودة في القاموس، والرموز اللي مفيهاش عربي (أرقام/أكواد) بتعدّي زي ما هي. كله أو لا شيء.
    words = core.split(" ")
    if 1 < len(words) <= 12:
        out, i, ok = [], 0, True
        while i < len(words):
            for n in range(min(5, len(words) - i), 0, -1):
                ph = " ".join(words[i:i + n])
                if ph in d:
                    out.append(d[ph]); i += n
                    break
            else:
                if _AR.search(words[i]):
                    ok = False
                    break
                out.append(words[i]); i += 1
        if ok and out:
            return lead + " ".join(out) + trail
    return text


# ---------------------------------------------------------------- تطبيق الترجمة على عناصر Flet
_STR_FIELDS = ("label", "hint_text", "helper_text", "error_text", "prefix_text", "suffix_text", "counter_text",
               "tooltip", "semantics_label", "title", "subtitle", "content", "text", "placeholder_text")


def page_lang():
    try:
        from flet.controls.context import _context_page
        pg = _context_page.get(None)
        v = getattr(pg, "_erp_lang", None)
        return v if isinstance(v, str) else "ar"
    except Exception:      # noqa: BLE001
        return "ar"


def translate_control(c):
    """بتتنادى قبل كل تحديث لأي عنصر (من theme). بتبدّل النصوص المعروضة بس، وعمرها ما بتلمس قيم الحقول (value)."""
    if page_lang() != "en":
        return
    import flet as ft
    def g(name):
        try:
            return getattr(c, name, None)
        except Exception:      # noqa: BLE001
            return None
    if isinstance(c, ft.Text):
        v = g("value")
        if isinstance(v, str):
            n = tr(v)
            if n != v:
                c.value = n
    is_opt = type(c).__name__ == "DropdownOption"
    for f in _STR_FIELDS:
        v = g(f)
        if isinstance(v, str) and v:
            n = tr(v)
            if n != v:
                if is_opt and f == "text" and g("key") is None:
                    c.key = v              # المفتاح الأصلي يفضل عربي (القيمة اللي الكود بيقارن بيها)
                setattr(c, f, n)
