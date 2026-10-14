"""شاشة الأمان للمستخدم: تغيير كلمة المرور + التحقق بخطوتين (QR + أكواد استرداد). بتتفتح من أيقونة الدرع في الشريط العلوي،
وبتتفتح إجباريًا عند الدخول لو ERP_REQUIRE_2FA مفعّل ولسه المستخدم ما فعّلش."""
import flet as ft
from .. import services, theme, twofa


def _close(page, dlg):
    dlg.open = False
    page.update()


def show_recovery_codes(page, codes, on_close=None):
    box = ft.Container(content=ft.Column([ft.Text(c, selectable=True, size=16, font_family="monospace") for c in codes], spacing=4),
                       padding=12, border_radius=8, bgcolor=theme.PRIMARY_LIGHT)
    dlg = ft.AlertDialog(modal=True, title=ft.Text("أكواد الاسترداد - احفظها دلوقتي"),
                         content=ft.Column([ft.Text("كل كود يتستخدم مرة واحدة لو ضاع تليفونك. مش هتظهر تاني.", size=13), box], tight=True, spacing=10, width=340))

    def done(e):
        _close(page, dlg)
        if on_close:
            on_close()
    dlg.actions = [ft.FilledButton("حفظتها", on_click=done)]
    page.overlay.append(dlg); dlg.open = True; page.update()


def setup_dialog(page, forced=False, on_done=None):
    """معالج التفعيل: امسح الـ QR (أو اكتب المفتاح) ← اكتب أول رمز ← أكواد الاسترداد."""
    try:
        data = twofa.begin_setup()
    except ValueError as ex:
        page.snack_bar = ft.SnackBar(ft.Text(str(ex))); page.snack_bar.open = True; page.update()
        return
    code_f = ft.TextField(label="الرمز المكوّن من 6 أرقام", width=300, autofocus=True, keyboard_type=ft.KeyboardType.NUMBER, max_length=6)
    err = ft.Text("", color=theme.DANGER, size=12)
    dlg = ft.AlertDialog(modal=True, title=ft.Text("تفعيل التحقق بخطوتين"))

    def confirm(e=None):
        try:
            codes = twofa.confirm_setup(code_f.value)
        except Exception as ex:
            err.value = str(ex); page.update(); return
        _close(page, dlg)
        show_recovery_codes(page, codes, on_close=on_done)
    code_f.on_submit = confirm
    dlg.content = ft.Column([
        ft.Text("1) افتح Google Authenticator أو Microsoft Authenticator وامسح الصورة، أو اكتب المفتاح يدويًا.", size=13),
        ft.Image(src=data["qr"], width=190, height=190),
        ft.Text(data["secret"], selectable=True, size=14, font_family="monospace"),
        ft.Text("2) اكتب الرمز اللي ظهر في التطبيق:", size=13), code_f, err,
    ], tight=True, spacing=8, width=360, horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.AUTO)
    dlg.actions = [ft.FilledButton("تأكيد وتفعيل", on_click=confirm)] + ([] if forced else [ft.TextButton("إلغاء", on_click=lambda e: _close(page, dlg))])
    page.overlay.append(dlg); dlg.open = True; page.update()


def open_security_dialog(page):
    st = twofa.status()
    msg = ft.Text("", size=12)
    old_f = ft.TextField(label="كلمة المرور الحالية", password=True, can_reveal_password=True, width=320)
    new_f = ft.TextField(label=f"كلمة المرور الجديدة ({services.MIN_PASSWORD_LEN} حروف على الأقل)", password=True, can_reveal_password=True, width=320)
    pw_tf = ft.TextField(label="كلمة المرور (للتأكيد)", password=True, can_reveal_password=True, width=320)
    dlg = ft.AlertDialog(modal=True, title=ft.Text("الأمان"))

    def say(text, ok=False):
        msg.value = text; msg.color = theme.SUCCESS if ok else theme.DANGER; page.update()

    def change_pw(e):
        try:
            services.change_own_password(old_f.value, new_f.value)
            old_f.value = new_f.value = ""
            say("تم تغيير كلمة المرور", True)
        except Exception as ex:
            say(str(ex))

    def reopen():
        _close(page, dlg); open_security_dialog(page)

    def disable(e):
        try:
            twofa.disable_self(pw_tf.value)
            reopen()
        except Exception as ex:
            say(str(ex))

    def regen(e):
        try:
            codes = twofa.regenerate_recovery(pw_tf.value)
            _close(page, dlg); show_recovery_codes(page, codes, on_close=lambda: open_security_dialog(page))
        except Exception as ex:
            say(str(ex))

    if st["enabled"]:
        tf = [ft.Text(f"✔ التحقق بخطوتين مفعّل - أكواد استرداد متبقية: {st['recovery_left']}", size=13, color=theme.SUCCESS), pw_tf,
              ft.Row([ft.OutlinedButton("أكواد استرداد جديدة", on_click=regen), ft.OutlinedButton("إيقاف التحقق", on_click=disable)], wrap=True)]
    else:
        tf = [ft.Text("التحقق بخطوتين بيحمي حسابك حتى لو كلمة المرور اتسرّبت.", size=13),
              ft.FilledButton("تفعيل التحقق بخطوتين", icon=ft.Icons.SECURITY, on_click=lambda e: (_close(page, dlg), setup_dialog(page, on_done=lambda: open_security_dialog(page))))]
    dlg.content = ft.Column([ft.Text("تغيير كلمة المرور", weight=ft.FontWeight.BOLD), old_f, new_f, ft.OutlinedButton("حفظ كلمة المرور", on_click=change_pw),
                             ft.Divider(), ft.Text("التحقق بخطوتين", weight=ft.FontWeight.BOLD), *tf, msg], tight=True, spacing=8, width=380, scroll=ft.ScrollMode.AUTO)
    dlg.actions = [ft.TextButton("إغلاق", on_click=lambda e: _close(page, dlg))]
    page.overlay.append(dlg); dlg.open = True; page.update()
