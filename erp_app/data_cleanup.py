"""تنظيف قاعدة البيانات: حذف الحركات القديمة (وعند الطلب البيانات الأساسية والرسائل والمستخدمين) من غير ما نخسر
هيكل النظام: شجرة الحسابات + إعدادات المحاسبة والشركة + الفروع ومراكز التكلفة + طرق الدفع + وحدات القياس + المخازن.
كل التنفيذ في معاملة واحدة بنسخة احتياطية قبلها، وبعدين VACUUM لتصغير ملف القاعدة. الترقيم (فواتير/قيود/سندات) بيبدأ من الأول."""
import datetime
import os
import shutil

from sqlalchemy import select, func, update, text

from . import audit
from . import services
from .db import Base, SessionLocal, engine, DB_PATH, IS_SQLITE, User, FiscalPeriod, init_db

CONFIRM_PHRASE = "احذف كل البيانات"

# مجموعات الحركات (اسم عرض -> جداول) - كلها بتتحذف دايمًا
TRANSACTION_GROUPS = [
    ("القيود المحاسبية", ["journal_entry_lines", "journal_entries"]),
    ("سندات القبض والصرف", ["payments"]),
    ("فواتير المبيعات والكاشير ومدفوعاتها", ["sales_invoice_payments", "payment_transactions", "sales_invoice_items", "sales_invoices"]),
    ("مرتجعات المبيعات", ["sales_return_items", "sales_returns"]),
    ("نقاط الولاء (الحركات)", ["loyalty_txns"]),
    ("عروض أسعار المبيعات", ["sales_quotation_items", "sales_quotations"]),
    ("فواتير المشتريات ومرفقاتها", ["purchase_invoice_attachments", "purchase_invoice_items", "purchase_invoices"]),
    ("سندات استلام المشتريات", ["goods_receipt_note_items", "goods_receipt_notes"]),
    ("حركات المخزون والتسويات والتوالف والتصنيع", ["stock_move_batches", "stock_moves", "inventory_adjustment_lines", "inventory_adjustments", "damage_lines", "damage_items", "damage_records", "production_orders"]),
    ("طلبات المطعم", ["kitchen_events", "restaurant_order_items", "restaurant_orders"]),
    ("عهد الموظفين وسنداتها", ["custody_settlements", "custody_expenses", "custody_fundings", "employee_custodies"]),
    ("الرواتب والمخصصات والتسويات", ["payslips", "payroll_runs", "allowance_insurance_items", "allowance_insurance_runs", "annual_leave_settlements", "eos_settlements"]),
    ("طلبات الموظفين (إجازات / استئذان / استقالات)", ["leave_requests", "permission_requests", "resignation_requests"]),
    ("الأصول الثابتة والإهلاك والجرد", ["depreciation_run_items", "depreciation_runs", "asset_inventory_lines", "asset_inventories", "fixed_assets"]),
]
# بيانات أساسية: بتتحذف بس لو اخترت "قاعدة نظيفة تمامًا"
MASTER_GROUPS = [
    ("الأصناف وفئاتها ووحداتها وأسعارها", ["price_list_items", "price_lists", "bom_lines", "pos_group_items", "pos_groups", "product_unit_lines", "products", "categories"]),
    ("العملاء", ["customers"]), ("الموردون", ["suppliers"]),
    ("الموظفون وعقودهم", ["contracts", "employees"]),
    ("الموازنات", ["budget_lines"]),
    ("أقسام وطاولات المطعم", ["restaurant_tables", "restaurant_sections"]),
]
# بيانات التنظيم (مش حركات مالية): رسائل وجدول أعمال ومتابعة المستندات
EXTRA_GROUPS = [
    ("الرسائل والمحادثات", ["chat_messages", "chat_members", "chat_conversations"]),
    ("جدول الأعمال والمواعيد", ["agenda_items"]),
    ("متابعة تجديد المستندات (المستندات وسجل التجديد والتنبيهات)", ["document_alerts", "document_renewals", "tracked_documents"]),
]
ATTACH_DIRS = {"transactions": ["purchase_invoices", "custody_expenses"], "master": ["product_images"], "extras": ["chat", "hr_documents"]}
KEPT_STRUCTURE = ["شجرة الحسابات", "إعدادات المحاسبة والشركة", "الفروع ومراكز التكلفة", "طرق الدفع", "وحدات القياس", "المخازن", "فئات الأصول الثابتة", "أنواع المستندات"]


