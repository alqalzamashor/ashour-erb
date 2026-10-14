"""بوابة التجارب: تدّي كل شخص عندك رابط دعوة، يفتحه ويكتب اسمه ورقم جواله واسم شركته، فيتعمل له فورًا
قاعدة بيانات جديدة فاضية ونسخة مستقلة من البرنامج (على بورت خاص) صالحة لفترة تجريبية (30 يوم افتراضيًا).

الفكرة: كل شركة تجريبية = نسخة كاملة معزولة (مجلد بيانات + قاعدة SQLite أو PostgreSQL + عملية server.py على بورت خاص).
البوابة (عملية واحدة) بتوفّر: صفحة التسجيل /s/<token>، صفحة المشرف /admin، ومشرف عمليات بيشغّل النسخ ويوقف المنتهية.
متغيرات: ERP_PORTAL_HOME / ERP_PORTAL_PORT(8700) / ERP_PORTAL_ADMIN_PASSWORD / ERP_PUBLIC_HOST / ERP_PUBLIC_SCHEME(http) / ERP_PUBLIC_DOMAIN (HTTPS لكل شركة عبر Caddy) / ERP_ACME_EMAIL / ERP_CADDYFILE / ERP_CADDY_RELOAD /
ERP_TRIAL_PORT_START(9100) / ERP_TRIAL_MAX_TENANTS(50) / ERP_TRIAL_DAYS(30) / ERP_TRIAL_PG_ADMIN_URL (اختياري: PostgreSQL لكل شركة)."""
import datetime
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.abspath(os.environ.get("ERP_PORTAL_HOME") or os.path.join(os.environ.get("ERP_HOME") or ROOT, "portal"))
PORT_START = int(os.environ.get("ERP_TRIAL_PORT_START", "9100"))
INTERNAL_OFFSET = 1000                      # البورت الداخلي = بورت الواجهة + 1000 (على 127.0.0.1 بس)
MAX_TENANTS = int(os.environ.get("ERP_TRIAL_MAX_TENANTS", "50"))
DEFAULT_DAYS = int(os.environ.get("ERP_TRIAL_DAYS", "30"))
SIGNUP_PER_IP_HOUR = 5
_lock = threading.RLock()
_ip_hits = {}
_procs = {}                                 # slug -> Popen (للي بدأناه نحن)
_fail = {}                                  # slug -> (عدد المحاولات، وقت آخر محاولة)
PORTAL_PORT = [int(os.environ.get("ERP_PORTAL_PORT", "8700"))]


def _p(*a):
    return os.path.join(HOME, *a)


