"""إشعارات الشات: أيقونة رسائل في الشريط العلوي بعدّاد الرسائل غير المقروءة، وإشعار (Snackbar) بزرار "فتح"
لما توصلك رسالة جديدة وانت مش في شاشة الشات. بيفحص قاعدة البيانات كل ~4 ثواني. لو شاشة الشات مفتوحة
بيحدّثها بالرسايل الجديدة بدل الإشعار."""
import asyncio
import flet as ft
from . import services, theme


class ChatNotifier:
    def __init__(self, page, username, open_chat=None, is_chat_open=None, poll_seconds=4):
        self.page = page
        self.username = username
        self.open_chat = open_chat
        self.is_chat_open = is_chat_open or (lambda: False)
        self.poll_seconds = poll_seconds
        self.active = True
        try:
            self.last_seen = services.chat_max_message_id(username)
        except Exception:
            self.last_seen = 0
        self.badge_text = ft.Text('', size=10, color='#FFFFFF', weight=ft.FontWeight.BOLD)
        self.badge = ft.Container(content=self.badge_text, bgcolor=theme.DANGER, border_radius=9, visible=False,
                                  padding=ft.Padding(left=5, right=5, top=0, bottom=0), top=2, right=2)
        self.button = ft.IconButton(icon=ft.Icons.CHAT_BUBBLE_OUTLINE, tooltip='الرسائل والمحادثات', on_click=lambda e: self.open_chat() if self.open_chat else None)
        self.control = ft.Stack([self.button, self.badge], width=46, height=46)
        services.add_chat_listener(self.refresh_badge)
        self.refresh_badge()

    def start(self):
        try:
            self.page.run_task(self._loop)
        except Exception:
            pass          # بيئات بدون run_task (اختبارات) - بنشغّل tick() يدويًا

    def stop(self):
        self.active = False
        services.remove_chat_listener(self.refresh_badge)

    async def _loop(self):
        await asyncio.sleep(2)
        while self.active:
            try:
                self.tick()
            except Exception:
                pass
            await asyncio.sleep(self.poll_seconds)

    def refresh_badge(self):
        try:
            n = services.chat_unread_total(self.username)
        except Exception:
            return
        self.badge_text.value = str(n if n < 100 else '99+')
        self.badge.visible = n > 0
        self.button.icon = ft.Icons.CHAT_BUBBLE if n else ft.Icons.CHAT_BUBBLE_OUTLINE
        self.button.icon_color = theme.PRIMARY if n else None
        self.button.tooltip = f'الرسائل - {n} غير مقروءة' if n else 'الرسائل والمحادثات'
        try:
            self.page.update()
        except Exception:
            pass

    def tick(self):
        """بيدوّر على رسائل جديدة: لو شاشة الشات مفتوحة بيحدّثها، وإلا بيظهر إشعار."""
        if not self.active:
            return
        new = services.chat_new_messages_since(self.last_seen, self.username)
        if new:
            self.last_seen = max(m['id'] for m in new)
            if self.is_chat_open():
                services.chat_refresh_view()
            else:
                self._toast(new)
        self.refresh_badge()

    def _toast(self, new):
        last = new[-1]
        senders = {m['title'] for m in new}
        if len(new) == 1:
            text = f"💬 {last['title']}" + (f" ({last['sender_name']})" if last['group'] else '') + f": {last['text']}"
        elif len(senders) == 1:
            text = f"💬 {len(new)} رسائل جديدة من {last['title']}"
        else:
            text = f"💬 {len(new)} رسائل جديدة من {len(senders)} محادثات"
        try:
            self.page.overlay.append(ft.SnackBar(ft.Text(text[:140]), action='فتح', on_action=lambda e: self.open_chat() if self.open_chat else None, duration=6000, open=True))
            self.page.update()
        except Exception:
            pass
