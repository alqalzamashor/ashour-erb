import pytest


@pytest.fixture(scope="module")
def rest(S, shop):
    return dict(shop, t1=S.create_restaurant_table("1"), t2=S.create_restaurant_table("2"), t3=S.create_restaurant_table("3"))


def new_order(S, rest, table, items):
    o = S.open_restaurant_order(table, 2, terminal_id=rest["term"])
    for pid, q in items:
        S.add_restaurant_order_item(o, pid, q)
    S.send_order_to_kitchen(o)
    return o


def test_one_open_order_per_table(S, rest):
    o = new_order(S, rest, rest["t1"], [(rest["burger"], 1)])
    with pytest.raises(ValueError):
        S.open_restaurant_order(rest["t1"], 1, terminal_id=rest["term"])
    S.checkout_restaurant_order(o, customer_id=rest["cust"], payment_method_id=1)


def test_split_bill(S, rest):
    o = new_order(S, rest, rest["t1"], [(rest["burger"], 2), (rest["cola"], 3)])
    items = {i["name"]: i["id"] for i in S.get_restaurant_order(o)["items"]}
    r = S.split_checkout_restaurant_order(o, {items["برجر"]: 1, items["بيبسي"]: 3}, customer_id=rest["cust"], payment_method_id=1)
    assert r["invoice_id"]
    rem = S.get_restaurant_order(o)
    assert rem["state"] == "open" and [(i["name"], i["quantity"]) for i in rem["items"]] == [("برجر", 1)]
    with pytest.raises(ValueError):
        S.split_checkout_restaurant_order(o, {items["برجر"]: 5}, customer_id=rest["cust"], payment_method_id=1)
    S.checkout_restaurant_order(o, customer_id=rest["cust"], payment_method_id=1)


def test_transfer_and_merge(S, rest):
    o1 = new_order(S, rest, rest["t1"], [(rest["burger"], 1)])
    S.transfer_restaurant_order(o1, rest["t2"])
    o2 = new_order(S, rest, rest["t3"], [(rest["cola"], 2)])
    with pytest.raises(ValueError):
        S.transfer_restaurant_order(o2, rest["t2"])          # الطاولة مشغولة
    S.merge_restaurant_orders(o1, o2)
    assert S.get_restaurant_order(o1)["state"] == "merged"
    merged = S.get_restaurant_order(o2)
    assert sorted(i["name"] for i in merged["items"]) == ["برجر", "بيبسي"]
    S.checkout_restaurant_order(o2, customer_id=rest["cust"], payment_method_id=1)


def test_checkout_requires_kitchen_send(S, rest):
    o = S.open_restaurant_order(rest["t1"], 1, terminal_id=rest["term"])
    S.add_restaurant_order_item(o, rest["burger"], 1)
    with pytest.raises(ValueError, match="مطبخ"):
        S.checkout_restaurant_order(o, customer_id=rest["cust"], payment_method_id=1)
    S.send_order_to_kitchen(o)
    S.checkout_restaurant_order(o, customer_id=rest["cust"], payment_method_id=1)
