"""طباعة استيكرات باركود للأصول الثابتة (PDF).
الباركود = كود الأصل نفسه (Code128 للأكواد اللاتينية/الأرقام، أو QR لأي كود
فيه حروف عربية أو لما المستخدم يختاره) - يعني أي ماسح بيرجّع كود الأصل مباشرةً."""
import datetime
import os
import re

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import code128
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .invoice_pdf import FONT_CANDIDATES, FONT_CANDIDATES_BOLD, _shape_ar

# مقاسات الاستيكر: ملصق حراري (ورقة لكل استيكر) أو ورق ملصقات A4 (شبكة)
PRESETS = {
    "thermal_40x25": {"label": "ملصق حراري 40×25 مم", "kind": "roll", "w": 40, "h": 25},
    "thermal_50x30": {"label": "ملصق حراري 50×30 مم", "kind": "roll", "w": 50, "h": 30},
    "thermal_60x40": {"label": "ملصق حراري 60×40 مم", "kind": "roll", "w": 60, "h": 40},
    "thermal_100x50": {"label": "ملصق حراري 100×50 مم", "kind": "roll", "w": 100, "h": 50},
    "a4_24": {"label": "ورق A4 - 24 ملصق (63.5×33.9 مم)", "kind": "sheet", "w": 63.5, "h": 33.9,
              "cols": 3, "rows": 8, "ml": 7.2, "mt": 15.1, "gx": 2.5, "gy": 0},
    "a4_65": {"label": "ورق A4 - 65 ملصق صغير (38.1×21.2 مم)", "kind": "sheet", "w": 38.1, "h": 21.2,
              "cols": 5, "rows": 13, "ml": 4.7, "mt": 10.7, "gx": 2.5, "gy": 0},
}
MAX_STICKERS = 3000
MIN_BAR_MM = 0.22   # أقل عرض عملي لعمود الباركود عشان الماسح يقراه
_AR = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")


def _register_fonts():
    reg = next((f for f in FONT_CANDIDATES if os.path.exists(f)), None)
    bold = next((f for f in FONT_CANDIDATES_BOLD if os.path.exists(f)), None)
    regular, bold_name = "Helvetica", "Helvetica-Bold"
    try:
        if reg:
            pdfmetrics.registerFont(TTFont("ERPFont", reg)); regular = "ERPFont"
        if bold:
            pdfmetrics.registerFont(TTFont("ERPFontBold", bold)); bold_name = "ERPFontBold"
        elif reg:
            bold_name = regular
    except Exception:
        regular, bold_name = "Helvetica", "Helvetica-Bold"
    return regular, bold_name


def _is_ascii(text):
    try:
        text.encode("ascii"); return True
    except UnicodeEncodeError:
        return False


def _shaped(text):
    return _shape_ar(text) if _AR.search(text) else text


def _pick_font(text, bold, fonts):
    has_ar = bool(_AR.search(text))
    if has_ar or fonts[0] != "Helvetica":
        return fonts[1] if bold else fonts[0]
    return "Helvetica-Bold" if bold else "Helvetica"


def _fit_text(c, text, font, size, max_w, min_size=4.5):
    """يصغّر الخط لحد ما النص يتناسب، ولو لسه أكبر بيقصّ آخر النص المنطقي ويضيف …
    (القص قبل التشكيل، فأول كلمات الاسم دايمًا هي اللي بتفضل ظاهرة)."""
    text = str(text or "")
    while size > min_size and c.stringWidth(_shaped(text), font, size) > max_w:
        size -= 0.25
    if c.stringWidth(_shaped(text), font, size) > max_w:
        while len(text) > 1 and c.stringWidth(_shaped(text + "…"), font, size) > max_w:
            text = text[:-1].rstrip()
        text += "…"
    return _shaped(text), size


