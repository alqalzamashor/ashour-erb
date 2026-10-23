import flet as ft
from erp_app.db import init_db
from erp_app import theme, services, i18n
from erp_app.views.login import show_login
from erp_app.views import security as security_view
import asyncio
import os
import time
from erp_app.views.dashboard import build_dashboard
from erp_app.views.products import build_products
from erp_app.views.product_categories import build_product_categories
from erp_app.views.stock_moves import build_stock_moves
from erp_app.views.stock_balance import build_stock_balance
from erp_app.views.customers import build_customers
from erp_app.views.price_lists import build_price_lists
from erp_app.views.suppliers import build_suppliers
from erp_app.views.sales_invoices import build_sales_invoices
from erp_app.views.purchase_invoices import build_purchase_invoices
from erp_app.views.asset_purchase_invoices import build_asset_purchase_invoices
from erp_app.views.goods_receipts import build_goods_receipts
from erp_app.views.settings import build_settings
from erp_app.views.units import build_units
from erp_app.views.accounts import build_accounts
from erp_app.views.inventory_adjustments import build_inventory_adjustments
from erp_app.views.locations import build_locations
from erp_app.views.product_components import build_product_components
from erp_app.views.manufacturing import build_manufacturing
from erp_app.views.damages import build_damages
from erp_app.views.stock_transfer import build_stock_transfer
from erp_app.views.reports import build_reports
from erp_app.views.vat_report import build_vat_report
from erp_app.views.sales_quotations import build_sales_quotations
from erp_app.views.agenda import build_agenda
from erp_app.agenda_notifier import AgendaNotifier
from erp_app.views.chat import build_chat
from erp_app.chat_notifier import ChatNotifier
from erp_app.views.hr_documents import build_hr_documents
from erp_app.views.chart_import import build_chart_import
from erp_app.views.data_cleanup import build_data_cleanup
from erp_app.views.prepaid_expenses import build_prepaid_expenses
from erp_app.views.expiry_report import build_expiry_report
from erp_app.views.purchase_price_report import build_purchase_price_report
from erp_app.document_notifier import DocumentNotifier
from erp_app.views.advanced_reports import build_advanced_reports
from erp_app.views.ashour_reports import build_ashour_pnl, build_ashour_pos, build_ashour_purchases, build_ashour_customers, build_ashour_settings
from erp_app.views.receipts_payments import build_receipts_payments
from erp_app.views.journal_entries import build_journal_entries
from erp_app.views.general_journal import build_general_journal
from erp_app.views.trial_balance import build_trial_balance
from erp_app.views.ledger import build_ledger
from erp_app.views.party_reports import build_party_reports
from erp_app.views.product_movements import build_product_movements
from erp_app.views.fiscal_periods import build_fiscal_periods
from erp_app.views.organization import build_organization
from erp_app.views.financial_consolidation import build_financial_consolidation
from erp_app.views.budgets import build_budgets
from erp_app.views.employees import build_employees
from erp_app.views.contracts import build_contracts
from erp_app.views.leave_requests import build_leave_requests
from erp_app.views.attendance import build_attendance
from erp_app.views.eos_settlements import build_eos_settlements
from erp_app.views.employee_balances import build_employee_balances
from erp_app.views.employee_reports import build_employee_reports
from erp_app.views.payroll_report import build_payroll_report
from erp_app.views.annual_leave_settlements import build_annual_leave_settlements
from erp_app.views.payroll import build_payroll
from erp_app.views.allowances_insurance import build_allowances_insurance
from erp_app.views.fixed_assets import build_fixed_assets
from erp_app.views.asset_categories import build_asset_categories
from erp_app.views.asset_inventory import build_asset_inventory
from erp_app.views.pos import build_pos
from erp_app.views.payment_methods import build_payment_methods
from erp_app.views.employee_custody import build_employee_custody, build_custody_issues, build_custody_expenses, build_custody_settlements
from erp_app.views.restaurant import build_restaurant
from erp_app.views.kitchen import build_kitchen
from erp_app.views.void_reports import build_void_reports
from erp_app.views.discount_report import build_discount_report
from erp_app.views.restaurant_dashboard import build_restaurant_dashboard
from erp_app.views.recipe_costing import build_recipe_costing
from erp_app.views.audit_log import build_audit_log
from erp_app.views.backup import build_backup
from erp_app import brand
from erp_app.views.sync_status import build_sync_status
from erp_app.views.scheduled_reports import build_scheduled_reports
from erp_app.views.coupons import build_coupons
from erp_app.views.loyalty import build_loyalty
from erp_app.views.data_integrity import build_data_integrity
from erp_app.views.product_labels import build_product_labels
from erp_app.views.notifications import build_notifications
from erp_app.views.currencies import build_currencies
from erp_app.views.approvals import build_approvals
from erp_app.views.receivables_aging import build_receivables_aging
from erp_app.views.smart_alerts import build_smart_alerts
from erp_app.views.delivery_orders import build_delivery_orders
from erp_app.views.database import build_database
from erp_app import global_search
from erp_app.views.printers import build_printers
from erp_app.views.subscription import build_subscription
from erp_app.views.zatca import build_zatca
from erp_app.views.pos_groups import build_pos_groups
from erp_app.views.banking import build_banking
from erp_app.views.trade_reports import build_sales_reports, build_purchase_reports
from erp_app.views.pos_terminals import build_pos_terminals
from erp_app.views.pos_sessions import build_pos_sessions
from erp_app.views.data_import_export import build_data_import_export

