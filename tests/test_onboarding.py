import pytest

from erp_app import onboarding as ob


def test_steps_progress_and_demo(S, tmp_path, monkeypatch):
    monkeypatch.setattr(ob, "PATH", str(tmp_path / "ob.json"))
    done0, total = ob.progress()
    assert total == 7 and done0 < total
    assert not ob.dismissed(); ob.dismiss(); assert ob.dismissed(); ob.dismiss(False)
    assert not ob.has_activity()
    r = ob.load_demo()
    assert r["products"] == 12 and r["sales"] > 10 and ob.has_activity()
    with pytest.raises(ValueError):                 # مرة واحدة بس على قاعدة فاضية
        ob.load_demo()
    keys = {s["key"]: s["done"] for s in ob.steps()}
    assert keys["products"] and keys["sale"] and keys["customers"]
    # الأرقام متسقة: المبيعات في اللوحة = مجموع الفواتير
    from erp_app.db import SalesInvoice, get_session
    with get_session() as s:
        assert s.query(SalesInvoice).count() == r["sales"]
    dash = S.executive_dashboard(None, None, None, None)
    assert dash["kpis"]["revenue"] > 0


def test_demo_requires_admin(S):
    me = S._get_user()
    S.set_current_user({"id": 999, "username": "x", "role": "user", "permissions": "{}"})
    try:
        with pytest.raises(PermissionError):
            ob.load_demo()
    finally:
        S.set_current_user(me)


def test_line_total_rounding_never_unbalances(S):
    import random
    r = random.Random(1)
    for _ in range(5000):
        q, p, d, t = r.randint(1, 9), round(r.uniform(0.5, 99), 2), r.choice([0, 0, 0.35, 1.1]), r.choice([0, 5, 15])
        b, tax, tot = S._compute_line_total(q, p, d, t)
        assert abs(tot - (b + tax)) < 1e-9
