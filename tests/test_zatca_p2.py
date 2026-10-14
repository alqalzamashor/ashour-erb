"""ZATCA المرحلة الثانية (اختبار داخلي بشهادة ذاتية التوقيع - مش اختبار قبول من الهيئة): XML، سلسلة الهاش، التوقيع، QR، وكشف أي تعديل."""
import base64
import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from lxml import etree

from erp_app import zatca_p2 as z

VAT = "399999999900003"


@pytest.fixture(scope="module")
def creds():
    key = ec.generate_private_key(ec.SECP256K1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TEST-CA")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(123456789)
            .not_valid_before(datetime.datetime(2024, 1, 1)).not_valid_after(datetime.datetime(2034, 1, 1)).sign(key, hashes.SHA256()))
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()).decode()
    return pem, base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode()


CFG = dict(z.DEFAULTS)
SELLER = {"name": "شركة اختبار", "vat": VAT, "id": "1010010000", "scheme": "CRN", "street": "Prince Sultan", "building": "1234", "district": "Olaya", "city": "Riyadh", "postal": "12345"}


def _doc(kind="invoice", std=False, items=None):
    cust = {"name": "عميل", "vat": "399999999800003", "crn": "1010", "street": "S", "building": "1111", "district": "D", "city": "C", "postal": "54321"} if std else {}
    return {"kind": kind, "number": "S-0001", "uuid": "8e6000cf-1a98-4174-b3e7-b5d5954bc10d", "when": datetime.datetime(2026, 10, 11, 14, 30, 5),
            "items": items or [{"name": "برجر & كولا <٢>", "qty": 3, "gross": 34.5, "rate": 15}, {"name": "ماء", "qty": 1, "gross": 5.0, "rate": 15}],
            "customer": cust, "pay_code": "10", "ref_number": "S-0000", "reason": "مرتجع"}


def _sign(creds, **kw):
    body, summ = z.build_body(_doc(**kw), 7, z.INITIAL_PIH, CFG, SELLER)
    return z.sign_document(body, summ, creds[0], creds[1], "شركة اختبار", VAT, "2026-10-11T11:30:05Z"), summ


def test_initial_pih_constant():
    assert z.INITIAL_PIH == "NWZlY2ViNjZmZmM4NmYzOGQ5NTI3ODZjNmQ2OTZjNzljMmRiYzIzOWRkNGU5MWI0NjcyOWQ3M2EyN2ZiNTdlOQ=="


@pytest.mark.parametrize("kind,std", [("invoice", False), ("invoice", True), ("credit", False), ("debit", True)])
def test_sign_and_self_verify(creds, kind, std):
    (xml, h, qr), summ = _sign(creds, kind=kind, std=std)
    assert z.verify_document(xml) == []
    root = etree.fromstring(xml.encode())
    ns = {"cbc": z.NS["cbc"], "cac": z.NS["cac"]}
    assert root.xpath("//cbc:InvoiceTypeCode/@name", namespaces=ns)[0] == ("0100000" if std else "0200000")
    assert root.xpath("//cbc:InvoiceTypeCode/text()", namespaces=ns)[0] == {"invoice": "388", "credit": "381", "debit": "383"}[kind]
    assert bool(root.xpath("//cac:BillingReference", namespaces=ns)) == (kind != "invoice")
    assert bool(root.xpath("//cac:Delivery", namespaces=ns)) == std
    assert root.xpath("//cac:AdditionalDocumentReference[cbc:ID='ICV']/cbc:UUID/text()", namespaces=ns) == ["7"]
    tags = z.parse_tlv(qr)
    assert tags[1].decode() == "شركة اختبار" and tags[2].decode() == VAT and tags[3].decode() == "2026-10-11T14:30:05"
    assert tags[4].decode() == "39.50" and tags[5].decode() == "5.15" and tags[6].decode() == h
    assert len(tags[8]) > 60 and len(tags[9]) > 60


def test_totals_consistent(creds):
    (xml, _, _), summ = _sign(creds, items=[{"name": "a", "qty": 3, "gross": 10.0, "rate": 15}, {"name": "b", "qty": 7, "gross": 0.99, "rate": 15}])
    root = etree.fromstring(xml.encode())
    ns = {"cbc": z.NS["cbc"], "cac": z.NS["cac"]}
    ext = float(root.xpath("//cac:LegalMonetaryTotal/cbc:LineExtensionAmount/text()", namespaces=ns)[0])
    tax = float(root.xpath("/*/cac:TaxTotal[1]/cbc:TaxAmount/text()", namespaces=ns)[0])
    incl = float(root.xpath("//cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount/text()", namespaces=ns)[0])
    lines_net = sum(float(x) for x in root.xpath("//cac:InvoiceLine/cbc:LineExtensionAmount/text()", namespaces=ns))
    lines_tax = sum(float(x) for x in root.xpath("//cac:InvoiceLine/cac:TaxTotal/cbc:TaxAmount/text()", namespaces=ns))
    assert abs(ext - lines_net) < 1e-9 and abs(tax - lines_tax) < 1e-9 and abs(incl - (ext + tax)) < 1e-9


