import pytest
from erp_app import loyalty


def sale(S, shop, cid, spec=None, qty=1):
    return S.create_pos_sale(customer_id=cid, items=[{"product_id": shop["burger"], "quantity": qty, "unit_price": 100}],
                             payment_method_id=1, terminal_id=shop["term"], discount_spec=spec)


@pytest.fixture(scope="module")
def member(S, shop):
    cid = S.create_customer(name="عضو", loyalty_enabled=True)
    loyalty.save_config(enabled=True, earn_per_currency=1, redeem_value=0.5, min_redeem=20, max_redeem_pct=50)
    return cid


def test_earn_on_member_only(S, shop, member):
    r = sale(S, shop, member)
    assert r["loyalty"]["earned"] == 115 and loyalty.balance(member) == 115
    assert sale(S, shop, shop["cust"])["loyalty"]["earned"] == 0


def test_redeem_rules(S, shop, member):
    with pytest.raises(ValueError, match="رصيد"):
        loyalty.redeem_amount(member, 5000, 115)
    with pytest.raises(ValueError, match="أقل"):
        loyalty.redeem_amount(member, 10, 115)
    with pytest.raises(ValueError, match="عضو"):
        loyalty.redeem_amount(shop["cust"], 50, 115)
    assert loyalty.redeem_amount(member, 100, 115) == 50.0


def test_redeem_reduces_total_and_earns_on_net(S, shop, member):
    before = loyalty.balance(member)
    r = sale(S, shop, member, {"points": 100, "customer_id": member})
    assert r["discount"] == 50.0
    assert r["loyalty"]["redeemed"] == 100 and r["loyalty"]["earned"] == 65
    assert loyalty.balance(member) == before - 100 + 65


def test_full_return_reverses_points(S, shop, member):
    loyalty.adjust(member, 300, "رصيد للاختبار")
    before = loyalty.balance(member)
    r = sale(S, shop, member, {"points": 100, "customer_id": member})
    after_sale = loyalty.balance(member)
    d = S.get_invoice_for_return(r["invoice_id"])
    S.create_sales_return(r["invoice_id"], [{"invoice_item_id": d["items"][0]["id"], "quantity": d["items"][0]["remaining_qty"]}], "اختبار", refund_method_id=1, is_full=True)
    assert loyalty.balance(member) == before          # اتعكست المكتسبة ورجعت المستبدلة
    assert after_sale == before - 100 + 65


def test_ledger_matches_balance(S, shop, member):
    assert sum(t["points"] for t in loyalty.list_txns(member)) == loyalty.balance(member)


def test_adjust_requires_reason_and_funds(S, shop, member):
    with pytest.raises(ValueError):
        loyalty.adjust(member, 10, "")
    with pytest.raises(ValueError):
        loyalty.adjust(member, -10**6, "x")
