"""دورة الموافقات: عمليات حساسة (مشتريات كبيرة، سندات صرف كبيرة، تسويات جرد كبيرة، بيع آجل فوق حد الائتمان) لازم موافقة مدير قبل التنفيذ.
الطريقة: المنفّذ يجرّب العملية → النظام يرفض برسالة ApprovalRequired → المنفّذ يبعت طلب موافقة → المعتمِد (صلاحية approvals:approve) يوافق أو يرفض →
المنفّذ يعيد نفس العملية فالنظام يطابقها بالبصمة والمبلغ ويستهلك الموافقة مرة واحدة (بتنتهي بعد expiry_hours).
مين عنده صلاحية الاعتماد بيعدّي مباشرة (ويتسجّل في التدقيق). المنفّذ مينفعش يعتمد طلب نفسه."""
import datetime
import json
import os

from . import audit
from .db import APP_DIR, ApprovalRequest, get_session

CFG_PATH = os.path.join(APP_DIR, "approvals.json")
KINDS = {"purchase_invoice": "فاتورة مشتريات", "payment_voucher": "سند صرف", "inventory_adjustment": "تسوية جرد", "credit_limit": "بيع آجل فوق حد الائتمان"}
DEFAULTS = {"expiry_hours": 48, "kinds": {"purchase_invoice": {"enabled": False, "threshold": 10000.0}, "payment_voucher": {"enabled": False, "threshold": 5000.0},
                                          "inventory_adjustment": {"enabled": False, "threshold": 2000.0}}}
STATUS = {"pending": "بانتظار الموافقة", "approved": "معتمد (لم يُنفَّذ)", "rejected": "مرفوض", "consumed": "اتنفّذ", "cancelled": "ملغى"}


class ApprovalRequired(ValueError):
    def __init__(self, kind, amount, fingerprint, summary=""):
        self.approval = {"kind": kind, "amount": float(amount), "fingerprint": fingerprint, "summary": summary}
        super().__init__(f"{KINDS.get(kind, kind)} بقيمة {float(amount):,.2f} محتاجة موافقة مدير" + (f" ({summary})" if summary else ""))


def get_config():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            d = json.load(f)
        cfg["expiry_hours"] = d.get("expiry_hours", cfg["expiry_hours"])
        for k, v in (d.get("kinds") or {}).items():
            cfg["kinds"].setdefault(k, {}).update(v)
    except Exception:
        pass
    return cfg


@audit.audited_config("إعدادات الموافقات")
def save_config(**kw):
    from . import services
    services.require_action("approvals", "edit")
    cfg = get_config()
    if "expiry_hours" in kw:
        cfg["expiry_hours"] = int(kw["expiry_hours"])
        if not 1 <= cfg["expiry_hours"] <= 720:
            raise ValueError("مدة صلاحية الموافقة من 1 إلى 720 ساعة")
    for k, v in (kw.get("kinds") or {}).items():
        if k not in DEFAULTS["kinds"]:
            raise ValueError("نوع غير معروف")
        thr = float(v.get("threshold", cfg["kinds"][k]["threshold"]))
        if thr < 0:
            raise ValueError("الحد لا يكون سالبًا")
        cfg["kinds"][k] = {"enabled": bool(v.get("enabled")), "threshold": thr}
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return cfg


def needs_approval(kind, amount):
    if kind == "credit_limit":
        return True
    k = get_config()["kinds"].get(kind) or {}
    return bool(k.get("enabled")) and float(amount or 0) >= float(k.get("threshold", 0)) - 1e-9


def _me():
    from . import services
    u = services.current_user() or {}
    return u.get("username") or ""


def _can_approve():
    from . import services
    return services.user_has_action(services._get_user(), "approvals", "approve")


