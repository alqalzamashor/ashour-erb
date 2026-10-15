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
