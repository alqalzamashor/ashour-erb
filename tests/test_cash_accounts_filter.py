"""حساب النقدية/البنك في السندات: الحسابات الفرعية اللي نوع تدفقها "نقدي" فقط (وأبناء الحساب النقدي)."""
from erp_app.db import Account, get_session


def test_list_cash_accounts_only_cash_typed_leaf_accounts(S):
    from erp_app import services
    with get_session() as s:
        par = Account(code="9100", name="نقدية وبنوك (رئيسي)", account_type="asset", cash_flow_type="cash"); s.add(par); s.flush()
        box = Account(code="9101", name="صندوق", account_type="asset", parent_id=par.id, cash_flow_type="cash")
        child_untyped = Account(code="9102", name="بنك تحت الرئيسي", account_type="asset", parent_id=par.id)   # ابن حساب نقدي: نقدي
        other = Account(code="9200", name="مبانى", account_type="asset", cash_flow_type="investing")
        plain = Account(code="9300", name="بنك (مش متعلّم)", account_type="asset")
        s.add_all([box, child_untyped, other, plain]); s.commit()
    codes = {a.code for a in services.list_cash_accounts()}
    assert {"9101", "9102"} <= codes
    assert "9100" not in codes            # الحساب الرئيسي مش قابل للترحيل
    assert "9200" not in codes and "9300" not in codes
    assert all(a.account_type for a in services.list_cash_accounts())
