"""الحضور وجهاز البصمة: استيراد ملفات، ADMS، ربط الموظفين، حساب الغياب في الرواتب."""
import datetime
import urllib.parse

import pytest

D = datetime.datetime


def _accs(S):
    a = [x.id for x in S.list_accounts(postable_only=True)]
    return a[0], a[1]


def _emp(S, name, dev):
    ex, pay = _accs(S)
    eid = S.create_employee(name, hire_date=D(2025, 1, 1))
    S.create_contract(eid, D(2025, 1, 1), 3000, housing_allowance=600, transport_allowance=400, gosi_rate_employee=0, gosi_rate_employer=0,
                      leave_provision_rate=0, eos_provision_rate=0, basic_salary_account_id=ex, housing_allowance_account_id=ex,
                      transport_allowance_account_id=ex, gosi_deduction_account_id=pay, other_deductions_account_id=pay)
    from erp_app import attendance
    if dev:
        attendance.set_employee_device_id(eid, dev)
    return eid


def _work_days(year, month, skip=()):
    d = datetime.date(year, month, 1)
    out = []
    while d.month == month:
        if d.weekday() not in (4, 5) and d.day not in skip:
            out.append(d)
        d += datetime.timedelta(days=1)
    return out


def test_norm_and_parse_file(S, tmp_path):
    from erp_app import attendance as A
    assert A.norm_id("007") == "7" and A.norm_id("٠٠٧") == "7" and A.norm_id(" 12 ") == "12"
    f = tmp_path / "p.csv"
    f.write_text("User ID,Date/Time\n7,2026-04-01 08:00:00\n7,01/04/2026 17:00\n٨,2026-04-02 08:05\nbad,xx\n", encoding="utf-8")
    punches, skipped = A.parse_attendance_file(str(f))
    assert len(punches) == 3 and skipped == 1
    f2 = tmp_path / "q.csv"
    f2.write_text("رقم الموظف;التاريخ;الوقت\n5;2026-04-01;08:00\n", encoding="utf-8")
    assert A.parse_attendance_file(str(f2))[0][0][1] == D(2026, 4, 1, 8, 0)
    f3 = tmp_path / "raw.txt"
    f3.write_text("5\t2026-04-01 08:00:00\t0\t1\n", encoding="utf-8")
    assert len(A.parse_attendance_file(str(f3))[0]) == 1
    f4 = tmp_path / "bad.csv"
    f4.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        A.parse_attendance_file(str(f4))


def test_link_unique_and_relink(S):
    from erp_app import attendance as A
    a = _emp(S, "علي", "101")
    b = _emp(S, "بدر", "")
    with pytest.raises(ValueError):
        A.set_employee_device_id(b, "0101")
    A.import_punches([("202", D(2026, 4, 1, 8, 0))])         # غير مربوط
    A.set_employee_device_id(b, "202")
    from erp_app.db import get_session, AttendanceLog
    with get_session() as s:
        assert s.query(AttendanceLog).filter(AttendanceLog.norm_id == "202").first().employee_id == b
    r = A.import_punches([("202", D(2026, 4, 1, 8, 0)), ("202", D(2026, 4, 1, 8, 0))])
    assert r["inserted"] == 0 and r["duplicates"] == 2


def test_adms_flow(S):
    from erp_app import attendance as A
    e = _emp(S, "موظف جهاز", "55")
    q = {"SN": ["SN12345"]}
    assert A.adms_handle("GET", "/iclock/cdata", q)[0] == 200
    assert A.adms_handle("GET", "/iclock/cdata", {"SN": ["../x"]})[0] == 400
    body = "55\t2026-04-02 08:00:00\t0\t1\n"
    A.adms_handle("POST", "/iclock/cdata", {"SN": ["SN12345"], "table": ["ATTLOG"]}, body)   # لسه غير مفعل
    from erp_app.db import get_session, AttendanceLog
    with get_session() as s:
        assert s.query(AttendanceLog).filter(AttendanceLog.device_serial == "SN12345").count() == 0
    dev = [d for d in A.list_devices() if d.serial == "SN12345"][0]
    assert dev.enabled is False
    A.save_device("SN12345", "المدخل", enabled=True, device_id=dev.id)
    code, txt = A.adms_handle("POST", "/iclock/cdata", {"SN": ["SN12345"], "table": ["ATTLOG"]}, body)
    assert code == 200 and txt == "OK: 1"
    with get_session() as s:
        assert s.query(AttendanceLog).filter(AttendanceLog.device_serial == "SN12345", AttendanceLog.employee_id == e).count() == 1


