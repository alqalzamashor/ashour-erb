import datetime
import flet as ft
from .. import services, theme
from ..report_export import export_excel, export_pdf

def build_advanced_reports(page):
    def datefield(label):return theme.DateField(label,page,width=155)
    a1,b1,a2,b2=[datefield(x) for x in ['فترة 1 من','فترة 1 إلى','فترة 2 من','فترة 2 إلى']]
    _asw=max(180,theme._page_w()-72) if theme._page_w() else 180
    as1=theme.DateField('ميزانية حتى تاريخ 1',page,width=_asw);as2=theme.DateField('ميزانية حتى تاريخ 2',page,width=_asw)
    tabs=theme.SimpleTabs(page); state={}
    def p(v):return datetime.datetime.strptime(v.strip(),'%Y-%m-%d') if v and v.strip() else None
    def table(rows,keys,heads):return theme.h_scroll(ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in heads],rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(str(r.get(k,'')))) for k in keys]) for r in rows],heading_row_height=38))
    def refresh_income(e=None):
        try:
            d=services.comparative_income_statement(p(a1.value),p(b1.value),p(a2.value),p(b2.value));state['income_compare']=d;tabs.set_tab_content(0,ft.Column([ft.Text(f"الفترة 1: {d['period1']['net_profit']:,.2f} | الفترة 2: {d['period2']['net_profit']:,.2f}",size=16,weight=ft.FontWeight.BOLD),table(d['rows'],['code','name','period1','period2','difference','change_pct'],['الكود','الحساب','الفترة 1','الفترة 2','الفرق','% التغير'])],scroll=ft.ScrollMode.AUTO));page.update()
        except Exception as ex:page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True, data='error')); page.update()
    def refresh_bs(e=None):
        try:
            d=services.comparative_balance_sheet(p(as1.value),p(as2.value));state['bs_compare']=d;tabs.set_tab_content(1,ft.Column([ft.Text(f"أصول: {d['period1']['total_assets']:,.2f} → {d['period2']['total_assets']:,.2f} | التزامات: {d['period2']['total_liabilities']:,.2f}",size=16,weight=ft.FontWeight.BOLD),table(d['rows'],['code','name','type','period1','period2','difference'],['الكود','الحساب','النوع','تاريخ 1','تاريخ 2','الفرق'])],scroll=ft.ScrollMode.AUTO));page.update()
        except Exception as ex:page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True, data='error')); page.update()
    def equity(e=None):
        try:
            d=services.statement_of_changes_in_equity(p(a1.value),p(b1.value));state['equity']=d;tabs.set_tab_content(2,ft.Column([ft.Text(f"حقوق الملكية الافتتاحية: {d['opening_equity']:,.2f} | الربح: {d['net_profit']:,.2f} | الختامي: {d['closing_equity']:,.2f}",size=16,weight=ft.FontWeight.BOLD),table(d['movements'],['code','name','amount'],['الكود','الحساب','التغير'])],scroll=ft.ScrollMode.AUTO));page.update()
        except Exception as ex:page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True, data='error')); page.update()
    tabs.set_tabs([('أرباح وخسائر مقارنة',ft.Text('أدخل الفترتين ثم اضغط عرض')),('ميزانية مقارنة',ft.Text('أدخل تاريخي المقارنة ثم اضغط عرض')),('تغيرات حقوق الملكية',ft.Text('أدخل الفترة ثم اضغط عرض'))])
    return ft.Column([theme.page_title('التقارير المقارنة وحقوق الملكية','مقارنة الفترات، الميزانية، الأرباح والخسائر، وتغيرات حقوق الملكية'),theme.card(ft.Column([ft.Row([a1.control,b1.control,a2.control,b2.control,ft.FilledButton('عرض الأرباح والخسائر',on_click=refresh_income)] ,wrap=True),ft.Row([as1.control,as2.control,ft.FilledButton('عرض الميزانية',on_click=refresh_bs),ft.OutlinedButton('عرض حقوق الملكية',on_click=equity)],wrap=True)])),tabs.control],expand=True,scroll=ft.ScrollMode.AUTO)
