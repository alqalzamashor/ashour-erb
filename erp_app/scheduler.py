"""مجدول المهام الدورية على مستوى السيرفر (مرة واحدة لكل عملية، بدون الاعتماد على وجود مستخدم فاتح المتصفح):
النسخ الاحتياطي التلقائي والرفع الخارجي، التقارير المجدولة بالبريد، إعادة الرسائل الفاشلة وتنبيه نقص المخزون،
الملخص اليومي للتنبيهات الذكية، ترحيل المصروفات المقدمة، وتنظيف الملفات المؤقتة (روابط التنزيل والرفع)."""
import datetime
import threading
import time
import traceback

_state = {"started": False, "tasks": {}}
_lock = threading.Lock()
TICK = 15


def _backup():
    from . import backup
    return backup.auto_backup_if_due()


def _reports():
    from . import scheduled_reports
    return scheduled_reports.run_due()


def _notify():
    from . import notify
    return notify.run_due()


def _alerts():
    from . import alerts
    return alerts.run_due()


def _zatca():
    from . import zatca_p2
    return zatca_p2.send_pending()


def _drill():
    from . import restore_drill
    return restore_drill.run_due()


def _prepaid():
    from . import services
    return services.auto_post_prepaid_expenses()


def _journal_recurring():
    from . import journal_tools
    return len(journal_tools.run_due_recurrences())


def _cleanup():
    from . import files, thermal
    n = files.cleanup()
    try:
        n += thermal.purge_jobs()
    except Exception:      # noqa: BLE001
        pass
    return n


# (الاسم، الدالة، كل كام ثانية، تأخير أول تشغيل)
TASKS = [("backup", _backup, 1800, 30), ("reports", _reports, 300, 20), ("notify", _notify, 600, 45), ("alerts", _alerts, 600, 60), ("drill", _drill, 3600, 120), ("zatca", _zatca, 120, 50), ("prepaid", _prepaid, 6 * 3600, 90), ("journal_recurring", _journal_recurring, 1800, 100), ("cleanup", _cleanup, 900, 10)]


def run_task(name):
    """يشغّل مهمة واحدة الآن (للاختبارات والإدارة) ويسجّل نتيجتها."""
    fn = next(f for n, f, _, _ in TASKS if n == name)
    t = _state["tasks"].setdefault(name, {})
    try:
        res = fn()
        t.update(last=datetime.datetime.now().isoformat(timespec="seconds"), ok=True, error=None)
        return res
    except Exception as ex:      # noqa: BLE001 - المجدول ما يقعش بسبب مهمة
        t.update(last=datetime.datetime.now().isoformat(timespec="seconds"), ok=False, error=f"{type(ex).__name__}: {ex}"[:300])
        traceback.print_exc()
        return None


def status():
    return {k: dict(v) for k, v in _state["tasks"].items()}


def _loop():
    t0 = time.time()
    due = {n: t0 + delay for n, _, _, delay in TASKS}
    while True:
        now = time.time()
        for name, _, every, _ in TASKS:
            if now >= due[name]:
                run_task(name)
                due[name] = time.time() + every
        time.sleep(TICK)


def start():
    """يبدأ الخيط الخلفي مرة واحدة لكل عملية. بيرجّع True لو بدأ فعلاً."""
    with _lock:
        if _state["started"]:
            return False
        _state["started"] = True
    threading.Thread(target=_loop, name="erp-scheduler", daemon=True).start()
    return True
