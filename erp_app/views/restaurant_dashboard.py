import datetime
import flet as ft
from .. import services, theme, restaurant_stats
from ..report_export import export_excel, export_pdf


def _bar_rows(rows, color, value_fmt=lambda r: f'{r[2]:,.2f}', extra=lambda r: f'{r[1]} طلب'):
    if not rows:
        return [ft.Text('لا توجد بيانات', size=12, color=theme.TEXT_MUTED)]
    mx = max(r[2] for r in rows) or 1
    out = []
    for r in rows:
        w = max(1, int(r[2] / mx * 100))
        out.append(ft.Row([
            ft.Container(width=130, content=ft.Text(str(r[0]), size=12, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, tooltip=str(r[0]))),
            ft.Container(expand=True, content=ft.Row([ft.Container(expand=w, height=14, border_radius=5, bgcolor=color), ft.Container(expand=max(0, 100 - w), height=14)], spacing=0)),
            ft.Text(f'{value_fmt(r)}', size=12, weight=ft.FontWeight.BOLD), ft.Text(extra(r), size=11, color=theme.TEXT_MUTED)], spacing=8))
    return out


def _kpi(title, value, color=theme.PRIMARY, sub=''):
    return theme.card(ft.Column([ft.Text(title, size=11, color=theme.TEXT_MUTED), ft.Text(value, size=20, weight=ft.FontWeight.BOLD, color=color),
                                 ft.Text(sub, size=10, color=theme.TEXT_MUTED, visible=bool(sub))], spacing=2, tight=True), padding=14, expand=True)


