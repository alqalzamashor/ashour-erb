import datetime
import flet as ft
from .. import services, theme


def build_employees(page: ft.Page):
    search = ft.TextField(label='بحث بالاسم أو الكود', width=300, prefix_icon=ft.Icons.SEARCH, border_radius=10)
    branches = services.list_branches(True)

    name_field = ft.TextField(label='اسم الموظف', width=250)
    national_id_field = ft.TextField(label='رقم الهوية', width=180)
    phone_field = ft.TextField(label='رقم الجوال', width=180)
    email_field = ft.TextField(label='البريد الإلكتروني', width=220)
    position_field = ft.TextField(label='المسمى الوظيفي', width=200)
    cost_centers = services.list_cost_centers(True)
    department_dd = ft.Dropdown(
        label='القسم (مركز التكلفة)', width=220,
        options=[ft.dropdown.Option('', 'بدون')] + [ft.dropdown.Option(str(c.id), f'{c.code} - {c.name}') for c in cost_centers],
        value='',
    )
    hire_date_field = theme.DateField('تاريخ التعيين', page, width=160, value=datetime.date.today().strftime('%Y-%m-%d'))
    bank_field = ft.TextField(label='رقم الحساب البنكي (IBAN)', width=260)
    branch_dd = ft.Dropdown(
        label='الفرع', width=200,
        options=[ft.dropdown.Option(str(b.id), f'{b.code} - {b.name}') for b in branches],
        value=str(services.default_branch_id() or ''),
    )
    error_text = ft.Text('', color=theme.DANGER, visible=False)
    editing_id = {'value': None}

    def _employee_row(emp):
        contract = services.get_active_contract(emp.id)
        contract_text = f'{contract.gross_salary:,.2f} ر.س' if contract else 'بدون عقد ساري'
        contract_color = theme.SUCCESS if contract else theme.DANGER
        return ft.DataRow(cells=[
            ft.DataCell(ft.Text(emp.code)),
            ft.DataCell(ft.Text(emp.name)),
            ft.DataCell(ft.Text(emp.position or '-')),
            ft.DataCell(ft.Text(emp.cost_center.name if emp.cost_center else (emp.department or '-'))),
            ft.DataCell(ft.Text(emp.phone or '-')),
            ft.DataCell(ft.Text(emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else '-')),
            ft.DataCell(ft.Text(contract_text, color=contract_color)),
            ft.DataCell(
                ft.Row([
                    ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل',
                                  on_click=lambda e, x=emp: open_edit(x)),
                    ft.IconButton(icon=ft.Icons.PERSON_OFF_OUTLINED, icon_color=theme.DANGER,
                                  tooltip='إيقاف الموظف',
                                  on_click=lambda e, eid=emp.id: deactivate(eid)),
                ])
            ),
        ])

    table_sortable = theme.SortableDataTable(
        columns=[
            ('الكود', lambda emp: emp.code), ('الاسم', lambda emp: emp.name), ('المسمى الوظيفي', lambda emp: emp.position),
            ('القسم', lambda emp: emp.cost_center.name if emp.cost_center else emp.department),
            ('الجوال', lambda emp: emp.phone), ('تاريخ التعيين', lambda emp: emp.hire_date),
            ('العقد الحالي', None), ('الإجراءات', None),
        ],
        row_builder=_employee_row, page=page, expand=True,
    )
    table = table_sortable.control

    def close_dialog(e=None):
        dialog.open = False
        page.update()

    def clear_form():
        editing_id['value'] = None
        name_field.value = ''
        national_id_field.value = ''
        phone_field.value = ''
        email_field.value = ''
        position_field.value = ''
        department_dd.value = ''
        hire_date_field.value = datetime.date.today().strftime('%Y-%m-%d')
        bank_field.value = ''
        error_text.visible = False

    def refresh(e=None):
        table_sortable.set_data(services.list_employees(search=search.value or None))

    def open_add(e=None):
        clear_form()
        dialog.title = ft.Text('إضافة موظف جديد')
        dialog.open = True
        page.update()

    def open_edit(emp):
        editing_id['value'] = emp.id
        name_field.value = emp.name
        national_id_field.value = emp.national_id or ''
        phone_field.value = emp.phone or ''
        email_field.value = emp.email or ''
        position_field.value = emp.position or ''
        department_dd.value = str(emp.cost_center_id) if emp.cost_center_id else ''
        hire_date_field.value = emp.hire_date.strftime('%Y-%m-%d') if emp.hire_date else ''
        bank_field.value = emp.bank_account or ''
        branch_dd.value = str(emp.branch_id) if emp.branch_id else ''
        error_text.visible = False
        dialog.title = ft.Text('تعديل بيانات الموظف')
        dialog.open = True
        page.update()

    def save(e):
        try:
            if not name_field.value:
                raise ValueError('اسم الموظف مطلوب')
            hire_date = None
            if hire_date_field.value:
                hire_date = datetime.datetime.strptime(hire_date_field.value, '%Y-%m-%d')

            if editing_id['value'] is None:
                services.create_employee(
                    name=name_field.value.strip(), national_id=national_id_field.value or '',
                    phone=phone_field.value or '', email=email_field.value or '',
                    position=position_field.value or '',
                    cost_center_id=int(department_dd.value) if department_dd.value else None,
                    hire_date=hire_date, bank_account=bank_field.value or '',
                    branch_id=int(branch_dd.value) if branch_dd.value else None,
                )
            else:
                services.update_employee(
                    editing_id['value'], name=name_field.value.strip(),
                    national_id=national_id_field.value or '', phone=phone_field.value or '',
                    email=email_field.value or '', position=position_field.value or '',
                    department='', cost_center_id=int(department_dd.value) if department_dd.value else None,
                    hire_date=hire_date,
                    bank_account=bank_field.value or '',
                    branch_id=int(branch_dd.value) if branch_dd.value else None,
                )
            dialog.open = False
            refresh()
        except Exception as ex:
            error_text.value = str(ex)
            error_text.visible = True
            page.update()

    def deactivate(emp_id):
        try:
            services.deactivate_employee(emp_id)
            refresh()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True)); page.update()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text('إضافة موظف جديد'),
        content=ft.Container(
            width=560,
            content=ft.Column(
                [
                    ft.Row([name_field, national_id_field], wrap=True),
                    ft.Row([phone_field, email_field], wrap=True),
                    ft.Row([position_field, department_dd], wrap=True),
                    ft.Row([hire_date_field.control, branch_dd], wrap=True),
                    bank_field,
                    error_text,
                ],
                spacing=12, tight=True, scroll=ft.ScrollMode.AUTO,
            ),
        ),
        actions=[
            ft.TextButton('إلغاء', on_click=close_dialog),
            ft.FilledButton('حفظ', bgcolor=theme.PRIMARY, on_click=save),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(dialog)

    search.on_change = refresh
    refresh()

    header = ft.Row(
        [
            theme.page_title('الموظفون', 'إدارة بيانات الموظفين'),
            ft.Container(expand=True),
            search,
            ft.FilledButton('إضافة موظف', icon=ft.Icons.PERSON_ADD_ALT_1, bgcolor=theme.PRIMARY, on_click=open_add),
        ],
    )

    return ft.Column(
        [header, ft.Container(height=12),
         theme.card(theme.h_scroll(table, vscroll=True), expand=True)],
        expand=True,
    )
