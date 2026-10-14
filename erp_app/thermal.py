"""الطباعة الحرارية المباشرة (ESC/POS): إيصال الكاشير + تذكرة المطبخ + إلغاء صنف.

الفكرة: بنرسم الإيصال كصورة (PIL) بخط عربي مشكّل، وبنبعتها للطابعة كـ raster (GS v 0)،
عشان العربي يطلع صح على أي طابعة حرارية حتى لو ما بتدعمش الكود بيج العربي.
طابعتين مستقلتين: «receipt» (الكاشير) و «kitchen» (المطبخ). كل واحدة ليها طريقة اتصال:
  network = IP:9100 (الأشهر) | system = اسم طابعة مثبتة على الجهاز (ويندوز/CUPS) | file = جهاز/ملف (COM/USB lp/اختبار).
"""
import datetime
import io
import json
import os
import socket
import subprocess
import sys
import tempfile

from . import audit
from .db import APP_DIR

CONFIG_PATH = os.path.join(APP_DIR, "printers.json")
STATIONS = {"receipt": "طابعة الكاشير (الإيصال)", "kitchen": "طابعة المطبخ"}
MODES = {"off": "غير مفعّلة (PDF فقط)", "network": "شبكة (IP)", "system": "طابعة مثبتة على الجهاز", "file": "منفذ / ملف", "agent": "وكيل طباعة على جهاز الكاشير (للسيرفر البعيد)"}
DEFAULT_STATION = {"mode": "off", "address": "", "port": 9100, "width": 80, "copies": 1, "cut": True, "drawer": False, "auto": True, "font_px": 24}

FONT_REG = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf", "/Library/Fonts/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"]
FONT_BOLD = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/tahomabd.ttf", "C:/Windows/Fonts/arialbd.ttf",
             "C:/Windows/Fonts/segoeuib.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]


# ------------------------------------------------------------------ الإعدادات
def get_config():
    cfg = {k: dict(DEFAULT_STATION) for k in STATIONS}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        for k in STATIONS:
            cfg[k].update(saved.get(k, {}))
    except Exception:
        pass
    return cfg


@audit.audited_config("إعدادات الطابعات الحرارية")
def save_config(station, **kw):
    if station not in STATIONS:
        raise ValueError("طابعة غير معروفة")
    cfg = get_config()
    st = cfg[station]
    if "mode" in kw and kw["mode"] not in MODES:
        raise ValueError("طريقة اتصال غير معروفة")
    for k, v in kw.items():
        if k in DEFAULT_STATION:
            st[k] = v
    st["width"] = 58 if int(st["width"]) == 58 else 80
    st["port"] = int(st["port"] or 9100)
    st["copies"] = max(1, min(5, int(st["copies"] or 1)))
    st["font_px"] = max(18, min(34, int(st["font_px"] or 24)))
    if st["mode"] in ("network", "system", "file") and not str(st["address"]).strip():
        raise ValueError("اكتب عنوان الطابعة (IP أو اسمها أو المنفذ)")
    st["address"] = str(st["address"]).strip()
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg


TOKEN_PATH = os.path.join(APP_DIR, "print_agent_token.txt")
MAX_ATTEMPTS = 3
STALE_SECS = 120


def agent_token(create=True):
    """المفتاح السري اللي وكيل الطباعة بيستخدمه. بيتولّد تلقائي أول مرة."""
    try:
        with open(TOKEN_PATH, encoding="utf-8") as f:
            t = f.read().strip()
            if t:
                return t
    except OSError:
        pass
    return rotate_agent_token() if create else ""


def rotate_agent_token():
    import secrets
    t = secrets.token_urlsafe(24)
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    fd = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(t)
    return t


def enqueue_job(station, data):
    from .db import PrintJob, get_session
    s = get_session()
    try:
        j = PrintJob(station=station, data=bytes(data))
        s.add(j); s.commit()
        return j.id
    finally:
        s.close()


