"""اليومية العامة بوضع العارض المتقدم + العروض المحفوظة باسم في العارض."""
from unittest.mock import MagicMock

import flet as ft
from flet.controls.context import _context_page

from erp_app import report_viewer as RV
from tests.test_drafts import _walk
from tests.test_report_viewer import _viewer


def test_journal_adv_mode_builds_viewer(S):
    from erp_app.views.general_journal import build_general_journal
    pg = MagicMock(); pg.overlay = []; _context_page.set(pg)
    root = build_general_journal(pg)
    dd = next(c for c in _walk(root) if isinstance(c, ft.Dropdown) and c.label == 'طريقة العرض' and any(o.key == 'adv' for o in c.options))
    assert dd.value == 'adv'            # الافتراضي الآن: التجميع الحر زي أودو
    dd.value = 'adv'; dd.on_select(MagicMock())
    tables = [c for c in _walk(root) if isinstance(c, ft.DataTable) and len(c.columns) == 10]
    assert tables, 'جدول العارض المتقدم (10 أعمدة) مش ظاهر'


def test_saved_views_roundtrip(S, tmp_path, monkeypatch):
    monkeypatch.setattr(RV, '_prefs_path', lambda: str(tmp_path / 'p.json'))
    v = _viewer('tv1')
    v.level_dds[0].value = 'acc'; v._on_level(0)
    v.state.filters = {'acc': 'صندوق'}; v._sort('debit')
    assert v.save_view('عرضي') and not v.save_view('  ')
    v._reset()
    assert v.state.group_keys == [] and not v.state.filters
    v.apply_snapshot(v.saved_views['عرضي'])
    assert v.state.group_keys == ['acc'] and v.state.filters == {'acc': 'صندوق'} and v.state.sort_key == 'debit'
    v2 = _viewer('tv1')                       # بيتحمّل من التفضيلات المحفوظة
    assert 'عرضي' in v2.saved_views
    v2.delete_view('عرضي')
    assert 'عرضي' not in _viewer('tv1').saved_views
