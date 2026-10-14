import datetime
import flet as ft
from .. import services, theme
from ._doc_grid import DocGrid, doc_datetime


def build_manufacturing(page: ft.Page):
    """أوامر التصنيع: التاريخ والمخزن فوق، والأصناف المصنَّعة وكمياتها في جدول (مع حالة توفر المكونات وتكلفتها التقديرية لكل سطر)."""
    manufactured = [p for p in services.list_products() if p.product_type == 'manufactured']
    locations = services.list_locations()

    date_f = theme.DateField('تاريخ الإنتاج *', page, width=170, value=datetime.date.today().strftime('%Y-%m-%d'))
    location_dd = ft.Dropdown(label='المخزن', width=220, options=[ft.dropdown.Option(str(l.id), l.name) for l in locations], value=str(services.default_location_id() or ''))
    notes_field = ft.TextField(label='ملاحظات', width=280)
    confirm_now = ft.Switch(label='تأكيد الأوامر فورًا (استهلاك المكونات وإنتاج الأصناف)', value=False)
    err = ft.Text('', color=theme.DANGER, visible=False)
    summary = ft.Text('', weight=ft.FontWeight.BOLD)

    def evaluate(e=None):
        """حالة كل سطر: المكونات المطلوبة مجمّعة على كل السطور (لو نفس المكوّن في أكتر من صنف) مقابل رصيد المخزن."""
        loc_id = int(location_dd.value) if location_dd.value else None
        lines = [ln for ln in grid.lines if ln.product_id]
        need, explosions = {}, {}
        for ln in lines:
            if ln.qty <= 0:
                continue
            try:
                bom = services.get_bom_explosion(ln.product_id, ln.qty)
            except Exception:
                bom = []
            explosions[id(ln)] = bom
            for l in bom:
                need[l['component_id']] = need.get(l['component_id'], 0.0) + l['quantity']
        balances = {cid: (services.get_product_balance(cid, loc_id) if loc_id else 0.0) for cid in need}
        total_cost = 0.0
        for ln in lines:
            bom = explosions.get(id(ln))
            if bom is None:
                ln.set_static('status', '-'); ln.set_static('cost', ''); continue
            if not bom:
                ln.set_static('status', '✗ مفيش مكونات معرَّفة', theme.DANGER); ln.set_static('cost', ''); continue
            short = [f"{l['component'].name}: المتاح {balances[l['component_id']]:g} / المطلوب {need[l['component_id']]:g}" for l in bom if balances[l['component_id']] + 1e-9 < need[l['component_id']]]
            cost = sum(l['quantity'] * (l['component'].cost_price or 0) for l in bom)
            total_cost += cost
            if short:
                ln.set_static('status', '✗ ناقص: ' + '، '.join(s.split(':')[0] for s in short), theme.DANGER, '\n'.join(short))
            else:
                ln.set_static('status', '✓ المكونات متاحة', theme.SUCCESS)
            ln.set_static('cost', f'{cost:,.2f}')
        summary.value = f'عدد الأصناف: {len(lines)}   |   تكلفة المكونات التقديرية: {total_cost:,.2f}' if lines else 'أضف الأصناف المراد تصنيعها في الجدول'
        try:
            page.update()
        except Exception:
            pass

    grid = DocGrid(page, [
        {'key': 'i', 'title': '#', 'width': 34, 'kind': 'index'}, {'key': 'p', 'title': 'الصنف المُصنَّع', 'width': 320, 'kind': 'product'},
        {'key': 'q', 'title': 'الكمية', 'width': 100, 'kind': 'qty'}, {'key': 'status', 'title': 'حالة المكونات', 'width': 330, 'kind': 'static'},
        {'key': 'cost', 'title': 'تكلفة المكونات', 'width': 130, 'kind': 'static'}, {'key': 'd', 'title': '', 'width': 46, 'kind': 'delete'},
    ], on_line=lambda ln: None, on_change=evaluate, rows_height=290)
    grid.set_products(manufactured)

    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(c)) for c in ['رقم الأمر', 'الصنف', 'الكمية', 'المخزن', 'التاريخ', 'الحالة', '']], rows=[])

    def refresh_table():
        rows = []
        for o in services.list_production_orders():
            state_label = 'مؤكَّد' if o.state == 'done' else 'مسودة'
            state_color = theme.SUCCESS if o.state == 'done' else theme.WARNING
            actions = ft.Row(spacing=2)
            if o.state == 'draft':
                actions.controls.append(ft.IconButton(icon=ft.Icons.CHECK_CIRCLE_OUTLINE, icon_color=theme.SUCCESS, tooltip='تأكيد الإنتاج', on_click=lambda e, oid=o.id: do_confirm(oid)))
                actions.controls.append(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف', on_click=lambda e, oid=o.id: do_delete(oid)))
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(o.number)), ft.DataCell(ft.Text(o.product.name if o.product else '-')), ft.DataCell(ft.Text(f'{o.quantity:g}')),
                ft.DataCell(ft.Text(o.location.name if o.location else '-')), ft.DataCell(ft.Text(o.date.strftime('%Y-%m-%d'))),
                ft.DataCell(ft.Text(state_label, color=state_color, weight=ft.FontWeight.BOLD)), ft.DataCell(actions)]))
        table.rows = rows
        page.update()

    def do_create(e):
        try:
            if not location_dd.value:
                raise ValueError('اختر المخزن')
            items = [{'product_id': i['product_id'], 'quantity': i['quantity']} for i in grid.get_items()]
            if not items:
                raise ValueError('أضف صنف واحد على الأقل')
            ids = services.create_production_orders(items, int(location_dd.value), notes=notes_field.value or '', order_date=doc_datetime(date_f.value))
            msg = f'تم إنشاء {len(ids)} أمر إنتاج'
            if confirm_now.value:
                failed = []
                for oid in ids:
                    try:
                        services.confirm_production_order(oid)
                    except Exception as ex:
                        failed.append(str(ex))
                msg += f' وتأكيد {len(ids) - len(failed)}' + (f' - تعذّر تأكيد {len(failed)}: {failed[0]}' if failed else '')
            err.visible = False
            grid.clear(); notes_field.value = ''
            refresh_table()
            page.overlay.append(ft.SnackBar(ft.Text(msg), open=True))
        except Exception as ex:
            err.value = str(ex)
            err.visible = True
        page.update()

    def do_confirm(order_id):
        try:
            services.confirm_production_order(order_id)
            refresh_table(); evaluate()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True)); page.update()

    def do_delete(order_id):
        try:
            services.delete_production_order(order_id)
            refresh_table()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True)); page.update()

    location_dd.on_change = evaluate
    refresh_table()
    evaluate()

    form = theme.card(ft.Column([
        ft.Text('أمر إنتاج جديد', size=16, weight=ft.FontWeight.BOLD),
        ft.Text('أضف الأصناف المراد تصنيعها وكمياتها في الجدول (أمر لكل صنف). بيستهلك المكونات حسب BOM كل صنف وينتج الكمية المطلوبة.', color=theme.TEXT_MUTED, size=12),
        ft.Row([date_f.control, location_dd, notes_field], wrap=True, spacing=12),
        theme.h_scroll(grid.control), summary, confirm_now, err,
        theme.guard_submit(ft.FilledButton('إنشاء أوامر الإنتاج', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=do_create)),
    ], spacing=10))

    return ft.Column([
        theme.page_title('التصنيع', 'أوامر الإنتاج بتاريخ الإنتاج - استهلاك المكونات وإنتاج الأصناف التامة'),
        ft.Container(height=12), form, ft.Container(height=16),
        theme.card(ft.Column([ft.Text('أوامر الإنتاج', size=16, weight=ft.FontWeight.BOLD), theme.h_scroll(table)]), expand=True),
    ], expand=True, scroll=ft.ScrollMode.AUTO)
