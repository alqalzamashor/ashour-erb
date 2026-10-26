import datetime
import os
import flet as ft
from .. import services, theme


def _money(v):
    return f'{(v or 0):,.2f}'


def _fmt_dt(d):
    return d.strftime('%Y-%m-%d %H:%M') if d else '-'


def _snack(page, msg):
    page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()


def open_session_dialog(page, terminal, on_done=None):
    """فتح جلسة جديدة للماكينة: العهدة الافتتاحية (النقدية اللي في الدرج) وملاحظات."""
    cash = ft.TextField(label='العهدة الافتتاحية (النقدية في الدرج)', width=300, value='0', keyboard_type=ft.KeyboardType.NUMBER, autofocus=True)
    notes = ft.TextField(label='ملاحظات (اختياري)', width=300)
    err = ft.Text('', color=theme.DANGER, visible=False, size=12)

    def close(e=None):
        dlg.open = False; page.update()

    def do_open(e):
        try:
            sid = services.open_pos_session(terminal['id'], cash.value or 0, notes.value or '')
            close()
            if on_done:
                on_done(sid)
        except Exception as ex:
            err.value = str(ex); err.visible = True; page.update()
    cash.on_submit = do_open
    info = ft.Column([ft.Text(f"{terminal['code']} - {terminal['name']}", weight=ft.FontWeight.BOLD),
                      ft.Text('  |  '.join(x for x in [f"الكاشير: {terminal['employee']}" if terminal['employee'] else '', f"الفرع: {terminal['branch']}" if terminal['branch'] else '',
                                                          f"المخزن: {terminal['location']}" if terminal['location'] else ''] if x) or 'الإعدادات الافتراضية', size=12, color=theme.TEXT_MUTED)], spacing=2, tight=True)
    dlg = ft.AlertDialog(modal=True, title=ft.Text('فتح جلسة جديدة'), content=ft.Container(width=340, content=ft.Column([info, cash, notes, err], tight=True, spacing=12)),
                         actions=[ft.TextButton('إلغاء', on_click=close), theme.guard_submit(ft.FilledButton('فتح الجلسة', icon=ft.Icons.LOCK_OPEN_OUTLINED, bgcolor=theme.PRIMARY, on_click=do_open))])
    page.overlay.append(dlg); dlg.open = True; page.update()


def close_session_dialog(page, session_id, on_done=None):
    """إغلاق الجلسة: بيعرض النقدية المتوقعة، والكاشير بيكتب النقدية اللي عدّها، والفرق بيظهر فورًا."""
    try:
        r = services.pos_session_report(session_id)
    except Exception as ex:
        _snack(page, str(ex)); return
    expected = r['expected_cash_now']
    open_orders = services.list_open_restaurant_orders(session_id=session_id)
    counted = ft.TextField(label='النقدية المعدودة فعليًا', width=300, keyboard_type=ft.KeyboardType.NUMBER, autofocus=True)
    notes = ft.TextField(label='ملاحظات الإغلاق (اختياري)', width=300)
    diff = ft.Text('', size=14, weight=ft.FontWeight.BOLD)
    err = ft.Text('', color=theme.DANGER, visible=False, size=12)

    def on_count(e=None):
        try:
            v = float(counted.value)
        except (TypeError, ValueError):
            diff.value = ''; page.update(); return
        d = v - expected
        diff.value = 'مطابق ✓' if abs(d) < 0.005 else (f'زيادة {d:,.2f}' if d > 0 else f'عجز {-d:,.2f}')
        diff.color = theme.SUCCESS if abs(d) < 0.005 else (theme.WARNING if d > 0 else theme.DANGER)
        page.update()
    counted.on_change = on_count

    def close(e=None):
        dlg.open = False; page.update()

    def do_close(e):
        try:
            rep = services.close_pos_session(session_id, counted.value, notes.value or '')
            close()
            if on_done:
                on_done(rep)
        except Exception as ex:
            err.value = str(ex); err.visible = True; page.update()
    counted.on_submit = do_close
    t = r['totals']
    body = ft.Column([
        ft.Text(f"{r['number']} - {r['terminal']}", weight=ft.FontWeight.BOLD), ft.Text(f"فُتحت {_fmt_dt(r['opened_at'])} بواسطة {r['opened_by_name']}", size=12, color=theme.TEXT_MUTED),
        ft.Divider(height=8),
        ft.Row([ft.Text('عدد الفواتير'), ft.Container(expand=True), ft.Text(str(t['count']))]),
        ft.Row([ft.Text('إجمالي المبيعات'), ft.Container(expand=True), ft.Text(_money(t['total']), weight=ft.FontWeight.BOLD)]),
        *[ft.Row([ft.Text(f"  {m['name']}" + (' (نقدي)' if m['is_cash'] else ''), size=12, color=theme.TEXT_MUTED), ft.Container(expand=True), ft.Text(_money(m['total']), size=12)]) for m in r['payment_methods']],
        ft.Divider(height=8),
        ft.Row([ft.Text('العهدة الافتتاحية'), ft.Container(expand=True), ft.Text(_money(r['opening_cash']))]),
        ft.Row([ft.Text('المبيعات النقدية'), ft.Container(expand=True), ft.Text(_money(r['cash_sales']))]),
        ft.Row([ft.Text('النقدية المتوقعة في الدرج', weight=ft.FontWeight.BOLD), ft.Container(expand=True), ft.Text(_money(expected), weight=ft.FontWeight.BOLD, color=theme.PRIMARY_TEXT)]),
        ft.Container(visible=bool(open_orders), padding=10, border_radius=8, bgcolor=theme.DANGER_LIGHT,
                     content=ft.Text(f"فيه {len(open_orders)} فاتورة/طلب مفتوح لسه ما اتدفعش - لازم تُدفع أو تُلغى قبل الإغلاق: " + "، ".join(o['number'] for o in open_orders[:8]), size=12, color=theme.DANGER, weight=ft.FontWeight.BOLD)),
        counted, diff, notes, err], tight=True, spacing=8, scroll=ft.ScrollMode.AUTO)
    dlg = ft.AlertDialog(modal=True, title=ft.Text('إغلاق الجلسة'), content=ft.Container(width=380, content=body),
                         actions=[ft.TextButton('إلغاء', on_click=close), theme.guard_submit(ft.FilledButton('إغلاق الجلسة', icon=ft.Icons.LOCK_OUTLINE, bgcolor=theme.DANGER, on_click=do_close, disabled=bool(open_orders)))])
    page.overlay.append(dlg); dlg.open = True; page.update()


