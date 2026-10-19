import os
import flet as ft
from ._approval import prompt as approval_prompt
from .. import services, theme
from ..report_export import export_excel, export_pdf


def build_receipts_payments(page: ft.Page):
    customers=services.list_customers(); suppliers=services.list_suppliers(); employees=services.list_employees(); accounts=services.list_accounts(postable_only=True)
    cash=[a for a in accounts if a.account_type=='asset' and (a.code.startswith('11') or 'نقد' in a.name or 'بنك' in a.name)] or [a for a in accounts if a.account_type=='asset']
    typ=ft.Dropdown(label='النوع',width=170,options=[ft.dropdown.Option(key='receipt',text='سند قبض'),ft.dropdown.Option(key='payment',text='سند صرف')],value='receipt')
    party_type=ft.Dropdown(label='نوع الطرف',width=150,options=[
        ft.dropdown.Option(key='customer',text='عميل'), ft.dropdown.Option(key='supplier',text='مورد'), ft.dropdown.Option(key='employee',text='موظف'),
    ],value='customer')
    party=theme.SearchableDropdown(label='الطرف',width=280,options=[])
    counterdd=theme.SearchableDropdown(label='حساب الطرف (الافتراضي - يمكن تغييره)',width=320,options=[(str(a.id),f'{a.code} - {a.name}') for a in accounts])
    cashdd=theme.SearchableDropdown(label='النقدية / البنك',width=300,options=[(str(a.id),f'{a.code} - {a.name}') for a in cash],value=str(cash[0].id) if cash else None)
    branches=services.list_branches(True); allowed=services.user_branch_ids(); branches=[b for b in branches if not allowed or b.id in allowed]; centers=services.list_cost_centers(True)
    branchdd=ft.Dropdown(label='الفرع',width=220,options=[ft.dropdown.Option(str(b.id),f'{b.code} - {b.name}') for b in branches],value=str(services.default_branch_id()) if services.default_branch_id() else None)
    centerdd=ft.Dropdown(label='مركز التكلفة',width=220,options=[ft.dropdown.Option(str(c.id),f'{c.code} - {c.name}') for c in centers],value=str(services.default_cost_center_id()) if services.default_cost_center_id() else None)
    amount=ft.TextField(label='المبلغ',width=160,keyboard_type=ft.KeyboardType.NUMBER)
    from .. import fx as _fx
    _curs=_fx.list_currencies(active_only=True)
    cur_dd=ft.Dropdown(label='العملة',width=110,value=_fx.base_code(),options=[ft.dropdown.Option(c.code,c.code) for c in _curs],visible=len(_curs)>1)
    rate_f=ft.TextField(label='سعر الصرف',width=120,keyboard_type=ft.KeyboardType.NUMBER,visible=False)
    def on_cur(e=None):
        rate_f.visible=_fx.is_foreign(cur_dd.value)
        if rate_f.visible:
            try: rate_f.value=f"{_fx.get_rate(cur_dd.value):g}"
            except ValueError: rate_f.value=''
        page.update()
    cur_dd.on_select=on_cur
    ref=ft.TextField(label='المرجع',width=180); notes=ft.TextField(label='ملاحظات',width=260)
    err=ft.Text('',color=theme.DANGER,visible=False)
    names_cache={}
    def _payment_row(p):
        type_label='قبض' if p.payment_type=='receipt' else 'صرف'
        party_name=names_cache.get((p.partner_type, p.partner_id),'-')
        account_text=f'{p.account.code} - {p.account.name}'
        status_text = 'ملغى' if p.voided else 'سارٍ'
        status_color = theme.DANGER if p.voided else theme.SUCCESS
        actions = ft.Row(spacing=2)
        actions.controls.append(ft.IconButton(icon=ft.Icons.VISIBILITY_OUTLINED, tooltip='معاينة', on_click=lambda e, pid=p.id: do_preview_voucher(pid)))
        actions.controls.append(ft.IconButton(icon=ft.Icons.PRINT_OUTLINED, tooltip='طباعة', on_click=lambda e, pid=p.id: do_print_voucher(pid)))
        if not p.voided:
            actions.controls.append(ft.IconButton(icon=ft.Icons.CANCEL_OUTLINED, icon_color=theme.DANGER, tooltip='إلغاء',
                                                    on_click=lambda e, pid=p.id, num=p.number: do_void_voucher(pid, num)))
        return ft.DataRow(cells=[ft.DataCell(ft.Text(p.number)),ft.DataCell(ft.Text(p.date.strftime('%Y-%m-%d'))),ft.DataCell(ft.Text(type_label)),ft.DataCell(ft.Text(party_name)),ft.DataCell(ft.Text(f'{p.amount:,.2f}')),ft.DataCell(ft.Text(account_text)),ft.DataCell(ft.Text(status_text, color=status_color, weight=ft.FontWeight.BOLD)),ft.DataCell(actions)])

    table_sortable=theme.SortableDataTable(
        columns=[('الرقم', lambda p: p.number), ('التاريخ', lambda p: p.date), ('النوع', lambda p: p.payment_type),
                 ('الطرف', lambda p: names_cache.get((p.partner_type, p.partner_id), '')), ('المبلغ', lambda p: p.amount, True),
                 ('الحساب', lambda p: p.account.name if p.account else ''), ('الحالة', lambda p: p.voided), ('', None)],
        row_builder=_payment_row, page=page,
    )
    table=table_sortable.control
    state={'rows':[]}
    def refresh_party(e=None):
        data = {'customer': customers, 'supplier': suppliers, 'employee': employees}.get(party_type.value, customers)
        party.options=[(str(x.id),x.name) for x in data]; party.value=str(data[0].id) if data else None; set_counter_default(); page.update()

    def set_counter_default(e=None):
        """يحط حساب الطرف الافتراضي حسب النوع والطرف المختار (المستخدم يقدر يغيّره بعدها)."""
        try:
            acc=services.default_counter_account(party_type.value, int(party.value) if party.value else None, typ.value)
        except Exception:
            acc=None
        counterdd.value=str(acc) if acc else None
        try: page.update()
        except Exception: pass

    def do_print_voucher(payment_id):
        try:
            path = services.generate_payment_pdf_file(payment_id)
            theme.open_or_download_file(page, path)
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذرت الطباعة: {ex}'), open=True)); page.update()

    def do_preview_voucher(payment_id):
        """معاينة السند (البيانات + القيد المحاسبي) قبل الطباعة، وفيها زر طباعة."""
        try:
            d=services.payment_voucher_details(payment_id)
            is_r=d['type']=='receipt'
            def kv(k,v): return ft.Row([ft.Text(k,size=12,color=theme.TEXT_MUTED,width=110),ft.Text(str(v),size=13,weight=ft.FontWeight.W_600,selectable=True)],spacing=8)
            info=[kv('رقم السند',d['number']),kv('التاريخ',d['date'].strftime('%Y-%m-%d')),kv('الطرف',d['party']),kv('المبلغ',f"{d['amount']:,.2f}"),kv('النقدية / البنك',d['cash_account'])]
            if d['currency'] and d['foreign_amount']: info.append(kv('بالعملة الأجنبية',f"{d['foreign_amount']:,.2f} {d['currency']} (سعر {d['exchange_rate']:g})"))
            if d['reference']: info.append(kv('المرجع',d['reference']))
            if d['notes']: info.append(kv('ملاحظات',d['notes']))
            if d['voided']: info.append(ft.Text('هذا السند ملغى',color=theme.DANGER,weight=ft.FontWeight.BOLD))
            jt=ft.DataTable(columns=[ft.DataColumn(ft.Text('الحساب')),ft.DataColumn(ft.Text('مدين'),numeric=True),ft.DataColumn(ft.Text('دائن'),numeric=True)],
                            rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(l['account'])),ft.DataCell(ft.Text(f"{l['debit']:,.2f}" if l['debit'] else '')),ft.DataCell(ft.Text(f"{l['credit']:,.2f}" if l['credit'] else ''))]) for l in d['lines']],
                            heading_row_height=36,data_row_min_height=32)
            dlg=ft.AlertDialog(modal=True,title=ft.Text(('سند قبض ' if is_r else 'سند صرف ')+d['number']))
            def close(e=None): dlg.open=False; page.update()
            def pr(e=None): do_print_voucher(payment_id)
            dlg.content=ft.Container(ft.Column(info+[ft.Divider(),ft.Text('القيد المحاسبي',size=13,weight=ft.FontWeight.BOLD),ft.Row([jt],scroll=ft.ScrollMode.AUTO)],spacing=6,scroll=ft.ScrollMode.AUTO,tight=True),width=560,height=min(460,max(260,int(page.height or 700)-240)))
            dlg.actions=[ft.TextButton('إغلاق',on_click=close),ft.ElevatedButton('طباعة',icon=ft.Icons.PRINT_OUTLINED,on_click=pr,bgcolor=theme.PRIMARY,color='#FFFFFF')]
            page.overlay.append(dlg); dlg.open=True; page.update()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذرت المعاينة: {ex}'), open=True)); page.update()

    def do_void_voucher(payment_id, number):
        def confirm(e):
            try:
                services.void_payment(payment_id)
                void_dialog.open = False
                page.update()
                refresh()
            except Exception as ex:
                void_err.value = str(ex); void_err.visible = True; page.update()

        void_err = ft.Text('', color=theme.DANGER, visible=False)
        void_dialog = ft.AlertDialog(
            modal=True, title=ft.Text('تأكيد الإلغاء'),
            content=ft.Column([ft.Text(f'هل تريد إلغاء السند {number}؟'), void_err], tight=True),
            actions=[
                ft.TextButton('تراجع', on_click=lambda e: (setattr(void_dialog, 'open', False), page.update())),
                ft.FilledButton('تأكيد الإلغاء', bgcolor=theme.DANGER, on_click=confirm),
            ],
        )
        page.overlay.append(void_dialog)
        void_dialog.open = True
        page.update()

    def refresh():
        names_cache.clear()
        for x in customers: names_cache[('customer', x.id)] = x.name
        for x in suppliers: names_cache[('supplier', x.id)] = x.name
        for x in employees: names_cache[('employee', x.id)] = x.name
        for r in services.list_payroll_runs():
            names_cache[('payroll', r.id)] = f'صرف رواتب {r.month}/{r.year}'
        payments = services.list_payments()
        table_sortable.set_data(payments)
        state['rows'] = [{'number': p.number, 'date': p.date.strftime('%Y-%m-%d'),
                          'type': 'قبض' if p.payment_type == 'receipt' else 'صرف',
                          'party': names_cache.get((p.partner_type, p.partner_id), '-'),
                          'amount': p.amount, 'account': f'{p.account.code} - {p.account.name}'} for p in payments]
    def do_export(kind):
        try:
            exports_dir=services.downloads_dir()
            path=(export_excel if kind=='xlsx' else export_pdf)({'rows':state['rows']},'receipts_payments',exports_dir)
            theme.open_or_download_file(page, path)
            page.overlay.append(ft.SnackBar(ft.Text(f'تم إنشاء الملف: {path}'), open=True)); page.update()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()
    def save(e, after=None):
        try:
            if not party.value: raise ValueError('اختر الطرف')
            if not cashdd.value: raise ValueError('اختر حساب النقدية أو البنك')
            if not counterdd.value: raise ValueError('اختر حساب الطرف')
            if typ.value=='receipt': pid=services.create_receipt(int(party.value),float(amount.value or 0),int(cashdd.value),reference=ref.value,notes=notes.value,**({'currency':cur_dd.value,'exchange_rate':rate_f.value} if _fx.is_foreign(cur_dd.value) else {}),branch_id=int(branchdd.value) if branchdd.value else None,cost_center_id=int(centerdd.value) if centerdd.value else None,partner_type=party_type.value,counter_account_id=int(counterdd.value))
            else: pid=services.create_payment(int(party.value),float(amount.value or 0),int(cashdd.value),reference=ref.value,notes=notes.value,**({'currency':cur_dd.value,'exchange_rate':rate_f.value} if _fx.is_foreign(cur_dd.value) else {}),branch_id=int(branchdd.value) if branchdd.value else None,cost_center_id=int(centerdd.value) if centerdd.value else None,partner_type=party_type.value,counter_account_id=int(counterdd.value))
            amount.value=''; ref.value=''; notes.value=''; err.visible=False; refresh()
            if after: after(pid)
        except Exception as ex: err.value=str(ex); err.visible=True; page.update(); approval_prompt(page, ex)

    def on_type_change(e):
        party_type.value = 'customer' if typ.value == 'receipt' else 'supplier'
        refresh_party()

    party.on_change=set_counter_default; typ.on_select=on_type_change; party_type.on_select=refresh_party; refresh_party(); refresh()
    return ft.Column([
        theme.page_title('سندات القبض والصرف','تحصيل العملاء وسداد الموردين وسلف/تسويات الموظفين مع قيد محاسبي تلقائي'),
        theme.card(ft.Column([ft.Row([typ,party_type,party.control,counterdd.control,cashdd.control,branchdd,centerdd],wrap=True),ft.Row([amount,cur_dd,rate_f,ref,notes,ft.FilledButton('حفظ السند',icon=ft.Icons.SAVE,bgcolor=theme.PRIMARY,on_click=save),ft.OutlinedButton('حفظ ومعاينة',icon=ft.Icons.PREVIEW_OUTLINED,on_click=lambda e:save(e,do_preview_voucher)),ft.OutlinedButton('حفظ وطباعة',icon=ft.Icons.PRINT_OUTLINED,on_click=lambda e:save(e,do_print_voucher))]),err],spacing=12)),
        ft.Container(height=12),
        theme.card(ft.Column([
            ft.Row([ft.Text('سجل السندات',size=16,weight=ft.FontWeight.BOLD),ft.Container(expand=True),
                    ft.ElevatedButton('Excel',icon=ft.Icons.TABLE_VIEW,on_click=lambda e:do_export('xlsx')),
                    ft.ElevatedButton('PDF',icon=ft.Icons.PICTURE_AS_PDF,on_click=lambda e:do_export('pdf'))]),
            theme.h_scroll(table),
        ]),expand=True),
    ],expand=True,scroll=ft.ScrollMode.AUTO)
