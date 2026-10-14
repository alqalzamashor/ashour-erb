import datetime
import flet as ft
from .. import services, theme


def build_sales_quotations(page: ft.Page):
    """عروض أسعار المبيعات: إنشاء وتعديل وطباعة، متابعة الحالة (مسودة ← مرسل ← مقبول/مرفوض/منتهي)،
    وتحويل العرض لفاتورة مبيعات بنفس الأسعار بضغطة واحدة."""
    STATE_COLORS = {'draft': theme.TEXT_MUTED, 'sent': theme.PRIMARY, 'accepted': theme.SUCCESS, 'rejected': theme.DANGER, 'invoiced': '#0E7A3F', 'expired': theme.WARNING}
    L = services.QUOTATION_STATE_LABELS

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def close(d):
        d.open = False; page.update()

    def _d(v):
        v = (v or '').strip()
        return datetime.datetime.strptime(v, '%Y-%m-%d') if v else None

    # ===================================================================== القايمة
    range_f = theme.DateRangeField('الفترة', page, width=290)
    from_f, to_f = range_f.start, range_f.end
    search_f = ft.TextField(label='بحث برقم العرض أو اسم العميل', width=260, prefix_icon=ft.Icons.SEARCH)
    state_f = ft.Dropdown(label='الحالة', width=170, options=[ft.dropdown.Option('', 'الكل')] + [ft.dropdown.Option(k, v) for k, v in L.items()], value='')
    cards = ft.Row(wrap=True, spacing=12)

    def print_quote(qid):
        try:
            theme.open_or_download_file(page, services.generate_quotation_pdf_file(qid))
        except Exception as ex:
            snack(f'تعذرت الطباعة: {ex}')

    def do_state(qid, state, note=''):
        try:
            services.set_quotation_state(qid, state, note); refresh(); snack('تم تحديث حالة العرض')
        except Exception as ex:
            snack(str(ex))

    def open_reject(q):
        note_f = ft.TextField(label='سبب رفض العميل *', width=380, multiline=True, min_lines=2, max_lines=3)
        err = ft.Text('', color=theme.DANGER, visible=False, size=12)

        def confirm(e):
            try:
                services.set_quotation_state(q.id, 'rejected', note_f.value)
                close(rdlg); refresh(); snack('تم تسجيل رفض العميل')
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()
        rdlg = ft.AlertDialog(modal=True, title=ft.Text(f'رفض العرض {q.number}'), content=ft.Container(width=420, content=ft.Column([note_f, err], tight=True, spacing=10)),
                              actions=[ft.TextButton('إلغاء', on_click=lambda e: close(rdlg)), ft.FilledButton('تأكيد الرفض', bgcolor=theme.DANGER, on_click=confirm)])
        page.overlay.append(rdlg); rdlg.open = True; page.update()

    def do_duplicate(qid):
        try:
            nid = services.duplicate_quotation(qid); refresh(); snack(f'تم عمل نسخة جديدة: {services.get_quotation(nid).number}')
        except Exception as ex:
            snack(str(ex))

    def do_delete(q):
        try:
            services.delete_quotation(q.id); refresh(); snack(f'تم حذف {q.number}')
        except Exception as ex:
            snack(str(ex))

    def row_builder(q):
        eff = services.quotation_effective_state(q)
        open_state = q.state in ('draft', 'sent', 'accepted')
        def tb(label, icon, handler, color=None, tooltip=None):
            return ft.TextButton(label, icon=icon, tooltip=tooltip, on_click=handler, style=ft.ButtonStyle(color=color, padding=ft.Padding(left=6, right=6, top=2, bottom=2)))
        acts = [ft.IconButton(icon=ft.Icons.PRINT_OUTLINED, tooltip='طباعة عرض السعر PDF', on_click=lambda e, i=q.id: print_quote(i))]
        if q.state not in ('invoiced', 'rejected'):
            acts.append(tb('فاتورة', ft.Icons.RECEIPT_LONG, lambda e, x=q: open_convert(x), theme.SUCCESS, 'تحويل العرض لفاتورة مبيعات'))
            acts.append(ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل العرض', on_click=lambda e, i=q.id: open_form(i)))
        if q.state == 'draft':
            acts.append(tb('إرسال', ft.Icons.SEND_OUTLINED, lambda e, i=q.id: do_state(i, 'sent'), theme.PRIMARY, 'تسجيل إن العرض اتبعت للعميل'))
        if q.state in ('draft', 'sent'):
            acts.append(ft.IconButton(icon=ft.Icons.THUMB_UP_OUTLINED, icon_color=theme.SUCCESS, tooltip='العميل وافق', on_click=lambda e, i=q.id: do_state(i, 'accepted')))
        if open_state:
            acts.append(ft.IconButton(icon=ft.Icons.THUMB_DOWN_OUTLINED, icon_color=theme.DANGER, tooltip='العميل رفض', on_click=lambda e, x=q: open_reject(x)))
        acts.append(ft.IconButton(icon=ft.Icons.CONTENT_COPY, tooltip='نسخ كعرض جديد', on_click=lambda e, i=q.id: do_duplicate(i)))
        if q.state != 'invoiced':
            acts.append(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف', on_click=lambda e, x=q: do_delete(x)))
        left = (q.valid_until.date() - datetime.date.today()).days if q.valid_until else None
        valid_cell = ft.Column([ft.Text(q.valid_until.strftime('%Y-%m-%d') if q.valid_until else '-', size=12)] + (
            [ft.Text(f'باقي {left} يوم', size=10, color=theme.WARNING if left <= 3 else theme.TEXT_MUTED)] if open_state and left is not None and left >= 0 else
            [ft.Text(f'انتهى من {-left} يوم', size=10, color=theme.DANGER)] if open_state and left is not None else []), spacing=0, tight=True)
        state_cell = ft.Column([ft.Text(L[eff], color=STATE_COLORS[eff], weight=ft.FontWeight.BOLD)] + (
            [ft.Text(q.decision_note, size=10, color=theme.TEXT_MUTED)] if q.state == 'rejected' and q.decision_note else []), spacing=0, tight=True)
        return ft.DataRow(cells=[
            ft.DataCell(ft.Text(q.number, weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(q.date.strftime('%Y-%m-%d'))),
            ft.DataCell(ft.Text(q.customer.name if q.customer else '-')), ft.DataCell(valid_cell),
            ft.DataCell(ft.Text(f'{q.total:,.2f}', weight=ft.FontWeight.BOLD)), ft.DataCell(state_cell),
            ft.DataCell(ft.Text(q.invoice.number if q.invoice else '-', color=theme.SUCCESS if q.invoice else theme.TEXT_MUTED)),
            ft.DataCell(ft.Row(acts, spacing=0))])

    table = theme.SortableDataTable(columns=[
        ('رقم العرض', lambda q: q.number), ('التاريخ', lambda q: q.date), ('العميل', lambda q: q.customer.name if q.customer else ''), ('ساري حتى', lambda q: q.valid_until),
        ('الإجمالي', lambda q: q.total, True), ('الحالة', lambda q: services.quotation_effective_state(q)), ('الفاتورة', lambda q: q.invoice.number if q.invoice else ''), ('الإجراءات', None)],
        row_builder=row_builder, page=page, expand=True)

    def _parse(v):
        try:
            return datetime.datetime.strptime((v or '').strip(), '%Y-%m-%d').date() if (v or '').strip() else None
        except ValueError:
            return None

    def refresh(e=None):
        rows = services.list_quotations(state=state_f.value or None, date_from=_parse(from_f.value), date_to=_parse(to_f.value), text=search_f.value)
        table.set_data(rows)
        everything = services.list_quotations() if (state_f.value or _parse(from_f.value) or _parse(to_f.value) or (search_f.value or '').strip()) else rows
        def card(label, value, count, color):
            return theme.card(ft.Column([ft.Text(label, size=12, color=theme.TEXT_MUTED), ft.Text(f'{value:,.2f}', size=20, weight=ft.FontWeight.BOLD, color=color),
                                         ft.Text(f'{count} عرض', size=11, color=theme.TEXT_MUTED)], spacing=0, tight=True), padding=14)
        def agg(*states):
            sel = [q for q in everything if services.quotation_effective_state(q) in states]
            return sum(q.total for q in sel), len(sel)
        o = agg('draft', 'sent'); a = agg('accepted'); i = agg('invoiced'); x = agg('expired')
        cards.controls = [card('عروض مفتوحة (مسودة / مرسلة)', *o, theme.PRIMARY), card('مقبولة - جاهزة للتحويل لفاتورة', *a, theme.SUCCESS),
                          card('اتحوّلت لفواتير', *i, '#0E7A3F'), card('منتهية الصلاحية', *x, theme.WARNING)]
        if e is not None:
            page.update()

    def clear_filters(e=None):
        from_f.value = ''; to_f.value = ''; search_f.value = ''; state_f.value = ''
        refresh(True)

    for c in (from_f, to_f):
        c.on_change = refresh
    search_f.on_change = refresh; state_f.on_change = refresh

    # ===================================================================== نموذج العرض
    from ._invoice_grid import InvoiceLinesGrid
    editing = {'id': None}
    customer_dd = theme.SearchableDropdown(label='العميل *', width=300, options=[], add_label='➕ إضافة عميل جديد:')
    date_f = theme.DateField('تاريخ العرض', page, width=160, value=datetime.date.today().strftime('%Y-%m-%d'))
    valid_f = theme.DateField('ساري حتى', page, width=160, value='')
    allowed = services.user_branch_ids()
    branches = [b for b in services.list_branches(True) if not allowed or b.id in allowed]
    centers = services.list_cost_centers(True)
    branch_dd = ft.Dropdown(label='الفرع', width=200, options=[ft.dropdown.Option(str(b.id), f'{b.code} - {b.name}') for b in branches])
    center_dd = ft.Dropdown(label='مركز التكلفة', width=200, options=[ft.dropdown.Option(str(c.id), f'{c.code} - {c.name}') for c in centers])
    notes_f = ft.TextField(label='ملاحظات', width=520)
    terms_f = ft.TextField(label='الشروط والأحكام (سطر لكل شرط)', multiline=True, min_lines=2, max_lines=4, width=520,
                           hint_text='مثال: الدفع خلال 30 يوم من تاريخ الفاتورة')
    discount_f = ft.TextField(label='خصم إجمالي', value='0', keyboard_type=ft.KeyboardType.NUMBER, width=140)
    subtotal_t = ft.Text('0.00', weight=ft.FontWeight.BOLD); tax_t = ft.Text('0.00', weight=ft.FontWeight.BOLD)
    total_t = ft.Text('0.00', weight=ft.FontWeight.BOLD, size=18, color=theme.PRIMARY)
    ferr = ft.Text('', color=theme.DANGER, visible=False)

    def recompute(e=None):
        sub = tax = grand = 0.0
        for it in grid.preview_items():
            base = max(0.0, it['quantity'] * it['unit_price'] - it['discount']); t = base * it['tax_rate'] / 100.0
            sub += base; tax += t; grand += base + t
        try:
            gd = float(discount_f.value or 0)
        except ValueError:
            gd = 0.0
        subtotal_t.value = f'{sub:,.2f}'; tax_t.value = f'{tax:,.2f}'; total_t.value = f'{max(0.0, grand - gd):,.2f}'

    grid = InvoiceLinesGrid(page, is_sales=True, on_change=lambda: (recompute(), page.update()))

    def resolve_price(p, unit_line):
        cid = int(customer_dd.value) if customer_dd.value else None
        price, from_list = services.get_customer_product_price(cid, p.id)
        if from_list:
            return price, True
        if unit_line and unit_line.sale_price is not None:
            return unit_line.sale_price, False
        return p.sale_price, False

    grid.price_resolver = resolve_price
    customer_dd.on_change = lambda e: (grid.reprice(), page.update())
    discount_f.on_change = lambda e: (recompute(), page.update())

    def open_quick_customer(typed):
        n_f = ft.TextField(label='اسم العميل *', width=360, value=typed, autofocus=True)
        ph_f = ft.TextField(label='الهاتف', width=170)
        qerr = ft.Text('', color=theme.DANGER, visible=False, size=12)

        def save_c(ev):
            try:
                cid = services.create_customer(n_f.value, ph_f.value)
                customer_dd.options = [(str(c.id), c.name) for c in services.list_customers()]
                customer_dd.value = str(cid)
                qdlg.open = False; grid.reprice(); snack(f'تم إضافة العميل "{(n_f.value or "").strip()}" واختياره')
            except Exception as ex:
                qerr.value = str(ex); qerr.visible = True; page.update()
        qdlg = ft.AlertDialog(modal=True, title=ft.Text('إضافة عميل جديد (فرد)'),
            content=ft.Container(width=400, content=ft.Column([n_f, ph_f, ft.Text('للشركات (B2B) بالرقم الضريبي والعنوان: من شاشة إدارة العملاء.', size=11, color=theme.TEXT_MUTED), qerr], tight=True, spacing=12)),
            actions=[ft.TextButton('إلغاء', on_click=lambda ev: close(qdlg)), ft.FilledButton('حفظ واختيار', icon=ft.Icons.CHECK, bgcolor=theme.PRIMARY, on_click=save_c)])
        page.overlay.append(qdlg); qdlg.open = True; page.update()

    customer_dd.on_add = open_quick_customer

    def collect():
        if not customer_dd.value:
            raise ValueError('اختر العميل')
        items = grid.get_items()
        d = _d(date_f.value) or datetime.datetime.now()
        return dict(customer_id=int(customer_dd.value), items=items, notes=notes_f.value, terms=terms_f.value, discount=float(discount_f.value or 0),
                    quote_date=d, valid_until=_d(valid_f.value), branch_id=int(branch_dd.value) if branch_dd.value else None,
                    cost_center_id=int(center_dd.value) if center_dd.value else None)

    def save(print_after=False):
        try:
            data = collect()
            if editing['id']:
                services.update_quotation(editing['id'], **data); qid = editing['id']; msg = 'تم تعديل العرض'
            else:
                qid = services.create_quotation(**data); msg = f'تم إنشاء العرض {services.get_quotation(qid).number}'
            close(form_dlg); refresh(True); snack(msg)
            if print_after:
                print_quote(qid)
        except Exception as ex:
            ferr.value = str(ex); ferr.visible = True; page.update()

    form_dlg = ft.AlertDialog(
        modal=True, title=ft.Text('عرض سعر جديد'),
        content=ft.Container(width=1100, content=ft.Column([
            ft.Row([customer_dd.control, date_f.control, valid_f.control, branch_dd, center_dd], wrap=True, spacing=12),
            ft.Row([notes_f, terms_f], wrap=True, spacing=12),
            ft.Divider(),
            ft.Text('بنود العرض', weight=ft.FontWeight.BOLD),
            ft.Text('اكتب كود أو اسم الصنف واضغط Enter، وكمّل بـ Enter: الكمية ← السعر ← الخصم. السعر بيجي من قائمة أسعار العميل لو مربوط بقائمة، وتقدر تعدّله.', size=12, color=theme.TEXT_MUTED),
            grid.control, ft.Divider(),
            ft.Row([ft.Column([ft.Text('الإجمالي قبل الضريبة', color=theme.TEXT_MUTED), subtotal_t], spacing=2), ft.Column([ft.Text('مجموع الضريبة', color=theme.TEXT_MUTED), tax_t], spacing=2),
                    ft.Column([ft.Text('خصم العرض', color=theme.TEXT_MUTED), discount_f], spacing=2), ft.Container(expand=True),
                    ft.Column([ft.Text('إجمالي العرض', color=theme.TEXT_MUTED), total_t], spacing=2)], spacing=20), ferr], spacing=10, tight=True)),
        actions=[ft.TextButton('إلغاء', on_click=lambda e: close(form_dlg)),
                 ft.OutlinedButton('حفظ وطباعة', icon=ft.Icons.PRINT, on_click=lambda e: save(True)),
                 ft.FilledButton('حفظ العرض', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=lambda e: save(False))],
        actions_alignment=ft.MainAxisAlignment.END)
    page.overlay.append(form_dlg)

    def open_form(qid=None):
        editing['id'] = qid
        customer_dd.options = [(str(c.id), c.name) for c in services.list_customers()]
        grid.set_products([p for p in services.list_products() if p.can_be_sold])
        ferr.visible = False
        if qid:
            q = services.get_quotation(qid)
            form_dlg.title.value = f'تعديل عرض السعر {q.number}'
            customer_dd.value = str(q.customer_id)
            date_f.value = q.date.strftime('%Y-%m-%d'); valid_f.value = q.valid_until.strftime('%Y-%m-%d') if q.valid_until else ''
            branch_dd.value = str(q.branch_id) if q.branch_id else None; center_dd.value = str(q.cost_center_id) if q.cost_center_id else None
            notes_f.value = q.notes or ''; terms_f.value = q.terms or ''; discount_f.value = f'{q.discount:g}'
            grid.load_items([{'product_id': i.product_id, 'unit_id': i.unit_id, 'quantity': i.quantity, 'unit_price': i.unit_price, 'discount': i.discount, 'tax_rate': i.tax_rate} for i in q.items])
            if q.state in ('sent', 'accepted'):
                ferr.value = 'تنبيه: تعديل عرض اتبعت أو اتقبل بيرجّعه لمسودة (العميل وافق على نسخة قديمة).'; ferr.visible = True
        else:
            form_dlg.title.value = 'عرض سعر جديد'
            customer_dd.value = None
            date_f.value = datetime.date.today().strftime('%Y-%m-%d')
            valid_f.value = (datetime.date.today() + datetime.timedelta(days=services.QUOTATION_DEFAULT_VALID_DAYS)).strftime('%Y-%m-%d')
            bid = services.default_branch_id(); cid = services.default_cost_center_id()
            branch_dd.value = str(bid) if bid else None; center_dd.value = str(cid) if cid else None
            notes_f.value = ''; terms_f.value = ''; discount_f.value = '0'
            grid.clear()
        recompute()
        form_dlg.open = True; page.update(); grid.focus_first()

    # ===================================================================== تحويل لفاتورة
    def open_convert(q):
        full = services.get_quotation(q.id)
        locations = services.list_locations(full.branch_id)
        loc_dd = ft.Dropdown(label='المخزن اللي هيتخصم منه', width=300, options=[ft.dropdown.Option(str(l.id), l.name) for l in locations],
                             value=str(services.default_location_id(full.branch_id)) if services.default_location_id(full.branch_id) else (str(locations[0].id) if locations else None))
        inv_date_f = theme.DateField('تاريخ الفاتورة', page, width=170, value=datetime.date.today().strftime('%Y-%m-%d'))
        expired = services.quotation_effective_state(full) == 'expired'
        force_sw = ft.Switch(label='أكّد التحويل رغم انتهاء صلاحية العرض', value=False, visible=expired)
        err = ft.Text('', color=theme.DANGER, visible=False, size=12)

        def confirm(e):
            try:
                inv_id = services.convert_quotation_to_invoice(full.id, int(loc_dd.value) if loc_dd.value else None, _d(inv_date_f.value), allow_expired=force_sw.value)
                close(cdlg); refresh(True)
                inv = services.get_sales_invoice(inv_id)
                def print_inv(ev):
                    try:
                        theme.open_or_download_file(page, services.generate_invoice_pdf_file(inv_id))
                    except Exception as ex2:
                        snack(f'تعذرت الطباعة: {ex2}')
                done = ft.AlertDialog(modal=True, title=ft.Text('تم إنشاء الفاتورة'),
                    content=ft.Container(width=420, content=ft.Column([
                        ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, color=theme.SUCCESS), ft.Text(f'فاتورة المبيعات {inv.number} من العرض {full.number}', weight=ft.FontWeight.BOLD)], spacing=8),
                        ft.Text(f'الإجمالي {inv.total:,.2f} - العميل {inv.customer.name if inv.customer else "-"}. اتخصمت الكميات من المخزون وبتظهر الفاتورة في شاشة فواتير المبيعات.', size=12, color=theme.TEXT_MUTED)], tight=True, spacing=10)),
                    actions=[ft.TextButton('إغلاق', on_click=lambda ev: close(done)), ft.FilledButton('طباعة الفاتورة', icon=ft.Icons.PRINT, bgcolor=theme.PRIMARY, on_click=print_inv)])
                page.overlay.append(done); done.open = True; page.update()
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()

        cdlg = ft.AlertDialog(modal=True, title=ft.Text(f'تحويل العرض {full.number} لفاتورة مبيعات'),
            content=ft.Container(width=480, content=ft.Column([
                ft.Text(f'العميل: {full.customer.name if full.customer else "-"}  |  {len(full.items)} بند  |  الإجمالي {full.total:,.2f}', weight=ft.FontWeight.BOLD),
                ft.Text('الفاتورة بتتعمل بنفس الأصناف والأسعار والخصومات اللي في العرض، وبتخصم من المخزون. لو الكمية مش متوفرة بتظهر رسالة والعرض بيفضل زي ما هو.', size=12, color=theme.TEXT_MUTED),
                loc_dd, inv_date_f.control, force_sw, err], tight=True, spacing=12)),
            actions=[ft.TextButton('إلغاء', on_click=lambda e: close(cdlg)), ft.FilledButton('إنشاء الفاتورة', icon=ft.Icons.RECEIPT_LONG, bgcolor=theme.PRIMARY, on_click=confirm)])
        page.overlay.append(cdlg); cdlg.open = True; page.update()

    refresh()
    return ft.Column([
        ft.Row([theme.page_title('عروض أسعار المبيعات', 'إنشاء عروض الأسعار ومتابعة موافقة العملاء وتحويل العرض المقبول لفاتورة مبيعات'),
                ft.Container(expand=True), ft.FilledButton('عرض سعر جديد', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=lambda e: open_form())]),
        ft.Container(height=8),
        ft.Row([range_f.control, search_f, state_f, ft.TextButton('مسح الفلاتر', icon=ft.Icons.FILTER_ALT_OFF, on_click=clear_filters)], spacing=10),
        cards, ft.Container(height=4),
        theme.card(theme.h_scroll(table.control)),
    ], expand=True, spacing=10, scroll=ft.ScrollMode.AUTO)
