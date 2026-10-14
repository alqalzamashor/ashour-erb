"""الخصومات والكوبونات في الكاشير والمطعم.
- كوبون (نسبة/مبلغ) بحد أدنى وحد أقصى وصلاحية وعدد استخدامات، أو خصم يدوي (نسبة/مبلغ) فوق حد معيّن بيحتاج اعتماد مدير.
- الخصم بيتوزع على أسطر الفاتورة (خصم السطر قبل الضريبة) فضريبة القيمة المضافة وQR الزكاة والقيد المحاسبي بيطلعوا صح."""
import datetime
import json
import os

from . import audit
from . import services
from .db import APP_DIR, Coupon, get_session

CFG_PATH = os.path.join(APP_DIR, "discounts.json")
DEFAULTS = {"manual_enabled": True, "max_percent_free": 10.0}


def get_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


@audit.audited_config("سياسة الخصم اليدوي")
def save_config(manual_enabled, max_percent_free):
    services.require_action("coupons", "edit")
    mp = float(max_percent_free or 0)
    if mp < 0 or mp > 100:
        raise ValueError("النسبة لازم تكون بين 0 و100")
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump({"manual_enabled": bool(manual_enabled), "max_percent_free": mp}, f)


# ---------------------------------------------------------------- الكوبونات
def _cd(c):
    return {"id": c.id, "code": c.code, "name": c.name or "", "kind": c.kind, "value": float(c.value or 0), "min_order": float(c.min_order or 0),
            "max_discount": float(c.max_discount or 0), "valid_from": c.valid_from, "valid_to": c.valid_to, "usage_limit": int(c.usage_limit or 0),
            "used_count": int(c.used_count or 0), "is_active": bool(c.is_active), "notes": c.notes or ""}


def list_coupons():
    services.require_action("coupons", "view")
    with get_session() as s:
        return [_cd(c) for c in s.query(Coupon).order_by(Coupon.created_at.desc()).all()]


def save_coupon(code, name="", kind="percent", value=0, min_order=0, max_discount=0, valid_from=None, valid_to=None, usage_limit=0, is_active=True, notes="", coupon_id=None):
    services.require_action("coupons", "edit" if coupon_id else "create")
    code = (code or "").strip().upper()
    if not code:
        raise ValueError("كود الكوبون مطلوب")
    if kind not in ("percent", "fixed"):
        raise ValueError("نوع الخصم غير معروف")
    value = float(value or 0)
    if value <= 0:
        raise ValueError("قيمة الخصم لازم تكون أكبر من صفر")
    if kind == "percent" and value > 100:
        raise ValueError("النسبة لا تزيد عن 100%")
    if valid_from and valid_to and valid_to < valid_from:
        raise ValueError("تاريخ النهاية قبل البداية")
    with get_session() as s:
        dup = s.query(Coupon).filter(Coupon.code == code)
        if coupon_id:
            dup = dup.filter(Coupon.id != int(coupon_id))
        if dup.count():
            raise ValueError("الكود ده مستخدم قبل كده")
        c = s.get(Coupon, int(coupon_id)) if coupon_id else Coupon()
        if coupon_id and not c:
            raise ValueError("الكوبون غير موجود")
        c.code, c.name, c.kind, c.value = code, name or "", kind, value
        c.min_order, c.max_discount = float(min_order or 0), float(max_discount or 0)
        c.valid_from, c.valid_to, c.usage_limit = valid_from, valid_to, int(usage_limit or 0)
        c.is_active, c.notes = bool(is_active), notes or ""
        s.add(c); s.commit()
        return c.id


def delete_coupon(coupon_id):
    services.require_action("coupons", "delete")
    with get_session() as s:
        c = s.get(Coupon, int(coupon_id))
        if c:
            s.delete(c); s.commit()


def _coupon_amount(code, total):
    code = (code or "").strip().upper()
    with get_session() as s:
        c = s.query(Coupon).filter(Coupon.code == code).first()
        if not c:
            raise ValueError("كوبون غير موجود")
        c = _cd(c)
    now = datetime.datetime.now()
    if not c["is_active"]:
        raise ValueError("الكوبون موقوف")
    if c["valid_from"] and now < c["valid_from"]:
        raise ValueError(f"الكوبون يبدأ من {c['valid_from']:%Y-%m-%d}")
    if c["valid_to"] and now > datetime.datetime.combine(c["valid_to"].date(), datetime.time.max):
        raise ValueError("الكوبون منتهي الصلاحية")
    if c["usage_limit"] and c["used_count"] >= c["usage_limit"]:
        raise ValueError("الكوبون استُهلك بالكامل")
    if total < c["min_order"]:
        raise ValueError(f"الكوبون لفواتير {c['min_order']:,.2f} فأكثر")
    amt = total * c["value"] / 100.0 if c["kind"] == "percent" else c["value"]
    if c["max_discount"]:
        amt = min(amt, c["max_discount"])
    return round(min(amt, total), 2), c


def _can_approve(user):
    return services.user_has_action(user, "restaurant", "close")


