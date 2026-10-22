"""أدوات القيود اليومية: القيد العكسي، القوالب والقيود المتكررة، لصق السطور من Excel/الحافظة، مرفقات القيد، والمساعد الذكي.
كل شيء بيمرّ على services.create_journal_entry (نفس فحوصات التوازن والفترة المقفولة والحسابات الرئيسية والصلاحيات)."""
import calendar
import datetime
import difflib
import json
import os
import re
import shutil
import uuid

from . import audit, services
from .db import (APP_DIR, Account, JournalEntry, JournalEntryAttachment, JournalEntryLine, JournalRecurrence,
                 JournalTemplate, JournalTemplateLine, get_session)

AI_CFG_PATH = os.path.join(APP_DIR, "journal_ai.json")
AI_DEFAULTS = {"enabled": False, "api_key": "", "model": "claude-sonnet-5-5"}
REVERSIBLE_SOURCES = ("manual", "recurring")
FREQUENCIES = {"weekly": "أسبوعي", "monthly": "شهري", "quarterly": "ربع سنوي", "yearly": "سنوي"}


# ============================================================ القيد العكسي
def reverse_journal_entry(entry_id, entry_date=None, reason=""):
    """يعمل قيد عكسي (مدين↔دائن بنفس الأطراف ومراكز التكلفة) لقيد مرحّل، ويربط القيدين ببعض. مسموح بس للقيود اليدوية/المتكررة؛
    القيود المولّدة من فواتير وسندات بتتعكس من مصدرها (مرتجع/إلغاء) عشان أرصدة العملاء والمخزون تفضل متسقة."""
    services.require_action("journals", "create")
    with get_session() as s:
        e = s.get(JournalEntry, entry_id)
        if not e:
            raise ValueError("القيد غير موجود")
        if not e.posted:
            raise ValueError("القيد ده مسودة غير مرحّلة - مفيش حاجة تتعكس")
        if e.reversal_of_id:
            raise ValueError("ده قيد عكسي بالفعل - مينفعش يتعكس تاني (اعمل قيد جديد لو محتاج)")
        if e.reversed_by_id:
            other = s.get(JournalEntry, e.reversed_by_id)
            raise ValueError(f"القيد ده اتعكس قبل كده بالقيد {other.number if other else e.reversed_by_id}")
        if e.source_type not in REVERSIBLE_SOURCES:
            raise ValueError("القيد ده متولّد تلقائيًا من مستند (فاتورة/سند/...) - اعكسه من المستند الأصلي (مرتجع أو إلغاء)")
        number, desc, branch_id = e.number, e.description or "", e.branch_id
        lines = [{"account_id": l.account_id, "debit": l.credit or 0.0, "credit": l.debit or 0.0,
                  "description": (l.description or "") or f"عكس {number}", "branch_id": l.branch_id,
                  "cost_center_id": l.cost_center_id, "partner_type": l.partner_type, "partner_id": l.partner_id} for l in e.lines]
    when = entry_date or datetime.datetime.now()
    text = f"عكس القيد {number}" + (f" - {reason.strip()}" if reason and reason.strip() else (f" - {desc}" if desc else ""))
    new_id = services.create_journal_entry(lines, reference=number, description=text, source_type="reversal",
                                           source_id=entry_id, entry_date=when, branch_id=branch_id)
    with get_session() as s:
        s.get(JournalEntry, new_id).reversal_of_id = entry_id
        s.get(JournalEntry, entry_id).reversed_by_id = new_id
        s.commit()
    audit.log_event("reverse_journal", label=f"عكس القيد {number}", changes={"original": entry_id, "reversal": new_id, "reason": reason or ""})
    return new_id


