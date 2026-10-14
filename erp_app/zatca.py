"""
توليد QR Code متوافق مع هيئة الزكاة والضريبة السعودية (ZATCA) - Phase 1
TLV Encoding ثم Base64 ثم QR PNG.
"""

import base64
import io

try:
    import qrcode
    _QR_AVAILABLE = True
except Exception:
    _QR_AVAILABLE = False


def _tlv(tag: int, value: str) -> bytes:
    value_bytes = str(value).encode("utf-8")
    return bytes([tag, len(value_bytes)]) + value_bytes


def build_zatca_base64(seller_name: str, vat_number: str, timestamp_iso: str,
                       total_with_vat: float, vat_total: float) -> str:
    """يبني نص base64 المتوافق مع ZATCA."""
    payload = (
        _tlv(1, seller_name or "-")
        + _tlv(2, vat_number or "-")
        + _tlv(3, timestamp_iso)
        + _tlv(4, f"{float(total_with_vat):.2f}")
        + _tlv(5, f"{float(vat_total):.2f}")
    )
    return base64.b64encode(payload).decode("ascii")


def qr_png_base64(text: str, box_size: int = 6) -> str:
    """يرجّع صورة QR كـ base64 (PNG) لعرضها في Flet."""
    if not _QR_AVAILABLE:
        return ""
    img = qrcode.make(text, box_size=box_size, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def zatca_qr_png_base64(seller_name, vat_number, timestamp_iso, total_with_vat, vat_total):
    payload = build_zatca_base64(seller_name, vat_number, timestamp_iso,
                                  total_with_vat, vat_total)
    return qr_png_base64(payload)


def send_invoice_to_zatca(settings, invoice_number, invoice_uuid, qr_base64, total_with_vat, vat_total, timeout=15):
    """
    محاولة إرسال الفاتورة لمنصة فاتورة (Reporting API - الفواتير المبسّطة).

    تنبيه صريح مهم: المرحلة الثانية من ZATCA (Phase 2 / Fatoora Integration)
    بتشترط إرسال الفاتورة كملف XML بصيغة UBL 2.1 موقّع رقمياً بشهادة CSID
    حقيقية معتمدة من الهيئة (سلسلة Hash مترابطة بين الفواتير + توقيع
    ECDSA). النظام ده حالياً بيولّد "QR Phase 1" بس (TLV + Base64) وده
    شغال ومضمون 100% لعرضه على الفاتورة الورقية/الإلكترونية.

    الدالة دي بتحاول ترسل بيانات أساسية لمنصة فاتورة كـ best-effort، لكنها
    مش هتنجح فعلياً غالباً من غير XML موقّع وشهادة CSID حقيقية مسجّلة -
    وده متوقع تماماً ومش خطأ في الكود. الاستجابة (نجاح أو فشل ورسالة
    الخطأ الحقيقية من ZATCA) بتتسجل كاملة عشان تكون واضحة، مش مخفية.

    لو محتاج الربط الكامل (XML + توقيع + تسجيل CSID)، ده تكامل إضافي
    منفصل يحتاج تسجيل فعلي مع الهيئة أولاً.
    """
    if not settings or not settings.zatca_enabled:
        return {'status': 'disabled', 'message': 'خاصية الربط مع الزكاة غير مفعّلة في الإعدادات.'}

    if not settings.zatca_api_url:
        return {'status': 'failed', 'message': 'رابط منصة فاتورة (API URL) غير معرَّف في الإعدادات.'}

    try:
        import requests
    except ImportError:
        return {'status': 'failed', 'message': 'مكتبة requests غير متاحة - شغّل: pip install requests'}

    try:
        response = requests.post(
            settings.zatca_api_url.rstrip('/') + '/invoices/reporting/single',
            json={
                'invoiceHash': qr_base64,
                'uuid': invoice_uuid,
                'invoice': qr_base64,
            },
            headers={'Accept-Version': 'V2', 'Content-Type': 'application/json'},
            auth=(settings.zatca_username or '', settings.zatca_password or ''),
            timeout=timeout,
        )
        if response.status_code in (200, 202):
            return {'status': 'sent', 'message': f'تم القبول من منصة فاتورة (HTTP {response.status_code}).', 'raw': response.text[:2000]}
        return {'status': 'failed', 'message': f'رفضت المنصة الطلب (HTTP {response.status_code}): {response.text[:500]}', 'raw': response.text[:2000]}
    except requests.exceptions.RequestException as ex:
        return {'status': 'failed', 'message': f'تعذر الاتصال بمنصة فاتورة: {ex}'}
