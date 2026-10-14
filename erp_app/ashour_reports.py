"""تقارير عاشور: نقل موديول Ashour Reports (أودو) لبرنامجنا.

كل تقرير بيرجّع نفس الشكل عشان الشاشة والإكسل يستخدموا نفس الكود:
    {'title', 'subtitle', 'columns': [اسم العمود...], 'rows': [{'kind': 'row|section|total|grand|sub', 'cells': [...]}],
     'notes': [{'level','title','items'}]}
الخلية: رقم (يتنسّق في العرض) أو نص جاهز. None = «-».
"""
import datetime
import json
import os
import re
from collections import defaultdict

from .db import (APP_DIR, Account, Branch, BudgetLine, Customer, JournalEntry, JournalEntryLine, PurchaseInvoice,
                 PurchaseInvoiceItem, Product, Category, SalesInvoice, SalesInvoiceItem, SalesInvoicePayment,
                 SalesReturn, Supplier, get_session)

TOTAL = "__total__"
UNASSIGNED = "__unassigned__"
CONFIG_FILE = os.path.join(APP_DIR, "ashour_reports.json")

# ------------------------------------------------------------------ الإعدادات
# بنود قائمة الدخل الافتراضية مطابقة لشجرة حساباتنا (41 مبيعات، 42-44 إيرادات أخرى، 51 تكلفة، 52 مصروفات).
# الحساب بيروح للبند صاحب أطول بادئة مطابقة.
DEFAULT_LINES = [
    {"code": "sec_rev", "name": "الإيرادات", "type": "section"},
    {"code": "sales", "name": "إيرادات المبيعات", "type": "item", "prefixes": "41", "nature": "revenue", "role": "sales"},
    {"code": "other_income", "name": "إيرادات أخرى", "type": "item", "prefixes": "42,43,44", "nature": "revenue"},
    {"code": "income", "name": "إجمالي الإيرادات", "type": "total", "formula": "sales + other_income", "role": "income"},
    {"code": "sec_cost", "name": "التكاليف", "type": "section"},
    {"code": "cogs", "name": "تكلفة المبيعات / المواد الخام", "type": "item", "prefixes": "51", "nature": "cost", "role": "cogs"},
    {"code": "gross", "name": "مجمل الربح", "type": "total", "formula": "sales - cogs", "role": "gross"},
    {"code": "sec_fixed", "name": "المصروفات", "type": "section"},
    {"code": "staff", "name": "رواتب وبدلات العاملين", "type": "item", "prefixes": "52000,52001", "nature": "cost", "role": "staff"},
    {"code": "rent", "name": "الإيجارات", "type": "item", "prefixes": "520037,520038", "nature": "cost", "role": "rent"},
    {"code": "depreciation", "name": "الإهلاك", "type": "item", "prefixes": "520081", "nature": "cost", "role": "depreciation"},
    {"code": "opex", "name": "مصروفات تشغيلية وإدارية أخرى", "type": "item", "prefixes": "52", "nature": "cost", "role": "opex"},
    {"code": "total_cost", "name": "إجمالي التكاليف والمصروفات", "type": "total", "formula": "cogs + staff + rent + depreciation + opex", "role": "total_cost"},
    {"code": "net", "name": "صافي الربح", "type": "grand", "formula": "income - total_cost", "role": "net"},
]
DEFAULT_CONFIG = {"business_day_start": 0.0, "lines": DEFAULT_LINES, "head_office_branch_id": None}


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for k in ("business_day_start", "head_office_branch_id"):
            if k in data:
                cfg[k] = data[k]
        if data.get("lines"):
            cfg["lines"] = data["lines"]
    except Exception:
        pass
    return cfg


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_FILE) or ".", exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)


def reset_config():
    try:
        os.remove(CONFIG_FILE)
    except OSError:
        pass


TOKEN_RE = re.compile(r"\s*([+-])?\s*([A-Za-z_][A-Za-z0-9_]*)\s*")


def parse_formula(formula):
    """'income - cogs + x' -> [(1,'income'), (-1,'cogs'), (1,'x')]"""
    out, pos, text = [], 0, (formula or "").strip()
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m or m.end() == pos:
            raise ValueError(f"معادلة غير صحيحة: {text}")
        sign = -1 if m.group(1) == "-" else 1
        if out and m.group(1) is None:
            raise ValueError(f"معادلة غير صحيحة: {text}")
        out.append((sign, m.group(2)))
        pos = m.end()
    return out


def split_prefixes(text):
    return [p.strip() for p in (text or "").replace("،", ",").split(",") if p.strip()]


def validate_lines(lines):
    codes = [l["code"] for l in lines]
    if len(codes) != len(set(codes)):
        raise ValueError("كود بند مكرر")
    for l in lines:
        if l["type"] in ("total", "grand"):
            for _, c in parse_formula(l.get("formula")):
                if c not in codes:
                    raise ValueError(f"المعادلة في «{l['name']}» بتشير لبند مش موجود: {c}")


# ------------------------------------------------------------------ أدوات
def _day(v, end=False):
    if isinstance(v, datetime.datetime):
        v = v.date()
    if isinstance(v, str):
        v = datetime.datetime.strptime(v.strip()[:10], "%Y-%m-%d").date()
    if end:
        return datetime.datetime.combine(v, datetime.time.max)
    return datetime.datetime.combine(v, datetime.time.min)


def _date(v):
    return _day(v).date()


def _prev_year(d):
    try:
        return d.replace(year=d.year - 1)
    except ValueError:                      # 29 فبراير
        return d.replace(year=d.year - 1, day=28)


def _pct(cur, old):
    if not old:
        return None
    return (cur - old) / abs(old) * 100.0


def _pct_txt(v):
    return "-" if v is None else f"{v:+.1f}%"


