import datetime

import pytest

from erp_app import data_integrity, fx
from erp_app.db import FxRevaluation, JournalEntryLine, PurchaseInvoice, SalesInvoice, get_session

TODAY = datetime.date.today()


@pytest.fixture(scope="module")
def cur(S, shop):
    fx.add_currency("USD", "دولار", "$"); fx.add_currency("EUR", "يورو", "€")
    fx.set_rate("USD", TODAY - datetime.timedelta(days=30), 3.75)
    fx.set_rate("USD", TODAY, 3.80)
    fx.set_rate("EUR", TODAY - datetime.timedelta(days=30), 4.00)
    S.create_purchase_invoice(shop["supplier"], [{"product_id": shop["item"], "quantity": 500, "unit_price": 1}], location_id=shop["loc"])
    return S


def cash(S):
    return [a.id for a in S.list_accounts() if a.code == "121001"][0]


def test_rates_and_validation(cur):
    assert fx.get_rate("SAR") == 1.0
    assert fx.get_rate("USD", TODAY - datetime.timedelta(days=10)) == 3.75        # آخر سعر قبل التاريخ
    assert fx.get_rate("USD") == 3.80
    with pytest.raises(ValueError, match="مفيش سعر"):
        fx.get_rate("EUR", TODAY - datetime.timedelta(days=60))
    with pytest.raises(ValueError):
        fx.set_rate("USD", TODAY, 0)
    with pytest.raises(ValueError):
        fx.add_currency("usd1")


def test_foreign_purchase_payment_realized_loss(cur, shop):
    S = cur
    day0 = datetime.datetime.now() - datetime.timedelta(days=30)
    inv = S.create_purchase_invoice(shop["supplier"], [{"product_id": shop["item"], "quantity": 100, "unit_price": 10}], location_id=shop["loc"],
                                    invoice_date=day0, currency="USD")                   # 1000$ + 15% = 1150$ @3.75
    with get_session() as s:
        i = s.get(PurchaseInvoice, inv)
        assert i.currency == "USD" and i.exchange_rate == 3.75 and i.foreign_total == 1150 and i.total == pytest.approx(4312.5)
    S.create_payment(shop["supplier"], 1150, cash(S), currency="USD")                    # اتدفع بسعر اليوم 3.80 = 4370
    rows = [r for r in fx.preview() if r["party_type"] == "supplier" and r["party_id"] == shop["supplier"]]
    assert len(rows) == 1 and rows[0]["foreign_balance"] == 0 and rows[0]["adjustment"] == pytest.approx(57.5)
    res = fx.post_revaluation()
    assert res["count"] >= 1 and res["loss"] >= 57.5
    assert not [r for r in fx.preview() if r["party_id"] == shop["supplier"] and r["party_type"] == "supplier"]    # تاني مرة مفيش فرق
    assert fx.post_revaluation()["count"] == 0
    with get_session() as s:
        assert s.query(FxRevaluation).count() >= 1
    assert data_integrity.run()["errors"] == 0


def test_foreign_sale_unrealized_gain(cur, shop):
    S = cur
    cid = S.create_customer(name="عميل أوروبي")
    inv = S.create_sales_invoice(cid, [{"product_id": shop["item"], "quantity": 10, "unit_price": 10}], location_id=shop["loc"],
                                 invoice_date=datetime.datetime.now() - datetime.timedelta(days=30), currency="EUR")       # 100€ + tax = 115€ @4.0 = 460
    with get_session() as s:
        i = s.get(SalesInvoice, inv)
        assert i.total == pytest.approx(460) and i.foreign_total == 115
    fx.set_rate("EUR", TODAY, 4.20)
    r = [x for x in fx.preview() if x["party_id"] == cid][0]
    assert r["target"] == pytest.approx(483) and r["adjustment"] == pytest.approx(23)
    res = fx.post_revaluation()
    assert res["gain"] >= 23
    # الدفع الجزئي: 15€ بسعر 4.5
    S.create_receipt(cid, 15, cash(S), currency="EUR", exchange_rate=4.5)                 # 67.5
    r = [x for x in fx.preview() if x["party_id"] == cid][0]
    assert r["foreign_balance"] == 100 and r["adjustment"] == pytest.approx(100 * 4.2 - (483 - 67.5))
    fx.post_revaluation()
    assert not [x for x in fx.preview() if x["party_id"] == cid]
    with get_session() as s:
        from sqlalchemy import func
        from erp_app.db import JournalEntry
        bad = [r for r in s.query(JournalEntry.number, func.sum(JournalEntryLine.debit), func.sum(JournalEntryLine.credit)).join(JournalEntryLine).group_by(JournalEntry.id).all()
               if abs((r[1] or 0) - (r[2] or 0)) > 0.01]
    assert bad == []


def test_base_currency_no_conversion_and_missing_rate(cur, shop):
    S = cur
    inv = S.create_purchase_invoice(shop["supplier"], [{"product_id": shop["item"], "quantity": 1, "unit_price": 10}], location_id=shop["loc"], currency="SAR")
    with get_session() as s:
        assert s.get(PurchaseInvoice, inv).currency is None
    with pytest.raises(ValueError, match="مفيش سعر"):
        S.create_purchase_invoice(shop["supplier"], [{"product_id": shop["item"], "quantity": 1, "unit_price": 10}], location_id=shop["loc"],
                                  invoice_date=datetime.datetime.now() - datetime.timedelta(days=90), currency="EUR")
