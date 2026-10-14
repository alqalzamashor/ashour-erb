import datetime

import pytest

from erp_app import approvals, credit
from erp_app.db import ApprovalRequest, AuditLog, get_session


@pytest.fixture(scope="module")
def users(S, shop):
    S.create_user("maker", "pw12345", "منفّذ", "viewer", permissions={
        "purchase_invoices": ["view", "create", "post"], "receipts_payments": ["view", "create"], "inventory_adjustments": ["view", "create"],
        "sales_invoices": ["view", "create", "post"], "approvals": ["view"]})
    S.create_user("boss", "pw12345", "مدير", "accountant")
    return S


def login(S, name):
    S.set_current_user(S.authenticate_user(name, "pw12345"))


@pytest.fixture
def as_admin(S):
    admin = S.current_user()
    yield
    S.set_current_user(admin)
    approvals.save_config(kinds={k: {"enabled": False, "threshold": 1000} for k in ("purchase_invoice", "payment_voucher", "inventory_adjustment")})


def test_purchase_flow_consumed_once(users, shop, as_admin):
    S = users
    approvals.save_config(kinds={"purchase_invoice": {"enabled": True, "threshold": 1000}})
    items = [{"product_id": shop["item"], "quantity": 100, "unit_price": 12}]          # 1380
    small = [{"product_id": shop["item"], "quantity": 10, "unit_price": 12}]
    login(S, "maker")
    S.create_purchase_invoice(shop["supplier"], small, location_id=shop["loc"])        # تحت الحد: عادي
    with pytest.raises(approvals.ApprovalRequired) as ei:
        S.create_purchase_invoice(shop["supplier"], items, location_id=shop["loc"])
    rid = approvals.request(**ei.value.approval)
    assert approvals.request(**ei.value.approval) == rid
    with pytest.raises(approvals.ApprovalRequired):
        S.create_purchase_invoice(shop["supplier"], items, location_id=shop["loc"])    # لسه معلّق
    with pytest.raises(PermissionError):
        approvals.approve(rid)                                                          # مفيش صلاحية اعتماد
    login(S, "boss")
    approvals.approve(rid, "تمام")
    login(S, "maker")
    assert S.create_purchase_invoice(shop["supplier"], items, location_id=shop["loc"])
    with pytest.raises(approvals.ApprovalRequired):                                     # استُهلكت
        S.create_purchase_invoice(shop["supplier"], items, location_id=shop["loc"])
    # موافقة على مبلغ مختلف مش بتنفع
    other = [{"product_id": shop["item"], "quantity": 120, "unit_price": 12}]
    with pytest.raises(approvals.ApprovalRequired):
        S.create_purchase_invoice(shop["supplier"], other, location_id=shop["loc"])


def test_reject_expiry_cancel_and_self_approval(users, shop, as_admin):
    S = users
    approvals.save_config(kinds={"payment_voucher": {"enabled": True, "threshold": 100}})
    cash = [a.id for a in S.list_accounts() if a.code == "121001"][0]
    login(S, "maker")
    with pytest.raises(approvals.ApprovalRequired) as ei:
        S.create_payment(shop["supplier"], 500, cash)
    rid = approvals.request(**ei.value.approval)
    login(S, "boss")
    with pytest.raises(ValueError, match="سبب"):
        approvals.reject(rid, "")
    approvals.reject(rid, "مش مبرر")
    login(S, "maker")
    with pytest.raises(approvals.ApprovalRequired):
        S.create_payment(shop["supplier"], 500, cash)
    rid2 = approvals.request(**ei.value.approval)
    assert rid2 != rid
    login(S, "boss"); approvals.approve(rid2)
    with get_session() as s:                                                           # انتهت الصلاحية
        s.get(ApprovalRequest, rid2).decided_at = datetime.datetime.now() - datetime.timedelta(hours=100); s.commit()
    login(S, "maker")
    with pytest.raises(approvals.ApprovalRequired):
        S.create_payment(shop["supplier"], 500, cash)
    approvals.cancel(rid2)
    # المعتمِد يعدّي مباشرة وبيتسجّل
    login(S, "boss")
    assert S.create_payment(shop["supplier"], 500, cash)
    with get_session() as s:
        assert s.query(AuditLog).filter(AuditLog.action == "approval_bypass").count() >= 1


def test_inventory_adjustment_and_credit_limit_via_approval(users, shop, as_admin):
    S = users
    approvals.save_config(kinds={"inventory_adjustment": {"enabled": True, "threshold": 50}})
    bal = S.get_balances_map()[shop["item"]]
    login(S, "maker")
    with pytest.raises(approvals.ApprovalRequired) as ei:
        S.create_inventory_adjustment(shop["loc"], {shop["item"]: bal - 20})          # عجز 20 × 12 = 240
    rid = approvals.request(**ei.value.approval)
    login(S, "boss"); approvals.approve(rid)
    login(S, "maker")
    assert S.create_inventory_adjustment(shop["loc"], {shop["item"]: bal - 20})
    # الائتمان: نفس الدورة
    S.set_current_user(S.authenticate_user("admin", "admin"))
    cid = S.create_customer(name="عميل حد صغير", credit_limit=100)
    login(S, "maker")
    sale = lambda: S.create_sales_invoice(cid, [{"product_id": shop["item"], "quantity": 10, "unit_price": 30}], location_id=shop["loc"])   # 345 > 100
    with pytest.raises(credit.CreditLimitError) as ei:
        sale()
    rid = approvals.request(**ei.value.approval)
    login(S, "boss"); approvals.approve(rid, "عميل مهم")
    login(S, "maker")
    assert sale()
    with pytest.raises(credit.CreditLimitError):
        sale()
    assert [r.status for r in approvals.list_requests("mine")][0] in ("pending", "consumed", "cancelled", "approved", "rejected")
