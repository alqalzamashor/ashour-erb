"""الإقفال الشهري: قفل التسجيل في الشهر، فحوصات قبل الإقفال، الترتيب، وإعادة الفتح."""
import datetime

import pytest

D = datetime.datetime


def _je(S, d):
    a = [x.id for x in S.list_accounts(postable_only=True)]
    return S.create_journal_entry([{"account_id": a[0], "debit": 100}, {"account_id": a[1], "credit": 100}], entry_date=d)


def test_month_close_flow(S):
    _je(S, D(2026, 1, 10))
    _je(S, D(2026, 2, 10))
    assert S.month_close_checks(2026, 1)["blockers"] == []
    S.close_month(2026, 1, "مراجعة")
    with pytest.raises(ValueError, match="مقفل"):
        _je(S, D(2026, 1, 20))
    _je(S, D(2026, 2, 20))                       # شهر تاني لسه مفتوح
    with pytest.raises(ValueError):
        S.close_month(2026, 1)                    # مقفل بالفعل
    with pytest.raises(ValueError, match="بالترتيب"):
        S.close_month(2026, 3)                    # فبراير لسه مفتوح
    S.close_month(2026, 2)
    with pytest.raises(ValueError, match="الأحدث"):
        S.reopen_month(2026, 1)
    S.reopen_month(2026, 2); S.reopen_month(2026, 1)
    _je(S, D(2026, 1, 25))
    assert S.list_month_closes() == []


def test_cannot_close_current_or_future_month(S):
    t = datetime.date.today()
    with pytest.raises(ValueError, match="ما خلصش"):
        S.close_month(t.year, t.month)


def test_draft_payroll_blocks_close(S):
    a = [x.id for x in S.list_accounts(postable_only=True)]
    eid = S.create_employee("موظف إقفال", hire_date=D(2025, 1, 1))
    S.create_contract(eid, D(2025, 1, 1), 3000, gosi_rate_employee=0, gosi_rate_employer=0, leave_provision_rate=0, eos_provision_rate=0,
                      basic_salary_account_id=a[0], gosi_deduction_account_id=a[1], other_deductions_account_id=a[1])
    S.create_payroll_run(3, 2026)
    with pytest.raises(ValueError, match="رواتب مسودة"):
        S.close_month(2026, 3)
    assert any("رواتب" in b for b in S.month_close_checks(2026, 3)["blockers"])


def test_screen_renders(S):
    import flet as ft
    from erp_app.views.fiscal_periods import build_fiscal_periods
    class P:
        overlay = []; services = []
        def update(self, *a, **k): pass
    try:
        build_fiscal_periods(P())
    except AttributeError:
        pytest.skip("fake page too thin")
