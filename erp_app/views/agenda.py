import calendar
import datetime
import flet as ft
from .. import services, theme
from ..agenda_notifier import KIND_ICONS, PRIORITY_COLORS, when_text

def _box_border(color, width=1):
    side = ft.border.BorderSide(width, color)
    return ft.border.Border(top=side, right=side, bottom=side, left=side)


WEEKDAYS = ['السبت', 'الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة']


def build_agenda(page: ft.Page):
    """جدول الأعمال: مواعيد ومهام بتواريخ وتنبيه قبل الموعد (قايمة + تقويم شهري). للتنظيم والمتابعة بس -
    مالوش أي تأثير محاسبي."""
    me = services.current_user() or {}
    is_admin = me.get('role') == 'admin'
    today = datetime.date.today()
    tabs = theme.SimpleTabs(page)
    state = {'month': today.replace(day=1)}

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def close(d):
        d.open = False; page.update()

    # ===================================================================== فلاتر
    view_dd = ft.Dropdown(label='العرض', width=190, value='open', options=[
        ft.dropdown.Option('open', 'القادمة والمتأخرة'), ft.dropdown.Option('today', 'النهاردة'), ft.dropdown.Option('overdue', 'المتأخرة'),
        ft.dropdown.Option('pending', 'القادمة فقط'), ft.dropdown.Option('done', 'المنجزة'), ft.dropdown.Option('cancelled', 'الملغاة'), ft.dropdown.Option('all', 'الكل')])
    kind_dd = ft.Dropdown(label='النوع', width=180, value='', options=[ft.dropdown.Option('', 'كل الأنواع')] + [ft.dropdown.Option(k, v) for k, v in services.AGENDA_KINDS.items()])
    search_f = ft.TextField(label='بحث في العنوان والوصف', width=240, prefix_icon=ft.Icons.SEARCH)
    all_sw = ft.Switch(label='جدول كل المستخدمين', value=False, visible=is_admin)
    cards = ft.Row(wrap=True, spacing=12)

    def scope():
        return 'all' if (is_admin and all_sw.value) else 'mine'

    def query_items():
        v = view_dd.value
        kw = dict(kind=kind_dd.value or None, text=search_f.value, scope=scope())
        if v == 'today':
            return services.list_agenda_items(date_from=today, date_to=today, status='open', **kw)
        if v == 'all':
            return services.list_agenda_items(**kw)
        return services.list_agenda_items(status=v, **kw)

    # ===================================================================== بطاقة موعد
    def chip(text, color=theme.TEXT_MUTED, icon=None):
        return ft.Container(content=ft.Row(([ft.Icon(icon, size=12, color=color)] if icon else []) + [ft.Text(text, size=10.5, color=color)], spacing=3, tight=True),
                            bgcolor=theme.PRIMARY_LIGHT, border_radius=10, padding=ft.Padding(left=7, right=7, top=2, bottom=2))

    def do(fn, *args, msg=None):
        try:
            fn(*args)
            refresh_all()
            if msg:
                snack(msg)
        except Exception as ex:
            snack(str(ex))

    def open_snooze(it):
        def pick(minutes):
            close(sd); do(services.snooze_agenda_item, it.id, minutes, msg='تم تأجيل التنبيه')
        opts = [('15 دقيقة', 15), ('ساعة', 60), ('3 ساعات', 180), ('بكرة', 1440), ('بعد أسبوع', 10080)]
        sd = ft.AlertDialog(modal=True, title=ft.Text('تأجيل التنبيه'),
            content=ft.Container(width=320, content=ft.Column([ft.Text(it.title, weight=ft.FontWeight.BOLD), ft.Text('التنبيه بيرجع يظهر بعد المدة دي (الموعد نفسه ما بيتغيّرش).', size=12, color=theme.TEXT_MUTED)]
                                                                  + [ft.OutlinedButton(lbl, icon=ft.Icons.SNOOZE, on_click=lambda e, m=m: pick(m)) for lbl, m in opts], tight=True, spacing=8)),
            actions=[ft.TextButton('إلغاء', on_click=lambda e: close(sd))])
        page.overlay.append(sd); sd.open = True; page.update()

    def item_card(it, compact=False):
        now = datetime.datetime.now()
        eff = services.agenda_effective_status(it, now)
        inactive = it.status != 'pending'
        bar = theme.TEXT_MUTED if inactive else (theme.DANGER if eff == 'overdue' else PRIORITY_COLORS.get(it.priority, theme.PRIMARY))
        title_t = ft.Text(it.title, weight=ft.FontWeight.BOLD, size=14, color=theme.TEXT_MUTED if inactive else None,
                          style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH) if inactive else None)
        chips = [chip(services.AGENDA_KINDS[it.kind], theme.PRIMARY_TEXT, KIND_ICONS.get(it.kind)),
                 chip((f'{it.start_at:%Y-%m-%d} طوال اليوم' if it.all_day else f'{it.start_at:%Y-%m-%d %H:%M}'), theme.TEXT_MUTED, ft.Icons.EVENT)]
        if it.status == 'pending':
            chips.append(chip(when_text(it, now), theme.DANGER if eff == 'overdue' else theme.SUCCESS, ft.Icons.SCHEDULE))
        else:
            chips.append(chip(services.AGENDA_STATUS_LABELS[it.status], theme.TEXT_MUTED))
        if it.remind_before_minutes is not None:
            lbl = dict(services.AGENDA_REMINDER_OPTIONS).get(it.remind_before_minutes, 'تنبيه')
            chips.append(chip(lbl.replace('قبل الموعد بـ ', 'تنبيه قبل ').replace('قبل الموعد ب', 'تنبيه قبل ') if it.remind_before_minutes else 'تنبيه عند الموعد', theme.WARNING, ft.Icons.NOTIFICATIONS_ACTIVE_OUTLINED))
        if it.repeat != 'none':
            chips.append(chip(services.AGENDA_REPEATS[it.repeat], theme.PRIMARY, ft.Icons.REPEAT))
        if it.assigned_to and it.assigned_to != me.get('username'):
            chips.append(chip(f'مكلَّف: {it.assigned_to}', theme.PRIMARY_TEXT, ft.Icons.PERSON_OUTLINE))
        elif is_admin and all_sw.value and it.created_by != me.get('username'):
            chips.append(chip(f'بواسطة: {it.created_by}', theme.TEXT_MUTED, ft.Icons.PERSON_OUTLINE))
        acts = []
        if it.status == 'pending':
            acts.append(ft.IconButton(icon=ft.Icons.CHECK_CIRCLE_OUTLINE, icon_color=theme.SUCCESS, tooltip='تم' + (' (وينتقل للموعد التالي)' if it.repeat != 'none' else ''),
                                      on_click=lambda e, i=it: do(services.complete_agenda_item, i.id)))
            if it.remind_before_minutes is not None:
                acts.append(ft.IconButton(icon=ft.Icons.SNOOZE, tooltip='تأجيل التنبيه', on_click=lambda e, i=it: open_snooze(i)))
            acts.append(ft.IconButton(icon=ft.Icons.EDIT_OUTLINED, tooltip='تعديل', on_click=lambda e, i=it: open_form(i.id)))
            acts.append(ft.IconButton(icon=ft.Icons.EVENT_BUSY_OUTLINED, tooltip='إلغاء الموعد', on_click=lambda e, i=it: do(services.cancel_agenda_item, i.id)))
        else:
            acts.append(ft.IconButton(icon=ft.Icons.UNDO, tooltip='إعادة فتح', on_click=lambda e, i=it: do(services.reopen_agenda_item, i.id)))
        acts.append(ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, icon_color=theme.DANGER, tooltip='حذف', on_click=lambda e, i=it: do(services.delete_agenda_item, i.id)))
        card = ft.Container(
            bgcolor=theme.CARD_BG, border_radius=10, border=ft.Border.all(1, theme.BORDER_LIGHT), expand=True,
            padding=ft.Padding(left=10, right=12, top=8, bottom=6),
            content=ft.Row([ft.Column([title_t] + ([ft.Text(it.description, size=12, color=theme.TEXT_MUTED, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)] if it.description else [])
                                      + [ft.Row(chips, wrap=True, spacing=6, run_spacing=4)], spacing=3, expand=True),
                            ft.Row(acts, spacing=0)], vertical_alignment=ft.CrossAxisAlignment.CENTER))
        # الشريط الملوّن على اليمين: حاوية خارجية مدوّرة (حدود بسُمك مختلف مع التدوير بتطلع مربعة)
        return ft.Container(card, padding=ft.Padding(left=0, right=5, top=0, bottom=0), bgcolor=bar, border_radius=12, clip_behavior=ft.ClipBehavior.ANTI_ALIAS)

    # ===================================================================== تبويب القايمة
    def group_of(it, now):
        if it.status != 'pending':
            return 'السجل'
        if services.agenda_effective_status(it, now) == 'overdue':
            return 'متأخر'
        d = (it.start_at.date() - today).days
        return 'النهاردة' if d == 0 else ('بكرة' if d == 1 else ('خلال الأسبوع' if d <= 7 else 'لاحقًا'))

    def show_list():
        items = query_items()
        now = datetime.datetime.now()
        order = ['متأخر', 'النهاردة', 'بكرة', 'خلال الأسبوع', 'لاحقًا', 'السجل']
        groups = {k: [] for k in order}
        for it in items:
            groups[group_of(it, now)].append(it)
        if view_dd.value in ('done', 'cancelled'):
            groups['السجل'].sort(key=lambda x: x.done_at or x.start_at, reverse=True)
        body = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        for g in order:
            rows = groups[g]
            if not rows:
                continue
            color = theme.DANGER if g == 'متأخر' else (theme.PRIMARY_TEXT if g in ('النهاردة', 'بكرة') else theme.TEXT_MUTED)
            body.controls.append(ft.Container(padding=ft.Padding(left=0, right=2, top=8, bottom=0), content=ft.Text(f'{g}  ({len(rows)})', weight=ft.FontWeight.BOLD, size=14, color=color)))
            body.controls += [item_card(it) for it in rows]
        if not body.controls:
            body.controls = [ft.Container(padding=40, alignment=ft.Alignment(0, 0), content=ft.Column([
                ft.Icon(ft.Icons.EVENT_AVAILABLE_OUTLINED, size=46, color=theme.TEXT_MUTED), ft.Text('مفيش مواعيد في العرض ده', color=theme.TEXT_MUTED),
                ft.FilledButton('موعد جديد', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=lambda e: open_form())], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10))]
        return body

    # ===================================================================== تبويب التقويم
    def show_calendar():
        first = state['month']
        weeks = calendar.Calendar(firstweekday=5).monthdatescalendar(first.year, first.month)
        grid_from, grid_to = weeks[0][0], weeks[-1][-1]
        by_day = {}
        for it in services.list_agenda_items(date_from=grid_from, date_to=grid_to, kind=kind_dd.value or None, text=search_f.value, scope=scope()):
            if it.status == 'cancelled':
                continue
            by_day.setdefault(it.start_at.date(), []).append(it)
        now = datetime.datetime.now()

        def shift(n):
            m = first.month - 1 + n
            state['month'] = first.replace(year=first.year + m // 12, month=m % 12 + 1, day=1); refresh_all()

        head = ft.Row([ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, tooltip='الشهر السابق', on_click=lambda e: shift(-1)),
                       ft.Text(f'{services._AR_MONTHS[first.month - 1]} {first.year}', size=17, weight=ft.FontWeight.BOLD, color=theme.PRIMARY_TEXT),
                       ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, tooltip='الشهر التالي', on_click=lambda e: shift(1)),
                       ft.TextButton('اليوم', icon=ft.Icons.TODAY, on_click=lambda e: (state.update(month=today.replace(day=1)), refresh_all()))], spacing=4)
        wd = ft.Row([ft.Container(expand=True, alignment=ft.Alignment(0, 0), padding=6, bgcolor=theme.PRIMARY_LIGHT, content=ft.Text(n, size=12, weight=ft.FontWeight.BOLD)) for n in WEEKDAYS], spacing=2)
        rows = [head, wd]
        for week in weeks:
            cells = []
            for d in week:
                its = by_day.get(d, [])
                in_month = d.month == first.month
                chips = []
                for it in its[:3]:
                    col = theme.TEXT_MUTED if it.status == 'done' else (theme.DANGER if services.agenda_effective_status(it, now) == 'overdue' else PRIORITY_COLORS.get(it.priority, theme.PRIMARY))
                    t = (f'{it.start_at:%H:%M} ' if not it.all_day else '') + it.title
                    chips.append(ft.Container(bgcolor=ft.Colors.with_opacity(0.14, col), border_radius=4, padding=ft.Padding(left=4, right=4, top=1, bottom=1),
                                              content=ft.Text(t, size=10, color=col, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                                                              style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH) if it.status == 'done' else None)))
                if len(its) > 3:
                    chips.append(ft.Text(f'+{len(its) - 3} أخرى', size=10, color=theme.TEXT_MUTED))
                is_today = d == today
                num = ft.Container(width=24, height=24, border_radius=12, alignment=ft.Alignment(0, 0), bgcolor=theme.PRIMARY if is_today else None,
                                   content=ft.Text(str(d.day), size=12, weight=ft.FontWeight.BOLD if (is_today or in_month) else None,
                                                   color='#FFFFFF' if is_today else (None if in_month else theme.TEXT_MUTED)))
                cells.append(ft.Container(expand=True, height=104, ink=True, border_radius=6, padding=4, on_click=lambda e, dd=d: open_day(dd),
                                          bgcolor=theme.CARD_BG if in_month else '#F7F7FA', border=_box_border(theme.PRIMARY if is_today else theme.BORDER_LIGHT),
                                          content=ft.Column([num] + chips, spacing=2, tight=True, alignment=ft.MainAxisAlignment.START)))
            rows.append(ft.Row(cells, spacing=2))
        return ft.Column(rows, spacing=2, scroll=ft.ScrollMode.AUTO, expand=True)

    # ===================================================================== يوم محدد
    def open_day(d):
        items = [it for it in services.list_agenda_items(date_from=d, date_to=d, scope=scope()) if it.status != 'cancelled']
        body = ft.Column([item_card(it) for it in items] or [ft.Text('مفيش مواعيد في اليوم ده', color=theme.TEXT_MUTED)], spacing=8, scroll=ft.ScrollMode.AUTO, tight=True)
        dd = ft.AlertDialog(modal=True, title=ft.Text(f'مواعيد {WEEKDAYS[(d.weekday() + 2) % 7]} {d:%Y-%m-%d}'),
            content=ft.Container(width=640, height=min(460, 100 + 100 * len(items)), content=body),
            actions=[ft.TextButton('إغلاق', on_click=lambda e: close(dd)),
                     ft.FilledButton('إضافة موعد في اليوم ده', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=lambda e: (close(dd), open_form(None, d)))])
        page.overlay.append(dd); dd.open = True; page.update()

    # ===================================================================== نموذج الموعد
    editing = {'id': None}
    f_title = ft.TextField(label='العنوان *', width=520, autofocus=True)
    f_kind = ft.Dropdown(label='النوع', width=200, options=[ft.dropdown.Option(k, v) for k, v in services.AGENDA_KINDS.items()], value='task')
    f_date = theme.DateField('التاريخ *', page, width=170, value=today.strftime('%Y-%m-%d'))
    f_time = ft.TextField(label='الساعة (HH:MM)', width=130, value='09:00', hint_text='14:30')
    f_all = ft.Switch(label='طوال اليوم', value=False)
    f_remind = ft.Dropdown(label='التنبيه', width=250, value='60', options=[ft.dropdown.Option('none' if m is None else str(m), lbl) for m, lbl in services.AGENDA_REMINDER_OPTIONS])
    f_repeat = ft.Dropdown(label='التكرار', width=170, value='none', options=[ft.dropdown.Option(k, v) for k, v in services.AGENDA_REPEATS.items()])
    f_priority = ft.Dropdown(label='الأولوية', width=140, value='normal', options=[ft.dropdown.Option(k, v) for k, v in services.AGENDA_PRIORITIES.items()])
    f_assign = ft.Dropdown(label='لمين', width=220, value='', options=[])
    f_desc = ft.TextField(label='وصف / ملاحظات', multiline=True, min_lines=2, max_lines=4, width=520)
    f_hint = ft.Text('', size=12, color=theme.TEXT_MUTED)
    f_err = ft.Text('', color=theme.DANGER, visible=False, size=12)

    def on_all_day(e=None):
        f_time.disabled = f_all.value
        f_hint.value = f'الموعد "طوال اليوم" بيتنبّه له الساعة {services.AGENDA_ALL_DAY_HOUR}:00 صباحًا (ناقص مدة التنبيه).' if f_all.value else ''
        page.update()
    f_all.on_change = on_all_day

    def parse_dt():
        d = datetime.datetime.strptime((f_date.value or '').strip(), '%Y-%m-%d') if (f_date.value or '').strip() else None
        if not d:
            raise ValueError('حدد تاريخ الموعد')
        if f_all.value:
            return d
        try:
            hh, mm = [int(x) for x in (f_time.value or '').strip().split(':')]
            return d.replace(hour=hh, minute=mm)
        except Exception:
            raise ValueError('اكتب الساعة بصيغة HH:MM (مثلًا 14:30)')

    def save(e):
        try:
            remind = None if f_remind.value == 'none' else int(f_remind.value)
            kw = dict(title=f_title.value, start_at=parse_dt(), kind=f_kind.value, description=f_desc.value, all_day=f_all.value, remind_before_minutes=remind,
                      repeat=f_repeat.value, priority=f_priority.value, assigned_to=f_assign.value or None)
            if editing['id']:
                services.update_agenda_item(editing['id'], **kw); msg = 'تم تعديل الموعد'
            else:
                services.create_agenda_item(**kw); msg = 'تم إضافة الموعد'
            close(form_dlg); refresh_all(); snack(msg)
        except Exception as ex:
            f_err.value = str(ex); f_err.visible = True; page.update()

    form_dlg = ft.AlertDialog(modal=True, title=ft.Text('موعد جديد'),
        content=ft.Container(width=580, content=ft.Column([
            f_title, ft.Row([f_kind, f_priority], wrap=True, spacing=10), ft.Row([f_date.control, f_time, f_all], wrap=True, spacing=10), f_hint,
            ft.Row([f_remind, f_repeat], wrap=True, spacing=10), f_assign, f_desc, f_err], tight=True, spacing=10, scroll=ft.ScrollMode.AUTO, height=520)),
        actions=[ft.TextButton('إلغاء', on_click=lambda e: close(form_dlg)), ft.FilledButton('حفظ', icon=ft.Icons.SAVE_OUTLINED, bgcolor=theme.PRIMARY, on_click=save)])
    page.overlay.append(form_dlg)

    def open_form(item_id=None, preset_date=None):
        editing['id'] = item_id
        users = [u for u in services.list_users() if u.is_active]
        f_assign.options = [ft.dropdown.Option('', 'أنا')] + [ft.dropdown.Option(u.username, u.full_name or u.username) for u in users if u.username != me.get('username')]
        f_err.visible = False
        if item_id:
            it = services.get_agenda_item(item_id)
            form_dlg.title.value = 'تعديل الموعد'
            f_title.value = it.title; f_kind.value = it.kind; f_priority.value = it.priority; f_desc.value = it.description or ''
            f_date.value = it.start_at.strftime('%Y-%m-%d'); f_time.value = it.start_at.strftime('%H:%M'); f_all.value = bool(it.all_day)
            f_remind.value = 'none' if it.remind_before_minutes is None else str(it.remind_before_minutes)
            f_repeat.value = it.repeat; f_assign.value = it.assigned_to if it.assigned_to != me.get('username') else ''
        else:
            form_dlg.title.value = 'موعد جديد'
            f_title.value = ''; f_kind.value = 'task'; f_priority.value = 'normal'; f_desc.value = ''
            f_date.value = (preset_date or today).strftime('%Y-%m-%d'); f_time.value = '09:00'; f_all.value = False
            f_remind.value = '60'; f_repeat.value = 'none'; f_assign.value = ''
        f_time.disabled = f_all.value
        f_hint.value = ''
        form_dlg.open = True; page.update()

    # ===================================================================== تجميع الشاشة
    def refresh_all(e=None):
        sm = services.agenda_summary()
        def card(label, value, color, sub):
            return theme.stat_card(label, value, color, sub, size=24)
        cards.controls = [card('متأخرة', sm['overdue'], theme.DANGER, 'عدّى موعدها ولسه ما اتنجزتش'), card('النهاردة', sm['today'], theme.PRIMARY, 'مواعيد النهاردة'), card('خلال 7 أيام', sm['week'], theme.WARNING, 'الأيام الجاية')]
        tabs.set_tabs([('القايمة', show_list()), ('التقويم الشهري', show_calendar())], selected_index=tabs.selected_index)
        page.update()

    for c in (view_dd, kind_dd):
        c.on_change = refresh_all
    search_f.on_change = refresh_all; all_sw.on_change = refresh_all
    theme.call_without_page_update(page, refresh_all)
    return ft.Column([
        ft.Row([theme.page_title('جدول الأعمال', 'مواعيدك ومهامك بتواريخها وتنبيه قبل الموعد - للمتابعة والتنظيم بس (من غير أي تأثير محاسبي)'),
                ft.Container(expand=True), ft.FilledButton('موعد جديد', icon=ft.Icons.ADD, bgcolor=theme.PRIMARY, on_click=lambda e: open_form())]),
        ft.Container(height=6), cards,
        ft.Row([view_dd, kind_dd, search_f, all_sw], spacing=10),
        ft.Container(height=4), tabs.control,
    ], expand=True, spacing=8)
