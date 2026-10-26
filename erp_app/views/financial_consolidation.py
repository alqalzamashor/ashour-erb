import datetime
import flet as ft
from .. import services, theme
from ..report_export import export_excel, export_pdf


def build_financial_consolidation(page: ft.Page):
    branches=services.list_branches(True)
    allowed=services.user_branch_ids()
    if allowed: branches=[b for b in branches if b.id in allowed]
    branch_options=[ft.dropdown.Option('', 'كل الفروع - موحد')] + [ft.dropdown.Option(str(b.id), f'{b.code} - {b.name}') for b in branches]
    branch=ft.Dropdown(label='الفرع',width=250,options=branch_options,value='')
    center=ft.Dropdown(label='مركز التكلفة',width=250,options=[ft.dropdown.Option('', 'كل مراكز التكلفة')]+[ft.dropdown.Option(str(c.id),f'{c.code} - {c.name}') for c in services.list_cost_centers(True)],value='')
    rng=theme.DateRangeField('الفترة',page,width=290); df,dt=rng.start,rng.end
    asof=theme.DateField('الميزانية حتى',page,width=150)
    tabs=theme.SimpleTabs(page)
    state={}
    def parse(v): return datetime.datetime.strptime(v.strip(),'%Y-%m-%d') if v and v.strip() else None
    def msg(x): page.overlay.append(ft.SnackBar(ft.Text(str(x)), open=True)); page.update()
    def bid(): return int(branch.value) if branch.value else None
    def cid(): return int(center.value) if center.value else None
    def render(rows,heads,keys):
        from ..report_viewer import smart_table
        return smart_table(page,'fc_'+'_'.join(keys),rows,keys,heads)
    def do_income(e=None):
        try:
            d=services.detailed_income_statement(parse(df.value),parse(dt.value),bid(),cid()); state['income']=d
            rows=[{'section':'إيراد','code':r['code'],'name':r['name'],'amount':f"{r['amount']:,.2f}"} for r in d['income']]+[{'section':'مصروف','code':r['code'],'name':r['name'],'amount':f"{r['amount']:,.2f}"} for r in d['expense']]
            tabs.set_tab_content(0,ft.Column([ft.Text(f"الإيرادات {d['total_income']:,.2f} | المصروفات {d['total_expense']:,.2f} | صافي الربح {d['net_profit']:,.2f}",size=17,weight=ft.FontWeight.BOLD),render(rows,['القسم','الكود','الحساب','المبلغ'],['section','code','name','amount'])],scroll=ft.ScrollMode.AUTO));page.update()
        except Exception as ex:msg(ex)
    def do_balance(e=None):
        try:
            d=services.detailed_balance_sheet(parse(asof.value),bid(),cid());state['balance']=d
            rows=[]
            for key,title in [('assets','الأصول'),('liabilities','الالتزامات'),('equity','حقوق الملكية')]: rows += [{'section':title,'code':r['code'],'name':r['name'],'amount':f"{r['amount']:,.2f}"} for r in d[key]]
            tabs.set_tab_content(1,ft.Column([ft.Text(f"الأصول {d['total_assets']:,.2f} | الالتزامات {d['total_liabilities']:,.2f} | حقوق الملكية {d['total_equity']:,.2f} | فرق التوازن {d['balance_gap']:,.2f}",size=17,weight=ft.FontWeight.BOLD),render(rows,['القسم','الكود','الحساب','المبلغ'],['section','code','name','amount'])],scroll=ft.ScrollMode.AUTO));page.update()
        except Exception as ex:msg(ex)
    def do_centers(e=None):
        try:
            rows=services.cost_center_statement(parse(df.value),parse(dt.value),bid()); state['cost_center']={'rows':rows,'date_from':parse(df.value),'date_to':parse(dt.value)}
            tabs.set_tab_content(2,ft.Column([render(rows,['الكود','مركز التكلفة','الإيرادات','المصروفات','صافي الربح'],['code','name','income','expense','profit'])],scroll=ft.ScrollMode.AUTO));page.update()
        except Exception as ex:msg(ex)
    def export_current(kind):
        try:
            idx=tabs.selected_index
            if idx==0:
                d=state.get('income') or services.detailed_income_statement(parse(df.value),parse(dt.value),bid(),cid());typ='consolidated_income' if not bid() else 'branch_income'
            elif idx==1:
                d=state.get('balance') or services.detailed_balance_sheet(parse(asof.value),bid(),cid());typ='consolidated_balance' if not bid() else 'branch_balance'
            else:
                d=state.get('cost_center') or {'rows':services.cost_center_statement(parse(df.value),parse(dt.value),bid())};typ='cost_center'
            path=export_pdf(d,typ,services.downloads_dir()) if kind=='pdf' else export_excel(d,typ,services.downloads_dir());msg(f'تم إنشاء التقرير: {path}')
        except Exception as ex:msg(ex)
    tabs.set_tabs([('قائمة الدخل حسب الفرع',ft.Text('اختر الفرع أو كل الفروع ثم اضغط عرض')),('الميزانية حسب الفرع',ft.Text('اختر التاريخ ثم اضغط عرض')),('تحليل مراكز التكلفة',ft.Text('اضغط عرض'))])
    return ft.Column([theme.page_title('القوائم المالية والفروع','تقارير فرعية وموحدة مع تجميع الحسابات الأب ومراكز التكلفة'),theme.card(ft.Column([ft.Row([branch,center,rng.control,asof.control],wrap=True),ft.Row([ft.FilledButton('عرض قائمة الدخل',on_click=do_income),ft.FilledButton('عرض الميزانية',on_click=do_balance),ft.FilledButton('تحليل مراكز التكلفة',on_click=do_centers),ft.OutlinedButton('PDF',on_click=lambda e:export_current('pdf')),ft.OutlinedButton('Excel',on_click=lambda e:export_current('excel'))],wrap=True)])),tabs.control],expand=True,scroll=ft.ScrollMode.AUTO)
