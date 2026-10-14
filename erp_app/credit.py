"""أعمار الديون (العملاء والموردين) وحدود الائتمان.
رصيد العميل = فواتيره غير الملغاة − ما اتسدد وقت البيع (كاشير) − سندات القبض غير الملغاة − مرتجعات اتردّت «على حساب العميل».
التسديدات بتتوزّع على أقدم فاتورة أولًا (FIFO)؛ والعمر بيتحسب من تاريخ الاستحقاق = تاريخ الفاتورة + مهلة العميل (credit_days).
أي زيادة في السداد عن الفواتير بتظهر «رصيد دائن» (دفعة مقدمة)."""
import datetime
import json
import os

from . import approvals, audit
from .db import APP_DIR, Customer, Payment, PurchaseInvoice, SalesInvoice, SalesReturn, Supplier, get_session

CFG_PATH = os.path.join(APP_DIR, "credit.json")
DEFAULTS = {"enabled": True, "block_overdue_days": 0}      # block_overdue_days: امنع الآجل لو فيه فاتورة متأخرة أكتر من كده (0 = مقفول)
BUCKETS = [("current", "غير مستحق"), ("d30", "1-30"), ("d60", "31-60"), ("d90", "61-90"), ("d90p", "أكثر من 90")]


class CreditLimitError(approvals.ApprovalRequired):
    pass


def get_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


@audit.audited_config("إعدادات الائتمان")
def save_config(**kw):
    from . import services
    services.require_action("credit", "edit")
    cfg = get_config()
    cfg.update({k: v for k, v in kw.items() if k in DEFAULTS})
    cfg["block_overdue_days"] = int(cfg["block_overdue_days"] or 0)
    if cfg["block_overdue_days"] < 0:
        raise ValueError("عدد الأيام لا يكون سالبًا")
    cfg["enabled"] = bool(cfg["enabled"])
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return cfg


def _bucket(days_over):
    return "current" if days_over <= 0 else "d30" if days_over <= 30 else "d60" if days_over <= 60 else "d90" if days_over <= 90 else "d90p"


def _open_items(s, party_type, as_of, party_id=None):
    """بيرجّع (docs, credits_by_party): docs = فواتير {id,party_id,number,date,due,amount}، credits = مجموع التسديدات لكل طرف."""
    from . import services
    cust = party_type == "customer"
    M = SalesInvoice if cust else PurchaseInvoice
    col = M.customer_id if cust else M.supplier_id
    q = s.query(M).filter(col.isnot(None), M.voided.isnot(True), M.date <= as_of)
    if party_id:
        q = q.filter(col == int(party_id))
    invs = q.order_by(M.date, M.id).all()
    days = {c.id: int(c.credit_days or 0) for c in s.query(Customer).all()} if cust else {}
    settled = {}
    if cust:
        for i, _n, a in services._invoice_settlements(s, invs):
            settled[i.id] = settled.get(i.id, 0.0) + a
    docs = []
    for i in invs:
        pid = i.customer_id if cust else i.supplier_id
        amt = max(0.0, float(i.total or 0) - settled.get(i.id, 0.0))
        if amt > 0.005:
            docs.append({"id": i.id, "party_id": pid, "number": i.number, "date": i.date, "due": i.date + datetime.timedelta(days=days.get(pid, 0)), "amount": amt})
    credits = {}
    pq = s.query(Payment).filter(Payment.partner_type == ("customer" if cust else "supplier"), Payment.payment_type == ("receipt" if cust else "payment"),
                                 Payment.voided.isnot(True), Payment.date <= as_of)
    if party_id:
        pq = pq.filter(Payment.partner_id == int(party_id))
    for p in pq.all():
        if p.partner_id:
            credits[p.partner_id] = credits.get(p.partner_id, 0.0) + float(p.amount or 0)
    if cust:
        rq = s.query(SalesReturn).filter(SalesReturn.refund_method == "على حساب العميل", SalesReturn.date <= as_of, SalesReturn.customer_id.isnot(None))
        if party_id:
            rq = rq.filter(SalesReturn.customer_id == int(party_id))
        for r in rq.all():
            credits[r.customer_id] = credits.get(r.customer_id, 0.0) + float(r.total or 0)
    return docs, credits


