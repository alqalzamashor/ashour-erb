"""طبقة الترجمة: دوال الترجمة + تغطية الشاشات الفعلية بالإنجليزي + اتجاه/اختيار اللغة."""
import collections
import dataclasses
import json
import os
import re
from unittest.mock import MagicMock

import flet as ft
import pytest
from flet.controls.base_control import BaseControl
from flet.controls.context import _context_page

from erp_app import i18n
from erp_app import onboarding as ob

AR = re.compile("[؀-ۿ]")
_STR = ("value", "label", "hint_text", "helper_text", "tooltip", "text", "title", "subtitle", "content")


def test_tr_basics():
    assert i18n.tr("حفظ", "en") == "Save"
    assert i18n.tr("حفظ", "ar") == "حفظ"
    assert i18n.tr("  إلغاء ", "en") == "  Cancel "
    assert i18n.tr("الإجمالي:", "en") == "Total:"
    assert i18n.tr("الإجمالي: 1,250.00", "en") == "Total: 1,250.00"
    assert i18n.tr("جملة مالهاش ترجمة أبدًا xyz", "en") == "جملة مالهاش ترجمة أبدًا xyz"
    assert i18n.tr("Save", "en") == "Save"
    assert i18n.tr(None, "en") is None
    assert i18n.tr("العميل (اختياري)", "en") == "Customer (optional)"


def test_dictionary_sane():
    d = json.load(open(i18n._DATA, encoding="utf-8"))
    d.pop("__patterns__", None)
    assert len(d) > 1000
    # مفاتيح لازم تفضل فيها كلمة عربية لأن الكود بيفحصها حرفيًا
    keep = {"English / العربية", "اكتب  استرجاع  للتأكيد", 'اكتب كلمة "استرجاع" بالظبط'}
    assert not [k for k, v in d.items() if k not in keep and isinstance(v, str) and AR.search(v)], "ترجمة فيها حروف عربي"
    assert not [k for k in d if not AR.search(k)], "مفتاح من غير عربي"


def test_translate_control_and_dropdown_key(monkeypatch):
    pg = MagicMock(); pg._erp_lang = "en"
    tok = _context_page.set(pg)
    try:
        t = ft.Text("الاسم"); i18n.translate_control(t); assert t.value == "Name"
        tf = ft.TextField(label="الكمية", value="الاسم"); i18n.translate_control(tf)
        assert tf.label == "Quantity" and tf.value == "الاسم"          # القيمة ما بتتلمسش
        o = ft.DropdownOption(text="نقدي"); i18n.translate_control(o)
        assert o.text == "Cash" and o.key == "نقدي"                   # المفتاح الأصلي محفوظ
        pg._erp_lang = "ar"
        t2 = ft.Text("الاسم"); i18n.translate_control(t2); assert t2.value == "الاسم"
    finally:
        _context_page.reset(tok)


def test_user_lang_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "_prefs_path", lambda: str(tmp_path / "lp.json"))
    assert i18n.load_user_lang("sara") == "ar"
    i18n.save_user_lang("sara", "en")
    assert i18n.load_user_lang("sara") == "en" and i18n.load_user_lang("omar") == "ar"
    i18n.save_user_lang("sara", "xx")
    assert i18n.load_user_lang("sara") == "en"


def _walk(c, seen):
    if id(c) in seen or not isinstance(c, BaseControl):
        return
    seen.add(id(c))
    yield c
    for f in dataclasses.fields(c):
        if f.name.startswith("_"):
            continue
        try:
            v = getattr(c, f.name, None)
        except Exception:      # noqa: BLE001
            v = None
        for x in (v if isinstance(v, (list, tuple)) else [v]):
            if isinstance(x, BaseControl):
                yield from _walk(x, seen)


def test_english_coverage_on_real_screens(S, tmp_path, monkeypatch):
    import main as M
    monkeypatch.setattr(ob, "PATH", str(tmp_path / "ob.json"))
    from erp_app.db import SalesInvoice, get_session
    with get_session() as s:
        if s.query(SalesInvoice).count() == 0:
            ob.load_demo()
    user = {"id": 1, "username": "admin", "role": "admin", "full_name": "x", "permissions": "{}", "branch_ids": "[]", "cost_center_ids": "[]"}
    pg = MagicMock(); pg.overlay = []; pg._erp_compact = False; pg.width = 1200; pg.height = 800; pg._erp_lang = "en"
    tok = _context_page.set(pg)
    left, total = collections.Counter(), 0
    try:
        for _gk, _t, _i, items in M.GROUPS:
            for key, _l, _ic, builder in items:
                pg._erp_cards_used = False
                try:
                    root = builder(pg, user) if key in ("dashboard", "organization", "budgets") else builder(pg)
                except Exception:      # noqa: BLE001
                    continue
                for c in _walk(root, set()):
                    names = ("value",) if isinstance(c, ft.Text) else _STR[1:]
                    for f in names:
                        v = getattr(c, f, None)
                        if isinstance(v, str) and AR.search(v):
                            total += 1
                            if AR.search(i18n.tr(v, "en")):
                                left[v.strip()] += 1
    finally:
        _context_page.reset(tok)
    rest = sum(left.values())
    rep = os.environ.get("ERP_I18N_REPORT")
    if rep:
        with open(rep, "w", encoding="utf-8") as f:
            json.dump({"total": total, "left": rest, "top": left.most_common(400)}, f, ensure_ascii=False)
    assert total > 500
    assert rest / total < 0.40, f"الباقي بالعربي {rest} من {total}"


def test_bullet_separated_and_spaces():
    assert i18n.tr("F9 إتمام البيع  •  F8 تفريغ السلة", "en") == "F9 Complete sale • F8 Clear cart"
    assert i18n.tr("التزامات  متداولة", "en") == "Current liabilities"
    assert i18n.tr("فاتورة مبيعات S-000040", "en") == "Sales invoice S-000040"
    assert i18n.tr("صفحة 2 من 5", "en") == "Page 2 of 5"


def test_login_has_language_switch():
    src = open(os.path.join(os.path.dirname(__file__), "..", "erp_app", "views", "login.py"), encoding="utf-8").read()
    assert "switch_lang" in src and "_erp_lang" in src


def test_hr_leave_screen_strings_translated():
    for s in ["الإجازات", "طلب إجازة جديد", "كل طلبات الإجازات", "الاستقالة ونهاية الخدمة"]:
        out = i18n.tr(s, "en")
        assert not AR.search(out), (s, out)
