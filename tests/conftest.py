"""إعداد الاختبارات: كل جلسة اختبار بتشتغل على مجلد بيانات مؤقت معزول (ERP_HOME) فمفيش أي لمس لبياناتك.
لاختبار PostgreSQL:  ERP_TEST_PG_URL=postgresql://user:pw@host:5432/erp_test pytest   (القاعدة بتتفضّى قبل كل ملف اختبار - استخدم قاعدة اختبار مخصصة!)"""
import os
import sys
import tempfile

_HOME = tempfile.mkdtemp(prefix="erp_test_")
os.environ["ERP_HOME"] = _HOME
_pg = os.environ.get("ERP_TEST_PG_URL", "").strip()
if _pg:
    os.environ["ERP_DATABASE_URL"] = _pg
else:
    os.environ.pop("ERP_DATABASE_URL", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import glob  # noqa: E402

import pytest  # noqa: E402

from erp_app import db  # noqa: E402


@pytest.fixture(scope="module")
def S():
    """قاعدة نظيفة + مدير النظام مسجّل دخول. بيرجّع وحدة services."""
    db.engine.dispose()
    db.Base.metadata.drop_all(db.engine)
    for f in glob.glob(os.path.join(db.APP_DIR, "*.json")):
        os.remove(f)
    db.init_db()
    from erp_app import services
    services._LOGIN_FAILS.clear()
    try:       # اختبارات شاشات قبلها بتسيب صفحة وهمية في سياق Flet فالمستخدم كان بيتخزن عليها بدل المتغير العام
        from flet.controls.context import _context_page
        _context_page.set(None)
    except Exception:      # noqa: BLE001
        pass
    services.set_current_user(services.authenticate_user("admin", "admin"))
    return services


@pytest.fixture(scope="module")
def shop(S):
    """بيانات تشغيل أساسية: أصناف وعميل وماكينة كاشير وجلسة مفتوحة."""
    S.update_company_settings(name="شركة اختبار", vat_number="300123456700003")
    ids = {}
    ids["burger"] = S.create_product("P1", "برجر", sale_price=100, cost_price=40, product_type="service")
    ids["cola"] = S.create_product("P2", "بيبسي", sale_price=5, cost_price=2, product_type="service")
    ids["item"] = S.create_product("G1", "سلعة مخزنية", sale_price=30, cost_price=12)
    ids["cust"] = S.create_customer(name="عميل نقدي")
    ids["supplier"] = S.create_supplier(name="مورد 1")
    ids["term"] = S.create_pos_terminal("T1", "كاشير 1", default_customer_id=ids["cust"], payment_method_ids=[1, 2], default_payment_method_id=1)
    S.open_pos_session(ids["term"], 0)
    ids["loc"] = S.list_locations()[0].id
    return ids


_SLOW_FILES = ("test_portal.py", "test_concurrency_browser.py", "test_print_screen.py", "test_perf.py")


def pytest_collection_modifyitems(items):
    import pytest
    for it in items:
        if it.fspath.basename in _SLOW_FILES:
            it.add_marker(pytest.mark.slow)