def aging(party_type="customer", as_of=None, party_id=None, include_details=True):
    """{'rows': [طرف: balance + أعمار], 'details': [فواتير مفتوحة], 'totals': {...}}. الأعمار حسب أيام التأخر عن الاستحقاق."""
    as_of = as_of or datetime.datetime.now()
    if isinstance(as_of, datetime.date) and not isinstance(as_of, datetime.datetime):
        as_of = datetime.datetime.combine(as_of, datetime.time(23, 59, 59))
    with get_session() as s:
        docs, credits = _open_items(s, party_type, as_of, party_id)
        Model = Customer if party_type == "customer" else Supplier
        info = {x.id: x for x in s.query(Model).all()}
        by = {}
        for d in docs:
            by.setdefault(d["party_id"], []).append(d)
        rows, details = [], []
        for pid in sorted(set(by) | set(credits)):
            left = credits.get(pid, 0.0)
            b = {k: 0.0 for k, _ in BUCKETS}
            for d in by.get(pid, []):
                use = min(left, d["amount"]); left -= use
                rem = d["amount"] - use
                if rem <= 0.005:
                    continue
                over = (as_of - d["due"]).days
                bk = _bucket(over)
                b[bk] += rem
                details.append({"party_id": pid, "party": info[pid].name if pid in info else "-", "number": d["number"], "date": d["date"], "due": d["due"],
                                "days_over": max(0, over), "bucket": bk, "due_amount": round(rem, 2), "amount": round(d["amount"], 2)})
            bal = sum(b.values())
            if bal <= 0.005 and left <= 0.005:
                continue
            c = info.get(pid)
            lim = float(getattr(c, "credit_limit", 0) or 0) if party_type == "customer" and c else 0.0
            rows.append(dict({"party_id": pid, "party": c.name if c else "-", "phone": getattr(c, "phone", "") if c else "", "balance": round(bal - left, 2), "unapplied": round(left, 2),
                              "credit_limit": lim, "over_limit": bool(lim > 0 and bal - left > lim + 0.005), "credit_hold": bool(getattr(c, "credit_hold", False)) if c else False},
                             **{k: round(v, 2) for k, v in b.items()}))
        rows.sort(key=lambda r: -r["balance"])
        tot = {k: round(sum(r[k] for r in rows), 2) for k in [k for k, _ in BUCKETS] + ["balance", "unapplied"]}
        return {"rows": rows, "details": details if include_details else [], "totals": tot, "as_of": as_of}


def customer_balance(customer_id, as_of=None):
    """الرصيد المستحق على العميل (موجب = عليه)، ومنه المتأخر عن الاستحقاق."""
    r = aging("customer", as_of=as_of, party_id=customer_id, include_details=False)["rows"]
    if not r:
        return {"balance": 0.0, "overdue": 0.0, "max_days_over": 0}
    x = r[0]
    with get_session() as s:
        docs, credits = _open_items(s, "customer", as_of or datetime.datetime.now(), customer_id)
    left, mx = credits.get(int(customer_id), 0.0), 0
    for d in docs:
        use = min(left, d["amount"]); left -= use
        if d["amount"] - use > 0.005:
            mx = max(mx, ((as_of or datetime.datetime.now()) - d["due"]).days)
    return {"balance": x["balance"], "overdue": round(x["d30"] + x["d60"] + x["d90"] + x["d90p"], 2), "max_days_over": max(0, mx)}


def check_sale(customer_id, credit_amount, approval_id=None):
    """قبل فاتورة فيها جزء آجل: يمنع لو العميل موقوف أو هيتعدّى حد الائتمان أو عليه متأخرات أكتر من المسموح.
    بيعدّي لو المستخدم معاه صلاحية credit:override (ويتسجّل في التدقيق) أو لو فيه موافقة معتمدة (approval_id)."""
    from . import services
    cfg = get_config()
    credit_amount = float(credit_amount or 0)
    if not cfg["enabled"] or not customer_id or credit_amount <= 0.005:
        return None
    with get_session() as s:
        c = s.get(Customer, int(customer_id))
        if not c:
            return None
        limit, hold, name = float(c.credit_limit or 0), bool(c.credit_hold), c.name
    reasons = []
    bal = None
    if hold:
        reasons.append(f"العميل «{name}» موقوف عن البيع الآجل")
    if limit > 0 or cfg["block_overdue_days"] > 0:
        bal = customer_balance(customer_id)
    if limit > 0 and bal["balance"] + credit_amount > limit + 0.005:
        reasons.append(f"هيتعدّى حد الائتمان: الرصيد الحالي {bal['balance']:,.2f} + الفاتورة {credit_amount:,.2f} أكبر من الحد {limit:,.2f}")
    if cfg["block_overdue_days"] > 0 and bal["max_days_over"] > cfg["block_overdue_days"]:
        reasons.append(f"عليه فواتير متأخرة {bal['max_days_over']} يوم (الحد المسموح {cfg['block_overdue_days']})")
    if not reasons:
        return None
    msg = " - ".join(reasons)
    if services.user_has_action(services._get_user(), "credit", "override"):
        audit.log_event("credit_override", label=f"تجاوز ائتمان: {name}", changes=msg)
        return msg
    try:
        aid = approvals.guard("credit_limit", credit_amount, str(customer_id), summary=f"{name}: {msg}"[:480], approval_id=approval_id, force=True)
    except approvals.ApprovalRequired as ex:
        err = CreditLimitError("credit_limit", credit_amount, str(customer_id), f"{name}: {msg}")
        err.args = (msg + " — محتاج موافقة مدير",)
        raise err from ex
    audit.log_event("credit_override", label=f"بيع آجل بموافقة: {name}", changes=f"{msg} (موافقة #{aid})")
    return msg