def period_label(d1, d2):
    d1, d2 = _date(d1), _date(d2)
    return f"{d1:%d/%m/%Y} - {d2:%d/%m/%Y}" if d1 != d2 else f"{d1:%d/%m/%Y}"


def _branches():
    with get_session() as s:
        return [(b.id, b.name) for b in s.query(Branch).filter(Branch.is_active.is_(True)).order_by(Branch.code)]


def _empty(title, columns, subtitle=""):
    return {"title": title, "subtitle": subtitle, "columns": columns, "rows": [], "notes": []}


def _row(res, cells, kind="row"):
    res["rows"].append({"kind": kind, "cells": cells})


# ================================================================== 1) أرباح وخسائر الفروع
def _pnl_fetch(d_from, d_to):
    """[(account_code, account_name, branch_id|None, balance مدين-دائن)] للقيود المرحّلة على حسابات الإيراد والمصروف."""
    with get_session() as s:
        q = (s.query(Account.code, Account.name, JournalEntryLine.branch_id, JournalEntry.branch_id,
                     JournalEntryLine.debit, JournalEntryLine.credit)
             .select_from(JournalEntryLine)
             .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
             .join(Account, Account.id == JournalEntryLine.account_id)
             .filter(JournalEntry.posted.is_(True), Account.account_type.in_(("income", "expense")),
                     JournalEntry.date >= _day(d_from), JournalEntry.date <= _day(d_to, True)))
        agg = defaultdict(float)
        names = {}
        for code, name, lb, eb, dr, cr in q.all():
            agg[(code, lb or eb)] += (dr or 0.0) - (cr or 0.0)
            names[code] = name
    return [(c, names[c], b, v) for (c, b), v in agg.items()]


def _best(code, pmap):
    for prefix, line in pmap:
        if code.startswith(prefix):
            return line
    return None


def _pnl_period(lines, rows, branch_ids, allocate_weights=None):
    """-> values[bucket][line_code], unmapped[(code,name)]"""
    items = [l for l in lines if l["type"] == "item"]
    pmap = sorted(((p, l) for l in items for p in split_prefixes(l.get("prefixes"))), key=lambda t: -len(t[0]))
    values = defaultdict(lambda: defaultdict(float))
    unmapped = defaultdict(float)
    known = set(branch_ids)
    for code, name, bid, bal in rows:
        line = _best(code, pmap)
        if not line:
            unmapped[(code, name)] += bal
            continue
        sgn = -1 if line.get("nature") == "revenue" else 1
        bucket = bid if bid in known else UNASSIGNED
        values[bucket][line["code"]] += sgn * bal
    _fill(values, lines, branch_ids)
    return values, unmapped


def _fill(values, lines, branch_ids):
    item_codes = [l["code"] for l in lines if l["type"] == "item"]
    leaf = list(branch_ids) + [UNASSIGNED]
    values[TOTAL] = defaultdict(float, {c: sum(values[k].get(c, 0.0) for k in leaf if k in values) for c in item_codes})
    parsed = {l["code"]: parse_formula(l.get("formula")) for l in lines if l["type"] in ("total", "grand")}
    for bucket in list(values.keys()) + [b for b in leaf if b not in values]:
        row = values[bucket]
        for l in lines:                                     # الترتيب مهم: إجمالي ممكن يعتمد على إجمالي قبله
            if l["code"] in parsed:
                row[l["code"]] = sum(sg * row.get(c, 0.0) for sg, c in parsed[l["code"]])


def _budget(lines, d_from, d_to, branch_ids):
    """الميزانية التقديرية من شاشة الموازنات: كل سطر موزّع على أيام الفترة المتداخلة معاها."""
    items = [l for l in lines if l["type"] == "item"]
    pmap = sorted(((p, l) for l in items for p in split_prefixes(l.get("prefixes"))), key=lambda t: -len(t[0]))
    f, t = _day(d_from), _day(d_to, True)
    values = defaultdict(lambda: defaultdict(float))
    has = False
    known = set(branch_ids)
    with get_session() as s:
        q = (s.query(BudgetLine, Account.code).join(Account, Account.id == BudgetLine.account_id)
             .filter(BudgetLine.is_active.is_(True), BudgetLine.date_from <= t, BudgetLine.date_to >= f))
        for b, code in q.all():
            line = _best(code, pmap)
            if not line:
                continue
            span = max((b.date_to - b.date_from).days + 1, 1)
            ov = (min(b.date_to, t) - max(b.date_from, f)).days + 1
            amt = (b.budget_amount or 0.0) * max(ov, 0) / span
            bucket = b.branch_id if b.branch_id in known else UNASSIGNED
            values[bucket][line["code"]] += amt
            has = True
    if has:
        _fill(values, lines, branch_ids)
    return values, has


def pnl_compute(d_from, d_to, allocate=False):
    """allocate=True: بنود المركز الرئيسي (الفرع المحدد في الإعدادات) بتتوزع على باقي الفروع بنسبة إيراداتها."""
    cfg = load_config()
    lines = cfg["lines"]
    validate_lines(lines)
    branches = _branches()
    ids = [b[0] for b in branches]
    d_from, d_to = _date(d_from), _date(d_to)
    p_from, p_to = _prev_year(d_from), _prev_year(d_to)
    cur, un_c = _pnl_period(lines, _pnl_fetch(d_from, d_to), ids)
    prev, un_p = _pnl_period(lines, _pnl_fetch(p_from, p_to), ids)
    bud, has_bud = _budget(lines, d_from, d_to, ids)
    ho = cfg.get("head_office_branch_id")
    if allocate and ho in ids:
        for vals in (cur, prev, bud):
            if vals:
                _allocate_ho(vals, lines, ids, ho)
    keys = [b for b in ids] + ([UNASSIGNED] if any(abs(v) > 0.5 for v in list(cur[UNASSIGNED].values()) + list(prev[UNASSIGNED].values())) else []) + [TOTAL]
    names = dict(branches)
    names[UNASSIGNED] = "غير محدد فرع"
    names[TOTAL] = "إجمالي الشركة"
    # فرع بدون أي حركة في أي فترة مالوش لازمة يظهر
    keep = []
    for k in keys:
        if k == TOTAL or any(abs(x) > 0.005 for src in (cur, prev, bud) if k in src for x in src[k].values()):
            keep.append(k)
    res = {"lines": lines, "keys": keep, "names": names, "cur": cur, "prev": prev, "budget": bud, "has_budget": has_bud,
           "period": (d_from, d_to), "prev_period": (p_from, p_to), "ho": ho,
           "unmapped": _merge_unmapped(un_c, un_p), "allocated": bool(allocate and ho in ids)}
    res["ratios"] = _ratios(res)
    res["notes"] = _notes(res)
    return res