# ============================================================ القوالب
def _clean_lines(lines):
    out = []
    for ln in lines:
        d = round(float(ln.get("debit") or 0), 2); c = round(float(ln.get("credit") or 0), 2)
        if d < 0 or c < 0 or (d and c):
            raise ValueError("سطر القالب لازم يكون مدين أو دائن فقط")
        if not ln.get("account_id"):
            continue
        if d or c:
            out.append({"account_id": int(ln["account_id"]), "debit": d, "credit": c, "description": ln.get("description") or "",
                        "branch_id": ln.get("branch_id") or None, "cost_center_id": ln.get("cost_center_id") or None,
                        "partner_type": ln.get("partner_type") or None, "partner_id": ln.get("partner_id") or None})
    if len(out) < 2:
        raise ValueError("القالب لازم فيه سطرين على الأقل")
    td = round(sum(x["debit"] for x in out), 2); tc = round(sum(x["credit"] for x in out), 2)
    if td != tc:
        raise ValueError(f"القالب غير متوازن: مدين {td:,.2f} / دائن {tc:,.2f}")
    return out


def save_template(name, lines, description="", reference="", template_id=None):
    services.require_action("journals", "create")
    name = (name or "").strip()
    if not name:
        raise ValueError("اكتب اسم القالب")
    data = _clean_lines(lines)
    with get_session() as s:
        dup = s.query(JournalTemplate).filter(JournalTemplate.name == name)
        if template_id:
            dup = dup.filter(JournalTemplate.id != template_id)
        if dup.first():
            raise ValueError("فيه قالب بنفس الاسم")
        t = s.get(JournalTemplate, template_id) if template_id else JournalTemplate()
        if template_id and not t:
            raise ValueError("القالب غير موجود")
        t.name = name; t.description = description or ""; t.reference = reference or ""
        if not template_id:
            s.add(t)
        s.flush()
        for old in list(t.lines):
            s.delete(old)
        s.flush()
        for d in data:
            s.add(JournalTemplateLine(template_id=t.id, **d))
        s.commit()
        return t.id


def template_from_entry(entry_id, name):
    e = services.get_journal_entry(entry_id)
    if not e:
        raise ValueError("القيد غير موجود")
    lines = [{"account_id": l.account_id, "debit": l.debit, "credit": l.credit, "description": l.description,
              "branch_id": l.branch_id, "cost_center_id": l.cost_center_id, "partner_type": l.partner_type, "partner_id": l.partner_id} for l in e.lines]
    return save_template(name, lines, description=e.description or "", reference=e.reference or "")


def list_templates(active_only=True):
    with get_session() as s:
        q = s.query(JournalTemplate)
        if active_only:
            q = q.filter(JournalTemplate.is_active.is_(True))
        rows = q.order_by(JournalTemplate.name).all()
        out = [{"id": t.id, "name": t.name, "description": t.description, "reference": t.reference, "is_active": t.is_active,
                "lines": [{"account_id": l.account_id, "account": f"{l.account.code} - {l.account.name}" if l.account else "",
                           "debit": l.debit, "credit": l.credit, "description": l.description, "branch_id": l.branch_id,
                           "cost_center_id": l.cost_center_id, "partner_type": l.partner_type, "partner_id": l.partner_id} for l in t.lines]}
               for t in rows]
        return out


def get_template(template_id):
    return next((t for t in list_templates(False) if t["id"] == template_id), None)


def delete_template(template_id):
    services.require_action("journals", "delete")
    with get_session() as s:
        t = s.get(JournalTemplate, template_id)
        if not t:
            raise ValueError("القالب غير موجود")
        if s.query(JournalRecurrence).filter(JournalRecurrence.template_id == template_id, JournalRecurrence.is_active.is_(True)).first():
            raise ValueError("القالب ده عليه جدولة قيد متكرر شغّالة - أوقفها أو احذفها الأول")
        for r in s.query(JournalRecurrence).filter(JournalRecurrence.template_id == template_id).all():
            s.delete(r)
        s.delete(t); s.commit()
    return True


