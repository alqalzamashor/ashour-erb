"""ترقية آمنة للبرنامج - شغّله والبرنامج مقفول.
    python update.py الإصدار_الجديد.zip            ← ترقية (بيسألك قبل التنفيذ)
    python update.py الإصدار_الجديد.zip --check    ← يعرض اللي هيتغيّر من غير ما ينفّذ
    python update.py https://.../app.zip --sha256 <البصمة>   ← من رابط (البصمة إجبارية)
    python update.py --rollback [--with-db]        ← رجوع لآخر إصدار (والقاعدة لو --with-db)
    python update.py --status                      ← الإصدار الحالي وسجل الترقيات
خيارات: --yes بدون سؤال، --force لإصدار أقدم/مطابق، --install-deps تثبيت المكتبات لو اتغيّرت."""
import argparse
import os
import sys
import tempfile


def main():
    ap = argparse.ArgumentParser(description="ترقية آمنة للبرنامج")
    ap.add_argument("package", nargs="?")
    ap.add_argument("--check", action="store_true"); ap.add_argument("--yes", action="store_true"); ap.add_argument("--force", action="store_true")
    ap.add_argument("--install-deps", action="store_true"); ap.add_argument("--sha256"); ap.add_argument("--rollback", action="store_true")
    ap.add_argument("--with-db", action="store_true"); ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    from erp_app import db, updater
    db.init_db()
    try:
        if a.status or not (a.package or a.rollback):
            print("الإصدار الحالي:", updater.read_version(updater.ROOT))
            for e in updater.history()[-10:]:
                print(" ", e.get("at"), e.get("status"), e.get("from", ""), "←", e.get("to", ""), e.get("db_backup") or "")
            return 0
        if a.rollback:
            if not a.yes and input("هيرجّع الكود للإصدار السابق" + (" ويسترجع القاعدة (بيانات بعد الترقية هتضيع)" if a.with_db else "") + ". متأكد؟ (y/n) ").lower() != "y":
                return 1
            updater.rollback(with_db=a.with_db)
            return 0
        src = a.package
        if src.startswith(("http://", "https://")):
            if not a.sha256:
                print("لازم --sha256 مع الروابط: بنشغّل كود من الحزمة، فلازم نتأكد إنها هي اللي تقصدها."); return 2
            import requests
            fd, tmp = tempfile.mkstemp(suffix=".zip"); os.close(fd)
            with requests.get(src, stream=True, timeout=60) as r, open(tmp, "wb") as f:
                r.raise_for_status()
                for b in r.iter_content(1 << 20):
                    f.write(b)
            src = tmp
        if a.check:
            r = updater.apply(src, dry_run=True, force=a.force, sha256=a.sha256)
            for k in ("added", "changed", "removed"):
                print(k + ":", len(r[k]), *r[k][:15])
            return 0
        if not a.yes and input("هتتاخد نسخة احتياطية الأول وبعدين يتم التحديث. نكمّل؟ (y/n) ").lower() != "y":
            return 1
        updater.apply(src, force=a.force, install_deps=a.install_deps, sha256=a.sha256)
        return 0
    except updater.UpdateError as ex:
        print("خطأ:", ex)
        return 1


if __name__ == "__main__":
    sys.exit(main())
