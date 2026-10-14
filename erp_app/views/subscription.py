import flet as ft
from .. import services, theme, trial


def _usage():
    from ..db import Branch, User, get_session
    with get_session() as s:
        return (s.query(User).filter(User.is_active.is_(True)).count(), s.query(Branch).filter(Branch.is_active.is_(True)).count())


def build_subscription(page: ft.Page):
    """حالة الاشتراك/التجربة، حدود الباقة، وتفعيل كود اشتراك."""
    services.require_action('subscription', 'view')
    box = ft.Column(spacing=14)
    code_f = ft.TextField(label='كود التفعيل', hint_text='ERP-XXXX-XXXX-XXXX', width=300, dense=True, text_align=ft.TextAlign.LEFT, capitalization=ft.TextCapitalization.CHARACTERS)
    msg = ft.Text('', size=13, visible=False)

    def stat(label, value, color=None):
        return theme.card(ft.Column([ft.Text(label, size=12, color=theme.TEXT_MUTED), ft.Text(str(value), size=20, weight=ft.FontWeight.BOLD, color=color)], spacing=2, tight=True), padding=14)

    def render():
        i = trial.info()
        if not i:
            box.controls = [theme.card(ft.Text('النسخة دي بدون اشتراك محدد المدة (ترخيص مفتوح).', size=14))]
            return
        users, branches = _usage()
        dl = i['days_left']
        col = theme.DANGER if dl is not None and dl <= 5 else (theme.SUCCESS if i['paid'] else theme.PRIMARY)
        lim = lambda v: 'بلا حد' if v is None else str(v)
        box.controls = [
            ft.Row([stat('الباقة', i['plan_label'] + (' (مدفوعة)' if i['paid'] else ' (تجريبية)'), col), stat('ينتهي في', i['expires'], col),
                    stat('الأيام المتبقية', max(dl, 0) if dl is not None else '-', col)], wrap=True, spacing=12),
            ft.Row([stat('المستخدمون', f"{users} / {lim(i['max_users'])}"), stat('الفروع', f"{branches} / {lim(i['max_branches'])}")], wrap=True, spacing=12),
        ]

    def show(text, ok):
        msg.value = text; msg.color = theme.SUCCESS if ok else theme.DANGER; msg.visible = True; page.update()

    def do_activate(e):
        try:
            services.require_action('subscription', 'edit')
            res = trial.activate(code_f.value)
            code_f.value = ''
            render()
            try:
                getattr(page, '_erp_refresh_trial', lambda: None)()
            except Exception:
                pass
            show(f"تم التفعيل: باقة {res.get('plan_label', '')} حتى {res.get('expires', '')}", True)
        except Exception as ex:
            show(str(ex), False)

    render()
    act = theme.card(ft.Column([
        ft.Text('تفعيل أو تجديد الاشتراك', size=16, weight=ft.FontWeight.BOLD),
        ft.Text('أدخل كود التفعيل اللي استلمته من مزوّد الخدمة. بيتضاف على المدة الحالية (مفيش حاجة بتضيع).', size=12, color=theme.TEXT_MUTED),
        ft.Row([code_f, ft.FilledButton('تفعيل', icon=ft.Icons.VERIFIED_OUTLINED, bgcolor=theme.PRIMARY, on_click=do_activate)], spacing=10, wrap=True),
        msg,
    ], spacing=10)) if trial.can_activate() else theme.card(ft.Text('لتفعيل الاشتراك تواصل مع مزوّد الخدمة.', size=13, color=theme.TEXT_MUTED))
    return ft.Column([theme.page_title('الاشتراك'), box, act], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)
