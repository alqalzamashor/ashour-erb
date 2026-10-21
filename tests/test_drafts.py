"""المسودات التلقائية: القيد والفاتورة بيتحفظوا أثناء الكتابة ويرجعوا بعد قطع الاتصال."""
import datetime
from unittest.mock import MagicMock

import flet as ft
import pytest
from flet.controls.context import _context_page

from erp_app import drafts


def _walk(root):
    stack, out = [root], []
    while stack:
        x = stack.pop()
        out.append(x)
        for a in ("controls", "content", "rows", "cells", "actions"):
            v = getattr(x, a, None)
            if isinstance(v, list):
                stack += v
            elif v is not None and hasattr(v, "__dict__"):
                stack.append(v)
    return out


def test_drafts_roundtrip_and_isolation(S):
    drafts.clear("t_kind")
    assert drafts.load("t_kind") is None
    assert drafts.save("t_kind", {"a": 1, "ar": "عربي"})
    d, at = drafts.load("t_kind")
    assert d == {"a": 1, "ar": "عربي"} and isinstance(at, datetime.datetime)
    assert drafts.save("t_kind", {"a": 1, "ar": "عربي"})            # نفس البيانات: مفيش كتابة تانية
    assert drafts.save("t_kind", {"a": 2})
    assert drafts.load("t_kind")[0] == {"a": 2}
    # مستخدم تاني مايشوفش مسودتي
    me = S._get_user()
    S.set_current_user({"username": "someone_else", "role": "admin"})
    try:
        assert drafts.load("t_kind") is None
    finally:
        S.set_current_user(me)
    assert drafts.load("t_kind") is not None
    drafts.clear("t_kind")
    assert drafts.load("t_kind") is None


def test_stale_draft_is_dropped(S):
    from erp_app.db import FormDraft, get_session
    drafts.save("t_old", {"x": 1})
    with get_session() as s:
        d = s.query(FormDraft).filter(FormDraft.kind == "t_old").first()
        d.updated_at = datetime.datetime.now() - datetime.timedelta(days=9); s.commit()
    assert drafts.load("t_old") is None


def _build(builder, *args):
    pg = MagicMock(); pg.overlay = []
    tok = _context_page.set(pg)
    return pg, tok, builder(pg, *args)


def test_journal_autosave_and_restore(S):
    from erp_app.views.journal_entries import build_journal_entries
    drafts.clear("journal_entry")
    accts = [a for a in S.list_accounts(postable_only=True)][:2]
    pg, tok, root = _build(build_journal_entries)
    try:
        fields = [c for c in _walk(root) if isinstance(c, ft.TextField)]
        ref = next(f for f in fields if f.label == "المرجع")
        ref.value = "مرجع مهم"
        ref.on_change(None)                                   # أي كتابة بتحفظ المسودة
        d, _ = drafts.load("journal_entry")
        assert d["ref"] == "مرجع مهم"
    finally:
        _context_page.reset(tok)
    # "الاتصال قطع": نبني الشاشة من جديد - لازم المرجع يرجع
    drafts.save("journal_entry", {"date": "2026-03-01", "ref": "R-9", "desc": "قيد معلّق", "branch": "", "center": "",
                                  "lines": [{"account": str(accts[0].id), "description": "", "partner": "", "debit": "150", "credit": "0", "branch": "", "center": ""},
                                            {"account": str(accts[1].id), "description": "", "partner": "", "debit": "0", "credit": "150", "branch": "", "center": ""}]})
    pg, tok, root = _build(build_journal_entries)
    try:
        vals = [c.value for c in _walk(root) if isinstance(c, ft.TextField)]
        assert "R-9" in vals and "قيد معلّق" in vals and "150" in vals
    finally:
        _context_page.reset(tok)
    drafts.clear("journal_entry")


def test_invoice_draft_restore(S):
    from erp_app.views._invoices import build_invoice_view
    drafts.clear("invoice_sales")
    pg, tok, root = _build(build_invoice_view, "sales")
    try:
        btn = next(c for c in _walk(root) if isinstance(c, ft.FilledButton) and getattr(c, "content", None) == "فاتورة مبيعات جديدة" or getattr(c, "text", None) == "فاتورة مبيعات جديدة")
        btn.on_click(None)
        dlg = pg.overlay[0] if isinstance(pg.overlay[0], ft.AlertDialog) else next(o for o in pg.overlay if isinstance(o, ft.AlertDialog))
        notes = next(c for c in _walk(dlg.content) if isinstance(c, ft.TextField) and c.label == "ملاحظات")
        notes.value = "ملاحظة قبل القطع"
        notes.on_change(None)
        assert drafts.load("invoice_sales")[0]["notes"] == "ملاحظة قبل القطع"
    finally:
        _context_page.reset(tok)
    pg, tok, root = _build(build_invoice_view, "sales")
    try:
        btn = next(c for c in _walk(root) if isinstance(c, ft.FilledButton) and (getattr(c, "content", None) == "فاتورة مبيعات جديدة" or getattr(c, "text", None) == "فاتورة مبيعات جديدة"))
        btn.on_click(None)
        dlg = next(o for o in pg.overlay if isinstance(o, ft.AlertDialog) and o.open)
        notes = next(c for c in _walk(dlg.content) if isinstance(c, ft.TextField) and c.label == "ملاحظات")
        assert notes.value == "ملاحظة قبل القطع"
    finally:
        _context_page.reset(tok)
    drafts.clear("invoice_sales")


