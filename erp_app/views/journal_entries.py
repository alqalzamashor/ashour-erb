import datetime, os
import flet as ft
from .. import services, theme
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
        opts += [ft.dropdown.Option(f'employee:{emp.id}', f'موظف - {emp.name}') for emp in employees]
        return opts

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

    ROW_COLOR_1 = "#FFFFFF"
    ROW_COLOR_2 = "#F3F1FA"

    lines_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text('الحساب')),
            ft.DataColumn(ft.Text('بيان السطر')),
            ft.DataColumn(ft.Text('العميل / المورد')),
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
        page.update()

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
        if posting_ref['value']:
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
        debit = ft.TextField(width=100, value='0', keyboard_type=ft.KeyboardType.NUMBER, border=CELL_BORDER, content_padding=CELL_PADDING, text_align=ft.TextAlign.CENTER)
        credit = ft.TextField(width=100, value='0', keyboard_type=ft.KeyboardType.NUMBER, border=CELL_BORDER, content_padding=CELL_PADDING, text_align=ft.TextAlign.CENTER)
        branch = ft.Dropdown(width=150, options=opt_branches(), value=str(services.default_branch_id() or ''), border=CELL_BORDER, content_padding=CELL_PADDING, hint_text='الفرع')
        center = ft.Dropdown(width=170, options=opt_centers(), value=str(services.default_cost_center_id() or ''), border=CELL_BORDER, content_padding=CELL_PADDING, hint_text='مركز التكلفة')
        item = {'account': account, 'description': line_desc, 'partner': partner, 'debit': debit, 'credit': credit, 'branch': branch, 'center': center}

        remove_btn = ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip='حذف السطر', on_click=None, icon_size=18)

        row = ft.DataRow(
            color=ROW_COLOR_1 if len(lines) % 2 == 0 else ROW_COLOR_2,
            cells=[
                ft.DataCell(account.control),
                ft.DataCell(line_desc),
                ft.DataCell(partner),
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
            for key in ('account', 'description', 'partner', 'debit', 'credit', 'branch', 'center'):
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
        page.update()

    def new_entry(e=None):
        posting_ref['value'] = False
        clear_form()
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
            item['partner'].value = f'{ln.partner_type}:{ln.partner_id}' if ln.partner_type and ln.partner_id else ''
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
                ptype = pid = None
                if x['partner'].value:
                    ptype, pid_s = x['partner'].value.split(':')
                    pid = int(pid_s)
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

    form_header = ft.Row([date_field.control, ref, desc, header_branch, header_center], wrap=True, spacing=10)

    add_line_btn = ft.OutlinedButton('إضافة سطر يدوياً', icon=ft.Icons.ADD, on_click=add_line)
    post_btn = theme.guard_submit(ft.FilledButton('ترحيل القيد', icon=ft.Icons.CHECK_CIRCLE, bgcolor=theme.PRIMARY, on_click=save))
    new_entry_btn = ft.FilledButton('قيد جديد', icon=ft.Icons.ADD_CIRCLE_OUTLINE, bgcolor=theme.PRIMARY, on_click=new_entry, visible=False)
    edit_btn = ft.OutlinedButton('تعديل القيد', icon=ft.Icons.EDIT_OUTLINED, on_click=start_edit, visible=False)
    print_btn = ft.ElevatedButton('طباعة القيد', icon=ft.Icons.PRINT_OUTLINED, on_click=do_print_entry, visible=False)

    entry_card = theme.card(ft.Column([
        ft.Text('إدخال قيد يومي متعدد السطور', size=18, weight=ft.FontWeight.BOLD),
        ft.Text(
            'بيانات القيد أولاً، ثم سطور الحسابات في الجدول تحت (سطرين ظاهرين تلقائيًا من البداية - مدين ودائن). اضغط Enter أو Tab للانتقال '
            'من حقل للي بعده تلقائياً بنفس الترتيب، وهيتضاف سطر جديد فاضي تلقائياً بعد آخر حقل لو احتجت أكتر من سطرين. '
            'بعد الترحيل، القيد بيفضل ظاهر للمراجعة والطباعة - اضغط "قيد جديد" عشان تبدأ قيد تاني، أو "تعديل القيد" لو عايز تصحّح حاجة فيه.',
            color=theme.TEXT_MUTED,
        ),
        ft.Divider(),
        form_header,
        ft.Divider(),
        theme.h_scroll(lines_table),
        ft.Row([add_line_btn, post_btn, new_entry_btn, edit_btn, print_btn, totals], wrap=True),
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
