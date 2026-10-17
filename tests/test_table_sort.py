"""أي ft.DataTable عادي بيتفرز بالضغط على عنوان العمود (أرقام بفواصل، تواريخ، نصوص، فاضي في الآخر)."""
from unittest.mock import MagicMock

import flet as ft

from erp_app import theme


def _table(values):
    rows = [ft.DataRow(cells=[ft.DataCell(ft.Text("x")), ft.DataCell(ft.Text(v))]) for v in values]
    t = ft.DataTable(columns=[ft.DataColumn(ft.Text("الاسم")), ft.DataColumn(ft.Text("القيمة")), ], rows=rows)
    return t


def _vals(t):
    return [r.cells[1].content.value for r in t.rows]


def test_numeric_sort_both_directions():
    t = _table(["1,200.00", "35.50", "", "900.00"])          # من غير صفحة: التحديث بيتجاهل الخطأ والترتيب بيتغير
    t.columns[1].on_sort(None)
    assert _vals(t) == ["35.50", "900.00", "1,200.00", ""]
    t.columns[1].on_sort(None)
    assert _vals(t) == ["", "1,200.00", "900.00", "35.50"] or _vals(t)[:3] == ["1,200.00", "900.00", "35.50"]
    assert t.sort_column_index == 1 and t.sort_ascending is False


def test_dates_and_text_keys():
    k = theme._sort_key_value
    assert k("2026-01-31") < k("31/03/2026") < k("2027-01-01")
    assert k("9.5") < k("10")
    assert k("abc") > k("5") and k("") > k("zzz")


def test_sortable_table_untouched_and_empty_label_not_sortable():
    st = theme.SortableDataTable(columns=[("a", lambda r: r)], row_builder=lambda r: ft.DataRow(cells=[ft.DataCell(ft.Text(str(r)))]))
    assert st.control.columns[0].on_sort is not None
    t = ft.DataTable(columns=[ft.DataColumn(ft.Text("")), ft.DataColumn(ft.Text("ع"))], rows=[])
    assert t.columns[0].on_sort is None and t.columns[1].on_sort is not None
