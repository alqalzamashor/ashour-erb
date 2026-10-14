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
        tabs.set_tabs([('الإجازات', leaves_tab()), ('الاستئذان', permissions_tab()), ('الاستقالة ونهاية الخدمة', resignations_tab())],
                      selected_index=tabs.selected_index)
        page.update()

    # ============================================================ الإجازات
    def leaves_tab():
        emp_dd = theme.SearchableDropdown(label='الموظف *', width=260, options=emp_options)
        type_dd = ft.Dropdown(label='نوع الإجازة', width=170, value='annual', options=[
            ft.dropdown.Option(k, v) for k, v in services.LEAVE_TYPE_LABELS.items()])
        start_f = theme.DateField('من تاريخ', page, width=150, value=datetime.date.today().strftime('%Y-%m-%d'))
        end_f = theme.DateField('إلى تاريخ', page, width=150, value=datetime.date.today().strftime('%Y-%m-%d'))
        reason_f = ft.TextField(label='السبب (اختياري)', width=280)
        err = ft.Text('', color=theme.DANGER, visible=False)
        balance_txt = ft.Text('', size=12, color=theme.TEXT_MUTED)

        def show_balance(e=None):
            if emp_dd.value and type_dd.value == 'annual':
                b = services.annual_leave_balance(int(emp_dd.value))
                balance_txt.value = f"رصيد {b['year']}: المستحق {b['allowance']} - المستخدم {b['used']} - معلّق {b['pending']} = المتاح {b['remaining']} يوم"
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
                    ft.DataCell(ft.Text(services.LEAVE_TYPE_LABELS.get(r.leave_type, r.leave_type))),
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
    return ft.Column([theme.page_title('طلبات الموظفين', 'الإجازات (سنوية/مرضية/بدون راتب) والاستئذان والاستقالة ونهاية الخدمة'),
                      ft.Container(height=10), tabs.control], expand=True)
