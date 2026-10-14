"""البداية السريعة: قائمة خطوات تشغيل للمدير (بتتعلّم تلقائيًا من حالة النظام) + تحميل بيانات تجريبية على قاعدة فاضية (للتجربة والتدريب).
البيانات التجريبية بتتحذف بشاشة «تنظيف قاعدة البيانات» (مع خيار البيانات الأساسية)."""
import datetime
import json
import os
import random

from .db import APP_DIR

PATH = os.path.join(APP_DIR, "onboarding.json")


def _state():
    try:
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def dismissed():
    return bool(_state().get("dismissed"))


def dismiss(flag=True):
    st = _state(); st["dismissed"] = bool(flag)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(st, f)


def has_activity():
    from .db import PurchaseInvoice, SalesInvoice, get_session
    with get_session() as s:
        return bool(s.query(SalesInvoice.id).first() or s.query(PurchaseInvoice.id).first())


def steps():
    """[{key, label, done, goto}] - goto = مفتاح الشاشة اللي تحل الخطوة."""
    from . import backup, services, twofa
    from .db import Customer, Product, SalesInvoice, User, get_session
    co = services.get_company_settings()
    with get_session() as s:
        n_prod = s.query(Product.id).count()
        n_cust = s.query(Customer.id).count()
        n_sales = s.query(SalesInvoice.id).count()
        n_users = s.query(User.id).filter(User.is_active.is_(True)).count()
    me = services._get_user() or {}
    try:
        two = twofa.is_enabled(me["id"]) if me.get("id") else True
    except Exception:      # noqa: BLE001
        two = True
    return [
        {"key": "company", "label": "اكتب اسم الشركة والرقم الضريبي والعنوان", "done": bool(co.name and co.name != "اسم الشركة" and co.vat_number), "goto": "settings"},
        {"key": "products", "label": "أضف أول أصناف (أو استورد من إكسل)", "done": n_prod > 0, "goto": "products"},
        {"key": "customers", "label": "أضف عملاء", "done": n_cust > 1, "goto": "customers"},
        {"key": "sale", "label": "اعمل أول فاتورة بيع", "done": n_sales > 0, "goto": "sales_invoices"},
        {"key": "users", "label": "ضيف موظفيك بصلاحياتهم", "done": n_users > 1, "goto": "organization"},
        {"key": "backup", "label": "اعمل أول نسخة احتياطية", "done": backup.last_backup_time() is not None, "goto": "backup"},
        {"key": "twofa", "label": "فعّل التحقق بخطوتين لحسابك (الدرع فوق)", "done": bool(two), "goto": None},
    ]


def progress():
    st = steps()
    return sum(1 for x in st if x["done"]), len(st)


def load_demo(seed=7):
    """بيانات تجريبية: تصنيفات وأصناف وعملاء وموردين وفاتورة شراء وفواتير بيع على آخر 25 يوم. بترفض لو القاعدة فيها فواتير."""
    from . import services
    me = services._get_user() or {}
    if me.get("role") != "admin":
        raise PermissionError("للمدير فقط")
    if has_activity():
        raise ValueError("القاعدة فيها فواتير بالفعل - البيانات التجريبية للقاعدة الفاضية بس")
    rnd = random.Random(seed)
    cats = {n: services.create_category(n) for n in ("مواد غذائية", "مشروبات", "منظفات")}
    catalog = [("DEMO-001", "أرز بسمتي 5 كجم", "مواد غذائية", 38, 52), ("DEMO-002", "سكر 2 كجم", "مواد غذائية", 7, 10), ("DEMO-003", "زيت طبخ 1.5 لتر", "مواد غذائية", 14, 19),
               ("DEMO-004", "مكرونة 400 جم", "مواد غذائية", 2.2, 3.5), ("DEMO-005", "شاي 100 كيس", "مشروبات", 9, 14), ("DEMO-006", "عصير برتقال 1 لتر", "مشروبات", 4, 6.5),
               ("DEMO-007", "مياه معدنية 12 عبوة", "مشروبات", 6, 9), ("DEMO-008", "قهوة عربية 250 جم", "مشروبات", 18, 27), ("DEMO-009", "سائل جلي 750 مل", "منظفات", 5, 8.5),
               ("DEMO-010", "مسحوق غسيل 3 كجم", "منظفات", 21, 30), ("DEMO-011", "مناديل 10 علب", "منظفات", 12, 18), ("DEMO-012", "معطر جو", "منظفات", 6, 11)]
    pids = []
    for sku, name, cat, cost, price in catalog:
        pids.append((services.create_product(sku, name, category_id=cats[cat], cost_price=cost, sale_price=price, reorder_point=30), cost, price))
    custs = [services.create_customer(name="عميل نقدي"),
             services.create_customer(name="مؤسسة النور للتجارة", phone="0500000001", vat_number="300000000000003", address="الرياض - حي العليا", party_type="company"),
             services.create_customer(name="محمد أحمد", phone="0500000002"), services.create_customer(name="سارة خالد", phone="0500000003")]
    sup = [services.create_supplier(name="شركة التوريدات المتحدة", phone="0110000001"), services.create_supplier(name="مؤسسة الأفق للجملة", phone="0110000002")]
    start = datetime.datetime.now() - datetime.timedelta(days=26)
    services.create_purchase_invoice(sup[0], [{"product_id": p, "quantity": 300, "unit_price": c, "tax_rate": 15} for p, c, _ in pids[:6]], notes="بيانات تجريبية", invoice_date=start)
    services.create_purchase_invoice(sup[1], [{"product_id": p, "quantity": 300, "unit_price": c, "tax_rate": 15} for p, c, _ in pids[6:]], notes="بيانات تجريبية", invoice_date=start)
    n = 0
    for day in range(25, -1, -1):
        for _ in range(rnd.randint(0, 3)):
            lines = [{"product_id": p, "quantity": rnd.randint(1, 6), "unit_price": price, "tax_rate": 15} for p, _, price in rnd.sample(pids, rnd.randint(1, 4))]
            when = (datetime.datetime.now() - datetime.timedelta(days=day)).replace(hour=rnd.randint(9, 21), minute=rnd.randint(0, 59), second=0, microsecond=0)
            services.create_sales_invoice(rnd.choice(custs), lines, notes="بيانات تجريبية", invoice_date=when)
            n += 1
    return {"products": len(pids), "customers": len(custs), "suppliers": len(sup), "sales": n}
