from ._invoices import build_invoice_view


def build_sales_invoices(page):
    return build_invoice_view(page, "sales")
