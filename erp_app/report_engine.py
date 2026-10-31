"""محرك عارض التقارير الجديد (بدون أي واجهة - منطق صافي قابل للاختبار):
فلترة لكل عمود (نص/أرقام بـ > < = a..b/تواريخ)، بحث عام، فرز، تجميع متعدد المستويات (حتى 3) بإجماليات حية
(مجموع/أول/آخر/متوسط/أقل/أكبر)، تجميع التواريخ بالشهر/السنة، إجماليات عامة، ملخص KPI، بيانات رسم بياني، وجدول التصدير.

الصفوف dicts بقيم بايثون حقيقية (float/int/date/str/None) - التنسيق بيتم وقت العرض بس، عشان الفرز والفلترة والجمع دقيقين."""
import datetime
import re
from dataclasses import dataclass, field

MONEY, QTY, INT, PCT, DATE, TEXT = 'money', 'qty', 'int', 'pct', 'date', 'text'
NUMERIC = (MONEY, QTY, INT, PCT)
DERIVED = {'month': 'شهر', 'year': 'سنة'}          # تجميع عمود تاريخ بالشهر/السنة


@dataclass
class Col:
    key: str
    label: str
    kind: str = TEXT
    total: str = None            # sum | first | last | avg | min | max | None (فاضي في الإجماليات)
    visible: bool = True
    group: bool = None           # قابل للتجميع (افتراضي: النصوص والتواريخ)
    width: float = None          # وزن العمود في التصدير
    bold: bool = False
    running: tuple = None        # ('debit','credit'): رصيد جاري داخل المجموعة الأخيرة (أو الصف كله لو مفيش تجميع)

    @property
    def numeric(self):
        return self.kind in NUMERIC

    @property
    def groupable(self):
        return self.group if self.group is not None else self.kind in (TEXT, DATE)


@dataclass
class ViewState:
    visible: list = field(default_factory=list)       # مفاتيح الأعمدة الظاهرة بالترتيب
    sort_key: str = None
    asc: bool = True
    group_keys: list = field(default_factory=list)    # مثال: ['account', 'date:month']
    search: str = ''
    filters: dict = field(default_factory=dict)       # {col_key: نص الفلتر}
    summary_only: bool = False                         # مجموعات بس من غير صفوف التفاصيل


# ------------------------------------------------------------------ تنسيق
def fmt(v, col):
    if v is None or v == '':
        return ''
    k = col.kind
    try:
        if k == MONEY:
            return f'{float(v):,.2f}'
        if k == QTY:
            f = float(v)
            return f'{f:,.0f}' if abs(f - round(f)) < 1e-9 else f'{f:,.3f}'.rstrip('0').rstrip('.')
        if k == INT:
            return f'{int(round(float(v))):,}'
        if k == PCT:
            return f'{float(v):.1f}%'
        if k == DATE:
            if hasattr(v, 'hour') and (v.hour or v.minute or v.second):          # datetime فيه وقت فعلي: نعرضه (سجل التدقيق/الخصومات/الملغاة)
                return v.strftime('%Y-%m-%d %H:%M:%S' if v.second else '%Y-%m-%d %H:%M')
            return v.strftime('%Y-%m-%d') if hasattr(v, 'strftime') else str(v)[:10]
    except (TypeError, ValueError):
        return str(v)
    return str(v)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _norm(s):
    s = str(s if s is not None else '').lower().strip()
    return s.translate(str.maketrans({'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ى': 'ي', 'ة': 'ه'}))


def _date(v):
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


# ------------------------------------------------------------------ فلترة
_CMP = re.compile(r'^(>=|<=|>|<|=)\s*(-?[\d,]*\.?\d+)$')
_RNG = re.compile(r'^(-?[\d,]*\.?\d*)\s*\.\.\s*(-?[\d,]*\.?\d*)$')


def _to_f(s):
    s = (s or '').replace(',', '').strip()
    return float(s) if s not in ('', '-', '.') else None


