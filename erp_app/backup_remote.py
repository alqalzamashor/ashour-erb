"""نسخ احتياطي خارج الجهاز: بعد كل نسخة محلية بترفعها تلقائي لمكان أو أكتر:
  - folder : مجلد شبكة / قرص خارجي / مجلد مزامنة (Dropbox, OneDrive...) - أي مسار متاح للجهاز
  - s3     : أي خدمة بروتوكول S3 (AWS S3 / Cloudflare R2 / Wasabi / MinIO ...) - توقيع SigV4 بدون مكتبات إضافية
  - gdrive : Google Drive (OAuth refresh token لحساب شخصي، أو Service Account لـ Shared Drive)
تشفير اختياري بكلمة سر (AES-256-GCM) قبل الرفع، تحقق من سلامة الرفع (حجم / MD5)، احتفاظ بآخر N نسخة بعيدة،
وإعادة محاولة تلقائية للي فشل. جلب نسخة بعيدة (وفك تشفيرها) لمجلد النسخ المحلي عشان تتسترجع من شاشة النسخ الاحتياطي.
الأوامر:  python -m erp_app.backup_remote  status | sync | test <folder|s3|gdrive> | list <slot>"""
import base64
import datetime
import hashlib
import hmac
import json
import os
import shutil
import struct
import tempfile
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET

from . import audit, backup
from .db import APP_DIR

CFG_PATH = os.path.join(APP_DIR, "backup_remote.json")
STATE_PATH = os.path.join(APP_DIR, "backup_remote_state.json")
SLOTS = {"folder": "مجلد شبكة / قرص خارجي", "s3": "S3 (AWS / R2 / Wasabi / MinIO)", "gdrive": "Google Drive"}
# أسماء المفاتيح السرية فيها secret / token / pass عشان سجل التدقيق يخفي قيمها
DEFAULTS = {
    "encrypt": False, "passphrase": "", "remote_keep": 30,
    "folder_enabled": False, "folder_path": "",
    "s3_enabled": False, "s3_endpoint": "https://s3.amazonaws.com", "s3_region": "us-east-1", "s3_bucket": "", "s3_prefix": "erp-backups/",
    "s3_access_key": "", "s3_secret_key": "", "s3_path_style": True,
    "gd_enabled": False, "gd_auth": "oauth", "gd_client_id": "", "gd_client_secret": "", "gd_refresh_token": "", "gd_service_secret": "", "gd_folder_id": "",
}
TIMEOUT = 60
SYNC = False            # للاختبارات: الرفع في نفس الخيط
GD_TOKEN_URL = "https://oauth2.googleapis.com/token"
GD_API = "https://www.googleapis.com/drive/v3"
GD_UPLOAD = "https://www.googleapis.com/upload/drive/v3"
GD_SCOPE = "https://www.googleapis.com/auth/drive"
_sync_lock = threading.Lock()
_state_lock = threading.RLock()


class RemoteError(Exception):
    pass


# ───────────────────────── الإعدادات والحالة ─────────────────────────
def get_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


@audit.audited_config("إعدادات النسخ الاحتياطي الخارجي")
def save_config(**kw):
    from . import services
    services.require_action("backup", "edit")
    cfg = get_config()
    cfg.update({k: v for k, v in kw.items() if k in DEFAULTS})
    for k, v in list(cfg.items()):
        if isinstance(DEFAULTS[k], str):
            cfg[k] = str(v or "").strip()
    cfg["remote_keep"] = max(1, int(cfg["remote_keep"] or 30))
    if cfg["gd_auth"] not in ("oauth", "service"):
        raise ValueError("طريقة دخول Google: oauth أو service")
    if cfg["encrypt"] and not cfg["passphrase"]:
        raise ValueError("التشفير مفعّل لكن كلمة السر فاضية. من غير كلمة السر النسخ المشفّرة مش هتتفتح أبدًا - احتفظ بها في مكان آمن.")
    for slot in enabled_slots(cfg):
        _validate_slot(slot, cfg)
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    return cfg


def enabled_slots(cfg=None):
    cfg = cfg or get_config()
    return [s for s, p in (("folder", "folder_enabled"), ("s3", "s3_enabled"), ("gdrive", "gd_enabled")) if cfg.get(p)]


