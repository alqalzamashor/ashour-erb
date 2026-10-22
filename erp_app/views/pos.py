import os
import base64
import flet as ft
from ._approval import prompt as approval_prompt
import asyncio
import threading
from .. import offline, services, theme, thermal
from ._discount import discount_box
from .pos_sessions import open_session_dialog, close_session_dialog, session_report_dialog


_GEN = {'n': 0}      # عشان حلقة المزامنة بتاعت شاشة قديمة تقف لما الشاشة تتفتح تاني


def build_pos(page: ft.Page):
    """شاشة نقاط البيع: بحث/شبكة أصناف + سلة + إتمام بيع فوري بفاتورة
    ضريبية وQR، مع محاولة إرسال اختيارية لمنصة فاتورة حسب إعدادات الشركة."""
    settings = services.get_company_settings()
    customers = services.list_customers()
    branches = services.list_branches(True)
    locations = services.list_locations() if hasattr(services, 'list_locations') else []
    pos_groups = services.list_pos_groups()
    active_group = {'id': None}  # None = كل الأصناف
    group_buttons_row = ft.Row(wrap=True, spacing=8)

    search = ft.TextField(label='بحث عن صنف (الاسم أو الكود)', width=320, prefix_icon=ft.Icons.SEARCH, autofocus=True)
    products_grid = ft.GridView(expand=True, max_extent=170, child_aspect_ratio=(0.8 if theme._page_w() else 0.95), spacing=8, run_spacing=8)

    customer_dd = ft.Dropdown(
        label='العميل', width=260,
        options=[ft.dropdown.Option(str(c.id), c.name) for c in customers],
        value=str(customers[0].id) if customers else None,
    )
    payment_methods = services.list_payment_methods(active_only=True)
    payment_dd = ft.Dropdown(
        label='طريقة الدفع', width=220,
        options=[ft.dropdown.Option(str(m.id), m.name) for m in payment_methods],
        value=str(payment_methods[0].id) if payment_methods else None,
    )
    err = ft.Text('', color=theme.DANGER, visible=False)
    # طرق الدفع المربوطة بجهاز شبكة يدوي: الكاشير يكتب رقم الموافقة من الجهاز
    from .. import banking
    pm_provider = {m.id: getattr(m, 'provider_id', None) for m in payment_methods}
    pay_ref = ft.TextField(label='رقم الموافقة / المرجع من جهاز الشبكة', width=260, dense=True, visible=False)

    def sync_pay_ref(e=None):
        pid = pm_provider.get(int(payment_dd.value)) if payment_dd.value else None
        pay_ref.visible = bool(pid and banking.provider_needs_reference(pid))
        if not pay_ref.visible:
            pay_ref.value = ''
        if e is not None:
            page.update()
    payment_dd.on_select = sync_pay_ref

    # ---- ماكينة الكاشير: لو فيه ماكينات معرَّفة (من شاشة "ماكينات نقاط البيع") الكاشير لازم يشتغل على ماكينة مسموح له بيها: الفرع ومركز التكلفة
    # والمخزن والكاشير بييجوا منها، وطرق الدفع بتتقيّد بطرقها، والعميل الافتراضي بيتعبّى (وبيتقفل لو الماكينة كده).
    terminals = services.pos_terminals_for_current_user()
    any_terminals = bool(services.list_pos_terminals(active_only=True))
    all_payment_methods = list(payment_methods)
    current_terminal = {'t': terminals[0] if terminals else None}
    terminal_dd = ft.Dropdown(label='ماكينة الكاشير', width=300, options=[ft.dropdown.Option(str(t['id']), f"{t['code']} - {t['name']}") for t in terminals],
                              value=str(terminals[0]['id']) if terminals else None, visible=bool(terminals))
    terminal_info = ft.Text('', size=11.5, color=theme.TEXT_MUTED)
    # ---- جلسة الكاشير: فتح نقاط البيع على ماكينة بيفتح جلسة جديدة (عهدة افتتاحية)، وكل فواتير الكاشير بتتسجّل عليها لحد ما تتقفل
    session = {'s': None}
    session_text = ft.Text('', size=12, weight=ft.FontWeight.BOLD)
    session_report_btn = ft.TextButton('تقرير الجلسة', icon=ft.Icons.ASSESSMENT_OUTLINED, on_click=lambda e: session_report_dialog(page, session['s']['id'], on_changed=lambda: refresh_session()))
    session_close_btn = ft.TextButton('إغلاق الجلسة', icon=ft.Icons.LOCK_OUTLINE, style=ft.ButtonStyle(color=theme.DANGER), on_click=lambda e: close_current_session())
    session_open_btn = ft.FilledButton('فتح جلسة', icon=ft.Icons.LOCK_OPEN_OUTLINED, bgcolor=theme.PRIMARY, on_click=lambda e: prompt_open_session())
    session_bar = ft.Container(visible=False, border_radius=10, padding=ft.Padding(left=10, right=10, top=6, bottom=6),
                               content=ft.Column([session_text, ft.Row([session_open_btn, session_report_btn, session_close_btn], spacing=2)], spacing=2, tight=True))
    if any_terminals and not terminals:
        terminal_info.value = 'مفيش ماكينة كاشير متاحة ليك - اطلب من المسؤول يخصّص لك ماكينة (شاشة ماكينات نقاط البيع)'
        terminal_info.color = theme.DANGER

    cart = []  # [{'product': Product, 'qty': float}]
    # ---- وضع عدم الاتصال: نسخة محلية للأصناف + طابور مبيعات نقدية بيتزامن لما الاتصال يرجع (انظر offline.py)
    off = {'down': False}
    _GEN['n'] += 1; my_gen = _GEN['n']
    offline_text = ft.Text('', size=12, weight=ft.FontWeight.BOLD)
    offline_sync_btn = ft.TextButton('مزامنة الآن', icon=ft.Icons.SYNC)
    offline_review_btn = ft.TextButton('مراجعة الفاشل', icon=ft.Icons.ERROR_OUTLINE, style=ft.ButtonStyle(color=theme.DANGER), visible=False)
    offline_bar = ft.Container(visible=False, border_radius=10, padding=ft.Padding(left=10, right=10, top=6, bottom=6), bgcolor=theme.WARNING_LIGHT,
                               content=ft.Row([ft.Icon(ft.Icons.CLOUD_OFF, color=theme.WARNING_TEXT, size=18), offline_text, ft.Container(expand=True), offline_sync_btn, offline_review_btn], spacing=6))

    def _is_down(ex):
        if offline.is_db_error(ex):
            off['down'] = True
            return True
        return False

    def update_offline_bar():
        c = offline.counts()
        offline_bar.visible = off['down'] or c['pending'] > 0 or c['failed'] > 0
        parts = []
        if off['down']:
            parts.append('وضع عدم الاتصال - البيع النقدي فقط ومن الأصناف المحفوظة محليًا')
        if c['pending']:
            parts.append(f"{c['pending']} بيع معلّق للمزامنة")
        if c['failed']:
            parts.append(f"{c['failed']} بيع فشلت مزامنته")
        offline_text.value = '  •  '.join(parts)
        offline_review_btn.visible = c['failed'] > 0

    def do_sync(e=None, quiet=False):
        def work():
            try:
                r = offline.sync(services)
            except Exception as ex:
                r = {'synced': 0, 'failed': 0, 'offline': _is_down(ex)}
            if not r['offline']:
                off['down'] = False
            try:
                update_offline_bar()
                if r['synced'] or r['failed'] or not quiet:
                    msg = f"اتزامن {r['synced']} بيع" + (f" - وفشل {r['failed']} (راجعها)" if r['failed'] else '') if not r['offline'] else 'لسه مفيش اتصال بالسيرفر'
                    page.overlay.append(ft.SnackBar(ft.Text(msg), open=True))
                page.update()
                if r['synced']:
                    refresh_session()
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()
    offline_sync_btn.on_click = do_sync

    def open_failed_dialog(e=None):
        rows = []
        for r in offline.failed():
            def retry(ev, u=r['uuid']):
                offline.retry(u); dlg.open = False; update_offline_bar(); page.update(); do_sync(quiet=True)

            def drop(ev, u=r['uuid']):
                reason = ft.TextField(label='سبب التجاهل (مثلًا: اتسجّل يدويًا)', width=320)

                def ok(e2):
                    try:
                        offline.discard(u, reason.value); d2.open = False; dlg.open = False; update_offline_bar(); page.update()
                    except Exception as ex:
                        reason.error_text = str(ex); page.update()
                d2 = ft.AlertDialog(modal=True, title=ft.Text('تجاهل البيع'), content=reason, actions=[ft.TextButton('إلغاء', on_click=lambda e2: (setattr(d2, 'open', False), page.update())), ft.FilledButton('تجاهل', bgcolor=theme.DANGER, on_click=ok)])
                page.overlay.append(d2); d2.open = True; page.update()
            rows.append(ft.Column([ft.Text(f"{r['number']}  •  {r['at'].replace('T', ' ')}  •  {r['total']:,.2f}", weight=ft.FontWeight.BOLD, size=13), ft.Text(r['error'], size=12, color=theme.DANGER),
                                   ft.Row([ft.OutlinedButton('إعادة محاولة', on_click=retry), ft.TextButton('تجاهل', on_click=drop)]), ft.Divider(height=4)], spacing=2))
        dlg = ft.AlertDialog(modal=True, title=ft.Text('مبيعات فشلت مزامنتها'), content=ft.Container(width=460, content=ft.Column(rows or [ft.Text('مفيش')], scroll=ft.ScrollMode.AUTO, tight=True)),
                             actions=[ft.TextButton('إغلاق', on_click=lambda ev: (setattr(dlg, 'open', False), page.update()))])
        page.overlay.append(dlg); dlg.open = True; page.update()
    offline_review_btn.on_click = open_failed_dialog

    def _snapshot_bg():
        try:
            offline.save_snapshot(current_terminal['t'])
        except Exception:
            pass
    threading.Thread(target=_snapshot_bg, daemon=True).start()
    cart_col = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
    subtotal_text = ft.Text('0.00', size=15)
    tax_text = ft.Text('0.00', size=15)
    total_text = ft.Text('0.00', size=22, weight=ft.FontWeight.BOLD, color=theme.PRIMARY)

    def _cart_unit_price(item):
        """سعر الوحدة الفعلي للصنف في السلة: سعر قائمة أسعار العميل
        المختار حاليًا (لو موجود)، وإلا سعر البيع الافتراضي للصنف."""
        customer_id = int(customer_dd.value) if customer_dd.value else None
        if isinstance(item['product'], offline.OfflineProduct):
            return item['product'].sale_price, False
        try:
            price, from_list = services.get_customer_product_price(customer_id, item['product'].id)
        except Exception as ex:
            if not _is_down(ex):
                raise
            return float(item['product'].sale_price or 0), False
        return price, from_list

    def compute_totals():
        subtotal = 0.0
        tax = 0.0
        for item in cart:
            p = item['product']
            qty = item['qty']
            price, _ = _cart_unit_price(item)
            line_subtotal = qty * price
            line_tax = line_subtotal * (p.tax_rate or settings.default_tax_rate or 15) / 100.0
            subtotal += line_subtotal
            tax += line_tax
        subtotal_text.value = f'{subtotal:,.2f}'
        tax_text.value = f'{tax:,.2f}'
        total_text.value = f'{subtotal + tax:,.2f}'
        try:
            cart_tab_btn.content = f"السلة ({sum(i['qty'] for i in cart):g}) - {subtotal + tax:,.2f}" if cart else 'السلة'
        except NameError:
            pass
        try:
            disc_recalc()
        except NameError:
            pass
        except Exception as ex:
            if not _is_down(ex):
                raise

    def render_cart():
        rows = []
        for item in cart:
            p = item['product']
            price, from_list = _cart_unit_price(item)
            line_total = item['qty'] * price
            qty_field = ft.TextField(value=str(item['qty']), width=60, text_align=ft.TextAlign.CENTER,
                                      keyboard_type=ft.KeyboardType.NUMBER)

            def on_qty_change(e, it=item, field=qty_field):
                try:
                    v = float(field.value or 0)
                    it['qty'] = v if v > 0 else 1
                except ValueError:
                    it['qty'] = 1
                render_cart()
                page.update()

            qty_field.on_change = on_qty_change
            remove_btn = ft.IconButton(icon=ft.Icons.CLOSE, icon_size=16,
                                        on_click=lambda e, it=item: (cart.remove(it), render_cart(), page.update()))
            rows.append(
                ft.Row([
                    ft.Column([
                        ft.Text(p.name, size=13, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Text(f'{price:,.2f} × ' + (' (سعر خاص)' if from_list else ''), size=11, color=theme.PRIMARY if from_list else theme.TEXT_MUTED),
                    ], spacing=0, expand=True),
                    qty_field,
                    ft.Text(f'{line_total:,.2f}', width=70, text_align=ft.TextAlign.END, weight=ft.FontWeight.BOLD),
                    remove_btn,
                ], spacing=6)
            )
        cart_col.controls = rows if rows else [ft.Text('السلة فاضية - دوس على أي صنف لإضافته', color=theme.TEXT_MUTED)]
        compute_totals()

    def add_to_cart(product, qty=1):
        for item in cart:
            if item['product'].id == product.id:
                item['qty'] = round(item['qty'] + qty, 3)
                render_cart()
                page.update()
                return
        cart.append({'product': product, 'qty': qty})
        render_cart()
        page.update()

    scan_msg = ft.Text('', size=11, color=theme.TEXT_MUTED)
    items_tab_btn = ft.OutlinedButton('الأصناف', icon=ft.Icons.GRID_VIEW)      # موبايل فقط
    cart_tab_btn = ft.OutlinedButton('السلة', icon=ft.Icons.SHOPPING_CART_OUTLINED)

    def focus_search():
        try:
            page.run_task(search.focus)
        except Exception:
            pass

    def on_scan(e=None):
        """Enter في خانة البحث (قارئ الباركود بيكتب الكود ويضغط Enter): تطابق تام باركود/كود -> يضيف للسلة، وإلا يفضل الفلتر."""
        code = (search.value or '').strip()
        if not code:
            return
        try:
            hit = services.scan_lookup(code)
        except ValueError as ex:
            scan_msg.value = str(ex); scan_msg.color = theme.DANGER; search.value = ''
            focus_search(); page.update(); return
        except Exception as ex:
            if not _is_down(ex):
                raise
            hit = offline.find(code)
            update_offline_bar()
            if not hit:
                scan_msg.value = 'مفيش اتصال والصنف مش في النسخة المحلية'; scan_msg.color = theme.DANGER; search.value = ''
                focus_search(); page.update(); return
        if hit:
            prod = hit['product']
            add_to_cart(prod, hit['qty'])
            search.value = ''
            scan_msg.value = f"أُضيف: {prod.name}" + (f"  ({hit['info']})" if hit['info'] else '')
            scan_msg.color = theme.SUCCESS
            render_products()
        else:
            try:
                found = [p for p in services.list_products(search=code) if p.can_be_sold]
            except Exception as ex:
                if not _is_down(ex):
                    raise
                found = offline.search(code)
            if len(found) == 1:                       # نتيجة وحيدة -> أضفها مباشرة
                add_to_cart(found[0]); search.value = ''; scan_msg.value = f"أُضيف: {found[0].name}"; scan_msg.color = theme.SUCCESS; render_products()
            else:
                scan_msg.value = 'لا يوجد صنف بهذا الباركود/الكود' if not found else f'{len(found)} صنف مطابق - اختر من القائمة'
                scan_msg.color = theme.DANGER if not found else theme.TEXT_MUTED
        focus_search()
        page.update()

    def render_group_buttons():
        def select_group(gid):
            active_group['id'] = gid
            render_group_buttons()
            render_products()

        buttons = [
            ft.Container(
                content=ft.Text('الكل', size=13, weight=ft.FontWeight.BOLD, color='#FFFFFF' if active_group['id'] is None else theme.TEXT_MUTED),
                bgcolor=theme.PRIMARY if active_group['id'] is None else theme.SURFACE_ALT,
                border_radius=18, padding=ft.Padding(left=16, right=16, top=8, bottom=8),
                ink=True, on_click=lambda e: select_group(None),
            )
        ]
        for g in pos_groups:
            is_active = active_group['id'] == g.id
            buttons.append(
                ft.Container(
                    content=ft.Text(g.name, size=13, weight=ft.FontWeight.BOLD, color='#FFFFFF' if is_active else theme.TEXT_MUTED),
                    bgcolor=(g.color or theme.PRIMARY) if is_active else theme.SURFACE_ALT,
                    border_radius=18, padding=ft.Padding(left=16, right=16, top=8, bottom=8),
                    ink=True, on_click=lambda e, gid=g.id: select_group(gid),
                )
            )
        group_buttons_row.controls = buttons

    def render_products(e=None):
        try:
            _render_products_online(e)
        except Exception as ex:
            if not _is_down(ex):
                raise
            _render_products_tiles(offline.search(search.value), e)
        update_offline_bar()

    def _render_products_online(e):
        if active_group['id'] is not None:
            group_products = services.list_products_in_pos_group(active_group['id'])
            products = [p for p in group_products if p.can_be_sold]
            if search.value:
                needle = search.value.strip().lower()
                products = [p for p in products if needle in p.name.lower() or needle in p.sku.lower()]
        else:
            products = [p for p in services.list_products(search=search.value or None) if p.can_be_sold]
        off['down'] = False
        _render_products_tiles(products, e)

    def _render_products_tiles(products, e):
        tiles = []
        for p in products[:60]:
            import os as _os
            if p.image_path and _os.path.exists(p.image_path):
                thumb = ft.Container(
                    content=ft.Image(src=p.image_path, width=64, height=64, fit=ft.BoxFit.COVER, border_radius=10),
                    border_radius=10,
                )
            else:
                thumb = ft.Container(
                    content=ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, size=32, color=theme.PRIMARY),
                    bgcolor=ft.Colors.with_opacity(0.08, theme.PRIMARY), border_radius=10,
                    padding=14, alignment=ft.Alignment(0, 0),
                )
            tiles.append(
                ft.Container(
                    content=ft.Column(
                        [
                            thumb,
                            ft.Text(p.name, size=12, weight=ft.FontWeight.BOLD, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, text_align=ft.TextAlign.CENTER),
                            ft.Text(f'{p.sale_price:,.2f} ر.س', size=12, color=theme.PRIMARY, weight=ft.FontWeight.BOLD),
                        ],
                        spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=8, border_radius=10, bgcolor=theme.CARD_BG,
                    border=ft.border.Border(
                        top=ft.border.BorderSide(1, theme.BORDER_LIGHT), right=ft.border.BorderSide(1, theme.BORDER_LIGHT),
                        bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT), left=ft.border.BorderSide(1, theme.BORDER_LIGHT),
                    ),
                    ink=True, on_click=lambda e, prod=p: add_to_cart(prod),
                )
            )
        products_grid.controls = tiles
        if e is not None:
            page.update()

    search.on_change = render_products
    search.on_submit = on_scan

    def apply_terminal(e=None):
        """تطبيق إعدادات الماكينة المختارة على الشاشة: طرق الدفع المسموحة، العميل الافتراضي، وسطر بيانات الماكينة."""
        t = next((x for x in terminals if str(x['id']) == (terminal_dd.value or '')), None)
        current_terminal['t'] = t
        if not t:
            return
        allowed = [m for m in t['payment_methods']]
        payment_dd.options = [ft.dropdown.Option(str(m['id']), m['name']) for m in allowed]
        payment_dd.value = str(t['default_payment_method_id']) if t['default_payment_method_id'] in [m['id'] for m in allowed] else (str(allowed[0]['id']) if allowed else None)
        if t['default_customer_id']:
            customer_dd.value = str(t['default_customer_id'])
        customer_dd.disabled = bool(t['lock_customer'])
        sync_pay_ref()
        parts = [f"الفرع: {t['branch']}" if t['branch'] else '', f"المخزن: {t['location']}" if t['location'] else '', f"مركز التكلفة: {t['cost_center']}" if t['cost_center'] else '',
                 f"الكاشير: {t['employee']}" if t['employee'] else '']
        terminal_info.value = '  |  '.join(p for p in parts if p) or 'الماكينة من غير فرع/مخزن محدد (الافتراضي)'
        terminal_info.color = theme.TEXT_MUTED
        render_cart()
        try:
            page.update()
        except Exception:
            pass
    def refresh_session(prompt=False):
        """تحديث شريط الجلسة للماكينة المختارة؛ لو مفيش جلسة مفتوحة (prompt=True) بيطلب فتح جلسة جديدة."""
        t = current_terminal['t']
        session_bar.visible = bool(t)
        if not t:
            return
        try:
            s_ = services.get_open_pos_session(t['id'])
            session['s'] = s_
            me = services.current_user() or {}
            tot = services.pos_session_totals(s_['id']) if s_ else None
        except Exception as ex:
            if not _is_down(ex):
                raise
            update_offline_bar()
            session_text.value = 'مفيش اتصال بالسيرفر - الجلسة آخر حالة معروفة'; session_text.color = theme.WARNING
            try:
                page.update()
            except Exception:
                pass
            return
        off['down'] = False
        update_offline_bar()
        if s_:
            mine = me.get('role') == 'admin' or s_['opened_by'] == me.get('username')
            session_text.value = f"الجلسة {s_['number']}  •  منذ {s_['opened_at']:%Y-%m-%d %H:%M}  •  {tot['count']} فاتورة  •  {tot['total']:,.2f}" + ('' if mine else f"  •  مفتوحة بواسطة {s_['opened_by_name']}")
            session_text.color = theme.SUCCESS if mine else theme.DANGER
            session_bar.bgcolor = ft.Colors.with_opacity(0.08, theme.SUCCESS if mine else theme.DANGER)
            session_report_btn.visible = True; session_close_btn.visible = mine; session_open_btn.visible = False
        else:
            session_text.value = 'مفيش جلسة مفتوحة على الماكينة دي - افتح جلسة عشان تبدأ البيع'
            session_text.color = theme.DANGER; session_bar.bgcolor = ft.Colors.with_opacity(0.08, theme.DANGER)
            session_report_btn.visible = False; session_close_btn.visible = False; session_open_btn.visible = True
        try:
            page.update()
        except Exception:
            pass
        if prompt and not s_:
            prompt_open_session()

    def prompt_open_session():
        t = current_terminal['t']
        if t:
            open_session_dialog(page, t, on_done=lambda sid: refresh_session())

    def close_current_session():
        if session['s']:
            def done(rep):
                refresh_session()
                session_report_dialog(page, rep['id'], on_changed=lambda: refresh_session())
            close_session_dialog(page, session['s']['id'], on_done=done)

    _apply = apply_terminal
    def apply_terminal_and_session(e=None):
        _apply(e)
        refresh_session(prompt=True)
    terminal_dd.on_change = apply_terminal_and_session
    if terminals:
        _apply()
        refresh_session(prompt=True)
    customer_dd.on_change = lambda e: (render_cart(), disc_recalc(), page.update())
    render_group_buttons()

    def clear_sale():
        cart.clear()
        render_cart()

    def show_offline_receipt(rec, items):
        names = {}
        try:
            snap = offline.load_snapshot() or {}
            names = {p['id']: p['name'] for p in snap.get('products', [])}
        except Exception:
            pass
        content = ft.Container(width=360, content=ft.Column([
            ft.Text(settings.name or 'اسم الشركة', size=18, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
            ft.Container(content=ft.Text('إيصال مؤقت - بدون اتصال', color='#FFFFFF', weight=ft.FontWeight.BOLD, size=12), bgcolor=theme.WARNING, border_radius=8, padding=ft.Padding(left=10, right=10, top=3, bottom=3)),
            ft.Divider(), ft.Text(f"رقم مؤقت: {rec['number']}", weight=ft.FontWeight.BOLD), ft.Text(f"التاريخ: {rec['at'].replace('T', ' ')}"),
            ft.Divider(),
            *[ft.Row([ft.Text(f"{it['quantity']:g} × {names.get(it['product_id'], it['product_id'])}", size=13), ft.Container(expand=True), ft.Text(f"{it['quantity'] * it['unit_price']:,.2f}", size=13)]) for it in items],
            ft.Divider(),
            ft.Row([ft.Text('قبل الضريبة'), ft.Container(expand=True), ft.Text(f"{rec['subtotal']:,.2f}")]),
            ft.Row([ft.Text('الضريبة'), ft.Container(expand=True), ft.Text(f"{rec['tax']:,.2f}")]),
            ft.Row([ft.Text('الإجمالي', weight=ft.FontWeight.BOLD), ft.Container(expand=True), ft.Text(f"{rec['total']:,.2f}", weight=ft.FontWeight.BOLD, size=18)]),
            ft.Text('دفع نقدي. الفاتورة الضريبية الرسمية (برقمها وQR) بتتولّد تلقائي أول ما الاتصال يرجع.', size=11.5, color=theme.TEXT_MUTED, text_align=ft.TextAlign.CENTER),
        ], spacing=6, tight=True, scroll=ft.ScrollMode.AUTO, horizontal_alignment=ft.CrossAxisAlignment.CENTER))
        for _c in content.content.controls:         # صفوف (عنوان — قيمة) ما تتفكّكش على الموبايل
            if isinstance(_c, ft.Row):
                _c._erp_nowrap = True
        dlg = ft.AlertDialog(modal=True, content=content, actions=[ft.FilledButton('تمام', on_click=lambda e: (setattr(dlg, 'open', False), focus_search(), page.update()))])
        page.overlay.append(dlg); dlg.open = True; page.update()

    def show_receipt(result, invoice, receipt_t=None):
        qr_control = (
            ft.Image(src=base64.b64decode(result['qr_png_base64']), width=170, height=170)
            if result['qr_png_base64'] else ft.Text('تعذر توليد QR')
        )
        zatca = result['zatca']
        pay_rows = services.get_invoice_payments(invoice.id)
        loy = (result.get('loyalty') or None)
        loy = loy if loy and (loy.get('earned') or loy.get('redeemed')) else None
        zatca_colors = {'pending': theme.WARNING, 'sent': theme.SUCCESS, 'disabled': theme.TEXT_MUTED, 'failed': theme.DANGER}
        zatca_labels = {'pending': 'موقّعة - بتتبعت لمنصة فاتورة', 'sent': 'تم الإرسال لمنصة فاتورة بنجاح', 'disabled': 'الربط مع الزكاة غير مفعّل', 'failed': 'تعذر الإرسال لمنصة فاتورة'}

        content = ft.Container(
            width=380,
            content=ft.Column(
                [
                    ft.Text(settings.name or 'اسم الشركة', size=18, weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER),
                    ft.Text(f'الرقم الضريبي: {settings.vat_number or "-"}', size=12, color=theme.TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                    ft.Divider(),
                    ft.Text(f'فاتورة رقم: {invoice.number}', weight=ft.FontWeight.BOLD),
                    ft.Text(f'التاريخ: {invoice.date.strftime("%Y-%m-%d %H:%M")}'),
                    ft.Text(f'العميل: {invoice.customer.name if invoice.customer else "-"}'),
                    *([ft.Text(f"الماكينة: {receipt_t['code']} - {receipt_t['name']}" + (f" | الكاشير: {receipt_t['employee']}" if receipt_t['employee'] else ''), size=12, color=theme.TEXT_MUTED)] if receipt_t else []),
                    ft.Divider(),
                    ft.Row([ft.Text('الإجمالي قبل الضريبة'), ft.Container(expand=True), ft.Text(f'{invoice.subtotal:,.2f}')]),
                    ft.Row([ft.Text('ضريبة القيمة المضافة'), ft.Container(expand=True), ft.Text(f'{invoice.tax_total:,.2f}')]),
                    ft.Row([ft.Text('الإجمالي', weight=ft.FontWeight.BOLD), ft.Container(expand=True), ft.Text(f'{invoice.total:,.2f}', weight=ft.FontWeight.BOLD, size=18)]),
                    *([ft.Text('طرق السداد', weight=ft.FontWeight.BOLD, size=13)] if len(pay_rows) > 1 or (pay_rows and pay_rows[0]['change']) else []),
                    *[ft.Row([ft.Text(p_['name'] + (' (مستلم ' + format(p_['tendered'], ',.2f') + ')' if p_['tendered'] and p_['change'] else '')), ft.Container(expand=True), ft.Text(f"{p_['amount']:,.2f}")]) for p_ in pay_rows if len(pay_rows) > 1 or p_['change']],
                    *([ft.Row([ft.Text('الباقي للعميل'), ft.Container(expand=True), ft.Text(f"{sum(p_['change'] for p_ in pay_rows):,.2f}", weight=ft.FontWeight.BOLD)])] if any(p_['change'] for p_ in pay_rows) else []),
                    *([ft.Text(f"نقاط الولاء: +{loy['earned']:,.0f}" + (f" / -{loy['redeemed']:,.0f}" if loy.get('redeemed') else '') + f" | الرصيد {loy['balance']:,.0f}", size=12, color=theme.PRIMARY)] if loy else []),
                    ft.Divider(),
                    ft.Container(content=qr_control, alignment=ft.Alignment(0, 0)),
                    ft.Container(
                        content=ft.Text(zatca_labels.get(zatca['status'], zatca['status']), color=zatca_colors.get(zatca['status'], theme.TEXT_MUTED), text_align=ft.TextAlign.CENTER, size=12),
                        alignment=ft.Alignment(0, 0),
                    ),
                    *([ft.Text(receipt_t['receipt_footer'], size=12, text_align=ft.TextAlign.CENTER)] if receipt_t and receipt_t['receipt_footer'] else []),
                ],
                spacing=6, tight=True, scroll=ft.ScrollMode.AUTO, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        def close_receipt(e):
            dialog.open = False
            page.update()

        share_status = ft.Text('', size=11, visible=False)

        printed = {'n': 0}

        def do_print(e=None):
            try:
                if thermal.is_enabled('receipt'):
                    ok, msg = thermal.print_receipt(invoice.id, reprint=printed['n'] > 0)
                    share_status.value = 'تمت طباعة الإيصال' if ok else msg
                    share_status.color = theme.SUCCESS if ok else theme.DANGER
                    share_status.visible = True
                    if ok:
                        printed['n'] += 1
                        try: page.update()
                        except Exception: pass
                        return
                    page.update()
                path = services.generate_invoice_pdf_file(invoice.id)
                theme.open_or_download_file(page, path)
            except Exception as ex:
                share_status.value = f'تعذرت الطباعة: {ex}'
                share_status.color = theme.DANGER
                share_status.visible = True
                page.update()

        def do_email(e):
            default_email = invoice.customer.email if invoice.customer else ''
            email_field = ft.TextField(label='البريد الإلكتروني', value=default_email or '', width=320)
            send_err = ft.Text('', color=theme.DANGER, visible=False)

            def send(ev):
                try:
                    services.email_invoice(invoice.id, email_field.value)
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
                services.generate_invoice_pdf_file(invoice.id)
                phone = invoice.customer.phone if invoice.customer else ''
                link = services.whatsapp_share_link(phone, invoice.number, invoice.total)
                theme.launch_url(page, link)
                share_status.value = 'فُتح واتساب - الملف محفوظ في مجلد exports لإرفاقه يدوياً (واتساب مايسمحش بإرفاق ملفات عن طريق الرابط مباشرة)'
                share_status.color = theme.TEXT_MUTED
                share_status.visible = True
            except Exception as ex:
                share_status.value = str(ex)
                share_status.color = theme.DANGER
                share_status.visible = True
            page.update()

        share_btns = [
            ft.IconButton(icon=ft.Icons.PRINT_OUTLINED, tooltip='طباعة', on_click=do_print),
            ft.IconButton(icon=ft.Icons.EMAIL_OUTLINED, tooltip='إرسال بالإيميل', on_click=do_email),
            ft.IconButton(icon=ft.Icons.CHAT_OUTLINED, tooltip='إرسال واتساب', on_click=do_whatsapp),
        ]
        done_btn = ft.FilledButton('إتمام - بيع جديد', bgcolor=theme.PRIMARY, on_click=close_receipt)
        for _c in content.content.controls:         # صفوف (عنوان — قيمة) ما تتفكّكش على الموبايل
            if isinstance(_c, ft.Row):
                _c._erp_nowrap = True
        if theme._page_w():       # موبايل: الأيقونات في صف جوه المحتوى والزر لوحده (الأزرار الأربعة مش بتتّسع جنب بعض)
            dialog = ft.AlertDialog(
                modal=True, title=ft.Text('الفاتورة الضريبية'),
                content=ft.Column([content, share_status, ft.Row(share_btns, alignment=ft.MainAxisAlignment.CENTER)], tight=True, spacing=8),
                actions=[done_btn], actions_alignment=ft.MainAxisAlignment.END,
            )
        else:
            dialog = ft.AlertDialog(
                modal=True, title=ft.Text('الفاتورة الضريبية'),
                content=ft.Column([content, share_status], tight=True, spacing=8),
                actions=share_btns + [done_btn],
                actions_alignment=ft.MainAxisAlignment.START,
            )
        page.overlay.append(dialog)
        dialog.open = True
        page.update()
        if thermal.is_enabled('receipt') and thermal.get_config()['receipt']['auto']:
            ok, msg = thermal.print_receipt(invoice.id)
            printed['n'] += 1 if ok else 0
            share_status.value = 'تمت طباعة الإيصال تلقائيًا' if ok else msg
            share_status.color = theme.SUCCESS if ok else theme.DANGER
            share_status.visible = True
            page.update()

    def _gross_total():
        try:
            return round(float((total_text.value or '0').replace(',', '')), 2)
        except ValueError:
            return 0.0

    def _cart_total():
        """الإجمالي النهائي المطلوب دفعه (بعد خصم/كوبون السلة لو فيه)."""
        return round(max(0.0, _gross_total() - disc_state['amount']), 2)

    disc_ctrl, disc_spec, disc_recalc, disc_state, disc_reset = discount_box(page, _gross_total, get_customer=lambda: customer_dd.value)

    def open_split_dialog(e):
        """سداد متعدد: الفاتورة تتقسم على أكتر من طريقة دفع (نقدي + شبكة + آجل...). المتبقي بيتحسب لحظيًا، والنقدي الزايد بيطلع باقي للعميل."""
        if not cart:
            err.value = 'السلة فاضية - أضف أصناف الأول'; err.visible = True; page.update(); return
        total = _cart_total()
        t = current_terminal['t']
        allowed_ids = [m['id'] for m in t['payment_methods']] if t else [m.id for m in all_payment_methods]
        methods = [m for m in all_payment_methods if m.id in allowed_ids]
        fields, refs = {}, {}
        remaining_t = ft.Text('', weight=ft.FontWeight.BOLD, size=15)
        dlg_err = ft.Text('', color=theme.DANGER, visible=False)

        def compute():
            """يرجّع (payments, paid_applied, change) من القيم المكتوبة: غير النقدي بالظبط، والنقدي بياخد الباقي والزايادة باقي."""
            vals = {}
            for m in methods:
                try:
                    v = float((fields[m.id].value or '0').replace(',', ''))
                except ValueError:
                    v = 0.0
                vals[m.id] = max(0.0, round(v, 2))
            rest = total
            pays = []
            for m in [x for x in methods if not services.pm_is_cash(x)]:
                if vals[m.id] > 0:
                    pays.append({'payment_method_id': m.id, 'amount': vals[m.id], 'reference': refs[m.id].value or ''})
                    rest = round(rest - vals[m.id], 2)
            change = 0.0
            for m in [x for x in methods if services.pm_is_cash(x)]:
                if vals[m.id] <= 0:
                    continue
                applied = min(vals[m.id], max(0.0, rest))
                if vals[m.id] > applied + 1e-9:
                    change += vals[m.id] - applied
                pays.append({'payment_method_id': m.id, 'amount': round(applied, 2), 'tendered': vals[m.id], 'reference': ''})
                rest = round(rest - applied, 2)
            return pays, rest, round(change, 2)

        def refresh(ev=None):
            pays, rest, change = compute()
            if rest > 0.005:
                remaining_t.value = f'المتبقي: {rest:,.2f}'; remaining_t.color = theme.DANGER
            elif rest < -0.005:
                remaining_t.value = f'زيادة غير مسموحة: {-rest:,.2f}'; remaining_t.color = theme.DANGER
            else:
                remaining_t.value = 'تم السداد بالكامل' + (f' - الباقي للعميل: {change:,.2f}' if change else ''); remaining_t.color = theme.SUCCESS
            page.update()

        def fill_rest(m):
            def _f(ev):
                pays, rest, _ = compute()
                try:
                    cur = float((fields[m.id].value or '0').replace(',', ''))
                except ValueError:
                    cur = 0.0
                if rest > 0:
                    fields[m.id].value = f'{cur + rest:.2f}'
                refresh()
            return _f

        rows = []
        for m in methods:
            fields[m.id] = ft.TextField(label=m.name + (' (آجل)' if m.is_credit else ''), width=190, keyboard_type=ft.KeyboardType.NUMBER, on_change=refresh, text_align=ft.TextAlign.RIGHT)
            refs[m.id] = ft.TextField(label='مرجع العملية', width=130, visible=not (services.pm_is_cash(m) or m.is_credit), dense=True)
            if theme._page_w():       # موبايل: المبلغ بعرض كامل، وتحته المرجع وزر «المتبقي»
                fields[m.id].width = max(200, theme._page_w() - 110)
                refs[m.id].width = max(140, theme._page_w() - 230)
                rows.append(ft.Column([fields[m.id], ft.Row([refs[m.id], ft.TextButton('المتبقي', on_click=fill_rest(m))], spacing=6)], spacing=4))
            else:
                rows.append(ft.Row([fields[m.id], refs[m.id], ft.TextButton('المتبقي', on_click=fill_rest(m))], spacing=6))

        def confirm(ev):
            pays, rest, _ = compute()
            if abs(rest) > 0.005:
                dlg_err.value = 'مجموع السداد لازم يساوي إجمالي الفاتورة'; dlg_err.visible = True; page.update(); return
            dlg.open = False
            page.update()
            checkout(None, payments=pays)

        dlg = ft.AlertDialog(
            modal=True, title=ft.Text(f'سداد متعدد - الإجمالي {total:,.2f}'),
            content=ft.Column([ft.Text('وزّع إجمالي الفاتورة على طرق الدفع. النقدي لو أكبر من المتبقي الزيادة بتتحسب باقي للعميل.', size=12, color=theme.TEXT_MUTED), *rows, remaining_t, dlg_err], tight=True, spacing=8, width=480, scroll=ft.ScrollMode.AUTO),
            actions=[ft.TextButton('إلغاء', on_click=lambda ev: (setattr(dlg, 'open', False), page.update())), ft.FilledButton('تأكيد السداد وإتمام البيع', bgcolor=theme.PRIMARY, on_click=confirm)],
        )
        remaining_t.value = f'المتبقي: {total:,.2f}'; remaining_t.color = theme.DANGER
        page.overlay.append(dlg); dlg.open = True; page.update()

    def open_customers_split_dialog(e):
        """تقسيم الفاتورة على أكتر من عميل: كل عميل بياخد كميات من أصناف السلة وطريقة دفعه، وبيطلع له فاتورة مستقلة."""
        if not cart:
            err.value = 'السلة فاضية - أضف أصناف الأول'; err.visible = True; page.update(); return
        t = current_terminal['t']
        if any_terminals and not t:
            err.value = 'مفيش ماكينة كاشير متاحة ليك - مينفعش تتم البيع'; err.visible = True; page.update(); return
        if t and not session['s']:
            prompt_open_session(); err.value = 'افتح جلسة للماكينة الأول'; err.visible = True; page.update(); return
        allowed_ids = [m['id'] for m in t['payment_methods']] if t else [m.id for m in all_payment_methods]
        methods = [m for m in all_payment_methods if m.id in allowed_ids]
        parts = []   # [{'cust': Dropdown, 'pay': Dropdown, 'qty': {cart_index: TextField}, 'total': Text}]
        body_col = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
        status_t = ft.Text('', size=13, weight=ft.FontWeight.BOLD)
        dlg_err = ft.Text('', color=theme.DANGER, visible=False)

        def _num(f):
            try:
                return max(0.0, float((f.value or '0').replace(',', '')))
            except ValueError:
                return 0.0

        def part_items(pt):
            cid = int(pt['cust'].value) if pt['cust'].value else None
            out = []
            for i, item in enumerate(cart):
                q = _num(pt['qty'][i])
                if q > 0:
                    price, _ = services.get_customer_product_price(cid, item['product'].id)
                    out.append({'product_id': item['product'].id, 'quantity': q, 'unit_price': price, 'tax_rate': item['product'].tax_rate or settings.default_tax_rate or 15})
            return out

        def part_total(pt):
            gross = sum(x['quantity'] * x['unit_price'] * (1 + x['tax_rate'] / 100.0) for x in part_items(pt))
            return round(max(0.0, gross - _num(pt['disc'])), 2)

        def toggle_split(pt):
            def _t(ev):
                pt['mbox'].visible = bool(pt['split'].value); pt['pay'].disabled = bool(pt['split'].value)
                refresh()
            return _t

        def fill_rest_pt(pt, mid):
            def _f(ev):
                rest = round(part_total(pt) - sum(_num(f) for f in pt['mamt'].values()), 2)
                if rest > 0:
                    pt['mamt'][mid].value = f"{_num(pt['mamt'][mid]) + rest:.2f}"
                refresh()
            return _f

        def refresh(ev=None):
            ok = True; msgs = []
            for i, item in enumerate(cart):
                got = sum(_num(pt['qty'][i]) for pt in parts)
                if abs(got - item['qty']) > 1e-6:
                    ok = False; msgs.append(f"{item['product'].name}: الموزع {got:g} من {item['qty']:g}")
            for pt in parts:
                tot = part_total(pt)
                pt['total'].value = f'الإجمالي: {tot:,.2f}'
                if pt['split'].value:
                    paid = sum(_num(f) for f in pt['mamt'].values())
                    rest = round(tot - paid, 2)
                    pt['rest'].value = f'المتبقي: {rest:,.2f}' if abs(rest) > 0.005 else 'تم السداد'
                    pt['rest'].color = theme.DANGER if abs(rest) > 0.005 else theme.SUCCESS
            status_t.value = 'التوزيع مكتمل' if ok else ' | '.join(msgs); status_t.color = theme.SUCCESS if ok else theme.DANGER
            page.update()

        def even_split(ev):
            n = len(parts)
            for i, item in enumerate(cart):
                share = round(item['qty'] / n, 3)
                for k, pt in enumerate(parts):
                    pt['qty'][i].value = f"{(item['qty'] - share * (n - 1)) if k == 0 else share:g}"
            refresh()

        def add_part(ev=None):
            idx = len(parts) + 1
            pt = {'qty': {}}
            pt['cust'] = ft.Dropdown(label=f'العميل {idx}', width=220, options=[ft.dropdown.Option(str(c.id), c.name) for c in customers], value=customer_dd.value if idx == 1 else None)
            pt['pay'] = ft.Dropdown(label='طريقة الدفع', width=180, options=[ft.dropdown.Option(str(m.id), m.name) for m in methods], value=payment_dd.value if payment_dd.value and int(payment_dd.value) in allowed_ids else (str(methods[0].id) if methods else None))
            pt['total'] = ft.Text('الإجمالي: 0.00', size=12, color=theme.TEXT_MUTED)
            pt['disc'] = ft.TextField(label='خصم', width=90, dense=True, value='0', keyboard_type=ft.KeyboardType.NUMBER, on_change=refresh, text_align=ft.TextAlign.RIGHT)
            pt['split'] = ft.Checkbox(label='تقسيم الدفع', value=False)
            pt['split'].on_change = toggle_split(pt)
            pt['rest'] = ft.Text('', size=12, weight=ft.FontWeight.BOLD)
            pt['mamt'] = {}
            mrows = []
            for m in methods:
                pt['mamt'][m.id] = ft.TextField(label=m.name, width=150, dense=True, keyboard_type=ft.KeyboardType.NUMBER, on_change=refresh, text_align=ft.TextAlign.RIGHT)
                mrows.append(ft.Row([pt['mamt'][m.id], ft.TextButton('المتبقي', on_click=fill_rest_pt(pt, m.id))], spacing=2))
            pt['mbox'] = ft.Row([*mrows, pt['rest']], spacing=8, wrap=True, visible=False)
            qrows = []
            for i, item in enumerate(cart):
                pt['qty'][i] = ft.TextField(label=item['product'].name, width=130, dense=True, value=f"{item['qty']:g}" if idx == 1 else '0', keyboard_type=ft.KeyboardType.NUMBER, on_change=refresh, text_align=ft.TextAlign.RIGHT)
                qrows.append(pt['qty'][i])
            parts.append(pt)
            body_col.controls.append(theme.card(ft.Column([ft.Row([pt['cust'], pt['pay'], pt['disc'], pt['split'], pt['total']], spacing=8, run_spacing=10, wrap=True), pt['mbox'], ft.Container(ft.Row(qrows, spacing=6, run_spacing=12, wrap=True), padding=ft.Padding(left=0, right=0, top=10, bottom=0))], spacing=8), padding=12))
            if ev is not None:
                refresh()

        def confirm(ev):
            try:
                if not all(pt['cust'].value for pt in parts):
                    raise ValueError('اختر العميل لكل جزء')
                refresh()
                if status_t.color != theme.SUCCESS:
                    raise ValueError('وزّع كل الكميات بالظبط على العملاء')
                req = []
                for pt in parts:
                    its = part_items(pt)
                    if not its:
                        continue
                    r_ = {'customer_id': int(pt['cust'].value), 'items': its, 'discount': _num(pt['disc'])}
                    if pt['split'].value:
                        r_['payments'] = [{'payment_method_id': mid, 'amount': _num(f)} for mid, f in pt['mamt'].items() if _num(f) > 0]
                    else:
                        r_['payment_method_id'] = int(pt['pay'].value) if pt['pay'].value else None
                    req.append(r_)
                results = services.create_pos_split_sale(req, terminal_id=t['id'] if t else None)
                dlg.open = False
                err.visible = False
                clear_sale()
                page.update()
                for r in reversed(results):
                    show_receipt(r, services.get_sales_invoice(r['invoice_id']), t)
                refresh_session()
            except Exception as ex:
                dlg_err.value = str(ex); dlg_err.visible = True; page.update()

        add_part(); add_part()
        dlg = ft.AlertDialog(
            modal=True, title=ft.Text('تقسيم الفاتورة على عملاء'),
            content=ft.Column([ft.Text('وزّع كميات السلة على العملاء، وكل عميل بيطلع له فاتورة ضريبية مستقلة، وتقدر تحط له خصم أو تقسم دفعه على أكتر من طريقة.', size=12, color=theme.TEXT_MUTED),
                               ft.Row([ft.OutlinedButton('إضافة عميل', icon=ft.Icons.PERSON_ADD, on_click=add_part), ft.OutlinedButton('توزيع بالتساوي', icon=ft.Icons.BALANCE, on_click=even_split)], spacing=8),
                               body_col, status_t, dlg_err], spacing=8, width=860, height=560),
            actions=[ft.TextButton('إلغاء', on_click=lambda ev: (setattr(dlg, 'open', False), page.update())), ft.FilledButton('تأكيد وإصدار الفواتير', bgcolor=theme.PRIMARY, on_click=confirm)],
        )
        page.overlay.append(dlg); dlg.open = True; refresh()

    def checkout(e, payments=None):
        try:
            if not cart:
                raise ValueError('السلة فاضية - أضف أصناف الأول')
            if not customer_dd.value:
                raise ValueError('اختر العميل')
            items = [{'product_id': item['product'].id, 'quantity': item['qty'], 'unit_price': _cart_unit_price(item)[0],
                      'tax_rate': item['product'].tax_rate or settings.default_tax_rate or 15}
                     for item in cart]
            spec = disc_spec()
            if not payments and not payment_dd.value:
                raise ValueError('اختر طريقة الدفع')
            if any_terminals and not current_terminal['t']:
                raise ValueError('مفيش ماكينة كاشير متاحة ليك - مينفعش تتم البيع')
            t = current_terminal['t']
            if t and not session['s']:
                prompt_open_session()
                raise ValueError('افتح جلسة للماكينة الأول')
            if not payments and pay_ref.visible:
                payments = [{'payment_method_id': int(payment_dd.value), 'amount': _cart_total(), 'reference': pay_ref.value}]
            import uuid as _uuid
            cuuid = _uuid.uuid4().hex          # لو الرد ضاع بعد الحفظ، المزامنة مش هتكرر الفاتورة
            try:
                result = services.create_pos_sale(
                    customer_id=int(customer_dd.value), items=items, payment_method_id=(None if payments else int(payment_dd.value)), payments=payments, terminal_id=t['id'] if t else None, discount_spec=spec,
                    client_uuid=cuuid,
                )
                invoice = services.get_sales_invoice(result['invoice_id'])
            except Exception as ex_off:
                if not _is_down(ex_off):
                    raise
                if payments or pay_ref.visible:
                    raise ValueError('مفيش اتصال بالسيرفر - السداد المتعدد/بجهاز الشبكة مش متاح بدون اتصال')
                if spec:
                    raise ValueError('مفيش اتصال بالسيرفر - الخصم والكوبونات مش متاحة بدون اتصال')
                if isinstance(ex_off, Exception) and not offline.load_snapshot():
                    raise ValueError('مفيش اتصال بالسيرفر ومفيش نسخة محلية للأصناف')
                rec = offline.queue_sale(int(customer_dd.value), items, int(payment_dd.value), t['id'] if t else None, client_uuid=cuuid)
                err.visible = False
                disc_reset()
                clear_sale()
                update_offline_bar()
                page.update()
                show_offline_receipt(rec, items)
                return
            if offline.counts()['pending']:
                do_sync(quiet=True)
            off['down'] = False
            update_offline_bar()
            err.visible = False
            pay_ref.value = ''
            disc_reset()
            clear_sale()
            page.update()
            show_receipt(result, invoice, t)
            refresh_session()
        except Exception as ex:
            err.value = str(ex)
            err.visible = True
            page.update()
            approval_prompt(page, ex)

    render_products()
    render_cart()

    left_panel = ft.Column(
        [
            theme.h_scroll(group_buttons_row),
            ft.Container(height=8),
            ft.Row([search, scan_msg], spacing=12),
            ft.Container(height=8),
            products_grid,
        ],
        expand=2,
    )

    right_panel = theme.card(
        ft.Column(
            [
                ft.Text('السلة', size=18, weight=ft.FontWeight.BOLD),
                terminal_dd, terminal_info, session_bar, offline_bar,
                customer_dd,
                ft.Row([payment_dd, pay_ref, ft.OutlinedButton('سداد متعدد', icon=ft.Icons.CALL_SPLIT, on_click=open_split_dialog, tooltip='تقسيم الفاتورة على أكتر من طريقة دفع'), ft.OutlinedButton('تقسيم على عملاء', icon=ft.Icons.GROUPS, on_click=open_customers_split_dialog, tooltip='فاتورة مستقلة لكل عميل')], spacing=8, wrap=True),
                ft.Divider(),
                cart_col,
                ft.Divider(),
                ft.Row([ft.Text('قبل الضريبة'), ft.Container(expand=True), subtotal_text]),
                ft.Row([ft.Text('الضريبة'), ft.Container(expand=True), tax_text]),
                ft.Row([ft.Text('الإجمالي', weight=ft.FontWeight.BOLD), ft.Container(expand=True), total_text]),
                ft.ExpansionTile(title=ft.Text('خصم / كوبون', size=13), controls=[ft.Container(content=disc_ctrl, padding=ft.Padding(left=8, right=8, top=0, bottom=8))], dense=True) if hasattr(ft, 'ExpansionTile') else disc_ctrl,
                err,
                theme.guard_submit(ft.FilledButton('إتمام البيع', icon=ft.Icons.POINT_OF_SALE, bgcolor=theme.PRIMARY, on_click=checkout, height=50)),
            ],
            spacing=10, expand=True,
        ),
        expand=1,
    )

    def ask_clear_cart():
        if not cart:
            return

        def yes(ev):
            cdlg.open = False
            clear_sale(); disc_reset(); focus_search()
            page.update()
        cdlg = ft.AlertDialog(modal=True, title=ft.Text('تفريغ السلة'), content=ft.Text('مسح كل الأصناف من السلة؟'),
                              actions=[ft.TextButton('تراجع', on_click=lambda ev: (setattr(cdlg, 'open', False), page.update())), ft.FilledButton('تفريغ', bgcolor=theme.DANGER, on_click=yes)])
        page.overlay.append(cdlg); cdlg.open = True; page.update()

    def on_key(e):
        """اختصارات الكاشير: F2 بحث/مسح باركود، F9 إتمام البيع، F8 تفريغ السلة، Esc مسح البحث. بتتجاهل لو فيه نافذة مفتوحة."""
        if any(getattr(c, 'open', False) for c in page.overlay if isinstance(c, ft.AlertDialog)):
            return
        k = e.key
        if k == 'F2':
            focus_search()
        elif k == 'F9':
            checkout(None)
        elif k == 'F8':
            ask_clear_cart()
        elif k == 'Escape':
            search.value = ''; scan_msg.value = ''
            render_products(); focus_search(); page.update()

    page.on_keyboard_event = on_key

    async def _offline_loop():
        tick = 0
        while _GEN['n'] == my_gen:
            await asyncio.sleep(20)
            tick += 1
            try:
                if offline.counts()['pending']:
                    do_sync(quiet=True)
                if tick % 30 == 0:                               # نسخة الأصناف المحلية كل 10 دقايق
                    threading.Thread(target=_snapshot_bg, daemon=True).start()
            except Exception:
                pass
    try:
        update_offline_bar()
        page.run_task(_offline_loop)
    except Exception:
        pass

    if getattr(page, '_erp_compact', False) is True:
        # موبايل: تبويبين (الأصناف / السلة) بدل عمودين جنب بعض
        search.width = None
        search.expand = True
        left_panel.expand = True
        right_panel.expand = True
        right_panel.visible = False

        def show_tab(which):
            left_panel.visible = which == 'items'
            right_panel.visible = which == 'cart'
            items_tab_btn.style = ft.ButtonStyle(bgcolor=theme.PRIMARY if which == 'items' else None, color='#FFFFFF' if which == 'items' else theme.PRIMARY_TEXT)
            cart_tab_btn.style = ft.ButtonStyle(bgcolor=theme.PRIMARY if which == 'cart' else None, color='#FFFFFF' if which == 'cart' else theme.PRIMARY_TEXT)
            page.update()

        items_tab_btn.expand = True
        cart_tab_btn.expand = True
        items_tab_btn.on_click = lambda e: show_tab('items')
        cart_tab_btn.on_click = lambda e: show_tab('cart')
        show_tab('items')
        return ft.Column([
            theme.page_title('نقاط البيع (POS)'),
            ft.Row([items_tab_btn, cart_tab_btn], spacing=8),
            left_panel, right_panel,
        ], expand=True, spacing=8)

    return ft.Column(
        [
            theme.page_title('نقاط البيع (POS)', 'بيع سريع بفاتورة ضريبية وQR فوري  •  F2 بحث / مسح باركود  •  F9 إتمام البيع  •  F8 تفريغ السلة  •  Esc مسح البحث'),
            ft.Container(height=10),
            ft.Row([left_panel, right_panel], expand=True, spacing=16),
        ],
        expand=True,
    )
