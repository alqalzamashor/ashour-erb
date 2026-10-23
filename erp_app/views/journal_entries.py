import asyncio, datetime, os
import flet as ft
from .. import services, theme, drafts
from . import journal_dialogs
from ..report_export import export_excel, export_pdf


def build_journal_entries(page: ft.Page):
    """شاشة إدخال القيود اليدوية - جدول بألوان متبادلة، عمود عميل/مورد،
    وانتقال بالـ Enter من حقل لحقل بالترتيب، وطباعة/تحميل للقيد الأخير."""
    accounts = services.list_accounts(postable_only=True)
    customers = services.list_customers()
    suppliers = services.list_suppliers()
    employees = services.list_employees()
    branches = services.list_branches(True)
    allowed_branches = services.user_branch_ids()
    branches = [b for b in branches if not allowed_branches or b.id in allowed_branches]
    centers = services.list_cost_centers(True)
    allowed_centers = services.user_cost_center_ids()
    centers = [c for c in centers if not allowed_centers or c.id in allowed_centers]

    def opt_accounts():
        return [ft.dropdown.Option(key=str(a.id), text=f'{a.code} - {a.name}') for a in accounts]

    def sd_opt_accounts():
        return [(str(a.id), f'{a.code} - {a.name}') for a in accounts]

    def opt_branches(include_empty=True):
        opts = [ft.dropdown.Option('', 'غير محدد')] if include_empty else []
        opts += [ft.dropdown.Option(str(b.id), f'{b.code} - {b.name}') for b in branches]
        return opts

    def opt_centers(include_empty=True):
        opts = [ft.dropdown.Option('', 'غير محدد')] if include_empty else []
        opts += [ft.dropdown.Option(str(c.id), f'{c.code} - {c.name}') for c in centers]
        return opts

    def opt_partners():
        opts = [ft.dropdown.Option('', 'بدون')]
        opts += [ft.dropdown.Option(f'customer:{c.id}', f'عميل - {c.name}') for c in customers]
        opts += [ft.dropdown.Option(f'supplier:{s.id}', f'مورد - {s.name}') for s in suppliers]
        return opts

    def opt_employees():
        return [('', 'بدون')] + [(str(emp.id), f'{emp.code} - {emp.name}') for emp in employees]

    def split_partner(item):
        """(نوع الطرف، رقمه) من حقلي العميل/المورد والموظف - طرف واحد بس للسطر."""
        emp = item['employee'].value
        par = item['partner'].value
        if emp and par:
            raise ValueError('السطر ده ليه طرفين: اختار عميل/مورد أو موظف، مش الاتنين')
        if emp:
            return 'employee', int(emp)
        if par:
            ptype, pid_s = par.split(':')
            return ptype, int(pid_s)
        return None, None

    today = datetime.date.today().strftime('%Y-%m-%d')
    date_field = theme.DateField('تاريخ القيد', page, width=160, value=today)
    ref = ft.TextField(label='المرجع', width=180)
    desc = ft.TextField(label='بيان القيد', width=330)
    header_branch = ft.Dropdown(label='الفرع الافتراضي', width=220, options=opt_branches(), value=str(services.default_branch_id() or ''))
    header_center = ft.Dropdown(label='مركز التكلفة الافتراضي', width=230, options=opt_centers(), value='')
    err = ft.Text('', color=theme.DANGER, visible=False)
    tot_debit = ft.Text('0.00', size=18, weight=ft.FontWeight.BOLD)
    tot_credit = ft.Text('0.00', size=18, weight=ft.FontWeight.BOLD)
    tot_diff = ft.Text('0.00', size=18, weight=ft.FontWeight.BOLD)
    bal_icon = ft.Icon(ft.Icons.BALANCE, size=18)
    bal_text = ft.Text('أدخل الأرقام', size=13, weight=ft.FontWeight.BOLD)
    bal_chip = ft.Container(content=ft.Row([bal_icon, bal_text], spacing=6, tight=True), padding=ft.Padding(left=12, right=12, top=6, bottom=6), border_radius=20)

    balance_btn = ft.FilledTonalButton('وازن تلقائيًا', icon=ft.Icons.AUTO_FIX_HIGH, visible=False, tooltip='يكمّل الفرق في سطر على الجانب المقابل')

    def _tot_box(title, value_ctl):
        return ft.Container(content=ft.Column([ft.Text(title, size=11, color=theme.TEXT_MUTED), value_ctl], spacing=0, tight=True),
                            padding=ft.Padding(left=14, right=14, top=8, bottom=8), border_radius=12, bgcolor=theme.SURFACE_ALT)
    last_entry_id = {'value': None}
    edit_mode = {'value': False}

    ROW_COLOR_1 = theme.ROW_BG[0]
    ROW_COLOR_2 = theme.ROW_BG[1]

    MOBILE = bool(theme._page_w())
    W_ACC, W_DESC, W_AMT, W_ACT, W_NUM, GAP = 340, 250, 120, 120, 28, 8

    def _hdr(text, w):
        return ft.Container(ft.Text(text, size=12, weight=ft.FontWeight.BOLD, color=theme.TEXT_MUTED), width=w,
                            alignment=ft.Alignment.CENTER if w == W_AMT else None)

    header_row = ft.Container(
        ft.Row([_hdr('#', W_NUM), _hdr('الحساب (اكتب كود أو اسم للبحث)', W_ACC), _hdr('بيان السطر', W_DESC), _hdr('مدين', W_AMT), _hdr('دائن', W_AMT), _hdr('', W_ACT)], spacing=GAP),
        padding=ft.Padding(left=8, right=8, top=8, bottom=8), bgcolor=theme.SURFACE_ALT, border_radius=10, visible=not MOBILE)
    lines_table = ft.Column([], spacing=4)        # صفوف السطور (كل سطر Container)
    table_host = ft.Column([header_row, lines_table], spacing=6)
    lines = []

    def parse_date(value):
        try:
            return datetime.datetime.strptime((value or '').strip(), '%Y-%m-%d')
        except Exception:
            raise ValueError('صيغة التاريخ يجب أن تكون YYYY-MM-DD')

    def update_totals(e=None):
        debit = credit = 0.0
        for item in lines:
            try:
                debit += float(item['debit'].value or 0)
                credit += float(item['credit'].value or 0)
            except Exception:
                pass
        diff = round(debit - credit, 2)
        tot_debit.value = f'{debit:,.2f}'; tot_credit.value = f'{credit:,.2f}'; tot_diff.value = f'{abs(diff):,.2f}'
        if debit == 0 and credit == 0:
            col, bg, ic, msg = theme.TEXT_MUTED, theme.SURFACE_ALT, ft.Icons.EDIT_NOTE, 'أدخل الأرقام'
        elif diff == 0:
            col, bg, ic, msg = theme.SUCCESS, theme.SUCCESS_LIGHT, ft.Icons.CHECK_CIRCLE, 'القيد متوازن'
        else:
            col, bg, ic, msg = theme.DANGER, theme.DANGER_LIGHT, ft.Icons.ERROR_OUTLINE, ('ناقص دائن ' if diff > 0 else 'ناقص مدين ') + f'{abs(diff):,.2f}'
        tot_diff.color = col; bal_icon.color = col; bal_icon.icon = ic; bal_text.value = msg; bal_text.color = col; bal_chip.bgcolor = bg
        balance_btn.visible = diff != 0 and not locked_state['on']
        autosave_draft()
        page.update()

    locked_state = {'on': False}

    def auto_balance(e=None):
        """يكمّل الفرق في أول سطر فاضي (أو سطر جديد) على الجانب المقابل."""
        debit = sum(float(x['debit'].value or 0) for x in lines)
        credit = sum(float(x['credit'].value or 0) for x in lines)
        diff = round(debit - credit, 2)
        if diff == 0:
            return
        target = next((x for x in lines if _num0(x['debit'].value) and _num0(x['credit'].value)), None)
        if target is None:
            add_line(); target = lines[-1]
        side, other = ('credit', 'debit') if diff > 0 else ('debit', 'credit')
        target[side].value = f'{abs(diff):g}'; target[other].value = '0'
        update_totals()
        if not target['account'].value:
            page.run_task(_safe_focus, target['account'])

    # ---------- حفظ تلقائي للمسودة (لو الاتصال قطع ما يضيعش اللي اتكتب) ----------
    DRAFT_KIND = 'journal_entry'
    draft_state = {'on': True}
    draft_banner_text = ft.Text('', color=theme.WARNING_TEXT, expand=True)
    draft_banner = ft.Container(
        visible=False, padding=10, border_radius=8, bgcolor=theme.SURFACE_ALT,
        content=ft.Row([ft.Icon(ft.Icons.RESTORE, color=theme.WARNING_TEXT), draft_banner_text,
                        ft.TextButton('تجاهل المسودة', on_click=lambda e: discard_draft())], spacing=8))
    LINE_KEYS = ('account', 'description', 'partner', 'employee', 'debit', 'credit', 'branch', 'center')

    def collect_draft():
        return {'date': date_field.value or '', 'ref': ref.value or '', 'desc': desc.value or '',
                'branch': header_branch.value or '', 'center': header_center.value or '',
                'lines': [{k: (x[k].value or '') for k in LINE_KEYS} for x in lines]}

    def _num0(v):
        try:
            return float(v or 0) == 0
        except ValueError:
            return False

    def draft_is_empty(d):
        return (not d['ref'].strip() and not d['desc'].strip() and
                all(not l['account'] and not l['description'].strip() and not l['partner'] and not l['employee'] and _num0(l['debit']) and _num0(l['credit']) for l in d['lines']))

    def autosave_draft(e=None):
        if not draft_state['on'] or edit_mode['value'] or posting_ref['value']:
            return
        d = collect_draft()
        if draft_is_empty(d):
            drafts.clear(DRAFT_KIND)
        else:
            drafts.save(DRAFT_KIND, d)

    def apply_draft(d, saved_at):
        draft_state['on'] = False
        try:
            date_field.value = d.get('date') or today
            ref.value = d.get('ref', ''); desc.value = d.get('desc', '')
            header_branch.value = d.get('branch') or header_branch.value
            header_center.value = d.get('center', '')
            lines.clear(); lines_table.controls.clear()
            for ln in d.get('lines', []):
                add_line()
                it = lines[-1]
                it['account'].value = ln.get('account') or None
                it['description'].value = ln.get('description', ''); it['partner'].value = ln.get('partner', '')
                if str(it['partner'].value).startswith('employee:'):          # مسودة قديمة: الموظف كان جوه قايمة الطرف
                    it['employee'].value = str(it['partner'].value).split(':')[1]; it['partner'].value = ''
                else:
                    it['employee'].value = ln.get('employee', '')
                it['debit'].value = ln.get('debit') or '0'; it['credit'].value = ln.get('credit') or '0'
                it['branch'].value = ln.get('branch', ''); it['center'].value = ln.get('center', '')
            while len(lines) < 2:
                add_line()
            repaint_rows()
            update_totals()
            draft_banner_text.value = f"اتسترجعت مسودة قيد غير مرحّل (آخر حفظ {saved_at:%Y-%m-%d %H:%M}) - كمّل وارحّل، أو اضغط تجاهل."
            draft_banner.visible = True
        finally:
            draft_state['on'] = True

    def discard_draft():
        drafts.clear(DRAFT_KIND)
        draft_banner.visible = False
        new_entry()

    def repaint_rows():
        for i, item in enumerate(lines):
            item['row'].bgcolor = ROW_COLOR_1 if i % 2 == 0 else ROW_COLOR_2
            item['num'].value = str(i + 1)
            refresh_more(item)

    def remove_line(item):
        def remove(e):
            if item in lines:
                lines.remove(item)
            if item['row'] in lines_table.controls:
                lines_table.controls.remove(item['row'])
            while len(lines) < 2:
                add_line()
            repaint_rows()
            update_totals()
        return remove

    async def _safe_focus(control):
        if theme.SearchableDropdown.picker_active():
            return
        try:
            await control.focus()
        except Exception:
            pass  # لو السطر لسه ما اتلحقش يتلحّم بالصفحة، تجاهل بدل ما نكسر الشاشة

    def field_order(item):
        """ترتيب التنقل بالـ Enter/Tab داخل السطر الواحد - بس الحقول
        الأساسية (حساب/بيان/طرف/مدين/دائن)؛ الفرع ومركز التكلفة بالماوس لو
        احتجتهم، عشان الإنتر من دائن يروح لسطر جديد على طول."""
        return [item['account'], item['description'], item['debit'], item['credit']] if not MOBILE else [item['account'], item['debit'], item['credit']]

    posting_ref = {'value': False}

    def focus_next(item, current_field):
        if posting_ref['value'] or theme.SearchableDropdown.picker_active():
            return  # عملية ترحيل شغالة دلوقتي - أي blur/change ناتج عن قفل الحقول مينفعش يفتح سطر جديد أو حوار اختيار
        order = field_order(item)
        idx = order.index(current_field)
        if idx + 1 < len(order):
            page.run_task(_safe_focus, order[idx + 1])
        else:
            # آخر حقل في السطر (دائن) - انتقل مباشرة لأول حقل في سطر جديد
            if lines and lines[-1] is item:
                add_line()
                page.run_task(_safe_focus, field_order(lines[-1])[0])
            else:
                next_idx = lines.index(item) + 1
                if next_idx < len(lines):
                    page.run_task(_safe_focus, field_order(lines[next_idx])[0])
        page.update()

    def make_advance(item, field_ref):
        def handler(e):
            focus_next(item, field_ref())
            update_totals()
        return handler

    CELL_BORDER = ft.InputBorder.NONE
    CELL_PADDING = ft.Padding(left=6, right=6, top=4, bottom=4)
    FIELD_PADDING = ft.Padding(left=10, right=10, top=8, bottom=8)

    def has_extra(item):
        db_, dc_ = str(services.default_branch_id() or ''), str(services.default_cost_center_id() or '')
        return bool(item['partner'].value or item['employee'].value or (item['branch'].value or '') != db_ or (item['center'].value or '') != dc_)

    def refresh_more(item):
        on = has_extra(item)
        item['more'].icon_color = theme.PRIMARY if on else theme.TEXT_MUTED
        item['more'].icon = ft.Icons.EDIT_NOTE if on else ft.Icons.TUNE

    def open_details(item):
        def op(e):
            wd = max(260, theme._page_w() - 96) if theme._page_w() else 400
            ctls = [item['partner'], item['employee'].control, item['branch'], item['center']]
            for c in list(ctls):
                c._erp_nocap = True
                c.width = wd
            dlg = ft.AlertDialog(modal=True, title=ft.Text(f"تفاصيل السطر {item['num'].value}"))

            def done(ev):
                dlg.open = False
                refresh_more(item)
                update_totals()
            if MOBILE:
                item['description'].width = wd; item['description']._erp_nocap = True
                item['description'].border = ft.InputBorder.OUTLINE
                ctls.insert(0, item['description'])

            def do_dup(ev):
                done(ev); dup_line(item)(ev)

            def do_del(ev):
                done(ev); remove_line(item)(ev)
            mob_top = [item['description'], ft.Row([ft.OutlinedButton('نسخ السطر', icon=ft.Icons.CONTENT_COPY, on_click=do_dup),
                                                    ft.OutlinedButton('حذف السطر', icon=ft.Icons.DELETE_OUTLINE, on_click=do_del)], wrap=True, spacing=8)] if MOBILE else []
            dlg.content = ft.Column(mob_top + [ft.Text('اختياري: ربط السطر بعميل/مورد أو موظف، أو فرع/مركز تكلفة مختلف.', size=12, color=theme.TEXT_MUTED),
                                     ft.Text('العميل / المورد', size=12), item['partner'], ft.Text('الموظف', size=12), item['employee'].control,
                                     ft.Text('الفرع', size=12), item['branch'], ft.Text('مركز التكلفة', size=12), item['center']],
                                    spacing=6, tight=True, width=wd)
            dlg.actions = [ft.FilledButton('تم', on_click=done)]
            page.overlay.append(dlg); dlg.open = True; page.update()
        return op

    def dup_line(item):
        def dup(e):
            add_line()
            n = lines[-1]
            n['account'].value = item['account'].value
            n['description'].value = item['description'].value
            n['partner'].value = item['partner'].value; n['employee'].value = item['employee'].value
            n['branch'].value = item['branch'].value; n['center'].value = item['center'].value
            d, c = item['debit'].value, item['credit'].value
            n['debit'].value, n['credit'].value = c, d          # بالعكس: السطر المنسوخ غالبًا هو الطرف المقابل
            repaint_rows(); update_totals()
            page.run_task(_safe_focus, n['account'])
        return dup

    def on_amount(item, side):
        """مدين/دائن بيستبعدوا بعض: كتابة رقم في واحد بتصفّر التاني."""
        def h(e):
            try:
                v = float(item[side].value or 0)
            except ValueError:
                v = 0
            if v:
                other = 'credit' if side == 'debit' else 'debit'
                if not _num0(item[other].value):
                    item[other].value = '0'
            update_totals()
        return h

    def add_line(e=None):
        _w_acc = (theme._page_w() - 96) if MOBILE else W_ACC
        account = theme.SearchableDropdown(label='', width=_w_acc, options=sd_opt_accounts(), hint_text='ابحث بالكود أو الاسم',
                                           suggestions_height=220, page=page)
        account.text_field.dense = True; account.text_field.content_padding = FIELD_PADDING; account.text_field.text_size = 14
        line_desc = ft.TextField(width=(_w_acc if MOBILE else W_DESC), dense=True, content_padding=FIELD_PADDING, text_size=14, hint_text='بيان السطر')
        partner = ft.Dropdown(width=190, options=opt_partners(), value='', border=CELL_BORDER, content_padding=CELL_PADDING, hint_text='الطرف')
        employee = theme.SearchableDropdown(label='الموظف', width=190, options=opt_employees(), value='', flat=True,
                                            hint_text='ابحث بالكود أو الاسم', suggestions_height=200, page=page)
        _w_amt = 100 if MOBILE else W_AMT
        debit = ft.TextField(width=_w_amt, value='0', dense=True, keyboard_type=ft.KeyboardType.NUMBER, content_padding=FIELD_PADDING, text_size=14, text_align=ft.TextAlign.CENTER, label='مدين' if MOBILE else None)
        credit = ft.TextField(width=_w_amt, value='0', dense=True, keyboard_type=ft.KeyboardType.NUMBER, content_padding=FIELD_PADDING, text_size=14, text_align=ft.TextAlign.CENTER, label='دائن' if MOBILE else None)
        branch = ft.Dropdown(width=150, options=opt_branches(), value=str(services.default_branch_id() or ''), border=CELL_BORDER, content_padding=CELL_PADDING, hint_text='الفرع')
        center = ft.Dropdown(width=170, options=opt_centers(), value=str(services.default_cost_center_id() or ''), border=CELL_BORDER, content_padding=CELL_PADDING, hint_text='مركز التكلفة')
        num = ft.Text(str(len(lines) + 1), size=12, color=theme.TEXT_MUTED, weight=ft.FontWeight.BOLD)
        item = {'account': account, 'description': line_desc, 'partner': partner, 'employee': employee, 'debit': debit, 'credit': credit, 'branch': branch, 'center': center, 'num': num}

        remove_btn = ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip='حذف السطر', on_click=None, icon_size=18, icon_color=theme.DANGER)
        dup_btn = ft.IconButton(icon=ft.Icons.CONTENT_COPY, tooltip='نسخ السطر (بالمبلغ في الجانب المقابل)', on_click=None, icon_size=18)
        more_btn = ft.IconButton(icon=ft.Icons.TUNE, tooltip='تفاصيل السطر: عميل/مورد، موظف، فرع، مركز تكلفة', icon_size=18, icon_color=theme.TEXT_MUTED)
        item['remove'] = remove_btn; item['dup'] = dup_btn; item['more'] = more_btn
        more_btn.on_click = open_details(item)
        _bg = ROW_COLOR_1 if len(lines) % 2 == 0 else ROW_COLOR_2
        if MOBILE:        # موبايل: كل سطر كارت صغير (الحساب فوق، والمدين/الدائن/التفاصيل تحته)
            body = ft.Column([ft.Row([ft.Container(num, width=W_NUM), account.control], spacing=GAP, vertical_alignment=ft.CrossAxisAlignment.START),
                              ft.Row([debit, credit, more_btn], spacing=GAP)], spacing=6)
        else:
            body = ft.Row([ft.Container(num, width=W_NUM, padding=ft.Padding(left=0, right=0, top=10, bottom=0)), account.control, line_desc, debit, credit,
                           ft.Row([more_btn, dup_btn, remove_btn], spacing=0, tight=True, width=W_ACT)], spacing=GAP, vertical_alignment=ft.CrossAxisAlignment.START)
        row = ft.Container(content=body, bgcolor=_bg, border_radius=10, padding=ft.Padding(left=8, right=8, top=6, bottom=6))
        item['row'] = row
        remove_btn.on_click = remove_line(item)
        dup_btn.on_click = dup_line(item)

        lines.append(item)
        lines_table.controls.append(row)

        # الانتقال بالـ Enter/Tab: حساب -> بيان -> طرف -> مدين -> دائن -> سطر جديد مباشرة
        account.on_change = make_advance(item, lambda: account)
        line_desc.on_submit = make_advance(item, lambda: line_desc)
        line_desc.on_blur = make_advance(item, lambda: line_desc)
        partner.on_change = lambda e: autosave_draft()
        employee.on_change = lambda e: autosave_draft()
        debit.on_submit = make_advance(item, lambda: debit)
        debit.on_blur = lambda e: update_totals()
        credit.on_submit = make_advance(item, lambda: credit)
        credit.on_blur = make_advance(item, lambda: credit)
        branch.on_change = lambda e: update_totals()
        center.on_change = lambda e: update_totals()
        debit.on_change = on_amount(item, 'debit')
        credit.on_change = on_amount(item, 'credit')

        page.update()

    def clear_form():
        lines.clear()
        lines_table.controls.clear()
        add_line()
        add_line()
        ref.value = ''
        desc.value = ''
        date_field.value = today
        err.visible = False
        update_totals()

    def set_form_locked(locked: bool):
        """بعد الترحيل، نقفل كل الحقول عشان القيد يفضل ظاهر للمراجعة
        والطباعة، لحد ما المستخدم يدوس 'قيد جديد' أو 'تعديل القيد' صراحةً.
        بنشيل كل معالجات الأحداث كمان (مش الـ disabled بس) كحماية إضافية
        من أي سطر يتضاف بالغلط بعد القفل."""
        date_field.control.disabled = locked
        for f in (ref, desc, header_branch, header_center):
            f.disabled = locked
        for item in lines:
            for key in ('account', 'description', 'partner', 'employee', 'debit', 'credit', 'branch', 'center'):
                # لازم نشيل المعالجات الأول قبل التعطيل: لو سيّبنا التعطيل
                # يحصل الأول وفيه حقل متركّز عليه وقتها، تعطيله ممكن يفعّل
                # on_blur بتاعه (لإن التركيز بيتشال منه تلقائيًا) - ولو
                # المعالج القديم (الانتقال للحقل اللي بعده) لسه موجود،
                # هيضيف سطر جديد ويفتح حوار اختيار الحساب بتاعه بالغلط.
                if locked:
                    item[key].on_change = None
                    if hasattr(item[key], 'on_submit'):
                        item[key].on_submit = None
                    if hasattr(item[key], 'on_blur'):
                        item[key].on_blur = None
                item[key].disabled = locked
            item['remove'].disabled = locked; item['dup'].disabled = locked; item['more'].disabled = False
        locked_state['on'] = locked
        add_line_btn.visible = not locked
        balance_btn.visible = False
        post_btn.visible = not locked
        new_entry_btn.visible = locked
        print_btn.visible = locked
        edit_btn.visible = locked
        reverse_btn.visible = locked
        attach_btn.visible = locked
        tools_row.visible = not locked
        page.update()

    def new_entry(e=None):
        posting_ref['value'] = False
        draft_state['on'] = False
        drafts.clear(DRAFT_KIND)
        draft_banner.visible = False
        clear_form()
        draft_state['on'] = True
        last_entry_id['value'] = None
        edit_mode['value'] = False
        post_btn.text = 'ترحيل القيد'
        set_form_locked(False)

    def populate_lines_from_entry(entry):
        lines.clear()
        lines_table.controls.clear()
        for ln in entry.lines:
            add_line()
            item = lines[-1]
            item['account'].value = str(ln.account_id) if ln.account_id else None
            item['description'].value = ln.description or ''
            if ln.partner_type == 'employee' and ln.partner_id:
                item['partner'].value = ''; item['employee'].value = str(ln.partner_id)
            else:
                item['partner'].value = f'{ln.partner_type}:{ln.partner_id}' if ln.partner_type and ln.partner_id else ''
                item['employee'].value = ''
            item['debit'].value = f'{ln.debit:g}' if ln.debit else '0'
            item['credit'].value = f'{ln.credit:g}' if ln.credit else '0'
            item['branch'].value = str(ln.branch_id) if ln.branch_id else ''
            item['center'].value = str(ln.cost_center_id) if ln.cost_center_id else ''
        while len(lines) < 2:
            add_line()
        repaint_rows()
        update_totals()

    def start_edit(e=None):
        if not last_entry_id['value']:
            return
        posting_ref['value'] = False
        try:
            services.set_journal_entry_draft(last_entry_id['value'])
            entry = services.get_journal_entry(last_entry_id['value'])
            if not entry:
                raise ValueError('تعذر العثور على القيد')
            date_field.value = entry.date.strftime('%Y-%m-%d')
            ref.value = entry.reference or ''
            desc.value = entry.description or ''
            header_branch.value = str(entry.branch_id) if entry.branch_id else ''
            populate_lines_from_entry(entry)
            edit_mode['value'] = True
            post_btn.text = 'حفظ التعديلات وإعادة الترحيل'
            err.visible = False
            set_form_locked(False)
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر فتح القيد للتعديل: {ex}'), open=True)); page.update()

    def collect_lines():
        """سطور النموذج الحالي كقواميس (للقوالب) - بتتجاهل السطر اللي مالوش حساب."""
        out = []
        for x in lines:
            if not x['account'].value:
                continue
            ptype, pid = split_partner(x)
            out.append({'account_id': int(x['account'].value), 'description': x['description'].value or '',
                        'debit': float(x['debit'].value or 0), 'credit': float(x['credit'].value or 0),
                        'branch_id': int(x['branch'].value) if x['branch'].value else None,
                        'cost_center_id': int(x['center'].value) if x['center'].value else None,
                        'partner_type': ptype, 'partner_id': pid})
        return out

    def apply_lines(new_lines, replace=True, description=None, reference=None):
        """يحمّل سطور (من قالب/لصق/مساعد ذكي) في النموذج؛ السطر اللي حسابه مش معروف بيتحمّل فاضي عشان تختاره."""
        draft_state['on'] = False
        try:
            if replace:
                lines.clear(); lines_table.controls.clear()
            else:
                for x in [x for x in lines if not x['account'].value and _num0(x['debit'].value) and _num0(x['credit'].value)]:
                    lines.remove(x); lines_table.controls.remove(x['row'])
            for ln in new_lines:
                add_line()
                it = lines[-1]
                it['account'].value = str(ln['account_id']) if ln.get('account_id') else None
                it['description'].value = ln.get('description') or ''
                if ln.get('partner_type') == 'employee' and ln.get('partner_id'):
                    it['partner'].value = ''; it['employee'].value = str(ln['partner_id'])
                elif ln.get('partner_type') and ln.get('partner_id'):
                    it['partner'].value = f"{ln['partner_type']}:{ln['partner_id']}"; it['employee'].value = ''
                it['debit'].value = f"{ln['debit']:g}" if ln.get('debit') else '0'
                it['credit'].value = f"{ln['credit']:g}" if ln.get('credit') else '0'
                if ln.get('branch_id'):
                    it['branch'].value = str(ln['branch_id'])
                if ln.get('cost_center_id'):
                    it['center'].value = str(ln['cost_center_id'])
            while len(lines) < 2:
                add_line()
            if description:
                desc.value = description
            if reference:
                ref.value = reference
            err.visible = False
            repaint_rows()
        finally:
            draft_state['on'] = True
        update_totals()

        async def _relayout():
            await asyncio.sleep(0.25)       # الجدول بيتقصّ لو اتحدّث مرة واحدة بعد ما صفوفه اتبدّلت دفعة واحدة
            lines_table.update()
            page.update()
        page.run_task(_relayout)

    def show_entry(entry_id):
        """يعرض قيد مرحّل (زي القيد العكسي اللي لسه اتعمل) مقفول للمراجعة."""
        entry = services.get_journal_entry(entry_id)
        date_field.value = entry.date.strftime('%Y-%m-%d')
        ref.value = entry.reference or ''
        desc.value = entry.description or ''
        header_branch.value = str(entry.branch_id) if entry.branch_id else ''
        populate_lines_from_entry(entry)
        last_entry_id['value'] = entry_id
        edit_mode['value'] = False
        draft_state['on'] = False
        set_form_locked(True)

    journal_ctx = {'accounts': accounts, 'collect_lines': collect_lines, 'apply_lines': apply_lines,
                   'get_header': lambda: {'description': desc.value or '', 'reference': ref.value or ''},
                   'on_reversed': show_entry}

    def open_reverse(e):
        if last_entry_id['value']:
            journal_dialogs.reverse_dialog(page, journal_ctx, last_entry_id['value'])

    def open_attachments(e):
        if last_entry_id['value']:
            journal_dialogs.attachments_dialog(page, journal_ctx, last_entry_id['value'])

    def do_print_entry(e):
        if not last_entry_id['value']:
            page.overlay.append(ft.SnackBar(ft.Text('مفيش قيد مرحّل للطباعة دلوقتي.'), open=True)); page.update()
            return
        try:
            path = services.generate_journal_entry_pdf_file(last_entry_id['value'])
            theme.open_or_download_file(page, path)
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذرت الطباعة: {ex}'), open=True)); page.update()

    def save(e):
        posting_ref['value'] = True
        try:
            entry_date = parse_date(date_field.value)
            data = []
            for x in lines:
                if not x['account'].value:
                    continue
                ptype, pid = split_partner(x)
                data.append({
                    'account_id': int(x['account'].value),
                    'description': x['description'].value or desc.value or '',
                    'debit': float(x['debit'].value or 0),
                    'credit': float(x['credit'].value or 0),
                    'branch_id': int(x['branch'].value) if x['branch'].value else (int(header_branch.value) if header_branch.value else None),
                    'cost_center_id': int(x['center'].value) if x['center'].value else (int(header_center.value) if header_center.value else None),
                    'partner_type': ptype,
                    'partner_id': pid,
                })
            if len(data) < 2:
                raise ValueError('يجب إدخال سطرين محاسبيين على الأقل (باختيار الحساب)')

            if edit_mode['value'] and last_entry_id['value']:
                services.update_journal_entry(
                    last_entry_id['value'], data,
                    reference=ref.value, description=desc.value, entry_date=entry_date,
                    branch_id=int(header_branch.value) if header_branch.value else None,
                    cost_center_id=int(header_center.value) if header_center.value else None,
                )
                services.post_journal_entry_by_id(last_entry_id['value'])
                jid = last_entry_id['value']
                success_msg = f'تم حفظ التعديلات وإعادة ترحيل القيد بنجاح — رقم القيد: {jid}'
            else:
                jid = services.create_journal_entry(
                    data,
                    reference=ref.value,
                    description=desc.value,
                    source_type='manual',
                    entry_date=entry_date,
                    branch_id=int(header_branch.value) if header_branch.value else None,
                    cost_center_id=int(header_center.value) if header_center.value else None,
                )
                success_msg = f'تم ترحيل القيد بنجاح — رقم القيد: {jid}'

            drafts.clear(DRAFT_KIND)
            draft_state['on'] = False          # بعد الترحيل مفيش مسودة لحد ما يتفتح "قيد جديد"
            last_entry_id['value'] = jid
            edit_mode['value'] = False
            post_btn.text = 'ترحيل القيد'
            err.visible = False
            # امسح أي سطر فاضي (مالوش حساب مختار) فضل من الإدخال قبل الترحيل
            # - زي السطر اللي بيتضاف تلقائيًا لما تدوس إنتر في آخر خانة دائن
            # - عشان بعد الترحيل يفضل ظاهر بس السطور اللي اترحّلت فعليًا.
            empty_items = [x for x in lines if not x['account'].value]
            for x in empty_items:
                if x in lines:
                    lines.remove(x)
                if x['row'] in lines_table.controls:
                    lines_table.controls.remove(x['row'])
            page.overlay.append(ft.SnackBar(ft.Text(success_msg), open=True))
            set_form_locked(True)
        except Exception as ex:
            posting_ref['value'] = False
            err.value = str(ex)
            err.visible = True
            page.update()

    def do_export(kind):
        if not last_entry_id['value']:
            page.overlay.append(ft.SnackBar(ft.Text('رحّل قيد أولاً قبل الطباعة أو التصدير.'), open=True)); page.update()
            return
        try:
            entries = [j for j in services.list_journal_entries(limit=500) if j.id == last_entry_id['value']]
            if not entries:
                raise ValueError('تعذر العثور على القيد.')
            j = entries[0]
            rows = [{
                'number': j.number, 'date': j.date.strftime('%Y-%m-%d'), 'source': 'قيد يدوي',
                'account': f'{ln.account.code} - {ln.account.name}' if ln.account else '-',
                'description': ln.description or j.description or '-',
                'branch': '-', 'cost_center': '-', 'debit': ln.debit, 'credit': ln.credit,
            } for ln in (j.lines or [])]
            exports_dir = services.downloads_dir()
            path = (export_excel if kind == 'xlsx' else export_pdf)({'rows': rows}, 'general_journal', exports_dir)
            theme.open_or_download_file(page, path)
            page.overlay.append(ft.SnackBar(ft.Text(f'تم إنشاء الملف: {path}'), open=True)); page.update()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

    balance_btn.on_click = auto_balance
    add_line()
    add_line()
    for _f in (ref, desc, header_branch, header_center):
        _f.on_change = autosave_draft
    _saved = drafts.load(DRAFT_KIND)
    if _saved:
        apply_draft(*_saved)

    form_header = ft.Row([date_field.control, ref, desc, header_branch, header_center], wrap=True, spacing=10)

    add_line_btn = ft.OutlinedButton('إضافة سطر يدوياً', icon=ft.Icons.ADD, on_click=add_line)
    post_btn = theme.guard_submit(ft.FilledButton('ترحيل القيد', icon=ft.Icons.CHECK_CIRCLE, bgcolor=theme.PRIMARY, on_click=save))
    new_entry_btn = ft.FilledButton('قيد جديد', icon=ft.Icons.ADD_CIRCLE_OUTLINE, bgcolor=theme.PRIMARY, on_click=new_entry, visible=False)
    edit_btn = ft.OutlinedButton('تعديل القيد', icon=ft.Icons.EDIT_OUTLINED, on_click=start_edit, visible=False)
    print_btn = ft.ElevatedButton('طباعة القيد', icon=ft.Icons.PRINT_OUTLINED, on_click=do_print_entry, visible=False)
    reverse_btn = ft.OutlinedButton('قيد عكسي', icon=ft.Icons.UNDO, on_click=open_reverse, visible=False, tooltip='يعمل قيد معكوس (مدين↔دائن) ويربطه بالقيد ده')
    attach_btn = ft.OutlinedButton('مرفقات', icon=ft.Icons.ATTACH_FILE, on_click=open_attachments, visible=False)
    tools_row = ft.Row([
        ft.OutlinedButton('قوالب ومتكررة', icon=ft.Icons.DYNAMIC_FORM, on_click=lambda e: journal_dialogs.templates_dialog(page, journal_ctx)),
        ft.OutlinedButton('لصق من Excel', icon=ft.Icons.CONTENT_PASTE, on_click=lambda e: journal_dialogs.paste_dialog(page, journal_ctx)),
        ft.FilledTonalButton('مساعد ذكي', icon=ft.Icons.AUTO_AWESOME, on_click=lambda e: journal_dialogs.ai_dialog(page, journal_ctx)),
    ], wrap=True, spacing=8)

    entry_card = theme.card(ft.Column([
        ft.Text('إدخال قيد يومي متعدد السطور', size=18, weight=ft.FontWeight.BOLD),
        ft.Text('اكتب بيانات القيد، ثم سطور الحسابات. Enter/Tab بينقلك للحقل التالي وبيضيف سطر جديد تلقائيًا، والمدين والدائن بيستبعدوا بعض. '
                'لو القيد مش متوازن اضغط "وازن تلقائيًا". بعد الترحيل القيد بيفضل ظاهر للمراجعة والطباعة.', color=theme.TEXT_MUTED, size=13),
        draft_banner,
        tools_row,
        ft.Divider(),
        form_header,
        ft.Divider(),
        table_host,
        ft.Row([add_line_btn, balance_btn], wrap=True, spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Row([ft.Row([post_btn, new_entry_btn, edit_btn, print_btn, reverse_btn, attach_btn], wrap=True, spacing=8),
                ft.Row([_tot_box('إجمالي المدين', tot_debit), _tot_box('إجمالي الدائن', tot_credit), _tot_box('الفرق', tot_diff), bal_chip], spacing=8, wrap=True)],
               wrap=True, spacing=12, run_spacing=10, alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ft.Row([
            ft.ElevatedButton('طباعة PDF لآخر قيد', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: do_export('pdf')),
            ft.ElevatedButton('تحميل Excel لآخر قيد', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: do_export('xlsx')),
        ], wrap=True),
        err,
    ], spacing=10))

    return ft.Column([
        theme.page_title('القيود اليومية', 'إدخال القيود اليدوية متعددة السطور وترحيلها'),
        entry_card,
    ], expand=True, scroll=ft.ScrollMode.AUTO)