def _validate_slot(slot, cfg):
    need = {"folder": ["folder_path"], "s3": ["s3_endpoint", "s3_bucket", "s3_access_key", "s3_secret_key", "s3_region"],
            "gdrive": ["gd_folder_id"] + (["gd_client_id", "gd_client_secret", "gd_refresh_token"] if cfg["gd_auth"] == "oauth" else ["gd_service_secret"])}[slot]
    miss = [k for k in need if not cfg.get(k)]
    if miss:
        raise ValueError(f"إعداد {SLOTS[slot]} ناقص: " + "، ".join(miss))


def _state():
    with _state_lock:
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                st = json.load(f)
        except Exception:
            st = {}
        st.setdefault("uploaded", {}); st.setdefault("last", {})
        return st


def _save_state(st):
    with _state_lock:
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
        os.replace(tmp, STATE_PATH)


def status():
    """ملخص الحالة لكل مكان مفعّل: آخر نتيجة وعدد النسخ المحلية اللي لسه ما اترفعتش."""
    st, cfg = _state(), get_config()
    local = [b["name"] for b in backup.list_backups()]
    out = {}
    for slot in enabled_slots(cfg):
        done = st["uploaded"].get(slot, {})
        out[slot] = {"label": SLOTS[slot], "last": st["last"].get(slot), "pending": len([n for n in local if n not in done]), "uploaded": len(done)}
    return out


# ───────────────────────── التشفير (AES-256-GCM بالأجزاء) ─────────────────────────
MAGIC = b"ERPENC01"
CHUNK = 1024 * 1024


def _key(passphrase, salt):
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    return Scrypt(salt=salt, length=32, n=2 ** 15, r=8, p=1).derive(passphrase.encode("utf-8"))


def encrypt_file(src, dst, passphrase):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not passphrase:
        raise RemoteError("كلمة سر التشفير فاضية")
    salt, prefix = os.urandom(16), os.urandom(8)
    aes = AESGCM(_key(passphrase, salt))
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        fo.write(MAGIC + salt + prefix)
        cur, i = fi.read(CHUNK), 0
        while True:
            nxt = fi.read(CHUNK)
            last = not nxt
            ct = aes.encrypt(prefix + struct.pack(">I", i), cur, b"L" if last else b"M")   # علامة آخر جزء: بتكشف أي قص للملف
            fo.write(struct.pack(">I", len(ct)) + ct)
            if last:
                break
            cur, i = nxt, i + 1


def decrypt_file(src, dst, passphrase):
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    with open(src, "rb") as fi:
        if fi.read(8) != MAGIC:
            raise RemoteError("الملف مش نسخة مشفّرة من البرنامج")
        salt, prefix = fi.read(16), fi.read(8)
        aes = AESGCM(_key(passphrase, salt))
        try:
            with open(dst, "wb") as fo:
                i = 0
                while True:
                    hdr = fi.read(4)
                    if len(hdr) < 4:
                        raise RemoteError("الملف المشفّر مقطوع")
                    ct = fi.read(struct.unpack(">I", hdr)[0])
                    pos = fi.tell(); last = not fi.read(1); fi.seek(pos)
                    fo.write(aes.decrypt(prefix + struct.pack(">I", i), ct, b"L" if last else b"M"))
                    if last:
                        break
                    i += 1
        except InvalidTag:
            if os.path.exists(dst):
                os.remove(dst)
            raise RemoteError("كلمة سر التشفير غلط أو الملف تالف/متعدّل")


# ───────────────────────── المزوّدات ─────────────────────────
def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(CHUNK), b""):
            h.update(b)
    return h.hexdigest()


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(CHUNK), b""):
            h.update(b)
    return h.hexdigest()


