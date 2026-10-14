"""تقارير المبيعات والمشتريات التحليلية: كل الفلاتر + تجميع على مستويين + مؤشرات + تفصيل على مستوى الصنف/الفاتورة."""
import datetime

from sqlalchemy.orm import joinedload

from . import services
from .db import (Customer, PosTerminal, Product, PurchaseInvoice, PurchaseInvoiceItem, SalesInvoice, SalesInvoiceItem, SalesReturn, Supplier, get_session)

WEEKDAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# مفتاح التجميع -> (عنوان، يتاح في المبيعات؟، يتاح في المشتريات؟)
GROUPS = {
    "none": ("بدون تجميع (تفصيل بنود الفواتير)", 1, 1),
    "invoice": ("الفاتورة", 1, 1),
    "day": ("اليوم", 1, 1),
    "month": ("الشهر", 1, 1),
    "year": ("السنة", 1, 1),
    "weekday": ("يوم الأسبوع", 1, 1),
    "party": ("العميل / المورد", 1, 1),
    "product": ("الصنف", 1, 1),
    "category": ("الفئة", 1, 1),
    "branch": ("الفرع", 1, 1),
    "cost_center": ("مركز التكلفة", 1, 1),
    "tax_rate": ("نسبة الضريبة", 1, 1),
    "payment_method": ("طريقة الدفع", 1, 0),
    "terminal": ("ماكينة الكاشير", 1, 0),
    "cashier": ("الكاشير", 1, 0),
    "channel": ("القناة (كاشير / فاتورة عادية)", 1, 0),
}


def group_options(kind):
    return [(k, v[0]) for k, v in GROUPS.items() if (v[1] if kind == "sales" else v[2])]


def _start(d):
    return datetime.datetime.combine(d, datetime.time.min) if d else None


def _end(d):
    return datetime.datetime.combine(d, datetime.time.max) if d else None


