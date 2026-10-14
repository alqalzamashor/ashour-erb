import pytest
from erp_app import promotions
from erp_app.db import SalesInvoice, get_session


def sale(S, shop, qty=1, terminal=None, **kw):
    return S.create_pos_sale(customer_id=shop["cust"], items=[{"product_id": shop["burger"], "quantity": qty, "unit_price": 100}],
                             payment_method_id=1, terminal_id=terminal or shop["term"], **kw)


def test_plain_sale_vat(S, shop):
    r = sale(S, shop)
    with get_session() as s:
        inv = s.get(SalesInvoice, r["invoice_id"])
        assert round(inv.total, 2) == 115.0 and round(inv.tax_total, 2) == 15.0


def test_manual_discount_keeps_vat_correct(S, shop):
    r = sale(S, shop, discount_spec={"manual_kind": "percent", "manual_value": 5, "reason": "ضيف"})
    with get_session() as s:
        inv = s.get(SalesInvoice, r["invoice_id"])
        assert round(inv.total, 2) == 109.25            # 115 - 5.75
        assert round(inv.tax_total, 2) == 14.25         # الضريبة اتحسبت على الصافي (95 × 15%)
        assert inv.promo_discount == 5.75
        assert round(inv.total - inv.tax_total, 2) == 95.0


def test_large_manual_discount_needs_manager_approval(S, shop):
    S.create_user("cash2", "pw12345", "كاشير", "sales")
    admin = S.current_user()
    t2 = S.create_pos_terminal("T2", "كاشير 2", default_customer_id=shop["cust"], payment_method_ids=[1], default_payment_method_id=1)
    try:
        S.set_current_user(S.authenticate_user("cash2", "pw12345"))
        S.open_pos_session(t2, 0)
        with pytest.raises(ValueError, match="اعتماد مدير"):
            sale(S, shop, terminal=t2, discount_spec={"manual_kind": "percent", "manual_value": 50, "reason": "ضيف"})
        with pytest.raises(ValueError, match="سبب"):
            sale(S, shop, terminal=t2, discount_spec={"manual_kind": "percent", "manual_value": 50, "reason": "", "approver": admin})
        r = sale(S, shop, terminal=t2, discount_spec={"manual_kind": "percent", "manual_value": 50, "reason": "كبار الشخصيات", "approver": admin})
        assert r["discount"] == 57.5
    finally:
        S.set_current_user(admin)
    with get_session() as s:
        assert s.get(SalesInvoice, r["invoice_id"]).promo_approved_by == "admin"


def test_coupon_rules(S, shop):
    promotions.save_coupon("SAVE10", "خصم 10", "percent", 10, 0, 0, None, None, 1, True)
    r = sale(S, shop, discount_spec={"coupon": "SAVE10"})
    assert round(r["discount"], 2) == 11.5
    with pytest.raises(ValueError):            # حد الاستخدام = 1
        sale(S, shop, discount_spec={"coupon": "SAVE10"})
    with pytest.raises(ValueError):
        sale(S, shop, discount_spec={"coupon": "NOPE"})


@pytest.mark.parametrize("amount", [1.0, 2.5, 7.77, 17.77])
def test_allocate_hits_target_total_exactly(amount):
    items = [{"quantity": 1, "unit_price": 33.33}, {"quantity": 2, "unit_price": 10.0}, {"quantity": 3, "unit_price": 3.1}]
    before = promotions.items_total(items)
    out = promotions.allocate(items, amount)
    assert promotions.items_total(out) == round(before - amount, 2)


def test_allocate_fuzz_exact_total():
    import random
    r = random.Random(3)
    for _ in range(1500):
        items = [{"quantity": r.randint(1, 5), "unit_price": round(r.uniform(0.5, 60), 2), "tax_rate": 15} for _ in range(r.randint(1, 4))]
        tot = promotions.items_total(items)
        amt = round(r.uniform(0.1, tot * 0.9), 2)
        assert promotions.items_total(promotions.allocate(items, amt)) == round(tot - amt, 2)
