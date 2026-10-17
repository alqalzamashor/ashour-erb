import datetime
import flet as ft
from .. import services, theme

TYPE_LABELS = {'resignation': 'استقالة الموظف', 'termination': 'إنهاء خدمة من الشركة'}


def build_eos_settlements(page: ft.Page):
    """تسوية نهاية الخدمة: مكافأة (حسب نظام العمل السعودي) + رصيد الإجازة
    غير المستخدم، بمعاينة قبل الحفظ وترحيل بيقفل المخصصات المتراكمة."""
    employees = services.list_employees(active_only=False)
    emp_options = [(str(e.id), f'{e.code} - {e.name}' + ('' if e.is_active else ' (غير نشط)')) for e in employees]

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    emp_dd = theme.SearchableDropdown(label='الموظف *', width=280, options=emp_options)
    type_dd = ft.Dropdown(label='نوع إنهاء الخدمة', width=220, value='resignation', options=[
        ft.dropdown.Option(k, v) for k, v in TYPE_LABELS.items()])
    last_day_f = theme.DateField('آخر يوم عمل', page, width=150, value=datetime.date.today().strftime('%Y-%m-%d'))
    leave_days_f = ft.TextField(label='أيام الإجازة غير المستخدمة *', width=250, hint_text='يُجلب من رصيد الإجازة ويمكن تعديله')
    dues_f = ft.TextField(label='مستحقات أخرى', width=150, value='0', keyboard_type=ft.KeyboardType.NUMBER)
    dues_note_f = ft.TextField(label='بيان المستحقات', width=220)
    ded_f = ft.TextField(label='خصومات أخرى', width=150, value='0', keyboard_type=ft.KeyboardType.NUMBER)
    ded_note_f = ft.TextField(label='بيان الخصومات', width=220)
    notes_f = ft.TextField(label='ملاحظات', width=400)
    err = ft.Text('', color=theme.DANGER, visible=False)
    preview_col = ft.Column(spacing=4)

    def fill_balance(e=None):
        """يجيب رصيد الإجازة المتبقي للموظف ويحطه في الحقل."""
        leave_days_f.value = ''
        if emp_dd.value and last_day_f.value:
            try:
                d = datetime.datetime.strptime(last_day_f.value, '%Y-%m-%d')
                calc = services.calculate_eos_settlement(int(emp_dd.value), d, type_dd.value, None)
                leave_days_f.value = f"{calc['unused_leave_days']:g}"
            except Exception:
                pass
        do_preview()

    def do_preview(e=None):
        preview_col.controls = []
        if not emp_dd.value or not last_day_f.value:
            page.update(); return
        try:
            last_day = datetime.datetime.strptime(last_day_f.value, '%Y-%m-%d')
            days_override = float(leave_days_f.value) if (leave_days_f.value or '').strip() else None
            calc = services.calculate_eos_settlement(int(emp_dd.value), last_day, type_dd.value, days_override)
            dues = float(dues_f.value or 0); ded = float(ded_f.value or 0)
            total = round(calc['eos_gratuity'] + calc['leave_amount'] + dues - ded, 2)
            rows = [
                ('سنوات الخدمة', f"{calc['years_of_service']:g} سنة"),
                ('الأجر المحسوب عليه (إجمالي شهري)', f"{calc['monthly_wage']:,.2f}"),
                ('مكافأة نهاية الخدمة كاملة', f"{calc['eos_gross']:,.2f}"),
                ('نسبة الاستحقاق', f"{calc['eos_multiplier']*100:g}%" + (' (استقالة بأقل من سنتين = صفر)' if calc['eos_multiplier'] == 0 else '')),
                ('مكافأة نهاية الخدمة المستحقة', f"{calc['eos_gratuity']:,.2f}"),
                ('   منها متراكم من دورة المخصصات', f"{calc['eos_provisioned']:,.2f}"),
                ('رصيد الإجازة المرحّل من آخر تسوية' if calc['leave_from_settlement'] else 'رصيد الإجازة المرحّل', f"{calc['leave_opening']:g} يوم"),
                ('المستحق من ' + calc['leave_since'].strftime('%Y-%m-%d') + ' حتى آخر يوم عمل', f"{calc['leave_accrued']:g} يوم"),
                ('أيام الإجازة المستخدمة (معتمدة ومعلّقة)', f"{calc['leave_used']:g} يوم"),
                ('أيام الإجازة غير المستخدمة', f"{calc['unused_leave_days']:g} يوم × {calc['daily_rate']:,.2f}"),
                ('قيمة رصيد الإجازة', f"{calc['leave_amount']:,.2f}"),
                ('   منها متراكم من دورة المخصصات', f"{calc['leave_provisioned']:,.2f}"),
                ('مستحقات أخرى', f"{dues:,.2f}"), ('خصومات أخرى', f"{ded:,.2f}"),
            ]
            preview_col.controls = [ft.Row([ft.Text(k, color=theme.TEXT_MUTED, expand=True), ft.Text(v, weight=ft.FontWeight.BOLD)]) for k, v in rows]
            preview_col.controls.append(ft.Divider())
            preview_col.controls.append(ft.Row([ft.Text('الإجمالي المستحق للموظف', weight=ft.FontWeight.BOLD, size=16, expand=True),
                                                ft.Text(f'{total:,.2f}', weight=ft.FontWeight.BOLD, size=18, color=theme.PRIMARY)]))
            err.visible = False
        except Exception as ex:
            preview_col.controls = [ft.Text(str(ex), color=theme.DANGER)]
        page.update()

    for f in (emp_dd, type_dd, last_day_f):
        f.on_change = fill_balance
    for f in (leave_days_f, dues_f, ded_f):
        f.on_change = do_preview

    def submit(e):
        try:
            if not emp_dd.value:
                raise ValueError('اختر الموظف')
            last_day = datetime.datetime.strptime(last_day_f.value, '%Y-%m-%d')
            if not (leave_days_f.value or '').strip():
                raise ValueError('أيام الإجازة غير المستخدمة مطلوبة (تُجلب من رصيد الإجازة)')
            days_override = float(leave_days_f.value)
            if days_override < 0:
                raise ValueError('أيام الإجازة لا يمكن أن تكون سالبة')
            services.create_eos_settlement(
                int(emp_dd.value), last_day, type_dd.value, days_override,
                other_dues=float(dues_f.value or 0), other_dues_note=dues_note_f.value or '',
                other_deductions=float(ded_f.value or 0), other_deductions_note=ded_note_f.value or '',
                notes=notes_f.value or '',
            )
            leave_days_f.value = ''; dues_f.value = '0'; dues_note_f.value = ''; ded_f.value = '0'; ded_note_f.value = ''; notes_f.value = ''
            err.visible = False
            snack('تم حفظ التسوية كمسودة'); refresh()
        except Exception as ex:
            err.value = str(ex); err.visible = True; page.update()

    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in
                                  ['الرقم', 'الموظف', 'النوع', 'آخر يوم عمل', 'المكافأة', 'الإجازة', 'الإجمالي', 'الحالة', '']], rows=[])
    state_filter = ft.Dropdown(label='الحالة', width=150, value='', options=[
        ft.dropdown.Option('', 'الكل'), ft.dropdown.Option('draft', 'مسودة'), ft.dropdown.Option('posted', 'مرحّلة')])

    def open_post_dialog(sid):
        st = services.get_eos_settlement(sid)
        accounts = services.list_accounts(postable_only=True)
        acct_dd = theme.SearchableDropdown(label='يُصرف الآن من حساب (نقدي/بنك) - أو سيبه فاضي ليُسجّل كمستحق', width=380,
                                           options=[(str(a.id), f'{a.code} - {a.name}') for a in accounts])
        derr = ft.Text('', color=theme.DANGER, visible=False)

        def do_post(ev):
            try:
                services.post_eos_settlement(sid, pay_now_account_id=int(acct_dd.value) if acct_dd.value else None)
                dlg.open = False; page.update()
                snack('تم ترحيل التسوية بنجاح'); refresh()
            except Exception as ex:
                derr.value = str(ex); derr.visible = True; page.update()

        dlg = ft.AlertDialog(modal=True, title=ft.Text(f'ترحيل التسوية {st.number}'),
                             content=ft.Column([
                                 ft.Text(f'الإجمالي المستحق: {st.total_amount:,.2f}', weight=ft.FontWeight.BOLD, size=16),
                                 acct_dd.control, derr,
                             ], tight=True, spacing=10, width=420),
                             actions=[ft.TextButton('تراجع', on_click=lambda ev: (setattr(dlg, 'open', False), page.update())),
                                      ft.FilledButton('ترحيل', bgcolor=theme.PRIMARY, on_click=do_post)])
        page.overlay.append(dlg); dlg.open = True; page.update()

    def delete_settlement(sid):
        try:
            services.delete_eos_settlement(sid); refresh()
        except Exception as ex:
            snack(str(ex))

    def refresh(e=None):
        rows = []
        for st in services.list_eos_settlements():
            if state_filter.value and st.state != state_filter.value:
                continue
            actions = ft.Row(spacing=0)
            if st.state == 'draft':
                actions.controls.append(ft.IconButton(icon=ft.Icons.CHECK_CIRCLE_OUTLINE, icon_color=theme.SUCCESS, tooltip='ترحيل', on_click=lambda e, sid=st.id: open_post_dialog(sid)))
                actions.controls.append(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف', on_click=lambda e, sid=st.id: delete_settlement(sid)))
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(st.number)), ft.DataCell(ft.Text(st.employee.name if st.employee else '-')),
                ft.DataCell(ft.Text(TYPE_LABELS.get(st.termination_type, st.termination_type))),
                ft.DataCell(ft.Text(st.last_working_date.strftime('%Y-%m-%d'))),
                ft.DataCell(ft.Text(f'{st.eos_gratuity:,.2f}')), ft.DataCell(ft.Text(f'{st.leave_amount:,.2f}')),
                ft.DataCell(ft.Text(f'{st.total_amount:,.2f}', weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text('مرحّلة' if st.state == 'posted' else 'مسودة', color=theme.SUCCESS if st.state == 'posted' else theme.WARNING, weight=ft.FontWeight.BOLD)),
                ft.DataCell(actions),
            ]))
        table.rows = rows; page.update()

    state_filter.on_change = refresh
    refresh()

    return ft.Column([
        theme.page_title('تسويات نهاية الخدمة', 'مكافأة نهاية الخدمة (نظام العمل السعودي) ورصيد الإجازة غير المستخدم - بقيد يقفل المخصصات المتراكمة'),
        ft.Container(height=12),
        theme.card(ft.Column([
            ft.Text('تسوية جديدة', size=16, weight=ft.FontWeight.BOLD),
            ft.Text('المكافأة بتتحسب حسب نظام العمل السعودي: نص شهر عن كل سنة من أول 5 سنين، وشهر كامل عن كل سنة بعد كده. '
                    'الاستقالة بأقل من سنتين = بدون مكافأة، من 2-5 سنين = الثلث، من 5-10 = الثلثين، 10 فأكثر = كامل المكافأة. '
                    'إنهاء الخدمة من الشركة = كامل المكافأة دايمًا.', color=theme.TEXT_MUTED, size=12),
            ft.Row([emp_dd.control, type_dd, last_day_f.control, leave_days_f], wrap=True, spacing=12),
            ft.Row([dues_f, dues_note_f, ded_f, ded_note_f], wrap=True, spacing=12),
            notes_f, err,
            theme.card(ft.Column([ft.Text('المعاينة', size=14, weight=ft.FontWeight.BOLD), preview_col], spacing=8)),
            theme.guard_submit(ft.FilledButton('حفظ التسوية كمسودة', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=submit)),
        ], spacing=10)),
        ft.Container(height=16),
        theme.card(ft.Column([ft.Row([ft.Text('كل التسويات', size=16, weight=ft.FontWeight.BOLD), ft.Container(expand=True), state_filter]), theme.h_scroll(table)])),
    ], expand=True, scroll=ft.ScrollMode.AUTO)
