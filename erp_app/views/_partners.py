"""شاشة CRUD عامة للعملاء والموردين."""
import flet as ft
from .. import services, theme


def build_partner_view(page: ft.Page, kind: str):
    """kind: 'customer' or 'supplier'."""
    is_customer = kind == "customer"
    labels = {
        "title": "العملاء" if is_customer else "الموردين",
        "subtitle": ("إدارة بيانات العملاء") if is_customer else ("إدارة بيانات الموردين"),
        "add_btn": "إضافة عميل" if is_customer else "إضافة مورد",
        "add_title": "إضافة عميل جديد" if is_customer else "إضافة مورد جديد",
        "edit_title": "تعديل بيانات العميل" if is_customer else "تعديل بيانات المورد",
        "name_label": "اسم العميل" if is_customer else "اسم المورد",
        "type_label": "نوع العميل (B2C / B2B)",
    }

    list_fn = services.list_customers if is_customer else services.list_suppliers
    create_fn = services.create_customer if is_customer else services.create_supplier
    update_fn = services.update_customer if is_customer else services.update_supplier
    delete_fn = services.delete_customer if is_customer else services.delete_supplier

    postable_accounts = services.list_accounts(postable_only=True)
    default_account_label = "الذمم المدينة (افتراضي)" if is_customer else "الذمم الدائنة (افتراضي)"

    search = ft.TextField(label="بحث", width=280, prefix_icon=ft.Icons.SEARCH, border_radius=10)

    TYPE_LABELS = {"individual": "B2C - فرد", "company": "B2B - شركة"}

    def _row_builder(r):
        accounts_by_id = {a.id: f"{a.code} - {a.name}" for a in postable_accounts}
        account_text = accounts_by_id.get(getattr(r, "account_id", None), default_account_label)
        cells = [ft.DataCell(ft.Text(r.name))]
        if is_customer:
            type_text = TYPE_LABELS.get(getattr(r, "party_type", None), "B2C - فرد")
            cells.append(ft.DataCell(ft.Text(type_text, color=theme.PRIMARY if getattr(r, "party_type", None) == "company" else theme.TEXT_MUTED)))
        cells += [ft.DataCell(ft.Text(r.phone or "-")),
            ft.DataCell(ft.Text(r.vat_number or "-")),
            ft.DataCell(ft.Text(r.address or "-")),
            ft.DataCell(ft.Text(account_text, size=12)),
            ft.DataCell(ft.Row([
                ft.IconButton(icon=ft.Icons.EDIT_OUTLINED,
                              on_click=lambda e, rec=r: open_edit(rec)),
                ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER,
                              on_click=lambda e, rec=r: confirm_delete(rec)),
            ])),
        ]
        return ft.DataRow(cells=cells)

    table_sortable = theme.SortableDataTable(
        columns=([
            ("الاسم", lambda r: r.name),
            ("النوع", lambda r: TYPE_LABELS.get(getattr(r, "party_type", None), "B2C - فرد")),
        ] if is_customer else [("الاسم", lambda r: r.name)]) + [
            ("الهاتف", lambda r: r.phone),
            ("الرقم الضريبي", lambda r: r.vat_number),
            ("العنوان", lambda r: r.address),
            ("الحساب المحاسبي", None),
            ("الإجراءات", None),
        ],
        row_builder=_row_builder, page=page, expand=True,
    )
    table = table_sortable.control

    editing = {"id": None}
    name_field = ft.TextField(label=labels["name_label"], autofocus=True)
    type_group = ft.RadioGroup(value="individual", content=ft.Row([
        ft.Radio(value="individual", label="B2C - فرد"),
        ft.Radio(value="company", label="B2B - شركة"),
    ], spacing=20))
    phone_field = ft.TextField(label="الهاتف")
    loyalty_sw = ft.Switch(label="عضو في برنامج الولاء (نقاط)", value=False, visible=is_customer)
    _can_credit = services.user_has_action(services._get_user(), "credit", "edit")
    credit_limit_f = ft.TextField(label="حد الائتمان (0 = بلا حد)", width=180, value="0", keyboard_type=ft.KeyboardType.NUMBER, visible=is_customer, disabled=not _can_credit)
    credit_days_f = ft.TextField(label="مهلة السداد (يوم)", width=150, value="0", keyboard_type=ft.KeyboardType.NUMBER, visible=is_customer, disabled=not _can_credit)
    credit_hold_sw = ft.Switch(label="إيقاف البيع الآجل", value=False, visible=is_customer, disabled=not _can_credit)
    notify_sw = ft.Switch(label="موافق على استلام رسائل واتساب/SMS (إيصالات وعروض)", value=False, visible=is_customer)
    email_field = ft.TextField(label="البريد الإلكتروني", visible=is_customer)
    vat_field = ft.TextField(label="الرقم الضريبي")
    address_field = ft.TextField(label="العنوان الوطني", multiline=True, min_lines=2, max_lines=3)
    crn_f = ft.TextField(label="السجل التجاري", width=190, visible=is_customer)
    bno_f = ft.TextField(label="رقم المبنى (4 أرقام)", width=150, visible=is_customer)
    district_f = ft.TextField(label="الحي", width=170, visible=is_customer)
    city_f = ft.TextField(label="المدينة", width=170, visible=is_customer)
    postal_f = ft.TextField(label="الرمز البريدي", width=150, visible=is_customer)
    b2b_hint = ft.Text("عملاء B2B (شركات) لازم يكون عندهم رقم ضريبي سعودي صحيح (15 رقم يبدأ وينتهي بـ3) وعنوان وطني مسجّل - شرط أساسي للفاتورة الضريبية القياسية.",
                       size=11, color=theme.WARNING, visible=False)

    def sync_b2b_requirements(e=None):
        is_b2b = is_customer and type_group.value == "company"
        vat_field.label = "الرقم الضريبي *" if is_b2b else "الرقم الضريبي"
        address_field.label = "العنوان الوطني *" if is_b2b else "العنوان الوطني"
        b2b_hint.visible = is_b2b
        page.update()

    if is_customer:
        type_group.on_change = sync_b2b_requirements
    account_dd = ft.Dropdown(
        label="الحساب المحاسبي المرتبط",
        width=380,
        options=[ft.dropdown.Option("", default_account_label)] + [ft.dropdown.Option(str(a.id), f"{a.code} - {a.name}") for a in postable_accounts],
        value="",
    )
    price_list_dd = ft.Dropdown(
        label="قائمة الأسعار (اختياري)", width=260,
        options=[ft.dropdown.Option("", "بدون - السعر الافتراضي للصنف")] + [ft.dropdown.Option(str(pl.id), pl.name) for pl in services.list_price_lists(active_only=True)],
        value="",
    ) if is_customer else None
    form_error = ft.Text("", color=theme.DANGER, visible=False)

    def close_dialog(e=None):
        dialog.open = False
        page.update()

    def reset_form():
        editing["id"] = None
        name_field.value = ""
        type_group.value = "individual"
        phone_field.value = ""
        loyalty_sw.value = False; notify_sw.value = False
        credit_limit_f.value = '0'; credit_days_f.value = '0'; credit_hold_sw.value = False
        email_field.value = ""
        crn_f.value = bno_f.value = district_f.value = city_f.value = postal_f.value = ""
        vat_field.value = ""
        address_field.value = ""
        account_dd.value = ""
        if price_list_dd:
            price_list_dd.value = ""
        form_error.visible = False
        sync_b2b_requirements()

    def open_add(e):
        reset_form()
        dialog.title = ft.Text(labels["add_title"])
        dialog.open = True
        page.update()

    def open_edit(rec):
        editing["id"] = rec.id
        name_field.value = rec.name
        type_group.value = getattr(rec, "party_type", None) or "individual"
        phone_field.value = rec.phone or ""
        loyalty_sw.value = bool(getattr(rec, "loyalty_enabled", False)); notify_sw.value = bool(getattr(rec, "notify_opt_in", False))
        credit_limit_f.value = f"{float(getattr(rec, 'credit_limit', 0) or 0):g}"; credit_days_f.value = str(int(getattr(rec, 'credit_days', 0) or 0)); credit_hold_sw.value = bool(getattr(rec, 'credit_hold', False))
        email_field.value = getattr(rec, "email", "") or ""
        crn_f.value = getattr(rec, "crn", "") or ""; bno_f.value = getattr(rec, "building_no", "") or ""; district_f.value = getattr(rec, "district", "") or ""
        city_f.value = getattr(rec, "city", "") or ""; postal_f.value = getattr(rec, "postal_code", "") or ""
        vat_field.value = rec.vat_number or ""
        address_field.value = rec.address or ""
        account_dd.value = str(rec.account_id) if getattr(rec, "account_id", None) else ""
        if price_list_dd:
            price_list_dd.value = str(getattr(rec, "price_list_id", None)) if getattr(rec, "price_list_id", None) else ""
        form_error.visible = False
        sync_b2b_requirements()
        dialog.title = ft.Text(labels["edit_title"])
        dialog.open = True
        page.update()

    def save(e):
        try:
            data = {
                "name": (name_field.value or "").strip(),
                "phone": (phone_field.value or "").strip(),
                "vat_number": (vat_field.value or "").strip(),
                "address": (address_field.value or "").strip(),
                "account_id": int(account_dd.value) if account_dd.value else None,
            }
            if is_customer:
                data["email"] = (email_field.value or "").strip()
                data["crn"] = (crn_f.value or "").strip(); data["building_no"] = (bno_f.value or "").strip(); data["district"] = (district_f.value or "").strip()
                data["city"] = (city_f.value or "").strip(); data["postal_code"] = (postal_f.value or "").strip()
                data["loyalty_enabled"] = bool(loyalty_sw.value); data["notify_opt_in"] = bool(notify_sw.value)
                data["credit_limit"] = credit_limit_f.value or 0; data["credit_days"] = credit_days_f.value or 0; data["credit_hold"] = bool(credit_hold_sw.value)
                data["party_type"] = type_group.value or "individual"
                data["price_list_id"] = int(price_list_dd.value) if price_list_dd.value else None
            if not data["name"]:
                raise ValueError(labels["name_label"] + " مطلوب")
            if editing["id"] is None:
                create_fn(**data)
            else:
                update_fn(editing["id"], **data)
            close_dialog()
            refresh_table()
        except Exception as ex:
            form_error.value = str(ex)
            form_error.visible = True
            page.update()

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(labels["add_title"]),
        content=ft.Container(
            content=ft.Column(
                [name_field] + ([ft.Column([ft.Text(labels["type_label"], size=12, color=theme.TEXT_MUTED), type_group], spacing=2)] if is_customer else []) +
                [phone_field, email_field, loyalty_sw, notify_sw, ft.Row([credit_limit_f, credit_days_f, credit_hold_sw], wrap=True, visible=is_customer), vat_field, address_field, ft.Row([crn_f, bno_f, district_f, city_f, postal_f], wrap=True, spacing=8, visible=is_customer), b2b_hint] + ([price_list_dd] if price_list_dd else []) + [account_dd, form_error],
                spacing=12, tight=True,
            ),
            width=420,
        ),
        actions=[
            ft.TextButton("إلغاء", on_click=close_dialog),
            ft.FilledButton("حفظ", bgcolor=theme.PRIMARY, on_click=save),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(dialog)

    def confirm_delete(rec):
        def do_delete(e):
            try:
                delete_fn(rec.id)
                cd.open = False
                refresh_table()
            except Exception as ex:
                cd.content = ft.Text(str(ex), color=theme.DANGER)
                page.update()

        cd = ft.AlertDialog(
            modal=True,
            title=ft.Text("تأكيد الحذف"),
            content=ft.Text(f"هل تريد حذف «{rec.name}»؟"),
            actions=[
                ft.TextButton("إلغاء", on_click=lambda e: (setattr(cd, "open", False), page.update())),
                ft.FilledButton("حذف", bgcolor=theme.DANGER, on_click=do_delete),
            ],
        )
        page.overlay.append(cd)
        cd.open = True
        page.update()

    def refresh_table(e=None):
        table_sortable.set_data(list_fn(search=search.value or None))

    search.on_change = refresh_table

    header = ft.Row(
        [
            theme.page_title(labels["title"], labels["subtitle"]),
            ft.Container(expand=True),
            search,
            ft.FilledButton(labels["add_btn"], icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=open_add),
        ],
    )

    refresh_table()

    return ft.Column(
        [header, ft.Container(height=12), theme.card(theme.h_scroll(table, vscroll=True), expand=True)],
        expand=True,
    )
