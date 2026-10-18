import flet as ft
from .. import theme

NUM_W = 112


def _m(v):
    return f'{float(v or 0):,.2f}'


def flatten(roots):
    """صفوف مسطّحة (حساب، موظف، مدين، دائن، رصيد) لتصدير Excel/PDF."""
    out = []

    def walk(n, path):
        label = f"{n['code']} - {n['name']}"
        for e in n['employees']:
            out.append([label, f"{e['code']} - {e['name']}", e['debit'], e['credit'], e['balance']])
        for ch in n['children']:
            walk(ch, path)
    for r in roots:
        walk(r, '')
    return out


def build_employee_tree(page, roots, load_movements):
    """شجرة: الحساب (بتجميع أبنائه) ← الموظفين تحته ← حركات الموظف. الحركات بتتحمّل أول ما تفتح الموظف.
    load_movements(account_id, employee_id) -> قايمة حركات (من services.employee_account_movements)."""
    toggles = []          # (kind, body, icon)

    def head():
        h = lambda t, w=None: ft.Text(t, weight=ft.FontWeight.BOLD, size=12, color=theme.TEXT_MUTED, width=w, expand=w is None)
        return ft.Container(padding=ft.Padding(left=8, right=8, top=6, bottom=6), bgcolor=theme.PRIMARY_LIGHT, border_radius=8,
                            content=ft.Row([ft.Container(width=34), h('الحساب / الموظف'), h('مدين', NUM_W), h('دائن', NUM_W), h('الرصيد', NUM_W)], spacing=6))

    def line(level, label, d, c, b, bold, on_click, expandable, bg=None):
        icon = ft.Icon(ft.Icons.CHEVRON_LEFT if expandable else ft.Icons.CIRCLE, size=22 if expandable else 6, color=theme.PRIMARY if expandable else theme.TEXT_MUTED)
        w = ft.FontWeight.BOLD if bold else None
        cont = ft.Container(
            padding=ft.Padding(left=8, right=8 + level * 24, top=7, bottom=7), bgcolor=bg, border_radius=6, ink=expandable,
            border=ft.border.Border(bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT)),
            on_click=on_click if expandable else None,
            content=ft.Row([ft.Container(icon, width=34, alignment=ft.Alignment(0, 0)), ft.Text(label, weight=w, expand=True, size=13),
                            ft.Text(_m(d), width=NUM_W, weight=w, size=13), ft.Text(_m(c), width=NUM_W, weight=w, size=13),
                            ft.Text(_m(b), width=NUM_W, weight=ft.FontWeight.BOLD, size=13, color=theme.PRIMARY if b >= 0 else theme.DANGER)], spacing=6))
        return cont, icon

    def movements_table(aid, eid, level):
        try:
            rows = load_movements(aid, eid)
        except Exception as ex:
            return ft.Text(str(ex), color=theme.DANGER)
        if not rows:
            return ft.Text('مفيش حركات', color=theme.TEXT_MUTED)
        cells = lambda r: [ft.DataCell(ft.Text(r['date'].strftime('%Y-%m-%d') if r['date'] else '')), ft.DataCell(ft.Text(r['number'])),
                           ft.DataCell(ft.Text(r['description'])), ft.DataCell(ft.Text(_m(r['debit']))), ft.DataCell(ft.Text(_m(r['credit']))),
                           ft.DataCell(ft.Text(_m(r['balance'])))]
        tbl = ft.DataTable(columns=[ft.DataColumn(ft.Text(c)) for c in ['التاريخ', 'القيد', 'البيان', 'مدين', 'دائن', 'الرصيد']],
                           rows=[ft.DataRow(cells=cells(r)) for r in rows], heading_row_height=36, data_row_min_height=32, column_spacing=22)
        return ft.Container(padding=ft.Padding(left=8, right=40 + level * 24, top=4, bottom=8), content=theme.h_scroll(tbl, vscroll=False))

    def make_toggle(kind, body, icon, loader=None):
        idx = len(toggles)
        toggles.append((kind, body, icon))          # الأيقونة الحقيقية بتتحط مكان المؤقتة بعد بناء السطر (toggles[idx])

        def on_click(e=None):
            body.visible = not body.visible
            if body.visible and loader and not body.controls:
                body.controls = [loader()]
            toggles[idx][2].icon = ft.Icons.EXPAND_MORE if body.visible else ft.Icons.CHEVRON_LEFT
            page.update()
        return on_click

    def account_node(n, level):
        body = ft.Column([], spacing=0, visible=False)
        icon_holder = {}
        click = make_toggle('account', body, ft.Icon(ft.Icons.CHEVRON_LEFT))        # الأيقونة الحقيقية بتتبدّل بعد ما نبني السطر
        row, icon = line(level, f"{n['code']} - {n['name']}", n['debit'], n['credit'], n['balance'], True, click, True, theme.CARD_BG)
        toggles[-1] = ('account', body, icon)
        kids = [account_node(ch, level + 1) for ch in n['children']] + [employee_node(n, e, level + 1) for e in n['employees']]
        body.controls = kids
        return ft.Column([row, body], spacing=0)

    def employee_node(n, e, level):
        body = ft.Column([], spacing=0, visible=False)
        click = make_toggle('employee', body, ft.Icon(ft.Icons.CHEVRON_LEFT), lambda a=n['id'], i=e['employee_id'], lv=level: movements_table(a, i, lv))
        row, icon = line(level, f"{e['code']} - {e['name']}", e['debit'], e['credit'], e['balance'], False, click, True, theme.BG)
        toggles[-1] = ('employee', body, icon)
        return ft.Column([row, body], spacing=0)

    def set_all(kind_filter, visible):
        for kind, body, icon in toggles:
            if kind_filter is None or kind == kind_filter:
                body.visible = visible
                icon.icon = ft.Icons.EXPAND_MORE if visible else ft.Icons.CHEVRON_LEFT
        page.update()

    if not roots:
        return ft.Text('مفيش حركات موظفين في الفترة دي. الحركات بتظهر من قيود الرواتب والصرف والمخصصات والتسويات والعهد.', color=theme.TEXT_MUTED)
    tops = [account_node(r, 0) for r in roots]
    total_d = sum(r['debit'] for r in roots); total_c = sum(r['credit'] for r in roots)
    bar = ft.Row([ft.OutlinedButton('فتح الحسابات', icon=ft.Icons.UNFOLD_MORE, on_click=lambda e: set_all('account', True)),
                  ft.TextButton('طي الكل', icon=ft.Icons.UNFOLD_LESS, on_click=lambda e: set_all(None, False)),
                  ft.Text(f'الإجمالي: مدين {_m(total_d)} | دائن {_m(total_c)} | الرصيد {_m(total_d - total_c)}', weight=ft.FontWeight.BOLD, color=theme.PRIMARY)], spacing=8, wrap=True)
    return ft.Column([bar, head()] + tops, spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
