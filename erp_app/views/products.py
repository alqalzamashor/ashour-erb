import flet as ft
from .. import services, theme, field_access


def build_products(page: ft.Page):
    SHOW_COST = field_access.can_see('cost_price')
    search_field = ft.TextField(label="بحث بالكود أو الاسم", width=320, prefix_icon=ft.Icons.SEARCH, border_radius=10)
    def _product_row(p):
        units = services.list_product_units(p.id); names = ", ".join(f"{u.unit.name}×{u.factor_to_base:g}" for u in units) or p.unit
        import os as _os
        if p.image_path and _os.path.exists(p.image_path):
            thumb = ft.Container(width=36, height=36, border_radius=6, content=ft.Image(src=p.image_path, width=36, height=36, fit=ft.BoxFit.COVER, border_radius=6))
        else:
            thumb = ft.Container(width=36, height=36, border_radius=6, bgcolor=theme.PRIMARY_LIGHT, alignment=ft.Alignment(0, 0), content=ft.Icon(ft.Icons.IMAGE_OUTLINED, size=16, color=theme.TEXT_MUTED))
        return ft.DataRow(cells=[ft.DataCell(thumb), ft.DataCell(ft.Text(p.sku)), ft.DataCell(ft.Text(p.name)), ft.DataCell(ft.Text(categories_cache.get(p.category_id, "-"))),
                                  ft.DataCell(ft.Text(p.unit)), ft.DataCell(ft.Text(names)), *([ft.DataCell(ft.Text(f"{p.cost_price:,.2f}"))] if SHOW_COST else []), ft.DataCell(ft.Text(f"{p.sale_price:,.2f}")),
                                  ft.DataCell(ft.Row([ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="تعديل الصنف", icon_color=theme.PRIMARY, on_click=lambda e, pid=p.id: open_edit_dialog(pid)),
                                                       ft.IconButton(ft.Icons.INVENTORY_2_OUTLINED, tooltip="وحدات الصنف", on_click=lambda e, pid=p.id: open_units_dialog(pid)),
                                                       ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip="إيقاف الصنف", on_click=lambda e, pid=p.id: (services.deactivate_product(pid), refresh_table()))]))])

    products_table_sortable = theme.SortableDataTable(
        columns=[("", None), ("الكود", lambda p: p.sku), ("الاسم", lambda p: p.name), ("الفئة", lambda p: categories_cache.get(p.category_id, "")),
                 ("الوحدة الأساسية", lambda p: p.unit), ("الوحدات", None), *([("سعر التكلفة", lambda p: p.cost_price, True)] if SHOW_COST else []),
                 ("سعر البيع", lambda p: p.sale_price, True), ("", None)],
        row_builder=_product_row, page=page, expand=True,
    )
    products_table = products_table_sortable.control
    categories_cache = {}
    sku_field = ft.TextField(label="الكود (SKU)")
    name_field = ft.TextField(label="اسم الصنف")
    unit_field = ft.Dropdown(label="الوحدة الأساسية", options=[], border_radius=10)
    cost_field = ft.TextField(label="سعر التكلفة للوحدة الأساسية", value="0", keyboard_type=ft.KeyboardType.NUMBER, visible=SHOW_COST)
    sale_field = ft.TextField(label="سعر البيع للوحدة الأساسية", value="0", keyboard_type=ft.KeyboardType.NUMBER)
    reorder_field = ft.TextField(label="حد إعادة الطلب (بالأساس)", value="0", keyboard_type=ft.KeyboardType.NUMBER)
    tax_field = ft.TextField(label="نسبة الضريبة %", value="15", keyboard_type=ft.KeyboardType.NUMBER)
    category_dropdown = ft.Dropdown(label="الفئة", options=[])
    form_error = ft.Text("", color=theme.DANGER, visible=False)
    sold_sw = ft.Switch(label="يُباع", value=True)
    purchased_sw = ft.Switch(label="يُشترى", value=True)
    cost_dd = ft.Dropdown(label="طريقة حساب التكلفة", width=330, value="auto", options=[ft.dropdown.Option(k, v) for k, v in services.COST_METHODS.items()])
    cost_note = ft.Text("", size=11.5, color=theme.TEXT_MUTED)
    issue_dd = ft.Dropdown(label="طريقة الإخراج", width=300, value="none", options=[ft.dropdown.Option(k, v) for k, v in services.BATCH_METHODS.items()])
    expiry_sw = ft.Switch(label="له تاريخ صلاحية", value=False)
    shelf_f = ft.TextField(label="مدة الصلاحية الافتراضية (يوم)", width=210, keyboard_type=ft.KeyboardType.NUMBER, hint_text="للإنتاج والجرد")
    alert_f = ft.TextField(label="تنبيه قبل الانتهاء (يوم)", width=190, value="30", keyboard_type=ft.KeyboardType.NUMBER)
    batch_note = ft.Text("", size=11.5, color=theme.TEXT_MUTED)

    def on_cost_change(e=None):
        # FIFO/LIFO في التكلفة محتاجة تشغيلات بنفس الترتيب: لو طريقة الإخراج مش نفسها (أو FEFO) بنضبطها
        if cost_dd.value in ("fifo", "lifo") and issue_dd.value not in (cost_dd.value, "fefo"):
            issue_dd.value = cost_dd.value
        cost_note.value = {"auto": "سعر التكلفة بيفضل زي ما هو مسجّل في الصنف (بتعدّله بنفسك).",
                           "avg": "سعر التكلفة بيتحدّث تلقائي مع كل استلام (شراء / سند استلام / إنتاج) = (الرصيد × التكلفة + الوارد × تكلفته) / (الرصيد + الوارد).",
                           "fifo": "تكلفة البضاعة المباعة من تكلفة أقدم تشغيلة وارد أولًا. بيتفعّل تتبّع التشغيلات.",
                           "lifo": "تكلفة البضاعة المباعة من تكلفة أحدث تشغيلة وارد أخيرًا. بيتفعّل تتبّع التشغيلات."}.get(cost_dd.value, "")
        on_issue_change()

    def on_issue_change(e=None):
        fefo = issue_dd.value == "fefo"
        if fefo:
            expiry_sw.value = True
        expiry_sw.disabled = fefo
        tracked = issue_dd.value != "none" or expiry_sw.value
        shelf_f.disabled = alert_f.disabled = not expiry_sw.value
        batch_note.value = ("بيتسجّل لكل استلام رقم تشغيلة وتاريخ صلاحية، والإخراج بيتوزّع تلقائي على التشغيلات: " + {"fifo": "الأقدم دخولًا أولًا", "lifo": "الأحدث دخولًا أولًا", "fefo": "الأقرب انتهاءً أولًا"}.get(issue_dd.value, "الأقرب انتهاءً أولًا")
                            + ". المنتهي الصلاحية مش بيتصرف في البيع والتصنيع والتحويل (بيتصرف في التلف والجرد)." if tracked else "من غير تتبّع تشغيلات: الصنف بيتعامل برصيد واحد (الوضع العادي).")
        try:
            page.update()
        except Exception:
            pass
    issue_dd.on_change = on_issue_change
    expiry_sw.on_change = on_issue_change
    cost_dd.on_change = on_cost_change
    unit_note = ft.Text("", size=11, color=theme.TEXT_MUTED, visible=False)
    editing = {"id": None}
    accounts = services.list_accounts()
    sales_acc = ft.Dropdown(label="حساب المبيعات", width=260, options=[ft.dropdown.Option(key=str(a.id), text=f"{a.code} - {a.name}") for a in accounts if a.account_type=="income"])
    inv_acc = ft.Dropdown(label="حساب المخزون", width=260, options=[ft.dropdown.Option(key=str(a.id), text=f"{a.code} - {a.name}") for a in accounts if a.account_type=="asset"])
    cogs_acc = ft.Dropdown(label="حساب تكلفة المبيعات", width=260, options=[ft.dropdown.Option(key=str(a.id), text=f"{a.code} - {a.name}") for a in accounts if a.account_type=="expense"])

    def refresh_units():
        rows = services.list_units()
        unit_field.options = [ft.dropdown.Option(key=u.name, text=u.name) for u in rows]
        if unit_field.value not in {u.name for u in rows}: unit_field.value = "قطعة" if any(u.name=="قطعة" for u in rows) else (rows[0].name if rows else None)
        page.update()
    def refresh_categories(selected=None):
        nonlocal categories_cache
        categories_cache={c.id:c.name for c in services.list_categories()}
        category_dropdown.options=[ft.dropdown.Option(str(k),v) for k,v in categories_cache.items()]
        category_dropdown.value=str(selected) if selected else None
        page.update()
    def reset_form():
        sku_field.value=name_field.value=""; unit_field.value="قطعة"; cost_field.value=sale_field.value=reorder_field.value="0"; tax_field.value="15"; category_dropdown.value=None
        sales_acc.value=inv_acc.value=cogs_acc.value=None; form_error.visible=False
        editing["id"]=None; sold_sw.value=purchased_sw.value=True; unit_field.disabled=False; unit_note.visible=False
        issue_dd.value="none"; cost_dd.value="auto"; expiry_sw.value=False; shelf_f.value=""; alert_f.value="30"; on_cost_change()
        create_dialog.title.value="إضافة صنف جديد"
    def close_dialog(e=None): create_dialog.open=False; page.update()

    def save_product(e):
        try:
            if not sku_field.value.strip() or not name_field.value.strip(): raise ValueError("الكود واسم الصنف مطلوبان")
            if editing["id"]:
                services.update_product_details(editing["id"], sku_field.value, name_field.value, category_id=int(category_dropdown.value) if category_dropdown.value else None,
                    unit=unit_field.value, cost_price=float(cost_field.value or 0), sale_price=float(sale_field.value or 0), reorder_point=float(reorder_field.value or 0),
                    tax_rate=float(tax_field.value or 0), sales_account_id=int(sales_acc.value) if sales_acc.value else None,
                    inventory_account_id=int(inv_acc.value) if inv_acc.value else None, cogs_account_id=int(cogs_acc.value) if cogs_acc.value else None,
                    can_be_sold=sold_sw.value, can_be_purchased=purchased_sw.value,
                    issue_method=issue_dd.value, cost_method=cost_dd.value, track_expiry=expiry_sw.value, shelf_life_days=int(shelf_f.value) if (shelf_f.value or "").strip() else None,
                    expiry_alert_days=int(alert_f.value) if (alert_f.value or "").strip() else 30)
                close_dialog(); refresh_table()
                page.overlay.append(ft.SnackBar(ft.Text("تم تعديل الصنف"), open=True)); page.update()
                return
            pid=services.create_product(sku_field.value.strip(),name_field.value.strip(),category_id=int(category_dropdown.value) if category_dropdown.value else None,unit=unit_field.value or "قطعة",cost_price=float(cost_field.value or 0),sale_price=float(sale_field.value or 0),reorder_point=float(reorder_field.value or 0),tax_rate=float(tax_field.value or 15),sales_account_id=int(sales_acc.value) if sales_acc.value else None,inventory_account_id=int(inv_acc.value) if inv_acc.value else None,cogs_account_id=int(cogs_acc.value) if cogs_acc.value else None,can_be_sold=sold_sw.value,can_be_purchased=purchased_sw.value,
                issue_method=issue_dd.value, cost_method=cost_dd.value, track_expiry=expiry_sw.value, shelf_life_days=int(shelf_f.value) if (shelf_f.value or "").strip() else None, expiry_alert_days=int(alert_f.value) if (alert_f.value or "").strip() else 30)
            close_dialog(); refresh_table(); open_units_dialog(pid)
        except Exception as ex: form_error.value=str(ex); form_error.visible=True; page.update()

    create_dialog=ft.AlertDialog(modal=True,title=ft.Text("إضافة صنف جديد"),content=ft.Container(width=850,content=ft.Column([
        ft.Row([sku_field,name_field],wrap=True),ft.Row([category_dropdown,unit_field],wrap=True),ft.Row([cost_field,sale_field,reorder_field,tax_field],wrap=True),
        unit_note,ft.Row([sold_sw,purchased_sw],wrap=True),ft.Text("طريقة التكلفة",size=14,weight=ft.FontWeight.BOLD),ft.Row([cost_dd],wrap=True),cost_note,ft.Text("الصلاحية وطريقة الإخراج",size=14,weight=ft.FontWeight.BOLD),
        ft.Row([issue_dd,expiry_sw,shelf_f,alert_f],wrap=True,vertical_alignment=ft.CrossAxisAlignment.CENTER),batch_note,ft.Text("الحسابات المرتبطة بالصنف",size=14,weight=ft.FontWeight.BOLD),ft.Row([sales_acc,inv_acc,cogs_acc],wrap=True),form_error]),padding=10),actions=[ft.TextButton("إلغاء",on_click=close_dialog),ft.FilledButton("حفظ",on_click=save_product,bgcolor=theme.PRIMARY)])
    page.overlay.append(create_dialog)

    # ---------- Multi unit dialog ----------
    unit_product_id = {"id": None}
    unit_rows = ft.Column(spacing=8)
    unit_options_cache=[]
    def add_unit_row(unit_id=None, factor="1", sale="", cost="", barcode="", is_default=False):
        dd=ft.Dropdown(label="الوحدة",width=170,options=unit_options_cache,value=str(unit_id) if unit_id else None)
        fac=ft.TextField(label="معامل التحويل",value=str(factor),width=120,keyboard_type=ft.KeyboardType.NUMBER)
        sp=ft.TextField(label="سعر البيع",value=str(sale) if sale not in (None,"") else "",width=120,keyboard_type=ft.KeyboardType.NUMBER)
        cp=ft.TextField(label="سعر التكلفة",value=str(cost) if cost not in (None,"") else "",width=120,keyboard_type=ft.KeyboardType.NUMBER,visible=SHOW_COST)
        bc=ft.TextField(label="باركود (اختياري)",value=barcode or "",width=150)
        chk=ft.Checkbox(label="أساسية",value=is_default)
        def remove(e): unit_rows.controls.remove(row); page.update()
        row=ft.Row([dd,fac,sp,cp,bc,chk,ft.IconButton(ft.Icons.DELETE_OUTLINE,on_click=remove,icon_color=theme.DANGER)],wrap=True)
        unit_rows.controls.append(row)
        page.update()
    def save_units(e):
        try:
            lines=[]
            for row in unit_rows.controls:
                dd,fac,sp,cp,bc,chk,_=row.controls
                if not dd.value: raise ValueError("اختر وحدة القياس لكل سطر")
                lines.append({"unit_id":int(dd.value),"factor_to_base":float(fac.value or 0),"sale_price":sp.value,"cost_price":cp.value,"barcode":bc.value,"is_default":bool(chk.value)})
            services.save_product_units(unit_product_id["id"],lines)
            units_dialog.open=False; refresh_table(); page.update()
        except Exception as ex: units_error.value=str(ex); units_error.visible=True; page.update()
    units_error=ft.Text("",color=theme.DANGER,visible=False)
    image_preview = ft.Container(
        width=140, height=140, border_radius=10, bgcolor=theme.PRIMARY_LIGHT,
        alignment=ft.Alignment(0, 0),
        content=ft.Icon(ft.Icons.IMAGE_OUTLINED, size=40, color=theme.TEXT_MUTED),
    )
    image_status = ft.Text("", color=theme.DANGER, visible=False)

    def refresh_image_preview():
        pid = unit_product_id["id"]
        if not pid:
            return
        p = services.get_product(pid)
        if p and p.image_path:
            import os
            if os.path.exists(p.image_path):
                image_preview.content = ft.Image(src=p.image_path, width=140, height=140, fit=ft.BoxFit.COVER, border_radius=10)
            else:
                image_preview.content = ft.Icon(ft.Icons.IMAGE_OUTLINED, size=40, color=theme.TEXT_MUTED)
        else:
            image_preview.content = ft.Icon(ft.Icons.IMAGE_OUTLINED, size=40, color=theme.TEXT_MUTED)
        page.update()

    async def browse_product_image(e):
        try:
            path = await theme.pick_file(page, "اختر صورة الصنف", ['png', 'jpg', 'jpeg', 'webp', 'gif'], max_mb=10)
            if not path:
                return
            if unit_product_id["id"]:
                services.set_product_image(unit_product_id["id"], path)
                image_status.visible = False
                refresh_image_preview()
                refresh_table()
        except Exception as ex:
            image_status.value = str(ex); image_status.visible = True; page.update()

    def remove_product_image(e):
        try:
            if unit_product_id["id"]:
                services.remove_product_image(unit_product_id["id"])
                image_status.visible = False
                refresh_image_preview()
                refresh_table()
        except Exception as ex:
            image_status.value = str(ex); image_status.visible = True; page.update()

    image_section = ft.Row(
        [
            image_preview,
            ft.Column([
                ft.Text("صورة الصنف", weight=ft.FontWeight.BOLD),
                ft.Row([
                    ft.OutlinedButton("تصفح واختيار صورة...", icon=ft.Icons.FOLDER_OPEN_OUTLINED, on_click=browse_product_image),
                    ft.OutlinedButton("إزالة الصورة", icon=ft.Icons.DELETE_OUTLINE, on_click=remove_product_image),
                ], wrap=True),
                image_status,
            ], spacing=8),
        ],
        spacing=16,
    )
    units_dialog=ft.AlertDialog(
        modal=True, title=ft.Text("تفاصيل الصنف - الوحدات والصورة"),
        content=ft.Container(width=950, content=ft.Column([
            image_section, ft.Divider(),
            ft.Text("مثال: حبة = 1، كرتونة 18 = 18، كرتونة 24 = 24. معامل التحويل هو عدد الوحدات الأساسية داخل الوحدة."),
            unit_rows, units_error], scroll=ft.ScrollMode.AUTO), padding=10),
        actions=[
            ft.TextButton("إغلاق", on_click=lambda e: (setattr(units_dialog,'open',False),page.update())),
            ft.OutlinedButton("إضافة وحدة", on_click=lambda e:add_unit_row()),
            ft.FilledButton("حفظ الوحدات", on_click=save_units, bgcolor=theme.PRIMARY)
        ])
    page.overlay.append(units_dialog)
    def open_units_dialog(pid):
        unit_product_id["id"]=pid; unit_rows.controls.clear(); units_error.visible=False
        unit_options_cache[:]=[ft.dropdown.Option(str(u.id),u.name) for u in services.list_units()]
        existing=services.list_product_units(pid)
        for x in existing: add_unit_row(x.unit_id,x.factor_to_base,x.sale_price,x.cost_price,x.barcode,x.is_default)
        if not existing: add_unit_row()
        refresh_image_preview()
        units_dialog.open=True; page.update()

    def refresh_table(e=None):
        products_table_sortable.set_data(services.list_products(search=search_field.value or None))
    search_field.on_change=refresh_table
    def open_add_dialog(e): refresh_units();refresh_categories();reset_form();create_dialog.open=True;page.update()
    def open_edit_dialog(pid):
        p=services.get_product(pid)
        if not p: return
        refresh_units(); reset_form(); refresh_categories(p.category_id)
        editing["id"]=p.id; create_dialog.title.value=f"تعديل الصنف: {p.name}"
        sku_field.value=p.sku; name_field.value=p.name
        unit_field.value=p.unit
        cost_field.value=f"{p.cost_price:g}"; sale_field.value=f"{p.sale_price:g}"; reorder_field.value=f"{p.reorder_point:g}"; tax_field.value=f"{p.tax_rate:g}"
        sold_sw.value=bool(p.can_be_sold); purchased_sw.value=bool(p.can_be_purchased)
        issue_dd.value=p.issue_method or "none"; cost_dd.value=p.cost_method or "auto"; expiry_sw.value=bool(p.track_expiry); shelf_f.value=str(p.shelf_life_days) if p.shelf_life_days else ""; alert_f.value=str(p.expiry_alert_days if p.expiry_alert_days is not None else 30); on_cost_change()
        keys={o.key for o in sales_acc.options}; sales_acc.value=str(p.sales_account_id) if p.sales_account_id and str(p.sales_account_id) in keys else None
        keys={o.key for o in inv_acc.options}; inv_acc.value=str(p.inventory_account_id) if p.inventory_account_id and str(p.inventory_account_id) in keys else None
        keys={o.key for o in cogs_acc.options}; cogs_acc.value=str(p.cogs_account_id) if p.cogs_account_id and str(p.cogs_account_id) in keys else None
        if services.product_has_movements(p.id):
            unit_field.disabled=True; unit_note.value="الوحدة الأساسية مقفولة لإن الصنف عليه حركة. ضيف وحدات جديدة من زرار 'وحدات الصنف'. تعديل السعر بيتطبّق على الوحدة الأساسية بس."; unit_note.visible=True
        else:
            unit_note.value="تعديل السعر بيتطبّق على الوحدة الأساسية بس (أسعار الوحدات التانية من 'وحدات الصنف')."; unit_note.visible=True
        create_dialog.open=True; page.update()
    refresh_units();refresh_categories();refresh_table()
    return ft.Column([ft.Row([theme.page_title("الأصناف","إدارة دليل الأصناف ووحدات القياس والأسعار"),ft.Container(expand=True),search_field,ft.FilledButton("إضافة صنف",icon=ft.Icons.ADD,bgcolor=theme.PRIMARY,on_click=open_add_dialog)]),ft.Container(height=12),theme.card(theme.h_scroll(products_table, vscroll=True),expand=True)],expand=True)
