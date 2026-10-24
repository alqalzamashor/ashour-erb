"""تقرير مطابقة الحسابات: بيطابق كشف خارجي (كشف البنك أو كشف المورد، Excel/CSV) مع الدفتر ويطلّع الفروقات.

الفكرة: كل حركة (في الكشف أو الدفتر) بتتحوّل لرقم واحد بإشارة = أثرها على رصيد الحساب في اتجاهه الطبيعي:
  - حساب بنك/نقدية (أصل): الإيداع +، السحب -   (الدفتر: مدين - دائن | الكشف: عمود دائن/إيداع - عمود مدين/سحب)
  - مورد (التزام):         الفاتورة +، السداد -   (الدفتر: دائن - مدين | الكشف من دفتر المورد: عمود مدين - عمود دائن)
وده بيخلّي المطابقة قاعدة واحدة (نفس المبلغ بنفس الإشارة). لو كشف جهة عكس الاتجاه ده فيه خيار "عكس الاتجاه".

التقرير مؤقت: مبيحفظش حاجة في قاعدة البيانات (عكس شاشة الربط البنكي اللي بتخزّن سطور الكشف وبتعمل قيود).

ترتيب المطابقة (واحد لواحد):
  1) نفس المبلغ + تاريخ متقارب (الفرق ≤ عدد الأيام المسموح) أو نفس المرجع/رقم المستند            → مطابق (أو مطابق بفارق تاريخ)
  2) نفس المرجع/رقم المستند بمبلغ مختلف                                                           → اختلاف في المبلغ
  3) نفس المبلغ وتاريخ بعيد (لحد 120 يوم)                                                          → مطابق بفارق تاريخ
  الباقي: في الكشف فقط (غير مسجّل عندنا) / في الدفتر فقط (غير موجود في الكشف)
"""
import datetime
import re

from . import services
from .banking import _num, _date, _read_rows
from .db import get_session, JournalEntry, JournalEntryLine, Supplier, Account

KINDS = {"account": "حساب بنك / نقدية", "supplier": "مورد"}

_HDR = {
    "date": ("date", "تاريخ", "التاريخ", "value date", "posting date", "doc date", "تاريخ المستند", "تاريخ الحركة"),
    "description": ("description", "details", "narrative", "البيان", "التفاصيل", "الوصف", "بيان", "note", "ملاحظات", "remarks"),
    "reference": ("reference", "ref", "المرجع", "رقم المرجع", "رقم العملية", "cheque", "الشيك", "invoice", "رقم الفاتورة", "document", "doc no",
                  "voucher", "رقم المستند", "رقم السند", "السند", "رقم الشيك"),
    "debit": ("debit", "withdrawal", "withdrawals", "مدين", "سحب", "مسحوبات", "المدين"),
    "credit": ("credit", "deposit", "deposits", "دائن", "إيداع", "ايداع", "مودعات", "الدائن"),
    "amount": ("amount", "المبلغ", "قيمة"),
    "balance": ("balance", "الرصيد", "رصيد"),
}
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
MAX_DATE_GAP = 120          # أقصى فرق تاريخ نقبله لنفس المبلغ من غير مرجع مشترك


def _tokens(*parts):
    """كلمات/أرقام مميّزة من المرجع والبيان (للمطابقة بالمرجع): بنشيل الأصفار من أول الأرقام (JE-000045 ~ 45)."""
    return _tok_pair(*parts)[0]


def _tok_pair(*parts):
    """(كل الرموز، الرموز القوية): القوي = الرمز الأصلي 5 خانات أو أكتر (CHQ1001، 000044، TRF77001) فبيعتمد عليه في مطابقة المرجع بمبلغ مختلف."""
    allt, strong = set(), set()
    for raw in re.findall(r"[A-Za-z0-9]{2,}", " ".join(str(p or "") for p in parts).translate(_DIGITS).upper()):
        t = raw.lstrip("0") if raw.isdigit() else raw
        if len(t) >= 3 or (t.isdigit() and len(t) >= 2):
            allt.add(t)
            if len(raw) >= 5:
                strong.add(t)
    return allt, strong


def _day(d):
    if isinstance(d, str):
        d = datetime.datetime.strptime(d.strip()[:10], "%Y-%m-%d")
    return d.date() if isinstance(d, datetime.datetime) else d


def _gap(a, b):
    return abs((_day(a) - _day(b)).days)


