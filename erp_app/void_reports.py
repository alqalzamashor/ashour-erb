"""تقرير الملغاة والمرتجعات: فواتير ملغاة (مبيعات/مشتريات) + مرتجعات المبيعات + طلبات/أصناف المطعم الملغاة،
على مستوى المستند وعلى مستوى الصنف."""
import datetime

from sqlalchemy.orm import joinedload

from . import services
from .db import (Customer, KitchenEvent, Product, PurchaseInvoice, SalesInvoice, SalesReturn, get_session)

KINDS = {
    "sales_void": "فاتورة مبيعات ملغاة",
    "purchase_void": "فاتورة مشتريات ملغاة",
    "sales_return": "مرتجع مبيعات",
    "rest_order_void": "طلب مطعم ملغي",
    "rest_item_void": "صنف مطعم ملغي (بعد المطبخ)",
}
ITEM_KIND_LABEL = {"sales_void": "صنف في فاتورة ملغاة", "purchase_void": "صنف في فاتورة مشتريات ملغاة", "sales_return": "صنف مرتجع",
                   "rest_order_void": "صنف في طلب مطعم ملغي", "rest_item_void": "صنف مطعم ملغي"}
GROUPS = {"none": "بدون تجميع (تفصيل)", "kind": "النوع", "product": "الصنف", "category": "الفئة", "party": "العميل / المورد", "reason": "السبب",
          "day": "اليوم", "month": "الشهر", "branch": "الفرع", "user": "بواسطة"}


def _d0(d):
    return datetime.datetime.combine(d, datetime.time.min) if d else None


def _d1(d):
    return datetime.datetime.combine(d, datetime.time.max) if d else None