def make_filter(text, col):
    """بيحوّل نص فلتر عمود لدالة بتاخد القيمة وترجع True/False. None = مفيش فلتر.
    أرقام: >100  >=5  <0  =12.5  10..50  ..50  10..   أو رقم لوحده (يساوي).  تواريخ: >=2026-01-01  a..b  أو بداية نص (2026-03).
    نص: كلمة (تحتوي)  a|b (أو)  !كلمة (لا تحتوي)  =كلمة (مطابق بالظبط)."""
    t = (text or '').strip()
    if not t:
        return None
    if col.numeric:
        m = _CMP.match(t)
        if m:
            op, n = m.group(1), _to_f(m.group(2))
            f = {'>': lambda v: v > n, '>=': lambda v: v >= n - 1e-9, '<': lambda v: v < n, '<=': lambda v: v <= n + 1e-9, '=': lambda v: abs(v - n) < 0.005}[op]
            return lambda v: (_num(v) is not None) and f(_num(v))
        m = _RNG.match(t)
        if m:
            lo, hi = _to_f(m.group(1)), _to_f(m.group(2))
            return lambda v: (_num(v) is not None) and (lo is None or _num(v) >= lo - 1e-9) and (hi is None or _num(v) <= hi + 1e-9)
        n = _to_f(t) if re.fullmatch(r'-?[\d,]*\.?\d+', t) else None
        if n is not None:
            return lambda v: (_num(v) is not None) and abs(_num(v) - n) < 0.005
        return lambda v: _norm(fmt(v, col)).find(_norm(t)) >= 0
    if col.kind == DATE:
        m = re.match(r'^(>=|<=|>|<)\s*(\d{4}-\d{2}-\d{2})$', t)
        if m:
            op, d0 = m.group(1), datetime.date.fromisoformat(m.group(2))
            f = {'>': lambda d: d > d0, '>=': lambda d: d >= d0, '<': lambda d: d < d0, '<=': lambda d: d <= d0}[op]
            return lambda v: (_date(v) is not None) and f(_date(v))
        m = re.match(r'^(\d{4}-\d{2}-\d{2})?\s*\.\.\s*(\d{4}-\d{2}-\d{2})?$', t)
        if m:
            lo = datetime.date.fromisoformat(m.group(1)) if m.group(1) else None
            hi = datetime.date.fromisoformat(m.group(2)) if m.group(2) else None
            return lambda v: (_date(v) is not None) and (lo is None or _date(v) >= lo) and (hi is None or _date(v) <= hi)
        return lambda v: fmt(v, col).startswith(t)
    if t.startswith('!'):
        w = _norm(t[1:])
        return lambda v: w not in _norm(fmt(v, col))
    if t.startswith('='):
        w = _norm(t[1:])
        return lambda v: _norm(fmt(v, col)) == w
    words = [_norm(w) for w in t.split('|') if w.strip()]
    return lambda v: any(w in _norm(fmt(v, col)) for w in words)


def apply_filters(rows, cols, state):
    by = {c.key: c for c in cols}
    fs = [(k, make_filter(t, by[k])) for k, t in (state.filters or {}).items() if k in by]
    fs = [(k, f) for k, f in fs if f]
    q = _norm(state.search) if (state.search or '').strip() else ''
    out = []
    for r in rows:
        if r.get('_style') in ('total', 'net'):
            continue
        if any(not f(r.get(k)) for k, f in fs):
            continue
        if q and not any(q in _norm(fmt(r.get(c.key), c)) for c in cols):
            continue
        out.append(r)
    return out


# ------------------------------------------------------------------ فرز
def _sort_key(v, col):
    if v is None or v == '':
        return (2, 0, '')
    if col.numeric:
        n = _num(v)
        return (0, n, '') if n is not None else (2, 0, '')
    if col.kind == DATE:
        d = _date(v)
        return (0, d.toordinal(), '') if d else (2, 0, '')
    return (1, 0, _norm(v))


def sort_rows(rows, col, asc=True):
    if col is None:
        return list(rows)
    present = [r for r in rows if _sort_key(r.get(col.key), col)[0] != 2]
    missing = [r for r in rows if _sort_key(r.get(col.key), col)[0] == 2]
    present.sort(key=lambda r: _sort_key(r.get(col.key), col)[1:], reverse=not asc)
    return present + missing


# ------------------------------------------------------------------ تجميع
def group_value(row, gk, cols_by):
    """قيمة التجميع لصف حسب مفتاح التجميع (عمود عادي أو 'date:month' / 'date:year')."""
    if ':' in gk:
        key, how = gk.split(':', 1)
        d = _date(row.get(key))
        if d is None:
            return ('', 'بدون تاريخ')
        return (f'{d:%Y-%m}', f'{d:%Y-%m}') if how == 'month' else (f'{d:%Y}', f'{d:%Y}')
    c = cols_by[gk]
    v = row.get(gk)
    label = fmt(v, c)
    return (label, label if label != '' else 'بدون')


