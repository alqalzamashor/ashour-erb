"""إعداد وفحص ونقل البيانات إلى PostgreSQL.
- test_connection(url): تجربة اتصال + نسخة السيرفر + هل فيه بيانات.
- save_url(url): كتابة الرابط في database.json (التغيير بيشتغل بعد إعادة تشغيل البرنامج).
- migrate(sqlite_path, pg_url): نسخ كل الجداول من SQLite لقاعدة PostgreSQL فاضية، مع إعادة ضبط عدّادات الترقيم وتقرير بالصفوف المتخطّاة."""
import json
import os
import stat
import time

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url

from . import audit, services
from .db import APP_DIR, Base, DB_CONFIG_PATH, DB_PATH, DB_URL, IS_SQLITE


def normalize_url(url):
    url = (url or "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def build_url(host, port, dbname, user, password):
    from sqlalchemy.engine import URL
    return URL.create("postgresql+psycopg2", username=user or None, password=password or None, host=host or "localhost", port=int(port or 5432), database=dbname).render_as_string(hide_password=False)


def mask(url):
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return "?"


def current_info():
    """حالة القاعدة المستخدمة حاليًا (للشاشة)."""
    info = {"kind": "SQLite" if IS_SQLITE else "PostgreSQL", "url": mask(DB_URL), "version": "", "size": 0}
    try:
        from .db import engine
        with engine.connect() as c:
            if IS_SQLITE:
                info["version"] = c.execute(text("select sqlite_version()")).scalar()
                info["size"] = os.path.getsize(DB_PATH) if os.path.isfile(DB_PATH) else 0
            else:
                info["version"] = (c.execute(text("show server_version")).scalar() or "")
                info["size"] = int(c.execute(text("select pg_database_size(current_database())")).scalar() or 0)
    except Exception as ex:
        info["error"] = str(ex)[:200]
    cfg_url = ""
    try:
        with open(DB_CONFIG_PATH, encoding="utf-8") as f:
            cfg_url = (json.load(f).get("url") or "")
    except Exception:
        pass
    info["configured"] = mask(normalize_url(cfg_url)) if cfg_url else ""
    info["env_override"] = bool(os.environ.get("ERP_DATABASE_URL"))
    return info


def test_connection(url):
    """بيرجّع {ok, message, version, empty}. empty = القاعدة مفيهاش جدول users (جاهزة لاستقبال نقل البيانات)."""
    url = normalize_url(url)
    if not url.startswith("postgresql"):
        return {"ok": False, "message": "الرابط لازم يبدأ بـ postgresql://", "version": "", "empty": False}
    eng = None
    try:
        eng = create_engine(url, connect_args={"connect_timeout": 8})
        with eng.connect() as c:
            ver = c.execute(text("show server_version")).scalar()
            has_users = bool(c.execute(text("select to_regclass('public.users')")).scalar())
            n = c.execute(text("select count(*) from users")).scalar() if has_users else 0
        return {"ok": True, "message": "تم الاتصال بنجاح" + ("" if not n else f" (القاعدة فيها بيانات: {n} مستخدم)"), "version": ver, "empty": n == 0}
    except Exception as ex:
        msg = str(ex).splitlines()[0][:250]
        return {"ok": False, "message": f"فشل الاتصال: {msg}", "version": "", "empty": False}
    finally:
        if eng is not None:
            eng.dispose()


def save_url(url):
    services.require_action("settings", "edit")
    url = normalize_url(url)
    t = test_connection(url)
    if not t["ok"]:
        raise ValueError(t["message"])
    with open(DB_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"url": url}, f)
    try:
        os.chmod(DB_CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)       # فيه كلمة سر القاعدة
    except Exception:
        pass
    audit.log_event("config", label="قاعدة البيانات", changes={"url": ["-", mask(url)]})
    return t


def clear_url():
    """الرجوع لـ SQLite المحلي (بعد إعادة التشغيل)."""
    services.require_action("settings", "edit")
    if os.path.exists(DB_CONFIG_PATH):
        os.remove(DB_CONFIG_PATH)
    audit.log_event("config", label="قاعدة البيانات", changes={"url": ["-", "SQLite المحلي"]})


def _clean(v):
    return v.replace("\x00", "") if isinstance(v, str) else v


