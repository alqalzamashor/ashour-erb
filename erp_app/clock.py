"""ساعة قابلة للتجاوز: بتخلّي services تشوف "النهارده/الآن" = وقت العملية الأصلي لما المركز بيعيد تنفيذ عملية اتسجّلت على نسخة فرع offline
(عشان الفاتورة تتسجّل بتاريخها الحقيقي مش بتاريخ وصولها). برّه with at(...) كل حاجة شغّالة زي datetime العادي بالظبط."""
import contextlib
import contextvars
import datetime as _dt

_ov = contextvars.ContextVar("erp_clock_override", default=None)


class _DateMeta(type(_dt.date)):
    def __instancecheck__(cls, o):
        return isinstance(o, _dt.date)

    def __subclasscheck__(cls, c):
        return issubclass(c, _dt.date)


class _DateTimeMeta(type(_dt.datetime)):
    def __instancecheck__(cls, o):
        return isinstance(o, _dt.datetime)

    def __subclasscheck__(cls, c):
        return issubclass(c, _dt.datetime)


class date(_dt.date, metaclass=_DateMeta):
    def __new__(cls, *a, **k):
        return _dt.date(*a, **k)

    @classmethod
    def today(cls):
        o = _ov.get()
        return o.date() if o is not None else _dt.date.today()


class datetime(_dt.datetime, metaclass=_DateTimeMeta):
    def __new__(cls, *a, **k):
        return _dt.datetime(*a, **k)

    @classmethod
    def now(cls, tz=None):
        o = _ov.get()
        if o is None:
            return _dt.datetime.now(tz)
        return o if tz is None else o.astimezone(tz)

    @classmethod
    def today(cls):
        return cls.now()

    @classmethod
    def utcnow(cls):
        o = _ov.get()
        return _dt.datetime.utcnow() if o is None else o


class _Module:
    """بديل لموديول datetime: نفس كل حاجة، بس date/datetime بيحترموا الساعة المتجاوزة."""
    date = date
    datetime = datetime

    def __getattr__(self, name):
        return getattr(_dt, name)


proxy = _Module()


@contextlib.contextmanager
def at(ts):
    """جوه البلوك: النهارده والآن = ts (datetime أو نص ISO)."""
    if isinstance(ts, str):
        ts = _dt.datetime.fromisoformat(ts)
    tok = _ov.set(ts)
    try:
        yield
    finally:
        _ov.reset(tok)
