"""دورة الرواتب بالفرع والقسم، وعدم ترحيل شهر وفيه شهر بعده مترحّل."""
import datetime

import pytest

D = datetime.datetime


def _mk(S, name, branch, cc):
    a = [x.id for x in S.list_accounts(postable_only=True)]
    eid = S.create_employee(name, hire_date=D(2030, 1, 1), branch_id=branch, cost_center_id=cc)
    S.create_contract(eid, D(2030, 1, 1), 3000, housing_allowance=0, transport_allowance=0, other_allowances=0,
                      gosi_rate_employee=0, gosi_rate_employer=0, leave_provision_rate=0, eos_provision_rate=0,
                      basic_salary_account_id=a[0], gosi_deduction_account_id=a[1], other_deductions_account_id=a[1])
    return eid


def _emps(S, rid):
    from erp_app.db import Payslip, get_session
    with get_session() as s:
        return {e for (e,) in s.query(Payslip.employee_id).filter(Payslip.run_id == rid).all()}


@pytest.fixture(scope="module")
def org(S):
    b1 = S.create_branch("PS1", "فرع أ"); b2 = S.create_branch("PS2", "فرع ب")
    c1 = S.create_cost_center("PC1", "قسم 1"); c2 = S.create_cost_center("PC2", "قسم 2")
    ids = lambda x: x if isinstance(x, int) else getattr(x, "id", x)
    b1, b2, c1, c2 = map(ids, (b1, b2, c1, c2))
    e = {"a1": _mk(S, "ف أ ق1", b1, c1), "a2": _mk(S, "ف أ ق2", b1, c2), "b1": _mk(S, "ف ب ق1", b2, c1)}
    return b1, b2, c1, c2, e


def test_run_by_branch_and_department(S, org):
    b1, b2, c1, c2, e = org
    r_a = S.create_payroll_run(1, 2030, branch_id=b1)
    assert _emps(S, r_a) == {e["a1"], e["a2"]}
    r_b1 = S.create_payroll_run(1, 2030, branch_id=b2, cost_center_id=c1)
    assert _emps(S, r_b1) == {e["b1"]}
    with pytest.raises(ValueError):                       # نفس الفرع والقسم تاني
        S.create_payroll_run(1, 2030, branch_id=b1)
    with pytest.raises(ValueError):                       # قسم مفيهوش موظفين متاحين (اتحسبوا)
        S.create_payroll_run(1, 2030, branch_id=b1, cost_center_id=c2)
    run = S.get_payroll_run(r_a)
    assert run.scope_branch_id == b1 and run.scope_cost_center_id is None


def test_cannot_post_month_before_a_posted_later_month(S, org):
    b1, b2, c1, c2, e = org
    r_feb = S.create_payroll_run(2, 2030, branch_id=b1)
    r_mar = S.create_payroll_run(3, 2030, branch_id=b1)
    S.post_payroll_run(r_mar)
    with pytest.raises(ValueError, match="اترحّلت بالفعل"):
        S.post_payroll_run(r_feb)
    other = S.create_payroll_run(2, 2030, branch_id=b2)   # فرع تاني مفيهوش شهر لاحق مرحّل
    S.post_payroll_run(other)


def test_run_dialog_groups_by_branch_and_department(S, org):
    """نافذة الدورة: سطر إجمالي لكل فرع/قسم (مطوي) فيه موظفينه."""
    from unittest.mock import MagicMock
    import flet as ft
    from flet.controls.context import _context_page
    from erp_app.views.payroll import build_payroll
    from tests.test_view_controls import _bad
    b1, b2, c1, c2, e = org
    rid = S.create_payroll_run(4, 2030)           # كل الموظفين في دورة واحدة
    assert len(_emps(S, rid)) >= 3
    pg = MagicMock(); pg.overlay = []; _context_page.set(pg)
    root = build_payroll(pg)
    from tests.test_drafts import _walk
    btns = [c for c in _walk(root) if isinstance(c, ft.IconButton) and getattr(c, "tooltip", "") == "عرض/تعديل"]
    assert btns
    for b in btns:
        b.on_click(None)
    dlgs = [o for o in pg.overlay if isinstance(o, ft.AlertDialog)]
    assert dlgs and _bad(dlgs[-1].content) == []
    texts = [c.value for d in dlgs for c in _walk(d.content) if isinstance(c, ft.Text) and isinstance(c.value, str)]
    assert any(" / " in t and ("فرع أ" in t or "بدون فرع" in t or "الفرع" in t) for t in texts)
    assert any(t.endswith(" موظف") for t in texts)
