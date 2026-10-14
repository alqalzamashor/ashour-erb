"""مراقبة وتنبيهات بوابة التجارب: حالة كل نسخة (تشغيل، سلامة، آخر دخول، حجم، ذاكرة، نسخ احتياطي) + مؤشرات السيرفر (قرص/ذاكرة/حمل)،
وتنبيهات للمشرف (نسخة وقعت أو غير سليمة، نسخ احتياطي فاشل أو متأخر، قرص أو ذاكرة قاربوا يخلصوا، اقتراب الحد الأقصى للشركات)
بتتبعت على واتساب/SMS (نفس مزوّد التذكيرات) و/أو Webhook (Slack وأي خدمة بتقبل JSON فيه text) وتظهر في لوحة المراقبة.
متغيرات: ERP_ALERT_DISK_MIN_GB (2) / ERP_ALERT_DISK_MIN_PCT (10) / ERP_ALERT_MEM_MIN_PCT (8) / ERP_ALERT_RENOTIFY_HOURS (6) / ERP_ALERT_DOWN_SECS (180)."""
import concurrent.futures
import datetime
import json
import os
import shutil
import threading
import time
import urllib.request

from . import portal as P

DISK_MIN_GB = float(os.environ.get("ERP_ALERT_DISK_MIN_GB", "2"))
DISK_MIN_PCT = float(os.environ.get("ERP_ALERT_DISK_MIN_PCT", "10"))
MEM_MIN_PCT = float(os.environ.get("ERP_ALERT_MEM_MIN_PCT", "8"))
RENOTIFY = float(os.environ.get("ERP_ALERT_RENOTIFY_HOURS", "6")) * 3600
BACKUP_STALE_HOURS = float(os.environ.get("ERP_ALERT_BACKUP_STALE_HOURS", "6"))
DOWN_SECS = float(os.environ.get("ERP_ALERT_DOWN_SECS", "180"))
_lock = threading.Lock()
_cache = {"t": 0.0, "rows": []}
_size_cache = {}
_down_since = {}
_bad_health = {}


def init_schema():
    with P._db() as c:
        c.executescript("""CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, kind TEXT NOT NULL, subject TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT 'warn', message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open', notified INTEGER NOT NULL DEFAULT 0,
            last_notified REAL NOT NULL DEFAULT 0, resolved_at TEXT);""")


# ------------------------------------------------------------------ السيرفر
def server_stats():
    out = {"time": datetime.datetime.now().isoformat(timespec="seconds")}
    try:
        du = shutil.disk_usage(P.HOME)
        out.update(disk_total_gb=round(du.total / 1e9, 1), disk_free_gb=round(du.free / 1e9, 1), disk_free_pct=round(du.free / du.total * 100, 1))
    except OSError:
        pass
    try:
        mi = {}
        for line in open("/proc/meminfo"):
            k, _, v = line.partition(":")
            mi[k] = int(v.split()[0])
        out.update(mem_total_mb=mi["MemTotal"] // 1024, mem_avail_mb=mi["MemAvailable"] // 1024, mem_avail_pct=round(mi["MemAvailable"] / mi["MemTotal"] * 100, 1))
    except (OSError, KeyError, ValueError):
        pass
    try:
        out["load1"] = round(os.getloadavg()[0], 2)
        out["cpus"] = os.cpu_count()
    except (OSError, AttributeError):
        pass
    return out


# ------------------------------------------------------------------ النسخ
def _dir_mb(path):
    now = time.time()
    hit = _size_cache.get(path)
    if hit and now - hit[0] < 300:
        return hit[1]
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    mb = round(total / 1e6, 1)
    _size_cache[path] = (now, mb)
    return mb


def _rss_mb(slug):
    pid = P._read_pid(slug)
    if not pid:
        return None
    try:
        for line in open(f"/proc/{pid}/status"):
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024)
    except (OSError, ValueError):
        pass
    return None


def _healthz(t):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{t['port'] + P.INTERNAL_OFFSET}/healthz", timeout=2) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as ex:      # noqa: BLE001
        return {"ok": False, "error": str(ex)[:120]}


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def tenant_row(t):
    home = P.tenant_home(t["slug"])
    running = P.is_running(t)
    hz = _healthz(t) if running else {"ok": False, "error": "غير شغّالة"}
    sched = hz.get("scheduler") or {}
    bk = sched.get("backup") or {}
    ui = hz.get("ui") or {}
    dr = sched.get("drill") or {}
    act = _read_json(os.path.join(home, "activity.json"))
    left = (datetime.date.fromisoformat(t["expires"]) - P.today()).days
    starts = [x for x in P._starts.get(t["slug"], []) if time.time() - x < 3600]
    return {"slug": t["slug"], "company": t["company"], "plan": t["plan"], "paid": bool(t["paid"]), "expires": t["expires"], "days_left": left, "status": t["status"],
            "running": running, "healthy": bool(hz.get("ok") and hz.get("db")), "error": hz.get("error", ""), "version": hz.get("version"),
            "last_login": act.get("last_login"), "last_user": act.get("user"), "size_mb": _dir_mb(home) if os.path.isdir(home) else 0, "rss_mb": _rss_mb(t["slug"]),
            "restarts_1h": len(starts), "backup_ok": (bk.get("ok") if bk else None), "backup_last": bk.get("last"), "backup_error": bk.get("error"), "drill_ok": (dr.get("ok") if dr.get("last") else None), "drill_error": dr.get("error"),
            "slow_handlers": ui.get("slow_handlers"), "lag_p95_ms": ui.get("loop_lag_p95_ms"), "busy": ui.get("busy_handlers"), "port": t["port"]}


def collect(max_age=15):
    with _lock:
        if time.time() - _cache["t"] < max_age:
            return _cache["rows"]
    tenants = P.list_tenants()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(tenant_row, tenants))
    with _lock:
        _cache.update(t=time.time(), rows=rows)
    return rows


def snapshot():
    rows = collect()
    return {"server": server_stats(), "tenants": rows, "open_alerts": list_alerts("open"),
            "summary": {"total": len(rows), "running": sum(r["running"] for r in rows), "unhealthy": sum(1 for r in rows if r["running"] and not r["healthy"]),
                        "expired": sum(1 for r in rows if r["days_left"] < 0), "paid": sum(r["paid"] for r in rows)}}


# ------------------------------------------------------------------ التنبيهات
def list_alerts(status=None, limit=100):
    with P._db() as c:
        q = "SELECT * FROM alerts" + (" WHERE status=?" if status else "") + " ORDER BY id DESC LIMIT ?"
        return [dict(r) for r in c.execute(q, ((status, limit) if status else (limit,)))]


def resolve_alert(aid):
    with P._lock, P._db() as c:
        c.execute("UPDATE alerts SET status='resolved', resolved_at=? WHERE id=? AND status='open'", (datetime.datetime.now().isoformat(timespec="seconds"), int(aid)))


def conditions(rows=None, server=None):
    """الحالات الغلط الحالية: {(النوع، الموضوع): (الخطورة، الرسالة)}."""
    rows = rows if rows is not None else collect(0)
    server = server or server_stats()
    now = time.time()
    out = {}
    live = set()
    for r in rows:
        key = r["slug"]
        live.add(key)
        want = r["status"] == "active" and r["days_left"] >= 0
        if want and not r["running"]:
            since = _down_since.setdefault(key, now)
            if now - since >= DOWN_SECS:
                out[("tenant_down", key)] = ("crit", f"نسخة «{r['company']}» واقفة من {int((now - since) // 60)} دقيقة (إعادة التشغيل: {r['restarts_1h']} في الساعة الأخيرة)")
        else:
            _down_since.pop(key, None)
        if r["running"] and not r["healthy"]:
            _bad_health[key] = _bad_health.get(key, 0) + 1
            if _bad_health[key] >= 3:
                out[("tenant_unhealthy", key)] = ("crit", f"نسخة «{r['company']}» شغّالة بس مش سليمة: {r['error'] or 'القاعدة لا تستجيب'}")
        else:
            _bad_health.pop(key, None)
        if want and r["running"] and r["backup_ok"] is False:
            out[("backup_failed", key)] = ("warn", f"النسخ الاحتياطي لـ «{r['company']}» فشل: {(r['backup_error'] or '')[:120]}")
        if want and r["running"] and r.get("drill_ok") is False:
            out[("drill_failed", key)] = ("crit", f"فحص استرجاع النسخ الاحتياطية لـ «{r['company']}» فشل: {(r.get('drill_error') or '')[:150]}")
        if want and r["running"] and r["backup_last"]:
            try:
                age = (datetime.datetime.now() - datetime.datetime.fromisoformat(r["backup_last"])).total_seconds()
            except ValueError:
                age = 0
            if age > BACKUP_STALE_HOURS * 3600:
                out[("backup_stale", key)] = ("warn", f"النسخ الاحتياطي لـ «{r['company']}» متأخر: آخر محاولة من {int(age // 3600)} ساعة")
    for k in list(_down_since):
        if k not in live:
            _down_since.pop(k, None)
    if "disk_free_gb" in server and (server["disk_free_gb"] < DISK_MIN_GB or server["disk_free_pct"] < DISK_MIN_PCT):
        out[("disk_low", "")] = ("crit", f"مساحة القرص قاربت تخلص: متاح {server['disk_free_gb']} جيجا ({server['disk_free_pct']}%)")
    if "mem_avail_pct" in server and server["mem_avail_pct"] < MEM_MIN_PCT:
        out[("mem_low", "")] = ("crit", f"الذاكرة قاربت تخلص: متاح {server['mem_avail_mb']} ميجا ({server['mem_avail_pct']}%)")
    total = sum(1 for r in rows)
    if P.MAX_TENANTS and total >= 0.9 * P.MAX_TENANTS:
        out[("capacity", "")] = ("warn", f"عدد الشركات {total} من أصل {P.MAX_TENANTS} (الحد الأقصى المضبوط)")
    return out


def notify_admin(text):
    """يبعت تنبيه للمشرف: واتساب/SMS للأرقام في alert_phones (بنفس مزوّد التذكيرات) و/أو Webhook. بيرجّع قايمة القنوات اللي نجحت."""
    cfg = P.messaging_cfg()
    ok = []
    if cfg["enabled"] and cfg["provider"] != "none":
        from .msgproviders import _send_via_provider, normalize_phone
        for ph in [x.strip() for x in str(cfg.get("alert_phones", "")).replace(";", ",").split(",") if x.strip()]:
            try:
                _send_via_provider(cfg, cfg["channel"], normalize_phone(ph, cfg["country_code"]), text, [text])
                ok.append("phone:" + ph)
            except Exception:      # noqa: BLE001
                pass
    url = str(cfg.get("alert_webhook", "")).strip()
    if url:
        try:
            req = urllib.request.Request(url, data=json.dumps({"text": text}, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json; charset=utf-8"})
            urllib.request.urlopen(req, timeout=10).read()
            ok.append("webhook")
        except Exception:      # noqa: BLE001
            pass
    return ok


def alerts_check(rows=None, server=None):
    """يقارن الحالات الغلط بالتنبيهات المفتوحة: يفتح الجديد ويبعته، ويعيد التنبيه بعد RENOTIFY ساعة لو لسه، ويقفل اللي اتصلح ويبلّغ إنه رجع."""
    cond = conditions(rows, server)
    now = time.time()
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    sent = 0
    with P._lock:
        with P._db() as c:
            open_rows = {(r["kind"], r["subject"]): dict(r) for r in c.execute("SELECT * FROM alerts WHERE status='open'")}
    for key, (sev, msg) in cond.items():
        cur = open_rows.get(key)
        if cur is None:
            with P._lock, P._db() as c:
                cur_id = c.execute("INSERT INTO alerts(created,kind,subject,severity,message) VALUES(?,?,?,?,?)", (stamp, key[0], key[1], sev, msg)).lastrowid
            chans = notify_admin(("🔴 " if sev == "crit" else "🟠 ") + msg)
            with P._lock, P._db() as c:
                c.execute("UPDATE alerts SET notified=?, last_notified=? WHERE id=?", (1 if chans else 0, now, cur_id))
            sent += 1
        else:
            if cur["message"] != msg:
                with P._lock, P._db() as c:
                    c.execute("UPDATE alerts SET message=? WHERE id=?", (msg, cur["id"]))
            if now - cur["last_notified"] >= RENOTIFY:
                chans = notify_admin("⏰ لسه: " + msg)
                with P._lock, P._db() as c:
                    c.execute("UPDATE alerts SET last_notified=?, notified=? WHERE id=?", (now, 1 if chans else cur["notified"], cur["id"]))
    for key, cur in open_rows.items():
        if key not in cond:
            with P._lock, P._db() as c:
                c.execute("UPDATE alerts SET status='resolved', resolved_at=? WHERE id=?", (stamp, cur["id"]))
            notify_admin("✅ رجع طبيعي: " + cur["message"])
    return sent


# ------------------------------------------------------------------ سجل الأخطاء
def log_tail(slug, lines=80):
    """آخر سطور server.log للنسخة + عدد الـ Traceback في آخر 256KB. بيرفض أي slug فيه مسار."""
    if not slug or "/" in slug or "\\" in slug or ".." in slug:
        raise ValueError("اسم غير صالح")
    path = os.path.join(P.tenant_home(slug), "server.log")
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - 262144))
            txt = f.read().decode("utf-8", "replace")
    except OSError:
        return {"errors": 0, "tail": ""}
    ls = txt.splitlines()
    return {"errors": txt.count("Traceback (most recent call last)"), "tail": "\n".join(ls[-int(lines):])}


def rotate_log(slug, max_mb=5):
    path = os.path.join(P.tenant_home(slug), "server.log")
    try:
        if os.path.getsize(path) > max_mb * 1e6:
            os.replace(path, path + ".1")
    except OSError:
        pass


# ------------------------------------------------------------------ صفحة المراقبة
def _fmt_ago(iso):
    if not iso:
        return "—"
    try:
        d = datetime.datetime.fromisoformat(iso)
        s = int((datetime.datetime.now() - d).total_seconds())
    except ValueError:
        return str(iso)
    if s < 90:
        return "من لحظات"
    if s < 5400:
        return f"من {s // 60} دقيقة"
    if s < 172800:
        return f"من {s // 3600} ساعة"
    return f"من {s // 86400} يوم"


