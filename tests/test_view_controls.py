"""كل عناصر الشاشات لازم تكون Controls حقيقية (مش wrapper زي DateField) - وإلا Flet يفشل في التسلسل ويظهر ERROR في المتصفح."""
from unittest.mock import MagicMock

import flet as ft
import pytest
from flet.controls.context import _context_page

from erp_app.views.attendance import build_attendance
from erp_app.views.employee_balances import build_employee_balances
from erp_app.views.employee_reports import build_employee_reports
from erp_app.views.eos_settlements import build_eos_settlements
from erp_app.views.fiscal_periods import build_fiscal_periods
from erp_app.views.payroll import build_payroll
from erp_app.views.employees import build_employees


def _bad(root, seen=None, path="root"):
    seen = seen if seen is not None else set()
    if id(root) in seen:
        return []
    seen.add(id(root)); out = []
    for a in ("controls", "content", "rows", "cells", "actions", "tabs", "leading", "trailing", "title", "icon_content"):
        v = getattr(root, a, None)
        items = v if isinstance(v, list) else ([v] if v is not None and not isinstance(v, (str, int, float, bool)) else [])
        for i, x in enumerate(items):
            if isinstance(x, ft.BaseControl):
                out += _bad(x, seen, f"{path}.{a}[{i}]")
            elif hasattr(x, "__dict__") and not isinstance(x, (ft.Text,)) and type(x).__module__.startswith("erp_app"):
                out.append(f"{path}.{a}[{i}]={type(x).__name__}")
    return out


@pytest.mark.parametrize("builder", [build_attendance, build_employee_balances, build_employee_reports, build_eos_settlements, build_fiscal_periods, build_payroll, build_employees])
def test_no_wrapper_objects_in_control_tree(S, builder):
    pg = MagicMock(); pg.overlay = []; _context_page.set(pg)
    assert _bad(builder(pg)) == []
