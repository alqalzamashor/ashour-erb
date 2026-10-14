"""
استيراد وتصدير جماعي للبيانات (أصناف، عملاء، موردين، شجرة حسابات) عن طريق
قوالب Excel - مصمّم عشان يتعامل مع آلاف السجلات دفعة واحدة بدل الإدخال
اليدوي واحد واحد.
"""
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from . import audit
from . import services
from . import field_access as _field_access


# ---- مؤشر تقدّم الاستيراد (للشاشة): الاستيراد الكبير (آلاف الصفوف) بياخد ثواني فنعرض شريط تقدّم بدل ما الشاشة تبان واقفة ----
_PROGRESS = {"cb": None}


def set_progress_callback(fn):
    """fn(done, total) - بتتنادى كل 20 صف أثناء أي استيراد. None = من غير تتبّع."""
    _PROGRESS["cb"] = fn


def _tick(done, total):
    cb = _PROGRESS["cb"]
    if cb and (done % 20 == 0 or done == total):
        try:
            cb(done, total)
        except Exception:
            pass


def _style_header(ws, ncols):
    header_fill = PatternFill(start_color="6C4EE3", end_color="6C4EE3", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for col in range(1, ncols + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width = 20


def _row_values(ws, headers, header_to_field):
    """يبني خريطة عمود -> اسم الحقل من صف العناوين الفعلي في الملف."""
    col_map = {}
    for idx, h in enumerate(headers):
        h = (h or "").strip() if isinstance(h, str) else h
        if h in header_to_field:
            col_map[header_to_field[h]] = idx
    return col_map


def _get(row, col_map, field, default=None):
    idx = col_map.get(field)
    if idx is None or idx >= len(row):
        return default
    v = row[idx]
    return v if v not in (None, "") else default


# ======================================================================
# الأصناف
# ======================================================================
PRODUCT_COLUMNS = [
    ("كود الصنف*", "sku"), ("الاسم*", "name"), ("الفئة", "category"), ("الوحدة", "unit"),
    ("سعر التكلفة", "cost_price"), ("سعر البيع", "sale_price"), ("حد الطلب", "reorder_point"),
    ("نسبة الضريبة %", "tax_rate"), ("نوع الصنف (عادي/Kit/مُصنَّع)", "product_type"),
    ("يُباع (نعم/لا)", "can_be_sold"), ("يُشترى (نعم/لا)", "can_be_purchased"),
    ("طريقة الإخراج (بدون/FIFO/LIFO/الأقرب انتهاءً)", "issue_method"), ("له صلاحية (نعم/لا)", "track_expiry"),
    ("مدة الصلاحية (يوم)", "shelf_life_days"), ("تنبيه قبل الانتهاء (يوم)", "expiry_alert_days"),
    ("طريقة التكلفة (افتراضي/متوسط مرجح/FIFO/LIFO)", "cost_method"),
]

_COST_METHOD_MAP = {"": "", "افتراضي": "auto", "الافتراضي": "auto", "auto": "auto", "متوسط": "avg", "متوسط مرجح": "avg", "المتوسط المرجح": "avg", "avg": "avg", "fifo": "fifo", "lifo": "lifo"}
_COST_METHOD_LABELS = {"auto": "افتراضي", "avg": "متوسط مرجح", "fifo": "FIFO", "lifo": "LIFO"}

_ISSUE_METHOD_MAP = {"بدون": "none", "بدون تتبع": "none", "none": "none", "": "none", "fifo": "fifo", "الأقدم": "fifo", "lifo": "lifo", "الأحدث": "lifo",
                     "fefo": "fefo", "الأقرب انتهاء": "fefo", "الأقرب انتهاءً": "fefo", "الاقرب انتهاء": "fefo", "الأقرب للانتهاء": "fefo"}
_ISSUE_METHOD_LABELS = {"none": "بدون", "fifo": "FIFO", "lifo": "LIFO", "fefo": "الأقرب انتهاءً"}


def _batch_import_values(row, col_map, existing=None):
    """قيم الصلاحية وطريقة الإخراج من صف الاستيراد: (issue_method, track_expiry, shelf_life_days, expiry_alert_days) أو None لو الأعمدة مش في الملف."""
    if not any(k in col_map for k in ("issue_method", "track_expiry", "shelf_life_days", "expiry_alert_days", "cost_method")):
        return None
    c_raw = str(_get(row, col_map, "cost_method") or "").strip().lower()
    if c_raw not in _COST_METHOD_MAP:
        raise ValueError(f'طريقة التكلفة "{c_raw}" غير معروفة - اكتب: افتراضي أو متوسط مرجح أو FIFO أو LIFO')
    cost_method = _COST_METHOD_MAP[c_raw] or ((existing.cost_method or "auto") if existing else "auto")
    m_raw = str(_get(row, col_map, "issue_method") or "").strip().lower()
    if m_raw not in _ISSUE_METHOD_MAP:
        raise ValueError(f'طريقة الإخراج "{m_raw}" غير معروفة - اكتب: بدون أو FIFO أو LIFO أو الأقرب انتهاءً')
    method = _ISSUE_METHOD_MAP[m_raw] if m_raw else (existing.issue_method if existing else "none")
    track = _yes_no(_get(row, col_map, "track_expiry"), bool(existing.track_expiry) if existing else False)
    shelf_raw = _get(row, col_map, "shelf_life_days")
    shelf = int(float(shelf_raw)) if shelf_raw not in (None, "") else (existing.shelf_life_days if existing else None)
    alert_raw = _get(row, col_map, "expiry_alert_days")
    alert = int(float(alert_raw)) if alert_raw not in (None, "") else (existing.expiry_alert_days if existing and existing.expiry_alert_days is not None else 30)
    return services._check_batch_settings(method, track, shelf, alert, cost_method)


def _yes_no(v, default=True):
    """نعم/لا (أو yes/no/1/0/true/false/صح/خطأ) -> bool. الفاضي = القيمة الافتراضية."""
    if v is None or str(v).strip() == "":
        return default
    t = str(v).strip().lower()
    if t in ("نعم", "yes", "y", "1", "true", "صح", "اه", "أيوه", "ايوه", "✓"):
        return True
    if t in ("لا", "no", "n", "0", "false", "خطأ", "خطا", "✗"):
        return False
    raise ValueError(f'القيمة "{v}" مش مفهومة - اكتب نعم أو لا')
_PRODUCT_TYPE_MAP = {"عادي": "simple", "kit": "kit", "Kit": "kit", "مصنع": "manufactured",
                      "مُصنَّع": "manufactured", "manufactured": "manufactured", "simple": "simple"}
_PRODUCT_TYPE_LABELS = {"simple": "عادي", "kit": "Kit", "manufactured": "مُصنَّع"}


def generate_product_template(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "أصناف"
    headers = [c[0] for c in PRODUCT_COLUMNS]
    ws.append(headers)
    _style_header(ws, len(headers))
    ws.append(["P001", "أرز بسمتي 5 كيلو", "مواد غذائية", "كيس", 25, 35, 10, 15, "عادي", "نعم", "نعم", "الأقرب انتهاءً", "نعم", 365, 30, "متوسط مرجح"])
    ws2 = wb.create_sheet("تعليمات")
    ws2.column_dimensions["A"].width = 90
    for line in [
        "الحقول اللي عليها * إجبارية (كود الصنف والاسم).",
        "كود الصنف: لو موجود بالفعل هيتحدّث بياناته، لو جديد هيتعمل صنف جديد.",
        "الفئة: لو مكتوبة ومش موجودة، هتتعمل تلقائياً.",
        "نوع الصنف: اكتب عادي أو Kit أو مُصنَّع - لو سبته فاضي هيبقى عادي.",
        "يُباع / يُشترى: اكتب نعم أو لا. \"يُباع\" = بيظهر في فواتير المبيعات والكاشير، و\"يُشترى\" = بيظهر في فواتير المشتريات وسندات الاستلام. الفاضي = نعم.",
        "طريقة الإخراج: بدون (الافتراضي) أو FIFO (الأقدم دخولًا أولًا) أو LIFO (الأحدث دخولًا أولًا) أو الأقرب انتهاءً. غير \"بدون\" = بيتتبّع التشغيلات لكل استلام.",
        "له صلاحية: نعم = بيطلب تاريخ الصلاحية عند الاستلام. مدة الصلاحية (يوم) اختيارية: بتتعبّى تلقائي في الاستلام والإنتاج. التنبيه قبل الانتهاء الافتراضي 30 يوم.",
        "احذف صف المثال (الصف التاني) قبل ما تملأ بياناتك الحقيقية، أو سيبه هيتحدّث زي أي صنف عادي.",
    ]:
        ws2.append([line])
    wb.save(output_path)
    return output_path


def export_products(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "أصناف"
    headers = [c[0] for c in PRODUCT_COLUMNS]
    ws.append(headers)
    _style_header(ws, len(headers))
    for p in services.list_products(active_only=False):
        cat_name = p.category.name if p.category else ""
        ws.append([p.sku, p.name, cat_name, p.unit, (p.cost_price if _field_access.can_see('cost_price') else None), p.sale_price, p.reorder_point,
                   p.tax_rate, _PRODUCT_TYPE_LABELS.get(p.product_type, "عادي"),
                   "نعم" if p.can_be_sold else "لا", "نعم" if p.can_be_purchased else "لا",
                   _ISSUE_METHOD_LABELS.get(p.issue_method or "none", "بدون"), "نعم" if p.track_expiry else "لا", p.shelf_life_days or "", p.expiry_alert_days if p.expiry_alert_days is not None else 30,
                   _COST_METHOD_LABELS.get(p.cost_method or "auto", "افتراضي")])
    wb.save(output_path)
    return output_path


@audit.audited_bulk("استيراد أصناف")
def import_products(file_path):
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.worksheets[0]
    headers = [c.value for c in ws[1]]
    col_map = _row_values(ws, headers, dict(PRODUCT_COLUMNS))

    created = updated = 0
    errors = []
    category_cache = {c.name: c.id for c in services.list_categories()}

    for row_idx in range(2, ws.max_row + 1):

        _tick(row_idx - 1, ws.max_row - 1)
        row = [c.value for c in ws[row_idx]]
        if all(v in (None, "") for v in row):
            continue
        try:
            sku = str(_get(row, col_map, "sku") or "").strip()
            name = str(_get(row, col_map, "name") or "").strip()
            if not sku or not name:
                raise ValueError("كود الصنف والاسم مطلوبين")

            cat_name = str(_get(row, col_map, "category") or "").strip()
            category_id = None
            if cat_name:
                if cat_name not in category_cache:
                    category_cache[cat_name] = services.create_category(cat_name)
                category_id = category_cache[cat_name]

            unit = str(_get(row, col_map, "unit") or "قطعة").strip()
            cost_price = float(_get(row, col_map, "cost_price") or 0)
            sale_price = float(_get(row, col_map, "sale_price") or 0)
            reorder_point = float(_get(row, col_map, "reorder_point") or 0)
            tax_rate = float(_get(row, col_map, "tax_rate") or 15)
            product_type = _PRODUCT_TYPE_MAP.get(str(_get(row, col_map, "product_type") or "عادي").strip(), "simple")
            sold_raw = _get(row, col_map, "can_be_sold"); purch_raw = _get(row, col_map, "can_be_purchased")
            batch_vals = _batch_import_values(row, col_map, services.get_product_by_sku(sku))

            existing = services.get_product_by_sku(sku)
            if existing:
                services.update_product(
                    existing.id, name=name, category_id=category_id or existing.category_id,
                    unit=unit, cost_price=cost_price, sale_price=sale_price,
                    reorder_point=reorder_point, tax_rate=tax_rate, product_type=product_type,
                    can_be_sold=_yes_no(sold_raw, bool(existing.can_be_sold)), can_be_purchased=_yes_no(purch_raw, bool(existing.can_be_purchased)),
                    **({"issue_method": batch_vals[0], "track_expiry": batch_vals[1], "shelf_life_days": batch_vals[2], "expiry_alert_days": batch_vals[3], "cost_method": batch_vals[4]} if batch_vals else {}),
                )
                updated += 1
            else:
                services.create_product(sku, name, category_id=category_id, unit=unit,
                                         cost_price=cost_price, sale_price=sale_price,
                                         reorder_point=reorder_point, tax_rate=tax_rate,
                                         can_be_sold=_yes_no(sold_raw, True), can_be_purchased=_yes_no(purch_raw, True),
                                         **({"issue_method": batch_vals[0], "track_expiry": batch_vals[1], "shelf_life_days": batch_vals[2], "expiry_alert_days": batch_vals[3], "cost_method": batch_vals[4]} if batch_vals else {}))
                if product_type != "simple":
                    p = services.get_product_by_sku(sku)
                    services.update_product(p.id, product_type=product_type)
                created += 1
        except Exception as ex:
            errors.append((row_idx, str(ex)))

    return {"created": created, "updated": updated, "errors": errors}


# ======================================================================
# العملاء
# ======================================================================
CUSTOMER_COLUMNS = [("الاسم*", "name"), ("الهاتف", "phone"), ("البريد الإلكتروني", "email"),
                     ("الرقم الضريبي", "vat_number"), ("العنوان", "address")]


def generate_customer_template(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "عملاء"
    headers = [c[0] for c in CUSTOMER_COLUMNS]
    ws.append(headers)
    _style_header(ws, len(headers))
    ws.append(["محمد عبدالله", "0555555555", "mohamed@example.com", "300000000000003", "الرياض"])
    wb.save(output_path)
    return output_path


def export_customers(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "عملاء"
    headers = [c[0] for c in CUSTOMER_COLUMNS]
    ws.append(headers)
    _style_header(ws, len(headers))
    for c in services.list_customers():
        ws.append([c.name, c.phone or "", getattr(c, "email", "") or "", c.vat_number or "", c.address or ""])
    wb.save(output_path)
    return output_path


@audit.audited_bulk("استيراد عملاء")
def import_customers(file_path):
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.worksheets[0]
    headers = [c.value for c in ws[1]]
    col_map = _row_values(ws, headers, dict(CUSTOMER_COLUMNS))
    created = updated = 0
    errors = []
    for row_idx in range(2, ws.max_row + 1):
        _tick(row_idx - 1, ws.max_row - 1)
        row = [c.value for c in ws[row_idx]]
        if all(v in (None, "") for v in row):
            continue
        try:
            name = str(_get(row, col_map, "name") or "").strip()
            if not name:
                raise ValueError("اسم العميل مطلوب")
            fields = dict(
                phone=str(_get(row, col_map, "phone") or ""),
                email=str(_get(row, col_map, "email") or ""),
                vat_number=str(_get(row, col_map, "vat_number") or ""),
                address=str(_get(row, col_map, "address") or ""),
            )
            existing = services.get_customer_by_name(name)
            if existing:
                services.update_customer(existing.id, **fields)
                updated += 1
            else:
                services.create_customer(name, **fields)
                created += 1
        except Exception as ex:
            errors.append((row_idx, str(ex)))
    return {"created": created, "updated": updated, "errors": errors}


# ======================================================================
# الموردون
# ======================================================================
SUPPLIER_COLUMNS = [("الاسم*", "name"), ("الهاتف", "phone"), ("الرقم الضريبي", "vat_number"), ("العنوان", "address")]


def generate_supplier_template(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "موردون"
    headers = [c[0] for c in SUPPLIER_COLUMNS]
    ws.append(headers)
    _style_header(ws, len(headers))
    ws.append(["شركة التوريدات المتحدة", "0114445555", "300000000000004", "جدة"])
    wb.save(output_path)
    return output_path


def export_suppliers(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "موردون"
    headers = [c[0] for c in SUPPLIER_COLUMNS]
    ws.append(headers)
    _style_header(ws, len(headers))
    for s in services.list_suppliers():
        ws.append([s.name, s.phone or "", s.vat_number or "", s.address or ""])
    wb.save(output_path)
    return output_path


@audit.audited_bulk("استيراد موردين")
def import_suppliers(file_path):
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.worksheets[0]
    headers = [c.value for c in ws[1]]
    col_map = _row_values(ws, headers, dict(SUPPLIER_COLUMNS))
    created = updated = 0
    errors = []
    for row_idx in range(2, ws.max_row + 1):
        _tick(row_idx - 1, ws.max_row - 1)
        row = [c.value for c in ws[row_idx]]
        if all(v in (None, "") for v in row):
            continue
        try:
            name = str(_get(row, col_map, "name") or "").strip()
            if not name:
                raise ValueError("اسم المورد مطلوب")
            fields = dict(
                phone=str(_get(row, col_map, "phone") or ""),
                vat_number=str(_get(row, col_map, "vat_number") or ""),
                address=str(_get(row, col_map, "address") or ""),
            )
            existing = services.get_supplier_by_name(name)
            if existing:
                services.update_supplier(existing.id, **fields)
                updated += 1
            else:
                services.create_supplier(name, **fields)
                created += 1
        except Exception as ex:
            errors.append((row_idx, str(ex)))
    return {"created": created, "updated": updated, "errors": errors}


# ======================================================================
# شجرة الحسابات
# ======================================================================
ACCOUNT_COLUMNS = [("الكود*", "code"), ("الاسم*", "name"), ("النوع* (أصول/التزامات/حقوق ملكية/إيرادات/مصروفات)", "account_type"),
                    ("كود الحساب الأب", "parent_code"), ("نوع التدفق النقدي (نقدية/تشغيلي/استثماري/تمويلي)", "cash_flow_type")]
_ACCOUNT_TYPE_MAP = {"أصول": "asset", "التزامات": "liability", "حقوق ملكية": "equity", "إيرادات": "income", "مصروفات": "expense",
                      "asset": "asset", "liability": "liability", "equity": "equity", "income": "income", "expense": "expense"}
_ACCOUNT_TYPE_LABELS = {"asset": "أصول", "liability": "التزامات", "equity": "حقوق ملكية", "income": "إيرادات", "expense": "مصروفات"}
_CF_TYPE_MAP = {"نقدية": "cash", "تشغيلي": "operating", "استثماري": "investing", "تمويلي": "financing",
                "cash": "cash", "operating": "operating", "investing": "investing", "financing": "financing"}
_CF_TYPE_LABELS = {"cash": "نقدية", "operating": "تشغيلي", "investing": "استثماري", "financing": "تمويلي"}


def generate_account_template(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "شجرة الحسابات"
    headers = [c[0] for c in ACCOUNT_COLUMNS]
    ws.append(headers)
    _style_header(ws, len(headers))
    ws.append(["1150", "بنك الأهلي - حساب جاري", "أصول", "1100", "نقدية"])
    ws2 = wb.create_sheet("تعليمات")
    ws2.column_dimensions["A"].width = 90
    for line in [
        "الحقول عليها * إجبارية.",
        "كود الحساب الأب اختياري - لو محدد، لازم يكون كود حساب موجود بالفعل (أو مستورد في صف سابق بنفس الملف).",
        "رتّب الصفوف بحيث الحساب الأب يظهر قبل أبنائه في الملف.",
        "نوع التدفق النقدي اختياري - سيبه فاضي لو مش عايز تصنّفه.",
    ]:
        ws2.append([line])
    wb.save(output_path)
    return output_path


def export_accounts(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "شجرة الحسابات"
    headers = [c[0] for c in ACCOUNT_COLUMNS]
    ws.append(headers)
    _style_header(ws, len(headers))
    accounts = services.list_accounts()
    by_id = {a.id: a for a in accounts}
    for a in accounts:
        parent_code = by_id[a.parent_id].code if a.parent_id and a.parent_id in by_id else ""
        ws.append([a.code, a.name, _ACCOUNT_TYPE_LABELS.get(a.account_type, a.account_type), parent_code,
                   _CF_TYPE_LABELS.get(a.cash_flow_type, "") if a.cash_flow_type else ""])
    wb.save(output_path)
    return output_path


@audit.audited_bulk("استيراد حسابات")
def import_accounts(file_path):
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.worksheets[0]
    headers = [c.value for c in ws[1]]
    col_map = _row_values(ws, headers, dict(ACCOUNT_COLUMNS))
    created = updated = 0
    errors = []
    code_cache = {a.code: a.id for a in services.list_accounts()}

    for row_idx in range(2, ws.max_row + 1):

        _tick(row_idx - 1, ws.max_row - 1)
        row = [c.value for c in ws[row_idx]]
        if all(v in (None, "") for v in row):
            continue
        try:
            code = str(_get(row, col_map, "code") or "").strip()
            name = str(_get(row, col_map, "name") or "").strip()
            type_raw = str(_get(row, col_map, "account_type") or "").strip()
            if not code or not name or not type_raw:
                raise ValueError("الكود والاسم والنوع مطلوبين")
            account_type = _ACCOUNT_TYPE_MAP.get(type_raw)
            if not account_type:
                raise ValueError(f'نوع الحساب "{type_raw}" غير معروف')

            parent_code = str(_get(row, col_map, "parent_code") or "").strip()
            parent_id = code_cache.get(parent_code) if parent_code else None
            if parent_code and not parent_id:
                raise ValueError(f'كود الحساب الأب "{parent_code}" غير موجود - تأكد إنه ظهر في صف سابق')

            cf_raw = str(_get(row, col_map, "cash_flow_type") or "").strip()
            cash_flow_type = _CF_TYPE_MAP.get(cf_raw) if cf_raw else None

            existing_id = code_cache.get(code)
            if existing_id:
                services.update_account(existing_id, name=name, account_type=account_type,
                                         parent_id=parent_id, cash_flow_type=cash_flow_type)
                updated += 1
            else:
                new_id = services.create_account(code, name, account_type, parent_id=parent_id, cash_flow_type=cash_flow_type)
                code_cache[code] = new_id
                created += 1
        except Exception as ex:
            errors.append((row_idx, str(ex)))
    return {"created": created, "updated": updated, "errors": errors}


# ======================================================================
# سجل الأنواع المدعومة - تُستخدم من شاشة الاستيراد/التصدير
# ======================================================================
ENTITY_SPECS = {
    "products": {"label": "الأصناف", "template": generate_product_template, "export": export_products, "import": import_products},
    "customers": {"label": "العملاء", "template": generate_customer_template, "export": export_customers, "import": import_customers},
    "suppliers": {"label": "الموردون", "template": generate_supplier_template, "export": export_suppliers, "import": import_suppliers},
    "accounts": {"label": "شجرة الحسابات", "template": generate_account_template, "export": export_accounts, "import": import_accounts},
}


# ======================================================================
# القيود / اليومية العامة (كل سطر = بند واحد ضمن قيد، الصفوف اللي ليها
# نفس "مرجع التجميع" بتتجمّع في قيد واحد)
# ======================================================================
JOURNAL_COLUMNS = [
    ("مرجع التجميع*", "group_ref"), ("التاريخ* (YYYY-MM-DD)", "date"), ("البيان", "description"),
    ("كود الحساب*", "account_code"), ("مدين", "debit"), ("دائن", "credit"),
    ("اسم الفرع", "branch"), ("اسم مركز التكلفة", "cost_center"),
]


def generate_journal_template(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "قيود"
    headers = [c[0] for c in JOURNAL_COLUMNS]
    ws.append(headers)
    _style_header(ws, len(headers))
    ws.append(["JE-001", "2026-01-15", "قيد افتتاحي", "1100", 5000, 0, "", ""])
    ws.append(["JE-001", "2026-01-15", "قيد افتتاحي", "3200", 0, 5000, "", ""])
    ws2 = wb.create_sheet("تعليمات")
    ws2.column_dimensions["A"].width = 90
    for line in [
        "الحقول عليها * إجبارية.",
        "مرجع التجميع: اكتب نفس القيمة لكل سطور القيد الواحد (كل صفوف نفس القيد لازم يكون ليها نفس مرجع التجميع).",
        "كود الحساب لازم يكون حساب فرعي موجود بالفعل في شجرة الحسابات.",
        "كل سطر يكون مدين أو دائن بس، مش الاتنين مع بعض.",
        "مجموع المدين لازم يساوي مجموع الدائن لكل قيد (نفس مرجع التجميع) وإلا هيترفض القيد كامل.",
    ]:
        ws2.append([line])
    wb.save(output_path)
    return output_path


def export_journal(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "قيود"
    headers = [c[0] for c in JOURNAL_COLUMNS]
    ws.append(headers)
    _style_header(ws, len(headers))
    for entry in services.list_journal_entries(limit=5000):
        for ln in entry.lines:
            ws.append([
                entry.reference or entry.number, entry.date.strftime("%Y-%m-%d"), ln.description or entry.description or "",
                ln.account.code if ln.account else "", ln.debit or 0, ln.credit or 0,
                entry.branch.name if entry.branch else "", "",
            ])
    wb.save(output_path)
    return output_path


@audit.audited_bulk("استيراد قيود")
def import_journal(file_path):
    import datetime
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.worksheets[0]
    headers = [c.value for c in ws[1]]
    col_map = _row_values(ws, headers, dict(JOURNAL_COLUMNS))

    groups = {}
    order = []
    for row_idx in range(2, ws.max_row + 1):
        _tick(row_idx - 1, ws.max_row - 1)
        row = [c.value for c in ws[row_idx]]
        if all(v in (None, "") for v in row):
            continue
        ref = str(_get(row, col_map, "group_ref") or "").strip()
        if not ref:
            continue
        groups.setdefault(ref, {"rows": [], "first_row": row_idx})
        groups[ref]["rows"].append((row_idx, row))
        if ref not in order:
            order.append(ref)

    created = 0
    errors = []
    branches = {b.name: b.id for b in services.list_branches(True)}
    centers = {c.name: c.id for c in services.list_cost_centers(True)}

    for ref in order:
        rows = groups[ref]["rows"]
        try:
            lines = []
            entry_date = None
            description = ""
            branch_id = None
            cost_center_id = None
            for row_idx, row in rows:
                code = str(_get(row, col_map, "account_code") or "").strip()
                if not code:
                    raise ValueError(f"صف {row_idx}: كود الحساب مطلوب")
                account = services.get_account_by_code(code)
                if not account:
                    raise ValueError(f"صف {row_idx}: كود الحساب \"{code}\" غير موجود")
                debit = float(_get(row, col_map, "debit") or 0)
                credit = float(_get(row, col_map, "credit") or 0)
                description = str(_get(row, col_map, "description") or description or "")
                date_raw = _get(row, col_map, "date")
                if date_raw and not entry_date:
                    entry_date = date_raw if isinstance(date_raw, datetime.datetime) else datetime.datetime.strptime(str(date_raw).strip(), "%Y-%m-%d")
                branch_name = str(_get(row, col_map, "branch") or "").strip()
                if branch_name and branch_name in branches:
                    branch_id = branches[branch_name]
                cc_name = str(_get(row, col_map, "cost_center") or "").strip()
                if cc_name and cc_name in centers:
                    cost_center_id = centers[cc_name]
                lines.append({"account_id": account.id, "debit": debit, "credit": credit, "description": description})

            services.create_journal_entry(lines, reference=ref, description=description, entry_date=entry_date,
                                           branch_id=branch_id, cost_center_id=cost_center_id)
            created += 1
        except Exception as ex:
            errors.append((rows[0][0], f'القيد "{ref}": {ex}'))

    return {"created": created, "updated": 0, "errors": errors}


# ======================================================================
# التسويات الجردية (كل سطر = صنف واحد ضمن تسوية، الصفوف اللي ليها نفس
# "مرجع التجميع + المخزن" بتتجمّع في تسوية واحدة)
# ======================================================================
ADJUSTMENT_COLUMNS = [
    ("مرجع التجميع*", "group_ref"), ("اسم المخزن*", "location"), ("كود الصنف*", "sku"),
    ("الكمية الفعلية بعد الجرد*", "counted_qty"), ("ملاحظات", "notes"),
]


def generate_adjustment_template(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "تسويات جردية"
    headers = [c[0] for c in ADJUSTMENT_COLUMNS]
    ws.append(headers)
    _style_header(ws, len(headers))
    ws.append(["ADJ-2026-01", "المخزن الرئيسي", "P001", 48, "جرد نهاية الشهر"])
    ws.append(["ADJ-2026-01", "المخزن الرئيسي", "P002", 20, "جرد نهاية الشهر"])
    ws2 = wb.create_sheet("تعليمات")
    ws2.column_dimensions["A"].width = 90
    for line in [
        "الحقول عليها * إجبارية.",
        "مرجع التجميع: اكتب نفس القيمة لكل أصناف نفس عملية الجرد (تتجمّع مع بعض في تسوية واحدة لنفس المخزن).",
        "الكمية الفعلية بعد الجرد: هي العدد اللي عددته فعليًا في المخزن - النظام هيحسب الفرق تلقائيًا عن الرصيد النظري ويسجّله.",
    ]:
        ws2.append([line])
    wb.save(output_path)
    return output_path


def export_adjustments(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "تسويات جردية"
    headers = ["مرجع التسوية", "اسم المخزن", "كود الصنف", "الرصيد النظري", "الكمية الفعلية", "الفرق", "ملاحظات", "التاريخ"]
    ws.append(headers)
    _style_header(ws, len(headers))
    for adj in services.list_inventory_adjustments(limit=2000):
        for ln in adj.lines:
            ws.append([adj.number, adj.location.name if adj.location else "", ln.product.sku if ln.product else "",
                       ln.theoretical_qty, ln.counted_qty, ln.difference_qty, adj.notes or "", adj.date.strftime("%Y-%m-%d")])
    wb.save(output_path)
    return output_path


@audit.audited_bulk("استيراد تسويات جرد")
def import_adjustments(file_path):
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.worksheets[0]
    headers = [c.value for c in ws[1]]
    col_map = _row_values(ws, headers, dict(ADJUSTMENT_COLUMNS))

    groups = {}
    order = []
    for row_idx in range(2, ws.max_row + 1):
        _tick(row_idx - 1, ws.max_row - 1)
        row = [c.value for c in ws[row_idx]]
        if all(v in (None, "") for v in row):
            continue
        ref = str(_get(row, col_map, "group_ref") or "").strip()
        loc_name = str(_get(row, col_map, "location") or "").strip()
        if not ref or not loc_name:
            continue
        key = (ref, loc_name)
        groups.setdefault(key, {"rows": []})
        groups[key]["rows"].append((row_idx, row))
        if key not in order:
            order.append(key)

    locations = {l.name: l.id for l in services.list_locations()}
    created = 0
    errors = []

    for key in order:
        ref, loc_name = key
        rows = groups[key]["rows"]
        try:
            location_id = locations.get(loc_name)
            if not location_id:
                raise ValueError(f'المخزن "{loc_name}" غير موجود')
            counts = {}
            notes = ""
            for row_idx, row in rows:
                sku = str(_get(row, col_map, "sku") or "").strip()
                if not sku:
                    raise ValueError(f"صف {row_idx}: كود الصنف مطلوب")
                product = services.get_product_by_sku(sku)
                if not product:
                    raise ValueError(f'صف {row_idx}: الصنف "{sku}" غير موجود')
                counted_qty = _get(row, col_map, "counted_qty")
                if counted_qty is None:
                    raise ValueError(f"صف {row_idx}: الكمية الفعلية مطلوبة")
                counts[product.id] = float(counted_qty)
                notes = str(_get(row, col_map, "notes") or notes or "")
            services.create_inventory_adjustment(location_id, counts, notes=notes)
            created += 1
        except Exception as ex:
            errors.append((rows[0][0], f'التسوية "{ref}": {ex}'))

    return {"created": created, "updated": 0, "errors": errors}


# ======================================================================
# معامل تحويل الأصناف (وحدات القياس لكل صنف) - كل سطر = وحدة واحدة
# لصنف، والصفوف اللي ليها نفس كود الصنف بتتجمّع مع بعض
# ======================================================================
UNIT_FACTOR_COLUMNS = [
    ("كود الصنف*", "sku"), ("اسم الوحدة*", "unit_name"), ("معامل التحويل للوحدة الأساسية*", "factor"),
    ("سعر البيع للوحدة", "sale_price"), ("سعر التكلفة للوحدة", "cost_price"), ("باركود", "barcode"),
    ("افتراضية (نعم/لا)", "is_default"),
]


def generate_unit_factor_template(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "معاملات التحويل"
    headers = [c[0] for c in UNIT_FACTOR_COLUMNS]
    ws.append(headers)
    _style_header(ws, len(headers))
    ws.append(["P001", "قطعة", 1, 5, 3, "", "نعم"])
    ws.append(["P001", "كرتونة", 24, 110, 70, "", "لا"])
    ws2 = wb.create_sheet("تعليمات")
    ws2.column_dimensions["A"].width = 90
    for line in [
        "الحقول عليها * إجبارية.",
        "كود الصنف: لازم يكون صنف موجود بالفعل (استورد الأصناف الأول لو محتاج).",
        "معامل التحويل: عدد الوحدات الأساسية داخل الوحدة دي (مثال: كرتونة فيها 24 قطعة = معامل 24).",
        "اسم الوحدة: لو مش موجودة في قائمة وحدات القياس هتتعمل تلقائياً.",
        "افتراضية: اكتب نعم لوحدة واحدة بس لكل صنف (هي اللي هتظهر افتراضيًا وقت البيع).",
        "الاستيراد بيستبدل كل وحدات الصنف الحالية بالكامل بالوحدات المذكورة في الملف لنفس كود الصنف.",
    ]:
        ws2.append([line])
    wb.save(output_path)
    return output_path


def export_unit_factors(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "معاملات التحويل"
    headers = [c[0] for c in UNIT_FACTOR_COLUMNS]
    ws.append(headers)
    _style_header(ws, len(headers))
    for p in services.list_products(active_only=False):
        for ln in services.list_product_units(p.id):
            ws.append([p.sku, ln.unit.name if ln.unit else "", ln.factor_to_base,
                       ln.sale_price or 0, ((ln.cost_price or 0) if _field_access.can_see('cost_price') else None), ln.barcode or "", "نعم" if ln.is_default else "لا"])
    wb.save(output_path)
    return output_path


@audit.audited_bulk("استيراد معاملات وحدات")
def import_unit_factors(file_path):
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.worksheets[0]
    headers = [c.value for c in ws[1]]
    col_map = _row_values(ws, headers, dict(UNIT_FACTOR_COLUMNS))

    groups = {}
    order = []
    for row_idx in range(2, ws.max_row + 1):
        _tick(row_idx - 1, ws.max_row - 1)
        row = [c.value for c in ws[row_idx]]
        if all(v in (None, "") for v in row):
            continue
        sku = str(_get(row, col_map, "sku") or "").strip()
        if not sku:
            continue
        groups.setdefault(sku, []).append((row_idx, row))
        if sku not in order:
            order.append(sku)

    unit_cache = {u.name: u.id for u in services.list_units()}
    updated = 0
    errors = []

    for sku in order:
        rows = groups[sku]
        try:
            product = services.get_product_by_sku(sku)
            if not product:
                raise ValueError(f'الصنف "{sku}" غير موجود')
            unit_lines = []
            for row_idx, row in rows:
                unit_name = str(_get(row, col_map, "unit_name") or "").strip()
                if not unit_name:
                    raise ValueError(f"صف {row_idx}: اسم الوحدة مطلوب")
                if unit_name not in unit_cache:
                    unit_cache[unit_name] = services.create_unit(unit_name)
                factor = float(_get(row, col_map, "factor") or 0)
                if factor <= 0:
                    raise ValueError(f"صف {row_idx}: معامل التحويل يجب أن يكون أكبر من صفر")
                is_default_raw = str(_get(row, col_map, "is_default") or "").strip()
                unit_lines.append({
                    "unit_id": unit_cache[unit_name], "factor_to_base": factor,
                    "sale_price": float(_get(row, col_map, "sale_price") or 0),
                    "cost_price": float(_get(row, col_map, "cost_price") or 0),
                    "barcode": str(_get(row, col_map, "barcode") or ""),
                    "is_default": is_default_raw in ("نعم", "Yes", "yes", "true", "True", "1"),
                })
            services.save_product_units(product.id, unit_lines)
            updated += 1
        except Exception as ex:
            errors.append((rows[0][0], f'الصنف "{sku}": {ex}'))

    return {"created": 0, "updated": updated, "errors": errors}


ENTITY_SPECS.update({
    "journal": {"label": "القيود / اليومية العامة", "template": generate_journal_template, "export": export_journal, "import": import_journal},
    "adjustments": {"label": "التسويات الجردية", "template": generate_adjustment_template, "export": export_adjustments, "import": import_adjustments},
    "unit_factors": {"label": "معامل تحويل الأصناف", "template": generate_unit_factor_template, "export": export_unit_factors, "import": import_unit_factors},
})


# ======================================================================
# وحدات القياس (القائمة الرئيسية للوحدات زي "قطعة"، "كرتون"، "كيلو" -
# منفصلة عن معاملات التحويل الخاصة بكل صنف)
# ======================================================================
UNIT_COLUMNS = [("اسم الوحدة*", "name")]


def generate_unit_template(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "وحدات القياس"
    headers = [c[0] for c in UNIT_COLUMNS]
    ws.append(headers)
    _style_header(ws, len(headers))
    for example in ["قطعة", "كرتون", "كيلوجرام"]:
        ws.append([example])
    ws2 = wb.create_sheet("تعليمات")
    ws2.column_dimensions["A"].width = 90
    ws2.append(["اسم الوحدة إجباري ولازم يكون فريد - لو موجود بالفعل، الصف بيتجاهل بهدوء (مفيش تكرار)."])
    ws2.append(["دي القائمة الرئيسية لأسماء الوحدات بس (زي قطعة، كرتون، كيلو). لتحديد معامل التحويل والأسعار لكل صنف، استخدم قالب \"معامل تحويل الأصناف\"."])
    wb.save(output_path)
    return output_path


def export_units(output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "وحدات القياس"
    headers = [c[0] for c in UNIT_COLUMNS]
    ws.append(headers)
    _style_header(ws, len(headers))
    for u in services.list_units():
        ws.append([u.name])
    wb.save(output_path)
    return output_path


@audit.audited_bulk("استيراد وحدات")
def import_units(file_path):
    wb = openpyxl.load_workbook(file_path, data_only=True)
    ws = wb.worksheets[0]
    headers = [c.value for c in ws[1]]
    col_map = _row_values(ws, headers, dict(UNIT_COLUMNS))

    created = 0
    errors = []
    existing = {u.name for u in services.list_units()}

    for row_idx in range(2, ws.max_row + 1):

        _tick(row_idx - 1, ws.max_row - 1)
        row = [c.value for c in ws[row_idx]]
        if all(v in (None, "") for v in row):
            continue
        try:
            name = str(_get(row, col_map, "name") or "").strip()
            if not name:
                raise ValueError("اسم الوحدة مطلوب")
            if name in existing:
                continue  # موجودة بالفعل - تجاهل بهدوء (مفيش داعي لسجل خطأ)
            services.create_unit(name)
            existing.add(name)
            created += 1
        except Exception as ex:
            errors.append((row_idx, str(ex)))

    return {"created": created, "updated": 0, "errors": errors}


ENTITY_SPECS.update({
    "units": {"label": "وحدات القياس", "template": generate_unit_template, "export": export_units, "import": import_units},
})


# توسيع الاستيراد والتصدير ليغطي باقي جداول النظام (بيتسجّل في ENTITY_SPECS)
from . import import_export_ext  # noqa: E402,F401