# ------------------------------------------------------------------ قراءة الكشف
def parse_statement(path, kind="account", flip=False):
    """يقرا كشف الجهة الخارجية (CSV/Excel) ويرجّع {lines, closing, opening, min_date, max_date, skipped}.
    كل سطر: date, description, reference, amount (بإشارة الأثر على رصيدنا - شوف أول الملف), balance, row (رقم السطر في الملف)."""
    rows = _read_rows(path)
    hdr_i, cols = None, {}
    for i, r in enumerate(rows[:40]):
        found = {}
        for j, c in enumerate(r):
            t = str(c or "").strip().lower()
            if not t or j in found.values():
                continue
            for key, names in _HDR.items():
                if key not in found and any(t == n.lower() or t.startswith(n.lower()) for n in names):
                    found[key] = j
                    break
        if "date" in found and ("debit" in found or "credit" in found or "amount" in found):
            hdr_i, cols = i, found
            break
    if hdr_i is None:
        raise ValueError("مش لاقي عناوين الأعمدة في الملف (لازم عمود تاريخ + مدين/دائن أو مبلغ) - راجع ملف الكشف")
    lines, skipped = [], 0
    for n, r in enumerate(rows[hdr_i + 1:], start=hdr_i + 2):
        g = lambda k: r[cols[k]] if k in cols and cols[k] < len(r) else None
        d = _date(g("date"))
        if not d:
            skipped += 1
            continue
        if "debit" in cols or "credit" in cols:
            dr, cr = abs(_num(g("debit"))), abs(_num(g("credit")))
            eff = (cr - dr) if kind == "account" else (dr - cr)
        else:
            eff = _num(g("amount"))
        if flip:
            eff = -eff
        if abs(eff) < 0.005:
            skipped += 1
            continue
        bal = g("balance")
        bal = (-_num(bal) if flip else _num(bal)) if bal not in (None, "") else None
        lines.append({"date": d, "description": str(g("description") or "").strip()[:300], "reference": str(g("reference") or "").strip()[:100],
                      "amount": round(eff, 2), "balance": bal, "row": n})
    if not lines:
        raise ValueError("الملف مفيهوش حركات (تأكد من الأعمدة والتواريخ)")
    first, last = lines[0]["date"], lines[-1]["date"]
    ordered = lines if first <= last else lines[::-1]            # كشف تنازلي (الأحدث فوق): نقلبه عشان آخر رصيد يبقى الأخير
    with_bal = [l for l in sorted(ordered, key=lambda x: x["date"]) if l["balance"] is not None]
    closing = with_bal[-1]["balance"] if with_bal else None
    return {"lines": lines, "closing": closing, "min_date": min(l["date"] for l in lines), "max_date": max(l["date"] for l in lines), "skipped": skipped,
            "total": round(sum(l["amount"] for l in lines), 2)}


# ------------------------------------------------------------------ سطور الدفتر
def book_balance(kind, ref_id, as_of):
    """رصيد الحساب في الدفتر (باتجاهه الطبيعي) لحد نهاية يوم as_of."""
    return book_lines(kind, ref_id, None, as_of)["closing"]


def book_lines(kind, ref_id, date_from=None, date_to=None):
    """حركات الدفتر للحساب/المورد في الفترة + الرصيد الافتتاحي والختامي. كل حركة: id, date, number, reference, description, amount."""
    df = services._dt_start(_day(date_from)) if date_from else None
    dt = services._dt_end(_day(date_to)) if date_to else None
    if kind == "supplier":
        st = services.party_statement("supplier", int(ref_id), df, dt)
        out = []
        for i, r in enumerate(st["rows"]):
            if not r.get("number") and r.get("description") == "الرصيد الافتتاحي":
                continue
            out.append({"id": f"S{i}", "date": r["date"], "number": r.get("number") or "", "reference": "", "description": r.get("description") or "",
                        "amount": round(float(r["credit"] or 0) - float(r["debit"] or 0), 2)})
        return {"lines": out, "opening": round(float(st["opening"] or 0), 2), "closing": round(float(st["closing"] or 0), 2)}
    allowed = services.user_branch_ids()
    with get_session() as s:
        q = (s.query(JournalEntryLine, JournalEntry).join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
             .filter(JournalEntryLine.account_id == int(ref_id), JournalEntry.posted.is_(True)))
        if allowed:
            q = q.filter((JournalEntryLine.branch_id.is_(None)) | (JournalEntryLine.branch_id.in_(allowed)))
        opening, out = 0.0, []
        for l, e in q.order_by(JournalEntry.date, JournalEntry.id, JournalEntryLine.id).all():
            amt = float(l.debit or 0) - float(l.credit or 0)
            if df and e.date < df:
                opening += amt
            elif dt and e.date > dt:
                continue
            else:
                out.append({"id": f"J{l.id}", "date": e.date, "number": e.number, "reference": e.reference or "",
                            "description": (l.description or e.description or "")[:300], "amount": round(amt, 2)})
        closing = opening + sum(x["amount"] for x in out)
        return {"lines": out, "opening": round(opening, 2), "closing": round(closing, 2)}


