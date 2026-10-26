import datetime, os
import flet as ft
from .. import journal_tools, journal_tree, services, theme
from . import journal_dialogs
from ..report_export import export_excel, export_pdf


def build_general_journal(page: ft.Page):
    """اليومية العامة: عرض جميع القيود المرحلة من كل المصادر (يدوي، فواتير، سندات، تسويات، إقفال)."""
    branches = services.list_branches(True)
    allowed_branches = services.user_branch_ids()
    branches = [b for b in branches if not allowed_branches or b.id in allowed_branches]
    centers = services.list_cost_centers(True)
    allowed_centers = services.user_cost_center_ids()
    centers = [c for c in centers if not allowed_centers or c.id in allowed_centers]

    def opt_branches(include_empty=True):
        opts = [ft.dropdown.Option('', 'غير محدد')] if include_empty else []
        opts += [ft.dropdown.Option(str(b.id), f'{b.code} - {b.name}') for b in branches]
        return opts

    def opt_centers(include_empty=True):
        opts = [ft.dropdown.Option('', 'غير محدد')] if include_empty else []
        opts += [ft.dropdown.Option(str(c.id), f'{c.code} - {c.name}') for c in centers]
        return opts

    today = datetime.date.today().strftime('%Y-%m-%d')
    err = ft.Text('', color=theme.DANGER, visible=False)
    state = {'export_rows': []}

    postable_accounts = services.list_accounts(postable_only=True)
    customers = services.list_customers()
    suppliers = services.list_suppliers()
    employees = services.list_employees()
    source_names = {
        'manual': 'قيد يدوي', 'sales_invoice': 'فاتورة مبيعات', 'purchase_invoice': 'فاتورة مشتريات',
        'receipt': 'سند قبض', 'payment': 'سند صرف', 'inventory_adjustment': 'تسوية جردية', 'closing': 'إقفال سنوي',
        'recurring': 'قيد متكرر', 'reversal': 'قيد عكسي',
    }

    def opt_accounts():
        return [ft.dropdown.Option(key=str(a.id), text=f'{a.code} - {a.name}') for a in postable_accounts]

    def opt_partners():
        opts = [ft.dropdown.Option('', 'بدون')]
        opts += [ft.dropdown.Option(f'customer:{c.id}', f'عميل - {c.name}') for c in customers]
        opts += [ft.dropdown.Option(f'supplier:{s.id}', f'مورد - {s.name}') for s in suppliers]
        return opts

    def opt_employees():
        return [ft.dropdown.Option('', 'بدون')] + [ft.dropdown.Option(str(emp.id), f'{emp.code} - {emp.name}') for emp in employees]

    emp_names = {emp.id: f'{emp.code} - {emp.name}' for emp in employees}
    party_names = {('customer', c.id): c.name for c in customers}
    party_names.update({('supplier', s.id): s.name for s in suppliers})

    def partner_value(ln):
        if ln.partner_type and ln.partner_id and ln.partner_type != 'employee':
            return f'{ln.partner_type}:{ln.partner_id}'
        return ''

    ctx = {'accounts': postable_accounts, 'on_reversed': lambda new_id: (refresh(), open_entry_dialog(new_id))}

    def open_entry_dialog(entry_id):
        entry = services.get_journal_entry(entry_id)
        if not entry:
            page.overlay.append(ft.SnackBar(ft.Text('تعذر العثور على القيد'), open=True)); page.update()
            return

        is_manual = entry.source_type == 'manual'
        edit_mode = {'value': False}
        dlg_err = ft.Text('', color=theme.DANGER, visible=False)
        line_rows_state = []

        info_text = ft.Text(
            f"رقم القيد: {entry.number}   |   التاريخ: {entry.date.strftime('%Y-%m-%d')}   |   "
            f"المصدر: {source_names.get(entry.source_type, entry.source_type)}   |   "
            f"الحالة: {'مرحّل' if entry.posted else 'مسودة'}"
            + (f"   |   عُكس بالقيد رقم {entry.reversed_by_id}" if entry.reversed_by_id else '')
            + (f"   |   عكس للقيد رقم {entry.reversal_of_id}" if entry.reversal_of_id else ''),
            weight=ft.FontWeight.BOLD,
        )
        ref_field = ft.TextField(label='المرجع', value=entry.reference or '', width=200, read_only=True)
        desc_field = ft.TextField(label='البيان', value=entry.description or '', width=300, read_only=True)

        lines_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text('الحساب')), ft.DataColumn(ft.Text('بيان السطر')),
                ft.DataColumn(ft.Text('العميل / المورد')), ft.DataColumn(ft.Text('الموظف')), ft.DataColumn(ft.Text('الفرع')),
                ft.DataColumn(ft.Text('مركز التكلفة')), ft.DataColumn(ft.Text('مدين')),
                ft.DataColumn(ft.Text('دائن')), ft.DataColumn(ft.Text('')),
            ],
            rows=[],
        )

        branch_map = {b.id: f'{b.code} - {b.name}' for b in branches}
        center_map = {c.id: f'{c.code} - {c.name}' for c in centers}

        def build_readonly_rows():
            rows = []
            for ln in entry.lines:
                account_text = f'{ln.account.code} - {ln.account.name}' if ln.account else '-'
                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(account_text)),
                    ft.DataCell(ft.Text(ln.description or '-')),
                    ft.DataCell(ft.Text(party_names.get((ln.partner_type, ln.partner_id), '-'))),
                    ft.DataCell(ft.Text(emp_names.get(ln.partner_id, '-') if ln.partner_type == 'employee' else '-')),
                    ft.DataCell(ft.Text(branch_map.get(ln.branch_id, '-'))),
                    ft.DataCell(ft.Text(center_map.get(ln.cost_center_id, '-'))),
                    ft.DataCell(ft.Text(f'{ln.debit:,.2f}')),
                    ft.DataCell(ft.Text(f'{ln.credit:,.2f}')),
                    ft.DataCell(ft.Text('')),
                ]))
            return rows

        def add_edit_line(existing_line=None):
            account = ft.Dropdown(label='الحساب', width=190, options=opt_accounts(),
                                   value=str(existing_line.account_id) if existing_line else None)
            desc = ft.TextField(label='بيان', width=150, value=existing_line.description if existing_line else '')
            partner = ft.Dropdown(label='الطرف', width=160, options=opt_partners(),
                                   value=partner_value(existing_line) if existing_line else '')
            employee = ft.Dropdown(label='الموظف', width=170, options=opt_employees(),
                                    value=str(existing_line.partner_id) if existing_line and existing_line.partner_type == 'employee' and existing_line.partner_id else '')
            branch_dd = ft.Dropdown(label='الفرع', width=150, options=opt_branches(),
                                     value=str(existing_line.branch_id) if existing_line and existing_line.branch_id else '')
            center_dd = ft.Dropdown(label='مركز التكلفة', width=160, options=opt_centers(),
                                     value=str(existing_line.cost_center_id) if existing_line and existing_line.cost_center_id else '')
            debit = ft.TextField(label='مدين', width=100, value=str(existing_line.debit if existing_line else 0), keyboard_type=ft.KeyboardType.NUMBER)
            credit = ft.TextField(label='دائن', width=100, value=str(existing_line.credit if existing_line else 0), keyboard_type=ft.KeyboardType.NUMBER)
            item = {'account': account, 'description': desc, 'partner': partner, 'employee': employee, 'branch': branch_dd, 'center': center_dd, 'debit': debit, 'credit': credit}
            remove_btn = ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip='حذف السطر')
            row = ft.DataRow(cells=[
                ft.DataCell(account), ft.DataCell(desc), ft.DataCell(partner), ft.DataCell(employee),
                ft.DataCell(branch_dd), ft.DataCell(center_dd),
                ft.DataCell(debit), ft.DataCell(credit), ft.DataCell(remove_btn),
            ])
            item['row'] = row

            def remove(e):
                if item in line_rows_state:
                    line_rows_state.remove(item)
                if row in lines_table.rows:
                    lines_table.rows.remove(row)
                page.update()
            remove_btn.on_click = remove

            line_rows_state.append(item)
            lines_table.rows.append(row)

        def render_edit_rows():
            line_rows_state.clear()
            lines_table.rows.clear()
            for ln in entry.lines:
                add_edit_line(ln)
            if not entry.lines:
                add_edit_line()

        def build_content():
            controls = [info_text, ft.Row([ref_field, desc_field]), ft.Divider(), theme.h_scroll(lines_table)]
            if edit_mode['value']:
                controls.append(ft.OutlinedButton('إضافة سطر', icon=ft.Icons.ADD, on_click=lambda e: (add_edit_line(), page.update())))
            controls.append(dlg_err)
            return ft.Container(content=ft.Column(controls, spacing=10, tight=True, scroll=ft.ScrollMode.AUTO), width=650, height=430)

        def refresh_dialog_body():
            if edit_mode['value']:
                render_edit_rows()
            else:
                lines_table.rows = build_readonly_rows()
            dialog.content = build_content()
            page.update()

        def start_edit(e):
            try:
                services.set_journal_entry_draft(entry.id)
                edit_mode['value'] = True
                dlg_err.visible = False
                refresh_dialog_body()
                rebuild_actions()
            except Exception as ex:
                dlg_err.value = str(ex); dlg_err.visible = True; page.update()

        def save_and_post(e):
            try:
                data = []
                for it in line_rows_state:
                    if not it['account'].value:
                        continue
                    ptype = pid = None
                    if it['employee'].value and it['partner'].value:
                        raise ValueError('السطر ده ليه طرفين: اختار عميل/مورد أو موظف، مش الاتنين')
                    if it['employee'].value:
                        ptype, pid = 'employee', int(it['employee'].value)
                    elif it['partner'].value:
                        ptype, pid_s = it['partner'].value.split(':')
                        pid = int(pid_s)
                    data.append({
                        'account_id': int(it['account'].value),
                        'description': it['description'].value or '',
                        'debit': float(it['debit'].value or 0),
                        'credit': float(it['credit'].value or 0),
                        'partner_type': ptype, 'partner_id': pid,
                        'branch_id': int(it['branch'].value) if it['branch'].value else None,
                        'cost_center_id': int(it['center'].value) if it['center'].value else None,
                    })
                services.update_journal_entry(entry.id, data, reference=ref_field.value, description=desc_field.value)
                services.post_journal_entry_by_id(entry.id)
                dialog.open = False
                page.update()
                refresh()
            except Exception as ex:
                dlg_err.value = str(ex); dlg_err.visible = True; page.update()

        def cancel_edit(e):
            try:
                if edit_mode['value']:
                    services.post_journal_entry_by_id(entry.id)
            except Exception:
                pass
            dialog.open = False
            page.update()
            refresh()

        def close_readonly(e):
            dialog.open = False
            page.update()

        def do_print_entry(e):
            try:
                path = services.generate_journal_entry_pdf_file(entry.id)
                theme.open_or_download_file(page, path)
            except Exception as ex:
                page.overlay.append(ft.SnackBar(ft.Text(f'تعذرت الطباعة: {ex}'), open=True)); page.update()

        def rebuild_actions():
            if edit_mode['value']:
                dialog.actions = [
                    ft.TextButton('إلغاء (رجوع للحالة المرحّلة)', on_click=cancel_edit),
                    ft.FilledButton('حفظ وإعادة الترحيل', icon=ft.Icons.CHECK_CIRCLE, bgcolor=theme.PRIMARY, on_click=save_and_post),
                ]
            else:
                can_reverse = entry.posted and entry.source_type in journal_tools.REVERSIBLE_SOURCES and not entry.reversed_by_id and not entry.reversal_of_id
                actions = [
                    ft.IconButton(icon=ft.Icons.PRINT_OUTLINED, tooltip='طباعة', on_click=do_print_entry),
                    ft.IconButton(icon=ft.Icons.ATTACH_FILE, tooltip='مرفقات القيد', on_click=lambda e: journal_dialogs.attachments_dialog(page, ctx, entry.id)),
                    ft.TextButton('إغلاق', on_click=close_readonly),
                ]
                if can_reverse:
                    actions.append(ft.OutlinedButton('قيد عكسي', icon=ft.Icons.UNDO, on_click=lambda e: (setattr(dialog, 'open', False), journal_dialogs.reverse_dialog(page, ctx, entry.id))))
                if is_manual:
                    actions.append(ft.OutlinedButton('تعديل القيد', icon=ft.Icons.EDIT, on_click=start_edit))
                dialog.actions = actions
            page.update()

        if not is_manual:
            lines_table.rows = build_readonly_rows()
            note = ft.Text(
                'ده قيد مولّد تلقائياً من النظام - مينفعش تتعدّل عليه من هنا. '
                'لو محتاج تعدّله، عدّل المستند المصدر (الفاتورة/السند/التسوية) بدل كده.',
                color=theme.WARNING,
            )
            dialog_content = ft.Container(
                content=ft.Column([info_text, note, ft.Divider(), theme.h_scroll(lines_table)],
                                   spacing=10, tight=True, scroll=ft.ScrollMode.AUTO),
                width=650, height=400,
            )
        else:
            lines_table.rows = build_readonly_rows()
            dialog_content = build_content()

        dialog = ft.AlertDialog(modal=True, title=ft.Text('تفاصيل القيد'), content=dialog_content, actions=[], actions_alignment=ft.MainAxisAlignment.END)
        page.overlay.append(dialog)
        rebuild_actions()
        dialog.open = True
        page.update()

    gj_range = theme.DateRangeField('الفترة', page, width=290, start=today[:8] + '01', end=today)
    gj_from, gj_to = gj_range.start, gj_range.end
    gj_branch = ft.Dropdown(label='الفرع', width=190, options=opt_branches(), value='')
    gj_center = ft.Dropdown(label='مركز التكلفة', width=205, options=opt_centers(), value='')
    gj_group = ft.Dropdown(
        label='تجميع حسب', width=190,
        options=[
            ft.dropdown.Option('none', 'تفصيلي (كل سطر)'),
            ft.dropdown.Option('adv', 'عارض متقدم'),
            ft.dropdown.Option('tree', 'شجري (اختر المستويات)'),
            ft.dropdown.Option('source', 'المصدر (مع قيوده)'),
            ft.dropdown.Option('type', 'نوع الحساب'),
            ft.dropdown.Option('branch', 'الفرع'),
            ft.dropdown.Option('cost_center', 'مركز التكلفة'),
        ],
        value='none',
    )
    gj_search = ft.TextField(label='بحث في رقم القيد / الحساب / البيان / المرجع', width=310)
    gj_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text('رقم القيد')),
            ft.DataColumn(ft.Text('التاريخ')),
            ft.DataColumn(ft.Text('المصدر')),
            ft.DataColumn(ft.Text('الحساب')),
            ft.DataColumn(ft.Text('بيان السطر')),
            ft.DataColumn(ft.Text('الفرع')),
            ft.DataColumn(ft.Text('مركز التكلفة')),
            ft.DataColumn(ft.Text('مدين')),
            ft.DataColumn(ft.Text('دائن')),
            ft.DataColumn(ft.Text('')),
        ], rows=[]
    )
    gj_pager = theme.RowPager(gj_table, page, 100)
    gj_group_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text('البند')),
            ft.DataColumn(ft.Text('مدين')),
            ft.DataColumn(ft.Text('دائن')),
        ], rows=[], visible=False,
    )
    gj_source_column = ft.Column([], spacing=8, visible=False)
    # ---- التجميع الشجري: المستخدم يختار ترتيب المستويات (الفرع / الحساب / الطرف / مركز التكلفة)
    lvl_defaults = ['branch', 'account', 'party', 'cost_center']
    lvl_opts = [ft.dropdown.Option('', 'بدون')] + [ft.dropdown.Option(k, v) for k, v in journal_tree.LEVELS.items()]
    gj_levels = [ft.Dropdown(label=f'المستوى {i + 1}', width=190, options=lvl_opts, value=lvl_defaults[i]) for i in range(4)]
    gj_levels_row = ft.Row(gj_levels, wrap=True, spacing=8, visible=False)
    gj_tree_column = ft.Column([], spacing=6, visible=False)
    gj_tree_summary = ft.Text('', size=13, weight=ft.FontWeight.BOLD)
    tree_state = {'nodes': [], 'grand': None, 'levels': []}

    def _party_label(ln):
        pt, pid = getattr(ln, 'partner_type', None), getattr(ln, 'partner_id', None)
        if not pt or not pid:
            return ''
        if pt == 'employee':
            return f"موظف - {emp_names.get(pid, pid)}"
        return f"{'عميل' if pt == 'customer' else 'مورد'} - {party_names.get((pt, pid), pid)}"

    def _tree_rows():
        d1 = gj_from.value.strip() if gj_from.value else None
        d2 = gj_to.value.strip() if gj_to.value else None
        bid = int(gj_branch.value) if gj_branch.value else None
        ccid = int(gj_center.value) if gj_center.value else None
        needle = (gj_search.value or '').strip().lower()
        branch_map = {b.id: f'{b.code} - {b.name}' for b in branches}
        center_map = {c.id: f'{c.code} - {c.name}' for c in centers}
        rows = []
        for j in services.list_journal_entries(limit=100000, date_from=d1, date_to=d2):
            for ln in (j.lines or []):
                if bid and ln.branch_id != bid:
                    continue
                if ccid and ln.cost_center_id != ccid:
                    continue
                acct = f'{ln.account.code} - {ln.account.name}' if ln.account else ''
                text = ln.description or j.description or ''
                if needle and needle not in ' '.join([j.number or '', j.reference or '', j.description or '', acct, text]).lower():
                    continue
                rows.append({'entry_id': j.id, 'number': j.number, 'date': j.date.strftime('%Y-%m-%d') if j.date else '', 'description': text,
                             'source': source_names.get(j.source_type, j.source_type or ''), 'account': acct, 'party': _party_label(ln),
                             'branch': branch_map.get(ln.branch_id, ''), 'cost_center': center_map.get(ln.cost_center_id, ''),
                             'debit': float(ln.debit or 0), 'credit': float(ln.credit or 0)})
        return rows

    def _m(v):
        return f'{v:,.2f}'

    def _lines_table(lines, levels):
        extra = [(k, journal_tree.LEVELS[k]) for k in ('account', 'party', 'branch', 'cost_center') if k not in levels]
        cols = [ft.DataColumn(ft.Text(c, size=12)) for c in ['رقم القيد', 'التاريخ'] + [n for _, n in extra] + ['بيان السطر']] + \
               [ft.DataColumn(ft.Text('مدين', size=12), numeric=True), ft.DataColumn(ft.Text('دائن', size=12), numeric=True), ft.DataColumn(ft.Text(''))]
        tbl = ft.DataTable(columns=cols, rows=[], heading_row_height=36, data_row_min_height=32)

        def build(r):
            cells = [ft.DataCell(ft.Text(r['number'], size=12)), ft.DataCell(ft.Text(r['date'], size=12))]
            cells += [ft.DataCell(ft.Text(r[k] or '-', size=12)) for k, _ in extra]
            cells += [ft.DataCell(ft.Text(r['description'] or '-', size=12)), ft.DataCell(ft.Text(_m(r['debit']) if r['debit'] else '-', size=12)),
                      ft.DataCell(ft.Text(_m(r['credit']) if r['credit'] else '-', size=12)),
                      ft.DataCell(ft.IconButton(icon=ft.Icons.OPEN_IN_NEW, tooltip='فتح القيد', on_click=lambda e, jid=r['entry_id']: open_entry_dialog(jid)))]
            return ft.DataRow(cells=cells)
        theme.RowPager(tbl, page, 100).set_items(lines, build, keep_page=False)
        return ft.Container(theme.h_scroll(tbl), padding=ft.Padding(left=8, right=8, top=0, bottom=8))

    def _make_tile(node, levels):
        colors = [theme.PRIMARY_TEXT, None, None, None]
        tile = ft.ExpansionTile(
            title=ft.Text(f"{journal_tree.LEVELS[node['level']]}: {node['label']}", weight=ft.FontWeight.BOLD, size=14 - node['depth'] * 0.5, color=colors[min(node['depth'], 3)]),
            subtitle=ft.Text(f"{node['count']} سطر   |   مدين: {_m(node['debit'])}   |   دائن: {_m(node['credit'])}   |   الرصيد: {_m(node['balance'])}", size=12, color=theme.TEXT_MUTED),
            controls=[ft.Text('...', size=11, color=theme.TEXT_MUTED)], expanded=False,
        )
        loaded = {'v': False}

        def on_change(e):
            if loaded['v'] or not tile.expanded:
                return
            loaded['v'] = True
            tile.controls = [ft.Container(_make_tile(c, levels), padding=ft.Padding(left=0, right=16, top=0, bottom=0)) for c in node['children']] if node['children'] else [_lines_table(node['lines'], levels)]
            page.update()
        tile.on_change = on_change
        return tile

    def refresh_tree():
        gj_table.visible = False
        gj_group_table.visible = False
        gj_source_column.visible = False
        gj_tree_column.visible = True
        try:
            levels = journal_tree.clean_levels([d.value for d in gj_levels])
            if not levels:
                raise ValueError('اختر مستوى تجميع واحد على الأقل')
            rows = _tree_rows()
            nodes, grand = journal_tree.build_tree(rows, levels)
            tree_state.update(nodes=nodes, grand=grand, levels=levels)
            gj_tree_summary.value = f"{grand['count']} سطر   |   إجمالي مدين: {_m(grand['debit'])}   |   إجمالي دائن: {_m(grand['credit'])}   |   الفرق: {_m(grand['balance'])}"
            gj_tree_column.controls = [gj_tree_summary] + ([_make_tile(n, levels) for n in nodes] if nodes else [ft.Text('لا توجد قيود مطابقة', color=theme.TEXT_MUTED)])
            state['export_rows'] = rows
            err.visible = False
        except Exception as ex:      # noqa: BLE001
            err.value = str(ex); err.visible = True
        page.update()

    SOURCE_LABELS = {
        'manual': 'قيود يدوية', 'sales_invoice': 'فواتير مبيعات', 'purchase_invoice': 'فواتير مشتريات',
        'receipt': 'سندات قبض', 'payment': 'سندات صرف', 'inventory_adjustment': 'تسويات جردية', 'closing': 'إقفال سنوي',
        'payroll': 'رواتب', 'payroll_payment': 'صرف رواتب', 'allowance_insurance': 'مخصصات وتأمينات',
        'depreciation': 'إهلاك أصول ثابتة', 'asset_purchase_invoice': 'فواتير مشتريات أصول',
        'fixed_asset_disposal': 'استبعاد أصل ثابت', 'asset_inventory_shortage': 'استبعاد عجز جرد أصول',
        'asset_inventory_shortage_reversal': 'عكس استبعاد عجز جرد', 'eos_settlement': 'تسوية نهاية خدمة',
        'annual_leave_settlement': 'استبدال رصيد إجازة', 'transfer': 'تحويل مخزني',
        'employee_custody': 'صرف وتعزيز وتسوية عهد', 'employee_custody_expense': 'مصروفات وفواتير عهد', None: 'بدون مصدر (يدوي)',
        'recurring': 'قيود متكررة', 'reversal': 'قيود عكسية',
    }

    def build_source_groups(entries):
        """بيبني قسم قابل للطي لكل مصدر، وجوّه كل قسم جدول بكل قيوده."""
        groups = {}
        for j in entries:
            groups.setdefault(j.source_type, []).append(j)
        tiles = []
        for src, js in sorted(groups.items(), key=lambda kv: SOURCE_LABELS.get(kv[0], kv[0] or '-')):
            js.sort(key=lambda j: (j.date or datetime.datetime.min, j.number or ''), reverse=True)
            total_debit = sum(sum(ln.debit for ln in (j.lines or [])) for j in js)
            total_credit = sum(sum(ln.credit for ln in (j.lines or [])) for j in js)
            inner_table = ft.DataTable(columns=[
                ft.DataColumn(ft.Text('رقم القيد')), ft.DataColumn(ft.Text('التاريخ')), ft.DataColumn(ft.Text('المرجع')),
                ft.DataColumn(ft.Text('البيان')), ft.DataColumn(ft.Text('مدين')), ft.DataColumn(ft.Text('دائن')), ft.DataColumn(ft.Text('')),
            ], rows=[
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(j.number)),
                    ft.DataCell(ft.Text(j.date.strftime('%Y-%m-%d') if j.date else '-')),
                    ft.DataCell(ft.Text(j.reference or '-')),
                    ft.DataCell(ft.Text(j.description or '-')),
                    ft.DataCell(ft.Text(f"{sum(ln.debit for ln in (j.lines or [])):,.2f}")),
                    ft.DataCell(ft.Text(f"{sum(ln.credit for ln in (j.lines or [])):,.2f}")),
                    ft.DataCell(ft.IconButton(icon=ft.Icons.OPEN_IN_NEW, tooltip='فتح القيد', on_click=lambda e, jid=j.id: open_entry_dialog(jid))),
                ]) for j in js
            ])
            label = SOURCE_LABELS.get(src, src or 'بدون مصدر')
            tiles.append(ft.ExpansionTile(
                title=ft.Text(f'{label}  ({len(js)} قيد)', weight=ft.FontWeight.BOLD),
                subtitle=ft.Text(f'إجمالي مدين: {total_debit:,.2f}   |   إجمالي دائن: {total_credit:,.2f}', size=12, color=theme.TEXT_MUTED),
                controls=[ft.Container(content=theme.h_scroll(inner_table), padding=ft.Padding(left=8, right=8, top=0, bottom=8))],
                expanded=False,
            ))
        return tiles

    adv = {'viewer': None}
    gj_adv_column = ft.Column([], visible=False)

    def refresh_adv():
        from .. import report_engine as RE
        from ..report_viewer import ReportViewer, Mode
        if adv['viewer'] is None:
            adv['viewer'] = ReportViewer(page, 'general_journal', 'اليومية العامة', [
                RE.Col('date', 'التاريخ', RE.DATE), RE.Col('number', 'القيد', bold=True), RE.Col('source', 'المصدر'), RE.Col('account', 'الحساب', width=2),
                RE.Col('party', 'الطرف'), RE.Col('description', 'البيان', width=2.4), RE.Col('branch', 'الفرع'), RE.Col('cost_center', 'مركز التكلفة'),
                RE.Col('debit', 'مدين', RE.MONEY, 'sum'), RE.Col('credit', 'دائن', RE.MONEY, 'sum')],
                modes=[Mode('by_acc', 'حسب الحساب', ['account']), Mode('by_src', 'حسب المصدر', ['source']), Mode('by_month', 'حسب الشهر', ['date:month']),
                       Mode('by_month_acc', 'شهر ← حساب', ['date:month', 'account'])], on_row_click=lambda r: open_entry_dialog(r['entry_id']), chart_value='debit', show_export=False)
            gj_adv_column.controls = [adv['viewer'].control]
        adv['viewer'].set_rows(_tree_rows())

    def refresh(e=None):
        is_adv = gj_group.value == 'adv'
        gj_adv_column.visible = is_adv
        if is_adv:
            gj_levels_row.visible = gj_tree_column.visible = gj_table_wrap.visible = gj_group_wrap.visible = gj_source_column.visible = False
            try:
                refresh_adv()
                err.visible = False
            except Exception as ex:      # noqa: BLE001
                err.value = f'تعذر تحميل العارض: {ex}'; err.visible = True
            if e is not None:
                page.update()
            return
        gj_levels_row.visible = gj_group.value == 'tree'
        gj_tree_column.visible = False
        gj_table_wrap.visible = gj_group_wrap.visible = gj_group.value != 'tree'
        if gj_group.value == 'tree':
            return refresh_tree()
        if gj_group.value == 'source':
            gj_table.visible = False
            gj_group_table.visible = False
            gj_source_column.visible = True
            try:
                d1 = datetime.datetime.strptime(gj_from.value.strip(), '%Y-%m-%d').date() if gj_from.value else None
                d2 = datetime.datetime.strptime(gj_to.value.strip(), '%Y-%m-%d').date() if gj_to.value else None
                bid = int(gj_branch.value) if gj_branch.value else None
                ccid = int(gj_center.value) if gj_center.value else None
                needle = (gj_search.value or '').strip().lower()
                entries = services.list_journal_entries(limit=1000)
                filtered = []
                for j in entries:
                    jd = j.date.date() if j.date else None
                    if d1 and jd and jd < d1: continue
                    if d2 and jd and jd > d2: continue
                    if bid and not any(ln.branch_id == bid for ln in (j.lines or [])): continue
                    if ccid and not any(ln.cost_center_id == ccid for ln in (j.lines or [])): continue
                    if needle:
                        hay = ' '.join([j.number or '', j.reference or '', j.description or ''] +
                                       [f'{ln.account.code} {ln.account.name}' if ln.account else '' for ln in (j.lines or [])] +
                                       [ln.description or '' for ln in (j.lines or [])]).lower()
                        if needle not in hay: continue
                    filtered.append(j)
                gj_source_column.controls = build_source_groups(filtered) if filtered else [ft.Text('لا توجد قيود مطابقة', color=theme.TEXT_MUTED)]
                branch_map = {b.id: f'{b.code} - {b.name}' for b in branches}
                center_map = {c.id: f'{c.code} - {c.name}' for c in centers}
                export_rows = []
                for j in filtered:
                    for ln in (j.lines or []):
                        export_rows.append({
                            'number': j.number, 'date': j.date.strftime('%Y-%m-%d') if j.date else '-',
                            'source': SOURCE_LABELS.get(j.source_type, j.source_type or '-'),
                            'account': f'{ln.account.code} - {ln.account.name}' if ln.account else '-',
                            'description': ln.description or j.description or '-',
                            'branch': branch_map.get(ln.branch_id, '-'), 'cost_center': center_map.get(ln.cost_center_id, '-'),
                            'debit': ln.debit, 'credit': ln.credit,
                        })
                state['export_rows'] = export_rows
                err.visible = False
            except Exception as ex:
                err.value = str(ex); err.visible = True
            page.update()
            return

        gj_source_column.visible = False
        if gj_group.value and gj_group.value != 'none':
            gj_table.visible = False
            gj_group_table.visible = True
            try:
                d1 = datetime.datetime.strptime(gj_from.value.strip(), '%Y-%m-%d') if gj_from.value else None
                d2 = datetime.datetime.strptime(gj_to.value.strip(), '%Y-%m-%d') if gj_to.value else None
                bid = int(gj_branch.value) if gj_branch.value else None
                ccid = int(gj_center.value) if gj_center.value else None
                data = services.trial_balance_detailed(d1, d2, bid, ccid, group_by=gj_group.value)
                grouped_rows = []
                for r in data:
                    label = r.get('label') or r.get('name') or '-'
                    if abs(r.get('period_debit', 0)) < 0.005 and abs(r.get('period_credit', 0)) < 0.005:
                        continue
                    grouped_rows.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Text(label)),
                        ft.DataCell(ft.Text(f"{r.get('period_debit', 0):,.2f}")),
                        ft.DataCell(ft.Text(f"{r.get('period_credit', 0):,.2f}")),
                    ]))
                gj_group_table.rows = grouped_rows
                err.visible = False
            except Exception as ex:
                err.value = str(ex); err.visible = True
            page.update()
            return

        gj_table.visible = True
        gj_group_table.visible = False
        try:
            entries = services.list_journal_entries(limit=1000)
            d1 = datetime.datetime.strptime(gj_from.value.strip(), '%Y-%m-%d').date() if gj_from.value else None
            d2 = datetime.datetime.strptime(gj_to.value.strip(), '%Y-%m-%d').date() if gj_to.value else None
            bid = int(gj_branch.value) if gj_branch.value else None
            ccid = int(gj_center.value) if gj_center.value else None
            needle = (gj_search.value or '').strip().lower()
            branch_map = {b.id: f'{b.code} - {b.name}' for b in branches}
            center_map = {c.id: f'{c.code} - {c.name}' for c in centers}
            rows = []
            export_rows = []
            source_names = {
                'manual': 'قيد يدوي', 'sales_invoice': 'فاتورة مبيعات', 'purchase_invoice': 'فاتورة مشتريات',
                'receipt': 'سند قبض', 'payment': 'سند صرف', 'inventory_adjustment': 'تسوية جردية', 'closing': 'إقفال سنوي',
            }
            for j in entries:
                jd = j.date.date() if j.date else None
                if d1 and jd and jd < d1: continue
                if d2 and jd and jd > d2: continue
                for ln in (j.lines or []):
                    if bid and ln.branch_id != bid: continue
                    if ccid and ln.cost_center_id != ccid: continue
                    account_text = f'{ln.account.code} - {ln.account.name}' if ln.account else '-'
                    line_text = ln.description or j.description or '-'
                    hay = ' '.join([j.number or '', j.reference or '', j.description or '', account_text, line_text]).lower()
                    if needle and needle not in hay: continue
                    rows.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Text(j.number)),
                        ft.DataCell(ft.Text(j.date.strftime('%Y-%m-%d') if j.date else '-')),
                        ft.DataCell(ft.Text(source_names.get(j.source_type, j.source_type or '-'))),
                        ft.DataCell(ft.Text(account_text)),
                        ft.DataCell(ft.Text(line_text)),
                        ft.DataCell(ft.Text(branch_map.get(ln.branch_id, '-'))),
                        ft.DataCell(ft.Text(center_map.get(ln.cost_center_id, '-'))),
                        ft.DataCell(ft.Text(f'{ln.debit:,.2f}')),
                        ft.DataCell(ft.Text(f'{ln.credit:,.2f}')),
                        ft.DataCell(ft.IconButton(
                            icon=ft.Icons.OPEN_IN_NEW, tooltip='فتح القيد',
                            on_click=lambda e, jid=j.id: open_entry_dialog(jid),
                        )),
                    ]))
                    export_rows.append({
                        'number': j.number, 'date': j.date.strftime('%Y-%m-%d') if j.date else '-',
                        'source': source_names.get(j.source_type, j.source_type or '-'),
                        'account': account_text, 'description': line_text,
                        'branch': branch_map.get(ln.branch_id, '-'), 'cost_center': center_map.get(ln.cost_center_id, '-'),
                        'debit': ln.debit, 'credit': ln.credit,
                    })
            gj_pager.set_rows(rows, keep_page=False)
            state['export_rows'] = export_rows
            page.update()
        except Exception as ex:
            err.value = str(ex); err.visible = True; page.update()

    def do_export(kind):
        try:
            exports_dir = services.downloads_dir()
            if gj_group.value == 'adv' and adv['viewer'] is not None:
                return adv['viewer'].export(kind)
            if gj_group.value == 'tree':
                if not tree_state['levels']:
                    refresh_tree()
                data = journal_tree.export_table(tree_state['nodes'], tree_state['grand'], tree_state['levels'])
                data.update(date_from=gj_from.value or None, date_to=gj_to.value or None)
                path = (export_excel if kind == 'xlsx' else export_pdf)(data, 'general_journal_tree', exports_dir)
            else:
                path = (export_excel if kind == 'xlsx' else export_pdf)({'rows': state['export_rows']}, 'general_journal', exports_dir)
            theme.open_or_download_file(page, path)
            page.overlay.append(ft.SnackBar(ft.Text(f'تم إنشاء الملف: {path}'), open=True)); page.update()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

    gj_table_wrap = theme.h_scroll(gj_table)
    gj_group_wrap = theme.h_scroll(gj_group_table)

    for ctl in (gj_from, gj_to, gj_branch, gj_center, gj_group, gj_search, *gj_levels):
        if isinstance(ctl, ft.Dropdown):
            ctl.on_select = refresh      # في Flet الحديثة القايمة المنسدلة حدثها on_select (on_change مش موجود فيها)
        else:
            ctl.on_change = refresh

    refresh()

    general_card = theme.card(ft.Column([
        ft.Row([
            ft.Text('اليومية العامة — جميع القيود المرحلة', size=18, weight=ft.FontWeight.BOLD),
            ft.Container(expand=True),
            ft.IconButton(icon=ft.Icons.REFRESH, tooltip='تحديث', on_click=refresh),
        ]),
        ft.Text('تعرض هذه اليومية كل القيود المرحلة من القيود اليدوية والفواتير والسندات والتسويات والإقفالات، سطرًا بسطر.', color=theme.TEXT_MUTED),
        ft.Row([gj_range.control, gj_branch, gj_center, gj_group, gj_search], wrap=True, spacing=8),
        gj_levels_row,
        ft.Row([
            ft.ElevatedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: do_export('xlsx')),
            ft.ElevatedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: do_export('pdf')),
        ], wrap=True, spacing=10),
        err,
        gj_adv_column,
        gj_tree_column,
        gj_table_wrap,
        gj_group_wrap,
        gj_source_column,
    ], spacing=10), expand=True)

    return ft.Column([
        theme.page_title('اليومية العامة', 'استعراض ومراجعة جميع القيود المرحلة من كل المصادر'),
        general_card,
    ], expand=True, scroll=ft.ScrollMode.AUTO)
