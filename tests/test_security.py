import threading
import time
from unittest.mock import MagicMock

import pytest
from flet.controls.context import _context_page

from erp_app.db import SalesInvoice, User, get_session


def test_password_hash_salted_and_legacy_upgrade(S):
    import hashlib
    a, b = S._hash_password("x"), S._hash_password("x")
    assert a != b and a.startswith("pbkdf2$") and S._verify_password("x", a) and not S._verify_password("y", a)
    S.create_user("legacy", "ignored", "قديم", "viewer")
    with get_session() as s:
        s.query(User).filter(User.username == "legacy").first().password_hash = hashlib.sha256(b"oldpw").hexdigest()
        s.commit()
    assert S.authenticate_user("legacy", "oldpw")
    with get_session() as s:
        assert s.query(User).filter(User.username == "legacy").first().password_hash.startswith("pbkdf2$")


def test_login_lockout(S):
    S.create_user("lock1", "right-pw", "ق", "viewer")
    for _ in range(S.LOGIN_MAX_FAILS):
        assert S.authenticate_user("lock1", "wrong") is None
    with pytest.raises(ValueError, match="خاطئة"):
        S.authenticate_user("lock1", "right-pw")
    S._LOGIN_FAILS.clear()
    assert S.authenticate_user("lock1", "right-pw")


def test_default_admin_password_flag(S):
    assert S.is_default_admin_password() is True


def test_sessions_do_not_share_current_user(S):
    S.create_user("viewer1", "pw12345", "مشاهد", "viewer")
    out, bar = {}, threading.Barrier(2)

    def run(name, user, pw):
        _context_page.set(MagicMock())
        S.set_current_user(S.authenticate_user(user, pw))
        bar.wait(); time.sleep(0.1)
        out[name] = S.current_user()["username"]
        try:
            S.require_action("organization", "edit"); out[name + "_org"] = True
        except PermissionError:
            out[name + "_org"] = False
    ts = [threading.Thread(target=run, args=("a", "admin", "admin")), threading.Thread(target=run, args=("b", "viewer1", "pw12345"))]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert out == {"a": "admin", "a_org": True, "b": "viewer1", "b_org": False}


def test_concurrent_sales_get_unique_numbers(S, shop):
    admin = S.authenticate_user("admin", "admin")
    errs = []

    def w():
        S.bind_thread_user(admin)
        try:
            S.create_pos_sale(customer_id=shop["cust"], items=[{"product_id": shop["burger"], "quantity": 1, "unit_price": 100}], payment_method_id=1, terminal_id=shop["term"])
        except Exception as e:                       # noqa: BLE001
            errs.append(repr(e)[:120])
    ts = [threading.Thread(target=w) for _ in range(10)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert errs == []
    with get_session() as s:
        nums = [i.number for i in s.query(SalesInvoice).all()]
    assert len(nums) == len(set(nums))
