import datetime
import flet as ft
from .. import services, theme


def build_annual_leave_settlements(page: ft.Page):
    """تسوية دورية لرصيد الإجازة السنوية: تاريخ التعيين وتاريخ آخر إجازة
    مسجّلين تلقائيًا، والمستحق بيتحسب بالتناسب الزمني من تاريخ التعيين
    (أو آخر تسوية سابقة) لحد تاريخ التسوية."""
    employees = services.list_employees(active_only=False)
    emp_options = [(str(e.id), f'{e.code} - {e.name}' + ('' if e.is_active else ' (غير نشط)')) for e in employees]

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def fmt_date(d):
        return d.strftime('%Y-%m-%d') if d else '-'

    emp_dd = theme.SearchableDropdown(label='الموظف *', width=280, options=emp_options)
    settle_date_f = theme.DateField('تاريخ التسوية', page, width=150, value=datetime.date.today().strftime('%Y-%m-%d'))
    encash_f = ft.TextField(label='أيام استبدال نقدي (اختياري)', width=220, hint_text='فاضي = 0 (يترحّل الرصيد كامل)')
    notes_f = ft.TextField(label='ملاحظات', width=400)
    err = ft.Text('', color=theme.DANGER, visible=False)
    preview_col = ft.Column(spacing=4)

    def do_preview(e=None):
        preview_col.controls = []
        if not emp_dd.value or not settle_date_f.value:
            page.update(); return
        try:
            settle_date = datetime.datetime.strptime(settle_date_f.value, '%Y-%m-%d')
            calc = services.calculate_annual_leave_settlement(int(emp_dd.value), settle_date)
            encash = float(encash_f.value) if (encash_f.value or '').strip() else 0.0
            closing = round(calc['closing_balance_before_encash'] - encash, 2)
            encash_amount = round(encash * calc['daily_rate'], 2)
            rows = [
                ('تاريخ التعيين', fmt_date(calc['hire_date'])),
                ('تاريخ آخر إجازة', fmt_date(calc['last_leave_date']) if calc['last_leave_date'] else 'لم يأخذ إجازة بعد'),
                ('من تاريخ (بداية الفترة)', fmt_date(calc['period_start']) + (' - أول تسوية' if calc['is_first_settlement'] else ' - آخر تسوية سابقة')),
                ('إلى تاريخ (تاريخ التسوية)', fmt_date(calc['settlement_date'])),
                ('عدد أيام الفترة', f"{calc['service_days']} يوم"),
                ('الرصيد الافتتاحي (من التسوية السابقة)', f"{calc['opening_balance']:g} يوم"),
                ('المستحق خلال الفترة (بالتناسب)', f"{calc['accrued_days']:g} يوم (من أصل {calc['allowance_per_year']:g} يوم/سنة)"),
                ('المستخدم خلال الفترة (إجازات معتمدة)', f"{calc['used_days']:g} يوم"),
                ('الرصيد قبل الاستبدال النقدي', f"{calc['closing_balance_before_encash']:g} يوم"),
                ('استبدال نقدي', f"{encash:g} يوم × {calc['daily_rate']:,.2f} = {encash_amount:,.2f}"),
            ]
            preview_col.controls = [ft.Row([ft.Text(k, color=theme.TEXT_MUTED, expand=True), ft.Text(v, weight=ft.FontWeight.BOLD)]) for k, v in rows]
            preview_col.controls.append(ft.Divider())
            preview_col.controls.append(ft.Row([ft.Text('الرصيد الختامي (يترحّل كافتتاحي للتسوية الجاية)', weight=ft.FontWeight.BOLD, size=15, expand=True),
                                                ft.Text(f'{closing:g} يوم', weight=ft.FontWeight.BOLD, size=17, color=theme.PRIMARY)]))
            err.visible = False
        except Exception as ex:
            preview_col.controls = [ft.Text(str(ex), color=theme.DANGER)]
        page.update()

    for f in (emp_dd, settle_date_f, encash_f):
        f.on_change = do_preview

    def submit(e):
        try:
            if not emp_dd.value:
                raise ValueError('اختر الموظف')
            settle_date = datetime.datetime.strptime(settle_date_f.value, '%Y-%m-%d')
            encash = float(encash_f.value) if (encash_f.value or '').strip() else 0.0
            services.create_annual_leave_settlement(int(emp_dd.value), settle_date, encashed_days=encash, notes=notes_f.value or '')
            encash_f.value = ''; notes_f.value = ''
            err.visible = False
            snack('تم حفظ التسوية كمسودة'); refresh()
        except Exception as ex:
            err.value = str(ex); err.visible = True; page.update()

    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in
                                  ['الرقم', 'الموظف', 'تاريخ التعيين', 'تاريخ آخر إجازة', 'من', 'إلى', 'افتتاحي', 'مستحق', 'مستخدم', 'ختامي', 'استبدال', 'الحالة', '']], rows=[])
    state_filter = ft.Dropdown(label='الحالة', width=150, value='', options=[
        ft.dropdown.Option('', 'الكل'), ft.dropdown.Option('draft', 'مسودة'), ft.dropdown.Option('posted', 'مرحّلة')])

    def open_post_dialog(sid):
        st = services.get_annual_leave_settlement(sid)
        accounts = services.list_accounts(postable_only=True)
        acct_dd = theme.SearchableDropdown(label='حساب الصرف (نقدي/بنك) - لازم لو فيه استبدال نقدي', width=380,
                                           options=[(str(a.id), f'{a.code} - {a.name}') for a in accounts])
        derr = ft.Text('', color=theme.DANGER, visible=False)

        def do_post(ev):
            try:
                services.post_annual_leave_settlement(sid, cash_account_id=int(acct_dd.value) if acct_dd.value else None)
                dlg.open = False; page.update()
                snack('تم ترحيل التسوية بنجاح'); refresh()
            except Exception as ex:
                derr.value = str(ex); derr.visible = True; page.update()

        content = [ft.Text(f'الرصيد الختامي: {st.closing_balance:g} يوم', weight=ft.FontWeight.BOLD, size=16)]
        if st.encashed_days:
            content.append(ft.Text(f'استبدال نقدي: {st.encashed_days:g} يوم = {st.encashed_amount:,.2f} - محتاج حساب صرف', color=theme.WARNING))
            content.append(acct_dd.control)
        else:
            content.append(ft.Text('مفيش استبدال نقدي - هيترحّل توثيق رصيد بس من غير قيد محاسبي.', color=theme.TEXT_MUTED, size=12))
        content.append(derr)

        dlg = ft.AlertDialog(modal=True, title=ft.Text(f'ترحيل التسوية {st.number}'),
                             content=ft.Column(content, tight=True, spacing=10, width=420),
                             actions=[ft.TextButton('تراجع', on_click=lambda ev: (setattr(dlg, 'open', False), page.update())),
                                      ft.FilledButton('ترحيل', bgcolor=theme.PRIMARY, on_click=do_post)])
        page.overlay.append(dlg); dlg.open = True; page.update()

    def delete_settlement(sid):
        try:
            services.delete_annual_leave_settlement(sid); refresh()
        except Exception as ex:
            snack(str(ex))

    def refresh(e=None):
        rows = []
        for st in services.list_annual_leave_settlements():
            if state_filter.value and st.state != state_filter.value:
                continue
            actions = ft.Row(spacing=0)
            if st.state == 'draft':
                actions.controls.append(ft.IconButton(icon=ft.Icons.CHECK_CIRCLE_OUTLINE, icon_color=theme.SUCCESS, tooltip='ترحيل', on_click=lambda e, sid=st.id: open_post_dialog(sid)))
                actions.controls.append(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف', on_click=lambda e, sid=st.id: delete_settlement(sid)))
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(st.number)), ft.DataCell(ft.Text(st.employee.name if st.employee else '-')),
                ft.DataCell(ft.Text(fmt_date(st.hire_date))), ft.DataCell(ft.Text(fmt_date(st.last_leave_date))),
                ft.DataCell(ft.Text(fmt_date(st.period_start))), ft.DataCell(ft.Text(fmt_date(st.settlement_date))),
                ft.DataCell(ft.Text(f'{st.opening_balance:g}')), ft.DataCell(ft.Text(f'{st.accrued_days:g}')),
                ft.DataCell(ft.Text(f'{st.used_days:g}')), ft.DataCell(ft.Text(f'{st.closing_balance:g}', weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(f'{st.encashed_days:g}' if st.encashed_days else '-')),
                ft.DataCell(ft.Text('مرحّلة' if st.state == 'posted' else 'مسودة', color=theme.SUCCESS if st.state == 'posted' else theme.WARNING, weight=ft.FontWeight.BOLD)),
                ft.DataCell(actions),
            ]))
        table.rows = rows; page.update()

    state_filter.on_change = refresh
    refresh()

    return ft.Column([
        theme.page_title('تسويات الإجازة السنوية', 'تسوية دورية لرصيد كل موظف - تاريخ التعيين وتاريخ آخر إجازة، والمستحق بالتناسب الزمني'),
        ft.Container(height=12),
        theme.card(ft.Column([
            ft.Text('تسوية جديدة', size=16, weight=ft.FontWeight.BOLD),
            ft.Text('المستحق بيتحسب من تاريخ التعيين (أول تسوية) أو من تاريخ آخر تسوية مرحّلة (بعد كده)، بالتناسب الزمني مع رصيد الإجازة '
                    'السنوية المحدد في الإعدادات. الرصيد الختامي بيترحّل تلقائيًا كافتتاحي للتسوية الجاية.', color=theme.TEXT_MUTED, size=12),
            ft.Row([emp_dd.control, settle_date_f.control, encash_f], wrap=True, spacing=12),
            notes_f, err,
            theme.card(ft.Column([ft.Text('المعاينة', size=14, weight=ft.FontWeight.BOLD), preview_col], spacing=8)),
            theme.guard_submit(ft.FilledButton('حفظ التسوية كمسودة', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=submit)),
        ], spacing=10)),
        ft.Container(height=16),
        theme.card(ft.Column([ft.Row([ft.Text('كل التسويات', size=16, weight=ft.FontWeight.BOLD), ft.Container(expand=True), state_filter]), theme.h_scroll(table)])),
    ], expand=True, scroll=ft.ScrollMode.AUTO)
