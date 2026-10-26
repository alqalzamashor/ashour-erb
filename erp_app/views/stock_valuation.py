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

    def group_table(g):
        B = ft.FontWeight.BOLD
        cols = [ft.DataColumn(ft.Text(c, size=12, weight=B), numeric=i >= 3) for i, c in enumerate(['الكود', 'الصنف', 'الوحدة', 'الكمية'] + (['متوسط السعر', 'القيمة'] if show_cost else []))]
        tbl = ft.DataTable(columns=cols, rows=[], heading_row_height=44, data_row_min_height=34, column_spacing=24)

        def cells(vals, bold=False, neg=False):
            return [ft.DataCell(ft.Text(v, size=12, weight=B if bold else None, color=theme.DANGER if neg and i == 3 else None)) for i, v in enumerate(vals)]
        build = lambda r: ft.DataRow(cells([r['product'].sku or '', r['product'].name, r['product'].unit or '', _n(r['qty'])] + ([_n(r['price']), _n(r['value'])] if show_cost else []), neg=r['qty'] < -1e-9))
        tot = ['', f"الإجمالي {g['name']}", '', _n(g['qty'])] + (['', _n(g['value'])] if show_cost else [])
        theme.RowPager(tbl, page, 100).set_items(g['rows'], build, keep_page=False)
        sub = ''
        if len(g['rows']) <= 100:
            tbl.rows.append(ft.DataRow(color='#FEF3C7', cells=cells(tot, True)))
        else:
            sub = f"   |   الإجمالي: كمية {_n(g['qty'])}" + (f" • قيمة {_n(g['value'])}" if show_cost else '')
        return ft.Column([ft.Container(ft.Text(g['name'] + sub, weight=B, color='#FFFFFF'), bgcolor=theme.PRIMARY, padding=ft.Padding.symmetric(horizontal=12, vertical=6), border_radius=6), theme.h_scroll(tbl)], spacing=6)

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
        body.controls = [group_table(g) for g in gs] if gs else [theme.empty_state('لا توجد أرصدة', hint='جرّب تغيّر التاريخ أو المستودع')]
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
