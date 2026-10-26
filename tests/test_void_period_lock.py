"""إلغاء سند داخل شهر مقفل ممنوع (بيغيّر أرقام فترة اتقفلت)."""
import datetime

import pytest

from erp_app.db import MonthClose, get_session


def test_void_payment_in_closed_month_blocked(S):
    cash = S.list_cash_accounts()[0].id
    cid = S.create_customer("عميل قفل الإلغاء"); cid = cid if isinstance(cid, int) else cid.id
    pid = S.create_receipt(cid, 10, cash, date=datetime.datetime(2047, 5, 10))
    with get_session() as s:
        m = MonthClose(year=2047, month=5, closed_by="t"); s.add(m); s.commit(); mid = m.id
    try:
        with pytest.raises(ValueError, match="مقفل"):
            S.void_payment(pid)
    finally:
        with get_session() as s:
            s.delete(s.get(MonthClose, mid)); s.commit()
    S.void_payment(pid)          # بعد فتح الشهر الإلغاء بيشتغل
