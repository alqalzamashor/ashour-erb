"""كاشير بدون اتصال: لو قاعدة البيانات/السيرفر وقع أثناء البيع، البيع النقدي بيتخزّن على جهاز الكاشير ويتزامن لما الاتصال يرجع.

إزاي بيشتغل:
- كل ما شاشة الكاشير تتفتح (وكل 10 دقايق) بتتحفظ نسخة محلية (snapshot) من الأصناف/الباركودات/الأسعار/طرق الدفع/بيانات الماكينة.
- لو create_pos_sale فشل بخطأ اتصال → البيع بيتحفظ كملف JSON في مجلد offline/queue (برقم مؤقت OFF-...) وبيتطبع إيصال مؤقت.
- كل بيع له client_uuid؛ المزامنة بتبعته create_pos_sale بنفس الـ uuid وبتاريخ البيع الأصلي، والسيرفر بيرفض التكرار (حتى لو الرد ضاع).
- بيع فشل لسبب إداري (جلسة اتقفلت، مخزون ناقص...) بيتعلّم "فشل" ومحتاج مراجعة بإيدك (إعادة محاولة أو تجاهل بسبب).

حدود مهمة: الدفع النقدي فقط، من غير ولاء/كوبونات/عميل آجل/إيصال بـ QR زكاة (الفاتورة الضريبية الرسمية بتتولّد عند المزامنة)،
والسيرفر لازم يكون الحاجة اللي وقعت؛ لو الكمبيوتر نفسه (جهاز الكاشير) مات قبل المزامنة الملفات المحلية بتفضل موجودة."""
import datetime
import glob
import json
import os
import threading
import uuid

from .db import APP_DIR

DIR = os.path.join(APP_DIR, "offline")
QUEUE = os.path.join(DIR, "queue")
DONE = os.path.join(DIR, "synced")
SNAP = os.path.join(DIR, "snapshot.json")
_lock = threading.RLock()
SNAPSHOT_MAX_AGE_H = 48


def _ensure():
    os.makedirs(QUEUE, exist_ok=True); os.makedirs(DONE, exist_ok=True)


def is_db_error(ex):
    """خطأ اتصال بقاعدة البيانات/الشبكة (مش خطأ منطق أعمال)."""
    try:
        from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
        if isinstance(ex, (OperationalError, InterfaceError)):
            return True
        if isinstance(ex, DBAPIError) and getattr(ex, "connection_invalidated", False):
            return True
    except Exception:
        pass
    return isinstance(ex, (ConnectionError, TimeoutError)) or type(ex).__name__ in ("OperationalError", "InterfaceError")


class OfflineProduct:
    """شبه الصنف للاستخدام في السلة بدون قاعدة بيانات."""
    def __init__(self, d):
        self.id = d["id"]; self.sku = d["sku"]; self.name = d["name"]; self.sale_price = float(d["sale_price"]); self.tax_rate = float(d["tax_rate"])
        self.unit = d.get("unit", "قطعة"); self.image_path = None; self.can_be_sold = True; self.product_type = d.get("product_type", "simple")


# ------------------------------------------------------------------ النسخة المحلية
def save_snapshot(terminal=None):
    """بيحفظ الأصناف وطرق الدفع للاستخدام بدون اتصال. بيتنادى والاتصال شغال. بيرجّع عدد الأصناف."""
    from . import services
    _ensure()
    prods = []
    for p in services.list_products():
        if not p.can_be_sold:
            continue
        prods.append({"id": p.id, "sku": p.sku, "name": p.name, "sale_price": float(p.sale_price or 0), "tax_rate": float(p.tax_rate if p.tax_rate is not None else 15),
                      "unit": p.unit or "", "product_type": p.product_type, "barcodes": []})
    by = {p["id"]: p for p in prods}
    from .db import ProductUnitLine, get_session
    with get_session() as s:
        for ln in s.query(ProductUnitLine).filter(ProductUnitLine.barcode != "").all():
            if ln.product_id in by:
                by[ln.product_id]["barcodes"].append({"code": ln.barcode, "factor": float(ln.factor_to_base or 1)})
    pms = [{"id": m.id, "name": m.name, "is_cash": bool(services.pm_is_cash(m))} for m in services.list_payment_methods(active_only=True)]
    snap = {"at": datetime.datetime.now().isoformat(timespec="seconds"), "products": prods, "payment_methods": pms,
            "terminal": {k: terminal.get(k) for k in ("id", "code", "name", "default_customer_id", "default_payment_method_id")} if terminal else None}
    tmp = f"{SNAP}.{os.getpid()}.{threading.get_ident()}.tmp"      # اسم مؤقت فريد: أكتر من خيط بيحفظوا مع بعض من غير ما يدوسوا على بعض
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False)
    os.replace(tmp, SNAP)
    return len(prods)


