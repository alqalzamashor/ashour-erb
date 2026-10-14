from ._invoices import build_invoice_view


def build_purchase_invoices(page):
    return build_invoice_view(page, "purchase")