# القائمة الرئيسية: تظهر أيقونات فقط. عناصر كل قسم تظهر في لوحة فرعية عند الضغط عليه.
GROUPS = [
    ('dashboard', 'الرئيسية', ft.Icons.SPACE_DASHBOARD_OUTLINED, [
        ('dashboard', 'لوحة التحكم', ft.Icons.SPACE_DASHBOARD_OUTLINED, build_dashboard),
        ('alerts', 'التنبيهات الذكية', ft.Icons.NOTIFICATIONS_ACTIVE_OUTLINED, build_smart_alerts),
    ]),
    ('agenda', 'جدول الأعمال', ft.Icons.EVENT_NOTE_OUTLINED, [
        ('agenda', 'جدول الأعمال والمواعيد', ft.Icons.EVENT_NOTE_OUTLINED, build_agenda),
    ]),
    ('chat', 'الرسائل', ft.Icons.CHAT_OUTLINED, [
        ('chat', 'الرسائل والمحادثات', ft.Icons.CHAT_OUTLINED, build_chat),
    ]),
    ('accounting', 'المحاسبة', ft.Icons.ACCOUNT_BALANCE_OUTLINED, [
        ('accounts', 'شجرة الحسابات', ft.Icons.ACCOUNT_TREE_OUTLINED, build_accounts),
        ('chart_import', 'تطبيق شجرة الحسابات الجديدة', ft.Icons.PLAYLIST_ADD_CHECK, build_chart_import),
        ('currencies', 'العملات وأسعار الصرف', ft.Icons.CURRENCY_EXCHANGE, build_currencies),
        ('journal_entries', 'القيود اليومية', ft.Icons.MENU_BOOK_OUTLINED, build_journal_entries),
        ('general_journal', 'اليومية العامة', ft.Icons.AUTO_STORIES_OUTLINED, build_general_journal),
        ('trial_balance', 'ميزان المراجعة', ft.Icons.BALANCE_OUTLINED, build_trial_balance),
        ('receipts_payments', 'سندات القبض والصرف', ft.Icons.PAYMENTS_OUTLINED, build_receipts_payments),
        ('banking', 'الربط البنكي', ft.Icons.ACCOUNT_BALANCE_OUTLINED, build_banking),
        ('ledger', 'دفتر الأستاذ', ft.Icons.LIBRARY_BOOKS_OUTLINED, build_ledger),
        ('party_reports', 'كشوف العملاء والموردين', ft.Icons.GROUPS_OUTLINED, build_party_reports),
        ('reports', 'التقارير المالية', ft.Icons.ASSESSMENT_OUTLINED, build_reports),
        ('vat_report', 'تقرير ضريبة القيمة المضافة', ft.Icons.PERCENT_OUTLINED, build_vat_report),
        ('prepaid_expenses', 'المصروفات المدفوعة مقدمًا', ft.Icons.EVENT_REPEAT, build_prepaid_expenses),
        ('advanced_reports', 'التقارير المقارنة وحقوق الملكية', ft.Icons.COMPARE_ARROWS, build_advanced_reports),
        ('budgets', 'الموازنات التقديرية', ft.Icons.SAVINGS_OUTLINED, build_budgets),
        ('asset_categories', 'فئات الأصول الثابتة', ft.Icons.CATEGORY_OUTLINED, build_asset_categories),
        ('fixed_assets', 'الأصول الثابتة', ft.Icons.PRECISION_MANUFACTURING_OUTLINED, build_fixed_assets),
        ('asset_inventory', 'جرد الأصول', ft.Icons.FACT_CHECK_OUTLINED, build_asset_inventory),
        ('financial_consolidation', 'القوائم الموحدة والفروع', ft.Icons.HUB_OUTLINED, build_financial_consolidation),
        ('fiscal_periods', 'الفترات والإقفال السنوي', ft.Icons.EVENT_AVAILABLE_OUTLINED, build_fiscal_periods),
    ]),
    ('ashour', 'تقارير عاشور', ft.Icons.INSIGHTS, [
        ('ashour_pnl', 'أرباح وخسائر الفروع', ft.Icons.STOREFRONT, build_ashour_pnl),
        ('ashour_pos', 'مبيعات نقاط البيع', ft.Icons.POINT_OF_SALE, build_ashour_pos),
        ('ashour_purchases', 'تقارير المشتريات', ft.Icons.SHOPPING_CART_CHECKOUT, build_ashour_purchases),
        ('ashour_customers', 'العملاء والتحصيلات', ft.Icons.PEOPLE_ALT_OUTLINED, build_ashour_customers),
        ('ashour_settings', 'إعدادات تقارير عاشور', ft.Icons.TUNE, build_ashour_settings),
    ]),
    ('sales', 'العملاء', ft.Icons.PEOPLE_ALT_OUTLINED, [
        ('pos', 'نقاط البيع (POS)', ft.Icons.SHOPPING_BAG_OUTLINED, build_pos),
        ('payment_methods', 'طرق الدفع', ft.Icons.PAYMENT_OUTLINED, build_payment_methods),
        ('restaurant', 'نظام المطاعم', ft.Icons.RESTAURANT_OUTLINED, build_restaurant),
        ('kitchen', 'شاشة المطبخ', ft.Icons.SOUP_KITCHEN_OUTLINED, build_kitchen),
        ('delivery_orders', 'طلبات التوصيل', ft.Icons.DELIVERY_DINING_OUTLINED, build_delivery_orders),
        ('pos_groups', 'مجموعات نقاط البيع', ft.Icons.APPS_OUTLINED, build_pos_groups),
        ('pos_terminals', 'ماكينات نقاط البيع', ft.Icons.POINT_OF_SALE, build_pos_terminals),
        ('coupons', 'الكوبونات والخصومات', ft.Icons.LOCAL_OFFER_OUTLINED, build_coupons),
        ('loyalty', 'برنامج الولاء', ft.Icons.CARD_GIFTCARD, build_loyalty),
        ('pos_sessions', 'جلسات نقاط البيع', ft.Icons.SCHEDULE_OUTLINED, build_pos_sessions),
        ('sales_quotations', 'عروض الأسعار', ft.Icons.REQUEST_QUOTE_OUTLINED, build_sales_quotations),
        ('sales_invoices', 'فواتير المبيعات', ft.Icons.RECEIPT_LONG_OUTLINED, build_sales_invoices),
        ('sales_reports', 'تقارير المبيعات التحليلية', ft.Icons.INSIGHTS, build_sales_reports),
        ('restaurant_dashboard', 'لوحة المطعم', ft.Icons.DASHBOARD_OUTLINED, build_restaurant_dashboard),
        ('discount_report', 'تقرير الخصومات والكوبونات', ft.Icons.DISCOUNT_OUTLINED, build_discount_report),
        ('void_reports', 'تقرير الملغاة والمرتجعات', ft.Icons.REMOVE_SHOPPING_CART_OUTLINED, build_void_reports),
        ('recipe_costing', 'تقرير تكلفة الوصفات', ft.Icons.MENU_BOOK_OUTLINED, build_recipe_costing),
        ('customers', 'إدارة العملاء', ft.Icons.PEOPLE_ALT_OUTLINED, build_customers),
        ('receivables_aging', 'أعمار الديون', ft.Icons.HOURGLASS_BOTTOM, build_receivables_aging),
        ('price_lists', 'قوائم الأسعار', ft.Icons.SELL_OUTLINED, build_price_lists),
    ]),
    ('purchases', 'الموردون', ft.Icons.LOCAL_SHIPPING_OUTLINED, [
        ('goods_receipts', 'سندات استلام المشتريات', ft.Icons.MOVE_TO_INBOX_OUTLINED, build_goods_receipts),
        ('purchase_invoices', 'فواتير المشتريات', ft.Icons.SHOPPING_CART_CHECKOUT, build_purchase_invoices),
        ('purchase_reports', 'تقارير المشتريات التحليلية', ft.Icons.INSIGHTS, build_purchase_reports),
        ('purchase_price_report', 'مقارنة أسعار الشراء', ft.Icons.COMPARE_ARROWS, build_purchase_price_report),
        ('asset_purchase_invoices', 'فواتير مشتريات الأصول', ft.Icons.PRECISION_MANUFACTURING_OUTLINED, build_asset_purchase_invoices),
        ('suppliers', 'إدارة الموردين', ft.Icons.LOCAL_SHIPPING_OUTLINED, build_suppliers),
        ('custody_issues', 'صرف العهد', ft.Icons.OUTPUT_OUTLINED, build_custody_issues),
        ('custody_expenses', 'مصروفات وفواتير العهد', ft.Icons.RECEIPT_OUTLINED, build_custody_expenses),
        ('custody_settlements', 'تسوية العهد', ft.Icons.TASK_ALT, build_custody_settlements),
        ('employee_custody', 'أرصدة وكشوف العهد', ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED, build_employee_custody),
    ]),
    ('inventory', 'المخزون', ft.Icons.INVENTORY_2_OUTLINED, [
        ('products', 'الأصناف', ft.Icons.INVENTORY_2_OUTLINED, build_products),
        ('product_labels', 'ملصقات الأصناف والأسعار', ft.Icons.QR_CODE_2, build_product_labels),
        ('categories', 'فئات الأصناف', ft.Icons.CATEGORY_OUTLINED, build_product_categories),
        ('units', 'وحدات القياس', ft.Icons.STRAIGHTEN_OUTLINED, build_units),
        ('stock_moves', 'حركات المخزون', ft.Icons.SWAP_VERT, build_stock_moves),
        ('stock_balance', 'أرصدة المخزون', ft.Icons.BAR_CHART, build_stock_balance),
        ('expiry_report', 'الصلاحية والتشغيلات', ft.Icons.EVENT_BUSY_OUTLINED, build_expiry_report),
        ('inventory_adjustments', 'التسويات الجردية', ft.Icons.FACT_CHECK_OUTLINED, build_inventory_adjustments),
        ('locations', 'المخازن', ft.Icons.WAREHOUSE_OUTLINED, build_locations),
        ('product_components', 'مكونات الأصناف', ft.Icons.LAYERS_OUTLINED, build_product_components),
        ('manufacturing', 'التصنيع', ft.Icons.FACTORY_OUTLINED, build_manufacturing),
        ('damages', 'التوالف', ft.Icons.DELETE_FOREVER_OUTLINED, build_damages),
        ('stock_transfer', 'تحويل بين المخازن', ft.Icons.SWAP_HORIZ, build_stock_transfer),
        ('product_movements', 'حركة الأصناف', ft.Icons.HISTORY, build_product_movements),
    ]),
    ('hr', 'الموارد البشرية', ft.Icons.BADGE_OUTLINED, [
        ('employees', 'الموظفون', ft.Icons.PEOPLE_OUTLINE, build_employees),
        ('contracts', 'العقود', ft.Icons.DESCRIPTION_OUTLINED, build_contracts),
        ('hr_documents', 'تجديد الرخص والمستندات', ft.Icons.ASSIGNMENT_LATE_OUTLINED, build_hr_documents),
        ('leave_requests', 'طلبات الموظفين', ft.Icons.EVENT_AVAILABLE_OUTLINED, build_leave_requests),
        ('attendance', 'الحضور والبصمة', ft.Icons.FINGERPRINT, build_attendance),
        ('annual_leave_settlements', 'تسويات الإجازة السنوية', ft.Icons.BEACH_ACCESS_OUTLINED, build_annual_leave_settlements),
        ('eos_settlements', 'تسويات نهاية الخدمة', ft.Icons.LOGOUT_OUTLINED, build_eos_settlements),
        ('employee_balances', 'أرصدة الموظفين', ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED, build_employee_balances),
        ('employee_reports', 'تقارير الموظفين', ft.Icons.ASSESSMENT_OUTLINED, build_employee_reports),
        ('payroll', 'الرواتب', ft.Icons.PAYMENTS_OUTLINED, build_payroll),
        ('payroll_report', 'تقرير الرواتب', ft.Icons.REQUEST_QUOTE_OUTLINED, build_payroll_report),
        ('allowances_insurance', 'المخصصات والتأمينات', ft.Icons.HEALTH_AND_SAFETY_OUTLINED, build_allowances_insurance),
    ]),
    ('admin', 'الإدارة والإعدادات', ft.Icons.ADMIN_PANEL_SETTINGS_OUTLINED, [
        ('organization', 'الفروع ومراكز التكلفة والمستخدمون', ft.Icons.CORPORATE_FARE_OUTLINED, build_organization),
        ('settings', 'إعدادات الشركة', ft.Icons.SETTINGS_OUTLINED, build_settings),
        ('data_import_export', 'استيراد وتصدير البيانات', ft.Icons.SWAP_VERT_OUTLINED, build_data_import_export),
        ('data_cleanup', 'تنظيف قاعدة البيانات', ft.Icons.CLEANING_SERVICES_OUTLINED, build_data_cleanup),
        ('printers', 'الطابعات الحرارية', ft.Icons.PRINT_OUTLINED, build_printers),
        ('subscription', 'الاشتراك', ft.Icons.CARD_MEMBERSHIP_OUTLINED, build_subscription),
        ('zatca', 'الفوترة الإلكترونية (فاتورة)', ft.Icons.QR_CODE_SCANNER, build_zatca),
        ('database', 'قاعدة البيانات', ft.Icons.STORAGE, build_database),
        ('backup', 'النسخ الاحتياطي والاسترجاع', ft.Icons.BACKUP_OUTLINED, build_backup),
        ('sync', 'مزامنة الفرع مع المركز', ft.Icons.SYNC, build_sync_status),
        ('notifications', 'الرسائل (واتساب/SMS)', ft.Icons.FORUM_OUTLINED, build_notifications),
        ('scheduled_reports', 'التقارير المجدولة بالبريد', ft.Icons.SCHEDULE_SEND_OUTLINED, build_scheduled_reports),
        ('audit_log', 'سجل التدقيق', ft.Icons.MANAGE_SEARCH_OUTLINED, build_audit_log),
        ('approvals', 'الموافقات', ft.Icons.VERIFIED_OUTLINED, build_approvals),
        ('data_integrity', 'فحص سلامة البيانات', ft.Icons.RULE_FOLDER_OUTLINED, build_data_integrity),
    ]),
]


