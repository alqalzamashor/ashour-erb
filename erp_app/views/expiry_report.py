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

    from .. import report_engine as RE
    from ..report_viewer import ReportViewer, Mode
    viewer = ReportViewer(page, 'expiry_report', 'الصلاحية والتشغيلات', [
        RE.Col('product', 'الصنف', bold=True, width=2), RE.Col('sku', 'الكود', visible=False), RE.Col('location', 'المخزن'), RE.Col('batch_no', 'التشغيلة'),
        RE.Col('expiry_date', 'تاريخ الصلاحية', RE.DATE), RE.Col('days_txt', 'المتبقي'), RE.Col('days_left', 'أيام', RE.QTY, visible=False),
        RE.Col('remaining', 'الكمية', RE.QTY, 'sum'), RE.Col('unit', 'الوحدة'), RE.Col('unit_cost', 'تكلفة الوحدة', RE.MONEY),
        RE.Col('value', 'القيمة', RE.MONEY, 'sum', bold=True), RE.Col('method', 'طريقة الإخراج'), RE.Col('status_label', 'الحالة', bold=True)],
        modes=[Mode('by_status', 'حسب الحالة', ['status_label']), Mode('by_wh', 'حسب المخزن', ['location']), Mode('by_product', 'حسب الصنف', ['product'])],
        show_export=False, chart_value='value', default_mode='detail')

    def _flat(r):
        d = r['days_left']
        return {'product': r['product'].name, 'sku': r['product'].sku, 'location': r['location'].name if r['location'] else '-', 'batch_no': r['batch_no'] or '-',
                'expiry_date': r['expiry_date'], 'days_txt': '-' if d is None else (f'متأخر {-d} يوم' if d < 0 else ('اليوم' if d == 0 else f'{d} يوم')), 'days_left': d,
                'remaining': r['remaining'], 'unit': r['product'].unit or '', 'unit_cost': r['unit_cost'], 'value': r['value'],
                'method': METHOD_SHORT.get(r['product'].issue_method or 'none', ''), 'status_label': STATUS[r['status']][0]}

    def refresh(e=None):
        rows = services.list_batches(location_id=int(location_dd.value) if location_dd.value else None, status=status_dd.value or None, search=search_f.value)
        state['rows'] = rows
        viewer.set_rows([_flat(r) for r in rows])
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
        theme.card(viewer.control),
    ], expand=True, scroll=ft.ScrollMode.AUTO)
