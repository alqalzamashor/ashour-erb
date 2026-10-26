"""اليومية العامة بتجميع شجري: المستخدم يختار ترتيب المستويات (الفرع / الحساب / الطرف / مركز التكلفة) وكل عقدة بإجمالي مدين ودائن
ورصيد، وفي آخر مستوى سطور القيود نفسها."""
LEVELS = {'branch': 'الفرع', 'account': 'الحساب', 'party': 'الطرف (عميل / مورد)', 'cost_center': 'مركز التكلفة'}
_NONE_LABEL = {'branch': 'بدون فرع', 'account': 'بدون حساب', 'party': 'بدون طرف', 'cost_center': 'بدون مركز تكلفة'}


def clean_levels(levels):
    """المستويات المختارة بالترتيب بدون فاضي ولا تكرار."""
    out = []
    for k in levels or []:
        if k in LEVELS and k not in out:
            out.append(k)
    return out


def _key(row, level):
    """(مفتاح ترتيب، عنوان) للسطر على مستوى معيّن."""
    label = row.get(level) or ''
    if not label:
        return ('￿', _NONE_LABEL[level])      # "بدون ..." في آخر الترتيب
    return (label, label)


def build_tree(rows, levels):
    """rows: قائمة dict لكل سطر قيد: number, date, description, branch, account, party, cost_center, debit, credit, entry_id, source.
    بيرجّع (عقد الشجرة، الإجمالي العام). العقدة: label, level, debit, credit, balance, count, children (أو lines في آخر مستوى)."""
    levels = clean_levels(levels)

    def totals(rs):
        d = round(sum(float(r.get('debit') or 0) for r in rs), 2)
        c = round(sum(float(r.get('credit') or 0) for r in rs), 2)
        return d, c, round(d - c, 2)

    def build(rs, depth):
        if depth >= len(levels):
            return [], sorted(rs, key=lambda r: (r.get('date') or '', r.get('number') or ''))
        lv = levels[depth]
        groups = {}
        for r in rs:
            k, lab = _key(r, lv)
            groups.setdefault(k, (lab, []))[1].append(r)
        nodes = []
        for k in sorted(groups):
            lab, items = groups[k]
            d, c, b = totals(items)
            kids, lines = build(items, depth + 1)
            nodes.append({'label': lab, 'level': lv, 'depth': depth, 'debit': d, 'credit': c, 'balance': b, 'count': len(items), 'children': kids, 'lines': lines})
        return nodes, []

    nodes, lines = build(rows, 0)
    d, c, b = totals(rows)
    grand = {'debit': d, 'credit': c, 'balance': b, 'count': len(rows)}
    if not levels:
        return [], grand
    return nodes, grand


def export_table(nodes, grand, levels, with_lines=True):
    """جدول التصدير: صف لكل عقدة (بمسافة بادئة حسب المستوى) وتحتها سطور القيود في آخر مستوى، وفي الآخر الإجمالي العام."""
    t = [['البند', 'مدين', 'دائن', 'الرصيد (مدين - دائن)']]
    styles = {}

    def walk(ns):
        for n in ns:
            t.append(['    ' * n['depth'] + f"{LEVELS[n['level']]}: {n['label']}  ({n['count']} سطر)", n['debit'], n['credit'], n['balance']])
            if n['depth'] == 0:
                styles[len(t) - 1] = 'section'
            elif n['children']:
                styles[len(t) - 1] = 'total'
            walk(n['children'])
            if with_lines:
                for r in n['lines']:
                    txt = ' • '.join(x for x in (r.get('number') or '', r.get('date') or '', r.get('description') or '') if x)
                    t.append(['    ' * (n['depth'] + 1) + txt, r.get('debit') or None, r.get('credit') or None, None])
    walk(nodes)
    t.append(['الإجمالي العام', grand['debit'], grand['credit'], grand['balance']])
    styles[len(t) - 1] = 'net'
    return {'table': t, 'row_styles': styles, 'col_weights': [6.0, 1.4, 1.4, 1.6]}
