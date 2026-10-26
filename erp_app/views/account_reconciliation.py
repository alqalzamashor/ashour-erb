import datetime
import os

import flet as ft

from .. import services, theme, reconciliation
from ..report_export import export_excel, export_pdf
from .restaurant_dashboard import _kpi

COLS = ['النوع', 'تاريخ الكشف', 'بيان / مرجع الكشف', 'مبلغ الكشف', 'تاريخ الدفتر', 'رقم / بيان الدفتر', 'مبلغ الدفتر', 'الفرق']
NUM_COLS = ('مبلغ الكشف', 'مبلغ الدفتر', 'الفرق')


def _m(v):
    return '' if v is None else f'{float(v):,.2f}'


def _d(v):
    return '' if not v else f'{v:%Y-%m-%d}'


def _row_values(r):
    return [r['label'], _d(r['s_date']), ' - '.join(x for x in (r['s_ref'], r['s_desc']) if x), _m(r['s_amount']),
            _d(r['b_date']), ' - '.join(x for x in (r['b_number'], r['b_desc']) if x), _m(r['b_amount']), _m(r['diff'])]


def export_table(rep):
    """جدول التصدير (Excel/PDF): ملخص التسوية ثم الفروقات ثم المطابق، مع row_styles وcol_weights."""
    t, styles = [COLS], {}

    def line(vals, style=None):
        t.append(vals + [''] * (len(COLS) - len(vals)))
        if style:
            styles[len(t) - 1] = style

    sm = rep['summary']
    who = 'مورد' if rep['kind'] == 'supplier' else 'حساب'
    line([f"مطابقة {who}: من {rep['date_from']:%Y-%m-%d} إلى {rep['date_to']:%Y-%m-%d} (مهلة التاريخ {rep['window']} يوم)"], 'section')
    line(['رصيد الدفتر في آخر الفترة', '', '', '', '', '', _m(rep['book_closing'])])
    line(['رصيد الكشف في آخر الفترة', '', '', _m(rep['stmt_closing']) if rep['stmt_closing'] is not None else 'غير محدد'])
    if rep['closing_diff'] is not None:
        line(['الفرق (الكشف - الدفتر)', '', '', '', '', '', '', _m(rep['closing_diff'])], 'total')
    line(['موجود في الكشف وغير مسجّل في الدفتر', '', '', _m(sm['stmt_only_sum']), '', '', '', f"{sm['stmt_only']} حركة"])
    line(['موجود في الدفتر وغير موجود في الكشف', '', '', '', '', '', _m(sm['book_only_sum']), f"{sm['book_only']} حركة"])
    line(['اختلاف في المبلغ لنفس الحركة', '', '', '', '', '', '', f"{_m(sm['amount_diff_sum'])} ({sm['amount_diff']} حركة)"])
    if rep['opening_diff'] is not None and abs(rep['opening_diff']) > 0.005:
        line(['فرق الرصيد الافتتاحي (قبل الفترة)', '', '', '', '', '', '', _m(rep['opening_diff'])], 'warn')
    line(['رصيد الدفتر المعدّل', '', '', '', '', '', _m(rep['adjusted_book'])], 'net')
    if rep['adjusted_stmt'] is not None:
        line(['رصيد الكشف المعدّل', '', '', _m(rep['adjusted_stmt'])], 'net')
    line([f"الفروقات ({sm['date_diff'] + sm['amount_diff'] + sm['stmt_only'] + sm['book_only']} حركة)"], 'section')
    for r in reconciliation.flat_rows(rep):
        line(_row_values(r), 'warn' if r['category'] in ('amount_diff', 'stmt_only') else None)
    line([f"المطابق ({sm['matched']} حركة)"], 'section')
    for r in reconciliation.flat_rows(rep, ('matched',)):
        line(_row_values(r))
    return {'table': t, 'row_styles': styles, 'col_weights': [1.3, 1.1, 2.4, 1.2, 1.1, 2.4, 1.2, 1.2], 'date_from': rep['date_from'], 'date_to': rep['date_to']}


