import datetime
from erp_app import ifrs, services


def _leaf(chart, code_prefix, typ):
    for a in sorted(chart.acc.values(), key=lambda x: x['code']):
        if a['type'] == typ and a['code'].startswith(code_prefix) and not chart.children.get(a['id']):
            return a['id']
    raise AssertionError(code_prefix)


def _entry(lines, when, branch=None):
    services.create_journal_entry([{'account_id': a, 'debit': d, 'credit': c} for a, d, c in lines], reference='ifrs', entry_date=when, branch_id=branch)


def test_ifrs_statements_balance_and_tree(S):
    ch = ifrs.load_chart()
    cash, cap = _leaf(ch, '1210', 'asset'), _leaf(ch, '3100', 'equity')
    fixed = _leaf(ch, '1110', 'asset')
    sales = _leaf(ch, '4100', 'income')
    cogs = _leaf(ch, '5100', 'expense')
    opex = _leaf(ch, '5200', 'expense')
    loan = _leaf(ch, '2120', 'liability')
    when = datetime.datetime(2031, 3, 10)
    _entry([(cash, 10000, 0), (cap, 0, 10000)], when)
    _entry([(fixed, 3000, 0), (cash, 0, 3000)], when)
    _entry([(cash, 5000, 0), (loan, 0, 5000)], when)
    _entry([(cash, 2000, 0), (sales, 0, 2000)], when)
    _entry([(cogs, 600, 0), (cash, 0, 600)], when)
    _entry([(opex, 300, 0), (cash, 0, 300)], when)
    r = ifrs.build('pl', date_from='2031-01-01', date_to='2031-12-31')
    byid = {x['id']: x for x in r['rows']}
    assert byid['rev:total']['values'][0] == 2000
    assert byid['gross']['values'][0] == 1400
    assert byid['op']['values'][0] == 1100 and byid['net']['values'][0] == 1100
    # الشجرة: كل صف بيتجمّع في أبيه (مفيش صف ابن أكبر من أبيه الوحيد)
    assert any(x['kind'] == 'group' for x in r['rows'] if x['id'].startswith('cogs:'))
    p = ifrs.build('position', date_to='2031-12-31')
    by = {x['id']: x for x in p['rows']}
    assert 'gap' not in by                                   # الميزانية متوازنة
    assert by['a_nc:total']['values'][0] == 3000             # أصول ثابتة = غير متداولة
    assert by['l_nc:total']['values'][0] == 5000             # قرض طويل الأجل = غير متداول
    assert by['a_total']['values'][0] == by['el_total']['values'][0]
    assert by['e:profit']['values'][0] == 1100               # صافي ربح الفترة ضمن حقوق الملكية


def test_ifrs_branch_columns_and_compare(S):
    ch = ifrs.load_chart()
    cash, sales = _leaf(ch, '1210', 'asset'), _leaf(ch, '4100', 'income')
    b = services.list_branches(True)[0]
    _entry([(cash, 700, 0), (sales, 0, 700)], datetime.datetime(2032, 5, 1), branch=b.id)
    _entry([(cash, 300, 0), (sales, 0, 300)], datetime.datetime(2031, 5, 1), branch=b.id)
    r = ifrs.build('pl', date_from='2032-01-01', date_to='2032-12-31', branches=[(b.id, b.name)], by_branch=True, compare=True)
    labels = [c['label'] for c in r['columns']]
    assert labels[-5:] == [labels[-5], 'الإجمالي الموحد', 'الفترة السابقة', 'التغير', '%']
    rev = next(x for x in r['rows'] if x['id'] == 'rev:total')
    ti = labels.index('الإجمالي الموحد')
    assert abs(sum(rev['values'][:ti]) - rev['values'][ti]) < 0.01      # مجموع الفروع = الموحد
    assert rev['values'][ti + 1] >= 300 and rev['values'][ti + 2] == rev['values'][ti] - rev['values'][ti + 1]


def test_visible_rows_levels_and_fmt():
    rows = [ifrs._row('s', None, 0, 'section', 'x', None, has_children=True), ifrs._row('s:1', 's', 1, 'group', 'a', [1.0], has_children=True),
            ifrs._row('s:2', 's:1', 2, 'account', 'b', [1.0])]
    assert [r['id'] for r in ifrs.visible_rows(rows, 1)] == ['s', 's:1']
    assert [r['id'] for r in ifrs.visible_rows(rows, None)] == ['s', 's:1', 's:2']
    assert [r['id'] for r in ifrs.visible_rows(rows, 1, expanded={'s:1'})] == ['s', 's:1', 's:2']
    assert ifrs.fmt(-5) == '(5.00)' and ifrs.fmt(0) == '-' and ifrs.fmt(1234.5) == '1,234.50'


def test_ifrs_views_build_and_toggle(S):
    from unittest.mock import MagicMock
    import flet as ft
    from flet.controls.context import _context_page
    from erp_app.views.financial_consolidation import build_financial_consolidation
    from erp_app.views.reports import build_reports
    pg = MagicMock(); pg.overlay = []; _context_page.set(pg)
    root = build_financial_consolidation(pg)

    def walk(c):
        yield c
        for a in ('controls', 'content', 'actions', 'rows', 'cells'):
            v = getattr(c, a, None)
            for ch in (v if isinstance(v, list) else ([v] if v is not None else [])):
                if hasattr(ch, '__dict__'):
                    yield from walk(ch)
    dd = next(c for c in walk(root) if isinstance(c, ft.Dropdown) and c.label == 'القائمة المالية')
    for k in ('position', 'pl', 'cf', 'equity', 'cc'):
        dd.value = k; dd.on_select(MagicMock())
        assert not [t for t in walk(root) if isinstance(t, ft.Text) and (t.value or '').startswith('تعذر تحميل')], k
    assert build_reports(pg) is not None


def test_ifrs_export_excel_and_pdf(S, tmp_path, monkeypatch):
    import os
    from unittest.mock import MagicMock
    import flet as ft
    from flet.controls.context import _context_page
    from erp_app import theme
    from erp_app.views.financial_consolidation import build_financial_consolidation
    monkeypatch.setattr(theme, 'open_or_download_file', lambda page, path: None)
    monkeypatch.setattr(services, 'downloads_dir', lambda: str(tmp_path))
    pg = MagicMock(); pg.overlay = []; _context_page.set(pg)
    root = build_financial_consolidation(pg)

    def walk(c):
        yield c
        for a in ('controls', 'content', 'actions', 'rows', 'cells'):
            v = getattr(c, a, None)
            for ch in (v if isinstance(v, list) else ([v] if v is not None else [])):
                if hasattr(ch, '__dict__'):
                    yield from walk(ch)
    for label in ('Excel', 'PDF'):
        b = next(c for c in walk(root) if isinstance(c, ft.ElevatedButton) and c.content == label or (isinstance(c, ft.ElevatedButton) and getattr(c, 'text', None) == label))
        b.on_click(MagicMock())
    names = os.listdir(tmp_path)
    assert any(n.endswith('.xlsx') for n in names) and any(n.endswith('.pdf') for n in names), names


def test_ifrs_labels_have_english():
    from erp_app import i18n
    for s in ('قائمة المركز المالي', 'الأصول غير المتداولة', 'إجمالي الالتزامات المتداولة', 'ربح التشغيل', 'الإجمالي الموحد',
              'كما في 2026-10-28', 'للفترة من 2026-01-01 إلى 2026-10-28', 'موحّد - تفصيل حسب الفرع', 'صافي التدفق النقدي من الأنشطة التمويلية'):
        out = i18n.tr(s)
        assert not i18n._AR.search(out), (s, out)
