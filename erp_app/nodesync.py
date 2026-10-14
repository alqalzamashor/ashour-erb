"""نسخة فرع محلية (offline كامل) + مزامنة مع المركز.

الفكرة: الفرع بيشغّل النظام كامل على جهاز محلي بقاعدته (يشتغل من غير إنترنت). كل عملية أعمال مهمة (فاتورة/كاشير/سند/مشتريات...) بتتنفّذ محليًا وبتتسجّل في
طابور (sync_ops). لما الاتصال يرجع الدورة بتعمل:
  1) push: بيبعت العمليات المعلّقة بالترتيب، والمركز بيعيد تنفيذها بنفس الدوال وبنفس التاريخ الأصلي (clock.at) ويرد برقم المستند عنده. التكرار ممنوع (node_id + uuid).
  2) pull: لو مفيش عمليات معلّقة/فاشلة، بينزّل نسخة محدّثة من المركز (بيانات أساسية + حركات + مخزون) وتحل محل القاعدة المحلية - فالفرع بيشوف مخزون وأسعار ومستندات المركز.
ملاحظات: أرقام المستندات اللي بتتطبع على الفرع محلية، والمركز بيدّي رقمه (بيظهر في شاشة المزامنة). التعديل على البيانات الأساسية (أصناف/عملاء/حسابات) بيتم من المركز بس.
المتغيرات (على الفرع): ERP_NODE_ID, ERP_HQ_URL (مثلًا https://hq.example.com أو http://IP:8600 - البورت الداخلي), ERP_SYNC_KEY, ERP_SYNC_INTERVAL (ثواني، افتراضي 60).
على المركز: python sync_admin.py add-node BR02 بيطبع المفتاح."""
import base64
import contextlib
import datetime
import functools
import gzip
import hashlib
import hmac
import io
import json
import os
import secrets
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid as _uuid

from . import clock
from .db import APP_DIR

# اسم الدالة -> مواصفاتها. consumes: (اسم المعامل, الكيان, مسموح محلي?) | produces: الكيان الناتج من قيمة الرجوع (int)
OPS = {
    "open_pos_session": {"produces": "PosSession"},
    "close_pos_session": {"consumes": ("session_id", "PosSession", True)},
    "create_pos_sale": {},
    "create_pos_split_sale": {},
    "create_sales_invoice": {},
    "create_sales_return": {"consumes": ("invoice_id", "SalesInvoice", False)},
    "create_full_sales_return": {"consumes": ("invoice_id", "SalesInvoice", False)},
    "create_receipt": {},
    "create_payment": {},
    "create_purchase_invoice": {},
    "create_goods_receipt": {},
    "create_stock_transfer_batch": {},
    "create_inventory_adjustment": {},
    "create_damage_entry": {},
}
# جداول مش بتتنقل في التنزيل (محلية للفرع أو مش لازمة)
EXCLUDE_TABLES = {"sync_ops", "sync_inbox", "sync_map", "sync_state", "audit_logs", "chat_messages", "chat_members", "chat_conversations",
                  "notification_logs", "print_jobs", "kitchen_events"}
PUSH_BATCH = 40
_tl = threading.local()
_lock = threading.RLock()
_NODES = os.path.join(APP_DIR, "sync_nodes.json")


# ------------------------------------------------------------------ الإعدادات
def node_id():
    return (os.environ.get("ERP_NODE_ID") or "").strip()


def is_node():
    return bool(node_id())


def hq_url():
    return (os.environ.get("ERP_HQ_URL") or "").strip().rstrip("/")


def sync_key():
    return (os.environ.get("ERP_SYNC_KEY") or "").strip()


