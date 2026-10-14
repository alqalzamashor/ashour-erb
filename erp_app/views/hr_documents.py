import datetime
import os
import flet as ft
from .. import services, theme
from ..document_notifier import days_text, status_color

STATUS_COLORS = {'expired': theme.DANGER, 'expiring': theme.WARNING, 'valid': theme.SUCCESS, 'archived': theme.TEXT_MUTED}


def build_hr_documents(page: ft.Page):
    """تجديد الرخص والمستندات: إقامات، جوازات، رخص، عقود إيجار، تأمينات، أي مستند بتاريخ انتهاء.
    متابعة المتبقي، تنبيه على مراحل قبل الانتهاء (من الجرس في الشريط العلوي)، وسجل تجديدات. من غير أي أثر محاسبي."""
    today = datetime.date.today()
    employees = services.list_employees()
    cards = ft.Row(wrap=True, spacing=12)

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def close(d):
        d.open = False; page.update()

    def _d(v):
        v = (v or '').strip()
        return datetime.datetime.strptime(v, '%Y-%m-%d') if v else None

    # ===================================================================== فلاتر
    types = services.list_document_types()
    type_f = ft.Dropdown(label='النوع', width=220, value='', options=[ft.dropdown.Option('', 'كل الأنواع')] + [ft.dropdown.Option(str(t.id), t.name) for t in types])
    status_f = ft.Dropdown(label='الحالة', width=200, value='', options=[ft.dropdown.Option('', 'الكل (من غير المؤرشف)'), ft.dropdown.Option('attention', 'محتاج انتباه (منتهي + قارب)'),
                                                                         ft.dropdown.Option('expired', 'منتهي'), ft.dropdown.Option('expiring', 'قارب على الانتهاء'),
                                                                         ft.dropdown.Option('valid', 'ساري'), ft.dropdown.Option('archived', 'مؤرشف')])
    emp_f = ft.Dropdown(label='الموظف', width=210, value='', options=[ft.dropdown.Option('', 'كل الموظفين')] + [ft.dropdown.Option(str(e.id), e.name) for e in employees])
    search_f = ft.TextField(label='بحث (اسم / رقم / جهة)', width=240, prefix_icon=ft.Icons.SEARCH)

    def open_attachment(doc_id, renewal_id=None):
        try:
            theme.open_or_download_file(page, services.document_attachment_path(doc_id, renewal_id))
        except Exception as ex:
            snack(str(ex))

    def row_builder(r):
        st = r['status']
        color = STATUS_COLORS[st]
        left_txt = days_text(r['days_left']) if st != 'archived' else 'مؤرشف'
        acts = []
        if st != 'archived':
            acts.append(ft.TextButton('تجديد', icon=ft.Icons.AUTORENEW, on_click=lambda e, x=r: open_renew(x['id']), style=ft.ButtonStyle(color=theme.SUCCESS, padding=ft.Padding(left=6, right=6, top=2, bottom=2))))
        acts.append(ft.IconButton(icon=ft.Icons.HISTORY, tooltip=f"سجل التجديدات ({r['renewals_count']})", on_click=lambda e, x=r: open_history(x['id'])))
        if r['has_attachment']:
            acts.append(ft.IconButton(icon=ft.Icons.ATTACH_FILE, tooltip='فتح صورة المستند', icon_color=theme.PRIMARY, on_click=lambda e, x=r: open_attachment(x['id'])))
        acts.append(ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل', on_click=lambda e, x=r: open_form(x['id'])))
        acts.append(ft.IconButton(icon=ft.Icons.UNARCHIVE_OUTLINED if r['archived'] else ft.Icons.ARCHIVE_OUTLINED, tooltip='إلغاء الأرشفة' if r['archived'] else 'أرشفة (مش محتاج تجديد)',
                                  on_click=lambda e, x=r: do(services.set_document_archived, x['id'], not x['archived'])))
        acts.append(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف', on_click=lambda e, x=r: confirm_delete(x)))
        return ft.DataRow(color=ft.Colors.with_opacity(0.07, color) if st in ('expired', 'expiring') else None, cells=[
            ft.DataCell(ft.Text(r['type_name'], size=12)),
            ft.DataCell(ft.Column([ft.Text(r['title'], weight=ft.FontWeight.BOLD), ft.Text(r['doc_number'] and f"رقم {r['doc_number']}" or '', size=10.5, color=theme.TEXT_MUTED)], spacing=0, tight=True)),
            ft.DataCell(ft.Text(r['holder'])), ft.DataCell(ft.Text(r['issuer'] or '-', size=12)),
            ft.DataCell(ft.Text(r['issue_date'].strftime('%Y-%m-%d') if r['issue_date'] else '-', size=12)),
            ft.DataCell(ft.Text(r['expiry_date'].strftime('%Y-%m-%d'), weight=ft.FontWeight.BOLD)),
            ft.DataCell(ft.Container(content=ft.Text(left_txt, size=11, color='#FFFFFF', weight=ft.FontWeight.BOLD), bgcolor=color, border_radius=10, padding=ft.Padding(left=8, right=8, top=2, bottom=2))),
            ft.DataCell(ft.Text(f"{r['cost']:,.2f}" if r['cost'] else '-', size=12)),
            ft.DataCell(ft.Row(acts, spacing=0))])

    table = theme.SortableDataTable(columns=[
        ('النوع', lambda r: r['type_name']), ('المستند', lambda r: r['title']), ('الخاص بـ', lambda r: r['holder']), ('جهة الإصدار', lambda r: r['issuer']),
        ('تاريخ الإصدار', lambda r: r['issue_date'] or datetime.datetime.min), ('تاريخ الانتهاء', lambda r: r['expiry_date']), ('المتبقي', lambda r: r['days_left'], True),
        ('آخر تكلفة', lambda r: r['cost'], True), ('الإجراءات', None)], row_builder=row_builder, page=page, expand=True)

    def query():
        return services.list_tracked_documents(status=status_f.value or None, type_id=int(type_f.value) if type_f.value else None,
                                               employee_id=int(emp_f.value) if emp_f.value else None, text=search_f.value)

    def refresh(e=None):
        rows = query()
        table.set_data(rows)
        sm = services.documents_summary()
        def card(label, value, color, sub):
            return theme.card(ft.Column([ft.Text(label, size=12, color=theme.TEXT_MUTED), ft.Text(str(value), size=24, weight=ft.FontWeight.BOLD, color=color), ft.Text(sub, size=11, color=theme.TEXT_MUTED)],
                                        spacing=0, tight=True), padding=14)
        cards.controls = [card('منتهية', sm['expired'], theme.DANGER, 'محتاجة تجديد فورًا'), card('قاربت على الانتهاء', sm['expiring'], theme.WARNING, 'وصلت مرحلة التنبيه'),
                          card('خلال 30 يوم', sm['within30'], theme.PRIMARY, 'هتنتهي قريب'), card('سارية', sm['valid'], theme.SUCCESS, f"من إجمالي {sm['total']} مستند")]
        if e is not None:
            page.update()

    def do(fn, *args, msg=None):
        try:
            fn(*args); refresh(True)
            if msg:
                snack(msg)
        except Exception as ex:
            snack(str(ex))

    def confirm_delete(r):
        dlg = ft.AlertDialog(modal=True, title=ft.Text('حذف المستند'), content=ft.Text(f'هتحذف "{r["title"]}" مع سجل تجديداته. لو المستند خلص غرضه الأفضل تأرشفه بدل الحذف.'),
                             actions=[ft.TextButton('إلغاء', on_click=lambda e: close(dlg)),
                                      ft.FilledButton('حذف', bgcolor=theme.DANGER, on_click=lambda e: (close(dlg), do(services.delete_tracked_document, r['id'], msg='تم الحذف')))])
        page.overlay.append(dlg); dlg.open = True; page.update()

    # ===================================================================== نموذج المستند
    editing = {'id': None, 'attach': None}
    f_type = theme.SearchableDropdown(label='نوع المستند *', width=300, options=[])
    f_title = ft.TextField(label='العنوان / الوصف', width=300, hint_text='يتعبّى تلقائي لو فاضي')
    f_kind = ft.RadioGroup(value='employee', content=ft.Row([ft.Radio(value='employee', label='موظف'), ft.Radio(value='company', label='الشركة'), ft.Radio(value='other', label='أخرى (سيارة / فرع / عقار)')], spacing=16))
    f_emp = theme.SearchableDropdown(label='الموظف *', width=300, options=[])
    f_holder = ft.TextField(label='اسم صاحب المستند (سيارة / فرع / عقار...)', width=300, visible=False)
    f_number = ft.TextField(label='رقم المستند', width=200)
    f_issuer = ft.TextField(label='جهة الإصدار', width=200)
    f_issue = theme.DateField('تاريخ الإصدار', page, width=160, value='')
    f_expiry = theme.DateField('تاريخ الانتهاء *', page, width=170, value='')
    f_cost = ft.TextField(label='التكلفة / الرسوم', width=140, keyboard_type=ft.KeyboardType.NUMBER)
    f_notes = ft.TextField(label='ملاحظات', width=620, multiline=True, min_lines=1, max_lines=3)
    REMIND_LABELS = {180: '6 شهور (180 يوم)', 120: '4 شهور (120 يوم)', 90: '3 شهور (90 يوم)', 60: 'شهرين (60 يوم)', 45: '45 يوم', 30: 'شهر (30 يوم)',
                     15: '15 يوم', 7: 'أسبوع (7 أيام)', 3: '3 أيام', 1: 'يوم واحد', 0: 'يوم الانتهاء'}
    remind_checks = {d: ft.Checkbox(label=REMIND_LABELS[d], value=False) for d in services.DOC_REMIND_CHOICES}
    f_err = ft.Text('', color=theme.DANGER, visible=False, size=12)
    attach_text = ft.Text('', size=12, color=theme.TEXT_MUTED)

    def apply_type_defaults(e=None):
        t = next((x for x in types if str(x.id) == (f_type.value or '')), None)
        if t and not editing['id']:
            tiers = services._parse_remind_days(t.remind_days)
            for d, cb in remind_checks.items():
                cb.value = d in tiers
            f_kind.value = t.holder_kind
            on_kind()
        page.update()

    def on_kind(e=None):
        f_emp.control.visible = f_kind.value == 'employee'
        f_holder.visible = f_kind.value != 'employee'
        f_holder.label = 'اسم صاحب المستند (مثلًا: سيارة 1234 / فرع جدة)' if f_kind.value == 'other' else 'اسم صاحب المستند (اختياري)'
        page.update()

    f_type.on_change = apply_type_defaults
    f_kind.on_change = on_kind

    async def pick_attachment(e=None):
        path = await theme.pick_file(page, 'اختر صورة/ملف المستند', ['pdf','png','jpg','jpeg'])
        if path:
            editing['attach'] = path; attach_text.value = os.path.basename(path); page.update()

    def save(e):
        try:
            kw = dict(type_id=int(f_type.value) if f_type.value else None, expiry_date=_d(f_expiry.value), title=f_title.value, holder_kind=f_kind.value,
                      employee_id=int(f_emp.value) if f_emp.value else None, holder_name=f_holder.value, doc_number=f_number.value, issuer=f_issuer.value,
                      issue_date=_d(f_issue.value), remind_days=[d for d, cb in remind_checks.items() if cb.value], cost=float((f_cost.value or '0').replace(',', '') or 0),
                      notes=f_notes.value, attachment_path=editing['attach'])
            if editing['id']:
                services.update_tracked_document(editing['id'], **kw); msg = 'تم تعديل المستند'
            else:
                services.create_tracked_document(**kw); msg = 'تم إضافة المستند للمتابعة'
            close(form_dlg); refresh(True); snack(msg)
        except ValueError as ex:
            f_err.value = str(ex); f_err.visible = True; page.update()
        except Exception as ex:
            f_err.value = f'خطأ: {ex}'; f_err.visible = True; page.update()

    rem_box = ft.Column([ft.Text('التنبيه قبل الانتهاء (علّم المراحل اللي عايز تتنبّه فيها)', weight=ft.FontWeight.BOLD, size=13),
                         ft.Row(list(remind_checks.values()), wrap=True, spacing=4, run_spacing=0),
                         ft.Text('بنتنبّهلك مرة عند كل مرحلة تعدّي عليها، ومرة لما المستند ينتهي - من الجرس في الشريط العلوي.', size=11.5, color=theme.TEXT_MUTED)], spacing=4)
    form_dlg = ft.AlertDialog(modal=True, title=ft.Text('مستند جديد'),
        content=ft.Container(width=700, content=ft.Column([
            ft.Row([f_type.control, f_title], wrap=True, spacing=10), f_kind, ft.Row([f_emp.control, f_holder], wrap=True, spacing=10),
            ft.Row([f_number, f_issuer, f_issue.control, f_expiry.control], wrap=True, spacing=10), ft.Row([f_cost, ft.OutlinedButton('إرفاق صورة المستند', icon=ft.Icons.ATTACH_FILE, on_click=pick_attachment), attach_text], spacing=10, wrap=True),
            rem_box, f_notes, f_err], tight=True, spacing=10, scroll=ft.ScrollMode.AUTO, height=560)),
        actions=[ft.TextButton('إلغاء', on_click=lambda e: close(form_dlg)), ft.FilledButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save)])
    page.overlay.append(form_dlg)

    def open_form(doc_id=None):
        nonlocal types
        types = services.list_document_types()
        f_type.options = [(str(t.id), t.name) for t in types]
        f_emp.options = [(str(x.id), f'{x.code} - {x.name}') for x in employees]
        editing['id'] = doc_id; editing['attach'] = None; attach_text.value = ''; f_err.visible = False
        if doc_id:
            r = services.get_tracked_document(doc_id)
            form_dlg.title.value = 'تعديل المستند'
            f_type.value = str(r['type_id']); f_title.value = r['title']; f_kind.value = r['holder_kind']; f_emp.value = str(r['employee_id']) if r['employee_id'] else None
            f_holder.value = r['holder_name']; f_number.value = r['doc_number']; f_issuer.value = r['issuer']
            f_issue.value = r['issue_date'].strftime('%Y-%m-%d') if r['issue_date'] else ''; f_expiry.value = r['expiry_date'].strftime('%Y-%m-%d')
            f_cost.value = f"{r['cost']:g}" if r['cost'] else ''; f_notes.value = r['notes']
            for d, cb in remind_checks.items():
                cb.value = d in r['remind_days']
            attach_text.value = 'فيه صورة محفوظة (اختار ملف جديد لو عايز تستبدلها)' if r['has_attachment'] else ''
        else:
            form_dlg.title.value = 'مستند جديد'
            f_type.value = None; f_title.value = ''; f_kind.value = 'employee'; f_emp.value = None; f_holder.value = ''; f_number.value = ''; f_issuer.value = ''
            f_issue.value = ''; f_expiry.value = ''; f_cost.value = ''; f_notes.value = ''
            for cb in remind_checks.values():
                cb.value = False
        on_kind()
        form_dlg.open = True; page.update()

    # ===================================================================== التجديد
    def open_renew(doc_id):
        r = services.get_tracked_document(doc_id)
        base = max(r['expiry_date'].date(), today)
        try:
            default_new = base.replace(year=base.year + 1)
        except ValueError:
            default_new = base + datetime.timedelta(days=365)
        new_expiry = theme.DateField('تاريخ الانتهاء الجديد *', page, width=190, value=default_new.strftime('%Y-%m-%d'))
        renew_date = theme.DateField('تاريخ التجديد', page, width=160, value=today.strftime('%Y-%m-%d'))
        number = ft.TextField(label='رقم المستند الجديد (لو اتغيّر)', width=240, hint_text=r['doc_number'] or '')
        cost = ft.TextField(label='تكلفة التجديد', width=150, keyboard_type=ft.KeyboardType.NUMBER, value=f"{r['cost']:g}" if r['cost'] else '')
        notes = ft.TextField(label='ملاحظات', width=520, multiline=True, min_lines=1, max_lines=3)
        att = {'path': None}; att_t = ft.Text('', size=12, color=theme.TEXT_MUTED)
        err = ft.Text('', color=theme.DANGER, visible=False, size=12)

        def quick(years):
            b = r['expiry_date'].date()
            b = max(b, today)
            try:
                nd = b.replace(year=b.year + years)
            except ValueError:
                nd = b + datetime.timedelta(days=365 * years)
            new_expiry.value = nd.strftime('%Y-%m-%d'); page.update()

        async def pick(e):
            p = await theme.pick_file(page, 'اختر صورة المستند المجدّد', ['pdf','png','jpg','jpeg'])
            if p:
                att['path'] = p; att_t.value = os.path.basename(p); page.update()

        def confirm(e):
            try:
                services.renew_tracked_document(doc_id, _d(new_expiry.value), _d(renew_date.value), number.value, float((cost.value or '0').replace(',', '') or 0), notes.value, att['path'])
                close(rdlg); refresh(True); snack('تم تجديد المستند وتسجيله في السجل')
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        rdlg = ft.AlertDialog(modal=True, title=ft.Text(f"تجديد: {r['title']}"),
            content=ft.Container(width=560, content=ft.Column([
                ft.Text(f"{r['type_name']} - {r['holder']} | ينتهي حاليًا {r['expiry_date']:%Y-%m-%d} ({days_text(r['days_left'])})", size=13, color=status_color(r['days_left']), weight=ft.FontWeight.BOLD),
                ft.Row([new_expiry.control, ft.OutlinedButton('+ سنة', on_click=lambda e: quick(1)), ft.OutlinedButton('+ سنتين', on_click=lambda e: quick(2)), ft.OutlinedButton('+ 5 سنين', on_click=lambda e: quick(5))], wrap=True, spacing=8),
                ft.Row([renew_date.control, number, cost], wrap=True, spacing=10),
                ft.Row([ft.OutlinedButton('إرفاق صورة المستند الجديد', icon=ft.Icons.ATTACH_FILE, on_click=pick), att_t], spacing=10), notes, err], tight=True, spacing=10)),
            actions=[ft.TextButton('إلغاء', on_click=lambda e: close(rdlg)), ft.FilledButton('تأكيد التجديد', icon=ft.Icons.AUTORENEW, bgcolor=theme.SUCCESS, on_click=confirm)])
        page.overlay.append(rdlg); rdlg.open = True; page.update()

    def open_history(doc_id):
        r = services.get_tracked_document(doc_id)
        rows = services.list_document_renewals(doc_id)
        tbl = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['تاريخ التجديد', 'الانتهاء القديم', 'الانتهاء الجديد', 'رقم المستند', 'التكلفة', 'ملاحظات', '']],
                           rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(x.renewed_at.strftime('%Y-%m-%d'))), ft.DataCell(ft.Text(x.old_expiry.strftime('%Y-%m-%d') if x.old_expiry else '-')),
                                                   ft.DataCell(ft.Text(x.new_expiry.strftime('%Y-%m-%d'), weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(x.doc_number or '-')),
                                                   ft.DataCell(ft.Text(f'{x.cost:,.2f}' if x.cost else '-')), ft.DataCell(ft.Text(x.notes or '-', size=12)),
                                                   ft.DataCell(ft.IconButton(icon=ft.Icons.ATTACH_FILE, tooltip='صورة المستند', on_click=lambda e, i=x.id: open_attachment(doc_id, i)) if x.attachment_path else ft.Text(''))]) for x in rows],
                           heading_row_height=38)
        body = [ft.Text(f"{r['type_name']} - {r['holder']} | ينتهي حاليًا {r['expiry_date']:%Y-%m-%d}", size=12, color=theme.TEXT_MUTED),
                theme.h_scroll(tbl) if rows else ft.Text('مفيش تجديدات متسجّلة لسه', color=theme.TEXT_MUTED)]
        hdlg = ft.AlertDialog(modal=True, title=ft.Text(f"سجل تجديدات: {r['title']}"), content=ft.Container(width=760, content=ft.Column(body, tight=True, spacing=10, scroll=ft.ScrollMode.AUTO, height=min(420, 120 + 50 * len(rows)))),
                              actions=[ft.TextButton('إغلاق', on_click=lambda e: close(hdlg))])
        page.overlay.append(hdlg); hdlg.open = True; page.update()

    # ===================================================================== أنواع المستندات
    def open_types():
        def render():
            nonlocal_rows = services.list_document_types(False)
            col.controls = [ft.Container(padding=ft.Padding(left=10, right=10, top=6, bottom=6), border_radius=8, bgcolor=theme.PRIMARY_LIGHT if t.is_active else theme.SURFACE_ALT,
                                         content=ft.Row([ft.Column([ft.Text(t.name + ('' if t.is_active else ' (معطّل)'), weight=ft.FontWeight.BOLD, color=None if t.is_active else theme.TEXT_MUTED),
                                                                    ft.Text(f"{services.DOC_HOLDER_KINDS[t.holder_kind]} | تنبيه قبل: " + ('، '.join(str(d) if d else 'يوم الانتهاء' for d in services._parse_remind_days(t.remind_days)) or 'بدون'), size=11, color=theme.TEXT_MUTED)], spacing=0, expand=True),
                                                         ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل', on_click=lambda e, x=t: edit_type(x))])) for t in nonlocal_rows]
            page.update()

        def edit_type(t=None):
            n = ft.TextField(label='اسم النوع *', width=300, value=t.name if t else '')
            hk = ft.Dropdown(label='خاص بـ', width=300, value=t.holder_kind if t else 'other', options=[ft.dropdown.Option(k, v) for k, v in services.DOC_HOLDER_KINDS.items()])
            tiers = services._parse_remind_days(t.remind_days) if t else [30, 7]
            cbs = {d: ft.Checkbox(label='يوم الانتهاء' if d == 0 else f'{d} يوم', value=d in tiers) for d in services.DOC_REMIND_CHOICES}
            act = ft.Switch(label='نشط', value=t.is_active if t else True, visible=bool(t))
            terr = ft.Text('', color=theme.DANGER, visible=False, size=12)

            def ok(e):
                try:
                    days = [d for d, c in cbs.items() if c.value]
                    if t:
                        services.update_document_type(t.id, n.value, hk.value, days, act.value)
                    else:
                        services.create_document_type(n.value, hk.value, days)
                    close(edlg); render(); snack('تم حفظ النوع')
                except Exception as ex:
                    terr.value = str(ex); terr.visible = True; page.update()
            edlg = ft.AlertDialog(modal=True, title=ft.Text('تعديل نوع' if t else 'نوع مستند جديد'),
                content=ft.Container(width=520, content=ft.Column([n, hk, ft.Text('التنبيه الافتراضي قبل الانتهاء', weight=ft.FontWeight.BOLD), ft.Row(list(cbs.values()), wrap=True, spacing=4), act, terr], tight=True, spacing=10)),
                actions=[ft.TextButton('إلغاء', on_click=lambda e: close(edlg)), ft.FilledButton('حفظ', bgcolor=theme.PRIMARY, on_click=ok)])
            page.overlay.append(edlg); edlg.open = True; page.update()

        col = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, height=420)
        tdlg = ft.AlertDialog(modal=True, title=ft.Text('أنواع المستندات'),
            content=ft.Container(width=560, content=ft.Column([ft.Text('أضف أي نوع مستند بتحب تتابعه (رخصة مصنع، شهادة جودة، اشتراك...) وحدد التنبيه الافتراضي له.', size=12, color=theme.TEXT_MUTED), col], tight=True, spacing=8)),
            actions=[ft.TextButton('إغلاق', on_click=lambda e: (close(tdlg), refresh_types())), ft.FilledButton('نوع جديد', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=lambda e: edit_type(None))])
        page.overlay.append(tdlg); tdlg.open = True
        render()

    def refresh_types():
        nonlocal types
        types = services.list_document_types()
        type_f.options = [ft.dropdown.Option('', 'كل الأنواع')] + [ft.dropdown.Option(str(t.id), t.name) for t in types]
        page.update()

    # ===================================================================== تصدير
    def export(kind):
        try:
            from ..report_export import export_pdf, export_excel
            data = {'hr_docs': query(), 'date_from': None, 'date_to': None}
            out_dir = os.path.join(services.APP_DIR, 'exports')
            os.makedirs(out_dir, exist_ok=True)
            theme.open_or_download_file(page, (export_pdf if kind == 'pdf' else export_excel)(data, 'hr_documents', out_dir)); snack('تم إنشاء الملف')
        except Exception as ex:
            snack(f'تعذر التصدير: {ex}')

    for c in (type_f, status_f, emp_f):
        c.on_change = refresh
    search_f.on_change = refresh
    refresh()
    return ft.Column([
        ft.Row([theme.page_title('تجديد الرخص والمستندات', 'إقامات، جوازات، رخص، عقود إيجار، تأمينات... أي مستند بتاريخ انتهاء - بنتنبّهلك قبل الانتهاء وبنسجّل كل تجديد'),
                ft.Container(expand=True), ft.OutlinedButton('أنواع المستندات', icon=ft.Icons.CATEGORY_OUTLINED, on_click=lambda e: open_types()),
                ft.OutlinedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf')), ft.OutlinedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('excel')),
                ft.FilledButton('مستند جديد', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=lambda e: open_form())], spacing=8),
        ft.Container(height=6), cards,
        ft.Row([type_f, status_f, emp_f, search_f], spacing=10, wrap=True), ft.Container(height=4),
        theme.card(theme.h_scroll(table.control)),
    ], expand=True, spacing=8, scroll=ft.ScrollMode.AUTO)
