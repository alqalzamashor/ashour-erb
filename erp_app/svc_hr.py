"""الموارد البشرية: الموظفون، العقود، الرواتب، المخصصات والتأمينات.

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
    _db_lock,
    _next_payment_number,
    create_journal_entry,
    default_branch_id,
    default_cost_center_id,
    get_journal_entry,
    get_payment_method,
    post_journal_entry_by_id,
    require_action,
    update_journal_entry,
    void_payment,
)

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


def _opening_leave_used(v):
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        raise ValueError("أيام الإجازة المستخدمة سابقًا لازم تكون رقم")
    if v < 0:
        raise ValueError("أيام الإجازة المستخدمة سابقًا لا يمكن أن تكون سالبة")
    return round(v, 2)


def create_employee(name, national_id="", phone="", email="", position="", department="",
                     hire_date=None, bank_account="", branch_id=None, cost_center_id=None, leave_used_opening=0.0):
    require_action("employees", "create")
    name = (name or "").strip()
    if not name:
        raise ValueError("اسم الموظف مطلوب")
    leave_used_opening = _opening_leave_used(leave_used_opening)
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
            leave_used_opening=leave_used_opening,
        )
        s.add(e); s.commit(); s.refresh(e)
        return e.id


def update_employee(employee_id, **fields):
    require_action("employees", "edit")
    with get_session() as s:
        e = s.get(Employee, employee_id)
        if not e:
            raise ValueError("الموظف غير موجود")
        if "leave_used_opening" in fields:
            fields["leave_used_opening"] = _opening_leave_used(fields["leave_used_opening"])
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
        # عقد جديد = الموظف يرجع نشط (لو كان اتحوّل لغير نشط بعد تسوية نهاية الخدمة)
        emp_obj = s.get(Employee, int(employee_id))
        if emp_obj is not None and not emp_obj.is_active:
            emp_obj.is_active = True
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
        # نفس تسوية نهاية الخدمة: الموظف يبقى غير نشط لحد ما يتعمله عقد جديد
        others = s.query(Contract).filter(Contract.employee_id == c.employee_id, Contract.id != c.id, Contract.state == "active").count()
        if not others:
            emp_row = s.get(Employee, c.employee_id)
            if emp_row is not None:
                emp_row.is_active = False
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
            joinedload(PayrollRun.payslips).joinedload(Payslip.employee).joinedload(Employee.cost_center),
            joinedload(PayrollRun.payslips).joinedload(Payslip.employee).joinedload(Employee.branch),
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

    # التأخير والإضافي (من البصمة): بيتحسبوا بس لو مفعّلين في إعدادات الدوام. أجر دقيقة التأخير = أجر اليوم ÷ دقائق الدوام،
    # وأجر ساعة الإضافي = الراتب الأساسي ÷ (أساس اليوم × ساعات الدوام) × المعامل.
    late_ded, ot_pay = 0.0, 0.0
    try:
        from . import attendance as _att
        rules = _att.get_shift_rules(p.employee_id, last)         # وردية آخر الشهر (لو اتغيّرت في النص)
    except Exception:
        rules = None
    if rules:
        if rules["late_on"] and (p.late_minutes or 0) > 0 and daily:
            late_ded = min(round(float(p.late_minutes) * daily / rules["shift_minutes"], 2), max(0.0, round(gross - unemp_ded - leave_ded - abs_ded, 2)))
        if rules["ot_on"] and (p.overtime_minutes or 0) > 0 and divisor:
            hourly = (p.basic_salary or 0) / divisor / (rules["shift_minutes"] / 60.0)
            ot_pay = round(float(p.overtime_minutes) / 60.0 * hourly * rules["ot_mult"], 2)

    p.unemployed_days = float(unemployed); p.unemployed_deduction = unemp_ded
    p.leave_deduction = leave_ded; p.leave_deduction_days = leave_days
    p.leave_days_total = float(leave_total)
    p.absent_days = absent; p.absence_deduction = abs_ded
    p.late_deduction = late_ded; p.overtime_pay = ot_pay
    p.worked_days = float(max(0.0, employed - leave_total - absent))
    p.net_salary = round(gross - p.total_deductions + ot_pay, 2)


def create_payroll_run(month, year, branch_id=None, cost_center_id=None):
    """ينشئ دورة رواتب جديدة ويولّد قسيمة لكل موظف نشط له عقد ساري تلقائياً.
    الدورة ممكن تتحدد بفرع و/أو قسم (مركز تكلفة)؛ من غير تحديد = كل الموظفين.
    الموظف اللي ليه قسيمة في دورة تانية لنفس الشهر مبيدخلش الدورة دي تاني."""
    require_action("payroll", "create")
    month = int(month); year = int(year)
    if month < 1 or month > 12:
        raise ValueError("الشهر غير صحيح")
    branch_id = int(branch_id) if branch_id else None
    cost_center_id = int(cost_center_id) if cost_center_id else None
    with get_session() as s:
        existing = s.query(PayrollRun).filter(
            PayrollRun.month == month, PayrollRun.year == year,
            PayrollRun.scope_branch_id.is_(None) if branch_id is None else PayrollRun.scope_branch_id == branch_id,
            PayrollRun.scope_cost_center_id.is_(None) if cost_center_id is None else PayrollRun.scope_cost_center_id == cost_center_id,
        ).first()
        if existing:
            raise ValueError(f"دورة رواتب شهر {month}/{year} بنفس الفرع والقسم موجودة بالفعل (رقم {existing.number})")
        # الموظف غير النشط (اتفسخ عقده أو خد تسوية نهاية خدمة) بيدخل الدورة لو عقده بيغطي أي يوم من الشهر - عشان أيام شغله الأخيرة تتحاسب
        q = s.query(Employee)
        if branch_id:
            q = q.filter(Employee.branch_id == branch_id)
        if cost_center_id:
            q = q.filter(Employee.cost_center_id == cost_center_id)
        covered = {eid for (eid,) in s.query(Payslip.employee_id).join(PayrollRun, Payslip.run_id == PayrollRun.id)
                   .filter(PayrollRun.month == month, PayrollRun.year == year).all()}
        employees = []
        for e in q.all():
            if e.id in covered:
                continue
            if e.is_active:
                employees.append(e); continue
            wc0 = weighted_pay_components(s, e.id, month, year)        # غير نشط: ندخله بس لو عقده اتنهى/انتهى وبيغطي أيام من الشهر (مش لو اتوقف يدويًا وعقده ساري)
            if wc0 and wc0["latest"].state in ("terminated", "expired"):
                employees.append(e)
        if not employees:
            raise ValueError("مفيش موظفين نشطين متاحين للدورة دي (يا مفيش موظفين في الفرع/القسم ده، أو كلهم اتحسبوا في دورة تانية لنفس الشهر)")
        number = _next_code(s, PayrollRun, "PR-")
        run = PayrollRun(number=number, month=month, year=year, branch_id=branch_id or default_branch_id(), state="draft",
                         scope_branch_id=branch_id, scope_cost_center_id=cost_center_id)
        s.add(run); s.flush()

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


def _emp_tag(eid):
    return {"partner_type": "employee", "partner_id": int(eid)} if eid else {}


def _payroll_entry_lines(payslips, cfg):
    """سطور قيد ترحيل الرواتب: سطر لكل (حساب، موظف) عشان كل حركة تتنسب للموظف (شجرة الحسابات > الموظفين > الحركات في التقارير المالية)."""
    debit, credit, payable = {}, {}, {}

    def add(book, amount, account_id, emp_name, label, eid):
        if not amount:
            return
        if not account_id:
            raise ValueError(f'الموظف "{emp_name}" عقده مفيهوش حساب "{label}" محدد - عدّل العقد من شاشة العقود أولاً')
        book[(account_id, eid)] = book.get((account_id, eid), 0.0) + amount

    for p in payslips:
        n = p.employee.name if p.employee else f"#{p.employee_id}"
        e = p.employee_id
        add(debit, p.basic_salary, p.basic_salary_account_id, n, "الراتب الأساسي", e)
        add(debit, p.housing_allowance, p.housing_allowance_account_id, n, "بدل السكن", e)
        add(debit, p.transport_allowance, p.transport_allowance_account_id, n, "بدل النقل", e)
        add(debit, p.other_allowances, p.other_allowances_account_id, n, "بدلات أخرى", e)
        add(credit, p.gosi_deduction, p.gosi_deduction_account_id, n, "خصم التأمينات الاجتماعية", e)
        add(credit, p.other_deductions, p.other_deductions_account_id, n, "الخصومات الأخرى", e)
        add(debit, p.overtime_pay, p.basic_salary_account_id, n, "الراتب الأساسي (بدل الإضافي)", e)
        add(credit, (p.leave_deduction or 0) + (p.absence_deduction or 0) + (p.unemployed_deduction or 0) + (p.late_deduction or 0),
            cfg.leave_deduction_account_id or p.other_deductions_account_id, n, "الخصومات الأخرى (خصم الإجازات والغياب والتأخير)", e)
        payable[e] = payable.get(e, 0.0) + (p.net_salary or 0.0)
    if not cfg.salaries_payable_account_id:
        raise ValueError("إعداد حساب الرواتب المستحقة ناقص - راجع الإعدادات المحاسبية")
    lines = [{"account_id": a, "debit": round(v, 2), **_emp_tag(e)} for (a, e), v in debit.items()]
    lines += [{"account_id": a, "credit": round(v, 2), **_emp_tag(e)} for (a, e), v in credit.items()]
    lines += [{"account_id": cfg.salaries_payable_account_id, "credit": round(v, 2), **_emp_tag(e)} for e, v in payable.items() if round(v, 2)]
    return lines


def _allowance_entry_lines(items, cfg):
    debit, credit, extra = {}, {}, {}

    def add(book, amount, account_id, emp_name, label, eid):
        if not amount:
            return
        if not account_id:
            raise ValueError(f'الموظف "{emp_name}" مفيهوش حساب "{label}" محدد')
        book[(account_id, eid)] = book.get((account_id, eid), 0.0) + amount

    for it in items:
        n = it.employee.name if it.employee else f"#{it.employee_id}"
        e = it.employee_id
        add(debit, it.extra_allowance, it.extra_allowance_account_id, n, "المخصص الإضافي", e)
        add(debit, it.employer_gosi_amount, it.employer_gosi_expense_account_id, n, "مصروف تأمينات صاحب العمل", e)
        add(credit, it.employer_gosi_amount, it.employer_gosi_payable_account_id, n, "مستحق تأمينات صاحب العمل", e)
        add(debit, it.leave_provision_amount, it.leave_provision_expense_account_id, n, "مصروف مخصص الإجازة", e)
        add(credit, it.leave_provision_amount, it.leave_provision_payable_account_id, n, "مستحق مخصص الإجازة", e)
        add(debit, it.eos_provision_amount, it.eos_provision_expense_account_id, n, "مصروف مخصص نهاية الخدمة", e)
        add(credit, it.eos_provision_amount, it.eos_provision_payable_account_id, n, "مستحق مخصص نهاية الخدمة", e)
        if it.extra_allowance:
            extra[e] = extra.get(e, 0.0) + it.extra_allowance
    if extra and not cfg.salaries_payable_account_id:
        raise ValueError("إعداد حساب الرواتب المستحقة ناقص - راجع الإعدادات المحاسبية")
    lines = [{"account_id": a, "debit": round(v, 2), **_emp_tag(e)} for (a, e), v in debit.items()]
    lines += [{"account_id": a, "credit": round(v, 2), **_emp_tag(e)} for (a, e), v in credit.items()]
    lines += [{"account_id": cfg.salaries_payable_account_id, "credit": round(v, 2), **_emp_tag(e)} for e, v in extra.items()]
    return lines


def _line_sums(lines):
    out = {}
    for ln in lines:
        k = (ln["account_id"] if isinstance(ln, dict) else ln.account_id)
        d = round(float((ln.get("debit") if isinstance(ln, dict) else ln.debit) or 0), 2)
        c = round(float((ln.get("credit") if isinstance(ln, dict) else ln.credit) or 0), 2)
        a = out.setdefault(k, [0.0, 0.0]); a[0] = round(a[0] + d, 2); a[1] = round(a[1] + c, 2)
    return out


def _retag_entry(s, e, cfg):
    """يوزّع/يوسم سطور قيد قديم بالموظف من غير ما يغيّر أي رصيد. بيرجّع True لو اتعدّل، وبيسيب القيد زي ما هو لو الحساب مش مطابق."""
    import re
    st = e.source_type
    if st in ("eos_settlement", "annual_leave_settlement"):
        m = EosSettlement if st == "eos_settlement" else AnnualLeaveSettlement
        rec = s.get(m, e.source_id)
        if not rec:
            return False
        for ln in e.lines:
            ln.partner_type, ln.partner_id = "employee", rec.employee_id
        return True
    expected = None
    if st == "payroll":
        slips = s.query(Payslip).options(joinedload(Payslip.employee)).filter(Payslip.run_id == e.source_id).all()
        expected = _payroll_entry_lines(slips, cfg) if slips else None
    elif st == "allowance_insurance":
        items = s.query(AllowanceInsuranceItem).options(joinedload(AllowanceInsuranceItem.employee)).filter(AllowanceInsuranceItem.run_id == e.source_id).all()
        expected = _allowance_entry_lines(items, cfg) if items else None
    elif st == "payroll_payment":
        mm = re.search(r"PY-\d+", e.description or "")
        pay = s.query(Payment).filter(Payment.number == mm.group(0)).first() if mm else None
        slips = s.query(Payslip).filter(Payslip.payment_id == pay.id).all() if pay else []
        debit_acc = next((l.account_id for l in e.lines if l.debit), None)
        if slips and debit_acc and pay.account_id:
            expected = []
            for p in slips:
                if round(p.net_salary or 0, 2):
                    expected += [{"account_id": debit_acc, "debit": round(p.net_salary, 2), **_emp_tag(p.employee_id)},
                                 {"account_id": pay.account_id, "credit": round(p.net_salary, 2), **_emp_tag(p.employee_id)}]
    if not expected or _line_sums(expected) != _line_sums(e.lines):
        return False
    meta = {l.account_id: (l.branch_id, l.cost_center_id, l.description) for l in e.lines}
    for l in list(e.lines):
        s.delete(l)
    s.flush()
    for ln in expected:
        b, c, d = meta.get(ln["account_id"], (None, None, ""))
        s.add(JournalEntryLine(entry_id=e.id, account_id=ln["account_id"], debit=ln.get("debit", 0.0), credit=ln.get("credit", 0.0),
                               description=d, branch_id=b, cost_center_id=c, partner_type=ln.get("partner_type"), partner_id=ln.get("partner_id")))
    return True


def retag_employee_entries():
    """ترحيل لمرة واحدة (وآمن لو اتكرر): القيود القديمة (رواتب، صرف رواتب، مخصصات، نهاية خدمة، تسوية إجازة) بتتوسم بالموظف
    عشان تظهر في شجرة (الحساب > الموظف > الحركات). مجاميع الحسابات مبتتغيرش، وأي قيد مش مطابق للحساب بيتساب زي ما هو."""
    n = 0
    with get_session() as s:
        cfg = s.get(AccountingSettings, 1)
        if not cfg:
            return 0
        entries = s.query(JournalEntry).options(joinedload(JournalEntry.lines)).filter(
            JournalEntry.source_type.in_(("payroll", "allowance_insurance", "payroll_payment", "eos_settlement", "annual_leave_settlement"))).all()
        for e in entries:
            if any(l.partner_type for l in e.lines):
                continue
            try:
                with s.begin_nested():
                    n += 1 if _retag_entry(s, e, cfg) else 0
            except Exception:
                pass
        s.commit()
    return n


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
        # مينفعش ترحّل شهر وفيه شهر بعده مرحّل لنفس الموظفين
        emp_ids = [eid for (eid,) in s.query(Payslip.employee_id).filter(Payslip.run_id == run.id).all()]
        if emp_ids:
            later = s.query(PayrollRun).join(Payslip, Payslip.run_id == PayrollRun.id).filter(
                PayrollRun.state == "posted", PayrollRun.id != run.id, Payslip.employee_id.in_(emp_ids),
                (PayrollRun.year * 12 + PayrollRun.month) > (run.year * 12 + run.month),
            ).order_by(PayrollRun.year, PayrollRun.month).first()
            if later:
                raise ValueError(f"مينفعش ترحّل رواتب شهر {run.month}/{run.year} لأن رواتب شهر {later.month}/{later.year} (دورة {later.number}) اترحّلت بالفعل")
        payslips = s.query(Payslip).options(joinedload(Payslip.employee)).filter(Payslip.run_id == run.id).all()
        if not payslips:
            raise ValueError("مفيش قسائم رواتب في الدورة دي - تأكد من وجود موظفين نشطين لهم عقود سارية")
        for p in payslips:      # الإجازات اللي اتعتمدت بعد إنشاء الدورة (وتغيّرات العقود) تتحسب قبل الترحيل
            recalc_payslip(s, p, run)
        s.commit()

        cfg = s.get(AccountingSettings, 1)

        lines = _payroll_entry_lines(payslips, cfg)

        total_net = sum(p.net_salary for p in payslips)
        entry_date = datetime.datetime(run.year, run.month, 1)
        run_branch_id = run.branch_id
        run_number, run_month, run_year = run.number, run.month, run.year

        if not cfg.salaries_payable_account_id:
            raise ValueError("إعداد حساب الرواتب المستحقة ناقص - راجع الإعدادات المحاسبية")

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
        employees = s.query(Employee).all()           # غير النشط (عقده اتنهى) بيدخل لو عقده بيغطي الشهر - زي دورة الرواتب
        for emp in employees:
            contract = s.query(Contract).filter(
                Contract.employee_id == emp.id, _contract_state_filter(),
                Contract.start_date <= period_end,
            ).filter((Contract.end_date.is_(None)) | (Contract.end_date >= datetime.datetime(year, month, 1))).order_by(Contract.start_date.desc()).first()
            if not contract:
                continue
            if not emp.is_active and contract.state not in ("terminated", "expired"):
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

        # المخصص الإضافي بيتدفع نقدًا/يضاف على المستحقات - نجمعه في نفس
        # حساب الرواتب المستحقة العام زي صافي الراتب في دورة الرواتب
        cfg = s.get(AccountingSettings, 1)
        lines = _allowance_entry_lines(items, cfg)
        entry_date = datetime.datetime(run.year, run.month, 1)
        run_branch_id = run.branch_id
        run_number, run_month, run_year = run.number, run.month, run.year

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
        slip_nets = [(p.employee_id, p.net_salary or 0.0) for p in unpaid]

    payment_date = payment_date or datetime.datetime.now()
    label = names[0] if len(names) == 1 else f"{len(names)} موظف"
    with get_session() as s:
        pay = Payment(number=_next_payment_number(s, "PY-"), date=payment_date, payment_type="payment",
                      branch_id=branch_id, cost_center_id=cost_center_id, partner_type="payroll", partner_id=run_id_val,
                      amount=round(total_net, 2), account_id=int(cash_account_id),
                      reference=reference or run_number, notes=f"صرف صافي راتب {label} - دورة {run_month}/{run_year} ({pm.name})")
        s.add(pay); s.flush(); pid = pay.id; s.commit()

    pay_lines = []
    for eid_, net_ in slip_nets:
        if round(net_, 2):
            pay_lines += [{"account_id": payable_account_id, "debit": round(net_, 2), **_emp_tag(eid_)},
                          {"account_id": int(cash_account_id), "credit": round(net_, 2), **_emp_tag(eid_)}]
    jid = create_journal_entry(
        pay_lines,
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


def payroll_payments_report(year=None, month=None, status="all", branch_id=None, cost_center_id=None, search=None):
    """تقرير الرواتب لكل الموظفين بالشهور: صف لكل قسيمة (موظف × شهر) مع حالة الصرف.
    status: all / paid / unpaid (غير المدفوع بيشمل قسائم الدورات اللي لسه ما اترحّلتش).
    بيرجّع rows + months (ملخص كل شهر) + totals."""
    require_action("payroll_report", "view")
    today = datetime.date.today()
    year = int(year or today.year)
    if status not in ("all", "paid", "unpaid"):
        raise ValueError("حالة الصرف غير معروفة")
    with get_session() as s:
        q = (s.query(Payslip, PayrollRun, Employee).join(PayrollRun, Payslip.run_id == PayrollRun.id)
             .join(Employee, Payslip.employee_id == Employee.id).filter(PayrollRun.year == year))
        if month:
            q = q.filter(PayrollRun.month == int(month))
        if status == "paid":
            q = q.filter(Payslip.paid_at.isnot(None))
        elif status == "unpaid":
            q = q.filter(Payslip.paid_at.is_(None))
        if branch_id:
            q = q.filter(Employee.branch_id == int(branch_id))
        if cost_center_id:
            q = q.filter(Employee.cost_center_id == int(cost_center_id))
        if search:
            like = f"%{search.strip()}%"
            q = q.filter((Employee.name.like(like)) | (Employee.code.like(like)))
        branches = {b.id: b.name for b in s.query(Branch).all()}
        ccs = {c.id: c.name for c in s.query(CostCenter).all()}
        pays = {p.id: p.number for p in s.query(Payment).filter(Payment.partner_type == "payroll").all()}
        rows, months = [], {}
        for p, r, e in q.order_by(PayrollRun.month, Employee.code).all():
            paid = bool(p.paid_at)
            net = round(p.net_salary or 0, 2)
            rows.append({"payslip_id": p.id, "run_id": r.id, "run_number": r.number, "month": r.month, "year": r.year,
                         "run_posted": r.state == "posted", "employee_id": e.id, "code": e.code, "name": e.name,
                         "branch": branches.get(e.branch_id, "-"), "department": ccs.get(e.cost_center_id, "-"),
                         "net": net, "paid": paid, "paid_at": p.paid_at, "payment_id": p.payment_id if paid else None, "payment_number": pays.get(p.payment_id, "-") if paid else "-"})
            m = months.setdefault(r.month, {"month": r.month, "count": 0, "total": 0.0, "paid": 0.0, "unpaid": 0.0, "posted": r.state == "posted"})
            m["count"] += 1; m["total"] += net
            m["paid" if paid else "unpaid"] += net
    for m in months.values():
        for k in ("total", "paid", "unpaid"):
            m[k] = round(m[k], 2)
    tot = {"count": len(rows), "total": round(sum(r["net"] for r in rows), 2),
           "paid": round(sum(r["net"] for r in rows if r["paid"]), 2), "unpaid": round(sum(r["net"] for r in rows if not r["paid"]), 2)}
    return {"rows": rows, "months": [months[k] for k in sorted(months)], "totals": tot}


def pay_payslips_multi(payslip_ids, payment_method_id, payment_date=None, reference=""):
    """صرف قسائم من تقرير الرواتب (ممكن تكون من أكتر من شهر/دورة): سند وقيد لكل دورة.
    بيتأكد الأول إن كل الدورات مترحّلة عشان ميحصلش صرف جزئي."""
    require_action("payroll_report", "post")
    ids = sorted({int(i) for i in (payslip_ids or [])})
    if not ids:
        raise ValueError("اختار موظف واحد على الأقل للصرف")
    with get_session() as s:
        slips = s.query(Payslip).filter(Payslip.id.in_(ids)).all()
        if len(slips) != len(ids):
            raise ValueError("بعض القسائم المختارة غير موجودة")
        by_run = {}
        for p in slips:
            if not p.paid_at:
                by_run.setdefault(p.run_id, []).append(p.id)
        for rid in by_run:
            r = s.get(PayrollRun, rid)
            if r.state != "posted":
                raise ValueError(f"دورة {r.month}/{r.year} لسه ما اترحّلتش - رحّلها الأول من شاشة الرواتب")
    if not by_run:
        raise ValueError("كل القسائم المختارة اتصرفت بالفعل")
    out = {"payments": [], "amount": 0.0, "employee_count": 0}
    for rid in sorted(by_run):
        res = pay_payslips(by_run[rid], payment_method_id, payment_date=payment_date, reference=reference)
        out["payments"].append(res["payment_number"]); out["amount"] = round(out["amount"] + res["amount"], 2)
        out["employee_count"] += res["employee_count"]
    return out


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