def _wrap_words(c, text, font, size, max_w, max_lines):
    """يقسّم النص المنطقي على سطور بالكلمات بحيث كل سطر يتناسب مع العرض."""
    words = str(text or "").split()
    lines, cur = [], ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        if cur and c.stringWidth(_shaped(trial), font, size) > max_w:
            lines.append(cur); cur = w_
        else:
            cur = trial
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        head, tail = lines[:max_lines - 1], " ".join(lines[max_lines - 1:])
        lines = head + [tail]
    return lines


def _draw_text(c, text, cx, y, size, max_w, bold, fonts):
    """يرسم نص (بيتشكّل لو عربي) متوسّط حوالين cx."""
    text = str(text or "")
    if not text:
        return
    font = _pick_font(text, bold, fonts)
    shown, size = _fit_text(c, text, font, size, max_w)
    c.setFont(font, size)
    c.drawCentredString(cx, y, shown)


def _draw_code128(c, value, x, y, w, h):
    """يرسم Code128 متوسّط في عرض الاستيكر كله (x,w) مع الحفاظ على المنطقة الفاضية
    (quiet zone = 10 أعمدة كل جنب) جوه حدود الاستيكر، عشان الإطار أو الاستيكر
    اللي جنبه ميتقراش كأنه جزء من الباركود. بيرجّع عرض العمود بالمم."""
    probe = code128.Code128(value, barWidth=1, barHeight=h, quiet=0, humanReadable=False)
    bar_w = min((w - 0.6 * mm) / (probe.width + 20), 0.55 * mm)
    bc = code128.Code128(value, barWidth=bar_w, barHeight=h, quiet=0, humanReadable=False)
    bc.drawOn(c, x + (w - bc.width) / 2.0, y)
    return bar_w / mm


def _draw_qr(c, value, x, y, side):
    widget = QrCodeWidget(value, barLevel="M")
    b = widget.getBounds()
    bw, bh = b[2] - b[0], b[3] - b[1]
    d = Drawing(side, side, transform=[side / bw, 0, 0, side / bh, 0, 0])
    d.add(widget)
    renderPDF.draw(d, c, x, y)


def _draw_sticker(c, x, y, w, h, item, use_qr, company, border, fonts, warnings):
    """يرسم استيكر واحد في المستطيل (x,y) للركن السفلي الأيسر، (w,h) بالنقاط."""
    m = max(1.6 * mm, min(2.5 * mm, w * 0.05))
    if border:
        c.setLineWidth(0.4); c.setStrokeGray(0.35)
        c.rect(x + 0.25 * mm, y + 0.25 * mm, w - 0.5 * mm, h - 0.5 * mm)
    code, name = item["code"], item["name"]
    unit = h / mm            # الارتفاع بالمم لتحديد أحجام الخطوط
    name_size = max(5.5, min(11, unit * 0.30))
    code_size = max(6.5, min(13, unit * 0.34))
    small = max(4.6, name_size * 0.78)
    top = y + h - m

    if use_qr:
        side = min(h - 2 * m, w * 0.46)
        _draw_qr(c, code, x + m, y + (h - side) / 2.0, side)
        tx0 = x + m + side + m * 0.8
        tw = x + w - m - tx0
        cx = tx0 + tw / 2.0
        name_font = _pick_font(name, False, fonts)
        name_lines = _wrap_words(c, name, name_font, name_size, tw, 2 if h >= 24 * mm else 1)
        rows = ([("c", company, small)] if company and h >= 24 * mm else []) \
            + [("n", ln, name_size) for ln in name_lines] + [("k", code, code_size)]
        block_h = sum(sz * 1.3 for _, _, sz in rows)
        yy = y + (h + block_h) / 2.0 - rows[0][2] * 1.0
        for kind, txt, sz in rows:
            _draw_text(c, txt, cx, yy, sz, tw, kind == "k", fonts)
            yy -= sz * 1.3
        return

    avail_w = w - 2 * m
    cx = x + w / 2.0
    yy = top - small * 0.8
    if company and h >= 24 * mm:
        _draw_text(c, company, cx, yy, small, avail_w, False, fonts); yy -= name_size * 1.1
    else:
        yy = top - name_size * 0.8
    _draw_text(c, name, cx, yy, name_size, avail_w, False, fonts)
    text_block = code_size * 1.35
    bar_top = yy - name_size * 0.45
    bar_bottom = y + m + text_block
    bar_h = max(6 * mm, bar_top - bar_bottom)
    bar_mm = _draw_code128(c, code, x, bar_bottom, w, bar_h)
    if bar_mm < MIN_BAR_MM:
        warnings.add(f"عرض الباركود ضيق جدًا في المقاس ده ({bar_mm:.2f} مم) - الأفضل مقاس أكبر أو QR")
    _draw_text(c, code, cx, y + m + code_size * 0.25, code_size, avail_w, True, fonts)


