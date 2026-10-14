"""البحث الشامل: بحث واحد في العملاء والموردين والأصناف والفواتير والموظفين والحسابات والسندات والقيود.
النتائج بتتفلتر بصلاحية العرض للمستخدم، وكل نتيجة بتشاور على شاشة (nav key) تتفتح وبيتعبّى فيها نص البحث."""
from sqlalchemy import or_

from . import services
from .db import (Account, Customer, Employee, JournalEntry, Payment, Product, PurchaseInvoice, SalesInvoice, SalesQuotation, Supplier,
                 get_session)

PER_KIND = 6


def _like(text):
    t = (text or "").strip().replace("%", r"\%").replace("_", r"\_")
    return f"%{t}%"


def search(text, limit_per_kind=PER_KIND):
    """بيرجّع قايمة مجموعات [{kind, label, screen, items:[{title, sub}]}] للنتائج غير الفاضية بس."""
    text = (text or "").strip()
    if len(text) < 2:
        return []
    lk = _like(text)
    user = services.current_user()

    def ok(module):
        return services.user_has_action(user, module, "view")

    groups = []
    with get_session() as s:
        def add(kind, label, screen, module, rows):
            if ok(module) and rows:
                groups.append({"kind": kind, "label": label, "screen": screen, "items": rows})

        def q(model, *cols):
            return s.query(model).filter(or_(*[c.ilike(lk, escape="\\") for c in cols])).limit(limit_per_kind)

        add("customers", "العملاء", "customers", "customers",
            [{"title": c.name, "sub": " · ".join(x for x in [c.phone, c.vat_number] if x)} for c in q(Customer, Customer.name, Customer.phone, Customer.vat_number, Customer.email)])
        add("suppliers", "الموردين", "suppliers", "suppliers",
            [{"title": c.name, "sub": " · ".join(x for x in [c.phone, c.vat_number] if x)} for c in q(Supplier, Supplier.name, Supplier.phone, Supplier.vat_number)])
        prod_cols = [Product.name, Product.sku]
        if hasattr(Product, "barcode"):
            prod_cols.append(Product.barcode)
        add("products", "الأصناف", "products", "products",
            [{"title": p.name, "sub": f"كود {p.sku} · سعر البيع {p.sale_price or 0:,.2f}"} for p in q(Product, *prod_cols)])
        add("sales_invoices", "فواتير المبيعات", "sales_invoices", "sales_invoices",
            [{"title": i.number, "sub": f"{i.date:%Y-%m-%d} · {i.total or 0:,.2f}" + (" · ملغاة" if i.voided else "")} for i in q(SalesInvoice, SalesInvoice.number)])
        add("sales_quotations", "عروض الأسعار", "sales_quotations", "sales_quotations",
            [{"title": i.number, "sub": f"{i.date:%Y-%m-%d} · {i.total or 0:,.2f}"} for i in q(SalesQuotation, SalesQuotation.number)])
        add("purchase_invoices", "فواتير المشتريات", "purchase_invoices", "purchase_invoices",
            [{"title": i.number, "sub": f"{i.date:%Y-%m-%d} · {i.total or 0:,.2f}"} for i in q(PurchaseInvoice, PurchaseInvoice.number)])
        add("employees", "الموظفون", "employees", "employees",
            [{"title": e.name, "sub": " · ".join(x for x in [e.code, e.phone, e.national_id] if x)} for e in q(Employee, Employee.name, Employee.code, Employee.national_id, Employee.phone)])
        add("accounts", "الحسابات", "accounts", "accounts",
            [{"title": a.name, "sub": f"كود {a.code}"} for a in q(Account, Account.name, Account.code)])
        add("receipts_payments", "سندات القبض والصرف", "receipts_payments", "receipts_payments",
            [{"title": p.number, "sub": f"{p.date:%Y-%m-%d}" + (f" · {p.reference}" if p.reference else "")} for p in q(Payment, Payment.number, Payment.reference)])
        add("journals", "قيود اليومية", "journals", "journals",
            [{"title": j.number, "sub": f"{j.date:%Y-%m-%d}" + (f" · {j.description[:50]}" if j.description else "")} for j in q(JournalEntry, JournalEntry.number, JournalEntry.reference, JournalEntry.description)])
    return groups


def find_first(text):
    """أول نتيجة (للضغط على Enter)."""
    for g in search(text, 1):
        return g
    return None
