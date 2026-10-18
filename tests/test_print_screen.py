"""زر الطباعة: أي شاشة (عادي وموبايل) تتحوّل لـ PDF من غير أخطاء، والجداول المترقّمة بتطلع بكل صفوفها."""
import os
from unittest.mock import MagicMock

import flet as ft
import pytest
from flet.controls.context import _context_page

from erp_app import onboarding as ob, print_screen as PS


@pytest.mark.parametrize("compact", [False, True])
def test_print_every_screen(S, compact, tmp_path, monkeypatch):
    import main as M
    monkeypatch.setattr(ob, "PATH", str(tmp_path / "ob.json"))
    from erp_app.db import SalesInvoice, get_session
    with get_session() as s:
        if s.query(SalesInvoice).count() == 0:
            ob.load_demo()
    user = {"id": 1, "username": "admin", "role": "admin", "full_name": "x", "permissions": "{}", "branch_ids": "[]", "cost_center_ids": "[]"}
    pg = MagicMock(); pg.overlay = []; pg._erp_compact = compact; pg.width = 390; pg.height = 800
    tok = _context_page.set(pg)
    bad, with_tables = [], 0
    try:
        for _gk, _t, _i, items in M.GROUPS:
            for key, label, _ic, builder in items:
                pg._erp_cards_used = False
                try:
                    c = builder(pg, user) if key in ("dashboard", "organization", "budgets") else builder(pg)
                    data = PS.extract(c)
                    with_tables += bool(data["tables"])
                    p = PS.print_control(c, label, str(tmp_path / "pdf"))
                    assert os.path.getsize(p) > 800
                except Exception as ex:      # noqa: BLE001
                    bad.append((key, repr(ex)[:160]))
    finally:
        _context_page.reset(tok)
    assert not bad, bad
    assert with_tables >= 15


def test_paged_table_prints_all_rows(tmp_path):
    t = ft.DataTable(columns=[ft.DataColumn(ft.Text("الاسم")), ft.DataColumn(ft.Text("الرقم")), ft.DataColumn(ft.Text(""))],
                     rows=[])
    from erp_app import theme
    pager = theme.RowPager(t, None, 10)
    pager.set_rows([ft.DataRow(cells=[ft.DataCell(ft.Text(f"موظف {i}")), ft.DataCell(ft.Text(str(i))), ft.DataCell(ft.IconButton(ft.Icons.EDIT))]) for i in range(35)])
    assert len(t.rows) == 10
    root = ft.Column([ft.TextField(label="بحث", value="س"), ft.Checkbox(label="نشط", value=True), t])
    d = PS.extract(root)
    assert d["filters"] == [("بحث", "س"), ("نشط", "نعم")]
    assert len(d["tables"]) == 1 and len(d["tables"][0]["rows"]) == 35 and d["tables"][0]["columns"] == ["الاسم", "الرقم"]
    assert os.path.getsize(PS.print_control(root, "اختبار", str(tmp_path))) > 800
