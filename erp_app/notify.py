"""رسائل واتساب / SMS: إيصال للعميل بعد البيع (بموافقته) وتنبيه نقص المخزون للمسؤولين.
المزوّدات: whatsapp_cloud (Meta WhatsApp Business Cloud API) | twilio (واتساب أو SMS) | http (أي بوابة SMS عامة بقالب JSON) | none (من غير مزوّد: رابط واتساب يدوي).
كل رسالة بتتسجّل في notification_log (pending → sent / failed) والإرسال بيتم في خيط خلفي عشان مايبطّئش الكاشير؛ والفاشل بيتعاد تلقائي (3 محاولات).
ملاحظات مهمة: واتساب بيسمح بنص حر بس خلال 24 ساعة من آخر رسالة من العميل؛ غير كده لازم قالب معتمد من ميتا (wa_template_name)."""
import datetime
import json
import os
import re
import threading
import urllib.parse

from . import audit
from .db import APP_DIR, Customer, NotificationLog, get_session

CFG_PATH = os.path.join(APP_DIR, "notify.json")
STATE_PATH = os.path.join(APP_DIR, "notify_state.json")
PROVIDERS = {"none": "من غير مزوّد (رابط واتساب يدوي)", "whatsapp_cloud": "واتساب Cloud API (ميتا)", "twilio": "Twilio (واتساب/SMS)", "http": "بوابة SMS عامة (HTTP)"}
DEFAULTS = {
    "enabled": False, "provider": "none", "channel": "whatsapp", "country_code": "966",
    "auto_receipt": True, "receipt_min_total": 0.0,
    "receipt_template": "شكرًا لزيارتكم {company}\nفاتورة رقم {number}\nالإجمالي: {total} {currency}{points}",
    "low_stock_enabled": False, "low_stock_recipients": "", "low_stock_hour": 9, "low_stock_repeat_days": 3,
    "wa_phone_number_id": "", "wa_token": "", "wa_template_name": "", "wa_template_lang": "ar", "wa_api_version": "v20.0",
    "twilio_sid": "", "twilio_token": "", "twilio_from": "",
    "http_url": "", "http_headers": "{}", "http_body": '{"to": "{to}", "text": "{text}"}',
    "currency": "ر.س",
}
MAX_ATTEMPTS = 3
TIMEOUT = 15
SYNC = False        # للاختبارات: يرسل في نفس الخيط
_lock = threading.RLock()


def get_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def _state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(st):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)


@audit.audited_config("إعدادات الرسائل (واتساب/SMS)")
def save_config(**kw):
    from . import services
    services.require_action("notifications", "edit")
    cfg = get_config()
    cfg.update({k: v for k, v in kw.items() if k in DEFAULTS})
    if cfg["provider"] not in PROVIDERS:
        raise ValueError("المزوّد غير معروف")
    if cfg["channel"] not in ("whatsapp", "sms"):
        raise ValueError("القناة: واتساب أو SMS")
    cfg["country_code"] = re.sub(r"\D", "", str(cfg["country_code"])) or "966"
    cfg["receipt_min_total"] = float(cfg["receipt_min_total"] or 0)
    cfg["low_stock_hour"] = int(cfg["low_stock_hour"]); cfg["low_stock_repeat_days"] = int(cfg["low_stock_repeat_days"])
    if not 0 <= cfg["low_stock_hour"] <= 23 or cfg["low_stock_repeat_days"] < 1:
        raise ValueError("ساعة التنبيه من 0 إلى 23 والتكرار يوم على الأقل")
    try:
        h = json.loads(cfg["http_headers"] or "{}"); assert isinstance(h, dict)
    except Exception:
        raise ValueError("الترويسات (headers) لازم تكون JSON صحيح مثل {\"Authorization\": \"Bearer xxx\"}")
    if cfg["provider"] == "http" and cfg["enabled"]:
        if not str(cfg["http_url"]).startswith(("http://", "https://")):
            raise ValueError("رابط البوابة لازم يبدأ بـ http:// أو https://")
        if "{to}" not in cfg["http_body"] or "{text}" not in cfg["http_body"]:
            raise ValueError("قالب الطلب لازم يحتوي {to} و{text}")
    if cfg["provider"] == "whatsapp_cloud" and cfg["enabled"] and not (cfg["wa_phone_number_id"] and cfg["wa_token"]):
        raise ValueError("واتساب Cloud: رقم الهاتف (Phone Number ID) والتوكن مطلوبين")
    if cfg["provider"] == "twilio" and cfg["enabled"] and not (cfg["twilio_sid"] and cfg["twilio_token"] and cfg["twilio_from"]):
        raise ValueError("Twilio: SID والتوكن ورقم المرسل مطلوبين")
    for ph in split_phones(cfg["low_stock_recipients"]):
        normalize_phone(ph, cfg["country_code"])
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)
    try:
        os.chmod(CFG_PATH, 0o600)
    except Exception:
        pass
    return cfg


