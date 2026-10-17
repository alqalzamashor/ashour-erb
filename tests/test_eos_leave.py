"""تسوية نهاية الخدمة: حقل أيام الإجازة بيتملي من الرصيد وإجباري."""
import datetime
from unittest.mock import MagicMock

import flet as ft
from flet.controls.context import _context_page

from erp_app.views.eos_settlements import build_eos_settlements
from tests.test_drafts import _walk


def _fields(root):
    return {getattr(c, "label", None): c for c in _walk(root) if getattr(c, "label", None)}


def test_leave_days_required_and_autofilled(S, monkeypatch):
    from erp_app import theme
    made = []
    orig = theme.SearchableDropdown.__init__

    def spy(self, *a, **k):
        orig(self, *a, **k); made.append(self)
    monkeypatch.setattr(theme.SearchableDropdown, '__init__', spy)
    accs = [a.id for a in S.list_accounts(postable_only=True)]
    eid = S.create_employee("موظف تسوية", hire_date=datetime.datetime(2024, 1, 1))
    S.create_contract(eid, datetime.datetime(2024, 1, 1), 3000, housing_allowance=0, transport_allowance=0, other_allowances=0,
                      gosi_rate_employee=0, gosi_rate_employer=0, leave_provision_rate=0, eos_provision_rate=0,
                      basic_salary_account_id=accs[0], gosi_deduction_account_id=accs[1], other_deductions_account_id=accs[1])
    emps = [e for e in S.list_employees(active_only=False) if e.id == eid]
    pg = MagicMock(); pg.overlay = []
    _context_page.set(pg)
    root = build_eos_settlements(pg)
    f = _fields(root)
    leave = next(v for k, v in f.items() if "أيام الإجازة غير المستخدمة" in str(k))
    assert "اختياري" not in leave.label and leave.label.endswith("*")
    emp = next(m for m in made if m.label == "الموظف *")
    emp.value = str(emps[0].id)
    emp.on_change(None)
    exp = S.calculate_eos_settlement(emps[0].id, datetime.datetime.combine(
        datetime.date.today(), datetime.time()), "resignation", None)
    assert leave.value == f"{exp['unused_leave_days']:g}"


def test_balance_is_prorated_by_service_not_fixed(S):
    D = datetime.datetime
    accs = [a.id for a in S.list_accounts(postable_only=True)]
    eid = S.create_employee("موظف رصيد", hire_date=D(2026, 1, 1))
    S.create_contract(eid, D(2026, 1, 1), 3000, housing_allowance=0, transport_allowance=0, other_allowances=0,
                      gosi_rate_employee=0, gosi_rate_employer=0, leave_provision_rate=0, eos_provision_rate=0,
                      basic_salary_account_id=accs[0], gosi_deduction_account_id=accs[1], other_deductions_account_id=accs[1])
    cfg_days = float(S.get_company_settings().annual_leave_days or 21)
    half = S.calculate_eos_settlement(eid, D(2026, 6, 30), "resignation", None)["unused_leave_days"]
    full = S.calculate_eos_settlement(eid, D(2026, 12, 31), "resignation", None)["unused_leave_days"]
    assert half == round(cfg_days * 180 / 365.25, 2) and half < full
    assert full == round(cfg_days * 364 / 365.25, 2)
    # إجازة سنوية معتمدة بتتخصم
    rid = S.create_leave_request(eid, "annual", D(2026, 3, 1), D(2026, 3, 5))
    S.decide_leave_request(rid, True)
    assert S.calculate_eos_settlement(eid, D(2026, 12, 31), "termination", None)["unused_leave_days"] == round(cfg_days * 364 / 365.25 - 5, 2)
    # حتى لو الإجازة بعد آخر يوم عمل أو لسه معلّقة، بتتخصم زي شاشة الرصيد
    rid2 = S.create_leave_request(eid, "annual", D(2026, 12, 20), D(2026, 12, 21))
    c = S.calculate_eos_settlement(eid, D(2026, 6, 30), "resignation", None)
    assert c["leave_used"] == 7 and c["unused_leave_days"] == round(cfg_days * 180 / 365.25 - 7, 2)


def test_balance_starts_from_last_posted_settlement(S):
    D = datetime.datetime
    accs = [a.id for a in S.list_accounts(postable_only=True)]
    eid = S.create_employee("موظف تسوية سابقة", hire_date=D(2024, 1, 1))
    S.create_contract(eid, D(2024, 1, 1), 3000, housing_allowance=0, transport_allowance=0, other_allowances=0,
                      gosi_rate_employee=0, gosi_rate_employer=0, leave_provision_rate=0, eos_provision_rate=0,
                      basic_salary_account_id=accs[0], gosi_deduction_account_id=accs[1], other_deductions_account_id=accs[1])
    sid = S.create_annual_leave_settlement(eid, D(2025, 1, 1))
    S.post_annual_leave_settlement(sid)
    closing = S.get_last_annual_leave_settlement(eid).closing_balance
    assert closing > 0
    c = S.calculate_eos_settlement(eid, D(2025, 7, 1), "resignation", None)
    cfg_days = float(S.get_company_settings().annual_leave_days or 21)
    accrued = round(181 / 365.25 * cfg_days, 2)
    assert c["leave_from_settlement"] and c["leave_opening"] == round(closing, 2) and c["leave_accrued"] == accrued
    assert c["unused_leave_days"] == round(closing + accrued, 2)
    # إجازة قبل التسوية مبتتحسبش تاني، وبعدها بتتخصم
    rid = S.create_leave_request(eid, "annual", D(2025, 2, 1), D(2025, 2, 3)); S.decide_leave_request(rid, True)
    c2 = S.calculate_eos_settlement(eid, D(2025, 7, 1), "resignation", None)
    assert c2["unused_leave_days"] == round(closing + accrued - 3, 2)
