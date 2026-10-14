import flet as ft
from .. import approvals, services, theme

COL = {'pending': 'WARNING', 'approved': 'SUCCESS', 'rejected': 'DANGER', 'consumed': 'TEXT_MUTED', 'cancelled': 'TEXT_MUTED'}


def build_approvals(page: ft.Page):
    """الموافقات: طلبات بانتظار قرارك (لو معتمِد)، طلباتي، وإعدادات الحدود."""
    services.require_action('approvals', 'view')
    me = services.current_user() or {}
    u = services._get_user()
    can_approve = services.user_has_action(u, 'approvals', 'approve')
    can_edit = services.user_has_action(u, 'approvals', 'edit')
    scope = ft.Dropdown(label='العرض', width=220, value='pending' if can_approve else 'mine',
                        options=[ft.dropdown.Option('pending', 'بانتظار الموافقة'), ft.dropdown.Option('mine', 'طلباتي'), ft.dropdown.Option('all', 'الكل')])
    col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)

    def snack(m, bad=False):
        page.overlay.append(ft.SnackBar(ft.Text(m), open=True, bgcolor=theme.DANGER if bad else None)); page.update()

    def decide(r, ok):
        note = ft.TextField(label='ملاحظة' + ('' if ok else ' (السبب مطلوب)'), width=360)

        def go(e):
            try:
                (approvals.approve if ok else approvals.reject)(r.id, note.value)
                dlg.open = False; refresh(); snack('تم')
            except Exception as ex:
                snack(str(ex), True)
        dlg = ft.AlertDialog(modal=True, title=ft.Text(('اعتماد' if ok else 'رفض') + f' الطلب #{r.id}'), content=note,
                             actions=[ft.TextButton('إلغاء', on_click=lambda e: (setattr(dlg, 'open', False), page.update())), ft.FilledButton('تأكيد', bgcolor=theme.SUCCESS if ok else theme.DANGER, on_click=go)])
        page.overlay.append(dlg); dlg.open = True; page.update()

    def cancel(r):
        try:
            approvals.cancel(r.id); refresh()
        except Exception as ex:
            snack(str(ex), True)

    def refresh(e=None):
        rows = approvals.list_requests(scope.value or 'mine')
        cards = []
        for r in rows:
            c = getattr(theme, COL.get(r.status, 'TEXT_MUTED'))
            acts = []
            if r.status == 'pending' and can_approve and r.requested_by != me.get('username'):
                acts += [ft.FilledButton('اعتماد', bgcolor=theme.SUCCESS, on_click=lambda ev, rr=r: decide(rr, True)), ft.OutlinedButton('رفض', on_click=lambda ev, rr=r: decide(rr, False))]
            if r.status in ('pending', 'approved') and r.requested_by == me.get('username'):
                acts.append(ft.TextButton('إلغاء الطلب', on_click=lambda ev, rr=r: cancel(rr)))
            cards.append(theme.card(ft.Column([
                ft.Row([ft.Container(content=ft.Text(approvals.STATUS.get(r.status, r.status), size=12, color='#FFFFFF', weight=ft.FontWeight.BOLD), bgcolor=c, border_radius=10, padding=ft.Padding(left=8, right=8, top=2, bottom=2)),
                        ft.Text(f"#{r.id}  {approvals.KINDS.get(r.kind, r.kind)}", weight=ft.FontWeight.BOLD), ft.Text(f"{r.amount:,.2f}", weight=ft.FontWeight.BOLD, color=theme.PRIMARY),
                        ft.Container(expand=True), ft.Text(f"{r.created_at:%m-%d %H:%M}", size=12, color=theme.TEXT_MUTED)]),
                ft.Text(f"طلب من: {r.requested_by}" + (f"  •  {r.summary}" if r.summary else ''), size=12),
                *([ft.Text(f"ملاحظة: {r.note}", size=12, color=theme.TEXT_MUTED)] if r.note else []),
                *([ft.Text(f"القرار: {r.decided_by} - {r.decision_note or ''}", size=12, color=theme.TEXT_MUTED)] if r.decided_by else []),
                ft.Row(acts, spacing=8)], spacing=4), padding=12))
        col.controls = cards or [ft.Text('مفيش طلبات', color=theme.TEXT_MUTED)]
        if e is not None:
            page.update()
    scope.on_select = refresh

    cfg = approvals.get_config()
    sw, th = {}, {}
    exp = ft.TextField(label='صلاحية الموافقة (ساعة)', width=180, value=str(cfg['expiry_hours']))
    set_rows = []
    for k, v in cfg['kinds'].items():
        sw[k] = ft.Switch(label=approvals.KINDS[k], value=v['enabled'], width=240)
        th[k] = ft.TextField(label='الحد (يبدأ من)', width=150, value=f"{v['threshold']:g}")
        set_rows.append(ft.Row([sw[k], th[k]]))
    msg = ft.Text('', size=12)

    def save(e):
        try:
            approvals.save_config(expiry_hours=exp.value, kinds={k: {'enabled': sw[k].value, 'threshold': th[k].value or 0} for k in sw})
            msg.value = 'اتحفظ'; msg.color = theme.SUCCESS
        except Exception as ex:
            msg.value = str(ex); msg.color = theme.DANGER
        page.update()
    refresh()
    return ft.Column([
        theme.page_title('الموافقات', 'عمليات كبيرة بتتعلّق لحد ما مدير يعتمدها؛ بعد الاعتماد المنفّذ يعيد نفس العملية'),
        ft.Row([scope, ft.IconButton(ft.Icons.REFRESH, on_click=refresh)]),
        ft.ExpansionTile(title=ft.Text('الحدود والإعدادات'), controls=[ft.Container(padding=10, content=ft.Column(set_rows + [exp, ft.Row([ft.FilledButton('حفظ', on_click=save, bgcolor=theme.PRIMARY, disabled=not can_edit), msg]),
                         ft.Text('البيع الآجل فوق حد الائتمان بيحتاج موافقة دايمًا. اللي معاه صلاحية «اعتماد» بيعدّي مباشرة (وبيتسجّل في سجل التدقيق).', size=11.5, color=theme.TEXT_MUTED)], spacing=8))]),
        col,
    ], expand=True, spacing=10)
