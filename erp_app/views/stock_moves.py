import flet as ft
from .. import services, theme


def build_stock_moves(page: ft.Page):
    products = [p for p in services.list_products() if p.product_type != 'service']
    locations = services.list_locations()
    product_options = {str(p.id): p.name for p in products}
    location_options = {str(l.id): l.name for l in locations}
    branches = services.list_branches(True); allowed=services.user_branch_ids(); branches=[b for b in branches if not allowed or b.id in allowed]; centers=services.list_cost_centers(True)

    from .. import report_engine as RE
    from ..report_viewer import ReportViewer, Mode
    moves = {}              # id -> عناصر الصف (للأزرار)

    def cell_status(r):
        return ft.Text(r['status'], color=theme.DANGER if r['status'] == 'ملغاة' else theme.TEXT_MUTED, weight=ft.FontWeight.BOLD)

    def cell_dir(r):
        return ft.Text(r['direction'], color=theme.SUCCESS if r['direction'] == 'دخول' else theme.DANGER, weight=ft.FontWeight.BOLD)

    def cell_actions(r):
        row = ft.Row(spacing=2, tight=True)
        row.controls.append(ft.IconButton(icon=ft.Icons.PRINT_OUTLINED, tooltip='طباعة', on_click=lambda e, mid=r['id']: do_print_move(mid)))
        if r['manual'] and r['status'] != 'ملغاة':
            row.controls.append(ft.IconButton(icon=ft.Icons.CANCEL_OUTLINED, icon_color=theme.DANGER, tooltip='إلغاء', on_click=lambda e, mid=r['id']: do_void_move(mid)))
        return row

    viewer = ReportViewer(page, 'stock_moves', 'حركات المخزون', [
        RE.Col('date', 'التاريخ', RE.DATE), RE.Col('product', 'الصنف', width=2.4, bold=True), RE.Col('location', 'المخزن'), RE.Col('direction', 'الاتجاه'),
        RE.Col('quantity', 'الكمية', RE.QTY, 'sum'), RE.Col('reference', 'المرجع'), RE.Col('status', 'الحالة'), RE.Col('actions', '', group=False)],
        modes=[Mode('by_prod', 'حسب الصنف', ['product']), Mode('by_loc', 'حسب المخزن', ['location']), Mode('by_dir', 'حسب الاتجاه', ['direction']),
               Mode('by_month', 'حسب الشهر', ['date:month'])], cell_builders={'status': cell_status, 'direction': cell_dir, 'actions': cell_actions}, kpis=None, chart_value='quantity')

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
            rows.append({'id': m.id, 'date': m.date, 'product': m.product.name, 'location': m.location.name, 'direction': 'دخول' if m.direction == 'in' else 'خروج',
                         'quantity': m.quantity, 'reference': m.reference or '-', 'status': 'ملغاة' if m.voided else 'سارية',
                         'manual': not (m.reference and m.reference.startswith(AUTO_PREFIXES)), 'actions': ''})
        viewer.set_rows(rows)
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
            viewer.control,
        ],
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )
