"""تقرير الخصومات والكوبونات: كل فاتورة اتطبق عليها كوبون أو خصم يدوي (أو خصم على مستوى الفاتورة)، بمين وبأي كوبون وبموافقة مين."""
import datetime
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from . import services
from .db import PosTerminal, SalesInvoice, get_session

KINDS = {"loyalty": "نقاط ولاء", "coupon": "كوبون", "manual": "خصم يدوي", "invoice": "خصم فاتورة"}


def build_report(date_from=None, date_to=None, kind=None, terminal_id=None, approved_only=False, search=None, include_voided=False):
    services.require_action("discount_report", "view")
    allowed = services.user_branch_ids()
    with get_session() as s:
        q = s.query(SalesInvoice).options(joinedload(SalesInvoice.customer)).filter((SalesInvoice.promo_discount > 0) | (SalesInvoice.discount > 0))
        base = s.query(func.coalesce(func.sum(SalesInvoice.total), 0.0)).filter(SalesInvoice.voided.is_(False))
        if date_from:
            dfrom = datetime.datetime.combine(date_from, datetime.time.min); q = q.filter(SalesInvoice.date >= dfrom); base = base.filter(SalesInvoice.date >= dfrom)
        if date_to:
            dto = datetime.datetime.combine(date_to, datetime.time.max); q = q.filter(SalesInvoice.date <= dto); base = base.filter(SalesInvoice.date <= dto)
        if terminal_id:
            q = q.filter(SalesInvoice.pos_terminal_id == int(terminal_id)); base = base.filter(SalesInvoice.pos_terminal_id == int(terminal_id))
        if not include_voided:
            q = q.filter(SalesInvoice.voided.is_(False))
        if search:
            q = q.filter(SalesInvoice.number.ilike(f"%{search.strip()}%"))
        if allowed:
            q = q.filter((SalesInvoice.branch_id.is_(None)) | (SalesInvoice.branch_id.in_(allowed)))
        invs = q.order_by(SalesInvoice.date.desc()).all()
        terms = {t.id: t.name for t in s.query(PosTerminal).all()}
        total_sales = float(base.scalar() or 0)
        rows = []
        for i in invs:
            promo = float(i.promo_discount or 0)
            k = "loyalty" if (promo and i.promo_code == "LOYALTY") else "coupon" if (promo and i.promo_code) else ("manual" if promo else "invoice")
            if kind and k != kind:
                continue
            if approved_only and not i.promo_approved_by:
                continue
            disc = promo or float(i.discount or 0)
            net = float(i.total or 0)
            rows.append({"date": i.date, "number": i.number, "customer": i.customer.name if i.customer else "-", "terminal": terms.get(i.pos_terminal_id, "-") if i.pos_terminal_id else "-",
                         "kind": k, "kind_label": KINDS[k], "code": i.promo_code or "", "note": i.promo_note or "", "approved_by": i.promo_approved_by or "",
                         "gross": round(net + disc, 2), "discount": round(disc, 2), "net": round(net, 2), "pct": round(disc / (net + disc) * 100, 1) if (net + disc) else 0.0, "voided": bool(i.voided)})
    tot = sum(r["discount"] for r in rows if not r["voided"])
    gross = sum(r["gross"] for r in rows if not r["voided"])

    def group(keyf):
        g = defaultdict(lambda: [0, 0.0])
        for r in rows:
            if r["voided"]:
                continue
            key = keyf(r)
            if key:
                g[key][0] += 1; g[key][1] += r["discount"]
        return sorted(([k, v[0], round(v[1], 2)] for k, v in g.items()), key=lambda x: -x[2])
    return {"rows": rows,
            "kpis": {"count": len([r for r in rows if not r["voided"]]), "total": round(tot, 2), "avg_pct": round(tot / gross * 100, 1) if gross else 0.0,
                     "share_of_sales": round(tot / (total_sales + tot) * 100, 1) if (total_sales + tot) else 0.0, "approved": sum(1 for r in rows if r["approved_by"] and not r["voided"])},
            "by_code": group(lambda r: r["code"]), "by_approver": group(lambda r: r["approved_by"]), "by_terminal": group(lambda r: r["terminal"] if r["terminal"] != "-" else ""),
            "by_kind": group(lambda r: r["kind_label"])}
