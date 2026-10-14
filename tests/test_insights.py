import datetime
import json
import os

import openpyxl
import pytest

from erp_app import alerts, field_access, import_export, insights, notify
from erp_app.db import JournalEntry, Product, ProductUnitLine, get_session

NOW = datetime.datetime.now()


def days(n):
    return NOW - datetime.timedelta(days=n)


@pytest.fixture(scope="module")
def world(S, shop):
    """مخزن فيه: راكد (دخل من 200 يوم بدون بيع)، سريع البيع قارب ينفد، وعملاء متأخر/متعدّي الحد."""
    loc = shop["loc"]
    slow = S.create_product("SLOW1", "صنف راكد", sale_price=50, cost_price=20)
    fast = S.create_product("FAST1", "صنف سريع", sale_price=10, cost_price=4)
    ok = S.create_product("OK1", "صنف سليم", sale_price=10, cost_price=4, reorder_point=0)
    S.create_stock_move(slow, loc, "in", 10, unit_cost=20, reference="OPEN", move_date=days(200))
    S.create_stock_move(fast, loc, "in", 100, unit_cost=4, reference="OPEN", move_date=days(70))
    S.create_stock_move(ok, loc, "in", 1000, unit_cost=4, reference="OPEN", move_date=days(5))
    late = S.create_customer(name="عميل متأخر", phone="0500000011", credit_days=30)
    capped = S.create_customer(name="عميل محدود", phone="0500000012", credit_limit=100, credit_days=30)
    # مبيعات الصنف السريع: 90 وحدة خلال 60 يوم => 1.5/يوم (والرصيد 10 => يكفي ~7 أيام)؛ أقدم فاتورة (55 يوم) متأخرة 25 يوم عن استحقاقها
    for d in (55, 20, 10):
        S.create_sales_invoice(late, [{"product_id": fast, "quantity": 30, "unit_price": 10}], location_id=loc, invoice_date=days(d))
    S.create_sales_invoice(capped, [{"product_id": ok, "quantity": 20, "unit_price": 10}], location_id=loc, invoice_date=days(2))   # 230 > 100
    return {"slow": slow, "fast": fast, "ok": ok, "late": late, "capped": capped, **shop}


def restricted_user(S, name, hidden, extra=None):
    perms = {"products": ["view", "create", "edit"], "alerts": ["view"], "dashboard": ["view"], "stock_moves": ["view", "create"],
             "sales_invoices": ["view", "create", "post"], "customers": ["view"], "reports": ["view"], **(extra or {})}
    S.create_user(name, "pw12345", name, "sales", field_access.with_hidden(perms, hidden))
    return name


def login(S, name):
    S.set_current_user(S.authenticate_user(name, "pw12345"))


def test_alerts_detect_slow_low_overdue_and_limit(S, world):
    items = alerts.compute()
    by = {(a["kind"], a["title"]): a for a in items}
    slow = by[("slow", "صنف راكد (SLOW1)")]
    assert slow["days"] >= 199 and slow["severity"] == "high" and slow["value"] == 200          # 10 × 20
    low = [a for a in items if a["kind"] == "low"]
    assert any("FAST1" in a["title"] and a["severity"] == "high" and "يكفي 7 يوم" in a["detail"] for a in low)
    assert not any("OK1" in a["title"] for a in low) and not any("OK1" in a["title"] for a in items if a["kind"] == "slow")
    over = {a["title"]: a for a in items if a["kind"] == "overdue"}
    assert over["عميل متأخر"]["days"] == 25 and over["عميل متأخر"]["value"] == 345 and over["عميل متأخر"]["severity"] == "low"     # فاتورة 345 متأخرة 25 يوم فقط (والباقي لسه مش مستحق)
    lim = [a for a in items if a["kind"] == "limit"]
    assert any(a["title"] == "عميل محدود" and a["severity"] == "high" for a in lim)


def test_alert_thresholds_are_configurable(S, world):
    alerts.save_config(slow_days=300)
    assert not any(a["kind"] == "slow" and "SLOW1" in a["title"] for a in alerts.compute())
    alerts.save_config(slow_days=90, slow_enabled=False)
    assert not any(a["kind"] == "slow" for a in alerts.compute())
    alerts.save_config(slow_enabled=True)
    with pytest.raises(ValueError):
        alerts.save_config(slow_days=0)
    s = alerts.summary()
    assert s["slow"] >= 1 and s["low"] >= 1 and s["total"] == sum(s[k] for k in alerts.KINDS)


