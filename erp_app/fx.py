"""عملات متعددة: عملات وأسعار صرف، فواتير/سندات بعملة أجنبية، وإعادة تقييم لأرصدة العملاء والموردين بالأجنبي.
المبدأ: كل الدفاتر بالعملة الأساسية. الفاتورة الأجنبية بتتسجّل بالأساسي بسعر يوم الفاتورة وبيتحفظ معاها المبلغ الأجنبي. سند القبض/الصرف الأجنبي بيتسجّل بسعر يوم السند.
فرق العملة (محقق وغير محقق) بيتحسب في «إعادة التقييم»: رصيد الطرف بالأجنبي × سعر اليوم − رصيده الدفتري بالأساسي → قيد فرق عملة.
لما الرصيد الأجنبي يتسدّد بالكامل بسعر مختلف، إعادة التقييم بتصفّر الباقي بالأساسي (= الفرق المحقق)."""
import datetime
import json
import os

from . import audit
from .db import (APP_DIR, Currency, Customer, ExchangeRate, FxRevaluation, Payment, PurchaseInvoice, SalesInvoice, Supplier, get_session)

CFG_PATH = os.path.join(APP_DIR, "fx.json")


def _cfg():
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cfg(d):
    c = _cfg(); c.update(d)
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(c, f)


def base_code():
    return (_cfg().get("base") or "SAR").upper()


def is_foreign(code):
    return bool(code) and str(code).upper() != base_code()


def _day_end(d):
    if isinstance(d, datetime.datetime):
        return d
    return datetime.datetime.combine(d, datetime.time(23, 59, 59))


def ensure_seed():
    with get_session() as s:
        if not s.query(Currency).filter(Currency.code == base_code()).first():
            s.add(Currency(code=base_code(), name="الريال السعودي" if base_code() == "SAR" else base_code(), symbol="ر.س" if base_code() == "SAR" else "", is_base=True)); s.commit()


def list_currencies(active_only=False):
    ensure_seed()
    with get_session() as s:
        q = s.query(Currency)
        if active_only:
            q = q.filter(Currency.is_active.is_(True))
        rows = q.order_by(Currency.is_base.desc(), Currency.code).all()
        s.expunge_all()
        return rows


def add_currency(code, name="", symbol=""):
    from . import services
    services.require_action("currencies", "edit")
    code = (code or "").strip().upper()
    if not (2 <= len(code) <= 5 and code.isalpha()):
        raise ValueError("رمز العملة حروف إنجليزية (مثل USD)")
    ensure_seed()
    with get_session() as s:
        if s.query(Currency).filter(Currency.code == code).count():
            raise ValueError("العملة موجودة بالفعل")
        s.add(Currency(code=code, name=name or code, symbol=symbol or code)); s.commit()


def set_rate(code, rate_date, rate):
    """سعر 1 وحدة أجنبية بالعملة الأساسية في تاريخ."""
    from . import services
    services.require_action("currencies", "edit")
    code = (code or "").upper()
    if not is_foreign(code):
        raise ValueError("اختار عملة أجنبية")
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        raise ValueError("السعر لازم يكون رقم")
    if rate <= 0 or rate > 1e7:
        raise ValueError("سعر الصرف لازم يكون أكبر من صفر")
    d = rate_date if isinstance(rate_date, datetime.datetime) else datetime.datetime.combine(rate_date, datetime.time(0, 0))
    with get_session() as s:
        if not s.query(Currency).filter(Currency.code == code).count():
            raise ValueError("العملة غير معرّفة")
        r = s.query(ExchangeRate).filter(ExchangeRate.currency_code == code, ExchangeRate.rate_date == d).first()
        if r:
            r.rate = rate
        else:
            s.add(ExchangeRate(currency_code=code, rate_date=d, rate=rate))
        s.commit()


def get_rate(code, on=None):
    code = (code or "").upper()
    if not is_foreign(code):
        return 1.0
    on = _day_end(on or datetime.date.today())
    with get_session() as s:
        r = s.query(ExchangeRate).filter(ExchangeRate.currency_code == code, ExchangeRate.rate_date <= on).order_by(ExchangeRate.rate_date.desc()).first()
        if not r:
            raise ValueError(f"مفيش سعر صرف مسجّل للعملة {code} - سجّله من شاشة العملات")
        return float(r.rate)


def list_rates(code=None, limit=200):
    with get_session() as s:
        q = s.query(ExchangeRate)
        if code:
            q = q.filter(ExchangeRate.currency_code == code.upper())
        rows = q.order_by(ExchangeRate.rate_date.desc(), ExchangeRate.id.desc()).limit(limit).all()
        s.expunge_all()
        return rows


