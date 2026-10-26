"""سندات القبض/الصرف: حساب النقدية لازم يكون نقدي/بنك - مفروض في طبقة الخدمات مش الشاشة بس."""
import pytest

from erp_app.db import Account, get_session


def test_voucher_rejects_non_cash_account(S):
    with get_session() as s:
        box = Account(code="9501", name="صندوق اختبار فرض", account_type="asset", cash_flow_type="cash")
        plain = Account(code="9502", name="مصروف عادي", account_type="expense")
        s.add_all([box, plain]); s.commit(); box_id, plain_id = box.id, plain.id
    cid = S.create_customer("عميل فرض النقدية")
    cid = cid if isinstance(cid, int) else getattr(cid, "id", cid)
    with pytest.raises(ValueError, match="نقدية"):
        S.create_receipt(cid, 10, plain_id)
    with pytest.raises(ValueError, match="نقدية"):
        S.create_payment(cid, 10, plain_id, partner_type="customer")
    assert S.create_receipt(cid, 10, box_id)
