from __future__ import annotations


def whitelist(*args, **kwargs):
    """Aplica `@frappe.whitelist` cuando se ejecuta dentro de Frappe y actúa como no-op en local."""
    try:
        import frappe

        return frappe.whitelist(*args, **kwargs)
    except ImportError:
        def decorator(fn):
            return fn

        return decorator