# ============================================================ القيود المتكررة
def add_period(d, frequency):
    """التاريخ التالي: شهري/ربع سنوي/سنوي بيحافظ على اليوم (لو الشهر أقصر بياخد آخر يوم فيه)."""
    if frequency == "weekly":
        return d + datetime.timedelta(days=7)
    step = {"monthly": 1, "quarterly": 3, "yearly": 12}.get(frequency)
    if not step:
        raise ValueError("تكرار غير معروف")
    m = d.month - 1 + step
    y = d.year + m // 12; m = m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def save_recurrence(template_id, frequency, start_date, end_date=None, auto_post=True, is_active=True, recurrence_id=None):
    services.require_action("journals", "create")
    if frequency not in FREQUENCIES:
        raise ValueError("اختر التكرار")
    if not start_date:
        raise ValueError("اكتب تاريخ أول تنفيذ")
    if end_date and end_date < start_date:
        raise ValueError("تاريخ النهاية قبل تاريخ البداية")
    with get_session() as s:
        if not s.get(JournalTemplate, template_id):
            raise ValueError("القالب غير موجود")
        r = s.get(JournalRecurrence, recurrence_id) if recurrence_id else JournalRecurrence(template_id=template_id)
        if recurrence_id and not r:
            raise ValueError("الجدولة غير موجودة")
        r.template_id = template_id; r.frequency = frequency
        if not recurrence_id or r.next_date is None or (r.runs_count or 0) == 0:
            r.next_date = start_date
        r.end_date = end_date; r.auto_post = bool(auto_post); r.is_active = bool(is_active)
        if not recurrence_id:
            s.add(r)
        s.commit()
        return r.id


def list_recurrences():
    with get_session() as s:
        rows = s.query(JournalRecurrence).order_by(JournalRecurrence.id).all()
        return [{"id": r.id, "template_id": r.template_id, "template": r.template.name if r.template else "", "frequency": r.frequency,
                 "frequency_label": FREQUENCIES.get(r.frequency, r.frequency), "next_date": r.next_date, "end_date": r.end_date,
                 "auto_post": r.auto_post, "is_active": r.is_active, "runs_count": r.runs_count or 0, "last_run_at": r.last_run_at,
                 "last_entry_id": r.last_entry_id, "last_error": r.last_error or ""} for r in rows]


def delete_recurrence(recurrence_id):
    services.require_action("journals", "delete")
    with get_session() as s:
        r = s.get(JournalRecurrence, recurrence_id)
        if not r:
            raise ValueError("الجدولة غير موجودة")
        s.delete(r); s.commit()
    return True


def _make_entry(tpl, when, auto_post, recurrence_id):
    lines = [{k: l[k] for k in ("account_id", "debit", "credit", "description", "branch_id", "cost_center_id", "partner_type", "partner_id")} for l in tpl["lines"]]
    jid = services.create_journal_entry(lines, reference=tpl["reference"] or tpl["name"], description=tpl["description"] or tpl["name"],
                                        source_type="recurring", source_id=recurrence_id, entry_date=when)
    if not auto_post:
        with get_session() as s:
            s.get(JournalEntry, jid).posted = False
            s.commit()
    return jid


def run_due_recurrences(today=None, max_catchup=24):
    """بيولّد القيود المستحقة (لحد النهارده) - لو السيرفر كان واقف بيعوّض الفترات الفايتة (بحد أقصى max_catchup لكل جدولة).
    لو فترة مقفولة أو حساب مش متاح: الجدولة بتقف عند الخطأ وبتتسجّل رسالته، وبتكمّل في الدورة الجاية بعد ما تتصلح."""
    today = today or datetime.datetime.now()
    made = []
    for r in list_recurrences():
        if not r["is_active"]:
            continue
        tpl = get_template(r["template_id"])
        nxt = r["next_date"]
        n = 0
        while nxt and nxt <= today and (not r["end_date"] or nxt <= r["end_date"]) and n < max_catchup:
            try:
                jid = _make_entry(tpl, nxt, r["auto_post"], r["id"])
            except Exception as ex:      # noqa: BLE001 - نسجّل السبب ونوقف الجدولة دي بس
                with get_session() as s:
                    s.get(JournalRecurrence, r["id"]).last_error = str(ex)[:300]; s.commit()
                break
            nxt = add_period(nxt, r["frequency"]); n += 1
            made.append(jid)
            with get_session() as s:
                row = s.get(JournalRecurrence, r["id"])
                row.next_date = nxt; row.runs_count = (row.runs_count or 0) + 1
                row.last_run_at = datetime.datetime.now(); row.last_entry_id = jid; row.last_error = ""
                if row.end_date and nxt > row.end_date:
                    row.is_active = False
                s.commit()
    return made


