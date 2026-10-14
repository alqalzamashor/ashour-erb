import threading
import flet as ft
from .. import services, theme, alerts

SEV = {'high': ('عاجل', 'DANGER'), 'medium': ('مهم', 'WARNING'), 'low': ('للعلم', 'TEXT_MUTED')}


def build_smart_alerts(page: ft.Page):
    """تنبيهات ذكية: أصناف راكدة / قاربة على النفاد، عملاء متأخرين أو متعدّين حد الائتمان. العتبات وملخص الواتساب اليومي من الإعدادات."""
    services.require_action('alerts', 'view')
    can_edit = services.user_has_action(services._get_user(), 'alerts', 'edit')
    cfg = alerts.get_config()
    kind_dd = ft.Dropdown(label='النوع', width=220, value='', options=[ft.dropdown.Option('', 'كل التنبيهات')] + [ft.dropdown.Option(k, v) for k, v in alerts.KINDS.items()])
    sev_dd = ft.Dropdown(label='الأهمية', width=150, value='', options=[ft.dropdown.Option('', 'الكل'), ft.dropdown.Option('high', 'عاجل'), ft.dropdown.Option('medium', 'مهم'), ft.dropdown.Option('low', 'للعلم')])
    summary = ft.Text('', size=13, weight=ft.FontWeight.BOLD)
    msg = ft.Text('', size=12, visible=False)
    state = {'items': []}
    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x, weight=ft.FontWeight.BOLD)) for x in ['الأهمية', 'النوع', 'البند', 'التفاصيل']], rows=[], heading_row_height=40)

    def show(t, ok=True):
        msg.value = t; msg.color = theme.SUCCESS if ok else theme.DANGER; msg.visible = True; page.update()

    def render(e=None):
        rows = []
        for a in state['items']:
            if kind_dd.value and a['kind'] != kind_dd.value:
                continue
            if sev_dd.value and a['severity'] != sev_dd.value:
                continue
            lab, col = SEV[a['severity']]
            rows.append(ft.DataRow(cells=[ft.DataCell(ft.Container(ft.Text(lab, size=11, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=getattr(theme, col), border_radius=8, padding=ft.Padding.symmetric(horizontal=8, vertical=2))),
                                          ft.DataCell(ft.Text(alerts.KINDS[a['kind']], size=12)), ft.DataCell(ft.Text(a['title'], size=12, weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(a['detail'], size=12))]))
        table.rows = rows
        c = {k: sum(1 for a in state['items'] if a['kind'] == k) for k in alerts.KINDS}
        summary.value = f"{len(state['items'])} تنبيه  |  " + "  ·  ".join(f"{alerts.KINDS[k]}: {n}" for k, n in c.items())
        page.update()

    def refresh(e=None):
        try:
            state['items'] = alerts.compute()
            render()
        except Exception as ex:
            show(str(ex), False)

    F = {}

    def num(key, label, w=150):
        F[key] = ft.TextField(label=label, value=str(cfg[key]), width=w, dense=True, keyboard_type=ft.KeyboardType.NUMBER, disabled=not can_edit)
        return F[key]

    def sw(key, label):
        F[key] = ft.Switch(label=label, value=bool(cfg[key]), disabled=not can_edit)
        return F[key]
    F['digest_recipients'] = ft.TextField(label='أرقام المسؤولين (مفصولة بفاصلة)', value=cfg['digest_recipients'], width=360, dense=True, disabled=not can_edit)

    def save(e):
        try:
            vals = {k: (c.value if isinstance(c, ft.Switch) else (c.value or '').strip()) for k, c in F.items()}
            alerts.save_config(**vals)
            show('تم حفظ الإعدادات'); refresh()
        except Exception as ex:
            show(str(ex), False)

    def digest(e):
        def go():
            try:
                n = alerts.send_digest(force=True)
                show(f'اتبعت الملخص لـ {n} رقم (أو اتسجّل كرابط يدوي لو مفيش مزوّد) - راجع شاشة الرسائل' if n else 'مفيش رسالة اتبعتت: تأكد من تفعيل الرسائل وكتابة أرقام المسؤولين، ومن وجود تنبيهات', bool(n))
            except Exception as ex:
                show(str(ex), False)
        threading.Thread(target=go, daemon=True).start()

    kind_dd.on_select = render; sev_dd.on_select = render
    refresh()
    settings = ft.ExpansionTile(title=ft.Text('إعدادات التنبيهات والملخص اليومي'), controls=[ft.Container(ft.Column([
        ft.Row([sw('slow_enabled', 'الأصناف الراكدة'), num('slow_days', 'راكد بعد (يوم بدون بيع)'), num('slow_min_value', 'أقل قيمة مجمّدة')], wrap=True, spacing=10),
        ft.Row([sw('low_enabled', 'قارب على النفاد'), num('cover_days', 'تنبيه لو الرصيد يكفي أقل من (يوم)'), num('lookback_days', 'مدة قياس معدل البيع (يوم)')], wrap=True, spacing=10),
        ft.Row([sw('overdue_enabled', 'عملاء متأخرين'), num('overdue_min_days', 'متأخر من (يوم)'), num('overdue_min_amount', 'أقل مبلغ متأخر')], wrap=True, spacing=10),
        sw('limit_enabled', 'تعدّي حد الائتمان / الإيقاف الائتماني'),
        ft.Divider(height=1),
        ft.Row([sw('digest_enabled', 'ملخص يومي واتساب/SMS'), F['digest_recipients'], num('digest_hour', 'الساعة (0-23)', 120), num('digest_max_items', 'أقصى عدد بنود', 130)], wrap=True, spacing=10),
        ft.Text('الملخص بيتبعت عن طريق إعدادات "الرسائل (واتساب/SMS)" - لازم تكون مفعّلة بمزوّد. بيتبعت مرة في اليوم والبرنامج مفتوح.', size=11.5, color=theme.TEXT_MUTED),
        ft.Row([ft.FilledButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, on_click=save, disabled=not can_edit), ft.OutlinedButton('ابعت الملخص الآن', icon=ft.Icons.SEND_OUTLINED, on_click=digest, disabled=not can_edit)], spacing=8),
    ], spacing=8), padding=10)])
    return ft.Column([
        theme.page_title('التنبيهات الذكية', 'أصناف راكدة أو قاربة على النفاد، وعملاء متأخرين في السداد'),
        theme.card(ft.Column([ft.Row([kind_dd, sev_dd, ft.FilledButton('تحديث', icon=ft.Icons.REFRESH, bgcolor=theme.PRIMARY, on_click=refresh)], spacing=10, wrap=True), summary, msg], spacing=8)),
        theme.card(theme.h_scroll(table), expand=True),
        theme.card(settings),
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