def _allocate_ho(values, lines, ids, ho):
    """توزيع مصروفات المركز الرئيسي على باقي الفروع بنسبة إيراداتها (الأوزان من بنود الإيراد)."""
    targets = [b for b in ids if b != ho]
    inc = next((l["code"] for l in lines if l.get("role") == "income"), None)
    w = {b: max(values[b].get(inc, 0.0), 0.0) for b in targets} if inc else {}
    tw = sum(w.values())
    if not tw:
        return
    for l in lines:
        if l["type"] != "item" or l.get("nature") != "cost":
            continue
        amt = values[ho].get(l["code"], 0.0)
        if not amt:
            continue
        values[ho][l["code"]] = 0.0
        for b in targets:
            values[b][l["code"]] += amt * w[b] / tw
    _fill(values, lines, ids)


def _merge_unmapped(c, p):
    out = defaultdict(lambda: [0.0, 0.0])
    for k, v in c.items():
        out[k][0] += v
    for k, v in p.items():
        out[k][1] += v
    return [{"code": k[0], "name": k[1], "cur": v[0], "prev": v[1]} for k, v in sorted(out.items()) if abs(v[0]) > 0.5 or abs(v[1]) > 0.5]


def _role(res, src, bucket, role):
    row = res[src].get(bucket, {})
    return sum(row.get(l["code"], 0.0) for l in res["lines"] if l.get("role") == role)


def _ratios(res):
    out = {}
    for k in res["keys"]:
        r = {}
        for tag in ("cur", "prev"):
            inc = _role(res, tag, k, "income")
            sales = _role(res, tag, k, "sales") or inc
            q = lambda a, base: (a / base * 100.0) if base else None   # noqa: E731
            r[tag] = {"income": inc, "sales": sales, "net": _role(res, tag, k, "net"),
                      "cogs_pct": q(_role(res, tag, k, "cogs"), sales), "staff_pct": q(_role(res, tag, k, "staff"), inc),
                      "opex_pct": q(_role(res, tag, k, "opex"), inc), "rent_pct": q(_role(res, tag, k, "rent"), inc),
                      "dep_pct": q(_role(res, tag, k, "depreciation"), inc), "gross_margin": q(_role(res, tag, k, "gross"), sales),
                      "net_margin": q(_role(res, tag, k, "net"), inc),
                      "pre_dep": _role(res, tag, k, "net") + _role(res, tag, k, "depreciation")}
        out[k] = r
    return out


def _notes(res):
    f = lambda v: f"{v:,.0f}"            # noqa: E731
    p = lambda v: "-" if v is None else f"{v:.1f}%"   # noqa: E731
    rt, nm = res["ratios"], res["names"]
    shops = [k for k in res["keys"] if k not in (TOTAL, UNASSIGNED) and k != res["ho"]]
    notes = []
    up = [(nm[k], rt[k]["prev"]["cogs_pct"], rt[k]["cur"]["cogs_pct"]) for k in shops
          if rt[k]["cur"]["cogs_pct"] is not None and rt[k]["prev"]["cogs_pct"] is not None
          and rt[k]["cur"]["cogs_pct"] - rt[k]["prev"]["cogs_pct"] >= 1.0]
    if up:
        one = (rt[TOTAL]["cur"]["sales"] or 0) / 100.0
        notes.append({"level": "urgent", "title": "نسبة تكلفة المبيعات زادت",
                      "text": f"كل نقطة زيادة على مستوى الشركة تساوي تقريبًا {f(one)} في الفترة.",
                      "items": [f"{n}: {p(b)} بدل {p(a)} ({b - a:+.1f} نقطة)" for n, a, b in up]})
    ranked = sorted((k for k in shops if rt[k]["cur"]["income"]), key=lambda k: rt[k]["cur"]["net"], reverse=True)
    win = [k for k in ranked if rt[k]["cur"]["net"] > 0][:3]
    if win:
        items = []
        for k in win:
            r = rt[k]
            g = _pct(r["cur"]["income"], r["prev"]["income"])
            items.append(f"{nm[k]}: صافي ربح {f(r['cur']['net'])}، الإيراد {'جديد' if g is None else f'{g:+.1f}%'}")
        notes.append({"level": "good", "title": "الفروع الرابحة", "text": "", "items": items})
    los = sorted((k for k in shops if rt[k]["cur"]["income"] and rt[k]["cur"]["net"] < 0), key=lambda k: rt[k]["cur"]["net"])
    if los:
        items = []
        for k in los:
            r = rt[k]["cur"]
            extra = []
            if r["pre_dep"] >= 0:
                extra.append(f"رابح قبل الإهلاك ({f(r['pre_dep'])})")
            if r["rent_pct"] and r["rent_pct"] > 15:
                extra.append(f"الإيجار {p(r['rent_pct'])} من الإيراد")
            if r["staff_pct"] and r["staff_pct"] > 30:
                extra.append(f"الرواتب {p(r['staff_pct'])} من الإيراد")
            items.append(f"{nm[k]}: {f(r['net'])}" + (" - " + "، ".join(extra) if extra else ""))
        notes.append({"level": "urgent", "title": "فروع خاسرة", "text": "", "items": items})
    drops = []
    for k in shops:
        g = _pct(rt[k]["cur"]["income"], rt[k]["prev"]["income"]) if rt[k]["prev"]["income"] and rt[k]["cur"]["income"] else None
        if g is not None and g <= -5:
            drops.append(f"{nm[k]}: {g:+.1f}%")
    if drops:
        notes.append({"level": "watch", "title": "الإيراد انخفض أكتر من 5% عن نفس الفترة السنة اللي فاتت", "text": "", "items": drops})
    dq = []
    if res["unmapped"]:
        dq.append(f"{len(res['unmapped'])} حساب مش مربوط بأي بند وبالتالي خارج القائمة (راجع تبويب «حسابات غير مربوطة»).")
    if UNASSIGNED in res["keys"]:
        dq.append("فيه قيود من غير فرع؛ ظاهرة في عمود «غير محدد فرع».")
    if dq:
        notes.append({"level": "info", "title": "مراجعة البيانات", "text": "", "items": dq})
    return notes


