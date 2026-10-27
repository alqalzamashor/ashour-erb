"""أدوات القيود: العكسي، القوالب والمتكررة، اللصق من Excel، المرفقات، والمساعد الذكي."""
import datetime
import json

import pytest

from erp_app import journal_tools as jt
from erp_app.db import JournalEntry, JournalEntryLine, get_session


def _acc(S):
    return {a.code: a for a in S.list_accounts(postable_only=True)}


def _two(S):
    codes = list(_acc(S))
    a = _acc(S)
    return a[codes[0]], a[codes[1]]


def _entry(S, amount=100.0, date=None, desc="إيجار الشهر"):
    x, y = _two(S)
    return S.create_journal_entry([{"account_id": x.id, "debit": amount}, {"account_id": y.id, "credit": amount}],
                                  reference="R1", description=desc, entry_date=date or datetime.datetime.now())


def _net(account_id):
    from sqlalchemy import func
    with get_session() as s:
        d, c = s.query(func.coalesce(func.sum(JournalEntryLine.debit), 0), func.coalesce(func.sum(JournalEntryLine.credit), 0)).join(JournalEntry).filter(
            JournalEntryLine.account_id == account_id, JournalEntry.posted.is_(True)).one()
        return round(d - c, 2)


# ---------------- القيد العكسي
def test_reverse_entry_nets_to_zero_and_links(S):
    x, y = _two(S)
    before = _net(x.id)
    eid = _entry(S, 250)
    rid = jt.reverse_journal_entry(eid, reason="خطأ في الحساب")
    assert _net(x.id) == before
    orig, rev = S.get_journal_entry(eid), S.get_journal_entry(rid)
    assert orig.reversed_by_id == rid and rev.reversal_of_id == eid and rev.source_type == "reversal"
    assert "خطأ في الحساب" in rev.description and rev.reference == orig.number
    assert {(l.account_id, l.debit, l.credit) for l in rev.lines} == {(l.account_id, l.credit, l.debit) for l in orig.lines}


def test_reverse_rejects_double_reversal_of_reversal_and_generated(S, shop):
    eid = _entry(S, 10)
    rid = jt.reverse_journal_entry(eid)
    with pytest.raises(ValueError, match="اتعكس"):
        jt.reverse_journal_entry(eid)
    with pytest.raises(ValueError, match="عكسي"):
        jt.reverse_journal_entry(rid)
    inv = S.create_sales_invoice(shop["cust"], [{"product_id": shop["burger"], "quantity": 1, "unit_price": 10}], location_id=shop["loc"])
    with get_session() as s:
        gen = s.query(JournalEntry).filter(JournalEntry.source_type == "sales_invoice").first()
        gid = gen.id
    with pytest.raises(ValueError, match="مستند"):
        jt.reverse_journal_entry(gid)


def test_reverse_draft_rejected(S):
    eid = _entry(S, 5)
    S.set_journal_entry_draft(eid)
    with pytest.raises(ValueError, match="مسودة"):
        jt.reverse_journal_entry(eid)


# ---------------- القوالب والمتكررة
def _tpl_lines(S, amount=500):
    x, y = _two(S)
    return [{"account_id": x.id, "debit": amount, "description": "إيجار"}, {"account_id": y.id, "credit": amount}]


def test_template_crud_and_validation(S):
    tid = jt.save_template("إيجار شهري", _tpl_lines(S), description="إيجار المقر")
    assert jt.get_template(tid)["lines"][0]["debit"] == 500
    with pytest.raises(ValueError, match="بنفس الاسم"):
        jt.save_template("إيجار شهري", _tpl_lines(S))
    x, y = _two(S)
    with pytest.raises(ValueError, match="غير متوازن"):
        jt.save_template("غلط", [{"account_id": x.id, "debit": 5}, {"account_id": y.id, "credit": 4}])
    with pytest.raises(ValueError, match="اسم"):
        jt.save_template(" ", _tpl_lines(S))
    tid2 = jt.template_from_entry(_entry(S, 77), "من قيد")
    assert [l["debit"] + l["credit"] for l in jt.get_template(tid2)["lines"]] == [77, 77]
    jt.save_template("إيجار شهري", _tpl_lines(S, 600), template_id=tid)
    assert jt.get_template(tid)["lines"][0]["debit"] == 600


def test_add_period_month_end_clamp():
    assert jt.add_period(datetime.datetime(2026, 1, 31), "monthly") == datetime.datetime(2026, 2, 28)
    assert jt.add_period(datetime.datetime(2026, 11, 30), "quarterly") == datetime.datetime(2027, 2, 28)
    assert jt.add_period(datetime.datetime(2028, 2, 29), "yearly") == datetime.datetime(2029, 2, 28)
    assert jt.add_period(datetime.datetime(2026, 3, 1), "weekly") == datetime.datetime(2026, 3, 8)


