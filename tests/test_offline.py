import datetime
import os

import pytest
from sqlalchemy.exc import OperationalError

from erp_app import offline
from erp_app.db import SalesInvoice, get_session


@pytest.fixture(autouse=True)
def clean():
    offline._ensure()
    for d in (offline.QUEUE, offline.DONE):
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
    yield


@pytest.fixture
def snap(S, shop):
    term = S.get_pos_terminal(shop["term"])
    n = offline.save_snapshot(term)
    assert n >= 3
    return term


def _items(shop, qty=2):
    return [{"product_id": shop["burger"], "quantity": qty, "unit_price": 100, "tax_rate": 15}]


def test_is_db_error():
    assert offline.is_db_error(OperationalError("x", {}, Exception("conn")))
    assert not offline.is_db_error(ValueError("business"))


def test_snapshot_lookup(S, shop, snap):
    assert offline.find("P1")["product"].name == "برجر"
    assert offline.find("p1")["product"].sale_price == 100
    assert offline.find("nope") is None
    assert [p.sku for p in offline.search("بيبسي")] == ["P2"]
    # باركود موزون
    from tests.test_misc import _ean13
    S.create_product("123", "جبنة", sale_price=40, cost_price=10)
    offline.save_snapshot(snap)
    hit = offline.find(_ean13("200012300850"))
    assert hit["product"].name == "جبنة" and hit["qty"] == 0.85


def test_queue_requires_cash_and_fresh_snapshot(S, shop, snap):
    credit = [m.id for m in S.list_payment_methods() if m.is_credit]
    with pytest.raises(ValueError, match="النقدي"):
        offline.queue_sale(shop["cust"], _items(shop), credit[0] if credit else 9999, shop["term"])
    r = offline.queue_sale(shop["cust"], _items(shop), 1, shop["term"])
    assert r["total"] == 230.0 and r["number"].startswith("OFF-")
    assert offline.counts() == {"pending": 1, "failed": 0}
    r2 = offline.queue_sale(shop["cust"], _items(shop, 1), 1, shop["term"])
    assert r2["number"] != r["number"]
    # نسخة قديمة
    s = offline.load_snapshot(); s["at"] = (datetime.datetime.now() - datetime.timedelta(hours=60)).isoformat()
    import json
    json.dump(s, open(offline.SNAP, "w", encoding="utf-8"), ensure_ascii=False)
    with pytest.raises(ValueError, match="قديمة"):
        offline.queue_sale(shop["cust"], _items(shop), 1, shop["term"])


def test_sync_idempotent_and_original_time(S, shop, snap):
    r = offline.queue_sale(shop["cust"], _items(shop), 1, shop["term"])
    at = datetime.datetime.fromisoformat(r["at"])
    # السيرفر لسه واقع: المزامنة بتوقف وتسيب الملف
    real = S.create_pos_sale
    def down(*a, **k):
        raise OperationalError("x", {}, Exception("server closed"))
    S.create_pos_sale = down
    try:
        res = offline.sync(S)
    finally:
        S.create_pos_sale = real
    assert res["offline"] and res["synced"] == 0 and offline.counts()["pending"] == 1
    # رجع الاتصال
    res = offline.sync(S)
    assert res["synced"] == 1 and offline.counts() == {"pending": 0, "failed": 0}
    with get_session() as s:
        inv = s.query(SalesInvoice).filter(SalesInvoice.client_uuid == r["uuid"]).one()
        assert inv.total == 230.0 and abs((inv.date - at).total_seconds()) < 1 and inv.is_pos
    # نفس الـ uuid تاني (الرد ضاع) = نفس الفاتورة مش فاتورة جديدة
    again = S.create_pos_sale(shop["cust"], _items(shop), payment_method_id=1, terminal_id=shop["term"], client_uuid=r["uuid"])
    assert again["duplicate"] and again["invoice_id"] == inv.id
    with get_session() as s:
        assert s.query(SalesInvoice).filter(SalesInvoice.client_uuid == r["uuid"]).count() == 1


def test_business_failure_marked_and_retry_discard(S, shop, snap):
    big = [{"product_id": shop["item"], "quantity": 99999, "unit_price": 30, "tax_rate": 15}]
    offline.queue_sale(shop["cust"], big, 1, shop["term"])
    res = offline.sync(S)
    assert res["failed"] == 1 and not res["offline"]
    f = offline.failed()[0]
    assert f["error"] and offline.counts() == {"pending": 0, "failed": 1}
    assert offline.retry(f["uuid"]) and offline.counts()["pending"] == 1
    offline.sync(S)
    with pytest.raises(ValueError):
        offline.discard(offline.failed()[0]["uuid"], "")
    assert offline.discard(offline.failed()[0]["uuid"], "اتسجّل يدويًا") and offline.counts() == {"pending": 0, "failed": 0}


def _walk(c):
    yield c
    for attr in ("controls", "content"):
        v = getattr(c, attr, None)
        if v is None:
            continue
        for x in (v if isinstance(v, list) else [v]):
            if hasattr(x, "__dict__") or hasattr(x, "controls"):
                yield from _walk(x)


def test_pos_screen_sells_offline_and_syncs(S, shop, snap, monkeypatch):
    """الشاشة نفسها: بنيها والاتصال شغال، نقطع القاعدة، نمسح باركود ونبيع → بيتخزّن؛ بعد رجوع الاتصال بيتزامن."""
    from unittest.mock import MagicMock
    from erp_app.views.pos import build_pos
    pg = MagicMock(); pg.overlay = []
    root = build_pos(pg)
    nodes = list(_walk(root))
    search = next(n for n in nodes if getattr(n, "label", "") == "بحث عن صنف (الاسم أو الكود)")
    pay = next(n for n in nodes if getattr(n, "label", "") == "طريقة الدفع")
    checkout = next(n for n in nodes if getattr(n, "content", None) == "إتمام البيع" or getattr(n, "text", None) == "إتمام البيع")
    offline.save_snapshot(snap)

    def down(*a, **k):
        raise OperationalError("x", {}, Exception("could not connect to server"))
    real = {n: getattr(S, n) for n in ("create_pos_sale", "scan_lookup", "list_products", "get_customer_product_price", "get_open_pos_session")}
    for n in real:
        monkeypatch.setattr(S, n, down)
    search.value = "P1"; search.on_submit(None)       # مسح من النسخة المحلية
    search.value = "P1"; search.on_submit(None)
    pay.value = "1"
    checkout.on_click(None)
    assert offline.counts()["pending"] == 1
    rec = offline.pending()[0]
    assert rec["items"][0]["quantity"] == 2 and rec["total"] == 230.0
    for n, f in real.items():
        monkeypatch.setattr(S, n, f)
    assert offline.sync(S)["synced"] == 1
