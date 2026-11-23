from __future__ import annotations

"""Restringe la lectura de Notas de Entrega: solo System Manager ve las de otros usuarios."""


def _is_admin(user: str, roles: list[str] | None = None) -> bool:
    if user == "Administrator":
        return True
    if roles is None:
        import frappe

        roles = frappe.get_roles(user)
    return "System Manager" in roles


def get_permission_query_conditions(user: str | None = None, doctype: str | None = None) -> str:
    import frappe

    user = (user or frappe.session.user or "").strip()
    if _is_admin(user):
        return ""
    escaped = frappe.db.escape(user)
    return (
        "(LOWER(COALESCE(NULLIF(`tabDelivery Note`.`ve_vendedor_usuario`, ''), "
        f"`tabDelivery Note`.`owner`)) = LOWER({escaped}))"
    )


def has_permission(doc, ptype: str | None = None, user: str | None = None, **kwargs) -> bool:
    """En Frappe v16 has_permission debe devolver True explícito (None se evalúa como falsy/denegado)."""
    import frappe

    user = (user or frappe.session.user or "").strip()
    if _is_admin(user):
        return True
    if not doc or isinstance(doc, str):
        return True
    seller = ((getattr(doc, "ve_vendedor_usuario", None) or "").strip() or (getattr(doc, "owner", None) or "").strip())
    if not seller or seller.lower() != user.lower():
        return False
    return True
