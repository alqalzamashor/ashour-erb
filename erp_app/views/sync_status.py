import flet as ft
import threading
from .. import services, theme, nodesync
from ..db import SyncOp, get_session

ST = {'pending': 'معلّقة', 'failed': 'فاشلة', 'pushed': 'اتزامنت', 'discarded': 'متجاهلة'}


def build_sync_status(page: ft.Page):
    """حالة مزامنة نسخة الفرع: عمليات معلّقة/فاشلة، آخر نجاح، زر مزامنة الآن، إعادة محاولة/تجاهل للفاشل."""
    services.require_action('sync', 'view')
    if not nodesync.is_node():
        return ft.Column([ft.Text('مزامنة الفرع', size=22, weight=ft.FontWeight.BOLD),
                          ft.Text('النسخة دي هي المركز (مش فرع). الفروع بتتسجّل بالأمر:  python sync_admin.py add-node BR02', size=13),
                          ft.Text('الفروع المسجّلة: ' + (', '.join(f"{n['node_id']} (آخر اتصال {n['last_seen'] or '-'})" for n in nodesync.list_nodes()) or 'لا يوجد'), size=13)], spacing=10)
    head = ft.Text('', size=14)
    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x, weight=ft.FontWeight.BOLD)) for x in ['العملية', 'المستخدم', 'الوقت', 'الحالة', 'رقم المركز / الخطأ', '']], rows=[])

    def snack(t):
        page.overlay.append(ft.SnackBar(ft.Text(t), open=True)); page.update()

    def refresh():
        st = nodesync.status()
        head.value = f"الفرع {st['node_id']} ← {st['hq_url']}   |   معلّقة: {st['pending']}   فاشلة: {st['failed']}   |   آخر نجاح: {st['last_ok'] or '-'}" + (f"   |   {st['last_error']}" if st['last_error'] else '')
        head.color = theme.DANGER if st['failed'] else (theme.WARNING if st['pending'] else theme.SUCCESS)
        with get_session() as s:
            ops = s.query(SyncOp).filter(SyncOp.status.in_(['pending', 'failed'])).order_by(SyncOp.id.desc()).limit(100).all() + \
                s.query(SyncOp).filter(SyncOp.status == 'pushed').order_by(SyncOp.id.desc()).limit(20).all()
            rows = []
            for o in ops:
                extra = o.error if o.status == 'failed' else (o.hq_ref or '')
                btns = []
                if o.status == 'failed':
                    btns = [ft.IconButton(ft.Icons.REPLAY, tooltip='إعادة محاولة', on_click=lambda e, u=o.uuid: retry(u)),
                            ft.IconButton(ft.Icons.BLOCK, tooltip='تجاهل (بسبب)', icon_color=theme.DANGER, on_click=lambda e, u=o.uuid: ask_discard(u))]
                rows.append(ft.DataRow(cells=[ft.DataCell(ft.Text(f"{o.fn} {o.local_ref or ''}", size=12)), ft.DataCell(ft.Text(o.username or '', size=12)),
                                              ft.DataCell(ft.Text(o.at.strftime('%Y-%m-%d %H:%M'), size=12)), ft.DataCell(ft.Text(ST.get(o.status, o.status), size=12)),
                                              ft.DataCell(ft.Text(str(extra)[:120], size=11, selectable=True)), ft.DataCell(ft.Row(btns, spacing=0))]))
        table.rows = rows

    def retry(u):
        services.require_action('sync', 'edit')
        nodesync.retry(u); refresh(); page.update()

    def ask_discard(u):
        services.require_action('sync', 'delete')
        reason = ft.TextField(label='سبب التجاهل (إجباري)', autofocus=True)
        dlg = ft.AlertDialog(modal=True, title=ft.Text('تجاهل العملية دي؟'), content=ft.Column([ft.Text('العملية مش هتتنفّذ عند المركز أبدًا. لازم تتعالج يدويًا هناك لو لسه مطلوبة.', size=12), reason], tight=True, width=380))

        def ok(e):
            try:
                nodesync.discard(u, reason.value)
            except Exception as ex:
                snack(str(ex)); return
            dlg.open = False; refresh(); page.update()
        dlg.actions = [ft.TextButton('إلغاء', on_click=lambda e: (setattr(dlg, 'open', False), page.update())), ft.FilledButton('تجاهل', on_click=ok)]
        page.overlay.append(dlg); dlg.open = True; page.update()

    def run(e):
        services.require_action('sync', 'edit')
        btn.disabled = True; head.value = 'جاري المزامنة...'; page.update()

        def work():
            r = nodesync.cycle()
            btn.disabled = False
            refresh()
            snack('اتزامن بنجاح' if r['ok'] else ('مفيش اتصال بالمركز - هتتزامن تلقائيًا لما الاتصال يرجع' if r['offline'] else (r['error'] or 'تعذرت المزامنة')))
        threading.Thread(target=work, daemon=True).start()

    btn = ft.FilledButton('زامن الآن', icon=ft.Icons.SYNC, on_click=run)
    refresh()
    return ft.Column([ft.Text('مزامنة الفرع مع المركز', size=22, weight=ft.FontWeight.BOLD), head,
                      ft.Text('الشغل بيتسجّل محليًا حتى من غير إنترنت وبيتبعت تلقائيًا. التعديل على الأصناف والعملاء والحسابات بيتم من المركز.', size=12, color=theme.TEXT_MUTED),
                      ft.Row([btn, ft.IconButton(ft.Icons.REFRESH, tooltip='تحديث', on_click=lambda e: (refresh(), page.update()))]),
                      ft.Row([table], scroll=ft.ScrollMode.AUTO)], spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
