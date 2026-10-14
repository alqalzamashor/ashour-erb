import datetime
import flet as ft
from .. import services, theme


def build_contracts(page: ft.Page):
    employees = services.list_employees()
    postable_accounts = services.list_accounts(postable_only=True)
    emp_filter = ft.Dropdown(
        label='الموظف', width=280,
        options=[ft.dropdown.Option('', 'كل الموظفين')] + [ft.dropdown.Option(str(e.id), f'{e.code} - {e.name}') for e in employees],
        value='',
    )

    acct_opts = [(str(a.id), f'{a.code} - {a.name}') for a in postable_accounts]

    emp_dd = theme.SearchableDropdown(label='الموظف', width=280, options=[(str(e.id), f'{e.code} - {e.name}') for e in employees])
    type_dd = ft.Dropdown(label='نوع العقد', width=160, options=[
        ft.dropdown.Option('permanent', 'دائم'), ft.dropdown.Option('temporary', 'مؤقت'),
    ], value='permanent')
    start_field = theme.DateField('تاريخ البداية', page, width=160, value=datetime.date.today().strftime('%Y-%m-%d'))
    end_field = theme.DateField('تاريخ النهاية (اختياري)', page, width=180)

    basic_field = ft.TextField(label='الراتب الأساسي', width=150, keyboard_type=ft.KeyboardType.NUMBER)
    basic_account_dd = theme.SearchableDropdown(label='حساب الراتب الأساسي *', width=260, options=acct_opts)

    housing_field = ft.TextField(label='بدل السكن', width=130, value='0', keyboard_type=ft.KeyboardType.NUMBER)
    housing_account_dd = theme.SearchableDropdown(label='حساب بدل السكن', width=230, options=acct_opts)

    transport_field = ft.TextField(label='بدل النقل', width=130, value='0', keyboard_type=ft.KeyboardType.NUMBER)
    transport_account_dd = theme.SearchableDropdown(label='حساب بدل النقل', width=230, options=acct_opts)

    other_field = ft.TextField(label='بدلات أخرى', width=130, value='0', keyboard_type=ft.KeyboardType.NUMBER)
    other_account_dd = theme.SearchableDropdown(label='حساب البدلات الأخرى', width=230, options=acct_opts)

    gosi_field = ft.TextField(label='نسبة التأمينات % (حصة الموظف)', width=220, value='9.75', keyboard_type=ft.KeyboardType.NUMBER)
    gosi_account_dd = theme.SearchableDropdown(label='حساب خصم التأمينات *', width=260, options=acct_opts)
    other_ded_account_dd = theme.SearchableDropdown(label='حساب الخصومات الأخرى *', width=260, options=acct_opts)

    gosi_employer_field = ft.TextField(label='نسبة تأمينات صاحب العمل %', width=200, value='11.75', keyboard_type=ft.KeyboardType.NUMBER)
    gosi_employer_expense_dd = theme.SearchableDropdown(label='تأمينات صاحب العمل - مدين (مصروف)', width=260, options=acct_opts)
    gosi_employer_payable_dd = theme.SearchableDropdown(label='تأمينات صاحب العمل - دائن (مستحق)', width=260, options=acct_opts)

    leave_field = ft.TextField(label='نسبة مخصص الإجازة %', width=180, value='8.33', keyboard_type=ft.KeyboardType.NUMBER)
    leave_expense_dd = theme.SearchableDropdown(label='مخصص الإجازة - مدين (مصروف)', width=250, options=acct_opts)
    leave_payable_dd = theme.SearchableDropdown(label='مخصص الإجازة - دائن (مستحق)', width=250, options=acct_opts)

    eos_field = ft.TextField(label='نسبة مخصص نهاية الخدمة %', width=200, value='8.33', keyboard_type=ft.KeyboardType.NUMBER)
    eos_expense_dd = theme.SearchableDropdown(label='مخصص نهاية الخدمة - مدين (مصروف)', width=260, options=acct_opts)
    eos_payable_dd = theme.SearchableDropdown(label='مخصص نهاية الخدمة - دائن (مستحق)', width=260, options=acct_opts)

    error_text = ft.Text('', color=theme.DANGER, visible=False)
    editing_id = {'value': None}

    STATE_LABELS = services.CONTRACT_STATE_LABELS
    STATE_COLORS = {'active': theme.SUCCESS, 'expired': theme.TEXT_MUTED, 'renewed': theme.PRIMARY, 'terminated': theme.DANGER}
    latest_ids = set()      # آخر عقد لكل موظف - الوحيد اللي يتجدد
    expiry_note = ft.Container(visible=False, bgcolor=theme.WARNING_LIGHT, border_radius=10,
                               padding=ft.Padding(left=14, right=14, top=10, bottom=10))

    def acc_text(account):
        return f'{account.code} - {account.name}' if account else '-'

    def _contract_row(c):
        actions = ft.Row(spacing=4)
        actions.controls.append(
            ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل العقد', on_click=lambda e, cid=c.id: open_edit(cid))
        )
        if c.state in ('active', 'expired') and c.id in latest_ids:
            actions.controls.append(
                ft.IconButton(icon=ft.Icons.AUTORENEW, icon_color=theme.PRIMARY, tooltip='تجديد العقد',
                              on_click=lambda e, cid=c.id: open_renew(cid))
            )
        if c.state in ('active', 'expired') and c.id in latest_ids:
            actions.controls.append(
                ft.IconButton(icon=ft.Icons.CANCEL_OUTLINED, icon_color=theme.DANGER, tooltip='إنهاء / فسخ العقد',
                              on_click=lambda e, cid=c.id: open_terminate(cid))
            )
        actions.controls.append(
            ft.IconButton(icon=ft.Icons.HISTORY, tooltip='سجل عقود الموظف ورواتبه', on_click=lambda e, eid=c.employee_id: open_history(eid))
        )
        # تفاصيل الحالة تحت اسمها: متبقي كام يوم / رقم التجديد / تاريخ الإنهاء
        state_extra = None
        if c.state == 'active' and c.end_date:
            left = (c.end_date.date() - datetime.date.today()).days
            if left < 0:
                state_extra = ft.Text(f'انتهت من {-left} يوم - محتاج تجديد', size=10, color=theme.DANGER, weight=ft.FontWeight.BOLD)
            elif left <= 60:
                state_extra = ft.Text(f'تنتهي بعد {left} يوم', size=10, color=theme.WARNING, weight=ft.FontWeight.BOLD)
        elif c.state == 'terminated' and c.termination_date:
            state_extra = ft.Text(f'بتاريخ {c.termination_date:%Y-%m-%d}', size=10, color=theme.TEXT_MUTED)
        if (c.renewal_count or 0) > 0 and c.state != 'terminated':
            state_extra = state_extra or ft.Text(f'تجديد رقم {c.renewal_count}', size=10, color=theme.PRIMARY)
        raise_cell = ft.Text('-', color=theme.TEXT_MUTED)
        if (c.raise_amount or 0) > 0:
            pct = (c.raise_amount / c.previous_gross_salary * 100.0) if c.previous_gross_salary else 0
            raise_cell = ft.Text(f'+{c.raise_amount:,.2f} ({pct:.1f}%)', color=theme.SUCCESS, weight=ft.FontWeight.BOLD, size=12)
        elif c.renewed_from_id:
            raise_cell = ft.Text('بدون زيادة', size=11, color=theme.TEXT_MUTED)
        return ft.DataRow(cells=[
            ft.DataCell(ft.Text(c.contract_number)),
            ft.DataCell(ft.Text(c.employee.name if c.employee else '-')),
            ft.DataCell(ft.Text(c.start_date.strftime('%Y-%m-%d') if c.start_date else '-')),
            ft.DataCell(ft.Text(c.end_date.strftime('%Y-%m-%d') if c.end_date else 'غير محدد')),
            ft.DataCell(ft.Text(f'{c.gross_salary:,.2f}')),
            ft.DataCell(raise_cell),
            ft.DataCell(ft.Text(acc_text(c.basic_salary_account), size=11)),
            ft.DataCell(ft.Text(acc_text(c.housing_allowance_account), size=11)),
            ft.DataCell(ft.Text(acc_text(c.transport_allowance_account), size=11)),
            ft.DataCell(ft.Text(acc_text(c.other_allowances_account), size=11)),
            ft.DataCell(ft.Text(acc_text(c.gosi_deduction_account), size=11)),
            ft.DataCell(ft.Text(acc_text(c.other_deductions_account), size=11)),
            ft.DataCell(ft.Column([ft.Text(STATE_LABELS.get(c.state, c.state), color=STATE_COLORS.get(c.state), weight=ft.FontWeight.BOLD)]
                                  + ([state_extra] if state_extra else []), spacing=0, tight=True)),
            ft.DataCell(actions),
        ])

    table_sortable = theme.SortableDataTable(
        columns=[
            ('رقم العقد', lambda c: c.contract_number), ('الموظف', lambda c: c.employee.name if c.employee else ''),
            ('من', lambda c: c.start_date), ('إلى', lambda c: c.end_date), ('الراتب الإجمالي', lambda c: c.gross_salary, True),
            ('الزيادة عند التجديد', lambda c: c.raise_amount or 0, True),
            ('حساب الراتب', None), ('حساب السكن', None), ('حساب النقل', None), ('حساب بدلات أخرى', None),
            ('حساب التأمينات', None), ('حساب خصومات أخرى', None),
            ('الحالة', lambda c: STATE_LABELS.get(c.state, c.state)), ('', None),
        ],
        row_builder=_contract_row, page=page, expand=True,
    )
    table = table_sortable.control

    def refresh(e=None):
        employee_id = int(emp_filter.value) if emp_filter.value else None
        all_contracts = services.list_contracts()
        latest = {}
        for c in all_contracts:
            if c.employee_id not in latest or c.start_date > latest[c.employee_id].start_date:
                latest[c.employee_id] = c
        latest_ids.clear(); latest_ids.update(c.id for c in latest.values())
        alerts = services.contracts_expiring(60)
        if alerts:
            lines = [f'{c.employee.name if c.employee else c.contract_number}: ' + (f'تنتهي بعد {d} يوم' if d >= 0 else f'انتهت من {-d} يوم') for c, d in alerts[:6]]
            expiry_note.content = ft.Column([
                ft.Row([ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=theme.WARNING, size=18),
                        ft.Text(f'{len(alerts)} عقد محتاج تجديد قريب', weight=ft.FontWeight.BOLD, color=theme.WARNING_TEXT)], spacing=6),
                ft.Text(' | '.join(lines) + (' ...' if len(alerts) > 6 else ''), size=12, color=theme.WARNING_TEXT),
            ], spacing=3, tight=True)
            expiry_note.visible = True
        else:
            expiry_note.visible = False
        table_sortable.set_data([c for c in all_contracts if not employee_id or c.employee_id == employee_id])

    def close_dialog(e=None):
        dialog.open = False
        page.update()

    def clear_form():
        emp_dd.value = None; type_dd.value = 'permanent'
        start_field.value = datetime.date.today().strftime('%Y-%m-%d'); end_field.value = ''
        basic_field.value = ''; basic_account_dd.value = None
        housing_field.value = '0'; housing_account_dd.value = None
        transport_field.value = '0'; transport_account_dd.value = None
        other_field.value = '0'; other_account_dd.value = None
        gosi_field.value = '9.75'; gosi_account_dd.value = None
        other_ded_account_dd.value = None
        gosi_employer_field.value = '11.75'; gosi_employer_expense_dd.value = None; gosi_employer_payable_dd.value = None
        leave_field.value = '8.33'; leave_expense_dd.value = None; leave_payable_dd.value = None
        eos_field.value = '8.33'; eos_expense_dd.value = None; eos_payable_dd.value = None
        error_text.visible = False

    def open_add(e=None):
        clear_form()
        editing_id['value'] = None
        dialog.title = ft.Text('عقد عمل جديد')
        dialog.open = True
        page.update()

    def open_edit(contract_id):
        c = services.get_contract(contract_id)
        if not c:
            page.overlay.append(ft.SnackBar(ft.Text('العقد غير موجود'), open=True)); page.update()
            return
        editing_id['value'] = contract_id
        emp_dd.value = str(c.employee_id)
        type_dd.value = c.contract_type
        start_field.value = c.start_date.strftime('%Y-%m-%d') if c.start_date else ''
        end_field.value = c.end_date.strftime('%Y-%m-%d') if c.end_date else ''
        basic_field.value = f'{c.basic_salary:g}'
        basic_account_dd.value = str(c.basic_salary_account_id) if c.basic_salary_account_id else None
        housing_field.value = f'{c.housing_allowance:g}'
        housing_account_dd.value = str(c.housing_allowance_account_id) if c.housing_allowance_account_id else None
        transport_field.value = f'{c.transport_allowance:g}'
        transport_account_dd.value = str(c.transport_allowance_account_id) if c.transport_allowance_account_id else None
        other_field.value = f'{c.other_allowances:g}'
        other_account_dd.value = str(c.other_allowances_account_id) if c.other_allowances_account_id else None
        gosi_field.value = f'{c.gosi_rate_employee:g}'
        gosi_account_dd.value = str(c.gosi_deduction_account_id) if c.gosi_deduction_account_id else None
        other_ded_account_dd.value = str(c.other_deductions_account_id) if c.other_deductions_account_id else None
        gosi_employer_field.value = f'{c.gosi_rate_employer:g}'
        gosi_employer_expense_dd.value = str(c.gosi_employer_expense_account_id) if c.gosi_employer_expense_account_id else None
        gosi_employer_payable_dd.value = str(c.gosi_employer_payable_account_id) if c.gosi_employer_payable_account_id else None
        leave_field.value = f'{c.leave_provision_rate:g}'
        leave_expense_dd.value = str(c.leave_provision_expense_account_id) if c.leave_provision_expense_account_id else None
        leave_payable_dd.value = str(c.leave_provision_payable_account_id) if c.leave_provision_payable_account_id else None
        eos_field.value = f'{c.eos_provision_rate:g}'
        eos_expense_dd.value = str(c.eos_provision_expense_account_id) if c.eos_provision_expense_account_id else None
        eos_payable_dd.value = str(c.eos_provision_payable_account_id) if c.eos_provision_payable_account_id else None
        error_text.visible = False
        dialog.title = ft.Text(f'تعديل العقد {c.contract_number}')
        dialog.open = True
        page.update()

    def save(e):
        try:
            if not emp_dd.value:
                raise ValueError('اختر الموظف')
            start_date = datetime.datetime.strptime(start_field.value, '%Y-%m-%d')
            end_date = datetime.datetime.strptime(end_field.value, '%Y-%m-%d') if end_field.value else None
            kwargs = dict(
                employee_id=int(emp_dd.value), start_date=start_date, basic_salary=float(basic_field.value or 0),
                housing_allowance=float(housing_field.value or 0), transport_allowance=float(transport_field.value or 0),
                other_allowances=float(other_field.value or 0), contract_type=type_dd.value,
                end_date=end_date, gosi_rate_employee=float(gosi_field.value or 0),
                gosi_rate_employer=float(gosi_employer_field.value or 0),
                leave_provision_rate=float(leave_field.value or 0), eos_provision_rate=float(eos_field.value or 0),
                basic_salary_account_id=int(basic_account_dd.value) if basic_account_dd.value else None,
                housing_allowance_account_id=int(housing_account_dd.value) if housing_account_dd.value else None,
                transport_allowance_account_id=int(transport_account_dd.value) if transport_account_dd.value else None,
                other_allowances_account_id=int(other_account_dd.value) if other_account_dd.value else None,
                gosi_deduction_account_id=int(gosi_account_dd.value) if gosi_account_dd.value else None,
                other_deductions_account_id=int(other_ded_account_dd.value) if other_ded_account_dd.value else None,
                gosi_employer_expense_account_id=int(gosi_employer_expense_dd.value) if gosi_employer_expense_dd.value else None,
                gosi_employer_payable_account_id=int(gosi_employer_payable_dd.value) if gosi_employer_payable_dd.value else None,
                leave_provision_expense_account_id=int(leave_expense_dd.value) if leave_expense_dd.value else None,
                leave_provision_payable_account_id=int(leave_payable_dd.value) if leave_payable_dd.value else None,
                eos_provision_expense_account_id=int(eos_expense_dd.value) if eos_expense_dd.value else None,
                eos_provision_payable_account_id=int(eos_payable_dd.value) if eos_payable_dd.value else None,
            )
            if editing_id['value']:
                services.update_contract(editing_id['value'], **kwargs)
            else:
                services.create_contract(**kwargs)
            dialog.open = False
            refresh()
        except Exception as ex:
            error_text.value = str(ex)
            error_text.visible = True
            page.update()

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def _d(v):
        v = (v or '').strip()
        return datetime.datetime.strptime(v, '%Y-%m-%d') if v else None

    # ----------------------------------------------------------- إنهاء
    def open_terminate(contract_id):
        c = services.get_contract(contract_id)
        tdate = theme.DateField('تاريخ الإنهاء', page, width=180, value=datetime.date.today().strftime('%Y-%m-%d'))
        reason_f = ft.TextField(label='سبب الإنهاء *', width=420, multiline=True, min_lines=2, max_lines=3)
        terr = ft.Text('', color=theme.DANGER, visible=False)

        def confirm(e):
            try:
                if not (reason_f.value or '').strip():
                    raise ValueError('اكتب سبب الإنهاء')
                services.terminate_contract(contract_id, _d(tdate.value), reason_f.value)
                tdlg.open = False; refresh(); snack('تم إنهاء العقد'); page.update()
            except Exception as ex:
                terr.value = str(ex); terr.visible = True; page.update()

        tdlg = ft.AlertDialog(
            modal=True, title=ft.Text(f'إنهاء العقد {c.contract_number}'),
            content=ft.Container(width=460, content=ft.Column([
                ft.Text(f'الموظف: {c.employee.name if c.employee else "-"}  |  الراتب الإجمالي: {c.gross_salary:,.2f}', size=13),
                ft.Text('العقد بيتقفل من الرواتب بعد تاريخ الإنهاء، وآخر شهر قبله بيتحسب عادي. لو الموظف مستقيل أو منتهية خدمته، '
                        'اعمل بعدها تسوية نهاية الخدمة من شاشتها.', size=12, color=theme.TEXT_MUTED),
                tdate.control, reason_f, terr,
            ], tight=True, spacing=12)),
            actions=[ft.TextButton('إلغاء', on_click=lambda e: (setattr(tdlg, 'open', False), page.update())),
                     ft.FilledButton('تأكيد الإنهاء', icon=ft.Icons.CANCEL_OUTLINED, bgcolor=theme.DANGER, on_click=confirm)],
        )
        page.overlay.append(tdlg); tdlg.open = True; page.update()

    # ----------------------------------------------------------- تجديد
    def open_renew(contract_id):
        c = services.get_contract(contract_id)
        default_start = (c.end_date + datetime.timedelta(days=1)) if c.end_date else datetime.datetime.now()
        default_end = None
        if c.contract_type == 'temporary' and c.start_date and c.end_date:
            default_end = default_start + (c.end_date - c.start_date)   # نفس مدة العقد السابق
        start_f = theme.DateField('بداية العقد الجديد', page, width=180, value=default_start.strftime('%Y-%m-%d'))
        end_f = theme.DateField('نهاية العقد الجديد' + (' *' if c.contract_type == 'temporary' else ' (اختياري)'), page, width=200,
                                value=default_end.strftime('%Y-%m-%d') if default_end else '')
        mode_rg = ft.RadioGroup(value='none', content=ft.Column([
            ft.Radio(value='none', label='تجديد بنفس الرواتب (من غير زيادة)'),
            ft.Radio(value='percent', label='زيادة بنسبة %'),
            ft.Radio(value='amount', label='زيادة بمبلغ لكل بند'),
        ], spacing=0))
        pct_f = ft.TextField(label='نسبة الزيادة %', width=140, keyboard_type=ft.KeyboardType.NUMBER)
        comp_cbs = {k: ft.Checkbox(label=lbl, value=(k == 'basic')) for k, lbl, _a, _b in services._RAISE_COMPONENTS}
        pct_box = ft.Column([ft.Row([pct_f], spacing=10), ft.Text('تتطبق النسبة على:', size=12, color=theme.TEXT_MUTED),
                             ft.Row(list(comp_cbs.values()), wrap=True, spacing=8)], spacing=6, visible=False)
        amt_fs = {k: ft.TextField(label=f'زيادة {lbl}', width=150, keyboard_type=ft.KeyboardType.NUMBER) for k, lbl, _a, _b in services._RAISE_COMPONENTS}
        amt_box = ft.Row(list(amt_fs.values()), wrap=True, spacing=10, visible=False)
        note_f = ft.TextField(label='ملاحظة / سبب الزيادة (اختياري)', width=420)
        rerr = ft.Text('', color=theme.DANGER, visible=False, size=12)
        month_hint = ft.Text('', size=11, color=theme.WARNING, visible=False)
        prev_table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['البند', 'الحالي', 'الزيادة', 'بعد التجديد']], rows=[],
                                  heading_row_height=36, data_row_min_height=32)

        def collect():
            def num(f):
                try: return float((f.value or '').replace(',', '') or 0)
                except ValueError: raise ValueError('اكتب أرقام صحيحة في خانات الزيادة')
            return (mode_rg.value, num(pct_f), tuple(k for k, cb in comp_cbs.items() if cb.value), {k: num(f) for k, f in amt_fs.items()})

        def recalc(e=None):
            pct_box.visible = mode_rg.value == 'percent'
            amt_box.visible = mode_rg.value == 'amount'
            try:
                sd = _d(start_f.value)
                month_hint.visible = bool(sd and sd.day != 1)
                month_hint.value = 'بداية العقد مش أول الشهر - دورة رواتب الشهر ده هتاخد الراتب الجديد كامل (الحساب بالشهر مش بالأيام).'
            except ValueError:
                month_hint.visible = False
            try:
                mode, pct, comps, raises = collect()
                pv = services.preview_contract_renewal(contract_id, mode, pct, comps, raises)
                rerr.visible = False
                rows = [ft.DataRow(cells=[ft.DataCell(ft.Text(l['label'])), ft.DataCell(ft.Text(f"{l['old']:,.2f}")),
                                          ft.DataCell(ft.Text(f"+{l['raise']:,.2f}" if l['raise'] else '-', color=theme.SUCCESS if l['raise'] else theme.TEXT_MUTED)),
                                          ft.DataCell(ft.Text(f"{l['new']:,.2f}", weight=ft.FontWeight.BOLD))])
                        for l in pv['lines'] if l['old'] or l['raise']]
                rows.append(ft.DataRow(color=theme.PRIMARY_LIGHT, cells=[
                    ft.DataCell(ft.Text('الإجمالي', weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(f"{pv['old_total']:,.2f}", weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(f"+{pv['raise_total']:,.2f} ({pv['raise_pct_of_total']:.1f}%)" if pv['raise_total'] else '-', weight=ft.FontWeight.BOLD, color=theme.SUCCESS)),
                    ft.DataCell(ft.Text(f"{pv['new_total']:,.2f}", weight=ft.FontWeight.BOLD, color=theme.PRIMARY))]))
                prev_table.rows = rows
            except Exception as ex:
                rerr.value = str(ex); rerr.visible = True
            page.update()

        def confirm(e):
            try:
                mode, pct, comps, raises = collect()
                new_id = services.renew_contract(contract_id, _d(start_f.value), _d(end_f.value), mode, pct, comps, raises, note_f.value)
                rdlg.open = False; refresh()
                snack(f'تم تجديد العقد - العقد الجديد {services.get_contract(new_id).contract_number}'); page.update()
            except Exception as ex:
                rerr.value = str(ex); rerr.visible = True; page.update()

        mode_rg.on_change = recalc; pct_f.on_change = recalc; start_f.on_change = recalc
        for cb in comp_cbs.values(): cb.on_change = recalc
        for f in amt_fs.values(): f.on_change = recalc
        recalc()
        rdlg = ft.AlertDialog(
            modal=True, title=ft.Text(f'تجديد العقد {c.contract_number} - {c.employee.name if c.employee else ""}'),
            content=ft.Container(width=640, content=ft.Column([
                ft.Text('التجديد بينسخ كل شروط العقد الحالي (الرواتب والبدلات ونسب التأمينات والمخصصات وكل الحسابات) في عقد جديد، '
                        'وأي زيادة بتتطبق على العقد الجديد بس. العقد الحالي بيتقفل كـ"مجدَّد" وبيفضل محفوظ بكل رواتبه في سجل الموظف.',
                        size=12, color=theme.TEXT_MUTED),
                ft.Row([start_f.control, end_f.control], wrap=True, spacing=12), month_hint,
                ft.Text('الزيادة', weight=ft.FontWeight.BOLD), mode_rg, pct_box, amt_box, note_f,
                ft.Divider(), ft.Text('معاينة الرواتب بعد التجديد', weight=ft.FontWeight.BOLD), theme.h_scroll(prev_table), rerr,
            ], tight=True, spacing=10, scroll=ft.ScrollMode.AUTO, height=520)),
            actions=[ft.TextButton('إلغاء', on_click=lambda e: (setattr(rdlg, 'open', False), page.update())),
                     ft.FilledButton('تأكيد التجديد', icon=ft.Icons.AUTORENEW, bgcolor=theme.PRIMARY, on_click=confirm)],
        )
        page.overlay.append(rdlg); rdlg.open = True; page.update()

    # ----------------------------------------------------------- سجل العقود
    def open_history(employee_id):
        hist = services.contract_history(employee_id)
        emp = next((e for e in employees if e.id == employee_id), None)
        def fmt_d(d): return d.strftime('%Y-%m-%d') if d else '-'
        rows = []
        for h in hist:
            raise_txt = f"+{h['raise_amount']:,.2f} ({h['raise_pct']:.1f}%)" if h['raise_amount'] else ('بدون زيادة' if h['renewal_count'] else '-')
            rows.append(ft.DataRow(color=theme.PRIMARY_LIGHT if h['state'] == 'active' else None, cells=[
                ft.DataCell(ft.Text(h['number'], weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(h['state_label'], color=STATE_COLORS.get(h['state']), weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(fmt_d(h['start_date']))), ft.DataCell(ft.Text(fmt_d(h['end_date']))),
                ft.DataCell(ft.Text(f"{h['basic']:,.2f}")), ft.DataCell(ft.Text(f"{h['gross']:,.2f}", weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(f"{h['previous_gross']:,.2f}" if h['previous_gross'] else '-', color=theme.TEXT_MUTED)),
                ft.DataCell(ft.Text(raise_txt, color=theme.SUCCESS if h['raise_amount'] else theme.TEXT_MUTED)),
                ft.DataCell(ft.Text(h['raise_note'] or (f"إنهاء: {h['termination_reason']}" if h['termination_reason'] else '-'), size=11)),
            ]))
        tbl = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['العقد', 'الحالة', 'من', 'إلى', 'الأساسي', 'الإجمالي', 'الإجمالي السابق', 'الزيادة', 'ملاحظات']],
                           rows=rows, heading_row_height=38)
        hdlg = ft.AlertDialog(
            modal=True, title=ft.Text(f'سجل عقود {emp.name if emp else ""}'),
            content=ft.Container(width=900, content=ft.Column([theme.h_scroll(tbl)], tight=True, scroll=ft.ScrollMode.AUTO, height=360)),
            actions=[ft.TextButton('إغلاق', on_click=lambda e: (setattr(hdlg, 'open', False), page.update()))],
        )
        page.overlay.append(hdlg); hdlg.open = True; page.update()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text('عقد عمل جديد'),
        content=ft.Container(
            width=650,
            content=ft.Column(
                [
                    ft.Text(
                        'إضافة عقد جديد لموظف يحوّل أي عقد سابق نشط له إلى "منتهي" تلقائياً. '
                        'كل عنصر (راتب أساسي / بدل / خصم) لازم يكون له حساب مستقل من شجرة الحسابات - '
                        'وده بيسمح إن كل موظف يترحّل على حسابات مختلفة حسب قسمه.',
                        color=theme.TEXT_MUTED,
                    ),
                    ft.Row([emp_dd.control, type_dd], wrap=True),
                    ft.Row([start_field.control, end_field.control], wrap=True),
                    ft.Divider(),
                    ft.Text('الراتب الأساسي', size=13, weight=ft.FontWeight.BOLD),
                    ft.Row([basic_field, basic_account_dd.control], wrap=True),
                    ft.Divider(),
                    ft.Text('البدلات (الحساب مطلوب فقط لو القيمة أكبر من صفر)', size=13, weight=ft.FontWeight.BOLD),
                    ft.Row([housing_field, housing_account_dd.control], wrap=True),
                    ft.Row([transport_field, transport_account_dd.control], wrap=True),
                    ft.Row([other_field, other_account_dd.control], wrap=True),
                    ft.Divider(),
                    ft.Text('الخصومات', size=13, weight=ft.FontWeight.BOLD),
                    ft.Row([gosi_field, gosi_account_dd.control], wrap=True),
                    other_ded_account_dd.control,
                    ft.Divider(),
                    ft.Text('المخصصات والتأمينات (للاستخدام في دورة المخصصات والتأمينات المنفصلة - حساب مطلوب فقط لو النسبة أكبر من صفر)', size=13, weight=ft.FontWeight.BOLD, color=theme.PRIMARY),
                    ft.Row([gosi_employer_field], wrap=True),
                    ft.Row([gosi_employer_expense_dd.control, gosi_employer_payable_dd.control], wrap=True),
                    ft.Row([leave_field], wrap=True),
                    ft.Row([leave_expense_dd.control, leave_payable_dd.control], wrap=True),
                    ft.Row([eos_field], wrap=True),
                    ft.Row([eos_expense_dd.control, eos_payable_dd.control], wrap=True),
                    error_text,
                ],
                spacing=10, tight=True, scroll=ft.ScrollMode.AUTO,
            ),
            height=560,
        ),
        actions=[
            ft.TextButton('إلغاء', on_click=close_dialog),
            ft.FilledButton('حفظ العقد', bgcolor=theme.PRIMARY, on_click=save),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(dialog)

    emp_filter.on_change = refresh
    refresh()

    header = ft.Row(
        [
            theme.page_title('العقود', 'إدارة عقود العمل والرواتب التعاقدية'),
            ft.Container(expand=True),
            emp_filter,
            ft.FilledButton('عقد جديد', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=open_add),
        ],
    )

    return ft.Column(
        [header, ft.Container(height=8), expiry_note, ft.Container(height=8),
         theme.card(theme.h_scroll(table, vscroll=True), expand=True)],
        expand=True,
    )