def test_recurrence_generates_catches_up_and_stops_at_end(S):
    tid = jt.save_template("اهتلاك", _tpl_lines(S, 100))
    now = datetime.datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    start = jt.add_period(jt.add_period(now, "weekly"), "weekly")        # مجرد قيمة مستقبلية نعدّلها تحت
    start = now - datetime.timedelta(days=70)
    rid = jt.save_recurrence(tid, "monthly", start, end_date=now - datetime.timedelta(days=5))
    made = jt.run_due_recurrences(today=now)
    assert len(made) == 3                                                   # بداية + شهر + شهرين، وبعدها النهاية
    r = next(x for x in jt.list_recurrences() if x["id"] == rid)
    assert r["runs_count"] == 3 and r["is_active"] is False
    e = S.get_journal_entry(made[0])
    assert e.source_type == "recurring" and e.posted and round(sum(l.debit for l in e.lines), 2) == 100
    assert jt.run_due_recurrences(today=now) == []                          # ما بيتكررش تاني


def test_recurrence_draft_mode_and_error_recorded(S):
    tid = jt.save_template("مسودة", _tpl_lines(S, 30))
    now = datetime.datetime.now()
    rid = jt.save_recurrence(tid, "weekly", now - datetime.timedelta(days=1), auto_post=False)
    made = jt.run_due_recurrences(today=now)
    assert len(made) == 1 and S.get_journal_entry(made[0]).posted is False
    # حساب بقى رئيسي (له فروع) → الجدولة تقف وتسجّل السبب بدل ما تقع
    from erp_app import db as _db
    if _db.IS_PG:       # PostgreSQL بيمنع رقم حساب غير موجود بالمفتاح الأجنبي (SQLite لأ) فالجزء ده خاص بـ SQLite
        return
    x, _ = _two(S)
    tid2 = jt.save_template("هيفشل", _tpl_lines(S, 10))
    with get_session() as s:
        from erp_app.db import JournalTemplateLine
        s.query(JournalTemplateLine).filter(JournalTemplateLine.template_id == tid2).first().account_id = 10 ** 6
        s.commit()
    rid2 = jt.save_recurrence(tid2, "monthly", now - datetime.timedelta(days=1))
    jt.run_due_recurrences(today=now)
    r2 = next(x for x in jt.list_recurrences() if x["id"] == rid2)
    assert r2["runs_count"] == 0 and r2["last_error"]


def test_delete_template_blocked_while_recurring(S):
    tid = jt.save_template("للحذف", _tpl_lines(S, 12))
    rid = jt.save_recurrence(tid, "monthly", datetime.datetime.now() + datetime.timedelta(days=30))
    with pytest.raises(ValueError, match="جدولة"):
        jt.delete_template(tid)
    jt.save_recurrence(tid, "monthly", datetime.datetime.now() + datetime.timedelta(days=30), is_active=False, recurrence_id=rid)
    jt.delete_recurrence(rid)
    assert jt.delete_template(tid) and jt.get_template(tid) is None


# ---------------- المرفقات
def test_attachments_roundtrip(S, tmp_path):
    eid = _entry(S, 9)
    f = tmp_path / "فاتورة.pdf"
    f.write_bytes(b"%PDF-1.4 test")
    aid = jt.attach_file(eid, str(f))
    rows = jt.list_attachments(eid)
    assert len(rows) == 1 and rows[0]["file_name"] == "فاتورة.pdf" and open(rows[0]["file_path"], "rb").read() == b"%PDF-1.4 test"
    with pytest.raises(ValueError, match="غير موجود"):
        jt.attach_file(eid, str(tmp_path / "nope.pdf"))
    jt.delete_attachment(aid)
    assert jt.list_attachments(eid) == []


# ---------------- اللصق
def test_parse_paste_with_header_arabic_digits_and_formats(S):
    x, y = _two(S)
    txt = f"الحساب\tالبيان\tمدين\tدائن\n{x.code}\tبند أول\t١٬٢٥٠٫٥٠\t0\n{y.code} - {y.name}\t\t\t1,250.50\n"
    r = jt.parse_pasted_lines(txt)
    assert r["warnings"] == []
    assert [(l["account_id"], l["debit"], l["credit"], l["description"]) for l in r["lines"]] == [(x.id, 1250.5, 0, "بند أول"), (y.id, 0, 1250.5, "")]


def test_parse_paste_without_header_three_columns_and_negative(S):
    x, y = _two(S)
    r = jt.parse_pasted_lines(f"{x.code},100,0\n{y.code},-100,0")
    assert [(l["debit"], l["credit"]) for l in r["lines"]] == [(100, 0), (0, 100)]
    assert r["warnings"] == []


