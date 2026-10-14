import flet as ft
from .. import services, theme


def build_asset_categories(page: ft.Page):
    """فئات الأصول الثابتة - جدول بيربط كل فئة بحساباتها الثلاثة (الأصل،
    مجمّع الإهلاك، مصروف الإهلاك) والعمر الإنتاجي ونسبة القيمة التخريدية،
    عشان الأصل يختار الفئة بس وميدخلش الحسابات كل مرة."""
    postable = services.list_accounts(postable_only=True)
    acct_options = [(str(a.id), f'{a.code} - {a.name}') for a in postable]

    name_field = ft.TextField(label='اسم الفئة', width=280, autofocus=True)
    life_field = ft.TextField(label='العمر الإنتاجي (شهور)', width=180, value='60', keyboard_type=ft.KeyboardType.NUMBER)
    salvage_field = ft.TextField(label='القيمة التخريدية % من التكلفة', width=230, value='0', keyboard_type=ft.KeyboardType.NUMBER)
    asset_dd = theme.SearchableDropdown(label='حساب الأصل *', width=400, options=acct_options)
    accum_dd = theme.SearchableDropdown(label='حساب مجمّع الإهلاك *', width=400, options=acct_options)
    expense_dd = theme.SearchableDropdown(label='حساب مصروف الإهلاك *', width=400, options=acct_options)
    code_field = ft.TextField(label='بداية تسلسل الكود (أول كود)', hint_text='مثال: LAP-0001 أو 1001', width=300)
    code_hint = ft.Text('اكتب أول كود للفئة دي والبرنامج بيكمل التسلسل تلقائيًا (LAP-0001 ← LAP-0002 ...). فاضي = الأصول بتاخد التسلسل العام FA-.', size=11, color=theme.TEXT_MUTED)
    active_sw = ft.Switch(label='فئة نشطة (تظهر في اختيار الأصول)', value=True)
    form_err = ft.Text('', color=theme.DANGER, visible=False)
    editing = {'id': None}

    def acc_text(a):
        return f'{a.code} - {a.name}' if a else '-'

    def _category_row(c):
        actions = ft.Row(spacing=0, controls=[
            ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل', on_click=lambda e, cid=c.id: open_edit(cid)),
            ft.IconButton(icon=ft.Icons.SYNC_ALT, tooltip='تطبيق حسابات الفئة على أصولها', on_click=lambda e, cid=c.id: apply_accounts(cid)),
            ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف', on_click=lambda e, cid=c.id: delete(cid)),
        ])
        return ft.DataRow(cells=[
            ft.DataCell(ft.Text(c.name, weight=ft.FontWeight.BOLD)),
            ft.DataCell(ft.Text(c.code_start or 'FA- (عام)', size=12)),
            ft.DataCell(ft.Text(c.next_code or '-', size=12, weight=ft.FontWeight.BOLD)),
            ft.DataCell(ft.Text(acc_text(c.asset_account), size=12)),
            ft.DataCell(ft.Text(acc_text(c.accumulated_depreciation_account), size=12)),
            ft.DataCell(ft.Text(acc_text(c.depreciation_expense_account), size=12)),
            ft.DataCell(ft.Text(str(c.useful_life_months))),
            ft.DataCell(ft.Text(f'{c.salvage_percent:g}%')),
            ft.DataCell(ft.Text('نشطة' if c.is_active else 'موقوفة', color=theme.SUCCESS if c.is_active else theme.WARNING)),
            ft.DataCell(actions),
        ])

    table_sortable = theme.SortableDataTable(
        columns=[('الفئة', lambda c: c.name), ('بداية التسلسل', lambda c: c.code_start), ('الكود التالي', lambda c: c.next_code),
                 ('حساب الأصل', None), ('مجمّع الإهلاك', None), ('مصروف الإهلاك', None),
                 ('العمر (شهور)', lambda c: c.useful_life_months, True), ('قيمة تخريدية %', lambda c: c.salvage_percent, True),
                 ('الحالة', lambda c: c.is_active), ('', None)],
        row_builder=_category_row, page=page,
    )
    table = table_sortable.control

    def refresh(e=None):
        table_sortable.set_data(services.list_asset_categories())

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def clear_form():
        name_field.value = ''; life_field.value = '60'; salvage_field.value = '0'; code_field.value = ''
        asset_dd.value = None; accum_dd.value = None; expense_dd.value = None
        active_sw.value = True; form_err.visible = False

    def save(e):
        try:
            args = dict(
                name=name_field.value, useful_life_months=int(life_field.value or 0), salvage_percent=float(salvage_field.value or 0),
                code_start=code_field.value,
                asset_account_id=int(asset_dd.value) if asset_dd.value else None,
                accumulated_depreciation_account_id=int(accum_dd.value) if accum_dd.value else None,
                depreciation_expense_account_id=int(expense_dd.value) if expense_dd.value else None,
            )
            if editing['id']:
                services.update_asset_category(editing['id'], is_active=active_sw.value, **args)
            else:
                services.create_asset_category(**args)
            dialog.open = False
            page.update()
            refresh()
        except Exception as ex:
            form_err.value = str(ex); form_err.visible = True; page.update()

    dialog = ft.AlertDialog(
        modal=True, title=ft.Text('فئة أصول جديدة'),
        content=ft.Container(width=460, height=480, content=ft.Column([
            ft.Text('الحسابات والعمر والقيمة التخريدية اللي هنا بتتطبق تلقائيًا على أي أصل يتسجّل بالفئة دي.', color=theme.TEXT_MUTED, size=12),
            name_field, code_field, code_hint, ft.Row([life_field, salvage_field], wrap=True),
            asset_dd.control, accum_dd.control, expense_dd.control, active_sw, form_err,
        ], spacing=10, tight=True, scroll=ft.ScrollMode.AUTO)),
        actions=[ft.TextButton('إلغاء', on_click=lambda e: (setattr(dialog, 'open', False), page.update())),
                 ft.FilledButton('حفظ الفئة', bgcolor=theme.PRIMARY, on_click=save)],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(dialog)

    def open_add(e=None):
        clear_form(); editing['id'] = None
        dialog.title = ft.Text('فئة أصول جديدة'); dialog.open = True; page.update()

    def open_edit(cid):
        c = services.get_asset_category(cid)
        if not c:
            return
        editing['id'] = cid
        name_field.value = c.name; life_field.value = str(c.useful_life_months); salvage_field.value = f'{c.salvage_percent:g}'
        code_field.value = c.code_start or ''
        asset_dd.value = str(c.asset_account_id) if c.asset_account_id else None
        accum_dd.value = str(c.accumulated_depreciation_account_id) if c.accumulated_depreciation_account_id else None
        expense_dd.value = str(c.depreciation_expense_account_id) if c.depreciation_expense_account_id else None
        active_sw.value = bool(c.is_active); form_err.visible = False
        dialog.title = ft.Text(f'تعديل الفئة: {c.name}'); dialog.open = True; page.update()

    def apply_accounts(cid):
        try:
            updated, skipped = services.apply_asset_category_accounts(cid)
            msg = f'اتطبّقت حسابات الفئة على {updated} أصل'
            if skipped:
                msg += f' - واتخطّى {skipped} أصل (عليها إهلاك أو فاتورة شراء)'
            snack(msg)
        except Exception as ex:
            snack(str(ex))

    def delete(cid):
        try:
            services.delete_asset_category(cid)
            refresh()
        except Exception as ex:
            snack(str(ex))

    refresh()
    return ft.Column([
        theme.page_title('فئات الأصول الثابتة', 'اربط كل فئة بحساباتها وعمرها الإنتاجي وقيمتها التخريدية مرة واحدة، والأصول بتختار الفئة بس'),
        ft.Container(height=12),
        theme.card(ft.Column([
            ft.Row([ft.Text('الفئات', size=16, weight=ft.FontWeight.BOLD), ft.Container(expand=True),
                    ft.FilledButton('فئة جديدة', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=open_add)]),
            ft.Text('تعديل حسابات فئة بيسري على الأصول الجديدة بس، والأصول الحالية بتفضل بحساباتها لحد ما تدوس أيقونة التطبيق (⇄) '
                    'عشان القيود اللي اترحّلت قبل كده ما تتلخبطش.', color=theme.TEXT_MUTED, size=12),
            theme.h_scroll(table),
        ], spacing=10), expand=True),
    ], expand=True, scroll=ft.ScrollMode.AUTO)
