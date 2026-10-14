import datetime
import os
import flet as ft
from .. import services, theme

STATE_COLORS = {'active': theme.PRIMARY, 'completed': theme.SUCCESS, 'stopped': theme.WARNING, 'cancelled': theme.TEXT_MUTED}


def build_prepaid_expenses(page: ft.Page):
    """المصروفات المدفوعة مقدمًا: بتسجّل مبلغ اتدفع مرة واحدة (إيجار سنة، تأمين، اشتراك...) وبيتقسّم آليًا على مدته؛ كل شهر
    بيترحّل قسط للمصروف (مدين المصروف / دائن المدفوع مقدمًا). فيها قوالب جاهزة بحساب المصروف والمدة وطريقة التقسيم."""
    today = datetime.date.today()
    cards = ft.Row(wrap=True, spacing=12)
    banner = ft.Container(visible=False, bgcolor=theme.WARNING_LIGHT, border_radius=10, padding=ft.Padding(left=14, right=14, top=10, bottom=10))
    cfg = services.get_accounting_settings()

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def close(d):
        d.open = False; page.update()

    def _d(v):
        v = (v or '').strip()
        return datetime.datetime.strptime(v, '%Y-%m-%d') if v else None

    def money(v):
        return f'{v:,.2f}'

    # ===================================================================== القايمة
    state_f = ft.Dropdown(label='الحالة', width=170, value='active', options=[ft.dropdown.Option('', 'الكل')] + [ft.dropdown.Option(k, v) for k, v in services.PREPAID_STATE_LABELS.items()])
    search_f = ft.TextField(label='بحث (رقم / بيان / مورد / حساب)', width=280, prefix_icon=ft.Icons.SEARCH)

    def row_builder(r):
        st = r['state']
        acts = [ft.IconButton(icon=ft.Icons.LIST_ALT_OUTLINED, tooltip='جدول الأقساط', icon_color=theme.PRIMARY, on_click=lambda e, x=r: open_schedule(x['id']))]
        if st == 'active':
            if r['due_count']:
                acts.append(ft.TextButton(f"ترحيل ({r['due_count']})", icon=ft.Icons.PLAY_ARROW, on_click=lambda e, x=r: post_item(x['id']), style=ft.ButtonStyle(color=theme.SUCCESS, padding=ft.Padding(left=6, right=6, top=2, bottom=2))))
            acts.append(ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل (البيان / الحساب / الترحيل الآلي)', on_click=lambda e, x=r: open_edit(x['id'])))
            acts.append(ft.IconButton(icon=ft.Icons.STOP_CIRCLE_OUTLINED, tooltip='إيقاف قبل نهاية المدة', icon_color=theme.WARNING, on_click=lambda e, x=r: open_stop(x['id'])))
            if r['lines_posted'] == 0:
                acts.append(ft.IconButton(icon=ft.Icons.CANCEL_OUTLINED, tooltip='إلغاء (لسه ما اترحّلش أي قسط)', icon_color=theme.DANGER, on_click=lambda e, x=r: confirm_cancel(x)))
        period = f"{r['start_date']:%Y-%m-%d} ← {r['end_date']:%Y-%m-%d}" if r['end_date'] else f"{r['start_date']:%Y-%m-%d}"
        return ft.DataRow(color=ft.Colors.with_opacity(0.08, theme.WARNING) if (st == 'active' and r['due_count']) else None, cells=[
            ft.DataCell(ft.Text(r['number'], weight=ft.FontWeight.BOLD)),
            ft.DataCell(ft.Column([ft.Text(r['title'], weight=ft.FontWeight.BOLD), ft.Text((r['template'] + ' - ' if r['template'] else '') + (r['supplier'] or ''), size=10.5, color=theme.TEXT_MUTED)], spacing=0, tight=True)),
            ft.DataCell(ft.Text(r['expense_account'], size=11.5)),
            ft.DataCell(ft.Column([ft.Text(period, size=11.5), ft.Text(f"{r['months']} شهر - {services.PREPAID_METHODS[r['method']]}", size=10.5, color=theme.TEXT_MUTED)], spacing=0, tight=True)),
            ft.DataCell(ft.Text(money(r['amount']), weight=ft.FontWeight.BOLD)),
            ft.DataCell(ft.Text(money(r['posted']), color=theme.DANGER)),
            ft.DataCell(ft.Text(money(r['remaining']), color=theme.PRIMARY, weight=ft.FontWeight.BOLD)),
            ft.DataCell(ft.Column([ft.ProgressBar(value=min(1.0, r['progress'] / 100.0), width=90, height=6, color=theme.SUCCESS, bgcolor=theme.SURFACE_ALT),
                                   ft.Text(f"{r['lines_posted']}/{r['lines_total']} قسط - {r['progress']:.0f}%", size=10.5, color=theme.TEXT_MUTED)], spacing=3, tight=True)),
            ft.DataCell(ft.Text((f"{r['next_due']:%Y-%m-%d}" if r['next_due'] else '-'), size=12, color=theme.WARNING if r['due_count'] else None)),
            ft.DataCell(ft.Text(services.PREPAID_STATE_LABELS[st], color=STATE_COLORS[st], weight=ft.FontWeight.BOLD)),
            ft.DataCell(ft.Row(acts, spacing=0))])

    table = theme.SortableDataTable(columns=[
        ('الرقم', lambda r: r['number']), ('البيان', lambda r: r['title']), ('حساب المصروف', lambda r: r['expense_account']), ('المدة', lambda r: r['start_date']),
        ('المبلغ', lambda r: r['amount'], True), ('اتحمّل كمصروف', lambda r: r['posted'], True), ('المتبقي', lambda r: r['remaining'], True), ('التقدّم', lambda r: r['progress'], True),
        ('القسط الجاي', lambda r: r['next_due'] or datetime.datetime.max), ('الحالة', lambda r: r['state']), ('الإجراءات', None)], row_builder=row_builder, page=page, expand=True)

    def refresh(e=None):
        table.set_data(services.list_prepaid_expenses(state_f.value or None, search_f.value))
        sm = services.prepaid_summary()
        def card(label, value, color, sub):
            return theme.card(ft.Column([ft.Text(label, size=12, color=theme.TEXT_MUTED), ft.Text(value, size=21, weight=ft.FontWeight.BOLD, color=color), ft.Text(sub, size=11, color=theme.TEXT_MUTED)], spacing=0, tight=True), padding=14)
        cards.controls = [card('مصروفات مقدمة نشطة', money(sm['total']), theme.PRIMARY, f"{sm['count']} مصروف"), card('اتحمّل كمصروف', money(sm['posted']), theme.DANGER, 'أقساط اترحّلت'),
                          card('رصيد المدفوع مقدمًا (متبقي)', money(sm['remaining']), theme.SUCCESS, 'لسه هيتحمّل على الشهور الجاية'), card('مستحق الترحيل', money(sm['due_amount']), theme.WARNING, f"{sm['due_count']} قسط")]
        if sm['due_count']:
            banner.content = ft.Row([ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE_OUTLINED, color=theme.WARNING), ft.Text(f"فيه {sm['due_count']} قسط مستحق بقيمة {money(sm['due_amount'])} لسه ما اترحّلش (الترحيل الآلي مقفول عليها، أو الفترة مقفولة).", color=theme.WARNING_TEXT, size=12, expand=True),
                                    ft.FilledButton('ترحيل الاستحقاقات الآن', icon=ft.Icons.PLAY_ARROW, bgcolor=theme.WARNING, on_click=post_all)], spacing=8)
            banner.visible = True
        else:
            banner.visible = False
        if e is not None:
            page.update()

    state_f.on_change = refresh; search_f.on_change = refresh

    def report_msg(rep):
        msg = f"اترحّل {rep['posted']} قسط بقيمة {money(rep['amount'])}" if rep['posted'] else 'مفيش أقساط مستحقة للترحيل'
        if rep['errors']:
            msg += f" | تعذّر {len(rep['errors'])}: {rep['errors'][0]}"
        return msg

    def post_all(e=None):
        try:
            rep = services.post_due_prepaid_lines(); refresh(True); snack(report_msg(rep))
        except Exception as ex:
            snack(str(ex))

    def post_item(pid):
        try:
            rep = services._post_due_prepaid(only_auto=False, prepaid_id=pid); refresh(True); snack(report_msg(rep))
        except Exception as ex:
            snack(str(ex))

    # ===================================================================== جدول الأقساط
    def open_schedule(pid):
        r = services.get_prepaid_expense(pid)
        line_labels = {'posted': ('مرحّل', theme.SUCCESS), 'pending': ('قادم', theme.PRIMARY), 'void': ('ملغى', theme.TEXT_MUTED)}
        now = datetime.datetime.now()

        def post_line(lid):
            try:
                services.post_prepaid_line_now(lid); close(sdlg); refresh(True); open_schedule(pid)
            except Exception as ex:
                snack(str(ex))
        rows = []
        for l in r['lines']:
            lbl, col = line_labels[l['state']]
            late = l['state'] == 'pending' and l['entry_date'] <= now
            rows.append(ft.DataRow(color=ft.Colors.with_opacity(0.1, theme.WARNING) if late else None, cells=[
                ft.DataCell(ft.Text(str(l['seq']))), ft.DataCell(ft.Text(f"{l['period_from']:%Y-%m-%d} ← {l['period_to']:%Y-%m-%d}", size=12)),
                ft.DataCell(ft.Text(f"{l['entry_date']:%Y-%m-%d}", size=12)), ft.DataCell(ft.Text(money(l['amount']), weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(lbl + (' (مستحق)' if late else ''), color=col, weight=ft.FontWeight.BOLD, size=12)),
                ft.DataCell(ft.Text(f"{l['posted_at']:%Y-%m-%d}" if l['posted_at'] else '-', size=12, color=theme.TEXT_MUTED)),
                ft.DataCell(ft.TextButton('ترحيل الآن', on_click=lambda e, i=l['id']: post_line(i)) if l['state'] == 'pending' and r['state'] == 'active' else ft.Text(''))]))
        tbl = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['م', 'الفترة', 'تاريخ الاستحقاق', 'المبلغ', 'الحالة', 'تاريخ الترحيل', '']], rows=rows, heading_row_height=36, data_row_min_height=34)

        def export(kind):
            try:
                from ..report_export import export_pdf, export_excel
                data = {'prepaid': r, 'date_from': None, 'date_to': None, 'title_suffix': f"{r['number']} - {r['title']}"}
                out_dir = os.path.join(services.APP_DIR, 'exports'); os.makedirs(out_dir, exist_ok=True)
                theme.open_or_download_file(page, (export_pdf if kind == 'pdf' else export_excel)(data, 'prepaid_schedule', out_dir))
            except Exception as ex:
                snack(f'تعذر التصدير: {ex}')
        pay = r['payment_method'] if r['payment_kind'] == 'paid' else ('آجل - ' + r['supplier'] if r['payment_kind'] == 'payable' else 'متسجّل قبل كده')
        info = [ft.Text(f"{r['title']}  |  {r['expense_account']}", weight=ft.FontWeight.BOLD),
                ft.Text(f"المبلغ {money(r['amount'])}" + (f" + ضريبة {money(r['tax_amount'])}" if r['tax_amount'] else '') + f"  |  السداد: {pay}  |  مرحّل {money(r['posted'])}  |  متبقي {money(r['remaining'])}", size=12, color=theme.TEXT_MUTED)]
        sdlg = ft.AlertDialog(modal=True, title=ft.Text(f"جدول أقساط {r['number']}"), content=ft.Container(width=780, content=ft.Column(info + [theme.h_scroll(tbl)], tight=True, spacing=8, scroll=ft.ScrollMode.AUTO, height=min(480, 150 + 36 * len(rows)))),
                              actions=[ft.TextButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf')), ft.TextButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('excel')),
                                       ft.TextButton('إغلاق', on_click=lambda e: close(sdlg))])
        page.overlay.append(sdlg); sdlg.open = True; page.update()

    # ===================================================================== مصروف جديد
    expense_accounts = [a for a in services.list_accounts(postable_only=True) if a.account_type == 'expense']
    all_postable = services.list_accounts(postable_only=True)
    f_template = ft.Dropdown(label='القالب (اختياري - بيعبّي الحساب والمدة)', width=320, options=[])
    f_title = ft.TextField(label='بيان المصروف *', width=320, hint_text='مثلًا: إيجار المحل - سنة 2026')
    f_expense = theme.SearchableDropdown(label='حساب المصروف *', width=320, options=[(str(a.id), f'{a.code} - {a.name}') for a in expense_accounts])
    f_prepaid = theme.SearchableDropdown(label='حساب المصروفات المدفوعة مقدمًا', width=320, options=[(str(a.id), f'{a.code} - {a.name}') for a in all_postable if a.account_type == 'asset'])
    f_amount = ft.TextField(label='المبلغ المقسَّم (قبل الضريبة) *', width=190, keyboard_type=ft.KeyboardType.NUMBER)
    f_tax = ft.TextField(label='ضريبة %', width=100, value=f"{(services.get_company_settings().default_tax_rate if services.get_company_settings() and services.get_company_settings().default_tax_rate is not None else 15):g}", keyboard_type=ft.KeyboardType.NUMBER)
    f_start = theme.DateField('بداية المدة *', page, width=170, value=today.strftime('%Y-%m-%d'))
    f_months = ft.TextField(label='المدة (شهور) *', width=120, value='12', keyboard_type=ft.KeyboardType.NUMBER)
    f_method = ft.Dropdown(label='طريقة التقسيم', width=230, value='equal', options=[ft.dropdown.Option(k, v) for k, v in services.PREPAID_METHODS.items()])
    f_kind = ft.RadioGroup(value='paid', content=ft.Column([ft.Radio(value=k, label=v) for k, v in services.PREPAID_PAYMENT_KINDS.items()], spacing=0))
    f_pm = ft.Dropdown(label='طريقة الدفع', width=230, options=[])
    f_supplier = theme.SearchableDropdown(label='المورد', width=260, options=[])
    f_branch = ft.Dropdown(label='الفرع', width=200, options=[]); f_cc = ft.Dropdown(label='مركز التكلفة', width=200, options=[])
    f_auto = ft.Switch(label='ترحيل الأقساط المستحقة آليًا (عند فتح البرنامج)', value=True)
    f_notes = ft.TextField(label='ملاحظات', width=660)
    f_err = ft.Text('', color=theme.DANGER, visible=False, size=12)
    f_summary = ft.Text('', size=12.5, weight=ft.FontWeight.BOLD, color=theme.PRIMARY_TEXT)
    f_prev = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, height=170)
    templates = {}

    def num(f, label):
        try:
            return float((f.value or '0').replace(',', '') or 0)
        except ValueError:
            raise ValueError(f'{label}: اكتب رقم صحيح')

    def on_kind(e=None):
        f_pm.visible = f_kind.value == 'paid'
        f_supplier.control.visible = f_kind.value == 'payable'
        recalc()

    def on_template(e=None):
        t = templates.get(f_template.value or '')
        if t:
            if t.expense_account_id:
                f_expense.value = str(t.expense_account_id)
            f_months.value = str(t.months); f_method.value = t.method
            if not (f_title.value or '').strip():
                f_title.value = t.name
        recalc()

    def recalc(e=None):
        f_prev.controls = []
        try:
            amount = num(f_amount, 'المبلغ'); months = int(num(f_months, 'المدة')); tax = num(f_tax, 'الضريبة')
            if amount <= 0:
                f_summary.value = 'اكتب المبلغ والمدة عشان يظهر جدول التقسيم'; page.update(); return
            sd = _d(f_start.value) or datetime.datetime.now()
            sched = services.prepaid_build_schedule(sd, months, amount, f_method.value)
            tax_amt = round(amount * tax / 100.0, 2)
            f_summary.value = f"{len(sched)} قسط - القسط الأول {money(sched[0]['amount'])} - آخر قسط {sched[-1]['entry_date']:%Y-%m-%d}  |  المدفوع فعليًا: {money(amount + tax_amt) if f_kind.value != 'none' else '—'}" + (f" (منها ضريبة {money(tax_amt)})" if tax_amt and f_kind.value != 'none' else '')
            f_prev.controls = [ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['م', 'الفترة', 'تاريخ الاستحقاق', 'المبلغ']],
                                            rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(str(r['seq']), size=12)), ft.DataCell(ft.Text(f"{r['period_from']:%Y-%m-%d} ← {r['period_to']:%Y-%m-%d}", size=12)),
                                                                    ft.DataCell(ft.Text(f"{r['entry_date']:%Y-%m-%d}", size=12)), ft.DataCell(ft.Text(money(r['amount']), size=12, weight=ft.FontWeight.BOLD))]) for r in sched],
                                            heading_row_height=30, data_row_min_height=28)]
        except Exception as ex:
            f_summary.value = str(ex)
        page.update()

    def save(e):
        try:
            sd = _d(f_start.value)
            pid = services.create_prepaid_expense(
                f_title.value, int(f_expense.value) if f_expense.value else None, num(f_amount, 'المبلغ'), sd, int(num(f_months, 'المدة')), f_method.value, num(f_tax, 'الضريبة'),
                f_kind.value, int(f_pm.value) if f_pm.value else None, int(f_supplier.value) if f_supplier.value else None, int(f_prepaid.value) if f_prepaid.value else None,
                int(f_template.value) if f_template.value else None, int(f_branch.value) if f_branch.value else None, int(f_cc.value) if f_cc.value else None, f_auto.value, f_notes.value)
            close(form); refresh(True)
            p = services.get_prepaid_expense(pid)
            snack(f"تم تسجيل {p['number']} - اترحّل {p['lines_posted']} قسط مستحق بقيمة {money(p['posted'])}" if p['lines_posted'] else f"تم تسجيل {p['number']} - الأقساط هتترحّل لوحدها في مواعيدها")
        except Exception as ex:
            f_err.value = str(ex); f_err.visible = True; page.update()

    for c in (f_amount, f_tax, f_months):
        c.on_change = recalc
    f_start.on_change = recalc; f_method.on_change = recalc; f_template.on_change = on_template; f_kind.on_change = on_kind
    form = ft.AlertDialog(modal=True, title=ft.Text('مصروف مدفوع مقدمًا جديد'),
        content=ft.Container(width=720, content=ft.Column([
            ft.Row([f_template, f_title], wrap=True, spacing=10), ft.Row([f_expense.control, f_prepaid.control], wrap=True, spacing=10),
            ft.Row([f_amount, f_tax, f_start.control, f_months, f_method], wrap=True, spacing=10),
            ft.Text('السداد', weight=ft.FontWeight.BOLD), f_kind, ft.Row([f_pm, f_supplier.control], wrap=True, spacing=10), ft.Row([f_branch, f_cc], wrap=True, spacing=10), f_auto, f_notes,
            ft.Divider(), ft.Text('معاينة جدول التقسيم', weight=ft.FontWeight.BOLD), f_summary, f_prev, f_err], tight=True, spacing=8, scroll=ft.ScrollMode.AUTO, height=620)),
        actions=[ft.TextButton('إلغاء', on_click=lambda e: close(form)), ft.FilledButton('حفظ وتفعيل التقسيم', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save)])
    page.overlay.append(form)

    def open_form(e=None):
        nonlocal templates
        tl = services.list_prepaid_templates()
        templates = {str(t.id): t for t in tl}
        f_template.options = [ft.dropdown.Option('', 'بدون قالب')] + [ft.dropdown.Option(str(t.id), t.name) for t in tl]; f_template.value = ''
        f_supplier.options = [(str(x.id), x.name) for x in services.list_suppliers()]
        f_pm.options = [ft.dropdown.Option(str(m.id), m.name) for m in services.list_payment_methods(active_only=True) if not m.is_credit]
        f_pm.value = f_pm.options[0].key if f_pm.options else None
        allowed = services.user_branch_ids()
        f_branch.options = [ft.dropdown.Option(str(b.id), f'{b.code} - {b.name}') for b in services.list_branches(True) if not allowed or b.id in allowed]
        f_cc.options = [ft.dropdown.Option(str(c.id), f'{c.code} - {c.name}') for c in services.list_cost_centers(True)]
        bid = services.default_branch_id(); cid = services.default_cost_center_id()
        f_branch.value = str(bid) if bid else None; f_cc.value = str(cid) if cid else None
        f_title.value = ''; f_expense.value = None; f_prepaid.value = str(cfg.prepaid_expenses_account_id) if cfg and cfg.prepaid_expenses_account_id else None
        f_amount.value = ''; f_start.value = today.strftime('%Y-%m-%d'); f_months.value = '12'; f_method.value = 'equal'; f_kind.value = 'paid'; f_supplier.value = None
        f_auto.value = True; f_notes.value = ''; f_err.visible = False
        on_kind(); form.open = True; page.update()

    # ===================================================================== تعديل / إيقاف / إلغاء
    def open_edit(pid):
        r = services.get_prepaid_expense(pid)
        t = ft.TextField(label='البيان *', value=r['title'], width=420); n = ft.TextField(label='ملاحظات', value=r['notes'], width=420)
        ex = theme.SearchableDropdown(label='حساب المصروف (للأقساط الجاية بس)', width=420, options=[(str(a.id), f'{a.code} - {a.name}') for a in expense_accounts], value=str(r['expense_account_id']))
        au = ft.Switch(label='ترحيل الأقساط المستحقة آليًا', value=r['auto_post']); err = ft.Text('', color=theme.DANGER, visible=False, size=12)

        def ok(e):
            try:
                services.update_prepaid_expense(pid, t.value, n.value, int(ex.value) if ex.value else None, au.value)
                close(edlg); refresh(True); snack('تم التعديل')
            except Exception as e2:
                err.value = str(e2); err.visible = True; page.update()
        edlg = ft.AlertDialog(modal=True, title=ft.Text(f"تعديل {r['number']}"),
                              content=ft.Container(width=460, content=ft.Column([ft.Text('المبلغ والمدة وتواريخ الأقساط مقفولة بعد التسجيل. لتغييرها: الغي المصروف (لو ما اترحّلش أي قسط) وأنشئه من جديد، أو أوقفه.', size=12, color=theme.TEXT_MUTED), t, ex.control, au, n, err], tight=True, spacing=10)),
                              actions=[ft.TextButton('إلغاء', on_click=lambda e: close(edlg)), ft.FilledButton('حفظ', bgcolor=theme.PRIMARY, on_click=ok)])
        page.overlay.append(edlg); edlg.open = True; page.update()

    def open_stop(pid):
        r = services.get_prepaid_expense(pid)
        mode = ft.RadioGroup(value='expense', content=ft.Column([ft.Radio(value='expense', label=f"حمّل المتبقي ({money(r['remaining'])}) كمصروف دلوقتي بقيد واحد"),
                                                                    ft.Radio(value='keep', label='أوقف الأقساط الجاية بس وسيب الرصيد على حساب المدفوع مقدمًا (هتسوّيه يدويًا)')], spacing=2))
        err = ft.Text('', color=theme.DANGER, visible=False, size=12)

        def ok(e):
            try:
                res = services.stop_prepaid_expense(pid, mode.value == 'expense')
                close(sdlg); refresh(True); snack('تم الإيقاف' + (f" وتحميل {money(res['remaining'])} كمصروف" if res['entry_id'] else ''))
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()
        sdlg = ft.AlertDialog(modal=True, title=ft.Text(f"إيقاف {r['number']} قبل نهاية المدة"),
                              content=ft.Container(width=480, content=ft.Column([ft.Text(f"{r['title']} - اترحّل {r['lines_posted']} من {r['lines_total']} قسط", size=13), mode, err], tight=True, spacing=10)),
                              actions=[ft.TextButton('إلغاء', on_click=lambda e: close(sdlg)), ft.FilledButton('تأكيد الإيقاف', bgcolor=theme.WARNING, on_click=ok)])
        page.overlay.append(sdlg); sdlg.open = True; page.update()

    def confirm_cancel(r):
        def ok(e):
            try:
                services.cancel_prepaid_expense(r['id']); close(cdlg); refresh(True); snack('تم الإلغاء وعكس قيد الدفع')
            except Exception as ex:
                close(cdlg); snack(str(ex))
        cdlg = ft.AlertDialog(modal=True, title=ft.Text('إلغاء المصروف المقدم'), content=ft.Text(f'هتلغي {r["number"]} - {r["title"]} وهيتعمل قيد عكسي لقيد الدفع. ده ممكن بس لإنه لسه ما اترحّلش أي قسط.'),
                              actions=[ft.TextButton('تراجع', on_click=lambda e: close(cdlg)), ft.FilledButton('إلغاء المصروف', bgcolor=theme.DANGER, on_click=ok)])
        page.overlay.append(cdlg); cdlg.open = True; page.update()

    # ===================================================================== القوالب
    def open_templates():
        col = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, height=420)

        def render():
            col.controls = [ft.Container(padding=ft.Padding(left=10, right=10, top=6, bottom=6), border_radius=8, bgcolor=theme.PRIMARY_LIGHT if t.is_active else theme.SURFACE_ALT,
                                         content=ft.Row([ft.Column([ft.Text(t.name + ('' if t.is_active else ' (معطّل)'), weight=ft.FontWeight.BOLD), ft.Text(f"{t.expense_account.code + ' - ' + t.expense_account.name if t.expense_account else 'من غير حساب (اختاره وقت الاستخدام)'} | {t.months} شهر | {services.PREPAID_METHODS[t.method]}", size=11, color=theme.TEXT_MUTED)], spacing=0, expand=True),
                                                         ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل', on_click=lambda e, x=t: edit_template(x))])) for t in services.list_prepaid_templates(False)]
            page.update()

        def edit_template(t=None):
            n = ft.TextField(label='اسم القالب *', value=t.name if t else '', width=380)
            ex = theme.SearchableDropdown(label='حساب المصروف', width=380, options=[(str(a.id), f'{a.code} - {a.name}') for a in expense_accounts], value=str(t.expense_account_id) if t and t.expense_account_id else None)
            mo = ft.TextField(label='المدة الافتراضية (شهور)', value=str(t.months if t else 12), width=190, keyboard_type=ft.KeyboardType.NUMBER)
            me = ft.Dropdown(label='طريقة التقسيم', width=230, value=t.method if t else 'equal', options=[ft.dropdown.Option(k, v) for k, v in services.PREPAID_METHODS.items()])
            ac = ft.Switch(label='نشط', value=t.is_active if t else True, visible=bool(t)); err = ft.Text('', color=theme.DANGER, visible=False, size=12)

            def ok(e):
                try:
                    if t:
                        services.update_prepaid_template(t.id, n.value, int(ex.value) if ex.value else None, int(mo.value or 0), me.value, '', ac.value)
                    else:
                        services.create_prepaid_template(n.value, int(ex.value) if ex.value else None, int(mo.value or 0), me.value)
                    close(edlg); render(); snack('تم حفظ القالب')
                except Exception as ex2:
                    err.value = str(ex2); err.visible = True; page.update()
            edlg = ft.AlertDialog(modal=True, title=ft.Text('تعديل قالب' if t else 'قالب جديد'), content=ft.Container(width=420, content=ft.Column([n, ex.control, ft.Row([mo, me], wrap=True, spacing=10), ac, err], tight=True, spacing=10)),
                                  actions=[ft.TextButton('إلغاء', on_click=lambda e: close(edlg)), ft.FilledButton('حفظ', bgcolor=theme.PRIMARY, on_click=ok)])
            page.overlay.append(edlg); edlg.open = True; page.update()
        tdlg = ft.AlertDialog(modal=True, title=ft.Text('قوالب المصروفات المدفوعة مقدمًا'),
                              content=ft.Container(width=560, content=ft.Column([ft.Text('القالب بيحفظ حساب المصروف والمدة وطريقة التقسيم، وبتختاره من شاشة "مصروف جديد" فتتعبّى لوحدها.', size=12, color=theme.TEXT_MUTED), col], tight=True, spacing=8)),
                              actions=[ft.TextButton('إغلاق', on_click=lambda e: close(tdlg)), ft.FilledButton('قالب جديد', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=lambda e: edit_template(None))])
        page.overlay.append(tdlg); tdlg.open = True
        render()

    # ===================================================================== تجميع الشاشة
    rep0 = services.auto_post_prepaid_expenses()      # لو فتحت الشاشة وفيه أقساط مستحقة، بتترحّل
    refresh()
    return ft.Column([
        ft.Row([theme.page_title('المصروفات المدفوعة مقدمًا', 'تقسيم المصروف على مدته آليًا: عند الدفع يتسجّل كمدفوع مقدمًا، وكل شهر بيترحّل قسطه للمصروف'),
                ft.Container(expand=True), ft.OutlinedButton('القوالب', icon=ft.Icons.DASHBOARD_CUSTOMIZE_OUTLINED, on_click=lambda e: open_templates()),
                ft.FilledButton('مصروف مدفوع مقدمًا جديد', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=open_form)], spacing=8),
        ft.Container(height=4), cards, banner, ft.Row([state_f, search_f], spacing=10), ft.Container(height=2),
        theme.card(theme.h_scroll(table.control)),
    ], expand=True, spacing=8, scroll=ft.ScrollMode.AUTO)
