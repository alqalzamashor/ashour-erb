"""لوحة المطعم: مبيعات الفترة، عدد الطلبات ومتوسط الفاتورة، أعلى الأصناف، المبيعات بالساعة، توزيع حسب نوع الطلب/الدفع/الكاشير/القسم، والإلغاءات.
المصدر: طلبات المطعم المدفوعة (وفواتيرها) + أحداث المطبخ للإلغاءات. القيم شاملة الضريبة."""
import datetime
from collections import defaultdict

from sqlalchemy.orm import joinedload

from . import services
from .db import KitchenEvent, RestaurantOrder, RestaurantOrderItem, RestaurantTable, get_session

PAY_LABELS = {"cash": "نقدي", "card": "شبكة / بطاقة", "transfer": "تحويل", "": "غير محدد"}


def _day(d, end=False):
    return datetime.datetime.combine(d, datetime.time.max if end else datetime.time.min)


def dashboard(date_from, date_to, terminal_id=None):
    services.require_action("restaurant_dashboard", "view")
    allowed = services.user_branch_ids()
    with get_session() as s:
        q = (s.query(RestaurantOrder)
             .options(joinedload(RestaurantOrder.items).joinedload(RestaurantOrderItem.product), joinedload(RestaurantOrder.sales_invoice), joinedload(RestaurantOrder.table).joinedload(RestaurantTable.section))
             .filter(RestaurantOrder.state == "paid", RestaurantOrder.closed_at >= _day(date_from), RestaurantOrder.closed_at <= _day(date_to, True)))
        if terminal_id:
            q = q.filter(RestaurantOrder.terminal_id == int(terminal_id))
        orders = [o for o in q.all() if not (allowed and o.branch_id and o.branch_id not in allowed)]
        inv_ids = set()
        by_hour = defaultdict(lambda: [0, 0.0]); by_type = defaultdict(lambda: [0, 0.0]); by_pay = defaultdict(lambda: [0, 0.0])
        by_user = defaultdict(lambda: [0, 0.0]); by_section = defaultdict(lambda: [0, 0.0]); by_day = defaultdict(lambda: [0, 0.0])
        items = defaultdict(lambda: [0.0, 0.0]); total = 0.0; guests = 0; discount = 0.0
        for o in orders:
            inv = o.sales_invoice
            if inv is None or inv.voided:
                continue
            if inv.id in inv_ids:
                continue
            inv_ids.add(inv.id)
            amt = float(inv.total or 0)
            total += amt; guests += int(o.guests or 0); discount += float(inv.discount or 0) + float(getattr(inv, "promo_discount", 0) or 0)
            h = (o.closed_at or o.opened_at).hour
            for d, key in ((by_hour, h), (by_type, o.order_type or "dine_in"), (by_pay, inv.payment_method or ""), (by_user, o.opened_by or "-"),
                           (by_section, (o.table.section.name if o.table and o.table.section else ("بدون طاولة" if not o.table_id else "بدون قسم"))),
                           (by_day, (o.closed_at or o.opened_at).date())):
                d[key][0] += 1; d[key][1] += amt
            for it in o.items:
                if it.kitchen_status == "voided":
                    continue
                nm = it.product.name if it.product else "-"
                items[nm][0] += float(it.quantity or 0); items[nm][1] += (it.quantity or 0) * (it.unit_price or 0) * (1 + (it.tax_rate or 0) / 100.0)
        ev = s.query(KitchenEvent).filter(KitchenEvent.created_at >= _day(date_from), KitchenEvent.created_at <= _day(date_to, True),
                                          KitchenEvent.kind.in_(["item_void", "order_void", "item_return", "invoice_void"])).all()
        void_count, void_amount = len(ev), sum(float(e.amount or 0) for e in ev)
    n = len(inv_ids)
    rank = lambda d, lab=None: sorted(([(lab(k) if lab else k), v[0], round(v[1], 2)] for k, v in d.items()), key=lambda r: -r[2])
    top_items = sorted(([k, round(v[0], 3), round(v[1], 2)] for k, v in items.items()), key=lambda r: -r[2])
    return {
        "kpis": {"sales": round(total, 2), "orders": n, "avg_ticket": round(total / n, 2) if n else 0.0, "guests": guests,
                 "per_guest": round(total / guests, 2) if guests else 0.0, "discount": round(discount, 2), "void_count": void_count, "void_amount": round(void_amount, 2),
                 "void_pct": round(void_amount / (total + void_amount) * 100, 1) if (total + void_amount) else 0.0},
        "hours": [[h, by_hour[h][0], round(by_hour[h][1], 2)] for h in range(24) if h in by_hour],
        "days": [[d, v[0], round(v[1], 2)] for d, v in sorted(by_day.items())],
        "top_items": top_items[:15], "bottom_items": list(reversed(top_items))[:5] if len(top_items) > 15 else [],
        "types": rank(by_type, lambda k: services.RESTAURANT_ORDER_TYPES.get(k, k)), "payments": rank(by_pay, lambda k: PAY_LABELS.get(k, k)),
        "users": rank(by_user), "sections": rank(by_section),
        "peak_hour": max(by_hour.items(), key=lambda kv: kv[1][1])[0] if by_hour else None,
    }


def export_table(r):
    """جدول التصدير (عناوين + أقسام) للوحة المطعم: [البيان، العدد، القيمة] + row_styles."""
    k = r['kpis']
    t = [['البيان', 'العدد', 'القيمة']]; styles = {}

    def sec(title):
        styles[len(t)] = 'section'; t.append([title, '', ''])

    sec('المؤشرات')
    for lab, cnt, val in [('إجمالي المبيعات', '', k['sales']), ('عدد الطلبات', k['orders'], ''), ('متوسط الفاتورة', '', k['avg_ticket']), ('عدد الضيوف', k['guests'], ''), ('متوسط للفرد', '', k['per_guest']),
                          ('الخصومات', '', k['discount']), ('الإلغاءات والمرتجعات', k['void_count'], k['void_amount']), ('نسبة الإلغاءات من المبيعات %', '', k['void_pct'])]:
        t.append([lab, cnt, f'{val:,.2f}' if val != '' else ''])
    if r['peak_hour'] is not None:
        t.append(['ساعة الذروة', '', f"{r['peak_hour']:02d}:00"])
    for title, rows, fmt_name in [('المبيعات بالساعة', [[f'{h:02d}:00', n, v] for h, n, v in r['hours']], None), ('المبيعات اليومية', [[f'{d:%Y-%m-%d}', n, v] for d, n, v in r['days']], None),
                                  ('أعلى الأصناف', r['top_items'], 'qty'), ('الأقل مبيعًا', r['bottom_items'], 'qty'), ('حسب نوع الطلب', r['types'], None), ('حسب طريقة الدفع', r['payments'], None),
                                  ('حسب الكاشير', r['users'], None), ('حسب القسم', r['sections'], None)]:
        if not rows:
            continue
        sec(title)
        for row in rows:
            t.append([str(row[0]), f'{row[1]:g}' if fmt_name == 'qty' else row[1], f'{row[2]:,.2f}'])
    return t, styles