def test_tamper_detected(creds):
    (xml, _, _), _ = _sign(creds)
    assert z.verify_document(xml.replace("<cbc:IssueDate>2026-10-11", "<cbc:IssueDate>2026-10-12")) != []
    assert z.verify_document(xml.replace("34.50", "1.00")) != [] or "34.50" not in xml
    assert any("SignedProperties" in p or "توقيع" in p for p in z.verify_document(xml.replace("11:30:05Z", "11:30:06Z")))


def test_hash_ignores_extensions_qr_signature_whitespace_stable(creds):
    (xml, h, _), _ = _sign(creds)
    raw, b64 = z.invoice_hash(xml)
    assert b64 == h
    # تغيير قيمة QR أو التوقيع ما بيغيّرش هاش الفاتورة
    assert z.invoice_hash(xml.replace("<cbc:SignatureMethod>urn:oasis:names:specification:ubl:dsig:enveloped:xades</cbc:SignatureMethod>", "<cbc:SignatureMethod>x</cbc:SignatureMethod>"))[1] == h


def test_zero_rate_requires_reason(creds):
    with pytest.raises(z.ZatcaError, match="إعفاء"):
        z.build_body(_doc(items=[{"name": "x", "qty": 1, "gross": 10, "rate": 0}]), 1, z.INITIAL_PIH, CFG, SELLER)
    body, _ = z.build_body(_doc(items=[{"name": "x", "qty": 1, "gross": 10, "rate": 0}]), 1, z.INITIAL_PIH, {**CFG, "zero_rate_code": "VATEX-SA-32", "zero_rate_text": "Export"}, SELLER)
    assert "VATEX-SA-32" in body and ">Z<" in body


def test_csr_shape():
    key_pem, csr_pem = z.generate_csr(VAT, "شركة اختبار", "sandbox", "فرع", "ERP-1", "1100", "Riyadh")
    csr = x509.load_pem_x509_csr(csr_pem.encode())
    assert csr.is_signature_valid
    assert csr.subject.get_attributes_for_oid(NameOID.COUNTRY_NAME)[0].value == "SA"
    assert csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value.startswith("TST-")
    tmpl = csr.extensions.get_extension_for_oid(x509.ObjectIdentifier("1.3.6.1.4.1.311.20.2")).value.value
    assert b"TSTZATCA-Code-Signing" in tmpl
    san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DirectoryName)[0]
    assert san.get_attributes_for_oid(NameOID.USER_ID)[0].value == VAT and san.get_attributes_for_oid(NameOID.TITLE)[0].value == "1100"
    with pytest.raises(z.ZatcaError):
        z.generate_csr("123", "x", "sandbox")


# ---------------------------------------------------------------- تكامل مع النظام (فواتير حقيقية بقاعدة الاختبار)
@pytest.fixture()
def enabled(S, creds, tmp_path, monkeypatch):
    monkeypatch.setattr(z, "CFG_PATH", str(tmp_path / "zp2.json"))
    monkeypatch.setattr(z, "SYNC", True)
    S.update_company_settings(name="شركة اختبار", vat_number=VAT)
    z.save_config(enabled=True, crn="1010010000", street="Prince Sultan", building="1234", district="Olaya", city="Riyadh", postal="12345", private_key_pem=creds[0],
                  production={"request_id": "1", "token": "t", "secret": "s", "cert_b64": creds[1]})
    sent = []

    def fake_api(path, env, body=None, headers=None, auth=None, method="POST", timeout=30):
        sent.append((path, headers, auth, body))
        status = "REPORTED" if "reporting" in path else "CLEARED"
        return 200, {"reportingStatus": status, "clearanceStatus": status, "validationResults": {"status": "PASS", "errorMessages": [], "warningMessages": []}}
    monkeypatch.setattr(z, "_api", fake_api)
    return sent


def test_invoice_chain_and_reporting(S, shop, enabled):
    from erp_app.db import SalesInvoice, ZatcaDoc, get_session
    r1 = S.create_pos_sale(shop["cust"], [{"product_id": shop["burger"], "quantity": 2, "unit_price": 100}], payment_method_id=1, terminal_id=shop["term"])
    r2 = S.create_pos_sale(shop["cust"], [{"product_id": shop["cola"], "quantity": 3, "unit_price": 5}], payment_method_id=1, terminal_id=shop["term"])
    with get_session() as s:
        docs = s.query(ZatcaDoc).order_by(ZatcaDoc.icv).all()
        assert [d.icv for d in docs][-2:] == [docs[-2].icv, docs[-2].icv + 1]
        d1, d2 = docs[-2], docs[-1]
        assert d2.pih == d1.hash and d1.status == "reported" and d2.status == "reported"
        assert z.verify_document(d1.xml) == [] and z.verify_document(d2.xml) == []
        assert s.get(SalesInvoice, r1["invoice_id"]).zatca_status == "sent"
    assert r1["zatca"]["status"] == "sent"
    assert any(p == "/invoices/reporting/single" and h.get("Clearance-Status") == "0" for p, h, a, b in enabled)
    from erp_app.zatca import build_zatca_base64
    assert z.qr_text_for_invoice(r1["invoice_id"]) and z.parse_tlv(z.qr_text_for_invoice(r1["invoice_id"]))[1].decode() == "شركة اختبار"
    assert r1["qr_png_base64"] and r1["qr_png_base64"] != r2["qr_png_base64"]