def resolve(total, spec):
    """spec = {coupon, manual_kind('percent'|'amount'), manual_value, reason, approver(user dict)}. بيرجّع {amount, code, note, approved_by, coupon_id, needs_approval}.
    الكوبون والخصم اليدوي مش بيتجمعوا. الخصم اليدوي فوق حد النسبة المسموح بيحتاج مدير."""
    total = round(float(total or 0), 2)
    spec = spec or {}
    out = {"amount": 0.0, "code": "", "note": "", "approved_by": "", "coupon_id": None, "needs_approval": False, "points": 0.0}
    if spec.get("points"):
        from . import loyalty
        pts = float(spec["points"])
        amt = loyalty.redeem_amount(spec.get("customer_id"), pts, total)
        out.update(amount=min(amt, total), code="LOYALTY", note=f"استبدال {pts:g} نقطة ولاء", points=pts)
        return out
    if spec.get("coupon"):
        amt, c = _coupon_amount(spec["coupon"], total)
        out.update(amount=amt, code=c["code"], note=c["name"] or f"كوبون {c['code']}", coupon_id=c["id"])
        return out
    kind, val = spec.get("manual_kind"), float(spec.get("manual_value") or 0)
    if kind and val > 0:
        cfg = get_config()
        if not cfg["manual_enabled"]:
            raise ValueError("الخصم اليدوي موقوف - استخدم كوبون")
        amt = total * val / 100.0 if kind == "percent" else val
        if amt > total + 1e-9:
            raise ValueError("الخصم أكبر من إجمالي الفاتورة")
        amt = round(min(amt, total), 2)
        pct = (amt / total * 100) if total else 0
        out.update(amount=amt, note=(spec.get("reason") or "").strip() or "خصم يدوي")
        if pct > float(cfg["max_percent_free"]) + 1e-9:
            out["needs_approval"] = True
            appr = spec.get("approver")
            if _can_approve(services.current_user()):
                out["approved_by"] = services._current_username()
            elif appr and _can_approve(appr):
                out["approved_by"] = (appr.get("username") if isinstance(appr, dict) else getattr(appr, "username", "")) or ""
            else:
                raise ValueError(f"الخصم {pct:.1f}% فوق الحد المسموح ({cfg['max_percent_free']:g}%) - محتاج اعتماد مدير")
        if not (spec.get("reason") or "").strip() and out["needs_approval"]:
            raise ValueError("اكتب سبب الخصم")
    return out


def preview(total, spec):
    """للواجهة: نفس resolve لكن بدون رمي خطأ الاعتماد (بيرجّع needs_approval + رسالة)."""
    try:
        r = resolve(total, spec)
        r["error"] = ""
        return r
    except ValueError as ex:
        msg = str(ex)
        r = {"amount": 0.0, "code": "", "note": "", "approved_by": "", "coupon_id": None, "needs_approval": ("اعتماد مدير" in msg or "سبب الخصم" in msg), "error": msg}
        if r["needs_approval"]:
            kind, val = spec.get("manual_kind"), float(spec.get("manual_value") or 0)
            r["amount"] = round(min(total * val / 100.0 if kind == "percent" else val, total), 2)
        return r


def allocate(items, amount):
    """وزّع خصم (شامل الضريبة) على أسطر الفاتورة كخصم سطر قبل الضريبة بنسبة قيمة كل سطر؛ آخر سطر بيمتص فرق التقريب."""
    amount = round(float(amount or 0), 2)
    if amount <= 0:
        return [dict(i) for i in items]
    bases, total = [], 0.0
    for it in items:
        b = max(0.0, float(it["quantity"]) * float(it["unit_price"]) - float(it.get("discount", 0)))
        bases.append(b); total += b * (1 + float(it.get("tax_rate", 15)) / 100.0)
    if total <= 0:
        return [dict(i) for i in items]
    out = [dict(i) for i in items]
    for it, b in zip(out, bases):
        it["discount"] = round(float(it.get("discount", 0)) + amount * b / total, 4)
    target = round(items_total(items) - amount, 2)
    last = max(range(len(out)), key=lambda k: bases[k])
    for _ in range(4):                      # آخر سطر بيمتص فرق تقريب الأسطر (كل سطر بيتقرّب لسنتين)
        delta = round(items_total(out) - target, 2)
        if abs(delta) < 0.005:
            break
        out[last]["discount"] = round(max(0.0, float(out[last]["discount"]) + delta / (1 + float(out[last].get("tax_rate", 15)) / 100.0)), 4)
    if abs(round(items_total(out) - target, 2)) >= 0.005:      # تقريب الصافي والضريبة بيعمل قفزات 1-2 قرش: نجرّب إزاحات صغيرة على الأسطر لحد ما نطابق الهدف بالظبط
        order = sorted(range(len(out)), key=lambda k: -bases[k])
        base_disc = [float(o["discount"]) for o in out]
        for k in order:
            for step in (0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009, 0.01, 0.015, 0.02):
                for sign in (1, -1):
                    out[k]["discount"] = round(max(0.0, base_disc[k] + sign * step), 4)
                    if round(items_total(out), 2) == target:
                        return out
            out[k]["discount"] = base_disc[k]
    return out


def items_total(items):
    return round(sum(services._compute_line_total(float(i["quantity"]), float(i["unit_price"]), float(i.get("discount", 0)), float(i.get("tax_rate", 15)))[2] for i in items), 2)


def record_use(invoice_id, res):
    """بعد نجاح البيع: خزّن بيانات الخصم على الفاتورة وزوّد عداد استخدام الكوبون."""
    from .db import SalesInvoice
    with get_session() as s:
        inv = s.get(SalesInvoice, int(invoice_id))
        inv.promo_code, inv.promo_discount, inv.promo_note, inv.promo_approved_by = res["code"], res["amount"], res["note"][:200], res["approved_by"]
        if res.get("coupon_id"):
            c = s.get(Coupon, res["coupon_id"])
            if c:
                c.used_count = int(c.used_count or 0) + 1
        s.commit()
