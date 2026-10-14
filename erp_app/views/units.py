import flet as ft
from .. import services, theme


def build_units(page: ft.Page):
    search=ft.TextField(label="بحث عن وحدة", width=300, prefix_icon=ft.Icons.SEARCH)
    name=ft.TextField(label="اسم وحدة القياس", width=340)
    editing={"id":None}
    err=ft.Text("", color=theme.DANGER, visible=False)
    def _unit_row(u):
        return ft.DataRow(cells=[ft.DataCell(ft.Text(str(u.id))), ft.DataCell(ft.Text(u.name)), ft.DataCell(ft.Row([
            ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, on_click=lambda e, uid=u.id, n=u.name: open_edit(uid, n)),
            ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, on_click=lambda e, uid=u.id: do_delete(uid)),]))])

    table_sortable = theme.SortableDataTable(
        columns=[("رقم", lambda u: u.id, True), ("الوحدة", lambda u: u.name), ("الإجراءات", None)],
        row_builder=_unit_row, page=page, expand=True,
    )
    table = table_sortable.control

    def refresh(e=None):
        table_sortable.set_data(services.list_units(search.value or None))

    def close(e=None): dialog.open=False; page.update()
    def open_add(e=None): editing['id']=None; name.value=''; err.visible=False; dialog.title=ft.Text('إضافة وحدة قياس'); dialog.open=True; page.update()
    def open_edit(uid,n): editing['id']=uid; name.value=n; err.visible=False; dialog.title=ft.Text('تعديل وحدة القياس'); dialog.open=True; page.update()
    def save(e):
        try:
            if editing['id'] is None: services.create_unit(name.value)
            else: services.update_unit(editing['id'], name.value)
            dialog.open=False; refresh()
        except Exception as ex: err.value=str(ex); err.visible=True; page.update()
    def do_delete(uid):
        try: services.delete_unit(uid); refresh()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True)); page.update()

    dialog=ft.AlertDialog(modal=True,title=ft.Text('وحدة قياس'),content=ft.Column([name,err],tight=True),actions=[ft.TextButton('إلغاء',on_click=close),ft.FilledButton('حفظ',bgcolor=theme.PRIMARY,on_click=save)])
    page.overlay.append(dialog); search.on_change=refresh; refresh()
    return ft.Column([ft.Row([theme.page_title('وحدات القياس','إضافة وتعديل وحذف وحدات القياس'),ft.Container(expand=True),search,ft.FilledButton('إضافة وحدة',icon=ft.Icons.ADD,bgcolor=theme.PRIMARY,on_click=open_add)]),ft.Container(height=12),theme.card(theme.h_scroll(table, vscroll=True),expand=True)],expand=True)
