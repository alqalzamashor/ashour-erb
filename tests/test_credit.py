import datetime

import pytest

from erp_app import credit
from erp_app.db import AuditLog, get_session


@pytest.fixture(scope="module")
def stocked(S, shop):
    S.create_purchase_invoice(shop["supplier"], [{"product_id": shop["item"], "quantity": 1000, "unit_price": 12}], location_id=shop["loc"])
    cid = S.create_customer(name="عميل آجل", phone="0500000001", credit_limit=500, credit_days=30)
    return cid


def sale(S, shop, cid, qty, days_ago=0):
    return S.create_sales_invoice(cid, [{"product_id": shop["item"], "quantity": qty, "unit_price": 30}], location_id=shop["loc"],
                                  invoice_date=datetime.datetime.now() - datetime.timedelta(days=days_ago))


def test_aging_buckets_fifo_and_receipt(S, shop, stocked):
    cid = stocked
    sale(S, shop, cid, 2, days_ago=130)     # 69 - استحقاق من 100 يوم => +90
    sale(S, shop, cid, 4, days_ago=45)      # 138 - متأخر 15 يوم
    sale(S, shop, cid, 1, days_ago=5)       # 34.5 - لسه مش مستحق
    r = credit.aging("customer", party_id=cid)["rows"][0]
    assert r["d90p"] == 69 and r["d30"] == 138 and r["current"] == 34.5 and r["balance"] == 241.5
    S.create_receipt(cid, 100, [a.id for a in S.list_accounts() if a.code == "121001"][0])
    r = credit.aging("customer", party_id=cid)["rows"][0]
    assert r["d90p"] == 0 and r["d30"] == 107 and r["balance"] == 141.5      # الأقدم اتسدد الأول
    cb = credit.customer_balance(cid)
    assert cb["balance"] == 141.5 and cb["overdue"] == 107 and cb["max_days_over"] >= 15


def test_credit_limit_blocks_and_override(S, shop, stocked):
    cid = stocked     # الرصيد 141.5 والحد 500
    S.create_user("seller", "pw12345", "بائع", "sales")
    admin = S.current_user()
    try:
        S.set_current_user(S.authenticate_user("seller", "pw12345"))
        with pytest.raises(credit.CreditLimitError, match="حد الائتمان"):
            sale(S, shop, cid, 12)                       # 414 + 141.5 > 500
        sale(S, shop, cid, 5)                            # 172.5 -> يعدّي (314)
        with pytest.raises(PermissionError):
            S.update_customer(cid, credit_limit=100000)  # البائع مينفعش يرفع الحد
    finally:
        S.set_current_user(admin)
    sale(S, shop, cid, 12)                               # المدير (credit:override) يعدّي
    with get_session() as s:
        ev = [e for e in s.query(AuditLog).filter(AuditLog.action == "credit_override").all()]
    assert ev
    assert credit.aging("customer", party_id=cid)["rows"][0]["over_limit"]


def test_hold_overdue_rule_cash_pos_and_credit_return(S, shop, stocked):
    c2 = S.create_customer(name="موقوف")
    S.update_customer(c2, credit_hold=True)
    S.create_user("seller2", "pw12345", "بائع2", "sales")
    admin = S.current_user()
    try:
        S.set_current_user(S.authenticate_user("seller2", "pw12345"))
        with pytest.raises(credit.CreditLimitError, match="موقوف"):
            sale(S, shop, c2, 1)
    finally:
        S.set_current_user(admin)
    # كاشير نقدي لعميل موقوف مش مشكلة
    r = S.create_pos_sale(c2, [{"product_id": shop["item"], "quantity": 1, "unit_price": 30}], payment_method_id=1, terminal_id=shop["term"])
    assert r["invoice_id"]
    # قاعدة المتأخرات
    c3 = S.create_customer(name="متأخر", credit_days=0)
    sale(S, shop, c3, 1, days_ago=40)
    credit.save_config(block_overdue_days=30)
    S.create_user("seller3", "pw12345", "بائع3", "sales")
    try:
        S.set_current_user(S.authenticate_user("seller3", "pw12345"))
        with pytest.raises(credit.CreditLimitError, match="متأخرة"):
            sale(S, shop, c3, 1)
    finally:
        S.set_current_user(admin); credit.save_config(block_overdue_days=0)
    # مرتجع على حساب العميل بيقلّل الرصيد
    inv_id = sale(S, shop, c3, 2)
    before = credit.customer_balance(c3)["balance"]
    inv = S.get_sales_invoice(inv_id)
    S.create_sales_return(inv_id, [{"invoice_item_id": inv.items[0].id, "quantity": 1}], "اختبار")
    assert credit.customer_balance(c3)["balance"] == pytest.approx(before - 34.5)


def test_supplier_aging_and_validation(S, shop, stocked):
    rows = credit.aging("supplier")["rows"]
    assert rows and rows[0]["balance"] > 0
    with pytest.raises(ValueError):
        S.update_customer(stocked, credit_limit=-5)
