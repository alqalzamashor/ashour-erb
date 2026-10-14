"""النسخ الاحتياطي والاسترجاع: SQLite (sqlite3 backup API - ملف .db) أو PostgreSQL (pg_dump بصيغة custom - ملف .dump؛ محتاج أدوات pg_dump/pg_restore على جهاز السيرفر).
فحص سلامة، احتفاظ بآخر N نسخة، نسخ تلقائي دوري، واسترجاع بنسخة أمان قبله."""
import datetime
import json
import os
import re
import shutil
import shutil as _sh
import sqlite3
import subprocess
import threading

from . import audit
from .db import APP_DIR, DB_PATH, DB_URL, IS_SQLITE, engine

BACKUP_DIR = os.path.join(APP_DIR, "backups")
CONFIG_PATH = os.path.join(BACKUP_DIR, "config.json")
DEFAULTS = {"auto": True, "interval_hours": 24, "keep": 14, "extra_dir": "", "pg_bin_dir": ""}
EXT = ".db" if IS_SQLITE else ".dump"
_lock = threading.Lock()


def _ensure():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def get_config():
    _ensure()
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_config(**kw):
    cfg = get_config()
    for k, v in kw.items():
        if k in DEFAULTS:
            cfg[k] = v
    cfg["interval_hours"] = max(1, int(cfg["interval_hours"] or 24))
    cfg["keep"] = max(1, int(cfg["keep"] or 14))
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    return cfg


def _pg_tool(name):
    """مسار أداة PostgreSQL (pg_dump / pg_restore): من إعداد pg_bin_dir أو PATH أو أماكن التثبيت الشائعة."""
    exe = name + (".exe" if os.name == "nt" else "")
    d = (get_config().get("pg_bin_dir") or "").strip()
    if d and os.path.isfile(os.path.join(d, exe)):
        return os.path.join(d, exe)
    w = _sh.which(name)
    if w:
        return w
    import glob
    pats = ["C:/Program Files/PostgreSQL/*/bin/" + exe, "/usr/lib/postgresql/*/bin/" + exe, "/usr/local/pgsql/bin/" + exe, "/opt/homebrew/bin/" + exe, "/Library/PostgreSQL/*/bin/" + exe]
    for pat in pats:
        hits = sorted(glob.glob(pat), reverse=True)
        if hits:
            return hits[0]
    raise RuntimeError(f"أداة {name} مش لاقيها - ثبّت أدوات PostgreSQL (client tools) على جهاز السيرفر أو اكتب مسار مجلد bin في إعدادات النسخ الاحتياطي")


def _pg_env_args():
    from sqlalchemy.engine import make_url
    u = make_url(DB_URL)
    env = dict(os.environ)
    if u.password:
        env["PGPASSWORD"] = u.password
    args = ["-h", u.host or "localhost", "-p", str(u.port or 5432)] + (["-U", u.username] if u.username else [])
    return env, args, u.database


def _run(cmd, env, timeout=3600):
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "فشل الأمر").strip()[-600:])
    return r


def _check(path):
    if not IS_SQLITE:
        env, args, db = _pg_env_args()
        try:
            _run([_pg_tool("pg_restore"), "--list", path], env, 300)
            return os.path.getsize(path) > 0
        except Exception:
            return False
    con = sqlite3.connect(path)
    try:
        return con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        con.close()


