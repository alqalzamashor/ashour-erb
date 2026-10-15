"""أنواع الإجازات (جدول قابل للإضافة) وأثرها على الراتب: مدفوعة / بدون راتب / نسبة خصم، وحد الأيام، وربطها بدورة الرواتب والقيد."""
import datetime

import pytest

D = datetime.datetime


@pytest.fixture(scope="module")
def emp(S):
    accs = [a.id for a in S.list_accounts(postable_only=True)]
    ex, pay = accs[0], accs[1]
    eid = S.create_employee("موظف إجازات", hire_date=D(2025, 1, 1))
    S.create_contract(eid, D(2025, 1, 1), 3000, housing_allowance=600, transport_allowance=400, other_allowances=0,
                      gosi_rate_employee=0, gosi_rate_employer=0, leave_provision_rate=0, eos_provision_rate=0,
                      basic_salary_account_id=ex, housing_allowance_account_id=ex, transport_allowance_account_id=ex,
                      gosi_deduction_account_id=pay, other_deductions_account_id=pay)
    return eid


def test_seeded_types(S):
    labels = S.leave_type_labels()
    assert labels["annual"] == "إجازة سنوية" and labels["unpaid"] == "إجازة بدون راتب" and "sick" in labels
    by = {t.code: t for t in S.list_leave_types()}
    assert by["annual"].uses_annual_balance and by["unpaid"].deduct_percent == 100 and by["sick"].deduct_percent == 0


def test_add_edit_delete_type(S):
    tid = S.save_leave_type(None, "إجازة نص راتب", 50, False, 10)
    t = next(x for x in S.list_leave_types() if x.id == tid)
    assert t.code.startswith("lt") and t.deduct_percent == 50 and t.max_days_per_year == 10
    with pytest.raises(ValueError):
        S.save_leave_type(None, "إجازة نص راتب", 10)          # اسم مكرر
    with pytest.raises(ValueError):
        S.save_leave_type(None, "x", 150)                     # نسبة خارج النطاق
    S.save_leave_type(tid, "نص راتب", 40, False, 10)
    S.delete_leave_type(tid)
    with pytest.raises(ValueError):
        S.delete_leave_type(next(x.id for x in S.list_leave_types() if x.code == "unpaid"))   # أساسي


def test_unpaid_and_partial_leave_deduct_in_payroll(S, emp):
    half = S.save_leave_type(None, "نص راتب", 50, False, 0)
    half_code = next(x.code for x in S.list_leave_types() if x.id == half)
    paid = S.save_leave_type(None, "إجازة زواج", 0, False, 5)
    paid_code = next(x.code for x in S.list_leave_types() if x.id == paid)
    # راتب إجمالي 4000 -> أجر اليوم 133.33
    ids = [S.create_leave_request(emp, "unpaid", D(2026, 3, 2), D(2026, 3, 4)),          # 3 أيام بدون راتب
           S.create_leave_request(emp, half_code, D(2026, 3, 10), D(2026, 3, 11)),       # يومين بنص الخصم = يوم
           S.create_leave_request(emp, paid_code, D(2026, 3, 15), D(2026, 3, 16)),       # مدفوعة: صفر
           S.create_leave_request(emp, "unpaid", D(2026, 3, 20), D(2026, 3, 22))]        # هتتلغى: ما تتحسبش
    for i in ids[:3]:
        S.decide_leave_request(i, True)
    S.decide_leave_request(ids[3], False)
    run = S.create_payroll_run(3, 2026)
    ps = S.get_payroll_run(run).payslips[0] if hasattr(S, "get_payroll_run") else None
    if ps is None:
        from erp_app.db import get_session, Payslip
        with get_session() as s:
            ps = s.query(Payslip).filter(Payslip.run_id == run).first(); s.expunge(ps)
    assert ps.leave_deduction_days == 4.0
    assert ps.leave_deduction == round(4 * 4000 / 30, 2)
    assert ps.net_salary == round(4000 - ps.leave_deduction, 2)
    assert ps.total_deductions == ps.leave_deduction


def test_deduction_capped_and_other_month(S, emp):
    from erp_app.db import get_session
    with get_session() as s:
        # إجازة بدون راتب بتغطي أبريل كله (30 يوم) ومايو يومين: أبريل = الإجمالي بحد أقصى، مايو يومين بس
        pass
    S.create_leave_request(emp, "unpaid", D(2026, 4, 1), D(2026, 5, 2))
    rid = max(r.id for r in S.list_leave_requests())
    S.decide_leave_request(rid, True)
    with get_session() as s:
        assert S.leave_deduction_for(s, emp, 4000, 4, 2026) == (4000.0, 30.0)
        assert S.leave_deduction_for(s, emp, 4000, 5, 2026) == (round(2 * 4000 / 30, 2), 2.0)
        assert S.leave_deduction_for(s, emp, 4000, 6, 2026) == (0.0, 0.0)


def test_max_days_and_inactive(S, emp):
    t = S.save_leave_type(None, "إجازة دراسية", 0, False, 3)
    code = next(x.code for x in S.list_leave_types() if x.id == t)
    S.create_leave_request(emp, code, D(2026, 8, 3), D(2026, 8, 4))
    with pytest.raises(ValueError, match="الحد الأقصى"):
        S.create_leave_request(emp, code, D(2026, 8, 10), D(2026, 8, 11))
    S.save_leave_type(t, "إجازة دراسية", 0, False, 3, is_active=False)
    with pytest.raises(ValueError, match="موقوف"):
        S.create_leave_request(emp, code, D(2026, 9, 1), D(2026, 9, 1))
    with pytest.raises(ValueError):
        S.create_leave_request(emp, "nope", D(2026, 9, 1), D(2026, 9, 1))


def test_custom_type_uses_annual_balance(S, emp):
    before = S.annual_leave_balance(emp, 2027)["remaining"]
    t = S.save_leave_type(None, "إجازة سنوية إضافية", 0, True, 0)
    code = next(x.code for x in S.list_leave_types() if x.id == t)
    S.create_leave_request(emp, code, D(2027, 1, 5), D(2027, 1, 6))
    assert S.annual_leave_balance(emp, 2027)["remaining"] == before - 2


def test_post_includes_leave_deduction(S, emp):
    from erp_app.db import get_session, Payslip, PayrollRun
    run = S.create_payroll_run(4, 2026) if False else None
    with get_session() as s:
        r = s.query(PayrollRun).filter(PayrollRun.month == 4, PayrollRun.year == 2026).first()
        assert r is None            # أبريل لسه ماتعملوش دورة
    rid = S.create_payroll_run(4, 2026)
    S.post_payroll_run(rid)
    with get_session() as s:
        p = s.query(Payslip).filter(Payslip.run_id == rid).first()
        assert p.leave_deduction == 4000.0 and p.net_salary == 0.0


def test_leave_types_screen_builds_and_english(S):
    from unittest.mock import MagicMock
    from erp_app import i18n
    from erp_app.views.leave_requests import build_leave_requests
    page = MagicMock(); page.overlay = []
    ctl = build_leave_requests(page)
    assert ctl is not None
    assert i18n.tr("أنواع الإجازات", "en") == "Leave types" and i18n.tr("خصم الإجازات", "en") == "Leave deduction"
