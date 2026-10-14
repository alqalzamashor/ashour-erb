"""تنبيهات جدول الأعمال: جرس في الشريط العلوي بعدّاد (متأخر + النهاردة)، ونافذة تنبيه
بتظهر لما يجي وقت تنبيه موعد (بتتفحص كل 30 ثانية والبرنامج شغّال)، ولوحة بالمواعيد القريبة."""
import asyncio
import datetime
import flet as ft
from . import services, theme

KIND_ICONS = {'task': ft.Icons.TASK_ALT, 'meeting': ft.Icons.GROUPS_OUTLINED, 'deadline': ft.Icons.EVENT_BUSY_OUTLINED,
              'reminder': ft.Icons.ALARM, 'other': ft.Icons.EVENT_NOTE_OUTLINED}
PRIORITY_COLORS = {'high': theme.DANGER, 'normal': theme.PRIMARY, 'low': theme.TEXT_MUTED}


def when_text(it, now=None):
    """وصف مختصر لموعد الموعد بالنسبة للوقت الحالي: 'بعد 20 دقيقة' / 'النهاردة 14:30' / 'متأخر ساعتين'."""
    now = now or datetime.datetime.now()
    if it.all_day:
        d = (it.start_at.date() - now.date()).days
        if d == 0:
            return 'النهاردة (طوال اليوم)'
        if d == 1:
            return 'بكرة (طوال اليوم)'
        if d > 1:
            return f'بعد {d} يوم - {it.start_at:%Y-%m-%d}'
        return f'متأخر {-d} يوم'
    mins = int((it.start_at - now).total_seconds() // 60)
    if mins < 0:
        late = -mins
        if late < 60:
            return f'متأخر {late} دقيقة'
        if late < 1440:
            return f'متأخر {late // 60} ساعة'
        return f'متأخر {late // 1440} يوم'
    if mins < 60:
        return f'بعد {mins} دقيقة' if mins else 'دلوقتي'
    d = (it.start_at.date() - now.date()).days
    if d == 0:
        return f'النهاردة {it.start_at:%H:%M}' + (f' (بعد {mins // 60} ساعة)' if mins >= 120 else '')
    if d == 1:
        return f'بكرة {it.start_at:%H:%M}'
    return f'{it.start_at:%Y-%m-%d %H:%M}'


class AgendaNotifier:
    def __init__(self, page, username, open_agenda=None, poll_seconds=30):
        self.page = page
        self.username = username
        self.open_agenda = open_agenda
        self.poll_seconds = poll_seconds
        self.active = True
        self._alert_dlg = None
        self._first = True
        self.badge_text = ft.Text('', size=10, color='#FFFFFF', weight=ft.FontWeight.BOLD)
        self.badge = ft.Container(content=self.badge_text, bgcolor=theme.DANGER, border_radius=9, visible=False,
                                  padding=ft.Padding(left=5, right=5, top=0, bottom=0), top=2, right=2)
        self.button = ft.IconButton(icon=ft.Icons.NOTIFICATIONS_OUTLINED, tooltip='جدول الأعمال والتنبيهات', on_click=self.open_panel)
        self.control = ft.Stack([self.button, self.badge], width=46, height=46)
        services.add_agenda_listener(self.refresh_badge)
        self.refresh_badge()

    # ------------------------------------------------------------ دورة الحياة
    def start(self):
        try:
            self.page.run_task(self._loop)
        except Exception:
            pass          # بيئات بدون run_task (اختبارات) - التنبيه بيتشغّل يدويًا عن طريق tick()

    def stop(self):
        self.active = False
        services.remove_agenda_listener(self.refresh_badge)

    async def _loop(self):
        await asyncio.sleep(1.5)
        while self.active:
            try:
                self.tick()
            except Exception:
                pass
            await asyncio.sleep(self.poll_seconds)

    # ------------------------------------------------------------ الجرس
    def refresh_badge(self):
        try:
            sm = services.agenda_summary(self.username)
        except Exception:
            return
        n = sm['attention']
        self.badge_text.value = str(n if n < 100 else '99+')
        self.badge.visible = n > 0
        self.button.icon = ft.Icons.NOTIFICATIONS_ACTIVE if n else ft.Icons.NOTIFICATIONS_OUTLINED
        self.button.icon_color = theme.DANGER if sm['overdue'] else (theme.PRIMARY if n else None)
        self.button.tooltip = f"جدول الأعمال - متأخر {sm['overdue']} | النهاردة {sm['today']} | خلال 7 أيام {sm['week']}"
        self._safe_update()

    def _safe_update(self):
        try:
            self.page.update()
        except Exception:
            pass

    def _alert_open(self):
        d = self._alert_dlg
        return bool(d is not None and d.open and d in self.page.overlay)

    # ------------------------------------------------------------ فحص التنبيهات
    def tick(self):
        """بيفحص المواعيد اللي جه وقت تنبيهها وبيعرضها، وبيحدّث عدّاد الجرس."""
        if not self.active:
            return
        due = services.due_agenda_alerts(self.username)
        if due and not self._alert_open():
            self.show_alert(due)
        elif self._first and not due:
            sm = services.agenda_summary(self.username)
            if sm['attention']:
                self.page.overlay.append(ft.SnackBar(ft.Text(f"جدول الأعمال: عندك {sm['today']} موعد النهاردة" + (f" و{sm['overdue']} متأخر" if sm['overdue'] else '')), open=True))
        self._first = False
        self.refresh_badge()

    # ------------------------------------------------------------ نافذة التنبيه
    def _row(self, it, on_done, on_snooze, compact=False):
        now = datetime.datetime.now()
        eff = services.agenda_effective_status(it, now)
        color = theme.DANGER if eff == 'overdue' else PRIORITY_COLORS.get(it.priority, theme.PRIMARY)
        acts = [ft.TextButton('تم', icon=ft.Icons.CHECK_CIRCLE_OUTLINE, on_click=lambda e, i=it: on_done(i), style=ft.ButtonStyle(color=theme.SUCCESS))]
        if on_snooze:
            acts += [ft.TextButton('15 د', icon=ft.Icons.SNOOZE, tooltip='تأجيل التنبيه 15 دقيقة', on_click=lambda e, i=it: on_snooze(i, 15)),
                     ft.TextButton('ساعة', tooltip='تأجيل التنبيه ساعة', on_click=lambda e, i=it: on_snooze(i, 60)),
                     ft.TextButton('بكرة', tooltip='تأجيل التنبيه لبكرة', on_click=lambda e, i=it: on_snooze(i, 1440))]
        return ft.Container(
            border=ft.border.Border(right=ft.border.BorderSide(4, color)), bgcolor=theme.PRIMARY_LIGHT if not compact else None, border_radius=8,
            padding=ft.Padding(left=10, right=12, top=8, bottom=8),
            content=ft.Column([
                ft.Row([ft.Icon(KIND_ICONS.get(it.kind, ft.Icons.EVENT_NOTE_OUTLINED), size=18, color=color),
                        ft.Text(it.title, weight=ft.FontWeight.BOLD, size=14, expand=True),
                        ft.Text(when_text(it, now), size=12, color=color, weight=ft.FontWeight.BOLD)], spacing=8),
                *([ft.Text(it.description, size=12, color=theme.TEXT_MUTED)] if it.description else []),
                ft.Row(acts, spacing=0, wrap=True)], spacing=2, tight=True))

    def show_alert(self, due):
        ids = [i.id for i in due]
        services.mark_agenda_alerted(ids)         # التنبيه يظهر مرة واحدة (التأجيل بيرجّعه)
        col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, tight=True)
        remaining = list(due)

        def rebuild():
            col.controls = [self._row(it, finish, snooze) for it in remaining]
            if not remaining:
                dlg.open = False
            self.page.update()

        def finish(it):
            try:
                services.complete_agenda_item(it.id)
            except Exception as ex:
                self.page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True))
            remaining[:] = [x for x in remaining if x.id != it.id]
            rebuild(); self.refresh_badge()

        def snooze(it, minutes):
            try:
                services.snooze_agenda_item(it.id, minutes)
            except Exception as ex:
                self.page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True))
            remaining[:] = [x for x in remaining if x.id != it.id]
            rebuild(); self.refresh_badge()

        def close(e=None):
            dlg.open = False; self.page.update()

        def open_agenda(e=None):
            dlg.open = False; self.page.update()
            if self.open_agenda:
                self.open_agenda()

        dlg = ft.AlertDialog(
            modal=False,
            title=ft.Row([ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE, color=theme.DANGER), ft.Text(f'تنبيه: {len(due)} موعد' if len(due) > 1 else 'تنبيه موعد', weight=ft.FontWeight.BOLD)], spacing=8),
            content=ft.Container(width=520, content=col),
            actions=[ft.TextButton('فتح جدول الأعمال', icon=ft.Icons.EVENT_NOTE_OUTLINED, on_click=open_agenda), ft.TextButton('إغلاق', on_click=close)])
        col.controls = [self._row(it, finish, snooze) for it in remaining]
        self._alert_dlg = dlg
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

    # ------------------------------------------------------------ لوحة الجرس
    def open_panel(self, e=None):
        items = services.agenda_upcoming(self.username, days=7)
        now = datetime.datetime.now(); today = now.date()
        groups = {'متأخر': [], 'النهاردة': [], 'الأيام الجاية (7 أيام)': []}
        for it in items:
            eff = services.agenda_effective_status(it, now)
            groups['متأخر' if eff == 'overdue' else ('النهاردة' if it.start_at.date() == today else 'الأيام الجاية (7 أيام)')].append(it)
        col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, tight=True)

        def finish(it):
            try:
                services.complete_agenda_item(it.id)
            except Exception as ex:
                self.page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True))
            panel.open = False; self.page.update(); self.open_panel()

        for title, rows in groups.items():
            if not rows:
                continue
            col.controls.append(ft.Text(f'{title} ({len(rows)})', weight=ft.FontWeight.BOLD, color=theme.DANGER if title == 'متأخر' else theme.PRIMARY_DARK))
            col.controls += [self._row(it, finish, None, compact=True) for it in rows]
        if not col.controls:
            col.controls = [ft.Container(padding=20, content=ft.Column([ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=40, color=theme.SUCCESS),
                                                                         ft.Text('مفيش مواعيد قريبة', color=theme.TEXT_MUTED)], horizontal_alignment=ft.CrossAxisAlignment.CENTER))]

        def go(ev):
            panel.open = False; self.page.update()
            if self.open_agenda:
                self.open_agenda()

        panel = ft.AlertDialog(modal=False, title=ft.Row([ft.Icon(ft.Icons.EVENT_NOTE_OUTLINED, color=theme.PRIMARY), ft.Text('مواعيدي القريبة', weight=ft.FontWeight.BOLD)], spacing=8),
                               content=ft.Container(width=520, height=min(460, 120 + 90 * len(items)), content=col),
                               actions=[ft.TextButton('فتح جدول الأعمال', icon=ft.Icons.OPEN_IN_NEW, on_click=go),
                                        ft.TextButton('إغلاق', on_click=lambda ev: (setattr(panel, 'open', False), self.page.update()))])
        self.page.overlay.append(panel)
        panel.open = True
        self.page.update()
