"""تقرير أرصدة المستودعات: لكل مستودع ولكل صنف خلال فترة - رصيد أول الفترة، الوارد (مشتريات، مرتجع مبيعات، تحويل داخل،
تسويات جرد زيادة)، المنصرف (مبيعات، مردود مشتريات، تحويل خارج، تالف، تسويات جرد نقص)، ثم رصيد آخر الفترة.

الحركة بتتصنّف من مرجعها (SALES:/PURCH:/GRN:/RET:/VOID:/TRF-/ADJ:/DMG:) وأي حاجة تانية (إنتاج، حركة يدوية...) بتروح
في عمود "أخرى" عشان رصيد آخر الفترة يقفل دايمًا = أول الفترة + الوارد - المنصرف (ويطابق تقرير أرصدة المخزون)."""
import datetime

from sqlalchemy import case, func

from . import services
from .db import StockMove, Product

# (key, label) - الترتيب هو ترتيب الأعمدة
IN_COLS = [('purchases', 'مشتريات'), ('sales_return', 'مرتجع مبيعات'), ('transfer_in', 'تحويل داخل'), ('adj_in', 'تسويات جردية زيادة'), ('other_in', 'أخرى')]
OUT_COLS = [('sales', 'مبيعات'), ('purchase_return', 'مردود مشتريات'), ('transfer_out', 'تحويل خارج'), ('damage', 'تالف'), ('adj_out', 'تسويات جردية نقص'), ('other_out', 'أخرى')]

_IN_PREFIX = {'PURCH:': 'purchases', 'GRN:': 'purchases', 'RET:': 'sales_return', 'VOID:': 'sales_return', 'TRF-': 'transfer_in', 'ADJ:': 'adj_in'}
_OUT_PREFIX = {'SALES:': 'sales', 'VOID:': 'purchase_return', 'TRF-': 'transfer_out', 'DMG:': 'damage', 'ADJ:': 'adj_out'}


def classify(reference, direction):
    """تصنيف حركة مخزون (من مرجعها واتجاهها) لعمود في التقرير."""
    ref = (reference or '').strip().upper()
    table, other = (_IN_PREFIX, 'other_in') if direction == 'in' else (_OUT_PREFIX, 'other_out')
    for pre, key in table.items():
        if ref.startswith(pre):
            return key
    return other


def _day_start(v):
    if isinstance(v, datetime.datetime):
        return v.replace(hour=0, minute=0, second=0, microsecond=0)
    if isinstance(v, datetime.date):
        return datetime.datetime.combine(v, datetime.time.min)
    return datetime.datetime.strptime(str(v).strip()[:10], '%Y-%m-%d')


