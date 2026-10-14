import os
import flet as ft
from .. import services, theme, chart_migration as M


def build_chart_import(page: ft.Page):
    """تطبيق شجرة الحسابات الجديدة على قاعدة البيانات الحالية: معاينة ثم تنفيذ بنسخة احتياطية تلقائية.
    بيحوّل كل ربط على حساب قديم (إعدادات المحاسبة، طرق الدفع، الأصناف، العقود، الموازنات...) للحساب الجديد المقابل."""
    state = {'path': None, 'rows': None}
    file_t = ft.Text('الشجرة الجديدة المدمجة في البرنامج (203 حساب)', size=13, weight=ft.FontWeight.BOLD)
    move_sw = ft.Switch(label='انقل القيود والحركات القديمة للحسابات الجديدة المقابلة', value=True)
    remove_sw = ft.Switch(label='احذف الحسابات القديمة اللي بقت من غير أي استخدام', value=True)
    summary = ft.Column(spacing=10)
    status = ft.Text('', size=12)

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    async def pick_file(e=None):
        path = await theme.pick_file(page, 'اختر ملف شجرة الحسابات (Excel)', ['xlsx'])
        if path:
            state['path'] = path; file_t.value = os.path.basename(path); refresh_plan()

    def use_builtin(e=None):
        state['path'] = None; file_t.value = 'الشجرة الجديدة المدمجة في البرنامج (203 حساب)'; refresh_plan()

    def card(label, value, color=None, sub=''):
        return theme.card(ft.Column([ft.Text(label, size=12, color=theme.TEXT_MUTED), ft.Text(str(value), size=22, weight=ft.FontWeight.BOLD, color=color),
                                     ft.Text(sub, size=11, color=theme.TEXT_MUTED)], spacing=0, tight=True), padding=14)

    def refresh_plan(e=None):
        try:
            rows, _w = M.load_chart_rows(state['path'])
            state['rows'] = rows
            plan = M.plan_chart_import(rows, move_sw.value, remove_sw.value)
        except Exception as ex:
            summary.controls = [ft.Container(bgcolor=theme.DANGER_LIGHT, border_radius=10, padding=12, content=ft.Text(f'تعذرت قراءة الملف: {ex}', color=theme.DANGER))]
            apply_btn.disabled = True; page.update(); return
        apply_btn.disabled = False
        mp = plan['mapping']
        used = [m for m in mp if m['journal_lines'] or m['other_refs']]
        tbl = ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['الحساب القديم', 'يتحوّل إلى', 'قيود عليه', 'ربط (إعدادات/أصناف/عقود...)']],
                           rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(f"{m['old_code']} - {m['old_name']}", size=12)),
                                                   ft.DataCell(ft.Text(f"{m['new_code']} - {m['new_name']}" if m['new_code'] else m['new_name'], size=12, color=None if m['new_code'] else theme.DANGER)),
                                                   ft.DataCell(ft.Text(str(m['journal_lines']))), ft.DataCell(ft.Text(str(m['other_refs'])))]) for m in mp], heading_row_height=36, data_row_min_height=32)
        custom = plan['custom_accounts']
        summary.controls = [
            ft.Row([card('حسابات هتتضاف', plan['to_create'], theme.SUCCESS, f"من {plan['total_rows']} حساب في الشجرة"), card('حسابات موجودة هتتحدّث', plan['to_update'], theme.PRIMARY, 'نفس الكود - الاسم والنوع والأب'),
                    card('قيود هتتنقل', plan['journal_lines_to_move'], theme.WARNING, 'لحسابات جديدة مقابلة' if move_sw.value else 'مش هتتنقل (الاختيار مقفول)'),
                    card('حسابات قديمة افتراضية', len(mp), theme.TEXT_MUTED, f'{len(used)} منها مستخدم')], wrap=True, spacing=12),
            *([ft.Container(bgcolor=theme.WARNING_LIGHT, border_radius=10, padding=12, content=ft.Text('مفيش حسابات قديمة افتراضية في القاعدة دي - هتتضاف الشجرة الجديدة وبس.', color=theme.WARNING_TEXT, size=12))] if not mp else
              [theme.card(ft.Column([theme.section_title('تحويل الحسابات القديمة للجديدة', ft.Icons.SWAP_HORIZ), theme.h_scroll(tbl)], spacing=8))]),
            *([theme.card(ft.Column([ft.Text(f'حسابات مخصصة عندك ({len(custom)}) هتفضل زي ما هي وتتنقل تحت المجموعة المناسبة:', weight=ft.FontWeight.BOLD, size=13)] +
                                    [ft.Text(f"{c['code']} - {c['name']}  ←  تحت {c['new_parent_code'] or '-'}", size=12, color=theme.TEXT_MUTED) for c in custom[:12]] +
                                    ([ft.Text(f'... و{len(custom) - 12} حساب تاني', size=12, color=theme.TEXT_MUTED)] if len(custom) > 12 else []), spacing=3))] if custom else []),
        ]
        page.update()

    def show_report(rep):
        def line(label, value, color=None):
            return ft.Row([ft.Text(label, size=13), ft.Container(expand=True), ft.Text(str(value), size=13, weight=ft.FontWeight.BOLD, color=color)])
        body = [line('حسابات اتضافت', rep['created'], theme.SUCCESS), line('حسابات اتحدّثت', rep['updated']), line('قيود اتنقلت للحسابات الجديدة', rep['journal_lines_moved']),
                line('حسابات قديمة اتحذفت', len(rep['removed'])), line('طرق دفع اتحوّلت', len(rep['payment_methods'])), line('حقول رواتب/مخصصات اتوزّعت على حسابات متخصصة', rep['payroll_overrides']),
                ft.Divider(height=1), ft.Text(f"إجمالي القيود بعد التحويل: مدين {rep['totals'][0]:,.2f} = دائن {rep['totals'][1]:,.2f} (مطابق لما قبل)", size=12, color=theme.SUCCESS)]
        if rep['kept']:
            body += [ft.Text(f"حسابات قديمة فضلت لإنها لسه مستخدمة ({len(rep['kept'])}):", weight=ft.FontWeight.BOLD, color=theme.WARNING)] + [ft.Text(f"{k['code']} - {k['name']} ({k['refs']} استخدام)", size=12, color=theme.TEXT_MUTED) for k in rep['kept']]
        if rep['reparented']:
            body += [ft.Text(f"حسابات مخصصة اتنقلت تحت مجموعة جديدة ({len(rep['reparented'])}):", weight=ft.FontWeight.BOLD)] + [ft.Text(f"{c} - {n}  ←  تحت {p}", size=12, color=theme.TEXT_MUTED) for c, n, p in rep['reparented'][:10]]
        for w in rep['warnings']:
            body.append(ft.Text('تنبيه: ' + w, size=12, color=theme.DANGER))
        if rep['backup']:
            body.append(ft.Text(f"نسخة احتياطية قبل التحويل: {rep['backup']}", size=11, color=theme.TEXT_MUTED, selectable=True))
        d = ft.AlertDialog(modal=True, title=ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, color=theme.SUCCESS), ft.Text('تم تطبيق الشجرة الجديدة', weight=ft.FontWeight.BOLD)], spacing=8),
                           content=ft.Container(width=560, content=ft.Column(body, tight=True, spacing=8, scroll=ft.ScrollMode.AUTO, height=min(520, 120 + 36 * len(body)))),
                           actions=[ft.FilledButton('تمام', bgcolor=theme.PRIMARY, on_click=lambda e: (setattr(d, 'open', False), refresh_plan()))])
        page.overlay.append(d); d.open = True; page.update()

    def do_apply(e):
        confirm = ft.AlertDialog(modal=True, title=ft.Text('تأكيد تطبيق الشجرة الجديدة'),
            content=ft.Container(width=460, content=ft.Column([
                ft.Text('هتتضاف الشجرة الجديدة وتتحوّل كل الروابط على الحسابات القديمة للجديدة' + (' وتتنقل القيود القديمة' if move_sw.value else '') + (' وتتحذف الحسابات القديمة غير المستخدمة' if remove_sw.value else '') + '.', size=13),
                ft.Text('هيتعمل تلقائي نسخة احتياطية من قاعدة البيانات قبل التنفيذ، ولو حصل أي خطأ مفيش حاجة بتتغيّر.', size=12, color=theme.TEXT_MUTED)], tight=True, spacing=8)),
            actions=[ft.TextButton('إلغاء', on_click=lambda ev: (setattr(confirm, 'open', False), page.update())), ft.FilledButton('تطبيق الآن', icon=ft.Icons.PLAY_ARROW, bgcolor=theme.DANGER, on_click=lambda ev: run(confirm))])
        page.overlay.append(confirm); confirm.open = True; page.update()

    def run(confirm):
        confirm.open = False; status.value = 'جاري التطبيق...'; status.color = theme.TEXT_MUTED; page.update()
        try:
            rep = M.apply_chart_import(state['rows'], move_sw.value, remove_sw.value, backup=True)
            status.value = ''; show_report(rep)
        except Exception as ex:
            status.value = f'اتلغى التنفيذ ومفيش حاجة اتغيّرت: {ex}'; status.color = theme.DANGER; page.update()

    apply_btn = ft.FilledButton('تطبيق الشجرة', icon=ft.Icons.ACCOUNT_TREE_OUTLINED, bgcolor=theme.PRIMARY, on_click=do_apply)
    move_sw.on_change = refresh_plan; remove_sw.on_change = refresh_plan
    refresh_plan()
    return ft.Column([
        theme.page_title('تطبيق شجرة الحسابات الجديدة', 'إضافة الشجرة الجديدة وتحويل أي ربط على حساب قديم للحساب الجديد المقابل - بمعاينة ونسخة احتياطية'),
        ft.Container(height=6),
        theme.card(ft.Column([ft.Row([ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, color=theme.PRIMARY), file_t, ft.Container(expand=True),
                                      ft.OutlinedButton('الشجرة المدمجة', icon=ft.Icons.HOME_OUTLINED, on_click=use_builtin),
                                      ft.OutlinedButton('اختيار ملف Excel آخر', icon=ft.Icons.UPLOAD_FILE, on_click=pick_file)], spacing=8),
                              move_sw, remove_sw, ft.Row([apply_btn, status], spacing=12)], spacing=8)),
        summary,
    ], expand=True, spacing=10, scroll=ft.ScrollMode.AUTO)
