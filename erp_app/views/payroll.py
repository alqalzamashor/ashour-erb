import datetime, os
import flet as ft
from .. import services, theme
from ..report_export import export_excel, export_pdf


def build_payroll(page: ft.Page):
    now = datetime.datetime.now()
    month_dd = ft.Dropdown(label='الشهر', width=140, options=[ft.dropdown.Option(str(m), str(m)) for m in range(1, 13)], value=str(now.month))
    year_field = ft.TextField(label='السنة', width=100, value=str(now.year), keyboard_type=ft.KeyboardType.NUMBER)
    err = ft.Text('', color=theme.DANGER, visible=False)

    runs_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text('رقم الدورة')),
            ft.DataColumn(ft.Text('الشهر/السنة')),
            ft.DataColumn(ft.Text('عدد الموظفين')),
            ft.DataColumn(ft.Text('إجمالي الرواتب')),
            ft.DataColumn(ft.Text('صافي المدفوع')),
            ft.DataColumn(ft.Text('الحالة')),
            ft.DataColumn(ft.Text('')),
        ],
        rows=[],
    )

    def refresh_runs(e=None):
        rows = []
        for r in services.list_payroll_runs():
            if r.state != 'posted':
                state_label, state_color = 'مسودة', theme.WARNING
            else:
                pay_status = services.payroll_run_payment_status(r.id)
                if pay_status['all_paid']:
                    state_label, state_color = 'مرحّلة ومصروفة بالكامل', theme.SUCCESS
                elif pay_status['paid_count']:
                    state_label, state_color = f"مرحّلة - مصروف جزئيًا ({pay_status['paid_count']}/{pay_status['total_count']})", theme.WARNING
                else:
                    state_label, state_color = 'مرحّلة', theme.PRIMARY
            total_gross = sum(p.gross_salary for p in r.payslips)
            total_net = sum(p.net_salary for p in r.payslips)
            actions = ft.Row(spacing=2)
            actions.controls.append(ft.IconButton(icon=ft.Icons.VISIBILITY_OUTLINED, tooltip='عرض/تعديل',
                                                    on_click=lambda e, rid=r.id: open_run_dialog(rid)))
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(r.number)),
                ft.DataCell(ft.Text(f'{r.month}/{r.year}')),
                ft.DataCell(ft.Text(str(len(r.payslips)))),
                ft.DataCell(ft.Text(f'{total_gross:,.2f}')),
                ft.DataCell(ft.Text(f'{total_net:,.2f}')),
                ft.DataCell(ft.Text(state_label, color=state_color, weight=ft.FontWeight.BOLD)),
                ft.DataCell(actions),
            ]))
        runs_table.rows = rows
        page.update()

    def create_run(e):
        try:
            rid = services.create_payroll_run(int(month_dd.value), int(year_field.value))
            err.visible = False
            refresh_runs()
            open_run_dialog(rid)
        except Exception as ex:
            err.value = str(ex)
            err.visible = True
            page.update()

    def open_run_dialog(run_id):
        run = services.get_payroll_run(run_id)
        if not run:
            return
        status = services.payroll_run_payment_status(run_id)
        selected_ids = set()

        def make_table(on_all):
            return ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text('الموظف')), ft.DataColumn(ft.Text('القسم')),
                    ft.DataColumn(ft.Text('الأساسي')), ft.DataColumn(ft.Text('البدلات')),
                    ft.DataColumn(ft.Text('التأمينات')), ft.DataColumn(ft.Text('خصومات أخرى')), ft.DataColumn(ft.Text('أيام الغياب')), ft.DataColumn(ft.Text('خصم الأيام (إجازات/غياب/غير موظف)')), ft.DataColumn(ft.Text('أيام العمل الفعلي')),
                    ft.DataColumn(ft.Text('الصافي')), ft.DataColumn(ft.Text('حالة الصرف')),
                ],
                rows=[], show_checkbox_column=(run.state == 'posted'),
                on_select_all=on_all if run.state == 'posted' else None,
            )
        groups_host = ft.Container()
        editable_fields = {}
        absent_fields = {}
        sel_label = ft.Text('', size=12, color=theme.TEXT_MUTED, visible=(run.state == 'posted'))
        dept_dd = ft.Dropdown(label='تحديد قسم كامل', width=220, visible=(run.state == 'posted'), options=[
            ft.dropdown.Option(str(cc_id), name) for cc_id, name in
            sorted({(p.employee.cost_center_id, p.employee.cost_center.name) for p in run.payslips
                   if p.employee and p.employee.cost_center_id} | set())
        ])

        def update_sel_label():
            n = len(selected_ids)
            sel_label.value = f'المحدد للصرف: {n} موظف' if n else 'حدّد موظفين (أو قسم كامل) للصرف الجزئي، أو استخدم "صرف كل المتبقي"'

        def toggle_row(pid, row, paid):
            if paid:
                return
            if pid in selected_ids:
                selected_ids.discard(pid)
            else:
                selected_ids.add(pid)
            row.selected = pid in selected_ids
            update_sel_label(); page.update()

        def select_group(e, pids):
            checked = str(getattr(e, 'data', '')).lower() == 'true'
            for pid in pids:
                p, row = row_by_id[pid]
                if p.paid_at:
                    continue
                (selected_ids.add if checked else selected_ids.discard)(p.id)
                row.selected = p.id in selected_ids
            update_sel_label(); page.update()

        def select_department(e):
            if not dept_dd.value:
                return
            for p, row in row_by_id.values():
                if p.paid_at or not p.employee or p.employee.cost_center_id != int(dept_dd.value):
                    continue
                selected_ids.add(p.id); row.selected = True
            update_sel_label(); page.update()

        dept_dd.on_change = select_department
        row_by_id = {}

        def render_rows():
            row_by_id.clear()
            for p in run.payslips:
                allowances = p.housing_allowance + p.transport_allowance + p.other_allowances
                if run.state == 'draft':
                    ded_field = ft.TextField(value=str(p.other_deductions), width=90, keyboard_type=ft.KeyboardType.NUMBER)
                    editable_fields[p.id] = ded_field
                    ded_cell = ded_field
                else:
                    ded_cell = ft.Text(f'{p.other_deductions:,.2f}')
                if run.state == 'draft':
                    absent_field = ft.TextField(value=f'{p.absent_days or 0:g}', width=70, keyboard_type=ft.KeyboardType.NUMBER)
                    absent_fields[p.id] = absent_field
                    absent_cell = absent_field
                else:
                    absent_cell = ft.Text(f'{p.absent_days or 0:g}')
                days_ded = (p.leave_deduction or 0) + (p.absence_deduction or 0) + (p.unemployed_deduction or 0)
                days_tip = ' | '.join(x for x in [
                    f'إجازات: {p.leave_deduction:,.2f} ({p.leave_deduction_days:g} يوم بعد النسبة)' if p.leave_deduction else '',
                    f'غياب: {p.absence_deduction:,.2f}' if p.absence_deduction else '',
                    f'أيام بدون عقد: {p.unemployed_deduction:,.2f} ({p.unemployed_days:g} يوم)' if p.unemployed_deduction else ''] if x)
                paid_text = ft.Text('مدفوع' if p.paid_at else 'غير مدفوع', color=theme.SUCCESS if p.paid_at else theme.WARNING, weight=ft.FontWeight.BOLD, size=12)
                row = ft.DataRow(selected=p.id in selected_ids, cells=[
                    ft.DataCell(ft.Text(p.employee.name if p.employee else '-')),
                    ft.DataCell(ft.Text(p.employee.cost_center.name if p.employee and p.employee.cost_center else '-', size=12)),
                    ft.DataCell(ft.Text(f'{p.basic_salary:,.2f}')),
                    ft.DataCell(ft.Text(f'{allowances:,.2f}')),
                    ft.DataCell(ft.Text(f'{p.gosi_deduction:,.2f}')),
                    ft.DataCell(ded_cell),
                    ft.DataCell(absent_cell),
                    ft.DataCell(ft.Text(f'{days_ded:,.2f}', size=12, tooltip=days_tip or None)),
                    ft.DataCell(ft.Text(f'{p.worked_days or 0:g}', size=12)),
                    ft.DataCell(ft.Text(f'{p.net_salary:,.2f}', weight=ft.FontWeight.BOLD)),
                    ft.DataCell(paid_text),
                ])
                if run.state == 'posted':
                    row.on_select_change = (lambda e, pid=p.id, r=row, paid=bool(p.paid_at): toggle_row(pid, r, paid))
                row_by_id[p.id] = (p, row)
            build_groups()

        def build_groups():
            """سطر إجمالي لكل (فرع / قسم) بيتفتح يظهر موظفينه."""
            groups = {}
            for p in run.payslips:
                emp = p.employee
                br = emp.branch.name if emp and getattr(emp, 'branch', None) else 'بدون فرع'
                dp = emp.cost_center.name if emp and emp.cost_center else 'بدون قسم'
                groups.setdefault((br, dp), []).append(p)
            blocks = []
            for (br, dp), plist in sorted(groups.items()):
                pids = [p.id for p in plist]
                tbl = make_table(lambda e, pids=pids: select_group(e, pids))
                tbl.rows = [row_by_id[pid][1] for pid in pids]
                body_box = ft.Container(content=theme.h_scroll(tbl), visible=False, padding=ft.Padding(left=8, right=8, top=0, bottom=8))
                icon = ft.IconButton(icon=ft.Icons.KEYBOARD_ARROW_DOWN)

                def toggle(e, box=body_box, ic=icon):
                    box.visible = not box.visible
                    ic.icon = ft.Icons.KEYBOARD_ARROW_UP if box.visible else ft.Icons.KEYBOARD_ARROW_DOWN
                    page.update()
                icon.on_click = toggle
                basic = sum(p.basic_salary for p in plist)
                allow = sum(p.housing_allowance + p.transport_allowance + p.other_allowances for p in plist)
                gosi = sum(p.gosi_deduction for p in plist)
                oth = sum(p.other_deductions for p in plist)
                net = sum(p.net_salary for p in plist)
                head = ft.Container(
                    on_click=toggle, ink=True, padding=ft.Padding(left=4, right=12, top=4, bottom=4),
                    bgcolor=ft.Colors.with_opacity(0.06, theme.PRIMARY), border_radius=8,
                    content=ft.Row([
                        icon,
                        ft.Column([ft.Text(f'{br} / {dp}', weight=ft.FontWeight.BOLD), ft.Text(f'{len(plist)} موظف', size=11, color=theme.TEXT_MUTED)], spacing=0, tight=True, expand=True),
                        ft.Text(f'الأساسي {basic:,.2f}', size=12), ft.Text(f'البدلات {allow:,.2f}', size=12),
                        ft.Text(f'التأمينات {gosi:,.2f}', size=12), ft.Text(f'خصومات {oth:,.2f}', size=12),
                        ft.Text(f'الصافي {net:,.2f}', weight=ft.FontWeight.BOLD, color=theme.PRIMARY),
                    ], spacing=14, wrap=False, scroll=ft.ScrollMode.AUTO))
                blocks.append(ft.Column([head, body_box], spacing=0, tight=True))
            groups_host.content = ft.Column(blocks, spacing=6, tight=True)

        render_rows()
        update_sel_label()

        total_gross = sum(p.gross_salary for p in run.payslips)
        summary = ft.Text(
            f'عدد الموظفين: {len(run.payslips)}   |   إجمالي الرواتب: {total_gross:,.2f}   |   '
            f'الصافي المستحق: {status["total"]:,.2f}   |   مدفوع: {status["paid"]:,.2f} ({status["paid_count"]})'
            f'   |   متبقٍ: {status["remaining"]:,.2f} ({status["total_count"] - status["paid_count"]})',
            weight=ft.FontWeight.BOLD,
        )
        dlg_err = ft.Text('', color=theme.DANGER, visible=False)

        def save_deductions(e):
            try:
                for pid, field in editable_fields.items():
                    services.update_payslip(pid, other_deductions=float(field.value or 0), absent_days=float(absent_fields[pid].value or 0) if pid in absent_fields else 0)
                dialog.open = False
                page.update()
                refresh_runs()
            except Exception as ex:
                dlg_err.value = str(ex); dlg_err.visible = True; page.update()

        def post_run(e):
            try:
                if editable_fields:
                    for pid, field in editable_fields.items():
                        services.update_payslip(pid, other_deductions=float(field.value or 0), absent_days=float(absent_fields[pid].value or 0) if pid in absent_fields else 0)
                services.post_payroll_run(run.id)
                dialog.open = False
                page.update()
                refresh_runs()
            except Exception as ex:
                dlg_err.value = str(ex); dlg_err.visible = True; page.update()

        def sync_attendance(e):
            try:
                from .. import attendance
                for pid, field in editable_fields.items():
                    services.update_payslip(pid, other_deductions=float(field.value or 0), absent_days=float(absent_fields[pid].value or 0) if pid in absent_fields else 0)
                n = attendance.sync_run_absence(run.id)
                dialog.open = False; page.update(); refresh_runs()
                page.overlay.append(ft.SnackBar(ft.Text(f'اتحسب الغياب من البصمة لـ {n} موظف (الباقي غيابهم يدوي)'), open=True)); page.update()
            except Exception as ex:
                dlg_err.value = str(ex); dlg_err.visible = True; page.update()

        def reopen_run(e):
            try:
                services.reopen_payroll_run(run.id)
                dialog.open = False
                page.update()
                refresh_runs()
            except Exception as ex:
                dlg_err.value = str(ex); dlg_err.visible = True; page.update()

        def delete_run(e):
            try:
                services.delete_payroll_run(run.id)
                dialog.open = False
                page.update()
                refresh_runs()
            except Exception as ex:
                dlg_err.value = str(ex); dlg_err.visible = True; page.update()

        def export_run(kind):
            try:
                rows = [{
                    'code': p.employee.code if p.employee else '-', 'name': p.employee.name if p.employee else '-',
                    'basic': p.basic_salary, 'housing': p.housing_allowance, 'transport': p.transport_allowance,
                    'other_allow': p.other_allowances, 'gosi': p.gosi_deduction, 'other_ded': p.other_deductions, 'leave_ded': (p.leave_deduction or 0) + (p.absence_deduction or 0) + (p.unemployed_deduction or 0), 'worked_days': p.worked_days or 0,
                    'net': p.net_salary,
                } for p in run.payslips]
                exports_dir = services.downloads_dir()
                path = (export_excel if kind == 'xlsx' else export_pdf)({'rows': rows}, 'payroll', exports_dir)
                theme.open_or_download_file(page, path)
                page.overlay.append(ft.SnackBar(ft.Text(f'تم إنشاء الملف: {path}'), open=True)); page.update()
            except Exception as ex:
                page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

        def open_pay_dialog(ids, label):
            methods = [m for m in services.list_payment_methods(active_only=True) if not m.is_credit]
            pm_dd = ft.Dropdown(label='طريقة الدفع *', width=280,
                               options=[ft.dropdown.Option(str(m.id), m.name) for m in methods],
                               value=str(methods[0].id) if methods else None)
            pdate_f = theme.DateField('تاريخ الصرف', page, width=160, value=datetime.date.today().strftime('%Y-%m-%d'))
            ref_f = ft.TextField(label='مرجع (اختياري)', width=200)
            perr = ft.Text('', color=theme.DANGER, visible=False)
            unpaid_total = sum(p.net_salary for p in run.payslips if p.id in ids and not p.paid_at)
            if not methods:
                perr.value = 'مفيش طريقة دفع فورية متاحة (غير آجلة) - ضيف واحدة من شاشة "طرق الدفع" الأول'; perr.visible = True

            def confirm_pay(ev):
                try:
                    if not pm_dd.value:
                        raise ValueError('اختر طريقة الدفع')
                    d = datetime.datetime.strptime(pdate_f.value, '%Y-%m-%d')
                    res = services.pay_payslips(list(ids), int(pm_dd.value), payment_date=d, reference=ref_f.value or '')
                    pay_dlg.open = False; dialog.open = False; page.update()
                    refresh_runs()
                    names_txt = '، '.join(res['employee_names'][:5]) + ('...' if len(res['employee_names']) > 5 else '')
                    page.overlay.append(ft.SnackBar(ft.Text(f"تم صرف {res['employee_count']} موظف ({names_txt}) - سند {res['payment_number']} بمبلغ {res['amount']:,.2f}"), open=True)); page.update()
                except Exception as ex:
                    perr.value = str(ex); perr.visible = True; page.update()

            pay_dlg = ft.AlertDialog(modal=True, title=ft.Text(f'صرف صافي الرواتب - {label}'),
                                     content=ft.Column([
                                         ft.Text(f'المبلغ المستحق (غير المدفوع فقط): {unpaid_total:,.2f}', weight=ft.FontWeight.BOLD, size=16),
                                         ft.Text('هيتعمل سند صرف واحد وقيد محاسبي (مدين الرواتب المستحقة / دائن حساب طريقة الدفع) للموظفين المختارين بس.',
                                                 color=theme.TEXT_MUTED, size=12),
                                         pm_dd, pdate_f.control, ref_f, perr], tight=True, spacing=10, width=420),
                                     actions=[ft.TextButton('تراجع', on_click=lambda ev: (setattr(pay_dlg, 'open', False), page.update())),
                                              ft.FilledButton('تأكيد الصرف', icon=ft.Icons.PAYMENTS_OUTLINED, bgcolor=theme.PRIMARY, on_click=confirm_pay)])
            page.overlay.append(pay_dlg); pay_dlg.open = True; page.update()

        def pay_selected(e):
            if not selected_ids:
                dlg_err.value = 'حدّد موظف واحد على الأقل الأول'; dlg_err.visible = True; page.update(); return
            open_pay_dialog(set(selected_ids), f'{len(selected_ids)} موظف محدد')

        def pay_all_remaining(e):
            remaining = [p.id for p in run.payslips if not p.paid_at]
            open_pay_dialog(set(remaining), 'كل المتبقي')

        def open_history(e):
            pays = services.list_payroll_run_payments(run.id)
            rows = []
            for pay in pays:
                color = theme.TEXT_MUTED if pay.voided else theme.SUCCESS
                rows.append(ft.Row([
                    ft.Text(pay.number, weight=ft.FontWeight.BOLD, color=color), ft.Text(pay.date.strftime('%Y-%m-%d'), size=12),
                    ft.Text(f'{pay.amount:,.2f}', color=color), ft.Text('ملغى' if pay.voided else 'سارٍ', size=12, color=color),
                    ft.Text(pay.notes or '', size=11, color=theme.TEXT_MUTED, expand=True),
                    ft.IconButton(icon=ft.Icons.CANCEL_OUTLINED, icon_color=theme.DANGER, tooltip='إلغاء السند', visible=not pay.voided,
                                 on_click=lambda ev, pid=pay.id: void_history_payment(pid)),
                ], spacing=10))
            hist_dlg.content = ft.Column(rows if rows else [ft.Text('مفيش سندات صرف لهذه الدورة بعد', color=theme.TEXT_MUTED)], tight=True, scroll=ft.ScrollMode.AUTO, height=260)
            page.overlay.append(hist_dlg); hist_dlg.open = True; page.update()

        def void_history_payment(payment_id):
            try:
                services.void_payment(payment_id)
                hist_dlg.open = False; dialog.open = False; page.update()
                refresh_runs()
                page.overlay.append(ft.SnackBar(ft.Text('تم إلغاء السند'), open=True)); page.update()
            except Exception as ex:
                page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True)); page.update()

        hist_dlg = ft.AlertDialog(modal=True, title=ft.Text('سندات صرف هذه الدورة'), content=ft.Text(''),
                                  actions=[ft.TextButton('إغلاق', on_click=lambda e: (setattr(hist_dlg, 'open', False), page.update()))])

        def unpay_run(e):
            def do(ev):
                try:
                    services.unpay_payroll_run(run.id)
                    undo_dlg.open = False; dialog.open = False; page.update()
                    refresh_runs()
                    page.overlay.append(ft.SnackBar(ft.Text('تم التراجع عن كل عمليات صرف هذه الدورة'), open=True)); page.update()
                except Exception as ex:
                    undo_dlg.open = False
                    page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True)); page.update()
            undo_dlg = ft.AlertDialog(modal=True, title=ft.Text('التراجع عن كل عمليات الصرف'),
                                      content=ft.Text('هيتم إلغاء كل سندات الصرف السارية لهذه الدورة (لكل الموظفين). متأكد؟'),
                                      actions=[ft.TextButton('لأ', on_click=lambda ev: (setattr(undo_dlg, 'open', False), page.update())),
                                               ft.FilledButton('تراجع عن الكل', bgcolor=theme.DANGER, on_click=do)])
            page.overlay.append(undo_dlg); undo_dlg.open = True; page.update()

        actions = [ft.TextButton('إغلاق', on_click=lambda e: (setattr(dialog, 'open', False), page.update()))]
        if run.state == 'draft':
            actions += [
                ft.OutlinedButton('حفظ التعديلات', icon=ft.Icons.SAVE, on_click=save_deductions),
                ft.OutlinedButton('احسب الغياب من البصمة', icon=ft.Icons.FINGERPRINT, on_click=sync_attendance),
                theme.guard_submit(ft.FilledButton('ترحيل الدورة', icon=ft.Icons.CHECK_CIRCLE, bgcolor=theme.PRIMARY, on_click=post_run)),
            ]
        else:
            actions.append(ft.TextButton('سجل السندات', icon=ft.Icons.HISTORY, on_click=open_history))
            if status['paid_count'] > 0:
                actions.append(ft.OutlinedButton('تراجع عن الكل', icon=ft.Icons.UNDO, on_click=unpay_run))
            if not status['all_paid']:
                if status['paid_count'] == 0:
                    actions.append(ft.OutlinedButton('إرجاع لمسودة', icon=ft.Icons.UNDO, on_click=reopen_run))
                actions.append(ft.OutlinedButton('صرف المحدد', icon=ft.Icons.CHECKLIST, on_click=pay_selected))
                actions.append(ft.FilledButton('صرف كل المتبقي', icon=ft.Icons.PAYMENTS_OUTLINED, bgcolor=theme.SUCCESS, on_click=pay_all_remaining))
        actions += [
            ft.OutlinedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export_run('xlsx')),
            ft.OutlinedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export_run('pdf')),
        ]
        if run.state == 'draft':
            actions.insert(1, ft.TextButton('حذف الدورة', on_click=delete_run))

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f'دورة رواتب {run.month}/{run.year} — {run.number} ({"مرحّلة" if run.state=="posted" else "مسودة"})'),
            content=ft.Container(
                width=900, height=520,
                content=ft.Column([summary, ft.Row([dept_dd, sel_label], wrap=True, spacing=16), ft.Divider(),
                                   groups_host, dlg_err],
                                   spacing=10, tight=True, scroll=ft.ScrollMode.AUTO),
            ),
            actions=actions, actions_alignment=ft.MainAxisAlignment.END,
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    refresh_runs()

    header = ft.Row(
        [theme.page_title('الرواتب', 'إنشاء دورات الرواتب الشهرية وترحيلها للحسابات')],
    )

    new_run_card = theme.card(
        ft.Column([
            ft.Text('دورة رواتب جديدة', size=16, weight=ft.FontWeight.BOLD),
            ft.Text('بتولّد قسيمة راتب تلقائياً لكل موظف نشط له عقد ساري في الشهر المحدد.', color=theme.TEXT_MUTED),
            ft.Row([month_dd, year_field, theme.guard_submit(ft.FilledButton('إنشاء الدورة', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=create_run))]),
            err,
        ], spacing=10)
    )

    return ft.Column(
        [
            header, ft.Container(height=12), new_run_card, ft.Container(height=16),
            theme.card(ft.Column([
                ft.Text('دورات الرواتب', size=16, weight=ft.FontWeight.BOLD),
                theme.h_scroll(runs_table),
            ]), expand=True),
        ],
        expand=True, scroll=ft.ScrollMode.AUTO,
    )
