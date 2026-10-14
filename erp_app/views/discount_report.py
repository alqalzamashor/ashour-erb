import datetime
import flet as ft
from .. import services, theme, discount_report
from ..report_export import export_excel, export_pdf
from .restaurant_dashboard import _bar_rows, _kpi

COLS = ['التاريخ', 'الفاتورة', 'العميل', 'الماكينة', 'النوع', 'الكود', 'السبب / الوصف', 'اعتماد', 'قبل الخصم', 'الخصم', 'بعد الخصم', '%']


def build_discount_report(page: ft.Page):
    """تقرير الخصومات والكوبونات: مين خصم كام وبأي كوبون وبموافقة مين."""
    services.require_action('discount_report', 'view')
    today = datetime.date.today()
    rng = theme.DateRangeField('الفترة', page, width=290)
    rng.start.value = f'{today:%Y-%m-01}'; rng.end.value = f'{today:%Y-%m-%d}'
    kind_dd = ft.Dropdown(label='النوع', width=150, value='', options=[ft.dropdown.Option('', 'الكل')] + [ft.dropdown.Option(k, v) for k, v in discount_report.KINDS.items()])
    term_dd = ft.Dropdown(label='الماكينة', width=190, value='', options=[ft.dropdown.Option('', 'الكل')] + [ft.dropdown.Option(str(t['id']), t['name']) for t in services.list_pos_terminals()])
    appr_cb = ft.Checkbox(label='المعتمد من مدير فقط', value=False)
    void_cb = ft.Checkbox(label='مع الفواتير الملغاة', value=False)
    search_f = ft.TextField(label='رقم الفاتورة', width=150, dense=True)
    kpi_row = ft.Row([], wrap=True, spacing=12)
    sums = ft.Column(spacing=12)
    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x, weight=ft.FontWeight.BOLD), numeric=x in ('قبل الخصم', 'الخصم', 'بعد الخصم', '%')) for x in COLS], rows=[])
    pager = theme.RowPager(table, page, 100)
    st = {'r': None}

    def d(v):
        return datetime.datetime.strptime(v, '%Y-%m-%d').date() if (v or '').strip() else None

    def run(e=None):
        try:
            r = discount_report.build_report(d(rng.start.value), d(rng.end.value), kind_dd.value or None, term_dd.value or None, appr_cb.value, search_f.value or None, void_cb.value)
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True)); page.update(); return
        st['r'] = r; k = r['kpis']
        kpi_row.controls = [_kpi('إجمالي الخصومات', f"{k['total']:,.2f}", theme.DANGER), _kpi('عدد الفواتير', str(k['count']), theme.PRIMARY), _kpi('متوسط نسبة الخصم', f"{k['avg_pct']}%", theme.WARNING),
                            _kpi('الخصم من المبيعات', f"{k['share_of_sales']}%", theme.WARNING, sub='إجمالي الخصم ÷ (المبيعات + الخصم)'), _kpi('معتمدة من مدير', str(k['approved']), theme.SUCCESS)]
        mk = lambda title, rows, col: theme.card(ft.Column([ft.Text(title, size=15, weight=ft.FontWeight.BOLD)] + _bar_rows(rows, col, extra=lambda x: f'{x[1]} فاتورة'), spacing=6), expand=True)
        sums.controls = [ft.Row([mk('حسب النوع', r['by_kind'], theme.PRIMARY), mk('حسب الكوبون', r['by_code'], theme.SUCCESS)], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START),
                         ft.Row([mk('حسب المدير المعتمد', r['by_approver'], theme.WARNING), mk('حسب الماكينة', r['by_terminal'], theme.PRIMARY)], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START)]

        def build(x):
            return ft.DataRow(cells=[ft.DataCell(ft.Text(f"{x['date']:%Y-%m-%d %H:%M}", size=12)), ft.DataCell(ft.Text(x['number'] + (' (ملغاة)' if x['voided'] else ''), size=12, weight=ft.FontWeight.BOLD, color=theme.DANGER if x['voided'] else None)),
                                     ft.DataCell(ft.Text(x['customer'], size=12)), ft.DataCell(ft.Text(x['terminal'], size=12)), ft.DataCell(ft.Text(x['kind_label'], size=12)), ft.DataCell(ft.Text(x['code'] or '-', size=12)),
                                     ft.DataCell(ft.Container(width=220, content=ft.Text(x['note'], size=12, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, tooltip=x['note'] or None))), ft.DataCell(ft.Text(x['approved_by'] or '-', size=12)),
                                     ft.DataCell(ft.Text(f"{x['gross']:,.2f}", size=12)), ft.DataCell(ft.Text(f"{x['discount']:,.2f}", size=12, weight=ft.FontWeight.BOLD, color=theme.DANGER)),
                                     ft.DataCell(ft.Text(f"{x['net']:,.2f}", size=12)), ft.DataCell(ft.Text(f"{x['pct']}%", size=12))])
        pager.set_items(r['rows'], build, keep_page=False)
        if e is not None:
            page.update()

    def export(fmt):
        try:
            if st['r'] is None:
                run()
            r = st['r']; k = r['kpis']
            t = [COLS]
            for x in r['rows']:
                t.append([f"{x['date']:%Y-%m-%d %H:%M}", x['number'] + (' (ملغاة)' if x['voided'] else ''), x['customer'], x['terminal'], x['kind_label'], x['code'], x['note'], x['approved_by'],
                          f"{x['gross']:,.2f}", f"{x['discount']:,.2f}", f"{x['net']:,.2f}", f"{x['pct']}%"])
            styles = {len(t): 'total'}
            t.append([f"الإجمالي ({k['count']} فاتورة)", '', '', '', '', '', '', '', '', f"{k['total']:,.2f}", '', f"{k['avg_pct']}%"])
            data = {'table': t, 'row_styles': styles, 'col_weights': [1.5, 1.3, 1.5, 1.2, 1, 1, 2, 1, 1.1, 1, 1.1, 0.7], 'date_from': d(rng.start.value), 'date_to': d(rng.end.value)}
            theme.open_or_download_file(page, (export_excel if fmt == 'xlsx' else export_pdf)(data, 'discount_report', services.downloads_dir()))
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

    run()
    return ft.Column([
        ft.Row([theme.page_title('تقرير الخصومات والكوبونات', 'مين خصم كام وبأي كوبون وبموافقة مين'), ft.Container(expand=True),
                ft.ElevatedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('xlsx')), ft.ElevatedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf'))]),
        theme.card(ft.Row([rng.control, kind_dd, term_dd, search_f, appr_cb, void_cb, theme.guard_submit(ft.FilledButton('عرض', icon=ft.Icons.SEARCH, bgcolor=theme.PRIMARY, on_click=run))], wrap=True, spacing=10)),
        kpi_row, sums, theme.card(theme.h_scroll(table), expand=True),
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
