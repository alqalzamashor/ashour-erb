import flet as ft
from .. import services, theme, notify

STATUS = {'sent': ('تم الإرسال', 'SUCCESS'), 'failed': ('فشل', 'DANGER'), 'pending': ('قيد الإرسال', 'WARNING'), 'link': ('رابط يدوي', 'TEXT_MUTED')}
KINDS = {'receipt': 'إيصال', 'low_stock': 'نقص مخزون', 'manual': 'يدوي', 'test': 'تجربة'}


def build_notifications(page: ft.Page):
    services.require_action('notifications', 'view')
    can_edit = services.user_has_action(services._get_user(), 'notifications', 'edit')
    cfg = notify.get_config()
    F = {}

    def tf(key, label, width=330, password=False, multiline=False, **kw):
        F[key] = ft.TextField(label=label, value=str(cfg.get(key, '')), width=width, password=password, can_reveal_password=password, multiline=multiline, **kw)
        return F[key]

    enabled = ft.Switch(label='تفعيل الرسائل', value=bool(cfg['enabled']))
    auto_receipt = ft.Switch(label='إيصال تلقائي بعد البيع (للعميل الموافق وله جوال)', value=bool(cfg['auto_receipt']))
    low_en = ft.Switch(label='تنبيه نقص المخزون للمسؤولين', value=bool(cfg['low_stock_enabled']))
    provider = ft.Dropdown(label='المزوّد', width=330, value=cfg['provider'], options=[ft.dropdown.Option(k, v) for k, v in notify.PROVIDERS.items()])
    channel = ft.Dropdown(label='القناة', width=160, value=cfg['channel'], options=[ft.dropdown.Option('whatsapp', 'واتساب'), ft.dropdown.Option('sms', 'SMS')])
    status = ft.Text('', size=12)
    log_col = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, height=320)
    test_phone = ft.TextField(label='رقم للتجربة', width=200, hint_text='05xxxxxxxx')
    man_phone = ft.TextField(label='رقم الجوال', width=200)
    man_text = ft.TextField(label='نص الرسالة', multiline=True, min_lines=2, max_lines=4, width=420)
    groups = {
        'whatsapp_cloud': [tf('wa_phone_number_id', 'Phone Number ID'), tf('wa_token', 'Access Token', password=True), tf('wa_template_name', 'اسم القالب المعتمد (اختياري)'),
                           tf('wa_template_lang', 'لغة القالب', 120), tf('wa_api_version', 'نسخة الـ API', 120)],
        'twilio': [tf('twilio_sid', 'Account SID'), tf('twilio_token', 'Auth Token', password=True), tf('twilio_from', 'رقم المرسل (+966..)')],
        'http': [tf('http_url', 'رابط البوابة (POST)', 560), tf('http_headers', 'Headers (JSON)', 560, multiline=True), tf('http_body', 'قالب الطلب (JSON) - استخدم {to} و{text}', 560, multiline=True)],
    }
    boxes = {k: ft.Column(v, spacing=8, visible=(k == cfg['provider'])) for k, v in groups.items()}
    common = [tf('country_code', 'مفتاح الدولة', 120), tf('currency', 'العملة في الرسالة', 130), tf('receipt_min_total', 'أقل إجمالي للإيصال', 160),
              tf('receipt_template', 'نص الإيصال ({company} {number} {total} {currency} {date} {customer} {points})', 560, multiline=True),
              tf('low_stock_recipients', 'جوالات المسؤولين (مفصولة بفاصلة)', 560), tf('low_stock_hour', 'ساعة الفحص اليومي (0-23)', 150), tf('low_stock_repeat_days', 'تكرار التنبيه لنفس الصنف (أيام)', 200)]

    def on_provider(e=None):
        for k, b in boxes.items():
            b.visible = provider.value == k
        page.update()
    provider.on_change = on_provider

    def say(msg, ok=True):
        status.value = msg; status.color = theme.SUCCESS if ok else theme.DANGER; page.update()

    def save(e):
        try:
            kw = {k: f.value for k, f in F.items()}
            kw.update(enabled=enabled.value, auto_receipt=auto_receipt.value, low_stock_enabled=low_en.value, provider=provider.value, channel=channel.value)
            notify.save_config(**kw)
            say('تم الحفظ')
        except Exception as ex:
            say(str(ex), False)

    def refresh_log(e=None):
        rows = []
        for r in notify.list_log(limit=100):
            label, col = STATUS.get(r.status, (r.status, 'TEXT_MUTED'))
            actions = []
            if r.status == 'link':
                actions.append(ft.TextButton('فتح واتساب', on_click=lambda ev, rr=r: theme.launch_url(page, f'https://wa.me/{rr.recipient}?text=' + __import__('urllib.parse').parse.quote(rr.body))))
            rows.append(ft.Container(padding=ft.Padding(left=6, right=6, top=3, bottom=3), content=ft.Row([
                ft.Text(f'{r.created_at:%m-%d %H:%M}', size=12, width=90), ft.Text(KINDS.get(r.kind, r.kind), size=12, width=80),
                ft.Text(r.recipient, size=12, width=120), ft.Text((r.body or '').replace('\n', ' ')[:70], size=12, expand=True),
                ft.Text(label + (f' ({r.attempts})' if r.attempts else ''), size=12, color=getattr(theme, col), width=110, tooltip=r.error or None)] + actions, spacing=8)))
        log_col.controls = rows or [ft.Text('مفيش رسائل لسه', color=theme.TEXT_MUTED)]
        if e is not None:
            page.update()

    def do_test(e):
        try:
            notify.send_test(test_phone.value); refresh_log(); say('اتسجّلت رسالة تجريبية - شوف حالتها في السجل (اضغط تحديث بعد ثواني)')
        except Exception as ex:
            say(str(ex), False)

    def do_manual(e):
        try:
            notify.send_manual(man_phone.value, man_text.value); refresh_log(); say('اتسجّلت الرسالة'); man_text.value = ''; page.update()
        except Exception as ex:
            say(str(ex), False)

    def do_retry(e):
        try:
            say(f'اتعادت محاولة {notify.retry_failed()} رسالة'); refresh_log(True)
        except Exception as ex:
            say(str(ex), False)

    def do_low(e):
        try:
            say(f'اتبلّغ عن {notify.check_low_stock(force=True)} صنف'); refresh_log(True)
        except Exception as ex:
            say(str(ex), False)

    refresh_log()
    note = ft.Text('الإيصال بيتبعت بس للعملاء اللي فعّلت لهم خانة «موافق على استلام رسائل» في بياناتهم. مفاتيح المزوّد بتتخزّن في ملف إعدادات على السيرفر (مش مشفّرة) - حافظ على صلاحيات المجلد. '
                   'واتساب Cloud: النص الحر مقبول بس خلال 24 ساعة من رسالة العميل؛ للإرسال في أي وقت لازم قالب معتمد من ميتا.', size=12, color=theme.TEXT_MUTED)
    return ft.Column([
        ft.Text('الرسائل (واتساب / SMS)', size=22, weight=ft.FontWeight.BOLD), note,
        theme.card(ft.Column([ft.Row([enabled, auto_receipt, low_en], wrap=True), ft.Row([provider, channel], wrap=True)] + list(boxes.values()) +
                             [ft.Row(common[:3], wrap=True)] + common[3:4] + common[4:5] + [ft.Row(common[5:], wrap=True),
                              ft.Row([ft.FilledButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save, disabled=not can_edit), status], wrap=True)], spacing=10), padding=16),
        theme.card(ft.Column([ft.Text('تجربة وإرسال يدوي', weight=ft.FontWeight.BOLD),
                              ft.Row([test_phone, ft.OutlinedButton('رسالة تجريبية', on_click=do_test)], wrap=True),
                              ft.Row([man_phone, man_text, ft.OutlinedButton('إرسال', on_click=do_manual)], wrap=True),
                              ft.Row([ft.OutlinedButton('فحص النقص الآن', on_click=do_low), ft.OutlinedButton('إعادة محاولة الفاشل', on_click=do_retry)], wrap=True)], spacing=10), padding=16),
        theme.card(ft.Column([ft.Row([ft.Text('سجل الرسائل', weight=ft.FontWeight.BOLD), ft.IconButton(ft.Icons.REFRESH, on_click=refresh_log)]), log_col]), padding=16),
    ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
