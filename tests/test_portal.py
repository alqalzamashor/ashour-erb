"""بوابة التجارب: دعوات، تسجيل، تجهيز قاعدة فاضية حقيقية، تشغيل نسخة، انتهاء التجربة وإيقافها، صفحة المشرف."""
import base64
import datetime
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

from erp_app import portal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module", autouse=True)
def env(tmp_path_factory):
    old = (portal.HOME, portal.PORT_START)
    portal.HOME = str(tmp_path_factory.mktemp("portal"))
    portal.PORT_START = 19100
    portal.init()
    yield
    for t in portal.list_tenants(True):
        portal.stop_tenant(t)
    portal.HOME, portal.PORT_START = old


def _login(slug, pw, user="admin"):
    """يجرّب تسجيل الدخول على قاعدة الشركة (في عملية مستقلة لأن db عامة لكل عملية)."""
    code = "from erp_app import services;import sys\ntry:\n u=services.authenticate_user('%s',sys.argv[1]);print('LOGIN', bool(u))\nexcept ValueError as e: print('ERR', e)" % user
    r = subprocess.run([sys.executable, "-c", code, pw], cwd=ROOT, env={**{k: v for k, v in os.environ.items() if k != "ERP_DATABASE_URL"}, "ERP_HOME": portal.tenant_home(slug)}, capture_output=True, text=True, timeout=60)
    return r.stdout.strip()


def _wait(pred, secs=60):
    end = time.time() + secs
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.5)
    return False