def claim_jobs(station=None, limit=10):
    """للوكيل: بيرجّع أوامر الطباعة المستنية (ويعتبرها اتبعتت). الأوامر اللي اتبعتت ومارجعش ردها خلال دقيقتين بتترجّع للطابور (لحد 3 محاولات)."""
    import datetime
    from .db import PrintJob, get_session
    s = get_session()
    try:
        now = datetime.datetime.now()
        stale = now - datetime.timedelta(seconds=STALE_SECS)
        for j in s.query(PrintJob).filter(PrintJob.status == "sent", PrintJob.updated_at < stale).all():
            j.status, j.updated_at = ("pending" if j.attempts < MAX_ATTEMPTS else "failed"), now
            if j.status == "failed":
                j.error = "الوكيل ماردّش"
        q = s.query(PrintJob).filter(PrintJob.status == "pending")
        if station:
            q = q.filter(PrintJob.station == station)
        out = []
        for j in q.order_by(PrintJob.id).limit(limit).all():
            j.status, j.attempts, j.updated_at = "sent", (j.attempts or 0) + 1, now
            out.append({"id": j.id, "station": j.station, "data": j.data})
        s.commit()
        return out
    finally:
        s.close()


def finish_job(job_id, ok, error=""):
    import datetime
    from .db import PrintJob, get_session
    s = get_session()
    try:
        j = s.get(PrintJob, int(job_id))
        if j is None:
            return False
        j.status = "done" if ok else ("pending" if (j.attempts or 0) < MAX_ATTEMPTS else "failed")
        j.error = "" if ok else str(error)[:300]
        j.updated_at = datetime.datetime.now()
        s.commit()
        return True
    finally:
        s.close()


def purge_jobs(days=7):
    import datetime
    from .db import PrintJob, get_session
    s = get_session()
    try:
        n = s.query(PrintJob).filter(PrintJob.created_at < datetime.datetime.now() - datetime.timedelta(days=days)).delete()
        s.commit()
        return n
    finally:
        s.close()


def pending_count():
    from .db import PrintJob, get_session
    s = get_session()
    try:
        return s.query(PrintJob).filter(PrintJob.status.in_(("pending", "sent"))).count()
    finally:
        s.close()


def is_enabled(station):
    return get_config()[station]["mode"] != "off"


def list_system_printers():
    """أسماء الطابعات المثبتة على الجهاز (للاختيار منها)."""
    names = []
    try:
        if sys.platform.startswith("win"):
            import win32print
            names = [p[2] for p in win32print.EnumPrinters(2 | 4)]
        else:
            out = subprocess.run(["lpstat", "-e"], capture_output=True, text=True, timeout=5).stdout
            names = [x.strip() for x in out.splitlines() if x.strip()]
    except Exception:
        pass
    return names


# ------------------------------------------------------------------ الرسم
def _font(bold, size):
    from PIL import ImageFont
    for f in (FONT_BOLD if bold else FONT_REG):
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, size, layout_engine=ImageFont.Layout.BASIC)   # BASIC: بدون raqm، لأن النص متشكّل ومترتّب بصريًا بالفعل
            except Exception:
                pass
    return ImageFont.load_default()


def _shape(t):
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(str(t)))
    except Exception:
        return str(t)


def _wrap(text, font, max_w):
    """تقسيم نص منطقي لأسطر (قبل التشكيل) بحيث كل سطر يتشكّل ويتقاس بعرضه الفعلي."""
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if font.getlength(_shape(trial)) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


