"""بناء كل الشاشات بصفحة وهمية في الوضعين الفاتح والليلي: بيكشف أخطاء الاستيراد والاستعلام والبناء (مش بيختبر الشكل نفسه)."""
from unittest.mock import MagicMock

import pytest

import main as app_main
from erp_app import theme


@pytest.mark.parametrize("dark", [False, True])
def test_every_screen_builds(S, shop, dark):
    theme.set_dark(dark, save=False)
    try:
        pg = MagicMock(); pg.overlay = []; pg.height = 900
        user = S.authenticate_user("admin", "admin")
        failed = []
        for g in app_main.GROUPS:
            for key, _label, _icon, builder in g[3]:
                try:
                    builder(pg, user) if key in ("dashboard", "organization", "budgets") else builder(pg)
                except Exception as e:           # noqa: BLE001
                    failed.append((key, repr(e)[:150]))
        assert failed == []
    finally:
        theme.set_dark(False, save=False)


def test_global_search_respects_permissions(S, shop):
    from erp_app import global_search
    assert any(g["screen"] == "customers" for g in global_search.search("نقدي"))
    S.create_user("nobody", "pw12345", "لا شيء", "viewer")
    admin = S.current_user()
    try:
        S.set_current_user(S.authenticate_user("nobody", "pw12345"))
        assert global_search.search("نقدي") == []
    finally:
        S.set_current_user(admin)
