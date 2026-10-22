"""شجرة (الحساب > الموظفين > الحركات) وفلتر الموظف في التقارير المالية + وسم قيود الموظفين."""
import datetime
from unittest.mock import MagicMock

from flet.controls.context import _context_page

D = datetime.datetime


def _emp(S, name, **kw):
    a = [x.id for x in S.list_accounts(postable_only=True)]
    eid = S.create_employee(name, hire_date=D(2033, 1, 1))
    args = dict(housing_allowance=0, transport_allowance=0, other_allowances=0, gosi_rate_employee=0, gosi_rate_employer=0,
                leave_provision_rate=0, eos_provision_rate=0, basic_salary_account_id=a[2], gosi_deduction_account_id=a[1], other_deductions_account_id=a[1])
    args.update(kw)
    S.create_contract(eid, D(2033, 1, 1), 3000, **args)
    return eid, a


def _lines(S, jid):
    from erp_app.db import JournalEntryLine, get_session
    with get_session() as s:
        return [(l.account_id, l.debit, l.credit, l.partner_type, l.partner_id) for l in s.query(JournalEntryLine).filter(JournalEntryLine.entry_id == jid).all()]


def test_payroll_payment_and_tree(S):
    e1, a = _emp(S, "شجرة أ"); e2, _ = _emp(S, "شجرة ب")
    rid = S.create_payroll_run(1, 2033)
    jid = S.post_payroll_run(rid)
    ls = _lines(S, jid)
    assert all(l[3] == "employee" for l in ls)
    assert {l[4] for l in ls} == {e1, e2}
    assert round(sum(l[1] for l in ls), 2) == round(sum(l[2] for l in ls), 2)
    pm = S.create_payment_method("بنك شجرة", account_id=a[0])
    S.pay_payroll_run(rid, pm if isinstance(pm, int) else pm.id, payment_date=D(2033, 2, 1))

    roots = S.employee_account_tree(D(2033, 1, 1), D(2033, 12, 31))
    flat = []

    def walk(n):
        flat.append(n)
        for c in n["children"]:
            walk(c)
    for r in roots:
        walk(r)
    exp = [n for n in flat if n["id"] == a[2]][0]                  # حساب الراتب الأساسي
    assert {e["employee_id"] for e in exp["employees"]} == {e1, e2}
    assert exp["debit"] == 6000 and exp["balance"] == 6000
    mv = S.employee_account_movements(a[2], e1, D(2033, 1, 1), D(2033, 12, 31))
    assert len(mv) == 1 and mv[0]["debit"] == 3000 and mv[0]["balance"] == 3000
    only = S.employee_account_tree(D(2033, 1, 1), D(2033, 12, 31), employee_id=e1)
    assert all(e["employee_id"] == e1 for n in only for e in n["employees"])
    d = S.report_data(D(2033, 1, 1), D(2033, 12, 31), employee_id=e1)
    assert d["ledger"] and all(x["debit"] or x["credit"] for x in d["ledger"]) and len(d["ledger"]) < len(S.report_data(D(2033, 1, 1), D(2033, 12, 31))["ledger"])
    pay_mv = S.employee_account_movements(a[0], e2, D(2033, 1, 1), D(2033, 12, 31))   # الصرف من البنك
    assert pay_mv and pay_mv[0]["credit"] > 0


def test_backfill_old_entries(S):
    from erp_app.db import JournalEntryLine, get_session
    e1, a = _emp(S, "قديم أ"); e2, _ = _emp(S, "قديم ب")
    rid = S.create_payroll_run(3, 2033)
    jid = S.post_payroll_run(rid)
    before = {}
    for l in _lines(S, jid):
        before.setdefault(l[0], [0.0, 0.0]); before[l[0]][0] += l[1]; before[l[0]][1] += l[2]
    with get_session() as s:                       # نحاكي قيد قديم: سطر واحد لكل حساب من غير موظف
        for l in s.query(JournalEntryLine).filter(JournalEntryLine.entry_id == jid).all():
            s.delete(l)
        s.flush()
        for acc, (d, c) in before.items():
            s.add(JournalEntryLine(entry_id=jid, account_id=acc, debit=d, credit=c))
        s.commit()
    assert all(l[3] is None for l in _lines(S, jid))
    assert S.retag_employee_entries() >= 1
    after = _lines(S, jid)
    assert all(l[3] == "employee" for l in after) and {e1, e2} <= {l[4] for l in after}
    sums = {}
    for l in after:
        sums.setdefault(l[0], [0.0, 0.0]); sums[l[0]][0] += l[1]; sums[l[0]][1] += l[2]
    assert {k: [round(x, 2) for x in v] for k, v in sums.items()} == {k: [round(x, 2) for x in v] for k, v in before.items()}
    assert S.retag_employee_entries() == 0         # تاني مرة مفيش حاجة