def _return_status_chip(status, returned_total=0.0):
    if status == 'full':
        return ft.Text('مرتجعة كليًا', color=theme.DANGER, weight=ft.FontWeight.BOLD, size=12)
    if status == 'partial':
        return ft.Text(f'مرتجع جزئي {_money(returned_total)}', color=theme.WARNING, weight=ft.FontWeight.BOLD, size=12)
    return ft.Text('سارية', color=theme.SUCCESS, size=12)


def return_dialog(page, detail, mode='full', item_id=None, on_done=None):
    """مرتجع على فاتورة: full = كل المتبقي، item = صنف واحد، pick = اختيار الأصناف والكميات. السبب إجباري، وطريقة الرد الافتراضية نفس طريقة دفع الفاتورة.
    الفاتورة الأصلية ما بتتحذفش ولا بتتلغي - المرتجع بيتسجّل عليها ويظهر في تقرير الجلسة."""
    items = [i for i in detail['items'] if i['remaining_qty'] > 1e-9 and (mode != 'item' or i['id'] == item_id)]
    if not items:
        _snack(page, 'مفيش كميات متبقية للمرتجع'); return
    fields = {}
    rows = []
    for i in items:
        f = ft.TextField(width=90, dense=True, text_align=ft.TextAlign.CENTER, keyboard_type=ft.KeyboardType.NUMBER, value=(f"{i['remaining_qty']:g}" if mode in ('full', 'item') else '0'), disabled=(mode == 'full'))
        fields[i['id']] = f
        rows.append(ft.Row([ft.Column([ft.Text(i['name'], weight=ft.FontWeight.BOLD, size=13), ft.Text(f"{i['sku']}  |  {i['unit']}  |  سعر {i['unit_price']:,.2f}", size=10.5, color=theme.TEXT_MUTED)], spacing=0, expand=True),
                            ft.Text(f"اتباع {i['qty']:g}", size=12, width=70), ft.Text(f"المتبقي {i['remaining_qty']:g}", size=12, width=85, color=theme.TEXT_MUTED), f], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER))
    reason = ft.TextField(label='سبب المرتجع *', width=460, multiline=False)
    me_methods = services.list_payment_methods(active_only=True)
    orig = detail['payment_method']
    refund_dd = ft.Dropdown(label='طريقة رد المبلغ', width=300, value='', options=[ft.dropdown.Option('', f'نفس طريقة دفع الفاتورة ({orig})')] + [ft.dropdown.Option(str(m.id), m.name + (' (آجل - على حساب العميل)' if m.is_credit else '')) for m in me_methods])
    total_txt = ft.Text('', weight=ft.FontWeight.BOLD, size=15, color=theme.DANGER)
    err = ft.Text('', color=theme.DANGER, visible=False, size=12)

    def recalc(e=None):
        t = 0.0
        for i in items:
            try:
                q = float(fields[i['id']].value or 0)
            except ValueError:
                q = 0.0
            if 0 < q <= i['remaining_qty'] + 1e-9:
                t += i['line_total'] / i['qty'] * q
        total_txt.value = f'إجمالي المرتجع (شامل الضريبة): {t:,.2f}'
        page.update()
    for f in fields.values():
        f.on_change = recalc
    recalc()

    def close(e=None):
        dlg.open = False; page.update()

    def do_return(e):
        try:
            lines = []
            for i in items:
                try:
                    q = float(fields[i['id']].value or 0)
                except ValueError:
                    raise ValueError(f"«{i['name']}»: الكمية مش رقم")
                if q > 0:
                    lines.append({'invoice_item_id': i['id'], 'quantity': q})
            rid = services.create_sales_return(detail['id'], lines, reason.value, int(refund_dd.value) if refund_dd.value else None, is_full=(mode == 'full'))
            close()
            _snack(page, 'تم تسجيل المرتجع')
            if on_done:
                on_done(rid)
        except Exception as ex:
            err.value = str(ex); err.visible = True; page.update()
    title = {'full': 'مرتجع كامل للفاتورة', 'item': 'مرتجع صنف', 'pick': 'مرتجع جزئي'}[mode]
    dlg = ft.AlertDialog(modal=True, title=ft.Text(f"{title} {detail['number']}"), content=ft.Container(width=640, content=ft.Column([
        ft.Text('الفاتورة الأصلية بتفضل زي ما هي (مفيش حذف نهائي)، والمرتجع بيرجّع المخزون ويسجّل قيد عكسي ويظهر في تقرير الجلسة.', size=12, color=theme.TEXT_MUTED),
        *rows, reason, refund_dd, total_txt, err], spacing=10, scroll=ft.ScrollMode.AUTO, height=min(560, 260 + 58 * len(rows)))),
        actions=[ft.TextButton('إلغاء', on_click=close), theme.guard_submit(ft.FilledButton('تنفيذ المرتجع', icon=ft.Icons.KEYBOARD_RETURN, bgcolor=theme.DANGER, on_click=do_return))])
    page.overlay.append(dlg); dlg.open = True; page.update()


