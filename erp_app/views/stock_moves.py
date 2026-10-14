import flet as ft
from .. import services, theme


def build_stock_moves(page: ft.Page):
    products = [p for p in services.list_products() if p.product_type != 'service']
    locations = services.list_locations()
    product_options = {str(p.id): p.name for p in products}
    location_options = {str(l.id): l.name for l in locations}
    branches = services.list_branches(True); allowed=services.user_branch_ids(); branches=[b for b in branches if not allowed or b.id in allowed]; centers=services.list_cost_centers(True)

    moves_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("التاريخ")),
            ft.DataColumn(ft.Text("الصنف")),
            ft.DataColumn(ft.Text("المخزن")),
            ft.DataColumn(ft.Text("الاتجاه")),
            ft.DataColumn(ft.Text("الكمية")),
            ft.DataColumn(ft.Text("المرجع")),
            ft.DataColumn(ft.Text("الحالة")),
            ft.DataColumn(ft.Text("")),
        ],
        rows=[],
        expand=True,
    )

    product_dd = theme.SearchableDropdown(
        label="الصنف",
        options=list(product_options.items()),
        width=260,
    )
    location_dd = ft.Dropdown(
        label="المخزن",
        options=[ft.dropdown.Option(key=k, text=v) for k, v in location_options.items()],
        value=str(services.default_location_id()) if services.default_location_id() else None,
        width=200,
    )
    branch_dd=ft.Dropdown(label="الفرع",width=220,options=[ft.dropdown.Option(str(b.id),f"{b.code} - {b.name}") for b in branches],value=str(services.default_branch_id()) if services.default_branch_id() else None)
    center_dd=ft.Dropdown(label="مركز التكلفة",width=220,options=[ft.dropdown.Option(str(c.id),f"{c.code} - {c.name}") for c in centers],value=str(services.default_cost_center_id()) if services.default_cost_center_id() else None)
    direction_dd = ft.Dropdown(
        label="الاتجاه",
        options=[ft.dropdown.Option(key="in", text="دخول (In)"), ft.dropdown.Option(key="out", text="خروج (Out)")],
        value="in",
        width=160,
    )
    unit_dd = ft.Dropdown(label="وحدة الحركة", options=[], width=180)
    qty_field = ft.TextField(label="الكمية", value="", width=120, keyboard_type=ft.KeyboardType.NUMBER)
    ref_field = ft.TextField(label="المرجع", width=180)
    form_error = ft.Text("", color=theme.DANGER, visible=False)

    def refresh_product_units(e=None):
        unit_dd.options=[]; unit_dd.value=None
        if product_dd.value:
            lines=services.list_product_units(int(product_dd.value))
            unit_dd.options=[ft.dropdown.Option(str(x.unit_id),x.unit.name) for x in lines]
            d=next((x for x in lines if x.is_default),lines[0] if lines else None)
            if d: unit_dd.value=str(d.unit_id)
        page.update()
    product_dd.on_change=refresh_product_units

    AUTO_PREFIXES = ("SALES:", "PURCHASE:", "MO:", "DMG:", "ADJ:", "TRF:", "VOID:", "GRN:")

    def do_print_move(move_id):
        try:
            path = services.generate_stock_move_pdf_file(move_id)
            theme.open_or_download_file(page, path)
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذرت الطباعة: {ex}'), open=True)); page.update()

    def do_void_move(move_id):
        def confirm(e):
            try:
                services.void_stock_move(move_id)
                void_dialog.open = False
                page.update()
                refresh_table()
            except Exception as ex:
                void_err.value = str(ex); void_err.visible = True; page.update()

        void_err = ft.Text('', color=theme.DANGER, visible=False)
        void_dialog = ft.AlertDialog(
            modal=True, title=ft.Text('تأكيد الإلغاء'),
            content=ft.Column([ft.Text('هل تريد إلغاء هذه الحركة؟'), void_err], tight=True),
            actions=[
                ft.TextButton('تراجع', on_click=lambda e: (setattr(void_dialog, 'open', False), page.update())),
                ft.FilledButton('تأكيد الإلغاء', bgcolor=theme.DANGER, on_click=confirm),
            ],
        )
        page.overlay.append(void_dialog)
        void_dialog.open = True
        page.update()

    def refresh_table():
        rows = []
        for m in services.list_stock_moves():
            direction_label = "دخول" if m.direction == "in" else "خروج"
            direction_color = theme.SUCCESS if m.direction == "in" else theme.DANGER
            status_label = 'ملغاة' if m.voided else 'سارية'
            status_color = theme.DANGER if m.voided else theme.TEXT_MUTED
            is_manual = not (m.reference and m.reference.startswith(AUTO_PREFIXES))
            actions = ft.Row(spacing=2)
            actions.controls.append(ft.IconButton(icon=ft.Icons.PRINT_OUTLINED, tooltip='طباعة', on_click=lambda e, mid=m.id: do_print_move(mid)))
            if is_manual and not m.voided:
                actions.controls.append(ft.IconButton(icon=ft.Icons.CANCEL_OUTLINED, icon_color=theme.DANGER, tooltip='إلغاء',
                                                        on_click=lambda e, mid=m.id: do_void_move(mid)))
            rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(m.date.strftime("%Y-%m-%d %H:%M"))),
                    ft.DataCell(ft.Text(m.product.name)),
                    ft.DataCell(ft.Text(m.location.name)),
                    ft.DataCell(ft.Text(direction_label, color=direction_color, weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(f"{m.quantity:g}")),
                    ft.DataCell(ft.Text(m.reference or "-")),
                    ft.DataCell(ft.Text(status_label, color=status_color, weight=ft.FontWeight.BOLD)),
                    ft.DataCell(actions),
                ])
            )
        moves_table.rows = rows
        page.update()

    def add_move(e):
        try:
            if not product_dd.value or not location_dd.value:
                raise ValueError("اختر الصنف والمخزن")
            qty = float(qty_field.value or 0)
            if qty <= 0:
                raise ValueError("الكمية لازم تكون أكبر من صفر")

            services.create_stock_move(
                product_id=int(product_dd.value),
                location_id=int(location_dd.value),
                direction=direction_dd.value,
                quantity=qty,
                unit_id=int(unit_dd.value) if unit_dd.value else None,
                reference=ref_field.value or "",
                branch_id=int(branch_dd.value) if branch_dd.value else None,
                cost_center_id=int(center_dd.value) if center_dd.value else None,
            )
            qty_field.value = ""
            ref_field.value = ""
            form_error.visible = False
            refresh_table()
        except Exception as ex:
            form_error.value = str(ex)
            form_error.visible = True
            page.update()

    form = theme.card(
        ft.Column(
            [
                ft.Text("تسجيل حركة مخزون", size=16, weight=ft.FontWeight.BOLD),
                ft.Row([product_dd.control, unit_dd, location_dd, branch_dd, center_dd, direction_dd], wrap=True, spacing=12),
                ft.Row([qty_field, ref_field,
                        ft.FilledButton("تسجيل الحركة", icon=ft.Icons.SAVE_OUTLINED,
                                        bgcolor=theme.PRIMARY, on_click=add_move)],
                       spacing=12),
                form_error,
            ],
            spacing=12,
        )
    )

    refresh_product_units()
    refresh_table()

    return ft.Column(
        [
            theme.page_title("حركات المخزون", "تسجيل الدخول والخروج للأصناف"),
            ft.Container(height=12),
            form,
            ft.Container(height=16),
            theme.card(theme.h_scroll(moves_table), expand=True),
        ],
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )
