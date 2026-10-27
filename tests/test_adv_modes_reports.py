"""وضع العارض المتقدم في تقارير التجارة وأسعار الشراء والرواتب وميزان المراجعة."""
from unittest.mock import MagicMock

import flet as ft
from flet.controls.context import _context_page

from tests.test_drafts import _walk


def _page():
    pg = MagicMock(); pg.overlay = []; _context_page.set(pg)
    return pg


def _tables(root):
    return [c for c in _walk(root) if isinstance(c, ft.DataTable)]


def test_trial_balance_adv(S):
    from erp_app.views.trial_balance import build_trial_balance
    root = build_trial_balance(_page())
    dd = next(c for c in _walk(root) if isinstance(c, ft.Dropdown) and c.label == 'تجميع حسب')
    assert any(o.key == 'adv' for o in dd.options)
    dd.value = 'adv'; dd.on_select(MagicMock())
    assert any(len(t.columns) == 11 for t in _tables(root))


def test_trade_reports_adv_switch(S):
    from erp_app.views.trade_reports import build_sales_reports, build_purchase_reports
    for b, n in ((build_sales_reports, 14), (build_purchase_reports, 11)):
        root = b(_page())
        sw = next(c for c in _walk(root) if isinstance(c, ft.Switch) and 'متقدم' in (c.label or ''))
        sw.value = True; sw.on_change(MagicMock())
        assert any(len(t.columns) == n for t in _tables(root)), (b.__name__, [len(t.columns) for t in _tables(root)])


def test_payroll_adv_switch(S):
    from erp_app.views.payroll_report import build_payroll_report
    root = build_payroll_report(_page())
    sw = next(c for c in _walk(root) if isinstance(c, ft.Switch) and 'متقدم' in (c.label or ''))
    sw.value = True; sw.on_change(MagicMock())
    assert any(len(t.columns) == 10 for t in _tables(root))


def test_purchase_price_adv_switch(S):
    from erp_app.views.purchase_price_report import build_purchase_price_report
    root = build_purchase_price_report(_page())
    sw = next(c for c in _walk(root) if isinstance(c, ft.Switch) and 'متقدم' in (c.label or ''))
    sw.value = True; sw.on_change(MagicMock())      # من غير بيانات: لازم ما يقعش


def test_sticky_header_clone_follows_columns_change(S):
    """تغيير أعمدة جدول بعد ما اتلفّ بـh_scroll لازم يتبعه عنوانه الثابت (وإلا ValueError: صفوف أكتر من الأعمدة)."""
    from erp_app import theme
    _page()
    t = ft.DataTable(columns=[ft.DataColumn(ft.Text(''))], rows=[])
    theme.h_scroll(t, vscroll=True)
    t.columns = [ft.DataColumn(ft.Text('a')), ft.DataColumn(ft.Text('b'))]
    t.rows = [ft.DataRow(cells=[ft.DataCell(ft.Text('1')), ft.DataCell(ft.Text('2'))])]
    clone = t._erp_clone
    assert len(clone.columns) == 2 and len(clone.rows) == 1
    clone.before_update()           # كان بيرمي ValueError


def test_trade_reports_tables_valid(S):
    from erp_app.views.trade_reports import build_sales_reports
    root = build_sales_reports(_page())
    for t in _tables(root):
        t.before_update()


def test_stock_moves_viewer_row_actions(S):
    from erp_app.views.stock_moves import build_stock_moves
    root = build_stock_moves(_page())
    for t in _tables(root):
        t.before_update()
    assert any(len(t.columns) == 8 for t in _tables(root))


def test_banking_lists_viewer_with_data(S, tmp_path):
    import gc
    from erp_app import banking, theme
    cash = next(a for a in S.list_accounts(postable_only=True))
    ba = banking.save_bank_account('BK1', 'حساب اختبار', cash.id, 'بنك')
    ba_id = ba if isinstance(ba, int) else getattr(ba, 'id', ba)
    prov = banking.save_provider('تجريبي', 'mock', ba_id)
    pid = prov if isinstance(prov, int) else getattr(prov, 'id', prov)
    cust = S.list_customers()[0].id if S.list_customers() else S.create_customer('عميل بنك')
    banking.create_payment_link(pid, 150, cust, 'اختبار')
    f = tmp_path / 'st.csv'
    f.write_text('التاريخ,البيان,مدين,دائن\n2026-10-01,رسوم,10,0\n2026-10-02,إيداع,0,500\n', encoding='utf-8')
    banking.import_statement(ba_id, str(f))
    from erp_app.views.banking import build_banking
    root = build_banking(_page())
    st = [o for o in gc.get_objects() if isinstance(o, theme.SimpleTabs)][-1]
    st._selected_index = 2; st._render()
    t = [t for t in _tables(st.control) if len(t.columns) == 10]
    assert t and len(t[0].rows) >= 1
    t[0].before_update()
