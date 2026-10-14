"""ملصقات رف/منتج: اسم + سعر كبير + باركود (EAN-13 لو الباركود 13 رقم صحيح، وإلا Code128 للكود).
بتستخدم نفس مقاسات وأدوات رسم ملصقات الأصول (حراري أو ورق A4 ملصقات)."""
import datetime
import os
import re

from reportlab.graphics.barcode import code128, eanbc
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from .asset_labels import (PRESETS, MAX_STICKERS, _register_fonts, _draw_text, _wrap_words, _pick_font,
                           _is_ascii, _draw_qr)
from .scale_barcode import ean13_valid


def _barcode_for(value):
    """يرجع (kind, value): ean13 | code128 | qr (لو فيه حروف مش لاتينية)."""
    v = str(value or "").strip()
    if v.isdigit() and len(v) == 13 and ean13_valid(v):
        return "ean13", v
    if v and _is_ascii(v):
        return "code128", v
    return "qr", v


def _draw_barcode(c, kind, value, x, y, w, h):
    if kind == "ean13":
        probe = eanbc.Ean13BarcodeWidget(value, barHeight=h, humanReadable=False)
        b = probe.getBounds(); bw = b[2] - b[0]
        scale = min(1.0, (w - 1 * mm) / bw)
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics import renderPDF
        d = Drawing(bw * scale, h, transform=[scale, 0, 0, 1, 0, 0]); d.add(probe)
        renderPDF.draw(d, c, x + (w - bw * scale) / 2.0, y)
    else:
        probe = code128.Code128(value, barWidth=1, barHeight=h, quiet=0, humanReadable=False)
        bar_w = min((w - 0.6 * mm) / (probe.width + 20), 0.55 * mm)
        bc = code128.Code128(value, barWidth=bar_w, barHeight=h, quiet=0, humanReadable=False)
        bc.drawOn(c, x + (w - bc.width) / 2.0, y)


def _draw_label(c, x, y, w, h, it, show_price, show_name, border, fonts, currency):
    m = max(1.4 * mm, min(2.4 * mm, w * 0.05))
    if border:
        c.setLineWidth(0.4); c.setStrokeGray(0.35)
        c.rect(x + 0.25 * mm, y + 0.25 * mm, w - 0.5 * mm, h - 0.5 * mm)
    unit = h / mm
    cx = x + w / 2.0
    avail = w - 2 * m
    kind, code = _barcode_for(it["barcode"])
    price_txt = f"{it['price']:,.2f} {currency}".strip() if show_price else ""
    price_size = max(9, min(22, unit * 0.46)) if show_price else 0
    name_size = max(5.5, min(10.5, unit * 0.27))
    code_size = max(5.5, min(9, unit * 0.22))
    yy = y + h - m
    if show_name:
        font = _pick_font(it["name"], False, fonts)
        lines = _wrap_words(c, it["name"], font, name_size, avail, 2 if h >= 28 * mm else 1)
        for ln in lines:
            yy -= name_size * 1.0
            _draw_text(c, ln, cx, yy, name_size, avail, False, fonts)
            yy -= name_size * 0.25
    bottom = y + m
    if show_price:
        _draw_text(c, price_txt, cx, bottom + 0.5 * mm, price_size, avail, True, fonts)
        bottom += price_size * 1.25
    if kind == "qr":
        side = max(8 * mm, min(yy - bottom - 1 * mm, avail))
        _draw_qr(c, code, cx - side / 2.0, bottom, side)
    else:
        text_h = code_size * 1.3
        bar_h = max(5 * mm, yy - bottom - text_h - 0.5 * mm)
        bar_h = min(bar_h, 14 * mm)
        _draw_barcode(c, kind, code, x, bottom + text_h, w, bar_h)
        _draw_text(c, code, cx, bottom + code_size * 0.2, code_size, avail, False, fonts)


def render_labels(items, output_path, preset="thermal_50x30", copies=1, border=False, start_slot=1,
                  show_price=True, show_name=True, currency=""):
    """items: [{"barcode","name","price","copies"(اختياري)}]."""
    if preset not in PRESETS:
        raise ValueError("مقاس الملصق غير معروف")
    if not items:
        raise ValueError("اختار صنف واحد على الأقل")
    copies = int(copies or 1)
    if copies < 1 or copies > 100:
        raise ValueError("عدد النسخ لازم يكون من 1 إلى 100")
    seq = []
    for it in items:
        n = int(it.get("copies") or copies)
        if n < 1 or n > 500:
            raise ValueError("عدد النسخ لكل صنف لازم يكون من 1 إلى 500")
        seq += [it] * n
    if len(seq) > MAX_STICKERS:
        raise ValueError(f"عدد الملصقات ({len(seq)}) أكبر من الحد ({MAX_STICKERS}) في ملف واحد - قسّمها")
    spec = PRESETS[preset]
    w, h = spec["w"] * mm, spec["h"] * mm
    fonts = _register_fonts()
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    if spec["kind"] == "roll":
        c = canvas.Canvas(output_path, pagesize=(w, h))
        for it in seq:
            _draw_label(c, 0, 0, w, h, it, show_price, show_name, border, fonts, currency); c.showPage()
    else:
        cols, rows = spec["cols"], spec["rows"]; per = cols * rows
        start_slot = int(start_slot or 1)
        if start_slot < 1 or start_slot > per:
            raise ValueError(f"رقم الخانة لازم يكون من 1 إلى {per}")
        _, ph = A4
        c = canvas.Canvas(output_path, pagesize=A4)
        slot = start_slot - 1
        for it in seq:
            if slot >= per:
                c.showPage(); slot = 0
            col, row = slot % cols, slot // cols
            x = spec["ml"] * mm + col * (w + spec["gx"] * mm)
            y = ph - spec["mt"] * mm - (row + 1) * h - row * spec["gy"] * mm
            _draw_label(c, x, y, w, h, it, show_price, show_name, border, fonts, currency)
            slot += 1
        c.showPage()
    c.save()
    return {"path": output_path, "count": len(seq)}


def default_output_path(directory):
    return os.path.join(directory, f"product_labels_{datetime.datetime.now():%Y%m%d_%H%M%S}.pdf")
