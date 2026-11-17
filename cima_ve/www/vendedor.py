import frappe

no_cache = 1

SELLER_LANDING = "/app/venta-rapida"


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/vendedor"
    else:
        frappe.local.flags.redirect_location = SELLER_LANDING
    raise frappe.Redirect
