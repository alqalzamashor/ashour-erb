"""طلبات التوصيل الواردة (هنقرستيشن/جاهز/تو يو/أي تطبيق...) في شاشة المطبخ.
التطبيقات بتبعت الطلب لـ webhook (انظر delivery_server.py) → بيتسجّل "جديد" → الكاشير يقبله فيتفتح طلب دليفري عادي ويتبعت للمطبخ.
الربط الفعلي بكل تطبيق محتاج حساب شريك واتفاقية وشكل الـ payload بتاعهم؛ هنا شكل عام (JSON) + "خريطة حقول" لكل مصدر تقدر تعدّلها من غير كود."""
import datetime
import json
import os
import re
import secrets

from sqlalchemy.exc import IntegrityError

from . import audit
from .db import APP_DIR, DeliveryItemMap, DeliveryOrder, Product, get_session

CFG_PATH = os.path.join(APP_DIR, "delivery.json")
DEFAULTS = {"enabled": False, "host": "0.0.0.0", "port": 8600, "sources": {}}
DEFAULT_MAPPING = {"external_id": "order_id", "customer_name": "customer.name", "phone": "customer.phone", "address": "address",
                   "notes": "notes", "total": "total", "payment": "payment", "items": "items",
                   "item_sku": "sku", "item_name": "name", "item_qty": "quantity", "item_price": "price", "item_note": "note"}
STATUS = {"new": "جديد", "accepted": "اتقبل (في المطبخ)", "ready": "جاهز", "dispatched": "خرج للتوصيل", "delivered": "اتسلّم", "rejected": "مرفوض"}
NEXT = {"accepted": ("ready",), "ready": ("dispatched", "delivered"), "dispatched": ("delivered",)}
SRC_RE = re.compile(r"^[a-z0-9_-]{2,30}$")
MAX_ITEMS = 100


def get_config():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


@audit.audited_config("إعدادات طلبات التوصيل")
def save_config(**kw):
    from . import services
    services.require_action("delivery_orders", "edit")
    cfg = get_config()
    cfg.update({k: v for k, v in kw.items() if k in DEFAULTS})
    cfg["port"] = int(cfg["port"])
    if not 1024 <= cfg["port"] <= 65535:
        raise ValueError("البورت من 1024 إلى 65535")
    for k, v in cfg["sources"].items():
        if not SRC_RE.match(k):
            raise ValueError("اسم المصدر حروف إنجليزية صغيرة وأرقام و - _ فقط (2-30)")
        if len(str(v.get("secret", ""))) < 16:
            raise ValueError(f"المفتاح السري للمصدر {k} قصير (16 حرف على الأقل)")
        m = v.get("mapping") or {}
        if not isinstance(m, dict) or not all(isinstance(x, str) for x in m.values()):
            raise ValueError(f"خريطة الحقول للمصدر {k} لازم تكون JSON من نصوص")
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    try:
        os.chmod(CFG_PATH, 0o600)
    except Exception:
        pass
    return cfg


def add_source(key, label="", mapping=None):
    """يضيف مصدر ويرجّع مفتاحه السري (بيتعرض مرة واحدة للمستخدم؛ متخزّن في الإعدادات)."""
    key = (key or "").strip().lower()
    if not SRC_RE.match(key):
        raise ValueError("اسم المصدر حروف إنجليزية صغيرة وأرقام و - _ فقط (2-30)")
    cfg = get_config()
    if key in cfg["sources"]:
        raise ValueError("المصدر موجود بالفعل")
    sec = secrets.token_urlsafe(24)
    cfg["sources"][key] = {"label": label or key, "secret": sec, "mapping": mapping or {}}
    save_config(sources=cfg["sources"])
    return sec


def rotate_secret(key):
    cfg = get_config()
    if key not in cfg["sources"]:
        raise ValueError("المصدر غير موجود")
    cfg["sources"][key]["secret"] = secrets.token_urlsafe(24)
    save_config(sources=cfg["sources"])
    return cfg["sources"][key]["secret"]


def remove_source(key):
    cfg = get_config()
    cfg["sources"].pop(key, None)
    save_config(sources=cfg["sources"])


# ------------------------------------------------------------------ قراءة الـ payload
def _dig(obj, path):
    for part in str(path or "").split("."):
        if part == "":
            continue
        if isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
        if obj is None:
            return None
    return obj


def _num(v, default=0.0):
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else default
    except ValueError:
        return default


def parse_payload(payload, mapping=None):
    """يحوّل payload المصدر لشكل موحّد. بيرمي ValueError لو ناقص (رقم طلب أو أصناف)."""
    m = dict(DEFAULT_MAPPING); m.update(mapping or {})
    if not isinstance(payload, dict):
        raise ValueError("الـ payload لازم يكون JSON object")
    ext = _dig(payload, m["external_id"])
    if ext in (None, ""):
        raise ValueError(f"رقم الطلب ({m['external_id']}) مفقود")
    raw_items = _dig(payload, m["items"])
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError(f"قايمة الأصناف ({m['items']}) فاضية أو مفقودة")
    if len(raw_items) > MAX_ITEMS:
        raise ValueError("عدد الأصناف أكبر من المسموح")
    items = []
    for it in raw_items:
        qty = _num(_dig(it, m["item_qty"]), 1.0)
        name = str(_dig(it, m["item_name"]) or "").strip()
        sku = str(_dig(it, m["item_sku"]) or "").strip()
        if qty <= 0 or qty > 10000 or not (name or sku):
            raise ValueError("صنف غير صالح (كمية أو اسم/كود)")
        items.append({"sku": sku, "name": name, "quantity": qty, "price": _num(_dig(it, m["item_price"])), "note": str(_dig(it, m["item_note"]) or "")[:200]})
    pay = str(_dig(payload, m["payment"]) or "").strip().lower()
    return {"external_id": str(ext)[:80], "customer_name": str(_dig(payload, m["customer_name"]) or "")[:150],
            "phone": str(_dig(payload, m["phone"]) or "")[:40], "address": str(_dig(payload, m["address"]) or "")[:300],
            "notes": str(_dig(payload, m["notes"]) or "")[:400], "total": _num(_dig(payload, m["total"])),
            "payment": "online" if pay in ("online", "paid", "prepaid", "card") else ("cash" if pay in ("cash", "cod") else ""), "items": items}


def ingest(source, payload, mapping=None, raw=""):
    """يسجّل الطلب. بيرجّع (order_id, created). نفس (المصدر، رقم الطلب) تاني = نفس الطلب (التطبيقات بتعيد الإرسال)."""
    d = parse_payload(payload, mapping)
    with get_session() as s:
        ex = s.query(DeliveryOrder).filter(DeliveryOrder.source == source, DeliveryOrder.external_id == d["external_id"]).first()
        if ex:
            return ex.id, False
        o = DeliveryOrder(source=source, external_id=d["external_id"], customer_name=d["customer_name"], phone=d["phone"], address=d["address"],
                          notes=d["notes"], items_json=json.dumps(d["items"], ensure_ascii=False), total=d["total"], payment=d["payment"], raw=(raw or "")[:20000])
        s.add(o)
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            ex = s.query(DeliveryOrder).filter(DeliveryOrder.source == source, DeliveryOrder.external_id == d["external_id"]).first()
            return ex.id, False
        return o.id, True


def create_manual(customer_name, phone, address, items, notes="", payment="cash"):
    """طلب تليفون/يدوي: items = [{sku|name, quantity, price?}]."""
    from . import services
    services.require_action("delivery_orders", "edit")
    ext = datetime.datetime.now().strftime("%y%m%d%H%M%S") + secrets.token_hex(2)
    oid, _ = ingest("manual", {"order_id": ext, "customer": {"name": customer_name, "phone": phone}, "address": address, "notes": notes,
                               "payment": payment, "items": items})
    return oid


# ------------------------------------------------------------------ مطابقة الأصناف
def _key(it):
    return (it.get("sku") or it.get("name") or "").strip().lower()


def match_items(order_id):
    """بيرجّع أصناف الطلب مع product_id المطابق (أو None): من الخريطة المحفوظة، ثم كود/باركود، ثم الاسم المطابق بالظبط."""
    from . import services
    with get_session() as s:
        o = s.get(DeliveryOrder, int(order_id))
        if not o:
            raise ValueError("الطلب غير موجود")
        src, items = o.source, json.loads(o.items_json or "[]")
        maps = {m.key: m.product_id for m in s.query(DeliveryItemMap).filter(DeliveryItemMap.source == src).all()}
    out = []
    for it in items:
        k = _key(it); pid = maps.get(k)
        if not pid and it.get("sku"):
            r = services.find_product_by_code(it["sku"])
            pid = r[0].id if r else None
        if not pid and it.get("name"):
            with get_session() as s:
                hit = s.query(Product).filter(Product.name == it["name"], Product.is_active.is_(True), Product.can_be_sold.is_(True)).all()
                pid = hit[0].id if len(hit) == 1 else None
        out.append(dict(it, product_id=pid))
    return out


def map_item(source, key, product_id):
    from . import services
    services.require_action("delivery_orders", "edit")
    key = (key or "").strip().lower()
    with get_session() as s:
        if not s.get(Product, int(product_id)):
            raise ValueError("الصنف غير موجود")
        m = s.query(DeliveryItemMap).filter(DeliveryItemMap.source == source, DeliveryItemMap.key == key).first()
        if m:
            m.product_id = int(product_id)
        else:
            s.add(DeliveryItemMap(source=source, key=key, product_id=int(product_id)))
        s.commit()


