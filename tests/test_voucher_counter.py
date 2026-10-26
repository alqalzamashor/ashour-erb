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
    cashes = [a.id for a in S.list_cash_accounts()]
    cash = cashes[0]
    other = next(a for a in accs if a not in cashes)
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
    pid = S.create_receipt(cid, 75, [a.id for a in S.list_cash_accounts()][0], reference="R1", notes="ن")
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


def test_update_payment_rebuilds_entry(S):
    import datetime
    import pytest
    from erp_app.db import JournalEntry, Payment, get_session
    accs = [a.id for a in S.list_accounts(postable_only=True)]
    _c = [a.id for a in S.list_cash_accounts()]
    cash, cash2, counter2 = _c[0], (_c[1] if len(_c) > 1 else _c[0]), next(a for a in accs if a not in _c)
    c1 = S.create_customer("عميل تعديل 1"); c1 = c1 if isinstance(c1, int) else c1.id
    c2 = S.create_customer("عميل تعديل 2"); c2 = c2 if isinstance(c2, int) else c2.id
    pid = S.create_receipt(c1, 100, cash)
    with get_session() as s:
        jid = s.get(Payment, pid).journal_entry_id
        number = s.get(Payment, pid).number
    S.update_payment(pid, c2, 250, cash2, reference="تعديل", notes="ن2", partner_type="customer", counter_account_id=counter2)
    d = S.payment_voucher_details(pid)
    assert d["party"] == "عميل تعديل 2" and d["amount"] == 250 and d["cash_account_id"] == cash2 and d["counter_account_id"] == counter2
    assert d["number"] == number and d["reference"] == "تعديل"
    la = _je_accounts(S, jid)
    assert la == {cash2: (250.0, 0.0), counter2: (0.0, 250.0)}
    with get_session() as s:
        assert s.get(JournalEntry, jid).posted is True and s.get(Payment, pid).journal_entry_id == jid
    # صرف
    py = S.create_payment(c1, 40, cash, partner_type="customer")
    S.update_payment(py, c1, 55, cash, partner_type="customer")
    with get_session() as s:
        jy = s.get(Payment, py).journal_entry_id
    assert sum(v[0] for v in _je_accounts(S, jy).values()) == 55
    # ملغى ومبلغ غلط
    with pytest.raises(ValueError):
        S.update_payment(pid, c2, 0, cash)
    S.void_payment(py)
    with pytest.raises(ValueError):
        S.update_payment(py, c1, 10, cash, partner_type="customer")


def test_screen_edit_button(S):
    from erp_app.views.receipts_payments import build_receipts_payments
    from tests.test_drafts import _walk
    pg = MagicMock(); pg.overlay = []; _context_page.set(pg)
    root = build_receipts_payments(pg)
    eds = [c for c in _walk(root) if isinstance(c, ft.IconButton) and c.tooltip == "تعديل"]
    assert eds
    eds[0].on_click(None)
    dlgs = [o for o in pg.overlay if isinstance(o, ft.AlertDialog)]
    assert dlgs and "تعديل" in dlgs[-1].title.value
    from tests.test_view_controls import _bad
    assert _bad(dlgs[-1].content) == []
    save = [c for c in dlgs[-1].actions if isinstance(c, ft.FilledButton)]
    save[0].on_click(None)
    assert getattr(dlgs[-1], "open", False) is False


def test_counter_account_in_list_and_pdf(S):
    from erp_app.db import Payment, get_session
    accs = [a.id for a in S.list_accounts(postable_only=True)]
    cid = S.create_customer("عميل عمود الطرف"); cid = cid if isinstance(cid, int) else cid.id
    custom = accs[5]
    pid = S.create_receipt(cid, 20, [a.id for a in S.list_cash_accounts()][0], counter_account_id=custom)
    pays = S.list_payments()
    m = S.payment_counter_accounts(pays)
    acc = next(a for a in S.list_accounts(postable_only=True) if a.id == custom)
    assert m[pid] == f"{acc.code} - {acc.name}"
    pdf = S.generate_payment_pdf_file(pid)
    assert pdf.endswith(".pdf")


def test_voucher_form_draft_roundtrip(S):
    """النموذج بيحفظ مسودة تلقائيًا وبيرجعها لما الشاشة تتفتح تاني، وبتتمسح بعد الحفظ."""
    import flet as ft
    from unittest.mock import MagicMock
    from flet.controls.context import _context_page
    from erp_app import drafts
    from erp_app.views.receipts_payments import build_receipts_payments
    prev = S._get_user()
    page = MagicMock(); page.overlay = []
    tok = _context_page.set(page)
    S.set_current_user({"username": "voucher_draft_user", "role": "admin"})      # بعد سياق الصفحة: المستخدم بيتخزن للصفحة دي
    drafts.clear("voucher")
    try:
        build_receipts_payments(page)
        assert drafts.load("voucher") is None
        assert drafts.save("voucher", {"typ": "payment", "party_type": "supplier", "amount": "123", "ref": "R9", "notes": "n"})
        v = build_receipts_payments(page)
        txt = []
        st = [v]
        while st:
            x = st.pop(); txt.append(x)
            for a in ("controls", "content"):
                c = getattr(x, a, None)
                if isinstance(c, list): st += c
                elif c is not None and hasattr(c, "__dict__"): st.append(c)
        vals = [(getattr(x, "label", None), x.value) for x in txt if isinstance(x, ft.TextField)]
        assert ("المبلغ", "123") in vals and ("المرجع", "R9") in vals, vals
        assert any(isinstance(x, ft.Container) and x.visible and x.bgcolor is not None and "مسودة" in str(getattr(getattr(x.content, "controls", [None, None])[1], "value", "")) for x in txt)
    finally:
        _context_page.reset(tok); drafts.clear("voucher"); S.set_current_user(prev)
