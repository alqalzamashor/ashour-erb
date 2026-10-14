import datetime
import flet as ft
from .. import credit, services, theme
from ..report_export import export_excel, export_pdf


def build_receivables_aging(page: ft.Page):
    """أعمار ديون العملاء (أو الموردين) حسب الاستحقاق + استهلاك حد الائتمان."""
    services.require_action('receivables_aging', 'view')
    st = {'data': None}
    kind = ft.Dropdown(label='النوع', width=150, value='customer', options=[ft.dropdown.Option('customer', 'العملاء'), ft.dropdown.Option('supplier', 'الموردين')])
    as_of = ft.TextField(label='حتى تاريخ', width=150, value=datetime.date.today().isoformat())
    only_over = ft.Switch(label='المتأخر فقط', value=False)
    summary = ft.Row(wrap=True, spacing=12)
    body = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
    detail_col = ft.Column(spacing=2)

    def kpi(title, value, color=None):
        return theme.card(ft.Column([ft.Text(title, size=12, color=theme.TEXT_MUTED), ft.Text(f'{value:,.2f}', size=20, weight=ft.FontWeight.BOLD, color=color or theme.TEXT)], spacing=2), padding=12)

    def party_type():
        return kind.value or 'customer'

    def run(e=None):
        try:
            d = datetime.date.fromisoformat((as_of.value or '').strip())
        except ValueError:
            body.controls = [ft.Text('التاريخ بصيغة 2026-01-31', color=theme.DANGER)]; page.update(); return
        data = credit.aging(party_type(), as_of=d)
        st['data'] = data
        t = data['totals']
        summary.controls = [kpi('إجمالي المستحق', t['balance']), kpi('غير مستحق', t['current']), kpi('1-30 يوم', t['d30'], theme.WARNING), kpi('31-60', t['d60'], theme.WARNING),
                            kpi('61-90', t['d90'], theme.DANGER), kpi('+90', t['d90p'], theme.DANGER)] + ([kpi('دفعات مقدمة', t['unapplied'], theme.SUCCESS)] if t['unapplied'] else [])
        rows = [r for r in data['rows'] if not only_over.value or (r['balance'] - r['current']) > 0.005]
        cust = party_type() == 'customer'
        head = ft.Container(padding=8, bgcolor=theme.PRIMARY_LIGHT, content=ft.Row([ft.Text('الاسم', expand=3, weight=ft.FontWeight.BOLD)] + [ft.Text(l, expand=1, weight=ft.FontWeight.BOLD, size=12) for _, l in credit.BUCKETS] +
                                                                                   [ft.Text('الإجمالي', expand=1, weight=ft.FontWeight.BOLD, size=12)] + ([ft.Text('الحد', expand=1, weight=ft.FontWeight.BOLD, size=12)] if cust else [])))
        lines = [head]
        for r in rows:
            flag = []
            if r.get('over_limit'):
                flag.append(ft.Icon(ft.Icons.WARNING_AMBER, color=theme.DANGER, size=16, tooltip='تجاوز حد الائتمان'))
            if r.get('credit_hold'):
                flag.append(ft.Icon(ft.Icons.BLOCK, color=theme.DANGER, size=16, tooltip='موقوف عن الآجل'))
            lines.append(ft.Container(padding=6, border=ft.border.Border(bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT)), ink=True, on_click=lambda ev, rr=r: show_details(rr),
                                      content=ft.Row([ft.Row([ft.Text(r['party'], size=13)] + flag, expand=3, spacing=4)] + [ft.Text(f"{r[k]:,.2f}" if r[k] else '-', expand=1, size=12) for k, _ in credit.BUCKETS] +
                                                     [ft.Text(f"{r['balance']:,.2f}", expand=1, size=12, weight=ft.FontWeight.BOLD)] + ([ft.Text(f"{r['credit_limit']:,.0f}" if r['credit_limit'] else '-', expand=1, size=12, color=theme.DANGER if r['over_limit'] else theme.TEXT_MUTED)] if cust else []))))
        body.controls = lines if rows else [ft.Text('مفيش مستحقات', color=theme.TEXT_MUTED)]
        detail_col.controls = []
        if e is not None:
            page.update()

    def show_details(r):
        ds = [d for d in st['data']['details'] if d['party_id'] == r['party_id']]
        detail_col.controls = [ft.Text(f"فواتير {r['party']} المفتوحة", weight=ft.FontWeight.BOLD)] + [
            ft.Text(f"{d['number']}  •  {d['date']:%Y-%m-%d}  •  استحقاق {d['due']:%Y-%m-%d}  •  متأخرة {d['days_over']} يوم  •  المتبقي {d['due_amount']:,.2f}", size=12) for d in ds]
        page.update()

    def export(fmt):
        try:
            if st['data'] is None:
                run()
            hdr = ['الاسم'] + [l for _, l in credit.BUCKETS] + ['الإجمالي', 'دفعات مقدمة', 'حد الائتمان']
            tb = [hdr]
            for r in st['data']['rows']:
                tb.append([r['party']] + [r[k] for k, _ in credit.BUCKETS] + [r['balance'], r['unapplied'], r['credit_limit']])
            t = st['data']['totals']
            tb.append(['الإجمالي'] + [t[k] for k, _ in credit.BUCKETS] + [t['balance'], t['unapplied'], ''])
            data = {'table': tb, 'row_styles': {len(tb) - 1: 'total'}, 'col_weights': [2.6, 1, 1, 1, 1, 1, 1.1, 1, 1]}
            theme.open_or_download_file(page, (export_excel if fmt == 'xlsx' else export_pdf)(data, 'receivables_aging', services.downloads_dir()))
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True)); page.update()

    kind.on_select = run
    only_over.on_change = run
    run()
    return ft.Column([
        theme.page_title('أعمار الديون', 'المستحقات مقسّمة حسب التأخر عن تاريخ الاستحقاق (تاريخ الفاتورة + مهلة العميل)، والسداد بيتوزّع على الأقدم أولًا'),
        ft.Row([kind, as_of, only_over, ft.OutlinedButton('عرض', on_click=run), ft.OutlinedButton('Excel', on_click=lambda e: export('xlsx')), ft.OutlinedButton('PDF', on_click=lambda e: export('pdf'))], wrap=True),
        summary, theme.card(body, padding=4, expand=True), theme.card(detail_col, padding=10),
    ], expand=True, spacing=10)