# ------------------------------------------------------------------ دورة حياة الطلب
def _touch(o, status):
    o.status = status; o.updated_at = datetime.datetime.now()


def accept(order_id, terminal_id, overrides=None):
    """يقبل الطلب: يطابق الأصناف (overrides = {index: product_id} للغير مطابق وبيتحفظ في الخريطة)، يفتح طلب دليفري على جلسة الماكينة، يضيف الأصناف ويبعته للمطبخ.
    لو أي خطوة فشلت الطلب الداخلي بيتلغي والطلب يفضل "جديد". بيرجّع {restaurant_order_id, number, send_result, price_diff}."""
    from . import services
    services.require_action("delivery_orders", "edit")
    with get_session() as s:
        o = s.get(DeliveryOrder, int(order_id))
        if not o:
            raise ValueError("الطلب غير موجود")
        if o.status != "new":
            raise ValueError("الطلب ده اتعالج قبل كده")
        src, ext, name, phone, addr, notes, total, pay = o.source, o.external_id, o.customer_name, o.phone, o.address, o.notes, o.total, o.payment
    items = match_items(order_id)
    for idx, pid in (overrides or {}).items():
        idx = int(idx)
        if 0 <= idx < len(items) and pid:
            map_item(src, _key(items[idx]), int(pid)); items[idx]["product_id"] = int(pid)
    missing = [i.get("name") or i.get("sku") for i in items if not i["product_id"]]
    if missing:
        raise ValueError("أصناف غير مربوطة بأصناف عندك: " + "، ".join(missing))
    rid = services.open_restaurant_order(order_type="delivery", customer_name=name or f"{src} #{ext}", customer_phone=phone or "-",
                                         delivery_address=addr or "-", terminal_id=terminal_id)
    try:
        for it in items:
            services.add_restaurant_order_item(rid, it["product_id"], it["quantity"], note=it.get("note", ""))
        with get_session() as s:
            r = s.get(services.RestaurantOrder, rid)
            r.notes = f"طلب {src} #{ext}" + (f" - إجمالي التطبيق {total:g}" if total else "") + (" - مدفوع أونلاين" if pay == "online" else (" - تحصيل نقدي عند التسليم" if pay == "cash" else "")) + (f" - {notes}" if notes else "")
            s.commit(); number = r.number
        send = services.send_order_to_kitchen(rid)
    except Exception:
        try:
            services.void_restaurant_order(rid, reason="فشل قبول طلب توصيل")
        except Exception:
            pass
        raise
    ours = 0.0
    with get_session() as s:
        for it in items:
            p = s.get(Product, it["product_id"]); ours += float(p.sale_price or 0) * (1 + float(p.tax_rate or 0) / 100.0) * it["quantity"]
        o = s.get(DeliveryOrder, int(order_id))
        o.restaurant_order_id = rid; _touch(o, "accepted"); s.commit()
    diff = round(total - ours, 2) if total else 0.0
    return {"restaurant_order_id": rid, "number": number, "send_result": send, "price_diff": diff}


def reject(order_id, reason=""):
    from . import services
    services.require_action("delivery_orders", "edit")
    with get_session() as s:
        o = s.get(DeliveryOrder, int(order_id))
        if not o or o.status != "new":
            raise ValueError("الطلب مش جديد")
        o.reject_reason = (reason or "")[:200]; _touch(o, "rejected"); s.commit()


def set_status(order_id, status):
    from . import services
    services.require_action("delivery_orders", "edit")
    with get_session() as s:
        o = s.get(DeliveryOrder, int(order_id))
        if not o:
            raise ValueError("الطلب غير موجود")
        if status not in NEXT.get(o.status, ()):
            raise ValueError(f"مينفعش النقل من «{STATUS.get(o.status)}» إلى «{STATUS.get(status, status)}»")
        _touch(o, status); s.commit()


def count_new():
    with get_session() as s:
        return s.query(DeliveryOrder).filter(DeliveryOrder.status == "new").count()


def list_orders(status=None, limit=300):
    with get_session() as s:
        q = s.query(DeliveryOrder)
        if status:
            q = q.filter(DeliveryOrder.status == status)
        rows = q.order_by(DeliveryOrder.id.desc()).limit(limit).all()
        out = []
        for o in rows:
            d = {c.name: getattr(o, c.name) for c in DeliveryOrder.__table__.columns if c.name != "raw"}
            d["items"] = json.loads(o.items_json or "[]")
            out.append(d)
        return out