# ============================================================ مرفقات القيد
def attach_file(entry_id, source_path):
    services.require_action("journals", "edit")
    if not source_path or not os.path.isfile(source_path):
        raise ValueError("الملف غير موجود")
    if os.path.getsize(source_path) > 15 * 1024 * 1024:
        raise ValueError("الملف أكبر من 15 ميجا")
    with get_session() as s:
        e = s.get(JournalEntry, entry_id)
        if not e:
            raise ValueError("القيد غير موجود")
        number = e.number
    base = os.path.normpath(os.path.join(APP_DIR, "attachments", "journal_entries", number))
    os.makedirs(base, exist_ok=True)
    name = os.path.basename(source_path); root, ext = os.path.splitext(name)
    dest = os.path.join(base, f"{root}_{uuid.uuid4().hex[:8]}{ext}")
    shutil.copy2(source_path, dest)
    with get_session() as s:
        a = JournalEntryAttachment(entry_id=entry_id, file_name=name, file_path=dest, uploaded_by=services._current_username() or "")
        s.add(a); s.commit(); return a.id


def list_attachments(entry_id):
    with get_session() as s:
        rows = s.query(JournalEntryAttachment).filter(JournalEntryAttachment.entry_id == entry_id).order_by(JournalEntryAttachment.uploaded_at.desc()).all()
        return [{"id": a.id, "file_name": a.file_name, "file_path": a.file_path, "uploaded_by": a.uploaded_by, "uploaded_at": a.uploaded_at} for a in rows]


def delete_attachment(attachment_id):
    services.require_action("journals", "edit")
    with get_session() as s:
        a = s.get(JournalEntryAttachment, attachment_id)
        if not a:
            raise ValueError("المرفق غير موجود")
        path = a.file_path; s.delete(a); s.commit()
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:       # noqa: BLE001
        pass
    return True


# ============================================================ لصق سطور من Excel / الحافظة
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬،", "0123456789.,,")
_HEAD = {"account": ("حساب", "الحساب", "كود", "رقم الحساب", "account", "code", "acc"),
         "description": ("بيان", "البيان", "وصف", "description", "memo", "narration", "details"),
         "debit": ("مدين", "debit", "dr"), "credit": ("دائن", "credit", "cr")}


def _num(v):
    if v is None:
        return 0.0
    t = str(v).strip().translate(_AR_DIGITS).replace(" ", "")
    if not t or t in "-—":
        return 0.0
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").replace(",", "")
    try:
        x = float(t)
    except ValueError:
        raise ValueError(f"رقم غير صحيح: {v}")
    return -x if neg else x


def _norm(t):
    t = str(t or "").translate(_AR_DIGITS).strip().lower()
    t = re.sub(r"[أإآ]", "ا", t).replace("ة", "ه").replace("ى", "ي")
    return re.sub(r"\s+", " ", t)


def match_account(text, accounts):
    """يطابق نص (كود أو اسم أو 'كود - اسم') على الحسابات القابلة للترحيل: كود مطابق ← اسم مطابق ← اسم قريب. بيرجّع (account, طريقة) أو (None, '')."""
    raw = str(text or "").strip()
    if not raw:
        return None, ""
    n = _norm(raw)
    code = re.match(r"^([0-9A-Za-z.\-]+)\s*(?:[-–:]\s*(.*))?$", raw.translate(_AR_DIGITS))
    by_code = {str(a.code).lower(): a for a in accounts}
    if code and code.group(1).lower() in by_code:
        return by_code[code.group(1).lower()], "كود"
    names = {_norm(a.name): a for a in accounts}
    if n in names:
        return names[n], "اسم"
    tail = _norm(code.group(2)) if code and code.group(2) else ""
    if tail in names:
        return names[tail], "اسم"
    cand = difflib.get_close_matches(tail or n, list(names), n=1, cutoff=0.82)
    if cand:
        return names[cand[0]], "اسم قريب"
    return None, ""


