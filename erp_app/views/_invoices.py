"""محرك مشترك لفاتورتَي المبيعات والمشتريات."""
import datetime
import base64
import flet as ft
from ._approval import prompt as approval_prompt

from .. import services, theme, drafts
from ..zatca import zatca_qr_png_base64


def build_invoice_view(page: ft.Page, kind: str):
    """kind: 'sales' or 'purchase'."""
    is_sales = kind == "sales"

    labels = {
        "title": "فواتير المبيعات" if is_sales else "فواتير المشتريات",
        "subtitle": "إصدار وعرض فواتير البيع" if is_sales else "إصدار وعرض فواتير الشراء",
        "add_btn": "فاتورة مبيعات جديدة" if is_sales else "فاتورة مشتريات جديدة",
        "party_label": "العميل" if is_sales else "المورد",
        "party_col": "العميل" if is_sales else "المورد",
        "preview_title": "فاتورة مبيعات" if is_sales else "فاتورة مشتريات",
    }

    list_parties = services.list_customers if is_sales else services.list_suppliers
    create_invoice = services.create_sales_invoice if is_sales else services.create_purchase_invoice
    list_invoices = services.list_sales_invoices if is_sales else services.list_purchase_invoices
    get_invoice = services.get_sales_invoice if is_sales else services.get_purchase_invoice

    # ---------- List Table ----------
    def _invoice_party(inv):
        return (inv.customer.name if is_sales and inv.customer else (inv.supplier.name if not is_sales and inv.supplier else "-"))

    def _invoice_b2b_label(inv):
        if not is_sales or not inv.customer:
            return "-"
        return "B2B - شركة" if getattr(inv.customer, "party_type", None) == "company" else "B2C - فرد"

    selected_ids = set()      # الفواتير المحددة للطباعة الجماعية
    visible_ids = []          # الفواتير الظاهرة حاليًا (بعد الفلاتر)
    row_by_id = {}

    def apply_selection():
        """الجدول ليه نسختين من الصفوف (الأصلي + نسخة العنوان الثابت): لازم نحدّث علامة الصح في الاتنين مش في آخر صف اتبنى بس."""
        for tbl in (table_sortable.control, table_sortable.clone):
            for r in tbl.rows:
                iid = getattr(r, '_inv_id', None)
                if iid is not None:
                    r.selected = iid in selected_ids

    def toggle_invoice(invoice_id):
        if invoice_id in selected_ids:
            selected_ids.discard(invoice_id)
        else:
            selected_ids.add(invoice_id)
        apply_selection()
        update_selection_ui()
        page.update()

    def select_all(e):
        checked = str(getattr(e, 'data', '')).lower() == 'true'
        for iid in visible_ids:
            (selected_ids.add if checked else selected_ids.discard)(iid)
        apply_selection()
        update_selection_ui()
        page.update()

    def print_one(invoice_id):
        try:
            path = services.generate_invoice_pdf_file(invoice_id, kind='sales' if is_sales else 'purchase')
            theme.open_or_download_file(page, path)
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذرت الطباعة: {ex}'), open=True)); page.update()

    def _invoice_row(inv):
        cells = [
            ft.DataCell(ft.Row([ft.Text(inv.number, weight=ft.FontWeight.BOLD, color=theme.DANGER if getattr(inv, 'voided', False) else None)]
                               + ([theme.status_badge('ملغاة', theme.DANGER, size=10.5)] if getattr(inv, 'voided', False) else []), spacing=6, tight=True)),
            ft.DataCell(ft.Text(inv.date.strftime("%Y-%m-%d %H:%M"))),
            ft.DataCell(ft.Text(_invoice_party(inv))),
        ]
        if is_sales:
            cells.append(ft.DataCell(ft.Text(_invoice_b2b_label(inv), size=12,
                                             color=theme.PRIMARY if (inv.customer and getattr(inv.customer, "party_type", None) == "company") else theme.TEXT_MUTED)))
        cells += [
            ft.DataCell(ft.Text(f"{inv.total:,.2f}", weight=ft.FontWeight.BOLD, color=theme.PRIMARY)),
            ft.DataCell(ft.Text(f"{inv.tax_total:,.2f}")),
            ft.DataCell(ft.Row([
                ft.IconButton(icon=ft.Icons.VISIBILITY_OUTLINED, tooltip="عرض / إرسال", on_click=lambda e, iid=inv.id: open_preview(iid)),
                ft.IconButton(icon=ft.Icons.PRINT_OUTLINED, tooltip="طباعة الفاتورة (PDF)", icon_color=theme.PRIMARY, on_click=lambda e, iid=inv.id: print_one(iid)),
            ], spacing=0)),
        ]
        row = ft.DataRow(selected=inv.id in selected_ids, on_select_change=lambda e, iid=inv.id: toggle_invoice(iid), cells=cells)
        row._inv_id = inv.id
        row_by_id[inv.id] = row
        return row

    table_sortable = theme.SortableDataTable(
        columns=([
            ("رقم الفاتورة", lambda inv: inv.number), ("التاريخ", lambda inv: inv.date), (labels["party_col"], _invoice_party),
        ] + ([("النوع", _invoice_b2b_label)] if is_sales else []) + [
            ("الإجمالي", lambda inv: inv.total, True), ("الضريبة", lambda inv: inv.tax_total, True), ("", None),
        ]),
        row_builder=_invoice_row, page=page, expand=True,
        show_checkbox_column=True, on_select_all=lambda e: select_all(e),
    )
    table = table_sortable.control

    # ---------- فلاتر + طباعة جماعية ----------
    range_f = theme.DateRangeField('الفترة', page, width=290)
    from_f, to_f = range_f.start, range_f.end
    search_f = ft.TextField(label=f'بحث برقم الفاتورة أو اسم {labels["party_col"]}', width=300, prefix_icon=ft.Icons.SEARCH)
    selection_label = ft.Text('', size=12, color=theme.TEXT_MUTED)
    print_selected_btn = ft.FilledButton('طباعة المحدد', icon=ft.Icons.PRINT_OUTLINED, bgcolor=theme.PRIMARY, disabled=True,
                                         on_click=lambda e: open_print_dialog(sorted(selected_ids), 'الفواتير المحددة'))
    print_all_btn = ft.OutlinedButton('طباعة كل النتائج', icon=ft.Icons.PRINT_OUTLINED,
                                      on_click=lambda e: open_print_dialog(list(visible_ids), 'كل الفواتير الظاهرة'))

    def update_selection_ui():
        n = len(selected_ids)
        print_selected_btn.content = f'طباعة المحدد ({n})'
        print_selected_btn.disabled = n == 0
        print_all_btn.content = f'طباعة كل النتائج ({len(visible_ids)})'
        print_all_btn.disabled = not visible_ids
        selection_label.value = (f'المحدد للطباعة: {n} فاتورة' if n else 'حدّد فواتير من الجدول (أو "تحديد الكل" من رأس الجدول) لطباعتها في ملف واحد، أو اضغط "طباعة كل النتائج"')

    def refresh_list(e=None):
        try:
            rows = services.search_invoices(kind, _parse(from_f.value), _parse(to_f.value), search_f.value, limit=1000)
        except Exception:
            rows = list_invoices()
        visible_ids[:] = [r.id for r in rows]
        selected_ids.intersection_update(visible_ids)
        row_by_id.clear()
        table_sortable.set_data(rows)
        update_selection_ui()
        if e is not None:
            page.update()

    def _parse(v):
        v = (v or '').strip()
        try:
            return datetime.datetime.strptime(v, '%Y-%m-%d').date() if v else None
        except ValueError:
            return None

    def open_print_dialog(ids, scope_label):
        if not ids:
            page.overlay.append(ft.SnackBar(ft.Text('مفيش فواتير للطباعة'), open=True)); page.update(); return
        rows = {r.id: r for r in services.search_invoices(kind, limit=5000)}
        chosen = [rows[i] for i in ids if i in rows]
        n_void = sum(1 for r in chosen if getattr(r, 'voided', False))
        total = sum(r.total or 0 for r in chosen if not getattr(r, 'voided', False))
        summary_sw = ft.Switch(label='صفحة كشف بإجماليات الفواتير في أول الملف', value=len(ids) > 1, disabled=len(ids) < 2)
        void_sw = ft.Switch(label='طباعة الفواتير الملغاة كمان', value=False, visible=n_void > 0)
        perr = ft.Text('', color=theme.DANGER, visible=False, size=12)

        def confirm(ev):
            try:
                res = services.generate_invoices_batch_pdf_file(ids, kind, include_summary=summary_sw.value, include_voided=void_sw.value)
                pdlg.open = False; page.update()
                theme.open_or_download_file(page, res['path'])
                msg = f"تم تجهيز ملف الطباعة - {res['count']} فاتورة" + (f" (تجاهلت {res['skipped_voided']} ملغاة)" if res['skipped_voided'] else '')
                page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()
            except Exception as ex:
                perr.value = str(ex); perr.visible = True; page.update()

        pdlg = ft.AlertDialog(modal=True, title=ft.Text(f'طباعة {labels["title"]}'),
            content=ft.Container(width=440, content=ft.Column([
                ft.Text(f'{scope_label}: {len(ids)} فاتورة' + (f' (منها {n_void} ملغاة)' if n_void else '') + f'  |  الإجمالي {total:,.2f}', weight=ft.FontWeight.BOLD),
                ft.Text('كل فاتورة بتطلع في صفحة مستقلة في ملف PDF واحد، مرتبة بالتاريخ' + (' ومعاها QR الزكاة.' if is_sales else '.'), size=12, color=theme.TEXT_MUTED),
                summary_sw, void_sw, perr], tight=True, spacing=10)),
            actions=[ft.TextButton('إلغاء', on_click=lambda ev: (setattr(pdlg, 'open', False), page.update())),
                     ft.FilledButton('طباعة', icon=ft.Icons.PRINT_OUTLINED, bgcolor=theme.PRIMARY, on_click=confirm)])
        page.overlay.append(pdlg); pdlg.open = True; page.update()

    for _ctl in (from_f, to_f):
        _ctl.on_change = refresh_list
    search_f.on_change = refresh_list

    def clear_filters(e=None):
        from_f.value = ''; to_f.value = ''; search_f.value = ''
        refresh_list(e if e is not None else True)

    clear_btn = ft.TextButton('مسح الفلاتر', icon=ft.Icons.FILTER_ALT_OFF, on_click=clear_filters)

    # ---------- Create Dialog ----------
    party_dd = theme.SearchableDropdown(label=labels["party_label"], options=[], width=280)
    branches = services.list_branches(True); allowed=services.user_branch_ids(); branches=[b for b in branches if not allowed or b.id in allowed]; centers = services.list_cost_centers(True)
    branch_dd = ft.Dropdown(label="الفرع", width=220, options=[ft.dropdown.Option(str(b.id), f"{b.code} - {b.name}") for b in branches], value=str(services.default_branch_id()) if services.default_branch_id() else None)
    center_dd = ft.Dropdown(label="مركز التكلفة", width=220, options=[ft.dropdown.Option(str(c.id), f"{c.code} - {c.name}") for c in centers], value=str(services.default_cost_center_id()) if services.default_cost_center_id() else None)
    notes_field = ft.TextField(label="ملاحظات", multiline=True, min_lines=1, max_lines=2)
    # عملة الفاتورة: الأسعار في السطور بتتكتب بالعملة المختارة وبتتحوّل للأساسي بسعر الصرف عند الحفظ
    from .. import fx as _fx
    _curs = [c for c in _fx.list_currencies(active_only=True)]
    currency_dd = ft.Dropdown(label="العملة", width=130, value=_fx.base_code(), options=[ft.dropdown.Option(c.code, c.code) for c in _curs], visible=len(_curs) > 1)
    rate_f = ft.TextField(label="سعر الصرف", width=130, value="1", keyboard_type=ft.KeyboardType.NUMBER, visible=False)
    fx_hint = ft.Text("", size=11.5, color=theme.WARNING_TEXT, visible=False)

    def on_currency(e=None):
        foreign = _fx.is_foreign(currency_dd.value)
        rate_f.visible = foreign; fx_hint.visible = foreign
        if foreign:
            try:
                rate_f.value = f"{_fx.get_rate(currency_dd.value):g}"; fx_hint.value = f"اكتب أسعار الأصناف بـ {currency_dd.value} (سعر الصنف الافتراضي بالعملة الأساسية)"
            except ValueError as ex:
                rate_f.value = ""; fx_hint.value = str(ex)
        page.update()
    currency_dd.on_select = on_currency
    global_discount = ft.TextField(label="خصم إجمالي", value="0",
                                    keyboard_type=ft.KeyboardType.NUMBER, width=140)

    product_dd = theme.SearchableDropdown(label="الصنف", options=[], width=280)
    unit_dd = ft.Dropdown(label="وحدة البيع/الشراء", options=[], width=180)
    qty_field = ft.TextField(label="الكمية", value="1", keyboard_type=ft.KeyboardType.NUMBER, width=100)
    price_field = ft.TextField(label="سعر الوحدة", value="0", keyboard_type=ft.KeyboardType.NUMBER, width=130)
    price_hint = ft.Text("", size=11, color=theme.PRIMARY, visible=False)
    disc_field = ft.TextField(label="خصم", value="0", keyboard_type=ft.KeyboardType.NUMBER, width=100)
    tax_field = ft.TextField(label="ضريبة%", value="15", keyboard_type=ft.KeyboardType.NUMBER, width=100)

    products_map = {}

    # فواتير المبيعات والمشتريات: سطور الفاتورة في جدول (شكل Excel) بدل نموذج الإضافة صنف-صنف
    use_grid = True
    grid = None
    if use_grid:
        from ._invoice_grid import InvoiceLinesGrid
        grid = InvoiceLinesGrid(page, is_sales=is_sales, on_change=lambda: (recompute_totals(), page.update()))

    def refresh_dropdowns():
        parties = list_parties()
        party_dd.options = [ft.dropdown.Option(key=str(p.id), text=p.name) for p in parties]
        if not party_dd.value and party_dd.options:
            party_dd.value = party_dd.options[0].key

        all_products = services.list_products()
        products = [p for p in all_products if (p.can_be_sold if is_sales else p.can_be_purchased)]
        products_map.clear()
        for p in products:
            products_map[str(p.id)] = p
        if use_grid:
            grid.set_products(products)
            return
        product_dd.options = [ft.dropdown.Option(key=str(p.id), text=f"{p.sku} - {p.name}") for p in products]
        if not product_dd.value and product_dd.options:
            product_dd.value = product_dd.options[0].key
            on_product_change(None)

    def _resolve_sale_price(p, unit_default):
        """سعر صنف لفاتورة مبيعات: سعر قائمة الأسعار المربوطة بالعميل
        المختار (لو موجود) بياخد الأولوية، وإلا سعر الوحدة، وإلا سعر
        البيع الافتراضي المسجّل على الصنف."""
        customer_id = int(party_dd.value) if party_dd.value else None
        price, from_list = services.get_customer_product_price(customer_id, p.id)
        if from_list:
            return price, True
        if unit_default and unit_default.sale_price is not None:
            return unit_default.sale_price, False
        return p.sale_price, False

    def on_product_change(e):
        if product_dd.value and product_dd.value in products_map:
            p = products_map[product_dd.value]
            lines = services.list_product_units(p.id)
            unit_dd.options = [ft.dropdown.Option(str(x.unit_id), x.unit.name) for x in lines]
            default = next((x for x in lines if x.is_default), lines[0] if lines else None)
            unit_dd.value = str(default.unit_id) if default else None
            if is_sales:
                price, from_list = _resolve_sale_price(p, default)
                price_field.value = f"{price:g}"
                price_hint.value = "سعر خاص من قائمة أسعار العميل" if from_list else ""
                price_hint.visible = from_list
            elif default and default.cost_price is not None:
                price_field.value = f"{default.cost_price:g}"
            else:
                price_field.value = f"{p.cost_price:g}"
            tax_field.value = f"{p.tax_rate:g}"
            page.update()

    if is_sales:
        # سعر الصنف في الشبكة بيتحدد من قائمة أسعار العميل (لو مربوط بقائمة) وبيتعاد
        # تسعير السطور أوتوماتيك لما العميل يتغيّر (من غير ما يلمس الأسعار المعدّلة يدويًا).
        grid.price_resolver = _resolve_sale_price

        def on_party_change_for_price(e):
            if use_grid:
                grid.reprice(); page.update()
            elif product_dd.value and product_dd.value in products_map:
                on_product_change(None)
        party_dd.on_change = on_party_change_for_price

    def on_unit_change(e):
        if product_dd.value and unit_dd.value:
            p = products_map.get(product_dd.value)
            x = services.get_product_unit(int(product_dd.value), int(unit_dd.value))
            if is_sales and p:
                price, from_list = _resolve_sale_price(p, x)
                price_field.value = f"{price:g}"
                price_hint.value = "سعر خاص من قائمة أسعار العميل" if from_list else ""
                price_hint.visible = from_list
                page.update()
            elif x and x.cost_price is not None:
                price_field.value = f"{x.cost_price:g}"
                page.update()

    product_dd.on_change = on_product_change
    unit_dd.on_change = on_unit_change

    items_state = []  # list of dicts

    items_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("الصنف")),
            ft.DataColumn(ft.Text("الوحدة")),
            ft.DataColumn(ft.Text("الكمية")),
            ft.DataColumn(ft.Text("السعر")),
            ft.DataColumn(ft.Text("الخصم")),
            ft.DataColumn(ft.Text("ضريبة%")),
            ft.DataColumn(ft.Text("الإجمالي")),
            ft.DataColumn(ft.Text("")),
        ],
        rows=[],
    )

    subtotal_txt = ft.Text("0.00", weight=ft.FontWeight.BOLD)
    tax_txt = ft.Text("0.00", weight=ft.FontWeight.BOLD)
    disc_txt = ft.Text("0.00", weight=ft.FontWeight.BOLD)
    total_txt = ft.Text("0.00", weight=ft.FontWeight.BOLD, size=18, color=theme.PRIMARY)
    form_error = ft.Text("", color=theme.DANGER, visible=False)

    def recompute_totals():
        subtotal = 0.0
        tax_total = 0.0
        grand = 0.0
        for it in (grid.preview_items() if use_grid else items_state):
            base = max(0.0, it["quantity"] * it["unit_price"] - it["discount"])
            tax = base * (it["tax_rate"] / 100.0)
            subtotal += base
            tax_total += tax
            grand += base + tax
        try:
            gd = float(global_discount.value or 0)
        except Exception:
            gd = 0
        grand = max(0.0, grand - gd)
        subtotal_txt.value = f"{subtotal:,.2f}"
        tax_txt.value = f"{tax_total:,.2f}"
        disc_txt.value = f"{gd:,.2f}"
        total_txt.value = f"{grand:,.2f}"

    def rebuild_items_table():
        rows = []
        for idx, it in enumerate(items_state):
            p = products_map.get(str(it["product_id"]))
            name = p.name if p else "-"
            unit_name = it.get("unit_name") or (p.unit if p else "-")
            base = max(0.0, it["quantity"] * it["unit_price"] - it["discount"])
            line_total = base * (1 + it["tax_rate"] / 100.0)
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(name)),
                ft.DataCell(ft.Text(unit_name)),
                ft.DataCell(ft.Text(f"{it['quantity']:g}")),
                ft.DataCell(ft.Text(f"{it['unit_price']:,.2f}")),
                ft.DataCell(ft.Text(f"{it['discount']:,.2f}")),
                ft.DataCell(ft.Text(f"{it['tax_rate']:g}%")),
                ft.DataCell(ft.Text(f"{line_total:,.2f}", weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER,
                    on_click=lambda e, i=idx: remove_item(i),
                )),
            ]))
        items_table.rows = rows
        recompute_totals()
        page.update()

    def remove_item(i):
        del items_state[i]
        rebuild_items_table()

    def add_item(e):
        try:
            if not product_dd.value:
                raise ValueError("اختر الصنف")
            qty = float(qty_field.value or 0)
            price = float(price_field.value or 0)
            disc = float(disc_field.value or 0)
            tr = float(tax_field.value or 0)
            if qty <= 0:
                raise ValueError("الكمية يجب أن تكون أكبر من صفر")
            unit_id = int(unit_dd.value) if unit_dd.value else None
            unit_line = services.get_product_unit(int(product_dd.value), unit_id) if unit_id else None
            items_state.append({
                "product_id": int(product_dd.value),
                "unit_id": unit_id,
                "unit_name": unit_line.unit.name if unit_line else products_map[product_dd.value].unit,
                "quantity": qty,
                "unit_price": price,
                "discount": disc,
                "tax_rate": tr,
            })
            qty_field.value = "1"
            disc_field.value = "0"
            form_error.visible = False
            rebuild_items_table()
        except Exception as ex:
            form_error.value = str(ex)
            form_error.visible = True
            page.update()

    global_discount.on_change = lambda e: (recompute_totals(), page.update())

    # ---------- حفظ تلقائي للمسودة (لو الاتصال قطع ما يضيعش اللي اتكتب) ----------
    DRAFT_KIND = f"invoice_{kind}"
    draft_state = {"on": False}
    draft_note_text = ft.Text("", color=theme.WARNING_TEXT, expand=True, size=12.5)
    draft_note = ft.Container(
        visible=False, padding=8, border_radius=8, bgcolor=theme.SURFACE_ALT,
        content=ft.Row([ft.Icon(ft.Icons.RESTORE, color=theme.WARNING_TEXT, size=18), draft_note_text,
                        ft.TextButton("تجاهل المسودة", on_click=lambda e: discard_invoice_draft())], spacing=8))

    def collect_invoice_draft():
        return {"party": party_dd.value or "", "branch": branch_dd.value or "", "center": center_dd.value or "",
                "currency": currency_dd.value or "", "rate": rate_f.value or "", "notes": notes_field.value or "",
                "discount": global_discount.value or "0", "items": grid.snapshot()}

    def invoice_draft_is_empty(d):
        try:
            zero_disc = float(d["discount"] or 0) == 0
        except ValueError:
            zero_disc = False
        return not d["items"] and not d["notes"].strip() and zero_disc

    def autosave_invoice_draft(e=None):
        if not draft_state["on"]:
            return
        d = collect_invoice_draft()
        if invoice_draft_is_empty(d):
            drafts.clear(DRAFT_KIND)
        else:
            drafts.save(DRAFT_KIND, d)

    def restore_invoice_draft():
        saved = drafts.load(DRAFT_KIND)
        if not saved:
            return
        d, at = saved
        draft_state["on"] = False
        try:
            valid_party = {o.key for o in party_dd.options}
            if d.get("party") in valid_party:
                party_dd.value = d["party"]
            for dd, key in ((branch_dd, "branch"), (center_dd, "center")):
                if d.get(key) and any(o.key == d[key] for o in dd.options):
                    dd.value = d[key]
            if d.get("currency") and any(o.key == d["currency"] for o in currency_dd.options):
                currency_dd.value = d["currency"]
                on_currency()
                if d.get("rate"):
                    rate_f.value = d["rate"]
            notes_field.value = d.get("notes", "")
            global_discount.value = d.get("discount") or "0"
            items = [it for it in d.get("items", []) if str(it.get("product_id")) in products_map]
            if items:
                grid.load_items(items)
            recompute_totals()
            draft_note_text.value = f"اتسترجعت مسودة فاتورة غير محفوظة (آخر حفظ {at:%Y-%m-%d %H:%M}) - كمّل واحفظ، أو اضغط تجاهل."
            draft_note.visible = True
        finally:
            draft_state["on"] = True

    def discard_invoice_draft():
        drafts.clear(DRAFT_KIND)
        draft_note.visible = False
        notes_field.value = ""; global_discount.value = "0"
        grid.clear(); recompute_totals()
        page.update()

    def close_create(e=None):
        create_dialog.open = False
        draft_state["on"] = False
        try:
            if invoice_draft_is_empty(collect_invoice_draft()):
                drafts.clear(DRAFT_KIND)          # نموذج فاضي: مفيش حاجة تتحفظ. لو فيه بيانات المسودة بتفضل
        except Exception:      # noqa: BLE001
            pass
        page.update()

    def save_invoice(e):
        try:
            items = grid.get_items() if use_grid else list(items_state)
            if not items:
                raise ValueError("أضف صنف واحد على الأقل")
            party_id = int(party_dd.value) if party_dd.value else None
            invoice_id = create_invoice(
                party_id, items,
                notes=notes_field.value or "",
                discount=float(global_discount.value or 0),
                branch_id=int(branch_dd.value) if branch_dd.value else None,
                cost_center_id=int(center_dd.value) if center_dd.value else None,
                **({"currency": currency_dd.value, "exchange_rate": rate_f.value} if _fx.is_foreign(currency_dd.value) else {}),
            )
            drafts.clear(DRAFT_KIND)
            draft_state["on"] = False
            close_create()
            refresh_list()
            open_preview(invoice_id)
        except Exception as ex:
            form_error.value = str(ex)
            form_error.visible = True
            page.update()
            approval_prompt(page, ex)

    _prev_party_change = party_dd.on_change
    party_dd.on_change = lambda e: ((_prev_party_change(e) if _prev_party_change else None), autosave_invoice_draft())
    grid.on_change = lambda: (recompute_totals(), autosave_invoice_draft(), page.update())
    global_discount.on_change = lambda e: (recompute_totals(), autosave_invoice_draft(), page.update())
    notes_field.on_change = autosave_invoice_draft
    for _dd in (branch_dd, center_dd):
        _dd.on_select = autosave_invoice_draft if hasattr(_dd, "on_select") else None

    if use_grid:
        lines_section = [
            ft.Text("أصناف الفاتورة", weight=ft.FontWeight.BOLD),
            ft.Text("اكتب كود أو اسم الصنف واضغط Enter، وكمّل بـ Enter: الكمية ← السعر ← الخصم ← الصنف اللي بعده. "
                    "السطر الفاضي بيتضاف تلقائيًا.", size=12, color=theme.TEXT_MUTED),
            grid.control,
        ]
    else:
        lines_section = [
            ft.Text("إضافة أصناف", weight=ft.FontWeight.BOLD),
            ft.Row(
                [product_dd.control, unit_dd, qty_field, price_field, disc_field, tax_field,
                 ft.FilledButton("إضافة", icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=add_item)],
                wrap=True, spacing=10,
            ),
            price_hint,
            ft.Container(
                content=ft.Column([theme.h_scroll(items_table)], scroll=ft.ScrollMode.AUTO),
                height=200,
            ),
        ]

    create_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(labels["add_btn"]),
        content=ft.Container(
            width=1080 if use_grid else 900,
            content=ft.Column([
                draft_note,
                ft.Row([party_dd.control, branch_dd, center_dd, currency_dd, rate_f], spacing=12, wrap=True),
                fx_hint,
                ft.Row([notes_field], spacing=12),
                ft.Divider(),
                *lines_section,
                ft.Divider(),
                ft.Row([
                    ft.Column([ft.Text("الإجمالي قبل الضريبة", color=theme.TEXT_MUTED), subtotal_txt], spacing=2),
                    ft.Column([ft.Text("مجموع الضريبة", color=theme.TEXT_MUTED), tax_txt], spacing=2),
                    ft.Column([ft.Text("خصم الفاتورة", color=theme.TEXT_MUTED), global_discount], spacing=2),
                    ft.Container(expand=True),
                    ft.Column([ft.Text("الإجمالي النهائي", color=theme.TEXT_MUTED), total_txt], spacing=2),
                ], spacing=20),
                form_error,
            ], spacing=10, tight=True),
        ),
        actions=[
            ft.TextButton("إلغاء", on_click=close_create),
            ft.FilledButton("حفظ الفاتورة", icon=ft.Icons.SAVE_OUTLINED,
                            bgcolor=theme.PRIMARY, on_click=save_invoice),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(create_dialog)

    def open_create(e):
        items_state.clear()
        notes_field.value = ""
        global_discount.value = "0"
        qty_field.value = "1"
        price_field.value = "0"
        disc_field.value = "0"
        tax_field.value = "15"
        form_error.visible = False
        draft_note.visible = False
        draft_state["on"] = False
        refresh_dropdowns()
        if use_grid:
            grid.clear()
        else:
            rebuild_items_table()
        restore_invoice_draft()
        draft_state["on"] = True
        create_dialog.open = True
        page.update()
        if use_grid:
            grid.focus_first()

    # ---------- Preview / Print Dialog ----------
    preview_dialog = ft.AlertDialog(modal=True, title=ft.Text(""), content=ft.Container())
    page.overlay.append(preview_dialog)

    def close_preview(e=None):
        preview_dialog.open = False
        page.update()

    def open_preview(invoice_id):
        inv = get_invoice(invoice_id)
        if not inv:
            return

        settings = services.get_company_settings()
        party = inv.customer if is_sales else inv.supplier
        party_name = party.name if party else "-"
        party_vat = party.vat_number if party and party.vat_number else "-"

        # Build QR (ZATCA) - only for sales invoices
        qr_img = None
        if is_sales:
            iso = inv.date.strftime("%Y-%m-%dT%H:%M:%SZ")
            from ..zatca_p2 import qr_png_for_invoice
            b64 = qr_png_for_invoice(inv.id) or zatca_qr_png_base64(
                settings.name or "-",
                settings.vat_number or "-",
                iso,
                inv.total,
                inv.tax_total,
            )
            if b64:
                qr_img = ft.Image(src=base64.b64decode(b64), width=140, height=140)

        item_rows = []
        for it in inv.items:
            p = it.product
            base = max(0.0, it.quantity * it.unit_price - it.discount)
            item_rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(p.name if p else "-")),
                ft.DataCell(ft.Text(f"{it.quantity:g}")),
                ft.DataCell(ft.Text(f"{it.unit_price:,.2f}")),
                ft.DataCell(ft.Text(f"{it.discount:,.2f}")),
                ft.DataCell(ft.Text(f"{it.tax_rate:g}%")),
                ft.DataCell(ft.Text(f"{it.line_total:,.2f}", weight=ft.FontWeight.BOLD)),
            ]))

        items_dt = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("الصنف")),
                ft.DataColumn(ft.Text("الكمية")),
                ft.DataColumn(ft.Text("السعر")),
                ft.DataColumn(ft.Text("الخصم")),
                ft.DataColumn(ft.Text("ضريبة%")),
                ft.DataColumn(ft.Text("الإجمالي")),
            ],
            rows=item_rows,
        )

        header_left = ft.Column([
            ft.Text(settings.name or "-", size=20, weight=ft.FontWeight.BOLD),
            ft.Text(f"الرقم الضريبي: {settings.vat_number or '-'}", color=theme.TEXT_MUTED),
            ft.Text(f"العنوان: {settings.address or '-'}", color=theme.TEXT_MUTED),
            ft.Text(f"الهاتف: {settings.phone or '-'}", color=theme.TEXT_MUTED),
        ], spacing=2)

        header_right = ft.Column([
            ft.Text(labels["preview_title"], size=20, weight=ft.FontWeight.BOLD, color=theme.PRIMARY),
            ft.Text(f"رقم الفاتورة: {inv.number}", weight=ft.FontWeight.BOLD),
            ft.Text(f"التاريخ: {inv.date.strftime('%Y-%m-%d %H:%M')}"),
            ft.Text(f"{labels['party_label']}: {party_name}"),
            ft.Text(f"الرقم الضريبي: {party_vat}", color=theme.TEXT_MUTED),
        ] + ([ft.Container(
            content=ft.Text("فاتورة B2B - شركة" if getattr(party, "party_type", None) == "company" else "فاتورة B2C - فرد",
                            size=11, weight=ft.FontWeight.BOLD,
                            color=theme.PRIMARY if getattr(party, "party_type", None) == "company" else theme.TEXT_MUTED),
            bgcolor=theme.PRIMARY_LIGHT if getattr(party, "party_type", None) == "company" else theme.SURFACE_ALT,
            padding=ft.Padding(left=10, right=10, top=4, bottom=4), border_radius=12,
        )] if is_sales and party else []), spacing=2, horizontal_alignment=ft.CrossAxisAlignment.END)

        totals_col = ft.Column([
            ft.Row([ft.Text("الإجمالي قبل الضريبة", color=theme.TEXT_MUTED),
                    ft.Container(expand=True),
                    ft.Text(f"{inv.subtotal:,.2f}", weight=ft.FontWeight.BOLD)]),
            ft.Row([ft.Text("مجموع الضريبة", color=theme.TEXT_MUTED),
                    ft.Container(expand=True),
                    ft.Text(f"{inv.tax_total:,.2f}", weight=ft.FontWeight.BOLD)]),
            ft.Row([ft.Text("خصم الفاتورة", color=theme.TEXT_MUTED),
                    ft.Container(expand=True),
                    ft.Text(f"{inv.discount:,.2f}", weight=ft.FontWeight.BOLD)]),
            ft.Divider(),
            ft.Row([ft.Text("الإجمالي النهائي", size=16, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.Text(f"{inv.total:,.2f}", size=18, weight=ft.FontWeight.BOLD, color=theme.PRIMARY)]),
        ], spacing=6)

        bottom_row_controls = [ft.Container(content=totals_col, width=340)]
        if qr_img:
            bottom_row_controls.append(ft.Container(expand=True))
            bottom_row_controls.append(ft.Column([
                ft.Text("QR الزكاة السعودية", size=12, color=theme.TEXT_MUTED),
                qr_img,
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6))

        attachments_section = ft.Column([], spacing=6)

        def refresh_attachments():
            atts = services.list_purchase_invoice_attachments(inv.id)
            rows = [ft.Text('مرفقات فاتورة المورد', size=13, weight=ft.FontWeight.BOLD)]
            if not atts:
                rows.append(ft.Text('لا يوجد مرفقات بعد', color=theme.TEXT_MUTED, size=12))
            for a in atts:
                def open_att(e, path=a.file_path):
                    try:
                        theme.open_or_download_file(page, path)
                    except Exception as ex:
                        page.overlay.append(ft.SnackBar(ft.Text(f'تعذر فتح الملف: {ex}'), open=True)); page.update()

                def delete_att(e, att_id=a.id):
                    try:
                        services.delete_purchase_invoice_attachment(att_id)
                        refresh_attachments()
                        page.update()
                    except Exception as ex:
                        page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True, data='error')); page.update()

                rows.append(ft.Row([
                    ft.Icon(ft.Icons.ATTACH_FILE, size=16, color=theme.PRIMARY),
                    ft.TextButton(a.file_name, on_click=open_att),
                    ft.Container(expand=True),
                    ft.Text(a.uploaded_at.strftime('%Y-%m-%d %H:%M'), size=11, color=theme.TEXT_MUTED),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, icon_size=18, on_click=delete_att),
                ]))
            attachments_section.controls = rows
            page.update()

        async def pick_attachment(e):
            try:
                path = await theme.pick_file(page, 'اختر فاتورة المورد', ['pdf','png','jpg','jpeg'])
                if not path:
                    return
                services.attach_purchase_invoice_file(inv.id, path)
                refresh_attachments()
            except Exception as ex:
                page.overlay.append(ft.SnackBar(ft.Text(f'تعذر إرفاق الملف: {ex}'), open=True)); page.update()

        if not is_sales:
            refresh_attachments()

        body = ft.Container(
            width=780,
            content=ft.Column([
                ft.Row([header_left, ft.Container(expand=True), header_right]),
                ft.Divider(),
                ft.Container(content=ft.Column([theme.h_scroll(items_dt)], scroll=ft.ScrollMode.AUTO), height=220),
                ft.Divider(),
                ft.Row(bottom_row_controls, vertical_alignment=ft.CrossAxisAlignment.START),
                ft.Text(f"ملاحظات: {inv.notes}" if inv.notes else "", color=theme.TEXT_MUTED),
            ] + ([
                ft.Divider(),
                ft.Row([ft.OutlinedButton('تصفح واختيار ملف...', icon=ft.Icons.ATTACH_FILE, on_click=pick_attachment)], wrap=True),
                attachments_section,
            ] if not is_sales else []), spacing=12, scroll=ft.ScrollMode.AUTO, tight=True),
        )

        share_status = ft.Text('', size=11, visible=False)

        def do_print(e):
            try:
                path = services.generate_invoice_pdf_file(inv.id, kind='sales' if is_sales else 'purchase')
                theme.open_or_download_file(page, path)
            except Exception as ex:
                share_status.value = f'تعذرت الطباعة: {ex}'
                share_status.color = theme.DANGER
                share_status.visible = True
            page.update()

        def do_email(e):
            default_email = party.email if (party and hasattr(party, 'email')) else ''
            email_field = ft.TextField(label='البريد الإلكتروني', value=default_email or '', width=320)
            send_err = ft.Text('', color=theme.DANGER, visible=False)

            def send(ev):
                try:
                    services.email_invoice(inv.id, email_field.value)
                    email_dialog.open = False
                    share_status.value = 'تم إرسال الفاتورة بالإيميل بنجاح'
                    share_status.color = theme.SUCCESS
                    share_status.visible = True
                except Exception as ex:
                    send_err.value = str(ex)
                    send_err.visible = True
                page.update()

            email_dialog = ft.AlertDialog(
                modal=True, title=ft.Text('إرسال الفاتورة بالإيميل'),
                content=ft.Column([email_field, send_err], tight=True, spacing=10),
                actions=[
                    ft.TextButton('إلغاء', on_click=lambda ev: (setattr(email_dialog, 'open', False), page.update())),
                    ft.FilledButton('إرسال', bgcolor=theme.PRIMARY, on_click=send),
                ],
            )
            page.overlay.append(email_dialog)
            email_dialog.open = True
            page.update()

        def do_whatsapp(e):
            try:
                services.generate_invoice_pdf_file(inv.id, kind='sales' if is_sales else 'purchase')
                phone = party.phone if party else ''
                link = services.whatsapp_share_link(phone, inv.number, inv.total)
                theme.launch_url(page, link)
                share_status.value = 'فُتح واتساب - الملف محفوظ في مجلد exports لإرفاقه يدوياً'
                share_status.color = theme.TEXT_MUTED
                share_status.visible = True
            except Exception as ex:
                share_status.value = str(ex)
                share_status.color = theme.DANGER
                share_status.visible = True
            page.update()

        def do_void(e):
            def confirm_void(ev):
                try:
                    if is_sales:
                        services.void_sales_invoice(inv.id)
                    else:
                        services.void_purchase_invoice(inv.id)
                    void_confirm.open = False
                    preview_dialog.open = False
                    page.update()
                    refresh_list()
                except Exception as ex:
                    void_err.value = str(ex)
                    void_err.visible = True
                    page.update()

            void_err = ft.Text('', color=theme.DANGER, visible=False)
            void_confirm = ft.AlertDialog(
                modal=True, title=ft.Text('تأكيد الإلغاء'),
                content=ft.Column([
                    ft.Text(f'هل تريد إلغاء الفاتورة {inv.number}؟ هيترجع تأثيرها على المخزون والحسابات بالكامل.'),
                    void_err,
                ], tight=True),
                actions=[
                    ft.TextButton('تراجع', on_click=lambda ev: (setattr(void_confirm, 'open', False), page.update())),
                    ft.FilledButton('تأكيد الإلغاء', bgcolor=theme.DANGER, on_click=confirm_void),
                ],
            )
            page.overlay.append(void_confirm)
            void_confirm.open = True
            page.update()

        preview_dialog.title = ft.Text(f"معاينة الفاتورة {inv.number}" + (' (ملغاة)' if getattr(inv, 'voided', False) else ''))
        preview_dialog.content = ft.Column([body, share_status], tight=True, spacing=8)
        preview_dialog.actions = [ft.TextButton("إغلاق", on_click=close_preview)]

        action_buttons = [ft.IconButton(icon=ft.Icons.PRINT_OUTLINED, tooltip='طباعة', on_click=do_print)]
        if is_sales:
            action_buttons += [
                ft.IconButton(icon=ft.Icons.EMAIL_OUTLINED, tooltip='إرسال بالإيميل', on_click=do_email),
                ft.IconButton(icon=ft.Icons.CHAT_OUTLINED, tooltip='إرسال واتساب', on_click=do_whatsapp),
            ]
        if not getattr(inv, 'voided', False):
            action_buttons.append(ft.IconButton(icon=ft.Icons.CANCEL_OUTLINED, icon_color=theme.DANGER, tooltip='إلغاء الفاتورة', on_click=do_void))
        preview_dialog.actions = action_buttons + [
            ft.Container(expand=True),
            ft.TextButton("إغلاق", on_click=close_preview),
        ]
        preview_dialog.actions_alignment = ft.MainAxisAlignment.END
        preview_dialog.open = True
        page.update()

    # ---------- Layout ----------
    header = ft.Row(
        [theme.page_title(labels["title"], labels["subtitle"]),
         ft.Container(expand=True),
         ft.FilledButton(labels["add_btn"], icon=ft.Icons.ADD,
                          bgcolor=theme.PRIMARY, on_click=open_create)],
    )

    refresh_list()

    toolbar = ft.Row([range_f.control, search_f, clear_btn, ft.Container(expand=True), print_all_btn, print_selected_btn], spacing=10)

    return ft.Column(
        [header, ft.Container(height=8), toolbar, selection_label, ft.Container(height=4),
         theme.card(theme.h_scroll(table, vscroll=True), expand=True)],
        expand=True,
    )