def test_credit_note_for_return(S, shop, enabled):
    from erp_app.db import ZatcaDoc, get_session
    r = S.create_pos_sale(shop["cust"], [{"product_id": shop["burger"], "quantity": 2, "unit_price": 100}], payment_method_id=1, terminal_id=shop["term"])
    S.create_full_sales_return(r["invoice_id"], "اختبار")
    with get_session() as s:
        cn = s.query(ZatcaDoc).filter_by(kind="credit").order_by(ZatcaDoc.icv.desc()).first()
        assert cn and cn.status == "reported" and z.verify_document(cn.xml) == []
        assert "<cbc:InvoiceTypeCode name=\"0200000\">381<" in cn.xml and "InstructionNote" in cn.xml


def test_failed_send_retries_with_backoff_and_rejection_final(S, shop, enabled, monkeypatch):
    from erp_app.db import ZatcaDoc, get_session
    calls = {"n": 0}

    def flaky(path, env, body=None, headers=None, auth=None, method="POST", timeout=30):
        calls["n"] += 1
        raise z.ZatcaError("no internet")
    monkeypatch.setattr(z, "_api", flaky)
    r = S.create_pos_sale(shop["cust"], [{"product_id": shop["cola"], "quantity": 1, "unit_price": 5}], payment_method_id=1, terminal_id=shop["term"])
    assert r["zatca"]["status"] == "failed"
    with get_session() as s:
        d = s.query(ZatcaDoc).order_by(ZatcaDoc.icv.desc()).first(); did = d.id
        assert d.status == "failed" and d.attempts == 1
    assert z.send_pending() == 0                       # backoff: لسه بدري
    monkeypatch.setattr(z, "_api", lambda *a, **k: (200, {"reportingStatus": "REPORTED"}))
    assert z.retry_doc(did) == "reported"
    # رفض نهائي
    monkeypatch.setattr(z, "_api", lambda *a, **k: (400, {"validationResults": {"errorMessages": [{"code": "X", "message": "bad"}]}}))
    r2 = S.create_pos_sale(shop["cust"], [{"product_id": shop["cola"], "quantity": 1, "unit_price": 5}], payment_method_id=1, terminal_id=shop["term"])
    with get_session() as s:
        d2 = s.query(ZatcaDoc).order_by(ZatcaDoc.icv.desc()).first()
        assert d2.status == "rejected" and "bad" in d2.response
    with pytest.raises(ValueError):
        z.retry_doc(d2.id)


def test_disabled_changes_nothing(S, shop, tmp_path, monkeypatch):
    monkeypatch.setattr(z, "CFG_PATH", str(tmp_path / "none.json"))
    from erp_app.db import ZatcaDoc, get_session
    with get_session() as s:
        before = s.query(ZatcaDoc).count()
    r = S.create_pos_sale(shop["cust"], [{"product_id": shop["cola"], "quantity": 1, "unit_price": 5}], payment_method_id=1, terminal_id=shop["term"])
    assert r["zatca"]["status"] == "disabled" and r["qr_png_base64"]
    with get_session() as s:
        assert s.query(ZatcaDoc).count() == before


def test_zero_rate_failure_does_not_break_sale(S, shop, enabled):
    pid = S.create_product("Z0", "معفى", sale_price=10, cost_price=1, tax_rate=0, product_type="service")
    r = S.create_pos_sale(shop["cust"], [{"product_id": pid, "quantity": 1, "unit_price": 10, "tax_rate": 0}], payment_method_id=1, terminal_id=shop["term"])
    assert r["invoice_id"] and r["zatca"]["status"] == "failed" and "إعفاء" in r["zatca"]["message"]
    z.save_config(zero_rate_code="VATEX-SA-32", zero_rate_text="Export")
    assert z.issue_missing(days=1) >= 1


def test_standard_b2b_invoice_clearance(S, shop, enabled):
    from erp_app.db import ZatcaDoc, get_session
    cid = S.create_customer(name="شركة العميل", phone="0500000000", vat_number="399999999800003", address="الرياض", party_type="company",
                            crn="1010010001", building_no="4321", district="العليا", city="الرياض", postal_code="12211")
    iid = S.create_sales_invoice(cid, [{"product_id": shop["cola"], "quantity": 4, "unit_price": 5, "tax_rate": 15}])
    with get_session() as s:
        d = s.query(ZatcaDoc).filter_by(kind="invoice", ref_id=iid).one()
        assert d.mode == "standard" and d.status == "cleared" and z.verify_document(d.xml) == []
        assert "4321" in d.xml and "399999999800003" in d.xml and "ActualDeliveryDate" in d.xml
    assert any(p == "/invoices/clearance/single" and h.get("Clearance-Status") == "1" for p, h, a, b in enabled)
