import os
import flet as ft
from .. import services, theme

STATUS = {'expired': ('منتهي', theme.DANGER), 'near': ('قارب على الانتهاء', theme.WARNING), 'ok': ('سليم', theme.SUCCESS), 'none': ('بدون صلاحية', theme.TEXT_MUTED)}
METHOD_SHORT = {'fifo': 'FIFO', 'lifo': 'LIFO', 'fefo': 'الأقرب انتهاءً', 'none': 'الأقرب انتهاءً'}


def build_expiry_report(page: ft.Page):
    """الصلاحية والتشغيلات: كل تشغيلة متبقّي منها كمية (الصنف، المخزن، رقم التشغيلة، تاريخ الصلاحية، الأيام المتبقية، الكمية والقيمة)،
    مع تمييز المنتهي والقارب على الانتهاء. للأصناف المتتبَّعة فقط (طريقة إخراج أو صلاحية)."""
    locations = services.list_locations()
    cards = ft.Row(wrap=True, spacing=12)
    location_dd = ft.Dropdown(label='المخزن', width=210, value='', options=[ft.dropdown.Option('', 'كل المخازن')] + [ft.dropdown.Option(str(l.id), l.name) for l in locations])
    status_dd = ft.Dropdown(label='الحالة', width=210, value='', options=[ft.dropdown.Option('', 'الكل')] + [ft.dropdown.Option(k, v[0]) for k, v in STATUS.items()])
    search_f = ft.TextField(label='بحث (كود / صنف / تشغيلة)', width=260, prefix_icon=ft.Icons.SEARCH)
    state = {'rows': []}

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def row_builder(r):
        label, color = STATUS[r['status']]
        d = r['days_left']
        days_txt = '-' if d is None else (f'متأخر {-d} يوم' if d < 0 else ('اليوم' if d == 0 else f'{d} يوم'))
        return ft.DataRow(color=ft.Colors.with_opacity(0.08, color) if r['status'] in ('expired', 'near') else None, cells=[
            ft.DataCell(ft.Column([ft.Text(r['product'].name, weight=ft.FontWeight.BOLD), ft.Text(r['product'].sku, size=10.5, color=theme.TEXT_MUTED)], spacing=0, tight=True)),
            ft.DataCell(ft.Text(r['location'].name if r['location'] else '-')),
            ft.DataCell(ft.Text(r['batch_no'] or '-', size=12.5)),
            ft.DataCell(ft.Text(r['expiry_date'].strftime('%Y-%m-%d') if r['expiry_date'] else '-', weight=ft.FontWeight.BOLD)),
            ft.DataCell(ft.Container(content=ft.Text(days_txt, size=11, color='#FFFFFF', weight=ft.FontWeight.BOLD), bgcolor=color, border_radius=10, padding=ft.Padding(left=8, right=8, top=2, bottom=2)) if d is not None else ft.Text('-')),
            ft.DataCell(ft.Text(f"{r['remaining']:g}", weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(r['product'].unit or '')),
            ft.DataCell(ft.Text(f"{r['unit_cost']:,.2f}")), ft.DataCell(ft.Text(f"{r['value']:,.2f}")),
            ft.DataCell(ft.Text(METHOD_SHORT.get(r['product'].issue_method or 'none', ''), size=12, color=theme.TEXT_MUTED)),
            ft.DataCell(ft.Text(label, color=color, weight=ft.FontWeight.BOLD, size=12)),
        ])

    table = theme.SortableDataTable(columns=[
        ('الصنف', lambda r: r['product'].name), ('المخزن', lambda r: r['location'].name if r['location'] else ''), ('التشغيلة', lambda r: r['batch_no'] or ''),
        ('تاريخ الصلاحية', lambda r: r['expiry_date'] or __import__('datetime').datetime.max), ('المتبقي', lambda r: r['days_left'] if r['days_left'] is not None else 10 ** 9, True),
        ('الكمية', lambda r: r['remaining'], True), ('الوحدة', None), ('تكلفة الوحدة', lambda r: r['unit_cost'], True), ('القيمة', lambda r: r['value'], True),
        ('طريقة الإخراج', None), ('الحالة', lambda r: r['status'])], row_builder=row_builder, page=page, expand=True, initial_sort=3)

    def refresh(e=None):
        rows = services.list_batches(location_id=int(location_dd.value) if location_dd.value else None, status=status_dd.value or None, search=search_f.value)
        state['rows'] = rows
        table.set_data(rows)
        all_rows = services.list_batches(location_id=int(location_dd.value) if location_dd.value else None)
        ex = [r for r in all_rows if r['status'] == 'expired']; nr = [r for r in all_rows if r['status'] == 'near']
        def card(label, value, color, sub):
            return theme.card(ft.Column([ft.Text(label, size=12, color=theme.TEXT_MUTED), ft.Text(value, size=22, weight=ft.FontWeight.BOLD, color=color), ft.Text(sub, size=11, color=theme.TEXT_MUTED)], spacing=0, tight=True), padding=14)
        cards.controls = [card('تشغيلات منتهية', str(len(ex)), theme.DANGER, f"قيمتها {sum(r['value'] for r in ex):,.2f} - مش بتتصرف في البيع"),
                          card('قاربت على الانتهاء', str(len(nr)), theme.WARNING, f"قيمتها {sum(r['value'] for r in nr):,.2f}"),
                          card('إجمالي التشغيلات', str(len(all_rows)), theme.PRIMARY, 'بمتبقّي كمية > 0'),
                          card('قيمة المخزون المتتبَّع', f"{sum(r['value'] for r in all_rows):,.2f}", theme.SUCCESS, 'بتكلفة كل تشغيلة')]
        if e is not None:
            page.update()

    def export(kind):
        try:
            from ..report_export import export_pdf, export_excel
            data = {'expiry_rows': state['rows'], 'date_from': None, 'date_to': None}
            out_dir = os.path.join(services.APP_DIR, 'exports'); os.makedirs(out_dir, exist_ok=True)
            theme.open_or_download_file(page, (export_pdf if kind == 'pdf' else export_excel)(data, 'expiry_report', out_dir)); snack('تم إنشاء الملف')
        except Exception as ex:
            snack(f'تعذر التصدير: {ex}')

    location_dd.on_change = refresh; status_dd.on_change = refresh; search_f.on_change = refresh
    refresh()
    return ft.Column([
        ft.Row([theme.page_title('الصلاحية والتشغيلات', 'تشغيلات الأصناف المتتبَّعة وتواريخ صلاحيتها - المنتهي والقارب على الانتهاء وطريقة الإخراج (FIFO / LIFO / الأقرب انتهاءً)'),
                ft.Container(expand=True), ft.OutlinedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf')), ft.OutlinedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('excel'))], spacing=8),
        ft.Container(height=4), cards, ft.Row([location_dd, status_dd, search_f], wrap=True, spacing=10), ft.Container(height=2),
        theme.card(theme.h_scroll(table.control, vscroll=True), expand=True),
    ], expand=True)
