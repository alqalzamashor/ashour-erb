import datetime
import os
import flet as ft
from .. import services, theme


def build_purchase_price_report(page: ft.Page):
    """مقارنة أسعار الشراء: بين فترات (سنوات / شهور / أيام) أو بين موردين، مجمّعة حسب الفئة وتتفتح تحت كل فئة أصنافها.
    السعر = سعر الوحدة الأساسية الصافي بعد الخصم ومن غير الضريبة، فبيتقارن صح حتى لو الشراء بوحدات مختلفة."""
    today = datetime.date.today()
    cats = services.list_categories()
    sups = services.list_suppliers()
    state = {'result': None, 'expanded': set(), 'rows': []}
    holder = ft.Container()
    info = ft.Text('', size=12, color=theme.TEXT_MUTED)
    warn = ft.Container(visible=False, bgcolor=theme.WARNING_LIGHT, border_radius=8, padding=ft.Padding(left=12, right=12, top=6, bottom=6), content=ft.Text('', size=12, color=theme.WARNING_TEXT))

    mode_dd = ft.Dropdown(label='المقارنة بين', width=170, value='period', options=[ft.dropdown.Option('period', 'فترات'), ft.dropdown.Option('supplier', 'موردين')])
    gran_dd = ft.Dropdown(label='تقسيم الفترة', width=150, value='month', options=[ft.dropdown.Option(k, v) for k, v in services.PPC_GRANULARITY.items()])
    start = (today.replace(day=1) - datetime.timedelta(days=330)).replace(day=1)
    rng = theme.DateRangeField('الفترة', page, width=290, start=start.strftime('%Y-%m-%d'), end=today.strftime('%Y-%m-%d'))
    metric_dd = ft.Dropdown(label='السعر', width=160, value='avg', options=[ft.dropdown.Option(k, v) for k, v in services.PPC_METRICS.items()])
    sup_dd = ft.Dropdown(label='المورد', width=200, value='', options=[ft.dropdown.Option('', 'كل الموردين')] + [ft.dropdown.Option(str(x.id), x.name) for x in sups])
    cat_dd = ft.Dropdown(label='الفئة', width=200, value='', options=[ft.dropdown.Option('', 'كل الفئات')] + [ft.dropdown.Option(str(c.id), c.name) for c in cats])
    search_f = ft.TextField(label='بحث صنف', width=200, prefix_icon=ft.Icons.SEARCH)

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def _d(v):
        return datetime.datetime.strptime(v, '%Y-%m-%d') if v else None

    def money(v):
        return f'{v:,.2f}' if v is not None else '-'

    def pct_cell(v, bold=False):
        if v is None:
            return ft.Text('-', color=theme.TEXT_MUTED)
        color = theme.DANGER if v > 0.05 else (theme.SUCCESS if v < -0.05 else theme.TEXT_MUTED)       # ارتفاع سعر الشراء = وحش (أحمر)
        arrow = '▲' if v > 0.05 else ('▼' if v < -0.05 else '■')
        return ft.Text(f'{arrow} {abs(v):.1f}%', color=color, weight=ft.FontWeight.BOLD if bold else None, size=12.5)

    def toggle(cid):
        state['expanded'] ^= {cid}
        render()

    def build_table(r):
        by_supplier = r['group_by'] == 'supplier'
        cols = [ft.DataColumn(ft.Text('الفئة / الصنف'))] + [ft.DataColumn(ft.Text(c), numeric=True) for c in r['columns']]
        cols += ([ft.DataColumn(ft.Text('أرخص مورد')), ft.DataColumn(ft.Text('الفرق %'), numeric=True)] if by_supplier else [ft.DataColumn(ft.Text('التغيّر %'), numeric=True)])
        cols += [ft.DataColumn(ft.Text('إجمالي الكمية'), numeric=True), ft.DataColumn(ft.Text('إجمالي القيمة'), numeric=True)]
        tbl = ft.DataTable(columns=cols, rows=[], heading_row_height=44, data_row_min_height=38, column_spacing=22)

        def builder(item):
            kind, obj = item
            if kind == 'cat':
                opened = (obj['category_id'] or 0) in state['expanded']
                head = ft.Container(on_click=lambda e, c=obj['category_id'] or 0: toggle(c), ink=True, border_radius=6,
                                    content=ft.Row([ft.Icon(ft.Icons.EXPAND_MORE if opened else ft.Icons.CHEVRON_LEFT, size=20, color=theme.PRIMARY),
                                                    ft.Text(obj['name'], weight=ft.FontWeight.BOLD, color=theme.PRIMARY_TEXT), ft.Text(f"({obj['count']} صنف)", size=11.5, color=theme.TEXT_MUTED)], spacing=4, tight=True))
                cells = [ft.DataCell(head)] + [ft.DataCell(ft.Text(money(v) if v else '-', weight=ft.FontWeight.BOLD, size=12.5, tooltip='إجمالي قيمة المشتريات')) for v in obj['values']]
                cells += ([ft.DataCell(ft.Text('')), ft.DataCell(ft.Text(''))] if by_supplier else [ft.DataCell(pct_cell(obj['change_pct'], True))])
                cells += [ft.DataCell(ft.Text('')), ft.DataCell(ft.Text(money(obj['total_value']), weight=ft.FontWeight.BOLD))]
                return ft.DataRow(color=theme.PRIMARY_LIGHT, cells=cells)
            p = obj
            cells = [ft.DataCell(ft.Container(padding=ft.Padding(left=0, right=28, top=0, bottom=0), content=ft.Column([ft.Text(p['name']), ft.Text(f"{p['sku']} - {p['unit']}", size=10.5, color=theme.TEXT_MUTED)], spacing=0, tight=True)))]
            for i, v in enumerate(p['prices']):
                color, weight = None, None
                if by_supplier and p['best_index'] is not None:
                    color = theme.SUCCESS if i == p['best_index'] else (theme.DANGER if i == p['worst_index'] else None)
                    weight = ft.FontWeight.BOLD if color else None
                tip = f"الكمية {p['qtys'][i]:g} - القيمة {p['values'][i]:,.2f}" if v is not None else None
                cells.append(ft.DataCell(ft.Text(money(v), color=color, weight=weight, tooltip=tip)))
            if by_supplier:
                cells += [ft.DataCell(ft.Text(r['columns'][p['best_index']] if p['best_index'] is not None else '-', color=theme.SUCCESS, size=12)),
                          ft.DataCell(ft.Text(f"{p['spread_pct']:.1f}%" if p['spread_pct'] is not None else '-', size=12.5))]
            else:
                cells.append(ft.DataCell(pct_cell(p['change_pct'])))
            cells += [ft.DataCell(ft.Text(f"{p['total_qty']:g}")), ft.DataCell(ft.Text(money(p['total_value'])))]
            return ft.DataRow(cells=cells)
        pager = theme.RowPager(tbl, page, 100)
        return tbl, pager, builder

    adv_sw = ft.Switch(label='عرض متقدم (فرز وفلترة وتجميع ورسم على كل الأصناف)', value=False)
    adv_host = ft.Container(expand=True, visible=False)

    def render_adv(r):
        from .. import report_engine as RE
        from ..report_viewer import ReportViewer, Mode, normalize_rows
        by_supplier = r['group_by'] == 'supplier'
        cols = [RE.Col('category', 'الفئة'), RE.Col('name', 'الصنف', width=2.4, bold=True), RE.Col('sku', 'الكود'), RE.Col('unit', 'الوحدة')]
        cols += [RE.Col(f'p{i}', c, RE.MONEY) for i, c in enumerate(r['columns'])]
        if by_supplier:
            cols += [RE.Col('best', 'أرخص مورد'), RE.Col('spread', 'الفرق %', RE.PCT)]
        else:
            cols += [RE.Col('change', 'التغيّر %', RE.PCT)]
        cols += [RE.Col('qty', 'إجمالي الكمية', RE.QTY, 'sum'), RE.Col('value', 'إجمالي القيمة', RE.MONEY, 'sum')]
        rows = []
        for c in r['categories']:
            for p in c['products']:
                d = {'category': c['name'], 'name': p['name'], 'sku': p['sku'], 'unit': p['unit'], 'qty': p['total_qty'], 'value': p['total_value']}
                for i, v in enumerate(p['prices']):
                    d[f'p{i}'] = v
                if by_supplier:
                    d['best'] = r['columns'][p['best_index']] if p['best_index'] is not None else ''
                    d['spread'] = p['spread_pct']
                else:
                    d['change'] = p['change_pct']
                rows.append(d)
        v = ReportViewer(page, 'ppc_adv_' + r['group_by'], 'مقارنة أسعار الشراء', cols,
                         modes=[Mode('by_cat', 'حسب الفئة', ['category']), Mode('by_unit', 'حسب الوحدة', ['unit'])], chart_value='value', kpis=None)
        v.set_rows(normalize_rows(rows, v.cols))
        adv_host.content = v.control

    def on_adv(e=None):
        adv_host.visible = adv_sw.value
        holder.visible = not adv_sw.value
        render()
    adv_sw.on_change = on_adv

    def render():
        r = state['result']
        if adv_sw.value and r and r['categories']:
            render_adv(r)
            info.value = f"{len(r['categories'])} فئة - إجمالي المشتريات {r['grand_total']:,.2f}"
            page.update(); return
        if not r or not r['categories']:
            holder.content = ft.Container(padding=40, alignment=ft.Alignment(0, 0), content=ft.Text('مفيش مشتريات في الفترة والفلاتر دي', color=theme.TEXT_MUTED))
            info.value = ''; page.update(); return
        tbl, pager, builder = build_table(r)
        items = []
        for c in r['categories']:
            items.append(('cat', c))
            if (c['category_id'] or 0) in state['expanded']:
                items += [('prod', p) for p in c['products']]
        pager.set_items(items, builder, keep_page=False)
        # صف الإجمالي (ثابت مع آخر صفحة): قيمة المشتريات لكل عمود
        n_prod = sum(c['count'] for c in r['categories'])
        info.value = f"{len(r['categories'])} فئة - {n_prod} صنف - إجمالي المشتريات {r['grand_total']:,.2f}   |   السعر: {services.PPC_METRICS[r['metric']]} للوحدة الأساسية (صافي بعد الخصم، من غير ضريبة)  |  صف الفئة = إجمالي قيمة المشتريات، وصف الصنف = سعر الوحدة"
        totals = ft.Row([ft.Text('إجمالي قيمة المشتريات:', weight=ft.FontWeight.BOLD)] + [ft.Text(f"{c}: {money(v)}", size=12.5) for c, v in zip(r['columns'], r['totals'])], wrap=True, spacing=14)
        holder.content = ft.Column([theme.h_scroll(tbl, vscroll=True), totals], spacing=8, expand=True)
        page.update()

    def compute(e=None):
        try:
            r = services.purchase_price_comparison(_d(rng.start.value), _d(rng.end.value), gran_dd.value, mode_dd.value, metric_dd.value,
                                                   int(sup_dd.value) if sup_dd.value else None, int(cat_dd.value) if cat_dd.value else None, search_f.value)
            state['result'] = r
            warn.visible = bool(r['truncated'])
            warn.content.value = 'الأعمدة كتير فاتعرض أحدث/أكبر 36 بس - ضيّق الفترة أو غيّر التقسيم' if r['truncated'] else ''
            render()
        except Exception as ex:
            snack(str(ex))

    def on_mode(e=None):
        gran_dd.visible = mode_dd.value == 'period'
        sup_dd.visible = mode_dd.value == 'period'
        compute()

    def expand_all(open_):
        r = state['result']
        state['expanded'] = {(c['category_id'] or 0) for c in r['categories']} if (r and open_) else set()
        render()

    def export(kind):
        try:
            from ..report_export import export_pdf, export_excel
            r = state['result']
            if not r or not r['categories']:
                snack('مفيش بيانات للتصدير'); return
            data = {'ppc': r, 'date_from': _d(rng.start.value), 'date_to': _d(rng.end.value)}
            out_dir = os.path.join(services.APP_DIR, 'exports'); os.makedirs(out_dir, exist_ok=True)
            theme.open_or_download_file(page, (export_pdf if kind == 'pdf' else export_excel)(data, 'purchase_price_comparison', out_dir)); snack('تم إنشاء الملف')
        except Exception as ex:
            snack(f'تعذر التصدير: {ex}')

    mode_dd.on_change = on_mode
    for c in (gran_dd, metric_dd, sup_dd, cat_dd):
        c.on_change = compute
    rng.on_change = compute
    search_f.on_change = compute
    gran_dd.visible = sup_dd.visible = True
    compute()
    return ft.Column([
        ft.Row([theme.page_title('مقارنة أسعار الشراء', 'قارن سعر شراء الأصناف بين فترات (سنوات / شهور / أيام) أو بين الموردين - مجمّع حسب الفئة وتفتح تحت كل فئة أصنافها'),
                ft.Container(expand=True), ft.OutlinedButton('فتح الكل', icon=ft.Icons.UNFOLD_MORE, on_click=lambda e: expand_all(True)), ft.OutlinedButton('طي الكل', icon=ft.Icons.UNFOLD_LESS, on_click=lambda e: expand_all(False)),
                ft.OutlinedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf')), ft.OutlinedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('excel'))], spacing=8),
        theme.card(ft.Row([mode_dd, gran_dd, rng.control, metric_dd, sup_dd, cat_dd, search_f], wrap=True, spacing=10), padding=12),
        warn, info, adv_sw,
        theme.card(holder, expand=True), adv_host,
    ], expand=True, spacing=8)