def test_alert_digest_goes_through_notifications(S, world, monkeypatch):
    monkeypatch.setattr(notify, "SYNC", True)
    notify.save_config(enabled=True, provider="none")
    alerts.save_config(digest_enabled=True, digest_recipients="0500000099", digest_hour=0)
    assert alerts.send_digest() == 1
    assert alerts.send_digest() == 0                                  # مرة واحدة في اليوم
    log = notify.list_log(kind="alerts")
    assert log and "صنف راكد" in log[0].body and "SLOW1" in log[0].body
    notify.save_config(enabled=False)


def test_period_ranges():
    f, t = datetime.datetime(2026, 3, 1), datetime.datetime(2026, 3, 31)
    assert insights.previous_range(f, t, "prev") == (datetime.datetime(2026, 1, 29), datetime.datetime(2026, 2, 28))
    assert insights.previous_range(datetime.datetime(2024, 2, 29), datetime.datetime(2024, 3, 10), "yoy") == (datetime.datetime(2023, 2, 28), datetime.datetime(2023, 3, 10))
    with pytest.raises(ValueError):
        insights.previous_range(t, f, "prev")


def test_compare_periods_and_cash(S, world):
    c = insights.compare(days(35), NOW, "prev")
    rows = {r["key"]: r for r in c["rows"]}
    assert rows["revenue"]["current"] > 0 and rows["revenue"]["delta"] == pytest.approx(rows["revenue"]["current"] - rows["revenue"]["previous"])
    assert rows["profit"]["current"] is not None and "cash_net" in rows and c["prev_range"][1] < days(35)
    assert insights.compare(days(35), NOW, "none")["previous"] is None
    cash = insights.cash_summary(days(35), NOW)
    assert {"operating", "investing", "financing", "net", "opening", "closing"} <= set(cash) and len(cash["months"]) >= 1


def test_hidden_cost_in_ui_reports_but_not_in_books(S, world):
    admin = S.current_user()
    real_cost = 20.0
    name = restricted_user(S, "nocost", ["cost_price", "profit"])
    login(S, name)
    try:
        assert not field_access.can_see("cost_price") and not field_access.can_see("profit")
        # لوحة الإدارة: لا ربح ولا قيمة مخزون
        d = S.executive_dashboard(days(35), NOW)
        assert d["kpis"]["profit"] is None and d["kpis"]["gross_profit"] is None and d["inventory"]["total_value"] is None
        assert all(m["profit"] is None for m in d["monthly"]) and d["kpis"]["revenue"] > 0
        c = insights.compare(days(35), NOW, "prev")
        assert {r["key"] for r in c["rows"]}.isdisjoint({"profit", "gross_profit", "net_margin_pct"}) and c["current"]["profit"] is None
        # تقارير المخزون
        assert S.get_inventory_kpis()["total_stock_value"] is None and S.inventory_report()["total_value"] is None
        assert all(r["unit_cost"] is None and r["value"] is None for r in S.product_movement_report(world["slow"]))
        # تنبيه الراكد من غير المبلغ المجمّد
        slow = next(a for a in alerts.compute() if a["kind"] == "slow" and "SLOW1" in a["title"])
        assert slow["value"] is None and "مجمّد" not in slow["detail"]
        # لا يقدر يحدد/يغيّر التكلفة
        p_new = S.create_product("NC1", "جديد", cost_price=55, sale_price=80)
        S.update_product_details(world["slow"], "SLOW1", "صنف راكد", cost_price=999, sale_price=50)
        S.update_product(world["slow"], cost_price=888)
        S.save_product_units(world["slow"], [{"unit_id": S.list_product_units(world["slow"])[0].unit_id, "factor_to_base": 1, "sale_price": 50, "cost_price": 777, "is_default": True}])
        # تصدير الأصناف بدون تكلفة
        out = os.path.join(os.environ["ERP_HOME"], "p.xlsx")
        import_export.export_products(out)
        ws = openpyxl.load_workbook(out).active
        assert all(row[4].value in (None, "") for row in ws.iter_rows(min_row=2))
        # الدفاتر الداخلية لسه بالتكلفة الحقيقية: بيع من مستخدم مخفي عنه التكلفة بيسجّل نفس قيد تكلفة المبيعات اللي بيسجّله المدير
        def sale_lines():
            inv = S.create_sales_invoice(world["cust"], [{"product_id": world["slow"], "quantity": 1, "unit_price": 50}], location_id=world["loc"])
            with get_session() as s:
                je = s.query(JournalEntry).filter(JournalEntry.source_type == "sales_invoice").order_by(JournalEntry.id.desc()).first()
                return sorted((round(l.debit or 0, 2), round(l.credit or 0, 2)) for l in je.lines)
        restricted_lines = sale_lines()
        S.set_current_user(admin)
        admin_lines = sale_lines()
        assert restricted_lines == admin_lines and (20.0, 0.0) in restricted_lines and (0.0, 20.0) in restricted_lines    # COGS / المخزون = 20 الحقيقية
        login(S, name)
        with get_session() as s:
            assert s.get(Product, p_new).cost_price == 0
            assert s.get(Product, world["slow"]).cost_price == real_cost
            assert s.query(ProductUnitLine).filter(ProductUnitLine.product_id == world["slow"]).first().cost_price in (None, real_cost)
    finally:
        S.set_current_user(admin)
    # الأدمن لسه بيشوف كل حاجة
    assert S.executive_dashboard(days(35), NOW)["kpis"]["profit"] is not None
    assert S.get_inventory_kpis()["total_stock_value"] is not None