def _split_row(line):
    if "\t" in line:
        return [c.strip() for c in line.split("\t")]
    if ";" in line:
        return [c.strip() for c in line.split(";")]
    return [c.strip() for c in re.split(r",(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", line)]


def parse_pasted_lines(text, accounts=None):
    """نص ملصوق من Excel (أعمدة بـTab) أو CSV → سطور قيد. بيتعرّف على صف العناوين (حساب/بيان/مدين/دائن) لو موجود،
    وإلا بيفترض الترتيب: حساب، [بيان]، مدين، دائن. بيرجّع {'lines': [...], 'warnings': [...]}؛ السطر اللي حسابه مش معروف account_id=None."""
    accounts = accounts if accounts is not None else services.list_accounts(postable_only=True)
    rows = [_split_row(l) for l in (text or "").splitlines() if l.strip()]
    if not rows:
        raise ValueError("مفيش بيانات للصق")
    colmap = None
    first = [_norm(c) for c in rows[0]]
    found = {}
    for key, names in _HEAD.items():
        for i, c in enumerate(first):
            if c in [_norm(x) for x in names]:
                found[key] = i
    if "debit" in found and "credit" in found:
        colmap = found; rows = rows[1:]
    width = max(len(r) for r in rows) if rows else 0
    if colmap is None:
        if width >= 4:
            colmap = {"account": 0, "description": 1, "debit": 2, "credit": 3}
        elif width == 3:
            colmap = {"account": 0, "debit": 1, "credit": 2}
        else:
            raise ValueError("مش قادر أفهم الأعمدة - لازم على الأقل: حساب، مدين، دائن")
    out, warns = [], []
    for n, r in enumerate(rows, start=1):
        def cell(k):
            i = colmap.get(k)
            return r[i] if i is not None and i < len(r) else ""
        if not any(cell(k) for k in ("account", "debit", "credit")):
            continue
        try:
            d, c = _num(cell("debit")), _num(cell("credit"))
        except ValueError as ex:
            warns.append(f"سطر {n}: {ex}"); continue
        if d < 0:
            c, d = c - d, 0.0
        if c < 0:
            d, c = d - c, 0.0
        if d and c:
            net = round(d - c, 2); d, c = (net, 0.0) if net > 0 else (0.0, -net)
        acc, how = match_account(cell("account"), accounts)
        if not acc:
            warns.append(f"سطر {n}: الحساب «{cell('account')}» مش موجود - اختاره بإيدك")
        elif how == "اسم قريب":
            warns.append(f"سطر {n}: «{cell('account')}» اتطابق تقريبًا مع {acc.code} - {acc.name} (راجعه)")
        out.append({"account_id": acc.id if acc else None, "account_text": cell("account"), "description": cell("description"),
                    "debit": round(d, 2), "credit": round(c, 2), "matched": how})
    if not out:
        raise ValueError(warns[0] if warns else "مفيش سطور صالحة في البيانات الملصوقة")
    td = round(sum(x["debit"] for x in out), 2); tc = round(sum(x["credit"] for x in out), 2)
    if td != tc:
        warns.append(f"القيد غير متوازن: مدين {td:,.2f} / دائن {tc:,.2f}")
    return {"lines": out, "warnings": warns}