# ------------------------------------------------------------------ ترميز القيم (JSON)
def enc(v):
    if isinstance(v, datetime.datetime):
        return {"__dt__": v.isoformat()}
    if isinstance(v, datetime.date):
        return {"__d__": v.isoformat()}
    if isinstance(v, (bytes, bytearray)):
        return {"__b__": base64.b64encode(bytes(v)).decode()}
    if isinstance(v, dict):
        return {str(k): enc(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [enc(x) for x in v]
    if hasattr(v, "__float__") and not isinstance(v, (int, float, bool)):
        return float(v)
    return v


def dec(v):
    if isinstance(v, dict):
        if len(v) == 1:
            if "__dt__" in v:
                return datetime.datetime.fromisoformat(v["__dt__"])
            if "__d__" in v:
                return datetime.date.fromisoformat(v["__d__"])
            if "__b__" in v:
                return base64.b64decode(v["__b__"])
        return {k: dec(x) for k, x in v.items()}
    if isinstance(v, list):
        return [dec(x) for x in v]
    return v


# ------------------------------------------------------------------ حالة الفرع
def _state_get(key, default=""):
    from .db import SyncState, get_session
    with get_session() as s:
        r = s.get(SyncState, key)
        return r.value if r else default


def _state_set(key, value):
    from .db import SyncState, get_session
    with get_session() as s:
        r = s.get(SyncState, key)
        if r:
            r.value = str(value)
        else:
            s.add(SyncState(key=key, value=str(value)))
        s.commit()


def _max_id(model):
    from sqlalchemy import func
    from .db import get_session
    with get_session() as s:
        return int(s.query(func.max(model.id)).scalar() or 0)


def _entity_model(name):
    from . import db
    return {"SalesInvoice": db.SalesInvoice, "PosSession": db.PosSession}[name]


def ensure_baseline():
    """بيسجّل أكبر معرّفات المستندات الموجودة (من نسخة المركز) علشان نفرّق مستند محلي جديد عن مستند قديم."""
    for ent in ("SalesInvoice", "PosSession"):
        if not _state_get("base:" + ent):
            _state_set("base:" + ent, _max_id(_entity_model(ent)))


def _check_consumes(name, spec, args, kwargs):
    c = spec.get("consumes")
    if not c:
        return
    pname, ent, allow_local = c
    val = kwargs.get(pname, args[0] if args else None)
    try:
        val = int(val)
    except (TypeError, ValueError):
        return
    ensure_baseline()
    if val > int(_state_get("base:" + ent) or 0) and not allow_local:
        raise ValueError("المستند ده اتعمل على نسخة الفرع ولسه ما اتزامنش مع المركز - زامن الأول وبعدها اعمل المرتجع")


# ------------------------------------------------------------------ تسجيل العمليات (الفرع)
def _ref_for(fn, res):
    try:
        from .db import SalesInvoice, get_session
        iid = res.get("invoice_id") if isinstance(res, dict) else (res if fn in ("create_sales_invoice", "create_purchase_invoice") else None)
        if iid:
            with get_session() as s:
                inv = s.get(SalesInvoice, int(iid))
                if inv:
                    return inv.number
    except Exception:      # noqa: BLE001
        pass
    return ""


def record_op(fn, args, kwargs, res):
    from . import services
    from .db import SyncOp, get_session
    u = services.current_user() or {}
    spec = OPS.get(fn, {})
    produced = {}
    if spec.get("produces") and isinstance(res, int):
        produced[spec["produces"]] = int(res)
    rec = {"uuid": _uuid.uuid4().hex, "fn": fn, "payload": json.dumps({"args": enc(list(args)), "kwargs": enc(dict(kwargs))}, ensure_ascii=False),
           "username": (u.get("username") if isinstance(u, dict) else getattr(u, "username", "")) or "", "at": datetime.datetime.now(),
           "local_ref": _ref_for(fn, res), "produced": json.dumps(produced) if produced else ""}
    try:
        with get_session() as s:
            s.add(SyncOp(**rec))
            s.commit()
    except Exception as ex:      # noqa: BLE001
        with contextlib.suppress(Exception):
            with open(os.path.join(APP_DIR, "sync_lost.log"), "a", encoding="utf-8") as f:
                f.write(json.dumps({**rec, "at": rec["at"].isoformat(), "error": str(ex)[:200]}, ensure_ascii=False) + "\n")
        raise RuntimeError("العملية اتنفّذت محليًا لكن تسجيلها للمزامنة فشل - بلّغ المسؤول (محفوظة في sync_lost.log)") from ex
    return rec["uuid"]


def _wrap(name, fn, spec):
    @functools.wraps(fn)
    def w(*a, **k):
        if getattr(_tl, "depth", 0) > 0 or getattr(_tl, "replay", False):
            return fn(*a, **k)
        _check_consumes(name, spec, a, k)
        _tl.depth = 1
        try:
            res = fn(*a, **k)
        finally:
            _tl.depth = 0
        record_op(name, a, k, res)
        return res
    w._erp_sync_wrapped = True
    return w


def install(services_mod=None):
    """بيغلّف دوال العمليات المدعومة في services لتسجيلها (نسخة فرع فقط). آمن لو اتنادى مرتين."""
    if not is_node():
        return 0
    if services_mod is None:
        from . import services as services_mod
    n = 0
    for name, spec in OPS.items():
        f = getattr(services_mod, name, None)
        if f is not None and not getattr(f, "_erp_sync_wrapped", False):
            setattr(services_mod, name, _wrap(name, f, spec))
            n += 1
    ensure_baseline()
    return n


# ------------------------------------------------------------------ المركز: تسجيل الفروع والمصادقة
def _nodes_read():
    try:
        return json.load(open(_NODES, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _nodes_write(d):
    with open(_NODES + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(_NODES + ".tmp", _NODES)


def add_node(nid, label=""):
    nid = (nid or "").strip()
    if not nid or not nid.replace("-", "").replace("_", "").isalnum():
        raise ValueError("اسم الفرع لازم حروف/أرقام/شرطة بس")
    with _lock:
        d = _nodes_read()
        if nid in d:
            raise ValueError("الفرع ده متسجّل قبل كده")
        key = secrets.token_urlsafe(24)
        d[nid] = {"key": key, "label": label, "created": datetime.datetime.now().isoformat(timespec="seconds"), "last_seen": ""}
        _nodes_write(d)
    return key


def remove_node(nid):
    with _lock:
        d = _nodes_read()
        d.pop(nid, None)
        _nodes_write(d)


def list_nodes():
    return [{"node_id": k, "label": v.get("label", ""), "last_seen": v.get("last_seen", ""), "created": v.get("created", "")} for k, v in _nodes_read().items()]


def auth_node(nid, key):
    v = _nodes_read().get(nid or "")
    if not v or not key or not hmac.compare_digest(str(key).encode(), str(v.get("key", "")).encode()):
        return False
    with _lock:
        d = _nodes_read()
        if nid in d:
            d[nid]["last_seen"] = datetime.datetime.now().isoformat(timespec="seconds")
            _nodes_write(d)
    return True


# ------------------------------------------------------------------ المركز: إعادة تنفيذ العمليات
def _summ(fn, res):
    out = {}
    try:
        from .db import SalesInvoice, get_session
        iid = res.get("invoice_id") if isinstance(res, dict) else (res if fn == "create_sales_invoice" else None)
        if isinstance(iid, int):
            out["invoice_id"] = iid
            with get_session() as s:
                inv = s.get(SalesInvoice, iid)
                if inv:
                    out["number"] = inv.number
        elif isinstance(res, int):
            out["id"] = res
        elif isinstance(res, list):
            out["count"] = len(res)
    except Exception:      # noqa: BLE001
        pass
    return out


def _user_dict(username):
    from .db import User, get_session
    with get_session() as s:
        u = s.query(User).filter(User.username == username).first()
        if not u or not getattr(u, "active", True):
            return None
        return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role, "permissions": u.permissions or "{}",
                "branch_ids": u.branch_ids or "[]", "cost_center_ids": getattr(u, "cost_center_ids", "[]") or "[]", "needs_2fa_setup": False}


def _map_get(nid, ent, node_ref):
    from .db import SyncMap, get_session
    with get_session() as s:
        r = s.query(SyncMap).filter(SyncMap.node_id == nid, SyncMap.entity == ent, SyncMap.node_ref == int(node_ref)).first()
        return r.hq_ref if r else None


def apply_ops(nid, ops):
    """(المركز) بينفّذ عمليات فرع بالترتيب. بيرجّع [{uuid,status,result,error}] - التكرار بيرجّع النتيجة المخزّنة من غير تنفيذ تاني."""
    from . import services
    from .db import SyncInbox, SyncMap, get_session
    out = []
    with _lock:
        for op in ops:
            u = str(op.get("uuid") or "")
            fn = str(op.get("fn") or "")
            with get_session() as s:
                old = s.query(SyncInbox).filter(SyncInbox.node_id == nid, SyncInbox.uuid == u).first()
                if old and old.status == "applied":
                    out.append({"uuid": u, "status": "applied", "result": json.loads(old.result or "{}"), "error": "", "duplicate": True})
                    continue
            status, result, error = "applied", {}, ""
            try:
                spec = OPS.get(fn)
                if spec is None:
                    raise ValueError("عملية غير مدعومة في المزامنة: " + fn)
                user = _user_dict(op.get("username"))
                if not user:
                    raise ValueError("المستخدم %r مش موجود/موقوف عند المركز" % op.get("username"))
                body = json.loads(op.get("payload") or "{}")
                args, kwargs = dec(body.get("args", [])), dec(body.get("kwargs", {}))
                c = spec.get("consumes")
                if c:
                    pname, ent, _allow = c
                    pos = 0
                    if pname in kwargs:
                        v = kwargs[pname]
                    else:
                        v = args[pos]
                    hq = _map_get(nid, ent, v)
                    if hq is not None:
                        if pname in kwargs:
                            kwargs[pname] = hq
                        else:
                            args[pos] = hq
                prev = services.current_user()
                services.set_current_user(user)
                _tl.replay = True
                try:
                    with clock.at(op.get("at") or datetime.datetime.now()):
                        res = getattr(services, fn)(*args, **kwargs)
                finally:
                    _tl.replay = False
                    services.set_current_user(prev)
                result = _summ(fn, res)
                produced = op.get("produced") or ""
                if produced and spec.get("produces") and isinstance(res, int):
                    pj = json.loads(produced)
                    nref = pj.get(spec["produces"])
                    if nref is not None:
                        with get_session() as s:
                            s.add(SyncMap(node_id=nid, entity=spec["produces"], node_ref=int(nref), hq_ref=int(res)))
                            s.commit()
            except Exception as ex:      # noqa: BLE001
                status, error = "failed", (str(ex) or type(ex).__name__)[:400]
            with get_session() as s:
                row = s.query(SyncInbox).filter(SyncInbox.node_id == nid, SyncInbox.uuid == u).first()
                if row is None:
                    row = SyncInbox(node_id=nid, uuid=u, fn=fn)
                    s.add(row)
                row.status, row.error, row.result = status, error, json.dumps(result, ensure_ascii=False)
                try:
                    row.op_at = datetime.datetime.fromisoformat(op["at"]) if op.get("at") else None
                except (ValueError, TypeError):
                    pass
                s.commit()
            out.append({"uuid": u, "status": status, "result": result, "error": error})
    return out


# ------------------------------------------------------------------ لقطة المركز (التنزيل)
def _tables():
    from .db import Base
    return [t for t in Base.metadata.sorted_tables if t.name not in EXCLUDE_TABLES]


def snapshot_marker():
    """علامة تتغيّر لو أي جدول مشمول اتغيّر عدده/أكبر معرّف (بتحدد لو الفرع محتاج تنزيل)."""
    from sqlalchemy import func, select
    from .db import engine
    parts = []
    with engine.connect() as c:
        for t in _tables():
            pk = list(t.primary_key.columns)
            if len(pk) == 1 and pk[0].type.python_type is int:
                n, m = c.execute(select(func.count(), func.max(pk[0]))).first() if False else c.execute(select(func.count(), func.max(pk[0])).select_from(t)).first()
                parts.append("%s:%s:%s" % (t.name, n, m))
            else:
                parts.append("%s:%s" % (t.name, c.execute(select(func.count()).select_from(t)).scalar()))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


def export_snapshot(fileobj):
    """بيكتب لقطة gzip (سطر JSON لكل دفعة صفوف) لكل الجداول المشمولة."""
    from .db import engine
    gz = gzip.GzipFile(fileobj=fileobj, mode="wb", compresslevel=5)
    gz.write((json.dumps({"meta": {"marker": snapshot_marker(), "at": datetime.datetime.now().isoformat(timespec="seconds")}}) + "\n").encode())
    with engine.connect() as c:
        for t in _tables():
            batch = []
            for row in c.execute(t.select()).mappings():
                batch.append({k: enc(v) for k, v in row.items()})
                if len(batch) >= 2000:
                    gz.write((json.dumps({"t": t.name, "rows": batch}, ensure_ascii=False) + "\n").encode())
                    batch = []
            gz.write((json.dumps({"t": t.name, "rows": batch}, ensure_ascii=False) + "\n").encode())
    gz.close()


def _coerce(col, v):
    from sqlalchemy import Date, DateTime, LargeBinary
    v = dec(v)
    if v is None:
        return None
    if isinstance(col.type, DateTime) and isinstance(v, str):
        return datetime.datetime.fromisoformat(v)
    if isinstance(col.type, Date) and not isinstance(col.type, DateTime) and isinstance(v, str):
        return datetime.date.fromisoformat(v)
    if isinstance(col.type, LargeBinary) and isinstance(v, str):
        return base64.b64decode(v)
    return v


def apply_snapshot(path):
    """(الفرع) بيستبدل الجداول المشمولة بلقطة المركز في معاملة واحدة (يا كله يا ولا حاجة). بيرجّع العلامة."""
    from sqlalchemy import text
    from .db import IS_SQLITE, engine
    tables = {t.name: t for t in _tables()}
    data = {}
    marker = ""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for ln in f:
            o = json.loads(ln)
            if "meta" in o:
                marker = o["meta"]["marker"]
            elif o["t"] in tables:
                data.setdefault(o["t"], []).extend(o["rows"])
    if not marker:
        raise RuntimeError("لقطة المركز ناقصة/تالفة")
    ordered = _tables()
    with engine.begin() as c:
        for t in reversed(ordered):
            c.execute(t.delete())
        for t in ordered:
            rows = data.get(t.name) or []
            cols = {col.name: col for col in t.columns}
            clean = [{k: _coerce(cols[k], v) for k, v in r.items() if k in cols} for r in rows]
            for i in range(0, len(clean), 500):
                c.execute(t.insert(), clean[i:i + 500])
            if not IS_SQLITE:
                pk = [col for col in t.primary_key.columns if col.type.python_type is int]
                if len(pk) == 1:
                    c.execute(text("SELECT setval(pg_get_serial_sequence(:t, :c), COALESCE((SELECT MAX(%s) FROM %s), 0) + 1, false)" % (pk[0].name, t.name)), {"t": t.name, "c": pk[0].name})
    return marker


# ------------------------------------------------------------------ مستقبل HTTP عند المركز (بيتنادى من delivery_server)
def handle_http(h, method, path, query):
    """h: BaseHTTPRequestHandler. بيرجّع True لو المسار /sync/* واتعامل معاه."""
    if not path.startswith("/sync/"):
        return False
    nid = h.headers.get("X-Node-Id") or ""
    if not auth_node(nid, h.headers.get("X-Node-Key") or ""):
        h._reply(401, {"ok": False, "error": "unauthorized"})
        return True
    try:
        if path == "/sync/ping" and method == "GET":
            h._reply(200, {"ok": True, "marker": snapshot_marker()})
        elif path == "/sync/push" and method == "POST":
            n = int(h.headers.get("Content-Length") or 0)
            if n <= 0 or n > 20_000_000:
                return h._reply(413, {"ok": False, "error": "bad size"}) or True
            ops = json.loads(h.rfile.read(n).decode("utf-8"))
            h._reply(200, {"ok": True, "results": apply_ops(nid, ops[:PUSH_BATCH * 5])})
        elif path == "/sync/pull" and method == "GET":
            buf = io.BytesIO()
            export_snapshot(buf)
            body = buf.getvalue()
            h.send_response(200)
            h.send_header("Content-Type", "application/gzip")
            h.send_header("Content-Length", str(len(body)))
            h.end_headers()
            h.wfile.write(body)
        else:
            h._reply(404, {"ok": False, "error": "not found"})
    except Exception as ex:      # noqa: BLE001
        h._reply(500, {"ok": False, "error": (str(ex) or type(ex).__name__)[:200]})
    return True


# ------------------------------------------------------------------ الفرع: الإرسال والتنزيل
class HQError(Exception):
    pass


def _req(method, path, body=None, timeout=60):
    url = hq_url() + path
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    rq = urllib.request.Request(url, data=data, method=method, headers={"X-Node-Id": node_id(), "X-Node-Key": sync_key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(rq, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as ex:
        raise HQError("المركز رفض الطلب (%s)" % ex.code) from ex
    except (urllib.error.URLError, OSError, TimeoutError) as ex:
        raise ConnectionError(str(ex)) from ex


def counts():
    from sqlalchemy import func
    from .db import SyncOp, get_session
    with get_session() as s:
        d = dict(s.query(SyncOp.status, func.count()).group_by(SyncOp.status).all())
    return {"pending": d.get("pending", 0), "failed": d.get("failed", 0), "pushed": d.get("pushed", 0)}


def push():
    """بيبعت العمليات المعلّقة. بيرجّع {'sent','failed'} وبيرمي ConnectionError لو المركز مش متاح."""
    from .db import SyncOp, get_session
    out = {"sent": 0, "failed": 0}
    while True:
        with get_session() as s:
            rows = s.query(SyncOp).filter(SyncOp.status == "pending").order_by(SyncOp.id).limit(PUSH_BATCH).all()
            batch = [{"uuid": r.uuid, "fn": r.fn, "payload": r.payload, "username": r.username, "at": r.at.isoformat(), "produced": r.produced} for r in rows]
        if not batch:
            return out
        res = json.loads(_req("POST", "/sync/push", batch, timeout=300))
        by = {x["uuid"]: x for x in res.get("results", [])}
        with get_session() as s:
            for r in s.query(SyncOp).filter(SyncOp.uuid.in_(list(by))).all():
                x = by[r.uuid]
                r.attempts = (r.attempts or 0) + 1
                if x["status"] == "applied":
                    r.status, r.error, r.hq_ref = "pushed", "", json.dumps(x.get("result") or {}, ensure_ascii=False)
                    out["sent"] += 1
                else:
                    r.status, r.error = "failed", (x.get("error") or "")[:400]
                    out["failed"] += 1
            s.commit()
        if len(by) < len(batch):
            return out


def pull(force=False):
    """بينزّل لقطة المركز ويستبدل بيها القاعدة المحلية. بيرفض لو فيه عمليات معلّقة/فاشلة (علشان ما نضيّعش شغل محلي)."""
    c = counts()
    if c["pending"] or c["failed"]:
        return {"pulled": False, "reason": "فيه عمليات معلّقة أو فاشلة"}
    info = json.loads(_req("GET", "/sync/ping"))
    if not force and info.get("marker") == _state_get("marker"):
        return {"pulled": False, "reason": "محدّث"}
    raw = _req("GET", "/sync/pull", timeout=600)
    fd, path = tempfile.mkstemp(suffix=".gz", dir=APP_DIR)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
        with _lock:
            marker = apply_snapshot(path)
    finally:
        with contextlib.suppress(OSError):
            os.remove(path)
    _state_set("marker", marker)
    for ent in ("SalesInvoice", "PosSession"):
        _state_set("base:" + ent, _max_id(_entity_model(ent)))
    return {"pulled": True, "marker": marker}


def cycle():
    """دورة مزامنة كاملة. بترجّع ملخص حالة، ومبترميش استثناءات اتصال."""
    out = {"ok": False, "offline": False, "error": "", "push": None, "pull": None}
    if not (is_node() and hq_url() and sync_key()):
        out["error"] = "نسخة الفرع مش مضبوطة (ERP_NODE_ID / ERP_HQ_URL / ERP_SYNC_KEY)"
        return out
    if not _lock.acquire(blocking=False):
        out["error"] = "مزامنة شغّالة بالفعل"
        return out
    try:
        try:
            out["push"] = push()
            out["pull"] = pull()
            out["ok"] = True
            _state_set("last_ok", datetime.datetime.now().isoformat(timespec="seconds"))
            _state_set("last_error", "")
        except ConnectionError as ex:
            out["offline"] = True
            out["error"] = str(ex)[:200]
            _state_set("last_error", "offline: " + out["error"])
        except Exception as ex:      # noqa: BLE001
            out["error"] = (str(ex) or type(ex).__name__)[:300]
            _state_set("last_error", out["error"])
    finally:
        _lock.release()
    return out


def retry(op_uuid):
    from .db import SyncOp, get_session
    with get_session() as s:
        r = s.query(SyncOp).filter(SyncOp.uuid == op_uuid, SyncOp.status == "failed").first()
        if not r:
            return False
        r.status, r.error = "pending", ""
        s.commit()
        return True


def discard(op_uuid, reason):
    from .db import SyncOp, get_session
    if not (reason or "").strip():
        raise ValueError("اكتب سبب التجاهل")
    with get_session() as s:
        r = s.query(SyncOp).filter(SyncOp.uuid == op_uuid, SyncOp.status == "failed").first()
        if not r:
            return False
        r.status, r.error = "discarded", (r.error + " | تجاهل: " + reason.strip())[:400]
        s.commit()
        return True


def status():
    c = counts()
    return {"node_id": node_id(), "hq_url": hq_url(), "pending": c["pending"], "failed": c["failed"], "last_ok": _state_get("last_ok"), "last_error": _state_get("last_error")}


_bg = {"t": None}


def start_background():
    """خيط خلفي بيشغّل cycle() كل ERP_SYNC_INTERVAL ثانية (نسخة فرع فقط)."""
    if not is_node() or _bg["t"] is not None:
        return False
    interval = max(10, int(os.environ.get("ERP_SYNC_INTERVAL", "60") or 60))

    def loop():
        while True:
            try:
                cycle()
            except Exception:      # noqa: BLE001
                pass
            time.sleep(interval)
    t = threading.Thread(target=loop, daemon=True, name="erp-nodesync")
    t.start()
    _bg["t"] = t
    return True
