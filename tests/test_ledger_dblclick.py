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
    cells = [c for c in _walk(root) if isinstance(c, ft.DataCell) and getattr(c, 'on_double_tap', None)]
    assert cells, 'no double-tap cells'
    before = len(page.overlay)
    cells[0].on_double_tap(None)
    assert len(page.overlay) > before


def test_ledger_has_branch_cc_party_columns(S):
    page = MagicMock(); page.overlay = []; _context_page.set(page); page._erp_ledger_preset = None
    root = build_ledger(page)
    labels = {t2.value for t in _walk(root) if isinstance(t, ft.DataTable) for c in t.columns for t2 in _walk(c.label) if isinstance(t2, ft.Text)}
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

