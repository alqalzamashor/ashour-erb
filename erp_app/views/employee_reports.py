import datetime
import os
import flet as ft
from .. import services, theme


def export_report_xlsx(rep, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook(); ws = wb.active; ws.title = 'تقرير'[:31]; ws.sheet_view.rightToLeft = True
    ws.append([rep['title']]); ws['A1'].font = Font(bold=True, size=13)
    ws.append(rep['columns'])
    for c in ws[2]:
        c.font = Font(bold=True, color='FFFFFF'); c.fill = PatternFill('solid', fgColor='1F6F5C'); c.alignment = Alignment(horizontal='center', wrap_text=True)
    for r in rep['rows']:
        ws.append(list(r))
    if rep.get('totals'):
        ws.append(list(rep['totals']))
        for c in ws[ws.max_row]:
            c.font = Font(bold=True)
    if rep.get('notes'):
        ws.append([]); ws.append([rep['notes']])
    for i in range(1, len(rep['columns']) + 1):
        ws.column_dimensions[ws.cell(row=2, column=i).column_letter].width = 18
    wb.save(path); return path


def export_report_pdf(rep, path, filters=None, rtl=True):
    """نفس تقرير الشاشة كـ PDF عربي (أعمدة وصفوف + سطر الإجمالي)."""
    from .. import print_screen
    rows = [[_fmt(v) for v in r] for r in rep['rows']]
    if rep.get('totals'):
        rows.append([_fmt(v) for v in rep['totals']])
    data = {'filters': filters or [], 'stats': [], 'tables': [{'columns': list(rep['columns']), 'rows': rows, 'caption': rep.get('notes') or ''}]}
    return print_screen.build_pdf(data, rep['title'], path, rtl=rtl)


def _fmt(v):
    if isinstance(v, float):
        return f'{v:,.2f}'
    return str(v)


def build_employee_reports(page: ft.Page):
    """تقارير الموظفين: اختار التقرير والفلاتر وبيتعرض في جدول قابل للفرز والتصدير Excel."""
    today = datetime.date.today()
    kinds = services.EMPLOYEE_REPORTS
    kind_dd = ft.Dropdown(label='التقرير', width=300, value=kinds[0][0], options=[ft.dropdown.Option(k, v) for k, v in kinds])
    emp_dd = theme.SearchableDropdown(label='الموظف', width=240, options=[('0', 'كل الموظفين')] + [(str(e.id), f'{e.code} - {e.name}') for e in services.list_employees(active_only=False)])
    branch_dd = ft.Dropdown(label='الفرع', width=180, value='0', options=[ft.dropdown.Option('0', 'كل الفروع')] + [ft.dropdown.Option(str(b.id), b.name) for b in services.list_branches()])
    cc_dd = ft.Dropdown(label='القسم', width=180, value='0', options=[ft.dropdown.Option('0', 'كل الأقسام')] + [ft.dropdown.Option(str(c.id), c.name) for c in services.list_cost_centers()])
    from_f = theme.DateField('من تاريخ', page, width=150, value=today.replace(day=1).strftime('%Y-%m-%d'))
    to_f = theme.DateField('إلى تاريخ', page, width=150, value=today.strftime('%Y-%m-%d'))
    year_f = ft.TextField(label='السنة', width=100, value=str(today.year), keyboard_type=ft.KeyboardType.NUMBER)
    days_f = ft.TextField(label='خلال (يوم)', width=110, value='60', keyboard_type=ft.KeyboardType.NUMBER)
    inactive_cb = ft.Checkbox(label='يشمل غير النشطين', value=False)
    filters = ft.Row(wrap=True, spacing=10)
    notes = ft.Text('', size=12, color=theme.TEXT_MUTED)
    table_host = ft.Container()
    msg = ft.Text('', color=theme.DANGER, visible=False)
    state = {'rep': None}
    USES = {  # الفلاتر المستخدمة في كل تقرير
        'roster': (branch_dd, cc_dd, inactive_cb), 'headcount': (branch_dd, cc_dd, inactive_cb),
        'contracts_expiring': (branch_dd, cc_dd, days_f), 'statement': (emp_dd.control, year_f),
        'leaves': (from_f.control, to_f.control, branch_dd, cc_dd, inactive_cb),
        'attendance': (from_f.control, to_f.control, branch_dd, cc_dd, inactive_cb),
        'movements': (from_f.control, to_f.control, emp_dd.control),
    }

    def snack(m):
        page.overlay.append(ft.SnackBar(ft.Text(m), open=True)); page.update()

    def val(dd):
        return None if dd.value in (None, '', '0') else dd.value

    def parse(f):
        return datetime.datetime.strptime(f.value, '%Y-%m-%d')

    def refresh(e=None):
        filters.controls = [kind_dd] + list(USES[kind_dd.value])
        try:
            rep = services.employee_report(
                kind_dd.value, employee_id=val(emp_dd), date_from=parse(from_f), date_to=parse(to_f),
                year=year_f.value or today.year, days=days_f.value or 60, branch_id=val(branch_dd),
                cost_center_id=val(cc_dd), active_only=not inactive_cb.value)
        except Exception as ex:
            msg.value = str(ex); msg.visible = True; state['rep'] = None; table_host.content = None; notes.value = ''
            page.update(); return
        msg.visible = False; state['rep'] = rep
        cols = [ft.DataColumn(ft.Text(c)) for c in rep['columns']]
        rows = [ft.DataRow(cells=[ft.DataCell(ft.Text(_fmt(v))) for v in r]) for r in rep['rows']]
        if rep.get('totals'):
            rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(_fmt(v), weight=ft.FontWeight.BOLD, color=theme.PRIMARY)) for v in rep['totals']]))
        table_host.content = theme.h_scroll(ft.DataTable(columns=cols, rows=rows), vscroll=True)
        notes.value = (rep.get('notes') or '') + (f"  •  عدد الصفوف: {len(rep['rows'])}" if rep['rows'] else '  •  لا توجد بيانات')
        page.update()

    def export(e=None):
        if not state['rep']:
            snack('مفيش تقرير لتصديره'); return
        try:
            out_dir = os.path.join(services.APP_DIR, 'exports'); os.makedirs(out_dir, exist_ok=True)
            path = export_report_xlsx(state['rep'], os.path.join(out_dir, f"employee_report_{kind_dd.value}_{datetime.date.today():%Y%m%d}.xlsx"))
            theme.open_or_download_file(page, path); snack('تم إنشاء الملف')
        except Exception as ex:
            snack(f'تعذر التصدير: {ex}')

    def export_pdf(e=None):
        if not state['rep']:
            snack('مفيش تقرير لتصديره'); return
        try:
            out_dir = os.path.join(services.APP_DIR, 'exports'); os.makedirs(out_dir, exist_ok=True)
            from .. import print_screen
            flt = [(k, v) for k, v in print_screen.extract(filters)['filters'] if k != kind_dd.label]       # الفلاتر الظاهرة حاليًا (من غير نوع التقرير - هو العنوان)
            path = export_report_pdf(state['rep'], os.path.join(out_dir, f"employee_report_{kind_dd.value}_{datetime.date.today():%Y%m%d}.pdf"), filters=flt)
            theme.open_or_download_file(page, path); snack('تم إنشاء الملف')
        except Exception as ex:
            snack(f'تعذر التصدير: {ex}')

    for f in (kind_dd, branch_dd, cc_dd):
        f.on_select = refresh          # ft.Dropdown بيستخدم on_select (on_change مبتتنفذش)
    for f in (emp_dd, from_f, to_f, year_f, days_f, inactive_cb):
        f.on_change = refresh
    refresh()
    return ft.Column([
        ft.Row([theme.page_title('تقارير الموظفين', 'بيانات الموظفين، التوزيع، العقود، كشف الموظف، الإجازات، الحضور، التعيينات والإنهاءات'),
                ft.Container(expand=True), ft.OutlinedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=export_pdf), ft.OutlinedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=export)], spacing=8),
        ft.Container(height=4), filters, msg, notes, theme.card(table_host, expand=True),
    ], expand=True)
