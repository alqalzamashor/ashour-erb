"""تنبيهات ذكية للإدارة:
  slow     : صنف راكد (له رصيد ومفيش بيع بقاله X يوم)
  low      : صنف قارب ينفد (وصل لحد الطلب أو غطّاه بالمعدل الحالي للبيع أقل من Y يوم، أو نفد وله مبيعات)
  overdue  : عميل متأخر في السداد (فواتير عدّت تاريخ استحقاقها)
  limit    : عميل تعدّى حد الائتمان أو موقوف ائتمانيًا
ملخص يومي اختياري بيتبعت واتساب/SMS للمسؤولين عن طريق نظام الرسائل. قيم التكلفة بتتشال لو مخفية عن المستخدم."""
import datetime
import json
import os

from sqlalchemy import func

from . import audit, credit, field_access
from .db import APP_DIR, Product, StockMove, get_session

CFG_PATH = os.path.join(APP_DIR, "alerts.json")
STATE_PATH = os.path.join(APP_DIR, "alerts_state.json")
KINDS = {"slow": "صنف راكد", "low": "قارب على النفاد", "overdue": "عميل متأخر في السداد", "limit": "تعدّي حد الائتمان"}
DEFAULTS = {
    "slow_enabled": True, "slow_days": 90, "slow_min_value": 0.0,
    "low_enabled": True, "cover_days": 14, "lookback_days": 60,
    "overdue_enabled": True, "overdue_min_days": 1, "overdue_min_amount": 0.0,
    "limit_enabled": True,
    "digest_enabled": False, "digest_recipients": "", "digest_hour": 8, "digest_max_items": 12,
}
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}
_NON_STOCK = ("service",)


def get_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


@audit.audited_config("إعدادات التنبيهات الذكية")
def save_config(**kw):
    from . import services
    services.require_action("alerts", "edit")
    cfg = get_config()
    cfg.update({k: v for k, v in kw.items() if k in DEFAULTS})
    for k in ("slow_days", "cover_days", "lookback_days", "overdue_min_days", "digest_hour", "digest_max_items"):
        cfg[k] = int(cfg[k])
    for k in ("slow_min_value", "overdue_min_amount"):
        cfg[k] = float(cfg[k] or 0)
    if cfg["slow_days"] < 1 or cfg["cover_days"] < 1 or cfg["lookback_days"] < 7 or cfg["overdue_min_days"] < 0 or not 0 <= cfg["digest_hour"] <= 23:
        raise ValueError("قيم غير صحيحة (الأيام ≥ 1، فترة قياس المبيعات ≥ 7، الساعة 0-23)")
    cfg["digest_recipients"] = str(cfg["digest_recipients"] or "").strip()
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    return cfg


def _alert(kind, severity, title, detail, ref_type=None, ref_id=None, value=None, days=None):
    return {"kind": kind, "severity": severity, "title": title, "detail": detail, "ref_type": ref_type, "ref_id": ref_id, "value": value, "days": days}


def _stock_alerts(cfg, now, branch_id, show_cost):
    from . import services
    bal = services.get_balances_map(None, branch_id)
    out = []
    with get_session() as s:
        prods = s.query(Product).filter(Product.is_active.is_(True), Product.product_type.notin_(_NON_STOCK)).all()
        out_q = s.query(StockMove.product_id, func.max(StockMove.date)).filter(StockMove.direction == "out", StockMove.voided.is_(False), StockMove.reference.like("SALES:%")).group_by(StockMove.product_id)
        last_sale = {pid: d for pid, d in out_q.all()}
        in_q = s.query(StockMove.product_id, func.min(StockMove.date)).filter(StockMove.direction == "in", StockMove.voided.is_(False)).group_by(StockMove.product_id)
        first_in = {pid: d for pid, d in in_q.all()}
        since = now - datetime.timedelta(days=cfg["lookback_days"])
        sold_q = s.query(StockMove.product_id, func.sum(StockMove.quantity)).filter(StockMove.direction == "out", StockMove.voided.is_(False), StockMove.reference.like("SALES:%"), StockMove.date >= since).group_by(StockMove.product_id)
        sold = {pid: float(q or 0) for pid, q in sold_q.all()}
        for p in prods:
            b = bal.get(p.id, 0.0)
            cost = float(p.cost_price or 0)
            if cfg["slow_enabled"] and b > 0.0001:
                ref = last_sale.get(p.id) or first_in.get(p.id) or p.created_at
                age = (now - ref).days if ref else 0
                value = b * cost
                if age >= cfg["slow_days"] and value >= cfg["slow_min_value"]:
                    what = "آخر بيع قبل" if last_sale.get(p.id) else "لم يُبَع منذ دخوله قبل"
                    out.append(_alert("slow", "high" if age >= cfg["slow_days"] * 2 else "medium", f"{p.name} ({p.sku})",
                                      f"رصيد {b:g} {p.unit or ''} - {what} {age} يوم" + (f" - مجمّد {value:,.2f}" if show_cost and cost > 0 else ""),
                                      "product", p.id, value if show_cost else None, age))
            if cfg["low_enabled"]:
                rate = sold.get(p.id, 0.0) / cfg["lookback_days"]
                at_reorder = p.reorder_point and p.reorder_point > 0 and b <= p.reorder_point
                cover = (b / rate) if rate > 0 else None
                if b <= 0.0001 and rate > 0:
                    out.append(_alert("low", "high", f"{p.name} ({p.sku})", f"نفد من المخزن - بيتباع بمعدل {rate:.2f} {p.unit or ''}/يوم", "product", p.id, None, 0))
                elif at_reorder or (cover is not None and cover <= cfg["cover_days"]):
                    why = []
                    if at_reorder:
                        why.append(f"وصل لحد الطلب ({p.reorder_point:g})")
                    if cover is not None and cover <= cfg["cover_days"]:
                        why.append(f"يكفي {cover:.0f} يوم بمعدل البيع الحالي")
                    out.append(_alert("low", "high" if (cover is not None and cover <= cfg["cover_days"] / 2) or b <= 0 else "medium", f"{p.name} ({p.sku})",
                                      f"رصيد {b:g} {p.unit or ''} - " + "، ".join(why), "product", p.id, None, int(cover) if cover is not None else None))
    return out