# ------------------------------------------------------------------ المطابقة
def reconcile(stmt_lines, book_lines_, window=5, period=None):
    """يطابق سطور الكشف مع سطور الدفتر. period=(من, إلى): سطور الدفتر خارجها بتتحط في "outside" ومبتحسبش فروقات.
    بيرجّع {matched, date_diff, amount_diff (أزواج (كشف، دفتر))، stmt_only, book_only, outside (قوايم)، summary}."""
    window = max(0, int(window or 0))
    S, B_all = [], []
    for i, s in enumerate(stmt_lines):
        t, st_ = _tok_pair(s.get("reference"), s.get("description"))
        S.append(dict(s, _i=i, _t=t, _st=st_))
    for i, b in enumerate(book_lines_):
        t, st_ = _tok_pair(b.get("number"), b.get("reference"), b.get("description"))
        B_all.append(dict(b, _i=i, _t=t, _st=st_))
    outside = []
    if period:
        lo, hi = _day(period[0]), _day(period[1])
        B = [b for b in B_all if lo <= _day(b["date"]) <= hi]
        outside = [b for b in B_all if not (lo <= _day(b["date"]) <= hi)]
    else:
        B = B_all
    free_s, free_b = {s["_i"] for s in S}, {b["_i"] for b in B}
    bs, bb = {s["_i"]: s for s in S}, {b["_i"]: b for b in B}
    by_amt = {}
    for b in B:
        by_amt.setdefault(round(b["amount"] * 100), []).append(b)
    matched, date_diff, amount_diff = [], [], []

    def take(si, bi, bucket):
        free_s.discard(si); free_b.discard(bi); bucket.append((bs[si], bb[bi]))

    # 1) نفس المبلغ: (مرجع مشترك، أو تاريخ ≤ المهلة) - الأفضل أولًا
    cand = []
    for s in S:
        for b in by_amt.get(round(s["amount"] * 100), [])[:400]:
            ov = len(s["_st"] & b["_t"]) or len(s["_t"] & b["_st"]) or len(s["_t"] & b["_t"]) // 2
            gap = _gap(s["date"], b["date"])
            if gap <= window or ov:
                cand.append((-ov, gap, s["_i"], b["_i"]))
    for _, gap, si, bi in sorted(cand):
        if si in free_s and bi in free_b:
            take(si, bi, matched if gap <= window else date_diff)
    # 2) نفس المرجع القوي بمبلغ مختلف
    cand = []
    for si in free_s:
        s = bs[si]
        if not s["_st"]:
            continue
        for bi in free_b:
            ov = len(s["_st"] & bb[bi]["_t"]) + len(s["_t"] & bb[bi]["_st"])
            if ov:
                cand.append((-ov, _gap(s["date"], bb[bi]["date"]), si, bi))
    for _, _, si, bi in sorted(cand):
        if si in free_s and bi in free_b:
            take(si, bi, amount_diff)
    # 3) نفس المبلغ بتاريخ بعيد
    cand = []
    for si in free_s:
        s = bs[si]
        for b in by_amt.get(round(s["amount"] * 100), [])[:400]:
            if b["_i"] in free_b:
                gap = _gap(s["date"], b["date"])
                if gap <= MAX_DATE_GAP:
                    cand.append((gap, si, b["_i"]))
    for _, si, bi in sorted(cand):
        if si in free_s and bi in free_b:
            take(si, bi, date_diff)
    stmt_only = sorted((bs[i] for i in free_s), key=lambda x: (x["date"], x["_i"]))
    book_only = sorted((bb[i] for i in free_b), key=lambda x: (x["date"], x["_i"]))
    for lst in (matched, date_diff, amount_diff):
        lst.sort(key=lambda p: (p[0]["date"], p[0]["_i"]))
    r2 = lambda v: round(v, 2)
    stmt_total = r2(sum(s["amount"] for s in S))
    book_total = r2(sum(b["amount"] for b in B))
    so, bo = r2(sum(s["amount"] for s in stmt_only)), r2(sum(b["amount"] for b in book_only))
    ad = r2(sum(s["amount"] - b["amount"] for s, b in amount_diff))
    summary = {"stmt_count": len(S), "book_count": len(B), "matched": len(matched), "date_diff": len(date_diff), "amount_diff": len(amount_diff),
               "stmt_only": len(stmt_only), "book_only": len(book_only), "outside": len(outside),
               "stmt_total": stmt_total, "book_total": book_total, "period_diff": r2(stmt_total - book_total),
               "stmt_only_sum": so, "book_only_sum": bo, "amount_diff_sum": ad,
               "unexplained": r2(stmt_total - book_total - (so - bo + ad))}
    return {"matched": matched, "date_diff": date_diff, "amount_diff": amount_diff, "stmt_only": stmt_only, "book_only": book_only, "outside": outside, "summary": summary}


