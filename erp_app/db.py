"""
طبقة قاعدة البيانات - نظام محاسبي محلي (SQLite)
"""

import os
import datetime
import json
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, ForeignKey,
    Text, Boolean, Index, Table, UniqueConstraint, LargeBinary
)
from sqlalchemy.orm import declarative_base, relationship, backref, sessionmaker, joinedload

import sys as _sys


def _resolve_app_dir():
    """مجلد بيانات البرنامج (القاعدة والنسخ والمرفقات والإعدادات): ERP_HOME لو متحدد، أو مجلد المستخدم لو البرنامج متحزّم (.exe)، وإلا مجلد المشروع."""
    env = os.environ.get("ERP_HOME", "").strip()
    if env:
        return os.path.abspath(env)
    if getattr(_sys, "frozen", False):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "ERP" if os.environ.get("APPDATA") else ".erp")
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


APP_DIR = _resolve_app_dir()
PKG_DIR = os.path.dirname(os.path.abspath(__file__))        # ملفات البرنامج نفسها (للقراءة فقط)
DB_PATH = os.path.join(APP_DIR, "data", "erp.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

DB_CONFIG_PATH = os.path.join(APP_DIR, "database.json")


def get_db_url():
    """رابط قاعدة البيانات: متغير البيئة ERP_DATABASE_URL ثم database.json ({"url": "..."}) ثم SQLite المحلي.
    مثال PostgreSQL:  postgresql://user:password@host:5432/erp"""
    url = os.environ.get("ERP_DATABASE_URL", "").strip()
    if not url:
        try:
            with open(DB_CONFIG_PATH, encoding="utf-8") as f:
                url = (json.load(f).get("url") or "").strip()
        except Exception:
            url = ""
    if not url:
        return f"sqlite:///{DB_PATH}"
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


DB_URL = get_db_url()
IS_SQLITE = DB_URL.startswith("sqlite")
IS_PG = DB_URL.startswith("postgresql")

if IS_SQLITE:
    engine = create_engine(DB_URL, echo=False, connect_args={"timeout": 30}, pool_size=int(os.environ.get("ERP_DB_POOL", "30")), max_overflow=30)
else:
    # قاعدة خادم (PostgreSQL): تجمّع اتصالات + فحص الاتصال قبل الاستخدام (يتعافى لو القاعدة اتعملها restart)
    engine = create_engine(DB_URL, echo=False, pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=1800, connect_args={"connect_timeout": 10})


def _sqlite_pragmas(dbapi_con, _rec):
    """WAL: القراءة ما بتتقفلش بالكتابة، وكاتب واحد في نفس الوقت مع انتظار (بدل خطأ database is locked) - لازم لتشغيل أكتر من جهاز على السيرفر."""
    try:
        cur = dbapi_con.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()
    except Exception:
        pass


from sqlalchemy import event as _sa_event
if IS_SQLITE:
    _sa_event.listen(engine, "connect", _sqlite_pragmas)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


def _now():
    return datetime.datetime.now()


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, unique=True)
    products = relationship("Product", back_populates="category")


class ProductUnit(Base):
    __tablename__ = "product_units"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False, unique=True)
    is_active = Column(Boolean, default=True)


class ProductUnitLine(Base):
    __tablename__ = "product_unit_lines"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    unit_id = Column(Integer, ForeignKey("product_units.id"), nullable=False)
    factor_to_base = Column(Float, default=1.0, nullable=False)
    sale_price = Column(Float, nullable=True)
    cost_price = Column(Float, nullable=True)
    barcode = Column(String(64), default="")
    is_default = Column(Boolean, default=False)
    product = relationship("Product", back_populates="unit_lines")
    unit = relationship("ProductUnit")


class Location(Base):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, unique=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    branch = relationship("Branch")
    cost_center = relationship("CostCenter")


class Branch(Base):
    __tablename__ = "branches"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), nullable=False, unique=True)
    name = Column(String(160), nullable=False)
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)


