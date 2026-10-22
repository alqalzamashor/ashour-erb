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
    totals = ft.Text('الإجمالي: مدين 0.00 | دائن 0.00 | الفرق 0.00', weight=ft.FontWeight.BOLD)
    last_entry_id = {'value': None}
    edit_mode = {'value': False}

    ROW_COLOR_1 = theme.ROW_BG[0]
    ROW_COLOR_2 = theme.ROW_BG[1]

    lines_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text('الحساب')),
            ft.DataColumn(ft.Text('بيان السطر')),
            ft.DataColumn(ft.Text('العميل / المورد')),
            ft.DataColumn(ft.Text('الموظف')),
            ft.DataColumn(ft.Text('مدين')),
            ft.DataColumn(ft.Text('دائن')),
            ft.DataColumn(ft.Text('الفرع')),
            ft.DataColumn(ft.Text('مركز التكلفة')),
            ft.DataColumn(ft.Text('')),
        ],
        rows=[],
        border=ft.Border(
            top=ft.BorderSide(1, theme.BORDER_LIGHT), right=ft.BorderSide(1, theme.BORDER_LIGHT),
            bottom=ft.BorderSide(1, theme.BORDER_LIGHT), left=ft.BorderSide(1, theme.BORDER_LIGHT),
        ),
        horizontal_lines=ft.BorderSide(1, theme.BORDER_LIGHT),
        vertical_lines=ft.BorderSide(1, theme.BORDER_LIGHT),
        column_spacing=6,
        heading_row_height=36,
        data_row_min_height=42,
        data_row_max_height=42,
        heading_row_color=theme.SURFACE_ALT,
    )
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
        totals.value = f'الإجمالي: مدين {debit:,.2f} | دائن {credit:,.2f} | الفرق {debit-credit:,.2f}'
        autosave_draft()
        page.update()

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
            lines.clear(); lines_table.rows.clear()
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
            item['row'].color = ROW_COLOR_1 if i % 2 == 0 else ROW_COLOR_2

    def remove_line(item):
        def remove(e):
            if item in lines:
                lines.remove(item)
            if item['row'] in lines_table.rows:
                lines_table.rows.remove(item['row'])
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
        return [item['account'], item['description'], item['partner'], item['debit'], item['credit']]

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

    def add_line(e=None):
        account = theme.SearchableDropdown(label='الحساب', width=230, options=sd_opt_accounts(), flat=True,
                                           hint_text='ابحث بالكود أو الاسم', suggestions_height=200, page=page)
        line_desc = ft.TextField(width=190, border=CELL_BORDER, content_padding=CELL_PADDING, hint_text='بيان السطر')
        partner = ft.Dropdown(width=190, options=opt_partners(), value='', border=CELL_BORDER, content_padding=CELL_PADDING, hint_text='الطرف')
        employee = theme.SearchableDropdown(label='الموظف', width=190, options=opt_employees(), value='', flat=True,
                                            hint_text='ابحث بالكود أو الاسم', suggestions_height=200, page=page)
        debit = ft.TextField(width=100, value='0', keyboard_type=ft.KeyboardType.NUMBER, border=CELL_BORDER, content_padding=CELL_PADDING, text_align=ft.TextAlign.CENTER)
        credit = ft.TextField(width=100, value='0', keyboard_type=ft.KeyboardType.NUMBER, border=CELL_BORDER, content_padding=CELL_PADDING, text_align=ft.TextAlign.CENTER)
        branch = ft.Dropdown(width=150, options=opt_branches(), value=str(services.default_branch_id() or ''), border=CELL_BORDER, content_padding=CELL_PADDING, hint_text='الفرع')
        center = ft.Dropdown(width=170, options=opt_centers(), value=str(services.default_cost_center_id() or ''), border=CELL_BORDER, content_padding=CELL_PADDING, hint_text='مركز التكلفة')
        item = {'account': account, 'description': line_desc, 'partner': partner, 'employee': employee, 'debit': debit, 'credit': credit, 'branch': branch, 'center': center}

        remove_btn = ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip='حذف السطر', on_click=None, icon_size=18)

        row = ft.DataRow(
            color=ROW_COLOR_1 if len(lines) % 2 == 0 else ROW_COLOR_2,
            cells=[
                ft.DataCell(account.control),
                ft.DataCell(line_desc),
                ft.DataCell(partner),
                ft.DataCell(employee.control),
                ft.DataCell(debit),
                ft.DataCell(credit),
                ft.DataCell(branch),
                ft.DataCell(center),
                ft.DataCell(remove_btn),
            ],
        )
        item['row'] = row
        remove_btn.on_click = remove_line(item)

        lines.append(item)
        lines_table.rows.append(row)

        # الانتقال بالـ Enter/Tab: حساب -> بيان -> طرف -> مدين -> دائن -> سطر جديد مباشرة
        account.on_change = make_advance(item, lambda: account)
        line_desc.on_submit = make_advance(item, lambda: line_desc)
        line_desc.on_blur = make_advance(item, lambda: line_desc)
        partner.on_change = make_advance(item, lambda: partner)
        employee.on_change = lambda e: autosave_draft()
        debit.on_submit = make_advance(item, lambda: debit)
        debit.on_blur = lambda e: update_totals()
        credit.on_submit = make_advance(item, lambda: credit)
        credit.on_blur = make_advance(item, lambda: credit)
        branch.on_change = lambda e: update_totals()
        center.on_change = lambda e: update_totals()
        debit.on_change = update_totals
        credit.on_change = update_totals

        page.update()

    def clear_form():
        lines.clear()
        lines_table.rows.clear()
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
            item['row'].cells[7].content.disabled = locked
        add_line_btn.visible = not locked
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
        lines_table.rows.clear()
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
                lines.clear(); lines_table.rows.clear()
            else:
                for x in [x for x in lines if not x['account'].value and _num0(x['debit'].value) and _num0(x['credit'].value)]:
                    lines.remove(x); lines_table.rows.remove(x['row'])
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
                if x['row'] in lines_table.rows:
                    lines_table.rows.remove(x['row'])
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
        ft.Text(
            'بيانات القيد أولاً، ثم سطور الحسابات في الجدول تحت (سطرين ظاهرين تلقائيًا من البداية - مدين ودائن). اضغط Enter أو Tab للانتقال '
            'من حقل للي بعده تلقائياً بنفس الترتيب، وهيتضاف سطر جديد فاضي تلقائياً بعد آخر حقل لو احتجت أكتر من سطرين. '
            'بعد الترحيل، القيد بيفضل ظاهر للمراجعة والطباعة - اضغط "قيد جديد" عشان تبدأ قيد تاني، أو "تعديل القيد" لو عايز تصحّح حاجة فيه.',
            color=theme.TEXT_MUTED,
        ),
        draft_banner,
        tools_row,
        ft.Divider(),
        form_header,
        ft.Divider(),
        theme.h_scroll(lines_table),
        ft.Row([add_line_btn, post_btn, new_entry_btn, edit_btn, print_btn, reverse_btn, attach_btn, totals], wrap=True),
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
