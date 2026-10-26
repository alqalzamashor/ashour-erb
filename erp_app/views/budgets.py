import datetime
import flet as ft
from .. import services, theme
from ..report_export import export_excel, export_pdf


def build_budgets(page, user=None):
    if user and not services.user_has_action(user, 'budgets', 'view'):
        return theme.card(ft.Text('ليس لديك صلاحية الموازنات التقديرية.', color=theme.DANGER))
    branches=services.list_branches(True); allowed=services.user_branch_ids(user)
    if allowed: branches=[b for b in branches if b.id in allowed]
    accounts=services.list_accounts(); centers=services.list_cost_centers(True)
    if services.user_cost_center_ids(user): centers=[c for c in centers if c.id in services.user_cost_center_ids(user)]
    rng=theme.DateRangeField('مدة الموازنة',page,width=290); df,dt=rng.start,rng.end
    branch=ft.Dropdown(label='الفرع',width=220,options=[ft.dropdown.Option('', 'كل الفروع / مشترك')]+[ft.dropdown.Option(str(b.id),f'{b.code} - {b.name}') for b in branches],value='')
    center=ft.Dropdown(label='مركز التكلفة',width=230,options=[ft.dropdown.Option('', 'كل المراكز')]+[ft.dropdown.Option(str(c.id),f'{c.code} - {c.name}') for c in centers],value='')
    account=theme.SearchableDropdown(label='الحساب',width=270,options=[(str(a.id),f'{a.code} - {a.name}') for a in accounts if a.account_type in ('income','expense')])
    amount=ft.TextField(label='المبلغ التقديري',width=150); name=ft.TextField(label='اسم الموازنة',width=180,value='موازنة تشغيلية'); notes=ft.TextField(label='ملاحظات',width=220)
    table=ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['الحساب','الفرع','مركز التكلفة','من','إلى','الموازنة','إجراء']],rows=[])
    vs=ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['الحساب','النوع','الموازنة','فعلي','الانحراف','% التحقيق']],rows=[])
    status=ft.Text('',color=theme.DANGER)
    def parse(v): return datetime.datetime.strptime(v.strip(),'%Y-%m-%d') if v and v.strip() else None
    def msg(x): status.value=str(x);page.update()
    def bid(): return int(branch.value) if branch.value else None
    def cid(): return int(center.value) if center.value else None
    def refresh(e=None):
        try:
            rows=services.list_budget_lines(parse(df.value),parse(dt.value),bid(),cid())
            table.rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(f'{x.account.code} - {x.account.name}')),ft.DataCell(ft.Text(x.branch.name if x.branch else 'مشترك')),ft.DataCell(ft.Text(x.cost_center.name if x.cost_center else 'مشترك')),ft.DataCell(ft.Text(x.date_from.strftime('%Y-%m-%d'))),ft.DataCell(ft.Text(x.date_to.strftime('%Y-%m-%d'))),ft.DataCell(ft.Text(f'{x.budget_amount:,.2f}')),ft.DataCell(ft.TextButton('حذف',on_click=lambda e,i=x.id:delete(i)))]) for x in rows]
            d=services.budget_vs_actual(parse(df.value),parse(dt.value),bid(),cid())
            vs.rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(f"{x['code']} - {x['account']}")),ft.DataCell(ft.Text('إيراد' if x['type']=='income' else 'مصروف')),ft.DataCell(ft.Text(f"{x['budget']:,.2f}")),ft.DataCell(ft.Text(f"{x['actual']:,.2f}")),ft.DataCell(ft.Text(f"{x['variance']:,.2f}",color=theme.SUCCESS if ((x['type']=='income' and x['variance']>=0) or (x['type']=='expense' and x['variance']<=0)) else theme.DANGER)),ft.DataCell(ft.Text(f"{x['achievement_pct']:.2f}%"))]) for x in d]
            status.value='';page.update()
        except Exception as ex:msg(ex)
    def add(e=None):
        try:
            if not account.value: raise ValueError('اختر حساب الإيراد أو المصروف')
            services.create_budget_line(name.value,parse(df.value),parse(dt.value),int(account.value),float(amount.value or 0),bid(),cid(),notes.value)
            amount.value='';refresh()
        except Exception as ex:msg(ex)
    def delete(i):
        theme.confirm(page, 'حذف بند موازنة', "هتحذف بند الموازنة ده. متأكد؟", lambda: _do_delete(i), yes_label='حذف')

    def _do_delete(i):
        try:services.delete_budget_line(i);refresh()
        except Exception as ex:msg(ex)
    def export(kind):
        try:
            data={'rows':services.budget_vs_actual(parse(df.value),parse(dt.value),bid(),cid()),'date_from':parse(df.value),'date_to':parse(dt.value)}
            path=export_pdf(data,'budget_vs_actual',services.downloads_dir()) if kind=='pdf' else export_excel(data,'budget_vs_actual',services.downloads_dir());msg(f'تم إنشاء التقرير: {path}')
        except Exception as ex:msg(ex)
    return ft.Column([theme.page_title('الموازنات التقديرية','Budget لكل فرع ومركز تكلفة ومقارنة Actual vs Budget'),theme.card(ft.Column([ft.Row([rng.control,branch,center,account.control],wrap=True),ft.Row([name,amount,notes,ft.FilledButton('إضافة موازنة',icon=ft.Icons.ADD,on_click=add),ft.OutlinedButton('تحديث',on_click=refresh),ft.OutlinedButton('PDF',on_click=lambda e:export('pdf')),ft.OutlinedButton('Excel',on_click=lambda e:export('excel'))],wrap=True)])),theme.card(ft.Column([ft.Text('بنود الموازنة',size=16,weight=ft.FontWeight.BOLD),theme.h_scroll(table)])),theme.card(ft.Column([ft.Text('Actual vs Budget',size=16,weight=ft.FontWeight.BOLD),theme.h_scroll(vs)])),status],expand=True,scroll=ft.ScrollMode.AUTO)