PNL_VIEWS = {"cur": "الفترة الحالية", "prev": "نفس الفترة السنة اللي فاتت", "budget": "الميزانية التقديرية",
             "var_prev": "التغيّر % عن السنة اللي فاتت", "var_budget": "الانحراف % عن الميزانية"}


def pnl_table(res, view="cur"):
    d1, d2 = res["period"]
    p1, p2 = res["prev_period"]
    sub = {"cur": period_label(d1, d2), "prev": period_label(p1, p2), "budget": period_label(d1, d2),
           "var_prev": f"{period_label(d1, d2)} مقابل {period_label(p1, p2)}", "var_budget": f"{period_label(d1, d2)} مقابل الميزانية"}[view]
    if res.get("allocated"):
        sub += " - بعد توزيع مصروفات المركز الرئيسي"
    out = _empty(f"أرباح وخسائر الفروع - {PNL_VIEWS[view]}", ["البند"] + [res["names"][k] for k in res["keys"]], sub)
    if view in ("budget", "var_budget") and not res["has_budget"]:
        out["notes"].append({"level": "info", "title": "مفيش ميزانية", "text": "أضف بنود في شاشة الموازنات (حسابات الإيراد/المصروف) عشان تظهر المقارنة.", "items": []})
    for l in res["lines"]:
        if l["type"] == "section":
            _row(out, [l["name"]] + [""] * len(res["keys"]), "section")
            continue
        cells = [l["name"]]
        for k in res["keys"]:
            c = res["cur"].get(k, {}).get(l["code"], 0.0)
            pv = res["prev"].get(k, {}).get(l["code"], 0.0)
            b = res["budget"].get(k, {}).get(l["code"]) if res["has_budget"] else None
            if view == "cur":
                cells.append(c)
            elif view == "prev":
                cells.append(pv)
            elif view == "budget":
                cells.append(b)
            elif view == "var_prev":
                cells.append(_pct_txt(_pct(c, pv)))
            else:
                cells.append(_pct_txt(_pct(c, b)) if b else "-")
        _row(out, cells, l["type"])
    out["notes"] = res["notes"] + out["notes"]
    return out


def pnl_ratios_table(res):
    out = _empty("النسب والمؤشرات", ["المؤشر"] + [res["names"][k] for k in res["keys"]],
                 period_label(*res["period"]) + " (الفترة الحالية | السنة اللي فاتت)")
    spec = [("نسبة تكلفة المبيعات", "cogs_pct"), ("هامش مجمل الربح", "gross_margin"), ("الرواتب من الإيراد", "staff_pct"),
            ("المصروفات التشغيلية من الإيراد", "opex_pct"), ("الإيجار من الإيراد", "rent_pct"), ("الإهلاك من الإيراد", "dep_pct"),
            ("هامش صافي الربح", "net_margin")]
    for label, key in spec:
        _row(out, [label] + [("-" if res["ratios"][k]["cur"][key] is None else f"{res['ratios'][k]['cur'][key]:.1f}%") +
                             " | " + ("-" if res["ratios"][k]["prev"][key] is None else f"{res['ratios'][k]['prev'][key]:.1f}%")
                             for k in res["keys"]])
    _row(out, ["الربح قبل الإهلاك"] + [res["ratios"][k]["cur"]["pre_dep"] for k in res["keys"]], "total")
    return out


def pnl_unmapped_table(res):
    out = _empty("حسابات غير مربوطة بأي بند", ["الكود", "الحساب", "الفترة الحالية", "السنة اللي فاتت"])
    for u in res["unmapped"]:
        _row(out, [u["code"], u["name"], u["cur"], u["prev"]])
    return out


# ================================================================== 2) مبيعات نقاط البيع
def _bday(dt, start_h):
    return (dt - datetime.timedelta(hours=start_h)).date()


def _hour_label(h):
    return f"{int(h) % 24:02d}:00"