def load_snapshot():
    try:
        with open(SNAP, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def snapshot_age_hours():
    s = load_snapshot()
    if not s:
        return None
    return (datetime.datetime.now() - datetime.datetime.fromisoformat(s["at"])).total_seconds() / 3600.0


def find(code):
    """مسح باركود/كود من النسخة المحلية → {'product','qty','info'} أو None. بيدعم الباركود الموزون."""
    snap = load_snapshot()
    code = (code or "").strip()
    if not snap or not code:
        return None
    from . import scale_barcode
    prods = snap["products"]

    def by_code(c):
        cl = c.lower()
        for p in prods:
            if any(b["code"] == c for b in p["barcodes"]) or p["sku"].lower() == cl:
                return p
        return None
    sc = scale_barcode.parse(code)
    if sc:
        p = by_code(sc["plu"]) or by_code(sc["plu"].lstrip("0") or "0")
        if p:
            if sc["kind"] == "weight":
                q = round(sc["value"], 3); return {"product": OfflineProduct(p), "qty": q, "info": f"{q:g} كجم"}
            unit = p["sale_price"] * (1 + p["tax_rate"] / 100.0)
            if unit > 0:
                q = round(sc["value"] / unit, 3); return {"product": OfflineProduct(p), "qty": q, "info": f"{sc['value']:g} ر.س"}
    p = by_code(code)
    if p:
        fac = next((b["factor"] for b in p["barcodes"] if b["code"] == code), 1.0)
        return {"product": OfflineProduct(p), "qty": fac, "info": ""}
    return None


def search(text, limit=60):
    snap = load_snapshot()
    if not snap:
        return []
    n = (text or "").strip().lower()
    out = [OfflineProduct(p) for p in snap["products"] if not n or n in p["name"].lower() or n in p["sku"].lower() or any(n in b["code"] for b in p["barcodes"])]
    return out[:limit]


def cash_method_ids():
    snap = load_snapshot() or {}
    return {m["id"] for m in snap.get("payment_methods", []) if m["is_cash"]}


# ------------------------------------------------------------------ الطابور
def _path(name):
    return os.path.join(QUEUE, name)


def _next_number():
    day = datetime.date.today().strftime("%y%m%d")
    n = len(glob.glob(os.path.join(QUEUE, f"*OFF-{day}-*.json"))) + len(glob.glob(os.path.join(DONE, f"*OFF-{day}-*.json"))) + 1
    return f"OFF-{day}-{n:03d}"


def queue_sale(customer_id, items, payment_method_id, terminal_id, tendered=None, client_uuid=None):
    """يخزّن بيع نقدي محلي. items = [{product_id, quantity, unit_price, tax_rate}]. بيرجّع {uuid, number, total, subtotal, tax, at}."""
    if payment_method_id is None or int(payment_method_id) not in cash_method_ids():
        raise ValueError("في وضع عدم الاتصال الدفع النقدي فقط - اختار طريقة الدفع النقدي")
    if not items:
        raise ValueError("السلة فاضية")
    snap = load_snapshot()
    age = snapshot_age_hours()
    if snap is None or (age is not None and age > SNAPSHOT_MAX_AGE_H):
        raise ValueError("النسخة المحلية للأصناف قديمة جدًا - مينفعش البيع بدون اتصال")
    sub = tax = 0.0
    for it in items:
        line = float(it["quantity"]) * float(it["unit_price"])
        sub += line; tax += line * float(it.get("tax_rate", 15)) / 100.0
    rec = {"uuid": client_uuid or uuid.uuid4().hex, "number": None, "at": datetime.datetime.now().isoformat(timespec="seconds"), "status": "pending", "error": "", "attempts": 0,
           "customer_id": int(customer_id), "items": items, "payment_method_id": int(payment_method_id), "terminal_id": int(terminal_id) if terminal_id else None,
           "subtotal": round(sub, 2), "tax": round(tax, 2), "total": round(sub + tax, 2), "tendered": tendered}
    with _lock:
        _ensure()
        rec["number"] = _next_number()
        name = f"{rec['at'].replace(':', '').replace('-', '').replace('T', '')}_{rec['number']}_{rec['uuid'][:6]}.json"
        tmp = _path(name) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False)
        os.replace(tmp, _path(name))
    return rec


