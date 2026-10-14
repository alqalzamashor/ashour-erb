import flet as ft
from .. import services, theme, promotions, loyalty


def discount_box(page, get_total, on_change=None, get_customer=None):
    """خانة خصم/كوبون للدفع: كوبون أو خصم يدوي (نسبة/مبلغ) + سبب، وبيطلب بيانات مدير لو الخصم فوق الحد.
    بيرجّع (control, get_spec, recalc, state): get_spec() بيرجّع spec للـ services (أو None) وبيتحقق من المدير؛ state['amount'] = قيمة الخصم الحالية."""
    state = {'amount': 0.0}
    coupon_f = ft.TextField(label='كوبون', width=140, dense=True, capitalization=ft.TextCapitalization.CHARACTERS)
    kind_dd = ft.Dropdown(label='خصم يدوي', width=130, value='', options=[ft.dropdown.Option('', 'بدون'), ft.dropdown.Option('percent', 'نسبة %'), ft.dropdown.Option('amount', 'مبلغ')])
    val_f = ft.TextField(label='القيمة', width=90, dense=True, keyboard_type=ft.KeyboardType.NUMBER)
    reason_f = ft.TextField(label='سبب الخصم', width=190, dense=True)
    mu_f = ft.TextField(label='مدير: المستخدم', width=140, dense=True, visible=False)
    mp_f = ft.TextField(label='كلمة المرور', width=140, dense=True, password=True, can_reveal_password=True, visible=False)
    pts_f = ft.TextField(label='استبدال نقاط ولاء', width=150, dense=True, keyboard_type=ft.KeyboardType.NUMBER, visible=False)
    loy_info = ft.Text('', size=12, color=theme.TEXT_MUTED, visible=False)
    info = ft.Text('', size=12)
    cfg_on = promotions.get_config()['manual_enabled']
    if not cfg_on:
        kind_dd.visible = val_f.visible = reason_f.visible = False
    can_approve = promotions._can_approve(services.current_user())

    def _loy():
        try:
            return loyalty.customer_info(get_customer()) if get_customer else None
        except Exception:
            return None

    def raw_spec():
        if (pts_f.value or '').strip():
            try:
                pv = float(pts_f.value)
            except ValueError:
                pv = 0
            if pv > 0:
                cid = get_customer()
                return {'points': pv, 'customer_id': int(cid) if cid else None}
        if (coupon_f.value or '').strip():
            return {'coupon': coupon_f.value.strip()}
        if kind_dd.value:
            try:
                v = float(val_f.value or 0)
            except ValueError:
                v = 0
            if v > 0:
                return {'manual_kind': kind_dd.value, 'manual_value': v, 'reason': reason_f.value or ''}
        return None

    def recalc(e=None):
        li = _loy()
        pts_f.visible = loy_info.visible = bool(li)
        if li:
            loy_info.value = f"{li['name']}: رصيد {li['balance']:,.0f} نقطة (كل نقطة = {li['redeem_value']:g}، أقل استبدال {li['min_redeem']:g}، حتى {li['max_pct']:g}% من الفاتورة)"
        elif pts_f.value:
            pts_f.value = ''
        using_pts = bool((pts_f.value or '').strip())
        spec = raw_spec()
        total = float(get_total() or 0)
        coupon_f.disabled = using_pts
        kind_dd.disabled = val_f.disabled = reason_f.disabled = using_pts or bool((coupon_f.value or '').strip())
        if not spec:
            state['amount'] = 0.0; info.value = ''; mu_f.visible = mp_f.visible = False
        else:
            p = promotions.preview(total, spec)
            state['amount'] = p['amount'] if (not p['error'] or p['needs_approval']) else 0.0
            need = p['needs_approval'] and not can_approve and not using_pts
            mu_f.visible = mp_f.visible = need
            if p['error'] and not (p['needs_approval'] and need and 'اعتماد' in p['error']):
                info.value = p['error']; info.color = theme.DANGER
                if 'سبب' not in p['error']:
                    state['amount'] = 0.0
            else:
                info.value = f"خصم {p['amount']:,.2f}  ←  الإجمالي بعد الخصم {total - p['amount']:,.2f}" + ('  (محتاج اعتماد مدير)' if need else '')
                info.color = theme.SUCCESS if not need else theme.WARNING
        if on_change:
            on_change()
        try:
            page.update()
        except Exception:
            pass

    for f in (coupon_f, val_f, reason_f, pts_f):
        f.on_change = recalc
    kind_dd.on_select = recalc

    def get_spec():
        spec = raw_spec()
        if not spec:
            return None
        if mu_f.visible:
            appr = services.authenticate_user(mu_f.value, mp_f.value, second_factor=False)
            if not appr:
                raise ValueError('بيانات المدير غير صحيحة')
            spec['approver'] = appr
        return spec

    def reset():
        coupon_f.value = val_f.value = reason_f.value = mu_f.value = mp_f.value = pts_f.value = ''
        kind_dd.value = ''
        recalc()

    ctrl = ft.Column([ft.Row([coupon_f, kind_dd, val_f, reason_f], wrap=True, spacing=8), ft.Row([mu_f, mp_f], wrap=True, spacing=8), ft.Row([pts_f], wrap=True), loy_info, info], spacing=6, tight=True)
    return ctrl, get_spec, recalc, state, reset
