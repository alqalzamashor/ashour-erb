"""القوائم المالية وفق IFRS / IAS 1 بشكل شجري (حساب رئيسي ← فرعي ← فرعي ...).

- قائمة المركز المالي (IAS 1.54): أصول غير متداولة / متداولة، حقوق ملكية، التزامات غير متداولة / متداولة.
- قائمة الربح أو الخسارة والدخل الشامل الآخر (IAS 1.82، تبويب حسب الوظيفة): إيرادات، تكلفة مبيعات، مجمل الربح،
  إيرادات أخرى، مصروفات تشغيلية، ربح التشغيل، تكاليف تمويل، الربح قبل الزكاة والضريبة، الزكاة والضريبة، صافي الربح.
- أعمدة لكل فرع + إجمالي موحد، ومقارنة بالفترة السابقة.

التصنيف (متداول/غير متداول، تكلفة مبيعات، تمويل، زكاة) بيتحدد من شجرة الحسابات نفسها: الحساب أو أي أب له
اسمه فيه كلمة دالة. لو الشجرة عندك مسمّياتها مختلفة عدّل القوائم الثابتة في أول الملف.
"""
from __future__ import annotations

import datetime
from collections import defaultdict

# ---- كلمات التصنيف (بعد التطبيع: همزات/ياء/تاء مربوطة/تشكيل) ----
NONCURRENT_KW = ('غير متداول', 'اصول ثابت', 'الاصول الثابت', 'مشروعات تحت التنفيذ', 'طويل الاجل', 'طويله الاجل',
                 'استثمارات طويل', 'مخصص نهايه خدم', 'مخصص نهاية خدم', 'ضريبه موجله', 'ضريبة موجلة')
CURRENT_KW = ('متداول',)
COGS_KW = ('تكلفه المبيعات', 'تكلفة المبيعات', 'تكلفه البضاعه', 'تكلفه الايراد')
REVENUE_KW = ('مبيعات', 'ايرادات التشغيل', 'ايرادات النشاط')
FINANCE_KW = ('فوائد', 'تكاليف تمويل', 'مصاريف تمويل', 'مصاريف قروض', 'اعباء تمويل')
TAX_KW = ('الزكاه', 'مخصص الزكاه', 'زكاه', 'ضريبه الدخل', 'ضريبه دخل')

AR_FIX = str.maketrans({'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ى': 'ي', 'ة': 'ه', 'ؤ': 'و', 'ئ': 'ي'})


def norm(s: str) -> str:
    s = (s or '').translate(AR_FIX)
    return ''.join(ch for ch in s if not ('ً' <= ch <= 'ْ')).strip()


def _has(name: str, kws) -> bool:
    n = norm(name)
    return any(norm(k) in n for k in kws)


class Chart:
    """شجرة الحسابات في الذاكرة + دوال التصنيف."""

    def __init__(self, accounts, sales_id=None, cogs_id=None):
        self.acc = {a['id']: a for a in accounts}
        self.children = defaultdict(list)
        for a in sorted(accounts, key=lambda x: x['code']):
            self.children[a['parent_id']].append(a['id'])
        self.sales_id, self.cogs_id = sales_id, cogs_id
        self._sub_cache = {}

    def chain(self, aid):
        out, seen = [], set()
        while aid and aid in self.acc and aid not in seen:
            seen.add(aid); out.append(self.acc[aid]); aid = self.acc[aid]['parent_id']
        return out

    def in_subtree(self, aid, root_id):
        return bool(root_id) and any(a['id'] == root_id for a in self.chain(aid))

    def liquidity(self, aid):
        """'non_current' أو 'current' لحساب أصل/التزام: أول اسم في السلسلة (من الحساب لفوق) فيه دلالة."""
        for a in self.chain(aid):
            if _has(a['name'], NONCURRENT_KW):
                return 'non_current'
            if _has(a['name'], CURRENT_KW):
                return 'current'
        return 'current'

    def pl_class(self, aid):
        """revenue / other_income / cogs / finance / tax / opex."""
        ch = self.chain(aid)
        typ = ch[0]['type']
        if typ == 'income':
            if self.in_subtree(aid, self.sales_id) or any(_has(a['name'], REVENUE_KW) for a in ch):
                return 'revenue'
            return 'other_income'
        if self.in_subtree(aid, self.cogs_id) or any(_has(a['name'], COGS_KW) and 'مصروفات' not in norm(a['name']) for a in ch):
            return 'cogs'
        if any(_has(a['name'], TAX_KW) for a in ch):
            return 'tax'
        if any(_has(a['name'], FINANCE_KW) for a in ch):
            return 'finance'
        return 'opex'