def migrate(pg_url, sqlite_path=None, progress=None, chunk=2000):
    """نقل كل البيانات من ملف SQLite إلى PostgreSQL (لازم القاعدة الهدف فاضية من المستخدمين). المفاتيح الأجنبية بتفضل مفعّلة: صف مرجعه ناقص (يتيم) بيتخطّى ويتسجّل في التقرير. بيرجّع تقرير."""
    services.require_action("settings", "edit")
    pg_url = normalize_url(pg_url)
    sqlite_path = sqlite_path or DB_PATH
    if not os.path.isfile(sqlite_path):
        raise ValueError("ملف SQLite المصدر مش موجود")
    say = progress or (lambda m: None)
    t0 = time.time()
    src = create_engine(f"sqlite:///{sqlite_path}")
    dst = create_engine(pg_url, connect_args={"connect_timeout": 10})
    report = {"tables": {}, "skipped": [], "seconds": 0, "rows": 0}
    try:
        Base.metadata.create_all(dst)
        tables = list(Base.metadata.sorted_tables)
        with dst.connect() as c:
            n_users = c.execute(text("select count(*) from users")).scalar()
        if n_users:
            raise ValueError("قاعدة PostgreSQL الهدف فيها بيانات فعلًا - لازم تكون فاضية (قاعدة جديدة)")
        with src.connect() as sc, dst.begin() as dc:
            deferred = []
            for i, t in enumerate(tables, 1):
                say(f"({i}/{len(tables)}) {t.name}")
                total = sc.execute(select(func.count()).select_from(t)).scalar() if _has_table(sc, t.name) else 0
                if not total:
                    report["tables"][t.name] = [0, 0]
                    continue
                cols = [c_.name for c_ in t.columns]
                src_cols = _existing_cols(sc, t.name)
                use_cols = [c_ for c_ in cols if c_ in src_cols]
                q = select(*[t.c[c_] for c_ in use_cols])
                done = 0
                rs = sc.execution_options(stream_results=True).execute(q)
                while True:
                    rows = rs.fetchmany(chunk)
                    if not rows:
                        break
                    batch = [{k: _clean(v) for k, v in zip(use_cols, r)} for r in rows]
                    sp = dc.begin_nested()
                    try:
                        dc.execute(t.insert(), batch)
                        sp.commit()
                        done += len(batch)
                    except Exception:
                        sp.rollback()
                        for row in batch:
                            sp2 = dc.begin_nested()
                            try:
                                dc.execute(t.insert(), [row])
                                sp2.commit()
                                done += 1
                            except Exception as ex:
                                sp2.rollback()
                                deferred.append((t, row, str(ex).splitlines()[0][:160]))
                report["tables"][t.name] = [total, done]
            # إعادة المحاولة للصفوف اللي فشلت (غالبًا مرجع لسجل لسه ما اتنقلش - دوائر المفاتيح الأجنبية)
            for _round in range(6):
                if not deferred:
                    break
                again = []
                for t, row, err in deferred:
                    sp = dc.begin_nested()
                    try:
                        dc.execute(t.insert(), [row]); sp.commit()
                        report["tables"][t.name][1] += 1
                    except Exception as ex:
                        sp.rollback(); again.append((t, row, str(ex).splitlines()[0][:160]))
                if len(again) == len(deferred):
                    deferred = again
                    break
                deferred = again
            for t, row, err in deferred:
                report["skipped"].append({"table": t.name, "id": row.get("id"), "error": err})
            # عدّادات الترقيم
            for t in tables:
                if "id" in t.c and t.c["id"].primary_key:
                    dc.execute(text("SELECT setval(pg_get_serial_sequence(:t, 'id'), COALESCE((SELECT MAX(id) FROM " + t.name + "), 0) + 1, false)"), {"t": t.name})
        report["rows"] = sum(v[1] for v in report["tables"].values())
        report["mismatch"] = {k: v for k, v in report["tables"].items() if v[0] != v[1]}
    finally:
        src.dispose(); dst.dispose()
    report["seconds"] = round(time.time() - t0, 1)
    audit.log_event("bulk", label="نقل البيانات إلى PostgreSQL", changes={"صفوف": report["rows"], "متخطّاة": len(report["skipped"]), "ثواني": report["seconds"]})
    return report


def _has_table(conn, name):
    return bool(conn.execute(text("select 1 from sqlite_master where type='table' and name=:n"), {"n": name}).first())


def _existing_cols(conn, name):
    return {r[1] for r in conn.execute(text(f"PRAGMA table_info({name})")).all()}
