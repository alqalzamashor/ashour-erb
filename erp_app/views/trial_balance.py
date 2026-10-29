import datetime, os
import flet as ft
from .. import services, theme, tb_tree
from ..report_export import export_excel, export_pdf


def build_trial_balance(page: ft.Page):
    """ميزان المراجعة: رصيد أول المدة + حركة الفترة + الرصيد الختامي (كل واحدة مدين/دائن)،
    مع فلاتر فترة/فرع/مركز تكلفة، وخيار تجميع حسب نوع الحساب/الفرع/مركز التكلفة/مستوى الشجرة."""
    branches = services.list_branches(True)
    allowed_branches = services.user_branch_ids()
    branches = [b for b in branches if not allowed_branches or b.id in allowed_branches]
    centers = services.list_cost_centers(True)
    allowed_centers = services.user_cost_center_ids()
    centers = [c for c in centers if not allowed_centers or c.id in allowed_centers]

    range_f = theme.DateRangeField('الفترة', page, width=290)
    date_from, date_to = range_f.start, range_f.end
    branch_dd = ft.Dropdown(
        label='الفرع', width=190,
        options=[ft.dropdown.Option('', 'كل الفروع')] + [ft.dropdown.Option(str(b.id), f'{b.code} - {b.name}') for b in branches],
        value='',
    )
    center_dd = ft.Dropdown(
        label='مركز التكلفة', width=200,
        options=[ft.dropdown.Option('', 'كل المراكز')] + [ft.dropdown.Option(str(c.id), f'{c.code} - {c.name}') for c in centers],
        value='',
    )
    group_dd = ft.Dropdown(
        label='تجميع حسب',
        width=290,
        options=[
            ft.dropdown.Option('tree', 'شجرة الحسابات (الأب وتحته المستويات)'),
            ft.dropdown.Option('account', 'تفصيلي (كل حساب)'),
            ft.dropdown.Option('level1', 'مستوى الشجرة الأول'),
            ft.dropdown.Option('level2', 'مستوى الشجرة الثاني'),
            ft.dropdown.Option('level3', 'مستوى الشجرة الثالث'),
            ft.dropdown.Option('type', 'نوع الحساب'),
            ft.dropdown.Option('branch', 'الفرع'),
            ft.dropdown.Option('cost_center', 'مركز التكلفة'),
            ft.dropdown.Option('adv', 'عارض متقدم (فرز وفلترة وتجميع حر ورسم)'),
        ],
        value='tree',
    )
    search = ft.TextField(label='بحث بالكود أو اسم الحساب', width=260, prefix_icon=ft.Icons.SEARCH, border_radius=10)
    hide_zero = ft.Switch(label='إخفاء الحسابات بدون حركة', value=True)
    compare_sw = ft.Switch(label='مقارنة بالفترة السابقة (في الشجرة)', value=False)
    err = ft.Text('', color=theme.DANGER, visible=False)
    state = {'rows': [], 'expanded': set(), 'roots': None}

    totals_texts = {k: ft.Text('0.00', size=15, weight=ft.FontWeight.BOLD) for k in
                    ('opening_debit', 'opening_credit', 'period_debit', 'period_credit', 'closing_debit', 'closing_credit')}
    diff_text = ft.Text('0.00', size=15, weight=ft.FontWeight.BOLD)

    table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text('الكود')),
            ft.DataColumn(ft.Text('الحساب')),
            ft.DataColumn(ft.Text('رصيد أول المدة - مدين')),
            ft.DataColumn(ft.Text('رصيد أول المدة - دائن')),
            ft.DataColumn(ft.Text('حركة الفترة - مدين')),
            ft.DataColumn(ft.Text('حركة الفترة - دائن')),
            ft.DataColumn(ft.Text('الرصيد الختامي - مدين')),
            ft.DataColumn(ft.Text('الرصيد الختامي - دائن')),
        ],
        rows=[],
        expand=True,
    )

    def parse_date(v):
        if not (v or '').strip():
            return None
        try:
            return datetime.datetime.strptime(v.strip(), '%Y-%m-%d')
        except Exception:
            raise ValueError('صيغة التاريخ يجب أن تكون YYYY-MM-DD')

    def rollup_by_level(rows_data, level):
        all_accounts = services.list_accounts()
        by_id = {a.id: a for a in all_accounts}

        def ancestor_at_level(acc_id, lvl):
            chain = []
            a = by_id.get(acc_id)
            while a:
                chain.append(a)
                a = by_id.get(a.parent_id) if a.parent_id else None
            chain.reverse()
            if len(chain) - 1 <= lvl:
                return chain[-1]
            return chain[lvl]

        aggregated = {}
        for r in rows_data:
            anc = ancestor_at_level(r['account_id'], level)
            if anc is None:
                continue
            bucket = aggregated.setdefault(anc.id, {
                'code': anc.code, 'name': anc.name, 'type': anc.account_type,
                'opening_debit': 0.0, 'opening_credit': 0.0, 'period_debit': 0.0,
                'period_credit': 0.0, 'closing_debit': 0.0, 'closing_credit': 0.0,
            })
            for f in ('opening_debit', 'opening_credit', 'period_debit', 'period_credit', 'closing_debit', 'closing_credit'):
                bucket[f] += r[f]
        return sorted(aggregated.values(), key=lambda x: x['code'])

    def _set_totals(sums):
        for k, txt in totals_texts.items():
            txt.value = f'{sums[k]:,.2f}'
        diff = sums['closing_debit'] - sums['closing_credit']
        diff_text.value = f'{diff:,.2f}'
        diff_text.color = theme.SUCCESS if abs(diff) < 0.01 else theme.DANGER

    def drill(acc_id):
        """فتح دفتر الأستاذ للحساب ده بنفس الفترة (للحساب الأب بيشمل فروعه)."""
        page._erp_ledger_preset = {'account_id': acc_id, 'date_from': (date_from.value or '').strip(), 'date_to': (date_to.value or '').strip()}
        goto = getattr(page, '_erp_goto', None)
        if goto:
            goto('ledger')

    def toggle(nid):
        ex = state['expanded']
        ex.discard(nid) if nid in ex else ex.add(nid)
        refresh()

    def set_all(open_):
        def ids(ns):
            for n in ns:
                if n['children']:
                    yield n['id']; yield from ids(n['children'])
        state['expanded'] = set(ids(state['roots'] or [])) if open_ else set()
        refresh()

    def _walk(ns):
        for n in ns:
            yield n
            yield from _walk(n['children'])

    def render_tree(df, dt, branch_id, cost_center_id):
        raw = services.trial_balance_detailed(df, dt, branch_id, cost_center_id, group_by=None)
        parents = {a.id: a.parent_id for a in services.list_accounts()}
        roots = tb_tree.build_tree(raw, parents)
        if state['roots'] is None:                      # أول مرة: المستوى الأول مفتوح
            state['expanded'] = {r['id'] for r in roots if r['children']}
        state['roots'] = roots
        prev = {}
        base_cols = table.columns[:8]
        if compare_sw.value and df and dt:
            span = (dt.date() - df.date()).days + 1
            p_to = df - datetime.timedelta(days=1)
            p_from = p_to - datetime.timedelta(days=span - 1)
            praw = services.trial_balance_detailed(p_from, p_to, branch_id, cost_center_id, group_by=None)
            for pn in _walk(tb_tree.build_tree(praw, parents)):
                prev[pn['id']] = pn['closing_debit'] - pn['closing_credit']
            table.columns = base_cols + [ft.DataColumn(ft.Text('الرصيد الختامي - الفترة السابقة')), ft.DataColumn(ft.Text('التغيّر عن الفترة السابقة'))]
        else:
            table.columns = base_cols
        vis = tb_tree.visible_rows(roots, state['expanded'], hide_zero.value, search.value)
        B = ft.FontWeight.BOLD
        rows, exp = [], []
        for n in vis:
            d = n['depth']
            opened = n['id'] in state['expanded'] or bool((search.value or '').strip())
            lead = (ft.IconButton(ft.Icons.EXPAND_MORE if opened else ft.Icons.CHEVRON_LEFT, icon_size=18, width=28, height=28, padding=0,
                                  on_click=lambda e, i=n['id']: toggle(i)) if n['has_children'] else ft.Container(width=28))
            bold = B if n['has_children'] else None
            bg = theme.MAIN_ROW_BG if d == 0 else (theme.ROW_BG[1] if n['has_children'] else None)
            rows.append(ft.DataRow(color=bg, cells=[
                ft.DataCell(ft.Text(n['code'], weight=bold, color=theme.PRIMARY_TEXT), on_tap=lambda e, i=n['id']: drill(i)),
                ft.DataCell(ft.Row([ft.Container(width=16 * d), lead, ft.Text(n['name'], weight=bold)], spacing=2), on_tap=lambda e, i=n['id']: drill(i)),
                *[ft.DataCell(ft.Text(f"{n[k]:,.2f}", weight=bold if k.startswith('closing') or n['has_children'] else None)) for k in tb_tree._F],
                *([ft.DataCell(ft.Text(f"{prev.get(n['id'], 0.0):,.2f}")),
                   ft.DataCell(ft.Text(f"{(n['closing_debit'] - n['closing_credit']) - prev.get(n['id'], 0.0):,.2f}", weight=ft.FontWeight.BOLD))] if prev or (compare_sw.value and df and dt) else []),
            ]))
            exp.append(dict(n, name=('    ' * d) + n['name']))
        table.rows = rows
        state['rows'] = exp
        _set_totals(tb_tree.totals(roots))
        page.update()

    adv = {'viewer': None}
    adv_box = ft.Column([], visible=False)

    def render_adv(df, dt, branch_id, cost_center_id):
        from .. import report_engine as RE
        from ..report_viewer import ReportViewer, Mode
        if adv['viewer'] is None:
            M = RE.MONEY
            adv['viewer'] = ReportViewer(page, 'trial_balance_adv', 'ميزان المراجعة', [
                RE.Col('code', 'الكود', bold=True), RE.Col('name', 'الحساب', width=2.4), RE.Col('type', 'النوع'), RE.Col('root', 'المجموعة الرئيسية', width=1.6),
                RE.Col('opening_debit', 'أول المدة - مدين', M, 'sum'), RE.Col('opening_credit', 'أول المدة - دائن', M, 'sum'),
                RE.Col('period_debit', 'الحركة - مدين', M, 'sum'), RE.Col('period_credit', 'الحركة - دائن', M, 'sum'),
                RE.Col('closing_debit', 'الختامي - مدين', M, 'sum', bold=True), RE.Col('closing_credit', 'الختامي - دائن', M, 'sum', bold=True),
                RE.Col('balance', 'صافي الرصيد (مدين - دائن)', M, 'sum')],
                modes=[Mode('by_type', 'حسب نوع الحساب', ['type']), Mode('by_root', 'حسب المجموعة الرئيسية', ['root']), Mode('root_type', 'مجموعة ← حساب', ['root'])],
                on_row_click=lambda r: drill(r['account_id']) if r.get('account_id') else None, chart_value='period_debit')
            adv_box.controls = [adv['viewer'].control]
        rows = services.trial_balance_detailed(df, dt, branch_id, cost_center_id, group_by=None)
        roots = {a.id: a for a in services.list_accounts()}
        out = []
        for r in rows:
            if hide_zero.value and not any(r.get(k, 0) for k in ('opening_debit', 'opening_credit', 'period_debit', 'period_credit')):
                continue
            a = roots.get(r['account_id'])
            top = a
            while top is not None and top.parent_id and roots.get(top.parent_id):
                top = roots[top.parent_id]
            out.append(dict(r, root=(f'{top.code} - {top.name}' if top else ''), balance=round(r['closing_debit'] - r['closing_credit'], 2)))
        adv['viewer'].set_rows(out)
        _set_totals({k: sum(x.get(k, 0) for x in out) for k in totals_texts})
        state['rows'] = out
        page.update()

    def refresh(e=None):
        try:
            df = parse_date(date_from.value)
            dt = parse_date(date_to.value)
        except ValueError as ex:
            err.value = str(ex); err.visible = True; page.update()
            return
        err.visible = False

        group_val = group_dd.value or 'tree'
        branch_id = int(branch_dd.value) if branch_dd.value else None
        cost_center_id = int(center_dd.value) if center_dd.value else None

        adv_box.visible = group_val == 'adv'
        table_card.visible = group_val != 'adv'
        if group_val == 'adv':
            return render_adv(df, dt, branch_id, cost_center_id)
        if group_val == 'tree':
            return render_tree(df, dt, branch_id, cost_center_id)
        if group_val.startswith('level'):
            rows_data = services.trial_balance_detailed(df, dt, branch_id, cost_center_id, group_by=None)
            rows_data = rollup_by_level(rows_data, int(group_val[-1]) - 1)
        elif group_val in ('type', 'branch', 'cost_center'):
            rows_data = services.trial_balance_detailed(df, dt, branch_id, cost_center_id, group_by=group_val)
            for r in rows_data:
                r['name'] = r.get('label', r.get('name', ''))
        else:
            rows_data = services.trial_balance_detailed(df, dt, branch_id, cost_center_id, group_by=None)
            for r in rows_data:
                r['name'] = r['name']

        query = (search.value or '').strip().lower()
        main_codes = services.main_account_codes()
        rows = []
        filtered_rows_data = []
        sums = {k: 0.0 for k in totals_texts}

        for r in rows_data:
            has_movement = any(r.get(k, 0) for k in ('opening_debit', 'opening_credit', 'period_debit', 'period_credit'))
            if hide_zero.value and not has_movement:
                continue
            code = r.get('code', '') or ''
            name = r.get('name', '')
            if query and query not in code.lower() and query not in name.lower():
                continue
            for k in sums:
                sums[k] += r.get(k, 0)
            filtered_rows_data.append(r)
            is_main = bool(code) and code in main_codes
            W = ft.FontWeight.W_800 if is_main else None
            C = theme.PRIMARY_TEXT if is_main else None
            rows.append(ft.DataRow(color=theme.MAIN_ROW_BG if is_main else None, cells=[
                ft.DataCell(ft.Text(code, weight=W, color=C), on_tap=(lambda e, i=r.get('account_id'): drill(i)) if r.get('account_id') else None),
                ft.DataCell(ft.Row([ft.Text(name, weight=W, color=C)] + ([ft.Container(
                    content=ft.Text('رئيسي', size=10, color='#FFFFFF'), bgcolor=theme.PRIMARY, border_radius=6,
                    padding=ft.Padding(left=6, right=6, top=1, bottom=1))] if is_main else []), spacing=6)),
                ft.DataCell(ft.Text(f"{r.get('opening_debit',0):,.2f}", weight=W, color=C)),
                ft.DataCell(ft.Text(f"{r.get('opening_credit',0):,.2f}", weight=W, color=C)),
                ft.DataCell(ft.Text(f"{r.get('period_debit',0):,.2f}", weight=W, color=C)),
                ft.DataCell(ft.Text(f"{r.get('period_credit',0):,.2f}", weight=W, color=C)),
                ft.DataCell(ft.Text(f"{r.get('closing_debit',0):,.2f}", weight=ft.FontWeight.BOLD, color=C)),
                ft.DataCell(ft.Text(f"{r.get('closing_credit',0):,.2f}", weight=ft.FontWeight.BOLD, color=C)),
            ]))

        table.rows = rows
        # التصدير لازم ياخد نفس الصفوف الظاهرة فعليًا على الشاشة (بعد فلتر
        # البحث وإخفاء الحسابات بدون حركة)، مش كل الحسابات الخام - عشان لو
        # المستخدم دوّر على حساب معيّن وصدّر، الملف يطلع بنفس النتيجة اللي شايفها.
        state['rows'] = filtered_rows_data
        for k, txt in totals_texts.items():
            txt.value = f'{sums[k]:,.2f}'
        diff = (sums['closing_debit'] - sums['closing_credit'])
        diff_text.value = f'{diff:,.2f}'
        diff_text.color = theme.SUCCESS if abs(diff) < 0.01 else theme.DANGER
        page.update()

    def do_export(kind):
        try:
            exports_dir = services.downloads_dir()
            data = {'trial_balance': state['rows'], 'date_from': parse_date(date_from.value), 'date_to': parse_date(date_to.value)}
            path = (export_excel if kind == 'xlsx' else export_pdf)(data, 'trial', exports_dir)
            theme.open_or_download_file(page, path)
            page.overlay.append(ft.SnackBar(ft.Text(f'تم إنشاء الملف: {path}'), open=True)); page.update()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

    for ctl in (date_from, date_to, branch_dd, center_dd, group_dd, search, hide_zero, compare_sw):
        if isinstance(ctl, ft.Dropdown):
            ctl.on_select = refresh
        else:
            ctl.on_change = refresh

    table_card = theme.card(theme.h_scroll(table), expand=True)
    refresh()

    summary_row = ft.Column(
        [
            ft.Row([ft.Text('رصيد أول المدة:'), ft.Text('مدين'), totals_texts['opening_debit'], ft.Text('دائن'), totals_texts['opening_credit']], wrap=True, spacing=8),
            ft.Row([ft.Text('حركة الفترة:'), ft.Text('مدين'), totals_texts['period_debit'], ft.Text('دائن'), totals_texts['period_credit']], wrap=True, spacing=8),
            ft.Row([ft.Text('الرصيد الختامي:'), ft.Text('مدين'), totals_texts['closing_debit'], ft.Text('دائن'), totals_texts['closing_credit'],
                    ft.Container(width=24), ft.Text('الفرق (لازم صفر):'), diff_text], wrap=True, spacing=8),
        ],
        spacing=6,
    )

    return ft.Column(
        [
            theme.page_title('ميزان المراجعة', 'رصيد أول المدة + حركة الفترة + الرصيد الختامي (مدين/دائن) لكل حساب'),
            ft.Row([range_f.control, branch_dd, center_dd, group_dd,
                    ft.TextButton('فتح الكل', icon=ft.Icons.UNFOLD_MORE, on_click=lambda e: set_all(True)),
                    ft.TextButton('قفل الكل', icon=ft.Icons.UNFOLD_LESS, on_click=lambda e: set_all(False))], wrap=True, spacing=10),
            ft.Row(
                [search, hide_zero, compare_sw, ft.Container(content=ft.Text('الحسابات الرئيسية: خط عريض + خلفية فاتحة + شارة "رئيسي"', size=11, color=theme.PRIMARY_TEXT), bgcolor=theme.MAIN_ROW_BG, border_radius=8, padding=ft.Padding(left=10, right=10, top=5, bottom=5)),
                 ft.ElevatedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: do_export('xlsx')),
                 ft.ElevatedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: do_export('pdf'))],
                wrap=True, spacing=10,
            ),
            err,
            ft.Container(height=4),
            theme.card(summary_row, padding=16),
            ft.Container(height=12),
            table_card, adv_box,
        ],
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )
