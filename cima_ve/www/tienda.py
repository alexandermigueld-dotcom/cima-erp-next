from __future__ import annotations

import frappe

no_cache = 1


def get_context(context):
    context.no_cache = 1
    context.full_width = 1
    context.show_sidebar = 0
    context.no_breadcrumbs = 1
    context.title = "CIMA ELECTRONIC VE | Tienda Online"
    context.csrf_token = frappe.sessions.get_csrf_token()
