import os
import sqlite3
import zipfile

import pytest

from erp_app import backup, updater
from erp_app.db import IS_SQLITE, DB_PATH


def _tree(root, version, extra=None, files=None):
    os.makedirs(os.path.join(root, "erp_app"), exist_ok=True)
    open(os.path.join(root, "main.py"), "w").write(f"# main {version}\n")
    open(os.path.join(root, "erp_app", "version.py"), "w").write(f'VERSION = "{version}"\n')
    open(os.path.join(root, "requirements.txt"), "w").write("flet==1\n")
    for rel, txt in {**(extra or {}), **(files or {})}.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(txt)


def _zip(tmp, name, version, wrap="pkg", **kw):
    src = tmp / ("src_" + name)
    _tree(str(src), version, **kw)
    z = tmp / name
    with zipfile.ZipFile(z, "w") as zf:
        for dp, _, fns in os.walk(src):
            for f in fns:
                p = os.path.join(dp, f)
                zf.write(p, os.path.join(wrap, os.path.relpath(p, src)))
    return str(z)


@pytest.fixture()
def env(S, tmp_path, monkeypatch):
    """مجلد كود وهمي بإصدار 1.0.0 + بيانات مستخدم (data/) + لقطات/سجل معزولين."""
    code = tmp_path / "app"
    _tree(str(code), "1.0.0", extra={"erp_app/old_module.py": "old\n", "data/keep.txt": "mine\n", "notes.txt": "user file\n"})
    monkeypatch.setattr(updater, "SNAP_DIR", str(tmp_path / "snaps"))
    monkeypatch.setattr(updater, "WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setattr(updater, "LOG_PATH", str(tmp_path / "log.json"))
    calls = {"backup": 0, "restore": []}

    def fake_backup():
        calls["backup"] += 1
        return {"name": "erp_pre_update_X.db", "path": "x", "size": 1}
    return {"code": str(code), "tmp": tmp_path, "calls": calls, "backup": fake_backup,
            "restore": lambda n: calls["restore"].append(n)}


def _apply(env, pkg, **kw):
    kw.setdefault("verify_fn", lambda d: None)
    return updater.apply(pkg, code_dir=env["code"], backup_fn=env["backup"], restore_db_fn=env["restore"], check_running=False, log=lambda *a: None, **kw)


def test_successful_upgrade_preserves_data_and_replaces_code(env):
    pkg = _zip(env["tmp"], "v2.zip", "2.0.0", extra={"erp_app/new_module.py": "new\n"})
    r = _apply(env, pkg)
    c = env["code"]
    assert r["applied"] and updater.read_version(c) == "2.0.0"
    assert os.path.exists(f"{c}/erp_app/new_module.py")
    assert not os.path.exists(f"{c}/erp_app/old_module.py")             # ملف قديم اتشال مع استبدال المجلد
    assert open(f"{c}/data/keep.txt").read() == "mine\n" and open(f"{c}/notes.txt").read() == "user file\n"
    assert env["calls"]["backup"] == 1 and env["calls"]["restore"] == []
    assert any(f.startswith("code_1.0.0_") for f in os.listdir(env["tmp"] / "snaps"))
    assert updater.history()[-1]["status"] == "ok"


def test_failed_verification_rolls_back_code_and_db(env):
    pkg = _zip(env["tmp"], "v2.zip", "2.0.0", extra={"erp_app/new_module.py": "new\n"})

    def bad(d):
        raise updater.UpdateError("import error في الإصدار الجديد")
    with pytest.raises(updater.UpdateError):
        _apply(env, pkg, verify_fn=bad)
    c = env["code"]
    assert updater.read_version(c) == "1.0.0" and os.path.exists(f"{c}/erp_app/old_module.py") and not os.path.exists(f"{c}/erp_app/new_module.py")
    assert env["calls"]["restore"] == ["erp_pre_update_X.db"]
    assert updater.history()[-1]["status"] == "failed_rolled_back"


def test_dry_run_changes_nothing_and_reports_diff(env):
    pkg = _zip(env["tmp"], "v2.zip", "2.0.0", extra={"erp_app/new_module.py": "new\n"})
    r = updater.apply(pkg, code_dir=env["code"], dry_run=True, check_running=False, log=lambda *a: None)
    assert not r["applied"] and "erp_app/new_module.py" in r["added"] and "erp_app/old_module.py" in r["removed"] and "main.py" in r["changed"]
    assert updater.read_version(env["code"]) == "1.0.0" and env["calls"]["backup"] == 0


def test_downgrade_and_same_version_refused_unless_forced(env):
    old = _zip(env["tmp"], "v0.zip", "0.9.0")
    with pytest.raises(updater.UpdateError, match="أقدم"):
        _apply(env, old)
    same = _zip(env["tmp"], "same.zip", "1.0.0", files={"erp_app/old_module.py": "old\n", "notes.txt": "x"})
    assert _apply(env, old, force=True)["applied"]          # --force بيسمح


def test_bad_packages_are_rejected(env):
    notzip = env["tmp"] / "x.zip"; notzip.write_text("hello")
    with pytest.raises(updater.UpdateError):
        _apply(env, str(notzip))
    nomain = env["tmp"] / "nomain.zip"
    with zipfile.ZipFile(nomain, "w") as z:
        z.writestr("readme.txt", "x")
    with pytest.raises(updater.UpdateError, match="main.py"):
        _apply(env, str(nomain))
    evil = env["tmp"] / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../../escape.txt", "x"); z.writestr("main.py", ""); z.writestr("erp_app/__init__.py", "")
    with pytest.raises(updater.UpdateError, match="غير آمن"):
        _apply(env, str(evil))
    assert not os.path.exists(env["tmp"].parent / "escape.txt")


def test_sha256_mismatch_refused(env):
    pkg = _zip(env["tmp"], "v2.zip", "2.0.0")
    with pytest.raises(updater.UpdateError, match="SHA-256"):
        _apply(env, pkg, sha256="0" * 64)
    import hashlib
    assert _apply(env, pkg, sha256=hashlib.sha256(open(pkg, "rb").read()).hexdigest())["applied"]


def test_package_from_plain_folder(env):
    d = env["tmp"] / "folder_pkg"
    _tree(str(d), "1.5.0")
    assert _apply(env, str(d))["applied"] and updater.read_version(env["code"]) == "1.5.0"


def test_rollback_restores_previous_code_and_db(env):
    pkg = _zip(env["tmp"], "v2.zip", "2.0.0", extra={"erp_app/new_module.py": "new\n"})
    _apply(env, pkg)
    r = updater.rollback(code_dir=env["code"], with_db=True, restore_db_fn=env["restore"], check_running=False, log=lambda *a: None)
    c = env["code"]
    assert r["version"] == "1.0.0" and os.path.exists(f"{c}/erp_app/old_module.py") and not os.path.exists(f"{c}/erp_app/new_module.py")
    assert open(f"{c}/data/keep.txt").read() == "mine\n"
    assert env["calls"]["restore"] == ["erp_pre_update_X.db"]


@pytest.mark.skipif(not IS_SQLITE, reason="قفل SQLite")
def test_refuses_while_app_holds_database(S):
    con = sqlite3.connect(DB_PATH, timeout=1, isolation_level=None)
    con.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(updater.UpdateError, match="شغّال"):
            updater.ensure_not_running()
    finally:
        con.execute("ROLLBACK"); con.close()
    updater.ensure_not_running()


def test_default_backup_creates_pre_update_copy_that_survives_pruning(S):
    b = updater.default_backup()
    assert "_pre_update_" in b["name"] and backup._check(b["path"])
    backup.save_config(keep=1)
    for _ in range(3):
        backup.backup_now("manual")
    assert any(x["kind"] == "pre_update" for x in backup.list_backups())
    backup.save_config(keep=14)


def test_default_verify_passes_on_real_project(S):
    updater.default_verify(updater.ROOT)