def _attachments_root():
    return os.path.normpath(os.path.join(os.path.dirname(DB_PATH), "..", "attachments"))


def _exports_dir():
    return os.path.normpath(os.path.join(os.path.dirname(DB_PATH), "..", "exports"))


def _count(session, table):
    return int(session.execute(select(func.count()).select_from(Base.metadata.tables[table])).scalar() or 0)


def _folder_stats(names):
    files = size = 0
    root = _attachments_root()
    for n in names:
        p = os.path.join(root, n)
        for dp, _dn, fn in os.walk(p):
            for f in fn:
                files += 1
                try:
                    size += os.path.getsize(os.path.join(dp, f))
                except OSError:
                    pass
    return files, size


def plan(master=False, extras=False, other_users=False, delete_files=True):
    """معاينة من غير أي تغيير: كام صف هيتحذف من كل مجموعة، وإيه اللي هيفضل."""
    session = SessionLocal()
    try:
        groups = [("حركات", g) for g in TRANSACTION_GROUPS]
        if master:
            groups += [("أساسية", g) for g in MASTER_GROUPS]
        if extras:
            groups += [("تنظيم", g) for g in EXTRA_GROUPS]
        out = []
        for kind, (label, tables) in groups:
            n = sum(_count(session, t) for t in tables)
            out.append({"kind": kind, "label": label, "rows": n, "tables": tables})
        users_n = session.query(User).filter(User.username != "admin").count() if other_users else 0
        total_rows = sum(g["rows"] for g in out) + users_n
        names = list(ATTACH_DIRS["transactions"]) + (ATTACH_DIRS["master"] if master else []) + (ATTACH_DIRS["extras"] if extras else [])
        files, size = _folder_stats(names) if delete_files else (0, 0)
        exp_files = len([f for f in os.listdir(_exports_dir())]) if delete_files and os.path.isdir(_exports_dir()) else 0
        db_size = _db_size()
        return {"groups": out, "other_users": users_n, "total_rows": total_rows, "files": files, "files_size": size, "export_files": exp_files,
                "db_size": db_size, "kept": list(KEPT_STRUCTURE) + ([] if master else ["الأصناف والعملاء والموردين والموظفين وقوائم الأسعار والموازنات"]) + ([] if extras else ["الرسائل وجدول الأعمال ومتابعة المستندات"]) + (["مدير النظام (admin)"] if other_users else ["كل المستخدمين"])}
    finally:
        session.close()


def _db_size():
    if IS_SQLITE:
        return os.path.getsize(DB_PATH) if os.path.isfile(DB_PATH) else 0
    try:
        with engine.connect() as c:
            return int(c.execute(text("SELECT pg_database_size(current_database())")).scalar() or 0)
    except Exception:
        return 0


def _backup():
    if not IS_SQLITE:
        from . import backup as _bk
        return _bk.backup_now("before_cleanup")["path"]
    if not os.path.isfile(DB_PATH):
        return None
    folder = os.path.join(os.path.dirname(DB_PATH), "backups")
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, f"erp_before_cleanup_{datetime.datetime.now():%Y%m%d_%H%M%S}.db")
    shutil.copy2(DB_PATH, dest)
    return dest


def _delete_dir_contents(path):
    removed = 0
    if os.path.isdir(path):
        for entry in os.listdir(path):
            p = os.path.join(path, entry)
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
                removed += 1
            except OSError:
                pass
    return removed


