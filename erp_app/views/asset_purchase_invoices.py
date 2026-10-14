import datetime
import flet as ft
from .. import services, theme
from ._asset_stickers import open_sticker_dialog


def build_asset_purchase_invoices(page: ft.Page):
    """فواتير مشتريات الأصول الثابتة - فاتورة مورد عادية (مستحقات وضريبة)
    لكن كل سطر فيها بيسجّل أصل ثابت جديد تلقائيًا في سجل الأصول، بدل ما
    تسجّل الشراء يدوي في مكان وتضيف الأصل يدوي في مكان تاني."""
    suppliers = services.list_suppliers()
    supplier_dd = theme.SearchableDropdown(label='المورد *', width=300, options=[(str(s.id), s.name) for s in suppliers])
    date_field = theme.DateField('تاريخ الفاتورة', page, width=160, value=datetime.date.today().strftime('%Y-%m-%d'))
    notes_field = ft.TextField(label='ملاحظات', width=360)
    err = ft.Text('', color=theme.DANGER, visible=False)
    cats = {}

    # سطور الفاتورة في جدول (شكل Excel) - نفس تصميم فاتورة المشتريات
    from ._asset_invoice_grid import AssetLinesGrid
    totals_text = ft.Text('', weight=ft.FontWeight.BOLD)
    subtotal_txt = ft.Text('0.00', weight=ft.FontWeight.BOLD)
    tax_txt = ft.Text('0.00', weight=ft.FontWeight.BOLD)
    total_txt = ft.Text('0.00', weight=ft.FontWeight.BOLD, size=18, color=theme.PRIMARY)
    units_txt = ft.Text('0', weight=ft.FontWeight.BOLD)

    def recompute_totals():
        units, subtotal, tax = grid.summary()
        units_txt.value = str(units); subtotal_txt.value = f'{subtotal:,.2f}'; tax_txt.value = f'{tax:,.2f}'; total_txt.value = f'{subtotal + tax:,.2f}'

    grid = AssetLinesGrid(page, on_change=lambda: (recompute_totals(), page.update()))

    invoices_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text('رقم الفاتورة')), ft.DataColumn(ft.Text('المورد')), ft.DataColumn(ft.Text('التاريخ')),
            ft.DataColumn(ft.Text('عدد الأصول')), ft.DataColumn(ft.Text('الإجمالي')), ft.DataColumn(ft.Text('الأصول')),
            ft.DataColumn(ft.Text('')),
        ],
        rows=[],
    )

    def print_invoice(invoice_id):
        try:
            path = services.generate_asset_purchase_invoice_pdf_file(invoice_id)
            theme.open_or_download_file(page, path)
            page.overlay.append(ft.SnackBar(ft.Text(f'تم إنشاء ملف الفاتورة: {path}'), open=True))
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذرت الطباعة: {ex}'), open=True))
        page.update()

    def refresh_invoices(e=None):
        cats.clear(); cats.update({str(c.id): c for c in services.list_asset_categories(active_only=True)})   # الكود التالي اتغيّر بعد الحفظ
        grid.set_categories(list(cats.values()))
        rows = []
        for inv, assets in services.list_asset_purchase_invoices():
            groups = {}
            for a in assets:
                groups.setdefault((a.name, a.cost), []).append(a)
            assets_text = '، '.join(
                (f'{n} × {len(g)} [{g[0].code} - {g[-1].code}] ({c:,.0f} للوحدة)' if len(g) > 1 else f'{n} [{g[0].code}] ({c:,.0f})')
                for (n, c), g in groups.items())
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(inv.number)),
                ft.DataCell(ft.Text(inv.supplier.name if inv.supplier else '-')),
                ft.DataCell(ft.Text(inv.date.strftime('%Y-%m-%d'))),
                ft.DataCell(ft.Text(str(len(assets)))),
                ft.DataCell(ft.Text(f'{inv.total:,.2f}', weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(assets_text, size=11)),
                ft.DataCell(ft.Row(spacing=0, controls=[
                    ft.IconButton(icon=ft.Icons.PRINT_OUTLINED, tooltip='طباعة الفاتورة',
                                  on_click=lambda e, iid=inv.id: print_invoice(iid)),
                    ft.IconButton(icon=ft.Icons.QR_CODE_2, tooltip='طباعة استيكرات باركود أصول الفاتورة',
                                  on_click=lambda e, ids=[a.id for a in assets], n=inv.number: open_sticker_dialog(page, ids, f'استيكرات أصول الفاتورة {n} ({len(ids)} أصل)')),
                ])),
            ]))
        invoices_table.rows = rows
        page.update()

    def close_create(e=None):
        create_dialog.open = False
        page.update()

    def save_invoice(e):
        try:
            if not supplier_dd.value:
                raise ValueError('اختر المورد')
            items = grid.get_items()
            if not items:
                raise ValueError('أضف أصل واحد على الأقل للفاتورة')
            invoice_date = datetime.datetime.strptime(date_field.value, '%Y-%m-%d')
            units_count = sum(i['quantity'] for i in items)
            new_invoice_id = services.create_asset_purchase_invoice(int(supplier_dd.value), items, notes=notes_field.value or '', invoice_date=invoice_date)
            err.visible = False
            close_create()
            refresh_invoices()
            page.overlay.append(ft.SnackBar(ft.Text(f'تم إنشاء فاتورة مشتريات الأصول وتسجيل {units_count} أصل في سجل الأصول الثابتة بنجاح'), open=True))
            print_invoice(new_invoice_id)
        except Exception as ex:
            err.value = str(ex); err.visible = True
        page.update()

    create_dialog = ft.AlertDialog(
        modal=True, title=ft.Text('فاتورة مشتريات أصول جديدة'),
        content=ft.Container(width=1100, content=ft.Column([
            ft.Row([supplier_dd.control, date_field.control, notes_field], wrap=True, spacing=12),
            ft.Divider(),
            ft.Text('أصول الفاتورة', weight=ft.FontWeight.BOLD),
            ft.Text('اكتب اسم الأصل واضغط Enter لاختيار الفئة، وكمّل بـ Enter: الكمية ← التكلفة ← الأصل اللي بعده. '
                    'العمر والقيمة التخريدية فاضيين = من الفئة. كل أصل بيتسجّل تلقائيًا في سجل الأصول الثابتة وبيترحّل على حساب الأصل نفسه.',
                    size=12, color=theme.TEXT_MUTED),
            grid.control,
            ft.Divider(),
            ft.Row([
                ft.Column([ft.Text('عدد الأصول', color=theme.TEXT_MUTED), units_txt], spacing=2),
                ft.Column([ft.Text('الإجمالي قبل الضريبة', color=theme.TEXT_MUTED), subtotal_txt], spacing=2),
                ft.Column([ft.Text('مجموع الضريبة', color=theme.TEXT_MUTED), tax_txt], spacing=2),
                ft.Container(expand=True),
                ft.Column([ft.Text('الإجمالي النهائي', color=theme.TEXT_MUTED), total_txt], spacing=2),
            ], spacing=20),
            err,
        ], spacing=10, tight=True)),
        actions=[ft.TextButton('إلغاء', on_click=close_create),
                 ft.FilledButton('حفظ فاتورة مشتريات الأصول', icon=ft.Icons.PRECISION_MANUFACTURING_OUTLINED, bgcolor=theme.PRIMARY, on_click=save_invoice)],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(create_dialog)

    def open_create(e=None):
        supplier_dd.options = [(str(x.id), x.name) for x in services.list_suppliers()]
        notes_field.value = ''
        err.visible = False
        grid.set_categories(list(cats.values()) or services.list_asset_categories(active_only=True))
        grid.clear()
        create_dialog.open = True
        page.update()
        grid.focus_first()

    refresh_invoices()

    return ft.Column(
        [
            ft.Row([theme.page_title('فواتير مشتريات الأصول', 'شراء أصول ثابتة من مورد - بتسجّل الأصل تلقائيًا في سجل الأصول الثابتة وتترحّل على حسابه مباشرة'),
                    ft.Container(expand=True),
                    ft.FilledButton('فاتورة مشتريات أصول جديدة', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=open_create)]),
            ft.Container(height=12),
            theme.card(ft.Column([
                ft.Text('سجل فواتير مشتريات الأصول', size=16, weight=ft.FontWeight.BOLD),
                theme.h_scroll(invoices_table),
            ])),
        ],
        expand=True, scroll=ft.ScrollMode.AUTO,
    )
