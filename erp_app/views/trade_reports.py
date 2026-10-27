import datetime
import flet as ft
from .. import services, theme, trade_reports
from ..report_export import export_excel, export_pdf


def _build(page: ft.Page, kind: str):
    is_sales = kind == 'sales'
    party_label = 'العميل' if is_sales else 'المورد'
    state = {'result': None, 'filters': {}}
    collapsed = set()

    def opts(items, blank='الكل'):
        return [('', blank)] + items

    branches = services.list_branches(True)
    centers = services.list_cost_centers(True)
    parties = services.list_customers(active_only=False) if is_sales else services.list_suppliers(active_only=False)
    cats = services.list_categories()
    products = services.list_products(active_only=False)

    rng = theme.DateRangeField('الفترة', page, width=290)
    rng.start.value = f'{datetime.date.today().year}-01-01'; rng.end.value = f'{datetime.date.today():%Y-%m-%d}'
    branch_dd = theme.SearchableDropdown(label='الفرع', width=210, options=opts([(str(b.id), f'{b.code} - {b.name}') for b in branches]), value='', page=page)
    cc_dd = theme.SearchableDropdown(label='مركز التكلفة', width=210, options=opts([(str(c.id), f'{c.code} - {c.name}') for c in centers]), value='', page=page)
    party_dd = theme.SearchableDropdown(label=party_label, width=240, options=opts([(str(p.id), p.name) for p in parties]), value='', page=page)
    cat_dd = theme.SearchableDropdown(label='الفئة', width=200, options=opts([(str(c.id), c.name) for c in cats]), value='', page=page)
    prod_dd = theme.SearchableDropdown(label='الصنف', width=260, options=opts([(str(p.id), f'{p.sku} - {p.name}') for p in products]), value='', page=page)
    ptype_dd = ft.Dropdown(label='نوع الصنف', width=150, options=[ft.dropdown.Option('', 'الكل'), ft.dropdown.Option('simple', 'عادي'), ft.dropdown.Option('service', 'خدمة'), ft.dropdown.Option('kit', 'Kit')], value='')
    tax_dd = ft.Dropdown(label='نسبة الضريبة', width=140, options=[ft.dropdown.Option('', 'الكل'), ft.dropdown.Option('15', '15%'), ft.dropdown.Option('5', '5%'), ft.dropdown.Option('0', '0%')], value='')
    void_dd = ft.Dropdown(label='الفواتير الملغاة', width=170, options=[ft.dropdown.Option('exclude', 'استبعاد الملغاة'), ft.dropdown.Option('include', 'تضمين الملغاة'), ft.dropdown.Option('only', 'الملغاة فقط')], value='exclude')
    search_f = ft.TextField(label='رقم الفاتورة', width=150, dense=True)
    min_f = ft.TextField(label='إجمالي من', width=110, dense=True, keyboard_type=ft.KeyboardType.NUMBER)
    max_f = ft.TextField(label='إجمالي إلى', width=110, dense=True, keyboard_type=ft.KeyboardType.NUMBER)
    filter_controls = [rng.control, branch_dd.control, cc_dd.control, party_dd.control, cat_dd.control, prod_dd.control, ptype_dd, tax_dd]
    if is_sales:
        methods = services.list_payment_methods()
        terms = services.list_pos_terminals()
        pm_dd = theme.SearchableDropdown(label='طريقة الدفع', width=190, options=opts([(m.name, m.name) for m in methods]), value='', page=page)
        term_dd = theme.SearchableDropdown(label='ماكينة الكاشير', width=220, options=opts([(str(t['id']), f"{t['code']} - {t['name']}") for t in terms]), value='', page=page)
        chan_dd = ft.Dropdown(label='القناة', width=170, options=[ft.dropdown.Option('', 'الكل'), ft.dropdown.Option('pos', 'كاشير (POS)'), ft.dropdown.Option('normal', 'فواتير عادية')], value='')
        filter_controls += [pm_dd.control, term_dd.control, chan_dd]
    filter_controls += [void_dd, search_f, min_f, max_f]

    go = [(k, v) for k, v in trade_reports.group_options(kind) if k != 'none']
    go_names = dict(go)
    levels = ['month']
    levels_box = ft.Column([], spacing=6)
    top_f = ft.TextField(label='أعلى N (اختياري)', width=140, dense=True, keyboard_type=ft.KeyboardType.NUMBER)

    def refresh_levels():
        rows = []
        for i, g in enumerate(levels):
            dd = ft.Dropdown(label=('تجميع حسب' if i == 0 else f'ثم حسب (مستوى {i + 1})'), width=260, value=g,
                             options=[ft.dropdown.Option(k, v) for k, v in go if k == g or k not in levels])
            def on_pick(e, idx=i):
                levels[idx] = e.control.value; refresh_levels(); run(e)
            dd.on_select = on_pick
            rows.append(ft.Row([ft.Text(f'{i + 1}', color=theme.TEXT_MUTED, width=18), dd, ft.IconButton(ft.Icons.CLOSE, tooltip='حذف المستوى', on_click=lambda e, idx=i: remove_level(e, idx))], spacing=6))
        if not levels:
            rows.append(ft.Text('بدون تجميع: بيتعرض تفصيل بنود الفواتير', size=12, color=theme.TEXT_MUTED))
        levels_box.controls = rows
        add_btn.disabled = len(levels) >= len(go)

    def remove_level(e, idx):
        levels.pop(idx); refresh_levels(); run(e)

    def add_level(e):
        free = [k for k, _ in go if k not in levels]
        if free:
            levels.append(free[0]); refresh_levels(); run(e)

    add_btn = ft.OutlinedButton('إضافة مستوى تجميع', icon=ft.Icons.ADD, on_click=add_level)

    kpi_row = ft.Row([], wrap=True, spacing=10)
    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(''))], rows=[])
    pager = theme.RowPager(table, page, 100)
    err = ft.Text('', color=theme.DANGER, visible=False)
    empty = ft.Text('مفيش بيانات مطابقة للفلاتر.', color=theme.TEXT_MUTED, visible=False)
    filt_text = ft.Text('', size=12, color=theme.TEXT_MUTED)

    def val(dd):
        return dd.value or None

    def collect():
        def d(v):
            return datetime.datetime.strptime(v, '%Y-%m-%d').date() if (v or '').strip() else None
        f = {'date_from': d(rng.start.value), 'date_to': d(rng.end.value), 'branch_id': val(branch_dd), 'cost_center_id': val(cc_dd), 'party_id': val(party_dd), 'category_id': val(cat_dd),
             'product_id': val(prod_dd), 'product_type': val(ptype_dd), 'tax_rate': val(tax_dd), 'voided': void_dd.value or 'exclude', 'search': search_f.value, 'min_total': min_f.value, 'max_total': max_f.value}
        if is_sales:
            f.update({'payment_method': val(pm_dd), 'terminal_id': val(term_dd), 'channel': val(chan_dd)})
        return f

    def names():
        m = {'branch_id': {str(b.id): b.name for b in branches}, 'cost_center_id': {str(c.id): c.name for c in centers}, 'party_id': {str(p.id): p.name for p in parties},
             'category_id': {str(c.id): c.name for c in cats}, 'product_id': {str(p.id): p.name for p in products}, 'channel': {'pos': 'كاشير', 'normal': 'عادية'}}
        if is_sales:
            m['terminal_id'] = {str(t['id']): t['name'] for t in services.list_pos_terminals()}
        return m

    def kpi(title, value, color=None):
        return theme.card(ft.Column([ft.Text(title, size=11, color=theme.TEXT_MUTED), ft.Text(value, size=17, weight=ft.FontWeight.BOLD, color=color)], spacing=2, tight=True), padding=12)

    def columns_for(lv):
        if not lv:
            cols = [('الفاتورة', 'label', 's'), ('التاريخ', 'date', 's'), (party_label, 'party', 's'), ('الصنف', 'product', 's'), ('الفئة', 'category', 's'), ('الكمية', 'qty', 'q'), ('السعر', 'price', 'n'),
                    ('الخصم', 'discount', 'n'), ('الصافي', 'net', 'n'), ('الضريبة', 'tax', 'n'), ('الإجمالي', 'total', 'n')]
            if is_sales:
                cols += [('التكلفة', 'cost', 'n'), ('الربح', 'profit', 'n'), ('الهامش %', 'margin', 'p')]
            return cols
        glabel = ' ← '.join(go_names.get(g, g) for g in lv)
        cols = [(glabel, 'label', 's'), ('الفواتير', 'invoices', 'q'), ('الكمية', 'qty', 'q'), ('قبل الخصم', 'gross', 'n'), ('الخصم', 'discount', 'n'), ('الصافي', 'net', 'n'), ('الضريبة', 'tax', 'n'), ('الإجمالي', 'total', 'n')]
        cols += [('التكلفة', 'cost', 'n'), ('الربح', 'profit', 'n'), ('الهامش %', 'margin', 'p')] if is_sales else [('متوسط السعر', 'avg_price', 'n')]
        cols += [('النسبة', 'share', 'bar')]
        return cols

    def fmt(v, t):
        if v is None or v == '':
            return ''
        if t == 'n':
            return f'{v:,.2f}'
        if t == 'q':
            return f'{v:,.2f}'.rstrip('0').rstrip('.') if isinstance(v, float) else f'{v:,}'
        if t == 'p':
            return f'{v:.1f}%'
        return str(v)

    def toggle(pth):
        collapsed.symmetric_difference_update({pth})
        render(); page.update()

    def fold_all(e, close):
        r = state['result']
        if not r:
            return
        collapsed.clear()
        if close:
            collapsed.update(row['path'] for row in r['rows'] if row.get('has_children'))
        render(); page.update()

    def render():
        r = state['result']
        k = r['kpis']
        cards = [kpi('عدد الفواتير', f"{k['invoices']:,}"), kpi('الكمية', f"{k['qty']:,.2f}".rstrip('0').rstrip('.')), kpi('الإجمالي قبل الخصم', f"{k['gross']:,.2f}"), kpi('الخصومات', f"{k['discount']:,.2f}"),
                 kpi('الصافي', f"{k['net']:,.2f}"), kpi('الضريبة', f"{k['tax']:,.2f}"), kpi('الإجمالي', f"{k['total']:,.2f}", theme.PRIMARY), kpi('متوسط الفاتورة', f"{k['avg_invoice']:,.2f}")]
        if is_sales:
            cards += [kpi('التكلفة التقديرية', f"{k['cost']:,.2f}"), kpi('الربح', f"{k['profit']:,.2f}", theme.SUCCESS if k['profit'] >= 0 else theme.DANGER), kpi('هامش الربح', f"{k['margin']:.1f}%"),
                      kpi('المرتجعات', f"{k['returns_total']:,.2f} ({k['returns_count']})", theme.WARNING), kpi('الإجمالي بعد المرتجعات', f"{k['net_after_returns']:,.2f}", theme.PRIMARY)]
        kpi_row.controls = cards
        cols = columns_for(r['levels'])
        table.columns = [ft.DataColumn(ft.Text(c[0], weight=ft.FontWeight.BOLD), numeric=c[2] in ('n', 'q', 'p')) for c in cols]
        multi = len(r['levels']) > 1

        def build(row):
            bold = multi and row.get('has_children')
            cells = []
            for lbl, key, t in cols:
                v = row.get(key)
                if t == 'bar':
                    cells.append(ft.DataCell(ft.Row([ft.ProgressBar(value=min(1.0, (v or 0) / 100.0), width=60, color=theme.PRIMARY), ft.Text(f'{(v or 0):.1f}%', size=11)], spacing=6)))
                else:
                    if key == 'label' and multi:
                        txt_c = ft.Text(fmt(v, t), weight=ft.FontWeight.BOLD if bold else None, size=12.5)
                        if row.get('has_children'):
                            is_c = row['path'] in collapsed
                            arrow = ft.IconButton(ft.Icons.KEYBOARD_ARROW_LEFT if is_c else ft.Icons.KEYBOARD_ARROW_DOWN, icon_size=18, tooltip='فتح' if is_c else 'طي',
                                                  on_click=lambda e, pth=row['path']: toggle(pth))
                        else:
                            arrow = ft.Container(width=40)
                        cells.append(ft.DataCell(ft.Row([ft.Container(width=18 * row['level']), arrow, txt_c], spacing=0, tight=True)))
                        continue
                    cells.append(ft.DataCell(ft.Text(fmt(v, t), weight=ft.FontWeight.BOLD if bold else None, size=12.5)))
            return ft.DataRow(cells=cells, color=ft.Colors.with_opacity(0.06, theme.PRIMARY) if bold else None)
        visible = [row for row in r['rows'] if not any(row['path'][:n] in collapsed for n in range(1, len(row['path'])))] if r['levels'] else r['rows']
        pager.set_items(visible, build, keep_page=True)
        empty.visible = not r['rows']
        filt_text.value = trade_reports.filters_text(kind, state['filters'], names())

    adv = {'viewer': None}
    adv_box = ft.Column([], visible=False)
    adv_sw = ft.Switch(label='عرض متقدم (فرز وفلترة وتجميع حر ورسم على بنود الفواتير)', value=False)

    def refresh_adv():
        from .. import report_engine as RE
        from ..report_viewer import ReportViewer, Mode
        if adv['viewer'] is None:
            cols = [RE.Col('date', 'التاريخ', RE.DATE), RE.Col('label', 'الفاتورة', bold=True), RE.Col('party', party_label, width=2), RE.Col('product', 'الصنف', width=2.4), RE.Col('category', 'الفئة'),
                    RE.Col('qty', 'الكمية', RE.QTY, 'sum'), RE.Col('price', 'السعر', RE.MONEY), RE.Col('discount', 'الخصم', RE.MONEY, 'sum'), RE.Col('net', 'الصافي', RE.MONEY, 'sum'),
                    RE.Col('tax', 'الضريبة', RE.MONEY, 'sum'), RE.Col('total', 'الإجمالي', RE.MONEY, 'sum')]
            if is_sales:
                cols += [RE.Col('cost', 'التكلفة', RE.MONEY, 'sum'), RE.Col('profit', 'الربح', RE.MONEY, 'sum'), RE.Col('margin', 'الهامش %', RE.PCT)]
            adv['viewer'] = ReportViewer(page, 'sales_adv' if is_sales else 'purchase_adv', 'تقارير المبيعات' if is_sales else 'تقارير المشتريات', cols,
                                         modes=[Mode('by_party', 'حسب ' + party_label, ['party']), Mode('by_prod', 'حسب الصنف', ['product']), Mode('by_cat', 'حسب الفئة', ['category']),
                                                Mode('by_month', 'حسب الشهر', ['date:month']), Mode('by_month_prod', 'شهر ← صنف', ['date:month', 'product'])], chart_value='total', show_export=True)
            adv_box.controls = [adv['viewer'].control]
        res = trade_reports.build_report(kind, state['filters'], [], 0)
        from ..report_viewer import normalize_rows
        adv['viewer'].set_rows(normalize_rows(res['rows'], adv['viewer'].cols))

    def on_adv(e=None):
        on = bool(adv_sw.value)
        adv_box.visible = on
        main_wrap.visible = not on
        for c in (kpi_row, filt_text, fold_row):
            c.visible = not on
        if on:
            try:
                refresh_adv(); err.visible = False
            except Exception as ex:      # noqa: BLE001
                err.value = f'تعذر تحميل العارض: {ex}'; err.visible = True
        page.update()
    adv_sw.on_change = on_adv

    def run(e=None):
        try:
            f = collect()
            state['filters'] = f
            collapsed.clear()
            top = int(top_f.value) if (top_f.value or '').strip() else 0
            state['result'] = trade_reports.build_report(kind, f, list(levels), top)
            render(); err.visible = False
            if adv_sw.value:
                refresh_adv()
        except Exception as ex:
            err.value = f'تعذر إنشاء التقرير: {ex}'; err.visible = True
        if e is not None:
            page.update()

    def clear(e):
        for dd in (branch_dd, cc_dd, party_dd, cat_dd, prod_dd) + ((pm_dd, term_dd) if is_sales else ()):
            dd.value = ''
        for dd in (ptype_dd, tax_dd) + ((chan_dd,) if is_sales else ()):
            dd.value = ''
        void_dd.value = 'exclude'
        for f in (search_f, min_f, max_f, top_f):
            f.value = ''
        levels[:] = ['month']; refresh_levels()
        run(e)

    def export_table():
        r = state['result']
        if not r:
            run()
            r = state['result']
        cols = columns_for(r['levels'])
        t = [[c[0] for c in cols]]
        styles = {}
        multi = len(r['levels']) > 1
        for row in r['rows']:
            t.append([(('    ' * row['level'] if key == 'label' and multi else '') + str(row.get(key)) if t_ in ('s',) else (round(row.get(key) or 0, 2) if row.get(key) is not None else '')) for _, key, t_ in cols])
            if multi and row.get('has_children'):
                styles[len(t) - 1] = 'section'
        k = r['totals']
        tot = []
        for _, key, t_ in cols:
            tot.append({'label': 'الإجمالي', 'invoices': k['invoices'], 'qty': round(k['qty'], 2), 'gross': round(k['gross'], 2), 'discount': round(k['discount'], 2), 'net': round(k['net'], 2), 'tax': round(k['tax'], 2),
                        'total': round(k['total'], 2), 'cost': round(k.get('cost', 0), 2), 'profit': round(k.get('profit', 0), 2), 'margin': round(k.get('margin', 0), 1), 'avg_price': round(k['avg_price'], 2)}.get(key, ''))
        t.append(tot); styles[len(t) - 1] = 'total'
        if state['filters']:
            ft_ = trade_reports.filters_text(kind, state['filters'], names())
            if ft_:
                t.insert(1, [ft_] + [''] * (len(cols) - 1)); styles = {(i + 1 if i >= 1 else i): v for i, v in styles.items()}; styles[1] = 'section'
        f = state['filters']
        return {'table': t, 'row_styles': styles, 'col_weights': [2.4 if c[2] == 's' else 1.2 for c in cols], 'date_from': f.get('date_from'), 'date_to': f.get('date_to')}

    def do_export(fmt_):
        try:
            data = export_table()
            path = (export_excel if fmt_ == 'xlsx' else export_pdf)(data, 'sales_analysis' if is_sales else 'purchase_analysis', services.downloads_dir())
            theme.open_or_download_file(page, path)
            page.overlay.append(ft.SnackBar(ft.Text(f'تم إنشاء الملف: {path}'), open=True)); page.update()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

    fold_row = ft.Row([ft.TextButton('طي الكل', icon=ft.Icons.UNFOLD_LESS, on_click=lambda e: fold_all(e, True)), ft.TextButton('فتح الكل', icon=ft.Icons.UNFOLD_MORE, on_click=lambda e: fold_all(e, False))], spacing=4)
    main_wrap = theme.card(ft.Column([empty, theme.h_scroll(table)], spacing=8), expand=True)
    refresh_levels()
    run()
    title = 'تقارير المبيعات التحليلية' if is_sales else 'تقارير المشتريات التحليلية'
    sub = 'كل الفلاتر + تجميع متعدد المستويات + ربحية ومرتجعات' if is_sales else 'كل الفلاتر + تجميع متعدد المستويات + متوسط أسعار الشراء'
    return ft.Column([
        ft.Row([theme.page_title(title, sub), ft.Container(expand=True), ft.ElevatedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: do_export('xlsx')),
                ft.ElevatedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: do_export('pdf'))]),
        theme.card(ft.Column([ft.Text('الفلاتر', size=15, weight=ft.FontWeight.BOLD), ft.Row(filter_controls, wrap=True, spacing=10),
                              levels_box, ft.Row([add_btn, top_f, theme.guard_submit(ft.FilledButton('عرض التقرير', icon=ft.Icons.SEARCH, bgcolor=theme.PRIMARY, on_click=run)),
                                      ft.TextButton('مسح الفلاتر', icon=ft.Icons.FILTER_ALT_OFF, on_click=clear)], wrap=True, spacing=10)], spacing=10)),
        err, adv_sw, kpi_row, filt_text, fold_row, main_wrap, adv_box,
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)


def build_sales_reports(page: ft.Page):
    return _build(page, 'sales')


def build_purchase_reports(page: ft.Page):
    return _build(page, 'purchase')
