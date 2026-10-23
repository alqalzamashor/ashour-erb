"""تقسيم الشريط الجانبي لقوائم فرعية: كل مفتاح في SECTIONS لازم يكون شاشة موجودة في نفس القسم، ومفيش شاشة تتكرر أو تختفي."""
import main


def test_sections_reference_real_screens_in_their_group():
    groups = {g[0]: [x[0] for x in g[3]] for g in main.GROUPS}
    for gk, secs in main.SECTIONS.items():
        assert gk in groups
        seen = []
        for title, icon, keys in secs:
            assert title and keys
            for k in keys:
                assert k in groups[gk], f"{k} مش في قسم {gk}"
            seen += keys
        assert len(seen) == len(set(seen)), f"شاشة متكررة في {gk}"


def test_group_sections_never_hides_a_screen_and_handles_permissions():
    for g in main.GROUPS:
        visible = list(g[3])
        secs = main.group_sections(g[0], visible)
        if secs is None:
            continue
        flat = [x[0] for _, _, items in secs for x in items]
        assert sorted(flat) == sorted(x[0] for x in visible)
        # مستخدم صلاحياته على شاشة واحدة بس: ما يبقاش فيه تقسيم فاضي
        one = main.group_sections(g[0], visible[:1])
        assert one is None


def test_every_screen_key_is_unique_across_groups():
    keys = [x[0] for g in main.GROUPS for x in g[3]]
    assert len(keys) == len(set(keys))


def test_landing_key_prefers_dashboard_then_first_allowed_then_none():
    assert main.landing_key(lambda k: True) == 'dashboard'
    assert main.landing_key(lambda k: k == 'pos') == 'pos'
    assert main.landing_key(lambda k: k in ('journal_entries', 'products')) == 'journal_entries'   # بترتيب القائمة (المحاسبة قبل المخزون)
    assert main.landing_key(lambda k: False) is None