def resolve_rate(currency, exchange_rate=None, on=None):
    """سعر الصرف المستخدم: المُدخل يدويًا (لو فيه) وإلا آخر سعر مسجّل."""
    if exchange_rate not in (None, "", 0):
        r = float(exchange_rate)
        if r <= 0:
            raise ValueError("سعر الصرف لازم يكون أكبر من صفر")
        return r
    return get_rate(currency, on)


def convert_items(items, discount, currency, exchange_rate=None, on=None):
    """يحوّل أسعار الأسطر (وخصم الفاتورة) من الأجنبي للأساسي. بيرجّع (items, discount, info{currency, rate, foreign_total})."""
    from . import services
    currency = currency.upper()
    if not is_foreign(currency):
        return items, discount, None
    with get_session() as s:
        if not s.query(Currency).filter(Currency.code == currency, Currency.is_active.is_(True)).count():
            raise ValueError("العملة غير معرّفة أو موقوفة")
    rate = resolve_rate(currency, exchange_rate, on)
    foreign = max(0.0, sum(services._compute_line_total(float(i["quantity"]), float(i["unit_price"]), float(i.get("discount", 0)), float(i.get("tax_rate", 15)))[2] for i in items) - float(discount or 0))
    out = []
    for it in items:
        d = dict(it)
        d["unit_price"] = round(float(it["unit_price"]) * rate, 6)
        d["discount"] = round(float(it.get("discount", 0)) * rate, 4)
        out.append(d)
    return out, round(float(discount or 0) * rate, 4), {"currency": currency, "rate": rate, "foreign_total": round(foreign, 2)}


def stamp_invoice(kind, invoice_id, info):
    M = SalesInvoice if kind == "sales" else PurchaseInvoice
    with get_session() as s:
        inv = s.get(M, int(invoice_id))
        inv.currency, inv.exchange_rate, inv.foreign_total = info["currency"], info["rate"], info["foreign_total"]
        inv.notes = ((inv.notes or "") + f" [{info['currency']} {info['foreign_total']:,.2f} @ {info['rate']:g}]").strip()
        s.commit()


# ------------------------------------------------------------------ حسابات فروق العملة
def _free_code(s, start):
    from .db import Account
    n = start
    while s.query(Account).filter(Account.code == str(n)).count():
        n += 1
    return str(n)


def ensure_accounts():
    """بيرجّع (gain_id, loss_id): من الإعداد، أو يدوّر بالاسم، أو يعمل الحسابين."""
    from . import services
    from .db import Account
    c = _cfg()
    with get_session() as s:
        ids = {}
        for key, name, typ, parent_code, start in (("gain", "أرباح فروق العملة", "income", "400000", 440001), ("loss", "خسائر فروق العملة", "expense", "520000", 520084)):
            a = s.get(Account, c.get(f"{key}_account_id")) if c.get(f"{key}_account_id") else None
            if not a:
                a = s.query(Account).filter(Account.name == name).first()
            if not a:
                parent = s.query(Account).filter(Account.code == parent_code).first()
                code = _free_code(s, start)
                aid = services.create_account(code, name, typ, parent_id=parent.id if parent else None, cash_flow_type="operating")
                a = s.get(Account, aid)
            ids[key] = a.id
        _save_cfg({"gain_account_id": ids["gain"], "loss_account_id": ids["loss"]})
        return ids["gain"], ids["loss"]


# ------------------------------------------------------------------ إعادة التقييم
def _pair_balances(s):
    """{(party_type, party_id, currency): (foreign_balance, book_base)} من المستندات الأجنبية (غير الملغاة) + تسويات سابقة."""
    out = {}

    def add(k, f, b):
        a = out.get(k, (0.0, 0.0)); out[k] = (a[0] + f, a[1] + b)
    for i in s.query(SalesInvoice).filter(SalesInvoice.currency.isnot(None), SalesInvoice.voided.isnot(True), SalesInvoice.customer_id.isnot(None)).all():
        add(("customer", i.customer_id, i.currency), float(i.foreign_total or 0), float(i.total or 0))
    for i in s.query(PurchaseInvoice).filter(PurchaseInvoice.currency.isnot(None), PurchaseInvoice.voided.isnot(True), PurchaseInvoice.supplier_id.isnot(None)).all():
        add(("supplier", i.supplier_id, i.currency), float(i.foreign_total or 0), float(i.total or 0))
    for p in s.query(Payment).filter(Payment.currency.isnot(None), Payment.voided.isnot(True), Payment.partner_id.isnot(None), Payment.partner_type.in_(["customer", "supplier"])).all():
        ok = (p.partner_type == "customer" and p.payment_type == "receipt") or (p.partner_type == "supplier" and p.payment_type == "payment")
        if ok:
            add((p.partner_type, p.partner_id, p.currency), -float(p.foreign_amount or 0), -float(p.amount or 0))
    for r in s.query(FxRevaluation).all():
        add((r.party_type, r.party_id, r.currency), 0.0, float(r.adjustment or 0))
    return out


