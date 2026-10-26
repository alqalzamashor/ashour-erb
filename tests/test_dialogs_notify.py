"""الشاشات المنبثقة الموحّدة: confirm / Esc / notify."""
from unittest.mock import MagicMock

import flet as ft

from erp_app import theme


def _page():
    pg = MagicMock(); pg.overlay = []; pg.on_keyboard_event = None
    return pg


def test_confirm_runs_once_and_closes():
    pg = _page(); calls = []
    dlg = theme.confirm(pg, "حذف", "متأكد؟", lambda: calls.append(1))
    assert dlg.open and dlg in pg.overlay
    yes = dlg.actions[1]
    yes.on_click(None); yes.on_click(None)          # ضغط مزدوج
    assert calls == [1] and dlg.open is False


def test_confirm_error_becomes_error_snackbar():
    pg = _page()
    def boom(): raise ValueError("ممنوع")
    dlg = theme.confirm(pg, "حذف", "م", boom)
    dlg.actions[1].on_click(None)
    sb = [c for c in pg.overlay if isinstance(c, ft.SnackBar)]
    assert sb and sb[-1].bgcolor == theme._NOTIFY_STYLE['error'][0]


def test_escape_closes_top_dialog_only():
    pg = _page()
    d1 = theme.confirm(pg, "a", "a", lambda: None); d2 = theme.confirm(pg, "b", "b", lambda: None)
    h = theme.install_dialog_keys(pg)
    h(MagicMock(key="Escape"))
    assert d2.open is False and d1.open is True
    h(MagicMock(key="Escape"))
    assert d1.open is False


def test_notify_kinds():
    pg = _page()
    for k in ("success", "error", "warning", "info", "غير معروف"):
        sb = theme.notify(pg, "رسالة", k)
        assert sb.open and sb.bgcolor
    assert theme.notify(pg, "x", "error").duration > theme.notify(pg, "x", "success").duration


def test_all_snackbars_are_styled_by_kind():
    assert ft.SnackBar(ft.Text("تعذر الحفظ"), open=True).bgcolor == theme._NOTIFY_STYLE['error'][0]
    assert ft.SnackBar(ft.Text("تم الحفظ"), open=True).bgcolor == theme._NOTIFY_STYLE['success'][0]
    assert ft.SnackBar(ft.Text("أي حاجة"), open=True).bgcolor == theme._NOTIFY_STYLE['info'][0]
    assert ft.SnackBar(ft.Text("س"), open=True, data='error').bgcolor == theme._NOTIFY_STYLE['error'][0]
    assert ft.SnackBar(ft.Text("س"), bgcolor='#000000').bgcolor == '#000000'      # صريح يتساب


def test_negative_numbers_red_and_icon_tooltips_and_empty_state():
    neg = ft.DataCell(ft.Text("-1,234.50")); pos = ft.DataCell(ft.Text("1,234.50")); txt = ft.DataCell(ft.Text("عميل-1"))
    assert neg.content.color == theme.DANGER and pos.content.color is None and txt.content.color is None
    assert ft.IconButton(icon=ft.Icons.DELETE_OUTLINE).tooltip == "حذف"
    assert ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip="x").tooltip == "x"
    assert theme.empty_state("فاضي", hint="تلميح") is not None


def test_global_keys_escape_closes_dialog():
    import main
    pg = _page()
    d = theme.confirm(pg, "a", "a", lambda: None)
    main._global_keys(MagicMock(key="Escape"), None, pg)
    assert d.open is False
