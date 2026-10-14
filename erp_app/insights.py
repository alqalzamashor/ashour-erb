"""تحليلات الإدارة: مقارنة فترتين (السابقة / نفس الفترة العام الماضي) وملخص التدفق النقدي، تحترم صلاحيات الحقول (الأرباح)."""
import datetime

from . import field_access, services

MODES = {"none": "بدون مقارنة", "prev": "الفترة السابقة (نفس الطول)", "yoy": "نفس الفترة العام الماضي"}


def _d(v):
    if isinstance(v, datetime.datetime):
        return v.replace(hour=0, minute=0, second=0, microsecond=0)
    if isinstance(v, datetime.date):
        return datetime.datetime.combine(v, datetime.time())
    return None


def previous_range(df, dt, mode):
    """(من، إلى) للفترة المقارَن بها. prev: الفترة اللي قبلها مباشرة بنفس عدد الأيام. yoy: نفس التواريخ قبل سنة."""
    df, dt = _d(df), _d(dt)
    if not df or not dt or dt < df:
        raise ValueError("حدد فترة صحيحة (من ≤ إلى)")
    if mode == "prev":
        n = (dt - df).days + 1
        pe = df - datetime.timedelta(days=1)
        return pe - datetime.timedelta(days=n - 1), pe
    if mode == "yoy":
        def back(x):
            try:
                return x.replace(year=x.year - 1)
            except ValueError:               # 29 فبراير
                return x.replace(year=x.year - 1, day=28)
        return back(df), back(dt)
    raise ValueError("نوع المقارنة غير معروف")


def _cash(df, dt, branch_id, cc_id):
    c = services.cash_flow_statement(df, dt, branch_id, cc_id)
    return {"net_operating": c["net_operating"], "net_investing": c["net_investing"], "net_financing": c["net_financing"], "net": c["net"],
            "opening_cash": c["opening_cash"], "closing_cash": c["closing_cash"]}


def _period(df, dt, branch_id, cc_id):
    k = services.management_kpis(df, dt, branch_id, cc_id)
    sales = services.executive_monthly_trend(df, dt, branch_id, cc_id)
    n_inv = sum(m["sales_count"] for m in sales)
    out = {"revenue": k["revenue"], "expense": k["expense"], "profit": k["profit"], "gross_profit": k["gross_profit"],
           "net_margin_pct": k["net_margin_pct"], "gross_margin_pct": k["gross_margin_pct"], "sales_count": n_inv,
           "avg_invoice": (k["revenue"] / n_inv if n_inv else 0.0)}
    out.update({"cash_" + a: b for a, b in _cash(df, dt, branch_id, cc_id).items()})
    return out


# (المفتاح، الاسم، هل الارتفاع جيد؟، الحقل المطلوب إظهاره)
METRICS = [("revenue", "المبيعات / الإيرادات", True, None), ("expense", "المصروفات", False, None), ("profit", "صافي الربح", True, "profit"),
           ("gross_profit", "مجمل الربح", True, "profit"), ("net_margin_pct", "هامش صافي الربح %", True, "profit"), ("sales_count", "عدد الفواتير", True, None),
           ("avg_invoice", "متوسط الفاتورة", True, None), ("cash_net_operating", "صافي النقد التشغيلي", True, None), ("cash_net", "صافي التغيّر في النقدية", True, None),
           ("cash_closing_cash", "رصيد النقدية آخر الفترة", True, None)]


def compare(df, dt, mode="prev", branch_id=None, cost_center_id=None):
    """{'current','previous','prev_range','rows':[{key,label,current,previous,delta,delta_pct,good}]}. الأرباح تتشال لو مخفية عن المستخدم."""
    cur = _period(_d(df), _d(dt), branch_id, cost_center_id)
    res = {"mode": mode, "current": cur, "previous": None, "prev_range": None, "rows": []}
    prev = None
    if mode != "none":
        pf, pt = previous_range(df, dt, mode)
        prev = _period(pf, pt, branch_id, cost_center_id)
        res["previous"], res["prev_range"] = prev, (pf, pt)
    hid = field_access.hidden_fields()
    for key, label, up_good, field in METRICS:
        if field in hid:
            continue
        c = cur[key]
        row = {"key": key, "label": label, "current": c, "previous": None, "delta": None, "delta_pct": None, "good": None}
        if prev is not None:
            p = prev[key]
            row["previous"], row["delta"] = p, c - p
            row["delta_pct"] = ((c - p) / abs(p) * 100.0) if abs(p) > 0.005 else None
            row["good"] = None if abs(c - p) < 0.005 else ((c > p) == up_good)
        res["rows"].append(row)
    if "profit" in hid:
        for blk in (res["current"], res["previous"] or {}):
            for k in ("profit", "gross_profit", "net_margin_pct", "gross_margin_pct"):
                if k in blk:
                    blk[k] = None
    return res


def cash_summary(df, dt, branch_id=None, cost_center_id=None):
    """ملخص التدفق النقدي للفترة + صافي التغيّر الشهري (للرسم)."""
    tot = services.cash_flow_statement(df, dt, branch_id, cost_center_id)
    months = []
    for start, end, key in services._month_ranges(df, dt):
        c = services.cash_flow_statement(start, end, branch_id, cost_center_id)
        months.append({"key": key, "label": start.strftime("%b %Y"), "operating": c["net_operating"], "investing": c["net_investing"], "financing": c["net_financing"], "net": c["net"], "closing": c["closing_cash"]})
    return {"operating": tot["net_operating"], "investing": tot["net_investing"], "financing": tot["net_financing"], "net": tot["net"],
            "opening": tot["opening_cash"], "closing": tot["closing_cash"], "unexplained": tot.get("unexplained", 0.0), "months": months}
