"""برنامج ولاء العملاء: نقاط على كل بيع (كاشير/مطعم) للعميل العضو، تُستبدل كخصم عند الدفع، وتتعكس نسبيًا مع المرتجع.
الإعدادات في loyalty.json: earn_per_currency (نقطة لكل 1 ريال من صافي الفاتورة)، redeem_value (قيمة النقطة بالريال)، min_redeem (أقل نقاط للاستبدال)، max_redeem_pct (أقصى نسبة من الفاتورة)."""
import datetime
import json
import math
import os

from sqlalchemy import func

from . import audit
from . import services
from .db import APP_DIR, Customer, LoyaltyTxn, SalesInvoice, get_session

CFG_PATH = os.path.join(APP_DIR, "loyalty.json")
DEFAULTS = {"enabled": False, "earn_per_currency": 1.0, "redeem_value": 0.05, "min_redeem": 100, "max_redeem_pct": 50.0}
KINDS = {"earn": "اكتساب", "redeem": "استبدال", "reverse": "عكس (مرتجع)", "refund": "استرداد نقاط (مرتجع)", "adjust": "تسوية"}


def get_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


@audit.audited_config("إعدادات برنامج الولاء")
def save_config(**kw):
    services.require_action("loyalty", "edit")
    cfg = get_config(); cfg.update({k: v for k, v in kw.items() if k in DEFAULTS})
    cfg["enabled"] = bool(cfg["enabled"])
    for k in ("earn_per_currency", "redeem_value", "min_redeem", "max_redeem_pct"):
        cfg[k] = float(cfg[k] or 0)
        if cfg[k] < 0:
            raise ValueError("القيم لازم تكون صفر أو أكبر")
    if cfg["max_redeem_pct"] > 100:
        raise ValueError("أقصى نسبة استبدال لا تزيد عن 100%")
    if cfg["enabled"] and (cfg["earn_per_currency"] <= 0 or cfg["redeem_value"] <= 0):
        raise ValueError("معدل الاكتساب وقيمة النقطة لازم يكونوا أكبر من صفر")
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return cfg


def _by():
    return services._current_username()


def _txn(s, c, kind, points, invoice=None, ref="", note=""):
    c.loyalty_points = round(float(c.loyalty_points or 0) + points, 3)
    s.add(LoyaltyTxn(customer_id=c.id, kind=kind, points=points, balance_after=c.loyalty_points, invoice_id=invoice.id if invoice else None,
                     ref=ref or (invoice.number if invoice else ""), note=note[:200], by=_by()))


def balance(customer_id):
    if not customer_id:
        return 0.0
    with get_session() as s:
        c = s.get(Customer, int(customer_id))
        return float(c.loyalty_points or 0) if c else 0.0


def customer_info(customer_id):
    """للواجهة: {member, balance, redeem_value, min_redeem, max_pct} أو None لو البرنامج متوقف/العميل مش عضو."""
    cfg = get_config()
    if not cfg["enabled"] or not customer_id:
        return None
    with get_session() as s:
        c = s.get(Customer, int(customer_id))
        if not c or not c.loyalty_enabled:
            return None
        return {"member": True, "name": c.name, "balance": float(c.loyalty_points or 0), "redeem_value": cfg["redeem_value"], "min_redeem": cfg["min_redeem"], "max_pct": cfg["max_redeem_pct"]}


def redeem_amount(customer_id, points, total):
    """قيمة خصم الاستبدال بالريال (مع التحقق من الرصيد والحد الأدنى والحد الأقصى كنسبة من الفاتورة)."""
    cfg = get_config(); points = float(points or 0)
    if not cfg["enabled"]:
        raise ValueError("برنامج الولاء متوقف")
    info = customer_info(customer_id)
    if not info:
        raise ValueError("العميل مش عضو في برنامج الولاء")
    if points <= 0:
        raise ValueError("اكتب عدد النقاط")
    if points > info["balance"] + 1e-9:
        raise ValueError(f"رصيد النقاط {info['balance']:g} فقط")
    if points < cfg["min_redeem"]:
        raise ValueError(f"أقل استبدال {cfg['min_redeem']:g} نقطة")
    amt = round(points * cfg["redeem_value"], 2)
    cap = round(float(total) * cfg["max_redeem_pct"] / 100.0, 2)
    if amt > cap + 1e-9:
        raise ValueError(f"الحد الأقصى للاستبدال {cfg['max_redeem_pct']:g}% من الفاتورة ({cap:,.2f} = {math.floor(cap / cfg['redeem_value'])} نقطة)")
    return amt


