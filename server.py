"""نقطة التشغيل الوحيدة للبرنامج: سيرفر ويب (نسخة سحابية فقط) - على سيرفر محلي في الفرع أو سيرفر بعيد (VPS / Docker / سحابة).
المستخدمون بيدخلوا من المتصفح فقط. كل الإعدادات بمتغيرات بيئة (أو أعلام سطر الأوامر):
  ERP_HOST=0.0.0.0        عنوان الاستماع            |  ERP_PORT=8552           بورت الواجهة
  ERP_INTERNAL_PORT=8600  بورت الـ API الداخلي (webhook التوصيل / وكيل الطباعة / healthz)
  ERP_DATABASE_URL=postgresql://user:pw@host:5432/erp   (الافتراضي SQLite داخل ERP_HOME)
  ERP_HOME=/var/lib/erp   مجلد البيانات (القاعدة/النسخ/الملفات)  |  ERP_ADMIN_PASSWORD=...  كلمة مرور المدير عند أول تشغيل
  ERP_UPLOAD_DIR / ERP_ASSETS_DIR / ERP_DOWNLOAD_TTL  (اختيارية)
شغّله خلف وكيل HTTPS (Caddy/nginx) لو على الإنترنت - اقرأ README_SERVER_AR.md."""
import argparse
import atexit
import os
import socket
import sys
for _s in (sys.stdout, sys.stderr):      # ويندوز: الإخراج لملف/أنبوب بيبقى cp1252 وبيفشل مع العربي
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:      # noqa: BLE001
        pass

os.environ.setdefault("FLET_FORCE_WEB_SERVER", "true")      # سيرفر ويب دايمًا، ومن غير فتح متصفح على السيرفر


def _lan_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127."))


def _acquire_lock(app_dir):
    """يمنع تشغيل نسختين على نفس مجلد البيانات (كل واحدة هتشغّل مجدول ومهام دورية، والجلسات داخل العملية)."""
    path = os.path.join(app_dir, "server.pid")
    if os.path.exists(path):
        try:
            old = int(open(path).read().strip() or 0)
            if old and old != os.getpid():
                from erp_app.proc import pid_alive
                if pid_alive(old):
                    raise SystemExit(f"فيه سيرفر شغّال بالفعل على نفس مجلد البيانات (PID {old}). أوقفه الأول.")
        except (ValueError, ProcessLookupError, PermissionError, OSError) as ex:
            if isinstance(ex, SystemExit):
                raise
    with open(path, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: os.path.exists(path) and open(path).read().strip() == str(os.getpid()) and os.remove(path))


def run(argv=None):
    ap = argparse.ArgumentParser(description="سيرفر نظام ERP")
    ap.add_argument("--host", default=os.environ.get("ERP_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("ERP_PORT", "8552")))
    a = ap.parse_args(argv)
    from erp_app import db, files, scheduler, services
    from main import init_db, main
    import flet as ft

    _acquire_lock(db.APP_DIR)
    files.ensure_fonts()
    files.ensure_secret_key()
    from erp_app import concurrency
    concurrency.install()
    init_db()
    from erp_app import nodesync
    if nodesync.is_node():
        n = nodesync.install()
        nodesync.start_background()
        print(f"نسخة فرع ({nodesync.node_id()}): تسجيل {n} نوع عملية للمزامنة مع {nodesync.hq_url() or '<ERP_HQ_URL غير مضبوط>'}")
    how, pw = services.bootstrap_admin(os.environ.get("ERP_ADMIN_PASSWORD", "").strip() or None, os.path.join(db.APP_DIR, "initial_admin_password.txt"))
    print("=" * 70)
    if how == "generated":
        print(f"أول تشغيل: اتولّدت كلمة مرور للمدير (admin):  {pw}")
        print("   اتحفظت كمان في:", os.path.join(db.APP_DIR, "initial_admin_password.txt"), "- غيّرها واحذف الملف.")
    elif how == "env":
        print("اتضبطت كلمة مرور المدير من ERP_ADMIN_PASSWORD.")
    print(f"قاعدة البيانات: {'PostgreSQL' if not db.IS_SQLITE else 'SQLite (' + db.DB_PATH + ')'}   |   مجلد البيانات: {db.APP_DIR}")
    print(f"السيرفر شغّال على {a.host}:{a.port}")
    if a.host in ("0.0.0.0", "::"):
        for ip in _lan_ips() or ["<عنوان-السيرفر>"]:
            print(f"   http://{ip}:{a.port}")
    print("للإنترنت: ضعه خلف HTTPS (Caddy/nginx/Cloudflare) - اقرأ README_SERVER_AR.md")
    try:
        from erp_app import delivery_server
        h = delivery_server.start()
        if h:
            print(f"API داخلي (webhook / وكيل الطباعة / healthz) على البورت {h[1]}")
    except Exception as ex:
        print("تعذر تشغيل الـ API الداخلي:", ex)
    scheduler.start()
    print("المهام الدورية (نسخ احتياطي، تقارير، رسائل، تنبيهات) شغّالة على السيرفر.")
    print("=" * 70)
    ft.run(main=main, view=ft.AppView.WEB_BROWSER, host=a.host, port=a.port, assets_dir=files.ASSETS_DIR, upload_dir=files.UPLOAD_DIR,
           no_cdn=os.environ.get("ERP_USE_CDN", "") not in ("1", "true"))   # بدون CDN: الواجهة تشتغل في شبكات من غير إنترنت


if __name__ == "__main__":
    sys.exit(run())