def build_restaurant_dashboard(page: ft.Page):
    """لوحة المطعم: مبيعات وطلبات ومتوسط فاتورة، أعلى الأصناف، المبيعات بالساعة، توزيعات، والإلغاءات."""
    services.require_action('restaurant_dashboard', 'view')
    today = datetime.date.today()
    rng = theme.DateRangeField('الفترة', page, width=290, allow_clear=False)
    rng.start.value = f'{today:%Y-%m-%d}'; rng.end.value = f'{today:%Y-%m-%d}'
    terms = services.list_pos_terminals(active_only=True)
    term_dd = ft.Dropdown(label='الماكينة', width=200, value='', options=[ft.dropdown.Option('', 'الكل')] + [ft.dropdown.Option(str(t['id']), t['name']) for t in terms])
    body = ft.Column(spacing=12)
    last = {'r': None}

    def d(v):
        return datetime.datetime.strptime(v, '%Y-%m-%d').date()

    def quick(days_back=0, month=False, week=False):
        def f(e):
            t = datetime.date.today()
            if month:
                a, b = t.replace(day=1), t
            elif week:
                a, b = t - datetime.timedelta(days=6), t
            else:
                a = b = t - datetime.timedelta(days=days_back)
            rng.start.value = f'{a:%Y-%m-%d}'; rng.end.value = f'{b:%Y-%m-%d}'
            run(True)
        return f

    def hours_chart(hours):
        if not hours:
            return ft.Text('لا توجد بيانات', size=12, color=theme.TEXT_MUTED)
        by = {h: v for h, _, v in hours}; mx = max(by.values()) or 1
        cols = []
        for h in range(24):
            v = by.get(h, 0)
            peak = v == mx and v > 0
            cols.append(ft.Column([
                ft.Container(width=22, height=110, bgcolor=ft.Colors.with_opacity(0.06, theme.PRIMARY), border_radius=5, alignment=ft.Alignment(0, 1),
                             content=ft.Container(width=22, height=max(3, int(110 * v / mx)) if v else 0, bgcolor=theme.WARNING if peak else theme.PRIMARY, border_radius=5), tooltip=f'{h:02d}:00 - {v:,.2f}'),
                ft.Text(f'{h:02d}', size=9, color=theme.TEXT_MUTED)], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER))
        return theme.h_scroll(ft.Row(cols, spacing=4))

    def run(e=None):
        try:
            r = restaurant_stats.dashboard(d(rng.start.value), d(rng.end.value), term_dd.value or None)
        except Exception as ex:
            body.controls = [ft.Text(str(ex), color=theme.DANGER)]
            if e is not None:
                page.update()
            return
        last['r'] = r
        k = r['kpis']
        ph = f"{r['peak_hour']:02d}:00" if r['peak_hour'] is not None else '-'
        kp = ft.Row([_kpi('إجمالي المبيعات', f"{k['sales']:,.2f}"), _kpi('عدد الطلبات', str(k['orders']), theme.SUCCESS), _kpi('متوسط الفاتورة', f"{k['avg_ticket']:,.2f}"),
                     _kpi('متوسط للفرد', f"{k['per_guest']:,.2f}", sub=f"{k['guests']} ضيف"), _kpi('ساعة الذروة', ph, theme.WARNING),
                     _kpi('الإلغاءات', f"{k['void_amount']:,.2f}", theme.DANGER if k['void_count'] else theme.SUCCESS, sub=f"{k['void_count']} عملية ({k['void_pct']}% من المبيعات)")], wrap=True, spacing=12)
        blocks = [kp,
                  theme.card(ft.Column([ft.Text('المبيعات بالساعة', size=15, weight=ft.FontWeight.BOLD), hours_chart(r['hours'])], spacing=8)),
                  ft.Row([theme.card(ft.Column([ft.Text('أعلى الأصناف (بالقيمة)', size=15, weight=ft.FontWeight.BOLD)] + _bar_rows(r['top_items'], theme.PRIMARY, extra=lambda x: f'× {x[1]:g}'), spacing=6), expand=True),
                          theme.card(ft.Column([ft.Text('حسب نوع الطلب', size=15, weight=ft.FontWeight.BOLD)] + _bar_rows(r['types'], theme.SUCCESS) +
                                                [ft.Divider(), ft.Text('حسب طريقة الدفع', size=15, weight=ft.FontWeight.BOLD)] + _bar_rows(r['payments'], theme.WARNING), spacing=6), expand=True)], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START),
                  ft.Row([theme.card(ft.Column([ft.Text('حسب الكاشير', size=15, weight=ft.FontWeight.BOLD)] + _bar_rows(r['users'], theme.PRIMARY), spacing=6), expand=True),
                          theme.card(ft.Column([ft.Text('حسب القسم', size=15, weight=ft.FontWeight.BOLD)] + _bar_rows(r['sections'], theme.SUCCESS), spacing=6), expand=True)], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START)]
        if len(r['days']) > 1:
            blocks.insert(2, theme.card(ft.Column([ft.Text('المبيعات اليومية', size=15, weight=ft.FontWeight.BOLD)] + _bar_rows([[f'{x[0]:%m-%d}', x[1], x[2]] for x in r['days']], theme.PRIMARY), spacing=6)))
        if r['bottom_items']:
            blocks.append(theme.card(ft.Column([ft.Text('الأقل مبيعًا', size=15, weight=ft.FontWeight.BOLD)] + _bar_rows(r['bottom_items'], theme.DANGER, extra=lambda x: f'× {x[1]:g}'), spacing=6)))
        mw = theme._page_w()
        if mw:       # موبايل: كروت الأرقام اتنين في الصف، واللوحات بعرض كامل تحت بعض
            for c in kp.controls:
                c.expand = None
                c.width = max(140, (mw - 42) / 2)
            for b in blocks:
                if b is kp:
                    continue
                if isinstance(b, ft.Row):
                    b.wrap = True
                    b.run_spacing = 12
                    for c in b.controls:
                        c.expand = None
                        c.width = mw - 32
                else:
                    b.width = mw - 32
        body.controls = blocks
        if e is not None:
            page.update()

    def export(fmt):
        try:
            if last['r'] is None:
                run()
            r = last['r']; k = r['kpis']
            t, styles = restaurant_stats.export_table(r)
            data = {'table': t, 'row_styles': styles, 'col_weights': [3, 1.2, 1.6], 'date_from': d(rng.start.value), 'date_to': d(rng.end.value)}
            path = (export_excel if fmt == 'xlsx' else export_pdf)(data, 'restaurant_dashboard', services.downloads_dir())
            theme.open_or_download_file(page, path)
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

    run()
    return ft.Column([
        ft.Row([theme.page_title('لوحة المطعم', 'المبيعات والطلبات وأعلى الأصناف وساعات الذروة والإلغاءات'), ft.Container(expand=True),
                ft.ElevatedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('xlsx')), ft.ElevatedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf'))]),
        theme.card(ft.Row([rng.control, term_dd, ft.OutlinedButton('اليوم', on_click=quick()), ft.OutlinedButton('أمس', on_click=quick(1)), ft.OutlinedButton('آخر 7 أيام', on_click=quick(week=True)),
                           ft.OutlinedButton('هذا الشهر', on_click=quick(month=True)), theme.guard_submit(ft.FilledButton('عرض', icon=ft.Icons.SEARCH, bgcolor=theme.PRIMARY, on_click=run))], wrap=True, spacing=10)),
        body], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
