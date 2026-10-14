import datetime
import flet as ft
from .. import services, theme
from ._doc_grid import DocGrid, doc_datetime

TYPE_LABELS = {'simple': 'عادي', 'kit': 'Kit', 'manufactured': 'مُصنَّع'}
TYPE_COLORS = {'simple': theme.TEXT_MUTED, 'kit': theme.PRIMARY, 'manufactured': theme.WARNING}


def build_damages(page: ft.Page):
    products = [p for p in services.list_products() if p.product_type != 'service']
    locations = services.list_locations()
    postable_accounts = services.list_accounts(postable_only=True)
    cfg = None
    try:
        cfg = services._accounting_settings()
    except Exception:
        cfg = None
    default_account_id = getattr(cfg, 'inventory_loss_account_id', None)
    default_account_text = next((f'{a.code} - {a.name}' for a in postable_accounts if a.id == default_account_id), 'غير محدد في الإعدادات')

    date_f = theme.DateField('تاريخ السند *', page, width=170, value=datetime.date.today().strftime('%Y-%m-%d'))
    location_dd = ft.Dropdown(label='المخزن', width=220, options=[ft.dropdown.Option(str(l.id), l.name) for l in locations], value=str(services.default_location_id() or ''))
    reason_field = ft.TextField(label='سبب التلف (للسند كامل)', width=320)
    err = ft.Text('', color=theme.DANGER, visible=False)
    summary = ft.Text('', weight=ft.FontWeight.BOLD)

    def available_for(p, loc_id):
        """المتاح للإتلاف: رصيد الصنف، أو لو Kit عدد الباقات اللي ممكن تتفكك من رصيد مكوناتها."""
        if p.product_type == 'kit':
            bom = services.get_bom_explosion(p.id, 1)
            if not bom:
                return 0.0
            return min(services.get_product_balance(l['component_id'], loc_id) / l['quantity'] for l in bom if l['quantity'] > 0)
        return services.get_product_balance(p.id, loc_id)

    def item_cost(p, qty):
        if p.product_type == 'kit':
            return sum(l['quantity'] * (l['component'].cost_price or 0) for l in services.get_bom_explosion(p.id, qty))
        return qty * (p.cost_price or 0)

    def on_line(line):
        p = line.product_obj
        if not p:
            return
        line.set_static('type', TYPE_LABELS.get(p.product_type, p.product_type), TYPE_COLORS.get(p.product_type, theme.TEXT_MUTED))
        loc_id = int(location_dd.value) if location_dd.value else None
        if not loc_id:
            line.set_static('avail', '-'); return
        av = available_for(p, loc_id)
        short = line.qty > av + 1e-9
        line.set_static('avail', f'{av:g}' + (' ✗' if short else ''), theme.DANGER if short else theme.SUCCESS,
                        'الكمية أكبر من المتاح' if short else None)

    def update_summary():
        lines = [ln for ln in grid.lines if ln.product_id]
        total = 0.0
        for ln in lines:
            try:
                total += item_cost(ln.product_obj or grid.products[str(ln.product_id)], ln.qty)
            except Exception:
                pass
        summary.value = f'عدد الأصناف: {len(lines)}   |   التكلفة التقديرية للتلف: {total:,.2f}' if lines else 'أضف الأصناف التالفة في الجدول'
        try:
            page.update()
        except Exception:
            pass

    grid = DocGrid(page, [
        {'key': 'i', 'title': '#', 'width': 34, 'kind': 'index'}, {'key': 'p', 'title': 'الصنف', 'width': 320, 'kind': 'product'},
        {'key': 'type', 'title': 'النوع', 'width': 90, 'kind': 'static'}, {'key': 'avail', 'title': 'المتاح بالمخزن', 'width': 130, 'kind': 'static'},
        {'key': 'q', 'title': 'الكمية', 'width': 100, 'kind': 'qty'},
        {'key': 'a', 'title': 'حساب التلف (اختياري)', 'width': 280, 'kind': 'acct', 'hint': f'افتراضي: {default_account_text}'},
        {'key': 'd', 'title': '', 'width': 46, 'kind': 'delete'},
    ], on_line=on_line, on_change=update_summary, rows_height=290,
        acct_options=[('', f'افتراضي ({default_account_text})')] + [(str(a.id), f'{a.code} - {a.name}') for a in postable_accounts])
    grid.set_products(products)

    def _damage_row(r):
        items_text = '، '.join(f'{it.product.name} ({it.quantity:g})' for it in r.items)
        return ft.DataRow(cells=[
            ft.DataCell(ft.Text(r.number)), ft.DataCell(ft.Text(r.date.strftime('%Y-%m-%d'))), ft.DataCell(ft.Text(items_text)),
            ft.DataCell(ft.Text(r.location.name if r.location else '-')), ft.DataCell(ft.Text(f'{r.total_cost:,.2f}')), ft.DataCell(ft.Text(r.reason or '-')),
        ])

    records_table_sortable = theme.SortableDataTable(
        columns=[('رقم السند', lambda r: r.number), ('التاريخ', lambda r: r.date), ('الأصناف', None), ('المخزن', lambda r: r.location.name if r.location else ''),
                 ('التكلفة الإجمالية', lambda r: r.total_cost, True), ('السبب', lambda r: r.reason)],
        row_builder=_damage_row, page=page, initial_sort=1, initial_ascending=False)
    records_table = records_table_sortable.control

    def refresh_records():
        records_table_sortable.set_data(services.list_damage_records())

    def do_save(e):
        try:
            if not location_dd.value:
                raise ValueError('اختر المخزن')
            items = grid.get_items()
            if not items:
                raise ValueError('أضف صنف واحد على الأقل للسند')
            services.create_damage_entry(items, int(location_dd.value), reason=reason_field.value or '', damage_date=doc_datetime(date_f.value))
            err.visible = False
            grid.clear(); reason_field.value = ''
            refresh_records()
            page.overlay.append(ft.SnackBar(ft.Text('تم تسجيل سند التلف بنجاح وتحديث المخزون والحسابات'), open=True))
        except Exception as ex:
            err.value = str(ex)
            err.visible = True
        page.update()

    location_dd.on_change = lambda e: grid.recalc_all()
    refresh_records()
    update_summary()

    form = theme.card(ft.Column([
        ft.Text('سند تلف جديد', size=16, weight=ft.FontWeight.BOLD),
        ft.Text('أضف الأصناف في الجدول (Enter بينقلك للسطر اللي بعده). لكل صنف حساب تلف اختياري، ولو سبته فاضي هيستخدم الحساب الافتراضي '
                f'({default_account_text}). صنف الـ Kit بيتفكك لمكوناته الفعلية عند الترحيل.', color=theme.TEXT_MUTED, size=12),
        ft.Row([date_f.control, location_dd, reason_field], wrap=True, spacing=12),
        theme.h_scroll(grid.control),
        summary, err,
        theme.guard_submit(ft.FilledButton('ترحيل سند التلف', icon=ft.Icons.DELETE_FOREVER_OUTLINED, bgcolor=theme.DANGER, on_click=do_save)),
    ], spacing=10))

    return ft.Column([
        theme.page_title('التوالف', 'تسجيل تلف صنف أو أكتر دفعة واحدة، بتاريخ السند وبحساب تلف قابل للتخصيص لكل صنف'),
        ft.Container(height=12), form, ft.Container(height=16),
        theme.card(ft.Column([ft.Text('سجل سندات التلف', size=16, weight=ft.FontWeight.BOLD), theme.h_scroll(records_table)]), expand=True),
    ], expand=True, scroll=ft.ScrollMode.AUTO)
