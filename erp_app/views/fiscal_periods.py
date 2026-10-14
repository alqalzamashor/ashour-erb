import datetime
import flet as ft
from .. import services, theme


def build_fiscal_periods(page: ft.Page):
    name=ft.TextField(label='اسم الفترة', width=220); start=theme.DateField('من تاريخ',page,width=170); end=theme.DateField('إلى تاريخ',page,width=170)
    table=ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['الفترة','من','إلى','الحالة','قيد الإقفال','إجراء']],rows=[])
    def parse(v): return datetime.datetime.strptime(v,'%Y-%m-%d')
    def refresh(e=None):
        table.rows=[]
        for p in services.list_fiscal_periods():
            if p.is_closed:
                action=ft.ElevatedButton('إعادة فتح',on_click=lambda e,pid=p.id: toggle(pid))
            else:
                action=ft.ElevatedButton('إقفال السنة وترحيل الربح',icon=ft.Icons.LOCK,on_click=lambda e,pid=p.id: annual_close(pid))
            table.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(p.name)),ft.DataCell(ft.Text(p.date_from.strftime('%Y-%m-%d'))),ft.DataCell(ft.Text(p.date_to.strftime('%Y-%m-%d'))),
                ft.DataCell(ft.Text('مقفلة' if p.is_closed else 'مفتوحة')),
                ft.DataCell(ft.Text(str(p.closing_journal_id or '-'))),ft.DataCell(action)
            ]))
        page.update()
    def toggle(pid):
        try:
            p=next(x for x in services.list_fiscal_periods() if x.id==pid)
            services.reopen_fiscal_period(pid) if p.is_closed else services.close_fiscal_period(pid); refresh()
        except Exception as ex: page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True)); page.update()
    def annual_close(pid):
        try:
            je=services.close_fiscal_year(pid)
            page.overlay.append(ft.SnackBar(ft.Text(f'تم إقفال السنة وترحيل النتيجة. رقم القيد: {je or "بدون قيد"}'), open=True)); refresh()
        except Exception as ex: page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True)); page.update()
    def add(e):
        try: services.create_fiscal_period(name.value,parse(start.value),parse(end.value)); name.value=''; refresh()
        except Exception as ex: page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True)); page.update()
    refresh()
    return ft.Column([
        theme.page_title('الفترات والسنوات المالية','إنشاء الفترات، إقفال السنة، ترحيل الأرباح وعكس الإقفال عند إعادة الفتح'),
        theme.card(ft.Row([name,start.control,end.control,ft.ElevatedButton('إضافة فترة',on_click=add)],wrap=True)),
        ft.Container(height=10),theme.h_scroll(table)
    ],expand=True,scroll=ft.ScrollMode.AUTO)