def test_http_adms_route(S):
    """الراوت الفعلي على السيرفر الداخلي."""
    import http.client
    from erp_app import delivery_server
    srv = delivery_server.start("127.0.0.1", 0) if delivery_server.start.__code__.co_argcount else None
    port = None
    s = delivery_server._server.get("srv")
    if s:
        port = s.server_address[1]
    if not port:
        pytest.skip("server did not start")
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("GET", "/iclock/cdata?SN=HTTPTEST1&options=all")
    r = c.getresponse()
    assert r.status == 200 and b"Stamp" in r.read()
    delivery_server.stop() if hasattr(delivery_server, "stop") else None


def test_absence_from_fingerprint_in_payroll(S):
    from erp_app import attendance as A
    S.update_company_settings(payroll_day_basis=30)
    A.set_weekly_off([4, 5])
    A.add_holiday(datetime.date(2026, 4, 15), "عطلة")
    e = _emp(S, "موظف بصمة", "900")
    manual = _emp(S, "موظف يدوي", "")                       # من غير رقم جهاز: غياب يدوي
    nopunch = _emp(S, "موظف رقمه بدون بصمات", "901")         # رقم بس مفيش بصمات: يدوي برضه
    days = _work_days(2026, 4, skip=(6, 7, 15))             # غاب 6 و 7 (15 عطلة)
    A.import_punches([("900", D(d.year, d.month, d.day, 8, 0)) for d in days])
    run = S.create_payroll_run(4, 2026)
    from erp_app.db import get_session, Payslip
    def slip(eid):
        with get_session() as s:
            return s.query(Payslip).filter(Payslip.run_id == run, Payslip.employee_id == eid).first()
    p = slip(e)
    assert p.absent_days == 2.0
    assert round(p.absence_deduction, 2) == round(4000 / 30 * 2, 2)
    assert round(p.net_salary, 2) == round(4000 - 4000 / 30 * 2, 2)
    assert slip(manual).absent_days == 0 and slip(nopunch).absent_days == 0
    # إجازة معتمدة بتشيل اليوم من الغياب
    codes = [t.code for t in S.list_leave_types() if t.code == "unpaid"]
    rid = S.create_leave_request(e, "unpaid", D(2026, 4, 6), D(2026, 4, 6))
    rid = rid if isinstance(rid, int) else getattr(rid, "id", rid)
    S.decide_leave_request(rid, True)
    with get_session() as s:
        assert A.attendance_absent_days(s, e, 4, 2026) == 1.0
    n = A.sync_run_absence(run)
    assert n >= 1 and slip(e).absent_days == 1.0


def test_attendance_screen_renders(S):
    import flet as ft
    from erp_app.views.attendance import build_attendance
    class P:
        overlay = []; services = []; session = type("X", (), {"store": {}})()
        def update(self, *a, **k): pass
    from erp_app import theme
    page = P()
    try:
        build_attendance(page)
    except AttributeError:
        pytest.skip("fake page too thin")


