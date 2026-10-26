import datetime

from erp_app import report_engine as E

D = datetime.date
COLS = [E.Col('date', 'التاريخ', E.DATE), E.Col('acc', 'الحساب'), E.Col('desc', 'البيان'),
        E.Col('debit', 'مدين', E.MONEY, 'sum'), E.Col('credit', 'دائن', E.MONEY, 'sum'), E.Col('bal', 'الرصيد', E.MONEY, 'last')]
ROWS = [
    {'date': D(2026, 1, 5), 'acc': 'الصندوق', 'desc': 'مبيعات', 'debit': 100.0, 'credit': 0.0, 'bal': 100.0},
    {'date': D(2026, 1, 20), 'acc': 'البنك', 'desc': 'إيداع', 'debit': 50.0, 'credit': 0.0, 'bal': 150.0},
    {'date': D(2026, 2, 3), 'acc': 'الصندوق', 'desc': 'مصروف كهرباء', 'debit': 0.0, 'credit': 30.0, 'bal': 120.0},
    {'date': D(2026, 2, 9), 'acc': 'الصندوق', 'desc': 'مبيعات', 'debit': 200.0, 'credit': 0.0, 'bal': 320.0},
]


def st(**k):
    return E.ViewState(**k)


def test_formatting():
    assert E.fmt(1234.5, COLS[3]) == '1,234.50' and E.fmt(None, COLS[3]) == '' and E.fmt(D(2026, 1, 2), COLS[0]) == '2026-01-02'
    q = E.Col('q', 'ك', E.QTY)
    assert E.fmt(3.0, q) == '3' and E.fmt(2.5, q) == '2.5' and E.fmt(12.5, E.Col('p', 'ن', E.PCT)) == '12.5%'


def test_numeric_text_date_filters():
    f = lambda text, col, v: E.make_filter(text, col)(v)
    m = COLS[3]
    assert f('>60', m, 100) and not f('>60', m, 50) and f('10..60', m, 50) and f('..60', m, 50) and not f('..60', m, 100)
    assert f('=50', m, 50.0) and f('50', m, 50.0) and f('<=50', m, 50)
    t = COLS[1]
    assert f('صندوق', t, 'الصندوق') and f('بنك|صندوق', t, 'البنك') and f('!بنك', t, 'الصندوق') and not f('!بنك', t, 'البنك') and f('=البنك', t, 'البنك')
    assert f('الصندوق', t, 'الصندوق') and f('الصنديق', t, 'الصندوق') is False
    d = COLS[0]
    assert f('2026-01', d, D(2026, 1, 5)) and not f('2026-01', d, D(2026, 2, 3))
    assert f('>=2026-02-01', d, D(2026, 2, 3)) and f('2026-01-01..2026-01-31', d, D(2026, 1, 20))
    assert E.make_filter('', t) is None


def test_arabic_normalization_in_search():
    rows = [{'acc': 'إيجار المبنى', 'debit': 1.0}]
    cols = [E.Col('acc', 'ح'), E.Col('debit', 'م', E.MONEY, 'sum')]
    assert len(E.apply_filters(rows, cols, st(search='ايجار'))) == 1


def test_sort_numeric_dates_and_missing_last():
    rows = ROWS + [{'date': None, 'acc': 'x', 'debit': None}]
    out = E.sort_rows(rows, COLS[3], asc=False)
    assert [r['debit'] for r in out][:4] == [200.0, 100.0, 50.0, 0.0] and out[-1]['debit'] is None
    out = E.sort_rows(rows, COLS[0], asc=True)
    assert out[0]['date'] == D(2026, 1, 5) and out[-1]['date'] is None


def test_group_with_aggregations_and_last_balance():
    res = E.run(ROWS, COLS, st(group_keys=['acc']))
    nodes = {n.label: n for n in res['nodes']}
    assert nodes['الصندوق'].agg['debit'] == 300.0 and nodes['الصندوق'].agg['credit'] == 30.0
    assert nodes['الصندوق'].agg['bal'] == 320.0           # آخر رصيد في المجموعة
    assert res['totals']['debit'] == 350.0 and res['totals']['bal'] == 320.0


def test_group_by_month_and_two_levels():
    res = E.run(ROWS, COLS, st(group_keys=['date:month', 'acc']))
    assert [n.label for n in res['nodes']] == ['2026-01', '2026-02']
    jan = res['nodes'][0]
    assert {c.label for c in jan.children} == {'الصندوق', 'البنك'} and jan.agg['debit'] == 150.0
    assert E.group_label('date:month', {c.key: c for c in COLS}) == 'التاريخ (شهر)'


def test_flatten_expansion_and_summary_only():
    res = E.run(ROWS, COLS, st(group_keys=['acc']))
    assert [i[0] for i in E.flatten(res['nodes'], set())] == ['group', 'group']
    ids = E.all_group_ids(res['nodes'])
    flat = E.flatten(res['nodes'], ids)
    assert sum(1 for i in flat if i[0] == 'row') == 4
    assert sum(1 for i in E.flatten(res['nodes'], ids, summary_only=True) if i[0] == 'row') == 0


def test_groups_sorted_by_numeric_sort_column():
    res = E.run(ROWS, COLS, st(group_keys=['acc'], sort_key='debit', asc=False))
    assert res['nodes'][0].label == 'الصندوق'
    res = E.run(ROWS, COLS, st(group_keys=['acc'], sort_key='debit', asc=True))
    assert res['nodes'][0].label == 'البنك'


def test_filters_then_totals_follow_filters():
    res = E.run(ROWS, COLS, st(filters={'acc': 'صندوق', 'debit': '>0'}))
    assert res['count'] == 2 and res['totals']['debit'] == 300.0 and res['source_count'] == 4


def test_kpis_and_chart_data():
    k = E.auto_kpis(ROWS, COLS)
    assert k[0] == ('عدد الصفوف', '4') and k[1] == ('مدين', '350.00')
    title, pts = E.chart_data(ROWS, COLS, st(group_keys=['date:month']), 'debit')
    assert [p[0] for p in pts] == ['2026-01', '2026-02'] and pts[0][1] == 150.0
    title, pts = E.chart_data(ROWS, COLS, st(), 'debit')
    assert pts[0][1] == 200.0


def test_export_table_matches_view():
    t = E.export_table(ROWS, COLS, st(group_keys=['acc'], visible=['acc', 'debit', 'bal']))
    assert t['table'][0] == ['الحساب', 'مدين', 'الرصيد']
    assert t['table'][1][0].startswith('البنك') and t['table'][1][1] == 50.0
    assert t['table'][-1][0].startswith('الإجمالي') and t['table'][-1][1] == 350.0 and t['row_styles'][len(t['table']) - 1] == 'net'
    plain = E.export_table(ROWS, COLS, st(sort_key='debit', asc=False))
    assert plain['table'][1][3] == 200.0 and len(plain['table']) == 6


def test_total_and_style_rows_are_ignored_in_filters():
    rows = ROWS + [{'_style': 'total', 'acc': 'إجمالي', 'debit': 999.0}]
    assert E.run(rows, COLS, st())['totals']['debit'] == 350.0
