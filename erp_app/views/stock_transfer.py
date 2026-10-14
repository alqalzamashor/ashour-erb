import datetime
import flet as ft
from .. import services, theme
from ._doc_grid import DocGrid, doc_datetime


def build_stock_transfer(page: ft.Page):
    """تحويل أصناف بين مخزنين في مستند واحد: التاريخ والمخزنين فوق، والأصناف والكميات في جدول (بتشوف المتاح في المخزن المصدر لكل سطر)."""
    products = [p for p in services.list_products() if p.product_type != 'service']
    locations = services.list_locations()

    date_f = theme.DateField('تاريخ التحويل *', page, width=170, value=datetime.date.today().strftime('%Y-%m-%d'))
    from_dd = ft.Dropdown(label='من مخزن (المصدر) *', width=230, options=[ft.dropdown.Option(str(l.id), l.name) for l in locations])
    to_dd = ft.Dropdown(label='إلى مخزن (الوجهة) *', width=230, options=[ft.dropdown.Option(str(l.id), l.name) for l in locations])
    note_field = ft.TextField(label='ملاحظات', width=280)
    error_text = ft.Text('', color=theme.DANGER, visible=False)
    summary = ft.Text('', weight=ft.FontWeight.BOLD)

    def on_line(line):
        p = line.product_obj
        if not p:
            return
        line.set_static('unit', p.unit or '')
        if not from_dd.value:
            line.set_static('avail', '-'); return
        av = services.get_product_balance(p.id, int(from_dd.value))
        same = sum(l.qty for l in grid.lines if l.product_id == p.id)            # نفس الصنف في أكتر من سطر
        short = same > av + 1e-9
        line.set_static('avail', f'{av:g}' + (' ✗' if short else ''), theme.DANGER if short else theme.SUCCESS, 'الكمية أكبر من المتاح بالمصدر' if short else None)

    def update_summary():
        lines = [ln for ln in grid.lines if ln.product_id]
        summary.value = f'عدد الأصناف: {len(lines)}   |   إجمالي الكميات: {sum(ln.qty for ln in lines):g}' if lines else 'أضف الأصناف المراد تحويلها في الجدول'
        try:
            page.update()
        except Exception:
            pass

    grid = DocGrid(page, [
        {'key': 'i', 'title': '#', 'width': 34, 'kind': 'index'}, {'key': 'p', 'title': 'الصنف', 'width': 360, 'kind': 'product'},
        {'key': 'avail', 'title': 'المتاح بالمخزن المصدر', 'width': 170, 'kind': 'static'}, {'key': 'q', 'title': 'الكمية المحوَّلة', 'width': 130, 'kind': 'qty'},
        {'key': 'unit', 'title': 'الوحدة', 'width': 100, 'kind': 'static'}, {'key': 'd', 'title': '', 'width': 46, 'kind': 'delete'},
    ], on_line=on_line, on_change=update_summary, rows_height=290)
    grid.set_products(products)

    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(c)) for c in ['التاريخ', 'المرجع', 'الصنف', 'من', 'إلى', 'الكمية']], rows=[])

    def refresh_table():
        table.rows = [ft.DataRow(cells=[
            ft.DataCell(ft.Text(t['date'].strftime('%Y-%m-%d'))), ft.DataCell(ft.Text(t['reference'])), ft.DataCell(ft.Text(f"{t['sku']} - {t['product']}")),
            ft.DataCell(ft.Text(t['from_location'])), ft.DataCell(ft.Text(t['to_location'])), ft.DataCell(ft.Text(f"{t['quantity']:g}"))]) for t in services.list_stock_transfers()]
        page.update()

    def do_transfer(e):
        try:
            if not from_dd.value or not to_dd.value:
                raise ValueError('اختر المخزن المصدر والوجهة')
            items = [{'product_id': i['product_id'], 'quantity': i['quantity']} for i in grid.get_items()]
            if not items:
                raise ValueError('أضف صنف واحد على الأقل للتحويل')
            result = services.create_stock_transfer_batch(items, int(from_dd.value), int(to_dd.value), note=note_field.value or '', transfer_date=doc_datetime(date_f.value))
            error_text.visible = False
            grid.clear(); note_field.value = ''
            refresh_table()
            page.overlay.append(ft.SnackBar(ft.Text(f"تم تحويل {result['lines']} صنف - المرجع: {result['reference']}"), open=True))
        except Exception as ex:
            error_text.value = str(ex)
            error_text.visible = True
        page.update()

    from_dd.on_change = lambda e: grid.recalc_all()
    refresh_table()
    update_summary()

    form = theme.card(ft.Column([
        ft.Text('مستند تحويل بين مخزنين', size=16, weight=ft.FontWeight.BOLD),
        ft.Row([date_f.control, from_dd, to_dd, note_field], wrap=True, spacing=12),
        theme.h_scroll(grid.control), summary, error_text,
        theme.guard_submit(ft.FilledButton('تنفيذ التحويل', icon=ft.Icons.SWAP_HORIZ, bgcolor=theme.PRIMARY, on_click=do_transfer)),
    ], spacing=10))

    return ft.Column([
        theme.page_title('تحويل بين المخازن', 'نقل أكتر من صنف بين مخزنين في مستند واحد بتاريخ التحويل، مع تسجيل حركتي خروج ودخول مرتبطتين'),
        ft.Container(height=12), form, ft.Container(height=16),
        theme.card(ft.Column([ft.Text('سجل التحويلات', size=16, weight=ft.FontWeight.BOLD), theme.h_scroll(table)]), expand=True),
    ], expand=True, scroll=ft.ScrollMode.AUTO)
