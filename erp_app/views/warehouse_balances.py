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

    def movement_view(rep):
        from .. import report_engine as RE
        from ..report_viewer import ReportViewer, Mode
        cols = [RE.Col('warehouse', 'المستودع'), RE.Col('sku', 'الكود'), RE.Col('name', 'الصنف', bold=True, width=2), RE.Col('unit', 'الوحدة'),
                RE.Col('opening', 'رصيد أول الفترة', RE.QTY, 'sum')]
        cols += [RE.Col('in_' + k, 'وارد: ' + l, RE.QTY, 'sum', visible=False) for k, l in rep['in_cols']] + [RE.Col('total_in', 'إجمالي الوارد', RE.QTY, 'sum')]
        cols += [RE.Col('out_' + k, 'منصرف: ' + l, RE.QTY, 'sum', visible=False) for k, l in rep['out_cols']] + [RE.Col('total_out', 'إجمالي المنصرف', RE.QTY, 'sum')]
        cols.append(RE.Col('closing', 'رصيد آخر الفترة', RE.QTY, 'sum', bold=True))
        multi = len(rep['groups']) > 1
        v = ReportViewer(page, 'warehouse_balances', 'أرصدة المستودعات', cols, modes=[Mode('by_wh', 'حسب المستودع', ['warehouse'])] if multi else [],
                         show_export=False, chart_value='closing', default_mode='by_wh' if multi else 'detail')
        rows = []
        for g in rep['groups']:
            for r in g['rows']:
                d = {'warehouse': g['location'].name, 'sku': r['product'].sku or '', 'name': r['product'].name, 'unit': r['product'].unit or '',
                     'opening': r['opening'], 'total_in': r['total_in'], 'total_out': r['total_out'], 'closing': r['closing']}
                d.update({'in_' + k: r[k] for k, _ in rep['in_cols']}); d.update({'out_' + k: r[k] for k, _ in rep['out_cols']})
                rows.append(d)
        v.set_rows(rows)
        return v.control

    def run(e=None):
        try:
            rep = wb.build_report((rng.start.value or '').strip(), (rng.end.value or '').strip(), loc_dd.value or None, hide_zero.value)
        except Exception as ex:      # noqa: BLE001
            page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True, data='error')); page.update(); return
        st['rep'] = rep
        tot = {k: sum(g['totals'][k] for g in rep['groups']) for k in ('opening', 'total_in', 'total_out', 'closing')}
        kpis.controls = [_kpi('رصيد أول الفترة', _q(tot['opening']), theme.PRIMARY), _kpi('إجمالي الوارد', _q(tot['total_in']), theme.SUCCESS),
                         _kpi('إجمالي المنصرف', _q(tot['total_out']), theme.DANGER), _kpi('رصيد آخر الفترة', _q(tot['closing']), theme.PRIMARY)]
        body.controls = ([movement_view(rep)] if rep['groups'] else
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