def parse_excel_lines(path, accounts=None):
    """نفس لصق الحافظة بس من ملف .xlsx/.csv (أول ورقة)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            return parse_pasted_lines(f.read(), accounts)
    if ext not in (".xlsx", ".xlsm"):
        raise ValueError("الملف لازم يكون Excel (.xlsx) أو CSV")
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    lines = ["\t".join("" if v is None else str(v) for v in row) for row in ws.iter_rows(values_only=True)]
    wb.close()
    return parse_pasted_lines("\n".join(lines), accounts)


# ============================================================ المساعد الذكي
def get_ai_config():
    cfg = dict(AI_DEFAULTS)
    try:
        with open(AI_CFG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:       # noqa: BLE001
        pass
    if os.environ.get("ANTHROPIC_API_KEY") and not cfg.get("api_key"):
        cfg["api_key"] = os.environ["ANTHROPIC_API_KEY"]
    return cfg


@audit.audited_config("إعدادات المساعد الذكي للقيود", getter="get_ai_config")
def save_ai_config(enabled=False, api_key=None, model=None):
    services.require_action("journals", "edit")
    cfg = get_ai_config()
    cfg["enabled"] = bool(enabled)
    if api_key is not None and api_key.strip():
        cfg["api_key"] = api_key.strip()
    if model and model.strip():
        cfg["model"] = model.strip()
    with open(AI_CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    try:
        os.chmod(AI_CFG_PATH, 0o600)
    except OSError:
        pass
    return {"enabled": cfg["enabled"], "has_key": bool(cfg["api_key"]), "model": cfg["model"]}


def ai_status():
    c = get_ai_config()
    return {"enabled": bool(c["enabled"] and c["api_key"]), "has_key": bool(c["api_key"]), "model": c["model"]}


def _http_post(url, headers, payload, timeout=40):
    import requests
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if r.status_code >= 300:
        raise RuntimeError(f"فشل الاتصال بالمساعد الذكي (HTTP {r.status_code})")
    return r.json()


def _tokens(t):
    return {w for w in re.split(r"[^\w]+", _norm(t)) if len(w) > 2}


def suggest_from_history(description, amount=None, limit=1):
    """اقتراح محلي (من غير إنترنت): أقرب قيد يدوي سابق في البيان، بنفس الحسابات، والمبلغ متحوّل لو القيد القديم من طرف مدين واحد ودائن واحد."""
    want = _tokens(description)
    if not want:
        return None
    best, score = None, 0.0
    with get_session() as s:
        for e in s.query(JournalEntry).filter(JournalEntry.posted.is_(True), JournalEntry.source_type.in_(("manual", "recurring"))).order_by(JournalEntry.id.desc()).limit(600).all():
            have = _tokens(e.description) | _tokens(e.reference)
            for l in e.lines:
                have |= _tokens(l.description)
            if not have:
                continue
            sc = len(want & have) / len(want | have)
            if sc > score:
                best, score = e, sc
        if not best or score < 0.25:
            return None
        lines = [{"account_id": l.account_id, "description": l.description or "", "debit": l.debit or 0.0, "credit": l.credit or 0.0,
                  "branch_id": l.branch_id, "cost_center_id": l.cost_center_id, "partner_type": l.partner_type, "partner_id": l.partner_id} for l in best.lines]
        src = best.number
    if amount and amount > 0:
        td = sum(x["debit"] for x in lines)
        if td > 0:
            f = amount / td
            for x in lines:
                x["debit"] = round(x["debit"] * f, 2); x["credit"] = round(x["credit"] * f, 2)
            diff = round(sum(x["debit"] for x in lines) - sum(x["credit"] for x in lines), 2)
            if diff:
                big = max(lines, key=lambda x: x["credit"]); big["credit"] = round(big["credit"] + diff, 2)
    return {"lines": lines, "source": f"أقرب قيد سابق ({src})", "confidence": round(score, 2), "engine": "history"}


def _chart_text(accounts):
    return "\n".join(f"{a.id}|{a.code}|{a.name}" for a in accounts[:600])


def suggest_with_ai(description, amount=None, accounts=None):
    """يطلب من Claude يقترح سطور القيد من وصف حر. بنبعت بس الوصف + المبلغ + شجرة الحسابات (أرقام وأسماء) - مفيش أرصدة ولا بيانات عملاء.
    الرد بيتتحقق منه بالكامل: الحسابات لازم تكون موجودة وقابلة للترحيل والقيد متوازن، وإلا بيترفض."""
    cfg = get_ai_config()
    if not (cfg["enabled"] and cfg["api_key"]):
        raise ValueError("المساعد الذكي مش مفعّل (فعّله وحط المفتاح من إعدادات المساعد)")
    accounts = accounts if accounts is not None else services.list_accounts(postable_only=True)
    by_id = {a.id: a for a in accounts}
    system = ("أنت محاسب خبير. حوّل وصف العملية إلى قيد يومية مزدوج متوازن باستخدام الحسابات المعطاة فقط (بالـ id). "
              "ردّ بـ JSON فقط بدون أي شرح خارجه بالشكل: {\"description\": \"...\", \"lines\": [{\"account_id\": 1, \"debit\": 0, \"credit\": 0, \"note\": \"...\"}], \"explanation\": \"جملة قصيرة\"}. "
              "كل سطر إما مدين أو دائن، ومجموع المدين = مجموع الدائن، ولا تخترع حسابات.")
    user = f"الحسابات (id|كود|اسم):\n{_chart_text(accounts)}\n\nوصف العملية: {description}\n" + (f"المبلغ: {amount}\n" if amount else "المبلغ: استنتجه من الوصف.\n")
    data = _http_post("https://api.anthropic.com/v1/messages",
                      {"x-api-key": cfg["api_key"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
                      {"model": cfg["model"], "max_tokens": 1200, "system": system, "messages": [{"role": "user", "content": user}]})
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("رد المساعد مش مفهوم - جرّب صياغة تانية")
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        raise ValueError("رد المساعد مش مفهوم - جرّب صياغة تانية")
    lines = []
    for l in obj.get("lines", []):
        try:
            aid = int(l["account_id"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("المساعد رجّع سطر من غير حساب صحيح")
        if aid not in by_id:
            raise ValueError("المساعد اختار حساب مش موجود أو مش قابل للترحيل - جرّب تاني")
        d = round(float(l.get("debit") or 0), 2); c = round(float(l.get("credit") or 0), 2)
        if d < 0 or c < 0 or (d and c) or not (d or c):
            raise ValueError("المساعد رجّع سطر مبلغه غير صحيح")
        lines.append({"account_id": aid, "description": str(l.get("note") or "")[:200], "debit": d, "credit": c})
    if len(lines) < 2:
        raise ValueError("المساعد رجّع أقل من سطرين")
    td = round(sum(x["debit"] for x in lines), 2); tc = round(sum(x["credit"] for x in lines), 2)
    if td != tc:
        raise ValueError(f"المساعد رجّع قيد غير متوازن ({td:,.2f} / {tc:,.2f}) - جرّب تاني")
    return {"lines": lines, "source": "المساعد الذكي", "explanation": str(obj.get("explanation") or "")[:300],
            "description": str(obj.get("description") or "")[:300], "engine": "ai"}


def suggest_entry(description, amount=None):
    """المساعد: لو الذكاء الاصطناعي مفعّل بيستخدمه (ولو فشل بيرجع للاقتراح من سجل القيود السابقة)، وإلا من السجل مباشرة.
    الناتج دايمًا اقتراح للمراجعة - مبيترحّلش من نفسه."""
    description = (description or "").strip()
    if len(description) < 3:
        raise ValueError("اكتب وصف للعملية (كلمتين على الأقل)")
    services.require_action("journals", "create")
    warn = ""
    if ai_status()["enabled"]:
        try:
            return suggest_with_ai(description, amount)
        except Exception as ex:      # noqa: BLE001
            warn = f"{ex}"
    h = suggest_from_history(description, amount)
    if h:
        if warn:
            h["warning"] = f"المساعد الذكي مردّش ({warn}) - ده اقتراح من قيودك السابقة"
        return h
    raise ValueError(warn or "ملقيتش قيد سابق شبه الوصف ده - فعّل المساعد الذكي أو اكتب القيد بإيدك")