def backup_now(kind="manual", username=None):
    """نسخة جديدة اسمها erp_<kind>_<timestamp>.db. kind = manual | auto | pre_restore. بترجّع {name, path, size}."""
    _ensure()
    with _lock:
        name = f"erp_{kind}_{datetime.datetime.now():%Y%m%d_%H%M%S}{EXT}"
        path = os.path.join(BACKUP_DIR, name)
        n_ = 1
        while os.path.exists(path):       # نفس الثانية: اسم فريد بدل الكتابة فوق نسخة موجودة
            name = f"erp_{kind}_{datetime.datetime.now():%Y%m%d_%H%M%S}_{n_}{EXT}"; path = os.path.join(BACKUP_DIR, name); n_ += 1
        if IS_SQLITE:
            src = sqlite3.connect(DB_PATH)
            dst = sqlite3.connect(path)
            try:
                src.backup(dst)
            finally:
                dst.close(); src.close()
        else:
            env, args, db = _pg_env_args()
            try:
                _run([_pg_tool("pg_dump"), *args, "-Fc", "--no-owner", "-f", path, db], env)
            except Exception:
                if os.path.exists(path):
                    os.remove(path)
                raise
        if not _check(path):
            os.remove(path)
            raise RuntimeError("فشل فحص سلامة النسخة الاحتياطية - اتلغت")
        cfg = get_config()
        if cfg.get("extra_dir"):
            try:
                os.makedirs(cfg["extra_dir"], exist_ok=True)
                shutil.copy2(path, os.path.join(cfg["extra_dir"], name))
            except Exception:
                pass          # مجلد النسخ الإضافي مش متاح - النسخة المحلية سليمة
        _prune(cfg["keep"])
    audit.log_event("backup", label=name, changes=kind, username=username)
    try:
        from . import backup_remote
        backup_remote.after_backup(name)      # رفع خارجي (لو متفعّل) في خيط خلفي
    except Exception:
        pass
    return {"name": name, "path": path, "size": os.path.getsize(path)}


def _prune(keep):
    files = [f for f in list_backups() if f["kind"] not in ("pre_restore", "pre_update")]
    for f in files[keep:]:
        try:
            os.remove(f["path"])
        except OSError:
            pass


def list_backups():
    _ensure()
    out = []
    for n in os.listdir(BACKUP_DIR):
        if not (n.startswith("erp_") and n.endswith(EXT)):
            continue
        p = os.path.join(BACKUP_DIR, n)
        m = re.match(r"erp_(.+)_\d{8}_\d{6}(?:_\d+)?\.(?:db|dump)$", n)
        out.append({"name": n, "path": p, "size": os.path.getsize(p), "kind": m.group(1) if m else "manual",
                    "at": datetime.datetime.fromtimestamp(os.path.getmtime(p))})
    return sorted(out, key=lambda r: r["at"], reverse=True)


def last_backup_time():
    rows = [b for b in list_backups() if b["kind"] in ("manual", "auto")]
    return rows[0]["at"] if rows else None


def auto_backup_if_due():
    """بتتنادى دوريًا: لو النسخ التلقائي شغّال ومرّ الوقت المحدد من آخر نسخة، تعمل نسخة. بترجّع النتيجة أو None."""
    try:
        from . import backup_remote
        backup_remote.retry_pending()         # إعادة رفع اللي فشل قبل كده
    except Exception:
        pass
    cfg = get_config()
    if not cfg["auto"]:
        return None
    last = last_backup_time()
    if last and (datetime.datetime.now() - last).total_seconds() < cfg["interval_hours"] * 3600:
        return None
    return backup_now("auto", username="system")


def delete_backup(name):
    p = _safe_path(name)
    os.remove(p)
    audit.log_event("backup_delete", label=name)


def _safe_path(name):
    p = os.path.join(BACKUP_DIR, os.path.basename(name))
    if not os.path.isfile(p) or not os.path.basename(p).startswith("erp_"):
        raise ValueError("النسخة غير موجودة")
    return p


def restore_backup(name):
    """استرجاع نسخة: فحص سلامتها، نسخة أمان من الحالية، ثم استبدال ملف القاعدة. لازم إعادة تشغيل البرنامج بعدها."""
    src = _safe_path(name)
    if not _check(src):
        raise ValueError("النسخة دي تالفة - مينفعش تتسترجع")
    safety = backup_now("pre_restore")
    with _lock:
        engine.dispose()
        if IS_SQLITE:
            for ext in ("-wal", "-shm"):
                try:
                    os.remove(DB_PATH + ext)
                except OSError:
                    pass
            shutil.copy2(src, DB_PATH)
        else:
            env, args, db = _pg_env_args()
            _run([_pg_tool("pg_restore"), *args, "--clean", "--if-exists", "--no-owner", "-d", db, src], env)
        engine.dispose()
    audit.log_event("restore", label=name, changes=f"نسخة الأمان: {safety['name']}")
    return safety["name"]
