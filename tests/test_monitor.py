"""مراقبة الشركات وتنبيهات المشرف: اكتشاف نسخة واقعة/غير سليمة/نسخ احتياطي فاشل/قرص، إرسال مرة واحدة، إعادة التذكير، الإغلاق التلقائي، صفحة المراقبة."""
import datetime
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from erp_app import portal, portal_ops as ops

GOT = []


class _H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        GOT.append(json.loads(self.rfile.read(n).decode("utf-8")))
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def hook():
    h = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=h.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{h.server_port}/hook"
    h.shutdown()


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch, hook):
    monkeypatch.setattr(portal, "HOME", str(tmp_path))
    portal.init()
    portal.save_messaging(alert_webhook=hook)
    GOT.clear()
    ops._cache.update(t=0.0, rows=[]); ops._down_since.clear(); ops._bad_health.clear(); ops._size_cache.clear()
    monkeypatch.setattr(ops, "DOWN_SECS", 0)
    with portal._lock, portal._db() as c:
        exp = (datetime.date.today() + datetime.timedelta(days=20)).isoformat()
        c.execute("INSERT INTO tenants(slug,company,owner,phone,port,created,expires) VALUES('acme','شركة أكمي','س','0501','19900',?,?)", ("2026-01-01", exp))
    os.makedirs(portal.tenant_home("acme"), exist_ok=True)
    yield


def _patch(monkeypatch, running=True, hz=None):
    monkeypatch.setattr(portal, "is_running", lambda t: running)
    monkeypatch.setattr(ops, "_healthz", lambda t: hz if hz is not None else {"ok": True, "db": True, "version": "1", "scheduler": {"backup": {"ok": True, "last": datetime.datetime.now().isoformat(timespec="seconds")}}, "ui": {}})


def test_healthy_no_alert(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(ops, "server_stats", lambda: {"time": "t", "disk_free_gb": 50, "disk_free_pct": 50, "mem_avail_pct": 50, "mem_avail_mb": 4000})
    assert ops.alerts_check(ops.collect(0)) == 0 and GOT == [] and ops.list_alerts("open") == []


def test_down_alert_once_then_renotify_then_resolve(monkeypatch):
    _patch(monkeypatch, running=False)
    sv = {"time": "t", "disk_free_gb": 50, "disk_free_pct": 50, "mem_avail_pct": 50, "mem_avail_mb": 4000}
    monkeypatch.setattr(ops, "server_stats", lambda: sv)
    ops.alerts_check(ops.collect(0))
    assert len(GOT) == 1 and "واقفة" in GOT[0]["text"] and len(ops.list_alerts("open")) == 1
    ops.alerts_check(ops.collect(0))
    assert len(GOT) == 1                                           # من غير تكرار
    monkeypatch.setattr(ops, "RENOTIFY", 0)
    ops.alerts_check(ops.collect(0))
    assert len(GOT) == 2 and GOT[1]["text"].startswith("⏰")
    monkeypatch.setattr(ops, "RENOTIFY", 99999)
    _patch(monkeypatch)
    ops.alerts_check(ops.collect(0))
    assert ops.list_alerts("open") == [] and GOT[-1]["text"].startswith("✅")


def test_unhealthy_needs_three_strikes_and_backup_failed(monkeypatch):
    _patch(monkeypatch, hz={"ok": False, "db": False, "error": "boom", "scheduler": {"backup": {"ok": False, "error": "no space", "last": "2026-01-01T00:00:00"}}})
    monkeypatch.setattr(ops, "server_stats", lambda: {"time": "t"})
    ops.alerts_check(ops.collect(0)); ops.alerts_check(ops.collect(0))
    kinds = {a["kind"] for a in ops.list_alerts("open")}
    assert "tenant_unhealthy" not in kinds and "backup_failed" in kinds and "backup_stale" in kinds
    ops.alerts_check(ops.collect(0))
    assert "tenant_unhealthy" in {a["kind"] for a in ops.list_alerts("open")}


def test_disk_and_memory_alerts(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(ops, "server_stats", lambda: {"time": "t", "disk_free_gb": 0.5, "disk_free_pct": 3, "mem_avail_pct": 2, "mem_avail_mb": 100})
    ops.alerts_check(ops.collect(0))
    assert {"disk_low", "mem_low"} <= {a["kind"] for a in ops.list_alerts("open")}


def test_suspended_or_expired_tenant_is_not_alerted(monkeypatch):
    _patch(monkeypatch, running=False)
    monkeypatch.setattr(ops, "server_stats", lambda: {"time": "t"})
    portal.set_status("acme", "suspended")
    ops.alerts_check(ops.collect(0))
    assert ops.list_alerts("open") == []


def test_log_tail_and_traversal(monkeypatch):
    with open(os.path.join(portal.tenant_home("acme"), "server.log"), "w", encoding="utf-8") as f:
        f.write("ok\nTraceback (most recent call last)\nValueError: x\n")
    d = ops.log_tail("acme")
    assert d["errors"] == 1 and "ValueError" in d["tail"]
    with pytest.raises(ValueError):
        ops.log_tail("../x")


def test_pages_render(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(ops, "server_stats", lambda: {"time": "t", "disk_free_gb": 50, "disk_free_pct": 50, "mem_avail_pct": 50, "mem_avail_mb": 4000})
    html = ops.monitor_page("csrf", "h")
    assert "شركة أكمي" in html and "🟢" in html
    snap = ops.snapshot()
    assert snap["summary"]["total"] == 1 and snap["tenants"][0]["healthy"]
    assert "المراقبة" in portal.admin_page("h")


def test_activity_marker(tmp_path, monkeypatch):
    from erp_app import monitor
    monkeypatch.setattr(monitor, "PATH", str(tmp_path / "activity.json"))
    monitor.mark_login("ali")
    p = tmp_path / "activity.json"
    assert p.exists() and json.loads(p.read_text())["user"] == "ali"


def test_drill_failure_alert(monkeypatch):
    _patch(monkeypatch, hz={"ok": True, "db": True, "scheduler": {"drill": {"ok": False, "last": "2026-10-01T00:00:00", "error": "RuntimeError: bad"}}, "ui": {}})
    monkeypatch.setattr(ops, "server_stats", lambda: {"time": "t"})
    ops.alerts_check(ops.collect(0))
    assert "drill_failed" in {a["kind"] for a in ops.list_alerts("open")}
