"""البحث بالإنجليزي في وضع English: الشاشة بتعرض الإنجليزي فلازم البحث يلقي بالعربي (المخزّن) وبالإنجليزي (المعروض)."""
from erp_app import i18n, theme


def test_matches_arabic_and_english():
    name = "مبانى وانشاءات"            # اسم حساب جاهز زي ما هو متخزّن
    assert i18n.matches("مباني".replace("ي", "ى"), name)
    assert i18n.matches("buildings", name) and i18n.matches("BUILD", name)
    assert not i18n.matches("zzz", name)
    assert i18n.matches("", name) and i18n.matches("  ", name)
    assert i18n.matches("111001", "111001 - " + name)


def test_search_hay_cached_and_plain_text():
    assert i18n.search_hay("Hello") == "hello"            # نص مفيهوش عربي: زي ما هو
    assert "buildings" in i18n.search_hay("111001 - مبانى وانشاءات")


def test_picker_filters_by_english(S):
    opts = [(str(a.id), f"{a.code} - {a.name}") for a in S.list_accounts(postable_only=True)]
    hits = [t for k, t in opts if "buildings" in i18n.search_hay(t)]
    assert hits, 'البحث بـ buildings لازم يلاقي حساب'