def test_allowance_run_tagged(S):
    a = [x.id for x in S.list_accounts(postable_only=True)]
    eid, _ = _emp(S, "مخصصات موسوم", gosi_rate_employer=10, leave_provision_rate=5, eos_provision_rate=5,
                  gosi_employer_expense_account_id=a[3], gosi_employer_payable_account_id=a[4],
                  leave_provision_expense_account_id=a[5], leave_provision_payable_account_id=a[6],
                  eos_provision_expense_account_id=a[7], eos_provision_payable_account_id=a[8])
    rid = S.create_allowance_insurance_run(6, 2033)
    jid = S.post_allowance_insurance_run(rid)
    ls = _lines(S, jid)
    assert ls and all(l[3] == "employee" for l in ls) and eid in {l[4] for l in ls}


def test_screen_builds_and_expands(S):
    import flet as ft
    from erp_app.views.reports import build_reports
    from tests.test_drafts import _walk
    pg = MagicMock(); pg.overlay = []; _context_page.set(pg)
    root = build_reports(pg)
    refresh = [c for c in _walk(root) if isinstance(c, ft.ElevatedButton) and c.content == "تحديث التقرير" or getattr(c, "text", None) == "تحديث التقرير"]
    assert refresh
    refresh[0].on_click(None)
    from erp_app.views.employee_account_tree import build_employee_tree
    roots = S.employee_account_tree(D(2033, 1, 1), D(2033, 12, 31))
    tree = build_employee_tree(pg, roots, lambda aid, eid: S.employee_account_movements(aid, eid, D(2033, 1, 1), D(2033, 12, 31)))
    from tests.test_view_controls import _bad
    assert _bad(tree) == []
    clickable = [c for c in _walk(tree) if isinstance(c, ft.Container) and c.on_click]
    assert clickable
    for c in clickable:               # فتح كل الحسابات ثم كل الموظفين (بيحمّل الحركات)
        c.on_click(None)
    for c in [c for c in _walk(tree) if isinstance(c, ft.Container) and c.on_click]:
        c.on_click(None)
    assert any(isinstance(x, ft.DataTable) for x in _walk(tree))


def _jbuild(builder, *a):
    pg = MagicMock(); pg.overlay = []
    _context_page.set(pg)
    return pg, builder(pg, *a)


def test_manual_journal_employee_field(S):
    """عمود "الموظف" في شاشة القيود: يتسجّل على السطر (partner employee) ويظهر في شجرة الحسابات، وطرفين على نفس السطر ممنوع."""
    import flet as ft
    from erp_app import drafts
    from erp_app.views.journal_entries import build_journal_entries
    from tests.test_drafts import _walk
    eid = S.create_employee("موظف قيد يدوي", hire_date=D(2034, 1, 1))
    acc = [a for a in S.list_accounts(postable_only=True)][:2]

    def run(partner="", employee=""):
        drafts.save("journal_entry", {"date": "2034-02-01", "ref": "EMP-J", "desc": "قيد بموظف", "branch": "", "center": "",
                                      "lines": [{"account": str(acc[0].id), "description": "", "partner": partner, "employee": employee, "debit": "250", "credit": "0", "branch": "", "center": ""},
                                                {"account": str(acc[1].id), "description": "", "partner": "", "employee": "", "debit": "0", "credit": "250", "branch": "", "center": ""}]})
        pg, root = _jbuild(build_journal_entries)
        # حقل الموظف بقى في نافذة "تفاصيل السطر" (مش عمود في الجدول) - القيمة بتتحمّل من المسودة وبتترحّل (بنتأكد تحت)
        btn = next(c for c in _walk(root) if isinstance(c, ft.FilledButton) and (getattr(c, "text", None) == "ترحيل القيد" or getattr(c, "content", None) == "ترحيل القيد"))
        btn.on_click(None)
        return pg

    pg = run(employee=str(eid))
    mv = S.employee_account_movements(acc[0].id, eid, D(2034, 1, 1), D(2034, 12, 31))
    assert len(mv) == 1 and mv[0]["debit"] == 250
    n_before = len(S.employee_account_movements(acc[0].id, eid, D(2034, 1, 1), D(2034, 12, 31)))
    run(partner=f"customer:1", employee=str(eid))          # طرفين: مرفوض
    assert len(S.employee_account_movements(acc[0].id, eid, D(2034, 1, 1), D(2034, 12, 31))) == n_before
    drafts.clear("journal_entry")


def test_tree_account_filter(S):
    """اختيار حساب في التقرير يعرض هذا الحساب (وأبناءه) فقط، مش كل الحسابات."""
    e1, a = _emp(S, "فلتر حساب")
    rid = S.create_payroll_run(9, 2036)
    S.post_payroll_run(rid)
    D0, D1 = None, None

    def ids(roots):
        out = []

        def w(n):
            out.append(n["id"])
            for c in n["children"]:
                w(c)
        for r in roots:
            w(r)
        return out
    allids = ids(S.employee_account_tree(D0, D1))
    assert len(allids) >= 2
    target = next(i for i in allids if any(e for e in _find(S.employee_account_tree(D0, D1), i)["employees"]))
    one = S.employee_account_tree(D0, D1, account_id=target)
    assert len(one) == 1 and one[0]["id"] == target
    assert set(ids(one)) < set(allids)
    assert S.employee_account_tree(D0, D1, account_id=a[-1] + 10**6) == []


def _find(roots, aid):
    for r in roots:
        if r["id"] == aid:
            return r
        f = _find(r["children"], aid)
        if f:
            return f
