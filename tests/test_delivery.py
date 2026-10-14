import json
import urllib.error
import urllib.request

import pytest

from erp_app import delivery, delivery_server


def _post(base, path, body, key=None, hdr="X-Api-Key"):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode("utf-8"), method="POST", headers={"Content-Type": "application/json"})
    if key:
        req.add_header(hdr, key)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture(scope="module")
def hook(S, shop):
    sec = delivery.add_source("hunger", "هنقر")
    delivery.save_config(enabled=True, port=18600)
    h = delivery_server.start("127.0.0.1", 18600)
    assert h
    yield f"http://127.0.0.1:{h[1]}", sec
    delivery_server.stop()


ORDER = {"order_id": "H-1001", "customer": {"name": "سعد", "phone": "0501234567"}, "address": "حي النخيل", "total": 230, "payment": "online",
         "items": [{"sku": "P1", "name": "برجر", "quantity": 2, "price": 100}, {"name": "منتج مجهول", "quantity": 1, "price": 10}]}


def test_webhook_auth_and_validation(hook):
    base, sec = hook
    assert _post(base, "/hook/hunger", ORDER)[0] == 401
    assert _post(base, "/hook/hunger", ORDER, key="wrong")[0] == 401
    assert _post(base, "/hook/nope", ORDER, key=sec)[0] == 404
    assert _post(base, "/hook/hunger", {"order_id": "x", "items": []}, key=sec)[0] == 400
    assert _post(base, "/hook/hunger", {"items": [{"name": "a"}]}, key=sec)[0] == 400
    assert _post(base, "/hook/hunger", ORDER, key=sec, hdr="Authorization") [0] == 401   # بدون Bearer
    assert urllib.request.urlopen(base + "/health").status == 200


def test_ingest_dedupe_accept_and_flow(S, shop, hook):
    base, sec = hook
    code, r = _post(base, "/hook/hunger", ORDER, key=sec)
    assert code == 200 and not r["duplicate"]
    code, r2 = _post(base, "/hook/hunger", ORDER, key=sec)
    assert code == 200 and r2["duplicate"] and r2["order_id"] == r["order_id"]
    assert delivery.count_new() == 1
    assert S.kitchen_board()["delivery_new"] == 1
    oid = r["order_id"]
    # صنف مجهول = مينفعش القبول
    with pytest.raises(ValueError, match="غير مربوطة"):
        delivery.accept(oid, shop["term"])
    res = delivery.accept(oid, shop["term"], {1: shop["cola"]})
    assert res["number"].startswith("RT-") and res["send_result"]["items"]
    assert abs(res["price_diff"] - (230 - (2 * 115 + 5.75))) < 0.01
    o = delivery.list_orders()[0]
    assert o["status"] == "accepted" and o["restaurant_order_id"] == res["restaurant_order_id"]
    # ظهر في تذاكر المطبخ كدليفري، والخريطة اتحفظت للمرة الجاية
    assert any(t["order_type"] == "delivery" for t in S.kitchen_board()["tickets"])
    order = S.get_restaurant_order(res["restaurant_order_id"])
    assert "مدفوع أونلاين" in order["notes"] and order["customer_phone"] == "0501234567"
    assert delivery.match_items(oid)[1]["product_id"] == shop["cola"]
    with pytest.raises(ValueError):
        delivery.accept(oid, shop["term"])
    delivery.set_status(oid, "ready"); delivery.set_status(oid, "dispatched"); delivery.set_status(oid, "delivered")
    with pytest.raises(ValueError):
        delivery.set_status(oid, "ready")


def test_reject_manual_mapping_and_secret_masking(S, shop, hook):
    oid = delivery.create_manual("منى", "0507654321", "شارع 1", [{"sku": "P2", "name": "بيبسي", "quantity": 3}], "بدون ثلج")
    delivery.reject(oid, "المطعم مغلق")
    assert delivery.list_orders(status="rejected")[0]["reject_reason"] == "المطعم مغلق"
    # خريطة حقول مخصصة
    p = {"id": 77, "cust": {"n": "ع", "tel": "050"}, "lines": [{"code": "P1", "q": 1, "amt": 100}], "addr": "x"}
    mp = {"external_id": "id", "customer_name": "cust.n", "phone": "cust.tel", "items": "lines", "item_sku": "code", "item_qty": "q", "item_price": "amt", "address": "addr"}
    d = delivery.parse_payload(p, mp)
    assert d["external_id"] == "77" and d["items"][0]["sku"] == "P1" and d["phone"] == "050"
    from erp_app.db import AuditLog, get_session
    sec = delivery.rotate_secret("hunger")
    with get_session() as s:
        rows = [r for r in s.query(AuditLog).filter(AuditLog.action == "config").all() if "secret" in (r.changes or "")]
    assert rows and all(sec not in r.changes for r in rows)
    with pytest.raises(ValueError):
        delivery.add_source("Bad Name!")
