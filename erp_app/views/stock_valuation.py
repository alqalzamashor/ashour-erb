import datetime

import flet as ft

from .. import services, theme, field_access, warehouse_balances as wb
from ..report_export import export_excel, export_pdf


def _n(v):
    return f'{v:,.2f}'


def build_stock_valuation(page: ft.Page):
    """تقييم المخزون: الكمية ومتوسط السعر والقيمة لكل صنف في كل مستودع حتى تاريخ معيّن."""
    services.require_action('stock_valuation', 'view')
    show_cost = field_access.can_see('cost_price')
    locations = services.list_locations()
    date_f = theme.DateField('حتى تاريخ', page, width=170, value=datetime.date.today().strftime('%Y-%m-%d'))
    loc_dd = ft.Dropdown(label='المستودع', width=240, value='', options=[ft.dropdown.Option('', 'كل المستودعات')] + [ft.dropdown.Option(str(l.id), l.name) for l in locations])
    combine = ft.Switch(label='إجمالي كل المستودعات في جدول واحد', value=False)
    hide_zero = ft.Switch(label='إخفاء الأصناف الصفرية', value=True)
    note = ft.Text('متوسط السعر = متوسط تكلفة الصنف الحالي • القيمة = الكمية × متوسط السعر' + ('' if show_cost else ' • (التكلفة مخفية عن حسابك)'), size=11, color=theme.TEXT_MUTED)
    kpis, body, st = ft.Row([], wrap=True, spacing=12), ft.Column([], spacing=14), {'rep': None}

    def _kpi(title, value, color=theme.PRIMARY):
        return theme.card(ft.Column([ft.Text(title, size=11, color=theme.TEXT_MUTED), ft.Text(value, size=20, weight=ft.FontWeight.BOLD, color=color)], spacing=2, tight=True), padding=14, expand=True)

    from .. import report_engine as RE
    from ..report_viewer import ReportViewer, Mode

    def valuation_view(gs):
        cols = [RE.Col('warehouse', 'المستودع'), RE.Col('sku', 'الكود'), RE.Col('name', 'الصنف', bold=True, width=2), RE.Col('unit', 'الوحدة'), RE.Col('qty', 'الكمية', RE.QTY, 'sum')]
        if show_cost:
            cols += [RE.Col('price', 'متوسط السعر', RE.MONEY), RE.Col('value', 'القيمة', RE.MONEY, 'sum', bold=True)]
        v = ReportViewer(page, 'stock_valuation', 'تقييم المخزون', cols, modes=[Mode('by_wh', 'حسب المستودع', ['warehouse'])] if len(gs) > 1 else [],
                         show_export=False, chart_value='value' if show_cost else 'qty', default_mode='by_wh' if len(gs) > 1 else 'detail')
        v.set_rows([{'warehouse': g['name'], 'sku': r['product'].sku or '', 'name': r['product'].name, 'unit': r['product'].unit or '', 'qty': r['qty'],
                     'price': r['price'], 'value': r['value']} for g in gs for r in g['rows']])
        return v.control

    def run(e=None):
        try:
            rep = wb.build_valuation((date_f.value or '').strip() or None, loc_dd.value or None, hide_zero.value, combine.value)
        except Exception as ex:      # noqa: BLE001
            page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True, data='error')); page.update(); return
        st['rep'] = rep
        gs = rep['groups']
        # الإجمالي العام: لو العرض مجمّع كل المستودعات هو نفسه؛ لو مفصّل بنجمع المستودعات
        kpis.controls = [_kpi('عدد الأصناف', str(len({r['product'].id for g in gs for r in g['rows']}))), _kpi('إجمالي الكمية', _n(sum(g['qty'] for g in gs)))] + \
                        ([_kpi('إجمالي القيمة', _n(sum(g['value'] for g in gs)), theme.SUCCESS)] if show_cost else [])
        body.controls = [valuation_view(gs)] if gs else [theme.empty_state('لا توجد أرصدة', hint='جرّب تغيّر التاريخ أو المستودع')]
        page.update()

    def export(fmt):
        try:
            if st['rep'] is None:
                run()
            if st['rep'] is None:
                return
            theme.open_or_download_file(page, (export_excel if fmt == 'xlsx' else export_pdf)(wb.valuation_export_table(st['rep'], show_cost), 'stock_valuation', services.downloads_dir()))
        except Exception as ex:      # noqa: BLE001
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

    return_col = ft.Column([
        ft.Row([theme.page_title('تقييم المخزون', 'الكمية ومتوسط السعر والقيمة لكل صنف حسب المستودع'), ft.Container(expand=True),
                ft.ElevatedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('xlsx')), ft.ElevatedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf'))]),
        theme.card(ft.Column([ft.Row([date_f.control, loc_dd, combine, hide_zero, theme.guard_submit(ft.FilledButton('عرض', icon=ft.Icons.SEARCH, bgcolor=theme.PRIMARY, on_click=run))], wrap=True, spacing=10), note], spacing=8)),
        kpis, body,
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
    run()
    return return_col