class Doc:
    """مستند إيصال: قايمة عمليات بترسم بعدين لصورة 1-bit."""

    def __init__(self, width_mm=80, font_px=24):
        self.px = 384 if int(width_mm) == 58 else 576
        self.fs = int(font_px)
        self.ops = []

    def title(self, t): self.ops.append(("text", t, "c", 1.6, True)); return self
    def big(self, t, bold=True, align="c"): self.ops.append(("text", t, align, 1.35, bold)); return self
    def text(self, t, align="r", bold=False, scale=1.0): self.ops.append(("text", t, align, scale, bold)); return self
    def kv(self, label, value, bold=False, scale=1.0): self.ops.append(("kv", label, value, bold, scale)); return self
    def sep(self, ch="-"): self.ops.append(("sep", ch)); return self
    def space(self, n=1): self.ops.append(("space", n)); return self
    def item(self, name, qty_price, total): self.ops.append(("item", name, qty_price, total)); return self
    def qr(self, data): self.ops.append(("qr", data)); return self
    def image(self, path): self.ops.append(("img", path)); return self

    def render(self):
        from PIL import Image, ImageDraw
        W, pad = self.px, 6
        inner = W - 2 * pad
        draws = []   # (kind, payload...) بعد القياس

        def f(scale, bold): return _font(bold, int(self.fs * scale))

        y = 6
        items = []
        for op in self.ops:
            k = op[0]
            if k == "text":
                _, t, al, sc, bold = op
                fo = f(sc, bold)
                for ln in _wrap(t, fo, inner):
                    h = int(fo.size * 1.35)
                    items.append(("t", y, _shape(ln), al, fo)); y += h
            elif k == "kv":
                _, lab, val, bold, sc = op
                fo = f(sc, bold)
                sl, sv = _shape(lab), _shape(val)
                if fo.getlength(sl) + fo.getlength(sv) + 14 <= inner:
                    items.append(("kv", y, sl, sv, fo)); y += int(fo.size * 1.35)
                else:           # ما اتسعش: التسمية فوق والقيمة تحتها
                    for ln in _wrap(lab, fo, inner):
                        items.append(("t", y, _shape(ln), "r", fo)); y += int(fo.size * 1.35)
                    for ln in _wrap(val, fo, inner):
                        items.append(("t", y, _shape(ln), "l", fo)); y += int(fo.size * 1.35)
            elif k == "item":
                _, name, qp, total = op
                fo, fb = f(1.0, False), f(1.0, True)
                for ln in _wrap(name, fb, inner):
                    items.append(("t", y, _shape(ln), "r", fb)); y += int(fb.size * 1.35)
                items.append(("kv", y, _shape(qp), _shape(total), fo)); y += int(fo.size * 1.4)
                # kv: التسمية يمين والقيمة شمال -> نعكس: الكمية×السعر يمين، الإجمالي شمال
            elif k == "sep":
                items.append(("sep", y, op[1])); y += int(self.fs * 0.9)
            elif k == "space":
                y += int(self.fs * 0.8 * op[1])
            elif k == "qr":
                try:
                    import qrcode
                    q = qrcode.QRCode(box_size=4, border=1); q.add_data(op[1]); q.make(fit=True)
                    im = q.make_image(fill_color="black", back_color="white").convert("L")
                    size = min(W - 80, 260); im = im.resize((size, size))
                    items.append(("img", y, im)); y += size + 8
                except Exception:
                    pass
            elif k == "img":
                try:
                    im = Image.open(op[1]).convert("L"); r = min(1.0, 220 / im.width, 110 / im.height)
                    im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))))
                    items.append(("img", y, im)); y += im.height + 8
                except Exception:
                    pass
        H = y + 10
        img = Image.new("L", (W, H), 255)
        d = ImageDraw.Draw(img)
        for it in items:
            k = it[0]
            if k == "t":
                _, yy, s, al, fo = it
                w = fo.getlength(s)
                x = W - pad - w if al == "r" else (pad if al == "l" else (W - w) / 2)
                d.text((x, yy), s, font=fo, fill=0)
            elif k == "kv":
                _, yy, sl, sv, fo = it
                d.text((W - pad - fo.getlength(sl), yy), sl, font=fo, fill=0)
                d.text((pad, yy), sv, font=fo, fill=0)
            elif k == "sep":
                _, yy, ch = it
                yc = yy + int(self.fs * 0.4)
                if ch == "=":
                    d.line((pad, yc - 2, W - pad, yc - 2), fill=0, width=2); d.line((pad, yc + 2, W - pad, yc + 2), fill=0, width=2)
                else:
                    for x in range(pad, W - pad, 10):
                        d.line((x, yc, x + 5, yc), fill=0, width=2)
            elif k == "img":
                _, yy, im = it
                img.paste(im, ((W - im.width) // 2, yy))
        return img.convert("1")


# ------------------------------------------------------------------ ESC/POS
def to_escpos(img, cut=True, drawer=False, copies=1):
    w, h = img.size
    wb = (w + 7) // 8
    raw = img.tobytes()          # mode "1": 1=أبيض، لازم نعكس (ESC/POS: 1=نقطة سودا)
    raw = bytes(b ^ 0xFF for b in raw)
    out = bytearray(b"\x1b@")
    if drawer:
        out += b"\x1bp\x00\x19\xfa"
    for _ in range(copies):
        for y0 in range(0, h, 255):
            rows = min(255, h - y0)
            out += b"\x1dv0\x00" + bytes([wb & 255, wb >> 8, rows & 255, rows >> 8]) + raw[y0 * wb:(y0 + rows) * wb]
        out += b"\n\n\n"
        out += b"\x1dVB\x03" if cut else b"\n\n"
    return bytes(out)


# ------------------------------------------------------------------ الإرسال
def _send(cfg, data):
    mode, addr = cfg["mode"], cfg["address"]
    if mode == "network":
        with socket.create_connection((addr, int(cfg["port"])), timeout=5) as s:
            s.sendall(data)
    elif mode == "file":
        with open(addr, "ab" if addr.startswith(("/dev/", "COM", "\\\\")) else "wb") as f:
            f.write(data)
    elif mode == "system":
        if sys.platform.startswith("win"):
            try:
                import win32print
                h = win32print.OpenPrinter(addr)
                try:
                    win32print.StartDocPrinter(h, 1, ("ERP", None, "RAW")); win32print.StartPagePrinter(h)
                    win32print.WritePrinter(h, data); win32print.EndPagePrinter(h); win32print.EndDocPrinter(h)
                finally:
                    win32print.ClosePrinter(h)
            except ImportError:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tf:
                    tf.write(data)
                try:
                    r = subprocess.run(["cmd", "/c", "copy", "/b", tf.name, f"\\\\localhost\\{addr}"], capture_output=True, text=True, timeout=15)
                    if r.returncode != 0:
                        raise RuntimeError("تعذر الإرسال للطابعة. ثبّت pywin32 (pip install pywin32) أو شارك الطابعة باسمها: " + (r.stdout or r.stderr)[:120])
                finally:
                    os.remove(tf.name)
        else:
            r = subprocess.run(["lp", "-d", addr, "-o", "raw"], input=data, capture_output=True, timeout=15)
            if r.returncode != 0:
                raise RuntimeError("فشل الإرسال للطابعة: " + r.stderr.decode(errors="ignore")[:120])
    else:
        raise RuntimeError("الطابعة غير مفعّلة")


def print_doc(station, doc):
    """يطبع Doc على طابعة المحطة. بيرجّع (ok, message). مش بيرمي استثناء."""
    cfg = get_config()[station]
    if cfg["mode"] == "off":
        return False, "الطابعة الحرارية غير مفعّلة"
    try:
        data = to_escpos(doc.render(), cut=cfg["cut"], drawer=cfg["drawer"] and station == "receipt", copies=cfg["copies"])
        if cfg["mode"] == "agent":
            enqueue_job(station, data)
            return True, "اتبعتت لوكيل الطباعة"
        _send(cfg, data)
        return True, "تمت الطباعة"
    except Exception as ex:
        return False, f"تعذرت الطباعة على {STATIONS[station]}: {ex}"


# ------------------------------------------------------------------ المستندات
def _mk(station):
    c = get_config()[station]
    return Doc(c["width"], c["font_px"])


def _company():
    from . import services
    return services.get_company_settings()


def receipt_doc(invoice_id, reprint=False):
    from . import services, zatca
    inv = services.get_sales_invoice(invoice_id)
    if not inv:
        raise ValueError("الفاتورة غير موجودة")
    co = _company()
    d = _mk("receipt")
    if getattr(co, "print_show_logo", True) and co.logo_path and os.path.exists(co.logo_path):
        d.image(co.logo_path)
    d.title(co.name or "")
    if co.address: d.text(co.address, "c")
    if co.phone: d.text(f"هاتف: {co.phone}", "c")
    if co.vat_number: d.text(f"الرقم الضريبي: {co.vat_number}", "c")
    d.space().big("فاتورة ضريبية مبسطة" + (" (نسخة)" if reprint else ""), True).sep("=")
    d.kv("رقم الفاتورة", inv.number, True)
    d.kv("التاريخ", f"{inv.date:%Y-%m-%d %H:%M}")
    if inv.customer and inv.customer.name:
        d.kv("العميل", inv.customer.name)
    if inv.payment_method:
        d.kv("الدفع", {"cash": "نقدي", "card": "شبكة", "transfer": "تحويل"}.get(inv.payment_method, inv.payment_method))
    if inv.notes and inv.notes.strip().upper() != "POS":
        d.text(inv.notes, "r")
    d.sep()
    for it in inv.items:
        nm = it.product.name if it.product else ""
        d.item(nm, f"{it.quantity:g} × {it.unit_price:,.2f}", f"{it.line_total:,.2f}")
    d.sep()
    d.kv("المجموع قبل الضريبة", f"{(inv.subtotal or 0) - (inv.discount or 0):,.2f}")
    if inv.discount:
        d.kv("الخصم", f"{inv.discount:,.2f}")
    if getattr(inv, "promo_discount", 0):
        d.kv("خصم مُطبّق (شامل الضريبة)" + (f" - {inv.promo_code}" if inv.promo_code else ""), f"{inv.promo_discount:,.2f}")
    d.kv("ضريبة القيمة المضافة", f"{inv.tax_total or 0:,.2f}")
    d.sep("=").kv("الإجمالي", f"{inv.total:,.2f} ر.س", True, 1.35).sep("=")
    try:
        from . import loyalty as _loy
        ls = _loy.invoice_summary(invoice_id)
        if ls:
            if ls["redeemed"]:
                d.kv("نقاط مستبدلة", f"{ls['redeemed']:,.0f}")
            d.kv("نقاط مكتسبة", f"{ls['earned']:,.0f}")
            d.kv("رصيد النقاط", f"{ls['balance']:,.0f}")
    except Exception:
        pass
    if getattr(co, "print_show_qr", True) and co.vat_number:
        try:
            from . import zatca_p2
            payload = zatca_p2.qr_text_for_invoice(inv.id) or zatca.build_zatca_base64(co.name or "", co.vat_number, inv.date.isoformat(), f"{inv.total:.2f}", f"{inv.tax_total or 0:.2f}")
            d.space().qr(payload)
        except Exception:
            pass
    foot = ""
    try:
        if inv.pos_terminal_id:
            from .db import PosTerminal
            with services.get_session() as s:
                t = s.get(PosTerminal, inv.pos_terminal_id)
                foot = (t.receipt_footer if t else "") or ""
    except Exception:
        pass
    foot = foot or getattr(co, "print_footer_note", "") or "شكراً لزيارتكم"
    d.space().text(foot, "c")
    return d


def kitchen_doc(res):
    """res = نتيجة send_order_to_kitchen أو void_sent_order_item (فيها cancel=True)."""
    d = _mk("kitchen")
    otype = {"dine_in": "محلي", "takeaway": "تيك أواي", "delivery": "دليفري"}.get(res.get("order_type", "dine_in"), "")
    where = f"طاولة {res['table_number']}" if res.get("table_number") else otype
    if res.get("cancel"):
        d.title("*** إلغاء ***").big(where).sep("=")
    else:
        d.title(where).big(f"{otype}" if res.get("table_number") else "", False).sep("=")
    d.kv("طلب", str(res.get("order_number", "")), True)
    sent = res.get("sent_at") or datetime.datetime.now()
    d.kv("الوقت", f"{sent:%H:%M:%S}")
    if res.get("customer_info"):
        d.text(res["customer_info"], "r")
    d.sep()
    for it in res["items"]:
        d.big(f"{it['quantity']:g} × {it['name']}", True, "r")
        if it.get("note"):
            d.text(f"   ملاحظة: {it['note']}", "r")
    if res.get("cancel") and res.get("reason"):
        d.sep().text(f"السبب: {res['reason']}", "r", True)
    d.sep("=")
    return d


def test_doc(station):
    d = _mk(station)
    d.title("اختبار الطباعة").big(STATIONS[station]).sep("=")
    d.kv("الوقت", f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    d.kv("العرض", f"{get_config()[station]['width']} مم")
    d.sep().text("أبجد هوز حطي كلمن 1234567890", "r").text("Thermal printer test OK", "c").sep("=")
    return d


# ------------------------------------------------------------------ واجهات مختصرة
def print_receipt(invoice_id, reprint=False):
    if not is_enabled("receipt"):
        return False, "الطابعة الحرارية غير مفعّلة"
    try:
        return print_doc("receipt", receipt_doc(invoice_id, reprint))
    except Exception as ex:
        return False, f"تعذر تجهيز الإيصال: {ex}"


def print_kitchen(res):
    if not is_enabled("kitchen"):
        return False, "طابعة المطبخ غير مفعّلة"
    try:
        return print_doc("kitchen", kitchen_doc(res))
    except Exception as ex:
        return False, f"تعذر تجهيز التذكرة: {ex}"


def print_test(station):
    return print_doc(station, test_doc(station))


def preview_png(doc, path):
    doc.render().convert("L").save(path)
    return path
