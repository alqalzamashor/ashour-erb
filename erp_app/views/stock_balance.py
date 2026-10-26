import datetime
import os
import flet as ft
from .. import services, theme, field_access
from ._doc_grid import end_of_day


def build_stock_balance(page: ft.Page):
    SHOW_COST = field_access.can_see('cost_price')
    locations = services.list_locations()
    location_dd = ft.Dropdown(
        label='المخزن', width=220,
        options=[ft.dropdown.Option('', 'كل المخازن (إجمالي)')] + [ft.dropdown.Option(str(l.id), l.name) for l in locations],
        value='',
    )
    date_f = theme.DateField('الرصيد حتى تاريخ', page, width=170, value=datetime.date.today().strftime('%Y-%m-%d'))
    asof_note = ft.Text('', size=12, color=theme.TEXT_MUTED)
    group_by_warehouse = ft.Switch(label='تفصيل حسب كل مخزن', value=False)
    low_only_switch = ft.Switch(label='عرض الأصناف الناقصة فقط', value=False)
    hide_zero_switch = ft.Switch(label='إخفاء الأصناف برصيد صفر', value=False)
    meta = {'as_of': None, 'by_wh': False, 'loc_name': 'كل المخازن', 'hidden': 0}

    from .. import report_engine as RE
    from ..report_viewer import ReportViewer, Mode
    stock_cols = [RE.Col('sku', 'الكود'), RE.Col('name', 'الصنف', bold=True, width=2), RE.Col('location_name', 'المخزن'),
                  RE.Col('balance', 'الرصيد', RE.QTY, 'sum', bold=True), RE.Col('unit', 'الوحدة'),
                  RE.Col('value', 'قيمة الرصيد', RE.MONEY, 'sum', visible=SHOW_COST), RE.Col('status', 'الحالة', group=True)]
    if not SHOW_COST:
        stock_cols = [c for c in stock_cols if c.key != 'value']
    viewer = ReportViewer(page, 'stock_balance', 'أرصدة المخزون', stock_cols,
                          modes=[Mode('by_wh', 'حسب المخزن', ['location_name']), Mode('by_status', 'حسب الحالة', ['status'])], show_export=False, chart_value='value' if SHOW_COST else 'balance')
    balance_table = viewer.control

    def _flat(row):
        p = row['product']
        return {'sku': p.sku, 'name': p.name, 'location_name': row['location_name'], 'balance': row['balance'], 'unit': p.unit, 'value': row['value'],
                'status': 'ناقص - يحتاج طلب' if row['is_low'] else 'متوفر', '_raw': row}

    def refresh_table(e=None):
        # تاريخ فاضي = الرصيد الحالي، وإلا الرصيد لحد نهاية اليوم ده (كل الحركات اللي قبله وفيه)
        try:
            as_of = end_of_day(date_f.value) if date_f.value else None
        except Exception:
            as_of = None
        asof_note.value = (f"الأرصدة حتى نهاية يوم {as_of:%d/%m/%Y} - القيمة محسوبة بآخر سعر تكلفة حالي للصنف" if as_of and as_of.date() != datetime.date.today()
                           else 'الأرصدة الحالية (حتى اللحظة)')
        if group_by_warehouse.value:
            location_dd.disabled = True
            data = services.get_stock_balance_by_warehouse(low_stock_only=low_only_switch.value, as_of=as_of)
            for row in data:
                row['location_name'] = row['location'].name
        else:
            location_dd.disabled = False
            loc_id = int(location_dd.value) if location_dd.value else None
            loc_name = next((l.name for l in locations if l.id == loc_id), 'كل المخازن')
            data = services.get_stock_balance_report(location_id=loc_id, low_stock_only=low_only_switch.value, as_of=as_of)
            for row in data:
                row['location_name'] = loc_name
        meta.update(as_of=as_of, by_wh=group_by_warehouse.value)
        meta['hidden'] = 0
        if hide_zero_switch.value:
            kept = [r for r in data if abs(r['balance']) > 1e-9]
            meta['hidden'] = len(data) - len(kept)
            data = kept
        if meta['hidden']:
            asof_note.value += f"  |  مخفي {meta['hidden']:,} صنف برصيد صفر"
        meta['loc_name'] = data[0]['location_name'] if (data and not group_by_warehouse.value) else 'كل المخازن'
        meta['raw'] = data
        viewer.set_rows([_flat(r) for r in data])

    location_dd.on_change = refresh_table
    date_f.on_change = refresh_table
    group_by_warehouse.on_change = refresh_table
    low_only_switch.on_change = refresh_table
    hide_zero_switch.on_change = refresh_table

    def export(kind):
        try:
            from ..report_export import export_pdf, export_excel
            rows = [r['_raw'] for r in RE.run([_flat(r) for r in meta.get('raw', [])], stock_cols, viewer.state)['rows']]          # بنفس ترتيب وفلاتر العارض على الشاشة
            if not rows:
                page.overlay.append(ft.SnackBar(ft.Text('مفيش أصناف للتصدير'), open=True)); page.update(); return
            as_of = meta['as_of'] or datetime.datetime.now()
            sub = f"حتى {as_of:%d/%m/%Y}" + ('' if meta['by_wh'] else f" - {meta['loc_name']}") + (' - تفصيل بالمخازن' if meta['by_wh'] else '') + (' - بدون الأصناف برصيد صفر' if hide_zero_switch.value else '') + (' - الناقصة فقط' if low_only_switch.value else '')
            data = {'stock_rows': rows, 'stock_by_warehouse': meta['by_wh'], 'date_from': None, 'date_to': None, 'title_suffix': sub}
            out_dir = os.path.join(services.APP_DIR, 'exports'); os.makedirs(out_dir, exist_ok=True)
            theme.open_or_download_file(page, (export_pdf if kind == 'pdf' else export_excel)(data, 'stock_balance', out_dir))
            page.overlay.append(ft.SnackBar(ft.Text('تم إنشاء الملف'), open=True)); page.update()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()
    refresh_table()

    return ft.Column(
        [
            ft.Row(
                [theme.page_title('أرصدة المخزون', 'الكميات المتاحة لكل صنف في أي تاريخ (افتراضيًا اليوم) - إجمالي أو تفصيلي حسب كل مخزن'),
                 ft.Container(expand=True), date_f.control, location_dd],
            ),
            ft.Row([group_by_warehouse, low_only_switch, hide_zero_switch, ft.Container(expand=True),
                    ft.OutlinedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf')), ft.OutlinedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('excel'))],
                   wrap=False, spacing=14),
            asof_note,
            ft.Container(height=12),
            theme.card(balance_table),
        ],
        expand=True, scroll=ft.ScrollMode.AUTO,
    )
