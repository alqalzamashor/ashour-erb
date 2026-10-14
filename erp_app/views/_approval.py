import flet as ft
from .. import approvals, theme


def prompt(page, ex):
    """لو الخطأ «محتاج موافقة» يفتح نافذة لإرسال طلب موافقة للمدير. بيرجّع True لو الخطأ من النوع ده."""
    info = getattr(ex, 'approval', None)
    if not info:
        return False
    note = ft.TextField(label='ملاحظة للمعتمِد (اختياري)', width=380, multiline=True, min_lines=1, max_lines=3)

    def send(e):
        try:
            rid = approvals.request(info['kind'], info['amount'], info['fingerprint'], info.get('summary', ''), note.value or '')
            dlg.open = False
            page.overlay.append(ft.SnackBar(ft.Text(f'اتبعت طلب الموافقة رقم {rid}. لما المدير يعتمده كرر نفس العملية بنفس البيانات.'), open=True, duration=8000)); page.update()
        except Exception as ex2:
            page.overlay.append(ft.SnackBar(ft.Text(str(ex2)), open=True, bgcolor=theme.DANGER)); page.update()
    dlg = ft.AlertDialog(modal=True, title=ft.Text('محتاج موافقة مدير'), content=ft.Container(width=400, content=ft.Column([ft.Text(str(ex), size=13), note], tight=True, spacing=10)),
                         actions=[ft.TextButton('لا', on_click=lambda e: (setattr(dlg, 'open', False), page.update())), ft.FilledButton('إرسال طلب موافقة', bgcolor=theme.PRIMARY, on_click=send)])
    page.overlay.append(dlg); dlg.open = True; page.update()
    return True
