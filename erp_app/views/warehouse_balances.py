import datetime

import flet as ft

from .. import services, theme, warehouse_balances as wb
from ..report_export import export_excel, export_pdf

IN_BG, OUT_BG = '#DDF1E6', '#FBE0DD'


def _q(v):
    return '-' if abs(v) < 1e-9 else f'{v:,.2f}'


def build_warehouse_balances(page: ft.Page):
    """أرصدة المستودعات خلال فترة: رصيد أول الفترة + الوارد - المنصرف = رصيد آخر الفترة لكل صنف وكل مستودع."""
    services.require_action('warehouse_balances', 'view')
    today = datetime.date.today()
    locations = services.list_locations()
    rng = theme.DateRangeField('الفترة', page, width=290, allow_clear=False)
    rng.set_range(today.replace(day=1), today)
    loc_dd = ft.Dropdown(label='المستودع', width=240, value='', options=[ft.dropdown.Option('', 'كل المستودعات')] + [ft.dropdown.Option(str(l.id), l.name) for l in locations])
    hide_zero = ft.Switch(label='إخفاء الأصناف الصفرية', value=True)
    note = ft.Text('الكميات بوحدة كل صنف الأساسية • الحركات الملغاة مش محسوبة', size=11, color=theme.TEXT_MUTED)
    kpis = ft.Row([], wrap=True, spacing=12)
    body = ft.Column([], spacing=14)
    st = {'rep': None}

    def _kpi(title, value, color):
        return theme.card(ft.Column([ft.Text(title, size=11, color=theme.TEXT_MUTED), ft.Text(value, size=20, weight=ft.FontWeight.BOLD, color=color)], spacing=2, tight=True), padding=14, expand=True)

    def head(text, bg=None, sub=None):
        return ft.DataColumn(ft.Container(ft.Column([ft.Text(sub or '', size=10, color=theme.TEXT_MUTED, visible=bool(sub)), ft.Text(text, size=12, weight=ft.FontWeight.BOLD)], spacing=0, tight=True), bgcolor=bg, padding=4), numeric=True)

    def group_table(g, rep):
        cols = [ft.DataColumn(ft.Text('الكود', size=12, weight=ft.FontWeight.BOLD)), ft.DataColumn(ft.Text('الصنف', size=12, weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text('الوحدة', size=12, weight=ft.FontWeight.BOLD)), head('رصيد أول الفترة')]
        cols += [head(l, IN_BG, 'وارد') for _, l in rep['in_cols']] + [head('إجمالي الوارد', IN_BG, 'وارد')]
        cols += [head(l, OUT_BG, 'منصرف') for _, l in rep['out_cols']] + [head('إجمالي المنصرف', OUT_BG, 'منصرف')]
        cols.append(head('رصيد آخر الفترة'))

        def cells(r, bold=False, first=('', '', '')):
            w = ft.FontWeight.BOLD
            c = [ft.DataCell(ft.Text(first[0], size=12)), ft.DataCell(ft.Text(first[1], size=12, weight=w if bold else None)), ft.DataCell(ft.Text(first[2], size=12)),
                 ft.DataCell(ft.Text(_q(r['opening']), size=12, weight=w))]
            c += [ft.DataCell(ft.Text(_q(r[k]), size=12)) for k, _ in rep['in_cols']] + [ft.DataCell(ft.Text(_q(r['total_in']), size=12, weight=w))]
            c += [ft.DataCell(ft.Text(_q(r[k]), size=12)) for k, _ in rep['out_cols']] + [ft.DataCell(ft.Text(_q(r['total_out']), size=12, weight=w))]
            c.append(ft.DataCell(ft.Text(_q(r['closing']), size=12, weight=w, color=theme.DANGER if r['closing'] < -1e-9 else None)))
            return c
        tbl = ft.DataTable(columns=cols, rows=[], heading_row_height=56, data_row_min_height=34, column_spacing=18)
        build = lambda r: ft.DataRow(cells=cells(r, first=(r['product'].sku or '', r['product'].name, r['product'].unit or '')))
        tot = g['totals']
        small = len(g['rows']) <= 100
        if small:
            theme.RowPager(tbl, page, 100).set_items(g['rows'], build, keep_page=False)
            tbl.rows.append(ft.DataRow(color='#FEF3C7', cells=cells(tot, True, ('', f"الإجمالي {g['location'].name}", ''))))
            sub = ''
        else:
            theme.RowPager(tbl, page, 100).set_items(g['rows'], build, keep_page=False)
            sub = f"   |   الإجمالي: أول {_q(tot['opening'])} • وارد {_q(tot['total_in'])} • منصرف {_q(tot['total_out'])} • آخر {_q(tot['closing'])}"
        return ft.Column([ft.Container(ft.Text(f"{g['location'].name}{sub}", weight=ft.FontWeight.BOLD, color='#FFFFFF'), bgcolor=theme.PRIMARY, padding=ft.Padding.symmetric(horizontal=12, vertical=6), border_radius=6),
                          theme.h_scroll(tbl)], spacing=6)

    def run(e=None):
        try:
            rep = wb.build_report((rng.start.value or '').strip(), (rng.end.value or '').strip(), loc_dd.value or None, hide_zero.value)
        except Exception as ex:      # noqa: BLE001
            page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True, data='error')); page.update(); return
        st['rep'] = rep
        tot = {k: sum(g['totals'][k] for g in rep['groups']) for k in ('opening', 'total_in', 'total_out', 'closing')}
        kpis.controls = [_kpi('رصيد أول الفترة', _q(tot['opening']), theme.PRIMARY), _kpi('إجمالي الوارد', _q(tot['total_in']), theme.SUCCESS),
                         _kpi('إجمالي المنصرف', _q(tot['total_out']), theme.DANGER), _kpi('رصيد آخر الفترة', _q(tot['closing']), theme.PRIMARY)]
        body.controls = ([group_table(g, rep) for g in rep['groups']] if rep['groups'] else
                         [theme.empty_state('لا توجد حركة أو أرصدة في الفترة دي', hint='جرّب توسّع الفترة أو تطفي إخفاء الأصناف الصفرية')])
        page.update()

    def export(fmt):
        try:
            if st['rep'] is None:
                run()
            if st['rep'] is None:
                return
            theme.open_or_download_file(page, (export_excel if fmt == 'xlsx' else export_pdf)(wb.export_table(st['rep']), 'warehouse_balances', services.downloads_dir()))
        except Exception as ex:      # noqa: BLE001
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

    run_btn = theme.guard_submit(ft.FilledButton('عرض', icon=ft.Icons.SEARCH, bgcolor=theme.PRIMARY, on_click=run))
    layout = ft.Column([
        ft.Row([theme.page_title('أرصدة المستودعات', 'رصيد أول الفترة والوارد والمنصرف ورصيد آخر الفترة لكل صنف وكل مستودع'), ft.Container(expand=True),
                ft.ElevatedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('xlsx')), ft.ElevatedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf'))]),
        theme.card(ft.Column([ft.Row([rng.control, loc_dd, hide_zero, run_btn], wrap=True, spacing=10), note], spacing=8)),
        kpis, body,
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
    run()
    return layout
