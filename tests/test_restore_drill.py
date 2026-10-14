"""فحص الاسترجاع: استرجاع فعلي في مكان مؤقت، اكتشاف نسخة تالفة، فحص النسخة البعيدة المشفّرة (وكلمة سر غلط)، والجدولة."""
import os

import pytest

from erp_app import backup, backup_remote as br, restore_drill as rd


@pytest.fixture()
def clean(S, tmp_path, monkeypatch):
    monkeypatch.setattr(rd, "PATH", str(tmp_path / "drill.json"))
    monkeypatch.setattr(rd, "CFG_PATH", str(tmp_path / "cfg.json"))
    monkeypatch.setattr(br, "CFG_PATH", str(tmp_path / "br.json"))
    monkeypatch.setattr(br, "STATE_PATH", str(tmp_path / "brs.json"))
    monkeypatch.setattr(br, "SYNC", True)
    for b in backup.list_backups():
        os.remove(b["path"])
    yield S
    for b in backup.list_backups():
        os.remove(b["path"])


def test_no_backup_fails_cleanly(clean):
    r = rd.run_drill()
    assert not r["ok"] and "مفيش نسخة" in r["error"] and rd.last()["ok"] is False
    assert rd.run_due() is None            # لسه مفيش نسخ: مفيش داعي يفشل المجدول


def test_drill_ok_and_due_logic(clean):
    backup.backup_now("manual")
    r = rd.run_drill()
    assert r["ok"] and r["level"] in ("full", "list") and r["remote"] is None
    if r["level"] == "full":
        assert r["rows"]["users"] >= 1
    assert rd.run_due() is None            # لسه في المدة
    rd.save_config(days=1)
    import datetime, json
    old = rd.last(); old["at"] = (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat(timespec="seconds")
    json.dump(old, open(rd.PATH, "w"))
    assert rd.run_due()["ok"]
    rd.save_config(enabled=False)
    old["at"] = "2000-01-01T00:00:00"; json.dump(old, open(rd.PATH, "w"))
    assert rd.run_due() is None


def test_corrupt_backup_detected_and_scheduler_raises(clean):
    b = backup.backup_now("manual")
    with open(b["path"], "r+b") as f:
        f.truncate(300) if backup.IS_SQLITE else f.write(b"garbage")
    r = rd.run_drill()
    assert not r["ok"] and r["error"]
    assert rd.run_due() is None            # فشل قريب: ما يكررش
    import datetime, json
    old = rd.last(); old["at"] = (datetime.datetime.now() - datetime.timedelta(hours=7)).isoformat(timespec="seconds")
    json.dump(old, open(rd.PATH, "w"))
    with pytest.raises(RuntimeError, match="فشل"):
        rd.run_due()


def test_remote_encrypted_ok_and_wrong_passphrase(clean, tmp_path):
    dest = tmp_path / "remote"; dest.mkdir()
    br.save_config(folder_enabled=True, folder_path=str(dest), encrypt=True, passphrase="p@ss-1")
    backup.backup_now("manual")
    assert os.listdir(dest) and all(n.endswith(".enc") for n in os.listdir(dest))
    r = rd.run_drill()
    assert r["ok"] and r["remote"]["ok"] and r["remote"]["encrypted"]
    br.save_config(passphrase="WRONG")
    r = rd.run_drill()
    assert not r["ok"] and not r["remote"]["ok"] and "النسخة البعيدة" in r["error"]


def test_scheduler_has_drill_task():
    from erp_app import scheduler
    assert "drill" in [t[0] for t in scheduler.TASKS]