def _load_lines(kind, f):
    """بنود الفواتير بعد تطبيق الفلاتر، كل بند dict جاهز للتجميع (مع توزيع خصم الفاتورة نسبيًا على بنودها)."""
    is_sales = kind == "sales"
    Inv, Item = (SalesInvoice, SalesInvoiceItem) if is_sales else (PurchaseInvoice, PurchaseInvoiceItem)
    ids_allowed = services.user_branch_ids()
    with get_session() as s:
        q = s.query(Inv).options(joinedload(Inv.items).joinedload(Item.product).joinedload(Product.category), joinedload(Inv.branch), joinedload(Inv.cost_center))
        q = q.options(joinedload(Inv.customer) if is_sales else joinedload(Inv.supplier))
        if f.get("date_from"):
            q = q.filter(Inv.date >= _start(f["date_from"]))
        if f.get("date_to"):
            q = q.filter(Inv.date <= _end(f["date_to"]))
        if f.get("branch_id"):
            q = q.filter(Inv.branch_id == int(f["branch_id"]))
        elif ids_allowed:
            q = q.filter(Inv.branch_id.is_(None) | Inv.branch_id.in_(ids_allowed))
        if f.get("cost_center_id"):
            q = q.filter(Inv.cost_center_id == int(f["cost_center_id"]))
        party_col = Inv.customer_id if is_sales else Inv.supplier_id
        if f.get("party_id"):
            q = q.filter(party_col == int(f["party_id"]))
        voided = f.get("voided", "exclude")           # exclude | include | only
        if voided == "exclude":
            q = q.filter(Inv.voided.is_(False))
        elif voided == "only":
            q = q.filter(Inv.voided.is_(True))
        if f.get("search"):
            q = q.filter(Inv.number.like(f"%{f['search'].strip()}%"))
        if f.get("min_total"):
            q = q.filter(Inv.total >= float(f["min_total"]))
        if f.get("max_total"):
            q = q.filter(Inv.total <= float(f["max_total"]))
        terminals = {}
        if is_sales:
            if f.get("payment_method"):
                q = q.filter(Inv.payment_method.like(f"%{f['payment_method']}%"))
            if f.get("terminal_id"):
                q = q.filter(Inv.pos_terminal_id == int(f["terminal_id"]))
            if f.get("channel") == "pos":
                q = q.filter(Inv.is_pos.is_(True))
            elif f.get("channel") == "normal":
                q = q.filter(Inv.is_pos.is_(False) | Inv.is_pos.is_(None))
            from .db import Employee
            terminals = {t.id: t for t in s.query(PosTerminal).options(joinedload(PosTerminal.employee)).all()}
            emp = {e.id: e.name for e in s.query(Employee).all()}
        out = []
        for inv in q.order_by(Inv.date, Inv.id).all():
            items = [i for i in inv.items if i.product]
            if f.get("product_id"):
                items_f = [i for i in items if i.product_id == int(f["product_id"])]
            else:
                items_f = items
            if f.get("category_id"):
                items_f = [i for i in items_f if i.product.category_id == int(f["category_id"])]
            if f.get("product_type"):
                items_f = [i for i in items_f if i.product.product_type == f["product_type"]]
            if f.get("tax_rate") not in (None, ""):
                items_f = [i for i in items_f if abs((i.tax_rate or 0) - float(f["tax_rate"])) < 1e-9]
            if not items_f:
                continue
            nets = {i.id: max(0.0, float(i.quantity or 0) * float(i.unit_price or 0) - float(i.discount or 0)) for i in items}
            all_net = sum(nets.values()) or 1.0
            inv_disc = float(inv.discount or 0)
            party = (inv.customer.name if inv.customer else "-") if is_sales else (inv.supplier.name if inv.supplier else "-")
            term = terminals.get(getattr(inv, "pos_terminal_id", None)) if is_sales else None
            for i in items_f:
                qty = float(i.quantity or 0); gross = qty * float(i.unit_price or 0)
                share = inv_disc * nets[i.id] / all_net
                net = nets[i.id] - share
                tax = float(i.line_total or 0) - nets[i.id]
                tax = tax * (net / nets[i.id]) if nets[i.id] else tax
                row = {"invoice_id": inv.id, "number": inv.number, "date": inv.date, "voided": bool(inv.voided), "party_id": party_col_value(inv, is_sales), "party": party,
                       "product_id": i.product_id, "sku": i.product.sku, "product": i.product.name, "category": i.product.category.name if i.product.category else "بدون فئة",
                       "branch": inv.branch.name if inv.branch else "بدون فرع", "cost_center": inv.cost_center.name if inv.cost_center else "بدون مركز", "tax_rate": float(i.tax_rate or 0),
                       "qty": qty, "base_qty": qty * float(i.unit_factor or 1), "price": float(i.unit_price or 0), "gross": gross, "discount": float(i.discount or 0) + share, "net": net, "tax": tax, "total": net + tax}
                if is_sales:
                    cost = qty * float(i.unit_factor or 1) * float(i.product.cost_price or 0) if i.product.product_type != "service" else 0.0
                    pm = (inv.payment_method or "").strip() or "غير محدد (فاتورة عادية)"
                    row.update({"cost": cost, "profit": net - cost, "payment_method": pm, "terminal": f"{term.code} - {term.name}" if term else "-",
                                "cashier": (term.employee.name if term and term.employee else (emp.get(inv.cashier_employee_id) or "-")), "channel": "كاشير (POS)" if inv.is_pos else "فاتورة عادية"})
                out.append(row)
        return out


def party_col_value(inv, is_sales):
    return inv.customer_id if is_sales else inv.supplier_id


def _key(row, g):
    d = row["date"]
    if g == "day":
        return d.strftime("%Y-%m-%d")
    if g == "month":
        return d.strftime("%Y-%m")
    if g == "year":
        return str(d.year)
    if g == "weekday":
        return f"{d.weekday()}-{WEEKDAYS[d.weekday()]}"
    if g == "invoice":
        return row["number"]
    if g == "product":
        return f"{row['sku']} - {row['product']}"
    if g == "tax_rate":
        return f"{row['tax_rate']:g}%"
    return row.get(g, "-") or "-"


def _label(k, g):
    return k.split("-", 1)[1] if g == "weekday" else k


def _agg(rows, is_sales):
    inv = {r["invoice_id"] for r in rows}
    a = {"invoices": len(inv), "qty": sum(r["base_qty"] for r in rows), "gross": sum(r["gross"] for r in rows), "discount": sum(r["discount"] for r in rows), "net": sum(r["net"] for r in rows),
         "tax": sum(r["tax"] for r in rows), "total": sum(r["total"] for r in rows)}
    a["avg_price"] = (a["net"] / a["qty"]) if a["qty"] else 0.0
    if is_sales:
        a["cost"] = sum(r["cost"] for r in rows); a["profit"] = a["net"] - a["cost"]; a["margin"] = (a["profit"] / a["net"] * 100) if a["net"] else 0.0
    return a


