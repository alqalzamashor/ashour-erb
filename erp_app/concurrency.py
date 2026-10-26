"""تشغيل معالجات أحداث الواجهة المتزامنة في خيوط بدل خيط الـ event loop المشترك.
المشكلة: Flet بينفّذ كل handler متزامن على نفس الخيط اللي بيخدم كل المستخدمين، فتقرير تقيل عند مستخدم بيوقف الباقي لحد ما يخلص.
الحل: handler المتزامن بيشتغل في ThreadPool (بسياق صفحة المستخدم)، ومعالجات نفس الجلسة بتتنفّذ بالترتيب (قفل لكل جلسة)
بينما جلسات المستخدمين المختلفين بتشتغل بالتوازي. ERP_THREAD_HANDLERS=0 يرجّع السلوك القديم، ERP_WORKERS عدد الخيوط (24).
بيحسب كمان تأخير الـ loop (loop lag) ويعرضه في /healthz للمراقبة. مربوط بإصدار Flet المثبّت (0.86.5)، وبيتجاهل نفسه مع أي إصدار تاني."""
import asyncio
import collections
import contextvars
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

ENABLED = os.environ.get("ERP_THREAD_HANDLERS", "1") not in ("0", "false", "no")
WORKERS = int(os.environ.get("ERP_WORKERS", "24"))
SUPPORTED = "0.86.5"

_pool = None
_lags = collections.deque(maxlen=1200)       # آخر ~دقيقتين (عينة كل 0.1ث)
_state = {"installed": False, "mode": "loop", "busy": 0, "total": 0, "monitor": False, "max_lag": 0.0, "slow": 0}
_slow_ms = float(os.environ.get("ERP_SLOW_HANDLER_MS", "2000"))
_lock = threading.Lock()


def _executor():
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="erp-h")
    return _pool


async def _monitor():
    while True:
        t = time.perf_counter()
        await asyncio.sleep(0.1)
        lag = max(0.0, (time.perf_counter() - t - 0.1) * 1000)
        _lags.append(lag)
        if lag > _state["max_lag"]:
            _state["max_lag"] = lag


def stats():
    s = sorted(_lags)
    p95 = s[int(len(s) * 0.95) - 1] if len(s) >= 20 else (s[-1] if s else 0.0)
    return {"mode": _state["mode"], "workers": WORKERS if _state["mode"] == "threads" else 0, "busy_handlers": _state["busy"],
            "handlers_total": _state["total"], "slow_handlers": _state["slow"], "loop_lag_p95_ms": round(p95, 1),
            "loop_lag_max_ms": round(_state["max_lag"], 1)}


def install(force=None):
    """يركّب التعديل على BaseControl._trigger_event. بيرجّع الوضع الفعلي ('threads' أو 'loop')."""
    if _state["installed"]:
        return _state["mode"]
    import flet as ft
    from flet.controls.base_control import BaseControl
    from flet.controls.context import _context_page, context
    from flet.controls.control_event import ControlEvent, get_event_field_type
    from flet.utils.from_dict import from_dict
    from flet.utils.object_model import get_param_count
    import inspect
    use_threads = ENABLED if force is None else force
    _state["installed"] = True
    if ft.__version__ != SUPPORTED:
        return "loop"
    orig = BaseControl._trigger_event

    async def _trigger_event(self, event_name, event_data, e=None):
        try:
            pg = self.page
            if pg is not None:
                pg._erp_last_active = time.time()
        except Exception:      # noqa: BLE001
            pass
        if not _state["monitor"]:
            _state["monitor"] = True
            asyncio.get_running_loop().create_task(_monitor())
        field_name = f"on_{event_name}"
        handler = getattr(self, field_name, None)
        plain = (handler is not None and callable(handler) and not inspect.iscoroutinefunction(handler) and not inspect.isasyncgenfunction(handler)
                 and not inspect.isgeneratorfunction(handler))
        if not (use_threads and plain):
            _state["total"] += 1
            if use_threads and handler is None and self.page is not None:
                # أحداث داخلية من Flet (مثلاً app_lifecycle_state_change) مالهاش handler لكن بتعمل auto-update للصفحة كلها؛
                # لو اتنفّذت أثناء handler شغّال في خيط ممكن تقارن الصفحة وهي نص-متعدّلة (جدول أعمدته غير صفوفه) وتفشل -> نستناها بنفس قفل الجلسة
                session = self.page.session
                lk = getattr(session, "_erp_lock", None)
                if lk is None:
                    lk = session._erp_lock = asyncio.Lock()
                async with lk:
                    return await orig(self, event_name, event_data, e)
            return await orig(self, event_name, event_data, e)
        event_type = get_event_field_type(self, field_name)
        if event_type is None:
            return
        if e is None:
            if event_type == ControlEvent or not isinstance(event_data, dict):
                e = ControlEvent(control=self, name=event_name, data=event_data)
            else:
                e = from_dict(event_type, {"control": self, "name": event_name, **(event_data or {})})
        handle_event = self.before_event(e)
        if not (handle_event is None or handle_event):
            return
        _context_page.set(self.page)
        context.reset_auto_update()
        if not self.page:
            raise RuntimeError("Control must be added to a page before triggering events.")
        session = self.page.session
        ctx = contextvars.copy_context()
        n = get_param_count(handler)
        call = (lambda: handler()) if n == 0 else (lambda: handler(e))
        lk = getattr(session, "_erp_lock", None)
        if lk is None:
            lk = session._erp_lock = asyncio.Lock()
        loop = asyncio.get_running_loop()
        async with lk:
            _state["busy"] += 1
            _state["total"] += 1
            t0 = time.perf_counter()
            try:
                await loop.run_in_executor(_executor(), ctx.run, call)
            finally:
                _state["busy"] -= 1
                if (time.perf_counter() - t0) * 1000 > _slow_ms:
                    _state["slow"] += 1
        await asyncio.create_task(session.after_event(session.index.get(self._i)), context=ctx)

    BaseControl._trigger_event = _trigger_event
    _state["mode"] = "threads" if use_threads else "loop"
    return _state["mode"]
