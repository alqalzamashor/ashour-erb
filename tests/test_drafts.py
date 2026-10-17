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
