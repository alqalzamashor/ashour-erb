"""فحص الاسترجاع: نسخة احتياطية عمرها ما اتجرّبت مش نسخة احتياطية. كل أسبوع (drill_days) السيرفر بياخد آخر نسخة ويستردّها فعليًا في مكان مؤقت
(SQLite: ملف مؤقت + integrity_check؛ PostgreSQL: قاعدة مؤقتة لو الصلاحية موجودة وإلا فحص pg_restore --list) ويتأكد إن الجداول والمستخدمين موجودين،
وكمان بيجيب آخر نسخة من المكان البعيد (ويفك تشفيرها بكلمة السر المحفوظة) ويفحصها - فتعرف قبل الكارثة لو كلمة السر ضاعت أو الرفع بايظ.
النتيجة في restore_drill.json، وبتظهر في شاشة النسخ الاحتياطي وفي حالة المهام (healthz) فبوابة المراقبة تنبّه عند الفشل."""
import datetime
import json
import os
import shutil
import sqlite3
import tempfile
import time

from . import backup
from .db import APP_DIR, DB_URL, IS_SQLITE

PATH = os.path.join(APP_DIR, "restore_drill.json")
CFG_PATH = os.path.join(APP_DIR, "restore_drill_cfg.json")


def get_config():
    cfg = {"enabled": True, "days": 7}
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(enabled=None, days=None):
    cfg = get_config()
    if enabled is not None:
        cfg["enabled"] = bool(enabled)
    if days is not None:
        cfg["days"] = max(1, int(days))
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return cfg


def last():
    try:
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _live_tables():
    from sqlalchemy import inspect
    from .db import engine
    return set(inspect(engine).get_table_names())


def _verify_sqlite(path, live):
    con = sqlite3.connect(path)
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("فشل integrity_check")
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        rows = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in ("users", "accounts") if t in tables}
    finally:
        con.close()
    return tables, rows, "full"


def _verify_pg(path, live):
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    env, args, db = backup._pg_env_args()
    backup._run([backup._pg_tool("pg_restore"), "--list", path], env, 300)
    scratch = "erp_drill_%d" % int(time.time())
    u = make_url(DB_URL)
    if u.drivername == "postgresql":
        u = u.set(drivername="postgresql+psycopg2")
    admin = create_engine(u.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            c.execute(text(f'CREATE DATABASE "{scratch}"'))
    except Exception:      # noqa: BLE001 - مفيش صلاحية CREATE DATABASE: نكتفي بفحص القائمة
        admin.dispose()
        return None, {}, "list"
    try:
        backup._run([backup._pg_tool("pg_restore"), *args, "--no-owner", "-d", scratch, path], env, 3600)
        eng = create_engine(u.set(database=scratch))
        try:
            with eng.connect() as c:
                tables = {r[0] for r in c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))}
                rows = {t: c.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar() for t in ("users", "accounts") if t in tables}
        finally:
            eng.dispose()
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)'))
        admin.dispose()
    return tables, rows, "full"


def _verify_remote():
    from . import backup_remote as br
    cfg = br.get_config()
    slots = br.enabled_slots(cfg)
    if not slots:
        return None
    slot = slots[0]
    try:
        prov = br.provider(slot, cfg)
        items = sorted(prov.list(), key=lambda r: r["at"], reverse=True)
        if not items:
            raise RuntimeError("المكان البعيد فاضي - مفيش نسخ مرفوعة")
        item = items[0]
        tmp_dir = tempfile.mkdtemp()
        try:
            raw = os.path.join(tmp_dir, "dl")
            prov.download(item["id"], raw)
            out = os.path.join(tmp_dir, "plain" + backup.EXT)
            if item["name"].endswith(".enc"):
                if not cfg["passphrase"]:
                    raise RuntimeError("النسخة مشفّرة وكلمة السر مش محفوظة")
                br.decrypt_file(raw, out, cfg["passphrase"])
            else:
                shutil.move(raw, out)
            if not backup._check(out):
                raise RuntimeError("النسخة البعيدة فشلت في فحص السلامة")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return {"slot": slot, "ok": True, "name": item["name"], "encrypted": item["name"].endswith(".enc")}
    except Exception as ex:      # noqa: BLE001
        return {"slot": slot, "ok": False, "error": f"{type(ex).__name__}: {ex}"[:300]}


def run_drill(use_remote=True):
    """يعمل الفحص ويسجّل النتيجة. بيرجّع dict النتيجة (ok / level / backup / rows / remote / error). مش بيرمي استثناء."""
    t0 = time.time()
    res = {"at": datetime.datetime.now().isoformat(timespec="seconds"), "ok": False, "level": None, "backup": None, "rows": {}, "remote": None, "error": None}
    try:
        cands = [b for b in backup.list_backups() if b["kind"] in ("manual", "auto")]
        if not cands:
            raise RuntimeError("مفيش نسخة احتياطية تتفحص")
        b = cands[0]
        res["backup"] = b["name"]
        tmp_dir = tempfile.mkdtemp()
        try:
            copy = os.path.join(tmp_dir, "drill" + backup.EXT)
            shutil.copy2(b["path"], copy)
            live = _live_tables()
            tables, rows, level = (_verify_sqlite if IS_SQLITE else _verify_pg)(copy, live)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        res["level"], res["rows"] = level, rows
        if level == "full":
            missing = sorted(t for t in live if t not in tables and not t.startswith("alembic"))
            core = {"users", "accounts", "company_settings"} & live
            if (core - tables) or rows.get("users", 0) < 1:
                raise RuntimeError("النسخة ناقصة: " + (", ".join(sorted(core - tables)) or "مفيش مستخدمين"))
            res["missing_tables"] = missing[:20]
        res["ok"] = True
    except Exception as ex:      # noqa: BLE001
        res["error"] = f"{type(ex).__name__}: {ex}"[:400]
    if use_remote:
        try:
            res["remote"] = _verify_remote()
        except Exception as ex:      # noqa: BLE001
            res["remote"] = {"ok": False, "error": str(ex)[:300]}
        if res["remote"] and not res["remote"]["ok"]:
            res["ok"] = False
            res["error"] = ((res["error"] + " | ") if res["error"] else "") + "النسخة البعيدة: " + res["remote"]["error"]
    res["secs"] = round(time.time() - t0, 1)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    try:
        from . import audit
        audit.log_event("backup_drill", label="فحص الاسترجاع " + ("نجح" if res["ok"] else "فشل"), changes=(res["error"] or res["backup"] or "")[:200], username="system")
    except Exception:      # noqa: BLE001
        pass
    return res


def run_due():
    """من المجدول: يعمل الفحص لو مفعّل ومرّت المدة. بيرمي استثناء لو فشل عشان المجدول يسجّله (ok=False) فتشوفه المراقبة."""
    cfg = get_config()
    if not cfg["enabled"]:
        return None
    prev = last()
    if prev:
        age = (datetime.datetime.now() - datetime.datetime.fromisoformat(prev["at"])).total_seconds()
        if age < cfg["days"] * 86400 and prev.get("ok"):
            return None
        if age < 6 * 3600:          # فشل قريب: ما نكررش كل مرة
            return None
    if not [b for b in backup.list_backups() if b["kind"] in ("manual", "auto")]:
        return None                  # لسه مفيش نسخ (أول يوم)
    res = run_drill()
    if not res["ok"]:
        raise RuntimeError("فحص الاسترجاع فشل: " + (res["error"] or ""))
    return res
