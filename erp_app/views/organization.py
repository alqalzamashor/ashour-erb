import json
import flet as ft
from .. import services, theme, field_access


def make_hidden_row(store):
    """مربعات اختيار الحقول المخفية عن المستخدم (بتخزّن في store['_hidden']). بيرجّع (العنصر، دالة مزامنة المربعات مع store)."""
    cbs = {}

    def toggle(f, v):
        cur = [x for x in store.get(field_access.KEY, []) if x != f]
        if v:
            cur.append(f)
        store[field_access.KEY] = cur
    for f, label in field_access.FIELDS.items():
        cbs[f] = ft.Checkbox(label='إخفاء: ' + label, value=False, on_change=lambda e, f=f: toggle(f, e.control.value))

    def sync():
        for f, cb in cbs.items():
            cb.value = f in store.get(field_access.KEY, [])
    col = ft.Column([ft.Text('إخفاء حقول حساسة عن المستخدم (مدير النظام بيشوف كل حاجة دايمًا)', weight=ft.FontWeight.BOLD, size=12)] + list(cbs.values()), spacing=2)
    return col, sync


def build_organization(page: ft.Page, user=None):
    if user and not services.user_has_action(user, 'organization', 'view'):
        return theme.card(ft.Text('ليس لديك صلاحية إدارة الهيكل الإداري والمستخدمين.', color=theme.DANGER))

    def msg(x):
        page.overlay.append(ft.SnackBar(ft.Text(str(x)), open=True)); page.update()

    tabs=theme.SimpleTabs(page)

    # ---------------- Branches ----------------
    def branches_view():
        code=ft.TextField(label='كود الفرع',width=130); name=ft.TextField(label='اسم الفرع',width=220); default=ft.Checkbox(label='افتراضي')
        def _branch_row(b):
            return ft.DataRow(cells=[ft.DataCell(ft.Text(b.code)),ft.DataCell(ft.Text(b.name)),ft.DataCell(ft.Text('نشط' if b.is_active else 'موقوف')),ft.DataCell(ft.Text('نعم' if b.is_default else '')),ft.DataCell(ft.TextButton('تعطيل' if b.is_active else 'تفعيل',on_click=lambda e,bid=b.id,active=b.is_active:toggle(bid,active)))])
        table_sortable=theme.SortableDataTable(
            columns=[('الكود', lambda b: b.code), ('الفرع', lambda b: b.name), ('الحالة', lambda b: b.is_active),
                     ('افتراضي', lambda b: b.is_default), ('إجراء', None)],
            row_builder=_branch_row, page=page,
        )
        table=table_sortable.control
        def refresh(e=None):
            table_sortable.set_data(services.list_branches(False))
        def add(e):
            try:
                services.create_branch(code.value,name.value,default.value);code.value='';name.value='';default.value=False;refresh()
            except Exception as ex:msg(ex)
        def toggle(bid,active):
            try:services.update_branch(bid,is_active=not active);refresh()
            except Exception as ex:msg(ex)
        refresh();return ft.Column([ft.Row([code,name,default,ft.FilledButton('إضافة فرع',on_click=add)]),theme.h_scroll(table)],scroll=ft.ScrollMode.AUTO)

    # ---------------- Cost centers ----------------
    def centers_view():
        code=ft.TextField(label='كود مركز التكلفة',width=160);name=ft.TextField(label='اسم مركز التكلفة',width=250)
        branch=ft.Dropdown(label='الفرع',width=240,options=[ft.dropdown.Option('', 'مشترك / كل الفروع')]+[ft.dropdown.Option(str(b.id),f'{b.code} - {b.name}') for b in services.list_branches(True)],value='')
        parent=ft.Dropdown(label='مركز التكلفة الأب',width=260,options=[ft.dropdown.Option('', 'بدون أب')],value='')
        table=ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['الكود','مركز التكلفة','الفرع','الأب','الحالة','إجراء']],rows=[])
        def refresh(e=None):
            centers=services.list_cost_centers(False); byid={x.id:x for x in centers}; parent.options=[ft.dropdown.Option('', 'بدون أب')]+[ft.dropdown.Option(str(x.id),f'{x.code} - {x.name}') for x in centers]
            branch_names={b.id:b.name for b in services.list_branches(False)}
            table.rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(x.code)),ft.DataCell(ft.Text(x.name)),ft.DataCell(ft.Text(branch_names.get(x.branch_id,'مشترك'))),ft.DataCell(ft.Text(f'{byid[x.parent_id].code} - {byid[x.parent_id].name}' if x.parent_id in byid else '-')),ft.DataCell(ft.Text('نشط' if x.is_active else 'موقوف')),ft.DataCell(ft.TextButton('تعطيل' if x.is_active else 'تفعيل',on_click=lambda e,i=x.id,a=x.is_active:toggle(i,a)))]) for x in centers];page.update()
        def add(e):
            try:services.create_cost_center(code.value,name.value,int(parent.value) if parent.value else None,int(branch.value) if branch.value else None);code.value='';name.value='';parent.value='';branch.value='';refresh()
            except Exception as ex:msg(ex)
        def toggle(i,a):
            try:services.update_cost_center(i,is_active=not a);refresh()
            except Exception as ex:msg(ex)
        refresh();return ft.Column([ft.Row([code,name,branch,parent,ft.FilledButton('إضافة مركز تكلفة',on_click=add)],wrap=True),ft.Text('مركز التكلفة يمكن أن يكون تابعاً لفرع أو مشتركاً بين الفروع، مع دعم التسلسل الأب/الابن.',color=theme.TEXT_MUTED),theme.h_scroll(table)],scroll=ft.ScrollMode.AUTO)

    # ---------------- Users & permissions ----------------
    modules=list(services.MODULE_NAMES.items())
        
    def users_view():
        uname=ft.TextField(label='اسم المستخدم',width=150);full=ft.TextField(label='الاسم الكامل',width=190);pw=ft.TextField(label='كلمة المرور',password=True,width=160)
        role=ft.Dropdown(label='الدور',width=150,options=[ft.dropdown.Option('admin','مدير النظام'),ft.dropdown.Option('accountant','محاسب'),ft.dropdown.Option('sales','مبيعات'),ft.dropdown.Option('inventory','مخزون'),ft.dropdown.Option('viewer','مشاهد')],value='accountant')
        branch_dd=theme.MultiCheckList('الفروع المسموحة',page,width=300)
        for b in services.list_branches(True): branch_dd.add_option(b.id,f'{b.code} - {b.name}')
        cc_dd=theme.MultiCheckList('مراكز التكلفة المسموحة',page,width=320)
        for c in services.list_cost_centers(True): cc_dd.add_option(c.id,f'{c.code} - {c.name}')
        selected_permissions={}
        hid_col,hid_sync=make_hidden_row(selected_permissions)
        perm_table=ft.DataTable(columns=[ft.DataColumn(ft.Text('الوحدة'))]+[ft.DataColumn(ft.Text(x)) for x in ['عرض','إضافة','تعديل','حذف','ترحيل','إقفال']],rows=[])
        def fill_permissions():
            base=services.ROLE_DEFAULT_PERMISSIONS.get(role.value,{})
            if not selected_permissions:
                selected_permissions.update({k:list(v) for k,v in base.items()})
                if field_access.ROLE_DEFAULT_HIDDEN.get(role.value): selected_permissions[field_access.KEY]=list(field_access.ROLE_DEFAULT_HIDDEN[role.value])
            hid_sync()
            perm_table.rows=[]
            for key,label in modules:
                actions=selected_permissions.get(key,base.get(key,[]))
                checks=[]
                for action in ['view','create','edit','delete','post','close']:
                    cb=ft.Checkbox(value=('*' in actions or action in actions),on_change=lambda e,k=key,a=action:set_perm(k,a,e.control.value))
                    checks.append(ft.DataCell(cb))
                perm_table.rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(label))]+checks))
            page.update()
        def set_perm(k,a,v):
            selected_permissions.setdefault(k,[])
            if v and a not in selected_permissions[k]: selected_permissions[k].append(a)
            if not v and a in selected_permissions[k]: selected_permissions[k].remove(a)
        def add(e):
            try:
                p={k:[a for a in v] for k,v in selected_permissions.items() if v}
                bids=[int(x) for x in (branch_dd.value or [])]
                cids=[int(x) for x in (cc_dd.value or [])]
                services.create_user(uname.value,pw.value,full.value,role.value,p,bids,cids)
                uname.value='';full.value='';pw.value='';branch_dd.value=[];cc_dd.value=[];selected_permissions.clear();fill_permissions();refresh()
            except Exception as ex:msg(ex)
        bs_cache={}; cs_cache={}
        def _user_names(x):
            try: bids=json.loads(x.branch_ids or '[]')
            except: bids=[]
            try: cids=json.loads(getattr(x,'cost_center_ids','[]') or '[]')
            except: cids=[]
            names=', '.join(bs_cache.get(int(i),str(i)) for i in bids) if bids else 'كل الفروع'
            cnames=', '.join(cs_cache.get(int(i),str(i)) for i in cids) if cids else 'كل المراكز'
            return names, cnames
        def reset_2fa(uid):
            try:
                from erp_app import twofa
                twofa.admin_reset(uid); refresh()
            except Exception as ex:
                page.snack_bar=ft.SnackBar(ft.Text(str(ex)));page.snack_bar.open=True;page.update()
        def _user_row(x):
            names, cnames = _user_names(x)
            return ft.DataRow(cells=[ft.DataCell(ft.Text(x.username)),ft.DataCell(ft.Text(x.full_name)),ft.DataCell(ft.Text(x.role)),ft.DataCell(ft.Text(names)),ft.DataCell(ft.Text(cnames)),ft.DataCell(ft.Text('نشط' if x.is_active else 'موقوف')),ft.DataCell(ft.Row([ft.IconButton(ft.Icons.EDIT_OUTLINED,tooltip='تعديل الصلاحيات',on_click=lambda e,uid=x.id:open_edit_user(uid)),ft.TextButton('توقيف' if x.is_active else 'تفعيل',on_click=lambda e,uid=x.id,a=x.is_active:toggle_user(uid,a)),*([ft.IconButton(ft.Icons.SECURITY,tooltip='تصفير التحقق بخطوتين (فقد الجهاز)',on_click=lambda e,uid=x.id:reset_2fa(uid))] if x.totp_enabled else [])]))])
        table_sortable=theme.SortableDataTable(
            columns=[('المستخدم', lambda x: x.username), ('الاسم', lambda x: x.full_name), ('الدور', lambda x: x.role),
                     ('الفروع', lambda x: _user_names(x)[0]), ('مراكز التكلفة', lambda x: _user_names(x)[1]),
                     ('الحالة', lambda x: x.is_active), ('إجراءات', None)],
            row_builder=_user_row, page=page,
        )
        table=table_sortable.control

        # ---------------- نافذة تعديل مستخدم موجود ----------------
        edit_full=ft.TextField(label='الاسم الكامل',width=200)
        edit_pw=ft.TextField(label='كلمة مرور جديدة (اتركها فاضية للاحتفاظ بالقديمة)',password=True,can_reveal_password=True,width=260)
        edit_role=ft.Dropdown(label='الدور',width=150,options=[ft.dropdown.Option('admin','مدير النظام'),ft.dropdown.Option('accountant','محاسب'),ft.dropdown.Option('sales','مبيعات'),ft.dropdown.Option('inventory','مخزون'),ft.dropdown.Option('viewer','مشاهد')])
        edit_branch_dd=theme.MultiCheckList('الفروع المسموحة',page,width=300)
        for b in services.list_branches(True): edit_branch_dd.add_option(b.id,f'{b.code} - {b.name}')
        edit_cc_dd=theme.MultiCheckList('مراكز التكلفة المسموحة',page,width=320)
        for c in services.list_cost_centers(True): edit_cc_dd.add_option(c.id,f'{c.code} - {c.name}')
        edit_selected_permissions={}
        edit_hid_col,edit_hid_sync=make_hidden_row(edit_selected_permissions)
        edit_perm_table=ft.DataTable(columns=[ft.DataColumn(ft.Text('الوحدة'))]+[ft.DataColumn(ft.Text(x)) for x in ['عرض','إضافة','تعديل','حذف','ترحيل','إقفال']],rows=[])
        edit_error=ft.Text('',color=theme.DANGER,visible=False)
        edit_user_id={'id':None}

        def edit_set_perm(k,a,v):
            edit_selected_permissions.setdefault(k,[])
            if v and a not in edit_selected_permissions[k]: edit_selected_permissions[k].append(a)
            if not v and a in edit_selected_permissions[k]: edit_selected_permissions[k].remove(a)

        def edit_fill_permissions():
            edit_hid_sync()
            edit_perm_table.rows=[]
            for key,label in modules:
                actions=edit_selected_permissions.get(key,[])
                checks=[]
                for action in ['view','create','edit','delete','post','close']:
                    cb=ft.Checkbox(value=('*' in actions or action in actions),on_change=lambda e,k=key,a=action:edit_set_perm(k,a,e.control.value))
                    checks.append(ft.DataCell(cb))
                edit_perm_table.rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(label))]+checks))
            page.update()

        def edit_role_changed(e):
            # لو المستخدم غيّر الدور، اعرض صلاحيات الدور الجديد الافتراضية كنقطة بداية
            edit_selected_permissions.clear()
            base=services.ROLE_DEFAULT_PERMISSIONS.get(edit_role.value,{})
            edit_selected_permissions.update({k:list(v) for k,v in base.items()})
            if field_access.ROLE_DEFAULT_HIDDEN.get(edit_role.value): edit_selected_permissions[field_access.KEY]=list(field_access.ROLE_DEFAULT_HIDDEN[edit_role.value])
            edit_fill_permissions()
        edit_role.on_change=edit_role_changed

        def save_edit(e):
            try:
                p={k:[a for a in v] for k,v in edit_selected_permissions.items() if v}
                bids=[int(x) for x in (edit_branch_dd.value or [])]
                cids=[int(x) for x in (edit_cc_dd.value or [])]
                services.update_user(
                    edit_user_id['id'], password=edit_pw.value or None,
                    full_name=edit_full.value, role=edit_role.value,
                    permissions=json.dumps(p, ensure_ascii=False),
                    branch_ids=json.dumps(bids, ensure_ascii=False),
                    cost_center_ids=json.dumps(cids, ensure_ascii=False),
                )
                edit_dialog.open=False; page.update(); refresh()
            except Exception as ex:
                edit_error.value=str(ex); edit_error.visible=True; page.update()

        def close_edit(e=None):
            edit_dialog.open=False; page.update()

        edit_dialog=ft.AlertDialog(
            modal=True, title=ft.Text('تعديل بيانات وصلاحيات المستخدم'),
            content=ft.Container(width=950, content=ft.Column([
                ft.Row([edit_full,edit_pw,edit_role,edit_branch_dd.control,edit_cc_dd.control],wrap=True),
                ft.Text('عدّل الصلاحيات الدقيقة لكل وحدة. تغيير الدور بيعرض صلاحياته الافتراضية كنقطة بداية - عدّلها زي ما تحب بعد كده.',color=theme.TEXT_MUTED),
                theme.h_scroll(edit_perm_table),
                edit_hid_col,
                edit_error,
            ], scroll=ft.ScrollMode.AUTO, spacing=10), padding=10),
            actions=[ft.TextButton('إلغاء',on_click=close_edit),ft.FilledButton('حفظ التعديلات',icon=ft.Icons.SAVE_OUTLINED,bgcolor=theme.PRIMARY,on_click=save_edit)],
        )
        page.overlay.append(edit_dialog)

        def open_edit_user(uid):
            u=next((x for x in services.list_users() if x.id==uid),None)
            if not u: return
            edit_user_id['id']=uid
            edit_full.value=u.full_name
            edit_pw.value=''
            edit_role.value=u.role
            try: cur_perms=json.loads(u.permissions or '{}')
            except Exception: cur_perms={}
            edit_selected_permissions.clear(); edit_selected_permissions.update({k:list(v) for k,v in cur_perms.items()})
            try: cur_bids=[int(x) for x in json.loads(u.branch_ids or '[]')]
            except Exception: cur_bids=[]
            try: cur_cids=[int(x) for x in json.loads(getattr(u,'cost_center_ids','[]') or '[]')]
            except Exception: cur_cids=[]
            edit_branch_dd.value=cur_bids
            edit_cc_dd.value=cur_cids
            edit_fill_permissions()
            edit_dialog.open=True; page.update()

        def toggle_user(uid, active):
            try:
                services.update_user(uid,is_active=not active); refresh()
            except Exception as ex: msg(ex)
        def refresh(e=None):
            bs_cache.clear(); bs_cache.update({b.id:b.name for b in services.list_branches(False)})
            cs_cache.clear(); cs_cache.update({c.id:c.name for c in services.list_cost_centers(False)})
            table_sortable.set_data(services.list_users())
        def role_changed(e):
            selected_permissions.clear(); fill_permissions()
        role.on_change=role_changed
        fill_permissions();refresh()
        return ft.Column([ft.Row([uname,full,pw,role,branch_dd.control,cc_dd.control],wrap=True),ft.Text('اختر الصلاحيات الدقيقة لكل وحدة. الفروع ومراكز التكلفة المحددة تمنع المستخدم من رؤية أو تسجيل الحركات خارج النطاق المسموح به.',color=theme.TEXT_MUTED),theme.h_scroll(perm_table),hid_col,ft.Row([theme.guard_submit(ft.FilledButton('إضافة مستخدم',icon=ft.Icons.PERSON_ADD,on_click=add)),ft.OutlinedButton('تحديث',on_click=refresh)]),theme.h_scroll(table)],scroll=ft.ScrollMode.AUTO)

    tabs.set_tabs([('الفروع',theme.card(branches_view())),('مراكز التكلفة',theme.card(centers_view())),('المستخدمون والصلاحيات',theme.card(users_view()))])
    return ft.Column([theme.page_title('الهيكل الإداري والأمان','الفروع ومراكز التكلفة والمستخدمون والصلاحيات الدقيقة'),tabs.control],expand=True)
