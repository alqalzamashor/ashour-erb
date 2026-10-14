"""مستقبل webhook لطلبات التوصيل: خادم HTTP صغير مستقل (بورت منفصل، افتراضي 8600) من مكتبة بايثون القياسية.
POST /hook/<source>   مع المفتاح السري في ترويسة  X-Api-Key  أو  Authorization: Bearer ...  (أو ?key=)
GET  /health
ردود: 200 {"ok":true,"order_id":N,"duplicate":bool} | 400 payload غلط | 401 مفتاح غلط | 404 مصدر مجهول | 413 كبير.
لازم HTTPS من أمام الخادم (nginx / ngrok / cloudflared) لو هيتفتح للإنترنت: المفتاح بيعدّي في الترويسة."""
import hmac
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import delivery

MAX_BODY = 1_000_000
_server = {"srv": None, "thread": None}


class _Handler(BaseHTTPRequestHandler):
    server_version = "ERPHook/1"

    def _reply(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/sync/"):
            from . import nodesync
            if nodesync.handle_http(self, "GET", path, ""):
                return
        if path in ("/health", "/healthz"):
            return self._health(path == "/healthz")
        if path == "/agent/jobs":
            if not self._agent_ok():
                return
            import base64
            from . import thermal
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                jobs = thermal.claim_jobs((q.get("station") or [None])[0], limit=10)
            except Exception:      # noqa: BLE001
                return self._reply(500, {"ok": False, "error": "server error"})
            return self._reply(200, {"ok": True, "jobs": [{"id": j["id"], "station": j["station"], "data": base64.b64encode(j["data"]).decode()} for j in jobs]})
        self._reply(404, {"ok": False, "error": "not found"})

    def _health(self, deep):
        """/health بسيط (الخادم شغّال). /healthz بيفحص القاعدة والمجدول (لـ Docker / مراقبة الجاهزية) - 503 لو القاعدة مش شغّالة."""
        if not deep:
            return self._reply(200, {"ok": True})
        out = {"ok": True}
        try:
            from sqlalchemy import text
            from .db import engine
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
            out["db"] = True
        except Exception as ex:      # noqa: BLE001
            return self._reply(503, {"ok": False, "db": False, "error": str(ex)[:200]})
        try:
            from . import scheduler, version
            out["version"] = version.VERSION
            out["scheduler"] = scheduler.status()
            from . import concurrency
            out["ui"] = concurrency.stats()
        except Exception:
            pass
        self._reply(200, out)

    def _agent_ok(self):
        from . import thermal
        auth = self.headers.get("Authorization") or ""
        key = auth[7:].strip() if auth.lower().startswith("bearer ") else (self.headers.get("X-Api-Key") or "")
        tok = thermal.agent_token(create=False)
        if not tok or not hmac.compare_digest(key.encode(), tok.encode()):
            self._reply(401, {"ok": False, "error": "unauthorized"})
            return False
        return True

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        if u.path.startswith("/sync/"):
            from . import nodesync
            if nodesync.handle_http(self, "POST", u.path, ""):
                return
        parts = [p for p in u.path.split("/") if p]
        if len(parts) == 3 and parts[0] == "agent" and parts[1] == "jobs":
            if not self._agent_ok():
                return
            from . import thermal
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(min(max(n, 0), 10000)).decode("utf-8", "replace") or "{}")
                found = thermal.finish_job(int(parts[2]), bool(body.get("ok")), body.get("error", ""))
            except (ValueError, TypeError):
                return self._reply(400, {"ok": False, "error": "bad request"})
            return self._reply(200 if found else 404, {"ok": found})
        if len(parts) != 2 or parts[0] != "hook":
            return self._reply(404, {"ok": False, "error": "not found"})
        cfg = delivery.get_config()
        src = cfg["sources"].get(parts[1])
        if not cfg["enabled"] or src is None:
            return self._reply(404, {"ok": False, "error": "unknown source"})
        key = self.headers.get("X-Api-Key") or ""
        auth = self.headers.get("Authorization") or ""
        if not key and auth.lower().startswith("bearer "):
            key = auth[7:].strip()
        if not key:
            key = (urllib.parse.parse_qs(u.query).get("key") or [""])[0]
        if not hmac.compare_digest(key.encode(), str(src.get("secret", "")).encode()):
            return self._reply(401, {"ok": False, "error": "unauthorized"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = -1
        if n < 0 or n > MAX_BODY:
            return self._reply(413, {"ok": False, "error": "body too large"})
        raw = self.rfile.read(n).decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
            oid, created = delivery.ingest(parts[1], payload, src.get("mapping"), raw)
        except ValueError as ex:        # JSON غلط أو بيانات ناقصة
            return self._reply(400, {"ok": False, "error": str(ex)})
        except Exception:               # noqa: BLE001
            return self._reply(500, {"ok": False, "error": "server error"})
        self._reply(200, {"ok": True, "order_id": oid, "duplicate": not created})

    def log_message(self, *a):
        pass


def start(host=None, port=None):
    """يشغّل الخادم في خيط خلفي (مرة واحدة لكل عملية). بيرجّع (host, port) أو None لو مقفول/مشغّل قبل كده/البورت مشغول."""
    if _server["srv"] is not None:
        return None
    import os
    cfg = delivery.get_config()
    # الخادم الداخلي بيشتغل دايمًا على السيرفر (healthz + وكيل الطباعة + webhook التوصيل لو مفعّل)؛ متغيرات البيئة تتغلب على الإعداد المحفوظ
    host = host or os.environ.get("ERP_INTERNAL_HOST") or cfg["host"]
    port = int(port if port is not None else (os.environ.get("ERP_INTERNAL_PORT") or cfg["port"]))
    try:
        srv = ThreadingHTTPServer((host, port), _Handler)
    except OSError:
        return None
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    _server.update(srv=srv, thread=t)
    return host, srv.server_port


def stop():
    srv = _server["srv"]
    if srv:
        srv.shutdown(); srv.server_close()
    _server.update(srv=None, thread=None)


def running():
    return _server["srv"] is not None
