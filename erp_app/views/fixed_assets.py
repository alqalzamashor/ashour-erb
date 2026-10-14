import datetime
import flet as ft
from .. import services, theme
from ..report_export import export_excel, export_pdf
from ._asset_stickers import open_sticker_dialog

STATE_LABELS = {'active': 'نشط', 'fully_depreciated': 'مستهلك بالكامل', 'disposed': 'مستبعد'}
STATE_COLORS = {'active': None, 'fully_depreciated': 'theme.WARNING', 'disposed': 'theme.DANGER'}


def build_fixed_assets(page: ft.Page):
    # ---------------- فورم إضافة/تعديل أصل ----------------
    code_field = ft.TextField(label='الكود (اختياري - من تسلسل الفئة لو فاضي)', width=220)
    name_field = ft.TextField(label='اسم الأصل', width=260)
    cats = {str(c.id): c for c in services.list_asset_categories()}

    def cat_options(include_id=None):
        return [(cid, c.name) for cid, c in cats.items() if c.is_active or cid == str(include_id or '')]

    category_dd = theme.SearchableDropdown(label='فئة الأصل *', width=240, options=cat_options())
    cat_info = ft.Text('', size=12, color=theme.TEXT_MUTED)

    def show_cat_info(e=None):
        c = cats.get(category_dd.value or '')
        if not c:
            cat_info.value = 'اختار الفئة - الحسابات والعمر الإنتاجي والقيمة التخريدية بتتاخد منها تلقائيًا (من شاشة فئات الأصول الثابتة).'
        else:
            cat_info.value = (f'من الفئة: أصل {c.asset_account.code if c.asset_account else "-"} | مجمّع {c.accumulated_depreciation_account.code if c.accumulated_depreciation_account else "-"}'
                              f' | مصروف {c.depreciation_expense_account.code if c.depreciation_expense_account else "-"}'
                              f' | العمر {c.useful_life_months} شهر | تخريدية {c.salvage_percent:g}%'
                              + (f' | الكود التالي: {c.next_code}' if getattr(c, 'next_code', None) else ' | الكود: تسلسل عام FA-'))
        page.update()

    orig_category = {'value': None}

    def on_cat_change(e=None):
        # لو بنعدّل أصل وغيّرنا فئته: نفضّي العمر والقيمة التخريدية عشان يرثوا من الفئة الجديدة
        if editing_asset_id['value'] and (category_dd.value or None) != orig_category['value']:
            life_field.value = ''; salvage_field.value = ''
        show_cat_info()

    category_dd.on_change = on_cat_change
    date_field = theme.DateField('تاريخ الشراء', page, width=160, value=datetime.date.today().strftime('%Y-%m-%d'))
    cost_field = ft.TextField(label='التكلفة', width=140, keyboard_type=ft.KeyboardType.NUMBER)
    salvage_field = ft.TextField(label='قيمة تخريدية (اختياري)', width=190, hint_text='فاضي = من الفئة', keyboard_type=ft.KeyboardType.NUMBER)
    life_field = ft.TextField(label='عمر إنتاجي بالشهور (اختياري)', width=210, hint_text='فاضي = من الفئة', keyboard_type=ft.KeyboardType.NUMBER)
    notes_field = ft.TextField(label='ملاحظات', width=400)
    asset_error = ft.Text('', color=theme.DANGER, visible=False)
    editing_asset_id = {'value': None}

    def _asset_row(a):
        state_label = STATE_LABELS.get(a.state, a.state)
        state_color = {'active': theme.SUCCESS, 'fully_depreciated': theme.WARNING, 'disposed': theme.DANGER}.get(a.state, None)
        actions = ft.Row(spacing=2)
        actions.controls.append(ft.IconButton(icon=ft.Icons.QR_CODE_2, tooltip='طباعة استيكر الباركود',
                                              on_click=lambda e, aid=a.id, code=a.code: open_sticker_dialog(page, [aid], f'استيكر الأصل {code}')))
        if a.state != 'disposed':
            actions.controls.append(ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل', on_click=lambda e, aid=a.id: open_edit_asset(aid)))
            actions.controls.append(ft.IconButton(icon=ft.Icons.DELETE_SWEEP_OUTLINED, tooltip='استبعاد الأصل', icon_color=theme.DANGER, on_click=lambda e, aid=a.id: open_dispose(aid)))
        visible_ids.append(a.id)
        row = ft.DataRow(selected=a.id in selected_ids, on_select_change=lambda e, aid=a.id: toggle_asset(aid), cells=[
            ft.DataCell(ft.Text(a.code)),
            ft.DataCell(ft.Text(a.name)),
            ft.DataCell(ft.Text(a.category or '-')),
            ft.DataCell(ft.Text(f'{a.cost:,.2f}')),
            ft.DataCell(ft.Text(f'{a.accumulated_depreciation:,.2f}')),
            ft.DataCell(ft.Text(f'{a.net_book_value:,.2f}', weight=ft.FontWeight.BOLD)),
            ft.DataCell(ft.Text(f'{a.monthly_depreciation:,.2f}')),
            ft.DataCell(ft.Text(state_label, color=state_color, weight=ft.FontWeight.BOLD)),
            ft.DataCell(actions),
        ])
        row_by_id[a.id] = row
        return row

    assets_table_sortable = theme.SortableDataTable(
        columns=[
            ('الكود', lambda a: a.code), ('الاسم', lambda a: a.name), ('الفئة', lambda a: a.category),
            ('التكلفة', lambda a: a.cost, True), ('مجمّع الإهلاك', lambda a: a.accumulated_depreciation, True),
            ('صافي القيمة الدفترية', lambda a: a.net_book_value, True), ('القسط الشهري', lambda a: a.monthly_depreciation, True),
            ('الحالة', lambda a: a.state), ('', None),
        ],
        row_builder=_asset_row, page=page,
        show_checkbox_column=True, on_select_all=lambda e: select_all(e),
    )
    assets_table = assets_table_sortable.control
    selected_ids = set()          # الأصول المحددة لطباعة الاستيكرات
    visible_ids = []              # الأصول الظاهرة حاليًا (بعد البحث)
    row_by_id = {}
    selected_label = ft.Text('', size=12, color=theme.TEXT_MUTED)
    search_field = ft.TextField(
        label='بحث بالكود أو الاسم - أو امسح الباركود بالماسح الضوئي ثم Enter', width=520,
        prefix_icon=ft.Icons.QR_CODE_SCANNER, border_radius=10,
    )

    def update_selected_label():
        selected_label.value = f'المحدد للطباعة: {len(selected_ids)}' if selected_ids else 'حدّد أصول من الجدول لطباعة استيكراتها، أو اختار نطاق من زرار الطباعة'

    def toggle_asset(asset_id):
        if asset_id in selected_ids:
            selected_ids.discard(asset_id)
        else:
            selected_ids.add(asset_id)
        if asset_id in row_by_id:
            row_by_id[asset_id].selected = asset_id in selected_ids
        update_selected_label()
        page.update()

    def select_all(e):
        checked = str(getattr(e, 'data', '')).lower() == 'true'
        for aid in visible_ids:
            (selected_ids.add if checked else selected_ids.discard)(aid)
            if aid in row_by_id:
                row_by_id[aid].selected = checked
        update_selected_label()
        page.update()

    def clear_asset_form():
        code_field.value = ''; name_field.value = ''
        category_dd.options = cat_options(); category_dd.value = None
        date_field.value = datetime.date.today().strftime('%Y-%m-%d')
        cost_field.value = ''; salvage_field.value = ''; life_field.value = ''
        notes_field.value = ''
        asset_error.visible = False
        show_cat_info()

    def refresh_assets(e=None):
        fresh = {str(c.id): c for c in services.list_asset_categories()}   # الكود التالي اتغيّر بعد الحفظ
        cats.clear(); cats.update(fresh)
        visible_ids.clear(); row_by_id.clear()
        assets_table_sortable.set_data(services.list_fixed_assets(search=(search_field.value or '').strip() or None))
        update_selected_label()
        page.update()

    def on_search_submit(e):
        """Enter بعد مسح الباركود: لو الكود مطابق تمامًا لأصل بيفتح الأصل ده على طول."""
        code = (search_field.value or '').strip()
        refresh_assets()
        if not code:
            return
        exact = [a for a in services.list_fixed_assets(search=code) if a.code.lower() == code.lower()]
        if not exact:
            page.overlay.append(ft.SnackBar(ft.Text(f'مفيش أصل بالكود "{code}"'), open=True)); page.update()
        elif exact[0].state == 'disposed':
            page.overlay.append(ft.SnackBar(ft.Text(f'الأصل {exact[0].code} ({exact[0].name}) مستبعد'), open=True)); page.update()
        else:
            open_edit_asset(exact[0].id)

    search_field.on_change = refresh_assets
    search_field.on_submit = on_search_submit

    def save_asset(e):
        try:
            purchase_date = datetime.datetime.strptime(date_field.value, '%Y-%m-%d')
            if not category_dd.value:
                raise ValueError('اختار فئة الأصل')
            kwargs = dict(
                code=code_field.value or '', name=name_field.value or '', category_id=int(category_dd.value),
                purchase_date=purchase_date, cost=float(cost_field.value or 0),
                salvage_value=float(salvage_field.value) if (salvage_field.value or '').strip() else None,
                useful_life_months=int(life_field.value) if (life_field.value or '').strip() else None,
                notes=notes_field.value or '',
            )
            if editing_asset_id['value']:
                services.update_fixed_asset(editing_asset_id['value'], **kwargs)
            else:
                services.create_fixed_asset(**kwargs)
            clear_asset_form()
            editing_asset_id['value'] = None
            asset_dialog.open = False
            page.update()
            refresh_assets()
        except Exception as ex:
            asset_error.value = str(ex); asset_error.visible = True; page.update()

    asset_dialog = ft.AlertDialog(
        modal=True, title=ft.Text('أصل ثابت جديد'),
        content=ft.Container(
            width=650,
            content=ft.Column([
                ft.Text('اختار فئة الأصل بس - الحسابات والعمر الإنتاجي والقيمة التخريدية بتتاخد منها. تقدر تغلبهم لأصل معيّن من الحقلين الاختياريين.', color=theme.TEXT_MUTED, size=12),
                ft.Row([name_field, code_field, category_dd.control], wrap=True),
                cat_info,
                ft.Row([date_field.control, cost_field], wrap=True),
                ft.Row([life_field, salvage_field], wrap=True),
                notes_field,
                asset_error,
            ], spacing=10, tight=True, scroll=ft.ScrollMode.AUTO),
            height=440,
        ),
        actions=[
            ft.TextButton('إلغاء', on_click=lambda e: (setattr(asset_dialog, 'open', False), page.update())),
            ft.FilledButton('حفظ الأصل', bgcolor=theme.PRIMARY, on_click=save_asset),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(asset_dialog)

    def open_add_asset(e=None):
        clear_asset_form()
        editing_asset_id['value'] = None
        asset_dialog.title = ft.Text('أصل ثابت جديد')
        asset_dialog.open = True
        page.update()

    def open_edit_asset(asset_id):
        a = services.get_fixed_asset(asset_id)
        if not a:
            return
        editing_asset_id['value'] = asset_id
        code_field.value = a.code; name_field.value = a.name
        category_dd.options = cat_options(a.category_id); category_dd.value = str(a.category_id) if a.category_id else None
        orig_category['value'] = category_dd.value
        date_field.value = a.purchase_date.strftime('%Y-%m-%d')
        cost_field.value = f'{a.cost:g}'
        # القيم اللي بتساوي اللي الفئة هتديها تلقائيًا نسيبها فاضية (عشان تتحسب من الفئة لو اتغيّرت التكلفة)
        c = cats.get(str(a.category_id)) if a.category_id else None
        life_inherited = bool(c) and a.useful_life_months == c.useful_life_months
        salvage_inherited = bool(c) and abs((a.salvage_value or 0) - round(a.cost * (c.salvage_percent or 0) / 100.0, 2)) < 0.01
        life_field.value = '' if life_inherited else str(a.useful_life_months)
        salvage_field.value = '' if salvage_inherited else f'{a.salvage_value:g}'
        notes_field.value = a.notes or ''
        asset_error.visible = False
        show_cat_info()
        asset_dialog.title = ft.Text(f'تعديل الأصل {a.code}')
        asset_dialog.open = True
        page.update()

    def open_dispose(asset_id):
        a = services.get_fixed_asset(asset_id)
        dispose_date = theme.DateField('تاريخ الاستبعاد', page, width=160, value=datetime.date.today().strftime('%Y-%m-%d'))
        dispose_amount = ft.TextField(label='قيمة البيع/الاستبعاد (0 لو تلف بدون مقابل)', width=260, value='0', keyboard_type=ft.KeyboardType.NUMBER)
        d_err = ft.Text('', color=theme.DANGER, visible=False)

        def confirm(e):
            try:
                d = datetime.datetime.strptime(dispose_date.value, '%Y-%m-%d')
                services.dispose_fixed_asset(asset_id, d, float(dispose_amount.value or 0))
                dispose_dialog.open = False
                page.update()
                refresh_assets()
            except Exception as ex:
                d_err.value = str(ex); d_err.visible = True; page.update()

        dispose_dialog = ft.AlertDialog(
            modal=True, title=ft.Text(f'استبعاد الأصل: {a.name}'),
            content=ft.Column([
                ft.Text(f'صافي القيمة الدفترية الحالية: {a.net_book_value:,.2f}', weight=ft.FontWeight.BOLD),
                dispose_date.control, dispose_amount, d_err,
            ], tight=True, spacing=10),
            actions=[
                ft.TextButton('تراجع', on_click=lambda e: (setattr(dispose_dialog, 'open', False), page.update())),
                ft.FilledButton('تأكيد الاستبعاد', bgcolor=theme.DANGER, on_click=confirm),
            ],
        )
        page.overlay.append(dispose_dialog)
        dispose_dialog.open = True
        page.update()

    # ---------------- دورات الإهلاك ----------------
    dep_month_dd = ft.Dropdown(label='الشهر', width=140, options=[ft.dropdown.Option(str(m), str(m)) for m in range(1, 13)], value=str(datetime.datetime.now().month))
    dep_year_field = ft.TextField(label='السنة', width=100, value=str(datetime.datetime.now().year), keyboard_type=ft.KeyboardType.NUMBER)
    dep_err = ft.Text('', color=theme.DANGER, visible=False)

    dep_runs_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text('رقم الدورة')), ft.DataColumn(ft.Text('الشهر/السنة')),
            ft.DataColumn(ft.Text('عدد الأصول')), ft.DataColumn(ft.Text('إجمالي الإهلاك')),
            ft.DataColumn(ft.Text('الحالة')), ft.DataColumn(ft.Text('')),
        ],
        rows=[],
    )

    def refresh_dep_runs(e=None):
        rows = []
        for r in services.list_depreciation_runs():
            state_label = 'مرحّلة' if r.state == 'posted' else 'مسودة'
            state_color = theme.SUCCESS if r.state == 'posted' else theme.WARNING
            total = sum(it.amount or 0 for it in r.items)
            actions = ft.Row(spacing=2)
            actions.controls.append(ft.IconButton(icon=ft.Icons.VISIBILITY_OUTLINED, tooltip='عرض/ترحيل', on_click=lambda e, rid=r.id: open_dep_run_dialog(rid)))
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(r.number)),
                ft.DataCell(ft.Text(f'{r.month}/{r.year}')),
                ft.DataCell(ft.Text(str(len(r.items)))),
                ft.DataCell(ft.Text(f'{total:,.2f}')),
                ft.DataCell(ft.Text(state_label, color=state_color, weight=ft.FontWeight.BOLD)),
                ft.DataCell(actions),
            ]))
        dep_runs_table.rows = rows
        page.update()

    def create_dep_run(e):
        try:
            rid = services.create_depreciation_run(int(dep_month_dd.value), int(dep_year_field.value))
            dep_err.visible = False
            refresh_dep_runs()
            open_dep_run_dialog(rid)
        except Exception as ex:
            dep_err.value = str(ex); dep_err.visible = True; page.update()

    def open_dep_run_dialog(run_id):
        run = services.get_depreciation_run(run_id)
        if not run:
            return
        item_table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text('الأصل')), ft.DataColumn(ft.Text('القسط')), ft.DataColumn(ft.Text('حساب المصروف')), ft.DataColumn(ft.Text('حساب المجمّع'))],
            rows=[
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(it.asset.name if it.asset else '-')),
                    ft.DataCell(ft.Text(f'{it.amount:,.2f}')),
                    ft.DataCell(ft.Text(it.expense_account.name if it.expense_account else '-', size=11)),
                    ft.DataCell(ft.Text(it.accumulated_account.name if it.accumulated_account else '-', size=11)),
                ]) for it in run.items
            ],
        )
        total = sum(it.amount or 0 for it in run.items)
        summary = ft.Text(f'عدد الأصول: {len(run.items)}   |   إجمالي الإهلاك: {total:,.2f}', weight=ft.FontWeight.BOLD)
        d_err = ft.Text('', color=theme.DANGER, visible=False)

        def post_run(e):
            try:
                services.post_depreciation_run(run.id)
                dep_dialog.open = False; page.update()
                refresh_dep_runs(); refresh_assets()
            except Exception as ex:
                d_err.value = str(ex); d_err.visible = True; page.update()

        def reopen_run(e):
            try:
                services.reopen_depreciation_run(run.id)
                dep_dialog.open = False; page.update()
                refresh_dep_runs(); refresh_assets()
            except Exception as ex:
                d_err.value = str(ex); d_err.visible = True; page.update()

        def delete_run(e):
            try:
                services.delete_depreciation_run(run.id)
                dep_dialog.open = False; page.update()
                refresh_dep_runs()
            except Exception as ex:
                d_err.value = str(ex); d_err.visible = True; page.update()

        def export_run(kind):
            try:
                rows = [{'code': it.asset.code if it.asset else '-', 'name': it.asset.name if it.asset else '-', 'amount': it.amount} for it in run.items]
                path = (export_excel if kind == 'xlsx' else export_pdf)({'rows': rows}, 'depreciation', services.downloads_dir())
                theme.open_or_download_file(page, path)
                page.overlay.append(ft.SnackBar(ft.Text(f'تم إنشاء الملف: {path}'), open=True)); page.update()
            except Exception as ex:
                page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

        actions = [ft.TextButton('إغلاق', on_click=lambda e: (setattr(dep_dialog, 'open', False), page.update()))]
        if run.state == 'draft':
            actions += [ft.TextButton('حذف الدورة', on_click=delete_run), ft.FilledButton('ترحيل الدورة', icon=ft.Icons.CHECK_CIRCLE, bgcolor=theme.PRIMARY, on_click=post_run)]
        else:
            actions += [ft.OutlinedButton('إرجاع لمسودة', icon=ft.Icons.UNDO, on_click=reopen_run)]
        actions += [ft.OutlinedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export_run('xlsx')), ft.OutlinedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export_run('pdf'))]

        dep_dialog = ft.AlertDialog(
            modal=True, title=ft.Text(f'دورة إهلاك {run.month}/{run.year} — {run.number} ({"مرحّلة" if run.state=="posted" else "مسودة"})'),
            content=ft.Container(width=650, height=380, content=ft.Column([summary, ft.Divider(), theme.h_scroll(item_table), d_err], spacing=10, tight=True, scroll=ft.ScrollMode.AUTO)),
            actions=actions, actions_alignment=ft.MainAxisAlignment.END,
        )
        page.overlay.append(dep_dialog)
        dep_dialog.open = True
        page.update()

    refresh_assets()
    refresh_dep_runs()

    assets_card = theme.card(ft.Column([
        ft.Row([
            ft.Text('سجل الأصول الثابتة', size=16, weight=ft.FontWeight.BOLD),
            ft.Container(expand=True),
            ft.OutlinedButton('طباعة استيكرات الباركود', icon=ft.Icons.QR_CODE_2,
                              on_click=lambda e: open_sticker_dialog(page, scope_picker=True, selected_ids=lambda: selected_ids)),
            ft.FilledButton('أصل جديد', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=open_add_asset),
        ]),
        ft.Row([search_field, selected_label], wrap=True, spacing=16),
        theme.h_scroll(assets_table),
    ]), expand=True)

    dep_card = theme.card(ft.Column([
        ft.Text('دورة إهلاك جديدة', size=16, weight=ft.FontWeight.BOLD),
        ft.Text('بتولّد بند تلقائي لكل أصل نشط لسه محتاج إهلاك، بقيمة القسط الشهري (طريقة القسط الثابت) أو الباقي المتبقي أيهما أقل.', color=theme.TEXT_MUTED),
        ft.Row([dep_month_dd, dep_year_field, theme.guard_submit(ft.FilledButton('إنشاء الدورة', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=create_dep_run))]),
        dep_err,
        ft.Divider(),
        ft.Text('دورات الإهلاك', size=14, weight=ft.FontWeight.BOLD),
        theme.h_scroll(dep_runs_table),
    ], spacing=10))

    return ft.Column(
        [
            theme.page_title('الأصول الثابتة', 'سجل الأصول الثابتة والإهلاك الشهري بطريقة القسط الثابت'),
            ft.Container(height=12),
            assets_card,
            ft.Container(height=16),
            dep_card,
        ],
        expand=True, scroll=ft.ScrollMode.AUTO,
    )
