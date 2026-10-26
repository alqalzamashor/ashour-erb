import datetime
from unittest.mock import MagicMock

import flet as ft
from flet.controls.context import _context_page

from erp_app import report_viewer as RV
from erp_app.report_engine import Col, DATE, MONEY

D = datetime.date
COLS = [Col('date', 'التاريخ', DATE), Col('acc', 'الحساب'), Col('debit', 'مدين', MONEY, 'sum'), Col('credit', 'دائن', MONEY, 'sum'), Col('bal', 'الرصيد', MONEY, 'last')]
ROWS = [{'date': D(2026, 1, 5), 'acc': 'الصندوق', 'debit': 100.0, 'credit': 0.0, 'bal': 100.0},
        {'date': D(2026, 1, 20), 'acc': 'البنك', 'debit': 50.0, 'credit': 0.0, 'bal': 150.0},
        {'date': D(2026, 2, 3), 'acc': 'الصندوق', 'debit': 0.0, 'credit': 30.0, 'bal': 120.0}]


def _viewer(rid='t1', **k):
    pg = MagicMock(); pg.overlay = []; _context_page.set(pg)
    v = RV.ReportViewer(pg, rid, 'اختبار', COLS, **k)
    v.set_rows(ROWS)
    return v


def test_detail_then_group_modes(S, tmp_path, monkeypatch):
    monkeypatch.setattr(RV, '_prefs_path', lambda: str(tmp_path / 'p.json'))
    v = _viewer()
    assert len(v.table.rows) == 3 and len(v.table.columns) == 5
    v.mode_dd.value = 'by:acc'; v._on_mode()
    assert len(v.table.rows) == 2                      # مجموعتان مقفولتان
    v._set_all(True)
    assert len(v.table.rows) == 5                      # 2 مجموعات + 3 صفوف
    assert any('الإجمالي' in str(getattr(c, 'controls', [None])[0].value) for c in [v.totals] if c.controls)


def test_levels_filter_sort_columns_and_chart(S, tmp_path, monkeypatch):
    monkeypatch.setattr(RV, '_prefs_path', lambda: str(tmp_path / 'p.json'))
    v = _viewer('t2')
    v.level_dds[0].value = 'date:month'; v.level_dds[1].value = 'acc'; v._on_level(0)
    assert v.mode_key == 'custom' and v.state.group_keys == ['date:month', 'acc']
    v.state.filters = {'acc': 'صندوق'}; v._refresh_ui()
    assert v._res['count'] == 2 and v.chips.visible
    v._sort('debit'); v._sort('debit')
    assert v.state.sort_key == 'debit' and v.state.asc is False
    v.show_chart = True; v._refresh_ui()
    assert v.chart_box.visible and v.chart_box.content is not None
    v.state.visible = ['acc', 'debit']; v._refresh_ui()
    assert len(v.table.columns) == 2


def test_prefs_roundtrip_and_reset(S, tmp_path, monkeypatch):
    monkeypatch.setattr(RV, '_prefs_path', lambda: str(tmp_path / 'p.json'))
    v = _viewer('t3')
    v.state.visible = ['acc', 'debit']; v.mode_dd.value = 'by:acc'; v._on_mode()
    v2 = _viewer('t3')
    assert v2.state.visible[:2] == ['acc', 'debit'] and v2.mode_key == 'by:acc' and v2.state.group_keys == ['acc']
    v2._reset()
    assert v2.mode_key == 'detail' and len(v2.table.columns) == 5


def test_export_uses_current_view(S, tmp_path, monkeypatch):
    monkeypatch.setattr(RV, '_prefs_path', lambda: str(tmp_path / 'p.json'))
    from erp_app.report_export import export_excel, export_pdf
    v = _viewer('t4')
    v.state.group_keys = ['acc']; v.state.visible = ['acc', 'debit']
    data = dict(v.view_table(), title='تقرير اختبار')
    assert data['table'][0] == ['الحساب', 'مدين']
    for f in (export_excel, export_pdf):
        assert f(data, 'report_view', str(tmp_path)).endswith(('.xlsx', '.pdf'))


def test_row_click_and_kpis(S, tmp_path, monkeypatch):
    monkeypatch.setattr(RV, '_prefs_path', lambda: str(tmp_path / 'p.json'))
    got = []
    v = _viewer('t5', on_row_click=lambda r: got.append(r['acc']))
    v.table.rows[0].cells[0].on_tap(None)
    assert got == ['الصندوق']
    assert v.kpi_row.visible and len(v.kpi_row.controls) >= 2
