"""اختبار تقارير عاشور: قائمة دخل الفروع، مبيعات الكاشير، المشتريات، العملاء/الموردين، الإكسل، وشاشات الواجهة."""
import datetime
import os

import pytest

from erp_app import ashour_reports as ar


def _id(x):
    return x if isinstance(x, int) else x.id


@pytest.fixture(scope="module")
def data(S, shop):
    b1 = _id(S.create_branch("A1", "فرع أ"))
    b2 = _id(S.create_branch("A2", "فرع ب"))
    def acc(code, name, t):
        a = S.get_account_by_code(code)
        if a:
            return a if isinstance(a, int) else a.id
        a = S.create_account(code, name, t)
        return a if isinstance(a, int) else a.id
    sales, cogs = acc("410100", "مبيعات اختبار", "income"), acc("510100", "تكلفة اختبار", "expense")
    rent, other = acc("520037", "ايجار الموقع", "expense"), acc("520099", "مصروف آخر", "expense")
    cash = acc("110100", "نقدية اختبار", "asset")
    today = datetime.datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)
    last_year = today.replace(year=today.year - 1) if not (today.month == 2 and today.day == 29) else today.replace(year=today.year - 1, day=28)

    def je(branch, rev, cost, rnt, when):
        lines = [{"account_id": cash, "debit": rev, "branch_id": branch},
                 {"account_id": sales, "credit": rev, "branch_id": branch},
                 {"account_id": cogs, "debit": cost, "branch_id": branch},
                 {"account_id": cash, "credit": cost, "branch_id": branch}]
        if rnt:
            lines += [{"account_id": rent, "debit": rnt, "branch_id": branch}, {"account_id": cash, "credit": rnt, "branch_id": branch}]
        S.create_journal_entry(lines, entry_date=when, branch_id=branch)
    je(b1, 1000, 400, 100, today)          # فرع أ: ربح 500
    je(b2, 500, 400, 300, today)           # فرع ب: خسارة 200
    je(b1, 800, 300, 100, last_year)       # السنة اللي فاتت
    S.create_journal_entry([{"account_id": other, "debit": 50}, {"account_id": cash, "credit": 50}], entry_date=today)  # من غير فرع صريح (يتحط على الفرع الافتراضي)
    S.create_budget_line("ميزانية", today.replace(day=1), today + datetime.timedelta(days=1), sales, 2000, branch_id=b1)
    return {"b1": b1, "b2": b2, "today": today.date()}


def test_formula_and_prefixes():
    assert ar.parse_formula("a - b + c") == [(1, "a"), (-1, "b"), (1, "c")]
    with pytest.raises(ValueError):
        ar.parse_formula("a b")
    assert ar.split_prefixes("42، 43,44") == ["42", "43", "44"]
    ar.validate_lines(ar.DEFAULT_LINES)
    bad = [dict(l) for l in ar.DEFAULT_LINES]
    bad[-1] = dict(bad[-1], formula="income - nope")
    with pytest.raises(ValueError):
        ar.validate_lines(bad)


def test_pnl_by_branch(data):
    d = data["today"]
    res = ar.pnl_compute(d, d)
    a, b = data["b1"], data["b2"]
    assert res["cur"][a]["income"] == 1000 and res["cur"][a]["net"] == 500
    assert res["cur"][b]["net"] == -200                      # 500 - 400 - 300 (الأطول بادئة: الإيجار مش opex)
    assert res["cur"][a]["rent"] == 100 and res["cur"][a]["opex"] == 0
    assert res["cur"][ar.TOTAL]["income"] == 1500
    assert res["prev"][a]["income"] == 800 and res["prev"][a]["net"] == 400
    assert res["has_budget"] and res["budget"][a]["sales"] > 0
    t = ar.pnl_table(res, "var_prev")
    assert t["rows"] and t["columns"][0] == "البند"
    assert any("فروع خاسرة" == n["title"] for n in res["notes"])
    for v in ar.PNL_VIEWS:
        assert ar.pnl_table(res, v)["rows"]
    assert ar.pnl_ratios_table(res)["rows"]


def test_pnl_allocation(data):
    cfg = ar.load_config()
    a = data["b1"]
    cfg["head_office_branch_id"] = a
    ar.save_config(cfg)
    d = data["today"]
    res = ar.pnl_compute(d, d, allocate=True)
    assert res["allocated"] and res["cur"][a]["rent"] == 0
    assert abs(res["cur"][ar.TOTAL]["rent"] - 400) < 0.01   # الإجمالي ما بيتغيرش بالتوزيع
    ar.reset_config()


def test_pos_and_purchases_and_party(S, shop, data):
    d = data["today"]
    S.create_pos_sale(shop["cust"], [{"product_id": shop["burger"], "quantity": 2, "unit_price": 100}], payment_method_id=1)
    sup = shop["supplier"]
    sid = sup if isinstance(sup, int) else sup.id
    S.create_purchase_invoice(sid, [{"product_id": shop["item"], "quantity": 10, "unit_price": 10}])
    S.create_purchase_invoice(sid, [{"product_id": shop["item"], "quantity": 10, "unit_price": 12}])
    for kind in ("branches", "daily", "hourly", "products", "payments"):
        rep = ar.pos_report(kind, d, d, d - datetime.timedelta(days=30), d - datetime.timedelta(days=1))
        assert rep["rows"], kind
    assert ar.pos_pivot(d, d, "day")["rows"]
    br = ar.pos_report("branches", d, d, d, d)
    assert br["rows"][-1]["cells"][1] >= 1
    pc = ar.purchases_report("price_changes", d, d, d, d)
    assert pc["rows"] and pc["rows"][0]["cells"][-1].startswith("+")
    assert ar.purchases_report("compare", d, d, d, d)["rows"]
    assert ar.purchases_report("vendors", d, d, d, d)["rows"]
    assert ar.purchases_report("ledger", d, d, d, d)["title"]
    assert ar.customers_report("balances", d, d)["rows"]
    assert ar.customers_report("top", d, d)["title"]


def test_excel_and_screens(S, data, tmp_path):
    d = data["today"]
    rep = ar.pnl_table(ar.pnl_compute(d, d), "cur")
    p = ar.export_xlsx(rep, str(tmp_path / "x.xlsx"), "شركة")
    import openpyxl
    ws = openpyxl.load_workbook(p).active
    assert ws.max_row > 8 and ws.sheet_view.rightToLeft


def test_ui_builds(S, data):
    import flet as ft
    from erp_app.views import ashour_reports as v

    class P:  # صفحة وهمية كفاية لبناء الشاشات
        overlay = []
        def update(self, *a, **k): pass
    for fn in (v.build_ashour_pnl, v.build_ashour_pos, v.build_ashour_purchases, v.build_ashour_customers, v.build_ashour_settings):
        assert isinstance(fn(P()), ft.Control)
    ctl = v.render_table(ar.pnl_table(ar.pnl_compute(data["today"], data["today"]), "cur"))
    assert isinstance(ctl, ft.Control)


def test_english_labels(data):
    """كل عناوين وأعمدة وبنود تقارير عاشور الثابتة لازم يبقى لها ترجمة إنجليزي (الأسماء المدخلة بالبيانات تفضل زي ما هي)."""
    import re
    from erp_app.i18n import tr
    ar_re = re.compile("[؀-ۿ]")
    d = data["today"]
    prev = d - datetime.timedelta(days=30)
    res = ar.pnl_compute(d, d)
    reps = [ar.pnl_table(res, v) for v in ar.PNL_VIEWS] + [ar.pnl_ratios_table(res), ar.pnl_unmapped_table(res)]
    reps += [ar.pos_report(k, d, d, prev, d) for k in ("branches", "daily", "hourly", "products", "payments")]
    reps += [ar.purchases_report(k, d, d, prev, d) for k in ("compare", "vendors", "price_changes", "ledger")]
    reps += [ar.customers_report(k, d, d) for k in ("balances", "top")]
    missing = set()
    for r in reps:
        texts = [r["title"], r.get("subtitle") or ""] + list(r["columns"])
        texts += [n["title"] for n in r["notes"]] + [c for row in r["rows"][:0] for c in row["cells"]]
        for row in r["rows"]:
            if row["kind"] in ("section", "total", "grand"):
                texts += [c for c in row["cells"] if isinstance(c, str)]
        for t in texts:
            if t and ar_re.search(tr(t, "en")):
                missing.add(t)
    names = {"فرع أ", "فرع ب"}
    missing = {m for m in missing if not any(n in m for n in names)}
    assert not missing, missing