def _sales_period(d_from, d_to, source, start_h):
    """يوم العمل D = من ساعة البداية يوم D لحد نفس الساعة يوم D+1."""
    f = _day(d_from) + datetime.timedelta(hours=start_h)
    t = _day(d_to) + datetime.timedelta(days=1, hours=start_h)
    data = {"invoices": [], "returns": [], "items": [], "pays": []}
    with get_session() as s:
        q = s.query(SalesInvoice).filter(SalesInvoice.voided.is_(False), SalesInvoice.date >= f, SalesInvoice.date < t)
        if source == "pos":
            q = q.filter(SalesInvoice.is_pos.is_(True))
        inv = q.all()
        ids = [i.id for i in inv]
        for i in inv:
            data["invoices"].append({"id": i.id, "b": i.branch_id, "dt": i.date, "total": i.total or 0.0, "tax": i.tax_total or 0.0})
        for st in range(0, len(ids), 500):
            chunk = ids[st:st + 500]
            for it in s.query(SalesInvoiceItem).filter(SalesInvoiceItem.invoice_id.in_(chunk)).all():
                data["items"].append({"inv": it.invoice_id, "pid": it.product_id, "qty": (it.quantity or 0.0) * (it.unit_factor or 1.0),
                                      "total": it.line_total or 0.0, "tax_rate": it.tax_rate or 0.0})
            for p in s.query(SalesInvoicePayment).filter(SalesInvoicePayment.invoice_id.in_(chunk)).all():
                data["pays"].append({"inv": p.invoice_id, "m": p.method_name or "غير محدد", "amount": p.amount or 0.0})
        rq = s.query(SalesReturn).filter(SalesReturn.date >= f, SalesReturn.date < t)
        if source == "pos":
            rq = rq.filter(SalesReturn.pos_terminal_id.isnot(None))
        for r in rq.all():
            data["returns"].append({"b": r.branch_id, "dt": r.date, "total": r.total or 0.0, "tax": r.tax_total or 0.0})
    return data


def _sales_branch_table(res_title, cur, cmp, names, start_h, cur_lab, cmp_lab):
    out = _empty(res_title, ["الفرع", "فواتير", "مرتجعات", "إجمالي المبيعات", "الصافي (بدون ضريبة)", "متوسط الفاتورة", "الكمية",
                             "فواتير (مقارنة)", "صافي (مقارنة)", "تغيّر الصافي %"], f"{cur_lab} مقابل {cmp_lab}")

    def agg(d):
        a = defaultdict(lambda: {"n": 0, "rn": 0, "total": 0.0, "net": 0.0, "rnet": 0.0, "qty": 0.0})
        inv_b = {}
        for i in d["invoices"]:
            x = a[i["b"]]
            x["n"] += 1
            x["total"] += i["total"]
            x["net"] += i["total"] - i["tax"]
            inv_b[i["id"]] = i["b"]
        for r in d["returns"]:
            x = a[r["b"]]
            x["rn"] += 1
            x["total"] -= r["total"]
            x["net"] -= r["total"] - r["tax"]
        for it in d["items"]:
            a[inv_b.get(it["inv"])]["qty"] += it["qty"]
        return a
    a, c = agg(cur), agg(cmp)
    keys = sorted(set(a) | set(c), key=lambda k: (k is None, names.get(k, "")))
    tot = defaultdict(float)
    for k in keys:
        x, y = a[k], c[k]
        n = names.get(k, "بدون فرع")
        _row(out, [n, x["n"], x["rn"], x["total"], x["net"], x["net"] / x["n"] if x["n"] else None, x["qty"], y["n"], y["net"], _pct_txt(_pct(x["net"], y["net"]))])
        for key, v in (("n", x["n"]), ("rn", x["rn"]), ("total", x["total"]), ("net", x["net"]), ("qty", x["qty"]), ("cn", y["n"]), ("cnet", y["net"])):
            tot[key] += v
    _row(out, ["الإجمالي", tot["n"], tot["rn"], tot["total"], tot["net"], tot["net"] / tot["n"] if tot["n"] else None, tot["qty"],
               tot["cn"], tot["cnet"], _pct_txt(_pct(tot["net"], tot["cnet"]))], "grand")
    return out


