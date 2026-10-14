import flet as ft
from .. import services, theme


def build_product_categories(page: ft.Page):
    search = ft.TextField(
        label="بحث عن الفئة",
        width=320,
        prefix_icon=ft.Icons.SEARCH,
        border_radius=10,
    )

    name_field = ft.TextField(
        label="اسم الفئة",
        autofocus=True,
        border_radius=10,
    )
    error_text = ft.Text("", color=theme.DANGER, visible=False)

    editing_id = {"value": None}

    counts_cache = {}

    def _category_row(c):
        count = counts_cache.get(c.id, 0)
        return ft.DataRow(cells=[
            ft.DataCell(ft.Text(str(c.id))),
            ft.DataCell(ft.Text(c.name)),
            ft.DataCell(ft.Text(str(count))),
            ft.DataCell(
                ft.Row([
                    ft.IconButton(
                        icon=ft.Icons.EDIT_OUTLINED,
                        tooltip="تعديل",
                        on_click=lambda e, cid=c.id, cname=c.name:
                            open_edit(cid, cname),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color=theme.DANGER,
                        tooltip="حذف",
                        on_click=lambda e, cid=c.id, cname=c.name:
                            ask_delete(cid, cname),
                    ),
                ])
            ),
        ])

    table_sortable = theme.SortableDataTable(
        columns=[("رقم", lambda c: c.id, True), ("اسم الفئة", lambda c: c.name),
                 ("عدد الأصناف", lambda c: counts_cache.get(c.id, 0), True), ("الإجراءات", None)],
        row_builder=_category_row, page=page, expand=True,
    )
    table = table_sortable.control

    def close_dialog(e=None):
        dialog.open = False
        page.update()

    def clear_form():
        editing_id["value"] = None
        name_field.value = ""
        error_text.value = ""
        error_text.visible = False

    def refresh(e=None):
        query = (search.value or "").strip().lower()
        try:
            products = services.list_products()
        except Exception:
            products = []
        counts_cache.clear()
        for p in products:
            if p.category_id:
                counts_cache[p.category_id] = counts_cache.get(p.category_id, 0) + 1
        data = [c for c in services.list_categories() if not query or query in c.name.lower()]
        table_sortable.set_data(data)

    def open_add(e=None):
        clear_form()
        dialog.title = ft.Text("إضافة فئة منتج")
        dialog.open = True
        page.update()

    def open_edit(category_id, category_name):
        editing_id["value"] = category_id
        name_field.value = category_name
        error_text.value = ""
        error_text.visible = False
        dialog.title = ft.Text("تعديل فئة المنتج")
        dialog.open = True
        page.update()

    def save(e):
        try:
            name = (name_field.value or "").strip()
            if not name:
                raise ValueError("اسم الفئة مطلوب")

            if editing_id["value"] is None:
                services.create_category(name)
            else:
                services.update_category(editing_id["value"], name)

            dialog.open = False
            refresh()
        except Exception as ex:
            error_text.value = str(ex)
            error_text.visible = True
            page.update()

    def ask_delete(category_id, category_name):
        def do_delete(e):
            try:
                services.delete_category(category_id)
                confirm.open = False
                refresh()
            except Exception as ex:
                confirm.content = ft.Column(
                    [
                        ft.Text(f"تعذر حذف «{category_name}»", weight=ft.FontWeight.BOLD),
                        ft.Text(str(ex), color=theme.DANGER),
                    ],
                    tight=True,
                )
                confirm.actions = [
                    ft.TextButton("إغلاق", on_click=lambda e: close_confirm())
                ]
                page.update()

        def close_confirm(e=None):
            confirm.open = False
            page.update()

        confirm = ft.AlertDialog(
            modal=True,
            title=ft.Text("تأكيد الحذف"),
            content=ft.Text(f"هل تريد حذف الفئة «{category_name}»؟"),
            actions=[
                ft.TextButton("إلغاء", on_click=close_confirm),
                ft.FilledButton(
                    "حذف",
                    bgcolor=theme.DANGER,
                    on_click=do_delete,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.overlay.append(confirm)
        confirm.open = True
        page.update()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("إضافة فئة منتج"),
        content=ft.Container(
            width=420,
            content=ft.Column(
                [
                    name_field,
                    error_text,
                ],
                spacing=12,
                tight=True,
            ),
        ),
        actions=[
            ft.TextButton("إلغاء", on_click=close_dialog),
            ft.FilledButton(
                "حفظ",
                bgcolor=theme.PRIMARY,
                on_click=save,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(dialog)

    search.on_change = refresh

    header = ft.Row(
        [
            theme.page_title("فئات المنتجات", "إضافة وتعديل وحذف والبحث في فئات الأصناف"),
            ft.Container(expand=True),
            search,
            ft.FilledButton(
                "إضافة فئة",
                icon=ft.Icons.ADD,
                bgcolor=theme.PRIMARY,
                on_click=open_add,
            ),
        ],
        alignment=ft.MainAxisAlignment.START,
    )

    refresh()

    return ft.Column(
        [
            header,
            ft.Container(height=12),
            theme.card(
                theme.h_scroll(table, vscroll=True),
                expand=True,
            ),
        ],
        expand=True,
    )