def group_label(gk, cols_by):
    if ':' in gk:
        key, how = gk.split(':', 1)
        return f"{cols_by[key].label} ({DERIVED.get(how, how)})"
    return cols_by[gk].label


def aggregate(rows, cols):
    """{col_key: قيمة التجميع} لأعمدة الأرقام حسب col.total."""
    out = {}
    for c in cols:
        if not c.numeric or not c.total:
            continue
        if c.total.startswith('net:'):        # 'net:مدين:دائن' => مجموع الأول - مجموع الثاني (زي رصيد الأستاذ في المجموعات)
            _, a, b = c.total.split(':', 2)
            va = [_num(r.get(a)) or 0.0 for r in rows]
            vb = [_num(r.get(b)) or 0.0 for r in rows]
            out[c.key] = (sum(va) - sum(vb)) if rows else None
            continue
        vals = [_num(r.get(c.key)) for r in rows]
        vals = [v for v in vals if v is not None]
        if not vals:
            out[c.key] = None
            continue
        t = c.total
        out[c.key] = (sum(vals) if t == 'sum' else vals[0] if t == 'first' else vals[-1] if t == 'last'
                      else sum(vals) / len(vals) if t == 'avg' else min(vals) if t == 'min' else max(vals) if t == 'max' else None)
    return out


@dataclass
class Node:
    id: tuple
    label: str
    level: int
    gk: str
    rows: list
    agg: dict
    children: list = field(default_factory=list)

    @property
    def count(self):
        return len(self.rows)


def build_groups(rows, cols, group_keys, sort_col=None, asc=True):
    cols_by = {c.key: c for c in cols}
    gks = [g for g in group_keys if (g.split(':')[0] in cols_by)]

    def make(rs, level, path):
        gk = gks[level]
        buckets, order = {}, []
        for r in rs:
            k, label = group_value(r, gk, cols_by)
            if k not in buckets:
                buckets[k] = (label, []); order.append(k)
            buckets[k][1].append(r)
        nodes = []
        for k in order:
            label, rr = buckets[k]
            n = Node(path + (k,), label, level, gk, rr, aggregate(rr, cols))
            if level + 1 < len(gks):
                n.children = make(rr, level + 1, n.id)
            nodes.append(n)
        # ترتيب المجموعات: بعمود الفرز لو رقمي، وإلا بالاسم/التاريخ تصاعدي
        if sort_col is not None and sort_col.numeric and sort_col.total:
            nodes.sort(key=lambda n: (n.agg.get(sort_col.key) is None, n.agg.get(sort_col.key) or 0), reverse=not asc)
            nodes.sort(key=lambda n: n.agg.get(sort_col.key) is None)
        else:
            nodes.sort(key=lambda n: (n.label in ('بدون', 'بدون تاريخ'), _norm(n.label)))
        return nodes
    return make(rows, 0, ()) if gks else []


def flatten(nodes, expanded, summary_only=False):
    """[('group', node) | ('row', row, level)] بالترتيب حسب المجموعات المفتوحة."""
    out = []

    def walk(ns):
        for n in ns:
            out.append(('group', n))
            if n.id in expanded:
                if n.children:
                    walk(n.children)
                elif not summary_only:
                    out.extend(('row', r, n.level + 1) for r in n.rows)
    walk(nodes)
    return out


def all_group_ids(nodes):
    ids = set()

    def walk(ns):
        for n in ns:
            ids.add(n.id)
            walk(n.children)
    walk(nodes)
    return ids


# ------------------------------------------------------------------ المحرك الكامل
def run(rows, cols, state):
    """بيطبّق الفلاتر والفرز والتجميع. بيرجّع dict: rows (بعد الفلترة والفرز)، nodes، totals (إجمالي عام)، visible_cols."""
    by = {c.key: c for c in cols}
    vis = [by[k] for k in (state.visible or [c.key for c in cols if c.visible]) if k in by]
    filtered = apply_filters(rows, cols, state)
    sc = by.get(state.sort_key)
    if state.group_keys:
        base = filtered          # التجميع بيحافظ على ترتيب الصفوف الأصلي داخل كل مجموعة (مهم للأرصدة الجارية)
        if sc is not None and not (sc.numeric and sc.total):
            base = sort_rows(filtered, sc, state.asc)
        nodes = build_groups(base, cols, state.group_keys, sc, state.asc)
        ordered = base
    else:
        ordered = sort_rows(filtered, sc, state.asc) if sc else filtered
        nodes = []
    return {'rows': ordered, 'nodes': nodes, 'totals': aggregate(filtered, cols), 'visible_cols': vis, 'count': len(filtered), 'source_count': len(rows)}