def pos_report(kind, d_from, d_to, c_from, c_to, source="pos", branch_id=None):
    """kind: branches | daily | hourly | products | payments"""
    start_h = float(load_config().get("business_day_start") or 0.0)
    names = dict(_branches())
    cur = _sales_period(d_from, d_to, source, start_h)
    cmp = _sales_period(c_from, c_to, source, start_h)
    if branch_id:
        for d in (cur, cmp):
            keep = {i["id"] for i in d["invoices"] if i["b"] == branch_id}
            d["invoices"] = [i for i in d["invoices"] if i["b"] == branch_id]
            d["returns"] = [r for r in d["returns"] if r["b"] == branch_id]
            d["items"] = [i for i in d["items"] if i["inv"] in keep]
            d["pays"] = [p for p in d["pays"] if p["inv"] in keep]
    cl, ml = period_label(d_from, d_to), period_label(c_from, c_to)
    if kind == "branches":
        return _sales_branch_table("مقارنة مبيعات الفروع", cur, cmp, names, start_h, cl, ml)
    if kind == "daily":
        out = _empty("المبيعات اليومية", ["يوم العمل", "فواتير", "الإجمالي", "الصافي", "متوسط الفاتورة", "مرتجعات (قيمة)"], cl)
        days = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
        for i in cur["invoices"]:
            x = days[_bday(i["dt"], start_h)]
            x[0] += 1
            x[1] += i["total"]
            x[2] += i["total"] - i["tax"]
        for r in cur["returns"]:
            x = days[_bday(r["dt"], start_h)]
            x[1] -= r["total"]
            x[2] -= r["total"] - r["tax"]
            x[3] += r["total"]
        t = [0, 0.0, 0.0, 0.0]
        for d in sorted(days):
            x = days[d]
            _row(out, [d.strftime("%Y-%m-%d"), x[0], x[1], x[2], x[2] / x[0] if x[0] else None, x[3]])
            t = [t[i] + x[i] for i in range(4)]
        _row(out, ["الإجمالي", t[0], t[1], t[2], t[2] / t[0] if t[0] else None, t[3]], "grand")
        return out
    if kind == "hourly":
        out = _empty("المبيعات بالساعة (بحسب ساعة بداية يوم العمل)", ["الساعة", "فواتير", "الإجمالي", "الصافي", "متوسط الفاتورة", "فواتير (مقارنة)", "صافي (مقارنة)", "تغيّر الصافي %"], f"{cl} مقابل {ml}")
        def hours(d):
            h = defaultdict(lambda: [0, 0.0, 0.0])
            for i in d["invoices"]:
                x = h[i["dt"].hour]
                x[0] += 1
                x[1] += i["total"]
                x[2] += i["total"] - i["tax"]
            return h
        a, c = hours(cur), hours(cmp)
        first = int(start_h)
        for k in range(24):
            hr = (first + k) % 24
            x, y = a[hr], c[hr]
            if not (x[0] or y[0]):
                continue
            _row(out, [_hour_label(hr), x[0], x[1], x[2], x[2] / x[0] if x[0] else None, y[0], y[2], _pct_txt(_pct(x[2], y[2]))])
        return out
    if kind == "products":
        out = _empty("مبيعات الأصناف", ["الصنف", "الفئة", "الكمية", "الصافي", "كمية (مقارنة)", "صافي (مقارنة)", "تغيّر الصافي %"], f"{cl} مقابل {ml}")
        with get_session() as s:
            pinfo = {p.id: (p.name, (p.category.name if getattr(p, "category", None) else "")) for p in s.query(Product).all()}
        def prods(d):
            p = defaultdict(lambda: [0.0, 0.0])
            for it in d["items"]:
                p[it["pid"]][0] += it["qty"]
                p[it["pid"]][1] += it["total"] / (1 + it["tax_rate"] / 100.0)
            return p
        a, c = prods(cur), prods(cmp)
        for pid in sorted(set(a) | set(c), key=lambda k: -(a[k][1] if k in a else 0)):
            x, y = a[pid], c[pid]
            nm, cat = pinfo.get(pid, (f"#{pid}", ""))
            _row(out, [nm, cat, x[0], x[1], y[0], y[1], _pct_txt(_pct(x[1], y[1]))])
        return out
    if kind == "payments":
        out = _empty("المبيعات حسب طريقة الدفع", ["طريقة الدفع", "المبلغ", "النسبة", "مبلغ (مقارنة)", "تغيّر %"], f"{cl} مقابل {ml}")
        def pays(d):
            m = defaultdict(float)
            for p in d["pays"]:
                m[p["m"]] += p["amount"]
            return m
        a, c = pays(cur), pays(cmp)
        tot = sum(a.values())
        for m in sorted(set(a) | set(c), key=lambda k: -a[k]):
            _row(out, [m, a[m], f"{a[m] / tot * 100:.1f}%" if tot else "-", c[m], _pct_txt(_pct(a[m], c[m]))])
        _row(out, ["الإجمالي", tot, "100%" if tot else "-", sum(c.values()), _pct_txt(_pct(tot, sum(c.values())))], "grand")
        return out
    raise ValueError(kind)


def pos_pivot(d_from, d_to, gran="month", source="pos"):
    """فرع > صنف × (سنة/شهر/يوم)"""
    start_h = float(load_config().get("business_day_start") or 0.0)
    names = dict(_branches())
    d = _sales_period(d_from, d_to, source, start_h)
    inv = {i["id"]: i for i in d["invoices"]}

    def key(dt):
        b = _bday(dt, start_h)
        return {"year": f"{b.year}", "month": f"{b:%Y-%m}", "day": f"{b:%Y-%m-%d}", "total": "الإجمالي"}[gran]
    cols = sorted({key(i["dt"]) for i in d["invoices"]})
    with get_session() as s:
        pn = {p.id: p.name for p in s.query(Product).all()}
    out = _empty("جدول مبيعات الأصناف حسب الفرع", ["الفرع", "الصنف"] + cols + ["الإجمالي"], period_label(d_from, d_to) + " (الصافي بدون ضريبة)")
    tab = defaultdict(lambda: defaultdict(float))
    for it in d["items"]:
        i = inv[it["inv"]]
        tab[(i["b"], it["pid"])][key(i["dt"])] += it["total"] / (1 + it["tax_rate"] / 100.0)
    for (b, pid) in sorted(tab, key=lambda k: (names.get(k[0], "~"), -sum(tab[k].values()))):
        v = tab[(b, pid)]
        _row(out, [names.get(b, "بدون فرع"), pn.get(pid, f"#{pid}")] + [v.get(c, 0.0) for c in cols] + [sum(v.values())])
    return out


# ================================================================== 3) المشتريات
def _purchase_lines(d_from, d_to, supplier_id=None, category_id=None):
    out = []
    with get_session() as s:
        q = (s.query(PurchaseInvoice.date, PurchaseInvoice.id, PurchaseInvoice.supplier_id, PurchaseInvoice.number,
                     PurchaseInvoiceItem.product_id, PurchaseInvoiceItem.quantity, PurchaseInvoiceItem.unit_factor,
                     PurchaseInvoiceItem.line_total, PurchaseInvoiceItem.tax_rate)
             .join(PurchaseInvoiceItem, PurchaseInvoiceItem.invoice_id == PurchaseInvoice.id)
             .filter(PurchaseInvoice.voided.is_(False), PurchaseInvoice.date >= _day(d_from), PurchaseInvoice.date <= _day(d_to, True)))
        if supplier_id:
            q = q.filter(PurchaseInvoice.supplier_id == supplier_id)
        for dt, iid, sid, num, pid, qty, fac, lt, tr in q.all():
            qty_b = (qty or 0.0) * (fac or 1.0)
            net = (lt or 0.0) / (1 + (tr or 0.0) / 100.0)
            out.append({"dt": dt, "inv": iid, "sid": sid, "num": num, "pid": pid, "qty": qty_b, "net": net})
        pinfo = {p.id: (p.name, p.unit or "", p.category_id) for p in s.query(Product).all()}
        cats = {c.id: c.name for c in s.query(Category).all()}
        snames = {x.id: x.name for x in s.query(Supplier).all()}
    if category_id:
        out = [l for l in out if pinfo.get(l["pid"], ("", "", None))[2] == category_id]
    return out, pinfo, cats, snames


