"""الفوترة الإلكترونية - ZATCA المرحلة الثانية (الربط والتكامل): فاتورة UBL 2.1 XML، سلسلة هاش (PIH/ICV)، توقيع ECDSA (secp256k1) XAdES،
QR المرحلة الثانية (TLV 1-9)، تسجيل الجهاز (CSR → Compliance CSID → فحوصات الامتثال → Production CSID) والإبلاغ/الاعتماد عبر API الهيئة.

تنبيه صريح: الكود مبني على مواصفات الهيئة (XML implementation standards + Security features) لكن ما اتجرّبش على منصة الهيئة نفسها. المرجع النهائي هو
زر «فحوصات الامتثال» في شاشة الفوترة الإلكترونية: بيبعت فواتير تجريبية للـ sandbox وبيعرض أخطاء الهيئة بالنص عشان تتصلح قبل الإنتاج.
المفتاح الخاص والأسرار في ملف zatca_p2.json (صلاحيات 600) في مجلد البيانات."""
import base64
import datetime
import hashlib
import json
import os
import threading
import urllib.error
import urllib.request
import uuid as _uuid
from xml.sax.saxutils import escape as _esc

from .db import APP_DIR

CFG_PATH = os.path.join(APP_DIR, "zatca_p2.json")
BASES = {"sandbox": "https://gw-fatoora.zatca.gov.sa/e-invoicing/developer-portal",
         "simulation": "https://gw-fatoora.zatca.gov.sa/e-invoicing/simulation",
         "production": "https://gw-fatoora.zatca.gov.sa/e-invoicing/core"}
TEMPLATE_NAMES = {"sandbox": "TSTZATCA-Code-Signing", "simulation": "PREZATCA-Code-Signing", "production": "ZATCA-Code-Signing"}
DEFAULTS = {"enabled": False, "env": "sandbox", "crn": "", "street": "", "building": "", "district": "", "city": "", "postal": "",
            "branch_name": "", "device_serial": "", "industry": "Supply activities", "invoice_types": "1100", "zero_rate_code": "", "zero_rate_text": "",
            "private_key_pem": "", "csr_pem": "", "compliance": {}, "production": {}, "otp_hint": ""}
SECRET_KEYS = ("private_key_pem", "compliance", "production")
INITIAL_PIH = base64.b64encode(hashlib.sha256(b"0").hexdigest().encode()).decode()
NS = {"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
      "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
      "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
      "ds": "http://www.w3.org/2000/09/xmldsig#", "xades": "http://uri.etsi.org/01903/v1.3.2#"}
_lock = threading.Lock()


class ZatcaError(Exception):
    pass


