"""صلاحيات الحقول: إخفاء بيانات حساسة (سعر التكلفة وقيم المخزون، الأرباح والهوامش) عن مستخدمين/أدوار معينة.
التخزين: جوه صلاحيات المستخدم (JSON) تحت المفتاح "_hidden" = قايمة الحقول المخفية. الأدمن بيشوف كل حاجة دايمًا.
قاعدة "قايمة منع": مستخدم قديم ما عندوش "_hidden" بيفضل يشوف كل حاجة زي ما كان (مفيش تغيير مفاجئ).
الإخفاء مطبّق في الشاشات والتقارير والتصدير والاستيراد، ومحمي في الخدمات اللي بتعدّل التكلفة؛ أما الحسابات الداخلية (القيود وتكلفة المبيعات)
فبتشتغل بالقيم الحقيقية دايمًا. التغطية الكاملة والمواضع غير المغطاة مذكورة في README_AR."""
import json

FIELDS = {
    "cost_price": "سعر التكلفة وقيمة المخزون (الأصناف، رصيد المخزن، حركة الأصناف، وتصدير تقارير المخزون)",
    "profit": "الأرباح والهوامش (لوحة الإدارة، مقارنة الفترات، ترتيب الفروع)",
}
# افتراضي الأدوار عند إنشاء مستخدم جديد بدون تحديد صلاحيات
ROLE_DEFAULT_HIDDEN = {"sales": ["cost_price", "profit"], "inventory": ["profit"], "viewer": ["cost_price", "profit"]}
KEY = "_hidden"


def _user(user=None):
    if user is not None:
        return user
    from . import services
    return services._get_user()


def hidden_fields(user=None):
    u = _user(user)
    if not u:
        return set()
    role = u.get("role") if isinstance(u, dict) else u.role
    if role == "admin":
        return set()
    try:
        raw = u.get("permissions") if isinstance(u, dict) else u.permissions
        data = json.loads(raw or "{}")
    except Exception:
        return set()
    if not isinstance(data, dict):
        return set()
    return {f for f in (data.get(KEY) or []) if f in FIELDS}


def can_see(field, user=None):
    return field not in hidden_fields(user)


def require_visible(field, user=None):
    if not can_see(field, user):
        raise PermissionError(f"ليس لديك صلاحية الاطلاع على: {FIELDS.get(field, field)}")


def with_hidden(permissions, fields):
    """نسخة من قاموس الصلاحيات فيها قايمة الحقول المخفية (للاستخدام عند حفظ مستخدم)."""
    p = {k: v for k, v in (permissions or {}).items() if k != KEY}
    fields = [f for f in (fields or []) if f in FIELDS]
    if fields:
        p[KEY] = fields
    return p


def hidden_in(permissions):
    return [f for f in ((permissions or {}).get(KEY) or []) if f in FIELDS]


def mask_keys(rows, keys, value=None):
    """بيمسح مفاتيح معينة من قايمة قواميس (نسخ جديدة، مش بيعدّل الأصل)."""
    return [{k: (value if k in keys else v) for k, v in r.items()} for r in rows]