class FolderProvider:
    def __init__(self, cfg):
        self.dir = cfg["folder_path"]

    def _p(self, name):
        return os.path.join(self.dir, os.path.basename(name))

    def upload(self, path, name):
        os.makedirs(self.dir, exist_ok=True)
        tmp = self._p(name) + ".part"
        shutil.copyfile(path, tmp)
        if os.path.getsize(tmp) != os.path.getsize(path):
            os.remove(tmp); raise RemoteError("حجم النسخة في المجلد مختلف بعد النسخ")
        os.replace(tmp, self._p(name))
        return name

    def list(self):
        if not os.path.isdir(self.dir):
            return []
        return [{"name": n, "id": n, "size": os.path.getsize(self._p(n)), "at": datetime.datetime.fromtimestamp(os.path.getmtime(self._p(n)))}
                for n in os.listdir(self.dir) if n.startswith("erp_") and not n.endswith(".part")]

    def download(self, rid, dest):
        shutil.copyfile(self._p(rid), dest)

    def delete(self, rid):
        os.remove(self._p(rid))


def sigv4_headers(method, url, region, access_key, secret_key, payload_hash, now=None, service="s3", extra=None):
    """ترويسات AWS Signature V4 لطلب S3 (Authorization + x-amz-date + x-amz-content-sha256)."""
    u = urllib.parse.urlsplit(url)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    amz, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    hdr = {"host": u.netloc, "x-amz-content-sha256": payload_hash, "x-amz-date": amz}
    hdr.update({k.lower(): str(v).strip() for k, v in (extra or {}).items()})
    uri = urllib.parse.quote(urllib.parse.unquote(u.path) or "/", safe="/~")
    qs = "&".join(f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
                  for k, v in sorted(urllib.parse.parse_qsl(u.query, keep_blank_values=True)))
    names = sorted(hdr)
    creq = "\n".join([method, uri, qs, "".join(f"{k}:{hdr[k]}\n" for k in names), ";".join(names), payload_hash])
    scope = f"{day}/{region}/{service}/aws4_request"
    sts = "\n".join(["AWS4-HMAC-SHA256", amz, scope, hashlib.sha256(creq.encode()).hexdigest()])

    def _h(k, m):
        return hmac.new(k, m.encode(), hashlib.sha256).digest()
    k = _h(_h(_h(_h(("AWS4" + secret_key).encode(), day), region), service), "aws4_request")
    sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
    out = {n: hdr[n] for n in names if n != "host"}
    out["Authorization"] = f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={';'.join(names)}, Signature={sig}"
    return out


class S3Provider:
    def __init__(self, cfg):
        self.c = cfg
        self.prefix = cfg["s3_prefix"].lstrip("/")
        if self.prefix and not self.prefix.endswith("/"):
            self.prefix += "/"

    def _url(self, key="", query=""):
        ep = urllib.parse.urlsplit(self.c["s3_endpoint"].rstrip("/") if "://" in self.c["s3_endpoint"] else "https://" + self.c["s3_endpoint"].rstrip("/"))
        k = urllib.parse.quote(key, safe="/~")
        if self.c["s3_path_style"]:
            path = f"/{self.c['s3_bucket']}/{k}" if k else f"/{self.c['s3_bucket']}"
            host = ep.netloc
        else:
            path, host = "/" + k, f"{self.c['s3_bucket']}.{ep.netloc}"
        return f"{ep.scheme}://{host}{path}" + (("?" + query) if query else "")

    def _req(self, method, key="", query="", data=None, payload_hash=None, stream=False, extra=None):
        import requests
        url = self._url(key, query)
        ph = payload_hash or hashlib.sha256(b"").hexdigest()
        h = sigv4_headers(method, url, self.c["s3_region"], self.c["s3_access_key"], self.c["s3_secret_key"], ph, extra=extra)
        r = requests.request(method, url, headers=h, data=data, timeout=TIMEOUT, stream=stream)
        if r.status_code >= 300:
            raise RemoteError(f"S3 {method} فشل ({r.status_code}): {r.text[:300]}")
        return r

    def upload(self, path, name):
        key = self.prefix + name
        md5 = _md5(path)
        with open(path, "rb") as f:
            r = self._req("PUT", key, data=f, payload_hash=_sha256(path))
        etag = (r.headers.get("ETag") or "").strip('"')
        if len(etag) == 32 and etag != md5:
            raise RemoteError("S3: بصمة الملف بعد الرفع مختلفة (ETag) - الرفع غير سليم")
        return key

    def list(self):
        out, token = [], None
        while True:
            q = "list-type=2&prefix=" + urllib.parse.quote(self.prefix + "erp_", safe="-_.~")
            if token:
                q += "&continuation-token=" + urllib.parse.quote(token, safe="-_.~")
            root = ET.fromstring(self._req("GET", "", q).content)
            ns = {"s": root.tag.split("}")[0][1:]} if root.tag.startswith("{") else None
            find = (lambda e, t: e.findall(f"s:{t}", ns)) if ns else (lambda e, t: e.findall(t))
            for c in find(root, "Contents"):
                key = find(c, "Key")[0].text
                lm = find(c, "LastModified")[0].text
                out.append({"name": key[len(self.prefix):], "id": key, "size": int(find(c, "Size")[0].text),
                            "at": datetime.datetime.fromisoformat(lm.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)})
            nt = find(root, "NextContinuationToken")
            if find(root, "IsTruncated") and find(root, "IsTruncated")[0].text == "true" and nt:
                token = nt[0].text
            else:
                return out

    def download(self, rid, dest):
        r = self._req("GET", rid, stream=True)
        with open(dest, "wb") as f:
            for b in r.iter_content(CHUNK):
                f.write(b)

    def delete(self, rid):
        self._req("DELETE", rid)


