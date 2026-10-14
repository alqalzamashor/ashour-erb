import flet as ft
from .. import services, theme
from ._bom_grid import BomLinesGrid

TYPE_LABELS = {'simple': 'عادي', 'kit': 'Kit (باقة تُباع مباشرة)', 'manufactured': 'مُصنَّع (يُنتَج بأمر إنتاج)', 'service': 'خدمة (بدون مخزون)'}
TYPE_COLORS = {'simple': theme.TEXT_MUTED, 'kit': theme.PRIMARY, 'manufactured': theme.WARNING, 'service': theme.SUCCESS}


def build_product_components(page: ft.Page):
    """مكونات الأصناف: فوق اختيار الصنف (أصناف البيع فقط) وخصائصه، وتحت جدول المكونات (مكوّن + وحدة + كمية) بشكل Excel."""
    state = {'products': services.list_products(), 'current': None, 'dirty': False}

    def sellable_options():
        return [(str(p.id), f'{p.sku} - {p.name}') for p in state['products'] if p.can_be_sold]

    product_dd = theme.SearchableDropdown(label='الصنف (أصناف البيع فقط)', width=360, options=sellable_options())
    type_dd = ft.Dropdown(label='نوع الصنف', width=260, options=[ft.dropdown.Option(k, v) for k, v in TYPE_LABELS.items()], value='simple')
    can_be_sold_switch = ft.Switch(label='يمكن بيعه', value=True)
    can_be_purchased_switch = ft.Switch(label='يمكن شراؤه', value=True)
    service_note = ft.Text('صنف الخدمة لا يؤثر على المخزون خالص - بيترحّل مباشرة على حسابات الإيراد (عند البيع) أو المصروف (عند الشراء) من غير أي حركة مخزون.',
                           color=theme.TEXT_MUTED, size=12, visible=False)
    simple_note = ft.Text('الصنف من النوع "عادي": المكونات اللي تحفظها مش بتتستخدم غير لما تحوّله لـ Kit أو مُصنَّع.', color=theme.WARNING, size=12, visible=False)
    save_type_status = ft.Text('', visible=False)
    err = ft.Text('', color=theme.DANGER, visible=False)
    status = ft.Text('', size=12, visible=False)
    summary = ft.Text('', weight=ft.FontWeight.BOLD)
    dirty_label = ft.Text('● تعديلات غير محفوظة', color=theme.WARNING, size=12, weight=ft.FontWeight.BOLD, visible=False)

    def on_grid_change():
        summary_update()
        if state['current'] is not None:
            state['dirty'] = True
            dirty_label.visible = True

    grid = BomLinesGrid(page, on_change=on_grid_change)
    grid.set_products(state['products'])

    def summary_update():
        n, cost = grid.summary()
        summary.value = f'عدد المكونات: {n}   |   إجمالي تكلفة المكونات للوحدة الواحدة: {cost:,.2f}' if n else 'مفيش مكونات لسه - أضف المكوّن الأول من الجدول'

    def selected_product():
        if not product_dd.value:
            return None
        return next((p for p in state['products'] if p.id == int(product_dd.value)), None)

    def load_product(p):
        """تحميل خصائص الصنف ومكوناته في الجدول (من غير تعليم "تعديلات غير محفوظة")."""
        state['current'] = None
        type_dd.value = p.product_type if p else 'simple'
        can_be_sold_switch.value = bool(p.can_be_sold) if p else True
        can_be_purchased_switch.value = bool(p.can_be_purchased) if p else True
        service_note.visible = (type_dd.value == 'service')
        simple_note.visible = bool(p) and type_dd.value == 'simple'
        bom_card.visible = bool(p) and (type_dd.value != 'service')
        save_type_status.visible = err.visible = status.visible = False
        if p:
            grid.set_products([x for x in state['products'] if x.id != p.id])       # الصنف مينفعش يبقى مكوّن لنفسه
            grid.load(services.list_bom_lines(p.id))
        else:
            grid.clear()
        state['current'] = p.id if p else None
        state['dirty'] = False
        dirty_label.visible = False
        summary_update()
        page.update()

    def on_product_change(e=None):
        p = selected_product()
        new_id = p.id if p else None
        if state['dirty'] and state['current'] is not None and new_id != state['current']:
            prev = state['current']
            def stay(ev):
                dlg.open = False
                product_dd.value = str(prev)
                page.update()
            def discard(ev):
                dlg.open = False
                page.update()
                load_product(selected_product())
            dlg = ft.AlertDialog(modal=True, title=ft.Text('تعديلات غير محفوظة'),
                                 content=ft.Text('فيه تعديلات في مكونات الصنف الحالي لسه ما اتحفظتش. لو انتقلت لصنف تاني هتضيع.'),
                                 actions=[ft.TextButton('ابقَ وكمّل', on_click=stay), ft.FilledButton('تجاهل وانتقل', bgcolor=theme.DANGER, on_click=discard)])
            page.overlay.append(dlg); dlg.open = True; page.update()
            return
        load_product(p)

    def on_type_change(e):
        service_note.visible = (type_dd.value == 'service')
        simple_note.visible = bool(selected_product()) and type_dd.value == 'simple'
        bom_card.visible = bool(selected_product()) and (type_dd.value != 'service')
        page.update()

    def save_type(e):
        try:
            p = selected_product()
            if not p:
                raise ValueError('اختر الصنف أولاً')
            services.update_product(p.id, product_type=type_dd.value, can_be_sold=can_be_sold_switch.value, can_be_purchased=can_be_purchased_switch.value)
            state['products'] = services.list_products()
            product_dd.options = sellable_options()          # لو شلت "يمكن بيعه" الصنف بيتشال من القايمة بعد الحفظ
            save_type_status.value = 'تم حفظ إعدادات الصنف بنجاح'
            save_type_status.color = theme.SUCCESS
            save_type_status.visible = True
            simple_note.visible = type_dd.value == 'simple'
        except Exception as ex:
            save_type_status.value = str(ex)
            save_type_status.color = theme.DANGER
            save_type_status.visible = True
        page.update()

    def save_bom(e):
        try:
            p = selected_product()
            if not p:
                raise ValueError('اختر الصنف الأول')
            n = services.save_bom(p.id, grid.get_items())
            err.visible = False
            state['dirty'] = False
            dirty_label.visible = False
            status.value = f'تم حفظ {n} مكوّن' if n else 'تم مسح مكونات الصنف'
            status.color = theme.SUCCESS
            status.visible = True
            grid.load(services.list_bom_lines(p.id)); state['dirty'] = False; dirty_label.visible = False
        except Exception as ex:
            err.value = str(ex)
            err.visible = True
            status.visible = False
        page.update()

    def revert(e):
        p = selected_product()
        if p:
            load_product(p)

    bom_card = theme.card(
        ft.Column([
            ft.Row([ft.Text('مكونات الصنف المحدد', size=16, weight=ft.FontWeight.BOLD), ft.Container(expand=True), dirty_label], spacing=8),
            ft.Text('أضف المكونات في الجدول: اختر المكوّن ثم الوحدة والكمية (لكل وحدة واحدة من الصنف). Enter بينقلك للسطر اللي بعده، وبعد ما تخلّص دوس "حفظ المكونات".', color=theme.TEXT_MUTED, size=12),
            simple_note,
            theme.h_scroll(grid.control),
            summary, err, status,
            ft.Row([theme.guard_submit(ft.FilledButton('حفظ المكونات', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save_bom)),
                    ft.OutlinedButton('تراجع عن التعديلات', icon=ft.Icons.UNDO, on_click=revert)], spacing=10),
        ], spacing=10),
    )
    bom_card.visible = False

    product_dd.on_change = on_product_change
    type_dd.on_change = on_type_change
    summary_update()

    return ft.Column([
        theme.page_title('مكونات الأصناف والخصائص', 'اختر صنف من أصناف البيع، وحدّد نوعه ومكوناته (مكوّن + وحدة + كمية) في الجدول'),
        ft.Container(height=12),
        theme.card(ft.Column([
            ft.Row([product_dd.control, type_dd], wrap=True),
            ft.Row([can_be_sold_switch, can_be_purchased_switch], wrap=True, spacing=24),
            service_note,
            ft.Row([ft.FilledButton('حفظ إعدادات الصنف', icon=ft.Icons.SAVE, bgcolor=theme.PRIMARY, on_click=save_type)], wrap=True),
            save_type_status,
        ], spacing=10)),
        ft.Container(height=16),
        bom_card,
    ], expand=True, scroll=ft.ScrollMode.AUTO)
