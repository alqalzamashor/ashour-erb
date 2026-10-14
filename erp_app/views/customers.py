from ._partners import build_partner_view


def build_customers(page):
    return build_partner_view(page, "customer")
