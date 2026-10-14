import datetime
import os
import flet as ft
from .. import services, theme

AVATAR_COLORS = ['#6C4EE3', '#0E9F6E', '#E5484D', '#D97706', '#2563EB', '#9333EA', '#0891B2', '#DB2777']
MINE_BG = '#E6E0FF'
OTHER_BG = '#F1F2F7'
FILE_ICONS = {'.pdf': ft.Icons.PICTURE_AS_PDF, '.xlsx': ft.Icons.TABLE_VIEW, '.xls': ft.Icons.TABLE_VIEW, '.csv': ft.Icons.TABLE_VIEW,
              '.doc': ft.Icons.DESCRIPTION_OUTLINED, '.docx': ft.Icons.DESCRIPTION_OUTLINED, '.txt': ft.Icons.TEXT_SNIPPET_OUTLINED,
              '.zip': ft.Icons.FOLDER_ZIP_OUTLINED, '.rar': ft.Icons.FOLDER_ZIP_OUTLINED}


def _size_text(n):
    if n >= 1024 * 1024:
        return f'{n / 1024 / 1024:.1f} MB'
    return f'{max(1, n // 1024)} KB'


def _avatar(title, size=40):
    color = AVATAR_COLORS[sum(ord(c) for c in (title or '?')) % len(AVATAR_COLORS)]
    return ft.Container(width=size, height=size, border_radius=size / 2, bgcolor=color, alignment=ft.Alignment(0, 0),
                        content=ft.Text((title or '?').strip()[:1], color='#FFFFFF', size=size * 0.45, weight=ft.FontWeight.BOLD))


def _when(dt_):
    today = datetime.date.today()
    if dt_.date() == today:
        return dt_.strftime('%H:%M')
    if dt_.date() == today - datetime.timedelta(days=1):
        return 'أمس'
    return dt_.strftime('%Y-%m-%d')


