import flet as ft
from .. import services, theme, thermal


def _station_card(page, key, title, snack):
    cfg = thermal.get_config()[key]
    is_receipt = key == 'receipt'
    mode = ft.Dropdown(label='طريقة الاتصال', width=240, value=cfg['mode'], options=[ft.dropdown.Option(k, v) for k, v in thermal.MODES.items()])
    addr = ft.TextField(label='العنوان', width=260, dense=True, value=cfg['address'])
    port = ft.TextField(label='المنفذ', width=100, dense=True, value=str(cfg['port']), keyboard_type=ft.KeyboardType.NUMBER)
    sysdd = ft.Dropdown(label='اختر من الطابعات المثبتة', width=260, options=[], visible=False)
    width = ft.Dropdown(label='عرض الورق', width=130, value=str(cfg['width']), options=[ft.dropdown.Option('80', '80 مم'), ft.dropdown.Option('58', '58 مم')])
    copies = ft.TextField(label='عدد النسخ', width=100, dense=True, value=str(cfg['copies']), keyboard_type=ft.KeyboardType.NUMBER)
    font = ft.TextField(label='حجم الخط', width=100, dense=True, value=str(cfg['font_px']), keyboard_type=ft.KeyboardType.NUMBER)
    cut = ft.Switch(label='قص الورق', value=bool(cfg['cut']))
    drawer = ft.Switch(label='فتح درج النقود', value=bool(cfg['drawer']), visible=is_receipt)
    auto = ft.Switch(label='طباعة الإيصال تلقائيًا بعد الدفع', value=bool(cfg['auto']), visible=is_receipt)
    tok_t = ft.Text('', selectable=True, size=12)
    def show_token(e=None):
        try:
            services.require_action('printers', 'edit')
            tok_t.value = 'المفتاح: ' + thermal.agent_token() + f'   |  الاسم في الوكيل: --station {key}'; page.update()
        except Exception as ex:
            tok_t.value = str(ex); page.update()
    def new_token(e=None):
        try:
            services.require_action('printers', 'edit')
            tok_t.value = 'المفتاح الجديد: ' + thermal.rotate_agent_token() + ' (لازم تحدّث الوكيل)'; page.update()
        except Exception as ex:
            tok_t.value = str(ex); page.update()
    agent_box = ft.Column([ft.Row([ft.OutlinedButton('عرض مفتاح الوكيل', on_click=show_token), ft.OutlinedButton('مفتاح جديد', on_click=new_token)], spacing=8), tok_t], spacing=6, visible=False)
    status = ft.Text('', size=12, visible=False)
    hint = ft.Text('', size=11, color=theme.TEXT_MUTED)

    def sync(e=None):
        m = mode.value
        addr.visible = m in ('network', 'system', 'file')
        agent_box.visible = m == 'agent'
        port.visible = m == 'network'
        sysdd.visible = m == 'system'
        addr.label = {'network': 'عنوان IP للطابعة', 'system': 'اسم الطابعة', 'file': 'المنفذ أو الملف (مثل COM3 أو /dev/usb/lp0)'}.get(m, 'العنوان')
        hint.value = {'off': 'بدون طباعة مباشرة: بيتفتح PDF للطباعة العادية.',
                      'network': 'الطابعات الحرارية بالشبكة بتستقبل على المنفذ 9100 غالبًا.',
                      'system': 'اسم الطابعة زي ما هو في إعدادات الويندوز. على ويندوز يفضّل تثبيت pywin32.',
                      'agent': 'السيرفر مش شايف الطابعة؟ ثبّت وكيل الطباعة (print_agent.py) على جهاز الكاشير: بيسحب أوامر الطباعة من السيرفر ويطبعها على الطابعة المحلية.',
                      'file': 'للطابعات المربوطة بمنفذ مباشر، أو لحفظ بيانات الطباعة في ملف للاختبار.'}.get(m, '')
        if m == 'system' and not sysdd.options:
            names = thermal.list_system_printers()
            sysdd.options = [ft.dropdown.Option(n) for n in names]
            if not names:
                sysdd.hint_text = 'ما لقيتش طابعات - اكتب الاسم يدويًا'
        try: page.update()
        except Exception: pass

    def pick(e):
        addr.value = sysdd.value; page.update()

    mode.on_select = sync
    sysdd.on_select = pick

    def collect():
        return dict(mode=mode.value, address=(addr.value or '').strip(), port=int(port.value or 9100), width=int(width.value),
                    copies=int(copies.value or 1), font_px=int(font.value or 24), cut=cut.value,
                    drawer=drawer.value if is_receipt else False, auto=auto.value if is_receipt else True)

    def show(ok, msg):
        status.value = msg; status.color = theme.SUCCESS if ok else theme.DANGER; status.visible = True; page.update()

    def save(e):
        try:
            services.require_action('printers', 'edit')
            thermal.save_config(key, **collect())
            show(True, 'تم الحفظ')
        except Exception as ex:
            show(False, str(ex))

    def test(e):
        try:
            services.require_action('printers', 'edit')
            thermal.save_config(key, **collect())
            ok, msg = thermal.print_test(key)
            show(ok, msg)
        except Exception as ex:
            show(False, str(ex))

    sync()
    return theme.card(ft.Column([
        ft.Text(title, size=16, weight=ft.FontWeight.BOLD),
        ft.Row([mode, addr, port, sysdd], wrap=True, spacing=12),
        hint, agent_box,
        ft.Row([width, copies, font], wrap=True, spacing=12),
        ft.Row([cut, drawer], wrap=True, spacing=16),
        auto,
        ft.Row([ft.FilledButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save),
                ft.OutlinedButton('حفظ وطباعة تجريبية', icon=ft.Icons.PRINT_OUTLINED, on_click=test), status], wrap=True, spacing=12),
    ], spacing=10))


def build_printers(page: ft.Page):
    """إعدادات الطابعات الحرارية (ESC/POS): طابعة الكاشير وطابعة المطبخ."""
    services.require_action('printers', 'view')

    def snack(t):
        page.overlay.append(ft.SnackBar(ft.Text(t), open=True)); page.update()

    return ft.Column([
        theme.page_title('الطابعات الحرارية'),
        ft.Text('الطباعة بتتم مباشرة على الطابعة (ESC/POS) والعربي بيتطبع كصورة فيشتغل على أي طابعة. لو الطابعة غير مفعّلة بيفضل التصدير PDF زي الأول.',
                size=12, color=theme.TEXT_MUTED),
        _station_card(page, 'receipt', thermal.STATIONS['receipt'], snack),
        _station_card(page, 'kitchen', thermal.STATIONS['kitchen'], snack),
    ], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)