class DriveProvider:
    def __init__(self, cfg):
        self.c = cfg
        self._tok, self._exp = None, 0

    def _token(self):
        import requests
        if self._tok and time.time() < self._exp - 60:
            return self._tok
        if self.c["gd_auth"] == "oauth":
            data = {"grant_type": "refresh_token", "client_id": self.c["gd_client_id"], "client_secret": self.c["gd_client_secret"], "refresh_token": self.c["gd_refresh_token"]}
        else:
            data = {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": self._jwt()}
        r = requests.post(GD_TOKEN_URL, data=data, timeout=TIMEOUT)
        if r.status_code != 200:
            raise RemoteError(f"Google: فشل تسجيل الدخول ({r.status_code}): {r.text[:300]}")
        j = r.json()
        self._tok, self._exp = j["access_token"], time.time() + int(j.get("expires_in", 3600))
        return self._tok

    def _jwt(self):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        raw = self.c["gd_service_secret"].strip()
        try:
            info = json.loads(raw if raw.startswith("{") else open(raw, encoding="utf-8").read())
        except Exception as ex:
            raise RemoteError(f"ملف/JSON حساب الخدمة غير صالح: {ex}")
        b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=")
        now = int(time.time())
        claims = {"iss": info["client_email"], "scope": GD_SCOPE, "aud": GD_TOKEN_URL, "iat": now, "exp": now + 3600}
        body = b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()) + b"." + b64(json.dumps(claims).encode())
        key = serialization.load_pem_private_key(info["private_key"].encode(), password=None)
        return (body + b"." + b64(key.sign(body, padding.PKCS1v15(), hashes.SHA256()))).decode()

    def _req(self, method, url, **kw):
        import requests
        h = {"Authorization": "Bearer " + self._token()}
        h.update(kw.pop("headers", {}))
        r = requests.request(method, url, headers=h, timeout=kw.pop("timeout", TIMEOUT), **kw)
        if r.status_code >= 300:
            raise RemoteError(f"Google Drive {method} فشل ({r.status_code}): {r.text[:300]}")
        return r

    def upload(self, path, name):
        size = os.path.getsize(path)
        meta = {"name": name, "parents": [self.c["gd_folder_id"]]}
        r = self._req("POST", f"{GD_UPLOAD}/files?uploadType=resumable&supportsAllDrives=true&fields=id,name,size,md5Checksum",
                      json=meta, headers={"X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "application/octet-stream"})
        loc = r.headers.get("Location")
        if not loc:
            raise RemoteError("Google Drive ما رجّعش رابط الرفع")
        with open(path, "rb") as f:
            r = self._req("PUT", loc, data=f, headers={"Content-Type": "application/octet-stream"}, timeout=3600)
        j = r.json()
        if int(j.get("size", size)) != size or (j.get("md5Checksum") and j["md5Checksum"] != _md5(path)):
            raise RemoteError("Google Drive: حجم/بصمة الملف بعد الرفع مختلفة - الرفع غير سليم")
        return j["id"]

    def list(self):
        out, tok = [], None
        while True:
            q = {"q": f"'{self.c['gd_folder_id']}' in parents and trashed=false and name contains 'erp_'", "pageSize": 1000, "supportsAllDrives": "true",
                 "includeItemsFromAllDrives": "true", "fields": "nextPageToken,files(id,name,size,createdTime)"}
            if tok:
                q["pageToken"] = tok
            j = self._req("GET", f"{GD_API}/files", params=q).json()
            for f in j.get("files", []):
                out.append({"name": f["name"], "id": f["id"], "size": int(f.get("size", 0)),
                            "at": datetime.datetime.fromisoformat(f["createdTime"].replace("Z", "+00:00")).astimezone().replace(tzinfo=None)})
            tok = j.get("nextPageToken")
            if not tok:
                return out

    def download(self, rid, dest):
        r = self._req("GET", f"{GD_API}/files/{rid}", params={"alt": "media", "supportsAllDrives": "true"}, stream=True, timeout=3600)
        with open(dest, "wb") as f:
            for b in r.iter_content(CHUNK):
                f.write(b)

    def delete(self, rid):
        self._req("DELETE", f"{GD_API}/files/{rid}", params={"supportsAllDrives": "true"})


def provider(slot, cfg=None):
    cfg = cfg or get_config()
    _validate_slot(slot, cfg)
    return {"folder": FolderProvider, "s3": S3Provider, "gdrive": DriveProvider}[slot](cfg)


# ───────────────────────── الرفع والمزامنة ─────────────────────────
def _remote_name(local_name, cfg):
    return local_name + ".enc" if cfg["encrypt"] else local_name


def _is_protected(n):
    return "_pre_restore_" in n or "_pre_update_" in n


def _prune_remote(prov, keep):
    rows = sorted((r for r in prov.list() if not _is_protected(r["name"])), key=lambda r: r["at"], reverse=True)
    for r in rows[keep:]:
        try:
            prov.delete(r["id"])
        except Exception:
            pass


def _upload_one(slot, prov, cfg, local):
    src, tmp = local["path"], None
    try:
        if cfg["encrypt"]:
            fd, tmp = tempfile.mkstemp(suffix=".enc", dir=backup.BACKUP_DIR); os.close(fd)
            encrypt_file(src, tmp, cfg["passphrase"])
            src = tmp
        return prov.upload(src, _remote_name(local["name"], cfg))
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


def sync_pending():
    """بيرفع كل نسخة محلية لسه ما اترفعتش لكل مكان مفعّل. فشل مكان ما بيوقفش الباقي. بيرجّع {slot: {uploaded: n, error: str|None}}."""
    cfg = get_config()
    slots = enabled_slots(cfg)
    if not slots or not _sync_lock.acquire(blocking=False):
        return {}
    res = {}
    try:
        locals_ = sorted(backup.list_backups()[:cfg["remote_keep"]], key=lambda b: b["at"])
        for slot in slots:
            n, err = 0, None
            try:
                prov = provider(slot, cfg)
                st = _state()
                done = st["uploaded"].setdefault(slot, {})
                for b in locals_:
                    if b["name"] in done:
                        continue
                    rid = _upload_one(slot, prov, cfg, b)
                    done[b["name"]] = {"remote": _remote_name(b["name"], cfg), "id": rid, "at": datetime.datetime.now().isoformat(timespec="seconds")}
                    st["last"][slot] = {"ok": True, "at": done[b["name"]]["at"], "name": b["name"], "error": None}
                    _save_state(st); n += 1
                if n:
                    _prune_remote(prov, cfg["remote_keep"])
            except Exception as ex:
                err = str(ex)[:400]
                st = _state()
                prev = st["last"].get(slot) or {}
                st["last"][slot] = {"ok": False, "at": datetime.datetime.now().isoformat(timespec="seconds"), "name": prev.get("name"), "error": err}
                _save_state(st)
            res[slot] = {"uploaded": n, "error": err}
        if any(r["uploaded"] for r in res.values()) or any(r["error"] for r in res.values()):
            audit.log_event("backup_remote", label="رفع نسخ احتياطية خارجية", changes=json.dumps({k: v for k, v in res.items()}, ensure_ascii=False), username="system")
    finally:
        _sync_lock.release()
    return res


def after_backup(name=None):
    """بتتنادى بعد كل نسخة محلية ناجحة (من backup.backup_now)."""
    if not enabled_slots():
        return
    if SYNC:
        sync_pending()
    else:
        threading.Thread(target=lambda: sync_pending(), daemon=True).start()


def retry_pending():
    """للحلقة الدورية: لو فيه نسخ ما اترفعتش (فشل سابق) بيعيد المحاولة."""
    if enabled_slots() and any(v["pending"] for v in status().values()):
        return sync_pending()
    return {}


def sync_now():
    from . import services
    services.require_action("backup", "edit")
    if not enabled_slots():
        raise RemoteError("مفيش مكان خارجي مفعّل")
    return sync_pending()


def test_slot(slot, **override):
    """تجربة اتصال: يرفع ملف صغير ويقراه ويمسحه. override = قيم من الشاشة لسه ما اتحفظتش."""
    from . import services
    services.require_action("backup", "edit")
    cfg = get_config(); cfg.update({k: v for k, v in override.items() if k in DEFAULTS})
    prov = provider(slot, cfg)
    name = f"erp_connection_test_{int(time.time())}.txt"
    fd, tmp = tempfile.mkstemp(suffix=".txt"); os.close(fd)
    out = tmp + ".back"
    try:
        with open(tmp, "w") as f:
            f.write("erp backup connection test")
        rid = prov.upload(tmp, name)
        rid = next((r["id"] for r in prov.list() if r["name"] == name), rid)
        prov.download(rid, out)
        if open(out).read() != "erp backup connection test":
            raise RemoteError("المحتوى بعد القراءة مختلف")
        prov.delete(rid)
    finally:
        for p in (tmp, out):
            if os.path.exists(p):
                os.remove(p)
    return f"الاتصال بـ {SLOTS[slot]} شغال (رفع / قراءة / حذف)"


def list_remote(slot):
    from . import services
    services.require_action("backup", "view")
    return sorted(provider(slot).list(), key=lambda r: r["at"], reverse=True)


def fetch_remote(slot, name):
    """بيجيب نسخة من المكان البعيد لمجلد النسخ المحلي (وبيفك التشفير) وبيتأكد من سلامتها. بعدها تتسترجع من شاشة النسخ."""
    from . import services
    services.require_action("backup", "edit")
    cfg = get_config()
    prov = provider(slot, cfg)
    item = next((r for r in prov.list() if r["name"] == name), None)
    if not item:
        raise RemoteError("النسخة مش موجودة في المكان البعيد")
    local_name = name[:-4] if name.endswith(".enc") else name
    dest = os.path.join(backup.BACKUP_DIR, os.path.basename(local_name))
    if os.path.exists(dest):
        return local_name
    fd, tmp = tempfile.mkstemp(dir=backup.BACKUP_DIR); os.close(fd)
    try:
        prov.download(item["id"], tmp)
        if name.endswith(".enc"):
            if not cfg["passphrase"]:
                raise RemoteError("النسخة مشفّرة - اكتب كلمة سر التشفير في الإعدادات الأول")
            decrypt_file(tmp, dest, cfg["passphrase"])
        else:
            os.replace(tmp, dest)
        if not backup._check(dest):
            os.remove(dest)
            raise RemoteError("النسخة اللي اتجابت تالفة (فشل فحص السلامة)")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    audit.log_event("backup_fetch", label=local_name, changes=slot)
    return local_name


if __name__ == "__main__":
    import sys
    from . import db
    db.init_db()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=1, default=str))
    elif cmd == "sync":
        print(json.dumps(sync_pending(), ensure_ascii=False, indent=1))
    elif cmd == "test" and len(sys.argv) > 2:
        print(test_slot(sys.argv[2]))
    elif cmd == "list" and len(sys.argv) > 2:
        for r in list_remote(sys.argv[2]):
            print(r["at"], r["size"], r["name"])
    else:
        print(__doc__)
