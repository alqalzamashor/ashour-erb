import re
import flet as ft
from .. import services, theme
from ..asset_labels import PRESETS

# آخر اختيارات المستخدم (بتفضل طول الجلسة عشان مايعيدش الاختيار كل مرة)
_LAST = {'preset': 'thermal_50x30', 'code_type': 'code128', 'border': False, 'company': True}   # النسخ بترجع 1 كل مرة


def natural_key(code):
    """ترتيب طبيعي للأكواد: LAP-0002 قبل LAP-0010، وبيتجنب مقارنة نص برقم."""
    return tuple(int(x) if x.isdigit() else x for x in re.split(r'(\d+)', str(code or '')))


def open_sticker_dialog(page, asset_ids=None, subtitle='', scope_picker=False, selected_ids=None):
    """نافذة طباعة استيكرات الباركود.
    - asset_ids: قايمة أصول محددة (من صف أو فاتورة).
    - scope_picker=True: المستخدم يختار النطاق (المحدد/الكل/فئة/فاتورة/من كود لكود)."""
    preset_dd = ft.Dropdown(label='مقاس الاستيكر', width=360, value=_LAST['preset'],
                            options=[ft.dropdown.Option(k, v['label']) for k, v in PRESETS.items()])
    type_dd = ft.Dropdown(label='نوع الرمز', width=360, value=_LAST['code_type'], options=[
        ft.dropdown.Option('code128', 'باركود (Code128) - للماسح الضوئي'),
        ft.dropdown.Option('qr', 'QR كود - للموبايل والماسحات الحديثة')])
    copies_f = ft.TextField(label='نسخ لكل أصل', width=140, value='1', keyboard_type=ft.KeyboardType.NUMBER)
    slot_f = ft.TextField(label='ابدأ من الخانة رقم', width=170, value='1', keyboard_type=ft.KeyboardType.NUMBER,
                          visible=PRESETS[_LAST['preset']]['kind'] == 'sheet')
    border_sw = ft.Switch(label='إطار حوالين الاستيكر (للقص على ورق عادي)', value=_LAST['border'])
    company_sw = ft.Switch(label='اسم الشركة على الاستيكر', value=_LAST['company'])
    status = ft.Text('', size=12, visible=False)
    info = ft.Text(subtitle, weight=ft.FontWeight.BOLD, visible=bool(subtitle))

    def on_preset(e=None):
        slot_f.visible = PRESETS[preset_dd.value]['kind'] == 'sheet'
        page.update()
    preset_dd.on_change = on_preset

    # ---------- اختيار النطاق ----------
    scope_controls = []
    resolve = None
    if scope_picker:
        sel = selected_ids() if selected_ids else set()
        scope_dd = ft.Dropdown(label='النطاق', width=360, value='selected' if sel else 'all', options=[
            ft.dropdown.Option('selected', f'الأصول المحددة في الجدول ({len(sel)})'),
            ft.dropdown.Option('all', 'كل الأصول (غير المستبعدة)'),
            ft.dropdown.Option('category', 'أصول فئة معيّنة'),
            ft.dropdown.Option('invoice', 'أصول فاتورة مشتريات'),
            ft.dropdown.Option('range', 'من كود إلى كود'),
        ])
        cat_dd = ft.Dropdown(label='الفئة', width=360, visible=False,
                             options=[ft.dropdown.Option(str(c.id), c.name) for c in services.list_asset_categories()])
        inv_dd = ft.Dropdown(label='فاتورة المشتريات', width=360, visible=False, options=[
            ft.dropdown.Option(str(i.id), f'{i.number} - {i.supplier.name if i.supplier else "-"} ({len(a)} أصل)')
            for i, a in services.list_asset_purchase_invoices()])
        from_f = ft.TextField(label='من كود', width=170, visible=False)
        to_f = ft.TextField(label='إلى كود', width=170, visible=False)

        def on_scope(e=None):
            cat_dd.visible = scope_dd.value == 'category'
            inv_dd.visible = scope_dd.value == 'invoice'
            from_f.visible = to_f.visible = scope_dd.value == 'range'
            page.update()
        scope_dd.on_change = on_scope
        scope_controls = [scope_dd, cat_dd, inv_dd, ft.Row([from_f, to_f], wrap=True)]

        def resolve():
            assets = services.list_fixed_assets()
            sc = scope_dd.value
            if sc == 'selected':
                ids = [a.id for a in assets if a.id in (selected_ids() if selected_ids else set())]
            elif sc == 'all':
                ids = [a.id for a in assets if a.state != 'disposed']
            elif sc == 'category':
                if not cat_dd.value:
                    raise ValueError('اختار الفئة')
                ids = [a.id for a in assets if str(a.category_id) == cat_dd.value]
            elif sc == 'invoice':
                if not inv_dd.value:
                    raise ValueError('اختار الفاتورة')
                ids = [a.id for a in assets if str(a.purchase_invoice_id) == inv_dd.value]
            else:
                lo, hi = (from_f.value or '').strip(), (to_f.value or '').strip()
                if not lo or not hi:
                    raise ValueError('اكتب كود البداية وكود النهاية')
                klo, khi = natural_key(lo), natural_key(hi)
                if khi < klo:
                    klo, khi = khi, klo
                ids = [a.id for a in assets if klo <= natural_key(a.code) <= khi]
            if not ids:
                raise ValueError('مفيش أصول في النطاق ده')
            return ids
    else:
        ids_fixed = list(asset_ids or [])

        def resolve():
            return ids_fixed

    def to_int(field, label):
        try:
            return int((field.value or '').strip() or 0)
        except ValueError:
            raise ValueError(f'{label} لازم تكون رقم صحيح')

    def do_print(e):
        try:
            ids = resolve()
            res = services.generate_asset_stickers_pdf(
                ids, preset=preset_dd.value, code_type=type_dd.value, copies=to_int(copies_f, 'عدد النسخ') or 1,
                border=border_sw.value, start_slot=to_int(slot_f, 'رقم الخانة') or 1, include_company=company_sw.value)
            _LAST.update(preset=preset_dd.value, code_type=type_dd.value, border=border_sw.value, company=company_sw.value)
            theme.open_or_download_file(page, res['path'])
            msg = f"تم إنشاء {res['count']} استيكر"
            if res['qr_fallback']:
                msg += f" — {len(res['qr_fallback'])} كود فيه حروف عربية اتطبع QR بدل الباركود"
            if res['warnings']:
                msg += ' — تنبيه: ' + '؛ '.join(res['warnings'])
            dialog.open = False
            page.overlay.append(ft.SnackBar(ft.Text(msg), open=True))
            page.update()
        except Exception as ex:
            status.value = str(ex); status.color = theme.DANGER; status.visible = True
            page.update()

    dialog = ft.AlertDialog(
        modal=True, title=ft.Text('طباعة استيكرات باركود الأصول'),
        content=ft.Container(width=420, content=ft.Column(
            [info] + scope_controls + [
                ft.Text('الباركود = كود الأصل نفسه، والماسح بيرجّع الكود مباشرة.', size=12, color=theme.TEXT_MUTED),
                preset_dd, type_dd, ft.Row([copies_f, slot_f], wrap=True), border_sw, company_sw, status,
            ], spacing=10, tight=True, scroll=ft.ScrollMode.AUTO)),
        actions=[ft.TextButton('إلغاء', on_click=lambda e: (setattr(dialog, 'open', False), page.update())),
                 ft.FilledButton('طباعة', icon=ft.Icons.PRINT_OUTLINED, bgcolor=theme.PRIMARY, on_click=do_print)],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(dialog)
    dialog.open = True
    page.update()
    return dialog
