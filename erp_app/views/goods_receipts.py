import datetime
import os
import flet as ft
from .. import services, theme, drafts


def build_goods_receipts(page: ft.Page):
    """سندات استلام المشتريات - تسجيل استلام البضاعة فعليًا في المخزون قبل
    وصول فاتورة المورد، وتحويل السند لفاتورة مشتريات لما الفاتورة توصل.
    التصميم زي فاتورة المشتريات: سجل السندات في الشاشة، والسند الجديد في حوار بجدول أصناف (شكل Excel)."""
    from ._receipt_grid import ReceiptLinesGrid

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def close(d):
        d.open = False; page.update()

    # ===================================================================== القايمة
    search_f = ft.TextField(label='بحث برقم السند أو اسم المورد', width=280, prefix_icon=ft.Icons.SEARCH)
    status_f = ft.Dropdown(label='الحالة', width=190, value='', options=[ft.dropdown.Option('', 'الكل'), ft.dropdown.Option('pending', 'بانتظار الفاتورة'),
                                                                           ft.dropdown.Option('invoiced', 'تم التحويل'), ft.dropdown.Option('voided', 'ملغى')])

    def _receipt_status(r):
        if r.voided:
            return 'ملغى', theme.DANGER, 'voided'
        if r.invoiced:
            return f'تم التحويل ({r.purchase_invoice.number if r.purchase_invoice else ""})', theme.SUCCESS, 'invoiced'
        return 'بانتظار الفاتورة', theme.WARNING, 'pending'

    def _estimate(r):
        return sum((it.quantity or 0) * (it.unit_cost or 0) for it in r.items)

    def print_receipt(rid):
        try:
            from ..report_export import export_voucher_pdf
            r = services.get_goods_receipt(rid)
            st = _receipt_status(r)[0]
            rows = [[f'{it.product.sku} - {it.product.name}' if it.product else '-', (it.unit.name if it.unit else (it.product.unit if it.product else '')), f'{it.quantity:g}', it.unit_cost or 0.0, (it.quantity or 0) * (it.unit_cost or 0)] for it in r.items]
            doc = {'title': 'سند استلام مشتريات', 'number': r.number, 'date': r.date,
                   'fields': [('المورد', r.supplier.name if r.supplier else '-'), ('المخزن', r.location.name if r.location else '-'), ('الحالة', st), ('ملاحظات', r.notes or '-')],
                   'table': {'caption': 'الأصناف المستلمة - التكلفة تقديرية لحين وصول فاتورة المورد', 'headers': ['الصنف', 'الوحدة', 'الكمية المستلمة', 'تكلفة الوحدة', 'الإجمالي'], 'rows': rows,
                             'col_weights': [4, 1.2, 1.6, 2.0, 1.6]},
                   'totals': [('إجمالي الكميات', sum(it.quantity or 0 for it in r.items)), ('إجمالي التكلفة التقديرية', _estimate(r))],
                   'signatures': ['المورد / المندوب', 'أمين المخزن', 'المحاسب', 'المدير المالي']}
            out_dir = os.path.join(services.APP_DIR, 'exports')
            theme.open_or_download_file(page, export_voucher_pdf(doc, out_dir, 'goods_receipt'))
        except Exception as ex:
            snack(f'تعذرت الطباعة: {ex}')

    def _receipt_row(r):
        items_text = '، '.join(f"{it.product.name} ({it.quantity:g}" + (f' {it.unit.name}' if it.unit else '') + ')' for it in r.items)
        status_text, status_color, status_key = _receipt_status(r)
        actions = ft.Row(spacing=2, controls=[ft.IconButton(icon=ft.Icons.PRINT_OUTLINED, tooltip='طباعة سند الاستلام', on_click=lambda e, rid=r.id: print_receipt(rid))])
        if status_key == 'pending':
            actions.controls.append(ft.IconButton(icon=ft.Icons.RECEIPT_LONG_OUTLINED, tooltip='تحويل لفاتورة مشتريات', icon_color=theme.PRIMARY, on_click=lambda e, rid=r.id: do_convert(rid)))
            actions.controls.append(ft.IconButton(icon=ft.Icons.CANCEL_OUTLINED, tooltip='إلغاء السند', icon_color=theme.DANGER, on_click=lambda e, rid=r.id: do_void(rid)))
        return ft.DataRow(cells=[
            ft.DataCell(ft.Text(r.number, weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(r.date.strftime('%Y-%m-%d %H:%M'))),
            ft.DataCell(ft.Text(r.supplier.name if r.supplier else '-')), ft.DataCell(ft.Text(r.location.name if r.location else '-')),
            ft.DataCell(ft.Text(items_text, size=12)), ft.DataCell(ft.Text(f'{_estimate(r):,.2f}')),
            ft.DataCell(theme.status_badge(status_text, status_color)), ft.DataCell(actions)])

    receipts_table = theme.SortableDataTable(
        columns=[('رقم السند', lambda r: r.number), ('التاريخ', lambda r: r.date), ('المورد', lambda r: r.supplier.name if r.supplier else ''),
                 ('المخزن', lambda r: r.location.name if r.location else ''), ('الأصناف', None), ('التكلفة التقديرية', _estimate, True),
                 ('الحالة', lambda r: _receipt_status(r)[0]), ('', None)],
        row_builder=_receipt_row, page=page)

    def refresh_receipts(e=None):
        rows = services.list_goods_receipts(limit=1000)
        text = (search_f.value or '').strip().lower()
        if text:
            rows = [r for r in rows if text in r.number.lower() or text in (r.supplier.name.lower() if r.supplier else '')]
        if status_f.value:
            rows = [r for r in rows if _receipt_status(r)[2] == status_f.value]
        receipts_table.set_data(rows)
        if e is not None:
            page.update()

    search_f.on_change = refresh_receipts
    status_f.on_change = refresh_receipts

    def do_convert(receipt_id):
        try:
            services.convert_receipt_to_purchase_invoice(receipt_id)
            refresh_receipts()
            snack('تم تحويل السند لفاتورة مشتريات بنجاح')
        except Exception as ex:
            snack(str(ex))

    def do_void(receipt_id):
        void_err = ft.Text('', color=theme.DANGER, visible=False)

        def confirm(ev):
            try:
                services.void_goods_receipt(receipt_id)
                void_dialog.open = False
                page.update()
                refresh_receipts()
            except Exception as ex:
                void_err.value = str(ex); void_err.visible = True; page.update()

        void_dialog = ft.AlertDialog(
            modal=True, title=ft.Text('تأكيد الإلغاء'),
            content=ft.Column([ft.Text('هل تريد إلغاء سند الاستلام؟ هيترجع تأثيره على المخزون.'), void_err], tight=True),
            actions=[ft.TextButton('تراجع', on_click=lambda ev: close(void_dialog)), ft.FilledButton('تأكيد الإلغاء', bgcolor=theme.DANGER, on_click=confirm)])
        page.overlay.append(void_dialog); void_dialog.open = True; page.update()

    # ===================================================================== نموذج السند الجديد
    supplier_dd = theme.SearchableDropdown(label='المورد *', width=280, options=[])
    location_dd = ft.Dropdown(label='المخزن *', width=220, options=[])
    date_field = theme.DateField('تاريخ الاستلام', page, width=160, value=datetime.date.today().strftime('%Y-%m-%d'))
    allowed = services.user_branch_ids()
    branches = [b for b in services.list_branches(True) if not allowed or b.id in allowed]
    centers = services.list_cost_centers(True)
    branch_dd = ft.Dropdown(label='الفرع', width=210, options=[ft.dropdown.Option(str(b.id), f'{b.code} - {b.name}') for b in branches])
    center_dd = ft.Dropdown(label='مركز التكلفة', width=210, options=[ft.dropdown.Option(str(c.id), f'{c.code} - {c.name}') for c in centers])
    notes_field = ft.TextField(label='ملاحظات', width=520)
    err = ft.Text('', color=theme.DANGER, visible=False)
    count_t = ft.Text('0', weight=ft.FontWeight.BOLD); qty_t = ft.Text('0', weight=ft.FontWeight.BOLD)
    total_t = ft.Text('0.00', weight=ft.FontWeight.BOLD, size=18, color=theme.PRIMARY)

    def recompute():
        n, qty, cost = grid.summary()
        count_t.value = str(n); qty_t.value = f'{qty:g}'; total_t.value = f'{cost:,.2f}'

    grid = ReceiptLinesGrid(page, on_change=lambda: (recompute(), autosave_draft(), page.update()))

    # ---------- حفظ تلقائي للمسودة (لو الاتصال قطع ما يضيعش اللي اتكتب) ----------
    DRAFT_KIND = 'goods_receipt'
    dstate = {'on': False}
    draft_text = ft.Text('', color=theme.WARNING_TEXT, expand=True, size=12.5)
    draft_note = ft.Container(visible=False, padding=8, border_radius=8, bgcolor=theme.SURFACE_ALT,
                              content=ft.Row([ft.Icon(ft.Icons.RESTORE, color=theme.WARNING_TEXT, size=18), draft_text,
                                              ft.TextButton('تجاهل المسودة', on_click=lambda e: discard_draft())], spacing=8))

    def collect_draft():
        return {'supplier': supplier_dd.value or '', 'location': location_dd.value or '', 'branch': branch_dd.value or '', 'center': center_dd.value or '',
                'notes': notes_field.value or '', 'items': grid.snapshot()}

    def autosave_draft(e=None):
        if not dstate['on']:
            return
        d = collect_draft()
        if not d['items'] and not d['notes'].strip():
            drafts.clear(DRAFT_KIND)
        else:
            drafts.save(DRAFT_KIND, d)

    def restore_draft():
        saved = drafts.load(DRAFT_KIND)
        if not saved:
            return
        d, at = saved
        dstate['on'] = False
        try:
            if d.get('supplier') and any(o[0] == d['supplier'] for o in supplier_dd.options):
                supplier_dd.value = d['supplier']
            for dd, key in ((location_dd, 'location'), (branch_dd, 'branch'), (center_dd, 'center')):
                if d.get(key) and any(o.key == d[key] for o in dd.options):
                    dd.value = d[key]
            notes_field.value = d.get('notes', '')
            grid.load_items(d.get('items', []))
            draft_text.value = f"اتسترجعت مسودة سند استلام غير محفوظ (آخر حفظ {at:%Y-%m-%d %H:%M}) - كمّل واحفظ، أو اضغط تجاهل."
            draft_note.visible = True
        finally:
            dstate['on'] = True

    def discard_draft():
        drafts.clear(DRAFT_KIND)
        draft_note.visible = False
        notes_field.value = ''
        grid.clear(); recompute()
        page.update()

    def close_create(e=None):
        create_dialog.open = False
        dstate['on'] = False
        try:
            if not grid.snapshot() and not (notes_field.value or '').strip():
                drafts.clear(DRAFT_KIND)
        except Exception:      # noqa: BLE001
            pass
        page.update()

    def do_save(e):
        try:
            if not supplier_dd.value:
                raise ValueError('اختر المورد')
            if not location_dd.value:
                raise ValueError('اختر المخزن')
            items = grid.get_items()
            if not items:
                raise ValueError('أضف صنف واحد على الأقل')
            rdate = datetime.datetime.strptime(date_field.value, '%Y-%m-%d') if (date_field.value or '').strip() else None
            if rdate and rdate.date() == datetime.date.today():
                rdate = datetime.datetime.now()
            services.create_goods_receipt(int(supplier_dd.value), items, int(location_dd.value), notes=notes_field.value or '',
                                          branch_id=int(branch_dd.value) if branch_dd.value else None,
                                          cost_center_id=int(center_dd.value) if center_dd.value else None, invoice_date=rdate)
            err.visible = False
            drafts.clear(DRAFT_KIND); draft_note.visible = False
            close_create()
            refresh_receipts()
            snack('تم تسجيل سند الاستلام وتحديث المخزون بنجاح')
        except Exception as ex:
            err.value = str(ex); err.visible = True
        page.update()

    create_dialog = ft.AlertDialog(
        modal=True, title=ft.Text('سند استلام مشتريات جديد'),
        content=ft.Container(width=1000, content=ft.Column([
            ft.Row([supplier_dd.control, location_dd, date_field.control, branch_dd, center_dd], wrap=True, spacing=12),
            draft_note,
            ft.Row([notes_field], spacing=12),
            ft.Divider(),
            ft.Text('الأصناف المستلمة', weight=ft.FontWeight.BOLD),
            ft.Text('اكتب كود أو اسم الصنف واضغط Enter، وكمّل بـ Enter: الكمية ← التكلفة التقديرية ← الصنف اللي بعده. '
                    'السند بيسجّل الاستلام في المخزون فورًا، وبعدين تحوّله لفاتورة مشتريات لما فاتورة المورد توصل من غير ما تدخل الكميات تاني.',
                    size=12, color=theme.TEXT_MUTED),
            grid.control,
            ft.Divider(),
            ft.Row([
                ft.Column([ft.Text('عدد الأصناف', color=theme.TEXT_MUTED), count_t], spacing=2),
                ft.Column([ft.Text('إجمالي الكميات', color=theme.TEXT_MUTED), qty_t], spacing=2),
                ft.Container(expand=True),
                ft.Column([ft.Text('إجمالي التكلفة التقديرية', color=theme.TEXT_MUTED), total_t], spacing=2),
            ], spacing=20),
            err,
        ], spacing=10, tight=True)),
        actions=[ft.TextButton('إلغاء', on_click=close_create),
                 ft.FilledButton('حفظ سند الاستلام', icon=ft.Icons.INVENTORY_OUTLINED, bgcolor=theme.PRIMARY, on_click=do_save)],
        actions_alignment=ft.MainAxisAlignment.END)
    page.overlay.append(create_dialog)

    supplier_dd.on_change = lambda e=None: autosave_draft()
    notes_field.on_change = lambda e=None: autosave_draft()
    for _c in (location_dd, branch_dd, center_dd):
        _c.on_select = lambda e=None: autosave_draft()

    def open_create(e=None):
        dstate['on'] = False
        supplier_dd.options = [(str(s.id), s.name) for s in services.list_suppliers()]
        locations = services.list_locations()
        location_dd.options = [ft.dropdown.Option(str(l.id), l.name) for l in locations]
        if not location_dd.value:
            location_dd.value = str(services.default_location_id() or '') or None
        bid = services.default_branch_id(); cid = services.default_cost_center_id()
        if not branch_dd.value:
            branch_dd.value = str(bid) if bid else None
        if not center_dd.value:
            center_dd.value = str(cid) if cid else None
        date_field.value = datetime.date.today().strftime('%Y-%m-%d')
        notes_field.value = ''
        err.visible = False
        draft_note.visible = False
        grid.set_products([p for p in services.list_products() if p.can_be_purchased and p.product_type != 'service'])
        grid.clear()
        restore_draft()
        dstate['on'] = True
        create_dialog.open = True
        page.update()

    refresh_receipts()

    return ft.Column(
        [
            ft.Row([theme.page_title('سندات استلام المشتريات', 'سجّل استلام البضاعة فور وصولها، وحوّلها لفاتورة مشتريات لما فاتورة المورد توصل'),
                    ft.Container(expand=True),
                    ft.FilledButton('سند استلام جديد', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=open_create)]),
            ft.Container(height=8),
            ft.Row([search_f, status_f], spacing=10),
            ft.Container(height=4),
            theme.card(theme.h_scroll(receipts_table.control)),
        ],
        expand=True, scroll=ft.ScrollMode.AUTO,
    )
