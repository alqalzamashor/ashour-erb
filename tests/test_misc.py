import datetime
import json

import pytest

from erp_app import audit, data_integrity, scale_barcode
from erp_app.db import AuditLog, JournalEntry, JournalEntryLine, get_session


def _ean13(first12):
    d = [int(c) for c in first12]
    chk = (10 - (sum(d[0::2]) + 3 * sum(d[1::2])) % 10) % 10
    return first12 + str(chk)


def test_weighted_barcode_parse(S):
    scale_barcode.save_config(enabled=True, prefix="20", plu_len=5, value_len=5, kind="weight", check_digit=True)
    ok = scale_barcode.parse("2000123008509")
    assert ok and ok["value"] == pytest.approx(0.85) and ok["plu"] == "00123"
    assert scale_barcode.parse("2000123008508") is None            # رقم تحقق غلط
    assert scale_barcode.parse("1234567890128") is None            # بادئة مختلفة


def test_scan_lookup_weighted_product(S):
    scale_barcode.save_config(enabled=True, prefix="20", plu_len=5, value_len=5, kind="weight", check_digit=True)
    pid = S.create_product("00123", "جبنة", sale_price=40, product_type="service")
    r = S.scan_lookup("2000123008509")
    assert r["kind"] == "weight" and r["qty"] == pytest.approx(0.85) and r["product"].id == pid
    assert S.scan_lookup("9999999999999") is None                  # باركود غير معروف
    with pytest.raises(ValueError):
        S.scan_lookup(_ean13("209999900850"))                       # باركود موزون صحيح لصنف غير موجود


def test_config_and_bulk_events_are_audited(S):
    scale_barcode.save_config(prefix="21")
    with get_session() as s:
        rows = s.query(AuditLog).filter(AuditLog.action == "config").all()
        assert any(json.loads(r.changes).get("prefix") == ["20", "21"] for r in rows)
    scale_barcode.save_config(prefix="20")


def test_audit_masks_password_changes(S):
    uid = S.create_user("masked", "a-password", "م", "viewer")
    S.update_user(uid, password="another-password")
    with get_session() as s:
        rows = [r for r in s.query(AuditLog).filter(AuditLog.table_name == "users", AuditLog.action == "update").all() if "password_hash" in (r.changes or "")]
    assert rows and all("another-password" not in r.changes and "pbkdf2" not in r.changes for r in rows)


def test_integrity_detects_injected_errors(S, shop):
    with get_session() as s:
        je = JournalEntry(number="BAD-1", source_type="manual"); s.add(je); s.flush()
        s.add(JournalEntryLine(entry_id=je.id, account_id=1, debit=100, credit=0))
        s.add(JournalEntry(number="EMPTY-1"))
        s.commit()
    r = {c["key"]: c["count"] for c in data_integrity.run()["checks"]}
    assert r["unbalanced"] >= 1 and r["empty_entries"] >= 1 and r["trial_balance"] == 1


def test_backup_restore_roundtrip(S, shop, tmp_path):
    from erp_app import backup
    from erp_app.db import Product
    b = backup.backup_now("manual")
    assert backup._check(b["path"])
    S.create_product("ZZ", "بعد النسخة", sale_price=1)
    backup.restore_backup(b["name"])
    with get_session() as s:
        assert s.query(Product).filter(Product.sku == "ZZ").count() == 0


def test_cleanup_clears_transactions_keeps_master(S, shop):
    from erp_app import data_cleanup
    from erp_app.db import Customer, SalesInvoice
    rep = data_cleanup.cleanup(master=False, extras=False, other_users=False, delete_files=False, backup=False, confirm=data_cleanup.CONFIRM_PHRASE, enforce_admin=False)
    assert rep["total_deleted"] > 0
    with get_session() as s:
        assert s.query(SalesInvoice).count() == 0 and s.query(Customer).count() > 0