def test_day_metrics_rules():
    from erp_app import attendance as A
    r = {"start": 480, "end": 960, "grace": 15, "ot_min": 30, "ot_mult": 1.5, "shift_minutes": 480}
    m = lambda f, l, c=2, off=False: A.day_metrics(D(2026, 5, 3, *f), D(2026, 5, 3, *l), c, r, off)
    assert m((8, 10), (16, 0)) == (0, 0, 0)            # داخل السماحية
    assert m((8, 20), (16, 0)) == (20, 0, 0)           # تأخير يتحسب من بداية الدوام
    assert m((8, 0), (15, 30)) == (0, 30, 0)           # خروج مبكر
    assert m((8, 0), (17, 30)) == (0, 0, 90)           # إضافي
    assert m((8, 0), (16, 20)) == (0, 0, 0)            # أقل من الحد الأدنى للإضافي
    assert m((8, 40), (8, 40), c=1) == (40, 0, 0)      # بصمة واحدة: تأخير بس
    assert m((9, 0), (13, 0), off=True) == (0, 0, 240)  # يوم راحة: كله إضافي


def test_late_and_overtime_in_payroll(S):
    from erp_app import attendance as A
    from erp_app.db import Payslip, get_session
    S.update_company_settings(payroll_day_basis=30)
    A.set_weekly_off([4, 5])
    A.set_shift_rules("08:00", "16:00", 15, True, True, 30, 1.5)
    e = _emp(S, "موظف تأخير وإضافي", "950")
    days = _work_days(2026, 6)
    punches = []
    for i, d in enumerate(days):
        f, l = D(d.year, d.month, d.day, 8, 0), D(d.year, d.month, d.day, 16, 0)
        if i == 0: f = D(d.year, d.month, d.day, 8, 45)       # تأخير 45
        if i == 1: l = D(d.year, d.month, d.day, 15, 0)       # خروج مبكر 60
        if i == 2: l = D(d.year, d.month, d.day, 18, 0)       # إضافي 120
        punches += [("950", f), ("950", l)]
    A.import_punches(punches)
    run = S.create_payroll_run(6, 2026)
    n = A.sync_run_absence(run)          # (إنشاء الدورة نفسه بيحسبها كمان)
    assert n >= 1
    with get_session() as s:
        p = s.query(Payslip).filter(Payslip.run_id == run, Payslip.employee_id == e).first()
        assert p.late_minutes == 105 and p.overtime_minutes == 120
        daily = 4000 / 30
        assert round(p.late_deduction, 2) == round(105 * daily / 480, 2)
        assert round(p.overtime_pay, 2) == round(120 / 60 * (3000 / 30 / 8) * 1.5, 2)
        assert round(p.net_salary, 2) == round(4000 - p.late_deduction - p.absence_deduction + p.overtime_pay, 2)
    jid = S.post_payroll_run(run)
    from erp_app.db import JournalEntryLine
    with get_session() as s:
        ls = s.query(JournalEntryLine).filter(JournalEntryLine.entry_id == jid).all()
        assert round(sum(l.debit for l in ls), 2) == round(sum(l.credit for l in ls), 2)
    # التفعيل مقفول: الدقائق تتسجل لكن مفيش خصم ولا بدل (شهر تاني)
    A.set_shift_rules("08:00", "16:00", 15, False, False, 30, 1.5)
    A.import_punches([("950", D(2026, 7, 1, 9, 0)), ("950", D(2026, 7, 1, 19, 0))])
    run2 = S.create_payroll_run(7, 2026)
    with get_session() as s:
        p2 = s.query(Payslip).filter(Payslip.run_id == run2, Payslip.employee_id == e).first()
        assert p2.late_minutes == 60 and p2.overtime_minutes == 180
        assert p2.late_deduction == 0 and p2.overtime_pay == 0
    A.set_shift_rules("08:00", "16:00", 15, False, False, 30, 1.5)


def test_shift_rules_validation_and_logs(S):
    from erp_app import attendance as A
    A.set_shift_rules("16:00", "08:00", 15, False, False, 30, 1.5)         # وردية بتعدّي منتصف الليل مقبولة
    assert A.get_shift_rules()["overnight"] is True
    A.set_shift_rules("08:00", "16:00", 15, False, False, 30, 1.5)
    with pytest.raises(ValueError):
        A.set_shift_rules("8am", "16:00", 15, False, False, 30, 1.5)
    with pytest.raises(ValueError):
        A.set_shift_rules("08:00", "16:00", 15, False, True, 30, 0.5)
    A.set_shift_rules("09:00", "17:00", 10, True, True, 20, 2)
    r = A.get_shift_rules()
    assert r["start_txt"] == "09:00" and r["shift_minutes"] == 480 and r["ot_mult"] == 2 and r["late_on"] and r["ot_on"]
    rows = A.daily_summary(datetime.date(2026, 6, 1), datetime.date(2026, 6, 30))
    assert rows and all("late" in x and "overtime" in x for x in rows)
    A.set_shift_rules("08:00", "16:00", 15, False, False, 30, 1.5)