def guard(kind, amount, fingerprint, summary="", approval_id=None, force=False):
    """يتنادى قبل العملية الحساسة. بيرجّع None (مش مطلوب) أو id الموافقة المستهلكة، أو يرمي ApprovalRequired."""
    if not force and not needs_approval(kind, amount):
        return None
    amount = float(amount or 0)
    if _can_approve():
        audit.log_event("approval_bypass", label=f"{KINDS.get(kind, kind)} {amount:,.2f} (معتمِد)", changes=summary)
        return 0
    exp = datetime.datetime.now() - datetime.timedelta(hours=get_config()["expiry_hours"])
    with get_session() as s:
        q = s.query(ApprovalRequest).filter(ApprovalRequest.kind == kind, ApprovalRequest.status == "approved", ApprovalRequest.requested_by == _me(),
                                            ApprovalRequest.decided_at >= exp, ApprovalRequest.amount >= amount - 0.005)
        q = q.filter(ApprovalRequest.id == int(approval_id)) if approval_id else q.filter(ApprovalRequest.fingerprint == fingerprint)
        r = q.order_by(ApprovalRequest.id).first()
        if r:
            r.status = "consumed"; r.consumed_at = datetime.datetime.now(); s.commit()
            audit.log_event("approval_used", label=f"موافقة #{r.id} ({KINDS.get(kind, kind)})", changes=f"{amount:,.2f} - اعتمدها {r.decided_by}")
            return r.id
    raise ApprovalRequired(kind, amount, fingerprint, summary)


def request(kind, amount, fingerprint, summary="", note=""):
    if kind not in KINDS:
        raise ValueError("نوع الموافقة غير معروف")
    me = _me()
    if not me:
        raise PermissionError("سجّل الدخول الأول")
    with get_session() as s:
        ex = s.query(ApprovalRequest).filter(ApprovalRequest.kind == kind, ApprovalRequest.requested_by == me, ApprovalRequest.fingerprint == fingerprint,
                                             ApprovalRequest.status.in_(["pending", "approved"])).first()
        if ex:
            return ex.id
        r = ApprovalRequest(kind=kind, fingerprint=fingerprint, amount=float(amount or 0), summary=(summary or "")[:500], requested_by=me, note=(note or "")[:300])
        s.add(r); s.commit()
        return r.id


def _decide(rid, status, note):
    from . import services
    services.require_action("approvals", "approve")
    with get_session() as s:
        r = s.get(ApprovalRequest, int(rid))
        if not r or r.status != "pending":
            raise ValueError("الطلب مش بانتظار قرار")
        if r.requested_by == _me():
            raise PermissionError("مينفعش تعتمد أو ترفض طلب قدّمته بنفسك")
        if status == "rejected" and not (note or "").strip():
            raise ValueError("اكتب سبب الرفض")
        r.status = status; r.decided_by = _me(); r.decided_at = datetime.datetime.now(); r.decision_note = (note or "")[:300]
        s.commit()


def approve(rid, note=""):
    _decide(rid, "approved", note)


def reject(rid, note):
    _decide(rid, "rejected", note)


def cancel(rid):
    with get_session() as s:
        r = s.get(ApprovalRequest, int(rid))
        if not r or r.requested_by != _me() or r.status not in ("pending", "approved"):
            raise ValueError("مينفعش إلغاء الطلب ده")
        r.status = "cancelled"; s.commit()


def list_requests(scope="pending", limit=200):
    """scope: pending (كل المعلّق - للمعتمِدين) | mine (طلباتي) | all."""
    with get_session() as s:
        q = s.query(ApprovalRequest)
        if scope == "pending":
            q = q.filter(ApprovalRequest.status == "pending")
        elif scope == "mine":
            q = q.filter(ApprovalRequest.requested_by == _me())
        rows = q.order_by(ApprovalRequest.id.desc()).limit(limit).all()
        s.expunge_all()
        return rows


def pending_count():
    with get_session() as s:
        return s.query(ApprovalRequest).filter(ApprovalRequest.status == "pending").count()