# تقسيم الشاشات الكتيرة جوه كل قسم لقوائم فرعية قابلة للطي: (عنوان القائمة، أيقونتها، مفاتيح الشاشات).
# أي شاشة مش مذكورة هنا بتظهر في قائمة "أخرى" آخر القسم (فمفيش شاشة بتختفي). الأقسام الصغيرة (من غير تقسيم) بتظهر قائمة واحدة مباشرة.
SECTIONS = {
    'accounting': [
        ('الحسابات الأساسية', ft.Icons.ACCOUNT_TREE_OUTLINED, ['accounts', 'chart_import', 'currencies']),
        ('القيود والسندات', ft.Icons.EDIT_NOTE_OUTLINED, ['journal_entries', 'receipts_payments', 'prepaid_expenses', 'banking']),
        ('الدفاتر', ft.Icons.AUTO_STORIES_OUTLINED, ['general_journal', 'ledger', 'trial_balance', 'party_reports']),
        ('التقارير المالية', ft.Icons.ASSESSMENT_OUTLINED, ['reports', 'advanced_reports', 'vat_report', 'financial_consolidation']),
        ('الأصول الثابتة', ft.Icons.PRECISION_MANUFACTURING_OUTLINED, ['asset_categories', 'fixed_assets', 'asset_inventory']),
        ('الموازنات والإقفال', ft.Icons.EVENT_AVAILABLE_OUTLINED, ['budgets', 'fiscal_periods']),
    ],
    'sales': [
        ('المبيعات', ft.Icons.RECEIPT_LONG_OUTLINED, ['sales_quotations', 'sales_invoices', 'customers', 'price_lists', 'receivables_aging']),
        ('نقاط البيع', ft.Icons.POINT_OF_SALE, ['pos', 'pos_sessions', 'pos_terminals', 'pos_groups', 'payment_methods']),
        ('المطاعم', ft.Icons.RESTAURANT_OUTLINED, ['restaurant', 'kitchen', 'delivery_orders', 'restaurant_dashboard', 'recipe_costing']),
        ('العروض والولاء', ft.Icons.LOCAL_OFFER_OUTLINED, ['coupons', 'loyalty']),
        ('تقارير المبيعات', ft.Icons.INSIGHTS, ['sales_reports', 'discount_report', 'void_reports']),
    ],
    'purchases': [
        ('المشتريات', ft.Icons.SHOPPING_CART_CHECKOUT, ['purchase_invoices', 'goods_receipts', 'asset_purchase_invoices', 'suppliers']),
        ('العهد', ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED, ['custody_issues', 'custody_expenses', 'custody_settlements', 'employee_custody']),
        ('تقارير المشتريات', ft.Icons.INSIGHTS, ['purchase_reports', 'purchase_price_report']),
    ],
    'inventory': [
        ('الأصناف', ft.Icons.INVENTORY_2_OUTLINED, ['products', 'categories', 'units', 'product_components', 'product_labels']),
        ('حركة المخزون', ft.Icons.SWAP_VERT, ['stock_moves', 'stock_transfer', 'inventory_adjustments', 'damages', 'locations']),
        ('التصنيع', ft.Icons.FACTORY_OUTLINED, ['manufacturing']),
        ('تقارير المخزون', ft.Icons.BAR_CHART, ['stock_balance', 'expiry_report', 'product_movements']),
    ],
    'hr': [
        ('الموظفون', ft.Icons.PEOPLE_OUTLINE, ['employees', 'contracts', 'hr_documents']),
        ('الحضور والإجازات', ft.Icons.FINGERPRINT, ['attendance', 'leave_requests', 'annual_leave_settlements']),
        ('الرواتب والمستحقات', ft.Icons.PAYMENTS_OUTLINED, ['payroll', 'allowances_insurance', 'eos_settlements']),
        ('تقارير الموارد البشرية', ft.Icons.ASSESSMENT_OUTLINED, ['employee_balances', 'employee_reports', 'payroll_report']),
    ],
    'admin': [
        ('إعدادات الشركة', ft.Icons.SETTINGS_OUTLINED, ['settings', 'organization', 'subscription', 'zatca']),
        ('البيانات والنسخ', ft.Icons.STORAGE, ['data_import_export', 'backup', 'database', 'sync', 'data_cleanup', 'data_integrity']),
        ('الاتصالات والطباعة', ft.Icons.FORUM_OUTLINED, ['notifications', 'scheduled_reports', 'printers']),
        ('الرقابة والموافقات', ft.Icons.VERIFIED_USER_OUTLINED, ['audit_log', 'approvals']),
    ],
}