def build_account_reconciliation(page: ft.Page):
    """تقرير مطابقة الحسابات: ارفع كشف البنك أو كشف المورد (Excel/CSV) وقارنه بالدفتر واطلع الفروقات."""
    services.require_action('account_reconciliation', 'view')
    cash = services.list_cash_accounts() or services.list_accounts(postable_only=True)
    kind_dd = ft.Dropdown(label='نوع الحساب', width=200, value='account', options=[ft.dropdown.Option(k, v) for k, v in reconciliation.KINDS.items()])
    acc_dd = theme.SearchableDropdown(label='حساب البنك / النقدية', width=330, page=page, clear_on_focus=True,
                                      options=[(str(a.id), f'{a.code} - {a.name}') for a in cash], value=str(cash[0].id) if cash else None)
    sup_dd = theme.SearchableDropdown(label='المورد', width=330, page=page, clear_on_focus=True, options=[(str(s.id), s.name) for s in services.list_suppliers()])
    sup_dd.control.visible = False
    file_txt = ft.Text('لم يتم اختيار ملف', size=12, color=theme.TEXT_MUTED)
    window_f = ft.TextField(label='مهلة فرق التاريخ (يوم)', value='5', width=170, dense=True, keyboard_type=ft.KeyboardType.NUMBER,
                            tooltip='الحركة بنفس المبلغ وفرق تاريخ أقل من المهلة دي بتتطابق عادي')
    closing_f = ft.TextField(label='رصيد الكشف الختامي (اختياري)', width=270, dense=True, keyboard_type=ft.KeyboardType.NUMBER,
                             tooltip='لو الكشف مفيهوش عمود رصيد، اكتب الرصيد الختامي بتاعه')
    flip_sw = ft.Switch(label='عكس اتجاه الأعمدة', value=False, tooltip='لو كشف الجهة بيستخدم مدين/دائن بالعكس من المعتاد: كل المطابقات هتطلع غلط (فروقات كتير) فجرّب تفعّله')
    rng = theme.DateRangeField('الفترة (اختياري - الافتراضي فترة الكشف)', page, width=330)
    rng.start.value = ''; rng.end.value = ''
    hint = ft.Text('', size=12, color=theme.TEXT_MUTED)
    kpis = ft.Row([], wrap=True, spacing=12)
    body = ft.Column([], spacing=12)
    st = {'path': None, 'rep': None}

    def on_kind(e=None):
        sup = kind_dd.value == 'supplier'
        acc_dd.control.visible = not sup
        sup_dd.control.visible = sup
        hint.value = ('كشف المورد من دفتره: الفاتورة (مدين) والسداد (دائن). لو الكشف بالعكس فعّل "عكس اتجاه الأعمدة".' if sup else
                      'كشف البنك: الإيداع (دائن) والسحب (مدين). لو الكشف بالعكس فعّل "عكس اتجاه الأعمدة".')
        page.update()
    kind_dd.on_select = on_kind      # القايمة المنسدلة في Flet الحديثة حدثها on_select

    async def pick(e):
        try:
            path = await theme.pick_file(page, 'اختر كشف الحساب (Excel أو CSV)', ['xlsx', 'csv'])
        except Exception as ex:      # noqa: BLE001
            page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True, data='error')); page.update(); return
        if path:
            st['path'] = path
            file_txt.value = os.path.basename(path); file_txt.color = theme.PRIMARY_TEXT
            page.update()

    def table_for(rows, empty_msg):
        tbl = ft.DataTable(columns=[ft.DataColumn(ft.Text(c, weight=ft.FontWeight.BOLD), numeric=c in NUM_COLS) for c in COLS], rows=[], heading_row_height=40, data_row_min_height=36)
        if not rows:
            return ft.Container(ft.Text(empty_msg, color=theme.SUCCESS, weight=ft.FontWeight.BOLD), padding=16)
        colors = {'date_diff': theme.TEXT_MUTED, 'amount_diff': theme.DANGER, 'stmt_only': theme.WARNING, 'book_only': theme.DANGER, 'matched': theme.SUCCESS}

        def build(r):
            v = _row_values(r)
            cells = [ft.DataCell(ft.Text(v[0], size=12, weight=ft.FontWeight.BOLD, color=colors.get(r['category'])))]
            for i, x in enumerate(v[1:], start=1):
                cells.append(ft.DataCell(ft.Container(width=230, content=ft.Text(x, size=12, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS, tooltip=x or None)) if i in (2, 5)
                                         else ft.Text(x, size=12, weight=ft.FontWeight.BOLD if i == 7 else None)))
            return ft.DataRow(cells=cells)
        theme.RowPager(tbl, page, 100).set_items(rows, build, keep_page=False)
        return theme.h_scroll(tbl)

    def summary_card(rep):
        sm = rep['summary']

        def kv(label, value, bold=False, color=None, note=''):
            return ft.Row([ft.Text(label, size=13, expand=True, weight=ft.FontWeight.BOLD if bold else None),
                           ft.Text(note, size=11, color=theme.TEXT_MUTED),
                           ft.Container(ft.Text(value, size=13, weight=ft.FontWeight.BOLD if bold else None, color=color), width=130, alignment=ft.Alignment(1, 0))], spacing=8)
        rows = [ft.Text('تسوية الأرصدة', size=15, weight=ft.FontWeight.BOLD),
                kv('رصيد الدفتر في آخر الفترة', _m(rep['book_closing'])),
                kv('رصيد الكشف في آخر الفترة', _m(rep['stmt_closing']) if rep['stmt_closing'] is not None else 'غير محدد'),
                kv('الفرق (الكشف - الدفتر)', _m(rep['closing_diff']) if rep['closing_diff'] is not None else '-', bold=True,
                   color=theme.DANGER if (rep['closing_diff'] or 0) else theme.SUCCESS), ft.Divider(height=8),
                kv('+ موجود في الكشف وغير مسجّل في الدفتر', _m(sm['stmt_only_sum']), note=f"{sm['stmt_only']} حركة"),
                kv('+ اختلاف في المبلغ لنفس الحركة', _m(sm['amount_diff_sum']), note=f"{sm['amount_diff']} حركة"),
                kv('= رصيد الدفتر المعدّل', _m(rep['adjusted_book']), bold=True), ft.Divider(height=8),
                kv('+ موجود في الدفتر وغير موجود في الكشف', _m(sm['book_only_sum']), note=f"{sm['book_only']} حركة"),
                kv('= رصيد الكشف المعدّل', _m(rep['adjusted_stmt']) if rep['adjusted_stmt'] is not None else '-', bold=True)]
        if rep['opening_diff'] is not None and abs(rep['opening_diff']) > 0.005:
            rows.append(ft.Text(f"تنبيه: في فرق {_m(rep['opening_diff'])} في الرصيد الافتتاحي (قبل أول حركة في الكشف) - الرصيدين المعدّلين مش هيتساووا لحد ما يتراجع.", size=12, color=theme.DANGER))
        elif rep['adjusted_stmt'] is not None:
            rows.append(ft.Text('الرصيدين المعدّلين متساويين: كل الفرق مفسّر بالحركات اللي فوق.', size=12, color=theme.SUCCESS))
        if sm['outside']:
            rows.append(ft.Text(f"{sm['outside']} حركة في الدفتر خارج فترة الكشف (متحسبتش كفروقات).", size=11, color=theme.TEXT_MUTED))
        return theme.card(ft.Column(rows, spacing=8))

    def run(e=None):
        try:
            ref = acc_dd.value if kind_dd.value == 'account' else sup_dd.value
            if not ref:
                raise ValueError('اختر الحساب' if kind_dd.value == 'account' else 'اختر المورد')
            if not st['path']:
                raise ValueError('اختر ملف الكشف الأول')
            clo = (closing_f.value or '').replace(',', '').strip()
            rep = reconciliation.build_report(kind_dd.value, int(ref), st['path'], int(window_f.value or 0), flip_sw.value,
                                              float(clo) if clo else None, (rng.start.value or '').strip() or None, (rng.end.value or '').strip() or None)
        except Exception as ex:      # noqa: BLE001
            page.overlay.append(ft.SnackBar(ft.Text(str(ex)), open=True, data='error')); page.update(); return
        st['rep'] = rep
        sm = rep['summary']
        diffs = sm['date_diff'] + sm['amount_diff'] + sm['stmt_only'] + sm['book_only']
        bad = rep['closing_diff'] is not None and abs(rep['closing_diff']) > 0.005
        kpis.controls = [_kpi('رصيد الدفتر', _m(rep['book_closing']), theme.PRIMARY, sub=f"حتى {rep['date_to']:%Y-%m-%d}"),
                         _kpi('رصيد الكشف', _m(rep['stmt_closing']) if rep['stmt_closing'] is not None else '-', theme.PRIMARY, sub='' if rep['stmt_closing'] is not None else 'اكتب الرصيد الختامي لو الملف مفيهوش عمود رصيد'),
                         _kpi('الفرق', _m(rep['closing_diff']) if rep['closing_diff'] is not None else '-', theme.DANGER if bad else theme.SUCCESS),
                         _kpi('مطابق', str(sm['matched']), theme.SUCCESS, sub=f"من {sm['stmt_count']} حركة في الكشف"),
                         _kpi('فروقات', str(diffs), theme.WARNING if diffs else theme.SUCCESS,
                              sub=f"{sm['stmt_only']} في الكشف فقط • {sm['book_only']} في الدفتر فقط • {sm['amount_diff']} اختلاف مبلغ • {sm['date_diff']} فارق تاريخ")]
        tabs = theme.SimpleTabs(page)
        tabs.set_tabs([
            (f'الفروقات ({diffs})', table_for(reconciliation.flat_rows(rep), 'مفيش فروقات: الكشف مطابق للدفتر ✓')),
            (f"المطابق ({sm['matched']})", table_for(reconciliation.flat_rows(rep, ('matched',)), 'مفيش حركات مطابقة')),
            ('تسوية الأرصدة', summary_card(rep)),
        ])
        body.controls = [theme.card(tabs.control, expand=True)]
        page.update()

    def export(fmt):
        try:
            if st['rep'] is None:
                run()
            if st['rep'] is None:
                return
            theme.open_or_download_file(page, (export_excel if fmt == 'xlsx' else export_pdf)(export_table(st['rep']), 'account_reconciliation', services.downloads_dir()))
        except Exception as ex:      # noqa: BLE001
            page.overlay.append(ft.SnackBar(ft.Text(f'تعذر التصدير: {ex}'), open=True)); page.update()

    on_kind()
    return ft.Column([
        ft.Row([theme.page_title('مطابقة الحسابات', 'ارفع كشف البنك أو كشف المورد وقارنه بالدفتر واطلع الفروقات'), ft.Container(expand=True),
                ft.ElevatedButton('Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: export('xlsx')), ft.ElevatedButton('PDF', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: export('pdf'))]),
        theme.card(ft.Column([
            ft.Row([kind_dd, acc_dd.control, sup_dd.control, ft.OutlinedButton('اختيار ملف الكشف', icon=ft.Icons.UPLOAD_FILE_OUTLINED, on_click=pick), file_txt], wrap=True, spacing=10,
                   vertical_alignment=ft.CrossAxisAlignment.START),
            ft.Row([rng.control, window_f, closing_f, flip_sw,
                    theme.guard_submit(ft.FilledButton('مطابقة', icon=ft.Icons.COMPARE_ARROWS, bgcolor=theme.PRIMARY, on_click=run))], wrap=True, spacing=10),
            hint], spacing=10)),
        kpis, body,
    ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=12)
