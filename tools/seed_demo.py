"""يبني قاعدة بيانات تجريبية كاملة (شركة وهمية) على مجلد البيانات الحالي.
    python tools/seed_demo.py            (على ERP_HOME أو مجلد المشروع - لازم القاعدة تكون جديدة)
بيضيف: فروع ومخازن، أصناف، عملاء وموردين، مشتريات ومبيعات وكاشير ومرتجع، سندات قبض ودفع، موظفين وعقود ورواتب وإجازات،
أصول وإهلاك، مطعم، عروض أسعار، موازنات، عُهد، مستندات، مصروفات مقدّمة، قيود يومية وقوالب ومواعيد.
بيانات وهمية للتجربة بس - ما تستخدمهاش في شغل حقيقي."""
import datetime
import os
import random
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from erp_app import db, services as S  # noqa: E402

D = datetime.datetime
TODAY = datetime.datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
random.seed(7)
LOG = []


def step(name):
    def deco(fn):
        try:
            r = fn()
            LOG.append((name, "ok"))
            return r
        except Exception as ex:
            LOG.append((name, f"FAIL: {ex}"))
            traceback.print_exc()
    return deco


def ago(days):
    return TODAY - datetime.timedelta(days=days)


def acc(code):
    return next(a.id for a in S.list_accounts() if a.code == code)


B2B = dict(address="جدة - شارع التحلية", crn="1010999888", building_no="1234", district="الروضة", city="جدة", postal_code="23433")


