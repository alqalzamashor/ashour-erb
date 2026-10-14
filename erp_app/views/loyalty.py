import flet as ft
from .. import services, theme, loyalty


def build_loyalty(page: ft.Page):
    """برنامج الولاء: الإعدادات (معدل الاكتساب وقيمة النقطة)، الأعضاء وأرصدتهم، كشف نقاط العميل، وتسوية يدوية."""
    services.require_action('loyalty', 'view')
    cfg = loyalty.get_config()
    on_sw = ft.Switch(label='تفعيل برنامج الولاء', value=bool(cfg['enabled']))
    earn_f = ft.TextField(label='نقاط لكل 1 ريال', width=150, dense=True, value=f"{cfg['earn_per_currency']:g}", keyboard_type=ft.KeyboardType.NUMBER)
    val_f = ft.TextField(label='قيمة النقطة (ريال)', width=160, dense=True, value=f"{cfg['redeem_value']:g}", keyboard_type=ft.KeyboardType.NUMBER)
    min_f = ft.TextField(label='أقل نقاط للاستبدال', width=170, dense=True, value=f"{cfg['min_redeem']:g}", keyboard_type=ft.KeyboardType.NUMBER)
    pct_f = ft.TextField(label='أقصى استبدال % من الفاتورة', width=210, dense=True, value=f"{cfg['max_redeem_pct']:g}", keyboard_type=ft.KeyboardType.NUMBER)
    msg = ft.Text('', size=12, visible=False)
    search = ft.TextField(label='بحث بالاسم أو الهاتف', width=260, dense=True)
    show_all = ft.Checkbox(label='إظهار غير الأعضاء', value=False)
    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x, weight=ft.FontWeight.BOLD)) for x in ['العميل', 'الهاتف', 'العضوية', 'الرصيد', 'إجمالي المكتسب', 'قيمة الرصيد', '']], rows=[])

    def snack(t):
        page.overlay.append(ft.SnackBar(ft.Text(t), open=True)); page.update()

    def save_cfg(e):
        try:
            loyalty.save_config(enabled=on_sw.value, earn_per_currency=earn_f.value, redeem_value=val_f.value, min_redeem=min_f.value, max_redeem_pct=pct_f.value)
            msg.value = 'تم الحفظ'; msg.color = theme.SUCCESS
        except Exception as ex:
            msg.value = str(ex); msg.color = theme.DANGER
        msg.visible = True; refresh(); page.update()

    def refresh(e=None):
        v = loyalty.get_config()['redeem_value']
        rows = []
        for m in loyalty.list_members(search.value, only_enabled=not show_all.value):
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(m['name'], size=12)), ft.DataCell(ft.Text(m['phone'] or '-', size=12)),
                ft.DataCell(ft.Switch(value=m['member'], on_change=lambda ev, x=m: toggle(x, ev.control.value))),
                ft.DataCell(ft.Text(f"{m['balance']:,.0f}", weight=ft.FontWeight.BOLD, size=12)), ft.DataCell(ft.Text(f"{m['earned_total']:,.0f}", size=12)),
                ft.DataCell(ft.Text(f"{m['balance'] * v:,.2f}", size=12)),
                ft.DataCell(ft.Row([ft.IconButton(ft.Icons.RECEIPT_LONG_OUTLINED, tooltip='كشف النقاط', on_click=lambda ev, x=m: statement(x)),
                                    ft.IconButton(ft.Icons.TUNE, tooltip='تسوية يدوية', on_click=lambda ev, x=m: adjust_dlg(x))], spacing=0))]))
        table.rows = rows

    def toggle(m, val):
        try:
            loyalty.set_member(m['id'], val)
        except Exception as ex:
            snack(str(ex))
        refresh(); page.update()

    def statement(m):
        t = ft.DataTable(columns=[ft.DataColumn(ft.Text(x, weight=ft.FontWeight.BOLD)) for x in ['التاريخ', 'النوع', 'النقاط', 'الرصيد', 'المرجع', 'ملاحظة', 'بواسطة']],
                         rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(f"{x['at']:%Y-%m-%d %H:%M}", size=11)), ft.DataCell(ft.Text(x['kind_label'], size=11)),
                                                 ft.DataCell(ft.Text(f"{x['points']:+,.0f}", size=11, color=theme.SUCCESS if x['points'] > 0 else theme.DANGER, weight=ft.FontWeight.BOLD)),
                                                 ft.DataCell(ft.Text(f"{x['balance']:,.0f}", size=11)), ft.DataCell(ft.Text(x['ref'] or '-', size=11)), ft.DataCell(ft.Text(x['note'] or '', size=11)),
                                                 ft.DataCell(ft.Text(x['by'] or '', size=11))]) for x in loyalty.list_txns(m['id'])])
        dlg = ft.AlertDialog(modal=True, title=ft.Text(f"كشف نقاط: {m['name']}"), content=ft.Container(width=760, height=420, content=ft.Column([theme.h_scroll(t)], scroll=ft.ScrollMode.AUTO)),
                             actions=[ft.TextButton('إغلاق', on_click=lambda ev: (setattr(dlg, 'open', False), page.update()))])
        page.overlay.append(dlg); dlg.open = True; page.update()

    def adjust_dlg(m):
        pts = ft.TextField(label='النقاط (موجب للإضافة / سالب للخصم)', width=300, keyboard_type=ft.KeyboardType.NUMBER)
        note = ft.TextField(label='السبب *', width=300)
        err = ft.Text('', color=theme.DANGER, visible=False)

        def ok(ev):
            try:
                loyalty.adjust(m['id'], pts.value, note.value)
                dlg.open = False; refresh(); page.update()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()
        dlg = ft.AlertDialog(modal=True, title=ft.Text(f"تسوية نقاط: {m['name']} (الرصيد {m['balance']:,.0f})"), content=ft.Column([pts, note, err], tight=True, spacing=10, width=320),
                             actions=[ft.TextButton('إلغاء', on_click=lambda ev: (setattr(dlg, 'open', False), page.update())), theme.guard_submit(ft.FilledButton('تسوية', bgcolor=theme.PRIMARY, on_click=ok))])
        page.overlay.append(dlg); dlg.open = True; page.update()

    search.on_change = refresh
    show_all.on_change = refresh
    refresh()
    return ft.Column([
        theme.page_title('برنامج الولاء', 'العميل العضو بيكسب نقاط على كل بيع (كاشير ومطعم) ويستبدلها كخصم عند الدفع'),
        theme.card(ft.Column([ft.Text('الإعدادات', size=15, weight=ft.FontWeight.BOLD), ft.Row([on_sw, earn_f, val_f, min_f, pct_f, ft.FilledButton('حفظ', on_click=save_cfg), msg], wrap=True, spacing=12),
                              ft.Text('النقاط بتتحسب على إجمالي الفاتورة بعد الخصم. المرتجع بيعكس النقاط بنفس النسبة. عضوية العميل بتتفعّل من شاشة العملاء أو من هنا.', size=11, color=theme.TEXT_MUTED)], spacing=8)),
        theme.card(ft.Column([ft.Row([search, show_all], wrap=True, spacing=12), theme.h_scroll(table)], spacing=8), expand=True),
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
