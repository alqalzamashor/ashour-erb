import asyncio
import json

import flet as ft
from .. import delivery, delivery_server, services, sounds, theme

STATUS_COLOR = {'new': 'WARNING', 'accepted': 'PRIMARY', 'ready': 'SUCCESS', 'dispatched': 'PRIMARY', 'delivered': 'SUCCESS', 'rejected': 'DANGER'}


def build_delivery_orders(page: ft.Page):
    """طلبات التوصيل الواردة من التطبيقات (webhook) أو اليدوية: قبول → المطبخ → تسليم."""
    services.require_action('delivery_orders', 'view')
    can_edit = services.user_has_action(services._get_user(), 'delivery_orders', 'edit')
    st = {'alive': True, 'filter': 'new', 'n': None}
    col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
    flt = ft.Dropdown(label='الحالة', width=200, value='new', options=[ft.dropdown.Option('', 'الكل')] + [ft.dropdown.Option(k, v) for k, v in delivery.STATUS.items()])
    info = ft.Text('', size=12, color=theme.TEXT_MUTED)

    def snack(msg, bad=False):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True, bgcolor=theme.DANGER if bad else None)); page.update()

    def terminals():
        out = []
        for t in services.pos_terminals_for_current_user():
            if services.get_open_pos_session(t['id']):
                out.append(t)
        return out

    # ---------------- قبول
    def open_accept(o):
        try:
            items = delivery.match_items(o['id'])
        except Exception as ex:
            return snack(str(ex), True)
        terms = terminals()
        term_dd = ft.Dropdown(label='ماكينة/جلسة المطعم', width=360, value=str(terms[0]['id']) if terms else None, options=[ft.dropdown.Option(str(t['id']), t['name']) for t in terms])
        prods = services.list_products()
        pick = {}
        rows = []
        for i, it in enumerate(items):
            label = f"{it['quantity']:g} × {it.get('name') or it.get('sku')}" + (f"  ({it['price']:g})" if it.get('price') else '')
            if it['product_id']:
                rows.append(ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, color=theme.SUCCESS, size=18), ft.Text(label, size=13)], spacing=6))
            else:
                dd = ft.Dropdown(label='اربطه بصنف عندك', width=300, options=[ft.dropdown.Option(str(p.id), f'{p.sku} - {p.name}') for p in prods if p.can_be_sold])
                pick[i] = dd
                rows.append(ft.Row([ft.Icon(ft.Icons.HELP_OUTLINE, color=theme.WARNING, size=18), ft.Text(label, size=13, width=200), dd], spacing=6, wrap=True))
        err = ft.Text('', color=theme.DANGER, size=12)

        def go(e):
            try:
                if not term_dd.value:
                    raise ValueError('مفيش ماكينة بجلسة مفتوحة - افتح جلسة الأول')
                r = delivery.accept(o['id'], int(term_dd.value), {i: int(d.value) for i, d in pick.items() if d.value})
                dlg.open = False
                msg = f"اتقبل وبعت للمطبخ: {r['number']}"
                if abs(r['price_diff']) > 0.5:
                    msg += f" — تنبيه: إجمالي التطبيق يختلف عن أسعارنا بـ {r['price_diff']:+.2f}"
                snack(msg); refresh(True)
            except Exception as ex:
                err.value = str(ex); page.update()
        dlg = ft.AlertDialog(modal=True, title=ft.Text(f"قبول طلب {o['source']} #{o['external_id']}"),
                             content=ft.Container(width=520, content=ft.Column([term_dd] + rows + [err], spacing=8, tight=True, scroll=ft.ScrollMode.AUTO)),
                             actions=[ft.TextButton('إلغاء', on_click=lambda e: (setattr(dlg, 'open', False), page.update())), ft.FilledButton('قبول وإرسال للمطبخ', bgcolor=theme.SUCCESS, on_click=go)])
        page.overlay.append(dlg); dlg.open = True; page.update()

    def open_reject(o):
        reason = ft.TextField(label='سبب الرفض', width=360)

        def go(e):
            try:
                delivery.reject(o['id'], reason.value); dlg.open = False; refresh(True)
            except Exception as ex:
                snack(str(ex), True)
        dlg = ft.AlertDialog(modal=True, title=ft.Text('رفض الطلب'), content=reason,
                             actions=[ft.TextButton('إلغاء', on_click=lambda e: (setattr(dlg, 'open', False), page.update())), ft.FilledButton('رفض', bgcolor=theme.DANGER, on_click=go)])
        page.overlay.append(dlg); dlg.open = True; page.update()

    def move(o, status):
        try:
            delivery.set_status(o['id'], status); refresh(True)
        except Exception as ex:
            snack(str(ex), True)

    # ---------------- يدوي
    def open_manual(e=None):
        n, ph, ad, nt = ft.TextField(label='اسم العميل', width=250), ft.TextField(label='الجوال', width=170), ft.TextField(label='العنوان', width=430), ft.TextField(label='ملاحظات', width=430)
        prods = services.list_products()
        lines = ft.Column(spacing=4)
        rows = []

        def add_line(e=None):
            dd = ft.Dropdown(label='الصنف', width=280, options=[ft.dropdown.Option(str(p.id), f'{p.sku} - {p.name}') for p in prods if p.can_be_sold])
            q = ft.TextField(label='الكمية', width=90, value='1')
            rows.append((dd, q)); lines.controls.append(ft.Row([dd, q])); page.update()
        add_line()
        err = ft.Text('', color=theme.DANGER, size=12)

        def go(e):
            try:
                its = []
                for dd, q in rows:
                    if dd.value:
                        p = next(p for p in prods if str(p.id) == dd.value)
                        its.append({'sku': p.sku, 'name': p.name, 'quantity': float(q.value or 1)})
                if not its:
                    raise ValueError('أضف صنف واحد على الأقل')
                delivery.create_manual(n.value, ph.value, ad.value, its, nt.value)
                dlg.open = False; refresh(True)
            except Exception as ex:
                err.value = str(ex); page.update()
        dlg = ft.AlertDialog(modal=True, title=ft.Text('طلب توصيل يدوي (تليفون)'),
                             content=ft.Container(width=520, content=ft.Column([ft.Row([n, ph]), ad, nt, lines, ft.TextButton('+ صنف', on_click=add_line), err], tight=True, scroll=ft.ScrollMode.AUTO)),
                             actions=[ft.TextButton('إلغاء', on_click=lambda e: (setattr(dlg, 'open', False), page.update())), ft.FilledButton('حفظ', bgcolor=theme.PRIMARY, on_click=go)])
        page.overlay.append(dlg); dlg.open = True; page.update()

    # ---------------- القائمة
    def refresh(force=False, update=True):
        orders = delivery.list_orders(status=flt.value or None, limit=100)
        n_new = delivery.count_new()
        if st['n'] is not None and n_new > st['n']:
            sounds.play('done')
        st['n'] = n_new
        cards = []
        for o in orders:
            sc = getattr(theme, STATUS_COLOR.get(o['status'], 'PRIMARY'))
            items = ', '.join(f"{i['quantity']:g}× {i.get('name') or i.get('sku')}" for i in o['items'])
            acts = []
            if can_edit:
                if o['status'] == 'new':
                    acts = [ft.FilledButton('قبول', icon=ft.Icons.CHECK, bgcolor=theme.SUCCESS, on_click=lambda e, oo=o: open_accept(oo)),
                            ft.OutlinedButton('رفض', on_click=lambda e, oo=o: open_reject(oo))]
                else:
                    acts = [ft.OutlinedButton(delivery.STATUS[nx], on_click=lambda e, oo=o, nx=nx: move(oo, nx)) for nx in delivery.NEXT.get(o['status'], ())]
            cards.append(theme.card(ft.Column([
                ft.Row([ft.Container(content=ft.Text(delivery.STATUS.get(o['status'], o['status']), size=12, color='#FFFFFF', weight=ft.FontWeight.BOLD), bgcolor=sc, border_radius=10, padding=ft.Padding(left=8, right=8, top=2, bottom=2)),
                        ft.Text(f"{o['source']} #{o['external_id']}", weight=ft.FontWeight.BOLD), ft.Container(expand=True), ft.Text(f"{o['created_at']:%m-%d %H:%M}", size=12, color=theme.TEXT_MUTED)]),
                ft.Text(f"{o['customer_name'] or '-'}  •  {o['phone'] or '-'}  •  {o['address'] or '-'}", size=13),
                ft.Text(items, size=13), ft.Text(' | '.join(x for x in [f"الإجمالي {o['total']:g}" if o['total'] else '', {'online': 'مدفوع أونلاين', 'cash': 'تحصيل نقدي'}.get(o['payment'], ''), o['notes'], o['reject_reason']] if x), size=12, color=theme.TEXT_MUTED),
                ft.Row(acts, spacing=8)], spacing=4), padding=12))
        col.controls = cards or [ft.Text('مفيش طلبات', color=theme.TEXT_MUTED)]
        info.value = f'{n_new} طلب جديد'
        if update:
            page.update()

    flt.on_select = lambda e: refresh(True)

    async def loop():
        while st['alive']:
            await asyncio.sleep(8)
            try:
                refresh()
            except Exception:
                pass

    # ---------------- الإعدادات
    cfg_box = ft.Column(spacing=8)

    def build_settings():
        cfg = delivery.get_config()
        en = ft.Switch(label='تفعيل مستقبل الطلبات (webhook)', value=cfg['enabled'])
        port = ft.TextField(label='البورت', width=110, value=str(cfg['port']))
        msg = ft.Text('', size=12)

        def save(e):
            try:
                delivery.save_config(enabled=en.value, port=port.value)
                delivery_server.stop()
                r = delivery_server.start() if en.value else None
                msg.value = f'اتحفظ. المستقبل شغال على البورت {r[1]}' if r else ('اتحفظ لكن المستقبل مش شغال (البورت مشغول؟)' if en.value else 'اتحفظ (المستقبل مقفول)')
                msg.color = theme.SUCCESS; page.update()
            except Exception as ex:
                msg.value = str(ex); msg.color = theme.DANGER; page.update()

        def add_src(e):
            k = ft.TextField(label='اسم المصدر (إنجليزي) مثل hungerstation', width=330); lab = ft.TextField(label='الاسم الظاهر', width=250)

            def go(ev):
                try:
                    sec = delivery.add_source(k.value, lab.value)
                    d2.open = False; build_settings(); page.update()
                    snack(f'اتضاف. المفتاح السري: {sec}  (انسخه من القايمة تحت)')
                except Exception as ex:
                    snack(str(ex), True)
            d2 = ft.AlertDialog(modal=True, title=ft.Text('إضافة مصدر'), content=ft.Column([k, lab], tight=True),
                                actions=[ft.TextButton('إلغاء', on_click=lambda e: (setattr(d2, 'open', False), page.update())), ft.FilledButton('إضافة', on_click=go)])
            page.overlay.append(d2); d2.open = True; page.update()

        def src_row(k, v):
            def rot(e):
                delivery.rotate_secret(k); build_settings(); page.update(); snack('اتغيّر المفتاح - حدّثه في التطبيق')

            def rem(e):
                delivery.remove_source(k); build_settings(); page.update()
            mp = ft.TextField(label='خريطة الحقول (JSON، اختياري)', value=json.dumps(v.get('mapping') or {}, ensure_ascii=False), width=520, text_size=12, multiline=True)

            def savemap(e):
                try:
                    c2 = delivery.get_config(); c2['sources'][k]['mapping'] = json.loads(mp.value or '{}')
                    delivery.save_config(sources=c2['sources']); snack('اتحفظت الخريطة')
                except Exception as ex:
                    snack(str(ex), True)
            url = f"http://<عنوان-السيرفر>:{cfg['port']}/hook/{k}"
            return theme.card(ft.Column([ft.Row([ft.Text(f"{v.get('label', k)} ({k})", weight=ft.FontWeight.BOLD), ft.Container(expand=True), ft.TextButton('تغيير المفتاح', on_click=rot), ft.TextButton('حذف', on_click=rem)]),
                                         ft.Text('الرابط: ' + url, size=12, selectable=True), ft.TextField(label='المفتاح السري (X-Api-Key)', value=v['secret'], read_only=True, password=True, can_reveal_password=True, width=420),
                                         mp, ft.TextButton('حفظ الخريطة', on_click=savemap)], spacing=6), padding=12)
        cfg_box.controls = [ft.Row([en, port, ft.FilledButton('حفظ', on_click=save, bgcolor=theme.PRIMARY, disabled=not can_edit), ft.OutlinedButton('+ مصدر', on_click=add_src, disabled=not can_edit), msg], wrap=True)] + [src_row(k, v) for k, v in cfg['sources'].items()] + [
            ft.Text('كل تطبيق بيبعت POST JSON على رابطه مع المفتاح في ترويسة X-Api-Key. الشكل العام: {"order_id","customer":{"name","phone"},"address","notes","total","payment":"online|cash","items":[{"sku","name","quantity","price","note"}]}. '
                    'لو شكل التطبيق مختلف عدّل «خريطة الحقول» (مسارات بنقط مثل order.customer.phone). لازم HTTPS قدام السيرفر لو مفتوح للإنترنت.', size=11.5, color=theme.TEXT_MUTED)]

    build_settings()
    theme.call_without_page_update(page, lambda: refresh(True, update=False))
    try:
        page.run_task(loop)
    except Exception:
        pass
    return ft.Column([
        ft.Row([theme.page_title('طلبات التوصيل', 'الطلبات الواردة من تطبيقات التوصيل أو التليفون: قبول ← المطبخ ← تسليم'), ft.Container(expand=True), info, flt,
                ft.OutlinedButton('طلب يدوي', icon=ft.Icons.ADD, on_click=open_manual, disabled=not can_edit), ft.IconButton(ft.Icons.REFRESH, on_click=lambda e: refresh(True))], wrap=True),
        ft.ExpansionTile(title=ft.Text('إعدادات الاستقبال والمصادر'), controls=[ft.Container(content=cfg_box, padding=10)], expanded=False),
        col,
    ], expand=True, spacing=10)
