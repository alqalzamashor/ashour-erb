import flet as ft
from erp_app import theme  # noqa: F401  (يفعّل الـshim)


def test_dropdown_on_change_routes_to_on_select():
    d = ft.Dropdown(options=[ft.dropdown.Option('a', 'A')])
    fn = lambda e: None
    d.on_change = fn
    assert d.on_select is fn and d.on_change is fn
