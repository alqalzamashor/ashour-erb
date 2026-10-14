"""سجل التدقيق التلقائي: بيسجّل كل إنشاء/تعديل/حذف على أي جدول (ماعدا المستثنى) مع المستخدم والوقت وقيم الحقول قبل وبعد.
بيتفعّل بـ install() مرة واحدة، والمستخدم الحالي بييجي من set_user_getter()."""
import datetime
import json

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from .db import AuditLog, SessionLocal

_user_getter = lambda: ""
_installed = False

SKIP_TABLES = {"audit_logs", "chat_messages", "chat_members", "chat_conversations", "kitchen_events"}
CHILD_SUFFIXES = ("_items", "_lines", "_batches", "_attachments", "_splits", "_payments")     # بنود تابعة: بنسجّل التعديل والحذف بس (الإنشاء مع الرأس)
MASK_FIELDS = {"password_hash", "password"}
SKIP_FIELDS = {"zatca_response"}
LABEL_ATTRS = ("number", "name", "code", "username", "sku", "title")

TABLE_NAMES = {
    "coupons": "الكوبونات", "loyalty_txns": "حركات نقاط الولاء", "sales_invoices": "فواتير المبيعات", "purchase_invoices": "فواتير المشتريات", "sales_returns": "مرتجعات المبيعات", "products": "الأصناف", "customers": "العملاء", "suppliers": "الموردون",
    "accounts": "الحسابات", "journal_entries": "القيود اليومية", "receipts_payments": "سندات القبض والصرف", "payments": "سندات القبض والصرف", "users": "المستخدمون", "employees": "الموظفون",
    "pos_sessions": "جلسات نقاط البيع", "pos_terminals": "ماكينات نقاط البيع", "payment_methods": "طرق الدفع", "restaurant_orders": "طلبات المطعم", "restaurant_order_items": "بنود طلبات المطعم",
    "restaurant_tables": "طاولات المطعم", "stock_moves": "حركات المخزون", "categories": "الفئات", "branches": "الفروع", "cost_centers": "مراكز التكلفة", "company_settings": "إعدادات الشركة",
    "fiscal_periods": "الفترات المالية", "price_lists": "قوائم الأسعار", "fixed_assets": "الأصول الثابتة", "bank_accounts": "حسابات البنوك", "payment_providers": "مزودو الدفع",
}


def set_user_getter(fn):
    global _user_getter
    _user_getter = fn


def _username():
    try:
        u = _user_getter()
        if isinstance(u, dict):
            return u.get("username", "") or ""
        return u or ""
    except Exception:
        return ""


def _val(v):
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.strftime("%Y-%m-%d %H:%M" if isinstance(v, datetime.datetime) else "%Y-%m-%d")
    if v is None or isinstance(v, (int, float, bool)):
        return v
    s = str(v)
    return s if len(s) <= 120 else s[:117] + "..."


def _label(obj):
    for a in LABEL_ATTRS:
        v = getattr(obj, a, None)
        if v:
            return str(v)[:200]
    return ""


def _is_child(table):
    return table.endswith(CHILD_SUFFIXES)


def _collect(session, flush_context, instances):
    user = _username()
    if not user:
        return          # عمليات النظام قبل الدخول (إنشاء الجداول والبيانات الافتراضية) ما بتتسجلش
    pending = session.info.setdefault("audit_pending", [])
    now = datetime.datetime.now()
    for obj in list(session.new):
        t = getattr(obj, "__tablename__", None)
        if not t or t in SKIP_TABLES or _is_child(t):
            continue
        pending.append({"obj": obj, "at": now, "user": user, "action": "create", "table": t, "changes": None})
    for obj in list(session.dirty):
        t = getattr(obj, "__tablename__", None)
        if not t or t in SKIP_TABLES or not session.is_modified(obj, include_collections=False):
            continue
        ch = {}
        for attr in inspect(obj).mapper.column_attrs:
            if attr.key in SKIP_FIELDS:
                continue
            h = inspect(obj).attrs[attr.key].history
            if h.has_changes() and h.added:
                old = h.deleted[0] if h.deleted else None
                new = h.added[0]
                if old == new:
                    continue
                ch[attr.key] = ["***", "***"] if attr.key in MASK_FIELDS else [_val(old), _val(new)]
        if ch:
            pending.append({"obj": obj, "at": now, "user": user, "action": "update", "table": t, "changes": ch})
    for obj in list(session.deleted):
        t = getattr(obj, "__tablename__", None)
        if not t or t in SKIP_TABLES:
            continue
        snap = {}
        for attr in inspect(obj).mapper.column_attrs:
            if attr.key in MASK_FIELDS or attr.key in SKIP_FIELDS or attr.key == "id":
                continue
            v = getattr(obj, attr.key, None)
            if v not in (None, "", 0, 0.0, False):
                snap[attr.key] = _val(v)
            if len(snap) >= 8:
                break
        pending.append({"obj": obj, "at": now, "user": user, "action": "delete", "table": t, "changes": snap, "rid": getattr(obj, "id", None), "label": _label(obj)})