# ------------------------------------------------------------------ البيانات
def load_chart():
    from . import services
    from .db import Account, get_session
    with get_session() as s:
        accs = [{'id': a.id, 'code': a.code, 'name': a.name, 'type': a.account_type, 'parent_id': a.parent_id}
                for a in s.query(Account).order_by(Account.code).all()]
    cfg = None
    try:
        cfg = services.get_accounting_settings()
    except Exception:       # noqa: BLE001
        pass
    return Chart(accs, getattr(cfg, 'sales_account_id', None), getattr(cfg, 'cogs_account_id', None))


def movements(date_from=None, date_to=None, cost_center_id=None):
    """{(account_id, branch_id|None): مدين - دائن} للقيود المرحّلة في الفترة (وبحدود فروع المستخدم)."""
    from sqlalchemy import func
    from . import services
    from .db import JournalEntry, JournalEntryLine, get_session
    df, dt = services._dt_start(_d(date_from)), services._dt_end(_d(date_to))
    with get_session() as s:
        q = (s.query(JournalEntryLine.account_id, JournalEntryLine.branch_id,
                     func.coalesce(func.sum(JournalEntryLine.debit), 0), func.coalesce(func.sum(JournalEntryLine.credit), 0))
             .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id).filter(JournalEntry.posted.is_(True)))
        if df:
            q = q.filter(JournalEntry.date >= df)
        if dt:
            q = q.filter(JournalEntry.date <= dt)
        if cost_center_id:
            q = q.filter(JournalEntryLine.cost_center_id == int(cost_center_id))
        ub = services.user_branch_ids()
        if ub:
            q = q.filter((JournalEntryLine.branch_id.is_(None)) | (JournalEntryLine.branch_id.in_(ub)))
        return {(a, b): float(d) - float(c) for a, b, d, c in q.group_by(JournalEntryLine.account_id, JournalEntryLine.branch_id).all()}


def _col_values(mv, branch):
    """{account_id: صافي (مدين - دائن)} لعمود: branch = 'all' | رقم فرع | 'none' (بدون فرع)."""
    out = defaultdict(float)
    for (aid, bid), v in mv.items():
        if branch == 'all' or (branch == 'none' and bid is None) or (isinstance(branch, int) and bid == branch):
            out[aid] += v
    return out


# ------------------------------------------------------------------ بناء الصفوف
def _row(rid, parent, level, kind, name, values, code='', has_children=False):
    return {'id': rid, 'parent': parent, 'level': level, 'kind': kind, 'name': name, 'code': code,
            'values': values, 'has_children': has_children}


def _zero(n):
    return [0.0] * n


def _tree_rows(chart, vals, sign, leaves, section_id, parent_row_id, base_level, ncols, skip_mixed_roots=None):
    """يبني صفوف شجرة لمجموعة حسابات `leaves` (اللي ليها رصيد في القسم ده): الأب ثم الابن ثم الابن.
    vals: قائمة قواميس {account_id: صافي} لكل عمود. بيرجع (rows, totals)."""
    members = set(leaves)
    nodes = set()
    for aid in members:
        for a in chart.chain(aid):
            nodes.add(a['id'])
    skip = set(skip_mixed_roots or ()) | {aid for aid in nodes if chart.acc[aid]['parent_id'] is None and chart.children.get(aid)}

    def total(aid):
        t = [sign * v.get(aid, 0.0) if aid in members else 0.0 for v in vals]
        for k in chart.children.get(aid, []):
            if k in nodes:
                t = [x + y for x, y in zip(t, total(k))]
        return t

    rows = []

    def emit(aid, parent, level):
        kids = [k for k in chart.children.get(aid, []) if k in nodes]
        a = chart.acc[aid]
        if aid in skip:          # أب مختلط (فيه متداول وغير متداول) بنتخطاه ونطلّع ولاده مكانه
            for k in kids:
                emit(k, parent, level)
            return
        rid = f'{section_id}:{aid}'
        rows.append(_row(rid, parent, level, 'group' if kids else 'account', a['name'], total(aid), a['code'], bool(kids)))
        for k in kids:
            emit(k, rid, level + 1)

    roots = [aid for aid in nodes if chart.acc[aid]['parent_id'] not in nodes]
    for aid in sorted(roots, key=lambda x: chart.acc[x]['code']):
        emit(aid, parent_row_id, base_level)
    tot = _zero(ncols)
    for aid in roots:
        tot = [x + y for x, y in zip(tot, total(aid))]
    return rows, tot