def preview(on_date=None):
    from . import services
    services.require_action("currencies", "view")
    on_date = on_date or datetime.date.today()
    rows = []
    with get_session() as s:
        names = {("customer", c.id): c.name for c in s.query(Customer).all()}
        names.update({("supplier", x.id): x.name for x in s.query(Supplier).all()})
        for (pt, pid, cur), (fb, bk) in sorted(_pair_balances(s).items(), key=lambda x: (x[0][0], x[0][1], x[0][2])):
            rate = get_rate(cur, on_date)
            target = round(fb * rate, 2)
            adj = round(target - bk, 2)
            if abs(adj) < 0.01:
                continue
            rows.append({"party_type": pt, "party_id": pid, "party": names.get((pt, pid), "-"), "currency": cur, "foreign_balance": round(fb, 2), "rate": rate,
                         "book_before": round(bk, 2), "target": target, "adjustment": adj})
    return rows


@audit.audited_bulk("إعادة تقييم العملات")
def post_revaluation(on_date=None):
    """يرحّل قيد فروق العملة لكل طرف/عملة فيه فرق. بيرجّع {'count', 'gain', 'loss', 'entry_id'}. تشغيله مرتين بنفس اليوم مفيهوش أثر تاني."""
    from . import services
    services.require_action("currencies", "post")
    on_date = on_date or datetime.date.today()
    rows = preview(on_date)
    if not rows:
        return {"count": 0, "gain": 0.0, "loss": 0.0, "entry_id": None}
    gain_id, loss_id = ensure_accounts()
    cfg = services._accounting_settings()
    with get_session() as s:
        cust = {c.id: c.account_id for c in s.query(Customer).all()}
        sup = {x.id: x.account_id for x in s.query(Supplier).all()}
    lines, gain, loss = [], 0.0, 0.0
    for r in rows:
        adj = r["adjustment"]
        if r["party_type"] == "customer":
            acc = cust.get(r["party_id"]) or cfg.receivable_account_id
            if adj > 0:
                lines.append({"account_id": acc, "debit": adj, "description": f"فرق عملة {r['currency']} - {r['party']}"}); gain += adj
            else:
                lines.append({"account_id": acc, "credit": -adj, "description": f"فرق عملة {r['currency']} - {r['party']}"}); loss += -adj
        else:       # مورد: الالتزام زاد = خسارة
            acc = sup.get(r["party_id"]) or cfg.payable_account_id
            if adj > 0:
                lines.append({"account_id": acc, "credit": adj, "description": f"فرق عملة {r['currency']} - {r['party']}"}); loss += adj
            else:
                lines.append({"account_id": acc, "debit": -adj, "description": f"فرق عملة {r['currency']} - {r['party']}"}); gain += -adj
    net = round(gain - loss, 2)
    if net > 0:
        lines.append({"account_id": gain_id, "credit": net, "description": "أرباح فروق العملة"})
    elif net < 0:
        lines.append({"account_id": loss_id, "debit": -net, "description": "خسائر فروق العملة"})
    d = on_date if isinstance(on_date, datetime.datetime) else datetime.datetime.combine(on_date, datetime.time(12, 0))
    eid = services.create_journal_entry(lines, reference="FX-REVAL", description=f"إعادة تقييم العملات بتاريخ {d:%Y-%m-%d}", source_type="fx_revaluation", entry_date=d)
    me = (services.current_user() or {}).get("username", "")
    with get_session() as s:
        for r in rows:
            s.add(FxRevaluation(reval_date=d, party_type=r["party_type"], party_id=r["party_id"], currency=r["currency"], foreign_balance=r["foreign_balance"], rate=r["rate"],
                                book_before=r["book_before"], adjustment=r["adjustment"], journal_entry_id=eid if isinstance(eid, int) else getattr(eid, "id", None), created_by=me))
        s.commit()
    return {"count": len(rows), "gain": round(gain, 2), "loss": round(loss, 2), "entry_id": eid}