# اسم قصير تحت أيقونة القسم في الشريط الضيق (التلميح بيعرض الاسم الكامل).
SHORT_LABELS = {'dashboard': 'الرئيسية', 'agenda': 'الأعمال', 'chat': 'الرسائل', 'accounting': 'المحاسبة', 'ashour': 'عاشور',
                'sales': 'العملاء', 'purchases': 'الموردون', 'inventory': 'المخزون', 'hr': 'الموارد', 'admin': 'الإعدادات'}


def group_sections(group_key, visible):
    """[(عنوان، أيقونة، [عناصر])] للقسم بعد تصفية الصلاحيات، أو None لو القسم يتعرض قائمة واحدة."""
    spec = SECTIONS.get(group_key)
    if not spec:
        return None
    by_key = {x[0]: x for x in visible}
    used, out = set(), []
    for title, icon, keys in spec:
        items = [by_key[k] for k in keys if k in by_key]
        used.update(k for k in keys if k in by_key)
        if items:
            out.append((title, icon, items))
    rest = [x for x in visible if x[0] not in used]
    if rest:
        out.append(('أخرى', ft.Icons.MORE_HORIZ, rest))
    return out if len(out) > 1 else None


search_ref = {'open': None}


def _global_keys(e, ref=None):
    ref = ref if ref is not None else search_ref
    try:
        if e.key in ('K', 'k') and getattr(e, 'ctrl', False) and ref['open']:
            ref['open']()
    except Exception:
        pass


def prefill_search(root, text):
    """بعد فتح شاشة من نتيجة بحث شامل: لاقي أول خانة بحث (label فيها "بحث") واكتب فيها النص وشغّل الفلترة."""
    def walk(c):
        if isinstance(c, ft.TextField) and 'بحث' in (c.label or '') and not c.read_only and c.visible:
            return c
        for a in ('controls', 'content', 'actions'):
            v = getattr(c, a, None)
            for ch in (v if isinstance(v, list) else ([v] if v is not None else [])):
                if hasattr(ch, '__dict__'):
                    r = walk(ch)
                    if r is not None:
                        return r
        return None
    try:
        tf = walk(root)
        if tf is None:
            return False
        tf.value = text
        import types
        ev = types.SimpleNamespace(control=tf, data=text, page=None)
        for h in (tf.on_change, tf.on_submit):
            if h:
                h(ev)
                break
        return True
    except Exception:
        return False


def _compact_headers(root, width):
    """موبايل: صفوف العنوان/الأدوات في أول الشاشة (عنوان + بحث + أزرار) بتنزل سطور بدل ما تتقصّ، والحقول العريضة بتتحدد بعرض الشاشة."""
    kids = getattr(root, 'controls', None)
    if not kids:
        return
    for row in kids[:3]:
        if not isinstance(row, ft.Row) or len(row.controls) < 2:
            continue
        kept = [c for c in row.controls if not (isinstance(c, ft.Container) and c.expand and c.content is None)]
        if any(getattr(c, 'expand', None) for c in kept):
            continue                 # فيه عنصر ممدود (expand): الصف ده مش بيتلفّ (Flutter بيفشل لو wrap مع expand)
        row.wrap = True
        row.run_spacing = 8
        for sub in [row] + [c for c in row.controls if isinstance(c, ft.Row)]:       # عنوان الشاشة (شريط لوني + عنوان ووصف): النص الطويل ينزل سطر بدل ما يتقصّ
            if len(sub.controls) == 2 and isinstance(sub.controls[1], ft.Column) and isinstance(sub.controls[0], ft.Container) and sub.controls[0].width == 4:
                sub.controls[1].width = max(120, width - 52)
        row.controls = [c for c in row.controls if not (isinstance(c, ft.Container) and c.expand and c.content is None)]
        for c in row.controls:
            w = getattr(c, 'width', None)
            if isinstance(w, (int, float)) and w > width - 36:
                c.width = max(120, width - 36)


MOBILE_MIN_W = 900      # أقل عرض بتتبني عليه الشاشات على الموبايل (بعده تمرير أفقي)


