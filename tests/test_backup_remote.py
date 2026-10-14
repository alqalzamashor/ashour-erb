import datetime
import json
import os

import pytest

from erp_app import backup, backup_remote as br
from erp_app.db import AuditLog, get_session
from tests.fake_cloud import Cloud


@pytest.fixture(autouse=True)
def _sync_mode(monkeypatch):
    monkeypatch.setattr(br, "SYNC", True)


@pytest.fixture()
def cloud(monkeypatch):
    c = Cloud()
    monkeypatch.setattr(br, "GD_TOKEN_URL", c.url + "/token")
    monkeypatch.setattr(br, "GD_API", c.url + "/drive/v3")
    monkeypatch.setattr(br, "GD_UPLOAD", c.url + "/upload/drive/v3")
    yield c
    c.close()


@pytest.fixture()
def clean(S):
    """يفضّي إعدادات/حالة الرفع الخارجي وكل النسخ المحلية قبل كل اختبار."""
    for p in (br.CFG_PATH, br.STATE_PATH):
        if os.path.exists(p):
            os.remove(p)
    for b in backup.list_backups():
        os.remove(b["path"])
    yield S
    for p in (br.CFG_PATH, br.STATE_PATH):
        if os.path.exists(p):
            os.remove(p)


S3CFG = dict(s3_enabled=True, s3_bucket="bkt", s3_access_key="AK", s3_secret_key="SK", s3_region="eu-west-1", s3_prefix="erp-backups/")


def test_encrypt_roundtrip_multichunk_and_tamper(tmp_path):
    src, enc, dec = tmp_path / "a.bin", tmp_path / "a.enc", tmp_path / "a.out"
    data = os.urandom(br.CHUNK * 2 + 123)
    src.write_bytes(data)
    br.encrypt_file(str(src), str(enc), "كلمة-سر")
    assert enc.read_bytes()[:8] == br.MAGIC and data[:64] not in enc.read_bytes()
    br.decrypt_file(str(enc), str(dec), "كلمة-سر")
    assert dec.read_bytes() == data
    with pytest.raises(br.RemoteError):
        br.decrypt_file(str(enc), str(tmp_path / "x"), "غلط")
    raw = enc.read_bytes()
    first_len = int.from_bytes(raw[32:36], "big")
    cut = tmp_path / "cut.enc"
    cut.write_bytes(raw[:32 + 4 + first_len])           # قص بعد أول جزء بالظبط
    with pytest.raises(br.RemoteError):
        br.decrypt_file(str(cut), str(tmp_path / "y"), "كلمة-سر")


def test_folder_target_uploads_and_prunes(clean, tmp_path):
    dest = tmp_path / "net"
    br.save_config(folder_enabled=True, folder_path=str(dest), remote_keep=2)
    names = [backup.backup_now("manual")["name"] for _ in range(3)]
    safety = backup.backup_now("pre_update")["name"]
    got = sorted(os.listdir(dest))
    assert safety in got                                        # نسخ الأمان ما بتتمسحش من المكان البعيد
    assert len([n for n in got if "_manual_" in n]) == 2 and names[0] not in got
    assert br.status()["folder"]["pending"] == 0 and br.status()["folder"]["last"]["ok"]
    assert "تم" in br.test_slot("folder") or "شغال" in br.test_slot("folder")


def test_encrypted_upload_and_fetch_back(clean, tmp_path):
    dest = tmp_path / "enc"
    br.save_config(folder_enabled=True, folder_path=str(dest), encrypt=True, passphrase="p@ss")
    b = backup.backup_now("manual")
    remote = [n for n in os.listdir(dest)]
    assert remote == [b["name"] + ".enc"]
    assert (dest / remote[0]).read_bytes()[:8] == br.MAGIC
    os.remove(b["path"])
    local = br.fetch_remote("folder", remote[0])
    assert local == b["name"] and backup._check(os.path.join(backup.BACKUP_DIR, local))
    assert any(x["name"] == local for x in backup.list_backups())


def test_config_validation_and_secret_masking(clean):
    with pytest.raises(ValueError):
        br.save_config(encrypt=True, passphrase="")
    with pytest.raises(ValueError):
        br.save_config(s3_enabled=True, s3_bucket="")
    br.save_config(**{**S3CFG, "s3_endpoint": "http://127.0.0.1:1"})
    br.save_config(s3_secret_key="NEW-SECRET-VALUE")
    with get_session() as s:
        rows = [r.changes for r in s.query(AuditLog).filter(AuditLog.action == "config").all() if r.changes]
    assert rows and not any("NEW-SECRET-VALUE" in r or '"SK"' in r for r in rows)