def _nonzero_leaves(chart, vals, types, pred=None):
    out = []
    for aid, a in chart.acc.items():
        if a['type'] not in types:
            continue
        if any(abs(v.get(aid, 0.0)) > 0.004 for v in vals) and (pred is None or pred(aid)):
            out.append(aid)
    return out


def _mixed_ancestors(chart, groups):
    """حسابات أب فيها أبناء من أكتر من قسم -> بتتخطى في العرض. groups: {section: [account ids]}."""
    seen = defaultdict(set)
    for sec, ids in groups.items():
        for aid in ids:
            for a in chart.chain(aid)[1:]:
                seen[a['id']].add(sec)
    return {aid for aid, secs in seen.items() if len(secs) > 1}


def financial_position(chart, mv_list, hide_zero=True):
    """mv_list: قائمة قواميس {account_id: صافي} (حركات تراكمية لحد تاريخ القائمة) لكل عمود."""
    n = len(mv_list)
    rows = []
    # أصول
    assets = _nonzero_leaves(chart, mv_list, ('asset',))
    liab = _nonzero_leaves(chart, mv_list, ('liability',))
    eq = _nonzero_leaves(chart, mv_list, ('equity',))
    a_groups = {'nc': [a for a in assets if chart.liquidity(a) == 'non_current'], 'c': [a for a in assets if chart.liquidity(a) == 'current']}
    l_groups = {'nc': [a for a in liab if chart.liquidity(a) == 'non_current'], 'c': [a for a in liab if chart.liquidity(a) == 'current']}
    a_skip, l_skip = _mixed_ancestors(chart, a_groups), _mixed_ancestors(chart, l_groups)

    def block(sec_id, title, leaves, sign, skip, level=1):
        head = _row(sec_id, None, 0 if level == 1 else level - 1, 'section', title, None, has_children=True)
        rows.append(head)
        sub, tot = _tree_rows(chart, mv_list, sign, leaves, sec_id, sec_id, level, n, skip)
        rows.extend(sub)
        rows.append(_row(sec_id + ':total', None, 0, 'subtotal', f'إجمالي {title}', tot))
        return tot

    top_a = _row('assets', None, 0, 'title', 'الأصول', None)
    rows.append(top_a)
    nc_a = block('a_nc', 'الأصول غير المتداولة', a_groups['nc'], 1, a_skip)
    c_a = block('a_c', 'الأصول المتداولة', a_groups['c'], 1, a_skip)
    tot_assets = [x + y for x, y in zip(nc_a, c_a)]
    rows.append(_row('a_total', None, 0, 'total', 'إجمالي الأصول', tot_assets))
    rows.append(_row('sp1', None, 0, 'spacer', '', None))

    rows.append(_row('eql', None, 0, 'title', 'حقوق الملكية والالتزامات', None))
    # حقوق الملكية + صافي ربح الفترة غير المرحّل (حسابات الإيراد والمصروف لسه ماتقفلتش)
    head = _row('e', None, 0, 'section', 'حقوق الملكية', None, has_children=True)
    rows.append(head)
    sub, eq_tot = _tree_rows(chart, mv_list, -1, eq, 'e', 'e', 1, n)
    rows.extend(sub)
    profit = [-sum(v.get(aid, 0.0) for aid, a in chart.acc.items() if a['type'] in ('income', 'expense')) for v in mv_list]
    if any(abs(p) > 0.004 for p in profit):
        rows.append(_row('e:profit', 'e', 1, 'account', 'صافي ربح / (خسارة) الفترة الحالية (غير مرحّل)', profit))
        eq_tot = [x + y for x, y in zip(eq_tot, profit)]
    rows.append(_row('e:total', None, 0, 'subtotal', 'إجمالي حقوق الملكية', eq_tot))
    nc_l = block('l_nc', 'الالتزامات غير المتداولة', l_groups['nc'], -1, l_skip)
    c_l = block('l_c', 'الالتزامات المتداولة', l_groups['c'], -1, l_skip)
    tot_l = [x + y for x, y in zip(nc_l, c_l)]
    rows.append(_row('l_total', None, 0, 'subtotal', 'إجمالي الالتزامات', tot_l))
    tot_el = [x + y for x, y in zip(eq_tot, tot_l)]
    rows.append(_row('el_total', None, 0, 'total', 'إجمالي حقوق الملكية والالتزامات', tot_el))
    gap = [round(a - b, 2) for a, b in zip(tot_assets, tot_el)]
    if any(abs(g) > 0.004 for g in gap):
        rows.append(_row('gap', None, 0, 'warn', 'فرق التوازن (يجب أن يكون صفرًا)', gap))
    return rows


