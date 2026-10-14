import datetime
import flet as ft
from .. import services, theme
from ..report_export import export_excel, export_pdf


def build_allowances_insurance(page: ft.Page):
    """دورة المخصصات والتأمينات - منفصلة عن دورة الرواتب الشهرية، بنفس
    الفكرة بالظبط: مسودة يوليّها المستخدم قبل الترحيل، ثم قيد محاسبي واحد
    يجمّع كل الموظفين. بتغطي مخصصات إضافية (مكافآت استثنائية) ونصيب صاحب
    العمل في التأمينات الاجتماعية (محسوب تلقائياً من نسبة العقد)."""
    now = datetime.datetime.now()
    month_dd = ft.Dropdown(label='الشهر', width=140, options=[ft.dropdown.Option(str(m), str(m)) for m in range(1, 13)], value=str(now.month))
    year_field = ft.TextField(label='السنة', width=100, value=str(now.year), keyboard_type=ft.KeyboardType.NUMBER)
    err = ft.Text('', color=theme.DANGER, visible=False)

    runs_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text('رقم الدورة')),
            ft.DataColumn(ft.Text('الشهر/السنة')),
            ft.DataColumn(ft.Text('عدد الموظفين')),
            ft.DataColumn(ft.Text('إجمالي المخصصات')),
            ft.DataColumn(ft.Text('إجمالي التأمينات والمخصصات')),
            ft.DataColumn(ft.Text('الحالة')),
            ft.DataColumn(ft.Text('')),
        ],
        rows=[],
    )

    def refresh_runs(e=None):
        rows = []
        for r in services.list_allowance_insurance_runs():
            state_label = 'مرحّلة' if r.state == 'posted' else 'مسودة'
            state_color = theme.SUCCESS if r.state == 'posted' else theme.WARNING
            total_extra = sum(it.extra_allowance or 0 for it in r.items)
            total_provisions = sum((it.employer_gosi_amount or 0) + (it.leave_provision_amount or 0) + (it.eos_provision_amount or 0) for it in r.items)
            actions = ft.Row(spacing=2)
            actions.controls.append(ft.IconButton(icon=ft.Icons.VISIBILITY_OUTLINED, tooltip='عرض/تعديل',
                                                    on_click=lambda e, rid=r.id: open_run_dialog(rid)))
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(r.number)),
                ft.DataCell(ft.Text(f'{r.month}/{r.year}')),
                ft.DataCell(ft.Text(str(len(r.items)))),
                ft.DataCell(ft.Text(f'{total_extra:,.2f}')),
                ft.DataCell(ft.Text(f'{total_provisions:,.2f}')),
                ft.DataCell(ft.Text(state_label, color=state_color, weight=ft.FontWeight.BOLD)),
                ft.DataCell(actions),
            ]))
        runs_table.rows = rows
        page.update()

    def create_run(e):
        try:
            rid = services.create_allowance_insurance_run(int(month_dd.value), int(year_field.value))
            err.visible = False
            refresh_runs()
            open_run_dialog(rid)
        except Exception as ex:
            err.value = str(ex)
            err.visible = True
            page.update()

    def open_run_dialog(run_id):
        run = services.get_allowance_insurance_run(run_id)
        if not run:
            return

        postable_accounts = services.list_accounts(postable_only=True)
        acct_options = [('', 'اختر حساب')] + [(str(a.id), f'{a.code} - {a.name}') for a in postable_accounts]

        item_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text('الموظف')),
                ft.DataColumn(ft.Text('مخصص إضافي')),
                ft.DataColumn(ft.Text('حساب المخصص')),
                ft.DataColumn(ft.Text('ملاحظة')),
                ft.DataColumn(ft.Text('تأمينات صاحب العمل')),
                ft.DataColumn(ft.Text('مخصص الإجازة')),
                ft.DataColumn(ft.Text('مخصص نهاية الخدمة')),
                ft.DataColumn(ft.Text('الإجمالي')),
            ],
            rows=[],
        )
        editable_fields = {}

        def render_rows():
            rows = []
            for it in run.items:
                if run.state == 'draft':
                    amt_field = ft.TextField(value=str(it.extra_allowance or 0), width=100, keyboard_type=ft.KeyboardType.NUMBER)
                    acc_dd = theme.SearchableDropdown(label='حساب المخصص الإضافي', value=str(it.extra_allowance_account_id) if it.extra_allowance_account_id else '', options=acct_options, width=220, flat=True, suggestions_height=160, page=page)
                    note_field = ft.TextField(value=it.extra_allowance_note or '', width=140)
                    editable_fields[it.id] = (amt_field, acc_dd, note_field)
                    amt_cell, acc_cell, note_cell = amt_field, acc_dd.control, note_field
                else:
                    amt_cell = ft.Text(f'{it.extra_allowance:,.2f}')
                    acc_cell = ft.Text(it.extra_allowance_account.name if it.extra_allowance_account else '-', size=11)
                    note_cell = ft.Text(it.extra_allowance_note or '-')
                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(it.employee.name if it.employee else '-')),
                    ft.DataCell(amt_cell),
                    ft.DataCell(acc_cell),
                    ft.DataCell(note_cell),
                    ft.DataCell(ft.Text(f'{it.employer_gosi_amount:,.2f}')),
                    ft.DataCell(ft.Text(f'{it.leave_provision_amount:,.2f}')),
                    ft.DataCell(ft.Text(f'{it.eos_provision_amount:,.2f}')),
                    ft.DataCell(ft.Text(f'{it.total:,.2f}', weight=ft.FontWeight.BOLD)),
                ]))
            item_table.rows = rows

        render_rows()

        total_extra = sum(it.extra_allowance or 0 for it in run.items)
        total_gosi = sum(it.employer_gosi_amount or 0 for it in run.items)
        total_leave = sum(it.leave_provision_amount or 0 for it in run.items)
        total_eos = sum(it.eos_provision_amount or 0 for it in run.items)
        grand_total = total_extra + total_gosi + total_leave + total_eos
        summary = ft.Text(
            f'عدد الموظفين: {len(run.items)}   |   المخصصات الإضافية: {total_extra:,.2f}   |   تأمينات صاحب العمل: {total_gosi:,.2f}   |   '
            f'مخصص الإجازة: {total_leave:,.2f}   |   مخصص نهاية الخدمة: {total_eos:,.2f}   |   الإجمالي الكلي: {grand_total:,.2f}',
            weight=ft.FontWeight.BOLD,
        )
        dlg_err = ft.Text('', color=theme.DANGER, visible=False)

        def apply_edits():
            for item_id, (amt_field, acc_dd, note_field) in editable_fields.items():
                amount = float(amt_field.value or 0)
                services.update_allowance_insurance_item(
                    item_id, extra_allowance=amount,
                    extra_allowance_account_id=int(acc_dd.value) if acc_dd.value else None,
                    extra_allowance_note=note_field.value or '',
                )

        def save_edits(e):
            try:
                apply_edits()
                dialog.open = False
                page.update()
                refresh_runs()
            except Exception as ex:
                dlg_err.value = str(ex); dlg_err.visible = True; page.update()

        def post_run(e):
            try:
                if editable_fields:
                    apply_edits()
                services.post_allowance_insurance_run(run.id)
                dialog.open = False
                page.update()
                refresh_runs()
            except Exception as ex:
                dlg_err.value = str(ex); dlg_err.visible = True; page.update()

        def reopen_run(e):
            try:
                services.reopen_allowance_insurance_run(run.id)
                dialog.open = False
                page.update()
                refresh_runs()
            except Exception as ex:
                dlg_err.value = str(ex); dlg_err.visible = True; page.update()

        def delete_run(e):
            try:
                services.delete_allowance_insurance_run(run.id)
                dialog.open = False
                page.update()
                refresh_runs()
            except Exception as ex:
                dlg_err.value = str(ex); dlg_err.visible = True; page.update()

        def export_run(kind):
            try:
                rows = [{
                    'code': it.employee.code if it.employee else '-', 'name': it.employee.name if it.employee else '-',
                    'extra_allowance': it.extra_allowance, 'extra_note': it.extra_allowance_note or '',
                    'employer_gosi': it.employer_gosi_amount, 'leave_provision': it.leave_provision_amount,
                    'eos_provision': it.eos_provision_amount, 'total': it.total,
                } for it in run.items]
                path = (export_excel if kind == 'xlsx' else export_pdf)({'rows': rows}, 'allowances_insurance', services.downloads_dir())
                theme.open_or_download_file(page, path)
                page.overlay.append(ft.SnackBar(ft.Text(f'تم إنشاء الملف: {path}'), open=True)); page.update()
            except Exception as ex:
                page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

        actions = [ft.TextButton('إغلاق', on_click=lambda e: (setattr(dialog, 'open', False), page.update()))]
        if run.state == 'draft':
            actions += [
                ft.OutlinedButton('حفظ التعديلات', icon=ft.Icons.SAVE, on_click=save_edits),
                theme.guard_submit(ft.FilledButton('ترحيل الدورة', icon=ft.Icons.CHECK_CIRCLE, bgcolor=theme.PRIMARY, on_click=post_run)),
            ]
        else:
            actions += [ft.OutlinedButton('إرجاع لمسودة', icon=ft.Icons.UNDO, on_click=reopen_run)]
        actions += [
            ft.OutlinedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export_run('xlsx')),
            ft.OutlinedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export_run('pdf')),
        ]
        if run.state == 'draft':
            actions.insert(1, ft.TextButton('حذف الدورة', on_click=delete_run))

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f'دورة مخصصات وتأمينات {run.month}/{run.year} — {run.number} ({"مرحّلة" if run.state=="posted" else "مسودة"})'),
            content=ft.Container(
                width=780, height=450,
                content=ft.Column([summary, ft.Divider(), theme.h_scroll(item_table), dlg_err],
                                   spacing=10, tight=True, scroll=ft.ScrollMode.AUTO),
            ),
            actions=actions, actions_alignment=ft.MainAxisAlignment.END,
        )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()

    refresh_runs()

    header = ft.Row([theme.page_title('المخصصات والتأمينات', 'دورة منفصلة عن الرواتب الشهرية لمخصصات إضافية ونصيب صاحب العمل في التأمينات الاجتماعية')])

    new_run_card = theme.card(
        ft.Column([
            ft.Text('دورة مخصصات وتأمينات جديدة', size=16, weight=ft.FontWeight.BOLD),
            ft.Text(
                'بتولّد بند تلقائي لكل موظف نشط له عقد ساري - نصيب صاحب العمل في التأمينات بيتحسب تلقائيًا من نسبة '
                'العقد (مصروف على الشركة، مش خصم من الموظف). المخصص الإضافي (مكافأة استثنائية مثلاً) بتحدده يدويًا لكل موظف قبل الترحيل.',
                color=theme.TEXT_MUTED,
            ),
            ft.Row([month_dd, year_field, theme.guard_submit(ft.FilledButton('إنشاء الدورة', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=create_run))]),
            err,
        ], spacing=10)
    )

    return ft.Column(
        [
            header, ft.Container(height=12), new_run_card, ft.Container(height=16),
            theme.card(ft.Column([
                ft.Text('دورات المخصصات والتأمينات', size=16, weight=ft.FontWeight.BOLD),
                theme.h_scroll(runs_table),
            ]), expand=True),
        ],
        expand=True, scroll=ft.ScrollMode.AUTO,
    )
