"""وضع السيرفر: الملفات (تنزيل/رفع)، سياسة كلمة المرور وتهيئة المدير، المجدول، healthz، وبروتوكول وكيل الطباعة."""
import base64
import json
import os
import time
import urllib.error
import urllib.request

import pytest

from erp_app import delivery_server, files, scheduler, sounds, thermal


def _req(url, method="GET", body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token is not None:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture(scope="module")
def srv(S):
    h = delivery_server.start("127.0.0.1", 18601)
    assert h
    yield f"http://127.0.0.1:{h[1]}"
    delivery_server.stop()


def test_download_link_and_cleanup(tmp_path):
    p = tmp_path / "تقرير 1.pdf"
    p.write_bytes(b"%PDF-x")
    url = files.publish_download(str(p))
    assert url.startswith("/dl/") and url.endswith(".pdf")
    real = os.path.join(files.ASSETS_DIR, url.lstrip("/"))
    assert open(real, "rb").read() == b"%PDF-x"
    old = time.time() - files.DL_TTL - 10
    os.utime(os.path.dirname(real), (old, old))
    assert files.cleanup() >= 1 and not os.path.exists(real)


def test_upload_path_is_confined():
    rel = files.make_upload_target("../../etc/passwd")
    assert ".." not in rel
    assert files.upload_path(rel).startswith(os.path.realpath(files.UPLOAD_DIR))
    with pytest.raises(ValueError):
        files.upload_path("../../etc/passwd")
    dest = files.keep_upload(__file__, os.path.join(files.UPLOAD_DIR, "keep"))
    assert os.path.exists(dest)


def test_fonts_and_sounds_published():
    files.ensure_fonts()
    assert os.path.exists(os.path.join(files.ASSETS_DIR, "fonts", files.FONT_FILE))
    for k in sounds.SOUND_DEFS:
        assert os.path.exists(os.path.join(files.ASSETS_DIR, "sounds", f"{k}.wav"))
    assert sounds.play("ok", page=None) is False       # من غير صفحة (سياق نظام) ما يرميش استثناء


def test_scheduler_runs_and_reports(S):
    for name, *_ in scheduler.TASKS:
        assert name in ("backup", "reports", "notify", "alerts", "drill", "zatca", "prepaid", "cleanup", "journal_recurring")
    scheduler.run_task("cleanup")
    st = scheduler.status()
    assert st["cleanup"]["ok"] is True


def test_healthz(srv):
    code, out = _req(srv + "/healthz")
    assert code == 200 and out["db"] is True and "version" in out
    assert _req(srv + "/health")[1] == {"ok": True}


def test_print_agent_protocol(S, srv):
    thermal.save_config("receipt", mode="agent", address="")
    tok = thermal.agent_token()
    assert _req(srv + "/agent/jobs?station=receipt")[0] == 401
    assert _req(srv + "/agent/jobs?station=receipt", token="bad")[0] == 401
    ok, msg = thermal.print_test("receipt")
    assert ok, msg
    assert thermal.pending_count() == 1
    code, out = _req(srv + "/agent/jobs?station=receipt", token=tok)
    assert code == 200 and len(out["jobs"]) == 1
    j = out["jobs"][0]
    assert base64.b64decode(j["data"]).startswith(b"\x1b@")
    # الأمر اتسحب: مايتسحبش تاني
    assert _req(srv + "/agent/jobs?station=receipt", token=tok)[1]["jobs"] == []
    assert _req(srv + f"/agent/jobs/{j['id']}", "POST", {"ok": True}, token=tok)[0] == 200
    assert thermal.pending_count() == 0
    assert _req(srv + "/agent/jobs/99999", "POST", {"ok": True}, token=tok)[0] == 404


def test_print_agent_retry_and_fail(S, srv):
    tok = thermal.agent_token()
    thermal.enqueue_job("kitchen", b"x")
    for i in range(thermal.MAX_ATTEMPTS):
        jobs = _req(srv + "/agent/jobs?station=kitchen", token=tok)[1]["jobs"]
        assert len(jobs) == 1, i
        _req(srv + f"/agent/jobs/{jobs[0]['id']}", "POST", {"ok": False, "error": "no paper"}, token=tok)
    assert _req(srv + "/agent/jobs?station=kitchen", token=tok)[1]["jobs"] == []     # بعد 3 محاولات: failed
    assert thermal.pending_count() == 0


def test_agent_token_rotation(S):
    a = thermal.agent_token()
    b = thermal.rotate_agent_token()
    assert a != b and thermal.agent_token() == b


def test_agent_script_roundtrip(S, srv, tmp_path):
    import argparse
    import print_agent
    thermal.save_config("receipt", mode="agent", address="")
    thermal.print_test("receipt")
    out = tmp_path / "printer.bin"
    a = argparse.Namespace(url=srv, token=thermal.agent_token(), station="receipt", mode="file", address=str(out), port=9100)
    assert print_agent.run_once(a) == 1
    assert out.read_bytes().startswith(b"\x1b@")
    assert print_agent.run_once(a) == 0


def test_password_policy_and_forced_change(S):
    with pytest.raises(ValueError):
        S.check_password_policy("123", "admin")
    with pytest.raises(ValueError):
        S.check_password_policy("admin", "admin")
    assert S.must_change_password(S.authenticate_user("admin", "admin")) is True


def test_bootstrap_admin_generates_and_env(S, tmp_path):
    path = str(tmp_path / "pw.txt")
    how, pw = S.bootstrap_admin(None, path)
    assert how == "generated" and pw and S.authenticate_user("admin", "admin") is None
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    assert S.authenticate_user("admin", pw)
    assert S.bootstrap_admin(None, path) == (None, None)       # مرة واحدة بس
