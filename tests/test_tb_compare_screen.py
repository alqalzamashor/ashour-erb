"""ميزان المراجعة (شجرة) مع المقارنة بالفترة السابقة: بيضيف عمودين ويشتغل من غير أخطاء."""
from unittest.mock import MagicMock

import flet as ft
from flet.controls.context import _context_page

from tests.test_drafts import _walk


def test_compare_adds_two_columns(S, monkeypatch):
    import datetime
    from erp_app import theme
    made = []
    orig = theme.DateRangeField.__init__
    monkeypatch.setattr(theme.DateRangeField, '__init__', lambda self, *a, **k: (orig(self, *a, **k), made.append(self))[0])
    from erp_app.views.trial_balance import build_trial_balance
    pg = MagicMock(); pg.overlay = []; _context_page.set(pg)
    root = build_trial_balance(pg)
    assert made
    ctls = list(_walk(root))
    tables = [c for c in ctls if isinstance(c, ft.DataTable)]
    base = 8
    sw = next(c for c in ctls if isinstance(c, ft.Switch) and 'مقارنة' in (c.label or ''))
    made[0].set_range(datetime.date(2026, 8, 1), datetime.date(2026, 8, 31))
    sw.value = True
    sw.on_change(MagicMock())
    wide = [t for t in tables if len(t.columns) == base + 2]
    assert wide, [len(t.columns) for t in tables]
    assert all(len(r.cells) == base + 2 for r in wide[0].rows)
