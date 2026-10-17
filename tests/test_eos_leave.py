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
