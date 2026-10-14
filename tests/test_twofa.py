"""التحقق بخطوتين: TOTP (متجه RFC 6238)، تفعيل/دخول/أكواد استرداد/منع إعادة الاستخدام، الإلزام، تصفير المدير."""
import pytest

from erp_app import services, twofa


def test_rfc6238_vector():
    import base64
    sec = base64.b32encode(b"12345678901234567890").decode()
    assert twofa._code(sec, 59 // 30) == "287082"
    assert twofa.check(sec, "287082", at=59) == 1
    assert twofa.check(sec, "287082", last_step=1, at=59) is None        # مستخدم قبل كده
    assert twofa.check(sec, "000000", at=59) is None and twofa.check(sec, "12", at=59) is None


@pytest.fixture
def user(S):
    prev = services._get_user()
    uid = services.create_user("sec1", "Passw0rd!x", "مستخدم أمان", "user")
    services.set_current_user({"id": uid, "username": "sec1", "role": "user"})
    yield uid
    services.set_current_user(prev)
    services.delete_user(uid)


def test_enable_login_recovery(S, user, monkeypatch):
    services._LOGIN_FAILS.clear()
    d = twofa.begin_setup()
    assert d["uri"].startswith("otpauth://totp/") and len(d["qr"]) > 100
    with pytest.raises(ValueError):
        twofa.confirm_setup("000000")
    codes = twofa.confirm_setup(twofa.totp_now(d["secret"]))
    assert len(codes) == 8 and twofa.status()["enabled"]
    # دخول: من غير رمز
    with pytest.raises(twofa.OtpRequired):
        services.authenticate_user("sec1", "Passw0rd!x")
    # رمز غلط
    with pytest.raises(ValueError):
        services.authenticate_user("sec1", "Passw0rd!x", otp="123456")
    # الرمز اللي اتستخدم في التفعيل ما يتقبلش تاني (نفس الـ step)
    with pytest.raises(ValueError):
        # نفس الـ step المحفوظ (مش totp_now: لو عدّينا حدّ الـ30 ثانية بين السطرين كان الرمز بيبقى step جديد وبيتقبل)
        with services.get_session() as _s:
            _last = _s.query(services.User).filter_by(username="sec1").first().totp_last_step
        services.authenticate_user("sec1", "Passw0rd!x", otp=twofa._code(d["secret"], _last))
    # رمز الـ step الجاي صح
    import time
    nxt = twofa._code(d["secret"], int(time.time() // 30) + 1)
    assert services.authenticate_user("sec1", "Passw0rd!x", otp=nxt)["username"] == "sec1"
    # كود استرداد مرة واحدة
    assert services.authenticate_user("sec1", "Passw0rd!x", otp=codes[0])
    with pytest.raises(ValueError):
        services.authenticate_user("sec1", "Passw0rd!x", otp=codes[0])
    assert twofa.status()["recovery_left"] == 7
    # كلمة مرور غلط ما بتكشفش حاجة
    assert services.authenticate_user("sec1", "bad") is None
    # الموافقات (مدير) من غير رمز
    assert services.authenticate_user("sec1", "Passw0rd!x", second_factor=False)


def test_lockout_counts_bad_otp(S, user):
    services._LOGIN_FAILS.clear()
    d = twofa.begin_setup(); twofa.confirm_setup(twofa.totp_now(d["secret"]))
    for _ in range(services.LOGIN_MAX_FAILS):
        with pytest.raises(ValueError):
            services.authenticate_user("sec1", "Passw0rd!x", otp="111111")
    with pytest.raises(ValueError, match="محاولات"):
        services.authenticate_user("sec1", "Passw0rd!x", otp="111111")
    services._LOGIN_FAILS.clear()


def test_disable_and_admin_reset(S, user):
    d = twofa.begin_setup(); twofa.confirm_setup(twofa.totp_now(d["secret"]))
    with pytest.raises(ValueError):
        twofa.disable_self("wrong")
    twofa.disable_self("Passw0rd!x")
    assert not twofa.status()["enabled"]
    d = twofa.begin_setup(); twofa.confirm_setup(twofa.totp_now(d["secret"]))
    services.set_current_user(None)
    from erp_app.db import User, get_session
    with get_session() as s:
        admin = s.query(User).filter_by(username="admin").first()
        services.set_current_user({"id": admin.id, "username": "admin", "role": "admin", "permissions": admin.permissions or "{}", "branch_ids": "[]"})
    twofa.admin_reset(user)
    assert not twofa.is_enabled(user)


def test_required_for_admin(S, monkeypatch):
    monkeypatch.setenv("ERP_REQUIRE_2FA", "admin")
    from erp_app.db import User, get_session
    with get_session() as s:
        pw_ok = s.query(User).filter_by(username="admin").first()
    assert twofa.required_for("admin", "admin") and not twofa.required_for("user", "x")
    monkeypatch.setenv("ERP_REQUIRE_2FA", "all")
    assert twofa.required_for("user", "x")
    monkeypatch.delenv("ERP_REQUIRE_2FA")
    assert not twofa.required_for("admin", "admin")
