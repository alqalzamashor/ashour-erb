import datetime
import flet as ft
from .. import services, theme, promotions


def build_coupons(page: ft.Page):
    """الكوبونات والخصومات: كوبونات (نسبة/مبلغ) بحدودها، وسياسة الخصم اليدوي (الحد اللي فوقه يحتاج مدير)."""
    services.require_action('coupons', 'view')
    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x, weight=ft.FontWeight.BOLD)) for x in ['الكود', 'الاسم', 'الخصم', 'أدنى فاتورة', 'سقف الخصم', 'الصلاحية', 'الاستخدام', 'الحالة', '']], rows=[])
    cfg = promotions.get_config()
    manual_sw = ft.Switch(label='السماح بخصم يدوي في الكاشير والمطعم', value=bool(cfg['manual_enabled']))
    free_f = ft.TextField(label='أقصى نسبة خصم بدون اعتماد مدير %', width=260, dense=True, value=f"{cfg['max_percent_free']:g}", keyboard_type=ft.KeyboardType.NUMBER)
    pol_msg = ft.Text('', size=12, visible=False)

    def snack(t):
        page.overlay.append(ft.SnackBar(ft.Text(t), open=True)); page.update()

    def refresh():
        rows = []
        for c in promotions.list_coupons():
            val = f"{c['value']:g}%" if c['kind'] == 'percent' else f"{c['value']:,.2f}"
            valid = ' → '.join(x for x in [f"{c['valid_from']:%Y-%m-%d}" if c['valid_from'] else '', f"{c['valid_to']:%Y-%m-%d}" if c['valid_to'] else ''] if x) or 'مفتوحة'
            use = f"{c['used_count']}" + (f" / {c['usage_limit']}" if c['usage_limit'] else '')
            expired = c['valid_to'] and datetime.datetime.now() > datetime.datetime.combine(c['valid_to'].date(), datetime.time.max)
            used_up = c['usage_limit'] and c['used_count'] >= c['usage_limit']
            st, col = ('موقوف', theme.TEXT_MUTED) if not c['is_active'] else (('منتهي', theme.DANGER) if expired else (('مستهلك', theme.DANGER) if used_up else ('فعّال', theme.SUCCESS)))
            rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(c['code'], weight=ft.FontWeight.BOLD, size=12)), ft.DataCell(ft.Text(c['name'], size=12)), ft.DataCell(ft.Text(val, size=12)),
                                          ft.DataCell(ft.Text(f"{c['min_order']:,.2f}" if c['min_order'] else '-', size=12)), ft.DataCell(ft.Text(f"{c['max_discount']:,.2f}" if c['max_discount'] else '-', size=12)),
                                          ft.DataCell(ft.Text(valid, size=12)), ft.DataCell(ft.Text(use, size=12)), ft.DataCell(ft.Text(st, color=col, weight=ft.FontWeight.BOLD, size=12)),
                                          ft.DataCell(ft.Row([ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip='تعديل', on_click=lambda e, x=c: edit(x)),
                                                              ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip='حذف', icon_color=theme.DANGER, on_click=lambda e, x=c: remove(x))], spacing=0))]))
        table.rows = rows

    def remove(c):
        try:
            promotions.delete_coupon(c['id']); refresh(); page.update()
        except Exception as ex:
            snack(str(ex))

    def edit(c=None):
        c = c or {}
        code_f = ft.TextField(label='الكود *', width=170, value=c.get('code', ''), capitalization=ft.TextCapitalization.CHARACTERS)
        name_f = ft.TextField(label='الاسم / الوصف', width=260, value=c.get('name', ''))
        kind_dd = ft.Dropdown(label='النوع', width=150, value=c.get('kind', 'percent'), options=[ft.dropdown.Option('percent', 'نسبة %'), ft.dropdown.Option('fixed', 'مبلغ ثابت')])
        val_f = ft.TextField(label='القيمة *', width=110, value=f"{c['value']:g}" if c else '', keyboard_type=ft.KeyboardType.NUMBER)
        min_f = ft.TextField(label='أدنى فاتورة', width=130, value=f"{c['min_order']:g}" if c.get('min_order') else '', keyboard_type=ft.KeyboardType.NUMBER)
        max_f = ft.TextField(label='سقف الخصم', width=130, value=f"{c['max_discount']:g}" if c.get('max_discount') else '', keyboard_type=ft.KeyboardType.NUMBER)
        from_f = ft.TextField(label='من (YYYY-MM-DD)', width=160, value=f"{c['valid_from']:%Y-%m-%d}" if c.get('valid_from') else '')
        to_f = ft.TextField(label='إلى (YYYY-MM-DD)', width=160, value=f"{c['valid_to']:%Y-%m-%d}" if c.get('valid_to') else '')
        lim_f = ft.TextField(label='أقصى عدد استخدامات (0 = بلا حد)', width=250, value=str(c.get('usage_limit', 0)), keyboard_type=ft.KeyboardType.NUMBER)
        act_sw = ft.Switch(label='فعّال', value=c.get('is_active', True))
        err = ft.Text('', color=theme.DANGER, visible=False)

        def dt(v):
            v = (v or '').strip()
            return datetime.datetime.strptime(v, '%Y-%m-%d') if v else None

        def save(e):
            try:
                promotions.save_coupon(code_f.value, name_f.value, kind_dd.value, val_f.value, min_f.value, max_f.value, dt(from_f.value), dt(to_f.value), lim_f.value, act_sw.value, coupon_id=c.get('id'))
                dlg.open = False; refresh(); page.update()
            except ValueError as ex:
                err.value = str(ex) if 'time data' not in str(ex) else 'التاريخ بصيغة YYYY-MM-DD'; err.visible = True; page.update()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        dlg = ft.AlertDialog(modal=True, title=ft.Text('تعديل كوبون' if c else 'كوبون جديد'),
                             content=ft.Column([ft.Row([code_f, name_f], wrap=True, spacing=10), ft.Row([kind_dd, val_f, min_f, max_f], wrap=True, spacing=10), ft.Row([from_f, to_f], wrap=True, spacing=10), lim_f, act_sw, err],
                                               tight=True, spacing=10, width=620),
                             actions=[ft.TextButton('إلغاء', on_click=lambda e: (setattr(dlg, 'open', False), page.update())), theme.guard_submit(ft.FilledButton('حفظ', bgcolor=theme.PRIMARY, on_click=save))])
        page.overlay.append(dlg); dlg.open = True; page.update()

    def save_policy(e):
        try:
            promotions.save_config(manual_sw.value, free_f.value)
            pol_msg.value = 'تم الحفظ'; pol_msg.color = theme.SUCCESS; pol_msg.visible = True
        except Exception as ex:
            pol_msg.value = str(ex); pol_msg.color = theme.DANGER; pol_msg.visible = True
        page.update()

    refresh()
    return ft.Column([
        ft.Row([theme.page_title('الكوبونات والخصومات', 'كوبونات الخصم وسياسة الخصم اليدوي في الكاشير والمطعم'), ft.Container(expand=True),
                ft.FilledButton('كوبون جديد', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=lambda e: edit())]),
        theme.card(ft.Column([ft.Text('سياسة الخصم اليدوي', size=15, weight=ft.FontWeight.BOLD), ft.Row([manual_sw, free_f, ft.FilledButton('حفظ', on_click=save_policy), pol_msg], wrap=True, spacing=12),
                              ft.Text('أي خصم يدوي نسبته أكبر من الحد ده بيحتاج اعتماد مدير (مستخدم لديه صلاحية "إغلاق" في المطعم) وكتابة سبب. الخصم بيتوزع على أسطر الفاتورة فالضريبة والـQR بيطلعوا صح.', size=11, color=theme.TEXT_MUTED)], spacing=8)),
        theme.card(theme.h_scroll(table), expand=True),
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
