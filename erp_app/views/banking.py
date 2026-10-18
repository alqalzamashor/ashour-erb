import datetime
import json
import flet as ft
from .. import services, theme, banking

STATUS_LABELS = {"pending": "معلّقة", "approved": "موافَق عليها", "declined": "مرفوضة", "failed": "فشلت", "paid": "مدفوعة", "expired": "منتهية", "orphaned": "تحتاج تراجع"}
STATUS_COLORS = {"approved": theme.SUCCESS, "paid": theme.SUCCESS, "pending": theme.WARNING, "declined": theme.DANGER, "failed": theme.DANGER, "orphaned": theme.DANGER}
LINE_LABELS = {"unmatched": "غير مطابق", "matched": "مطابق", "posted": "مُرحَّل بقيد", "ignored": "متجاهَل"}

HTTP_TEMPLATE = json.dumps({
    "base_url": "https://api.example-bank.com", "headers": {"Authorization": "Bearer YOUR_API_KEY"}, "currency": "SAR", "merchant_id": "", "terminal_id": "",
    "charge": {"path": "/v1/terminal/sale", "method": "POST", "body": {"amount": "{amount_minor}", "currency": "{currency}", "terminal": "{terminal}", "reference": "{reference}"},
               "ok_path": "status", "ok_values": ["approved"], "ref_path": "rrn", "last4_path": "card.last4", "message_path": "message"},
    "link": {"path": "/v1/payment-links", "body": {"amount": "{amount_minor}", "currency": "{currency}", "description": "{description}", "reference": "{reference}"}, "url_path": "url", "id_path": "id"},
    "status": {"path": "/v1/payment-links/{external_id}", "method": "GET", "paid_path": "status", "paid_values": ["paid"], "ref_path": "payment.rrn"},
}, ensure_ascii=False, indent=2)


