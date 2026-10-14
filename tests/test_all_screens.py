"""كل شاشات القوائم لازم تتبني من غير أخطاء - بالوضع العادي ووضع الموبايل - على قاعدة فيها بيانات (دي اللي لقطت خطأ ft.border.only في أعمار الديون)."""
from unittest.mock import MagicMock

import pytest
from flet.controls.context import _context_page

from erp_app import onboarding as ob


@pytest.mark.parametrize("compact", [False, True])
def test_every_screen_builds(S, compact, tmp_path, monkeypatch):
    import main as M
    monkeypatch.setattr(ob, "PATH", str(tmp_path / "ob.json"))
    from erp_app.db import SalesInvoice, get_session
    with get_session() as s:
        empty = s.query(SalesInvoice).count() == 0
    if empty:
        ob.load_demo()
    user = {"id": 1, "username": "admin", "role": "admin", "full_name": "x", "permissions": "{}", "branch_ids": "[]", "cost_center_ids": "[]"}
    pg = MagicMock(); pg.overlay = []; pg._erp_compact = compact; pg.width = 390; pg.height = 800
    tok = _context_page.set(pg)
    bad, n = [], 0
    try:
        for _gk, _title, _icon, items in M.GROUPS:
            for key, _label, _ic, builder in items:
                n += 1
                pg._erp_cards_used = False
                try:
                    c = builder(pg, user) if key in ("dashboard", "organization", "budgets") else builder(pg)
                    if compact:
                        M._compact_headers(c, 390.0)
                except Exception as ex:      # noqa: BLE001
                    bad.append((key, repr(ex)[:160]))
    finally:
        _context_page.reset(tok)
    assert n > 60
    assert not bad, bad
