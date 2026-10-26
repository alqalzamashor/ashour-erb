import datetime
import os
import flet as ft
from .. import services, theme


def build_vat_report(page: ft.Page):
    """تقرير ضريبة القيمة المضافة - شهري أو ربع سنوي: ملخص على نسق الإقرار الضريبي
    (مخرجات - مدخلات = صافي)، مطابقة بدفتر الأستاذ، تنبيهات، وتفاصيل المستندات."""
    today = datetime.date.today()
    prev_month = today.month - 1 or 12
    prev_year = today.year if today.month > 1 else today.year - 1
    prev_quarter = ((today.month - 1) // 3) or 4
    prev_q_year = today.year if ((today.month - 1) // 3) >= 1 else today.year - 1

    period_rg = ft.RadioGroup(value='monthly', content=ft.Row([ft.Radio(value='monthly', label='شهري'), ft.Radio(value='quarterly', label='ربع سنوي')], spacing=20))
    year_dd = ft.Dropdown(label='السنة', width=110, options=[ft.dropdown.Option(str(y), str(y)) for y in range(today.year + 1, today.year - 6, -1)], value=str(prev_year))
    month_dd = ft.Dropdown(label='الشهر', width=150, options=[ft.dropdown.Option(str(i + 1), n) for i, n in enumerate(services._AR_MONTHS)], value=str(prev_month))
    quarter_dd = ft.Dropdown(label='الربع', width=250, visible=False, options=[
        ft.dropdown.Option(str(i + 1), f"الربع {services._AR_QUARTERS[i]} ({services._AR_MONTHS[3 * i]} - {services._AR_MONTHS[3 * i + 2]})") for i in range(4)], value=str(prev_quarter))
    allowed = services.user_branch_ids()
    branches = [b for b in services.list_branches(True) if not allowed or b.id in allowed]
    branch_dd = ft.Dropdown(label='الفرع', width=210, options=[ft.dropdown.Option('', 'كل الفروع')] + [ft.dropdown.Option(str(b.id), f'{b.code} - {b.name}') for b in branches], value='')
    err = ft.Text('', color=theme.DANGER, visible=False, size=12)
    result = ft.Column(spacing=14)
    state = {'data': None}

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def on_period_change(e=None):
        monthly = period_rg.value == 'monthly'
        month_dd.visible = monthly; quarter_dd.visible = not monthly
        if monthly:
            year_dd.value = str(prev_year); month_dd.value = str(prev_month)
        else:
            year_dd.value = str(prev_q_year); quarter_dd.value = str(prev_quarter)
        page.update()

    def money(v, color=None, bold=False, size=13):
        return ft.Text(f'{v:,.2f}', size=size, color=color, weight=ft.FontWeight.BOLD if bold else None)

    def card(label, value, color, sub=''):
        return theme.stat_card(label, f'{value:,.2f}', color, sub, padding=16)

    def table(headers, rows, total_row=None):
        trs = [ft.DataRow(cells=[ft.DataCell(c if isinstance(c, ft.Control) else ft.Text(str(c), size=12)) for c in r]) for r in rows]
        if total_row:
            trs.append(ft.DataRow(color=theme.PRIMARY_LIGHT, cells=[ft.DataCell(c if isinstance(c, ft.Control) else ft.Text(str(c), size=12, weight=ft.FontWeight.BOLD)) for c in total_row]))
        return theme.h_scroll(ft.DataTable(columns=[ft.DataColumn(ft.Text(h)) for h in headers], rows=trs, heading_row_height=38, data_row_min_height=34))

    def render(v):
        sm, sl, pu, lg = v['summary'], v['sales'], v['purchases'], v['ledger']
        status_txt, status_color = {'payable': ('صافي الضريبة المستحقة للسداد', theme.DANGER),
                                    'refundable': ('رصيد دائن لصالح المنشأة (استرداد / ترحيل)', theme.SUCCESS),
                                    'zero': ('لا يوجد صافي مستحق', theme.TEXT_MUTED)}[sm['status']]
        cards = ft.Row([card('ضريبة المخرجات (المبيعات)', sm['output_tax'], theme.PRIMARY, f"{sl['count']} فاتورة مبيعات"),
                        card('ضريبة المدخلات (المشتريات)', sm['input_tax'], theme.WARNING, f"{pu['count']} مستند مشتريات"),
                        card(status_txt, abs(sm['net_tax']), status_color, 'المخرجات - المدخلات')], wrap=True, spacing=12)
        warn = []
        if v['warnings']:
            warn = [ft.Container(bgcolor=theme.WARNING_LIGHT, border_radius=10, padding=ft.Padding(left=14, right=14, top=10, bottom=10), content=ft.Column(
                [ft.Row([ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=theme.WARNING, size=18), ft.Text(f"{len(v['warnings'])} تنبيه محتاج مراجعة قبل تقديم الإقرار", weight=ft.FontWeight.BOLD, color=theme.WARNING_TEXT)], spacing=6)]
                + [ft.Text('• ' + w, size=12, color=theme.WARNING_TEXT) for w in v['warnings']], spacing=4, tight=True))]
        else:
            warn = [ft.Container(bgcolor=theme.SUCCESS_LIGHT, border_radius=10, padding=ft.Padding(left=14, right=14, top=10, bottom=10),
                                 content=ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, color=theme.SUCCESS, size=18), ft.Text('مفيش تنبيهات - الدفتر مطابق للمستندات والبيانات الضريبية مكتملة', color=theme.SUCCESS_TEXT, size=12)], spacing=6))]

        sales_tbl = table(['البند', 'المبلغ الخاضع', 'الضريبة'],
                          [[r['label'], money(r['base']), money(r['tax'])] for r in sl['rows']]
                          + [[f"   منها B2B - {sl['b2b']['count']} فاتورة", money(sl['b2b']['base']), money(sl['b2b']['tax'])],
                             [f"   منها B2C - {sl['b2c']['count']} فاتورة", money(sl['b2c']['base']), money(sl['b2c']['tax'])]],
                          ['إجمالي المبيعات', money(sl['total_base'], bold=True), money(sl['total_tax'], theme.PRIMARY, True)])
        purch_tbl = table(['البند', 'المبلغ', 'الضريبة', 'عدد المستندات'],
                          [[r['label'], money(r['base']), money(r['tax']), str(r['count'])] for r in pu['rows']],
                          ['إجمالي المشتريات', money(pu['total_base'], bold=True), money(pu['total_tax'], theme.WARNING, True), str(pu['count'])])
        gl_tbl = table(['البند', 'حسب المستندات', 'حسب دفتر الأستاذ', 'الفرق'],
                       [['ضريبة المخرجات', money(lg['output_docs']), money(lg['output_gl']), money(lg['output_diff'], theme.DANGER if abs(lg['output_diff']) > 0.05 else theme.SUCCESS, True)],
                        ['ضريبة المدخلات', money(lg['input_docs']), money(lg['input_gl']), money(lg['input_diff'], theme.DANGER if abs(lg['input_diff']) > 0.05 else theme.SUCCESS, True)],
                        ['الصافي (مخرجات - مدخلات)', money(sm['net_tax']), money(lg['net_gl']), money(round(lg['net_gl'] - sm['net_tax'], 2))]])
        sales_docs = table(['التاريخ', 'رقم الفاتورة', 'العميل', 'الرقم الضريبي', 'النوع', 'المبلغ الخاضع', 'الضريبة', 'الإجمالي'],
                           [[x['date'].strftime('%Y-%m-%d'), x['number'], x['party'], x['vat_number'] or '-', x['kind'], money(x['base']), money(x['tax']), money(x['total'])] for x in sl['invoices']])
        purch_docs = table(['التاريخ', 'المصدر', 'رقم الفاتورة', 'المورد', 'الرقم الضريبي', 'المبلغ', 'الضريبة', 'الإجمالي'],
                           [[x['date'].strftime('%Y-%m-%d'), x['source'], x['number'], x['party'], x['vat_number'] or ft.Text('ناقص', size=12, color=theme.DANGER, weight=ft.FontWeight.BOLD),
                             money(x['base']), money(x['tax']), money(x['total'])] for x in pu['documents']])

        def section(title, content, icon):
            return theme.card(ft.Column([theme.section_title(title, icon), content], spacing=10))

        def tile(title, subtitle, content):
            return ft.ExpansionTile(title=ft.Text(title, weight=ft.FontWeight.BOLD), subtitle=ft.Text(subtitle, size=12, color=theme.TEXT_MUTED), expanded=False,
                                    controls=[ft.Container(content=content, padding=ft.Padding(left=8, right=8, top=0, bottom=10))])

        result.controls = [
            ft.Row([ft.Text(f"{v['period']['label']}", size=17, weight=ft.FontWeight.BOLD, color=theme.PRIMARY_TEXT), ft.Container(expand=True),
                    ft.OutlinedButton('تفاصيل المبيعات', icon=ft.Icons.TABLE_VIEW, tooltip='تفاصيل فواتير المبيعات Excel', on_click=lambda e: export('vat_sales_details', 'excel')),
                    ft.OutlinedButton('تفاصيل المشتريات', icon=ft.Icons.TABLE_VIEW, tooltip='تفاصيل مستندات المشتريات Excel', on_click=lambda e: export('vat_purchases_details', 'excel')),
                    ft.OutlinedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('vat_return', 'excel')),
                    ft.OutlinedButton('طباعة كاملة PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('vat_return', 'pdf')),
                    ft.FilledButton('طباعة الإقرار PDF', icon=ft.Icons.PRINT_OUTLINED, bgcolor=theme.PRIMARY, tooltip='أولًا: المخرجات - ثانيًا: المدخلات - ثالثًا: صافي الضريبة (بدون المطابقة والتنبيهات)',
                                    on_click=lambda e: export('vat_return_summary', 'pdf'))], spacing=8),
            cards, *warn,
            section('أولًا: ضريبة المخرجات (المبيعات)', sales_tbl, ft.Icons.TRENDING_UP),
            section('ثانيًا: ضريبة المدخلات (المشتريات والأصول وفواتير العهد)', purch_tbl, ft.Icons.TRENDING_DOWN),
            section('ثالثًا: المطابقة مع دفتر الأستاذ', gl_tbl, ft.Icons.BALANCE_OUTLINED),
            theme.card(ft.Column([tile(f"تفاصيل فواتير المبيعات - {sl['count']} فاتورة", 'التاريخ، العميل، الرقم الضريبي، النوع، المبلغ والضريبة', sales_docs),
                                  tile(f"تفاصيل مستندات المشتريات - {pu['count']} مستند", 'فواتير المشتريات والأصول وفواتير العهد برقم المورد الضريبي', purch_docs)], spacing=0), padding=8),
        ]

    def export(report_type, kind):
        try:
            from ..report_export import export_pdf, export_excel
            v = state['data']
            if not v:
                return
            data = {'vat': v, 'date_from': v['period']['date_from'], 'date_to': v['period']['date_to'], 'title_suffix': v['period']['label']}
            out_dir = os.path.join(services.APP_DIR, 'exports')
            path = (export_pdf if kind == 'pdf' else export_excel)(data, report_type, out_dir)
            theme.open_or_download_file(page, path); snack('تم إنشاء الملف')
        except Exception as ex:
            snack(f'تعذر التصدير: {ex}')

    def run(e=None):
        try:
            v = services.vat_return(period_rg.value, int(year_dd.value), month_dd.value, quarter_dd.value, int(branch_dd.value) if branch_dd.value else None)
            state['data'] = v; err.visible = False
            render(v)
        except Exception as ex:
            err.value = str(ex); err.visible = True; result.controls = []
        page.update()

    period_rg.on_change = on_period_change
    on_period_change()
    run()
    return ft.Column([
        theme.page_title('تقرير ضريبة القيمة المضافة', 'شهري أو ربع سنوي - ضريبة المخرجات والمدخلات وصافي المستحق مع المطابقة بدفتر الأستاذ'),
        ft.Container(height=8),
        theme.card(ft.Row([period_rg, year_dd, month_dd, quarter_dd, branch_dd, ft.FilledButton('عرض التقرير', icon=ft.Icons.ASSESSMENT_OUTLINED, bgcolor=theme.PRIMARY, on_click=run)], wrap=True, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER), padding=14),
        err, result,
    ], expand=True, spacing=12, scroll=ft.ScrollMode.AUTO)
