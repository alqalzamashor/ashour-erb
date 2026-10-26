from erp_app import data_integrity


def test_quick_summary_shape_and_stock_check(S):
    r = data_integrity.quick_summary()
    assert r is not None and set(r) == {"errors", "warnings", "items"}
    full = data_integrity.run({"stock_vs_gl"})
    assert full["checks"][0]["key"] == "stock_vs_gl"
