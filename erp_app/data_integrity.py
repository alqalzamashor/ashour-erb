"""فحص سلامة البيانات: بيدوّر على أخطاء محاسبية/تشغيلية (قيود غير متوازنة، فواتير بلا قيد، مخزون سالب، تكرار، أرصدة ولاء غير مطابقة...)
للقراءة فقط - مابيصلّحش حاجة، بيطلّع قايمة بالأسباب عشان المحاسب يراجعها."""
import datetime

from sqlalchemy import case, func

from . import services
from .db import (Customer, JournalEntry, JournalEntryLine, LoyaltyTxn, PosSession, Product, PurchaseInvoice, RestaurantOrder, SalesInvoice,
                 SalesInvoiceItem, StockMove, Supplier, get_session)

LIMIT = 50          # أقصى عدد أسطر بتتعرض لكل فحص
TOL = 0.01


def _item(ref, detail):
    return {"ref": str(ref), "detail": detail}


def _check(key, title, severity, items, total=None, hint=""):
    return {"key": key, "title": title, "severity": severity, "count": total if total is not None else len(items), "items": items[:LIMIT], "hint": hint}


def run(only=None):
    """بيرجّع {checks:[...], errors, warnings, ran_at}. only = مجموعة مفاتيح فحوص (اختياري)."""
    services.require_action("data_integrity", "view")
    out = []
    with get_session() as s:
        def want(k):
            return not only or k in only

        # 1) قيود غير متوازنة
        if want("unbalanced"):
            rows = (s.query(JournalEntry.id, JournalEntry.number, func.coalesce(func.sum(JournalEntryLine.debit), 0.0), func.coalesce(func.sum(JournalEntryLine.credit), 0.0))
                    .outerjoin(JournalEntryLine, JournalEntryLine.entry_id == JournalEntry.id).group_by(JournalEntry.id).all())
            bad = [r for r in rows if abs(r[2] - r[3]) > TOL]
            out.append(_check("unbalanced", "قيود غير متوازنة (مدين ≠ دائن)", "error",
                              [_item(r[1], f"مدين {r[2]:,.2f} / دائن {r[3]:,.2f} (فرق {r[2] - r[3]:,.2f})") for r in bad], len(bad), "راجع القيد وعدّله أو اعكسه."))
        # 2) قيود بلا أسطر
        if want("empty_entries"):
            ids = [r for r in s.query(JournalEntry.number).outerjoin(JournalEntryLine, JournalEntryLine.entry_id == JournalEntry.id).group_by(JournalEntry.id).having(func.count(JournalEntryLine.id) == 0).all()]
            out.append(_check("empty_entries", "قيود بلا أسطر", "error", [_item(r[0], "قيد فاضي") for r in ids], len(ids)))
        # 3) مسودات قيود
        if want("draft_entries"):
            ds = s.query(JournalEntry.number, JournalEntry.date).filter(JournalEntry.posted.is_(False)).order_by(JournalEntry.date).all()
            out.append(_check("draft_entries", "قيود غير مرحّلة (مسودة)", "warn", [_item(r[0], f"{r[1]:%Y-%m-%d}") for r in ds], len(ds), "مش داخلة في التقارير المالية لحد ما تترحّل."))
        # 4) فواتير مبيعات بلا قيد
        if want("sales_no_entry"):
            have = {r[0] for r in s.query(JournalEntry.source_id).filter(JournalEntry.source_type == "sales_invoice").all()}
            inv = s.query(SalesInvoice.id, SalesInvoice.number, SalesInvoice.total).filter(SalesInvoice.voided.is_(False), SalesInvoice.total > 0).all()
            bad = [r for r in inv if r[0] not in have]
            out.append(_check("sales_no_entry", "فواتير مبيعات بلا قيد محاسبي", "error", [_item(r[1], f"إجمالي {r[2]:,.2f}") for r in bad], len(bad)))
        if want("purchase_no_entry"):
            have = {r[0] for r in s.query(JournalEntry.source_id).filter(JournalEntry.source_type == "purchase_invoice").all()}
            inv = s.query(PurchaseInvoice.id, PurchaseInvoice.number, PurchaseInvoice.total).filter(PurchaseInvoice.voided.is_(False), PurchaseInvoice.total > 0).all()
            bad = [r for r in inv if r[0] not in have]
            out.append(_check("purchase_no_entry", "فواتير مشتريات بلا قيد محاسبي", "error", [_item(r[1], f"إجمالي {r[2]:,.2f}") for r in bad], len(bad)))
        # 5) إجمالي الفاتورة ≠ مجموع بنودها
        if want("sales_total_mismatch"):
            sums = dict(s.query(SalesInvoiceItem.invoice_id, func.coalesce(func.sum(SalesInvoiceItem.line_total), 0.0)).group_by(SalesInvoiceItem.invoice_id).all())
            inv = s.query(SalesInvoice.id, SalesInvoice.number, SalesInvoice.total, SalesInvoice.discount).filter(SalesInvoice.voided.is_(False)).all()
            bad = [(r, sums.get(r[0], 0.0)) for r in inv if r[0] in sums and abs(sums[r[0]] - (r[2] or 0)) > 0.05 and abs(sums[r[0]] - (r[2] or 0)) > (r[3] or 0) * 1.2 + 0.05]
            out.append(_check("sales_total_mismatch", "إجمالي فاتورة مبيعات ≠ مجموع بنودها", "error",
                              [_item(r[1], f"الإجمالي {r[2]:,.2f} / مجموع البنود {t:,.2f}") for r, t in bad], len(bad)))
        # 6) إجمالي القيود
        if want("trial_balance"):
            d, c = s.query(func.coalesce(func.sum(JournalEntryLine.debit), 0.0), func.coalesce(func.sum(JournalEntryLine.credit), 0.0)).join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id).filter(JournalEntry.posted.is_(True)).one()
            out.append(_check("trial_balance", "ميزان المراجعة (إجمالي المدين = إجمالي الدائن)", "error",
                              [_item("الإجمالي", f"مدين {d:,.2f} / دائن {c:,.2f} (فرق {d - c:,.2f})")] if abs(d - c) > TOL else [], 1 if abs(d - c) > TOL else 0))
        # 7) مخزون سالب
        if want("negative_stock"):
            signed = func.sum(case((StockMove.direction == "in", StockMove.quantity), (StockMove.direction == "out", -StockMove.quantity), else_=0))
            rows = (s.query(Product.sku, Product.name, signed).join(StockMove, StockMove.product_id == Product.id)
                    .filter(StockMove.voided.is_(False), Product.product_type.in_(["simple", "manufactured"])).group_by(Product.id).having(signed < -1e-6).all())
            out.append(_check("negative_stock", "أصناف برصيد مخزون سالب", "error", [_item(f"{r[0]} - {r[1]}", f"الرصيد {r[2]:,.3f}") for r in rows], len(rows), "غالبًا بيع قبل استلام أو حركة مش مسجّلة - اعمل تسوية جردية."))
        # 8) بيع تحت التكلفة
        if want("below_cost"):
            rows = s.query(Product.sku, Product.name, Product.cost_price, Product.sale_price).filter(
                Product.is_active.is_(True), Product.can_be_sold.is_(True), Product.product_type == "simple", Product.cost_price > 0, Product.sale_price < Product.cost_price).all()
            out.append(_check("below_cost", "أصناف سعر بيعها أقل من تكلفتها", "warn", [_item(f"{r[0]} - {r[1]}", f"تكلفة {r[2]:,.2f} / بيع {r[3]:,.2f}") for r in rows], len(rows)))
        # 9) تكرار عملاء/موردين
        for key, model, title in (("dup_customers", Customer, "عملاء مكررين (نفس الرقم الضريبي أو الهاتف)"), ("dup_suppliers", Supplier, "موردين مكررين (نفس الرقم الضريبي أو الهاتف)")):
            if not want(key):
                continue
            items = []
            for col, lbl in ((model.vat_number, "الرقم الضريبي"), (model.phone, "الهاتف")):
                for val, n in s.query(col, func.count(model.id)).filter(col.isnot(None), col != "").group_by(col).having(func.count(model.id) > 1).all():
                    names = [r[0] for r in s.query(model.name).filter(col == val).limit(4).all()]
                    items.append(_item(f"{lbl}: {val}", f"{n} سجلات: " + "، ".join(names)))
            out.append(_check(key, title, "warn", items, len(items)))
        # 10) أرصدة الولاء
        if want("loyalty"):
            led = dict(s.query(LoyaltyTxn.customer_id, func.coalesce(func.sum(LoyaltyTxn.points), 0.0)).group_by(LoyaltyTxn.customer_id).all())
            bad = [(c, led.get(c.id, 0.0)) for c in s.query(Customer).filter((Customer.loyalty_points != 0) | Customer.id.in_(list(led) or [0])).all() if abs((c.loyalty_points or 0) - led.get(c.id, 0.0)) > 0.01]
            neg = s.query(Customer.name, Customer.loyalty_points).filter(Customer.loyalty_points < 0).all()
            items = [_item(c.name, f"الرصيد {c.loyalty_points or 0:,.0f} / مجموع الحركات {t:,.0f}") for c, t in bad] + [_item(n, f"رصيد سالب {p:,.0f}") for n, p in neg]
            out.append(_check("loyalty", "أرصدة نقاط الولاء غير مطابقة للحركات", "error", items, len(items)))
        # 11) جلسات كاشير متروكة
        if want("old_sessions"):
            lim = datetime.datetime.now() - datetime.timedelta(days=2)
            rows = s.query(PosSession.number, PosSession.opened_by, PosSession.opened_at).filter(PosSession.state == "open", PosSession.opened_at < lim).all()
            out.append(_check("old_sessions", "جلسات كاشير مفتوحة من أكتر من يومين", "warn", [_item(r[0], f"فتحها {r[1]} في {r[2]:%Y-%m-%d %H:%M}") for r in rows], len(rows), "اقفلها عشان تتسوّى النقدية."))
        # 12) طلبات مطعم مفتوحة قديمة
        if want("old_orders"):
            lim = datetime.datetime.now() - datetime.timedelta(days=1)
            col = getattr(RestaurantOrder, "created_at", None) or getattr(RestaurantOrder, "opened_at", None)
            rows = s.query(RestaurantOrder.number, col).filter(RestaurantOrder.state == "open", col < lim).all() if col is not None else []
            out.append(_check("old_orders", "طلبات مطعم مفتوحة من أكتر من يوم", "warn", [_item(r[0], f"من {r[1]:%Y-%m-%d %H:%M}") for r in rows], len(rows), "طاولات محجوزة بدون سبب - ادفعها أو ألغها."))
    return {"checks": out, "errors": sum(1 for c in out if c["severity"] == "error" and c["count"]), "warnings": sum(1 for c in out if c["severity"] == "warn" and c["count"]), "ran_at": datetime.datetime.now()}
