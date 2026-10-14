#!/usr/bin/env python3
"""بوابة التجارب - شغّلها على سيرفرك:   python trial_portal.py            (أو: --port 8700)
إنشاء رابط دعوة من الطرفية:           python trial_portal.py invite --count 10 --days 30 [--label "معرض كذا"]
أكواد تفعيل اشتراك:                   python trial_portal.py code --plan pro --months 12 --count 5 [--label "اسم العميل"]
بعدها ابعت الرابط للأشخاص (واتساب مثلًا): كل واحد يفتحه ويكتب اسمه وجواله واسم شركته فتتجهّز له نسخة جديدة فاضية.
صفحة المشرف: http://السيرفر:8700/admin  (المستخدم admin، وكلمة المرور من ERP_PORTAL_ADMIN_PASSWORD أو ملف portal_admin_password.txt)."""
import argparse
import os
import socket
import sys
for _s in (sys.stdout, sys.stderr):      # ويندوز: الإخراج لملف/أنبوب بيبقى cp1252 وبيفشل مع العربي
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:      # noqa: BLE001
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def main():
    from erp_app import portal
    ap = argparse.ArgumentParser(description="بوابة التجارب")
    ap.add_argument("cmd", nargs="?", default="run", choices=["run", "invite", "list", "stop-all", "code", "remind"])
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=int(os.environ.get("ERP_PORTAL_PORT", "8700")))
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--days", type=int, default=portal.DEFAULT_DAYS)
    ap.add_argument("--label", default="")
    ap.add_argument("--plan", default="basic")
    ap.add_argument("--months", type=int, default=12)
    a = ap.parse_args()
    portal.init()
    host = os.environ.get("ERP_PUBLIC_HOST") or _lan_ip()
    if a.cmd == "invite":
        tok = portal.create_invite(a.count, a.days, a.label)
        print(f"{portal._scheme()}://{host}:{a.port}/s/{tok}   (يسمح بـ {a.count} تسجيل، تجربة {a.days} يوم)")
        return
    if a.cmd == "code":
        for c in portal.create_codes(a.plan, a.months, a.count, a.label):
            print(c)
        return
    if a.cmd == "remind":
        print("تذكيرات جديدة:", portal.reminders_once())
        return
    if a.cmd == "list":
        for t in portal.list_tenants():
            print(t["slug"], t["company"], t["phone"], f":{t['port']}", t["expires"], t["status"])
        return
    if a.cmd == "stop-all":
        for t in portal.list_tenants():
            portal.stop_tenant(t)
        return
    srv = portal.serve(a.host, a.port)
    print("=" * 70)
    print(f"بوابة التجارب شغّالة على {a.host}:{a.port}")
    print(f"صفحة المشرف: http://{host}:{a.port}/admin   (admin / {portal.admin_password()})")
    print(f"افتح البورتات {portal.PORT_START}-{portal.PORT_START + 999} في الجدار الناري عشان العملاء يدخلوا نسخهم.")
    print("إنشاء رابط دعوة:  python trial_portal.py invite --count 10")
    print("=" * 70)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
