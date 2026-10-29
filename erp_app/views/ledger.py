import datetime
import flet as ft
from .. import services, theme


def build_ledger(page: ft.Page):
    err = ft.Text('', color=theme.DANGER, visible=False)

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
    branch_dd = theme.SearchableDropdown(label='الفرع', width=210, options=[('', 'كل الفروع')] + [(str(b.id), f'{b.code} - {b.name}') for b in services.list_branches(False)], value='')
    cc_dd = theme.SearchableDropdown(label='مركز التكلفة', width=210, options=[('', 'كل المراكز')] + [(str(c.id), f'{c.code} - {c.name}') for c in services.list_cost_centers(False)], value='')
    party_opts = [('', 'كل الأطراف')]
    party_opts += [(f'customer:{c.id}', f'عميل - {c.name}') for c in services.list_customers()]
    party_opts += [(f'supplier:{c.id}', f'مورد - {c.name}') for c in services.list_suppliers()]
    party_opts += [(f'employee:{c.id}', f'موظف - {c.name}') for c in services.list_employees()]
    party_dd = theme.SearchableDropdown(label='الطرف', width=250, options=party_opts, value='')


    from ..report_viewer import ReportViewer, Mode, Col
    from .. import report_engine as RE
    state = {'rows': [], 'opening': 0.0}
    cols = [Col('date', 'التاريخ', RE.DATE), Col('number', 'القيد'), Col('account', 'الحساب'), Col('party', 'الطرف'), Col('description', 'البيان', width=2.6), Col('branch', 'الفرع'), Col('cost_center', 'مركز التكلفة'),
            Col('debit', 'مدين', RE.MONEY, 'sum'), Col('credit', 'دائن', RE.MONEY, 'sum'), Col('balance', 'الرصيد', RE.MONEY, 'net:debit:credit', bold=True)]
    from .general_journal import build_general_journal
    opener = {}

    def open_entry(row):
        if not row.get('entry_id'):
            return
        if 'fn' not in opener:
            opener['fn'] = build_general_journal(page, dialog_only=True, on_changed=lambda: compute(True))
        opener['fn'](row['entry_id'])
    viewer = ReportViewer(
        page, 'ledger', 'دفتر الأستاذ', cols,
        modes=[Mode('acc_month', 'حسب الحساب ثم الشهر', ['account', 'date:month']), Mode('by_party', 'حسب الطرف', ['party']), Mode('by_branch', 'حسب الفرع', ['branch']), Mode('by_cc', 'حسب مركز التكلفة', ['cost_center']), Mode('month_acc', 'حسب الشهر ثم الحساب', ['date:month', 'account'])],
        kpis=[('رصيد أول الفترة', lambda r: f"{state['opening']:,.2f}"), ('إجمالي المدين', lambda r: f"{(r['totals'].get('debit') or 0):,.2f}"),
              ('إجمالي الدائن', lambda r: f"{(r['totals'].get('credit') or 0):,.2f}"), ('الرصيد الختامي', lambda r: f"{state['opening'] + (r['totals'].get('debit') or 0) - (r['totals'].get('credit') or 0):,.2f}"),
              ('عدد الحركات', lambda r: f"{r['count']:,}")],
        chart_value='debit', empty_text='لا توجد حركات في الفترة المحددة', on_row_double_click=open_entry)
    opening_text = ft.Text('', size=13, color=theme.PRIMARY, weight=ft.FontWeight.BOLD)
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
            _pt, _, _pi = (party_dd.value or '').partition(':')
            result = services.account_ledger(int(dd.value) if dd.value else None, date_from=df, date_to=dt,
                                             branch_id=branch_dd.value or None, cost_center_id=cc_dd.value or None,
                                             partner_type=_pt or None, partner_id=_pi or None)
            rows = result['rows']
            opening = result['opening_balance']

            state['opening'] = opening
            bmap = {b.id: f'{b.code} - {b.name}' for b in services.list_branches(False)} if hasattr(services, 'list_branches') else {}
            cmap = {c.id: f'{c.code} - {c.name}' for c in services.list_cost_centers(False)} if hasattr(services, 'list_cost_centers') else {}
            pmap = {('customer', c.id): f'عميل - {c.name}' for c in services.list_customers()}
            pmap.update({('supplier', c.id): f'مورد - {c.name}' for c in services.list_suppliers()})
            pmap.update({('employee', c.id): f'موظف - {c.name}' for c in services.list_employees()})
            state['rows'] = [{'branch': bmap.get(r.get('branch_id'), ''), 'cost_center': cmap.get(r.get('cost_center_id'), ''), 'party': pmap.get((r.get('partner_type'), r.get('partner_id')), ''),'date': r['date'], 'number': r['number'], 'account': f"{r['code']} - {r['account']}", 'description': r['description'] or '-',
                              'debit': r['debit'], 'credit': r['credit'], 'balance': r['balance'], 'account_id': r['account_id'], 'entry_id': r.get('entry_id')} for r in rows]
            viewer.title = 'دفتر الأستاذ' + (f' - رصيد أول الفترة {opening:,.2f}' if df else '')
            viewer.set_rows(state['rows'])
            if df:
                opening_text.value = f'الرصيد الافتتاحي (قبل {df.strftime("%Y-%m-%d")}): {opening:,.2f}'
                opening_text.visible = True
            else:
                opening_text.visible = False

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
            err.visible = False
        except Exception as ex:
            err.value = f'حدث خطأ أثناء تحميل دفتر الأستاذ: {ex}'
            err.visible = True
        if update_ui:
            page.update()

    def refresh(e=None):
        compute(update_ui=True)

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
    branch_dd.on_change = cc_dd.on_change = party_dd.on_change = refresh
    date_from.on_change = refresh
    date_to.on_change = refresh
    compute(update_ui=False)  # حساب أولي بدون page.update()

    return ft.Column(
        [
            ft.Row(
                [theme.page_title('دفتر الأستاذ', 'تفاصيل الحركة والأرصدة التراكمية لكل حساب، مع رصيد افتتاحي لأي فترة تحددها'),
                 ft.Container(expand=True)],
            ),
            ft.Container(height=12),
            theme.card(ft.Row([dd.control, range_f.control, branch_dd.control, cc_dd.control, party_dd.control], wrap=True, spacing=12)),
            ft.Container(height=8),
            opening_text,
            err,
            ft.Column([children_title, children_wrap, children_total], spacing=6),
            viewer.control,
        ],
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )
