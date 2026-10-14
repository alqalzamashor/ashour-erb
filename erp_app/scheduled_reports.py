"""التقارير المجدولة بالبريد: ملخص يومي/أسبوعي/شهري (مبيعات، مشتريات، مؤشرات المطعم، أعلى الأصناف، الخصومات والإلغاءات، حالة النسخ الاحتياطي)
بيتبعت لقايمة مستلمين مع ملف Excel. بيشتغل والبرنامج مفتوح (حلقة في main.py بتنادي run_due كل كام دقيقة)."""
import datetime
import json
import os
from html import escape

from sqlalchemy import func

from . import audit
from . import services
from .db import APP_DIR, PurchaseInvoice, SalesInvoice, get_session

CFG_PATH = os.path.join(APP_DIR, "scheduled_reports.json")
STATE_PATH = os.path.join(APP_DIR, "scheduled_reports_state.json")
WEEKDAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]   # مطابقة datetime.weekday()
DEFAULTS = {"enabled": False, "recipients": "", "daily": True, "weekly": False, "monthly": False, "time": "23:30", "weekday": 3, "attach_excel": True}
FREQ = {"daily": "يومي", "weekly": "أسبوعي", "monthly": "شهري"}
RETRY_MINUTES = 60


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        out = dict(default); out.update(d)
        return out
    except Exception:
        return dict(default)


def get_config():
    return _load(CFG_PATH, DEFAULTS)


def get_state():
    return _load(STATE_PATH, {"last_sent": {}, "last_attempt": {}, "last_error": "", "last_ok_at": ""})


def _save_state(st):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)


@audit.audited_config("إعدادات التقارير المجدولة")
def save_config(**kw):
    services.require_action("scheduled_reports", "edit")
    cfg = get_config()
    cfg.update({k: v for k, v in kw.items() if k in DEFAULTS})
    try:
        hh, mm = str(cfg["time"]).split(":"); assert 0 <= int(hh) < 24 and 0 <= int(mm) < 60
        cfg["time"] = f"{int(hh):02d}:{int(mm):02d}"
    except Exception:
        raise ValueError("الوقت بصيغة HH:MM مثل 23:30")
    mails = [x.strip() for x in str(cfg["recipients"]).replace(";", ",").replace("\n", ",").split(",") if x.strip()]
    bad = [m for m in mails if "@" not in m or "." not in m.split("@")[-1]]
    if bad:
        raise ValueError("بريد غير صحيح: " + bad[0])
    if cfg["enabled"] and not mails:
        raise ValueError("اكتب بريد مستلم واحد على الأقل")
    if cfg["enabled"] and not (cfg["daily"] or cfg["weekly"] or cfg["monthly"]):
        raise ValueError("اختر تقرير واحد على الأقل (يومي/أسبوعي/شهري)")
    cfg["recipients"] = ", ".join(mails); cfg["weekday"] = int(cfg["weekday"])
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)
    return cfg


def recipients(cfg=None):
    return [x.strip() for x in (cfg or get_config())["recipients"].split(",") if x.strip()]


# ---------------------------------------------------------------- المحتوى
def period_for(freq, now=None):
    now = now or datetime.datetime.now()
    t = now.date()
    if freq == "daily":
        return t, t, t.isoformat(), f"يوم {t:%Y-%m-%d}"
    if freq == "weekly":
        a = t - datetime.timedelta(days=6)
        return a, t, f"{t.isocalendar()[0]}-W{t.isocalendar()[1]:02d}", f"الأسبوع من {a:%Y-%m-%d} إلى {t:%Y-%m-%d}"
    first = t.replace(day=1); last = first - datetime.timedelta(days=1); a = last.replace(day=1)
    return a, last, f"{a:%Y-%m}", f"شهر {a:%Y-%m}"


def collect(date_from, date_to):
    from . import backup, discount_report, restaurant_stats
    d0, d1 = datetime.datetime.combine(date_from, datetime.time.min), datetime.datetime.combine(date_to, datetime.time.max)
    with get_session() as s:
        sq = s.query(func.count(SalesInvoice.id), func.coalesce(func.sum(SalesInvoice.total), 0.0), func.coalesce(func.sum(SalesInvoice.tax_total), 0.0)).filter(
            SalesInvoice.voided.is_(False), SalesInvoice.date >= d0, SalesInvoice.date <= d1).one()
        pq = s.query(func.count(PurchaseInvoice.id), func.coalesce(func.sum(PurchaseInvoice.total), 0.0)).filter(
            PurchaseInvoice.voided.is_(False), PurchaseInvoice.date >= d0, PurchaseInvoice.date <= d1).one()
        voided = s.query(func.count(SalesInvoice.id)).filter(SalesInvoice.voided.is_(True), SalesInvoice.date >= d0, SalesInvoice.date <= d1).scalar()
    r = restaurant_stats.dashboard(date_from, date_to)
    disc = discount_report.build_report(date_from, date_to)["kpis"]
    last = backup.last_backup_time()
    return {"sales": {"count": int(sq[0]), "total": float(sq[1]), "tax": float(sq[2]), "voided": int(voided or 0)},
            "purchases": {"count": int(pq[0]), "total": float(pq[1])}, "restaurant": r, "discounts": disc,
            "backup_hours": (datetime.datetime.now() - last).total_seconds() / 3600 if last else None}


def render(data, label):
    co = services.get_company_settings().name or ""
    s, p, r, d = data["sales"], data["purchases"], data["restaurant"], data["discounts"]; k = r["kpis"]
    rows = [("مبيعات (كل الفواتير)", f"{s['total']:,.2f}", f"{s['count']} فاتورة" + (f" - {s['voided']} ملغاة" if s["voided"] else "")), ("ضريبة المبيعات", f"{s['tax']:,.2f}", ""),
            ("مشتريات", f"{p['total']:,.2f}", f"{p['count']} فاتورة"), ("مبيعات المطعم", f"{k['sales']:,.2f}", f"{k['orders']} طلب - متوسط {k['avg_ticket']:,.2f}"),
            ("الخصومات", f"{d['total']:,.2f}", f"{d['count']} فاتورة ({d['avg_pct']}%)"), ("الإلغاءات والمرتجعات (المطعم)", f"{k['void_amount']:,.2f}", f"{k['void_count']} عملية")]
    if r["peak_hour"] is not None:
        rows.append(("ساعة الذروة", f"{r['peak_hour']:02d}:00", ""))
    text = f"{co} - ملخص {label}\n\n" + "\n".join(f"{a}: {b}  {c}".rstrip() for a, b, c in rows)
    if r["top_items"]:
        text += "\n\nأعلى الأصناف:\n" + "\n".join(f"- {n} × {q:g} = {v:,.2f}" for n, q, v in r["top_items"][:5])
    bk = data["backup_hours"]
    warn = bk is None or bk > 48
    text += f"\n\nالنسخ الاحتياطي: " + ("لا توجد نسخة!" if bk is None else f"آخر نسخة من {bk:.0f} ساعة")
    td = lambda x, st="": f'<td style="padding:6px 10px;border-bottom:1px solid #e5e7eb;{st}">{escape(str(x))}</td>'
    html = [f'<div dir="rtl" style="font-family:Tahoma,Arial,sans-serif;max-width:640px"><h2 style="color:#4f46e5;margin:0 0 4px">{escape(co)}</h2><div style="color:#6b7280;margin-bottom:14px">ملخص {escape(label)}</div>',
            '<table style="width:100%;border-collapse:collapse;font-size:14px">']
    for a, b, c in rows:
        html.append(f'<tr>{td(a)}{td(b, "font-weight:bold;text-align:left")}{td(c, "color:#6b7280")}</tr>')
    html.append("</table>")
    if r["top_items"]:
        html.append('<h3 style="margin:18px 0 6px">أعلى الأصناف</h3><table style="width:100%;border-collapse:collapse;font-size:14px">' +
                    "".join(f'<tr>{td(n)}{td(f"× {q:g}", "color:#6b7280")}{td(f"{v:,.2f}", "font-weight:bold;text-align:left")}</tr>' for n, q, v in r["top_items"][:5]) + "</table>")
    html.append(f'<p style="margin-top:16px;color:{"#dc2626" if warn else "#16a34a"}">النسخ الاحتياطي: ' + ("لا توجد نسخة!" if bk is None else f"آخر نسخة من {bk:.0f} ساعة") + "</p></div>")
    return text, "".join(html)


def send_report(freq, now=None, to=None):
    """يبني الملخص ويرسله فورًا. بيرجّع {'label','to'}. لو to اتبعت (اختبار) بيستخدمه بدل قايمة الإعدادات."""
    from .report_export import export_excel
    cfg = get_config()
    d0, d1, key, label = period_for(freq, now)
    data = collect(d0, d1)
    text, html = render(data, label)
    files = []
    if cfg["attach_excel"]:
        from . import restaurant_stats
        t, styles = restaurant_stats.export_table(data["restaurant"])
        files.append(export_excel({"table": t, "row_styles": styles, "col_weights": [3, 1.2, 1.6], "date_from": d0, "date_to": d1}, "restaurant_dashboard", services.downloads_dir()))
    to = to or recipients(cfg)
    services.send_email(to, f"[{services.get_company_settings().name or 'ERP'}] ملخص {label}", text, html, files)
    for f in files:
        try: os.remove(f)
        except OSError: pass
    return {"label": label, "to": to, "key": key}


def run_due(now=None):
    """بتتنادى دوريًا: لكل تقرير مفعّل حان وقته ولم يُرسل لفترته، يبعته. فشل الإرسال بيتسجّل ويتعاد بعد ساعة. بيرجّع قايمة النتائج."""
    cfg = get_config()
    if not cfg["enabled"] or not recipients(cfg):
        return []
    now = now or datetime.datetime.now()
    hh, mm = (int(x) for x in cfg["time"].split(":"))
    if (now.hour, now.minute) < (hh, mm):
        return []
    st = get_state(); out = []
    for freq in ("daily", "weekly", "monthly"):
        if not cfg[freq]:
            continue
        if freq == "weekly" and now.weekday() != int(cfg["weekday"]):
            continue
        if freq == "monthly" and now.day != 1:
            continue
        key = period_for(freq, now)[2]
        if st["last_sent"].get(freq) == key:
            continue
        la = st["last_attempt"].get(freq)
        if la and (now - datetime.datetime.fromisoformat(la)).total_seconds() < RETRY_MINUTES * 60:
            continue
        st["last_attempt"][freq] = now.isoformat(timespec="seconds")
        try:
            r = send_report(freq, now)
            st["last_sent"][freq] = key; st["last_error"] = ""; st["last_ok_at"] = now.isoformat(timespec="seconds")
            out.append({"freq": freq, "ok": True, "label": r["label"]})
        except Exception as ex:
            st["last_error"] = f"{FREQ[freq]}: {ex}"
            out.append({"freq": freq, "ok": False, "error": str(ex)})
        _save_state(st)
    return out
