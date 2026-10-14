import os

from tests.test_misc import _ean13


def test_product_labels(S, shop, tmp_path, monkeypatch):
    monkeypatch.setattr(S, "downloads_dir", lambda: str(tmp_path))
    ean = _ean13("629123456789")
    pid = S.create_product("LB1", "عصير برتقال طبيعي كبير الحجم", sale_price=10, cost_price=4,
                           unit_lines=None)
    rows = {r["sku"]: r for r in S.product_label_rows()}
    assert rows["LB1"]["price"] == 11.5 and rows["LB1"]["barcode"] == "LB1" and not rows["LB1"]["has_barcode"]
    from erp_app.product_labels import _barcode_for
    assert _barcode_for(ean)[0] == "ean13"
    assert _barcode_for("123456789012")[0] == "code128"
    assert _barcode_for("عربي")[0] == "qr"
    for preset in ("thermal_50x30", "a4_24", "a4_65"):
        res = S.generate_product_labels_pdf([{"product_id": pid, "copies": 3}, {"product_id": shop["burger"]}], preset=preset)
        assert res["count"] == 4 and os.path.getsize(res["path"]) > 800
    import pytest
    with pytest.raises(ValueError):
        S.generate_product_labels_pdf([])
