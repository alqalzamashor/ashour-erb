import flet as ft
from .. import services, theme


def build_pos_terminals(page: ft.Page):
    """ماكينات نقاط البيع: كل ماكينة مربوطة بفرع ومركز تكلفة ومخزن وموظف (الكاشير) ومستخدم مسموح له وطرق دفع معيّنة وعميل افتراضي.
    الفواتير اللي بتتعمل من شاشة نقاط البيع بتاخد بيانات الماكينة المختارة وبتتسجّل عليها."""
    branches = services.list_branches(True)
    centers = services.list_cost_centers(True)
    locations = services.list_locations()
    employees = services.list_employees(active_only=True)
    customers = services.list_customers()
    methods = services.list_payment_methods(active_only=True)
    users = [u for u in services.list_users() if u.is_active]
    cards = ft.Row(wrap=True, spacing=12)

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def close(d):
        d.open = False; page.update()

    def money(v):
        return f'{v:,.2f}'

    # ===================================================================== القايمة
    def row_builder(t):
        sm = state['summary'].get(t['id'])
        pm_text = '، '.join(m['name'] for m in t['payment_methods']) or '-'
        acts = [ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل', on_click=lambda e, x=t: open_form(x['id'])),
                ft.IconButton(icon=ft.Icons.PAUSE_CIRCLE_OUTLINE if t['is_active'] else ft.Icons.PLAY_CIRCLE_OUTLINE, tooltip='إيقاف' if t['is_active'] else 'تفعيل',
                              icon_color=theme.WARNING if t['is_active'] else theme.SUCCESS, on_click=lambda e, x=t: toggle(x)),
                ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف', on_click=lambda e, x=t: confirm_delete(x))]
        return ft.DataRow(color=None if t['is_active'] else '#F4F4F8', cells=[
            ft.DataCell(ft.Text(t['code'], weight=ft.FontWeight.BOLD)),
            ft.DataCell(ft.Column([ft.Text(t['name'], weight=ft.FontWeight.BOLD), ft.Text(t['notes'], size=10.5, color=theme.TEXT_MUTED)], spacing=0, tight=True)),
            ft.DataCell(ft.Text(t['branch'] or '-')), ft.DataCell(ft.Text(t['cost_center'] or '-')), ft.DataCell(ft.Text(t['location'] or '-')),
            ft.DataCell(ft.Text(t['employee'] or '-')), ft.DataCell(ft.Text(t['assigned_username'] or 'أي مستخدم', color=None if t['assigned_username'] else theme.TEXT_MUTED, size=12)),
            ft.DataCell(ft.Text(pm_text, size=12)), ft.DataCell(ft.Text((t['default_customer'] or '-') + (' (مقفول)' if t['lock_customer'] else ''), size=12)),
            ft.DataCell(ft.Text(f"{sm['count']} فاتورة - {money(sm['total'])}" if sm else '-', size=12)),
            ft.DataCell(ft.Text('نشطة' if t['is_active'] else 'موقوفة', color=theme.SUCCESS if t['is_active'] else theme.TEXT_MUTED, weight=ft.FontWeight.BOLD)),
            ft.DataCell(ft.Row(acts, spacing=0))])

    state = {'summary': {}}
    table = theme.SortableDataTable(columns=[
        ('الكود', lambda t: t['code']), ('الاسم', lambda t: t['name']), ('الفرع', lambda t: t['branch']), ('مركز التكلفة', lambda t: t['cost_center']), ('المخزن', lambda t: t['location']),
        ('الكاشير', lambda t: t['employee']), ('المستخدم', lambda t: t['assigned_username']), ('طرق الدفع', None), ('العميل الافتراضي', lambda t: t['default_customer']),
        ('المبيعات', None), ('الحالة', lambda t: t['is_active']), ('الإجراءات', None)], row_builder=row_builder, page=page, expand=True, column_spacing=14, horizontal_margin=10)

    def refresh(e=None):
        state['summary'] = services.terminal_sales_summary()
        rows = services.list_pos_terminals()
        table.set_data(rows)
        act = [t for t in rows if t['is_active']]
        tot = sum(v['total'] for v in state['summary'].values()); cnt = sum(v['count'] for v in state['summary'].values())
        def card(label, value, color, sub):
            return theme.card(ft.Column([ft.Text(label, size=12, color=theme.TEXT_MUTED), ft.Text(value, size=22, weight=ft.FontWeight.BOLD, color=color), ft.Text(sub, size=11, color=theme.TEXT_MUTED)], spacing=0, tight=True), padding=14)
        cards.controls = [card('الماكينات', str(len(rows)), theme.PRIMARY, f'{len(act)} نشطة'), card('مبيعات الماكينات', money(tot), theme.SUCCESS, f'{cnt} فاتورة (غير الملغاة)'),
                          card('ماكينات مخصصة لمستخدمين', str(len([t for t in rows if t['assigned_username']])), theme.WARNING, 'الباقي متاح لأي مستخدم')]
        if e is not None:
            page.update()

    def toggle(t):
        try:
            services.update_pos_terminal(t['id'], t['code'], t['name'], t['branch_id'], t['cost_center_id'], t['location_id'], t['employee_id'], t['assigned_username'] or None, t['default_customer_id'],
                                         t['lock_customer'], [m['id'] for m in t['payment_methods']], t['default_payment_method_id'], t['receipt_footer'], t['notes'], not t['is_active'])
            refresh(True)
        except Exception as ex:
            snack(str(ex))

    def confirm_delete(t):
        def ok(e):
            try:
                services.delete_pos_terminal(t['id']); close(dlg); refresh(True); snack('تم حذف الماكينة')
            except Exception as ex:
                close(dlg); snack(str(ex))
        dlg = ft.AlertDialog(modal=True, title=ft.Text('حذف الماكينة'), content=ft.Text(f'هتحذف «{t["name"]}». لو اتباع عليها فواتير لازم توقفها بدل الحذف.'),
                             actions=[ft.TextButton('إلغاء', on_click=lambda e: close(dlg)), ft.FilledButton('حذف', bgcolor=theme.DANGER, on_click=ok)])
        page.overlay.append(dlg); dlg.open = True; page.update()

    # ===================================================================== النموذج
    f_code = ft.TextField(label='كود الماكينة *', width=170, hint_text='POS-01')
    f_name = ft.TextField(label='اسم الماكينة *', width=300)
    f_active = ft.Switch(label='نشطة', value=True)
    f_branch = ft.Dropdown(label='الفرع', width=260, options=[ft.dropdown.Option('', 'بدون (الافتراضي)')] + [ft.dropdown.Option(str(b.id), f'{b.code} - {b.name}') for b in branches])
    f_cc = ft.Dropdown(label='مركز التكلفة', width=260, options=[ft.dropdown.Option('', 'بدون (الافتراضي)')] + [ft.dropdown.Option(str(c.id), f'{c.code} - {c.name}') for c in centers])
    f_loc = ft.Dropdown(label='المخزن (اللي بيصرف منه الكاشير)', width=300, options=[ft.dropdown.Option('', 'بدون (الافتراضي)')] + [ft.dropdown.Option(str(l.id), l.name) for l in locations])
    f_emp = theme.SearchableDropdown(label='الموظف (الكاشير)', width=300, options=[(str(e.id), f'{e.code} - {e.name}') for e in employees])
    f_user = ft.Dropdown(label='المستخدم المسموح له', width=260, options=[ft.dropdown.Option('', 'أي مستخدم')] + [ft.dropdown.Option(u.username, f'{u.full_name or u.username} ({u.username})') for u in users])
    f_cust = theme.SearchableDropdown(label='العميل الافتراضي (نقدي)', width=300, options=[(str(c.id), c.name) for c in customers])
    f_lock = ft.Switch(label='منع تغيير العميل (دايمًا الافتراضي)', value=False)
    pm_checks = {m.id: ft.Checkbox(label=m.name + (' (آجل)' if m.is_credit else ''), value=False, width=210) for m in methods}
    f_defpm = ft.Dropdown(label='طريقة الدفع الافتراضية', width=260, options=[])
    f_footer = ft.TextField(label='نص أسفل الإيصال', width=620, hint_text='مثال: شكرًا لزيارتكم - الاسترجاع خلال 3 أيام')
    f_notes = ft.TextField(label='ملاحظات', width=620)
    f_err = ft.Text('', color=theme.DANGER, visible=False, size=12)
    editing = {'id': None}

    def sync_defpm(e=None):
        sel = [m for m in methods if pm_checks[m.id].value]
        f_defpm.options = [ft.dropdown.Option(str(m.id), m.name) for m in sel]
        if f_defpm.value not in [o.key for o in f_defpm.options]:
            f_defpm.value = f_defpm.options[0].key if f_defpm.options else None
        page.update()
    for c in pm_checks.values():
        c.on_change = sync_defpm

    def save(e):
        try:
            args = dict(code=f_code.value, name=f_name.value, branch_id=int(f_branch.value) if f_branch.value else None, cost_center_id=int(f_cc.value) if f_cc.value else None,
                        location_id=int(f_loc.value) if f_loc.value else None, employee_id=int(f_emp.value) if f_emp.value else None, assigned_username=f_user.value or None,
                        default_customer_id=int(f_cust.value) if f_cust.value else None, lock_customer=f_lock.value, payment_method_ids=[mid for mid, c in pm_checks.items() if c.value],
                        default_payment_method_id=int(f_defpm.value) if f_defpm.value else None, receipt_footer=f_footer.value, notes=f_notes.value, is_active=f_active.value)
            if editing['id']:
                services.update_pos_terminal(editing['id'], **args)
            else:
                services.create_pos_terminal(**args)
            close(form); refresh(True); snack('تم حفظ الماكينة')
        except Exception as ex:
            f_err.value = str(ex); f_err.visible = True; page.update()

    form = ft.AlertDialog(modal=True, title=ft.Text('ماكينة جديدة'), content=ft.Container(width=700, content=ft.Column([
        ft.Row([f_code, f_name, f_active], wrap=True, spacing=10), ft.Text('الربط الإداري', weight=ft.FontWeight.BOLD), ft.Row([f_branch, f_cc, f_loc], wrap=True, spacing=10),
        ft.Row([f_emp.control, f_user], wrap=True, spacing=10), ft.Text('العميل وطرق الدفع', weight=ft.FontWeight.BOLD), ft.Row([f_cust.control, f_lock], wrap=True, spacing=10),
        ft.Text('طرق الدفع المسموحة على الماكينة *', size=13), ft.Row(list(pm_checks.values()), wrap=True, spacing=8), f_defpm, ft.Text('الإيصال', weight=ft.FontWeight.BOLD), f_footer, f_notes, f_err],
        tight=True, spacing=10, scroll=ft.ScrollMode.AUTO, height=600)),
        actions=[ft.TextButton('إلغاء', on_click=lambda e: close(form)), theme.guard_submit(ft.FilledButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save))])
    page.overlay.append(form)

    def open_form(tid=None):
        editing['id'] = tid; f_err.visible = False
        t = services.get_pos_terminal(tid) if tid else None
        form.title.value = 'تعديل الماكينة' if t else 'ماكينة جديدة'
        f_code.value = t['code'] if t else ''; f_name.value = t['name'] if t else ''; f_active.value = t['is_active'] if t else True
        f_branch.value = str(t['branch_id']) if t and t['branch_id'] else ''; f_cc.value = str(t['cost_center_id']) if t and t['cost_center_id'] else ''; f_loc.value = str(t['location_id']) if t and t['location_id'] else ''
        f_emp.value = str(t['employee_id']) if t and t['employee_id'] else None; f_user.value = (t['assigned_username'] if t else '') or ''
        f_cust.value = str(t['default_customer_id']) if t and t['default_customer_id'] else None; f_lock.value = t['lock_customer'] if t else False
        sel = {m['id'] for m in t['payment_methods']} if t else set()
        for mid, c in pm_checks.items():
            c.value = mid in sel
        f_footer.value = t['receipt_footer'] if t else ''; f_notes.value = t['notes'] if t else ''
        f_defpm.options = [ft.dropdown.Option(str(m.id), m.name) for m in methods if m.id in sel]
        f_defpm.value = str(t['default_payment_method_id']) if t and t['default_payment_method_id'] in sel else (f_defpm.options[0].key if f_defpm.options else None)
        form.open = True; page.update()

    refresh()
    return ft.Column([
        ft.Row([theme.page_title('ماكينات نقاط البيع', 'اربط كل ماكينة كاشير بفرع ومركز تكلفة ومخزن وموظف ومستخدم وطرق دفع معيّنة'), ft.Container(expand=True),
                ft.FilledButton('ماكينة جديدة', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=lambda e: open_form())], spacing=8),
        ft.Container(height=4), cards, theme.card(theme.h_scroll(table.control, vscroll=True), expand=True),
    ], expand=True, spacing=8)
