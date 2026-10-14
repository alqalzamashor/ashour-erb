"""الفوترة الإلكترونية (ZATCA المرحلة الثانية): بيانات البائع، تسجيل الجهاز (CSR/OTP/فحوصات الامتثال/شهادة الإنتاج)، التفعيل، وسجل المستندات وإعادة المحاولة."""
import os
import threading

import flet as ft
from .. import services, theme, zatca_p2 as z

STATUS_LABEL = {"signed": "موقّعة (في الانتظار)", "reported": "تم الإبلاغ ✔", "cleared": "تم الاعتماد ✔", "rejected": "مرفوضة ✘", "failed": "فشل الإرسال - هتتعاد"}
STATUS_COLOR = {"reported": theme.SUCCESS, "cleared": theme.SUCCESS, "rejected": theme.DANGER, "failed": theme.WARNING, "signed": theme.TEXT_MUTED}


def build_zatca(page: ft.Page):
    services.require_action('zatca', 'view')
    cfg = z.get_config()
    msg = ft.Text('', size=13, visible=False, selectable=True)
    checks = ft.Column(spacing=2)
    table_box = ft.Column(spacing=0)
    status_txt = ft.Text('', size=13)

    def show(text, ok=True):
        msg.value = text; msg.color = theme.SUCCESS if ok else theme.DANGER; msg.visible = True; page.update()

    def tf(key, label, width=200, **kw):
        return ft.TextField(label=label, width=width, dense=True, value=str(cfg.get(key) or ''), **kw)
    f = {k: tf(k, l, w) for k, l, w in (('crn', 'السجل التجاري (CRN)', 200), ('street', 'الشارع', 220), ('building', 'رقم المبنى', 150), ('district', 'الحي', 160),
                                         ('city', 'المدينة', 150), ('postal', 'الرمز البريدي', 170), ('branch_name', 'اسم الفرع / الوحدة', 200), ('device_serial', 'رقم الجهاز (اختياري)', 200),
                                         ('zero_rate_code', 'كود إعفاء 0%', 260), ('zero_rate_text', 'سبب الإعفاء', 220))}
    env = ft.Dropdown(label='البيئة', width=190, value=cfg['env'], options=[ft.dropdown.Option('sandbox', 'تجريبية (sandbox)'), ft.dropdown.Option('simulation', 'محاكاة'), ft.dropdown.Option('production', 'إنتاج')])
    types = ft.Dropdown(label='أنواع الفواتير', width=230, value=cfg['invoice_types'], options=[ft.dropdown.Option('1100', 'ضريبية + مبسّطة'), ft.dropdown.Option('0100', 'مبسّطة فقط (B2C)'), ft.dropdown.Option('1000', 'ضريبية فقط (B2B)')])
    otp = ft.TextField(label='رمز OTP من بوابة فاتورة', width=220, dense=True, keyboard_type=ft.KeyboardType.NUMBER)
    enable_sw = ft.Switch(label='تفعيل الفوترة الإلكترونية (كل فاتورة جديدة تتوقّع وتتبعت)', value=bool(cfg['enabled']))

    def company():
        c = services.get_company_settings()
        return (c.name or '').strip(), (c.vat_number or '').strip()

    def save(e=None, quiet=False):
        try:
            services.require_action('zatca', 'edit')
            z.save_config(env=env.value, invoice_types=types.value, enabled=enable_sw.value, **{k: (v.value or '').strip() for k, v in f.items()})
            if enable_sw.value and not z.is_enabled():
                z.save_config(enabled=False); enable_sw.value = False
                raise ValueError('مينفعش التفعيل قبل الحصول على شهادة الإنتاج')
            refresh()
            if not quiet:
                show('تم الحفظ')
        except Exception as ex:
            show(str(ex), False)

    def bg(fn, busy):
        def run():
            try:
                show(busy)
                r = fn()
                show(r if isinstance(r, str) else 'تم', True)
            except Exception as ex:
                show(str(ex), False)
            refresh()
        threading.Thread(target=run, daemon=True).start()

    def step1(e):
        services.require_action('zatca', 'edit')
        save(quiet=True)
        name, vat = company()
        bg(lambda: 'تم استلام شهادة الامتثال (' + z.start_onboarding(vat, name, otp.value) + ') - كمّل بفحوصات الامتثال', 'بطلب الشهادة من الهيئة...')

    def step2(e):
        def go():
            name, vat = company()
            res = z.run_compliance_checks(vat, name)
            checks.controls = [ft.Text(('✔ ' if ok else '✘ ') + label + ('' if ok else ' — ' + ' | '.join(m)), size=12, color=theme.SUCCESS if ok else theme.DANGER, selectable=True) for label, ok, m in res]
            return 'كل الفحوصات نجحت - اطلب شهادة الإنتاج' if all(r[1] for r in res) else 'فيه فحوصات فشلت (التفاصيل تحت) - صحّح البيانات وجرّب تاني'
        bg(go, 'بفحص فواتير تجريبية مع الهيئة...')

    def step3(e):
        bg(lambda: 'تم استلام شهادة الإنتاج (' + z.finish_onboarding() + ') - فعّل الفوترة من المفتاح فوق', 'بطلب شهادة الإنتاج...')

    def issue_missing(e):
        bg(lambda: f'اتوقّع {z.issue_missing(3)} مستند ناقص (وهيتبعتوا تلقائيًا)', 'بصدّر الناقص...')

    def retry(did):
        bg(lambda: 'النتيجة: ' + str(z.retry_doc(did)), 'بعيد الإرسال...')

    def download(did):
        num, xml = z.get_xml(did)
        path = os.path.join(services.downloads_dir(), f"{num}.xml".replace('/', '-'))
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(xml)
        theme.open_or_download_file(page, path)

    def refresh():
        c = z.public_config()
        status_txt.value = ('شهادة الإنتاج: ' + ('موجودة ✔' if c['has_production'] else 'لسه ❌') + '  ·  شهادة الامتثال: ' + ('موجودة' if c['has_compliance'] else 'لسه') +
                            '  ·  الفوترة: ' + ('مفعّلة ✔' if z.is_enabled() else 'غير مفعّلة'))
        status_txt.color = theme.SUCCESS if z.is_enabled() else theme.WARNING
        rows = []
        for d in z.list_docs(60):
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(str(d['icv']), size=12)), ft.DataCell(ft.Text(d['number'], size=12)), ft.DataCell(ft.Text('إشعار دائن' if d['kind'] == 'credit' else 'فاتورة', size=12)),
                ft.DataCell(ft.Text('ضريبية' if d['mode'] == 'standard' else 'مبسّطة', size=12)),
                ft.DataCell(ft.Text(STATUS_LABEL.get(d['status'], d['status']), size=12, color=STATUS_COLOR.get(d['status']))),
                ft.DataCell(ft.Container(ft.Text((d['response'] or '')[:160], size=11, color=theme.TEXT_MUTED, selectable=True), width=360)),
                ft.DataCell(ft.Row([ft.IconButton(ft.Icons.REFRESH, tooltip='إعادة الإرسال', on_click=lambda e, i=d['id']: retry(i)) if d['status'] in ('signed', 'failed') else ft.Container(),
                                    ft.IconButton(ft.Icons.DOWNLOAD_OUTLINED, tooltip='تنزيل XML', on_click=lambda e, i=d['id']: download(i))], spacing=0))]))
        table_box.controls = [theme.h_scroll(ft.DataTable(columns=[ft.DataColumn(ft.Text(t)) for t in ('ICV', 'الرقم', 'النوع', 'الشكل', 'الحالة', 'رد الهيئة', '')], rows=rows, heading_row_height=36, data_row_min_height=34))] if rows else [ft.Text('لسه مفيش مستندات.', size=12, color=theme.TEXT_MUTED)]
        try:
            page.update()
        except Exception:
            pass

    refresh()
    seller = theme.card(ft.Column([
        ft.Text('بيانات البائع (بتتكتب في الفاتورة والشهادة)', weight=ft.FontWeight.BOLD),
        ft.Text('الاسم والرقم الضريبي بيتاخدوا من «إعدادات الشركة» (الرقم الضريبي لازم 15 رقم يبدأ وينتهي بـ 3).', size=11.5, color=theme.TEXT_MUTED),
        ft.Row([f['crn'], f['street'], f['building'], f['district'], f['city'], f['postal']], wrap=True, spacing=10),
        ft.Row([f['branch_name'], f['device_serial'], env, types], wrap=True, spacing=10),
        ft.Row([f['zero_rate_code'], f['zero_rate_text']], wrap=True, spacing=10),
        ft.FilledButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, on_click=save)], spacing=10))
    onboarding = theme.card(ft.Column([
        ft.Text('تسجيل الجهاز مع الهيئة (مرة واحدة)', weight=ft.FontWeight.BOLD),
        ft.Text('1) من بوابة فاتورة (fatoora.zatca.gov.sa) أنشئ رمز OTP.  2) اكتبه هنا واضغط «طلب شهادة الامتثال».  3) «فحوصات الامتثال» بتبعت فواتير تجريبية وبتعرض ردود الهيئة.  4) «شهادة الإنتاج».  5) فعّل المفتاح تحت. جرّب الأول على بيئة sandbox.', size=11.5, color=theme.TEXT_MUTED),
        ft.Row([otp, ft.FilledButton('1) طلب شهادة الامتثال', on_click=step1), ft.OutlinedButton('2) فحوصات الامتثال', on_click=step2), ft.OutlinedButton('3) شهادة الإنتاج', on_click=step3)], wrap=True, spacing=10),
        checks], spacing=10))
    ctl = theme.card(ft.Column([status_txt, enable_sw, ft.Row([ft.FilledButton('حفظ/تفعيل', on_click=save), ft.OutlinedButton('أصدر الناقص (آخر 3 أيام)', icon=ft.Icons.PLAYLIST_ADD_CHECK, on_click=issue_missing)], spacing=10), msg], spacing=10))
    warn = ft.Text('تنبيه: التكامل مبني على مواصفات الهيئة ولسه ما اتجرّبش على منصتها من جهتنا - اختبره على sandbox وشوف نتيجة «فحوصات الامتثال» قبل الإنتاج، وراجع محاسبك/مستشار الزكاة قبل الاعتماد عليه.', size=12, color=theme.WARNING)
    return ft.Column([theme.page_title('الفوترة الإلكترونية (ZATCA - المرحلة الثانية)'), warn, ctl, seller, onboarding, theme.card(ft.Column([ft.Text('سجل المستندات', weight=ft.FontWeight.BOLD), table_box], spacing=8))],
                     spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)