def _write(session, flush_context):
    pending = session.info.pop("audit_pending", None)
    if not pending:
        return
    rows = []
    for p in pending:
        obj = p["obj"]
        rid = p.get("rid") if p["action"] == "delete" else getattr(obj, "id", None)
        label = p.get("label") if p["action"] == "delete" else _label(obj)
        ch = p["changes"]
        rows.append({"at": p["at"], "username": p["user"], "action": p["action"], "table_name": p["table"], "record_id": rid, "label": label or "",
                     "changes": json.dumps(ch, ensure_ascii=False) if ch else ""})
    session.connection().execute(AuditLog.__table__.insert(), rows)


def install():
    global _installed
    if _installed:
        return
    event.listen(Session, "before_flush", _collect)
    event.listen(Session, "after_flush", _write)
    _installed = True


def log_event(action, label="", changes="", table="", username=None):
    """حدث يدوي (دخول، دخول فاشل، نسخ احتياطي، استرجاع...)."""
    with SessionLocal() as s:
        s.connection().execute(AuditLog.__table__.insert(), [{"at": datetime.datetime.now(), "username": username if username is not None else _username(), "action": action,
                                                              "table_name": table, "record_id": None, "label": label[:200], "changes": changes if isinstance(changes, str) else json.dumps(changes, ensure_ascii=False)}])
        s.commit()


# ---------------------------------------------------------------- عمليات مش بتعدّي على ORM
_SECRET_HINTS = ("password", "pass", "secret", "token")


def _flat(d, prefix=""):
    out = {}
    for k, v in (d or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flat(v, key + "."))
        else:
            out[key] = v
    return out


def diff_config(before, after):
    b, a = _flat(before), _flat(after)
    ch = {}
    for k in sorted(set(a) | set(b)):
        if b.get(k) != a.get(k):
            masked = any(h in k.lower() for h in _SECRET_HINTS)
            ch[k] = ["***", "***"] if masked else [_val(b.get(k)) if not isinstance(b.get(k), (list, dict)) else str(b.get(k))[:120],
                                                  _val(a.get(k)) if not isinstance(a.get(k), (list, dict)) else str(a.get(k))[:120]]
    return ch


def audited_config(label, getter="get_config"):
    """ديكوريتر لدوال save_config اللي بتحفظ في ملفات json: بيسجّل الإعداد اللي اتغيّر (قبل ← بعد)."""
    import functools

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            g = fn.__globals__[getter]
            try:
                before = g()
            except Exception:
                before = {}
            res = fn(*a, **kw)
            try:
                ch = diff_config(before, g())
                if ch:
                    log_event("config", label=label, changes=ch)
            except Exception:
                pass
            return res
        return wrapper
    return deco


def audited_bulk(label):
    """ديكوريتر للعمليات الجماعية (استيراد/تنظيف): بيسجّل حدث واحد بملخّص النتيجة (أو الفشل)."""
    import functools

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            try:
                res = fn(*a, **kw)
            except Exception as ex:
                try:
                    log_event("bulk", label=label, changes={"النتيجة": "فشل", "السبب": str(ex)[:150]})
                except Exception:
                    pass
                raise
            try:
                info = {}
                if isinstance(res, dict):
                    for k, v in res.items():
                        if isinstance(v, (int, float)):
                            info[k] = v
                        elif isinstance(v, (list, tuple, dict)):
                            info[k] = len(v)
                log_event("bulk", label=label, changes=info or {"النتيجة": "تم"})
            except Exception:
                pass
            return res
        return wrapper
    return deco