@audit.audited_bulk("تنظيف قاعدة البيانات")
def cleanup(master=False, extras=False, other_users=False, delete_files=True, backup=True, confirm=None, enforce_admin=True):
    """تنفيذ التنظيف. confirm لازم يساوي CONFIRM_PHRASE بالظبط. بيرجّع تقرير بالمحذوف والنسخة الاحتياطية."""
    if enforce_admin:
        me = services.current_user() or {}
        if me.get("role") != "admin":
            raise PermissionError("تنظيف قاعدة البيانات للأدمن بس")
    if (confirm or "").strip() != CONFIRM_PHRASE:
        raise ValueError(f'اكتب عبارة التأكيد بالظبط: "{CONFIRM_PHRASE}"')
    backup_path = _backup() if backup else None
    tables_to_clear = [t for _l, ts in TRANSACTION_GROUPS for t in ts]
    if master:
        tables_to_clear += [t for _l, ts in MASTER_GROUPS for t in ts]
    if extras:
        tables_to_clear += [t for _l, ts in EXTRA_GROUPS for t in ts]
    meta = Base.metadata.tables
    clear_set = set(tables_to_clear)
    # أي جدول تابع (مفتاح أجنبي إجباري) على جدول هيتمسح لازم يتمسح معاه - بنضمّه تلقائيًا بدل ما التنظيف يفشل أو يسيب بيانات يتيمة
    changed = True
    while changed:
        changed = False
        for t in Base.metadata.sorted_tables:
            if t.name in clear_set or t.name == "users":
                continue
            for c in t.columns:
                if not c.nullable and any(fk.column.table.name in clear_set for fk in c.foreign_keys):
                    clear_set.add(t.name); changed = True
                    break
    report = {"backup": backup_path, "deleted": {}, "users_deleted": 0, "nulled": {}, "files_removed": 0, "db_size_before": _db_size()}
    session = SessionLocal()
    try:
        # الجداول اللي هتتحذف مرتبة: الأبناء الأول
        order = [t for t in reversed(Base.metadata.sorted_tables) if t.name in clear_set]
        # جداول باقية بتشاور على جداول هتتحذف: نصفّر المراجع (لو العمود يقبل null)، وإلا نوقف قبل ما نغيّر حاجة
        kept_refs = []
        for t in Base.metadata.sorted_tables:
            if t.name in clear_set:
                continue
            for c in t.columns:
                for fk in c.foreign_keys:
                    if fk.column.table.name in clear_set:
                        if not c.nullable:
                            raise RuntimeError(f"الجدول {t.name} فيه عمود إجباري ({c.name}) بيشاور على {fk.column.table.name} المطلوب حذفه - اتلغى التنفيذ")
                        kept_refs.append((t, c))
        for t, c in kept_refs:
            res = session.execute(update(t).where(c.isnot(None)).values({c.name: None}))
            if res.rowcount:
                report["nulled"][f"{t.name}.{c.name}"] = res.rowcount
        for t in order:
            res = session.execute(t.delete())
            if res.rowcount:
                report["deleted"][t.name] = res.rowcount
        if other_users:
            n = session.query(User).filter(User.username != "admin").delete(synchronize_session=False)
            report["users_deleted"] = n
        if "loyalty_txns" in clear_set and "customers" not in clear_set:
            session.execute(text("UPDATE customers SET loyalty_points = 0"))      # الحركات اتمسحت فالأرصدة لازم تتصفّر
        # الفترات المحاسبية: نفتحها تاني (القيود اتمسحت)
        session.query(FiscalPeriod).update({"is_closed": False, "closed_at": None, "closing_journal_id": None}, synchronize_session=False)
        # عدّادات الترقيم التلقائي بتتصفّر عشان الترقيم يبدأ من الأول
        try:
            if IS_SQLITE:
                existing = {r[0] for r in session.execute(text("SELECT name FROM sqlite_master WHERE name='sqlite_sequence'")).all()}
                if existing:
                    for t in order:
                        session.execute(text("DELETE FROM sqlite_sequence WHERE name = :n"), {"n": t.name})
            else:
                for t in order:
                    if "id" in t.c:
                        session.execute(text("SELECT setval(pg_get_serial_sequence(:t, 'id'), 1, false)"), {"t": t.name})
        except Exception:
            pass
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    if delete_files:
        root = _attachments_root()
        names = list(ATTACH_DIRS["transactions"]) + (ATTACH_DIRS["master"] if master else []) + (ATTACH_DIRS["extras"] if extras else [])
        for n in names:
            report["files_removed"] += _delete_dir_contents(os.path.join(root, n))
            try:
                shutil.rmtree(os.path.join(root, n), ignore_errors=True)
            except OSError:
                pass
        report["files_removed"] += _delete_dir_contents(_exports_dir())
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql("VACUUM")
    except Exception:
        pass
    init_db()      # يتأكد إن الأساسيات (مدير النظام، الفترة المحاسبية الحالية، طرق الدفع...) موجودة
    report["db_size_after"] = _db_size()
    report["total_deleted"] = sum(report["deleted"].values()) + report["users_deleted"]
    return report
