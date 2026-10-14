import datetime
import flet as ft
from .. import services, sounds, theme

MAX_ROWS = 300
SCOPE_LABELS = [('all', 'كل الأصول'), ('category', 'فئة معيّنة'), ('branch', 'فرع معيّن'), ('cost_center', 'مركز تكلفة معيّن')]
BANNER = {   # لون الخلفية، لون الإطار/الأيقونة، الأيقونة
    'ready': ('#F3F4F8', '#8A8D9F', ft.Icons.QR_CODE_SCANNER),
    'ok': ('#E6F6EE', '#1B8E5A', ft.Icons.CHECK_CIRCLE),
    'dup': ('#FFF6E0', '#C98A00', ft.Icons.WARNING_AMBER),
    'error': ('#FDE9E7', '#C0392B', ft.Icons.CANCEL),
}


def build_asset_inventory(page: ft.Page):
    """جرد الأصول الثابتة: جلسة بلقطة من الأصول المتوقعة + مسح الباركود (بصوت) +
    تقرير بالعجز (متوقع ومش موجود) والزيادة (موجود ومش متوقع)."""
    root = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO)

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    async def _focus(ctrl):
        try:
            await ctrl.focus()
        except Exception:
            pass

    def focus_on(ctrl):
        try:
            page.run_task(_focus, ctrl)
        except Exception:
            pass

    def fmt_money(v):
        return f'{v:,.2f}'

    # ====================================================================== قايمة الجلسات
    def show_list():
        name_f = ft.TextField(label='اسم الجرد', hint_text=f'جرد أصول {datetime.date.today():%Y-%m-%d}', width=320)
        scope_dd = ft.Dropdown(label='نطاق الجرد', width=220, value='all', options=[ft.dropdown.Option(k, v) for k, v in SCOPE_LABELS])
        item_dd = ft.Dropdown(label='اختار', width=260, visible=False)
        err = ft.Text('', color=theme.DANGER, visible=False)

        def on_scope(e=None):
            opts = []
            if scope_dd.value == 'category':
                opts = [(str(c.id), c.name) for c in services.list_asset_categories()]
                item_dd.label = 'الفئة'
            elif scope_dd.value == 'branch':
                opts = [(str(b.id), b.name) for b in services.list_branches()]
                item_dd.label = 'الفرع'
            elif scope_dd.value == 'cost_center':
                opts = [(str(c.id), f'{c.code} - {c.name}') for c in services.list_cost_centers()]
                item_dd.label = 'مركز التكلفة'
            item_dd.options = [ft.dropdown.Option(k, v) for k, v in opts]
            item_dd.value = None
            item_dd.visible = scope_dd.value != 'all'
            page.update()
        scope_dd.on_change = on_scope

        def start(e):
            try:
                inv_id = services.create_asset_inventory(name_f.value, scope_dd.value, int(item_dd.value) if item_dd.value else None)
                show_session(inv_id)
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in
                                      ['الرقم', 'الاسم', 'التاريخ', 'النطاق', 'الحالة', 'المتوقع', 'تم العثور', 'عجز', 'زيادة', '']], rows=[])

        def confirm_delete(inv):
            def do(e):
                try:
                    services.delete_asset_inventory(inv['id'])
                    dlg.open = False; page.update(); fill()
                except Exception as ex:
                    dlg.open = False; snack(str(ex))
            dlg = ft.AlertDialog(modal=True, title=ft.Text('حذف جلسة الجرد'),
                                 content=ft.Text(f'هتحذف {inv["number"]} - {inv["name"]} بكل عمليات المسح فيها. متأكد؟'),
                                 actions=[ft.TextButton('تراجع', on_click=lambda e: (setattr(dlg, 'open', False), page.update())),
                                          ft.FilledButton('حذف', bgcolor=theme.DANGER, on_click=do)])
            page.overlay.append(dlg); dlg.open = True; page.update()

        def fill():
            rows = []
            for inv in services.list_asset_inventories():
                closed = inv['state'] == 'closed'
                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(inv['number'], weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(inv['name'])),
                    ft.DataCell(ft.Text(inv['date'].strftime('%Y-%m-%d'))), ft.DataCell(ft.Text(inv['scope_label'], size=12)),
                    ft.DataCell(ft.Text('مقفول' if closed else 'مفتوح', color=theme.SUCCESS if closed else theme.WARNING, weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(str(inv['expected']))), ft.DataCell(ft.Text(str(inv['found']), color=theme.SUCCESS)),
                    ft.DataCell(ft.Text(str(inv['shortage']), color=theme.DANGER if inv['shortage'] else None)),
                    ft.DataCell(ft.Text(str(inv['surplus']), color=theme.WARNING if inv['surplus'] else None)),
                    ft.DataCell(ft.Row(spacing=0, controls=[
                        ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip='فتح الجرد', on_click=lambda e, i=inv['id']: show_session(i)),
                        ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف', on_click=lambda e, i=inv: confirm_delete(i)),
                    ])),
                ]))
            table.rows = rows

        fill()
        root.controls = [
            theme.page_title('جرد الأصول الثابتة', 'امسح باركود كل أصل (بصوت تأكيد) وبعدها اطلع تقرير بالعجز والزيادة'),
            ft.Container(height=12),
            theme.card(ft.Column([
                ft.Text('بدء جرد جديد', size=16, weight=ft.FontWeight.BOLD),
                ft.Text('البرنامج بياخد لقطة من الأصول المسجّلة (غير المستبعدة) في النطاق، وأي أصل مش هتمسحه بيظهر عجز، وأي كود تمسحه وهو مش في اللقطة بيظهر زيادة.',
                        color=theme.TEXT_MUTED, size=12),
                ft.Row([name_f, scope_dd, item_dd, ft.FilledButton('بدء الجرد', icon=ft.Icons.PLAY_ARROW, bgcolor=theme.PRIMARY, on_click=start)], wrap=True, spacing=12),
                err,
            ], spacing=10)),
            ft.Container(height=16),
            theme.card(ft.Column([ft.Text('جلسات الجرد', size=16, weight=ft.FontWeight.BOLD), theme.h_scroll(table)], spacing=10)),
        ]

    # ====================================================================== شاشة الجرد
    def show_session(inv_id):
        st = {'inv': services.get_asset_inventory(inv_id), 'recent': [], 'sel': set(), 'pending_ids': [], 'sel_label': None}
        tabs = theme.SimpleTabs(page)

        scan_f = ft.TextField(label='امسح الباركود هنا (الماسح بيكتب الكود ويدوس Enter) - أو اكتب الكود واضغط Enter', width=560,
                              prefix_icon=ft.Icons.QR_CODE_SCANNER, autofocus=True, border_radius=10, text_size=16)
        banner_icon = ft.Icon(BANNER['ready'][2], size=44, color=BANNER['ready'][1])
        banner_main = ft.Text('جاهز للمسح', size=22, weight=ft.FontWeight.BOLD)
        banner_sub = ft.Text('اضغط على الحقل ثم امسح أول أصل', size=13, color=theme.TEXT_MUTED)
        banner = ft.Container(content=ft.Row([banner_icon, ft.Column([banner_main, banner_sub], spacing=2, expand=True)], spacing=14),
                              bgcolor=BANNER['ready'][0], border=ft.Border.all(2, BANNER['ready'][1]) if hasattr(ft, 'Border') and hasattr(ft.Border, 'all') else None,
                              border_radius=12, padding=16)
        recent_col = ft.Column(spacing=2)
        sound_sw = ft.Switch(label='صوت الجرد', value=True)
        filter_f = ft.TextField(label='بحث في القوائم (كود أو اسم)', width=300, prefix_icon=ft.Icons.SEARCH, border_radius=10)
        title_txt = ft.Text('', size=20, weight=ft.FontWeight.BOLD)
        scope_txt = ft.Text('', size=12, color=theme.TEXT_MUTED)
        state_btn = ft.OutlinedButton('')
        counters = {k: ft.Text('0', size=24, weight=ft.FontWeight.BOLD, color=c) for k, c in
                    [('expected', None), ('found', theme.SUCCESS), ('shortage', theme.DANGER), ('surplus', theme.WARNING)]}
        pct_txt = ft.Text('', size=12, color=theme.TEXT_MUTED)
        progress = ft.ProgressBar(value=0, height=8, color=theme.SUCCESS)

        def set_banner(kind, main, sub=''):
            bg, fg, icon = BANNER[kind]
            banner.bgcolor = bg
            try:
                banner.border = ft.Border.all(2, fg)
            except Exception:
                pass
            banner_icon.name = icon; banner_icon.color = fg
            banner_main.value = main; banner_main.color = fg
            banner_sub.value = sub

        def play(kind):
            sounds.play(kind, enabled=sound_sw.value)

        def is_open():
            return st['inv']['state'] == 'open'

        # ---------- الجداول ----------
        def match(r, q):
            return not q or q in r['code'].lower() or q in (r['name'] or '').lower()

        def limited(rows, table_rows_builder, empty_msg):
            q = (filter_f.value or '').strip().lower()
            rows = [r for r in rows if match(r, q)]
            shown = rows[:MAX_ROWS]
            note = ft.Text(f'بيعرض أول {MAX_ROWS} من {len(rows)} - استخدم البحث للباقي', size=12, color=theme.TEXT_MUTED, visible=len(rows) > MAX_ROWS)
            return shown, note, len(rows)

        def act(fn, msg_kind):
            def handler(e):
                try:
                    fn(); refresh()
                except Exception as ex:
                    snack(str(ex))
            return handler

        def sel_text():
            n = len(st['sel'])
            return f'المحدد للاستبعاد: {n}' if n else 'حدّد أصول (اختياري) لاستبعادها كعجز، أو سيب التحديد فاضي لاستبعاد كل العجز المتبقي'

        def toggle_sel(lid, row):
            if lid in st['sel']:
                st['sel'].discard(lid)
            else:
                st['sel'].add(lid)
            row.selected = lid in st['sel']
            if st['sel_label'] is not None:
                st['sel_label'].value = sel_text()
            page.update()

        def select_all(e, rows_by_id):
            checked = str(getattr(e, 'data', '')).lower() == 'true'
            for lid, row in rows_by_id.items():
                (st['sel'].add if checked else st['sel'].discard)(lid)
                row.selected = checked
            if st['sel_label'] is not None:
                st['sel_label'].value = sel_text()
            page.update()

        def shortage_tab():
            rows = services.list_asset_inventory_lines(inv_id, 'shortage')
            st['pending_ids'] = [r['id'] for r in rows if not r['disposed_at']]
            st['sel'] &= set(st['pending_ids'])
            shown, note, total = limited(rows, None, '')
            cols = ['الكود', 'الأصل', 'الفئة', 'القيمة الدفترية', 'الاستبعاد'] + ([''] if is_open() else [])
            rows_by_id = {}
            t = ft.DataTable(columns=[ft.DataColumn(ft.Text(c)) for c in cols], rows=[], show_checkbox_column=True,
                             on_select_all=lambda e: select_all(e, rows_by_id))
            for r in shown:
                disposed = bool(r['disposed_at'])
                cells = [ft.DataCell(ft.Text(r['code'], weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(r['name'])),
                         ft.DataCell(ft.Text(r['category'] or '-')), ft.DataCell(ft.Text(fmt_money(r['book_value']))),
                         ft.DataCell(ft.Text(f"مستبعد ({r['disposal_ref']}) - خسارة {fmt_money(r['disposal_loss'])}" if disposed else '-',
                                             size=12, color=theme.DANGER if disposed else None))]
                if is_open():
                    cells.append(ft.DataCell(ft.IconButton(icon=ft.Icons.CHECK_CIRCLE_OUTLINE, icon_color=theme.SUCCESS,
                                                           tooltip='تأكيد إن الأصل موجود (يدويًا - لو الاستيكر مش بيتقرا)',
                                                           on_click=act(lambda lid=r['id']: services.set_inventory_line_found(lid, True), 'ok'))))
                row = ft.DataRow(cells=cells, selected=(r['id'] in st['sel']) and not disposed)
                if not disposed:
                    row.on_select_change = lambda e, lid=r['id'], rw=row: toggle_sel(lid, rw)
                    rows_by_id[r['id']] = row
                t.rows.append(row)
            st['sel_label'] = ft.Text(sel_text(), size=12, color=theme.TEXT_MUTED)
            body = ft.Column([st['sel_label'], note, theme.h_scroll(t)] if shown else [ft.Text('مفيش عجز - كل الأصول المتوقعة اتلاقت ✔' if not total else 'مفيش نتائج للبحث', color=theme.TEXT_MUTED)])
            return body, total

        def found_tab():
            rows = services.list_asset_inventory_lines(inv_id, 'found')
            shown, note, total = limited(rows, None, '')
            cols = ['الكود', 'الأصل', 'وقت المسح', 'مرات', 'الإثبات'] + ([''] if is_open() else [])
            t = ft.DataTable(columns=[ft.DataColumn(ft.Text(c)) for c in cols], rows=[])
            for r in shown:
                cells = [ft.DataCell(ft.Text(r['code'], weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(r['name'])),
                         ft.DataCell(ft.Text(r['scanned_at'].strftime('%H:%M:%S') if r['scanned_at'] else '-')), ft.DataCell(ft.Text(str(r['scan_count']))),
                         ft.DataCell(ft.Text('يدوي' if r['method'] == 'manual' else 'باركود', color=theme.WARNING if r['method'] == 'manual' else None))]
                if is_open():
                    cells.append(ft.DataCell(ft.IconButton(icon=ft.Icons.UNDO, tooltip='تراجع (رجّعه لغير موجود)',
                                                           on_click=act(lambda lid=r['id']: services.set_inventory_line_found(lid, False), 'undo'))))
                t.rows.append(ft.DataRow(cells=cells))
            return ft.Column([note, theme.h_scroll(t)] if shown else [ft.Text('لسه ماتمسحش أي أصل' if not total else 'مفيش نتائج للبحث', color=theme.TEXT_MUTED)]), total

        def surplus_tab():
            rows = services.list_asset_inventory_lines(inv_id, 'surplus')
            shown, note, total = limited(rows, None, '')
            cols = ['الكود', 'الأصل', 'السبب', 'مرات'] + ([''] if is_open() else [])
            t = ft.DataTable(columns=[ft.DataColumn(ft.Text(c)) for c in cols], rows=[])
            for r in shown:
                cells = [ft.DataCell(ft.Text(r['code'], weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(r['name'] or '-')),
                         ft.DataCell(ft.Text(r['reason_label'], size=12, color=theme.WARNING)), ft.DataCell(ft.Text(str(r['scan_count'])))]
                if is_open():
                    cells.append(ft.DataCell(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف (اتمسح بالغلط)',
                                                           on_click=act(lambda lid=r['id']: services.delete_inventory_extra_line(lid), 'del'))))
                t.rows.append(ft.DataRow(cells=cells))
            return ft.Column([note, theme.h_scroll(t)] if shown else [ft.Text('مفيش زيادة' if not total else 'مفيش نتائج للبحث', color=theme.TEXT_MUTED)]), total

        include_sw = ft.Switch(label='تضمين الأصول الموجودة في التقرير', value=False)

        def export(kind):
            def handler(e):
                try:
                    path = services.export_asset_inventory(inv_id, kind, include_found=include_sw.value)
                    theme.open_or_download_file(page, path)
                    snack(f'تم إنشاء التقرير: {path}')
                except Exception as ex:
                    snack(f'تعذر إنشاء التقرير: {ex}')
            return handler

        # ---------- استبعاد العجز (اختياري) ----------
        def open_dispose_dialog(e=None):
            sel = set(st['sel']) & set(st['pending_ids'])
            scope_dd = ft.Dropdown(label='الأصول اللي هتتستبعد', width=420, value='selected' if sel else 'all', options=[
                ft.dropdown.Option('all', 'كل العجز المتبقي (اللي لسه ما اتستبعدش)'),
                ft.dropdown.Option('selected', f'الأصول المحددة في جدول العجز ({len(sel)})')] if sel else [
                ft.dropdown.Option('all', 'كل العجز المتبقي (اللي لسه ما اتستبعدش)')])
            date_f = theme.DateField('تاريخ الاستبعاد (تاريخ القيد)', page, width=240, value=datetime.date.today().strftime('%Y-%m-%d'))
            cfg = services.get_accounting_settings()
            acct_opts = [('', 'حساب الخسارة الافتراضي (الإعدادات) / مصروف إهلاك الأصل')] + [
                (str(a.id), f'{a.code} - {a.name}') for a in services.list_accounts(postable_only=True)]
            loss_dd = theme.SearchableDropdown(label='حساب الخسارة (اختياري)', width=420, options=acct_opts, value='')
            info = ft.Column(spacing=4)
            err = ft.Text('', color=theme.DANGER, visible=False)

            def ids_now():
                return sorted(sel) if scope_dd.value == 'selected' else None

            def update_preview(e=None):
                try:
                    pv = services.preview_inventory_shortage_disposal(inv_id, ids_now(), int(loss_dd.value) if loss_dd.value else None)
                    rows = [f"عدد الأصول: {len(pv['items'])}", f"إجمالي التكلفة: {fmt_money(pv['total_cost'])}",
                            f"مجمّع الإهلاك: {fmt_money(pv['total_accumulated'])}", f"الخسارة المسجّلة (صافي القيمة الدفترية): {fmt_money(pv['total_loss'])}"]
                    info.controls = [ft.Text(r, weight=ft.FontWeight.BOLD if r.startswith('الخسارة') else None,
                                             color=theme.DANGER if r.startswith('الخسارة') else None) for r in rows]
                    if pv['skipped']:
                        info.controls.append(ft.Text(f"هيتخطّى {len(pv['skipped'])} أصل: " + '؛ '.join(f"{x['code']} ({x['reason']})" for x in pv['skipped'][:3]),
                                                     size=12, color=theme.WARNING))
                except Exception as ex:
                    info.controls = [ft.Text(str(ex), color=theme.DANGER)]
                page.update()

            scope_dd.on_change = update_preview
            loss_dd.on_change = update_preview

            def confirm(ev):
                try:
                    d = datetime.datetime.strptime(date_f.value, '%Y-%m-%d')
                    res = services.dispose_inventory_shortage(inv_id, d, ids_now(), int(loss_dd.value) if loss_dd.value else None)
                    dlg.open = False
                    msg = f"تم استبعاد {res['count']} أصل بخسارة {fmt_money(res['total_loss'])} - القيد {res['journal_number']}"
                    if res['skipped']:
                        msg += f" (اتخطّى {len(res['skipped'])})"
                    st['sel'].clear(); play('done')
                    set_banner('ok', f"تم استبعاد {res['count']} أصل", f"القيد {res['journal_number']} - الخسارة {fmt_money(res['total_loss'])}")
                    refresh(); snack(msg)
                except Exception as ex:
                    err.value = str(ex); err.visible = True; page.update()

            dlg = ft.AlertDialog(
                modal=True, title=ft.Text('استبعاد أصول العجز'),
                content=ft.Container(width=460, content=ft.Column([
                    ft.Text('هيتعمل قيد واحد: مدين مجمّع الإهلاك + مدين الخسارة / دائن حساب الأصل، والأصول بتتعلّم "مستبعدة". '
                            'تقدر تتراجع بعدين من نفس المكان (بقيد عكسي).', size=12, color=theme.TEXT_MUTED),
                    scope_dd, date_f.control, loss_dd.control, ft.Divider(height=6), info, err], spacing=10, tight=True, scroll=ft.ScrollMode.AUTO)),
                actions=[ft.TextButton('تراجع', on_click=lambda ev: (setattr(dlg, 'open', False), page.update())),
                         ft.FilledButton('تأكيد الاستبعاد', icon=ft.Icons.DELETE_SWEEP_OUTLINED, bgcolor=theme.DANGER, on_click=confirm)],
                actions_alignment=ft.MainAxisAlignment.END)
            page.overlay.append(dlg); dlg.open = True
            update_preview()

        def open_undo_dialog(e=None):
            def do(ev):
                try:
                    res = services.undo_inventory_shortage_disposal(inv_id)
                    dlg.open = False; refresh()
                    snack(f"تم التراجع: {res['restored_assets']} أصل رجعوا نشطين + {res['reversed_entries']} قيد عكسي")
                except Exception as ex:
                    dlg.open = False; snack(str(ex))
            dlg = ft.AlertDialog(modal=True, title=ft.Text('التراجع عن استبعاد العجز'),
                                 content=ft.Text('هيتعمل قيد عكسي لكل قيد استبعاد اتعمل من الجرد ده، وكل الأصول اللي اتستبعدت هترجع نشطة.'),
                                 actions=[ft.TextButton('لأ', on_click=lambda ev: (setattr(dlg, 'open', False), page.update())),
                                          ft.FilledButton('تراجع عن الاستبعاد', bgcolor=theme.WARNING, on_click=do)])
            page.overlay.append(dlg); dlg.open = True; page.update()

        def disposal_section(sm):
            items = [ft.Text('استبعاد العجز (اختياري)', weight=ft.FontWeight.BOLD, size=15)]
            if sm['disposed_count']:
                items.append(ft.Text(f"تم استبعاد {sm['disposed_count']} أصل بخسارة {fmt_money(sm['disposed_loss'])}", color=theme.DANGER, weight=ft.FontWeight.BOLD))
            items.append(ft.Text(f"عجز متبقٍ لم يُستبعد: {sm['pending_count']} أصل - صافي قيمته الدفترية {fmt_money(sm['pending_book_value'])}", size=13))
            can = (not is_open()) and sm['pending_count'] > 0
            btns = [ft.FilledButton('استبعاد أصول العجز (بخسارتها)', icon=ft.Icons.DELETE_SWEEP_OUTLINED, bgcolor=theme.DANGER,
                                    disabled=not can, on_click=open_dispose_dialog)]
            if sm['disposed_count']:
                btns.append(ft.OutlinedButton('تراجع عن استبعاد العجز', icon=ft.Icons.UNDO, on_click=open_undo_dialog))
            items.append(ft.Row(btns, spacing=10, wrap=True))
            if is_open():
                items.append(ft.Text('الزر بيشتغل بعد إنهاء الجرد (عشان العجز يبقى نهائي).', size=12, color=theme.TEXT_MUTED))
            elif sm['pending_count'] == 0:
                items.append(ft.Text('مفيش عجز متبقٍ للاستبعاد.', size=12, color=theme.TEXT_MUTED))
            return ft.Column(items, spacing=8)

        def summary_tab():
            rep = services.asset_inventory_report(inv_id); sm = rep['summary']
            def line(label, value, color=None, bold=False):
                return ft.Row([ft.Text(label, expand=True, weight=ft.FontWeight.BOLD if bold else None),
                               ft.Text(str(value), weight=ft.FontWeight.BOLD, color=color)], width=520)
            dispose_section = disposal_section(sm)
            return ft.Column([
                line('عدد الأصول المتوقعة (حسب السجلات)', sm['expected']),
                line('تم العثور عليها', f"{sm['found']}  ({sm['match_pct']:g}%)", theme.SUCCESS),
                line('   منها مؤكّدة يدويًا (بدون باركود)', sm['manual_confirmed']),
                ft.Divider(height=8),
                line('العجز - أصول مسجّلة ولم يتم العثور عليها', sm['shortage_count'], theme.DANGER, True),
                line('   قيمة العجز بالتكلفة', fmt_money(sm['shortage_cost']), theme.DANGER),
                line('   قيمة العجز بصافي القيمة الدفترية', fmt_money(sm['shortage_book_value']), theme.DANGER),
                ft.Divider(height=8),
                line('الزيادة - أصول موجودة وغير متوقعة', sm['surplus_count'], theme.WARNING, True),
                line('   منها أكواد غير مسجّلة في النظام', sm['surplus_unknown']),
                line('   منها أصول مسجّلة خارج النطاق أو مستبعدة', sm['surplus_known']),
                ft.Divider(height=8),
                include_sw,
                ft.Row([ft.FilledButton('تقرير PDF', icon=ft.Icons.PICTURE_AS_PDF, bgcolor=theme.PRIMARY, on_click=export('pdf')),
                        ft.OutlinedButton('تقرير Excel', icon=ft.Icons.TABLE_VIEW, on_click=export('xlsx'))], spacing=10),
                ft.Text('التقرير فيه الملخص + قايمة العجز (بالتكلفة والقيمة الدفترية) + قايمة الزيادة وسببها، وخانات توقيع لجنة الجرد.', size=12, color=theme.TEXT_MUTED),
                ft.Divider(height=8),
                dispose_section,
            ], spacing=8)

        # ---------- التحديث ----------
        def refresh():
            st['inv'] = services.get_asset_inventory(inv_id)
            inv = st['inv']
            title_txt.value = f"{inv['number']} - {inv['name']}  ({'مقفول' if inv['state'] == 'closed' else 'مفتوح'})"
            scope_txt.value = f"{inv['scope_label']}   |   بدأ: {inv['date']:%Y-%m-%d %H:%M}" + (f"   |   اتقفل: {inv['closed_at']:%Y-%m-%d %H:%M}" if inv['closed_at'] else '')
            for k in counters:
                counters[k].value = str(inv[k])
            pct = (inv['found'] / inv['expected'] * 100) if inv['expected'] else 0
            progress.value = pct / 100.0
            pct_txt.value = f"{pct:g}% اتلاقى من المتوقع"
            scan_f.disabled = not is_open()
            state_btn.text = 'إعادة فتح الجرد' if not is_open() else 'إنهاء الجرد'
            state_btn.icon = ft.Icons.LOCK_OPEN if not is_open() else ft.Icons.LOCK_OUTLINE
            short, n_short = shortage_tab(); found, n_found = found_tab(); sur, n_sur = surplus_tab()
            tabs.set_tabs([(f'العجز المحتمل ({inv["shortage"]})', short), (f'تم العثور ({inv["found"]})', found),
                           (f'الزيادة ({inv["surplus"]})', sur), ('الملخص والتقرير', summary_tab())])
            recent_col.controls = [ft.Text(x, size=12, color=theme.TEXT_MUTED) for x in st['recent'][:6]]
            page.update()

        def on_scan(e):
            code = (scan_f.value or '').strip()
            scan_f.value = ''
            if not code:
                focus_on(scan_f); return
            try:
                res = services.scan_asset_code(inv_id, code)
            except Exception as ex:
                set_banner('error', 'تعذر المسح', str(ex)); play('error')
                refresh(); focus_on(scan_f); return
            label = f"{res['code']}" + (f" - {res['name']}" if res['name'] else '')
            if res['status'] == 'found':
                set_banner('ok', f'✔ تم العثور: {label}', 'اتسجّل ضمن الأصول الموجودة'); play('ok'); tag = '✔'
            elif res['status'] == 'duplicate':
                set_banner('dup', f'⚠ اتمسح قبل كده: {label}', f"عدد مرات المسح: {res['scan_count']}" + ('  (بند زيادة)' if res['is_extra'] else '')); play('dup'); tag = '⚠'
            else:
                set_banner('error', f'✖ زيادة: {label}', services.EXTRA_REASON_LABELS.get(res['reason'], '')); play('error'); tag = '✖'
            st['recent'].insert(0, f"{datetime.datetime.now():%H:%M:%S}  {tag}  {label}")
            refresh(); focus_on(scan_f)

        scan_f.on_submit = on_scan
        filter_f.on_change = lambda e: refresh()

        def toggle_state(e):
            try:
                if is_open():
                    def do(ev):
                        try:
                            services.close_asset_inventory(inv_id); dlg.open = False
                            set_banner('ok', 'تم إنهاء الجرد', 'التقرير جاهز من تاب "الملخص والتقرير"'); play('done'); refresh()
                        except Exception as ex:
                            dlg.open = False; snack(str(ex))
                    inv = st['inv']
                    dlg = ft.AlertDialog(modal=True, title=ft.Text('إنهاء الجرد'),
                                         content=ft.Text(f"هيتقفل الجرد ومش هتقدر تمسح بعد كده إلا لو أعدت فتحه.\nتم العثور على {inv['found']} من {inv['expected']} - العجز {inv['shortage']} والزيادة {inv['surplus']}."),
                                         actions=[ft.TextButton('تراجع', on_click=lambda ev: (setattr(dlg, 'open', False), page.update())),
                                                  ft.FilledButton('إنهاء الجرد', bgcolor=theme.PRIMARY, on_click=do)])
                    page.overlay.append(dlg); dlg.open = True; page.update()
                else:
                    services.reopen_asset_inventory(inv_id); set_banner('ready', 'الجرد مفتوح', 'كمّل المسح'); refresh(); focus_on(scan_f)
            except Exception as ex:
                snack(str(ex))
        state_btn.on_click = toggle_state

        def card(label, key, color=None):
            c_ = theme.card(ft.Column([ft.Text(label, size=12, color=theme.TEXT_MUTED), counters[key]], spacing=2))
            c_.width = 160
            return c_

        sound_tests = ft.Row([ft.Text('تجربة الصوت:', size=12, color=theme.TEXT_MUTED)] + [
            ft.TextButton(t, on_click=lambda e, k=k: play(k)) for t, k in (('✔ نجاح', 'ok'), ('⚠ مكرر', 'dup'), ('✖ خطأ', 'error'))], spacing=0)

        refresh_placeholder = ft.Container()
        view = ft.Column([
            ft.Row([ft.OutlinedButton('رجوع للقايمة', icon=ft.Icons.ARROW_FORWARD, on_click=lambda e: (show_list(), page.update())),
                    ft.Column([title_txt, scope_txt], spacing=0, expand=True), state_btn]),
            theme.card(ft.Column([
                ft.Row([scan_f, sound_sw], wrap=True, spacing=16), banner, sound_tests,
                ft.Column([ft.Text('آخر عمليات المسح', size=12, weight=ft.FontWeight.BOLD), recent_col], spacing=2),
            ], spacing=12)),
            ft.Row([card('المتوقع', 'expected'), card('تم العثور', 'found'), card('العجز المحتمل', 'shortage'), card('الزيادة', 'surplus'),
                    ft.Column([progress, pct_txt], spacing=4, width=260)], wrap=True, spacing=12),
            filter_f,
            theme.card(tabs.control, expand=True),
        ], spacing=12, expand=True)
        root.controls = [view]
        theme.call_without_page_update(page, refresh)
        set_banner('ready', 'جاهز للمسح', 'اضغط على الحقل ثم امسح أول أصل' if is_open() else 'الجرد مقفول - أعد فتحه لو عايز تكمّل المسح')

    theme.call_without_page_update(page, show_list)
    return root