def profit_or_loss(chart, mv_list):
    n = len(mv_list)
    rows = []
    inc = _nonzero_leaves(chart, mv_list, ('income',))
    exp = _nonzero_leaves(chart, mv_list, ('expense',))
    groups = {k: [a for a in inc if chart.pl_class(a) == k] for k in ('revenue', 'other_income')}
    groups.update({k: [a for a in exp if chart.pl_class(a) == k] for k in ('cogs', 'opex', 'finance', 'tax')})
    skip = _mixed_ancestors(chart, groups)

    def block(sec_id, title, key, sign, always=True):
        sub, tot = _tree_rows(chart, mv_list, sign, groups[key], sec_id, sec_id, 1, n, skip)
        if not sub and not always:
            return tot
        rows.append(_row(sec_id, None, 0, 'section', title, None, has_children=True))
        rows.extend(sub)
        rows.append(_row(sec_id + ':total', None, 0, 'subtotal', f'إجمالي {title}', tot))
        return tot

    def line(rid, label, vals, kind='total'):
        rows.append(_row(rid, None, 0, kind, label, vals))
        return vals

    sub_ = lambda a, b: [x - y for x, y in zip(a, b)]          # noqa: E731
    add_ = lambda a, b: [x + y for x, y in zip(a, b)]          # noqa: E731
    rev = block('rev', 'الإيرادات', 'revenue', -1)
    cogs = block('cogs', 'تكلفة المبيعات', 'cogs', 1)
    gross = line('gross', 'مجمل الربح', sub_(rev, cogs))
    oth = block('oth', 'إيرادات أخرى', 'other_income', -1, always=False)
    opex = block('opex', 'المصروفات التشغيلية والإدارية', 'opex', 1)
    op = line('op', 'ربح التشغيل', sub_(add_(gross, oth), opex))
    fin = block('fin', 'تكاليف التمويل', 'finance', 1, always=False)
    pbt = line('pbt', 'الربح قبل الزكاة والضريبة', sub_(op, fin))
    tax = block('tax', 'الزكاة وضريبة الدخل', 'tax', 1, always=False)
    net = line('net', 'صافي ربح / (خسارة) الفترة', sub_(pbt, tax))
    line('oci', 'الدخل الشامل الآخر', _zero(n), 'subtotal')
    line('tci', 'إجمالي الدخل الشامل للفترة', net)
    return rows