def test_s3_upload_list_paging_fetch_and_prune(clean, cloud):
    br.save_config(**S3CFG, s3_endpoint=cloud.url, s3_path_style=True, remote_keep=3)
    assert "شغال" in br.test_slot("s3")
    names = [backup.backup_now("manual")["name"] for _ in range(4)]
    keys = sorted(cloud.s3)
    assert len(keys) == 3 and all(k.startswith("erp-backups/erp_manual_") for k in keys)       # الاحتفاظ بآخر 3
    items = br.list_remote("s3")                                                              # القائمة على صفحتين
    assert len(items) == 3 and {i["name"] for i in items} <= set(names)
    os.remove(os.path.join(backup.BACKUP_DIR, items[0]["name"]))
    assert br.fetch_remote("s3", items[0]["name"]) == items[0]["name"]


def test_s3_failure_then_retry(clean, cloud):
    br.save_config(**S3CFG, s3_endpoint=cloud.url)
    cloud.fail_next = 1
    b = backup.backup_now("manual")                                  # الرفع بيفشل لكن النسخة المحلية سليمة
    st = br.status()["s3"]
    assert os.path.exists(b["path"]) and st["pending"] == 1 and st["last"]["ok"] is False and "500" in st["last"]["error"]
    assert not cloud.s3
    br.retry_pending()
    assert len(cloud.s3) == 1 and br.status()["s3"]["pending"] == 0


def test_s3_wrong_etag_detected(clean, cloud, monkeypatch):
    br.save_config(**S3CFG, s3_endpoint=cloud.url)
    monkeypatch.setattr(br, "_md5", lambda p: "0" * 32)
    backup.backup_now("manual")
    assert br.status()["s3"]["last"]["ok"] is False and "ETag" in br.status()["s3"]["last"]["error"]


def test_s3_virtual_host_url():
    p = br.S3Provider({**br.DEFAULTS, **S3CFG, "s3_endpoint": "https://s3.eu-west-1.amazonaws.com", "s3_path_style": False})
    assert p._url("erp-backups/a.db") == "https://bkt.s3.eu-west-1.amazonaws.com/erp-backups/a.db"
    p.c["s3_path_style"] = True
    assert p._url("erp-backups/a.db") == "https://s3.eu-west-1.amazonaws.com/bkt/erp-backups/a.db"


def test_sigv4_matches_botocore():
    bc = pytest.importorskip("botocore.auth")
    import hashlib
    from botocore.awsrequest import AWSRequest
    from botocore.credentials import Credentials
    body = b"x" * 500
    for method, url, data in [("PUT", "https://s3.amazonaws.com/my-bucket/erp-backups/erp_a.db", body),
                              ("GET", "http://127.0.0.1:9000/b?list-type=2&prefix=erp-backups%2Ferp_&continuation-token=a%2Bb%3D", b""),
                              ("DELETE", "https://b.s3.eu-west-1.amazonaws.com/p%20x/erp_a.db", b"")]:
        req = AWSRequest(method=method, url=url, data=data)
        bc.S3SigV4Auth(Credentials("AKIDEXAMPLE", "SECRET"), "s3", "eu-west-1").add_auth(req)
        ts = datetime.datetime.strptime(req.headers["X-Amz-Date"], "%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc)
        mine = br.sigv4_headers(method, url, "eu-west-1", "AKIDEXAMPLE", "SECRET", hashlib.sha256(data).hexdigest(), now=ts)
        assert mine["Authorization"] == req.headers["Authorization"], method


def test_gdrive_oauth_upload_fetch_prune(clean, cloud):
    br.save_config(gd_enabled=True, gd_auth="oauth", gd_client_id="cid", gd_client_secret="csecret", gd_refresh_token="rtok", gd_folder_id="FOLDER1", remote_keep=2)
    assert "شغال" in br.test_slot("gdrive")
    for _ in range(3):
        backup.backup_now("manual")
    assert len(cloud.gd) == 2 and all(f["parent"] == "FOLDER1" for f in cloud.gd.values())
    items = br.list_remote("gdrive")
    local = os.path.join(backup.BACKUP_DIR, items[0]["name"])
    os.remove(local)
    br.fetch_remote("gdrive", items[0]["name"])
    assert backup._check(local)
    br.save_config(gd_refresh_token="wrong")
    cloud.tokens.clear()
    with pytest.raises(br.RemoteError):
        br.test_slot("gdrive")


def test_gdrive_service_account_jwt(clean, cloud):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cloud.sa_public_key = key.public_key()
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    info = json.dumps({"client_email": "sa@proj.iam.gserviceaccount.com", "private_key": pem})
    br.save_config(gd_enabled=True, gd_auth="service", gd_service_secret=info, gd_folder_id="SHARED")
    backup.backup_now("manual")
    assert len(cloud.gd) == 1 and next(iter(cloud.gd.values()))["parent"] == "SHARED"


def test_one_target_failing_does_not_block_others(clean, cloud, tmp_path):
    br.save_config(folder_enabled=True, folder_path=str(tmp_path / "ok"), **S3CFG, s3_endpoint="http://127.0.0.1:1")
    backup.backup_now("manual")
    st = br.status()
    assert st["folder"]["pending"] == 0 and st["s3"]["pending"] == 1 and st["s3"]["last"]["ok"] is False
