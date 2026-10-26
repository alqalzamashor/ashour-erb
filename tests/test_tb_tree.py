from erp_app import tb_tree


def _r(i, code, od=0, oc=0, pd=0, pc=0):
    return {'account_id': i, 'code': code, 'name': f'a{i}', 'opening_debit': od, 'opening_credit': oc, 'period_debit': pd, 'period_credit': pc}


ROWS = [_r(1, '1'), _r(2, '11'), _r(3, '111', od=100, pd=50, pc=20), _r(4, '112', pd=10), _r(5, '2', pc=40), _r(6, '21', oc=30, pc=10)]
PAR = {2: 1, 3: 2, 4: 2, 6: 5}


def test_parent_rolls_up_children_net():
    roots = tb_tree.build_tree(ROWS, PAR)
    assert [r['code'] for r in roots] == ['1', '2']
    a = roots[0]
    assert a['opening_debit'] == 100 and a['period_debit'] == 60 and a['period_credit'] == 20
    assert a['closing_debit'] == 140 and a['closing_credit'] == 0
    assert a['children'][0]['children'][0]['depth'] == 2


def test_totals_use_roots_only_and_balance_when_data_balances():
    roots = tb_tree.build_tree(ROWS, PAR)
    t = tb_tree.totals(roots)
    assert t['period_debit'] == 60 and t['period_credit'] == 70
    assert t['closing_debit'] == 60 and t['closing_credit'] == 0


def test_visibility_expand_search_and_hide_zero():
    roots = tb_tree.build_tree(ROWS, PAR)
    assert [n['code'] for n in tb_tree.visible_rows(roots, set())] == ['1', '2']
    assert [n['code'] for n in tb_tree.visible_rows(roots, {1, 2})] == ['1', '11', '111', '112', '2']
    assert [n['code'] for n in tb_tree.visible_rows(roots, set(), query='112')] == ['1', '11', '112']
    assert '-0.0' not in str(tb_tree.totals(roots).values())
