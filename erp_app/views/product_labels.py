import flet as ft
from .. import services, theme
from ..asset_labels import PRESETS

_LAST = {'preset': 'thermal_50x30', 'border': False, 'price': True, 'name': True, 'tax': True, 'currency': 'ر.س'}


def build_product_labels(page: ft.Page):
    """طباعة ملصقات الرف: اسم + سعر + باركود. اختار الأصناف وعدد النسخ لكل صنف."""
    services.require_action('product_labels', 'view')
    st = {'rows': [], 'sel': {}}          # sel: product_id -> نسخ (TextField)
    search = ft.TextField(label='بحث بالكود أو الاسم أو الباركود', width=320, prefix_icon=ft.Icons.SEARCH, border_radius=10)
    cat = ft.Dropdown(label='الفئة', width=220, options=[ft.dropdown.Option('', 'كل الفئات')] + [ft.dropdown.Option(str(c.id), c.name) for c in services.list_categories()], value='')
    preset = ft.Dropdown(label='مقاس الملصق', width=330, value=_LAST['preset'], options=[ft.dropdown.Option(k, v['label']) for k, v in PRESETS.items()])
    default_copies = ft.TextField(label='نسخ لكل صنف', width=120, value='1', keyboard_type=ft.KeyboardType.NUMBER)
    slot = ft.TextField(label='ابدأ من الخانة', width=130, value='1', keyboard_type=ft.KeyboardType.NUMBER, visible=PRESETS[_LAST['preset']]['kind'] == 'sheet')
    currency = ft.TextField(label='العملة على الملصق', width=140, value=_LAST['currency'])
    price_sw = ft.Switch(label='السعر', value=_LAST['price'])
    name_sw = ft.Switch(label='الاسم', value=_LAST['name'])
    tax_sw = ft.Switch(label='السعر شامل الضريبة', value=_LAST['tax'])
    border_sw = ft.Switch(label='إطار', value=_LAST['border'])
    info = ft.Text('', size=12, color=theme.TEXT_MUTED)
    body = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)

    def on_preset(e=None):
        slot.visible = PRESETS[preset.value]['kind'] == 'sheet'
        page.update()
    preset.on_change = on_preset

    def checked_ids():
        return [pid for pid, (cb, _) in st['sel'].items() if cb.value]

    def update_info(e=None):
        info.value = f'المحدد: {len(checked_ids())} صنف'
        page.update()

    def load(e=None):
        st['rows'] = services.product_label_rows(search=search.value or None, category_id=int(cat.value) if cat.value else None)
        old = {pid: (cb.value, c.value) for pid, (cb, c) in st['sel'].items()}
        st['sel'] = {}
        lines = []
        for r in st['rows']:
            was = old.get(r['id'], (False, ''))
            cb = ft.Checkbox(value=was[0], on_change=update_info)
            cp = ft.TextField(value=was[1], hint_text='افتراضي', width=80, dense=True, keyboard_type=ft.KeyboardType.NUMBER, text_size=12)
            st['sel'][r['id']] = (cb, cp)
            lines.append(ft.Container(padding=ft.Padding(left=8, right=8, top=2, bottom=2), content=ft.Row([
                cb, ft.Text(r['sku'], width=110, size=12), ft.Text(r['name'], expand=True, size=13),
                ft.Text(r['barcode'] + ('' if r['has_barcode'] else '  (الكود)'), width=170, size=12, color=theme.TEXT_MUTED),
                ft.Text(f"{r['price']:,.2f}", width=80, size=13, weight=ft.FontWeight.BOLD), cp], spacing=8)))
        body.controls = lines or [ft.Text('مفيش أصناف', color=theme.TEXT_MUTED)]
        update_info()

    def select_all(v):
        for cb, _ in st['sel'].values():
            cb.value = v
        update_info()

    def to_int(f, label):
        try:
            return int((f.value or '').strip() or 0)
        except ValueError:
            raise ValueError(f'{label} لازم تكون رقم صحيح')

    def do_print(e):
        try:
            ids = checked_ids()
            if not ids:
                raise ValueError('حدد صنف واحد على الأقل')
            d = to_int(default_copies, 'عدد النسخ') or 1
            entries = [{'product_id': pid, 'copies': to_int(st['sel'][pid][1], 'عدد النسخ') or d} for pid in ids]
            res = services.generate_product_labels_pdf(entries, preset=preset.value, border=border_sw.value, start_slot=to_int(slot, 'رقم الخانة') or 1,
                                                       show_price=price_sw.value, show_name=name_sw.value, currency=(currency.value or '').strip(), price_with_tax=tax_sw.value)
            _LAST.update(preset=preset.value, border=border_sw.value, price=price_sw.value, name=name_sw.value, tax=tax_sw.value, currency=currency.value)
            theme.open_or_download_file(page, res['path'])
            page.overlay.append(ft.SnackBar(ft.Text(f"تم إنشاء {res['count']} ملصق"), open=True))
            page.update()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True, bgcolor=theme.DANGER)); page.update()

    search.on_submit = load
    cat.on_select = load
    load()
    return ft.Column([
        ft.Text('ملصقات الأصناف والأسعار', size=22, weight=ft.FontWeight.BOLD),
        ft.Text('الباركود المطبوع = باركود الصنف (EAN-13 لو صحيح، وإلا Code128 بكود الصنف)، والماسح بيقراه في الكاشير مباشرة.', size=12, color=theme.TEXT_MUTED),
        theme.card(ft.Column([ft.Row([search, cat, ft.OutlinedButton('بحث', on_click=load), ft.TextButton('تحديد الكل', on_click=lambda e: select_all(True)), ft.TextButton('إلغاء التحديد', on_click=lambda e: select_all(False))], wrap=True),
                              ft.Row([preset, default_copies, slot, currency], wrap=True),
                              ft.Row([price_sw, name_sw, tax_sw, border_sw, info,
                                      ft.FilledButton('طباعة', icon=ft.Icons.PRINT_OUTLINED, bgcolor=theme.PRIMARY, on_click=do_print)], wrap=True)], spacing=10), padding=14),
        theme.card(body, padding=6, expand=True),
    ], expand=True, spacing=10)
