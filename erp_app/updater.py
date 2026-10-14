"""ترقية آمنة للبرنامج من ملف zip (أو مجلد) للإصدار الجديد.
الخطوات: فحص الحزمة والإصدار ← التأكد إن البرنامج مقفول ← نسخة احتياطية للقاعدة (pre_update، وبتترفع للمكان الخارجي لو متفعّل) + لقطة zip للكود
← استبدال ملفات الكود (data/ و backups/ و exports/ محفوظة زي ما هي) ← فحص: تجميع الكود + ترحيل القاعدة (init_db) + استيراد البرنامج
← لو أي خطوة فشلت: رجوع تلقائي للكود القديم + استرجاع نسخة القاعدة. وفيه rollback يدوي بعدين.
التشغيل:  python update.py <الحزمة.zip> [--check] [--yes] [--force] [--install-deps]  |  python update.py --rollback [--with-db]  |  python update.py --status"""
import datetime
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile

from . import audit, backup, backup_remote
from .db import APP_DIR, DB_PATH, IS_SQLITE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRESERVE = {"data", "backups", "exports", "__pycache__", ".git", ".pytest_cache", "venv", ".venv", "update_work", "update_backups"}
WORK_DIR = os.path.join(APP_DIR, "update_work")
SNAP_DIR = os.path.join(APP_DIR, "update_backups")
LOG_PATH = os.path.join(APP_DIR, "update_log.json")
KEEP_SNAPSHOTS = 5


class UpdateError(Exception):
    pass


# ───────────────────────── مساعدات ─────────────────────────
def _vt(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:4])


def read_version(code_dir):
    try:
        m = re.search(r'VERSION\s*=\s*["\']([^"\']+)', open(os.path.join(code_dir, "erp_app", "version.py"), encoding="utf-8").read())
        return m.group(1) if m else "0"
    except OSError:
        return "0"


def find_root(base):
    """مجلد الحزمة الحقيقي (فيه main.py و erp_app) حتى لو الـ zip فيه مجلد خارجي."""
    for dp, dn, fn in os.walk(base):
        if dp[len(base):].count(os.sep) > 2:
            dn[:] = []
            continue
        if "main.py" in fn and "erp_app" in dn:
            return dp
    raise UpdateError("الحزمة مش شكل برنامج صحيح (مفيش main.py + مجلد erp_app)")


def _files(root):
    out = {}
    for dp, dn, fn in os.walk(root):
        rel = os.path.relpath(dp, root)
        top = rel.split(os.sep)[0]
        dn[:] = [d for d in dn if d != "__pycache__" and not (rel == "." and d in PRESERVE)]
        if top in PRESERVE or top == "__pycache__":
            continue
        for f in fn:
            if f.endswith(".pyc"):
                continue
            p = os.path.join(dp, f)
            out[os.path.normpath(os.path.relpath(p, root))] = p
    return out


def _same(a, b):
    return os.path.getsize(a) == os.path.getsize(b) and open(a, "rb").read() == open(b, "rb").read()


def unpack(src, dest):
    """بيفك zip (مع حماية من مسارات خارج الوجهة) أو بينسخ مجلد، وبيرجّع مجلد الحزمة."""
    os.makedirs(dest, exist_ok=True)
    if os.path.isdir(src):
        shutil.copytree(src, os.path.join(dest, "pkg"), ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return find_root(dest)
    if not zipfile.is_zipfile(src):
        raise UpdateError("الملف مش zip صالح")
    with zipfile.ZipFile(src) as z:
        bad = z.testzip()
        if bad:
            raise UpdateError(f"الـ zip تالف عند الملف {bad}")
        base = os.path.realpath(dest)
        for n in z.namelist():
            if not os.path.realpath(os.path.join(base, n)).startswith(base + os.sep):
                raise UpdateError("الـ zip فيه مسار غير آمن: " + n)
        z.extractall(dest)
    return find_root(dest)


def plan(code_dir, new_root):
    old, new = _files(code_dir), _files(new_root)
    added = sorted(k for k in new if k not in old)
    changed = sorted(k for k in new if k in old and not _same(old[k], new[k]))
    new_dirs = {e for e in os.listdir(new_root) if os.path.isdir(os.path.join(new_root, e))}
    removed = sorted(k for k in old if k not in new and k.split(os.sep)[0] in new_dirs)
    req = lambda d: open(os.path.join(d, "requirements.txt"), encoding="utf-8").read().split() if os.path.exists(os.path.join(d, "requirements.txt")) else []
    return {"from": read_version(code_dir), "to": read_version(new_root), "added": added, "changed": changed, "removed": removed,
            "requirements_changed": sorted(req(code_dir)) != sorted(req(new_root))}


def snapshot_code(code_dir, label):
    os.makedirs(SNAP_DIR, exist_ok=True)
    path = os.path.join(SNAP_DIR, f"code_{label}.zip")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, p in _files(code_dir).items():
            z.write(p, rel)
    for old in _snaps()[:-KEEP_SNAPSHOTS]:
        os.remove(os.path.join(SNAP_DIR, old))
    return path


def _snaps():
    """أسماء لقطات الكود من الأقدم للأحدث (بتاريخ الإنشاء مش بالاسم)."""
    if not os.path.isdir(SNAP_DIR):
        return []
    return sorted((f for f in os.listdir(SNAP_DIR) if f.startswith("code_") and f.endswith(".zip")), key=lambda f: os.path.getmtime(os.path.join(SNAP_DIR, f)))


def ensure_not_running():
    """SQLite: لو فيه برنامج شغّال على القاعدة مش هنقدر ناخد قفل حصري. PostgreSQL: مفيش طريقة نتأكد، التحذير في الشاشة."""
    if not IS_SQLITE or not os.path.exists(DB_PATH):
        return
    con = sqlite3.connect(DB_PATH, timeout=1)
    try:
        con.execute("BEGIN EXCLUSIVE")
        con.execute("ROLLBACK")
    except sqlite3.OperationalError:
        raise UpdateError("البرنامج (أو السيرفر) لسه شغّال على القاعدة. اقفله تمامًا وجرّب تاني.")
    finally:
        con.close()


def default_backup():
    backup_remote.SYNC = True          # العملية قصيرة العمر: لازم الرفع الخارجي يخلص قبل ما تنتهي
    return backup.backup_now("pre_update", username="updater")


def default_restore_db(name):
    return backup.restore_backup(name)


def default_verify(code_dir):
    """تجميع الكود، ترحيل القاعدة بالكود الجديد (init_db)، واستيراد البرنامج كله - كل واحدة في عملية منفصلة."""
    py = sys.executable
    steps = [("تجميع الكود (syntax)", [py, "-m", "compileall", "-q", os.path.join(code_dir, "erp_app"), os.path.join(code_dir, "main.py")]),
             ("ترحيل القاعدة", [py, "-c", "from erp_app import db; db.init_db()"]),
             ("استيراد البرنامج", [py, "-c", "import main"])]
    for label, cmd in steps:
        r = subprocess.run(cmd, cwd=code_dir, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise UpdateError(f"فشل فحص «{label}»: " + (r.stderr or r.stdout).strip()[-500:])


def _log(entry):
    try:
        rows = json.load(open(LOG_PATH, encoding="utf-8"))
    except Exception:
        rows = []
    rows.append(entry)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    json.dump(rows[-50:], open(LOG_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def history():
    try:
        return json.load(open(LOG_PATH, encoding="utf-8"))
    except Exception:
        return []


def _swap_in(code_dir, new_root, old_dir):
    """كل عنصر على المستوى الأعلى في الحزمة الجديدة: القديم يتنقل لـ old_dir والجديد يتنسخ مكانه. بيرجّع قايمة للتراجع."""
    done = []
    os.makedirs(old_dir, exist_ok=True)
    for name in sorted(os.listdir(new_root)):
        if name in PRESERVE or name.endswith(".pyc"):
            continue
        tgt, src = os.path.join(code_dir, name), os.path.join(new_root, name)
        had = os.path.lexists(tgt)
        if had:
            shutil.move(tgt, os.path.join(old_dir, name))
        done.append((name, had))
        if os.path.isdir(src):
            shutil.copytree(src, tgt, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(src, tgt)
    return done


def _swap_back(code_dir, old_dir, done):
    for name, had in reversed(done):
        tgt = os.path.join(code_dir, name)
        if os.path.isdir(tgt) and not os.path.islink(tgt):
            shutil.rmtree(tgt, ignore_errors=True)
        elif os.path.lexists(tgt):
            os.remove(tgt)
        if had:
            shutil.move(os.path.join(old_dir, name), tgt)


# ───────────────────────── الترقية والتراجع ─────────────────────────
def apply(src, *, code_dir=ROOT, dry_run=False, force=False, check_running=True, install_deps=False, sha256=None,
          backup_fn=default_backup, verify_fn=default_verify, restore_db_fn=default_restore_db, log=print):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if sha256 and os.path.isfile(src):
        h = hashlib.sha256(open(src, "rb").read()).hexdigest()
        if h.lower() != sha256.lower():
            raise UpdateError("بصمة SHA-256 للحزمة مش مطابقة - الملف متعدّل أو ناقص")
    work = os.path.join(WORK_DIR, ts)
    try:
        new_root = unpack(src, os.path.join(work, "new"))
        pl = plan(code_dir, new_root)
        log(f"الإصدار الحالي {pl['from']} ← الجديد {pl['to']}  |  ملفات جديدة {len(pl['added'])}، معدّلة {len(pl['changed'])}، محذوفة {len(pl['removed'])}")
        if pl["requirements_changed"]:
            log("تنبيه: ملف requirements.txt اتغيّر - لازم تثبّت المكتبات (--install-deps أو pip install -r requirements.txt)")
        if _vt(pl["to"]) < _vt(pl["from"]) and not force:
            raise UpdateError(f"الحزمة أقدم من المثبّت ({pl['to']} < {pl['from']}). استخدم --force لو متأكد.")
        if _vt(pl["to"]) == _vt(pl["from"]) and not pl["added"] and not pl["changed"] and not force:
            raise UpdateError("المثبّت عندك هو نفس الإصدار ومفيش أي اختلاف في الملفات.")
        if dry_run:
            return {**pl, "applied": False}
        if check_running:
            ensure_not_running()
        log("1) نسخة احتياطية للقاعدة...")
        b = backup_fn()
        log(f"   تم: {b['name']}")
        snap = snapshot_code(code_dir, f"{pl['from']}_{ts}")
        log(f"2) لقطة من الكود الحالي: {os.path.basename(snap)}")
        old_dir = os.path.join(work, "old")
        done = []
        entry = {"at": datetime.datetime.now().isoformat(timespec="seconds"), "from": pl["from"], "to": pl["to"], "db_backup": b["name"], "code_snapshot": os.path.basename(snap)}
        try:
            log("3) استبدال ملفات الكود...")
            done = _swap_in(code_dir, new_root, old_dir)
            if install_deps and pl["requirements_changed"]:
                log("   تثبيت المكتبات...")
                r = subprocess.run([sys.executable, "-m", "pip", "install", "-r", os.path.join(code_dir, "requirements.txt")], capture_output=True, text=True, timeout=1800)
                if r.returncode != 0:
                    raise UpdateError("فشل تثبيت المكتبات: " + (r.stderr or "")[-400:])
            log("4) فحص الإصدار الجديد (تجميع + ترحيل القاعدة + استيراد)...")
            verify_fn(code_dir)
        except Exception as ex:
            log(f"!! فشلت الترقية: {ex}\n   رجوع للكود القديم...")
            _swap_back(code_dir, old_dir, done)
            db_note = ""
            try:
                restore_db_fn(b["name"]); db_note = "واتسترجعت نسخة القاعدة"
            except Exception as ex2:
                db_note = f"تعذر استرجاع القاعدة تلقائيًا ({ex2}) - استرجع {b['name']} يدويًا"
            log("   " + db_note)
            _log({**entry, "status": "failed_rolled_back", "error": str(ex)[:500], "db": db_note})
            raise UpdateError(f"{ex} — رجّعنا الكود القديم. {db_note}")
        _log({**entry, "status": "ok"})
        try:
            audit.log_event("update", label=f"{pl['from']} ← {pl['to']}", changes=json.dumps({"db_backup": b["name"], "code_snapshot": entry["code_snapshot"]}, ensure_ascii=False), username="updater")
        except Exception:
            pass
        log(f"تمت الترقية للإصدار {pl['to']}. شغّل البرنامج. (للتراجع لاحقًا: python update.py --rollback --with-db)")
        return {**pl, "applied": True, "db_backup": b["name"], "code_snapshot": snap}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def rollback(*, code_dir=ROOT, with_db=False, snapshot=None, restore_db_fn=default_restore_db, backup_fn=default_backup, check_running=True, log=print):
    """رجوع للكود من آخر لقطة (أو snapshot محدد)، واختياريًا استرجاع نسخة القاعدة المرتبطة بآخر ترقية ناجحة."""
    snaps = [f for f in _snaps() if "_before_rollback_" not in f]
    if not snaps:
        raise UpdateError("مفيش لقطات كود سابقة للرجوع ليها")
    name = snapshot or snaps[-1]
    path = os.path.join(SNAP_DIR, os.path.basename(name))
    if not os.path.isfile(path):
        raise UpdateError("اللقطة مش موجودة")
    if check_running:
        ensure_not_running()
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    cur = snapshot_code(code_dir, f"{read_version(code_dir)}_before_rollback_{ts}")
    log(f"لقطة من الكود الحالي قبل الرجوع: {os.path.basename(cur)}")
    work = os.path.join(WORK_DIR, "rb_" + ts)
    try:
        with zipfile.ZipFile(path) as z:
            z.extractall(os.path.join(work, "new"))
        new_root = os.path.join(work, "new")
        # نرجّع بنفس طريقة الترقية: اللقطة فيها كل ملفات الكود، فنستبدل كل عنصر على المستوى الأعلى فيها
        _swap_in(code_dir, new_root, os.path.join(work, "old"))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    db_name = None
    if with_db:
        last = next((e for e in reversed(history()) if e.get("status") == "ok" and e.get("db_backup")), None)
        if not last:
            raise UpdateError("مفيش ترقية ناجحة مسجّلة عشان نعرف نسخة القاعدة المرتبطة بيها")
        db_name = last["db_backup"]
        restore_db_fn(db_name)
        log(f"اتسترجعت القاعدة من {db_name} (أي بيانات اتسجّلت بعد الترقية ضاعت - نسخة أمان بتاعتها متاخدة قبل الاسترجاع).")
    _log({"at": datetime.datetime.now().isoformat(timespec="seconds"), "status": "rollback", "code_snapshot": os.path.basename(path), "db_backup": db_name})
    log(f"رجعنا للكود من {os.path.basename(path)} (الإصدار {read_version(code_dir)}).")
    return {"snapshot": os.path.basename(path), "db_backup": db_name, "version": read_version(code_dir)}
