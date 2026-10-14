import flet as ft
from .. import services, theme, data_integrity
from ..report_export import export_excel, export_pdf


def build_data_integrity(page: ft.Page):
    """فحص سلامة البيانات: بيدوّر على قيود غير متوازنة، فواتير بلا قيد، مخزون سالب، تكرار، أرصدة ولاء... (للقراءة فقط)."""
    services.require_action('data_integrity', 'view')
    st = {'r': None}
    summary = ft.Row(wrap=True, spacing=12)
    body = ft.Column(spacing=10)
    stamp = ft.Text('', size=12, color=theme.TEXT_MUTED)

    def tile(title, value, color):
        return theme.card(ft.Column([ft.Text(title, size=12, color=theme.TEXT_MUTED), ft.Text(value, size=24, weight=ft.FontWeight.BOLD, color=color)], spacing=2), padding=14)

    def run(e=None):
        try:
            r = data_integrity.run()
        except Exception as ex:
            body.controls = [ft.Text(f'تعذر الفحص: {ex}', color=theme.DANGER)]
            page.update(); return
        st['r'] = r
        ok_n = sum(1 for c in r['checks'] if not c['count'])
        summary.controls = [tile('أخطاء تحتاج معالجة', str(r['errors']), theme.DANGER if r['errors'] else theme.SUCCESS),
                            tile('تنبيهات للمراجعة', str(r['warnings']), theme.WARNING if r['warnings'] else theme.SUCCESS),
                            tile('فحوص سليمة', f"{ok_n} / {len(r['checks'])}", theme.SUCCESS)]
        stamp.value = f"آخر فحص: {r['ran_at']:%Y-%m-%d %H:%M:%S}"
        rows = []
        for c in sorted(r['checks'], key=lambda x: (not x['count'], x['severity'] != 'error')):
            if not c['count']:
                rows.append(theme.card(ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, color=theme.SUCCESS, size=20), ft.Text(c['title'], size=13), ft.Container(expand=True), ft.Text('سليم', color=theme.SUCCESS, size=12, weight=ft.FontWeight.BOLD)], spacing=8), padding=12))
                continue
            col = theme.DANGER if c['severity'] == 'error' else theme.WARNING
            more = c['count'] - len(c['items'])
            lines = [ft.Text(f"{i['ref']}  —  {i['detail']}", size=12) for i in c['items']] + ([ft.Text(f'... و{more} حالة أخرى', size=12, color=theme.TEXT_MUTED)] if more > 0 else [])
            if c['hint']:
                lines.append(ft.Text(c['hint'], size=11, color=theme.TEXT_MUTED))
            rows.append(theme.card(ft.ExpansionTile(
                title=ft.Row([ft.Icon(ft.Icons.ERROR if c['severity'] == 'error' else ft.Icons.WARNING_AMBER, color=col, size=20), ft.Text(c['title'], size=13, weight=ft.FontWeight.BOLD),
                              ft.Container(content=ft.Text(str(c['count']), size=12, color='#FFFFFF', weight=ft.FontWeight.BOLD), bgcolor=col, border_radius=10, padding=ft.Padding(left=8, right=8, top=2, bottom=2))], spacing=8),
                controls=[ft.Container(content=ft.Column(lines, spacing=4), padding=ft.Padding(left=12, right=12, top=4, bottom=10))],
                expanded=c['severity'] == 'error'), padding=4))
        body.controls = rows
        if e is not None:
            page.update()

    def export(fmt):
        try:
            if st['r'] is None:
                run()
            t = [['الفحص', 'النوع', 'العدد', 'المرجع', 'التفاصيل']]; styles = {}
            for c in st['r']['checks']:
                t.append([c['title'], 'خطأ' if c['severity'] == 'error' else 'تنبيه', c['count'], '' if c['count'] else 'سليم', ''])
                styles[len(t) - 1] = 'section' if not c['count'] else ('warn' if c['severity'] == 'error' else 'total')
                for i in c['items']:
                    t.append(['', '', '', i['ref'], i['detail']])
            data = {'table': t, 'row_styles': styles, 'col_weights': [2.4, 0.8, 0.7, 1.8, 3.2]}
            path = (export_excel if fmt == 'xlsx' else export_pdf)(data, 'data_integrity', services.downloads_dir())
            theme.open_or_download_file(page, path)
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

    run()
    return ft.Column([
        ft.Row([theme.page_title('فحص سلامة البيانات', 'مراجعة تلقائية لأخطاء القيود والفواتير والمخزون والتكرار - للقراءة فقط ولا يغيّر أي بيانات'), ft.Container(expand=True),
                ft.ElevatedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('xlsx')), ft.ElevatedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf')),
                theme.guard_submit(ft.FilledButton('إعادة الفحص', icon=ft.Icons.REFRESH, bgcolor=theme.PRIMARY, on_click=run))]),
        summary, stamp, body,
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
