"""تنبيهات تجديد الرخص والمستندات: أيقونة في الشريط العلوي بعدّاد (المنتهي + القارب على الانتهاء)، ونافذة تنبيه
بتظهر لما مستند يوصل لمرحلة تنبيه جديدة (مثلًا قبل الانتهاء بـ 90 ثم 60 ثم 30 ثم 7 أيام، وعند الانتهاء)،
ولوحة بكل المستندات اللي محتاجة تجديد. كل مستخدم بيتنبّه مرة لكل مرحلة وبيقدر يأجّل التنبيه."""
import asyncio
import datetime
import flet as ft
from . import services, theme


def days_text(days_left):
    if days_left < 0:
        d = -days_left
        return f'انتهى من {d} يوم' if d > 2 else ('انتهى من يومين' if d == 2 else 'انتهى من يوم')
    if days_left == 0:
        return 'بينتهي النهاردة'
    if days_left == 1:
        return 'بينتهي بكرة'
    if days_left == 2:
        return 'بينتهي بعد يومين'
    return f'بينتهي بعد {days_left} يوم'


def status_color(days_left):
    return theme.DANGER if days_left < 0 else (theme.WARNING if days_left <= 30 else theme.PRIMARY)


class DocumentNotifier:
    def __init__(self, page, username, open_screen=None, poll_seconds=60):
        self.page = page
        self.username = username
        self.open_screen = open_screen
        self.poll_seconds = poll_seconds
        self.active = True
        self._alert_dlg = None
        self._first = True
        self.badge_text = ft.Text('', size=10, color='#FFFFFF', weight=ft.FontWeight.BOLD)
        self.badge = ft.Container(content=self.badge_text, bgcolor=theme.DANGER, border_radius=9, visible=False,
                                  padding=ft.Padding(left=5, right=5, top=0, bottom=0), top=2, right=2)
        self.button = ft.IconButton(icon=ft.Icons.ASSIGNMENT_LATE_OUTLINED, tooltip='تجديد الرخص والمستندات', on_click=self.open_panel)
        self.control = ft.Stack([self.button, self.badge], width=46, height=46)
        services.add_document_listener(self.refresh_badge)
        self.refresh_badge()

    def start(self):
        try:
            self.page.run_task(self._loop)
        except Exception:
            pass

    def stop(self):
        self.active = False
        services.remove_document_listener(self.refresh_badge)

    async def _loop(self):
        await asyncio.sleep(2.5)
        while self.active:
            try:
                self.tick()
            except Exception:
                pass
            await asyncio.sleep(self.poll_seconds)

    def _safe_update(self):
        try:
            self.page.update()
        except Exception:
            pass

    def refresh_badge(self):
        try:
            sm = services.documents_summary()
        except Exception:
            return
        n = sm['attention']
        self.badge_text.value = str(n if n < 100 else '99+')
        self.badge.visible = n > 0
        self.button.icon_color = theme.DANGER if sm['expired'] else (theme.WARNING if n else None)
        self.button.tooltip = f"تجديد المستندات - منتهي {sm['expired']} | قارب على الانتهاء {sm['expiring']}" if n else 'تجديد الرخص والمستندات'
        self._safe_update()

    def _alert_open(self):
        d = self._alert_dlg
        return bool(d is not None and d.open and d in self.page.overlay)

    def tick(self):
        if not self.active:
            return
        due = services.due_document_alerts(self.username)
        if due and not self._alert_open():
            self.show_alert(due)
        self._first = False
        self.refresh_badge()

    # ------------------------------------------------------------ صف مستند
    def _row(self, r, actions):
        color = status_color(r['days_left'])
        return ft.Container(
            border=ft.border.Border(right=ft.border.BorderSide(4, color)), bgcolor=theme.PRIMARY_LIGHT, border_radius=8,
            padding=ft.Padding(left=10, right=12, top=8, bottom=8),
            content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.ASSIGNMENT_LATE_OUTLINED, size=18, color=color), ft.Text(r['title'], weight=ft.FontWeight.BOLD, size=14, expand=True),
                        ft.Text(days_text(r['days_left']), size=12, color=color, weight=ft.FontWeight.BOLD)], spacing=8),
                ft.Text(f"{r['type_name']} - {r['holder']}" + (f" - رقم {r['doc_number']}" if r['doc_number'] else '') + f" - ينتهي {r['expiry_date']:%Y-%m-%d}", size=12, color=theme.TEXT_MUTED),
                ft.Row(actions, spacing=0, wrap=True) if actions else ft.Container(height=0)], spacing=2, tight=True))

    # ------------------------------------------------------------ نافذة التنبيه
    def show_alert(self, due):
        services.mark_document_alerted([(r['id'], r['tier']) for r in due], self.username)
        remaining = list(due)
        col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, tight=True)

        def rebuild():
            col.controls = [self._row(r, acts(r)) for r in remaining]
            if not remaining:
                dlg.open = False
            self.page.update()

        def snooze(r, days):
            services.snooze_document_alert(r['id'], r['tier'], days, self.username)
            remaining[:] = [x for x in remaining if x['id'] != r['id']]
            rebuild()

        def renew(r):
            dlg.open = False; self.page.update()
            if self.open_screen:
                self.open_screen()

        def acts(r):
            return [ft.TextButton('فتح للتجديد', icon=ft.Icons.AUTORENEW, on_click=lambda e, x=r: renew(x), style=ft.ButtonStyle(color=theme.SUCCESS)),
                    ft.TextButton('ذكّرني بكرة', icon=ft.Icons.SNOOZE, on_click=lambda e, x=r: snooze(x, 1)),
                    ft.TextButton('بعد أسبوع', on_click=lambda e, x=r: snooze(x, 7))]

        n_exp = len([r for r in due if r['days_left'] < 0])
        title = 'تنبيه: مستندات محتاجة تجديد' if len(due) > 1 else 'تنبيه: مستند محتاج تجديد'
        dlg = ft.AlertDialog(
            modal=False,
            title=ft.Row([ft.Icon(ft.Icons.ASSIGNMENT_LATE_OUTLINED, color=theme.DANGER if n_exp else theme.WARNING), ft.Text(title, weight=ft.FontWeight.BOLD)], spacing=8),
            content=ft.Container(width=560, content=col),
            actions=[ft.TextButton('فتح شاشة التجديدات', icon=ft.Icons.OPEN_IN_NEW, on_click=lambda e: renew(None)),
                     ft.TextButton('إغلاق', on_click=lambda e: (setattr(dlg, 'open', False), self.page.update()))])
        col.controls = [self._row(r, acts(r)) for r in remaining]
        self._alert_dlg = dlg
        self.page.overlay.append(dlg)
        dlg.open = True
        self.page.update()

    # ------------------------------------------------------------ لوحة الجرس
    def open_panel(self, e=None):
        rows = services.documents_needing_attention()
        sm = services.documents_summary()
        col = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, tight=True)
        if rows:
            expired = [r for r in rows if r['days_left'] < 0]; soon = [r for r in rows if r['days_left'] >= 0]
            for title, grp, color in (('منتهية', expired, theme.DANGER), ('قاربت على الانتهاء', soon, theme.WARNING)):
                if grp:
                    col.controls.append(ft.Text(f'{title} ({len(grp)})', weight=ft.FontWeight.BOLD, color=color))
                    col.controls += [self._row(r, []) for r in grp]
        else:
            col.controls = [ft.Container(padding=20, content=ft.Column([ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=40, color=theme.SUCCESS),
                                                                         ft.Text(f"كل المستندات سارية ({sm['total']})", color=theme.TEXT_MUTED)], horizontal_alignment=ft.CrossAxisAlignment.CENTER))]

        def go(ev):
            panel.open = False; self.page.update()
            if self.open_screen:
                self.open_screen()

        panel = ft.AlertDialog(modal=False, title=ft.Row([ft.Icon(ft.Icons.ASSIGNMENT_LATE_OUTLINED, color=theme.PRIMARY), ft.Text('المستندات المحتاجة تجديد', weight=ft.FontWeight.BOLD)], spacing=8),
                               content=ft.Container(width=560, height=min(480, 120 + 80 * len(rows)), content=col),
                               actions=[ft.TextButton('فتح شاشة التجديدات', icon=ft.Icons.OPEN_IN_NEW, on_click=go),
                                        ft.TextButton('إغلاق', on_click=lambda ev: (setattr(panel, 'open', False), self.page.update()))])
        self.page.overlay.append(panel)
        panel.open = True
        self.page.update()