def main(page: ft.Page):
    page.title = brand.NAME + ' - نظام ERP المحاسبي'
    try:
        from erp_app import files as _files
        page.fonts = {theme.FONT_FAMILY: _files.FONT_URL}      # خط عربي مرفق مع السيرفر (مش من الإنترنت)
    except Exception:
        pass
    page._erp_lang = i18n.default_lang()
    page.rtl = page._erp_lang == 'ar'
    theme.load_mode()
    page.bgcolor = theme.BG
    page.padding = 0
    page.theme = theme.app_theme()
    page.dark_theme = theme.app_theme(dark=True)
    page.theme_mode = ft.ThemeMode.DARK if theme.DARK else ft.ThemeMode.LIGHT

    notifier_ref = {'n': None, 'chat': None, 'docs': None}
    current_key = {'k': 'dashboard'}

    def stop_notifier():
        for k in ('n', 'chat', 'docs'):
            if notifier_ref[k]:
                notifier_ref[k].stop()
                notifier_ref[k] = None

    def logout(e=None, note=None):
        stop_notifier()
        page._erp_idle_token = None
        services.set_current_user(None)
        show_login(page, start)
        if note:
            page.snack_bar = ft.SnackBar(ft.Text(note)); page.snack_bar.open = True; page.update()

    idle_min = float(os.environ.get('ERP_SESSION_IDLE_MIN', '60') or 0)

    async def idle_watch(token):
        """بيطلّع المستخدم لو ما عملش أي حاجة المدة دي (ERP_SESSION_IDLE_MIN دقيقة، 0 = متعطّل)."""
        while getattr(page, '_erp_idle_token', None) is token:
            await asyncio.sleep(20)
            if getattr(page, '_erp_idle_token', None) is not token:
                return
            if time.time() - getattr(page, '_erp_last_active', time.time()) > idle_min * 60:
                logout(note='انتهت الجلسة لعدم النشاط - سجّل الدخول من جديد')
                return

    def start(user):
        stop_notifier()
        services.set_current_user(user)
        if idle_min > 0:
            tok = object()
            page._erp_idle_token = tok
            page._erp_last_active = time.time()
            page.run_task(idle_watch, tok)
        page._erp_lang = i18n.load_user_lang(user.get('username'), getattr(page, '_erp_lang', None))      # لغة المستخدم المحفوظة
        page.rtl = page._erp_lang == 'ar'
        page.title = brand.NAME + (' - نظام ERP المحاسبي' if page._erp_lang == 'ar' else ' - ERP Accounting System')
        page.clean()
        content = ft.Container(expand=True, padding=28)
        nav = []
        search_ref = {'open': None}        # لكل جلسة مستقلة (أكتر من جهاز على السيرفر)
        group_buttons = []
        section_open = {}
        submenu_title = ft.Text('', size=16, weight=ft.FontWeight.BOLD, color='#FFFFFF')
        submenu_body = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)
        submenu_panel = ft.Container(
            width=265,
            bgcolor=theme.SIDEBAR_BG,
            padding=ft.Padding(left=14, right=14, top=18, bottom=18),
            visible=False,
            content=ft.Column([
                ft.Row([submenu_title, ft.Container(expand=True)], alignment=ft.MainAxisAlignment.START),
                ft.Divider(color='#2A4A41'),
                submenu_body,
            ], spacing=10, expand=True),
        )

        def allowed(key):
            return services.user_has_action(user, key, 'view')

        def show_page(key):
            current_key['k'] = key
            page.on_keyboard_event = lambda e: _global_keys(e, search_ref)   # Ctrl+K للبحث الشامل؛ اختصارات لوحة المفاتيح بتاعة الشاشة السابقة (زي أسهم الجرد) ما تفضلش شغالة
            try:
                h = getattr(page, 'height', None) or getattr(getattr(page, 'window', None), 'height', None)
                if h:
                    theme.PAGE_HEIGHT = int(h)          # بيحدّد أقصى ارتفاع لمنطقة الجدول (عنوان ثابت + سكرول) حسب حجم النافذة
            except Exception:
                pass
            parent_key = next((g[0] for g in GROUPS if any(item[0] == key for item in g[3])), 'dashboard')
            for gk, b in group_buttons:
                active_group = gk == parent_key
                b.bgcolor = theme.PRIMARY if active_group else None
                for ch in (b.content.controls if isinstance(b.content, ft.Column) else [b.content]):
                    if isinstance(ch, (ft.Icon, ft.Text)):
                        ch.color = '#FFFFFF' if active_group else (theme.TEXT_MUTED if isinstance(ch, ft.Icon) else '#9FB8AE')
            for _, _, _, items in GROUPS:
                for k, label, icon, builder in items:
                    if k == key:
                        page.overlay.clear()  # امسح نوافذ/تقاويم الشاشة السابقة قبل بناء شاشة جديدة
                        page._erp_cards_used = False
                        if k in ('dashboard', 'organization', 'budgets'):
                            content.content = theme.call_without_page_update(page, builder, page, user)
                        else:
                            content.content = theme.call_without_page_update(page, builder, page)
                        if getattr(page, '_erp_compact', False):
                            _compact_headers(content.content, float(page.width or 390))
                        screen_ref['root'] = None
                        theme.fit_page_tables(content.content)       # توزيع أعمدة الجداول على عرض الصفحة
                        if parent_key == 'hr':      # شريط معاينة/طباعة ظاهر جوه كل شاشات الموارد البشرية وتقاريرها
                            built = content.content
                            screen_ref['root'] = built
                            bar = ft.Row([ft.OutlinedButton('معاينة', icon=ft.Icons.PREVIEW_OUTLINED, on_click=lambda e: preview_current()),
                                          ft.OutlinedButton('طباعة', icon=ft.Icons.PRINT_OUTLINED, on_click=lambda e: print_current())],
                                         alignment=ft.MainAxisAlignment.END, spacing=8)
                            bar._erp_nowrap = True
                            content.content = ft.Column([bar, built], expand=True, spacing=6)
                        # الموبايل: الشاشات المصمّمة لعرض الكمبيوتر بتتحط في منطقة بتتمرّر أفقيًا بدل ما تتقصّ (اللوحة الرئيسية متجاوبة أصلًا)
                        if False:      # (اتلغى) كان بيحط الشاشة في منطقة عرضها 900px؛ التجاوب العام في theme._compact_fix بقى هو المسؤول
                            content.content = ft.Row([ft.Column([content.content], expand=True, width=MOBILE_MIN_W)], scroll=ft.ScrollMode.AUTO,
                                                     expand=True, vertical_alignment=ft.CrossAxisAlignment.START)
                        break
            for k, b in nav:
                active = k == key
                b.bgcolor = theme.PRIMARY if active else None
                if b.content and hasattr(b.content, 'controls') and len(b.content.controls) >= 2:
                    b.content.controls[0].color = '#FFFFFF' if active else theme.TEXT_MUTED
                    b.content.controls[1].color = '#FFFFFF' if active else '#C7C9D9'
            page.update()

        page._erp_goto = lambda k: show_page(k) if k and allowed(k) else None

        if os.environ.get('ERP_E2E_NAV'):
            # للفحص الآلي بالمتصفح فقط (بيتفعّل بمتغير بيئة، مش شغّال في التشغيل العادي): اكتب مفتاح الشاشة في ملف nav.txt جوه مجلد البيانات وهتفتح.
            async def _e2e_nav():
                from erp_app import db as _db
                path = os.path.join(_db.APP_DIR, 'nav.txt')
                while True:
                    await asyncio.sleep(0.4)
                    try:
                        key = open(path).read().strip() if os.path.exists(path) else ''
                        if key:
                            os.remove(path)
                            page._erp_goto(key)
                    except Exception:
                        pass
            page.run_task(_e2e_nav)

        def open_group(group_key):
            group = next((g for g in GROUPS if g[0] == group_key), None)
            if not group:
                return
            _, title, _, items = group
            visible = [x for x in items if allowed(x[0])]
            if not visible:
                return
            # مجموعة فيها شاشة واحدة بس (مسموحة للمستخدم) تفتح مباشرة ولا تحتاج قائمة فرعية.
            if len(visible) == 1:
                submenu_panel.visible = False
                show_page(visible[0][0])
                return
            submenu_title.value = title
            submenu_body.controls.clear()
            nav.clear()

            def item_btn(key, label, icon):
                b = ft.Container(
                    content=ft.Row([
                        ft.Icon(icon, size=18, color=theme.TEXT_MUTED),
                        ft.Text(label, size=13, color='#C7C9D9', expand=True),
                    ], spacing=10),
                    padding=ft.Padding(left=12, right=12, top=9, bottom=9),
                    border_radius=9,
                    ink=True,
                    on_click=lambda e, k=key: show_page(k),
                )
                nav.append((key, b))
                return b

            sections = group_sections(group_key, visible)
            if not sections:
                for key, label, icon, builder in visible:
                    submenu_body.controls.append(item_btn(key, label, icon))
            else:
                cur = current_key['k']
                for si, (stitle, sicon, sitems) in enumerate(sections):
                    state_key = (group_key, stitle)
                    if state_key not in section_open:
                        section_open[state_key] = any(x[0] == cur for x in sitems) or (si == 0 and not any(x[0] == cur for _, _, ii in sections for x in ii))
                    body = ft.Column([item_btn(k, lb, ic) for k, lb, ic, _ in sitems], spacing=2, visible=section_open[state_key])
                    chev = ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN if section_open[state_key] else ft.Icons.CHEVRON_LEFT, size=18, color='#8FB5A8')

                    def toggle(e, sk=state_key, body=body, chev=chev):
                        section_open[sk] = not section_open[sk]
                        body.visible = section_open[sk]
                        chev.icon = ft.Icons.KEYBOARD_ARROW_DOWN if section_open[sk] else ft.Icons.CHEVRON_LEFT
                        page.update()

                    head = ft.Container(
                        content=ft.Row([ft.Icon(sicon, size=17, color='#8FB5A8'),
                                        ft.Text(stitle, size=12.5, weight=ft.FontWeight.W_700, color='#B7D3C8', expand=True), chev], spacing=8),
                        padding=ft.Padding(left=10, right=10, top=8, bottom=8), border_radius=8, ink=True, on_click=toggle,
                        bgcolor=ft.Colors.with_opacity(0.06, '#FFFFFF'))
                    submenu_body.controls.append(ft.Column([head, ft.Container(content=body, padding=ft.Padding(left=0, right=10, top=0, bottom=0))], spacing=3))
            submenu_panel.visible = True
            page.update()

        # شريط أيقونات رئيسي ضيق.
        icon_sidebar = ft.Container(
            width=80,
            gradient=ft.LinearGradient(begin=ft.Alignment(0, -1), end=ft.Alignment(0, 1),
                                       colors=[theme.SIDEBAR_BG, theme.SIDEBAR_BG_2]),
            padding=ft.Padding(left=8, right=8, top=18, bottom=18),
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=14, color=ft.Colors.with_opacity(0.18, "#000000"), offset=ft.Offset(3, 0)),
        )
        icon_column = ft.Column(spacing=8, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
        icon_sidebar.content = icon_column

        icon_column.controls.append(
            ft.Container(
                content=ft.Image(src=brand.mark_png(96), width=36, height=36, fit=ft.BoxFit.CONTAIN),
                padding=6,
                tooltip=brand.NAME,
            )
        )
        icon_column.controls.append(ft.Divider(color='#2A4A41', height=12))

        for group_key, title, group_icon, items in GROUPS:
            visible = [x for x in items if allowed(x[0])]
            if not visible:
                continue
            btn = ft.Container(
                width=62,
                height=60,
                border_radius=12,
                alignment=ft.Alignment(0, 0),
                tooltip=title,
                ink=True,
                on_click=lambda e, g=group_key: open_group(g),
                content=ft.Column([ft.Icon(group_icon, size=22, color=theme.TEXT_MUTED),
                                   ft.Text(SHORT_LABELS.get(group_key, title), size=10, color='#9FB8AE', max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, text_align=ft.TextAlign.CENTER)],
                                  spacing=3, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            )
            group_buttons.append((group_key, btn))
            icon_column.controls.append(btn)

        icon_column.controls.append(ft.Container(expand=True))
        icon_column.controls.append(
            ft.Text(user['full_name'], size=9, color='#C7C9D9', text_align=ft.TextAlign.CENTER)
        )

        title_txt = ft.Text(brand.NAME, size=19, weight=ft.FontWeight.W_800, color=theme.PRIMARY, style=ft.TextStyle(letter_spacing=0.6))
        user_icon = ft.Icon(ft.Icons.PERSON_OUTLINE, size=15, color=theme.PRIMARY)
        user_txt = ft.Text(user['full_name'], size=12.5, color=theme.PRIMARY_TEXT, weight=ft.FontWeight.W_600)
        user_chip = ft.Container(padding=ft.Padding(left=12, right=12, top=6, bottom=6), bgcolor=theme.PRIMARY_LIGHT, border_radius=20,
                                 content=ft.Row([user_icon, user_txt], spacing=6))
        mode_btn = ft.IconButton(icon=ft.Icons.DARK_MODE_OUTLINED, tooltip='الوضع الليلي')
        try:
            from erp_app import trial as _trial
            _dl = _trial.days_left()
        except Exception:
            _dl = None
        def _trial_view():
            try:
                ti, dl = _trial.info(), _trial.days_left()
            except Exception:
                return None, None, ''
            if not ti or dl is None:
                return None, None, ''
            return ti, dl, (f"{ti['plan_label']} - باقي {max(dl, 0)} يوم" if ti['paid'] else f"نسخة تجريبية - باقي {max(dl, 0)} يوم")
        _ti, _dl, _txt = _trial_view()
        trial_text = ft.Text(_txt, size=12, weight=ft.FontWeight.W_600, color=theme.DANGER if (_dl is not None and _dl <= 7) else theme.PRIMARY_TEXT)
        trial_chip = ft.Container(visible=_dl is not None, padding=ft.Padding(left=10, right=10, top=5, bottom=5), border_radius=20,
                                  bgcolor=theme.WARNING_LIGHT if hasattr(theme, 'WARNING_LIGHT') else theme.PRIMARY_LIGHT, tooltip='الاشتراك',
                                  on_click=(lambda e: show_page('subscription')) if allowed('subscription') else None, content=trial_text)

        def refresh_trial_chip():
            ti, dl, txt = _trial_view()
            trial_chip.visible = dl is not None and not getattr(page, '_erp_compact', False)
            trial_text.value = txt
            trial_text.color = theme.DANGER if (dl is not None and dl <= 7) else theme.PRIMARY_TEXT
            page.update()
        page._erp_refresh_trial = refresh_trial_chip
        search_btn = ft.IconButton(icon=ft.Icons.SEARCH, tooltip='بحث شامل (Ctrl+K)')

        screen_ref = {'root': None}

        def print_target():
            """(root, title, subtitle) للشاشة الحالية أو للنافذة المفتوحة فوقها."""
            from erp_app import print_screen
            en = getattr(page, '_erp_lang', 'ar') == 'en'
            label = next((l for _, _, _, items in GROUPS for k, l, _, _ in items if k == current_key['k']), brand.NAME)
            root, title, sub = (screen_ref['root'] or content.content), (i18n.tr(label) if en else label), ''
            dlgs = [o for o in page.overlay if isinstance(o, ft.AlertDialog) and getattr(o, 'open', False) and not getattr(o, '_erp_preview', False)]
            if dlgs:
                root, sub = dlgs[-1].content, title
                title = print_screen._text_of(dlgs[-1].title).strip() or title
            return root, title, sub

        def print_current(e=None):
            """طباعة الشاشة الحالية (أو النافذة المفتوحة فوقها) كـ PDF بيتفتح في المتصفح للطباعة."""
            try:
                from erp_app import print_screen
                root, title, sub = print_target()
                path = print_screen.print_control(root, title, os.path.join(services.APP_DIR, 'exports'), rtl=getattr(page, '_erp_lang', 'ar') == 'ar', subtitle=sub)
                theme.open_or_download_file(page, path)
            except Exception as ex:
                page.overlay.append(ft.SnackBar(ft.Text(f'تعذرت الطباعة: {ex}'), open=True)); page.update()

        def preview_current(e=None):
            """معاينة محتوى الطباعة في نافذة قبل ما تطبع."""
            try:
                from erp_app import print_screen
                root, title, sub = print_target()
                d = print_screen.open_preview(page, root, title, sub, rtl=getattr(page, '_erp_lang', 'ar') == 'ar',
                                              on_print=lambda: print_current())
                d._erp_preview = True
            except Exception as ex:
                page.overlay.append(ft.SnackBar(ft.Text(f'تعذرت المعاينة: {ex}'), open=True)); page.update()

        preview_btn = ft.IconButton(icon=ft.Icons.PREVIEW_OUTLINED, tooltip='معاينة قبل الطباعة', on_click=preview_current)

        print_btn = ft.IconButton(icon=ft.Icons.PRINT_OUTLINED, tooltip='طباعة الشاشة', on_click=print_current)

        def toggle_lang(e=None):
            new = 'en' if getattr(page, '_erp_lang', 'ar') == 'ar' else 'ar'
            i18n.save_user_lang(user.get('username'), new)
            start(user)                       # إعادة بناء الواجهة كلها باللغة الجديدة (والاتجاه RTL/LTR)

        lang_btn = ft.TextButton('EN' if getattr(page, '_erp_lang', 'ar') == 'ar' else 'عربي', tooltip='English / العربية', on_click=toggle_lang)
        brand_icon = ft.Image(src=brand.mark_png(96), width=30, height=30, fit=ft.BoxFit.CONTAIN)
        top_spacer = ft.Container(expand=True)
        top = ft.Container(
            bgcolor=theme.CARD_BG,
            padding=ft.Padding(left=24, right=24, top=13, bottom=13),
            border=ft.border.Border(bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT)),
            content=ft.Row([
                brand_icon,
                title_txt,
                top_spacer,
                trial_chip,
                preview_btn,
                print_btn,
                search_btn,
                lang_btn,
                mode_btn,
                ft.IconButton(icon=ft.Icons.SHIELD_OUTLINED, tooltip='الأمان: كلمة المرور والتحقق بخطوتين', on_click=lambda e: security_view.open_security_dialog(page)),
                user_chip,
                ft.IconButton(
                    icon=ft.Icons.LOGOUT,
                    tooltip='تسجيل الخروج',
                    on_click=logout,
                ),
            ], spacing=10),
        )

        top.content._erp_nowrap = True       # الشريط العلوي يفضل سطر واحد على الموبايل (مش بيلفّ)

        def apply_chrome():
            page.bgcolor = theme.BG
            page.theme_mode = ft.ThemeMode.DARK if theme.DARK else ft.ThemeMode.LIGHT
            top.bgcolor = theme.CARD_BG
            top.border = ft.border.Border(bottom=ft.border.BorderSide(1, theme.BORDER_LIGHT))
            title_txt.color = theme.TEXT
            user_chip.bgcolor = theme.PRIMARY_LIGHT
            user_txt.color = theme.PRIMARY_TEXT
            mode_btn.icon = ft.Icons.LIGHT_MODE_OUTLINED if theme.DARK else ft.Icons.DARK_MODE_OUTLINED
            mode_btn.tooltip = 'الوضع الفاتح' if theme.DARK else 'الوضع الليلي'

        def toggle_mode(e=None):
            theme.set_dark(not theme.DARK)
            apply_chrome()
            show_page(current_key['k'])        # إعادة بناء الشاشة الحالية بالألوان الجديدة

        mode_btn.on_click = toggle_mode
        apply_chrome()

        def open_search(e=None):
            def go(screen, text):
                dlg.open = False
                page.update()
                show_page(screen)
                prefill_search(content.content, text)

            q = ft.TextField(hint_text='ابحث عن عميل، مورد، صنف، فاتورة، موظف، حساب، سند...', autofocus=True, prefix_icon=ft.Icons.SEARCH, border_radius=12, dense=True)
            res = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, height=380)
            hint = ft.Text('اكتب حرفين على الأقل', size=12, color=theme.TEXT_MUTED)
            res.controls.append(hint)

            def run(ev=None):
                res.controls.clear()
                text = (q.value or '').strip()
                if len(text) < 2:
                    res.controls.append(hint)
                else:
                    try:
                        groups = global_search.search(text)
                    except Exception as ex:
                        groups = []
                        res.controls.append(ft.Text(f'تعذر البحث: {ex}', color=theme.DANGER))
                    for g in groups:
                        res.controls.append(ft.Text(g['label'], size=12, weight=ft.FontWeight.BOLD, color=theme.PRIMARY_TEXT))
                        for it in g['items']:
                            res.controls.append(ft.Container(
                                padding=ft.Padding(left=12, right=12, top=8, bottom=8), border_radius=8, ink=True, bgcolor=theme.SURFACE_ALT,
                                on_click=lambda ev, sc=g['screen'], t=text: go(sc, t),
                                content=ft.Column([ft.Text(it['title'], size=13, weight=ft.FontWeight.W_600), ft.Text(it['sub'] or ' ', size=11, color=theme.TEXT_MUTED)], spacing=1)))
                    if not groups and not res.controls:
                        res.controls.append(ft.Text('لا توجد نتائج', color=theme.TEXT_MUTED))
                page.update()

            def submit(ev=None):
                g = global_search.find_first(q.value) if len((q.value or '').strip()) >= 2 else None
                if g:
                    go(g['screen'], (q.value or '').strip())

            q.on_change = run
            q.on_submit = submit
            dlg = ft.AlertDialog(modal=False, title=ft.Text('بحث شامل'), content=ft.Container(width=520, content=ft.Column([q, res], spacing=10, tight=True)),
                                 actions=[ft.TextButton('إغلاق', on_click=lambda ev: (setattr(dlg, 'open', False), page.update()))])
            page.overlay.append(dlg)
            dlg.open = True
            page.update()

        search_btn.on_click = open_search
        search_ref['open'] = open_search
        # جرس جدول الأعمال: عدّاد المواعيد (متأخر + النهاردة) + نافذة تنبيه قبل الموعد
        if allowed('agenda'):
            notifier = AgendaNotifier(page, user['username'], open_agenda=lambda: show_page('agenda'))
            notifier_ref['n'] = notifier
            top.content.controls.insert(3, notifier.control)
        if allowed('hr_documents'):
            doc_notifier = DocumentNotifier(page, user['username'], open_screen=lambda: show_page('hr_documents'))
            notifier_ref['docs'] = doc_notifier
            top.content.controls.insert(3, doc_notifier.control)
        if allowed('chat'):
            chat_notifier = ChatNotifier(page, user['username'], open_chat=lambda: show_page('chat'), is_chat_open=lambda: current_key['k'] == 'chat')
            notifier_ref['chat'] = chat_notifier
            top.content.controls.insert(3, chat_notifier.control)
        main_area = ft.Column([top, content], spacing=0, expand=True)

        # ---- وضع الموبايل / الشاشات الضيقة: القوائم الجانبية بتتحول لزر قائمة بيفتح نافذة بكل الشاشات ----
        COMPACT_W = 760
        menu_btn = ft.IconButton(icon=ft.Icons.MENU, tooltip='القائمة', visible=False, icon_size=26)
        top.content.controls.insert(0, menu_btn)
        layout = {'compact': None}

        def open_menu(e=None):
            tiles = []
            for gk, gtitle, gicon, items in GROUPS:
                vis = [x for x in items if allowed(x[0])]
                if not vis:
                    continue
                if len(vis) == 1:
                    tiles.append(ft.ListTile(leading=ft.Icon(gicon), title=ft.Text(gtitle), on_click=lambda ev, k=vis[0][0]: go_menu(k)))
                    continue
                def _lt(k, lb, ic):
                    return ft.ListTile(leading=ft.Icon(ic, size=18), title=ft.Text(lb, size=13), dense=True, on_click=lambda ev, k=k: go_menu(k))
                secs = group_sections(gk, vis)
                if secs:
                    kids = [ft.ExpansionTile(leading=ft.Icon(sic, size=18), title=ft.Text(st, size=13, weight=ft.FontWeight.W_600),
                                             controls=[_lt(k, lb, ic) for k, lb, ic, _ in sit]) for st, sic, sit in secs]
                else:
                    kids = [_lt(k, lb, ic) for k, lb, ic, _ in vis]
                tiles.append(ft.ExpansionTile(leading=ft.Icon(gicon), title=ft.Text(gtitle, weight=ft.FontWeight.W_600), controls=kids))
            dlg = ft.AlertDialog(modal=False, title=ft.Text('القائمة'), content_padding=ft.Padding(left=0, right=0, top=8, bottom=0),
                                 content=ft.Container(width=340, height=min(520, int((page.height or 700) * 0.7)), content=ft.Column(tiles, scroll=ft.ScrollMode.AUTO, spacing=0)),
                                 actions=[ft.TextButton('إغلاق', on_click=lambda ev: close_dlg())])

            def close_dlg():
                dlg.open = False
                page.update()

            def go_menu(k):
                dlg.open = False
                page.update()
                show_page(k)
            page.overlay.append(dlg)
            dlg.open = True
            page.update()

        menu_btn.on_click = open_menu

        def apply_layout(e=None):
            try:
                w = float(page.width or 0)
            except Exception:
                w = 0
            compact = bool(w) and w < COMPACT_W
            if compact == layout['compact']:
                return
            first = layout['compact'] is None
            layout['compact'] = compact
            page._erp_compact = compact
            icon_sidebar.visible = not compact
            if compact:
                submenu_panel.visible = False
            menu_btn.visible = compact
            title_txt.visible = not compact
            brand_icon.visible = not compact
            top_spacer.visible = not compact
            top.content.scroll = ft.ScrollMode.AUTO if compact else None      # لو الأيقونات أكتر من العرض: الشريط يتحرك بالسحب
            trial_chip.visible = (not compact) and _dl is not None
            user_chip.visible = not compact
            content.padding = 10 if compact else 28
            top.padding = ft.Padding(left=8, right=8, top=6, bottom=6) if compact else ft.Padding(left=24, right=24, top=13, bottom=13)
            top.content.spacing = 2 if compact else 10
            if not first:
                show_page(current_key['k'])      # إعادة بناء الشاشة الحالية بالتخطيط المناسب
            page.update()

        page.on_resize = apply_layout

        # RTL: لوحة القوائم تكون بجانب المحتوى، والقائمة الفرعية تظهر بجوار شريط الأيقونات.
        page.add(ft.Row([icon_sidebar, submenu_panel, main_area], spacing=0, expand=True))
        show_page('dashboard')
        apply_layout()
        try:
            if user.get('role') == 'admin' and services.is_default_admin_password():
                page.overlay.append(ft.SnackBar(ft.Text('تنبيه أمان: كلمة مرور المدير ما زالت الافتراضية (admin). غيّرها من شاشة المستخدمين قبل ما تشغّل البرنامج على الشبكة.'), open=True, duration=15000))
                page.update()
        except Exception:
            pass
        for k in ('n', 'chat', 'docs'):
            if notifier_ref[k]:
                notifier_ref[k].start()
        # المهام الدورية (نسخ احتياطي، تقارير مجدولة، رسائل، تنبيهات) بتشتغل على مستوى السيرفر في erp_app/scheduler.py - مش مرتبطة بفتح أي مستخدم للمتصفح.
        # ترحيل أقساط المصروفات المدفوعة مقدمًا المستحقة آليًا عند فتح البرنامج
        if allowed('prepaid_expenses'):
            rep = services.auto_post_prepaid_expenses()
            if rep['posted'] or rep['errors']:
                msg = f"المصروفات المقدمة: اترحّل {rep['posted']} قسط بقيمة {rep['amount']:,.2f}" if rep['posted'] else ''
                if rep['errors']:
                    msg += (' | ' if msg else '') + f"تعذّر {len(rep['errors'])} قسط (فترة مقفولة؟)"
                page.overlay.append(ft.SnackBar(ft.Text(msg), open=True)); page.update()

    show_login(page, start)


if __name__ == '__main__':
    # البرنامج سيرفر ويب فقط: التشغيل من server.py (python server.py). الأمر ده بيوجّه له.
    import server
    raise SystemExit(server.run())