def render_stickers(items, output_path, preset="thermal_50x30", code_type="code128", copies=1,
                    border=False, start_slot=1, company_name=""):
    """items: [{"code","name"}]. بيرجّع dict: path, count, qr_fallback (أكواد اتحوّلت لـ QR
    لأن فيها حروف عربية), warnings."""
    if preset not in PRESETS:
        raise ValueError("مقاس الاستيكر غير معروف")
    if code_type not in ("code128", "qr"):
        raise ValueError("نوع الرمز غير معروف")
    if not items:
        raise ValueError("مفيش أصول للطباعة")
    copies = int(copies or 1)
    if copies < 1 or copies > 100:
        raise ValueError("عدد النسخ لكل أصل يجب أن يكون من 1 إلى 100")
    total = len(items) * copies
    if total > MAX_STICKERS:
        raise ValueError(f"عدد الاستيكرات ({total}) أكبر من الحد ({MAX_STICKERS}) في ملف واحد - قسّمها")

    spec = PRESETS[preset]
    w, h = spec["w"] * mm, spec["h"] * mm
    fonts = _register_fonts()
    warnings, qr_fallback = set(), []
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    sequence = []
    for it in items:
        for _ in range(copies):
            sequence.append(it)

    def use_qr_for(it):
        if code_type == "qr":
            return True
        if not _is_ascii(it["code"]):
            if it["code"] not in qr_fallback:
                qr_fallback.append(it["code"])
            return True
        return False

    if spec["kind"] == "roll":
        c = canvas.Canvas(output_path, pagesize=(w, h))
        for it in sequence:
            _draw_sticker(c, 0, 0, w, h, it, use_qr_for(it), company_name, border, fonts, warnings)
            c.showPage()
    else:
        cols, rows = spec["cols"], spec["rows"]
        per_page = cols * rows
        start_slot = int(start_slot or 1)
        if start_slot < 1 or start_slot > per_page:
            raise ValueError(f"رقم الخانة اللي هتبدأ منها لازم يكون من 1 إلى {per_page}")
        pw, ph = A4
        c = canvas.Canvas(output_path, pagesize=A4)
        slot = start_slot - 1
        for it in sequence:
            if slot >= per_page:
                c.showPage(); slot = 0
            col, row = slot % cols, slot // cols
            x = spec["ml"] * mm + col * (w + spec["gx"] * mm)
            y = ph - spec["mt"] * mm - (row + 1) * h - row * spec["gy"] * mm
            _draw_sticker(c, x, y, w, h, it, use_qr_for(it), company_name, border, fonts, warnings)
            slot += 1
        c.showPage()
    c.save()
    return {"path": output_path, "count": total, "qr_fallback": qr_fallback, "warnings": sorted(warnings)}


def default_output_path(directory, codes):
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if len(codes) == 1:
        safe = re.sub(r"[^\w\-]+", "_", codes[0], flags=re.UNICODE)
        return os.path.join(directory, f"asset_sticker_{safe}_{stamp}.pdf")
    return os.path.join(directory, f"asset_stickers_{stamp}.pdf")