def _read_all():
    out = []
    for fp in sorted(glob.glob(os.path.join(QUEUE, "*.json"))):
        try:
            with open(fp, encoding="utf-8") as f:
                r = json.load(f)
            r["_file"] = fp; out.append(r)
        except Exception:
            continue
    return out


def pending():
    return [r for r in _read_all() if r["status"] == "pending"]


def failed():
    return [r for r in _read_all() if r["status"] == "failed"]


def counts():
    a = _read_all()
    return {"pending": sum(1 for r in a if r["status"] == "pending"), "failed": sum(1 for r in a if r["status"] == "failed")}


def _write(r):
    fp = r.pop("_file")
    tmp = fp + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False)
    os.replace(tmp, fp)
    r["_file"] = fp


def sync(services=None):
    """يزامن البيع المعلّق بالترتيب. بيرجّع {'synced','failed','offline'(بقى فيه اتصال مفقود)}. بيوقف عند أول خطأ اتصال."""
    if services is None:
        from . import services as services
    out = {"synced": 0, "failed": 0, "offline": False, "invoices": []}
    if not _lock.acquire(blocking=False):
        return out
    try:
        for r in pending():
            r["attempts"] = int(r.get("attempts", 0)) + 1
            try:
                pm = [{"payment_method_id": r["payment_method_id"], "amount": None, "tendered": r.get("tendered")}] if r.get("tendered") else None
                res = services.create_pos_sale(customer_id=r["customer_id"], items=r["items"], payment_method_id=None if pm else r["payment_method_id"], payments=pm,
                                               terminal_id=r["terminal_id"], client_uuid=r["uuid"], sale_time=datetime.datetime.fromisoformat(r["at"]))
            except Exception as ex:      # noqa: BLE001
                if is_db_error(ex):
                    out["offline"] = True; _write(r); break
                r["status"] = "failed"; r["error"] = str(ex)[:300]; _write(r); out["failed"] += 1
                continue
            r["status"] = "synced"; r["invoice_id"] = res["invoice_id"]
            _write(r)
            os.replace(r["_file"], os.path.join(DONE, os.path.basename(r["_file"])))
            out["synced"] += 1; out["invoices"].append(res["invoice_id"])
    finally:
        _lock.release()
    return out


def retry(uuid_):
    with _lock:
        for r in failed():
            if r["uuid"] == uuid_:
                r["status"] = "pending"; r["error"] = ""; _write(r); return True
    return False


def discard(uuid_, reason):
    """تجاهل بيع فاشل بعد مراجعته (مثلًا اتسجّل يدويًا): بيتنقل لمجلد synced بحالة discarded وسبب."""
    if not (reason or "").strip():
        raise ValueError("اكتب سبب التجاهل")
    with _lock:
        for r in failed():
            if r["uuid"] == uuid_:
                r["status"] = "discarded"; r["error"] = (r["error"] + " | تجاهل: " + reason.strip())[:400]; _write(r)
                os.replace(r["_file"], os.path.join(DONE, os.path.basename(r["_file"]))); return True
    return False


def purge_old(days=60):
    cutoff = datetime.datetime.now().timestamp() - days * 86400
    for fp in glob.glob(os.path.join(DONE, "*.json")):
        try:
            if os.path.getmtime(fp) < cutoff:
                os.remove(fp)
        except OSError:
            pass
