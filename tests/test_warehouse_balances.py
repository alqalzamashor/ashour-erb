"""تقرير أرصدة المستودعات: أول الفترة + الوارد - المنصرف = آخر الفترة، وتصنيف الحركات من المرجع."""
import datetime

import pytest

from erp_app import warehouse_balances as W

D = datetime.datetime
_N = {"n": 0}


def _setup(S):
    _N["n"] += 1
    n = _N["n"]
    loc_a = S.create_location(f"مستودع أ{n}")
    loc_b = S.create_location(f"مستودع ب{n}")
    pid = S.create_product(f"WB{n}", f"صنف تقرير {n}", cost_price=10)

    def mv(loc, d, qty, ref, date):
        S.create_stock_move(pid, loc, d, qty, unit_cost=10, reference=ref, _internal=True, move_date=date, update_cost=False)
    return loc_a, loc_b, pid, mv


def _row(rep, loc, pid):
    for g in rep["groups"]:
        if g["location"].id == loc:
            for r in g["rows"]:
                if r["product"].id == pid:
                    return r
    return None


def test_classify():
    assert W.classify("PURCH:1", "in") == "purchases"
    assert W.classify("GRN:5", "in") == "purchases"
    assert W.classify("VOID:S1", "in") == "sales_return"
    assert W.classify("VOID:P1", "out") == "purchase_return"
    assert W.classify("TRF-2026", "out") == "transfer_out"
    assert W.classify("ADJ:3", "in") == "adj_in"
    assert W.classify("DMG:1", "out") == "damage"
    assert W.classify("MO:1", "in") == "other_in"
    assert W.classify("", "out") == "other_out"


def test_opening_in_out_closing(S):
    a, b, pid, mv = _setup(S)
    mv(a, "in", 100, "PURCH:X", D(2061, 8, 20))      # قبل الفترة -> رصيد أول
    mv(a, "out", 10, "SALES:X", D(2061, 8, 25))      # قبل الفترة
    mv(a, "in", 50, "PURCH:Y", D(2061, 9, 3))
    mv(a, "in", 3, "RET:Z", D(2061, 9, 5))
    mv(a, "in", 9, "ADJ:1", D(2061, 9, 6))
    mv(a, "out", 44, "SALES:Y", D(2061, 9, 7))
    mv(a, "out", 5, "VOID:P9", D(2061, 9, 8))
    mv(a, "out", 20, "TRF-1", D(2061, 9, 9))
    mv(a, "out", 2, "DMG:1", D(2061, 9, 10))
    mv(a, "out", 4, "ADJ:2", D(2061, 9, 11))
    mv(a, "in", 7, "MO:1", D(2061, 9, 30))           # آخر يوم في الفترة داخل
    mv(a, "in", 99, "PURCH:LATE", D(2061, 10, 1))     # بعد الفترة: مش محسوب
    rep = W.build_report("2061-09-01", "2061-09-30", location_id=a)
    r = _row(rep, a, pid)
    assert r["opening"] == 90
    assert (r["purchases"], r["sales_return"], r["adj_in"], r["other_in"]) == (50, 3, 9, 7)
    assert r["total_in"] == 69
    assert (r["sales"], r["purchase_return"], r["transfer_out"], r["damage"], r["adj_out"]) == (44, 5, 20, 2, 4)
    assert r["total_out"] == 75
    assert r["closing"] == 90 + 69 - 75
    assert any(k == "other_in" for k, _ in rep["in_cols"])
    assert all(k != "other_out" for k, _ in rep["out_cols"])      # مفيش "أخرى" منصرف -> العمود مخفي
    # الإجمالي بتاع المستودع
    g = rep["groups"][0]
    assert g["totals"]["closing"] == r["closing"]


def test_transfer_and_matches_stock_balance(S):
    a, b, pid, mv = _setup(S)
    mv(a, "in", 40, "PURCH:Q", D(2062, 1, 2))
    S.create_stock_transfer_batch([{"product_id": pid, "quantity": 15}], a, b, transfer_date=D(2062, 1, 10))
    rep = W.build_report("2062-01-01", "2062-01-31")
    ra, rb = _row(rep, a, pid), _row(rep, b, pid)
    assert ra["transfer_out"] == 15 and ra["closing"] == 25
    assert rb["transfer_in"] == 15 and rb["closing"] == 15 and rb["opening"] == 0
    bal = S.get_balances_map(by_location=True, as_of=D(2062, 1, 31, 23, 59, 59))
    assert bal[(pid, a)] == ra["closing"] and bal[(pid, b)] == rb["closing"]


def test_hide_zero_and_empty_period(S):
    a, b, pid, mv = _setup(S)
    mv(a, "in", 5, "PURCH:H", D(2063, 3, 1))
    mv(a, "out", 5, "SALES:H", D(2063, 3, 2))
    assert _row(W.build_report("2063-04-01", "2063-04-30", location_id=a), a, pid) is None      # صفر طول الفترة
    assert _row(W.build_report("2063-04-01", "2063-04-30", location_id=a, hide_zero=False), a, pid) is not None
    with pytest.raises(ValueError):
        W.build_report("2063-05-01", "2063-04-01")


def test_export_table_and_files(S, tmp_path):
    from erp_app.report_export import export_excel, export_pdf
    a, b, pid, mv = _setup(S)
    mv(a, "in", 12, "PURCH:E", D(2064, 6, 5))
    rep = W.build_report("2064-06-01", "2064-06-30", location_id=a)
    data = W.export_table(rep)
    assert data["table"][0][:4] == ["الكود", "الصنف", "الوحدة", "رصيد أول الفترة"]
    assert data["table"][-1][1].startswith("الإجمالي")
    for fn in (export_excel, export_pdf):
        path = fn(data, "warehouse_balances", str(tmp_path))
        assert path and path.endswith((".xlsx", ".pdf"))


def test_valuation(S, tmp_path):
    from erp_app.report_export import export_excel, export_pdf
    a, b, pid, mv = _setup(S)            # تكلفة الصنف 10
    mv(a, "in", 30, "PURCH:V1", D(2065, 2, 1))
    mv(b, "in", 12, "PURCH:V2", D(2065, 2, 2))
    mv(a, "out", 5, "SALES:V3", D(2065, 2, 20))
    mv(a, "in", 100, "PURCH:LATE", D(2065, 3, 5))      # بعد التاريخ: مش محسوب
    rep = W.build_valuation("2065-02-28")
    byname = {g["name"]: g for g in rep["groups"]}
    ga = next(g for g in rep["groups"] if g["rows"] and any(r["product"].id == pid for r in g["rows"]) and "أ" in g["name"])
    ra = next(r for r in ga["rows"] if r["product"].id == pid)
    assert ra["qty"] == 25 and ra["price"] == 10 and ra["value"] == 250
    rep2 = W.build_valuation("2065-02-28", combine=True)
    assert len(rep2["groups"]) == 1 and rep2["groups"][0]["name"].startswith("كل المستودعات")
    rc = next(r for r in rep2["groups"][0]["rows"] if r["product"].id == pid)
    assert rc["qty"] == 37 and rc["value"] == 370
    # نفس أرقام أرصدة المخزون
    bal = S.get_balances_map(as_of=D(2065, 2, 28, 23, 59, 59))
    assert bal[pid] == 37
    for show in (True, False):
        data = W.valuation_export_table(rep, show)
        assert len(data["table"][0]) == (6 if show else 4)
        for fn in (export_excel, export_pdf):
            assert fn(data, "stock_valuation", str(tmp_path))
