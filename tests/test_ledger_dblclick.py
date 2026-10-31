import datetime
from unittest.mock import MagicMock
import flet as ft
from flet.controls.context import _context_page
from erp_app import services
from erp_app.views.ledger import build_ledger


def _walk(c):
    yield c
    for a in ('controls', 'content', 'actions', 'rows', 'cells'):
        v = getattr(c, a, None)
        for ch in (v if isinstance(v, list) else ([v] if v is not None else [])):
            if hasattr(ch, '__dict__'):
                yield from _walk(ch)


def test_ledger_double_tap_opens_entry(S):
    page = MagicMock(); page.overlay = []; _context_page.set(page); page._erp_ledger_preset = None
    accs = services.list_accounts(postable_only=True)
    services.create_journal_entry([{'account_id': accs[0].id, 'debit': 10, 'credit': 0}, {'account_id': accs[1].id, 'debit': 0, 'credit': 10}], reference='dbl')
    root = build_ledger(page)
    cells = [c for c in _walk(root) if isinstance(c, ft.GestureDetector) and getattr(c, 'on_double_tap', None) and c.mouse_cursor == ft.MouseCursor.CLICK]
    assert cells, 'no double-tap cells'
    before = len(page.overlay)
    cells[0].on_double_tap(None)
    assert len(page.overlay) > before


def test_ledger_has_branch_cc_party_columns(S):
    page = MagicMock(); page.overlay = []; _context_page.set(page); page._erp_ledger_preset = None
    root = build_ledger(page)
    labels = {t2.value for t in _walk(root) if isinstance(t, ft.Stack) for t2 in _walk(t) if isinstance(t2, ft.Text)}
    assert {'الفرع', 'مركز التكلفة', 'الطرف'} <= labels


def test_ledger_group_balance_is_net(S):
    from erp_app import report_engine as RE
    rows = [{'g': 'a', 'debit': 2000, 'credit': 0, 'balance': 2000}, {'g': 'a', 'debit': 0, 'credit': 100, 'balance': 1900}, {'g': 'a', 'debit': 0, 'credit': 100, 'balance': 1800}]
    cols = [RE.Col('debit', 'مدين', RE.MONEY, 'sum'), RE.Col('credit', 'دائن', RE.MONEY, 'sum'), RE.Col('balance', 'الرصيد', RE.MONEY, 'net:debit:credit')]
    agg = RE.aggregate(rows[::-1], cols)           # ترتيب الصفوف مش مهم (كان 'last' بيطلع غلط)
    assert agg['balance'] == 1800 and agg['debit'] == 2000 and agg['credit'] == 200


def test_viewer_column_resize_and_persist(S, tmp_path, monkeypatch):
    from erp_app import report_viewer as RV
    from tests.test_report_viewer import _viewer
    monkeypatch.setattr(RV, '_prefs_path', lambda: str(tmp_path / 'p.json'))
    v = _viewer('rs1')
    c = v.cols[0]
    hdr = v.table.columns[0].label                    # Row[label, handle]
    handle = hdr.controls[1]
    ev = MagicMock(); ev.primary_delta = -80.0; handle.on_horizontal_drag_update(ev); handle.on_horizontal_drag_end(MagicMock())
    assert v.col_w[c.key] > 150                      # RTL: سحب لليسار = توسيع
    assert _viewer('rs1').col_w.get(c.key) == v.col_w[c.key]      # محفوظ
    v.table.columns[0].label.controls[1].on_double_tap(MagicMock())
    assert c.key not in v.col_w


