"""تثبيت التطبيق على الموبايل (PWA): manifest عربي + أيقونات + viewport في index.html."""
import json
import os

from erp_app import files


def test_ensure_pwa_writes_manifest_icons_and_viewport(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "ASSETS_DIR", str(tmp_path))
    files.ensure_pwa()
    m = json.load(open(tmp_path / "manifest.json", encoding="utf-8"))
    assert m["lang"] == "ar" and m["dir"] == "rtl" and m["display"] == "standalone"
    assert {i["sizes"] for i in m["icons"]} == {"192x192", "512x512"}
    assert any(i.get("purpose") == "maskable" for i in m["icons"])
    for i in m["icons"]:
        p = tmp_path / i["src"]
        assert p.exists() and p.read_bytes()[:4] == b"\x89PNG"
    html = open(tmp_path / "index.html", encoding="utf-8").read()
    assert 'name="viewport"' in html and 'lang="ar"' in html and 'content="Flet"' not in html
    assert (tmp_path / "icons" / "apple-touch-icon-192.png").exists()


def test_ensure_pwa_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "ASSETS_DIR", str(tmp_path))
    files.ensure_pwa(); files.ensure_pwa()
    html = open(tmp_path / "index.html", encoding="utf-8").read()
    assert html.count('name="viewport"') == 1


def test_pos_compact_layout_uses_tabs_and_normal_layout_does_not(S, shop):
    from unittest.mock import MagicMock
    from erp_app.views.pos import build_pos

    def labels(root):
        out = []
        def walk(c):
            out.append(getattr(c, "content", None) if isinstance(getattr(c, "content", None), str) else getattr(c, "label", None))
            for attr in ("controls", "content"):
                v = getattr(c, attr, None)
                for x in (v if isinstance(v, list) else [v]):
                    if x is not None and (hasattr(x, "controls") or hasattr(x, "content")):
                        walk(x)
        walk(root)
        return out

    pg = MagicMock(); pg.overlay = []; pg._erp_compact = True
    assert "الأصناف" in labels(build_pos(pg))
    pg2 = MagicMock(); pg2.overlay = []; pg2._erp_compact = False
    assert "الأصناف" not in labels(build_pos(pg2))


def test_card_table_mode_on_compact_page():
    """موبايل: SortableDataTable بيتعرض كروت (عنوان + اسم عمود: قيمة + أزرار)، وبيتحدّث لما البيانات تتغيّر."""
    import flet as ft
    from flet.controls.context import _context_page
    from types import SimpleNamespace
    from erp_app import theme

    def build():
        t = theme.SortableDataTable(
            columns=[("الكود", lambda r: r[0]), ("الاسم", lambda r: r[1]), ("الإجراءات", None)],
            row_builder=lambda r: ft.DataRow(cells=[ft.DataCell(ft.Text(r[0])), ft.DataCell(ft.Text(r[1])),
                                                      ft.DataCell(ft.Row([ft.IconButton(ft.Icons.EDIT)]))]))
        return t, theme.h_scroll(t.control)

    tok = _context_page.set(SimpleNamespace(_erp_compact=True))
    try:
        t, wrapped = build()
        t.set_data([("A1", "صنف أول"), ("A2", "صنف ثاني")])
    finally:
        _context_page.reset(tok)
    cards = [c for c in _flat(wrapped) if isinstance(c, ft.Container) and isinstance(getattr(c, "content", None), ft.Column) and getattr(c, "border_radius", None) == 12]
    assert len(cards) == 2
    assert any(isinstance(x, ft.IconButton) for x in _flat(cards[0]))
    t.set_data([("A3", "ثالث")])
    cards = [c for c in _flat(wrapped) if isinstance(c, ft.Container) and isinstance(getattr(c, "content", None), ft.Column) and getattr(c, "border_radius", None) == 12]
    assert len(cards) == 1
    # شاشة عادية: جدول عادي مش كروت
    t2, wrapped2 = build()
    assert any(isinstance(x, ft.DataTable) for x in _flat(wrapped2))


def _flat(c):
    yield c
    for attr in ("controls", "content"):
        v = getattr(c, attr, None)
        for x in (v if isinstance(v, list) else [v]):
            if x is not None and hasattr(x, "__dataclass_fields__"):
                yield from _flat(x)


def test_wrap_row_drops_expand_children():
    """Row(wrap=True) مع عنصر expand كان بيطلّع مربع رمادي في المتصفح: بيتشال expand قبل أي تحديث."""
    import flet as ft
    from erp_app import theme  # noqa: F401  (بيركّب التعديل)
    spacer = ft.Container(expand=True)
    r = ft.Row([ft.Text("a"), spacer, ft.Text("b", expand=True)], wrap=True)
    r.before_update()
    assert not spacer.expand and not r.controls[2].expand
    r2 = ft.Row([ft.Text("a"), ft.Container(expand=True)])           # بدون wrap: ما يتغيّرش
    r2.before_update()
    assert r2.controls[1].expand


def test_no_removed_flet_helpers_in_source():
    """ft.padding.symmetric وft.border.only... اتشالت من Flet 0.86 (كانت بتكسر تنبيهات اللوحة الرئيسية وأعمار الديون): ممنوع ترجع."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[1]
    pat = re.compile(r"ft\.(padding|margin)\.(symmetric|only|all)\(|ft\.border\.(only|all|symmetric)\(")
    bad = []
    for f in list(root.glob("erp_app/**/*.py")) + [root / "main.py"]:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line):
                bad.append(f"{f.relative_to(root)}:{i}")
    assert not bad, bad


def test_compact_reflow_wraps_wide_rows_and_caps_widths():
    import flet as ft
    from flet.controls.context import _context_page
    from types import SimpleNamespace
    from erp_app import theme

    def rows():
        wide = ft.Row([ft.TextField(width=300), ft.TextField(width=300), ft.TextField(width=500)])
        top = ft.Row([ft.IconButton(ft.Icons.MENU)] * 9)
        top._erp_nowrap = True
        spacer_row = ft.Row([ft.Text("عنوان طويل جدا " * 4), ft.Container(expand=True), ft.FilledButton("زر")])
        return wide, top, spacer_row

    # كمبيوتر: ما يتغيّرش حاجة
    wide, top, sp = rows()
    for r in (wide, top, sp):
        r.before_update()
    assert not wide.wrap and wide.controls[2].width == 500 and sp.controls[1].visible is not False
    # موبايل
    pg = SimpleNamespace(_erp_compact=True, width=390.0)
    tok = _context_page.set(pg)
    try:
        wide, top, sp = rows()
        for r in (wide, top, sp):
            r.before_update()
    finally:
        _context_page.reset(tok)
    assert wide.wrap and max(c.width for c in wide.controls) <= 390 - 32
    assert not top.wrap                       # الشريط العلوي فاضل سطر واحد
    assert sp.wrap and sp.controls[1].visible is False
    assert pg.width == 390.0                  # عرض الصفحة نفسها ما يتلمسش