# ------------------------------------------------------------------ KPI + رسم
def auto_kpis(rows, cols, limit=4):
    """[(label, قيمة منسّقة)]: عدد الصفوف + أول أعمدة الأرقام اللي ليها إجمالي."""
    out = [('عدد الصفوف', f'{len(rows):,}')]
    agg = aggregate(rows, cols)
    for c in cols:
        if len(out) >= limit:
            break
        if c.numeric and c.total and agg.get(c.key) is not None:
            out.append((c.label, fmt(agg[c.key], c)))
    return out


def chart_data(rows, cols, state, value_key=None, limit=12):
    """بيانات الرسم: لو فيه تجميع => قيمة كل مجموعة (المستوى الأول)، وإلا أكبر الصفوف بعمود نصي أول + عمود رقمي.
    بيرجّع (title, [(label, value)]) أو None لو مفيش حاجة تترسم."""
    by = {c.key: c for c in cols}
    num = by.get(value_key) if value_key else next((c for c in cols if c.numeric and c.total == 'sum'), None) or next((c for c in cols if c.numeric), None)
    if num is None:
        return None
    if state.group_keys:
        nodes = build_groups(apply_filters(rows, cols, state), cols, state.group_keys[:1])
        pts = [(n.label, n.agg.get(num.key) or 0.0) for n in nodes]
        if state.group_keys[0].endswith((':month', ':year')):
            pts.sort(key=lambda p: p[0])                    # زمني
            return f'{num.label} حسب {group_label(state.group_keys[0], by)}', pts[-limit:]
        pts.sort(key=lambda p: abs(p[1]), reverse=True)
        return f'{num.label} حسب {group_label(state.group_keys[0], by)}', pts[:limit]
    lab = next((c for c in cols if c.kind == TEXT), None)
    if lab is None:
        return None
    rs = apply_filters(rows, cols, state)
    pts = sorted(((fmt(r.get(lab.key), lab), _num(r.get(num.key)) or 0.0) for r in rs), key=lambda p: abs(p[1]), reverse=True)[:limit]
    return f'أكبر {len(pts)} حسب {num.label}', pts


# ------------------------------------------------------------------ التصدير
def export_table(rows, cols, state, expanded=None):
    """جدول التصدير بنفس العرض الحالي (أعمدة ظاهرة، فلترة، فرز، تجميع بإجمالياته) + إجمالي عام.
    بيرجّع {'table', 'row_styles', 'col_weights'} بنفس شكل تقارير الجداول في report_export."""
    res = run(rows, cols, state)
    vis = res['visible_cols']
    t = [[c.label for c in vis]]
    styles = {}

    def line(r):
        return [fmt(r.get(c.key), c) if not c.numeric else r.get(c.key) for c in vis]

    def group_line(n, indent):
        cells = [''] * len(vis)
        cells[0] = ('    ' * indent) + f'{n.label} ({n.count})'
        for i, c in enumerate(vis):
            if c.numeric and n.agg.get(c.key) is not None:
                cells[i] = n.agg[c.key]
        return cells

    if res['nodes']:
        ids = expanded if expanded is not None else all_group_ids(res['nodes'])
        for item in flatten(res['nodes'], ids, state.summary_only):
            if item[0] == 'group':
                t.append(group_line(item[1], item[1].level)); styles[len(t) - 1] = 'section'
            else:
                t.append(line(item[1]))
    else:
        for r in res['rows']:
            t.append(line(r))
            if r.get('_style') in ('section', 'warn'):
                styles[len(t) - 1] = r['_style']
    tot = [''] * len(vis)
    tot[0] = f"الإجمالي ({res['count']})"
    for i, c in enumerate(vis):
        if c.numeric and res['totals'].get(c.key) is not None:
            tot[i] = res['totals'][c.key]
    t.append(tot); styles[len(t) - 1] = 'net'
    weights = [c.width or (1.6 if c.kind == TEXT else 1.2) for c in vis]
    return {'table': t, 'row_styles': styles, 'col_weights': weights}