def after_sale(invoice_id, customer_id, redeemed_points=0.0):
    """بعد نجاح بيع: خصم النقاط المستبدلة وإضافة النقاط المكتسبة على صافي الفاتورة. لو العميل مش عضو/البرنامج متوقف: لا شيء."""
    cfg = get_config()
    if not cfg["enabled"] or not customer_id:
        return {"earned": 0, "redeemed": 0, "balance": 0}
    with get_session() as s:
        c = s.get(Customer, int(customer_id))
        if not c or not c.loyalty_enabled:
            return {"earned": 0, "redeemed": 0, "balance": 0}
        inv = s.get(SalesInvoice, int(invoice_id))
        red = float(redeemed_points or 0)
        if red > 0:
            _txn(s, c, "redeem", -red, inv, note="استبدال نقاط كخصم")
        earned = math.floor(float(inv.total or 0) * cfg["earn_per_currency"] + 1e-9)
        if earned > 0:
            _txn(s, c, "earn", earned, inv, note=f"على فاتورة {inv.total:,.2f}")
        s.commit()
        return {"earned": earned, "redeemed": red, "balance": float(c.loyalty_points or 0)}


def on_return(invoice_id, refund_total, ref=""):
    """مرتجع: بيعكس النقاط المكتسبة نسبيًا (مع سقف الرصيد المتاح) ويرجّع نسبة من النقاط المستبدلة."""
    with get_session() as s:
        inv = s.get(SalesInvoice, int(invoice_id))
        if not inv or not inv.total:
            return
        txns = s.query(LoyaltyTxn).filter(LoyaltyTxn.invoice_id == inv.id).all()
        if not txns:
            return
        c = s.get(Customer, txns[0].customer_id)
        earned = sum(t.points for t in txns if t.kind == "earn"); red = -sum(t.points for t in txns if t.kind == "redeem")
        rev = -sum(t.points for t in txns if t.kind == "reverse"); ref_ = sum(t.points for t in txns if t.kind == "refund")
        share = min(1.0, float(refund_total) / float(inv.total))
        rev_pts = min(round(earned * share), earned - rev, max(0.0, float(c.loyalty_points or 0)))
        if rev_pts > 0:
            _txn(s, c, "reverse", -rev_pts, inv, ref, "عكس نقاط بسبب مرتجع")
        back = min(round(red * share), red - ref_)
        if back > 0:
            _txn(s, c, "refund", back, inv, ref, "إرجاع نقاط مستبدلة بسبب مرتجع")
        s.commit()


def adjust(customer_id, points, note):
    services.require_action("loyalty", "edit")
    points = float(points or 0)
    if not points:
        raise ValueError("اكتب عدد النقاط (موجب أو سالب)")
    if not (note or "").strip():
        raise ValueError("اكتب سبب التسوية")
    with get_session() as s:
        c = s.get(Customer, int(customer_id))
        if not c:
            raise ValueError("العميل غير موجود")
        if float(c.loyalty_points or 0) + points < 0:
            raise ValueError("الرصيد لا يكفي للخصم")
        _txn(s, c, "adjust", points, None, "", note)
        s.commit()


def set_member(customer_id, enabled):
    services.require_action("loyalty", "edit")
    with get_session() as s:
        c = s.get(Customer, int(customer_id))
        if not c:
            raise ValueError("العميل غير موجود")
        c.loyalty_enabled = bool(enabled); s.commit()


def list_members(search=None, only_enabled=True):
    services.require_action("loyalty", "view")
    with get_session() as s:
        q = s.query(Customer)
        if only_enabled:
            q = q.filter(Customer.loyalty_enabled.is_(True))
        if search:
            like = f"%{search.strip()}%"; q = q.filter((Customer.name.like(like)) | (Customer.phone.like(like)))
        rows = q.order_by(Customer.name).all()
        earned = dict(s.query(LoyaltyTxn.customer_id, func.coalesce(func.sum(LoyaltyTxn.points), 0.0)).filter(LoyaltyTxn.kind == "earn").group_by(LoyaltyTxn.customer_id).all())
        return [{"id": c.id, "name": c.name, "phone": c.phone or "", "member": bool(c.loyalty_enabled), "balance": float(c.loyalty_points or 0), "earned_total": float(earned.get(c.id, 0))} for c in rows]


def list_txns(customer_id, limit=300):
    services.require_action("loyalty", "view")
    with get_session() as s:
        return [{"at": t.at, "kind": t.kind, "kind_label": KINDS.get(t.kind, t.kind), "points": t.points, "balance": t.balance_after, "ref": t.ref, "note": t.note, "by": t.by}
                for t in s.query(LoyaltyTxn).filter(LoyaltyTxn.customer_id == int(customer_id)).order_by(LoyaltyTxn.id.desc()).limit(limit).all()]


def invoice_summary(invoice_id):
    """للإيصال: النقاط المكتسبة والمستبدلة والرصيد بعد الفاتورة."""
    with get_session() as s:
        ts = s.query(LoyaltyTxn).filter(LoyaltyTxn.invoice_id == int(invoice_id), LoyaltyTxn.kind.in_(["earn", "redeem"])).order_by(LoyaltyTxn.id).all()
        if not ts:
            return None
        return {"earned": sum(t.points for t in ts if t.kind == "earn"), "redeemed": -sum(t.points for t in ts if t.kind == "redeem"), "balance": ts[-1].balance_after}
