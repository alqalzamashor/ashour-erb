"""مسودات النماذج (قيد / فاتورة...): حفظ تلقائي على السيرفر لكل مستخدم، عشان قطع الاتصال ما يضيّعش اللي اتكتب."""
import datetime
import json

from . import services as S
from .db import FormDraft, get_session

MAX_AGE_DAYS = 7
MAX_BYTES = 400_000


def _user():
    return S._current_username() or ""


def save(kind, data):
    """بيحفظ (أو يستبدل) مسودة المستخدم الحالي. بيرجّع True لو اتحفظ. أي خطأ بيتجاهل (الحفظ التلقائي مينفعش يكسر الشاشة)."""
    user = _user()
    if not user:
        return False
    try:
        raw = json.dumps(data, ensure_ascii=False, default=str)
        if len(raw) > MAX_BYTES:
            return False
        with get_session() as s:
            d = s.query(FormDraft).filter(FormDraft.username == user, FormDraft.kind == kind).first()
            if d is None:
                d = FormDraft(username=user, kind=kind)
                s.add(d)
            elif d.data == raw:
                return True
            d.data = raw
            d.updated_at = datetime.datetime.now()
            s.commit()
        return True
    except Exception:      # noqa: BLE001
        return False


def load(kind):
    """بيرجّع (data, updated_at) أو None. المسودة الأقدم من 7 أيام بتتمسح."""
    user = _user()
    if not user:
        return None
    try:
        with get_session() as s:
            d = s.query(FormDraft).filter(FormDraft.username == user, FormDraft.kind == kind).first()
            if d is None:
                return None
            if d.updated_at and (datetime.datetime.now() - d.updated_at).days >= MAX_AGE_DAYS:
                s.delete(d); s.commit()
                return None
            return json.loads(d.data), d.updated_at
    except Exception:      # noqa: BLE001
        return None


def clear(kind):
    user = _user()
    if not user:
        return
    try:
        with get_session() as s:
            s.query(FormDraft).filter(FormDraft.username == user, FormDraft.kind == kind).delete()
            s.commit()
    except Exception:      # noqa: BLE001
        pass