def monitor_page(cs, host, msg=""):
    E = P.E
    snap = snapshot()
    sv, sm = snap["server"], snap["summary"]

    def card(label, val, bad=False):
        return f'<div class="c" style="flex:1;min-width:130px;margin:4px;text-align:center{";border:2px solid #d33" if bad else ""}"><div class="s">{E(label)}</div><b style="font-size:20px">{E(str(val))}</b></div>'
    low_disk = "disk_free_gb" in sv and (sv["disk_free_gb"] < DISK_MIN_GB or sv["disk_free_pct"] < DISK_MIN_PCT)
    low_mem = "mem_avail_pct" in sv and sv["mem_avail_pct"] < MEM_MIN_PCT
    cards = (card("شغّالة", f'{sm["running"]} / {sm["total"]}', sm["unhealthy"] > 0) + card("غير سليمة", sm["unhealthy"], sm["unhealthy"] > 0)
             + card("منتهية", sm["expired"]) + card("مدفوعة", sm["paid"])
             + card("القرص المتاح", f'{sv.get("disk_free_gb", "?")} GB ({sv.get("disk_free_pct", "?")}%)', low_disk)
             + card("الذاكرة المتاحة", f'{sv.get("mem_avail_mb", "?")} MB ({sv.get("mem_avail_pct", "?")}%)', low_mem)
             + card("حمل المعالج", f'{sv.get("load1", "?")} / {sv.get("cpus", "?")} نواة'))
    al = ""
    for a in snap["open_alerts"]:
        al += (f'<tr><td>{"🔴" if a["severity"] == "crit" else "🟠"}</td><td>{E(a["created"])}</td><td>{E(a["message"])}</td>'
               f'<td>{"اتبلّغ" if a["notified"] else "لم يُرسل (راجع إعدادات الإرسال)"}</td><td><form class="i" method="post" action="/admin/act">{P._hid(cs, "alert_ok", str(a["id"]))}<button class="g">إغلاق</button></form></td></tr>')
    if not al:
        al = '<tr><td colspan="5">مفيش تنبيهات مفتوحة ✔</td></tr>'
    hist = "".join(f'<tr><td>{E(a["created"])}</td><td>{E(a["message"])}</td><td>{E(a["resolved_at"] or "")}</td></tr>' for a in list_alerts("resolved", 15))
    rows = ""
    for r in snap["tenants"]:
        st = "موقوفة" if r["status"] != "active" else ("منتهية" if r["days_left"] < 0 else ("🟢 سليمة" if r["running"] and r["healthy"] else ("🟠 شغّالة ومش سليمة" if r["running"] else "🔴 واقفة")))
        bk = "—" if r["backup_ok"] is None else (f'✔ {_fmt_ago(r["backup_last"])}' if r["backup_ok"] else "❌ فشل")
        lg = log_tail(r["slug"], 0)
        rows += (f'<tr><td>{E(r["company"])}</td><td>{st}</td><td>{E(_fmt_ago(r["last_login"]))}{" (" + E(r["last_user"]) + ")" if r["last_user"] else ""}</td>'
                 f'<td>{r["size_mb"]} MB</td><td>{r["rss_mb"] if r["rss_mb"] is not None else "—"} MB</td><td>{bk}</td><td>{r["restarts_1h"]}</td>'
                 f'<td><a href="/admin/log?slug={E(r["slug"])}">{lg["errors"]} خطأ</a></td></tr>')
    return P._page(f'''<meta http-equiv="refresh" content="30"><div class="c"><h1>مراقبة الشركات</h1>{f'<div class="ok">{E(msg)}</div>' if msg else ''}
<p class="s"><a href="/admin">← الإدارة</a> · بتتحدّث كل 30 ثانية · آخر تحديث {E(sv["time"])}</p><div style="display:flex;flex-wrap:wrap">{cards}</div></div>
<div class="c"><h2>تنبيهات مفتوحة</h2><table><tr><th></th><th>وقت الفتح</th><th>التنبيه</th><th>الإبلاغ</th><th></th></tr>{al}</table></div>
<div class="c"><h2>حالة كل شركة</h2><table><tr><th>الشركة</th><th>الحالة</th><th>آخر دخول</th><th>حجم البيانات</th><th>الذاكرة</th><th>آخر نسخة احتياطية</th><th>إعادة تشغيل/ساعة</th><th>سجل الأخطاء</th></tr>{rows}</table></div>
<div class="c"><h2>آخر تنبيهات اتحلّت</h2><table><tr><th>الوقت</th><th>التنبيه</th><th>اتحل</th></tr>{hist}</table></div>''', wide=True, title="مراقبة الشركات")


def log_page(slug):
    E = P.E
    d = log_tail(slug, 150)
    return P._page(f'<div class="c"><h1>سجل {E(slug)}</h1><p class="s"><a href="/admin/monitor">← المراقبة</a> · عدد الـ Traceback في آخر 256KB: {d["errors"]}</p>'
                   f'<pre dir="ltr" style="white-space:pre-wrap;font-size:12px;background:#111;color:#ddd;padding:10px;border-radius:8px;overflow:auto">{E(d["tail"] or "(فاضي)")}</pre></div>', wide=True, title="سجل النسخة")
