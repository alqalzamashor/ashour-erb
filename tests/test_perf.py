"""الأداء: تجميع الموازنة في SQL بنفس نتيجة الحساب القديم، كاش لوحة المؤشرات (يتجدّد مع التعديل ومفصول لكل مستخدم)، وإحصاءات التزامن."""
import datetime

import pytest

from erp_app import concurrency
from erp_app.db import Account, JournalEntry, JournalEntryLine, get_session


def _reference_actual(S, df, dt):
    """الحساب القديم (تحميل كل سطر قيد) كمرجع للمقارنة."""
    out = {}
    with get_session() as s:
        q = s.query(JournalEntryLine).join(JournalEntry).filter(JournalEntry.posted.is_(True))
        if df:
            q = q.filter(JournalEntry.date >= S._dt_start(df))
        if dt:
            q = q.filter(JournalEntry.date <= S._dt_end(dt))
        for l in q.all():
            if l.account.account_type not in ("income", "expense"):
                continue
            amt = (float(l.credit or 0) - float(l.debit or 0)) if l.account.account_type == "income" else (float(l.debit or 0) - float(l.credit or 0))
            k = (l.account_id, l.branch_id, l.cost_center_id)
            out[k] = out.get(k, 0) + amt
    return out


def test_budget_vs_actual_matches_reference(S, shop):
    for _ in range(3):
        S.create_sales_invoice(shop["cust"], [{"product_id": shop["burger"], "quantity": 2, "unit_price": 100}], location_id=shop["loc"])
    df, dt = datetime.date(2000, 1, 1), datetime.date.today() + datetime.timedelta(days=1)
    ref = _reference_actual(S, df, dt)
    assert ref, "لازم يكون فيه قيود دخل/مصروف للمقارنة"
    got = {(r["account_id"], r["branch_id"], r["cost_center_id"]): r["actual"] for r in S.budget_vs_actual(df, dt)}
    assert set(got) == set(ref)
    for k, v in ref.items():
        assert got[k] == pytest.approx(round(v, 2))


def test_dashboard_cache_hits_and_invalidates(S, shop, monkeypatch):
    calls = []
    real = S._executive_dashboard_uncached
    monkeypatch.setattr(S, "_executive_dashboard_uncached", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    S._DASH_CACHE.clear()
    df, dt = datetime.date(2000, 1, 1), datetime.date.today()
    a = S.executive_dashboard(df, dt)
    b = S.executive_dashboard(df, dt)
    assert len(calls) == 1 and a == b
    b["kpis"]["revenue"] = -1                                   # تعديل النسخة المرجّعة ما يلوّثش الكاش
    assert S.executive_dashboard(df, dt)["kpis"]["revenue"] == a["kpis"]["revenue"]
    S.create_customer(name="عميل جديد للكاش")                    # أي commit بيبطل الكاش
    S.executive_dashboard(df, dt)
    assert len(calls) == 2
    # مستخدم تاني (أو سياق نظام) = مفتاح كاش مختلف
    me = S._get_user()
    try:
        S.set_current_user(None)
        S.executive_dashboard(df, dt)
        assert len(calls) == 3
    finally:
        S.set_current_user(me)


def test_dashboard_cache_can_be_disabled(S, monkeypatch):
    monkeypatch.setattr(S, "DASH_TTL", 0)
    calls = []
    real = S._executive_dashboard_uncached
    monkeypatch.setattr(S, "_executive_dashboard_uncached", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    S.executive_dashboard(datetime.date(2000, 1, 1), datetime.date.today())
    S.executive_dashboard(datetime.date(2000, 1, 1), datetime.date.today())
    assert len(calls) == 2


def test_concurrency_stats_shape():
    s = concurrency.stats()
    assert {"mode", "workers", "busy_handlers", "handlers_total", "slow_handlers", "loop_lag_p95_ms", "loop_lag_max_ms"} <= set(s)
    assert concurrency.WORKERS >= 1
