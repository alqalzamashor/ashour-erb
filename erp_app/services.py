"""
طبقة منطق الأعمال - جميع العمليات على قاعدة البيانات مركّزة هنا.
"""

from . import clock
datetime = clock.proxy      # ساعة قابلة للتجاوز (مزامنة الفروع offline) - من غير تجاوز شغّالة زي datetime العادي
import os
import re
import json
from sqlalchemy import func, case, or_
from sqlalchemy.orm import joinedload
from .db import (
    MonthClose,
    get_session, Product, Category, ProductUnit, ProductUnitLine, Location, StockMove,
    Customer, Supplier, CompanySettings, PriceList, PriceListItem, PrepaidTemplate, PrepaidExpense, PrepaidExpenseLine, AgendaItem, DocumentType, TrackedDocument, DocumentRenewal, DocumentAlert, ChatConversation, ChatMember, ChatMessage, SalesQuotation, SalesQuotationItem, EmployeeCustody, CustodyFunding, CustodyExpense, CustodySettlement,
    SalesInvoice, SalesInvoiceItem, PurchaseInvoice, PurchaseInvoiceItem, PurchaseInvoiceAttachment,
    GoodsReceiptNote, GoodsReceiptNoteItem,
    Account, JournalEntry, JournalEntryLine, AccountingSettings, Payment, FiscalPeriod, Branch, CostCenter, User, BudgetLine,
    Employee, Contract, PayrollRun, Payslip, AllowanceInsuranceRun, AllowanceInsuranceItem,
    FixedAsset, DepreciationRun, DepreciationRunItem, AssetCategory, AssetInventory, AssetInventoryLine,
    RestaurantSection, RestaurantTable, RestaurantOrder, RestaurantOrderItem, KitchenEvent, PaymentMethod,
    LeaveRequest, LeaveType, PermissionRequest, ResignationRequest, EosSettlement, AnnualLeaveSettlement,
    BomLine, ProductionOrder,
    DamageRecord, DamageItem, DamageLine,
    PosGroup, PosGroupItem,
 )


# ============================== Session / Security Context ==============================
_CURRENT_USER = None

ACTION_NAMES = ("view", "create", "edit", "delete", "post", "close")
MODULE_NAMES = {
    "dashboard":"لوحة التحكم", "agenda":"جدول الأعمال", "chat":"الرسائل والمحادثات", "hr_documents":"تجديد الرخص والمستندات", "prepaid_expenses":"المصروفات المدفوعة مقدمًا", "chart_import":"تطبيق شجرة الحسابات الجديدة", "data_cleanup":"تنظيف قاعدة البيانات", "sales_quotations":"عروض الأسعار", "sales_invoices":"فواتير المبيعات", "purchase_invoices":"فواتير المشتريات",
    "customers":"العملاء", "suppliers":"الموردون", "products":"الأصناف", "categories":"الفئات", "price_lists":"قوائم الأسعار", "employee_custody":"أرصدة وكشوف العهد", "vat_report":"تقرير ضريبة القيمة المضافة", "custody_issues":"صرف العهد", "custody_expenses":"مصروفات وفواتير العهد", "custody_settlements":"تسوية العهد",
    "units":"وحدات القياس", "stock_moves":"حركات المخزون", "stock_balance":"أرصدة المخزون", "pos_returns":"مرتجعات المبيعات", "pos_sessions":"جلسات نقاط البيع", "pos_terminals":"ماكينات نقاط البيع", "expiry_report":"الصلاحية والتشغيلات", "purchase_price_report":"مقارنة أسعار الشراء",
    "inventory_adjustments":"التسويات الجردية", "accounts":"شجرة الحسابات", "journals":"القيود اليومية",
    "receipts_payments":"السندات", "ledger":"دفتر الأستاذ", "party_reports":"كشوف الأطراف",
    "reports":"التقارير", "advanced_reports":"التقارير المقارنة", "fiscal_periods":"الفترات والإقفال",
    "organization":"الفروع ومراكز التكلفة", "financial_consolidation":"القوائم الموحدة والفروع", "budgets":"الموازنات التقديرية", "settings":"الإعدادات",
    "employees":"الموظفون", "contracts":"العقود", "payroll":"الرواتب", "allowances_insurance":"المخصصات والتأمينات", "fixed_assets":"الأصول الثابتة", "asset_categories":"فئات الأصول الثابتة", "asset_inventory":"جرد الأصول الثابتة", "restaurant":"نظام المطاعم", "kitchen":"شاشة المطبخ", "void_reports":"تقرير الملغاة والمرتجعات", "recipe_costing":"تقرير تكلفة الوصفات", "restaurant_dashboard":"لوحة المطعم", "coupons":"الكوبونات والخصومات", "scheduled_reports":"التقارير المجدولة بالبريد", "loyalty":"برنامج الولاء", "notifications":"الرسائل (واتساب/SMS)", "delivery_orders":"طلبات التوصيل", "credit":"حدود الائتمان", "alerts":"التنبيهات الذكية", "approvals":"الموافقات", "currencies":"العملات وأسعار الصرف", "receivables_aging":"أعمار الديون", "product_labels":"ملصقات الأصناف", "data_integrity":"فحص سلامة البيانات", "database":"قاعدة البيانات", "discount_report":"تقرير الخصومات والكوبونات", "audit_log":"سجل التدقيق", "backup":"النسخ الاحتياطي والاسترجاع", "printers":"إعدادات الطابعات الحرارية", "subscription":"الاشتراك", "sync":"مزامنة الفرع مع المركز", "zatca":"الفوترة الإلكترونية", "payment_methods":"طرق الدفع", "leave_requests":"الإجازات والاستئذان", "attendance":"الحضور والانصراف وجهاز البصمة", "resignations":"الاستقالات ونهاية الخدمة", "eos_settlements":"تسويات نهاية الخدمة", "employee_balances":"تقرير أرصدة الموظفين (إجازات ونهاية خدمة)", "annual_leave_settlements":"تسويات الإجازة السنوية", "asset_purchase_invoices":"فواتير مشتريات الأصول",
    "goods_receipts":"سندات استلام المشتريات", "pos":"نقاط البيع", "pos_groups":"مجموعات نقاط البيع",
    "locations":"المخازن", "product_components":"مكونات الأصناف والخصائص", "manufacturing":"أوامر الإنتاج",
    "damages":"التوالف والهوالك", "stock_transfer":"التحويل بين المخازن", "product_movements":"تقرير حركة الأصناف",
    "journal_entries":"إدخال القيود اليومية", "general_journal":"اليومية العامة", "trial_balance":"ميزان المراجعة",
    "data_import_export":"استيراد وتصدير البيانات", "banking":"الربط البنكي", "sales_reports":"تقارير المبيعات التحليلية", "purchase_reports":"تقارير المشتريات التحليلية",
    "ashour_pnl":"عاشور: أرباح وخسائر الفروع", "ashour_pos":"عاشور: مبيعات نقاط البيع", "ashour_purchases":"عاشور: تقارير المشتريات", "ashour_customers":"عاشور: العملاء والتحصيلات", "ashour_settings":"عاشور: الإعدادات",
}

ROLE_DEFAULT_PERMISSIONS = {
    "admin": {"*": ["*"]},
    "accountant": {"alerts":["view","edit"], "currencies":["view","edit","post"], "approvals":["view","approve"], "credit":["edit"], "receivables_aging":["view"], "notifications":["view","edit"], "product_labels":["view"], "data_integrity":["view"], "loyalty":["view","edit"], "void_reports":["view"], "discount_report":["view"], "restaurant_dashboard":["view"], "recipe_costing":["view"], "banking":["view","create","edit","delete","post"], "sales_reports":["view"], "purchase_reports":["view"], "pos_returns":["view","create"], "pos_sessions":["view","create","edit"], "pos_terminals":["view","create","edit","delete"], "purchase_price_report":["view"], "expiry_report":["view"], 
        "dashboard":["view"], "accounts":["view","create","edit","delete"], "journals":["view","create","edit","delete","post"],
        "receipts_payments":["view","create","edit","delete","post"], "ledger":["view"], "party_reports":["view"],
        "reports":["view"], "advanced_reports":["view"], "ashour_pnl":["view"], "ashour_pos":["view"], "ashour_purchases":["view"], "ashour_customers":["view"], "financial_consolidation":["view"], "budgets":["view","create","edit","delete","post"], "fiscal_periods":["view","create","edit","close"],
        "agenda":["view","create","edit","delete"], "chat":["view","create","delete"], "customers":["view","create","edit"], "suppliers":["view","create","edit"], "sales_invoices":["view","create","edit","post"], "sales_quotations":["view","create","edit","delete","post"], "purchase_invoices":["view","create","edit","post"], "products":["view"],
        "employees":["view","create","edit"], "employee_balances":["view"], "contracts":["view","create","edit"], "prepaid_expenses":["view","create","edit","delete","post"], "hr_documents":["view","create","edit","delete"], "payroll":["view","create","edit","delete","post"], "vat_report":["view"],
        "employee_custody":["view"], "custody_issues":["view","create","edit","delete","post"], "custody_expenses":["view","create","edit","delete","post"], "custody_settlements":["view","create","edit","delete","post"],
    },
    "sales": {"alerts":["view"], "approvals":["view"], "receivables_aging":["view"], "delivery_orders":["view","edit"], "loyalty":["view"], "void_reports":["view"], "discount_report":["view"], "restaurant_dashboard":["view"], "sales_reports":["view"], "pos_sessions":["view","create","edit"], "dashboard":["view"],"agenda":["view","create","edit","delete"],"chat":["view","create","delete"],"sales_invoices":["view","create","edit","post"],"sales_quotations":["view","create","edit","delete","post"],"customers":["view","create","edit"],"party_reports":["view"],"reports":["view"],
              "pos":["view","create","edit","post"],"restaurant":["view","create","edit","post","delete"],"kitchen":["view","edit"],"payment_methods":["view"]},
    "inventory": {"alerts":["view"], "approvals":["view"], "product_labels":["view"],"expiry_report":["view"],"dashboard":["view"],"agenda":["view","create","edit","delete"],"chat":["view","create","delete"],"products":["view","create","edit"],"categories":["view","create","edit","delete"],"units":["view","create","edit","delete"],"stock_moves":["view","create","edit"],"stock_balance":["view"],"inventory_adjustments":["view","create","edit","post"],"reports":["view"]},
    "viewer": {"alerts":["view"], "void_reports":["view"], "discount_report":["view"], "restaurant_dashboard":["view"], "recipe_costing":["view"], "sales_reports":["view"], "purchase_reports":["view"], "pos_sessions":["view"],"purchase_price_report":["view"],"expiry_report":["view"],"dashboard":["view"],"agenda":["view","create","edit","delete"],"chat":["view","create","delete"],"reports":["view"],"party_reports":["view"],"stock_balance":["view"]}
}

import threading as _threading
import weakref as _weakref
from .db import lock_numbering as _db_lock
from .db import APP_DIR

_TL = _threading.local()            # مستخدم مرتبط بخيط معيّن (خيوط خلفية زي الاستيراد)
_PAGE_USERS = _weakref.WeakKeyDictionary()   # مستخدم كل جلسة ويب/نافذة (Flet page) - عشان أكتر من جهاز على نفس السيرفر
_PAGE_USERS_ID = {}


def _ctx_page():
    try:
        from flet.controls.context import _context_page
        return _context_page.get()
    except Exception:
        return None


def _get_user():
    """المستخدم الحالي: خيط مخصص > جلسة الصفحة الحالية (Flet) > المتغير العام (وضع المكتب/السكربتات)."""
    u = getattr(_TL, "user", None)
    if u is not None:
        return u
    p = _ctx_page()
    if p is not None:
        try:
            if p in _PAGE_USERS:
                return _PAGE_USERS[p]
        except TypeError:
            if id(p) in _PAGE_USERS_ID:
                return _PAGE_USERS_ID[id(p)]
    return _CURRENT_USER


def set_current_user(user):
    """بيحدد مستخدم الجلسة الحالية. جوه حدث من صفحة Flet بيتخزن للصفحة دي بس (كل جهاز مستخدم مستقل)؛ برّه كده (سكربتات/اختبارات) متغير عام."""
    global _CURRENT_USER
    p = _ctx_page()
    if p is None:
        _CURRENT_USER = user
        return
    try:
        _PAGE_USERS[p] = user
    except TypeError:
        _PAGE_USERS_ID[id(p)] = user
    active = [u for u in list(_PAGE_USERS.values()) + list(_PAGE_USERS_ID.values()) if u]
    # جلسة واحدة (مكتب) -> نحتفظ بنسخة عامة للخيوط بدون سياق؛ أكتر من جلسة -> مفيش مستخدم عام (عشان مايتخلطش)
    _CURRENT_USER = user if len(active) <= 1 else None


def bind_thread_user(user=None):
    """للخيوط الخلفية: اربط الخيط بمستخدم (الافتراضي المستخدم الحالي لحظة الاستدعاء)."""
    _TL.user = user if user is not None else _get_user()


from . import audit as _audit
_audit.set_user_getter(lambda: _get_user())
_audit.install()

def current_user():
    return _get_user()

def _permission_map(user=None):
    user = user or _get_user()
    if not user: return {}
    try:
        raw = user.get("permissions") if isinstance(user, dict) else user.permissions
        data = json.loads(raw or "{}")
        if isinstance(data, list): return {"legacy":["*"]} if "*" in data else {x:["view","create","edit","delete","post","close"] for x in data}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def user_has_action(user, module, action):
    user = user or _get_user()
    if not user: return True
    role = user.get("role") if isinstance(user, dict) else user.role
    if role == "admin": return True
    data = _permission_map(user)
    if not data:
        # مفيش صلاحيات محفوظة خالص (سجل قديم/تالف) - ارجع لصلاحيات الدور
        # الافتراضية كشبكة أمان بس، مش كسلوك عادي.
        data = ROLE_DEFAULT_PERMISSIONS.get(role, {})
    allowed = list(data.get(module, [])) + list(data.get("*", []))
    return "*" in allowed or action in allowed

def require_action(module, action):
    if not user_has_action(_get_user(), module, action):
        raise PermissionError(f"ليس لديك صلاحية {action} في {MODULE_NAMES.get(module,module)}")

def user_branch_ids(user=None):
    user = user or _get_user()
    if not user: return []
    role = user.get("role") if isinstance(user, dict) else user.role
    if role == "admin": return []
    try:
        raw = user.get("branch_ids", "[]") if isinstance(user, dict) else user.branch_ids
        ids=[int(x) for x in json.loads(raw or "[]")]
        if ids: return ids
        with get_session() as s:
            b=s.query(Branch).filter(Branch.is_default.is_(True),Branch.is_active.is_(True)).first() or s.query(Branch).filter(Branch.is_active.is_(True)).first()
            return [b.id] if b else []
    except Exception:
        with get_session() as s:
            b=s.query(Branch).filter(Branch.is_default.is_(True),Branch.is_active.is_(True)).first() or s.query(Branch).filter(Branch.is_active.is_(True)).first()
            return [b.id] if b else []

def allowed_branch(branch_id, user=None):
    ids = user_branch_ids(user)
    return not ids or int(branch_id) in ids

def user_cost_center_ids(user=None):
    user = user or _get_user()
    if not user: return []
    role = user.get("role") if isinstance(user, dict) else user.role
    if role == "admin": return []
    try:
        raw = user.get("cost_center_ids", "[]") if isinstance(user, dict) else getattr(user, "cost_center_ids", "[]")
        ids=[int(x) for x in json.loads(raw or "[]")]
        if ids: return ids
        with get_session() as s:
            c=s.query(CostCenter).filter(CostCenter.is_active.is_(True)).order_by(CostCenter.id).first()
            return [c.id] if c else []
    except Exception:
        return []

def allowed_cost_center(cost_center_id, user=None):
    ids=user_cost_center_ids(user)
    return not ids or int(cost_center_id) in ids

def default_cost_center_id():
    with get_session() as s:
        x=s.query(CostCenter).filter(CostCenter.is_active.is_(True)).order_by(CostCenter.id).first()
        return x.id if x else None


# ============================== Categories ==============================
def list_categories():
    with get_session() as s:
        return s.query(Category).order_by(Category.name).all()


def create_category(name):
    require_action("categories", "create")
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم الفئة مطلوب")
    with get_session() as s:
        cat = Category(name=name)
        s.add(cat)
        s.commit()
        s.refresh(cat)
        return cat.id


def update_category(category_id, name):
    require_action("categories", "edit")
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم الفئة مطلوب")
    with get_session() as s:
        cat = s.get(Category, category_id)
        if not cat:
            raise ValueError("الفئة غير موجودة")
        cat.name = name
        s.commit()


def delete_category(category_id):
    require_action("categories", "delete")
    with get_session() as s:
        used = s.query(Product).filter(Product.category_id == category_id).count()
        if used:
            raise ValueError(f"لا يمكن حذف الفئة لأنها مستخدمة في {used} صنف")
        cat = s.get(Category, category_id)
        if cat:
            s.delete(cat)
            s.commit()


# ============================== Units ==============================
def list_units(search=None):
    with get_session() as s:
        q = s.query(ProductUnit).filter(ProductUnit.is_active.is_(True))
        if search:
            q = q.filter(ProductUnit.name.like(f"%{search.strip()}%"))
        return q.order_by(ProductUnit.name).all()


def create_unit(name):
    require_action("units", "create")
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم وحدة القياس مطلوب")
    with get_session() as s:
        u = ProductUnit(name=name, is_active=True)
        s.add(u)
        s.commit()
        s.refresh(u)
        return u.id


def update_unit(unit_id, name):
    require_action("units", "edit")
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم وحدة القياس مطلوب")
    with get_session() as s:
        u = s.get(ProductUnit, unit_id)
        if not u:
            raise ValueError("الوحدة غير موجودة")
        old_name = u.name
        # إبقاء الأصناف مرتبطة بالوحدة بعد تغيير اسمها.
        s.query(Product).filter(Product.unit == old_name).update({Product.unit: name}, synchronize_session=False)
        u.name = name
        s.commit()


def delete_unit(unit_id):
    require_action("units", "delete")
    with get_session() as s:
        u = s.get(ProductUnit, unit_id)
        if not u:
            raise ValueError("الوحدة غير موجودة")
        used = s.query(Product).filter(Product.unit == u.name).count()
        if used:
            raise ValueError(f"لا يمكن حذف الوحدة لأنها مستخدمة في {used} صنف")
        s.delete(u)
        s.commit()


# ============================== Product Units / Conversions ==============================
def list_product_units(product_id):
    with get_session() as s:
        return (s.query(ProductUnitLine)
                .options(joinedload(ProductUnitLine.unit))
                .filter(ProductUnitLine.product_id == int(product_id))
                .order_by(ProductUnitLine.factor_to_base, ProductUnitLine.id).all())

def get_product_unit(product_id, unit_id=None):
    with get_session() as s:
        if unit_id:
            return (s.query(ProductUnitLine).options(joinedload(ProductUnitLine.unit))
                    .filter(ProductUnitLine.product_id==int(product_id), ProductUnitLine.unit_id==int(unit_id)).first())
        return (s.query(ProductUnitLine).options(joinedload(ProductUnitLine.unit))
                .filter(ProductUnitLine.product_id==int(product_id), ProductUnitLine.is_default.is_(True)).first())

def save_product_units(product_id, unit_lines):
    require_action("products", "edit")
    product_id=int(product_id)
    with get_session() as s:
        p=s.get(Product, product_id)
        if not p: raise ValueError("الصنف غير موجود")
        from . import field_access as _fa
        _keep_cost = {} if _fa.can_see("cost_price") else {l.unit_id: l.cost_price for l in s.query(ProductUnitLine).filter(ProductUnitLine.product_id==product_id).all()}
        seen=set(); default_count=0
        normalized=[]
        for row in unit_lines or []:
            uid=int(row["unit_id"]); factor=float(row.get("factor_to_base",1) or 0)
            if factor <= 0: raise ValueError("معامل التحويل يجب أن يكون أكبر من صفر")
            if uid in seen: raise ValueError("لا يمكن تكرار وحدة القياس للصنف")
            seen.add(uid)
            is_default=bool(row.get("is_default",False))
            default_count += 1 if is_default else 0
            normalized.append((uid,factor,row.get("sale_price"),(row.get("cost_price") if _fa.can_see("cost_price") else _keep_cost.get(uid)),row.get("barcode","") or "",is_default))
        if not normalized:
            base=s.query(ProductUnit).filter(ProductUnit.name==p.unit).first()
            if not base: raise ValueError("وحدة الأساس غير موجودة")
            normalized=[(base.id,1.0,p.sale_price,p.cost_price,"",True)]
        if default_count == 0:
            normalized[0]=(*normalized[0][0:5],True)
        elif default_count > 1:
            raise ValueError("حدد وحدة أساسية واحدة فقط")
        s.query(ProductUnitLine).filter(ProductUnitLine.product_id==product_id).delete(synchronize_session=False)
        for uid,factor,sp,cp,barcode,is_default in normalized:
            s.add(ProductUnitLine(product_id=product_id, unit_id=uid, factor_to_base=factor,
                                  sale_price=None if sp in (None,"") else float(sp),
                                  cost_price=None if cp in (None,"") else float(cp), barcode=barcode, is_default=is_default))
        default_row=next(x for x in normalized if x[5])
        default_unit=s.get(ProductUnit, default_row[0])
        p.unit=default_unit.name
        p.sale_price=float(default_row[2]) if default_row[2] not in (None,"") else p.sale_price
        p.cost_price=float(default_row[3]) if default_row[3] not in (None,"") else p.cost_price
        s.commit()

def convert_to_base_quantity(product_id, quantity, unit_id=None):
    qty=float(quantity or 0)
    if qty <= 0: raise ValueError("الكمية يجب أن تكون أكبر من صفر")
    line=get_product_unit(product_id, unit_id)
    if not line:
        p=get_product(product_id)
        return qty, (p.unit if p else "قطعة"), 1.0
    return qty*float(line.factor_to_base or 1), line.unit.name, float(line.factor_to_base or 1)


# ============================== Products ==============================
def list_products(search=None, category_id=None, active_only=True):
    with get_session() as s:
        q = s.query(Product).options(joinedload(Product.category))
        if active_only:
            q = q.filter(Product.is_active.is_(True))
        if category_id:
            q = q.filter(Product.category_id == category_id)
        if search:
            like = f"%{search}%"
            q = q.filter((Product.name.like(like)) | (Product.sku.like(like)) |
                         (Product.id.in_(s.query(ProductUnitLine.product_id).filter(ProductUnitLine.barcode != "", ProductUnitLine.barcode.like(like)))))
        products = q.order_by(Product.sku).all()
        s.expunge_all()
        return products


def find_product_by_code(code, sellable_only=True):
    """مسح باركود/كود: يدوّر على باركود وحدة الصنف (مطابق تمامًا) ثم على كود الصنف SKU (بدون حساسية حروف).
    بيرجّع (product, factor) - factor = معامل الوحدة (عبوة/كرتونة) - أو None. بيتجاهل الأصناف الموقوفة (وغير القابلة للبيع لو sellable_only)."""
    code = (code or "").strip()
    if not code:
        return None
    with get_session() as s:
        def ok(p):
            return p is not None and p.is_active and (p.can_be_sold or not sellable_only)
        ln = s.query(ProductUnitLine).filter(ProductUnitLine.barcode == code).first()
        if ln:
            p = s.get(Product, ln.product_id)
            if ok(p):
                s.expunge(p); return p, float(ln.factor_to_base or 1.0)
        p = s.query(Product).filter(func.lower(Product.sku) == code.lower()).first()
        if ok(p):
            s.expunge(p); return p, 1.0
    return None


def scan_lookup(code):
    """نقطة دخول المسح الموحدة (كاشير/مطعم): باركود موزون/مسعّر -> الكمية من الوزن أو السعر؛ وإلا باركود عبوة/كود صنف عادي.
    بيرجّع {'product','qty','kind'(weight|price|pack|item),'info'} أو None. بيرمي ValueError برسالة واضحة لو الباركود الموزون صنفه مش موجود أو القيمة صفر."""
    from . import scale_barcode
    sc = scale_barcode.parse(code)
    if sc:
        plu = sc["plu"]
        cands = {plu, plu.lstrip("0") or "0"}
        with get_session() as s:
            p = None
            for ln in s.query(ProductUnitLine).filter(ProductUnitLine.barcode.in_(list(cands))).all():
                q = s.get(Product, ln.product_id)
                if q and q.is_active and q.can_be_sold:
                    p = q; break
            if p is None:
                for q in s.query(Product).filter(Product.sku.in_(list(cands))).all():
                    if q.is_active and q.can_be_sold:
                        p = q; break
            if p is not None:
                s.expunge(p)
        if p is None:
            raise ValueError(f"باركود موزون: مفيش صنف بكود الميزان {plu.lstrip('0') or '0'} (سجّله كباركود/كود للصنف)")
        if sc["kind"] == "weight":
            qty = round(sc["value"], 3); info = f"{qty:g} كجم"
        else:
            unit = float(p.sale_price or 0) * (1 + float(p.tax_rate or 0) / 100.0)
            if unit <= 0:
                raise ValueError(f"الصنف «{p.name}» سعره صفر - مينفعش حساب الكمية من السعر")
            qty = round(sc["value"] / unit, 3); info = f"بسعر {sc['value']:,.2f}"
        if qty <= 0:
            raise ValueError("الباركود الموزون بقيمة صفر")
        return {"product": p, "qty": qty, "kind": sc["kind"], "info": info}
    hit = find_product_by_code(code)
    if hit:
        return {"product": hit[0], "qty": hit[1], "kind": "pack" if hit[1] and hit[1] != 1 else "item", "info": f"× {hit[1]:g}" if hit[1] and hit[1] != 1 else ""}
    return None


def get_product(product_id):
    with get_session() as s:
        return (s.query(Product).options(joinedload(Product.unit_lines).joinedload(ProductUnitLine.unit))
                .filter(Product.id==int(product_id)).first())


def _check_batch_settings(issue_method, track_expiry, shelf_life_days, expiry_alert_days, cost_method="auto"):
    cost_method = (cost_method or "auto").strip().lower()
    if cost_method not in COST_METHODS:
        raise ValueError("طريقة التكلفة غير معروفة (auto / avg / fifo / lifo)")
    method = (issue_method or "none").strip().lower()
    if method not in BATCH_METHODS:
        raise ValueError("طريقة الإخراج غير معروفة (none / fifo / lifo / fefo)")
    if cost_method in ("fifo", "lifo") and method not in (cost_method, "fefo"):
        method = cost_method           # تكلفة FIFO/LIFO محتاجة تشغيلات بنفس الترتيب (أو FEFO والتكلفة من التشغيلة الفعلية)
    track = bool(track_expiry) or method == "fefo"           # FEFO معناها الصنف له صلاحية
    shelf = int(shelf_life_days) if shelf_life_days not in (None, "") else None
    if shelf is not None and shelf <= 0:
        raise ValueError("مدة الصلاحية بالأيام لازم تكون أكبر من صفر")
    alert = int(expiry_alert_days) if expiry_alert_days not in (None, "") else 30
    if alert < 0:
        raise ValueError("أيام التنبيه قبل الانتهاء لا يمكن أن تكون سالبة")
    return method, track, shelf, alert, cost_method


def create_product(sku, name, category_id=None, unit="قطعة",
                    cost_price=0.0, sale_price=0.0, reorder_point=0.0,
                    tax_rate=15.0, sales_account_id=None, inventory_account_id=None, cogs_account_id=None, unit_lines=None,
                    product_type="simple", can_be_sold=True, can_be_purchased=True,
                    issue_method="none", track_expiry=False, shelf_life_days=None, expiry_alert_days=30, cost_method="auto"):
    require_action("products", "create")
    from . import field_access as _fa
    if not _fa.can_see("cost_price"):
        cost_price = 0.0          # مستخدم مخفي عنه سعر التكلفة ما يقدرش يحدده
    issue_method, track_expiry, shelf_life_days, expiry_alert_days, cost_method = _check_batch_settings(issue_method, track_expiry, shelf_life_days, expiry_alert_days, cost_method)
    with get_session() as s:
        cfg = s.get(AccountingSettings, 1)
        p = Product(
            sku=sku, name=name, category_id=category_id, unit=unit,
            cost_price=cost_price, sale_price=sale_price,
            reorder_point=reorder_point, tax_rate=tax_rate,
            sales_account_id=sales_account_id or (cfg.sales_account_id if cfg else None),
            inventory_account_id=inventory_account_id or (cfg.inventory_account_id if cfg else None),
            cogs_account_id=cogs_account_id or (cfg.cogs_account_id if cfg else None),
            product_type=product_type or "simple", can_be_sold=can_be_sold, can_be_purchased=can_be_purchased,
            issue_method=issue_method, track_expiry=track_expiry, shelf_life_days=shelf_life_days, expiry_alert_days=expiry_alert_days, cost_method=cost_method,
        )
        s.add(p)
        s.flush()
        base_unit = s.query(ProductUnit).filter(ProductUnit.name == unit).first()
        if not base_unit:
            base_unit = s.query(ProductUnit).filter(ProductUnit.is_active.is_(True)).first()
        if base_unit:
            rows = unit_lines or [{"unit_id": base_unit.id, "factor_to_base": 1.0, "sale_price": sale_price, "cost_price": cost_price, "is_default": True}]
            for row in rows:
                s.add(ProductUnitLine(product_id=p.id, unit_id=int(row["unit_id"]), factor_to_base=float(row.get("factor_to_base",1) or 1),
                                      sale_price=float(row["sale_price"]) if row.get("sale_price") not in (None,"") else None,
                                      cost_price=float(row["cost_price"]) if row.get("cost_price") not in (None,"") else None,
                                      barcode=row.get("barcode","") or "", is_default=bool(row.get("is_default",False))))
        s.commit()
        s.refresh(p)
        return p.id


def update_product(product_id, **fields):
    require_action("products", "edit")
    from . import field_access as _fa
    if not _fa.can_see("cost_price"):
        fields = {k: v for k, v in fields.items() if k != "cost_price"}
    with get_session() as s:
        p = s.get(Product, product_id)
        if not p:
            raise ValueError("الصنف غير موجود")
        for k, v in fields.items():
            setattr(p, k, v)
        s.commit()


def product_has_movements(product_id):
    """هل الصنف عليه حركة (مخزون أو فواتير)؟ - بيمنع تغيير الوحدة الأساسية بعد التعامل عليه."""
    with get_session() as s:
        pid = int(product_id)
        return bool(s.query(StockMove).filter(StockMove.product_id == pid).count()
                    or s.query(SalesInvoiceItem).filter(SalesInvoiceItem.product_id == pid).count()
                    or s.query(PurchaseInvoiceItem).filter(PurchaseInvoiceItem.product_id == pid).count())


def update_product_details(product_id, sku, name, category_id=None, unit=None, cost_price=0.0, sale_price=0.0, reorder_point=0.0,
                           tax_rate=15.0, sales_account_id=None, inventory_account_id=None, cogs_account_id=None,
                           can_be_sold=None, can_be_purchased=None, issue_method=None, track_expiry=None, shelf_life_days="__keep__", expiry_alert_days=None, cost_method=None):
    """تعديل بيانات صنف من شاشة الأصناف مع التحقق:
    - الكود والاسم مطلوبين، والكود ما يتكررش مع صنف تاني.
    - الأسعار وحد إعادة الطلب مش سالبين، والضريبة بين 0 و100.
    - الوحدة الأساسية ما تتغيّرش لو الصنف عليه حركة (مخزون/فواتير).
    - تعديل سعر التكلفة/البيع بيتطبّق كمان على سطر الوحدة الأساسية (اللي بتاخد منه الفواتير سعرها)
      من غير ما يلمس أسعار الوحدات التانية (كرتونة مثلًا).
    - الحسابات: القيمة الفاضية = من غير تغيير (الافتراضي بيجي من الإعدادات)."""
    require_action("products", "edit")
    sku = (sku or "").strip(); name = (name or "").strip()
    if not sku or not name:
        raise ValueError("الكود واسم الصنف مطلوبان")
    cost_price = float(cost_price or 0); sale_price = float(sale_price or 0); reorder_point = float(reorder_point or 0); tax_rate = float(tax_rate or 0)
    new_batch = None
    if issue_method is not None or track_expiry is not None or shelf_life_days != "__keep__" or expiry_alert_days is not None or cost_method is not None:
        with get_session() as s0:
            cur = s0.get(Product, int(product_id))
        if cur:
            new_batch = _check_batch_settings(issue_method if issue_method is not None else cur.issue_method,
                                              track_expiry if track_expiry is not None else cur.track_expiry,
                                              cur.shelf_life_days if shelf_life_days == "__keep__" else shelf_life_days,
                                              expiry_alert_days if expiry_alert_days is not None else cur.expiry_alert_days,
                                              cost_method if cost_method is not None else (cur.cost_method or "auto"))
    if cost_price < 0 or sale_price < 0:
        raise ValueError("الأسعار لا يمكن أن تكون سالبة")
    if reorder_point < 0:
        raise ValueError("حد إعادة الطلب لا يمكن أن يكون سالبًا")
    if not 0 <= tax_rate <= 100:
        raise ValueError("نسبة الضريبة لازم تكون بين 0 و100")
    with get_session() as s:
        p = s.query(Product).options(joinedload(Product.unit_lines)).filter(Product.id == int(product_id)).first()
        if not p:
            raise ValueError("الصنف غير موجود")
        dup = s.query(Product).filter(Product.sku == sku, Product.id != p.id).first()
        if dup:
            raise ValueError(f'الكود "{sku}" مستخدم لصنف تاني ({dup.name})')
        for label, acc_id in (("حساب المبيعات", sales_account_id), ("حساب المخزون", inventory_account_id), ("حساب تكلفة المبيعات", cogs_account_id)):
            if acc_id and not s.get(Account, int(acc_id)):
                raise ValueError(f"{label} غير موجود")
        base_lines = [u for u in p.unit_lines if abs((u.factor_to_base or 1) - 1.0) < 1e-9]
        if unit and unit != p.unit:
            if product_has_movements(p.id):
                raise ValueError("الوحدة الأساسية مينفعش تتغيّر بعد ما الصنف يتحرّك (مخزون أو فواتير) - ضيف وحدة جديدة من 'وحدات الصنف' بدل كده")
            new_unit = s.query(ProductUnit).filter(ProductUnit.name == unit).first()
            if not new_unit:
                raise ValueError("الوحدة غير موجودة")
            if any(u.unit_id == new_unit.id and u not in base_lines for u in p.unit_lines):
                raise ValueError("الوحدة دي مستخدمة كوحدة تانية للصنف - عدّلها من 'وحدات الصنف'")
            for u in base_lines:
                u.unit_id = new_unit.id
            p.unit = unit
        from . import field_access as _fa
        if not _fa.can_see("cost_price"):
            cost_price = float(p.cost_price or 0)       # التكلفة مخفية عن المستخدم: تفضل كما هي
        if cost_price != (p.cost_price or 0):
            for u in base_lines:
                u.cost_price = cost_price
        if sale_price != (p.sale_price or 0):
            for u in base_lines:
                u.sale_price = sale_price
        p.sku = sku; p.name = name; p.category_id = int(category_id) if category_id else None
        p.cost_price = cost_price; p.sale_price = sale_price; p.reorder_point = reorder_point; p.tax_rate = tax_rate
        if sales_account_id: p.sales_account_id = int(sales_account_id)
        if inventory_account_id: p.inventory_account_id = int(inventory_account_id)
        if cogs_account_id: p.cogs_account_id = int(cogs_account_id)
        if new_batch:
            p.issue_method, p.track_expiry, p.shelf_life_days, p.expiry_alert_days, p.cost_method = new_batch
        if can_be_sold is not None: p.can_be_sold = bool(can_be_sold)
        if can_be_purchased is not None: p.can_be_purchased = bool(can_be_purchased)
        s.commit()


def deactivate_product(product_id):
    update_product(product_id, is_active=False)


# ============================== Locations ==============================
def list_locations(branch_id=None, active_only=True):
    with get_session() as s:
        q=s.query(Location).options(joinedload(Location.branch), joinedload(Location.cost_center))
        if active_only: q = q.filter(Location.is_active.is_(True))
        if branch_id:q=q.filter(Location.branch_id==int(branch_id))
        elif user_branch_ids():q=q.filter(((Location.branch_id.is_(None))|(Location.branch_id.in_(user_branch_ids()))))
        locations = q.order_by(Location.name).all()
        s.expunge_all()
        return locations


def create_location(name, branch_id=None, cost_center_id=None, is_default=False):
    require_action("stock_moves", "create")
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم المخزن مطلوب")
    branch_id=branch_id or default_branch_id()
    if branch_id and not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    if cost_center_id and not allowed_cost_center(cost_center_id): raise PermissionError("مركز التكلفة غير مسموح لهذا المستخدم")
    with get_session() as s:
        if s.query(Location).filter(Location.name == name).first():
            raise ValueError(f'يوجد مخزن بنفس الاسم "{name}" بالفعل')
        if is_default:
            s.query(Location).update({"is_default": False})
        loc = Location(name=name, branch_id=branch_id, cost_center_id=cost_center_id, is_default=is_default, is_active=True)
        s.add(loc)
        s.commit()
        s.refresh(loc)
        return loc.id


def update_location(location_id, **fields):
    require_action("stock_moves", "edit")
    with get_session() as s:
        loc = s.get(Location, location_id)
        if not loc:
            raise ValueError("المخزن غير موجود")
        if fields.get("is_default"):
            s.query(Location).filter(Location.id != location_id).update({"is_default": False})
        for k, v in fields.items():
            setattr(loc, k, v)
        s.commit()


def delete_location(location_id):
    require_action("stock_moves", "delete")
    with get_session() as s:
        used = s.query(StockMove).filter(StockMove.location_id == location_id).count()
        if used:
            raise ValueError(f"لا يمكن حذف المخزن - له {used} حركة مخزون مسجّلة. عطّله بدل الحذف.")
        loc = s.get(Location, location_id)
        if loc:
            s.delete(loc)
            s.commit()


def deactivate_location(location_id):
    update_location(location_id, is_active=False)


def default_location_id(branch_id=None):
    with get_session() as s:
        q=s.query(Location).filter(Location.is_default.is_(True))
        if branch_id: q=q.filter(Location.branch_id==int(branch_id))
        loc=q.first()
        if loc: return loc.id
        q=s.query(Location)
        if branch_id:q=q.filter(Location.branch_id==int(branch_id))
        elif user_branch_ids():q=q.filter(((Location.branch_id.is_(None))|(Location.branch_id.in_(user_branch_ids()))))
        loc=q.order_by(Location.id).first()
        return loc.id if loc else None

# ============================== Stock ==============================
# ======================================================================
# تتبّع التشغيلات والصلاحية وطرق الإخراج (FIFO / LIFO / FEFO)
# الصنف المتتبَّع (طريقة إخراج غير "none" أو له صلاحية): كل حركة دخول بتسجّل تشغيلة (رقم + تاريخ صلاحية + تكلفة)، وكل حركة خروج بتتوزّع
# تلقائي على التشغيلات حسب طريقة الصنف: FIFO الأقدم دخولًا، LIFO الأحدث دخولًا، FEFO الأقرب انتهاءً. المنتهي الصلاحية مش بيتصرف في
# البيع والتصنيع والتحويل (بيتصرف بس في التلف والجرد). رصيد الصنف قبل تفعيل التتبّع بيظهر كتشغيلة "رصيد سابق".
# ======================================================================
LEGACY_BATCH = "رصيد سابق"
BATCH_METHODS = {"none": "بدون تتبّع تشغيلات", "fifo": "FIFO - الأقدم دخولًا يخرج أولًا", "lifo": "LIFO - الأحدث دخولًا يخرج أولًا", "fefo": "FEFO - الأقرب انتهاءً يخرج أولًا"}


COST_METHODS = {"auto": "الافتراضي (سعر التكلفة المسجّل في الصنف)", "avg": "متوسط مرجح (بيتحدّث مع كل استلام)", "fifo": "FIFO - الوارد أولًا صادر أولًا", "lifo": "LIFO - الوارد أخيرًا صادر أولًا"}


def is_batch_tracked(p):
    return bool(p) and (((getattr(p, "issue_method", None) or "none") in ("fifo", "lifo", "fefo")) or bool(getattr(p, "track_expiry", False))
                        or (getattr(p, "cost_method", None) or "auto") in ("fifo", "lifo"))


def effective_issue_method(p):
    m = getattr(p, "issue_method", None) or "none"
    if m in ("fifo", "lifo", "fefo"):
        return m
    cm = getattr(p, "cost_method", None) or "auto"
    return cm if cm in ("fifo", "lifo") else "fefo"        # تكلفة FIFO/LIFO من غير طريقة إخراج = نفس الطريقة، وصنف له صلاحية بس = الأقرب انتهاءً


def uses_batch_cost(p):
    """تكلفة البضاعة المباعة من تكلفة التشغيلات الفعلية: لأي صنف متتبَّع إلا لو طريقة تكلفته "متوسط مرجح" (بيستخدم سعر التكلفة المتحرك)."""
    return is_batch_tracked(p) and (getattr(p, "cost_method", None) or "auto") != "avg"


def _batch_state(product_id, location_id):
    """تشغيلات الصنف في مخزن (المتبقي > 0): [{batch_no, expiry_date, remaining, unit_cost, received_at}] بما فيها "رصيد سابق"."""
    from .db import StockMoveBatch
    pid, lid = int(product_id), int(location_id)
    with get_session() as s:
        q = (s.query(StockMoveBatch.batch_no, StockMoveBatch.expiry_date,
                     func.sum(case((StockMoveBatch.direction == "in", StockMoveBatch.quantity), else_=-StockMoveBatch.quantity)),
                     func.sum(case((StockMoveBatch.direction == "in", StockMoveBatch.quantity * StockMoveBatch.unit_cost), else_=0)),
                     func.sum(case((StockMoveBatch.direction == "in", StockMoveBatch.quantity), else_=0)),
                     func.min(case((StockMoveBatch.direction == "in", StockMoveBatch.received_at), else_=None)))
             .join(StockMove, StockMove.id == StockMoveBatch.move_id)
             .filter(StockMoveBatch.product_id == pid, StockMoveBatch.location_id == lid, StockMove.voided.is_(False))
             .group_by(StockMoveBatch.batch_no, StockMoveBatch.expiry_date))
        rows = q.all()
    out, tracked_net = [], 0.0
    for bn, exp, net, val_in, q_in, first_in in rows:
        net = float(net or 0)
        if bn != LEGACY_BATCH:
            tracked_net += net
        if net > 1e-9 and bn != LEGACY_BATCH:
            out.append({"batch_no": bn or "", "expiry_date": exp, "remaining": net, "unit_cost": (float(val_in or 0) / float(q_in)) if q_in else 0.0,
                        "received_at": first_in or datetime.datetime.min})
    legacy = get_product_balance(pid, lid) - tracked_net      # الرصيد اللي ملهوش تشغيلات (قبل التتبّع) = الرصيد الكلي - المتتبَّع
    if legacy > 1e-9:
        with get_session() as s:
            cost = s.query(Product.cost_price).filter(Product.id == pid).scalar() or 0.0
        out.append({"batch_no": LEGACY_BATCH, "expiry_date": None, "remaining": legacy, "unit_cost": float(cost), "received_at": datetime.datetime.min})
    return out


def _is_expired(b, ref_dt=None):
    exp = b.get("expiry_date")
    return bool(exp) and exp.date() < (ref_dt or datetime.datetime.now()).date()


def _allocate_batches(product, location_id, base_qty, allow_expired=False, ref_dt=None):
    """يوزّع كمية الخروج على التشغيلات حسب طريقة الصنف. بيرجّع [{batch_no, expiry_date, quantity, unit_cost}]."""
    method = effective_issue_method(product)
    batches = _batch_state(product.id, location_id)
    valid = [b for b in batches if allow_expired or not _is_expired(b, ref_dt)]
    mx, mn = datetime.datetime.max, datetime.datetime.min
    if method == "fifo":
        valid.sort(key=lambda b: (b["received_at"] or mn, b["expiry_date"] or mx))
    elif method == "lifo":
        valid.sort(key=lambda b: (b["received_at"] or mn), reverse=True)
    else:
        valid.sort(key=lambda b: (b["expiry_date"] is None, b["expiry_date"] or mx, b["received_at"] or mn))
    need, lines = float(base_qty), []
    for b in valid:
        if need <= 1e-9:
            break
        take = min(b["remaining"], need)
        lines.append({"batch_no": b["batch_no"], "expiry_date": b["expiry_date"], "quantity": take, "unit_cost": b["unit_cost"]})
        need -= take
    if need > 1e-9:
        have = sum(b["remaining"] for b in valid)
        expired_qty = sum(b["remaining"] for b in batches if _is_expired(b, ref_dt)) if not allow_expired else 0.0
        msg = f"المتاح من «{product.name}» للصرف ({have:g}) أقل من المطلوب ({float(base_qty):g})"
        if expired_qty > 1e-9:
            msg += f" - فيه {expired_qty:g} منتهي الصلاحية مش بيتصرف"
        raise ValueError(msg)
    return lines


def get_move_batch_lines(move_id):
    from .db import StockMoveBatch
    with get_session() as s:
        return [{"batch_no": b.batch_no or "", "expiry_date": b.expiry_date, "quantity": b.quantity, "unit_cost": b.unit_cost}
                for b in s.query(StockMoveBatch).filter(StockMoveBatch.move_id == int(move_id)).all()]


def _reference_batch_lines(reference, product_id, direction):
    """مجموع سطور التشغيلات لحركات مرجع معيّن (فاتورة/سند) لصنف - لعكسها بنفس التشغيلات عند الإلغاء."""
    from .db import StockMoveBatch
    agg = {}
    with get_session() as s:
        rows = (s.query(StockMoveBatch).join(StockMove, StockMove.id == StockMoveBatch.move_id)
                .filter(StockMove.reference == reference, StockMove.product_id == int(product_id), StockMove.direction == direction, StockMove.voided.is_(False)).all())
        for b in rows:
            k = (b.batch_no or "", b.expiry_date)
            cur = agg.setdefault(k, {"batch_no": b.batch_no or "", "expiry_date": b.expiry_date, "quantity": 0.0, "cost_value": 0.0})
            cur["quantity"] += b.quantity; cur["cost_value"] += b.quantity * (b.unit_cost or 0)
    return [{"batch_no": v["batch_no"], "expiry_date": v["expiry_date"], "quantity": v["quantity"], "unit_cost": (v["cost_value"] / v["quantity"]) if v["quantity"] else 0.0} for v in agg.values()]


def _reference_batch_cost(reference, product_id):
    """تكلفة بضاعة مباعة من التشغيلات الفعلية اللي اتصرفت لمرجع معيّن (FIFO/LIFO/FEFO) - أو None لو مفيش تشغيلات."""
    lines = _reference_batch_lines(reference, product_id, "out")
    return sum(l["quantity"] * l["unit_cost"] for l in lines) if lines else None


def list_batches(location_id=None, product_id=None, status=None, search=None, include_legacy=True):
    """تقرير التشغيلات والصلاحية: كل تشغيلة متبقّي منها كمية: الصنف، المخزن، رقم التشغيلة، الصلاحية، المتبقي، التكلفة، الأيام المتبقية، الحالة.
    status: expired | near (قارب على الانتهاء حسب تنبيه الصنف) | ok | none (من غير تاريخ صلاحية)."""
    from .db import StockMoveBatch
    today = datetime.date.today()
    with get_session() as s:
        prods = s.query(Product).filter(Product.is_active.is_(True))
        if product_id:
            prods = prods.filter(Product.id == int(product_id))
        prods = [p for p in prods.all() if is_batch_tracked(p)]
        locs = {l.id: l for l in s.query(Location).all()}
        pids = [p.id for p in prods]
        pairs = set()
        if pids:
            q = s.query(StockMoveBatch.product_id, StockMoveBatch.location_id).filter(StockMoveBatch.product_id.in_(pids)).distinct()
            if location_id:
                q = q.filter(StockMoveBatch.location_id == int(location_id))
            pairs = set(q.all())
    # أصناف متتبَّعة ليها رصيد سابق (من غير سطور تشغيلات)
    if include_legacy and pids:
        bal = get_balances_map(int(location_id) if location_id else None, by_location=True, product_ids=pids)
        for (pid, lid), b in bal.items():
            if b > 1e-9 and (not location_id or lid == int(location_id)):
                pairs.add((pid, lid))
    pmap = {p.id: p for p in prods}
    rows = []
    for pid, lid in sorted(pairs):
        p = pmap.get(pid)
        if not p:
            continue
        for b in _batch_state(pid, lid):
            if b["batch_no"] == LEGACY_BATCH and not include_legacy:
                continue
            exp = b["expiry_date"]
            days = (exp.date() - today).days if exp else None
            st = "none" if exp is None else ("expired" if days < 0 else ("near" if days <= int(p.expiry_alert_days or 30) else "ok"))
            rows.append({"product": p, "location": locs.get(lid), "batch_no": b["batch_no"], "expiry_date": exp, "days_left": days, "status": st,
                         "remaining": b["remaining"], "unit_cost": b["unit_cost"], "value": b["remaining"] * b["unit_cost"], "received_at": None if b["received_at"] == datetime.datetime.min else b["received_at"]})
    if status:
        rows = [r for r in rows if r["status"] == status]
    if search and search.strip():
        t = search.strip().lower()
        rows = [r for r in rows if t in (r["product"].sku + " " + r["product"].name + " " + (r["batch_no"] or "")).lower()]
    rows.sort(key=lambda r: (r["expiry_date"] is None, r["expiry_date"] or datetime.datetime.max, r["product"].sku))
    return rows


def expiry_summary():
    """أرقام الكروت: كمية وقيمة المنتهي والقارب على الانتهاء، وعدد التشغيلات."""
    rows = list_batches()
    out = {"expired_n": 0, "expired_value": 0.0, "near_n": 0, "near_value": 0.0, "batches": len(rows)}
    for r in rows:
        if r["status"] == "expired":
            out["expired_n"] += 1; out["expired_value"] += r["value"]
        elif r["status"] == "near":
            out["near_n"] += 1; out["near_value"] += r["value"]
    return out


def create_stock_move(product_id, location_id, direction, quantity,
                       unit_cost=0.0, reference="", note="", branch_id=None, cost_center_id=None, _internal=False, unit_id=None, move_date=None,
                       batch_no=None, expiry_date=None, batch_lines=None, allow_expired=False, require_expiry=False, update_cost=None):
    if not _internal: require_action("stock_moves", "create")
    if direction not in ("in", "out"):
        raise ValueError("الاتجاه لازم يكون 'in' أو 'out'")
    if quantity <= 0:
        raise ValueError("الكمية لازم تكون أكبر من صفر")
    base_quantity, selected_unit_name, factor = convert_to_base_quantity(product_id, quantity, unit_id)
    if direction == "out":
        current = get_product_balance(product_id, location_id, branch_id)
        if current < base_quantity:
            raise ValueError(
                f"الكمية المتاحة بالوحدة الأساسية ({current:g}) أقل من المطلوب ({base_quantity:g})"
            )
    branch_id = branch_id or default_branch_id()
    cost_center_id = cost_center_id or default_cost_center_id()
    if branch_id and not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    if cost_center_id and not allowed_cost_center(cost_center_id): raise PermissionError("مركز التكلفة غير مسموح لهذا المستخدم")
    with get_session() as s:
        loc=s.get(Location,int(location_id))
        if loc and loc.branch_id and branch_id and int(loc.branch_id)!=int(branch_id): raise ValueError("المخزن لا يتبع الفرع المختار")
        prod = s.get(Product, int(product_id))
        tracked = is_batch_tracked(prod)
        lines = None            # سطور التشغيلات (لو الصنف متتبَّع): None = من غير سطور
        ref_dt = move_date or datetime.datetime.now()
        if tracked:
            base_cost = (float(unit_cost) / factor) if factor else float(unit_cost)
            if batch_lines is not None:
                lines = [dict(l) for l in batch_lines]                       # سطور جاهزة (إلغاء فاتورة / تحويل): بنستخدمها زي ما هي
                if lines and abs(sum(l["quantity"] for l in lines) - base_quantity) > 1e-6:
                    raise ValueError("سطور التشغيلات لا تطابق كمية الحركة")
                if direction == "out" and lines:
                    state = {(b["batch_no"], b["expiry_date"]): b["remaining"] for b in _batch_state(prod.id, location_id)}
                    for l in lines:
                        if state.get((l["batch_no"], l["expiry_date"]), 0.0) + 1e-9 < l["quantity"]:
                            raise ValueError(f"التشغيلة «{l['batch_no'] or '-'}» من «{prod.name}» مبقاش منها الكمية المطلوبة (اتصرف جزء منها)")
            elif direction == "in":
                exp = expiry_date
                if exp is None and prod.shelf_life_days:
                    exp = ref_dt + datetime.timedelta(days=int(prod.shelf_life_days))
                if exp is None and (require_expiry and prod.track_expiry):
                    raise ValueError(f"حدد تاريخ الصلاحية للصنف «{prod.name}» (الصنف متتبَّع الصلاحية)")
                lines = [{"batch_no": (batch_no or "").strip() or f"{(reference or 'دفعة')}", "expiry_date": exp, "quantity": base_quantity, "unit_cost": base_cost}]
            else:
                lines = _allocate_batches(prod, location_id, base_quantity, allow_expired=allow_expired, ref_dt=ref_dt)
        m = StockMove(
            product_id=product_id, location_id=location_id, branch_id=branch_id, cost_center_id=cost_center_id, direction=direction,
            quantity=base_quantity, unit_id=(int(unit_id) if unit_id else None), unit_factor=factor,
            unit_cost=(float(unit_cost) / factor if factor else float(unit_cost)), reference=reference, note=note,
        )
        if move_date:
            m.date = move_date            # تاريخ المستند (مش تاريخ التسجيل)
        s.add(m)
        s.flush()
        # المتوسط المرجح المتحرك: استلام بتكلفة بيحدّث سعر تكلفة الصنف = (رصيد الصنف الكلي × تكلفته + الوارد × تكلفته) / (الرصيد + الوارد)
        if update_cost is None:
            update_cost = (not _internal) and direction == "in"
        if direction == "in" and update_cost and prod is not None and (prod.cost_method or "auto") == "avg" and float(unit_cost or 0) > 0:
            bal_before = float(s.query(func.coalesce(func.sum(case((StockMove.direction == "in", StockMove.quantity), else_=-StockMove.quantity)), 0.0))
                               .filter(StockMove.product_id == int(product_id), StockMove.voided.is_(False), StockMove.id != m.id).scalar() or 0.0)
            in_cost = float(unit_cost) / factor if factor else float(unit_cost)
            held = max(bal_before, 0.0)
            new_cost = round(((held * float(prod.cost_price or 0)) + base_quantity * in_cost) / (held + base_quantity), 4) if (held + base_quantity) > 0 else in_cost
            prod.cost_price = new_cost
            for ul in s.query(ProductUnitLine).filter(ProductUnitLine.product_id == prod.id, ProductUnitLine.factor_to_base == 1.0).all():
                ul.cost_price = new_cost
        if lines:
            from .db import StockMoveBatch
            for l in lines:
                s.add(StockMoveBatch(move_id=m.id, product_id=int(product_id), location_id=int(location_id), direction=direction, batch_no=l["batch_no"],
                                     expiry_date=l["expiry_date"], quantity=float(l["quantity"]), unit_cost=float(l.get("unit_cost") or 0), received_at=m.date or ref_dt))
        s.commit()
        s.refresh(m)
        return m.id


def create_stock_transfer(product_id, from_location_id, to_location_id, quantity, unit_cost=0.0, note="", unit_id=None):
    """
    تحويل صنف بين مخزنين: بيسجّل حركة خروج من المخزن المصدر وحركة دخول
    للمخزن الوجهة بنفس المرجع، كل واحدة بفرع/مركز تكلفة المخزن بتاعها.
    """
    require_action("stock_moves", "create")
    if not from_location_id or not to_location_id:
        raise ValueError("اختر المخزن المصدر والمخزن الوجهة")
    if int(from_location_id) == int(to_location_id):
        raise ValueError("لازم تختار مخزن مصدر ومخزن وجهة مختلفين")

    with get_session() as s:
        from_loc = s.get(Location, int(from_location_id))
        to_loc = s.get(Location, int(to_location_id))
        if not from_loc or not to_loc:
            raise ValueError("مخزن غير موجود")
        from_branch, from_cc = from_loc.branch_id, from_loc.cost_center_id
        to_branch, to_cc = to_loc.branch_id, to_loc.cost_center_id

    reference = f"TRF-{datetime.datetime.now():%Y%m%d%H%M%S}"
    out_id = create_stock_move(
        product_id, from_location_id, "out", quantity, unit_cost=unit_cost,
        reference=reference, note=note or "تحويل بين المخازن",
        branch_id=from_branch, cost_center_id=from_cc, unit_id=unit_id,
    )
    in_id = create_stock_move(
        product_id, to_location_id, "in", quantity, unit_cost=unit_cost,
        reference=reference, note=note or "تحويل بين المخازن",
        branch_id=to_branch, cost_center_id=to_cc, unit_id=unit_id,
        batch_lines=get_move_batch_lines(out_id) or None, update_cost=False,
    )
    return {"reference": reference, "out_move_id": out_id, "in_move_id": in_id}


def create_stock_transfer_batch(items, from_location_id, to_location_id, note="", transfer_date=None):
    """تحويل أكتر من صنف بين مخزنين في مستند واحد (مرجع واحد TRF-...): items = [{product_id, quantity}].
    بيتحقق من رصيد كل الأصناف الأول (مع جمع الأصناف المكررة) وبعدين بيسجّل الحركات - يا الكل يا ولا حاجة."""
    require_action("stock_moves", "create")
    if not items:
        raise ValueError("أضف صنف واحد على الأقل للتحويل")
    if not from_location_id or not to_location_id:
        raise ValueError("اختر المخزن المصدر والمخزن الوجهة")
    if int(from_location_id) == int(to_location_id):
        raise ValueError("لازم تختار مخزن مصدر ومخزن وجهة مختلفين")
    with get_session() as s:
        from_loc = s.get(Location, int(from_location_id)); to_loc = s.get(Location, int(to_location_id))
        if not from_loc or not to_loc:
            raise ValueError("مخزن غير موجود")
        from_branch, from_cc, to_branch, to_cc = from_loc.branch_id, from_loc.cost_center_id, to_loc.branch_id, to_loc.cost_center_id
    totals = {}
    for n, it in enumerate(items, 1):
        qty = float(it.get("quantity") or 0)
        if qty <= 0:
            raise ValueError(f"السطر {n}: الكمية لازم تكون أكبر من صفر")
        pid = int(it["product_id"])
        p = get_product(pid)
        if not p:
            raise ValueError(f"السطر {n}: الصنف غير موجود")
        if p.product_type == "service":
            raise ValueError(f"السطر {n}: «{p.name}» خدمة - مفيش تحويل مخزني للخدمات")
        totals[pid] = totals.get(pid, 0.0) + qty
    for pid, qty in totals.items():
        bal = get_product_balance(pid, int(from_location_id), from_branch)
        if bal < qty:
            raise ValueError(f"الرصيد المتاح من «{get_product(pid).name}» في المخزن المصدر ({bal:g}) أقل من المطلوب تحويله ({qty:g})")
    reference = f"TRF-{datetime.datetime.now():%Y%m%d%H%M%S}"
    with get_session() as s:                       # مرجع فريد
        n = 1
        while s.query(StockMove).filter(StockMove.reference == reference).first():
            n += 1; reference = f"TRF-{datetime.datetime.now():%Y%m%d%H%M%S}-{n}"
    for pid, qty in totals.items():
        out_id = create_stock_move(pid, int(from_location_id), "out", qty, unit_cost=0.0, reference=reference, note=note or "تحويل بين المخازن",
                                   branch_id=from_branch, cost_center_id=from_cc, move_date=transfer_date)
        create_stock_move(pid, int(to_location_id), "in", qty, unit_cost=0.0, reference=reference, note=note or "تحويل بين المخازن",
                          branch_id=to_branch, cost_center_id=to_cc, move_date=transfer_date, batch_lines=get_move_batch_lines(out_id) or None, update_cost=False)
    return {"reference": reference, "lines": len(totals)}


def list_stock_transfers(limit=200):
    """يرجّع سجل عمليات التحويل (كل صف = التحويل كامل: من - إلى - الكمية)
    عن طريق تجميع حركات الخروج والدخول اللي ليها نفس مرجع TRF-."""
    with get_session() as s:
        out_moves = s.query(StockMove).options(
            joinedload(StockMove.product), joinedload(StockMove.location)
        ).filter(StockMove.reference.like("TRF-%"), StockMove.direction == "out").order_by(StockMove.date.desc()).limit(limit).all()

        result = []
        for om in out_moves:
            im = s.query(StockMove).options(joinedload(StockMove.location)).filter(
                StockMove.reference == om.reference, StockMove.direction == "in", StockMove.product_id == om.product_id
            ).first()
            result.append({
                "date": om.date, "reference": om.reference,
                "product": om.product.name if om.product else "-",
                "sku": om.product.sku if om.product else "-",
                "from_location": om.location.name if om.location else "-",
                "to_location": im.location.name if im and im.location else "-",
                "quantity": om.quantity, "unit_cost": om.unit_cost,
            })
        return result


def list_stock_moves(product_id=None, location_id=None, branch_id=None, limit=200):
    # تحميل العلاقات قبل إغلاق الـ Session حتى لا يحدث DetachedInstanceError
    # عند عرض اسم الصنف أو اسم المخزن في الواجهة.
    with get_session() as s:
        q = (
            s.query(StockMove)
            .options(
                joinedload(StockMove.product),
                joinedload(StockMove.location),
            )
            .order_by(StockMove.date.desc())
        )
        if product_id:
            q = q.filter(StockMove.product_id == product_id)
        if location_id:
            q = q.filter(StockMove.location_id == location_id)
        if branch_id:
            q=q.filter(StockMove.branch_id==int(branch_id))
        elif user_branch_ids():
            q=q.filter(((StockMove.branch_id.is_(None))|(StockMove.branch_id.in_(user_branch_ids()))))
        return q.limit(limit).all()


def get_product_balance(product_id, location_id=None, branch_id=None, as_of=None):
    with get_session() as s:
        q = s.query(
            func.coalesce(func.sum(
                case((StockMove.direction == "in", StockMove.quantity), else_=0)
            ), 0)
            - func.coalesce(func.sum(
                case((StockMove.direction == "out", StockMove.quantity), else_=0)
            ), 0)
        ).filter(StockMove.product_id == product_id, StockMove.voided.is_(False))
        if as_of is not None:
            q = q.filter(StockMove.date <= as_of)          # الرصيد في تاريخ معيّن (لحد as_of)
        if location_id:
            q = q.filter(StockMove.location_id == location_id)
        if branch_id:
            q = q.filter(StockMove.branch_id == int(branch_id))
        elif user_branch_ids():
            q = q.filter(((StockMove.branch_id.is_(None))|(StockMove.branch_id.in_(user_branch_ids()))))
        return float(q.scalar() or 0)


def get_balances_map(location_id=None, branch_id=None, by_location=False, product_ids=None, as_of=None):
    """أرصدة كل الأصناف باستعلام واحد مجمّع (بدل استعلام لكل صنف - كان بياخد ثواني مع آلاف الأصناف).
    بنفس فلاتر get_product_balance. بيرجّع {product_id: رصيد} أو {(product_id, location_id): رصيد} لو by_location."""
    signed = func.sum(case((StockMove.direction == "in", StockMove.quantity), (StockMove.direction == "out", -StockMove.quantity), else_=0))
    with get_session() as s:
        cols = [StockMove.product_id] + ([StockMove.location_id] if by_location else [])
        q = s.query(*cols, signed).filter(StockMove.voided.is_(False))
        if as_of is not None:
            q = q.filter(StockMove.date <= as_of)
        if location_id:
            q = q.filter(StockMove.location_id == int(location_id))
        if branch_id:
            q = q.filter(StockMove.branch_id == int(branch_id))
        elif user_branch_ids():
            q = q.filter(((StockMove.branch_id.is_(None)) | (StockMove.branch_id.in_(user_branch_ids()))))
        if product_ids is not None:
            q = q.filter(StockMove.product_id.in_([int(i) for i in product_ids]))
        q = q.group_by(*cols)
        if by_location:
            return {(r[0], r[1]): float(r[2] or 0) for r in q.all()}
        return {r[0]: float(r[1] or 0) for r in q.all()}


def get_stock_balance_report(location_id=None, low_stock_only=False, branch_id=None, as_of=None):
    with get_session() as s:
        products = s.query(Product).filter(Product.is_active.is_(True)).order_by(Product.sku).all()
    balances = get_balances_map(location_id, branch_id, as_of=as_of)
    report = []
    for p in products:
        balance = balances.get(p.id, 0.0)
        is_low = p.reorder_point > 0 and balance <= p.reorder_point
        if low_stock_only and not is_low:
            continue
        report.append({
            "product": p, "balance": balance, "is_low": is_low,
            "value": balance * (p.cost_price or 0),
        })
    return report


def get_stock_balance_by_warehouse(low_stock_only=False, branch_id=None, as_of=None):
    """تفصيل رصيد كل صنف حسب كل مخزن على حدة (صف واحد لكل صنف/مخزن له
    رصيد غير صفري)."""
    with get_session() as s:
        products = s.query(Product).filter(Product.is_active.is_(True)).order_by(Product.sku).all()
    locations = list_locations()
    balances = get_balances_map(None, branch_id, by_location=True, as_of=as_of)
    report = []
    for loc in locations:
        for p in products:
            balance = balances.get((p.id, loc.id), 0.0)
            if abs(balance) < 0.0001:
                continue
            is_low = p.reorder_point > 0 and balance <= p.reorder_point
            if low_stock_only and not is_low:
                continue
            report.append({
                "product": p, "location": loc, "balance": balance, "is_low": is_low,
                "value": balance * (p.cost_price or 0),
            })
    return report


def _fa_can_see(field):
    from . import field_access
    return field_access.can_see(field)


def get_inventory_kpis(branch_id=None):
    with get_session() as s:
        total_products = s.query(Product).filter(Product.is_active.is_(True)).count()
    report = get_stock_balance_report(branch_id=branch_id)
    return {
        "total_products": total_products,
        "total_stock_value": sum(r["value"] for r in report) if _fa_can_see("cost_price") else None,
        "low_stock_count": sum(1 for r in report if r["is_low"]),
    }


# ============================== Customers ==============================
def list_customers(search=None, active_only=True):
    with get_session() as s:
        q = s.query(Customer)
        if active_only:
            q = q.filter(Customer.is_active.is_(True))
        if search:
            like = f"%{search}%"
            q = q.filter(Customer.name.like(like) | Customer.phone.like(like))
        return q.order_by(Customer.name).all()


def _check_b2b_requirements(party_type, vat_number, address):
    """عملاء B2B (شركات) محتاجين الرقم الضريبي والعنوان الوطني إجباريين
    حسب متطلبات الفاتورة الضريبية القياسية لهيئة الزكاة والضريبة. الرقم
    الضريبي السعودي 15 رقم ويبدأ وينتهي بالرقم 3."""
    if party_type != "company":
        return
    vat_number = (vat_number or "").strip()
    address = (address or "").strip()
    if not vat_number:
        raise ValueError("الرقم الضريبي مطلوب لعملاء B2B (شركات)")
    if not (len(vat_number) == 15 and vat_number.isdigit() and vat_number[0] == "3" and vat_number[-1] == "3"):
        raise ValueError("الرقم الضريبي السعودي لازم يكون 15 رقم ويبدأ وينتهي بالرقم 3")
    if not address:
        raise ValueError("العنوان الوطني مطلوب لعملاء B2B (شركات)")


def _check_credit_fields(limit, days):
    try:
        limit, days = round(float(limit or 0), 2), int(days or 0)
    except (TypeError, ValueError):
        raise ValueError("حد الائتمان والمهلة لازم يكونوا أرقام")
    if limit < 0 or days < 0 or days > 365:
        raise ValueError("حد الائتمان لا يكون سالبًا والمهلة من 0 إلى 365 يوم")
    return limit, days


def create_customer(name, phone="", vat_number="", address="", email="", account_id=None, party_type="individual", price_list_id=None, loyalty_enabled=False, notify_opt_in=False, credit_limit=0.0, credit_days=0, credit_hold=False, crn="", building_no="", district="", city="", postal_code=""):
    require_action("customers", "create")
    credit_limit, credit_days = _check_credit_fields(credit_limit, credit_days)
    if credit_limit or credit_days or credit_hold:
        require_action("credit", "edit")
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم العميل مطلوب")
    if party_type not in ("individual", "company"):
        raise ValueError("نوع العميل غير معروف")
    _check_b2b_requirements(party_type, vat_number, address)
    with get_session() as s:
        c = Customer(name=name, phone=phone or "", vat_number=vat_number or "", party_type=party_type,
                      address=address or "", email=email or "", account_id=int(account_id) if account_id else None,
                      price_list_id=int(price_list_id) if price_list_id else None, loyalty_enabled=bool(loyalty_enabled), notify_opt_in=bool(notify_opt_in), credit_limit=credit_limit, credit_days=credit_days, credit_hold=bool(credit_hold),
                      crn=crn or "", building_no=building_no or "", district=district or "", city=city or "", postal_code=postal_code or "")
        s.add(c)
        s.commit()
        s.refresh(c)
        return c.id


def update_customer(customer_id, **fields):
    require_action("customers", "edit")
    if "party_type" in fields and fields["party_type"] not in ("individual", "company"):
        raise ValueError("نوع العميل غير معروف")
    with get_session() as s:
        c = s.get(Customer, customer_id)
        if not c:
            raise ValueError("العميل غير موجود")
        if any(k in fields for k in ("credit_limit", "credit_days", "credit_hold")):
            lim, dys = _check_credit_fields(fields.get("credit_limit", c.credit_limit), fields.get("credit_days", c.credit_days))
            fields["credit_limit"], fields["credit_days"] = lim, dys
            if "credit_hold" in fields:
                fields["credit_hold"] = bool(fields["credit_hold"])
            if (lim, dys, bool(fields.get("credit_hold", c.credit_hold))) != (float(c.credit_limit or 0), int(c.credit_days or 0), bool(c.credit_hold)):
                require_action("credit", "edit")
        party_type = fields.get("party_type", c.party_type)
        vat_number = fields.get("vat_number", c.vat_number)
        address = fields.get("address", c.address)
        _check_b2b_requirements(party_type, vat_number, address)
        for k, v in fields.items():
            setattr(c, k, v)
        s.commit()


def delete_customer(customer_id):
    require_action("customers", "delete")
    with get_session() as s:
        used = s.query(SalesInvoice).filter(SalesInvoice.customer_id == customer_id).count()
        if used:
            raise ValueError(f"لا يمكن حذف العميل - مرتبط بـ {used} فاتورة")
        c = s.get(Customer, customer_id)
        if c:
            s.delete(c)
            s.commit()


# ============================== Suppliers ==============================
def list_suppliers(search=None, active_only=True):
    with get_session() as s:
        q = s.query(Supplier)
        if active_only:
            q = q.filter(Supplier.is_active.is_(True))
        if search:
            like = f"%{search}%"
            q = q.filter(Supplier.name.like(like) | Supplier.phone.like(like))
        return q.order_by(Supplier.name).all()


def create_supplier(name, phone="", vat_number="", address="", account_id=None):
    """ملحوظة: تصنيف B2C/B2B خاص بالعملاء والمبيعات بس - الموردين مالهمش
    نوع زي ده."""
    require_action("suppliers", "create")
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم المورد مطلوب")
    with get_session() as s:
        sup = Supplier(name=name, phone=phone or "", vat_number=vat_number or "",
                        address=address or "", account_id=int(account_id) if account_id else None)
        s.add(sup)
        s.commit()
        s.refresh(sup)
        return sup.id


def update_supplier(supplier_id, **fields):
    require_action("suppliers", "edit")
    fields.pop("party_type", None)  # تصنيف B2C/B2B خاص بالعملاء بس
    with get_session() as s:
        sup = s.get(Supplier, supplier_id)
        if not sup:
            raise ValueError("المورد غير موجود")
        for k, v in fields.items():
            setattr(sup, k, v)
        s.commit()


def delete_supplier(supplier_id):
    require_action("suppliers", "delete")
    with get_session() as s:
        used = s.query(PurchaseInvoice).filter(PurchaseInvoice.supplier_id == supplier_id).count()
        if used:
            raise ValueError(f"لا يمكن حذف المورد - مرتبط بـ {used} فاتورة")
        sup = s.get(Supplier, supplier_id)
        if sup:
            s.delete(sup)
            s.commit()


# ============================== Company Settings ==============================
def get_company_settings():
    with get_session() as s:
        c = s.get(CompanySettings, 1)
        if not c:
            c = CompanySettings(id=1)
            s.add(c)
            s.commit()
            s.refresh(c)
        return c


def update_company_settings(**fields):
    require_action("settings", "edit")
    with get_session() as s:
        c = s.get(CompanySettings, 1)
        if not c:
            c = CompanySettings(id=1)
            s.add(c)
        for k, v in fields.items():
            setattr(c, k, v)
        s.commit()


# ============================== Invoice helpers ==============================
def _next_invoice_number(session, model, prefix):
    _db_lock(session)
    last = session.query(model).order_by(model.id.desc()).first()
    next_id = (last.id + 1) if last else 1
    return f"{prefix}{next_id:06d}"


def _compute_line_total(quantity, unit_price, discount, tax_rate):
    base = max(0.0, quantity * unit_price - discount)
    tax = base * (tax_rate / 100.0)
    b, t = round(base, 2), round(tax, 2)
    return b, t, round(b + t, 2)         # الإجمالي = المقرّب + المقرّب (مش تقريب المجموع) عشان القيد المحاسبي يتوازن دايمًا


# ============================== Sales Invoices ==============================
def create_sales_invoice(customer_id, items, notes="", discount=0.0,
                          location_id=None, invoice_date=None, branch_id=None, cost_center_id=None,
                          receivable_override_account_id=None, payment_splits=None, credit_approval_id=None, _credit_checked=False, currency=None, exchange_rate=None, _zatca=True):
    require_action("sales_invoices", "create")
    require_action("sales_invoices", "post")
    """
    items: list of dicts: {product_id, quantity, unit_price, discount, tax_rate}
    ينزّل الكميات من المخزون تلقائياً.
    currency/exchange_rate: أسعار الأسطر بالعملة الأجنبية؛ بتتحوّل للأساسي بسعر الصرف (انظر fx.py).
    """
    if not items:
        raise ValueError("أضف صنف واحد على الأقل")
    _fxinfo = None
    if currency:
        from . import fx as _fx
        items, discount, _fxinfo = _fx.convert_items(items, discount, currency, exchange_rate, invoice_date)

    branch_id = branch_id or default_branch_id()
    cost_center_id = cost_center_id or default_cost_center_id()
    if branch_id and not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    if cost_center_id and not allowed_cost_center(cost_center_id): raise PermissionError("مركز التكلفة غير مسموح لهذا المستخدم")
    if location_id is None:
        location_id = default_location_id(branch_id)
    if location_id is None:
        raise ValueError("لا يوجد مخزن معرَّف")
    branch_id = branch_id or default_branch_id()
    cost_center_id = cost_center_id or default_cost_center_id()
    if branch_id and not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")

    # التحقق من توفر الكميات قبل أي عملية حفظ (بيفكّك أصناف الـ Kit لمكوناتها)
    for it in items:
        pid = int(it["product_id"])
        qty = float(it["quantity"])
        if qty <= 0:
            raise ValueError("الكمية لازم تكون أكبر من صفر")
        p = get_product(pid)
        if p and p.product_type == "service":
            continue  # صنف خدمة - مالوش مخزون خالص، متأثرش بالكمية المتاحة
        if p and p.product_type == "kit":
            bom = get_bom_explosion(pid, qty)
            if not bom:
                raise ValueError(f'الصنف «{p.name}» من نوع Kit لكن مفهوش مكونات معرَّفة له')
            for line in bom:
                balance = get_product_balance(line["component_id"], location_id, branch_id)
                if balance < line["quantity"]:
                    raise ValueError(
                        f'الرصيد المتاح من «{line["component"].name}» (مكوّن ضمن «{p.name}») '
                        f'({balance:g}) أقل من المطلوب ({line["quantity"]:g})'
                    )
        else:
            base_qty, _, _ = convert_to_base_quantity(pid, qty, it.get("unit_id"))
            balance = get_product_balance(pid, location_id, branch_id)
            if balance < base_qty:
                name = p.name if p else f"صنف #{pid}"
                raise ValueError(f"الرصيد المتاح من «{name}» ({balance:g}) أقل من المطلوب ({qty:g})")

    settings = get_company_settings()

    # حد الائتمان: الجزء الآجل بس (الكاشير النقدي/الشبكة مش آجل)
    if customer_id and not _credit_checked:
        _tot = max(0.0, sum(_compute_line_total(float(i["quantity"]), float(i["unit_price"]), float(i.get("discount", 0)), float(i.get("tax_rate", 15)))[2] for i in items) - float(discount or 0))
        if payment_splits:
            _credit = sum(float(sp["amount"]) for sp in payment_splits if not sp.get("account_id"))
        else:
            _credit = 0.0 if receivable_override_account_id else _tot
        if _credit > 0.005:
            from . import credit as _credit_mod
            _credit_mod.check_sale(customer_id, _credit, approval_id=credit_approval_id)

    with get_session() as s:
        number = _next_invoice_number(s, SalesInvoice, settings.invoice_prefix_sales or "S-")

        invoice = SalesInvoice(
            number=number,
            date=invoice_date or datetime.datetime.now(),
            customer_id=customer_id,
            branch_id=branch_id,
            cost_center_id=cost_center_id,
            discount=float(discount or 0),
            notes=notes or "",
        )
        s.add(invoice)
        s.flush()

        subtotal = 0.0
        tax_total = 0.0
        grand = 0.0
        for it in items:
            base, tax, line_total = _compute_line_total(
                float(it["quantity"]), float(it["unit_price"]),
                float(it.get("discount", 0)), float(it.get("tax_rate", 15)),
            )
            s.add(SalesInvoiceItem(
                invoice_id=invoice.id,
                product_id=int(it["product_id"]),
                quantity=float(it["quantity"]),
                unit_id=int(it["unit_id"]) if it.get("unit_id") else None,
                unit_factor=float(convert_to_base_quantity(int(it["product_id"]), float(it["quantity"]), it.get("unit_id"))[2]),
                unit_price=float(it["unit_price"]),
                discount=float(it.get("discount", 0)),
                tax_rate=float(it.get("tax_rate", 15)),
                line_total=line_total,
            ))
            subtotal += base
            tax_total += tax
            grand += line_total

        # خصم إجمالي على مستوى الفاتورة (يُطرح من الإجمالي النهائي)
        grand = max(0.0, grand - float(discount or 0))

        invoice.subtotal = round(subtotal, 2)
        invoice.tax_total = round(tax_total, 2)
        invoice.total = round(grand, 2)
        s.commit()
        s.refresh(invoice)

        # تنزيل الكميات من المخزون
        invoice_id = invoice.id
        invoice_number = invoice.number

    for it in items:
        pid = int(it["product_id"])
        p = get_product(pid)
        if p and p.product_type == "service":
            continue  # خدمة - مفيش حركة مخزون خالص
        if p and p.product_type == "kit":
            bom = get_bom_explosion(pid, float(it["quantity"]))
            for line in bom:
                create_stock_move(
                    product_id=line["component_id"],
                    location_id=location_id,
                    direction="out",
                    quantity=line["quantity"],
                    unit_cost=line["component"].cost_price or 0,
                    reference=f"SALES:{invoice_number}",
                    note=f"فاتورة مبيعات {invoice_number} (مكوّن ضمن Kit: {p.name})",
                    branch_id=branch_id, cost_center_id=cost_center_id, _internal=True,
                )
        else:
            create_stock_move(
                product_id=pid,
                location_id=location_id,
                direction="out",
                quantity=float(it["quantity"]),
                unit_cost=float(it["unit_price"]),
                unit_id=int(it["unit_id"]) if it.get("unit_id") else None,
                reference=f"SALES:{invoice_number}",
                note=f"فاتورة مبيعات {invoice_number}",
                branch_id=branch_id, cost_center_id=cost_center_id, _internal=True,
            )

    post_sales_invoice_accounting(invoice_id, receivable_override_account_id=receivable_override_account_id, payment_splits=payment_splits)
    if _fxinfo:
        _fx.stamp_invoice("sales", invoice_id, _fxinfo)
    if _zatca:
        from . import zatca_p2 as _z2
        _z2.issue_invoice(invoice_id)       # فوترة إلكترونية (لو مفعّلة) - مبيوقفش البيع لو فشلت
    return invoice_id


def list_sales_invoices(limit=200):
    # تحميل العميل مسبقاً لأن الفاتورة تُستخدم بعد إغلاق Session في Flet.
    with get_session() as s:
        q = (
            s.query(SalesInvoice)
            .options(joinedload(SalesInvoice.customer), joinedload(SalesInvoice.branch), joinedload(SalesInvoice.cost_center))
            .order_by(SalesInvoice.date.desc())
        )
        if user_branch_ids(): q=q.filter(((SalesInvoice.branch_id.is_(None))|(SalesInvoice.branch_id.in_(user_branch_ids()))))
        return q.limit(limit).all()


def get_sales_invoice(invoice_id):
    with get_session() as s:
        inv = (
            s.query(SalesInvoice)
            .options(
                joinedload(SalesInvoice.customer),
                joinedload(SalesInvoice.branch),
                joinedload(SalesInvoice.cost_center),
                joinedload(SalesInvoice.items).joinedload(SalesInvoiceItem.product),
                joinedload(SalesInvoice.items).joinedload(SalesInvoiceItem.unit),
            )
            .filter(SalesInvoice.id == invoice_id)
            .first()
        )
        return inv


# ============================== Purchase Invoices ==============================
def _net_unit_cost(it):
    """تكلفة وحدة الشراء الصافية بعد خصم البند (الضريبة المسترد مش جزء من التكلفة)."""
    qty = float(it.get("quantity") or 0); price = float(it.get("unit_price") or 0); disc = float(it.get("discount") or 0)
    return max(0.0, (qty * price - disc) / qty) if qty > 0 else price


def create_purchase_invoice(supplier_id, items, notes="", discount=0.0,
                             location_id=None, invoice_date=None, branch_id=None, cost_center_id=None,
                             skip_stock_move=False, currency=None, exchange_rate=None):
    require_action("purchase_invoices", "create")
    if not items:
        raise ValueError("أضف صنف واحد على الأقل")
    _fxinfo = None
    if currency:
        from . import fx as _fx
        items, discount, _fxinfo = _fx.convert_items(items, discount, currency, exchange_rate, invoice_date)

    branch_id = branch_id or default_branch_id()
    cost_center_id = cost_center_id or default_cost_center_id()
    if branch_id and not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    if cost_center_id and not allowed_cost_center(cost_center_id): raise PermissionError("مركز التكلفة غير مسموح لهذا المستخدم")
    if location_id is None:
        location_id = default_location_id(branch_id)
    if location_id is None:
        raise ValueError("لا يوجد مخزن معرَّف")

    for it in items:
        if float(it["quantity"]) <= 0:
            raise ValueError("الكمية لازم تكون أكبر من صفر")

    settings = get_company_settings()
    from . import approvals as _appr
    _ptot = max(0.0, sum(_compute_line_total(float(i["quantity"]), float(i["unit_price"]), float(i.get("discount", 0)), float(i.get("tax_rate", 15)))[2] for i in items) - float(discount or 0))
    _appr.guard("purchase_invoice", _ptot, f"{supplier_id}:{_ptot:.2f}", summary=f"مورد #{supplier_id} - {len(items)} صنف")

    with get_session() as s:
        number = _next_invoice_number(s, PurchaseInvoice, settings.invoice_prefix_purchase or "P-")
        invoice = PurchaseInvoice(
            number=number,
            date=invoice_date or datetime.datetime.now(),
            supplier_id=supplier_id,
            branch_id=branch_id,
            cost_center_id=cost_center_id,
            discount=float(discount or 0),
            notes=notes or "",
        )
        s.add(invoice)
        s.flush()

        subtotal = 0.0
        tax_total = 0.0
        grand = 0.0
        for it in items:
            base, tax, line_total = _compute_line_total(
                float(it["quantity"]), float(it["unit_price"]),
                float(it.get("discount", 0)), float(it.get("tax_rate", 15)),
            )
            s.add(PurchaseInvoiceItem(
                invoice_id=invoice.id,
                product_id=int(it["product_id"]),
                quantity=float(it["quantity"]),
                unit_id=int(it["unit_id"]) if it.get("unit_id") else None,
                unit_factor=float(convert_to_base_quantity(int(it["product_id"]), float(it["quantity"]), it.get("unit_id"))[2]),
                unit_price=float(it["unit_price"]),
                discount=float(it.get("discount", 0)),
                tax_rate=float(it.get("tax_rate", 15)),
                line_total=line_total,
            ))
            subtotal += base
            tax_total += tax
            grand += line_total

        grand = max(0.0, grand - float(discount or 0))
        invoice.subtotal = round(subtotal, 2)
        invoice.tax_total = round(tax_total, 2)
        invoice.total = round(grand, 2)
        s.commit()
        s.refresh(invoice)

        invoice_id = invoice.id
        invoice_number = invoice.number

    for it in items:
        product_id = int(it["product_id"])
        p = get_product(product_id)
        if not skip_stock_move and not (p and p.product_type == "service"):
            create_stock_move(
                product_id=product_id,
                location_id=location_id,
                direction="in",
                quantity=float(it["quantity"]),
                unit_cost=_net_unit_cost(it),
                unit_id=int(it["unit_id"]) if it.get("unit_id") else None,
                reference=f"PURCH:{invoice_number}",
                note=f"فاتورة مشتريات {invoice_number}",
                branch_id=branch_id, cost_center_id=cost_center_id, _internal=True,
                batch_no=it.get("batch_no"), expiry_date=it.get("expiry_date"), require_expiry=True, update_cost=True,
            )

    post_purchase_invoice_accounting(invoice_id)
    if _fxinfo:
        _fx.stamp_invoice("purchase", invoice_id, _fxinfo)
    return invoice_id


def list_purchase_invoices(limit=200):
    # تحميل المورد مسبقاً لأن الفاتورة تُستخدم بعد إغلاق Session في Flet.
    with get_session() as s:
        q = (
            s.query(PurchaseInvoice)
            .options(joinedload(PurchaseInvoice.supplier), joinedload(PurchaseInvoice.branch), joinedload(PurchaseInvoice.cost_center))
            .order_by(PurchaseInvoice.date.desc())
        )
        if user_branch_ids(): q=q.filter(((PurchaseInvoice.branch_id.is_(None))|(PurchaseInvoice.branch_id.in_(user_branch_ids()))))
        return q.limit(limit).all()


def get_purchase_invoice(invoice_id):
    with get_session() as s:
        inv = (
            s.query(PurchaseInvoice)
            .options(
                joinedload(PurchaseInvoice.supplier),
                joinedload(PurchaseInvoice.branch),
                joinedload(PurchaseInvoice.cost_center),
                joinedload(PurchaseInvoice.items).joinedload(PurchaseInvoiceItem.product),
                joinedload(PurchaseInvoice.items).joinedload(PurchaseInvoiceItem.unit),
            )
            .filter(PurchaseInvoice.id == invoice_id)
            .first()
        )
        return inv

# ============================== Accounting ==============================
def main_account_codes():
    """أكواد الحسابات الرئيسية (اللي ليها حسابات فرعية تحتها) - بتتستخدم
    لتمييزها بخط عريض وخلفية فاتحة في الشاشات والتقارير المطبوعة."""
    from .db import Account
    with get_session() as s:
        parent_ids = {pid for (pid,) in s.query(Account.parent_id).filter(Account.parent_id.isnot(None)).distinct().all()}
        if not parent_ids:
            return set()
        return {c for (c,) in s.query(Account.code).filter(Account.id.in_(parent_ids)).all()}


def list_accounts(search=None, postable_only=False):
    from .db import Account
    with get_session() as s:
        q = s.query(Account)
        if search:
            like = f"%{search.strip()}%"
            q = q.filter((Account.code.like(like)) | (Account.name.like(like)))
        accounts = q.order_by(Account.code).all()
        if postable_only:
            parent_ids = {a.parent_id for a in s.query(Account).all() if a.parent_id}
            accounts = [a for a in accounts if a.id not in parent_ids]
        return accounts


def is_leaf_account(account_id):
    """حساب فرعي (قابل لتسجيل حركات عليه) = مفيش أي حساب تاني بياخده كأب."""
    from .db import Account
    with get_session() as s:
        has_children = s.query(Account).filter(Account.parent_id == account_id).first() is not None
        return not has_children


def create_account(code, name, account_type, parent_id=None, cash_flow_type=None):
    require_action("accounts", "create")
    from .db import Account
    code, name = (code or "").strip(), (name or "").strip()
    if not code or not name:
        raise ValueError("كود واسم الحساب مطلوبان")
    if account_type not in ("asset", "liability", "equity", "income", "expense"):
        raise ValueError("نوع الحساب غير صحيح")
    if cash_flow_type and cash_flow_type not in ("cash", "operating", "investing", "financing"):
        raise ValueError("نوع التدفق النقدي غير صحيح")
    with get_session() as s:
        a = Account(code=code, name=name, account_type=account_type, parent_id=parent_id, cash_flow_type=cash_flow_type)
        s.add(a); s.commit(); s.refresh(a); return a.id


def update_account(account_id, **fields):
    require_action("accounts", "edit")
    from .db import Account
    with get_session() as s:
        a = s.get(Account, account_id)
        if not a: raise ValueError("الحساب غير موجود")
        for k, v in fields.items(): setattr(a, k, v)
        s.commit()


def delete_account(account_id):
    require_action("accounts", "delete")
    from .db import Account, JournalEntryLine
    with get_session() as s:
        a = s.get(Account, account_id)
        if not a: return
        if s.query(Account).filter(Account.parent_id == account_id).count():
            raise ValueError("لا يمكن حذف حساب يحتوي على حسابات فرعية")
        if s.query(JournalEntryLine).filter(JournalEntryLine.account_id == account_id).count():
            raise ValueError("لا يمكن حذف حساب عليه حركات محاسبية")
        s.delete(a); s.commit()


def _assert_period_open(entry_date=None):
    """منع تسجيل قيود/عمليات مالية بتاريخ داخل فترة مقفلة."""
    d = entry_date or datetime.datetime.now()
    with get_session() as s:
        closed = s.query(FiscalPeriod).filter(FiscalPeriod.is_closed.is_(True), FiscalPeriod.date_from <= d, FiscalPeriod.date_to >= d).first()
        if closed:
            raise ValueError(f"الفترة المالية «{closed.name}» مقفلة، لا يمكن تسجيل عملية بتاريخ {d:%Y-%m-%d}")
        if s.query(MonthClose.id).filter(MonthClose.year == d.year, MonthClose.month == d.month).first():
            raise ValueError(f"شهر {d.month}/{d.year} مقفل، لا يمكن تسجيل عملية بتاريخ {d:%Y-%m-%d} (افتح الشهر من شاشة الإقفال الشهري)")

def _next_journal_number(s):
    _db_lock(s)
    from .db import JournalEntry
    last = s.query(JournalEntry).order_by(JournalEntry.id.desc()).first()
    return f"JE-{((last.id + 1) if last else 1):06d}"


def create_journal_entry(lines, reference="", description="", source_type="manual", source_id=None, entry_date=None, branch_id=None, cost_center_id=None):
    from .db import JournalEntry, JournalEntryLine
    entry_date = entry_date or datetime.datetime.now()
    if source_type == "manual": require_action("journals", "create")
    _assert_period_open(entry_date)
    branch_id = branch_id or default_branch_id()
    cost_center_id = cost_center_id or default_cost_center_id()
    if branch_id and not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    if cost_center_id and not allowed_cost_center(cost_center_id): raise PermissionError("مركز التكلفة غير مسموح لهذا المستخدم")
    clean=[]; td=tc=0.0
    for ln in lines:
        d=round(float(ln.get("debit",0) or 0),2); c=round(float(ln.get("credit",0) or 0),2)
        if d < 0 or c < 0 or (d and c): raise ValueError("سطر القيد يجب أن يكون مديناً أو دائناً فقط")
        if d or c:
            line_branch = ln.get("branch_id", branch_id) or branch_id
            line_cc = ln.get("cost_center_id", cost_center_id) or cost_center_id
            if line_branch and not allowed_branch(line_branch): raise PermissionError("الفرع في سطر القيد غير مسموح لهذا المستخدم")
            if line_cc and not allowed_cost_center(line_cc): raise PermissionError("مركز التكلفة في سطر القيد غير مسموح لهذا المستخدم")
            clean.append((int(ln["account_id"]), d, c, ln.get("description", ""), line_branch, line_cc, ln.get("partner_type"), ln.get("partner_id")))
            td += d; tc += c
    if not clean or round(td-tc,2) != 0:
        raise ValueError(f"القيد غير متوازن: مدين {td:.2f} / دائن {tc:.2f}")
    from .db import Account
    with get_session() as s:
        parent_ids = {a.parent_id for a in s.query(Account).all() if a.parent_id}
        for aid, d, c, desc, bid, ccid, ptype, pid in clean:
            if aid in parent_ids:
                acc = s.get(Account, aid)
                raise ValueError(
                    f'لا يمكن تسجيل حركة على الحساب الرئيسي "{acc.code} - {acc.name}" - '
                    f'اختر أحد الحسابات الفرعية التابعة له.'
                )
    with get_session() as s:
        e=JournalEntry(number=_next_journal_number(s), date=entry_date or datetime.datetime.now(), reference=reference or "", description=description or "", source_type=source_type, source_id=source_id, posted=True, branch_id=branch_id)
        s.add(e); s.flush()
        for aid,d,c,desc,bid,ccid,ptype,pid in clean:
            s.add(JournalEntryLine(entry_id=e.id, account_id=aid, debit=d, credit=c, description=desc, branch_id=bid, cost_center_id=ccid, partner_type=ptype, partner_id=pid))
        s.commit(); return e.id


def list_journal_entries(limit=300):
    from .db import JournalEntry, JournalEntryLine
    with get_session() as s:
        q=s.query(JournalEntry).options(
            joinedload(JournalEntry.lines).joinedload(JournalEntryLine.account),
            joinedload(JournalEntry.branch),
        ).filter(JournalEntry.posted.is_(True))
        if user_branch_ids(): q=q.filter(((JournalEntry.branch_id.is_(None))|(JournalEntry.branch_id.in_(user_branch_ids()))))
        entries = q.order_by(JournalEntry.date.desc(), JournalEntry.id.desc()).limit(limit).all()
        s.expunge_all()
        return entries


def get_journal_entry(entry_id):
    """يرجّع قيد واحد بكل تفاصيله (سواء كان مرحّل أو مسودة) - يُستخدم لفتح
    القيد للمراجعة أو التعديل، بعكس list_journal_entries اللي بترجّع
    المرحّل بس."""
    from .db import JournalEntry, JournalEntryLine
    with get_session() as s:
        e = s.query(JournalEntry).options(
            joinedload(JournalEntry.lines).joinedload(JournalEntryLine.account)
        ).filter(JournalEntry.id == entry_id).first()
        return e


def set_journal_entry_draft(entry_id):
    """يحوّل قيد مرحّل لمسودة عشان تقدر تعدّل عليه - القيد هيختفي من
    اليومية العامة والتقارير لحد ما تعيد ترحيله. مسموح بس للقيود اليدوية
    (مش قيود مولّدة تلقائياً من فواتير أو سندات، عشان الحفاظ على تناسقها)."""
    from .db import JournalEntry
    with get_session() as s:
        e = s.get(JournalEntry, entry_id)
        if not e:
            raise ValueError('القيد غير موجود')
        if e.source_type != 'manual':
            raise ValueError(
                f'القيد ده اتولّد تلقائياً من "{e.source_type}" - مينفعش تتعدّل عليه '
                f'مباشرة من هنا، عدّل المصدر الأصلي بدل كده.'
            )
        e.posted = False
        s.commit()
        return True


def update_journal_entry(entry_id, lines, reference=None, description=None, entry_date=None, branch_id=None, cost_center_id=None, _internal=False):
    """يستبدل سطور قيد (لازم يكون في وضع مسودة أولاً) بسطور جديدة، مع نفس
    فحوصات التوازن والحسابات الفرعية اللي بتتطبّق وقت الإنشاء.
    _internal=True بتسمح لعمليات النظام الموثوقة (زي إعادة ترحيل الرواتب)
    تعدّل على قيود مولّدة تلقائياً - متستخدمش الباراميتر ده من واجهة مستخدم مباشرة."""
    from .db import JournalEntry, JournalEntryLine, Account

    clean = []
    td = tc = 0.0
    for ln in lines:
        d = round(float(ln.get("debit", 0) or 0), 2)
        c = round(float(ln.get("credit", 0) or 0), 2)
        if d < 0 or c < 0 or (d and c):
            raise ValueError("سطر القيد يجب أن يكون مديناً أو دائناً فقط")
        if d or c:
            clean.append((int(ln["account_id"]), d, c, ln.get("description", ""),
                          ln.get("branch_id"), ln.get("cost_center_id"),
                          ln.get("partner_type"), ln.get("partner_id")))
            td += d; tc += c
    if not clean or round(td - tc, 2) != 0:
        raise ValueError(f"القيد غير متوازن: مدين {td:.2f} / دائن {tc:.2f}")

    with get_session() as s:
        parent_ids = {a.parent_id for a in s.query(Account).all() if a.parent_id}
        for aid, d, c, desc, bid, ccid, ptype, pid in clean:
            if aid in parent_ids:
                acc = s.get(Account, aid)
                raise ValueError(
                    f'لا يمكن تسجيل حركة على الحساب الرئيسي "{acc.code} - {acc.name}" - '
                    f'اختر أحد الحسابات الفرعية التابعة له.'
                )

    with get_session() as s:
        e = s.get(JournalEntry, entry_id)
        if not e:
            raise ValueError('القيد غير موجود')
        if e.posted:
            raise ValueError('حوّل القيد لمسودة أولاً قبل التعديل عليه')
        if e.source_type != 'manual' and not _internal:
            raise ValueError('مينفعش تعدّل على قيد مولّد تلقائياً من هنا')

        if reference is not None: e.reference = reference
        if description is not None: e.description = description
        if entry_date is not None: e.date = entry_date
        if branch_id is not None: e.branch_id = branch_id

        for old_line in list(e.lines):
            s.delete(old_line)
        s.flush()

        for aid, d, c, desc, bid, ccid, ptype, pid in clean:
            s.add(JournalEntryLine(
                entry_id=e.id, account_id=aid, debit=d, credit=c, description=desc,
                branch_id=bid or e.branch_id, cost_center_id=ccid,
                partner_type=ptype, partner_id=pid,
            ))
        s.commit()
        return e.id


def post_journal_entry_by_id(entry_id):
    """يعيد ترحيل قيد كان في وضع مسودة (بعد التعديل عليه)."""
    from .db import JournalEntry
    with get_session() as s:
        e = s.get(JournalEntry, entry_id)
        if not e:
            raise ValueError('القيد غير موجود')
        if e.posted:
            raise ValueError('القيد مرحّل بالفعل')
        entry_date = e.date
    _assert_period_open(entry_date)
    with get_session() as s:
        e = s.get(JournalEntry, entry_id)
        total_debit = sum(l.debit for l in e.lines)
        total_credit = sum(l.credit for l in e.lines)
        if round(total_debit - total_credit, 2) != 0:
            raise ValueError(f"القيد غير متوازن: مدين {total_debit:.2f} / دائن {total_credit:.2f}")
        if not e.lines:
            raise ValueError('القيد لازم يحتوي على سطور')
        e.posted = True
        s.commit()
        return True


def _accounting_settings():
    from .db import AccountingSettings
    with get_session() as s: return s.get(AccountingSettings, 1)


def post_sales_invoice_accounting(invoice_id, receivable_override_account_id=None, payment_splits=None):
    """receivable_override_account_id: لو اتبعت، بيتسجّل عليه بدل الذمم
    المدينة (مثلاً حساب نقدي/بنك لبيع POS متحصّل فورًا بدل ما يفضل دين
    على العميل)."""
    from .db import JournalEntry
    with get_session() as s:
        if s.query(JournalEntry).filter(JournalEntry.source_type=="sales_invoice", JournalEntry.source_id==invoice_id).count(): return
    inv=get_sales_invoice(invoice_id); cfg=_accounting_settings()
    receivable_account_id = int(receivable_override_account_id) if receivable_override_account_id else (
        (inv.customer.account_id if inv.customer and inv.customer.account_id else None) or cfg.receivable_account_id)
    net=max(0.0, (inv.total or 0) - (inv.tax_total or 0))
    if payment_splits:
        # سداد متعدد: سطر مدين لكل طريقة دفع على حسابها (account_id=None = الجزء الآجل على حساب العميل)
        cust_acc = (inv.customer.account_id if inv.customer and inv.customer.account_id else None) or cfg.receivable_account_id
        lines = []
        for sp in payment_splits:
            if round(float(sp["amount"]), 2) > 0:
                lines.append({"account_id": int(sp["account_id"]) if sp.get("account_id") else cust_acc, "debit": round(float(sp["amount"]), 2)})
        lines.append({"account_id": cfg.vat_output_account_id, "credit": inv.tax_total})
    else:
        lines=[{"account_id":receivable_account_id,"debit":inv.total}, {"account_id":cfg.vat_output_account_id,"credit":inv.tax_total}]
    by_account = {}
    for i in inv.items:
        aid = i.product.sales_account_id or cfg.sales_account_id
        base = max(0.0, float(i.quantity or 0) * float(i.unit_price or 0) - float(i.discount or 0))
        by_account[aid] = by_account.get(aid, 0.0) + base
    # خصم إجمالي على مستوى الفاتورة (مختلف عن خصم كل سطر) - بيقلّل صافي
    # الذمم المدينة، فلازم يتسجّل كمصروف خصومات ممنوحة عشان القيد يفضل متوازن
    invoice_discount = float(getattr(inv, 'discount', 0) or 0)
    if invoice_discount:
        if not cfg.sales_discount_account_id:
            raise ValueError("إعداد حساب الخصومات الممنوحة ناقص - راجع الإعدادات المحاسبية قبل استخدام خصم على مستوى الفاتورة")
        lines.append({"account_id": cfg.sales_discount_account_id, "debit": round(invoice_discount, 2)})
    for aid, amount in by_account.items():
        if amount: lines.append({"account_id":aid,"credit":round(amount,2)})
    cost=0.0
    cost_lines = {}
    _bc_cache = {}

    def _batch_share(product_id, base_qty):
        """حصة بند من تكلفة التشغيلات الفعلية لنفس الصنف في الفاتورة (لو الصنف ظهر في أكتر من بند): None لو مفيش تشغيلات."""
        if product_id not in _bc_cache:
            lines = _reference_batch_lines(f"SALES:{inv.number}", product_id, "out")
            _bc_cache[product_id] = (sum(l["quantity"] * l["unit_cost"] for l in lines), sum(l["quantity"] for l in lines)) if lines else None
        v = _bc_cache[product_id]
        return None if v is None or v[1] <= 0 else v[0] * min(1.0, float(base_qty) / v[1])

    for i in inv.items:
        if i.product.product_type == "service":
            continue  # خدمة - مفيش تكلفة بضاعة مباعة أو مخزون خالص
        if i.product.product_type == "kit":
            bom = get_bom_explosion(i.product_id, float(i.quantity or 0))
            cost = 0.0
            for line in bom:
                bc = _batch_share(line["component_id"], line["quantity"]) if uses_batch_cost(line["component"]) else None
                cost += (line["quantity"] * (line["component"].cost_price or 0)) if bc is None else bc
        else:
            cost = float(i.quantity or 0) * float(i.product.cost_price or 0)
            if uses_batch_cost(i.product):
                bc = _batch_share(i.product_id, float(i.quantity or 0) * float(getattr(i, "unit_factor", 1) or 1))         # تكلفة التشغيلات الفعلية (FIFO/LIFO/FEFO)
                if bc is not None:
                    cost = bc
        if cost > 0:
            ca = i.product.cogs_account_id or cfg.cogs_account_id
            ia = i.product.inventory_account_id or cfg.inventory_account_id
            cost_lines[ca] = cost_lines.get(ca, 0.0) + cost
            lines.append({"account_id":ia,"credit":round(cost,2)})
            lines.append({"account_id":ca,"debit":round(cost,2)})
    create_journal_entry(lines, reference=inv.number, description=f"فاتورة مبيعات {inv.number}", source_type="sales_invoice", source_id=inv.id, entry_date=inv.date, branch_id=inv.branch_id, cost_center_id=inv.cost_center_id)


def post_purchase_invoice_accounting(invoice_id):
    from .db import JournalEntry
    with get_session() as s:
        if s.query(JournalEntry).filter(JournalEntry.source_type=="purchase_invoice", JournalEntry.source_id==invoice_id).count(): return
    inv=get_purchase_invoice(invoice_id); cfg=_accounting_settings()

    by_account = {}  # حساب المخزون (سلع) أو المصروف المباشر (خدمات) -> المبلغ
    for i in inv.items:
        base = max(0.0, float(i.quantity or 0) * float(i.unit_price or 0) - float(i.discount or 0))
        if i.product.product_type == "service":
            aid = i.product.cogs_account_id or cfg.purchases_account_id
            if not aid:
                raise ValueError(f'الصنف «{i.product.name}» صنف خدمة ومفهوش حساب مصروف محدد - حدد حساب "تكلفة المبيعات" للصنف أو راجع إعداد "حساب المشتريات" في الإعدادات المحاسبية')
        else:
            aid = i.product.inventory_account_id or cfg.inventory_account_id
        by_account[aid] = by_account.get(aid, 0.0) + base

    payable_account_id = (inv.supplier.account_id if inv.supplier and inv.supplier.account_id else None) or cfg.payable_account_id
    lines = [{"account_id": cfg.vat_input_account_id, "debit": inv.tax_total}, {"account_id": payable_account_id, "credit": inv.total}]
    invoice_discount = float(getattr(inv, 'discount', 0) or 0)
    if invoice_discount:
        if not cfg.purchase_discount_account_id:
            raise ValueError("إعداد حساب الخصومات المكتسبة من الموردين ناقص - راجع الإعدادات المحاسبية قبل استخدام خصم على مستوى الفاتورة")
        lines.append({"account_id": cfg.purchase_discount_account_id, "credit": round(invoice_discount, 2)})
    for aid, amount in by_account.items():
        if amount: lines.append({"account_id": aid, "debit": round(amount, 2)})
    create_journal_entry(lines, reference=inv.number, description=f"فاتورة مشتريات {inv.number}", source_type="purchase_invoice", source_id=inv.id, entry_date=inv.date, branch_id=inv.branch_id, cost_center_id=inv.cost_center_id)


def trial_balance_detailed(date_from=None, date_to=None, branch_id=None, cost_center_id=None, group_by=None):
    """
    ميزان مراجعة بصيغة محاسبية كاملة: رصيد أول المدة (مدين/دائن) + حركة
    الفترة (مدين/دائن) + الرصيد الختامي (مدين/دائن) لكل حساب.
    group_by: None (تفصيلي لكل حساب) | 'type' (حسب نوع الحساب) |
              'branch' (حسب الفرع) | 'cost_center' (حسب مركز التكلفة)
    """
    from sqlalchemy import text, bindparam
    df, dt = _dt_start(date_from), _dt_end(date_to)

    branch_clause = ""
    params = {}
    if branch_id:
        branch_clause = " AND l.branch_id = :branch_id"
        params["branch_id"] = int(branch_id)
    elif user_branch_ids():
        branch_clause = " AND (l.branch_id IS NULL OR l.branch_id IN :ubids)"
        params["ubids"] = tuple(user_branch_ids())
    cc_clause = ""
    if cost_center_id:
        cc_clause = " AND l.cost_center_id = :cost_center_id"
        params["cost_center_id"] = int(cost_center_id)

    opening_clause = "je.date < :date_from" if df else "FALSE"
    period_clause_parts = []
    if df:
        period_clause_parts.append("je.date >= :date_from")
    if dt:
        period_clause_parts.append("je.date <= :date_to")
    period_clause = " AND ".join(period_clause_parts) if period_clause_parts else "TRUE"
    if df: params["date_from"] = df
    if dt: params["date_to"] = dt

    with get_session() as s:
        query = f"""
            SELECT a.id AS account_id, a.code, a.name, a.account_type,
                   COALESCE(SUM(CASE WHEN {opening_clause} THEN l.debit ELSE 0 END), 0) AS opening_debit,
                   COALESCE(SUM(CASE WHEN {opening_clause} THEN l.credit ELSE 0 END), 0) AS opening_credit,
                   COALESCE(SUM(CASE WHEN {period_clause} THEN l.debit ELSE 0 END), 0) AS period_debit,
                   COALESCE(SUM(CASE WHEN {period_clause} THEN l.credit ELSE 0 END), 0) AS period_credit
            FROM accounts a
            LEFT JOIN journal_entry_lines l ON l.account_id = a.id
            LEFT JOIN journal_entries je ON je.id = l.entry_id AND je.posted IS TRUE
            WHERE 1=1 {branch_clause} {cc_clause}
            GROUP BY a.id
            ORDER BY a.code
        """
        bind = text(query)
        if "ubids" in params:
            bind = bind.bindparams(bindparam("ubids", expanding=True))
        rows = s.execute(bind, params).fetchall()

        result = []
        for r in rows:
            opening_net = float(r.opening_debit) - float(r.opening_credit)
            period_net = float(r.period_debit) - float(r.period_credit)
            closing_net = opening_net + period_net
            result.append({
                "account_id": r.account_id, "code": r.code, "name": r.name, "type": r.account_type,
                "opening_debit": max(opening_net, 0) or 0.0, "opening_credit": max(-opening_net, 0) or 0.0,
                "period_debit": round(float(r.period_debit), 2), "period_credit": round(float(r.period_credit), 2),
                "closing_debit": round(max(closing_net, 0), 2) or 0.0, "closing_credit": round(max(-closing_net, 0), 2) or 0.0,
            })

    if group_by in (None, "", "account"):
        return result

    TYPE_LABELS = {"asset": "أصول", "liability": "التزامات", "equity": "حقوق ملكية", "income": "إيرادات", "expense": "مصروفات"}
    if group_by == "type":
        groups = {}
        for r in result:
            key = r["type"]
            groups.setdefault(key, {"label": TYPE_LABELS.get(key, key), "opening_debit": 0, "opening_credit": 0, "period_debit": 0, "period_credit": 0, "closing_debit": 0, "closing_credit": 0})
            for f in ("opening_debit", "opening_credit", "period_debit", "period_credit", "closing_debit", "closing_credit"):
                groups[key][f] += r[f]
        return [dict(v, code="", type=k) for k, v in groups.items()]

    if group_by in ("branch", "cost_center"):
        col = "l.branch_id" if group_by == "branch" else "l.cost_center_id"
        label_table = "branches" if group_by == "branch" else "cost_centers"
        with get_session() as s:
            query2 = f"""
                SELECT {col} AS gid,
                       COALESCE(SUM(CASE WHEN {opening_clause} THEN l.debit ELSE 0 END), 0) AS opening_debit,
                       COALESCE(SUM(CASE WHEN {opening_clause} THEN l.credit ELSE 0 END), 0) AS opening_credit,
                       COALESCE(SUM(CASE WHEN {period_clause} THEN l.debit ELSE 0 END), 0) AS period_debit,
                       COALESCE(SUM(CASE WHEN {period_clause} THEN l.credit ELSE 0 END), 0) AS period_credit
                FROM journal_entry_lines l
                JOIN journal_entries je ON je.id = l.entry_id AND je.posted IS TRUE
                WHERE 1=1 {branch_clause} {cc_clause}
                GROUP BY {col}
            """
            bind2 = text(query2)
            if "ubids" in params:
                bind2 = bind2.bindparams(bindparam("ubids", expanding=True))
            rows2 = s.execute(bind2, params).fetchall()
            names = {}
            if group_by == "branch":
                names = {b.id: f"{b.code} - {b.name}" for b in s.query(Branch).all()}
            else:
                names = {c.id: f"{c.code} - {c.name}" for c in s.query(CostCenter).all()}

        grouped = []
        for r in rows2:
            opening_net = float(r.opening_debit) - float(r.opening_credit)
            period_net = float(r.period_debit) - float(r.period_credit)
            closing_net = opening_net + period_net
            grouped.append({
                "code": "", "type": "",
                "label": names.get(r.gid, "غير محدد") if r.gid else "غير محدد",
                "opening_debit": max(opening_net, 0), "opening_credit": max(-opening_net, 0),
                "period_debit": round(float(r.period_debit), 2), "period_credit": round(float(r.period_credit), 2),
                "closing_debit": round(max(closing_net, 0), 2), "closing_credit": round(max(-closing_net, 0), 2),
            })
        return grouped

    return result


def trial_balance(date_from=None, date_to=None, branch_id=None, cost_center_id=None):
    from .db import Account, JournalEntryLine, JournalEntry
    with get_session() as s:
        q = s.query(
            Account.id, Account.code, Account.name, Account.account_type,
            func.coalesce(func.sum(JournalEntryLine.debit), 0).label('debit'),
            func.coalesce(func.sum(JournalEntryLine.credit), 0).label('credit'),
        ).outerjoin(JournalEntryLine, JournalEntryLine.account_id == Account.id)

        needs_entry_join = date_from or date_to
        if needs_entry_join:
            q = q.outerjoin(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            if date_from:
                q = q.filter((JournalEntryLine.id.is_(None)) | (JournalEntry.date >= date_from))
            if date_to:
                q = q.filter((JournalEntryLine.id.is_(None)) | (JournalEntry.date <= date_to))
        if branch_id:
            q = q.filter((JournalEntryLine.id.is_(None)) | (JournalEntryLine.branch_id == branch_id))
        if cost_center_id:
            q = q.filter((JournalEntryLine.id.is_(None)) | (JournalEntryLine.cost_center_id == cost_center_id))

        rows = q.group_by(Account.id).order_by(Account.code).all()
        return [{"id": r.id, "code": r.code, "name": r.name, "type": r.account_type,
                 "debit": float(r.debit), "credit": float(r.credit),
                 "balance": float(r.debit - r.credit)} for r in rows]


def financial_report():
    tb=trial_balance()
    income=sum(-r['balance'] for r in tb if r['type']=='income')
    expense=sum(r['balance'] for r in tb if r['type']=='expense')
    assets=sum(r['balance'] for r in tb if r['type']=='asset')
    liabilities=sum(-r['balance'] for r in tb if r['type']=='liability')
    equity=sum(-r['balance'] for r in tb if r['type']=='equity')
    profit=income-expense
    return {"income":income,"expense":expense,"profit":profit,"assets":assets,"liabilities":liabilities,"equity":equity,"equity_with_profit":equity+profit,"trial_balance":tb}



# ============================== Receipts / Payments ==============================
def _next_payment_number(s, prefix):
    _db_lock(s)
    last = s.query(Payment).order_by(Payment.id.desc()).first()
    return f"{prefix}{((last.id + 1) if last else 1):06d}"


def _fx_payment(currency, exchange_rate, foreign_amount, date):
    """سند بعملة أجنبية: بيرجّع (currency, rate, base_amount, foreign_amount) أو None لو بالأساسي."""
    from . import fx as _fx
    if not currency or not _fx.is_foreign(currency):
        return None
    rate = _fx.resolve_rate(currency, exchange_rate, date)
    return (currency.upper(), rate, round(foreign_amount * rate, 2), foreign_amount)


def create_receipt(partner_id, amount, account_id, date=None, reference="", notes="", branch_id=None, cost_center_id=None, partner_type="customer", currency=None, exchange_rate=None):
    require_action("receipts_payments", "create")
    amount=float(amount or 0)
    if amount <= 0: raise ValueError("قيمة سند القبض يجب أن تكون أكبر من صفر")
    _fxp = _fx_payment(currency, exchange_rate, amount, date)
    if _fxp: amount = _fxp[2]
    cfg=_accounting_settings()
    counter_account_id, counter_label = {
        "customer": (cfg.receivable_account_id, "حساب العملاء"),
        "employee": (cfg.employee_advances_account_id, "حساب سلف الموظفين"),
        "supplier": (cfg.payable_account_id, "حساب الموردين"),
    }.get(partner_type, (cfg.receivable_account_id, "حساب العملاء"))
    if partner_type == "customer" and partner_id:
        with get_session() as s:
            cust = s.get(Customer, int(partner_id))
            if cust and cust.account_id:
                counter_account_id = cust.account_id
    elif partner_type == "supplier" and partner_id:
        with get_session() as s:
            sup = s.get(Supplier, int(partner_id))
            if sup and sup.account_id:
                counter_account_id = sup.account_id
    if not account_id or not counter_account_id: raise ValueError(f"إعداد حساب النقدية/{counter_label} ناقص - راجع الإعدادات المحاسبية")
    branch_id = branch_id or default_branch_id()
    cost_center_id = cost_center_id or default_cost_center_id()
    if branch_id and not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    with get_session() as s:
        p=Payment(number=_next_payment_number(s,"RC-"), date=date or datetime.datetime.now(), payment_type="receipt", branch_id=branch_id, cost_center_id=cost_center_id, partner_type=partner_type, partner_id=int(partner_id) if partner_id else None, amount=amount, account_id=int(account_id), reference=reference or "", notes=notes or "",
                   currency=_fxp[0] if _fxp else None, exchange_rate=_fxp[1] if _fxp else None, foreign_amount=_fxp[3] if _fxp else None)
        s.add(p); s.flush(); pid=p.id; s.commit()
    je=create_journal_entry([{"account_id":int(account_id),"debit":amount},{"account_id":counter_account_id,"credit":amount}], reference=reference or p.number, description=f"سند قبض {p.number}", source_type="receipt", source_id=pid, entry_date=p.date, branch_id=branch_id, cost_center_id=cost_center_id)
    with get_session() as s: s.get(Payment,pid).journal_entry_id=je; s.commit()
    return pid


def create_payment(partner_id, amount, account_id, date=None, reference="", notes="", branch_id=None, cost_center_id=None, partner_type="supplier", currency=None, exchange_rate=None):
    require_action("receipts_payments", "create")
    amount=float(amount or 0)
    if amount <= 0: raise ValueError("قيمة سند الصرف يجب أن تكون أكبر من صفر")
    _fxp = _fx_payment(currency, exchange_rate, amount, date)
    if _fxp: amount = _fxp[2]
    cfg=_accounting_settings()
    counter_account_id, counter_label = {
        "supplier": (cfg.payable_account_id, "حساب الموردين"),
        "employee": (cfg.employee_advances_account_id, "حساب سلف الموظفين"),
        "customer": (cfg.receivable_account_id, "حساب العملاء"),
    }.get(partner_type, (cfg.payable_account_id, "حساب الموردين"))
    if partner_type == "supplier" and partner_id:
        with get_session() as s:
            sup = s.get(Supplier, int(partner_id))
            if sup and sup.account_id:
                counter_account_id = sup.account_id
    elif partner_type == "customer" and partner_id:
        with get_session() as s:
            cust = s.get(Customer, int(partner_id))
            if cust and cust.account_id:
                counter_account_id = cust.account_id
    if not account_id or not counter_account_id: raise ValueError(f"إعداد حساب النقدية/{counter_label} ناقص - راجع الإعدادات المحاسبية")
    from . import approvals as _appr
    _appr.guard("payment_voucher", amount, f"{partner_type}:{partner_id}:{amount:.2f}", summary=f"{partner_type} #{partner_id}")
    branch_id = branch_id or default_branch_id()
    cost_center_id = cost_center_id or default_cost_center_id()
    if branch_id and not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    with get_session() as s:
        p=Payment(number=_next_payment_number(s,"PY-"), date=date or datetime.datetime.now(), payment_type="payment", branch_id=branch_id, cost_center_id=cost_center_id, partner_type=partner_type, partner_id=int(partner_id) if partner_id else None, amount=amount, account_id=int(account_id), reference=reference or "", notes=notes or "",
                   currency=_fxp[0] if _fxp else None, exchange_rate=_fxp[1] if _fxp else None, foreign_amount=_fxp[3] if _fxp else None)
        s.add(p); s.flush(); pid=p.id; s.commit()
    je=create_journal_entry([{"account_id":counter_account_id,"debit":amount},{"account_id":int(account_id),"credit":amount}], reference=reference or p.number, description=f"سند صرف {p.number}", source_type="payment", source_id=pid, entry_date=p.date, branch_id=branch_id, cost_center_id=cost_center_id)
    with get_session() as s: s.get(Payment,pid).journal_entry_id=je; s.commit()
    return pid


def list_payments(payment_type=None, partner_type=None, branch_id=None, limit=300):
    with get_session() as s:
        q=s.query(Payment).options(joinedload(Payment.account)).order_by(Payment.date.desc(),Payment.id.desc())
        if payment_type: q=q.filter(Payment.payment_type==payment_type)
        if partner_type: q=q.filter(Payment.partner_type==partner_type)
        if branch_id: q=q.filter(Payment.branch_id==int(branch_id))
        elif user_branch_ids(): q=q.filter(((Payment.branch_id.is_(None))|(Payment.branch_id.in_(user_branch_ids()))))
        return q.limit(limit).all()


def account_ledger(account_id=None, date_from=None, date_to=None):
    """دفتر أستاذ حساب معيّن (أو كل الحسابات) - بيحسب رصيد افتتاحي لو فيه
    تاريخ بداية محدد (مجموع الحركات قبل التاريخ ده)، وبيبدأ الرصيد
    التراكمي من فوقه بدل الصفر."""
    df, dt = _dt_start(date_from), _dt_end(date_to)
    opening_balance = 0.0
    if df:
        with get_session() as s:
            oq = s.query(JournalEntryLine).join(JournalEntry).filter(JournalEntry.date < df)
            if account_id: oq = oq.filter(JournalEntryLine.account_id == int(account_id))
            if user_branch_ids(): oq = oq.filter(((JournalEntryLine.branch_id.is_(None))|(JournalEntryLine.branch_id.in_(user_branch_ids()))))
            for x in oq.all():
                opening_balance += float(x.debit or 0) - float(x.credit or 0)
    with get_session() as s:
        q=s.query(JournalEntryLine).join(JournalEntry).options(joinedload(JournalEntryLine.account),joinedload(JournalEntryLine.entry)).order_by(JournalEntry.date,JournalEntry.id,JournalEntryLine.id)
        if account_id: q=q.filter(JournalEntryLine.account_id==int(account_id))
        if df: q=q.filter(JournalEntry.date >= df)
        if dt: q=q.filter(JournalEntry.date <= dt)
        if user_branch_ids(): q=q.filter(((JournalEntryLine.branch_id.is_(None))|(JournalEntryLine.branch_id.in_(user_branch_ids()))))
        rows=q.all(); running=opening_balance; out=[]
        for x in rows:
            running += float(x.debit or 0)-float(x.credit or 0)
            out.append({"date":x.entry.date,"number":x.entry.number,"account":x.account.name,"code":x.account.code,"description":x.description or x.entry.description,"debit":float(x.debit or 0),"credit":float(x.credit or 0),"balance":running})
        return {"rows": out, "opening_balance": opening_balance, "closing_balance": running}


def _invoice_settlements(s, invoices):
    """السداد وقت البيع للفواتير (كاشير/POS): [(invoice, اسم الطريقة, المبلغ)] للأجزاء غير الآجلة - عشان كشف العميل ما يعتبرهاش دين."""
    from .db import SalesInvoicePayment
    invs = [i for i in invoices if getattr(i, "is_pos", False) and not i.voided]
    if not invs:
        return []
    pays = {}
    for pr in s.query(SalesInvoicePayment).filter(SalesInvoicePayment.invoice_id.in_([i.id for i in invs])).order_by(SalesInvoicePayment.id).all():
        pays.setdefault(pr.invoice_id, []).append(pr)
    methods = {m.name: m for m in s.query(PaymentMethod).all()}
    out = []
    for i in invs:
        if i.id in pays:
            out += [(i, pr.method_name or "-", float(pr.amount or 0)) for pr in pays[i.id] if not pr.is_credit and (pr.amount or 0) > 0]
        else:   # فاتورة POS قديمة (قبل جدول المدفوعات): طريقة واحدة بإجمالي الفاتورة
            m = methods.get(i.payment_method or "")
            if m is not None and not m.is_credit:
                out.append((i, i.payment_method, float(i.total or 0)))
    return out


def party_statement(party_type, party_id, date_from=None, date_to=None):
    """كشف حساب متحرك: رصيد افتتاحي + حركات مرتبة زمنياً + رصيد تراكمي."""
    is_customer = party_type == "customer"
    df, dt = _dt_start(date_from), _dt_end(date_to)
    with get_session() as s:
        if is_customer:
            invoices_q = s.query(SalesInvoice).filter(SalesInvoice.customer_id == int(party_id))
            pays_q = s.query(Payment).filter(Payment.partner_type == "customer", Payment.partner_id == int(party_id), Payment.payment_type == "receipt")
        else:
            invoices_q = s.query(PurchaseInvoice).filter(PurchaseInvoice.supplier_id == int(party_id))
            pays_q = s.query(Payment).filter(Payment.partner_type == "supplier", Payment.partner_id == int(party_id), Payment.payment_type == "payment")
        if user_branch_ids():
            invoices_q=invoices_q.filter(((SalesInvoice.branch_id if is_customer else PurchaseInvoice.branch_id).is_(None))|((SalesInvoice.branch_id if is_customer else PurchaseInvoice.branch_id).in_(user_branch_ids())))
            pays_q=pays_q.filter(((Payment.branch_id.is_(None))|(Payment.branch_id.in_(user_branch_ids()))))
        if df:
            invoices_q = invoices_q.filter((SalesInvoice.date if is_customer else PurchaseInvoice.date) < df)
            pays_q = pays_q.filter(Payment.date < df)
        opening = 0.0
        if df:   # الرصيد الافتتاحي = كل ما قبل تاريخ البداية فقط (من غير تاريخ بداية الافتتاحي صفر وإلا الحركات تتحسب مرتين)
            _prior = invoices_q.all()
            opening += sum(float(x.total or 0) for x in _prior)
            opening -= sum(float(x.amount or 0) for x in pays_q.all())
            if is_customer:
                opening -= sum(a for _, _, a in _invoice_settlements(s, _prior))

        if is_customer:
            invoices_q = s.query(SalesInvoice).filter(SalesInvoice.customer_id == int(party_id))
        else:
            invoices_q = s.query(PurchaseInvoice).filter(PurchaseInvoice.supplier_id == int(party_id))
        if user_branch_ids(): invoices_q=invoices_q.filter(((SalesInvoice.branch_id if is_customer else PurchaseInvoice.branch_id).is_(None))|((SalesInvoice.branch_id if is_customer else PurchaseInvoice.branch_id).in_(user_branch_ids())))
        pays_q = s.query(Payment).filter(Payment.partner_type == ("customer" if is_customer else "supplier"), Payment.partner_id == int(party_id), Payment.payment_type == ("receipt" if is_customer else "payment"))
        if user_branch_ids(): pays_q=pays_q.filter(((Payment.branch_id.is_(None))|(Payment.branch_id.in_(user_branch_ids()))))
        if df:
            invoices_q = invoices_q.filter((SalesInvoice.date if is_customer else PurchaseInvoice.date) >= df)
            pays_q = pays_q.filter(Payment.date >= df)
        if dt:
            invoices_q = invoices_q.filter((SalesInvoice.date if is_customer else PurchaseInvoice.date) <= dt)
            pays_q = pays_q.filter(Payment.date <= dt)
        rows=[]
        for inv in invoices_q.all():
            amt=float(inv.total or 0)
            rows.append({"date":inv.date,"number":inv.number,"description":"فاتورة مبيعات" if is_customer else "فاتورة مشتريات",
                         "debit":amt if is_customer else 0.0,"credit":0.0 if is_customer else amt,"balance":0.0})
        if is_customer:
            for inv, mname, amt in _invoice_settlements(s, invoices_q.all()):
                rows.append({"date":inv.date,"number":inv.number,"description":f"سداد فاتورة {inv.number} ({mname})","debit":0.0,"credit":amt,"balance":0.0})
        for pay in pays_q.all():
            amt=float(pay.amount or 0)
            rows.append({"date":pay.date,"number":pay.number,"description":"سند قبض" if is_customer else "سند صرف",
                         "debit":0.0 if is_customer else amt,"credit":amt if is_customer else 0.0,"balance":0.0})
        rows.sort(key=lambda x:(x["date"],x["number"]))
        balance=opening
        out=[{"date":df,"number":"","description":"الرصيد الافتتاحي","debit":max(opening,0.0) if is_customer else 0.0,"credit":0.0 if is_customer else max(opening,0.0),"balance":opening}] if df else []
        for r in rows:
            balance += (r["debit"]-r["credit"]) if is_customer else (r["credit"]-r["debit"])   # الرصيد الموجب = مستحق (علينا للمورد / على العميل لنا)
            r["balance"]=balance; out.append(r)
        return {"opening":opening,"rows":out,"closing":balance,"party_type":party_type,"party_id":int(party_id)}

def aging_report(party_type):
    now=datetime.datetime.now(); result=[]
    with get_session() as s:
        if party_type=="customer":
            invoices=s.query(SalesInvoice).filter(SalesInvoice.customer_id.isnot(None)).order_by(SalesInvoice.date).all()
            parties={x.id:x.name for x in s.query(Customer).all()}; payments=s.query(Payment).filter(Payment.partner_type=="customer",Payment.payment_type=="receipt").order_by(Payment.date).all()
        else:
            invoices=s.query(PurchaseInvoice).filter(PurchaseInvoice.supplier_id.isnot(None)).order_by(PurchaseInvoice.date).all()
            parties={x.id:x.name for x in s.query(Supplier).all()}; payments=s.query(Payment).filter(Payment.partner_type=="supplier",Payment.payment_type=="payment").order_by(Payment.date).all()
        paid={}
        for p in payments: paid[p.partner_id]=paid.get(p.partner_id,0)+float(p.amount or 0)
        _settled = {}
        if party_type == "customer":
            for _i, _n, _a in _invoice_settlements(s, invoices):
                _settled[_i.id] = _settled.get(_i.id, 0.0) + _a
        for inv in invoices:
            amount=max(0.0, float(inv.total or 0) - _settled.get(inv.id, 0.0)); used=min(amount,paid.get(inv.customer_id if party_type=="customer" else inv.supplier_id,0)); paid[inv.customer_id if party_type=="customer" else inv.supplier_id]=paid.get(inv.customer_id if party_type=="customer" else inv.supplier_id,0)-used; due=amount-used
            if due<=0.005: continue
            days=max(0,(now-inv.date).days); bucket="0-30" if days<=30 else "31-60" if days<=60 else "61-90" if days<=90 else "90+"
            result.append({"party_id":inv.customer_id if party_type=="customer" else inv.supplier_id,"party":parties.get(inv.customer_id if party_type=="customer" else inv.supplier_id,"-"),"number":inv.number,"date":inv.date,"days":days,"bucket":bucket,"due":due})
    return result


def product_movement_report(product_id=None, location_id=None, date_from=None, date_to=None):
    from . import field_access as _fa
    _cost_visible = _fa.can_see("cost_price")
    with get_session() as s:
        q=s.query(StockMove).options(joinedload(StockMove.product),joinedload(StockMove.location)).order_by(StockMove.date,StockMove.id)
        if product_id: q=q.filter(StockMove.product_id==int(product_id))
        if location_id: q=q.filter(StockMove.location_id==int(location_id))
        if date_from: q=q.filter(StockMove.date>=date_from)
        if date_to: q=q.filter(StockMove.date<=date_to)
        rows=q.all(); running_by_product={}; out=[]
        for m in rows:
            qty=float(m.quantity or 0)
            running = running_by_product.get(m.product_id, 0.0) + (qty if m.direction=="in" else -qty)      # الرصيد المتحرك لكل صنف لوحده (مش مجمّع على الأصناف كلها)
            running_by_product[m.product_id] = running
            out.append({"date":m.date,"product":m.product.name,"sku":m.product.sku,"location":m.location.name,"direction":m.direction,"quantity":qty,"unit_cost":(float(m.unit_cost or 0) if _cost_visible else None),"value":(qty*float(m.unit_cost or 0) if _cost_visible else None),"reference":m.reference,"balance":running})
        return out


def inventory_count_report(location_id=None, date_from=None, date_to=None):
    with get_session() as s:
        q=s.query(InventoryAdjustment).options(joinedload(InventoryAdjustment.location),joinedload(InventoryAdjustment.lines).joinedload(InventoryAdjustmentLine.product)).order_by(InventoryAdjustment.date.desc())
        if location_id:q=q.filter(InventoryAdjustment.location_id==int(location_id))
        if date_from:q=q.filter(InventoryAdjustment.date>=date_from)
        if date_to:q=q.filter(InventoryAdjustment.date<=date_to)
        return q.all()



# ============================== Executive Dashboard ==============================
def _month_ranges(date_from=None, date_to=None):
    """Return calendar months covering the requested range."""
    df = _dt_start(date_from) or datetime.datetime(datetime.datetime.now().year, 1, 1)
    dt = _dt_end(date_to) or datetime.datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
    cur = datetime.datetime(df.year, df.month, 1)
    out = []
    while cur <= dt:
        if cur.month == 12:
            nxt = datetime.datetime(cur.year + 1, 1, 1)
        else:
            nxt = datetime.datetime(cur.year, cur.month + 1, 1)
        start = max(cur, df)
        end = min(nxt - datetime.timedelta(microseconds=1), dt)
        out.append((start, end, cur.strftime('%Y-%m')))
        cur = nxt
    return out


def _scope_invoice_query(q, model, branch_id=None, cost_center_id=None):
    if branch_id:
        q = q.filter(model.branch_id == int(branch_id))
    elif user_branch_ids():
        q = q.filter(((model.branch_id.is_(None))|(model.branch_id.in_(user_branch_ids()))))
    if cost_center_id:
        q = q.filter(model.cost_center_id == int(cost_center_id))
    elif user_cost_center_ids():
        q = q.filter(((model.cost_center_id.is_(None))|(model.cost_center_id.in_(user_cost_center_ids()))))
    return q


def executive_monthly_trend(date_from=None, date_to=None, branch_id=None, cost_center_id=None):
    """Monthly revenue, expenses, profit, sales invoices and purchases for executive charts."""
    _check_scope(branch_id, cost_center_id)
    months = _month_ranges(date_from, date_to)
    out=[]
    for start,end,key in months:
        k = management_kpis(start,end,branch_id,cost_center_id)
        with get_session() as s:
            sq=_scope_invoice_query(s.query(SalesInvoice), SalesInvoice, branch_id, cost_center_id)
            pq=_scope_invoice_query(s.query(PurchaseInvoice), PurchaseInvoice, branch_id, cost_center_id)
            sales_count=sq.filter(SalesInvoice.date>=start,SalesInvoice.date<=end).count()
            purchase_count=pq.filter(PurchaseInvoice.date>=start,PurchaseInvoice.date<=end).count()
        out.append({'key':key,'label':start.strftime('%b %Y'),'revenue':round(k['revenue'],2),'expense':round(k['expense'],2),'profit':round(k['profit'],2),'sales_count':sales_count,'purchase_count':purchase_count})
    return out


def executive_top_customers(date_from=None,date_to=None,branch_id=None,cost_center_id=None,limit=10):
    _check_scope(branch_id,cost_center_id); df,dt=_dt_start(date_from),_dt_end(date_to)
    with get_session() as s:
        q=_scope_invoice_query(s.query(SalesInvoice).options(joinedload(SalesInvoice.customer)),SalesInvoice,branch_id,cost_center_id)
        if df:q=q.filter(SalesInvoice.date>=df)
        if dt:q=q.filter(SalesInvoice.date<=dt)
        totals={}
        for inv in q.all():
            cid=inv.customer_id or 0; name=inv.customer.name if inv.customer else 'عميل نقدي / غير محدد'
            totals[cid]=totals.get(cid,{'id':cid,'name':name,'sales':0.0,'count':0})
            totals[cid]['sales']+=float(inv.total or 0); totals[cid]['count']+=1
        return sorted(totals.values(),key=lambda x:x['sales'],reverse=True)[:int(limit)]


def executive_top_products(date_from=None,date_to=None,branch_id=None,cost_center_id=None,limit=10):
    _check_scope(branch_id,cost_center_id); df,dt=_dt_start(date_from),_dt_end(date_to)
    with get_session() as s:
        q=_scope_invoice_query(s.query(SalesInvoice).options(joinedload(SalesInvoice.items).joinedload(SalesInvoiceItem.product)),SalesInvoice,branch_id,cost_center_id)
        if df:q=q.filter(SalesInvoice.date>=df)
        if dt:q=q.filter(SalesInvoice.date<=dt)
        totals={}
        for inv in q.all():
            for item in inv.items:
                pid=item.product_id; p=item.product
                if not p: continue
                x=totals.setdefault(pid,{'id':pid,'sku':p.sku,'name':p.name,'qty':0.0,'sales':0.0,'count':0})
                x['qty']+=float(item.quantity or 0); x['sales']+=float(item.line_total or 0); x['count']+=1
        return sorted(totals.values(),key=lambda x:x['sales'],reverse=True)[:int(limit)]


def executive_receivables_aging(date_from=None,date_to=None,branch_id=None,cost_center_id=None):
    """Customer receivables aging, allocated by invoice and filtered by organization scope."""
    _check_scope(branch_id,cost_center_id); now=datetime.datetime.now(); df,dt=_dt_start(date_from),_dt_end(date_to)
    with get_session() as s:
        iq=s.query(SalesInvoice).options(joinedload(SalesInvoice.customer)).filter(SalesInvoice.customer_id.isnot(None))
        pq=s.query(Payment).filter(Payment.partner_type=='customer',Payment.payment_type=='receipt')
        if branch_id: iq=iq.filter(SalesInvoice.branch_id==int(branch_id)); pq=pq.filter(Payment.branch_id==int(branch_id))
        elif user_branch_ids(): iq=iq.filter(((SalesInvoice.branch_id.is_(None))|(SalesInvoice.branch_id.in_(user_branch_ids())))); pq=pq.filter(((Payment.branch_id.is_(None))|(Payment.branch_id.in_(user_branch_ids()))))
        if cost_center_id: iq=iq.filter(SalesInvoice.cost_center_id==int(cost_center_id)); pq=pq.filter(Payment.cost_center_id==int(cost_center_id))
        elif user_cost_center_ids(): iq=iq.filter(((SalesInvoice.cost_center_id.is_(None))|(SalesInvoice.cost_center_id.in_(user_cost_center_ids())))); pq=pq.filter(((Payment.cost_center_id.is_(None))|(Payment.cost_center_id.in_(user_cost_center_ids()))))
        if df: iq=iq.filter(SalesInvoice.date<=dt if not dt else SalesInvoice.date<=dt)
        if dt: pq=pq.filter(Payment.date<=dt)
        payments={}
        for pay in pq.order_by(Payment.date).all(): payments[pay.partner_id]=payments.get(pay.partner_id,0)+float(pay.amount or 0)
        buckets={'0-30':0.0,'31-60':0.0,'61-90':0.0,'90+':0.0}; rows=[]
        for inv in iq.order_by(SalesInvoice.date).all():
            amt=float(inv.total or 0); used=min(amt,payments.get(inv.customer_id,0)); payments[inv.customer_id]=payments.get(inv.customer_id,0)-used; due=amt-used
            if due<=0.005: continue
            days=max(0,(now-inv.date).days)
            bucket='0-30' if days<=30 else '31-60' if days<=60 else '61-90' if days<=90 else '90+'
            buckets[bucket]+=due
            rows.append({'party_id':inv.customer_id,'party':inv.customer.name if inv.customer else '-', 'number':inv.number,'date':inv.date,'days':days,'bucket':bucket,'due':round(due,2)})
        rows.sort(key=lambda x:x['due'],reverse=True)
        return {'buckets':{k:round(v,2) for k,v in buckets.items()},'total':round(sum(buckets.values()),2),'rows':rows}


def executive_inventory(branch_id=None,cost_center_id=None,limit=10):
    _check_scope(branch_id,cost_center_id)
    report=get_stock_balance_report(branch_id=branch_id)
    total_value=sum(float(x['value'] or 0) for x in report); low=[x for x in report if x['is_low']]
    top=sorted(report,key=lambda x:float(x['value'] or 0),reverse=True)[:int(limit)]
    top_rows=[{'id':x['product'].id,'sku':x['product'].sku,'name':x['product'].name,'balance':float(x['balance']),'unit':x['product'].unit,'value':float(x['value']),'is_low':x['is_low']} for x in top]
    return {'total_value':round(total_value,2),'total_qty':round(sum(float(x['balance']) for x in report),2),'product_count':len(report),'low_count':len(low),'top':top_rows,'low':sorted([{'id':x['product'].id,'sku':x['product'].sku,'name':x['product'].name,'balance':float(x['balance']),'reorder_point':float(x['product'].reorder_point),'value':float(x['value'])} for x in low],key=lambda x:x['balance'])[:int(limit)]}


def executive_branch_ranking(date_from=None,date_to=None,cost_center_id=None):
    rows=branch_comparison(date_from,date_to)
    ids=user_branch_ids()
    if ids: rows=[x for x in rows if x.get('branch_id') in ids]
    if cost_center_id:
        rows=[dict(x, **{'profit':management_kpis(date_from,date_to,x['branch_id'],cost_center_id)['profit']}) for x in rows]
    return sorted(rows,key=lambda x:float(x.get('profit',0) or 0),reverse=True)


# كاش قصير للوحة المؤشرات: بيتجدّد عند أي حفظ (commit) في القاعدة أو بعد DASH_TTL ثانية، ومفصول لكل مستخدم/صلاحيات (فمفيش تسريب بيانات بين المستخدمين)
DASH_TTL = float(os.environ.get("ERP_DASH_CACHE_SECS", "30"))
_DASH_CACHE = {}
_DB_VERSION = [0]
_DASH_LOCK = _threading.Lock()


def _bump_db_version(_session=None):
    _DB_VERSION[0] += 1


from sqlalchemy import event as _sa_ev
from sqlalchemy.orm import Session as _SASession
_sa_ev.listen(_SASession, "after_commit", _bump_db_version)


def executive_dashboard(date_from=None,date_to=None,branch_id=None,cost_center_id=None):
    """لوحة الإدارة (كل القيم بتحترم نطاق المستخدم). مخزّنة مؤقتًا لمدة قصيرة وبتتجدّد مع أي تعديل في البيانات."""
    import copy
    import hashlib
    import time
    if DASH_TTL <= 0:
        return _executive_dashboard_uncached(date_from,date_to,branch_id,cost_center_id)
    u=_get_user()
    uk=hashlib.md5(json.dumps(u,sort_keys=True,default=str).encode()).hexdigest() if u else ""
    key=(uk,str(date_from),str(date_to),branch_id,cost_center_id)
    ver=_DB_VERSION[0]
    with _DASH_LOCK:
        hit=_DASH_CACHE.get(key)
    if hit and hit[0]==ver and time.time()-hit[1]<DASH_TTL:
        return copy.deepcopy(hit[2])
    data=_executive_dashboard_uncached(date_from,date_to,branch_id,cost_center_id)
    with _DASH_LOCK:
        if len(_DASH_CACHE)>200:
            _DASH_CACHE.clear()
        _DASH_CACHE[key]=(ver,time.time(),copy.deepcopy(data))
    return data


def _executive_dashboard_uncached(date_from=None,date_to=None,branch_id=None,cost_center_id=None):
    k=management_kpis(date_from,date_to,branch_id,cost_center_id)
    inv=executive_inventory(branch_id,cost_center_id)
    return mask_dashboard({'kpis':k,'monthly':executive_monthly_trend(date_from,date_to,branch_id,cost_center_id),
            'branches':executive_branch_ranking(date_from,date_to,cost_center_id),
            'customers':executive_top_customers(date_from,date_to,branch_id,cost_center_id),
            'products':executive_top_products(date_from,date_to,branch_id,cost_center_id),
            'aging':executive_receivables_aging(date_from,date_to,branch_id,cost_center_id),
            'inventory':inv})


def mask_dashboard(d):
    """إخفاء الأرباح/الهوامش و/أو قيم المخزون (التكلفة) من حمولة لوحة الإدارة حسب صلاحيات الحقول للمستخدم الحالي."""
    from . import field_access as fa
    hid = fa.hidden_fields()
    if "profit" in hid:
        for key in ("profit", "gross_profit", "net_margin_pct", "gross_margin_pct"):
            if key in d.get("kpis", {}):
                d["kpis"][key] = None
        for m in d.get("monthly", []):
            m["profit"] = None
        for b in d.get("branches", []):
            b["profit"] = None
    if "cost_price" in hid:
        inv = d.get("inventory") or {}
        inv["total_value"] = None
        for r in inv.get("top", []) + inv.get("low", []):
            r["value"] = None
    return d


# ============================== Inventory Adjustments ==============================
def create_inventory_adjustment(location_id, counts, notes="", branch_id=None, cost_center_id=None, adjustment_date=None):
    require_action("inventory_adjustments", "create")
    from .db import InventoryAdjustment, InventoryAdjustmentLine
    if not counts: raise ValueError("أدخل جرد صنف واحد على الأقل")
    cfg=_accounting_settings()
    branch_id = branch_id or default_branch_id()
    cost_center_id = cost_center_id or default_cost_center_id()
    if branch_id and not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    # موافقة المدير على التسويات الكبيرة (قبل أي كتابة): قيمة الفروق = |الفرق| × التكلفة
    from . import approvals as _appr
    if _appr.needs_approval("inventory_adjustment", 10 ** 12):
        _th = get_balances_map(int(location_id), branch_id, as_of=adjustment_date)
        with get_session() as s0:
            _costs = {p.id: float(p.cost_price or 0) for p in s0.query(Product).filter(Product.id.in_([int(x) for x in counts.keys()])).all()}
        _aval = round(sum(abs(float(c) - _th.get(int(pid), 0.0)) * _costs.get(int(pid), 0.0) for pid, c in counts.items()), 2)
        _appr.guard("inventory_adjustment", _aval, f"{location_id}:{_aval:.2f}", summary=f"مخزن #{location_id} - {len(counts)} صنف")
    with get_session() as s:
        loc=s.get(Location,int(location_id))
        if loc and loc.branch_id and branch_id and int(loc.branch_id)!=int(branch_id): raise ValueError("المخزن لا يتبع الفرع المختار")
        _db_lock(s)
        last=s.query(InventoryAdjustment).order_by(InventoryAdjustment.id.desc()).first()
        num=f"ADJ-{((last.id+1) if last else 1):06d}"
        adj=InventoryAdjustment(number=num, location_id=int(location_id), branch_id=branch_id, cost_center_id=cost_center_id, notes=notes or "")
        if adjustment_date:
            adj.date = adjustment_date
        s.add(adj); s.flush(); payload=[]
        # الرصيد الدفتري = رصيد المخزن لحد تاريخ التسوية (مش الرصيد الحالي)
        theory_map = get_balances_map(int(location_id), branch_id, as_of=adjustment_date)
        current_map = get_balances_map(int(location_id), branch_id) if adjustment_date else None
        prod_map = {p.id: p for p in s.query(Product).filter(Product.id.in_([int(x) for x in counts.keys()])).all()}
        for pid, counted in counts.items():
            p=prod_map.get(int(pid)) or s.get(Product, int(pid)); theoretical=theory_map.get(int(pid), 0.0); counted=float(counted); diff=counted-theoretical
            if abs(diff) < 1e-9: continue
            cost=float(p.cost_price or 0)
            if current_map is not None and diff < 0 and current_map.get(p.id, 0.0) + 1e-9 < -diff:
                raise ValueError(f"«{p.name}»: عجز الجرد ({-diff:g}) أكبر من الرصيد الحالي ({current_map.get(p.id, 0.0):g}) بسبب حركات بعد تاريخ الجرد - سجّل الجرد بتاريخ أحدث أو راجع الحركات اللاحقة")
            s.add(InventoryAdjustmentLine(adjustment_id=adj.id, product_id=p.id, theoretical_qty=theoretical, counted_qty=counted, difference_qty=diff, unit_cost=cost))
            payload.append((p.id,diff,cost,p.name))
        if not payload: raise ValueError("لا توجد فروق جرد للحفظ")
        s.commit(); adj_id=adj.id; adj_num=adj.number
    journal=[]
    for pid,diff,cost,name in payload:
        create_stock_move(pid, int(location_id), "in" if diff>0 else "out", abs(diff), cost, f"ADJ:{adj_num}", "تسوية جرد", branch_id=branch_id, cost_center_id=cost_center_id, _internal=True, move_date=adjustment_date, allow_expired=True)
        value=round(abs(diff)*cost,2)
        if value:
            if diff>0: journal += [{"account_id":cfg.inventory_account_id,"debit":value,"description":name},{"account_id":cfg.inventory_gain_account_id,"credit":value,"description":name}]
            else: journal += [{"account_id":cfg.inventory_loss_account_id,"debit":value,"description":name},{"account_id":cfg.inventory_account_id,"credit":value,"description":name}]
    if journal: create_journal_entry(journal, reference=adj_num, description=f"تسوية جرد {adj_num}", source_type="inventory_adjustment", source_id=adj_id, branch_id=branch_id, cost_center_id=cost_center_id, entry_date=adjustment_date)
    return adj_id


def list_inventory_adjustments(limit=100):
    from .db import InventoryAdjustment, InventoryAdjustmentLine
    with get_session() as s:
        return s.query(InventoryAdjustment).options(joinedload(InventoryAdjustment.location), joinedload(InventoryAdjustment.lines).joinedload(InventoryAdjustmentLine.product)).order_by(InventoryAdjustment.date.desc()).limit(limit).all()


def get_inventory_adjustment_detail(adjustment_id):
    """تفاصيل تسوية جردية للمعاينة والطباعة: الرأس (الرقم، التاريخ، المخزن، الفرع، مركز التكلفة، الملاحظات، القيد المحاسبي) + سطور الفروق
    (الدفتري، الفعلي، الفرق، التكلفة، قيمة الفرق) + إجماليات الزيادة والعجز. السطور المخزّنة هي الفروق بس (الأصناف المطابقة مش بتتسجّل)."""
    from .db import InventoryAdjustment, InventoryAdjustmentLine
    with get_session() as s:
        a = (s.query(InventoryAdjustment).options(joinedload(InventoryAdjustment.location), joinedload(InventoryAdjustment.branch), joinedload(InventoryAdjustment.cost_center),
                                                  joinedload(InventoryAdjustment.lines).joinedload(InventoryAdjustmentLine.product))
             .filter(InventoryAdjustment.id == int(adjustment_id)).first())
        if not a:
            raise ValueError("التسوية غير موجودة")
        je = s.query(JournalEntry).filter(JournalEntry.source_type == "inventory_adjustment", JournalEntry.source_id == a.id).first()
        lines = []
        for l in sorted(a.lines, key=lambda x: x.product.sku if x.product else ""):
            diff = float(l.difference_qty or 0); cost = float(l.unit_cost or 0)
            lines.append({"sku": l.product.sku, "name": l.product.name, "unit": l.product.unit or "", "theoretical": float(l.theoretical_qty or 0), "counted": float(l.counted_qty or 0),
                          "difference": diff, "unit_cost": cost, "value": diff * cost})
        surplus = [l for l in lines if l["difference"] > 0]; shortage = [l for l in lines if l["difference"] < 0]
        return {"id": a.id, "number": a.number, "date": a.date, "location": a.location.name if a.location else "-", "branch": a.branch.name if a.branch else "-",
                "cost_center": a.cost_center.name if a.cost_center else "-", "notes": a.notes or "", "journal_number": je.number if je else "-", "lines": lines,
                "surplus_count": len(surplus), "shortage_count": len(shortage), "surplus_value": sum(l["value"] for l in surplus), "shortage_value": -sum(l["value"] for l in shortage),
                "net_value": sum(l["value"] for l in lines)}


def inventory_report(location_id=None):
    rows=get_stock_balance_report(location_id=location_id)
    from . import field_access as _fa
    if not _fa.can_see("cost_price"):
        rows=[dict(r,value=None) for r in rows]
        return {"rows":rows,"total_qty":sum(r['balance'] for r in rows),"total_value":None,"low_count":sum(1 for r in rows if r['is_low'])}
    return {"rows":rows,"total_qty":sum(r['balance'] for r in rows),"total_value":sum(r['value'] for r in rows),"low_count":sum(1 for r in rows if r['is_low'])}


# ============================== Professional Reports / Fiscal Periods ==============================
def _dt_end(value):
    if not value: return None
    if isinstance(value, datetime.datetime):
        return value.replace(hour=23, minute=59, second=59, microsecond=999999) if value.time() == datetime.time.min else value
    return datetime.datetime.combine(value, datetime.time(23,59,59))

def _dt_start(value):
    if not value: return None
    if isinstance(value, datetime.datetime): return value
    return datetime.datetime.combine(value, datetime.time.min)

def report_data(date_from=None, date_to=None, location_id=None, account_id=None, product_id=None, customer_id=None, supplier_id=None, branch_id=None, cost_center_id=None):
    if branch_id and not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    df, dt = _dt_start(date_from), _dt_end(date_to)
    with get_session() as s:
        # General ledger
        q=s.query(JournalEntryLine).join(JournalEntry).options(joinedload(JournalEntryLine.account), joinedload(JournalEntryLine.entry)).order_by(JournalEntry.date,JournalEntry.id,JournalEntryLine.id)
        if df:q=q.filter(JournalEntry.date>=df)
        if dt:q=q.filter(JournalEntry.date<=dt)
        if account_id:q=q.filter(JournalEntryLine.account_id==int(account_id))
        if branch_id:q=q.filter(JournalEntryLine.branch_id==int(branch_id))
        elif user_branch_ids():q=q.filter(((JournalEntryLine.branch_id.is_(None))|(JournalEntryLine.branch_id.in_(user_branch_ids()))))
        if cost_center_id:q=q.filter(JournalEntryLine.cost_center_id==int(cost_center_id))
        ledger=[]
        for x in q.all():
            ledger.append({'date':x.entry.date,'number':x.entry.number,'code':x.account.code,'account':x.account.name,'description':x.description or x.entry.description,'debit':float(x.debit or 0),'credit':float(x.credit or 0)})

        # Inventory movements
        mq=s.query(StockMove).options(joinedload(StockMove.product),joinedload(StockMove.location)).order_by(StockMove.date,StockMove.id)
        if df:mq=mq.filter(StockMove.date>=df)
        if dt:mq=mq.filter(StockMove.date<=dt)
        if location_id:mq=mq.filter(StockMove.location_id==int(location_id))
        if product_id:mq=mq.filter(StockMove.product_id==int(product_id))
        if branch_id:mq=mq.filter(StockMove.branch_id==int(branch_id))
        elif user_branch_ids():mq=mq.filter(((StockMove.branch_id.is_(None))|(StockMove.branch_id.in_(user_branch_ids()))))
        if cost_center_id:mq=mq.filter(StockMove.cost_center_id==int(cost_center_id))
        moves=[]
        for m in mq.all():
            moves.append({'date':m.date,'sku':m.product.sku,'product':m.product.name,'location':m.location.name,'direction':m.direction,'quantity':float(m.quantity or 0),'unit_cost':float(m.unit_cost or 0),'value':float(m.quantity or 0)*float(m.unit_cost or 0),'reference':m.reference})

        # Sales / purchases summary
        sq=s.query(SalesInvoice).options(joinedload(SalesInvoice.customer))
        pq=s.query(PurchaseInvoice).options(joinedload(PurchaseInvoice.supplier))
        if df:sq=sq.filter(SalesInvoice.date>=df); pq=pq.filter(PurchaseInvoice.date>=df)
        if dt:sq=sq.filter(SalesInvoice.date<=dt); pq=pq.filter(PurchaseInvoice.date<=dt)
        if customer_id:sq=sq.filter(SalesInvoice.customer_id==int(customer_id))
        if supplier_id:pq=pq.filter(PurchaseInvoice.supplier_id==int(supplier_id))
        if branch_id:sq=sq.filter(SalesInvoice.branch_id==int(branch_id)); pq=pq.filter(PurchaseInvoice.branch_id==int(branch_id))
        elif user_branch_ids():sq=sq.filter(((SalesInvoice.branch_id.is_(None))|(SalesInvoice.branch_id.in_(user_branch_ids())))); pq=pq.filter(((PurchaseInvoice.branch_id.is_(None))|(PurchaseInvoice.branch_id.in_(user_branch_ids()))))
        if cost_center_id:sq=sq.filter(SalesInvoice.cost_center_id==int(cost_center_id)); pq=pq.filter(PurchaseInvoice.cost_center_id==int(cost_center_id))
        sales=[{'date':x.date,'number':x.number,'party':x.customer.name if x.customer else '-', 'total':float(x.total or 0)} for x in sq.order_by(SalesInvoice.date).all()]
        purchases=[{'date':x.date,'number':x.number,'party':x.supplier.name if x.supplier else '-', 'total':float(x.total or 0)} for x in pq.order_by(PurchaseInvoice.date).all()]
        accounts=s.query(Account).order_by(Account.code).all()
        balances={a.id:{'code':a.code,'name':a.name,'type':a.account_type,'debit':0.0,'credit':0.0} for a in accounts}
        for x in ledger:
            a=next((a for a in accounts if a.code==x['code']),None)
            if a: balances[a.id]['debit']+=x['debit']; balances[a.id]['credit']+=x['credit']
        trial=[]
        for a in accounts:
            b=balances[a.id]; b['balance']=b['debit']-b['credit'];
            if b['debit'] or b['credit']: trial.append(b)
        income=sum(b['credit']-b['debit'] for b in trial if b['type']=='income')
        expense=sum(b['debit']-b['credit'] for b in trial if b['type']=='expense')
        assets=sum(b['debit']-b['credit'] for b in trial if b['type']=='asset')
        liabilities=sum(b['credit']-b['debit'] for b in trial if b['type']=='liability')
        equity=sum(b['credit']-b['debit'] for b in trial if b['type']=='equity')
        return {'ledger':ledger,'moves':moves,'sales':sales,'purchases':purchases,'trial_balance':trial,'income':income,'expense':expense,'profit':income-expense,'assets':assets,'liabilities':liabilities,'equity':equity,'equity_with_profit':equity+income-expense, 'date_from':df, 'date_to':dt}

def list_fiscal_periods():
    with get_session() as s:
        return s.query(FiscalPeriod).order_by(FiscalPeriod.date_from.desc()).all()

def create_fiscal_period(name,date_from,date_to):
    require_action("fiscal_periods", "create")
    with get_session() as s:
        if not name or not name.strip(): raise ValueError('اسم الفترة مطلوب')
        if date_to<date_from: raise ValueError('تاريخ نهاية السنة يجب أن يكون بعد تاريخ البداية')
        start, end = _dt_start(date_from), _dt_end(date_to)
        overlap=s.query(FiscalPeriod).filter(FiscalPeriod.date_from<=end, FiscalPeriod.date_to>=start).count()
        if overlap: raise ValueError('الفترة الجديدة تتداخل مع فترة مالية موجودة')
        p=FiscalPeriod(name=name.strip(),date_from=start,date_to=end); s.add(p); s.commit(); s.refresh(p); return p.id

def _account_balances_until(date_to=None, date_from=None, include_types=None, branch_id=None, cost_center_id=None):
    df, dt = _dt_start(date_from), _dt_end(date_to)
    with get_session() as s:
        q=(s.query(Account.id,Account.code,Account.name,Account.account_type,
                  func.coalesce(func.sum(JournalEntryLine.debit),0).label('debit'),
                  func.coalesce(func.sum(JournalEntryLine.credit),0).label('credit'))
            .join(JournalEntryLine, JournalEntryLine.account_id==Account.id)
            .join(JournalEntry, JournalEntry.id==JournalEntryLine.entry_id))
        if df:q=q.filter(JournalEntry.date>=df)
        if dt:q=q.filter(JournalEntry.date<=dt)
        if include_types:q=q.filter(Account.account_type.in_(include_types))
        if branch_id:q=q.filter(JournalEntryLine.branch_id==int(branch_id))
        elif user_branch_ids():q=q.filter(((JournalEntryLine.branch_id.is_(None))|(JournalEntryLine.branch_id.in_(user_branch_ids()))))
        if cost_center_id:q=q.filter(JournalEntryLine.cost_center_id==int(cost_center_id))
        rows=q.group_by(Account.id).order_by(Account.code).all()
        return [{"id":r.id,"code":r.code,"name":r.name,"type":r.account_type,"debit":float(r.debit or 0),"credit":float(r.credit or 0),"balance":float(r.debit or 0)-float(r.credit or 0)} for r in rows]

def detailed_income_statement(date_from=None, date_to=None, branch_id=None, cost_center_id=None):
    rows=_rolled_account_rows(date_from,date_to,["income","expense"],branch_id,cost_center_id)
    income=[dict(r, amount=round(r['credit']-r['debit'],2)) for r in rows if r['type']=='income' and abs(r['credit']-r['debit'])>0.005]
    expense=[dict(r, amount=round(r['debit']-r['credit'],2)) for r in rows if r['type']=='expense' and abs(r['debit']-r['credit'])>0.005]
    # الإجمالي يحسب من الحسابات العليا فقط حتى لا يتكرر رصيد الحساب الأب مع أبنائه.
    total_income=sum(r['amount'] for r in income if not r.get('parent_id'))
    total_expense=sum(r['amount'] for r in expense if not r.get('parent_id'))
    # إذا لم توجد حسابات عليا منشورة، استخدم الحسابات المفردة كحالة توافق قديمة.
    if not income: total_income=0.0
    elif abs(total_income)<0.005: total_income=sum(r['amount'] for r in income if not any(x.get('code')==r.get('code') for x in income if x.get('parent_id') is None))
    if not expense: total_expense=0.0
    elif abs(total_expense)<0.005: total_expense=sum(r['amount'] for r in expense if not r.get('parent_id'))
    return {"income":income,"expense":expense,"total_income":total_income,"total_expense":total_expense,"net_profit":total_income-total_expense,"date_from":_dt_start(date_from),"date_to":_dt_end(date_to)}

def detailed_balance_sheet(as_of=None, branch_id=None, cost_center_id=None):
    dt=_dt_end(as_of or datetime.datetime.now())
    rows=_rolled_account_rows(None,dt,["asset","liability","equity"],branch_id,cost_center_id)
    assets=[dict(r, amount=round(r['debit']-r['credit'],2)) for r in rows if r['type']=='asset' and abs(r['debit']-r['credit'])>0.005]
    liabilities=[dict(r, amount=round(r['credit']-r['debit'],2)) for r in rows if r['type']=='liability' and abs(r['credit']-r['debit'])>0.005]
    equity=[dict(r, amount=round(r['credit']-r['debit'],2)) for r in rows if r['type']=='equity' and (abs(r['debit'])+abs(r['credit'])>0.005)]
    # حساب صافي الربح الحالي فقط إذا لم يكن قد تم ترحيله بعد إلى الأرباح المرحلة.
    inc=_account_balances_until(dt,None,["income","expense"],branch_id,cost_center_id)
    current_profit=sum(r['credit']-r['debit'] for r in inc if r['type']=='income')-sum(r['debit']-r['credit'] for r in inc if r['type']=='expense')
    # بعد الإقفال السنوي تصبح حسابات الدخل والمصروف صفراً، وبالتالي لا نضيف ربحاً مرتين.
    total_assets=sum(r['amount'] for r in assets if not r.get('parent_id')); total_liab=sum(r['amount'] for r in liabilities if not r.get('parent_id')); total_equity=sum(r['amount'] for r in equity if not r.get('parent_id'))
    balance_gap=round(total_assets-(total_liab+total_equity),2)
    if abs(balance_gap)>0.005 and abs(current_profit)>0.005:
        equity.append({"id":None,"code":"CURRENT","name":"صافي الربح / (الخسارة) للفترة","type":"equity","debit":0.0,"credit":current_profit if current_profit>0 else -current_profit,"balance":-current_profit,"amount":current_profit})
        total_equity += current_profit
    return {"assets":assets,"liabilities":liabilities,"equity":equity,"total_assets":total_assets,"total_liabilities":total_liab,"total_equity":total_equity,"current_profit":current_profit,"balance_gap":round(total_assets-(total_liab+total_equity),2),"as_of":dt}

def _cash_account_ids_by_type(s):
    """حسابات النقدية = أي حساب اتحدد نوع تدفقه النقدي 'cash' (زي
    x_cash_flow_activity في موديول أودو)."""
    ids = {a.id for a in s.query(Account).filter(Account.cash_flow_type == "cash").all()}
    if not ids:
        return set()
    changed = True
    while changed:
        changed = False
        for a in s.query(Account).filter(Account.parent_id.in_(ids)).all():
            if a.id not in ids:
                ids.add(a.id); changed = True
    return ids


def cash_flow_statement(date_from=None, date_to=None, branch_id=None, cost_center_id=None):
    """
    قائمة التدفقات النقدية بنفس منطق موديول أودو: تصنيف كل حساب (غير
    النقدية) لنشاط تشغيلي/استثماري/تمويلي عن طريق حقل "نوع التدفق النقدي"
    في شجرة الحسابات، مع مقبوضات ومدفوعات منفصلة لكل نشاط، وفرق غير
    مفسَّر للتأكد من التوازن.
    """
    from sqlalchemy import text, bindparam
    df, dt = _dt_start(date_from), _dt_end(date_to)
    with get_session() as s:
        cash_ids = _cash_account_ids_by_type(s)
        empty = {
            "operating_in": [], "operating_out": [], "investing_in": [], "investing_out": [],
            "financing_in": [], "financing_out": [], "net_operating": 0.0, "net_investing": 0.0,
            "net_financing": 0.0, "net": 0.0, "opening_cash": 0.0, "closing_cash": 0.0,
            "unexplained": 0.0, "cash_accounts": [],
            "operating": [], "investing": [], "financing": [],
        }
        if not cash_ids:
            return empty

        branch_clause = ""
        params = {"cash_ids": tuple(cash_ids), "date_from": df, "date_to": dt}
        if branch_id:
            branch_clause = " AND am.branch_id = :branch_id"
            params["branch_id"] = int(branch_id)
        elif user_branch_ids():
            branch_clause = " AND (am.branch_id IS NULL OR am.branch_id IN :ubids)"
            params["ubids"] = tuple(user_branch_ids())
        cc_clause = ""
        if cost_center_id:
            cc_clause = " AND aml.cost_center_id = :cost_center_id"
            params["cost_center_id"] = int(cost_center_id)

        query = f"""
            SELECT aml.account_id AS account_id, SUM(aml.credit - aml.debit) AS amount
            FROM journal_entry_lines aml
            JOIN journal_entries am ON am.id = aml.entry_id
            WHERE am.posted IS TRUE
              AND am.date BETWEEN :date_from AND :date_to
              AND aml.account_id NOT IN :cash_ids
              {branch_clause} {cc_clause}
              AND aml.entry_id IN (
                  SELECT DISTINCT entry_id FROM journal_entry_lines WHERE account_id IN :cash_ids
              )
            GROUP BY aml.account_id
        """
        rows = s.execute(
            text(query).bindparams(bindparam("cash_ids", expanding=True), *([bindparam("ubids", expanding=True)] if "ubids" in params else [])),
            params,
        ).fetchall()

        buckets = {"operating": {}, "investing": {}, "financing": {}}
        for account_id, amount in rows:
            amount = float(amount or 0)
            if abs(amount) < 0.005:
                continue
            account = s.get(Account, account_id)
            activity = (account.cash_flow_type if account and account.cash_flow_type in
                        ("operating", "investing", "financing") else "operating")
            key = f"{account.code} - {account.name}" if account else str(account_id)
            buckets[activity][key] = buckets[activity].get(key, 0.0) + amount

        def split_rows(d):
            cash_in = [{"description": k, "amount": round(v, 2)} for k, v in sorted(d.items()) if v > 0.005]
            cash_out = [{"description": k, "amount": round(v, 2)} for k, v in sorted(d.items()) if v < -0.005]
            return cash_in, cash_out

        operating_in, operating_out = split_rows(buckets["operating"])
        investing_in, investing_out = split_rows(buckets["investing"])
        financing_in, financing_out = split_rows(buckets["financing"])

        net_operating = round(sum(x["amount"] for x in operating_in + operating_out), 2)
        net_investing = round(sum(x["amount"] for x in investing_in + investing_out), 2)
        net_financing = round(sum(x["amount"] for x in financing_in + financing_out), 2)
        net = round(net_operating + net_investing + net_financing, 2)

        def cash_balance(as_of, before):
            op = "<" if before else "<="
            bal_query = f"""
                SELECT COALESCE(SUM(aml.debit - aml.credit), 0)
                FROM journal_entry_lines aml
                JOIN journal_entries am ON am.id = aml.entry_id
                WHERE am.posted IS TRUE AND aml.account_id IN :cash_ids
                  AND am.date {op} :as_of
                  {branch_clause} {cc_clause}
            """
            bal_params = dict(params)
            bal_params["as_of"] = as_of
            return float(s.execute(
                text(bal_query).bindparams(bindparam("cash_ids", expanding=True), *([bindparam("ubids", expanding=True)] if "ubids" in bal_params else [])),
                bal_params,
            ).scalar() or 0)

        opening = cash_balance(df, before=True) if df else 0.0
        closing = cash_balance(dt, before=False) if dt else cash_balance(_dt_end(None), before=False)
        unexplained = round(closing - opening - net, 2)

        return {
            "operating_in": operating_in, "operating_out": operating_out,
            "investing_in": investing_in, "investing_out": investing_out,
            "financing_in": financing_in, "financing_out": financing_out,
            "net_operating": net_operating, "net_investing": net_investing, "net_financing": net_financing,
            "net": net, "opening_cash": round(opening, 2), "closing_cash": round(closing, 2),
            "unexplained": unexplained, "cash_accounts": sorted(cash_ids),
            "operating": operating_in + operating_out,
            "investing": investing_in + investing_out,
            "financing": financing_in + financing_out,
        }


def close_fiscal_year(period_id):
    require_action("fiscal_periods", "close")
    """إقفال السنة: تصفير الإيرادات والمصروفات وترحيل صافي الربح إلى الأرباح المرحلة."""
    with get_session() as s:
        p=s.get(FiscalPeriod,int(period_id))
        if not p: raise ValueError('الفترة المالية غير موجودة')
        if p.closing_journal_id: raise ValueError('تم تنفيذ قيد الإقفال السنوي لهذه الفترة بالفعل')
        if p.is_closed: raise ValueError('الفترة مقفلة بالفعل')
        rows=_account_balances_until(p.date_to,p.date_from,["income","expense"])
        lines=[]; income_total=expense_total=0.0
        for r in rows:
            bal=r['debit']-r['credit']
            if r['type']=='income':
                amount=round(-bal,2)
                if amount>0: lines.append({"account_id":r['id'],"debit":amount,"description":"إقفال الإيرادات"})
                elif amount<0: lines.append({"account_id":r['id'],"credit":-amount,"description":"إقفال الإيرادات"})
                income_total += -bal
            elif r['type']=='expense':
                amount=round(bal,2)
                if amount>0: lines.append({"account_id":r['id'],"credit":amount,"description":"إقفال المصروفات"})
                elif amount<0: lines.append({"account_id":r['id'],"debit":-amount,"description":"إقفال المصروفات"})
                expense_total += bal
        profit=round(income_total-expense_total,2)
        cfg=s.get(AccountingSettings,1); re_id=cfg.retained_earnings_account_id if cfg else None
        if not re_id:
            re=s.query(Account).filter(Account.code.in_(("340000","3200"))).first(); re_id=re.id if re else None
        if not lines and abs(profit)<0.005:
            # سنة بلا نتيجة: نقفل الفترة بدون قيد.
            p.is_closed=True; p.closed_at=datetime.datetime.now(); s.commit(); return None
        if not re_id: raise ValueError('لم يتم تحديد حساب الأرباح المرحلة / المحتجزة (3200)')
        if profit>0: lines.append({"account_id":re_id,"credit":profit,"description":"ترحيل صافي الربح إلى الأرباح المرحلة"})
        elif profit<0: lines.append({"account_id":re_id,"debit":-profit,"description":"ترحيل صافي الخسارة إلى الأرباح المرحلة"})
    je=create_journal_entry(lines, reference=f"CLOSE-{p.id}", description=f"قيد الإقفال السنوي - {p.name}", source_type="annual_closing", source_id=p.id, entry_date=p.date_to)
    with get_session() as s:
        p=s.get(FiscalPeriod,int(period_id)); p.is_closed=True; p.closed_at=datetime.datetime.now(); p.closing_journal_id=je; s.commit()
    return je

def close_fiscal_period(period_id):
    require_action("fiscal_periods", "close")
    return close_fiscal_year(period_id)

def reopen_fiscal_period(period_id):
    require_action("fiscal_periods", "close")
    with get_session() as s:
        p=s.get(FiscalPeriod,int(period_id))
        if not p: raise ValueError('الفترة المالية غير موجودة')
        closing_id=p.closing_journal_id
        if not closing_id:
            p.is_closed=False;p.closed_at=None;s.commit();return
        e=s.get(JournalEntry,closing_id)
        if not e: p.is_closed=False;p.closed_at=None;p.closing_journal_id=None;s.commit();return
        # فتح الفترة أولاً للسماح بالقيد العكسي، ثم عكس قيد الإقفال.
        p.is_closed=False;p.closed_at=None;s.commit()
        reverse_lines=[{"account_id":l.account_id,"debit":float(l.credit or 0),"credit":float(l.debit or 0),"description":"عكس قيد الإقفال السنوي"} for l in e.lines]
    rev=create_journal_entry(reverse_lines, reference=f"REV-CLOSE-{period_id}", description=f"عكس قيد الإقفال السنوي - {p.name}", source_type="annual_closing_reversal", source_id=period_id, entry_date=p.date_to)
    with get_session() as s:
        p=s.get(FiscalPeriod,int(period_id)); p.closing_journal_id=None; s.commit()
    return rev

# ---------------- الإقفال الشهري ----------------
def list_month_closes():
    with get_session() as s:
        rows = s.query(MonthClose).order_by(MonthClose.year.desc(), MonthClose.month.desc()).all()
        s.expunge_all()
        return rows


def month_close_checks(year, month):
    """مشاكل بتمنع الإقفال (blockers) وملاحظات (warnings) للشهر."""
    first, last = _month_bounds(month, year)
    t0 = datetime.datetime(first.year, first.month, first.day)
    t1 = datetime.datetime(last.year, last.month, last.day) + datetime.timedelta(days=1)
    blockers, warnings = [], []
    today = datetime.date.today()
    if (year, month) >= (today.year, today.month):
        blockers.append("الشهر لسه ما خلصش - مينفعش يتقفل")
    with get_session() as s:
        if s.query(MonthClose.id).filter(MonthClose.year == year, MonthClose.month == month).first():
            blockers.append("الشهر مقفل بالفعل")
        py, pm = (year, month - 1) if month > 1 else (year - 1, 12)
        earlier = s.query(MonthClose.id).filter((MonthClose.year < year) | ((MonthClose.year == year) & (MonthClose.month < month))).count()
        if earlier and not s.query(MonthClose.id).filter(MonthClose.year == py, MonthClose.month == pm).first():
            blockers.append(f"اقفل شهر {pm}/{py} الأول (الإقفال بالترتيب)")
        n = s.query(PayrollRun).filter(PayrollRun.month == month, PayrollRun.year == year, PayrollRun.state == "draft").count()
        if n:
            blockers.append(f"فيه {n} دورة رواتب مسودة للشهر ده - رحّلها أو احذفها")
        n = s.query(JournalEntry).filter(JournalEntry.date >= t0, JournalEntry.date < t1, JournalEntry.posted.is_(False)).count()
        if n:
            blockers.append(f"فيه {n} قيد غير مرحّل في الشهر ده")
        if not s.query(PayrollRun.id).filter(PayrollRun.month == month, PayrollRun.year == year).first():
            warnings.append("مفيش دورة رواتب للشهر ده")
        if s.query(FiscalPeriod).filter(FiscalPeriod.is_closed.is_(True), FiscalPeriod.date_from <= t0, FiscalPeriod.date_to >= t0).first():
            blockers.append("الشهر داخل سنة مالية مقفلة")
    return {"blockers": blockers, "warnings": warnings}


def close_month(year, month, note=""):
    require_action("fiscal_periods", "close")
    year, month = int(year), int(month)
    if not 1 <= month <= 12:
        raise ValueError("شهر غير صحيح")
    chk = month_close_checks(year, month)
    if chk["blockers"]:
        raise ValueError("؛ ".join(chk["blockers"]))
    first, last = _month_bounds(month, year)
    inc = exp = 0.0
    for r in _account_balances_until(datetime.datetime(last.year, last.month, last.day, 23, 59, 59), datetime.datetime(first.year, first.month, first.day), ["income", "expense"]):
        bal = (r["debit"] or 0) - (r["credit"] or 0)
        if r["type"] == "income":
            inc += -bal
        else:
            exp += bal
    with get_session() as s:
        m = MonthClose(year=year, month=month, closed_by=_current_username(), income=round(inc, 2), expense=round(exp, 2), note=(note or "")[:300])
        s.add(m); s.commit()
        return m.id


def reopen_month(year, month):
    """بيفتح آخر شهر مقفل بس (عشان الترتيب يفضل سليم)."""
    require_action("fiscal_periods", "close")
    with get_session() as s:
        m = s.query(MonthClose).filter(MonthClose.year == int(year), MonthClose.month == int(month)).first()
        if not m:
            raise ValueError("الشهر ده مش مقفل")
        later = s.query(MonthClose.id).filter((MonthClose.year > m.year) | ((MonthClose.year == m.year) & (MonthClose.month > m.month))).first()
        if later:
            raise ValueError("افتح الشهور الأحدث الأول - بيتفتح آخر شهر مقفل بس")
        s.delete(m); s.commit()


def current_closed_period(date_value=None):
    d=_dt_start(date_value or datetime.datetime.now())
    with get_session() as s:
        return s.query(FiscalPeriod).filter(FiscalPeriod.is_closed.is_(True),FiscalPeriod.date_from<=d,FiscalPeriod.date_to>=d).first()



# ============================== Branches / Cost Centers / Users ==============================
def list_branches(active_only=True):
    with get_session() as s:
        q=s.query(Branch)
        if active_only: q=q.filter(Branch.is_active.is_(True))
        return q.order_by(Branch.code).all()

def create_branch(code,name,is_default=False):
    require_action("organization", "create")
    code=(code or '').strip(); name=(name or '').strip()
    if not code or not name: raise ValueError('كود واسم الفرع مطلوبان')
    with get_session() as s:
        if s.query(Branch).filter(Branch.code==code).first(): raise ValueError('كود الفرع مستخدم بالفعل')
        from . import trial as _trial
        _trial.check_limit("branches", s.query(Branch).filter(Branch.is_active.is_(True)).count(), "الفروع")
        if is_default: s.query(Branch).update({Branch.is_default:False})
        b=Branch(code=code,name=name,is_default=is_default); s.add(b); s.commit(); s.refresh(b); return b.id

def update_branch(branch_id, **fields):
    require_action("organization", "edit")
    with get_session() as s:
        b=s.get(Branch,int(branch_id));
        if not b: raise ValueError('الفرع غير موجود')
        if fields.get('is_active') and not b.is_active:
            from . import trial as _trial
            _trial.check_limit("branches", s.query(Branch).filter(Branch.is_active.is_(True)).count(), "الفروع")
        if fields.get('is_default'): s.query(Branch).update({Branch.is_default:False})
        for k,v in fields.items(): setattr(b,k,v)
        s.commit()

def delete_branch(branch_id):
    require_action("organization", "delete")
    with get_session() as s:
        b=s.get(Branch,int(branch_id));
        if not b:return
        if s.query(JournalEntry).filter(JournalEntry.branch_id==b.id).count() or s.query(JournalEntryLine).filter(JournalEntryLine.branch_id==b.id).count(): raise ValueError('لا يمكن حذف فرع عليه حركات')
        s.delete(b); s.commit()

def default_branch_id():
    allowed=user_branch_ids() if _get_user() else []
    with get_session() as s:
        if allowed:
            b=s.query(Branch).filter(Branch.id.in_(allowed),Branch.is_active.is_(True)).order_by(Branch.id).first()
            return b.id if b else None
        b=s.query(Branch).filter(Branch.is_default.is_(True),Branch.is_active.is_(True)).first() or s.query(Branch).filter(Branch.is_active.is_(True)).first()
        return b.id if b else None

def list_cost_centers(active_only=True):
    with get_session() as s:
        q=s.query(CostCenter)
        if active_only:q=q.filter(CostCenter.is_active.is_(True))
        return q.order_by(CostCenter.code).all()

def create_cost_center(code,name,parent_id=None,branch_id=None):
    require_action("organization", "create")
    code=(code or '').strip(); name=(name or '').strip()
    if not code or not name: raise ValueError('كود واسم مركز التكلفة مطلوبان')
    if branch_id and not allowed_branch(branch_id): raise PermissionError('الفرع غير مسموح لهذا المستخدم')
    with get_session() as s:
        if s.query(CostCenter).filter(CostCenter.code==code).first(): raise ValueError('كود مركز التكلفة مستخدم بالفعل')
        if parent_id:
            parent=s.get(CostCenter,int(parent_id))
            if not parent: raise ValueError('مركز التكلفة الأب غير موجود')
        x=CostCenter(code=code,name=name,parent_id=parent_id,branch_id=branch_id); s.add(x); s.commit(); s.refresh(x); return x.id

def update_cost_center(center_id, **fields):
    require_action("organization", "edit")
    with get_session() as s:
        x=s.get(CostCenter,int(center_id));
        if not x: raise ValueError('مركز التكلفة غير موجود')
        for k,v in fields.items(): setattr(x,k,v)
        s.commit()

def delete_cost_center(center_id):
    require_action("organization", "delete")
    with get_session() as s:
        x=s.get(CostCenter,int(center_id));
        if not x:return
        if s.query(JournalEntryLine).filter(JournalEntryLine.cost_center_id==x.id).count(): raise ValueError('لا يمكن حذف مركز تكلفة عليه حركات')
        s.delete(x); s.commit()

def _hash_password(password):
    """PBKDF2-SHA256 بملح عشوائي لكل مستخدم. الصيغة: pbkdf2$<iters>$<salt>$<hash>. (كلمات المرور القديمة SHA256 بتتقبل وبتتحدّث تلقائيًا عند أول دخول.)"""
    import hashlib, os
    iters = 200_000
    salt = os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), bytes.fromhex(salt), iters).hex()
    return f"pbkdf2${iters}${salt}${h}"


def _verify_password(password, stored):
    import hashlib, hmac
    stored = stored or ""
    if stored.startswith("pbkdf2$"):
        try:
            _, iters, salt, h = stored.split("$")
            calc = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), bytes.fromhex(salt), int(iters)).hex()
            return hmac.compare_digest(calc, h)
        except Exception:
            return False
    return hmac.compare_digest(hashlib.sha256((password or "").encode("utf-8")).hexdigest(), stored)


_LOGIN_FAILS = {}            # username -> [timestamps] (بالذاكرة؛ بيتصفّر مع إعادة تشغيل السيرفر)
LOGIN_MAX_FAILS = 5
LOGIN_WINDOW_SEC = 600


def login_locked(username):
    """ثواني متبقية على فك قفل المحاولات الخاطئة لاسم المستخدم ده (0 = مش مقفول)."""
    import time
    key = (username or "").strip().lower()
    now = time.time()
    fails = [t for t in _LOGIN_FAILS.get(key, []) if now - t < LOGIN_WINDOW_SEC]
    _LOGIN_FAILS[key] = fails
    if len(fails) >= LOGIN_MAX_FAILS:
        return int(LOGIN_WINDOW_SEC - (now - fails[0]))
    return 0


def is_default_admin_password():
    with get_session() as s:
        u = s.query(User).filter(User.username == "admin").first()
        return bool(u and _verify_password("admin", u.password_hash))


MIN_PASSWORD_LEN = 8


def check_password_policy(pw, username=""):
    """سياسة كلمة المرور للسيرفر: 8 حروف على الأقل، مش كلمة افتراضية معروفة ولا اسم المستخدم."""
    pw = pw or ""
    if len(pw) < MIN_PASSWORD_LEN:
        raise ValueError(f"كلمة المرور لازم تكون {MIN_PASSWORD_LEN} حروف على الأقل")
    if pw.lower() in ("admin", "password", "12345678", "123456789", "admin123", "qwertyui") or (username and pw.lower() == username.lower()):
        raise ValueError("كلمة المرور ضعيفة (معروفة أو نفس اسم المستخدم) - اختر غيرها")
    return True


def must_change_password(user):
    """هل لازم المستخدم يغيّر كلمة مروره قبل ما يكمّل؟ (مدير النظام بكلمة المرور الافتراضية admin)."""
    if not user:
        return False
    name = user.get("username") if isinstance(user, dict) else user.username
    return name == "admin" and is_default_admin_password()


def change_own_password(old_password, new_password):
    """تغيير كلمة مرور المستخدم الحالي (من غير صلاحية إدارة المستخدمين)، مع التحقق من القديمة والسياسة."""
    from . import audit
    u0 = _get_user()
    if not u0:
        raise PermissionError("سجّل الدخول أولًا")
    uid = u0.get("id") if isinstance(u0, dict) else u0.id
    with get_session() as s:
        u = s.get(User, int(uid))
        if not u or not _verify_password(old_password or "", u.password_hash):
            raise ValueError("كلمة المرور الحالية غير صحيحة")
        if old_password == new_password:
            raise ValueError("كلمة المرور الجديدة نفس القديمة")
        check_password_policy(new_password, u.username)
        u.password_hash = _hash_password(new_password)
        s.commit()
    try:
        audit.log_event("update", label="تغيير كلمة المرور", changes=u0.get("username") if isinstance(u0, dict) else u0.username)
    except Exception:
        pass
    return True


def bootstrap_admin(env_password=None, generated_path=None):
    """للسيرفر: لو حساب admin لسه بكلمة المرور الافتراضية، بيتحط له كلمة مرور من ERP_ADMIN_PASSWORD، وإلا كلمة عشوائية
    بتتكتب في ملف (صلاحيات 600) وبتتطبع في السجل - عشان ما يبقاش فيه فترة السيرفر مكشوف بـ admin/admin.
    بيرجّع ("env"|"generated"|None, كلمة المرور لو generated)."""
    import os
    import secrets
    if not is_default_admin_password():
        return None, None
    if env_password:
        check_password_policy(env_password, "admin")
        pw, how = env_password, "env"
    else:
        pw, how = secrets.token_urlsafe(12), "generated"
    with get_session() as s:
        u = s.query(User).filter(User.username == "admin").first()
        u.password_hash = _hash_password(pw)
        s.commit()
    if how == "generated" and generated_path:
        fd = os.open(generated_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"admin / {pw}\nاحذف الملف بعد حفظ كلمة المرور وتغييرها.\n")
    return how, (pw if how == "generated" else None)


def authenticate_user(username,password,otp=None,second_factor=True):
    """بيرجّع بيانات المستخدم أو None. بعد 5 محاولات خاطئة لنفس الاسم في 10 دقايق بيترفض الدخول مؤقتًا (ValueError فيه المدة)."""
    import time
    from . import audit
    key = (username or "").strip().lower()
    from . import trial as _trial
    if _trial.is_expired():
        raise ValueError(_trial.EXPIRED_MSG)
    wait = login_locked(username)
    if wait:
        raise ValueError(f"محاولات دخول خاطئة كتير - حاول بعد {max(1, wait // 60 + (1 if wait % 60 else 0))} دقيقة")
    with get_session() as s:
        u=s.query(User).filter(User.username==(username or '').strip(),User.is_active.is_(True)).first()
        if not u or not _verify_password(password, u.password_hash):
            _LOGIN_FAILS.setdefault(key, []).append(time.time())
            try: audit.log_event("login_failed", label=(username or '').strip()[:100], username=(username or '').strip()[:100])
            except Exception: pass
            return None
        from . import twofa as _tf
        if second_factor and u.totp_enabled:
            if not (otp or "").strip():
                raise _tf.OtpRequired()
            if not _tf.verify_login(u, otp):
                _LOGIN_FAILS.setdefault(key, []).append(time.time())
                try: audit.log_event("login_failed", label=(u.username + " (2FA)")[:100], username=u.username)
                except Exception: pass
                s.rollback()
                raise ValueError("رمز التحقق غير صحيح")
            s.commit()
        _LOGIN_FAILS.pop(key, None)
        if not (u.password_hash or "").startswith("pbkdf2$"):
            u.password_hash = _hash_password(password); s.commit()      # ترقية تلقائية للتشفير الجديد
        try:
            from . import monitor as _mon
            _mon.mark_login(u.username)
        except Exception: pass
        try: audit.log_event("login", label=u.username, username=u.username)
        except Exception: pass
        return {'id':u.id,'username':u.username,'full_name':u.full_name,'role':u.role,'permissions':u.permissions or '{}','branch_ids':u.branch_ids or '[]','cost_center_ids':getattr(u,'cost_center_ids','[]') or '[]',
                'needs_2fa_setup': bool(not u.totp_enabled and _tf.required_for(u.role, u.username))}

def list_users():
    with get_session() as s:return s.query(User).order_by(User.username).all()

def create_user(username,password,full_name,role='user',permissions=None,branch_ids=None,cost_center_ids=None):
    require_action("organization", "create")
    import json
    username=(username or '').strip()
    if not username or not password or not full_name: raise ValueError('اسم المستخدم وكلمة المرور والاسم مطلوبون')
    with get_session() as s:
        if s.query(User).filter(User.username==username).first(): raise ValueError('اسم المستخدم مستخدم بالفعل')
        from . import trial as _trial
        _trial.check_limit("users", s.query(User).filter(User.is_active.is_(True)).count(), "المستخدمين")
        if not permissions:
            from . import field_access as _fa
            permissions = _fa.with_hidden(ROLE_DEFAULT_PERMISSIONS.get(role, {}), _fa.ROLE_DEFAULT_HIDDEN.get(role, []))
        u=User(username=username,password_hash=_hash_password(password),full_name=full_name.strip(),role=role,permissions=json.dumps(permissions,ensure_ascii=False), branch_ids=json.dumps(branch_ids or [],ensure_ascii=False), cost_center_ids=json.dumps(cost_center_ids or [],ensure_ascii=False))
        s.add(u);s.commit();s.refresh(u);return u.id

def update_user(user_id, password=None, **fields):
    require_action("organization", "edit")
    with get_session() as s:
        u=s.get(User,int(user_id));
        if not u:raise ValueError('المستخدم غير موجود')
        if fields.get("is_active") and not u.is_active:
            from . import trial as _trial
            _trial.check_limit("users", s.query(User).filter(User.is_active.is_(True)).count(), "المستخدمين")
        if password is not None and password!='':u.password_hash=_hash_password(password)
        for k,v in fields.items(): setattr(u,k,v)
        s.commit()

def delete_user(user_id):
    require_action("organization", "delete")
    with get_session() as s:
        u=s.get(User,int(user_id));
        if u and u.username!='admin':s.delete(u);s.commit()

def user_has_permission(user, permission):
    if not user: return False
    return user_has_action(user, permission, "view")


def branch_dashboard(branch_id, date_from=None, date_to=None):
    """مؤشرات مالية وتشغيلية لفرع واحد."""
    if branch_id is None: return {'branch_id':None,'revenue':0,'expense':0,'profit':0,'assets':0,'liabilities':0,'equity':0,'sales_total':0,'purchase_total':0}
    if not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    df,dt=_dt_start(date_from),_dt_end(date_to)
    with get_session() as s:
        q=s.query(JournalEntryLine).join(JournalEntry).filter(JournalEntryLine.branch_id==int(branch_id))
        if df:q=q.filter(JournalEntry.date>=df)
        if dt:q=q.filter(JournalEntry.date<=dt)
        lines=q.all()
        rev=sum(float(x.credit or 0)-float(x.debit or 0) for x in lines if x.account.account_type=='income')
        exp=sum(float(x.debit or 0)-float(x.credit or 0) for x in lines if x.account.account_type=='expense')
        assets=sum(float(x.debit or 0)-float(x.credit or 0) for x in lines if x.account.account_type=='asset')
        liabilities=sum(float(x.credit or 0)-float(x.debit or 0) for x in lines if x.account.account_type=='liability')
        equity=sum(float(x.credit or 0)-float(x.debit or 0) for x in lines if x.account.account_type=='equity')
        sales=s.query(SalesInvoice).filter(SalesInvoice.branch_id==int(branch_id))
        purchases=s.query(PurchaseInvoice).filter(PurchaseInvoice.branch_id==int(branch_id))
        if df:sales=sales.filter(SalesInvoice.date>=df);purchases=purchases.filter(PurchaseInvoice.date>=df)
        if dt:sales=sales.filter(SalesInvoice.date<=dt);purchases=purchases.filter(PurchaseInvoice.date<=dt)
        return {'branch_id':int(branch_id),'revenue':rev,'expense':exp,'profit':rev-exp,'assets':assets,'liabilities':liabilities,'equity':equity,'sales_total':sum(float(x.total or 0) for x in sales.all()),'purchase_total':sum(float(x.total or 0) for x in purchases.all())}

def branch_comparison(date_from=None,date_to=None):
    ids=user_branch_ids()
    branches=list_branches(True)
    if ids: branches=[b for b in branches if b.id in ids]
    return [{'branch':b.name,'code':b.code,**branch_dashboard(b.id,date_from,date_to)} for b in branches]


def _period_totals(start,end,types):
    rows=_account_balances_until(end,start,types)
    return {r['id']:r for r in rows}

def comparative_income_statement(period1_from,period1_to,period2_from,period2_to):
    a=detailed_income_statement(period1_from,period1_to); b=detailed_income_statement(period2_from,period2_to)
    amap={r['code']:r for r in a['income']+a['expense']}; bmap={r['code']:r for r in b['income']+b['expense']}; codes=sorted(set(amap)|set(bmap))
    rows=[]
    for code in codes:
        r=amap.get(code) or bmap.get(code); v1=amap.get(code,{}).get('amount',0); v2=bmap.get(code,{}).get('amount',0)
        rows.append({'code':code,'name':r['name'],'period1':round(v1,2),'period2':round(v2,2),'difference':round(v2-v1,2),'change_pct':round(((v2-v1)/v1*100) if v1 else 0,2)})
    return {'rows':rows,'period1':a,'period2':b}

def comparative_balance_sheet(asof1,asof2):
    a=detailed_balance_sheet(asof1); b=detailed_balance_sheet(asof2)
    amap={r['code']:r for k in ('assets','liabilities','equity') for r in a[k]}; bmap={r['code']:r for k in ('assets','liabilities','equity') for r in b[k]}; codes=sorted(set(amap)|set(bmap)); rows=[]
    for code in codes:
        r=amap.get(code) or bmap.get(code); v1=amap.get(code,{}).get('amount',0);v2=bmap.get(code,{}).get('amount',0)
        rows.append({'code':code,'name':r['name'],'type':r['type'],'period1':round(v1,2),'period2':round(v2,2),'difference':round(v2-v1,2)})
    return {'rows':rows,'period1':a,'period2':b}

def statement_of_changes_in_equity(date_from=None,date_to=None):
    rows=_account_balances_until(date_to,date_from,['equity']); details=[dict(r,amount=round(r['credit']-r['debit'],2)) for r in rows if abs(r['credit']-r['debit'])>.005]
    opening_rows=_account_balances_until(_dt_end(date_from)-datetime.timedelta(seconds=1) if date_from else None,None,['equity']) if date_from else []
    opening=sum(r['credit']-r['debit'] for r in opening_rows)
    movements=sum(r['amount'] for r in details)
    inc=detailed_income_statement(date_from,date_to); _cfg=get_accounting_settings(); retained=next((r['amount'] for r in details if r['id']==(_cfg.retained_earnings_account_id if _cfg else None) or r['code'] in ('340000','3200')),0)
    return {'opening_equity':round(opening,2),'movements':details,'net_profit':inc['net_profit'],'closing_equity':round(opening+movements+inc['net_profit'],2),'date_from':_dt_start(date_from),'date_to':_dt_end(date_to)}

def branch_cost_report(date_from=None,date_to=None,branch_id=None,cost_center_id=None):
    df,dt=_dt_start(date_from),_dt_end(date_to)
    with get_session() as s:
        q=s.query(JournalEntryLine).join(JournalEntry).options(joinedload(JournalEntryLine.account)).order_by(JournalEntry.date,JournalEntry.id)
        if df:q=q.filter(JournalEntry.date>=df)
        if dt:q=q.filter(JournalEntry.date<=dt)
        if branch_id:q=q.filter(JournalEntryLine.branch_id==int(branch_id))
        if cost_center_id:q=q.filter(JournalEntryLine.cost_center_id==int(cost_center_id))
        rows=q.all(); out=[]
        for x in rows:
            out.append({'date':x.entry.date,'code':x.account.code,'account':x.account.name,'debit':float(x.debit or 0),'credit':float(x.credit or 0),'branch_id':x.branch_id,'cost_center_id':x.cost_center_id})
        return out

# ============================== Enterprise Financial Statements / Consolidation ==============================
def _visible_branch_filter(query, column):
    ids = user_branch_ids()
    return query.filter(column.in_(ids)) if ids else query


def _rolled_account_rows(date_from=None, date_to=None, account_types=None, branch_id=None, cost_center_id=None):
    """حسابات تفصيلية مع تجميع أرصدة الحسابات الأب تلقائياً."""
    df, dt = _dt_start(date_from), _dt_end(date_to)
    if branch_id and not allowed_branch(branch_id):
        raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    with get_session() as s:
        accounts = s.query(Account).filter(Account.is_active.is_(True)).order_by(Account.code).all()
        q = s.query(JournalEntryLine).join(JournalEntry).filter(JournalEntry.posted.is_(True))
        if df: q = q.filter(JournalEntry.date >= df)
        if dt: q = q.filter(JournalEntry.date <= dt)
        if account_types: q = q.filter(JournalEntryLine.account_id.in_(s.query(Account.id).filter(Account.account_type.in_(account_types))))
        if branch_id: q = q.filter(JournalEntryLine.branch_id == int(branch_id))
        elif user_branch_ids(): q = q.filter(((JournalEntryLine.branch_id.is_(None))|(JournalEntryLine.branch_id.in_(user_branch_ids()))))
        if cost_center_id: q = q.filter(JournalEntryLine.cost_center_id == int(cost_center_id))
        totals = {}
        for line in q.all():
            d, c = float(line.debit or 0), float(line.credit or 0)
            x = totals.setdefault(line.account_id, [0.0, 0.0]); x[0] += d; x[1] += c
        by_id = {a.id:a for a in accounts}
        # Roll up child accounts bottom-up. كل مستوى يمرر رصيده مرة واحدة للأب لمنع تكرار الأرصدة.
        depth_cache={}
        def depth(aid):
            if aid in depth_cache:return depth_cache[aid]
            n=0; seen=set(); p=by_id.get(aid)
            while p and p.parent_id and p.parent_id not in seen:
                seen.add(p.id); n+=1; p=by_id.get(p.parent_id)
            depth_cache[aid]=n; return n
        for a in sorted(accounts, key=lambda x: (depth(x.id), x.code), reverse=True):
            if a.parent_id:
                child=totals.get(a.id,[0.0,0.0]); x=totals.setdefault(a.parent_id,[0.0,0.0]); x[0]+=child[0]; x[1]+=child[1]
        out=[]
        for a in accounts:
            d,c=totals.get(a.id,[0.0,0.0]);
            if abs(d)+abs(c) <= 0.005: continue
            out.append({'id':a.id,'code':a.code,'name':a.name,'type':a.account_type,'parent_id':a.parent_id,
                        'debit':round(d,2),'credit':round(c,2),'balance':round(d-c,2),
                        'amount':round((d-c) if a.account_type=='asset' else (c-d),2)})
        return out


def account_tree_report(account_type=None, date_to=None, branch_id=None, cost_center_id=None):
    rows=_rolled_account_rows(None,date_to,[account_type] if account_type else None,branch_id,cost_center_id)
    with get_session() as s:
        accounts=s.query(Account).filter(Account.is_active.is_(True)).order_by(Account.code).all()
    by_id={a.id:a for a in accounts}; levels={}
    def level(a):
        if a.id in levels:return levels[a.id]
        n=0;p=a.parent_id
        while p and p in by_id:
            n+=1;p=by_id[p].parent_id
        levels[a.id]=n;return n
    for r in rows:
        r['level']=level(by_id[r['id']]); r['display_name']=('    '*r['level']) + ('└─ ' if r['level'] else '') + r['name']
    return rows


def branch_income_statement(branch_id, date_from=None, date_to=None, cost_center_id=None):
    return detailed_income_statement(date_from,date_to,branch_id,cost_center_id)


def branch_balance_sheet(branch_id, as_of=None, cost_center_id=None):
    return detailed_balance_sheet(as_of,branch_id,cost_center_id)


def consolidated_income_statement(date_from=None, date_to=None, branch_id=None, cost_center_id=None):
    """قائمة دخل موحدة: كل الفروع المسموح بها، أو فرع محدد."""
    return detailed_income_statement(date_from,date_to,branch_id,cost_center_id)


def consolidated_balance_sheet(as_of=None, branch_id=None, cost_center_id=None):
    return detailed_balance_sheet(as_of,branch_id,cost_center_id)


def cost_center_statement(date_from=None, date_to=None, branch_id=None):
    if branch_id and not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    centers=list_cost_centers(True)
    if branch_id: centers=[c for c in centers if not c.branch_id or c.branch_id==int(branch_id)]
    elif user_branch_ids(): centers=[c for c in centers if not c.branch_id or c.branch_id in user_branch_ids()]
    out=[]
    for c in centers:
        inc=detailed_income_statement(date_from,date_to,branch_id,c.id)
        out.append({'id':c.id,'code':c.code,'name':c.name,'branch_id':c.branch_id,'income':inc['total_income'],'expense':inc['total_expense'],'profit':inc['net_profit']})
    return out


# ============================== Budgeting & Management KPIs ==============================
def _check_scope(branch_id=None, cost_center_id=None):
    if branch_id and not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    if cost_center_id and not allowed_cost_center(cost_center_id): raise PermissionError("مركز التكلفة غير مسموح لهذا المستخدم")

def list_budget_lines(date_from=None,date_to=None,branch_id=None,cost_center_id=None,account_id=None):
    _check_scope(branch_id,cost_center_id)
    with get_session() as s:
        q=s.query(BudgetLine).options(joinedload(BudgetLine.account),joinedload(BudgetLine.branch),joinedload(BudgetLine.cost_center)).filter(BudgetLine.is_active.is_(True))
        if date_from:q=q.filter(BudgetLine.date_to>=_dt_start(date_from))
        if date_to:q=q.filter(BudgetLine.date_from<=_dt_end(date_to))
        if branch_id:q=q.filter(BudgetLine.branch_id==int(branch_id))
        elif user_branch_ids():q=q.filter((BudgetLine.branch_id.is_(None)) | BudgetLine.branch_id.in_(user_branch_ids()))
        if cost_center_id:q=q.filter(BudgetLine.cost_center_id==int(cost_center_id))
        elif user_cost_center_ids():q=q.filter((BudgetLine.cost_center_id.is_(None)) | BudgetLine.cost_center_id.in_(user_cost_center_ids()))
        if account_id:q=q.filter(BudgetLine.account_id==int(account_id))
        return q.order_by(BudgetLine.date_from,BudgetLine.id).all()

def create_budget_line(name,date_from,date_to,account_id,budget_amount,branch_id=None,cost_center_id=None,notes=""):
    require_action("budgets","create"); _check_scope(branch_id,cost_center_id)
    if _dt_start(date_from)>_dt_end(date_to): raise ValueError("تاريخ بداية الموازنة يجب أن يسبق تاريخ النهاية")
    with get_session() as s:
        if not s.get(Account,int(account_id)): raise ValueError("الحساب غير موجود")
        b=BudgetLine(name=name or "موازنة",date_from=_dt_start(date_from),date_to=_dt_end(date_to),account_id=int(account_id),budget_amount=float(budget_amount or 0),branch_id=branch_id,cost_center_id=cost_center_id,notes=notes or "")
        s.add(b);s.commit();s.refresh(b);return b.id

def update_budget_line(line_id,**fields):
    require_action("budgets","edit")
    with get_session() as s:
        b=s.get(BudgetLine,int(line_id));
        if not b: raise ValueError("بند الموازنة غير موجود")
        _check_scope(fields.get("branch_id",b.branch_id),fields.get("cost_center_id",b.cost_center_id))
        for k,v in fields.items():
            if k in ("date_from","date_to") and v: v=_dt_start(v) if k=="date_from" else _dt_end(v)
            setattr(b,k,v)
        s.commit()

def delete_budget_line(line_id):
    require_action("budgets","delete")
    with get_session() as s:
        b=s.get(BudgetLine,int(line_id));
        if b: _check_scope(b.branch_id,b.cost_center_id); s.delete(b);s.commit()

def budget_vs_actual(date_from=None,date_to=None,branch_id=None,cost_center_id=None):
    _check_scope(branch_id,cost_center_id); df,dt=_dt_start(date_from),_dt_end(date_to)
    budgets=list_budget_lines(date_from,date_to,branch_id,cost_center_id)
    budget_by={}
    for b in budgets:
        k=(b.account_id,b.branch_id,b.cost_center_id);budget_by[k]=budget_by.get(k,0)+float(b.budget_amount or 0)
    with get_session() as s:
        q=s.query(JournalEntryLine).join(JournalEntry).filter(JournalEntry.posted.is_(True))
        if df:q=q.filter(JournalEntry.date>=df)
        if dt:q=q.filter(JournalEntry.date<=dt)
        if branch_id:q=q.filter(JournalEntryLine.branch_id==int(branch_id))
        elif user_branch_ids():q=q.filter(((JournalEntryLine.branch_id.is_(None))|(JournalEntryLine.branch_id.in_(user_branch_ids()))))
        if cost_center_id:q=q.filter(JournalEntryLine.cost_center_id==int(cost_center_id))
        elif user_cost_center_ids():q=q.filter(((JournalEntryLine.cost_center_id.is_(None))|(JournalEntryLine.cost_center_id.in_(user_cost_center_ids()))))
        # تجميع في قاعدة البيانات بدل تحميل كل سطر قيد كـ ORM (أسرع بكتير على الداتا الكبيرة) - نفس النتيجة
        agg=(s.query(JournalEntryLine.account_id,JournalEntryLine.branch_id,JournalEntryLine.cost_center_id,Account.account_type,
                     func.coalesce(func.sum(JournalEntryLine.credit),0),func.coalesce(func.sum(JournalEntryLine.debit),0))
             .select_from(JournalEntryLine).join(JournalEntry,JournalEntry.id==JournalEntryLine.entry_id).join(Account,Account.id==JournalEntryLine.account_id)
             .filter(JournalEntry.posted.is_(True),Account.account_type.in_(("income","expense"))))
        if df:agg=agg.filter(JournalEntry.date>=df)
        if dt:agg=agg.filter(JournalEntry.date<=dt)
        if branch_id:agg=agg.filter(JournalEntryLine.branch_id==int(branch_id))
        elif user_branch_ids():agg=agg.filter(((JournalEntryLine.branch_id.is_(None))|(JournalEntryLine.branch_id.in_(user_branch_ids()))))
        if cost_center_id:agg=agg.filter(JournalEntryLine.cost_center_id==int(cost_center_id))
        elif user_cost_center_ids():agg=agg.filter(((JournalEntryLine.cost_center_id.is_(None))|(JournalEntryLine.cost_center_id.in_(user_cost_center_ids()))))
        actual={}
        for aid,bid,ccid,atype,cr,dr in agg.group_by(JournalEntryLine.account_id,JournalEntryLine.branch_id,JournalEntryLine.cost_center_id,Account.account_type).all():
            amt=(float(cr or 0)-float(dr or 0)) if atype=="income" else (float(dr or 0)-float(cr or 0))
            k=(aid,bid,ccid);actual[k]=actual.get(k,0)+amt
        keys=set(budget_by)|set(actual); out=[]
        with get_session() as s2:
            amap={a.id:a for a in s2.query(Account).all()};
        for k in keys:
            aid,bid,ccid=k; bd=budget_by.get(k,0); ac=actual.get(k,0); variance=ac-bd
            a=amap.get(aid);
            out.append({'account_id':aid,'code':a.code if a else '', 'account':a.name if a else '', 'type':a.account_type if a else '', 'branch_id':bid,'cost_center_id':ccid,'budget':round(bd,2),'actual':round(ac,2),'variance':round(variance,2),'achievement_pct':round((ac/bd*100) if bd else 0,2)})
        return sorted(out,key=lambda x:(x['type'],x['code']))

def management_kpis(date_from=None,date_to=None,branch_id=None,cost_center_id=None):
    _check_scope(branch_id,cost_center_id)
    inc=detailed_income_statement(date_from,date_to,branch_id,cost_center_id)
    revenue=float(inc['total_income'] or 0); expense=float(inc['total_expense'] or 0); profit=float(inc['net_profit'] or 0)
    gross=0.0
    for r in inc.get('expense',[]):
        if str(r.get('code','')).startswith('51'): gross += float(r.get('amount',0) or 0)
    gross_profit=revenue-gross
    return {'revenue':revenue,'expense':expense,'profit':profit,'gross_profit':gross_profit,'net_margin_pct':(profit/revenue*100 if revenue else 0),'gross_margin_pct':(gross_profit/revenue*100 if revenue else 0),'expense_ratio_pct':(expense/revenue*100 if revenue else 0),'budget_vs_actual':budget_vs_actual(date_from,date_to,branch_id,cost_center_id)}

def branch_budget_summary(date_from=None,date_to=None):
    ids=user_branch_ids(); branches=list_branches(True);
    if ids:branches=[b for b in branches if b.id in ids]
    out=[]
    for b in branches:
        k=management_kpis(date_from,date_to,b.id,None); bv=k['budget_vs_actual']; budget=sum(x['budget'] for x in bv); actual=sum(x['actual'] for x in bv);
        out.append({'branch_id':b.id,'branch':b.name,'revenue':k['revenue'],'expense':k['expense'],'profit':k['profit'],'budget':budget,'actual':actual,'variance':actual-budget})
    return out


def executive_customer_detail(customer_id,date_from=None,date_to=None,branch_id=None,cost_center_id=None):
    _check_scope(branch_id,cost_center_id); df,dt=_dt_start(date_from),_dt_end(date_to)
    with get_session() as s:
        q=_scope_invoice_query(s.query(SalesInvoice),SalesInvoice,branch_id,cost_center_id).filter(SalesInvoice.customer_id==int(customer_id))
        if df:q=q.filter(SalesInvoice.date>=df)
        if dt:q=q.filter(SalesInvoice.date<=dt)
        return [{'number':x.number,'date':x.date.strftime('%Y-%m-%d'),'subtotal':round(float(x.subtotal or 0),2),'tax':round(float(x.tax_total or 0),2),'total':round(float(x.total or 0),2)} for x in q.order_by(SalesInvoice.date.desc()).all()]


def executive_product_detail(product_id,date_from=None,date_to=None,branch_id=None,cost_center_id=None):
    _check_scope(branch_id,cost_center_id); df,dt=_dt_start(date_from),_dt_end(date_to)
    with get_session() as s:
        q=_scope_invoice_query(s.query(SalesInvoice).options(joinedload(SalesInvoice.customer),joinedload(SalesInvoice.items).joinedload(SalesInvoiceItem.product)),SalesInvoice,branch_id,cost_center_id)
        if df:q=q.filter(SalesInvoice.date>=df)
        if dt:q=q.filter(SalesInvoice.date<=dt)
        out=[]
        for inv in q.order_by(SalesInvoice.date.desc()).all():
            for item in inv.items:
                if item.product_id==int(product_id):
                    out.append({'number':inv.number,'date':inv.date.strftime('%Y-%m-%d'),'customer':inv.customer.name if inv.customer else 'عميل نقدي / غير محدد','qty':float(item.quantity or 0),'unit_price':float(item.unit_price or 0),'total':float(item.line_total or 0)})
        return out


# ======================================================================
# الموارد البشرية: الموظفون، العقود، الرواتب
# ======================================================================

def _next_code(session, model, prefix, width=5):
    _db_lock(session)
    last = session.query(model).order_by(model.id.desc()).first()
    return f"{prefix}{((last.id + 1) if last else 1):0{width}d}"


# ---------------------------- الموظفون ----------------------------
def list_employees(active_only=True, search=None):
    with get_session() as s:
        q = s.query(Employee).options(joinedload(Employee.cost_center), joinedload(Employee.branch))
        if active_only:
            q = q.filter(Employee.is_active.is_(True))
        if search:
            like = f"%{search.strip()}%"
            q = q.filter((Employee.name.like(like)) | (Employee.code.like(like)))
        employees = q.order_by(Employee.code).all()
        s.expunge_all()
        return employees


def get_employee(employee_id):
    with get_session() as s:
        return s.get(Employee, employee_id)


def create_employee(name, national_id="", phone="", email="", position="", department="",
                     hire_date=None, bank_account="", branch_id=None, cost_center_id=None):
    require_action("employees", "create")
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم الموظف مطلوب")
    branch_id = branch_id or default_branch_id()
    with get_session() as s:
        code = _next_code(s, Employee, "EMP-")
        dept_text = department
        if cost_center_id and not dept_text:
            cc = s.get(CostCenter, int(cost_center_id))
            dept_text = cc.name if cc else department
        e = Employee(
            code=code, name=name, national_id=national_id, phone=phone, email=email,
            position=position, department=dept_text, hire_date=hire_date or datetime.datetime.now(),
            bank_account=bank_account, branch_id=branch_id, cost_center_id=int(cost_center_id) if cost_center_id else None, is_active=True,
        )
        s.add(e); s.commit(); s.refresh(e)
        return e.id


def update_employee(employee_id, **fields):
    require_action("employees", "edit")
    with get_session() as s:
        e = s.get(Employee, employee_id)
        if not e:
            raise ValueError("الموظف غير موجود")
        for k, v in fields.items():
            setattr(e, k, v)
        s.commit()


def deactivate_employee(employee_id):
    require_action("employees", "delete")
    update_employee(employee_id, is_active=False)


# ---------------------------- العقود ----------------------------
def list_contracts(employee_id=None):
    with get_session() as s:
        q = s.query(Contract).options(
            joinedload(Contract.employee), joinedload(Contract.basic_salary_account),
            joinedload(Contract.housing_allowance_account), joinedload(Contract.transport_allowance_account),
            joinedload(Contract.other_allowances_account), joinedload(Contract.gosi_deduction_account),
            joinedload(Contract.other_deductions_account),
        )
        if employee_id:
            q = q.filter(Contract.employee_id == employee_id)
        contracts = q.order_by(Contract.start_date.desc()).all()
        s.expunge_all()
        return contracts


def get_contract(contract_id):
    with get_session() as s:
        c = s.query(Contract).options(
            joinedload(Contract.employee), joinedload(Contract.basic_salary_account),
            joinedload(Contract.housing_allowance_account), joinedload(Contract.transport_allowance_account),
            joinedload(Contract.other_allowances_account), joinedload(Contract.gosi_deduction_account),
            joinedload(Contract.other_deductions_account),
        ).filter(Contract.id == contract_id).first()
        if c:
            s.expunge_all()
        return c


def _contract_state_filter():
    """العقود المعتد بيها في الرواتب والمخصصات: النشطة، والمجدَّدة (فترتها
    السابقة لسه صالحة لدورات رواتب قديمة)، والمنتهية/المفسوخة اللي ليها
    تاريخ نهاية محدد (عشان آخر شهر قبل الإنهاء يتحسب صح)."""
    from sqlalchemy import or_, and_
    return or_(Contract.state.in_(("active", "renewed")),
               and_(Contract.state.in_(("terminated", "expired")), Contract.end_date.isnot(None)))


def get_active_contract(employee_id, as_of=None):
    as_of = as_of or datetime.datetime.now()
    with get_session() as s:
        q = s.query(Contract).filter(
            Contract.employee_id == employee_id, _contract_state_filter(),
            Contract.start_date <= as_of,
        ).filter((Contract.end_date.is_(None)) | (Contract.end_date >= as_of))
        return q.order_by(Contract.start_date.desc()).first()


def create_contract(employee_id, start_date, basic_salary, housing_allowance=0.0,
                     transport_allowance=0.0, other_allowances=0.0, contract_type="permanent",
                     end_date=None, gosi_rate_employee=9.75, gosi_rate_employer=11.75,
                     leave_provision_rate=8.33, eos_provision_rate=8.33,
                     basic_salary_account_id=None, housing_allowance_account_id=None,
                     transport_allowance_account_id=None, other_allowances_account_id=None,
                     gosi_deduction_account_id=None, other_deductions_account_id=None,
                     gosi_employer_expense_account_id=None, gosi_employer_payable_account_id=None,
                     leave_provision_expense_account_id=None, leave_provision_payable_account_id=None,
                     eos_provision_expense_account_id=None, eos_provision_payable_account_id=None,
                     renewed_from_id=None, previous_gross_salary=None, raise_amount=0.0, raise_note=""):
    require_action("contracts", "create")
    if not employee_id:
        raise ValueError("اختر الموظف")
    basic_salary = float(basic_salary or 0)
    housing_allowance = float(housing_allowance or 0)
    transport_allowance = float(transport_allowance or 0)
    other_allowances = float(other_allowances or 0)
    gosi_rate_employer = float(gosi_rate_employer or 0)
    leave_provision_rate = float(leave_provision_rate or 0)
    eos_provision_rate = float(eos_provision_rate or 0)
    if basic_salary <= 0:
        raise ValueError("الراتب الأساسي يجب أن يكون أكبر من صفر")

    # كل عنصر قيمته أكبر من صفر لازم يكون له حساب مدين وحساب دائن محددين -
    # وكمان حسابات الخصومات (تأمينات وخصومات أخرى) إجبارية دايماً لأي عقد
    required = [("الراتب الأساسي", basic_salary_account_id, True)]
    required.append(("بدل السكن", housing_allowance_account_id, housing_allowance > 0))
    required.append(("بدل النقل", transport_allowance_account_id, transport_allowance > 0))
    required.append(("بدلات أخرى", other_allowances_account_id, other_allowances > 0))
    required.append(("خصم التأمينات الاجتماعية", gosi_deduction_account_id, True))
    required.append(("الخصومات الأخرى", other_deductions_account_id, True))
    required.append(("تأمينات صاحب العمل - مدين (مصروف)", gosi_employer_expense_account_id, gosi_rate_employer > 0))
    required.append(("تأمينات صاحب العمل - دائن (مستحق)", gosi_employer_payable_account_id, gosi_rate_employer > 0))
    required.append(("مخصص الإجازة - مدين (مصروف)", leave_provision_expense_account_id, leave_provision_rate > 0))
    required.append(("مخصص الإجازة - دائن (مستحق)", leave_provision_payable_account_id, leave_provision_rate > 0))
    required.append(("مخصص نهاية الخدمة - مدين (مصروف)", eos_provision_expense_account_id, eos_provision_rate > 0))
    required.append(("مخصص نهاية الخدمة - دائن (مستحق)", eos_provision_payable_account_id, eos_provision_rate > 0))

    for label, aid, mandatory in required:
        if mandatory and not aid:
            raise ValueError(f'لازم تحدد حساب "{label}" من شجرة الحسابات')

    with get_session() as s:
        parent_ids = {a.parent_id for a in s.query(Account).all() if a.parent_id}
        for label, aid, mandatory in required:
            if aid and int(aid) in parent_ids:
                acc = s.get(Account, int(aid))
                raise ValueError(f'حساب "{label}" لازم يكون حساب فرعي - "{acc.code} - {acc.name}" حساب رئيسي مينفعش تترحّل عليه حركات مباشرة')

        # أي عقد نشط سابق لنفس الموظف يتحول لمنتهي تلقائياً عند إضافة عقد جديد
        s.query(Contract).filter(Contract.employee_id == employee_id, Contract.state == "active").update({"state": "expired"})
        renewal_count = 0
        if renewed_from_id:
            prev = s.get(Contract, int(renewed_from_id))
            if prev:
                # العقد السابق يتقفل كـ"مجدَّد" وتاريخ نهايته يتظبط ليوم قبل بداية العقد الجديد
                # بالظبط عشان مفيش تداخل ولا فجوة، وكل بياناته (الرواتب والحسابات) تفضل زي ما هي.
                prev.state = "renewed"
                day_before = start_date - datetime.timedelta(days=1)
                if prev.end_date is None or prev.end_date > day_before:
                    prev.end_date = day_before
                renewal_count = (prev.renewal_count or 0) + 1
        number = _next_code(s, Contract, "CON-")
        c = Contract(
            renewed_from_id=int(renewed_from_id) if renewed_from_id else None, renewal_count=renewal_count,
            previous_gross_salary=previous_gross_salary, raise_amount=round(float(raise_amount or 0), 2), raise_note=raise_note or "",
            employee_id=employee_id, contract_number=number, contract_type=contract_type,
            start_date=start_date, end_date=end_date, basic_salary=basic_salary,
            housing_allowance=housing_allowance, transport_allowance=transport_allowance,
            other_allowances=other_allowances, gosi_rate_employee=float(gosi_rate_employee or 0),
            gosi_rate_employer=gosi_rate_employer, leave_provision_rate=leave_provision_rate, eos_provision_rate=eos_provision_rate,
            state="active",
            basic_salary_account_id=int(basic_salary_account_id),
            housing_allowance_account_id=int(housing_allowance_account_id) if housing_allowance_account_id else None,
            transport_allowance_account_id=int(transport_allowance_account_id) if transport_allowance_account_id else None,
            other_allowances_account_id=int(other_allowances_account_id) if other_allowances_account_id else None,
            gosi_deduction_account_id=int(gosi_deduction_account_id),
            other_deductions_account_id=int(other_deductions_account_id),
            gosi_employer_expense_account_id=int(gosi_employer_expense_account_id) if gosi_employer_expense_account_id else None,
            gosi_employer_payable_account_id=int(gosi_employer_payable_account_id) if gosi_employer_payable_account_id else None,
            leave_provision_expense_account_id=int(leave_provision_expense_account_id) if leave_provision_expense_account_id else None,
            leave_provision_payable_account_id=int(leave_provision_payable_account_id) if leave_provision_payable_account_id else None,
            eos_provision_expense_account_id=int(eos_provision_expense_account_id) if eos_provision_expense_account_id else None,
            eos_provision_payable_account_id=int(eos_provision_payable_account_id) if eos_provision_payable_account_id else None,
        )
        s.add(c); s.commit(); s.refresh(c)
        return c.id


def update_contract(contract_id, employee_id, start_date, basic_salary, housing_allowance=0.0,
                     transport_allowance=0.0, other_allowances=0.0, contract_type="permanent",
                     end_date=None, gosi_rate_employee=9.75, gosi_rate_employer=11.75,
                     leave_provision_rate=8.33, eos_provision_rate=8.33,
                     basic_salary_account_id=None, housing_allowance_account_id=None,
                     transport_allowance_account_id=None, other_allowances_account_id=None,
                     gosi_deduction_account_id=None, other_deductions_account_id=None,
                     gosi_employer_expense_account_id=None, gosi_employer_payable_account_id=None,
                     leave_provision_expense_account_id=None, leave_provision_payable_account_id=None,
                     eos_provision_expense_account_id=None, eos_provision_payable_account_id=None):
    """يعدّل عقد موجود بالفعل - بيحترم نفس قواعد create_contract (حساب
    مستقل لكل عنصر قيمته أكبر من صفر، وحسابات الخصومات إجبارية دايماً).
    تعديل العقد ما بيأثرش على رواتب سابقة اتصرفت بالفعل، لأن كل مسير رواتب
    بياخد نسخته الخاصة من الحسابات وقت الإصدار."""
    require_action("contracts", "edit")
    if not employee_id:
        raise ValueError("اختر الموظف")
    basic_salary = float(basic_salary or 0)
    housing_allowance = float(housing_allowance or 0)
    transport_allowance = float(transport_allowance or 0)
    other_allowances = float(other_allowances or 0)
    gosi_rate_employer = float(gosi_rate_employer or 0)
    leave_provision_rate = float(leave_provision_rate or 0)
    eos_provision_rate = float(eos_provision_rate or 0)
    if basic_salary <= 0:
        raise ValueError("الراتب الأساسي يجب أن يكون أكبر من صفر")

    required = [("الراتب الأساسي", basic_salary_account_id, True)]
    required.append(("بدل السكن", housing_allowance_account_id, housing_allowance > 0))
    required.append(("بدل النقل", transport_allowance_account_id, transport_allowance > 0))
    required.append(("بدلات أخرى", other_allowances_account_id, other_allowances > 0))
    required.append(("خصم التأمينات الاجتماعية", gosi_deduction_account_id, True))
    required.append(("الخصومات الأخرى", other_deductions_account_id, True))
    required.append(("تأمينات صاحب العمل - مدين (مصروف)", gosi_employer_expense_account_id, gosi_rate_employer > 0))
    required.append(("تأمينات صاحب العمل - دائن (مستحق)", gosi_employer_payable_account_id, gosi_rate_employer > 0))
    required.append(("مخصص الإجازة - مدين (مصروف)", leave_provision_expense_account_id, leave_provision_rate > 0))
    required.append(("مخصص الإجازة - دائن (مستحق)", leave_provision_payable_account_id, leave_provision_rate > 0))
    required.append(("مخصص نهاية الخدمة - مدين (مصروف)", eos_provision_expense_account_id, eos_provision_rate > 0))
    required.append(("مخصص نهاية الخدمة - دائن (مستحق)", eos_provision_payable_account_id, eos_provision_rate > 0))

    for label, aid, mandatory in required:
        if mandatory and not aid:
            raise ValueError(f'لازم تحدد حساب "{label}" من شجرة الحسابات')

    with get_session() as s:
        c = s.get(Contract, int(contract_id))
        if not c:
            raise ValueError("العقد غير موجود")

        parent_ids = {a.parent_id for a in s.query(Account).all() if a.parent_id}
        for label, aid, mandatory in required:
            if aid and int(aid) in parent_ids:
                acc = s.get(Account, int(aid))
                raise ValueError(f'حساب "{label}" لازم يكون حساب فرعي - "{acc.code} - {acc.name}" حساب رئيسي مينفعش تترحّل عليه حركات مباشرة')

        c.employee_id = int(employee_id)
        c.contract_type = contract_type
        c.start_date = start_date
        c.end_date = end_date
        c.basic_salary = basic_salary
        c.housing_allowance = housing_allowance
        c.transport_allowance = transport_allowance
        c.other_allowances = other_allowances
        c.gosi_rate_employee = float(gosi_rate_employee or 0)
        c.gosi_rate_employer = gosi_rate_employer
        c.leave_provision_rate = leave_provision_rate
        c.eos_provision_rate = eos_provision_rate
        c.basic_salary_account_id = int(basic_salary_account_id)
        c.housing_allowance_account_id = int(housing_allowance_account_id) if housing_allowance_account_id else None
        c.transport_allowance_account_id = int(transport_allowance_account_id) if transport_allowance_account_id else None
        c.other_allowances_account_id = int(other_allowances_account_id) if other_allowances_account_id else None
        c.gosi_deduction_account_id = int(gosi_deduction_account_id)
        c.other_deductions_account_id = int(other_deductions_account_id)
        c.gosi_employer_expense_account_id = int(gosi_employer_expense_account_id) if gosi_employer_expense_account_id else None
        c.gosi_employer_payable_account_id = int(gosi_employer_payable_account_id) if gosi_employer_payable_account_id else None
        c.leave_provision_expense_account_id = int(leave_provision_expense_account_id) if leave_provision_expense_account_id else None
        c.leave_provision_payable_account_id = int(leave_provision_payable_account_id) if leave_provision_payable_account_id else None
        c.eos_provision_expense_account_id = int(eos_provision_expense_account_id) if eos_provision_expense_account_id else None
        c.eos_provision_payable_account_id = int(eos_provision_payable_account_id) if eos_provision_payable_account_id else None
        s.commit()
        return c.id


CONTRACT_STATE_LABELS = {"active": "ساري", "expired": "منتهي", "renewed": "مجدَّد", "terminated": "مفسوخ / منتهي بقرار"}

_RAISE_COMPONENTS = (("basic", "الراتب الأساسي", "basic_salary", "basic_salary_account_id"),
                     ("housing", "بدل السكن", "housing_allowance", "housing_allowance_account_id"),
                     ("transport", "بدل النقل", "transport_allowance", "transport_allowance_account_id"),
                     ("other", "بدلات أخرى", "other_allowances", "other_allowances_account_id"))


def preview_contract_renewal(contract_id, raise_mode="none", raise_percent=0.0, percent_components=("basic",),
                              raises=None):
    """بيحسب الرواتب الجديدة بعد الزيادة من غير ما يحفظ حاجة (للمعاينة في الشاشة).
    raise_mode: none (تجديد بنفس الرواتب) | percent (نسبة على بنود محددة) | amount (مبلغ لكل بند).
    بيرجع لكل بند: القديم والزيادة والجديد، وإجمالي القديم والجديد."""
    c = get_contract(contract_id)
    if not c:
        raise ValueError("العقد غير موجود")
    raises = raises or {}
    if raise_mode not in ("none", "percent", "amount"):
        raise ValueError("نوع الزيادة غير معروف")
    pct = float(raise_percent or 0)
    if raise_mode == "percent" and not (0 < pct <= 100):
        raise ValueError("نسبة الزيادة لازم تكون أكبر من صفر وحد أقصى 100%")
    lines = []
    for key, label, attr, acc_attr in _RAISE_COMPONENTS:
        old = float(getattr(c, attr) or 0)
        inc = 0.0
        if raise_mode == "percent" and key in percent_components:
            inc = round(old * pct / 100.0, 2)
        elif raise_mode == "amount":
            inc = round(float(raises.get(key) or 0), 2)
        if inc < 0:
            raise ValueError(f'زيادة "{label}" مينفعش تبقى سالبة')
        if inc > 0 and old <= 0 and not getattr(c, acc_attr):
            raise ValueError(f'"{label}" مالوش حساب في العقد الحالي - عدّل العقد وحدد الحساب الأول قبل ما تضيف عليه زيادة')
        lines.append({"key": key, "label": label, "old": old, "raise": inc, "new": round(old + inc, 2)})
    old_total = round(sum(l["old"] for l in lines), 2)
    new_total = round(sum(l["new"] for l in lines), 2)
    return {"lines": lines, "old_total": old_total, "new_total": new_total, "raise_total": round(new_total - old_total, 2),
            "raise_pct_of_total": round((new_total - old_total) / old_total * 100.0, 2) if old_total else 0.0}


def renew_contract(contract_id, new_start_date=None, new_end_date=None, raise_mode="none", raise_percent=0.0,
                   percent_components=("basic",), raises=None, raise_note="", contract_type=None):
    """تجديد عقد: بيعمل عقد جديد بنفس كل شروط العقد السابق (الرواتب والبدلات
    ونسب التأمينات والمخصصات وكل الحسابات) + أي زيادة بتتطبّق على العقد
    الجديد بس. العقد السابق بيتقفل كـ"مجدَّد" بتاريخ نهاية قبل بداية الجديد
    بيوم، وبيفضل محفوظ بكل رواتبه - والعقد الجديد بيسجّل الراتب السابق
    وقيمة الزيادة عشان تاريخ الرواتب يفضل واضح."""
    require_action("contracts", "create")
    prev = get_contract(contract_id)
    if not prev:
        raise ValueError("العقد غير موجود")
    if prev.state == "terminated":
        raise ValueError("العقد ده اتفسخ - مينفعش يتجدد، أنشئ عقد جديد للموظف لو هترجّعه")
    if prev.state == "renewed":
        raise ValueError("العقد ده اتجدد بالفعل - جدّد آخر عقد للموظف")
    with get_session() as s:
        newer = s.query(Contract).filter(Contract.employee_id == prev.employee_id, Contract.start_date > prev.start_date,
                                         Contract.id != prev.id).count()
    if newer:
        raise ValueError("فيه عقد أحدث للموظف ده - جدّد آخر عقد بس")

    if new_start_date is None:
        new_start_date = (prev.end_date + datetime.timedelta(days=1)) if prev.end_date else datetime.datetime.now()
    if new_start_date <= prev.start_date:
        raise ValueError("تاريخ بداية العقد الجديد لازم يكون بعد بداية العقد السابق")
    ctype = contract_type or prev.contract_type
    if ctype == "temporary":
        if not new_end_date:
            raise ValueError("العقد المحدد المدة لازم له تاريخ نهاية")
        if new_end_date <= new_start_date:
            raise ValueError("تاريخ نهاية العقد لازم يكون بعد بدايته")
    elif new_end_date and new_end_date <= new_start_date:
        raise ValueError("تاريخ نهاية العقد لازم يكون بعد بدايته")

    prev_calc = preview_contract_renewal(contract_id, raise_mode, raise_percent, percent_components, raises)
    new_vals = {l["key"]: l["new"] for l in prev_calc["lines"]}
    if raise_mode != "none" and prev_calc["raise_total"] <= 0:
        raise ValueError("اخترت زيادة بس إجمالي الزيادة صفر - حدد نسبة أو مبالغ، أو اختار \"تجديد بنفس الرواتب\"")

    return create_contract(
        employee_id=prev.employee_id, start_date=new_start_date, basic_salary=new_vals["basic"],
        housing_allowance=new_vals["housing"], transport_allowance=new_vals["transport"], other_allowances=new_vals["other"],
        contract_type=ctype, end_date=new_end_date,
        gosi_rate_employee=prev.gosi_rate_employee, gosi_rate_employer=prev.gosi_rate_employer,
        leave_provision_rate=prev.leave_provision_rate, eos_provision_rate=prev.eos_provision_rate,
        basic_salary_account_id=prev.basic_salary_account_id, housing_allowance_account_id=prev.housing_allowance_account_id,
        transport_allowance_account_id=prev.transport_allowance_account_id, other_allowances_account_id=prev.other_allowances_account_id,
        gosi_deduction_account_id=prev.gosi_deduction_account_id, other_deductions_account_id=prev.other_deductions_account_id,
        gosi_employer_expense_account_id=prev.gosi_employer_expense_account_id, gosi_employer_payable_account_id=prev.gosi_employer_payable_account_id,
        leave_provision_expense_account_id=prev.leave_provision_expense_account_id, leave_provision_payable_account_id=prev.leave_provision_payable_account_id,
        eos_provision_expense_account_id=prev.eos_provision_expense_account_id, eos_provision_payable_account_id=prev.eos_provision_payable_account_id,
        renewed_from_id=prev.id, previous_gross_salary=prev_calc["old_total"], raise_amount=prev_calc["raise_total"],
        raise_note=raise_note,
    )


def terminate_contract(contract_id, termination_date=None, reason=""):
    """إنهاء عقد بقرار (فسخ): بيحدد تاريخ الإنهاء وسببه، وبيقفل العقد من
    الرواتب بعد التاريخ ده. آخر شهر قبل الإنهاء بيتحسب عادي في الدورات."""
    require_action("contracts", "edit")
    termination_date = termination_date or datetime.datetime.now()
    with get_session() as s:
        c = s.get(Contract, contract_id)
        if not c:
            raise ValueError("العقد غير موجود")
        if c.state == "terminated":
            raise ValueError("العقد ده منتهي بالفعل")
        if c.state == "renewed":
            raise ValueError("العقد ده اتجدد - أنهِ آخر عقد للموظف")
        if termination_date < c.start_date:
            raise ValueError("تاريخ الإنهاء لا يمكن يكون قبل بداية العقد")
        c.state = "terminated"
        c.end_date = termination_date
        c.termination_date = termination_date
        c.termination_reason = (reason or "").strip()
        s.commit()


def contract_history(employee_id):
    """سجل عقود الموظف بالترتيب الزمني: كل عقد برواتبه، والراتب السابق
    والزيادة اللي اتطبقت عند التجديد (بالمبلغ وبالنسبة)، وبيانات الإنهاء."""
    contracts = sorted(list_contracts(employee_id), key=lambda c: c.start_date)
    out = []
    for c in contracts:
        prev_gross = c.previous_gross_salary
        out.append({
            "id": c.id, "number": c.contract_number, "state": c.state, "state_label": CONTRACT_STATE_LABELS.get(c.state, c.state),
            "start_date": c.start_date, "end_date": c.end_date, "contract_type": c.contract_type,
            "basic": c.basic_salary, "gross": c.gross_salary, "renewal_count": c.renewal_count or 0,
            "previous_gross": prev_gross, "raise_amount": c.raise_amount or 0.0,
            "raise_pct": round((c.raise_amount or 0) / prev_gross * 100.0, 2) if prev_gross else 0.0,
            "raise_note": c.raise_note or "", "termination_date": c.termination_date, "termination_reason": c.termination_reason or "",
        })
    return out


def contracts_expiring(days=60):
    """العقود الساريّة المحددة المدة اللي هتنتهي خلال days يوم (أو انتهت ولسه
    ما اتجددتش) - للتنبيه بالتجديد في الوقت المناسب. بيرجع [(contract, days_left)]."""
    now = datetime.datetime.now()
    out = []
    for c in list_contracts():
        if c.state != "active" or not c.end_date:
            continue
        left = (c.end_date.date() - now.date()).days
        if left <= int(days):
            out.append((c, left))
    out.sort(key=lambda x: x[1])
    return out


# ---------------------------- الرواتب ----------------------------
def list_payroll_runs(limit=100):
    with get_session() as s:
        return s.query(PayrollRun).options(joinedload(PayrollRun.payslips)).order_by(
            PayrollRun.year.desc(), PayrollRun.month.desc()
        ).limit(limit).all()


def get_payroll_run(run_id):
    with get_session() as s:
        r = s.query(PayrollRun).options(
            joinedload(PayrollRun.payslips).joinedload(Payslip.employee).joinedload(Employee.cost_center)
        ).filter(PayrollRun.id == run_id).first()
        if r:
            s.expunge_all()
        return r


def _month_bounds(month, year):
    first = datetime.date(year, month, 1)
    return first, datetime.date(year + (month == 12), month % 12 + 1, 1) - datetime.timedelta(days=1)


def leave_deduction_for(s, employee_id, gross, month, year, day_basis=30):
    """خصم الإجازات المعتمدة في شهر معيّن: لكل إجازة (حسب نوعها) أيام الشهر × نسبة الخصم × أجر اليوم (الإجمالي ÷ أساس اليوم)، بحد أقصى الإجمالي.
    day_basis: 30 (شهر ثابت) أو 0 (أيام الشهر الفعلية). بيرجّع (المبلغ، الأيام المخصومة بعد النسبة)."""
    first = datetime.date(year, month, 1)
    last = (datetime.date(year + (month == 12), month % 12 + 1, 1) - datetime.timedelta(days=1))
    pct_by_code = {t.code: (t.deduct_percent or 0.0) for t in s.query(LeaveType).all()}
    weighted = 0.0
    for r in s.query(LeaveRequest).filter(
            LeaveRequest.employee_id == int(employee_id), LeaveRequest.state == "approved",
            LeaveRequest.start_date <= datetime.datetime(last.year, last.month, last.day, 23, 59, 59),
            LeaveRequest.end_date >= datetime.datetime(first.year, first.month, first.day)).all():
        pct = pct_by_code.get(r.leave_type, 0.0)
        if pct <= 0:
            continue
        a, b = max(r.start_date.date(), first), min(r.end_date.date(), last)
        if b >= a:
            weighted += ((b - a).days + 1) * pct / 100.0
    divisor = float(day_basis) if day_basis else float((last - first).days + 1)
    amount = min(round(weighted * (gross or 0) / divisor, 2), round(gross or 0, 2))
    return amount, round(weighted, 2)


def _employment_days(s, employee_id, first, last):
    """أيام الشهر اللي الموظف فيها على عقد (اتحاد كل عقوده - عشان التجديد في نص الشهر ما يتحسبش فجوة)."""
    spans = []
    for c in s.query(Contract).filter(Contract.employee_id == int(employee_id), _contract_state_filter()).all():
        a = c.start_date.date()
        e = (c.termination_date or c.end_date)
        b = e.date() if e else last
        a, b = max(a, first), min(b, last)
        if b >= a:
            spans.append((a, b))
    days = set()
    for a, b in spans:
        for i in range((b - a).days + 1):
            days.add(a + datetime.timedelta(days=i))
    return len(days)


def _leave_days_total(s, employee_id, first, last):
    """كل أيام الإجازات المعتمدة (أي نوع) داخل الشهر - للعرض في أيام العمل الفعلي."""
    n = 0
    for r in s.query(LeaveRequest).filter(
            LeaveRequest.employee_id == int(employee_id), LeaveRequest.state == "approved",
            LeaveRequest.start_date <= datetime.datetime(last.year, last.month, last.day, 23, 59, 59),
            LeaveRequest.end_date >= datetime.datetime(first.year, first.month, first.day)).all():
        a, b = max(r.start_date.date(), first), min(r.end_date.date(), last)
        if b >= a:
            n += (b - a).days + 1
    return n


def _contract_day_map(s, employee_id, first, last):
    """لكل يوم في الشهر: العقد الساري (لو أكتر من عقد بيغطّوا اليوم، العقد الأحدث بداية هو اللي بيحكم).
    بيرجّع (قايمة العقود مرتبة بالأحدث أولًا، {contract_id: عدد الأيام})."""
    contracts = s.query(Contract).filter(Contract.employee_id == int(employee_id), _contract_state_filter()).order_by(Contract.start_date.desc()).all()
    counts = {}
    d = first
    while d <= last:
        for c in contracts:
            e = c.termination_date or c.end_date
            if c.start_date.date() <= d and (e is None or e.date() >= d):
                counts[c.id] = counts.get(c.id, 0) + 1
                break
        d += datetime.timedelta(days=1)
    return contracts, counts


def weighted_pay_components(s, employee_id, month, year):
    """مكونات الراتب الموزونة بأيام كل عقد في الشهر (زيادة/تجديد في نص الشهر: القديم لأيامه والجديد لأيامه).
    بيرجّع None لو مفيش أي يوم على عقد. غير كده: dict فيه latest (العقد الأحدث)، employed_days، المكونات والتأمينات المتوسطة لأيام التعيين."""
    first, last = _month_bounds(month, year)
    contracts, counts = _contract_day_map(s, employee_id, first, last)
    employed = sum(counts.values())
    if not employed:
        return None
    by_id = {c.id: c for c in contracts}
    out = {"basic": 0.0, "housing": 0.0, "transport": 0.0, "other": 0.0, "gosi": 0.0}
    for cid, n in counts.items():
        c = by_id[cid]
        w = n / employed
        out["basic"] += (c.basic_salary or 0) * w
        out["housing"] += (c.housing_allowance or 0) * w
        out["transport"] += (c.transport_allowance or 0) * w
        out["other"] += (c.other_allowances or 0) * w
        out["gosi"] += (c.basic_salary or 0) * (c.gosi_rate_employee or 0) / 100.0 * w
    latest = next(c for c in contracts if c.id in counts)
    res = {k: round(v, 2) for k, v in out.items()}
    res.update(latest=latest, employed_days=employed, split=len(counts) > 1)
    return res


def recalc_payslip(s, p, run):
    """بيحسب أثر أيام العمل الفعلي على القسيمة: أيام غير موظف (تعيين/إنهاء في نص الشهر) + خصم الإجازات حسب نوعها + أيام الغياب.
    كل أجر يوم = الإجمالي ÷ أساس اليوم (30 ثابت، أو أيام الشهر الفعلية من إعدادات الشركة). مجموع الخصومات الثلاثة ≤ الإجمالي."""
    cfg = s.get(CompanySettings, 1)
    basis = 30 if cfg is None or cfg.payroll_day_basis is None else int(cfg.payroll_day_basis)
    first, last = _month_bounds(run.month, run.year)
    dim = (last - first).days + 1
    divisor = float(basis) if basis else float(dim)
    gross = p.gross_salary
    daily = gross / divisor if divisor else 0.0

    employed = _employment_days(s, p.employee_id, first, last)
    unemployed = max(0, dim - employed)
    unemp_ded = min(round(unemployed * daily, 2), round(gross, 2))
    leave_ded, leave_days = leave_deduction_for(s, p.employee_id, gross, run.month, run.year, basis)
    leave_ded = min(leave_ded, round(gross - unemp_ded, 2))
    absent = max(0.0, float(p.absent_days or 0))
    abs_ded = min(round(absent * daily, 2), round(gross - unemp_ded - leave_ded, 2))
    leave_total = _leave_days_total(s, p.employee_id, first, last)

    p.unemployed_days = float(unemployed); p.unemployed_deduction = unemp_ded
    p.leave_deduction = leave_ded; p.leave_deduction_days = leave_days
    p.leave_days_total = float(leave_total)
    p.absent_days = absent; p.absence_deduction = abs_ded
    p.worked_days = float(max(0.0, employed - leave_total - absent))
    p.net_salary = round(gross - p.total_deductions, 2)


def create_payroll_run(month, year, branch_id=None):
    """ينشئ دورة رواتب جديدة ويولّد قسيمة لكل موظف نشط له عقد ساري تلقائياً."""
    require_action("payroll", "create")
    month = int(month); year = int(year)
    if month < 1 or month > 12:
        raise ValueError("الشهر غير صحيح")
    with get_session() as s:
        existing = s.query(PayrollRun).filter(PayrollRun.month == month, PayrollRun.year == year).first()
        if existing:
            raise ValueError(f"دورة رواتب شهر {month}/{year} موجودة بالفعل (رقم {existing.number})")
        number = _next_code(s, PayrollRun, "PR-")
        run = PayrollRun(number=number, month=month, year=year, branch_id=branch_id or default_branch_id(), state="draft")
        s.add(run); s.flush()

        employees = s.query(Employee).filter(Employee.is_active.is_(True)).all()
        for emp in employees:
            wc = weighted_pay_components(s, emp.id, month, year)      # بيراعي الزيادة/التجديد في نص الشهر (راتب موزون بأيام كل عقد)
            if not wc:
                continue
            contract = wc["latest"]
            gosi = wc["gosi"]
            gross = wc["basic"] + wc["housing"] + wc["transport"] + wc["other"]
            s.add(Payslip(
                run_id=run.id, employee_id=emp.id, contract_id=contract.id,
                basic_salary=wc["basic"], housing_allowance=wc["housing"],
                transport_allowance=wc["transport"], other_allowances=wc["other"],
                gosi_deduction=gosi, other_deductions=0.0,
                net_salary=round(gross - gosi, 2),
                basic_salary_account_id=contract.basic_salary_account_id,
                housing_allowance_account_id=contract.housing_allowance_account_id,
                transport_allowance_account_id=contract.transport_allowance_account_id,
                other_allowances_account_id=contract.other_allowances_account_id,
                gosi_deduction_account_id=contract.gosi_deduction_account_id,
                other_deductions_account_id=contract.other_deductions_account_id,
            ))
        s.flush()
        for p in s.query(Payslip).filter(Payslip.run_id == run.id).all():
            recalc_payslip(s, p, run)
        try:
            from . import attendance
            attendance.apply_attendance_to_run(s, run)        # غياب البصمة (للموظفين اللي ليهم بصمات في الشهر)
        except Exception:      # noqa: BLE001
            pass
        s.commit(); s.refresh(run)
        return run.id


def update_payslip(payslip_id, **fields):
    """تعديل يدوي على قسيمة راتب (خصومات إضافية، مكافآت...) قبل الترحيل."""
    require_action("payroll", "edit")
    with get_session() as s:
        p = s.get(Payslip, payslip_id)
        if not p:
            raise ValueError("القسيمة غير موجودة")
        run = s.get(PayrollRun, p.run_id)
        if run.state != "draft":
            raise ValueError("مينفعش تعدّل على قسيمة في دورة مرحّلة - رجّع الدورة مسودة أولاً")
        if "absent_days" in fields:
            try:
                if float(fields["absent_days"] or 0) < 0 or float(fields["absent_days"] or 0) > 31:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError("أيام الغياب لازم تكون رقم من 0 لـ 31")
            fields["absent_days"] = float(fields["absent_days"] or 0)
        for k, v in fields.items():
            setattr(p, k, v)
        recalc_payslip(s, p, run)
        s.commit()


def delete_payroll_run(run_id):
    require_action("payroll", "delete")
    with get_session() as s:
        run = s.get(PayrollRun, run_id)
        if not run:
            raise ValueError("الدورة غير موجودة")
        if run.state == "posted":
            raise ValueError("مينفعش تحذف دورة مرحّلة - رجّعها مسودة أولاً")
        s.delete(run)
        s.commit()


def post_payroll_run(run_id):
    """يرحّل دورة الرواتب: بيبني قيد محاسبي بيجمّع الراتب الأساسي والبدلات
    حسب حساب كل موظف بالظبط (كل موظف ممكن يكون ليه حساب مصروف مختلف
    للراتب الأساسي وحساب تاني للبدلات، زي ما محدّد في عقده)."""
    require_action("payroll", "post")
    with get_session() as s:
        run = s.get(PayrollRun, run_id)
        if not run:
            raise ValueError("الدورة غير موجودة")
        if run.state == "posted":
            raise ValueError("الدورة مرحّلة بالفعل")
        payslips = s.query(Payslip).options(joinedload(Payslip.employee)).filter(Payslip.run_id == run.id).all()
        if not payslips:
            raise ValueError("مفيش قسائم رواتب في الدورة دي - تأكد من وجود موظفين نشطين لهم عقود سارية")
        for p in payslips:      # الإجازات اللي اتعتمدت بعد إنشاء الدورة (وتغيّرات العقود) تتحسب قبل الترحيل
            recalc_payslip(s, p, run)
        s.commit()

        cfg = s.get(AccountingSettings, 1)

        debit_by_account = {}   # account_id -> amount مجمّع (مصروفات: أساسي + بدلات)
        credit_by_account = {}  # account_id -> amount مجمّع (خصومات: تأمينات + أخرى)

        def add_debit(amount, account_id, emp_name, label):
            if not amount:
                return
            if not account_id:
                raise ValueError(f'الموظف "{emp_name}" عقده مفيهوش حساب "{label}" محدد - عدّل العقد من شاشة العقود أولاً')
            debit_by_account[account_id] = debit_by_account.get(account_id, 0.0) + amount

        def add_credit(amount, account_id, emp_name, label):
            if not amount:
                return
            if not account_id:
                raise ValueError(f'الموظف "{emp_name}" عقده مفيهوش حساب "{label}" محدد - عدّل العقد من شاشة العقود أولاً')
            credit_by_account[account_id] = credit_by_account.get(account_id, 0.0) + amount

        for p in payslips:
            emp_name = p.employee.name if p.employee else f"#{p.employee_id}"
            add_debit(p.basic_salary, p.basic_salary_account_id, emp_name, "الراتب الأساسي")
            add_debit(p.housing_allowance, p.housing_allowance_account_id, emp_name, "بدل السكن")
            add_debit(p.transport_allowance, p.transport_allowance_account_id, emp_name, "بدل النقل")
            add_debit(p.other_allowances, p.other_allowances_account_id, emp_name, "بدلات أخرى")
            add_credit(p.gosi_deduction, p.gosi_deduction_account_id, emp_name, "خصم التأمينات الاجتماعية")
            add_credit(p.other_deductions, p.other_deductions_account_id, emp_name, "الخصومات الأخرى")
            add_credit((p.leave_deduction or 0) + (p.absence_deduction or 0) + (p.unemployed_deduction or 0),
                       cfg.leave_deduction_account_id or p.other_deductions_account_id, emp_name, "الخصومات الأخرى (خصم الإجازات والغياب)")

        total_net = sum(p.net_salary for p in payslips)
        entry_date = datetime.datetime(run.year, run.month, 1)
        run_branch_id = run.branch_id
        run_number, run_month, run_year = run.number, run.month, run.year

        if not cfg.salaries_payable_account_id:
            raise ValueError("إعداد حساب الرواتب المستحقة ناقص - راجع الإعدادات المحاسبية")

    lines = []
    for acc_id, amount in debit_by_account.items():
        lines.append({"account_id": acc_id, "debit": round(amount, 2)})
    for acc_id, amount in credit_by_account.items():
        lines.append({"account_id": acc_id, "credit": round(amount, 2)})
    lines.append({"account_id": cfg.salaries_payable_account_id, "credit": round(total_net, 2)})

    with get_session() as s:
        run_row = s.get(PayrollRun, run_id)
        existing_jid = run_row.journal_entry_id

    if existing_jid and get_journal_entry(existing_jid):
        update_journal_entry(existing_jid, lines, reference=run_number, description=f"رواتب شهر {run_month}/{run_year}", _internal=True)
        post_journal_entry_by_id(existing_jid)
        jid = existing_jid
    else:
        jid = create_journal_entry(
            lines, reference=run_number, description=f"رواتب شهر {run_month}/{run_year}",
            source_type="payroll", source_id=run_id, entry_date=entry_date, branch_id=run_branch_id,
        )

    with get_session() as s:
        run = s.get(PayrollRun, run_id)
        run.state = "posted"
        run.journal_entry_id = jid
        s.commit()
    return jid


# ======================================================================
# دورة المخصصات والتأمينات - منفصلة عن دورة الرواتب الشهرية، بنفس النمط
# بالظبط (مسودة -> ترحيل -> قيد محاسبي واحد يجمّع كل الموظفين)
# ======================================================================
def list_allowance_insurance_runs(limit=100):
    with get_session() as s:
        runs = s.query(AllowanceInsuranceRun).options(joinedload(AllowanceInsuranceRun.items)).order_by(
            AllowanceInsuranceRun.year.desc(), AllowanceInsuranceRun.month.desc()
        ).limit(limit).all()
        s.expunge_all()
        return runs


def get_allowance_insurance_run(run_id):
    with get_session() as s:
        r = s.query(AllowanceInsuranceRun).options(
            joinedload(AllowanceInsuranceRun.items).joinedload(AllowanceInsuranceItem.employee),
            joinedload(AllowanceInsuranceRun.items).joinedload(AllowanceInsuranceItem.extra_allowance_account),
        ).filter(AllowanceInsuranceRun.id == run_id).first()
        if r:
            s.expunge_all()
        return r


def create_allowance_insurance_run(month, year, branch_id=None):
    """ينشئ دورة مخصصات وتأمينات جديدة - بند لكل موظف نشط له عقد ساري،
    بنصيب صاحب العمل في التأمينات محسوب تلقائياً من نسبة العقد (مصروف على
    الشركة بالكامل، مش خصم من الموظف). المخصص الإضافي بيتحدد يدوياً بعد
    كده لكل موظف حسب الحاجة قبل الترحيل."""
    require_action("allowances_insurance", "create")
    month = int(month); year = int(year)
    if month < 1 or month > 12:
        raise ValueError("الشهر غير صحيح")
    with get_session() as s:
        existing = s.query(AllowanceInsuranceRun).filter(AllowanceInsuranceRun.month == month, AllowanceInsuranceRun.year == year).first()
        if existing:
            raise ValueError(f"دورة مخصصات وتأمينات شهر {month}/{year} موجودة بالفعل (رقم {existing.number})")
        number = _next_code(s, AllowanceInsuranceRun, "AI-")
        run = AllowanceInsuranceRun(number=number, month=month, year=year, branch_id=branch_id or default_branch_id(), state="draft")
        s.add(run); s.flush()

        period_end = datetime.datetime(year, month, 1) + datetime.timedelta(days=31)
        employees = s.query(Employee).filter(Employee.is_active.is_(True)).all()
        for emp in employees:
            contract = s.query(Contract).filter(
                Contract.employee_id == emp.id, _contract_state_filter(),
                Contract.start_date <= period_end,
            ).filter((Contract.end_date.is_(None)) | (Contract.end_date >= datetime.datetime(year, month, 1))).order_by(Contract.start_date.desc()).first()
            if not contract:
                continue
            employer_gosi = round(contract.basic_salary * (contract.gosi_rate_employer or 0) / 100.0, 2)
            leave_provision = round(contract.basic_salary * (contract.leave_provision_rate or 0) / 100.0, 2)
            eos_provision = round(contract.basic_salary * (contract.eos_provision_rate or 0) / 100.0, 2)
            s.add(AllowanceInsuranceItem(
                run_id=run.id, employee_id=emp.id, contract_id=contract.id,
                extra_allowance=0.0, extra_allowance_account_id=None,
                employer_gosi_amount=employer_gosi,
                employer_gosi_expense_account_id=contract.gosi_employer_expense_account_id,
                employer_gosi_payable_account_id=contract.gosi_employer_payable_account_id,
                leave_provision_amount=leave_provision,
                leave_provision_expense_account_id=contract.leave_provision_expense_account_id,
                leave_provision_payable_account_id=contract.leave_provision_payable_account_id,
                eos_provision_amount=eos_provision,
                eos_provision_expense_account_id=contract.eos_provision_expense_account_id,
                eos_provision_payable_account_id=contract.eos_provision_payable_account_id,
            ))
        s.commit(); s.refresh(run)
        return run.id


def update_allowance_insurance_item(item_id, **fields):
    """تعديل بند مخصص/تأمين لموظف واحد قبل الترحيل - أهم استخدام هو تحديد
    مبلغ المخصص الإضافي وحسابه."""
    require_action("allowances_insurance", "edit")
    with get_session() as s:
        item = s.get(AllowanceInsuranceItem, item_id)
        if not item:
            raise ValueError("البند غير موجود")
        run = s.get(AllowanceInsuranceRun, item.run_id)
        if run.state != "draft":
            raise ValueError("مينفعش تعدّل على بند في دورة مرحّلة - رجّع الدورة مسودة أولاً")
        for k, v in fields.items():
            setattr(item, k, v)
        s.commit()


def delete_allowance_insurance_run(run_id):
    require_action("allowances_insurance", "delete")
    with get_session() as s:
        run = s.get(AllowanceInsuranceRun, run_id)
        if not run:
            raise ValueError("الدورة غير موجودة")
        if run.state == "posted":
            raise ValueError("مينفعش تحذف دورة مرحّلة - رجّعها مسودة أولاً")
        s.delete(run)
        s.commit()


def reopen_allowance_insurance_run(run_id):
    """يرجّع دورة مرحّلة لمسودة عشان تقدر تعدّل عليها - بيلغي القيد
    المحاسبي المرتبط بيها (بيحوّله لمسودة برضه، مش بيمسحه)."""
    require_action("allowances_insurance", "edit")
    with get_session() as s:
        run = s.get(AllowanceInsuranceRun, run_id)
        if not run:
            raise ValueError("الدورة غير موجودة")
        if run.state != "posted":
            raise ValueError("الدورة مسودة بالفعل")
        jid = run.journal_entry_id
        run.state = "draft"
        s.commit()
    if jid:
        try:
            set_journal_entry_draft_by_source(jid)
        except Exception:
            pass


def post_allowance_insurance_run(run_id):
    """يرحّل دورة المخصصات والتأمينات: قيد واحد بيجمّع المخصصات الإضافية
    (مصروف) ونصيب صاحب العمل في التأمينات (مصروف / مستحق) حسب حساب كل
    موظف، بنفس منطق ترحيل الرواتب بالظبط."""
    require_action("allowances_insurance", "post")
    with get_session() as s:
        run = s.get(AllowanceInsuranceRun, run_id)
        if not run:
            raise ValueError("الدورة غير موجودة")
        if run.state == "posted":
            raise ValueError("الدورة مرحّلة بالفعل")
        items = s.query(AllowanceInsuranceItem).options(joinedload(AllowanceInsuranceItem.employee)).filter(AllowanceInsuranceItem.run_id == run.id).all()
        if not items:
            raise ValueError("مفيش بنود في الدورة دي - تأكد من وجود موظفين نشطين لهم عقود سارية")

        debit_by_account = {}
        credit_by_account = {}

        def add_debit(amount, account_id, emp_name, label):
            if not amount:
                return
            if not account_id:
                raise ValueError(f'الموظف "{emp_name}" مفيهوش حساب "{label}" محدد')
            debit_by_account[account_id] = debit_by_account.get(account_id, 0.0) + amount

        def add_credit(amount, account_id, emp_name, label):
            if not amount:
                return
            if not account_id:
                raise ValueError(f'الموظف "{emp_name}" مفيهوش حساب "{label}" محدد')
            credit_by_account[account_id] = credit_by_account.get(account_id, 0.0) + amount

        for it in items:
            emp_name = it.employee.name if it.employee else f"#{it.employee_id}"
            add_debit(it.extra_allowance, it.extra_allowance_account_id, emp_name, "المخصص الإضافي")
            add_debit(it.employer_gosi_amount, it.employer_gosi_expense_account_id, emp_name, "مصروف تأمينات صاحب العمل")
            add_credit(it.employer_gosi_amount, it.employer_gosi_payable_account_id, emp_name, "مستحق تأمينات صاحب العمل")
            add_debit(it.leave_provision_amount, it.leave_provision_expense_account_id, emp_name, "مصروف مخصص الإجازة")
            add_credit(it.leave_provision_amount, it.leave_provision_payable_account_id, emp_name, "مستحق مخصص الإجازة")
            add_debit(it.eos_provision_amount, it.eos_provision_expense_account_id, emp_name, "مصروف مخصص نهاية الخدمة")
            add_credit(it.eos_provision_amount, it.eos_provision_payable_account_id, emp_name, "مستحق مخصص نهاية الخدمة")

        # المخصص الإضافي بيتدفع نقدًا/يضاف على المستحقات - نجمعه في نفس
        # حساب الرواتب المستحقة العام زي صافي الراتب في دورة الرواتب
        cfg = s.get(AccountingSettings, 1)
        total_extra = sum(it.extra_allowance or 0 for it in items)
        entry_date = datetime.datetime(run.year, run.month, 1)
        run_branch_id = run.branch_id
        run_number, run_month, run_year = run.number, run.month, run.year
        if total_extra and not cfg.salaries_payable_account_id:
            raise ValueError("إعداد حساب الرواتب المستحقة ناقص - راجع الإعدادات المحاسبية")

    lines = []
    for acc_id, amount in debit_by_account.items():
        lines.append({"account_id": acc_id, "debit": round(amount, 2)})
    for acc_id, amount in credit_by_account.items():
        lines.append({"account_id": acc_id, "credit": round(amount, 2)})
    if total_extra:
        lines.append({"account_id": cfg.salaries_payable_account_id, "credit": round(total_extra, 2)})

    with get_session() as s:
        run_row = s.get(AllowanceInsuranceRun, run_id)
        existing_jid = run_row.journal_entry_id

    if existing_jid and get_journal_entry(existing_jid):
        update_journal_entry(existing_jid, lines, reference=run_number, description=f"مخصصات وتأمينات شهر {run_month}/{run_year}", _internal=True)
        post_journal_entry_by_id(existing_jid)
        jid = existing_jid
    else:
        jid = create_journal_entry(
            lines, reference=run_number, description=f"مخصصات وتأمينات شهر {run_month}/{run_year}",
            source_type="allowance_insurance", source_id=run_id, entry_date=entry_date, branch_id=run_branch_id,
        )

    with get_session() as s:
        run = s.get(AllowanceInsuranceRun, run_id)
        run.state = "posted"
        run.journal_entry_id = jid
        s.commit()
    return jid


def reopen_payroll_run(run_id):
    """يرجّع دورة رواتب مرحّلة لمسودة (وبيحوّل قيدها المحاسبي لمسودة برضه)."""
    require_action("payroll", "edit")
    with get_session() as s:
        run = s.get(PayrollRun, run_id)
        if not run:
            raise ValueError("الدورة غير موجودة")
        if run.state != "posted":
            raise ValueError("الدورة مش مرحّلة أصلاً")
        if s.query(Payslip.id).filter(Payslip.run_id == run.id, Payslip.paid_at.isnot(None)).first():
            raise ValueError("فيه موظفين اتصرف راتبهم بالفعل - تراجع عن صرفهم الأول من شاشة الرواتب")
        jid = run.journal_entry_id
        run.state = "draft"
        s.commit()
    if jid:
        try:
            set_journal_entry_draft_by_source(jid)
        except Exception:
            pass


def payroll_run_payment_status(run_id):
    """ملخص حالة الصرف لدورة: إجمالي، مدفوع، متبقٍ، وهل كل الموظفين اتصرفوا."""
    with get_session() as s:
        payslips = s.query(Payslip).filter(Payslip.run_id == int(run_id)).all()
        total = sum(p.net_salary for p in payslips)
        paid = sum(p.net_salary for p in payslips if p.paid_at)
        return {"total": round(total, 2), "paid": round(paid, 2), "remaining": round(total - paid, 2),
                "paid_count": sum(1 for p in payslips if p.paid_at), "total_count": len(payslips),
                "all_paid": bool(payslips) and all(p.paid_at for p in payslips)}


def list_payroll_run_payments(run_id):
    """كل سندات الصرف (سارية وملغاة) المرتبطة بدورة رواتب معيّنة، الأحدث الأول."""
    with get_session() as s:
        return s.query(Payment).filter(Payment.partner_type == "payroll", Payment.partner_id == int(run_id)).order_by(Payment.id.desc()).all()


def pay_payslips(payslip_ids, payment_method_id, payment_date=None, reference=""):
    """يصرف صافي راتب مجموعة قسائم محددة (موظف واحد، قسم كامل، أو أي
    تشكيلة) دفعة واحدة: سند صرف واحد وقيد واحد (مدين الرواتب المستحقة /
    دائن حساب طريقة الدفع)، وبيعلّم كل قسيمة بتاريخ وسند صرفها. القسائم
    المدفوعة بالفعل ضمن الاختيار بتتجاهل تلقائيًا. طريقة الدفع لازم تكون
    ليها حساب ثابت (مش "آجل") عشان الرواتب المستحقة تتقفل فعليًا."""
    require_action("payroll", "post")
    pm = get_payment_method(payment_method_id)
    if not pm:
        raise ValueError("طريقة الدفع غير موجودة")
    if not pm.is_active:
        raise ValueError(f'طريقة الدفع "{pm.name}" موقوفة')
    if pm.is_credit or not pm.account_id:
        raise ValueError(f'طريقة الدفع "{pm.name}" آجل - بدون حساب ثابت، فمينفعش تتصرف بيها الرواتب فعليًا')
    cash_account_id = pm.account_id
    ids = sorted({int(i) for i in (payslip_ids or [])})
    if not ids:
        raise ValueError("اختار موظف واحد على الأقل للصرف")
    with get_session() as s:
        payslips = s.query(Payslip).options(joinedload(Payslip.employee)).filter(Payslip.id.in_(ids)).all()
        if len(payslips) != len(ids):
            raise ValueError("بعض القسائم المختارة غير موجودة")
        run_ids = {p.run_id for p in payslips}
        if len(run_ids) > 1:
            raise ValueError("مينفعش تصرف قسائم من أكتر من دورة رواتب في نفس السند")
        run = s.get(PayrollRun, run_ids.pop())
        if run.state != "posted":
            raise ValueError("لازم ترحّل الدورة الأول قبل ما تصرف أي موظف فيها")
        unpaid = [p for p in payslips if not p.paid_at]
        if not unpaid:
            raise ValueError("كل القسائم المختارة اتصرفت بالفعل")
        total_net = sum(p.net_salary for p in unpaid)
        if total_net <= 0:
            raise ValueError("صافي المبلغ المختار صفر - مفيش حاجة تتصرف")
        cfg = s.get(AccountingSettings, 1)
        if not cfg.salaries_payable_account_id:
            raise ValueError("إعداد حساب الرواتب المستحقة ناقص - راجع الإعدادات المحاسبية")
        payable_account_id = cfg.salaries_payable_account_id
        branch_id, cost_center_id = run.branch_id, default_cost_center_id()
        run_id_val, run_number, run_month, run_year = run.id, run.number, run.month, run.year
        names = [p.employee.name if p.employee else f"#{p.employee_id}" for p in unpaid]
        unpaid_ids = [p.id for p in unpaid]

    payment_date = payment_date or datetime.datetime.now()
    label = names[0] if len(names) == 1 else f"{len(names)} موظف"
    with get_session() as s:
        pay = Payment(number=_next_payment_number(s, "PY-"), date=payment_date, payment_type="payment",
                      branch_id=branch_id, cost_center_id=cost_center_id, partner_type="payroll", partner_id=run_id_val,
                      amount=round(total_net, 2), account_id=int(cash_account_id),
                      reference=reference or run_number, notes=f"صرف صافي راتب {label} - دورة {run_month}/{run_year} ({pm.name})")
        s.add(pay); s.flush(); pid = pay.id; s.commit()

    jid = create_journal_entry(
        [{"account_id": payable_account_id, "debit": round(total_net, 2)}, {"account_id": int(cash_account_id), "credit": round(total_net, 2)}],
        reference=reference or run_number, description=f"صرف صافي راتب {label} - دورة {run_month}/{run_year} - سند {pay.number}",
        source_type="payroll_payment", source_id=run_id_val, entry_date=payment_date, branch_id=branch_id, cost_center_id=cost_center_id,
    )
    with get_session() as s:
        p = s.get(Payment, pid); p.journal_entry_id = jid
        for pid_slip in unpaid_ids:
            slip = s.get(Payslip, pid_slip)
            slip.paid_at = payment_date; slip.payment_id = pid
        run = s.get(PayrollRun, run_id_val)
        all_paid = all(sl.paid_at for sl in s.query(Payslip).filter(Payslip.run_id == run_id_val).all())
        run.paid_at = payment_date if all_paid else None
        run.payment_id = pid
        s.commit()
    return {"payment_id": pid, "payment_number": pay.number, "journal_entry_id": jid, "amount": round(total_net, 2),
            "employee_count": len(unpaid), "employee_names": names}


def pay_payroll_run(run_id, payment_method_id, payment_date=None, reference=""):
    """يصرف صافي رواتب كل الموظفين اللي لسه ما اتصرفوش في الدورة دفعة واحدة."""
    with get_session() as s:
        run = s.get(PayrollRun, int(run_id))
        if not run:
            raise ValueError("الدورة غير موجودة")
        if run.state != "posted":
            raise ValueError("لازم ترحّل الدورة الأول قبل ما تصرفها")
        unpaid_ids = [p.id for p in s.query(Payslip).filter(Payslip.run_id == run.id, Payslip.paid_at.is_(None)).all()]
    if not unpaid_ids:
        raise ValueError("كل موظفي الدورة اتصرفوا بالفعل")
    return pay_payslips(unpaid_ids, payment_method_id, payment_date=payment_date, reference=reference)


def unpay_payroll_run(run_id):
    """يتراجع عن كل عمليات صرف دورة رواتب (بيلغي كل سنداتها السارية)."""
    require_action("payroll", "post")
    payments = [p for p in list_payroll_run_payments(run_id) if not p.voided]
    if not payments:
        raise ValueError("الدورة دي مش متصرفة أصلاً")
    for p in payments:
        void_payment(p.id)


def set_journal_entry_draft_by_source(entry_id):
    """نسخة من set_journal_entry_draft بس بتسمح بمصادر تانية غير manual
    (مستخدمة داخلياً بس من عمليات مضبوطة زي إعادة فتح الرواتب)."""
    with get_session() as s:
        e = s.get(JournalEntry, entry_id)
        if e:
            e.posted = False
            s.commit()


def payroll_summary_report(year=None):
    """تقرير سريع: إجمالي الرواتب المدفوعة لكل شهر في السنة المحددة."""
    with get_session() as s:
        q = s.query(PayrollRun)
        if year:
            q = q.filter(PayrollRun.year == int(year))
        runs = q.order_by(PayrollRun.year, PayrollRun.month).all()
        out = []
        for r in runs:
            payslips = s.query(Payslip).filter(Payslip.run_id == r.id).all()
            out.append({
                "number": r.number, "month": r.month, "year": r.year,
                "state": "مرحّلة" if r.state == "posted" else "مسودة",
                "employees_count": len(payslips),
                "total_gross": round(sum(p.gross_salary for p in payslips), 2),
                "total_deductions": round(sum(p.total_deductions for p in payslips), 2),
                "total_net": round(sum(p.net_salary for p in payslips), 2),
            })
        return out


# ======================================================================
# نقاط البيع (POS)
# ======================================================================
def create_pos_sale(customer_id, items, payment_method_id=None, location_id=None,
                     branch_id=None, cost_center_id=None, discount=0.0, terminal_id=None, payments=None, discount_spec=None,
                     client_uuid=None, sale_time=None, credit_approval_id=None):
    """
    بيع سريع من شاشة نقاط البيع: نفس منطق create_sales_invoice بالكامل
    (تنزيل مخزون + قيد محاسبي تلقائي) + علامة is_pos + محاولة إرسال
    للزكاة لو الخاصية مفعّلة + توليد QR للفاتورة الضريبية فوراً.

    طريقة الدفع (payment_method_id) بتحدد حساب الاستحقاق في القيد تلقائيًا
    من جدول طرق الدفع: طريقة عادية (نقدي/بطاقة/تحويل...) بتترحّل على
    حسابها المرتبط بدل الذمم المدينة، وطريقة "آجل" (is_credit) بتفضل دين
    على حساب العميل (الذمم المدينة) زي أي فاتورة عادية.
    """
    import uuid as _uuid
    from .zatca import zatca_qr_png_base64, build_zatca_base64, send_invoice_to_zatca

    if client_uuid:      # بيع اتسجّل بدون اتصال: لو اتزامن قبل كده (حتى لو الرد ضاع) نرجّع نفس الفاتورة بدل ما نكرر
        with get_session() as s:
            ex = s.query(SalesInvoice).filter(SalesInvoice.client_uuid == str(client_uuid)).first()
            if ex:
                return {'invoice_id': ex.id, 'qr_png_base64': None, 'zatca': {'status': ex.zatca_status or 'disabled', 'message': ex.zatca_response or ''},
                        'discount': float(ex.promo_discount or 0), 'loyalty': {'earned': 0, 'redeemed': 0, 'balance': 0}, 'duplicate': True}

    # ---- سطور السداد: payments = [{payment_method_id, amount, tendered?, reference?}] (أو طريقة واحدة بالإجمالي)
    plines = [dict(p_) for p_ in (payments or [])]
    if not plines:
        if not payment_method_id:
            raise ValueError("اختر طريقة الدفع")
        plines = [{"payment_method_id": int(payment_method_id), "amount": None}]
    seen_pm = set()
    for pl in plines:
        if not pl.get("payment_method_id"):
            raise ValueError("سطر سداد من غير طريقة دفع")
        if int(pl["payment_method_id"]) in seen_pm:
            raise ValueError("طريقة الدفع متكررة - اجمع المبلغ في سطر واحد")
        seen_pm.add(int(pl["payment_method_id"]))
    promo = None
    if discount_spec:
        from . import promotions as _promo
        promo = _promo.resolve(_promo.items_total(items), discount_spec)
        if promo["amount"] > 0:
            items = _promo.allocate(items, promo["amount"])     # الخصم على أسطر الفاتورة (قبل الضريبة) عشان الضريبة والزكاة تطلع صح
        else:
            promo = None
    expected_total = 0.0
    for it in items:
        expected_total += _compute_line_total(float(it["quantity"]), float(it["unit_price"]), float(it.get("discount", 0)), float(it.get("tax_rate", 15)))[2]
    expected_total = round(max(0.0, expected_total - float(discount or 0)), 2)
    if len(plines) == 1 and plines[0].get("amount") is None:
        plines[0]["amount"] = expected_total
    terminal = None
    if terminal_id:
        # بيع من ماكينة: بنتحقق إنها شغّالة والمستخدم مسموح له بيها وطريقة الدفع من طرقها، وبناخد الفرع ومركز التكلفة والمخزن منها
        terminal = get_pos_terminal(terminal_id)
        if not terminal:
            raise ValueError("الماكينة غير موجودة")
        if not terminal["is_active"]:
            raise ValueError(f'الماكينة «{terminal["name"]}» موقوفة')
        if not user_can_use_terminal(terminal):
            raise PermissionError(f'الماكينة «{terminal["name"]}» مخصصة لمستخدم تاني')
        _allowed_ids = [m["id"] for m in terminal["payment_methods"]]
        for _pl in plines:
            if int(_pl["payment_method_id"]) not in _allowed_ids:
                raise ValueError(f'طريقة الدفع دي مش مسموحة على ماكينة «{terminal["name"]}»')
        location_id = location_id or terminal["location_id"]
        branch_id = branch_id or terminal["branch_id"]
        cost_center_id = cost_center_id or terminal["cost_center_id"]
        session = get_open_pos_session(terminal["id"])
        if not session:
            raise ValueError(f'مفيش جلسة مفتوحة على الماكينة «{terminal["name"]}» - افتح جلسة الأول')
        me = current_user() or {}
        if me.get("role") != "admin" and session["opened_by"] != me.get("username"):
            raise PermissionError(f'الجلسة {session["number"]} مفتوحة بواسطة {session["opened_by_name"]} - مينفعش تبيع عليها')
    # تحقق السطور وتجهيز الحسابات
    splits, resolved = [], []
    for pl in plines:
        pm = get_payment_method(pl["payment_method_id"])
        if not pm:
            raise ValueError("طريقة الدفع غير موجودة")
        if not pm.is_active:
            raise ValueError(f'طريقة الدفع "{pm.name}" موقوفة')
        amt = round(float(pl.get("amount") or 0), 2)
        if amt < 0:
            raise ValueError("مبلغ السداد لا يمكن أن يكون سالبًا")
        if not pm.is_credit and not pm.account_id:
            raise ValueError(f'طريقة الدفع "{pm.name}" مالهاش حساب مرتبط - اضبطها من شاشة طرق الدفع')
        tendered = pl.get("tendered")
        tendered = round(float(tendered), 2) if tendered not in (None, "") else None
        if tendered is not None and tendered + 1e-9 < amt:
            raise ValueError(f'المبلغ المستلم ({tendered:g}) أقل من المطلوب ({amt:g}) في «{pm.name}»')
        if tendered is not None and tendered > amt + 1e-9 and not pm_is_cash(pm):
            raise ValueError(f'الباقي مسموح بس في الدفع النقدي - «{pm.name}» لازم يكون المبلغ بالظبط')
        if amt > 0:
            resolved.append((pm, amt, tendered, (pl.get("reference") or "").strip()))
            splits.append({"account_id": None if pm.is_credit else pm.account_id, "amount": amt})
    if not resolved:
        raise ValueError("أدخل مبلغ السداد")
    if abs(sum(a for _, a, _, _ in resolved) - expected_total) > 0.01:
        raise ValueError(f'مجموع السداد ({sum(a for _, a, _, _ in resolved):,.2f}) لا يساوي إجمالي الفاتورة ({expected_total:,.2f})')
    if any(pm.is_credit for pm, _, _, _ in resolved) and (not customer_id):
        raise ValueError("السداد الآجل محتاج عميل")
    override_account = None
    pm = resolved[0][0]
    use_splits = len(resolved) > 1

    _credit_part = sum(a for pm_, a, _, _ in resolved if pm_.is_credit)
    if _credit_part > 0.005:         # حد الائتمان قبل أي خصم من بطاقة
        from . import credit as _credit_mod
        _credit_mod.check_sale(customer_id, _credit_part, approval_id=credit_approval_id)

    # ---- طرق الدفع المربوطة بمزوّد بنكي: بنتحقق من العملية (جهاز/API) قبل إصدار الفاتورة
    from . import banking as _bk
    charged = []
    for (pm_, amt_, tend_, ref_) in resolved:
        if getattr(pm_, "provider_id", None) and not pm_.is_credit and not pm_is_cash(pm_):
            try:
                res_ = _bk.charge_card(pm_.provider_id, amt_, manual_reference=ref_, payment_method_id=pm_.id, customer_id=customer_id)
            except Exception:
                for c_ in charged:
                    _bk.mark_orphaned(c_["transaction_id"], "عملية اتخصمت لكن الدفع التاني فشل - راجع الجهاز/البنك")
                raise
            charged.append(res_)
            for k_, r_ in enumerate(resolved):
                if r_[0].id == pm_.id:
                    resolved[k_] = (pm_, amt_, tend_, res_["reference"] or ref_)
    try:
        invoice_id = create_sales_invoice(
        customer_id, items, notes='POS', discount=discount,
        location_id=location_id, branch_id=branch_id, cost_center_id=cost_center_id,
        receivable_override_account_id=(None if (use_splits or pm.is_credit) else pm.account_id),
        payment_splits=(splits if use_splits else None), invoice_date=sale_time, _credit_checked=True, _zatca=False,
        )
    except Exception as ex_:
        for c_ in charged:
            _bk.mark_orphaned(c_["transaction_id"], f"اتخصمت من العميل لكن الفاتورة فشلت ({ex_}) - لازم تتراجع من الجهاز/البنك")
        raise
    for c_ in charged:
        _bk.attach_invoice(c_["transaction_id"], invoice_id)

    settings = get_company_settings()
    invoice = get_sales_invoice(invoice_id)
    iso = invoice.date.strftime('%Y-%m-%dT%H:%M:%SZ')
    qr_b64 = build_zatca_base64(settings.name or '-', settings.vat_number or '-', iso, invoice.total, invoice.tax_total)
    qr_png = zatca_qr_png_base64(settings.name or '-', settings.vat_number or '-', iso, invoice.total, invoice.tax_total)
    invoice_uuid = str(_uuid.uuid4())

    zatca_result = {'status': 'disabled', 'message': 'خاصية الربط مع الزكاة غير مفعّلة.'}
    from . import zatca_p2 as _zp2
    from . import nodesync as _ns
    if settings.zatca_enabled and not _zp2.is_enabled() and not _ns.is_node():
        zatca_result = send_invoice_to_zatca(settings, invoice.number, invoice_uuid, qr_b64, invoice.total, invoice.tax_total)

    with get_session() as s:
        inv = s.get(SalesInvoice, invoice_id)
        inv.is_pos = True
        if client_uuid:
            inv.client_uuid = str(client_uuid)
        if terminal:
            inv.pos_terminal_id = terminal["id"]; inv.cashier_employee_id = terminal["employee_id"]; inv.pos_session_id = session["id"]
        inv.payment_method = " + ".join(p_.name for p_, _, _, _ in resolved)
        from .db import SalesInvoicePayment
        for p_, a_, t_, r_ in resolved:
            s.add(SalesInvoicePayment(invoice_id=invoice_id, payment_method_id=p_.id, method_name=p_.name, amount=a_, is_cash=bool(pm_is_cash(p_)), is_credit=bool(p_.is_credit), tendered=t_, reference=r_))
        inv.zatca_status = zatca_result['status']
        inv.zatca_response = zatca_result.get('message', '')
        s.commit()

    from . import zatca_p2 as _z2
    if _z2.is_enabled():
        _z2.issue_invoice(invoice_id)
        qr_png = _z2.qr_png_for_invoice(invoice_id) or qr_png
        with get_session() as s_:
            i_ = s_.get(SalesInvoice, invoice_id)
            zatca_result = {'status': i_.zatca_status or 'pending', 'message': i_.zatca_response or ''}
    if promo:
        _promo.record_use(invoice_id, promo)
    from . import loyalty as _loy
    try:
        loy = _loy.after_sale(invoice_id, customer_id, promo.get('points', 0) if promo else 0)
    except Exception:
        loy = {'earned': 0, 'redeemed': 0, 'balance': 0}
    try:                                    # إيصال واتساب/SMS للعميل (لو مفعّل وموافق) - فشله مايأثرش على البيع
        from . import notify as _notify
        _notify.send_receipt(invoice_id)
    except Exception:
        pass
    return {'invoice_id': invoice_id, 'qr_png_base64': qr_png, 'zatca': zatca_result, 'discount': promo['amount'] if promo else 0.0, 'loyalty': loy}


def create_pos_split_sale(parts, terminal_id=None):
    """تقسيم فاتورة كاشير على أكتر من عميل: parts = [{customer_id, items, payment_method_id | payments}]. بيطلع فاتورة POS مستقلة لكل عميل
    (فاتورة ضريبية باسمه ودفعه وحسابه). بيتحقق من كل الأجزاء قبل ما يسجّل أي حاجة."""
    if not parts or len(parts) < 2:
        raise ValueError("التقسيم محتاج عميلين على الأقل")
    totals = {}
    for n, pt in enumerate(parts, 1):
        if not pt.get("customer_id"):
            raise ValueError(f"الجزء {n}: اختر العميل")
        if not pt.get("items"):
            raise ValueError(f"الجزء {n}: مفيش أصناف متوزعة على العميل ده")
        if not pt.get("payments") and not pt.get("payment_method_id"):
            raise ValueError(f"الجزء {n}: اختر طريقة الدفع")
        for it in pt["items"]:
            totals[int(it["product_id"])] = totals.get(int(it["product_id"]), 0.0) + float(it["quantity"])
    results = []
    for pt in parts:
        results.append(create_pos_sale(pt["customer_id"], pt["items"], payment_method_id=pt.get("payment_method_id"), payments=pt.get("payments"), terminal_id=terminal_id, discount=pt.get("discount", 0.0)))
    return results


# ---------------- ماكينات نقاط البيع ----------------
def _terminal_dict(t):
    return {"id": t.id, "code": t.code, "name": t.name, "is_active": bool(t.is_active), "branch_id": t.branch_id, "branch": t.branch.name if t.branch else "",
            "cost_center_id": t.cost_center_id, "cost_center": t.cost_center.name if t.cost_center else "", "location_id": t.location_id, "location": t.location.name if t.location else "",
            "employee_id": t.employee_id, "employee": t.employee.name if t.employee else "", "assigned_username": t.assigned_username or "",
            "default_customer_id": t.default_customer_id, "default_customer": t.default_customer.name if t.default_customer else "", "lock_customer": bool(t.lock_customer),
            "default_payment_method_id": t.default_payment_method_id, "receipt_footer": t.receipt_footer or "", "notes": t.notes or "",
            "payment_methods": [{"id": m.id, "name": m.name, "is_credit": bool(m.is_credit)} for m in t.payment_methods if m.is_active]}


def _terminal_load():
    from .db import PosTerminal
    return (joinedload(PosTerminal.branch), joinedload(PosTerminal.cost_center), joinedload(PosTerminal.location), joinedload(PosTerminal.employee),
            joinedload(PosTerminal.default_customer), joinedload(PosTerminal.payment_methods))


def get_pos_terminal(terminal_id):
    from .db import PosTerminal
    with get_session() as s:
        t = s.query(PosTerminal).options(*_terminal_load()).filter(PosTerminal.id == int(terminal_id)).first()
        return _terminal_dict(t) if t else None


def list_pos_terminals(active_only=False):
    from .db import PosTerminal
    with get_session() as s:
        q = s.query(PosTerminal).options(*_terminal_load())
        if active_only:
            q = q.filter(PosTerminal.is_active.is_(True))
        return [_terminal_dict(t) for t in q.order_by(PosTerminal.code).all()]


def user_can_use_terminal(terminal, user=None):
    """الأدمن بيستخدم أي ماكينة؛ غيره بس الماكينة اللي مخصصة له أو اللي مش مخصصة لحد."""
    user = user or current_user() or {}
    return user.get("role") == "admin" or not terminal.get("assigned_username") or terminal["assigned_username"] == user.get("username")


def pos_terminals_for_current_user():
    """الماكينات الشغّالة اللي المستخدم الحالي يقدر يفتحها (المخصصة له الأول)."""
    me = (current_user() or {}).get("username")
    rows = [t for t in list_pos_terminals(active_only=True) if user_can_use_terminal(t)]
    return sorted(rows, key=lambda t: (t["assigned_username"] != me, t["code"]))


def _check_terminal_fields(s, code, name, branch_id, cost_center_id, location_id, employee_id, assigned_username, default_customer_id, payment_method_ids, default_payment_method_id, exclude_id=None):
    from .db import PosTerminal
    code = (code or "").strip(); name = (name or "").strip()
    if not code or not name:
        raise ValueError("كود واسم الماكينة مطلوبين")
    q = s.query(PosTerminal).filter(PosTerminal.code == code)
    if exclude_id:
        q = q.filter(PosTerminal.id != int(exclude_id))
    if q.first():
        raise ValueError("كود الماكينة موجود قبل كده")
    pm_ids = sorted({int(x) for x in (payment_method_ids or [])})
    if not pm_ids:
        raise ValueError("اختر طريقة دفع واحدة على الأقل للماكينة")
    pms = s.query(PaymentMethod).filter(PaymentMethod.id.in_(pm_ids)).all()
    if len(pms) != len(pm_ids):
        raise ValueError("فيه طريقة دفع غير موجودة")
    if default_payment_method_id and int(default_payment_method_id) not in pm_ids:
        raise ValueError("طريقة الدفع الافتراضية لازم تكون من الطرق المسموحة للماكينة")
    if location_id and branch_id:
        loc = s.get(Location, int(location_id))
        if loc and loc.branch_id and int(loc.branch_id) != int(branch_id):
            raise ValueError("المخزن المختار مش تابع للفرع المختار")
    if employee_id and not s.get(Employee, int(employee_id)):
        raise ValueError("الموظف غير موجود")
    if assigned_username:
        u = s.query(User).filter(User.username == assigned_username, User.is_active.is_(True)).first()
        if not u:
            raise ValueError("المستخدم غير موجود أو غير نشط")
        if branch_id and u.role != "admin" and not allowed_branch(branch_id, u):       # لازم المستخدم يكون مسموح له بفرع الماكينة وإلا البيع هيترفض
            raise ValueError(f"المستخدم «{u.full_name or u.username}» مش مسموح له بفرع الماكينة - ادّيله صلاحية الفرع من شاشة المستخدمين الأول")
        if cost_center_id and u.role != "admin" and not allowed_cost_center(cost_center_id, u):
            raise ValueError(f"المستخدم «{u.full_name or u.username}» مش مسموح له بمركز تكلفة الماكينة - ادّيله الصلاحية من شاشة المستخدمين الأول")
    if default_customer_id and not s.get(Customer, int(default_customer_id)):
        raise ValueError("العميل الافتراضي غير موجود")
    return code, name, pms


def create_pos_terminal(code, name, branch_id=None, cost_center_id=None, location_id=None, employee_id=None, assigned_username=None, default_customer_id=None,
                        lock_customer=False, payment_method_ids=(), default_payment_method_id=None, receipt_footer="", notes="", is_active=True):
    require_action("pos_terminals", "create")
    from .db import PosTerminal
    with get_session() as s:
        code, name, pms = _check_terminal_fields(s, code, name, branch_id, cost_center_id, location_id, employee_id, assigned_username, default_customer_id, payment_method_ids, default_payment_method_id)
        t = PosTerminal(code=code, name=name, is_active=bool(is_active), branch_id=int(branch_id) if branch_id else None, cost_center_id=int(cost_center_id) if cost_center_id else None,
                        location_id=int(location_id) if location_id else None, employee_id=int(employee_id) if employee_id else None, assigned_username=(assigned_username or None),
                        default_customer_id=int(default_customer_id) if default_customer_id else None, lock_customer=bool(lock_customer),
                        default_payment_method_id=int(default_payment_method_id) if default_payment_method_id else None, receipt_footer=(receipt_footer or "").strip(), notes=(notes or "").strip())
        t.payment_methods = pms
        s.add(t); s.commit(); s.refresh(t)
        return t.id


def update_pos_terminal(terminal_id, code, name, branch_id=None, cost_center_id=None, location_id=None, employee_id=None, assigned_username=None, default_customer_id=None,
                        lock_customer=False, payment_method_ids=(), default_payment_method_id=None, receipt_footer="", notes="", is_active=True):
    require_action("pos_terminals", "edit")
    from .db import PosTerminal
    with get_session() as s:
        t = s.get(PosTerminal, int(terminal_id))
        if not t:
            raise ValueError("الماكينة غير موجودة")
        code, name, pms = _check_terminal_fields(s, code, name, branch_id, cost_center_id, location_id, employee_id, assigned_username, default_customer_id, payment_method_ids, default_payment_method_id, exclude_id=t.id)
        t.code, t.name, t.is_active = code, name, bool(is_active)
        t.branch_id = int(branch_id) if branch_id else None; t.cost_center_id = int(cost_center_id) if cost_center_id else None; t.location_id = int(location_id) if location_id else None
        t.employee_id = int(employee_id) if employee_id else None; t.assigned_username = assigned_username or None
        t.default_customer_id = int(default_customer_id) if default_customer_id else None; t.lock_customer = bool(lock_customer)
        t.default_payment_method_id = int(default_payment_method_id) if default_payment_method_id else None
        t.receipt_footer = (receipt_footer or "").strip(); t.notes = (notes or "").strip()
        t.payment_methods = pms
        s.commit()


def delete_pos_terminal(terminal_id):
    """حذف الماكينة لو ما اتباعش عليها؛ لو عليها فواتير لازم توقفها بدل الحذف."""
    require_action("pos_terminals", "delete")
    from .db import PosTerminal
    with get_session() as s:
        t = s.get(PosTerminal, int(terminal_id))
        if not t:
            raise ValueError("الماكينة غير موجودة")
        if s.query(SalesInvoice).filter(SalesInvoice.pos_terminal_id == t.id).count():
            raise ValueError("اتباع على الماكينة دي فواتير - أوقفها بدل ما تحذفها")
        s.delete(t); s.commit()


# ---------------- مرتجعات المبيعات (إشعار دائن): بديل الحذف/الإلغاء النهائي ----------------
def can_return(user=None):
    """مين يقدر يعمل مرتجع: الأدمن أو أي مستخدم عنده صلاحية "مرتجعات المبيعات" (إنشاء)."""
    try:
        require_action("pos_returns", "create")
        return True
    except PermissionError:
        return False


def get_invoice_for_return(invoice_id):
    from .db import SalesReturnItem as _SRI, SalesReturn as _SR      # noqa
    """بيانات فاتورة للمعاينة والمرتجع: الأصناف بكمياتها وما اترجّع منها وما تبقى، وسجل المرتجعات السابقة."""
    from .db import SalesReturn, SalesReturnItem, PosSession, PosTerminal
    with get_session() as s:
        inv = (s.query(SalesInvoice).options(joinedload(SalesInvoice.customer), joinedload(SalesInvoice.items).joinedload(SalesInvoiceItem.product), joinedload(SalesInvoice.items).joinedload(SalesInvoiceItem.unit))
               .filter(SalesInvoice.id == int(invoice_id)).first())
        if not inv:
            raise ValueError("الفاتورة غير موجودة")
        returned = {iid: float(q or 0) for iid, q in s.query(SalesReturnItem.invoice_item_id, func.sum(SalesReturnItem.quantity)).join(SalesReturn, SalesReturn.id == SalesReturnItem.return_id)
                    .filter(SalesReturn.invoice_id == inv.id).group_by(SalesReturnItem.invoice_item_id).all()}
        rets = s.query(SalesReturn).filter(SalesReturn.invoice_id == inv.id).order_by(SalesReturn.date).all()
        ses = s.get(PosSession, inv.pos_session_id) if inv.pos_session_id else None
        term = s.get(PosTerminal, inv.pos_terminal_id) if inv.pos_terminal_id else None
        items = []
        for it in inv.items:
            rq = returned.get(it.id, 0.0)
            items.append({"id": it.id, "product_id": it.product_id, "sku": it.product.sku, "name": it.product.name, "unit": it.unit.name if it.unit else (it.product.unit or ""), "unit_id": it.unit_id,
                          "qty": float(it.quantity), "unit_price": float(it.unit_price), "discount": float(it.discount or 0), "tax_rate": float(it.tax_rate or 0), "line_total": float(it.line_total or 0),
                          "returned_qty": rq, "remaining_qty": max(0.0, float(it.quantity) - rq)})
        returned_total = sum(float(r.total or 0) for r in rets)
        remaining = sum(i["remaining_qty"] for i in items)
        status = "none" if not rets else ("full" if remaining <= 1e-9 else "partial")
        return {"id": inv.id, "number": inv.number, "date": inv.date, "customer": inv.customer.name if inv.customer else "-", "customer_id": inv.customer_id, "payment_method": inv.payment_method or "-", "payments": get_invoice_payments(inv.id),
                "is_pos": bool(inv.is_pos), "voided": bool(inv.voided), "terminal": f"{term.code} - {term.name}" if term else "", "session": ses.number if ses else "", "session_id": inv.pos_session_id,
                "subtotal": float(inv.subtotal or 0), "tax": float(inv.tax_total or 0), "total": float(inv.total or 0), "discount": float(getattr(inv, "discount", 0) or 0), "items": items,
                "returns": [{"id": r.id, "number": r.number, "date": r.date, "total": float(r.total or 0), "reason": r.reason or "", "refund_method": r.refund_method or "", "is_full": bool(r.is_full),
                             "processed_by": r.processed_by or ""} for r in rets], "returned_total": returned_total, "status": status}


def get_invoice_payments(invoice_id):
    """سطور سداد الفاتورة [{method_id, name, amount, is_cash, is_credit, tendered, change, reference}]؛ للفواتير القديمة (قبل السداد المتعدد) بتطلع سطر واحد بإجمالي الفاتورة."""
    from .db import SalesInvoicePayment
    with get_session() as s:
        rows = s.query(SalesInvoicePayment).filter(SalesInvoicePayment.invoice_id == int(invoice_id)).order_by(SalesInvoicePayment.id).all()
        if rows:
            return [{"method_id": r.payment_method_id, "name": r.method_name or "-", "amount": float(r.amount or 0), "is_cash": bool(r.is_cash), "is_credit": bool(r.is_credit),
                     "tendered": r.tendered, "change": round(float(r.tendered) - float(r.amount or 0), 2) if r.tendered is not None and r.tendered > (r.amount or 0) else 0.0, "reference": r.reference or ""} for r in rows]
        inv = s.get(SalesInvoice, int(invoice_id))
        if not inv:
            return []
        m = s.query(PaymentMethod).filter(PaymentMethod.name == (inv.payment_method or "")).first()
        return [{"method_id": m.id if m else None, "name": inv.payment_method or "-", "amount": float(inv.total or 0), "is_cash": pm_is_cash(m), "is_credit": bool(m.is_credit) if m else False,
                 "tendered": None, "change": 0.0, "reference": ""}]


def create_sales_return(invoice_id, lines, reason, refund_method_id=None, is_full=False):
    from .db import SalesReturn, SalesReturnItem
    """مرتجع على فاتورة مبيعات (كلي أو جزئي): lines = [{invoice_item_id, quantity}]. بيرجّع الكميات للمخزون (وفك الـ Kit) ويسجّل قيد عكسي
    (مبيعات + ضريبة + ردّ للعميل + مخزون/تكلفة). الفاتورة الأصلية بتفضل زي ما هي. الرد النقدي لفاتورة كاشير لازم تكون جلسة الماكينة مفتوحة."""
    require_action("pos_returns", "create")
    from .db import SalesReturn, SalesReturnItem
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("اكتب سبب المرتجع")
    if not lines:
        raise ValueError("اختر صنف واحد على الأقل للمرتجع")
    detail = get_invoice_for_return(invoice_id)
    if detail["voided"]:
        raise ValueError("الفاتورة ملغاة - مينفعش عليها مرتجع")
    by_id = {i["id"]: i for i in detail["items"]}
    chosen = {}
    for n, ln in enumerate(lines, 1):
        it = by_id.get(int(ln["invoice_item_id"]))
        if not it:
            raise ValueError(f"السطر {n}: البند مش من الفاتورة دي")
        qty = float(ln.get("quantity") or 0)
        if qty <= 0:
            raise ValueError(f"السطر {n}: كمية المرتجع لازم تكون أكبر من صفر")
        chosen[it["id"]] = chosen.get(it["id"], 0.0) + qty
    for iid, qty in chosen.items():
        if qty > by_id[iid]["remaining_qty"] + 1e-9:
            raise ValueError(f"«{by_id[iid]['name']}»: كمية المرتجع ({qty:g}) أكبر من المتبقي ({by_id[iid]['remaining_qty']:g})")
    # الأرقام: حصة الكمية المرتجعة من خصم السطر وإجماليه
    rows, sub_base, tax_total, lines_total = [], 0.0, 0.0, 0.0
    for iid, qty in chosen.items():
        it = by_id[iid]; ratio = qty / it["qty"]
        disc = it["discount"] * ratio; lt = it["line_total"] * ratio
        base = max(0.0, qty * it["unit_price"] - disc)
        rows.append({"it": it, "qty": qty, "discount": round(disc, 2), "line_total": round(lt, 2), "base": round(base, 2), "tax": round(lt - base, 2)})
        sub_base += base; tax_total += lt - base; lines_total += lt
    all_base = sum(max(0.0, i["qty"] * i["unit_price"] - i["discount"]) for i in detail["items"]) or 1.0
    inv_disc_share = round(detail["discount"] * (sub_base / all_base), 2) if detail["discount"] else 0.0
    refund_amount = round(lines_total - inv_disc_share, 2)
    # طريقة الرد: الافتراضي نفس طريقة دفع الفاتورة؛ الآجل بيتخصم من حساب العميل
    cfg = _accounting_settings()
    with get_session() as s:
        inv_obj = s.get(SalesInvoice, int(invoice_id))
        customer = s.get(Customer, inv_obj.customer_id) if inv_obj.customer_id else None
        if refund_method_id:
            pm = s.get(PaymentMethod, int(refund_method_id))
        else:
            pm = None
            pays = get_invoice_payments(int(invoice_id))
            paid = [p_ for p_ in pays if p_["method_id"] and not p_["is_credit"]]
            if len(pays) <= 1:
                pm = s.query(PaymentMethod).filter(PaymentMethod.name == (inv_obj.payment_method or "")).first()
            elif paid:
                # فاتورة بسداد متعدد: الرد الافتراضي على أول طريقة غير آجلة تكفي مبلغ المرتجع، وإلا الأكبر
                fit = [p_ for p_ in paid if p_["amount"] + 0.005 >= refund_amount]
                pick = fit[0] if fit else max(paid, key=lambda p_: p_["amount"])
                pm = s.get(PaymentMethod, int(pick["method_id"]))
        inv_number, inv_date_, branch_id, cost_center_id = inv_obj.number, inv_obj.date, inv_obj.branch_id, inv_obj.cost_center_id
        terminal_id, orig_session_id, is_pos, customer_id = inv_obj.pos_terminal_id, inv_obj.pos_session_id, bool(inv_obj.is_pos), inv_obj.customer_id
    if refund_method_id and (not pm or not pm.is_active):
        raise ValueError("طريقة الرد غير موجودة أو موقوفة")
    if pm is None or pm.is_credit:
        refund_account = (customer.account_id if customer and customer.account_id else None) or cfg.receivable_account_id
        refund_name, refund_cash = "على حساب العميل", False
    else:
        if not pm.account_id:
            raise ValueError(f'طريقة الرد "{pm.name}" مالهاش حساب مرتبط')
        refund_account, refund_name, refund_cash = pm.account_id, pm.name, pm_is_cash(pm)
    session = get_open_pos_session(terminal_id) if terminal_id else None
    if is_pos and terminal_id and refund_cash and not session:
        raise ValueError("الرد النقدي محتاج جلسة مفتوحة على الماكينة - افتح جلسة الأول أو اختار طريقة رد تانية")
    me = current_user() or {}
    with get_session() as s:
        ret = SalesReturn(number=_next_code(s, SalesReturn, "RET-"), date=datetime.datetime.now(), invoice_id=int(invoice_id), customer_id=customer_id, branch_id=branch_id, cost_center_id=cost_center_id,
                          pos_terminal_id=terminal_id, original_session_id=orig_session_id, pos_session_id=session["id"] if session else None, processed_by=me.get("username", ""), reason=reason,
                          refund_method=refund_name, refund_is_cash=bool(refund_cash), is_full=bool(is_full), subtotal=round(sub_base, 2), tax_total=round(tax_total, 2), total=refund_amount)
        s.add(ret); s.flush()
        for r in rows:
            it = r["it"]
            s.add(SalesReturnItem(return_id=ret.id, invoice_item_id=it["id"], product_id=it["product_id"], quantity=r["qty"], unit_id=it["unit_id"], unit_factor=1.0, unit_price=it["unit_price"],
                                  discount=r["discount"], tax_rate=it["tax_rate"], line_total=r["line_total"]))
        _kitchen_events_for_invoice(s, int(invoice_id), "item_return", [(r["it"]["product_id"], r["qty"], r["line_total"]) for r in rows], reason)
        s.commit()
        ret_id, ret_number, ret_date = ret.id, ret.number, ret.date
    try:
        from . import loyalty as _loy
        _loy.on_return(int(invoice_id), refund_amount, ret_number)
    except Exception:
        pass
    # ---- المخزون + تكلفة البضاعة
    location_id = _sales_invoice_location(inv_number) or default_location_id()
    ref = f"SALES:{inv_number}"
    cost_by_accounts = {}
    inv_obj_items = get_sales_invoice(int(invoice_id)).items
    items_by_id = {i.id: i for i in inv_obj_items}
    for r in rows:
        it = items_by_id[r["it"]["id"]]; prod = it.product; qty = r["qty"]
        if prod.product_type == "service":
            continue
        factor = float(it.unit_factor or 1)
        def scaled_lines(pid, base_qty):
            orig = _reference_batch_lines(ref, pid, "out")
            tot = sum(l["quantity"] for l in orig)
            if not orig or tot <= 0:
                return orig and [] or ([] if is_batch_tracked(get_product(pid)) else None)
            k = min(1.0, base_qty / tot)
            return [{**l, "quantity": l["quantity"] * k} for l in orig]
        if prod.product_type == "kit":
            cost = 0.0
            for comp in get_bom_explosion(prod.id, qty):
                bl = scaled_lines(comp["component_id"], comp["quantity"])
                create_stock_move(product_id=comp["component_id"], location_id=location_id, direction="in", quantity=comp["quantity"], unit_cost=comp["component"].cost_price or 0, reference=f"RET:{ret_number}",
                                  note=f"مرتجع {ret_number} على فاتورة {inv_number}", branch_id=branch_id, cost_center_id=cost_center_id, _internal=True, batch_lines=bl)
                if uses_batch_cost(comp["component"]) and bl:
                    cost += sum(l["quantity"] * l["unit_cost"] for l in bl)
                else:
                    cost += comp["quantity"] * (comp["component"].cost_price or 0)
        else:
            bl = scaled_lines(prod.id, qty * factor)
            create_stock_move(product_id=prod.id, location_id=location_id, direction="in", quantity=qty, unit_cost=float(it.unit_price), unit_id=it.unit_id, reference=f"RET:{ret_number}",
                              note=f"مرتجع {ret_number} على فاتورة {inv_number}", branch_id=branch_id, cost_center_id=cost_center_id, _internal=True, batch_lines=bl)
            cost = qty * float(prod.cost_price or 0)
            if uses_batch_cost(prod) and bl:
                cost = sum(l["quantity"] * l["unit_cost"] for l in bl)
        if cost > 0:
            ca = prod.cogs_account_id or cfg.cogs_account_id; ia = prod.inventory_account_id or cfg.inventory_account_id
            cost_by_accounts.setdefault((ia, ca), 0.0); cost_by_accounts[(ia, ca)] += cost
    # ---- القيد المحاسبي (عكس البيع)
    jl = []
    by_sales = {}
    for r in rows:
        prod = items_by_id[r["it"]["id"]].product
        aid = prod.sales_account_id or cfg.sales_account_id
        by_sales[aid] = by_sales.get(aid, 0.0) + r["base"]
    for aid, amount in by_sales.items():
        if amount:
            jl.append({"account_id": aid, "debit": round(amount, 2)})
    if round(tax_total, 2):
        jl.append({"account_id": cfg.vat_output_account_id, "debit": round(tax_total, 2)})
    if inv_disc_share:
        jl.append({"account_id": cfg.sales_discount_account_id, "credit": inv_disc_share})
    jl.append({"account_id": refund_account, "credit": refund_amount})
    for (ia, ca), cost in cost_by_accounts.items():
        jl.append({"account_id": ia, "debit": round(cost, 2)}); jl.append({"account_id": ca, "credit": round(cost, 2)})
    create_journal_entry(jl, reference=ret_number, description=f"مرتجع مبيعات {ret_number} على فاتورة {inv_number}", source_type="sales_return", source_id=ret_id,
                         entry_date=ret_date, branch_id=branch_id, cost_center_id=cost_center_id)
    from . import zatca_p2 as _z2
    _z2.issue_return(ret_id)                 # إشعار دائن إلكتروني (لو الفوترة الإلكترونية مفعّلة)
    return ret_id


def create_full_sales_return(invoice_id, reason, refund_method_id=None):
    """مرتجع كامل لباقي الفاتورة (كل الكميات اللي لسه ماتردّتش)."""
    d = get_invoice_for_return(invoice_id)
    lines = [{"invoice_item_id": i["id"], "quantity": i["remaining_qty"]} for i in d["items"] if i["remaining_qty"] > 1e-9]
    if not lines:
        raise ValueError("الفاتورة اترجّعت بالكامل قبل كده")
    return create_sales_return(invoice_id, lines, reason, refund_method_id, is_full=True)


def get_sales_return(return_id):
    from .db import SalesReturn, SalesReturnItem
    with get_session() as s:
        r = (s.query(SalesReturn).options(joinedload(SalesReturn.customer), joinedload(SalesReturn.invoice), joinedload(SalesReturn.items).joinedload(SalesReturnItem.product), joinedload(SalesReturn.items).joinedload(SalesReturnItem.unit))
             .filter(SalesReturn.id == int(return_id)).first())
        if not r:
            raise ValueError("المرتجع غير موجود")
        return {"id": r.id, "number": r.number, "date": r.date, "invoice_number": r.invoice.number if r.invoice else "-", "customer": r.customer.name if r.customer else "-", "reason": r.reason or "",
                "refund_method": r.refund_method or "", "processed_by": r.processed_by, "processed_by_name": _user_display(r.processed_by), "is_full": bool(r.is_full), "subtotal": float(r.subtotal or 0),
                "tax": float(r.tax_total or 0), "total": float(r.total or 0),
                "items": [{"sku": i.product.sku, "name": i.product.name, "unit": i.unit.name if i.unit else (i.product.unit or ""), "qty": float(i.quantity), "unit_price": float(i.unit_price),
                           "tax_rate": float(i.tax_rate or 0), "line_total": float(i.line_total or 0)} for i in r.items]}


def print_sales_return(return_id):
    """PDF مرتجع (إشعار دائن) للطباعة."""
    from .report_export import export_voucher_pdf
    d = get_sales_return(return_id)
    doc = {"title": "إشعار دائن - مرتجع مبيعات", "number": d["number"], "date": d["date"],
           "fields": [("على الفاتورة", d["invoice_number"]), ("العميل", d["customer"]), ("طريقة الرد", d["refund_method"]), ("بواسطة", d["processed_by_name"]), ("السبب", d["reason"]), ("النوع", "مرتجع كامل" if d["is_full"] else "مرتجع جزئي")],
           "table": {"caption": "الأصناف المرتجعة", "headers": ["الصنف", "الوحدة", "الكمية", "سعر الوحدة", "الإجمالي"], "rows": [[f"{i['sku']} - {i['name']}", i["unit"], f"{i['qty']:g}", i["unit_price"], i["line_total"]] for i in d["items"]],
                     "col_weights": [4, 1.2, 1.2, 1.8, 1.8]},
           "totals": [("قبل الضريبة", d["subtotal"]), ("الضريبة", d["tax"]), ("إجمالي المرتجع", d["total"])]}
    return export_voucher_pdf(doc, os.path.join(APP_DIR, "exports"), prefix="return")


# ---------------- جلسات نقاط البيع (الورديات) ----------------
def _user_display(username):
    with get_session() as s:
        u = s.query(User).filter(User.username == username).first()
    return (u.full_name or u.username) if u else (username or "")


def _session_dict(ses):
    return {"id": ses.id, "number": ses.number, "terminal_id": ses.terminal_id, "terminal": f"{ses.terminal.code} - {ses.terminal.name}" if ses.terminal else "",
            "employee_id": ses.employee_id, "employee": ses.employee.name if ses.employee else "", "opened_by": ses.opened_by, "opened_by_name": _user_display(ses.opened_by),
            "opened_at": ses.opened_at, "opening_cash": float(ses.opening_cash or 0), "notes": ses.notes or "", "state": ses.state,
            "closed_by": ses.closed_by, "closed_at": ses.closed_at, "expected_cash": ses.expected_cash, "counted_cash": ses.counted_cash, "difference": ses.difference, "close_notes": ses.close_notes or ""}


def get_open_pos_session(terminal_id):
    from .db import PosSession
    with get_session() as s:
        ses = (s.query(PosSession).options(joinedload(PosSession.terminal), joinedload(PosSession.employee))
               .filter(PosSession.terminal_id == int(terminal_id), PosSession.state == "open").first())
        return _session_dict(ses) if ses else None


def open_pos_session(terminal_id, opening_cash=0.0, notes=""):
    """فتح جلسة جديدة للماكينة بعهدة افتتاحية. جلسة واحدة مفتوحة بس لكل ماكينة، والمستخدم لازم يكون مسموح له بالماكينة."""
    require_action("pos_sessions", "create")
    from .db import PosSession
    terminal = get_pos_terminal(terminal_id)
    if not terminal:
        raise ValueError("الماكينة غير موجودة")
    if not terminal["is_active"]:
        raise ValueError(f'الماكينة «{terminal["name"]}» موقوفة')
    if not user_can_use_terminal(terminal):
        raise PermissionError(f'الماكينة «{terminal["name"]}» مخصصة لمستخدم تاني')
    try:
        cash = float(opening_cash or 0)
    except (TypeError, ValueError):
        raise ValueError("العهدة الافتتاحية لازم تكون رقم")
    if cash < 0:
        raise ValueError("العهدة الافتتاحية لا يمكن أن تكون سالبة")
    existing = get_open_pos_session(terminal_id)
    if existing:
        raise ValueError(f'الماكينة عليها جلسة مفتوحة ({existing["number"]} بواسطة {existing["opened_by_name"]}) - اقفلها الأول')
    with get_session() as s:
        ses = PosSession(number=_next_code(s, PosSession, "SES-"), terminal_id=int(terminal_id), employee_id=terminal["employee_id"], opened_by=(current_user() or {}).get("username", ""),
                         opened_at=datetime.datetime.now(), opening_cash=cash, notes=(notes or "").strip(), state="open")
        s.add(ses); s.commit(); s.refresh(ses)
        return ses.id


def pos_session_report(session_id):
    """تقرير الجلسة: بياناتها + إجماليات الفواتير (غير الملغاة) + المرتجعات (على فواتير الجلسة وما اتصرف من درجها) + إجمالي كل طريقة دفع
    + النقدية المتوقعة (العهدة + المبيعات النقدية - المرتجعات المردودة نقدًا من درج الجلسة) + مبيعات الأصناف (بالمرتجع والصافي) + قايمة الفواتير."""
    from .db import PosSession, SalesReturn, SalesReturnItem
    with get_session() as s:
        ses = s.query(PosSession).options(joinedload(PosSession.terminal), joinedload(PosSession.employee)).filter(PosSession.id == int(session_id)).first()
        if not ses:
            raise ValueError("الجلسة غير موجودة")
        base = _session_dict(ses)
        invs = (s.query(SalesInvoice).options(joinedload(SalesInvoice.customer), joinedload(SalesInvoice.items).joinedload(SalesInvoiceItem.product).joinedload(Product.category))
                .filter(SalesInvoice.pos_session_id == ses.id).order_by(SalesInvoice.date).all())
        methods = {m.name: m for m in s.query(PaymentMethod).all()}
        rets = (s.query(SalesReturn).options(joinedload(SalesReturn.customer), joinedload(SalesReturn.invoice), joinedload(SalesReturn.items).joinedload(SalesReturnItem.product).joinedload(Product.category))
                .filter((SalesReturn.original_session_id == ses.id) | (SalesReturn.pos_session_id == ses.id)).order_by(SalesReturn.date).all())
        from .db import SalesInvoicePayment
        pays_by_inv = {}
        for pr in s.query(SalesInvoicePayment).filter(SalesInvoicePayment.invoice_id.in_([i.id for i in invs] or [0])).order_by(SalesInvoicePayment.id).all():
            pays_by_inv.setdefault(pr.invoice_id, []).append({"name": pr.method_name or "-", "amount": float(pr.amount or 0), "is_cash": bool(pr.is_cash)})
        returned_by_invoice = {}
        for r in rets:
            if r.original_session_id == ses.id:
                returned_by_invoice[r.invoice_id] = returned_by_invoice.get(r.invoice_id, 0.0) + float(r.total or 0)
        invoices, by_pm, by_item = [], {}, {}
        tot = {"count": 0, "subtotal": 0.0, "tax": 0.0, "total": 0.0, "voided_count": 0, "voided_total": 0.0}
        for inv in invs:
            rt = returned_by_invoice.get(inv.id, 0.0)
            status = "none" if rt <= 0.005 else ("full" if rt >= float(inv.total or 0) - 0.005 else "partial")
            invoices.append({"id": inv.id, "number": inv.number, "date": inv.date, "customer": inv.customer.name if inv.customer else "-", "payment_method": inv.payment_method or "-",
                             "subtotal": float(inv.subtotal or 0), "tax": float(inv.tax_total or 0), "total": float(inv.total or 0), "voided": bool(inv.voided), "returned_total": rt, "return_status": status})
            if inv.voided:
                tot["voided_count"] += 1; tot["voided_total"] += float(inv.total or 0)
                continue
            tot["count"] += 1; tot["subtotal"] += float(inv.subtotal or 0); tot["tax"] += float(inv.tax_total or 0); tot["total"] += float(inv.total or 0)
            for pay in pays_by_inv.get(inv.id) or [{"name": inv.payment_method or "-", "amount": float(inv.total or 0), "is_cash": pm_is_cash(methods.get(inv.payment_method))}]:
                pm = by_pm.setdefault(pay["name"], {"name": pay["name"], "count": 0, "total": 0.0, "is_cash": bool(pay["is_cash"])})
                pm["count"] += 1; pm["total"] += float(pay["amount"] or 0)
            for it in inv.items:
                if not it.product:
                    continue
                row = by_item.setdefault(it.product_id, {"product_id": it.product_id, "sku": it.product.sku, "name": it.product.name, "unit": it.product.unit or "", "category": it.product.category.name if it.product.category else "بدون فئة",
                                                         "qty": 0.0, "net": 0.0, "tax": 0.0, "total": 0.0, "invoices": set(), "returned_qty": 0.0, "returned_total": 0.0})
                row["qty"] += float(it.quantity or 0) * float(it.unit_factor or 1)
                net = max(0.0, float(it.quantity or 0) * float(it.unit_price or 0) - float(it.discount or 0))
                row["net"] += net; row["total"] += float(it.line_total or 0); row["tax"] += float(it.line_total or 0) - net; row["invoices"].add(inv.id)
        # ---- المرتجعات: على فواتير الجلسة (للصافي) وما اتصرف من درجها (للنقدية)
        returns_list, returned_items, rtot = [], {}, {"count": 0, "subtotal": 0.0, "tax": 0.0, "total": 0.0, "cash_refunds": 0.0, "drawer_total": 0.0}
        for r in rets:
            on_this = r.original_session_id == ses.id; in_drawer = r.pos_session_id == ses.id
            returns_list.append({"id": r.id, "number": r.number, "date": r.date, "invoice_id": r.invoice_id, "invoice_number": r.invoice.number if r.invoice else "-", "customer": r.customer.name if r.customer else "-",
                                 "reason": r.reason or "", "refund_method": r.refund_method or "", "refund_is_cash": bool(r.refund_is_cash), "is_full": bool(r.is_full), "subtotal": float(r.subtotal or 0),
                                 "tax": float(r.tax_total or 0), "total": float(r.total or 0), "processed_by": _user_display(r.processed_by), "on_session_invoice": on_this, "in_session_drawer": in_drawer})
            if on_this:
                rtot["count"] += 1; rtot["subtotal"] += float(r.subtotal or 0); rtot["tax"] += float(r.tax_total or 0); rtot["total"] += float(r.total or 0)
                for it in r.items:
                    ri = returned_items.setdefault(it.product_id, {"sku": it.product.sku, "name": it.product.name, "unit": it.product.unit or "", "category": it.product.category.name if it.product.category else "بدون فئة", "qty": 0.0, "total": 0.0, "returns": set()})
                    ri["qty"] += float(it.quantity or 0) * float(it.unit_factor or 1); ri["total"] += float(it.line_total or 0); ri["returns"].add(r.id)
                    if it.product_id in by_item:
                        by_item[it.product_id]["returned_qty"] += float(it.quantity or 0) * float(it.unit_factor or 1); by_item[it.product_id]["returned_total"] += float(it.line_total or 0)
            if in_drawer:
                rtot["drawer_total"] += float(r.total or 0)
                if r.refund_is_cash:
                    rtot["cash_refunds"] += float(r.total or 0)
        items = sorted(({**v, "invoice_count": len(v.pop("invoices")), "net_qty": v["qty"] - v["returned_qty"], "net_total": v["total"] - v["returned_total"]} for v in by_item.values()), key=lambda r: -r["total"])
        returned_items_list = sorted(({**v, "return_count": len(v.pop("returns"))} for v in returned_items.values()), key=lambda r: -r["total"])
        cash_sales = sum(v["total"] for v in by_pm.values() if v["is_cash"])
        expected = base["opening_cash"] + cash_sales - rtot["cash_refunds"]
        # ---- إلغاءات المطعم على طلبات الجلسة (أصناف مبعوتة اتلغت / طلبات اتلغت)
        cancellations, ctot = [], {"count": 0, "amount": 0.0, "qty": 0.0}
        sess_orders = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.items).joinedload(RestaurantOrderItem.product), joinedload(RestaurantOrder.table)).filter(RestaurantOrder.pos_session_id == ses.id).all()
        if sess_orders:
            oid_map = {o.id: o for o in sess_orders}
            evs = s.query(KitchenEvent).filter(KitchenEvent.order_id.in_(list(oid_map)), KitchenEvent.kind.in_(["item_void", "order_void"])).order_by(KitchenEvent.created_at).all()
            ev_orders = {e.order_id for e in evs if e.kind == "order_void"}
            for e in evs:
                cancellations.append({"date": e.created_at, "kind": e.kind, "kind_label": KITCHEN_EVENT_KINDS[e.kind], "order_number": e.order_number,
                                      "where": f"طاولة {e.table_number}" if e.table_number else RESTAURANT_ORDER_TYPES.get(e.order_type, ""), "product": e.product_name, "quantity": float(e.quantity or 0),
                                      "amount": float(e.amount or 0), "reason": e.reason or "", "by": _user_display(e.created_by) if e.created_by else "", "approved_by": e.approved_by or ""})
            for o in sess_orders:
                if o.state == "voided" and o.id not in ev_orders:       # طلب اتلغى قبل ما حاجة تتبعت للمطبخ
                    for it in o.items:
                        if it.kitchen_status == "voided":
                            continue
                        cancellations.append({"date": o.closed_at or o.opened_at, "kind": "order_void", "kind_label": "طلب ملغي (قبل المطبخ)", "order_number": o.number,
                                              "where": f"طاولة {o.table.number}" if o.table else RESTAURANT_ORDER_TYPES.get(o.order_type, ""), "product": it.product.name if it.product else "-",
                                              "quantity": float(it.quantity or 0), "amount": round(float(it.quantity or 0) * float(it.unit_price or 0) * (1 + float(it.tax_rate or 0) / 100.0), 2),
                                              "reason": (o.notes or "").split("ملغى:")[-1].strip(" |") if "ملغى:" in (o.notes or "") else "", "by": _user_display(o.opened_by) if o.opened_by else "", "approved_by": ""})
            cancellations.sort(key=lambda c: c["date"])
            ctot = {"count": len(cancellations), "amount": round(sum(c["amount"] for c in cancellations), 2), "qty": sum(c["quantity"] for c in cancellations)}
        return {**base, "cancellations": cancellations, "cancel_totals": ctot, "invoices": invoices, "totals": tot, "payment_methods": sorted(by_pm.values(), key=lambda r: -r["total"]), "items": items,
                "returns": returns_list, "returned_items": returned_items_list, "returns_totals": rtot,
                "net_total": tot["total"] - rtot["total"], "net_subtotal": tot["subtotal"] - rtot["subtotal"], "net_tax": tot["tax"] - rtot["tax"],
                "cash_sales": cash_sales, "cash_refunds": rtot["cash_refunds"], "expected_cash_now": expected,
                "expected_cash_final": base["expected_cash"] if base["state"] == "closed" and base["expected_cash"] is not None else expected}


def close_pos_session(session_id, counted_cash, notes=""):
    """إغلاق الجلسة: بيحسب النقدية المتوقعة (العهدة + المبيعات النقدية) ويقارنها بالمعدودة ويسجّل الفرق. الفاتح أو الأدمن بس."""
    require_action("pos_sessions", "edit")
    from .db import PosSession
    try:
        counted = float(counted_cash)
    except (TypeError, ValueError):
        raise ValueError("اكتب النقدية المعدودة (رقم)")
    if counted < 0:
        raise ValueError("النقدية المعدودة لا يمكن أن تكون سالبة")
    rep_ = pos_session_report(session_id)
    if rep_["state"] != "open":
        raise ValueError("الجلسة مقفولة بالفعل")
    pending_orders = list_open_restaurant_orders(session_id=session_id)
    if pending_orders:
        raise ValueError(f'مينفعش تقفل الجلسة - فيه {len(pending_orders)} فاتورة/طلب مفتوح لسه ما اتدفعش: ' + "، ".join(o["number"] for o in pending_orders[:6]))
    me = current_user() or {}
    if me.get("role") != "admin" and rep_["opened_by"] != me.get("username"):
        raise PermissionError(f'الجلسة مفتوحة بواسطة {rep_["opened_by_name"]} - هو أو الأدمن بس يقفلها')
    with get_session() as s:
        ses = s.get(PosSession, int(session_id))
        ses.state = "closed"; ses.closed_by = me.get("username", ""); ses.closed_at = datetime.datetime.now()
        ses.expected_cash = round(rep_["expected_cash_now"], 2); ses.counted_cash = round(counted, 2); ses.difference = round(counted - rep_["expected_cash_now"], 2)
        ses.close_notes = (notes or "").strip()
        s.commit()
    return pos_session_report(session_id)


def pos_session_totals(session_id):
    """أرقام سريعة للجلسة (عدد الفواتير غير الملغاة وإجماليها) - لشريط الجلسة في شاشة الكاشير بعد كل بيعة."""
    with get_session() as s:
        n, t = (s.query(func.count(SalesInvoice.id), func.coalesce(func.sum(SalesInvoice.total), 0.0))
                .filter(SalesInvoice.pos_session_id == int(session_id), SalesInvoice.voided.is_(False)).one())
    return {"count": int(n), "total": float(t)}


def list_pos_sessions(terminal_id=None, state=None, date_from=None, date_to=None):
    """قايمة الجلسات مع إجمالي مبيعاتها وعدد فواتيرها (غير الملغاة). غير الأدمن بيشوف جلساته بس."""
    from .db import PosSession
    me = current_user() or {}
    with get_session() as s:
        q = s.query(PosSession).options(joinedload(PosSession.terminal), joinedload(PosSession.employee))
        if terminal_id:
            q = q.filter(PosSession.terminal_id == int(terminal_id))
        if state:
            q = q.filter(PosSession.state == state)
        if date_from:
            q = q.filter(PosSession.opened_at >= date_from)
        if date_to:
            q = q.filter(PosSession.opened_at <= datetime.datetime.combine(date_to.date() if hasattr(date_to, "date") else date_to, datetime.time(23, 59, 59)))
        if me.get("role") not in ("admin", "accountant"):
            q = q.filter(PosSession.opened_by == me.get("username"))
        rows = q.order_by(PosSession.opened_at.desc()).all()
        sums = {sid: (n, float(t or 0)) for sid, n, t in s.query(SalesInvoice.pos_session_id, func.count(SalesInvoice.id), func.coalesce(func.sum(SalesInvoice.total), 0.0))
                .filter(SalesInvoice.pos_session_id.in_([r.id for r in rows] or [0]), SalesInvoice.voided.is_(False)).group_by(SalesInvoice.pos_session_id).all()}
        from .db import SalesReturn
        rsum = {sid: (n, float(t or 0)) for sid, n, t in s.query(SalesReturn.original_session_id, func.count(SalesReturn.id), func.coalesce(func.sum(SalesReturn.total), 0.0))
                .filter(SalesReturn.original_session_id.in_([r.id for r in rows] or [0])).group_by(SalesReturn.original_session_id).all()}
        out = []
        for r in rows:
            d = _session_dict(r); n, t = sums.get(r.id, (0, 0.0)); d["invoice_count"] = n; d["total_sales"] = t
            rn, rt = rsum.get(r.id, (0, 0.0)); d["returns_count"] = rn; d["returns_total"] = rt; d["net_sales"] = t - rt
            out.append(d)
        return out


def terminal_sales_summary():
    """إجمالي مبيعات كل ماكينة (غير الملغاة): عدد الفواتير وإجمالي المبيعات وآخر عملية."""
    with get_session() as s:
        rows = (s.query(SalesInvoice.pos_terminal_id, func.count(SalesInvoice.id), func.coalesce(func.sum(SalesInvoice.total), 0.0), func.max(SalesInvoice.date))
                .filter(SalesInvoice.pos_terminal_id.isnot(None), SalesInvoice.voided.is_(False)).group_by(SalesInvoice.pos_terminal_id).all())
    return {tid: {"count": n, "total": float(tot), "last": last} for tid, n, tot, last in rows}


def list_pos_sales(limit=100):
    with get_session() as s:
        return s.query(SalesInvoice).options(joinedload(SalesInvoice.customer)).filter(
            SalesInvoice.is_pos.is_(True)
        ).order_by(SalesInvoice.date.desc()).limit(limit).all()


def resend_invoice_to_zatca(invoice_id):
    """إعادة محاولة إرسال فاتورة (POS أو عادية) لمنصة فاتورة يدوياً."""
    from .zatca import build_zatca_base64, send_invoice_to_zatca
    import uuid as _uuid
    from . import zatca_p2 as _z2
    if _z2.is_enabled():
        from .db import ZatcaDoc
        doc_id = _z2.issue_invoice(invoice_id, send=False)
        if not doc_id:
            raise ValueError('تعذر إصدار الفاتورة الإلكترونية - راجع شاشة الفوترة الإلكترونية')
        st = _z2.retry_doc(doc_id)
        with get_session() as s:
            i_ = s.get(SalesInvoice, invoice_id)
            return {'status': i_.zatca_status, 'message': i_.zatca_response or st}
    settings = get_company_settings()
    invoice = get_sales_invoice(invoice_id)
    if not invoice:
        raise ValueError('الفاتورة غير موجودة')
    iso = invoice.date.strftime('%Y-%m-%dT%H:%M:%SZ')
    qr_b64 = build_zatca_base64(settings.name or '-', settings.vat_number or '-', iso, invoice.total, invoice.tax_total)
    result = send_invoice_to_zatca(settings, invoice.number, str(_uuid.uuid4()), qr_b64, invoice.total, invoice.tax_total)
    with get_session() as s:
        inv = s.get(SalesInvoice, invoice_id)
        inv.zatca_status = result['status']
        inv.zatca_response = result.get('message', '')
        s.commit()
    return result


# ======================================================================
# طباعة وإرسال الفواتير (إيميل / واتساب)
# ======================================================================
def generate_asset_purchase_invoice_pdf_file(invoice_id):
    """يولّد PDF لفاتورة مشتريات أصول - بيحوّل الأصول المرتبطة بالفاتورة
    لصفوف جدول زي أي فاتورة مشتريات عادية (كل أصل كصنف بكمية 1)، عشان
    نعيد استخدام نفس تصميم طباعة الفواتير الموحّد في البرنامج."""
    import os
    import types
    from .invoice_pdf import generate_invoice_pdf

    with get_session() as s:
        invoice = s.query(PurchaseInvoice).options(joinedload(PurchaseInvoice.supplier)).filter(PurchaseInvoice.id == invoice_id).first()
        if not invoice:
            raise ValueError("الفاتورة غير موجودة")
        assets = s.query(FixedAsset).filter(FixedAsset.purchase_invoice_id == invoice_id).all()
        if not assets:
            raise ValueError("مفيش أصول مرتبطة بالفاتورة دي")
        s.expunge_all()

    fake_items = []
    overall_tax_rate = round((invoice.tax_total / invoice.subtotal) * 100, 2) if invoice.subtotal else 15.0
    groups = {}
    for a in sorted(assets, key=lambda x: x.id):     # نفس الاسم + نفس التكلفة = سطر واحد بكمية
        groups.setdefault((a.name, a.cost), []).append(a)
    for (gname, gcost), units in groups.items():
        codes = units[0].code if len(units) == 1 else f"{units[0].code} - {units[-1].code}"
        fake_items.append(types.SimpleNamespace(
            quantity=len(units), unit_price=gcost, tax_rate=overall_tax_rate,
            product=types.SimpleNamespace(name=f"{gname} ({codes})"),
        ))
    invoice_wrapper = types.SimpleNamespace(
        number=invoice.number, date=invoice.date, subtotal=invoice.subtotal, tax_total=invoice.tax_total,
        total=invoice.total, discount=0.0, items=fake_items,
    )
    settings = get_company_settings()
    exports_dir = downloads_dir()
    return generate_invoice_pdf(invoice_wrapper, settings, None, exports_dir, party=invoice.supplier, party_label='المورد', doc_title='فاتورة مشتريات أصول ثابتة')


def generate_invoice_pdf_file(invoice_id, kind='sales'):
    """يولّد ملف PDF للفاتورة (فاتورة مبيعات بـ QR الزكاة، أو فاتورة مشتريات
    بدون QR) ويرجّع مساره."""
    import os
    from .invoice_pdf import generate_invoice_pdf
    from .zatca import zatca_qr_png_base64

    if kind == 'purchase':
        invoice = get_purchase_invoice(invoice_id)
        if not invoice:
            raise ValueError("الفاتورة غير موجودة")
        settings = get_company_settings()
        exports_dir = downloads_dir()
        return generate_invoice_pdf(invoice, settings, None, exports_dir, party=invoice.supplier, party_label='المورد', doc_title='فاتورة مشتريات')

    invoice = get_sales_invoice(invoice_id)
    if not invoice:
        raise ValueError("الفاتورة غير موجودة")
    settings = get_company_settings()
    iso = invoice.date.strftime('%Y-%m-%dT%H:%M:%SZ')
    from . import zatca_p2 as _z2
    qr_png = _z2.qr_png_for_invoice(invoice_id) or zatca_qr_png_base64(settings.name or '-', settings.vat_number or '-', iso, invoice.total, invoice.tax_total)
    exports_dir = downloads_dir()
    return generate_invoice_pdf(invoice, settings, qr_png, exports_dir)


def search_invoices(kind="sales", date_from=None, date_to=None, text=None, party_id=None, include_voided=True, limit=2000):
    """بحث/فلترة فواتير المبيعات أو المشتريات (بالتاريخ، النص في الرقم أو اسم الطرف، أو طرف
    محدد) - بيرجّع نفس كائنات list_*_invoices (الطرف والفرع محمّلين) بحد أقصى limit."""
    is_sales = kind == "sales"
    M = SalesInvoice if is_sales else PurchaseInvoice
    P = Customer if is_sales else Supplier
    party_rel = M.customer if is_sales else M.supplier
    with get_session() as s:
        q = s.query(M).options(joinedload(party_rel), joinedload(M.branch), joinedload(M.cost_center)).outerjoin(P, (M.customer_id if is_sales else M.supplier_id) == P.id)
        if date_from:
            q = q.filter(M.date >= _dt_start(date_from))
        if date_to:
            q = q.filter(M.date <= _dt_end(date_to))
        if party_id:
            q = q.filter((M.customer_id if is_sales else M.supplier_id) == int(party_id))
        if text and text.strip():
            like = f"%{text.strip()}%"
            q = q.filter((M.number.like(like)) | (P.name.like(like)))
        if not include_voided:
            q = q.filter(M.voided.isnot(True))
        if user_branch_ids():
            q = q.filter((M.branch_id.is_(None)) | (M.branch_id.in_(user_branch_ids())))
        rows = q.order_by(M.date.desc(), M.id.desc()).limit(int(limit)).all()
        s.expunge_all()
        return rows


def generate_invoices_batch_pdf_file(invoice_ids, kind="sales", include_summary=True, include_voided=False, summary_subtitle=""):
    """يطبع مجموعة فواتير (مبيعات أو مشتريات) في ملف PDF واحد، كل فاتورة في صفحة،
    مرتبة بالتاريخ، مع صفحة كشف بالإجماليات في الأول (اختياري). فواتير المبيعات
    بتتطبع بـ QR الزكاة. بيرجّع {path, count, skipped_voided}."""
    from .invoice_pdf import generate_invoices_pdf
    from .zatca import zatca_qr_png_base64
    ids = [int(i) for i in dict.fromkeys(invoice_ids or [])]
    if not ids:
        raise ValueError("اختر فاتورة واحدة على الأقل للطباعة")
    if len(ids) > 1000:
        raise ValueError("الحد الأقصى 1000 فاتورة في الملف الواحد - قسّمها على أكتر من دفعة")
    is_sales = kind == "sales"
    settings = get_company_settings()
    invoices = []
    for iid in ids:
        inv = get_sales_invoice(iid) if is_sales else get_purchase_invoice(iid)
        if inv:
            invoices.append(inv)
    skipped = 0
    if not include_voided:
        kept = [i for i in invoices if not getattr(i, "voided", False)]
        skipped = len(invoices) - len(kept); invoices = kept
    if not invoices:
        raise ValueError("كل الفواتير المختارة ملغاة - فعّل خيار طباعة الملغاة لو عايزها")
    invoices.sort(key=lambda i: (i.date, i.number))
    entries = []
    for inv in invoices:
        if is_sales:
            iso = inv.date.strftime('%Y-%m-%dT%H:%M:%SZ')
            from . import zatca_p2 as _z2
            qr = _z2.qr_png_for_invoice(inv.id) or zatca_qr_png_base64(settings.name or '-', settings.vat_number or '-', iso, inv.total, inv.tax_total)
            entries.append({"invoice": inv, "qr": qr})
        else:
            entries.append({"invoice": inv, "qr": None, "party": inv.supplier, "party_label": "المورد", "doc_title": "فاتورة مشتريات"})
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:19]   # بالأجزاء من الثانية عشان طباعتين ورا بعض ما يكتبوش على بعض
    kind_name = "sales" if is_sales else "purchases"
    path = generate_invoices_pdf(entries, settings, downloads_dir(), filename=f"invoices_{kind_name}_{stamp}.pdf", include_summary=include_summary,
                                 summary_title="كشف فواتير المبيعات المطبوعة" if is_sales else "كشف فواتير المشتريات المطبوعة",
                                 summary_subtitle=summary_subtitle)
    return {"path": path, "count": len(entries), "skipped_voided": skipped}


def email_invoice(invoice_id, to_email, pdf_path=None):
    """يرسل الفاتورة كملف PDF مرفق بالإيميل عن طريق إعدادات SMTP المسجّلة."""
    import smtplib
    from email.message import EmailMessage

    settings = get_company_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        raise ValueError("إعدادات البريد الإلكتروني (SMTP) غير مكتملة - راجع الإعدادات.")
    if not to_email or '@' not in to_email:
        raise ValueError("بريد إلكتروني غير صحيح")

    invoice = get_sales_invoice(invoice_id)
    if not invoice:
        raise ValueError("الفاتورة غير موجودة")

    pdf_path = pdf_path or generate_invoice_pdf_file(invoice_id)

    msg = EmailMessage()
    msg['Subject'] = f'فاتورة رقم {invoice.number} - {settings.name or ""}'
    msg['From'] = settings.smtp_from_email
    msg['To'] = to_email
    msg.set_content(
        f"مرفق فاتورتكم رقم {invoice.number} بتاريخ {invoice.date.strftime('%Y-%m-%d')} "
        f"بإجمالي {invoice.total:,.2f}.\n\nشكراً لتعاملكم معنا - {settings.name or ''}"
    )
    with open(pdf_path, 'rb') as f:
        msg.add_attachment(f.read(), maintype='application', subtype='pdf', filename=os.path.basename(pdf_path))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port or 587, timeout=20) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password or '')
        server.send_message(msg)

    return True


def send_email(to_list, subject, text, html=None, attachments=()):
    """بريد عام بإعدادات SMTP المسجلة: to_list قايمة عناوين، html اختياري، attachments = مسارات ملفات."""
    import mimetypes
    import smtplib
    from email.message import EmailMessage
    settings = get_company_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        raise ValueError("إعدادات البريد الإلكتروني (SMTP) غير مكتملة - راجع الإعدادات.")
    to_list = [x.strip() for x in (to_list or []) if x and "@" in x]
    if not to_list:
        raise ValueError("مفيش مستلمين صحيحين")
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, settings.smtp_from_email, ", ".join(to_list)
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    for path in attachments or ():
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        mt, st = ctype.split("/", 1)
        with open(path, "rb") as f:
            msg.add_attachment(f.read(), maintype=mt, subtype=st, filename=os.path.basename(path))
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port or 587, timeout=25) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password or "")
        server.send_message(msg)
    return True


def whatsapp_share_link(phone, invoice_number, total):
    """
    بيبني رابط واتساب (wa.me) بنص جاهز عن الفاتورة. الرابط ده بيفتح محادثة
    واتساب (ويب أو تطبيق) بنص جاهز بس - واتساب مالوش API عام بيسمح بإرفاق
    ملفات عن طريق الرابط المباشر، فالـ PDF محتاج يتبعت يدوياً (ملف الفاتورة
    بيتحفظ أصلاً في مجلد exports جاهز للإرفاق).
    """
    import urllib.parse
    if not phone:
        raise ValueError("رقم جوال العميل غير مسجّل")
    clean_phone = ''.join(ch for ch in phone if ch.isdigit() or ch == '+')
    if not clean_phone.startswith('+'):
        # افتراض رقم سعودي محلي لو مفيش كود دولة
        clean_phone = '966' + clean_phone.lstrip('0') if clean_phone.startswith('0') else clean_phone
    else:
        clean_phone = clean_phone.lstrip('+')

    message = f"فاتورتكم رقم {invoice_number} بإجمالي {total:,.2f} ر.س. الملف مرفق منفصلاً."
    return f"https://wa.me/{clean_phone}?text={urllib.parse.quote(message)}"


# ======================================================================
# مكونات الأصناف (BOM) - أصناف Kit والتصنيع
# ======================================================================
def list_bom_lines(product_id):
    with get_session() as s:
        lines = s.query(BomLine).options(joinedload(BomLine.component), joinedload(BomLine.unit)).filter(BomLine.product_id == product_id).order_by(BomLine.id).all()
        s.expunge_all()
        return lines


def add_bom_line(product_id, component_id, quantity):
    require_action("products", "edit")
    if int(product_id) == int(component_id):
        raise ValueError("الصنف مينفعش يكون مكوّن لنفسه")
    if float(quantity or 0) <= 0:
        raise ValueError("كمية المكوّن يجب أن تكون أكبر من صفر")
    with get_session() as s:
        existing = s.query(BomLine).filter(BomLine.product_id == product_id, BomLine.component_id == component_id).first()
        if existing:
            existing.quantity = float(quantity)
            existing.unit_id = None; existing.unit_qty = None       # الكمية هنا بالوحدة الأساسية (استيراد/إضافة سريعة)
            s.commit()
            return existing.id
        line = BomLine(product_id=product_id, component_id=component_id, quantity=float(quantity))
        s.add(line); s.commit(); s.refresh(line)
        return line.id


def _bom_reaches(s, start_id, target_id, seen=None):
    """هل مكونات start_id (وأحفادها) فيها target_id؟ - لمنع الدورات (أ يحتوي ب وب يحتوي أ)."""
    seen = seen or set()
    if start_id in seen:
        return False
    seen.add(start_id)
    for (cid,) in s.query(BomLine.component_id).filter(BomLine.product_id == start_id).all():
        if cid == target_id or _bom_reaches(s, cid, target_id, seen):
            return True
    return False


def save_bom(product_id, items):
    """حفظ كل مكونات الصنف مرة واحدة (بيستبدل القديم): items = [{component_id, quantity (بالوحدة المختارة), unit_id}].
    الكمية بتتحوّل للوحدة الأساسية للمكوّن وبتتخزّن (quantity) مع الوحدة والكمية الأصلية. بيرفض: مكوّن مكرر، الصنف نفسه، دورة، كمية <= 0."""
    require_action("products", "edit")
    product_id = int(product_id)
    seen = set()
    prepared = []
    for n, it in enumerate(items or [], 1):
        cid = int(it["component_id"])
        if cid == product_id:
            raise ValueError(f"السطر {n}: الصنف مينفعش يكون مكوّن لنفسه")
        if cid in seen:
            raise ValueError(f"السطر {n}: المكوّن مكرر - اجمع كمياته في سطر واحد")
        seen.add(cid)
        qty = float(it.get("quantity") or 0)
        if qty <= 0:
            raise ValueError(f"السطر {n}: الكمية يجب أن تكون أكبر من صفر")
        base, _unit_name, _factor = convert_to_base_quantity(cid, qty, it.get("unit_id"))
        prepared.append((cid, base, int(it["unit_id"]) if it.get("unit_id") else None, qty))
    with get_session() as s:
        parent = s.get(Product, product_id)
        if not parent:
            raise ValueError("الصنف غير موجود")
        if parent.product_type == "service":
            raise ValueError("أصناف الخدمة ملهاش مكونات")
        for cid, _b, _u, _q in prepared:
            if not s.get(Product, cid):
                raise ValueError("فيه مكوّن غير موجود")
            if _bom_reaches(s, cid, product_id):
                raise ValueError(f"المكوّن «{s.get(Product, cid).name}» بيحتوي على هذا الصنف نفسه (دورة) - مينفعش")
        s.query(BomLine).filter(BomLine.product_id == product_id).delete(synchronize_session=False)
        for cid, base, uid, qty in prepared:
            s.add(BomLine(product_id=product_id, component_id=cid, quantity=base, unit_id=uid, unit_qty=qty))
        s.commit()
    return len(prepared)


def delete_bom_line(line_id):
    require_action("products", "edit")
    with get_session() as s:
        line = s.get(BomLine, line_id)
        if line:
            s.delete(line); s.commit()


def get_bom_explosion(product_id, quantity=1.0):
    """يرجّع قائمة (component, needed_qty) لصنف معيّن بكمية معينة - مستوى
    واحد فقط (مش هيكل متداخل)."""
    with get_session() as s:
        lines = s.query(BomLine).options(joinedload(BomLine.component)).filter(BomLine.product_id == product_id).all()
        result = [{"component": ln.component, "component_id": ln.component_id, "quantity": ln.quantity * float(quantity)} for ln in lines]
        s.expunge_all()
        return result


# ---------------------------- أوامر الإنتاج/التصنيع ----------------------------
def list_production_orders(limit=200):
    with get_session() as s:
        orders = s.query(ProductionOrder).options(joinedload(ProductionOrder.product), joinedload(ProductionOrder.location)).order_by(ProductionOrder.date.desc()).limit(limit).all()
        s.expunge_all()
        return orders


def create_production_order(product_id, quantity, location_id, notes="", branch_id=None, cost_center_id=None, order_date=None):
    require_action("stock_moves", "create")
    if float(quantity or 0) <= 0:
        raise ValueError("الكمية يجب أن تكون أكبر من صفر")
    with get_session() as s:
        product = s.get(Product, int(product_id))
        if not product:
            raise ValueError("الصنف غير موجود")
        if product.product_type != "manufactured":
            raise ValueError(f'الصنف "{product.name}" مش معرَّف كصنف "مُصنَّع" - غيّر نوعه من شاشة مكونات الأصناف أولاً')
        has_bom = s.query(BomLine).filter(BomLine.product_id == product_id).count()
        if not has_bom:
            raise ValueError(f'الصنف "{product.name}" مفهوش مكونات معرَّفة (BOM) - عرّفها من شاشة مكونات الأصناف أولاً')

        number = _next_code(s, ProductionOrder, "MO-")
        order = ProductionOrder(
            number=number, product_id=product_id, quantity=float(quantity), location_id=location_id,
            notes=notes or "", state="draft", branch_id=branch_id or default_branch_id(),
            cost_center_id=cost_center_id or default_cost_center_id(),
        )
        if order_date:
            order.date = order_date
        s.add(order); s.commit(); s.refresh(order)
        return order.id


def create_production_orders(items, location_id, notes="", order_date=None):
    """أوامر إنتاج لأكتر من صنف مصنَّع دفعة واحدة (أمر لكل صنف بنفس التاريخ والمخزن): items = [{product_id, quantity}].
    بيتحقق من كل الأصناف الأول (نوع مصنَّع + له مكونات + كمية صحيحة) قبل ما يعمل أي أمر. بيرجّع قايمة أرقام الأوامر."""
    require_action("stock_moves", "create")
    if not items:
        raise ValueError("أضف صنف واحد على الأقل")
    if not location_id:
        raise ValueError("اختر المخزن")
    with get_session() as s:
        for n, it in enumerate(items, 1):
            if float(it.get("quantity") or 0) <= 0:
                raise ValueError(f"السطر {n}: الكمية يجب أن تكون أكبر من صفر")
            p = s.get(Product, int(it["product_id"]))
            if not p:
                raise ValueError(f"السطر {n}: الصنف غير موجود")
            if p.product_type != "manufactured":
                raise ValueError(f'السطر {n}: «{p.name}» مش معرَّف كصنف "مُصنَّع" - غيّر نوعه من شاشة مكونات الأصناف')
            if not s.query(BomLine).filter(BomLine.product_id == p.id).count():
                raise ValueError(f"السطر {n}: «{p.name}» مفهوش مكونات (BOM) - عرّفها من شاشة مكونات الأصناف")
    ids = []
    for it in items:
        ids.append(create_production_order(int(it["product_id"]), float(it["quantity"]), int(location_id), notes=notes, order_date=order_date))
    return ids


def confirm_production_order(order_id):
    """يستهلك المكونات (حسب BOM) وينتج كمية الصنف التام - بيتحقق من توفر
    كل المكونات أولاً قبل أي حركة."""
    require_action("stock_moves", "post")
    with get_session() as s:
        order = s.get(ProductionOrder, order_id)
        if not order:
            raise ValueError("أمر الإنتاج غير موجود")
        if order.state == "done":
            raise ValueError("أمر الإنتاج مؤكَّد بالفعل")
        product_id, quantity, location_id = order.product_id, order.quantity, order.location_id
        branch_id, cost_center_id = order.branch_id, order.cost_center_id
        order_number = order.number
        order_date = order.date

    bom = get_bom_explosion(product_id, quantity)
    if not bom:
        raise ValueError("مفيش مكونات معرَّفة لهذا الصنف")

    # تحقق من توفر كل المكونات أولاً (قبل أي حركة فعلية)
    for line in bom:
        balance = get_product_balance(line["component_id"], location_id, branch_id)
        if balance < line["quantity"]:
            raise ValueError(
                f'الرصيد المتاح من "{line["component"].name}" ({balance:g}) أقل من المطلوب للإنتاج ({line["quantity"]:g})'
            )

    total_component_cost = 0.0
    for line in bom:
        comp = line["component"]
        create_stock_move(
            product_id=line["component_id"], location_id=location_id, direction="out",
            quantity=line["quantity"], unit_cost=comp.cost_price or 0,
            reference=f"MO:{order_number}", note=f"استهلاك إنتاج {order_number}",
            branch_id=branch_id, cost_center_id=cost_center_id, _internal=True, move_date=order_date,
        )
        total_component_cost += line["quantity"] * (comp.cost_price or 0)

    unit_cost = round(total_component_cost / quantity, 4) if quantity else 0
    create_stock_move(
        product_id=product_id, location_id=location_id, direction="in",
        quantity=quantity, unit_cost=unit_cost,
        reference=f"MO:{order_number}", note=f"ناتج إنتاج {order_number}",
        branch_id=branch_id, cost_center_id=cost_center_id, _internal=True, move_date=order_date, update_cost=True,
    )

    with get_session() as s:
        prod = s.get(Product, product_id)
        if prod and unit_cost and (prod.cost_method or "auto") != "avg":
            prod.cost_price = unit_cost  # تحديث تكلفة الصنف المُصنَّع بآخر تكلفة إنتاج فعلية (المتوسط المرجح اتحدّث تلقائي مع حركة الناتج)
        order = s.get(ProductionOrder, order_id)
        order.state = "done"
        s.commit()
    return True


def delete_production_order(order_id):
    require_action("stock_moves", "delete")
    with get_session() as s:
        order = s.get(ProductionOrder, order_id)
        if not order:
            raise ValueError("أمر الإنتاج غير موجود")
        if order.state == "done":
            raise ValueError("مينفعش تحذف أمر إنتاج مؤكَّد")
        s.delete(order); s.commit()


# ======================================================================
# التوالف (Damage / Scrap) - بيتعامل مع الصنف العادي والمُصنَّع والـ Kit
# ======================================================================
def create_damage_entry(items, location_id, reason="", branch_id=None, cost_center_id=None, damage_date=None):
    """
    يسجّل سند تلف لأكتر من صنف دفعة واحدة.
    items: [{"product_id":.., "quantity":.., "damage_account_id": اختياري}, ...]
    - صنف عادي أو مُصنَّع: بيتخصم مباشرة من مخزونه هو.
    - صنف Kit: بيتفكك لمكوناته (حسب BOM) وكل مكوّن بيتخصم بنسبته الفعلية.
    - damage_account_id: حساب خسارة اختياري لكل صنف - لو فاضي بيستخدم
      حساب خسائر الجرد الافتراضي من الإعدادات المحاسبية.
    """
    require_action("inventory_adjustments", "create")
    if not items:
        raise ValueError("أضف صنف واحد على الأقل للتلف")

    branch_id = branch_id or default_branch_id()
    cost_center_id = cost_center_id or default_cost_center_id()
    if branch_id and not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    if cost_center_id and not allowed_cost_center(cost_center_id): raise PermissionError("مركز التكلفة غير مسموح لهذا المستخدم")

    cfg = _accounting_settings()
    default_loss_account = cfg.inventory_loss_account_id
    if not cfg.inventory_account_id:
        raise ValueError("إعداد حساب المخزون ناقص - راجع الإعدادات المحاسبية")

    # جهّز كل صنف: تحقق من وجوده، فكّ الـ Kit لمكوناته، وحدّد حساب التلف
    # المستخدم (المحدد يدويًا أو الافتراضي من الإعدادات).
    prepared = []  # [{"product":, "quantity":, "damage_account_id":, "lines":[(pid,qty,cost,name)]}]
    for it in items:
        product_id = int(it["product_id"])
        quantity = float(it.get("quantity") or 0)
        if quantity <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من صفر لكل صنف")
        product = get_product(product_id)
        if not product:
            raise ValueError("أحد الأصناف المختارة غير موجود")

        damage_account_id = it.get("damage_account_id") or default_loss_account
        if not damage_account_id:
            raise ValueError(f'حدد حساب التلف للصنف «{product.name}» (مفيش حساب افتراضي في الإعدادات)')

        if product.product_type == "kit":
            bom = get_bom_explosion(product_id, quantity)
            if not bom:
                raise ValueError(f'الصنف «{product.name}» من نوع Kit لكن مفهوش مكونات معرَّفة له')
            item_lines = [(line["component_id"], line["quantity"], line["component"].cost_price or 0, line["component"].name) for line in bom]
        else:
            item_lines = [(product_id, quantity, product.cost_price or 0, product.name)]

        prepared.append({"product": product, "quantity": quantity, "damage_account_id": int(damage_account_id), "lines": item_lines})

    # تحقق من توفر كل سطور كل الأصناف قبل أي حركة فعلية
    for p in prepared:
        for pid, qty, cost, name in p["lines"]:
            balance = get_product_balance(pid, location_id, branch_id)
            if balance < qty:
                extra = f' (مكوّن ضمن «{p["product"].name}»)' if p["product"].product_type == "kit" else ''
                raise ValueError(f'الرصيد المتاح من «{name}»{extra} ({balance:g}) أقل من كمية التلف المطلوبة ({qty:g})')

    with get_session() as s:
        number = _next_code(s, DamageRecord, "DMG-")
        total_cost = sum(qty * cost for p in prepared for _, qty, cost, _ in p["lines"])
        record = DamageRecord(
            number=number, location_id=location_id, reason=reason or "",
            branch_id=branch_id, cost_center_id=cost_center_id, total_cost=round(total_cost, 2),
        )
        if damage_date:
            record.date = damage_date
        s.add(record); s.flush()

        item_rows = []
        for p in prepared:
            di = DamageItem(record_id=record.id, product_id=p["product"].id, quantity=p["quantity"], damage_account_id=p["damage_account_id"])
            s.add(di); s.flush()
            for pid, qty, cost, _ in p["lines"]:
                s.add(DamageLine(item_id=di.id, product_id=pid, quantity=qty, unit_cost=cost))
            item_rows.append((di, p))
        s.commit()
        record_id, record_number = record.id, record.number

    # حركات المخزون الفعلية لكل الأصناف/المكونات
    for p in prepared:
        for pid, qty, cost, name in p["lines"]:
            create_stock_move(
                product_id=pid, location_id=location_id, direction="out", quantity=qty, unit_cost=cost,
                reference=f"DMG:{record_number}", note=f"تلف {record_number} - {p['product'].name}",
                branch_id=branch_id, cost_center_id=cost_center_id, _internal=True, move_date=damage_date, allow_expired=True,
            )

    # قيد محاسبي واحد: بيجمّع حسب حساب التلف المستخدم فعليًا لكل صنف (كل
    # صنف ممكن يكون له حساب مختلف)
    debit_by_account = {}
    for p in prepared:
        item_cost = sum(qty * cost for _, qty, cost, _ in p["lines"])
        if item_cost > 0:
            debit_by_account[p["damage_account_id"]] = debit_by_account.get(p["damage_account_id"], 0.0) + item_cost

    if debit_by_account:
        lines = [{"account_id": acc_id, "debit": round(amount, 2)} for acc_id, amount in debit_by_account.items()]
        lines.append({"account_id": cfg.inventory_account_id, "credit": round(sum(debit_by_account.values()), 2)})
        names = "، ".join(p["product"].name for p in prepared)
        create_journal_entry(
            lines, reference=record_number, description=f"تلف أصناف: {names} ({reason or 'بدون سبب مذكور'})",
            source_type="damage", source_id=record_id, branch_id=branch_id, cost_center_id=cost_center_id, entry_date=damage_date,
        )
    return record_id


def list_damage_records(limit=200):
    with get_session() as s:
        records = s.query(DamageRecord).options(
            joinedload(DamageRecord.location),
            joinedload(DamageRecord.items).joinedload(DamageItem.product),
            joinedload(DamageRecord.items).joinedload(DamageItem.damage_account),
            joinedload(DamageRecord.items).joinedload(DamageItem.lines).joinedload(DamageLine.product),
        ).order_by(DamageRecord.date.desc()).limit(limit).all()
        s.expunge_all()
        return records


# ======================================================================
# إلغاء/إغلاق المستندات (فواتير، سندات، حركات مخزون يدوية)
# ======================================================================
_AUTO_STOCK_PREFIXES = ("SALES:", "PURCHASE:", "MO:", "DMG:", "ADJ:", "TRF:", "VOID:", "GRN:")


def void_stock_move(move_id):
    """إلغاء حركة مخزون يدوية فقط (مش حركة مولّدة تلقائياً من فاتورة/إنتاج/
    تلف/تسوية/تحويل - هذه تُلغى من مستندها الأصلي)."""
    require_action("stock_moves", "delete")
    with get_session() as s:
        m = s.get(StockMove, move_id)
        if not m:
            raise ValueError("الحركة غير موجودة")
        if m.voided:
            raise ValueError("الحركة ملغاة بالفعل")
        if m.reference and m.reference.startswith(_AUTO_STOCK_PREFIXES):
            raise ValueError("الحركة دي مولّدة تلقائياً من مستند آخر - ألغِ المستند الأصلي بدل ما تلغيها من هنا مباشرة")
        m.voided = True
        s.commit()
    return True


def void_payment(payment_id):
    """إلغاء سند قبض/صرف: بيحوّل قيده المحاسبي لمسودة (يستبعده من كل
    التقارير) ويعلّم السند كملغى. لو السند صرف رواتب، بيرجّع كل القسائم
    اللي اتصرفت بيه (موظف واحد أو مجموعة) قابلة للصرف تاني."""
    require_action("receipts_payments", "delete")
    with get_session() as s:
        p = s.get(Payment, payment_id)
        if not p:
            raise ValueError("السند غير موجود")
        if p.voided:
            raise ValueError("السند ملغى بالفعل")
        jid = p.journal_entry_id
        p.voided = True
        if p.partner_type == "payroll" and p.partner_id:
            for slip in s.query(Payslip).filter(Payslip.payment_id == p.id).all():
                slip.paid_at = None; slip.payment_id = None
            run = s.get(PayrollRun, p.partner_id)
            if run:
                run.paid_at = None
                if run.payment_id == p.id:
                    run.payment_id = None
        s.commit()
    if jid:
        set_journal_entry_draft_by_source(jid)
    return True


def _void_batch_lines(kind, invoice_number, product_id):
    """سطور التشغيلات اللي لازم ترجع/تتشال عند إلغاء فاتورة: نفس تشغيلات الحركة الأصلية (None لو الصنف مش متتبَّع أو مفيش سطور)."""
    lines = _reference_batch_lines(f"{'SALES' if kind == 'sales' else 'PURCH'}:{invoice_number}", product_id, "out" if kind == "sales" else "in")
    if lines:
        return lines
    with get_session() as s:
        p = s.get(Product, int(product_id))
    return [] if is_batch_tracked(p) else None        # متتبَّع بس الحركة الأصلية قبل التفعيل: من غير سطور (يرجع للرصيد السابق)


def _sales_invoice_location(invoice_number):
    """المخزن اللي اتصرف منه بيع فاتورة (من حركة الخروج الأصلية) - مش دايمًا المخزن الافتراضي (مثلًا ماكينة كاشير بمخزن خاص)."""
    with get_session() as s:
        m = s.query(StockMove).filter(StockMove.reference == f"SALES:{invoice_number}", StockMove.direction == "out").first()
        return m.location_id if m else None


def _reverse_invoice_stock(invoice_id, kind):
    """يعكس حركات مخزون فاتورة (بيع أو شراء) - بما فيها فك تكيّت الـ Kit."""
    invoice = get_sales_invoice(invoice_id) if kind == "sales" else get_purchase_invoice(invoice_id)
    if not invoice:
        raise ValueError("الفاتورة غير موجودة")
    reverse_direction = "in" if kind == "sales" else "out"
    location_id = (getattr(invoice, "location_id", None) or (_sales_invoice_location(invoice.number) if kind == "sales" else None)) or default_location_id()
    branch_id, cost_center_id = invoice.branch_id, invoice.cost_center_id
    for it in invoice.items:
        product = it.product
        if product and product.product_type == "kit" and kind == "sales":
            bom = get_bom_explosion(product.id, float(it.quantity))
            for line in bom:
                create_stock_move(
                    product_id=line["component_id"], location_id=location_id, direction=reverse_direction,
                    quantity=line["quantity"], unit_cost=line["component"].cost_price or 0,
                    reference=f"VOID:{invoice.number}", note=f"إلغاء فاتورة {invoice.number}",
                    branch_id=branch_id, cost_center_id=cost_center_id, _internal=True,
                    batch_lines=_void_batch_lines(kind, invoice.number, line["component_id"]),
                )
        else:
            create_stock_move(
                product_id=it.product_id, location_id=location_id, direction=reverse_direction,
                quantity=float(it.quantity), unit_cost=float(it.unit_price),
                unit_id=it.unit_id, reference=f"VOID:{invoice.number}", note=f"إلغاء فاتورة {invoice.number}",
                branch_id=branch_id, cost_center_id=cost_center_id, _internal=True,
                batch_lines=_void_batch_lines(kind, invoice.number, it.product_id),
            )
    return invoice


def void_sales_invoice(invoice_id):
    """إلغاء فاتورة مبيعات: بيرجّع الكميات للمخزون (بما فيها فك الـ Kit)
    ويحوّل القيد المحاسبي لمسودة."""
    require_action("sales_invoices", "delete")
    with get_session() as s:
        inv = s.get(SalesInvoice, invoice_id)
        if not inv:
            raise ValueError("الفاتورة غير موجودة")
        if inv.voided:
            raise ValueError("الفاتورة ملغاة بالفعل")
        if inv.is_pos:
            raise ValueError("فواتير الكاشير مينفعش تتلغي أو تتحذف نهائيًا - اعمل مرتجع (كلي أو جزئي) من تقرير الجلسة")

    invoice = _reverse_invoice_stock(invoice_id, "sales")

    with get_session() as s:
        entry_ids = [e.id for e in s.query(JournalEntry).filter(
            JournalEntry.source_type == "sales_invoice", JournalEntry.source_id == invoice_id
        ).all()]
    for eid in entry_ids:
        set_journal_entry_draft_by_source(eid)

    with get_session() as s:
        inv = s.get(SalesInvoice, invoice_id)
        inv.voided = True
        _kitchen_events_for_invoice(s, int(invoice_id), "invoice_void",
                                    [(i.product_id, i.quantity, i.line_total) for i in inv.items], "إلغاء فاتورة")
        s.commit()
    return True


def recompute_average_cost(product_id):
    """يعيد حساب المتوسط المرجح لصنف من تاريخ حركاته (من الأقدم للأحدث) - بيُستخدم بعد إلغاء فاتورة مشتريات أو سند استلام عشان
    المتوسط يرجع لقيمته الصحيحة كأن الاستلام الملغي ما حصلش. الاستلامات (شراء / سند استلام / إنتاج / إدخال يدوي بتكلفة) بتتدمج بالمتوسط،
    والخروج بينقّص الكمية بس، والتحويل والجرد ومرتجع المبيعات بيغيّروا الكمية من غير ما يغيّروا التكلفة. بيرجّع المتوسط الجديد (أو None)."""
    with get_session() as s:
        p = s.get(Product, int(product_id))
        if not p or (p.cost_method or "auto") != "avg":
            return None
        moves = s.query(StockMove).filter(StockMove.product_id == p.id, StockMove.voided.is_(False)).order_by(StockMove.date, StockMove.id).all()
        voided_nums = {(m.reference or "")[5:] for m in moves if (m.reference or "").startswith("VOID:") and m.direction == "out"}
        skip_refs = {f"PURCH:{n}" for n in voided_nums} | {f"GRN:{n}" for n in voided_nums}
        if voided_nums:     # فاتورة اتعملت من سند استلام: الاستلام الأصلي هو GRN المربوط بيها
            inv_ids = [i for (i,) in s.query(PurchaseInvoice.id).filter(PurchaseInvoice.number.in_(voided_nums)).all()]
            if inv_ids:
                skip_refs |= {f"GRN:{n}" for (n,) in s.query(GoodsReceiptNote.number).filter(GoodsReceiptNote.purchase_invoice_id.in_(inv_ids)).all()}
        first_cost = next((float(m.unit_cost or 0) for m in moves if m.direction == "in" and float(m.unit_cost or 0) > 0 and (m.reference or "") not in skip_refs), None)
        qty, cost = 0.0, (first_cost if first_cost is not None else float(p.cost_price or 0))
        for m in moves:
            ref = m.reference or ""
            if m.direction == "out":
                if ref.startswith("VOID:"):
                    continue                       # إلغاء استلام: الاستلام الأصلي اتخطّى فمفيش داعي نخصم تاني
                qty -= m.quantity
                continue
            if ref in skip_refs:
                continue
            base_cost = float(m.unit_cost or 0)
            blends = ref.startswith(("PURCH:", "GRN:", "MO:")) or (not ref.startswith(("TRF-", "VOID:", "ADJ:", "SALES:")) and base_cost > 0)
            if blends and base_cost > 0:
                held = max(qty, 0.0)
                cost = round(((held * cost) + m.quantity * base_cost) / (held + m.quantity), 4) if (held + m.quantity) > 0 else base_cost
            qty += m.quantity
        p.cost_price = cost
        for ul in s.query(ProductUnitLine).filter(ProductUnitLine.product_id == p.id, ProductUnitLine.factor_to_base == 1.0).all():
            ul.cost_price = cost
        s.commit()
        return cost


def void_purchase_invoice(invoice_id):
    """إلغاء فاتورة مشتريات: بينزّل الكميات اللي كانت اتضافت للمخزون
    ويحوّل القيد المحاسبي لمسودة."""
    require_action("purchase_invoices", "delete")
    with get_session() as s:
        inv = s.get(PurchaseInvoice, invoice_id)
        if not inv:
            raise ValueError("الفاتورة غير موجودة")
        if inv.voided:
            raise ValueError("الفاتورة ملغاة بالفعل")

    inv_obj = _reverse_invoice_stock(invoice_id, "purchase")
    for pid in {it.product_id for it in inv_obj.items}:      # المتوسط المرجح يرجع للقيمة الصحيحة من غير الاستلام الملغي
        recompute_average_cost(pid)

    with get_session() as s:
        entry_ids = [e.id for e in s.query(JournalEntry).filter(
            JournalEntry.source_type == "purchase_invoice", JournalEntry.source_id == invoice_id
        ).all()]
    for eid in entry_ids:
        set_journal_entry_draft_by_source(eid)

    with get_session() as s:
        inv = s.get(PurchaseInvoice, invoice_id)
        inv.voided = True
        s.commit()
    return True


def generate_payment_pdf_file(payment_id):
    """يولّد سند قبض/صرف PDF احترافي (شعار + مبلغ بالأرقام والحروف +
    توقيعات) - بيحترم إعدادات تنسيق الطباعة المحفوظة."""
    import os
    from .invoice_pdf import generate_payment_pdf

    with get_session() as s:
        p = s.query(Payment).options(joinedload(Payment.account)).filter(Payment.id == payment_id).first()
        if not p:
            raise ValueError("السند غير موجود")
        party_name = "-"
        if p.partner_id:
            if p.partner_type == "customer":
                party = s.get(Customer, p.partner_id)
            elif p.partner_type == "employee":
                party = s.get(Employee, p.partner_id)
            else:
                party = s.get(Supplier, p.partner_id)
            party_name = party.name if party else "-"
        s.expunge(p)
        if p.account:
            s.expunge(p.account)

    settings = get_company_settings()
    exports_dir = downloads_dir()
    return generate_payment_pdf(p, settings, party_name, exports_dir)


def generate_stock_move_pdf_file(move_id):
    """يولّد إذن حركة مخزون PDF بسيط."""
    import os
    from .invoice_pdf import _simple_doc_pdf

    with get_session() as s:
        m = s.query(StockMove).options(joinedload(StockMove.product), joinedload(StockMove.location)).filter(StockMove.id == move_id).first()
        if not m:
            raise ValueError("الحركة غير موجودة")
        rows = [
            ("التاريخ", m.date.strftime("%Y-%m-%d %H:%M")),
            ("الصنف", f"{m.product.sku} - {m.product.name}" if m.product else "-"),
            ("المخزن", m.location.name if m.location else "-"),
            ("الاتجاه", "دخول" if m.direction == "in" else "خروج"),
            ("الكمية", f"{m.quantity:g}"),
            ("تكلفة الوحدة", f"{m.unit_cost:,.2f}"),
            ("المرجع", m.reference or "-"),
            ("ملاحظات", m.note or "-"),
            ("الحالة", "ملغاة" if m.voided else "سارية"),
        ]
        number = f"move_{m.id}"

    settings = get_company_settings()
    exports_dir = downloads_dir()
    return _simple_doc_pdf("إذن حركة مخزون", settings.name or '', rows, exports_dir, number, company=settings)


def generate_journal_entry_pdf_file(entry_id):
    """يولّد PDF احترافي لقيد يومية (شعار + رأسية + جدول حساب/بيان/مدين/
    دائن بإجمالي + خانات توقيع) - بيحترم إعدادات تنسيق الطباعة المحفوظة."""
    import os
    from .invoice_pdf import generate_journal_entry_pdf

    entry = get_journal_entry(entry_id)
    if not entry:
        raise ValueError("القيد غير موجود")

    settings = get_company_settings()
    exports_dir = downloads_dir()
    return generate_journal_entry_pdf(entry, settings, exports_dir)


# ======================================================================
# مرفقات فاتورة المشتريات (نسخة فاتورة المورد الأصلية)
# ======================================================================
def attach_purchase_invoice_file(invoice_id, source_path):
    """ينسخ ملف (فاتورة المورد الممسوحة ضوئياً/PDF) لمجلد مرفقات دائم
    ويسجّله على الفاتورة. يدعم إرفاق أكتر من ملف لنفس الفاتورة."""
    import os, shutil, uuid

    require_action("purchase_invoices", "edit")
    if not source_path or not os.path.exists(source_path):
        raise ValueError("الملف غير موجود")

    with get_session() as s:
        inv = s.get(PurchaseInvoice, invoice_id)
        if not inv:
            raise ValueError("الفاتورة غير موجودة")
        invoice_number = inv.number

    base_dir = os.path.normpath(os.path.join(APP_DIR, 'attachments', 'purchase_invoices', str(invoice_number)))
    os.makedirs(base_dir, exist_ok=True)

    original_name = os.path.basename(source_path)
    name_root, ext = os.path.splitext(original_name)
    unique_name = f"{name_root}_{uuid.uuid4().hex[:8]}{ext}"
    dest_path = os.path.join(base_dir, unique_name)
    shutil.copy2(source_path, dest_path)

    with get_session() as s:
        att = PurchaseInvoiceAttachment(invoice_id=invoice_id, file_name=original_name, file_path=dest_path)
        s.add(att); s.commit(); s.refresh(att)
        return att.id


def list_purchase_invoice_attachments(invoice_id):
    with get_session() as s:
        atts = s.query(PurchaseInvoiceAttachment).filter(
            PurchaseInvoiceAttachment.invoice_id == invoice_id
        ).order_by(PurchaseInvoiceAttachment.uploaded_at.desc()).all()
        s.expunge_all()
        return atts


def delete_purchase_invoice_attachment(attachment_id):
    import os
    require_action("purchase_invoices", "edit")
    with get_session() as s:
        att = s.get(PurchaseInvoiceAttachment, attachment_id)
        if not att:
            raise ValueError("المرفق غير موجود")
        file_path = att.file_path
        s.delete(att)
        s.commit()
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass  # فشل حذف الملف الفعلي مش لازم يمنع حذف السجل
    return True


# ======================================================================
# صورة الصنف
# ======================================================================
def set_product_image(product_id, source_path):
    """ينسخ صورة الصنف لمجلد دائم ويحفظ مسارها على الصنف. بيمسح الصورة
    القديمة لو موجودة."""
    import os, shutil, uuid

    require_action("products", "edit")
    if not source_path or not os.path.exists(source_path):
        raise ValueError("الملف غير موجود")

    ext = os.path.splitext(source_path)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        raise ValueError("صيغة الصورة غير مدعومة - استخدم PNG أو JPG أو WEBP")

    with get_session() as s:
        p = s.get(Product, product_id)
        if not p:
            raise ValueError("الصنف غير موجود")
        old_path = p.image_path

    base_dir = os.path.normpath(os.path.join(APP_DIR, 'attachments', 'product_images'))
    os.makedirs(base_dir, exist_ok=True)
    dest_path = os.path.join(base_dir, f"product_{product_id}_{uuid.uuid4().hex[:8]}{ext}")
    shutil.copy2(source_path, dest_path)

    with get_session() as s:
        p = s.get(Product, product_id)
        p.image_path = dest_path
        s.commit()

    if old_path and os.path.exists(old_path):
        try:
            os.remove(old_path)
        except Exception:
            pass
    return dest_path


def remove_product_image(product_id):
    import os
    require_action("products", "edit")
    with get_session() as s:
        p = s.get(Product, product_id)
        if not p:
            raise ValueError("الصنف غير موجود")
        old_path = p.image_path
        p.image_path = None
        s.commit()
    if old_path and os.path.exists(old_path):
        try:
            os.remove(old_path)
        except Exception:
            pass
    return True


# ======================================================================
# مجموعات نقاط البيع (أزرار تصفية سريعة قابلة للتخصيص)
# ======================================================================
def list_pos_groups(active_only=True):
    with get_session() as s:
        q = s.query(PosGroup)
        if active_only:
            q = q.filter(PosGroup.is_active.is_(True))
        groups = q.order_by(PosGroup.sort_order, PosGroup.name).all()
        s.expunge_all()
        return groups


def create_pos_group(name, color="", sort_order=0):
    require_action("products", "create")
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم المجموعة مطلوب")
    with get_session() as s:
        if s.query(PosGroup).filter(PosGroup.name == name).first():
            raise ValueError(f'يوجد مجموعة بنفس الاسم "{name}" بالفعل')
        g = PosGroup(name=name, color=color or "", sort_order=int(sort_order or 0), is_active=True)
        s.add(g); s.commit(); s.refresh(g)
        return g.id


def update_pos_group(group_id, **fields):
    require_action("products", "edit")
    with get_session() as s:
        g = s.get(PosGroup, group_id)
        if not g:
            raise ValueError("المجموعة غير موجودة")
        for k, v in fields.items():
            setattr(g, k, v)
        s.commit()


def delete_pos_group(group_id):
    require_action("products", "delete")
    with get_session() as s:
        g = s.get(PosGroup, group_id)
        if g:
            s.delete(g); s.commit()


def get_pos_group_product_ids(group_id):
    with get_session() as s:
        return [x.product_id for x in s.query(PosGroupItem).filter(PosGroupItem.group_id == group_id).all()]


def set_pos_group_products(group_id, product_ids):
    """يستبدل قائمة أصناف المجموعة بالكامل بالقائمة الجديدة."""
    require_action("products", "edit")
    with get_session() as s:
        g = s.get(PosGroup, group_id)
        if not g:
            raise ValueError("المجموعة غير موجودة")
        s.query(PosGroupItem).filter(PosGroupItem.group_id == group_id).delete()
        for pid in (product_ids or []):
            s.add(PosGroupItem(group_id=group_id, product_id=int(pid)))
        s.commit()


def list_products_in_pos_group(group_id):
    with get_session() as s:
        rows = s.query(PosGroupItem).options(joinedload(PosGroupItem.product)).filter(PosGroupItem.group_id == group_id).all()
        products = [r.product for r in rows if r.product and r.product.is_active]
        s.expunge_all()
        return products


def get_product_by_sku(sku):
    with get_session() as s:
        return s.query(Product).filter(Product.sku == sku).first()


def get_customer_by_name(name):
    with get_session() as s:
        return s.query(Customer).filter(Customer.name == name).first()


def get_supplier_by_name(name):
    with get_session() as s:
        return s.query(Supplier).filter(Supplier.name == name).first()


def get_account_by_code(code):
    with get_session() as s:
        return s.query(Account).filter(Account.code == code).first()


def get_unit_by_name(name):
    with get_session() as s:
        return s.query(ProductUnit).filter(ProductUnit.name == name).first()


# ======================================================================
# سندات استلام المشتريات (Goods Receipt Notes) - قبل فاتورة المورد
# ======================================================================
def create_goods_receipt(supplier_id, items, location_id, notes="", branch_id=None, cost_center_id=None, invoice_date=None):
    """
    يسجّل استلام بضاعة فعليًا في المخزون (قبل ما توصل فاتورة المورد
    بالضرورة). items: [{"product_id":, "quantity":, "unit_cost": (اختياري)}]
    """
    require_action("purchase_invoices", "create")
    if not items:
        raise ValueError("أضف صنف واحد على الأقل")
    for n, it in enumerate(items, 1):
        if float(it.get("quantity") or 0) <= 0:
            raise ValueError("الكمية لازم تكون أكبر من صفر")
        if it.get("unit_id") and not get_product_unit(int(it["product_id"]), int(it["unit_id"])):
            raise ValueError(f"السطر {n}: الوحدة المختارة مش من وحدات الصنف")

    branch_id = branch_id or default_branch_id()
    cost_center_id = cost_center_id or default_cost_center_id()
    if branch_id and not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    if cost_center_id and not allowed_cost_center(cost_center_id): raise PermissionError("مركز التكلفة غير مسموح لهذا المستخدم")
    if not location_id:
        raise ValueError("اختر المخزن")

    with get_session() as s:
        number = _next_code(s, GoodsReceiptNote, "GRN-")
        receipt = GoodsReceiptNote(
            number=number, date=invoice_date or datetime.datetime.now(), supplier_id=supplier_id,
            location_id=location_id, notes=notes or "", branch_id=branch_id, cost_center_id=cost_center_id,
        )
        s.add(receipt); s.flush()
        for it in items:
            factor = float(convert_to_base_quantity(int(it["product_id"]), float(it["quantity"]), it.get("unit_id"))[2])      # بيرفض كمية <= 0 ووحدة مش تابعة للصنف
            s.add(GoodsReceiptNoteItem(
                receipt_id=receipt.id, product_id=int(it["product_id"]), quantity=float(it["quantity"]),
                unit_cost=float(it.get("unit_cost") or 0), unit_id=int(it["unit_id"]) if it.get("unit_id") else None, unit_factor=factor,
            ))
        s.commit()
        receipt_id, receipt_number = receipt.id, receipt.number

    for it in items:
        create_stock_move(
            product_id=int(it["product_id"]), location_id=location_id, direction="in",
            quantity=float(it["quantity"]), unit_cost=float(it.get("unit_cost") or 0), unit_id=int(it["unit_id"]) if it.get("unit_id") else None,
            reference=f"GRN:{receipt_number}", note=f"سند استلام {receipt_number}",
            branch_id=branch_id, cost_center_id=cost_center_id, _internal=True,
            batch_no=it.get("batch_no"), expiry_date=it.get("expiry_date"), require_expiry=True, move_date=invoice_date, update_cost=True,
        )
    return receipt_id


def list_goods_receipts(limit=200):
    with get_session() as s:
        q = s.query(GoodsReceiptNote).options(
            joinedload(GoodsReceiptNote.supplier), joinedload(GoodsReceiptNote.location),
            joinedload(GoodsReceiptNote.items).joinedload(GoodsReceiptNoteItem.product),
            joinedload(GoodsReceiptNote.items).joinedload(GoodsReceiptNoteItem.unit),
            joinedload(GoodsReceiptNote.purchase_invoice),
        ).order_by(GoodsReceiptNote.date.desc())
        if user_branch_ids():
            q = q.filter((GoodsReceiptNote.branch_id.is_(None)) | (GoodsReceiptNote.branch_id.in_(user_branch_ids())))
        receipts = q.limit(limit).all()
        s.expunge_all()
        return receipts


def get_goods_receipt(receipt_id):
    with get_session() as s:
        r = s.query(GoodsReceiptNote).options(
            joinedload(GoodsReceiptNote.supplier), joinedload(GoodsReceiptNote.location),
            joinedload(GoodsReceiptNote.items).joinedload(GoodsReceiptNoteItem.product),
            joinedload(GoodsReceiptNote.items).joinedload(GoodsReceiptNoteItem.unit),
            joinedload(GoodsReceiptNote.purchase_invoice),
        ).filter(GoodsReceiptNote.id == receipt_id).first()
        if r:
            s.expunge_all()
        return r


def convert_receipt_to_purchase_invoice(receipt_id, price_overrides=None, tax_rate=15.0, invoice_notes=None):
    """
    يحوّل سند استلام (لسه ماتحولش لفاتورة) لفاتورة مشتريات فعلية، بنفس
    الكميات والأصناف، من غير ما يكرر حركة المخزون (اتسجّلت بالفعل وقت
    الاستلام). price_overrides: {product_id: unit_price} لو أسعار الفاتورة
    الفعلية مختلفة عن التكلفة التقديرية وقت الاستلام.
    """
    require_action("purchase_invoices", "create")
    receipt = get_goods_receipt(receipt_id)
    if not receipt:
        raise ValueError("سند الاستلام غير موجود")
    if receipt.invoiced:
        raise ValueError(f"سند الاستلام {receipt.number} اتحوّل لفاتورة مشتريات بالفعل ({receipt.purchase_invoice.number if receipt.purchase_invoice else ''})")
    if receipt.voided:
        raise ValueError("سند الاستلام ده ملغى")
    if not receipt.supplier_id:
        raise ValueError("سند الاستلام مالوش مورد محدد - عدّله وحدد المورد أولاً")

    price_overrides = price_overrides or {}
    items = []
    for it in receipt.items:
        unit_price = price_overrides.get(it.product_id, it.unit_cost or (it.product.cost_price if it.product else 0))
        items.append({"product_id": it.product_id, "quantity": it.quantity, "unit_price": unit_price, "tax_rate": tax_rate, "unit_id": it.unit_id})

    invoice_id = create_purchase_invoice(
        receipt.supplier_id, items, notes=invoice_notes or f"محوّلة من سند استلام {receipt.number}",
        location_id=receipt.location_id, branch_id=receipt.branch_id, cost_center_id=receipt.cost_center_id,
        skip_stock_move=True,
    )

    with get_session() as s:
        r = s.get(GoodsReceiptNote, receipt_id)
        r.invoiced = True
        r.purchase_invoice_id = invoice_id
        s.commit()
    return invoice_id


def void_goods_receipt(receipt_id):
    """إلغاء سند استلام لسه ماتحولش لفاتورة - بيرجّع الكميات اللي دخلت
    المخزون بيه."""
    require_action("purchase_invoices", "delete")
    receipt = get_goods_receipt(receipt_id)
    if not receipt:
        raise ValueError("سند الاستلام غير موجود")
    if receipt.invoiced:
        raise ValueError("مينفعش تلغي سند استلام اتحوّل لفاتورة بالفعل - ألغِ الفاتورة نفسها")
    if receipt.voided:
        raise ValueError("السند ملغى بالفعل")

    for it in receipt.items:
        create_stock_move(
            product_id=it.product_id, location_id=receipt.location_id, direction="out",
            quantity=it.quantity, unit_cost=it.unit_cost or 0, unit_id=it.unit_id,
            reference=f"VOID:{receipt.number}", note=f"إلغاء سند استلام {receipt.number}",
            branch_id=receipt.branch_id, cost_center_id=receipt.cost_center_id, _internal=True,
            batch_lines=_reference_batch_lines(f"GRN:{receipt.number}", it.product_id, "in") or None,
        )
    for pid in {it.product_id for it in receipt.items}:
        recompute_average_cost(pid)

    with get_session() as s:
        r = s.get(GoodsReceiptNote, receipt_id)
        r.voided = True
        s.commit()
    return True


def downloads_dir():
    """يرجّع مسار مجلد 'التنزيلات' (Downloads) الفعلي بتاع جهاز المستخدم -
    عشان أي ملف PDF/Excel يتم إنشاؤه ينزل مباشرة هناك (زي أي تحميل عادي من
    المتصفح)، بدل ما يتخبّى جوه مجلد exports داخل مجلد تثبيت البرنامج.
    لو تعذّر تحديد مجلد Downloads لأي سبب (صلاحيات، نظام تشغيل غريب)،
    يرجع لمجلد exports جوه البرنامج كخطة بديلة آمنة."""
    try:
        home = os.path.expanduser('~')
        downloads = os.path.join(home, 'Downloads')
        if not os.path.isdir(downloads):
            os.makedirs(downloads, exist_ok=True)
        return downloads
    except Exception:
        fallback = downloads_dir()
        os.makedirs(fallback, exist_ok=True)
        return fallback


ACCOUNTING_SETTINGS_FIELDS = [
    ("receivable_account_id", "حساب العملاء (الذمم المدينة) الافتراضي"),
    ("payable_account_id", "حساب الموردين (الذمم الدائنة) الافتراضي"),
    ("sales_account_id", "حساب إيرادات المبيعات الافتراضي"),
    ("purchases_account_id", "حساب المشتريات الافتراضي"),
    ("inventory_account_id", "حساب المخزون"),
    ("cogs_account_id", "حساب تكلفة البضاعة المباعة"),
    ("vat_input_account_id", "حساب ضريبة القيمة المضافة - مدخلات"),
    ("vat_output_account_id", "حساب ضريبة القيمة المضافة - مخرجات"),
    ("cash_account_id", "حساب النقدية الافتراضي"),
    ("retained_earnings_account_id", "حساب الأرباح المرحلة / المحتجزة"),
    ("inventory_gain_account_id", "حساب أرباح فروق الجرد"),
    ("inventory_loss_account_id", "حساب خسائر فروق الجرد"),
    ("salary_expense_account_id", "حساب مصروف الرواتب والأجور"),
    ("salaries_payable_account_id", "حساب الرواتب مستحقة الدفع"),
    ("gosi_payable_account_id", "حساب التأمينات الاجتماعية مستحقة"),
    ("sales_discount_account_id", "حساب الخصومات المسموح بها (خصم فاتورة مبيعات)"),
    ("purchase_discount_account_id", "حساب الخصومات المكتسبة من الموردين (خصم فاتورة مشتريات)"),
    ("employee_advances_account_id", "حساب سلف الموظفين"),
    ("employee_custody_account_id", "حساب عهد الموظفين"),
    ("prepaid_expenses_account_id", "حساب المصروفات المدفوعة مقدمًا"),
    ("asset_loss_account_id", "حساب خسائر استبعاد الأصول الثابتة (عجز الجرد)"),
    ("leave_deduction_account_id", "حساب خصم الإجازات والغياب من الرواتب"),
]


def get_accounting_settings():
    """يرجّع إعدادات ربط الحسابات الافتراضية - نفس الكائن اللي بتستخدمه كل
    عمليات الترحيل المحاسبي التلقائي (فواتير، سندات، رواتب...). لو مفيش
    سجل لسه، بيتعمل واحد فاضي عشان الشاشة متتعطلش."""
    with get_session() as s:
        cfg = s.get(AccountingSettings, 1)
        if not cfg:
            cfg = AccountingSettings(id=1)
            s.add(cfg)
            s.commit()
            s.refresh(cfg)
        s.expunge(cfg)
        return cfg


def update_accounting_settings(**fields):
    """يحدّث ربط أي عدد من الحسابات الافتراضية (زي حساب العملاء، حساب
    المخزون، حساب ضريبة المدخلات...) بالحساب اللي المستخدم يختاره من شجرة
    حساباته الخاصة - بدل ما تكون مربوطة بحسابات ثابتة من البرنامج."""
    require_action("settings", "edit")
    with get_session() as s:
        cfg = s.get(AccountingSettings, 1)
        if not cfg:
            cfg = AccountingSettings(id=1)
            s.add(cfg)
            s.flush()
        valid_keys = {k for k, _ in ACCOUNTING_SETTINGS_FIELDS}
        for key, value in fields.items():
            if key not in valid_keys:
                continue
            setattr(cfg, key, int(value) if value else None)
        s.commit()
        return True


# ======================================================================
# الأصول الثابتة - تسجيل الأصل + دورة إهلاك شهرية بطريقة القسط الثابت
# (Straight-line)، بنفس نمط دورة الرواتب/المخصصات والتأمينات بالظبط
# ======================================================================
def list_fixed_assets(state=None, search=None):
    with get_session() as s:
        q = s.query(FixedAsset).options(
            joinedload(FixedAsset.asset_account), joinedload(FixedAsset.accumulated_depreciation_account),
            joinedload(FixedAsset.depreciation_expense_account),
        )
        if state:
            q = q.filter(FixedAsset.state == state)
        if search:
            like = f"%{search.strip()}%"
            q = q.filter((FixedAsset.name.like(like)) | (FixedAsset.code.like(like)))
        assets = q.order_by(FixedAsset.code).all()
        s.expunge_all()
        return assets


def get_fixed_asset(asset_id):
    with get_session() as s:
        a = s.query(FixedAsset).options(
            joinedload(FixedAsset.asset_account), joinedload(FixedAsset.accumulated_depreciation_account),
            joinedload(FixedAsset.depreciation_expense_account),
        ).filter(FixedAsset.id == asset_id).first()
        if a:
            s.expunge_all()
        return a


def _validate_asset_accounts(asset_account_id, accumulated_depreciation_account_id, depreciation_expense_account_id):
    required = [
        ("حساب الأصل", asset_account_id),
        ("حساب مجمّع الإهلاك", accumulated_depreciation_account_id),
        ("حساب مصروف الإهلاك", depreciation_expense_account_id),
    ]
    for label, aid in required:
        if not aid:
            raise ValueError(f'لازم تحدد "{label}" من شجرة الحسابات')
    with get_session() as s:
        parent_ids = {a.parent_id for a in s.query(Account).all() if a.parent_id}
        for label, aid in required:
            if int(aid) in parent_ids:
                acc = s.get(Account, int(aid))
                raise ValueError(f'"{label}" لازم يكون حساب فرعي - "{acc.code} - {acc.name}" حساب رئيسي مينفعش تترحّل عليه حركات مباشرة')


def _resolve_asset_terms(cost, category_id=None, useful_life_months=None, salvage_value=None,
                         asset_account_id=None, accumulated_depreciation_account_id=None,
                         depreciation_expense_account_id=None, legacy_category="", label=""):
    """يحدد شروط الأصل النهائية: لو اتحددت فئة، الحسابات الثلاثة والعمر
    الإنتاجي ونسبة القيمة التخريدية بتتاخد منها تلقائيًا (وأي قيمة اتدخلت
    يدوي للأصل نفسه بتغلب قيمة الفئة). من غير فئة لازم الحسابات تتبعت صراحةً."""
    cost = float(cost or 0)
    cat_id = int(category_id) if category_id else None
    cat_name = legacy_category or ""
    life = int(useful_life_months) if useful_life_months not in (None, "", 0) else None
    salvage = float(salvage_value) if salvage_value not in (None, "") else None
    suffix = f' للأصل "{label}"' if label else ""
    if cat_id:
        with get_session() as s:
            cat = s.get(AssetCategory, cat_id)
            if not cat:
                raise ValueError("فئة الأصل غير موجودة")
            if not cat.is_active:
                raise ValueError(f'فئة الأصول "{cat.name}" موقوفة')
            cat_name = cat.name
            life = life or cat.useful_life_months
            if salvage is None:
                salvage = round(cost * (cat.salvage_percent or 0) / 100.0, 2)
            asset_account_id = asset_account_id or cat.asset_account_id
            accumulated_depreciation_account_id = accumulated_depreciation_account_id or cat.accumulated_depreciation_account_id
            depreciation_expense_account_id = depreciation_expense_account_id or cat.depreciation_expense_account_id
        if not (asset_account_id and accumulated_depreciation_account_id and depreciation_expense_account_id):
            raise ValueError(f'فئة الأصول "{cat_name}" ناقصة الحسابات - كمّلها من شاشة فئات الأصول الثابتة')
    life = life or 60
    salvage = 0.0 if salvage is None else salvage
    if life <= 0:
        raise ValueError(f"العمر الإنتاجي (بالشهور){suffix} يجب أن يكون أكبر من صفر")
    if salvage < 0 or salvage >= cost:
        raise ValueError(f"القيمة التخريدية{suffix} يجب أن تكون أقل من تكلفة الأصل")
    _validate_asset_accounts(asset_account_id, accumulated_depreciation_account_id, depreciation_expense_account_id)
    return {
        "category_id": cat_id, "category": cat_name, "useful_life_months": life, "salvage_value": salvage,
        "asset_account_id": int(asset_account_id), "accumulated_depreciation_account_id": int(accumulated_depreciation_account_id),
        "depreciation_expense_account_id": int(depreciation_expense_account_id),
    }


def create_fixed_asset(code, name, purchase_date, cost, category="", salvage_value=None, useful_life_months=None,
                        asset_account_id=None, accumulated_depreciation_account_id=None, depreciation_expense_account_id=None,
                        branch_id=None, cost_center_id=None, notes="", category_id=None):
    """يسجّل أصل ثابت جديد في السجل (مش بيعمل قيد اقتناء تلقائي - لو
    الأصل اتشرى بفاتورة مشتريات أو قيد يدوي، سجّله هنا للمتابعة والإهلاك
    بس). اختار فئة الأصل (category_id) والحسابات والعمر الإنتاجي والقيمة
    التخريدية بتتاخد منها تلقائيًا - ومتقدرش تتخطاها إلا لو بعتّها صراحةً."""
    require_action("fixed_assets", "create")
    code = (code or "").strip()
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم الأصل مطلوب")
    cost = float(cost or 0)
    if cost <= 0:
        raise ValueError("تكلفة الأصل يجب أن تكون أكبر من صفر")
    t = _resolve_asset_terms(cost, category_id, useful_life_months, salvage_value, asset_account_id,
                             accumulated_depreciation_account_id, depreciation_expense_account_id, category, name)

    with get_session() as s:
        if not code:
            code = _next_asset_code(s, t["category_id"])
        elif s.query(FixedAsset).filter(FixedAsset.code == code).count():
            raise ValueError(f'الكود "{code}" مستخدم بالفعل لأصل آخر')
        a = FixedAsset(
            code=code, name=name, category=t["category"], category_id=t["category_id"], purchase_date=purchase_date, cost=cost,
            salvage_value=t["salvage_value"], useful_life_months=t["useful_life_months"], accumulated_depreciation=0.0,
            state="active", notes=notes or "", branch_id=branch_id or default_branch_id(), cost_center_id=cost_center_id,
            asset_account_id=t["asset_account_id"], accumulated_depreciation_account_id=t["accumulated_depreciation_account_id"],
            depreciation_expense_account_id=t["depreciation_expense_account_id"],
        )
        s.add(a); s.commit(); s.refresh(a)
        return a.id


def update_fixed_asset(asset_id, code, name, purchase_date, cost, category="", salvage_value=None, useful_life_months=None,
                        asset_account_id=None, accumulated_depreciation_account_id=None, depreciation_expense_account_id=None,
                        branch_id=None, cost_center_id=None, notes="", category_id=None):
    require_action("fixed_assets", "edit")
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم الأصل مطلوب")
    cost = float(cost or 0)
    if cost <= 0:
        raise ValueError("تكلفة الأصل يجب أن تكون أكبر من صفر")

    with get_session() as s:
        a = s.get(FixedAsset, int(asset_id))
        if not a:
            raise ValueError("الأصل غير موجود")
        old_accounts = (a.asset_account_id, a.accumulated_depreciation_account_id, a.depreciation_expense_account_id)
        has_history = bool(a.accumulated_depreciation or a.purchase_invoice_id)
        if not category_id:   # من غير فئة: نحتفظ بحسابات الأصل الحالية
            asset_account_id = asset_account_id or a.asset_account_id
            accumulated_depreciation_account_id = accumulated_depreciation_account_id or a.accumulated_depreciation_account_id
            depreciation_expense_account_id = depreciation_expense_account_id or a.depreciation_expense_account_id
        legacy_name = category or a.category

    t = _resolve_asset_terms(cost, category_id, useful_life_months, salvage_value, asset_account_id,
                             accumulated_depreciation_account_id, depreciation_expense_account_id, legacy_name, name)
    new_accounts = (t["asset_account_id"], t["accumulated_depreciation_account_id"], t["depreciation_expense_account_id"])
    if new_accounts != old_accounts and has_history:
        raise ValueError("مينفعش تغيّر حسابات أصل اترحّل عليه إهلاك أو مربوط بفاتورة شراء (الحسابات القديمة عليها أرصدة) - سجّل قيد تسوية بدل كده")

    with get_session() as s:
        a = s.get(FixedAsset, int(asset_id))
        if code and code != a.code:
            if s.query(FixedAsset).filter(FixedAsset.code == code, FixedAsset.id != a.id).count():
                raise ValueError(f'الكود "{code}" مستخدم بالفعل لأصل آخر')
            a.code = code
        a.name = name; a.category = t["category"]; a.category_id = t["category_id"]; a.purchase_date = purchase_date
        a.cost = cost; a.salvage_value = t["salvage_value"]; a.useful_life_months = t["useful_life_months"]
        a.branch_id = branch_id; a.cost_center_id = cost_center_id; a.notes = notes or ""
        a.asset_account_id, a.accumulated_depreciation_account_id, a.depreciation_expense_account_id = new_accounts
        s.commit()
        return a.id


# ------------------------- فئات الأصول الثابتة -------------------------
def list_asset_categories(active_only=False):
    with get_session() as s:
        q = s.query(AssetCategory).options(
            joinedload(AssetCategory.asset_account), joinedload(AssetCategory.accumulated_depreciation_account),
            joinedload(AssetCategory.depreciation_expense_account),
        )
        if active_only:
            q = q.filter(AssetCategory.is_active.is_(True))
        cats = q.order_by(AssetCategory.name).all()
        for c in cats:
            c.next_code = _preview_next_asset_code(s, c)
        s.expunge_all()
        return cats


def get_asset_category(category_id):
    with get_session() as s:
        c = s.query(AssetCategory).options(
            joinedload(AssetCategory.asset_account), joinedload(AssetCategory.accumulated_depreciation_account),
            joinedload(AssetCategory.depreciation_expense_account),
        ).filter(AssetCategory.id == category_id).first()
        if c:
            c.next_code = _preview_next_asset_code(s, c)
            s.expunge_all()
        return c


def _parse_code_start(text):
    """أول كود للفئة (مثلاً LAP-0001 أو 1001) -> (البادئة، عدد الخانات، الرقم). بيتوقف
    عند آخر مجموعة أرقام في النص: اللي قبلها بادئة ثابتة واللي هي بتتزوّد."""
    t = (text or "").strip()
    if not t:
        return None
    if len(t) > 25:
        raise ValueError("بداية التسلسل طويلة (الحد الأقصى 25 حرف)")
    m = re.match(r"^(.*?)(\d+)$", t)
    if not m:
        raise ValueError('بداية التسلسل لازم تنتهي برقم - مثال: LAP-0001 أو 1001')
    prefix, digits = m.group(1), m.group(2)
    return prefix, len(digits), int(digits)


def _next_asset_code(session, category_id=None):
    """الكود التالي لأصل جديد: من تسلسل فئته لو الفئة ليها بداية تسلسل (وبيتخطى أي كود
    مستخدم بالفعل)، وإلا من التسلسل العام FA-xxxxx. لازم يتنده جوه نفس الجلسة اللي
    بتسجّل الأصل."""
    cat = session.get(AssetCategory, int(category_id)) if category_id else None
    if not cat or not cat.code_start or cat.code_next is None:
        return _next_code(session, FixedAsset, "FA-")
    n = cat.code_next
    width = cat.code_width or 0
    while True:
        code = f"{cat.code_prefix or ''}{n:0{width}d}"
        if not session.query(FixedAsset.id).filter(FixedAsset.code == code).first():
            break
        n += 1
    cat.code_next = n + 1
    session.flush()
    return code


def _preview_next_asset_code(session, cat):
    """الكود اللي هيتاخد للأصل الجاي (للعرض بس - من غير ما يستهلك التسلسل)."""
    if not cat.code_start or cat.code_next is None:
        return None
    n = cat.code_next
    width = cat.code_width or 0
    while True:
        code = f"{cat.code_prefix or ''}{n:0{width}d}"
        if not session.query(FixedAsset.id).filter(FixedAsset.code == code).first():
            return code
        n += 1


def _check_category_fields(name, useful_life_months, salvage_percent):
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم الفئة مطلوب")
    life = int(useful_life_months or 0)
    if life <= 0:
        raise ValueError("العمر الإنتاجي (بالشهور) يجب أن يكون أكبر من صفر")
    pct = float(salvage_percent or 0)
    if pct < 0 or pct >= 100:
        raise ValueError("نسبة القيمة التخريدية يجب أن تكون من 0 إلى أقل من 100%")
    return name, life, pct


def create_asset_category(name, asset_account_id, accumulated_depreciation_account_id, depreciation_expense_account_id,
                          useful_life_months=60, salvage_percent=0.0, code_start=None):
    require_action("asset_categories", "create")
    name, life, pct = _check_category_fields(name, useful_life_months, salvage_percent)
    parsed = _parse_code_start(code_start)
    _validate_asset_accounts(asset_account_id, accumulated_depreciation_account_id, depreciation_expense_account_id)
    with get_session() as s:
        if s.query(AssetCategory).filter(AssetCategory.name == name).count():
            raise ValueError(f'فئة "{name}" موجودة بالفعل')
        c = AssetCategory(
            name=name, useful_life_months=life, salvage_percent=pct, is_active=True,
            asset_account_id=int(asset_account_id), accumulated_depreciation_account_id=int(accumulated_depreciation_account_id),
            depreciation_expense_account_id=int(depreciation_expense_account_id),
        )
        if parsed:
            c.code_start = code_start.strip(); c.code_prefix, c.code_width, c.code_next = parsed
        s.add(c); s.commit(); s.refresh(c)
        return c.id


def update_asset_category(category_id, name, asset_account_id, accumulated_depreciation_account_id, depreciation_expense_account_id,
                          useful_life_months=60, salvage_percent=0.0, is_active=True, code_start=None):
    """تعديل الفئة بيسري على الأصول الجديدة. الأصول الحالية بتفضل بحساباتها
    لحد ما تدوس 'تطبيق حسابات الفئة على أصولها' (apply_asset_category_accounts)،
    عشان أي قيود اترحّلت قبل كده ما تتلخبطش."""
    require_action("asset_categories", "edit")
    name, life, pct = _check_category_fields(name, useful_life_months, salvage_percent)
    parsed = _parse_code_start(code_start)
    _validate_asset_accounts(asset_account_id, accumulated_depreciation_account_id, depreciation_expense_account_id)
    with get_session() as s:
        c = s.get(AssetCategory, int(category_id))
        if not c:
            raise ValueError("الفئة غير موجودة")
        if s.query(AssetCategory).filter(AssetCategory.name == name, AssetCategory.id != c.id).count():
            raise ValueError(f'فئة "{name}" موجودة بالفعل')
        new_start = (code_start or "").strip() or None
        if new_start != (c.code_start or None):   # اتغيّرت بداية التسلسل: نبدأ من أولها من جديد
            if parsed:
                c.code_start = new_start; c.code_prefix, c.code_width, c.code_next = parsed
            else:
                c.code_start = c.code_prefix = c.code_width = c.code_next = None
        renamed = c.name != name
        c.name = name; c.useful_life_months = life; c.salvage_percent = pct; c.is_active = bool(is_active)
        c.asset_account_id = int(asset_account_id)
        c.accumulated_depreciation_account_id = int(accumulated_depreciation_account_id)
        c.depreciation_expense_account_id = int(depreciation_expense_account_id)
        if renamed:
            s.query(FixedAsset).filter(FixedAsset.category_id == c.id).update({"category": name})
        s.commit()
        return c.id


def delete_asset_category(category_id):
    require_action("asset_categories", "delete")
    with get_session() as s:
        c = s.get(AssetCategory, int(category_id))
        if not c:
            raise ValueError("الفئة غير موجودة")
        used = s.query(FixedAsset).filter(FixedAsset.category_id == c.id).count()
        if used:
            raise ValueError(f"مينفعش تحذف الفئة - مستخدمة في {used} أصل (وقّفها بدل الحذف)")
        s.delete(c); s.commit()


def apply_asset_category_accounts(category_id):
    """يطبّق حسابات الفئة الحالية على أصولها. بيتخطى الأصول اللي اترحّل عليها
    إهلاك أو مربوطة بفاتورة شراء (حساباتها القديمة عليها أرصدة). بيرجّع
    (اتحدّث، اتخطّى)."""
    require_action("asset_categories", "edit")
    with get_session() as s:
        c = s.get(AssetCategory, int(category_id))
        if not c:
            raise ValueError("الفئة غير موجودة")
        updated = skipped = 0
        for a in s.query(FixedAsset).filter(FixedAsset.category_id == c.id, FixedAsset.state != "disposed").all():
            new = (c.asset_account_id, c.accumulated_depreciation_account_id, c.depreciation_expense_account_id)
            if new == (a.asset_account_id, a.accumulated_depreciation_account_id, a.depreciation_expense_account_id):
                continue
            if a.accumulated_depreciation or a.purchase_invoice_id:
                skipped += 1
                continue
            a.asset_account_id, a.accumulated_depreciation_account_id, a.depreciation_expense_account_id = new
            updated += 1
        s.commit()
        return updated, skipped


def delete_fixed_asset(asset_id):
    require_action("fixed_assets", "delete")
    with get_session() as s:
        a = s.get(FixedAsset, int(asset_id))
        if not a:
            raise ValueError("الأصل غير موجود")
        if a.accumulated_depreciation:
            raise ValueError("مينفعش تحذف أصل اترحّل عليه إهلاك بالفعل")
        s.delete(a)
        s.commit()


def dispose_fixed_asset(asset_id, disposal_date, disposal_amount=0.0, loss_account_id=None):
    """يشطب أصل (بيع/إحلال/تلف) - بيقفل رصيد الأصل ومجمّع إهلاكه، وبيسجّل
    الخسارة في حساب خسائر استبعاد الأصول (من الإعدادات، أو loss_account_id لو اتبعت)،
    وإلا في حساب مصروف الإهلاك للأصل. الربح بيتسجّل في حساب مصروف الإهلاك (تبسيطًا).
    القيد بيتعمل الأول، وبعدين الأصل بيتعلّم مستبعد - عشان لو القيد فشل (فترة مقفولة
    مثلاً) الأصل يفضل زي ما هو."""
    require_action("fixed_assets", "post")
    disposal_amount = float(disposal_amount or 0)
    with get_session() as s:
        a = s.get(FixedAsset, int(asset_id))
        if not a:
            raise ValueError("الأصل غير موجود")
        if a.state == "disposed":
            raise ValueError("الأصل مستبعد بالفعل")
        cost = a.cost; accumulated = a.accumulated_depreciation or 0.0
        nbv = max(0.0, cost - accumulated)
        asset_account_id = a.asset_account_id
        accumulated_account_id = a.accumulated_depreciation_account_id
        expense_account_id = a.depreciation_expense_account_id
        cfg = s.get(AccountingSettings, 1)
        cash_account_id = cfg.cash_account_id if cfg else None
        default_loss_account_id = cfg.asset_loss_account_id if cfg else None
        asset_name = a.name

    gain_loss = disposal_amount - nbv  # موجب = ربح، سالب = خسارة
    lines = [
        {"account_id": accumulated_account_id, "debit": round(accumulated, 2)},
        {"account_id": asset_account_id, "credit": round(cost, 2)},
    ]
    if disposal_amount:
        if not cash_account_id:
            raise ValueError("إعداد حساب النقدية الافتراضي ناقص - راجع الإعدادات المحاسبية")
        lines.append({"account_id": cash_account_id, "debit": round(disposal_amount, 2)})
    if gain_loss > 0.01:
        lines.append({"account_id": expense_account_id, "credit": round(gain_loss, 2)})
    elif gain_loss < -0.01:
        lines.append({"account_id": loss_account_id or default_loss_account_id or expense_account_id, "debit": round(-gain_loss, 2)})

    jid = create_journal_entry(
        lines, reference=f"DISPOSE-{asset_id}", description=f"استبعاد أصل ثابت: {asset_name}",
        source_type="fixed_asset_disposal", source_id=asset_id, entry_date=disposal_date,
    )
    with get_session() as s:
        a = s.get(FixedAsset, int(asset_id))
        a.state = "disposed"; a.disposal_date = disposal_date; a.disposal_amount = disposal_amount
        s.commit()
    return jid


def list_depreciation_runs(limit=100):
    with get_session() as s:
        runs = s.query(DepreciationRun).options(joinedload(DepreciationRun.items)).order_by(
            DepreciationRun.year.desc(), DepreciationRun.month.desc()
        ).limit(limit).all()
        s.expunge_all()
        return runs


def get_depreciation_run(run_id):
    with get_session() as s:
        r = s.query(DepreciationRun).options(
            joinedload(DepreciationRun.items).joinedload(DepreciationRunItem.asset),
            joinedload(DepreciationRun.items).joinedload(DepreciationRunItem.expense_account),
            joinedload(DepreciationRun.items).joinedload(DepreciationRunItem.accumulated_account),
        ).filter(DepreciationRun.id == run_id).first()
        if r:
            s.expunge_all()
        return r


def create_depreciation_run(month, year, branch_id=None):
    """ينشئ دورة إهلاك جديدة - بند تلقائي لكل أصل نشط لسه ماوصلش لكامل
    قيمته القابلة للإهلاك، بقيمة القسط الشهري (بطريقة القسط الثابت) أو
    الباقي المتبقي أيهما أقل."""
    require_action("fixed_assets", "create")
    month = int(month); year = int(year)
    if month < 1 or month > 12:
        raise ValueError("الشهر غير صحيح")
    with get_session() as s:
        existing = s.query(DepreciationRun).filter(DepreciationRun.month == month, DepreciationRun.year == year).first()
        if existing:
            raise ValueError(f"دورة إهلاك شهر {month}/{year} موجودة بالفعل (رقم {existing.number})")
        number = _next_code(s, DepreciationRun, "DEP-")
        run = DepreciationRun(number=number, month=month, year=year, branch_id=branch_id or default_branch_id(), state="draft")
        s.add(run); s.flush()

        assets = s.query(FixedAsset).filter(FixedAsset.state == "active").all()
        count = 0
        for asset in assets:
            remaining = round(asset.depreciable_amount - (asset.accumulated_depreciation or 0), 2)
            if remaining <= 0:
                continue
            amount = min(asset.monthly_depreciation, remaining)
            if amount <= 0:
                continue
            s.add(DepreciationRunItem(
                run_id=run.id, asset_id=asset.id, amount=amount,
                expense_account_id=asset.depreciation_expense_account_id,
                accumulated_account_id=asset.accumulated_depreciation_account_id,
            ))
            count += 1
        s.commit(); s.refresh(run)
        if count == 0:
            s.delete(s.get(DepreciationRun, run.id)); s.commit()
            raise ValueError("مفيش أصول لسه محتاجة إهلاك للفترة دي")
        return run.id


def delete_depreciation_run(run_id):
    require_action("fixed_assets", "delete")
    with get_session() as s:
        run = s.get(DepreciationRun, run_id)
        if not run:
            raise ValueError("الدورة غير موجودة")
        if run.state == "posted":
            raise ValueError("مينفعش تحذف دورة مرحّلة - رجّعها مسودة أولاً")
        s.delete(run)
        s.commit()


def post_depreciation_run(run_id):
    """يرحّل دورة الإهلاك: قيد واحد (مدين مصروف الإهلاك / دائن مجمّع
    الإهلاك) مجمّع حسب حساب كل أصل، وبيحدّث مجمّع إهلاك كل أصل بالمبلغ
    المرحّل (وبيعلّمه 'مستهلك بالكامل' لو وصل لآخر قيمة قابلة للإهلاك)."""
    require_action("fixed_assets", "post")
    with get_session() as s:
        run = s.get(DepreciationRun, run_id)
        if not run:
            raise ValueError("الدورة غير موجودة")
        if run.state == "posted":
            raise ValueError("الدورة مرحّلة بالفعل")
        items = s.query(DepreciationRunItem).options(joinedload(DepreciationRunItem.asset)).filter(DepreciationRunItem.run_id == run.id).all()
        if not items:
            raise ValueError("مفيش بنود في الدورة دي")

        debit_by_account = {}
        credit_by_account = {}
        for it in items:
            if not it.expense_account_id or not it.accumulated_account_id:
                asset_name = it.asset.name if it.asset else f"#{it.asset_id}"
                raise ValueError(f'الأصل "{asset_name}" مفيهوش حسابات إهلاك محددة')
            debit_by_account[it.expense_account_id] = debit_by_account.get(it.expense_account_id, 0.0) + it.amount
            credit_by_account[it.accumulated_account_id] = credit_by_account.get(it.accumulated_account_id, 0.0) + it.amount

        entry_date = datetime.datetime(run.year, run.month, 1)
        run_branch_id = run.branch_id
        run_number, run_month, run_year = run.number, run.month, run.year

        lines = [{"account_id": aid, "debit": round(amt, 2)} for aid, amt in debit_by_account.items()]
        lines += [{"account_id": aid, "credit": round(amt, 2)} for aid, amt in credit_by_account.items()]

        jid = create_journal_entry(
            lines, reference=run_number, description=f"إهلاك أصول ثابتة شهر {run_month}/{run_year}",
            source_type="depreciation", source_id=run_id, entry_date=entry_date, branch_id=run_branch_id,
        )

        for it in items:
            asset = s.get(FixedAsset, it.asset_id)
            asset.accumulated_depreciation = round((asset.accumulated_depreciation or 0) + it.amount, 2)
            if asset.accumulated_depreciation >= asset.depreciable_amount - 0.01:
                asset.state = "fully_depreciated"

        run = s.get(DepreciationRun, run_id)
        run.state = "posted"
        run.journal_entry_id = jid
        s.commit()
    return jid


def reopen_depreciation_run(run_id):
    """يرجّع دورة إهلاك مرحّلة لمسودة - بيرجّع مجمّع إهلاك كل أصل زي ما
    كان قبل الدورة دي (بيطرح مبلغها)، وبيرجّع حالة الأصل لنشط لو كان
    اتعلّم مستهلك بالكامل بسببها."""
    require_action("fixed_assets", "edit")
    with get_session() as s:
        run = s.get(DepreciationRun, run_id)
        if not run:
            raise ValueError("الدورة غير موجودة")
        if run.state != "posted":
            raise ValueError("الدورة مسودة بالفعل")
        items = s.query(DepreciationRunItem).filter(DepreciationRunItem.run_id == run_id).all()
        for it in items:
            asset = s.get(FixedAsset, it.asset_id)
            if asset:
                asset.accumulated_depreciation = round(max(0.0, (asset.accumulated_depreciation or 0) - it.amount), 2)
                if asset.state == "fully_depreciated":
                    asset.state = "active"
        jid = run.journal_entry_id
        run.state = "draft"
        s.commit()
    if jid:
        try:
            set_journal_entry_draft_by_source(jid)
        except Exception:
            pass


# ======================================================================
# فواتير مشتريات الأصول الثابتة - فاتورة مشتريات عادية (مورد/ضريبة/
# مستحقات) لكن كل سطر فيها بيسجّل أصل ثابت جديد بدل صنف مخزون، وبيترحّل
# مباشرة على حساب الأصل بدل المخزون.
# ======================================================================
MAX_ASSET_QTY_PER_LINE = 1000   # حماية من كتابة كمية غلط بالغلط


def create_asset_purchase_invoice(supplier_id, items, notes="", invoice_date=None, branch_id=None, cost_center_id=None):
    """
    items: [{"name","category_id","cost","tax_rate","quantity"}] - cost = تكلفة الوحدة الواحدة،
    و quantity = عدد الوحدات (افتراضي 1). الحسابات والعمر الإنتاجي والقيمة
    التخريدية بتتاخد من فئة الأصل تلقائيًا (وممكن تتبعت صراحةً لتغلب قيمة الفئة).
    كل وحدة بتتسجّل كأصل ثابت مستقل في سجل الأصول (بكود مختلف عشان الإهلاك
    والاستبعاد يبقوا لكل وحدة لوحدها)، كلهم مربوطين بفاتورة المورد دي. الفاتورة بتترحّل فورًا (مدين حساب كل أصل + ضريبة
    مدخلات / دائن حساب المورد)."""
    require_action("purchase_invoices", "create")
    require_action("fixed_assets", "create")
    if not items:
        raise ValueError("أضف أصل واحد على الأقل")
    resolved = []
    for it in items:
        name = (it.get("name") or "").strip()
        if not name:
            raise ValueError("اسم الأصل مطلوب لكل سطر")
        cost = float(it.get("cost") or 0)
        if cost <= 0:
            raise ValueError(f'تكلفة الأصل "{name}" يجب أن تكون أكبر من صفر')
        raw_qty = it.get("quantity")
        try:
            qty = 1 if raw_qty in (None, "") else int(float(raw_qty))   # 0 مش "فاضي" - بيترفض تحت
        except (TypeError, ValueError):
            raise ValueError(f'كمية الأصل "{name}" غير صحيحة')
        if qty < 1:
            raise ValueError(f'كمية الأصل "{name}" يجب أن تكون 1 أو أكثر')
        if qty > MAX_ASSET_QTY_PER_LINE:
            raise ValueError(f'كمية الأصل "{name}" أكبر من الحد المسموح ({MAX_ASSET_QTY_PER_LINE}) في سطر واحد - قسّمها على أكتر من سطر')
        terms = _resolve_asset_terms(
            cost, it.get("category_id"), it.get("useful_life_months"), it.get("salvage_value"),
            it.get("asset_account_id"), it.get("accumulated_depreciation_account_id"),
            it.get("depreciation_expense_account_id"), it.get("category"), name,
        )
        resolved.append((it, terms, qty))

    branch_id = branch_id or default_branch_id()
    cost_center_id = cost_center_id or default_cost_center_id()
    if branch_id and not allowed_branch(branch_id): raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    if cost_center_id and not allowed_cost_center(cost_center_id): raise PermissionError("مركز التكلفة غير مسموح لهذا المستخدم")

    settings = get_company_settings()
    with get_session() as s:
        number = _next_invoice_number(s, PurchaseInvoice, "FAP-")
        invoice = PurchaseInvoice(
            number=number, date=invoice_date or datetime.datetime.now(), supplier_id=supplier_id,
            branch_id=branch_id, cost_center_id=cost_center_id, discount=0.0,
            notes=(notes or "") + " [فاتورة مشتريات أصول ثابتة]",
        )
        s.add(invoice); s.flush()

        subtotal = 0.0; tax_total = 0.0
        line_debits = []   # (حساب الأصل، إجمالي السطر) - كل سطر بمبلغه المقرّب مرة واحدة
        for it, t, qty in resolved:
            unit_cost = float(it["cost"]); tax_rate = float(it.get("tax_rate", 15))
            line_total = round(unit_cost * qty, 2)
            subtotal += line_total
            tax_total += round(line_total * tax_rate / 100.0, 2)
            line_debits.append((t["asset_account_id"], line_total))
            for _ in range(qty):
                code = _next_asset_code(s, t["category_id"])
                a = FixedAsset(
                    code=code, name=it["name"].strip(), category=t["category"], category_id=t["category_id"],
                    purchase_date=invoice.date, cost=unit_cost, salvage_value=t["salvage_value"],
                    useful_life_months=t["useful_life_months"], accumulated_depreciation=0.0, state="active",
                    branch_id=branch_id, cost_center_id=cost_center_id, purchase_invoice_id=invoice.id,
                    asset_account_id=t["asset_account_id"],
                    accumulated_depreciation_account_id=t["accumulated_depreciation_account_id"],
                    depreciation_expense_account_id=t["depreciation_expense_account_id"],
                )
                s.add(a); s.flush()

        invoice.subtotal = round(subtotal, 2)
        invoice.tax_total = round(tax_total, 2)
        invoice.total = round(subtotal + tax_total, 2)
        s.commit()
        invoice_id, invoice_number, invoice_date_val, invoice_total, invoice_tax = invoice.id, invoice.number, invoice.date, invoice.total, invoice.tax_total

    cfg = _accounting_settings()
    supplier_account_id = None
    if supplier_id:
        with get_session() as s:
            sup = s.get(Supplier, int(supplier_id))
            supplier_account_id = sup.account_id if sup else None
    payable_account_id = supplier_account_id or cfg.payable_account_id
    if not payable_account_id:
        raise ValueError("إعداد حساب الموردين الافتراضي ناقص - راجع الإعدادات المحاسبية")

    by_account = {}
    for account_id, line_total in line_debits:
        by_account[account_id] = by_account.get(account_id, 0.0) + line_total

    lines = [{"account_id": aid, "debit": round(amt, 2)} for aid, amt in by_account.items()]
    if invoice_tax:
        lines.append({"account_id": cfg.vat_input_account_id, "debit": round(invoice_tax, 2)})
    lines.append({"account_id": payable_account_id, "credit": round(invoice_total, 2)})

    create_journal_entry(
        lines, reference=invoice_number, description=f"فاتورة مشتريات أصول ثابتة {invoice_number}",
        source_type="asset_purchase_invoice", source_id=invoice_id, entry_date=invoice_date_val,
        branch_id=branch_id, cost_center_id=cost_center_id,
    )
    return invoice_id


def list_asset_purchase_invoices(limit=200):
    """فواتير مشتريات الأصول بس - بيتعرّفوا بإنهم مالهومش أي سطر أصناف
    عادي (items فاضية) لكن مربوط بيهم أصل ثابت واحد على الأقل."""
    with get_session() as s:
        invoices = s.query(PurchaseInvoice).options(
            joinedload(PurchaseInvoice.supplier),
        ).filter(PurchaseInvoice.number.like("FAP-%")).order_by(PurchaseInvoice.date.desc()).limit(limit).all()
        result = []
        for inv in invoices:
            assets = s.query(FixedAsset).filter(FixedAsset.purchase_invoice_id == inv.id).order_by(FixedAsset.id).all()
            result.append((inv, assets))
        s.expunge_all()
        return result


def generate_asset_stickers_pdf(asset_ids, preset="thermal_50x30", code_type="code128", copies=1,
                                border=False, start_slot=1, include_company=True):
    """يولّد PDF فيه استيكر باركود لكل أصل من asset_ids (الباركود = كود الأصل).
    بيرجّع dict: path, count, qr_fallback, warnings."""
    require_action("fixed_assets", "view")
    from .asset_labels import render_stickers, default_output_path
    ids = sorted({int(i) for i in (asset_ids or [])})
    if not ids:
        raise ValueError("اختار أصل واحد على الأقل")
    with get_session() as s:
        assets = s.query(FixedAsset).filter(FixedAsset.id.in_(ids)).order_by(FixedAsset.id).all()
        items = [{"code": a.code, "name": a.name} for a in assets]
    if not items:
        raise ValueError("الأصول المطلوبة مش موجودة")
    company = get_company_settings()
    company_name = (company.name or "") if include_company and company else ""
    path = default_output_path(downloads_dir(), [i["code"] for i in items])
    return render_stickers(items, path, preset=preset, code_type=code_type, copies=copies,
                           border=border, start_slot=start_slot, company_name=company_name)


def product_label_rows(search=None, category_id=None):
    """صفوف لشاشة طباعة ملصقات الأصناف: كود/اسم/باركود فعلي/سعر شامل الضريبة."""
    require_action("product_labels", "view")
    with get_session() as s:
        out = []
        for p in list_products(search=search, category_id=category_id):
            lines = s.query(ProductUnitLine).filter(ProductUnitLine.product_id == p.id, ProductUnitLine.barcode != "").all()
            lines.sort(key=lambda l: (abs(float(l.factor_to_base or 1) - 1.0) > 1e-9, l.id))
            bc = lines[0].barcode if lines else p.sku
            price = round(float(p.sale_price or 0) * (1 + float(p.tax_rate or 0) / 100.0), 2)
            out.append({"id": p.id, "sku": p.sku, "name": p.name, "barcode": bc, "price": price, "has_barcode": bool(lines)})
        return out


def generate_product_labels_pdf(entries, preset="thermal_50x30", border=False, start_slot=1, show_price=True,
                                show_name=True, currency="", price_with_tax=True):
    """entries: [{"product_id", "copies"}] -> PDF ملصقات (اسم + سعر + باركود). بيرجّع {path, count}."""
    require_action("product_labels", "view")
    from .product_labels import render_labels, default_output_path
    want = {int(e["product_id"]): int(e.get("copies") or 1) for e in (entries or [])}
    if not want:
        raise ValueError("اختار صنف واحد على الأقل")
    rows = {r["id"]: r for r in product_label_rows()}
    items = []
    for pid, n in want.items():
        r = rows.get(pid)
        if not r:
            continue
        price = r["price"]
        if not price_with_tax:
            with get_session() as s:
                p = s.get(Product, pid); price = round(float(p.sale_price or 0), 2)
        items.append({"barcode": r["barcode"], "name": r["name"], "price": price, "copies": n})
    return render_labels(items, default_output_path(downloads_dir()), preset=preset, border=border, start_slot=start_slot,
                         show_price=show_price, show_name=show_name, currency=currency)


# ======================================================================
# جرد الأصول الثابتة بالباركود: جلسة بلقطة من الأصول المتوقعة + مسح باركود
# + تقرير عجز (متوقع ومش موجود) وزيادة (موجود ومش متوقع)
# ======================================================================
INVENTORY_SCOPES = ("all", "category", "branch", "cost_center")
EXTRA_REASON_LABELS = {
    "out_of_scope": "أصل مسجّل لكن خارج نطاق الجرد",
    "disposed": "أصل مستبعد من السجلات لكنه موجود فعليًا",
    "unknown": "كود غير مسجّل في النظام",
}


def _norm_scanned_code(raw):
    """بيشيل أي رموز تحكم (Enter/Tab اللي الماسح بيضيفها) والمسافات الزايدة."""
    return re.sub(r"[\x00-\x1f\x7f]", "", str(raw or "")).strip()


def _current_username():
    u = _get_user()
    if not u:
        return ""
    return (u.get("username") if isinstance(u, dict) else getattr(u, "username", "")) or ""


def _natural_code_key(code):
    return tuple(int(x) if x.isdigit() else x for x in re.split(r"(\d+)", str(code or "")))


def _inventory_line_dict(l):
    return {
        "id": l.id, "asset_id": l.asset_id, "code": l.code, "name": l.name or "", "category": l.category or "",
        "cost": l.cost or 0.0, "book_value": l.book_value or 0.0, "kind": l.kind, "reason": l.extra_reason,
        "reason_label": EXTRA_REASON_LABELS.get(l.extra_reason or "", ""), "scanned_at": l.scanned_at,
        "scan_count": l.scan_count or 0, "method": l.method,
        "disposal_journal_id": l.disposal_journal_id, "disposed_at": l.disposed_at, "disposal_loss": l.disposal_loss or 0.0,
        "disposal_ref": "",
    }


def _inventory_counts(s, inventory_id):
    from sqlalchemy import func
    L = AssetInventoryLine
    expected = s.query(func.count(L.id)).filter(L.inventory_id == inventory_id, L.kind == "expected").scalar() or 0
    found = s.query(func.count(L.id)).filter(L.inventory_id == inventory_id, L.kind == "expected", L.scanned_at.isnot(None)).scalar() or 0
    surplus = s.query(func.count(L.id)).filter(L.inventory_id == inventory_id, L.kind == "extra").scalar() or 0
    return {"expected": expected, "found": found, "shortage": expected - found, "surplus": surplus}


def _inventory_header(s, inv):
    d = {"id": inv.id, "number": inv.number, "name": inv.name, "date": inv.date, "state": inv.state,
         "scope_type": inv.scope_type, "scope_id": inv.scope_id, "scope_label": inv.scope_label or "",
         "notes": inv.notes or "", "created_by": inv.created_by or "", "closed_at": inv.closed_at}
    d.update(_inventory_counts(s, inv.id))
    return d


def create_asset_inventory(name="", scope_type="all", scope_id=None, notes=""):
    """يبدأ جلسة جرد: بياخد لقطة من الأصول غير المستبعدة في النطاق المطلوب."""
    require_action("asset_inventory", "create")
    if scope_type not in INVENTORY_SCOPES:
        raise ValueError("نطاق الجرد غير معروف")
    if scope_type != "all" and not scope_id:
        raise ValueError("حدد النطاق (الفئة / الفرع / مركز التكلفة)")
    with get_session() as s:
        q = s.query(FixedAsset).filter(FixedAsset.state != "disposed")
        label = "كل الأصول"
        if scope_type == "category":
            c = s.get(AssetCategory, int(scope_id))
            if not c: raise ValueError("الفئة غير موجودة")
            q = q.filter(FixedAsset.category_id == c.id); label = f"فئة: {c.name}"
        elif scope_type == "branch":
            b = s.get(Branch, int(scope_id))
            if not b: raise ValueError("الفرع غير موجود")
            q = q.filter(FixedAsset.branch_id == b.id); label = f"فرع: {b.name}"
        elif scope_type == "cost_center":
            cc = s.get(CostCenter, int(scope_id))
            if not cc: raise ValueError("مركز التكلفة غير موجود")
            q = q.filter(FixedAsset.cost_center_id == cc.id); label = f"مركز تكلفة: {cc.name}"
        assets = q.all()
        if not assets:
            raise ValueError("مفيش أصول في النطاق ده للجرد")
        assets.sort(key=lambda a: _natural_code_key(a.code))
        name = (name or "").strip() or f"جرد أصول {datetime.date.today().strftime('%Y-%m-%d')}"
        inv = AssetInventory(number=_next_code(s, AssetInventory, "AC-"), name=name, scope_type=scope_type,
                             scope_id=int(scope_id) if scope_id else None, scope_label=label, notes=notes or "",
                             created_by=_current_username(), state="open")
        s.add(inv); s.flush()
        for a in assets:
            s.add(AssetInventoryLine(
                inventory_id=inv.id, asset_id=a.id, code=a.code, code_key=a.code.upper(), name=a.name, category=a.category or "",
                cost=a.cost or 0.0, book_value=a.net_book_value, kind="expected", scan_count=0))
        s.commit()
        return inv.id


def list_asset_inventories():
    with get_session() as s:
        return [_inventory_header(s, i) for i in s.query(AssetInventory).order_by(AssetInventory.id.desc()).all()]


def get_asset_inventory(inventory_id):
    with get_session() as s:
        inv = s.get(AssetInventory, int(inventory_id))
        return _inventory_header(s, inv) if inv else None


def _open_inventory_or_raise(s, inventory_id):
    inv = s.get(AssetInventory, int(inventory_id))
    if not inv:
        raise ValueError("جلسة الجرد غير موجودة")
    if inv.state != "open":
        raise ValueError("الجرد مقفول - أعد فتحه الأول لو عايز تعدّل عليه")
    return inv


def scan_asset_code(inventory_id, raw_code, method="barcode"):
    """يسجّل مسح كود أصل. بيرجّع dict فيه status:
       found      - أصل متوقع اتلاقى أول مرة
       duplicate  - اتمسح قبل كده (متوقع أو زيادة)
       extra      - مش ضمن المتوقع => زيادة (reason: out_of_scope | disposed | unknown)"""
    require_action("asset_inventory", "edit")
    code = _norm_scanned_code(raw_code)
    if not code:
        raise ValueError("الكود فاضي")
    key = code.upper()
    now = datetime.datetime.now()
    with get_session() as s:
        _open_inventory_or_raise(s, inventory_id)
        line = s.query(AssetInventoryLine).filter(AssetInventoryLine.inventory_id == int(inventory_id),
                                                  AssetInventoryLine.code_key == key).first()
        if line:
            is_extra = line.kind == "extra"
            if not is_extra and not line.scanned_at:
                line.scanned_at = now; line.scan_count = 1; line.method = method
                status = "found"
            else:
                line.scan_count = (line.scan_count or 0) + 1
                status = "duplicate"
            s.commit()
            return {"status": status, "code": line.code, "name": line.name, "is_extra": is_extra,
                    "reason": line.extra_reason, "scan_count": line.scan_count, "line_id": line.id}
        from sqlalchemy import func
        asset = s.query(FixedAsset).filter(func.upper(FixedAsset.code) == key).first()
        if asset:
            reason = "disposed" if asset.state == "disposed" else "out_of_scope"
            line = AssetInventoryLine(
                inventory_id=int(inventory_id), asset_id=asset.id, code=asset.code, code_key=key, name=asset.name,
                category=asset.category or "", cost=asset.cost or 0.0, book_value=asset.net_book_value, kind="extra",
                extra_reason=reason, scanned_at=now, scan_count=1, method=method)
        else:
            reason = "unknown"
            line = AssetInventoryLine(inventory_id=int(inventory_id), asset_id=None, code=code, code_key=key, name="",
                                      kind="extra", extra_reason=reason, scanned_at=now, scan_count=1, method=method)
        s.add(line); s.commit()
        return {"status": "extra", "code": line.code, "name": line.name, "is_extra": True, "reason": reason,
                "scan_count": 1, "line_id": line.id}


def set_inventory_line_found(line_id, found=True):
    """تأكيد يدوي إن الأصل موجود (لو الاستيكر بايظ ومش بيتقرا) أو التراجع عنه."""
    require_action("asset_inventory", "edit")
    with get_session() as s:
        line = s.get(AssetInventoryLine, int(line_id))
        if not line:
            raise ValueError("البند غير موجود")
        _open_inventory_or_raise(s, line.inventory_id)
        if line.kind != "expected":
            raise ValueError("التأكيد اليدوي للأصول المتوقعة بس")
        if line.disposed_at:
            raise ValueError("الأصل ده اتستبعد كعجز - تراجع عن استبعاد العجز الأول")
        if found:
            if not line.scanned_at:
                line.scanned_at = datetime.datetime.now(); line.scan_count = 1; line.method = "manual"
        else:
            line.scanned_at = None; line.scan_count = 0; line.method = None
        s.commit()


def delete_inventory_extra_line(line_id):
    """حذف بند زيادة اتمسح بالغلط."""
    require_action("asset_inventory", "edit")
    with get_session() as s:
        line = s.get(AssetInventoryLine, int(line_id))
        if not line:
            raise ValueError("البند غير موجود")
        _open_inventory_or_raise(s, line.inventory_id)
        if line.kind != "extra":
            raise ValueError("بند متوقع - استخدم التراجع بدل الحذف")
        s.delete(line); s.commit()


def close_asset_inventory(inventory_id):
    require_action("asset_inventory", "post")
    with get_session() as s:
        inv = _open_inventory_or_raise(s, inventory_id)
        inv.state = "closed"; inv.closed_at = datetime.datetime.now(); s.commit()


def reopen_asset_inventory(inventory_id):
    require_action("asset_inventory", "post")
    with get_session() as s:
        inv = s.get(AssetInventory, int(inventory_id))
        if not inv:
            raise ValueError("جلسة الجرد غير موجودة")
        if inv.state != "closed":
            raise ValueError("الجرد مفتوح بالفعل")
        inv.state = "open"; inv.closed_at = None; s.commit()


def delete_asset_inventory(inventory_id):
    require_action("asset_inventory", "delete")
    with get_session() as s:
        inv = s.get(AssetInventory, int(inventory_id))
        if not inv:
            raise ValueError("جلسة الجرد غير موجودة")
        if inv.state == "closed":
            raise ValueError("مينفعش تحذف جرد مقفول - أعد فتحه الأول")
        s.delete(inv); s.commit()


def list_asset_inventory_lines(inventory_id, group="all"):
    """group: shortage (متوقع ومش موجود) | found | surplus | all"""
    L = AssetInventoryLine
    with get_session() as s:
        q = s.query(L).filter(L.inventory_id == int(inventory_id))
        if group == "shortage":
            q = q.filter(L.kind == "expected", L.scanned_at.is_(None))
        elif group == "found":
            q = q.filter(L.kind == "expected", L.scanned_at.isnot(None))
        elif group == "surplus":
            q = q.filter(L.kind == "extra")
        rows = [_inventory_line_dict(l) for l in q.all()]
        jids = {r["disposal_journal_id"] for r in rows if r["disposal_journal_id"]}
        if jids:
            nums = {j.id: j.number for j in s.query(JournalEntry).filter(JournalEntry.id.in_(jids)).all()}
            for r in rows:
                r["disposal_ref"] = nums.get(r["disposal_journal_id"], "")
    if group == "found":
        rows.sort(key=lambda r: r["scanned_at"], reverse=True)     # الأحدث مسحًا الأول
    elif group == "surplus":
        rows.sort(key=lambda r: r["scanned_at"] or datetime.datetime.min, reverse=True)
    else:
        rows.sort(key=lambda r: _natural_code_key(r["code"]))
    return rows


def asset_inventory_report(inventory_id):
    """تقرير الجرد: ملخص + قوايم العجز والزيادة والموجود."""
    inv = get_asset_inventory(inventory_id)
    if not inv:
        raise ValueError("جلسة الجرد غير موجودة")
    shortage = list_asset_inventory_lines(inventory_id, "shortage")
    found = list_asset_inventory_lines(inventory_id, "found")
    found.sort(key=lambda r: _natural_code_key(r["code"]))
    surplus = list_asset_inventory_lines(inventory_id, "surplus")
    surplus.sort(key=lambda r: _natural_code_key(r["code"]))
    expected = inv["expected"]
    summary = {
        "expected": expected, "found": len(found), "shortage_count": len(shortage),
        "shortage_cost": round(sum(r["cost"] for r in shortage), 2),
        "shortage_book_value": round(sum(r["book_value"] for r in shortage), 2),
        "surplus_count": len(surplus), "surplus_unknown": sum(1 for r in surplus if r["reason"] == "unknown"),
        "surplus_known": sum(1 for r in surplus if r["reason"] != "unknown"),
        "match_pct": round(len(found) / expected * 100, 1) if expected else 0.0,
        "manual_confirmed": sum(1 for r in found if r["method"] == "manual"),
        "disposed_count": sum(1 for r in shortage if r["disposed_at"]),
        "disposed_loss": round(sum(r["disposal_loss"] for r in shortage if r["disposed_at"]), 2),
        "pending_count": sum(1 for r in shortage if not r["disposed_at"]),
        "pending_book_value": round(sum(r["book_value"] for r in shortage if not r["disposed_at"]), 2),
    }
    return {"inventory": inv, "summary": summary, "shortage": shortage, "found": found, "surplus": surplus}


def export_asset_inventory(inventory_id, kind="pdf", include_found=False):
    """يصدّر تقرير الجرد (pdf أو xlsx) في مجلد التنزيلات وبيرجّع مساره."""
    from .asset_inventory_report import export_inventory_excel, export_inventory_pdf
    rep = asset_inventory_report(inventory_id)
    company = get_company_settings()
    fn = export_inventory_excel if kind == "xlsx" else export_inventory_pdf
    return fn(rep, company, downloads_dir(), include_found=include_found)


# ---------------- تحويل عجز الجرد لاستبعاد أصول بخسارتها (اختياري) ----------------
def _pending_shortage_lines(s, inventory_id, line_ids=None):
    L = AssetInventoryLine
    q = s.query(L).filter(L.inventory_id == int(inventory_id), L.kind == "expected", L.scanned_at.is_(None), L.disposed_at.is_(None))
    if line_ids:
        q = q.filter(L.id.in_([int(i) for i in line_ids]))
    return q.all()


def _shortage_disposal_plan(s, inventory_id, line_ids=None, loss_account_id=None):
    """يحسب قيد الاستبعاد من القيم الحالية للأصول (مش لقطة الجرد): بيرجّع الأصول
    اللي هتتستبعد، اللي هتتخطّى، وسطور القيد المجمّعة."""
    cfg = s.get(AccountingSettings, 1)
    default_loss = cfg.asset_loss_account_id if cfg else None
    items, skipped = [], []
    debit, credit = {}, {}
    for line in sorted(_pending_shortage_lines(s, inventory_id, line_ids), key=lambda l: _natural_code_key(l.code)):
        a = s.get(FixedAsset, line.asset_id) if line.asset_id else None
        if not a:
            skipped.append({"code": line.code, "reason": "الأصل مش موجود في السجلات"}); continue
        if a.state == "disposed":
            skipped.append({"code": line.code, "reason": "الأصل مستبعد بالفعل"}); continue
        if not (a.asset_account_id and a.accumulated_depreciation_account_id and a.depreciation_expense_account_id):
            skipped.append({"code": line.code, "reason": "حسابات الأصل ناقصة"}); continue
        cost = round(a.cost or 0.0, 2)
        acc = round(min(a.accumulated_depreciation or 0.0, cost), 2)
        nbv = round(cost - acc, 2)
        loss_acc = loss_account_id or default_loss or a.depreciation_expense_account_id
        credit[a.asset_account_id] = credit.get(a.asset_account_id, 0.0) + cost
        if acc:
            debit[a.accumulated_depreciation_account_id] = debit.get(a.accumulated_depreciation_account_id, 0.0) + acc
        if nbv > 0:
            debit[loss_acc] = debit.get(loss_acc, 0.0) + nbv
        items.append({"line_id": line.id, "asset_id": a.id, "code": a.code, "name": a.name, "cost": cost,
                      "accumulated": acc, "loss": nbv})
    lines = [{"account_id": k, "debit": round(v, 2)} for k, v in debit.items()] + \
            [{"account_id": k, "credit": round(v, 2)} for k, v in credit.items()]
    return {"items": items, "skipped": skipped, "lines": lines, "default_loss_account_id": default_loss,
            "total_cost": round(sum(i["cost"] for i in items), 2), "total_accumulated": round(sum(i["accumulated"] for i in items), 2),
            "total_loss": round(sum(i["loss"] for i in items), 2)}


def preview_inventory_shortage_disposal(inventory_id, line_ids=None, loss_account_id=None):
    """أرقام الاستبعاد المتوقعة (بدون ما ينفّذ حاجة) - بتتعرض للمستخدم قبل التأكيد."""
    with get_session() as s:
        plan = _shortage_disposal_plan(s, inventory_id, line_ids, loss_account_id)
    plan.pop("lines")
    return plan


def dispose_inventory_shortage(inventory_id, disposal_date=None, line_ids=None, loss_account_id=None):
    """يحوّل عجز الجرد (أصول متوقعة ومتمسحتش) لاستبعاد: قيد واحد مجمّع
    (مدين مجمّع الإهلاك + مدين خسارة الاستبعاد / دائن حساب الأصل) وبيعلّم الأصول مستبعدة.
    شروطه: الجرد مقفول. line_ids = أصول معيّنة، وإلا كل العجز اللي لسه ما اتستبعدش.
    القيد بيتعمل الأول، ولو فشل (فترة مقفولة مثلاً) مفيش أي أصل بيتغيّر."""
    require_action("asset_inventory", "post")
    require_action("fixed_assets", "post")
    disposal_date = disposal_date or datetime.datetime.combine(datetime.date.today(), datetime.time.min)
    with get_session() as s:
        inv = s.get(AssetInventory, int(inventory_id))
        if not inv:
            raise ValueError("جلسة الجرد غير موجودة")
        if inv.state != "closed":
            raise ValueError("أنهِ الجرد الأول - العجز لازم يبقى نهائي قبل ما يتحوّل لاستبعاد")
        number = inv.number
        plan = _shortage_disposal_plan(s, inventory_id, line_ids, loss_account_id)
    if not plan["items"]:
        detail = "؛ ".join(f'{x["code"]}: {x["reason"]}' for x in plan["skipped"][:5])
        raise ValueError("مفيش عجز متبقي للاستبعاد" + (f" ({detail})" if detail else ""))
    jid = create_journal_entry(
        plan["lines"], reference=number, description=f"استبعاد أصول عجز الجرد {number} ({len(plan['items'])} أصل)",
        source_type="asset_inventory_shortage", source_id=int(inventory_id), entry_date=disposal_date,
    )
    now = datetime.datetime.now()
    with get_session() as s:
        for it in plan["items"]:
            a = s.get(FixedAsset, it["asset_id"])
            a.state = "disposed"; a.disposal_date = disposal_date; a.disposal_amount = 0.0
            line = s.get(AssetInventoryLine, it["line_id"])
            line.disposal_journal_id = jid; line.disposed_at = now; line.disposal_loss = it["loss"]
        journal_number = s.get(JournalEntry, jid).number
        s.commit()
    return {"journal_id": jid, "journal_number": journal_number, "count": len(plan["items"]), "total_cost": plan["total_cost"],
            "total_accumulated": plan["total_accumulated"], "total_loss": plan["total_loss"], "skipped": plan["skipped"]}


def undo_inventory_shortage_disposal(inventory_id):
    """يتراجع عن استبعاد العجز: بيعمل قيد عكسي (مدين/دائن معكوسين) لكل قيد استبعاد
    اتعمل من الجرد ده، وبيرجّع الأصول لحالتها. بيتراجع بس لو كل الأصول لسه مستبعدة
    بنفس الاستبعاد (متغيّرتش بعد كده)."""
    require_action("asset_inventory", "post")
    require_action("fixed_assets", "post")
    with get_session() as s:
        lines = s.query(AssetInventoryLine).filter(AssetInventoryLine.inventory_id == int(inventory_id),
                                                   AssetInventoryLine.disposal_journal_id.isnot(None)).all()
        if not lines:
            raise ValueError("مفيش استبعاد عجز للتراجع عنه في الجرد ده")
        groups = {}
        for l in lines:
            groups.setdefault(l.disposal_journal_id, []).append((l.id, l.asset_id))
        for jid, members in groups.items():
            for _lid, asset_id in members:
                a = s.get(FixedAsset, asset_id)
                if not a or a.state != "disposed" or (a.disposal_amount or 0) != 0:
                    raise ValueError(f'الأصل {a.code if a else asset_id} اتغيّر بعد الاستبعاد - مينفعش التراجع الآلي، سجّل قيد تسوية يدوي')
        number = s.get(AssetInventory, int(inventory_id)).number
    reversed_no = 0
    for jid, members in groups.items():
        e = get_journal_entry(jid)
        rev = [{"account_id": ln.account_id, "debit": ln.credit, "credit": ln.debit} for ln in e.lines]
        create_journal_entry(rev, reference=number, description=f"عكس استبعاد أصول عجز الجرد {number} (قيد {e.number})",
                             source_type="asset_inventory_shortage_reversal", source_id=int(inventory_id))
        reversed_no += 1
    restored = 0
    with get_session() as s:
        for jid, members in groups.items():
            for lid, asset_id in members:
                a = s.get(FixedAsset, asset_id)
                a.state = "fully_depreciated" if (a.accumulated_depreciation or 0) >= a.depreciable_amount - 0.01 else "active"
                a.disposal_date = None; a.disposal_amount = 0.0
                line = s.get(AssetInventoryLine, lid)
                line.disposal_journal_id = None; line.disposed_at = None; line.disposal_loss = 0.0
                restored += 1
        s.commit()
    return {"reversed_entries": reversed_no, "restored_assets": restored}


# ======================================================================
# نظام المطاعم: طاولات + طلب مفتوح لكل طاولة + إرسال للمطبخ + تحويل
# للدفع كفاتورة POS عادية (بيستخدم create_pos_sale نفسها)
# ======================================================================
def list_restaurant_sections(active_only=False):
    with get_session() as s:
        q = s.query(RestaurantSection)
        if active_only:
            q = q.filter(RestaurantSection.is_active.is_(True))
        return q.order_by(RestaurantSection.sort_order, RestaurantSection.name).all()


def create_restaurant_section(name, sort_order=0):
    require_action("restaurant", "create")
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم القسم مطلوب")
    with get_session() as s:
        if s.query(RestaurantSection).filter(RestaurantSection.name == name).count():
            raise ValueError(f'قسم "{name}" موجود بالفعل')
        c = RestaurantSection(name=name, sort_order=int(sort_order or 0), is_active=True)
        s.add(c); s.commit(); s.refresh(c)
        return c.id


def update_restaurant_section(section_id, name, sort_order=0, is_active=True):
    require_action("restaurant", "edit")
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم القسم مطلوب")
    with get_session() as s:
        c = s.get(RestaurantSection, int(section_id))
        if not c:
            raise ValueError("القسم غير موجود")
        if s.query(RestaurantSection).filter(RestaurantSection.name == name, RestaurantSection.id != c.id).count():
            raise ValueError(f'قسم "{name}" موجود بالفعل')
        c.name = name; c.sort_order = int(sort_order or 0); c.is_active = bool(is_active)
        s.commit()


def delete_restaurant_section(section_id):
    require_action("restaurant", "delete")
    with get_session() as s:
        used = s.query(RestaurantTable).filter(RestaurantTable.section_id == int(section_id)).count()
        if used:
            raise ValueError(f"القسم مستخدم في {used} طاولة - وقّفه بدل الحذف")
        c = s.get(RestaurantSection, int(section_id))
        if not c:
            raise ValueError("القسم غير موجود")
        s.delete(c); s.commit()


def list_restaurant_tables(branch_id=None, active_only=True):
    with get_session() as s:
        q = s.query(RestaurantTable).options(joinedload(RestaurantTable.section), joinedload(RestaurantTable.branch))
        if branch_id:
            q = q.filter(RestaurantTable.branch_id == int(branch_id))
        if active_only:
            q = q.filter(RestaurantTable.is_active.is_(True))
        tables = q.order_by(RestaurantTable.number).all()
        s.expunge_all()
        return tables


def create_restaurant_table(number, name="", seats=4, section_id=None, branch_id=None):
    require_action("restaurant", "create")
    number = (number or "").strip()
    if not number:
        raise ValueError("رقم الطاولة مطلوب")
    with get_session() as s:
        if s.query(RestaurantTable).filter(RestaurantTable.number == number).count():
            raise ValueError(f'طاولة رقم "{number}" موجودة بالفعل')
        t = RestaurantTable(number=number, name=name or "", seats=int(seats or 1), section_id=int(section_id) if section_id else None,
                            branch_id=int(branch_id) if branch_id else default_branch_id(), is_active=True)
        s.add(t); s.commit(); s.refresh(t)
        return t.id


def update_restaurant_table(table_id, number, name="", seats=4, section_id=None, branch_id=None, is_active=True):
    require_action("restaurant", "edit")
    number = (number or "").strip()
    if not number:
        raise ValueError("رقم الطاولة مطلوب")
    with get_session() as s:
        t = s.get(RestaurantTable, int(table_id))
        if not t:
            raise ValueError("الطاولة غير موجودة")
        if s.query(RestaurantTable).filter(RestaurantTable.number == number, RestaurantTable.id != t.id).count():
            raise ValueError(f'طاولة رقم "{number}" موجودة بالفعل')
        t.number = number; t.name = name or ""; t.seats = int(seats or 1)
        t.section_id = int(section_id) if section_id else None; t.branch_id = int(branch_id) if branch_id else None
        t.is_active = bool(is_active)
        s.commit()


def delete_restaurant_table(table_id):
    require_action("restaurant", "delete")
    with get_session() as s:
        if s.query(RestaurantOrder).filter(RestaurantOrder.table_id == int(table_id), RestaurantOrder.state == "open").count():
            raise ValueError("الطاولة عليها طلب مفتوح - قفّل الطلب الأول")
        t = s.get(RestaurantTable, int(table_id))
        if not t:
            raise ValueError("الطاولة غير موجودة")
        s.delete(t); s.commit()


def _order_dict(s, o):
    act = [i for i in o.items if i.kitchen_status != "voided"]
    total = sum((i.quantity or 0) * (i.unit_price or 0) * (1 + (i.tax_rate or 0) / 100.0) for i in act)
    pending = sum(1 for i in act if i.kitchen_status == "pending")
    return {"id": o.id, "number": o.number, "table_id": o.table_id, "guests": o.guests, "state": o.state,
            "opened_at": o.opened_at, "closed_at": o.closed_at, "opened_by": o.opened_by, "notes": o.notes,
            "sales_invoice_id": o.sales_invoice_id, "items_count": len(act), "total": round(total, 2),
            "pending_items": pending, "order_type": o.order_type, "customer_name": o.customer_name or "",
            "customer_phone": o.customer_phone or "", "delivery_address": o.delivery_address or "",
            "locked_items": sum(1 for i in act if i.kitchen_status != "pending"), "terminal_id": o.terminal_id, "pos_session_id": o.pos_session_id}


def list_tables_status(branch_id=None):
    """كل الطاولات مع حالتها الحالية (فاضية / عليها طلب مفتوح وملخصه)."""
    tables = list_restaurant_tables(branch_id)
    with get_session() as s:
        open_orders = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.items)).filter(RestaurantOrder.state == "open").all()
        by_table = {o.table_id: _order_dict(s, o) for o in open_orders}
    out = []
    for t in tables:
        out.append({"id": t.id, "number": t.number, "name": t.name, "seats": t.seats,
                    "section": t.section.name if t.section else "", "order": by_table.get(t.id)})
    return out


def get_open_order_for_table(table_id):
    with get_session() as s:
        o = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.items).joinedload(RestaurantOrderItem.product),
                                              joinedload(RestaurantOrder.table)).filter(
            RestaurantOrder.table_id == int(table_id), RestaurantOrder.state == "open").first()
        if not o:
            return None
        d = _order_dict(s, o)
        d["table_number"] = o.table.number if o.table else ""
        d["items"] = [{"id": i.id, "product_id": i.product_id, "name": i.product.name if i.product else "-",
                       "quantity": i.quantity, "unit_price": i.unit_price, "tax_rate": i.tax_rate, "note": i.note or "",
                       "kitchen_status": i.kitchen_status, "line_total": 0.0 if i.kitchen_status == "voided" else round(i.quantity * i.unit_price * (1 + i.tax_rate / 100.0), 2),
                       "void_reason": i.void_reason or "", "approved_by": i.approved_by or ""}
                      for i in o.items]
        s.expunge_all()
        return d


def get_restaurant_order(order_id):
    d = None
    with get_session() as s:
        o = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.items).joinedload(RestaurantOrderItem.product),
                                              joinedload(RestaurantOrder.table)).filter(RestaurantOrder.id == int(order_id)).first()
        if not o:
            return None
        d = _order_dict(s, o)
        d["table_number"] = o.table.number if o.table else ""
        d["items"] = [{"id": i.id, "product_id": i.product_id, "name": i.product.name if i.product else "-",
                       "quantity": i.quantity, "unit_price": i.unit_price, "tax_rate": i.tax_rate, "note": i.note or "",
                       "kitchen_status": i.kitchen_status, "line_total": 0.0 if i.kitchen_status == "voided" else round(i.quantity * i.unit_price * (1 + i.tax_rate / 100.0), 2),
                       "void_reason": i.void_reason or "", "approved_by": i.approved_by or ""}
                      for i in o.items]
        s.expunge_all()
    return d


RESTAURANT_ORDER_TYPES = {"dine_in": "طلب محلي", "takeaway": "طلب تيك أواي", "delivery": "طلب دليفري"}


def open_restaurant_order(table_id=None, guests=1, branch_id=None, order_type="dine_in", customer_name="", customer_phone="", delivery_address="", terminal_id=None):
    """يفتح طلب جديد - على طاولة (صالة، بيرفض لو عليها طلب مفتوح بالفعل)،
    أو من غير طاولة خالص (تيك أواي/دليفري)."""
    require_action("restaurant", "create")
    if order_type not in RESTAURANT_ORDER_TYPES:
        raise ValueError("نوع الطلب غير معروف")
    if not terminal_id:
        raise ValueError("اختر ماكينة المطعم وافتح جلسة الأول")
    terminal = get_pos_terminal(terminal_id)
    if not terminal or not terminal["is_active"]:
        raise ValueError("الماكينة غير موجودة أو موقوفة")
    session = get_open_pos_session(terminal["id"])
    if not session:
        raise ValueError(f'مفيش جلسة مفتوحة على «{terminal["name"]}» - افتح جلسة الأول')
    me = current_user() or {}
    if me.get("role") != "admin" and session["opened_by"] != me.get("username"):
        raise PermissionError(f'الجلسة {session["number"]} مفتوحة بواسطة {session["opened_by_name"]} - مينفعش تفتح طلب عليها')
    with get_session() as s:
        if order_type == "dine_in":
            if not table_id:
                raise ValueError("اختر الطاولة لطلب الصالة")
            t = s.get(RestaurantTable, int(table_id))
            if not t:
                raise ValueError("الطاولة غير موجودة")
            if s.query(RestaurantOrder).filter(RestaurantOrder.table_id == t.id, RestaurantOrder.state == "open").count():
                raise ValueError(f"الطاولة {t.number} عليها طلب مفتوح بالفعل")
            resolved_branch = branch_id or t.branch_id or terminal["branch_id"] or default_branch_id()
            resolved_table_id = t.id
        else:
            if order_type == "delivery" and not (customer_phone or "").strip():
                raise ValueError("رقم هاتف العميل مطلوب لطلب الدليفري")
            if order_type == "delivery" and not (delivery_address or "").strip():
                raise ValueError("عنوان التوصيل مطلوب لطلب الدليفري")
            resolved_branch = branch_id or terminal["branch_id"] or default_branch_id()
            resolved_table_id = None
        o = RestaurantOrder(number=_next_code(s, RestaurantOrder, "RT-"), table_id=resolved_table_id, guests=int(guests or 1),
                            order_type=order_type, customer_name=customer_name or "", customer_phone=(customer_phone or "").strip(), delivery_address=(delivery_address or "").strip(), terminal_id=terminal["id"], pos_session_id=session["id"],
                            branch_id=resolved_branch, state="open", opened_by=_current_username())
        s.add(o); s.commit(); s.refresh(o)
        return o.id


def list_open_orders_without_table():
    """طلبات التيك أواي والدليفري المفتوحة (مالهاش طاولة تتعرض بيها)."""
    with get_session() as s:
        orders = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.items)).filter(
            RestaurantOrder.state == "open", RestaurantOrder.table_id.is_(None)).order_by(RestaurantOrder.opened_at.desc()).all()
        return [_order_dict(s, o) for o in orders]


def add_restaurant_order_item(order_id, product_id, quantity=1.0, note="", customer_id=None):
    """customer_id اختياري: لو اتبعت، السعر بيتحدد من قائمة أسعار العميل
    ده لو موجودة، وإلا سعر البيع الافتراضي للصنف كالمعتاد."""
    require_action("restaurant", "edit")
    quantity = float(quantity or 0)
    if quantity <= 0:
        raise ValueError("الكمية يجب أن تكون أكبر من صفر")
    unit_price, _ = get_customer_product_price(customer_id, product_id)
    with get_session() as s:
        o = s.get(RestaurantOrder, int(order_id))
        if not o:
            raise ValueError("الطلب غير موجود")
        if o.state != "open":
            raise ValueError("الطلب ده مقفول")
        p = s.get(Product, int(product_id))
        if not p:
            raise ValueError("الصنف غير موجود")
        if not p.can_be_sold:
            raise ValueError(f'الصنف "{p.name}" غير متاح للبيع')
        existing = next((i for i in o.items if i.product_id == p.id and i.kitchen_status == "pending" and (i.note or "") == (note or "")), None)
        if existing:
            existing.quantity = (existing.quantity or 0) + quantity
        else:
            s.add(RestaurantOrderItem(order_id=o.id, product_id=p.id, quantity=quantity, unit_price=unit_price,
                                      tax_rate=p.tax_rate or 15, note=note or "", kitchen_status="pending"))
        s.commit()


def update_restaurant_order_item(item_id, quantity=None, note=None):
    require_action("restaurant", "edit")
    with get_session() as s:
        it = s.get(RestaurantOrderItem, int(item_id))
        if not it:
            raise ValueError("الصنف غير موجود في الطلب")
        o = s.get(RestaurantOrder, it.order_id)
        if o.state != "open":
            raise ValueError("الطلب ده مقفول")
        if it.kitchen_status != "pending":
            raise ValueError("الصنف اتبعت للمطبخ - ممنوع تعديل كميته. لو محتاج زيادة أضفه كسطر جديد")
        if quantity is not None:
            quantity = float(quantity)
            if quantity <= 0:
                raise ValueError("الكمية يجب أن تكون أكبر من صفر")
            it.quantity = quantity
        if note is not None:
            it.note = note
        s.commit()


def remove_restaurant_order_item(item_id):
    require_action("restaurant", "edit")
    with get_session() as s:
        it = s.get(RestaurantOrderItem, int(item_id))
        if not it:
            raise ValueError("الصنف غير موجود في الطلب")
        o = s.get(RestaurantOrder, it.order_id)
        if o.state != "open":
            raise ValueError("الطلب ده مقفول")
        if it.kitchen_status != "pending":
            raise ValueError("الصنف اتبعت للمطبخ - ممنوع حذفه أو تعديله")
        s.delete(it); s.commit()


def list_open_restaurant_orders(session_id=None, terminal_id=None):
    """كل الطلبات/الفواتير المفتوحة (اللي لسه ما اتدفعتش) - ممكن تتفلتر بجلسة أو ماكينة."""
    from .db import PosSession
    with get_session() as s:
        q = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.items), joinedload(RestaurantOrder.table)).filter(RestaurantOrder.state == "open")
        if session_id:
            q = q.filter(RestaurantOrder.pos_session_id == int(session_id))
        if terminal_id:
            q = q.filter(RestaurantOrder.terminal_id == int(terminal_id))
        out = []
        for o in q.order_by(RestaurantOrder.opened_at).all():
            ses = s.get(PosSession, o.pos_session_id) if o.pos_session_id else None
            out.append(_order_dict(s, o) | {"table_number": o.table.number if o.table else "", "session_number": ses.number if ses else ""})
        return out


def void_sent_order_item(item_id, reason, approver=None, quantity=None):
    """إلغاء صنف اتبعت للمطبخ - بصلاحية مدير (restaurant:close). لو المستخدم الحالي ما عندوش الصلاحية
    لازم يتبعت approver (نتيجة authenticate_user لمدير). السبب إجباري، والصنف بيفضل ظاهر كملغي للمراجعة."""
    require_action("restaurant", "edit")
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("سبب الإلغاء مطلوب")
    boss = _get_user() if user_has_action(_get_user(), "restaurant", "close") else approver
    if not boss or not user_has_action(boss, "restaurant", "close"):
        raise PermissionError("إلغاء صنف مبعوث للمطبخ محتاج اعتماد مدير")
    boss_name = boss.get("username") if isinstance(boss, dict) else getattr(boss, "username", "")
    now = datetime.datetime.now()
    with get_session() as s:
        it = s.get(RestaurantOrderItem, int(item_id))
        if not it:
            raise ValueError("الصنف غير موجود في الطلب")
        o = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.table)).filter(RestaurantOrder.id == it.order_id).first()
        if o.state != "open":
            raise ValueError("الطلب ده مقفول")
        if it.kitchen_status == "voided":
            raise ValueError("الصنف ملغي بالفعل")
        if it.kitchen_status == "pending":
            raise ValueError("الصنف لسه ما اتبعتش للمطبخ - احذفه عادي")
        prod = s.get(Product, it.product_id)
        total_q = float(it.quantity or 0)
        try:
            vq = total_q if quantity in (None, "") else float(quantity)
        except (TypeError, ValueError):
            raise ValueError("الكمية الملغاة لازم تكون رقم")
        if vq <= 0:
            raise ValueError("الكمية الملغاة لازم تكون أكبر من صفر")
        if vq > total_q + 1e-9:
            raise ValueError(f"الكمية الملغاة ({vq:g}) أكبر من كمية الصنف ({total_q:g})")
        if vq < total_q - 1e-9:
            # إلغاء جزئي: الباقي يفضل مبعوت، والكمية الملغاة تتسجل في سطر ملغي مستقل للمراجعة
            it.quantity = total_q - vq
            vit = RestaurantOrderItem(order_id=it.order_id, product_id=it.product_id, quantity=vq, unit_price=it.unit_price, tax_rate=it.tax_rate, note=it.note or "", course=it.course,
                                      kitchen_status="voided", sent_at=it.sent_at, void_reason=reason[:200], voided_by=_current_username(), approved_by=boss_name or "", voided_at=now)
            s.add(vit)
            it = vit
        else:
            it.kitchen_status = "voided"; it.void_reason = reason[:200]; it.voided_by = _current_username(); it.approved_by = boss_name or ""; it.voided_at = now
        _add_kitchen_events(s, "item_void", o, [(it.product_id, it.quantity, it.quantity * it.unit_price * (1 + (it.tax_rate or 0) / 100.0))], reason, approved_by=boss_name or "")
        res = {"table_number": o.table.number if o.table else "", "order_number": o.number, "order_type": o.order_type, "sent_at": now,
               "items": [{"name": prod.name if prod else "-", "quantity": it.quantity, "note": it.note or ""}], "customer_info": "", "cancel": True, "reason": reason}
        s.commit()
    return res


KITCHEN_EVENT_KINDS = {"item_void": "إلغاء صنف مبعوث", "order_void": "إلغاء طلب", "item_return": "مرتجع صنف", "invoice_void": "إلغاء فاتورة"}


def _add_kitchen_events(s, kind, order, lines, reason="", approved_by="", invoice=None):
    """lines = [(product_id, qty, amount_with_tax)]. بتتسجل في نفس الـ session (بتتحفظ مع العملية الأصلية)."""
    now = datetime.datetime.now()
    for pid, qty, amount in lines:
        prod = s.get(Product, int(pid)) if pid else None
        s.add(KitchenEvent(created_at=now, kind=kind, order_id=order.id if order else None, order_number=order.number if order else "", order_type=order.order_type if order else "",
                           table_number=(order.table.number if order is not None and order.table else ""), invoice_id=invoice.id if invoice else (order.sales_invoice_id if order else None),
                           invoice_number=invoice.number if invoice else "", branch_id=(order.branch_id if order else (invoice.branch_id if invoice else None)),
                           product_id=pid, product_name=prod.name if prod else "-", quantity=float(qty or 0), amount=round(float(amount or 0), 2), reason=(reason or "")[:300],
                           created_by=_current_username(), approved_by=approved_by or ""))


def _kitchen_events_for_invoice(s, invoice_id, kind, lines, reason=""):
    """لو الفاتورة طلعت من طلب مطعم، سجّل الإلغاء/المرتجع كإشعار للمطبخ وللتقارير."""
    order = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.table)).filter(RestaurantOrder.sales_invoice_id == int(invoice_id)).first()
    if not order:
        return
    inv = s.get(SalesInvoice, int(invoice_id))
    _add_kitchen_events(s, kind, order, lines, reason, invoice=inv)


def list_audit_logs(date_from=None, date_to=None, username=None, action=None, table=None, search=None, limit=3000):
    require_action("audit_log", "view")
    from .db import AuditLog
    with get_session() as s:
        q = s.query(AuditLog)
        if date_from:
            q = q.filter(AuditLog.at >= datetime.datetime.combine(date_from, datetime.time.min))
        if date_to:
            q = q.filter(AuditLog.at <= datetime.datetime.combine(date_to, datetime.time.max))
        if username:
            q = q.filter(AuditLog.username == username)
        if action:
            q = q.filter(AuditLog.action == action)
        if table:
            q = q.filter(AuditLog.table_name == table)
        if search:
            like = f"%{search.strip()}%"
            q = q.filter(AuditLog.label.like(like) | AuditLog.changes.like(like))
        rows = q.order_by(AuditLog.at.desc(), AuditLog.id.desc()).limit(limit).all()
        return [{c.name: getattr(r, c.name) for c in AuditLog.__table__.columns} for r in rows]


def audit_filter_options():
    require_action("audit_log", "view")
    from .db import AuditLog
    with get_session() as s:
        users = [u for (u,) in s.query(AuditLog.username).distinct().all() if u]
        tables = [t for (t,) in s.query(AuditLog.table_name).distinct().all() if t]
    return {"users": sorted(users), "tables": sorted(tables)}


def list_kitchen_events(kind=None, date_from=None, date_to=None, only_new=False, branch_id=None, limit=1000):
    with get_session() as s:
        q = s.query(KitchenEvent)
        if kind:
            q = q.filter(KitchenEvent.kind == kind)
        if date_from:
            q = q.filter(KitchenEvent.created_at >= datetime.datetime.combine(date_from, datetime.time.min))
        if date_to:
            q = q.filter(KitchenEvent.created_at <= datetime.datetime.combine(date_to, datetime.time.max))
        if only_new:
            q = q.filter(KitchenEvent.acknowledged.is_(False))
        if branch_id:
            q = q.filter(KitchenEvent.branch_id == int(branch_id))
        rows = q.order_by(KitchenEvent.created_at.desc(), KitchenEvent.id.desc()).limit(limit).all()
        out = [{c.name: getattr(e, c.name) for c in KitchenEvent.__table__.columns} for e in rows]
    for r in out:
        r["kind_label"] = KITCHEN_EVENT_KINDS.get(r["kind"], r["kind"])
    return out


def acknowledge_kitchen_events(ids):
    require_action("kitchen", "edit")
    with get_session() as s:
        now = datetime.datetime.now()
        for e in s.query(KitchenEvent).filter(KitchenEvent.id.in_([int(i) for i in ids])).all():
            if not e.acknowledged:
                e.acknowledged = True; e.acknowledged_by = _current_username(); e.acknowledged_at = now
        s.commit()


def kitchen_events_summary(date_from=None, date_to=None, branch_id=None):
    rows = list_kitchen_events(None, date_from, date_to, False, branch_id, limit=100000)
    by = {}
    for r in rows:
        d = by.setdefault(r["kind"], {"count": 0, "qty": 0.0, "amount": 0.0})
        d["count"] += 1; d["qty"] += r["quantity"]; d["amount"] += r["amount"]
    return {"rows": rows, "by_kind": by, "total_amount": round(sum(r["amount"] for r in rows), 2)}


def kitchen_board(branch_id=None):
    """شاشة المطبخ: الأصناف المبعوتة وما اتقدمتش لسه، مجمّعة بالطلب (الأقدم الأول) + الإشعارات الجديدة."""
    with get_session() as s:
        q = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.items).joinedload(RestaurantOrderItem.product), joinedload(RestaurantOrder.table)).filter(RestaurantOrder.state == "open")
        if branch_id:
            q = q.filter(RestaurantOrder.branch_id == int(branch_id))
        tickets = []
        for o in q.all():
            its = [i for i in o.items if i.kitchen_status == "sent"]
            if not its:
                continue
            tickets.append({"order_id": o.id, "number": o.number, "order_type": o.order_type, "table_number": o.table.number if o.table else "", "customer_name": o.customer_name or "",
                            "since": min(i.sent_at or o.opened_at for i in its),
                            "items": [{"id": i.id, "name": i.product.name if i.product else "-", "quantity": i.quantity, "note": i.note or "", "sent_at": i.sent_at} for i in its]})
        tickets.sort(key=lambda t: t["since"])
    try:
        from . import delivery as _dl
        delivery_new = _dl.count_new()
    except Exception:
        delivery_new = 0
    return {"tickets": tickets, "events": list_kitchen_events(only_new=True, branch_id=branch_id, limit=200), "delivery_new": delivery_new}


def mark_items_served(item_ids):
    require_action("kitchen", "edit")
    with get_session() as s:
        now = datetime.datetime.now()
        for it in s.query(RestaurantOrderItem).filter(RestaurantOrderItem.id.in_([int(i) for i in item_ids])).all():
            if it.kitchen_status == "sent":
                it.kitchen_status = "served"; it.served_at = now
        s.commit()


def _stock_demand(pairs):
    """pairs = [(product_id, qty)] -> {component_id: (name, qty_base)} بنفس منطق البيع: الخدمة بلا مخزون، الـKit بيتفكك لمكوناته."""
    out = {}
    for pid, qty in pairs:
        p = get_product(int(pid))
        if not p or p.product_type == "service":
            continue
        if p.product_type == "kit":
            for ln in get_bom_explosion(int(pid), float(qty)):
                n, q = out.get(ln["component_id"], (ln["component"].name, 0.0)); out[ln["component_id"]] = (n, q + ln["quantity"])
        else:
            n, q = out.get(p.id, (p.name, 0.0)); out[p.id] = (n, q + float(qty))
    return out


def _check_recipe_stock(order, pending):
    """قبل الإرسال للمطبخ: لو المخزون (بعد المحجوز لطلبات تانية مفتوحة اتبعتت للمطبخ ولسه ما اتدفعتش) مش كفاية، ارفض بدل ما البيع يترفض عند الدفع."""
    location_id = branch_id = None
    if order.terminal_id:
        t = get_pos_terminal(order.terminal_id)
        if t:
            location_id, branch_id = t["location_id"], t["branch_id"]
    need = _stock_demand([(i.product_id, i.quantity) for i in pending])
    if not need:
        return
    with get_session() as s:
        committed_items = (s.query(RestaurantOrderItem.product_id, RestaurantOrderItem.quantity)
                           .join(RestaurantOrder, RestaurantOrder.id == RestaurantOrderItem.order_id)
                           .filter(RestaurantOrder.state == "open", RestaurantOrderItem.kitchen_status.in_(["sent", "served"])).all())
    held = _stock_demand([(pid, q) for pid, q in committed_items])
    short = []
    for cid, (name, q) in need.items():
        avail = get_product_balance(cid, location_id, branch_id) - held.get(cid, (name, 0.0))[1]
        if avail + 1e-9 < q:
            short.append(f"«{name}» المتاح {max(avail, 0):g} والمطلوب {q:g}")
    if short:
        raise ValueError("المخزون لا يكفي لتجهيز الطلب: " + " - ".join(short))


def recipe_costing(search=None, category_id=None):
    """تكلفة الوصفات: لكل صنف Kit/مُصنَّع -> تكلفة المكونات، سعر البيع (قبل الضريبة)، الهامش، نسبة تكلفة الطعام، وعدد الأطباق اللي المخزون يكفيها."""
    require_action("recipe_costing", "view")

    def unit_cost(pid, depth=0):
        with get_session() as s:
            lines = s.query(BomLine).options(joinedload(BomLine.component)).filter(BomLine.product_id == pid).all()
            s.expunge_all()
        total, incomplete = 0.0, False
        for ln in lines:
            c = ln.component
            if depth < 3 and c.product_type in ("kit", "manufactured") and get_bom_explosion(c.id, 1):
                cc, inc = unit_cost(c.id, depth + 1)
            else:
                cc, inc = float(c.cost_price or 0), not (c.cost_price or 0) > 0
            total += cc * ln.quantity; incomplete = incomplete or inc
        return total, incomplete

    rows = []
    with get_session() as s:
        q = s.query(Product).filter(Product.product_type.in_(["kit", "manufactured"]))
        if search:
            q = q.filter(or_(Product.name.ilike(f"%{search}%"), Product.sku.ilike(f"%{search}%")))
        if category_id:
            q = q.filter(Product.category_id == int(category_id))
        prods = q.order_by(Product.name).all(); s.expunge_all()
    for p in prods:
        lines = get_bom_explosion(p.id, 1)
        if not lines:
            continue
        cost, inc = unit_cost(p.id)
        price = float(p.sale_price or 0)
        portions = min(int(max(get_product_balance(l["component_id"]), 0) // l["quantity"]) if l["quantity"] > 0 else 10 ** 9 for l in lines)
        limiting = min(lines, key=lambda l: (get_product_balance(l["component_id"]) / l["quantity"]) if l["quantity"] > 0 else 10 ** 9)
        rows.append({"id": p.id, "sku": p.sku, "name": p.name, "type": "Kit" if p.product_type == "kit" else "مُصنَّع", "components": len(lines),
                     "cost": round(cost, 4), "price": round(price, 4), "margin": round(price - cost, 4),
                     "margin_pct": round((price - cost) / price * 100, 1) if price else 0.0, "food_cost_pct": round(cost / price * 100, 1) if price else 0.0,
                     "portions": portions, "limiting": limiting["component"].name, "incomplete": inc})
    return rows


def send_order_to_kitchen(order_id):
    """يعلّم كل الأصناف اللي لسه pending إنها اتبعتت للمطبخ، وبيرجّع الأصناف
    دي بس (عشان تتطبع كتذكرة مطبخ جديدة - مش الأصناف اللي اتبعتت قبل كده)."""
    require_action("restaurant", "edit")
    now = datetime.datetime.now()
    with get_session() as s:
        o = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.items).joinedload(RestaurantOrderItem.product),
                                              joinedload(RestaurantOrder.table)).filter(RestaurantOrder.id == int(order_id)).first()
        if not o:
            raise ValueError("الطلب غير موجود")
        if o.state != "open":
            raise ValueError("الطلب ده مقفول")
        pending = [i for i in o.items if i.kitchen_status == "pending"]
        if not pending:
            raise ValueError("مفيش أصناف جديدة للإرسال للمطبخ")
        _check_recipe_stock(o, pending)
        new_items = [{"name": i.product.name if i.product else "-", "quantity": i.quantity, "note": i.note or ""} for i in pending]
        for i in pending:
            i.kitchen_status = "sent"; i.sent_at = now
        table_number = o.table.number if o.table else ""
        order_number = o.number
        order_type = o.order_type
        extra = " - ".join(x for x in (o.customer_name, o.customer_phone) if x)
        s.commit()
    return {"table_number": table_number, "order_number": order_number, "items": new_items, "sent_at": now, "order_type": order_type, "customer_info": extra}


def void_restaurant_order(order_id, reason=""):
    """يلغي الطلب كله من غير فاتورة - بيحرر الطاولة."""
    require_action("restaurant", "delete")
    with get_session() as s:
        o = s.get(RestaurantOrder, int(order_id))
        if not o:
            raise ValueError("الطلب غير موجود")
        if o.state != "open":
            raise ValueError("الطلب ده مقفول بالفعل")
        o.state = "voided"; o.closed_at = datetime.datetime.now()
        o.notes = ((o.notes or "") + f" | ملغى: {reason}").strip(" |")
        sent = [i for i in o.items if i.kitchen_status in ("sent", "served")]
        if sent:
            _add_kitchen_events(s, "order_void", o, [(i.product_id, i.quantity, i.quantity * i.unit_price * (1 + (i.tax_rate or 0) / 100.0)) for i in sent], reason or "إلغاء الطلب")
        s.commit()


def checkout_restaurant_order(order_id, customer_id=None, payment_method_id=None, discount=0.0, payments=None, discount_spec=None):
    """يحوّل الطلب المفتوح لفاتورة POS عادية (نفس create_pos_sale)، بيقفل
    الطلب وبيحرر الطاولة (لو كانت طاولة أصلاً). الأصناف اللي لسه ما
    اتبعتتش للمطبخ بتتضمّن برضه (الافتراض إن الدفع بيسبقه إرسالها، بس
    مش شرط). طريقة الدفع بتحدد حساب الاستحقاق تلقائيًا من جدول طرق الدفع."""
    require_action("restaurant", "post")
    with get_session() as s:
        o = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.items)).filter(RestaurantOrder.id == int(order_id)).first()
        if not o:
            raise ValueError("الطلب غير موجود")
        if o.state != "open":
            raise ValueError("الطلب ده مقفول بالفعل")
        active = [i for i in o.items if i.kitchen_status != "voided"]
        if not active:
            raise ValueError("مفيش أصناف في الطلب")
        unsent = [i for i in active if i.kitchen_status == "pending"]
        if unsent:
            raise ValueError(f"فيه {len(unsent)} صنف لم يُرسل للمطبخ - أرسل الطلب للمطبخ أولًا قبل إتمام البيع")
        items = [{"product_id": i.product_id, "quantity": i.quantity, "unit_price": i.unit_price, "tax_rate": i.tax_rate}
                 for i in active]
        branch_id = o.branch_id
        terminal_id = o.terminal_id
    if not terminal_id:
        raise ValueError("الطلب ده مالوش ماكينة/جلسة - افتح جلسة وأنشئ الطلب من جديد")

    if not customer_id:
        cfg_customers = list_customers()
        if not cfg_customers:
            raise ValueError("مفيش عملاء مسجّلين - أضف عميل افتراضي (زي 'عميل نقدي') الأول")
        customer_id = cfg_customers[0].id
    if not payment_method_id and not payments:
        raise ValueError("اختر طريقة الدفع")

    result = create_pos_sale(customer_id=customer_id, items=items, payment_method_id=payment_method_id,
                             branch_id=branch_id, discount=discount, terminal_id=terminal_id, payments=payments, discount_spec=discount_spec)

    with get_session() as s:
        o = s.get(RestaurantOrder, int(order_id))
        o.state = "paid"; o.closed_at = datetime.datetime.now(); o.sales_invoice_id = result["invoice_id"]
        s.commit()
    return result


def transfer_restaurant_order(order_id, new_table_id):
    """نقل طلب مفتوح لطاولة فاضية (الأصناف والمطبخ بيتبعوا الطلب، شاشة المطبخ بتعرض رقم الطاولة الجديد)."""
    require_action("restaurant", "edit")
    with get_session() as s:
        o = s.get(RestaurantOrder, int(order_id))
        if not o:
            raise ValueError("الطلب غير موجود")
        if o.state != "open":
            raise ValueError("الطلب ده مقفول")
        if o.order_type != "dine_in" or not o.table_id:
            raise ValueError("النقل لطلبات الصالة بس")
        t = s.get(RestaurantTable, int(new_table_id))
        if not t:
            raise ValueError("الطاولة غير موجودة")
        if t.id == o.table_id:
            raise ValueError("الطلب على نفس الطاولة بالفعل")
        if s.query(RestaurantOrder).filter(RestaurantOrder.table_id == t.id, RestaurantOrder.state == "open").count():
            raise ValueError(f"الطاولة {t.number} عليها طلب مفتوح - استخدم الدمج بدل النقل")
        old = o.table.number if o.table else ""
        o.table_id = t.id
        o.notes = ((o.notes or "") + f"\nنُقل من طاولة {old} إلى {t.number} ({datetime.datetime.now():%H:%M})").strip()
        s.commit()
        return {"order_id": o.id, "from": old, "to": t.number}


def merge_restaurant_orders(source_id, target_id):
    """دمج طلب مفتوح (المصدر) داخل طلب مفتوح تاني (الهدف): الأصناف بتتنقل بحالتها (مبعوث/جديد) والمصدر بيتقفل كـ «مدمج»."""
    require_action("restaurant", "edit")
    if int(source_id) == int(target_id):
        raise ValueError("اختر طلبين مختلفين")
    with get_session() as s:
        src = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.items), joinedload(RestaurantOrder.table)).filter(RestaurantOrder.id == int(source_id)).first()
        dst = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.items), joinedload(RestaurantOrder.table)).filter(RestaurantOrder.id == int(target_id)).first()
        if not src or not dst:
            raise ValueError("الطلب غير موجود")
        if src.state != "open" or dst.state != "open":
            raise ValueError("الدمج بين طلبات مفتوحة بس")
        if (src.terminal_id or 0) != (dst.terminal_id or 0) and src.terminal_id and dst.terminal_id:
            raise ValueError("الطلبين على ماكينتين مختلفتين - مينفعش الدمج")
        moved = 0
        for it in list(src.items):
            it.order_id = dst.id; moved += 1
        s.flush()
        s.expire(src, ["items"]); s.expire(dst, ["items"])
        dst.guests = (dst.guests or 0) + (src.guests or 0)
        label = f"طاولة {src.table.number}" if src.table else src.number
        dst.notes = ((dst.notes or "") + f"\nدُمج معه {src.number} ({label}) - {datetime.datetime.now():%H:%M}").strip()
        src.state = "merged"; src.closed_at = datetime.datetime.now()
        src.notes = ((src.notes or "") + f"\nاندمج في {dst.number}").strip()
        s.commit()
        return {"target_id": dst.id, "moved": moved}


def split_checkout_restaurant_order(order_id, selection, customer_id=None, payment_method_id=None, discount=0.0, payments=None, discount_spec=None):
    """تقسيم الفاتورة: دفع جزء من الأصناف/الكميات (selection = {item_id: quantity}) في فاتورة مستقلة
    والباقي يفضل مفتوح على نفس الطاولة. الأصناف المختارة لازم تكون اتبعتت للمطبخ."""
    require_action("restaurant", "post")
    sel = {int(k): float(v) for k, v in (selection or {}).items() if float(v or 0) > 0}
    if not sel:
        raise ValueError("اختر الأصناف اللي هتتدفع")
    with get_session() as s:
        o = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.items)).filter(RestaurantOrder.id == int(order_id)).first()
        if not o:
            raise ValueError("الطلب غير موجود")
        if o.state != "open":
            raise ValueError("الطلب ده مقفول بالفعل")
        by_id = {i.id: i for i in o.items if i.kitchen_status != "voided"}
        for iid, q in sel.items():
            it = by_id.get(iid)
            if not it:
                raise ValueError("صنف غير موجود في الطلب")
            if it.kitchen_status == "pending":
                raise ValueError("أرسل الأصناف للمطبخ أولًا قبل دفعها")
            if q > it.quantity + 1e-9:
                raise ValueError(f"الكمية المختارة أكبر من الموجود ({it.quantity:g})")
        full = all(abs(sel.get(i.id, 0) - i.quantity) < 1e-9 for i in by_id.values())
    if full:
        return checkout_restaurant_order(order_id, customer_id, payment_method_id, discount, payments, discount_spec)
    with get_session() as s:
        o = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.items)).filter(RestaurantOrder.id == int(order_id)).first()
        by_id = {i.id: i for i in o.items}
        items = [{"product_id": by_id[i].product_id, "quantity": q, "unit_price": by_id[i].unit_price, "tax_rate": by_id[i].tax_rate} for i, q in sel.items()]
        branch_id, terminal_id = o.branch_id, o.terminal_id
    if not terminal_id:
        raise ValueError("الطلب ده مالوش ماكينة/جلسة - افتح جلسة وأنشئ الطلب من جديد")
    if not customer_id:
        cs = list_customers()
        if not cs:
            raise ValueError("مفيش عملاء مسجّلين - أضف عميل افتراضي الأول")
        customer_id = cs[0].id
    if not payment_method_id and not payments:
        raise ValueError("اختر طريقة الدفع")
    result = create_pos_sale(customer_id=customer_id, items=items, payment_method_id=payment_method_id, branch_id=branch_id,
                             discount=discount, terminal_id=terminal_id, payments=payments, discount_spec=discount_spec)
    with get_session() as s:
        o = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.items)).filter(RestaurantOrder.id == int(order_id)).first()
        child = RestaurantOrder(number=_next_code(s, RestaurantOrder, "RT-"), table_id=o.table_id, order_type=o.order_type, customer_name=o.customer_name,
                                customer_phone=o.customer_phone, delivery_address=o.delivery_address, terminal_id=o.terminal_id, pos_session_id=o.pos_session_id,
                                branch_id=o.branch_id, guests=1, state="paid", opened_by=o.opened_by, opened_at=o.opened_at, closed_at=datetime.datetime.now(),
                                sales_invoice_id=result["invoice_id"], notes=f"تقسيم من {o.number}")
        s.add(child); s.flush()
        for iid, q in sel.items():
            it = next(x for x in o.items if x.id == iid)
            s.add(RestaurantOrderItem(order_id=child.id, product_id=it.product_id, quantity=q, unit_price=it.unit_price, tax_rate=it.tax_rate, note=it.note,
                                      course=it.course, kitchen_status=it.kitchen_status, sent_at=it.sent_at, served_at=it.served_at))
            if abs(it.quantity - q) < 1e-9:
                s.delete(it)
            else:
                it.quantity = round(it.quantity - q, 6)
        o.notes = ((o.notes or "") + f"\nدُفع جزء منه في {child.number}").strip()
        s.commit()
    result["split_order_number"] = child.number
    return result


def restaurant_shift_summary(branch_id=None, date_from=None, date_to=None):
    """ملخص سريع: الطلبات المدفوعة والملغاة في الفترة."""
    with get_session() as s:
        q = s.query(RestaurantOrder).options(joinedload(RestaurantOrder.items), joinedload(RestaurantOrder.table))
        if branch_id:
            q = q.filter(RestaurantOrder.branch_id == int(branch_id))
        if date_from:
            q = q.filter(RestaurantOrder.opened_at >= date_from)
        if date_to:
            q = q.filter(RestaurantOrder.opened_at <= date_to)
        orders = q.order_by(RestaurantOrder.opened_at.desc()).all()
        rows = [_order_dict(s, o) | {"table_number": o.table.number if o.table else ""} for o in orders]
    paid = [r for r in rows if r["state"] == "paid"]
    return {"rows": rows, "paid_count": len(paid), "paid_total": round(sum(r["total"] for r in paid), 2),
            "voided_count": sum(1 for r in rows if r["state"] == "voided"), "open_count": sum(1 for r in rows if r["state"] == "open")}


def generate_kitchen_ticket_pdf_file(send_result):
    """يولّد PDF تذكرة مطبخ من نتيجة send_order_to_kitchen (رقم الطاولة +
    رقم الطلب + الأصناف الجديدة بس اللي اتبعتت الآن)."""
    from .invoice_pdf import _simple_doc_pdf
    settings = get_company_settings()
    rows = [(f"{it['quantity']:g} × {it['name']}" + (f"  ({it['note']})" if it['note'] else ''), '') for it in send_result['items']]
    if send_result.get('cancel'):
        rows = [(f"إلغاء: {it['quantity']:g} × {it['name']}", '') for it in send_result['items']] + [(f"السبب: {send_result.get('reason', '')}", '')]
        where = f"طاولة {send_result['table_number']}" if send_result.get('table_number') else RESTAURANT_ORDER_TYPES.get(send_result['order_type'], '')
        return _simple_doc_pdf(f"إلغاء صنف من المطبخ - {where}", f"طلب {send_result['order_number']}  -  {send_result['sent_at']:%H:%M:%S}", rows, downloads_dir(),
                               f"kitchen_cancel_{send_result['order_number']}_{send_result['sent_at']:%H%M%S}", footer_note=None, company=settings)
    if send_result.get('order_type', 'dine_in') == 'dine_in':
        title = f"تذكرة مطبخ - محلي - طاولة {send_result['table_number']}"
    else:
        title = f"تذكرة مطبخ - {RESTAURANT_ORDER_TYPES.get(send_result['order_type'], '')}"
    subtitle = f"طلب {send_result['order_number']}  -  {send_result['sent_at']:%H:%M:%S}" + (f"  -  {send_result['customer_info']}" if send_result.get('customer_info') else '')
    return _simple_doc_pdf(title, subtitle, rows, downloads_dir(), f"kitchen_{send_result['order_number']}_{send_result['sent_at']:%H%M%S}",
                           footer_note=None, company=settings)


# ======================================================================
# طلبات الإجازات (سنوية/مرضية/بدون راتب) والاستئذان والاستقالة ونهاية الخدمة
# ======================================================================

def list_leave_types(active_only=False):
    with get_session() as s:
        q = s.query(LeaveType)
        if active_only:
            q = q.filter(LeaveType.is_active.is_(True))
        rows = q.order_by(LeaveType.sort_order, LeaveType.id).all()
        s.expunge_all()
        return rows


def leave_type_labels(active_only=False):
    """{code: الاسم} - للقوائم وعرض الطلبات القديمة (كل الأنواع، حتى الموقوفة، لما active_only=False)."""
    return {t.code: t.name for t in list_leave_types(active_only)}


def _validate_leave_type_fields(name, deduct_percent, max_days):
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم النوع مطلوب")
    try:
        deduct_percent = float(deduct_percent or 0)
    except (TypeError, ValueError):
        raise ValueError("نسبة الخصم لازم تكون رقم")
    if not (0 <= deduct_percent <= 100):
        raise ValueError("نسبة الخصم لازم تكون بين 0 و100")
    try:
        max_days = int(max_days or 0)
    except (TypeError, ValueError):
        raise ValueError("الحد الأقصى للأيام لازم يكون رقم")
    if max_days < 0:
        raise ValueError("الحد الأقصى للأيام لا يكون سالبًا")
    return name, deduct_percent, max_days


def save_leave_type(type_id=None, name="", deduct_percent=0.0, uses_annual_balance=False, max_days_per_year=0, is_active=True, notes=""):
    """إضافة نوع إجازة جديد (type_id=None) أو تعديل نوع. deduct_percent: 0 = مدفوعة كاملة، 100 = بدون راتب، أو نسبة (مثلًا 25)."""
    require_action("leave_requests", "edit" if type_id else "create")
    name, deduct_percent, max_days = _validate_leave_type_fields(name, deduct_percent, max_days_per_year)
    with get_session() as s:
        dup = s.query(LeaveType).filter(LeaveType.name == name)
        if type_id:
            dup = dup.filter(LeaveType.id != int(type_id))
        if dup.first():
            raise ValueError("فيه نوع إجازة بنفس الاسم")
        if type_id:
            t = s.get(LeaveType, int(type_id))
            if not t:
                raise ValueError("النوع غير موجود")
        else:
            t = LeaveType(code="tmp", name=name)
            s.add(t); s.flush()
            t.code = f"lt{t.id}"
            t.sort_order = 100 + t.id
        t.name = name; t.deduct_percent = deduct_percent; t.max_days_per_year = max_days
        t.uses_annual_balance = bool(uses_annual_balance); t.notes = notes or ""
        if t.is_system and not is_active and t.code == "annual":
            raise ValueError("الإجازة السنوية نوع أساسي ومينفعش توقفه")
        t.is_active = bool(is_active)
        s.commit()
        return t.id


def delete_leave_type(type_id):
    require_action("leave_requests", "delete")
    with get_session() as s:
        t = s.get(LeaveType, int(type_id))
        if not t:
            raise ValueError("النوع غير موجود")
        if t.is_system:
            raise ValueError("النوع ده أساسي ومينفعش يتحذف - عدّله أو أوقفه")
        if s.query(LeaveRequest).filter(LeaveRequest.leave_type == t.code).first():
            raise ValueError("النوع ده عليه طلبات إجازة - أوقفه بدل الحذف")
        s.delete(t); s.commit()


def _annual_codes(s):
    return [t.code for t in s.query(LeaveType).filter(LeaveType.uses_annual_balance.is_(True)).all()] or ["annual"]
REQUEST_STATE_LABELS = {"pending": "قيد المراجعة", "approved": "معتمد", "rejected": "مرفوض", "cancelled": "ملغى"}


def _days_inclusive(start, end):
    return (end.date() - start.date()).days + 1


def annual_leave_balance(employee_id, year=None):
    """رصيد الإجازة السنوية للموظف في سنة معيّنة: المستحق (من إعدادات
    الشركة) ناقص أيام الإجازات السنوية المعتمدة (والمعلّقة كحجز مبدئي)."""
    year = year or datetime.date.today().year
    cfg = get_company_settings()
    allowance = cfg.annual_leave_days or 21
    with get_session() as s:
        rows = s.query(LeaveRequest).filter(
            LeaveRequest.employee_id == int(employee_id), LeaveRequest.leave_type.in_(_annual_codes(s)),
            LeaveRequest.state.in_(["approved", "pending"]),
        ).all()
        used_approved = sum(r.days for r in rows if r.state == "approved" and r.start_date.year == year)
        used_pending = sum(r.days for r in rows if r.state == "pending" and r.start_date.year == year)
    return {"allowance": allowance, "used": used_approved, "pending": used_pending,
            "remaining": allowance - used_approved - used_pending, "year": year}


def accrued_leave_balance(employee_id, as_of, hire_date=None):
    """رصيد الإجازة المستحق فعليًا لحد تاريخ معيّن (لتسوية نهاية الخدمة):
    الاستحقاق السنوي موزّع على أيام الخدمة من تاريخ التعيين لحد التاريخ ده
    (مش السنة كاملة) ناقص كل أيام الإجازات السنوية المعتمدة اللي خدها الموظف
    لحد التاريخ ده. بيرجّع dict فيه: earned, used, remaining (مقرّب لـ 2 رقم)."""
    cfg = get_company_settings()
    allowance = float(cfg.annual_leave_days or 21)
    hire = hire_date or _employee_hire_date(employee_id)
    served = max(0, (as_of.date() - hire.date()).days + 1) if hire else 0
    earned = round(allowance * served / 365.0, 2)
    with get_session() as s:
        rows = s.query(LeaveRequest).filter(
            LeaveRequest.employee_id == int(employee_id), LeaveRequest.leave_type.in_(_annual_codes(s)),
            LeaveRequest.state.in_(["approved", "pending"]),
        ).all()
        used = sum(r.days for r in rows if r.state == "approved")
        pending = sum(r.days for r in rows if r.state == "pending")
    return {"allowance": allowance, "served_days": served, "earned": earned, "used": used, "pending": pending,
            "remaining": round(max(0.0, earned - used - pending), 2)}


def list_leave_requests(employee_id=None, state=None, leave_type=None):
    with get_session() as s:
        q = s.query(LeaveRequest).options(joinedload(LeaveRequest.employee))
        if employee_id:
            q = q.filter(LeaveRequest.employee_id == int(employee_id))
        if state:
            q = q.filter(LeaveRequest.state == state)
        if leave_type:
            q = q.filter(LeaveRequest.leave_type == leave_type)
        rows = q.order_by(LeaveRequest.requested_at.desc()).all()
        s.expunge_all()
        return rows


def create_leave_request(employee_id, leave_type, start_date, end_date, reason=""):
    require_action("leave_requests", "create")
    with get_session() as s0:
        lt = s0.query(LeaveType).filter(LeaveType.code == leave_type).first()
        if lt:
            s0.expunge(lt)
    if not lt:
        raise ValueError("نوع الإجازة غير معروف")
    if not lt.is_active:
        raise ValueError(f'نوع الإجازة "{lt.name}" موقوف')
    if end_date < start_date:
        raise ValueError("تاريخ النهاية قبل تاريخ البداية")
    days = _days_inclusive(start_date, end_date)
    with get_session() as s:
        emp = s.get(Employee, int(employee_id))
        if not emp:
            raise ValueError("الموظف غير موجود")
        if not emp.is_active:
            raise ValueError(f'الموظف "{emp.name}" غير نشط')
        overlap = s.query(LeaveRequest).filter(
            LeaveRequest.employee_id == emp.id, LeaveRequest.state.in_(["pending", "approved"]),
            LeaveRequest.start_date <= end_date, LeaveRequest.end_date >= start_date,
        ).first()
        if overlap:
            raise ValueError(f"فيه طلب إجازة تاني متداخل مع نفس الفترة ({overlap.number})")
        emp_name = emp.name
    if lt.uses_annual_balance:
        bal = annual_leave_balance(employee_id, start_date.year)
        if days > bal["remaining"]:
            raise ValueError(f'الرصيد المتاح {bal["remaining"]} يوم بس لسنة {bal["year"]} (المطلوب {days} يوم)')
    if lt.max_days_per_year:
        with get_session() as s1:
            used = sum(r.days for r in s1.query(LeaveRequest).filter(
                LeaveRequest.employee_id == int(employee_id), LeaveRequest.leave_type == lt.code,
                LeaveRequest.state.in_(["approved", "pending"])).all() if r.start_date.year == start_date.year)
        if used + days > lt.max_days_per_year:
            raise ValueError(f'الحد الأقصى لـ "{lt.name}" {lt.max_days_per_year} يوم في السنة (المستخدم {used} والمطلوب {days})')
    with get_session() as s:
        req = LeaveRequest(number=_next_code(s, LeaveRequest, "LV-"), employee_id=int(employee_id), leave_type=leave_type,
                           start_date=start_date, end_date=end_date, days=days, reason=reason or "", state="pending")
        s.add(req); s.commit(); s.refresh(req)
        return req.id


def decide_leave_request(request_id, approve, note=""):
    require_action("leave_requests", "post")
    with get_session() as s:
        req = s.get(LeaveRequest, int(request_id))
        if not req:
            raise ValueError("الطلب غير موجود")
        if req.state != "pending":
            raise ValueError("الطلب ده اتقرر فيه بالفعل")
        req.state = "approved" if approve else "rejected"
        req.decided_at = datetime.datetime.now(); req.decided_by = _current_username(); req.decision_note = note or ""
        s.commit()


def cancel_leave_request(request_id):
    require_action("leave_requests", "edit")
    with get_session() as s:
        req = s.get(LeaveRequest, int(request_id))
        if not req:
            raise ValueError("الطلب غير موجود")
        if req.state not in ("pending", "approved"):
            raise ValueError("الطلب ده مينفعش يتلغى")
        req.state = "cancelled"; req.decided_at = datetime.datetime.now(); req.decided_by = _current_username()
        s.commit()


def list_permission_requests(employee_id=None, state=None):
    with get_session() as s:
        q = s.query(PermissionRequest).options(joinedload(PermissionRequest.employee))
        if employee_id:
            q = q.filter(PermissionRequest.employee_id == int(employee_id))
        if state:
            q = q.filter(PermissionRequest.state == state)
        rows = q.order_by(PermissionRequest.requested_at.desc()).all()
        s.expunge_all()
        return rows


def _parse_hhmm(t):
    try:
        h, m = str(t).strip().split(":")
        h, m = int(h), int(m)
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
        return h * 60 + m
    except Exception:
        raise ValueError(f'الوقت "{t}" غير صحيح - الصيغة HH:MM')


def create_permission_request(employee_id, date, time_from, time_to, reason=""):
    require_action("leave_requests", "create")
    t1, t2 = _parse_hhmm(time_from), _parse_hhmm(time_to)
    if t2 <= t1:
        raise ValueError("وقت النهاية لازم يكون بعد وقت البداية")
    hours = round((t2 - t1) / 60.0, 2)
    if hours > 8:
        raise ValueError("مدة الاستئذان أكبر من يوم عمل - استخدم طلب إجازة بدل كده")
    with get_session() as s:
        emp = s.get(Employee, int(employee_id))
        if not emp:
            raise ValueError("الموظف غير موجود")
        if not emp.is_active:
            raise ValueError(f'الموظف "{emp.name}" غير نشط')
        req = PermissionRequest(number=_next_code(s, PermissionRequest, "PM-"), employee_id=int(employee_id), date=date,
                                time_from=time_from, time_to=time_to, hours=hours, reason=reason or "", state="pending")
        s.add(req); s.commit(); s.refresh(req)
        return req.id


def decide_permission_request(request_id, approve, note=""):
    require_action("leave_requests", "post")
    with get_session() as s:
        req = s.get(PermissionRequest, int(request_id))
        if not req:
            raise ValueError("الطلب غير موجود")
        if req.state != "pending":
            raise ValueError("الطلب ده اتقرر فيه بالفعل")
        req.state = "approved" if approve else "rejected"
        req.decided_at = datetime.datetime.now(); req.decided_by = _current_username(); req.decision_note = note or ""
        s.commit()


def cancel_permission_request(request_id):
    require_action("leave_requests", "edit")
    with get_session() as s:
        req = s.get(PermissionRequest, int(request_id))
        if not req:
            raise ValueError("الطلب غير موجود")
        if req.state not in ("pending", "approved"):
            raise ValueError("الطلب ده مينفعش يتلغى")
        req.state = "cancelled"; req.decided_at = datetime.datetime.now(); req.decided_by = _current_username()
        s.commit()


def list_resignation_requests(employee_id=None, state=None):
    with get_session() as s:
        q = s.query(ResignationRequest).options(joinedload(ResignationRequest.employee))
        if employee_id:
            q = q.filter(ResignationRequest.employee_id == int(employee_id))
        if state:
            q = q.filter(ResignationRequest.state == state)
        rows = q.order_by(ResignationRequest.requested_at.desc()).all()
        s.expunge_all()
        return rows


def create_resignation_request(employee_id, submission_date, last_working_date, reason=""):
    require_action("resignations", "create")
    if last_working_date < submission_date:
        raise ValueError("آخر يوم عمل قبل تاريخ التقديم")
    with get_session() as s:
        emp = s.get(Employee, int(employee_id))
        if not emp:
            raise ValueError("الموظف غير موجود")
        if not emp.is_active:
            raise ValueError(f'الموظف "{emp.name}" غير نشط بالفعل')
        if s.query(ResignationRequest).filter(ResignationRequest.employee_id == emp.id, ResignationRequest.state == "pending").count():
            raise ValueError(f'فيه طلب استقالة قيد المراجعة بالفعل للموظف "{emp.name}"')
        req = ResignationRequest(number=_next_code(s, ResignationRequest, "RS-"), employee_id=int(employee_id),
                                 submission_date=submission_date, last_working_date=last_working_date, reason=reason or "", state="pending")
        s.add(req); s.commit(); s.refresh(req)
        return req.id


def decide_resignation_request(request_id, approve, note=""):
    """الموافقة على الاستقالة بتوقف الموظف وتنهي عقده الساري (state=terminated)
    باعتبار آخر يوم عمل تاريخ الانتهاء - عشان يبقى واضح في تاريخ العقود."""
    require_action("resignations", "post")
    with get_session() as s:
        req = s.get(ResignationRequest, int(request_id))
        if not req:
            raise ValueError("الطلب غير موجود")
        if req.state != "pending":
            raise ValueError("الطلب ده اتقرر فيه بالفعل")
        req.state = "approved" if approve else "rejected"
        req.decided_at = datetime.datetime.now(); req.decided_by = _current_username(); req.decision_note = note or ""
        if approve:
            emp = s.get(Employee, req.employee_id)
            emp.is_active = False
            active_contract = next((c for c in emp.contracts if c.state == "active"), None)
            if active_contract:
                active_contract.state = "terminated"
                active_contract.end_date = req.last_working_date
                active_contract.termination_date = req.last_working_date
                active_contract.termination_reason = f"استقالة - طلب {req.number}"
        s.commit()


def cancel_resignation_request(request_id):
    require_action("resignations", "edit")
    with get_session() as s:
        req = s.get(ResignationRequest, int(request_id))
        if not req:
            raise ValueError("الطلب غير موجود")
        if req.state != "pending":
            raise ValueError("الطلب ده اتقرر فيه بالفعل - مينفعش يتلغى")
        req.state = "cancelled"; req.decided_at = datetime.datetime.now(); req.decided_by = _current_username()
        s.commit()


# ======================================================================
# تسوية نهاية الخدمة: مكافأة (حسب نظام العمل السعودي) + رصيد الإجازة غير
# المستخدم، بقيد محاسبي بيقفل المخصصات المتراكمة ويسجّل الفرق
# ======================================================================
def get_latest_contract(employee_id):
    """آخر عقد للموظف بغض النظر عن حالته - للتسوية بعد ما العقد يتقفل."""
    with get_session() as s:
        return s.query(Contract).filter(Contract.employee_id == int(employee_id)).order_by(Contract.start_date.desc()).first()


def _eos_multiplier(years, termination_type):
    """نسبة استحقاق المكافأة حسب نظام العمل السعودي: إنهاء من الشركة =
    كامل المكافأة دايمًا. استقالة الموظف: أقل من سنتين = صفر، من 2 لـ5 =
    الثلث، من 5 لـ10 = الثلثين، 10 فأكثر = كامل المكافأة."""
    if termination_type == "termination":
        return 1.0
    if years < 2:
        return 0.0
    if years < 5:
        return 1.0 / 3.0
    if years < 10:
        return 2.0 / 3.0
    return 1.0


def _eos_gross_amount(monthly_wage, years):
    """المكافأة كاملة (قبل نسبة الاستقالة): نص شهر عن كل سنة من أول 5
    سنين، وشهر كامل عن كل سنة بعد كده (بالتناسب للكسر من السنة)."""
    if years <= 0 or monthly_wage <= 0:
        return 0.0
    first_5 = min(years, 5.0)
    rest = max(0.0, years - 5.0)
    return round(first_5 * monthly_wage * 0.5 + rest * monthly_wage * 1.0, 2)


def _employee_hire_date(employee_id):
    """تاريخ التعيين الفعلي: تاريخ تعيين الموظف لو متسجّل، وإلا أقدم عقد له.
    (بعد التجديد، بداية آخر عقد مش هي تاريخ التعيين - فسنوات الخدمة لازم تتحسب من الأول)."""
    with get_session() as s:
        emp = s.get(Employee, int(employee_id))
        dates = [d for d in [emp.hire_date if emp else None] if d]
        first = s.query(func.min(Contract.start_date)).filter(Contract.employee_id == int(employee_id)).scalar()
        if first:
            dates.append(first)
        return min(dates) if dates else None


def _provisioned_totals(contract_id):
    """إجمالي مخصص الإجازة ومخصص نهاية الخدمة المتراكم للموظف من الدورات
    المرحّلة فقط (الدورات المسودة ماليهاش أثر محاسبي بعد) - من كل عقوده
    (الأصلي والمجدَّدة)، مش العقد الأخير بس، عشان التجديد ما يضيّعش
    المخصصات المتراكمة."""
    if not contract_id:
        return 0.0, 0.0
    with get_session() as s:
        c = s.get(Contract, int(contract_id))
        if not c:
            return 0.0, 0.0
        contract_ids = [x for (x,) in s.query(Contract.id).filter(Contract.employee_id == c.employee_id).all()]
        rows = s.query(AllowanceInsuranceItem).join(AllowanceInsuranceRun).filter(
            AllowanceInsuranceItem.contract_id.in_(contract_ids), AllowanceInsuranceRun.state == "posted",
        ).all()
        leave = sum(r.leave_provision_amount or 0 for r in rows)
        eos = sum(r.eos_provision_amount or 0 for r in rows)
    return round(leave, 2), round(eos, 2)


def calculate_eos_settlement(employee_id, last_working_date, termination_type="resignation", unused_leave_days=None):
    """يحسب تسوية نهاية الخدمة من غير ما يسجّل حاجة - للمعاينة قبل الحفظ."""
    with get_session() as s:
        emp = s.get(Employee, int(employee_id))
        if not emp:
            raise ValueError("الموظف غير موجود")
        emp_name = emp.name
    contract = get_latest_contract(employee_id)
    if not contract:
        raise ValueError(f'الموظف "{emp_name}" ليس له عقد مسجّل')
    if termination_type not in ("resignation", "termination"):
        raise ValueError("نوع إنهاء الخدمة غير معروف")

    hire_date = _employee_hire_date(employee_id) or contract.start_date
    years = max(0.0, (last_working_date - hire_date).days / 365.25)
    monthly_wage = contract.gross_salary
    gross = _eos_gross_amount(monthly_wage, years)
    multiplier = _eos_multiplier(years, termination_type)
    gratuity = round(gross * multiplier, 2)

    if unused_leave_days is None:
        unused_leave_days = accrued_leave_balance(employee_id, last_working_date, hire_date)["remaining"]
    bal = accrued_leave_balance(employee_id, last_working_date, hire_date)
    daily_rate = round(monthly_wage / 30.0, 2)
    leave_amount = round(unused_leave_days * daily_rate, 2)

    leave_provisioned, eos_provisioned = _provisioned_totals(contract.id)

    return {
        "employee_id": int(employee_id), "employee_name": emp_name, "contract_id": contract.id,
        "hire_date": hire_date, "last_working_date": last_working_date, "termination_type": termination_type,
        "years_of_service": round(years, 2), "monthly_wage": monthly_wage,
        "eos_gross": gross, "eos_multiplier": round(multiplier, 4), "eos_gratuity": gratuity, "eos_provisioned": eos_provisioned,
        "leave_earned": bal["earned"], "leave_used": bal["used"] + bal["pending"],
        "unused_leave_days": unused_leave_days, "daily_rate": daily_rate, "leave_amount": leave_amount, "leave_provisioned": leave_provisioned,
        "contract_accounts": {
            "eos_expense": contract.eos_provision_expense_account_id, "eos_payable": contract.eos_provision_payable_account_id,
            "leave_expense": contract.leave_provision_expense_account_id, "leave_payable": contract.leave_provision_payable_account_id,
        },
    }


def employee_balances_report(as_of=None, active_only=True, search=None):
    """تقرير أرصدة الموظفين لحد تاريخ معيّن: رصيد الإجازة (المستحق / المستخدم /
    المتبقي وقيمته) ومكافأة نهاية الخدمة المستحقة لو استقال أو لو تم إنهاء خدمته
    (بدون تسجيل أي حاجة). الموظف من غير عقد بيظهر بدون مبالغ."""
    require_action("employee_balances", "view")
    as_of = as_of or datetime.datetime.combine(datetime.date.today(), datetime.time())
    rows = []
    for e in list_employees(active_only=active_only, search=search):
        r = {"employee_id": e.id, "code": e.code, "name": e.name, "is_active": e.is_active,
             "hire_date": None, "years": 0.0, "monthly_wage": 0.0, "has_contract": False,
             "leave_earned": 0.0, "leave_used": 0.0, "leave_days": 0.0, "daily_rate": 0.0, "leave_amount": 0.0,
             "eos_resignation": 0.0, "eos_termination": 0.0, "eos_provisioned": 0.0, "leave_provisioned": 0.0}
        try:
            c = calculate_eos_settlement(e.id, as_of, "resignation")
            t = calculate_eos_settlement(e.id, as_of, "termination")
            r.update(has_contract=True, hire_date=c["hire_date"], years=c["years_of_service"], monthly_wage=c["monthly_wage"],
                     leave_earned=c["leave_earned"], leave_used=c["leave_used"], leave_days=c["unused_leave_days"],
                     daily_rate=c["daily_rate"], leave_amount=c["leave_amount"],
                     eos_resignation=c["eos_gratuity"], eos_termination=t["eos_gratuity"],
                     eos_provisioned=c["eos_provisioned"], leave_provisioned=c["leave_provisioned"])
        except ValueError:
            r["hire_date"] = _employee_hire_date(e.id)
        rows.append(r)
    return rows


def list_eos_settlements(employee_id=None):
    with get_session() as s:
        q = s.query(EosSettlement).options(joinedload(EosSettlement.employee))
        if employee_id:
            q = q.filter(EosSettlement.employee_id == int(employee_id))
        rows = q.order_by(EosSettlement.created_at.desc()).all()
        s.expunge_all()
        return rows


def get_eos_settlement(settlement_id):
    with get_session() as s:
        r = s.query(EosSettlement).options(joinedload(EosSettlement.employee)).filter(EosSettlement.id == int(settlement_id)).first()
        if r:
            s.expunge_all()
        return r


def create_eos_settlement(employee_id, last_working_date, termination_type="resignation", unused_leave_days=None,
                          other_dues=0.0, other_dues_note="", other_deductions=0.0, other_deductions_note="",
                          resignation_request_id=None, notes=""):
    """يحسب ويسجّل تسوية نهاية خدمة كمسودة (من غير ترحيل) - تقدر تراجعها
    قبل ما ترحّلها. مينفعش تعمل تسوية تانية للموظف نفسه ولسه فيه مسودة."""
    require_action("eos_settlements", "create")
    calc = calculate_eos_settlement(employee_id, last_working_date, termination_type, unused_leave_days)
    other_dues = float(other_dues or 0); other_deductions = float(other_deductions or 0)
    if other_dues < 0 or other_deductions < 0:
        raise ValueError("المستحقات والخصومات الأخرى لازم تكون أرقام موجبة")
    total = round(calc["eos_gratuity"] + calc["leave_amount"] + other_dues - other_deductions, 2)
    if total < 0:
        raise ValueError("إجمالي التسوية سالب - الخصومات الأخرى أكبر من المستحق")
    with get_session() as s:
        if s.query(EosSettlement).filter(EosSettlement.employee_id == int(employee_id), EosSettlement.state == "draft").count():
            raise ValueError("فيه تسوية مسودة بالفعل لنفس الموظف - كمّلها أو احذفها الأول")
        st = EosSettlement(
            number=_next_code(s, EosSettlement, "EOS-"), employee_id=int(employee_id), contract_id=calc["contract_id"],
            resignation_request_id=int(resignation_request_id) if resignation_request_id else None, termination_type=termination_type,
            hire_date=calc["hire_date"], last_working_date=last_working_date, years_of_service=calc["years_of_service"],
            monthly_wage=calc["monthly_wage"], eos_gross=calc["eos_gross"], eos_multiplier=calc["eos_multiplier"],
            eos_gratuity=calc["eos_gratuity"], eos_provisioned=calc["eos_provisioned"], unused_leave_days=calc["unused_leave_days"],
            daily_rate=calc["daily_rate"], leave_amount=calc["leave_amount"], leave_provisioned=calc["leave_provisioned"],
            other_dues=other_dues, other_dues_note=other_dues_note or "", other_deductions=other_deductions,
            other_deductions_note=other_deductions_note or "", total_amount=total, notes=notes or "", state="draft",
        )
        s.add(st); s.commit(); s.refresh(st)
        return st.id


def delete_eos_settlement(settlement_id):
    require_action("eos_settlements", "delete")
    with get_session() as s:
        st = s.get(EosSettlement, int(settlement_id))
        if not st:
            raise ValueError("التسوية غير موجودة")
        if st.state != "draft":
            raise ValueError("مينفعش تحذف تسوية مرحّلة")
        s.delete(st); s.commit()


def post_eos_settlement(settlement_id, payable_account_id=None, pay_now_account_id=None):
    """يرحّل التسوية: قيد بيقفل المخصصات المتراكمة (لحد سقف كل بند) ويسجّل
    الفرق كمصروف إضافي (لو المستحق أكبر) أو عكس مصروف (لو المتراكم أكبر)،
    ودائن حساب مستحقات الموظفين (أو حساب تدفعه بعتّه pay_now_account_id
    لو هتصرف المبلغ فورًا نقدًا/بنك بدل ما يفضل مستحق)."""
    require_action("eos_settlements", "post")
    with get_session() as s:
        st = s.get(EosSettlement, int(settlement_id))
        if not st:
            raise ValueError("التسوية غير موجودة")
        if st.state != "draft":
            raise ValueError("التسوية مرحّلة بالفعل")
        contract = s.get(Contract, st.contract_id) if st.contract_id else None
        if not contract:
            raise ValueError("عقد الموظف غير موجود")
        eos_expense_id, eos_payable_id = contract.eos_provision_expense_account_id, contract.eos_provision_payable_account_id
        leave_expense_id, leave_payable_id = contract.leave_provision_expense_account_id, contract.leave_provision_payable_account_id
        if st.eos_gratuity and not (eos_expense_id and eos_payable_id):
            raise ValueError("حسابات مخصص نهاية الخدمة ناقصة في عقد الموظف")
        if st.leave_amount and not (leave_expense_id and leave_payable_id):
            raise ValueError("حسابات مخصص الإجازة ناقصة في عقد الموظف")
        cfg = s.get(AccountingSettings, 1)
        credit_account_id = int(pay_now_account_id) if pay_now_account_id else (int(payable_account_id) if payable_account_id else cfg.employee_advances_account_id)
        if not credit_account_id:
            raise ValueError("حدد حساب سداد المستحقات (أو اضبط حساب سلف الموظفين في الإعدادات)")
        number, emp_name = st.number, st.employee.name if st.employee else ""

        debit, credit = {}, {}

        def plug(expense_id, payable_id, provisioned, due):
            """يقفل حساب المستحق المتراكم بالكامل (Dr) عشان يتصفّى بعد رحيل
            الموظف، والفرق بين المتراكم والمستحق الفعلي بيتسوّى في حساب
            المصروف نفسه: مصروف إضافي لو المستحق أكبر من المتراكم، أو عكس
            مصروف (تخفيضه) لو المتراكم كان أكبر من المستحق الفعلي."""
            if not due and not provisioned:
                return
            if provisioned:
                debit[payable_id] = debit.get(payable_id, 0.0) + provisioned
            diff = round(due - provisioned, 2)
            if diff > 0.005:
                debit[expense_id] = debit.get(expense_id, 0.0) + diff
            elif diff < -0.005:
                credit[expense_id] = credit.get(expense_id, 0.0) + (-diff)

        plug(eos_expense_id, eos_payable_id, st.eos_provisioned, st.eos_gratuity)
        plug(leave_expense_id, leave_payable_id, st.leave_provisioned, st.leave_amount)

        if st.other_dues:
            other_expense = cfg.salary_expense_account_id or eos_expense_id
            if not other_expense:
                raise ValueError("حدد حساب مصروف الرواتب في الإعدادات (لسداد مستحقات أخرى)")
            debit[other_expense] = debit.get(other_expense, 0.0) + st.other_dues
        if st.other_deductions:
            # الخصومات الأخرى (زي سلفة سابقة) بتتقفل من حساب سلف/مستحقات
            # الموظفين نفسه - عشان تقلّل صافي المدفوع من غير ما تكسر توازن القيد
            if not cfg.employee_advances_account_id:
                raise ValueError("حدد حساب سلف الموظفين في الإعدادات المحاسبية عشان يترحّل عليه الخصم")
            credit[cfg.employee_advances_account_id] = credit.get(cfg.employee_advances_account_id, 0.0) + st.other_deductions

        lines = [{"account_id": aid, "debit": round(amt, 2)} for aid, amt in debit.items() if amt]
        lines += [{"account_id": aid, "credit": round(amt, 2)} for aid, amt in credit.items() if amt and aid != credit_account_id]
        if st.total_amount:
            lines.append({"account_id": credit_account_id, "credit": round(st.total_amount, 2)})
        if not lines:
            raise ValueError("مفيش قيمة تُرحّل في التسوية دي")

        settlement_id_val, last_working_date, employee_id_val = st.id, st.last_working_date, st.employee_id

    jid = create_journal_entry(
        lines, reference=number, description=f"تسوية نهاية خدمة - {emp_name} ({number})",
        source_type="eos_settlement", source_id=settlement_id_val, entry_date=last_working_date,
    )
    with get_session() as s:
        st = s.get(EosSettlement, settlement_id_val)
        st.state = "posted"; st.posted_at = datetime.datetime.now(); st.journal_entry_id = jid
        s.commit()
    return jid


# ======================================================================
# تسوية دورية لرصيد الإجازة السنوية: تاريخ التعيين + تاريخ آخر إجازة +
# المستحق بالتناسب الزمني من آخر تسوية (أو التعيين) لحد تاريخ التسوية
# ======================================================================
def get_last_leave_date(employee_id, before=None):
    """آخر يوم إجازة معتمدة للموظف (أي نوع) قبل تاريخ معيّن - أو None لو
    ماخدش إجازة قبل كده خالص."""
    with get_session() as s:
        q = s.query(LeaveRequest).filter(LeaveRequest.employee_id == int(employee_id), LeaveRequest.state == "approved")
        if before:
            q = q.filter(LeaveRequest.end_date < before)
        last = q.order_by(LeaveRequest.end_date.desc()).first()
        return last.end_date if last else None


def get_last_annual_leave_settlement(employee_id):
    with get_session() as s:
        return s.query(AnnualLeaveSettlement).filter(
            AnnualLeaveSettlement.employee_id == int(employee_id), AnnualLeaveSettlement.state == "posted",
        ).order_by(AnnualLeaveSettlement.settlement_date.desc()).first()


def calculate_annual_leave_settlement(employee_id, settlement_date):
    """يحسب تسوية الإجازة السنوية من غير ما يسجّل حاجة - للمعاينة قبل الحفظ."""
    with get_session() as s:
        emp = s.get(Employee, int(employee_id))
        if not emp:
            raise ValueError("الموظف غير موجود")
        emp_name, hire_date = emp.name, emp.hire_date
    if not hire_date:
        raise ValueError(f'الموظف "{emp_name}" ليس له تاريخ تعيين مسجّل')
    if settlement_date < hire_date:
        raise ValueError("تاريخ التسوية قبل تاريخ التعيين")

    last = get_last_annual_leave_settlement(employee_id)
    period_start = last.settlement_date if last else hire_date
    opening_balance = last.closing_balance if last else 0.0
    if settlement_date <= period_start:
        raise ValueError(f"تاريخ التسوية لازم يكون بعد تاريخ التسوية السابقة ({period_start:%Y-%m-%d})" if last
                         else "تاريخ التسوية لازم يكون بعد تاريخ التعيين")

    cfg = get_company_settings()
    allowance = cfg.annual_leave_days or 21
    service_days = (settlement_date - period_start).days
    accrued_days = round(service_days / 365.25 * allowance, 2)

    with get_session() as s:
        used = s.query(LeaveRequest).filter(
            LeaveRequest.employee_id == int(employee_id), LeaveRequest.leave_type.in_(_annual_codes(s)),
            LeaveRequest.state == "approved", LeaveRequest.start_date >= period_start, LeaveRequest.start_date <= settlement_date,
        ).all()
        used_days = round(sum(r.days for r in used), 2)

    contract = get_latest_contract(employee_id)
    daily_rate = round((contract.gross_salary / 30.0), 2) if contract else 0.0
    last_leave_date = get_last_leave_date(employee_id, before=settlement_date)

    return {
        "employee_id": int(employee_id), "employee_name": emp_name, "contract_id": contract.id if contract else None,
        "hire_date": hire_date, "last_leave_date": last_leave_date, "period_start": period_start, "settlement_date": settlement_date,
        "opening_balance": round(opening_balance, 2), "accrued_days": accrued_days, "used_days": used_days,
        "closing_balance_before_encash": round(opening_balance + accrued_days - used_days, 2),
        "daily_rate": daily_rate, "allowance_per_year": allowance, "service_days": service_days,
        "is_first_settlement": last is None,
    }


def list_annual_leave_settlements(employee_id=None):
    with get_session() as s:
        q = s.query(AnnualLeaveSettlement).options(joinedload(AnnualLeaveSettlement.employee))
        if employee_id:
            q = q.filter(AnnualLeaveSettlement.employee_id == int(employee_id))
        rows = q.order_by(AnnualLeaveSettlement.settlement_date.desc()).all()
        s.expunge_all()
        return rows


def get_annual_leave_settlement(settlement_id):
    with get_session() as s:
        r = s.query(AnnualLeaveSettlement).options(joinedload(AnnualLeaveSettlement.employee)).filter(
            AnnualLeaveSettlement.id == int(settlement_id)).first()
        if r:
            s.expunge_all()
        return r


def create_annual_leave_settlement(employee_id, settlement_date, encashed_days=0.0, notes=""):
    """يحسب ويسجّل تسوية إجازة سنوية كمسودة. مينفعش تعمل تسوية تانية
    مسودة لنفس الموظف، ولازم تترحّل تسويات الموظف بالترتيب الزمني."""
    require_action("annual_leave_settlements", "create")
    calc = calculate_annual_leave_settlement(employee_id, settlement_date)
    encashed_days = float(encashed_days or 0)
    if encashed_days < 0:
        raise ValueError("أيام الاستبدال النقدي يجب أن تكون رقم موجب")
    if encashed_days > calc["closing_balance_before_encash"]:
        raise ValueError(f'أيام الاستبدال أكبر من الرصيد المتاح ({calc["closing_balance_before_encash"]:g} يوم)')
    closing_balance = round(calc["closing_balance_before_encash"] - encashed_days, 2)
    encashed_amount = round(encashed_days * calc["daily_rate"], 2)

    with get_session() as s:
        if s.query(AnnualLeaveSettlement).filter(AnnualLeaveSettlement.employee_id == int(employee_id), AnnualLeaveSettlement.state == "draft").count():
            raise ValueError("فيه تسوية مسودة بالفعل لنفس الموظف - كمّلها أو احذفها الأول")
        st = AnnualLeaveSettlement(
            number=_next_code(s, AnnualLeaveSettlement, "ALV-"), employee_id=int(employee_id), contract_id=calc["contract_id"],
            hire_date=calc["hire_date"], last_leave_date=calc["last_leave_date"], period_start=calc["period_start"],
            settlement_date=settlement_date, opening_balance=calc["opening_balance"], accrued_days=calc["accrued_days"],
            used_days=calc["used_days"], closing_balance=closing_balance, encashed_days=encashed_days,
            daily_rate=calc["daily_rate"], encashed_amount=encashed_amount, notes=notes or "", state="draft",
        )
        s.add(st); s.commit(); s.refresh(st)
        return st.id


def delete_annual_leave_settlement(settlement_id):
    require_action("annual_leave_settlements", "delete")
    with get_session() as s:
        st = s.get(AnnualLeaveSettlement, int(settlement_id))
        if not st:
            raise ValueError("التسوية غير موجودة")
        if st.state != "draft":
            raise ValueError("مينفعش تحذف تسوية مرحّلة")
        s.delete(st); s.commit()


def post_annual_leave_settlement(settlement_id, cash_account_id=None):
    """يرحّل التسوية. لو مفيش استبدال نقدي (encashed_days=0) بترحّل من
    غير قيد محاسبي (توثيق رصيد بس). لو فيه استبدال نقدي، بيترحّل قيد:
    مدين مخصص الإجازة المستحق (من حسابات عقد الموظف) / دائن حساب الصرف."""
    require_action("annual_leave_settlements", "post")
    with get_session() as s:
        st = s.get(AnnualLeaveSettlement, int(settlement_id))
        if not st:
            raise ValueError("التسوية غير موجودة")
        if st.state != "draft":
            raise ValueError("التسوية مرحّلة بالفعل")
        emp_name = st.employee.name if st.employee else ""
        number, settlement_date, encashed_days, encashed_amount = st.number, st.settlement_date, st.encashed_days, st.encashed_amount
        contract_id = st.contract_id

        jid = None
        if encashed_days:
            if not cash_account_id:
                raise ValueError("حدد حساب الصرف (نقدي/بنك) عشان الاستبدال النقدي")
            contract = s.get(Contract, contract_id) if contract_id else None
            leave_payable_id = contract.leave_provision_payable_account_id if contract else None
            leave_expense_id = contract.leave_provision_expense_account_id if contract else None
            settlement_id_val = st.id

    if encashed_days:
        lines = [{"account_id": int(leave_payable_id) if leave_payable_id else int(leave_expense_id),
                  "debit": round(encashed_amount, 2)}, {"account_id": int(cash_account_id), "credit": round(encashed_amount, 2)}]
        if not (leave_payable_id or leave_expense_id):
            raise ValueError("حسابات مخصص الإجازة ناقصة في عقد الموظف - حدد حساب مخصص الإجازة المستحق أو مصروفه")
        jid = create_journal_entry(
            lines, reference=number, description=f"استبدال نقدي لرصيد إجازة - {emp_name} ({number})",
            source_type="annual_leave_settlement", source_id=settlement_id_val, entry_date=settlement_date,
        )
    with get_session() as s:
        st = s.get(AnnualLeaveSettlement, int(settlement_id))
        st.state = "posted"; st.posted_at = datetime.datetime.now(); st.journal_entry_id = jid
        s.commit()
    return jid


# ======================================================================
# طرق الدفع: جدول بيربط كل طريقة دفع بحساب محاسبي محدد مسبقًا، عشان
# شاشات البيع (نقاط البيع والمطاعم) تختار طريقة الدفع بس من غير ما تسأل
# عن الحساب كل مرة
# ======================================================================
def list_payment_methods(active_only=False):
    with get_session() as s:
        q = s.query(PaymentMethod).options(joinedload(PaymentMethod.account))
        if active_only:
            q = q.filter(PaymentMethod.is_active.is_(True))
        rows = q.order_by(PaymentMethod.sort_order, PaymentMethod.name).all()
        s.expunge_all()
        return rows


def get_payment_method(method_id):
    with get_session() as s:
        m = s.query(PaymentMethod).options(joinedload(PaymentMethod.account)).filter(PaymentMethod.id == int(method_id)).first()
        if m:
            s.expunge_all()
        return m


def _check_payment_method_fields(name, account_id, is_credit):
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم طريقة الدفع مطلوب")
    if not is_credit and not account_id:
        raise ValueError('حدد الحساب المرتبط، أو فعّل "آجل - بدون حساب ثابت" لو الطريقة دي بتسجّل دين على العميل')
    if is_credit and account_id:
        raise ValueError('طريقة "آجل" بتستخدم حساب العميل نفسه تلقائيًا - متحددش حساب ثابت ليها')
    return name


def pm_is_cash(m):
    """طريقة الدفع النقدية (بتدخل صندوق الكاشير): اللي اتحددت نقدي صراحة، أو (لو متحددتش) اللي اسمها "نقدي". الآجل مش نقدي أبدًا."""
    if m is None or getattr(m, "is_credit", False):
        return False
    return bool(m.is_cash) if m.is_cash is not None else (m.name or "").strip() == "نقدي"


def create_payment_method(name, account_id=None, is_credit=False, sort_order=0, is_cash=None, provider_id=None):
    require_action("payment_methods", "create")
    name = _check_payment_method_fields(name, account_id, is_credit)
    with get_session() as s:
        if s.query(PaymentMethod).filter(PaymentMethod.name == name).count():
            raise ValueError(f'طريقة دفع "{name}" موجودة بالفعل')
        m = PaymentMethod(name=name, account_id=int(account_id) if account_id else None, is_credit=bool(is_credit),
                          is_active=True, sort_order=int(sort_order or 0), is_cash=(None if is_cash is None else bool(is_cash)), provider_id=(int(provider_id) if provider_id and not is_credit else None))
        s.add(m); s.commit(); s.refresh(m)
        return m.id


def update_payment_method(method_id, name, account_id=None, is_credit=False, is_active=True, sort_order=0, is_cash="__keep__", provider_id="__keep__"):
    require_action("payment_methods", "edit")
    name = _check_payment_method_fields(name, account_id, is_credit)
    with get_session() as s:
        m = s.get(PaymentMethod, int(method_id))
        if not m:
            raise ValueError("طريقة الدفع غير موجودة")
        if s.query(PaymentMethod).filter(PaymentMethod.name == name, PaymentMethod.id != m.id).count():
            raise ValueError(f'طريقة دفع "{name}" موجودة بالفعل')
        m.name = name; m.account_id = int(account_id) if account_id else None; m.is_credit = bool(is_credit)
        m.is_active = bool(is_active); m.sort_order = int(sort_order or 0)
        if is_cash != "__keep__":
            m.is_cash = None if is_cash is None else bool(is_cash)
        if provider_id != "__keep__":
            m.provider_id = int(provider_id) if provider_id and not is_credit else None
        s.commit()


def delete_payment_method(method_id):
    require_action("payment_methods", "delete")
    with get_session() as s:
        m = s.get(PaymentMethod, int(method_id))
        if not m:
            raise ValueError("طريقة الدفع غير موجودة")
        if s.query(PaymentMethod).filter(PaymentMethod.is_active.is_(True)).count() <= 1 and m.is_active:
            raise ValueError("مينفعش تحذف آخر طريقة دفع نشطة - وقّفها أو ضيف طريقة تانية الأول")
        s.delete(m); s.commit()


# ======================================================================
# قوائم الأسعار: سعر بيع مخصص لكل عميل (أو مجموعة عملاء مرتبطين بنفس
# القائمة) لكل صنف - لو الصنف مش موجود في قائمة العميل، أو العميل مالوش
# قائمة أسعار خالص، بيترجع لسعر البيع الافتراضي المسجّل على الصنف
# ======================================================================
def list_price_lists(active_only=False):
    with get_session() as s:
        q = s.query(PriceList)
        if active_only:
            q = q.filter(PriceList.is_active.is_(True))
        rows = q.order_by(PriceList.name).all()
        s.expunge_all()
        return rows


def get_price_list(price_list_id):
    with get_session() as s:
        pl = s.get(PriceList, int(price_list_id))
        if pl:
            s.expunge_all()
        return pl


def create_price_list(name, notes=""):
    require_action("price_lists", "create")
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم قائمة الأسعار مطلوب")
    with get_session() as s:
        if s.query(PriceList).filter(PriceList.name == name).count():
            raise ValueError(f'قائمة أسعار "{name}" موجودة بالفعل')
        pl = PriceList(name=name, notes=notes or "", is_active=True)
        s.add(pl); s.commit(); s.refresh(pl)
        return pl.id


def update_price_list(price_list_id, name, notes="", is_active=True):
    require_action("price_lists", "edit")
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم قائمة الأسعار مطلوب")
    with get_session() as s:
        pl = s.get(PriceList, int(price_list_id))
        if not pl:
            raise ValueError("قائمة الأسعار غير موجودة")
        if s.query(PriceList).filter(PriceList.name == name, PriceList.id != pl.id).count():
            raise ValueError(f'قائمة أسعار "{name}" موجودة بالفعل')
        pl.name = name; pl.notes = notes or ""; pl.is_active = bool(is_active)
        s.commit()


def delete_price_list(price_list_id):
    require_action("price_lists", "delete")
    with get_session() as s:
        used = s.query(Customer).filter(Customer.price_list_id == int(price_list_id)).count()
        if used:
            raise ValueError(f"القائمة دي مربوطة بـ{used} عميل - وقّفها أو احذف الربط الأول")
        pl = s.get(PriceList, int(price_list_id))
        if not pl:
            raise ValueError("قائمة الأسعار غير موجودة")
        s.delete(pl); s.commit()


def list_price_list_items(price_list_id):
    with get_session() as s:
        rows = s.query(PriceListItem).options(joinedload(PriceListItem.product)).filter(
            PriceListItem.price_list_id == int(price_list_id)).order_by(PriceListItem.id.desc()).all()
        s.expunge_all()
        return rows


def set_price_list_item(price_list_id, product_id, price):
    """يضيف سعر صنف جديد للقائمة، أو يعدّل سعره لو موجود بالفعل."""
    require_action("price_lists", "edit")
    price = float(price or 0)
    if price <= 0:
        raise ValueError("السعر يجب أن يكون أكبر من صفر")
    with get_session() as s:
        pl = s.get(PriceList, int(price_list_id))
        if not pl:
            raise ValueError("قائمة الأسعار غير موجودة")
        p = s.get(Product, int(product_id))
        if not p:
            raise ValueError("الصنف غير موجود")
        existing = s.query(PriceListItem).filter(
            PriceListItem.price_list_id == pl.id, PriceListItem.product_id == p.id).first()
        if existing:
            existing.price = price
        else:
            s.add(PriceListItem(price_list_id=pl.id, product_id=p.id, price=price))
        s.commit()


def set_price_list_items_bulk(price_list_id, items):
    """يحفظ أسعار أكتر من صنف دفعة واحدة - items: [{"product_id":.., "price":..}, ...].
    أي سطر سعره فاضي أو صفر أو سالب بيتجاهل من غير ما يوقف الباقي (يسمح
    للمستخدم يملى الأسعار اللي يحتاجها بس ويسيب الباقي فاضي)."""
    require_action("price_lists", "edit")
    with get_session() as s:
        pl = s.get(PriceList, int(price_list_id))
        if not pl:
            raise ValueError("قائمة الأسعار غير موجودة")
        existing_map = {it.product_id: it for it in s.query(PriceListItem).filter(PriceListItem.price_list_id == pl.id).all()}
        saved = 0
        for row in items:
            try:
                price = float(row.get("price") or 0)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            product_id = int(row["product_id"])
            if product_id in existing_map:
                existing_map[product_id].price = price
            else:
                s.add(PriceListItem(price_list_id=pl.id, product_id=product_id, price=price))
            saved += 1
        s.commit()
        return saved


def remove_price_list_item(item_id):
    require_action("price_lists", "edit")
    with get_session() as s:
        it = s.get(PriceListItem, int(item_id))
        if not it:
            raise ValueError("السطر غير موجود")
        s.delete(it); s.commit()


def get_customer_product_price(customer_id, product_id):
    """السعر الفعلي لصنف لعميل معيّن: سعر قائمة الأسعار المربوطة بالعميل
    لو موجود، وإلا سعر البيع الافتراضي المسجّل على الصنف."""
    with get_session() as s:
        p = s.get(Product, int(product_id))
        if not p:
            raise ValueError("الصنف غير موجود")
        default_price = p.sale_price or 0.0
        if not customer_id:
            return default_price, False
        c = s.get(Customer, int(customer_id))
        if not c or not c.price_list_id:
            return default_price, False
        item = s.query(PriceListItem).filter(
            PriceListItem.price_list_id == c.price_list_id, PriceListItem.product_id == p.id).first()
        if item:
            return item.price, True
        return default_price, False


# ======================================================================
# عهد الموظفين: صرف عهدة → مصروفات/فواتير مقدَّمة عليها → اعتماد (قيد
# تلقائي) → تعزيز أو إرجاع للباقي. حساب العهد (من الإعدادات) هو الحساب
# المدين وقت الصرف، والدائن وقت اعتماد أي مصروف.
# ======================================================================
CUSTODY_STATE_LABELS = {"open": "مفتوحة", "closed": "مقفولة"}
CUSTODY_EXPENSE_STATE_LABELS = {"pending": "قيد المراجعة", "approved": "معتمد", "rejected": "مرفوض"}
CUSTODY_EXPENSE_TYPE_LABELS = {"expense": "مصروف", "invoice": "فاتورة"}
CUSTODY_FUNDING_LABELS = {"issue": "صرف عهدة", "topup": "تعزيز عهدة", "return": "مرتجع للخزينة"}


def _custody_account_id():
    cfg = get_accounting_settings()
    if not cfg.employee_custody_account_id:
        raise ValueError("حدد حساب عهد الموظفين من إعدادات الشركة (الحسابات الافتراضية) الأول")
    return cfg.employee_custody_account_id


def _custody_balances(c):
    funded = sum(f.amount for f in c.fundings if f.kind in ("issue", "topup"))
    returned = sum(f.amount for f in c.fundings if f.kind == "return")
    spent = sum(e.total for e in c.expenses if e.state == "approved")
    pending = sum(e.total for e in c.expenses if e.state == "pending")
    balance = round(funded - returned - spent, 2)
    return {"funded": round(funded, 2), "returned": round(returned, 2), "spent": round(spent, 2),
            "pending": round(pending, 2), "balance": balance, "available": round(balance - pending, 2)}


def _custody_load_options():
    return (joinedload(EmployeeCustody.employee), joinedload(EmployeeCustody.fundings).joinedload(CustodyFunding.cash_account),
            joinedload(EmployeeCustody.expenses).joinedload(CustodyExpense.account),
            joinedload(EmployeeCustody.expenses).joinedload(CustodyExpense.supplier))


def list_custodies(employee_id=None, state=None):
    """بيرجّع قايمة dicts: العهدة + كل أرصدتها (وارد/مصروف/معلّق/مرتجع/رصيد)."""
    with get_session() as s:
        q = s.query(EmployeeCustody).options(*_custody_load_options())
        if employee_id:
            q = q.filter(EmployeeCustody.employee_id == int(employee_id))
        if state:
            q = q.filter(EmployeeCustody.state == state)
        rows = q.order_by(EmployeeCustody.id.desc()).all()
        out = []
        for c in rows:
            d = {"id": c.id, "number": c.number, "employee_id": c.employee_id, "employee_name": c.employee.name if c.employee else "-",
                 "date": c.date, "purpose": c.purpose or "", "state": c.state, "closed_at": c.closed_at,
                 "expense_count": len(c.expenses), "pending_count": sum(1 for e in c.expenses if e.state == "pending")}
            d.update(_custody_balances(c))
            out.append(d)
        return out


def get_custody(custody_id):
    with get_session() as s:
        c = s.query(EmployeeCustody).options(*_custody_load_options()).filter(EmployeeCustody.id == int(custody_id)).first()
        if not c:
            return None
        d = {"id": c.id, "number": c.number, "employee_id": c.employee_id, "employee_name": c.employee.name if c.employee else "-",
             "date": c.date, "purpose": c.purpose or "", "state": c.state, "closed_at": c.closed_at}
        d.update(_custody_balances(c))
        return d


def _custody_funding_entry(custody, kind, amount, cash_account_id, entry_date, notes=""):
    """بيعمل قيد حركة التمويل ويرجّع رقمه. issue/topup: من حـ العهد / إلى حـ الخزينة، return: العكس.
    (بيتنده خارج أي جلسة مفتوحة - القيد بيفتح جلسته الخاصة.)"""
    custody_acc = _custody_account_id()
    ptype = {"partner_type": "employee", "partner_id": custody["employee_id"]}
    desc = f"{CUSTODY_FUNDING_LABELS[kind]} {custody['number']} - {custody['employee_name']}"
    if kind == "return":
        lines = [{"account_id": int(cash_account_id), "debit": amount, "description": desc},
                 {"account_id": custody_acc, "credit": amount, "description": desc, **ptype}]
    else:
        lines = [{"account_id": custody_acc, "debit": amount, "description": desc, **ptype},
                 {"account_id": int(cash_account_id), "credit": amount, "description": desc}]
    return create_journal_entry(lines, reference=custody["number"], description=desc, source_type="employee_custody",
                                source_id=custody["id"], entry_date=entry_date, branch_id=custody["branch_id"], cost_center_id=custody["cost_center_id"])


def _custody_info(custody_id):
    with get_session() as s:
        c = s.query(EmployeeCustody).options(*_custody_load_options()).filter(EmployeeCustody.id == int(custody_id)).first()
        if not c:
            raise ValueError("العهدة غير موجودة")
        info = {"id": c.id, "number": c.number, "employee_id": c.employee_id, "employee_name": c.employee.name if c.employee else "",
                "branch_id": c.branch_id, "cost_center_id": c.cost_center_id, "state": c.state}
        info.update(_custody_balances(c))
        return info


_FUNDING_PREFIX = {"issue": "CPV-", "topup": "CPV-", "return": "CRV-"}


def _add_custody_funding_row(custody_id, kind, amount, cash_account_id, entry_date, notes, method_name, journal_id):
    """بيسجّل حركة التمويل برقم سند (CPV- لسند صرف العهدة والتعزيز، CRV- لسند الإرجاع) وبيرجّع id."""
    with get_session() as s:
        f = CustodyFunding(custody_id=int(custody_id), kind=kind, date=entry_date, amount=amount, cash_account_id=int(cash_account_id),
                           payment_method_name=method_name, notes=notes or "", journal_entry_id=journal_id)
        s.add(f); s.flush()
        f.number = f"{_FUNDING_PREFIX[kind]}{f.id:05d}"
        s.commit()
        return f.id


def _resolve_payment_method_account(payment_method_id):
    pm = get_payment_method(payment_method_id)
    if not pm:
        raise ValueError("اختر طريقة الدفع")
    if not pm.is_active:
        raise ValueError(f'طريقة الدفع "{pm.name}" موقوفة')
    if pm.is_credit or not pm.account_id:
        raise ValueError(f'طريقة الدفع "{pm.name}" آجل - مينفعش تتصرف بيها عهدة، اختار طريقة نقدية أو بنكية')
    return pm.account_id, pm.name


def create_custody(employee_id, amount, payment_method_id, date=None, purpose="", branch_id=None, cost_center_id=None):
    """صرف عهدة جديدة لموظف: بيفتح العهدة وبيعمل قيد الصرف (مدين عهد الموظفين / دائن الخزينة)."""
    require_action("custody_issues", "create")
    amount = round(float(amount or 0), 2)
    if not employee_id:
        raise ValueError("اختر الموظف")
    if amount <= 0:
        raise ValueError("مبلغ العهدة لازم يكون أكبر من صفر")
    account_id, method_name = _resolve_payment_method_account(payment_method_id)
    _custody_account_id()
    entry_date = date or datetime.datetime.now()
    with get_session() as s:
        emp = s.get(Employee, int(employee_id))
        if not emp:
            raise ValueError("الموظف غير موجود")
        if not emp.is_active:
            raise ValueError("الموظف غير نشط")
        c = EmployeeCustody(number=_next_code(s, EmployeeCustody, "CUS-"), employee_id=emp.id, date=entry_date, purpose=(purpose or "").strip(),
                            branch_id=branch_id or emp.branch_id or default_branch_id(), cost_center_id=cost_center_id or emp.cost_center_id,
                            state="open", created_by=_current_username())
        s.add(c); s.commit(); s.refresh(c)
        custody_id = c.id
    try:
        info = _custody_info(custody_id)
        jid = _custody_funding_entry(info, "issue", amount, account_id, entry_date)
    except Exception:
        with get_session() as s:       # القيد فشل (فترة مقفولة مثلًا) - نلغي العهدة الفاضية
            c = s.get(EmployeeCustody, custody_id)
            if c: s.delete(c); s.commit()
        raise
    _add_custody_funding_row(custody_id, "issue", amount, account_id, entry_date, purpose, method_name, jid)
    return custody_id


def topup_custody(custody_id, amount, payment_method_id, date=None, notes=""):
    """تعزيز عهدة مفتوحة بمبلغ إضافي (قيد صرف جديد على نفس العهدة)."""
    require_action("custody_issues", "create")
    amount = round(float(amount or 0), 2)
    if amount <= 0:
        raise ValueError("مبلغ التعزيز لازم يكون أكبر من صفر")
    account_id, method_name = _resolve_payment_method_account(payment_method_id)
    info = _custody_info(custody_id)
    if info["state"] != "open":
        raise ValueError("العهدة دي مقفولة")
    entry_date = date or datetime.datetime.now()
    jid = _custody_funding_entry(info, "topup", amount, account_id, entry_date)
    _add_custody_funding_row(custody_id, "topup", amount, account_id, entry_date, notes, method_name, jid)


def return_custody_funds(custody_id, amount, payment_method_id, date=None, notes=""):
    """إرجاع جزء من رصيد العهدة للخزينة/البنك (مدين الخزينة / دائن عهد الموظفين)."""
    require_action("custody_issues", "create")
    amount = round(float(amount or 0), 2)
    if amount <= 0:
        raise ValueError("المبلغ المرتجع لازم يكون أكبر من صفر")
    account_id, method_name = _resolve_payment_method_account(payment_method_id)
    info = _custody_info(custody_id)
    if amount > info["available"] + 0.001:
        raise ValueError(f"المبلغ المرتجع ({amount:,.2f}) أكبر من الرصيد المتاح للإرجاع ({info['available']:,.2f}) - فيه مصروفات قيد المراجعة محجوزة من الرصيد")
    entry_date = date or datetime.datetime.now()
    jid = _custody_funding_entry(info, "return", amount, account_id, entry_date)
    _add_custody_funding_row(custody_id, "return", amount, account_id, entry_date, notes, method_name, jid)


def settle_custody(custody_id, return_payment_method_id=None, date=None, notes=""):
    """تسوية عهدة: مستند تسوية بيطابق الوارد بالمصروف المعتمد، وبيرجّع المتبقي للخزينة
    بقيد إرجاع (لو فيه رصيد)، وبيقفل العهدة. لازم مفيش مصروفات قيد المراجعة.
    بيرجّع id مستند التسوية."""
    require_action("custody_settlements", "create")
    info = _custody_info(custody_id)
    if info["state"] != "open":
        raise ValueError("العهدة دي مقفولة بالفعل")
    if info["pending"] > 0:
        raise ValueError(f"فيه مصروفات قيد المراجعة بـ {info['pending']:,.2f} - اعتمدها أو ارفضها الأول")
    entry_date = date or datetime.datetime.now()
    returned_now, fid = 0.0, None
    if info["balance"] > 0.001:
        if not return_payment_method_id:
            raise ValueError(f"فيه رصيد متبقي {info['balance']:,.2f} - اختار طريقة الدفع اللي هيرجع بيها للخزينة")
        account_id, method_name = _resolve_payment_method_account(return_payment_method_id)
        jid = _custody_funding_entry(info, "return", info["balance"], account_id, entry_date)
        fid = _add_custody_funding_row(custody_id, "return", info["balance"], account_id, entry_date, "تسوية وقفل العهدة", method_name, jid)
        returned_now = info["balance"]
    with get_session() as s:
        c = s.get(EmployeeCustody, int(custody_id))
        c.state = "closed"; c.closed_at = entry_date
        st = CustodySettlement(number=_next_code(s, CustodySettlement, "CST-"), custody_id=c.id, date=entry_date, funded=info["funded"],
                               spent=info["spent"], returned_before=info["returned"], returned_now=returned_now, notes=(notes or "").strip(),
                               return_funding_id=fid, created_by=_current_username())
        s.add(st); s.commit(); s.refresh(st)
        return st.id


def close_custody(custody_id, return_payment_method_id=None, date=None):
    """اسم قديم لـ settle_custody (للتوافق)."""
    return settle_custody(custody_id, return_payment_method_id, date)


def list_custody_fundings(kinds=None, employee_id=None, custody_id=None):
    """سندات صرف/تعزيز/إرجاع العهد كـ dicts (برقم السند ومعلوماته)."""
    with get_session() as s:
        q = s.query(CustodyFunding).options(joinedload(CustodyFunding.cash_account), joinedload(CustodyFunding.custody).joinedload(EmployeeCustody.employee))
        if kinds:
            q = q.filter(CustodyFunding.kind.in_(list(kinds)))
        if custody_id:
            q = q.filter(CustodyFunding.custody_id == int(custody_id))
        if employee_id:
            q = q.join(EmployeeCustody).filter(EmployeeCustody.employee_id == int(employee_id))
        out = []
        for f in q.order_by(CustodyFunding.id.desc()).all():
            out.append({"id": f.id, "number": f.number or f"{_FUNDING_PREFIX[f.kind]}{f.id:05d}", "kind": f.kind, "kind_label": CUSTODY_FUNDING_LABELS[f.kind],
                        "date": f.date, "amount": f.amount, "method": f.payment_method_name or (f.cash_account.name if f.cash_account else ""),
                        "account": f"{f.cash_account.code} - {f.cash_account.name}" if f.cash_account else "", "notes": f.notes or "",
                        "custody_id": f.custody_id, "custody_number": f.custody.number if f.custody else "",
                        "employee_name": f.custody.employee.name if f.custody and f.custody.employee else "-",
                        "purpose": f.custody.purpose if f.custody else "", "journal_entry_id": f.journal_entry_id})
        return out


def get_custody_funding_doc(funding_id):
    rows = [r for r in list_custody_fundings() if r["id"] == int(funding_id)]
    if not rows:
        raise ValueError("السند غير موجود")
    d = rows[0]
    with get_session() as s:
        je = s.get(JournalEntry, d["journal_entry_id"]) if d["journal_entry_id"] else None
        d["journal_number"] = je.number if je else ""
    d["balances"] = (get_custody(d["custody_id"]) or {})
    return d


def list_custody_settlements(employee_id=None):
    with get_session() as s:
        q = s.query(CustodySettlement).options(joinedload(CustodySettlement.custody).joinedload(EmployeeCustody.employee))
        if employee_id:
            q = q.join(EmployeeCustody).filter(EmployeeCustody.employee_id == int(employee_id))
        out = []
        for t in q.order_by(CustodySettlement.id.desc()).all():
            out.append({"id": t.id, "number": t.number, "date": t.date, "custody_id": t.custody_id, "custody_number": t.custody.number if t.custody else "",
                        "employee_name": t.custody.employee.name if t.custody and t.custody.employee else "-", "purpose": t.custody.purpose if t.custody else "",
                        "funded": t.funded, "spent": t.spent, "returned_before": t.returned_before, "returned_now": t.returned_now,
                        "returned_total": round((t.returned_before or 0) + (t.returned_now or 0), 2), "notes": t.notes or "", "created_by": t.created_by})
        return out


def get_custody_settlement_doc(settlement_id):
    """مستند التسوية بكل تفاصيله للطباعة: بيانات العهدة + المصروفات المعتمدة (مصروف/فاتورة) + الإجماليات."""
    rows = [r for r in list_custody_settlements() if r["id"] == int(settlement_id)]
    if not rows:
        raise ValueError("مستند التسوية غير موجود")
    d = rows[0]
    d["expenses"] = [e for e in list_custody_expenses(custody_id=d["custody_id"], state="approved")][::-1]
    d["tax_total"] = round(sum(e.tax_amount for e in d["expenses"]), 2)
    return d


def _custody_expense_totals(expense_type, amount, tax_rate):
    amount = round(float(amount or 0), 2)
    if amount <= 0:
        raise ValueError("المبلغ لازم يكون أكبر من صفر")
    if expense_type == "invoice":
        tax_rate = float(tax_rate or 0)
        if tax_rate < 0 or tax_rate > 100:
            raise ValueError("نسبة الضريبة غير صحيحة")
        tax = round(amount * tax_rate / 100.0, 2)
    else:
        tax_rate, tax = 0.0, 0.0
    return amount, tax_rate, tax, round(amount + tax, 2)


def attach_custody_expense_file(expense_id, source_path):
    """بينسخ مرفق (صورة/PDF الفاتورة) لمجلد المرفقات ويربطه بالمصروف."""
    import shutil, uuid
    if not source_path or not os.path.exists(source_path):
        raise ValueError("الملف غير موجود")
    with get_session() as s:
        e = s.get(CustodyExpense, int(expense_id))
        if not e:
            raise ValueError("المصروف غير موجود")
        base_dir = os.path.normpath(os.path.join(APP_DIR, "attachments", "custody_expenses", e.number))
        os.makedirs(base_dir, exist_ok=True)
        root, ext = os.path.splitext(os.path.basename(source_path))
        dest = os.path.join(base_dir, f"{root}_{uuid.uuid4().hex[:8]}{ext}")
        shutil.copy2(source_path, dest)
        e.attachment_path = dest
        s.commit()
        return dest


def add_custody_expense(custody_id, expense_type, account_id, amount, description="", date=None, tax_rate=0.0,
                        supplier_id=None, supplier_name="", invoice_number="", invoice_date=None, attachment_path=""):
    """تقديم مصروف أو فاتورة على عهدة (بيدخل قيد المراجعة - مفيش أثر محاسبي لحد الاعتماد).
    الفاتورة لازم تحمل رقم فاتورة ومورد (من الموردين أو اسم حر)."""
    require_action("custody_expenses", "create")
    if expense_type not in ("expense", "invoice"):
        raise ValueError("نوع المصروف غير معروف")
    if not account_id:
        raise ValueError("اختر حساب المصروف")
    amount, tax_rate, tax, total = _custody_expense_totals(expense_type, amount, tax_rate)
    description = (description or "").strip()
    if expense_type == "expense" and not description:
        raise ValueError("اكتب بيان المصروف")
    if expense_type == "invoice":
        if not (invoice_number or "").strip():
            raise ValueError("رقم الفاتورة مطلوب")
        if not supplier_id and not (supplier_name or "").strip():
            raise ValueError("اختر المورد من الحقل، أو اكتب اسمه واضغط \"إضافة مورد جديد\"")
    with get_session() as s:
        c = s.query(EmployeeCustody).options(*_custody_load_options()).filter(EmployeeCustody.id == int(custody_id)).first()
        if not c:
            raise ValueError("العهدة غير موجودة")
        if c.state != "open":
            raise ValueError("العهدة دي مقفولة - مينفعش تضيف عليها")
        acc = s.get(Account, int(account_id))
        if not acc:
            raise ValueError("حساب المصروف غير موجود")
        if s.query(Account).filter(Account.parent_id == acc.id).count():
            raise ValueError(f'"{acc.code} - {acc.name}" حساب رئيسي - اختر حساب فرعي')
        if invoice_number and expense_type == "invoice" and supplier_id:
            dup = s.query(CustodyExpense).filter(CustodyExpense.supplier_id == int(supplier_id), CustodyExpense.invoice_number == invoice_number.strip(),
                                                  CustodyExpense.state != "rejected").first()
            if dup:
                raise ValueError(f'فاتورة المورد رقم "{invoice_number}" اتسجلت قبل كده على المصروف {dup.number}')
        sup = s.get(Supplier, int(supplier_id)) if supplier_id else None
        bal = _custody_balances(c)
        if total > bal["available"] + 0.001:
            raise ValueError(f"المبلغ ({total:,.2f}) أكبر من الرصيد المتاح في العهدة ({bal['available']:,.2f}) - عزّز العهدة الأول")
        e = CustodyExpense(number=_next_code(s, CustodyExpense, "CEX-"), custody_id=c.id, expense_type=expense_type,
                           date=date or datetime.datetime.now(), description=description, account_id=acc.id, amount=amount,
                           tax_rate=tax_rate, tax_amount=tax, total=total, supplier_id=sup.id if sup else None,
                           supplier_name=(sup.name if sup else (supplier_name or "").strip()), supplier_vat=(sup.vat_number if sup else ""),
                           invoice_number=(invoice_number or "").strip(), invoice_date=invoice_date, attachment_path=attachment_path or "",
                           state="pending", created_by=_current_username())
        s.add(e); s.commit(); s.refresh(e)
        return e.id


def list_custody_expenses(custody_id=None, state=None, employee_id=None):
    with get_session() as s:
        q = s.query(CustodyExpense).options(joinedload(CustodyExpense.account), joinedload(CustodyExpense.supplier),
                                            joinedload(CustodyExpense.custody).joinedload(EmployeeCustody.employee))
        if custody_id:
            q = q.filter(CustodyExpense.custody_id == int(custody_id))
        if state:
            q = q.filter(CustodyExpense.state == state)
        if employee_id:
            q = q.join(EmployeeCustody).filter(EmployeeCustody.employee_id == int(employee_id))
        rows = q.order_by(CustodyExpense.id.desc()).all()
        s.expunge_all()
        return rows


def decide_custody_expense(expense_id, approve, note=""):
    """اعتماد أو رفض مصروف مقدَّم. الاعتماد بيعمل القيد:
    مدين المصروف (قبل الضريبة) [+ مدين ضريبة المدخلات للفاتورة] / دائن عهد الموظفين."""
    require_action("custody_expenses", "post")
    note = (note or "").strip()
    with get_session() as s:
        e = s.query(CustodyExpense).options(joinedload(CustodyExpense.custody).joinedload(EmployeeCustody.employee)).filter(CustodyExpense.id == int(expense_id)).first()
        if not e:
            raise ValueError("المصروف غير موجود")
        if e.state != "pending":
            raise ValueError("المصروف ده اتقرر فيه بالفعل")
        if not approve:
            if not note:
                raise ValueError("اكتب سبب الرفض")
            e.state = "rejected"; e.decided_at = datetime.datetime.now(); e.decided_by = _current_username(); e.decision_note = note
            s.commit(); return
        snap = {"id": e.id, "number": e.number, "type": e.expense_type, "account_id": e.account_id, "amount": e.amount, "tax": e.tax_amount,
                "total": e.total, "date": e.date, "description": e.description, "invoice_number": e.invoice_number, "supplier_name": e.supplier_name,
                "custody_id": e.custody_id}
    info = _custody_info(snap["custody_id"])
    cfg = get_accounting_settings()
    custody_acc = _custody_account_id()
    if snap["tax"] > 0 and not cfg.vat_input_account_id:
        raise ValueError("حساب ضريبة المدخلات غير محدد في الإعدادات")
    if snap["total"] > info["balance"] + 0.001:
        raise ValueError(f"رصيد العهدة ({info['balance']:,.2f}) أقل من المصروف ({snap['total']:,.2f}) - عزّز العهدة الأول")
    desc = f"{CUSTODY_EXPENSE_TYPE_LABELS[snap['type']]} على عهدة {info['number']} - {info['employee_name']}" + (f" - {snap['description']}" if snap["description"] else "")
    if snap["type"] == "invoice":
        desc += f" | فاتورة {snap['invoice_number']} - {snap['supplier_name']}"
    lines = [{"account_id": snap["account_id"], "debit": snap["amount"], "description": desc}]
    if snap["tax"] > 0:
        lines.append({"account_id": cfg.vat_input_account_id, "debit": snap["tax"], "description": f"ضريبة مدخلات - {desc}"})
    lines.append({"account_id": custody_acc, "credit": snap["total"], "description": desc, "partner_type": "employee", "partner_id": info["employee_id"]})
    jid = create_journal_entry(lines, reference=snap["number"], description=desc, source_type="employee_custody_expense", source_id=snap["id"],
                               entry_date=snap["date"], branch_id=info["branch_id"], cost_center_id=info["cost_center_id"])
    with get_session() as s:
        e = s.get(CustodyExpense, snap["id"])
        e.state = "approved"; e.journal_entry_id = jid
        e.decided_at = datetime.datetime.now(); e.decided_by = _current_username(); e.decision_note = note
        s.commit()


def delete_custody_expense(expense_id):
    """حذف مصروف لسه قيد المراجعة أو مرفوض (المعتمد ليه قيد - ماينفعش يتحذف)."""
    require_action("custody_expenses", "delete")
    with get_session() as s:
        e = s.get(CustodyExpense, int(expense_id))
        if not e:
            raise ValueError("المصروف غير موجود")
        if e.state == "approved":
            raise ValueError("المصروف المعتمد ليه قيد محاسبي - مينفعش يتحذف")
        s.delete(e); s.commit()


def custody_statement(custody_id):
    """كشف حساب العهدة: كل حركات التمويل والمصروفات المعتمدة بالترتيب الزمني ورصيد جاري،
    + المصروفات قيد المراجعة والمرفوضة في قسم منفصل."""
    with get_session() as s:
        c = s.query(EmployeeCustody).options(*_custody_load_options()).filter(EmployeeCustody.id == int(custody_id)).first()
        if not c:
            raise ValueError("العهدة غير موجودة")
        events = []
        for f in c.fundings:
            events.append({"date": f.date, "order": 0, "type": CUSTODY_FUNDING_LABELS[f.kind],
                           "description": f.notes or f.payment_method_name, "ref": c.number, "account": f.cash_account.name if f.cash_account else "",
                           "incoming": f.amount if f.kind != "return" else 0.0, "outgoing": f.amount if f.kind == "return" else 0.0})
        for e in c.expenses:
            if e.state == "approved":
                ref = (f"فاتورة {e.invoice_number}" if e.expense_type == "invoice" else e.number)
                desc = e.description or e.supplier_name
                if e.expense_type == "invoice" and e.supplier_name:
                    desc = f"{e.supplier_name}" + (f" - {e.description}" if e.description else "")
                events.append({"date": e.date, "order": 1, "type": CUSTODY_EXPENSE_TYPE_LABELS[e.expense_type], "description": desc, "ref": ref,
                               "account": e.account.name if e.account else "", "incoming": 0.0, "outgoing": e.total})
        events.sort(key=lambda x: (x["date"] or datetime.datetime.min, x["order"]))
        running = 0.0
        for ev in events:
            running = round(running + ev["incoming"] - ev["outgoing"], 2)
            ev["balance"] = running
        bal = _custody_balances(c)
        return {"custody": {"id": c.id, "number": c.number, "employee_name": c.employee.name if c.employee else "-", "date": c.date,
                            "purpose": c.purpose or "", "state": c.state}, "rows": events, "balances": bal,
                "pending": [(e.number, e.date, e.description or e.supplier_name, e.total, "قيد المراجعة") for e in c.expenses if e.state == "pending"],
                "rejected": [(e.number, e.date, e.description or e.supplier_name, e.total, e.decision_note) for e in c.expenses if e.state == "rejected"]}


# ======================================================================
# تقرير ضريبة القيمة المضافة (شهري / ربع سنوي) على نسق الإقرار الضريبي:
#   ضريبة المخرجات (المبيعات) - ضريبة المدخلات (المشتريات والأصول وفواتير العهد)
#   = صافي الضريبة المستحقة، مع مطابقة بدفتر الأستاذ وتنبيهات جودة البيانات.
# ======================================================================
_AR_MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
_AR_QUARTERS = ["الأول", "الثاني", "الثالث", "الرابع"]


def vat_period(period_type, year, month=None, quarter=None):
    """بيحدد بداية ونهاية الفترة وتسميتها. period_type: monthly | quarterly."""
    year = int(year)
    if period_type == "monthly":
        month = int(month or 0)
        if not 1 <= month <= 12:
            raise ValueError("اختر الشهر")
        m1 = m2 = month
        label = f"{_AR_MONTHS[month - 1]} {year}"
    elif period_type == "quarterly":
        quarter = int(quarter or 0)
        if not 1 <= quarter <= 4:
            raise ValueError("اختر الربع")
        m1 = 3 * (quarter - 1) + 1; m2 = m1 + 2
        label = f"الربع {_AR_QUARTERS[quarter - 1]} {year} ({_AR_MONTHS[m1 - 1]} - {_AR_MONTHS[m2 - 1]})"
    else:
        raise ValueError("نوع الفترة غير معروف")
    date_from = datetime.datetime(year, m1, 1)
    date_to = (datetime.datetime(year + 1, 1, 1) if m2 == 12 else datetime.datetime(year, m2 + 1, 1)) - datetime.timedelta(microseconds=1)
    return {"type": period_type, "year": year, "month": month, "quarter": quarter, "label": label, "date_from": date_from, "date_to": date_to}


def _vat_lines_by_rate(items, fallback_base, fallback_tax):
    """بيجمّع سطور الفاتورة حسب نسبة الضريبة: {rate: [base, tax]}. لو مفيش سطور
    (زي فواتير الأصول) بيستخدم إجماليات الفاتورة نفسها."""
    buckets = {}
    for it in items or []:
        base = max(0.0, (it.quantity or 0) * (it.unit_price or 0) - (it.discount or 0))
        rate = float(it.tax_rate or 0)
        tax = round(base * rate / 100.0, 2)
        b = buckets.setdefault(rate, [0.0, 0.0]); b[0] += round(base, 2); b[1] += tax
    if not buckets and (fallback_base or fallback_tax):
        rate = round((fallback_tax / fallback_base) * 100.0) if fallback_base else 0.0
        buckets[float(rate)] = [round(fallback_base or 0.0, 2), round(fallback_tax or 0.0, 2)]
    return buckets


def vat_return(period_type, year, month=None, quarter=None, branch_id=None):
    """يبني تقرير الضريبة كامل (ملخص الإقرار + المطابقة + التفاصيل + التنبيهات)."""
    require_action("vat_report", "view")
    per = vat_period(period_type, year, month, quarter)
    df, dt = per["date_from"], per["date_to"]
    if branch_id and not allowed_branch(int(branch_id)):
        raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    allowed = user_branch_ids()
    cfg = get_accounting_settings()

    def branch_ok(col):
        conds = []
        if branch_id:
            conds.append(col == int(branch_id))
        elif allowed:
            conds.append((col.is_(None)) | (col.in_(allowed)))
        return conds

    warnings = []
    sales_rows = {}        # rate -> [base, tax]
    sales_detail = []
    b2b = {"count": 0, "base": 0.0, "tax": 0.0}; b2c = {"count": 0, "base": 0.0, "tax": 0.0}
    mismatch = 0; b2b_no_vat = 0
    with get_session() as s:
        q = s.query(SalesInvoice).options(joinedload(SalesInvoice.items), joinedload(SalesInvoice.customer)).filter(
            SalesInvoice.voided.isnot(True), SalesInvoice.date >= df, SalesInvoice.date <= dt)
        for c in branch_ok(SalesInvoice.branch_id):
            q = q.filter(c)
        for inv in q.order_by(SalesInvoice.date, SalesInvoice.id).all():
            buckets = _vat_lines_by_rate(inv.items, inv.subtotal, inv.tax_total)
            base = round(sum(b[0] for b in buckets.values()), 2); tax = round(sum(b[1] for b in buckets.values()), 2)
            for rate, (bb, tt) in buckets.items():
                r = sales_rows.setdefault(rate, [0.0, 0.0]); r[0] += bb; r[1] += tt
            if abs(tax - (inv.tax_total or 0)) > 0.05:
                mismatch += 1
            cust = inv.customer
            is_b2b = bool(cust and cust.party_type == "company")
            tgt = b2b if is_b2b else b2c
            tgt["count"] += 1; tgt["base"] += base; tgt["tax"] += tax
            if is_b2b and not (cust.vat_number or "").strip():
                b2b_no_vat += 1
            sales_detail.append({"date": inv.date, "number": inv.number, "party": cust.name if cust else "عميل نقدي",
                                 "vat_number": (cust.vat_number if cust else "") or "", "kind": "B2B" if is_b2b else "B2C",
                                 "base": base, "tax": tax, "total": round(base + tax, 2), "is_pos": bool(inv.is_pos)})

    purchase_sources = {"local": [0.0, 0.0, 0], "assets": [0.0, 0.0, 0], "custody": [0.0, 0.0, 0]}
    purchase_detail = []
    no_vat_suppliers = 0
    with get_session() as s:
        q = s.query(PurchaseInvoice).options(joinedload(PurchaseInvoice.items), joinedload(PurchaseInvoice.supplier)).filter(
            PurchaseInvoice.voided.isnot(True), PurchaseInvoice.date >= df, PurchaseInvoice.date <= dt)
        for c in branch_ok(PurchaseInvoice.branch_id):
            q = q.filter(c)
        for inv in q.order_by(PurchaseInvoice.date, PurchaseInvoice.id).all():
            buckets = _vat_lines_by_rate(inv.items, inv.subtotal, inv.tax_total)
            base = round(sum(b[0] for b in buckets.values()), 2); tax = round(sum(b[1] for b in buckets.values()), 2)
            if inv.items and abs(tax - (inv.tax_total or 0)) > 0.05:
                mismatch += 1
            is_asset = (inv.number or "").startswith("FAP-")
            src = purchase_sources["assets" if is_asset else "local"]
            src[0] += base; src[1] += tax; src[2] += 1
            sup = inv.supplier
            if tax > 0 and not (sup and (sup.vat_number or "").strip()):
                no_vat_suppliers += 1
            purchase_detail.append({"date": inv.date, "source": "أصول ثابتة" if is_asset else "مشتريات", "number": inv.number,
                                    "party": sup.name if sup else "-", "vat_number": (sup.vat_number if sup else "") or "",
                                    "base": base, "tax": tax, "total": round(base + tax, 2)})
        q = s.query(CustodyExpense).options(joinedload(CustodyExpense.custody)).filter(
            CustodyExpense.state == "approved", CustodyExpense.expense_type == "invoice", CustodyExpense.date >= df, CustodyExpense.date <= dt)
        for e in q.order_by(CustodyExpense.date, CustodyExpense.id).all():
            bid = e.custody.branch_id if e.custody else None
            if branch_id and bid != int(branch_id):
                continue
            if allowed and bid is not None and bid not in allowed:
                continue
            src = purchase_sources["custody"]; src[0] += e.amount or 0; src[1] += e.tax_amount or 0; src[2] += 1
            if (e.tax_amount or 0) > 0 and not (e.supplier_vat or "").strip():
                no_vat_suppliers += 1
            purchase_detail.append({"date": e.date, "source": "فاتورة عهدة", "number": e.invoice_number or e.number, "party": e.supplier_name or "-",
                                    "vat_number": e.supplier_vat or "", "base": round(e.amount or 0, 2), "tax": round(e.tax_amount or 0, 2), "total": round(e.total or 0, 2)})

    # ---- ملخص المبيعات
    std_rows = [{"label": f"مبيعات خاضعة للضريبة بنسبة {rate:g}%", "base": round(v[0], 2), "tax": round(v[1], 2), "rate": rate}
                for rate, v in sorted(sales_rows.items(), reverse=True) if rate > 0]
    zero = sales_rows.get(0.0, [0.0, 0.0])
    zero_row = {"label": "مبيعات بنسبة صفر / معفاة", "base": round(zero[0], 2), "tax": 0.0, "rate": 0.0}
    sales_total_base = round(sum(r[0] for r in sales_rows.values()), 2)
    output_tax = round(sum(r[1] for r in sales_rows.values()), 2)

    purchase_rows = [
        {"label": "مشتريات محلية (فواتير المشتريات)", "base": round(purchase_sources["local"][0], 2), "tax": round(purchase_sources["local"][1], 2), "count": purchase_sources["local"][2]},
        {"label": "مشتريات أصول ثابتة", "base": round(purchase_sources["assets"][0], 2), "tax": round(purchase_sources["assets"][1], 2), "count": purchase_sources["assets"][2]},
        {"label": "فواتير مصروفات العهد", "base": round(purchase_sources["custody"][0], 2), "tax": round(purchase_sources["custody"][1], 2), "count": purchase_sources["custody"][2]},
    ]
    purchases_total_base = round(sum(r["base"] for r in purchase_rows), 2)
    input_tax = round(sum(r["tax"] for r in purchase_rows), 2)
    net = round(output_tax - input_tax, 2)

    # ---- المطابقة مع دفتر الأستاذ (قيود مرحّلة فقط)
    def gl_movement(account_id):
        if not account_id:
            return 0.0, 0.0
        with get_session() as s:
            q = s.query(func.coalesce(func.sum(JournalEntryLine.debit), 0.0), func.coalesce(func.sum(JournalEntryLine.credit), 0.0)).join(JournalEntry).filter(
                JournalEntryLine.account_id == int(account_id), JournalEntry.posted.is_(True), JournalEntry.date >= df, JournalEntry.date <= dt)
            for c in branch_ok(JournalEntryLine.branch_id):
                q = q.filter(c)
            d, c_ = q.one()
            return float(d or 0), float(c_ or 0)
    od, oc = gl_movement(cfg.vat_output_account_id); idb, icr = gl_movement(cfg.vat_input_account_id)
    gl_output = round(oc - od, 2); gl_input = round(idb - icr, 2)
    ledger = {"output_gl": gl_output, "output_docs": output_tax, "output_diff": round(gl_output - output_tax, 2),
              "input_gl": gl_input, "input_docs": input_tax, "input_diff": round(gl_input - input_tax, 2),
              "net_gl": round(gl_output - gl_input, 2)}

    if abs(ledger["output_diff"]) > 0.05:
        warnings.append(f"ضريبة المخرجات في دفتر الأستاذ ({gl_output:,.2f}) تختلف عن مجموع الفواتير ({output_tax:,.2f}) بفرق {ledger['output_diff']:,.2f} - غالبًا قيود يدوية أو فواتير في فترة تانية.")
    if abs(ledger["input_diff"]) > 0.05:
        warnings.append(f"ضريبة المدخلات في دفتر الأستاذ ({gl_input:,.2f}) تختلف عن مجموع المستندات ({input_tax:,.2f}) بفرق {ledger['input_diff']:,.2f} - راجع قيود الضريبة اليدوية.")
    if b2b_no_vat:
        warnings.append(f"{b2b_no_vat} فاتورة مبيعات B2B لعملاء من غير رقم ضريبي - الفاتورة الضريبية القياسية بتتطلبه.")
    if no_vat_suppliers:
        warnings.append(f"{no_vat_suppliers} مستند مشتريات فيه ضريبة مدخلات من مورد من غير رقم ضريبي - الخصم ممكن يترفض بدون الرقم الضريبي للمورد.")
    if mismatch:
        warnings.append(f"{mismatch} فاتورة ضريبتها المحسوبة من السطور مختلفة عن الضريبة المحفوظة على الفاتورة.")

    return {
        "period": per, "branch_id": int(branch_id) if branch_id else None,
        "sales": {"rows": std_rows + [zero_row], "total_base": sales_total_base, "total_tax": output_tax,
                  "b2b": {k: round(v, 2) if isinstance(v, float) else v for k, v in b2b.items()},
                  "b2c": {k: round(v, 2) if isinstance(v, float) else v for k, v in b2c.items()},
                  "count": b2b["count"] + b2c["count"], "invoices": sales_detail},
        "purchases": {"rows": purchase_rows, "total_base": purchases_total_base, "total_tax": input_tax, "count": len(purchase_detail), "documents": purchase_detail},
        "summary": {"output_tax": output_tax, "input_tax": input_tax, "net_tax": net,
                    "status": "payable" if net > 0.004 else ("refundable" if net < -0.004 else "zero")},
        "ledger": ledger, "warnings": warnings,
    }


# ======================================================================
# عروض أسعار المبيعات: إنشاء/تعديل → إرسال → قبول/رفض → تحويل لفاتورة مبيعات
# (بنفس الأسعار والخصومات). العرض مالوش أي قيد محاسبي ولا حركة مخزون.
# ======================================================================
QUOTATION_STATE_LABELS = {"draft": "مسودة", "sent": "مرسل للعميل", "accepted": "مقبول", "rejected": "مرفوض", "invoiced": "اتحوّل لفاتورة", "expired": "منتهي الصلاحية"}
QUOTATION_DEFAULT_VALID_DAYS = 15


def quotation_effective_state(q):
    """الحالة الفعلية: العرض المفتوح (مسودة/مرسل/مقبول) اللي فات تاريخ صلاحيته = منتهي."""
    if q.state in ("draft", "sent", "accepted") and q.valid_until and q.valid_until.date() < datetime.date.today():
        return "expired"
    return q.state


def _quotation_totals(items, discount):
    subtotal = tax_total = grand = 0.0
    lines = []
    for it in items:
        base, tax, line_total = _compute_line_total(float(it["quantity"]), float(it["unit_price"]), float(it.get("discount", 0) or 0), float(it.get("tax_rate", 15)))
        subtotal += base; tax_total += tax; grand += line_total
        lines.append((base, tax, line_total))
    discount = round(float(discount or 0), 2)
    if discount < 0:
        raise ValueError("الخصم لا يمكن أن يكون سالبًا")
    if discount > grand + 0.001:
        raise ValueError("خصم العرض أكبر من إجمالي العرض")
    return round(subtotal, 2), round(tax_total, 2), round(max(0.0, grand - discount), 2), discount, lines


def _validate_quotation_items(items):
    if not items:
        raise ValueError("أضف صنف واحد على الأقل للعرض")
    for n, it in enumerate(items, 1):
        if float(it["quantity"]) <= 0:
            raise ValueError(f"السطر {n}: الكمية لازم تكون أكبر من صفر")
        if float(it["unit_price"]) < 0:
            raise ValueError(f"السطر {n}: السعر لا يمكن أن يكون سالبًا")
        d = float(it.get("discount", 0) or 0)
        if d < 0 or d > float(it["quantity"]) * float(it["unit_price"]) + 0.001:
            raise ValueError(f"السطر {n}: الخصم غير صحيح")
        tr = float(it.get("tax_rate", 15))
        if tr < 0 or tr > 100:
            raise ValueError(f"السطر {n}: نسبة الضريبة غير صحيحة")


def _write_quotation_items(s, q, items, lines):
    for it, (base, tax, line_total) in zip(items, lines):
        s.add(SalesQuotationItem(quotation_id=q.id, product_id=int(it["product_id"]), quantity=float(it["quantity"]),
                                 unit_id=int(it["unit_id"]) if it.get("unit_id") else None, unit_price=float(it["unit_price"]),
                                 discount=float(it.get("discount", 0) or 0), tax_rate=float(it.get("tax_rate", 15)), line_total=line_total))


def create_quotation(customer_id, items, notes="", terms="", discount=0.0, quote_date=None, valid_until=None, branch_id=None, cost_center_id=None):
    require_action("sales_quotations", "create")
    if not customer_id:
        raise ValueError("اختر العميل")
    _validate_quotation_items(items)
    quote_date = quote_date or datetime.datetime.now()
    valid_until = valid_until or (quote_date + datetime.timedelta(days=QUOTATION_DEFAULT_VALID_DAYS))
    if valid_until.date() < quote_date.date():
        raise ValueError("تاريخ صلاحية العرض لا يمكن أن يكون قبل تاريخه")
    branch_id = branch_id or default_branch_id()
    cost_center_id = cost_center_id or default_cost_center_id()
    if branch_id and not allowed_branch(branch_id):
        raise PermissionError("الفرع غير مسموح لهذا المستخدم")
    subtotal, tax_total, total, discount, lines = _quotation_totals(items, discount)
    with get_session() as s:
        if not s.get(Customer, int(customer_id)):
            raise ValueError("العميل غير موجود")
        q = SalesQuotation(number=_next_code(s, SalesQuotation, "QT-", 6), date=quote_date, valid_until=valid_until, customer_id=int(customer_id),
                           branch_id=branch_id, cost_center_id=cost_center_id, subtotal=subtotal, discount=discount, tax_total=tax_total, total=total,
                           notes=(notes or "").strip(), terms=(terms or "").strip(), state="draft", created_by=_current_username())
        s.add(q); s.flush()
        _write_quotation_items(s, q, items, lines)
        s.commit()
        return q.id


def _quotation_load_options():
    return (joinedload(SalesQuotation.customer), joinedload(SalesQuotation.branch), joinedload(SalesQuotation.invoice),
            joinedload(SalesQuotation.items).joinedload(SalesQuotationItem.product), joinedload(SalesQuotation.items).joinedload(SalesQuotationItem.unit))


def get_quotation(quotation_id):
    with get_session() as s:
        q = s.query(SalesQuotation).options(*_quotation_load_options()).filter(SalesQuotation.id == int(quotation_id)).first()
        if q:
            s.expunge_all()
        return q


def update_quotation(quotation_id, customer_id, items, notes="", terms="", discount=0.0, quote_date=None, valid_until=None, branch_id=None, cost_center_id=None):
    """تعديل عرض (مسودة أو مرسل أو مقبول). العرض اللي اتحوّل لفاتورة أو اتحسم برفض مينفعش يتعدّل
    (انسخه كعرض جديد). التعديل بيرجّع العرض لحالة مسودة لو كان مرسل/مقبول لإن العميل وافق على نسخة قديمة."""
    require_action("sales_quotations", "edit")
    if not customer_id:
        raise ValueError("اختر العميل")
    _validate_quotation_items(items)
    subtotal, tax_total, total, discount, lines = _quotation_totals(items, discount)
    with get_session() as s:
        q = s.query(SalesQuotation).filter(SalesQuotation.id == int(quotation_id)).first()
        if not q:
            raise ValueError("العرض غير موجود")
        if q.state == "invoiced":
            raise ValueError("العرض ده اتحوّل لفاتورة - مينفعش يتعدّل")
        if q.state == "rejected":
            raise ValueError("العرض ده مرفوض - انسخه كعرض جديد لو عايز تعدّله")
        qd = quote_date or q.date
        vu = valid_until or q.valid_until
        if vu and vu.date() < qd.date():
            raise ValueError("تاريخ صلاحية العرض لا يمكن أن يكون قبل تاريخه")
        q.customer_id = int(customer_id); q.date = qd; q.valid_until = vu
        if branch_id: q.branch_id = int(branch_id)
        if cost_center_id: q.cost_center_id = int(cost_center_id)
        q.subtotal, q.tax_total, q.total, q.discount = subtotal, tax_total, total, discount
        q.notes = (notes or "").strip(); q.terms = (terms or "").strip()
        if q.state in ("sent", "accepted"):
            q.state = "draft"; q.decision_note = ""; q.decided_at = None
        for it in list(q.items):
            s.delete(it)
        s.flush()
        _write_quotation_items(s, q, items, lines)
        s.commit()


def list_quotations(state=None, customer_id=None, date_from=None, date_to=None, text=None, limit=1000):
    """state يقبل: draft/sent/accepted/rejected/invoiced/expired (المنتهي بيتحسب من تاريخ الصلاحية)."""
    with get_session() as s:
        q = s.query(SalesQuotation).options(joinedload(SalesQuotation.customer), joinedload(SalesQuotation.invoice)).outerjoin(Customer, SalesQuotation.customer_id == Customer.id)
        if customer_id:
            q = q.filter(SalesQuotation.customer_id == int(customer_id))
        if date_from:
            q = q.filter(SalesQuotation.date >= _dt_start(date_from))
        if date_to:
            q = q.filter(SalesQuotation.date <= _dt_end(date_to))
        if text and text.strip():
            like = f"%{text.strip()}%"
            q = q.filter((SalesQuotation.number.like(like)) | (Customer.name.like(like)))
        if user_branch_ids():
            q = q.filter((SalesQuotation.branch_id.is_(None)) | (SalesQuotation.branch_id.in_(user_branch_ids())))
        rows = q.order_by(SalesQuotation.id.desc()).limit(int(limit)).all()
        if state:
            rows = [r for r in rows if quotation_effective_state(r) == state]
        s.expunge_all()
        return rows


def set_quotation_state(quotation_id, new_state, note=""):
    """تغيير حالة العرض: sent (تم إرساله) | accepted (العميل وافق) | rejected (العميل رفض - بسبب) | draft (رجوع لمسودة)."""
    require_action("sales_quotations", "edit")
    if new_state not in ("draft", "sent", "accepted", "rejected"):
        raise ValueError("حالة غير معروفة")
    note = (note or "").strip()
    with get_session() as s:
        q = s.query(SalesQuotation).filter(SalesQuotation.id == int(quotation_id)).first()
        if not q:
            raise ValueError("العرض غير موجود")
        if q.state == "invoiced":
            raise ValueError("العرض ده اتحوّل لفاتورة - الحالة ما تتغيّرش")
        if new_state == "rejected" and not note:
            raise ValueError("اكتب سبب رفض العميل للعرض")
        if new_state == "accepted" and quotation_effective_state(q) == "expired":
            raise ValueError("العرض منتهي الصلاحية - عدّل تاريخ الصلاحية الأول")
        q.state = new_state; q.decision_note = note; q.decided_at = datetime.datetime.now() if new_state in ("accepted", "rejected") else None
        s.commit()


def duplicate_quotation(quotation_id):
    """نسخة جديدة (مسودة) من عرض - بأسعاره وبنوده - بتاريخ النهاردة وصلاحية جديدة."""
    require_action("sales_quotations", "create")
    q = get_quotation(quotation_id)
    if not q:
        raise ValueError("العرض غير موجود")
    items = [{"product_id": i.product_id, "unit_id": i.unit_id, "quantity": i.quantity, "unit_price": i.unit_price, "discount": i.discount, "tax_rate": i.tax_rate} for i in q.items]
    return create_quotation(q.customer_id, items, notes=q.notes, terms=q.terms, discount=q.discount, branch_id=q.branch_id, cost_center_id=q.cost_center_id)


def delete_quotation(quotation_id):
    require_action("sales_quotations", "delete")
    with get_session() as s:
        q = s.query(SalesQuotation).filter(SalesQuotation.id == int(quotation_id)).first()
        if not q:
            raise ValueError("العرض غير موجود")
        if q.state == "invoiced":
            raise ValueError("العرض ده اتحوّل لفاتورة - مينفعش يتحذف")
        s.delete(q); s.commit()


def convert_quotation_to_invoice(quotation_id, location_id=None, invoice_date=None, allow_expired=False):
    """تحويل عرض سعر لفاتورة مبيعات بنفس الأصناف والأسعار والخصومات (والعميل والفرع). بيتحقق من
    المخزون زي أي فاتورة. العرض بيتقفل بحالة 'اتحوّل لفاتورة' ومربوط برقم الفاتورة،
    والفاتورة بتحمل رقم العرض في ملاحظاتها. بيرجّع id الفاتورة."""
    require_action("sales_quotations", "post")
    q = get_quotation(quotation_id)
    if not q:
        raise ValueError("العرض غير موجود")
    if q.state == "invoiced":
        raise ValueError(f"العرض ده اتحوّل قبل كده لفاتورة {q.invoice.number if q.invoice else ''}")
    if q.state == "rejected":
        raise ValueError("العرض ده مرفوض من العميل - مينفعش يتحوّل لفاتورة")
    if quotation_effective_state(q) == "expired" and not allow_expired:
        raise ValueError(f"العرض منتهي الصلاحية (من {q.valid_until:%Y-%m-%d}) - عدّل تاريخ الصلاحية أو أكّد التحويل")
    items = [{"product_id": i.product_id, "unit_id": i.unit_id, "quantity": i.quantity, "unit_price": i.unit_price, "discount": i.discount, "tax_rate": i.tax_rate} for i in q.items]
    note = f"من عرض السعر {q.number}" + (f" | {q.notes}" if q.notes else "")
    invoice_id = create_sales_invoice(q.customer_id, items, notes=note, discount=q.discount, location_id=location_id, invoice_date=invoice_date,
                                      branch_id=q.branch_id, cost_center_id=q.cost_center_id)
    with get_session() as s:
        row = s.get(SalesQuotation, q.id)
        row.state = "invoiced"; row.invoice_id = invoice_id; row.decided_at = datetime.datetime.now()
        s.commit()
    return invoice_id


def generate_quotation_pdf_file(quotation_id):
    """ملف PDF لعرض السعر (برأس الشركة): العميل وتاريخ العرض وصلاحيته، بنود بالأسعار والضريبة، الإجماليات، الشروط."""
    from .invoice_pdf import generate_invoices_pdf
    q = get_quotation(quotation_id)
    if not q:
        raise ValueError("العرض غير موجود")
    settings = get_company_settings()
    extra = []
    if q.valid_until:
        extra.append(("صالح حتى", q.valid_until.strftime("%Y-%m-%d")))
    entry = {"invoice": q, "qr": None, "party": q.customer, "party_label": "العميل", "doc_title": "عرض سعر", "number_label": "رقم العرض",
             "extra_info": extra, "terms": q.terms, "notes": q.notes}
    return generate_invoices_pdf([entry], settings, downloads_dir(), filename=f"{q.number}.pdf")


# ======================================================================
# جدول الأعمال: مواعيد ومهام بتواريخ وتنبيه قبل الموعد (مالوش أي أثر محاسبي).
# التنبيه بيظهر جوه البرنامج وهو شغّال (نافذة تنبيه + عدّاد على الجرس).
# ======================================================================
AGENDA_KINDS = {"task": "مهمة", "meeting": "اجتماع", "deadline": "موعد استحقاق / سداد", "reminder": "تذكير", "other": "أخرى"}
AGENDA_PRIORITIES = {"low": "منخفضة", "normal": "عادية", "high": "عالية"}
AGENDA_REPEATS = {"none": "بدون تكرار", "daily": "يوميًا", "weekly": "أسبوعيًا", "monthly": "شهريًا", "yearly": "سنويًا"}
AGENDA_REMINDER_OPTIONS = [(None, "بدون تنبيه"), (0, "عند الموعد"), (15, "قبل الموعد بـ 15 دقيقة"), (30, "قبل الموعد بنص ساعة"), (60, "قبل الموعد بساعة"),
                           (120, "قبل الموعد بساعتين"), (1440, "قبل الموعد بيوم"), (2880, "قبل الموعد بيومين"), (10080, "قبل الموعد بأسبوع")]
AGENDA_STATUS_LABELS = {"pending": "قادم", "done": "منجز", "cancelled": "ملغى", "overdue": "متأخر"}
AGENDA_ALL_DAY_HOUR = 9     # الموعد "طوال اليوم" بيتنبّه له الساعة 9 الصبح (ناقص مدة التنبيه)


def _agenda_event_time(start_at, all_day):
    if all_day:
        return datetime.datetime.combine(start_at.date(), datetime.time(AGENDA_ALL_DAY_HOUR, 0))
    return start_at


def _agenda_alert_time(start_at, all_day, lead_minutes):
    if lead_minutes is None:
        return None
    return _agenda_event_time(start_at, all_day) - datetime.timedelta(minutes=int(lead_minutes))


def _agenda_add_months(dt, n, anchor_day=None):
    import calendar
    m = dt.month - 1 + n
    y = dt.year + m // 12; m = m % 12 + 1
    return dt.replace(year=y, month=m, day=min(anchor_day or dt.day, calendar.monthrange(y, m)[1]))


def _agenda_step(dt, repeat, anchor_day=None):
    if repeat == "daily":
        return dt + datetime.timedelta(days=1)
    if repeat == "weekly":
        return dt + datetime.timedelta(days=7)
    if repeat == "monthly":
        return _agenda_add_months(dt, 1, anchor_day)
    if repeat == "yearly":
        return _agenda_add_months(dt, 12, anchor_day)
    return dt


def agenda_effective_status(it, now=None):
    """الحالة الفعلية: قادم / متأخر (فات موعده ولسه ما اتنجزش) / منجز / ملغى."""
    now = now or datetime.datetime.now()
    if it.status != "pending":
        return it.status
    if it.all_day:
        return "overdue" if it.start_at.date() < now.date() else "pending"
    return "overdue" if it.start_at < now else "pending"


def _agenda_validate(title, start_at, kind, repeat, priority, remind_before_minutes, assigned_to):
    title = (title or "").strip()
    if not title:
        raise ValueError("اكتب عنوان الموعد")
    if not isinstance(start_at, datetime.datetime):
        raise ValueError("حدد تاريخ الموعد")
    if kind not in AGENDA_KINDS:
        raise ValueError("نوع الموعد غير معروف")
    if repeat not in AGENDA_REPEATS:
        raise ValueError("نوع التكرار غير معروف")
    if priority not in AGENDA_PRIORITIES:
        raise ValueError("الأولوية غير معروفة")
    if remind_before_minutes is not None and int(remind_before_minutes) not in {m for m, _ in AGENDA_REMINDER_OPTIONS if m is not None}:
        raise ValueError("مدة التنبيه غير مدعومة")
    if assigned_to:
        with get_session() as s:
            if not s.query(User).filter(User.username == assigned_to, User.is_active.is_(True)).first():
                raise ValueError("المستخدم المكلَّف غير موجود")
    return title


def create_agenda_item(title, start_at, kind="task", description="", all_day=False, remind_before_minutes=60, repeat="none",
                       priority="normal", assigned_to=None):
    require_action("agenda", "create")
    title = _agenda_validate(title, start_at, kind, repeat, priority, remind_before_minutes, assigned_to)
    if all_day:
        start_at = datetime.datetime.combine(start_at.date(), datetime.time(0, 0))
    alert = _agenda_alert_time(start_at, all_day, remind_before_minutes)
    if _agenda_event_time(start_at, all_day) < datetime.datetime.now():
        alert = None        # موعد فات أصلًا وقت إضافته - مفيش داعي ينبّه
    with get_session() as s:
        it = AgendaItem(title=title, description=(description or "").strip(), kind=kind, start_at=start_at, all_day=bool(all_day),
                        remind_before_minutes=int(remind_before_minutes) if remind_before_minutes is not None else None,
                        next_alert_at=alert, repeat=repeat, anchor_day=start_at.day, priority=priority, status="pending", created_by=_current_username(), assigned_to=assigned_to or None)
        s.add(it); s.commit(); s.refresh(it)
        return it.id


def get_agenda_item(item_id):
    with get_session() as s:
        it = s.get(AgendaItem, int(item_id))
        if it:
            s.expunge(it)
        return it


def update_agenda_item(item_id, title, start_at, kind="task", description="", all_day=False, remind_before_minutes=60, repeat="none",
                       priority="normal", assigned_to=None):
    require_action("agenda", "edit")
    title = _agenda_validate(title, start_at, kind, repeat, priority, remind_before_minutes, assigned_to)
    if all_day:
        start_at = datetime.datetime.combine(start_at.date(), datetime.time(0, 0))
    with get_session() as s:
        it = s.get(AgendaItem, int(item_id))
        if not it:
            raise ValueError("الموعد غير موجود")
        changed_time = (it.start_at != start_at or it.all_day != bool(all_day) or it.remind_before_minutes != (int(remind_before_minutes) if remind_before_minutes is not None else None))
        it.title = title; it.description = (description or "").strip(); it.kind = kind; it.start_at = start_at; it.all_day = bool(all_day)
        it.remind_before_minutes = int(remind_before_minutes) if remind_before_minutes is not None else None
        it.repeat = repeat; it.priority = priority; it.assigned_to = assigned_to or None
        it.anchor_day = start_at.day
        if changed_time and it.status == "pending":
            alert = _agenda_alert_time(start_at, all_day, it.remind_before_minutes)
            it.next_alert_at = alert if (alert and _agenda_event_time(start_at, all_day) >= datetime.datetime.now()) else None
        s.commit()


def list_agenda_items(date_from=None, date_to=None, status=None, kind=None, text=None, scope="mine", limit=3000):
    """status: pending (قادم) | overdue | done | cancelled | open (قادم + متأخر). scope: mine (اللي أنشأتها أو متكلَّف بيها) | all (للأدمن بس)."""
    me = _current_username()
    is_admin = (current_user() or {}).get("role") == "admin"
    with get_session() as s:
        q = s.query(AgendaItem)
        if scope != "all" or not is_admin:
            q = q.filter((AgendaItem.created_by == me) | (AgendaItem.assigned_to == me))
        if date_from:
            q = q.filter(AgendaItem.start_at >= _dt_start(date_from))
        if date_to:
            q = q.filter(AgendaItem.start_at <= _dt_end(date_to))
        if kind:
            q = q.filter(AgendaItem.kind == kind)
        if text and text.strip():
            like = f"%{text.strip()}%"
            q = q.filter((AgendaItem.title.like(like)) | (AgendaItem.description.like(like)))
        rows = q.order_by(AgendaItem.start_at).limit(int(limit)).all()
        now = datetime.datetime.now()
        if status == "open":
            rows = [r for r in rows if r.status == "pending"]
        elif status in ("pending", "overdue"):
            rows = [r for r in rows if r.status == "pending" and agenda_effective_status(r, now) == status]
        elif status in ("done", "cancelled"):
            rows = [r for r in rows if r.status == status]
        s.expunge_all()
        return rows


def complete_agenda_item(item_id):
    """تم: الموعد العادي بيتقفل كمنجز. الموعد المتكرر بيتنقل للموعد التالي (ومعاه التنبيه)."""
    require_action("agenda", "edit")
    with get_session() as s:
        it = s.get(AgendaItem, int(item_id))
        if not it:
            raise ValueError("الموعد غير موجود")
        if it.status != "pending":
            raise ValueError("الموعد ده مش قيد الانتظار")
        now = datetime.datetime.now()
        it.done_count = (it.done_count or 0) + 1; it.done_at = now
        if it.repeat and it.repeat != "none":
            nxt = _agenda_step(it.start_at, it.repeat, it.anchor_day)
            while _agenda_event_time(nxt, it.all_day) <= now:
                nxt = _agenda_step(nxt, it.repeat, it.anchor_day)
            it.start_at = nxt
            it.next_alert_at = _agenda_alert_time(nxt, it.all_day, it.remind_before_minutes)
            s.commit()
            return "advanced"
        it.status = "done"; it.next_alert_at = None
        s.commit()
        return "done"


def reopen_agenda_item(item_id):
    require_action("agenda", "edit")
    with get_session() as s:
        it = s.get(AgendaItem, int(item_id))
        if not it:
            raise ValueError("الموعد غير موجود")
        it.status = "pending"; it.done_at = None
        alert = _agenda_alert_time(it.start_at, it.all_day, it.remind_before_minutes)
        it.next_alert_at = alert if (alert and _agenda_event_time(it.start_at, it.all_day) >= datetime.datetime.now()) else None
        s.commit()


def cancel_agenda_item(item_id):
    require_action("agenda", "edit")
    with get_session() as s:
        it = s.get(AgendaItem, int(item_id))
        if not it:
            raise ValueError("الموعد غير موجود")
        it.status = "cancelled"; it.next_alert_at = None
        s.commit()


def delete_agenda_item(item_id):
    require_action("agenda", "delete")
    with get_session() as s:
        it = s.get(AgendaItem, int(item_id))
        if not it:
            raise ValueError("الموعد غير موجود")
        s.delete(it); s.commit()


def snooze_agenda_item(item_id, minutes):
    """تأجيل التنبيه (مش الموعد نفسه): التنبيه يرجع يظهر بعد minutes دقيقة."""
    require_action("agenda", "edit")
    minutes = int(minutes)
    if minutes <= 0:
        raise ValueError("مدة التأجيل لازم تكون أكبر من صفر")
    with get_session() as s:
        it = s.get(AgendaItem, int(item_id))
        if not it:
            raise ValueError("الموعد غير موجود")
        if it.status != "pending":
            raise ValueError("الموعد ده مش قيد الانتظار")
        it.next_alert_at = datetime.datetime.now() + datetime.timedelta(minutes=minutes)
        s.commit()


def _agenda_targets_user(it, username):
    return (it.assigned_to == username) or (not it.assigned_to and it.created_by == username)


def due_agenda_alerts(username=None):
    """المواعيد اللي جه وقت تنبيهها ولسه ما اتنبّهش لها (للمستخدم المستهدف). مفيهاش require_action
    عشان الفاحص الخلفي ما يرميش أخطاء صلاحيات."""
    username = username or _current_username()
    now = datetime.datetime.now()
    with get_session() as s:
        rows = s.query(AgendaItem).filter(AgendaItem.status == "pending", AgendaItem.next_alert_at.isnot(None), AgendaItem.next_alert_at <= now).order_by(AgendaItem.start_at).all()
        rows = [r for r in rows if _agenda_targets_user(r, username)]
        s.expunge_all()
        return rows


def mark_agenda_alerted(item_ids):
    """بعد ما التنبيه يظهر بنصفّر وقته (متأجّلش ولا يتكرر لنفس الموعد)."""
    ids = [int(i) for i in item_ids]
    if not ids:
        return
    with get_session() as s:
        s.query(AgendaItem).filter(AgendaItem.id.in_(ids)).update({"next_alert_at": None}, synchronize_session=False)
        s.commit()


def agenda_summary(username=None):
    """أرقام الجرس: متأخر / النهاردة / خلال 7 أيام - لمواعيد المستخدم اللي لسه قيد الانتظار."""
    username = username or _current_username()
    now = datetime.datetime.now(); today = now.date(); week_end = today + datetime.timedelta(days=7)
    with get_session() as s:
        rows = [r for r in s.query(AgendaItem).filter(AgendaItem.status == "pending").all() if _agenda_targets_user(r, username)]
    overdue = today_n = week_n = 0
    for r in rows:
        eff = agenda_effective_status(r, now)
        if eff == "overdue":
            overdue += 1
        elif r.start_at.date() == today:
            today_n += 1
        elif r.start_at.date() <= week_end:
            week_n += 1
    return {"overdue": overdue, "today": today_n, "week": week_n, "attention": overdue + today_n}


def agenda_upcoming(username=None, days=7, limit=40):
    """مواعيد المستخدم القريبة للّوحة: المتأخرة + لحد days يوم قدّام (للجرس)."""
    username = username or _current_username()
    now = datetime.datetime.now(); horizon = datetime.datetime.combine(now.date() + datetime.timedelta(days=days), datetime.time(23, 59, 59))
    with get_session() as s:
        rows = [r for r in s.query(AgendaItem).filter(AgendaItem.status == "pending", AgendaItem.start_at <= horizon).order_by(AgendaItem.start_at).all() if _agenda_targets_user(r, username)]
        s.expunge_all()
        return rows[:limit]


# ---- إشعار المستمعين (الجرس في الشريط العلوي) بأي تغيير في جدول الأعمال ----
_AGENDA_LISTENERS = []


def add_agenda_listener(fn):
    if fn not in _AGENDA_LISTENERS:
        _AGENDA_LISTENERS.append(fn)


def remove_agenda_listener(fn):
    if fn in _AGENDA_LISTENERS:
        _AGENDA_LISTENERS.remove(fn)


def _notify_agenda_changed(fn):
    import functools

    @functools.wraps(fn)
    def inner(*args, **kwargs):
        result = fn(*args, **kwargs)
        for cb in list(_AGENDA_LISTENERS):
            try:
                cb()
            except Exception:
                pass
        return result
    return inner


for _name in ("create_agenda_item", "update_agenda_item", "complete_agenda_item", "reopen_agenda_item", "cancel_agenda_item", "delete_agenda_item", "snooze_agenda_item"):
    globals()[_name] = _notify_agenda_changed(globals()[_name])


# ======================================================================
# الشات بين المستخدمين: محادثات فردية ومجموعات، رسائل نصية ومرفقات (حد 25MB وبدون ملفات
# تنفيذية)، عدّاد غير مقروء، وإشعار بالرسائل الجديدة. كل حاجة محفوظة في قاعدة البيانات
# فالمستخدمين على أجهزة مختلفة (نفس القاعدة) بيشوفوا نفس الرسائل.
# ======================================================================
CHAT_MAX_FILE_MB = 25
CHAT_MAX_BODY = 4000
CHAT_BLOCKED_EXT = {".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".vbs", ".vbe", ".js", ".jse", ".ps1", ".jar", ".lnk", ".reg", ".dll", ".sys", ".hta", ".cpl", ".msc"}
CHAT_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


def _chat_me():
    me = _current_username()
    if not me:
        raise PermissionError("لازم تسجّل دخول الأول")
    return me


def _chat_names(s):
    return {u.username: (u.full_name or u.username) for u in s.query(User).all()}


def _chat_member(s, conv_id, username):
    m = s.query(ChatMember).filter(ChatMember.conversation_id == int(conv_id), ChatMember.username == username, ChatMember.left.is_(False)).first()
    if not m:
        raise PermissionError("أنت مش عضو في المحادثة دي")
    return m


def chat_users():
    """المستخدمين النشطين اللي ينفع تكلمهم (من غير نفسك)."""
    me = _chat_me()
    with get_session() as s:
        return [{"username": u.username, "full_name": u.full_name or u.username} for u in s.query(User).filter(User.is_active.is_(True), User.username != me).order_by(User.full_name).all()]


def _chat_add_system(s, conv, text):
    msg = ChatMessage(conversation_id=conv.id, sender=_current_username() or "", body=text, is_system=True)
    s.add(msg); conv.last_message_at = datetime.datetime.now()
    s.flush()
    return msg


def _chat_max_id(s, conv_id):
    return s.query(func.coalesce(func.max(ChatMessage.id), 0)).filter(ChatMessage.conversation_id == int(conv_id)).scalar() or 0


def chat_get_or_create_direct(other_username):
    require_action("chat", "create")
    me = _chat_me()
    other_username = (other_username or "").strip()
    if not other_username or other_username == me:
        raise ValueError("اختر مستخدم تاني")
    key = "|".join(sorted([me, other_username]))
    with get_session() as s:
        if not s.query(User).filter(User.username == other_username, User.is_active.is_(True)).first():
            raise ValueError("المستخدم غير موجود أو غير نشط")
        conv = s.query(ChatConversation).filter(ChatConversation.direct_key == key).first()
        if not conv:
            conv = ChatConversation(kind="direct", direct_key=key, created_by=me)
            s.add(conv); s.flush()
            for u in (me, other_username):
                s.add(ChatMember(conversation_id=conv.id, username=u))
            s.commit()
        else:
            for u in (me, other_username):          # لو حد كان "سايب" المحادثة (مش في الفردي) نرجّعه
                m = s.query(ChatMember).filter(ChatMember.conversation_id == conv.id, ChatMember.username == u).first()
                if m and m.left:
                    m.left = False
            s.commit()
        return conv.id


def chat_create_group(title, usernames):
    require_action("chat", "create")
    me = _chat_me()
    title = (title or "").strip()
    if not title:
        raise ValueError("اكتب اسم المجموعة")
    if len(title) > 150:
        raise ValueError("اسم المجموعة طويل")
    others = [u for u in dict.fromkeys(usernames or []) if u and u != me]
    if not others:
        raise ValueError("اختر عضو واحد على الأقل")
    with get_session() as s:
        valid = {u.username: u.full_name for u in s.query(User).filter(User.is_active.is_(True), User.username.in_(others)).all()}
        if len(valid) != len(others):
            raise ValueError("فيه مستخدم غير موجود أو غير نشط")
        conv = ChatConversation(kind="group", title=title, created_by=me)
        s.add(conv); s.flush()
        for u in [me] + others:
            s.add(ChatMember(conversation_id=conv.id, username=u))
        names = _chat_names(s)
        _chat_add_system(s, conv, f"{names.get(me, me)} أنشأ المجموعة وضاف: " + "، ".join(names.get(u, u) for u in others))
        s.commit()
        return conv.id


def chat_group_info(conv_id):
    """بيانات المجموعة للتعديل: العنوان والأعضاء النشطين والمنشئ."""
    me = _chat_me()
    with get_session() as s:
        _chat_member(s, conv_id, me)
        conv = s.get(ChatConversation, int(conv_id))
        names = _chat_names(s)
        mem = [m.username for m in conv.members if not m.left]
        return {"id": conv.id, "kind": conv.kind, "title": conv.title, "created_by": conv.created_by,
                "members": [{"username": u, "full_name": names.get(u, u)} for u in mem],
                "can_edit": conv.kind == "group" and (conv.created_by == me or (current_user() or {}).get("role") == "admin")}


def chat_update_group(conv_id, title, usernames):
    """تعديل اسم المجموعة وأعضائها (للمنشئ أو الأدمن)."""
    require_action("chat", "create")
    me = _chat_me()
    title = (title or "").strip()
    if not title:
        raise ValueError("اكتب اسم المجموعة")
    wanted = set(u for u in (usernames or []) if u)
    with get_session() as s:
        conv = s.get(ChatConversation, int(conv_id))
        if not conv or conv.kind != "group":
            raise ValueError("المجموعة غير موجودة")
        _chat_member(s, conv.id, me)
        if conv.created_by != me and (current_user() or {}).get("role") != "admin":
            raise PermissionError("تعديل المجموعة للي أنشأها أو للأدمن")
        wanted.add(conv.created_by)
        valid = {u.username for u in s.query(User).filter(User.is_active.is_(True), User.username.in_(wanted)).all()}
        if wanted - valid:
            raise ValueError("فيه مستخدم غير موجود أو غير نشط")
        names = _chat_names(s)
        current = {m.username: m for m in conv.members}
        added = [u for u in wanted if u not in current or current[u].left]
        removed = [u for u, m in current.items() if not m.left and u not in wanted]
        mx = _chat_max_id(s, conv.id)
        for u in added:
            if u in current:
                current[u].left = False; current[u].joined_message_id = mx; current[u].last_read_message_id = mx
            else:
                s.add(ChatMember(conversation_id=conv.id, username=u, joined_message_id=mx, last_read_message_id=mx))
        for u in removed:
            current[u].left = True
        if title != conv.title:
            _chat_add_system(s, conv, f"{names.get(me, me)} غيّر اسم المجموعة إلى «{title}»"); conv.title = title
        if added:
            _chat_add_system(s, conv, f"{names.get(me, me)} ضاف: " + "، ".join(names.get(u, u) for u in added))
        if removed:
            _chat_add_system(s, conv, f"{names.get(me, me)} شال: " + "، ".join(names.get(u, u) for u in removed))
        s.commit()


def chat_leave_group(conv_id):
    me = _chat_me()
    with get_session() as s:
        conv = s.get(ChatConversation, int(conv_id))
        if not conv or conv.kind != "group":
            raise ValueError("المجموعة غير موجودة")
        m = _chat_member(s, conv.id, me)
        names = _chat_names(s)
        _chat_add_system(s, conv, f"{names.get(me, me)} غادر المجموعة")
        m.left = True
        s.commit()


def _chat_unread(s, conv_id, member):
    return s.query(func.count(ChatMessage.id)).filter(
        ChatMessage.conversation_id == int(conv_id), ChatMessage.id > max(member.last_read_message_id or 0, member.joined_message_id or 0),
        ChatMessage.sender != member.username, ChatMessage.is_system.is_(False), ChatMessage.deleted.is_(False)).scalar() or 0


def _chat_preview(m, names):
    if m is None:
        return ""
    if m.deleted:
        return "تم حذف الرسالة"
    if m.is_system:
        return m.body
    pre = ""
    if m.attachment_name:
        pre = ("🖼 " if m.attachment_kind == "image" else "📎 ") + (m.attachment_name if not m.body else "")
    return (pre + (m.body or "")).strip().replace("\n", " ")[:80]


def chat_list_conversations():
    """محادثاتي مرتبة بآخر رسالة: العنوان (اسم الطرف التاني في الفردي)، آخر رسالة، غير المقروء."""
    require_action("chat", "view")
    me = _chat_me()
    with get_session() as s:
        names = _chat_names(s)
        out = []
        for m in s.query(ChatMember).filter(ChatMember.username == me, ChatMember.left.is_(False)).all():
            conv = m.conversation
            if conv.kind == "direct":
                other = next((x.username for x in conv.members if x.username != me), me)
                title = names.get(other, other); other_user = other
            else:
                title = conv.title or "مجموعة"; other_user = None
            vis = max(m.joined_message_id or 0, 0)
            last = s.query(ChatMessage).filter(ChatMessage.conversation_id == conv.id, ChatMessage.id > vis).order_by(ChatMessage.id.desc()).first()
            out.append({"id": conv.id, "kind": conv.kind, "title": title, "other": other_user, "members": len([x for x in conv.members if not x.left]),
                        "last_text": _chat_preview(last, names), "last_sender": names.get(last.sender, last.sender) if last and not last.is_system else "",
                        "last_mine": bool(last and last.sender == me), "last_at": last.created_at if last else conv.created_at, "unread": _chat_unread(s, conv.id, m)})
        out.sort(key=lambda c: c["last_at"], reverse=True)
        return out


def chat_messages(conv_id, limit=300):
    """آخر limit رسالة في المحادثة (من وقت انضمامي) بالترتيب الزمني، مع علامة "اتقرت" في الفردي."""
    require_action("chat", "view")
    me = _chat_me()
    with get_session() as s:
        mem = _chat_member(s, conv_id, me)
        conv = s.get(ChatConversation, int(conv_id))
        names = _chat_names(s)
        others = [x for x in conv.members if x.username != me and not x.left]
        rows = s.query(ChatMessage).filter(ChatMessage.conversation_id == int(conv_id), ChatMessage.id > (mem.joined_message_id or 0)).order_by(ChatMessage.id.desc()).limit(int(limit)).all()
        out = []
        for m in reversed(rows):
            out.append({"id": m.id, "sender": m.sender, "sender_name": names.get(m.sender, m.sender), "mine": m.sender == me, "body": "" if m.deleted else (m.body or ""),
                        "created_at": m.created_at, "system": bool(m.is_system), "deleted": bool(m.deleted),
                        "attachment_name": "" if m.deleted else (m.attachment_name or ""), "attachment_size": m.attachment_size or 0,
                        "attachment_kind": m.attachment_kind or "", "has_attachment": bool(m.attachment_name) and not m.deleted,
                        "seen": bool(others) and all((x.last_read_message_id or 0) >= m.id for x in others)})
        return out


def _chat_safe_name(name):
    import re
    base = os.path.basename(name or "file")
    base = re.sub(r"[^\w\-. \u0600-\u06FF()]", "_", base).strip() or "file"
    return base[:120]


def chat_send(conv_id, body="", attachment_path=None):
    """إرسال رسالة نصية و/أو مرفق (ملف واحد). المرفق بيتنسخ لمجلد المرفقات وبيتفحص حجمه ونوعه."""
    require_action("chat", "create")
    me = _chat_me()
    body = (body or "").strip()
    if not body and not attachment_path:
        raise ValueError("اكتب رسالة أو أرفق ملف")
    if len(body) > CHAT_MAX_BODY:
        raise ValueError(f"الرسالة طويلة (الحد {CHAT_MAX_BODY} حرف)")
    dest = name = None; size = 0; kind = ""
    if attachment_path:
        import shutil, uuid
        if not os.path.isfile(attachment_path):
            raise ValueError("الملف المرفق مش موجود")
        ext = os.path.splitext(attachment_path)[1].lower()
        if ext in CHAT_BLOCKED_EXT:
            raise ValueError(f"نوع الملف ({ext}) مش مسموح إرساله لدواعي الأمان")
        size = os.path.getsize(attachment_path)
        if size <= 0:
            raise ValueError("الملف فاضي")
        if size > CHAT_MAX_FILE_MB * 1024 * 1024:
            raise ValueError(f"حجم الملف أكبر من {CHAT_MAX_FILE_MB} ميجا")
        name = _chat_safe_name(attachment_path); kind = "image" if ext in CHAT_IMAGE_EXT else "file"
    with get_session() as s:
        _chat_member(s, conv_id, me)
        if attachment_path:
            base_dir = os.path.normpath(os.path.join(APP_DIR, "attachments", "chat", str(int(conv_id))))
            os.makedirs(base_dir, exist_ok=True)
            dest = os.path.join(base_dir, f"{datetime.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}_{name}")
            shutil.copy2(attachment_path, dest)
        msg = ChatMessage(conversation_id=int(conv_id), sender=me, body=body, attachment_path=dest or "", attachment_name=name or "", attachment_size=size, attachment_kind=kind)
        s.add(msg); s.flush()
        conv = s.get(ChatConversation, int(conv_id)); conv.last_message_at = msg.created_at or datetime.datetime.now()
        mem = _chat_member(s, conv_id, me); mem.last_read_message_id = msg.id
        s.commit()
        return msg.id


def chat_mark_read(conv_id):
    me = _chat_me()
    with get_session() as s:
        mem = _chat_member(s, conv_id, me)
        mx = _chat_max_id(s, conv_id)
        if (mem.last_read_message_id or 0) < mx:
            mem.last_read_message_id = mx
            s.commit()
            return True
        return False


def chat_delete_message(message_id):
    """حذف رسالتك (بيتحوّل لـ"تم حذف الرسالة" عند الكل ويتمسح مرفقها)."""
    require_action("chat", "delete")
    me = _chat_me()
    with get_session() as s:
        m = s.get(ChatMessage, int(message_id))
        if not m:
            raise ValueError("الرسالة غير موجودة")
        if m.sender != me:
            raise PermissionError("تقدر تحذف رسايلك بس")
        if m.is_system:
            raise ValueError("رسائل النظام ما بتتحذفش")
        path = m.attachment_path
        m.deleted = True; m.body = ""; m.attachment_path = ""; m.attachment_name = ""; m.attachment_size = 0
        s.commit()
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except Exception:
            pass


def chat_attachment_path(message_id):
    """مسار مرفق رسالة (لو انت عضو في المحادثة بتاعتها)."""
    require_action("chat", "view")
    me = _chat_me()
    with get_session() as s:
        m = s.get(ChatMessage, int(message_id))
        if not m or m.deleted or not m.attachment_path:
            raise ValueError("المرفق غير موجود")
        mem = _chat_member(s, m.conversation_id, me)
        if m.id <= (mem.joined_message_id or 0):
            raise PermissionError("المرفق ده كان قبل انضمامك للمجموعة")
        if not os.path.isfile(m.attachment_path):
            raise ValueError("ملف المرفق اتمسح من الجهاز")
        return m.attachment_path


def chat_unread_total(username=None):
    username = username or _current_username()
    total = 0
    with get_session() as s:
        for m in s.query(ChatMember).filter(ChatMember.username == username, ChatMember.left.is_(False)).all():
            total += _chat_unread(s, m.conversation_id, m)
    return total


def chat_max_message_id(username=None):
    """أكبر رقم رسالة في محادثاتي (نقطة البداية للفاحص عشان ما ينبّهش على رسائل قديمة)."""
    username = username or _current_username()
    with get_session() as s:
        ids = [m.conversation_id for m in s.query(ChatMember).filter(ChatMember.username == username, ChatMember.left.is_(False)).all()]
        if not ids:
            return 0
        return s.query(func.coalesce(func.max(ChatMessage.id), 0)).filter(ChatMessage.conversation_id.in_(ids)).scalar() or 0


def chat_new_messages_since(since_id, username=None):
    """الرسائل الجديدة (من غيري) في محادثاتي بعد رقم since_id - للإشعارات."""
    username = username or _current_username()
    out = []
    with get_session() as s:
        names = _chat_names(s)
        for m in s.query(ChatMember).filter(ChatMember.username == username, ChatMember.left.is_(False)).all():
            conv = m.conversation
            rows = s.query(ChatMessage).filter(ChatMessage.conversation_id == conv.id, ChatMessage.id > max(since_id, m.joined_message_id or 0),
                                                ChatMessage.sender != username, ChatMessage.is_system.is_(False), ChatMessage.deleted.is_(False)).order_by(ChatMessage.id).all()
            for r in rows:
                out.append({"id": r.id, "conversation_id": conv.id, "sender": r.sender, "sender_name": names.get(r.sender, r.sender),
                            "title": names.get(r.sender, r.sender) if conv.kind == "direct" else (conv.title or "مجموعة"),
                            "group": conv.kind == "group", "text": _chat_preview(r, names)})
    out.sort(key=lambda x: x["id"])
    return out


# ---- مستمعين: عدّاد الشاشة العلوي + تحديث شاشة الشات المفتوحة ----
_CHAT_LISTENERS = []
_CHAT_VIEW_REFRESH = {"fn": None}


def add_chat_listener(fn):
    if fn not in _CHAT_LISTENERS:
        _CHAT_LISTENERS.append(fn)


def remove_chat_listener(fn):
    if fn in _CHAT_LISTENERS:
        _CHAT_LISTENERS.remove(fn)


def set_chat_view_refresh(fn):
    """شاشة الشات المفتوحة بتسجّل دالة تحديثها هنا (آخر شاشة اتفتحت هي الفعّالة)."""
    _CHAT_VIEW_REFRESH["fn"] = fn


def chat_refresh_view():
    fn = _CHAT_VIEW_REFRESH["fn"]
    if fn:
        try:
            fn()
        except Exception:
            pass


def _chat_notify(fn):
    import functools

    @functools.wraps(fn)
    def inner(*args, **kwargs):
        result = fn(*args, **kwargs)
        for cb in list(_CHAT_LISTENERS):
            try:
                cb()
            except Exception:
                pass
        return result
    return inner


for _cn in ("chat_send", "chat_mark_read", "chat_delete_message", "chat_leave_group", "chat_update_group", "chat_create_group", "chat_get_or_create_direct"):
    globals()[_cn] = _chat_notify(globals()[_cn])


# ======================================================================
# تجديد الرخص والمستندات (الموارد البشرية): إقامات، جوازات، رخص، عقود إيجار، تأمينات، أي مستند
# بتاريخ انتهاء. بنتابع المتبقي، وبنتنبّه على مراحل قبل الانتهاء، وبنسجّل كل تجديد.
# مالوش أي أثر محاسبي (التكلفة معلومة بس).
# ======================================================================
DOC_HOLDER_KINDS = {"employee": "موظف", "company": "الشركة", "other": "أخرى (سيارة / فرع / عقار...)"}
DOC_REMIND_CHOICES = [180, 120, 90, 60, 45, 30, 15, 7, 3, 1, 0]
DOC_STATUS_LABELS = {"expired": "منتهي", "expiring": "قارب على الانتهاء", "valid": "ساري", "archived": "مؤرشف"}
_DEFAULT_DOCUMENT_TYPES = [
    ("إقامة موظف", "employee", "90,60,30,15,7"), ("جواز سفر", "employee", "180,90,60,30"), ("رخصة قيادة", "employee", "60,30,7"),
    ("شهادة صحية", "employee", "30,15,7"), ("تأمين طبي", "employee", "60,30,15"), ("سجل تجاري", "company", "90,60,30,7"),
    ("رخصة نشاط / رخصة بلدية", "company", "60,30,15,7"), ("عقد إيجار", "company", "90,60,30,15"), ("تأمين (مركبات / ممتلكات)", "company", "60,30,15"),
    ("استمارة / ترخيص مركبة", "other", "60,30,15,7"), ("فحص دوري", "other", "30,15,7"), ("اشتراك / ترخيص برنامج", "company", "30,15,7"),
    ("شهادة الزكاة والضريبة", "company", "60,30,7"), ("أخرى", "other", "30,7"),
]


def _parse_remind_days(text):
    out = []
    for p in str(text or "").replace("،", ",").split(","):
        p = p.strip()
        if p.isdigit() and int(p) in DOC_REMIND_CHOICES and int(p) not in out:
            out.append(int(p))
    return sorted(out, reverse=True)


def _doc_days_left(expiry, today=None):
    today = today or datetime.date.today()
    return (expiry.date() - today).days


def _doc_alert_tier(days_left, tiers):
    """المرحلة الحالية للتنبيه: -1 لو منتهي، وإلا أضيق مرحلة وصلنا لها (أقل رقم >= الأيام المتبقية)، أو None."""
    if days_left < 0:
        return -1
    crossed = [t for t in tiers if days_left <= t]
    return min(crossed) if crossed else None


def _doc_status(archived, days_left, tiers):
    if archived:
        return "archived"
    if days_left < 0:
        return "expired"
    if tiers and days_left <= max(tiers):
        return "expiring"
    return "valid"


def list_document_types(active_only=True):
    """أنواع المستندات (بيتعمل لها بذر افتراضي أول مرة)."""
    with get_session() as s:
        if not s.query(DocumentType).count():
            for i, (n, hk, rd) in enumerate(_DEFAULT_DOCUMENT_TYPES):
                s.add(DocumentType(name=n, holder_kind=hk, remind_days=rd, sort_order=i))
            s.commit()
        q = s.query(DocumentType)
        if active_only:
            q = q.filter(DocumentType.is_active.is_(True))
        rows = q.order_by(DocumentType.sort_order, DocumentType.id).all()
        s.expunge_all()
        return rows


def _check_doc_type_fields(name, holder_kind, remind_days):
    name = (name or "").strip()
    if not name:
        raise ValueError("اكتب اسم نوع المستند")
    if holder_kind not in DOC_HOLDER_KINDS:
        raise ValueError("نوع صاحب المستند غير معروف")
    days = remind_days if isinstance(remind_days, (list, tuple)) else _parse_remind_days(remind_days)
    days = sorted({int(d) for d in days if int(d) in DOC_REMIND_CHOICES}, reverse=True)
    return name, ",".join(str(d) for d in days)


def create_document_type(name, holder_kind="other", remind_days=(30, 7)):
    require_action("hr_documents", "create")
    list_document_types()
    name, days = _check_doc_type_fields(name, holder_kind, remind_days)
    with get_session() as s:
        if s.query(DocumentType).filter(DocumentType.name == name).first():
            raise ValueError("النوع ده موجود بالفعل")
        t = DocumentType(name=name, holder_kind=holder_kind, remind_days=days, sort_order=(s.query(func.coalesce(func.max(DocumentType.sort_order), 0)).scalar() or 0) + 1)
        s.add(t); s.commit(); s.refresh(t)
        return t.id


def update_document_type(type_id, name, holder_kind, remind_days, is_active=True):
    require_action("hr_documents", "edit")
    name, days = _check_doc_type_fields(name, holder_kind, remind_days)
    with get_session() as s:
        t = s.get(DocumentType, int(type_id))
        if not t:
            raise ValueError("النوع غير موجود")
        if s.query(DocumentType).filter(DocumentType.name == name, DocumentType.id != t.id).first():
            raise ValueError("فيه نوع تاني بنفس الاسم")
        t.name = name; t.holder_kind = holder_kind; t.remind_days = days; t.is_active = bool(is_active)
        s.commit()


def _doc_to_dict(d, today=None):
    tiers = _parse_remind_days(d.remind_days)
    left = _doc_days_left(d.expiry_date, today)
    holder = d.employee.name if d.holder_kind == "employee" and d.employee else (d.holder_name or ("الشركة" if d.holder_kind == "company" else "-"))
    return {"id": d.id, "type_id": d.type_id, "type_name": d.doc_type.name if d.doc_type else "-", "title": d.title, "doc_number": d.doc_number or "",
            "holder_kind": d.holder_kind, "employee_id": d.employee_id, "holder": holder, "holder_name": d.holder_name or "", "issuer": d.issuer or "",
            "issue_date": d.issue_date, "expiry_date": d.expiry_date, "days_left": left, "remind_days": tiers, "cost": d.cost or 0.0, "notes": d.notes or "",
            "branch_id": d.branch_id, "archived": bool(d.archived), "status": _doc_status(d.archived, left, tiers), "has_attachment": bool(d.attachment_path),
            "attachment_path": d.attachment_path or "", "renewals_count": len(d.renewals)}


def _doc_load_options():
    return (joinedload(TrackedDocument.doc_type), joinedload(TrackedDocument.employee), joinedload(TrackedDocument.renewals))


def _doc_save_attachment(doc_id, source_path):
    import shutil, uuid
    if not os.path.isfile(source_path):
        raise ValueError("ملف المرفق مش موجود")
    ext = os.path.splitext(source_path)[1].lower()
    if ext in CHAT_BLOCKED_EXT:
        raise ValueError(f"نوع الملف ({ext}) مش مسموح")
    if os.path.getsize(source_path) > 25 * 1024 * 1024:
        raise ValueError("حجم الملف أكبر من 25 ميجا")
    base_dir = os.path.normpath(os.path.join(APP_DIR, "attachments", "hr_documents", str(int(doc_id))))
    os.makedirs(base_dir, exist_ok=True)
    dest = os.path.join(base_dir, f"{datetime.datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}_{_chat_safe_name(source_path)}")
    shutil.copy2(source_path, dest)
    return dest


def _doc_validate(type_id, title, expiry_date, holder_kind, employee_id, issue_date, remind_days, cost, s):
    t = s.get(DocumentType, int(type_id)) if type_id else None
    if not t:
        raise ValueError("اختر نوع المستند")
    if holder_kind not in DOC_HOLDER_KINDS:
        raise ValueError("اختر صاحب المستند")
    emp = None
    if holder_kind == "employee":
        emp = s.get(Employee, int(employee_id)) if employee_id else None
        if not emp:
            raise ValueError("اختر الموظف صاحب المستند")
    if not isinstance(expiry_date, datetime.datetime):
        raise ValueError("حدد تاريخ انتهاء المستند")
    if issue_date and issue_date > expiry_date:
        raise ValueError("تاريخ الإصدار لا يمكن أن يكون بعد تاريخ الانتهاء")
    if float(cost or 0) < 0:
        raise ValueError("التكلفة لا يمكن أن تكون سالبة")
    title = (title or "").strip() or (f"{t.name} - {emp.name}" if emp else t.name)
    tiers = remind_days if remind_days is not None else _parse_remind_days(t.remind_days)
    tiers = sorted({int(x) for x in tiers if int(x) in DOC_REMIND_CHOICES}, reverse=True)
    return t, emp, title, ",".join(str(x) for x in tiers)


def create_tracked_document(type_id, expiry_date, title="", holder_kind="company", employee_id=None, holder_name="", doc_number="", issuer="",
                            issue_date=None, remind_days=None, cost=0.0, notes="", branch_id=None, attachment_path=None):
    """إضافة مستند للمتابعة. remind_days: قايمة أيام التنبيه (None = الافتراضي بتاع النوع)."""
    require_action("hr_documents", "create")
    list_document_types()
    with get_session() as s:
        t, emp, title, days = _doc_validate(type_id, title, expiry_date, holder_kind, employee_id, issue_date, remind_days, cost, s)
        d = TrackedDocument(type_id=t.id, title=title, doc_number=(doc_number or "").strip(), holder_kind=holder_kind, employee_id=emp.id if emp else None,
                            holder_name=(holder_name or "").strip() if holder_kind != "employee" else "", issuer=(issuer or "").strip(), issue_date=issue_date,
                            expiry_date=expiry_date, remind_days=days, cost=float(cost or 0), notes=(notes or "").strip(), branch_id=branch_id or (emp.branch_id if emp else None),
                            created_by=_current_username())
        s.add(d); s.flush()
        if attachment_path:
            d.attachment_path = _doc_save_attachment(d.id, attachment_path)
        s.commit()
        return d.id


def update_tracked_document(doc_id, type_id, expiry_date, title="", holder_kind="company", employee_id=None, holder_name="", doc_number="", issuer="",
                            issue_date=None, remind_days=None, cost=0.0, notes="", branch_id=None, attachment_path=None):
    require_action("hr_documents", "edit")
    with get_session() as s:
        d = s.get(TrackedDocument, int(doc_id))
        if not d:
            raise ValueError("المستند غير موجود")
        t, emp, title, days = _doc_validate(type_id, title, expiry_date, holder_kind, employee_id, issue_date, remind_days, cost, s)
        expiry_changed = d.expiry_date != expiry_date
        d.type_id = t.id; d.title = title; d.doc_number = (doc_number or "").strip(); d.holder_kind = holder_kind; d.employee_id = emp.id if emp else None
        d.holder_name = (holder_name or "").strip() if holder_kind != "employee" else ""; d.issuer = (issuer or "").strip(); d.issue_date = issue_date
        d.expiry_date = expiry_date; d.remind_days = days; d.cost = float(cost or 0); d.notes = (notes or "").strip(); d.branch_id = branch_id or d.branch_id
        if attachment_path:
            d.attachment_path = _doc_save_attachment(d.id, attachment_path)
        if expiry_changed:       # تاريخ جديد = مراحل التنبيه تبدأ من الأول
            s.query(DocumentAlert).filter(DocumentAlert.document_id == d.id).delete(synchronize_session=False)
        s.commit()


def get_tracked_document(doc_id):
    with get_session() as s:
        d = s.query(TrackedDocument).options(*_doc_load_options()).filter(TrackedDocument.id == int(doc_id)).first()
        return _doc_to_dict(d) if d else None


def list_tracked_documents(status=None, type_id=None, employee_id=None, text=None, include_archived=False, limit=3000):
    """status: expired | expiring | valid | archived | attention (منتهي + قارب). بيرجّع dicts مرتبة بالأقرب انتهاءً."""
    with get_session() as s:
        q = s.query(TrackedDocument).options(*_doc_load_options())
        if type_id:
            q = q.filter(TrackedDocument.type_id == int(type_id))
        if employee_id:
            q = q.filter(TrackedDocument.employee_id == int(employee_id))
        if user_branch_ids():
            q = q.filter((TrackedDocument.branch_id.is_(None)) | (TrackedDocument.branch_id.in_(user_branch_ids())))
        rows = [_doc_to_dict(d) for d in q.order_by(TrackedDocument.expiry_date).limit(int(limit)).all()]
    if text and text.strip():
        t = text.strip().lower()
        rows = [r for r in rows if t in (r["title"] + " " + r["doc_number"] + " " + r["holder"] + " " + r["type_name"] + " " + r["issuer"]).lower()]
    if status == "attention":
        rows = [r for r in rows if r["status"] in ("expired", "expiring")]
    elif status == "archived":
        rows = [r for r in rows if r["archived"]]
    elif status:
        rows = [r for r in rows if r["status"] == status]
    elif not include_archived:
        rows = [r for r in rows if not r["archived"]]
    return rows


def renew_tracked_document(doc_id, new_expiry, renewal_date=None, new_doc_number=None, cost=0.0, notes="", attachment_path=None):
    """تجديد مستند: بيسجّل التجديد في السجل ويحدّث تاريخ الانتهاء (والرقم والمرفق لو اتغيروا)
    وبيبدأ مراحل التنبيه من الأول للتاريخ الجديد."""
    require_action("hr_documents", "edit")
    if not isinstance(new_expiry, datetime.datetime):
        raise ValueError("حدد تاريخ الانتهاء الجديد")
    if float(cost or 0) < 0:
        raise ValueError("التكلفة لا يمكن أن تكون سالبة")
    with get_session() as s:
        d = s.get(TrackedDocument, int(doc_id))
        if not d:
            raise ValueError("المستند غير موجود")
        if new_expiry <= d.expiry_date:
            raise ValueError(f"تاريخ الانتهاء الجديد لازم يكون بعد التاريخ الحالي ({d.expiry_date:%Y-%m-%d})")
        renewed = renewal_date or datetime.datetime.now()
        att = _doc_save_attachment(d.id, attachment_path) if attachment_path else ""
        s.add(DocumentRenewal(document_id=d.id, renewed_at=renewed, old_expiry=d.expiry_date, new_expiry=new_expiry, doc_number=(new_doc_number or "").strip(),
                              cost=float(cost or 0), notes=(notes or "").strip(), attachment_path=att, created_by=_current_username()))
        d.expiry_date = new_expiry; d.issue_date = renewed
        if (new_doc_number or "").strip():
            d.doc_number = new_doc_number.strip()
        if float(cost or 0) > 0:
            d.cost = float(cost)
        if att:
            d.attachment_path = att
        d.archived = False
        s.query(DocumentAlert).filter(DocumentAlert.document_id == d.id).delete(synchronize_session=False)
        s.commit()


def list_document_renewals(doc_id):
    with get_session() as s:
        rows = s.query(DocumentRenewal).filter(DocumentRenewal.document_id == int(doc_id)).order_by(DocumentRenewal.id.desc()).all()
        s.expunge_all()
        return rows


def set_document_archived(doc_id, archived=True):
    require_action("hr_documents", "edit")
    with get_session() as s:
        d = s.get(TrackedDocument, int(doc_id))
        if not d:
            raise ValueError("المستند غير موجود")
        d.archived = bool(archived)
        s.commit()


def delete_tracked_document(doc_id):
    require_action("hr_documents", "delete")
    with get_session() as s:
        d = s.get(TrackedDocument, int(doc_id))
        if not d:
            raise ValueError("المستند غير موجود")
        s.query(DocumentAlert).filter(DocumentAlert.document_id == d.id).delete(synchronize_session=False)
        s.delete(d); s.commit()


def document_attachment_path(doc_id, renewal_id=None):
    with get_session() as s:
        if renewal_id:
            r = s.get(DocumentRenewal, int(renewal_id)); path = r.attachment_path if r else ""
        else:
            d = s.get(TrackedDocument, int(doc_id)); path = d.attachment_path if d else ""
    if not path or not os.path.isfile(path):
        raise ValueError("مفيش مرفق لل مستند ده (أو الملف اتمسح من الجهاز)")
    return path


def documents_summary():
    """أرقام الجرس والكروت: منتهي / قارب على الانتهاء / ساري."""
    rows = list_tracked_documents()
    out = {"expired": 0, "expiring": 0, "valid": 0, "total": len(rows), "within30": 0, "within90": 0}
    for r in rows:
        out[r["status"]] += 1
        if 0 <= r["days_left"] <= 30:
            out["within30"] += 1
        if 0 <= r["days_left"] <= 90:
            out["within90"] += 1
    out["attention"] = out["expired"] + out["expiring"]
    return out


def documents_needing_attention(limit=60):
    return list_tracked_documents(status="attention", limit=limit)[:limit]


def due_document_alerts(username=None):
    """المستندات اللي وصلت لمرحلة تنبيه جديدة ولسه ما اتعرضتش للمستخدم (أو انتهى تأجيلها)."""
    username = username or _current_username()
    now = datetime.datetime.now()
    out = []
    with get_session() as s:
        alerts = {}
        for a in s.query(DocumentAlert).filter(DocumentAlert.username == username).all():
            alerts[(a.document_id, a.tier)] = a
    for r in list_tracked_documents():
        tier = _doc_alert_tier(r["days_left"], r["remind_days"])
        if tier is None:
            continue
        a = alerts.get((r["id"], tier))
        if a is None or (a.snoozed_until and a.snoozed_until <= now):
            r = dict(r); r["tier"] = tier
            out.append(r)
    return sorted(out, key=lambda x: x["days_left"])


def mark_document_alerted(items, username=None):
    """items: قايمة (doc_id, tier). بنسجّل إن التنبيه اتعرض (أو بنلغي التأجيل لو كان متأجّل)."""
    username = username or _current_username()
    now = datetime.datetime.now()
    with get_session() as s:
        for doc_id, tier in items:
            a = s.query(DocumentAlert).filter(DocumentAlert.document_id == int(doc_id), DocumentAlert.username == username, DocumentAlert.tier == int(tier)).first()
            if a:
                a.alerted_at = now; a.snoozed_until = None
            else:
                s.add(DocumentAlert(document_id=int(doc_id), username=username, tier=int(tier), alerted_at=now))
        s.commit()


def snooze_document_alert(doc_id, tier, days=1, username=None):
    """"ذكّرني بعد": التنبيه ده يرجع يظهر بعد days يوم."""
    username = username or _current_username()
    until = datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=int(days)), datetime.time(8, 0))
    with get_session() as s:
        a = s.query(DocumentAlert).filter(DocumentAlert.document_id == int(doc_id), DocumentAlert.username == username, DocumentAlert.tier == int(tier)).first()
        if a:
            a.snoozed_until = until
        else:
            s.add(DocumentAlert(document_id=int(doc_id), username=username, tier=int(tier), snoozed_until=until))
        s.commit()


_DOC_LISTENERS = []


def add_document_listener(fn):
    if fn not in _DOC_LISTENERS:
        _DOC_LISTENERS.append(fn)


def remove_document_listener(fn):
    if fn in _DOC_LISTENERS:
        _DOC_LISTENERS.remove(fn)


def _notify_documents_changed(fn):
    import functools

    @functools.wraps(fn)
    def inner(*args, **kwargs):
        result = fn(*args, **kwargs)
        for cb in list(_DOC_LISTENERS):
            try:
                cb()
            except Exception:
                pass
        return result
    return inner


for _dn in ("create_tracked_document", "update_tracked_document", "renew_tracked_document", "set_document_archived", "delete_tracked_document", "mark_document_alerted", "snooze_document_alert"):
    globals()[_dn] = _notify_documents_changed(globals()[_dn])


# ======================================================================
# المصروفات المدفوعة مقدمًا: مبلغ بيتدفع مرة واحدة (إيجار سنة، تأمين، اشتراك...) وبيتقسّم آليًا على مدة بالشهور.
# عند الدفع: مدين "مصروفات مدفوعة مقدمًا" (+ ضريبة المدخلات) / دائن الخزينة أو البنك أو المورد.
# كل شهر: مدين حساب المصروف / دائن "مصروفات مدفوعة مقدمًا" - بيترحّل لوحده (أو بزرار "ترحيل الاستحقاقات").
# ======================================================================
PREPAID_METHODS = {"equal": "أقساط شهرية متساوية", "daily": "بالأيام الفعلية لكل شهر"}
PREPAID_PAYMENT_KINDS = {"paid": "مدفوع الآن (خزينة / بنك)", "payable": "على حساب المورد (آجل)", "none": "متسجّل قبل كده (جدول التقسيم بس)"}
PREPAID_STATE_LABELS = {"active": "نشط", "completed": "مكتمل", "stopped": "موقوف", "cancelled": "ملغى"}
_PREPAID_DEFAULT_TEMPLATES = [
    ("إيجار الموقع", "520037", 12, "equal"), ("إيجار مكاتب ومستودعات", "520038", 12, "equal"), ("التأمين الصحي للموظفين", "520014", 12, "equal"),
    ("تأمين السيارات وخدمات التتبع", "520049", 12, "equal"), ("رسوم تراخيص وتصاريح", "520057", 12, "equal"), ("اشتراكات برامج وخدمات تقنية", "520083", 12, "equal"),
    ("هاتف وإنترنت (اشتراك سنوي)", "520054", 12, "equal"), ("خطابات الضمان", "520072", 12, "daily"), ("رسوم تجديد السيارات", "520048", 12, "equal"),
    ("أدوات ومواد مكتبية", "520078", 6, "equal"), ("صيانة وإصلاح (عقد سنوي)", "520051", 12, "equal"), ("مصروفات تشغيلية متنوعة", "520075", 3, "equal"),
]


def _prepaid_month_end(d):
    import calendar
    return datetime.datetime(d.year, d.month, calendar.monthrange(d.year, d.month)[1], 12, 0)


def prepaid_build_schedule(start_date, months, amount, method="equal"):
    """جدول التقسيم: قايمة dicts (seq, period_from, period_to, entry_date, amount). الفرق الناتج عن التقريب بيروح لآخر قسط.
    equal: n قسط متساوي في n شهر تقويمي بادئ من شهر البداية، كل قسط تاريخه آخر الشهر.
    daily: بيتوزّع على الشهور بنسبة الأيام الفعلية من تاريخ البداية لحد نهاية المدة (آخر قسط في آخر يوم من المدة)."""
    months = int(months); amount = round(float(amount), 2)
    if months < 1 or months > 240:
        raise ValueError("المدة لازم تكون من شهر لـ 240 شهر")
    if amount <= 0:
        raise ValueError("المبلغ لازم يكون أكبر من صفر")
    start = datetime.datetime.combine(start_date.date() if isinstance(start_date, datetime.datetime) else start_date, datetime.time(0, 0))
    rows = []
    if method == "equal":
        base = round(amount / months, 2)
        for k in range(months):
            ms = _agenda_add_months(datetime.datetime(start.year, start.month, 1), k, 1)
            me = _prepaid_month_end(ms)
            rows.append({"seq": k + 1, "period_from": start if k == 0 else ms, "period_to": me.replace(hour=0), "entry_date": me, "amount": base})
    elif method == "daily":
        end = _agenda_add_months(start, months, start.day) - datetime.timedelta(days=1)
        total_days = (end.date() - start.date()).days + 1
        cur = start; k = 0
        while cur <= end:
            me = _prepaid_month_end(cur)
            seg_end = min(me.replace(hour=0), end)
            days = (seg_end.date() - cur.date()).days + 1
            k += 1
            rows.append({"seq": k, "period_from": cur, "period_to": seg_end, "entry_date": seg_end.replace(hour=12), "amount": round(amount * days / total_days, 2)})
            cur = seg_end + datetime.timedelta(days=1)
    else:
        raise ValueError("طريقة التقسيم غير معروفة")
    diff = round(amount - sum(r["amount"] for r in rows), 2)
    rows[-1]["amount"] = round(rows[-1]["amount"] + diff, 2)
    return rows


def list_prepaid_templates(active_only=True):
    with get_session() as s:
        if not s.query(PrepaidTemplate).count():
            for i, (name, code, months, method) in enumerate(_PREPAID_DEFAULT_TEMPLATES):
                acc = s.query(Account).filter(Account.code == code).first()
                s.add(PrepaidTemplate(name=name, expense_account_id=acc.id if acc else None, months=months, method=method, sort_order=i))
            s.commit()
        q = s.query(PrepaidTemplate).options(joinedload(PrepaidTemplate.expense_account))
        if active_only:
            q = q.filter(PrepaidTemplate.is_active.is_(True))
        rows = q.order_by(PrepaidTemplate.sort_order, PrepaidTemplate.id).all()
        s.expunge_all()
        return rows


def _check_prepaid_template(name, months, method):
    name = (name or "").strip()
    if not name:
        raise ValueError("اكتب اسم القالب")
    months = int(months or 0)
    if months < 1 or months > 240:
        raise ValueError("مدة القالب لازم تكون من شهر لـ 240 شهر")
    if method not in PREPAID_METHODS:
        raise ValueError("طريقة التقسيم غير معروفة")
    return name, months


def create_prepaid_template(name, expense_account_id=None, months=12, method="equal", notes=""):
    require_action("prepaid_expenses", "create")
    list_prepaid_templates()
    name, months = _check_prepaid_template(name, months, method)
    with get_session() as s:
        if s.query(PrepaidTemplate).filter(PrepaidTemplate.name == name).first():
            raise ValueError("فيه قالب بنفس الاسم")
        t = PrepaidTemplate(name=name, expense_account_id=int(expense_account_id) if expense_account_id else None, months=months, method=method, notes=(notes or "").strip(),
                            sort_order=(s.query(func.coalesce(func.max(PrepaidTemplate.sort_order), 0)).scalar() or 0) + 1)
        s.add(t); s.commit(); s.refresh(t)
        return t.id


def update_prepaid_template(template_id, name, expense_account_id=None, months=12, method="equal", notes="", is_active=True):
    require_action("prepaid_expenses", "edit")
    name, months = _check_prepaid_template(name, months, method)
    with get_session() as s:
        t = s.get(PrepaidTemplate, int(template_id))
        if not t:
            raise ValueError("القالب غير موجود")
        if s.query(PrepaidTemplate).filter(PrepaidTemplate.name == name, PrepaidTemplate.id != t.id).first():
            raise ValueError("فيه قالب تاني بنفس الاسم")
        t.name = name; t.expense_account_id = int(expense_account_id) if expense_account_id else None; t.months = months; t.method = method
        t.notes = (notes or "").strip(); t.is_active = bool(is_active)
        s.commit()


def _prepaid_line_dict(l):
    return {"id": l.id, "seq": l.seq, "period_from": l.period_from, "period_to": l.period_to, "entry_date": l.entry_date, "amount": l.amount, "state": l.state,
            "journal_entry_id": l.journal_entry_id, "posted_at": l.posted_at}


def _prepaid_to_dict(p, today=None):
    today = today or datetime.datetime.now()
    live = [l for l in p.lines if l.state in ("pending", "posted")]
    posted = round(sum(l.amount for l in live if l.state == "posted"), 2)
    pending = round(sum(l.amount for l in live if l.state == "pending"), 2)
    due = [l for l in live if l.state == "pending" and l.entry_date <= today]
    nxt = next((l for l in live if l.state == "pending"), None)
    return {"id": p.id, "number": p.number, "title": p.title, "template_id": p.template_id, "template": p.template.name if p.template else "",
            "supplier_id": p.supplier_id, "supplier": p.supplier.name if p.supplier else "", "expense_account_id": p.expense_account_id,
            "expense_account": f"{p.expense_account.code} - {p.expense_account.name}" if p.expense_account else "", "prepaid_account_id": p.prepaid_account_id,
            "prepaid_account": f"{p.prepaid_account.code} - {p.prepaid_account.name}" if p.prepaid_account else "", "amount": p.amount, "tax_rate": p.tax_rate,
            "tax_amount": p.tax_amount, "total_paid": round((p.amount or 0) + (p.tax_amount or 0), 2), "start_date": p.start_date, "months": p.months, "method": p.method,
            "payment_kind": p.payment_kind, "payment_method": p.payment_method.name if p.payment_method else "", "branch_id": p.branch_id, "cost_center_id": p.cost_center_id,
            "auto_post": bool(p.auto_post), "state": p.state, "initial_entry_id": p.initial_entry_id, "notes": p.notes or "", "posted": posted, "remaining": pending,
            "progress": round(posted / p.amount * 100, 1) if p.amount else 0.0, "lines_total": len(live), "lines_posted": len([l for l in live if l.state == "posted"]),
            "due_count": len(due), "due_amount": round(sum(l.amount for l in due), 2), "next_due": nxt.entry_date if nxt else None,
            "next_amount": nxt.amount if nxt else 0.0, "end_date": live[-1].period_to if live else None, "lines": [_prepaid_line_dict(l) for l in p.lines]}


def _prepaid_load():
    return (joinedload(PrepaidExpense.lines), joinedload(PrepaidExpense.template), joinedload(PrepaidExpense.supplier), joinedload(PrepaidExpense.expense_account),
            joinedload(PrepaidExpense.prepaid_account), joinedload(PrepaidExpense.payment_method))


def get_prepaid_expense(prepaid_id):
    with get_session() as s:
        p = s.query(PrepaidExpense).options(*_prepaid_load()).filter(PrepaidExpense.id == int(prepaid_id)).first()
        return _prepaid_to_dict(p) if p else None


def list_prepaid_expenses(state=None, text=None):
    with get_session() as s:
        q = s.query(PrepaidExpense).options(*_prepaid_load())
        if state:
            q = q.filter(PrepaidExpense.state == state)
        if user_branch_ids():
            q = q.filter((PrepaidExpense.branch_id.is_(None)) | (PrepaidExpense.branch_id.in_(user_branch_ids())))
        rows = [_prepaid_to_dict(p) for p in q.order_by(PrepaidExpense.id.desc()).all()]
    if text and text.strip():
        t = text.strip().lower()
        rows = [r for r in rows if t in (r["number"] + " " + r["title"] + " " + r["supplier"] + " " + r["expense_account"]).lower()]
    return rows


def prepaid_summary():
    """أرقام الكروت: إجمالي المدفوع مقدمًا (النشط)، اللي اتحمّل كمصروف، المتبقي (رصيد الحساب)، والمستحق ترحيله."""
    rows = list_prepaid_expenses()
    act = [r for r in rows if r["state"] == "active"]
    return {"count": len(act), "total": round(sum(r["amount"] for r in act), 2), "posted": round(sum(r["posted"] for r in act), 2), "remaining": round(sum(r["remaining"] for r in act), 2),
            "due_count": sum(r["due_count"] for r in act), "due_amount": round(sum(r["due_amount"] for r in act), 2)}


def create_prepaid_expense(title, expense_account_id, amount, start_date, months=12, method="equal", tax_rate=0.0, payment_kind="paid", payment_method_id=None,
                           supplier_id=None, prepaid_account_id=None, template_id=None, branch_id=None, cost_center_id=None, auto_post=True, notes="",
                           payment_date=None, post_due=True):
    """إنشاء مصروف مدفوع مقدمًا: جدول التقسيم + قيد الدفع (لو مدفوع/آجل) + ترحيل الأقساط المستحقة لحد النهاردة (لو auto_post)."""
    require_action("prepaid_expenses", "create")
    title = (title or "").strip()
    if not title:
        raise ValueError("اكتب بيان المصروف")
    if not expense_account_id:
        raise ValueError("اختر حساب المصروف")
    if not isinstance(start_date, datetime.datetime):
        raise ValueError("حدد تاريخ بداية المدة")
    amount = round(float(amount or 0), 2)
    tax_rate = float(tax_rate or 0)
    if not 0 <= tax_rate <= 100:
        raise ValueError("نسبة الضريبة غير صحيحة")
    if payment_kind not in PREPAID_PAYMENT_KINDS:
        raise ValueError("طريقة السداد غير معروفة")
    schedule = prepaid_build_schedule(start_date, months, amount, method)
    tax_amount = round(amount * tax_rate / 100.0, 2)
    cfg = get_accounting_settings()
    prepaid_acc = int(prepaid_account_id) if prepaid_account_id else (cfg.prepaid_expenses_account_id if cfg else None)
    if not prepaid_acc:
        raise ValueError("حدد حساب المصروفات المدفوعة مقدمًا من إعدادات الشركة (الحسابات الافتراضية)")
    if int(expense_account_id) == prepaid_acc:
        raise ValueError("حساب المصروف لازم يختلف عن حساب المصروفات المدفوعة مقدمًا")
    credit_acc = None; partner = None
    if payment_kind == "paid":
        if not payment_method_id:
            raise ValueError("اختر طريقة الدفع")
        credit_acc, _name = _resolve_payment_method_account(payment_method_id)
    elif payment_kind == "payable":
        if not supplier_id:
            raise ValueError("اختر المورد (السداد على حسابه)")
        credit_acc = cfg.payable_account_id
        if not credit_acc:
            raise ValueError("حساب الموردين الافتراضي غير محدد في الإعدادات")
        partner = ("supplier", int(supplier_id))
    if tax_amount > 0 and payment_kind != "none" and not cfg.vat_input_account_id:
        raise ValueError("حساب ضريبة المدخلات غير محدد في الإعدادات")
    branch_id = branch_id or default_branch_id(); cost_center_id = cost_center_id or default_cost_center_id()
    with get_session() as s:
        for aid, label in ((int(expense_account_id), "حساب المصروف"), (prepaid_acc, "حساب المدفوع مقدمًا")):
            if not s.get(Account, aid):
                raise ValueError(f"{label} غير موجود")
        p = PrepaidExpense(number=_next_code(s, PrepaidExpense, "PPE-"), template_id=int(template_id) if template_id else None, title=title,
                           supplier_id=int(supplier_id) if supplier_id else None, expense_account_id=int(expense_account_id), prepaid_account_id=prepaid_acc,
                           amount=amount, tax_rate=tax_rate, tax_amount=tax_amount, start_date=start_date, months=int(months), method=method, payment_kind=payment_kind,
                           payment_method_id=int(payment_method_id) if (payment_kind == "paid" and payment_method_id) else None, branch_id=branch_id, cost_center_id=cost_center_id,
                           auto_post=bool(auto_post), state="active", notes=(notes or "").strip(), created_by=_current_username())
        for r in schedule:
            p.lines.append(PrepaidExpenseLine(seq=r["seq"], period_from=r["period_from"], period_to=r["period_to"], entry_date=r["entry_date"], amount=r["amount"], state="pending"))
        s.add(p); s.commit(); s.refresh(p)
        pid, number = p.id, p.number
    if payment_kind != "none":
        try:
            desc = f"دفع مصروف مقدم {number} - {title}"
            lines = [{"account_id": prepaid_acc, "debit": amount, "description": desc}]
            if tax_amount > 0:
                lines.append({"account_id": cfg.vat_input_account_id, "debit": tax_amount, "description": f"ضريبة مدخلات - {desc}"})
            cr = {"account_id": credit_acc, "credit": round(amount + tax_amount, 2), "description": desc}
            if partner:
                cr["partner_type"], cr["partner_id"] = partner
            lines.append(cr)
            jid = create_journal_entry(lines, reference=number, description=desc, source_type="prepaid_expense_payment", source_id=pid,
                                       entry_date=payment_date or min(start_date, datetime.datetime.now()), branch_id=branch_id, cost_center_id=cost_center_id)
            with get_session() as s:
                s.get(PrepaidExpense, pid).initial_entry_id = jid; s.commit()
        except Exception:
            with get_session() as s:            # القيد فشل (فترة مقفولة مثلًا) - نلغي المصروف الفاضي
                row = s.get(PrepaidExpense, pid)
                if row: s.delete(row); s.commit()
            raise
    if post_due and auto_post:
        _post_due_prepaid(prepaid_id=pid)
    return pid


def _post_prepaid_line(s, p, line, force=False):
    """بيرحّل قسط واحد (قيد مدين المصروف / دائن المدفوع مقدمًا). بيرجّع id القيد."""
    if line.state != "pending":
        raise ValueError("القسط ده اترحّل بالفعل")
    if not force and line.entry_date > datetime.datetime.now():
        raise ValueError(f"القسط ده مستحق في {line.entry_date:%Y-%m-%d} - لسه ما جاش ميعاده")
    desc = f"إطفاء مصروف مقدم {p.number} - {p.title} ({line.period_from:%Y-%m-%d} إلى {line.period_to:%Y-%m-%d})"
    return create_journal_entry(
        [{"account_id": p.expense_account_id, "debit": line.amount, "description": desc}, {"account_id": p.prepaid_account_id, "credit": line.amount, "description": desc}],
        reference=p.number, description=desc, source_type="prepaid_expense", source_id=p.id, entry_date=line.entry_date, branch_id=p.branch_id, cost_center_id=p.cost_center_id)


def _post_due_prepaid(as_of=None, only_auto=True, prepaid_id=None):
    """ترحيل الأقساط المستحقة (تاريخها <= as_of) للمصروفات النشطة. بيعدّي على الفترات المقفولة ويسجّل الخطأ ويكمّل."""
    as_of = as_of or datetime.datetime.now()
    report = {"posted": 0, "amount": 0.0, "errors": [], "items": 0}
    with get_session() as s:
        q = s.query(PrepaidExpense).filter(PrepaidExpense.state == "active")
        if only_auto:
            q = q.filter(PrepaidExpense.auto_post.is_(True))
        if prepaid_id:
            q = q.filter(PrepaidExpense.id == int(prepaid_id))
        ids = [p.id for p in q.all()]
    for pid in ids:
        touched = False
        with get_session() as s:
            p = s.query(PrepaidExpense).options(joinedload(PrepaidExpense.lines)).filter(PrepaidExpense.id == pid).first()
            for line in [l for l in p.lines if l.state == "pending" and l.entry_date <= as_of]:
                try:
                    jid = _post_prepaid_line(s, p, line, force=True)      # الفلترة بتاريخ as_of فوق، فمفيش داعي نفحص "لسه ما جاش ميعاده" تاني
                    line.state = "posted"; line.journal_entry_id = jid; line.posted_at = datetime.datetime.now()
                    s.commit()
                    report["posted"] += 1; report["amount"] = round(report["amount"] + line.amount, 2); touched = True
                except Exception as ex:
                    s.rollback()
                    report["errors"].append(f"{p.number} - قسط {line.entry_date:%Y-%m}: {ex}")
            p = s.query(PrepaidExpense).options(joinedload(PrepaidExpense.lines)).filter(PrepaidExpense.id == pid).first()
            if p.state == "active" and p.lines and all(l.state in ("posted", "void") for l in p.lines):
                p.state = "completed"; s.commit()
        if touched:
            report["items"] += 1
    return report


def post_due_prepaid_lines(as_of=None):
    """زرار "ترحيل الاستحقاقات": بيرحّل كل الأقساط المستحقة لكل المصروفات النشطة (حتى اللي الترحيل الآلي مقفول عليها)."""
    require_action("prepaid_expenses", "post")
    return _post_due_prepaid(as_of, only_auto=False)


def auto_post_prepaid_expenses():
    """الترحيل الآلي (بيتنده وقت تسجيل الدخول): الأقساط المستحقة للمصروفات اللي الترحيل الآلي مفعّل عليها."""
    try:
        return _post_due_prepaid(only_auto=True)
    except Exception as ex:
        return {"posted": 0, "amount": 0.0, "errors": [str(ex)], "items": 0}


def post_prepaid_line_now(line_id):
    """ترحيل قسط واحد (حتى لو لسه ما جاش ميعاده - ترحيل مبكر)."""
    require_action("prepaid_expenses", "post")
    with get_session() as s:
        line = s.get(PrepaidExpenseLine, int(line_id))
        if not line:
            raise ValueError("القسط غير موجود")
        p = s.query(PrepaidExpense).options(joinedload(PrepaidExpense.lines)).filter(PrepaidExpense.id == line.prepaid_id).first()
        if p.state != "active":
            raise ValueError("المصروف ده مش نشط")
        jid = _post_prepaid_line(s, p, line, force=True)
        line.state = "posted"; line.journal_entry_id = jid; line.posted_at = datetime.datetime.now()
        if all(l.state in ("posted", "void") for l in p.lines):
            p.state = "completed"
        s.commit()
        return jid


def update_prepaid_expense(prepaid_id, title, notes="", expense_account_id=None, auto_post=True, cost_center_id=None):
    """تعديل محدود: البيان والملاحظات وحساب المصروف (للأقساط الجاية بس) والترحيل الآلي. لتغيير المبلغ أو المدة: الغي المصروف (لو ما اترحّلش حاجة) وأنشئه من جديد."""
    require_action("prepaid_expenses", "edit")
    title = (title or "").strip()
    if not title:
        raise ValueError("اكتب بيان المصروف")
    with get_session() as s:
        p = s.get(PrepaidExpense, int(prepaid_id))
        if not p:
            raise ValueError("المصروف غير موجود")
        if expense_account_id:
            acc = s.get(Account, int(expense_account_id))
            if not acc:
                raise ValueError("حساب المصروف غير موجود")
            if int(expense_account_id) == p.prepaid_account_id:
                raise ValueError("حساب المصروف لازم يختلف عن حساب المدفوع مقدمًا")
            p.expense_account_id = int(expense_account_id)
        p.title = title; p.notes = (notes or "").strip(); p.auto_post = bool(auto_post)
        if cost_center_id:
            p.cost_center_id = int(cost_center_id)
        s.commit()


def stop_prepaid_expense(prepaid_id, expense_remaining=True):
    """إيقاف المصروف قبل نهاية مدته (إنهاء عقد/تأمين...): إما تحميل المتبقي كمصروف دلوقتي بقيد واحد، أو إيقاف الأقساط
    الجاية وترك الرصيد على حساب المدفوع مقدمًا (لتسويته يدويًا)."""
    require_action("prepaid_expenses", "post")
    with get_session() as s:
        p = s.query(PrepaidExpense).options(joinedload(PrepaidExpense.lines)).filter(PrepaidExpense.id == int(prepaid_id)).first()
        if not p:
            raise ValueError("المصروف غير موجود")
        if p.state != "active":
            raise ValueError("المصروف ده مش نشط")
        pending = [l for l in p.lines if l.state == "pending"]
        remaining = round(sum(l.amount for l in pending), 2)
        for l in pending:
            l.state = "void"
        jid = None
        if expense_remaining and remaining > 0:
            now = datetime.datetime.now()
            desc = f"تحميل المتبقي من مصروف مقدم {p.number} - {p.title} (إيقاف قبل نهاية المدة)"
            try:
                jid = create_journal_entry([{"account_id": p.expense_account_id, "debit": remaining, "description": desc}, {"account_id": p.prepaid_account_id, "credit": remaining, "description": desc}],
                                           reference=p.number, description=desc, source_type="prepaid_expense", source_id=p.id, entry_date=now, branch_id=p.branch_id, cost_center_id=p.cost_center_id)
            except Exception:
                s.rollback()
                raise
            p.lines.append(PrepaidExpenseLine(seq=len(p.lines) + 1, period_from=now, period_to=now, entry_date=now, amount=remaining, state="posted", journal_entry_id=jid, posted_at=now))
        p.state = "stopped"
        s.commit()
        return {"remaining": remaining, "entry_id": jid}


def cancel_prepaid_expense(prepaid_id):
    """إلغاء مصروف لسه ما اترحّلش منه أي قسط: بيعمل قيد عكسي لقيد الدفع (لو كان اتسجّل) وبيلغي الجدول."""
    require_action("prepaid_expenses", "delete")
    with get_session() as s:
        p = s.query(PrepaidExpense).options(joinedload(PrepaidExpense.lines)).filter(PrepaidExpense.id == int(prepaid_id)).first()
        if not p:
            raise ValueError("المصروف غير موجود")
        if p.state != "active":
            raise ValueError("المصروف ده مش نشط")
        if any(l.state == "posted" for l in p.lines):
            raise ValueError("اترحّلت منه أقساط بالفعل - استخدم \"إيقاف\" بدل الإلغاء")
        initial = p.initial_entry_id
        pid, number, title = p.id, p.number, p.title
    if initial:
        from .db import JournalEntry, JournalEntryLine
        with get_session() as s:
            orig = s.query(JournalEntryLine).filter(JournalEntryLine.entry_id == initial).all()
            rev = [{"account_id": l.account_id, "debit": l.credit, "credit": l.debit, "description": f"عكس قيد دفع مصروف مقدم {number} (إلغاء)",
                    "partner_type": l.partner_type, "partner_id": l.partner_id} for l in orig]
            e = s.get(JournalEntry, initial)
            bid = e.branch_id if e else None
        create_journal_entry(rev, reference=number, description=f"إلغاء مصروف مقدم {number} - {title}", source_type="prepaid_expense_payment", source_id=pid, branch_id=bid)
    with get_session() as s:
        p = s.query(PrepaidExpense).options(joinedload(PrepaidExpense.lines)).filter(PrepaidExpense.id == pid).first()
        for l in p.lines:
            l.state = "void"
        p.state = "cancelled"
        s.commit()


# ======================================================================
# تقرير مقارنة أسعار الشراء: بين فترات (سنوات / شهور / أيام) أو بين موردين، مجمّع حسب الفئة وتحته الأصناف.
# السعر = سعر وحدة الشراء الصافي (بعد خصم البند، من غير الضريبة) محوّل للوحدة الأساسية للصنف، فبيتقارن صح حتى لو اتشرى بوحدات مختلفة.
# ======================================================================
PPC_METRICS = {"avg": "متوسط مرجح", "last": "آخر سعر", "min": "أقل سعر", "max": "أعلى سعر"}
PPC_GRANULARITY = {"year": "سنوات", "month": "شهور", "day": "أيام"}


def purchase_price_comparison(date_from=None, date_to=None, granularity="month", group_by="period", metric="avg", supplier_id=None,
                              category_id=None, search=None, max_columns=36):
    """بيرجّع: columns (عناوين الأعمدة: فترات أو موردين)، categories (كل فئة: إجماليها لكل عمود + أصنافها بأسعارها)، totals، truncated.
    group_by: period (أعمدة = فترات حسب granularity) | supplier (أعمدة = موردين). metric: avg | last | min | max."""
    if group_by not in ("period", "supplier"):
        raise ValueError("نوع المقارنة غير معروف")
    if granularity not in PPC_GRANULARITY:
        raise ValueError("تقسيم الفترة غير معروف")
    if metric not in PPC_METRICS:
        raise ValueError("طريقة حساب السعر غير معروفة")
    with get_session() as s:
        q = (s.query(PurchaseInvoice.date, PurchaseInvoice.supplier_id, PurchaseInvoiceItem.product_id, PurchaseInvoiceItem.quantity, PurchaseInvoiceItem.unit_factor,
                     PurchaseInvoiceItem.unit_price, PurchaseInvoiceItem.discount)
             .join(PurchaseInvoice, PurchaseInvoice.id == PurchaseInvoiceItem.invoice_id).filter(PurchaseInvoice.voided.is_(False)))
        if date_from:
            q = q.filter(PurchaseInvoice.date >= date_from)
        if date_to:
            q = q.filter(PurchaseInvoice.date <= datetime.datetime.combine(date_to.date() if hasattr(date_to, "date") else date_to, datetime.time(23, 59, 59)))
        if supplier_id and group_by == "period":
            q = q.filter(PurchaseInvoice.supplier_id == int(supplier_id))
        if user_branch_ids():
            q = q.filter((PurchaseInvoice.branch_id.is_(None)) | (PurchaseInvoice.branch_id.in_(user_branch_ids())))
        raw = q.order_by(PurchaseInvoice.date).all()
        products = {p.id: p for p in s.query(Product).options(joinedload(Product.category)).all()}
        suppliers = {x.id: x.name for x in s.query(Supplier).all()}

    def bucket(dt_, sup):
        if group_by == "supplier":
            return sup or 0
        return f"{dt_.year}" if granularity == "year" else (f"{dt_.year}-{dt_.month:02d}" if granularity == "month" else dt_.strftime("%Y-%m-%d"))

    agg = {}        # (product_id, bucket) -> dict
    needle = (search or "").strip().lower()
    for dt_, sup, pid, qty, factor, price, disc in raw:
        p = products.get(pid)
        if not p or (category_id and p.category_id != int(category_id)):
            continue
        if needle and needle not in (p.sku + " " + p.name).lower():
            continue
        base_qty = float(qty or 0) * float(factor or 1)
        if base_qty <= 0:
            continue
        net = max(0.0, float(qty or 0) * float(price or 0) - float(disc or 0))
        unit = net / base_qty
        a = agg.setdefault((pid, bucket(dt_, sup)), {"qty": 0.0, "value": 0.0, "min": unit, "max": unit, "last": unit, "n": 0})
        a["qty"] += base_qty; a["value"] += net; a["min"] = min(a["min"], unit); a["max"] = max(a["max"], unit); a["last"] = unit; a["n"] += 1   # raw مرتّب بالتاريخ فآخر قيمة = آخر سعر
    buckets = {}
    for (pid, b), a in agg.items():
        buckets[b] = buckets.get(b, 0.0) + a["value"]
    truncated = False
    if group_by == "supplier":
        keys = sorted(buckets, key=lambda k: -buckets[k])
        if len(keys) > max_columns:
            keys, truncated = keys[:max_columns], True
        labels = [suppliers.get(k, "بدون مورد") for k in keys]
    else:
        keys = sorted(buckets)
        if len(keys) > max_columns:
            keys, truncated = keys[-max_columns:], True      # بنعرض الأحدث
        labels = list(keys)

    def price_of(a):
        return None if a is None else (a["value"] / a["qty"] if metric == "avg" and a["qty"] else a[metric if metric != "avg" else "last"])

    by_cat = {}
    for pid in sorted({k[0] for k in agg}):
        p = products[pid]
        cells = [agg.get((pid, k)) for k in keys]
        prices = [price_of(c) for c in cells]
        have = [x for x in prices if x is not None]
        if not have:
            continue
        first, last = have[0], have[-1]
        total_qty = sum(c["qty"] for c in cells if c); total_value = sum(c["value"] for c in cells if c)
        row = {"product_id": pid, "sku": p.sku, "name": p.name, "unit": p.unit or "", "prices": prices, "qtys": [c["qty"] if c else None for c in cells],
               "values": [c["value"] if c else None for c in cells], "min": min(have), "max": max(have), "total_qty": total_qty, "total_value": total_value,
               "change_pct": ((last - first) / first * 100.0) if len(have) > 1 and first else None,
               "spread_pct": ((max(have) - min(have)) / min(have) * 100.0) if len(have) > 1 and min(have) else None,
               "best_index": prices.index(min(have)) if len(have) > 1 else None, "worst_index": prices.index(max(have)) if len(have) > 1 else None}
        cat = p.category
        entry = by_cat.setdefault(p.category_id or 0, {"category_id": p.category_id, "name": cat.name if cat else "بدون فئة", "products": []})
        entry["products"].append(row)
    categories = []
    for entry in sorted(by_cat.values(), key=lambda e: e["name"]):
        prods = entry["products"]
        values = [sum((r["values"][i] or 0.0) for r in prods) or None for i in range(len(keys))]
        weighted = [(r["change_pct"], r["total_value"]) for r in prods if r["change_pct"] is not None and r["total_value"] > 0]
        wsum = sum(w for _, w in weighted)
        entry.update({"values": values, "total_value": sum(r["total_value"] for r in prods), "count": len(prods),
                      "change_pct": (sum(c * w for c, w in weighted) / wsum) if wsum else None})
        categories.append(entry)
    totals = [sum((c["values"][i] or 0.0) for c in categories) or None for i in range(len(keys))]
    return {"columns": labels, "keys": keys, "categories": categories, "totals": totals, "grand_total": sum(c["total_value"] for c in categories),
            "truncated": truncated, "group_by": group_by, "metric": metric, "granularity": granularity}