# ------------------------------------------------------------------ الواجهة
def build(kind, *, date_from=None, date_to=None, branches=None, by_branch=False, compare=False,
          cost_center_id=None, chart=None):
    """kind: 'position' | 'pl'.
    branches: [(id, label)] الفروع المسموح بها. by_branch: عمود لكل فرع + «بدون فرع» + إجمالي موحد.
    compare: عمود الفترة السابقة (نفس الطول) + التغير.
    بيرجع {'rows','columns','chart'}. columns = [{'label','kind'}]"""
    chart = chart or load_chart()
    df = date_from if kind == 'pl' else None
    cur = movements(df, date_to, cost_center_id)
    specs = []
    if by_branch:
        used = {b for (_, b) in cur}
        for bid, label in branches or []:
            if bid in used:
                specs.append((label, bid, 'branch'))
        if None in used:
            specs.append(('بدون فرع', 'none', 'branch'))
    specs.append(('الإجمالي الموحد' if by_branch else ('الفترة الحالية' if compare else 'المبلغ'), 'all', 'total'))
    vals = [_col_values(cur, b) for _, b, _ in specs]
    cols = [{'label': l, 'kind': k} for l, _, k in specs]
    if compare and date_to:
        pf, pt = _prior_range(kind, date_from, date_to)
        prev = movements(pf if kind == 'pl' else None, pt, cost_center_id)
        vals.append(_col_values(prev, 'all'))
        cols.append({'label': 'الفترة السابقة', 'kind': 'prior'})
    rows = (financial_position if kind == 'position' else profit_or_loss)(chart, vals)
    if compare and date_to:
        ti, pi = next(i for i, c in enumerate(cols) if c['kind'] == 'total'), len(cols) - 1
        for r in rows:
            if r['values'] is not None:
                a, b = r['values'][ti], r['values'][pi]
                r['values'] = r['values'] + [a - b, ((a - b) / abs(b) * 100.0) if abs(b) > 0.004 else None]
        cols += [{'label': 'التغير', 'kind': 'delta'}, {'label': '%', 'kind': 'pct'}]
    return {'rows': rows, 'columns': cols, 'chart': chart}


def _prior_range(kind, date_from, date_to):
    d2 = _d(date_to)
    p2 = _shift_year(d2, -1)
    if kind == 'position':
        return None, p2
    d1 = _d(date_from) or datetime.date(d2.year, 1, 1)
    return _shift_year(d1, -1), p2


def _d(v):
    if v is None or v == '':
        return None
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    return datetime.date.fromisoformat(str(v)[:10])


def _shift_year(d, n):
    try:
        return d.replace(year=d.year + n)
    except ValueError:      # 29 فبراير
        return d.replace(year=d.year + n, day=28)


def fmt(v, kind='total'):
    """أرقام IFRS: السالب بين أقواس، الصفر شرطة."""
    if v is None:
        return ''
    if kind == 'pct':
        return f'{v:,.1f}%'
    if abs(v) < 0.005:
        return '-'
    return f'({abs(v):,.2f})' if v < 0 else f'{v:,.2f}'


def visible_rows(rows, level_limit, collapsed=None, expanded=None):
    """الصفوف الظاهرة: صف ظاهر لو كل آبائه مفتوحين. الأب مفتوح لو level < level_limit (أو حسب ضغط المستخدم)."""
    collapsed, expanded = collapsed or set(), expanded or set()
    by_id = {r['id']: r for r in rows}

    def is_open(r):
        if r['id'] in collapsed:
            return False
        if r['id'] in expanded:
            return True
        return level_limit is None or r['level'] < level_limit

    out = []
    for r in rows:
        p, ok = r['parent'], True
        while p:
            pr = by_id.get(p)
            if pr is None:
                break
            if not is_open(pr):
                ok = False
                break
            p = pr['parent']
        if ok:
            out.append(r)
    return out


def to_export_rows(res, hide_zero=True):
    """جدول مسطّح للتصدير: [(مستوى, اسم, [قيم نصية])]."""
    cols = res['columns']
    out = []
    for r in res['rows']:
        if r['kind'] == 'spacer':
            continue
        vals = None if r['values'] is None else [fmt(v, c['kind']) for v, c in zip(r['values'], cols)]
        if hide_zero and r['kind'] in ('account', 'group') and r['values'] is not None and all(abs(v or 0) < 0.005 for v in r['values']):
            continue
        name = (f"{r['code']} - " if r.get('code') else '') + r['name']
        out.append((r['kind'], r['level'], name, vals))
    return out
