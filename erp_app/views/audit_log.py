import datetime
import json
import flet as ft
from .. import services, theme, audit
from ..report_export import export_excel, export_pdf

ACTIONS = {'create': 'إنشاء', 'update': 'تعديل', 'delete': 'حذف', 'login': 'دخول', 'login_failed': 'دخول فاشل', 'backup': 'نسخ احتياطي', 'restore': 'استرجاع', 'backup_delete': 'حذف نسخة', 'backup_remote': 'رفع نسخ خارجي', 'backup_fetch': 'جلب نسخة بعيدة', 'update': 'ترقية البرنامج', 'config': 'تغيير إعدادات', 'bulk': 'عملية جماعية'}
COLORS = {'create': theme.SUCCESS, 'update': theme.PRIMARY, 'delete': theme.DANGER, 'login': theme.TEXT_MUTED, 'login_failed': theme.DANGER, 'backup': theme.SUCCESS, 'restore': theme.WARNING, 'backup_delete': theme.WARNING, 'backup_remote': theme.SUCCESS, 'backup_fetch': theme.PRIMARY, 'update': theme.WARNING, 'config': theme.PRIMARY, 'bulk': theme.WARNING}


def _changes_text(action, raw):
    if not raw:
        return ''
    try:
        d = json.loads(raw)
    except Exception:
        return raw
    if not isinstance(d, dict):
        return str(d)
    if action in ('update', 'config'):
        return ' | '.join(f"{k}: {('-' if v[0] in (None, '') else v[0])} ← {('-' if v[1] in (None, '') else v[1])}" for k, v in d.items())
    return ' | '.join(f'{k}: {v}' for k, v in d.items())


def build_audit_log(page: ft.Page):
    """سجل التدقيق: كل إنشاء/تعديل/حذف ودخول ونسخ احتياطي - مين وإمتى وإيه اللي اتغيّر (قيمة قبل ← بعد)."""
    opts = services.audit_filter_options()
    today = datetime.date.today()
    rng = theme.DateRangeField('الفترة', page, width=290)
    rng.start.value = f'{today - datetime.timedelta(days=7):%Y-%m-%d}'; rng.end.value = f'{today:%Y-%m-%d}'
    user_dd = ft.Dropdown(label='المستخدم', width=170, value='', options=[ft.dropdown.Option('', 'الكل')] + [ft.dropdown.Option(u, u) for u in opts['users']])
    act_dd = ft.Dropdown(label='العملية', width=150, value='', options=[ft.dropdown.Option('', 'الكل')] + [ft.dropdown.Option(k, v) for k, v in ACTIONS.items()])
    tbl_dd = theme.SearchableDropdown(label='الشاشة / الجدول', width=230, options=[('', 'الكل')] + [(t, audit.TABLE_NAMES.get(t, t)) for t in opts['tables']], value='', page=page)
    search_f = ft.TextField(label='بحث (رقم / اسم / قيمة)', width=220, dense=True)
    count_txt = ft.Text('', size=12, color=theme.TEXT_MUTED)
    from .. import report_engine as RE
    from ..report_viewer import ReportViewer, Mode
    viewer = ReportViewer(page, 'audit_log', 'سجل التدقيق', [
        RE.Col('at', 'الوقت', RE.DATE), RE.Col('username', 'المستخدم'), RE.Col('action_label', 'العملية', bold=True), RE.Col('table_label', 'الشاشة'),
        RE.Col('record', 'السجل'), RE.Col('details', 'التفاصيل', width=4)], modes=[Mode('by_user', 'حسب المستخدم', ['username']), Mode('by_action', 'حسب العملية', ['action_label']),
                                                                                Mode('by_screen', 'حسب الشاشة', ['table_label'])], kpis=None, show_export=False)
    st = {'rows': []}

    def d(v):
        return datetime.datetime.strptime(v, '%Y-%m-%d').date() if (v or '').strip() else None

    def run(e=None):
        rows = services.list_audit_logs(d(rng.start.value), d(rng.end.value), user_dd.value or None, act_dd.value or None, tbl_dd.value or None, search_f.value or None)
        st['rows'] = rows
        count_txt.value = f'{len(rows)} سجل' + (' (أول 3000)' if len(rows) >= 3000 else '')

        viewer.set_rows([{'at': r['at'], 'username': r['username'] or '-', 'action_label': ACTIONS.get(r['action'], r['action']),
                          'table_label': audit.TABLE_NAMES.get(r['table_name'], r['table_name']) or '-',
                          'record': f"{r['label'] or ''}" + (f" #{r['record_id']}" if r['record_id'] and not r['label'] else ''),
                          'details': _changes_text(r['action'], r['changes'])} for r in rows])
        if e is not None:
            page.update()

    def export(fmt):
        try:
            if not st['rows']:
                run()
            t = [['الوقت', 'المستخدم', 'العملية', 'الشاشة', 'السجل', 'التفاصيل']]
            for r in st['rows']:
                t.append([r['at'].strftime('%Y-%m-%d %H:%M:%S'), r['username'] or '-', ACTIONS.get(r['action'], r['action']), audit.TABLE_NAMES.get(r['table_name'], r['table_name']) or '-', r['label'] or '', _changes_text(r['action'], r['changes'])])
            data = {'table': t, 'row_styles': {}, 'col_weights': [1.6, 1.1, 1, 1.5, 1.5, 5], 'date_from': d(rng.start.value), 'date_to': d(rng.end.value)}
            path = (export_excel if fmt == 'xlsx' else export_pdf)(data, 'audit_log', services.downloads_dir())
            theme.open_or_download_file(page, path)
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

    run()
    return ft.Column([
        ft.Row([theme.page_title('سجل التدقيق', 'مين عمل إيه ومتى - إنشاء وتعديل وحذف ودخول ونسخ احتياطي (للأدمن)'), ft.Container(expand=True),
                ft.ElevatedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('xlsx')), ft.ElevatedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf'))]),
        theme.card(ft.Row([rng.control, user_dd, act_dd, tbl_dd.control, search_f, theme.guard_submit(ft.FilledButton('عرض', icon=ft.Icons.SEARCH, bgcolor=theme.PRIMARY, on_click=run)), count_txt], wrap=True, spacing=10)),
        theme.card(viewer.control, expand=True),
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