def split_phones(text):
    return [x.strip() for x in re.split(r"[,;\n]", str(text or "")) if x.strip()]


from .msgproviders import normalize_phone  # noqa: E402,F401


def wa_link(phone, text):
    return f"https://wa.me/{normalize_phone(phone, get_config()['country_code'])}?text={urllib.parse.quote(text)}"


# ---------------------------------------------------------------- الإرسال
from .msgproviders import _post, _send_via_provider  # noqa: E402,F401


def _deliver(log_id):
    cfg = get_config()
    with _lock, get_session() as s:      # المطالبة بالرسالة: مفيش خيطين يبعتوا نفس الرسالة
        row = s.get(NotificationLog, log_id)
        if not row or row.status not in ("pending", "failed"):
            return
        channel, to, text, params = row.channel, row.recipient, row.body, row.params
        row.attempts = (row.attempts or 0) + 1
        row.status = "sending"
        s.commit()
    err = ""
    try:
        _send_via_provider(cfg, channel, to, text, json.loads(params) if params else None)
    except Exception as ex:     # noqa: BLE001
        err = str(ex)[:500]
    with get_session() as s:
        row = s.get(NotificationLog, log_id)
        row.status = "failed" if err else "sent"
        row.error = err
        row.sent_at = None if err else datetime.datetime.now()
        s.commit()


def queue(kind, phone, text, ref="", params=None, channel=None, force=False):
    """يسجّل الرسالة ويبعتها (خيط خلفي). بيرجّع id السجل أو None لو الخاصية مقفولة. بيرمي ValueError لرقم غلط."""
    cfg = get_config()
    if not cfg["enabled"] and not force:
        return None
    to = normalize_phone(phone, cfg["country_code"])
    channel = channel or cfg["channel"]
    status = "link" if cfg["provider"] == "none" else "pending"
    with get_session() as s:
        row = NotificationLog(channel=channel, provider=cfg["provider"], kind=kind, recipient=to, ref=str(ref or "")[:60],
                              body=text, params=json.dumps(params, ensure_ascii=False) if params else "", status=status)
        s.add(row); s.commit(); lid = row.id
    if status == "pending":
        if SYNC:
            _deliver(lid)
        else:
            threading.Thread(target=_deliver, args=(lid,), daemon=True).start()
    return lid


def retry_failed():
    """يعيد المحاولة للفاشل (أقل من 3 محاولات وخلال 24 ساعة). بيرجّع عدد اللي اتعاد."""
    cfg = get_config()
    if not cfg["enabled"] or cfg["provider"] == "none":
        return 0
    since = datetime.datetime.now() - datetime.timedelta(hours=24)
    with get_session() as s:       # رسائل علقت في "sending" أكتر من 10 دقايق (انهيار) تتحسب فاشلة
        stuck = datetime.datetime.now() - datetime.timedelta(minutes=10)
        for r in s.query(NotificationLog).filter(NotificationLog.status == "sending", NotificationLog.created_at < stuck).all():
            r.status = "failed"; r.error = r.error or "لم يكتمل الإرسال"
        s.commit()
        ids = [r.id for r in s.query(NotificationLog).filter(NotificationLog.status == "failed", NotificationLog.attempts < MAX_ATTEMPTS,
                                                              NotificationLog.created_at >= since).all()]
    for i in ids:
        _deliver(i)
    return len(ids)


# ---------------------------------------------------------------- الاستخدامات
def render_receipt(inv, customer_name, company, loyalty=None, cfg=None):
    cfg = cfg or get_config()
    pts = ""
    if loyalty and (loyalty.get("earned") or loyalty.get("redeemed")):
        pts = f"\nنقاط الولاء: +{loyalty.get('earned', 0):g} (رصيدك {loyalty.get('balance', 0):g})"
    vals = {"company": company, "number": inv["number"], "total": f"{inv['total']:,.2f}", "currency": cfg["currency"],
            "date": inv["date"], "customer": customer_name, "points": pts}
    out = cfg["receipt_template"]
    for k, v in vals.items():
        out = out.replace("{" + k + "}", str(v))
    return out, [company, inv["number"], vals["total"]]


