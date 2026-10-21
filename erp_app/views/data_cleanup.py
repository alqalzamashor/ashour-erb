import flet as ft
from .. import services, theme, data_cleanup as C


def build_data_cleanup(page: ft.Page):
    """تنظيف قاعدة البيانات: حذف كل الحركات القديمة (مالية ومخزنية وموارد بشرية) والرجوع لقاعدة نظيفة، مع اختيار حذف البيانات
    الأساسية والرسائل والمستخدمين كمان. شجرة الحسابات والإعدادات بتفضل. نسخة احتياطية تلقائية قبل التنفيذ. للأدمن بس."""
    me = services.current_user() or {}
    if me.get('role') != 'admin':
        return ft.Column([theme.page_title('تنظيف قاعدة البيانات', 'متاح لمدير النظام فقط'), ft.Text('مش مسموح ليك بالشاشة دي.', color=theme.DANGER)], expand=True)

    master_sw = ft.Switch(label='احذف كمان البيانات الأساسية: الأصناف والعملاء والموردين والموظفين والعقود وقوائم الأسعار والموازنات', value=False)
    extras_sw = ft.Switch(label='احذف كمان الرسائل وجدول الأعمال ومتابعة تجديد المستندات', value=False)
    users_sw = ft.Switch(label='احذف باقي المستخدمين (بيفضل مدير النظام admin بس)', value=False)
    files_sw = ft.Switch(label='امسح ملفات المرفقات والتقارير المصدّرة من الجهاز', value=True)
    confirm_f = ft.TextField(label=f'اكتب "{C.CONFIRM_PHRASE}" للتأكيد', width=360, hint_text=C.CONFIRM_PHRASE)
    status = ft.Text('', size=12)
    cards = ft.Row(wrap=True, spacing=12)
    body = ft.Column(spacing=10)

    def snack(msg):
        page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    def card(label, value, color=None, sub=''):
        return theme.stat_card(label, value, color, sub)

    def size_text(n):
        return f'{n / 1024 / 1024:.1f} MB' if n >= 1024 * 1024 else f'{max(1, n // 1024)} KB'

    def refresh(e=None):
        p = C.plan(master_sw.value, extras_sw.value, users_sw.value, files_sw.value)
        cards.controls = [card('صفوف هتتحذف', f"{p['total_rows']:,}", theme.DANGER, 'من كل الحركات والاختيارات تحت'),
                          card('ملفات هتتمسح', f"{p['files'] + p['export_files']:,}", theme.WARNING, f"{size_text(p['files_size'])} مرفقات + {p['export_files']} تقرير"),
                          card('حجم قاعدة البيانات', size_text(p['db_size']), theme.PRIMARY, 'بيصغّر بعد التنظيف')]
        rows = [ft.DataRow(color=theme.DANGER_LIGHT if g['kind'] != 'حركات' else None, cells=[ft.DataCell(ft.Text(g['label'], size=13)),
                                                                                            ft.DataCell(ft.Text(g['kind'], size=12, color=theme.TEXT_MUTED)),
                                                                                            ft.DataCell(ft.Text(f"{g['rows']:,}", weight=ft.FontWeight.BOLD, color=theme.DANGER if g['rows'] else theme.TEXT_MUTED))]) for g in p['groups']]
        if p['other_users']:
            rows.append(ft.DataRow(color=theme.DANGER_LIGHT, cells=[ft.DataCell(ft.Text('المستخدمين (ما عدا admin)')), ft.DataCell(ft.Text('مستخدمين', size=12, color=theme.TEXT_MUTED)), ft.DataCell(ft.Text(str(p['other_users']), weight=ft.FontWeight.BOLD, color=theme.DANGER))]))
        body.controls = [
            theme.card(ft.Column([theme.section_title('اللي هيتحذف', ft.Icons.DELETE_SWEEP_OUTLINED),
                                  theme.h_scroll(ft.DataTable(columns=[ft.DataColumn(ft.Text(x)) for x in ['المجموعة', 'النوع', 'عدد الصفوف']], rows=rows, heading_row_height=36, data_row_min_height=32))], spacing=8)),
            theme.card(ft.Column([theme.section_title('اللي هيفضل زي ما هو', ft.Icons.VERIFIED_OUTLINED),
                                  ft.Row([ft.Container(content=ft.Text(k, size=12, color=theme.PRIMARY_TEXT), bgcolor=theme.PRIMARY_LIGHT, border_radius=10, padding=ft.Padding(left=10, right=10, top=4, bottom=4)) for k in p['kept']], wrap=True, spacing=6, run_spacing=6)], spacing=8)),
        ]
        run_btn.disabled = (confirm_f.value or '').strip() != C.CONFIRM_PHRASE
        if e is not None:
            page.update()

    def preset(master, extras, users):
        master_sw.value, extras_sw.value, users_sw.value = master, extras, users
        refresh(True)

    def report_dialog(rep):
        def line(label, value, color=None):
            return ft.Row([ft.Text(label, size=13), ft.Container(expand=True), ft.Text(str(value), size=13, weight=ft.FontWeight.BOLD, color=color)])
        top = sorted(rep['deleted'].items(), key=lambda kv: -kv[1])[:8]
        content = [line('إجمالي الصفوف المحذوفة', f"{rep['total_deleted']:,}", theme.DANGER), line('ملفات اتمسحت', rep['files_removed']),
                   line('حجم القاعدة', f"{size_text(rep['db_size_before'])} ← {size_text(rep['db_size_after'])}", theme.SUCCESS), ft.Divider(height=1),
                   ft.Text('أكتر الجداول حذفًا:', weight=ft.FontWeight.BOLD, size=12)] + [ft.Text(f'{t}: {n:,}', size=12, color=theme.TEXT_MUTED) for t, n in top]
        if rep['backup']:
            content += [ft.Divider(height=1), ft.Text('نسخة احتياطية قبل التنظيف (للرجوع: انسخها فوق data/erp.db والبرنامج مقفول):', size=12, color=theme.TEXT_MUTED), ft.Text(rep['backup'], size=11, selectable=True)]
        content.append(ft.Container(bgcolor=theme.WARNING_LIGHT, border_radius=10, padding=10, content=ft.Text('اقفل البرنامج وافتحه تاني عشان كل الشاشات تتحدّث. الترقيم هيبدأ من الأول (فاتورة S-000001، قيد JE-000001...).', size=12, color=theme.WARNING_TEXT)))
        d = ft.AlertDialog(modal=True, title=ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, color=theme.SUCCESS), ft.Text('تم تنظيف قاعدة البيانات', weight=ft.FontWeight.BOLD)], spacing=8),
                           content=ft.Container(width=560, content=ft.Column(content, tight=True, spacing=8, scroll=ft.ScrollMode.AUTO, height=min(520, 100 + 34 * len(content)))),
                           actions=[ft.FilledButton('تمام', bgcolor=theme.PRIMARY, on_click=lambda e: (setattr(d, 'open', False), confirm_f.__setattr__('value', ''), refresh(True)))])
        page.overlay.append(d); d.open = True; page.update()

    def run(e):
        if (confirm_f.value or '').strip() != C.CONFIRM_PHRASE:
            status.value = f'اكتب عبارة التأكيد بالظبط: "{C.CONFIRM_PHRASE}"'; status.color = theme.DANGER; page.update(); return
        status.value = 'جاري التنظيف... (بيعمل نسخة احتياطية الأول)'; status.color = theme.TEXT_MUTED; page.update()
        try:
            rep = C.cleanup(master_sw.value, extras_sw.value, users_sw.value, files_sw.value, backup=True, confirm=confirm_f.value)
            status.value = ''; report_dialog(rep)
        except Exception as ex:
            status.value = f'اتلغى التنفيذ ومفيش حاجة اتغيّرت: {ex}'; status.color = theme.DANGER; page.update()

    run_btn = ft.FilledButton('تنفيذ التنظيف', icon=ft.Icons.DELETE_SWEEP_OUTLINED, bgcolor=theme.DANGER, disabled=True, on_click=run)
    for sw in (master_sw, extras_sw, users_sw, files_sw):
        sw.on_change = refresh
    confirm_f.on_change = refresh
    refresh()
    return ft.Column([
        theme.page_title('تنظيف قاعدة البيانات', 'حذف الحركات القديمة والرجوع لقاعدة نظيفة - شجرة الحسابات والإعدادات بتفضل'),
        ft.Container(height=4),
        ft.Container(bgcolor=theme.DANGER_LIGHT, border_radius=12, padding=ft.Padding(left=16, right=16, top=12, bottom=12), content=ft.Row([
            ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=theme.DANGER, size=26),
            ft.Column([ft.Text('عملية حذف نهائية', weight=ft.FontWeight.BOLD, color=theme.DANGER, size=15),
                       ft.Text('بتمسح القيود والفواتير والسندات وحركات المخزون والرواتب والعهد والأصول الثابتة وكل الحركات المرتبطة بيها. بيتعمل نسخة احتياطية تلقائية قبل التنفيذ، '
                               'ومع كده اتأكد إنك عايز الحذف قبل ما تكمّل.', size=12, color='#7A1F23')], spacing=2, expand=True)], spacing=12)),
        cards,
        theme.card(ft.Column([theme.section_title('اختار مستوى التنظيف', ft.Icons.TUNE),
                              ft.Row([ft.OutlinedButton('حذف الحركات بس', icon=ft.Icons.RECEIPT_LONG_OUTLINED, on_click=lambda e: preset(False, False, False)),
                                      ft.OutlinedButton('قاعدة نظيفة تمامًا', icon=ft.Icons.CLEANING_SERVICES_OUTLINED, on_click=lambda e: preset(True, True, True))], spacing=8),
                              master_sw, extras_sw, users_sw, files_sw], spacing=6)),
        body,
        theme.card(ft.Column([theme.section_title('التأكيد', ft.Icons.SECURITY_OUTLINED), confirm_f, ft.Row([run_btn, status], spacing=12)], spacing=8)),
    ], expand=True, spacing=10, scroll=ft.ScrollMode.AUTO)
