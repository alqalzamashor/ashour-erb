import base64
import datetime
import os
import flet as ft
from .. import services, theme, thermal
from ..report_export import export_excel, export_pdf
from ._discount import discount_box
from .pos_sessions import open_session_dialog, close_session_dialog, session_report_dialog

STATE_COLORS = {'free': ('#E6F6EE', '#1B8E5A'), 'occupied': ('#FDECEA', '#C0392B')}


def build_restaurant(page: ft.Page):
    """نظام المطاعم: طاولات مقسّمة بأقسام، طلب مفتوح لكل طاولة، إرسال
    للمطبخ (تذكرة PDF)، وتحويل الطلب لفاتورة POS عادية عند الدفع."""
    tabs = theme.SimpleTabs(page)
    sess = {'terminal_id': None}

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def require_terminal():
        """ماكينة بجلسة مفتوحة لفتح طلب جديد، وإلا رسالة واضحة."""
        tid = sess['terminal_id']
        if not tid:
            snack('مفيش ماكينة - أضف ماكينة من "ماكينات نقاط البيع" وافتح جلسة'); return None
        if not services.get_open_pos_session(tid):
            snack('افتح جلسة على الماكينة الأول (من شريط الجلسة فوق)'); return None
        return tid

    # ============================================================ الصالة
    def show_floor():
        grid = ft.GridView(expand=True, max_extent=190, child_aspect_ratio=1.15, spacing=10, run_spacing=10)
        sections = services.list_restaurant_sections(active_only=True)
        sec_dd = ft.Dropdown(label='القسم', width=200, options=[ft.dropdown.Option('', 'كل الأقسام')] + [ft.dropdown.Option(str(s.id), s.name) for s in sections], value='')

        no_table_col = ft.Column(spacing=8)

        def fill_no_table():
            orders = services.list_open_orders_without_table()
            if not orders:
                no_table_col.controls = []
                return
            cards = []
            for o in orders:
                elapsed = int((datetime.datetime.now() - o['opened_at']).total_seconds() // 60)
                type_label = services.RESTAURANT_ORDER_TYPES.get(o['order_type'], o['order_type'])
                cards.append(ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.TAKEOUT_DINING_OUTLINED if o['order_type'] == 'takeaway' else ft.Icons.DELIVERY_DINING_OUTLINED, color=theme.PRIMARY),
                        ft.Column([
                            ft.Text(f"{type_label} - {o['number']}" + (f" - {o['customer_name']}" if o['customer_name'] else '') + (f" - {o['customer_phone']}" if o['customer_phone'] else ''), weight=ft.FontWeight.BOLD, size=13),
                            ft.Text(f"{o['items_count']} صنف  |  {o['total']:,.2f}  |  منذ {elapsed} دقيقة" + ('  •  مطبخ بانتظار' if o['pending_items'] else ''), size=11, color=theme.WARNING if o['pending_items'] else theme.TEXT_MUTED),
                        ], spacing=2, expand=True),
                    ], spacing=10),
                    bgcolor=STATE_COLORS['occupied'][0], border_radius=10, padding=10, ink=True,
                    on_click=lambda e, oid=o['id']: open_order_screen(oid),
                ))
            no_table_col.controls = [ft.Text('طلبات تيك أواي ودليفري مفتوحة', size=14, weight=ft.FontWeight.BOLD)] + cards

        def fill(e=None):
            fill_no_table()
            tables = services.list_tables_status()
            if sec_dd.value:
                sec_name = next((s.name for s in sections if str(s.id) == sec_dd.value), None)
                tables = [t for t in tables if t['section'] == sec_name]
            tiles = []
            for t in tables:
                order = t['order']
                free = order is None
                bg, fg = STATE_COLORS['free' if free else 'occupied']
                lines = [ft.Text(f"طاولة {t['number']}", size=16, weight=ft.FontWeight.BOLD, color=fg),
                         ft.Text(t['name'] or (t['section'] or ''), size=11, color=theme.TEXT_MUTED)]
                if free:
                    lines.append(ft.Icon(ft.Icons.EVENT_SEAT_OUTLINED, color=fg, size=28))
                    lines.append(ft.Text(f"{t['seats']} مقعد", size=11, color=theme.TEXT_MUTED))
                else:
                    elapsed = int((datetime.datetime.now() - order['opened_at']).total_seconds() // 60)
                    lines.append(ft.Text(f"{order['items_count']} صنف  |  {order['total']:,.2f}", size=13, weight=ft.FontWeight.BOLD, color=fg))
                    lines.append(ft.Text(f"منذ {elapsed} دقيقة" + ('  •  مطبخ بانتظار' if order['pending_items'] else ''), size=11, color=theme.WARNING if order['pending_items'] else theme.TEXT_MUTED))
                tiles.append(ft.Container(
                    content=ft.Column(lines, spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER),
                    bgcolor=bg, border=ft.border.Border(*(ft.border.BorderSide(2, fg) for _ in range(4))), border_radius=14, padding=10,
                    ink=True, on_click=lambda e, tid=t['id'], free=free: (open_order_for(tid) if not free else open_new_order(tid)),
                ))
            grid.controls = tiles
            page.update()

        def open_new_order(table_id):
            guests_f = ft.TextField(label='عدد الأشخاص', value='1', width=160, keyboard_type=ft.KeyboardType.NUMBER, autofocus=True)
            err = ft.Text('', color=theme.DANGER, visible=False)

            def start(e):
                try:
                    oid = services.open_restaurant_order(table_id, guests=guests_f.value or 1, terminal_id=sess['terminal_id'])
                    dlg.open = False; page.update()
                    open_order_screen(oid)
                except Exception as ex:
                    err.value = str(ex); err.visible = True; page.update()

            dlg = ft.AlertDialog(modal=True, title=ft.Text('فتح طلب جديد'),
                                 content=ft.Column([guests_f, err], tight=True, spacing=10),
                                 actions=[ft.TextButton('إلغاء', on_click=lambda e: (setattr(dlg, 'open', False), page.update())),
                                          ft.FilledButton('فتح الطلب', bgcolor=theme.PRIMARY, on_click=start)])
            page.overlay.append(dlg); dlg.open = True; page.update()

        def open_order_for(table_id):
            order = services.get_open_order_for_table(table_id)
            if order:
                open_order_screen(order['id'])

        def open_no_table_order(order_type):
            if not require_terminal():
                return
            is_delivery = order_type == 'delivery'
            cust_name_f = ft.TextField(label='اسم العميل' + ('' if is_delivery else ' (اختياري)'), width=300, autofocus=True)
            phone_f = ft.TextField(label='رقم الهاتف' + (' *' if is_delivery else ' (اختياري)'), width=300, keyboard_type=ft.KeyboardType.PHONE)
            addr_f = ft.TextField(label='عنوان التوصيل *', width=300, multiline=True, min_lines=2, max_lines=3, visible=is_delivery)
            err = ft.Text('', color=theme.DANGER, visible=False)

            def start(ev):
                try:
                    oid = services.open_restaurant_order(order_type=order_type, customer_name=cust_name_f.value or '', customer_phone=phone_f.value or '', delivery_address=addr_f.value or '', terminal_id=sess['terminal_id'])
                    dlg.open = False; page.update()
                    open_order_screen(oid)
                except Exception as ex:
                    err.value = str(ex); err.visible = True; page.update()

            dlg = ft.AlertDialog(modal=True, title=ft.Text(services.RESTAURANT_ORDER_TYPES[order_type]),
                                 content=ft.Column([cust_name_f, phone_f, addr_f, err], tight=True, spacing=10),
                                 actions=[ft.TextButton('إلغاء', on_click=lambda ev: (setattr(dlg, 'open', False), page.update())),
                                          theme.guard_submit(ft.FilledButton('فتح الطلب', bgcolor=theme.PRIMARY, on_click=start))])
            page.overlay.append(dlg); dlg.open = True; page.update()

        def open_local_order(e=None):
            """طلب محلي: الأقسام أولًا (بعدد الفاضي/المشغول)، وبالضغط على قسم تظهر طاولاته المشغولة والمتاحة."""
            if not require_terminal():
                return
            body = ft.Column([], tight=True, spacing=12, scroll=ft.ScrollMode.AUTO, width=640, height=420)
            title = ft.Text('طلب محلي - اختر القسم', size=18, weight=ft.FontWeight.BOLD)
            back_btn = ft.IconButton(ft.Icons.ARROW_FORWARD, tooltip='رجوع للأقسام', visible=False)

            def border(color, w=2):
                return ft.border.Border(*(ft.border.BorderSide(w, color) for _ in range(4)))

            def close():
                dlg.open = False; page.update()

            def pick_table(t):
                close()
                if t['order'] is None:
                    open_new_order(t['id'])
                else:
                    open_order_screen(t['order']['id'])

            def show_sections():
                tables = services.list_tables_status()
                names = [sc.name for sc in services.list_restaurant_sections(active_only=True)]
                if any(not t['section'] for t in tables):
                    names.append('')
                tiles = []
                for nm in names:
                    ts = [t for t in tables if t['section'] == nm]
                    if not ts:
                        continue
                    busy = sum(1 for t in ts if t['order'] is not None); free = len(ts) - busy
                    tiles.append(ft.Container(width=190, padding=14, border_radius=14, bgcolor=theme.CARD_BG, border=border(theme.PRIMARY), ink=True, on_click=lambda ev, n=nm: show_tables(n),
                                              content=ft.Column([ft.Icon(ft.Icons.TABLE_RESTAURANT, color=theme.PRIMARY, size=30), ft.Text(nm or 'بدون قسم', size=16, weight=ft.FontWeight.BOLD),
                                                                 ft.Row([ft.Text(f'متاحة {free}', size=12, color=STATE_COLORS['free'][1], weight=ft.FontWeight.BOLD),
                                                                         ft.Text(f'مشغولة {busy}', size=12, color=STATE_COLORS['occupied'][1], weight=ft.FontWeight.BOLD)], spacing=10, alignment=ft.MainAxisAlignment.CENTER)],
                                                                horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6)))
                title.value = 'طلب محلي - اختر القسم'; back_btn.visible = False
                body.controls = [ft.Row(tiles, wrap=True, spacing=12, run_spacing=12)] if tiles else [ft.Text('مفيش طاولات - أضفها من تبويب "الأقسام والطاولات"', color=theme.TEXT_MUTED)]
                page.update()

            def show_tables(sec_name):
                ts = [t for t in services.list_tables_status() if t['section'] == sec_name]
                title.value = f"طلب محلي - {sec_name or 'بدون قسم'}"; back_btn.visible = True
                def tile(t):
                    free = t['order'] is None
                    bg, fg = STATE_COLORS['free' if free else 'occupied']
                    lines = [ft.Text(f"طاولة {t['number']}", size=15, weight=ft.FontWeight.BOLD, color=fg)]
                    if free:
                        lines += [ft.Icon(ft.Icons.EVENT_SEAT_OUTLINED, color=fg, size=24), ft.Text(f"متاحة - {t['seats']} مقعد", size=11, color=theme.TEXT_MUTED)]
                    else:
                        o = t['order']; el = int((datetime.datetime.now() - o['opened_at']).total_seconds() // 60)
                        lines += [ft.Text(f"{o['items_count']} صنف  |  {o['total']:,.2f}", size=12, weight=ft.FontWeight.BOLD, color=fg),
                                  ft.Text(f"مفتوحة منذ {el} دقيقة" + ('  •  مطبخ بانتظار' if o['pending_items'] else ''), size=10, color=theme.WARNING if o['pending_items'] else theme.TEXT_MUTED)]
                    return ft.Container(width=170, height=110, padding=8, border_radius=12, bgcolor=bg, border=border(fg), ink=True, on_click=lambda ev, tt=t: pick_table(tt),
                                        content=ft.Column(lines, spacing=3, horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER))
                free_n = sum(1 for t in ts if t['order'] is None)
                body.controls = [ft.Text(f'متاحة {free_n}  •  مشغولة {len(ts) - free_n}', size=12, color=theme.TEXT_MUTED),
                                 ft.Row([tile(t) for t in ts], wrap=True, spacing=10, run_spacing=10)]
                page.update()

            back_btn.on_click = lambda ev: show_sections()
            dlg = ft.AlertDialog(modal=True, title=ft.Row([back_btn, title], spacing=4), content=body,
                                 actions=[ft.TextButton('إغلاق', on_click=lambda ev: close())])
            show_sections()
            page.overlay.append(dlg); dlg.open = True; page.update()

        sec_dd.on_select = fill; sec_dd.on_change = fill
        fill()
        return ft.Column([
            ft.Row([sec_dd, ft.OutlinedButton('تحديث', icon=ft.Icons.REFRESH, on_click=fill),
                    ft.FilledButton('طلب محلي', icon=ft.Icons.RESTAURANT, bgcolor=theme.PRIMARY, on_click=open_local_order),
                    ft.FilledButton('طلب تيك أواي', icon=ft.Icons.TAKEOUT_DINING_OUTLINED, bgcolor='#F5A524', on_click=lambda e: open_no_table_order('takeaway')),
                    ft.FilledButton('طلب دليفري', icon=ft.Icons.DELIVERY_DINING_OUTLINED, bgcolor='#17A589', on_click=lambda e: open_no_table_order('delivery')),
                    ft.Row([ft.Container(width=16, height=16, bgcolor=STATE_COLORS['free'][0], border=ft.border.Border(*(ft.border.BorderSide(2, STATE_COLORS['free'][1]) for _ in range(4)))),
                            ft.Text('فاضية', size=12), ft.Container(width=16, height=16, bgcolor=STATE_COLORS['occupied'][0], border=ft.border.Border(*(ft.border.BorderSide(2, STATE_COLORS['occupied'][1]) for _ in range(4)))),
                            ft.Text('مشغولة', size=12)], spacing=6)], wrap=True),
            ft.Container(height=10),
            no_table_col,
            ft.Container(height=10),
            grid,
        ], expand=True)

    # ============================================================ شاشة الطلب
    pos_groups_cache = services.list_pos_groups()

    def open_order_screen(order_id):
        _o0 = services.get_restaurant_order(order_id)
        order0_has_table = bool(_o0 and _o0.get('table_id'))
        products_all = [p for p in services.list_products() if p.can_be_sold]
        products_by_id = {p.id: p for p in products_all}
        active_group = {'id': None}
        group_buttons_row = ft.Row(wrap=True, spacing=8)
        search_f = ft.TextField(label='بحث عن صنف (الاسم أو الكود)', width=280, prefix_icon=ft.Icons.SEARCH)
        products_grid = ft.GridView(expand=True, max_extent=150, child_aspect_ratio=(0.8 if theme._page_w() else 0.95), spacing=8, run_spacing=8)
        note_f = ft.TextField(label='ملاحظة للصنف التالي (اختياري - زي "من غير بصل")', width=320)
        customers_cache = services.list_customers()
        price_customer_dd = theme.SearchableDropdown(label='العميل (لتطبيق قائمة أسعاره - اختياري)', width=280,
                                                      options=[(str(c.id), c.name) for c in customers_cache])
        add_err = ft.Text('', color=theme.DANGER, visible=False)
        items_col = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
        total_txt = ft.Text('0.00', size=20, weight=ft.FontWeight.BOLD, color=theme.PRIMARY)
        items_tab_btn = ft.OutlinedButton('الأصناف', icon=ft.Icons.GRID_VIEW)            # موبايل: تبويبين بدل عمودين جنب بعض
        order_tab_btn = ft.OutlinedButton('الطلب', icon=ft.Icons.RECEIPT_LONG)
        header_txt = ft.Text('', size=18, weight=ft.FontWeight.BOLD)
        sub_txt = ft.Text('', size=12, color=theme.TEXT_MUTED)
        page_err = ft.Text('', color=theme.DANGER, visible=False)

        def refresh():
            o = services.get_restaurant_order(order_id)
            if not o or o['state'] != 'open':
                show_floor_tab(); return
            if o['table_number']:
                header_txt.value = f"طاولة {o['table_number']}  -  {o['number']}"
            else:
                type_label = services.RESTAURANT_ORDER_TYPES.get(o['order_type'], o['order_type'])
                header_txt.value = f"{type_label}  -  {o['number']}" + (f"  -  {o['customer_name']}" if o['customer_name'] else '') + (f"  -  {o['customer_phone']}" if o['customer_phone'] else '')
            sub_txt.value = (f"طلب محلي  •  {o['guests']} أشخاص  •  فُتح: {o['opened_at']:%H:%M}" if o['table_number'] else f"فُتح: {o['opened_at']:%H:%M}" + (f"  •  العنوان: {o['delivery_address']}" if o['delivery_address'] else ''))
            rows = []
            for it in o['items']:
                status_badge = {'pending': ('لم يُرسل', theme.WARNING), 'sent': ('في المطبخ', theme.PRIMARY), 'served': ('قُدّم', theme.SUCCESS)}.get(it['kitchen_status'], ('', None))
                locked = it['kitchen_status'] != 'pending'
                if it['kitchen_status'] == 'voided':
                    rows.append(ft.Container(content=ft.Row([
                        ft.Column([ft.Text(it['name'], size=13, color=theme.TEXT_MUTED, style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH)),
                                   ft.Text(f"ملغي ({it['quantity']:g}) - {it['void_reason']}" + (f" - اعتماد: {it['approved_by']}" if it['approved_by'] else ''), size=11, color=theme.DANGER)], spacing=0, expand=True),
                        ft.Icon(ft.Icons.BLOCK, size=16, color=theme.DANGER)], spacing=6), padding=ft.Padding(left=4, right=4, top=4, bottom=4),
                        border=ft.border.Border(bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT))))
                    continue
                q_f = ft.TextField(value=f"{it['quantity']:g}", width=60, text_align=ft.TextAlign.CENTER, keyboard_type=ft.KeyboardType.NUMBER, read_only=locked, disabled=locked)

                def on_qty(e, iid=it['id'], f=q_f):
                    try:
                        services.update_restaurant_order_item(iid, quantity=float(f.value or 1))
                    except Exception as ex:
                        snack(str(ex))
                    refresh()
                if not locked:
                    q_f.on_submit = on_qty
                    q_f.on_blur = on_qty
                rows.append(ft.Container(
                    content=ft.Row([
                        ft.Column([ft.Text(it['name'], size=13, weight=ft.FontWeight.BOLD),
                                   ft.Row([ft.Text(f"{it['unit_price']:,.2f}", size=11, color=theme.TEXT_MUTED),
                                           ft.Text(status_badge[0], size=10, color=status_badge[1])] +
                                          ([ft.Text(f"• {it['note']}", size=11, color=theme.WARNING)] if it['note'] else []), spacing=8)],
                                  spacing=0, expand=True),
                        q_f,
                        ft.Text(f"{it['line_total']:,.2f}", width=70, text_align=ft.TextAlign.END, weight=ft.FontWeight.BOLD),
                        (ft.IconButton(icon=ft.Icons.LOCK_OUTLINE, icon_size=16, icon_color=theme.DANGER, tooltip='اتبعت للمطبخ - الكمية مقفولة. اضغط لإلغاء الصنف (باعتماد مدير)',
                                       on_click=lambda e, i_=it: open_void_sent(i_)) if locked else
                         ft.IconButton(icon=ft.Icons.CLOSE, icon_size=16, on_click=lambda e, iid=it['id']: (services.remove_restaurant_order_item(iid), refresh()))),
                    ], spacing=6),
                    padding=ft.Padding(left=4, right=4, top=4, bottom=4),
                    border=ft.border.Border(bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT)),
                ))
            items_col.controls = rows if rows else [ft.Text('لسه مفيش أصناف - أضف من الأعلى', color=theme.TEXT_MUTED)]
            total_txt.value = f"{o['total']:,.2f}"
            order_tab_btn.content = f"الطلب ({o['items_count']}) - {o['total']:,.2f}"
            send_btn.disabled = o['pending_items'] == 0
            send_btn.content = f"إرسال للمطبخ ({o['pending_items']})" if o['pending_items'] else 'إرسال للمطبخ'
            pay_btn.disabled = o['items_count'] == 0 or o['pending_items'] > 0
            pay_btn.tooltip = 'ابعت الأصناف للمطبخ الأول' if o['pending_items'] else None
            page_err.value = f"فيه {o['pending_items']} صنف لم يُرسل للمطبخ - اضغط \"إرسال للمطبخ\" قبل الدفع" if o['pending_items'] else ''
            page_err.visible = bool(o['pending_items'])
            page.update()

        def add_item(product, qty=1):
            try:
                cid = int(price_customer_dd.value) if price_customer_dd.value else None
                services.add_restaurant_order_item(order_id, product.id, qty, note_f.value or '', customer_id=cid)
                add_err.visible = False
                refresh()
            except Exception as ex:
                add_err.value = str(ex); add_err.visible = True; page.update()

        def render_group_buttons():
            def select_group(gid):
                active_group['id'] = gid
                render_group_buttons(); render_products(); page.update()

            buttons = [ft.Container(
                content=ft.Text('الكل', size=13, weight=ft.FontWeight.BOLD, color='#FFFFFF' if active_group['id'] is None else theme.TEXT_MUTED),
                bgcolor=theme.PRIMARY if active_group['id'] is None else theme.SURFACE_ALT, border_radius=18,
                padding=ft.Padding(left=16, right=16, top=8, bottom=8), ink=True, on_click=lambda e: select_group(None),
            )]
            for g in pos_groups_cache:
                is_active = active_group['id'] == g.id
                buttons.append(ft.Container(
                    content=ft.Text(g.name, size=13, weight=ft.FontWeight.BOLD, color='#FFFFFF' if is_active else theme.TEXT_MUTED),
                    bgcolor=(g.color or theme.PRIMARY) if is_active else theme.SURFACE_ALT, border_radius=18,
                    padding=ft.Padding(left=16, right=16, top=8, bottom=8), ink=True, on_click=lambda e, gid=g.id: select_group(gid),
                ))
            group_buttons_row.controls = buttons

        def render_products(e=None):
            if active_group['id'] is not None:
                products = [p for p in services.list_products_in_pos_group(active_group['id']) if p.can_be_sold]
                if search_f.value:
                    needle = search_f.value.strip().lower()
                    products = [p for p in products if needle in p.name.lower() or needle in p.sku.lower()]
            else:
                products = [p for p in services.list_products(search=search_f.value or None) if p.can_be_sold]
            tiles = []
            for p in products[:60]:
                if p.image_path and os.path.exists(p.image_path):
                    thumb = ft.Container(content=ft.Image(src=p.image_path, width=56, height=56, fit=ft.BoxFit.COVER, border_radius=10), border_radius=10)
                else:
                    thumb = ft.Container(content=ft.Icon(ft.Icons.RESTAURANT_MENU, size=26, color=theme.PRIMARY),
                                         bgcolor=ft.Colors.with_opacity(0.08, theme.PRIMARY), border_radius=10, padding=12, alignment=ft.Alignment(0, 0))
                tiles.append(ft.Container(
                    content=ft.Column([thumb, ft.Text(p.name, size=11, weight=ft.FontWeight.BOLD, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, text_align=ft.TextAlign.CENTER),
                                       ft.Text(f'{p.sale_price:,.2f} ر.س', size=11, color=theme.PRIMARY, weight=ft.FontWeight.BOLD)],
                                      spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=6, border_radius=10, bgcolor=theme.CARD_BG,
                    border=ft.border.Border(*(ft.border.BorderSide(1, theme.BORDER_LIGHT) for _ in range(4))),
                    ink=True, on_click=lambda e, prod=p: add_item(prod),
                ))
            products_grid.controls = tiles
            if e is not None:
                page.update()

        search_f.on_change = render_products

        def on_scan(e=None):
            code = (search_f.value or '').strip()
            if not code:
                return
            try:
                hit = services.scan_lookup(code)
            except ValueError as ex:
                add_err.value = str(ex); add_err.visible = True; search_f.value = ''; page.update(); return
            if hit:
                add_item(hit['product'], hit['qty']); search_f.value = ''; render_products(); page.update()
                try: page.run_task(search_f.focus)
                except Exception: pass

        search_f.on_submit = on_scan

        def kitchen_out(res):
            """تذكرة المطبخ: طباعة حرارية مباشرة لو طابعة المطبخ مفعّلة (وتفشل لـ PDF)، وإلا PDF زي الأول."""
            if thermal.is_enabled('kitchen'):
                ok, msg = thermal.print_kitchen(res)
                if ok:
                    return True
                snack(msg)
            try:
                theme.open_or_download_file(page, services.generate_kitchen_ticket_pdf_file(res))
            except Exception:
                pass
            return False

        def send_kitchen(e):
            try:
                res = services.send_order_to_kitchen(order_id)
                kitchen_out(res)
                snack(f"اتبعت {len(res['items'])} صنف للمطبخ")
                refresh()
            except Exception as ex:
                snack(str(ex))

        def open_void_sent(it):
            can = services.user_has_action(services.current_user(), 'restaurant', 'close')
            qty_f = ft.TextField(label=f"الكمية الملغاة (من {it['quantity']:g})", width=300, value=f"{it['quantity']:g}", keyboard_type=ft.KeyboardType.NUMBER)
            reason_f = ft.TextField(label='سبب الإلغاء *', width=300, autofocus=True)
            mu_f = ft.TextField(label='اسم مستخدم المدير', width=300, visible=not can)
            mp_f = ft.TextField(label='كلمة مرور المدير', width=300, password=True, can_reveal_password=True, visible=not can)
            verr = ft.Text('', color=theme.DANGER, visible=False)

            def do(ev):
                try:
                    approver = None
                    if not can:
                        approver = services.authenticate_user(mu_f.value, mp_f.value, second_factor=False)
                        if not approver:
                            raise ValueError('بيانات المدير غير صحيحة')
                    res = services.void_sent_order_item(it['id'], reason_f.value, approver, qty_f.value)
                    vd.open = False; page.update()
                    kitchen_out(res)
                    snack('تم إلغاء الصنف وإبلاغ المطبخ'); refresh()
                except Exception as ex:
                    verr.value = str(ex); verr.visible = True; page.update()

            vd = ft.AlertDialog(modal=True, title=ft.Text(f"إلغاء (كلي أو جزئي) لصنف مبعوث: {it['name']}"),
                                content=ft.Column([ft.Text(f"الكمية: {it['quantity']:g}" + ('' if can else ' - محتاج اعتماد مدير'), size=12, color=theme.TEXT_MUTED), qty_f, reason_f, mu_f, mp_f, verr], tight=True, spacing=10),
                                actions=[ft.TextButton('تراجع', on_click=lambda ev: (setattr(vd, 'open', False), page.update())),
                                         theme.guard_submit(ft.FilledButton('إلغاء الصنف', bgcolor=theme.DANGER, on_click=do))])
            page.overlay.append(vd); vd.open = True; page.update()

        def void_order(e):
            def do(ev):
                try:
                    services.void_restaurant_order(order_id, reason_f.value or '')
                    vdlg.open = False; page.update()
                    snack('تم إلغاء الطلب'); show_floor_tab()
                except Exception as ex:
                    snack(str(ex))
            reason_f = ft.TextField(label='السبب (اختياري)', width=280)
            vdlg = ft.AlertDialog(modal=True, title=ft.Text('إلغاء الطلب'),
                                  content=ft.Column([ft.Text('هيتحرر الطاولة من غير فاتورة. متأكد؟'), reason_f], tight=True, spacing=10),
                                  actions=[ft.TextButton('تراجع', on_click=lambda ev: (setattr(vdlg, 'open', False), page.update())),
                                           ft.FilledButton('إلغاء الطلب', bgcolor=theme.DANGER, on_click=do)])
            page.overlay.append(vdlg); vdlg.open = True; page.update()

        def open_pay(e):
            customers = services.list_customers()
            o0 = services.get_restaurant_order(order_id)
            term = services.get_pos_terminal(o0['terminal_id']) if o0 and o0.get('terminal_id') else None
            def_cust = str(term['default_customer_id']) if term and term['default_customer_id'] else None
            cust_dd = ft.Dropdown(label='العميل', width=240, options=[ft.dropdown.Option(str(c.id), c.name) for c in customers],
                                  value=def_cust if (term and term['lock_customer'] and def_cust) else (price_customer_dd.value or def_cust or (str(customers[0].id) if customers else None)),
                                  disabled=bool(term and term['lock_customer'] and def_cust))
            payment_methods = [m for m in services.list_payment_methods(active_only=True) if (not term) or m.id in [x['id'] for x in term['payment_methods']]]
            pay_dd = ft.Dropdown(label='طريقة الدفع', width=220,
                                 options=[ft.dropdown.Option(str(m.id), m.name) for m in payment_methods],
                                 value=(str(term['default_payment_method_id']) if term and term['default_payment_method_id'] in [m.id for m in payment_methods] else (str(payment_methods[0].id) if payment_methods else None)))
            perr = ft.Text('', color=theme.DANGER, visible=False)
            disc_ctrl, disc_spec, disc_recalc, disc_state, _ = discount_box(page, lambda: o0['total'] if o0 else 0, get_customer=lambda: cust_dd.value)
            cust_dd.on_select = disc_recalc
            disc_recalc()

            def confirm(ev):
                try:
                    if not cust_dd.value:
                        raise ValueError('اختر العميل')
                    if not pay_dd.value:
                        raise ValueError('اختر طريقة الدفع')
                    r = services.checkout_restaurant_order(order_id, customer_id=int(cust_dd.value), payment_method_id=int(pay_dd.value), discount_spec=disc_spec())
                    pdlg.open = False; page.update()
                    show_receipt(r['invoice_id'])
                    show_floor_tab()
                except Exception as ex:
                    perr.value = str(ex); perr.visible = True; page.update()

            o = services.get_restaurant_order(order_id)
            pdlg = ft.AlertDialog(modal=True, title=ft.Text('الدفع وإتمام الطلب'),
                                  content=ft.Column([ft.Text(f"الإجمالي: {o['total']:,.2f}", size=16, weight=ft.FontWeight.BOLD), cust_dd, pay_dd, ft.Divider(), ft.Text('خصم / كوبون (اختياري)', size=12, color=theme.TEXT_MUTED), disc_ctrl, perr], tight=True, spacing=10, width=470),
                                  actions=[ft.TextButton('تراجع', on_click=lambda ev: (setattr(pdlg, 'open', False), page.update())),
                                           ft.FilledButton('تأكيد الدفع', icon=ft.Icons.PAYMENTS_OUTLINED, bgcolor=theme.PRIMARY, on_click=confirm)])
            page.overlay.append(pdlg); pdlg.open = True; page.update()

        def open_split(e):
            o = services.get_restaurant_order(order_id)
            rows_src = [i for i in o['items'] if i['kitchen_status'] in ('sent', 'served')]
            if not rows_src:
                snack('مفيش أصناف مبعوثة للمطبخ تتقسم - أرسل الطلب أولًا'); return
            if o['pending_items']:
                snack('فيه أصناف لم تُرسل للمطبخ - هتفضل مفتوحة، والتقسيم للمبعوث بس')
            customers = services.list_customers()
            term = services.get_pos_terminal(o['terminal_id']) if o.get('terminal_id') else None
            def_cust = str(term['default_customer_id']) if term and term['default_customer_id'] else None
            cust_dd = ft.Dropdown(label='العميل', width=200, options=[ft.dropdown.Option(str(c.id), c.name) for c in customers],
                                  value=def_cust or (str(customers[0].id) if customers else None), disabled=bool(term and term['lock_customer'] and def_cust))
            pms = [m for m in services.list_payment_methods(active_only=True) if (not term) or m.id in [x['id'] for x in term['payment_methods']]]
            pay_dd = ft.Dropdown(label='طريقة الدفع', width=180, options=[ft.dropdown.Option(str(m.id), m.name) for m in pms],
                                 value=(str(term['default_payment_method_id']) if term and term['default_payment_method_id'] in [m.id for m in pms] else (str(pms[0].id) if pms else None)))
            serr = ft.Text('', color=theme.DANGER, visible=False)
            total_txt = ft.Text('الجزء المدفوع: 0.00', weight=ft.FontWeight.BOLD, color=theme.PRIMARY)
            fields = {}
            sel_total = {'v': 0.0}
            disc_ctrl, disc_spec, disc_recalc, disc_state, _ = discount_box(page, lambda: sel_total['v'], get_customer=lambda: cust_dd.value)
            cust_dd.on_select = disc_recalc

            def recalc(ev=None):
                t = 0.0
                for it in rows_src:
                    try:
                        q = float(fields[it['id']].value or 0)
                    except ValueError:
                        q = 0
                    t += max(0, min(q, it['quantity'])) * it['unit_price'] * (1 + it['tax_rate'] / 100.0)
                sel_total['v'] = t
                total_txt.value = f'الجزء المدفوع: {t:,.2f}'
                disc_recalc()

            lines = []
            for it in rows_src:
                f = ft.TextField(value='0', width=70, dense=True, text_align=ft.TextAlign.CENTER, keyboard_type=ft.KeyboardType.NUMBER, on_change=recalc)
                fields[it['id']] = f

                def all_(ev, f=f, q=it['quantity']):
                    f.value = f'{q:g}'; recalc()
                lines.append(ft.Row([ft.Column([ft.Text(it['name'], size=13, weight=ft.FontWeight.BOLD), ft.Text(f"{it['quantity']:g} × {it['unit_price']:,.2f}", size=11, color=theme.TEXT_MUTED)], spacing=0, expand=True),
                                     f, ft.TextButton('الكل', on_click=all_)], spacing=6))

            def go(ev):
                try:
                    sel = {}
                    for it in rows_src:
                        q = float(fields[it['id']].value or 0)
                        if q < 0:
                            raise ValueError('كمية غير صحيحة')
                        if q > 0:
                            sel[it['id']] = q
                    r = services.split_checkout_restaurant_order(order_id, sel, customer_id=int(cust_dd.value) if cust_dd.value else None, payment_method_id=int(pay_dd.value) if pay_dd.value else None, discount_spec=disc_spec())
                    sdlg.open = False; page.update()
                    show_receipt(r['invoice_id'])
                    refresh()
                except Exception as ex:
                    serr.value = str(ex); serr.visible = True; page.update()

            sdlg = ft.AlertDialog(modal=True, title=ft.Text('تقسيم الفاتورة - اختر الكميات اللي هتتدفع الآن'),
                                  content=ft.Column([ft.Column(lines, spacing=8, scroll=ft.ScrollMode.AUTO, height=min(320, 56 * len(lines) + 10)), ft.Divider(),
                                                     ft.Row([cust_dd, pay_dd], wrap=True, spacing=10), total_txt, ft.Text('خصم / كوبون (اختياري)', size=12, color=theme.TEXT_MUTED), disc_ctrl, serr], tight=True, spacing=8, width=500),
                                  actions=[ft.TextButton('تراجع', on_click=lambda ev: (setattr(sdlg, 'open', False), page.update())),
                                           theme.guard_submit(ft.FilledButton('دفع الجزء المحدد', icon=ft.Icons.CALL_SPLIT, bgcolor=theme.PRIMARY, on_click=go))])
            page.overlay.append(sdlg); sdlg.open = True; page.update()

        def open_move(e):
            o = services.get_restaurant_order(order_id)
            tables = services.list_tables_status()
            free = [t for t in tables if not t['order'] and t['id'] != o['table_id']]
            busy = [t for t in tables if t['order'] and t['order']['id'] != order_id]
            mode_dd = ft.Dropdown(label='العملية', width=260, value='transfer', options=[ft.dropdown.Option('transfer', 'نقل لطاولة فاضية'), ft.dropdown.Option('merge', 'دمج مع طلب طاولة تانية')])
            tgt_dd = ft.Dropdown(label='الطاولة', width=260, options=[])
            merr = ft.Text('', color=theme.DANGER, visible=False)

            def fill(ev=None):
                src = free if mode_dd.value == 'transfer' else busy
                tgt_dd.options = [ft.dropdown.Option(str(t['id']), f"طاولة {t['number']}" + (f" ({t['section']})" if t['section'] else '') + (f" - {t['order']['items_count']} صنف" if t['order'] else '')) for t in src]
                tgt_dd.value = None
                try: page.update()
                except Exception: pass

            def do(ev):
                try:
                    if not tgt_dd.value:
                        raise ValueError('اختر الطاولة')
                    if mode_dd.value == 'transfer':
                        services.transfer_restaurant_order(order_id, int(tgt_dd.value))
                        snack('تم نقل الطلب')
                        mdlg.open = False; page.update(); refresh()
                    else:
                        t = next(x for x in busy if str(x['id']) == tgt_dd.value)
                        services.merge_restaurant_orders(order_id, t['order']['id'])
                        snack('تم دمج الطلب')
                        mdlg.open = False; page.update(); open_order_screen(t['order']['id'])
                except Exception as ex:
                    merr.value = str(ex); merr.visible = True; page.update()

            mode_dd.on_select = fill
            fill()
            mdlg = ft.AlertDialog(modal=True, title=ft.Text('نقل / دمج الطلب'),
                                  content=ft.Column([mode_dd, tgt_dd, ft.Text('الدمج بينقل كل أصناف الطلب ده (بحالتها) للطلب التاني ويقفل ده.', size=11, color=theme.TEXT_MUTED), merr], tight=True, spacing=10, width=300),
                                  actions=[ft.TextButton('تراجع', on_click=lambda ev: (setattr(mdlg, 'open', False), page.update())),
                                           theme.guard_submit(ft.FilledButton('تنفيذ', bgcolor=theme.PRIMARY, on_click=do))])
            page.overlay.append(mdlg); mdlg.open = True; page.update()

        send_btn = ft.OutlinedButton('إرسال للمطبخ', icon=ft.Icons.SOUP_KITCHEN_OUTLINED, on_click=send_kitchen)
        pay_btn = ft.FilledButton('الدفع وإتمام الطلب', icon=ft.Icons.PAYMENTS_OUTLINED, bgcolor=theme.PRIMARY, on_click=open_pay)

        def back_to_floor(e=None):
            show_floor_tab()

        left_panel = ft.Column([
            theme.h_scroll(group_buttons_row), ft.Container(height=8),
            ft.Row([search_f]), ft.Container(height=8), products_grid,
        ], expand=2)

        price_customer_dd.on_change = lambda e: page.update()
        right_col = ft.Column([
            ft.Text('أصناف الطلب', size=16, weight=ft.FontWeight.BOLD),
            price_customer_dd.control, note_f, add_err, ft.Divider(),
            items_col, ft.Divider(),
            ft.Row([ft.Text('الإجمالي', weight=ft.FontWeight.BOLD), ft.Container(expand=True), total_txt]),
            page_err,
            ft.Row([send_btn, pay_btn], wrap=True, spacing=10),
            ft.Row([ft.OutlinedButton('تقسيم الفاتورة', icon=ft.Icons.CALL_SPLIT, on_click=open_split),
                    ft.OutlinedButton('نقل / دمج', icon=ft.Icons.SWAP_HORIZ, on_click=open_move, visible=bool(order0_has_table))], wrap=True, spacing=10),
            ft.OutlinedButton('إلغاء الطلب', icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, on_click=void_order),
        ], spacing=10, expand=True)
        right_panel = theme.card(right_col, expand=1)

        render_group_buttons(); render_products()
        head_row = ft.Row([ft.IconButton(icon=ft.Icons.ARROW_FORWARD, tooltip='رجوع للصالة', on_click=back_to_floor),
                           ft.Column([header_txt, sub_txt], spacing=0)])
        if theme._page_w():
            # موبايل: الأصناف والطلب في تبويبين، والطلب بيسكرول (items_col بتاخد ارتفاعها الطبيعي)
            search_f.expand = None
            left_panel.expand = True
            right_panel.expand = True
            right_col.scroll = ft.ScrollMode.AUTO
            items_col.expand = None
            items_col.scroll = None
            order_tab_btn.expand = True
            items_tab_btn.expand = True

            def show_tab(which):
                left_panel.visible = which == 'items'
                right_panel.visible = which == 'order'
                items_tab_btn.style = ft.ButtonStyle(bgcolor=theme.PRIMARY if which == 'items' else None, color='#FFFFFF' if which == 'items' else theme.PRIMARY_TEXT)
                order_tab_btn.style = ft.ButtonStyle(bgcolor=theme.PRIMARY if which == 'order' else None, color='#FFFFFF' if which == 'order' else theme.PRIMARY_TEXT)
                page.update()
            items_tab_btn.on_click = lambda e: show_tab('items')
            order_tab_btn.on_click = lambda e: show_tab('order')
            show_tab('items')
            root.controls = [head_row, ft.Row([items_tab_btn, order_tab_btn], spacing=8), left_panel, right_panel]
        else:
            root.controls = [
                head_row,
                ft.Container(height=8),
                ft.Row([left_panel, right_panel], expand=True, spacing=16),
            ]
        page.update()
        refresh()

    def show_receipt(invoice_id):
        invoice = services.get_sales_invoice(invoice_id)
        printed = {'n': 0}

        def do_print(e=None):
            try:
                if thermal.is_enabled('receipt'):
                    ok, msg = thermal.print_receipt(invoice.id, reprint=printed['n'] > 0)
                    if ok:
                        printed['n'] += 1; snack('تمت طباعة الإيصال'); return
                    snack(msg)
                path = services.generate_invoice_pdf_file(invoice.id)
                theme.open_or_download_file(page, path)
            except Exception as ex:
                snack(f'تعذرت الطباعة: {ex}')

        if thermal.is_enabled('receipt') and thermal.get_config()['receipt']['auto']:
            ok_, msg_ = thermal.print_receipt(invoice.id)
            printed['n'] += 1 if ok_ else 0
            if not ok_:
                snack(msg_)

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text('تم الدفع بنجاح'),
            content=ft.Column([
                ft.Text(f"فاتورة رقم: {invoice.number}", weight=ft.FontWeight.BOLD),
                ft.Text(f"الإجمالي: {invoice.total:,.2f}", size=18, weight=ft.FontWeight.BOLD, color=theme.PRIMARY),
            ], tight=True, spacing=6),
            actions=[ft.IconButton(icon=ft.Icons.PRINT_OUTLINED, tooltip='طباعة', on_click=do_print),
                     ft.FilledButton('تمام', bgcolor=theme.PRIMARY, on_click=lambda e: (setattr(dlg, 'open', False), page.update()))],
        )
        page.overlay.append(dlg); dlg.open = True; page.update()

    # ============================================================ الأقسام والطاولات
    def show_manage():
        sec_name_f = ft.TextField(label='اسم القسم', width=220)
        sec_err = ft.Text('', color=theme.DANGER, visible=False)
        sec_table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['القسم', 'الحالة', '']], rows=[])

        tbl_number_f = ft.TextField(label='رقم الطاولة', width=140)
        tbl_name_f = ft.TextField(label='اسم/ملاحظة', width=180)
        tbl_seats_f = ft.TextField(label='عدد المقاعد', width=120, value='4', keyboard_type=ft.KeyboardType.NUMBER)
        tbl_sec_dd = ft.Dropdown(label='القسم', width=220, options=[])
        tbl_err = ft.Text('', color=theme.DANGER, visible=False)
        tbl_table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['الرقم', 'الاسم', 'المقاعد', 'القسم', '']], rows=[])

        def fill_sections():
            secs = services.list_restaurant_sections()
            tbl_sec_dd.options = [ft.dropdown.Option('', 'بدون')] + [ft.dropdown.Option(str(s.id), s.name) for s in secs]
            rows = []
            for s in secs:
                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(s.name)), ft.DataCell(ft.Text('نشط' if s.is_active else 'موقوف')),
                    ft.DataCell(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, on_click=lambda e, sid=s.id: del_section(sid))),
                ]))
            sec_table.rows = rows

        def add_section(e):
            try:
                services.create_restaurant_section(sec_name_f.value)
                sec_name_f.value = ''; sec_err.visible = False
                show_floor_tab()
            except Exception as ex:
                sec_err.value = str(ex); sec_err.visible = True; page.update()

        def del_section(sid):
            try:
                services.delete_restaurant_section(sid)
                show_floor_tab()
            except Exception as ex:
                snack(str(ex))

        def fill_tables():
            rows = []
            for t in services.list_restaurant_tables():
                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(t.number, weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(t.name or '-')),
                    ft.DataCell(ft.Text(str(t.seats))), ft.DataCell(ft.Text(t.section.name if t.section else '-')),
                    ft.DataCell(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, on_click=lambda e, tid=t.id: del_table(tid))),
                ]))
            tbl_table.rows = rows

        def add_table(e):
            try:
                services.create_restaurant_table(tbl_number_f.value, tbl_name_f.value, tbl_seats_f.value or 4, tbl_sec_dd.value or None)
                tbl_number_f.value = ''; tbl_name_f.value = ''; tbl_seats_f.value = '4'; tbl_err.visible = False
                show_floor_tab()
            except Exception as ex:
                tbl_err.value = str(ex); tbl_err.visible = True; page.update()

        def del_table(tid):
            try:
                services.delete_restaurant_table(tid)
                show_floor_tab()
            except Exception as ex:
                snack(str(ex))

        fill_sections(); fill_tables()
        return ft.Row([
            theme.card(ft.Column([
                ft.Text('الأقسام', size=16, weight=ft.FontWeight.BOLD),
                ft.Row([sec_name_f, ft.FilledButton('إضافة', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=add_section)]),
                sec_err, theme.h_scroll(sec_table),
            ], spacing=10), expand=1),
            theme.card(ft.Column([
                ft.Text('الطاولات', size=16, weight=ft.FontWeight.BOLD),
                ft.Row([tbl_number_f, tbl_name_f, tbl_seats_f, tbl_sec_dd, ft.FilledButton('إضافة', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=add_table)], wrap=True),
                tbl_err, theme.h_scroll(tbl_table),
            ], spacing=10), expand=2),
        ], expand=True, vertical_alignment=ft.CrossAxisAlignment.START)

    # ============================================================ ملخص الشيفت
    def show_summary():
        sm = services.restaurant_shift_summary()
        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['رقم الطلب', 'الطاولة', 'وقت الفتح', 'الحالة', 'الإجمالي']], rows=[
            ft.DataRow(cells=[ft.DataCell(ft.Text(r['number'])), ft.DataCell(ft.Text(r['table_number'])), ft.DataCell(ft.Text(r['opened_at'].strftime('%Y-%m-%d %H:%M'))),
                              ft.DataCell(ft.Text({'paid': 'مدفوع', 'voided': 'ملغى', 'open': 'مفتوح', 'merged': 'مدمج'}.get(r['state'], r['state']),
                                                  color={'paid': theme.SUCCESS, 'voided': theme.DANGER, 'open': theme.WARNING}.get(r['state']))),
                              ft.DataCell(ft.Text(f"{r['total']:,.2f}"))])
            for r in sm['rows'][:200]
        ])
        return ft.Column([
            ft.Row([theme.card(ft.Column([ft.Text('طلبات مدفوعة', color=theme.TEXT_MUTED, size=12), ft.Text(str(sm['paid_count']), size=22, weight=ft.FontWeight.BOLD, color=theme.SUCCESS)])),
                    theme.card(ft.Column([ft.Text('إجمالي المبيعات', color=theme.TEXT_MUTED, size=12), ft.Text(f"{sm['paid_total']:,.2f}", size=22, weight=ft.FontWeight.BOLD, color=theme.PRIMARY)])),
                    theme.card(ft.Column([ft.Text('طلبات ملغاة', color=theme.TEXT_MUTED, size=12), ft.Text(str(sm['voided_count']), size=22, weight=ft.FontWeight.BOLD, color=theme.DANGER)])),
                    theme.card(ft.Column([ft.Text('طلبات مفتوحة الآن', color=theme.TEXT_MUTED, size=12), ft.Text(str(sm['open_count']), size=22, weight=ft.FontWeight.BOLD, color=theme.WARNING)]))], wrap=True, spacing=12),
            ft.Container(height=12),
            theme.card(ft.Column([ft.Text('كل الطلبات', size=16, weight=ft.FontWeight.BOLD), theme.h_scroll(table)])),
        ], expand=True, scroll=ft.ScrollMode.AUTO)

    # ============================================================ تقرير الإلغاءات والمرتجعات
    def show_events_report():
        rng = theme.DateRangeField('الفترة', page, width=290)
        today = datetime.date.today()
        rng.start.value = f'{today:%Y-%m-01}'; rng.end.value = f'{today:%Y-%m-%d}'
        kind_dd = ft.Dropdown(label='النوع', width=200, value='', options=[ft.dropdown.Option('', 'الكل')] + [ft.dropdown.Option(k, v) for k, v in services.KITCHEN_EVENT_KINDS.items()])
        kpis = ft.Row([], wrap=True, spacing=10)
        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x, weight=ft.FontWeight.BOLD)) for x in ['التاريخ', 'النوع', 'الطلب', 'الطاولة / النوع', 'الفاتورة', 'الصنف', 'الكمية', 'القيمة', 'السبب', 'بواسطة', 'اعتماد', 'اطلع المطبخ']], rows=[])
        pager = theme.RowPager(table, page, 100)
        st = {'rows': []}

        def d(v):
            return datetime.datetime.strptime(v, '%Y-%m-%d').date() if (v or '').strip() else None

        def run(e=None):
            sm = services.kitchen_events_summary(d(rng.start.value), d(rng.end.value))
            rows = [r for r in sm['rows'] if not kind_dd.value or r['kind'] == kind_dd.value]
            st['rows'] = rows
            kpis.controls = [theme.card(ft.Column([ft.Text(v, size=11, color=theme.TEXT_MUTED), ft.Text(f"{sm['by_kind'].get(k, {}).get('count', 0)}  |  {sm['by_kind'].get(k, {}).get('amount', 0):,.2f}", size=15, weight=ft.FontWeight.BOLD, color=theme.DANGER)], spacing=2, tight=True), padding=12)
                             for k, v in services.KITCHEN_EVENT_KINDS.items()] + [theme.card(ft.Column([ft.Text('إجمالي القيمة', size=11, color=theme.TEXT_MUTED), ft.Text(f"{sum(r['amount'] for r in rows):,.2f}", size=15, weight=ft.FontWeight.BOLD, color=theme.PRIMARY)], spacing=2, tight=True), padding=12)]

            def build(r):
                cells = [r['created_at'].strftime('%Y-%m-%d %H:%M'), r['kind_label'], r['order_number'], (f"طاولة {r['table_number']}" if r['table_number'] else services.RESTAURANT_ORDER_TYPES.get(r['order_type'], '')),
                         r['invoice_number'] or '-', r['product_name'], f"{r['quantity']:g}", f"{r['amount']:,.2f}", r['reason'], r['created_by'], r['approved_by'] or '-', 'نعم' if r['acknowledged'] else 'لا']
                return ft.DataRow(cells=[ft.DataCell(ft.Text(c, size=12.5)) for c in cells])
            pager.set_items(rows, build, keep_page=False)
            if e is not None:
                page.update()

        def export(kind):
            try:
                if not st['rows']:
                    run()
                t = [['التاريخ', 'النوع', 'الطلب', 'الطاولة / النوع', 'الفاتورة', 'الصنف', 'الكمية', 'القيمة', 'السبب', 'بواسطة', 'اعتماد']]
                for r in st['rows']:
                    t.append([r['created_at'].strftime('%Y-%m-%d %H:%M'), r['kind_label'], r['order_number'], (f"طاولة {r['table_number']}" if r['table_number'] else services.RESTAURANT_ORDER_TYPES.get(r['order_type'], '')),
                              r['invoice_number'] or '-', r['product_name'], round(r['quantity'], 2), round(r['amount'], 2), r['reason'], r['created_by'], r['approved_by'] or '-'])
                t.append(['الإجمالي', '', '', '', '', '', '', round(sum(r['amount'] for r in st['rows']), 2), '', '', ''])
                data = {'table': t, 'row_styles': {len(t) - 1: 'total'}, 'col_weights': [1.6, 1.4, 1.2, 1.4, 1.2, 2.2, 0.8, 1.1, 2.2, 1.1, 1.1], 'date_from': d(rng.start.value), 'date_to': d(rng.end.value)}
                path = (export_excel if kind == 'xlsx' else export_pdf)(data, 'kitchen_events', services.downloads_dir())
                theme.open_or_download_file(page, path)
                snack(f'تم إنشاء الملف: {path}')
            except Exception as ex:
                snack(f'تعذر التصدير: {ex}')

        kind_dd.on_select = run; kind_dd.on_change = run
        run()
        return ft.Column([
            theme.card(ft.Row([rng.control, kind_dd, ft.FilledButton('عرض', icon=ft.Icons.SEARCH, bgcolor=theme.PRIMARY, on_click=run),
                               ft.OutlinedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('xlsx')), ft.OutlinedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf'))], wrap=True, spacing=10)),
            kpis, theme.card(theme.h_scroll(table)),
        ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)

    # ============================================================ الفواتير المفتوحة
    def show_open_invoices():
        orders = services.list_open_restaurant_orders()
        now = datetime.datetime.now()
        rows = []
        for o in orders:
            el = int((now - o['opened_at']).total_seconds() // 60)
            where = f"طاولة {o['table_number']}" if o['table_number'] else services.RESTAURANT_ORDER_TYPES.get(o['order_type'], '')
            rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(o['number'], weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(where)), ft.DataCell(ft.Text(o['customer_name'] or '-')),
                                          ft.DataCell(ft.Text(str(o['items_count']))), ft.DataCell(ft.Text(f"{o['total']:,.2f}", weight=ft.FontWeight.BOLD)),
                                          ft.DataCell(ft.Text('مطبخ بانتظار' if o['pending_items'] else ('في المطبخ/قُدّم' if o['items_count'] else 'فاضي'), color=theme.WARNING if o['pending_items'] else theme.TEXT_MUTED, size=12)),
                                          ft.DataCell(ft.Text(f"{el // 60}س {el % 60}د" if el >= 60 else f"{el} د")), ft.DataCell(ft.Text(o['session_number'] or '-')),
                                          ft.DataCell(ft.FilledButton('فتح / دفع', bgcolor=theme.PRIMARY, on_click=lambda e, oid=o['id']: open_order_screen(oid)))]))
        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x, weight=ft.FontWeight.BOLD)) for x in ['الطلب', 'النوع / الطاولة', 'العميل', 'الأصناف', 'الإجمالي', 'المطبخ', 'منذ', 'الجلسة', '']], rows=rows)
        total = sum(o['total'] for o in orders)
        return ft.Column([
            ft.Row([theme.card(ft.Column([ft.Text('فواتير مفتوحة (غير مدفوعة)', size=11, color=theme.TEXT_MUTED), ft.Text(str(len(orders)), size=20, weight=ft.FontWeight.BOLD, color=theme.WARNING if orders else theme.SUCCESS)], spacing=2, tight=True), padding=12),
                    theme.card(ft.Column([ft.Text('قيمتها', size=11, color=theme.TEXT_MUTED), ft.Text(f'{total:,.2f}', size=20, weight=ft.FontWeight.BOLD, color=theme.PRIMARY)], spacing=2, tight=True), padding=12),
                    ft.Text('الفاتورة غير المدفوعة بتفضل هنا ومينفعش تقفل الجلسة وهي موجودة.', size=12, color=theme.TEXT_MUTED)], spacing=12, wrap=True),
            theme.card(ft.Column([theme.h_scroll(table) if rows else ft.Text('مفيش فواتير مفتوحة', color=theme.TEXT_MUTED)])),
        ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)

    # ============================================================ شريط الجلسة
    def build_session_bar():
        terminals = services.pos_terminals_for_current_user()
        if sess['terminal_id'] not in [t['id'] for t in terminals]:
            with_open = [t for t in terminals if services.get_open_pos_session(t['id'])]
            sess['terminal_id'] = (with_open or terminals or [{'id': None}])[0]['id']
        if not terminals:
            return theme.card(ft.Text('مفيش ماكينات نقاط بيع - أضف ماكينة من "ماكينات نقاط البيع" عشان تفتح جلسة وتستخدم المطعم.', color=theme.DANGER), padding=12)
        term_dd = ft.Dropdown(label='ماكينة / كاشير', width=260, value=str(sess['terminal_id']), options=[ft.dropdown.Option(str(t['id']), f"{t['code']} - {t['name']}") for t in terminals])

        def change(e):
            sess['terminal_id'] = int(term_dd.value); show_floor_tab()
        term_dd.on_select = change; term_dd.on_change = change
        ses = services.get_open_pos_session(sess['terminal_id'])
        term = next(t for t in terminals if t['id'] == sess['terminal_id'])
        if ses:
            n_open = len(services.list_open_restaurant_orders(session_id=ses['id']))
            info = ft.Column([ft.Text(f"جلسة {ses['number']} مفتوحة", weight=ft.FontWeight.BOLD, color=theme.SUCCESS),
                              ft.Text(f"{ses['opened_by_name']}  •  منذ {ses['opened_at']:%H:%M}  •  عهدة {ses['opening_cash']:,.2f}  •  فواتير مفتوحة: {n_open}", size=12, color=theme.WARNING if n_open else theme.TEXT_MUTED)], spacing=0, width=420)
            btns = [ft.OutlinedButton('تقرير الجلسة', icon=ft.Icons.ASSESSMENT_OUTLINED, on_click=lambda e: session_report_dialog(page, ses['id'], on_changed=show_floor_tab)),
                    ft.FilledButton('إغلاق الجلسة', icon=ft.Icons.LOCK_OUTLINE, bgcolor=theme.DANGER, on_click=lambda e: close_session_dialog(page, ses['id'], on_done=lambda rep: (snack('تم إغلاق الجلسة'), show_floor_tab())))]
        else:
            info = ft.Column([ft.Text('مفيش جلسة مفتوحة', weight=ft.FontWeight.BOLD, color=theme.DANGER), ft.Text('افتح جلسة عشان تقدر تفتح طلبات جديدة', size=12, color=theme.TEXT_MUTED)], spacing=0, width=420)
            btns = [ft.FilledButton('فتح جلسة', icon=ft.Icons.LOCK_OPEN_OUTLINED, bgcolor=theme.PRIMARY, on_click=lambda e: open_session_dialog(page, term, on_done=lambda sid: (snack('تم فتح الجلسة'), show_floor_tab())))]
        return theme.card(ft.Row([ft.Icon(ft.Icons.SCHEDULE, color=theme.PRIMARY), term_dd, info] + btns, spacing=12, wrap=True, vertical_alignment=ft.CrossAxisAlignment.CENTER), padding=12)

    root = ft.Column(expand=True)

    def show_floor_tab():
        idx = tabs.selected_index
        tabs.set_tabs([('الصالة', show_floor()), ('الأقسام والطاولات', show_manage()), ('ملخص الشيفت', show_summary()), ('الفواتير المفتوحة', show_open_invoices()), ('الإلغاءات والمرتجعات', show_events_report())], selected_index=idx)
        root.controls = [theme.page_title('نظام المطاعم', 'طاولات وطلبات وإرسال للمطبخ - والدفع بيتحوّل لفاتورة POS تلقائيًا'),
                         ft.Container(height=6), build_session_bar(), ft.Container(height=6), tabs.control]
        page.update()

    theme.call_without_page_update(page, show_floor_tab)
    return root
