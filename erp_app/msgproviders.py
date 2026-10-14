"""إرسال الرسائل عبر المزوّدات (واتساب Cloud / Twilio / HTTP) - من غير أي اعتماد على قاعدة البيانات عشان تستخدمها البرنامج وبوابة التجارب."""
import json
import re

TIMEOUT = 15


def normalize_phone(phone, country_code="966"):
    """رقم دولي بأرقام فقط من غير +: 0501234567 → 966501234567. بيرمي ValueError لو شكله غلط."""
    raw = str(phone or "").strip()
    d = re.sub(r"\D", "", raw)
    if d.startswith("00"):
        d = d[2:]
    elif raw.startswith("+"):
        pass
    elif d.startswith("0"):
        d = country_code + d[1:]
    elif not d.startswith(country_code) and len(d) <= 10:
        d = country_code + d
    if not 8 <= len(d) <= 15:
        raise ValueError(f"رقم الجوال غير صحيح: {phone}")
    return d



def _post(url, **kw):
    import requests
    r = requests.post(url, timeout=TIMEOUT, **kw)
    if not 200 <= r.status_code < 300:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r


def _send_via_provider(cfg, channel, to, text, params):
    p = cfg["provider"]
    if p == "whatsapp_cloud":
        if channel != "whatsapp":
            raise RuntimeError("واتساب Cloud للواتساب فقط")
        url = f"https://graph.facebook.com/{cfg['wa_api_version']}/{cfg['wa_phone_number_id']}/messages"
        if cfg["wa_template_name"]:
            body = {"messaging_product": "whatsapp", "to": to, "type": "template",
                    "template": {"name": cfg["wa_template_name"], "language": {"code": cfg["wa_template_lang"]},
                                 "components": [{"type": "body", "parameters": [{"type": "text", "text": str(x)} for x in (params or [text])]}]}}
        else:
            body = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
        _post(url, headers={"Authorization": f"Bearer {cfg['wa_token']}"}, json=body)
    elif p == "twilio":
        pre = "whatsapp:" if channel == "whatsapp" else ""
        frm = cfg["twilio_from"]
        if channel == "whatsapp" and not frm.startswith("whatsapp:"):
            frm = "whatsapp:" + frm
        _post(f"https://api.twilio.com/2010-04-01/Accounts/{cfg['twilio_sid']}/Messages.json",
              auth=(cfg["twilio_sid"], cfg["twilio_token"]), data={"To": f"{pre}+{to}", "From": frm, "Body": text})
    elif p == "http":
        body = cfg["http_body"].replace("{to}", json.dumps(to)[1:-1]).replace("{text}", json.dumps(text, ensure_ascii=False)[1:-1])
        _post(cfg["http_url"], headers={"Content-Type": "application/json; charset=utf-8", **json.loads(cfg["http_headers"] or "{}")}, data=body.encode("utf-8"))
    else:
        raise RuntimeError("مفيش مزوّد مفعّل")
