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
