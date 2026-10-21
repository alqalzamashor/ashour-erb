import asyncio
import datetime
import flet as ft
from .. import services, sounds, theme

KIND_COLORS = {'item_void': theme.DANGER, 'order_void': theme.DANGER, 'item_return': theme.WARNING, 'invoice_void': theme.DANGER}
TYPE_ICONS = {'dine_in': ft.Icons.RESTAURANT, 'takeaway': ft.Icons.TAKEOUT_DINING_OUTLINED, 'delivery': ft.Icons.DELIVERY_DINING_OUTLINED}


def build_kitchen(page: ft.Page):
    """شاشة المطبخ: تذاكر الطلبات المبعوتة (الأقدم أولًا) + إشعارات الإلغاء والمرتجعات بتفضل ظاهرة لحد ما المطبخ يضغط "تم الاطلاع"."""
    state = {'alive': True, 'sig': None, 'dl': None}
    dl_banner = ft.Container(visible=False, padding=10, border_radius=10, bgcolor=theme.WARNING_LIGHT,
                             content=ft.Row([ft.Icon(ft.Icons.DELIVERY_DINING_OUTLINED, color=theme.WARNING_TEXT), ft.Text('', size=14, weight=ft.FontWeight.BOLD, color=theme.WARNING_TEXT)], spacing=8))
    tickets_col = ft.Row([], wrap=True, spacing=12, run_spacing=12, vertical_alignment=ft.CrossAxisAlignment.START)
    events_col = ft.Column([], spacing=8)
    count_txt = ft.Text('', size=12, color=theme.TEXT_MUTED)
    events_title = ft.Text('', size=15, weight=ft.FontWeight.BOLD, color=theme.DANGER)

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def served(ids):
        try:
            services.mark_items_served(ids)
            refresh(force=True)
        except Exception as ex:
            snack(str(ex))

    def ack(ids):
        try:
            services.acknowledge_kitchen_events(ids)
            refresh(force=True)
        except Exception as ex:
            snack(str(ex))

    def refresh(force=False, update=True):
        data = services.kitchen_board()
        n_dl = data.get('delivery_new', 0)
        if state['dl'] is not None and n_dl > state['dl']:
            sounds.play('done')
        state['dl'] = n_dl
        dl_banner.visible = n_dl > 0
        dl_banner.content.controls[1].value = f'{n_dl} طلب توصيل جديد مستني القبول (من شاشة «طلبات التوصيل»)'
        sig = (tuple((t['order_id'], tuple(i['id'] for i in t['items'])) for t in data['tickets']), tuple(e['id'] for e in data['events']), n_dl)
        if sig == state['sig'] and not force:
            _refresh_times(data)
            return
        state['sig'] = sig
        now = datetime.datetime.now()
        cards = []
        for t in data['tickets']:
            mins = int((now - t['since']).total_seconds() // 60)
            where = f"طاولة {t['table_number']}" if t['table_number'] else services.RESTAURANT_ORDER_TYPES.get(t['order_type'], '')
            late = mins >= 15
            items = [ft.Row([ft.Text(f"{i['quantity']:g} ×", weight=ft.FontWeight.BOLD, size=15), ft.Column([ft.Text(i['name'], size=14, weight=ft.FontWeight.BOLD)] + ([ft.Text(f"• {i['note']}", size=12, color=theme.WARNING)] if i['note'] else []), spacing=0, expand=True),
                            ft.IconButton(ft.Icons.CHECK_CIRCLE_OUTLINE, icon_color=theme.SUCCESS, tooltip='جاهز', on_click=lambda e, iid=i['id']: served([iid]))], spacing=6) for i in t['items']]
            cards.append(ft.Container(width=300, padding=12, border_radius=12, bgcolor=theme.DANGER_LIGHT if late else theme.CARD_BG,
                                      border=ft.border.Border(*(ft.border.BorderSide(2, theme.DANGER if late else theme.PRIMARY) for _ in range(4))),
                                      content=ft.Column([ft.Row([ft.Icon(TYPE_ICONS.get(t['order_type'], ft.Icons.RESTAURANT), color=theme.PRIMARY), ft.Text(where, size=16, weight=ft.FontWeight.BOLD, expand=True),
                                                                 ft.Text(f"{mins} د", size=13, weight=ft.FontWeight.BOLD, color=theme.DANGER if late else theme.TEXT_MUTED)]),
                                                         ft.Text(t['number'] + (f" - {t['customer_name']}" if t['customer_name'] else ''), size=11, color=theme.TEXT_MUTED), ft.Divider(height=6)] + items +
                                                        [ft.FilledButton('الكل جاهز', icon=ft.Icons.DONE_ALL, bgcolor=theme.SUCCESS, on_click=lambda e, ids=[i['id'] for i in t['items']]: served(ids))], spacing=4)))
        tickets_col.controls = cards or [ft.Text('مفيش طلبات قيد التحضير', color=theme.TEXT_MUTED)]
        count_txt.value = f"{len(data['tickets'])} طلب قيد التحضير"
        ev = []
        for e in data['events']:
            where = f"طاولة {e['table_number']}" if e['table_number'] else services.RESTAURANT_ORDER_TYPES.get(e['order_type'], '')
            color = KIND_COLORS.get(e['kind'], theme.DANGER)
            ev.append(ft.Container(padding=10, border_radius=10, bgcolor=ft.Colors.with_opacity(0.08, color), border=ft.border.Border(*(ft.border.BorderSide(1.5, color) for _ in range(4))),
                                   content=ft.Row([ft.Icon(ft.Icons.REPORT_PROBLEM_OUTLINED, color=color),
                                                   ft.Column([ft.Text(f"{e['kind_label']} - {where}", size=13, weight=ft.FontWeight.BOLD, color=color),
                                                              ft.Text(f"{e['quantity']:g} × {e['product_name']}", size=13, weight=ft.FontWeight.BOLD),
                                                              ft.Text(f"{e['reason']}  •  {e['created_at']:%H:%M}" + (f"  •  اعتماد: {e['approved_by']}" if e['approved_by'] else ''), size=11, color=theme.TEXT_MUTED)], spacing=1, expand=True),
                                                   ft.FilledButton('تم الاطلاع', bgcolor=color, on_click=lambda ev_, eid=e['id']: ack([eid]))], spacing=8)))
        events_col.controls = ev or [ft.Text('مفيش إشعارات جديدة', color=theme.TEXT_MUTED)]
        events_title.value = f"إلغاءات ومرتجعات جديدة ({len(data['events'])})" if data['events'] else 'إلغاءات ومرتجعات'
        events_title.color = theme.DANGER if data['events'] else theme.TEXT_MUTED
        if update:
            page.update()

    def _refresh_times(data):
        pass

    async def loop():
        while state['alive']:
            await asyncio.sleep(5)
            try:
                refresh(force=False)
            except Exception:
                pass

    root = ft.Column([
        dl_banner,
        ft.Row([theme.page_title('شاشة المطبخ', 'الطلبات المبعوتة + إشعارات إلغاء الأصناف والمرتجعات (بتتحدث تلقائيًا)'), ft.Container(expand=True), count_txt,
                ft.OutlinedButton('تحديث', icon=ft.Icons.REFRESH, on_click=lambda e: refresh(force=True))]),
        ft.Row([ft.Column([ft.Text('قيد التحضير', size=15, weight=ft.FontWeight.BOLD), tickets_col], expand=3, scroll=ft.ScrollMode.AUTO),
                theme.card(ft.Column([events_title, events_col], spacing=8, scroll=ft.ScrollMode.AUTO), expand=2)], expand=True, vertical_alignment=ft.CrossAxisAlignment.START, spacing=16),
    ], expand=True)
    theme.call_without_page_update(page, lambda: refresh(force=True, update=False))
    try:
        page.run_task(loop)
    except Exception:
        pass
    return root