def _gr_open(S, user):
    """بيبني شاشة سندات الاستلام على صفحة جديدة ويفتح نموذج السند الجديد."""
    from erp_app.views.goods_receipts import build_goods_receipts
    page = MagicMock(); page.overlay = []
    _context_page.set(page)
    S.set_current_user({"username": user, "role": "admin"})
    root = build_goods_receipts(page)
    nb = next(b for b in _walk(root) if isinstance(b, ft.FilledButton) and "جديد" in str(getattr(b, "content", "") or getattr(b, "text", "")))
    nb.on_click(None)
    dlg = next(o for o in page.overlay if isinstance(o, ft.AlertDialog) and o.open)
    return page, dlg


def test_goods_receipt_draft_roundtrip(S):
    """سند الاستلام بيحفظ مسودة بالأصناف وبيرجعها لما النموذج يتفتح تاني."""
    from erp_app import drafts
    page = MagicMock(); tok = _context_page.set(page)
    prev = S._get_user()
    drafts.clear("goods_receipt")
    try:
        _, dlg = _gr_open(S, "gr_draft_user")
        S.set_current_user({"username": "gr_draft_user", "role": "admin"})
        notes = next(x for x in _walk(dlg.content) if isinstance(x, ft.TextField) and x.label == "ملاحظات")
        notes.value = "مسودة اختبار"; notes.on_change(None)
        saved = drafts.load("goods_receipt")
        assert saved and saved[0]["notes"] == "مسودة اختبار"
        _, dlg2 = _gr_open(S, "gr_draft_user")
        n2 = next(x for x in _walk(dlg2.content) if isinstance(x, ft.TextField) and x.label == "ملاحظات")
        assert n2.value == "مسودة اختبار"
        banner = [x for x in _walk(dlg2.content) if isinstance(x, ft.Container) and x.visible and x.bgcolor is not None and "مسودة" in str(getattr(getattr(x.content, "controls", [None, None])[-2:][0], "value", ""))]
        assert banner
    finally:
        drafts.clear("goods_receipt"); _context_page.reset(tok); S.set_current_user(prev)


def test_receipt_grid_snapshot_load(S):
    """snapshot/load_items في جدول الاستلام بيرجّعوا نفس السطور (صنف/كمية/تكلفة)."""
    from erp_app.views._receipt_grid import ReceiptLinesGrid
    S.create_product("GRD1", "صنف مسودة استلام", cost_price=5)
    page = MagicMock(); page.overlay = []
    tok = _context_page.set(page)
    try:
        prods = [p for p in S.list_products() if p.can_be_purchased and p.product_type != "service"]
        g = ReceiptLinesGrid(page)
        g.set_products(prods)
        ln = g.lines[0]
        ln.product.value = str(prods[0].id); ln._on_product()
        ln.qty.value = "7"; ln.cost.value = "3.5"; ln._recalc()
        snap = g.snapshot()
        assert len(snap) == 1 and snap[0]["quantity"] == "7"
        g2 = ReceiptLinesGrid(page); g2.set_products(prods)
        g2.load_items(snap)
        got = g2.snapshot()
        assert [(x["product_id"], x["quantity"], x["unit_cost"]) for x in got] == [(snap[0]["product_id"], "7", "3.5")]
        assert len(g2.lines) == 2 and not g2.lines[-1].product.value
    finally:
        _context_page.reset(tok)


def test_asset_invoice_draft_roundtrip(S):
    """فاتورة مشتريات الأصول: المسودة بتتحفظ بالسطور وترجع لما النموذج يتفتح تاني."""
    from erp_app import drafts
    from erp_app.views.asset_purchase_invoices import build_asset_purchase_invoices
    prev = S._get_user()
    tok = _context_page.set(MagicMock())

    def open_form():
        page = MagicMock(); page.overlay = []
        _context_page.set(page)
        S.set_current_user({"username": "asset_draft_user", "role": "admin"})
        root = build_asset_purchase_invoices(page)
        nb = next(b for b in _walk(root) if isinstance(b, ft.FilledButton) and "جديدة" in str(getattr(b, "content", "") or getattr(b, "text", "")))
        nb.on_click(None)
        return next(o for o in page.overlay if isinstance(o, ft.AlertDialog) and o.open)
    drafts.clear("asset_purchase_invoice")
    try:
        dlg = open_form()
        notes = next(x for x in _walk(dlg.content) if isinstance(x, ft.TextField) and x.label == "ملاحظات")
        notes.value = "مسودة أصول"; notes.on_change(None)
        saved = drafts.load("asset_purchase_invoice")
        assert saved and saved[0]["notes"] == "مسودة أصول"
        dlg2 = open_form()
        n2 = next(x for x in _walk(dlg2.content) if isinstance(x, ft.TextField) and x.label == "ملاحظات")
        assert n2.value == "مسودة أصول"
    finally:
        drafts.clear("asset_purchase_invoice"); _context_page.reset(tok); S.set_current_user(prev)


def test_asset_grid_snapshot_load(S):
    from erp_app.views._asset_invoice_grid import AssetLinesGrid
    page = MagicMock(); page.overlay = []
    tok = _context_page.set(page)
    try:
        cats = S.list_asset_categories(active_only=True)
        g = AssetLinesGrid(page); g.set_categories(cats)
        ln = g.lines[0]
        ln.name.value = "طابعة"; ln.cost.value = "250"; ln.qty.value = "3"
        if cats:
            ln.category.value = str(cats[0].id)
        snap = g.snapshot()
        assert snap and snap[0]["name"] == "طابعة" and snap[0]["qty"] == "3"
        g2 = AssetLinesGrid(page); g2.set_categories(cats)
        g2.load_items(snap)
        assert g2.snapshot() == snap
        assert len(g2.lines) == 2 and g2.lines[-1].is_empty()
    finally:
        _context_page.reset(tok)
