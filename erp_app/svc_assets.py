"""الأصول الثابتة (التسجيل، الإهلاك، فواتير مشتريات الأصول، الجرد).

اتنقلت من services.py (تقسيم الملف الكبير). الأسماء كلها لسه بتتقري من services.* لأن services بيعيد تصديرها."""
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

from .services import (  # noqa: E402  (الاستيراد الدائري آمن: services بيستورد الملف ده في آخره)
    _accounting_settings,
    _get_user,
    _next_code,
    _next_invoice_number,
    allowed_branch,
    allowed_cost_center,
    create_journal_entry,
    default_branch_id,
    default_cost_center_id,
    downloads_dir,
    get_company_settings,
    get_journal_entry,
    list_products,
    require_action,
    set_journal_entry_draft_by_source,
)

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
