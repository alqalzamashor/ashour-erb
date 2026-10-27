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
