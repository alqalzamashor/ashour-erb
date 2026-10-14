import os, datetime
import flet as ft
from .. import services, theme
from ..db import Account, Product, Customer, Supplier, Location
from ..report_export import export_excel, export_pdf


def build_reports(page: ft.Page):
    rng=theme.DateRangeField('الفترة', page, width=290); df,dt=rng.start,rng.end
    account=theme.SearchableDropdown(label='الحساب', width=230, options=[('', 'كل الحسابات')])
    product=theme.SearchableDropdown(label='الصنف', width=230, options=[('', 'كل الأصناف')])
    customer=theme.SearchableDropdown(label='العميل', width=230, options=[('', 'كل العملاء')])
    supplier=theme.SearchableDropdown(label='المورد', width=230, options=[('', 'كل الموردين')])
    location=theme.SearchableDropdown(label='المخزن', width=200, options=[('', 'كل المخازن')])
    branches=services.list_branches(True); allowed=services.user_branch_ids(); branches=[b for b in branches if not allowed or b.id in allowed]; branch=ft.Dropdown(label='الفرع', width=220, options=[ft.dropdown.Option('', 'كل الفروع')]+[ft.dropdown.Option(str(b.id),f'{b.code} - {b.name}') for b in branches])
    centers=services.list_cost_centers(True); center=ft.Dropdown(label='مركز التكلفة', width=220, options=[ft.dropdown.Option('', 'كل المراكز')]+[ft.dropdown.Option(str(c.id),f'{c.code} - {c.name}') for c in centers])
    tabs=theme.SimpleTabs(page)
    state={'data':None,'type':'trial'}

    def parse_date(v):
        if not v.strip(): return None
        try:return datetime.datetime.strptime(v.strip(),'%Y-%m-%d')
        except: raise ValueError('التاريخ يجب أن يكون بالشكل YYYY-MM-DD')

    def load_filters():
        with services.get_session() as s:
            _pids = {a.parent_id for a in s.query(Account).all() if a.parent_id}
            account.options = [('', 'كل الحسابات')] + [(str(a.id), f'{a.code} - {a.name}' + (' (رئيسي)' if a.id in _pids else '')) for a in s.query(Account).order_by(Account.code).all()]
            product.options = [('', 'كل الأصناف')] + [(str(p.id), f'{p.sku} - {p.name}') for p in s.query(Product).filter(Product.is_active.is_(True)).order_by(Product.sku).all()]
            customer.options = [('', 'كل العملاء')] + [(str(c.id), c.name) for c in s.query(Customer).order_by(Customer.name).all()]
            supplier.options = [('', 'كل الموردين')] + [(str(x.id), x.name) for x in s.query(Supplier).order_by(Supplier.name).all()]
            location.options = [('', 'كل المخازن')] + [(str(l.id), l.name) for l in s.query(Location).order_by(Location.name).all()]

    def money(v): return f'{float(v or 0):,.2f}'
    def render_table(rows, keys, cols):
        main_codes = services.main_account_codes()
        def is_main(r):
            return 'code' in keys and str(r.get('code','') or '') in main_codes
        def cell(r, k):
            m = is_main(r)
            return ft.DataCell(ft.Text(str(r.get(k,'')), weight=ft.FontWeight.W_800 if m else None, color=theme.PRIMARY_TEXT if m else None))
        tbl = ft.DataTable(columns=[ft.DataColumn(ft.Text(c)) for c in cols], rows=[], heading_row_height=40, data_row_min_height=34)
        theme.RowPager(tbl, page, 200).set_rows([ft.DataRow(color=theme.MAIN_ROW_BG if is_main(r) else None, cells=[cell(r, k) for k in keys]) for r in rows], keep_page=False)
        return theme.h_scroll(tbl)
    def financial_card(title, value, subtitle=''):
        return theme.card(ft.Column([ft.Text(title,size=13,color=theme.TEXT_MUTED),ft.Text(money(value),size=21,weight=ft.FontWeight.BOLD),ft.Text(subtitle,size=11,color=theme.TEXT_MUTED)],spacing=3))

    def build_tabs(d):
        income=services.detailed_income_statement(d['date_from'],d['date_to'],int(branch.value) if branch.value else None,int(center.value) if center.value else None)
        bs=services.detailed_balance_sheet(d['date_to'] or datetime.datetime.now(),int(branch.value) if branch.value else None,int(center.value) if center.value else None)
        cf=services.cash_flow_statement(d['date_from'],d['date_to'],int(branch.value) if branch.value else None,int(center.value) if center.value else None)
        state['income'],state['balance_sheet'],state['cash_flow']=income,bs,cf
        tabs.set_tabs([
            ('ملخص', ft.Column([ft.Row([financial_card('الإيرادات',d['income']),financial_card('المصروفات',d['expense']),financial_card('صافي الربح',d['profit']),financial_card('إجمالي الأصول',d['assets'])],wrap=True),ft.Row([financial_card('الالتزامات',d['liabilities']),financial_card('حقوق الملكية + الربح',d['equity_with_profit']),financial_card('نقدية ختامية',cf['closing_cash'])],wrap=True)],scroll=ft.ScrollMode.AUTO)),
            ('ميزان المراجعة', render_table(d['trial_balance'],['code','name','debit','credit','balance'],['الكود','الحساب','مدين','دائن','الرصيد'])),
            ('قائمة الدخل', ft.Column([ft.Text(f"إجمالي الإيرادات: {money(income['total_income'])}    إجمالي المصروفات: {money(income['total_expense'])}    صافي الربح: {money(income['net_profit'])}",size=15,weight=ft.FontWeight.BOLD),render_table(income['income'],['code','name','amount'],['الكود','الإيراد','المبلغ']),ft.Divider(),render_table(income['expense'],['code','name','amount'],['الكود','المصروف','المبلغ'])],scroll=ft.ScrollMode.AUTO)),
            ('الميزانية العمومية', ft.Column([ft.Text(f"الأصول: {money(bs['total_assets'])} | الالتزامات: {money(bs['total_liabilities'])} | حقوق الملكية: {money(bs['total_equity'])} | فرق التوازن: {money(bs['balance_gap'])}",size=15,weight=ft.FontWeight.BOLD),ft.Text('الأصول',size=16,weight=ft.FontWeight.BOLD),render_table(bs['assets'],['code','name','amount'],['الكود','الحساب','المبلغ']),ft.Text('الالتزامات',size=16,weight=ft.FontWeight.BOLD),render_table(bs['liabilities'],['code','name','amount'],['الكود','الحساب','المبلغ']),ft.Text('حقوق الملكية',size=16,weight=ft.FontWeight.BOLD),render_table(bs['equity'],['code','name','amount'],['الكود','الحساب','المبلغ'])],scroll=ft.ScrollMode.AUTO)),
            ('التدفقات النقدية', ft.Column([
                ft.Text(f"الرصيد الافتتاحي: {money(cf['opening_cash'])}    |    صافي التغير: {money(cf['net'])}    |    الرصيد الختامي: {money(cf['closing_cash'])}", size=15, weight=ft.FontWeight.BOLD),
                ft.Text('الأنشطة التشغيلية', size=16, weight=ft.FontWeight.BOLD, color=theme.PRIMARY),
                ft.Text('مقبوضات (Cash In)', size=13, color=theme.SUCCESS),
                render_table(cf['operating_in'], ['description', 'amount'], ['البيان', 'المبلغ']),
                ft.Text('مدفوعات (Cash Out)', size=13, color=theme.DANGER),
                render_table(cf['operating_out'], ['description', 'amount'], ['البيان', 'المبلغ']),
                ft.Text(f"صافي التدفق النقدي من النشاط التشغيلي: {money(cf['net_operating'])}", weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Text('الأنشطة الاستثمارية', size=16, weight=ft.FontWeight.BOLD, color=theme.PRIMARY),
                ft.Text('مقبوضات (Cash In)', size=13, color=theme.SUCCESS),
                render_table(cf['investing_in'], ['description', 'amount'], ['البيان', 'المبلغ']),
                ft.Text('مدفوعات (Cash Out)', size=13, color=theme.DANGER),
                render_table(cf['investing_out'], ['description', 'amount'], ['البيان', 'المبلغ']),
                ft.Text(f"صافي التدفق النقدي من النشاط الاستثماري: {money(cf['net_investing'])}", weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Text('الأنشطة التمويلية', size=16, weight=ft.FontWeight.BOLD, color=theme.PRIMARY),
                ft.Text('مقبوضات (Cash In)', size=13, color=theme.SUCCESS),
                render_table(cf['financing_in'], ['description', 'amount'], ['البيان', 'المبلغ']),
                ft.Text('مدفوعات (Cash Out)', size=13, color=theme.DANGER),
                render_table(cf['financing_out'], ['description', 'amount'], ['البيان', 'المبلغ']),
                ft.Text(f"صافي التدفق النقدي من النشاط التمويلي: {money(cf['net_financing'])}", weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Text(
                    f"فرق غير مفسَّر (Unexplained Difference): {money(cf['unexplained'])}",
                    weight=ft.FontWeight.BOLD,
                    color=theme.DANGER if abs(cf['unexplained']) > 0.01 else theme.SUCCESS,
                ) if abs(cf['unexplained']) > 0.01 else ft.Text('لا يوجد فرق غير مفسَّر - القائمة متوازنة تماماً ✓', color=theme.SUCCESS),
            ], scroll=ft.ScrollMode.AUTO)),
            ('دفتر الأستاذ', render_table(d['ledger'],['date','number','code','account','description','debit','credit'],['التاريخ','القيد','الكود','الحساب','البيان','مدين','دائن'])),
            ('حركة المخزون', render_table(d['moves'],['date','sku','product','location','direction','quantity','unit_cost','value','reference'],['التاريخ','الكود','الصنف','المخزن','الحركة','الكمية','تكلفة الوحدة','القيمة','المرجع'])),
            ('المبيعات', render_table(d['sales'],['date','number','party','total'],['التاريخ','الفاتورة','العميل','الإجمالي'])),
            ('المشتريات', render_table(d['purchases'],['date','number','party','total'],['التاريخ','الفاتورة','المورد','الإجمالي'])),
        ])

    def refresh(e=None):
        try:
            d=services.report_data(parse_date(df.value),parse_date(dt.value),int(location.value) if location.value else None,int(account.value) if account.value else None,int(product.value) if product.value else None,int(customer.value) if customer.value else None,int(supplier.value) if supplier.value else None,int(branch.value) if branch.value else None,int(center.value) if center.value else None)
            state['data']=d; build_tabs(d); page.update()
        except Exception as ex: page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True)); page.update()

    def do_export(kind):
        if state['data'] is None: refresh()
        try:
            idx=tabs.selected_index
            mapping={1:'trial',2:'income',3:'balance_sheet',4:'cash_flow',5:'ledger',6:'stock',7:'sales',8:'purchases'}
            rtype=mapping.get(idx,'trial')
            if rtype=='income': data=state['income']
            elif rtype=='balance_sheet': data=state['balance_sheet']
            elif rtype=='cash_flow': data=state['cash_flow']
            else: data=state['data']
            path=(export_excel if kind=='xlsx' else export_pdf)(data,rtype,services.downloads_dir())
            theme.open_or_download_file(page, path)
            page.overlay.append(ft.SnackBar(ft.Text(f'تم إنشاء الملف: {path}'), open=True)); page.update()
        except Exception as ex: page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

    load_filters()
    df.value=f'{datetime.datetime.now().year}-01-01'; dt.value=f'{datetime.datetime.now():%Y-%m-%d}'
    return ft.Column([
        theme.page_title('التقارير الاحترافية','قوائم مالية تفصيلية، تدفقات نقدية، دفتر أستاذ ومخزون مع طباعة رسمية'),
        ft.Row([rng.control,branch,center,location.control,account.control],wrap=True),
        ft.Row([product.control,customer.control,supplier.control,ft.ElevatedButton('تحديث التقرير',icon=ft.Icons.REFRESH,on_click=refresh),ft.ElevatedButton('Excel',icon=ft.Icons.TABLE_VIEW,on_click=lambda e:do_export('xlsx')),ft.ElevatedButton('PDF',icon=ft.Icons.PICTURE_AS_PDF,on_click=lambda e:do_export('pdf'))],wrap=True),
        tabs.control,
    ],expand=True)
