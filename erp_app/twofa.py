"""التحقق بخطوتين (TOTP - RFC 6238) من غير مكتبات خارجية، متوافق مع Google/Microsoft Authenticator وAuthy وغيرهم.
أكواد الاسترداد (8 أكواد استخدام واحد) بتتخزن مشفّرة (SHA-256). الكود المستخدم مرة ما يتقبلش تاني (حماية من إعادة الإرسال).
ERP_REQUIRE_2FA = admin | all | (فاضي): إلزام المدير (أو الكل) بتفعيل التحقق بخطوتين قبل الدخول."""
import base64
import hashlib
import hmac
import io
import json
import os
import secrets
import struct
import time

from .db import User, get_session

STEP = 30
DIGITS = 6
ISSUER = "ERP"


class OtpRequired(Exception):
    """كلمة المرور صح لكن لازم رمز التحقق."""


def required_for(role, username=""):
    mode = (os.environ.get("ERP_REQUIRE_2FA") or "").strip().lower()
    return mode == "all" or (mode == "admin" and (role == "admin" or username == "admin"))


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret, counter):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 15
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** DIGITS).zfill(DIGITS)


def totp_now(secret, at=None):
    return _code(secret, int((at or time.time()) // STEP))


def check(secret, code, last_step=0, at=None, window=1):
    """بيرجّع رقم الـ step لو الرمز صح (±نافذة) ومش مستخدم قبل كده، وإلا None."""
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != DIGITS:
        return None
    cur = int((at or time.time()) // STEP)
    for st in range(cur - window, cur + window + 1):
        if st > (last_step or 0) and hmac.compare_digest(_code(secret, st), code):
            return st
    return None


def uri(username, secret, issuer=None):
    from urllib.parse import quote
    iss = quote(issuer or ISSUER)
    return f"otpauth://totp/{iss}:{quote(username)}?secret={secret}&issuer={iss}&digits={DIGITS}&period={STEP}"


def qr_base64(text):
    import qrcode
    img = qrcode.make(text, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _hash_rc(code):
    return hashlib.sha256(code.replace("-", "").strip().lower().encode()).hexdigest()


def _make_recovery(n=8):
    codes = []
    for _ in range(n):
        raw = "".join(secrets.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(10))
        codes.append(raw[:5] + "-" + raw[5:])
    return codes


def _current_id():
    from . import services
    u = services._get_user()
    if not u:
        raise PermissionError("سجّل الدخول أولًا")
    return int(u["id"] if isinstance(u, dict) else u.id)


def is_enabled(user_id):
    with get_session() as s:
        u = s.get(User, int(user_id))
        return bool(u and u.totp_enabled)


def status(user_id=None):
    uid = user_id or _current_id()
    with get_session() as s:
        u = s.get(User, int(uid))
        left = len(json.loads(u.recovery_codes or "[]")) if u and u.totp_enabled else 0
        return {"enabled": bool(u and u.totp_enabled), "recovery_left": left}


def begin_setup():
    """للمستخدم الحالي: بيولّد سر جديد (لسه مش مفعّل) ويرجّع السر والرابط وصورة QR."""
    uid = _current_id()
    with get_session() as s:
        u = s.get(User, uid)
        if u.totp_enabled:
            raise ValueError("التحقق بخطوتين مفعّل بالفعل")
        u.totp_secret = new_secret()
        u.totp_last_step = 0
        s.commit()
        link = uri(u.username, u.totp_secret, _issuer())
        return {"secret": u.totp_secret, "uri": link, "qr": qr_base64(link)}


def _issuer():
    try:
        from . import services
        return (services.get_company_settings().name or ISSUER)[:40].replace(":", " ")
    except Exception:      # noqa: BLE001
        return ISSUER


def confirm_setup(code):
    """بيتأكد من الرمز الأول ويفعّل ويرجّع أكواد الاسترداد (بتظهر مرة واحدة بس)."""
    from . import audit
    uid = _current_id()
    with get_session() as s:
        u = s.get(User, uid)
        if u.totp_enabled or not u.totp_secret:
            raise ValueError("ابدأ الإعداد الأول")
        st = check(u.totp_secret, code)
        if st is None:
            raise ValueError("الرمز غير صحيح - تأكد من وقت جهازك وجرّب الرمز الحالي")
        codes = _make_recovery()
        u.totp_enabled = True
        u.totp_last_step = st
        u.recovery_codes = json.dumps([_hash_rc(c) for c in codes])
        s.commit()
        name = u.username
    try:
        audit.log_event("update", label="تفعيل التحقق بخطوتين", changes=name)
    except Exception:      # noqa: BLE001
        pass
    return codes


def regenerate_recovery(password):
    from . import services
    uid = _current_id()
    with get_session() as s:
        u = s.get(User, uid)
        if not u.totp_enabled:
            raise ValueError("التحقق بخطوتين مش مفعّل")
        if not services._verify_password(password or "", u.password_hash):
            raise ValueError("كلمة المرور غير صحيحة")
        codes = _make_recovery()
        u.recovery_codes = json.dumps([_hash_rc(c) for c in codes])
        s.commit()
    return codes


def disable_self(password):
    from . import audit, services
    uid = _current_id()
    with get_session() as s:
        u = s.get(User, uid)
        if required_for(u.role, u.username):
            raise ValueError("التحقق بخطوتين إلزامي في هذا النظام")
        if not services._verify_password(password or "", u.password_hash):
            raise ValueError("كلمة المرور غير صحيحة")
        u.totp_enabled, u.totp_secret, u.recovery_codes, u.totp_last_step = False, None, None, 0
        s.commit()
        name = u.username
    try:
        audit.log_event("update", label="إيقاف التحقق بخطوتين", changes=name)
    except Exception:      # noqa: BLE001
        pass


def admin_reset(user_id):
    """المدير بيصفّر التحقق بخطوتين لمستخدم ضاع جهازه (يطلب صلاحية تعديل المستخدمين)."""
    from . import audit, services
    services.require_action("organization", "edit")
    with get_session() as s:
        u = s.get(User, int(user_id))
        if not u:
            raise ValueError("المستخدم غير موجود")
        u.totp_enabled, u.totp_secret, u.recovery_codes, u.totp_last_step = False, None, None, 0
        s.commit()
        name = u.username
    try:
        audit.log_event("update", label="تصفير التحقق بخطوتين", changes=name)
    except Exception:      # noqa: BLE001
        pass


def verify_login(u, otp):
    """جوه جلسة الدخول: بيقبل رمز TOTP أو كود استرداد (بيتحرق). بيرجّع True/False ويحدّث u."""
    otp = (otp or "").strip()
    if not otp:
        return False
    st = check(u.totp_secret or "", otp, u.totp_last_step)
    if st is not None:
        u.totp_last_step = st
        return True
    h = _hash_rc(otp)
    codes = json.loads(u.recovery_codes or "[]")
    if len(otp.replace("-", "")) == 10 and h in codes:
        codes.remove(h)
        u.recovery_codes = json.dumps(codes)
        return True
    return False
