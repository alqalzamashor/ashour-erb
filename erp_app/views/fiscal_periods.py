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
    # ---- الإقفال الشهري
    today=datetime.date.today()
    prev=(today.replace(day=1)-datetime.timedelta(days=1))
    m_year=ft.TextField(label='السنة',width=100,value=str(prev.year)); m_month=ft.TextField(label='الشهر',width=90,value=str(prev.month))
    m_note=ft.TextField(label='ملاحظة (اختياري)',width=240)
    m_info=ft.Text('',size=12)
    m_table=ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['الشهر','إيرادات','مصروفات','الصافي','أُقفل بواسطة','تاريخ الإقفال','']],rows=[])
    def snack(msg): page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()
    def m_check(e=None):
        try:
            c=services.month_close_checks(int(m_year.value),int(m_month.value))
            lines=[f'✖ {x}' for x in c['blockers']]+[f'• {x}' for x in c['warnings']]
            m_info.value='\n'.join(lines) if lines else '✔ الشهر جاهز للإقفال'
            m_info.color=theme.DANGER if c['blockers'] else theme.SUCCESS
        except Exception as ex: m_info.value=str(ex); m_info.color=theme.DANGER
        page.update()
    def m_close(e):
        try:
            services.close_month(int(m_year.value),int(m_month.value),m_note.value or ''); m_note.value=''; snack('تم إقفال الشهر'); m_refresh(); m_check()
        except Exception as ex: snack(str(ex))
    def m_reopen(y,mo):
        try: services.reopen_month(y,mo); m_refresh(); m_check()
        except Exception as ex: snack(str(ex))
    def m_refresh():
        m_table.rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(f'{c.month}/{c.year}')),ft.DataCell(ft.Text(f'{c.income:,.2f}')),ft.DataCell(ft.Text(f'{c.expense:,.2f}')),
            ft.DataCell(ft.Text(f'{c.income-c.expense:,.2f}')),ft.DataCell(ft.Text(c.closed_by or '-')),ft.DataCell(ft.Text(c.closed_at.strftime('%Y-%m-%d %H:%M') if c.closed_at else '-')),
            ft.DataCell(ft.TextButton('إعادة فتح',on_click=lambda e,y=c.year,mo=c.month: m_reopen(y,mo)))]) for c in services.list_month_closes()]
        page.update()
    refresh(); m_refresh(); m_check()
    return ft.Column([
        theme.page_title('الفترات والسنوات المالية','إنشاء الفترات، إقفال السنة، ترحيل الأرباح وعكس الإقفال عند إعادة الفتح'),
        theme.card(ft.Column([ft.Text('الإقفال الشهري (قفل التسجيل في الشهر بعد مراجعته)',weight=ft.FontWeight.BOLD),
            ft.Row([m_year,m_month,m_note,ft.OutlinedButton('فحص',on_click=m_check),ft.FilledButton('إقفال الشهر',icon=ft.Icons.LOCK,bgcolor=theme.PRIMARY,on_click=m_close)],wrap=True),
            m_info,theme.h_scroll(m_table)])),
        ft.Container(height=10),
        theme.card(ft.Row([name,start.control,end.control,ft.ElevatedButton('إضافة فترة',on_click=add)],wrap=True)),
        ft.Container(height=10),theme.h_scroll(table)
    ],expand=True,scroll=ft.ScrollMode.AUTO)
