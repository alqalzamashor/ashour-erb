import os, datetime
import flet as ft
from .. import services, theme
from ..report_export import export_excel, export_pdf


def build_party_reports(page: ft.Page):
    typ = ft.Dropdown(label='نوع الكشف', width=230,
                       options=[ft.dropdown.Option(key='customer', text='عميل'), ft.dropdown.Option(key='supplier', text='مورد')],
                       value='customer')
    party = theme.SearchableDropdown(label='الطرف', width=320, options=[])
    rng = theme.DateRangeField('الفترة', page, width=290)
    df, dt = rng.start, rng.end
    from .. import report_engine as RE
    from ..report_viewer import ReportViewer
    viewer = ReportViewer(page, 'party_statement', 'كشف حساب', [
        RE.Col('date', 'التاريخ', RE.DATE), RE.Col('number', 'المستند'), RE.Col('description', 'البيان', width=2.6),
        RE.Col('debit', 'مدين', RE.MONEY, 'sum'), RE.Col('credit', 'دائن', RE.MONEY, 'sum'), RE.Col('balance', 'الرصيد', RE.MONEY, 'last', bold=True)],
        modes=[], show_export=False)
    summary = ft.Text('')
    err = ft.Text('', color=theme.DANGER, visible=False)
    empty_hint = ft.Text('اختر عميل أو مورد لعرض كشف حسابه.', color=theme.TEXT_MUTED, visible=False)
    state = {'data': None}

    def parse(v):
        if not (v or '').strip():
            return None
        return datetime.datetime.strptime(v.strip(), '%Y-%m-%d')

    def parties():
        return services.list_customers() if typ.value == 'customer' else services.list_suppliers()

    def refresh_party(e=None, update_ui=True):
        ps = parties()
        party.options = [(str(x.id), x.name) for x in ps]
        party.value = str(ps[0].id) if ps else None
        refresh_statement(update_ui=update_ui)

    def refresh_statement(e=None, update_ui=True):
        if not party.value:
            empty_hint.visible = True
            viewer.set_rows([])
            summary.value = ''
            if update_ui:
                page.update()
            return
        try:
            state['data'] = services.party_statement(typ.value, int(party.value), parse(df.value), parse(dt.value))
            d = state['data']
            summary.value = f"الرصيد الافتتاحي: {d['opening']:,.2f}    |    الرصيد الختامي: {d['closing']:,.2f}"
            viewer.set_rows([dict(r) for r in d['rows']])
            empty_hint.visible = len(d['rows']) == 0
            err.visible = False
        except Exception as ex:
            err.value = f'حدث خطأ أثناء تحميل كشف الحساب: {ex}'
            err.visible = True
        if update_ui:
            page.update()

    def export(kind):
        if state['data'] is None:
            refresh_statement()
        if state['data'] is None:
            return
        ps = parties()
        name = next((x.name for x in ps if x.id == int(party.value)), '-') if party.value else '-'
        data = dict(state['data'])
        data['party_name'] = name
        try:
            path = (export_excel if kind == 'xlsx' else export_pdf)(
                data, 'party_statement', services.downloads_dir()
            )
            theme.open_or_download_file(page, path)
            page.overlay.append(ft.SnackBar(ft.Text(f'تم إنشاء الملف: {path}'), open=True)); page.update()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True, data='error')); page.update()

    def open_voucher(e=None):
        """سند قبض (عميل) / سند صرف (مورد) مباشرة من كشف الحساب: المبلغ الافتراضي هو الرصيد المستحق، والقيد بيتعمل تلقائي."""
        if not party.value:
            page.overlay.append(ft.SnackBar(ft.Text('اختر الطرف الأول'), open=True)); page.update(); return
        is_cust = typ.value == 'customer'
        d = state['data'] or services.party_statement(typ.value, int(party.value))
        due = max(0.0, float(d['closing'] or 0))
        accs = services.list_accounts(postable_only=True)
        cash = [a for a in accs if a.account_type == 'asset' and (a.code.startswith('11') or 'نقد' in a.name or 'بنك' in a.name)] or [a for a in accs if a.account_type == 'asset']
        cash_dd = theme.SearchableDropdown(label='النقدية / البنك', width=380, options=[(str(a.id), f'{a.code} - {a.name}') for a in cash], value=str(cash[0].id) if cash else None, page=page)
        amount = ft.TextField(label='المبلغ', width=170, value=f'{due:.2f}' if due else '', keyboard_type=ft.KeyboardType.NUMBER, autofocus=True)
        vdate = theme.DateField('التاريخ', page, width=170, value=f'{datetime.datetime.now():%Y-%m-%d}')
        ref = ft.TextField(label='المرجع (رقم الحوالة/الشيك)', width=380)
        notes = ft.TextField(label='ملاحظات', width=380)
        verr = ft.Text('', color=theme.DANGER, visible=False)
        ok_t = ft.Text('', color=theme.SUCCESS, visible=False)
        st = {'pid': None}
        name = next((x.name for x in parties() if x.id == int(party.value)), '-')

        def save(ev):
            try:
                when = datetime.datetime.strptime(vdate.value, '%Y-%m-%d') if vdate.value else None
                fn = services.create_receipt if is_cust else services.create_payment
                st['pid'] = fn(int(party.value), amount.value, int(cash_dd.value) if cash_dd.value else None, date=when, reference=ref.value or '', notes=notes.value or '', partner_type=typ.value)
                verr.visible = False; ok_t.value = 'تم حفظ السند وترحيل القيد'; ok_t.visible = True
                save_btn.visible = False; print_btn.visible = True
                refresh_statement(update_ui=False); page.update()
            except Exception as ex:
                verr.value = str(ex); verr.visible = True; page.update()

        def do_print(ev):
            try:
                theme.open_or_download_file(page, services.generate_payment_pdf_file(st['pid']))
            except Exception as ex:
                verr.value = f'تعذرت الطباعة: {ex}'; verr.visible = True; page.update()

        save_btn = theme.guard_submit(ft.FilledButton('حفظ وترحيل', bgcolor=theme.PRIMARY, on_click=save))
        print_btn = ft.OutlinedButton('طباعة السند', icon=ft.Icons.PRINT_OUTLINED, on_click=do_print, visible=False)
        dlg = ft.AlertDialog(
            modal=True, title=ft.Text(f"{'سند قبض من' if is_cust else 'سند صرف إلى'} {name}"),
            content=ft.Column([ft.Text(f'الرصيد الحالي: {float(d["closing"] or 0):,.2f}', size=12, color=theme.TEXT_MUTED), cash_dd.control, ft.Row([amount, vdate.control], spacing=8), ref, notes, verr, ok_t], tight=True, spacing=10, width=420),
            actions=[ft.TextButton('إغلاق', on_click=lambda ev: (setattr(dlg, 'open', False), page.update())), print_btn, save_btn])
        page.overlay.append(dlg); dlg.open = True; page.update()

    voucher_btn = ft.FilledButton('سند قبض', icon=ft.Icons.DOWNLOAD_DONE, bgcolor=theme.PRIMARY, on_click=open_voucher)

    def sync_voucher_btn():
        voucher_btn.content = 'سند قبض' if typ.value == 'customer' else 'سند صرف'
        voucher_btn.icon = ft.Icons.DOWNLOAD_DONE if typ.value == 'customer' else ft.Icons.PAYMENTS_OUTLINED

    def on_typ(e=None):
        sync_voucher_btn(); refresh_party()

    typ.on_select = on_typ; typ.on_change = on_typ
    party.on_change = refresh_statement
    df.value = f'{datetime.datetime.now().year}-01-01'
    dt.value = f'{datetime.datetime.now():%Y-%m-%d}'
    refresh_party(update_ui=False)  # حساب أولي بدون page.update() قبل ما الشاشة تتلحّم بالصفحة

    return ft.Column(
        [
            ft.Row(
                [theme.page_title('كشف الحساب المتحرك', 'رصيد افتتاحي + حركات زمنية + رصيد تراكمي للعميل أو المورد'),
                 ft.Container(expand=True), typ, party.control],
            ),
            ft.Row(
                [rng.control,
                 voucher_btn,
                 ft.ElevatedButton('تحديث', icon=ft.Icons.REFRESH, on_click=refresh_statement),
                 ft.ElevatedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('xlsx')),
                 ft.ElevatedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf'))],
                wrap=True,
            ),
            err,
            theme.card(ft.Column([summary, empty_hint, viewer.control], spacing=8)),
        ],
        expand=True, scroll=ft.ScrollMode.AUTO,
    )