def test_parse_paste_warnings_unknown_account_and_unbalanced(S):
    x, _ = _two(S)
    r = jt.parse_pasted_lines(f"{x.code}\t100\t0\nحساب مش موجود بالمرة\t0\t90")
    assert r["lines"][1]["account_id"] is None
    assert any("مش موجود" in w for w in r["warnings"]) and any("غير متوازن" in w for w in r["warnings"])
    with pytest.raises(ValueError):
        jt.parse_pasted_lines("   \n  ")
    with pytest.raises(ValueError, match="رقم غير صحيح"):
        jt.parse_pasted_lines(f"{x.code}\tabc\t0")


def test_match_account_by_name_and_fuzzy(S):
    accs = S.list_accounts(postable_only=True)
    a = accs[3]
    assert jt.match_account(a.name, accs)[0].id == a.id
    got, how = jt.match_account(f"{a.code} - {a.name}", accs)
    assert got.id == a.id and how == "كود"
    assert jt.match_account("", accs) == (None, "")


def test_parse_excel_file(S, tmp_path):
    import openpyxl
    x, y = _two(S)
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Account", "Description", "Debit", "Credit"]); ws.append([x.code, "d", 40, None]); ws.append([y.code, "c", None, 40])
    p = tmp_path / "e.xlsx"; wb.save(p)
    r = jt.parse_excel_lines(str(p))
    assert [(l["account_id"], l["debit"], l["credit"]) for l in r["lines"]] == [(x.id, 40, 0), (y.id, 0, 40)]
    with pytest.raises(ValueError, match="Excel"):
        jt.parse_excel_lines(str(tmp_path / "a.txt"))


# ---------------- المساعد الذكي
def test_suggest_from_history_scales_amount(S):
    _entry(S, 1000, desc="سداد فاتورة كهرباء المقر الرئيسي")
    r = jt.suggest_entry("فاتورة كهرباء المقر", amount=400)
    assert r["engine"] == "history" and round(sum(l["debit"] for l in r["lines"]), 2) == 400 == round(sum(l["credit"] for l in r["lines"]), 2)
    with pytest.raises(ValueError):
        jt.suggest_entry("xyz qqq zzz")
    with pytest.raises(ValueError, match="وصف"):
        jt.suggest_entry("ab")


def _enable_ai(S):
    jt.save_ai_config(enabled=True, api_key="sk-test-123", model="m1")


def test_ai_config_masks_key_in_audit_and_status(S):
    _enable_ai(S)
    st = jt.ai_status()
    assert st["enabled"] and st["has_key"] and "api_key" not in st
    from erp_app.db import AuditLog
    with get_session() as s:
        logs = " ".join((a.changes or "") for a in s.query(AuditLog).filter(AuditLog.action == "config").all())
    assert "sk-test-123" not in logs


def test_ai_suggestion_valid_and_validated(S, monkeypatch):
    x, y = _two(S)
    _enable_ai(S)
    seen = {}

    def fake(url, headers, payload, timeout=40):
        seen.update(headers=headers, payload=payload)
        body = {"description": "إيجار", "lines": [{"account_id": x.id, "debit": 300, "credit": 0, "note": "م"}, {"account_id": y.id, "debit": 0, "credit": 300}], "explanation": "شرح"}
        return {"content": [{"type": "text", "text": "```json\n" + json.dumps(body) + "\n```"}]}
    monkeypatch.setattr(jt, "_http_post", fake)
    r = jt.suggest_entry("دفعت إيجار 300", amount=300)
    assert r["engine"] == "ai" and len(r["lines"]) == 2 and r["explanation"] == "شرح"
    assert seen["headers"]["x-api-key"] == "sk-test-123" and "الأرصدة" not in seen["payload"]["messages"][0]["content"]
    # حساب مش في الشجرة
    monkeypatch.setattr(jt, "_http_post", lambda *a, **k: {"content": [{"type": "text", "text": json.dumps({"lines": [{"account_id": 10 ** 7, "debit": 5}, {"account_id": y.id, "credit": 5}]})}]})
    with pytest.raises(ValueError):
        jt.suggest_with_ai("وصف طويل كفاية")
    # غير متوازن
    monkeypatch.setattr(jt, "_http_post", lambda *a, **k: {"content": [{"type": "text", "text": json.dumps({"lines": [{"account_id": x.id, "debit": 5}, {"account_id": y.id, "credit": 4}]})}]})
    with pytest.raises(ValueError, match="متوازن"):
        jt.suggest_with_ai("وصف طويل كفاية")


def test_ai_failure_falls_back_to_history_with_warning(S, monkeypatch):
    _enable_ai(S)
    _entry(S, 800, desc="مصروف ضيافة اجتماع")

    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(jt, "_http_post", boom)
    r = jt.suggest_entry("مصروف ضيافة اجتماع", amount=200)
    assert r["engine"] == "history" and "down" in r["warning"]