# ------------------------------------------------------------------ التقرير الكامل
def build_report(kind, ref_id, path, window=5, flip=False, closing_override=None, date_from=None, date_to=None):
    """التقرير كله: قراءة الكشف + الدفتر + المطابقة + الأرصدة. closing_override = رصيد الكشف الختامي لو الملف مفيهوش عمود رصيد."""
    if kind not in KINDS:
        raise ValueError("نوع غير مدعوم")
    st = parse_statement(path, kind, flip)
    lines = st["lines"]
    lo, hi = _day(date_from) if date_from else _day(st["min_date"]), _day(date_to) if date_to else _day(st["max_date"])
    if lo > hi:
        raise ValueError("تاريخ البداية بعد تاريخ النهاية")
    in_scope = [l for l in lines if lo <= _day(l["date"]) <= hi]
    if not in_scope:
        raise ValueError("مفيش حركات في الكشف داخل الفترة دي")
    pad = max(int(window or 0), MAX_DATE_GAP)
    book = book_lines(kind, ref_id, lo - datetime.timedelta(days=pad), hi + datetime.timedelta(days=pad))
    res = reconcile(in_scope, book["lines"], window, period=(lo, hi))
    sm = res["summary"]
    book_open = book_balance(kind, ref_id, lo - datetime.timedelta(days=1))
    book_close = book_balance(kind, ref_id, hi)
    stmt_close = closing_override if closing_override not in (None, "") else (st["closing"] if hi == _day(st["max_date"]) else None)
    stmt_close = None if stmt_close is None else round(float(stmt_close), 2)
    stmt_open = None if stmt_close is None else round(stmt_close - sm["stmt_total"], 2)
    out = dict(res)
    out.update({
        "kind": kind, "kind_label": KINDS[kind], "ref_id": int(ref_id), "date_from": lo, "date_to": hi, "window": int(window or 0), "flip": bool(flip),
        "book_opening": book_open, "book_closing": book_close, "stmt_opening": stmt_open, "stmt_closing": stmt_close,
        "closing_diff": None if stmt_close is None else round(stmt_close - book_close, 2),
        "opening_diff": None if stmt_open is None else round(stmt_open - book_open, 2),
        # تسوية الأرصدة: رصيد الدفتر بعد تسجيل اللي في الكشف بس / رصيد الكشف بعد إضافة اللي في الدفتر بس - لو الافتتاحي متطابق بيتساووا
        "adjusted_book": round(book_close + sm["stmt_only_sum"] + sm["amount_diff_sum"], 2),
        "adjusted_stmt": None if stmt_close is None else round(stmt_close + sm["book_only_sum"], 2),
        "skipped": st["skipped"],
    })
    return out


CATEGORY_LABELS = {"matched": "مطابق", "date_diff": "مطابق بفارق تاريخ", "amount_diff": "اختلاف في المبلغ",
                   "stmt_only": "في الكشف فقط", "book_only": "في الدفتر فقط"}


def flat_rows(rep, categories=("date_diff", "amount_diff", "stmt_only", "book_only")):
    """صفوف مسطّحة للعرض/التصدير مرتبة بالتاريخ: category, label, s_date, s_ref, s_desc, s_amount, b_date, b_number, b_desc, b_amount, diff."""
    out = []
    for cat in categories:
        for item in rep[cat]:
            s, b = item if isinstance(item, tuple) else ((item, None) if cat == "stmt_only" else (None, item))
            out.append({"category": cat, "label": CATEGORY_LABELS[cat],
                        "s_date": s["date"] if s else None, "s_ref": (s or {}).get("reference", ""), "s_desc": (s or {}).get("description", ""), "s_amount": s["amount"] if s else None,
                        "b_date": b["date"] if b else None, "b_number": (b or {}).get("number", ""), "b_desc": (b or {}).get("description", ""), "b_amount": b["amount"] if b else None,
                        "diff": round((s["amount"] if s else 0.0) - (b["amount"] if b else 0.0), 2)})
    out.sort(key=lambda r: (r["s_date"] or r["b_date"], r["label"]))
    return out
