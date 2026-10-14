import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from erp_app import notify

GOT = []


class _H(BaseHTTPRequestHandler):
    code = 200

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        GOT.append({"path": self.path, "headers": dict(self.headers), "body": self.rfile.read(n).decode("utf-8")})
        self.send_response(_H.code); self.end_headers(); self.wfile.write(b'{"ok":1}')

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def srv():
    h = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=h.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{h.server_port}"
    h.shutdown()


@pytest.fixture(autouse=True)
def sync(monkeypatch):
    monkeypatch.setattr(notify, "SYNC", True)
    GOT.clear(); _H.code = 200


def test_phone_normalize():
    n = notify.normalize_phone
    assert n("0501234567") == "966501234567"
    assert n("+966 50 123 4567") == "966501234567"
    assert n("00966501234567") == "966501234567"
    assert n("501234567") == "966501234567"
    with pytest.raises(ValueError):
        n("12")


def test_http_receipt_and_retry(S, shop, srv):
    S.update_customer(shop["cust"], phone="0501234567", notify_opt_in=True)
    notify.save_config(enabled=True, provider="http", http_url=srv + "/sms", http_headers='{"X-Key": "k1"}')
    # العميل مش موافق → مفيش رسالة
    c2 = S.create_customer(name="مش موافق", phone="0507654321")
    r = S.create_pos_sale(c2, [{"product_id": shop["burger"], "quantity": 1, "unit_price": 100}], payment_method_id=1, terminal_id=shop["term"])
    assert GOT == []
    r = S.create_pos_sale(shop["cust"], [{"product_id": shop["burger"], "quantity": 2, "unit_price": 100}], payment_method_id=1, terminal_id=shop["term"])
    assert len(GOT) == 1
    body = json.loads(GOT[0]["body"])
    assert body["to"] == "966501234567" and "230.00" in body["text"] and "شركة اختبار" in body["text"]
    assert GOT[0]["headers"].get("X-Key") == "k1"
    log = notify.list_log(kind="receipt")[0]
    assert log.status == "sent" and log.attempts == 1
    # فشل ثم إعادة محاولة
    _H.code = 500
    lid = notify.send_manual("0501234567", "اختبار فشل")
    assert notify.list_log(kind="manual")[0].status == "failed"
    _H.code = 200
    assert notify.retry_failed() == 1
    row = notify.list_log(kind="manual")[0]
    assert row.status == "sent" and row.attempts == 2


def test_sale_never_breaks_when_provider_down(S, shop):
    notify.save_config(enabled=True, provider="http", http_url="http://127.0.0.1:9/x")
    r = S.create_pos_sale(shop["cust"], [{"product_id": shop["cola"], "quantity": 1, "unit_price": 5}], payment_method_id=1, terminal_id=shop["term"])
    assert r["invoice_id"]
    assert notify.list_log(kind="receipt")[0].status == "failed"


def test_whatsapp_cloud_and_twilio_payloads(S, monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw)); return None
    from erp_app import msgproviders
    monkeypatch.setattr(msgproviders, "_post", fake_post)
    notify.save_config(enabled=True, provider="whatsapp_cloud", wa_phone_number_id="123", wa_token="TOK", wa_template_name="")
    notify.send_manual("0501234567", "مرحبا")
    url, kw = calls[-1]
    assert url.endswith("/123/messages") and kw["json"]["text"]["body"] == "مرحبا" and kw["json"]["to"] == "966501234567"
    assert kw["headers"]["Authorization"] == "Bearer TOK"
    notify.save_config(wa_template_name="receipt_ar")
    notify.send_manual("0501234567", "مرحبا")
    assert calls[-1][1]["json"]["template"]["name"] == "receipt_ar"
    notify.save_config(provider="twilio", twilio_sid="AC1", twilio_token="T", twilio_from="+15551234567")
    notify.send_manual("0501234567", "hi")
    url, kw = calls[-1]
    assert "Accounts/AC1/Messages.json" in url and kw["data"]["To"] == "whatsapp:+966501234567" and kw["data"]["From"] == "whatsapp:+15551234567"
    notify.save_config(channel="sms")
    notify.send_manual("0501234567", "hi")
    assert calls[-1][1]["data"]["To"] == "+966501234567" and calls[-1][1]["data"]["From"] == "+15551234567"
    notify.save_config(channel="whatsapp")


def test_low_stock_alert(S, shop, srv, monkeypatch):
    pid = S.create_product("LOW1", "صنف ناقص", sale_price=5, cost_price=2, reorder_point=10)
    notify.save_config(enabled=True, provider="http", http_url=srv + "/sms", http_headers="{}", low_stock_enabled=True, low_stock_recipients="0501111111, 0502222222")
    GOT.clear()
    assert notify.check_low_stock(force=True) >= 1
    texts = [json.loads(g["body"]) for g in GOT]
    assert len(texts) == 2 and all("صنف ناقص" in t["text"] for t in texts)
    GOT.clear()
    assert notify.check_low_stock(force=True) == 0 and GOT == []     # مفيش تكرار قبل المدة


def test_provider_none_gives_link_and_secrets_masked(S):
    notify.save_config(enabled=True, provider="none")
    lid = notify.send_manual("0501234567", "نص عربي")
    assert notify.list_log(kind="manual")[0].status == "link"
    assert notify.wa_link("0501234567", "نص").startswith("https://wa.me/966501234567?text=")
    from erp_app.db import AuditLog, get_session
    notify.save_config(wa_token="SUPERSECRET")
    with get_session() as s:
        rows = [r for r in s.query(AuditLog).filter(AuditLog.action == "config").all() if "wa_token" in (r.changes or "")]
    assert rows and all("SUPERSECRET" not in r.changes for r in rows)
    with pytest.raises(ValueError):
        notify.save_config(provider="http", http_url="ftp://x")