def return_preview_dialog(page, return_id):
    try:
        d = services.get_sales_return(return_id)
    except Exception as ex:
        _snack(page, str(ex)); return
    def info(label, value):
        return ft.Container(bgcolor=theme.PRIMARY_LIGHT, border_radius=8, padding=ft.Padding(left=10, right=10, top=5, bottom=5),
                            content=ft.Column([ft.Text(label, size=10.5, color=theme.TEXT_MUTED), ft.Text(str(value), weight=ft.FontWeight.BOLD, size=12.5)], spacing=0, tight=True))
    rows = [ft.DataRow(cells=[ft.DataCell(ft.Text(f"{i['sku']} - {i['name']}")), ft.DataCell(ft.Text(i['unit'])), ft.DataCell(ft.Text(f"{i['qty']:g}")), ft.DataCell(ft.Text(_money(i['unit_price']))), ft.DataCell(ft.Text(_money(i['line_total']), weight=ft.FontWeight.BOLD))]) for i in d['items']]
    tbl = ft.DataTable(columns=[ft.DataColumn(ft.Text(c), numeric=n) for c, n in (('الصنف', False), ('الوحدة', False), ('الكمية', True), ('سعر الوحدة', True), ('الإجمالي', True))], rows=rows, column_spacing=24)

    def do_print(e):
        try:
            theme.open_or_download_file(page, services.print_sales_return(return_id))
        except Exception as ex:
            _snack(page, f'تعذرت الطباعة: {ex}')
    dlg = ft.AlertDialog(modal=True, title=ft.Text(f"مرتجع {d['number']}"), content=ft.Container(width=760, content=ft.Column([
        ft.Row([info('على الفاتورة', d['invoice_number']), info('التاريخ', f"{d['date']:%Y-%m-%d %H:%M}"), info('العميل', d['customer']), info('طريقة الرد', d['refund_method']), info('بواسطة', d['processed_by_name']),
                info('النوع', 'مرتجع كامل' if d['is_full'] else 'مرتجع جزئي')], wrap=True, spacing=8),
        ft.Text(f"السبب: {d['reason']}", size=12.5), theme.h_scroll(tbl),
        ft.Row([ft.Text(f"قبل الضريبة {_money(d['subtotal'])}"), ft.Text(f"الضريبة {_money(d['tax'])}"), ft.Text(f"الإجمالي {_money(d['total'])}", weight=ft.FontWeight.BOLD, color=theme.DANGER)], spacing=24)], spacing=10, scroll=ft.ScrollMode.AUTO, height=420)),
        actions=[ft.FilledButton('طباعة', icon=ft.Icons.PRINT_OUTLINED, bgcolor=theme.PRIMARY, on_click=do_print), ft.TextButton('إغلاق', on_click=lambda e: (setattr(dlg, 'open', False), page.update()))])
    page.overlay.append(dlg); dlg.open = True; page.update()


