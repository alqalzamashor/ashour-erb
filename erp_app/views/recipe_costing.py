import flet as ft
from .. import services, theme
from ..report_export import export_excel, export_pdf


def _pct_color(v):
    return theme.SUCCESS if v <= 30 else (theme.WARNING if v <= 40 else theme.DANGER)


def build_recipe_costing(page: ft.Page):
    """تكلفة الوصفات: تكلفة كل طبق (من مكوناته)، الهامش، نسبة تكلفة الطعام، وعدد الأطباق اللي المخزون يكفيها."""
    services.require_action('recipe_costing', 'view')
    search_f = ft.TextField(label='بحث (اسم / كود)', width=240, dense=True)
    cols = ['الصنف', 'النوع', 'المكونات', 'التكلفة', 'سعر البيع (قبل الضريبة)', 'الهامش', 'هامش %', 'تكلفة الطعام %', 'أطباق متاحة', 'أول مكوّن ينفد']
    table = ft.DataTable(columns=[ft.DataColumn(ft.Text(x, weight=ft.FontWeight.BOLD), numeric=i in (3, 4, 5, 6, 7, 8)) for i, x in enumerate(cols)], rows=[])
    pager = theme.RowPager(table, page, 50)
    kpi = ft.Row(wrap=True, spacing=12)
    note = ft.Text('', size=11, color=theme.TEXT_MUTED)
    st = {'rows': []}

    def run(e=None):
        rows = services.recipe_costing(search_f.value or None)
        st['rows'] = rows

        def build(r):
            warn = ' ⚠' if r['incomplete'] else ''
            return ft.DataRow(cells=[
                ft.DataCell(ft.Text(r['name'], size=12, weight=ft.FontWeight.BOLD)), ft.DataCell(ft.Text(r['type'], size=12)), ft.DataCell(ft.Text(str(r['components']), size=12)),
                ft.DataCell(ft.Text(f"{r['cost']:,.2f}{warn}", size=12, color=theme.WARNING if r['incomplete'] else None, tooltip='فيه مكوّن تكلفته صفر - التكلفة غير مكتملة' if r['incomplete'] else None)),
                ft.DataCell(ft.Text(f"{r['price']:,.2f}", size=12)), ft.DataCell(ft.Text(f"{r['margin']:,.2f}", size=12, color=theme.DANGER if r['margin'] < 0 else None)),
                ft.DataCell(ft.Text(f"{r['margin_pct']:.1f}%", size=12)),
                ft.DataCell(ft.Text(f"{r['food_cost_pct']:.1f}%", size=12, weight=ft.FontWeight.BOLD, color=_pct_color(r['food_cost_pct']))),
                ft.DataCell(ft.Text(str(r['portions']), size=12, color=theme.DANGER if r['portions'] <= 0 else None)), ft.DataCell(ft.Text(r['limiting'], size=12))])
        pager.set_items(rows, build, keep_page=False)
        avg = (sum(r['food_cost_pct'] for r in rows) / len(rows)) if rows else 0
        bad = sum(1 for r in rows if r['food_cost_pct'] > 40 or r['margin'] < 0)
        out = sum(1 for r in rows if r['portions'] <= 0)
        kpi.controls = [theme.card(ft.Column([ft.Text(t, size=11, color=theme.TEXT_MUTED), ft.Text(v, size=16, weight=ft.FontWeight.BOLD, color=c)], spacing=2, tight=True), padding=12)
                        for t, v, c in [('عدد الوصفات', str(len(rows)), theme.PRIMARY), ('متوسط تكلفة الطعام', f'{avg:.1f}%', _pct_color(avg)),
                                        ('أصناف تكلفتها فوق 40% أو بخسارة', str(bad), theme.DANGER if bad else theme.SUCCESS), ('أصناف لا يكفيها المخزون', str(out), theme.DANGER if out else theme.SUCCESS)]]
        note.value = 'التكلفة من سعر تكلفة المكونات الحالي في الأصناف، وعدد الأطباق من الرصيد الفعلي للمخزون. الأخضر ≤30% والأصفر ≤40%.'
        if e is not None:
            page.update()

    def export(fmt):
        try:
            if not st['rows']:
                run()
            t = [cols] + [[r['name'], r['type'], r['components'], f"{r['cost']:.2f}", f"{r['price']:.2f}", f"{r['margin']:.2f}", f"{r['margin_pct']:.1f}%", f"{r['food_cost_pct']:.1f}%", r['portions'], r['limiting']] for r in st['rows']]
            data = {'table': t, 'row_styles': {}, 'col_weights': [2.2, 0.9, 0.9, 1, 1.3, 1, 0.9, 1.1, 1, 1.8]}
            path = (export_excel if fmt == 'xlsx' else export_pdf)(data, 'recipe_costing', services.downloads_dir())
            theme.open_or_download_file(page, path)
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

    run()
    return ft.Column([
        ft.Row([theme.page_title('تقرير تكلفة الوصفات', 'تكلفة الطبق ونسبة تكلفة الطعام وكام طبق يكفي المخزون'), ft.Container(expand=True),
                ft.ElevatedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('xlsx')), ft.ElevatedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf'))]),
        theme.card(ft.Row([search_f, theme.guard_submit(ft.FilledButton('عرض', icon=ft.Icons.SEARCH, bgcolor=theme.PRIMARY, on_click=run))], wrap=True, spacing=10)),
        kpi, theme.card(theme.h_scroll(table), expand=True), note,
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