def purchases_report(kind, d_from, d_to, c_from, c_to, supplier_id=None, category_id=None):
    """kind: compare | vendors | price_changes | ledger"""
    cl, ml = period_label(d_from, d_to), period_label(c_from, c_to)
    if kind == "compare":
        cur, pinfo, cats, sn = _purchase_lines(d_from, d_to, supplier_id, category_id)
        cmp, _a, _b, _c = _purchase_lines(c_from, c_to, supplier_id, category_id)
        out = _empty("مقارنة المشتريات", ["الفئة", "الصنف", "الوحدة", "الكمية", "القيمة", "متوسط السعر", "كمية (مقارنة)", "قيمة (مقارنة)", "متوسط سعر (مقارنة)", "تغيّر السعر %", "تغيّر القيمة %"], f"{cl} مقابل {ml}")
        def agg(ls):
            a = defaultdict(lambda: [0.0, 0.0])
            for l in ls:
                a[l["pid"]][0] += l["qty"]
                a[l["pid"]][1] += l["net"]
            return a
        a, c = agg(cur), agg(cmp)
        bycat = defaultdict(list)
        for pid in set(a) | set(c):
            nm, un, cid = pinfo.get(pid, (f"#{pid}", "", None))
            bycat[cats.get(cid, "بدون فئة")].append((nm, un, a[pid], c[pid]))
        gt = [0.0, 0.0, 0.0, 0.0]
        for cat in sorted(bycat):
            items = sorted(bycat[cat], key=lambda r: -r[2][1])
            sq = sum(i[2][0] for i in items); sv = sum(i[2][1] for i in items)
            cq = sum(i[3][0] for i in items); cv = sum(i[3][1] for i in items)
            _row(out, [cat, f"({len(items)} صنف)", "", sq, sv, None, cq, cv, None, "", _pct_txt(_pct(sv, cv))], "section")
            gt = [gt[0] + sq, gt[1] + sv, gt[2] + cq, gt[3] + cv]
            for nm, un, x, y in items:
                px = x[1] / x[0] if x[0] else None
                py = y[1] / y[0] if y[0] else None
                _row(out, ["", nm, un, x[0], x[1], px, y[0], y[1], py, _pct_txt(_pct(px, py) if px and py else None), _pct_txt(_pct(x[1], y[1]))])
        _row(out, ["الإجمالي", "", "", gt[0], gt[1], None, gt[2], gt[3], None, "", _pct_txt(_pct(gt[1], gt[3]))], "grand")
        return out
    if kind == "vendors":
        cur, pinfo, cats, sn = _purchase_lines(d_from, d_to, None, category_id)
        out = _empty("مقارنة الموردين (أحسن سعر)", ["الصنف", "الوحدة", "أرخص مورد", "أرخص سعر", "أغلى مورد", "أغلى سعر", "الفرق %", "عدد الموردين", "تفاصيل الأسعار"], cl)
        pv = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
        for l in cur:
            pv[l["pid"]][l["sid"]][0] += l["qty"]
            pv[l["pid"]][l["sid"]][1] += l["net"]
        rows = []
        for pid, sup in pv.items():
            prices = {sid: v[1] / v[0] for sid, v in sup.items() if v[0] > 0}
            if len(prices) < 1:
                continue
            lo = min(prices, key=prices.get); hi = max(prices, key=prices.get)
            nm, un, _c = pinfo.get(pid, (f"#{pid}", "", None))
            diff = _pct(prices[hi], prices[lo]) if len(prices) > 1 else None
            det = "، ".join(f"{sn.get(s_, 'بدون مورد')}: {p:,.2f}" for s_, p in sorted(prices.items(), key=lambda t: t[1]))
            rows.append((diff or 0, [nm, un, sn.get(lo, "بدون مورد"), prices[lo], sn.get(hi, "بدون مورد") if len(prices) > 1 else "-",
                                      prices[hi] if len(prices) > 1 else None, _pct_txt(diff), len(prices), det]))
        for _, cells in sorted(rows, key=lambda r: -r[0]):
            _row(out, cells)
        return out
    if kind == "price_changes":
        cur, pinfo, cats, sn = _purchase_lines(d_from, d_to, supplier_id, category_id)
        out = _empty("تغيّر أسعار الشراء", ["الصنف", "المورد", "تاريخ آخر شراء", "آخر سعر", "تاريخ الشراء السابق", "السعر السابق", "التغيّر %"], cl + " (آخر فاتورتين لكل صنف/مورد)")
        by = defaultdict(list)
        for l in cur:
            if l["qty"] > 0:
                by[(l["pid"], l["sid"])].append(l)
        rows = []
        for (pid, sid), ls in by.items():
            ls.sort(key=lambda l: (l["dt"], l["inv"]))
            if len(ls) < 2:
                continue
            a, b = ls[-2], ls[-1]
            pa, pb = a["net"] / a["qty"], b["net"] / b["qty"]
            ch = _pct(pb, pa)
            rows.append((abs(ch or 0), [pinfo.get(pid, (f"#{pid}",))[0], sn.get(sid, "بدون مورد"), b["dt"].strftime("%Y-%m-%d"), pb,
                                         a["dt"].strftime("%Y-%m-%d"), pa, _pct_txt(ch)]))
        for _, cells in sorted(rows, key=lambda r: -r[0]):
            _row(out, cells)
        return out
    if kind == "ledger":
        return party_ledger("supplier", d_from, d_to)
    raise ValueError(kind)


