"""حساب الطرف الافتراضي في سندات القبض/الصرف (قابل للتغيير)."""
from unittest.mock import MagicMock

import flet as ft
from flet.controls.context import _context_page


def _je_accounts(S, jid):
    from erp_app.db import JournalEntryLine, get_session
    with get_session() as s:
        return {l.account_id: (float(l.debit or 0), float(l.credit or 0)) for l in s.query(JournalEntryLine).filter(JournalEntryLine.entry_id == jid).all()}


def test_default_and_override(S):
    from erp_app.db import Payment, get_session
    accs = [a.id for a in S.list_accounts(postable_only=True)]
    cash, other = accs[0], accs[3]
    cid = S.create_customer("عميل حساب الطرف") if hasattr(S, "create_customer") else None
    cid = cid if isinstance(cid, int) else getattr(cid, "id", cid)
    default = S.default_counter_account("customer", cid, "receipt")
    assert default
    pid = S.create_receipt(cid, 100, cash)                      # بدون تحديد: الافتراضي
    with get_session() as s:
        jid = s.get(Payment, pid).journal_entry_id
    assert _je_accounts(S, jid)[default] == (0.0, 100.0)
    custom = next(a for a in accs if a not in (cash, default))
    pid = S.create_receipt(cid, 50, cash, counter_account_id=custom)      # حساب مغيَّر
    with get_session() as s:
        jid = s.get(Payment, pid).journal_entry_id
    ja = _je_accounts(S, jid)
    assert ja[custom] == (0.0, 50.0) and default not in ja
    pid = S.create_payment(cid, 30, cash, partner_type="customer", counter_account_id=custom)
    with get_session() as s:
        jid = s.get(Payment, pid).journal_entry_id
    assert _je_accounts(S, jid)[custom] == (30.0, 0.0)


def test_screen_field(S):
    from erp_app.views.receipts_payments import build_receipts_payments
    from tests.test_drafts import _walk
    pg = MagicMock(); pg.overlay = []; _context_page.set(pg)
    root = build_receipts_payments(pg)
    from tests.test_view_controls import _bad
    assert _bad(root) == []
    lbls = [getattr(c, "label", None) for c in _walk(root)]
    assert any(isinstance(l, str) and "حساب الطرف" in l for l in lbls)


def test_voucher_party_name_and_details(S):
    """PDF/معاينة السند لازم يطلّعوا اسم الطرف (عميل/مورد/موظف) - وفيه سطور القيد."""
    from erp_app.db import Payment, get_session
    accs = [a.id for a in S.list_accounts(postable_only=True)]
    cid = S.create_customer("عميل اسم السند")
    cid = cid if isinstance(cid, int) else getattr(cid, "id", cid)
    pid = S.create_receipt(cid, 75, accs[0], reference="R1", notes="ن")
    d = S.payment_voucher_details(pid)
    assert d["party"] == "عميل اسم السند" and d["amount"] == 75 and d["number"].startswith("RC-")
    assert len(d["lines"]) == 2 and round(sum(l["debit"] for l in d["lines"]), 2) == 75
    with get_session() as s:
        p = s.get(Payment, pid)
        assert S._payment_party_name(s, p) == "عميل اسم السند"
    assert S.generate_payment_pdf_file(pid).endswith(".pdf")


def test_screen_preview_and_save_buttons(S):
    from erp_app.views.receipts_payments import build_receipts_payments
    from tests.test_drafts import _walk
    pg = MagicMock(); pg.overlay = []; _context_page.set(pg)
    root = build_receipts_payments(pg)
    texts = [getattr(c, "content", None) or getattr(c, "text", None) for c in _walk(root) if isinstance(c, (ft.OutlinedButton, ft.FilledButton))]
    assert "حفظ ومعاينة" in texts and "حفظ وطباعة" in texts
    tips = [c.tooltip for c in _walk(root) if isinstance(c, ft.IconButton)]
    assert "معاينة" in tips
