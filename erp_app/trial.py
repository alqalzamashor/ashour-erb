"""الترخيص داخل النسخة (تجربة / اشتراك مدفوع): ملف trial.json في مجلد البيانات (بتكتبه بوابة التجارب). لو مفيش ملف = نسخة عادية بدون حد ولا انتهاء.
{"expires": "2026-11-10", "plan": "trial|basic|pro|...", "plan_label": "...", "paid": false, "max_users": 5, "max_branches": 2 (أو null = بلا حد), "company":..., "owner":..., "phone":...}"""
import datetime
import json
import os
import urllib.error
import urllib.request

from .db import APP_DIR

PATH = os.path.join(APP_DIR, "trial.json")
EXPIRED_MSG = "انتهت الفترة التجريبية/الاشتراك لهذه النسخة. أدخل كود تفعيل أو تواصل مع مزوّد الخدمة."


def load():
    try:
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write(expires, **info):
    cur = load() or {}
    cur.update(info)
    cur["expires"] = expires.isoformat() if hasattr(expires, "isoformat") else str(expires)
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False)
    os.replace(tmp, PATH)


def days_left(today=None):
    """الأيام المتبقية (0 = آخر يوم، سالب = منتهية). None لو النسخة مش مرتبطة بترخيص."""
    t = load()
    if not t:
        return None
    try:
        exp = datetime.date.fromisoformat(str(t["expires"])[:10])
    except (KeyError, ValueError):
        return None
    return (exp - (today or datetime.date.today())).days


def is_expired(today=None):
    d = days_left(today)
    return d is not None and d < 0


def is_paid():
    t = load()
    return bool(t and t.get("paid"))


def info():
    """ملخص للعرض: None لو مفيش ترخيص."""
    t = load()
    if not t:
        return None
    return {"plan": t.get("plan", "trial"), "plan_label": t.get("plan_label") or ("اشتراك" if t.get("paid") else "تجريبية"), "paid": bool(t.get("paid")),
            "expires": str(t.get("expires", ""))[:10], "days_left": days_left(), "max_users": t.get("max_users"), "max_branches": t.get("max_branches"),
            "company": t.get("company", "")}


def limit(kind):
    """حد الباقة ('users' أو 'branches') أو None لو بلا حد."""
    t = load()
    if not t:
        return None
    v = t.get("max_" + kind)
    return int(v) if v not in (None, "") else None


def check_limit(kind, current, label):
    """يرمي ValueError لو العدد الحالي وصل لحد الباقة (قبل الإضافة)."""
    lim = limit(kind)
    if lim is not None and current >= lim:
        raise ValueError(f"وصلت للحد الأقصى من {label} في باقتك ({lim}). رقّي الباقة أو فعّل كود جديد من «الاشتراك».")


def can_activate():
    return bool(os.environ.get("ERP_PORTAL_URL") and os.environ.get("ERP_TENANT_SLUG"))


def activate(code):
    """تفعيل كود اشتراك: بيكلّم البوابة (نفس السيرفر) اللي بتحدّث ملف الترخيص. بيرجّع dict النتيجة أو يرمي ValueError برسالة مفهومة."""
    if not can_activate():
        raise ValueError("النسخة دي مش مرتبطة ببوابة اشتراكات")
    body = json.dumps({"slug": os.environ["ERP_TENANT_SLUG"], "code": str(code or "")}).encode()
    req = urllib.request.Request(os.environ["ERP_PORTAL_URL"].rstrip("/") + "/api/activate", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("error")
        except Exception:      # noqa: BLE001
            msg = None
        raise ValueError(msg or f"تعذر التفعيل ({e.code})")
    except (urllib.error.URLError, OSError):
        raise ValueError("تعذر الوصول لخدمة التفعيل، حاول بعد شوية")