def _db():
    os.makedirs(HOME, exist_ok=True)
    c = sqlite3.connect(_p("registry.db"), timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init():
    os.makedirs(_p("tenants"), exist_ok=True)
    with _lock, _db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS invites(token TEXT PRIMARY KEY, label TEXT DEFAULT '', max_uses INTEGER NOT NULL, uses INTEGER NOT NULL DEFAULT 0,
            trial_days INTEGER NOT NULL, created TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS tenants(id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE NOT NULL, company TEXT NOT NULL, owner TEXT NOT NULL,
            phone TEXT NOT NULL, invite TEXT, port INTEGER UNIQUE NOT NULL, db_url TEXT DEFAULT '', created TEXT NOT NULL, expires TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active', ip TEXT DEFAULT '', plan TEXT NOT NULL DEFAULT 'trial', paid INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS codes(code TEXT PRIMARY KEY, plan TEXT NOT NULL, months INTEGER NOT NULL, note TEXT DEFAULT '', created TEXT NOT NULL,
            used_by TEXT, used_at TEXT, void INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT NOT NULL, kind TEXT NOT NULL, expires TEXT NOT NULL, created TEXT NOT NULL,
            status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, error TEXT DEFAULT '', body TEXT DEFAULT '', link TEXT DEFAULT '', UNIQUE(slug, kind, expires));
        """)
        cols = {r[1] for r in c.execute("PRAGMA table_info(tenants)")}
        for col, ddl in (("plan", "TEXT NOT NULL DEFAULT 'trial'"), ("paid", "INTEGER NOT NULL DEFAULT 0")):
            if col not in cols:
                c.execute(f"ALTER TABLE tenants ADD COLUMN {col} {ddl}")
    _ensure_plans_file()
    from . import portal_ops
    portal_ops.init_schema()


def today():
    return datetime.date.today()


# ------------------------------------------------------------------ الباقات
DEFAULT_PLANS = {
    "trial": {"label": "تجريبية", "max_users": 5, "max_branches": 2},
    "basic": {"label": "أساسية", "max_users": 3, "max_branches": 1},
    "pro": {"label": "احترافية", "max_users": 10, "max_branches": 5},
    "business": {"label": "أعمال", "max_users": 50, "max_branches": None},
}


def _ensure_plans_file():
    p = _p("plans.json")
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_PLANS, f, ensure_ascii=False, indent=2)


def plans():
    """الباقات من plans.json (تقدر تعدّلها: label / max_users / max_branches، و null = بلا حد). 'trial' إلزامية."""
    try:
        with open(_p("plans.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    out = {k: dict(v) for k, v in DEFAULT_PLANS.items()}
    for k, v in (data or {}).items():
        if isinstance(v, dict):
            out[k] = {"label": v.get("label") or k, "max_users": v.get("max_users"), "max_branches": v.get("max_branches")}
    return out


def plan_license(plan, paid):
    pl = plans().get(plan) or plans()["trial"]
    return {"plan": plan, "plan_label": pl["label"], "paid": bool(paid), "max_users": pl.get("max_users"), "max_branches": pl.get("max_branches")}


def add_months(d, months):
    y, m = divmod(d.month - 1 + int(months), 12)
    y, m = d.year + y, m + 1
    import calendar
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


# ------------------------------------------------------------------ أكواد التفعيل
_ALPHA = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _norm_code(c):
    return re.sub(r"[^A-Z0-9]", "", str(c or "").upper())


def _fmt_code(raw):
    return "ERP-" + "-".join(raw[i:i + 4] for i in range(0, 12, 4))


def create_codes(plan, months, count=1, note=""):
    if plan not in plans() or plan == "trial":
        raise ValueError("باقة غير صحيحة")
    months, count = int(months), int(count)
    if not 1 <= months <= 60 or not 1 <= count <= 500:
        raise ValueError("المدة (1-60 شهر) والعدد (1-500)")
    out = []
    with _lock, _db() as c:
        for _ in range(count):
            raw = "".join(secrets.choice(_ALPHA) for _ in range(12))
            code = _fmt_code(raw)
            c.execute("INSERT INTO codes(code,plan,months,note,created) VALUES(?,?,?,?,?)", (code, plan, months, (note or "")[:80], today().isoformat()))
            out.append(code)
    return out


def list_codes(limit=300):
    with _db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM codes ORDER BY created DESC, rowid DESC LIMIT ?", (limit,))]


def void_code(code):
    with _lock, _db() as c:
        c.execute("UPDATE codes SET void=1 WHERE code=? AND used_by IS NULL", (code,))


def apply_subscription(slug, plan, months):
    """يفعّل/يجدّد اشتراك شركة: بيضيف المدة على الأطول من (الانتهاء الحالي، النهارده)، ويحدّث الباقة والحدود في ملف ترخيص النسخة."""
    t = get_tenant(slug)
    if not t or t["status"] == "deleted":
        raise ValueError("شركة غير موجودة")
    if plan not in plans() or plan == "trial":
        raise ValueError("باقة غير صحيحة")
    new = add_months(max(datetime.date.fromisoformat(t["expires"]), today()), months).isoformat()
    with _lock, _db() as c:
        c.execute("UPDATE tenants SET expires=?, plan=?, paid=1 WHERE slug=?", (new, plan, slug))
    _write_trial_file(tenant_home(slug), new, **plan_license(plan, True))
    if t["status"] == "active":
        start_tenant(get_tenant(slug))
    return {"plan": plan, "plan_label": plans()[plan]["label"], "expires": new}


_act_hits = {}


def activate_code(slug, code, ip=""):
    """يستهلك كود تفعيل (مرة واحدة) لشركة. بيرمي ValueError برسالة مفهومة."""
    now = time.time()
    hits = [h for h in _act_hits.get(ip, []) if now - h < 3600]
    if ip and len(hits) >= 10:
        raise ValueError("محاولات كتير - حاول بعد ساعة")
    _act_hits[ip] = hits + [now]
    raw = _norm_code(code)
    if raw.startswith("ERP"):
        raw = raw[3:]
    if len(raw) != 12:
        raise ValueError("كود التفعيل غير صحيح")
    full = _fmt_code(raw)
    with _lock:
        with _db() as c:
            r = c.execute("SELECT * FROM codes WHERE code=?", (full,)).fetchone()
            if not r or r["void"]:
                raise ValueError("كود التفعيل غير صحيح")
            if r["used_by"]:
                raise ValueError("الكود ده اتستخدم قبل كده")
        res = apply_subscription(slug, r["plan"], r["months"])
        with _db() as c:
            c.execute("UPDATE codes SET used_by=?, used_at=? WHERE code=?", (slug, today().isoformat(), full))
    return res


# ------------------------------------------------------------------ الدعوات
def create_invite(max_uses, trial_days=None, label=""):
    max_uses = int(max_uses)
    if not 1 <= max_uses <= 10000:
        raise ValueError("عدد الأشخاص لازم بين 1 و10000")
    days = DEFAULT_DAYS if trial_days in (None, "") else int(trial_days)
    if not 1 <= days <= 365:
        raise ValueError("مدة التجربة لازم بين 1 و365 يوم")
    tok = secrets.token_urlsafe(9)
    with _lock, _db() as c:
        c.execute("INSERT INTO invites(token,label,max_uses,trial_days,created) VALUES(?,?,?,?,?)", (tok, (label or "")[:80], max_uses, days, today().isoformat()))
    return tok


def list_invites():
    with _db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM invites ORDER BY created DESC, rowid DESC")]


def set_invite_active(token, active):
    with _lock, _db() as c:
        c.execute("UPDATE invites SET active=? WHERE token=?", (1 if active else 0, token))


def get_invite(token):
    with _db() as c:
        r = c.execute("SELECT * FROM invites WHERE token=?", (token or "",)).fetchone()
        return dict(r) if r else None


def invite_state(inv):
    """(مفتوح؟، سبب الإغلاق)"""
    if not inv:
        return False, "رابط الدعوة غير صحيح"
    if not inv["active"]:
        return False, "رابط الدعوة اتوقّف"
    if inv["uses"] >= inv["max_uses"]:
        return False, "رابط الدعوة استُنفد (وصل الحد الأقصى من التسجيلات)"
    return True, ""


# ------------------------------------------------------------------ الشركات
def norm_phone(s):
    d = re.sub(r"\D", "", (s or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")))
    return d


def list_tenants(include_deleted=False):
    with _db() as c:
        q = "SELECT * FROM tenants" + ("" if include_deleted else " WHERE status!='deleted'") + " ORDER BY id DESC"
        return [dict(r) for r in c.execute(q)]


def get_tenant(slug):
    with _db() as c:
        r = c.execute("SELECT * FROM tenants WHERE slug=?", (slug,)).fetchone()
        return dict(r) if r else None


def tenant_home(slug):
    return _p("tenants", slug)


def _free_port(c):
    used = {r[0] for r in c.execute("SELECT port FROM tenants")}
    for p in range(PORT_START, PORT_START + 1000):
        if p in used or p + INTERNAL_OFFSET in used:
            continue
        if _port_open(p) or _port_open(p + INTERNAL_OFFSET):
            continue
        return p
    raise RuntimeError("مفيش بورتات فاضية للتجارب")


def _port_open(port, host="127.0.0.1"):
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def _norm_pg(url):
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def _pg_create(slug):
    """لو ERP_TRIAL_PG_ADMIN_URL متضبط: بيعمل قاعدة PostgreSQL جديدة فاضية للشركة وبيرجّع رابطها، وإلا '' (SQLite داخل مجلد الشركة)."""
    admin = os.environ.get("ERP_TRIAL_PG_ADMIN_URL", "").strip()
    if not admin:
        return ""
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    name = "trial_" + slug
    eng = create_engine(_norm_pg(admin), isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as c:
            c.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        eng.dispose()
    return make_url(_norm_pg(admin)).set(database=name).render_as_string(hide_password=False)


def _pg_drop(slug):
    admin = os.environ.get("ERP_TRIAL_PG_ADMIN_URL", "").strip()
    if not admin:
        return
    from sqlalchemy import create_engine, text
    eng = create_engine(_norm_pg(admin), isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "trial_{slug}" WITH (FORCE)'))
    finally:
        eng.dispose()


def _env_for(t):
    env = dict(os.environ)
    for k in ("FLET_SECRET_KEY", "ERP_ADMIN_PASSWORD", "ERP_DATABASE_URL", "ERP_PORT", "ERP_HOST", "ERP_INTERNAL_PORT", "ERP_INTERNAL_HOST"):
        env.pop(k, None)
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")      # ويندوز: stdout لملف بيبقى cp1252 وبيفشل مع العربي
    env.update(ERP_TENANT_SLUG=t["slug"], ERP_PORTAL_URL=f"http://127.0.0.1:{PORTAL_PORT[0]}",
               ERP_HOME=tenant_home(t["slug"]), ERP_HOST="127.0.0.1" if public_domain() else "0.0.0.0", ERP_PORT=str(t["port"]), ERP_INTERNAL_HOST="127.0.0.1", ERP_INTERNAL_PORT=str(t["port"] + INTERNAL_OFFSET))
    if t.get("db_url"):
        env["ERP_DATABASE_URL"] = t["db_url"]
    return env


def _write_trial_file(home, expires, **info):
    p = os.path.join(home, "trial.json")
    cur = {}
    try:
        cur = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        pass
    cur.update(info)
    cur["expires"] = expires
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False)
    os.replace(p + ".tmp", p)


_undelivered = set()                        # تسجيلات اتعملت ولسه بياناتها ما اتسلّمتش للمستخدم


def signup(token, owner, phone, company, ip=""):
    """يسجّل شركة تجريبية جديدة. بيرجّع dict فيه رقم البورت وكلمة مرور المدير (بتظهر مرة واحدة بس) وتاريخ الانتهاء."""
    owner, company = (owner or "").strip(), (company or "").strip()
    ph = norm_phone(phone)
    if len(owner) < 2 or len(owner) > 100:
        raise ValueError("اكتب اسمك (حرفين على الأقل)")
    if len(company) < 2 or len(company) > 120:
        raise ValueError("اكتب اسم الشركة (حرفين على الأقل)")
    if not 8 <= len(ph) <= 15:
        raise ValueError("رقم الجوال غير صحيح")
    now = time.time()
    hits = [t for t in _ip_hits.get(ip, []) if now - t < 3600]
    if ip and len(hits) >= SIGNUP_PER_IP_HOUR:
        raise ValueError("محاولات كتير من نفس الجهاز - حاول بعد ساعة")
    _ip_hits[ip] = hits + [now]
    with _lock:
        inv = get_invite(token)
        ok, why = invite_state(inv)
        if not ok:
            raise ValueError(why)
        with _db() as c:
            old = c.execute("SELECT slug FROM tenants WHERE phone=? AND status!='deleted'", (ph,)).fetchone()
            if old and old["slug"] in _undelivered:
                # تسجيل سابق ما وصلش للمستخدم (فشل تشغيل/انقطاع قبل عرض كلمة المرور) - بنشيله ونكمّل
                delete_tenant(old["slug"])
                with _db() as c2:
                    c2.execute("UPDATE invites SET uses=MAX(uses-1,0) WHERE token=(SELECT invite FROM tenants WHERE slug=?)", (old["slug"],))
                _undelivered.discard(old["slug"])
                old = None
                inv = get_invite(token)
                ok, why = invite_state(inv)
                if not ok:
                    raise ValueError(why)
            if old:
                raise ValueError("الرقم ده سجّل تجربة قبل كده. تواصل معنا لو محتاج مساعدة")
            if c.execute("SELECT COUNT(*) FROM tenants WHERE status!='deleted'").fetchone()[0] >= MAX_TENANTS:
                raise ValueError("وصلنا للحد الأقصى من النسخ التجريبية حاليًا")
            port = _free_port(c)
        slug = "c" + secrets.token_hex(4)
        home = tenant_home(slug)
        pw = secrets.token_urlsafe(9)
        expires = (today() + datetime.timedelta(days=inv["trial_days"])).isoformat()
        db_url = ""
        try:
            db_url = _pg_create(slug)
            os.makedirs(home)
            env = _env_for({"slug": slug, "port": port, "db_url": db_url})
            r = subprocess.run([sys.executable, "-m", "erp_app.provision"], cwd=ROOT, env=env, timeout=300, capture_output=True, text=True,
                               input=json.dumps({"company": company, "owner": owner, "phone": ph, "admin_password": pw, "expires": expires, **plan_license("trial", False)}))
            if r.returncode != 0 or "OK" not in r.stdout:
                raise RuntimeError((r.stderr or r.stdout)[-300:])
            with _db() as c:
                c.execute("INSERT INTO tenants(slug,company,owner,phone,invite,port,db_url,created,expires,ip) VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (slug, company, owner, ph, token, port, db_url, today().isoformat(), expires, ip))
                c.execute("UPDATE invites SET uses=uses+1 WHERE token=?", (token,))
            _undelivered.add(slug)
        except Exception:
            shutil.rmtree(home, ignore_errors=True)
            try:
                _pg_drop(slug)
            except Exception:      # noqa: BLE001
                pass
            raise
    t = get_tenant(slug)
    try:
        sync_caddy()
    except Exception:      # noqa: BLE001
        pass
    try:
        start_tenant(t)
    except Exception:      # noqa: BLE001  - المشرف هيحاول يشغّلها؛ المهم المستخدم ياخد بياناته
        pass
    for _ in range(60):                      # نستنى النسخة تقوم (لحد 30 ثانية) عشان الرابط يفتح أول ما يظهر
        if _port_open(port):
            break
        time.sleep(0.5)
    _undelivered.discard(slug)
    return {"slug": slug, "port": port, "username": "admin", "password": pw, "expires": expires, "company": company}


# ------------------------------------------------------------------ تشغيل النسخ
def _read_pid(slug):
    try:
        return int(open(os.path.join(tenant_home(slug), "server.pid")).read().strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid):
    from .proc import pid_alive
    return pid_alive(pid)


def is_running(t):
    return _port_open(t["port"])


_starts = {}                                # slug -> [أوقات بدء التشغيل اللي عملناها] (لعدد إعادة التشغيل)


def start_tenant(t):
    """بيشغّل نسخة الشركة (لو شغّالة فعلًا - حتى لو من تشغيل سابق للبوابة - بيتبناها)."""
    if is_running(t):
        return True
    pid = _read_pid(t["slug"])
    if pid and _pid_alive(pid):
        return True                       # لسه بتقوم
    from . import portal_ops
    portal_ops.rotate_log(t["slug"])
    log = open(os.path.join(tenant_home(t["slug"]), "server.log"), "ab")
    kw = {"start_new_session": True} if os.name != "nt" else {}
    pr = subprocess.Popen([sys.executable, os.path.join(ROOT, "server.py")], cwd=ROOT, env=_env_for(t), stdout=log, stderr=log, stdin=subprocess.DEVNULL, **kw)
    _procs[t["slug"]] = pr
    _starts.setdefault(t["slug"], []).append(time.time())
    del _starts[t["slug"]][:-50]
    return True


def stop_tenant(t):
    pr = _procs.pop(t["slug"], None)
    pid = pr.pid if pr else _read_pid(t["slug"])
    if pid and _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(50):
            if not _pid_alive(pid):
                break
            time.sleep(0.1)
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except (OSError, AttributeError):
                pass
    if pr:
        try:
            pr.wait(timeout=2)
        except Exception:      # noqa: BLE001
            pass


def is_expired(t):
    return datetime.date.fromisoformat(t["expires"]) < today()


def supervise_once():
    """دورة واحدة: يشغّل النسخ اللي لازم تشتغل ويوقف الموقوفة/المنتهية."""
    try:
        sync_caddy()
    except Exception:      # noqa: BLE001
        pass
    for t in list_tenants():
        want = t["status"] == "active" and not is_expired(t)
        running = is_running(t)
        if want and not running:
            n, last = _fail.get(t["slug"], (0, 0))
            if time.time() - last >= min(300, 10 * 2 ** n):
                _fail[t["slug"]] = (n + 1, time.time())
                try:
                    start_tenant(t)
                except Exception:      # noqa: BLE001
                    pass
            continue
        if want and running:
            _fail.pop(t["slug"], None)
        if not want and (running or _read_pid(t["slug"])):
            stop_tenant(t)


def supervisor_loop(interval=10):
    last_rem = 0.0
    last_alert = 0.0
    while True:
        try:
            supervise_once()
        except Exception:      # noqa: BLE001
            pass
        if time.time() - last_rem >= 3600:
            last_rem = time.time()
            try:
                reminders_once()
            except Exception:      # noqa: BLE001
                pass
        if time.time() - last_alert >= 60:
            last_alert = time.time()
            try:
                from . import portal_ops
                portal_ops.alerts_check()
            except Exception:      # noqa: BLE001
                pass
        time.sleep(interval)


def extend(slug, days):
    t = get_tenant(slug)
    if not t:
        raise ValueError("شركة غير موجودة")
    base = max(datetime.date.fromisoformat(t["expires"]), today())
    new = (base + datetime.timedelta(days=int(days))).isoformat()
    with _lock, _db() as c:
        c.execute("UPDATE tenants SET expires=? WHERE slug=?", (new, slug))
    _write_trial_file(tenant_home(slug), new)
    if t["status"] == "active":
        start_tenant(get_tenant(slug))
    return new


def set_status(slug, status):
    with _lock, _db() as c:
        c.execute("UPDATE tenants SET status=? WHERE slug=?", (status, slug))
    t = get_tenant(slug)
    if status != "active":
        stop_tenant(t)
    else:
        start_tenant(t)


def delete_tenant(slug, purge=True):
    t = get_tenant(slug)
    if not t:
        return
    stop_tenant(t)
    with _lock, _db() as c:
        c.execute("UPDATE tenants SET status='deleted' WHERE slug=?", (slug,))
    if purge:
        shutil.rmtree(tenant_home(slug), ignore_errors=True)
        try:
            _pg_drop(slug)
        except Exception:      # noqa: BLE001
            pass


# ------------------------------------------------------------------ التذكيرات قبل الانتهاء
MSG_DEFAULTS = {"enabled": False, "provider": "none", "channel": "whatsapp", "country_code": os.environ.get("ERP_COUNTRY_CODE", "966"),
                "wa_phone_number_id": "", "wa_token": "", "wa_template_name": "", "wa_template_lang": "ar", "wa_api_version": "v20.0",
                "twilio_sid": "", "twilio_token": "", "twilio_from": "", "http_url": "", "http_headers": "{}", "http_body": '{"to": "{to}", "text": "{text}"}',
                "alert_phones": "", "alert_webhook": ""}
_SECRET_KEYS = ("wa_token", "twilio_token")
CONTACT = os.environ.get("ERP_PORTAL_CONTACT", "")


def messaging_cfg():
    cfg = dict(MSG_DEFAULTS)
    try:
        with open(_p("messaging.json"), encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save_messaging(**kw):
    cfg = messaging_cfg()
    for k, v in kw.items():
        if k not in MSG_DEFAULTS:
            continue
        if k in _SECRET_KEYS and not str(v or "").strip():
            continue                       # فاضي = سيب القيمة القديمة
        cfg[k] = bool(v) if k == "enabled" else str(v).strip()
    if cfg["provider"] not in ("none", "whatsapp_cloud", "twilio", "http"):
        raise ValueError("مزوّد غير معروف")
    if cfg["channel"] not in ("whatsapp", "sms"):
        raise ValueError("قناة غير معروفة")
    fd = os.open(_p("messaging.json"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg


def reminder_kind(days_left):
    if days_left < 0:
        return "expired" if days_left >= -7 else None
    if days_left == 0:
        return "d0"
    if days_left <= 3:
        return "d3"
    if days_left <= 7:
        return "d7"
    return None


def reminder_text(t, kind, d):
    what = "اشتراكك" if t.get("paid") else "فترتك التجريبية"
    if kind == "expired":
        head = f"{what} لشركة {t['company']} انتهى بتاريخ {t['expires']} والنسخة متوقفة."
    elif kind == "d0":
        head = f"{what} لشركة {t['company']} بينتهي النهارده ({t['expires']})."
    else:
        head = f"{what} لشركة {t['company']} هينتهي بعد {d} يوم ({t['expires']})."
    how = "للتفعيل أو التجديد: ادخل البرنامج ← الإدارة ← الاشتراك وأدخل كود التفعيل." + (f" أو تواصل معنا: {CONTACT}" if CONTACT else "")
    return f"مرحبًا {t['owner']}،\n{head}\n{how}\nبياناتك محفوظة ولن تُحذف."


def _wa_link(phone, text, cc):
    from .msgproviders import normalize_phone
    return f"https://wa.me/{normalize_phone(phone, cc)}?text={urllib.parse.quote(text)}"


def reminders_once():
    """يسجّل التذكيرات المستحقة (مرة لكل شركة/نوع/تاريخ انتهاء) ويرسل المتاح منها عبر المزوّد، أو يحضّر رابط واتساب للإرسال اليدوي."""
    from .msgproviders import _send_via_provider, normalize_phone
    cfg = messaging_cfg()
    auto = cfg["enabled"] and cfg["provider"] != "none"
    made = 0
    for t in list_tenants():
        if t["status"] != "active":
            continue
        d = (datetime.date.fromisoformat(t["expires"]) - today()).days
        kind = reminder_kind(d)
        if not kind:
            continue
        text = reminder_text(t, kind, d)
        try:
            link = _wa_link(t["phone"], text, cfg["country_code"])
        except ValueError:
            link = ""
        with _lock, _db() as c:
            cur = c.execute("INSERT OR IGNORE INTO reminders(slug,kind,expires,created,status,body,link) VALUES(?,?,?,?,?,?,?)",
                            (t["slug"], kind, t["expires"], today().isoformat(), "queued" if auto else "link", text, link))
            made += cur.rowcount
    if auto:
        with _db() as c:
            rows = [dict(r) for r in c.execute("SELECT r.*, t.phone FROM reminders r JOIN tenants t ON t.slug=r.slug WHERE r.status IN ('queued','failed') AND r.attempts<3")]
        for r in rows:
            err = ""
            try:
                _send_via_provider(cfg, cfg["channel"], normalize_phone(r["phone"], cfg["country_code"]), r["body"], [r["body"]])
            except Exception as ex:      # noqa: BLE001
                err = str(ex)[:300]
            with _lock, _db() as c:
                c.execute("UPDATE reminders SET status=?, attempts=attempts+1, error=? WHERE id=?", ("failed" if err else "sent", err, r["id"]))
    return made


def list_reminders(status=None, limit=100):
    with _db() as c:
        q = "SELECT r.*, t.company, t.phone FROM reminders r LEFT JOIN tenants t ON t.slug=r.slug" + (" WHERE r.status=?" if status else "") + " ORDER BY r.id DESC LIMIT ?"
        return [dict(r) for r in c.execute(q, ((status, limit) if status else (limit,)))]


def mark_reminder_done(rid):
    with _lock, _db() as c:
        c.execute("UPDATE reminders SET status='sent_manual' WHERE id=? AND status IN ('link','failed')", (int(rid),))


# ------------------------------------------------------------------ مشرف البوابة
def admin_password():
    pw = os.environ.get("ERP_PORTAL_ADMIN_PASSWORD", "").strip()
    if pw:
        return pw
    p = _p("portal_admin_password.txt")
    try:
        return open(p, encoding="utf-8").read().strip()
    except OSError:
        pass
    pw = secrets.token_urlsafe(12)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(pw)
    return pw


def _csrf():
    return hmac.new(admin_password().encode(), b"csrf", hashlib.sha256).hexdigest()[:32]


def _host(handler):
    h = os.environ.get("ERP_PUBLIC_HOST") or (handler.headers.get("Host") or "localhost").rsplit(":", 1)[0]
    return h.strip("[]")


def public_domain():
    """وضع الدومين: لو ERP_PUBLIC_DOMAIN متحدد، كل شركة بتاخد https://<رمزها>.<الدومين> ومحمية بـ HTTPS عن طريق Caddy."""
    return (os.environ.get("ERP_PUBLIC_DOMAIN") or "").strip().strip(".").lower()


def _scheme():
    return "https" if public_domain() else os.environ.get("ERP_PUBLIC_SCHEME", "http")


def tenant_url(t, host):
    d = public_domain()
    return f'https://{t["slug"]}.{d}' if d else f'{_scheme()}://{host}:{t["port"]}'


def portal_base(host):
    d = public_domain()
    if d:
        return f'https://{os.environ.get("ERP_PORTAL_SUBDOMAIN", "portal")}.{d}'
    return f'{_scheme()}://{host}:{os.environ.get("ERP_PORTAL_PORT", "8700")}'


def caddy_config():
    """Caddyfile كامل: بوابة التجارب + كل شركة شغّالة على نطاقها الفرعي (شهادة HTTPS تلقائية). وكيل الطباعة /agent/ و/hook/ على البورت الداخلي."""
    d = public_domain()
    if not d:
        return ""
    email = (os.environ.get("ERP_ACME_EMAIL") or "").strip()
    out = ["# مولَّد تلقائيًا من البوابة - ما تعدّلوش بإيدك (بيتكتب من جديد عند أي تغيير)"]
    if email:
        out.append("{\n\temail %s\n}" % email)
    out.append("%s.%s {\n\tencode gzip\n\treverse_proxy 127.0.0.1:%s\n}" % (os.environ.get("ERP_PORTAL_SUBDOMAIN", "portal"), d, PORTAL_PORT[0]))
    for t in sorted(list_tenants(), key=lambda r: r["slug"]):
        if t["status"] == "deleted":
            continue
        out.append("%s.%s {\n\tencode gzip\n\thandle /agent/* {\n\t\treverse_proxy 127.0.0.1:%d\n\t}\n\thandle /hook/* {\n\t\treverse_proxy 127.0.0.1:%d\n\t}\n\thandle {\n\t\treverse_proxy 127.0.0.1:%d\n\t}\n}"
                   % (t["slug"], d, t["port"] + INTERNAL_OFFSET, t["port"] + INTERNAL_OFFSET, t["port"]))
    return "\n\n".join(out) + "\n"


_caddy_hash = [None]


def sync_caddy(force=False):
    """بيكتب Caddyfile لو اتغيّر، وبيعمل reload لـ Caddy (لو ERP_CADDY_RELOAD=1 أو ERP_CADDY_CMD متحدد). بيرجّع True لو اتحدّث."""
    cfg = caddy_config()
    if not cfg:
        return False
    h = hashlib.sha256(cfg.encode("utf-8")).hexdigest()
    if h == _caddy_hash[0] and not force:
        return False
    path = os.environ.get("ERP_CADDYFILE") or _p("Caddyfile")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(cfg)
    os.replace(path + ".tmp", path)
    _caddy_hash[0] = h
    cmd = os.environ.get("ERP_CADDY_CMD") or ("caddy" if os.environ.get("ERP_CADDY_RELOAD") == "1" else "")
    if cmd:
        try:
            subprocess.run([cmd, "reload", "--config", path, "--adapter", "caddyfile"], timeout=30, capture_output=True)
        except Exception:      # noqa: BLE001
            _caddy_hash[0] = None          # نحاول تاني في الدورة الجاية
    return True


E = html.escape
CSS = """body{font-family:Tahoma,'Noto Sans Arabic','DejaVu Sans',sans-serif;background:#f4f5fa;margin:0;color:#1d1d3a}
.w{max-width:560px;margin:40px auto;padding:0 16px}.wide{max-width:1000px}.c{background:#fff;border-radius:16px;padding:26px;box-shadow:0 2px 10px #0001;margin-bottom:18px}
h1{font-size:22px;margin:0 0 6px}h2{font-size:17px}p.s{color:#6b6d85;margin:0 0 18px;font-size:14px}label{display:block;margin:12px 0 4px;font-size:13px;color:#444}
input{width:100%;box-sizing:border-box;padding:11px;border:1px solid #c9cbe0;border-radius:10px;font-size:15px;font-family:inherit}
button{background:#6c4de0;color:#fff;border:0;border-radius:10px;padding:11px 20px;font-size:15px;cursor:pointer;margin-top:16px;font-family:inherit}
button.g{background:#eee;color:#333;margin:0 2px;padding:5px 10px;font-size:12px}.err{background:#fde8e8;color:#b00020;padding:10px;border-radius:10px;margin-bottom:12px}
.ok{background:#e6f7ee;color:#0a6b3a;padding:12px;border-radius:10px}code{background:#eef;padding:3px 8px;border-radius:6px;direction:ltr;display:inline-block;font-size:15px}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:8px;border-bottom:1px solid #eee;text-align:right}form.i{display:inline}"""


def _page(body, wide=False, title="ashour ERP"):
    return f'<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(title)}</title><style>{CSS}</style></head><body><div class="w{" wide" if wide else ""}">{body}</div></body></html>'


def signup_form(token, inv, err="", vals=None):
    vals = vals or {}
    ok, why = invite_state(inv)
    if not ok:
        return _page(f'<div class="c"><h1>تعذّر التسجيل</h1><p class="s">{E(why)}</p></div>')
    return _page(f'''<div class="c"><h1>جرّب النظام مجانًا {inv["trial_days"]} يوم</h1><p class="s">سجّل بياناتك وهنجهّز لك نسخة جديدة فاضية خاصة بشركتك فورًا.</p>
{f'<div class="err">{E(err)}</div>' if err else ''}
<form method="post"><label>اسمك</label><input name="owner" required minlength="2" value="{E(vals.get("owner", ""))}">
<label>رقم الجوال</label><input name="phone" required inputmode="tel" dir="ltr" value="{E(vals.get("phone", ""))}">
<label>اسم الشركة</label><input name="company" required minlength="2" value="{E(vals.get("company", ""))}">
<button type="submit">إنشاء قاعدة البيانات التجريبية</button></form></div>''')


def signup_done(host, res):
    link = tenant_url({"slug": res["slug"], "port": res["port"]}, host)
    return _page(f'''<div class="c"><h1>تم تجهيز نسختك 🎉</h1><div class="ok">احفظ البيانات دي دلوقتي - كلمة المرور بتظهر مرة واحدة بس.</div>
<p>رابط الدخول:<br><a href="{E(link)}"><code>{E(link)}</code></a></p><p>اسم المستخدم: <code>admin</code></p><p>كلمة المرور: <code>{E(res["password"])}</code></p>
<p class="s">لو الرابط ما فتحش، استنى نص دقيقة وجرّب تاني (النسخة بتقوم في الخلفية).</p><p>الشركة: {E(res["company"])}<br>الفترة التجريبية تنتهي في: <b>{E(res["expires"])}</b></p>
<p class="s">النسخة فاضية بالكامل. تقدر تغيّر كلمة المرور من داخل البرنامج، وتضيف مستخدمين وأصناف وعملاء.</p>
<a href="{E(link)}"><button>الدخول للنظام</button></a></div>''')


def _hid(cs, a, k="", **extra):
    ex = "".join(f'<input type="hidden" name="{E(n)}" value="{E(str(v))}">' for n, v in extra.items())
    return f'<input type="hidden" name="csrf" value="{cs}"><input type="hidden" name="a" value="{a}"><input type="hidden" name="k" value="{E(k)}">{ex}'


def _alert_badge():
    try:
        from . import portal_ops
        n = len(portal_ops.list_alerts("open"))
    except Exception:      # noqa: BLE001
        return ""
    return f'<span style="color:#d33">({n} تنبيه مفتوح)</span>' if n else ""


def admin_page(host, msg=""):
    cs = _csrf()
    pl = plans()
    plan_opts = "".join(f'<option value="{E(k)}">{E(v["label"])} ({"∞" if v["max_users"] is None else v["max_users"]} مستخدم / {"∞" if v["max_branches"] is None else v["max_branches"]} فرع)</option>' for k, v in pl.items() if k != "trial")
    inv_rows = "".join(
        f'<tr><td>{E(i["label"] or "-")}</td><td dir="ltr"><code>{E(portal_base(host))}/s/{E(i["token"])}</code></td><td>{i["uses"]} / {i["max_uses"]}</td><td>{i["trial_days"]} يوم</td>'
        f'<td>{"مفعّل" if i["active"] else "موقوف"}</td><td><form class="i" method="post" action="/admin/act">{_hid(cs, "inv_off" if i["active"] else "inv_on", i["token"])}<button class="g">{"إيقاف" if i["active"] else "تفعيل"}</button></form></td></tr>'
        for i in list_invites())
    ten_rows = ""
    for t in list_tenants():
        left = (datetime.date.fromisoformat(t["expires"]) - today()).days
        state = {"active": "شغّالة" if is_running(t) else "مش شغّالة", "suspended": "موقوفة"}.get(t["status"], t["status"])
        if left < 0:
            state = "انتهت"
        plan_txt = (pl.get(t["plan"]) or {}).get("label", t["plan"]) + (" ✔ مدفوعة" if t["paid"] else " (تجريبية)")

        def btn(a, label, **extra):
            return f'<form class="i" method="post" action="/admin/act">{_hid(cs, a, t["slug"], **extra)}<button class="g">{label}</button></form>'
        act_form = (f'<form class="i" method="post" action="/admin/act">{_hid(cs, "sub", t["slug"])}<select name="plan" style="font-size:12px">{plan_opts}</select> '
                    f'<input name="m" type="number" min="1" value="12" style="width:60px;display:inline;padding:4px"> شهر <button class="g">تفعيل/تجديد</button></form>')
        ten_rows += (f'<tr><td>{E(t["company"])}</td><td>{E(t["owner"])}</td><td dir="ltr">{E(t["phone"])}</td><td dir="ltr"><a href="{E(tenant_url(t, host))}">{E(tenant_url(t, host).split("://", 1)[1])}</a></td>'
                     f'<td>{E(plan_txt)}</td><td>{E(t["expires"])} ({left} يوم)</td><td>{E(state)}</td><td>{act_form}<br>{btn("ext", "+30 يوم", d=30)}'
                     f'{btn("sus", "إيقاف") if t["status"] == "active" else btn("res", "تشغيل")}{btn("del", "حذف نهائي")}</td></tr>')
    code_rows = ""
    for c in list_codes(100):
        if c["void"]:
            state, cancel = "ملغي", ""
        elif c["used_by"]:
            state, cancel = "اتستخدم: %s %s" % (E(c["used_by"]), E(c["used_at"] or "")), ""
        else:
            state = "متاح"
            cancel = '<form class="i" method="post" action="/admin/act">%s<button class="g">إلغاء</button></form>' % _hid(cs, "code_void", c["code"])
        code_rows += ('<tr><td dir="ltr"><code>%s</code></td><td>%s</td><td>%d شهر</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                      % (E(c["code"]), E((pl.get(c["plan"]) or {}).get("label", c["plan"])), c["months"], E(c["note"]), state, cancel))
    rem = list_reminders("link", 50)
    kinds = {"d7": "قبل 7 أيام", "d3": "قبل 3 أيام", "d0": "آخر يوم", "expired": "انتهى"}
    rem_rows = ""
    for r in rem:
        link = '<a target="_blank" href="%s">فتح واتساب</a>' % E(r["link"]) if r["link"] else "رقم غير صالح"
        rem_rows += ('<tr><td>%s</td><td>%s</td><td>%s</td><td><form class="i" method="post" action="/admin/act">%s<button class="g">تم الإرسال</button></form></td></tr>'
                     % (E(r["company"] or r["slug"]), E(kinds.get(r["kind"], r["kind"])), link, _hid(cs, "rem_done", str(r["id"]))))
    mc = messaging_cfg()
    prov_opts = "".join(f'<option value="{k}"{" selected" if mc["provider"] == k else ""}>{v}</option>' for k, v in (("none", "بدون (روابط واتساب يدوية)"), ("whatsapp_cloud", "واتساب Cloud (ميتا)"), ("twilio", "Twilio"), ("http", "بوابة SMS (HTTP)")))

    def fld(name, label, secret=False):
        v = "" if secret else mc.get(name, "")
        ph = " placeholder='(محفوظ - اتركه فاضي للإبقاء)'" if secret and mc.get(name) else ""
        return f'<label>{label}</label><input name="{name}" value="{E(str(v))}"{ph} dir="ltr">'
    return _page(f'''<div class="c"><h1>إدارة التجارب والاشتراكات</h1>{f'<div class="ok">{E(msg)}</div>' if msg else ''}
<p><a href="/admin/monitor"><b>📊 لوحة المراقبة والتنبيهات</b></a> {_alert_badge()}</p>
<h2>إنشاء رابط دعوة (تجربة)</h2><form method="post" action="/admin/act">{_hid(cs, "inv_new")}
<label>عدد الأشخاص المسموح لهم بالتسجيل</label><input name="n" type="number" min="1" value="10"><label>مدة التجربة (يوم)</label><input name="d" type="number" min="1" value="{DEFAULT_DAYS}">
<label>ملاحظة (اختياري)</label><input name="label"><button>إنشاء الرابط</button></form></div>
<div class="c"><h2>روابط الدعوة</h2><table><tr><th>ملاحظة</th><th>الرابط</th><th>الاستخدام</th><th>المدة</th><th>الحالة</th><th></th></tr>{inv_rows}</table></div>
<div class="c"><h2>الشركات ({len(list_tenants())})</h2><table><tr><th>الشركة</th><th>الاسم</th><th>الجوال</th><th>الرابط</th><th>الباقة</th><th>الانتهاء</th><th>الحالة</th><th></th></tr>{ten_rows}</table></div>
<div class="c"><h2>أكواد التفعيل</h2><form method="post" action="/admin/act">{_hid(cs, "code_new")}
<label>الباقة</label><select name="plan" style="width:100%;padding:10px">{plan_opts}</select><label>المدة (شهر)</label><input name="m" type="number" min="1" value="12">
<label>عدد الأكواد</label><input name="n" type="number" min="1" max="500" value="1"><label>ملاحظة (اسم العميل مثلًا)</label><input name="label"><button>توليد الأكواد</button></form>
<p class="s">العميل بيدخل الكود من داخل برنامجه: الإدارة ← الاشتراك. الكود بيشتغل مرة واحدة وبيتضاف على المدة الحالية. الباقات وحدودها في plans.json.</p>
<table><tr><th>الكود</th><th>الباقة</th><th>المدة</th><th>ملاحظة</th><th>الحالة</th><th></th></tr>{code_rows}</table></div>
<div class="c"><h2>تذكيرات بانتظار الإرسال اليدوي ({len(rem)})</h2><p class="s">بتتولّد تلقائيًا قبل الانتهاء بـ 7 و3 أيام وفي آخر يوم وبعد الانتهاء. اضغط «فتح واتساب» وابعت الرسالة، بعدين «تم الإرسال».</p>
<table><tr><th>الشركة</th><th>النوع</th><th>الرسالة</th><th></th></tr>{rem_rows}</table></div>
<div class="c"><h2>الإرسال التلقائي للتذكيرات</h2><form method="post" action="/admin/act">{_hid(cs, "msg_save")}
<label><input type="checkbox" name="enabled" value="1" style="width:auto"{" checked" if mc["enabled"] else ""}> تفعيل الإرسال التلقائي</label>
<label>المزوّد</label><select name="provider" style="width:100%;padding:10px">{prov_opts}</select>
<label>القناة</label><select name="channel" style="width:100%;padding:10px"><option value="whatsapp"{" selected" if mc["channel"] == "whatsapp" else ""}>واتساب</option><option value="sms"{" selected" if mc["channel"] == "sms" else ""}>SMS</option></select>
{fld("country_code", "كود الدولة (966)")}{fld("wa_phone_number_id", "واتساب: Phone Number ID")}{fld("wa_token", "واتساب: Token", True)}{fld("wa_template_name", "واتساب: اسم القالب (لو لازم)")}
{fld("alert_phones", "أرقام المشرف لتنبيهات الأعطال (مفصولة بفاصلة)")}{fld("alert_webhook", "Webhook للتنبيهات (Slack أو غيره - اختياري)")}
{fld("twilio_sid", "Twilio SID")}{fld("twilio_token", "Twilio Token", True)}{fld("twilio_from", "Twilio From")}{fld("http_url", "HTTP: الرابط")}
<button>حفظ</button></form></div>''', wide=True, title="إدارة التجارب")


class Handler(BaseHTTPRequestHandler):
    server_version = "ERPPortal/1"

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        b = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def _admin_ok(self):
        import base64
        a = self.headers.get("Authorization") or ""
        try:
            user, _, pw = base64.b64decode(a[6:]).decode("utf-8").partition(":") if a.lower().startswith("basic ") else ("", "", "")
        except Exception:      # noqa: BLE001
            user, pw = "", ""
        if user == "admin" and hmac.compare_digest(pw.encode(), admin_password().encode()):
            return True
        self._send(401, _page('<div class="c">مطلوب تسجيل الدخول</div>'), extra={"WWW-Authenticate": 'Basic realm="ERP Portal", charset="UTF-8"'})
        return False

    def _form(self):
        n = min(int(self.headers.get("Content-Length") or 0), 20000)
        return {k: v[0] for k, v in urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace")).items()}

    def _ip(self):
        ip = self.client_address[0]
        if public_domain() and ip in ("127.0.0.1", "::1"):          # ورا Caddy: عنوان العميل الحقيقي من X-Forwarded-For
            xf = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            if xf:
                return xf[:64]
        return ip

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if path == "/healthz":
            return self._send(200, json.dumps({"ok": True}), "application/json")
        m = re.fullmatch(r"/s/([\w-]{6,40})", path)
        if m:
            return self._send(200, signup_form(m.group(1), get_invite(m.group(1))))
        if path in ("/admin/monitor", "/admin/status.json", "/admin/log"):
            if not self._admin_ok():
                return
            from . import portal_ops
            if path == "/admin/status.json":
                return self._send(200, json.dumps(portal_ops.snapshot(), ensure_ascii=False), "application/json; charset=utf-8")
            if path == "/admin/log":
                try:
                    return self._send(200, portal_ops.log_page((q.get("slug") or [""])[0]))
                except ValueError as ex:
                    return self._send(400, _page('<div class="c">%s</div>' % E(str(ex))))
            return self._send(200, portal_ops.monitor_page(_csrf(), _host(self), (q.get("m") or [""])[0]))
        if path == "/admin":
            if self._admin_ok():
                self._send(200, admin_page(_host(self), (q.get("m") or [""])[0]))
            return
        self._send(404, _page('<div class="c"><h1>صفحة غير موجودة</h1></div>'))

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        m = re.fullmatch(r"/s/([\w-]{6,40})", path)
        if m:
            tok, f = m.group(1), self._form()
            try:
                res = signup(tok, f.get("owner"), f.get("phone"), f.get("company"), self._ip())
            except ValueError as ex:
                return self._send(400, signup_form(tok, get_invite(tok), str(ex), f))
            except Exception as ex:      # noqa: BLE001
                import traceback
                traceback.print_exc()
                return self._send(500, signup_form(tok, get_invite(tok), "حصل خطأ أثناء التجهيز، حاول تاني بعد دقيقة", f))
            return self._send(200, signup_done(_host(self), res))
        if path == "/api/activate":
            try:
                n = min(int(self.headers.get("Content-Length") or 0), 2000)
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                res = activate_code(str(body.get("slug", "")), body.get("code", ""), ip="slug:" + str(body.get("slug", "")))
            except ValueError as ex:
                return self._send(400, json.dumps({"ok": False, "error": str(ex)}, ensure_ascii=False), "application/json; charset=utf-8")
            except Exception:      # noqa: BLE001
                return self._send(500, json.dumps({"ok": False, "error": "خطأ في الخدمة"}, ensure_ascii=False), "application/json; charset=utf-8")
            return self._send(200, json.dumps({"ok": True, **res}, ensure_ascii=False), "application/json; charset=utf-8")
        if path == "/admin/act":
            if not self._admin_ok():
                return
            f = self._form()
            if not hmac.compare_digest(f.get("csrf", ""), _csrf()):
                return self._send(403, _page('<div class="c">طلب غير صالح</div>'))
            a, k, msg = f.get("a"), f.get("k", ""), "تم"
            try:
                if a == "inv_new":
                    tok = create_invite(f.get("n"), f.get("d"), f.get("label", ""))
                    msg = f"اتعمل رابط جديد: {portal_base(_host(self))}/s/{tok}"
                elif a in ("inv_on", "inv_off"):
                    set_invite_active(k, a == "inv_on")
                elif a == "ext":
                    msg = "الانتهاء الجديد: " + extend(k, int(f.get("d") or 30))
                elif a == "sub":
                    r = apply_subscription(k, f.get("plan", ""), int(f.get("m") or 12))
                    msg = f"تم التفعيل: {r['plan_label']} حتى {r['expires']}"
                elif a == "code_new":
                    codes = create_codes(f.get("plan", ""), int(f.get("m") or 12), int(f.get("n") or 1), f.get("label", ""))
                    msg = "الأكواد: " + " ، ".join(codes)
                elif a == "code_void":
                    void_code(k)
                elif a == "alert_ok":
                    from . import portal_ops
                    portal_ops.resolve_alert(k)
                    self.send_response(303); self.send_header("Location", "/admin/monitor"); self.end_headers()
                    return
                elif a == "rem_done":
                    mark_reminder_done(k)
                elif a == "msg_save":
                    save_messaging(**{n: f.get(n, "") for n in MSG_DEFAULTS if n != "enabled"}, enabled=f.get("enabled") == "1")
                    msg = "تم حفظ إعدادات الإرسال"
                elif a == "sus":
                    set_status(k, "suspended")
                elif a == "res":
                    set_status(k, "active")
                elif a == "del":
                    delete_tenant(k)
            except (ValueError, TypeError) as ex:
                msg = str(ex)
            self.send_response(303)
            self.send_header("Location", "/admin?m=" + urllib.parse.quote(msg))
            self.end_headers()
            return
        self._send(404, _page('<div class="c"><h1>صفحة غير موجودة</h1></div>'))

    def log_message(self, *a):
        pass


def serve(host="0.0.0.0", port=None, supervise=True):
    init()
    port = int(port or os.environ.get("ERP_PORTAL_PORT", "8700"))
    PORTAL_PORT[0] = port
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    if supervise:
        threading.Thread(target=supervisor_loop, daemon=True).start()
    return srv