def build_banking(page: ft.Page):
    tabs = theme.SimpleTabs(page)
    accounts = services.list_accounts(postable_only=True)
    acct_options = [(str(a.id), f'{a.code} - {a.name}') for a in accounts]
    customers = services.list_customers()

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def bank_options(blank=False):
        return ([('', 'بدون')] if blank else []) + [(str(b.id), f'{b.code} - {b.name}') for b in banking.list_bank_accounts(True)]

    # ======================================================= الحسابات البنكية
    def build_accounts_tab():
        code, name, bank_name, iban, swift, est = (ft.TextField(label=l, width=w) for l, w in [('كود', 110), ('اسم الحساب', 220), ('البنك', 180), ('الآيبان (SA...)', 280), ('SWIFT', 130), ('رقم المنشأة لدى البنك', 190)])
        gl = theme.SearchableDropdown(label='حساب شجرة الحسابات المرتبط', width=330, options=acct_options, page=page)
        err = ft.Text('', color=theme.DANGER, visible=False)
        editing = {'id': None}
        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['الكود', 'الحساب', 'البنك', 'الآيبان', 'حساب الأستاذ', 'الحالة', '']], rows=[])

        def refresh():
            rows = []
            for b in banking.list_bank_accounts():
                rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(b.code)), ft.DataCell(ft.Text(b.name, weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(b.bank_name or '-')), ft.DataCell(ft.Text(b.iban or '-', size=12)),
                    ft.DataCell(ft.Text(f'{b.account.code} - {b.account.name}', size=12)), ft.DataCell(ft.Text('نشط' if b.is_active else 'موقوف', color=theme.SUCCESS if b.is_active else theme.TEXT_MUTED)),
                    ft.DataCell(ft.Row([ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, on_click=lambda e, x=b: edit(x)), ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, on_click=lambda e, x=b: delete(x))], spacing=0))]))
            table.rows = rows

        def edit(b):
            editing['id'] = b.id
            code.value, name.value, bank_name.value, iban.value, swift.value, est.value, gl.value = b.code, b.name, b.bank_name, b.iban, b.swift, b.establishment_id, str(b.account_id)
            page.update()

        def delete(b):
            try:
                banking.delete_bank_account(b.id); refresh(); page.update()
            except Exception as ex:
                snack(str(ex))

        def save(e):
            try:
                banking.save_bank_account(code.value, name.value, gl.value, bank_name.value, iban.value, swift.value, est.value, bank_account_id=editing['id'])
                editing['id'] = None
                for f in (code, name, bank_name, iban, swift, est):
                    f.value = ''
                gl.value = None; err.visible = False; refresh(); page.update(); snack('تم الحفظ')
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()
        refresh()
        return ft.Column([theme.card(ft.Column([ft.Text('حساب بنكي', size=16, weight=ft.FontWeight.BOLD), ft.Row([code, name, bank_name, iban, swift, est, gl.control], wrap=True, spacing=10), err,
                                                 theme.guard_submit(ft.FilledButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save))], spacing=10)),
                          theme.card(theme.h_scroll(table))], spacing=14)

    # ======================================================= مزوّدو الدفع
    def build_providers_tab():
        name = ft.TextField(label='اسم المزوّد', width=220)
        kind = ft.Dropdown(label='النوع', width=340, options=[ft.dropdown.Option(k, v) for k, v in banking.PROVIDER_KINDS.items()], value='terminal_manual')
        bank = theme.SearchableDropdown(label='الحساب البنكي', width=280, options=bank_options(True), value='', page=page)
        cfg = ft.TextField(label='إعدادات الـ API (JSON) - للأنواع عبر API فقط', multiline=True, min_lines=6, max_lines=14, width=760, value='{}')
        hint = ft.TextButton('إدراج قالب API', on_click=lambda e: (setattr(cfg, 'value', HTTP_TEMPLATE), page.update()))
        err = ft.Text('', color=theme.DANGER, visible=False)
        editing = {'id': None}
        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['المزوّد', 'النوع', 'الحساب البنكي', 'الحالة', '']], rows=[])

        def refresh():
            rows = []
            for p in banking.list_providers():
                rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(p.name, weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(banking.PROVIDER_KINDS.get(p.kind, p.kind), size=12)),
                    ft.DataCell(ft.Text(p.bank_account.name if p.bank_account else '-')), ft.DataCell(ft.Text('نشط' if p.is_active else 'موقوف', color=theme.SUCCESS if p.is_active else theme.TEXT_MUTED)),
                    ft.DataCell(ft.Row([ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, on_click=lambda e, x=p: edit(x)),
                                        ft.IconButton(icon=ft.Icons.TOGGLE_ON_OUTLINED if p.is_active else ft.Icons.TOGGLE_OFF_OUTLINED, on_click=lambda e, x=p: toggle(x)),
                                        ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, on_click=lambda e, x=p: delete(x))], spacing=0))]))
            table.rows = rows

        def edit(p):
            editing['id'] = p.id; name.value, kind.value, bank.value, cfg.value = p.name, p.kind, str(p.bank_account_id or ''), p.config_json or '{}'; page.update()

        def toggle(p):
            try:
                banking.save_provider(p.name, p.kind, p.bank_account_id, p.config_json, not p.is_active, p.id); refresh(); page.update()
            except Exception as ex:
                snack(str(ex))

        def delete(p):
            try:
                banking.delete_provider(p.id); refresh(); page.update()
            except Exception as ex:
                snack(str(ex))

        def save(e):
            try:
                banking.save_provider(name.value, kind.value, bank.value or None, cfg.value, True, editing['id'])
                editing['id'] = None; name.value = ''; cfg.value = '{}'; err.visible = False; refresh(); page.update(); snack('تم الحفظ - اربط المزوّد بطريقة دفع من شاشة «طرق الدفع»')
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()
        refresh()
        return ft.Column([theme.card(ft.Column([ft.Text('مزوّد دفع', size=16, weight=ft.FontWeight.BOLD),
                                                 ft.Text('«جهاز شبكة» يعمل فورًا: الكاشير يدخل رقم الموافقة من الجهاز. أنواع الـ API محتاجة بيانات الدخول من البنك/المزوّد (تتحط في JSON).', size=12, color=theme.TEXT_MUTED),
                                                 ft.Row([name, kind, bank.control], wrap=True, spacing=10), cfg, hint, err,
                                                 theme.guard_submit(ft.FilledButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save))], spacing=10)),
                          theme.card(theme.h_scroll(table))], spacing=14)

    # ======================================================= العمليات وروابط الدفع
    def build_transactions_tab():
        prov = theme.SearchableDropdown(label='مزوّد (بوابة/تجريبي)', width=260, options=[(str(p.id), p.name) for p in banking.list_providers(True) if p.kind in ('online_http', 'mock')], page=page)
        cust = theme.SearchableDropdown(label='العميل', width=260, options=[(str(c.id), c.name) for c in customers], page=page)
        amount = ft.TextField(label='المبلغ', width=140, keyboard_type=ft.KeyboardType.NUMBER)
        desc = ft.TextField(label='البيان', width=260)
        err = ft.Text('', color=theme.DANGER, visible=False)
        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['#', 'التاريخ', 'المزوّد', 'النوع', 'العميل', 'المبلغ', 'المرجع', 'الحالة', 'الرابط', '']], rows=[])

        def check(t):
            try:
                r = banking.check_payment_link(t.id)
                snack('اتسدد وتم عمل سند القبض' if r.status == 'paid' else 'لسه ما اتسددش')
                refresh(); page.update()
            except Exception as ex:
                snack(str(ex))

        def refresh():
            rows = []
            for t in banking.list_transactions():
                acts = [ft.IconButton(icon=ft.Icons.SYNC, tooltip='تحقق من السداد', on_click=lambda e, x=t: check(x))] if t.kind == 'link' and t.status == 'pending' else []
                rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(str(t.id))), ft.DataCell(ft.Text(t.created_at.strftime('%Y-%m-%d %H:%M'))), ft.DataCell(ft.Text(t.provider.name if t.provider else '-')),
                    ft.DataCell(ft.Text('رابط دفع' if t.kind == 'link' else 'بطاقة')), ft.DataCell(ft.Text(t.customer.name if t.customer else '-')), ft.DataCell(ft.Text(f'{t.amount:,.2f}')),
                    ft.DataCell(ft.Text(t.reference or '-', size=12)), ft.DataCell(ft.Text(STATUS_LABELS.get(t.status, t.status), color=STATUS_COLORS.get(t.status, theme.TEXT_MUTED), weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.TextButton('فتح', on_click=lambda e, u=t.link_url: theme.launch_url(page, u)) if t.link_url else ft.Text('-')), ft.DataCell(ft.Row(acts, spacing=0))]))
            table.rows = rows

        def create(e):
            try:
                t = banking.create_payment_link(int(prov.value) if prov.value else None, amount.value, int(cust.value) if cust.value else None, desc.value)
                err.visible = False; amount.value = ''; refresh(); page.update()
                page.set_clipboard(t.link_url) if hasattr(page, 'set_clipboard') else None
                snack(f'تم إنشاء الرابط: {t.link_url}')
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()
        refresh()
        return ft.Column([theme.card(ft.Column([ft.Text('رابط دفع أونلاين لعميل', size=16, weight=ft.FontWeight.BOLD), ft.Row([prov.control, cust.control, amount, desc], wrap=True, spacing=10), err,
                                                 theme.guard_submit(ft.FilledButton('إنشاء الرابط', icon=ft.Icons.LINK, bgcolor=theme.PRIMARY, on_click=create))], spacing=10)),
                          theme.card(ft.Column([ft.Row([ft.Text('سجل عمليات الدفع البنكي', size=16, weight=ft.FontWeight.BOLD), ft.Container(expand=True), ft.TextButton('تحديث', icon=ft.Icons.REFRESH, on_click=lambda e: (refresh(), page.update()))]), theme.h_scroll(table)]))], spacing=14)

    # ======================================================= مطابقة كشف البنك
    def build_recon_tab():
        bank = theme.SearchableDropdown(label='الحساب البنكي', width=300, options=bank_options(), page=page)
        status_dd = ft.Dropdown(label='عرض', width=170, options=[ft.dropdown.Option('', 'الكل'), ft.dropdown.Option('unmatched', 'غير مطابق'), ft.dropdown.Option('matched', 'مطابق'), ft.dropdown.Option('posted', 'مُرحَّل'), ft.dropdown.Option('ignored', 'متجاهَل')], value='unmatched')
        summary = ft.Text('', size=13, weight=ft.FontWeight.BOLD)
        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['التاريخ', 'البيان', 'المرجع', 'سحب', 'إيداع', 'الحالة', '']], rows=[])
        pager = theme.RowPager(table, page, 100)

        def refresh(e=None):
            if not bank.value:
                return
            sm = banking.reconciliation_summary(int(bank.value))
            summary.value = (f"رصيد الأستاذ: {sm['gl_balance']:,.2f}" + (f" | رصيد الكشف: {sm['bank_balance']:,.2f} | الفرق: {sm['difference']:,.2f}" if sm['bank_balance'] is not None else '')
                             + f" | غير مطابق في الكشف: {sm['unmatched']} (إيداع {sm['unmatched_in']:,.2f} / سحب {sm['unmatched_out']:,.2f}) | في الأستاذ بدون كشف: {sm['gl_unmatched']}")
            pager.set_items(banking.list_statement_lines(int(bank.value), status_dd.value or None), lambda l: ft.DataRow(cells=[
                ft.DataCell(ft.Text(l.date.strftime('%Y-%m-%d'))), ft.DataCell(ft.Text(l.description or '-', size=12)), ft.DataCell(ft.Text(l.reference or '-', size=12)),
                ft.DataCell(ft.Text(f'{l.debit:,.2f}' if l.debit else '')), ft.DataCell(ft.Text(f'{l.credit:,.2f}' if l.credit else '')),
                ft.DataCell(ft.Text(LINE_LABELS.get(l.status, l.status), color=theme.SUCCESS if l.status in ('matched', 'posted') else theme.WARNING)),
                ft.DataCell(ft.Row(([ft.TextButton('قيد', tooltip='عمل قيد للسطر (رسوم/فوائد/إيداع)', on_click=lambda e, x=l: post_dialog(x)), ft.TextButton('تجاهل', on_click=lambda e, x=l: setst(x, 'ignored'))] if l.status == 'unmatched'
                                    else ([ft.TextButton('فك', on_click=lambda e, x=l: setst(x, 'unmatched'))] if l.status in ('matched', 'ignored') else [])), spacing=0))]), keep_page=False)
            page.update()

        def setst(l, st):
            try:
                banking.set_line_status(l.id, st); refresh()
            except Exception as ex:
                snack(str(ex))

        def post_dialog(l):
            acc = theme.SearchableDropdown(label='الحساب المقابل (مصروف رسوم، إيراد فوائد...)', width=380, options=acct_options, page=page)
            d = ft.TextField(label='البيان', width=380, value=l.description or '')
            er = ft.Text('', color=theme.DANGER, visible=False)

            def ok(e):
                try:
                    banking.post_statement_line(l.id, acc.value, d.value)
                    dlg.open = False; refresh()
                except Exception as ex:
                    er.value = str(ex); er.visible = True; page.update()
            dlg = ft.AlertDialog(modal=True, title=ft.Text(f"قيد لسطر {'إيداع' if l.credit else 'سحب'} {(l.credit or l.debit):,.2f}"), content=ft.Column([acc.control, d, er], tight=True, spacing=10, width=400),
                                 actions=[ft.TextButton('إلغاء', on_click=lambda e: (setattr(dlg, 'open', False), page.update())), ft.FilledButton('ترحيل', bgcolor=theme.PRIMARY, on_click=ok)])
            page.overlay.append(dlg); dlg.open = True; page.update()

        async def do_import(e):
            if not bank.value:
                return snack('اختر الحساب البنكي الأول')
            path = await theme.pick_file(page, 'اختر كشف حساب البنك', ['csv', 'xlsx'])
            if not path:
                return
            try:
                new, dup = banking.import_statement(int(bank.value), path)
                matched = banking.auto_match(int(bank.value))
                snack(f'تم استيراد {new} سطر ({dup} مكرر اتجاهل) - مطابقة تلقائية: {matched}'); refresh()
            except Exception as ex:
                snack(str(ex))

        def do_match(e):
            try:
                if not bank.value:
                    return
                snack(f'تمت مطابقة {banking.auto_match(int(bank.value))} سطر'); refresh()
            except Exception as ex:
                snack(str(ex))
        bank.on_change = refresh; status_dd.on_select = refresh
        return ft.Column([theme.card(ft.Column([ft.Row([bank.control, status_dd, ft.FilledButton('استيراد كشف (CSV/Excel)', icon=ft.Icons.UPLOAD_FILE, bgcolor=theme.PRIMARY, on_click=do_import),
                                                         ft.OutlinedButton('مطابقة تلقائية', icon=ft.Icons.AUTO_FIX_HIGH, on_click=do_match)], wrap=True, spacing=10), summary,
                                                 ft.Text('الملف لازم فيه عمود تاريخ وأعمدة مدين/دائن (أو مبلغ). العناوين بالعربي أو الإنجليزي بتتعرّف تلقائيًا.', size=12, color=theme.TEXT_MUTED)], spacing=10)),
                          theme.card(theme.h_scroll(table))], spacing=14)

    # ======================================================= ملفات التحويل
    def build_files_tab():
        bank = theme.SearchableDropdown(label='حساب الخصم (البنك)', width=300, options=bank_options(), page=page)
        runs = services.list_payroll_runs()
        run_dd = theme.SearchableDropdown(label='دورة الرواتب', width=300, options=[(str(r.id), f'{r.number} - {r.month:02d}/{r.year}') for r in runs], page=page)
        out = ft.Text('', size=13)
        err = ft.Text('', color=theme.DANGER, visible=False)
        sup_rows = []
        sup_col = ft.Column(spacing=6)

        def salary(e):
            try:
                if not bank.value or not run_dd.value:
                    raise ValueError('اختر حساب البنك ودورة الرواتب')
                xlsx, csv_, total, n = banking.export_salary_file(int(run_dd.value), int(bank.value))
                err.visible = False; out.value = f'تم إنشاء ملف الرواتب: {n} موظف بإجمالي {total:,.2f}\n{xlsx}\n{csv_}'
                theme.open_or_download_file(page, xlsx); page.update()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        def load_suppliers(e=None):
            sup_rows.clear(); sup_col.controls.clear()
            for sp in services.list_suppliers():
                bal = banking.supplier_balance(sp.id)
                if bal <= 0.005:
                    continue
                chk = ft.Checkbox(value=False); amt = ft.TextField(value=f'{bal:.2f}', width=130, dense=True, keyboard_type=ft.KeyboardType.NUMBER); ib = ft.TextField(value=sp.iban or '', width=260, dense=True, hint_text='SA...')
                sup_rows.append((sp, chk, amt, ib))
                sup_col.controls.append(ft.Row([chk, ft.Container(ft.Text(sp.name), width=220), ft.Text(f'المستحق {bal:,.2f}', width=130, size=12, color=theme.TEXT_MUTED), amt, ib], spacing=8))
            if not sup_rows:
                sup_col.controls.append(ft.Text('مفيش موردين عليهم أرصدة مستحقة.', color=theme.TEXT_MUTED))
            page.update()

        def suppliers(e):
            try:
                if not bank.value:
                    raise ValueError('اختر حساب البنك')
                items = [{'supplier_id': sp.id, 'amount': amt.value, 'iban': ib.value} for sp, chk, amt, ib in sup_rows if chk.value]
                xlsx, csv_, total, n = banking.export_supplier_transfers(items, int(bank.value))
                err.visible = False; out.value = f'تم إنشاء ملف تحويلات الموردين: {n} مورد بإجمالي {total:,.2f}\n{xlsx}\n{csv_}\nبعد تنفيذ التحويل في البنك سجّل سندات الصرف من شاشة «السندات».'
                theme.open_or_download_file(page, xlsx); page.update()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()
        return ft.Column([theme.card(ft.Column([ft.Text('ملف تحويل رواتب (WPS عام)', size=16, weight=ft.FontWeight.BOLD),
                                                 ft.Text('الآيبان بيتاخد من خانة «الحساب البنكي» في بيانات الموظف. لو فيه آيبان غلط بيتوقف التصدير وتظهر الأسماء.', size=12, color=theme.TEXT_MUTED),
                                                 ft.Row([bank.control, run_dd.control, ft.FilledButton('تصدير ملف الرواتب', icon=ft.Icons.DOWNLOAD, bgcolor=theme.PRIMARY, on_click=salary)], wrap=True, spacing=10)], spacing=10)),
                          theme.card(ft.Column([ft.Text('ملف تحويلات موردين', size=16, weight=ft.FontWeight.BOLD), ft.Row([ft.OutlinedButton('تحميل الموردين المستحقين', icon=ft.Icons.REFRESH, on_click=load_suppliers),
                                                                                                                         ft.FilledButton('تصدير ملف الموردين المحدَّدين', icon=ft.Icons.DOWNLOAD, bgcolor=theme.PRIMARY, on_click=suppliers)], spacing=10), sup_col], spacing=10)),
                          err, out], spacing=14)

    tabs.set_tabs([('الحسابات البنكية', build_accounts_tab()), ('مزوّدو الدفع', build_providers_tab()), ('عمليات وروابط الدفع', build_transactions_tab()),
                   ('مطابقة كشف البنك', build_recon_tab()), ('ملفات التحويل', build_files_tab())])
    return ft.Column([theme.page_title('الربط البنكي', 'حسابات البنوك، أجهزة الشبكة وبوابات الدفع، مطابقة الكشف، وملفات تحويل الرواتب والموردين'), ft.Container(height=10), tabs.control], expand=True, scroll=ft.ScrollMode.AUTO)
