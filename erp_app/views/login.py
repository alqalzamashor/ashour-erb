import flet as ft
from .. import brand, services, theme, twofa


def show_login(page, on_success):
    from .. import i18n
    page.rtl = getattr(page, '_erp_lang', 'ar') == 'ar'
    user_f = ft.TextField(label='اسم المستخدم', width=320, autofocus=True, prefix_icon=ft.Icons.PERSON_OUTLINE, border_radius=10)
    pw_f = ft.TextField(label='كلمة المرور', password=True, can_reveal_password=True, width=320,
                        prefix_icon=ft.Icons.LOCK_OUTLINE, border_radius=10)
    otp_f = ft.TextField(label='رمز التحقق (أو كود استرداد)', width=320, prefix_icon=ft.Icons.SECURITY, border_radius=10, visible=False)
    status = ft.Text('', color=theme.DANGER, size=12)

    def switch_lang(e=None):
        page._erp_lang = 'en' if getattr(page, '_erp_lang', 'ar') == 'ar' else 'ar'
        show_login(page, on_success)

    def finish(x):
        if x.get('needs_2fa_setup'):
            from . import security
            services.set_current_user(x)
            security.setup_dialog(page, forced=True, on_done=lambda: on_success(x))
        else:
            on_success(x)

    def login(e):
        try:
            x = services.authenticate_user(user_f.value, pw_f.value, otp=otp_f.value if otp_f.visible else None)
        except twofa.OtpRequired:
            otp_f.visible = True
            status.value = 'أدخل رمز التحقق من تطبيق المصادقة'
            page.update()
            page.run_task(otp_f.focus)
            return
        except ValueError as ex:
            status.value = str(ex)
            page.update()
            return
        if x:
            if services.must_change_password(x):
                force_change(x)
            else:
                finish(x)
        else:
            status.value = 'اسم المستخدم أو كلمة المرور غير صحيحة'
            page.update()

    pw_f.on_submit = login
    otp_f.on_submit = login

    def force_change(user):
        """كلمة المرور الافتراضية ممنوعة على السيرفر: نافذة إجبارية لتغييرها قبل الدخول."""
        old_f = ft.TextField(label='كلمة المرور الحالية', password=True, can_reveal_password=True, width=320)
        new_f = ft.TextField(label=f'كلمة المرور الجديدة ({services.MIN_PASSWORD_LEN} حروف على الأقل)', password=True, can_reveal_password=True, width=320)
        rep_f = ft.TextField(label='أعد كتابتها', password=True, can_reveal_password=True, width=320)
        err = ft.Text('', color=theme.DANGER, size=12)

        def save(ev):
            try:
                if new_f.value != rep_f.value:
                    raise ValueError('كلمتا المرور غير متطابقتين')
                services.set_current_user(user)          # عشان change_own_password تعرف مين المستخدم
                services.change_own_password(old_f.value, new_f.value)
                dlg.open = False
                services.set_current_user(None)
                x2 = services.authenticate_user(user['username'], new_f.value, second_factor=False)
                finish(x2)
            except Exception as ex:
                services.set_current_user(None)
                err.value = str(ex); page.update()
        dlg = ft.AlertDialog(modal=True, title=ft.Text('لازم تغيّر كلمة المرور الافتراضية'),
                             content=ft.Column([ft.Text('حساب المدير لسه بكلمة المرور الافتراضية، وده خطر على أي سيرفر. اختر كلمة مرور جديدة للمتابعة.', size=13), old_f, new_f, rep_f, err], tight=True, spacing=10, width=360),
                             actions=[ft.FilledButton('حفظ ومتابعة', on_click=save)])
        page.overlay.append(dlg); dlg.open = True; page.update()

    card = theme.card(
        ft.Column([
            ft.Image(src=brand.mark_png(256), width=128, height=128, fit=ft.BoxFit.CONTAIN),
            ft.Text('نظام ERP المالي والإداري', size=13, color=theme.TEXT_MUTED),
            ft.Text('سجّل الدخول للمتابعة', color=theme.TEXT_MUTED, size=13),
            ft.Container(height=10),
            user_f, pw_f, otp_f, status,
            ft.Container(height=4),
            ft.FilledButton('تسجيل الدخول', icon=ft.Icons.LOGIN, bgcolor=theme.PRIMARY, width=320, height=46, on_click=login),
            ft.TextButton('تثبيت التطبيق على الموبايل' if getattr(page, '_erp_lang', 'ar') == 'ar' else 'Install the app', icon=ft.Icons.INSTALL_MOBILE, url='/install.html'),
            ft.TextButton('English' if getattr(page, '_erp_lang', 'ar') == 'ar' else 'العربية', icon=ft.Icons.LANGUAGE, on_click=switch_lang),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12),
        padding=40,
    )

    page.clean()
    page.add(
        ft.Container(
            expand=True, alignment=ft.Alignment(0, 0),
            gradient=ft.LinearGradient(begin=ft.Alignment(-1, -1), end=ft.Alignment(1, 1),
                                       colors=[theme.SIDEBAR_BG, theme.PRIMARY_DARK, theme.SIDEBAR_BG_2]),
            content=card,
        )
    )
