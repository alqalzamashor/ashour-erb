from ._partners import build_partner_view


def build_suppliers(page):
    return build_partner_view(page, "supplier")