def build_chat(page: ft.Page):
    """الشات بين المستخدمين: محادثات فردية ومجموعات، رسائل ومرفقات ملفات (حد 25MB، بدون ملفات تنفيذية)،
    عدّاد غير مقروء، وعلامة "اتقرت" في المحادثات الفردية. الرسائل بتتحدّث لوحدها."""
    me = services.current_user() or {}
    me_name = me.get('username')
    active = {'id': None, 'conv': None}
    pending = {'path': None}
    busy = {'send': False}

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def close(d):
        d.open = False; page.update()

    # ===================================================================== قايمة المحادثات
    search_f = ft.TextField(hint_text='بحث في المحادثات', prefix_icon=ft.Icons.SEARCH, dense=True, content_padding=ft.Padding(left=10, right=10, top=8, bottom=8))
    list_col = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, expand=True)
    convs = {'rows': []}

    def conv_tile(c):
        is_active = c['id'] == active['id']
        unread = ft.Container(content=ft.Text(str(c['unread'] if c['unread'] < 100 else '99+'), size=10, color='#FFFFFF', weight=ft.FontWeight.BOLD), bgcolor=theme.PRIMARY,
                              border_radius=10, padding=ft.Padding(left=6, right=6, top=1, bottom=1), visible=c['unread'] > 0)
        who = ('أنت: ' if c['last_mine'] else (f"{c['last_sender']}: " if c['kind'] == 'group' and c['last_sender'] else ''))
        return ft.Container(
            ink=True, border_radius=10, padding=ft.Padding(left=8, right=8, top=8, bottom=8), bgcolor=theme.PRIMARY_LIGHT if is_active else None,
            on_click=lambda e, i=c['id']: open_conversation(i),
            content=ft.Row([_avatar(c['title']),
                            ft.Column([ft.Row([ft.Text(c['title'], weight=ft.FontWeight.BOLD if c['unread'] else None, size=13.5, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True),
                                               ft.Text(_when(c['last_at']), size=10.5, color=theme.TEXT_MUTED)], spacing=4),
                                       ft.Row([ft.Text((who + c['last_text']) if c['last_text'] else 'لسه مفيش رسائل', size=11.5, color=theme.TEXT_MUTED, max_lines=1,
                                                       overflow=ft.TextOverflow.ELLIPSIS, expand=True), unread], spacing=4)], spacing=2, expand=True)], spacing=10))

    def refresh_list():
        try:
            convs['rows'] = services.chat_list_conversations()
        except Exception:
            convs['rows'] = []
        q = (search_f.value or '').strip().lower()
        rows = [c for c in convs['rows'] if not q or q in c['title'].lower()]
        list_col.controls = [conv_tile(c) for c in rows] or [ft.Container(padding=20, content=ft.Text('مفيش محادثات لسه - ابدأ محادثة جديدة', size=12, color=theme.TEXT_MUTED, text_align=ft.TextAlign.CENTER))]

    # ===================================================================== الرسائل
    msgs_col = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, auto_scroll=True, expand=True)
    head_title = ft.Text('', weight=ft.FontWeight.BOLD, size=16)
    head_sub = ft.Text('', size=11.5, color=theme.TEXT_MUTED)
    head_avatar = ft.Container()
    head_actions = ft.Row(spacing=0)
    header = ft.Container(visible=False, padding=ft.Padding(left=4, right=4, top=2, bottom=8),
                          content=ft.Row([head_avatar, ft.Column([head_title, head_sub], spacing=0, tight=True), ft.Container(expand=True), head_actions], spacing=10))
    placeholder = ft.Container(expand=True, alignment=ft.Alignment(0, 0), content=ft.Column([
        ft.Icon(ft.Icons.FORUM_OUTLINED, size=64, color=theme.TEXT_MUTED), ft.Text('اختار محادثة من القايمة أو ابدأ محادثة جديدة', color=theme.TEXT_MUTED),
        ft.Row([ft.FilledButton('محادثة جديدة', icon=ft.Icons.PERSON_ADD_ALT_1, bgcolor=theme.PRIMARY, on_click=lambda e: open_new_direct()),
                ft.OutlinedButton('مجموعة جديدة', icon=ft.Icons.GROUP_ADD, on_click=lambda e: open_new_group())], alignment=ft.MainAxisAlignment.CENTER, spacing=10)],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10, alignment=ft.MainAxisAlignment.CENTER))

    def open_attachment(message_id):
        try:
            theme.open_or_download_file(page, services.chat_attachment_path(message_id))
        except Exception as ex:
            snack(str(ex))

    def delete_message(message_id):
        try:
            services.chat_delete_message(message_id)
            refresh_messages(); refresh_list(); page.update()
        except Exception as ex:
            snack(str(ex))

    def attachment_card(m):
        ext = os.path.splitext(m['attachment_name'])[1].lower()
        icon = ft.Icons.IMAGE_OUTLINED if m['attachment_kind'] == 'image' else FILE_ICONS.get(ext, ft.Icons.INSERT_DRIVE_FILE_OUTLINED)
        return ft.Container(
            bgcolor='#FFFFFF', border_radius=8, padding=ft.Padding(left=8, right=8, top=6, bottom=6), ink=True, tooltip='فتح الملف', on_click=lambda e, i=m['id']: open_attachment(i),
            content=ft.Row([ft.Icon(icon, color=theme.PRIMARY, size=28),
                            ft.Column([ft.Text(m['attachment_name'], size=12.5, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                       ft.Text(_size_text(m['attachment_size']), size=10.5, color=theme.TEXT_MUTED)], spacing=0, tight=True),
                            ft.Icon(ft.Icons.DOWNLOAD, size=18, color=theme.TEXT_MUTED)], spacing=8, tight=True))

    def bubble(m, show_name, direct):
        if m['system']:
            return ft.Container(alignment=ft.Alignment(0, 0), padding=ft.Padding(left=0, right=0, top=4, bottom=4),
                                content=ft.Container(bgcolor='#ECEDF3', border_radius=10, padding=ft.Padding(left=10, right=10, top=3, bottom=3), content=ft.Text(m['body'], size=11, color=theme.TEXT_MUTED)))
        mine = m['mine']
        body = []
        if show_name and not mine:
            body.append(ft.Text(m['sender_name'], size=11, weight=ft.FontWeight.BOLD, color=AVATAR_COLORS[sum(ord(c) for c in m['sender_name']) % len(AVATAR_COLORS)]))
        if m['deleted']:
            body.append(ft.Text('🚫 تم حذف الرسالة', size=12, color=theme.TEXT_MUTED, italic=True))
        else:
            if m['has_attachment']:
                body.append(attachment_card(m))
            if m['body']:
                body.append(ft.Text(m['body'], size=13.5, selectable=True))
        foot = [ft.Text(m['created_at'].strftime('%H:%M'), size=10, color=theme.TEXT_MUTED)]
        if mine and direct and not m['deleted']:
            foot.append(ft.Icon(ft.Icons.DONE_ALL if m['seen'] else ft.Icons.DONE, size=14, color='#2563EB' if m['seen'] else theme.TEXT_MUTED, tooltip='اتقرت' if m['seen'] else 'اتبعتت'))
        if mine and not m['deleted']:
            foot.append(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_size=14, icon_color=theme.TEXT_MUTED, tooltip='حذف الرسالة', width=22, height=22, padding=0,
                                      on_click=lambda e, i=m['id']: delete_message(i)))
        body.append(ft.Row(foot, spacing=4, alignment=ft.MainAxisAlignment.END, tight=True))
        long = len(m['body']) > 45 or m['has_attachment']
        card = ft.Container(content=ft.Column(body, spacing=3, tight=True), bgcolor=MINE_BG if mine else OTHER_BG, border_radius=12,
                            padding=ft.Padding(left=10, right=10, top=6, bottom=4), width=420 if long else None)
        return ft.Row([card], alignment=ft.MainAxisAlignment.END if mine else ft.MainAxisAlignment.START)

    def day_label(d):
        today = datetime.date.today()
        return 'اليوم' if d == today else ('أمس' if d == today - datetime.timedelta(days=1) else d.strftime('%Y-%m-%d'))

    def refresh_messages(mark_read=True):
        cid = active['id']
        if not cid:
            return
        try:
            rows = services.chat_messages(cid)
        except Exception as ex:
            msgs_col.controls = [ft.Text(str(ex), color=theme.DANGER)]
            return
        direct = active['conv']['kind'] == 'direct' if active['conv'] else True
        out, last_day, last_sender = [], None, None
        for m in rows:
            d = m['created_at'].date()
            if d != last_day:
                out.append(ft.Container(alignment=ft.Alignment(0, 0), padding=ft.Padding(left=0, right=0, top=6, bottom=2),
                                        content=ft.Container(bgcolor='#E3E5EE', border_radius=10, padding=ft.Padding(left=10, right=10, top=2, bottom=2),
                                                             content=ft.Text(day_label(d), size=10.5, color=theme.TEXT_MUTED))))
                last_day, last_sender = d, None
            show_name = (not direct) and (m['sender'] != last_sender)
            out.append(bubble(m, show_name, direct))
            last_sender = None if m['system'] else m['sender']
        msgs_col.controls = out or [ft.Container(padding=30, alignment=ft.Alignment(0, 0), content=ft.Text('ابدأ المحادثة بإرسال أول رسالة 👋', color=theme.TEXT_MUTED))]
        if mark_read:
            try:
                services.chat_mark_read(cid)
            except Exception:
                pass

    def open_conversation(conv_id):
        active['id'] = conv_id
        refresh_list()
        active['conv'] = next((c for c in convs['rows'] if c['id'] == conv_id), None)
        c = active['conv']
        if not c:
            return
        header.visible = True; placeholder.visible = False; chat_box.visible = True
        head_title.value = c['title']
        head_avatar.content = _avatar(c['title'], 38)
        if c['kind'] == 'group':
            head_sub.value = f"مجموعة - {c['members']} عضو"
            head_actions.controls = [ft.IconButton(icon=ft.Icons.GROUP_OUTLINED, tooltip='أعضاء المجموعة', on_click=lambda e: open_group_info()),
                                     ft.IconButton(icon=ft.Icons.EXIT_TO_APP, icon_color=theme.DANGER, tooltip='مغادرة المجموعة', on_click=lambda e: leave_group())]
        else:
            head_sub.value = 'محادثة فردية'
            head_actions.controls = []
        refresh_messages()
        refresh_list()
        page.update()
        try:
            page.run_task(composer.focus)
        except Exception:
            pass

    # ===================================================================== الإرسال والمرفقات
    composer = ft.TextField(hint_text='اكتب رسالة... (Enter للإرسال، Shift+Enter لسطر جديد)', multiline=True, min_lines=1, max_lines=4, shift_enter=True, expand=True,
                            content_padding=ft.Padding(left=12, right=12, top=10, bottom=10), border_radius=20)
    pending_name = ft.Text('', size=12.5, weight=ft.FontWeight.BOLD, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
    pending_size = ft.Text('', size=11, color=theme.TEXT_MUTED)
    pending_row = ft.Container(visible=False, bgcolor=theme.PRIMARY_LIGHT, border_radius=10, padding=ft.Padding(left=10, right=6, top=4, bottom=4),
                               content=ft.Row([ft.Icon(ft.Icons.ATTACH_FILE, color=theme.PRIMARY, size=18), ft.Column([pending_name, pending_size], spacing=0, tight=True),
                                               ft.Container(expand=True),
                                               ft.IconButton(icon=ft.Icons.CLOSE, icon_size=16, tooltip='إلغاء المرفق', on_click=lambda e: set_pending(None))], spacing=8))

    def set_pending(path):
        pending['path'] = path
        pending_row.visible = bool(path)
        if path:
            pending_name.value = os.path.basename(path)
            try:
                pending_size.value = _size_text(os.path.getsize(path))
            except OSError:
                pending_size.value = ''
        page.update()

    async def pick_file(e=None):
        path = await theme.pick_file(page, 'اختر ملف لإرساله', max_mb=services.CHAT_MAX_FILE_MB)
        if path:
            ext = os.path.splitext(path)[1].lower()
            if ext in services.CHAT_BLOCKED_EXT:
                snack(f'نوع الملف ({ext}) مش مسموح إرساله لدواعي الأمان'); return
            try:
                if os.path.getsize(path) > services.CHAT_MAX_FILE_MB * 1024 * 1024:
                    snack(f'حجم الملف أكبر من {services.CHAT_MAX_FILE_MB} ميجا'); return
            except OSError:
                pass
            set_pending(path)

    def do_send(e=None):
        if busy['send'] or not active['id']:
            return
        text = (composer.value or '').strip()
        if not text and not pending['path']:
            return
        busy['send'] = True
        try:
            services.chat_send(active['id'], text, pending['path'])
            composer.value = ''
            pending['path'] = None; pending_row.visible = False
            refresh_messages(); refresh_list()
        except Exception as ex:
            snack(str(ex))
        finally:
            busy['send'] = False
        page.update()
        try:
            page.run_task(composer.focus)
        except Exception:
            pass

    composer.on_submit = do_send
    send_btn = ft.IconButton(icon=ft.Icons.SEND, icon_color='#FFFFFF', bgcolor=theme.PRIMARY, tooltip='إرسال', on_click=do_send)
    attach_btn = ft.IconButton(icon=ft.Icons.ATTACH_FILE, tooltip='إرفاق ملف (حتى 25 ميجا)', on_click=pick_file)

    # ===================================================================== محادثة / مجموعة جديدة
    def user_picker(multi, selected=None, on_pick=None):
        """قايمة مستخدمين بحث + (اختيار واحد أو تشيك بوكس متعدد)."""
        users = services.chat_users()
        checks = {u['username']: ft.Checkbox(label=f"{u['full_name']}  ({u['username']})", value=bool(selected and u['username'] in selected)) for u in users}
        sf = ft.TextField(hint_text='بحث عن مستخدم', prefix_icon=ft.Icons.SEARCH, dense=True)
        col = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, height=300)

        def render(e=None):
            q = (sf.value or '').strip().lower()
            if multi:
                col.controls = [cb for u, cb in checks.items() if not q or q in cb.label.lower()]
            else:
                col.controls = [ft.Container(ink=True, border_radius=8, padding=ft.Padding(left=8, right=8, top=8, bottom=8), on_click=lambda ev, un=u['username']: on_pick(un),
                                             content=ft.Row([_avatar(u['full_name'], 34), ft.Column([ft.Text(u['full_name'], weight=ft.FontWeight.BOLD), ft.Text(u['username'], size=11, color=theme.TEXT_MUTED)], spacing=0)], spacing=10))
                                for u in users if not q or q in (u['full_name'] + u['username']).lower()]
            if not col.controls:
                col.controls = [ft.Text('مفيش مستخدمين', color=theme.TEXT_MUTED)]
            page.update()
        sf.on_change = render
        return sf, col, checks, render

    def open_new_direct():
        def pick(username):
            try:
                cid = services.chat_get_or_create_direct(username)
                close(dlg); open_conversation(cid)
            except Exception as ex:
                snack(str(ex))
        sf, col, _checks, render = user_picker(False, on_pick=pick)
        dlg = ft.AlertDialog(modal=True, title=ft.Text('محادثة جديدة'), content=ft.Container(width=420, content=ft.Column([sf, col], tight=True, spacing=8)),
                             actions=[ft.TextButton('إلغاء', on_click=lambda e: close(dlg))])
        page.overlay.append(dlg); dlg.open = True
        render()

    def open_new_group():
        sf, col, checks, render = user_picker(True)
        title_f = ft.TextField(label='اسم المجموعة *', autofocus=True)
        err = ft.Text('', color=theme.DANGER, visible=False, size=12)

        def create(e):
            try:
                cid = services.chat_create_group(title_f.value, [u for u, cb in checks.items() if cb.value])
                close(dlg); open_conversation(cid)
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()
        dlg = ft.AlertDialog(modal=True, title=ft.Text('مجموعة جديدة'),
                             content=ft.Container(width=440, content=ft.Column([title_f, ft.Text('الأعضاء', weight=ft.FontWeight.BOLD), sf, col, err], tight=True, spacing=8)),
                             actions=[ft.TextButton('إلغاء', on_click=lambda e: close(dlg)), ft.FilledButton('إنشاء المجموعة', icon=ft.Icons.GROUP_ADD, bgcolor=theme.PRIMARY, on_click=create)])
        page.overlay.append(dlg); dlg.open = True
        render()

    def open_group_info():
        try:
            info = services.chat_group_info(active['id'])
        except Exception as ex:
            snack(str(ex)); return
        selected = {m['username'] for m in info['members']}
        sf, col, checks, render = user_picker(True, selected)
        title_f = ft.TextField(label='اسم المجموعة', value=info['title'] or '', disabled=not info['can_edit'])
        err = ft.Text('', color=theme.DANGER, visible=False, size=12)
        creator_name = next((m['full_name'] for m in info['members'] if m['username'] == info['created_by']), info['created_by'])
        members_text = '، '.join(m['full_name'] for m in info['members'])

        def save(e):
            try:
                services.chat_update_group(info['id'], title_f.value, [u for u, cb in checks.items() if cb.value])
                close(dlg); open_conversation(info['id'])
            except Exception as ex:
                err.value = str(ex); err.visible = True; page.update()
        content = [title_f, ft.Text(f'المنشئ: {creator_name}', size=12, color=theme.TEXT_MUTED)]
        if info['can_edit']:
            content += [ft.Text('الأعضاء (علّم اللي عايزهم في المجموعة)', weight=ft.FontWeight.BOLD), sf, col]
        else:
            content += [ft.Text('الأعضاء', weight=ft.FontWeight.BOLD), ft.Text(members_text, size=13)]
        content.append(err)
        dlg = ft.AlertDialog(modal=True, title=ft.Text('بيانات المجموعة'), content=ft.Container(width=440, content=ft.Column(content, tight=True, spacing=8)),
                             actions=[ft.TextButton('إغلاق', on_click=lambda e: close(dlg))] + ([ft.FilledButton('حفظ التعديلات', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save)] if info['can_edit'] else []))
        page.overlay.append(dlg); dlg.open = True
        if info['can_edit']:
            render()
        else:
            page.update()

    def leave_group():
        def confirm(e):
            try:
                services.chat_leave_group(active['id'])
                close(dlg)
                active['id'] = None; active['conv'] = None
                header.visible = False; chat_box.visible = False; placeholder.visible = True
                refresh_list(); page.update()
            except Exception as ex:
                snack(str(ex))
        dlg = ft.AlertDialog(modal=True, title=ft.Text('مغادرة المجموعة'), content=ft.Text('هتخرج من المجموعة ومش هتستقبل رسايلها. تقدر ترجع لو حد ضافك تاني.'),
                             actions=[ft.TextButton('إلغاء', on_click=lambda e: close(dlg)), ft.FilledButton('مغادرة', bgcolor=theme.DANGER, on_click=confirm)])
        page.overlay.append(dlg); dlg.open = True; page.update()

    # ===================================================================== التجميع
    chat_box = ft.Column([ft.Container(content=msgs_col, expand=True), pending_row, ft.Row([attach_btn, composer, send_btn], spacing=6, vertical_alignment=ft.CrossAxisAlignment.END)],
                         expand=True, spacing=6, visible=False)
    chat_pane = theme.card(ft.Column([header, ft.Divider(height=1), placeholder, chat_box], expand=True, spacing=6), expand=True)
    list_header = ft.Row([ft.Text('المحادثات', size=16, weight=ft.FontWeight.BOLD), ft.Container(expand=True),
                          ft.IconButton(icon=ft.Icons.PERSON_ADD_ALT_1, tooltip='محادثة جديدة', icon_color=theme.PRIMARY, on_click=lambda e: open_new_direct()),
                          ft.IconButton(icon=ft.Icons.GROUP_ADD, tooltip='مجموعة جديدة', icon_color=theme.PRIMARY, on_click=lambda e: open_new_group())], spacing=0)
    list_pane = ft.Container(width=330, content=theme.card(ft.Column([list_header, search_f, list_col], expand=True, spacing=8), expand=True))

    def poll_refresh():
        refresh_list()
        if active['id']:
            refresh_messages()
        page.update()

    search_f.on_change = lambda e: (refresh_list(), page.update())
    services.set_chat_view_refresh(poll_refresh)
    refresh_list()
    return ft.Column([
        theme.page_title('الرسائل والمحادثات', 'محادثات فردية ومجموعات بين مستخدمي النظام، مع إرفاق الملفات'),
        ft.Container(height=6),
        ft.Row([list_pane, chat_pane], expand=True, spacing=12, vertical_alignment=ft.CrossAxisAlignment.STRETCH),
    ], expand=True, spacing=6)