def invoice_preview_dialog(page, invoice_id, on_changed=None):
    """معاينة فاتورة: بياناتها وأصنافها وما اترجّع منها، ولو المستخدم مدير (صلاحية المرتجعات) يقدر يرجّع صنف أو الفاتورة كلها (من غير حذف)."""
    try:
        d = services.get_invoice_for_return(invoice_id)
    except Exception as ex:
        _snack(page, str(ex)); return
    can = services.can_return() and not d['voided']

    def refresh_all(rid=None):
        dlg.open = False; page.update()
        invoice_preview_dialog(page, invoice_id, on_changed)
        if on_changed:
            on_changed()

    def info(label, value):
        return ft.Container(bgcolor=theme.PRIMARY_LIGHT, border_radius=8, padding=ft.Padding(left=10, right=10, top=5, bottom=5),
                            content=ft.Column([ft.Text(label, size=10.5, color=theme.TEXT_MUTED), ft.Text(str(value), weight=ft.FontWeight.BOLD, size=12.5)], spacing=0, tight=True))
    head = [info('رقم الفاتورة', d['number']), info('التاريخ', f"{d['date']:%Y-%m-%d %H:%M}"), info('العميل', d['customer']), info('طريقة الدفع', d['payment_method'])]
    if d['terminal']:
        head.append(info('الماكينة', d['terminal']))
    if d['session']:
        head.append(info('الجلسة', d['session']))
    status_txt = {'none': 'سارية', 'partial': 'مرتجع جزئي', 'full': 'مرتجعة كليًا'}[d['status']]
    head.append(info('الحالة', 'ملغاة' if d['voided'] else status_txt))

    def item_row(i):
        acts = [ft.TextButton('مرتجع', icon=ft.Icons.KEYBOARD_RETURN, style=ft.ButtonStyle(color=theme.DANGER), on_click=lambda e, x=i: return_dialog(page, d, 'item', x['id'], refresh_all))] if (can and i['remaining_qty'] > 1e-9) else []
        return ft.DataRow(color=ft.Colors.with_opacity(0.06, theme.DANGER) if i['remaining_qty'] <= 1e-9 else None, cells=[
            ft.DataCell(ft.Text(i['sku'])), ft.DataCell(ft.Text(i['name'], weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(i['unit'])), ft.DataCell(ft.Text(f"{i['qty']:g}")), ft.DataCell(ft.Text(_money(i['unit_price']))),
            ft.DataCell(ft.Text(_money(i['discount']) if i['discount'] else '-')), ft.DataCell(ft.Text(f"{i['tax_rate']:g}%")), ft.DataCell(ft.Text(_money(i['line_total']), weight=ft.FontWeight.BOLD)),
            ft.DataCell(ft.Text(f"{i['returned_qty']:g}" if i['returned_qty'] else '-', color=theme.DANGER if i['returned_qty'] else None, weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(f"{i['remaining_qty']:g}")), ft.DataCell(ft.Row(acts, spacing=0))])
    tbl = ft.DataTable(columns=[ft.DataColumn(ft.Text(c), numeric=n) for c, n in (('الكود', False), ('الصنف', False), ('الوحدة', False), ('الكمية', True), ('السعر', True), ('الخصم', True), ('الضريبة', True), ('الإجمالي', True), ('المرتجع', True), ('المتبقي', True), ('', False))],
                       rows=[item_row(i) for i in d['items']], column_spacing=14, horizontal_margin=8)
    ret_rows = [ft.DataRow(cells=[ft.DataCell(ft.Text(r['number'], weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(f"{r['date']:%Y-%m-%d %H:%M}", size=12)), ft.DataCell(ft.Text('كلي' if r['is_full'] else 'جزئي')),
                                  ft.DataCell(ft.Text(r['refund_method'], size=12)), ft.DataCell(ft.Text(r['reason'], size=12)), ft.DataCell(ft.Text(_money(r['total']), color=theme.DANGER, weight=ft.FontWeight.BOLD)),
                                  ft.DataCell(ft.TextButton('عرض', on_click=lambda e, i=r['id']: return_preview_dialog(page, i)))]) for r in d['returns']]
    ret_tbl = ft.DataTable(columns=[ft.DataColumn(ft.Text(c), numeric=(c == 'المبلغ')) for c in ('المرتجع', 'التاريخ', 'النوع', 'طريقة الرد', 'السبب', 'المبلغ', '')], rows=ret_rows, column_spacing=16)
    totals = ft.Row([ft.Text(f"قبل الضريبة {_money(d['subtotal'])}"), ft.Text(f"الضريبة {_money(d['tax'])}"), ft.Text(f"الإجمالي {_money(d['total'])}", weight=ft.FontWeight.BOLD),
                     *([ft.Text(f"المرتجع {_money(d['returned_total'])}", color=theme.DANGER, weight=ft.FontWeight.BOLD), ft.Text(f"الصافي {_money(d['total'] - d['returned_total'])}", color=theme.PRIMARY_TEXT, weight=ft.FontWeight.BOLD)] if d['returns'] else [])], spacing=22, wrap=True)

    def do_print_invoice(e):
        try:
            theme.open_or_download_file(page, services.generate_invoice_pdf_file(d['id']))
        except Exception as ex:
            _snack(page, f'تعذرت الطباعة: {ex}')
    remaining_any = any(i['remaining_qty'] > 1e-9 for i in d['items'])
    note = ft.Text('فواتير الكاشير مينفعش تتحذف أو تتلغي - الإلغاء بيتم بمرتجع (كلي أو جزئي) من المدير.' + ('' if can else ' صلاحية المرتجع للمدير بس.'), size=12, color=theme.TEXT_MUTED)
    body = ft.Column([ft.Row(head, wrap=True, spacing=8), note, theme.h_scroll(tbl), totals, *([ft.Text('المرتجعات على الفاتورة', weight=ft.FontWeight.BOLD), theme.h_scroll(ret_tbl)] if d['returns'] else [])],
                     spacing=10, scroll=ft.ScrollMode.AUTO, height=560)
    dlg = ft.AlertDialog(modal=True, title=ft.Text(f"معاينة الفاتورة {d['number']}"), content=ft.Container(width=1020, content=body),
                         actions=[*([ft.OutlinedButton('مرتجع جزئي', icon=ft.Icons.CHECKLIST, on_click=lambda e: return_dialog(page, d, 'pick', None, refresh_all)),
                                     ft.FilledButton('مرتجع كامل الفاتورة', icon=ft.Icons.KEYBOARD_RETURN, bgcolor=theme.DANGER, on_click=lambda e: return_dialog(page, d, 'full', None, refresh_all))] if (can and remaining_any) else []),
                                  ft.OutlinedButton('طباعة الفاتورة', icon=ft.Icons.PRINT_OUTLINED, on_click=do_print_invoice), ft.TextButton('إغلاق', on_click=lambda e: (setattr(dlg, 'open', False), page.update()))])
    page.overlay.append(dlg); dlg.open = True; page.update()


def session_report_dialog(page, session_id, on_changed=None):
    """تقرير الجلسة: ملخص (طرق الدفع والمرتجعات وجرد النقدية) + فواتير الجلسة (بمعاينة ومرتجع) + مبيعات الأصناف (بالمرتجع والصافي) + المرتجعات (فواتير وأصناف)،
    مع طباعة PDF/Excel وإمكانية الإغلاق لو لسه مفتوحة."""
    try:
        r = services.pos_session_report(session_id)
    except Exception as ex:
        _snack(page, str(ex)); return
    t = r['totals']; rt = r['returns_totals']; ct = r['cancel_totals']
    me = services.current_user() or {}

    def reopen(*a):
        dlg.open = False; page.update()
        session_report_dialog(page, session_id, on_changed)
        if on_changed:
            on_changed()

    def card(label, value, color, sub=''):
        return theme.card(ft.Column([ft.Text(label, size=11.5, color=theme.TEXT_MUTED), ft.Text(value, size=19, weight=ft.FontWeight.BOLD, color=color), ft.Text(sub, size=10.5, color=theme.TEXT_MUTED)], spacing=0, tight=True), padding=10)

    def info(label, value):
        return ft.Container(bgcolor=theme.PRIMARY_LIGHT, border_radius=8, padding=ft.Padding(left=10, right=10, top=5, bottom=5),
                            content=ft.Column([ft.Text(label, size=10.5, color=theme.TEXT_MUTED), ft.Text(str(value), weight=ft.FontWeight.BOLD, size=12.5)], spacing=0, tight=True))

    # ---- الملخص
    pm_rows = [ft.DataRow(cells=[ft.DataCell(ft.Text(m['name'] + (' (نقدي)' if m['is_cash'] else ''), weight=ft.FontWeight.BOLD if m['is_cash'] else None)), ft.DataCell(ft.Text(str(m['count']))), ft.DataCell(ft.Text(_money(m['total'])))]) for m in r['payment_methods']]
    pm_tbl = ft.DataTable(columns=[ft.DataColumn(ft.Text('طريقة الدفع')), ft.DataColumn(ft.Text('عدد الفواتير'), numeric=True), ft.DataColumn(ft.Text('الإجمالي'), numeric=True)], rows=pm_rows, column_spacing=30)

    def line(label, value, bold=False, color=None):
        return ft.Row([ft.Text(label, weight=ft.FontWeight.BOLD if bold else None), ft.Container(expand=True), ft.Text(value, weight=ft.FontWeight.BOLD if bold else None, color=color)], width=440)
    recon = [line('العهدة الافتتاحية', _money(r['opening_cash'])), line('المبيعات النقدية', _money(r['cash_sales']))]
    if r['cash_refunds']:
        recon.append(line('(-) مرتجعات مردودة نقدًا من الدرج', _money(-r['cash_refunds']), color=theme.DANGER))
    recon.append(line('النقدية المتوقعة', _money(r['expected_cash_final']), True, theme.PRIMARY_TEXT))
    if r['state'] == 'closed':
        dd = r['difference'] or 0
        recon += [line('النقدية المعدودة', _money(r['counted_cash'])), line('الفرق', ('مطابق ✓' if abs(dd) < 0.005 else (f'زيادة {dd:,.2f}' if dd > 0 else f'عجز {-dd:,.2f}')), True,
                                                                            theme.SUCCESS if abs(dd) < 0.005 else (theme.WARNING if dd > 0 else theme.DANGER))]
        if r['close_notes']:
            recon.append(ft.Text(f"ملاحظات الإغلاق: {r['close_notes']}", size=12, color=theme.TEXT_MUTED))
    sales_net = [line('إجمالي المبيعات', _money(t['total'])), line(f"(-) المرتجعات على فواتير الجلسة ({rt['count']})", _money(-rt['total']), color=theme.DANGER if rt['total'] else None), line('صافي المبيعات', _money(r['net_total']), True, theme.PRIMARY_TEXT),
                 line(f"فواتير ملغاة مستبعدة ({t['voided_count']})", _money(t['voided_total']), color=theme.DANGER if t['voided_count'] else None),
                 line(f"إلغاءات المطعم - أصناف/طلبات ({ct['count']}) - لم تدخل في المبيعات", _money(ct['amount']), color=theme.DANGER if ct['count'] else None)]
    summary_panel = ft.Column([ft.Text('المبيعات والمرتجعات', weight=ft.FontWeight.BOLD), *sales_net, ft.Text('طرق الدفع', weight=ft.FontWeight.BOLD), theme.h_scroll(pm_tbl), ft.Text('جرد النقدية', weight=ft.FontWeight.BOLD), *recon,
                               *([ft.Text(f"فواتير ملغاة مستبعدة: {t['voided_count']} بإجمالي {_money(t['voided_total'])}", size=12, color=theme.TEXT_MUTED)] if t['voided_count'] else [])], spacing=8)

    # ---- الفواتير (بمعاينة)
    def inv_row(i):
        color = theme.DANGER if (i['voided'] or i['return_status'] == 'full') else None
        return ft.DataRow(cells=[ft.DataCell(ft.Text(i['number'], color=color, weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(f"{i['date']:%H:%M}")), ft.DataCell(ft.Text(i['customer'])),
                                 ft.DataCell(ft.Text(i['payment_method'])), ft.DataCell(ft.Text(_money(i['subtotal']))), ft.DataCell(ft.Text(_money(i['tax']))),
                                 ft.DataCell(ft.Text(_money(i['total']), weight=ft.FontWeight.BOLD, color=color)), ft.DataCell(ft.Text(_money(i['returned_total']) if i['returned_total'] else '-', color=theme.DANGER)),
                                 ft.DataCell(ft.Text('ملغاة', color=theme.DANGER, size=12) if i['voided'] else _return_status_chip(i['return_status'], i['returned_total'])),
                                 ft.DataCell(ft.TextButton('معاينة', icon=ft.Icons.VISIBILITY_OUTLINED, on_click=lambda e, x=i['id']: invoice_preview_dialog(page, x, reopen)))])
    inv_tbl = theme.SortableDataTable(columns=[('رقم الفاتورة', lambda i: i['number']), ('الوقت', lambda i: i['date']), ('العميل', lambda i: i['customer']), ('طريقة الدفع', lambda i: i['payment_method']),
                                               ('قبل الضريبة', lambda i: i['subtotal'], True), ('الضريبة', lambda i: i['tax'], True), ('الإجمالي', lambda i: i['total'], True), ('المرتجع', lambda i: i['returned_total'], True),
                                               ('الحالة', lambda i: i['return_status']), ('', None)], row_builder=inv_row, page=page, page_size=50, column_spacing=16, horizontal_margin=10)
    inv_tbl.set_data(r['invoices'])

    # ---- مبيعات الأصناف (بالمرتجع والصافي)
    def item_row(i):
        return ft.DataRow(cells=[ft.DataCell(ft.Text(i['sku'])), ft.DataCell(ft.Text(i['name'])), ft.DataCell(ft.Text(i['category'], size=12)), ft.DataCell(ft.Text(f"{i['qty']:g} {i['unit']}")),
                                 ft.DataCell(ft.Text(f"{i['returned_qty']:g}" if i['returned_qty'] else '-', color=theme.DANGER)), ft.DataCell(ft.Text(f"{i['net_qty']:g}", weight=ft.FontWeight.BOLD)),
                                 ft.DataCell(ft.Text(str(i['invoice_count']))), ft.DataCell(ft.Text(_money(i['total']))), ft.DataCell(ft.Text(_money(i['returned_total']) if i['returned_total'] else '-', color=theme.DANGER)),
                                 ft.DataCell(ft.Text(_money(i['net_total']), weight=ft.FontWeight.BOLD))])
    item_tbl = theme.SortableDataTable(columns=[('الكود', lambda i: i['sku']), ('الصنف', lambda i: i['name']), ('الفئة', lambda i: i['category']), ('الكمية المباعة', lambda i: i['qty'], True), ('المرتجع', lambda i: i['returned_qty'], True),
                                                ('الصافي', lambda i: i['net_qty'], True), ('عدد الفواتير', lambda i: i['invoice_count'], True), ('إجمالي المبيعات', lambda i: i['total'], True),
                                                ('قيمة المرتجع', lambda i: i['returned_total'], True), ('الصافي', lambda i: i['net_total'], True)], row_builder=item_row, page=page, page_size=50, column_spacing=16,
                                       horizontal_margin=10, initial_sort=7, initial_ascending=False)
    item_tbl.set_data(r['items'])

    # ---- المرتجعات: الفواتير المرتجعة + الأصناف المرتجعة
    def ret_row(x):
        where = 'على فاتورة من الجلسة' + (' + من درجها' if x['in_session_drawer'] else '') if x['on_session_invoice'] else 'من درج الجلسة (فاتورة جلسة تانية)'
        return ft.DataRow(cells=[ft.DataCell(ft.Text(x['number'], weight=ft.FontWeight.BOLD, color=theme.DANGER)), ft.DataCell(ft.Text(f"{x['date']:%H:%M}")), ft.DataCell(ft.Text(x['invoice_number'])), ft.DataCell(ft.Text(x['customer'])),
                                 ft.DataCell(ft.Text('كلي' if x['is_full'] else 'جزئي')), ft.DataCell(ft.Text(x['refund_method'], size=12)), ft.DataCell(ft.Text(x['reason'], size=12)),
                                 ft.DataCell(ft.Text(_money(x['total']), weight=ft.FontWeight.BOLD, color=theme.DANGER)), ft.DataCell(ft.Text(where, size=11, color=theme.TEXT_MUTED)),
                                 ft.DataCell(ft.TextButton('عرض', on_click=lambda e, i=x['id']: return_preview_dialog(page, i)))])
    ret_tbl = theme.SortableDataTable(columns=[('المرتجع', lambda x: x['number']), ('الوقت', lambda x: x['date']), ('الفاتورة', lambda x: x['invoice_number']), ('العميل', lambda x: x['customer']), ('النوع', lambda x: x['is_full']),
                                               ('طريقة الرد', lambda x: x['refund_method']), ('السبب', None), ('المبلغ', lambda x: x['total'], True), ('النطاق', None), ('', None)], row_builder=ret_row, page=page,
                                      page_size=50, column_spacing=14, horizontal_margin=10)
    ret_tbl.set_data(r['returns'])

    def ritem_row(i):
        return ft.DataRow(cells=[ft.DataCell(ft.Text(i['sku'])), ft.DataCell(ft.Text(i['name'])), ft.DataCell(ft.Text(i['category'], size=12)), ft.DataCell(ft.Text(f"{i['qty']:g} {i['unit']}", color=theme.DANGER, weight=ft.FontWeight.BOLD)),
                                 ft.DataCell(ft.Text(str(i['return_count']))), ft.DataCell(ft.Text(_money(i['total']), color=theme.DANGER, weight=ft.FontWeight.BOLD))])
    ritem_tbl = ft.DataTable(columns=[ft.DataColumn(ft.Text(c), numeric=n) for c, n in (('الكود', False), ('الصنف', False), ('الفئة', False), ('الكمية المرتجعة', True), ('عدد المرتجعات', True), ('القيمة', True))], rows=[ritem_row(i) for i in r['returned_items']], column_spacing=22)
    returns_panel = ft.Column([ft.Text(f"الفواتير المرتجعة ({len(r['returns'])})", weight=ft.FontWeight.BOLD), theme.h_scroll(ret_tbl.control),
                               ft.Text(f"الأصناف المرتجعة على فواتير الجلسة ({len(r['returned_items'])})", weight=ft.FontWeight.BOLD), theme.h_scroll(ritem_tbl)], spacing=8) if r['returns'] else \
        ft.Container(padding=30, content=ft.Text('مفيش مرتجعات على الجلسة دي', color=theme.TEXT_MUTED))

    def canc_row(c):
        return ft.DataRow(cells=[ft.DataCell(ft.Text(f"{c['date']:%H:%M}")), ft.DataCell(ft.Text(c['kind_label'], color=theme.DANGER, weight=ft.FontWeight.BOLD, size=12)), ft.DataCell(ft.Text(c['order_number'])),
                                 ft.DataCell(ft.Text(c['where'])), ft.DataCell(ft.Text(c['product'])), ft.DataCell(ft.Text(f"{c['quantity']:g}")), ft.DataCell(ft.Text(_money(c['amount']), color=theme.DANGER, weight=ft.FontWeight.BOLD)),
                                 ft.DataCell(ft.Text(c['reason'], size=12)), ft.DataCell(ft.Text(c['by'] + (f" / اعتماد {c['approved_by']}" if c['approved_by'] else ''), size=12))])
    canc_tbl = ft.DataTable(columns=[ft.DataColumn(ft.Text(x), numeric=x in ('الكمية', 'القيمة')) for x in ['الوقت', 'النوع', 'الطلب', 'الطاولة / النوع', 'الصنف', 'الكمية', 'القيمة', 'السبب', 'بواسطة']],
                            rows=[canc_row(c) for c in r['cancellations']], column_spacing=18)
    canc_panel = ft.Column([ft.Text(f"إلغاءات المطعم على طلبات الجلسة: {ct['count']} بند بقيمة {_money(ct['amount'])}", weight=ft.FontWeight.BOLD), theme.h_scroll(canc_tbl)], spacing=8) if r['cancellations'] else \
        ft.Container(padding=30, content=ft.Text('مفيش إلغاءات مطعم على الجلسة دي', color=theme.TEXT_MUTED))

    panels = {'cancels': canc_panel, 'summary': summary_panel, 'invoices': theme.h_scroll(inv_tbl.control), 'items': theme.h_scroll(item_tbl.control), 'returns': returns_panel}
    holder = ft.Container(content=panels['summary'])
    tab_btns = {}

    def show(key):
        holder.content = panels[key]
        for k, b in tab_btns.items():
            b.style = ft.ButtonStyle(bgcolor=theme.PRIMARY if k == key else None, color='#FFFFFF' if k == key else theme.TEXT_MUTED)
        page.update()
    for key, label in (('summary', 'الملخص'), ('invoices', f"الفواتير ({len(r['invoices'])})"), ('items', f"مبيعات الأصناف ({len(r['items'])})"), ('returns', f"المرتجعات ({len(r['returns'])})"), ('cancels', f"الإلغاءات ({ct['count']})")):
        tab_btns[key] = ft.OutlinedButton(label, on_click=lambda e, k=key: show(k))
    tab_btns['summary'].style = ft.ButtonStyle(bgcolor=theme.PRIMARY, color='#FFFFFF')

    def export(kind):
        try:
            from ..report_export import export_pdf, export_excel
            fresh = services.pos_session_report(session_id)
            data = {'session': fresh, 'date_from': None, 'date_to': None, 'title_suffix': f"{fresh['number']} - {fresh['terminal']}"}
            out_dir = os.path.join(services.APP_DIR, 'exports'); os.makedirs(out_dir, exist_ok=True)
            theme.open_or_download_file(page, (export_pdf if kind == 'pdf' else export_excel)(data, 'pos_session', out_dir))
        except Exception as ex:
            _snack(page, f'تعذر الإنشاء: {ex}')

    def do_close_session(e):
        dlg.open = False; page.update()
        close_session_dialog(page, session_id, on_done=lambda rep: (on_changed() if on_changed else None, session_report_dialog(page, session_id, on_changed)))

    can_close = r['state'] == 'open' and (me.get('role') == 'admin' or r['opened_by'] == me.get('username'))
    state_chip = ft.Container(bgcolor=theme.SUCCESS if r['state'] == 'open' else theme.TEXT_MUTED, border_radius=10, padding=ft.Padding(left=10, right=10, top=3, bottom=3),
                              content=ft.Text('مفتوحة' if r['state'] == 'open' else 'مقفولة', color='#FFFFFF', size=12, weight=ft.FontWeight.BOLD))
    head = ft.Row([state_chip, info('الماكينة', r['terminal']), info('الكاشير', r['employee'] or r['opened_by_name']), info('فُتحت', f"{_fmt_dt(r['opened_at'])} - {r['opened_by_name']}"),
                   info('أُغلقت', f"{_fmt_dt(r['closed_at'])} - {r['closed_by']}" if r['state'] == 'closed' else '-')], wrap=True, spacing=8)
    cards = ft.Row([card('عدد الفواتير', str(t['count']), theme.PRIMARY, f"{t['voided_count']} ملغاة" if t['voided_count'] else ''), card('إجمالي المبيعات', _money(t['total']), theme.SUCCESS, f"قبل الضريبة {_money(t['subtotal'])}"),
                    card('المرتجعات', _money(rt['total']), theme.DANGER if rt['total'] else theme.TEXT_MUTED, f"{rt['count']} مرتجع"), card('صافي المبيعات', _money(r['net_total']), theme.PRIMARY_TEXT),
                    card('إلغاءات المطعم', _money(ct['amount']), theme.DANGER if ct['count'] else theme.TEXT_MUTED, f"{ct['count']} بند"), card('النقدية المتوقعة', _money(r['expected_cash_final']), theme.WARNING, f"العهدة {_money(r['opening_cash'])}")], wrap=True, spacing=10)
    body = ft.Column([head, cards, ft.Row(list(tab_btns.values()), spacing=8, wrap=True), holder], spacing=10, scroll=ft.ScrollMode.AUTO, height=600)
    dlg = ft.AlertDialog(modal=True, title=ft.Text(f"تقرير الجلسة {r['number']}"), content=ft.Container(width=1040, content=body),
                         actions=[*( [ft.FilledButton('إغلاق الجلسة', icon=ft.Icons.LOCK_OUTLINE, bgcolor=theme.DANGER, on_click=do_close_session)] if can_close else []),
                                  ft.OutlinedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('excel')), ft.FilledButton('طباعة PDF', icon=ft.Icons.PRINT_OUTLINED, bgcolor=theme.PRIMARY, on_click=lambda e: export('pdf')),
                                  ft.TextButton('إغلاق النافذة', on_click=lambda e: (setattr(dlg, 'open', False), page.update()))])
    page.overlay.append(dlg); dlg.open = True; page.update()


def build_pos_sessions(page: ft.Page):
    """جلسات نقاط البيع (الورديات): كل جلسة كاشير على ماكينة - العهدة، المبيعات، النقدية المتوقعة والمعدودة والفرق - مع تقرير تفصيلي لكل جلسة."""
    terminals = services.list_pos_terminals()
    me = services.current_user() or {}
    today = datetime.date.today()
    term_dd = ft.Dropdown(label='الماكينة', width=230, value='', options=[ft.dropdown.Option('', 'كل الماكينات')] + [ft.dropdown.Option(str(t['id']), f"{t['code']} - {t['name']}") for t in terminals])
    state_dd = ft.Dropdown(label='الحالة', width=160, value='', options=[ft.dropdown.Option('', 'الكل'), ft.dropdown.Option('open', 'مفتوحة'), ft.dropdown.Option('closed', 'مقفولة')])
    rng = theme.DateRangeField('الفترة', page, width=290, start=(today - datetime.timedelta(days=30)).strftime('%Y-%m-%d'), end=today.strftime('%Y-%m-%d'))
    cards = ft.Row(wrap=True, spacing=12)

    def row_builder(x):
        d = x['difference']
        acts = [ft.TextButton('عرض', icon=ft.Icons.VISIBILITY_OUTLINED, on_click=lambda e, i=x['id']: session_report_dialog(page, i, refresh))]
        if x['state'] == 'open' and (me.get('role') == 'admin' or x['opened_by'] == me.get('username')):
            acts.append(ft.TextButton('إغلاق', icon=ft.Icons.LOCK_OUTLINE, style=ft.ButtonStyle(color=theme.DANGER), on_click=lambda e, i=x['id']: close_session_dialog(page, i, on_done=lambda rep: refresh(True))))
        return ft.DataRow(cells=[
            ft.DataCell(ft.Text(x['number'], weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(x['terminal'], size=12)), ft.DataCell(ft.Text(x['employee'] or x['opened_by_name'])),
            ft.DataCell(ft.Text(_fmt_dt(x['opened_at']), size=12)), ft.DataCell(ft.Text(_fmt_dt(x['closed_at']), size=12)), ft.DataCell(ft.Text(_money(x['opening_cash']))),
            ft.DataCell(ft.Text(str(x['invoice_count']))), ft.DataCell(ft.Text(_money(x['total_sales']), weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(_money(x['returns_total']) if x['returns_total'] else '-', color=theme.DANGER)),
            ft.DataCell(ft.Text(_money(x['expected_cash']) if x['expected_cash'] is not None else '-')), ft.DataCell(ft.Text(_money(x['counted_cash']) if x['counted_cash'] is not None else '-')),
            ft.DataCell(ft.Text('-' if d is None else ('مطابق' if abs(d) < 0.005 else f'{d:+,.2f}'), color=None if d is None else (theme.SUCCESS if abs(d) < 0.005 else (theme.WARNING if d > 0 else theme.DANGER)), weight=ft.FontWeight.BOLD)),
            ft.DataCell(ft.Text('مفتوحة' if x['state'] == 'open' else 'مقفولة', color=theme.SUCCESS if x['state'] == 'open' else theme.TEXT_MUTED, weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Row(acts, spacing=0))])
    table = theme.SortableDataTable(columns=[
        ('الجلسة', lambda x: x['number']), ('الماكينة', lambda x: x['terminal']), ('الكاشير', lambda x: x['employee'] or x['opened_by_name']), ('فُتحت', lambda x: x['opened_at']),
        ('أُغلقت', lambda x: x['closed_at'] or datetime.datetime.max), ('العهدة', lambda x: x['opening_cash'], True), ('الفواتير', lambda x: x['invoice_count'], True), ('المبيعات', lambda x: x['total_sales'], True), ('المرتجع', lambda x: x['returns_total'], True),
        ('المتوقع', lambda x: x['expected_cash'] or 0, True), ('المعدود', lambda x: x['counted_cash'] or 0, True), ('الفرق', lambda x: x['difference'] or 0, True), ('الحالة', lambda x: x['state']), ('', None)],
        row_builder=row_builder, page=page, expand=True, initial_sort=3, initial_ascending=False, column_spacing=14, horizontal_margin=10)

    def _d(v):
        return datetime.datetime.strptime(v, '%Y-%m-%d') if v else None

    def refresh(e=None):
        rows = services.list_pos_sessions(int(term_dd.value) if term_dd.value else None, state_dd.value or None, _d(rng.start.value), _d(rng.end.value))
        table.set_data(rows)
        closed = [r for r in rows if r['state'] == 'closed' and r['difference'] is not None]
        def card(label, value, color, sub=''):
            return theme.card(ft.Column([ft.Text(label, size=12, color=theme.TEXT_MUTED), ft.Text(value, size=21, weight=ft.FontWeight.BOLD, color=color), ft.Text(sub, size=11, color=theme.TEXT_MUTED)], spacing=0, tight=True), padding=14)
        cards.controls = [card('الجلسات', str(len(rows)), theme.PRIMARY, f"{len([r for r in rows if r['state'] == 'open'])} مفتوحة"), card('إجمالي المبيعات', _money(sum(r['total_sales'] for r in rows)), theme.SUCCESS, f"{sum(r['invoice_count'] for r in rows)} فاتورة"),
                          card('فروق النقدية', f"{sum(r['difference'] for r in closed):+,.2f}", theme.WARNING if any(abs(r['difference']) > 0.005 for r in closed) else theme.SUCCESS, f"{len([r for r in closed if abs(r['difference']) > 0.005])} جلسة فيها فرق")]
        if e is not None:
            page.update()

    def new_session(e=None):
        usable = [t for t in services.pos_terminals_for_current_user() if not services.get_open_pos_session(t['id'])]
        if not usable:
            _snack(page, 'مفيش ماكينة متاحة لفتح جلسة (كلها عليها جلسة مفتوحة أو مش مسموح لك بيها)'); return
        pick = ft.Dropdown(label='الماكينة', width=320, value=str(usable[0]['id']), options=[ft.dropdown.Option(str(t['id']), f"{t['code']} - {t['name']}") for t in usable])
        dlg = ft.AlertDialog(modal=True, title=ft.Text('فتح جلسة - اختر الماكينة'), content=pick,
                             actions=[ft.TextButton('إلغاء', on_click=lambda ev: (setattr(dlg, 'open', False), page.update())),
                                      ft.FilledButton('التالي', bgcolor=theme.PRIMARY, on_click=lambda ev: (setattr(dlg, 'open', False), page.update(), open_session_dialog(page, next(t for t in usable if str(t['id']) == pick.value), lambda sid: refresh(True))))])
        page.overlay.append(dlg); dlg.open = True; page.update()

    for c in (term_dd, state_dd):
        c.on_change = refresh
    rng.on_change = refresh
    refresh()
    return ft.Column([
        ft.Row([theme.page_title('جلسات نقاط البيع', 'ورديات الكاشير: عهدة الفتح، مبيعات الجلسة وفواتيرها ومبيعات أصنافها، وجرد النقدية عند الإغلاق'), ft.Container(expand=True),
                ft.FilledButton('فتح جلسة', icon=ft.Icons.LOCK_OPEN_OUTLINED, bgcolor=theme.PRIMARY, on_click=new_session)], spacing=8),
        cards, theme.card(ft.Row([term_dd, state_dd, rng.control], wrap=True, spacing=10), padding=12),
        theme.card(theme.h_scroll(table.control, vscroll=True), expand=True),
    ], expand=True, spacing=8)
