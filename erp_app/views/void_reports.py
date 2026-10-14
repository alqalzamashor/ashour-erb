import datetime
import flet as ft
from .. import services, theme, void_reports
from ..report_export import export_excel, export_pdf

KIND_COLORS = {'sales_void': theme.DANGER, 'purchase_void': theme.DANGER, 'sales_return': theme.WARNING, 'rest_order_void': theme.DANGER, 'rest_item_void': theme.DANGER}


def build_void_reports(page: ft.Page):
    """تقرير الفواتير الملغاة والمرتجعة + الأصناف الملغاة والمرتجعة (مبيعات، مشتريات، مطعم)."""
    st = {'res': None}
    rng = theme.DateRangeField('الفترة', page, width=290)
    today = datetime.date.today()
    rng.start.value = f'{today:%Y-%m-01}'; rng.end.value = f'{today:%Y-%m-%d}'
    branches = services.list_branches(True)
    cats = services.list_categories()
    products = services.list_products(active_only=False)
    branch_dd = theme.SearchableDropdown(label='الفرع', width=210, options=[('', 'الكل')] + [(str(b.id), b.name) for b in branches], value='', page=page)
    party_dd = theme.SearchableDropdown(label='العميل', width=230, options=[('', 'الكل')] + [(str(c.id), c.name) for c in services.list_customers(active_only=False)], value='', page=page)
    cat_dd = theme.SearchableDropdown(label='الفئة', width=200, options=[('', 'الكل')] + [(str(c.id), c.name) for c in cats], value='', page=page)
    prod_dd = theme.SearchableDropdown(label='الصنف', width=260, options=[('', 'الكل')] + [(str(p.id), f'{p.sku} - {p.name}') for p in products], value='', page=page)
    search_f = ft.TextField(label='رقم المستند', width=150, dense=True)
    kind_checks = {k: ft.Checkbox(label=v, value=True) for k, v in void_reports.KINDS.items()}
    group_dd = ft.Dropdown(label='تجميع الأصناف حسب', width=210, value='none', options=[ft.dropdown.Option(k, v) for k, v in void_reports.GROUPS.items()])
    kpi_row = ft.Row([], wrap=True, spacing=10)
    err = ft.Text('', color=theme.DANGER, visible=False)
    doc_table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x, weight=ft.FontWeight.BOLD), numeric=x == 'القيمة') for x in ['التاريخ', 'النوع', 'المستند', 'الفاتورة الأصلية', 'العميل / المورد / الطاولة', 'الفرع', 'القناة', 'القيمة', 'السبب', 'بواسطة']], rows=[])
    item_table = ft.DataTable(columns=[ft.DataColumn(ft.Text('')), ], rows=[])
    doc_pager = theme.RowPager(doc_table, page, 100)
    item_pager = theme.RowPager(item_table, page, 100)
    tabs = theme.SimpleTabs(page)
    doc_view = ft.Column([theme.h_scroll(doc_table)], scroll=ft.ScrollMode.AUTO)
    item_view = ft.Column([theme.h_scroll(item_table)], scroll=ft.ScrollMode.AUTO)

    def d(v):
        return datetime.datetime.strptime(v, '%Y-%m-%d').date() if (v or '').strip() else None

    def collect():
        return {'date_from': d(rng.start.value), 'date_to': d(rng.end.value), 'branch_id': branch_dd.value or None, 'party_id': party_dd.value or None,
                'category_id': cat_dd.value or None, 'product_id': prod_dd.value or None, 'search': search_f.value}

    def money(v):
        return f'{v:,.2f}'

    def item_cols(group):
        if group == 'none':
            return ['التاريخ', 'النوع', 'المستند', 'الصنف', 'الفئة', 'العميل / المورد / الطاولة', 'الكمية', 'القيمة', 'السبب', 'بواسطة']
        return [void_reports.GROUPS[group], 'عدد البنود', 'الكمية', 'القيمة', 'النسبة']

    def item_rows(res, group):
        g = void_reports.group_items(res['items'], group)
        if g is None:
            return [[i['date'].strftime('%Y-%m-%d %H:%M'), void_reports.ITEM_KIND_LABEL[i['kind']], i['number'], i['product'], i['category'], i['party'], f"{i['qty']:g}", money(i['amount']), i['reason'], i['user']] for i in res['items']], None
        return [[r['label'], str(r['count']), f"{r['qty']:g}", money(r['amount']), f"{r['share']:.1f}%"] for r in g], g

    def run(e=None):
        try:
            kinds = [k for k, c in kind_checks.items() if c.value]
            res = void_reports.build_report(collect(), kinds)
            st['res'] = res
            kpi_row.controls = [theme.card(ft.Column([ft.Text(v, size=11, color=theme.TEXT_MUTED), ft.Text(f"{res['kpis'][k]['docs']}  |  {money(res['kpis'][k]['amount'])}", size=15, weight=ft.FontWeight.BOLD, color=KIND_COLORS[k]),
                                                       ft.Text(f"كمية الأصناف: {res['kpis'][k]['qty']:g}", size=10, color=theme.TEXT_MUTED)], spacing=2, tight=True), padding=12)
                                for k, v in void_reports.KINDS.items() if k in kinds]
            doc_pager.set_items(res['docs'], lambda r: ft.DataRow(cells=[ft.DataCell(ft.Text(c, size=12.5, color=KIND_COLORS[r['kind']] if i == 1 else None)) for i, c in enumerate(
                [r['date'].strftime('%Y-%m-%d %H:%M'), void_reports.KINDS[r['kind']], r['number'], r['ref'] or '-', r['party'], r['branch'], r['channel'], money(r['amount']), r['reason'], r['user'] or '-'])]), keep_page=False)
            cols = item_cols(group_dd.value)
            item_table.columns = [ft.DataColumn(ft.Text(c, weight=ft.FontWeight.BOLD), numeric=c in ('القيمة', 'الكمية', 'عدد البنود')) for c in cols]
            rows, _ = item_rows(res, group_dd.value)
            item_pager.set_items(rows, lambda r: ft.DataRow(cells=[ft.DataCell(ft.Text(c, size=12.5)) for c in r]), keep_page=False)
            tabs.set_tabs([(f"الفواتير والمستندات ({len(res['docs'])})", doc_view),
                           (f"الأصناف ({len(res['items'])})", item_view)], selected_index=tabs.selected_index)
            err.visible = False
        except Exception as ex:
            err.value = f'تعذر إنشاء التقرير: {ex}'; err.visible = True
        if e is not None:
            page.update()

    def export(fmt):
        try:
            if not st['res']:
                run()
            res = st['res']
            if tabs.selected_index == 0:
                t = [['التاريخ', 'النوع', 'المستند', 'الفاتورة الأصلية', 'العميل / المورد / الطاولة', 'الفرع', 'القناة', 'القيمة', 'السبب', 'بواسطة']]
                for r in res['docs']:
                    t.append([r['date'].strftime('%Y-%m-%d %H:%M'), void_reports.KINDS[r['kind']], r['number'], r['ref'] or '-', r['party'], r['branch'], r['channel'], round(r['amount'], 2), r['reason'], r['user'] or '-'])
                t.append(['الإجمالي'] + [''] * 6 + [round(sum(r['amount'] for r in res['docs']), 2), '', ''])
                w = [1.5, 1.7, 1.2, 1.2, 1.8, 1.2, 1.2, 1, 2.2, 1]
            else:
                cols = item_cols(group_dd.value)
                t = [cols]
                rows, g = item_rows(res, group_dd.value)
                if g is None:
                    for i in res['items']:
                        t.append([i['date'].strftime('%Y-%m-%d %H:%M'), void_reports.ITEM_KIND_LABEL[i['kind']], i['number'], i['product'], i['category'], i['party'], round(i['qty'], 3), round(i['amount'], 2), i['reason'], i['user']])
                    t.append(['الإجمالي'] + [''] * 5 + [round(sum(i['qty'] for i in res['items']), 3), round(sum(i['amount'] for i in res['items']), 2), '', ''])
                    w = [1.5, 1.8, 1.2, 2.2, 1.4, 1.6, 0.8, 1, 2, 1]
                else:
                    for r in g:
                        t.append([r['label'], r['count'], round(r['qty'], 3), round(r['amount'], 2), round(r['share'], 1)])
                    t.append(['الإجمالي', sum(r['count'] for r in g), round(sum(r['qty'] for r in g), 3), round(sum(r['amount'] for r in g), 2), ''])
                    w = [3, 1, 1, 1.2, 1]
            data = {'table': t, 'row_styles': {len(t) - 1: 'total'}, 'col_weights': w, 'date_from': d(rng.start.value), 'date_to': d(rng.end.value)}
            path = (export_excel if fmt == 'xlsx' else export_pdf)(data, 'void_report', services.downloads_dir())
            theme.open_or_download_file(page, path)
            page.overlay.append(ft.SnackBar(ft.Text(f'تم إنشاء الملف: {path}'), open=True)); page.update()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

    def clear(e):
        for dd in (branch_dd, party_dd, cat_dd, prod_dd):
            dd.value = ''
        search_f.value = ''
        for c in kind_checks.values():
            c.value = True
        group_dd.value = 'none'
        run(e)

    group_dd.on_select = run; group_dd.on_change = run
    run()
    return ft.Column([
        ft.Row([theme.page_title('تقرير الملغاة والمرتجعات', 'فواتير ملغاة ومرتجعة + أصناف ملغاة ومرتجعة (مبيعات / مشتريات / مطعم)'), ft.Container(expand=True),
                ft.ElevatedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('xlsx')), ft.ElevatedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf'))]),
        theme.card(ft.Column([ft.Row([rng.control, branch_dd.control, party_dd.control, cat_dd.control, prod_dd.control, search_f], wrap=True, spacing=10),
                              ft.Row(list(kind_checks.values()), wrap=True, spacing=14),
                              ft.Row([group_dd, theme.guard_submit(ft.FilledButton('عرض التقرير', icon=ft.Icons.SEARCH, bgcolor=theme.PRIMARY, on_click=run)),
                                      ft.TextButton('مسح الفلاتر', icon=ft.Icons.FILTER_ALT_OFF, on_click=clear)], wrap=True, spacing=10)], spacing=10)),
        err, kpi_row, tabs.control,
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