# ================================================================== 4) أرصدة العملاء / الموردين
def party_ledger(ptype, d_from, d_to, only_active=True):
    """كشف تجميعي: رصيد أول المدة + (مبيعات|مشتريات) + (تحصيلات|مدفوعات) = رصيد آخر المدة، من القيود المرحّلة على الطرف."""
    is_c = ptype == "customer"
    f, t = _day(d_from), _day(d_to, True)
    op, dr, cr = defaultdict(float), defaultdict(float), defaultdict(float)
    with get_session() as s:
        q = (s.query(JournalEntryLine.partner_id, JournalEntry.date, JournalEntryLine.debit, JournalEntryLine.credit)
             .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
             .filter(JournalEntry.posted.is_(True), JournalEntryLine.partner_type == ptype,
                     JournalEntryLine.partner_id.isnot(None), JournalEntry.date <= t))
        for pid, dt, d, c in q.all():
            if dt < f:
                op[pid] += ((d or 0.0) - (c or 0.0)) * (1 if is_c else -1)
            else:
                dr[pid] += d or 0.0
                cr[pid] += c or 0.0
        model = Customer if is_c else Supplier
        names = {x.id: x.name for x in s.query(model).all()}
    ids = set(op) | set(dr) | set(cr)
    title = "أرصدة العملاء والتحصيلات" if is_c else "كشف حساب الموردين"
    cols = ["العميل" if is_c else "المورد", "رصيد أول المدة", "مبيعات (مدين)" if is_c else "مشتريات (دائن)",
            "تحصيلات (دائن)" if is_c else "مدفوعات (مدين)", "رصيد آخر المدة"] + (["نسبة التحصيل %"] if is_c else [])
    out = _empty(title, cols, period_label(d_from, d_to))
    tot = [0.0, 0.0, 0.0, 0.0]
    rows = []
    for pid in ids:
        o = op[pid]
        inc = dr[pid] if is_c else cr[pid]          # مبيعات | مشتريات
        pay = cr[pid] if is_c else dr[pid]          # تحصيلات | مدفوعات
        bal = o + inc - pay
        if only_active and all(abs(x) < 0.005 for x in (o, inc, pay, bal)):
            continue
        rows.append((bal, [names.get(pid, f"#{pid}"), o, inc, pay, bal] + ([f"{pay / (o + inc) * 100:.0f}%" if (o + inc) > 0 else "-"] if is_c else [])))
        tot = [tot[0] + o, tot[1] + inc, tot[2] + pay, tot[3] + bal]
    for _, cells in sorted(rows, key=lambda r: -abs(r[0])):
        _row(out, cells)
    _row(out, ["الإجمالي"] + tot + ([f"{tot[2] / (tot[0] + tot[1]) * 100:.0f}%" if (tot[0] + tot[1]) > 0 else "-"] if is_c else []), "grand")
    return out


def customers_report(kind, d_from, d_to):
    if kind == "balances":
        return party_ledger("customer", d_from, d_to)
    if kind == "top":
        out = _empty("أكبر العملاء مبيعًا", ["العميل", "فواتير", "الصافي (بدون ضريبة)", "الإجمالي", "متوسط الفاتورة"], period_label(d_from, d_to))
        with get_session() as s:
            q = s.query(SalesInvoice).filter(SalesInvoice.voided.is_(False), SalesInvoice.customer_id.isnot(None),
                                             SalesInvoice.date >= _day(d_from), SalesInvoice.date <= _day(d_to, True)).all()
            names = {c.id: c.name for c in s.query(Customer).all()}
            agg = defaultdict(lambda: [0, 0.0, 0.0])
            for i in q:
                x = agg[i.customer_id]
                x[0] += 1
                x[1] += (i.total or 0.0) - (i.tax_total or 0.0)
                x[2] += i.total or 0.0
        for cid, x in sorted(agg.items(), key=lambda t: -t[1][1]):
            _row(out, [names.get(cid, f"#{cid}"), x[0], x[1], x[2], x[2] / x[0]])
        return out
    raise ValueError(kind)


# ================================================================== تصدير Excel
def export_xlsx(report, path, company_name="", lang="ar"):
    from openpyxl import Workbook
    from .i18n import tr
    T = lambda v: tr(v, lang) if isinstance(v, str) else v    # noqa: E731  (الترجمة للإنجليزي لو المستخدم على EN)
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = (T(report["title"]) or "Report")[:31].replace("/", "-")
    ws.sheet_view.rightToLeft = lang != "en"
    r = 1
    if company_name:
        ws.cell(r, 1, company_name).font = Font(bold=True, size=13)
        r += 1
    ws.cell(r, 1, T(report["title"])).font = Font(bold=True, size=14)
    r += 1
    if report.get("subtitle"):
        ws.cell(r, 1, T(report["subtitle"]))
        r += 1
    r += 1
    head_fill = PatternFill("solid", fgColor="1F4E78")
    for j, c in enumerate(report["columns"], 1):
        cell = ws.cell(r, j, T(c))
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = ws.cell(r + 1, 2)
    r += 1
    fills = {"section": "DDEBF7", "total": "F2F2F2", "grand": "FFF2CC"}
    for row in report["rows"]:
        for j, v in enumerate(row["cells"], 1):
            cell = ws.cell(r, j, T(v) if v is not None else "-")
            if isinstance(v, float):
                cell.number_format = '#,##0.00;[Red]-#,##0.00'
            if row["kind"] in fills:
                cell.fill = PatternFill("solid", fgColor=fills[row["kind"]])
                cell.font = Font(bold=True)
        r += 1
    for n in report.get("notes", []):
        r += 1
        ws.cell(r, 1, T(n["title"])).font = Font(bold=True)
        for it in n.get("items", []) or ([n["text"]] if n.get("text") else []):
            r += 1
            ws.cell(r, 1, "• " + T(it))
    ws.column_dimensions["A"].width = 34
    for j in range(2, len(report["columns"]) + 1):
        ws.column_dimensions[ws.cell(1, j).column_letter].width = 18
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    wb.save(path)
    return path