TIME_GROUPS = ("day", "month", "year", "weekday", "invoice")


def _group_rows(lines, levels, depth, is_sales, top_n, out, path=()):
    """تجميع تكراري: كل مستوى داخل اللي قبله، بعدد مستويات غير محدود."""
    g = levels[depth]
    groups = {}
    for r in lines:
        groups.setdefault(_key(r, g), []).append(r)
    if g in TIME_GROUPS:
        order = sorted(groups.items(), key=lambda kv: kv[0])
    else:
        order = sorted(groups.items(), key=lambda kv: -sum(x["total"] for x in kv[1]))
        if top_n:
            order = order[: int(top_n)]
    parent_total = sum(x["total"] for _, v in order for x in v) or 1.0
    for k, v in order:
        a = _agg(v, is_sales)
        out.append({"level": depth, "path": path + (k,), "label": _label(k, g), "group": g, "has_children": depth < len(levels) - 1, **a, "share": a["total"] / parent_total * 100})
        if depth < len(levels) - 1:
            _group_rows(v, levels, depth + 1, is_sales, 0, out, path + (k,))


def build_report(kind, filters, group_by=None, top_n=0):
    """kind = sales | purchase. group_by = قائمة مستويات التجميع بالترتيب (فاضية = تفصيل البنود). بيرجّع {kpis, rows, totals}."""
    is_sales = kind == "sales"
    services.require_action("reports", "view")
    if isinstance(group_by, str):
        group_by = [] if group_by in ("", "none") else [group_by]
    levels = []
    for g in (group_by or []):
        if g and g != "none" and g in GROUPS and g not in levels:
            levels.append(g)
    lines = _load_lines(kind, filters)
    total = _agg(lines, is_sales)
    kpis = {**total, "lines": len(lines), "avg_invoice": (total["total"] / total["invoices"]) if total["invoices"] else 0.0}
    if is_sales:
        with get_session() as s:
            q = s.query(SalesReturn)
            if filters.get("date_from"):
                q = q.filter(SalesReturn.date >= _start(filters["date_from"]))
            if filters.get("date_to"):
                q = q.filter(SalesReturn.date <= _end(filters["date_to"]))
            if filters.get("branch_id"):
                q = q.filter(SalesReturn.branch_id == int(filters["branch_id"]))
            if filters.get("party_id"):
                q = q.filter(SalesReturn.customer_id == int(filters["party_id"]))
            if filters.get("terminal_id"):
                q = q.filter(SalesReturn.pos_terminal_id == int(filters["terminal_id"]))
            rets = q.all()
            kpis["returns_count"] = len(rets); kpis["returns_total"] = sum(float(r.total or 0) for r in rets)
            kpis["net_after_returns"] = total["total"] - kpis["returns_total"]
    rows = []
    if not levels:
        for r in lines:
            rows.append({"level": 0, "label": r["number"], "date": r["date"].strftime("%Y-%m-%d"), "party": r["party"], "product": f"{r['sku']} - {r['product']}", "category": r["category"],
                         "invoices": 1, "qty": r["qty"], "price": r["price"], "gross": r["gross"], "discount": r["discount"], "net": r["net"], "tax": r["tax"], "total": r["total"],
                         **({"cost": r["cost"], "profit": r["profit"], "margin": (r["profit"] / r["net"] * 100) if r["net"] else 0.0} if is_sales else {})})
    else:
        _group_rows(lines, levels, 0, is_sales, top_n, rows)
    return {"kind": kind, "kpis": kpis, "rows": rows, "levels": levels, "totals": total}


def filters_text(kind, f, names):
    parts = []
    for k, label in [("branch_id", "الفرع"), ("cost_center_id", "مركز التكلفة"), ("party_id", "العميل" if kind == "sales" else "المورد"), ("product_id", "الصنف"), ("category_id", "الفئة"),
                     ("payment_method", "طريقة الدفع"), ("terminal_id", "الماكينة"), ("channel", "القناة"), ("search", "بحث"), ("tax_rate", "نسبة الضريبة")]:
        if f.get(k) not in (None, ""):
            parts.append(f"{label}: {names.get(k, {}).get(str(f[k]), f[k])}")
    if f.get("voided") and f["voided"] != "exclude":
        parts.append("الملغاة: " + ("مع الملغاة" if f["voided"] == "include" else "الملغاة فقط"))
    return " | ".join(parts)