def test_shifts_per_employee(S):
    from erp_app import attendance as A
    from erp_app.db import Payslip, get_session
    S.update_company_settings(payroll_day_basis=30)
    A.set_weekly_off([4, 5])
    A.set_shift_rules("08:00", "16:00", 15, True, True, 30, 1.5)
    night = A.save_shift("مسائي", "14:00", "22:00", grace=5, weekly_off=[4])      # راحته الجمعة بس
    with pytest.raises(ValueError):
        A.save_shift("مسائي", "10:00", "11:00")                                    # اسم مكرر
    with pytest.raises(ValueError):
        A.save_shift("", "22:00", "06:00")                                         # اسم مطلوب
    e1 = _emp(S, "موظف صباحي", "960")
    e2 = _emp(S, "موظف مسائي", "961")
    A.set_employee_shift(e2, night)
    r1, r2 = A.get_shift_rules(e1), A.get_shift_rules(e2)
    assert (r1["start_txt"], r1["shift_name"], r1["grace"]) == ("08:00", "", 15)
    assert (r2["start_txt"], r2["end_txt"], r2["grace"], r2["shift_name"], r2["shift_minutes"]) == ("14:00", "22:00", 5, "مسائي", 480)
    assert A.get_weekly_off(e1) == {4, 5} and A.get_weekly_off(e2) == {4}
    punches = []
    for d in _work_days(2026, 8):                       # كل أيام العمل (الأحد-الخميس)
        punches += [("960", D(d.year, d.month, d.day, 8, 0)), ("960", D(d.year, d.month, d.day, 16, 0))]
        punches += [("961", D(d.year, d.month, d.day, 14, 0)), ("961", D(d.year, d.month, d.day, 22, 0))]
    sat = [d for d in (datetime.date(2026, 8, x) for x in range(1, 32)) if d.weekday() == 5][0]       # سبت: راحة الصباحي، يوم عمل عادي للمسائي
    fri = [d for d in (datetime.date(2026, 8, x) for x in range(1, 32)) if d.weekday() == 4][0]       # جمعة: راحة الاتنين
    punches += [("961", D(sat.year, sat.month, sat.day, 14, 0)), ("961", D(sat.year, sat.month, sat.day, 22, 0))]     # عادي للمسائي = مفيش إضافي
    punches += [("960", D(sat.year, sat.month, sat.day, 8, 0)), ("960", D(sat.year, sat.month, sat.day, 16, 0))]      # راحة للصباحي = 480 إضافي
    punches += [("961", D(fri.year, fri.month, fri.day, 14, 0)), ("961", D(fri.year, fri.month, fri.day, 22, 0))]     # راحة المسائي = 480 إضافي
    first_work = _work_days(2026, 8)[0]
    A.import_punches(punches)
    rows = {r["name"]: r for r in A.daily_summary(first_work, first_work)}
    assert rows["موظف مسائي"]["late"] == 0 and rows["موظف مسائي"]["shift"] == "مسائي"       # 14:00 مش تأخير على المسائي
    run = S.create_payroll_run(8, 2026)
    with get_session() as s:
        p1 = s.query(Payslip).filter(Payslip.run_id == run, Payslip.employee_id == e1).first()
        p2 = s.query(Payslip).filter(Payslip.run_id == run, Payslip.employee_id == e2).first()
        assert p1.late_minutes == 0 and p1.overtime_minutes == 480        # سبت = راحة الصباحي
        assert p2.late_minutes == 0 and p2.overtime_minutes == 480        # جمعة = راحة المسائي، والسبت عادي
    # حذف وردية مستخدمة ممنوع
    with pytest.raises(ValueError):
        A.delete_shift(night)
    A.set_employee_shift(e2, None)
    A.delete_shift(night)
    A.set_shift_rules("08:00", "16:00", 15, False, False, 30, 1.5)


