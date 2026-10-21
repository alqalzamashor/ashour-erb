import datetime
import os
import flet as ft
from .. import services, theme


def build_employee_custody(page: ft.Page, mode='overview'):
    """عهد الموظفين - 4 شاشات من نفس الموديول (مجموعة المشتريات):
      issues      صرف العهد: سندات صرف وتعزيز وإرجاع (قابلة للطباعة)
      expenses    مصروفات وفواتير العهد: تقديم + اعتماد/رفض بقيد تلقائي
      settlements تسوية العهد: مستند تسوية بيطابق ويرجّع المتبقي ويقفل العهدة (قابل للطباعة)
      overview    أرصدة وكشوف العهد: متابعة كل عهدة وكشفها."""
    holder = ft.Container(expand=True)
    employees = services.list_employees()
    cfg_company = services.get_company_settings()

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def _d(v):
        v = (v or '').strip()
        return datetime.datetime.strptime(v, '%Y-%m-%d') if v else None

    def _num(f, label):
        try:
            return float((f.value or '').replace(',', '') or 0)
        except ValueError:
            raise ValueError(f'{label}: اكتب رقم صحيح')

    def pm_dropdown(width=240):
        methods = [m for m in services.list_payment_methods(active_only=True) if not m.is_credit]
        return ft.Dropdown(label='طريقة الدفع (من أين يُصرف)', width=width,
                           options=[ft.dropdown.Option(str(m.id), m.name) for m in methods],
                           value=str(methods[0].id) if methods else None), bool(methods)

    def refresh_all():
        holder.content = SECTIONS[mode]()
        page.update()

    def close_dlg(d):
        d.open = False; page.update()

    # ===================================================================== العهد
    def open_create(e=None):
        emp_dd = theme.SearchableDropdown(label='الموظف *', width=320, options=[(str(x.id), f'{x.code} - {x.name}') for x in employees])
        amount_f = ft.TextField(label='مبلغ العهدة *', width=160, keyboard_type=ft.KeyboardType.NUMBER)
        pm_dd, has_pm = pm_dropdown()
        date_f = theme.DateField('تاريخ الصرف', page, width=170, value=datetime.date.today().strftime('%Y-%m-%d'))
        purpose_f = ft.TextField(label='الغرض من العهدة', width=420)
        err = ft.Text('' if has_pm else 'مفيش طريقة دفع نقدية/بنكية - ضيفها من شاشة "طرق الدفع" الأول',
                      color=theme.DANGER, visible=not has_pm, size=12)

        def save(ev):
            try:
                if not emp_dd.value:
                    raise ValueError('اختر الموظف')
                services.create_custody(int(emp_dd.value), _num(amount_f, 'المبلغ'), int(pm_dd.value) if pm_dd.value else None,
                                        _d(date_f.value), purpose_f.value)
                close_dlg(dlg); refresh_all()
                fid = services.list_custody_fundings(kinds=('issue',))[0]
                snack(f"تم صرف العهدة - سند {fid['number']} وتسجيل القيد")
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        dlg = ft.AlertDialog(modal=True, title=ft.Text('صرف عهدة جديدة'),
            content=ft.Container(width=460, content=ft.Column([
                ft.Text('بيتسجل قيد: مدين عهد الموظفين / دائن الخزينة (أو البنك) حسب طريقة الدفع.', size=12, color=theme.TEXT_MUTED),
                emp_dd.control, ft.Row([amount_f, pm_dd], wrap=True, spacing=10), date_f.control, purpose_f, err], tight=True, spacing=12)),
            actions=[ft.TextButton('إلغاء', on_click=lambda ev: close_dlg(dlg)),
                     ft.FilledButton('صرف العهدة', icon=ft.Icons.PAYMENTS_OUTLINED, bgcolor=theme.PRIMARY, on_click=save)])
        page.overlay.append(dlg); dlg.open = True; page.update()

    def _open_custody_options():
        oc = services.list_custodies(state='open')
        return oc, [(str(c['id']), f"{c['number']} - {c['employee_name']} (رصيد {c['balance']:,.2f})") for c in oc]

    def open_amount_dialog(kind, custody=None):
        """kind: topup (تعزيز عهدة) | return (إرجاع جزء من الرصيد للخزينة بدون قفل العهدة)"""
        oc, opts = _open_custody_options()
        if not oc:
            snack('مفيش عهد مفتوحة'); return
        by_id = {str(c['id']): c for c in oc}
        titles = {'topup': 'تعزيز عهدة (سند صرف إضافي)', 'return': 'إرجاع جزء من العهدة للخزينة (سند إرجاع)'}
        cust_dd = theme.SearchableDropdown(label='العهدة *', width=440, options=opts, value=str(custody['id']) if custody else None)
        amount_f = ft.TextField(label='المبلغ *', width=160, keyboard_type=ft.KeyboardType.NUMBER)
        pm_dd, has_pm = pm_dropdown()
        pm_dd.label = 'طريقة الدفع (من أين يُصرف)' if kind == 'topup' else 'طريقة الدفع (إلى أين يرجع)'
        date_f = theme.DateField('التاريخ', page, width=170, value=datetime.date.today().strftime('%Y-%m-%d'))
        notes_f = ft.TextField(label='ملاحظات', width=440)
        hint = ft.Text('', size=12, color=theme.TEXT_MUTED)
        err = ft.Text('', color=theme.DANGER, visible=False, size=12)

        def on_pick(ev=None):
            c = by_id.get(cust_dd.value or '')
            if c and kind == 'return':
                hint.value = f"المتاح للإرجاع: {c['available']:,.2f} (الرصيد {c['balance']:,.2f} - المحجوز لمصروفات قيد المراجعة {c['pending']:,.2f})"
                if not amount_f.value:
                    amount_f.value = f"{c['available']:g}"
            elif c:
                hint.value = f"رصيد العهدة الحالي {c['balance']:,.2f}"
            page.update()

        def save(ev):
            try:
                if not cust_dd.value:
                    raise ValueError('اختر العهدة')
                pmid = int(pm_dd.value) if pm_dd.value else None
                fn = services.topup_custody if kind == 'topup' else services.return_custody_funds
                fn(int(cust_dd.value), _num(amount_f, 'المبلغ'), pmid, _d(date_f.value), notes_f.value)
                close_dlg(dlg); refresh_all(); snack('تم تسجيل السند والقيد')
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        cust_dd.on_change = on_pick
        on_pick()
        dlg = ft.AlertDialog(modal=True, title=ft.Text(titles[kind]),
            content=ft.Container(width=480, content=ft.Column([cust_dd.control, hint, ft.Row([amount_f, pm_dd], wrap=True, spacing=10), date_f.control, notes_f, err], tight=True, spacing=12)),
            actions=[ft.TextButton('إلغاء', on_click=lambda ev: close_dlg(dlg)),
                     ft.FilledButton('تأكيد', icon=ft.Icons.CHECK, bgcolor=theme.PRIMARY, on_click=save)])
        page.overlay.append(dlg); dlg.open = True; page.update()

    def open_settle(custody=None):
        """تسوية عهدة: مطابقة الوارد بالمصروف المعتمد + إرجاع المتبقي + قفل العهدة (بمستند تسوية)."""
        oc, opts = _open_custody_options()
        if not oc:
            snack('مفيش عهد مفتوحة للتسوية'); return
        by_id = {str(c['id']): c for c in oc}
        cust_dd = theme.SearchableDropdown(label='العهدة *', width=440, options=opts, value=str(custody['id']) if custody else None)
        summary = ft.Column(spacing=4, tight=True)
        pm_dd, has_pm = pm_dropdown(width=300)
        pm_dd.label = 'طريقة الدفع (إلى أين يرجع المتبقي)'
        date_f = theme.DateField('تاريخ التسوية', page, width=170, value=datetime.date.today().strftime('%Y-%m-%d'))
        notes_f = ft.TextField(label='ملاحظات التسوية', width=440)
        err = ft.Text('', color=theme.DANGER, visible=False, size=12)

        def line(label, value, color=None, bold=False):
            return ft.Row([ft.Text(label, size=13), ft.Container(expand=True), ft.Text(f'{value:,.2f}', size=13, color=color, weight=ft.FontWeight.BOLD if bold else None)])

        def on_pick(ev=None):
            c = by_id.get(cust_dd.value or '')
            summary.controls = []
            if c:
                summary.controls = [line('إجمالي الوارد (صرف + تعزيز)', c['funded']), line('المصروف المعتمد', c['spent'], theme.DANGER),
                                    line('مرتجع سابق', c['returned'], theme.TEXT_MUTED), ft.Divider(height=1),
                                    line('الرصيد المتبقي (هيرجع للخزينة)', c['balance'], theme.PRIMARY, True)]
                if c['pending'] > 0:
                    summary.controls.append(ft.Text(f"تنبيه: فيه مصروفات قيد المراجعة بـ {c['pending']:,.2f} ({c['pending_count']}) - لازم تتحسم قبل التسوية", size=12, color=theme.DANGER, weight=ft.FontWeight.BOLD))
                pm_dd.visible = c['balance'] > 0.001
            page.update()

        def save(ev):
            try:
                if not cust_dd.value:
                    raise ValueError('اختر العهدة')
                sid = services.settle_custody(int(cust_dd.value), int(pm_dd.value) if pm_dd.value else None, _d(date_f.value), notes_f.value)
                close_dlg(dlg); refresh_all()
                snack('تمت التسوية وقفل العهدة')
                print_settlement(sid)
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        cust_dd.on_change = on_pick
        on_pick()
        dlg = ft.AlertDialog(modal=True, title=ft.Text('تسوية عهدة'),
            content=ft.Container(width=480, content=ft.Column([
                ft.Text('التسوية بتطابق الوارد بالمصروفات المعتمدة، وبترجّع المتبقي للخزينة بقيد، وبتقفل العهدة، وبتطلع مستند تسوية للطباعة.', size=12, color=theme.TEXT_MUTED),
                cust_dd.control, theme.card(summary, padding=12), pm_dd, date_f.control, notes_f, err], tight=True, spacing=12, scroll=ft.ScrollMode.AUTO, height=520)),
            actions=[ft.TextButton('إلغاء', on_click=lambda ev: close_dlg(dlg)),
                     ft.FilledButton('تأكيد التسوية وقفل العهدة', icon=ft.Icons.TASK_ALT, bgcolor=theme.DANGER, on_click=save)])
        page.overlay.append(dlg); dlg.open = True; page.update()

    # ---------------------------------------------------------------- طباعة السندات
    def _out_dir():
        d = os.path.join(services.APP_DIR, 'exports')
        os.makedirs(d, exist_ok=True); return d

    def print_funding(funding_id):
        try:
            from ..report_export import export_voucher_pdf
            f = services.get_custody_funding_doc(funding_id)
            b = f['balances']
            is_return = f['kind'] == 'return'
            title = {'issue': 'سند صرف عهدة', 'topup': 'سند تعزيز عهدة', 'return': 'سند إرجاع عهدة'}[f['kind']]
            doc = {'title': title, 'number': f['number'], 'date': f['date'],
                   'fields': [('الموظف', f['employee_name']), ('رقم العهدة', f['custody_number']), ('الغرض', f['purpose'] or '-'),
                              ('المبلغ', f"{f['amount']:,.2f}"), ('طريقة الدفع', f['method']), ('الحساب', f['account']),
                              ('رقم القيد', f['journal_number'] or '-'), ('ملاحظات', f['notes'] or '-')],
                   'totals': [('رصيد العهدة الحالي', b.get('balance', 0.0))],
                   'signatures': (['المستلم' if not is_return else 'المُسلِّم (الموظف)', 'أمين الصندوق', 'المحاسب', 'المدير المالي'])}
            theme.open_or_download_file(page, export_voucher_pdf(doc, _out_dir(), 'custody_voucher'))
        except Exception as ex:
            snack(f'تعذر الطباعة: {ex}')

    def print_settlement(settlement_id):
        try:
            from ..report_export import export_voucher_pdf
            t = services.get_custody_settlement_doc(settlement_id)
            rows = [[e.date, e.number, services.CUSTODY_EXPENSE_TYPE_LABELS[e.expense_type],
                     (f'{e.supplier_name} - {e.description}'.strip(' -') if e.expense_type == 'invoice' else (e.description or '')),
                     e.invoice_number or '-', e.account.name if e.account else '', e.amount, e.tax_amount, e.total] for e in t['expenses']]
            doc = {'title': 'سند تسوية عهدة', 'number': t['number'], 'date': t['date'],
                   'fields': [('الموظف', t['employee_name']), ('رقم العهدة', t['custody_number']), ('الغرض', t['purpose'] or '-'), ('ملاحظات', t['notes'] or '-')],
                   'table': {'caption': 'المصروفات والفواتير المعتمدة على العهدة',
                             'headers': ['التاريخ', 'رقم', 'النوع', 'البيان / المورد', 'رقم الفاتورة', 'الحساب', 'قبل الضريبة', 'الضريبة', 'الإجمالي'], 'rows': rows,
                             'col_weights': [1.5, 1.55, 0.95, 2.0, 1.1, 1.35, 1.0, 0.85, 1.05]},
                   'totals': [('إجمالي الوارد (صرف + تعزيز)', t['funded']), ('إجمالي المصروف المعتمد', t['spent']), ('منها ضريبة مدخلات', t['tax_total']),
                              ('مرتجع سابق', t['returned_before']), ('المرتجع في التسوية', t['returned_now']), ('الرصيد بعد التسوية', 0.0)],
                   'signatures': ['الموظف', 'المحاسب', 'أمين الصندوق', 'المدير المالي']}
            theme.open_or_download_file(page, export_voucher_pdf(doc, _out_dir(), 'custody_settlement'))
        except Exception as ex:
            snack(f'تعذر الطباعة: {ex}')

    def open_statement(custody_id):
        st = services.custody_statement(custody_id)
        c, b = st['custody'], st['balances']
        def chip(label, value, color):
            return ft.Container(content=ft.Column([ft.Text(label, size=11, color=theme.TEXT_MUTED), ft.Text(f'{value:,.2f}', size=16, weight=ft.FontWeight.BOLD, color=color)],
                                                  spacing=0, tight=True), bgcolor=theme.PRIMARY_LIGHT, border_radius=10, padding=ft.Padding(left=14, right=14, top=8, bottom=8))
        rows = [ft.DataRow(cells=[ft.DataCell(ft.Text(r['date'].strftime('%Y-%m-%d'))), ft.DataCell(ft.Text(r['type'], weight=ft.FontWeight.BOLD)),
                                  ft.DataCell(ft.Text(r['description'] or '-', size=12)), ft.DataCell(ft.Text(r['ref'], size=12)), ft.DataCell(ft.Text(r['account'], size=12)),
                                  ft.DataCell(ft.Text(f"{r['incoming']:,.2f}" if r['incoming'] else '-', color=theme.SUCCESS)),
                                  ft.DataCell(ft.Text(f"{r['outgoing']:,.2f}" if r['outgoing'] else '-', color=theme.DANGER)),
                                  ft.DataCell(ft.Text(f"{r['balance']:,.2f}", weight=ft.FontWeight.BOLD))]) for r in st['rows']]
        tbl = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['التاريخ', 'النوع', 'البيان', 'المرجع', 'الحساب', 'وارد', 'منصرف', 'الرصيد']], rows=rows, heading_row_height=38)
        extra = []
        if st['pending']:
            extra.append(ft.Text(f"قيد المراجعة ({len(st['pending'])}): " + ' | '.join(f'{n} {t} {v:,.2f}' for n, d, t, v, _ in st['pending']), size=12, color=theme.WARNING))
        if st['rejected']:
            extra.append(ft.Text(f"مرفوضة ({len(st['rejected'])}): " + ' | '.join(f'{n} {t} {v:,.2f} ({note})' for n, d, t, v, note in st['rejected']), size=12, color=theme.DANGER))

        def export(kind):
            try:
                from ..report_export import export_pdf, export_excel
                data = {'custody': c, 'custody_rows': st['rows'], 'custody_balances': b, 'date_from': None, 'date_to': None}
                out_dir = os.path.join(services.APP_DIR, 'exports')
                os.makedirs(out_dir, exist_ok=True)
                path = (export_pdf if kind == 'pdf' else export_excel)(data, 'custody_statement', out_dir)
                theme.open_or_download_file(page, path); snack('تم إنشاء الملف')
            except Exception as ex:
                snack(f'تعذر التصدير: {ex}')

        sdlg = ft.AlertDialog(modal=True, title=ft.Text(f"كشف العهدة {c['number']} - {c['employee_name']}"),
            content=ft.Container(width=960, content=ft.Column([
                ft.Text(f"{c['purpose']}  |  بتاريخ {c['date']:%Y-%m-%d}  |  الحالة: {services.CUSTODY_STATE_LABELS[c['state']]}", size=12, color=theme.TEXT_MUTED),
                ft.Row([chip('إجمالي الوارد', b['funded'], theme.SUCCESS), chip('المصروف المعتمد', b['spent'], theme.DANGER), chip('المرتجع', b['returned'], theme.TEXT_MUTED),
                        chip('قيد المراجعة', b['pending'], theme.WARNING), chip('الرصيد', b['balance'], theme.PRIMARY)], wrap=True, spacing=10),
                theme.h_scroll(tbl), *extra], tight=True, spacing=10, scroll=ft.ScrollMode.AUTO, height=460)),
            actions=[ft.TextButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda ev: export('pdf')),
                     ft.TextButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda ev: export('excel')),
                     ft.TextButton('إغلاق', on_click=lambda ev: close_dlg(sdlg))])
        page.overlay.append(sdlg); sdlg.open = True; page.update()

    def show_overview():
        emp_filter = ft.Dropdown(label='الموظف', width=240, options=[ft.dropdown.Option('', 'كل الموظفين')] + [ft.dropdown.Option(str(x.id), x.name) for x in employees], value='')
        state_filter = ft.Dropdown(label='الحالة', width=160, options=[ft.dropdown.Option('', 'الكل'), ft.dropdown.Option('open', 'مفتوحة'), ft.dropdown.Option('closed', 'مقفولة')], value='')
        cards = ft.Row(wrap=True, spacing=12)
        STATE_COLORS = {'open': theme.SUCCESS, 'closed': theme.TEXT_MUTED}

        def print_issue_for(custody_id):
            f = [x for x in services.list_custody_fundings(kinds=('issue',), custody_id=custody_id)]
            if f:
                print_funding(f[-1]['id'])
            else:
                snack('مفيش سند صرف للعهدة دي')

        def print_settle_for(custody_id):
            t = [x for x in services.list_custody_settlements() if x['custody_id'] == custody_id]
            if t:
                print_settlement(t[0]['id'])
            else:
                snack('العهدة دي لسه ما اتسوّتش')

        def row_builder(c):
            # أزرار بأسماء واضحة (مش أيقونات بس) عشان الإجراءات تبان للمستخدم
            def tb(label, icon, handler, color=None):
                return ft.TextButton(label, icon=icon, on_click=handler, style=ft.ButtonStyle(color=color, padding=ft.Padding(left=6, right=6, top=2, bottom=2)))
            acts = [tb('كشف', ft.Icons.RECEIPT_LONG_OUTLINED, lambda e, i=c['id']: open_statement(i))]
            if c['state'] == 'open':
                acts += [tb('مصروف', ft.Icons.ADD_CARD_OUTLINED, lambda e, i=c['id']: open_expense(i), theme.PRIMARY),
                         tb('تعزيز', ft.Icons.ADD_CIRCLE_OUTLINE, lambda e, x=c: open_amount_dialog('topup', x), theme.SUCCESS),
                         tb('إرجاع', ft.Icons.UNDO, lambda e, x=c: open_amount_dialog('return', x), theme.WARNING),
                         tb('تسوية', ft.Icons.TASK_ALT, lambda e, x=c: open_settle(x), theme.DANGER),
                         tb('سند الصرف', ft.Icons.PRINT_OUTLINED, lambda e, i=c['id']: print_issue_for(i))]
            else:
                acts += [tb('سند التسوية', ft.Icons.PRINT_OUTLINED, lambda e, i=c['id']: print_settle_for(i)),
                         tb('سند الصرف', ft.Icons.PRINT_OUTLINED, lambda e, i=c['id']: print_issue_for(i))]
            return ft.DataRow(cells=[
                ft.DataCell(ft.Text(c['number'], weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(c['employee_name'])),
                ft.DataCell(ft.Text(c['date'].strftime('%Y-%m-%d'))), ft.DataCell(ft.Text(c['purpose'] or '-', size=12)),
                ft.DataCell(ft.Text(f"{c['funded']:,.2f}")), ft.DataCell(ft.Text(f"{c['spent']:,.2f}")), ft.DataCell(ft.Text(f"{c['returned']:,.2f}", color=theme.TEXT_MUTED)),
                ft.DataCell(ft.Text(f"{c['pending']:,.2f}" if c['pending'] else '-', color=theme.WARNING)),
                ft.DataCell(ft.Text(f"{c['balance']:,.2f}", weight=ft.FontWeight.BOLD, color=theme.PRIMARY)),
                ft.DataCell(ft.Text(services.CUSTODY_STATE_LABELS[c['state']], color=STATE_COLORS[c['state']], weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Row(acts, spacing=0))])

        table = theme.SortableDataTable(columns=[
            ('رقم العهدة', lambda c: c['number']), ('الموظف', lambda c: c['employee_name']), ('التاريخ', lambda c: c['date']), ('الغرض', lambda c: c['purpose']),
            ('الوارد', lambda c: c['funded'], True), ('المصروف', lambda c: c['spent'], True), ('المرتجع', lambda c: c['returned'], True),
            ('قيد المراجعة', lambda c: c['pending'], True), ('الرصيد', lambda c: c['balance'], True), ('الحالة', lambda c: c['state']), ('الإجراءات', None)],
            row_builder=row_builder, page=page)

        def refresh(e=None):
            data = services.list_custodies(int(emp_filter.value) if emp_filter.value else None, state_filter.value or None)
            table.set_data(data)
            open_rows = [c for c in data if c['state'] == 'open']
            def card(label, value, color, sub=''):
                return theme.stat_card(label, f'{value:,.2f}' if isinstance(value, float) else str(value), color, sub)
            cards.controls = [card('أرصدة العهد المفتوحة', float(sum(c['balance'] for c in open_rows)), theme.PRIMARY, f'{len(open_rows)} عهدة مفتوحة'),
                              card('مصروفات قيد المراجعة', float(sum(c['pending'] for c in data)), theme.WARNING, f"{sum(c['pending_count'] for c in data)} مصروف محتاج قرار"),
                              card('إجمالي المصروف المعتمد', float(sum(c['spent'] for c in data)), theme.DANGER)]
            page.update()

        emp_filter.on_change = refresh; state_filter.on_change = refresh
        refresh()
        return ft.Column([
            ft.Row([emp_filter, state_filter, ft.Container(expand=True),
                    ft.OutlinedButton('تسوية عهدة', icon=ft.Icons.TASK_ALT, on_click=lambda e: open_settle()),
                    ft.OutlinedButton('تقديم مصروف / فاتورة', icon=ft.Icons.ADD_CARD_OUTLINED, on_click=lambda e: open_expense()),
                    ft.FilledButton('صرف عهدة جديدة', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=open_create)], spacing=10),
            cards, theme.card(theme.h_scroll(table.control))], expand=True, spacing=12, scroll=ft.ScrollMode.AUTO)

    # ===================================================================== مصروف / فاتورة
    def open_expense(preselect_custody_id=None):
        open_c = services.list_custodies(state='open')
        if not open_c:
            snack('مفيش عهد مفتوحة - اصرف عهدة الأول'); return
        cust_dd = theme.SearchableDropdown(label='العهدة *', width=420,
                                           options=[(str(c['id']), f"{c['number']} - {c['employee_name']} (متاح {c['available']:,.2f})") for c in open_c],
                                           value=str(preselect_custody_id) if preselect_custody_id else None)
        type_rg = ft.RadioGroup(value='expense', content=ft.Row([ft.Radio(value='expense', label='مصروف'), ft.Radio(value='invoice', label='فاتورة مورد')], spacing=24))
        exp_accounts = [a for a in services.list_accounts(postable_only=True) if a.account_type == 'expense'] or services.list_accounts(postable_only=True)
        acc_dd = theme.SearchableDropdown(label='حساب المصروف *', width=420, options=[(str(a.id), f'{a.code} - {a.name}') for a in exp_accounts])
        date_f = theme.DateField('التاريخ', page, width=170, value=datetime.date.today().strftime('%Y-%m-%d'))
        desc_f = ft.TextField(label='البيان *', width=420)
        amount_f = ft.TextField(label='المبلغ *', width=170, keyboard_type=ft.KeyboardType.NUMBER)
        tax_f = ft.TextField(label='نسبة الضريبة %', width=130, value=f"{(cfg_company.default_tax_rate if cfg_company and cfg_company.default_tax_rate is not None else 15):g}", keyboard_type=ft.KeyboardType.NUMBER)
        total_t = ft.Text('', size=13, weight=ft.FontWeight.BOLD, color=theme.PRIMARY)
        suppliers = services.list_suppliers()
        sup_dd = theme.SearchableDropdown(label='المورد * (اكتب للبحث، أو أضف مورد جديد)', width=420, options=[(str(x.id), x.name) for x in suppliers],
                                          add_label='➕ إضافة مورد جديد:')

        def open_quick_supplier(typed_name):
            """إضافة مورد جديد من نفس حقل المورد: الاسم متعبّي من اللي كتبته، وبعد الحفظ بيتختار تلقائي."""
            n_f = ft.TextField(label='اسم المورد *', width=360, value=typed_name, autofocus=True)
            ph_f = ft.TextField(label='الهاتف', width=170)
            vat_f = ft.TextField(label='الرقم الضريبي', width=200, hint_text='15 رقم')
            qerr = ft.Text('', color=theme.DANGER, visible=False, size=12)

            def save_supplier(ev):
                try:
                    new_id = services.create_supplier(n_f.value, ph_f.value, vat_f.value)
                    sup_dd.options = [(str(x.id), x.name) for x in services.list_suppliers()]
                    sup_dd.value = str(new_id)
                    qdlg.open = False
                    snack(f'تم إضافة المورد "{(n_f.value or "").strip()}" واختياره')
                except Exception as ex:
                    qerr.value = str(ex); qerr.visible = True; page.update()

            qdlg = ft.AlertDialog(modal=True, title=ft.Text('إضافة مورد جديد'),
                content=ft.Container(width=400, content=ft.Column([n_f, ft.Row([ph_f, vat_f], wrap=True, spacing=10), qerr], tight=True, spacing=12)),
                actions=[ft.TextButton('إلغاء', on_click=lambda ev: (setattr(qdlg, 'open', False), page.update())),
                         ft.FilledButton('حفظ واختيار', icon=ft.Icons.CHECK, bgcolor=theme.PRIMARY, on_click=save_supplier)])
            page.overlay.append(qdlg); qdlg.open = True; page.update()

        sup_dd.on_add = open_quick_supplier
        inv_no_f = ft.TextField(label='رقم الفاتورة *', width=200)
        inv_date_f = theme.DateField('تاريخ الفاتورة', page, width=170, value=datetime.date.today().strftime('%Y-%m-%d'))
        attach = {'path': ''}
        attach_t = ft.Text('', size=12, color=theme.TEXT_MUTED)
        err = ft.Text('', color=theme.DANGER, visible=False, size=12)
        inv_box = ft.Column([sup_dd.control, ft.Row([inv_no_f, inv_date_f.control, tax_f], wrap=True, spacing=10)], spacing=10, visible=False)

        def recalc(ev=None):
            inv_box.visible = type_rg.value == 'invoice'
            amount_f.label = 'المبلغ قبل الضريبة *' if type_rg.value == 'invoice' else 'المبلغ *'
            try:
                a = float((amount_f.value or '').replace(',', '') or 0)
                t = round(a * float((tax_f.value or '0')) / 100.0, 2) if type_rg.value == 'invoice' else 0.0
                total_t.value = f'الضريبة {t:,.2f}  |  الإجمالي {a + t:,.2f}' if type_rg.value == 'invoice' else f'الإجمالي {a:,.2f}'
            except ValueError:
                total_t.value = ''
            page.update()

        async def pick(ev):
            path = await theme.pick_file(page, 'اختر صورة/ملف الفاتورة', ['pdf','png','jpg','jpeg'])
            if path:
                attach['path'] = path; attach_t.value = os.path.basename(path); page.update()

        def save(ev):
            try:
                if not cust_dd.value:
                    raise ValueError('اختر العهدة')
                eid = services.add_custody_expense(
                    int(cust_dd.value), type_rg.value, int(acc_dd.value) if acc_dd.value else None, _num(amount_f, 'المبلغ'), desc_f.value,
                    _d(date_f.value), _num(tax_f, 'نسبة الضريبة') if type_rg.value == 'invoice' else 0.0,
                    int(sup_dd.value) if sup_dd.value else None, '', inv_no_f.value, _d(inv_date_f.value) if type_rg.value == 'invoice' else None)
                if attach['path']:
                    services.attach_custody_expense_file(eid, attach['path'])
                close_dlg(dlg); refresh_all(); snack('تم تقديم المصروف للمراجعة')
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        type_rg.on_change = recalc; amount_f.on_change = recalc; tax_f.on_change = recalc
        recalc()
        dlg = ft.AlertDialog(modal=True, title=ft.Text('تقديم مصروف / فاتورة على عهدة'),
            content=ft.Container(width=480, content=ft.Column([
                ft.Text('المصروف بيدخل قيد المراجعة، والقيد المحاسبي بيتسجل لما المحاسب يعتمده.', size=12, color=theme.TEXT_MUTED),
                cust_dd.control, type_rg, acc_dd.control, ft.Row([date_f.control, amount_f], wrap=True, spacing=10), desc_f, inv_box, total_t,
                ft.Row([ft.OutlinedButton('إرفاق صورة الفاتورة', icon=ft.Icons.ATTACH_FILE, on_click=pick), attach_t], spacing=10), err],
                tight=True, spacing=10, scroll=ft.ScrollMode.AUTO, height=560)),
            actions=[ft.TextButton('إلغاء', on_click=lambda ev: close_dlg(dlg)),
                     ft.FilledButton('تقديم', icon=ft.Icons.SEND, bgcolor=theme.PRIMARY, on_click=save)])
        page.overlay.append(dlg); dlg.open = True; page.update()

    def open_reject(expense):
        note_f = ft.TextField(label='سبب الرفض *', width=380, multiline=True, min_lines=2, max_lines=3)
        err = ft.Text('', color=theme.DANGER, visible=False, size=12)
        def confirm(ev):
            try:
                services.decide_custody_expense(expense.id, False, note_f.value)
                close_dlg(rdlg); refresh_all(); snack('تم رفض المصروف')
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()
        rdlg = ft.AlertDialog(modal=True, title=ft.Text(f'رفض المصروف {expense.number}'), content=ft.Container(width=420, content=ft.Column([note_f, err], tight=True, spacing=10)),
                              actions=[ft.TextButton('إلغاء', on_click=lambda ev: close_dlg(rdlg)), ft.FilledButton('تأكيد الرفض', bgcolor=theme.DANGER, on_click=confirm)])
        page.overlay.append(rdlg); rdlg.open = True; page.update()

    def show_expenses():
        emp_filter = ft.Dropdown(label='الموظف', width=220, options=[ft.dropdown.Option('', 'كل الموظفين')] + [ft.dropdown.Option(str(x.id), x.name) for x in employees], value='')
        state_filter = ft.Dropdown(label='الحالة', width=170, options=[ft.dropdown.Option('', 'الكل')] + [ft.dropdown.Option(k, v) for k, v in services.CUSTODY_EXPENSE_STATE_LABELS.items()], value='pending')
        STATE_COLORS = {'pending': theme.WARNING, 'approved': theme.SUCCESS, 'rejected': theme.DANGER}

        def do_approve(ex):
            try:
                services.decide_custody_expense(ex.id, True); refresh_all(); snack(f'تم اعتماد {ex.number} وتسجيل القيد')
            except Exception as e2:
                snack(str(e2))

        def do_delete(ex):
            try:
                services.delete_custody_expense(ex.id); refresh_all()
            except Exception as e2:
                snack(str(e2))

        def row_builder(x):
            acts = []
            if x.state == 'pending':
                acts += [ft.IconButton(icon=ft.Icons.CHECK_CIRCLE_OUTLINE, icon_color=theme.SUCCESS, tooltip='اعتماد وتسجيل القيد', on_click=lambda e, y=x: do_approve(y)),
                         ft.IconButton(icon=ft.Icons.CANCEL_OUTLINED, icon_color=theme.DANGER, tooltip='رفض', on_click=lambda e, y=x: open_reject(y))]
            if x.state != 'approved':
                acts.append(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip='حذف', on_click=lambda e, y=x: do_delete(y)))
            acts.append(ft.IconButton(icon=ft.Icons.RECEIPT_LONG_OUTLINED, tooltip='كشف العهدة', on_click=lambda e, i=x.custody_id: open_statement(i)))
            if x.attachment_path and os.path.exists(x.attachment_path):
                acts.append(ft.IconButton(icon=ft.Icons.ATTACH_FILE, tooltip='فتح المرفق', icon_color=theme.PRIMARY, on_click=lambda e, p=x.attachment_path: theme.open_or_download_file(page, p)))
            what = x.description or '-'
            if x.expense_type == 'invoice':
                what = f"{x.supplier_name}" + (f" - {x.description}" if x.description else '')
            return ft.DataRow(cells=[
                ft.DataCell(ft.Text(x.number, weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(x.custody.number if x.custody else '-')),
                ft.DataCell(ft.Text(x.custody.employee.name if x.custody and x.custody.employee else '-')),
                ft.DataCell(ft.Text(services.CUSTODY_EXPENSE_TYPE_LABELS[x.expense_type], color=theme.PRIMARY if x.expense_type == 'invoice' else None)),
                ft.DataCell(ft.Text(x.date.strftime('%Y-%m-%d'))), ft.DataCell(ft.Text(what, size=12)), ft.DataCell(ft.Text(x.invoice_number or '-', size=12)),
                ft.DataCell(ft.Text(f'{x.account.code} - {x.account.name}' if x.account else '-', size=11)),
                ft.DataCell(ft.Text(f'{x.amount:,.2f}')), ft.DataCell(ft.Text(f'{x.tax_amount:,.2f}' if x.tax_amount else '-')),
                ft.DataCell(ft.Text(f'{x.total:,.2f}', weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Column([ft.Text(services.CUSTODY_EXPENSE_STATE_LABELS[x.state], color=STATE_COLORS[x.state], weight=ft.FontWeight.BOLD)]
                                      + ([ft.Text(x.decision_note, size=10, color=theme.TEXT_MUTED)] if x.state == 'rejected' and x.decision_note else []), spacing=0, tight=True)),
                ft.DataCell(ft.Row(acts, spacing=0))])

        table = theme.SortableDataTable(columns=[
            ('رقم', lambda x: x.number), ('العهدة', lambda x: x.custody.number if x.custody else ''), ('الموظف', lambda x: x.custody.employee.name if x.custody and x.custody.employee else ''),
            ('النوع', lambda x: x.expense_type), ('التاريخ', lambda x: x.date), ('البيان / المورد', lambda x: x.description), ('رقم الفاتورة', lambda x: x.invoice_number),
            ('الحساب', lambda x: x.account.code if x.account else ''), ('قبل الضريبة', lambda x: x.amount, True), ('الضريبة', lambda x: x.tax_amount, True),
            ('الإجمالي', lambda x: x.total, True), ('الحالة', lambda x: x.state), ('الإجراءات', None)], row_builder=row_builder, page=page)

        def refresh(e=None):
            table.set_data(services.list_custody_expenses(state=state_filter.value or None, employee_id=int(emp_filter.value) if emp_filter.value else None))
            page.update()

        emp_filter.on_change = refresh; state_filter.on_change = refresh
        refresh()
        return ft.Column([
            ft.Row([emp_filter, state_filter, ft.Container(expand=True),
                    ft.FilledButton('تقديم مصروف / فاتورة', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=lambda e: open_expense())], spacing=12),
            theme.card(theme.h_scroll(table.control))], expand=True, spacing=12, scroll=ft.ScrollMode.AUTO)

    # ===================================================================== صرف العهد
    def show_issues():
        emp_filter = ft.Dropdown(label='الموظف', width=220, options=[ft.dropdown.Option('', 'كل الموظفين')] + [ft.dropdown.Option(str(x.id), x.name) for x in employees], value='')
        kind_filter = ft.Dropdown(label='نوع السند', width=190, options=[ft.dropdown.Option('', 'الكل')] + [ft.dropdown.Option(k, v) for k, v in services.CUSTODY_FUNDING_LABELS.items()], value='')
        cards = ft.Row(wrap=True, spacing=12)
        KIND_COLORS = {'issue': theme.PRIMARY, 'topup': theme.SUCCESS, 'return': theme.WARNING}

        def row_builder(f):
            return ft.DataRow(cells=[
                ft.DataCell(ft.Text(f['number'], weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(f['kind_label'], color=KIND_COLORS[f['kind']], weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(f['date'].strftime('%Y-%m-%d'))), ft.DataCell(ft.Text(f['custody_number'])), ft.DataCell(ft.Text(f['employee_name'])),
                ft.DataCell(ft.Text(f['purpose'] or '-', size=12)), ft.DataCell(ft.Text(f"{f['amount']:,.2f}", weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(f['method'] or '-', size=12)), ft.DataCell(ft.Text(f['notes'] or '-', size=11, color=theme.TEXT_MUTED)),
                ft.DataCell(ft.Row([ft.IconButton(icon=ft.Icons.PRINT_OUTLINED, tooltip='طباعة السند', on_click=lambda e, i=f['id']: print_funding(i)),
                                    ft.IconButton(icon=ft.Icons.RECEIPT_LONG_OUTLINED, tooltip='كشف العهدة', on_click=lambda e, i=f['custody_id']: open_statement(i))], spacing=0))])

        table = theme.SortableDataTable(columns=[
            ('رقم السند', lambda f: f['number']), ('النوع', lambda f: f['kind']), ('التاريخ', lambda f: f['date']), ('العهدة', lambda f: f['custody_number']),
            ('الموظف', lambda f: f['employee_name']), ('الغرض', lambda f: f['purpose']), ('المبلغ', lambda f: f['amount'], True),
            ('طريقة الدفع', lambda f: f['method']), ('ملاحظات', None), ('', None)], row_builder=row_builder, page=page)

        def refresh(e=None):
            data = services.list_custody_fundings(kinds=(kind_filter.value,) if kind_filter.value else None, employee_id=int(emp_filter.value) if emp_filter.value else None)
            table.set_data(data)
            def card(label, value, color):
                return theme.stat_card(label, f'{value:,.2f}', color)
            issued = sum(x['amount'] for x in data if x['kind'] == 'issue'); topped = sum(x['amount'] for x in data if x['kind'] == 'topup'); ret = sum(x['amount'] for x in data if x['kind'] == 'return')
            cards.controls = [card('إجمالي العهد المصروفة', float(issued), theme.PRIMARY), card('إجمالي التعزيزات', float(topped), theme.SUCCESS), card('إجمالي المرتجع', float(ret), theme.WARNING)]
            page.update()

        emp_filter.on_change = refresh; kind_filter.on_change = refresh
        refresh()
        return ft.Column([
            ft.Row([emp_filter, kind_filter, ft.Container(expand=True),
                    ft.OutlinedButton('إرجاع جزء للخزينة', icon=ft.Icons.UNDO, on_click=lambda e: open_amount_dialog('return')),
                    ft.OutlinedButton('تعزيز عهدة', icon=ft.Icons.ADD_CIRCLE_OUTLINE, on_click=lambda e: open_amount_dialog('topup')),
                    ft.FilledButton('صرف عهدة جديدة', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=open_create)], spacing=10),
            cards, theme.card(theme.h_scroll(table.control))], expand=True, spacing=12, scroll=ft.ScrollMode.AUTO)

    # ===================================================================== تسوية العهد
    def show_settlements():
        emp_filter = ft.Dropdown(label='الموظف', width=240, options=[ft.dropdown.Option('', 'كل الموظفين')] + [ft.dropdown.Option(str(x.id), x.name) for x in employees], value='')
        open_note = ft.Container(visible=False, bgcolor=theme.WARNING_LIGHT, border_radius=10, padding=ft.Padding(left=14, right=14, top=10, bottom=10))

        def row_builder(t):
            return ft.DataRow(cells=[
                ft.DataCell(ft.Text(t['number'], weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(t['date'].strftime('%Y-%m-%d'))),
                ft.DataCell(ft.Text(t['custody_number'])), ft.DataCell(ft.Text(t['employee_name'])), ft.DataCell(ft.Text(t['purpose'] or '-', size=12)),
                ft.DataCell(ft.Text(f"{t['funded']:,.2f}")), ft.DataCell(ft.Text(f"{t['spent']:,.2f}", color=theme.DANGER)),
                ft.DataCell(ft.Text(f"{t['returned_total']:,.2f}", color=theme.SUCCESS)), ft.DataCell(ft.Text(t['notes'] or '-', size=11, color=theme.TEXT_MUTED)),
                ft.DataCell(ft.Row([ft.IconButton(icon=ft.Icons.PRINT_OUTLINED, tooltip='طباعة سند التسوية', on_click=lambda e, i=t['id']: print_settlement(i)),
                                    ft.IconButton(icon=ft.Icons.RECEIPT_LONG_OUTLINED, tooltip='كشف العهدة', on_click=lambda e, i=t['custody_id']: open_statement(i))], spacing=0))])

        table = theme.SortableDataTable(columns=[
            ('رقم التسوية', lambda t: t['number']), ('التاريخ', lambda t: t['date']), ('العهدة', lambda t: t['custody_number']), ('الموظف', lambda t: t['employee_name']),
            ('الغرض', lambda t: t['purpose']), ('الوارد', lambda t: t['funded'], True), ('المصروف المعتمد', lambda t: t['spent'], True),
            ('المرتجع للخزينة', lambda t: t['returned_total'], True), ('ملاحظات', None), ('', None)], row_builder=row_builder, page=page)

        def refresh(e=None):
            table.set_data(services.list_custody_settlements(int(emp_filter.value) if emp_filter.value else None))
            oc = services.list_custodies(state='open')
            if oc:
                open_note.content = ft.Column([ft.Row([ft.Icon(ft.Icons.PENDING_ACTIONS, color=theme.WARNING, size=18),
                                                       ft.Text(f'{len(oc)} عهدة مفتوحة لسه ما اتسوّتش', weight=ft.FontWeight.BOLD, color=theme.WARNING_TEXT)], spacing=6),
                                               ft.Text(' | '.join(f"{c['employee_name']}: رصيد {c['balance']:,.2f}" + (f" (قيد مراجعة {c['pending']:,.2f})" if c['pending'] else '') for c in oc[:6]) + (' ...' if len(oc) > 6 else ''), size=12, color=theme.WARNING_TEXT)],
                                              spacing=3, tight=True)
                open_note.visible = True
            else:
                open_note.visible = False
            page.update()

        emp_filter.on_change = refresh
        refresh()
        return ft.Column([
            ft.Row([emp_filter, ft.Container(expand=True), ft.FilledButton('تسوية عهدة', icon=ft.Icons.TASK_ALT, bgcolor=theme.PRIMARY, on_click=lambda e: open_settle())], spacing=10),
            open_note, theme.card(theme.h_scroll(table.control))], expand=True, spacing=12, scroll=ft.ScrollMode.AUTO)

    SECTIONS = {'overview': show_overview, 'issues': show_issues, 'expenses': show_expenses, 'settlements': show_settlements}
    TITLES = {
        'overview': ('أرصدة وكشوف العهد', 'متابعة رصيد كل عهدة وكشف حركتها، وتقديم مصروف أو فاتورة عليها'),
        'issues': ('صرف العهد', 'سندات صرف وتعزيز وإرجاع العهد - بقيد تلقائي وطباعة السند'),
        'expenses': ('مصروفات وفواتير العهد', 'تقديم المصروفات والفواتير على العهدة ثم اعتمادها بقيد تلقائي أو رفضها'),
        'settlements': ('تسوية العهد', 'مطابقة الوارد بالمصروفات المعتمدة وإرجاع المتبقي وقفل العهدة بمستند تسوية'),
    }
    theme.call_without_page_update(page, refresh_all)
    t, sub = TITLES[mode]
    return ft.Column([theme.page_title(t, sub), ft.Container(height=10), holder], expand=True)


def build_custody_issues(page: ft.Page):
    return build_employee_custody(page, 'issues')


def build_custody_expenses(page: ft.Page):
    return build_employee_custody(page, 'expenses')


def build_custody_settlements(page: ft.Page):
    return build_employee_custody(page, 'settlements')
