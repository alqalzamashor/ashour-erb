import flet as ft
from .. import services, theme, scheduled_reports as SR


def build_scheduled_reports(page: ft.Page):
    """التقارير المجدولة بالبريد: ملخص يومي/أسبوعي/شهري يتبعت تلقائيًا (والبرنامج مفتوح) لقايمة مستلمين."""
    services.require_action('scheduled_reports', 'view')
    cfg = SR.get_config()
    smtp_ok = bool((services.get_company_settings().smtp_host or '') and (services.get_company_settings().smtp_from_email or ''))
    en_sw = ft.Switch(label='تفعيل الإرسال التلقائي', value=bool(cfg['enabled']))
    rec_f = ft.TextField(label='المستلمون (افصل بفاصلة)', width=480, dense=True, value=cfg['recipients'], multiline=False)
    daily = ft.Checkbox(label='ملخص يومي', value=bool(cfg['daily']))
    weekly = ft.Checkbox(label='ملخص أسبوعي (آخر 7 أيام)', value=bool(cfg['weekly']))
    monthly = ft.Checkbox(label='ملخص شهري (الشهر السابق، يوم 1)', value=bool(cfg['monthly']))
    time_f = ft.TextField(label='وقت الإرسال HH:MM', width=150, dense=True, value=cfg['time'])
    wd_dd = ft.Dropdown(label='يوم الأسبوعي', width=150, value=str(cfg['weekday']), options=[ft.dropdown.Option(str(i), n) for i, n in enumerate(SR.WEEKDAYS)])
    xl_sw = ft.Switch(label='إرفاق ملف Excel', value=bool(cfg['attach_excel']))
    msg = ft.Text('', size=12, visible=False)
    status = ft.Column(spacing=4)
    test_dd = ft.Dropdown(label='نوع التجربة', width=140, value='daily', options=[ft.dropdown.Option(k, v) for k, v in SR.FREQ.items()])

    def show(ok, t):
        msg.value = t; msg.color = theme.SUCCESS if ok else theme.DANGER; msg.visible = True; page.update()

    def refresh_status():
        st = SR.get_state(); rows = []
        if not smtp_ok:
            rows.append(ft.Text('إعدادات البريد (SMTP) غير مكتملة - أكملها من «إعدادات الشركة» عشان الإرسال يشتغل.', size=12, color=theme.DANGER))
        for k, n in SR.FREQ.items():
            rows.append(ft.Text(f"آخر {n}: {st['last_sent'].get(k, 'لم يُرسل بعد')}", size=12, color=theme.TEXT_MUTED))
        if st.get('last_ok_at'):
            rows.append(ft.Text(f"آخر إرسال ناجح: {st['last_ok_at'].replace('T', ' ')}", size=12, color=theme.SUCCESS))
        if st.get('last_error'):
            rows.append(ft.Text(f"آخر خطأ: {st['last_error']}", size=12, color=theme.DANGER))
        status.controls = rows

    def collect():
        return dict(enabled=en_sw.value, recipients=rec_f.value, daily=daily.value, weekly=weekly.value, monthly=monthly.value, time=time_f.value, weekday=int(wd_dd.value), attach_excel=xl_sw.value)

    def save(e):
        try:
            SR.save_config(**collect())
            rec_f.value = SR.get_config()['recipients']
            show(True, 'تم الحفظ' + (' - هيتبعت والبرنامج مفتوح بحساب أدمن' if en_sw.value else ''))
        except Exception as ex:
            show(False, str(ex))

    def test(e):
        try:
            SR.save_config(**collect())
            if not SR.recipients():
                raise ValueError('اكتب بريد مستلم الأول')
            r = SR.send_report(test_dd.value)
            show(True, f"اتبعت تقرير تجريبي ({r['label']}) إلى: {', '.join(r['to'])}")
        except Exception as ex:
            show(False, f'تعذر الإرسال: {ex}')

    refresh_status()
    return ft.Column([
        theme.page_title('التقارير المجدولة بالبريد', 'ملخص المبيعات والمطعم والخصومات والنسخ الاحتياطي على إيميلك بشكل دوري'),
        theme.card(ft.Column([
            en_sw, rec_f,
            ft.Row([daily, weekly, monthly], wrap=True, spacing=16),
            ft.Row([time_f, wd_dd, xl_sw], wrap=True, spacing=16),
            ft.Row([ft.FilledButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save), test_dd,
                    theme.guard_submit(ft.OutlinedButton('إرسال تجربة الآن', icon=ft.Icons.SEND_OUTLINED, on_click=test)), msg], wrap=True, spacing=12),
            ft.Text('الإرسال بيتم تلقائيًا طول ما البرنامج مفتوح بحساب أدمن (بيتفحص كل 5 دقايق). لو البرنامج كان مقفول وقت الإرسال، بيتبعت أول ما يتفتح في نفس اليوم.', size=11, color=theme.TEXT_MUTED),
        ], spacing=12)),
        theme.card(ft.Column([ft.Text('الحالة', size=15, weight=ft.FontWeight.BOLD), status], spacing=6)),
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