def _get(url, headers=None, data=None):
    req = urllib.request.Request(url, headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def test_invite_rules():
    with pytest.raises(ValueError):
        portal.create_invite(0)
    with pytest.raises(ValueError):
        portal.create_invite(5, 0)
    tok = portal.create_invite(2, 30, "اختبار")
    assert portal.invite_state(portal.get_invite(tok)) == (True, "")
    portal.set_invite_active(tok, False)
    assert portal.invite_state(portal.get_invite(tok))[0] is False
    assert portal.invite_state(None)[0] is False


def test_signup_validation():
    tok = portal.create_invite(3)
    for args in [("", "0501234567", "شركة"), ("أحمد", "123", "شركة"), ("أحمد", "0501234567", "")]:
        with pytest.raises(ValueError):
            portal.signup(tok, *args, ip="9.9.9.9")
    with pytest.raises(ValueError):
        portal.signup("nope-token", "أحمد", "0501234567", "شركة", ip="9.9.9.9")
    assert portal.get_invite(tok)["uses"] == 0                  # الفشل ما بيستهلكش من الدعوة
    assert portal.norm_phone("٠٥٠-١٢٣ 4567") == "0501234567"


def test_full_lifecycle():
    tok = portal.create_invite(1, 30)
    res = portal.signup(tok, "سعد", "+966 50 111 2222", "شركة النجوم", ip="1.1.1.1")
    slug, port = res["slug"], res["port"]
    t = portal.get_tenant(slug)
    assert res["expires"] == (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    assert os.path.exists(os.path.join(portal.tenant_home(slug), "data", "erp.db"))
    # الدعوة استُنفدت + الرقم متسجل قبل كده
    assert portal.get_invite(tok)["uses"] == 1
    with pytest.raises(ValueError):
        portal.signup(tok, "تاني", "0509999999", "شركة", ip="1.1.1.1")
    tok2 = portal.create_invite(5)
    with pytest.raises(ValueError):
        portal.signup(tok2, "سعد", "966501112222", "شركة تانية", ip="1.1.1.1")
    # النسخة اشتغلت وبتخدم الواجهة و healthz
    assert _wait(lambda: portal._port_open(port) and portal._port_open(port + portal.INTERNAL_OFFSET)), "النسخة ما اشتغلتش"
    assert _get(f"http://127.0.0.1:{port}/")[0] == 200
    assert _get(f"http://127.0.0.1:{port + portal.INTERNAL_OFFSET}/healthz")[0] == 200
    # القاعدة فاضية وباسم الشركة، والدخول بالبيانات المُرسلة
    db = sqlite3.connect(os.path.join(portal.tenant_home(slug), "data", "erp.db"))
    assert db.execute("select name from company_settings").fetchone()[0] == "شركة النجوم"
    assert db.execute("select count(*) from products").fetchone()[0] == 0
    assert db.execute("select count(*) from sales_invoices").fetchone()[0] == 0 if "sales_invoices" in {r[0] for r in db.execute("select name from sqlite_master")} else True
    db.close()
    assert _login(slug, res["password"]) == "LOGIN True"
    assert _login(slug, "غلط-غلط-غلط").startswith("LOGIN False")
    # انتهاء التجربة: الدخول مرفوض والمشرف يوقف النسخة
    with sqlite3.connect(os.path.join(portal.HOME, "registry.db")) as c:
        c.execute("update tenants set expires=? where slug=?", ((datetime.date.today() - datetime.timedelta(days=1)).isoformat(), slug))
    portal._write_trial_file(portal.tenant_home(slug), (datetime.date.today() - datetime.timedelta(days=1)).isoformat())
    assert _login(slug, res["password"]).startswith("ERR انتهت الفترة التجريبية")
    portal.supervise_once()
    assert _wait(lambda: not portal._port_open(port), 30), "النسخة المنتهية ما اتوقفتش"
    # التمديد بيرجّعها
    new = portal.extend(slug, 30)
    assert new > datetime.date.today().isoformat()
    assert _login(slug, res["password"]) == "LOGIN True"
    assert _wait(lambda: portal._port_open(port), 60)
    # إيقاف يدوي ثم حذف نهائي
    portal.set_status(slug, "suspended")
    assert _wait(lambda: not portal._port_open(port), 30)
    portal.delete_tenant(slug)
    assert not os.path.exists(portal.tenant_home(slug))
    assert portal.get_tenant(slug)["status"] == "deleted"
    # الرقم يتحرر بعد الحذف
    assert portal.signup(tok2, "سعد", "966501112222", "شركة جديدة", ip="2.2.2.2")["slug"] != slug


def test_http_pages():
    srv = portal.serve("127.0.0.1", 18700, supervise=False)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:18700"
    try:
        assert _get(base + "/s/bad-token-123")[1].count("غير صحيح") == 1
        tok = portal.create_invite(2, 14, "http")
        code, page = _get(base + f"/s/{tok}")
        assert code == 200 and "14 يوم" in page and 'name="company"' in page
        code, page = _get(base + f"/s/{tok}", data=urllib.parse.urlencode({"owner": "س", "phone": "1", "company": "x"}).encode())
        assert code == 400 and "اسمك" in page
        # المشرف: محمي بكلمة مرور و CSRF
        assert _get(base + "/admin")[0] == 401
        auth = {"Authorization": "Basic " + base64.b64encode(f"admin:{portal.admin_password()}".encode()).decode()}
        code, page = _get(base + "/admin", auth)
        assert code == 200 and tok in page
        assert _get(base + "/admin/act", auth, data=b"a=inv_new&n=3&d=30&csrf=bad")[0] == 403
        form = urllib.parse.urlencode({"a": "inv_off", "k": tok, "csrf": portal._csrf()}).encode()

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        op = urllib.request.build_opener(NoRedirect)
        with pytest.raises(urllib.error.HTTPError) as ei:
            op.open(urllib.request.Request(base + "/admin/act", headers=auth, data=form))
        assert ei.value.code == 303
        assert portal.get_invite(tok)["active"] == 0
    finally:
        srv.shutdown()
        srv.server_close()


def test_signup_start_failure_not_blocking(monkeypatch):
    tok = portal.create_invite(3, 30)
    real = portal.start_tenant
    monkeypatch.setattr(portal, "start_tenant", lambda t: (_ for _ in ()).throw(OSError("boom")))
    res = portal.signup(tok, "منى", "0561110001", "شركة أ", ip="3.3.3.3")   # الفشل ما يوقعش التسجيل
    assert res["password"] and portal.get_tenant(res["slug"])
    monkeypatch.setattr(portal, "start_tenant", real)
    portal.delete_tenant(res["slug"])


def test_signup_undelivered_can_retry():
    tok = portal.create_invite(3, 30)
    res = portal.signup(tok, "علي", "0561110002", "شركة ب", ip="3.3.3.4")
    portal._undelivered.add(res["slug"])          # محاكاة: الرد ما وصلش للمستخدم
    res2 = portal.signup(tok, "علي", "0561110002", "شركة ب", ip="3.3.3.4")
    assert res2["slug"] != res["slug"]
    assert portal.get_invite(tok)["uses"] == 1
    with pytest.raises(ValueError):                # بعد التسليم الرقم يتقفل عادي
        portal.signup(tok, "علي", "0561110002", "شركة ب", ip="3.3.3.4")
    portal.delete_tenant(res2["slug"])


def test_pid_alive_safe():
    from erp_app.proc import pid_alive
    assert pid_alive(os.getpid())
    assert not pid_alive(0) and not pid_alive(None)
    import subprocess, sys
    p = subprocess.Popen([sys.executable, "-c", "pass"]); p.wait()
    assert not pid_alive(p.pid)


def test_tenant_env_utf8():
    env = portal._env_for({"slug": "cabc", "port": 9100})
    assert env["PYTHONUTF8"] == "1" and env["PYTHONIOENCODING"] == "utf-8"


def test_domain_mode_https(monkeypatch, tmp_path):
    monkeypatch.setenv("ERP_PUBLIC_DOMAIN", "Erp.Example.com")
    monkeypatch.setenv("ERP_ACME_EMAIL", "ops@example.com")
    monkeypatch.setenv("ERP_CADDYFILE", str(tmp_path / "Caddyfile"))
    monkeypatch.delenv("ERP_CADDY_RELOAD", raising=False)
    monkeypatch.delenv("ERP_CADDY_CMD", raising=False)
    assert portal.public_domain() == "erp.example.com" and portal._scheme() == "https"
    t = {"slug": "cabc12345", "port": 9100}
    assert portal.tenant_url(t, "10.0.0.1") == "https://cabc12345.erp.example.com"
    assert portal.portal_base("x") == "https://portal.erp.example.com"
    assert portal._env_for(t)["ERP_HOST"] == "127.0.0.1"
    tok = portal.create_invite(1, 30)
    res = portal.signup(tok, "هدى", "0561110099", "شركة https", ip="4.4.4.4")
    cfg = (tmp_path / "Caddyfile").read_text(encoding="utf-8")
    assert "email ops@example.com" in cfg
    assert f'{res["slug"]}.erp.example.com {{' in cfg and f"reverse_proxy 127.0.0.1:{res['port']}\n" in cfg
    assert f"reverse_proxy 127.0.0.1:{res['port'] + portal.INTERNAL_OFFSET}" in cfg      # /agent و /hook
    assert "portal.erp.example.com {" in cfg
    portal.delete_tenant(res["slug"])
    assert portal.sync_caddy(force=True)
    assert res["slug"] not in (tmp_path / "Caddyfile").read_text(encoding="utf-8")
    assert "https://" + res["slug"] + ".erp.example.com" in portal.signup_done("h", res)


def test_no_domain_mode_unchanged(monkeypatch):
    monkeypatch.delenv("ERP_PUBLIC_DOMAIN", raising=False)
    assert portal.caddy_config() == "" and portal.sync_caddy() is False
    assert portal.tenant_url({"slug": "c1", "port": 9101}, "h") == "http://h:9101"


def test_pwa_assets_and_install_page(tmp_path, monkeypatch):
    import json
    from erp_app import files
    monkeypatch.setattr(files, "ASSETS_DIR", str(tmp_path))
    files.ensure_pwa()
    m = json.load(open(tmp_path / "manifest.json", encoding="utf-8"))
    assert m["short_name"] == "ashour" and m["display"] == "standalone" and m["id"] == "/"
    for n in ("icon-192.png", "icon-maskable-512.png", "apple-touch-icon-180.png", "logo.png", "loading-animation.png"):
        assert (tmp_path / "icons" / n).exists(), n
    assert "install.html" in os.listdir(tmp_path) and "__NAME__" not in (tmp_path / "install.html").read_text(encoding="utf-8")
