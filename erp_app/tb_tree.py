"""ميزان المراجعة بشكل شجرة حسابات: الحساب الأب بإجمالي فروعه وتحته المستويات.
الأب بيتحسب من صافي فروعه (مش بجمع أعمدة المدين/الدائن) عشان رصيده الختامي يكون صافي حقيقي."""

_F = ('opening_debit', 'opening_credit', 'period_debit', 'period_credit', 'closing_debit', 'closing_credit')


def _finish(opening_net, pd, pc):
    closing = opening_net + pd - pc
    r = lambda v: abs(round(v, 2))          # abs: عشان ما يظهرش -0.00
    return {'opening_debit': r(max(opening_net, 0)), 'opening_credit': r(max(-opening_net, 0)),
            'period_debit': r(pd), 'period_credit': r(pc),
            'closing_debit': r(max(closing, 0)), 'closing_credit': r(max(-closing, 0))}


def build_tree(rows, parents):
    """rows: ناتج trial_balance_detailed (account_id, code, name, ...). parents: {account_id: parent_id}.
    بيرجع (roots, flat) - كل عقدة: id, code, name, depth, children, has_children + أعمدة الميزان مجمّعة."""
    nodes = {}
    for r in rows:
        on = r['opening_debit'] - r['opening_credit']
        nodes[r['account_id']] = {'id': r['account_id'], 'code': r['code'], 'name': r['name'], 'type': r.get('type'),
                                  '_on': on, '_pd': r['period_debit'], '_pc': r['period_credit'], 'children': [], 'depth': 0}
    roots = []
    for nid, n in nodes.items():
        p = parents.get(nid)
        (nodes[p]['children'] if p in nodes else roots).append(n)

    def fin(n, depth):
        n['depth'] = depth
        n['children'].sort(key=lambda c: c['code'])
        for c in n['children']:
            fin(c, depth + 1)
            n['_on'] += c['_on']; n['_pd'] += c['_pd']; n['_pc'] += c['_pc']
        n['has_children'] = bool(n['children'])
        n.update(_finish(n['_on'], n['_pd'], n['_pc']))
    roots.sort(key=lambda c: c['code'])
    for r in roots:
        fin(r, 0)
    return roots


def has_movement(n):
    return any(abs(n[k]) > 1e-9 for k in ('opening_debit', 'opening_credit', 'period_debit', 'period_credit'))


def visible_rows(roots, expanded=None, hide_zero=True, query='', expand_all=False):
    """قائمة مسطّحة بالعقد الظاهرة بالترتيب (الأب ثم أبناؤه) حسب المفتوح/المقفول. البحث بيفتح الطريق للأبناء المطابقين."""
    q = (query or '').strip().lower()
    expanded = expanded or set()
    out = []

    def match(n):
        return q in (n['code'] or '').lower() or q in (n['name'] or '').lower()

    def keep(n):                      # العقدة أو أي فرع منها لازم يعدّي الفلاتر
        if hide_zero and not has_movement(n):
            return False
        if not q:
            return True
        return match(n) or any(keep(c) for c in n['children'])

    def walk(n):
        if not keep(n):
            return
        out.append(n)
        if n['children'] and (expand_all or bool(q) or n['id'] in expanded):
            for c in n['children']:
                walk(c)
    for r in roots:
        walk(r)
    return out


def totals(roots, hide_zero=True):
    """إجمالي الميزان = مجموع الجذور فقط (عشان مفيش عدّ مزدوج)."""
    on = sum(r['_on'] for r in roots); pd = sum(r['_pd'] for r in roots); pc = sum(r['_pc'] for r in roots)
    return _finish(on, pd, pc)
