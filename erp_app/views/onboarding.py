import flet as ft
from .. import onboarding, services, theme


def onboarding_card(page, on_change):
    """كارت «البداية السريعة» للمدير في اللوحة الرئيسية، أو None لو كله خلص/اتقفل."""
    me = services.current_user() or {}
    if me.get('role') != 'admin' or onboarding.dismissed():
        return None
    done, total = onboarding.progress()
    if done == total:
        return None
    goto = getattr(page, '_erp_goto', None)
    rows = []
    for st in onboarding.steps():
        ok = st['done']
        col = theme.SUCCESS if ok else theme.PRIMARY
        can = (not ok) and st['goto'] and goto
        rows.append(ft.Container(
            ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE if ok else ft.Icons.ARROW_CIRCLE_LEFT_OUTLINED, size=17, color=col),
                    ft.Text(st['label'], size=12.5, color=theme.TEXT_MUTED if ok else theme.TEXT)], spacing=7, tight=True),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8), border_radius=20, bgcolor=ft.Colors.with_opacity(0.10 if ok else 0.07, col),
            border=ft.border.Border(*(ft.border.BorderSide(1, ft.Colors.with_opacity(0.35, col)) for _ in range(4))),
            ink=bool(can), on_click=(lambda e, g=st['goto']: goto(g)) if can else None))
    rows = [ft.Row(rows, wrap=True, spacing=8, run_spacing=8)]
    msg = ft.Text('', size=12, color=theme.DANGER, visible=False)

    def hide(e):
        onboarding.dismiss(); on_change()

    def demo(e):
        try:
            r = onboarding.load_demo()
            on_change()
            page.overlay.append(ft.SnackBar(ft.Text(f"اتحمّلت بيانات تجريبية: {r['products']} صنف و{r['sales']} فاتورة بيع"), open=True)); page.update()
        except Exception as ex:
            msg.value = str(ex); msg.visible = True; page.update()
    actions = [ft.TextButton('إخفاء', on_click=hide)]
    if not onboarding.has_activity():
        actions.insert(0, ft.OutlinedButton('حمّل بيانات تجريبية للتجربة', icon=ft.Icons.AUTO_AWESOME_OUTLINED, on_click=demo))
    return theme.card(ft.Column([
        ft.Row([ft.Text('البداية السريعة', size=15, weight=ft.FontWeight.W_800), ft.Container(expand=True), ft.Text(f'{done} من {total}', size=12, color=theme.TEXT_MUTED)]),
        ft.ProgressBar(value=done / total, color=theme.PRIMARY, bgcolor=theme.PRIMARY_LIGHT), *rows, msg, ft.Row(actions, spacing=8, wrap=True)], spacing=8))