def test_existing_users_without_hidden_list_see_everything(S, world):
    admin = S.current_user()
    S.create_user("legacy", "pw12345", "قديم", "sales", {"products": ["view"], "dashboard": ["view"]})
    login(S, "legacy")
    try:
        assert field_access.hidden_fields() == set() and S.get_inventory_kpis()["total_stock_value"] is not None
    finally:
        S.set_current_user(admin)


def test_role_defaults_hide_cost_for_new_sales_user_and_admin_never_hidden(S):
    S.create_user("auto_sales", "pw12345", "مبيعات", "sales")
    with get_session() as s:
        from erp_app.db import User
        perms = json.loads(s.query(User).filter(User.username == "auto_sales").first().permissions)
    assert set(field_access.hidden_in(perms)) == {"cost_price", "profit"}
    assert field_access.hidden_fields({"role": "admin", "permissions": json.dumps({"_hidden": ["cost_price"]})}) == set()


class _Page:
    """صفحة Flet وهمية تكفي لبناء الشاشات (بدون واجهة)."""
    overlay = []
    session = None

    def update(self, *a, **k):
        pass

    def run_task(self, *a, **k):
        pass


def _controls(c, acc=None):
    acc = [] if acc is None else acc
    acc.append(c)
    for attr in ("controls", "content", "rows", "cells"):
        v = getattr(c, attr, None)
        for x in (v if isinstance(v, list) else [v] if v is not None else []):
            if hasattr(x, "__dict__"):
                _controls(x, acc)
    return acc


def test_screens_build_for_restricted_and_admin_users(S, world):
    from erp_app.views.dashboard import build_dashboard
    from erp_app.views.product_movements import build_product_movements
    from erp_app.views.products import build_products
    from erp_app.views.smart_alerts import build_smart_alerts
    from erp_app.views.stock_balance import build_stock_balance
    admin = S.current_user()
    S.create_user("viewer_nc", "pw12345", "مشاهد", "viewer", field_access.with_hidden(
        {"dashboard": ["view"], "alerts": ["view"], "products": ["view"], "stock_balance": ["view"], "product_movements": ["view"]}, ["cost_price", "profit"]))
    try:
        for who in ("admin", "viewer_nc"):
            if who != "admin":
                login(S, who)
            for b in (build_dashboard, build_products, build_stock_balance, build_product_movements, build_smart_alerts):
                assert b(_Page()) is not None, (who, b.__name__)
        # لوحة المستخدم المقيّد ما فيهاش بطاقات الربح
        texts = [getattr(c, "value", "") for c in _controls(build_dashboard(_Page())) if isinstance(getattr(c, "value", None), str)]
        assert "صافي الربح" not in texts and "مجمل الربح" not in texts and "إجمالي المبيعات" in texts
    finally:
        S.set_current_user(admin)
    texts = [getattr(c, "value", "") for c in _controls(build_dashboard(_Page())) if isinstance(getattr(c, "value", None), str)]
    assert "صافي الربح" in texts and "مجمل الربح" in texts