# ------------------------------------------------------------------ الإعدادات
def get_config():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(**kw):
    cfg = get_config()
    for k, v in kw.items():
        if k in DEFAULTS:
            cfg[k] = v
    if cfg["env"] not in BASES:
        raise ValueError("بيئة غير معروفة")
    fd = os.open(CFG_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    return cfg


def public_config():
    c = get_config()
    out = {k: v for k, v in c.items() if k not in SECRET_KEYS and k != "csr_pem"}
    out["has_key"] = bool(c["private_key_pem"])
    out["has_compliance"] = bool(c["compliance"].get("cert_b64"))
    out["has_production"] = bool(c["production"].get("cert_b64"))
    return out


def is_enabled():
    from . import nodesync
    if nodesync.is_node():
        return False          # نسخة فرع: الفوترة الإلكترونية بتتم عند المركز لما العملية تتزامن (مينفعش تتبعت مرتين)
    c = get_config()
    return bool(c["enabled"] and c["production"].get("cert_b64") and c["private_key_pem"])


# ------------------------------------------------------------------ أدوات تشفير
def b64hex_sha256(data):
    """base64 للنص السداسي لـ SHA-256 - الصيغة اللي بتطلبها الهيئة لهاش الشهادة وSignedProperties."""
    return base64.b64encode(hashlib.sha256(data).hexdigest().encode()).decode()


def _load_key(pem):
    from cryptography.hazmat.primitives import serialization
    return serialization.load_pem_private_key(pem.encode() if isinstance(pem, str) else pem, password=None)


def _load_cert(cert_b64):
    from cryptography import x509
    der = base64.b64decode(cert_b64)
    return x509.load_der_x509_certificate(der)


def cert_b64_from_token(token):
    """binarySecurityToken من الهيئة = base64(نص الشهادة base64) → نص الشهادة (DER بصيغة base64)."""
    return base64.b64decode(token).decode().strip()


def generate_csr(vat, org_name, env, branch_name="", serial="", invoice_types="1100", address="", industry="Supply activities"):
    """بيولّد مفتاح EC (secp256k1) وCSR بالتنسيق اللي بتطلبه الهيئة. بيرجّع (key_pem, csr_pem)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID, ObjectIdentifier
    if not (vat and len(vat) == 15 and vat.isdigit() and vat[0] == "3" and vat[-1] == "3"):
        raise ZatcaError("الرقم الضريبي لازم يكون 15 رقم يبدأ بـ 3 وينتهي بـ 3 (اضبطه في إعدادات الشركة)")
    serial = serial or str(_uuid.uuid4())
    key = ec.generate_private_key(ec.SECP256K1())
    prefix = {"sandbox": "TST", "simulation": "PRE", "production": "PRD"}[env]
    subject = x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, "SA"),
                         x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, (branch_name or org_name)[:60]),
                         x509.NameAttribute(NameOID.ORGANIZATION_NAME, org_name[:60]),
                         x509.NameAttribute(NameOID.COMMON_NAME, f"{prefix}-{serial[:20]}-{vat}")])
    san = x509.Name([x509.NameAttribute(NameOID.SURNAME, f"1-ERP|2-1|3-{serial}"), x509.NameAttribute(NameOID.USER_ID, vat),
                     x509.NameAttribute(NameOID.TITLE, invoice_types), x509.NameAttribute(ObjectIdentifier("2.5.4.26"), (address or "SA")[:100]),
                     x509.NameAttribute(NameOID.BUSINESS_CATEGORY, industry[:60])])
    name = TEMPLATE_NAMES[env].encode()
    template = x509.UnrecognizedExtension(ObjectIdentifier("1.3.6.1.4.1.311.20.2"), b"\x13" + bytes([len(name)]) + name)    # PrintableString
    csr = (x509.CertificateSigningRequestBuilder().subject_name(subject)
           .add_extension(template, critical=False)
           .add_extension(x509.SubjectAlternativeName([x509.DirectoryName(san)]), critical=False)
           .sign(key, hashes.SHA256()))
    return (key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()).decode(),
            csr.public_bytes(serialization.Encoding.PEM).decode())


# ------------------------------------------------------------------ بناء الفاتورة
def _q2(x):
    return f"{round(float(x) + 1e-9, 2):.2f}"


def _party_xml(p, supplier=False):
    ident = f'<cac:PartyIdentification><cbc:ID schemeID="{_esc(p.get("scheme", "CRN"))}">{_esc(p["id"])}</cbc:ID></cac:PartyIdentification>' if p.get("id") else ""
    addr = ""
    if p.get("street") or supplier:
        addr = ("<cac:PostalAddress>" f'<cbc:StreetName>{_esc(p.get("street") or "-")}</cbc:StreetName>' f'<cbc:BuildingNumber>{_esc(p.get("building") or "0000")}</cbc:BuildingNumber>'
                f'<cbc:CitySubdivisionName>{_esc(p.get("district") or "-")}</cbc:CitySubdivisionName>' f'<cbc:CityName>{_esc(p.get("city") or "-")}</cbc:CityName>'
                f'<cbc:PostalZone>{_esc(p.get("postal") or "00000")}</cbc:PostalZone>' "<cac:Country><cbc:IdentificationCode>SA</cbc:IdentificationCode></cac:Country></cac:PostalAddress>")
    tax = (f'<cac:PartyTaxScheme><cbc:CompanyID>{_esc(p["vat"])}</cbc:CompanyID><cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:PartyTaxScheme>') if p.get("vat") else ""
    return f'<cac:Party>{ident}{addr}{tax}<cac:PartyLegalEntity><cbc:RegistrationName>{_esc(p["name"])}</cbc:RegistrationName></cac:PartyLegalEntity></cac:Party>'


def _tax_cat(cat, rate, cfg, tag="cac:TaxCategory"):
    ex = ""
    if cat in ("Z", "E", "O"):
        if not cfg.get("zero_rate_code"):
            raise ZatcaError("فيه أصناف بضريبة 0% - اضبط كود وسبب الإعفاء (zero_rate_code / zero_rate_text) في شاشة الفوترة الإلكترونية")
        ex = f'<cbc:TaxExemptionReasonCode>{_esc(cfg["zero_rate_code"])}</cbc:TaxExemptionReasonCode><cbc:TaxExemptionReason>{_esc(cfg.get("zero_rate_text") or cfg["zero_rate_code"])}</cbc:TaxExemptionReason>'
    sch = ' schemeID="UN/ECE 5305" schemeAgencyID="6"' if tag == "cac:TaxCategory" else ""
    return (f'<{tag}><cbc:ID{sch}>{cat}</cbc:ID><cbc:Percent>{rate:.2f}</cbc:Percent>{ex}'
            f'<cac:TaxScheme><cbc:ID{(" schemeID=" + chr(34) + "UN/ECE 5153" + chr(34) + " schemeAgencyID=" + chr(34) + "6" + chr(34)) if tag == "cac:TaxCategory" else ""}>VAT</cbc:ID></cac:TaxScheme></{tag}>')


def compute_lines(items, cfg):
    """items: [{name, qty, gross (شامل الضريبة بعد الخصم), rate}] → أسطر بصافي وضريبة مقرّبة + إجماليات متسقة."""
    lines, groups = [], {}
    for i, it in enumerate(items, 1):
        rate = float(it.get("rate") or 0)
        gross = float(it["gross"])
        if it.get("net") is not None:
            net = round(float(it["net"]), 2)
            tax = round(gross - net, 2)
        else:
            net = round(gross / (1 + rate / 100.0) + 1e-9, 2)
            tax = round(net * rate / 100.0 + 1e-9, 2)
        qty = float(it["qty"]) or 1.0
        cat = "S" if rate > 0 else "Z"
        lines.append({"n": i, "name": it["name"], "qty": qty, "net": net, "tax": tax, "rate": rate, "cat": cat, "price": net / qty})
        g = groups.setdefault((cat, rate), [0.0, 0.0])
        g[0] += net; g[1] += tax
    ext = round(sum(l["net"] for l in lines), 2)
    tax = round(sum(l["tax"] for l in lines), 2)
    return lines, groups, ext, tax


def build_body(d, icv, pih, cfg, seller):
    """d: {kind: invoice|credit|debit, number, uuid, when: datetime, items, customer{...}, pay_code, ref_number, reason}.
    بيرجّع (نص الـXML بعلامات @@UBLEXT@@ و@@QR@@ و@@SIG@@ ، ملخص: {total, vat, mode, issue_ts})."""
    kind = d.get("kind", "invoice")
    cust = d.get("customer") or {}
    standard = bool(cust.get("vat"))
    flags = "0100000" if standard else "0200000"
    code = {"invoice": "388", "credit": "381", "debit": "383"}[kind]
    lines, groups, ext, tax = compute_lines(d["items"], cfg)
    if not lines:
        raise ZatcaError("الفاتورة من غير أصناف")
    total = round(ext + tax, 2)
    when = d["when"]
    idate, itime = when.strftime("%Y-%m-%d"), when.strftime("%H:%M:%S")
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" xmlns:cac="{NS["cac"]}" xmlns:cbc="{NS["cbc"]}" xmlns:ext="{NS["ext"]}">',
             "@@UBLEXT@@",
             "    <cbc:ProfileID>reporting:1.0</cbc:ProfileID>", f"    <cbc:ID>{_esc(d['number'])}</cbc:ID>", f"    <cbc:UUID>{d['uuid']}</cbc:UUID>",
             f"    <cbc:IssueDate>{idate}</cbc:IssueDate>", f"    <cbc:IssueTime>{itime}</cbc:IssueTime>",
             f'    <cbc:InvoiceTypeCode name="{flags}">{code}</cbc:InvoiceTypeCode>',
             "    <cbc:DocumentCurrencyCode>SAR</cbc:DocumentCurrencyCode>", "    <cbc:TaxCurrencyCode>SAR</cbc:TaxCurrencyCode>"]
    if kind in ("credit", "debit"):
        parts.append(f"    <cac:BillingReference><cac:InvoiceDocumentReference><cbc:ID>{_esc(d['ref_number'])}</cbc:ID></cac:InvoiceDocumentReference></cac:BillingReference>")
    parts += [f"    <cac:AdditionalDocumentReference><cbc:ID>ICV</cbc:ID><cbc:UUID>{int(icv)}</cbc:UUID></cac:AdditionalDocumentReference>",
              f'    <cac:AdditionalDocumentReference><cbc:ID>PIH</cbc:ID><cac:Attachment><cbc:EmbeddedDocumentBinaryObject mimeCode="text/plain">{pih}</cbc:EmbeddedDocumentBinaryObject></cac:Attachment></cac:AdditionalDocumentReference>',
              "@@QR@@", "@@SIG@@",
              f"    <cac:AccountingSupplierParty>{_party_xml(seller, True)}</cac:AccountingSupplierParty>"]
    buyer = {"name": cust.get("name") or "عميل نقدي", "vat": cust.get("vat"), "id": cust.get("crn"), "scheme": "CRN" if cust.get("crn") else "NAT",
             "street": cust.get("street") or (cust.get("address") if standard else ""), "building": cust.get("building"), "district": cust.get("district"),
             "city": cust.get("city"), "postal": cust.get("postal")}
    if standard and not buyer["id"]:
        buyer["id"] = None
    parts.append(f"    <cac:AccountingCustomerParty>{_party_xml(buyer)}</cac:AccountingCustomerParty>")
    if standard:
        parts.append(f"    <cac:Delivery><cbc:ActualDeliveryDate>{idate}</cbc:ActualDeliveryDate><cbc:LatestDeliveryDate>{idate}</cbc:LatestDeliveryDate></cac:Delivery>")
    note = f"<cbc:InstructionNote>{_esc((d.get('reason') or 'مرتجع')[:200])}</cbc:InstructionNote>" if kind in ("credit", "debit") else ""
    parts.append(f"    <cac:PaymentMeans><cbc:PaymentMeansCode>{d.get('pay_code', '10')}</cbc:PaymentMeansCode>{note}</cac:PaymentMeans>")
    parts.append(f'    <cac:TaxTotal><cbc:TaxAmount currencyID="SAR">{_q2(tax)}</cbc:TaxAmount></cac:TaxTotal>')
    subs = "".join(f'<cac:TaxSubtotal><cbc:TaxableAmount currencyID="SAR">{_q2(v[0])}</cbc:TaxableAmount><cbc:TaxAmount currencyID="SAR">{_q2(v[1])}</cbc:TaxAmount>{_tax_cat(c, r, cfg)}</cac:TaxSubtotal>'
                   for (c, r), v in sorted(groups.items()))
    parts.append(f'    <cac:TaxTotal><cbc:TaxAmount currencyID="SAR">{_q2(tax)}</cbc:TaxAmount>{subs}</cac:TaxTotal>')
    parts.append('    <cac:LegalMonetaryTotal>' f'<cbc:LineExtensionAmount currencyID="SAR">{_q2(ext)}</cbc:LineExtensionAmount>' f'<cbc:TaxExclusiveAmount currencyID="SAR">{_q2(ext)}</cbc:TaxExclusiveAmount>'
                 f'<cbc:TaxInclusiveAmount currencyID="SAR">{_q2(total)}</cbc:TaxInclusiveAmount>' '<cbc:AllowanceTotalAmount currencyID="SAR">0.00</cbc:AllowanceTotalAmount>'
                 '<cbc:PrepaidAmount currencyID="SAR">0.00</cbc:PrepaidAmount>' f'<cbc:PayableAmount currencyID="SAR">{_q2(total)}</cbc:PayableAmount></cac:LegalMonetaryTotal>')
    for l in lines:
        parts.append(f'    <cac:InvoiceLine><cbc:ID>{l["n"]}</cbc:ID><cbc:InvoicedQuantity unitCode="PCE">{l["qty"]:.6f}</cbc:InvoicedQuantity>'
                     f'<cbc:LineExtensionAmount currencyID="SAR">{_q2(l["net"])}</cbc:LineExtensionAmount>'
                     f'<cac:TaxTotal><cbc:TaxAmount currencyID="SAR">{_q2(l["tax"])}</cbc:TaxAmount><cbc:RoundingAmount currencyID="SAR">{_q2(l["net"] + l["tax"])}</cbc:RoundingAmount></cac:TaxTotal>'
                     f'<cac:Item><cbc:Name>{_esc(l["name"][:200])}</cbc:Name>{_tax_cat(l["cat"], l["rate"], cfg, "cac:ClassifiedTaxCategory")}</cac:Item>'
                     f'<cac:Price><cbc:PriceAmount currencyID="SAR">{l["price"]:.4f}</cbc:PriceAmount></cac:Price></cac:InvoiceLine>')
    parts.append("</Invoice>")
    return "\n".join(parts), {"total": total, "vat": tax, "mode": "standard" if standard else "simplified", "issue_ts": f"{idate}T{itime}"}


# ------------------------------------------------------------------ الهاش والتوقيع
def _strip(el):
    parent = el.getparent()
    tail = el.tail or ""
    prev = el.getprevious()
    if prev is not None:
        prev.tail = (prev.tail or "") + tail
    else:
        parent.text = (parent.text or "") + tail
    parent.remove(el)


def invoice_hash(xml_text):
    """هاش الفاتورة: نشيل UBLExtensions وcac:Signature ومرجع QR، C14N11، SHA-256 → (bytes, base64)."""
    from lxml import etree
    root = etree.fromstring(xml_text.encode("utf-8"))
    ns = {"cac": NS["cac"], "cbc": NS["cbc"], "ext": NS["ext"]}
    for el in root.xpath("/*/ext:UBLExtensions", namespaces=ns):
        _strip(el)
    for el in root.xpath("/*/cac:Signature", namespaces=ns):
        _strip(el)
    for el in root.xpath("/*/cac:AdditionalDocumentReference[cbc:ID='QR']", namespaces=ns):
        _strip(el)
    raw = hashlib.sha256(etree.tostring(root, method="c14n")).digest()
    return raw, base64.b64encode(raw).decode()


def _signed_props(signing_time, cert_digest, issuer, serial):
    return ('<xades:SignedProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" Id="xadesSignedProperties">\n'
            "    <xades:SignedSignatureProperties>\n"
            f"        <xades:SigningTime>{signing_time}</xades:SigningTime>\n"
            "        <xades:SigningCertificate>\n"
            "            <xades:Cert>\n"
            "                <xades:CertDigest>\n"
            '                    <ds:DigestMethod xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"></ds:DigestMethod>\n'
            f'                    <ds:DigestValue xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{cert_digest}</ds:DigestValue>\n'
            "                </xades:CertDigest>\n"
            "                <xades:IssuerSerial>\n"
            f'                    <ds:X509IssuerName xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{_esc(issuer)}</ds:X509IssuerName>\n'
            f'                    <ds:X509SerialNumber xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{serial}</ds:X509SerialNumber>\n'
            "                </xades:IssuerSerial>\n"
            "            </xades:Cert>\n"
            "        </xades:SigningCertificate>\n"
            "    </xades:SignedSignatureProperties>\n"
            "</xades:SignedProperties>")


def _ubl_ext(inv_digest, props_digest, sig_value, cert_b64, props):
    return ('    <ext:UBLExtensions><ext:UBLExtension><ext:ExtensionURI>urn:oasis:names:specification:ubl:dsig:enveloped:xades</ext:ExtensionURI><ext:ExtensionContent>'
            '<sig:UBLDocumentSignatures xmlns:sig="urn:oasis:names:specification:ubl:schema:xsd:CommonSignatureComponents-2" '
            'xmlns:sac="urn:oasis:names:specification:ubl:schema:xsd:SignatureAggregateComponents-2" xmlns:sbc="urn:oasis:names:specification:ubl:schema:xsd:SignatureBasicComponents-2">'
            "<sac:SignatureInformation><cbc:ID>urn:oasis:names:specification:ubl:signature:1</cbc:ID><sbc:ReferencedSignatureID>urn:oasis:names:specification:ubl:signature:Invoice</sbc:ReferencedSignatureID>"
            '<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#" Id="signature"><ds:SignedInfo>'
            '<ds:CanonicalizationMethod Algorithm="http://www.w3.org/2006/12/xml-c14n11"></ds:CanonicalizationMethod>'
            '<ds:SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#ecdsa-sha256"></ds:SignatureMethod>'
            '<ds:Reference Id="invoiceSignedData" URI=""><ds:Transforms>'
            '<ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116"><ds:XPath>not(//ancestor-or-self::ext:UBLExtensions)</ds:XPath></ds:Transform>'
            '<ds:Transform Algorithm="http://www.w3.org/TR/1999/REC-xpath-19991116"><ds:XPath>not(//ancestor-or-self::cac:Signature)</ds:XPath></ds:Transform>'
            "<ds:Transform Algorithm=\"http://www.w3.org/TR/1999/REC-xpath-19991116\"><ds:XPath>not(//ancestor-or-self::cac:AdditionalDocumentReference[cbc:ID='QR'])</ds:XPath></ds:Transform>"
            '<ds:Transform Algorithm="http://www.w3.org/2006/12/xml-c14n11"></ds:Transform></ds:Transforms>'
            f'<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"></ds:DigestMethod><ds:DigestValue>{inv_digest}</ds:DigestValue></ds:Reference>'
            '<ds:Reference Type="http://www.w3.org/2000/09/xmldsig#SignatureProperties" URI="#xadesSignedProperties">'
            f'<ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"></ds:DigestMethod><ds:DigestValue>{props_digest}</ds:DigestValue></ds:Reference></ds:SignedInfo>'
            f"<ds:SignatureValue>{sig_value}</ds:SignatureValue>"
            f"<ds:KeyInfo><ds:X509Data><ds:X509Certificate>{cert_b64}</ds:X509Certificate></ds:X509Data></ds:KeyInfo>"
            '<ds:Object><xades:QualifyingProperties xmlns:xades="http://uri.etsi.org/01903/v1.3.2#" Target="signature">'
            f"{props}"
            "</xades:QualifyingProperties></ds:Object></ds:Signature></sac:SignatureInformation></sig:UBLDocumentSignatures></ext:ExtensionContent></ext:UBLExtension></ext:UBLExtensions>")


_SIG_ELEM = ("    <cac:Signature><cbc:ID>urn:oasis:names:specification:ubl:signature:Invoice</cbc:ID>"
             "<cbc:SignatureMethod>urn:oasis:names:specification:ubl:dsig:enveloped:xades</cbc:SignatureMethod></cac:Signature>")


def _qr_elem(b64):
    return ('    <cac:AdditionalDocumentReference><cbc:ID>QR</cbc:ID><cac:Attachment>'
            f'<cbc:EmbeddedDocumentBinaryObject mimeCode="text/plain">{b64}</cbc:EmbeddedDocumentBinaryObject></cac:Attachment></cac:AdditionalDocumentReference>')


def _tlv(tag, value):
    b = value if isinstance(value, bytes) else str(value).encode("utf-8")
    if len(b) > 255:
        raise ZatcaError("قيمة QR أطول من 255 بايت")
    return bytes([tag, len(b)]) + b


def build_qr(seller_name, vat, ts, total, vat_total, inv_hash_b64, sig_b64, pubkey_der, cert_sig):
    payload = (_tlv(1, seller_name) + _tlv(2, vat) + _tlv(3, ts) + _tlv(4, f"{total:.2f}") + _tlv(5, f"{vat_total:.2f}")
               + _tlv(6, inv_hash_b64) + _tlv(7, sig_b64) + _tlv(8, pubkey_der) + _tlv(9, cert_sig))
    return base64.b64encode(payload).decode()


def sign_document(body, summary, key_pem, cert_b64, seller_name, vat, signing_time=None):
    """بيوقّع الفاتورة. بيرجّع (xml نهائي، hash_b64، qr_b64)."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    cert = _load_cert(cert_b64)
    key = _load_key(key_pem)
    signing_time = signing_time or datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    # شكل الوثيقة (بعلامات فاضية بنفس البنية) لحساب الهاش
    probe = body.replace("@@UBLEXT@@", "    <ext:UBLExtensions></ext:UBLExtensions>").replace("@@QR@@", _qr_elem("")).replace("@@SIG@@", _SIG_ELEM)
    raw, inv_b64 = invoice_hash(probe)
    sig = key.sign(raw, ec.ECDSA(hashes.SHA256()))
    sig_b64 = base64.b64encode(sig).decode()
    props = _signed_props(signing_time, b64hex_sha256(cert_b64.encode()), cert.issuer.rfc4514_string(), cert.serial_number)
    props_digest = b64hex_sha256(props.encode("utf-8"))
    pub = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    qr = build_qr(seller_name, vat, summary["issue_ts"], summary["total"], summary["vat"], inv_b64, sig_b64, pub, cert.signature)
    final = body.replace("@@UBLEXT@@", _ubl_ext(inv_b64, props_digest, sig_b64, cert_b64, props)).replace("@@QR@@", _qr_elem(qr)).replace("@@SIG@@", _SIG_ELEM)
    return final, inv_b64, qr


def verify_document(xml_text):
    """فحص ذاتي: يعيد حساب الهاش ويتحقق من التوقيع والـ SignedProperties وQR. بيرجّع قايمة مشاكل (فاضية = سليم)."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from lxml import etree
    problems = []
    root = etree.fromstring(xml_text.encode("utf-8"))
    ns = {"ds": NS["ds"], "xades": NS["xades"], "cac": NS["cac"], "cbc": NS["cbc"]}
    try:
        raw, b64 = invoice_hash(xml_text)
        stated = root.xpath("//ds:Reference[@Id='invoiceSignedData']/ds:DigestValue/text()", namespaces=ns)[0]
        if stated != b64:
            problems.append("هاش الفاتورة مش مطابق للمكتوب في التوقيع")
        sigv = root.xpath("//ds:SignatureValue/text()", namespaces=ns)[0]
        cert_b64 = root.xpath("//ds:X509Certificate/text()", namespaces=ns)[0]
        cert = _load_cert(cert_b64)
        try:
            cert.public_key().verify(base64.b64decode(sigv), raw, ec.ECDSA(hashes.SHA256()))
        except Exception:      # noqa: BLE001
            problems.append("توقيع ECDSA غير صحيح")
        start = xml_text.index("<xades:SignedProperties")
        end = xml_text.index("</xades:SignedProperties>") + len("</xades:SignedProperties>")
        pd = root.xpath("//ds:Reference[@URI='#xadesSignedProperties']/ds:DigestValue/text()", namespaces=ns)[0]
        if pd != b64hex_sha256(xml_text[start:end].encode("utf-8")):
            problems.append("digest الـ SignedProperties غلط")
        cd = root.xpath("//xades:CertDigest/ds:DigestValue/text()", namespaces=ns)[0]
        if cd != b64hex_sha256(cert_b64.encode()):
            problems.append("digest الشهادة غلط")
        qr = root.xpath("//cac:AdditionalDocumentReference[cbc:ID='QR']//cbc:EmbeddedDocumentBinaryObject/text()", namespaces=ns)[0]
        tags = parse_tlv(qr)
        if tags.get(6, b"").decode() != b64 or tags.get(7, b"").decode() != sigv:
            problems.append("QR مش مطابق لهاش/توقيع الفاتورة")
        tot = root.xpath("//cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount/text()", namespaces=ns)[0]
        if tags.get(4, b"").decode() != tot:
            problems.append("إجمالي QR مختلف عن الفاتورة")
    except Exception as ex:      # noqa: BLE001
        problems.append(f"فشل الفحص: {type(ex).__name__}: {ex}")
    return problems


def parse_tlv(b64):
    raw, i, out = base64.b64decode(b64), 0, {}
    while i < len(raw):
        t, n = raw[i], raw[i + 1]
        out[t] = raw[i + 2:i + 2 + n]
        i += 2 + n
    return out


# ------------------------------------------------------------------ API الهيئة
def _api(path, cfg_env, body=None, headers=None, auth=None, method="POST", timeout=30):
    url = BASES[cfg_env] + path
    h = {"Accept": "application/json", "Accept-Version": "V2", "Accept-Language": "en", "Content-Type": "application/json"}
    h.update(headers or {})
    if auth:
        h["Authorization"] = "Basic " + base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, txt = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        code, txt = e.code, e.read().decode("utf-8", "replace")
    except Exception as ex:      # noqa: BLE001
        raise ZatcaError(f"تعذر الاتصال بالهيئة: {ex}")
    try:
        return code, json.loads(txt)
    except ValueError:
        return code, {"raw": txt[:1500]}


def _msgs(resp):
    out = []
    v = resp.get("validationResults") or {}
    for k in ("errorMessages", "warningMessages"):
        for m in v.get(k) or []:
            out.append(("خطأ" if k.startswith("error") else "تحذير") + f" {m.get('code', '')}: {m.get('message', '')}")
    for k in ("errors", "message", "dispositionMessage", "raw"):
        if resp.get(k):
            out.append(str(resp[k])[:400])
    return out


def start_onboarding(vat, org_name, otp):
    """1) يولّد المفتاح وCSR  2) يبعتهم مع الـ OTP (من بوابة فاتورة) ويستلم Compliance CSID. بيحفظ كل حاجة في الإعدادات."""
    cfg = get_config()
    key_pem, csr_pem = generate_csr(vat, org_name, cfg["env"], cfg["branch_name"], cfg["device_serial"], cfg["invoice_types"],
                                    " ".join(x for x in (cfg["building"], cfg["street"], cfg["district"], cfg["city"]) if x))
    code, resp = _api("/compliance", cfg["env"], {"csr": base64.b64encode(csr_pem.encode()).decode()}, {"OTP": str(otp).strip()})
    if code != 200 or not resp.get("binarySecurityToken"):
        raise ZatcaError(f"رفضت الهيئة طلب الشهادة (HTTP {code}): " + " | ".join(_msgs(resp)))
    save_config(private_key_pem=key_pem, csr_pem=csr_pem, production={}, compliance={
        "request_id": str(resp.get("requestID")), "token": resp["binarySecurityToken"], "secret": resp["secret"], "cert_b64": cert_b64_from_token(resp["binarySecurityToken"])})
    return resp.get("dispositionMessage", "ISSUED")


def sample_docs(cfg, seller):
    """فواتير تجريبية (حسب أنواع الفواتير المعلنة في CSR) لفحوصات الامتثال."""
    types = cfg["invoice_types"]
    now = datetime.datetime.now()
    items = [{"name": "صنف تجريبي", "qty": 2, "gross": 115.0, "rate": 15}]
    out = []
    for std, flag in ((True, types[0] == "1"), (False, types[1] == "1")):
        if not flag:
            continue
        cust = {"name": "عميل تجريبي", "vat": "399999999800003", "crn": "1010010000", "street": "Prince Sultan", "building": "1234", "district": "Olaya", "city": "Riyadh", "postal": "12345"} if std else {}
        for kind in ("invoice", "credit", "debit"):
            out.append({"kind": kind, "number": f"SMPL-{'STD' if std else 'SIM'}-{kind[:3].upper()}-{now:%H%M%S}", "uuid": str(_uuid.uuid4()), "when": now, "items": items, "customer": cust,
                        "pay_code": "10", "ref_number": "SMPL-REF-1", "reason": "اختبار"})
    return out


def run_compliance_checks(vat, org_name):
    """يبعت فواتير تجريبية موقّعة بشهادة الامتثال لـ /compliance/invoices ويرجّع [(الوصف، ok، رسائل)]."""
    cfg = get_config()
    comp = cfg["compliance"]
    if not comp.get("cert_b64"):
        raise ZatcaError("ابدأ التسجيل الأول (اطلب شهادة الامتثال)")
    seller = seller_info(cfg, vat, org_name)
    pih, icv, results = INITIAL_PIH, 1, []
    for d in sample_docs(cfg, seller):
        body, summ = build_body(d, icv, pih, cfg, seller)
        xml, h, _ = sign_document(body, summ, cfg["private_key_pem"], comp["cert_b64"], org_name, vat)
        code, resp = _api("/compliance/invoices", cfg["env"], {"invoiceHash": h, "uuid": d["uuid"], "invoice": base64.b64encode(xml.encode()).decode()}, auth=(comp["token"], comp["secret"]))
        status = (resp.get("reportingStatus") or resp.get("clearanceStatus") or "")
        ok = code == 200 and ("REPORTED" in status or "CLEARED" in status) and not (resp.get("validationResults") or {}).get("errorMessages")
        results.append((f"{summ['mode']} / {d['kind']}", ok, _msgs(resp) or [f"HTTP {code} {status}"]))
        pih, icv = h, icv + 1
    return results


def finish_onboarding():
    """بعد نجاح الفحوصات: يطلب Production CSID."""
    cfg = get_config()
    comp = cfg["compliance"]
    code, resp = _api("/production/csids", cfg["env"], {"compliance_request_id": comp["request_id"]}, auth=(comp["token"], comp["secret"]))
    if code != 200 or not resp.get("binarySecurityToken"):
        raise ZatcaError(f"رفضت الهيئة شهادة الإنتاج (HTTP {code}): " + " | ".join(_msgs(resp)))
    save_config(production={"request_id": str(resp.get("requestID")), "token": resp["binarySecurityToken"], "secret": resp["secret"], "cert_b64": cert_b64_from_token(resp["binarySecurityToken"])})
    return resp.get("dispositionMessage", "ISSUED")


def seller_info(cfg, vat, name):
    return {"name": name, "vat": vat, "id": cfg["crn"], "scheme": "CRN", "street": cfg["street"], "building": cfg["building"], "district": cfg["district"], "city": cfg["city"], "postal": cfg["postal"]}


def submit_xml(doc_row):
    """يبعت فاتورة موقّعة محفوظة: مبسّطة → reporting، عادية → clearance. بيرجّع (status, رسالة, xml_معتمد|None)."""
    cfg = get_config()
    prod = cfg["production"]
    if not prod.get("cert_b64"):
        raise ZatcaError("مفيش شهادة إنتاج")
    standard = doc_row["mode"] == "standard"
    path = "/invoices/clearance/single" if standard else "/invoices/reporting/single"
    code, resp = _api(path, cfg["env"], {"invoiceHash": doc_row["hash"], "uuid": doc_row["uuid"], "invoice": base64.b64encode(doc_row["xml"].encode()).decode()},
                      {"Clearance-Status": "1" if standard else "0"}, auth=(prod["token"], prod["secret"]))
    msgs = " | ".join(_msgs(resp))
    st = str(resp.get("reportingStatus") or resp.get("clearanceStatus") or "")
    if code in (200, 202) and ("REPORTED" in st or "CLEARED" in st):
        cleared = None
        if resp.get("clearedInvoice"):
            try:
                cleared = base64.b64decode(resp["clearedInvoice"]).decode("utf-8")
            except Exception:      # noqa: BLE001
                cleared = None
        return "cleared" if standard else "reported", (msgs or st)[:1500], cleared
    if code in (400, 401, 403, 409, 422):
        return "rejected", f"HTTP {code}: {msgs}"[:1500], None
    return "failed", f"HTTP {code}: {msgs}"[:1500], None


# ------------------------------------------------------------------ ربط بالنظام (فواتير ومرتجعات)
SYNC = False                # الاختبارات: إرسال متزامن بدل خيط خلفي
MAX_ATTEMPTS = 8


def _company():
    from . import services
    c = services.get_company_settings()
    return (c.name or "-"), (c.vat_number or "").strip()


def _pay_code(method, has_customer):
    m = (method or "")
    if any(k in m for k in ("بطاقة", "شبكة", "مدى", "فيزا", "card", "Card", "mada")):
        return "48"
    if "تحويل" in m or "transfer" in m.lower():
        return "42"
    if not m:
        return "30" if has_customer else "10"
    return "10"


def _customer_dict(c):
    if not c:
        return {}
    return {"name": c.name, "vat": (c.vat_number or "").strip() or None, "crn": getattr(c, "crn", "") or None, "street": c.address or "", "building": getattr(c, "building_no", ""),
            "district": getattr(c, "district", ""), "city": getattr(c, "city", ""), "postal": getattr(c, "postal_code", "")}


def _net_of(it):
    """صافي السطر قبل الضريبة زي ما النظام حسبه (كمية×سعر−خصم) لو متطابق مع الإجمالي، وإلا (خصم ترويجي موزّع) بنستنتجه من الإجمالي."""
    base = round(max(0.0, float(it.quantity) * float(it.unit_price) - float(it.discount or 0)), 2)
    rate = float(it.tax_rate or 0)
    if abs(float(it.line_total) - (base + round(base * rate / 100.0, 2))) <= 0.011:
        return base
    return None


def _inv_dict(s, kind, ref_id):
    from .db import SalesInvoice, SalesReturn
    if kind == "invoice":
        inv = s.get(SalesInvoice, ref_id)
        if not inv:
            raise ZatcaError("الفاتورة غير موجودة")
        items = [{"name": it.product.name if it.product else f"صنف {it.product_id}", "qty": it.quantity, "gross": it.line_total, "rate": it.tax_rate, "net": _net_of(it)} for it in inv.items]
        return {"kind": "invoice", "number": inv.number, "when": inv.date, "items": items, "customer": _customer_dict(inv.customer),
                "pay_code": _pay_code(inv.payment_method, bool(inv.customer_id))}
    ret = s.get(SalesReturn, ref_id)
    if not ret:
        raise ZatcaError("المرتجع غير موجود")
    items = [{"name": it.product.name if it.product else f"صنف {it.product_id}", "qty": it.quantity, "gross": it.line_total, "rate": it.tax_rate, "net": _net_of(it)} for it in ret.items]
    return {"kind": "credit", "number": ret.number, "when": ret.date, "items": items, "customer": _customer_dict(ret.customer or (ret.invoice.customer if ret.invoice else None)),
            "pay_code": _pay_code(ret.refund_method, False), "ref_number": ret.invoice.number if ret.invoice else "", "reason": ret.reason or "مرتجع"}


def _issue(kind, ref_id):
    from .db import ZatcaDoc, get_session, lock_numbering
    cfg = get_config()
    if not is_enabled():
        return None
    name, vat = _company()
    with get_session() as s:
        lock_numbering(s)
        ex = s.query(ZatcaDoc).filter_by(kind=kind, ref_id=ref_id).first()
        if ex:
            return ex.id
        last = s.query(ZatcaDoc).order_by(ZatcaDoc.icv.desc()).first()
        icv, pih = (last.icv + 1, last.hash) if last else (1, INITIAL_PIH)
        d = _inv_dict(s, kind, ref_id)
        d["uuid"] = str(_uuid.uuid4())
        body, summ = build_body(d, icv, pih, cfg, seller_info(cfg, vat, name))
        xml, h, qr = sign_document(body, summ, cfg["private_key_pem"], cfg["production"]["cert_b64"], name, vat)
        doc = ZatcaDoc(kind=kind, ref_id=ref_id, number=d["number"], uuid=d["uuid"], icv=icv, pih=pih, hash=h, mode=summ["mode"], xml=xml, qr=qr, status="signed")
        s.add(doc)
        _mark_invoice(s, kind, ref_id, "pending", "موقّعة - في انتظار الإرسال لمنصة فاتورة")
        s.commit()
        return doc.id


def _mark_invoice(s, kind, ref_id, status, msg):
    from .db import SalesInvoice
    if kind == "invoice":
        inv = s.get(SalesInvoice, ref_id)
        if inv:
            inv.zatca_status, inv.zatca_response = status, msg[:1500]


def issue_invoice(invoice_id, send=True):
    """يوقّع فاتورة المبيعات (لو الفوترة الإلكترونية مفعّلة) ويبدأ إرسالها. مبيرميش استثناء أبدًا: فشل الفوترة ما يوقفش البيع."""
    return _safe_issue("invoice", invoice_id, send)


def issue_return(return_id, send=True):
    return _safe_issue("credit", return_id, send)


def _safe_issue(kind, ref_id, send):
    try:
        doc_id = _issue(kind, ref_id)
    except Exception as ex:      # noqa: BLE001
        try:
            from . import audit
            audit.log_event("zatca_error", label=f"{kind} {ref_id}", changes=f"{type(ex).__name__}: {ex}"[:300], username="system")
            from .db import SalesInvoice, get_session
            if kind == "invoice":
                with get_session() as s:
                    _mark_invoice(s, kind, ref_id, "failed", f"تعذر إصدار الفاتورة الإلكترونية: {ex}")
                    s.commit()
        except Exception:      # noqa: BLE001
            pass
        return None
    if doc_id and send:
        if SYNC:
            try:
                send_doc(doc_id)
            except Exception:      # noqa: BLE001
                pass
        else:
            threading.Thread(target=lambda: _quiet(send_doc, doc_id), daemon=True).start()
    return doc_id


def _quiet(fn, *a):
    try:
        return fn(*a)
    except Exception:      # noqa: BLE001
        return None


def send_doc(doc_id):
    from .db import ZatcaDoc, get_session
    with _lock:
        with get_session() as s:
            d = s.get(ZatcaDoc, doc_id)
            if not d or d.status in ("reported", "cleared", "rejected"):
                return d.status if d else None
            row = {"mode": d.mode, "hash": d.hash, "uuid": d.uuid, "xml": d.xml}
        try:
            status, msg, cleared = submit_xml(row)
        except Exception as ex:      # noqa: BLE001
            status, msg, cleared = "failed", f"{type(ex).__name__}: {ex}"[:1500], None
        with get_session() as s:
            d = s.get(ZatcaDoc, doc_id)
            d.attempts = (d.attempts or 0) + 1
            d.status, d.response, d.sent_at = status, msg, datetime.datetime.now()
            if cleared:
                d.xml = cleared
                try:
                    from lxml import etree
                    r = etree.fromstring(cleared.encode("utf-8"))
                    q = r.xpath("//cac:AdditionalDocumentReference[cbc:ID='QR']//cbc:EmbeddedDocumentBinaryObject/text()", namespaces={"cac": NS["cac"], "cbc": NS["cbc"]})
                    if q:
                        d.qr = q[0]
                except Exception:      # noqa: BLE001
                    pass
            _mark_invoice(s, d.kind, d.ref_id, {"reported": "sent", "cleared": "sent", "rejected": "failed"}.get(status, "failed" if status == "failed" else "pending"), msg or status)
            s.commit()
        return status


def send_pending(limit=30):
    """للمجدول: يعيد محاولة المستندات الموقّعة/الفاشلة (backoff أُسّي، حد أقصى MAX_ATTEMPTS)."""
    from .db import ZatcaDoc, get_session
    if not is_enabled():
        return 0
    now = datetime.datetime.now()
    with get_session() as s:
        ids = []
        for d in s.query(ZatcaDoc).filter(ZatcaDoc.status.in_(("signed", "failed"))).order_by(ZatcaDoc.icv).limit(200):
            if (d.attempts or 0) >= MAX_ATTEMPTS:
                continue
            wait = min(3600, 60 * 2 ** (d.attempts or 0))
            if d.sent_at and (now - d.sent_at).total_seconds() < wait:
                continue
            ids.append(d.id)
    n = 0
    for i in ids[:limit]:
        send_doc(i)
        n += 1
    return n


def issue_missing(days=3):
    """يصدر مستندات لفواتير/مرتجعات آخر N يوم اللي ما اتوقّعتش (مثلًا لو الفوترة اتفعّلت بعد البيع أو حصل خطأ)."""
    from .db import SalesInvoice, SalesReturn, ZatcaDoc, get_session
    since = datetime.datetime.now() - datetime.timedelta(days=days)
    with get_session() as s:
        have = {(k, r) for k, r in s.query(ZatcaDoc.kind, ZatcaDoc.ref_id)}
        todo = [("invoice", i.id, i.date) for i in s.query(SalesInvoice).filter(SalesInvoice.date >= since, SalesInvoice.voided.isnot(True)) if ("invoice", i.id) not in have]
        todo += [("credit", r.id, r.date) for r in s.query(SalesReturn).filter(SalesReturn.date >= since) if ("credit", r.id) not in have]
    n = 0
    for kind, rid, _ in sorted(todo, key=lambda t: t[2]):
        if _safe_issue(kind, rid, False):
            n += 1
    return n


def qr_png_for_invoice(invoice_id):
    """صورة QR (base64 PNG) من المستند الموقّع للفاتورة، أو None لو مفيش فوترة إلكترونية لها."""
    from .db import ZatcaDoc, get_session
    from .zatca import qr_png_base64
    try:
        with get_session() as s:
            d = s.query(ZatcaDoc).filter_by(kind="invoice", ref_id=int(invoice_id)).first()
            return qr_png_base64(d.qr) if d and d.qr else None
    except Exception:      # noqa: BLE001
        return None


def qr_text_for_invoice(invoice_id):
    """نص QR (base64 TLV) من المستند الموقّع، أو None."""
    from .db import ZatcaDoc, get_session
    try:
        with get_session() as s:
            d = s.query(ZatcaDoc).filter_by(kind="invoice", ref_id=int(invoice_id)).first()
            return d.qr if d and d.qr else None
    except Exception:      # noqa: BLE001
        return None


def list_docs(limit=100):
    from .db import ZatcaDoc, get_session
    with get_session() as s:
        return [{"id": d.id, "kind": d.kind, "number": d.number, "icv": d.icv, "mode": d.mode, "status": d.status, "attempts": d.attempts, "response": d.response or "",
                 "created": d.created, "sent_at": d.sent_at} for d in s.query(ZatcaDoc).order_by(ZatcaDoc.icv.desc()).limit(limit)]


def get_xml(doc_id):
    from .db import ZatcaDoc, get_session
    with get_session() as s:
        d = s.get(ZatcaDoc, int(doc_id))
        if not d:
            raise ValueError("المستند غير موجود")
        return d.number, d.xml


def retry_doc(doc_id):
    """إعادة محاولة يدوية (بتصفّر عدّاد المحاولات). المرفوض (rejected) ما بيتبعتش تاني لأن الهيئة رفضته - لازم إشعار دائن وإصدار جديد."""
    from .db import ZatcaDoc, get_session
    with get_session() as s:
        d = s.get(ZatcaDoc, int(doc_id))
        if not d:
            raise ValueError("المستند غير موجود")
        if d.status == "rejected":
            raise ValueError("الهيئة رفضت المستند ده - صحّح البيانات وأصدر إشعار دائن/فاتورة جديدة")
        d.attempts = 0
        s.commit()
    return send_doc(int(doc_id))