class CostCenter(Base):
    __tablename__ = "cost_centers"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), nullable=False, unique=True)
    name = Column(String(160), nullable=False)
    parent_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    parent = relationship("CostCenter", remote_side=[id], backref="children")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), nullable=False, unique=True)
    password_hash = Column(String(128), nullable=False)
    full_name = Column(String(160), nullable=False)
    role = Column(String(40), default="user")
    # JSON: {"sales_invoices":["view","create",...], ...}
    permissions = Column(Text, default="{}")
    # JSON list of allowed branch IDs; empty = all branches for admins only, otherwise defaults to default branch.
    branch_ids = Column(Text, default="[]")
    cost_center_ids = Column(Text, default="[]")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
    totp_secret = Column(String(64), nullable=True)
    totp_enabled = Column(Boolean, default=False)
    recovery_codes = Column(Text, nullable=True)
    totp_last_step = Column(Integer, default=0)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    sku = Column(String(64), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    unit = Column(String(32), default="قطعة")
    cost_price = Column(Float, default=0.0)
    sale_price = Column(Float, default=0.0)
    reorder_point = Column(Float, default=0.0)
    tax_rate = Column(Float, default=15.0)  # نسبة ضريبة القيمة المضافة الافتراضية
    sales_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    inventory_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    cogs_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
    product_type = Column(String(15), default="simple")  # simple | kit | manufactured | service
    image_path = Column(String(600), nullable=True)
    can_be_sold = Column(Boolean, default=True)
    can_be_purchased = Column(Boolean, default=True)
    # طريقة الإخراج: none (من غير تتبّع تشغيلات - الافتراضي) | fifo (الأقدم دخولًا أولًا) | lifo (الأحدث دخولًا أولًا) | fefo (الأقرب انتهاءً أولًا)
    issue_method = Column(String(8), default="none")
    track_expiry = Column(Boolean, default=False)          # الصنف له تاريخ صلاحية (بيتسجّل عند الاستلام)
    shelf_life_days = Column(Integer, nullable=True)       # مدة الصلاحية الافتراضية بالأيام (للإنتاج والتسويات)
    expiry_alert_days = Column(Integer, default=30)        # التنبيه قبل الانتهاء بكام يوم
    # طريقة حساب التكلفة: auto (سعر التكلفة المسجّل - الافتراضي) | avg (متوسط مرجح بيتحدّث مع كل استلام) | fifo | lifo (من تكلفة التشغيلات)
    cost_method = Column(String(8), default="auto")

    category = relationship("Category", back_populates="products")
    unit_lines = relationship("ProductUnitLine", back_populates="product", cascade="all, delete-orphan")


class StockMove(Base):
    __tablename__ = "stock_moves"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    direction = Column(String(3), nullable=False)  # 'in' | 'out'
    quantity = Column(Float, nullable=False)
    unit_id = Column(Integer, ForeignKey("product_units.id"), nullable=True)
    unit_factor = Column(Float, default=1.0, nullable=False)
    unit_cost = Column(Float, default=0.0)
    reference = Column(String(120), default="")
    note = Column(Text, default="")
    date = Column(DateTime, default=_now)
    voided = Column(Boolean, default=False)

    product = relationship("Product")
    unit = relationship("ProductUnit")
    location = relationship("Location")
    branch = relationship("Branch")
    cost_center = relationship("CostCenter")


pos_terminal_payment_methods = Table(
    "pos_terminal_payment_methods", Base.metadata,
    Column("terminal_id", Integer, ForeignKey("pos_terminals.id"), primary_key=True),
    Column("payment_method_id", Integer, ForeignKey("payment_methods.id"), primary_key=True),
)


class PosTerminal(Base):
    """ماكينة نقاط بيع (كاشير): مربوطة بفرع ومركز تكلفة ومخزن وموظف (الكاشير) ومستخدم مسموح له وطرق دفع معيّنة وعميل نقدي افتراضي.
    الفاتورة اللي بتتعمل من الماكينة بتاخد بياناتها (الفرع، مركز التكلفة، المخزن، الكاشير) وبتتسجّل عليها."""
    __tablename__ = "pos_terminals"
    id = Column(Integer, primary_key=True)
    code = Column(String(30), nullable=False, unique=True)
    name = Column(String(120), nullable=False)
    is_active = Column(Boolean, default=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    assigned_username = Column(String(80), nullable=True)           # المستخدم المسموح له يفتح الماكينة (فاضي = أي مستخدم)
    default_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    lock_customer = Column(Boolean, default=False)                  # منع تغيير العميل (دايمًا العميل الافتراضي)
    default_payment_method_id = Column(Integer, ForeignKey("payment_methods.id"), nullable=True)
    receipt_footer = Column(String(300), default="")
    notes = Column(String(300), default="")
    created_at = Column(DateTime, default=_now)

    branch = relationship("Branch")
    cost_center = relationship("CostCenter")
    location = relationship("Location")
    employee = relationship("Employee")
    default_customer = relationship("Customer")
    default_payment_method = relationship("PaymentMethod", foreign_keys=[default_payment_method_id])
    payment_methods = relationship("PaymentMethod", secondary=pos_terminal_payment_methods)


class SalesReturn(Base):
    """مرتجع مبيعات (إشعار دائن) على فاتورة: كلي أو جزئي لأصناف معيّنة. بديل الحذف/الإلغاء النهائي: الفاتورة الأصلية بتفضل زي ما هي والمرتجع
    بيسجّل عكس البيع (مخزون + قيد محاسبي) ويظهر في تقرير الجلسة."""
    __tablename__ = "sales_returns"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    date = Column(DateTime, default=_now)
    invoice_id = Column(Integer, ForeignKey("sales_invoices.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    pos_terminal_id = Column(Integer, ForeignKey("pos_terminals.id"), nullable=True)
    original_session_id = Column(Integer, ForeignKey("pos_sessions.id"), nullable=True)    # جلسة الفاتورة الأصلية
    pos_session_id = Column(Integer, ForeignKey("pos_sessions.id"), nullable=True)         # الجلسة اللي اتعمل فيها المرتجع (رد النقدية من درجها)
    processed_by = Column(String(80), default="")
    reason = Column(String(300), default="")
    refund_method = Column(String(100), default="")          # طريقة رد المبلغ (اسم طريقة الدفع) أو "على حساب العميل"
    refund_is_cash = Column(Boolean, default=False)
    is_full = Column(Boolean, default=False)                 # مرتجع كامل لباقي الفاتورة
    subtotal = Column(Float, default=0.0)
    tax_total = Column(Float, default=0.0)
    total = Column(Float, default=0.0)

    invoice = relationship("SalesInvoice", foreign_keys=[invoice_id])
    customer = relationship("Customer")
    items = relationship("SalesReturnItem", back_populates="sales_return", cascade="all, delete-orphan")


class SalesReturnItem(Base):
    __tablename__ = "sales_return_items"
    id = Column(Integer, primary_key=True)
    return_id = Column(Integer, ForeignKey("sales_returns.id"), nullable=False)
    invoice_item_id = Column(Integer, ForeignKey("sales_invoice_items.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, nullable=False)                 # بوحدة الفاتورة
    unit_id = Column(Integer, ForeignKey("product_units.id"), nullable=True)
    unit_factor = Column(Float, default=1.0)
    unit_price = Column(Float, default=0.0)
    discount = Column(Float, default=0.0)                    # حصة الكمية المرتجعة من خصم السطر
    tax_rate = Column(Float, default=15.0)
    line_total = Column(Float, default=0.0)                  # شامل الضريبة

    sales_return = relationship("SalesReturn", back_populates="items")
    product = relationship("Product")
    unit = relationship("ProductUnit")


class PosSession(Base):
    """جلسة (وردية) كاشير على ماكينة: بتتفتح بعهدة افتتاحية وبتتقفل بجرد النقدية. كل فواتير الكاشير في الفترة دي بتتسجّل عليها."""
    __tablename__ = "pos_sessions"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    terminal_id = Column(Integer, ForeignKey("pos_terminals.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)      # الكاشير (من الماكينة وقت الفتح)
    opened_by = Column(String(80), nullable=False)
    opened_at = Column(DateTime, default=_now)
    opening_cash = Column(Float, default=0.0)
    notes = Column(String(300), default="")
    state = Column(String(10), default="open")        # open | closed
    closed_by = Column(String(80), nullable=True)
    closed_at = Column(DateTime, nullable=True)
    expected_cash = Column(Float, nullable=True)      # العهدة + المبيعات النقدية وقت الإغلاق
    counted_cash = Column(Float, nullable=True)       # النقدية الفعلية المعدودة
    difference = Column(Float, nullable=True)         # المعدود - المتوقع (+ زيادة / - عجز)
    close_notes = Column(String(300), default="")

    terminal = relationship("PosTerminal")
    employee = relationship("Employee")


class StockMoveBatch(Base):
    """توزيع حركة مخزون على تشغيلات (batches) للأصناف المتتبَّعة (طريقة إخراج أو صلاحية).
    حركة الدخول: سطر لكل تشغيلة داخلة. حركة الخروج: سطر لكل تشغيلة اتسحب منها. المتبقي من تشغيلة = مجموع الدخول - مجموع الخروج لنفس
    (الصنف، المخزن، رقم التشغيلة، تاريخ الصلاحية). الكميات بالوحدة الأساسية."""
    __tablename__ = "stock_move_batches"
    id = Column(Integer, primary_key=True)
    move_id = Column(Integer, ForeignKey("stock_moves.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    direction = Column(String(3), nullable=False)          # in | out
    batch_no = Column(String(60), default="")
    expiry_date = Column(DateTime, nullable=True)
    quantity = Column(Float, nullable=False)
    unit_cost = Column(Float, default=0.0)                 # تكلفة الوحدة الأساسية في التشغيلة (بتتحوّل لتكلفة مبيعات عند الخروج)
    received_at = Column(DateTime, nullable=True)          # تاريخ دخول التشغيلة (لـ FIFO/LIFO)

    move = relationship("StockMove")
    product = relationship("Product")
    location = relationship("Location")


class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    party_type = Column(String(10), default="individual")  # individual | company
    phone = Column(String(50), default="")
    email = Column(String(200), default="")
    vat_number = Column(String(50), default="")
    address = Column(Text, default="")
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    price_list_id = Column(Integer, ForeignKey("price_lists.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
    loyalty_enabled = Column(Boolean, default=False)     # عضو في برنامج الولاء
    loyalty_points = Column(Float, default=0.0)          # رصيد النقاط الحالي
    notify_opt_in = Column(Boolean, default=False)       # موافقة العميل على استلام رسائل (واتساب/SMS)
    credit_limit = Column(Float, default=0.0)            # حد الائتمان (0 = بلا حد)
    credit_days = Column(Integer, default=0)             # مهلة السداد بالأيام من تاريخ الفاتورة
    credit_hold = Column(Boolean, default=False)         # إيقاف البيع الآجل لهذا العميل
    crn = Column(String(30), default="")                 # السجل التجاري (للفاتورة الضريبية العادية B2B)
    building_no = Column(String(10), default="")         # العنوان الوطني (4 أرقام)
    district = Column(String(100), default="")
    city = Column(String(100), default="")
    postal_code = Column(String(10), default="")

    price_list = relationship("PriceList")


class ZatcaDoc(Base):
    """مستند فوترة إلكترونية (ZATCA المرحلة 2): XML موقّع + سلسلة الهاش + حالة الإبلاغ. فاتورة أو إشعار دائن (مرتجع)."""
    __tablename__ = "zatca_docs"
    id = Column(Integer, primary_key=True)
    kind = Column(String(10), nullable=False)               # invoice | credit
    ref_id = Column(Integer, nullable=False)                # id الفاتورة أو المرتجع
    number = Column(String(40), default="")
    uuid = Column(String(40), nullable=False)
    icv = Column(Integer, nullable=False, unique=True)      # عداد الفواتير المتسلسل
    pih = Column(String(100), default="")
    hash = Column(String(100), default="")
    mode = Column(String(12), default="simplified")         # simplified (إبلاغ) | standard (اعتماد)
    xml = Column(Text, default="")
    qr = Column(Text, default="")
    status = Column(String(12), default="signed")           # signed | reported | cleared | rejected | failed | error
    response = Column(Text, default="")
    attempts = Column(Integer, default=0)
    created = Column(DateTime, default=_now)
    sent_at = Column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("kind", "ref_id", name="uq_zatca_doc_ref"),)


class PriceList(Base):
    """قائمة أسعار بيع مخصصة - تتربط بعميل (أو أكتر)، ولو الصنف مش موجود
    فيها (أو العميل مالوش قائمة أسعار خالص) بيترجع لسعر البيع الافتراضي
    المسجّل على الصنف نفسه."""
    __tablename__ = "price_lists"
    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False, unique=True)
    notes = Column(String(300), default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)


class PriceListItem(Base):
    __tablename__ = "price_list_items"
    id = Column(Integer, primary_key=True)
    price_list_id = Column(Integer, ForeignKey("price_lists.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    price = Column(Float, nullable=False)

    price_list = relationship("PriceList", backref=backref("items", cascade="all, delete-orphan"))
    product = relationship("Product")


class Supplier(Base):
    __tablename__ = "suppliers"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    party_type = Column(String(10), default="individual")  # individual | company
    phone = Column(String(50), default="")
    vat_number = Column(String(50), default="")
    address = Column(Text, default="")
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now)
    iban = Column(String(40), default="")           # آيبان المورد (لملفات التحويل البنكي)
    bank_name = Column(String(100), default="")


class CompanySettings(Base):
    """إعدادات الشركة - سطر واحد فقط (id=1)."""
    __tablename__ = "company_settings"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), default="اسم الشركة")
    vat_number = Column(String(50), default="")
    address = Column(Text, default="")
    phone = Column(String(50), default="")
    default_tax_rate = Column(Float, default=15.0)
    invoice_prefix_sales = Column(String(10), default="S-")
    invoice_prefix_purchase = Column(String(10), default="P-")
    logo_path = Column(String(500), default="")
    # ربط منصة فاتورة (ZATCA) - اختياري بالكامل، معطّل افتراضياً
    zatca_enabled = Column(Boolean, default=False)
    zatca_environment = Column(String(20), default="sandbox")  # sandbox | production
    zatca_api_url = Column(String(300), default="")
    zatca_username = Column(String(200), default="")   # CSID / Certificate ID
    zatca_password = Column(String(500), default="")   # Certificate Secret
    # إرسال الفواتير بالإيميل (SMTP)
    smtp_host = Column(String(200), default="")
    smtp_port = Column(Integer, default=587)
    smtp_username = Column(String(200), default="")
    smtp_password = Column(String(500), default="")
    smtp_from_email = Column(String(200), default="")
    smtp_use_tls = Column(Boolean, default=True)
    # تخصيص تنسيق الطباعة
    print_paper_size = Column(String(20), default="a4")  # a4 | thermal80 | thermal58
    print_color = Column(String(20), default="#1A7A5E")
    print_show_logo = Column(Boolean, default=True)
    print_show_qr = Column(Boolean, default=True)
    print_font_size = Column(String(10), default="normal")  # normal | large
    annual_leave_days = Column(Integer, default=21)  # رصيد الإجازة السنوية بالأيام لكل موظف
    weekly_off_days = Column(String(20), default="4,5")   # أيام الراحة الأسبوعية (0=الإثنين ... 4=الجمعة 5=السبت 6=الأحد)
    payroll_day_basis = Column(Integer, default=30)  # أساس أجر اليوم في الرواتب: 30 = شهر ثابت 30 يوم، 0 = أيام الشهر الفعلية
    print_footer_note = Column(Text, default="")


class SalesInvoice(Base):
    __tablename__ = "sales_invoices"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    date = Column(DateTime, default=_now)
    voided = Column(Boolean, default=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    subtotal = Column(Float, default=0.0)      # قبل الخصم والضريبة
    discount = Column(Float, default=0.0)      # قيمة خصم إجمالية
    tax_total = Column(Float, default=0.0)     # مجموع الضريبة
    total = Column(Float, default=0.0)         # الإجمالي النهائي
    notes = Column(Text, default="")
    is_pos = Column(Boolean, default=False)
    pos_terminal_id = Column(Integer, ForeignKey("pos_terminals.id"), nullable=True)            # ماكينة الكاشير اللي اتباع عليها (POS)
    pos_session_id = Column(Integer, ForeignKey("pos_sessions.id"), nullable=True)              # جلسة الكاشير اللي اتباع فيها
    cashier_employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)           # الموظف (الكاشير) المرتبط بالماكينة وقت البيع
    payment_method = Column(String(20), default="")  # cash | card | transfer (POS فقط)
    zatca_status = Column(String(20), default="not_sent")  # not_sent | sent | failed | disabled
    zatca_response = Column(Text, default="")
    promo_code = Column(String(40), default="")           # كوبون مستخدم (لو فيه)
    promo_discount = Column(Float, default=0.0)           # قيمة الخصم الترويجي/اليدوي (شامل الضريبة) - موزعة على أسطر الفاتورة
    promo_note = Column(String(200), default="")          # سبب الخصم اليدوي أو وصف الكوبون
    promo_approved_by = Column(String(100), default="")   # المدير اللي اعتمد (لو الخصم فوق الحد)
    client_uuid = Column(String(40), nullable=True, index=True)   # معرّف بيع الكاشير (لمنع تكرار الفاتورة عند مزامنة بيع بدون اتصال)
    currency = Column(String(5), nullable=True)                   # عملة الفاتورة الأجنبية (فاضي = العملة الأساسية)
    exchange_rate = Column(Float, nullable=True)                  # سعر الصرف وقت الفاتورة (أساسي لكل 1 أجنبي)
    foreign_total = Column(Float, nullable=True)                  # الإجمالي بالعملة الأجنبية

    customer = relationship("Customer")
    branch = relationship("Branch")
    cost_center = relationship("CostCenter")
    items = relationship("SalesInvoiceItem", back_populates="invoice",
                          cascade="all, delete-orphan")


class SalesInvoiceItem(Base):
    __tablename__ = "sales_invoice_items"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("sales_invoices.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    unit_id = Column(Integer, ForeignKey("product_units.id"), nullable=True)
    unit_factor = Column(Float, default=1.0, nullable=False)
    unit_price = Column(Float, nullable=False)
    discount = Column(Float, default=0.0)      # قيمة خصم للسطر
    tax_rate = Column(Float, default=15.0)     # نسبة الضريبة %
    line_total = Column(Float, default=0.0)    # الإجمالي شامل الضريبة بعد الخصم

    invoice = relationship("SalesInvoice", back_populates="items")
    product = relationship("Product")
    unit = relationship("ProductUnit")


class DocumentType(Base):
    """نوع مستند/رخصة قابل للتجديد (إقامة، جواز، رخصة نشاط، عقد إيجار...) - المستخدم يقدر يضيف أي نوع.
    remind_days: أيام التنبيه قبل الانتهاء مفصولة بفاصلة (مثلًا 90,60,30,7)."""
    __tablename__ = "document_types"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, unique=True)
    holder_kind = Column(String(10), default="other")      # employee | company | other
    remind_days = Column(String(80), default="30,7")
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)


class TrackedDocument(Base):
    """مستند/رخصة بتاريخ انتهاء بنتابعه ونتنبّه قبل انتهائه ونجدّده. مالوش أي أثر محاسبي."""
    __tablename__ = "tracked_documents"
    id = Column(Integer, primary_key=True)
    type_id = Column(Integer, ForeignKey("document_types.id"), nullable=False)
    title = Column(String(200), nullable=False)
    doc_number = Column(String(80), default="")
    holder_kind = Column(String(10), default="company")    # employee | company | other
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    holder_name = Column(String(200), default="")          # لو الشركة/حاجة تانية (سيارة، فرع، محل...)
    issuer = Column(String(200), default="")
    issue_date = Column(DateTime, nullable=True)
    expiry_date = Column(DateTime, nullable=False)
    remind_days = Column(String(80), default="30,7")
    cost = Column(Float, default=0.0)                      # آخر تكلفة تجديد/رسوم
    notes = Column(Text, default="")
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    archived = Column(Boolean, default=False)              # مش محتاج تجديد (ملغي/انتهى الغرض منه)
    attachment_path = Column(String(500), default="")
    created_by = Column(String(100), default="")
    created_at = Column(DateTime, default=_now)

    doc_type = relationship("DocumentType")
    employee = relationship("Employee")
    branch = relationship("Branch")
    renewals = relationship("DocumentRenewal", back_populates="document", cascade="all, delete-orphan", order_by="DocumentRenewal.id")


class DocumentRenewal(Base):
    """سجل تجديدات المستند (تاريخ الانتهاء القديم والجديد والتكلفة)."""
    __tablename__ = "document_renewals"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("tracked_documents.id"), nullable=False)
    renewed_at = Column(DateTime, default=_now)
    old_expiry = Column(DateTime, nullable=True)
    new_expiry = Column(DateTime, nullable=False)
    doc_number = Column(String(80), default="")
    cost = Column(Float, default=0.0)
    notes = Column(String(300), default="")
    attachment_path = Column(String(500), default="")
    created_by = Column(String(100), default="")

    document = relationship("TrackedDocument", back_populates="renewals")


class DocumentAlert(Base):
    """تنبيه اتعرض لمستخدم عن مستند عند مرحلة معينة (tier = عدد الأيام المتبقية للمرحلة، -1 = منتهي)
    - عشان كل مستخدم يتنبّه مرة لكل مرحلة، ويقدر يأجّل (snoozed_until)."""
    __tablename__ = "document_alerts"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("tracked_documents.id"), nullable=False)
    username = Column(String(80), nullable=False)
    tier = Column(Integer, nullable=False)
    alerted_at = Column(DateTime, default=_now)
    snoozed_until = Column(DateTime, nullable=True)


class PrepaidTemplate(Base):
    """قالب مصروف مدفوع مقدمًا (إيجار، تأمين، اشتراك...): حساب المصروف والمدة وطريقة التقسيم الافتراضية."""
    __tablename__ = "prepaid_templates"
    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False, unique=True)
    expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    months = Column(Integer, default=12)
    method = Column(String(10), default="equal")      # equal (أقساط شهرية متساوية) | daily (بالأيام الفعلية لكل شهر)
    notes = Column(String(300), default="")
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

    expense_account = relationship("Account", foreign_keys=[expense_account_id])


class PrepaidExpense(Base):
    """مصروف مدفوع مقدمًا بيتقسّم آليًا على مدة (شهور): عند الدفع بيتسجّل على حساب المصروفات المدفوعة مقدمًا،
    وكل شهر بيترحّل قسط للمصروف (مدين المصروف / دائن المدفوع مقدمًا)."""
    __tablename__ = "prepaid_expenses"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    template_id = Column(Integer, ForeignKey("prepaid_templates.id"), nullable=True)
    title = Column(String(200), nullable=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    prepaid_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    amount = Column(Float, default=0.0)               # المبلغ اللي بيتقسّم (قبل الضريبة)
    tax_rate = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    start_date = Column(DateTime, nullable=False)
    months = Column(Integer, default=12)
    method = Column(String(10), default="equal")
    payment_kind = Column(String(10), default="paid")  # paid (مدفوع الآن) | payable (على حساب المورد) | none (متسجّل قبل كده - جدول بس)
    payment_method_id = Column(Integer, ForeignKey("payment_methods.id"), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    auto_post = Column(Boolean, default=True)          # ترحيل الأقساط المستحقة آليًا
    state = Column(String(12), default="active")       # active | completed | stopped | cancelled
    initial_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    notes = Column(Text, default="")
    created_by = Column(String(100), default="")
    created_at = Column(DateTime, default=_now)

    template = relationship("PrepaidTemplate")
    supplier = relationship("Supplier")
    expense_account = relationship("Account", foreign_keys=[expense_account_id])
    prepaid_account = relationship("Account", foreign_keys=[prepaid_account_id])
    payment_method = relationship("PaymentMethod")
    lines = relationship("PrepaidExpenseLine", back_populates="prepaid", cascade="all, delete-orphan", order_by="PrepaidExpenseLine.seq")


class PrepaidExpenseLine(Base):
    """قسط من جدول التقسيم: الفترة وتاريخ الاستحقاق (آخر الشهر) والمبلغ وحالته."""
    __tablename__ = "prepaid_expense_lines"
    id = Column(Integer, primary_key=True)
    prepaid_id = Column(Integer, ForeignKey("prepaid_expenses.id"), nullable=False)
    seq = Column(Integer, default=1)
    period_from = Column(DateTime, nullable=False)
    period_to = Column(DateTime, nullable=False)
    entry_date = Column(DateTime, nullable=False)
    amount = Column(Float, default=0.0)
    state = Column(String(10), default="pending")      # pending | posted
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    posted_at = Column(DateTime, nullable=True)

    prepaid = relationship("PrepaidExpense", back_populates="lines")


class ChatConversation(Base):
    """محادثة بين مستخدمي النظام: direct (واحد لواحد - مفتاحها فريد من اسمَي المستخدمين) أو group (مجموعة)."""
    __tablename__ = "chat_conversations"
    id = Column(Integer, primary_key=True)
    kind = Column(String(10), default="direct")
    title = Column(String(150), nullable=True)            # اسم المجموعة (للمحادثات الفردية بيظهر اسم الطرف التاني)
    direct_key = Column(String(170), unique=True, nullable=True)
    created_by = Column(String(80), default="")
    created_at = Column(DateTime, default=_now)
    last_message_at = Column(DateTime, default=_now)

    members = relationship("ChatMember", back_populates="conversation", cascade="all, delete-orphan")
    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan")


class ChatMember(Base):
    """عضوية مستخدم في محادثة. last_read_message_id = آخر رسالة قراها (للعدّاد)،
    joined_message_id = آخر رسالة كانت موجودة وقت انضمامه (العضو الجديد مبيشوفش اللي قبلها)."""
    __tablename__ = "chat_members"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("chat_conversations.id"), nullable=False)
    username = Column(String(80), nullable=False)
    joined_at = Column(DateTime, default=_now)
    joined_message_id = Column(Integer, default=0)
    last_read_message_id = Column(Integer, default=0)
    left = Column(Boolean, default=False)

    conversation = relationship("ChatConversation", back_populates="members")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("chat_conversations.id"), nullable=False)
    sender = Column(String(80), nullable=False)
    body = Column(Text, default="")
    created_at = Column(DateTime, default=_now)
    is_system = Column(Boolean, default=False)            # رسالة نظام (إنشاء مجموعة / إضافة / مغادرة)
    deleted = Column(Boolean, default=False)
    attachment_path = Column(String(500), default="")
    attachment_name = Column(String(255), default="")
    attachment_size = Column(Integer, default=0)
    attachment_kind = Column(String(10), default="")      # image | file

    conversation = relationship("ChatConversation", back_populates="messages")


class AgendaItem(Base):
    """موعد/مهمة في جدول الأعمال - للتنظيم والتذكير فقط (مالوش أي أثر محاسبي أو مخزني).
    remind_before_minutes: None = من غير تنبيه، 0 = عند الموعد، وإلا قبل الموعد بعدد الدقايق.
    next_alert_at: وقت التنبيه القادم (بيتحسب من الموعد وبيتصفّر بعد ما التنبيه يظهر،
    وبيتأجّل لو المستخدم اختار تأجيل). repeat: none | daily | weekly | monthly | yearly."""
    __tablename__ = "agenda_items"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    kind = Column(String(15), default="task")          # task | meeting | deadline | reminder | other
    start_at = Column(DateTime, nullable=False)
    all_day = Column(Boolean, default=False)
    remind_before_minutes = Column(Integer, nullable=True)
    next_alert_at = Column(DateTime, nullable=True)
    repeat = Column(String(10), default="none")
    anchor_day = Column(Integer, nullable=True)         # يوم الشهر الأصلي للتكرار الشهري/السنوي (31 يناير → 28 فبراير → 31 مارس)
    priority = Column(String(10), default="normal")    # low | normal | high
    status = Column(String(12), default="pending")     # pending | done | cancelled
    done_at = Column(DateTime, nullable=True)
    done_count = Column(Integer, default=0)
    created_by = Column(String(100), default="")
    assigned_to = Column(String(80), nullable=True)    # username؛ فاضي = للي أنشأه
    created_at = Column(DateTime, default=_now)


class SalesQuotation(Base):
    """عرض سعر للعميل: بنود بالأسعار والخصم والضريبة وصلاحية محددة. مالوش أي أثر
    محاسبي أو مخزني؛ بيتحوّل لفاتورة مبيعات (بنفس الأسعار) بعد موافقة العميل.
    state: draft (مسودة) | sent (مرسل) | accepted (مقبول) | rejected (مرفوض) | invoiced (اتحوّل لفاتورة).
    'منتهي' بيتحسب من تاريخ الصلاحية (valid_until) للعروض غير المحسومة."""
    __tablename__ = "sales_quotations"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    date = Column(DateTime, default=_now)
    valid_until = Column(DateTime, nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    subtotal = Column(Float, default=0.0)      # بعد خصم السطور وقبل الضريبة
    discount = Column(Float, default=0.0)      # خصم إجمالي على العرض
    tax_total = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    notes = Column(Text, default="")
    terms = Column(Text, default="")           # شروط العرض (دفع، تسليم، ضمان...)
    state = Column(String(15), default="draft")
    decision_note = Column(String(300), default="")
    decided_at = Column(DateTime, nullable=True)
    invoice_id = Column(Integer, ForeignKey("sales_invoices.id"), nullable=True)
    created_by = Column(String(100), default="")

    customer = relationship("Customer")
    branch = relationship("Branch")
    cost_center = relationship("CostCenter")
    invoice = relationship("SalesInvoice")
    items = relationship("SalesQuotationItem", back_populates="quotation", cascade="all, delete-orphan", order_by="SalesQuotationItem.id")


class SalesQuotationItem(Base):
    __tablename__ = "sales_quotation_items"
    id = Column(Integer, primary_key=True)
    quotation_id = Column(Integer, ForeignKey("sales_quotations.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    unit_id = Column(Integer, ForeignKey("product_units.id"), nullable=True)
    unit_price = Column(Float, nullable=False)
    discount = Column(Float, default=0.0)
    tax_rate = Column(Float, default=15.0)
    line_total = Column(Float, default=0.0)

    quotation = relationship("SalesQuotation", back_populates="items")
    product = relationship("Product")
    unit = relationship("ProductUnit")


class GoodsReceiptNote(Base):
    """سند استلام مشتريات - بيسجّل استلام البضاعة فعليًا في المخزون وقت
    وصولها، سواء وصلت فاتورة المورد وقتها أو لأ. لما توصل الفاتورة، بيتم
    تحويل السند لفاتورة مشتريات (من غير ما يتكرر إدخال المخزون تاني)."""
    __tablename__ = "goods_receipt_notes"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    date = Column(DateTime, default=_now)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    notes = Column(Text, default="")
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    invoiced = Column(Boolean, default=False)
    purchase_invoice_id = Column(Integer, ForeignKey("purchase_invoices.id"), nullable=True)
    voided = Column(Boolean, default=False)

    supplier = relationship("Supplier")
    location = relationship("Location")
    branch = relationship("Branch")
    cost_center = relationship("CostCenter")
    purchase_invoice = relationship("PurchaseInvoice")
    items = relationship("GoodsReceiptNoteItem", back_populates="receipt", cascade="all, delete-orphan")


class GoodsReceiptNoteItem(Base):
    __tablename__ = "goods_receipt_note_items"
    id = Column(Integer, primary_key=True)
    receipt_id = Column(Integer, ForeignKey("goods_receipt_notes.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, default=0.0)                      # الكمية بالوحدة المختارة (unit_id) - مش بالوحدة الأساسية
    unit_cost = Column(Float, default=0.0)                     # تكلفة الوحدة المختارة
    unit_id = Column(Integer, ForeignKey("product_units.id"), nullable=True)
    unit_factor = Column(Float, default=1.0)                   # معامل الوحدة المختارة للوحدة الأساسية وقت الاستلام

    receipt = relationship("GoodsReceiptNote", back_populates="items")
    product = relationship("Product")
    unit = relationship("ProductUnit", foreign_keys=[unit_id])


class PurchaseInvoice(Base):
    __tablename__ = "purchase_invoices"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    date = Column(DateTime, default=_now)
    voided = Column(Boolean, default=False)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    subtotal = Column(Float, default=0.0)
    discount = Column(Float, default=0.0)
    tax_total = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    currency = Column(String(5), nullable=True)
    exchange_rate = Column(Float, nullable=True)
    foreign_total = Column(Float, nullable=True)
    notes = Column(Text, default="")

    supplier = relationship("Supplier")
    branch = relationship("Branch")
    cost_center = relationship("CostCenter")
    items = relationship("PurchaseInvoiceItem", back_populates="invoice",
                          cascade="all, delete-orphan")
    attachments = relationship("PurchaseInvoiceAttachment", back_populates="invoice",
                                cascade="all, delete-orphan")


class PurchaseInvoiceAttachment(Base):
    """مرفقات فاتورة المشتريات - نسخة ممسوحة ضوئياً أو PDF من فاتورة
    المورد الأصلية، ممكن يتضاف أكتر من ملف للفاتورة الواحدة."""
    __tablename__ = "purchase_invoice_attachments"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("purchase_invoices.id"), nullable=False)
    file_name = Column(String(300), nullable=False)
    file_path = Column(String(600), nullable=False)
    uploaded_at = Column(DateTime, default=_now)

    invoice = relationship("PurchaseInvoice", back_populates="attachments")


class PurchaseInvoiceItem(Base):
    __tablename__ = "purchase_invoice_items"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("purchase_invoices.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, nullable=False)
    unit_id = Column(Integer, ForeignKey("product_units.id"), nullable=True)
    unit_factor = Column(Float, default=1.0, nullable=False)
    unit_price = Column(Float, nullable=False)   # سعر الشراء
    discount = Column(Float, default=0.0)
    tax_rate = Column(Float, default=15.0)
    line_total = Column(Float, default=0.0)

    invoice = relationship("PurchaseInvoice", back_populates="items")
    product = relationship("Product")
    unit = relationship("ProductUnit")


_PERF_INDEXES = [
    ("ix_stock_moves_prod_loc", "stock_moves", "product_id, location_id, voided"), ("ix_stock_moves_date", "stock_moves", "date"), ("ix_stock_moves_branch", "stock_moves", "branch_id"),
    ("ix_sales_items_product", "sales_invoice_items", "product_id"), ("ix_sales_items_invoice", "sales_invoice_items", "invoice_id"),
    ("ix_purch_items_product", "purchase_invoice_items", "product_id"), ("ix_purch_items_invoice", "purchase_invoice_items", "invoice_id"),
    ("ix_je_lines_account", "journal_entry_lines", "account_id"), ("ix_je_lines_entry", "journal_entry_lines", "entry_id"), ("ix_je_date", "journal_entries", "date"),
    ("ix_sales_inv_date", "sales_invoices", "date"), ("ix_sales_inv_customer", "sales_invoices", "customer_id"), ("ix_purch_inv_date", "purchase_invoices", "date"),
    ("ix_purch_inv_supplier", "purchase_invoices", "supplier_id"), ("ix_payments_date", "payments", "date"), ("ix_products_category", "products", "category_id"),
    ("ix_products_name", "products", "name"), ("ix_smb_prod_loc", "stock_move_batches", "product_id, location_id"), ("ix_smb_move", "stock_move_batches", "move_id"), ("ix_customers_name", "customers", "name"), ("ix_suppliers_name", "suppliers", "name"),
]


def _ensure_indexes():
    """فهارس الأداء: أي استعلام على آلاف الأصناف/الحركات/القيود بيبقى فوري بدل ما يمسح الجدول كله. آمنة للتكرار (IF NOT EXISTS)."""
    from sqlalchemy import text
    with engine.begin() as conn:
        for name, table, cols in _PERF_INDEXES:
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})"))
            except Exception:
                pass           # عمود/جدول مش موجود في قاعدة قديمة جدًا - نتجاهل بهدوء


def _ddl(definition):
    """تعريف عمود مكتوب بصيغة SQLite -> الصيغة المناسبة للقاعدة الحالية (PostgreSQL بيرفض DATETIME وREAL وBOOLEAN DEFAULT 0)."""
    if IS_SQLITE:
        return definition
    import re
    d = re.sub(r"\bDATETIME\b", "TIMESTAMP", definition)
    d = re.sub(r"\bREAL\b", "DOUBLE PRECISION", d)
    if "BOOLEAN" in d:
        d = re.sub(r"DEFAULT 0\b", "DEFAULT FALSE", d)
        d = re.sub(r"DEFAULT 1\b", "DEFAULT TRUE", d)
    return d


def init_db():
    Base.metadata.create_all(engine)
    _migrate_legacy_schema()
    _ensure_indexes()
    _seed_defaults()
    _seed_accounting_defaults()
    _seed_product_account_links()
    _seed_product_unit_lines()
    _seed_fiscal_period()
    _backfill_org_links()
    _seed_budget_defaults()
    _seed_leave_types()
    _migrate_asset_categories()
    _seed_payment_methods()



def _migrate_asset_categories():
    """أصول اتسجّلت قبل جدول الفئات (فئة نصية + حسابات على كل أصل): بنعمل
    فئة جدولية لكل اسم فئة مميّز (بحسابات وعمر أول أصل فيها) ونربط الأصول بيها.
    آمنة للتكرار - بتشتغل بس على الأصول اللي لسه ملهاش category_id."""
    session = SessionLocal()
    try:
        legacy = session.query(FixedAsset).filter(FixedAsset.category_id.is_(None), FixedAsset.category != "", FixedAsset.category.isnot(None)).order_by(FixedAsset.id).all()
        if not legacy:
            return
        by_name = {c.name: c for c in session.query(AssetCategory).all()}
        for a in legacy:
            cat = by_name.get(a.category)
            if not cat:
                pct = round((a.salvage_value or 0) / a.cost * 100, 2) if a.cost else 0.0
                cat = AssetCategory(
                    name=a.category, useful_life_months=a.useful_life_months or 60, salvage_percent=pct,
                    asset_account_id=a.asset_account_id, accumulated_depreciation_account_id=a.accumulated_depreciation_account_id,
                    depreciation_expense_account_id=a.depreciation_expense_account_id, is_active=True,
                )
                session.add(cat); session.flush()
                by_name[a.category] = cat
            a.category_id = cat.id
        session.commit()
    finally:
        session.close()

def _seed_payment_methods():
    """طرق دفع افتراضية لو الجدول لسه فاضي - نقدي (على حساب النقدية
    الافتراضي لو محدد) + شبكة/بطاقة + تحويل بنكي + آجل على حساب العميل."""
    session = SessionLocal()
    try:
        if session.query(PaymentMethod).count():
            return
        from .chart_data import payment_method_new_code
        cfg = session.get(AccountingSettings, 1)
        cash_id = cfg.cash_account_id if cfg else None

        def method_acc(name):
            a = session.query(Account).filter(Account.code == payment_method_new_code(name)).first()
            return a.id if a else cash_id
        session.add_all([
            PaymentMethod(name="نقدي", account_id=method_acc("نقدي"), is_credit=False, is_active=True, sort_order=1),
            PaymentMethod(name="شبكة / بطاقة", account_id=method_acc("شبكة / بطاقة"), is_credit=False, is_active=True, sort_order=2),
            PaymentMethod(name="تحويل بنكي", account_id=method_acc("تحويل بنكي"), is_credit=False, is_active=True, sort_order=3),
            PaymentMethod(name="آجل - على حساب العميل", account_id=None, is_credit=True, is_active=True, sort_order=4),
        ])
        session.commit()
    finally:
        session.close()


def _seed_defaults():
    session = SessionLocal()
    try:
        if session.query(Location).count() == 0:
            session.add(Location(name="المخزن الرئيسي", is_default=True))

        if session.query(ProductUnit).count() == 0:
            for u in ("قطعة", "كجم", "جرام", "لتر", "مل", "علبة", "كرتون", "متر", "وحدة"):
                session.add(ProductUnit(name=u, is_active=True))

        if session.query(CompanySettings).count() == 0:
            session.add(CompanySettings(
                id=1, name="اسم الشركة", vat_number="", address="", phone="",
                default_tax_rate=15.0, invoice_prefix_sales="S-",
                invoice_prefix_purchase="P-",
            ))
        if session.query(Branch).count() == 0:
            session.add(Branch(code="BR01", name="الفرع الرئيسي", is_active=True, is_default=True))
        if session.query(CostCenter).count() == 0:
            session.add(CostCenter(code="CC01", name="المركز الرئيسي", is_active=True))
        if session.query(User).count() == 0:
            import hashlib, json
            session.add(User(username="admin", password_hash=hashlib.sha256("admin".encode()).hexdigest(),
                             full_name="مدير النظام", role="admin", permissions=json.dumps({"*": ["*"]}, ensure_ascii=False), branch_ids=json.dumps([], ensure_ascii=False)) )

        session.commit()
    finally:
        session.close()


def _migrate_legacy_schema():
    """إضافة الأعمدة الجديدة لقواعد البيانات القديمة بدون حذف البيانات."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)

    # موديول التوالف اتعاد تصميمه ليدعم أكتر من صنف في نفس السند (schema
    # جديد كليًا: damage_records -> damage_items -> damage_lines بدل
    # damage_records -> damage_lines مباشرة). لو لقينا الشكل القديم
    # (damage_lines فيها عمود record_id بدل item_id)، نعيد بناء الجداول
    # دي بس من الأول - الموديول حديث جدًا ومفيش بيانات إنتاجية عليه.
    if inspector.has_table("damage_lines"):
        old_cols = {c["name"] for c in inspector.get_columns("damage_lines")}
        if "record_id" in old_cols and "item_id" not in old_cols:
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS damage_lines"))
                conn.execute(text("DROP TABLE IF EXISTS damage_records"))
            Base.metadata.create_all(engine)  # يعيد بناء damage_records/damage_items/damage_lines بالشكل الجديد
            inspector = inspect(engine)

    # نظام المطاعم اتوسّع بعد كده ليدعم طلبات بدون طاولة (تيك أواي/دليفري)،
    # يعني عمود table_id لازم يبقى قابل للفراغ. SQLite مش بيسمح بتعديل قيد
    # NOT NULL على عمود موجود مباشرة، فلو لقينا الجدول القديم (table_id
    # لسه إجباري)، بنعيد بنائه بالشكل الجديد مع الحفاظ على كل البيانات
    # الموجودة (بما فيها أي أعمدة جديدة زي order_type/customer_name لو
    # كانت اتضافت بالفعل في ترقية سابقة).
    if inspector.has_table("restaurant_orders"):
        cols_info = {c["name"]: c for c in inspector.get_columns("restaurant_orders")}
        if "table_id" in cols_info and cols_info["table_id"]["nullable"] is False:
            with engine.begin() as conn:
                old_cols = list(cols_info.keys())
                conn.execute(text("ALTER TABLE restaurant_orders RENAME TO restaurant_orders_old_tmp"))
            Base.metadata.create_all(engine)  # يعيد بناء restaurant_orders بالشكل الجديد (table_id قابل للفراغ)
            with engine.begin() as conn:
                new_cols = {c["name"] for c in inspect(engine).get_columns("restaurant_orders")}
                common = [c for c in old_cols if c in new_cols]
                cols_sql = ", ".join(common)
                conn.execute(text(f"INSERT INTO restaurant_orders ({cols_sql}) SELECT {cols_sql} FROM restaurant_orders_old_tmp"))
                conn.execute(text("DROP TABLE restaurant_orders_old_tmp"))
            inspector = inspect(engine)

    with engine.begin() as conn:
        table_cols = {}
        additions = {
            "products": ["sales_account_id INTEGER", "inventory_account_id INTEGER", "cogs_account_id INTEGER",
                         "product_type VARCHAR(15) DEFAULT 'simple'", "image_path VARCHAR(600)",
                         "can_be_sold BOOLEAN DEFAULT 1", "can_be_purchased BOOLEAN DEFAULT 1",
                         "issue_method VARCHAR(8) DEFAULT 'none'", "track_expiry BOOLEAN DEFAULT 0", "shelf_life_days INTEGER", "expiry_alert_days INTEGER DEFAULT 30", "cost_method VARCHAR(8) DEFAULT 'auto'"],
            "bom_lines": ["unit_id INTEGER", "unit_qty FLOAT"],
            "payment_methods": ["is_cash BOOLEAN", "provider_id INTEGER"],
            "goods_receipt_note_items": ["unit_id INTEGER", "unit_factor FLOAT DEFAULT 1.0"],
            "sales_invoice_items": ["unit_id INTEGER", "unit_factor FLOAT DEFAULT 1.0"],
            "purchase_invoice_items": ["unit_id INTEGER", "unit_factor FLOAT DEFAULT 1.0"],
            "company_settings": ["logo_path VARCHAR(500)", "zatca_enabled BOOLEAN DEFAULT 0",
                                  "zatca_environment VARCHAR(20) DEFAULT 'sandbox'", "zatca_api_url VARCHAR(300)",
                                  "zatca_username VARCHAR(200)", "zatca_password VARCHAR(500)",
                                  "smtp_host VARCHAR(200)", "smtp_port INTEGER DEFAULT 587",
                                  "smtp_username VARCHAR(200)", "smtp_password VARCHAR(500)",
                                  "smtp_from_email VARCHAR(200)", "smtp_use_tls BOOLEAN DEFAULT 1",
                                  "print_paper_size VARCHAR(20) DEFAULT 'a4'", "print_color VARCHAR(20) DEFAULT '#1A7A5E'",
                                  "print_show_logo BOOLEAN DEFAULT 1", "print_show_qr BOOLEAN DEFAULT 1",
                                  "print_font_size VARCHAR(10) DEFAULT 'normal'", "print_footer_note TEXT",
                                  "annual_leave_days INTEGER DEFAULT 21", "payroll_day_basis INTEGER DEFAULT 30", "weekly_off_days VARCHAR(20) DEFAULT '4,5'"],
            "customers": ["email VARCHAR(200)", "account_id INTEGER", "party_type VARCHAR(10) DEFAULT 'individual'", "price_list_id INTEGER", "loyalty_enabled BOOLEAN DEFAULT 0", "loyalty_points FLOAT DEFAULT 0", "notify_opt_in BOOLEAN DEFAULT 0", "credit_limit FLOAT DEFAULT 0", "credit_days INTEGER DEFAULT 0", "credit_hold BOOLEAN DEFAULT 0",
                          "crn VARCHAR(30) DEFAULT ''", "building_no VARCHAR(10) DEFAULT ''", "district VARCHAR(100) DEFAULT ''", "city VARCHAR(100) DEFAULT ''", "postal_code VARCHAR(10) DEFAULT ''"],
            "employees": ["cost_center_id INTEGER", "device_user_id VARCHAR(30) DEFAULT ''"],
            "suppliers": ["account_id INTEGER", "party_type VARCHAR(10) DEFAULT 'individual'", "iban VARCHAR(40) DEFAULT ''", "bank_name VARCHAR(100) DEFAULT ''"],
            "accounting_settings": ["cash_account_id INTEGER", "retained_earnings_account_id INTEGER",
                                     "salary_expense_account_id INTEGER", "salaries_payable_account_id INTEGER",
                                     "gosi_payable_account_id INTEGER", "sales_discount_account_id INTEGER",
                                     "purchase_discount_account_id INTEGER", "employee_advances_account_id INTEGER", "employee_custody_account_id INTEGER", "prepaid_expenses_account_id INTEGER",
                                     "asset_loss_account_id INTEGER", "leave_deduction_account_id INTEGER"],
            "fiscal_periods": ["closing_journal_id INTEGER"],
            "journal_entries": ["branch_id INTEGER"],
            "journal_entry_lines": ["branch_id INTEGER", "cost_center_id INTEGER", "partner_type VARCHAR(10)", "partner_id INTEGER"],
            "sales_invoices": ["branch_id INTEGER", "cost_center_id INTEGER", "is_pos BOOLEAN DEFAULT 0",
                                "payment_method VARCHAR(20)", "pos_terminal_id INTEGER", "cashier_employee_id INTEGER", "pos_session_id INTEGER", "zatca_status VARCHAR(20) DEFAULT 'not_sent'",
                                "zatca_response TEXT", "voided BOOLEAN DEFAULT 0", "promo_code VARCHAR(40) DEFAULT ''", "promo_discount FLOAT DEFAULT 0",
                                "promo_note VARCHAR(200) DEFAULT ''", "promo_approved_by VARCHAR(100) DEFAULT ''", "client_uuid VARCHAR(40)",
                                "currency VARCHAR(5)", "exchange_rate FLOAT", "foreign_total FLOAT"],
            "purchase_invoices": ["branch_id INTEGER", "cost_center_id INTEGER", "voided BOOLEAN DEFAULT 0", "currency VARCHAR(5)", "exchange_rate FLOAT", "foreign_total FLOAT"],
            "stock_moves": ["branch_id INTEGER", "cost_center_id INTEGER", "voided BOOLEAN DEFAULT 0",
                            "unit_id INTEGER", "unit_factor FLOAT DEFAULT 1.0"],
            "payments": ["branch_id INTEGER", "cost_center_id INTEGER", "voided BOOLEAN DEFAULT 0", "currency VARCHAR(5)", "exchange_rate FLOAT", "foreign_amount FLOAT"],
            "inventory_adjustments": ["branch_id INTEGER", "cost_center_id INTEGER"],
            "users": ["branch_ids TEXT", "cost_center_ids TEXT", "totp_secret VARCHAR(64)", "totp_enabled BOOLEAN DEFAULT 0", "recovery_codes TEXT", "totp_last_step INTEGER DEFAULT 0"],
            "locations": ["branch_id INTEGER", "cost_center_id INTEGER", "is_active BOOLEAN DEFAULT 1"],
            "accounts": ["cash_flow_type VARCHAR(15)"],
            "contracts": ["basic_salary_account_id INTEGER", "housing_allowance_account_id INTEGER",
                          "transport_allowance_account_id INTEGER", "other_allowances_account_id INTEGER",
                          "gosi_deduction_account_id INTEGER", "other_deductions_account_id INTEGER",
                          "gosi_rate_employer REAL DEFAULT 11.75", "gosi_employer_expense_account_id INTEGER",
                          "gosi_employer_payable_account_id INTEGER",
                          "leave_provision_rate REAL DEFAULT 8.33", "leave_provision_expense_account_id INTEGER",
                          "leave_provision_payable_account_id INTEGER",
                          "eos_provision_rate REAL DEFAULT 8.33", "eos_provision_expense_account_id INTEGER",
                          "eos_provision_payable_account_id INTEGER",
                          "renewed_from_id INTEGER", "renewal_count INTEGER DEFAULT 0", "previous_gross_salary REAL",
                          "raise_amount REAL DEFAULT 0", "raise_note VARCHAR(300) DEFAULT ''",
                          "termination_date DATETIME", "termination_reason VARCHAR(300) DEFAULT ''"],
            "custody_fundings": ["number VARCHAR(30) DEFAULT ''"],
            "allowance_insurance_items": ["leave_provision_amount REAL DEFAULT 0", "leave_provision_expense_account_id INTEGER",
                          "leave_provision_payable_account_id INTEGER", "eos_provision_amount REAL DEFAULT 0",
                          "eos_provision_expense_account_id INTEGER", "eos_provision_payable_account_id INTEGER"],
            "fixed_assets": ["purchase_invoice_id INTEGER", "category_id INTEGER"],
            "payroll_runs": ["paid_at DATETIME", "payment_id INTEGER"],
            "asset_categories": ["code_start VARCHAR(30)", "code_prefix VARCHAR(30)", "code_width INTEGER", "code_next INTEGER"],
            "asset_inventory_lines": ["disposal_journal_id INTEGER", "disposed_at DATETIME", "disposal_loss REAL DEFAULT 0"],
            "restaurant_order_items": ["void_reason VARCHAR(200)", "voided_by VARCHAR(100)", "approved_by VARCHAR(100)", "voided_at DATETIME", "served_at DATETIME"],
            "restaurant_orders": ["order_type VARCHAR(20) DEFAULT 'dine_in'", "customer_name VARCHAR(150)", "customer_phone VARCHAR(40)", "delivery_address VARCHAR(300)", "terminal_id INTEGER", "pos_session_id INTEGER"],
            "payslips": ["basic_salary_account_id INTEGER", "housing_allowance_account_id INTEGER",
                        "transport_allowance_account_id INTEGER", "other_allowances_account_id INTEGER",
                        "gosi_deduction_account_id INTEGER", "other_deductions_account_id INTEGER",
                        "paid_at DATETIME", "payment_id INTEGER",
                        "leave_deduction REAL DEFAULT 0", "leave_deduction_days REAL DEFAULT 0",
                        "absent_days REAL DEFAULT 0", "absence_deduction REAL DEFAULT 0", "unemployed_days REAL DEFAULT 0",
                        "unemployed_deduction REAL DEFAULT 0", "leave_days_total REAL DEFAULT 0", "worked_days REAL DEFAULT 0"],
            "cost_centers": ["branch_id INTEGER"],
        }
        table_cols = {table: ({c["name"] for c in inspector.get_columns(table)} if inspector.has_table(table) else set()) for table in additions}
        for table, columns in additions.items():
            if not inspector.has_table(table):
                continue
            for definition in columns:
                name = definition.split()[0]
                if name not in table_cols[table]:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {_ddl(definition)}"))


def _seed_product_account_links():
    session = SessionLocal()
    try:
        cfg = session.get(AccountingSettings, 1)
        if not cfg:
            return
        products = session.query(Product).filter(
            (Product.sales_account_id.is_(None)) |
            (Product.inventory_account_id.is_(None)) |
            (Product.cogs_account_id.is_(None))
        ).all()
        for p in products:
            if p.sales_account_id is None: p.sales_account_id = cfg.sales_account_id
            if p.inventory_account_id is None: p.inventory_account_id = cfg.inventory_account_id
            if p.cogs_account_id is None: p.cogs_account_id = cfg.cogs_account_id
        session.commit()
    finally:
        session.close()


def _seed_product_unit_lines():
    session = SessionLocal()
    try:
        units = {u.name: u for u in session.query(ProductUnit).all()}
        # الأصناف اللي ملهاش أسطر وحدات بس (استعلام واحد) - الطريقة القديمة كانت بتفتح أسطر كل صنف لوحده
        # فبتاخد ثواني في كل تشغيل مع آلاف الأصناف
        from sqlalchemy import exists
        missing = session.query(Product).filter(~exists().where(ProductUnitLine.product_id == Product.id)).all()
        for p in missing:
            u = units.get(p.unit)
            if u:
                session.add(ProductUnitLine(product_id=p.id, unit_id=u.id, factor_to_base=1.0,
                                             sale_price=p.sale_price, cost_price=p.cost_price, is_default=True))
        session.commit()
    finally:
        session.close()


def _seed_fiscal_period():
    session = SessionLocal()
    try:
        if session.query(FiscalPeriod).count() == 0:
            year = datetime.datetime.now().year
            session.add(FiscalPeriod(name=f"السنة المالية {year}", date_from=datetime.datetime(year,1,1), date_to=datetime.datetime(year,12,31,23,59,59)))
            session.commit()
    finally:
        session.close()


def _backfill_org_links():
    """ربط البيانات القديمة بالفرع والمركز الافتراضيين دون حذف أي بيانات."""
    session = SessionLocal()
    try:
        branch = session.query(Branch).filter(Branch.is_default.is_(True)).first() or session.query(Branch).first()
        center = session.query(CostCenter).first()
        if branch:
            for model in (SalesInvoice, PurchaseInvoice, StockMove, Payment, InventoryAdjustment, JournalEntry, Location):
                if hasattr(model, "branch_id"):
                    session.query(model).filter(model.branch_id.is_(None)).update({model.branch_id: branch.id}, synchronize_session=False)
        if center:
            for model in (SalesInvoice, PurchaseInvoice, StockMove, Payment, InventoryAdjustment):
                if hasattr(model, "cost_center_id"):
                    session.query(model).filter(model.cost_center_id.is_(None)).update({model.cost_center_id: center.id}, synchronize_session=False)
            session.query(JournalEntryLine).filter(JournalEntryLine.cost_center_id.is_(None)).update({JournalEntryLine.cost_center_id: center.id}, synchronize_session=False)
        if branch:
            session.query(JournalEntryLine).filter(JournalEntryLine.branch_id.is_(None)).update({JournalEntryLine.branch_id: branch.id}, synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _seed_budget_defaults():
    session = SessionLocal()
    try:
        # Ensure the default user has an unrestricted cost-center scope.
        u=session.query(User).filter(User.username=="admin").first()
        if u and not getattr(u, "cost_center_ids", None): u.cost_center_ids=json.dumps([], ensure_ascii=False)
        session.commit()
    finally:
        session.close()


def _seed_leave_types():
    """الأنواع الأساسية بنفس سلوك الإصدارات القديمة (سنوية: من الرصيد، مرضية: مدفوعة، بدون راتب: خصم 100%)."""
    session = SessionLocal()
    try:
        if session.query(LeaveType).count():
            return
        for i, (code, name, pct, bal) in enumerate([("annual", "إجازة سنوية", 0, True), ("sick", "إجازة مرضية", 0, False), ("unpaid", "إجازة بدون راتب", 100, False)]):
            session.add(LeaveType(code=code, name=name, deduct_percent=pct, uses_annual_balance=bal, is_system=True, sort_order=(i + 1) * 10))
        session.commit()
    finally:
        session.close()


def get_session():
    return SessionLocal()


# ---- قفل الترقيم: ترقيم الفواتير/القيود بيقرا "آخر رقم + 1"، فلو جلستين في نفس اللحظة هيطلعوا نفس الرقم.
# القفل بيتاخد عند حساب الرقم وبيتفك مع نهاية معاملة الجلسة (commit/rollback/close) - فجلسة تانية بتستنى وبعدين بتقرا آخر رقم محدّث.
import threading as _threading
from sqlalchemy.orm import Session as _Session

_NUM_LOCK = _threading.RLock()


def lock_numbering(session, timeout=30):
    if session.info.get("_numlock"):
        return
    if not IS_SQLITE:
        # PostgreSQL: قفل استشاري على مستوى المعاملة (بيتفك تلقائيًا مع commit/rollback) - شغال حتى لو فيه أكتر من سيرفر على نفس القاعدة
        from sqlalchemy import text as _t
        session.execute(_t("SELECT pg_advisory_xact_lock(727001)"))
        session.info["_numlock"] = "pg"
        return
    if _NUM_LOCK.acquire(timeout=timeout):
        session.info["_numlock"] = True
    # لو القفل اتأخر أكتر من المهلة نكمّل بدونه (أحسن من تعليق السيرفر) - أسوأ احتمال خطأ تكرار رقم بيظهر للمستخدم


@_sa_event.listens_for(_Session, "after_transaction_end")
def _release_numbering(session, transaction):
    if transaction.parent is None and session.info.pop("_numlock", False) is True:
        try:
            _NUM_LOCK.release()
        except RuntimeError:
            pass

# ============================== Accounting ==============================
class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    code = Column(String(32), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    account_type = Column(String(32), nullable=False)  # asset/liability/equity/income/expense
    parent_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    cash_flow_type = Column(String(15), nullable=True)  # cash | operating | investing | financing
    parent = relationship("Account", remote_side=[id], backref="children")


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    id = Column(Integer, primary_key=True)
    number = Column(String(40), nullable=False, unique=True)
    date = Column(DateTime, default=_now)
    reference = Column(String(120), default="")
    description = Column(Text, default="")
    source_type = Column(String(40), default="manual")
    source_id = Column(Integer, nullable=True)
    posted = Column(Boolean, default=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    branch = relationship("Branch")
    lines = relationship("JournalEntryLine", back_populates="entry", cascade="all, delete-orphan")


class JournalEntryLine(Base):
    __tablename__ = "journal_entry_lines"
    id = Column(Integer, primary_key=True)
    entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    description = Column(String(255), default="")
    debit = Column(Float, default=0.0)
    credit = Column(Float, default=0.0)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    partner_type = Column(String(10), nullable=True)  # 'customer' | 'supplier' | None
    partner_id = Column(Integer, nullable=True)
    entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account")


class AccountingSettings(Base):
    __tablename__ = "accounting_settings"
    id = Column(Integer, primary_key=True)
    receivable_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    payable_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    sales_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    purchases_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    inventory_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    cogs_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    vat_input_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    vat_output_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    cash_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    retained_earnings_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    inventory_gain_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    inventory_loss_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    salary_expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    salaries_payable_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    gosi_payable_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    sales_discount_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    purchase_discount_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    employee_advances_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    asset_loss_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)   # خسائر استبعاد الأصول (عجز الجرد)
    employee_custody_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)   # عهد الموظفين
    prepaid_expenses_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)   # مصاريف مدفوعة مقدمًا
    leave_deduction_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)    # خصم الإجازات من الرواتب (لو فاضي: حساب الخصومات الأخرى في العقد)


class EmployeeCustody(Base):
    """عهدة موظف: مبلغ بيتصرف للموظف من الخزينة/البنك ينفقه على مصروفات
    الشركة، وبعدها بيقدّم مصروفات أو فواتير عليها (بموافقة المحاسب) والباقي
    بيرجع أو بيتقفل. الرصيد = الوارد (صرف + تعزيز) - المصروفات المعتمدة - المرتجع."""
    __tablename__ = "employee_custodies"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    date = Column(DateTime, default=_now)
    purpose = Column(String(300), default="")
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    state = Column(String(20), default="open")   # open | closed
    closed_at = Column(DateTime, nullable=True)
    created_by = Column(String(100), default="")

    employee = relationship("Employee")
    fundings = relationship("CustodyFunding", back_populates="custody", cascade="all, delete-orphan", order_by="CustodyFunding.id")
    expenses = relationship("CustodyExpense", back_populates="custody", cascade="all, delete-orphan", order_by="CustodyExpense.id")


class CustodyFunding(Base):
    """حركة تمويل للعهدة: issue (صرف أولي) | topup (تعزيز) | return (مرتجع للخزينة)."""
    __tablename__ = "custody_fundings"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), default="")      # رقم سند الصرف/التعزيز/الإرجاع (CPV-.. / CRV-..)
    custody_id = Column(Integer, ForeignKey("employee_custodies.id"), nullable=False)
    kind = Column(String(10), nullable=False)
    date = Column(DateTime, default=_now)
    amount = Column(Float, default=0.0)
    cash_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    payment_method_name = Column(String(100), default="")
    notes = Column(String(300), default="")
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)

    custody = relationship("EmployeeCustody", back_populates="fundings")
    cash_account = relationship("Account", foreign_keys=[cash_account_id])


class CustodySettlement(Base):
    """مستند تسوية عهدة: بيقفل العهدة بعد مطابقة الوارد بالمصروف المعتمد وإرجاع المتبقي
    (لو فيه) للخزينة بقيد إرجاع، وبيتطبع كسند تسوية فيه تفاصيل المصروفات."""
    __tablename__ = "custody_settlements"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    custody_id = Column(Integer, ForeignKey("employee_custodies.id"), nullable=False)
    date = Column(DateTime, default=_now)
    funded = Column(Float, default=0.0)           # إجمالي الوارد (صرف + تعزيز)
    spent = Column(Float, default=0.0)            # المصروف المعتمد
    returned_before = Column(Float, default=0.0)  # مرتجعات سابقة قبل التسوية
    returned_now = Column(Float, default=0.0)     # المرتجع في التسوية نفسها
    notes = Column(String(300), default="")
    return_funding_id = Column(Integer, ForeignKey("custody_fundings.id"), nullable=True)
    created_by = Column(String(100), default="")

    custody = relationship("EmployeeCustody")


class CustodyExpense(Base):
    """مصروف أو فاتورة على عهدة. expense_type: expense (مصروف بسيط) | invoice
    (فاتورة مورد بضريبة). state: pending (مقدَّم للمراجعة) → approved (اتقيّد
    محاسبيًا) | rejected."""
    __tablename__ = "custody_expenses"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    custody_id = Column(Integer, ForeignKey("employee_custodies.id"), nullable=False)
    expense_type = Column(String(10), default="expense")
    date = Column(DateTime, default=_now)
    description = Column(String(300), default="")
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    amount = Column(Float, default=0.0)       # قبل الضريبة (للمصروف البسيط = الإجمالي)
    tax_rate = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    supplier_name = Column(String(200), default="")
    supplier_vat = Column(String(50), default="")
    invoice_number = Column(String(80), default="")
    invoice_date = Column(DateTime, nullable=True)
    attachment_path = Column(String(500), default="")
    state = Column(String(20), default="pending")   # pending | approved | rejected
    decided_at = Column(DateTime, nullable=True)
    decided_by = Column(String(100), default="")
    decision_note = Column(String(300), default="")
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    created_by = Column(String(100), default="")

    custody = relationship("EmployeeCustody", back_populates="expenses")
    account = relationship("Account", foreign_keys=[account_id])
    supplier = relationship("Supplier")


class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True)
    code = Column(String(30), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    national_id = Column(String(30), default="")
    phone = Column(String(30), default="")
    email = Column(String(120), default="")
    position = Column(String(120), default="")
    department = Column(String(120), default="")
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    hire_date = Column(DateTime, nullable=True)
    bank_account = Column(String(60), default="")
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    device_user_id = Column(String(30), default="")      # رقم الموظف على جهاز البصمة

    branch = relationship("Branch")
    cost_center = relationship("CostCenter")
    contracts = relationship("Contract", back_populates="employee", cascade="all, delete-orphan")


class AttendanceDevice(Base):
    """جهاز بصمة (ZKTeco وأشباهه): بيبعت البصمات للسيرفر (ADMS push) أو بنسحبها منه بالـ IP."""
    __tablename__ = "attendance_devices"
    id = Column(Integer, primary_key=True)
    serial = Column(String(60), nullable=False, unique=True)
    name = Column(String(100), default="")
    host = Column(String(100), default="")               # للسحب المباشر (اختياري)
    port = Column(Integer, default=4370)
    enabled = Column(Boolean, default=False)             # الجهاز الجديد بيبان "بانتظار الموافقة" ومفيش بصمات بتتسجّل منه لحد ما تفعّله
    last_seen = Column(DateTime, nullable=True)
    last_ip = Column(String(60), default="")
    last_count = Column(Integer, default=0)


class AttendanceLog(Base):
    """بصمة واحدة (دخول أو خروج - الجهاز مش دايمًا بيفرّق). التكرار ممنوع بنفس الرقم والوقت."""
    __tablename__ = "attendance_logs"
    __table_args__ = (UniqueConstraint("norm_id", "punch_time", name="uq_attendance_punch"),)
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    device_user_id = Column(String(30), nullable=False)
    norm_id = Column(String(30), nullable=False, index=True)   # الرقم من غير أصفار في الأول - للمطابقة
    punch_time = Column(DateTime, nullable=False, index=True)
    source = Column(String(20), default="file")           # device | pull | file | manual
    device_serial = Column(String(60), default="")


class Holiday(Base):
    """إجازة رسمية (بتتحسب مش غياب)."""
    __tablename__ = "holidays"
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=False, unique=True)
    name = Column(String(120), default="")


class Contract(Base):
    __tablename__ = "contracts"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    contract_number = Column(String(40), nullable=False, unique=True)
    contract_type = Column(String(20), default="permanent")  # permanent | temporary
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    basic_salary = Column(Float, default=0.0)
    housing_allowance = Column(Float, default=0.0)
    transport_allowance = Column(Float, default=0.0)
    other_allowances = Column(Float, default=0.0)
    gosi_rate_employee = Column(Float, default=9.75)   # % حسم الموظف (تأمينات)
    gosi_rate_employer = Column(Float, default=11.75)  # % نصيب صاحب العمل (تأمينات) - مصروف على الشركة بالكامل
    leave_provision_rate = Column(Float, default=8.33)  # % مخصص الإجازة الشهري (افتراضي = شهر إجازة سنويًا تقريبًا)
    eos_provision_rate = Column(Float, default=8.33)    # % مخصص نهاية الخدمة الشهري
    state = Column(String(20), default="active")  # active | expired | renewed | terminated
    # سلسلة التجديد: كل عقد مجدَّد بيحتفظ بربط للعقد السابق وبالراتب السابق
    # والزيادة اللي اتطبقت وقت التجديد - فتاريخ الرواتب كله يفضل محفوظ.
    renewed_from_id = Column(Integer, ForeignKey("contracts.id"), nullable=True)
    renewal_count = Column(Integer, default=0)
    previous_gross_salary = Column(Float, nullable=True)
    raise_amount = Column(Float, default=0.0)
    raise_note = Column(String(300), default="")
    # بيانات الإنهاء
    termination_date = Column(DateTime, nullable=True)
    termination_reason = Column(String(300), default="")
    # حساب مستقل لكل عنصر - إجباري لأي عنصر قيمته أكبر من صفر
    basic_salary_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    housing_allowance_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    transport_allowance_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    other_allowances_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    gosi_deduction_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    other_deductions_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    gosi_employer_expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)   # تأمينات - مدين (مصروف)
    gosi_employer_payable_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)   # تأمينات - دائن (مستحق)
    leave_provision_expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)  # مخصص إجازة - مدين (مصروف)
    leave_provision_payable_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)  # مخصص إجازة - دائن (مستحق)
    eos_provision_expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)    # مخصص نهاية خدمة - مدين (مصروف)
    eos_provision_payable_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)    # مخصص نهاية خدمة - دائن (مستحق)

    employee = relationship("Employee", back_populates="contracts")
    basic_salary_account = relationship("Account", foreign_keys=[basic_salary_account_id])
    housing_allowance_account = relationship("Account", foreign_keys=[housing_allowance_account_id])
    transport_allowance_account = relationship("Account", foreign_keys=[transport_allowance_account_id])
    other_allowances_account = relationship("Account", foreign_keys=[other_allowances_account_id])
    gosi_deduction_account = relationship("Account", foreign_keys=[gosi_deduction_account_id])
    other_deductions_account = relationship("Account", foreign_keys=[other_deductions_account_id])
    gosi_employer_expense_account = relationship("Account", foreign_keys=[gosi_employer_expense_account_id])
    gosi_employer_payable_account = relationship("Account", foreign_keys=[gosi_employer_payable_account_id])
    leave_provision_expense_account = relationship("Account", foreign_keys=[leave_provision_expense_account_id])
    leave_provision_payable_account = relationship("Account", foreign_keys=[leave_provision_payable_account_id])
    eos_provision_expense_account = relationship("Account", foreign_keys=[eos_provision_expense_account_id])
    eos_provision_payable_account = relationship("Account", foreign_keys=[eos_provision_payable_account_id])

    @property
    def gross_salary(self):
        return (self.basic_salary or 0) + (self.housing_allowance or 0) + (self.transport_allowance or 0) + (self.other_allowances or 0)


class PayrollRun(Base):
    """دورة رواتب شهرية"""
    __tablename__ = "payroll_runs"
    id = Column(Integer, primary_key=True)
    number = Column(String(40), nullable=False, unique=True)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    date = Column(DateTime, default=_now)
    state = Column(String(20), default="draft")  # draft | posted
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    paid_at = Column(DateTime, nullable=True)            # وقت صرف الرواتب فعليًا (بعد الترحيل)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True)   # سند الصرف المرتبط

    payslips = relationship("Payslip", back_populates="run", cascade="all, delete-orphan")


class Payslip(Base):
    """قسيمة راتب موظف واحد ضمن دورة رواتب"""
    __tablename__ = "payslips"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("payroll_runs.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=True)
    basic_salary = Column(Float, default=0.0)
    housing_allowance = Column(Float, default=0.0)
    transport_allowance = Column(Float, default=0.0)
    other_allowances = Column(Float, default=0.0)
    gosi_deduction = Column(Float, default=0.0)
    other_deductions = Column(Float, default=0.0)
    leave_deduction = Column(Float, default=0.0)          # خصم الإجازات (محسوب من الإجازات المعتمدة حسب نوع كل إجازة)
    leave_deduction_days = Column(Float, default=0.0)     # أيام الإجازة اللي اتخصمت (بعد ضرب النسبة)
    absent_days = Column(Float, default=0.0)              # أيام غياب بدون إذن (بتتسجل يدويًا قبل الترحيل)
    absence_deduction = Column(Float, default=0.0)
    unemployed_days = Column(Float, default=0.0)          # أيام الشهر اللي الموظف مكانش فيها على عقد (تعيين/إنهاء في نص الشهر)
    unemployed_deduction = Column(Float, default=0.0)
    leave_days_total = Column(Float, default=0.0)         # كل أيام الإجازة المعتمدة في الشهر (مدفوعة وغير مدفوعة) - للعرض
    worked_days = Column(Float, default=0.0)              # أيام العمل الفعلي = أيام الشهر على العقد − الإجازات − الغياب
    net_salary = Column(Float, default=0.0)
    basic_salary_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    housing_allowance_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    transport_allowance_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    other_allowances_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    gosi_deduction_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    other_deductions_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    paid_at = Column(DateTime, nullable=True)             # وقت صرف صافي راتب الموظف ده تحديدًا
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True)   # سند الصرف اللي اتصرف بيه

    run = relationship("PayrollRun", back_populates="payslips")
    employee = relationship("Employee")
    contract = relationship("Contract")
    basic_salary_account = relationship("Account", foreign_keys=[basic_salary_account_id])
    housing_allowance_account = relationship("Account", foreign_keys=[housing_allowance_account_id])
    transport_allowance_account = relationship("Account", foreign_keys=[transport_allowance_account_id])
    other_allowances_account = relationship("Account", foreign_keys=[other_allowances_account_id])
    gosi_deduction_account = relationship("Account", foreign_keys=[gosi_deduction_account_id])
    other_deductions_account = relationship("Account", foreign_keys=[other_deductions_account_id])

    @property
    def gross_salary(self):
        return (self.basic_salary or 0) + (self.housing_allowance or 0) + (self.transport_allowance or 0) + (self.other_allowances or 0)

    @property
    def total_deductions(self):
        return ((self.gosi_deduction or 0) + (self.other_deductions or 0) + (self.leave_deduction or 0)
                + (self.absence_deduction or 0) + (self.unemployed_deduction or 0))


class AllowanceInsuranceRun(Base):
    """دورة مخصصات وتأمينات - منفصلة عن دورة الرواتب الشهرية، بتغطي
    مخصصات إضافية (مكافآت/بدلات استثنائية خارج الراتب الشهري) ونصيب صاحب
    العمل في التأمينات الاجتماعية (مصروف على الشركة، مش خصم من الموظف)."""
    __tablename__ = "allowance_insurance_runs"
    id = Column(Integer, primary_key=True)
    number = Column(String(40), nullable=False, unique=True)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    date = Column(DateTime, default=_now)
    state = Column(String(20), default="draft")  # draft | posted
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)

    items = relationship("AllowanceInsuranceItem", back_populates="run", cascade="all, delete-orphan")


class AllowanceInsuranceItem(Base):
    """بند مخصصات وتأمينات لموظف واحد ضمن دورة - مخصص إضافي (بمبلغ وحساب
    مصروف يحدده المستخدم وقت الإدخال) + نصيب صاحب العمل في التأمينات +
    مخصص إجازة + مخصص نهاية خدمة (الثلاثة محسوبين تلقائياً من نسب العقد،
    كل واحد بحساب مصروف (مدين) وحساب مستحق (دائن) مستقلين)."""
    __tablename__ = "allowance_insurance_items"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("allowance_insurance_runs.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=True)
    extra_allowance = Column(Float, default=0.0)
    extra_allowance_note = Column(String(200), default="")
    extra_allowance_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    employer_gosi_amount = Column(Float, default=0.0)
    employer_gosi_expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    employer_gosi_payable_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    leave_provision_amount = Column(Float, default=0.0)
    leave_provision_expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    leave_provision_payable_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    eos_provision_amount = Column(Float, default=0.0)
    eos_provision_expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    eos_provision_payable_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)

    run = relationship("AllowanceInsuranceRun", back_populates="items")
    employee = relationship("Employee")
    contract = relationship("Contract")
    extra_allowance_account = relationship("Account", foreign_keys=[extra_allowance_account_id])
    employer_gosi_expense_account = relationship("Account", foreign_keys=[employer_gosi_expense_account_id])
    employer_gosi_payable_account = relationship("Account", foreign_keys=[employer_gosi_payable_account_id])
    leave_provision_expense_account = relationship("Account", foreign_keys=[leave_provision_expense_account_id])
    leave_provision_payable_account = relationship("Account", foreign_keys=[leave_provision_payable_account_id])
    eos_provision_expense_account = relationship("Account", foreign_keys=[eos_provision_expense_account_id])
    eos_provision_payable_account = relationship("Account", foreign_keys=[eos_provision_payable_account_id])

    @property
    def total(self):
        return (self.extra_allowance or 0) + (self.employer_gosi_amount or 0) + (self.leave_provision_amount or 0) + (self.eos_provision_amount or 0)


class AssetCategory(Base):
    """فئة أصول ثابتة - جدول مستقل بيحمل الحسابات الثلاثة (الأصل، مجمّع
    الإهلاك، مصروف الإهلاك) والعمر الإنتاجي ونسبة القيمة التخريدية، عشان
    الأصل يختار الفئة بس وميدخلش الحسابات والعمر والقيمة التخريدية كل مرة."""
    __tablename__ = "asset_categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    useful_life_months = Column(Integer, default=60)
    salvage_percent = Column(Float, default=0.0)   # % من تكلفة الأصل
    asset_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    accumulated_depreciation_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    depreciation_expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    # تسلسل كود الأصول لكل فئة: المستخدم بيكتب أول كود (code_start) والباقي بيتحسب تلقائي
    code_start = Column(String(30), nullable=True)    # أول كود زي ما اتكتب (مثلاً LAP-0001)
    code_prefix = Column(String(30), nullable=True)   # الجزء النصي قبل الرقم (LAP-)
    code_width = Column(Integer, nullable=True)       # عدد خانات الرقم (4 => 0001)
    code_next = Column(Integer, nullable=True)        # الرقم التالي اللي هيتاخد

    asset_account = relationship("Account", foreign_keys=[asset_account_id])
    accumulated_depreciation_account = relationship("Account", foreign_keys=[accumulated_depreciation_account_id])
    depreciation_expense_account = relationship("Account", foreign_keys=[depreciation_expense_account_id])


class FixedAsset(Base):
    """أصل ثابت - بيتسجّل بتكلفته وعمره الإنتاجي وحساباته الثلاثة (الأصل
    نفسه، مجمّع الإهلاك، مصروف الإهلاك)، وبيتراكم إهلاكه شهريًا عن طريق
    دورة إهلاك دورية (زي دورة الرواتب بالظبط) بطريقة القسط الثابت."""
    __tablename__ = "fixed_assets"
    id = Column(Integer, primary_key=True)
    code = Column(String(30), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    category = Column(String(100), default="")   # اسم الفئة (نسخة للعرض)
    category_id = Column(Integer, ForeignKey("asset_categories.id"), nullable=True)
    purchase_date = Column(DateTime, nullable=False)
    cost = Column(Float, default=0.0)
    salvage_value = Column(Float, default=0.0)
    useful_life_months = Column(Integer, default=60)  # 5 سنوات افتراضيًا
    accumulated_depreciation = Column(Float, default=0.0)
    state = Column(String(20), default="active")  # active | fully_depreciated | disposed
    disposal_date = Column(DateTime, nullable=True)
    disposal_amount = Column(Float, default=0.0)
    notes = Column(Text, default="")
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    purchase_invoice_id = Column(Integer, ForeignKey("purchase_invoices.id"), nullable=True)
    asset_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    accumulated_depreciation_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    depreciation_expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)

    branch = relationship("Branch")
    cost_center = relationship("CostCenter")
    purchase_invoice = relationship("PurchaseInvoice")
    asset_account = relationship("Account", foreign_keys=[asset_account_id])
    accumulated_depreciation_account = relationship("Account", foreign_keys=[accumulated_depreciation_account_id])
    depreciation_expense_account = relationship("Account", foreign_keys=[depreciation_expense_account_id])

    @property
    def depreciable_amount(self):
        return max(0.0, (self.cost or 0) - (self.salvage_value or 0))

    @property
    def monthly_depreciation(self):
        if not self.useful_life_months:
            return 0.0
        return round(self.depreciable_amount / self.useful_life_months, 2)

    @property
    def net_book_value(self):
        return max(0.0, (self.cost or 0) - (self.accumulated_depreciation or 0))


class DepreciationRun(Base):
    """دورة إهلاك شهرية - بند لكل أصل نشط لسه ماوصلش لكامل قيمته القابلة
    للإهلاك، بقيمة القسط الشهري المحسوب تلقائيًا بطريقة القسط الثابت."""
    __tablename__ = "depreciation_runs"
    id = Column(Integer, primary_key=True)
    number = Column(String(40), nullable=False, unique=True)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    date = Column(DateTime, default=_now)
    state = Column(String(20), default="draft")  # draft | posted
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)

    items = relationship("DepreciationRunItem", back_populates="run", cascade="all, delete-orphan")


class DepreciationRunItem(Base):
    __tablename__ = "depreciation_run_items"
    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("depreciation_runs.id"), nullable=False)
    asset_id = Column(Integer, ForeignKey("fixed_assets.id"), nullable=False)
    amount = Column(Float, default=0.0)
    expense_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    accumulated_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)

    run = relationship("DepreciationRun", back_populates="items")
    asset = relationship("FixedAsset")
    expense_account = relationship("Account", foreign_keys=[expense_account_id])
    accumulated_account = relationship("Account", foreign_keys=[accumulated_account_id])


class AssetInventory(Base):
    """جلسة جرد أصول ثابتة: بتاخد لقطة من الأصول المتوقعة وقت البدء (حسب النطاق)
    وبعدين بتتسجّل عليها عمليات مسح الباركود. الفرق بين المتوقع والموجود = عجز،
    وأي حاجة اتمسحت وهي مش ضمن المتوقع = زيادة."""
    __tablename__ = "asset_inventories"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    date = Column(DateTime, default=_now)
    state = Column(String(20), default="open")      # open | closed
    scope_type = Column(String(20), default="all")  # all | category | branch | cost_center
    scope_id = Column(Integer, nullable=True)
    scope_label = Column(String(200), default="")
    notes = Column(Text, default="")
    created_by = Column(String(100), default="")
    closed_at = Column(DateTime, nullable=True)

    lines = relationship("AssetInventoryLine", back_populates="inventory", cascade="all, delete-orphan")


class AssetInventoryLine(Base):
    __tablename__ = "asset_inventory_lines"
    id = Column(Integer, primary_key=True)
    inventory_id = Column(Integer, ForeignKey("asset_inventories.id"), nullable=False)
    asset_id = Column(Integer, ForeignKey("fixed_assets.id"), nullable=True)   # فاضي لو الكود مش مسجّل
    code = Column(String(60), nullable=False)
    code_key = Column(String(60), nullable=False)    # الكود بحروف كبيرة للمطابقة من غير حساسية لحالة الحروف
    name = Column(String(200), default="")
    category = Column(String(100), default="")
    cost = Column(Float, default=0.0)
    book_value = Column(Float, default=0.0)          # صافي القيمة الدفترية وقت بدء الجرد
    kind = Column(String(10), default="expected")    # expected | extra
    extra_reason = Column(String(20), nullable=True) # out_of_scope | disposed | unknown
    scanned_at = Column(DateTime, nullable=True)
    scan_count = Column(Integer, default=0)
    method = Column(String(20), nullable=True)       # barcode | manual
    disposal_journal_id = Column(Integer, nullable=True)   # قيد استبعاد العجز (لو اتحوّل لاستبعاد)
    disposed_at = Column(DateTime, nullable=True)
    disposal_loss = Column(Float, default=0.0)             # الخسارة اللي اتسجّلت للأصل ده

    inventory = relationship("AssetInventory", back_populates="lines")
    __table_args__ = (Index("ix_asset_inv_lines_code", "inventory_id", "code_key"),)


class RestaurantSection(Base):
    """قسم صالة (زي: الصالة الرئيسية، التراس، الشرفة) - تجميع منطقي للطاولات."""
    __tablename__ = "restaurant_sections"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)


class RestaurantTable(Base):
    __tablename__ = "restaurant_tables"
    id = Column(Integer, primary_key=True)
    number = Column(String(20), nullable=False, unique=True)
    name = Column(String(100), default="")
    seats = Column(Integer, default=4)
    section_id = Column(Integer, ForeignKey("restaurant_sections.id"), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    is_active = Column(Boolean, default=True)

    section = relationship("RestaurantSection")
    branch = relationship("Branch")


class RestaurantOrder(Base):
    """طلب مطعم مفتوح على طاولة - بيتحوّل لفاتورة POS عادية عند الدفع
    (بيستخدم create_pos_sale نفسها)، وبيفضل مربوط بيها بعد كده للمراجعة."""
    __tablename__ = "restaurant_orders"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    table_id = Column(Integer, ForeignKey("restaurant_tables.id"), nullable=True)   # فاضي لطلبات تيك أواي/دليفري
    order_type = Column(String(20), default="dine_in")   # dine_in | takeaway | delivery
    customer_name = Column(String(150), default="")      # اسم العميل لطلبات تيك أواي/دليفري
    customer_phone = Column(String(40), default="")
    delivery_address = Column(String(300), default="")
    terminal_id = Column(Integer, ForeignKey("pos_terminals.id"), nullable=True)       # ماكينة/جلسة الطلب (نظام السشن)
    pos_session_id = Column(Integer, ForeignKey("pos_sessions.id"), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    guests = Column(Integer, default=1)
    state = Column(String(20), default="open")   # open | paid | voided
    opened_at = Column(DateTime, default=_now)
    closed_at = Column(DateTime, nullable=True)
    opened_by = Column(String(100), default="")
    notes = Column(Text, default="")
    sales_invoice_id = Column(Integer, ForeignKey("sales_invoices.id"), nullable=True)

    table = relationship("RestaurantTable")
    branch = relationship("Branch")
    sales_invoice = relationship("SalesInvoice")
    items = relationship("RestaurantOrderItem", back_populates="order", cascade="all, delete-orphan")


class Currency(Base):
    __tablename__ = "currencies"
    id = Column(Integer, primary_key=True)
    code = Column(String(5), nullable=False, unique=True)
    name = Column(String(60), default="")
    symbol = Column(String(10), default="")
    is_base = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)


class ExchangeRate(Base):
    """سعر عملة أجنبية مقابل الأساسية في تاريخ معيّن: rate = كام وحدة أساسية في 1 أجنبي (دولار = 3.75 ريال)."""
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("currency_code", "rate_date", name="uq_fx_rate"),)
    id = Column(Integer, primary_key=True)
    currency_code = Column(String(5), nullable=False, index=True)
    rate_date = Column(DateTime, nullable=False)
    rate = Column(Float, nullable=False)


class FxRevaluation(Base):
    """تسوية فروق العملة لطرف (عميل/مورد) وعملة: adjustment موجب = زاد المستحق (على العميل لنا / علينا للمورد) بالأساسي."""
    __tablename__ = "fx_revaluations"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=_now)
    reval_date = Column(DateTime, nullable=False)
    party_type = Column(String(10), nullable=False)
    party_id = Column(Integer, nullable=False, index=True)
    currency = Column(String(5), nullable=False)
    foreign_balance = Column(Float, default=0.0)
    rate = Column(Float, default=0.0)
    book_before = Column(Float, default=0.0)
    adjustment = Column(Float, default=0.0)
    journal_entry_id = Column(Integer, nullable=True)
    created_by = Column(String(80), default="")


class ApprovalRequest(Base):
    """طلب موافقة مدير قبل تنفيذ عملية كبيرة (مشتريات/صرف/تسوية جرد/تجاوز ائتمان). المنفّذ بيعيد العملية بعد الاعتماد والنظام بيطابقها بالبصمة (fingerprint) ويستهلك الموافقة مرة واحدة."""
    __tablename__ = "approval_requests"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=_now, index=True)
    kind = Column(String(24), nullable=False, index=True)
    fingerprint = Column(String(120), default="")
    amount = Column(Float, default=0.0)
    summary = Column(String(500), default="")
    requested_by = Column(String(80), default="")
    note = Column(String(300), default="")
    status = Column(String(10), default="pending", index=True)    # pending | approved | rejected | consumed | cancelled
    decided_by = Column(String(80), default="")
    decided_at = Column(DateTime, nullable=True)
    decision_note = Column(String(300), default="")
    consumed_at = Column(DateTime, nullable=True)


class NotificationLog(Base):
    """سجل الرسائل الصادرة (واتساب/SMS): pending → sent | failed | link (مفيش مزوّد: رابط واتساب يدوي)."""
    __tablename__ = "notification_log"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=_now, index=True)
    sent_at = Column(DateTime, nullable=True)
    channel = Column(String(10), default="whatsapp")      # whatsapp | sms
    provider = Column(String(20), default="")
    kind = Column(String(15), default="manual", index=True)   # receipt | low_stock | manual | test
    recipient = Column(String(30), default="")
    ref = Column(String(60), default="")
    body = Column(Text, default="")
    params = Column(Text, default="")                      # JSON: متغيرات القالب (لقوالب واتساب المعتمدة)
    status = Column(String(10), default="pending", index=True)
    attempts = Column(Integer, default=0)
    error = Column(Text, default="")


class DeliveryOrder(Base):
    """طلب توصيل وارد من تطبيق خارجي (webhook) أو يدوي: new → accepted (بيتحوّل لطلب دليفري في المطعم) → ready → dispatched → delivered | rejected."""
    __tablename__ = "delivery_orders"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_delivery_source_ext"),)
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=_now, index=True)
    updated_at = Column(DateTime, default=_now)
    source = Column(String(30), nullable=False, index=True)
    external_id = Column(String(80), nullable=False)
    customer_name = Column(String(150), default="")
    phone = Column(String(40), default="")
    address = Column(String(300), default="")
    notes = Column(String(400), default="")
    items_json = Column(Text, default="[]")              # [{sku,name,quantity,price,note}]
    total = Column(Float, default=0.0)                   # إجمالي التطبيق (للمطابقة فقط)
    payment = Column(String(20), default="")             # online | cash
    status = Column(String(12), default="new", index=True)
    restaurant_order_id = Column(Integer, nullable=True)
    reject_reason = Column(String(200), default="")
    raw = Column(Text, default="")


class PrintJob(Base):
    """أمر طباعة حرارية في الطابور لوكيل الطباعة (برنامج على جهاز الكاشير بيسحب الأوامر ويطبعها محليًا): pending → sent → done | failed."""
    __tablename__ = "print_jobs"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=_now, index=True)
    updated_at = Column(DateTime, default=_now)
    station = Column(String(20), nullable=False, index=True)
    data = Column(LargeBinary, nullable=False)
    status = Column(String(10), default="pending", index=True)
    attempts = Column(Integer, default=0)
    error = Column(String(300), default="")


class DeliveryItemMap(Base):
    """ربط صنف التطبيق (SKU أو الاسم) بصنف عندنا - بيتعمل مرة واحدة ويتفكّر."""
    __tablename__ = "delivery_item_map"
    __table_args__ = (UniqueConstraint("source", "key", name="uq_delivery_map"),)
    id = Column(Integer, primary_key=True)
    source = Column(String(30), nullable=False)
    key = Column(String(200), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)


class LoyaltyTxn(Base):
    """حركة نقاط ولاء: earn (اكتساب من بيع) / redeem (استبدال كخصم) / reverse (عكس بسبب مرتجع) / adjust (تسوية يدوية)."""
    __tablename__ = "loyalty_txns"
    id = Column(Integer, primary_key=True)
    at = Column(DateTime, default=_now, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    kind = Column(String(10), nullable=False)
    points = Column(Float, default=0.0)                  # موجب = زيادة رصيد، سالب = نقص
    balance_after = Column(Float, default=0.0)
    invoice_id = Column(Integer, nullable=True, index=True)
    ref = Column(String(40), default="")                 # رقم فاتورة/مرتجع
    note = Column(String(200), default="")
    by = Column(String(100), default="")

    customer = relationship("Customer")


class Coupon(Base):
    """كوبون خصم: نسبة أو مبلغ ثابت، بحد أدنى للفاتورة وحد أقصى للخصم وفترة صلاحية وعدد مرات استخدام."""
    __tablename__ = "coupons"
    id = Column(Integer, primary_key=True)
    code = Column(String(40), nullable=False, unique=True)
    name = Column(String(150), default="")
    kind = Column(String(10), default="percent")     # percent | fixed
    value = Column(Float, default=0.0)
    min_order = Column(Float, default=0.0)           # أقل إجمالي فاتورة (شامل الضريبة)
    max_discount = Column(Float, default=0.0)        # 0 = بلا حد
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    usage_limit = Column(Integer, default=0)         # 0 = بلا حد
    used_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    notes = Column(String(300), default="")
    created_at = Column(DateTime, default=_now)


class AuditLog(Base):
    """سجل التدقيق: كل إنشاء/تعديل/حذف بيتسجل أوتوماتيك (من SQLAlchemy events) بالمستخدم والوقت والقيم قبل/بعد."""
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    at = Column(DateTime, default=_now, index=True)
    username = Column(String(100), default="", index=True)
    action = Column(String(20), default="", index=True)    # create | update | delete | login | login_failed | backup | restore ...
    table_name = Column(String(80), default="", index=True)
    record_id = Column(Integer, nullable=True)
    label = Column(String(200), default="")                # رقم/اسم السجل
    changes = Column(Text, default="")                     # JSON: {field: [old, new]} أو نص حر


class SyncOp(Base):
    """(نسخة الفرع) عملية أعمال اتنفّذت محليًا وفي انتظار إرسالها للمركز: بتتسجّل بعد نجاحها. status: pending | pushed | failed | discarded."""
    __tablename__ = "sync_ops"
    id = Column(Integer, primary_key=True)
    uuid = Column(String(40), unique=True, index=True)
    fn = Column(String(60), default="")
    payload = Column(Text, default="")            # JSON: {"args": [...], "kwargs": {...}}
    username = Column(String(100), default="")
    at = Column(DateTime, default=_now, index=True)
    status = Column(String(12), default="pending", index=True)
    attempts = Column(Integer, default=0)
    error = Column(Text, default="")
    local_ref = Column(String(60), default="")    # رقم المستند المحلي (للعرض)
    produced = Column(Text, default="")           # JSON: {"PosSession": 7} المعرّف المحلي الناتج (للربط)
    hq_ref = Column(Text, default="")             # JSON: ردّ المركز (رقم الفاتورة هناك...)


class SyncInbox(Base):
    """(المركز) العمليات اللي وصلت من الفروع: بتمنع التكرار (node_id + uuid) وبتحفظ النتيجة أو الخطأ."""
    __tablename__ = "sync_inbox"
    __table_args__ = (UniqueConstraint("node_id", "uuid", name="uq_sync_inbox_node_uuid"),)
    id = Column(Integer, primary_key=True)
    node_id = Column(String(40), index=True)
    uuid = Column(String(40), index=True)
    fn = Column(String(60), default="")
    status = Column(String(12), default="applied")     # applied | failed
    op_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, default=_now)
    result = Column(Text, default="")
    error = Column(Text, default="")


class SyncMap(Base):
    """(المركز) ربط معرّف مستند اتعمل على الفرع (جلسة كاشير مثلًا) بمعرّفه عند المركز، علشان العمليات التالية اللي بتشاور عليه."""
    __tablename__ = "sync_map"
    __table_args__ = (UniqueConstraint("node_id", "entity", "node_ref", name="uq_sync_map"),)
    id = Column(Integer, primary_key=True)
    node_id = Column(String(40), index=True)
    entity = Column(String(40))
    node_ref = Column(Integer)
    hq_ref = Column(Integer)


class SyncState(Base):
    """(الفرع) حالة المزامنة: آخر علامة نسخة من المركز، آخر مزامنة، أكبر معرّفات وقت آخر تنزيل..."""
    __tablename__ = "sync_state"
    key = Column(String(60), primary_key=True)
    value = Column(Text, default="")


class KitchenEvent(Base):
    """إشعار للمطبخ + سجل للتقارير: إلغاء صنف مبعوث / إلغاء طلب / مرتجع صنف / إلغاء فاتورة لطلب مطعم."""
    __tablename__ = "kitchen_events"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=_now)
    kind = Column(String(20), nullable=False)   # item_void | order_void | item_return | invoice_void
    order_id = Column(Integer, nullable=True)
    order_number = Column(String(30), default="")
    order_type = Column(String(20), default="")
    table_number = Column(String(30), default="")
    invoice_id = Column(Integer, nullable=True)
    invoice_number = Column(String(30), default="")
    branch_id = Column(Integer, nullable=True)
    product_id = Column(Integer, nullable=True)
    product_name = Column(String(200), default="")
    quantity = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)         # شامل الضريبة
    reason = Column(String(300), default="")
    created_by = Column(String(100), default="")
    approved_by = Column(String(100), default="")
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String(100), default="")
    acknowledged_at = Column(DateTime, nullable=True)


class RestaurantOrderItem(Base):
    __tablename__ = "restaurant_order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("restaurant_orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, default=1.0)
    unit_price = Column(Float, default=0.0)
    tax_rate = Column(Float, default=15.0)
    note = Column(String(200), default="")
    course = Column(Integer, default=1)          # ترتيب التقديم (مقبلات=1، رئيسي=2 ...)
    kitchen_status = Column(String(20), default="pending")  # pending | sent | served | voided
    sent_at = Column(DateTime, nullable=True)
    void_reason = Column(String(200), default="")
    voided_by = Column(String(100), default="")      # الكاشير اللي طلب الإلغاء
    approved_by = Column(String(100), default="")    # المدير اللي اعتمد
    voided_at = Column(DateTime, nullable=True)
    served_at = Column(DateTime, nullable=True)

    order = relationship("RestaurantOrder", back_populates="items")
    product = relationship("Product")


class LeaveType(Base):
    """نوع إجازة قابل للإضافة: نسبة الخصم من الراتب (0 = مدفوعة، 100 = بدون راتب، أو أي نسبة)، وهل بتخصم من رصيد الإجازة السنوية."""
    __tablename__ = "leave_types"
    id = Column(Integer, primary_key=True)
    code = Column(String(20), nullable=False, unique=True)
    name = Column(String(100), nullable=False, unique=True)
    deduct_percent = Column(Float, default=0.0)          # نسبة خصم أجر اليوم عن كل يوم إجازة (0..100)
    uses_annual_balance = Column(Boolean, default=False)  # بتخصم من رصيد الإجازة السنوية وتتحقق منه
    max_days_per_year = Column(Integer, default=0)       # 0 = بدون حد
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)           # الأنواع الأساسية: تتعدّل ومش بتتحذف
    sort_order = Column(Integer, default=100)
    notes = Column(String(300), default="")


class LeaveRequest(Base):
    """طلب إجازة (حسب نوع من جدول أنواع الإجازات) لموظف."""
    __tablename__ = "leave_requests"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    leave_type = Column(String(20), nullable=False)  # كود من leave_types (annual | sick | unpaid | ...)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    days = Column(Integer, default=1)
    reason = Column(Text, default="")
    state = Column(String(20), default="pending")  # pending | approved | rejected | cancelled
    requested_at = Column(DateTime, default=_now)
    decided_at = Column(DateTime, nullable=True)
    decided_by = Column(String(100), default="")
    decision_note = Column(Text, default="")

    employee = relationship("Employee")


class PermissionRequest(Base):
    """طلب استئذان (ساعات) في يوم معيّن."""
    __tablename__ = "permission_requests"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    date = Column(DateTime, nullable=False)
    time_from = Column(String(5), nullable=False)   # "HH:MM"
    time_to = Column(String(5), nullable=False)
    hours = Column(Float, default=1.0)
    reason = Column(Text, default="")
    state = Column(String(20), default="pending")
    requested_at = Column(DateTime, default=_now)
    decided_at = Column(DateTime, nullable=True)
    decided_by = Column(String(100), default="")
    decision_note = Column(Text, default="")

    employee = relationship("Employee")


class ResignationRequest(Base):
    """تقديم استقالة / إنهاء خدمة - الموافقة عليه بتقفل عقد الموظف وتوقفه."""
    __tablename__ = "resignation_requests"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    submission_date = Column(DateTime, nullable=False)
    last_working_date = Column(DateTime, nullable=False)
    reason = Column(Text, default="")
    state = Column(String(20), default="pending")  # pending | approved | rejected | cancelled
    requested_at = Column(DateTime, default=_now)
    decided_at = Column(DateTime, nullable=True)
    decided_by = Column(String(100), default="")
    decision_note = Column(Text, default="")

    employee = relationship("Employee")


class AnnualLeaveSettlement(Base):
    """تسوية دورية لرصيد الإجازة السنوية لموظف نشط - بتوثّق تاريخ التعيين
    وتاريخ آخر إجازة اتاخدت، وتحسب المستحق (بالتناسب الزمني) من تاريخ
    التعيين أو آخر تسوية سابقة لحد تاريخ التسوية، وترحّل الرصيد الختامي
    كافتتاحي للتسوية الجاية. الاستبدال النقدي (لو موجود) بيترحّل بقيد
    زي تسوية نهاية الخدمة بالظبط."""
    __tablename__ = "annual_leave_settlements"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=True)
    hire_date = Column(DateTime, nullable=True)
    last_leave_date = Column(DateTime, nullable=True)     # آخر يوم إجازة معتمدة قبل هذه التسوية
    period_start = Column(DateTime, nullable=False)       # من تاريخ التعيين أو آخر تسوية سابقة
    settlement_date = Column(DateTime, nullable=False)    # تاريخ التسوية (نهاية الفترة)
    opening_balance = Column(Float, default=0.0)          # الرصيد المرحّل من التسوية السابقة
    accrued_days = Column(Float, default=0.0)              # المستحق بالتناسب الزمني خلال الفترة
    used_days = Column(Float, default=0.0)                 # الإجازات المعتمدة المأخوذة خلال الفترة
    closing_balance = Column(Float, default=0.0)           # الرصيد الختامي (بيترحّل كافتتاحي للتسوية الجاية)
    encashed_days = Column(Float, default=0.0)             # أيام مُستبدلة نقدًا (اختياري)
    daily_rate = Column(Float, default=0.0)
    encashed_amount = Column(Float, default=0.0)
    notes = Column(Text, default="")
    state = Column(String(20), default="draft")             # draft | posted
    created_at = Column(DateTime, default=_now)
    posted_at = Column(DateTime, nullable=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)

    employee = relationship("Employee")
    contract = relationship("Contract")


class EosSettlement(Base):
    """تسوية نهاية خدمة: مكافأة نهاية الخدمة (حسب نظام العمل السعودي) +
    رصيد الإجازة غير المستخدم، بقيد محاسبي بيخصم المستحق من حسابات
    المخصص (المكافأة والإجازة) مباشرةً من غير قيد على المصروف، ودائن صافي المستحق للموظف."""
    __tablename__ = "eos_settlements"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), nullable=False, unique=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=True)
    resignation_request_id = Column(Integer, ForeignKey("resignation_requests.id"), nullable=True)
    termination_type = Column(String(20), default="resignation")  # resignation | termination
    hire_date = Column(DateTime, nullable=True)
    last_working_date = Column(DateTime, nullable=False)
    years_of_service = Column(Float, default=0.0)
    monthly_wage = Column(Float, default=0.0)          # الأجر المحسوب عليه (إجمالي الراتب)
    eos_gross = Column(Float, default=0.0)              # المكافأة كاملة قبل نسبة الاستقالة
    eos_multiplier = Column(Float, default=1.0)         # نسبة الاستحقاق (استقالة) أو 1 (إنهاء من الشركة)
    eos_gratuity = Column(Float, default=0.0)           # المكافأة المستحقة فعليًا
    eos_provisioned = Column(Float, default=0.0)        # المتراكم من دورة المخصصات (مرحّل فقط)
    unused_leave_days = Column(Float, default=0.0)
    daily_rate = Column(Float, default=0.0)
    leave_amount = Column(Float, default=0.0)
    leave_provisioned = Column(Float, default=0.0)
    other_dues = Column(Float, default=0.0)
    other_dues_note = Column(String(200), default="")
    other_deductions = Column(Float, default=0.0)
    other_deductions_note = Column(String(200), default="")
    total_amount = Column(Float, default=0.0)           # صافي المستحق للموظف
    notes = Column(Text, default="")
    state = Column(String(20), default="draft")         # draft | posted
    created_at = Column(DateTime, default=_now)
    posted_at = Column(DateTime, nullable=True)
    journal_entry_id = Column(Integer, ForeignKey("journal_entries.id"), nullable=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True)

    employee = relationship("Employee")
    contract = relationship("Contract")
    resignation_request = relationship("ResignationRequest")


class SalesInvoicePayment(Base):
    """سطر سداد لفاتورة مبيعات (POS): الفاتورة الواحدة ممكن تتسدد بأكتر من طريقة دفع (نقدي + شبكة + آجل...)."""
    __tablename__ = "sales_invoice_payments"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("sales_invoices.id"), nullable=False, index=True)
    payment_method_id = Column(Integer, ForeignKey("payment_methods.id"), nullable=True)
    method_name = Column(String(100), default="")
    amount = Column(Float, default=0.0)              # المبلغ المحسوب على الفاتورة (بعد خصم الباقي)
    is_cash = Column(Boolean, default=False)
    is_credit = Column(Boolean, default=False)       # الجزء الآجل على حساب العميل
    tendered = Column(Float, nullable=True)          # المبلغ المستلم فعليًا (للنقدي) - الباقي = tendered - amount
    reference = Column(String(100), default="")      # رقم عملية الشبكة/التحويل (اختياري)


class BankAccount(Base):
    """حساب بنكي للشركة: مربوط بحساب في شجرة الحسابات (للمطابقة) وببيانات الآيبان ورقم المنشأة (لملفات التحويل/الرواتب)."""
    __tablename__ = "bank_accounts"
    id = Column(Integer, primary_key=True)
    code = Column(String(30), nullable=False, unique=True)
    name = Column(String(150), nullable=False)
    bank_name = Column(String(100), default="")
    iban = Column(String(40), default="")
    swift = Column(String(20), default="")
    establishment_id = Column(String(40), default="")     # رقم المنشأة/العميل لدى البنك (ملف الرواتب)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    account = relationship("Account")


class PaymentProvider(Base):
    """مزوّد دفع بنكي: kind = terminal_manual (جهاز شبكة بإدخال رقم الموافقة) | mock (تجريبي) | terminal_http / online_http (API عام بقوالب في config_json)."""
    __tablename__ = "payment_providers"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, unique=True)
    kind = Column(String(20), default="terminal_manual")
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=True)
    config_json = Column(Text, default="{}")
    is_active = Column(Boolean, default=True)
    bank_account = relationship("BankAccount")


class PaymentTransaction(Base):
    """عملية دفع بنكي (خصم بطاقة على جهاز/بوابة، أو رابط دفع أونلاين)."""
    __tablename__ = "payment_transactions"
    id = Column(Integer, primary_key=True)
    provider_id = Column(Integer, ForeignKey("payment_providers.id"), nullable=False)
    kind = Column(String(10), default="charge")      # charge | link
    amount = Column(Float, default=0.0)
    status = Column(String(12), default="pending")   # pending | approved | declined | failed | paid | expired | orphaned
    reference = Column(String(100), default="")      # رقم المرجع/الموافقة (RRN)
    card_last4 = Column(String(8), default="")
    external_id = Column(String(120), default="")
    link_url = Column(String(500), default="")
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    invoice_id = Column(Integer, ForeignKey("sales_invoices.id"), nullable=True)
    payment_method_id = Column(Integer, ForeignKey("payment_methods.id"), nullable=True)
    receipt_payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True)   # سند القبض اللي اتعمل بعد التأكد من سداد الرابط
    message = Column(Text, default="")
    created_by = Column(String(60), default="")
    created_at = Column(DateTime, default=_now)
    provider = relationship("PaymentProvider")
    customer = relationship("Customer")


class BankStatementLine(Base):
    """سطر من كشف حساب البنك المستورد - للمطابقة مع قيود حساب البنك."""
    __tablename__ = "bank_statement_lines"
    id = Column(Integer, primary_key=True)
    bank_account_id = Column(Integer, ForeignKey("bank_accounts.id"), nullable=False, index=True)
    batch = Column(String(40), default="")
    date = Column(DateTime, nullable=False)
    description = Column(String(300), default="")
    reference = Column(String(100), default="")
    debit = Column(Float, default=0.0)       # مسحوب من الحساب (خروج)
    credit = Column(Float, default=0.0)      # مودع في الحساب (دخول)
    balance = Column(Float, nullable=True)
    status = Column(String(10), default="unmatched")   # unmatched | matched | posted | ignored
    journal_line_id = Column(Integer, ForeignKey("journal_entry_lines.id"), nullable=True)
    row_hash = Column(String(64), index=True)
    bank_account = relationship("BankAccount")


class PaymentMethod(Base):
    """طريقة دفع (نقدي، شبكة، تحويل، آجل...) مربوطة بحساب محاسبي محدد
    مسبقًا - عشان شاشات البيع تختار طريقة الدفع بس من غير ما تسأل عن
    الحساب كل مرة. is_credit=True معناها آجل على حساب العميل (الذمم
    المدينة) فمالهاش حساب ثابت."""
    __tablename__ = "payment_methods"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    is_credit = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    provider_id = Column(Integer, ForeignKey("payment_providers.id"), nullable=True)   # مزوّد دفع بنكي (جهاز شبكة/بوابة) - بيتحقق من العملية قبل إصدار الفاتورة
    is_cash = Column(Boolean, nullable=True)       # نقدي (بيدخل صندوق الماكينة في جلسة الكاشير)؛ None = تلقائي: الطريقة اللي اسمها "نقدي"

    account = relationship("Account")


class DamageRecord(Base):
    """سند تلف - يدعم إتلاف أكتر من صنف في نفس السند دفعة واحدة (عادي/
    مُصنَّع/Kit مع بعض)."""
    __tablename__ = "damage_records"
    id = Column(Integer, primary_key=True)
    number = Column(String(40), nullable=False, unique=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    date = Column(DateTime, default=_now)
    reason = Column(Text, default="")
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    total_cost = Column(Float, default=0.0)

    location = relationship("Location")
    items = relationship("DamageItem", back_populates="record", cascade="all, delete-orphan")


class DamageItem(Base):
    """صنف واحد ضمن سند تلف (ممكن يكون Kit) - بحساب تلف اختياري خاص بيه؛
    لو فاضي بيستخدم حساب خسائر الجرد الافتراضي من الإعدادات المحاسبية."""
    __tablename__ = "damage_items"
    id = Column(Integer, primary_key=True)
    record_id = Column(Integer, ForeignKey("damage_records.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, default=1.0)
    damage_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)

    record = relationship("DamageRecord", back_populates="items")
    product = relationship("Product")
    damage_account = relationship("Account")
    lines = relationship("DamageLine", back_populates="item", cascade="all, delete-orphan")


class DamageLine(Base):
    """السطر الفعلي اللي اتخصم من المخزون - نفس الصنف لو عادي/مُصنَّع، أو
    كل مكوّن على حدة لو الصنف الأصلي Kit."""
    __tablename__ = "damage_lines"
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("damage_items.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, default=0.0)
    unit_cost = Column(Float, default=0.0)

    item = relationship("DamageItem", back_populates="lines")
    product = relationship("Product")


class PosGroup(Base):
    """مجموعة أصناف مخصّصة لشاشة نقاط البيع (زي "مجموعة أ"، "مشروبات"،
    "أكل سريع" ...) - المستخدم بينظّمها بنفسه ويحدد أصنافها."""
    __tablename__ = "pos_groups"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(20), default="")
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    items = relationship("PosGroupItem", back_populates="group", cascade="all, delete-orphan")


class PosGroupItem(Base):
    __tablename__ = "pos_group_items"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("pos_groups.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    group = relationship("PosGroup", back_populates="items")
    product = relationship("Product")


class BomLine(Base):
    """مكوّن ضمن قائمة مكونات صنف (BOM) - سواء كان الصنف الأب من نوع Kit
    (بيتفكك وقت البيع) أو Manufactured (بيتصنّع عن طريق أمر إنتاج)."""
    __tablename__ = "bom_lines"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)      # الصنف الأب
    component_id = Column(Integer, ForeignKey("products.id"), nullable=False)    # المكوّن
    quantity = Column(Float, default=1.0)  # كمية المكوّن بالوحدة الأساسية لكل وحدة واحدة من الصنف الأب (اللي بيستخدمها التصنيع والـKit)
    unit_id = Column(Integer, ForeignKey("product_units.id"), nullable=True)   # الوحدة اللي اتسجّل بيها المكوّن (كرتونة، كيلو...)
    unit_qty = Column(Float, nullable=True)                                    # الكمية بالوحدة المختارة (quantity = unit_qty × معامل الوحدة)

    product = relationship("Product", foreign_keys=[product_id])
    component = relationship("Product", foreign_keys=[component_id])
    unit = relationship("ProductUnit", foreign_keys=[unit_id])


class ProductionOrder(Base):
    """أمر إنتاج/تصنيع: يستهلك مكونات (حسب BOM الصنف) وينتج كمية من الصنف التام."""
    __tablename__ = "production_orders"
    id = Column(Integer, primary_key=True)
    number = Column(String(40), nullable=False, unique=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Float, default=1.0)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    date = Column(DateTime, default=_now)
    state = Column(String(15), default="draft")  # draft | done
    notes = Column(Text, default="")
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)

    product = relationship("Product")
    location = relationship("Location")


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    number = Column(String(40), nullable=False, unique=True)
    date = Column(DateTime, default=_now)
    payment_type = Column(String(20), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)  # receipt / payment
    partner_type = Column(String(20), nullable=False)  # customer / supplier / other
    partner_id = Column(Integer, nullable=True)
    amount = Column(Float, nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    reference = Column(String(120), default="")
    notes = Column(Text, default="")
    voided = Column(Boolean, default=False)
    journal_entry_id = Column(Integer, nullable=True)
    currency = Column(String(5), nullable=True)           # سند بعملة أجنبية: amount = المقابل بالأساسي، foreign_amount = المبلغ الأجنبي
    exchange_rate = Column(Float, nullable=True)
    foreign_amount = Column(Float, nullable=True)
    account = relationship("Account")
    branch = relationship("Branch")
    cost_center = relationship("CostCenter")


class InventoryAdjustment(Base):
    __tablename__ = "inventory_adjustments"
    id = Column(Integer, primary_key=True)
    number = Column(String(40), nullable=False, unique=True)
    date = Column(DateTime, default=_now)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    notes = Column(Text, default="")
    state = Column(String(20), default="done")
    location = relationship("Location")
    branch = relationship("Branch")
    cost_center = relationship("CostCenter")
    lines = relationship("InventoryAdjustmentLine", back_populates="adjustment", cascade="all, delete-orphan")


class InventoryAdjustmentLine(Base):
    __tablename__ = "inventory_adjustment_lines"
    id = Column(Integer, primary_key=True)
    adjustment_id = Column(Integer, ForeignKey("inventory_adjustments.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    theoretical_qty = Column(Float, default=0.0)
    counted_qty = Column(Float, default=0.0)
    difference_qty = Column(Float, default=0.0)
    unit_cost = Column(Float, default=0.0)
    adjustment = relationship("InventoryAdjustment", back_populates="lines")
    product = relationship("Product")


class FormDraft(Base):
    """مسودة نموذج غير محفوظ (قيد / فاتورة...) لكل مستخدم: بتتحفظ تلقائيًا أثناء الكتابة عشان لو الاتصال قطع ما تضيعش."""
    __tablename__ = "form_drafts"
    id = Column(Integer, primary_key=True)
    username = Column(String(80), nullable=False, index=True)
    kind = Column(String(60), nullable=False)
    data = Column(Text, default="")
    updated_at = Column(DateTime, default=_now)
    __table_args__ = (UniqueConstraint("username", "kind", name="uq_form_draft"),)


class MonthClose(Base):
    """إقفال شهري: قفل التسجيل في الشهر (بدون قيد إقفال) بعد مراجعته. السنة المالية ليها إقفالها الخاص."""
    __tablename__ = "month_closes"
    id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    closed_at = Column(DateTime, default=_now)
    closed_by = Column(String(80), default="")
    income = Column(Float, default=0.0)
    expense = Column(Float, default=0.0)
    note = Column(String(300), default="")
    __table_args__ = (UniqueConstraint("year", "month", name="uq_month_close"),)


class FiscalPeriod(Base):
    __tablename__ = "fiscal_periods"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, unique=True)
    date_from = Column(DateTime, nullable=False)
    date_to = Column(DateTime, nullable=False)
    is_closed = Column(Boolean, default=False)
    closed_at = Column(DateTime, nullable=True)
    closing_journal_id = Column(Integer, nullable=True)



# (حقل الإعدادات، كود قديم، اسم قديم، نوع، كود الأب القديم، تدفق نقدي) - للقواعد القديمة اللي ناقصها حساب افتراضي
_LEGACY_DEFAULT_ACCOUNTS = [
    ("receivable_account_id", "1200", "العملاء / الذمم المدينة", "asset", "1000", "operating"),
    ("payable_account_id", "2100", "الموردون / الذمم الدائنة", "liability", "2000", "operating"),
    ("sales_account_id", "4100", "إيرادات المبيعات", "income", "4000", "operating"),
    ("purchases_account_id", "5200", "المشتريات", "expense", "5000", "operating"),
    ("inventory_account_id", "1300", "المخزون", "asset", "1000", "operating"),
    ("cogs_account_id", "5100", "تكلفة البضاعة المباعة", "expense", "5000", "operating"),
    ("vat_input_account_id", "1400", "ضريبة القيمة المضافة - مدخلات", "asset", "1000", "operating"),
    ("vat_output_account_id", "2200", "ضريبة القيمة المضافة - مخرجات", "liability", "2000", "operating"),
    ("cash_account_id", "1100", "النقدية والبنوك", "asset", "1000", "cash"),
    ("retained_earnings_account_id", "3200", "الأرباح المرحلة / المحتجزة", "equity", "3000", "financing"),
    ("inventory_gain_account_id", "4200", "أرباح فروق الجرد", "income", "4000", "operating"),
    ("inventory_loss_account_id", "5300", "خسائر فروق الجرد", "expense", "5000", "operating"),
    ("salary_expense_account_id", "5400", "الرواتب والأجور", "expense", "5000", "operating"),
    ("salaries_payable_account_id", "2300", "رواتب مستحقة الدفع", "liability", "2000", "operating"),
    ("gosi_payable_account_id", "2400", "التأمينات الاجتماعية مستحقة", "liability", "2000", "operating"),
    ("sales_discount_account_id", "5500", "الخصومات المسموح بها", "expense", "5000", "operating"),
    ("purchase_discount_account_id", "4300", "خصومات مكتسبة من الموردين", "income", "4000", "operating"),
    ("employee_advances_account_id", "1500", "سلف الموظفين", "asset", "1000", "operating"),
    ("asset_loss_account_id", "5600", "خسائر استبعاد أصول ثابتة", "expense", "5000", "operating"),
    ("employee_custody_account_id", "1510", "عهد الموظفين", "asset", "1000", "operating"),
    ("prepaid_expenses_account_id", "1600", "مصاريف مدفوعة مقدمًا", "asset", "1000", "operating"),
]


def _seed_accounting_defaults():
    """قاعدة جديدة: بتتبني بالشجرة الجديدة (erp_app/chart_data.py) والإعدادات الافتراضية بتتربط بحساباتها.
    قاعدة موجودة: أي إعداد افتراضي لسه فاضي بيتربط بحساب موجود (من الشجرة الجديدة أو القديمة)، ولو مفيش خالص
    بيتعمل الحساب القديم - من غير ما يرجّع حسابات قديمة اتحذفت بعد تحويل الشجرة."""
    from .chart_data import NEW_CHART, NEW_SETTINGS_CODES
    session = SessionLocal()
    try:
        def acc(code):
            return session.query(Account).filter(Account.code == code).first()

        if session.query(Account).count() == 0:
            by_code = {}
            for code, name, typ, parent_code, cf in NEW_CHART:
                a = Account(code=code, name=name, account_type=typ, parent=by_code.get(parent_code), cash_flow_type=cf)
                session.add(a); session.flush(); by_code[code] = a
            if not session.get(AccountingSettings, 1):
                session.add(AccountingSettings(id=1, **{f: by_code[c].id for f, c in NEW_SETTINGS_CODES.items()}))
            session.commit()
            return

        cf_defaults = {"1100": "cash", "1200": "operating", "1300": "operating", "1400": "operating", "2100": "operating", "2200": "operating",
                       "3200": "financing", "4100": "operating", "4200": "operating", "5100": "operating", "5200": "operating", "5300": "operating",
                       "5400": "operating", "2300": "operating", "2400": "operating"}
        for code, cf_type in cf_defaults.items():
            a = acc(code)
            if a and not a.cash_flow_type:
                a.cash_flow_type = cf_type

        cfg = session.get(AccountingSettings, 1)
        if not cfg:
            cfg = AccountingSettings(id=1); session.add(cfg); session.flush()
        for field, old_code, old_name, typ, parent_code, cf in _LEGACY_DEFAULT_ACCOUNTS:
            if getattr(cfg, field) is not None:
                continue
            target = acc(NEW_SETTINGS_CODES.get(field, "")) or acc(old_code)
            if not target:
                parent = acc(parent_code) if parent_code else None
                target = Account(code=old_code, name=old_name, account_type=typ, parent_id=parent.id if parent else None, cash_flow_type=cf)
                session.add(target); session.flush()
            setattr(cfg, field, target.id)
        session.commit()
    finally:
        session.close()

class BudgetLine(Base):
    __tablename__ = "budget_lines"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), default="")
    date_from = Column(DateTime, nullable=False)
    date_to = Column(DateTime, nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cost_center_id = Column(Integer, ForeignKey("cost_centers.id"), nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    budget_amount = Column(Float, default=0.0)
    notes = Column(Text, default="")
    is_active = Column(Boolean, default=True)
    branch = relationship("Branch")
    cost_center = relationship("CostCenter")
    account = relationship("Account")
