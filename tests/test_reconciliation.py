"""تقرير مطابقة الحسابات: كشف بنك/مورد (Excel/CSV) مقابل الدفتر، وطلوع الفروقات."""
import datetime

import pytest

from erp_app import reconciliation as R

D = datetime.datetime


def _two(S):
    a = {x.code: x for x in S.list_accounts(postable_only=True)}
    c = list(a)
    return a[c[0]], a[c[1]]


def _csv(tmp_path, text, name="stmt.csv"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


_N = {"n": 0}


def _bank_book(S):
    """بنك جديد لكل اختبار (الداتابيز مشتركة بين الاختبارات)، والمقابل حساب موجود."""
    from erp_app.db import Account, get_session
    _N["n"] += 1
    _, other = _two(S)
    bid = S.create_account(f"77{_N['n']:03d}", f"بنك اختبار {_N['n']}", "asset", cash_flow_type="cash")
    with get_session() as sess:
        bank = sess.get(Account, bid)
        sess.expunge(bank)
    def dep(amount, d, ref="", desc="x"):
        S.create_journal_entry([{"account_id": bank.id, "debit": amount}, {"account_id": other.id, "credit": amount}], reference=ref, description=desc, entry_date=d)
    def wd(amount, d, ref="", desc="x"):
        S.create_journal_entry([{"account_id": other.id, "debit": amount}, {"account_id": bank.id, "credit": amount}], reference=ref, description=desc, entry_date=d)
    dep(2000, D(2060, 2, 15), desc="رصيد سابق")
    dep(1000, D(2060, 3, 1), desc="تحصيل")
    wd(300, D(2060, 3, 5), ref="CHQ1001", desc="شيك")
    dep(500, D(2060, 3, 10), desc="إيداع")
    wd(200, D(2060, 3, 20), desc="شيك معلّق")          # مش في الكشف
    wd(90, D(2060, 3, 26), ref="TRF77001", desc="تحويل")
    return bank


STMT = """التاريخ,البيان,المرجع,مدين,دائن,الرصيد
2060-03-01,تحصيل,,0,1000,3000
2060-03-07,شيك,CHQ1001,300,0,2700
2060-03-18,إيداع,,0,500,3200
2060-03-25,رسوم بنكية,,15,0,3185
2060-03-28,تحويل,TRF77001,95,0,3090
"""


def test_bank_reconciliation_end_to_end(S, tmp_path):
    bank = _bank_book(S)
    rep = R.build_report("account", bank.id, _csv(tmp_path, STMT), window=5)
    sm = rep["summary"]
    assert (sm["matched"], sm["date_diff"], sm["amount_diff"], sm["stmt_only"], sm["book_only"]) == (2, 1, 1, 1, 1)
    assert [s["description"] for s, b in rep["date_diff"]] == ["إيداع"]                       # نفس المبلغ بفارق 8 يوم > المهلة
    s, b = rep["amount_diff"][0]
    assert (s["amount"], b["amount"]) == (-95.0, -90.0) and s["reference"] == "TRF77001"
    assert rep["stmt_only"][0]["amount"] == -15.0 and rep["book_only"][0]["amount"] == -200.0
    # الأرصدة والتسوية
    assert rep["book_opening"] == 2000 and rep["stmt_opening"] == 2000 and rep["opening_diff"] == 0
    assert rep["book_closing"] == 2910 and rep["stmt_closing"] == 3090 and rep["closing_diff"] == 180
    assert sm["unexplained"] == 0 and sm["period_diff"] == 180
    assert rep["adjusted_book"] == rep["adjusted_stmt"] == 2890


def test_window_changes_matching_and_flip_reverses_columns(S, tmp_path):
    bank = _bank_book(S)
    rep = R.build_report("account", bank.id, _csv(tmp_path, STMT), window=10)
    assert rep["summary"]["date_diff"] == 0 and rep["summary"]["matched"] == 3          # المهلة 10 أيام: الإيداع بقى مطابق عادي
    flipped = R.build_report("account", bank.id, _csv(tmp_path, STMT, "f.csv"), window=5, flip=True)
    assert flipped["summary"]["matched"] == 0 and flipped["stmt_closing"] == -3090      # كل الإشارات اتعكست


def test_closing_override_and_period_filter_excludes_book_lines_outside(S, tmp_path):
    bank = _bank_book(S)
    rep = R.build_report("account", bank.id, _csv(tmp_path, STMT.replace(",3090\n", ",\n").replace(",3185\n", ",\n").replace(",3200\n", ",\n").replace(",2700\n", ",\n").replace(",3000\n", ",\n")),
                         window=5, closing_override=3090)
    assert rep["stmt_closing"] == 3090 and rep["stmt_opening"] == 2000                  # بدون عمود رصيد: الختامي من الإدخال اليدوي
    part = R.build_report("account", bank.id, _csv(tmp_path, STMT, "p.csv"), window=5, date_from="2060-03-01", date_to="2060-03-10")
    assert part["summary"]["stmt_count"] == 2                                           # 01 و07 (شيك)؛ إيداع 18 خارج الفترة
    assert any(b["amount"] == -200.0 for b in part["outside"]) and part["summary"]["book_only"] == 1   # شيك 03-20 خارج؛ والإيداع 03-10 في الفترة مالوش مقابل


def test_parse_statement_formats(S, tmp_path):
    # عمود مبلغ واحد بإشارة + أرقام عربية + كشف تنازلي (الأحدث فوق)
    txt = "Date,Details,Amount,Balance\n2060-05-03,Fee,-10.50,990\n2060-05-02,Deposit,\"1,000.00\",1000.50\n"
    st = R.parse_statement(_csv(tmp_path, txt), "account")
    assert [l["amount"] for l in st["lines"]] == [-10.5, 1000.0]
    assert st["closing"] == 990 and st["skipped"] == 0
    with pytest.raises(ValueError):
        R.parse_statement(_csv(tmp_path, "a,b\n1,2\n", "bad.csv"), "account")


def test_supplier_statement_sign_convention_and_reconcile(S, shop, tmp_path):
    sup = shop["supplier"]
    S.create_purchase_invoice(sup, [{"product_id": shop["item"], "quantity": 10, "unit_price": 12}], location_id=shop["loc"], invoice_date=D(2061, 1, 10))      # علينا 138 (120 + ضريبة 15%)
    S.create_payment(sup, 50, S.list_cash_accounts()[0].id, date=D(2061, 1, 20), partner_type="supplier")
    bl = R.book_lines("supplier", sup, "2061-01-01", "2061-01-31")
    assert sorted(l["amount"] for l in bl["lines"]) == [-50.0, 138.0] and bl["closing"] == 88.0
    # كشف المورد من دفتره: الفاتورة مدين والسداد دائن (+ فاتورة ما سجلناهاش 30)
    txt = "التاريخ,البيان,رقم المستند,مدين,دائن\n2061-01-10,فاتورة,INV-1,138,0\n2061-01-20,سداد,PAY-1,0,50\n2061-01-25,فاتورة,INV-2,30,0\n"
    rep = R.build_report("supplier", sup, _csv(tmp_path, txt), window=3)
    assert rep["summary"]["matched"] == 2 and [s["amount"] for s in rep["stmt_only"]] == [30.0] and rep["summary"]["unexplained"] == 0
    assert rep["book_closing"] == 88.0
    rows = R.flat_rows(rep)
    assert len(rows) == 1 and rows[0]["label"] == "في الكشف فقط" and rows[0]["diff"] == 30.0


def test_reconcile_pure_handles_duplicates_one_to_one():
    st = [{"date": D(2060, 1, 1), "description": "", "reference": "", "amount": 25.0}] * 3
    bk = [{"date": D(2060, 1, 2), "number": f"J{i}", "reference": "", "description": "", "amount": 25.0} for i in range(2)]
    r = R.reconcile(st, bk, 5)
    assert len(r["matched"]) == 2 and len(r["stmt_only"]) == 1 and r["summary"]["unexplained"] == 0


def test_export_table_excel_and_pdf(S, tmp_path):
    from erp_app.report_export import export_excel, export_pdf
    from erp_app.views.account_reconciliation import export_table
    bank = _bank_book(S)
    rep = R.build_report("account", bank.id, _csv(tmp_path, STMT), window=5)
    data = export_table(rep)
    t = data["table"]
    assert t[0][0] == "النوع" and len(t[0]) == 8
    labels = [r[0] for r in t]
    assert "رصيد الدفتر المعدّل" in labels and "اختلاف في المبلغ" in labels and "في الكشف فقط" in labels and "في الدفتر فقط" in labels
    assert any(str(r[0]).startswith("المطابق") for r in t) and any(v == "total" for v in data["row_styles"].values())
    for fn in (export_excel, export_pdf):
        p = fn(dict(data), "account_reconciliation", str(tmp_path))
        assert __import__("os").path.getsize(p) > 500
