"""اليومية العامة بتجميع شجري (فرع > حساب > طرف > مركز)."""
import datetime

from erp_app import journal_tree as T

ROWS = [
    {"entry_id": 1, "number": "JV-1", "date": "2060-01-02", "description": "a", "branch": "B1 - الرئيسي", "account": "1100 - عملاء", "party": "عميل - أحمد", "cost_center": "", "debit": 100.0, "credit": 0.0},
    {"entry_id": 1, "number": "JV-1", "date": "2060-01-02", "description": "b", "branch": "B1 - الرئيسي", "account": "4100 - مبيعات", "party": "", "cost_center": "CC1 - مطعم", "debit": 0.0, "credit": 100.0},
    {"entry_id": 2, "number": "JV-2", "date": "2060-01-05", "description": "c", "branch": "B2 - الفرع", "account": "1100 - عملاء", "party": "عميل - سارة", "cost_center": "CC1 - مطعم", "debit": 50.0, "credit": 0.0},
    {"entry_id": 2, "number": "JV-2", "date": "2060-01-05", "description": "d", "branch": "", "account": "4100 - مبيعات", "party": "", "cost_center": "", "debit": 0.0, "credit": 50.0},
]


def test_clean_levels():
    assert T.clean_levels(["branch", "", "branch", "bogus", "account"]) == ["branch", "account"]
    assert T.clean_levels(None) == []


def test_tree_totals_and_order():
    nodes, grand = T.build_tree(ROWS, ["branch", "account", "party"])
    assert grand == {"debit": 150.0, "credit": 150.0, "balance": 0.0, "count": 4}
    assert [n["label"] for n in nodes] == ["B1 - الرئيسي", "B2 - الفرع", "بدون فرع"]      # "بدون" في الآخر
    b1 = nodes[0]
    assert (b1["debit"], b1["credit"], b1["balance"], b1["count"]) == (100.0, 100.0, 0.0, 2)
    assert [c["label"] for c in b1["children"]] == ["1100 - عملاء", "4100 - مبيعات"]
    leaf = b1["children"][0]["children"][0]
    assert leaf["label"] == "عميل - أحمد" and leaf["children"] == [] and len(leaf["lines"]) == 1
    # مجموع الفروع = الإجمالي العام
    assert round(sum(n["debit"] for n in nodes), 2) == grand["debit"]


def test_order_is_user_choice():
    nodes, _ = T.build_tree(ROWS, ["account", "branch"])
    assert [n["label"] for n in nodes] == ["1100 - عملاء", "4100 - مبيعات"]
    assert nodes[0]["children"][0]["level"] == "branch"
    assert T.build_tree(ROWS, [])[0] == []


def test_export_table():
    nodes, grand = T.build_tree(ROWS, ["branch", "cost_center"])
    data = T.export_table(nodes, grand, ["branch", "cost_center"])
    t = data["table"]
    assert t[0] == ["البند", "مدين", "دائن", "الرصيد (مدين - دائن)"] and t[-1][0] == "الإجمالي العام" and t[-1][1] == 150.0
    assert any("JV-1" in str(r[0]) for r in t)
    assert data["row_styles"][len(t) - 1] == "net"
    nolines = T.export_table(nodes, grand, ["branch", "cost_center"], with_lines=False)["table"]
    assert len(nolines) < len(t)


def test_journal_entries_date_filter(S):
    a = {x.code: x for x in S.list_accounts(postable_only=True)}
    c = list(a)
    S.create_journal_entry([{"account_id": a[c[0]].id, "debit": 7}, {"account_id": a[c[1]].id, "credit": 7}], reference="TREE-DF", description="x", entry_date=datetime.datetime(2058, 5, 10))
    got = S.list_journal_entries(limit=100000, date_from="2058-05-01", date_to="2058-05-31")
    assert [j.reference for j in got] == ["TREE-DF"]
    assert S.list_journal_entries(limit=100000, date_from="2058-06-01", date_to="2058-06-30") == []


def test_tree_export_files(tmp_path):
    from erp_app.report_export import export_excel, export_pdf
    nodes, grand = T.build_tree(ROWS, ["branch", "account", "party", "cost_center"])
    data = T.export_table(nodes, grand, ["branch", "account", "party", "cost_center"])
    data.update(date_from="2060-01-01", date_to="2060-01-31")
    for fn in (export_excel, export_pdf):
        assert fn(data, "general_journal_tree", str(tmp_path))
