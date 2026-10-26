import datetime
import os
import flet as ft
from .. import services, theme


def build_ledger(page: ft.Page):
    err = ft.Text('', color=theme.DANGER, visible=False)
    empty_hint = ft.Text('لا توجد حركات لعرضها في الفترة المحددة.', color=theme.TEXT_MUTED, visible=False)

    accounts = services.list_accounts()
    dd = theme.SearchableDropdown(
        label='الحساب', width=330,
        options=[('', 'كل الحسابات')] + [
            (str(a.id), f'{a.code} - {a.name}') for a in accounts
        ],
        value='',
    )
    range_f = theme.DateRangeField('الفترة', page, width=290)
    date_from, date_to = range_f.start, range_f.end

    opening_text = ft.Text('', size=14, weight=ft.FontWeight.BOLD, color=theme.PRIMARY)
    closing_text = ft.Text('', size=14, weight=ft.FontWeight.BOLD)

    table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text('التاريخ')), ft.DataColumn(ft.Text('القيد')),
            ft.DataColumn(ft.Text('الحساب')), ft.DataColumn(ft.Text('البيان')),
            ft.DataColumn(ft.Text('مدين')), ft.DataColumn(ft.Text('دائن')), ft.DataColumn(ft.Text('الرصيد')),
        ],
        rows=[],
    )
    ledger_pager = theme.RowPager(table, page, 100)
    state = {'rows': []}
    # ملخص الحسابات الفرعية: بيظهر لما الحساب المختار أب (ليه حسابات تحته)
    children_title = ft.Text('الحسابات الفرعية', size=15, weight=ft.FontWeight.BOLD, visible=False)
    children_table = ft.DataTable(columns=[ft.DataColumn(ft.Text('الحساب'))] + [ft.DataColumn(ft.Text(c), numeric=True) for c in ('رصيد أول الفترة', 'مدين', 'دائن', 'الرصيد')], rows=[], visible=False)
    children_total = ft.Text('', size=13, weight=ft.FontWeight.BOLD, visible=False)
    children_wrap = theme.h_scroll(children_table)
    children_wrap.visible = False

    def parse_date(v):
        if not (v or '').strip():
            return None
        try:
            return datetime.datetime.strptime(v.strip(), '%Y-%m-%d')
        except Exception:
            raise ValueError('صيغة التاريخ يجب أن تكون YYYY-MM-DD')

    def compute(update_ui=True):
        """يحسب صفوف الجدول. update_ui=False أثناء البناء الأول (قبل ما
        الشاشة تتلحّم بالصفحة فعلياً) لتفادي استدعاء page.update() على
        عناصر لسه مش متصلة - وده كان بيسبب ظهور مربع فاضي بدل الجدول."""
        try:
            df = parse_date(date_from.value)
            dt = parse_date(date_to.value)
            result = services.account_ledger(int(dd.value) if dd.value else None, date_from=df, date_to=dt)
            rows = result['rows']
            opening = result['opening_balance']
            closing = result['closing_balance']

            ledger_pager.set_items(rows, lambda r: (
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(r['date'].strftime('%Y-%m-%d'))),
                    ft.DataCell(ft.Text(r['number'])),
                    ft.DataCell(ft.Text(f"{r['code']} - {r['account']}")),
                    ft.DataCell(ft.Text(r['description'] or '-')),
                    ft.DataCell(ft.Text(f"{r['debit']:,.2f}")),
                    ft.DataCell(ft.Text(f"{r['credit']:,.2f}")),
                    ft.DataCell(ft.Text(f"{r['balance']:,.2f}")),
                ])
            ), keep_page=False)
            state['rows'] = []
            if df:
                state['rows'].append({
                    'date': df, 'number': '', 'code': '', 'account': f'رصيد افتتاحي (قبل {df.strftime("%Y-%m-%d")})',
                    'description': '', 'debit': '', 'credit': '', 'balance': opening,
                })
            state['rows'] += [{'date': r['date'], 'number': r['number'], 'code': r['code'],
                                'account': r['account'], 'description': r['description'] or '-',
                                'debit': r['debit'], 'credit': r['credit'], 'balance': r['balance']} for r in rows]

            if df:
                opening_text.value = f'الرصيد الافتتاحي (قبل {df.strftime("%Y-%m-%d")}): {opening:,.2f}'
                opening_text.visible = True
            else:
                opening_text.visible = False
            closing_text.value = f'الرصيد الختامي: {closing:,.2f}'
            closing_text.visible = bool(rows) or df is not None

            kids = result.get('children') or []
            state['children'] = kids
            children_title.visible = children_table.visible = children_wrap.visible = children_total.visible = bool(kids)
            if kids:
                children_title.value = f'الحسابات الفرعية ({len(kids)}) - الرصيد الختامي أعلاه = مجموع أرصدتها'
                f = lambda v: f'{v:,.2f}'
                b = ft.FontWeight.BOLD
                children_table.rows = [ft.DataRow(cells=[ft.DataCell(ft.Text(f"{k['code']} - {k['name']}")), ft.DataCell(ft.Text(f(k['opening']))), ft.DataCell(ft.Text(f(k['debit']))),
                                                         ft.DataCell(ft.Text(f(k['credit']))), ft.DataCell(ft.Text(f(k['balance']), weight=b))]) for k in kids]
                children_total.value = (f"الإجمالي: أول الفترة {f(sum(k['opening'] for k in kids))} • مدين {f(sum(k['debit'] for k in kids))} • "
                                        f"دائن {f(sum(k['credit'] for k in kids))} • الرصيد {f(sum(k['balance'] for k in kids))}")
            empty_hint.visible = len(rows) == 0
            err.visible = False
        except Exception as ex:
            err.value = f'حدث خطأ أثناء تحميل دفتر الأستاذ: {ex}'
            err.visible = True
        if update_ui:
            page.update()

    def refresh(e=None):
        compute(update_ui=True)

    def do_export(kind):
        try:
            from ..report_export import export_excel, export_pdf
            exports_dir = services.downloads_dir()
            path = (export_excel if kind == 'xlsx' else export_pdf)({'ledger': state['rows'], 'ledger_children': state.get('children') or []}, 'ledger', exports_dir)
            theme.open_or_download_file(page, path)
            page.overlay.append(ft.SnackBar(ft.Text(f'تم إنشاء الملف: {path}'), open=True)); page.update()
        except Exception as ex:
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

    pre = getattr(page, '_erp_ledger_preset', None)      # فتح من ميزان المراجعة (drill-down): حساب + فترة
    if pre:
        page._erp_ledger_preset = None
        dd.value = str(pre['account_id'])
        if pre.get('date_from') or pre.get('date_to'):
            try:
                _d = lambda v: datetime.date.fromisoformat(v) if v else None
                range_f.set_range(_d(pre.get('date_from')), _d(pre.get('date_to')))
            except Exception:      # noqa: BLE001
                pass
    dd.on_change = refresh
    date_from.on_change = refresh
    date_to.on_change = refresh
    compute(update_ui=False)  # حساب أولي بدون page.update()

    return ft.Column(
        [
            ft.Row(
                [theme.page_title('دفتر الأستاذ', 'تفاصيل الحركة والأرصدة التراكمية لكل حساب، مع رصيد افتتاحي لأي فترة تحددها'),
                 ft.Container(expand=True),
                 ft.ElevatedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: do_export('xlsx')),
                 ft.ElevatedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: do_export('pdf'))],
            ),
            ft.Container(height=12),
            theme.card(ft.Row([dd.control, range_f.control], wrap=True, spacing=12)),
            ft.Container(height=8),
            ft.Row([opening_text, closing_text], spacing=24),
            ft.Container(height=8),
            err,
            ft.Column([children_title, children_wrap, children_total], spacing=6),
            theme.card(
                ft.Column([empty_hint, theme.h_scroll(table)], spacing=8),
                expand=True,
            ),
        ],
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )
