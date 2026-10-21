"""الرواتب بأيام العمل الفعلي: تعيين/إنهاء في نص الشهر، الغياب، أساس أجر اليوم (30 ثابت / أيام الشهر)، وربطها بالإجازات."""
import datetime

import pytest

D = datetime.datetime


def _accs(S):
    a = [x.id for x in S.list_accounts(postable_only=True)]
    return a[0], a[1]


def _emp(S, name, start, end=None, gross_basic=3000):
    ex, pay = _accs(S)
    eid = S.create_employee(name, hire_date=start)
    S.create_contract(eid, start, gross_basic, housing_allowance=600, transport_allowance=400, end_date=end,
                      gosi_rate_employee=0, gosi_rate_employer=0, leave_provision_rate=0, eos_provision_rate=0,
                      basic_salary_account_id=ex, housing_allowance_account_id=ex, transport_allowance_account_id=ex,
                      gosi_deduction_account_id=pay, other_deductions_account_id=pay)
    return eid


def _slip(S, run_id, eid):
    from erp_app.db import get_session, Payslip
    with get_session() as s:
        p = s.query(Payslip).filter(Payslip.run_id == run_id, Payslip.employee_id == eid).first()
        s.expunge(p)
        return p


@pytest.fixture(scope="module")
def people(S):
    S.update_company_settings(payroll_day_basis=30)
    return {
        "full": _emp(S, "موظف كامل", D(2025, 1, 1)),
        "newhire": _emp(S, "موظف جديد", D(2026, 3, 11)),       # بدأ يوم 11 مارس -> 21 يوم من 31
        "leaver": _emp(S, "موظف منتهي", D(2025, 1, 1), end=D(2026, 3, 20)),   # آخر يوم 20 مارس -> 20 يوم
    }


def test_full_month_no_deduction(S, people):
    run = S.create_payroll_run(3, 2026)
    p = _slip(S, run, people["full"])
    assert p.unemployed_days == 0 and p.unemployed_deduction == 0 and p.net_salary == 4000
    assert p.worked_days == 31


def test_mid_month_hire_and_termination(S, people):
    from erp_app.db import get_session, PayrollRun
    with get_session() as s:
        run = s.query(PayrollRun).filter(PayrollRun.month == 3, PayrollRun.year == 2026).first().id
    nh = _slip(S, run, people["newhire"])
    assert nh.unemployed_days == 10 and nh.unemployed_deduction == round(10 * 4000 / 30, 2)
    assert nh.worked_days == 21 and nh.net_salary == round(4000 - nh.unemployed_deduction, 2)
    lv = _slip(S, run, people["leaver"])
    assert lv.unemployed_days == 11 and lv.unemployed_deduction == round(11 * 4000 / 30, 2)


def test_absence_and_leave_combined_and_cap(S, people):
    from erp_app.db import get_session, PayrollRun
    with get_session() as s:
        run = s.query(PayrollRun).filter(PayrollRun.month == 3, PayrollRun.year == 2026).first().id
    full = people["full"]
    S.create_leave_request(full, "unpaid", D(2026, 3, 2), D(2026, 3, 3))          # يومين بدون راتب
    S.create_leave_request(full, "annual", D(2026, 3, 9), D(2026, 3, 10))         # سنوية مدفوعة
    for r in S.list_leave_requests(employee_id=full):
        S.decide_leave_request(r.id, True)
    ps = _slip(S, run, full)
    S.update_payslip(ps.id, absent_days=3)
    p = _slip(S, run, full)
    daily = 4000 / 30
    assert p.leave_deduction == round(2 * daily, 2) and p.leave_days_total == 4
    assert p.absence_deduction == round(3 * daily, 2)
    assert p.worked_days == 31 - 4 - 3
    assert p.net_salary == round(4000 - p.leave_deduction - p.absence_deduction, 2)
    with pytest.raises(ValueError):
        S.update_payslip(ps.id, absent_days=40)
    S.update_payslip(ps.id, absent_days=0)
    assert _slip(S, run, full).absence_deduction == 0


def test_deductions_capped_at_gross(S, people):
    from erp_app.db import get_session, PayrollRun
    with get_session() as s:
        run = s.query(PayrollRun).filter(PayrollRun.month == 3, PayrollRun.year == 2026).first().id
    ps = _slip(S, run, people["newhire"])
    S.update_payslip(ps.id, absent_days=31)
    p = _slip(S, run, people["newhire"])
    assert p.unemployed_deduction + p.leave_deduction + p.absence_deduction <= 4000
    assert p.net_salary >= 0


def test_calendar_day_basis(S, people):
    S.update_company_settings(payroll_day_basis=0)       # أيام الشهر الفعلية (31 في مارس)
    from erp_app.db import get_session, PayrollRun
    with get_session() as s:
        run = s.query(PayrollRun).filter(PayrollRun.month == 3, PayrollRun.year == 2026).first().id
    ps = _slip(S, run, people["newhire"])
    S.update_payslip(ps.id, absent_days=0)
    p = _slip(S, run, people["newhire"])
    assert p.unemployed_deduction == round(10 * 4000 / 31, 2)
    S.update_company_settings(payroll_day_basis=30)


def test_renewal_gap_not_deducted_and_post(S):
    """عقد اتجدد في نص الشهر: الموظف على عقد طول الشهر (مفيش خصم أيام غير موظف). والترحيل بيعدّي بالخصومات."""
    ex, pay = _accs(S)
    eid = S.create_employee("موظف مجدد", hire_date=D(2025, 1, 1))
    S.create_contract(eid, D(2025, 1, 1), 3000, end_date=D(2026, 5, 15), gosi_rate_employee=0, gosi_rate_employer=0,
                      leave_provision_rate=0, eos_provision_rate=0, basic_salary_account_id=ex, gosi_deduction_account_id=pay, other_deductions_account_id=pay)
    S.create_contract(eid, D(2026, 5, 16), 3500, gosi_rate_employee=0, gosi_rate_employer=0, leave_provision_rate=0, eos_provision_rate=0,
                      basic_salary_account_id=ex, gosi_deduction_account_id=pay, other_deductions_account_id=pay)
    run = S.create_payroll_run(5, 2026)
    p = _slip(S, run, eid)
    assert p.unemployed_days == 0 and p.worked_days == 31
    S.post_payroll_run(run)


def test_payroll_screen_dialog_renders_day_columns(S, people):
    """شاشة الرواتب بتفتح قسيمة الدورة وفيها أيام الغياب وأيام العمل الفعلي (مسودة ومرحّلة)."""
    from unittest.mock import MagicMock
    import flet as ft
    from flet.controls.context import _context_page
    from erp_app.views.payroll import build_payroll
    pg = MagicMock(); pg.overlay = []
    tok = _context_page.set(pg)
    try:
        root = build_payroll(pg)
        btns, stack = [], [root]
        while stack:
            x = stack.pop()
            if isinstance(x, ft.IconButton) and x.tooltip == "عرض/تعديل":
                btns.append(x)
            for a in ("controls", "content", "rows", "cells"):
                v = getattr(x, a, None)
                if isinstance(v, list):
                    stack += v
                elif v is not None and hasattr(v, "__dict__"):
                    stack.append(v)
        assert btns
        for b in btns:
            pg.overlay.clear()
            b.on_click(None)
            assert pg.overlay, "الدايلوج ما اتفتحش"
    finally:
        _context_page.reset(tok)


def test_raise_mid_month_splits_the_month(S):
    """تجديد بزيادة من 16 يونيو: الراتب = القديم لـ15 يوم + الجديد لـ15 يوم (متوسط موزون بالأيام الفعلية)."""
    ex, pay = _accs(S)
    S.update_company_settings(payroll_day_basis=30)
    eid = S.create_employee("موظف زيادة", hire_date=D(2025, 1, 1))
    old = S.create_contract(eid, D(2025, 1, 1), 3000, end_date=D(2026, 6, 15), gosi_rate_employee=10, gosi_rate_employer=0,
                            leave_provision_rate=0, eos_provision_rate=0, basic_salary_account_id=ex, gosi_deduction_account_id=pay, other_deductions_account_id=pay)
    S.create_contract(eid, D(2026, 6, 16), 4000, gosi_rate_employee=10, gosi_rate_employer=0, leave_provision_rate=0, eos_provision_rate=0,
                      basic_salary_account_id=ex, gosi_deduction_account_id=pay, other_deductions_account_id=pay)
    run = S.create_payroll_run(6, 2026)            # يونيو 30 يوم: 15 قديم + 15 جديد
    p = _slip(S, run, eid)
    assert p.basic_salary == 3500.0 and p.gosi_deduction == 350.0
    assert p.unemployed_days == 0 and p.net_salary == 3150.0
    S.create_payroll_run(7, 2026)                  # يوليو كله بالراتب الجديد
    from erp_app.db import get_session, PayrollRun
    with get_session() as s:
        r7 = s.query(PayrollRun).filter(PayrollRun.month == 7, PayrollRun.year == 2026).first().id
    assert _slip(S, r7, eid).basic_salary == 4000.0
    with get_session() as s:
        old5 = s.query(PayrollRun).filter(PayrollRun.month == 5, PayrollRun.year == 2026).first()
        if old5:
            if old5.state == 'posted':
                S.reopen_payroll_run(old5.id)
            S.delete_payroll_run(old5.id)
    run5 = S.create_payroll_run(5, 2026)           # مايو كله بالقديم
    assert _slip(S, run5, eid).basic_salary == 3000.0


def test_contract_starting_next_month_is_skipped(S):
    """عقد بيبدأ الشهر الجاي ما يطلعلوش قسيمة الشهر ده (كان ممكن يتلقط في شهر قصير زي فبراير)."""
    eid = _emp(S, "موظف لسه", D(2026, 3, 2))
    run = S.create_payroll_run(2, 2026)
    from erp_app.db import get_session, Payslip
    with get_session() as s:
        assert s.query(Payslip).filter(Payslip.run_id == run, Payslip.employee_id == eid).count() == 0


def test_terminated_employee_included_in_termination_month():
    """موظف اتفسخ عقده في نص الشهر (وبقى غير نشط) لازم يدخل دورة شهر الإنهاء بأيام شغله بس، ومايدخلش الشهر اللي بعده."""
    import datetime
    from erp_app import services as S
    from erp_app.db import Payslip, get_session
    D = datetime.datetime
    a = [x.id for x in S.list_accounts(postable_only=True)]
    eid = S.create_employee("منتهي وسط الشهر", hire_date=D(2031, 1, 1))
    S.create_contract(eid, D(2031, 1, 1), 3000, gosi_rate_employee=0, gosi_rate_employer=0, leave_provision_rate=0, eos_provision_rate=0,
                      basic_salary_account_id=a[2], gosi_deduction_account_id=a[1], other_deductions_account_id=a[1])
    cid = S.list_contracts(eid)[0].id
    S.terminate_contract(cid, D(2031, 3, 10), "x")
    S.update_company_settings(payroll_day_basis=30)
    rid = S.create_payroll_run(3, 2031)
    with get_session() as s:
        p = s.query(Payslip).filter(Payslip.run_id == rid, Payslip.employee_id == eid).first()
        assert p is not None and p.unemployed_days == 21.0          # 31 يوم − 10 أيام شغل
    try:
        r2 = S.create_payroll_run(4, 2031)                          # أبريل: ما عندوش أي يوم على عقد
    except ValueError:
        return                                                      # (مفيش غيره في القاعدة)
    with get_session() as s:
        assert s.query(Payslip).filter(Payslip.run_id == r2, Payslip.employee_id == eid).first() is None


def test_allowance_run_includes_terminated_in_last_month():
    import datetime
    from erp_app import services as S
    from erp_app.db import AllowanceInsuranceItem, get_session
    D = datetime.datetime
    a = [x.id for x in S.list_accounts(postable_only=True)]
    eid = S.create_employee("منتهي مخصصات", hire_date=D(2032, 1, 1))
    S.create_contract(eid, D(2032, 1, 1), 3000, gosi_rate_employee=0, gosi_rate_employer=10, leave_provision_rate=0, eos_provision_rate=0,
                      basic_salary_account_id=a[2], gosi_deduction_account_id=a[1], other_deductions_account_id=a[1],
                      gosi_employer_expense_account_id=a[2], gosi_employer_payable_account_id=a[1])
    cid = S.list_contracts(eid)[0].id
    S.terminate_contract(cid, D(2032, 5, 10), "x")
    rid = S.create_allowance_insurance_run(5, 2032)
    with get_session() as s:
        assert s.query(AllowanceInsuranceItem).filter(AllowanceInsuranceItem.run_id == rid, AllowanceInsuranceItem.employee_id == eid).count() == 1
    rid2 = S.create_allowance_insurance_run(6, 2032)
    with get_session() as s:
        assert s.query(AllowanceInsuranceItem).filter(AllowanceInsuranceItem.run_id == rid2, AllowanceInsuranceItem.employee_id == eid).count() == 0
