import datetime
import flet as ft
from .. import services, theme

STATE_COLORS = {'pending': theme.WARNING, 'approved': theme.SUCCESS, 'rejected': theme.DANGER, 'cancelled': theme.TEXT_MUTED}


def build_leave_requests(page: ft.Page):
    """طلبات الموظفين: إجازات (سنوية/مرضية/بدون راتب) + استئذان + استقالة
    ونهاية خدمة - كل نوع بدورة طلب/اعتماد أو رفض مستقلة."""
    tabs = theme.SimpleTabs(page)
    employees = services.list_employees()
    emp_options = [(str(e.id), f'{e.code} - {e.name}') for e in employees]

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def state_text(state):
        return ft.Text(services.REQUEST_STATE_LABELS.get(state, state), color=STATE_COLORS.get(state), weight=ft.FontWeight.BOLD)

    def refresh_all():
        tabs.set_tabs([('الإجازات', leaves_tab()), ('أنواع الإجازات', leave_types_tab()), ('الاستئذان', permissions_tab()), ('الاستقالة ونهاية الخدمة', resignations_tab())],
                      selected_index=tabs.selected_index)
        page.update()

    def deduct_text(t):
        if (t.deduct_percent or 0) <= 0:
            return 'مدفوعة بالكامل (من غير خصم من الراتب)'
        if t.deduct_percent >= 100:
            return 'بدون راتب: بيتخصم أجر اليوم كامل عن كل يوم'
        return f'بيتخصم {t.deduct_percent:g}% من أجر اليوم عن كل يوم'

    # ============================================================ أنواع الإجازات
    def leave_types_tab():
        edit_id = {'v': None}
        name_f = ft.TextField(label='اسم النوع *', width=240)
        pct_f = ft.TextField(label='نسبة الخصم من الراتب % (0 مدفوعة، 100 بدون راتب)', width=330, value='0', keyboard_type=ft.KeyboardType.NUMBER)
        max_f = ft.TextField(label='أقصى أيام في السنة (0 بدون حد)', width=240, value='0', keyboard_type=ft.KeyboardType.NUMBER)
        bal_cb = ft.Checkbox(label='تخصم من رصيد الإجازة السنوية', value=False)
        act_cb = ft.Checkbox(label='مفعّل', value=True)
        notes_f = ft.TextField(label='ملاحظات (اختياري)', width=300)
        err = ft.Text('', color=theme.DANGER, visible=False)
        title = ft.Text('نوع إجازة جديد', size=16, weight=ft.FontWeight.BOLD)
        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['النوع', 'الراتب', 'من الرصيد السنوي', 'الحد السنوي', 'الحالة', '']], rows=[])

        def reset():
            edit_id['v'] = None; name_f.value = ''; pct_f.value = '0'; max_f.value = '0'; bal_cb.value = False; act_cb.value = True; notes_f.value = ''
            title.value = 'نوع إجازة جديد'; err.visible = False

        def save(e):
            try:
                services.save_leave_type(edit_id['v'], name_f.value, pct_f.value, bal_cb.value, max_f.value, act_cb.value, notes_f.value or '')
                snack('تم حفظ نوع الإجازة'); reset(); refresh_all()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        def edit(t):
            edit_id['v'] = t.id; name_f.value = t.name; pct_f.value = f'{t.deduct_percent or 0:g}'; max_f.value = str(t.max_days_per_year or 0)
            bal_cb.value = bool(t.uses_annual_balance); act_cb.value = bool(t.is_active); notes_f.value = t.notes or ''
            title.value = f'تعديل: {t.name}'; err.visible = False; page.update()

        def delete(t):
            try:
                services.delete_leave_type(t.id); snack('تم الحذف'); refresh_all()
            except Exception as ex:
                snack(str(ex))

        rows = []
        for t in services.list_leave_types():
            btns = [ft.IconButton(icon=ft.Icons.EDIT, tooltip='تعديل', on_click=lambda e, t=t: edit(t))]
            if not t.is_system:
                btns.append(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف', on_click=lambda e, t=t: delete(t)))
            pay = 'مدفوعة' if (t.deduct_percent or 0) <= 0 else ('بدون راتب' if t.deduct_percent >= 100 else f'خصم {t.deduct_percent:g}%')
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(t.name, weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(pay, color=theme.DANGER if (t.deduct_percent or 0) > 0 else theme.SUCCESS)),
                ft.DataCell(ft.Text('نعم' if t.uses_annual_balance else 'لا')),
                ft.DataCell(ft.Text(str(t.max_days_per_year) if t.max_days_per_year else '-')),
                ft.DataCell(ft.Text('مفعّل' if t.is_active else 'موقوف', color=theme.SUCCESS if t.is_active else theme.TEXT_MUTED)),
                ft.DataCell(ft.Row(btns, spacing=0))]))
        table.rows = rows
        return ft.Column([
            theme.card(ft.Column([
                title,
                ft.Text('الخصم بيتحسب أوتوماتيك في دورة الرواتب من الإجازات المعتمدة: عدد الأيام × النسبة × أجر اليوم (الإجمالي ÷ 30).', color=theme.TEXT_MUTED, size=12),
                ft.Row([name_f, pct_f, max_f], wrap=True, spacing=12),
                ft.Row([bal_cb, act_cb, notes_f], wrap=True, spacing=12),
                err,
                ft.Row([ft.FilledButton('حفظ', icon=ft.Icons.SAVE, bgcolor=theme.PRIMARY, on_click=save),
                        ft.TextButton('جديد', on_click=lambda e: (reset(), page.update()))]),
            ], spacing=10)),
            ft.Container(height=12),
            theme.card(ft.Column([ft.Text('أنواع الإجازات', size=16, weight=ft.FontWeight.BOLD), theme.h_scroll(table)])),
        ], expand=True, scroll=ft.ScrollMode.AUTO)

    # ============================================================ الإجازات
    def leaves_tab():
        emp_dd = theme.SearchableDropdown(label='الموظف *', width=260, options=emp_options)
        all_types = {t.code: t for t in services.list_leave_types()}
        type_dd = ft.Dropdown(label='نوع الإجازة', width=200, value='annual', options=[
            ft.dropdown.Option(t.code, t.name) for t in all_types.values() if t.is_active])
        start_f = theme.DateField('من تاريخ', page, width=150, value=datetime.date.today().strftime('%Y-%m-%d'))
        end_f = theme.DateField('إلى تاريخ', page, width=150, value=datetime.date.today().strftime('%Y-%m-%d'))
        reason_f = ft.TextField(label='السبب (اختياري)', width=280)
        err = ft.Text('', color=theme.DANGER, visible=False)
        balance_txt = ft.Text('', size=12, color=theme.TEXT_MUTED)

        def show_balance(e=None):
            t = all_types.get(type_dd.value)
            if emp_dd.value and t and t.uses_annual_balance:
                b = services.annual_leave_balance(int(emp_dd.value))
                balance_txt.value = f"رصيد {b['year']}: المستحق {b['allowance']} - المستخدم {b['used']} - معلّق {b['pending']} = المتاح {b['remaining']} يوم"
            elif t:
                balance_txt.value = deduct_text(t)
            else:
                balance_txt.value = ''
            page.update()

        emp_dd.on_change = show_balance
        type_dd.on_change = show_balance

        def submit(e):
            try:
                if not emp_dd.value:
                    raise ValueError('اختر الموظف')
                sd = datetime.datetime.strptime(start_f.value, '%Y-%m-%d')
                ed = datetime.datetime.strptime(end_f.value, '%Y-%m-%d')
                services.create_leave_request(int(emp_dd.value), type_dd.value, sd, ed, reason_f.value or '')
                reason_f.value = ''; err.visible = False
                snack('تم تقديم طلب الإجازة'); refresh_all()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        state_filter = ft.Dropdown(label='الحالة', width=160, value='', options=[ft.dropdown.Option('', 'الكل')] + [
            ft.dropdown.Option(k, v) for k, v in services.REQUEST_STATE_LABELS.items()])
        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in
                                      ['الرقم', 'الموظف', 'النوع', 'من', 'إلى', 'أيام', 'الحالة', '']], rows=[])

        def fill(e=None):
            rows = []
            for r in services.list_leave_requests(state=state_filter.value or None):
                actions = ft.Row(spacing=0)
                if r.state == 'pending':
                    actions.controls.append(ft.IconButton(icon=ft.Icons.CHECK_CIRCLE_OUTLINE, icon_color=theme.SUCCESS, tooltip='اعتماد', on_click=lambda e, rid=r.id: decide(rid, True)))
                    actions.controls.append(ft.IconButton(icon=ft.Icons.CANCEL_OUTLINED, icon_color=theme.DANGER, tooltip='رفض', on_click=lambda e, rid=r.id: decide(rid, False)))
                if r.state in ('pending', 'approved'):
                    actions.controls.append(ft.IconButton(icon=ft.Icons.UNDO, tooltip='إلغاء الطلب', on_click=lambda e, rid=r.id: cancel(rid)))
                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(r.number)), ft.DataCell(ft.Text(r.employee.name if r.employee else '-')),
                    ft.DataCell(ft.Text(all_types[r.leave_type].name if r.leave_type in all_types else r.leave_type)),
                    ft.DataCell(ft.Text(r.start_date.strftime('%Y-%m-%d'))), ft.DataCell(ft.Text(r.end_date.strftime('%Y-%m-%d'))),
                    ft.DataCell(ft.Text(str(r.days))), ft.DataCell(state_text(r.state)), ft.DataCell(actions),
                ]))
            table.rows = rows; page.update()

        def decide(rid, approve):
            try:
                services.decide_leave_request(rid, approve); fill()
            except Exception as ex:
                snack(str(ex))

        def cancel(rid):
            try:
                services.cancel_leave_request(rid); fill()
            except Exception as ex:
                snack(str(ex))

        state_filter.on_change = fill
        fill()
        return ft.Column([
            theme.card(ft.Column([
                ft.Text('طلب إجازة جديد', size=16, weight=ft.FontWeight.BOLD),
                ft.Row([emp_dd.control, type_dd, start_f.control, end_f.control, reason_f], wrap=True, spacing=12),
                balance_txt, err,
                ft.FilledButton('تقديم الطلب', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=submit),
            ], spacing=10)),
            ft.Container(height=12),
            theme.card(ft.Column([ft.Row([ft.Text('كل طلبات الإجازات', size=16, weight=ft.FontWeight.BOLD), ft.Container(expand=True), state_filter]), theme.h_scroll(table)])),
        ], expand=True, scroll=ft.ScrollMode.AUTO)

    # ============================================================ الاستئذان
    def permissions_tab():
        emp_dd = theme.SearchableDropdown(label='الموظف *', width=260, options=emp_options)
        date_f = theme.DateField('التاريخ', page, width=150, value=datetime.date.today().strftime('%Y-%m-%d'))
        from_f = ft.TextField(label='من الساعة (HH:MM)', width=160, hint_text='09:00')
        to_f = ft.TextField(label='إلى الساعة (HH:MM)', width=160, hint_text='11:00')
        reason_f = ft.TextField(label='السبب (اختياري)', width=280)
        err = ft.Text('', color=theme.DANGER, visible=False)

        def submit(e):
            try:
                if not emp_dd.value:
                    raise ValueError('اختر الموظف')
                d = datetime.datetime.strptime(date_f.value, '%Y-%m-%d')
                services.create_permission_request(int(emp_dd.value), d, from_f.value, to_f.value, reason_f.value or '')
                from_f.value = ''; to_f.value = ''; reason_f.value = ''; err.visible = False
                snack('تم تقديم طلب الاستئذان'); refresh_all()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        state_filter = ft.Dropdown(label='الحالة', width=160, value='', options=[ft.dropdown.Option('', 'الكل')] + [
            ft.dropdown.Option(k, v) for k, v in services.REQUEST_STATE_LABELS.items()])
        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in
                                      ['الرقم', 'الموظف', 'التاريخ', 'من', 'إلى', 'ساعات', 'الحالة', '']], rows=[])

        def fill(e=None):
            rows = []
            for r in services.list_permission_requests(state=state_filter.value or None):
                actions = ft.Row(spacing=0)
                if r.state == 'pending':
                    actions.controls.append(ft.IconButton(icon=ft.Icons.CHECK_CIRCLE_OUTLINE, icon_color=theme.SUCCESS, tooltip='اعتماد', on_click=lambda e, rid=r.id: decide(rid, True)))
                    actions.controls.append(ft.IconButton(icon=ft.Icons.CANCEL_OUTLINED, icon_color=theme.DANGER, tooltip='رفض', on_click=lambda e, rid=r.id: decide(rid, False)))
                if r.state in ('pending', 'approved'):
                    actions.controls.append(ft.IconButton(icon=ft.Icons.UNDO, tooltip='إلغاء الطلب', on_click=lambda e, rid=r.id: cancel(rid)))
                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(r.number)), ft.DataCell(ft.Text(r.employee.name if r.employee else '-')),
                    ft.DataCell(ft.Text(r.date.strftime('%Y-%m-%d'))), ft.DataCell(ft.Text(r.time_from)), ft.DataCell(ft.Text(r.time_to)),
                    ft.DataCell(ft.Text(f'{r.hours:g}')), ft.DataCell(state_text(r.state)), ft.DataCell(actions),
                ]))
            table.rows = rows; page.update()

        def decide(rid, approve):
            try:
                services.decide_permission_request(rid, approve); fill()
            except Exception as ex:
                snack(str(ex))

        def cancel(rid):
            try:
                services.cancel_permission_request(rid); fill()
            except Exception as ex:
                snack(str(ex))

        state_filter.on_change = fill
        fill()
        return ft.Column([
            theme.card(ft.Column([
                ft.Text('طلب استئذان جديد', size=16, weight=ft.FontWeight.BOLD),
                ft.Text('استئذان لساعات محدودة في نفس اليوم. لأكتر من يوم استخدم طلب إجازة.', color=theme.TEXT_MUTED, size=12),
                ft.Row([emp_dd.control, date_f.control, from_f, to_f, reason_f], wrap=True, spacing=12),
                err,
                ft.FilledButton('تقديم الطلب', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=submit),
            ], spacing=10)),
            ft.Container(height=12),
            theme.card(ft.Column([ft.Row([ft.Text('كل طلبات الاستئذان', size=16, weight=ft.FontWeight.BOLD), ft.Container(expand=True), state_filter]), theme.h_scroll(table)])),
        ], expand=True, scroll=ft.ScrollMode.AUTO)

    # ============================================================ الاستقالة ونهاية الخدمة
    def resignations_tab():
        emp_dd = theme.SearchableDropdown(label='الموظف *', width=260, options=emp_options)
        sub_f = theme.DateField('تاريخ التقديم', page, width=150, value=datetime.date.today().strftime('%Y-%m-%d'))
        last_f = theme.DateField('آخر يوم عمل', page, width=150, value=datetime.date.today().strftime('%Y-%m-%d'))
        reason_f = ft.TextField(label='السبب (اختياري)', width=280)
        err = ft.Text('', color=theme.DANGER, visible=False)

        def submit(e):
            try:
                if not emp_dd.value:
                    raise ValueError('اختر الموظف')
                sd = datetime.datetime.strptime(sub_f.value, '%Y-%m-%d')
                ld = datetime.datetime.strptime(last_f.value, '%Y-%m-%d')
                services.create_resignation_request(int(emp_dd.value), sd, ld, reason_f.value or '')
                reason_f.value = ''; err.visible = False
                snack('تم تقديم طلب الاستقالة'); refresh_all()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        state_filter = ft.Dropdown(label='الحالة', width=160, value='', options=[ft.dropdown.Option('', 'الكل')] + [
            ft.dropdown.Option(k, v) for k, v in services.REQUEST_STATE_LABELS.items()])
        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in
                                      ['الرقم', 'الموظف', 'تاريخ التقديم', 'آخر يوم عمل', 'الحالة', '']], rows=[])

        def fill(e=None):
            rows = []
            for r in services.list_resignation_requests(state=state_filter.value or None):
                actions = ft.Row(spacing=0)
                if r.state == 'pending':
                    actions.controls.append(ft.IconButton(icon=ft.Icons.CHECK_CIRCLE_OUTLINE, icon_color=theme.SUCCESS, tooltip='اعتماد (بيوقف الموظف)', on_click=lambda e, rid=r.id: confirm_approve(rid)))
                    actions.controls.append(ft.IconButton(icon=ft.Icons.CANCEL_OUTLINED, icon_color=theme.DANGER, tooltip='رفض', on_click=lambda e, rid=r.id: decide(rid, False)))
                    actions.controls.append(ft.IconButton(icon=ft.Icons.UNDO, tooltip='إلغاء الطلب', on_click=lambda e, rid=r.id: cancel(rid)))
                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(r.number)), ft.DataCell(ft.Text(r.employee.name if r.employee else '-')),
                    ft.DataCell(ft.Text(r.submission_date.strftime('%Y-%m-%d'))), ft.DataCell(ft.Text(r.last_working_date.strftime('%Y-%m-%d'))),
                    ft.DataCell(state_text(r.state)), ft.DataCell(actions),
                ]))
            table.rows = rows; page.update()

        def confirm_approve(rid):
            def do(ev):
                try:
                    services.decide_resignation_request(rid, True)
                    dlg.open = False; page.update()
                    fill(); snack('تم اعتماد الاستقالة وإيقاف الموظف')
                except Exception as ex:
                    dlg.open = False; snack(str(ex))
            dlg = ft.AlertDialog(modal=True, title=ft.Text('اعتماد الاستقالة'),
                                 content=ft.Text('هيتم إيقاف الموظف وإنهاء عقده الحالي بتاريخ آخر يوم عمل. متأكد؟'),
                                 actions=[ft.TextButton('تراجع', on_click=lambda e: (setattr(dlg, 'open', False), page.update())),
                                          ft.FilledButton('اعتماد', bgcolor=theme.DANGER, on_click=do)])
            page.overlay.append(dlg); dlg.open = True; page.update()

        def decide(rid, approve):
            try:
                services.decide_resignation_request(rid, approve); fill()
            except Exception as ex:
                snack(str(ex))

        def cancel(rid):
            try:
                services.cancel_resignation_request(rid); fill()
            except Exception as ex:
                snack(str(ex))

        state_filter.on_change = fill
        fill()
        return ft.Column([
            theme.card(ft.Column([
                ft.Text('طلب استقالة / إنهاء خدمة جديد', size=16, weight=ft.FontWeight.BOLD),
                ft.Text('الاعتماد بيوقف الموظف وينهي عقده الساري تلقائيًا بتاريخ آخر يوم عمل.', color=theme.TEXT_MUTED, size=12),
                ft.Row([emp_dd.control, sub_f.control, last_f.control, reason_f], wrap=True, spacing=12),
                err,
                ft.FilledButton('تقديم الطلب', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=submit),
            ], spacing=10)),
            ft.Container(height=12),
            theme.card(ft.Column([ft.Row([ft.Text('كل طلبات الاستقالة', size=16, weight=ft.FontWeight.BOLD), ft.Container(expand=True), state_filter]), theme.h_scroll(table)])),
        ], expand=True, scroll=ft.ScrollMode.AUTO)

    theme.call_without_page_update(page, refresh_all)
    return ft.Column([theme.page_title('طلبات الموظفين', 'الإجازات (بأنواعها وأثرها على الراتب) والاستئذان والاستقالة ونهاية الخدمة'),
                      ft.Container(height=10), tabs.control], expand=True)