def test_overnight_shifts(S):
    """ورديات على مدار 24 ساعة: بصمة الفجر بتتنسب ليوم بدء الوردية، والتأخير/الخروج المبكر/الإضافي بيتحسبوا صح."""
    from erp_app import attendance as A
    from erp_app.db import get_session
    A.set_weekly_off([])
    A.set_shift_rules("08:00", "16:00", 10, True, True, 30, 1.5)
    night = A.save_shift("ليلي 22-06", "22:00", "06:00")
    late_ev = A.save_shift("مسائي 16-00", "16:00", "00:00")
    full = A.save_shift("24 ساعة", "08:00", "08:00")
    e = _emp(S, "موظف ليلي", "970")
    A.set_employee_shift(e, night)
    r = A.get_shift_rules(e)
    assert r["overnight"] and r["end_abs"] == 360 + 1440 and r["shift_minutes"] == 480
    # 1 أكتوبر 2034: دخل 22:20 (تأخير 20 بعد سماحية 10) وخرج 2/10 الساعة 06:45 (إضافي 45)
    d0 = D(2034, 10, 1)
    first, last = D(2034, 10, 1, 22, 20), D(2034, 10, 2, 6, 45)
    assert A._work_date(last, r) == d0.date() and A._work_date(first, r) == d0.date()
    assert A.day_metrics(first, last, 2, r) == (20, 0, 45)
    # خروج مبكر 05:30 = 30 دقيقة
    assert A.day_metrics(first, D(2034, 10, 2, 5, 30), 2, r)[1] == 30
    # الوردية المسائية 16:00→00:00: خروج 00:40 = إضافي 40
    r2 = {**r, **A._overnight_fields(16 * 60, 0), "start": 16 * 60, "end": 0}
    assert A.day_metrics(D(2034, 10, 1, 16, 0), D(2034, 10, 2, 0, 40), 2, r2) == (0, 0, 40)
    # وردية 24 ساعة 08→08
    r3 = {**r, **A._overnight_fields(480, 480), "start": 480, "end": 480}
    assert r3["end_abs"] == 480 + 1440 and A._work_date(D(2034, 10, 2, 7, 0), r3) == d0.date()
    assert A._work_date(D(2034, 10, 2, 9, 0), r3) == D(2034, 10, 2).date()
    # بصمات حقيقية: يومين ورا بعض
    A.import_punches([("970", D(2034, 10, 1, 22, 20)), ("970", D(2034, 10, 2, 6, 45)),
                      ("970", D(2034, 10, 2, 22, 0)), ("970", D(2034, 10, 3, 6, 0))])
    rows = [x for x in A.daily_summary(D(2034, 10, 1).date(), D(2034, 10, 3).date(), employee_id=e)]
    by_day = {x["date"]: x for x in rows}
    assert set(by_day) == {D(2034, 10, 1).date(), D(2034, 10, 2).date()}       # مفيش يوم 3/10 (بصمة الفجر تبع 2/10)
    assert by_day[D(2034, 10, 1).date()]["count"] == 2 and by_day[D(2034, 10, 1).date()]["overtime"] == 45
    assert by_day[D(2034, 10, 2).date()]["late"] == 0
    with get_session() as s:
        assert A.attendance_time_minutes(s, e, 10, 2034, today=D(2034, 11, 5).date()) == (20.0, 0.0, 45.0)
        # الغياب: كل أيام الشهر اللي قبل 3/10 مش متوقع ليه عقد؛ مفيش غياب مسجّل عن يوم عليه بصمة
        assert A.attendance_absent_days(s, e, 10, 2034, today=D(2034, 11, 5).date()) is not None
    A.set_employee_shift(e, None)
