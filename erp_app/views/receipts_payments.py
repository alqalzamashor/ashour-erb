import os
import flet as ft
from ._approval import prompt as approval_prompt
from .. import services, theme, drafts
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
    counter_cache={}
    def _payment_row(p):
        type_label='قبض' if p.payment_type=='receipt' else 'صرف'
        party_name=names_cache.get((p.partner_type, p.partner_id),'-')
        account_text=f'{p.account.code} - {p.account.name}'
        status_text = 'ملغى' if p.voided else 'ساري'
        status_color = theme.DANGER if p.voided else theme.SUCCESS
        actions = ft.Row(spacing=2)
        actions.controls.append(ft.IconButton(icon=ft.Icons.VISIBILITY_OUTLINED, tooltip='معاينة', on_click=lambda e, pid=p.id: do_preview_voucher(pid)))
        actions.controls.append(ft.IconButton(icon=ft.Icons.PRINT_OUTLINED, tooltip='طباعة', on_click=lambda e, pid=p.id: do_print_voucher(pid)))
        if not p.voided and p.partner_type!='payroll':
            actions.controls.append(ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل', on_click=lambda e, pid=p.id: do_edit_voucher(pid)))
        if not p.voided:
            actions.controls.append(ft.IconButton(icon=ft.Icons.CANCEL_OUTLINED, icon_color=theme.DANGER, tooltip='إلغاء',
                                                    on_click=lambda e, pid=p.id, num=p.number: do_void_voucher(pid, num)))
        return ft.DataRow(cells=[ft.DataCell(ft.Text(p.number)),ft.DataCell(ft.Text(p.date.strftime('%Y-%m-%d'))),ft.DataCell(ft.Text(type_label)),ft.DataCell(ft.Text(party_name)),ft.DataCell(ft.Text(f'{p.amount:,.2f}')),ft.DataCell(ft.Text(account_text)),ft.DataCell(ft.Text(counter_cache.get(p.id,'-'))),ft.DataCell(theme.status_badge(status_text, status_color)),ft.DataCell(actions)])

    table_sortable=theme.SortableDataTable(
        columns=[('الرقم', lambda p: p.number), ('التاريخ', lambda p: p.date), ('النوع', lambda p: p.payment_type),
                 ('الطرف', lambda p: names_cache.get((p.partner_type, p.partner_id), '')), ('المبلغ', lambda p: p.amount, True),
                 ('النقدية / البنك', lambda p: p.account.name if p.account else ''), ('حساب الطرف', lambda p: counter_cache.get(p.id, '')), ('الحالة', lambda p: p.voided), ('', None)],
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

    def do_edit_voucher(payment_id):
        """تعديل سند قبض/صرف: نافذة بنفس حقول الإدخال، والحفظ بيعيد بناء القيد المحاسبي على نفس رقم السند."""
        try:
            d=services.payment_voucher_details(payment_id)
            if d['voided']: raise ValueError('السند ملغى - لا يمكن تعديله')
            if d['partner_type']=='payroll': raise ValueError('سند صرف الرواتب مش بيتعدّل من هنا - الغيه وأعد الصرف من تقرير الرواتب')
            is_r=d['type']=='receipt'
            e_ptype=ft.Dropdown(label='نوع الطرف',width=150,value=d['partner_type'] or ('customer' if is_r else 'supplier'),
                                options=[ft.dropdown.Option(key='customer',text='عميل'),ft.dropdown.Option(key='supplier',text='مورد'),ft.dropdown.Option(key='employee',text='موظف')])
            def _opts(pt):
                data={'customer':customers,'supplier':suppliers,'employee':employees}.get(pt,customers)
                return [(str(x.id),x.name) for x in data]
            e_party=theme.SearchableDropdown(label='الطرف',width=260,options=_opts(e_ptype.value),value=str(d['partner_id']) if d['partner_id'] else None)
            e_counter=theme.SearchableDropdown(label='حساب الطرف',width=300,options=[(str(a.id),f'{a.code} - {a.name}') for a in accounts],value=str(d['counter_account_id']) if d['counter_account_id'] else None)
            e_cash=theme.SearchableDropdown(label='النقدية / البنك',width=300,options=[(str(a.id),f'{a.code} - {a.name}') for a in accounts],value=str(d['cash_account_id']))
            e_branch=ft.Dropdown(label='الفرع',width=200,options=[ft.dropdown.Option(str(b.id),f'{b.code} - {b.name}') for b in branches],value=str(d['branch_id']) if d['branch_id'] else None)
            e_center=ft.Dropdown(label='مركز التكلفة',width=200,options=[ft.dropdown.Option(str(c.id),f'{c.code} - {c.name}') for c in centers],value=str(d['cost_center_id']) if d['cost_center_id'] else None)
            foreign=bool(d['currency'] and d['foreign_amount'])
            e_amount=ft.TextField(label='المبلغ'+(f" ({d['currency']})" if foreign else ''),width=150,keyboard_type=ft.KeyboardType.NUMBER,value=f"{(d['foreign_amount'] if foreign else d['amount']):g}")
            e_date=theme.DateField('التاريخ',page,width=160,value=d['date'].strftime('%Y-%m-%d'))
            e_ref=ft.TextField(label='المرجع',width=180,value=d['reference']); e_notes=ft.TextField(label='ملاحظات',width=300,value=d['notes'])
            e_err=ft.Text('',color=theme.DANGER,visible=False)
            def on_pt(e=None):
                e_party.options=_opts(e_ptype.value); e_party.value=None; e_counter.value=None; page.update()
            e_ptype.on_select=on_pt
            def on_party(e=None):
                try:
                    acc=services.default_counter_account(e_ptype.value,int(e_party.value) if e_party.value else None,d['type'])
                    e_counter.value=str(acc) if acc else None; page.update()
                except Exception: pass
            e_party.on_change=on_party
            dlg=ft.AlertDialog(modal=True,title=ft.Text(('تعديل سند قبض ' if is_r else 'تعديل سند صرف ')+d['number']))
            def close(e=None): dlg.open=False; page.update()
            def do_save(e=None):
                try:
                    if not e_party.value: raise ValueError('اختر الطرف')
                    if not e_cash.value: raise ValueError('اختر حساب النقدية أو البنك')
                    if not e_counter.value: raise ValueError('اختر حساب الطرف')
                    import datetime as _dtm
                    dtv=_dtm.datetime.strptime(e_date.value,'%Y-%m-%d') if e_date.value else d['date']
                    if dtv.date()==d['date'].date(): dtv=d['date']          # نفس اليوم: نحافظ على الوقت الأصلي
                    services.update_payment(payment_id,int(e_party.value),float(e_amount.value or 0),int(e_cash.value),date=dtv,reference=e_ref.value,notes=e_notes.value,
                                            branch_id=int(e_branch.value) if e_branch.value else None,cost_center_id=int(e_center.value) if e_center.value else None,
                                            partner_type=e_ptype.value,counter_account_id=int(e_counter.value),
                                            **({'currency':d['currency'],'exchange_rate':d['exchange_rate']} if foreign else {}))
                    dlg.open=False; refresh()
                    page.overlay.append(ft.SnackBar(ft.Text('تم تعديل السند وإعادة بناء قيده'),open=True)); page.update()
                except Exception as ex:
                    e_err.value=str(ex); e_err.visible=True; page.update(); approval_prompt(page, ex)
            dlg.content=ft.Container(ft.Column([ft.Row([e_ptype,e_party.control],wrap=True),ft.Row([e_counter.control,e_cash.control],wrap=True),ft.Row([e_branch,e_center],wrap=True),
                                                ft.Row([e_amount,e_date.control],wrap=True),ft.Row([e_ref,e_notes],wrap=True),e_err],spacing=10,scroll=ft.ScrollMode.AUTO,tight=True),
                                     width=660,height=min(460,max(300,int(page.height or 700)-200)))
            dlg.actions=[ft.TextButton('إغلاق',on_click=close),ft.FilledButton('حفظ التعديل',icon=ft.Icons.SAVE,bgcolor=theme.PRIMARY,on_click=do_save)]
            page.overlay.append(dlg); dlg.open=True; page.update()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التعديل: {ex}'), open=True)); page.update()

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
        counter_cache.clear(); counter_cache.update(services.payment_counter_accounts(payments))
        table_sortable.set_data(payments)
        state['rows'] = [{'number': p.number, 'date': p.date.strftime('%Y-%m-%d'),
                          'type': 'قبض' if p.payment_type == 'receipt' else 'صرف',
                          'party': names_cache.get((p.partner_type, p.partner_id), '-'),
                          'amount': p.amount, 'account': f'{p.account.code} - {p.account.name}', 'counter': counter_cache.get(p.id, '-')} for p in payments]
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
            amount.value=''; ref.value=''; notes.value=''; err.visible=False; drafts.clear(DRAFT_KIND); banner.visible=False; refresh()
            if after: after(pid)
        except Exception as ex: err.value=str(ex); err.visible=True; page.update(); approval_prompt(page, ex)

    def on_type_change(e):
        party_type.value = 'customer' if typ.value == 'receipt' else 'supplier'
        refresh_party()

    # ---- مسودة تلقائية: اللي بتكتبه في النموذج بيتحفظ ويرجع لو الصفحة اتقفلت قبل الحفظ ----
    DRAFT_KIND='voucher'
    dstate={'on':True}
    banner_text=ft.Text('',color=theme.WARNING_TEXT,expand=True)
    banner=ft.Container(visible=False,padding=10,border_radius=8,bgcolor=theme.SURFACE_ALT,
        content=ft.Row([ft.Icon(ft.Icons.RESTORE,color=theme.WARNING_TEXT),banner_text,ft.TextButton('تجاهل المسودة',on_click=lambda e:discard_draft())],spacing=8))
    def collect_draft():
        return {'typ':typ.value,'party_type':party_type.value,'party':party.value or '','counter':counterdd.value or '','cash':cashdd.value or '',
                'branch':branchdd.value or '','center':centerdd.value or '','amount':amount.value or '','cur':cur_dd.value or '','rate':rate_f.value or '',
                'ref':ref.value or '','notes':notes.value or ''}
    def autosave_draft(e=None):
        if not dstate['on']: return
        d=collect_draft()
        if not (d['amount'].strip() or d['ref'].strip() or d['notes'].strip()): drafts.clear(DRAFT_KIND)
        else: drafts.save(DRAFT_KIND,d)
    def apply_draft(d,saved_at):
        dstate['on']=False
        try:
            typ.value=d.get('typ') or typ.value; party_type.value=d.get('party_type') or party_type.value
            refresh_party()
            if d.get('party'): party.value=d['party']
            if d.get('counter'): counterdd.value=d['counter']
            if d.get('cash'): cashdd.value=d['cash']
            if d.get('branch'): branchdd.value=d['branch']
            if d.get('center'): centerdd.value=d['center']
            amount.value=d.get('amount',''); ref.value=d.get('ref',''); notes.value=d.get('notes','')
            if d.get('cur'): cur_dd.value=d['cur']
            on_cur()
            if d.get('rate') and rate_f.visible: rate_f.value=d['rate']
            banner_text.value=f"اتسترجعت مسودة سند غير محفوظ (آخر حفظ {saved_at:%Y-%m-%d %H:%M}) - كمّل واحفظ، أو اضغط تجاهل."
            banner.visible=True
        finally: dstate['on']=True
    def discard_draft():
        drafts.clear(DRAFT_KIND); banner.visible=False
        amount.value=''; ref.value=''; notes.value=''; page.update()
    def _chain(old):
        def h(e=None):
            if old: old(e)
            autosave_draft()
        return h
    def on_party_change(e=None):
        set_counter_default(e); autosave_draft()
    party.on_change=on_party_change
    typ.on_select=lambda e:(on_type_change(e),autosave_draft())
    party_type.on_select=lambda e:(refresh_party(e),autosave_draft())
    for _c in (cashdd,counterdd): _c.on_change=autosave_draft
    for _c in (branchdd,centerdd): _c.on_select=autosave_draft
    cur_dd.on_select=lambda e:(on_cur(e),autosave_draft())
    for _c in (amount,ref,notes,rate_f): _c.on_change=autosave_draft
    refresh_party(); refresh()
    _saved=drafts.load(DRAFT_KIND)
    if _saved: apply_draft(*_saved)
    return ft.Column([
        theme.page_title('سندات القبض والصرف','تحصيل العملاء وسداد الموردين وسلف/تسويات الموظفين مع قيد محاسبي تلقائي'),
        theme.card(ft.Column([banner,ft.Row([typ,party_type,party.control,counterdd.control,cashdd.control,branchdd,centerdd],wrap=True),ft.Row([amount,cur_dd,rate_f,ref,notes,ft.FilledButton('حفظ السند',icon=ft.Icons.SAVE,bgcolor=theme.PRIMARY,on_click=save),ft.OutlinedButton('حفظ ومعاينة',icon=ft.Icons.PREVIEW_OUTLINED,on_click=lambda e:save(e,do_preview_voucher)),ft.OutlinedButton('حفظ وطباعة',icon=ft.Icons.PRINT_OUTLINED,on_click=lambda e:save(e,do_print_voucher))]),err],spacing=12)),
        ft.Container(height=12),
        theme.card(ft.Column([
            ft.Row([ft.Text('سجل السندات',size=16,weight=ft.FontWeight.BOLD),ft.Container(expand=True),
                    ft.ElevatedButton('Excel',icon=ft.Icons.TABLE_VIEW,on_click=lambda e:do_export('xlsx')),
                    ft.ElevatedButton('PDF',icon=ft.Icons.PICTURE_AS_PDF,on_click=lambda e:do_export('pdf'))]),
            theme.h_scroll(table),
        ]),expand=True),
    ],expand=True,scroll=ft.ScrollMode.AUTO)