def build_report(filters, kinds=None):
    """filters: date_from/date_to/branch_id/party_id/product_id/category_id/search. kinds = مفاتيح KINDS المطلوبة (None = الكل).
    بيرجّع {docs, items, kpis}. القيم شاملة الضريبة. الفاتورة الملغاة مالهاش تاريخ إلغاء محفوظ فبنستخدم تاريخ الفاتورة."""
    services.require_action("reports", "view")
    f = filters or {}
    kinds = set(kinds or KINDS)
    allowed_branches = services.user_branch_ids()
    pid = int(f["product_id"]) if f.get("product_id") else None
    cid = int(f["category_id"]) if f.get("category_id") else None
    party = int(f["party_id"]) if f.get("party_id") else None
    branch = int(f["branch_id"]) if f.get("branch_id") else None
    search = (f.get("search") or "").strip()
    docs, items = [], []

    def item_ok(prod):
        if pid and (not prod or prod.id != pid):
            return False
        if cid and (not prod or prod.category_id != cid):
            return False
        return True

    def branch_ok(bid):
        if branch:
            return bid == branch
        return not allowed_branches or bid is None or bid in allowed_branches

    with get_session() as s:
        def inv_query(Inv, party_col):
            q = s.query(Inv).options(joinedload(Inv.items), joinedload(Inv.branch)).filter(Inv.voided.is_(True))
            if f.get("date_from"):
                q = q.filter(Inv.date >= _d0(f["date_from"]))
            if f.get("date_to"):
                q = q.filter(Inv.date <= _d1(f["date_to"]))
            if party:
                q = q.filter(party_col == party)
            if search:
                q = q.filter(Inv.number.like(f"%{search}%"))
            return q.order_by(Inv.date.desc()).all()

        if "sales_void" in kinds:
            for inv in inv_query(SalesInvoice, SalesInvoice.customer_id):
                if not branch_ok(inv.branch_id):
                    continue
                its = [(i, s.get(Product, i.product_id)) for i in inv.items]
                its_f = [(i, p) for i, p in its if item_ok(p)]
                if (pid or cid) and not its_f:
                    continue
                cust = s.get(Customer, inv.customer_id) if inv.customer_id else None
                pname = cust.name if cust else "-"
                chan = "كاشير/مطعم" if inv.is_pos else "فاتورة عادية"
                docs.append({"date": inv.date, "kind": "sales_void", "number": inv.number, "ref": "", "party": pname, "branch": inv.branch.name if inv.branch else "-", "channel": chan,
                             "amount": float(inv.total or 0), "reason": "إلغاء فاتورة", "user": ""})
                for i, p in its_f:
                    items.append({"date": inv.date, "kind": "sales_void", "number": inv.number, "product": p.name if p else "-", "category": (p.category.name if p and p.category else "بدون فئة"),
                                  "party": pname, "branch": inv.branch.name if inv.branch else "-", "qty": float(i.quantity or 0), "amount": float(i.line_total or 0), "reason": "إلغاء فاتورة", "user": ""})
        if "purchase_void" in kinds and not (f.get("channel")):
            from .db import Supplier
            for inv in inv_query(PurchaseInvoice, PurchaseInvoice.supplier_id):
                if not branch_ok(inv.branch_id):
                    continue
                its = [(i, s.get(Product, i.product_id)) for i in inv.items]
                its_f = [(i, p) for i, p in its if item_ok(p)]
                if (pid or cid) and not its_f:
                    continue
                sup = s.get(Supplier, inv.supplier_id) if inv.supplier_id else None
                pname = sup.name if sup else "-"
                docs.append({"date": inv.date, "kind": "purchase_void", "number": inv.number, "ref": "", "party": pname, "branch": inv.branch.name if inv.branch else "-", "channel": "مشتريات",
                             "amount": float(inv.total or 0), "reason": "إلغاء فاتورة", "user": ""})
                for i, p in its_f:
                    items.append({"date": inv.date, "kind": "purchase_void", "number": inv.number, "product": p.name if p else "-", "category": (p.category.name if p and p.category else "بدون فئة"),
                                  "party": pname, "branch": inv.branch.name if inv.branch else "-", "qty": float(i.quantity or 0), "amount": float(i.line_total or 0), "reason": "إلغاء فاتورة", "user": ""})
        if "sales_return" in kinds:
            q = s.query(SalesReturn).options(joinedload(SalesReturn.items), joinedload(SalesReturn.invoice), joinedload(SalesReturn.customer))
            if f.get("date_from"):
                q = q.filter(SalesReturn.date >= _d0(f["date_from"]))
            if f.get("date_to"):
                q = q.filter(SalesReturn.date <= _d1(f["date_to"]))
            if party:
                q = q.filter(SalesReturn.customer_id == party)
            if search:
                q = q.filter(SalesReturn.number.like(f"%{search}%"))
            from .db import Branch
            for r in q.order_by(SalesReturn.date.desc()).all():
                if not branch_ok(r.branch_id):
                    continue
                its = [(i, s.get(Product, i.product_id)) for i in r.items]
                its_f = [(i, p) for i, p in its if item_ok(p)]
                if (pid or cid) and not its_f:
                    continue
                br = s.get(Branch, r.branch_id) if r.branch_id else None
                pname = r.customer.name if r.customer else "-"
                docs.append({"date": r.date, "kind": "sales_return", "number": r.number, "ref": r.invoice.number if r.invoice else "", "party": pname, "branch": br.name if br else "-",
                             "channel": ("كلي" if r.is_full else "جزئي") + (" - كاشير" if r.invoice and r.invoice.is_pos else ""), "amount": float(r.total or 0), "reason": r.reason or "", "user": r.processed_by or ""})
                for i, p in its_f:
                    items.append({"date": r.date, "kind": "sales_return", "number": r.number, "product": p.name if p else "-", "category": (p.category.name if p and p.category else "بدون فئة"),
                                  "party": pname, "branch": br.name if br else "-", "qty": float(i.quantity or 0), "amount": float(i.line_total or 0), "reason": r.reason or "", "user": r.processed_by or ""})
        if kinds & {"rest_order_void", "rest_item_void"}:
            q = s.query(KitchenEvent).filter(KitchenEvent.kind.in_(["order_void", "item_void"]))
            if f.get("date_from"):
                q = q.filter(KitchenEvent.created_at >= _d0(f["date_from"]))
            if f.get("date_to"):
                q = q.filter(KitchenEvent.created_at <= _d1(f["date_to"]))
            if search:
                q = q.filter(KitchenEvent.order_number.like(f"%{search}%"))
            from .db import Branch
            by_order = {}
            for e in q.order_by(KitchenEvent.created_at.desc()).all():
                k = "rest_order_void" if e.kind == "order_void" else "rest_item_void"
                if k not in kinds or not branch_ok(e.branch_id):
                    continue
                p = s.get(Product, e.product_id) if e.product_id else None
                if not item_ok(p):
                    continue
                br = s.get(Branch, e.branch_id) if e.branch_id else None
                where = f"طاولة {e.table_number}" if e.table_number else services.RESTAURANT_ORDER_TYPES.get(e.order_type, "")
                items.append({"date": e.created_at, "kind": k, "number": e.order_number, "product": e.product_name, "category": (p.category.name if p and p.category else "بدون فئة"),
                              "party": where, "branch": br.name if br else "-", "qty": float(e.quantity or 0), "amount": float(e.amount or 0), "reason": e.reason or "", "user": e.created_by or ""})
                if k == "rest_order_void":
                    d = by_order.setdefault(e.order_number, {"date": e.created_at, "kind": k, "number": e.order_number, "ref": "", "party": where, "branch": br.name if br else "-", "channel": "مطعم",
                                                              "amount": 0.0, "reason": e.reason or "", "user": e.created_by or ""})
                    d["amount"] += float(e.amount or 0)
                else:
                    docs.append({"date": e.created_at, "kind": k, "number": e.order_number, "ref": "", "party": where, "branch": br.name if br else "-", "channel": "مطعم",
                                 "amount": float(e.amount or 0), "reason": f"{e.product_name} × {e.quantity:g} - {e.reason or ''}", "user": e.created_by or ""})
            docs.extend(by_order.values())
    docs.sort(key=lambda r: r["date"], reverse=True)
    items.sort(key=lambda r: r["date"], reverse=True)
    kp = {}
    for k in KINDS:
        rows = [d for d in docs if d["kind"] == k]
        it = [i for i in items if i["kind"] == k]
        kp[k] = {"docs": len(rows), "amount": round(sum(d["amount"] for d in rows), 2), "qty": round(sum(i["qty"] for i in it), 3)}
    return {"docs": docs, "items": items, "kpis": kp}


def group_items(items, group):
    """تجميع الأصناف: بيرجّع صفوف {label, count, qty, amount, share}."""
    if group in (None, "", "none"):
        return None
    def key(i):
        d = i["date"]
        return {"kind": ITEM_KIND_LABEL.get(i["kind"], i["kind"]), "product": i["product"], "category": i["category"], "party": i["party"] or "-", "reason": i["reason"] or "-",
                "day": d.strftime("%Y-%m-%d"), "month": d.strftime("%Y-%m"), "branch": i["branch"], "user": i["user"] or "-"}[group]
    g = {}
    for i in items:
        a = g.setdefault(key(i), {"label": key(i), "count": 0, "qty": 0.0, "amount": 0.0})
        a["count"] += 1; a["qty"] += i["qty"]; a["amount"] += i["amount"]
    rows = sorted(g.values(), key=lambda r: r["label"] if group in ("day", "month") else -r["amount"])
    tot = sum(r["amount"] for r in rows) or 1.0
    for r in rows:
        r["share"] = r["amount"] / tot * 100
    return rows
