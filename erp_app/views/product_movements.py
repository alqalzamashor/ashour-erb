import flet as ft
from .. import services, theme


def build_product_movements(page: ft.Page):
    """دفتر تفصيلي لحركات الأصناف (دخول وخروج ورصيد متحرك): ابحث عن صنف بالكود أو الاسم واختاره فيتحدّث الجدول فورًا،
    أو سيبه فاضي لكل الأصناف. تقدر تفلتر بالمخزن كمان."""
    products = [p for p in services.list_products() if p.product_type != 'service']
    locations = services.list_locations()
    prod_sd = theme.SearchableDropdown('بحث عن صنف (كود أو اسم)', width=380, page=page,
                                       options=[(str(p.id), f'{p.sku} - {p.name}') for p in products], hint_text='اكتب كود أو اسم الصنف، أو سيبه فاضي لكل الأصناف')
    ld = ft.Dropdown(label='المخزن', width=240, value='', options=[ft.dropdown.Option(key='', text='كل المخازن')] + [ft.dropdown.Option(key=str(l.id), text=l.name) for l in locations])
    summary = ft.Text('', weight=ft.FontWeight.BOLD, color=theme.PRIMARY_TEXT)
    from .. import report_engine as RE
    from ..report_viewer import ReportViewer, Mode
    viewer = ReportViewer(page, 'product_movements', 'حركة الأصناف', [
        RE.Col('date', 'التاريخ', RE.DATE), RE.Col('product', 'الصنف', width=2.4, bold=True), RE.Col('location', 'المخزن'), RE.Col('move', 'الحركة'),
        RE.Col('in_qty', 'وارد', RE.QTY, 'sum'), RE.Col('out_qty', 'صادر', RE.QTY, 'sum'), RE.Col('unit_cost', 'تكلفة الوحدة', RE.MONEY),
        RE.Col('value', 'القيمة', RE.MONEY), RE.Col('balance', 'الرصيد', RE.QTY, 'last', bold=True)],
        modes=[Mode('by_prod', 'حسب الصنف', ['product']), Mode('by_loc', 'حسب المخزن', ['location']), Mode('by_move', 'حسب نوع الحركة', ['move']),
               Mode('by_month', 'حسب الشهر', ['date:month']), Mode('month_prod', 'شهر ← صنف', ['date:month', 'product'])], chart_value='in_qty')
    shown = {'pid': None}            # الصنف اللي الجدول معروض عليه حاليًا

    def refresh(e=None):
        pid = int(prod_sd.value) if prod_sd.value else None
        shown['pid'] = pid
        rows = services.product_movement_report(pid, int(ld.value) if ld.value else None)
        viewer.set_rows([{'date': r['date'], 'product': f"{r['sku']} - {r['product']}", 'location': r['location'], 'move': 'دخول' if r['direction'] == 'in' else 'خروج',
                          'in_qty': r['quantity'] if r['direction'] == 'in' else 0, 'out_qty': r['quantity'] if r['direction'] != 'in' else 0,
                          'unit_cost': r['unit_cost'], 'value': r['value'], 'balance': r['balance']} for r in rows])
        ins = sum(r['quantity'] for r in rows if r['direction'] == 'in'); outs = sum(r['quantity'] for r in rows if r['direction'] == 'out')
        if pid and rows:
            summary.value = f"{rows[0]['sku']} - {rows[0]['product']}   |   {len(rows):,} حركة   |   دخول {ins:g}   |   خروج {outs:g}   |   الرصيد الحالي {rows[-1]['balance']:g}"
        elif pid:
            summary.value = 'مفيش حركات للصنف ده' + (' في المخزن المختار' if ld.value else '')
        else:
            summary.value = f"كل الأصناف   |   {len(rows):,} حركة   |   دخول {ins:g}   |   خروج {outs:g}"
        page.update()

    def clear_product(e=None):
        prod_sd.value = None
        prod_sd.text_field.value = ''
        if prod_sd.suggestions_container:
            prod_sd.suggestions_container.visible = False
            prod_sd.suggestions_list.controls = []
        refresh()

    # مسح النص بإيدك = رجوع لكل الأصناف (بدل ما يفضل الجدول على الصنف القديم)
    orig_type = prod_sd._on_type
    def on_type(e):
        orig_type(e)
        if shown['pid'] is not None and not (prod_sd.text_field.value or '').strip():
            refresh()
    prod_sd.text_field.on_change = on_type
    prod_sd.on_change = refresh               # اختيار صنف = تحديث الجدول
    ld.on_change = refresh
    refresh()
    return ft.Column([
        theme.page_title('حركة الأصناف', 'دفتر تفصيلي لكل حركة دخول وخروج ورصيد متحرك - ابحث عن صنف واختاره فيتحدّث الجدول'),
        ft.Container(height=6),
        theme.card(ft.Column([ft.Row([prod_sd.control, ft.IconButton(icon=ft.Icons.CLOSE, tooltip='كل الأصناف', on_click=clear_product), ld], wrap=True, spacing=10,
                                     vertical_alignment=ft.CrossAxisAlignment.START), summary], spacing=8), padding=14),
        ft.Container(height=8),
        viewer.control,
    ], expand=True, scroll=ft.ScrollMode.AUTO)
