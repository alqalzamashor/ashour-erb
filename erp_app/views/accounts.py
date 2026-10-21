import flet as ft
from .. import services, theme, i18n

TYPE_LABELS={'asset':'أصول','liability':'التزامات','equity':'حقوق ملكية','income':'إيرادات','expense':'مصروفات'}
CF_LABELS={'cash':'نقدية','operating':'تشغيلي','investing':'استثماري','financing':'تمويلي'}
CF_COLORS={'cash':theme.PRIMARY,'operating':theme.SUCCESS,'investing':theme.WARNING,'financing':"#8E5CE6"}


def build_accounts(page: ft.Page):
    search=ft.TextField(label='بحث',width=260,prefix_icon=ft.Icons.SEARCH)
    tree_holder=ft.Container(content=ft.Column(spacing=2))   # كل تحديث بيبدّل العمود كله (مش diff على قايمة كبيرة - ده كان بيكسر الواجهة وقت البحث)
    code=ft.TextField(label='كود الحساب',width=180); name=ft.TextField(label='اسم الحساب',width=300)
    typ=ft.Dropdown(label='نوع الحساب',width=220,options=[ft.dropdown.Option(key=k,text=v) for k,v in TYPE_LABELS.items()])
    cf_dd=ft.Dropdown(label='نوع التدفق النقدي',width=220,options=[ft.dropdown.Option(key='',text='بدون تصنيف')]+[ft.dropdown.Option(key=k,text=v) for k,v in CF_LABELS.items()])
    parent=ft.Dropdown(label='الحساب الأب',width=300); editing={'id':None}; err=ft.Text('',color=theme.DANGER,visible=False)
    expanded_state = {}  # account_id -> True/False (متوسع أو مطوي)

    def cf_badge(cf_type):
        if not cf_type:
            return ft.Text('-', color=theme.TEXT_MUTED, size=12)
        return ft.Container(
            content=ft.Text(CF_LABELS.get(cf_type, cf_type), size=10, color="#FFFFFF"),
            bgcolor=CF_COLORS.get(cf_type, theme.TEXT_MUTED), border_radius=6,
            padding=ft.Padding(left=8, right=8, top=2, bottom=2),
        )

    def build_row(a, level, has_children, all_accts_by_parent, expand=True):
        is_expanded = expanded_state.get(a.id, level == 0)  # المستوى الأول متفرد افتراضياً

        toggle_icon = None
        if has_children:
            toggle_icon = ft.Icon(
                ft.Icons.KEYBOARD_ARROW_DOWN if is_expanded else ft.Icons.CHEVRON_LEFT,
                size=18, color=theme.PRIMARY,
            )
        else:
            toggle_icon = ft.Container(width=18)

        def on_toggle(e, acc_id=a.id):
            expanded_state[acc_id] = not expanded_state.get(acc_id, level == 0)
            refresh()

        name_row = ft.Row(
            [
                ft.Container(width=level * 24),
                ft.Container(
                    content=toggle_icon,
                    on_click=on_toggle if has_children else None,
                    ink=has_children,
                    border_radius=4,
                    padding=2,
                ),
                ft.Text(
                    a.name,
                    weight=ft.FontWeight.BOLD if has_children else ft.FontWeight.NORMAL,
                    color=theme.PRIMARY if has_children else None,
                ),
                ft.Container(
                    content=ft.Text('رئيسي', size=10, color="#FFFFFF"),
                    bgcolor=theme.TEXT_MUTED, border_radius=6,
                    padding=ft.Padding(left=6, right=6, top=1, bottom=1),
                    visible=has_children,
                ),
            ],
            spacing=4,
        )

        row = ft.Row(
            [
                ft.Container(ft.Text(a.code, no_wrap=True), width=110),
                ft.Container(name_row, width=310),
                ft.Container(ft.Text(TYPE_LABELS.get(a.account_type, a.account_type)), width=100),
                ft.Container(cf_badge(a.cash_flow_type), width=100),
                ft.Container(
                    ft.Row([
                        ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل', on_click=lambda e, x=a: open_edit(x)),
                        ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف', on_click=lambda e, i=a.id: delete(i)),
                    ]),
                ),
            ],
            spacing=4,
        )
        row._erp_nowrap = True
        name_row._erp_nowrap = True

        rows_out = [ft.Container(row, padding=ft.Padding(left=4, right=4, top=6, bottom=6),
                                  bgcolor=theme.SURFACE_ALT if has_children else None, border_radius=6)]

        if expand and has_children and is_expanded:
            for child in all_accts_by_parent.get(a.id, []):
                child_has_children = child.id in all_accts_by_parent
                rows_out += build_row(child, level + 1, child_has_children, all_accts_by_parent)

        return rows_out

    def refresh(e=None):
        query = (search.value or '').strip().lower()
        all_accts = services.list_accounts()
        by_parent = {}
        for a in all_accts:
            if a.parent_id:
                by_parent.setdefault(a.parent_id, []).append(a)
        for k in by_parent:
            by_parent[k].sort(key=lambda x: x.code)

        parent.options = [ft.dropdown.Option(key='', text='بدون حساب أب')] + [
            ft.dropdown.Option(key=str(a.id), text=f'{a.code} - {a.name}') for a in all_accts if a.id != editing['id']
        ]

        if query:
            # لو فيه بحث، اعرض قايمة مسطحة عادية (مش شجرة) عشان النتائج تبان كلها
            # البحث بالكود وباسم الحساب بالعربي وبترجمته الإنجليزية (الشاشة بتعرض الإنجليزي في وضع English)
            matched = [a for a in all_accts if query in a.code.lower() or query in a.name.lower() or query in (i18n.tr(a.name, 'en') or '').lower()]
            controls = []
            for a in matched:
                has_children = a.id in by_parent
                controls += build_row(a, 0, has_children, by_parent, expand=False)   # نتائج البحث مسطّحة من غير تكرار الأبناء
            tree_holder.content = ft.Column(controls, spacing=2)
        else:
            roots = [a for a in all_accts if not a.parent_id]
            roots.sort(key=lambda x: x.code)
            controls = []
            for a in roots:
                has_children = a.id in by_parent
                controls += build_row(a, 0, has_children, by_parent)
            tree_holder.content = ft.Column(controls, spacing=2)

        page.update()

    def _parent_ids():
        return {a.parent_id for a in services.list_accounts() if a.parent_id}

    def unfold_all(e=None):
        for pid in _parent_ids():
            expanded_state[pid] = True
        refresh()

    def fold_all(e=None):
        for pid in _parent_ids():
            expanded_state[pid] = False
        refresh()

    def open_add(e=None):
        editing['id']=None; code.value=''; name.value=''; typ.value='asset'; cf_dd.value=''; parent.value=''; err.visible=False; refresh(); dialog.title=ft.Text('إضافة حساب'); dialog.open=True; page.update()
    def open_edit(a):
        editing['id']=a.id; code.value=a.code; name.value=a.name; typ.value=a.account_type; cf_dd.value=a.cash_flow_type or ''; parent.value=str(a.parent_id or ''); err.visible=False; refresh(); dialog.title=ft.Text('تعديل حساب'); dialog.open=True; page.update()
    def save(e):
        try:
            pid=int(parent.value) if parent.value else None
            cf_type = cf_dd.value or None
            if editing['id'] is None: services.create_account(code.value,name.value,typ.value,pid,cash_flow_type=cf_type)
            else: services.update_account(editing['id'],code=(code.value or '').strip(),name=(name.value or '').strip(),account_type=typ.value,parent_id=pid,cash_flow_type=cf_type)
            dialog.open=False; refresh()
        except Exception as ex: err.value=str(ex); err.visible=True; page.update()
    def delete(i):
        try: services.delete_account(i); refresh()
        except Exception as ex: page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True)); page.update()

    dialog=ft.AlertDialog(
        modal=True,title=ft.Text('حساب'),
        content=ft.Container(
            width=420,
            content=ft.Column([ft.Row([code,typ],wrap=True),cf_dd,name,parent,err],tight=True,spacing=12),
        ),
        actions=[ft.TextButton('إلغاء',on_click=lambda e:setattr(dialog,'open',False) or page.update()),ft.FilledButton('حفظ',bgcolor=theme.PRIMARY,on_click=save)],
    )
    page.overlay.append(dialog); search.on_change=refresh; refresh()

    header_row = ft.Row(
        [
            ft.Container(ft.Text('الكود', weight=ft.FontWeight.BOLD), width=110),
            ft.Container(ft.Text('الحساب', weight=ft.FontWeight.BOLD), width=310),
            ft.Container(ft.Text('النوع', weight=ft.FontWeight.BOLD), width=100),
            ft.Container(ft.Text('التدفق النقدي', weight=ft.FontWeight.BOLD), width=100),
            ft.Container(ft.Text('الإجراءات', weight=ft.FontWeight.BOLD)),
        ],
        spacing=4,
    )
    header_row._erp_nowrap = True

    def _tree_body():
        inner = ft.Column([header_row, ft.Divider(height=1), ft.Column([tree_holder], scroll=ft.ScrollMode.AUTO, expand=True)],
                          spacing=6, expand=True)
        if not theme._page_w():
            return inner
        # موبايل: الأعمدة ثابتة العرض، فنسيب الشجرة بعرض كامل ويتمرر أفقيًا بدل ما الصف يتفكك تحت بعضه
        inner._erp_nocap = True
        inner.width = 780
        return ft.Row([ft.Container(inner, padding=ft.Padding(left=0, right=14, top=0, bottom=0))], scroll=ft.ScrollMode.AUTO, vertical_alignment=ft.CrossAxisAlignment.START)

    return ft.Column([
        ft.Row([theme.page_title('شجرة الحسابات','الدليل المحاسبي - دوس على السهم جنب أي حساب رئيسي لعرض الحسابات الفرعية'),
                ft.Container(expand=True), search,
                ft.OutlinedButton('فتح الكل', icon=ft.Icons.UNFOLD_MORE, on_click=unfold_all),
                ft.OutlinedButton('طي الكل', icon=ft.Icons.UNFOLD_LESS, on_click=fold_all),
                ft.FilledButton('إضافة حساب', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=open_add)]),
        ft.Container(height=12),
        theme.card(_tree_body(), expand=True),
    ], expand=True)