def build_report(date_from, date_to, location_id=None, hide_zero=True, category_id=None):
    start = _day_start(date_from)
    end = _day_start(date_to) + datetime.timedelta(days=1)       # حصري: كل حركات يوم النهاية داخلة
    if end <= start:
        raise ValueError('تاريخ النهاية لازم يكون بعد تاريخ البداية')
    ref = StockMove.reference
    cat = case(*[(ref.like(p + '%'), p) for p in ('PURCH:', 'GRN:', 'RET:', 'VOID:', 'TRF-', 'ADJ:', 'DMG:', 'SALES:')], else_='')
    period = case((StockMove.date < start, 'open'), else_='mid')
    with services.get_session() as s:
        q = (s.query(StockMove.location_id, StockMove.product_id, StockMove.direction, cat, period, func.sum(StockMove.quantity))
             .filter(StockMove.voided.is_(False), StockMove.date < end))
        if location_id:
            q = q.filter(StockMove.location_id == int(location_id))
        ub = services.user_branch_ids()
        if ub:
            q = q.filter((StockMove.branch_id.is_(None)) | (StockMove.branch_id.in_(ub)))
        if category_id:
            q = q.join(Product, Product.id == StockMove.product_id).filter(Product.category_id == int(category_id))
        raw = q.group_by(StockMove.location_id, StockMove.product_id, StockMove.direction, cat, period).all()
        products = {p.id: p for p in s.query(Product).all()}
        s.expunge_all()
    in_keys = [k for k, _ in IN_COLS]
    out_keys = [k for k, _ in OUT_COLS]
    cells = {}
    for loc_id, pid, direction, prefix, per, qty in raw:
        row = cells.setdefault((loc_id, pid), {'opening': 0.0, **{k: 0.0 for k in in_keys + out_keys}})
        qty = float(qty or 0)
        if per == 'open':
            row['opening'] += qty if direction == 'in' else -qty
            continue
        key = classify(prefix, direction) if prefix else classify('', direction)
        row[key] += qty
    locations = {l.id: l for l in services.list_locations(active_only=False)}
    groups = {}
    for (loc_id, pid), row in cells.items():
        if loc_id not in locations or pid not in products:
            continue
        row['total_in'] = sum(row[k] for k in in_keys)
        row['total_out'] = sum(row[k] for k in out_keys)
        row['closing'] = row['opening'] + row['total_in'] - row['total_out']
        if hide_zero and all(abs(row[k]) < 1e-9 for k in ('opening', 'total_in', 'total_out', 'closing')):
            continue
        groups.setdefault(loc_id, []).append({'product': products[pid], **row})
    out = []
    for loc_id in sorted(groups, key=lambda i: locations[i].name):
        rows = sorted(groups[loc_id], key=lambda r: ((r['product'].sku or ''), r['product'].name))
        tot = {k: sum(r[k] for r in rows) for k in ['opening', 'total_in', 'total_out', 'closing'] + in_keys + out_keys}
        out.append({'location': locations[loc_id], 'rows': rows, 'totals': tot})
    # الأعمدة الفاضية (أخرى) متظهرش لو كلها صفر
    used = {k for g in out for k in in_keys + out_keys if any(abs(r[k]) > 1e-9 for r in g['rows'])}
    in_cols = [c for c in IN_COLS if c[0] != 'other_in' or c[0] in used]
    out_cols = [c for c in OUT_COLS if c[0] != 'other_out' or c[0] in used]
    return {'date_from': start.date(), 'date_to': (end - datetime.timedelta(days=1)).date(), 'groups': out,
            'in_cols': in_cols, 'out_cols': out_cols}


def _n(v):
    return float(v) if abs(v) > 1e-9 else None


def export_table(rep):
    """جدول التصدير (Excel/PDF): رأس واحد بأسماء "الوارد - ..." و"المنصرف - ..."، وصف عنوان لكل مستودع وصف إجمالي."""
    in_cols, out_cols = rep['in_cols'], rep['out_cols']
    head = ['الكود', 'الصنف', 'الوحدة', 'رصيد أول الفترة'] + [f'وارد: {l}' for _, l in in_cols] + ['إجمالي الوارد'] + \
           [f'منصرف: {l}' for _, l in out_cols] + ['إجمالي المنصرف', 'رصيد آخر الفترة']
    width = len(head)
    t, styles = [head], {}
    for g in rep['groups']:
        t.append([g['location'].name] + [''] * (width - 1)); styles[len(t) - 1] = 'section'
        for r in g['rows']:
            p = r['product']
            t.append([p.sku or '', p.name, p.unit or '', _n(r['opening'])] + [_n(r[k]) for k, _ in in_cols] + [_n(r['total_in'])] +
                     [_n(r[k]) for k, _ in out_cols] + [_n(r['total_out']), _n(r['closing'])])
        tot = g['totals']
        t.append(['', f"الإجمالي {g['location'].name}", '', _n(tot['opening'])] + [_n(tot[k]) for k, _ in in_cols] + [_n(tot['total_in'])] +
                 [_n(tot[k]) for k, _ in out_cols] + [_n(tot['total_out']), _n(tot['closing'])])
        styles[len(t) - 1] = 'net'
    if not rep['groups']:
        t.append(['لا توجد حركة أو أرصدة في الفترة'] + [''] * (width - 1))
    weights = [1.1, 2.8, 0.9, 1.2] + [1.1] * len(in_cols) + [1.2] + [1.1] * len(out_cols) + [1.2, 1.3]
    return {'table': t, 'row_styles': styles, 'col_weights': weights, 'date_from': rep['date_from'], 'date_to': rep['date_to']}
