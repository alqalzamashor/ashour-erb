import flet as ft
from .. import services, theme, i18n


def build_locations(page: ft.Page):
    search = ft.TextField(label='بحث عن مخزن', width=280, prefix_icon=ft.Icons.SEARCH, border_radius=10)
    branches = services.list_branches(True)
    centers = services.list_cost_centers(True)

    name_field = ft.TextField(label='اسم المخزن', autofocus=True, border_radius=10)
    branch_dd = ft.Dropdown(label='الفرع', options=[ft.dropdown.Option('', 'بدون')] + [ft.dropdown.Option(str(b.id), f'{b.code} - {b.name}') for b in branches])
    center_dd = ft.Dropdown(label='مركز التكلفة', options=[ft.dropdown.Option('', 'بدون')] + [ft.dropdown.Option(str(c.id), f'{c.code} - {c.name}') for c in centers])
    is_default_switch = ft.Switch(label='مخزن افتراضي', value=False)
    error_text = ft.Text('', color=theme.DANGER, visible=False)
    editing_id = {'value': None}

    def _location_row(loc):
        return ft.DataRow(cells=[
            ft.DataCell(ft.Text(loc.name)),
            ft.DataCell(ft.Text(loc.branch.name if loc.branch else '-')),
            ft.DataCell(ft.Text(loc.cost_center.name if loc.cost_center else '-')),
            ft.DataCell(ft.Icon(ft.Icons.CHECK_CIRCLE, color=theme.SUCCESS, size=18) if loc.is_default else ft.Text('-')),
            ft.DataCell(
                ft.Row([
                    ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل',
                                  on_click=lambda e, x=loc: open_edit(x)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف',
                                  on_click=lambda e, lid=loc.id, lname=loc.name: ask_delete(lid, lname)),
                ])
            ),
        ])

    table_sortable = theme.SortableDataTable(
        columns=[('اسم المخزن', lambda loc: loc.name), ('الفرع', lambda loc: loc.branch.name if loc.branch else ''),
                 ('مركز التكلفة', lambda loc: loc.cost_center.name if loc.cost_center else ''),
                 ('افتراضي', lambda loc: loc.is_default), ('الإجراءات', None)],
        row_builder=_location_row, page=page, expand=True,
    )
    table = table_sortable.control

    def close_dialog(e=None):
        dialog.open = False
        page.update()

    def clear_form():
        editing_id['value'] = None
        name_field.value = ''
        branch_dd.value = ''
        center_dd.value = ''
        is_default_switch.value = False
        error_text.visible = False

    def refresh(e=None):
        query = (search.value or '').strip().lower()
        data = [loc for loc in services.list_locations() if i18n.matches(query, loc.name)]
        table_sortable.set_data(data)

    def open_add(e=None):
        clear_form()
        dialog.title = ft.Text('إضافة مخزن')
        dialog.open = True
        page.update()

    def open_edit(loc):
        editing_id['value'] = loc.id
        name_field.value = loc.name
        branch_dd.value = str(loc.branch_id) if loc.branch_id else ''
        center_dd.value = str(loc.cost_center_id) if loc.cost_center_id else ''
        is_default_switch.value = bool(loc.is_default)
        error_text.visible = False
        dialog.title = ft.Text('تعديل مخزن')
        dialog.open = True
        page.update()

    def save(e):
        try:
            data = {
                'branch_id': int(branch_dd.value) if branch_dd.value else None,
                'cost_center_id': int(center_dd.value) if center_dd.value else None,
                'is_default': is_default_switch.value,
            }
            if editing_id['value'] is None:
                services.create_location(name_field.value, **data)
            else:
                services.update_location(editing_id['value'], name=(name_field.value or '').strip(), **data)
            dialog.open = False
            refresh()
        except Exception as ex:
            error_text.value = str(ex)
            error_text.visible = True
            page.update()

    def ask_delete(loc_id, loc_name):
        def do_delete(e):
            try:
                services.delete_location(loc_id)
                confirm.open = False
                refresh()
            except Exception as ex:
                confirm.content = ft.Column(
                    [ft.Text(f'تعذر حذف "{loc_name}"', weight=ft.FontWeight.BOLD), ft.Text(str(ex), color=theme.DANGER)],
                    tight=True,
                )
                confirm.actions = [
                    ft.TextButton('تعطيل بدل الحذف', on_click=lambda e: (services.deactivate_location(loc_id), setattr(confirm, 'open', False), refresh())),
                    ft.TextButton('إغلاق', on_click=lambda e: close_confirm()),
                ]
                page.update()

        def close_confirm(e=None):
            confirm.open = False
            page.update()

        confirm = ft.AlertDialog(
            modal=True, title=ft.Text('تأكيد الحذف'),
            content=ft.Text(f'هل تريد حذف المخزن "{loc_name}"؟'),
            actions=[ft.TextButton('إلغاء', on_click=close_confirm), ft.FilledButton('حذف', bgcolor=theme.DANGER, on_click=do_delete)],
        )
        page.overlay.append(confirm)
        confirm.open = True
        page.update()

    dialog = ft.AlertDialog(
        modal=True, title=ft.Text('إضافة مخزن'),
        content=ft.Container(
            width=380,
            content=ft.Column([name_field, branch_dd, center_dd, is_default_switch, error_text], spacing=12, tight=True),
        ),
        actions=[ft.TextButton('إلغاء', on_click=close_dialog), ft.FilledButton('حفظ', bgcolor=theme.PRIMARY, on_click=save)],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(dialog)

    search.on_change = refresh
    refresh()

    header = ft.Row(
        [
            theme.page_title('المخازن', 'إدارة المخازن وربطها بالفروع ومراكز التكلفة'),
            ft.Container(expand=True),
            search,
            ft.FilledButton('إضافة مخزن', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=open_add),
        ],
    )

    return ft.Column(
        [header, ft.Container(height=12), theme.card(theme.h_scroll(table, vscroll=True), expand=True)],
        expand=True,
    )
