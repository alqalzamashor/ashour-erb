import flet as ft
from .. import services, theme, banking


def build_payment_methods(page: ft.Page):
    """طرق الدفع: كل طريقة مربوطة بحساب محاسبي محدد مسبقًا (أو "آجل" على
    حساب العميل)، عشان شاشات البيع تختار الطريقة بس من غير ما تسأل عن
    الحساب كل مرة."""
    accounts = services.list_accounts(postable_only=True)
    acct_options = [(str(a.id), f'{a.code} - {a.name}') for a in accounts]

    name_f = ft.TextField(label='اسم طريقة الدفع', width=240)
    acct_dd = theme.SearchableDropdown(label='الحساب المرتبط', width=320, options=acct_options)
    prov_dd = theme.SearchableDropdown(label='مزوّد الدفع البنكي (اختياري - جهاز شبكة/بوابة)', width=380, options=[('', 'بدون')] + [(str(p.id), p.name) for p in banking.list_providers(True)], value='')
    credit_sw = ft.Switch(label='آجل - على حساب العميل (بدون حساب ثابت)', value=False)
    cash_sw = ft.Switch(label='نقدي - بيدخل صندوق الكاشير (بيتحسب في جرد النقدية عند إغلاق الجلسة)', value=False)
    order_f = ft.TextField(label='الترتيب', width=100, value='1', keyboard_type=ft.KeyboardType.NUMBER)
    err = ft.Text('', color=theme.DANGER, visible=False)
    editing = {'id': None}

    def on_credit_toggle(e=None):
        acct_dd.control.visible = not credit_sw.value
        prov_dd.control.visible = not credit_sw.value
        cash_sw.disabled = credit_sw.value
        if credit_sw.value:
            acct_dd.value = None; cash_sw.value = False; prov_dd.value = ''
        page.update()

    credit_sw.on_change = on_credit_toggle

    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['طريقة الدفع', 'الحساب المرتبط', 'مزوّد البنك', 'النوع', 'الترتيب', 'الحالة', '']], rows=[])

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def clear_form():
        name_f.value = ''; acct_dd.value = None; credit_sw.value = False; cash_sw.value = False; cash_sw.disabled = False; order_f.value = '1'; prov_dd.value = ''
        acct_dd.control.visible = True; prov_dd.control.visible = True; err.visible = False

    def submit(e):
        try:
            services_fn = services.update_payment_method if editing['id'] else services.create_payment_method
            args = dict(name=name_f.value, account_id=int(acct_dd.value) if acct_dd.value else None,
                       is_credit=credit_sw.value, sort_order=int(order_f.value or 0), is_cash=(False if credit_sw.value else cash_sw.value), provider_id=(int(prov_dd.value) if prov_dd.value else None))
            if editing['id']:
                services.update_payment_method(editing['id'], is_active=True, **args)
            else:
                services.create_payment_method(**args)
            clear_form(); editing['id'] = None
            snack('تم الحفظ'); refresh()
        except Exception as ex:
            err.value = str(ex); err.visible = True; page.update()

    def open_edit(m):
        editing['id'] = m.id
        name_f.value = m.name; acct_dd.value = str(m.account_id) if m.account_id else None
        prov_dd.value = str(m.provider_id) if getattr(m, 'provider_id', None) else ''; prov_dd.control.visible = not m.is_credit
        credit_sw.value = m.is_credit; order_f.value = str(m.sort_order); cash_sw.value = services.pm_is_cash(m); cash_sw.disabled = bool(m.is_credit)
        acct_dd.control.visible = not m.is_credit
        err.visible = False
        page.update()

    def cancel_edit(e=None):
        editing['id'] = None
        clear_form(); page.update()

    def toggle_active(m):
        try:
            services.update_payment_method(m.id, m.name, m.account_id, m.is_credit, is_active=not m.is_active, sort_order=m.sort_order)
            refresh()
        except Exception as ex:
            snack(str(ex))

    def delete_method(m):
        try:
            services.delete_payment_method(m.id)
            refresh()
        except Exception as ex:
            snack(str(ex))

    def refresh(e=None):
        rows = []
        prov_names = {p.id: p.name for p in banking.list_providers()}
        for m in services.list_payment_methods():
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(m.name, weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(f'{m.account.code} - {m.account.name}' if m.account else 'حساب العميل (آجل)', size=12)),
                ft.DataCell(ft.Text(prov_names.get(getattr(m, 'provider_id', None), '-'), size=12)),
                ft.DataCell(ft.Text('آجل' if m.is_credit else ('فوري - نقدي' if services.pm_is_cash(m) else 'فوري'), color=theme.WARNING if m.is_credit else theme.SUCCESS)),
                ft.DataCell(ft.Text(str(m.sort_order))),
                ft.DataCell(ft.Text('نشطة' if m.is_active else 'موقوفة', color=theme.SUCCESS if m.is_active else theme.TEXT_MUTED)),
                ft.DataCell(ft.Row(spacing=0, controls=[
                    ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل', on_click=lambda e, x=m: open_edit(x)),
                    ft.IconButton(icon=ft.Icons.TOGGLE_ON_OUTLINED if m.is_active else ft.Icons.TOGGLE_OFF_OUTLINED,
                                 tooltip='إيقاف' if m.is_active else 'تفعيل', on_click=lambda e, x=m: toggle_active(x)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف', on_click=lambda e, x=m: delete_method(x)),
                ])),
            ]))
        table.rows = rows; page.update()

    refresh()
    return ft.Column([
        theme.page_title('طرق الدفع', 'اربط كل طريقة دفع بحسابها المحاسبي - شاشات البيع تختار الطريقة بس من غير ما تسأل عن الحساب'),
        ft.Container(height=12),
        theme.card(ft.Column([
            ft.Text('طريقة دفع جديدة / تعديل', size=16, weight=ft.FontWeight.BOLD),
            ft.Row([name_f, acct_dd.control, order_f], wrap=True, spacing=12),
            prov_dd.control,
            credit_sw, cash_sw, err,
            ft.Row([theme.guard_submit(ft.FilledButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=submit)),
                    ft.TextButton('إلغاء التعديل', on_click=cancel_edit)], spacing=10),
        ], spacing=10)),
        ft.Container(height=16),
        theme.card(ft.Column([ft.Text('كل طرق الدفع', size=16, weight=ft.FontWeight.BOLD), theme.h_scroll(table)])),
    ], expand=True, scroll=ft.ScrollMode.AUTO)