def send_receipt(invoice_id):
    """بعد بيع الكاشير: لو مفعّل والعميل موافق وله جوال → إيصال نصي. بيرجّع id السجل أو None."""
    cfg = get_config()
    if not cfg["enabled"] or not cfg["auto_receipt"]:
        return None
    from . import loyalty, services
    from .db import SalesInvoice
    with get_session() as s:
        inv = s.get(SalesInvoice, invoice_id)
        c = s.get(Customer, inv.customer_id) if inv and inv.customer_id else None
        if not inv or not c or not c.notify_opt_in or not (c.phone or "").strip():
            return None
        if float(inv.total or 0) < float(cfg["receipt_min_total"] or 0):
            return None
        data = {"number": inv.number, "total": float(inv.total or 0), "date": f"{inv.date:%Y-%m-%d}" if getattr(inv, "date", None) else ""}
        name, phone = c.name, c.phone
    company = (services.get_company_settings().name or "").strip()
    text, params = render_receipt(data, name, company, loyalty.invoice_summary(invoice_id), cfg)
    return queue("receipt", phone, text, ref=data["number"], params=params)


def check_low_stock(now=None, force=False):
    """رسالة واحدة لكل مسؤول فيها الأصناف اللي وصلت لحد الطلب (بتتكرر لنفس الصنف بعد low_stock_repeat_days). بيرجّع عدد الأصناف المبلّغ عنها."""
    cfg = get_config()
    if not cfg["enabled"] or not cfg["low_stock_enabled"]:
        return 0
    recips = split_phones(cfg["low_stock_recipients"])
    if not recips:
        return 0
    from . import services
    now = now or datetime.datetime.now()
    with _lock:
        st = _state()
        if not force:
            if now.hour < cfg["low_stock_hour"] or st.get("low_checked") == now.strftime("%Y-%m-%d"):
                return 0
            st["low_checked"] = now.strftime("%Y-%m-%d")
        sent = st.setdefault("low_sent", {})
        cutoff = now - datetime.timedelta(days=cfg["low_stock_repeat_days"])
        fresh = []
        for r in services.get_stock_balance_report(low_stock_only=True):
            p = r["product"]
            last = sent.get(str(p.id))
            if last and datetime.datetime.fromisoformat(last) > cutoff:
                continue
            fresh.append((p, r["balance"]))
        low_ids = {str(p.id) for p, _ in fresh}
        if fresh:
            lines = [f"• {p.name} ({p.sku}): الرصيد {b:g} / حد الطلب {p.reorder_point:g}" for p, b in fresh[:15]]
            more = f"\n... و{len(fresh) - 15} صنف آخر" if len(fresh) > 15 else ""
            company = (services.get_company_settings().name or "").strip()
            text = f"تنبيه نقص مخزون - {company}\n" + "\n".join(lines) + more
            for ph in recips:
                queue("low_stock", ph, text, ref=f"{len(fresh)} صنف", params=[company, str(len(fresh))])
            for i in low_ids:
                sent[i] = now.isoformat(timespec="seconds")
        # الأصناف اللي رجع رصيدها طبيعي تتشال عشان يتبلّغ عنها لو نزلت تاني
        still = {str(r["product"].id) for r in services.get_stock_balance_report(low_stock_only=True)}
        st["low_sent"] = {k: v for k, v in sent.items() if k in still}
        _save_state(st)
    return len(fresh)


def run_due():
    """بتتنادى دوريًا من الحلقة الخلفية: إعادة الفاشل + فحص النقص اليومي."""
    out = {"retried": 0, "low": 0}
    try:
        out["retried"] = retry_failed()
        out["low"] = check_low_stock()
    except Exception:
        pass
    return out


def list_log(kind=None, status=None, limit=300):
    with get_session() as s:
        q = s.query(NotificationLog)
        if kind:
            q = q.filter(NotificationLog.kind == kind)
        if status:
            q = q.filter(NotificationLog.status == status)
        rows = q.order_by(NotificationLog.id.desc()).limit(limit).all()
        s.expunge_all()
        return rows


def send_test(phone):
    from . import services
    services.require_action("notifications", "edit")
    text = "رسالة تجريبية من نظام ERP ✅"
    return queue("test", phone, text, ref="test", params=["ERP", "test", "0"], force=True)


def send_manual(phone, text):
    from . import services
    services.require_action("notifications", "edit")
    if not (text or "").strip():
        raise ValueError("اكتب نص الرسالة")
    return queue("manual", phone, text.strip(), ref="manual", params=[text.strip()], force=True)