def _customer_alerts(cfg, now):
    out = []
    ag = credit.aging("customer", now, include_details=True)
    if cfg["overdue_enabled"]:
        by = {}
        for d in ag["details"]:
            if d["days_over"] >= max(cfg["overdue_min_days"], 1):
                x = by.setdefault(d["party_id"], {"party": d["party"], "amount": 0.0, "days": 0, "n": 0})
                x["amount"] += d["due_amount"]; x["days"] = max(x["days"], d["days_over"]); x["n"] += 1
        for pid, x in by.items():
            if x["amount"] < cfg["overdue_min_amount"] or x["amount"] <= 0.005:
                continue
            sev = "high" if x["days"] > 60 else "medium" if x["days"] > 30 else "low"
            out.append(_alert("overdue", sev, x["party"], f"متأخر {x['amount']:,.2f} عن {x['n']} فاتورة - أقدمها متأخرة {x['days']} يوم", "customer", pid, x["amount"], x["days"]))
    if cfg["limit_enabled"]:
        for r in ag["rows"]:
            if r["over_limit"]:
                out.append(_alert("limit", "high", r["party"], f"الرصيد {r['balance']:,.2f} تعدّى حد الائتمان {r['credit_limit']:,.2f}", "customer", r["party_id"], r["balance"], None))
            elif r["credit_hold"] and r["balance"] > 0.005:
                out.append(_alert("limit", "medium", r["party"], f"موقوف ائتمانيًا وعليه رصيد {r['balance']:,.2f}", "customer", r["party_id"], r["balance"], None))
    return out


def compute(branch_id=None, now=None):
    """قايمة التنبيهات مرتبة بالأهمية. قيم التكلفة (مبلغ المخزون الراكد) بتتشال لو مخفية عن المستخدم الحالي."""
    cfg = get_config()
    now = now or datetime.datetime.now()
    show_cost = field_access.can_see("cost_price")
    items = _stock_alerts(cfg, now, branch_id, show_cost) + _customer_alerts(cfg, now)
    items.sort(key=lambda a: (SEV_ORDER[a["severity"]], -(a["value"] or 0), a["title"]))
    return items


def summary(branch_id=None):
    items = compute(branch_id)
    out = {k: 0 for k in KINDS}
    for a in items:
        out[a["kind"]] += 1
    out["total"] = len(items)
    out["high"] = sum(1 for a in items if a["severity"] == "high")
    return out


# ───────────────────────── الملخص اليومي (واتساب/SMS) ─────────────────────────
def _state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def send_digest(now=None, force=False):
    """بيبعت ملخص التنبيهات لأرقام المسؤولين (عبر notify). مرة في اليوم بعد ساعة الإرسال. بيرجّع عدد الرسائل."""
    from . import notify, services
    cfg = get_config()
    if not cfg["digest_enabled"] and not force:
        return 0
    recips = notify.split_phones(cfg["digest_recipients"])
    if not recips:
        return 0
    now = now or datetime.datetime.now()
    st = _state()
    if not force and (now.hour < cfg["digest_hour"] or st.get("digest_day") == now.strftime("%Y-%m-%d")):
        return 0
    items = [a for a in compute(now=now) if a["severity"] != "low" or force]
    st["digest_day"] = now.strftime("%Y-%m-%d")
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(st, f)
    if not items:
        return 0
    company = (services.get_company_settings().name or "").strip()
    n = cfg["digest_max_items"]
    lines = [f"• [{KINDS[a['kind']]}] {a['title']}: {a['detail']}" for a in items[:n]]
    more = f"\n... و{len(items) - n} تنبيه آخر" if len(items) > n else ""
    text = f"تنبيهات {company} ({now:%Y-%m-%d})\n" + "\n".join(lines) + more
    sent = 0
    for ph in recips:
        if notify.queue("alerts", ph, text, ref=f"{len(items)} تنبيه", params=[company, str(len(items))], force=force) is not None:
            sent += 1
    return sent


def run_due():
    try:
        return send_digest()
    except Exception:
        return 0