def main():
    db.init_db()
    S.set_current_user(S.authenticate_user("admin", "admin"))
    ids = {}

    @step("company")
    def _():
        S.update_company_settings(name="شركة أشور التجريبية للتجارة", vat_number="300123456700003", phone="0500000000",
                                  address="جدة - حي الروضة", email="demo@ashour.example")

    @step("branches/locations")
    def _():
        ids["br2"] = S.create_branch("BR02", "فرع الرياض")
        ids["cc_sales"] = S.create_cost_center("CC-SALES", "قسم المبيعات")
        ids["cc_adm"] = S.create_cost_center("CC-ADM", "الإدارة")
        ids["loc1"] = S.list_locations()[0].id
        ids["loc2"] = S.create_location("مخزن الرياض", branch_id=ids["br2"])

    @step("users")
    def _():
        S.create_user("cashier1", "123456", "أحمد الكاشير", role="user")
        S.create_user("accountant", "123456", "سارة المحاسبة", role="user")

    @step("products")
    def _():
        cats = {n: S.create_category(n) for n in ["مواد غذائية", "مشروبات", "منظفات", "إلكترونيات", "أدوات مكتبية", "وجبات المطعم"]}
        rows = [
            ("F001", "أرز بسمتي 5 كجم", "مواد غذائية", 38, 52), ("F002", "سكر 2 كجم", "مواد غذائية", 7, 10),
            ("F003", "زيت طبخ 1.5 لتر", "مواد غذائية", 12, 17), ("F004", "دقيق 5 كجم", "مواد غذائية", 14, 20),
            ("F005", "شاي ليبتون 100 كيس", "مواد غذائية", 11, 16), ("F006", "تونة 185 جم", "مواد غذائية", 4, 6.5),
            ("D001", "مياه 330 مل (كرتون)", "مشروبات", 9, 14), ("D002", "عصير برتقال 1 لتر", "مشروبات", 4, 7),
            ("D003", "بيبسي 330 مل", "مشروبات", 1.5, 3), ("D004", "قهوة عربية 250 جم", "مشروبات", 18, 28),
            ("C001", "سائل جلي 750 مل", "منظفات", 6, 10), ("C002", "مسحوق غسيل 3 كجم", "منظفات", 19, 28),
            ("C003", "مناديل (علبة)", "منظفات", 3, 5), ("C004", "كلور 4 لتر", "منظفات", 8, 13),
            ("E001", "سماعة بلوتوث", "إلكترونيات", 45, 79), ("E002", "شاحن سريع 25 واط", "إلكترونيات", 22, 39),
            ("E003", "كابل USB-C", "إلكترونيات", 5, 12), ("E004", "باور بنك 10000", "إلكترونيات", 60, 99),
            ("O001", "دفتر A4 (100 ورقة)", "أدوات مكتبية", 4, 8), ("O002", "قلم حبر (علبة 12)", "أدوات مكتبية", 9, 16),
            ("O003", "ورق تصوير A4 (رزمة)", "أدوات مكتبية", 14, 22), ("O004", "ملف حافظ", "أدوات مكتبية", 2, 4),
        ]
        ids["prods"] = []
        for sku, name, cat, cost, price in rows:
            pid = S.create_product(sku, name, category_id=cats[cat], cost_price=cost, sale_price=price, reorder_point=20)
            ids["prods"].append((pid, cost, price))
        # أصناف المطعم (خدمية/جاهزة)
        ids["menu"] = []
        for sku, name, price in [("R001", "برجر لحم", 28), ("R002", "دجاج مشوي", 32), ("R003", "بيتزا مارجريتا", 30),
                                 ("R004", "سلطة سيزر", 18), ("R005", "عصير طازج", 12), ("R006", "قهوة", 10)]:
            ids["menu"].append(S.create_product(sku, name, category_id=cats["وجبات المطعم"], cost_price=price * 0.35, sale_price=price, product_type="service"))

    @step("parties")
    def _():
        ids["custs"] = [S.create_customer(n, phone=f"05{random.randint(10000000, 99999999)}", credit_limit=lim, credit_days=30,
                                          vat_number=vat, party_type=pt, **(B2B if pt == "company" else {}))
                        for n, lim, vat, pt in [("مؤسسة النور التجارية", 50000, "300111222300003", "company"), ("شركة الأفق للمقاولات", 80000, "300222333400003", "company"),
                                                ("محمد العتيبي", 5000, "", "individual"), ("فهد القحطاني", 5000, "", "individual"),
                                                ("بقالة الحي", 20000, "300999111200003", "company"), ("مطعم السعادة", 30000, "300333444500003", "company")]]
        ids["cash_cust"] = S.create_customer("عميل نقدي")
        ids["sups"] = [S.create_supplier(n, phone=f"05{random.randint(10000000, 99999999)}", vat_number=v, address="جدة")
                       for n, v in [("شركة الخليج للتوريدات", "300444555600003"), ("مؤسسة الأمل للجملة", "300555666700003"),
                                    ("الدولية للإلكترونيات", "300666777800003"), ("مصنع القرطاسية الحديث", "300777888900003")]]

    @step("price list")
    def _():
        pl = S.create_price_list("أسعار الجملة")
        S.set_price_list_items_bulk(pl, [{"product_id": pid, "price": round(price * 0.9, 2)} for pid, _, price in ids["prods"][:10]])

    @step("purchases")
    def _():
        n = len(ids["prods"])
        for k, sid in enumerate(ids["sups"]):
            items = [{"product_id": pid, "quantity": random.choice([60, 80, 100, 120]), "unit_price": cost}
                     for pid, cost, _ in ids["prods"][k::4]]
            S.create_purchase_invoice(sid, items, location_id=ids["loc1"], invoice_date=ago(80 - k * 9), notes="توريد دوري")
        # نقل بعض الكمية لمخزن الرياض
        for pid, cost, _ in ids["prods"][:6]:
            S.create_stock_transfer(pid, ids["loc1"], ids["loc2"], 10, unit_cost=cost, note="تغذية فرع الرياض")

    @step("sales")
    def _():
        invs = []
        for i in range(40):
            cust = random.choice(ids["custs"])
            picks = random.sample(ids["prods"], random.randint(1, 4))
            items = [{"product_id": pid, "quantity": random.randint(1, 6), "unit_price": price, "discount": 0, "tax_rate": 15} for pid, _, price in picks]
            try:
                invs.append(S.create_sales_invoice(cust, items, location_id=ids["loc1"], invoice_date=ago(random.randint(1, 70))))
            except Exception as ex:
                LOG.append(("sales-skip", str(ex)[:80]))
        ids["invs"] = invs

    @step("receipts/payments")
    def _():
        cash, bank = acc("121001"), acc("121004")
        for cid in ids["custs"][:4]:
            S.create_receipt(cid, 1500, cash, date=ago(random.randint(1, 30)), notes="دفعة من الحساب")
        S.create_receipt(ids["custs"][1], 4000, bank, date=ago(10), notes="تحويل بنكي")
        for sid in ids["sups"][:3]:
            S.create_payment(sid, 2000, bank, date=ago(random.randint(1, 30)), notes="سداد جزء من المستحق")

    @step("quotations")
    def _():
        for i, cid in enumerate(ids["custs"][:3]):
            items = [{"product_id": pid, "quantity": 10, "unit_price": price, "tax_rate": 15} for pid, _, price in ids["prods"][14:17]]
            q = S.create_quotation(cid, items, notes="عرض سعر تجريبي", quote_date=ago(5 + i), valid_until=TODAY + datetime.timedelta(days=20))
            if i == 1:
                S.set_quotation_state(q, "sent")

    @step("pos")
    def _():
        term = S.create_pos_terminal("T1", "كاشير 1", default_customer_id=ids["cash_cust"], payment_method_ids=[1, 2], default_payment_method_id=1,
                                     location_id=ids["loc1"])
        sess = S.open_pos_session(term, 500)
        for i in range(25):
            picks = random.sample(ids["prods"], random.randint(1, 3))
            items = [{"product_id": pid, "quantity": random.randint(1, 3), "unit_price": price} for pid, _, price in picks]
            S.create_pos_sale(ids["cash_cust"], items, payment_method_id=random.choice([1, 2]), terminal_id=term)
        ids["term"], ids["sess"] = term, sess
        S.close_pos_session(sess, counted_cash=500)

    @step("sales return")
    def _():
        inv = ids["invs"][0]
        S.create_full_sales_return(inv, "مرتجع تجريبي - عيب تصنيع", refund_method_id=1)

    @step("hr")
    def _():
        staff = [("خالد الشمري", "مدير مبيعات", "المبيعات", 9000), ("نورة العنزي", "محاسبة", "المالية", 7000),
                 ("يوسف الحربي", "أمين مستودع", "المخازن", 5000), ("ريم الدوسري", "موظفة استقبال", "الإدارة", 4500),
                 ("عمر السبيعي", "كاشير", "المبيعات", 4000), ("هند المطيري", "مشرفة مطعم", "المطعم", 5500)]
        ids["emps"] = []
        for k, (n, pos, dep, sal) in enumerate(staff):
            e = S.create_employee(n, national_id=f"10{random.randint(10000000, 99999999)}", phone=f"05{random.randint(10000000, 99999999)}",
                                  position=pos, department=dep, hire_date=D(2024, 1 + k, 1))
            S.create_contract(e, D(2024, 1 + k, 1), sal, housing_allowance=sal * 0.25, transport_allowance=400,
                              basic_salary_account_id=acc("520001"), housing_allowance_account_id=acc("520006"), transport_allowance_account_id=acc("520007"),
                              other_allowances_account_id=acc("520009"), gosi_deduction_account_id=acc("223008"), other_deductions_account_id=acc("224001"),
                              gosi_employer_expense_account_id=acc("520010"), gosi_employer_payable_account_id=acc("223008"),
                              leave_provision_expense_account_id=acc("520012"), leave_provision_payable_account_id=acc("224004"),
                              eos_provision_expense_account_id=acc("520013"), eos_provision_payable_account_id=acc("211000"))
            ids["emps"].append(e)

    @step("payroll")
    def _():
        for m in (8, 9):
            run = S.create_payroll_run(m, 2026)
            S.post_payroll_run(run)
            S.pay_payroll_run(run, 3, payment_date=D(2026, m, 28))

    @step("leaves")
    def _():
        types = [t.code for t in S.list_leave_types()]
        S.create_leave_request(ids["emps"][1], types[0], D(2026, 11, 2), D(2026, 11, 6), "إجازة سنوية")
        S.create_leave_request(ids["emps"][2], types[1], D(2026, 10, 12), D(2026, 10, 13), "ظرف صحي")

    @step("assets")
    def _():
        ac = S.create_asset_category("أجهزة حاسب", acc("111021"), acc("111022"), acc("530009"), useful_life_months=48)
        ids["asset_cat"] = ac
        for code, name, cost, d in [("AST-001", "لابتوب إدارة", 4500, D(2026, 3, 1)), ("AST-002", "طابعة ليزر", 1800, D(2026, 5, 15)),
                                    ("AST-003", "خادم الشركة", 12000, D(2026, 6, 1))]:
            S.create_fixed_asset(code, name, d, cost, category_id=ac)
        for m in (8, 9):
            r = S.create_depreciation_run(m, 2026)
            S.post_depreciation_run(r)

    @step("restaurant")
    def _():
        rt = S.create_pos_terminal("R1", "كاشير المطعم", default_customer_id=ids["cash_cust"], payment_method_ids=[1, 2], default_payment_method_id=1, location_id=ids["loc1"])
        S.open_pos_session(rt, 0)
        ids["rterm"] = rt
        sec = S.create_restaurant_section("الصالة الرئيسية")
        tabs = [S.create_restaurant_table(str(i), seats=4, section_id=sec) for i in range(1, 7)]
        for t in tabs[:3]:
            o = S.open_restaurant_order(table_id=t, guests=2, terminal_id=ids["rterm"])
            for mid in random.sample(ids["menu"], 3):
                S.add_restaurant_order_item(o, mid, quantity=random.randint(1, 2))

    @step("custody")
    def _():
        c = S.create_custody(ids["emps"][2], 2000, 1, date=ago(15), purpose="عهدة مشتريات نثرية")
        S.add_custody_expense(c, "expense", acc("520078"), 350, description="أدوات مكتبية", date=ago(10))
        S.add_custody_expense(c, "expense", acc("520079"), 120, description="انتقالات", date=ago(8))

    @step("budget")
    def _():
        for code, amt in [("520001", 60000), ("520041", 9000), ("520078", 3000)]:
            S.create_budget_line(f"موازنة {code}", D(2026, 1, 1), D(2026, 12, 31), acc(code), amt)

    @step("documents")
    def _():
        dts = {d.name: d.id for d in S.list_document_types()}
        k = next(iter(dts))
        S.create_tracked_document(dts[k], TODAY + datetime.timedelta(days=25), title="السجل التجاري", doc_number="1010123456", issuer="وزارة التجارة")
        S.create_tracked_document(dts[k], TODAY + datetime.timedelta(days=200), title="رخصة البلدية", doc_number="BL-7788", issuer="البلدية")

    @step("prepaid")
    def _():
        S.create_prepaid_expense("إيجار المعرض سنة", acc("520038"), 24000, D(2026, 7, 1), months=12, payment_kind="paid", payment_method_id=1)

    @step("journal")
    def _():
        cash, bank, cap, rent = acc("121001"), acc("121004"), acc("310000"), acc("520037")
        e1 = S.create_journal_entry([{"account_id": bank, "debit": 100000, "credit": 0, "description": "زيادة رأس المال"},
                                     {"account_id": cap, "debit": 0, "credit": 100000, "description": "زيادة رأس المال"}],
                                    description="إيداع رأس مال إضافي", entry_date=ago(85))
        e2 = S.create_journal_entry([{"account_id": rent, "debit": 3500, "credit": 0, "description": "إيجار أكتوبر"},
                                     {"account_id": cash, "debit": 0, "credit": 3500, "description": "إيجار أكتوبر"}],
                                    description="إيجار الموقع - أكتوبر", entry_date=ago(12))
        from erp_app import journal_tools as J
        J.reverse_journal_entry(e2, reason="تجربة قيد عكسي")
        tid = J.save_template("إيجار شهري", [{"account_id": rent, "debit": 3500, "credit": 0, "description": "إيجار الموقع"},
                                             {"account_id": cash, "debit": 0, "credit": 3500, "description": "إيجار الموقع"}], description="قيد الإيجار الشهري")
        J.save_recurrence(tid, "monthly", TODAY + datetime.timedelta(days=9), auto_post=True)

    @step("agenda")
    def _():
        for i, t in enumerate(["اجتماع المبيعات الأسبوعي", "مراجعة المخزون", "تسليم إقرار الضريبة"]):
            S.create_agenda_item(t, datetime.datetime.combine(TODAY + datetime.timedelta(days=i + 1), datetime.time(10, 0)))

    for n, r in LOG:
        print(f"{'✓' if r == 'ok' else '✗'} {n} {'' if r == 'ok' else r}")


if __name__ == "__main__":
    main()
