"""من تجربة لاشتراك: باقات وحدودها، أكواد التفعيل (مرة واحدة)، التفعيل من داخل النسخة، والتذكيرات قبل الانتهاء."""
import datetime
import http.server
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

from erp_app import portal, trial

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY = datetime.date.today()


def _env_clean(extra):
    e = {k: v for k, v in os.environ.items() if k != "ERP_DATABASE_URL"}
    e.update(extra)
    return e


def _tenant_py(slug, code, extra=None):
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=90,
                          env=_env_clean({"ERP_HOME": portal.tenant_home(slug), **(extra or {})}))


def _wait(pred, secs=60):
    end = time.time() + secs
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.5)
    return False


def _post_json(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture(scope="module", autouse=True)
def env(tmp_path_factory):
    old = (portal.HOME, portal.PORT_START, portal.PORTAL_PORT[0])
    portal.HOME = str(tmp_path_factory.mktemp("portal_sub"))
    portal.PORT_START = 19300
    portal.init()
    yield
    for t in portal.list_tenants(True):
        portal.stop_tenant(t)
    portal.HOME, portal.PORT_START, portal.PORTAL_PORT[0] = old


@pytest.fixture(scope="module")
def srv(env):
    s = portal.serve("127.0.0.1", 18701, supervise=False)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:18701"
    s.shutdown(); s.server_close()


@pytest.fixture(scope="module")
def tenant(srv):
    tok = portal.create_invite(5, 30)
    res = portal.signup(tok, "نورة", "0551230001", "شركة اشتراك", ip="5.5.5.5")
    t = portal.get_tenant(res["slug"])
    assert _wait(lambda: portal._port_open(t["port"]), 60)
    return t


def test_plans_and_months():
    pl = portal.plans()
    assert pl["trial"]["max_users"] and {"basic", "pro", "business"} <= set(pl)
    assert portal.add_months(datetime.date(2026, 1, 31), 1) == datetime.date(2026, 2, 28)
    assert portal.add_months(datetime.date(2026, 11, 15), 3) == datetime.date(2027, 2, 15)
    lic = portal.plan_license("pro", True)
    assert lic["paid"] and lic["max_users"] == 10


def test_codes_validation():
    with pytest.raises(ValueError):
        portal.create_codes("trial", 12)
    with pytest.raises(ValueError):
        portal.create_codes("nope", 12)
    with pytest.raises(ValueError):
        portal.create_codes("pro", 0)
    cs = portal.create_codes("pro", 6, 3, "عميل")
    assert len(set(cs)) == 3 and all(c.startswith("ERP-") and len(c) == 18 for c in cs)
    portal.void_code(cs[0])
    with pytest.raises(ValueError):
        portal.activate_code("nonexistent", cs[0], ip="x1")           # ملغي
    for bad in ("", "ERP-AAAA", "ERP-AAAA-BBBB-CCCC"):
        with pytest.raises(ValueError):
            portal.activate_code("nonexistent", bad, ip="x2")


def test_tenant_starts_as_trial_with_limits(tenant):
    t = json.load(open(os.path.join(portal.tenant_home(tenant["slug"]), "trial.json"), encoding="utf-8"))
    assert t["paid"] is False and t["plan"] == "trial" and t["max_users"] == portal.plans()["trial"]["max_users"]


def test_activation_flow_end_to_end(tenant, srv):
    slug = tenant["slug"]
    before = datetime.date.fromisoformat(portal.get_tenant(slug)["expires"])
    code = portal.create_codes("basic", 6, 1, "e2e")[0]
    # من داخل النسخة نفسها (نفس طريق شاشة «الاشتراك»)
    r = _tenant_py(slug, "from erp_app import trial;import json;print(json.dumps(trial.activate('%s')))" % code.lower().replace("-", " "),
                   {"ERP_PORTAL_URL": srv, "ERP_TENANT_SLUG": slug})
    assert r.returncode == 0, r.stderr[-400:]
    res = json.loads(r.stdout.strip().splitlines()[-1])
    assert res["ok"] and res["plan"] == "basic"
    t = portal.get_tenant(slug)
    assert t["paid"] == 1 and t["plan"] == "basic"
    assert datetime.date.fromisoformat(t["expires"]) == portal.add_months(max(before, TODAY), 6)
    lic = json.load(open(os.path.join(portal.tenant_home(slug), "trial.json"), encoding="utf-8"))
    assert lic["paid"] is True and lic["plan_label"] == "أساسية" and lic["max_users"] == 3 and lic["max_branches"] == 1
    # الكود مرة واحدة
    assert _post_json(srv + "/api/activate", {"slug": slug, "code": code})[0] == 400
    assert _post_json(srv + "/api/activate", {"slug": slug, "code": "ERP-ZZZZ-ZZZZ-ZZZZ"})[0] == 400
    # كود تاني بيتجمّع على المدة (مفيش حاجة بتضيع)
    code2 = portal.create_codes("basic", 3, 1)[0]
    assert _post_json(srv + "/api/activate", {"slug": slug, "code": code2})[1]["expires"] == portal.add_months(datetime.date.fromisoformat(t["expires"]), 3).isoformat()


def test_limits_enforced_inside_tenant(tenant):
    slug = tenant["slug"]
    code = """
from erp_app import services as S, trial
S.set_current_user(None)
print('LIMITS', trial.limit('users'), trial.limit('branches'))
ok = 0
for i in range(5):
    try:
        S.create_user('u%d' % i, 'Passw0rd!%d' % i, 'مستخدم %d' % i); ok += 1
    except ValueError as e:
        print('BLOCKED', ok, str(e)[:40]); break
try:
    S.create_branch('B2', 'فرع تاني'); print('BRANCH OK')
except ValueError as e:
    print('BRANCH BLOCKED')
"""
    r = _tenant_py(slug, code)
    out = r.stdout
    assert "LIMITS 3 1" in out, r.stderr[-400:]
    assert "BLOCKED 2" in out            # admin + مستخدمين = 3 (حد الباقة الأساسية)
    assert "BRANCH BLOCKED" in out        # الفرع الافتراضي = 1 = الحد


def test_reminder_kinds():
    k = portal.reminder_kind
    assert [k(d) for d in (10, 7, 5, 4, 3, 1, 0, -1, -7, -8)] == [None, "d7", "d7", "d7", "d3", "d3", "d0", "expired", "expired", None]


def _set_expiry(slug, days):
    d = (TODAY + datetime.timedelta(days=days)).isoformat()
    with sqlite3.connect(os.path.join(portal.HOME, "registry.db")) as c:
        c.execute("update tenants set expires=? where slug=?", (d, slug))
    return d


def test_reminders_manual_links_and_dedupe(tenant):
    slug = tenant["slug"]
    _set_expiry(slug, 6)
    assert portal.reminders_once() == 1
    assert portal.reminders_once() == 0                      # مرة واحدة لكل نوع/تاريخ
    r = portal.list_reminders("link")[0]
    assert r["kind"] == "d7" and r["link"].startswith("https://wa.me/966551230001?text=") and "شركة اشتراك" in r["body"]
    portal.mark_reminder_done(r["id"])
    assert portal.list_reminders("link") == []
    _set_expiry(slug, 2)                                     # نوع أقرب = تذكير جديد
    assert portal.reminders_once() == 1
    d = _set_expiry(slug, 0)
    assert portal.reminders_once() == 1 and "النهارده" in portal.list_reminders("link")[0]["body"]
    # نفس التاريخ ونفس النوع = ما يتكررش، لكن تاريخ انتهاء مختلف (بعد تجديد) = تذكير جديد
    _set_expiry(slug, 6)
    assert portal.reminders_once() == 0
    _set_expiry(slug, 5)
    assert portal.reminders_once() == 1


class _Sink(http.server.BaseHTTPRequestHandler):
    got, fail = [], [False]

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        if self.fail[0]:
            self.send_response(500); self.end_headers(); return
        self.got.append(json.loads(body)); self.send_response(200); self.end_headers()

    def log_message(self, *a):
        pass


def test_reminders_auto_send_via_provider(tenant):
    slug = tenant["slug"]
    sink = http.server.ThreadingHTTPServer(("127.0.0.1", 18702), _Sink)
    threading.Thread(target=sink.serve_forever, daemon=True).start()
    try:
        portal.save_messaging(enabled=True, provider="http", http_url="http://127.0.0.1:18702/send", channel="sms", country_code="966")
        _set_expiry(slug, 3)
        _Sink.fail[0] = True
        assert portal.reminders_once() == 1                   # أول مرة: الإرسال فشل
        r = [x for x in portal.list_reminders() if x["kind"] == "d3"][0]
        assert r["status"] == "failed" and r["attempts"] == 1 and r["error"]
        _Sink.fail[0] = False
        portal.reminders_once()                               # إعادة المحاولة
        r = [x for x in portal.list_reminders() if x["kind"] == "d3"][0]
        assert r["status"] == "sent" and _Sink.got and _Sink.got[-1]["to"] == "966551230001" and "شركة اشتراك" in _Sink.got[-1]["text"]
        portal.reminders_once()
        assert len(_Sink.got) == 1                            # ما اتبعتش تاني
        # الأسرار ما بتتمسحش لما الحقل يتسيب فاضي
        portal.save_messaging(provider="twilio", twilio_token="SECRET")
        portal.save_messaging(provider="twilio", twilio_token="")
        assert portal.messaging_cfg()["twilio_token"] == "SECRET"
        assert oct(os.stat(os.path.join(portal.HOME, "messaging.json")).st_mode & 0o777) == "0o600"
    finally:
        portal.save_messaging(enabled=False, provider="none")
        sink.shutdown(); sink.server_close()


def test_admin_actions_over_http(tenant, srv):
    import base64
    auth = {"Authorization": "Basic " + base64.b64encode(f"admin:{portal.admin_password()}".encode()).decode()}

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    op = urllib.request.build_opener(NoRedirect)

    def act(**f):
        f["csrf"] = portal._csrf()
        try:
            op.open(urllib.request.Request(srv + "/admin/act", headers=auth, data=urllib.parse.urlencode(f).encode()))
        except urllib.error.HTTPError as e:
            assert e.code == 303
            return urllib.parse.unquote(e.headers["Location"])
    loc = act(a="code_new", plan="pro", m="12", n="2", label="http")
    assert loc.count("ERP-") == 2
    before = portal.get_tenant(tenant["slug"])
    loc = act(a="sub", k=tenant["slug"], plan="pro", m="1")
    assert "تم التفعيل" in loc and portal.get_tenant(tenant["slug"])["plan"] == "pro"
    req = urllib.request.Request(srv + "/admin", headers=auth)
    page = urllib.request.urlopen(req, timeout=10).read().decode()
    assert "أكواد التفعيل" in page and "احترافية" in page and "تذكيرات بانتظار" in page
    assert before["expires"] < portal.get_tenant(tenant["slug"])["expires"]
