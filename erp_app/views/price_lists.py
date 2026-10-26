import flet as ft
from .. import services, theme


def build_price_lists(page: ft.Page):
    """قوائم الأسعار: كل قائمة بتتربط بعميل (أو أكتر) من شاشة العملاء،
    وبتحدد سعر بيع خاص لكل صنف. أي صنف مش موجود في القائمة بيترجع لسعر
    البيع الافتراضي المسجّل عليه."""
    tabs = theme.SimpleTabs(page)

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    name_f = ft.TextField(label='اسم قائمة الأسعار', width=260)
    notes_f = ft.TextField(label='ملاحظات (اختياري)', width=320)
    err = ft.Text('', color=theme.DANGER, visible=False)
    editing = {'id': None}

    def refresh_all():
        tabs.set_tabs([('القوائم', show_lists()), ('أسعار الأصناف', show_items())], selected_index=tabs.selected_index)
        page.update()

    # ============================================================ القوائم
    def show_lists():
        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['اسم القائمة', 'ملاحظات', 'عدد الأصناف المسعّرة', 'عدد العملاء', 'الحالة', '']], rows=[])

        def clear_form():
            editing['id'] = None; name_f.value = ''; notes_f.value = ''; err.visible = False

        def submit(e):
            try:
                if editing['id']:
                    services.update_price_list(editing['id'], name_f.value, notes_f.value)
                else:
                    services.create_price_list(name_f.value, notes_f.value)
                clear_form(); snack('تم الحفظ'); refresh_all()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        def open_edit(pl):
            editing['id'] = pl.id; name_f.value = pl.name; notes_f.value = pl.notes or ''; err.visible = False
            page.update()

        def toggle_active(pl):
            try:
                services.update_price_list(pl.id, pl.name, pl.notes, is_active=not pl.is_active)
                refresh_all()
            except Exception as ex:
                snack(str(ex))

        def delete(pl):
            theme.confirm(page, 'حذف قائمة أسعار', f"هتحذف قائمة الأسعار {pl.name} بكل أسعارها. متأكد؟", lambda: _do_delete(pl), yes_label='حذف')

        def _do_delete(pl):
            try:
                services.delete_price_list(pl.id); refresh_all()
            except Exception as ex:
                snack(str(ex))

        def open_view(pl):
            view_pending = {}  # product_id -> آخر قيمة اتكتبت (مش محفوظة لسه)
            view_table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['الصنف', 'السعر الافتراضي', 'سعر البيع في القائمة', '']], rows=[])
            add_search = theme.SearchableDropdown(label='إضافة صنف للقائمة', width=320,
                                                   options=[(str(p.id), f'{p.sku} - {p.name}') for p in services.list_products()])
            vierr = ft.Text('', color=theme.DANGER, visible=False)
            visuccess = ft.Text('', color=theme.SUCCESS, visible=False)
            all_products_by_id = {p.id: p for p in services.list_products()}

            def on_view_price_type(e, pid):
                view_pending[pid] = e.control.value

            def remove_row(pid):
                try:
                    item = next((it for it in services.list_price_list_items(pl.id) if it.product_id == pid), None)
                    if item:
                        services.remove_price_list_item(item.id)
                    view_pending.pop(pid, None)
                    rebuild_view()
                except Exception as ex:
                    vierr.value = str(ex); vierr.visible = True; page.update()

            def rebuild_view():
                vierr.visible = False; visuccess.visible = False
                existing_items = services.list_price_list_items(pl.id)
                rows = []
                for it in existing_items:
                    p = it.product
                    current = view_pending[it.product_id] if it.product_id in view_pending else f'{it.price:g}'
                    f = ft.TextField(value=current, width=140, keyboard_type=ft.KeyboardType.NUMBER)
                    f.on_change = lambda e, pid=it.product_id: on_view_price_type(e, pid)
                    rows.append(ft.DataRow(cells=[
                        ft.DataCell(ft.Text(p.name if p else '-')),
                        ft.DataCell(ft.Text(f'{p.sale_price:,.2f}' if p else '-', color=theme.TEXT_MUTED)),
                        ft.DataCell(f),
                        ft.DataCell(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف من القائمة',
                                                  on_click=lambda e, pid=it.product_id: remove_row(pid))),
                    ]))
                for pid, val in view_pending.items():
                    if pid not in {it.product_id for it in existing_items} and (val or '').strip():
                        p = all_products_by_id.get(pid)
                        if not p:
                            continue
                        f = ft.TextField(value=val, width=140, keyboard_type=ft.KeyboardType.NUMBER)
                        f.on_change = lambda e, pid=pid: on_view_price_type(e, pid)
                        rows.append(ft.DataRow(cells=[
                            ft.DataCell(ft.Text(p.name)),
                            ft.DataCell(ft.Text(f'{p.sale_price:,.2f}', color=theme.TEXT_MUTED)),
                            ft.DataCell(f),
                            ft.DataCell(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='إلغاء',
                                                      on_click=lambda e, pid=pid: (view_pending.pop(pid, None), rebuild_view()))),
                        ]))
                view_table.rows = rows if rows else [ft.DataRow(cells=[ft.DataCell(ft.Text('مفيش أصناف مسعّرة لسه - ضيف من الحقل فوق', color=theme.TEXT_MUTED)), ft.DataCell(ft.Text('')), ft.DataCell(ft.Text('')), ft.DataCell(ft.Text(''))])]
                page.update()

            def add_product_row(e):
                if not add_search.value:
                    return
                pid = int(add_search.value)
                default_price = all_products_by_id[pid].sale_price if pid in all_products_by_id else 0
                if pid not in view_pending:
                    view_pending[pid] = f'{default_price:g}'
                add_search.value = None
                rebuild_view()

            add_search.on_change = add_product_row

            def save_view(e):
                try:
                    items = [{'product_id': pid, 'price': v} for pid, v in view_pending.items() if (v or '').strip()]
                    saved = services.set_price_list_items_bulk(pl.id, items)
                    view_pending.clear()
                    visuccess.value = f'تم حفظ {saved} سعر بنجاح'; visuccess.visible = True
                    rebuild_view()
                except Exception as ex:
                    vierr.value = str(ex); vierr.visible = True; page.update()

            rebuild_view()

            view_dlg = ft.AlertDialog(
                modal=True, title=ft.Text(f'أسعار قائمة: {pl.name}'),
                content=ft.Container(width=620, content=ft.Column([
                    add_search.control, vierr, visuccess, ft.Divider(), theme.h_scroll(view_table),
                ], spacing=10, tight=True, scroll=ft.ScrollMode.AUTO, height=420)),
                actions=[
                    ft.TextButton('إغلاق', on_click=lambda e: (setattr(view_dlg, 'open', False), page.update(), refresh_all())),
                    ft.FilledButton('حفظ التعديلات', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save_view),
                ],
            )
            page.overlay.append(view_dlg); view_dlg.open = True; page.update()

        customers_all = services.list_customers()
        rows = []
        for pl in services.list_price_lists():
            items_count = len(services.list_price_list_items(pl.id))
            customers_count = sum(1 for c in customers_all if c.price_list_id == pl.id)
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(pl.name, weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(pl.notes or '-', size=12)),
                ft.DataCell(ft.Text(str(items_count))),
                ft.DataCell(ft.Text(str(customers_count))),
                ft.DataCell(ft.Text('نشطة' if pl.is_active else 'موقوفة', color=theme.SUCCESS if pl.is_active else theme.TEXT_MUTED)),
                ft.DataCell(ft.Row(spacing=0, controls=[
                    ft.IconButton(icon=ft.Icons.VISIBILITY_OUTLINED, tooltip='عرض أصناف القائمة وأسعارها', on_click=lambda e, x=pl: open_view(x)),
                    ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل', on_click=lambda e, x=pl: open_edit(x)),
                    ft.IconButton(icon=ft.Icons.TOGGLE_ON_OUTLINED if pl.is_active else ft.Icons.TOGGLE_OFF_OUTLINED,
                                 tooltip='إيقاف' if pl.is_active else 'تفعيل', on_click=lambda e, x=pl: toggle_active(x)),
                    ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف', on_click=lambda e, x=pl: delete(x)),
                ])),
            ]))
        table.rows = rows

        return ft.Column([
            theme.card(ft.Column([
                ft.Text('قائمة أسعار جديدة / تعديل', size=16, weight=ft.FontWeight.BOLD),
                ft.Row([name_f, notes_f], wrap=True, spacing=12), err,
                ft.Row([ft.FilledButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=submit),
                        ft.TextButton('إلغاء التعديل', on_click=lambda e: (clear_form(), page.update()))], spacing=10),
            ], spacing=10)),
            ft.Container(height=16),
            theme.card(ft.Column([ft.Text('كل قوائم الأسعار', size=16, weight=ft.FontWeight.BOLD), theme.h_scroll(table)])),
        ], expand=True, scroll=ft.ScrollMode.AUTO)

    # ============================================================ أسعار الأصناف (تعديل دفعة واحدة)
    def show_items():
        lists = services.list_price_lists()
        if not lists:
            quick_name = ft.TextField(label='اسم قائمة الأسعار', width=260, autofocus=True)
            quick_err = ft.Text('', color=theme.DANGER, visible=False)

            def quick_create(e):
                try:
                    services.create_price_list(quick_name.value)
                    refresh_all()
                except Exception as ex:
                    quick_err.value = str(ex); quick_err.visible = True; page.update()

            return theme.card(ft.Column([
                ft.Text('مفيش قوائم أسعار لسه - أنشئ أول قائمة عشان تقدر تحدد أسعار الأصناف', size=15, weight=ft.FontWeight.BOLD),
                ft.Row([quick_name, ft.FilledButton('إنشاء القائمة', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=quick_create)], wrap=True, spacing=12),
                quick_err,
            ], spacing=10))

        pl_dd = ft.Dropdown(label='قائمة الأسعار', width=260, options=[ft.dropdown.Option(str(p.id), p.name) for p in lists], value=str(lists[0].id))
        search_f = ft.TextField(label='بحث بالاسم أو الكود', width=280, prefix_icon=ft.Icons.SEARCH)
        ierr = ft.Text('', color=theme.DANGER, visible=False)
        isuccess = ft.Text('', color=theme.SUCCESS, visible=False)
        pending_values = {}  # product_id -> آخر قيمة اتكتبت (بتتحافظ عليها حتى لو فلترت بالبحث قبل ما تحفظ)
        item_table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['الكود', 'الصنف', 'السعر الافتراضي', 'السعر الخاص بالقائمة']], rows=[])

        def on_price_type(e, pid):
            pending_values[pid] = e.control.value

        def rebuild_table(reset_pending=False):
            ierr.visible = False; isuccess.visible = False
            if reset_pending:
                pending_values.clear()
            existing = {it.product_id: it.price for it in services.list_price_list_items(int(pl_dd.value))}
            needle = (search_f.value or '').strip().lower()
            products = [p for p in services.list_products() if not needle or needle in p.name.lower() or needle in p.sku.lower()]
            rows = []
            for p in products:
                current = pending_values[p.id] if p.id in pending_values else (f'{existing[p.id]:g}' if p.id in existing else '')
                f = ft.TextField(value=current, width=140, keyboard_type=ft.KeyboardType.NUMBER, hint_text='بدون سعر خاص',
                                 border_color=theme.PRIMARY if p.id in existing else None)
                f.on_change = lambda e, pid=p.id: on_price_type(e, pid)
                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(p.sku, size=12)),
                    ft.DataCell(ft.Text(p.name)),
                    ft.DataCell(ft.Text(f'{p.sale_price:,.2f}', color=theme.TEXT_MUTED)),
                    ft.DataCell(f),
                ]))
            item_table.rows = rows
            page.update()

        def on_list_change(e):
            rebuild_table(reset_pending=True)  # قائمة تانية = قيم افتراضية مختلفة، منطقي نبدأ من جديد

        def on_search_change(e):
            rebuild_table(reset_pending=False)  # البحث بيفلتر بس - القيم اللي اتكتبت بتفضل محفوظة

        def save_all(e):
            try:
                items = [{'product_id': pid, 'price': v} for pid, v in pending_values.items() if (v or '').strip()]
                saved = services.set_price_list_items_bulk(int(pl_dd.value), items)
                ierr.visible = False
                isuccess.value = f'تم حفظ {saved} سعر بنجاح'; isuccess.visible = True
                rebuild_table(reset_pending=True)
                snack(f'تم حفظ {saved} سعر')
            except Exception as ex:
                isuccess.visible = False
                ierr.value = str(ex); ierr.visible = True; page.update()

        pl_dd.on_change = on_list_change
        search_f.on_change = on_search_change
        rebuild_table(reset_pending=True)

        return ft.Column([
            theme.card(ft.Column([
                ft.Text('تعديل أسعار القائمة', size=16, weight=ft.FontWeight.BOLD),
                ft.Text('ملّى سعر البيع الخاص للأصناف اللي عايزها بس، وسيب الباقي فاضي، وبعدين دوس "حفظ كل الأسعار" مرة واحدة. '
                        'الصنف اللي تسيبه فاضي بياخد السعر الافتراضي تلقائيًا.', size=12, color=theme.TEXT_MUTED),
                ft.Row([pl_dd, search_f, ft.FilledButton('حفظ كل الأسعار', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save_all)], wrap=True, spacing=12),
                ierr, isuccess,
            ], spacing=10)),
            ft.Container(height=16),
            theme.card(ft.Column([ft.Text('كل الأصناف', size=16, weight=ft.FontWeight.BOLD), theme.h_scroll(item_table)])),
        ], expand=True, scroll=ft.ScrollMode.AUTO)

    theme.call_without_page_update(page, refresh_all)
    return ft.Column([theme.page_title('قوائم الأسعار', 'سعر بيع خاص لكل عميل حسب قائمته - أي صنف غير مسعّر بيرجع للسعر الافتراضي'),
                      ft.Container(height=10), tabs.control], expand=True)