def test_ledger_filters_branch_cc_party(S):
    allr = services.account_ledger()['rows']
    br = next((r['branch_id'] for r in allr if r['branch_id']), None)
    if br is None:
        accs = services.list_accounts(postable_only=True)
        b = services.list_branches(False)[0]
        services.create_journal_entry([{'account_id': accs[0].id, 'debit': 5, 'credit': 0, 'branch_id': b.id}, {'account_id': accs[1].id, 'debit': 0, 'credit': 5, 'branch_id': b.id}], reference='brf')
        allr = services.account_ledger()['rows']
        br = b.id
    sub = services.account_ledger(branch_id=br)['rows']
    assert sub and len(sub) <= len(allr) and all(r['branch_id'] == br for r in sub)
    none = services.account_ledger(branch_id=999999)['rows']
    assert none == []
    p = next((r for r in allr if r['partner_id']), None)
    if p:
        ps = services.account_ledger(partner_type=p['partner_type'], partner_id=p['partner_id'])['rows']
        assert ps and all(r['partner_id'] == p['partner_id'] for r in ps)
    cc = next((r['cost_center_id'] for r in allr if r['cost_center_id']), None)
    if cc:
        assert all(r['cost_center_id'] == cc for r in services.account_ledger(cost_center_id=cc)['rows'])



def test_ledger_party_running_balance(S):
    accs = services.list_accounts(postable_only=True)
    a, b = accs[0].id, accs[1].id
    L = lambda aid, d, c, pid: {'account_id': aid, 'debit': d, 'credit': c, 'partner_type': 'employee', 'partner_id': pid}
    services.create_journal_entry([L(a, 100, 0, 9001), L(b, 0, 100, 9001)], reference='pb1')
    services.create_journal_entry([L(a, 50, 0, 9002), L(b, 0, 50, 9002)], reference='pb2')
    services.create_journal_entry([L(a, 0, 30, 9001), L(b, 30, 0, 9001)], reference='pb3')
    rows = [r for r in services.account_ledger(a)['rows'] if r['partner_id'] in (9001, 9002)]
    p1 = [r['party_balance'] for r in rows if r['partner_id'] == 9001]
    p2 = [r['party_balance'] for r in rows if r['partner_id'] == 9002]
    assert p1 == [100.0, 70.0]          # رصيد كل طرف لوحده مش الرصيد الجاري للحساب كله
    assert p2 == [50.0]


def test_running_balance_per_group(S, tmp_path, monkeypatch):
    from erp_app import report_viewer as RV
    from erp_app.report_engine import Col, MONEY
    monkeypatch.setattr(RV, '_prefs_path', lambda: str(tmp_path / 'p.json'))
    pg = MagicMock(); pg.overlay = []; _context_page.set(pg)
    cols = [Col('acc', 'الحساب'), Col('party', 'الطرف'), Col('debit', 'مدين', MONEY, 'sum'), Col('credit', 'دائن', MONEY, 'sum'),
            Col('balance', 'الرصيد', MONEY, 'net:debit:credit', running=('debit', 'credit'))]
    rows = [{'acc': 'A', 'party': 'x', 'debit': 100.0, 'credit': 0.0, 'balance': 100.0},
            {'acc': 'A', 'party': 'y', 'debit': 50.0, 'credit': 0.0, 'balance': 150.0},
            {'acc': 'A', 'party': 'x', 'debit': 0.0, 'credit': 30.0, 'balance': 120.0}]
    v = RV.ReportViewer(pg, 'rb1', 't', cols)
    v.set_rows(rows)
    v.level_dds[0].value = 'acc'; v._on_level(0)
    v.level_dds[1].value = 'party'; v._on_level(1)
    leaves = [n for top in v._res['nodes'] for n in top.children]
    got = {n.label: [r['balance'] for r in n.rows] for n in leaves}
    assert got == {'x': [100.0, 70.0], 'y': [50.0]}
    assert {n.label: n.agg['balance'] for n in leaves} == {'x': 70.0, 'y': 50.0}
    v.level_dds[1].value = ''; v._on_level(1)
    v.level_dds[0].value = ''; v._on_level(0)
    assert [r['balance'] for r in v._res['rows']] == [100.0, 150.0, 120.0]      # من غير تجميع: الرصيد الأصلي
