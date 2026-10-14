import flet as ft
from .. import services, theme

COLOR_CHOICES = [
    ('#6C4EE3', 'بنفسجي'), ('#00C2A8', 'أخضر مائي'), ('#F5A524', 'برتقالي'),
    ('#EF4444', 'أحمر'), ('#3B82F6', 'أزرق'), ('#EC4899', 'وردي'),
]


def build_pos_groups(page: ft.Page):
    products = services.list_products()

    name_field = ft.TextField(label='اسم المجموعة (مثال: مجموعة أ، مشروبات)', width=280)
    color_dd = ft.Dropdown(label='اللون', width=160, options=[ft.dropdown.Option(c, label) for c, label in COLOR_CHOICES], value=COLOR_CHOICES[0][0])
    err = ft.Text('', color=theme.DANGER, visible=False)

    groups_col = ft.Column(spacing=10)

    def build_group_card(g):
        """يبني كارت المجموعة مرة واحدة بعناصر ثابتة (chips_row و assign_dd)
        وبيرجّع (card, refresh_fn) - refresh_fn بتحدّث نفس العناصر مكانها
        بدل ما تبني عناصر جديدة، عشان التحديث يبان فورًا على أي نسخة Flet."""
        chips_row = ft.Row(wrap=True, spacing=6)
        assign_dd = ft.Dropdown(label='اختر صنف', width=260)
        add_err = ft.Text('', color=theme.DANGER, visible=False, size=12)

        def refresh_this_group():
            current = services.list_products_in_pos_group(g.id)
            current_ids = {p.id for p in current}
            chips_row.controls = [
                ft.Container(
                    content=ft.Row(
                        [ft.Text(p.name, size=12, color='#FFFFFF'),
                         ft.IconButton(icon=ft.Icons.CLOSE, icon_size=14, icon_color='#FFFFFF',
                                       on_click=lambda e, pid=p.id: do_remove(pid))],
                        spacing=2, tight=True,
                    ),
                    bgcolor=g.color or theme.PRIMARY, border_radius=16,
                    padding=ft.Padding(left=10, right=4, top=2, bottom=2),
                )
                for p in current
            ] if current else [ft.Text('مفيش أصناف في المجموعة دي لسه', color=theme.TEXT_MUTED, size=12)]

            assign_dd.options = [ft.dropdown.Option(str(p.id), f'{p.sku} - {p.name}') for p in products if p.id not in current_ids]
            assign_dd.value = None
            page.update()

        def do_add(e):
            add_err.visible = False
            if not assign_dd.value:
                add_err.value = 'اختر صنف من القائمة أولاً'
                add_err.visible = True
                page.update()
                return
            try:
                current_ids = [p.id for p in services.list_products_in_pos_group(g.id)]
                current_ids.append(int(assign_dd.value))
                services.set_pos_group_products(g.id, current_ids)
                refresh_this_group()
            except Exception as ex:
                add_err.value = str(ex)
                add_err.visible = True
                page.update()

        def do_remove(pid):
            try:
                current_ids = [p.id for p in services.list_products_in_pos_group(g.id) if p.id != pid]
                services.set_pos_group_products(g.id, current_ids)
                refresh_this_group()
            except Exception as ex:
                add_err.value = str(ex)
                add_err.visible = True
                page.update()

        def do_delete(e):
            try:
                services.delete_pos_group(g.id)
                refresh_all_groups()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        card = theme.card(
            ft.Column(
                [
                    ft.Row([
                        ft.Container(width=14, height=14, bgcolor=g.color or theme.PRIMARY, border_radius=7),
                        ft.Text(g.name, size=15, weight=ft.FontWeight.BOLD),
                        ft.Container(expand=True),
                        ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف المجموعة', on_click=do_delete),
                    ]),
                    chips_row,
                    ft.Row([assign_dd, ft.FilledButton('إضافة للمجموعة', icon=ft.Icons.ADD, on_click=do_add)], wrap=True, spacing=10),
                    add_err,
                ],
                spacing=10,
            )
        )
        refresh_this_group()
        return card

    def refresh_all_groups():
        groups_col.controls = [build_group_card(g) for g in services.list_pos_groups()]
        page.update()

    def add_group(e):
        try:
            services.create_pos_group(name_field.value, color=color_dd.value)
            name_field.value = ''
            err.visible = False
            refresh_all_groups()
        except Exception as ex:
            err.value = str(ex)
            err.visible = True
            page.update()

    refresh_all_groups()

    form = theme.card(
        ft.Column(
            [
                ft.Text('مجموعة جديدة', size=16, weight=ft.FontWeight.BOLD),
                ft.Text('نظّم شاشة نقاط البيع بمجموعات زرار سريعة حسب ما يناسبك (مشروبات، وجبات، مجموعة أ...) وحدد أصناف كل مجموعة.', color=theme.TEXT_MUTED),
                ft.Row([name_field, color_dd, ft.FilledButton('إضافة مجموعة', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=add_group)], wrap=True, spacing=10),
                err,
            ],
            spacing=10,
        )
    )

    return ft.Column(
        [
            theme.page_title('مجموعات نقاط البيع', 'نظّم شاشة الكاشير بمجموعات أصناف سريعة تختارها بنفسك'),
            ft.Container(height=12),
            form,
            ft.Container(height=16),
            groups_col,
        ],
        expand=True, scroll=ft.ScrollMode.AUTO,
    )
