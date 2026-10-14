"""تنظيف قاعدة البيانات من سطر الأوامر (من غير فتح البرنامج):
    python clean_database.py                 معاينة بس (مفيش حذف)
    python clean_database.py --yes           حذف كل الحركات (وبيعمل نسخة احتياطية الأول)
    python clean_database.py --yes --master  + حذف الأصناف والعملاء والموردين والموظفين وقوائم الأسعار والموازنات
    python clean_database.py --yes --extras  + حذف الرسائل وجدول الأعمال ومتابعة المستندات
    python clean_database.py --yes --users   + حذف كل المستخدمين ما عدا admin
    python clean_database.py --yes --all     = كل اللي فوق (قاعدة نظيفة تمامًا: شجرة الحسابات والإعدادات بس)
    إضافة --keep-files: ما تمسحش ملفات المرفقات والتقارير المصدّرة."""
import sys
from erp_app import data_cleanup as C
from erp_app.db import init_db


def main(argv):
    init_db()
    allf = "--all" in argv
    kw = dict(master=allf or "--master" in argv, extras=allf or "--extras" in argv, other_users=allf or "--users" in argv, delete_files="--keep-files" not in argv)
    p = C.plan(**kw)
    print("اللي هيتحذف:")
    for g in p["groups"]:
        print(f"  - {g['label']}: {g['rows']:,} صف")
    if p["other_users"]:
        print(f"  - مستخدمين (ما عدا admin): {p['other_users']}")
    print(f"  ملفات مرفقات: {p['files']:,} | تقارير مصدّرة: {p['export_files']:,} | الإجمالي: {p['total_rows']:,} صف")
    print("هيفضل:", "، ".join(p["kept"]))
    if "--yes" not in argv:
        print("\nده معاينة بس. أضف --yes للتنفيذ (بيعمل نسخة احتياطية الأول).")
        return 0
    rep = C.cleanup(confirm=C.CONFIRM_PHRASE, enforce_admin=False, **kw)
    print(f"\nتم. اتحذف {rep['total_deleted']:,} صف | نسخة احتياطية: {rep['backup']}")
    print(f"حجم القاعدة: {rep['db_size_before'] / 1024:,.0f} KB -> {rep['db_size_after'] / 1024:,.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
