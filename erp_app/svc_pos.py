"""نقاط البيع (POS): الماكينات، المرتجعات، الجلسات.

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
    APP_DIR,
    KITCHEN_EVENT_KINDS,
    RESTAURANT_ORDER_TYPES,
    _accounting_settings,
    _compute_line_total,
    _kitchen_events_for_invoice,
    _next_code,
    _reference_batch_lines,
    _sales_invoice_location,
    allowed_branch,
    allowed_cost_center,
    create_journal_entry,
    create_sales_invoice,
    create_stock_move,
    current_user,
    default_location_id,
    get_bom_explosion,
    get_company_settings,
    get_payment_method,
    get_product,
    get_sales_invoice,
    is_batch_tracked,
    list_open_restaurant_orders,
    pm_is_cash,
    require_action,
    uses_batch_cost,
)

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
