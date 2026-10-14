from erp_app import data_integrity
from erp_app.db import JournalEntry, JournalEntryLine, get_session
from sqlalchemy import func


def test_purchase_sale_stock_and_entries(S, shop):
    S.create_purchase_invoice(shop["supplier"], [{"product_id": shop["item"], "quantity": 100, "unit_price": 12}], location_id=shop["loc"])
    assert S.get_balances_map()[shop["item"]] == 100
    S.create_sales_invoice(shop["cust"], [{"product_id": shop["item"], "quantity": 10, "unit_price": 30}], location_id=shop["loc"])
    assert S.get_balances_map()[shop["item"]] == 90


def test_every_entry_is_balanced(S, shop):
    with get_session() as s:
        bad = [r for r in s.query(JournalEntry.number, func.sum(JournalEntryLine.debit), func.sum(JournalEntryLine.credit))
               .join(JournalEntryLine).group_by(JournalEntry.id).all() if abs((r[1] or 0) - (r[2] or 0)) > 0.01]
    assert bad == []


def test_unbalanced_manual_entry_rejected(S, shop):
    accs = {a.code: a.id for a in S.list_accounts()}
    cash, exp = accs["121001"], accs["520075"]
    S.create_journal_entry([{"account_id": cash, "debit": 10}, {"account_id": exp, "credit": 10}], reference="t")
    try:
        S.create_journal_entry([{"account_id": cash, "debit": 10}, {"account_id": exp, "credit": 9}], reference="bad")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_receipt_and_payment_numbers_unique(S, shop):
    cash = {a.code: a.id for a in S.list_accounts()}["121001"]
    a = S.create_receipt(shop["cust"], 50, cash)
    b = S.create_receipt(shop["cust"], 60, cash)
    assert a != b


def test_integrity_clean_on_valid_data(S, shop):
    r = data_integrity.run()
    assert r["errors"] == 0, [c for c in r["checks"] if c["severity"] == "error" and c["count"]]
