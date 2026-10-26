"""دفتر الأستاذ في التقارير: رصيد أول الفترة، رصيد تراكمي، إجمالي كل حساب، وإجمالي عام."""
import datetime

from erp_app import report_export


def _two(S):
    a = {x.code: x for x in S.list_accounts(postable_only=True)}
    c = list(a)
    return a[c[0]], a[c[1]]


def _post(S, x, y, amt, d):
    S.create_journal_entry([{"account_id": x.id, "debit": amt}, {"account_id": y.id, "credit": amt}], description="t", entry_date=d)


def test_single_account_opening_running_balance_and_total(S):
    x, y = _two(S)
    D = datetime.datetime
    _post(S, x, y, 1000, D(2041, 12, 20))      # قبل الفترة -> رصيد أول
    _post(S, x, y, 300, D(2042, 1, 5))
    _post(S, y, x, 100, D(2042, 1, 9))
    d = S.report_data(D(2042, 1, 1), D(2042, 12, 31), account_id=x.id)
    st = d["ledger_statement"]
    assert [r["kind"] for r in st] == ["opening", "line", "line", "total"]
    assert st[0]["balance"] == 1000 and st[0]["description"] == "رصيد أول الفترة"
    assert [r["balance"] for r in st[1:3]] == [1300, 1200]            # تراكمي
    assert st[1]["date"] == "2042-01-05"
    t = st[-1]
    assert (t["debit"], t["credit"], t["balance"]) == (300, 100, 1200)     # الإجمالي والرصيد الختامي = أول + مدين - دائن
    assert all(r["kind"] != "grand" for r in st)


def test_all_accounts_grouped_with_grand_total_and_no_movement_opening(S):
    x, y = _two(S)
    D = datetime.datetime
    _post(S, x, y, 500, D(2043, 3, 1))                  # خارج الفترة، الحسابين ليهم رصيد أول
    _post(S, x, y, 200, D(2044, 2, 1))
    d = S.report_data(D(2044, 1, 1), D(2044, 12, 31))
    st = d["ledger_statement"]
    codes = [r["code"] for r in st if r["kind"] == "opening"]
    assert codes == sorted(codes) and x.code in codes and y.code in codes
    assert st[-1]["kind"] == "grand"
    assert st[-1]["debit"] == sum(r["debit"] for r in st if r["kind"] == "total")
    mine = [r for r in st if r["code"] == x.code]
    assert mine[0]["balance"] >= 500 and mine[-1]["kind"] == "total"
    # لو مفيش حركة في الفترة والحساب ليه رصيد أول: يظهر برصيده
    d2 = S.report_data(D(2050, 1, 1), D(2050, 12, 31), account_id=x.id)
    assert [r["kind"] for r in d2["ledger_statement"]] == ["opening", "total"]
    assert d2["ledger_statement"][-1]["balance"] == d2["ledger_statement"][0]["balance"]


def test_no_date_from_means_zero_opening_and_raw_ledger_untouched(S):
    x, y = _two(S)
    D = datetime.datetime
    _post(S, x, y, 70, D(2045, 5, 5))
    d = S.report_data(None, D(2045, 12, 31), account_id=x.id)
    assert d["ledger_statement"][0]["balance"] == 0 or d["ledger_statement"][0]["kind"] == "opening"
    assert all("balance" not in r for r in d["ledger"])        # الحسابات التانية (ميزان المراجعة) بتعتمد على السطور الخام


def test_export_rows_have_balance_column_and_styles(S):
    x, y = _two(S)
    D = datetime.datetime
    _post(S, x, y, 40, D(2046, 6, 6))
    d = S.report_data(D(2046, 1, 1), D(2046, 12, 31))
    rows = report_export._rows(d, "ledger")
    assert rows[0][-1].startswith("الرصيد") and len(rows[0]) == 8
    styles = d["row_styles"]
    assert "section" in styles.values() and "total" in styles.values()
    assert rows[1][4] == "رصيد أول الفترة"


def test_excel_and_pdf_export_build(S, tmp_path):
    x, y = _two(S)
    D = datetime.datetime
    _post(S, x, y, 40, D(2047, 6, 6))
    d = S.report_data(D(2047, 1, 1), D(2047, 12, 31))
    for fn in (report_export.export_excel, report_export.export_pdf):
        p = fn(dict(d), "ledger", str(tmp_path))
        assert p.endswith((".xlsx", ".pdf")) and __import__("os").path.getsize(p) > 500


def test_parent_account_includes_children(S):
    """دفتر الأستاذ لحساب أب بيجيب حركة وأرصدة كل الحسابات اللي تحته (أبناء وأحفاد)."""
    import datetime as _dt
    from erp_app import services as _S
    base = _S.list_accounts(postable_only=True)
    other = base[0]
    p = _S.create_account("88000", "أب اختبار", "asset")
    c1 = _S.create_account("88100", "ابن 1", "asset", parent_id=p)
    c2 = _S.create_account("88200", "ابن 2", "asset", parent_id=p)
    g = _S.create_account("88210", "حفيد", "asset", parent_id=c2)
    D = _dt.datetime
    _S.create_journal_entry([{"account_id": c1, "debit": 100}, {"account_id": other.id, "credit": 100}], reference="P1", description="x", entry_date=D(2070, 1, 5))
    _S.create_journal_entry([{"account_id": g, "debit": 40}, {"account_id": other.id, "credit": 40}], reference="P2", description="x", entry_date=D(2070, 2, 5))
    _S.create_journal_entry([{"account_id": c1, "credit": 10}, {"account_id": other.id, "debit": 10}], reference="P3", description="x", entry_date=D(2070, 3, 5))
    assert _S.account_and_descendant_ids(p) == {p, c1, c2, g}
    assert _S.account_and_descendant_ids(g) == {g}
    r = _S.account_ledger(p, date_from=D(2070, 2, 1))
    assert r["opening_balance"] == 100 and r["closing_balance"] == 130
    assert {x["code"] for x in r["rows"]} == {"88210", "88100"}
    kids = {k["code"]: k for k in r["children"]}
    assert kids["88100"]["opening"] == 100 and kids["88100"]["balance"] == 90 and kids["88210"]["balance"] == 40
    assert round(sum(k["balance"] for k in r["children"]), 2) == r["closing_balance"]
    assert _S.account_ledger(g)["children"] == []              # حساب فرعي: مفيش ملخص أبناء
    # التقارير الاحترافية: نفس السلوك (أقسام لكل حساب + إجمالي عام)
    d = _S.report_data(date_from=D(2070, 1, 1), date_to=D(2070, 12, 31), account_id=p)
    codes = {x["code"] for x in d["ledger"]}
    assert codes == {"88100", "88210"}
    assert any(r2.get("kind") == "grand" for r2 in d["ledger_statement"])
